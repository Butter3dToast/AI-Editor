"""The Import screen in the new design (Phase 4C-2), as JSON for the frame.

The designer's Import (mockups/Import.dc.html), in two halves: From this PC,
the new recordings in your raw folder with a tick box each (several at once,
the creator's choice, 1 Nov), or a file anywhere; and From Twitch, a VOD link
checked, then downloaded and imported. Today's Import keeps working as it is in
the browser.

Every import is a job in the same queue as the rest, so ticking three runs them
one after another, never side by side, each with the usual graphics-card check
first (the creator asked that it not overload the PC). A file is read where it
is: never copied, moved or changed.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Here, not in add_routes: FastAPI reads the handlers' types by name from this
# module (4B: imported inside a function, Request wasn't found).
from fastapi import Body, Request
from fastapi.responses import JSONResponse

from ..config import Settings
from ..db import init_db
from ..errors import AIEditorError
from ..games import canonical_game, suggest_game
from ..logging_setup import get_logger
from . import library, tasks
from .library_screen import hms, long_day, short_day
from .worker import DONE, RUNNING, WAITING, Worker

log = get_logger(__name__)


# --- the raw folder's new recordings ---------------------------------------------------


class Probes:
    """What ffprobe said about each new file, asked once per file (by its size and time)."""

    def __init__(self) -> None:
        self._seen: dict[tuple[str, int, float], dict] = {}
        self._lock = threading.Lock()

    def __call__(self, found: library.NewFile) -> dict:
        key = (str(found.path), found.size, found.modified)
        with self._lock:
            if key in self._seen:
                return self._seen[key]
        from ..ffmpeg import probe

        try:
            info = probe(found.path)
            said = {"length": hms(info.duration_sec), "duration": info.duration_sec,
                    "sound": (f"{len(info.audio)} tracks" if len(info.audio) > 1
                              else "1 mixed track" if info.audio else "No sound")}
        except Exception as exc:  # noqa: BLE001 -- shown as "can't read it", the rest go on
            log.info("Couldn't read %s: %s", found.path, exc)
            said = {"length": "-", "duration": None, "sound": "Can't read it"}
        with self._lock:
            self._seen[key] = said
        return said


def companion_games(conn, found: library.NewFile, duration: float | None) -> list[str]:
    """The games the Stream Companion saw while this file was recorded, if it was running."""
    from ..companion.link import find_session, started_at_of, started_from_name

    guesses = [g for g in (started_from_name(found.path), started_at_of(found.path, duration))
               if g is not None]
    match = find_session(conn, source_file=found.path, started_at=guesses)
    if match is None:
        return []
    began = match.started_at.isoformat()
    until = (match.started_at + timedelta(seconds=duration or 12 * 3600)).isoformat()
    # The scene showing when recording began (set before pressing record), then any after.
    rows = conn.execute(
        "SELECT payload_json FROM companion_events WHERE session_id = ? AND event_type = "
        "'obs_scene' AND wall_clock <= ? ORDER BY wall_clock DESC LIMIT 1",
        (match.session_id, began)).fetchall()
    rows += conn.execute(
        "SELECT payload_json FROM companion_events WHERE session_id = ? AND event_type = "
        "'obs_scene' AND wall_clock > ? AND wall_clock <= ? ORDER BY wall_clock",
        (match.session_id, began, until)).fetchall()
    games = (json.loads(r["payload_json"] or "{}").get("game") for r in rows)
    return list(dict.fromkeys(g for g in games if g))


def new_files(conn, settings: Settings, probes: Probes, snapshot) -> list[dict]:
    """The raw folder's videos not in the library yet, newest first, as the list shows them."""
    queued = {t.key for t in snapshot if t.status != DONE}
    out = []
    for found in library.new_recordings(conn, settings):
        said = {"length": "-", "duration": None, "sound": "-"} if found.still_recording \
            else probes(found)
        game = suggest_game(found.path.stem, settings.lets_play.games)
        game_from = "the file name" if game else ""
        if not game and not found.still_recording:
            try:
                played = companion_games(conn, found, said["duration"])
            except Exception:  # noqa: BLE001 -- only a guess: worked out again on import
                played = []
            if played:
                game, game_from = " + ".join(played), "the Stream Companion"
        # When it started: OBS's file name says; else when the file was last saved.
        from ..companion.link import started_from_name

        began = started_from_name(found.path) or datetime.fromtimestamp(found.modified,
                                                                         tz=timezone.utc)
        made = began.isoformat()
        out.append({
            "path": str(found.path), "name": found.path.name, "length": said["length"],
            "recorded": short_day(made), "when": long_day(made), "sound": said["sound"],
            "size": library.size_text(found.size), "game": game or "", "game_from": game_from,
            "still_recording": found.still_recording,
            "in_jobs": f"import:{str(found.path).lower()}" in queued,
        })
    return out


# --- importing ---------------------------------------------------------------------------


