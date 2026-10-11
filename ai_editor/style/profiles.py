"""Style profiles kept in the library, and their sliders (Phase 2G-1).

What the creator chose (2026-10-11): a profile sets the *pace and amounts* --
how fast the cuts are, how much silence is left in, the opening teaser, how
often and how strong zooms and sound effects are, how captions look -- but it
never switches an effect or burned-in captions on. That stays the creator's
own doing, per video or in Settings (they're off by default).

A profile's sliders start from what its reference videos measured (the
median of them); with nothing measured yet, from the creator's own settings.
Saving keeps the sliders as set.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from ..config import Settings
from .measure import Measured

RECIPES = [("Highlights", "highlights"), ("Shorts", "shorts"), ("Let's Plays", "letsplay")]
VIDEO_TYPES = (".mp4", ".mkv", ".mov", ".webm", ".m4v", ".flv", ".ts", ".avi")
# Caption text, as OCR boxes it, is about 1.3 times the font size.
BOX_PER_FONT = 1.3


class ProfileProblem(Exception):
    """Something the creator asked for that can't be done, in plain words."""


@dataclass(frozen=True)
class Slider:
    key: str
    label: str
    minimum: float
    maximum: float
    step: float
    info: str
    # What a reference measured, in the slider's own units (None: couldn't tell).
    measured: Callable[[Measured], float | None]
    # Before anything is measured: from the creator's own settings.
    default: Callable[[Settings], float]


def _pct(x: float | None) -> float | None:
    return None if x is None else x * 100


SLIDERS: list[Slider] = [
    Slider("cuts_per_min", "Cuts per minute", 0, 30, 0.1,
           "How often the picture jumps to another moment. Higher: faster, punchier pacing.",
           lambda m: m.cuts_per_min,
           lambda s: round(60 / ((s.clips.min_length_sec + s.highlights.max_clip_sec) / 2), 1)),
    Slider("dead_air_sec", "Longest silence left in (seconds)", 0.5, 30, 0.5,
           "How long nobody talks before the editor cuts. Lower: tighter, snappier.",
           lambda m: m.dead_air_sec, lambda s: s.lets_play.dead_air_sec),
    Slider("hook_sec", "Opening teaser (seconds)", 0, 30, 1,
           "How long the video's opening shot runs before the first cut. 0: no teaser.",
           lambda m: m.hook_sec if m.hook_sec is not None else 0.0,
           lambda s: round(sum(s.highlights.hook_seconds) / 2)),
    Slider("zooms_per_min", "Zooms per minute", 0, 10, 0.1,
           "How often it punches in. Only used when zooms are switched on.",
           lambda m: m.zooms_per_min, lambda s: s.effects.highlights_per_min),
    Slider("zoom_strength", "Zoom strength", 0.05, 0.5, 0.01,
           "How far a zoom pushes in: 0.2 is 1.2 times. Only used when zooms are switched on.",
           lambda m: m.zoom_strength, lambda s: s.effects.zoom_strength),
    Slider("sfx_per_min", "Sound effects per minute", 0, 10, 0.1,
           "How often a sound effect plays. Only used when sound effects are switched on. "
           "Measured from meme sounds (whoosh, boing, air horn, ding): booms and hits can't "
           "be told from the game's own sounds.",
           lambda m: m.sfx_per_min, lambda s: s.effects.highlights_per_min),
    Slider("caption_size", "Caption size (% of the picture's height)", 2, 15, 0.1,
           "How tall caption text is. Only used when captions are switched on.",
           lambda m: _pct(m.caption_size),
           lambda s: round(s.captions.size * BOX_PER_FONT / 1080 * 100, 1)),
    Slider("caption_position", "Caption height above the bottom (%)", 0, 80, 1,
           "Where captions sit. Only used when captions are switched on.",
           lambda m: _pct(m.caption_position),
           lambda s: round(s.captions.position.highlights * 100)),
    Slider("caption_words", "Caption words on screen at once", 1, 10, 1,
           "A few words at a time, or whole sentences. Only used when captions are switched on.",
           lambda m: m.caption_words, lambda s: float(s.captions.shorts_words)),
]
BY_KEY = {s.key: s for s in SLIDERS}


