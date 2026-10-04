"""Getting a finished video ready to upload (spec section 7.6, "Extra outputs").

For each video -- a highlight video, or one part of a Let's Play -- the
local AI writes 3-5 title ideas, a description, tags and a name for each
chapter, and picks thumbnail frames. Nothing is uploaded: the creator copies
the text into YouTube (spec section 1, non-goals).

**Chapters** come from the plan, so their times match the finished video to
the frame: a highlight video gets one per clip (YouTube needs each to last 10
seconds, so a short teaser joins the clip after it); a Let's Play part gets
one about every five minutes, at a join between kept pieces. The AI only
names them, from what it said about each clip (analysis/ai_rating.py) and
what was said.

**Titles** are plain and descriptive, the creator's choice (2026-10-04):
"Wardogs Highlights – Holding the Zone with Friends". Let's Play titles keep
the series pattern (publish.lets_play_title); the AI writes only the part
after the colon.

**Thumbnails**: up to 12 full-size frames from the strongest moments, each
shown to the AI, best 6 kept as PNGs to finish in a free editor (spec 7.6).

Everything is kept with the plan and in a .txt file beside the video.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from . import llm
from .analysis.ai_rating import SLOW_ANSWER_SEC, notes_for
from .analysis.moments import load_signal
from .config import Settings
from .errors import AiTooSlow
from .ffmpeg import find_binary
from .logging_setup import get_logger
from .recipes.plan import EditPlan, Segment

log = get_logger(__name__)

FOLDER = "thumbnails"
MIN_CHAPTER_SEC = 10.0         # YouTube ignores chapters shorter than this
MIN_CHAPTERS = 3               # ...and chapter lists with fewer than three
WORDS_PER_SECTION = 120        # what was said, per chapter, for the AI to read
THUMB_CANDIDATES = 12
THUMB_SPACING_SEC = 20.0       # candidate frames at least this far apart
PROMPT_VERSION = 1


@dataclass
class Section:
    """One chapter: where it starts and ends in the finished video, and what's in it."""

    start: float
    end: float
    pieces: list[Segment]
    about: str = ""
    # Named without the AI: the teaser is "Intro" (it previews the ending, so
    # there's nothing of its own to name it from).
    name: str | None = None

    @property
    def length(self) -> float:
        return self.end - self.start


def fingerprint(plan: EditPlan) -> str:
    """Changes whenever what's in the video changes, so stale chapters are spotted."""
    pieces = [(s.recording_id, round(s.src_in, 2), round(s.src_out, 2)) for s in plan.segments]
    return hashlib.sha1(json.dumps(pieces).encode()).hexdigest()[:12]


def key_of(part: int | None) -> str:
    return f"part {part}" if part else "video"


def placed(plan: EditPlan, fps: int) -> list[tuple[float, Segment]]:
    """Each piece with where it starts in the finished video. Lengths are whole
    frames, exactly as the renderer cuts them (render.final.frame_exact)."""
    from .render.final import frame_exact

    out, t = [], 0.0
    for segment in plan.segments:
        out.append((t, segment))
        t += frame_exact(segment.length, fps)
    return out


def sections(plan: EditPlan, fps: int, every_sec: float) -> list[Section]:
    """Where the chapters go: per clip for highlights, about every ``every_sec`` otherwise."""
    from .render.final import frame_exact

    found: list[Section] = []
    if plan.recipe != "letsplay":
        for start, segment in placed(plan, fps):
            found.append(Section(start, start + frame_exact(segment.length, fps), [segment]))
    else:
        current: Section | None = None
        for start, segment in placed(plan, fps):
            end = start + frame_exact(segment.length, fps)
            if current is None or current.length >= every_sec:
                current = Section(start, end, [segment])
                found.append(current)
            else:
                current.end = end
                current.pieces.append(segment)
    # Too short to be a chapter: joins the next one (the teaser joins the
    # first clip), or the one before if it's last.
    merged: list[Section] = []
    pending: Section | None = None
    for section in found:
        if pending is not None:
            section = Section(pending.start, section.end, pending.pieces + section.pieces)
            pending = None
        if section.length < MIN_CHAPTER_SEC:
            pending = section
            continue
        if [p.kind for p in section.pieces] == ["teaser"]:
            section.name = "Intro"
        merged.append(section)
    if pending is not None:
        if merged:
            last = merged[-1]
            merged[-1] = Section(last.start, pending.end, last.pieces + pending.pieces)
        else:
            merged.append(pending)
    return merged


