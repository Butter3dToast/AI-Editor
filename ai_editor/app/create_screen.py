"""The Create video screen in the new design (Phase 4E), as JSON for the frame.

The designer's Create video (mockups/Create.dc.html): Highlights, Let's Play or
Shorts in the header; for highlights the game, length, style profile and which
clips, then "What it will use", the streams in reach, oldest first. Ticking
streams there is today's "Only these streams" (the creator, 1 Nov); ticking none
leaves AI-Editor to take the oldest unused clips first, as before. Let's Play
and Shorts, which the mockup doesn't draw, pick their recording from a list like
the Library's.

A plan is made exactly as today's Create video makes it (the same jobs in
tasks.py); create.js opens it in Review once it's ready. Today's Create video
keeps working as it is in the browser.
"""

from __future__ import annotations

# Here, not in add_routes: FastAPI reads the handlers' types by name from this
# module (4B: imported inside a function, Request wasn't found).
from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse

from ..config import Settings
from ..db import init_db
from ..games import canonical_game
from ..recipes.plan import LIKED, SAVED, used_in
from . import library, tasks
from .library_screen import hms, is_lets_play, name_of, short_day
from .worker import DONE, FAILED, RUNNING, WAITING, Worker

KINDS = {"highlights": "Highlights", "letsplay": "Let's Play", "shorts": "Shorts"}
ALL_STREAMS = "All my streams"
WHICH = ("any", "liked", "saved")


def stream_games(conn, settings: Settings) -> list[str]:
    """The Game box: every game, Let's Play games left out (as today's)."""
    return [g for g in library.game_choices(conn) if not is_lets_play(settings, g)]


def picked_style(conn, settings: Settings, kind: str, game: str | None) -> int | None:
    """The profile made for this game and kind of video, as today's Create video picks."""
    from ..style.apply import matching

    return matching(conn, settings, game, kind)


def styles(conn) -> list[dict]:
    from ..style import profiles

    return [{"id": pid, "name": name} for name, pid in profiles.names(conn)]


def _clips(conn, recording_id: int) -> list:
    return conn.execute("SELECT user_rating, used_in_json FROM clips "
                        "WHERE recording_id = ?", (recording_id,)).fetchall()


def in_reach(conn, settings: Settings, game: str | None, reuse: bool) -> list[dict]:
    """The streams a highlight video draws from (recipes.highlights.recordings_for),
    oldest first: what each still has to give. 👎 clips never go in; clips already
    in a video only with "Use clips already in a video".

    No "Best score" (the mockup's): scores are scaled per stream, so every stream's
    best is 1.00 (1 Nov, the creator's library). Your 👍 and 🔖 in it instead."""
    from ..recipes.highlights import recorded_at, recordings_for

    rows = sorted(recordings_for(conn, settings, game=game, recording_ids=None),
                  key=recorded_at)
    out = []
    for row in rows:
        free = [c for c in _clips(conn, row["id"]) if (c["user_rating"] or 0) >= 0
                and (reuse or not used_in(c["used_in_json"], shorts=False))]
        out.append({
            "id": row["id"], "name": name_of(row), "game": row["game"] or "",
            "recorded": short_day(row["recorded_at"] or row["imported_at"]),
            "free": len(free),
            "liked": sum(c["user_rating"] == LIKED for c in free),
            "saved": sum(c["user_rating"] == SAVED for c in free),
        })
    return out


def episodes(conn, settings: Settings, *, streams: bool = False) -> list[dict]:
    """Let's Play recordings to make a plan from, newest first; ``streams``: the rest
    too (today's list had both, Let's Plays first)."""
    from ..recipes.highlights import has_video

    target = settings.lets_play.target_min * 60
    out = []
    for row in conn.execute("SELECT * FROM recordings WHERE analysis_status = 'complete' "
                            "ORDER BY COALESCE(recorded_at, imported_at) DESC"):
        if not has_video(row) or (not streams and not is_lets_play(settings, row["game"])):
            continue
        length = row["duration_sec"] or 0
        out.append({"id": row["id"], "name": name_of(row), "game": row["game"] or "",
                    "length": hms(length),
                    "recorded": short_day(row["recorded_at"] or row["imported_at"]),
                    "parts": max(1, round(length / target)) if length and target else 1})
    return out


