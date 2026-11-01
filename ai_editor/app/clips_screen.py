"""The Clips screen in the new design (Phase 4D), as JSON for the frame.

The designer's Clips (mockups/Clips.dc.html): the player with the rating
buttons under it and the clip's details beside it, kept at the top while the
list scrolls underneath (the creator: "I don't want to keep scrolling up and
down", 1 Nov); after a rating it moves to the next clip by itself, and the
keyboard rates too (clips.js). The list keeps the designer's columns; the rest
of today's (In a video, Your taste, Why, You said, Used) is in the details.

Ratings are kept exactly as today's Clips keeps them (videos.rate), so what
AI-Editor learns from them is the same. Today's Clips keeps working as it is
in the browser.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.parse import quote

# Here, not in add_routes: FastAPI reads the handlers' types by name from this
# module (4B: imported inside a function, Request wasn't found).
from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse

from ..analysis.ai_rating import notes_for
from ..analysis.captions import clock
from ..cli import SIGNAL_LABELS
from ..config import Settings
from ..db import init_db
from ..recipes.plan import LIKED, SAVED, used_in
from . import tasks, videos
from .library_screen import name_of, short_day
from .worker import RUNNING, WAITING, Worker

SHOWS = {"unused": "Not used yet", "all": "All", "rated": "Rated"}
RATINGS = {1: "👍", 2: "🔖", -1: "👎"}
MARKS = {"marker", "marker_short"}
AFTER = {LIKED: " It goes into your next highlight video. To put it in one you've already "
                "made, use 'Add a clip' in Review.",
         SAVED: " To make that video: Create video, then Which clips: My 🔖 next-video clips."}


class Lengths:
    """Each clip's length in a video (videos.video_lengths: the highlight picker run
    over the recording, about half a second on the creator's streams), kept per
    recording until something it depends on changes.

    The list refreshes every few seconds and the details on every click, so working
    it out each time made rating lag (1 Nov). It depends on the clips used in videos,
    the settings, rules and style profiles, and leaves 👎 clips out: a new 👎 is
    simply left out of what's kept; a 👎 cleared, or any of the rest changed, works it
    out again, as does EVERY_SEC passing. 👍 and 🔖 change nothing here.
    """

    EVERY_SEC = 300.0

    def __init__(self) -> None:
        self._kept: dict[int, tuple] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _stamp(conn, settings: Settings, rows) -> tuple:
        rules = conn.execute("SELECT group_concat(id || ':' || enabled || ':' || "
                             "length(COALESCE(rule_json, '')), ',') FROM rules").fetchone()[0]
        styles = conn.execute("SELECT COUNT(*), MAX(updated_at) FROM style_profiles").fetchone()
        return (tuple(sorted((r["clip_id"], r["used_in_json"] or "") for r in rows)),
                rules, tuple(styles), hash(settings.model_dump_json()))

    def __call__(self, conn, settings: Settings, recording_id: int) -> dict[str, float]:
        rows = conn.execute("SELECT clip_id, user_rating, used_in_json FROM clips "
                            "WHERE recording_id = ?", (recording_id,)).fetchall()
        down = {r["clip_id"] for r in rows if (r["user_rating"] or 0) < 0}
        stamp = self._stamp(conn, settings, rows)
        with self._lock:
            kept = self._kept.get(recording_id)
        if (kept is None or kept[0] != stamp or not kept[1] <= down
                or time.monotonic() - kept[3] > self.EVERY_SEC):
            kept = (stamp, down, videos.video_lengths(conn, settings, recording_id),
                    time.monotonic())
            with self._lock:
                self._kept[recording_id] = kept
        return {cid: length for cid, length in kept[2].items() if cid not in down}


def plain_lengths(conn, settings: Settings, recording_id: int) -> dict[str, float]:
    return videos.video_lengths(conn, settings, recording_id)


def recordings(conn, settings: Settings, *, deleted: bool = False) -> list[dict]:
    """The analysed recordings to pick from, newest first (as today's Clips)."""
    rows = {r["id"]: r for r in conn.execute("SELECT * FROM recordings")}
    out = []
    for label, rid in videos.analysed_choices(conn, settings, deleted=deleted):
        row = rows[rid]
        gone = not Path(row["source_file"]).is_file()
        out.append({"id": rid, "name": name_of(row), "game": row["game"] or "",
                    "day": short_day(row["recorded_at"] or row["imported_at"]),
                    "label": label.strip(), "gone": gone})
    return out


def video_url(conn, recording_id: int) -> str:
    """Where the window plays the recording's preview copy (today's screens' address:
    only AI-Editor's own cache and output folders are served there)."""
    proxy = videos.proxy_of(conn, recording_id)
    if proxy is None or not proxy.is_file():
        return ""
    return (f"/classic/gradio_api/file={quote(proxy.as_posix(), safe='/:')}"
            f"?v={proxy.stat().st_mtime_ns}")


def what_happens(note, said: str) -> str:
    """The list's one line: the AI's summary, else the words said."""
    if note is not None:
        return note.summary
    said = " ".join((said or "").split())
    return (said[:90] + "…" if len(said) > 90 else said) or "-"


def listing(conn, settings: Settings, recording_id: int, show: str = "unused",
            lengths_of=plain_lengths) -> dict:
    """The recording's clips, best first (your taste's order where it's in use)."""
    from ..learning.taste import ranked

    row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    if row is None:
        return {}
    rows, _ = ranked(conn, settings, recording_id)
    notes = notes_for(conn, recording_id, rows)
    clips = []
    for clip in rows:
        used = used_in(clip["used_in_json"], shorts=False)
        if show == "unused" and used:
            continue
        if show == "rated" and clip["user_rating"] is None:
            continue
        clips.append({
            "id": clip["clip_id"], "n": len(clips) + 1, "at": clock(clip["start_sec"]),
            "length": f"{clip['end_sec'] - clip['start_sec']:.0f} s",
            "score": f"{clip['score']:.2f}",
            "what": what_happens(notes.get(clip["clip_id"]), clip["transcript"]),
            "rated": RATINGS.get(clip["user_rating"], ""),
            "start": clip["start_sec"], "end": clip["end_sec"],
            "marked": bool(MARKS & set(json.loads(clip["signals_json"] or "{}")
                                       .get("reasons", []))),
        })
    found = len(rows)
    unused = sum(not used_in(c["used_in_json"], shorts=False) for c in rows)
    when = short_day(row["recorded_at"] or row["imported_at"])
    lengths = lengths_of(conn, settings, recording_id)
    return {
        "recording": {"id": row["id"], "name": name_of(row), "game": row["game"] or "",
                      "gone": not Path(row["source_file"]).is_file()},
        "line": " · ".join(x for x in (row["game"] or name_of(row), when) if x)
                + f" · {found} found · {unused} not used yet",
        "totals": videos.clip_summary(conn, settings, recording_id, lengths).replace("**", ""),
        "video": video_url(conn, recording_id), "clips": clips,
    }


def details(conn, settings: Settings, clip_id: str, lengths_of=plain_lengths) -> dict | None:
    """Everything about one clip, for the panel beside the player."""
    from ..learning.taste import ranked

    clip = conn.execute("SELECT * FROM clips WHERE clip_id = ?", (clip_id,)).fetchone()
    if clip is None:
        return None
    summary = json.loads(clip["signals_json"] or "{}")
    reasons = summary.get("reasons", [])
    _, liking = ranked(conn, settings, clip["recording_id"])
    lengths = lengths_of(conn, settings, clip["recording_id"])
    note = notes_for(conn, clip["recording_id"], [clip]).get(clip_id)
    used = json.loads(clip["used_in_json"] or "[]")
    places = (["video"] if used_in(clip["used_in_json"], shorts=False) else []) + \
        (["Short"] if used_in(clip["used_in_json"], shorts=True) else [])
    facts = [
        ["At", f"{clock(clip['start_sec'])}–{clock(clip['end_sec'])}"],
        ["In a video", f"{lengths[clip_id]:.0f} s" if clip_id in lengths else "Can't go in one"],
        ["Score", f"{clip['score']:.2f}"],
        ["Your taste", f"{liking[clip_id]:.0%}" if clip_id in liking else "-"],
        ["Why", ("⭐ Marked by you · " if MARKS & set(reasons) else "")
         + (", ".join(SIGNAL_LABELS.get(r, r) for r in reasons if r not in MARKS) or "-")],
        ["Used", " + ".join(places) or "Not yet"],
    ]
    if summary.get("game"):
        facts.insert(4, ["Game", summary["game"]])
    ai = None
    if note is not None:
        ai = {"stars": note.stars, "summary": note.summary, "reason": note.reason,
              "alone": ("Makes sense on its own (a Short)" if note.stands_alone
                        else "Needs the rest of the stream to make sense"),
              "tags": note.tags}
    league = [[clock(e["t"]), e["text"]] for e in json.loads(clip["game_events_json"] or "[]")]
    return {"id": clip_id, "facts": facts, "ai": ai, "league": league,
            "said": (clip["transcript"] or "").strip(), "used_in": used,
            "rated": RATINGS.get(clip["user_rating"], ""),
            "start": clip["start_sec"], "end": clip["end_sec"]}


def rate(settings: Settings, clip_id: str, rating: int | None) -> str:
    """As today's buttons: kept for learning (videos.rate), with the same words after."""
    if rating not in (LIKED, SAVED, -1, None):
        return "That isn't a rating."
    conn = init_db(settings.db_path)
    try:
        said = videos.rate(conn, clip_id, rating, settings)
    finally:
        conn.close()
    return said + AFTER.get(rating, "") if not said.startswith("That clip") else said


def rate_with_ai(settings: Settings, worker: Worker, recording_id: int) -> str:
    if not settings.llm.enabled:
        return "The AI is switched off in Settings (AI)."
    task = worker.submit(f"AI rating the clips of #{recording_id}", f"rate:{recording_id}",
                         tasks.rate_clips(settings, recording_id))
    if task is None:
        return "That's already in Jobs."
    ahead = sum(t.status in (WAITING, RUNNING) for t in worker.snapshot()) - 1
    return "Added to Jobs." + (f" It starts after the {ahead} ahead of it." if ahead > 0 else "")


def knows(conn) -> dict:
    """How well AI-Editor knows you: per game, a line per week (learning.scoreboard)."""
    from ..learning.scoreboard import TOP, weeks

    found = weeks(conn)
    share = lambda v, top, of: "-" if v is None else f"{v:.0%} ({top} of {of})"  # noqa: E731
    games = []
    for game in dict.fromkeys(w.game for w in found):
        games.append({"game": game, "weeks": [
            [f"{w.monday.day} {w.monday:%b}", w.streams, share(w.picked_right, w.liked_top,
                                                               w.rated_top),
             share(w.found, w.liked_top, w.liked)] for w in found if w.game == game]})
    return {"top": TOP, "games": games}


# --- its addresses in the frame's server (frame_api.py) --------------------------------


def add_routes(app, frame, guarded) -> None:
    settings, worker = frame.settings, frame.worker
    no_cache = {"Cache-Control": "no-store"}
    kept = Lengths()

    def read(fn, *args, **kwargs):
        conn = init_db(settings.db_path)
        try:
            return fn(conn, *args, **kwargs)
        finally:
            conn.close()

    @app.get("/api/clips/recordings")
    def recording_list(deleted: bool = False):
        return JSONResponse({"recordings": read(recordings, settings, deleted=deleted)},
                            headers=no_cache)

    @app.get("/api/clips/knows")
    def how_well():
        return JSONResponse(read(knows), headers=no_cache)

    @app.get("/api/clips/clip/{clip_id}")
    def one(clip_id: str):
        found = read(details, settings, clip_id, kept)
        if found is None:
            raise HTTPException(status_code=404)
        return JSONResponse(found, headers=no_cache)

    @app.post("/api/clips/clip/{clip_id}/rate")
    def rated(clip_id: str, request: Request, rating: int | None = Body(None, embed=True)):
        guarded(request)
        return {"said": rate(settings, clip_id, rating)}

    @app.post("/api/clips/{recording_id}/ai")
    def ai(recording_id: int, request: Request):
        guarded(request)
        return {"said": rate_with_ai(settings, worker, recording_id)}

    @app.get("/api/clips/{recording_id}")
    def clips(recording_id: int, show: str = "unused"):
        if show not in SHOWS:
            raise HTTPException(status_code=404)
        found = read(listing, settings, recording_id, show, kept)
        if not found:
            raise HTTPException(status_code=404)
        return JSONResponse({**found, "version": worker.version}, headers=no_cache)
