"""A readable summary of what analysis found, for the creator to check.

This is the Phase 1B acceptance tool, not a feature of the finished product:
it lists timestamps the creator can jump to in the proxy and judge ("yes, I
was laughing there" / "no, that's game music"). Scoring moments properly is
Phase 1E's job.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

import numpy as np

from .audio_signals import top_moments

# How sure the sound model must be before a moment is listed.
EVENT_THRESHOLD = 0.3
MIN_GAP_SEC = 30

# The loudest moments are listed whatever their score. On EP 1's mixed track,
# game audio alone swings about 11 dB, so no second reached even 1.5x the
# normal variation: a fixed "spike" threshold listed nothing at all, which told
# the creator nothing. Ranking lets them judge whether the loudest moments are
# them or the game. Real spike detection belongs to scoring (Phase 1E), where
# a clean mic track makes the voice's own peaks stand out.

EVENT_LABELS = {
    "laughter": "Laughter",
    "shout": "Shouting",
    "scream": "Screaming",
    "gunfire": "Gunfire",
    "explosion": "Explosions",
}


def load_signal(conn: sqlite3.Connection, recording_id: int, name: str) -> np.ndarray:
    rows = conn.execute(
        "SELECT t_sec, value FROM signals WHERE recording_id = ? AND name = ? ORDER BY t_sec",
        (recording_id, name),
    ).fetchall()
    if not rows:
        return np.zeros(0, dtype=np.float32)
    values = np.zeros(rows[-1]["t_sec"] + 1, dtype=np.float32)
    for row in rows:
        values[row["t_sec"]] = row["value"]
    return values


def runs(mask: np.ndarray, value: float = 1.0) -> list[tuple[int, int]]:
    """(start, end) of each unbroken stretch where ``mask == value``."""
    found: list[tuple[int, int]] = []
    start = None
    for second, v in enumerate(mask):
        if v == value and start is None:
            start = second
        elif v != value and start is not None:
            found.append((start, second))
            start = None
    if start is not None:
        found.append((start, len(mask)))
    return found


@dataclass
class MomentReport:
    duration_sec: int
    words: int
    source_role: str | None
    talking_pct: float
    silence_pct: float
    spikes: list[tuple[int, float]] = field(default_factory=list)
    events: dict[str, list[tuple[int, float]]] = field(default_factory=dict)
    quiet_stretches: list[tuple[int, int]] = field(default_factory=list)
    phrases_set_aside: int = 0
    # Moments the creator marked themselves with the Companion's hotkeys.
    markers: list[tuple[int, str]] = field(default_factory=list)


def build_report(conn: sqlite3.Connection, recording_id: int, top: int = 8) -> MomentReport:
    speech = load_signal(conn, recording_id, "speech")
    silence = load_signal(conn, recording_id, "silence")
    energy = load_signal(conn, recording_id, "energy_z")
    seconds = len(speech)

    word_row = conn.execute(
        "SELECT COUNT(*) AS n, MAX(source_role) AS role FROM transcript_words WHERE recording_id = ?",
        (recording_id,),
    ).fetchone()

    events = {}
    for name in EVENT_LABELS:
        values = load_signal(conn, recording_id, name)
        if values.size:
            events[name] = top_moments(values, count=top, min_gap=MIN_GAP_SEC,
                                       threshold=EVENT_THRESHOLD)

    # Stretches of at least 20 s with no words at all, longest first.
    quiet = [(s, e) for s, e in runs((speech > 0).astype(np.float32), 0.0) if e - s >= 20]
    quiet.sort(key=lambda span: span[1] - span[0], reverse=True)

    notes_row = conn.execute("SELECT notes FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    try:
        set_aside = int(json.loads(notes_row["notes"] or "{}").get("phrases_set_aside", 0))
    except (ValueError, TypeError, AttributeError):
        set_aside = 0

    marker_rows = conn.execute(
        "SELECT t_sec, name FROM signals WHERE recording_id = ? AND name IN "
        "('marker', 'marker_short') ORDER BY t_sec",
        (recording_id,),
    ).fetchall()

    return MomentReport(
        phrases_set_aside=set_aside,
        markers=[(int(r["t_sec"]), r["name"]) for r in marker_rows],
        duration_sec=seconds,
        words=word_row["n"],
        source_role=word_row["role"],
        talking_pct=float((speech > 0).mean() * 100) if seconds else 0.0,
        silence_pct=float(silence.mean() * 100) if silence.size else 0.0,
        spikes=top_moments(energy, count=top, min_gap=MIN_GAP_SEC, threshold=0.0)
        if energy.size else [],
        events=events,
        quiet_stretches=quiet[:5],
    )
