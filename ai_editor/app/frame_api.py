"""The new frame (Phase 4B): served in AI-Editor's own window.

The frame is plain HTML, CSS and JavaScript (app/frame/), in the Phase 4
design (mockups/): the sidebar, the header, the Jobs panel and the morning
note. Until each screen is rebuilt (4C-4H), its body shows today's screen,
served under /classic and shown without its own title, Jobs box and tabs.

Only the window serves this. ``ai-editor app`` in the browser starts exactly
as before (the creator's rule while Phase 4 is built, 31 Oct).

The frame learns everything from small JSON answers here, asked every second
or so. Nothing here is reachable from outside this PC (127.0.0.1), and every
change (Pause, Resume, the Companion...) needs a header no web page in a
browser can send to it, so no website can press these buttons.
"""

from __future__ import annotations

import html
import re
import shutil
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import Settings
from ..db import init_db
from ..logging_setup import get_logger
from . import estimate
from .worker import DONE, FAILED, PAUSED, RUNNING, WAITING, Task, Worker

log = get_logger(__name__)

FRAME = Path(__file__).with_name("frame")
CLASSIC = "/classic"
GUARD = "X-AI-Editor"          # every change must carry it: no web page can send it here
COUNTS_EVERY_SEC = 5.0

STATES = {RUNNING: ("Running", "run"), WAITING: ("Waiting", "wait"), PAUSED: ("Paused", "wait"),
          FAILED: ("Stopped", "fail"), DONE: ("Finished", "done")}


