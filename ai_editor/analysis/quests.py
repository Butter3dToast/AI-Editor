"""Reading Dawnwalker's quest tracker, for story missions (Phase 2F-1).

The Blood of Dawnwalker shows a tracker in the top-right corner while you
play: the time of day ("Noon"), the main story ("The Blood of Dawnwalker",
"Rescue your family • 12 days left"), then the quest being followed ("Where
Loyalty Lies") and its current step. Reading it every few seconds tells
AI-Editor which quest is going on and when it changes, so a part isn't split
in the middle of one (the creator's choice, 2026-10-11: every tracked quest
counts, the "Rescue your family" line doesn't).

It's read from the preview copy (960x540, still sharp enough), so it works
for episodes whose recording was deleted, with RapidOCR: a small offline text
reader, on the processor only (the creator may be gaming). The tracker sits
over the moving game, so single reads are noisy ("Aftemoon", a title split in
two); each line is found by where it sits, names are matched allowing for
misspellings, and a change only counts once it's seen twice.
"""

from __future__ import annotations

import difflib
import re
import sqlite3
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from ..logging_setup import get_logger

log = get_logger(__name__)

GAME = "The Blood of Dawnwalker"
# One look every this many seconds: quests last minutes (4-22 on the
# creator's 10 Oct episode), and a part only ends at a safe break anyway.
EVERY_SEC = 15.0
# The tracker's top rows (time of day down to the quest's name), as a share of
# the picture: x from, y from, x to, y to. About half a second a look on the
# processor: 4-5 minutes for a 2-hour episode.
REGION = (0.74, 0.0, 1.0, 0.21)
TIMES = ("Dawn", "Morning", "Noon", "Afternoon", "Evening", "Dusk", "Night", "Midnight")
# Two spellings of a quest this alike are the same quest, misread.
SAME_NAME = 0.8
READER = "rapidocr-3.10"


@dataclass(frozen=True)
class Sighting:
    t: float
    time_of_day: str | None
    quest: str | None
    step: str | None


@dataclass(frozen=True)
class Mission:
    name: str
    start: float        # recording time it was first seen
    end: float          # ...and last seen

    def holds(self, t: float, margin: float = 0.0) -> bool:
        return self.start + margin < t < self.end - margin


# --- Reading one look at the tracker ----------------------------------------------------


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" •·-|")


def _like(a: str, b: str) -> float:
    return difflib.SequenceMatcher(a=a.lower(), b=b.lower()).ratio()


def rows_of(boxes: Sequence, texts: Sequence[str]) -> list[str]:
    """Text pieces grouped into the tracker's rows, top to bottom (a row read
    in two pieces, "Where" and "Loyalty Lies", becomes one again)."""
    pieces = []
    for box, text in zip(boxes, texts):
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        pieces.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), text))
    pieces.sort()
    rows: list[list] = []
    for y, h, x, text in pieces:
        if rows and abs(y - rows[-1][0][0]) <= max(4.0, 0.5 * h):
            rows[-1].append((y, h, x, text))
        else:
            rows.append([(y, h, x, text)])
    return [_clean(" ".join(p[3] for p in sorted(row, key=lambda p: p[2]))) for row in rows]


def parse(rows: list[str], t: float) -> Sighting:
    """Which rows are the time of day, the quest and its step."""
    story = next((i for i, r in enumerate(rows)
                  if _like(r, GAME) >= 0.6 or "dawnw" in r.lower() or "blood of" in r.lower()),
                 None)
    family = next((i for i, r in enumerate(rows) if "days left" in r.lower()
                   or "rescue" in r.lower()), None)
    time_of_day = None
    for r in rows[:story if story is not None else 2]:
        found = difflib.get_close_matches(r.split(" ")[0].title(), TIMES, n=1, cutoff=0.6)
        if found:
            time_of_day = found[0]
            break
    after = family if family is not None else (story + 1 if story is not None else None)
    quest = step = None
    if after is not None and after + 1 < len(rows):
        quest = rows[after + 1] or None
        step = rows[after + 2] if after + 2 < len(rows) else None
    if quest is not None and (len(quest) < 4 or "days left" in quest.lower()):
        quest = None
    return Sighting(t, time_of_day, quest, step)


