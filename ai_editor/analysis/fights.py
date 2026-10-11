"""A fight already going when a clip starts (Phase 2H-1).

The creator's tip (2026-10-11): "Ensure the action is always within the
clip." A clip's end already waits for a fight to finish
(clips.fight_continues); its start didn't look. On the 10 Oct League stream a
highlight clip opened at 46:32, two deaths into a fight whose sound began at
46:27.

**Fighting**, second by second: what fight_continues follows (gunfire,
explosions, champions dying close together), or the game's own sound among
its loudest seconds (clips.fight_loud_percentile of that recording's).
On League, gunfire and explosions barely register and League only says when
someone dies; the game's sound around its kills sits at the 90th percentile
of the stream.

**Going on at a clip's start**: at least NEED_SEC of the SIDE_SEC seconds on
each side of it are fighting. It **began** where the fighting before it
started, followed back while it never stops for FIGHT_GAP_SEC, up to
fight_extend_sec.

On the creator's plans of 10-11 Oct, 1 clip in 84 opened mid-fight this way.
Only the videos' clips move (recipes/highlights.py): the clip library keeps
its edges, so ratings and adjusted cuts stay where they are.
"""

from __future__ import annotations

import sqlite3

import numpy as np

from ..config import Settings
from .clips import action_signal

SIDE_SEC = 5
NEED_SEC = 3
# A shorter gap than a clip's end follows (fight_gap_sec, 10 s): the game's
# sound is loud now and then outside fights too, and 10 s let one loud second
# before the fight count as its start.
FIGHT_GAP_SEC = 4
# Start this long before the first second of fighting.
BEFORE_SEC = 1.0
# Review marks a clip only when it misses at least this much of the fight.
MISSED_SEC = 2.0
# The game's sound in seconds where nothing plays (dB): left out of its percentile.
SILENT_DB = -90.0


def fighting(signals: dict[str, np.ndarray], settings: Settings) -> np.ndarray | None:
    """Each second: is a fight going on? None when nothing can tell."""
    found = []
    action = action_signal(signals)
    if action is not None:
        found.append(action >= settings.clips.fight_level)
    game = signals.get("game_db")
    if game is not None:
        playing = game[game > SILENT_DB]
        if playing.size >= 60:
            # Above the middle too: where hardly anything is loud, the percentile
            # is the usual level itself, and every second would count.
            found.append((game >= np.percentile(playing, settings.clips.fight_loud_percentile))
                         & (game > np.median(playing)))
    if not found:
        return None
    size = min(len(f) for f in found)
    return np.logical_or.reduce([f[:size] for f in found])


def began(fight: np.ndarray | None, start: float, settings: Settings) -> float | None:
    """Where the fight going on at ``start`` began, or None if there isn't one."""
    if fight is None or not fight.size:
        return None
    t = int(start)
    if fight[max(0, t - SIDE_SEC):t].sum() < NEED_SEC or fight[t:t + SIDE_SEC].sum() < NEED_SEC:
        return None
    limit = max(0, t - int(settings.clips.fight_extend_sec))
    first = t
    while first > limit:
        lo = max(limit, first - FIGHT_GAP_SEC)
        hits = np.nonzero(fight[lo:first])[0]
        if not hits.size:
            break
        first = lo + int(hits[0])
    return float(first) if first < t else None


def start_before(fight: np.ndarray | None, start: float, settings: Settings) -> float | None:
    """Where a clip starting at ``start`` should start to have all of the fight
    going on there, or None when there's no fight to wait for."""
    first = began(fight, start, settings)
    if first is None:
        return None
    return max(0.0, first - BEFORE_SEC)


_cache: dict[tuple[str, int], np.ndarray | None] = {}


def _fighting_for(conn: sqlite3.Connection, settings: Settings,
                  recording_id: int) -> np.ndarray | None:
    from .hype import load_signals

    key = (str(settings.db_path), recording_id)
    if key not in _cache:
        row = conn.execute("SELECT duration_sec FROM recordings WHERE id = ?",
                           (recording_id,)).fetchone()
        seconds = int(row[0] or 0) + 1 if row else 0
        _cache[key] = fighting(load_signals(conn, recording_id, seconds), settings) \
            if seconds > 1 else None
    return _cache[key]


def missed(conn: sqlite3.Connection, settings: Settings, recording_id: int,
           start: float) -> float | None:
    """How much of a fight a clip starting at ``start`` leaves out, for Review's
    mark: None when it misses less than MISSED_SEC (or there's no fight)."""
    if not settings.clips.keep_fights_whole:
        return None
    first = began(_fighting_for(conn, settings, recording_id), start, settings)
    if first is None or start - first < MISSED_SEC:
        return None
    return start - first
