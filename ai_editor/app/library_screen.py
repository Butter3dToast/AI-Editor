"""The Library screen in the new design (Phase 4C-1), as JSON for the frame.

The designer's Library (mockups/Main.dc.html): every recording in a list with
its status, a filter for streams and Let's Plays, and the picked recording's
details underneath, with Who's talking folded away there (4C, 1 Nov). Today's
Library (window.py) keeps working as it is in the browser.

What it can do is what today's can: start an analysis (a job, queued like any
other, one at a time), open the preview copy in your video player, show the file
in Explorer, and name your friends' voices. Nothing here deletes anything.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Here, not in add_routes: FastAPI reads the handlers' types by name from this
# module (4B: imported inside a function, Request wasn't found).
from fastapi import Body, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from ..companion.link import league_events, league_summary, listed
from ..analysis.captions import clock
from ..config import Settings
from ..db import init_db
from . import estimate, library, tasks
from .worker import DONE, FAILED, PAUSED, RUNNING, WAITING, Task, Worker

ROLES = {"mixed": "mixed", "mic": "mic", "game": "game", "voice_chat": "voice chat",
         "music": "music"}
LABEL = re.compile(r"^[A-Z]{1,3}$")       # a stream's voices are Voice A, B... AA


def hms(seconds: float | None) -> str:
    """'2:11:44', as the design writes a length."""
    if not seconds:
        return "-"
    whole = int(round(seconds))
    return f"{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}"


def _local(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone()


def short_day(iso: str | None, now: datetime | None = None) -> str:
    """'Today', 'Yesterday', 'Wed' within the week, else '25 Oct' (or '25 Oct 2025')."""
    moment = _local(iso)
    if moment is None:
        return "-"
    today = (now or datetime.now().astimezone()).date()
    day = moment.date()
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    if today - timedelta(days=6) <= day < today:
        return moment.strftime("%a")
    text = f"{day.day} {moment.strftime('%b')}"
    return text if day.year == today.year else f"{text} {day.year}"


def long_day(iso: str | None) -> str:
    """'Thu 30 Oct, 19:02'."""
    moment = _local(iso)
    return f"{moment.strftime('%a')} {moment.day} {moment.strftime('%b, %H:%M')}" if moment else "-"


def is_lets_play(settings: Settings, game: str | None) -> bool:
    return bool(game) and game.casefold() in {g.casefold() for g in settings.lets_play.games}


def task_for(row, snapshot: list[Task]) -> Task | None:
    """The unfinished job working on this recording, if there is one."""
    source = f"import:{str(row['source_file']).lower()}"
    for task in snapshot:
        if task.status == DONE:
            continue
        if (task.key in (f"analyse:{row['id']}", source)
                or task.result.get("recording_id") == row["id"]):
            return task
    return None


def share_done(task: Task, past: dict, size: float | None, now: float) -> int | None:
    """How far through the whole job it is, from how long its steps took before."""
    if task.started is None:
        return None
    left = estimate.left(task, past, size)
    if left is None:
        return None
    spent = max(0.0, now - task.started)
    return min(99, round(100 * spent / max(1.0, spent + left)))


def status(row, task: Task | None, percent: int | None = None) -> tuple[str, str]:
    """(What the Status column says, its dot): the job if one is on it, else the library."""
    if not Path(row["source_file"]).exists():
        return "Video deleted", "off"
    if task is not None:
        doing = "Importing" if task.key.startswith(("import:", "twitch:")) else "Analysing"
        if task.status == RUNNING:   # no "0%": only once it has really started
            return doing + (f" · {percent}%" if percent else ""), "run"
        if task.status == WAITING:
            return "Waiting in Jobs", "wait"
        if task.status == PAUSED:
            return "Paused", "wait"
        if task.status == FAILED:
            return "Stopped", "fail"
    said = library.status_of(row)
    return {
        "Analysed": ("Analysed", "done"),
        "Analysing": ("Analysing", "run"),
        "Analysis paused": ("Paused", "wait"),
        "Analysis failed": ("Analysis failed", "fail"),
        "Not analysed yet": ("Not analysed", "off"),
        "Import unfinished": ("Import unfinished", "wait"),
    }.get(said, (said, "off"))


def name_of(row) -> str:
    return row["title"] or Path(row["source_file"]).stem


def recordings(conn, settings: Settings, snapshot: list[Task], past: dict,
               now: float) -> list[dict]:
    """Every recording, newest first, as the list shows it."""
    out = []
    for row in library._rows(conn):
        task = task_for(row, snapshot)
        percent = None
        if task is not None and task.status == RUNNING:
            percent = share_done(task, past, estimate.size_of(conn, task) or row["duration_sec"],
                                 now)
        said, state = status(row, task, percent)
        out.append({
            "id": row["id"], "name": name_of(row), "game": row["game"] or "",
            "length": hms(row["duration_sec"]),
            "recorded": short_day(row["recorded_at"] or row["imported_at"]),
            "clips": row["clip_count"] or 0, "status": said, "state": state,
            "lets_play": is_lets_play(settings, row["game"]),
        })
    return out


def _sound(tracks: list) -> str:
    if not tracks:
        return "-"
    if len(tracks) == 1:
        return "1 mixed track"
    return f"{len(tracks)} tracks · " + ", ".join(ROLES.get(t["role"], t["role"].replace("_", " "))
                                                  for t in tracks)


def details(conn, settings: Settings, recording_id: int, snapshot: list[Task]) -> dict | None:
    """Everything about one recording, for the panel under the list."""
    row = next((r for r in library._rows(conn) if r["id"] == recording_id), None)
    if row is None:
        return None
    tracks = conn.execute("SELECT stream_index, role FROM audio_tracks WHERE recording_id = ? "
                          "ORDER BY stream_index", (recording_id,)).fetchall()
    source = Path(row["source_file"])
    gone = not source.exists()
    said, state = status(row, task_for(row, snapshot))
    proxy = Path(row["proxy_path"] or "")
    has_preview = bool(row["proxy_path"]) and proxy.is_file()
    marks = None
    if row["session_id"]:
        marks = conn.execute(
            "SELECT COUNT(*) FROM companion_events WHERE session_id = ? "
            "AND event_type IN ('marker', 'marker_short')", (row["session_id"],)).fetchone()[0]
    facts = [
        ["Sound", _sound(tracks)],
        ["Companion", f"Linked · {marks} marked moment{'s' if marks != 1 else ''}"
         if marks is not None else "Not linked"],
        ["Twitch chat", library.chat_of(row, settings)],
        ["Preview copy", "Ready" if has_preview else "Not made yet"],
        ["Length", hms(row["duration_sec"])],
        ["Video", f"{row['width']}×{row['height']} · {row['fps'] or 0:.0f} fps"
         if row["width"] else "-"],
        ["From", f"Twitch VOD {row['twitch_vod_id']}" if row["twitch_vod_id"]
         else "OBS on this PC"],
        ["Imported", long_day(row["imported_at"])],
    ]
    if row["analysis_status"] == "complete":
        facts.append(["Clips found", str(row["clip_count"])])
        notes = json.loads(row["notes"] or "{}")
        if notes.get("phrases_set_aside"):
            facts.append(["Set aside", f"{notes['phrases_set_aside']} phrase(s) probably music "
                                       "or noise misheard as speech"])
    league = []
    summary = ""
    if row["session_id"]:
        events = league_events(conn, recording_id)
        if events:
            summary = league_summary(events)
            league = [[clock(t), e.get("text") or ""] for t, e in events if listed(e)]
    when = long_day(row["recorded_at"] or row["imported_at"])
    return {
        "id": row["id"], "name": name_of(row),
        "line": " · ".join(x for x in (row["game"], f"recorded {when}") if x),
        "status": said, "state": state, "facts": facts,
        "league": league, "league_summary": summary,
        "file": str(source), "gone": gone, "preview": has_preview,
        # Your Let's Play games from Settings too (Crimson Desert wasn't listed, 1 Nov).
        "game": row["game"] or "",
        "games": sorted(set(library.game_choices(conn)) | set(settings.lets_play.games)),
    }


# --- what its buttons do -------------------------------------------------------------


def set_game(settings: Settings, recording_id: int, game: str) -> str:
    """A recording's game, set or put right after importing (1 Nov: a Dawnwalker episode
    named only by its date, with the Companion off, came in with no game, so it wasn't
    a Let's Play). Only the game changes."""
    from ..games import canonical_game

    name = canonical_game(" ".join((game or "").split()))
    if not name:
        return "Type or pick the game first."
    conn = init_db(settings.db_path)
    try:
        if conn.execute("UPDATE recordings SET game = ? WHERE id = ?",
                        (name, recording_id)).rowcount == 0:
            return "That recording isn't in the library."
        conn.commit()
    finally:
        conn.close()
    if is_lets_play(settings, name):
        return (f"#{recording_id} is now {name}: a Let's Play episode, so it stays out of stream "
                "highlights and is in Create video, Let's Play.")
    return f"#{recording_id} is now {name}."