def describe_sections(conn: sqlite3.Connection, found: list[Section]) -> None:
    """What happens in each chapter, in words the AI can name it from."""
    for section in found:
        lines = []
        for piece in section.pieces:
            if piece.kind == "teaser":
                continue  # a preview of the ending: it isn't what this chapter is about
            clips = conn.execute(
                "SELECT * FROM clips WHERE recording_id = ? AND end_sec > ? AND start_sec < ?",
                (piece.recording_id, piece.src_in, piece.src_out)).fetchall()
            for note in notes_for(conn, piece.recording_id, clips).values():
                if note.summary and note.summary not in lines:
                    lines.append(note.summary)
        # Words from every piece, not just the first: a five-minute Let's Play
        # chapter is many pieces, and its first minute isn't the whole story.
        pieces = [p for p in section.pieces if p.kind != "teaser"] or section.pieces
        each = max(10, WORDS_PER_SECTION // len(pieces))
        words = []
        for piece in pieces:
            words += conn.execute(
                "SELECT word FROM transcript_words WHERE recording_id = ? AND start_sec >= ? AND "
                "end_sec <= ? ORDER BY start_sec LIMIT ?",
                (piece.recording_id, piece.src_in, piece.src_out, each)).fetchall()
        said = " ".join(w["word"].strip() for w in words[:WORDS_PER_SECTION])
        section.about = ("; ".join(lines[:4]) or "-") + (f' | Said: "{said}"' if said else "")


def clock(seconds: float) -> str:
    """YouTube's chapter format: 0:00, 4:05, 1:02:03."""
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


# --- The AI's text -----------------------------------------------------------------


SYSTEM = """You write the YouTube upload text for a gaming creator's videos, made from their
Twitch streams and Let's Play recordings.

Style, the creator's own choice: plain and descriptive. Say what the video is. No clickbait,
no ALL CAPS words, no emoji, no "you won't believe". Example titles:
"Wardogs Highlights - Holding the Zone with Friends", "Tarkov Highlights - Close Calls on Customs".

Only use what the chapter notes say happened. Never invent kills, names, wins or events.
The notes come from speech recognition and an AI looking at clips, so they can be rough:
write around anything unclear rather than repeating it.

The description: 2-4 sentences in the creator's own voice ("I", "we"), about what happens in
this video. Don't list the chapters (they're added below it), and no links or hashtags.
Tags: 8-15 short search terms, the game's name first.
Chapter names: 2-6 words each, one per chapter, in order, saying what happens in it."""


def _schema(chapters: int, lets_play: bool) -> dict:
    title = {"type": "string", "maxLength": 90}
    return {
        "type": "object",
        "properties": {
            "titles": {"type": "array", "items": title, "minItems": 3, "maxItems": 5},
            "description": {"type": "string", "maxLength": 700},
            "tags": {"type": "array", "items": {"type": "string", "maxLength": 30},
                     "minItems": 5, "maxItems": 15},
            "chapters": {"type": "array", "items": {"type": "string", "maxLength": 50},
                         "minItems": chapters, "maxItems": chapters},
        },
        "required": ["titles", "description", "tags", "chapters"],
    }


def question(plan: EditPlan, found: list[Section], *, part: int | None,
             episode: int | None, spoiler_games: list[str] = ()) -> str:
    total = found[-1].end if found else 0.0
    if plan.recipe == "letsplay":
        what = (f"A Let's Play of {plan.game or 'a game'}: episode {episode or '?'}, part "
                f"{part or 1}. The titles are only the part after the colon in "
                f'"{plan.game} - EP {episode or "?"} Part {part or 1}: ...", so 2-7 words '
                "about what happens in this part.")
    else:
        games = sorted({s.game for s in plan.segments if s.game} | ({plan.game} if plan.game
                                                                    else set()))
        what = (f"A highlight video of the best moments from Twitch streams of "
                f"{', '.join(games) or 'several games'}.")
    if plan.game in spoiler_games:
        what += (" It's a story game: the titles must not give away twists, deaths, who the "
                 "villain is or how the story ends. Tease instead.")
    lines = [what, f"Length: {clock(total)}.", "", "Chapters, in order:"]
    for n, section in enumerate([s for s in found if s.name is None], 1):
        lines.append(f"{n}. [{clock(section.start)}] {section.about}")
    return "\n".join(lines)


@dataclass
class Thumbnail:
    path: Path
    rating: int
    reason: str


@dataclass
class Publish:
    titles: list[str]
    description: str
    tags: list[str]
    chapters: list[tuple[float, str]]
    thumbnails: list[Thumbnail]
    fingerprint: str
    made_at: str
    # What the creator changed in Review: "title", "description" (as pasted,
    # chapters included) and "tags". Kept over the AI's.
    edited: dict | None = None

    @property
    def title(self) -> str | None:
        return (self.edited or {}).get("title") or None

    def as_dict(self) -> dict:
        return {"titles": self.titles, "description": self.description, "tags": self.tags,
                "chapters": [list(c) for c in self.chapters],
                "thumbnails": [{"path": str(t.path), "rating": t.rating, "reason": t.reason}
                               for t in self.thumbnails],
                "fingerprint": self.fingerprint, "made_at": self.made_at,
                "prompt_version": PROMPT_VERSION, "edited": self.edited}

    @classmethod
    def from_dict(cls, data: dict) -> "Publish":
        return cls(list(data.get("titles", [])), data.get("description", ""),
                   list(data.get("tags", [])),
                   [(float(t), str(name)) for t, name in data.get("chapters", [])],
                   [Thumbnail(Path(t["path"]), int(t.get("rating", 0)), t.get("reason", ""))
                    for t in data.get("thumbnails", [])],
                   data.get("fingerprint", ""), data.get("made_at", ""), data.get("edited"))


def full_titles(settings: Settings, plan: EditPlan, ideas: list[str], *, part: int | None,
                episode: int | None) -> list[str]:
    """Let's Play ideas are the part after the colon; the series pattern goes in front."""
    if plan.recipe != "letsplay":
        return [i.strip() for i in ideas if i.strip()]
    pattern = settings.publish.lets_play_title
    titles = []
    for idea in ideas:
        # Asked for only the part after the colon, the AI still sometimes writes
        # the whole title ("The Blood of Dawnwalker - EP 1 Part 1: ..."): keep its end.
        while ":" in idea and any(w in idea.split(":")[0] for w in
                                  ("EP", "Part", "Episode", plan.game or "\0")):
            idea = idea.split(":", 1)[1]
        idea = idea.strip().rstrip(".")
        if idea:
            titles.append(pattern.format(game=plan.game or "Let's Play", episode=episode or "?",
                                         part=part or 1, subtitle=idea))
    return list(dict.fromkeys(titles))


def description_text(settings: Settings, publish: Publish) -> str:
    """Ready to paste into YouTube: the description, the chapters, your footer."""
    if (publish.edited or {}).get("description"):
        return publish.edited["description"]
    parts = [publish.description.strip()]
    if len(publish.chapters) >= MIN_CHAPTERS:
        parts.append("\n".join(f"{clock(t)} {name}" for t, name in publish.chapters))
    if settings.publish.description_footer.strip():
        parts.append(settings.publish.description_footer.strip())
    return "\n\n".join(p for p in parts if p)


def tags_of(publish: Publish) -> list[str]:
    return list((publish.edited or {}).get("tags") or publish.tags)


def text_file(settings: Settings, publish: Publish, title: str | None = None) -> str:
    title = title or publish.title
    lines = (["TITLE", f"  {title}"] if title
             else ["TITLE (pick one)"] + [f"  {t}" for t in publish.titles])
    lines += ["", "DESCRIPTION", description_text(settings, publish), "",
              "TAGS", ", ".join(tags_of(publish))]
    if publish.thumbnails:
        lines += ["", "THUMBNAIL FRAMES (best first)"] + [f"  {t.path}" for t in publish.thumbnails]
    return "\n".join(lines) + "\n"


def write_text_beside(settings: Settings, publish: Publish, video: Path,
                      title: str | None = None) -> Path:
    path = video.with_suffix(".txt")
    path.write_text(text_file(settings, publish, title), encoding="utf-8")
    return path


# --- Thumbnails ------------------------------------------------------------------------


THUMB_SCHEMA = {
    "type": "object",
    "properties": {
        "problem": {"type": "string",
                    "enum": ["none", "blurry", "menu", "loading", "dark", "nothing happening"]},
        "reason": {"type": "string", "maxLength": 100},
        "rating": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["problem", "reason", "rating"],
}

THUMB_SYSTEM = """You judge frames from a gaming video as YouTube thumbnail backgrounds.
The creator adds text and their face later in an editor. A good frame is sharp, has a clear
subject and action (a fight, an explosion, a boss, a dramatic view), and reads well when small.
Bad frames: blurry from motion, menus, loading screens, maps, very dark, nothing happening.
Answer with any problem, a reason in under 15 words, and a rating 1-10."""


def thumbnail_moments(conn: sqlite3.Connection, plan: EditPlan,
                      count: int = THUMB_CANDIDATES) -> list[tuple[int, float]]:
    """(recording, second) at the video's strongest moments, spread out."""
    scored: list[tuple[float, int, float]] = []
    hype: dict[int, np.ndarray] = {}
    for segment in plan.segments:
        if segment.kind == "teaser":
            continue  # the same moment is in the video again later
        if segment.recording_id not in hype:
            hype[segment.recording_id] = load_signal(conn, segment.recording_id, "hype")
        values = hype[segment.recording_id]
        lo, hi = int(segment.src_in) + 1, int(segment.src_out) - 1
        if hi <= lo:
            continue
        window = values[lo:hi] if values.size >= hi else np.zeros(hi - lo)
        # Every second in the piece is a candidate; spacing picks the peaks.
        for offset in np.argsort(window)[::-1][:20]:
            scored.append((float(window[offset]), segment.recording_id, float(lo + offset) + 0.5))
    chosen: list[tuple[int, float]] = []
    for _, recording_id, t in sorted(scored, reverse=True):
        if all(r != recording_id or abs(t - c) >= THUMB_SPACING_SEC for r, c in chosen):
            chosen.append((recording_id, t))
        if len(chosen) >= count:
            break
    return chosen


def grab(video: Path, t: float, target: Path, height: int | None = None) -> bool:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    scale = ["-vf", f"scale=-2:{height}"] if height else []
    try:
        subprocess.run([str(find_binary("ffmpeg")), "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", *scale,
                        str(target)], capture_output=True, timeout=120, creationflags=flags)
    except (OSError, subprocess.SubprocessError):
        return False
    return target.is_file() and target.stat().st_size > 0


def thumbnails(conn: sqlite3.Connection, settings: Settings, plan: EditPlan, folder: Path,
               on_progress: Callable[[float], None] | None = None) -> list[Thumbnail]:
    """Full-size frames at the strongest moments, the AI's favourites first."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.png"):
        old.unlink()
    sources = {}
    for row in conn.execute(f"SELECT id, source_file, proxy_path FROM recordings WHERE id IN "
                            f"({','.join('?' * len(plan.recording_ids))})", plan.recording_ids):
        raw = Path(row["source_file"])
        sources[row["id"]] = raw if raw.is_file() else Path(row["proxy_path"] or "")
    moments = thumbnail_moments(conn, plan)
    found: list[Thumbnail] = []
    for i, (recording_id, t) in enumerate(moments):
        if on_progress:
            on_progress(i / max(1, len(moments)))
        video = sources.get(recording_id)
        if video is None or not video.is_file():
            continue
        full = folder / f"candidate {i + 1:02d}.png"
        small = folder / f"candidate {i + 1:02d}.jpg"
        if not grab(video, t, full):
            continue
        rating, reason = 5, ""
        if grab(video, t, small, height=540):
            asked = time.monotonic()
            try:
                answer = llm.ask(settings, THUMB_SYSTEM, "Rate this frame as a thumbnail.",
                                 schema=THUMB_SCHEMA, images=[small.read_bytes()])
                rating = int(answer.get("rating") or 1)
                if answer.get("problem", "none") != "none":
                    rating = min(rating, 3)
                reason = str(answer.get("reason", ""))[:120]
            except llm.AiAnswerUnreadable as exc:
                log.warning("AI couldn't judge thumbnail frame %s: %s", full.name, exc)
            finally:
                small.unlink(missing_ok=True)
            if i > 0 and time.monotonic() - asked > SLOW_ANSWER_SEC:
                raise AiTooSlow("The thumbnail frames found so far were kept.")
        found.append(Thumbnail(full, rating, reason))
    found.sort(key=lambda th: -th.rating)
    kept, dropped = found[:settings.publish.thumbnails], found[settings.publish.thumbnails:]
    for thumb in dropped:
        thumb.path.unlink(missing_ok=True)
    final = []
    for n, thumb in enumerate(kept, 1):
        target = folder / f"thumbnail {n}.png"
        thumb.path.replace(target)
        final.append(Thumbnail(target, thumb.rating, thumb.reason))
    if on_progress:
        on_progress(1.0)
    return final


# --- All of it --------------------------------------------------------------------------


def thumbnail_folder(settings: Settings, plan: EditPlan, part: int | None) -> Path:
    name = plan.plan_id + (f" part {part}" if part else "")
    return settings.folders.output / FOLDER / name


def prepare(conn: sqlite3.Connection, settings: Settings, plan: EditPlan, *,
            part: int | None = None, episode: int | None = None,
            on_progress: Callable[[str, float], None] | None = None) -> Publish:
    """Titles, description, tags, chapters and thumbnails for one video."""
    from .render import parts as lp

    video = lp.part_plan(plan, part) if part else plan
    fps = settings.render.presets[settings.render.preset].fps
    found = sections(video, fps, settings.publish.chapter_every_min * 60)
    describe_sections(conn, found)
    lets_play = plan.recipe == "letsplay"

    def step(label: str) -> Callable[[float], None]:
        return lambda f: on_progress(label, f) if on_progress else None

    with llm.session(settings):
        step("Writing titles, description and chapters")(0.0)
        to_name = [s for s in found if s.name is None]
        answer = llm.ask(settings, SYSTEM, question(video, found, part=part, episode=episode,
                                  spoiler_games=settings.shorts.spoiler_check_games),
                         schema=_schema(len(to_name), lets_play))
        step("Writing titles, description and chapters")(1.0)
        names = iter(chapter_name(n) for n in answer.get("chapters", []))
        chapters = []
        for n, section in enumerate(found):
            name = section.name or next(names, "") or f"Part {n + 1}"
            chapters.append((0.0 if n == 0 else section.start, name))
        thumbs = thumbnails(conn, settings, video, thumbnail_folder(settings, plan, part),
                            step("Picking thumbnail frames"))
    tags = list(dict.fromkeys(str(t).strip() for t in answer.get("tags", []) if str(t).strip()))
    if plan.game and plan.game not in tags:
        tags.insert(0, plan.game)
    return Publish(full_titles(settings, plan, list(answer.get("titles", [])), part=part,
                               episode=episode),
                   str(answer.get("description", "")).strip(), tags[:15], chapters, thumbs,
                   fingerprint(video),
                   datetime.now(timezone.utc).isoformat(timespec="seconds"))


def chapter_name(text: object) -> str:
    """The AI sometimes writes the time in too ("0:00 - Intro"): YouTube adds its own."""
    import re

    return re.sub(r"^\s*\d{1,2}(:\d{2}){1,2}\s*[-–:.]?\s*", "", str(text)).strip()


def saved(plan: EditPlan, part: int | None) -> Publish | None:
    data = plan.publish.get(key_of(part))
    return Publish.from_dict(data) if data else None


def is_stale(plan: EditPlan, part: int | None, publish: Publish) -> bool:
    """The plan changed since the text was written: the chapters may be off."""
    from .render import parts as lp

    video = lp.part_plan(plan, part) if part else plan
    return publish.fingerprint != fingerprint(video)
