"""The local AI's verdict on each clip (spec sections 7.3 and 13, Phase 2).

The signals hear *that* something happened -- shouting, gunfire, chat
going quiet or wild. They can't tell a funny quiet moment from a loud
ordinary one. For each clip the AI reads what was said and what chat wrote,
looks at a few frames, and gives:

- a rating out of 10, for viewers who weren't watching live;
- a one-line summary ("Got third-partied at the zone and raged");
- whether it makes sense without context (what Shorts need);
- a few tags.

How much the rating counts is llm.rating_weight. It starts at 0 -- shown,
not used to pick -- because on the creator's League stream it agreed with
their 👍/👎 no better than chance while the signals did (agreement() keeps
measuring, per game). A 👍 or 👎 always decides on its own.

Verdicts are kept in ai_clip_notes, not on the clip rows, because unrated
clips are cut again every time a video is made. A re-cut clip finds its
verdict by id, or by covering mostly the same stretch of the recording.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from .. import llm
from ..config import Settings
from ..errors import AiTooSlow
from ..ffmpeg import find_binary
from ..games import game_notes
from ..logging_setup import get_logger
from .captions import YOURS, clock

log = get_logger(__name__)

# The question's version, kept with each verdict. 2: with the creator's own
# verdicts as examples (3A-3b); 1 when a game doesn't have enough of them yet.
PROMPT_VERSION = 2
WITH_EXAMPLES = 2
# Verdicts older than this are asked again. Not 2: the creator chose not to
# re-rate old clips with examples (25 Oct), only new ones.
REDO_BEFORE = 1
# Examples shown with each question (3A-3b): this many clips the creator liked,
# and as many they didn't, from other streams of the same game. Fewer of either
# and the question goes without (version 1).
EXAMPLES_EACH = 4
# A re-cut clip keeps a verdict covering at least this share of it.
SAME_MOMENT_OVERLAP = 0.6
# Chat lags the stream by a few seconds; reactions to the end land after it.
CHAT_LAG_SEC = 6.0
MAX_CHAT_LINES = 30
FRAME_HEIGHT = 540
# Once the model is loaded an answer takes 2-3 s on the 4070 Ti. Ten times that
# means something else -- a game -- has the graphics card: stop, don't grind on.
SLOW_ANSWER_SEC = 30.0
# Fewer 👍 or 👎 than this per game and the agreement figure means nothing yet.
ENOUGH_TO_TELL = 8

TAGS = ["funny", "fail", "clutch", "fight", "kill", "death", "rage", "banter", "scary",
        "story", "win", "loss", "chill", "skill", "teamwork"]

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "maxLength": 90},
        "reason": {"type": "string", "maxLength": 160},
        "tags": {"type": "array", "items": {"type": "string", "enum": TAGS}, "maxItems": 3,
                 "uniqueItems": True},
        "stands_alone": {"type": "boolean"},
        "rating": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["summary", "reason", "tags", "stands_alone", "rating"],
}

SYSTEM = """You help a Twitch streamer choose moments for YouTube highlight videos and Shorts.
You get one clip from a stream: the game, what was said (with seconds from the clip's start),
what Twitch chat wrote, which sounds were detected, and a few frames from the video.

Rate the clip for YouTube viewers who were NOT watching live:
- 9-10: a moment people would share. Hilarious, a huge play, a shocking twist.
- 7-8: clearly entertaining. A good laugh, a tense fight with a payoff, a big reaction.
- 4-6: fine but ordinary. Some action or chat, nothing memorable.
- 1-3: nothing happens. Waiting, menus, looting, travel, quiet talk about nothing.

Funny beats loud: banter, a fail, a surprise or a genuine reaction is worth more than
noise alone. Shouting during an ordinary fight is still ordinary.
The transcript can contain teammates and game characters as well as the streamer, and
may have mistakes.

Answer with:
- "summary": what happens, at most 12 words, like a chapter title. Examples:
  "Got third-partied at the zone and raged", "Baron steal by the enemy jungler".
  Never mention the clip, the streamer's markers or the timestamps.
- "reason": why this rating, at most 20 words.
- "tags": up to 3 that fit, no repeats.
- "stands_alone": true only if someone scrolling Shorts would understand and enjoy the
  clip with no context from the rest of the stream.
- "rating": 1-10 as above.

Only describe what the words and frames show. Never invent names, kills or events."""

READABLE = {
    "marker": "the streamer pressed their 'mark this moment' key",
    "marker_short": "the streamer marked this as a Short",
    "laughter": "laughter", "scream": "screaming", "shout": "shouting",
    "explosion": "explosions", "gunfire": "gunfire", "chat_z": "Twitch chat got busy",
    "energy_z": "the streamer got loud", "speech": "talking", "combination": "several things at once",
}


@dataclass
class Note:
    clip_id: str
    recording_id: int
    start_sec: float
    end_sec: float
    rating: float
    summary: str
    reason: str
    tags: list[str]
    stands_alone: bool
    model: str
    prompt_version: int

    @property
    def stars(self) -> str:
        return f"{self.rating:.0f}/10"


def _note(row: sqlite3.Row) -> Note:
    return Note(row["clip_id"], row["recording_id"], row["start_sec"], row["end_sec"],
                row["rating"], row["summary"] or "", row["reason"] or "",
                json.loads(row["tags_json"] or "[]"), bool(row["stands_alone"]), row["model"],
                row["prompt_version"])


def blended(score: float, note: Note | None, weight: float) -> float:
    """The clip's score with the AI's rating as ``weight`` of it.

    Ratings 1-10 become 0-1, like the signal score (1.0 = the recording's
    best moment). A clip the AI hasn't seen keeps its score as it is.
    """
    if note is None or weight <= 0:
        return score
    return round((1 - weight) * score + weight * (note.rating - 1) / 9, 3)


def notes_for(conn: sqlite3.Connection, recording_id: int,
              clips: Sequence[sqlite3.Row]) -> dict[str, Note]:
    """Each clip's verdict, by clip id: its own, or one covering mostly the same moment."""
    notes = [_note(r) for r in conn.execute(
        "SELECT * FROM ai_clip_notes WHERE recording_id = ? ORDER BY start_sec", (recording_id,))]
    by_id = {n.clip_id: n for n in notes}
    found: dict[str, Note] = {}
    for clip in clips:
        own = by_id.get(clip["clip_id"])
        if own is not None:
            found[clip["clip_id"]] = own
            continue
        length = clip["end_sec"] - clip["start_sec"]
        best, best_share = None, 0.0
        for n in notes:
            overlap = min(n.end_sec, clip["end_sec"]) - max(n.start_sec, clip["start_sec"])
            if overlap <= 0:
                continue
            share = overlap / max(1e-6, min(length, n.end_sec - n.start_sec))
            if share > best_share:
                best, best_share = n, share
        if best is not None and best_share >= SAME_MOMENT_OVERLAP:
            found[clip["clip_id"]] = best
    return found


def scores_for(conn: sqlite3.Connection, settings: Settings, recording_id: int,
               clips: Sequence[sqlite3.Row]) -> dict[str, float]:
    """Every clip's score with the AI's say in it, by clip id."""
    notes = notes_for(conn, recording_id, clips)
    weight = settings.llm.rating_weight if settings.llm.enabled else 0.0
    return {c["clip_id"]: blended(c["score"], notes.get(c["clip_id"]), weight) for c in clips}


# --- Asking ------------------------------------------------------------------------


def frame_times(start: float, end: float, peak: float, count: int) -> list[float]:
    """When to take the frames: the build-up, the moment, and just after it."""
    if count <= 0:
        return []
    lo = max(start + 0.5, peak - 8.0)
    hi = min(end - 0.5, peak + 4.0)
    if hi <= lo:
        lo, hi = start + 0.5, max(start + 0.5, end - 0.5)
    if count == 1:
        return [round(min(max(peak, lo), hi), 2)]
    step = (hi - lo) / (count - 1)
    return [round(lo + i * step, 2) for i in range(count)]


def grab_frame(video: Path, t: float) -> bytes | None:
    """One JPEG from the preview copy, or None if it can't be read."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        result = subprocess.run(
            [str(find_binary("ffmpeg")), "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}",
             "-i", str(video), "-frames:v", "1", "-vf", f"scale=-2:{FRAME_HEIGHT}",
             "-q:v", "5", "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1"],
            capture_output=True, timeout=60, creationflags=flags)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout or None


def said(words: Sequence[sqlite3.Row], start: float) -> str:
    """The words, a line per phrase, each with its time from the clip's start."""
    lines, current, line_start, last_end = [], [], None, None
    for w in words:
        if current and (w["start_sec"] - last_end > 1.0 or len(current) >= 25):
            lines.append(f"[{line_start:4.0f}s] {' '.join(current)}")
            current = []
        if not current:
            line_start = w["start_sec"] - start
        current.append(w["word"].strip())
        last_end = w["end_sec"]
    if current:
        lines.append(f"[{line_start:4.0f}s] {' '.join(current)}")
    return "\n".join(lines) or "(nobody talks)"


def chat_lines(conn: sqlite3.Connection, settings: Settings, clip: sqlite3.Row) -> str:
    ignore = {n.lower() for n in settings.twitch.ignore_chatters}
    rows = conn.execute(
        "SELECT t_sec, username, message FROM chat_messages WHERE recording_id = ? "
        "AND t_sec BETWEEN ? AND ? ORDER BY t_sec",
        (clip["recording_id"], clip["start_sec"], clip["end_sec"] + CHAT_LAG_SEC)).fetchall()
    kept = [r for r in rows if (r["username"] or "").lower() not in ignore]
    if not kept:
        return ""
    if len(kept) > MAX_CHAT_LINES:  # keep the spread, not just the start
        step = len(kept) / MAX_CHAT_LINES
        kept = [kept[int(i * step)] for i in range(MAX_CHAT_LINES)]
    return "\n".join(f"[{r['t_sec'] - clip['start_sec']:4.0f}s] {r['username']}: {r['message']}"
                     for r in kept)


def examples(conn: sqlite3.Connection, game: str | None, recording_id: int) -> str | None:
    """The creator's own verdicts, for the AI to rate like them (3A-3b): the clips
    they rated most recently in other streams of this game, with what the AI
    said happens in each. Not their marked clips: those go in anyway.

    Tried on 25 Oct, each League stream rated with examples from the others only:
    the AI put a liked clip above a disliked one 63% of the time, 54% without;
    the same question asked again without them, 54% (69% and 69% on a sample).
    """
    if not game:
        return None
    recent = {r[0]: r[1] for r in conn.execute("SELECT clip_id, MAX(id) FROM feedback "
                                                "GROUP BY clip_id")}
    found = []
    for rec in conn.execute("SELECT id, game FROM recordings WHERE id != ?", (recording_id,)):
        clips = conn.execute("SELECT * FROM clips WHERE recording_id = ? AND user_rating IS NOT "
                             "NULL AND user_rating != 0", (rec["id"],)).fetchall()
        notes = notes_for(conn, rec["id"], clips)
        for c in clips:
            summary = json.loads(c["signals_json"] or "{}")
            if c["clip_id"] not in notes or (summary.get("game") or rec["game"]) != game or \
                    "marker" in summary or "marker_short" in summary:
                continue
            found.append((recent.get(c["clip_id"]) or 0, c["user_rating"] > 0,
                          notes[c["clip_id"]]))
    found.sort(key=lambda f: -f[0])
    liked = [n for _, good, n in found if good][:EXAMPLES_EACH]
    disliked = [n for _, good, n in found if not good][:EXAMPLES_EACH]
    if len(liked) < EXAMPLES_EACH or len(disliked) < EXAMPLES_EACH:
        return None

    def line(note: Note) -> str:
        return f'- "{note.summary}"' + (f" ({', '.join(note.tags)})" if note.tags else "")

    return ("This streamer's own verdicts on earlier clips of this game (from other streams):\n"
            "They liked:\n" + "\n".join(map(line, liked)) +
            "\nThey didn't like:\n" + "\n".join(map(line, disliked)) +
            "\nRate this clip the way they would: higher the more it's like the ones they "
            "liked, lower the more it's like the ones they didn't.")


def question(conn: sqlite3.Connection, settings: Settings, clip: sqlite3.Row,
             game: str | None, shown: str | None = None) -> str:
    """``shown``: the creator's verdicts as examples (``examples``), put first."""
    summary = json.loads(clip["signals_json"] or "{}")
    heard = [READABLE.get(name, name) for name in summary.get("reasons", [])]
    if "marker" in summary or "marker_short" in summary:
        heard.insert(0, READABLE["marker"])
    words = conn.execute(
        "SELECT word, start_sec, end_sec FROM transcript_words WHERE recording_id = ? "
        f"AND {YOURS} AND start_sec >= ? AND end_sec <= ? ORDER BY start_sec",
        (clip["recording_id"], clip["start_sec"], clip["end_sec"])).fetchall()
    notes = game_notes(game)
    parts = [
        f"Game: {game or 'unknown'}" + (f"\n{notes}" if notes else ""),
        f"Clip length: {clip['end_sec'] - clip['start_sec']:.0f} seconds; the main moment is "
        f"about {summary.get('peak', clip['start_sec']) - clip['start_sec']:.0f}s in.",
        f"Detected: {', '.join(dict.fromkeys(heard)) or 'nothing in particular'}",
        f"What was said:\n{said(words, clip['start_sec'])}",
    ]
    chat = chat_lines(conn, settings, clip)
    if chat:
        parts.append(f"Twitch chat:\n{chat}")
    text = "\n\n".join(parts)
    return f"{shown}\n\n---\n\n{text}" if shown else text


def ask_about(conn: sqlite3.Connection, settings: Settings, clip: sqlite3.Row,
              game: str | None, proxy: Path | None, shown: str | None = None) -> Note:
    summary = json.loads(clip["signals_json"] or "{}")
    images = []
    if proxy is not None and proxy.exists():
        for t in frame_times(clip["start_sec"], clip["end_sec"],
                             float(summary.get("peak", clip["start_sec"])),
                             settings.llm.frames_per_clip):
            frame = grab_frame(proxy, t)
            if frame:
                images.append(frame)
    answer = llm.ask(settings, SYSTEM, question(conn, settings, clip, game, shown),
                     schema=SCHEMA, images=images)
    rating = min(10, max(1, int(answer.get("rating") or 1)))
    return Note(clip["clip_id"], clip["recording_id"], clip["start_sec"], clip["end_sec"],
                rating, str(answer.get("summary", "")).strip()[:200],
                str(answer.get("reason", "")).strip()[:400],
                list(dict.fromkeys(t for t in answer.get("tags", []) if t in TAGS))[:3],
                bool(answer.get("stands_alone")), settings.llm.model or "",
                WITH_EXAMPLES if shown else 1)


def save(conn: sqlite3.Connection, note: Note) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO ai_clip_notes (clip_id, recording_id, start_sec, end_sec, rating, "
        "summary, reason, tags_json, stands_alone, model, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (note.clip_id, note.recording_id, note.start_sec, note.end_sec, note.rating, note.summary,
         note.reason, json.dumps(note.tags), int(note.stands_alone), note.model,
         note.prompt_version, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    conn.commit()


def unrated(conn: sqlite3.Connection, settings: Settings, recording_id: int) -> list[sqlite3.Row]:
    """Clips with no verdict yet from this model and this version of the question."""
    clips = conn.execute("SELECT * FROM clips WHERE recording_id = ? ORDER BY score DESC",
                         (recording_id,)).fetchall()
    notes = notes_for(conn, recording_id, clips)
    return [c for c in clips
            if (n := notes.get(c["clip_id"])) is None or n.model != settings.llm.model
            or n.prompt_version < REDO_BEFORE]


@dataclass
class RatingResult:
    rated: int
    already: int
    failed: int


def rate_recording(conn: sqlite3.Connection, settings: Settings, recording_id: int,
                   on_progress: Callable[[float], None] | None = None) -> RatingResult:
    """Ask the AI about every clip it hasn't judged yet. Each answer is saved as
    it comes, so pausing loses at most the clip being asked about."""
    row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    total = conn.execute("SELECT COUNT(*) FROM clips WHERE recording_id = ?",
                         (recording_id,)).fetchone()[0]
    todo = unrated(conn, settings, recording_id)
    if not todo:
        if on_progress:
            on_progress(1.0)
        return RatingResult(0, total, 0)
    proxy = Path(row["proxy_path"]) if row["proxy_path"] else None
    shown: dict[str | None, str | None] = {}   # per game: the creator's examples
    rated = failed = 0
    with llm.session(settings):
        for i, clip in enumerate(todo):
            if on_progress:
                on_progress(i / len(todo))
            game = json.loads(clip["signals_json"] or "{}").get("game") or row["game"]
            asked = time.monotonic()
            if game not in shown:
                shown[game] = examples(conn, game, recording_id)
            try:
                save(conn, ask_about(conn, settings, clip, game, proxy, shown[game]))
                rated += 1
            except llm.AiAnswerUnreadable as exc:
                failed += 1
                log.warning("AI couldn't rate clip %s at %s: %s", clip["clip_id"],
                            clock(clip["start_sec"]), exc)
            # The first answer includes loading the model, so it may take longer.
            if i > 0 and time.monotonic() - asked > SLOW_ANSWER_SEC:
                raise AiTooSlow(f"{rated} clip(s) were rated before it stopped.")
    if on_progress:
        on_progress(1.0)
    return RatingResult(rated, total - len(todo), failed)


@dataclass
class Agreement:
    game: str
    liked: int
    rejected: int
    ai: float | None       # share of (👍, 👎) pairs the AI ranks the right way round
    signals: float | None  # the same for the score from what was heard and seen


def _pairs_right(liked: list[float], rejected: list[float]) -> float | None:
    pairs = [1.0 if a > b else 0.5 if a == b else 0.0 for a in liked for b in rejected]
    return sum(pairs) / len(pairs) if pairs else None


def agreement(conn: sqlite3.Connection) -> list[Agreement]:
    """Per game: how often the AI, and the signals, rank a clip you liked above
    one you rejected. 50% is a coin flip. Clips you marked are left out: they
    go in anyway, so only the unmarked ones are where the AI could matter."""
    by_game: dict[str, list[tuple[int, float, float]]] = {}
    for rec in conn.execute("SELECT id, game FROM recordings"):
        clips = conn.execute("SELECT * FROM clips WHERE recording_id = ? AND user_rating "
                             "IS NOT NULL AND user_rating != 0", (rec["id"],)).fetchall()
        notes = notes_for(conn, rec["id"], clips)
        for c in clips:
            summary = json.loads(c["signals_json"] or "{}")
            note = notes.get(c["clip_id"])
            if note is None or "marker" in summary or "marker_short" in summary:
                continue
            game = summary.get("game") or rec["game"] or "Other"
            by_game.setdefault(game, []).append((c["user_rating"], note.rating, c["score"]))
    found = []
    for game, rows in sorted(by_game.items()):
        liked = [r for r in rows if r[0] > 0]
        rejected = [r for r in rows if r[0] < 0]
        found.append(Agreement(game, len(liked), len(rejected),
                               _pairs_right([r[1] for r in liked], [r[1] for r in rejected]),
                               _pairs_right([r[2] for r in liked], [r[2] for r in rejected])))
    return found


def agreement_text(conn: sqlite3.Connection) -> str:
    """For Settings: one line per game you've rated clips in."""
    lines = []
    for a in agreement(conn):
        if a.ai is None:
            continue
        line = (f"- **{a.game}**: the AI puts a clip you liked above one you rejected "
                f"**{a.ai:.0%}** of the time; the usual score does {a.signals:.0%} "
                f"(from {a.liked} 👍 and {a.rejected} 👎 clips, not counting marked ones; "
                "50% is a coin flip).")
        if min(a.liked, a.rejected) < ENOUGH_TO_TELL:
            # 2 👍 and 1 👎 on Wardogs read "75% against 0%": meaningless, but tempting.
            line += (f" **Too few to tell yet:** rate at least {ENOUGH_TO_TELL} of each "
                     "(unmarked clips the AI has rated).")
        lines.append(line)
    return "\n".join(lines) or ("_Not measured yet: rate some clips 👍/👎 that the AI has "
                                 "rated too._")