@dataclass
class Reference:
    id: int
    source: str
    title: str | None
    duration_sec: float | None
    measured: Measured | None
    notes: list[str]
    error: str | None
    analysed_at: str | None

    @property
    def is_link(self) -> bool:
        return is_link(self.source)

    @property
    def name(self) -> str:
        return self.title or (self.source if self.is_link else Path(self.source).name)


@dataclass
class Profile:
    id: int
    name: str
    games: list[str]
    recipes: list[str]
    values: dict[str, float]          # as saved; empty until saved
    notes: list[str]                  # the AI's technique notes, summed up
    references: list[Reference] = field(default_factory=list)

    @property
    def measured(self) -> list[Measured]:
        return [r.measured for r in self.references if r.measured is not None]

    def draft(self, settings: Settings) -> dict[str, float]:
        return draft(self.measured, settings)

    def current(self, settings: Settings) -> dict[str, float]:
        """The sliders as saved, else as measured."""
        return {**self.draft(settings), **{k: v for k, v in self.values.items() if k in BY_KEY}}


def draft(measured: list[Measured], settings: Settings) -> dict[str, float]:
    """Each slider: the middle of what the references measured, else the creator's setting."""
    out = {}
    for s in SLIDERS:
        found = [v for v in (s.measured(m) for m in measured) if v is not None]
        value = float(np.median(found)) if found else float(s.default(settings))
        out[s.key] = snap(s, value)
    return out


def snap(slider: Slider, value: float) -> float:
    value = min(slider.maximum, max(slider.minimum, value))
    return round(round(value / slider.step) * slider.step, 4)


def is_link(text: str) -> bool:
    return text.strip().lower().startswith(("http://", "https://"))


# --- The library ---------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def names(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    return [(r["name"], r["id"]) for r in
            conn.execute("SELECT id, name FROM style_profiles ORDER BY name COLLATE NOCASE")]


def create(conn: sqlite3.Connection, name: str) -> int:
    name = " ".join((name or "").split())
    if not name:
        raise ProfileProblem("Give the profile a name first.")
    if conn.execute("SELECT 1 FROM style_profiles WHERE name = ? COLLATE NOCASE",
                    (name,)).fetchone():
        raise ProfileProblem(f"There's already a profile called \"{name}\".")
    now = _now()
    cur = conn.execute("INSERT INTO style_profiles (name, games_json, applies_to_json, "
                       "profile_json, created_at, updated_at) VALUES (?, '[]', '[]', '{}', ?, ?)",
                       (name, now, now))
    conn.commit()
    return int(cur.lastrowid)


def rename(conn: sqlite3.Connection, profile_id: int, name: str) -> None:
    name = " ".join((name or "").split())
    if not name:
        raise ProfileProblem("Type the new name first.")
    clash = conn.execute("SELECT id FROM style_profiles WHERE name = ? COLLATE NOCASE",
                         (name,)).fetchone()
    if clash and clash["id"] != profile_id:
        raise ProfileProblem(f"There's already a profile called \"{name}\".")
    conn.execute("UPDATE style_profiles SET name = ?, updated_at = ? WHERE id = ?",
                 (name, _now(), profile_id))
    conn.commit()


def delete(conn: sqlite3.Connection, profile_id: int) -> None:
    """The profile and its list of references (only the measurements: no video is touched)."""
    conn.execute("DELETE FROM style_profiles WHERE id = ?", (profile_id,))
    conn.commit()