def import_files(settings: Settings, worker: Worker, paths: list[str], *, analyse: bool = True,
                 game: str = "", tracks: str = "", vod_link: str = "") -> str:
    """Each file a job of its own, queued one after another. Game, sound tracks and a
    Twitch link are for one file at a time, so with several they're left out."""
    from .. import twitch

    chosen = list(dict.fromkeys(p.strip().strip('"') for p in paths if p and p.strip()))
    if not chosen:
        return "Tick a recording in the list, or Browse to one."
    one = len(chosen) == 1
    vod_link = (vod_link or "").strip() if one else ""
    if vod_link:
        try:
            twitch.parse_vod_id(vod_link)
        except AIEditorError as exc:
            return exc.user_message()
    problems, added, already = [], 0, 0
    what = "Importing and analysing" if analyse else "Importing"
    for text in chosen:
        path, problem = library.check_importable(text)
        if problem:
            problems.append(problem)
            continue
        task = worker.submit(
            f"{what} {path.name}", f"import:{str(path).lower()}",
            tasks.import_file(settings, path,
                              game=canonical_game(game) if one and game.strip() else None,
                              tracks=(tracks.strip() or None) if one else None,
                              vod_link=vod_link or None, analyse=analyse))
        if task is None:
            already += 1
        else:
            added += 1
    said = []
    if added:
        said.append("Added to Jobs." if added == 1 else
                    f"Added {added} to Jobs: they run one after another.")
    if already:
        said.append("That's already in Jobs." if already == 1 else
                    f"{already} were already in Jobs.")
    return " ".join(said + problems)


def check_vod(settings: Settings, link: str, now: datetime | None = None) -> dict:
    """What Twitch says about a VOD, before downloading it."""
    from .. import twitch

    try:
        info = twitch.vod_info(settings, twitch.parse_vod_id(link or ""))
    except AIEditorError as exc:
        return {"problem": exc.user_message()}
    left = None
    if info.created_at is not None:
        left = library.days_left(info.created_at.isoformat(), settings.twitch.vod_keep_days, now)
    return {
        "title": info.title or "Twitch VOD", "channel": info.channel or "",
        "game": info.game or "", "length": hms(info.length_sec),
        "streamed": long_day(info.created_at.isoformat()).rsplit(",", 1)[0]
        if info.created_at else "-",
        "deletes": ("may already be gone" if left is not None and left <= 0 else
                    f"in {left:.0f} day{'s' if round(left) != 1 else ''}" if left is not None
                    else "not known"),
        "soon": left is not None and left <= 3,
        "warning": twitch.expiry_warning(info, settings.twitch.vod_keep_days, now) or "",
    }


def import_vod(settings: Settings, worker: Worker, link: str, *, game: str = "",
               chat: bool = True, analyse: bool = True) -> str:
    from .. import twitch

    try:
        vod_id = twitch.parse_vod_id(link or "")
    except AIEditorError as exc:
        return exc.user_message()
    task = worker.submit(f"Twitch VOD {vod_id}", f"twitch:{vod_id}",
                         tasks.import_twitch(settings, link,
                                             game=canonical_game(game) if game.strip() else None,
                                             chat=chat, analyse=analyse))
    if task is None:
        return "That's already in Jobs."
    ahead = sum(t.status in (WAITING, RUNNING) for t in worker.snapshot()) - 1
    return "Added to Jobs." + (f" It starts after the {ahead} ahead of it." if ahead > 0 else "")


# --- its addresses in the frame's server (frame_api.py) --------------------------------


def add_routes(app, frame, guarded) -> None:
    settings, worker = frame.settings, frame.worker
    probes = Probes()
    no_cache = {"Cache-Control": "no-store"}

    @app.get("/api/import")
    def everything():
        conn = init_db(settings.db_path)
        try:
            files = new_files(conn, settings, probes, worker.snapshot())
            games = library.game_choices(conn)
        finally:
            conn.close()
        return JSONResponse({"raw": str(settings.folders.raw), "files": files,
                             "games": sorted(set(games) | set(settings.lets_play.games)),
                             "version": worker.version}, headers=no_cache)

    @app.post("/api/import/files")
    def files(request: Request, paths: list[str] = Body(...), analyse: bool = Body(True),
              game: str = Body(""), tracks: str = Body(""), vod: str = Body("")):
        guarded(request)
        return {"said": import_files(settings, worker, paths, analyse=analyse, game=game,
                                     tracks=tracks, vod_link=vod)}

    @app.post("/api/import/browse")
    def browse(request: Request, start: str = Body("", embed=True)):
        """Windows' own Open dialog (today's Browse)."""
        guarded(request)
        here = Path(start).parent if start and Path(start).parent.is_dir() else settings.folders.raw
        return {"path": library.browse_for_video(here)}

    @app.post("/api/import/twitch/check")
    def check(request: Request, link: str = Body("", embed=True)):
        guarded(request)       # asks Twitch: only AI-Editor's own page may
        return check_vod(settings, link)

    @app.post("/api/import/twitch")
    def vod(request: Request, link: str = Body(...), game: str = Body(""),
            chat: bool = Body(True), analyse: bool = Body(True)):
        guarded(request)
        return {"said": import_vod(settings, worker, link, game=game, chat=chat, analyse=analyse)}