def _row(settings: Settings, recording_id: int):
    conn = init_db(settings.db_path)
    try:
        return conn.execute(
            "SELECT r.*, (SELECT COUNT(*) FROM audio_tracks a WHERE a.recording_id = r.id) "
            "AS tracks, (SELECT COUNT(*) FROM audio_tracks a WHERE a.recording_id = r.id "
            "AND a.extracted_path IS NOT NULL) AS tracks_ready "
            "FROM recordings r WHERE r.id = ?", (recording_id,)).fetchone()
    finally:
        conn.close()


def analyse(settings: Settings, worker: Worker, recording_id: int) -> str:
    """Analyse it (or carry on where it stopped): a job, queued like any other."""
    row = _row(settings, recording_id)
    if row is None:
        return "That recording isn't in the library any more."
    name = name_of(row)
    said = library.status_of(row)
    if said == library.VIDEO_GONE:
        return (f"The recording isn't at {row['source_file']} any more. If you moved it, "
                "import it from its new place: it's recognised and relinked.")
    if said == "Import unfinished":
        task = worker.submit(f"Importing and analysing #{row['id']} {name}",
                             f"import:{str(row['source_file']).lower()}",
                             tasks.import_file(settings, Path(row["source_file"]), analyse=True))
    else:
        task = worker.submit(f"Analysing #{row['id']} {name}", f"analyse:{row['id']}",
                             tasks.analyse(settings, row["id"]))
    if task is None:
        return "That's already in Jobs."
    ahead = sum(t.status in (WAITING, RUNNING) for t in worker.snapshot()) - 1
    return "Added to Jobs." + (f" It starts after the {ahead} ahead of it." if ahead > 0 else "")