def load(conn: sqlite3.Connection, profile_id: int | None) -> Profile | None:
    if profile_id is None:
        return None
    row = conn.execute("SELECT * FROM style_profiles WHERE id = ?", (profile_id,)).fetchone()
    if row is None:
        return None
    refs = [Reference(r["id"], r["source"], r["title"], r["duration_sec"],
                      Measured.from_dict(json.loads(r["measured_json"])) if r["measured_json"]
                      else None,
                      json.loads(r["notes_json"]) if r["notes_json"] else [],
                      r["error"], r["analysed_at"])
            for r in conn.execute("SELECT * FROM style_references WHERE profile_id = ? ORDER BY id",
                                  (profile_id,))]
    return Profile(row["id"], row["name"], json.loads(row["games_json"] or "[]"),
                   json.loads(row["applies_to_json"] or "[]"),
                   json.loads(row["profile_json"] or "{}"), json.loads(row["notes_json"]), refs)


def save(conn: sqlite3.Connection, profile_id: int, *, games: list[str], recipes: list[str],
         values: dict[str, float]) -> None:
    clean = {k: snap(BY_KEY[k], float(v)) for k, v in values.items() if k in BY_KEY and v is not None}
    conn.execute("UPDATE style_profiles SET games_json = ?, applies_to_json = ?, "
                 "profile_json = ?, updated_at = ? WHERE id = ?",
                 (json.dumps(list(games)), json.dumps(list(recipes)), json.dumps(clean), _now(),
                  profile_id))
    conn.commit()


def add_reference(conn: sqlite3.Connection, profile_id: int, source: str) -> str:
    """A YouTube link or a video file on this PC. Returns what was added, in plain words."""
    source = source.strip().strip('"')
    if not source:
        raise ProfileProblem("Paste a link or pick a video file first.")
    if is_link(source):
        shown = source
    else:
        path = Path(source)
        if not path.is_file():
            raise ProfileProblem(f"Can't find the file {source}.")
        if path.suffix.lower() not in VIDEO_TYPES:
            raise ProfileProblem(f"{path.name} doesn't look like a video.")
        source, shown = str(path.resolve()), path.name
    try:
        conn.execute("INSERT INTO style_references (profile_id, source) VALUES (?, ?)",
                     (profile_id, source))
    except sqlite3.IntegrityError:
        raise ProfileProblem(f"{shown} is already one of this profile's references.") from None
    conn.commit()
    return shown


def remove_reference(conn: sqlite3.Connection, reference_id: int) -> None:
    """Off the list, with what it measured. A file on this PC is never touched."""
    conn.execute("DELETE FROM style_references WHERE id = ?", (reference_id,))
    conn.commit()


def store_measured(conn: sqlite3.Connection, reference_id: int, *, title: str | None,
                   measured: Measured, notes: list[str] | None = None) -> None:
    conn.execute("UPDATE style_references SET title = COALESCE(?, title), duration_sec = ?, "
                 "measured_json = ?, notes_json = COALESCE(?, notes_json), error = NULL, "
                 "analysed_at = ? WHERE id = ?",
                 (title, measured.duration_sec, json.dumps(measured.to_dict()),
                  json.dumps(notes) if notes is not None else None, _now(), reference_id))
    conn.commit()


def store_notes(conn: sqlite3.Connection, reference_id: int, notes: list[str]) -> None:
    conn.execute("UPDATE style_references SET notes_json = ? WHERE id = ?",
                 (json.dumps(notes), reference_id))
    conn.commit()


def store_error(conn: sqlite3.Connection, reference_id: int, error: str) -> None:
    conn.execute("UPDATE style_references SET error = ? WHERE id = ?", (error, reference_id))
    conn.commit()


def store_profile_notes(conn: sqlite3.Connection, profile_id: int, notes: list[str]) -> None:
    conn.execute("UPDATE style_profiles SET notes_json = ?, updated_at = ? WHERE id = ?",
                 (json.dumps(notes), _now(), profile_id))
    conn.commit()