# --- Reading a whole episode --------------------------------------------------------------


def _reader():
    from rapidocr import RapidOCR

    # On the processor only (the creator may be playing), on a few of its cores.
    return RapidOCR(params={"Global.log_level": "error",
                            "EngineConfig.onnxruntime.intra_op_num_threads": 4})


def read_tracker(ffmpeg: str, video: Path, duration: float, *, size: tuple[int, int],
                 every: float = EVERY_SEC,
                 on_progress: Callable[[float], None] | None = None) -> list[Sighting]:
    """Look at the tracker every ``every`` seconds of ``video`` (a preview copy)."""
    from ..ffmpeg import _BACKGROUND

    w, h = size
    x0, y0 = int(w * REGION[0]), int(h * REGION[1])
    cw, ch = int(w * REGION[2]) - x0, int(h * REGION[3]) - y0
    cw, ch = cw - cw % 2, ch - ch % 2
    proc = subprocess.Popen(
        [ffmpeg, "-v", "error", "-i", str(video), "-vf",
         f"fps=1/{every:g},crop={cw}:{ch}:{x0}:{y0}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, creationflags=_BACKGROUND)
    engine = _reader()
    found: list[Sighting] = []
    frame_bytes = cw * ch * 3
    n = 0
    try:
        while True:
            raw = proc.stdout.read(frame_bytes)
            if len(raw) < frame_bytes:
                break
            t = n * every
            result = engine(np.frombuffer(raw, np.uint8).reshape(ch, cw, 3))
            if result.txts:
                found.append(parse(rows_of(result.boxes, result.txts), t))
            else:
                found.append(Sighting(t, None, None, None))
            n += 1
            if on_progress and duration > 0:
                on_progress(min(1.0, t / duration))
    finally:
        proc.stdout.close()
        proc.wait()
    return found


# --- Kept in the library --------------------------------------------------------------


def store(conn: sqlite3.Connection, recording_id: int, sightings: list[Sighting],
          every: float = EVERY_SEC) -> None:
    conn.execute("DELETE FROM quest_log WHERE recording_id = ?", (recording_id,))
    conn.executemany(
        "INSERT INTO quest_log (recording_id, t_sec, time_of_day, quest, step) "
        "VALUES (?, ?, ?, ?, ?)",
        [(recording_id, s.t, s.time_of_day, s.quest, s.step) for s in sightings
         if s.time_of_day or s.quest])
    conn.execute("INSERT INTO quest_reads (recording_id, every_sec, reader, read_at) VALUES "
                 "(?, ?, ?, ?) ON CONFLICT(recording_id) DO UPDATE SET every_sec = excluded."
                 "every_sec, reader = excluded.reader, read_at = excluded.read_at",
                 (recording_id, every, READER,
                  datetime.now(timezone.utc).isoformat(timespec="seconds")))
    conn.commit()


def is_read(conn: sqlite3.Connection, recording_id: int) -> bool:
    return conn.execute("SELECT 1 FROM quest_reads WHERE recording_id = ?",
                        (recording_id,)).fetchone() is not None


def load(conn: sqlite3.Connection, recording_id: int) -> list[Sighting]:
    return [Sighting(r["t_sec"], r["time_of_day"], r["quest"], r["step"]) for r in conn.execute(
        "SELECT t_sec, time_of_day, quest, step FROM quest_log WHERE recording_id = ? "
        "ORDER BY t_sec", (recording_id,))]


# --- What the readings mean ---------------------------------------------------------------


def _names(sightings: list[Sighting]) -> dict[str, str]:
    """Each spelling read -> the quest's name (its most common spelling)."""
    counts = Counter(s.quest for s in sightings if s.quest)
    groups: list[list[str]] = []
    for name, _ in counts.most_common():
        for group in groups:
            if _like(name, group[0]) >= SAME_NAME:
                group.append(name)
                break
        else:
            groups.append([name])
    return {name: group[0] for group in groups for name in group}


def missions(sightings: list[Sighting], every: float = EVERY_SEC) -> list[Mission]:
    """Each quest followed, from when it was first seen to when it was last seen
    before another took over. A name seen only once is a misreading."""
    name_of = _names(sightings)
    seen = [(s.t, name_of[s.quest]) for s in sightings if s.quest]
    counts = Counter(name for _, name in seen)
    seen = [(t, name) for t, name in seen if counts[name] >= 2]
    runs: list[list] = []
    for t, name in seen:
        if runs and runs[-1][0] == name:
            runs[-1][2] = t
        else:
            runs.append([name, t, t, 0])
        runs[-1][3] += 1
    # A lone look at another quest in the middle of one is a misreading too.
    steady = [r for i, r in enumerate(runs)
              if r[3] >= 2 or not (0 < i < len(runs) - 1 and runs[i - 1][0] == runs[i + 1][0])]
    merged: list[list] = []
    for r in steady:
        if merged and merged[-1][0] == r[0]:
            merged[-1][2] = r[2]
        else:
            merged.append(list(r))
    return [Mission(name, start, end + every) for name, start, end, _ in merged]


def day_changes(sightings: list[Sighting]) -> list[float]:
    """When the time of day changed (Noon -> Afternoon), once the new one is seen twice."""
    seen = [(s.t, s.time_of_day) for s in sightings if s.time_of_day]
    changes, current = [], None
    for i, (t, tod) in enumerate(seen):
        if tod == current:
            continue
        if i + 1 < len(seen) and seen[i + 1][1] == tod:
            if current is not None:
                changes.append(t)
            current = tod
    return changes


# --- For the Let's Play recipe ----------------------------------------------------------


@dataclass
class Story:
    """What the tracker says about one episode."""
    missions: list[Mission]
    day_changes: list[float]

    def inside(self, t: float, margin: float = 20.0) -> Mission | None:
        """The quest going on at ``t`` (away from its first and last few seconds)."""
        return next((m for m in self.missions if m.holds(t, margin)), None)

    def quest_ended(self, t: float, margin: float = 20.0, after: float = 180.0) -> bool:
        """``t`` is just after a quest's last look (within ``after`` seconds),
        before the next one is seen."""
        if self.inside(t, 0.0) is not None:
            return False
        return any(m.end - margin <= t <= m.end + after for m in self.missions)

    def day_turned(self, t: float, within: float = 45.0) -> bool:
        return any(abs(t - c) <= within for c in self.day_changes)


def plays(game: str | None) -> bool:
    return (game or "").strip().lower() == GAME.lower()


def ensure_read(conn: sqlite3.Connection, row: sqlite3.Row,
                on_progress: Callable[[float], None] | None = None) -> bool:
    """Read an episode's tracker once (a few minutes); True when there's a reading."""
    from ..ffmpeg import find_binary, probe

    if not plays(row["game"]):
        return False
    if is_read(conn, row["id"]):
        return True
    try:
        import rapidocr  # noqa: F401
    except ImportError:
        log.warning("The quest tracker can't be read: the text reader isn't installed "
                    "(pip install --no-deps rapidocr==3.10.0)")
        return False
    proxy = Path(row["proxy_path"] or "")
    if not row["proxy_path"] or not proxy.is_file():
        log.info("Recording #%s has no preview copy: no quest tracker to read", row["id"])
        return False
    info = probe(proxy)
    sightings = read_tracker(str(find_binary("ffmpeg")), proxy, float(row["duration_sec"] or 0),
                             size=(info.width or 960, info.height or 540), on_progress=on_progress)
    store(conn, row["id"], sightings)
    return True


def story_of(conn: sqlite3.Connection, recording_id: int) -> Story | None:
    """The episode's quests and times of day; None if its tracker hasn't been read."""
    read = conn.execute("SELECT every_sec FROM quest_reads WHERE recording_id = ?",
                        (recording_id,)).fetchone()
    if read is None:
        return None
    seen = load(conn, recording_id)
    return Story(missions(seen, read["every_sec"]), day_changes(seen))