def watch(settings: Settings, recording_id: int) -> str:
    """The preview copy, in the PC's own video player."""
    row = _row(settings, recording_id)
    if row is None:
        return "That recording isn't in the library any more."
    proxy = Path(row["proxy_path"] or "")
    if not row["proxy_path"] or not proxy.is_file():
        return "This recording has no preview copy yet. Import it to make one."
    os.startfile(proxy)  # noqa: S606 -- the PC's video player, on our own file
    return "Opened in your video player. Once analysed, its subtitles load by themselves in VLC."


def explore(settings: Settings, recording_id: int) -> str:
    """Explorer, with the recording picked."""
    row = _row(settings, recording_id)
    if row is None:
        return "That recording isn't in the library any more."
    source = Path(row["source_file"])
    if not source.exists():
        return f"The file isn't at {source} any more."
    subprocess.Popen(["explorer", "/select,", str(source)])  # noqa: S603,S607
    return ""


# --- Who's talking ---------------------------------------------------------------------


def voices(settings: Settings, recording_id: int) -> dict:
    from . import friends_panel
    from ..analysis import voices as voice_data

    found = friends_panel._read(settings, voice_data.stream_voices, recording_id)
    return {
        "intro": friends_panel.INTRO,
        "voices": [{"label": v.label, "said": v.said(),
                    "named": v.friend.name if v.friend else ""} for v in found],
        "friends": friends_panel.friend_names(settings),
    }


def name_voice(settings: Settings, recording_id: int, label: str, name: str) -> str:
    from . import friends_panel
    from ..analysis import voices as voice_data

    return friends_panel._read(settings, voice_data.name_voice, recording_id, label, name or "")


def unname_voice(settings: Settings, recording_id: int, label: str) -> str:
    from . import friends_panel
    from ..analysis import voices as voice_data

    return friends_panel._read(settings, voice_data.unname_voice, recording_id, label)


# --- its addresses in the frame's server (frame_api.py) --------------------------------


def add_routes(app, frame, guarded) -> None:
    settings, worker = frame.settings, frame.worker
    no_cache = {"Cache-Control": "no-store"}

    @app.get("/api/library")
    def everything():
        import time

        conn = init_db(settings.db_path)
        try:
            listed_now = recordings(conn, settings, worker.snapshot(), frame._history(conn),
                                    time.monotonic())
        finally:
            conn.close()
        return JSONResponse({"recordings": listed_now, "version": worker.version,
                             "lets_play": list(settings.lets_play.games)}, headers=no_cache)

    @app.get("/api/library/{recording_id}")
    def one(recording_id: int):
        conn = init_db(settings.db_path)
        try:
            found = details(conn, settings, recording_id, worker.snapshot())
        finally:
            conn.close()
        if found is None:
            raise HTTPException(status_code=404)
        return JSONResponse(found, headers=no_cache)

    @app.post("/api/library/{recording_id}/game")
    def game(recording_id: int, request: Request, game: str = Body("", embed=True)):
        guarded(request)
        return {"said": set_game(settings, recording_id, game)}

    @app.post("/api/library/{recording_id}/{action}")
    def act(recording_id: int, action: str, request: Request):
        guarded(request)
        do = {"analyse": lambda: analyse(settings, worker, recording_id),
              "watch": lambda: watch(settings, recording_id),
              "explore": lambda: explore(settings, recording_id)}.get(action)
        if do is None:
            raise HTTPException(status_code=404)
        return {"said": do()}

    @app.get("/api/library/{recording_id}/voices")
    def stream_voices(recording_id: int):
        return JSONResponse(voices(settings, recording_id), headers=no_cache)

    @app.get("/api/library/{recording_id}/voices/{label}.wav")
    def voice_sample(recording_id: int, label: str):
        from . import friends_panel

        if not LABEL.match(label):
            raise HTTPException(status_code=404)
        found = friends_panel.sample(settings, recording_id, label)
        if not found:
            raise HTTPException(status_code=404)
        return FileResponse(found, media_type="audio/wav")

    @app.post("/api/library/{recording_id}/voices/{label}/{action}")
    def voice_name(recording_id: int, label: str, action: str, request: Request,
                   name: str = Body("", embed=True)):
        guarded(request)
        if not LABEL.match(label) or action not in ("name", "not"):
            raise HTTPException(status_code=404)
        if action == "not":
            return {"said": unname_voice(settings, recording_id, label)}
        return {"said": name_voice(settings, recording_id, label, name)}