def _clock(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return "under a minute"
    return f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 60 else f"{minutes} min"


class Frame:
    """What the frame's JSON answers come from: the jobs and the library."""

    def __init__(self, settings: Settings, worker: Worker) -> None:
        self.settings, self.worker = settings, worker
        self._past: dict | None = None
        self._past_version = -1
        self._counts: tuple[float, dict] | None = None
        self._lock = threading.Lock()

    # --- jobs ------------------------------------------------------------------------

    def _history(self, conn) -> dict:
        """The past step times, read again whenever another job has finished."""
        finished = sum(t.status == DONE for t in self.worker.snapshot())
        with self._lock:
            if self._past is None or self._past_version != finished:
                self._past, self._past_version = estimate.history(conn), finished
            return self._past

    def jobs(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        snapshot = self.worker.snapshot()
        conn = init_db(self.settings.db_path) if any(t.status == RUNNING for t in snapshot) \
            else None
        try:
            cards = [self.card(t, now, conn) for t in snapshot]
        finally:
            if conn is not None:
                conn.close()
        return {"version": self.worker.version, "jobs": cards}

    def card(self, task: Task, now: float, conn=None) -> dict:
        badge, style = STATES[task.status]
        if task.status == RUNNING and task.started is not None:
            meta = f"{_clock(now - task.started)} in"
            if conn is not None:
                left = estimate.words(estimate.left(task, self._history(conn),
                                                    estimate.size_of(conn, task)))
                meta += f" · {left}" if left else ""
        elif task.status == WAITING:
            meta = "starts when the one before it finishes"
        elif task.status == DONE and task.started is not None:
            meta = f"took {_clock((task.finished or now) - task.started)}"
        elif task.status == PAUSED:
            cut = next((label for label, f in task.steps.items() if f < 1.0), None)
            meta = (f"stopped at {task.steps[cut]:.0%} of {cut.lower()} · nothing is lost"
                    if cut else "nothing is lost")
        else:
            meta = ""
        action = None
        if task.error and re.search(r"free (some )?space|GB free", task.error, re.IGNORECASE):
            action = {"label": "Free up space", "screen": "storage"}
        return {"id": task.id, "title": task.title, "badge": badge, "state": style, "meta": meta,
                "steps": [[label, round(f, 3)] for label, f in task.steps.items()],
                "lines": task.lines[-8:], "error": task.error, "action": action,
                "resume": task.status in (PAUSED, FAILED)}

    # --- the sidebar, the header, the Companion, the morning note ------------------------

    def counts(self) -> dict:
        """The sidebar's numbers and each screen's line, at most every few seconds."""
        with self._lock:
            if self._counts and time.monotonic() - self._counts[0] < COUNTS_EVERY_SEC:
                return self._counts[1]
        conn = init_db(self.settings.db_path)
        try:
            found = self._count(conn)
        finally:
            conn.close()
        with self._lock:
            self._counts = (time.monotonic(), found)
        return found

    def _count(self, conn) -> dict:
        rows = conn.execute("SELECT id, source_file, analysis_status FROM recordings").fetchall()
        kept = [r for r in rows if Path(r["source_file"]).exists()]
        with_video = {r["id"] for r in kept}
        unrated = 0
        if with_video:
            unrated = conn.execute(
                f"SELECT COUNT(*) FROM clips WHERE user_rating IS NULL AND recording_id IN "
                f"({','.join('?' * len(with_video))})", sorted(with_video)).fetchone()[0]
        drafts = conn.execute("SELECT COUNT(*) FROM edit_plans WHERE status = 'draft'").fetchone()[0]
        open_issues = conn.execute("SELECT COUNT(*) FROM issues WHERE status = 'open'").fetchone()[0]
        profiles = conn.execute("SELECT COUNT(*) FROM style_profiles").fetchone()[0]
        rules = conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
        free = _free_gb(self.settings.folders.raw)
        plural = lambda n, one, many=None: f"{n} {one if n == 1 else (many or one + 's')}"  # noqa: E731
        return {
            "tallies": {"library": len(kept), "clips": unrated, "review": drafts,
                        "issues": open_issues},
            "lines": {
                # The designer's line (4C-1): how many, and room left where they are.
                "library": plural(len(kept), "recording") + (
                    f" · {free:.0f} GB free on {self.settings.folders.raw.drive or 'disk'}"
                    if free is not None else ""),
                # The designer's line (4C-2); how many are new is on the screen itself.
                "import": "Your file is read where it is: never copied, moved or changed",
                "clips": f"{unrated} not rated yet" if unrated else "Every clip rated",
                # The designer's line (4E).
                "create": "Builds a plan you can change before anything renders",
                "review": plural(drafts, "draft") + " waiting" if drafts else "No drafts waiting",
                "style": plural(profiles, "profile"),
                "rules": plural(rules, "rule"),
                "storage": f"{free:.0f} GB free where your recordings are" if free is not None
                else "",
                "settings": "Saved on this PC only",
                "issues": f"{open_issues} open" if open_issues else "Nothing open",
            },
        }

    def companion(self) -> dict:
        from ..companion import status

        current = status.read(status.folder(self.settings))
        if current is None:
            return {"running": False, "title": "Companion off", "detail": "Start it before you play"}
        good = current.get("obs") == "connected"
        live = [label for key, label in (("stream", "live"), ("record", "recording"))
                if (current.get(key) or {}).get("on")]
        marks = current.get("markers", 0) + current.get("shorts", 0)
        detail = " · ".join([*live, f"{marks} mark{'s' if marks != 1 else ''} today"])
        return {"running": True, "warn": not good,
                "title": "Companion running" if good else "Companion: no OBS yet",
                "detail": detail}

    def note(self) -> dict | None:
        from . import overnight

        conn = init_db(self.settings.db_path)
        try:
            found = overnight.morning_note(conn, self.settings)
        finally:
            conn.close()
        if found is None:
            return None
        night_id, text = found
        # **bold** -> <b>, the rest kept as text.
        safe = html.escape(text)
        return {"id": night_id, "html": re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)}


def _free_gb(folder: Path) -> float | None:
    for path in (folder, *folder.parents):
        if path.exists():
            return shutil.disk_usage(path).free / 1e9
    return None


def build_app(settings: Settings, ui, worker: Worker, *, mount_kwargs: dict):
    """The frame, its answers, and today's screens under /classic."""
    import gradio as gr

    from .. import __product_name__, __version__

    frame = Frame(settings, worker)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    no_cache = {"Cache-Control": "no-store"}

    def guarded(request: Request) -> None:
        if request.headers.get(GUARD) != "1":
            raise HTTPException(status_code=403)

    @app.get("/")
    def page():
        # Opened in the chosen theme straight away: no flash of the other one.
        text = (FRAME / "index.html").read_text(encoding="utf-8")
        text = text.replace('data-theme="auto"', f'data-theme="{settings.appearance.theme}"')
        return HTMLResponse(text, headers=no_cache)

    favicon = mount_kwargs.pop("favicon_path", None)

    @app.get("/favicon.ico")
    def icon():
        return FileResponse(favicon) if favicon else JSONResponse({}, status_code=404)

    @app.get("/config")
    def config():
        # What `ai-editor app` looks for: AI-Editor is open, here, in its window.
        return {"title": __product_name__, "aie_frame": True}

    @app.get("/api/frame")
    def about():
        return JSONResponse({"version": __version__, **frame.counts(),
                             "companion": frame.companion(), "note": frame.note(),
                             "theme": settings.appearance.theme}, headers=no_cache)

    @app.post("/api/theme/{mode}")
    def theme(mode: str, request: Request):
        """Auto, light or dark: kept in your settings, whatever Windows is set to."""
        guarded(request)
        if mode not in ("auto", "light", "dark"):
            raise HTTPException(status_code=404)
        from ..config import save_local_settings
        from .manage_tabs import apply

        apply(settings, save_local_settings(settings.source_path, {("appearance", "theme"): mode}))
        return {"theme": mode}

    @app.get("/api/jobs")
    def jobs():
        return JSONResponse(frame.jobs(), headers=no_cache)

    @app.post("/api/jobs/pause")
    def pause(request: Request):
        guarded(request)
        return {"held": worker.pause()}

    @app.post("/api/jobs/resume")
    def resume(request: Request, id: int | None = None):  # noqa: A002 -- the query's name
        guarded(request)
        return {"resumed": worker.resume(id)}

    @app.post("/api/jobs/clear")
    def clear(request: Request):
        guarded(request)
        worker.clear_finished()
        return {}

    @app.post("/api/companion/{action}")
    def companion(action: str, request: Request):
        guarded(request)
        from . import companion_panel

        if action not in ("start", "stop"):
            raise HTTPException(status_code=404)
        said = (companion_panel.start if action == "start" else companion_panel.stop)(settings)
        return {"said": said}

    @app.post("/api/note/{night_id}/seen")
    def seen(night_id: int, request: Request):
        guarded(request)
        from . import overnight

        conn = init_db(settings.db_path)
        try:
            overnight.mark_seen(conn, night_id)
        finally:
            conn.close()
        return {}

    from . import clips_screen, create_screen, import_screen, library_screen

    library_screen.add_routes(app, frame, guarded)   # 4C-1: the Library, rebuilt
    import_screen.add_routes(app, frame, guarded)    # 4C-2: Import, rebuilt
    clips_screen.add_routes(app, frame, guarded)     # 4D: Clips, rebuilt
    create_screen.add_routes(app, frame, guarded)    # 4E: Create video, rebuilt
    app.mount("/frame", StaticFiles(directory=FRAME), name="frame")
    return gr.mount_gradio_app(app, ui, path=CLASSIC, **mount_kwargs)


class Server:
    """The window's server: uvicorn on 127.0.0.1, in the background."""

    def __init__(self, app, host: str, port: int) -> None:
        import uvicorn

        self._server = uvicorn.Server(uvicorn.Config(app, host=host, port=port,
                                                     log_level="warning", access_log=False))
        self._thread = threading.Thread(target=self._server.run, name="ai-editor-frame",
                                        daemon=True)

    def start(self, wait: float = 30.0) -> None:
        self._thread.start()
        deadline = time.monotonic() + wait
        while not self._server.started and time.monotonic() < deadline:
            if not self._thread.is_alive():
                raise RuntimeError("AI-Editor's page couldn't start (is the address in use?)")
            time.sleep(0.05)
        if not self._server.started:
            raise RuntimeError("AI-Editor's page didn't start in time")

    def close(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)