def shorts_from(conn, settings: Settings) -> list[dict]:
    """Every analysed recording with its video, newest first, with your Numpad -
    marks (Shorts start from those) and its clips."""
    from ..recipes.highlights import has_video

    marks = dict(conn.execute(
        "SELECT recording_id, COUNT(*) FROM companion_events WHERE event_type = 'marker_short' "
        "AND recording_time_sec IS NOT NULL GROUP BY recording_id").fetchall())
    clips = dict(conn.execute("SELECT recording_id, COUNT(*) FROM clips "
                              "GROUP BY recording_id").fetchall())
    out = []
    for row in conn.execute("SELECT * FROM recordings WHERE analysis_status = 'complete' "
                            "ORDER BY COALESCE(recorded_at, imported_at) DESC"):
        if not has_video(row):
            continue
        out.append({"id": row["id"], "name": name_of(row), "game": row["game"] or "",
                    "length": hms(row["duration_sec"]),
                    "recorded": short_day(row["recorded_at"] or row["imported_at"]),
                    "marks": marks.get(row["id"], 0), "clips": clips.get(row["id"], 0)})
    return out


def _game_of(conn, recording_id: int | None) -> str | None:
    if recording_id is None:
        return None
    row = conn.execute("SELECT game FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    return row["game"] if row else None


def screen(conn, settings: Settings, kind: str, *, game: str | None = None,
           reuse: bool = False, recording: int | None = None, streams: bool = False) -> dict:
    """Everything the screen shows for one kind of video."""
    out = {"kind": kind, "styles": styles(conn)}
    if kind == "highlights":
        game = None if not game or game == ALL_STREAMS else canonical_game(game)
        out.update({
            "games": [ALL_STREAMS, *stream_games(conn, settings)],
            "minutes": settings.highlights.target_length_min,
            "which": "liked" if settings.highlights.only_liked else "any",
            "oldest": settings.highlights.fill_order == "oldest_first",
            "rows": in_reach(conn, settings, game, reuse),
            "picked_style": picked_style(conn, settings, "highlights", game),
        })
    elif kind == "letsplay":
        out.update({"rows": episodes(conn, settings, streams=streams),
                    "target": settings.lets_play.target_min,
                    "picked_style": picked_style(conn, settings, "letsplay",
                                                 _game_of(conn, recording))})
    else:
        out.update({"rows": shorts_from(conn, settings),
                    "picked_style": picked_style(conn, settings, "shorts",
                                                 _game_of(conn, recording))})
    return out


def opening(conn, settings: Settings, recording_id: int) -> dict:
    """Where Clips' Make a video opens: a Let's Play recording on Let's Play, anything
    else on Highlights with that stream ticked (the creator, 1 Nov)."""
    game = _game_of(conn, recording_id)
    return {"kind": "letsplay" if is_lets_play(settings, game) else "highlights",
            "recording": recording_id}


def make(settings: Settings, worker: Worker, choice: dict) -> dict:
    """Start the plan as today's Make the plan does: {"said", "job"}. ``job`` is the
    job's number, to open the plan in Review when it's done (also when the same plan
    was already in Jobs)."""
    kind = choice.get("kind")
    style = choice.get("style")
    profile = int(style) if style not in (None, "", -1) else None
    if kind == "shorts":
        rid = choice.get("recording")
        if rid is None:
            return {"said": "Pick the stream or recording first."}
        key, title = f"make:shorts:{rid}", f"Suggesting Shorts from #{rid}"
        job = tasks.make_shorts(settings, int(rid), profile)
    elif kind == "letsplay":
        rid = choice.get("recording")
        if rid is None:
            return {"said": "Pick the episode's recording first."}
        key, title = f"make:letsplay:{rid}", f"Making a Let's Play plan from #{rid}"
        job = tasks.make_letsplay(settings, int(rid), profile)
    elif kind == "highlights":
        game = choice.get("game")
        game = None if not game or game == ALL_STREAMS else canonical_game(game)
        ids = [int(x) for x in choice.get("recordings") or []] or None
        which = choice.get("which") if choice.get("which") in WHICH else "any"
        try:
            minutes = float(choice["minutes"]) if choice.get("minutes") not in (None, "") \
                else None
        except (TypeError, ValueError):
            return {"said": "The length is a number of minutes, like 10."}
        if minutes is not None and not 1 <= minutes <= 60:
            return {"said": "The length is between 1 and 60 minutes."}
        # One job per game and streams: several plans queue from Create video (1 Nov),
        # but the same game from the same streams would replace the draft before it
        # (plan.discard_drafts), so that one is watched instead.
        key = f"make:highlights:{game}:{','.join(map(str, sorted(ids))) if ids else 'all'}"
        title = f"Making a {game or 'stream'} highlights plan"
        job = tasks.make_highlights(settings, game=game, recording_ids=ids, minutes=minutes,
                                    reuse=bool(choice.get("reuse")), profile=profile,
                                    only_liked=which == "liked", saved=which == "saved")
    else:
        return {"said": "That isn't a kind of video."}
    task = worker.submit(title, key, job)
    if task is None:   # the same plan is already being made: watch that one
        same = next((t for t in worker.snapshot()
                     if t.key == key and t.status not in (DONE, FAILED)), None)
        return {"said": "That plan is already being made. It opens in Review when it's ready.",
                "job": same.id if same else None}
    ahead = sum(t.status in (WAITING, RUNNING) for t in worker.snapshot()) - 1
    return {"said": "Making the plan. It opens in Review when it's ready."
                    + (f" It starts after the {ahead} job{'s' if ahead != 1 else ''} ahead "
                       "of it." if ahead > 0 else ""),
            "job": task.id}


def made(worker: Worker, job_id: int) -> dict:
    """How a plan's job is getting on: running, ready (with its plan) or failed."""
    task = next((t for t in worker.snapshot() if t.id == job_id), None)
    if task is None:
        return {"state": "gone"}
    if task.status == DONE:
        if "plan_id" in task.result:
            return {"state": "ready", "plan": task.result["plan_id"], "title": task.title}
        return {"state": "failed", "error": (task.lines or ["No plan was made."])[-1]}
    if task.status == FAILED:
        return {"state": "failed", "error": task.error or "The plan couldn't be made."}
    return {"state": "waiting"}


# --- its addresses in the frame's server (frame_api.py) --------------------------------


def add_routes(app, frame, guarded) -> None:
    settings, worker = frame.settings, frame.worker
    no_cache = {"Cache-Control": "no-store"}

    def read(fn, *args, **kwargs):
        conn = init_db(settings.db_path)
        try:
            return fn(conn, *args, **kwargs)
        finally:
            conn.close()

    @app.get("/api/create/from/{recording_id}")
    def start_from(recording_id: int):
        return JSONResponse(read(opening, settings, recording_id), headers=no_cache)

    @app.get("/api/create/job/{job_id}")
    def job(job_id: int):
        return JSONResponse(made(worker, job_id), headers=no_cache)

    @app.post("/api/create/make")
    def make_plan(request: Request, choice: dict = Body(...)):
        guarded(request)
        return make(settings, worker, choice)

    @app.get("/api/create/{kind}")
    def create(kind: str, game: str | None = None, reuse: bool = False,
               recording: int | None = None, streams: bool = False):
        if kind not in KINDS:
            raise HTTPException(status_code=404)
        return JSONResponse(read(screen, settings, kind, game=game, reuse=reuse,
                                 recording=recording, streams=streams), headers=no_cache)
