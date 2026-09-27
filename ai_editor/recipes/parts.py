"""Splitting a trimmed Let's Play episode into parts (spec section 7.6, Recipe A).

The creator's default: about four 30-minute parts from a two-hour session,
each 25-35 minutes, never split mid-talk, mid-fight or mid-cutscene. A part
may stretch toward 45 minutes (60 at most) only when there's no clean break.

How: every place a part could end is a *break point*, with a cost -- a
loading screen is the best place, a pause in talking is fine, a break right
after a strong moment is better still (viewers want the next part). Each
possible part has a cost too, by how far its length is from the target. The
cheapest way through the whole episode wins (dynamic programming, as the spec
suggests), so an early long part is balanced by the ones after it.

Story missions (never split inside one) need the screen read for "quest
started / completed", which comes later. Until then talking, fights and
cutscenes are what's protected.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import Settings
from .letsplay import Cut, Episode

# A pause in talking at least this long is a place a part can end.
PAUSE_SEC = 1.5
# Where a cut already is, the jump is there anyway: the best places to end.
CUT_BREAK_COST = {"loading": -3.0, "stream_screen": -3.0, "menu": -2.0, "silence": -1.0}
# A strong moment this recently before a break makes it a hook ending.
HOOK_WINDOW_SEC = 60.0
HOOK_SCORE = 0.7
# If there's no allowed break at all for too long: split at the gentlest
# pause anyway, and say so.
FORCED_COST = 50.0
# Prefer lengths close to the target even inside the normal range.
NEAR_TARGET_COST_PER_MIN = 0.1


@dataclass
class Break:
    at: float            # output time (seconds into the trimmed episode)
    source: float        # the same moment in the recording
    cost: float
    kind: str            # "loading", "menu", "silence", "stream_screen", "pause", "forced"
    hook: bool = False


@dataclass
class Part:
    number: int
    start: float         # output time
    end: float
    source_start: float  # recording time
    source_end: float
    ends_on: str         # what the break at its end is ("end" for the last part)
    hook: bool = False
    flagged: bool = False  # split somewhere it'd rather not: check it

    @property
    def length(self) -> float:
        return self.end - self.start


def to_output(pieces: list[tuple[float, float]], t: float) -> float | None:
    """Recording time -> time in the trimmed episode (None if t was cut)."""
    out = 0.0
    for a, b in pieces:
        if a <= t <= b:
            return out + (t - a)
        out += b - a
    return None


def to_source(pieces: list[tuple[float, float]], at: float) -> float:
    """Time in the trimmed episode -> recording time."""
    for a, b in pieces:
        if at <= b - a:
            return a + at
        at -= b - a
    return pieces[-1][1] if pieces else 0.0


def break_points(episode: Episode, cuts: list[Cut], pieces: list[tuple[float, float]],
                 settings: Settings) -> list[Break]:
    """Everywhere a part could end, with what it costs to end there."""
    lp = settings.lets_play
    seconds = episode.seconds
    hud = episode.signals.get("hud")
    playing = (np.resize(hud, seconds) >= lp.hud_level) if hud is not None and hud.size else None

    def hook_at(source: float) -> bool:
        a = max(0, int(source - HOOK_WINDOW_SEC))
        return lp.hook_endings and bool(episode.score[a:int(source) + 1].max(initial=0.0) >= HOOK_SCORE)

    breaks: list[Break] = []
    for cut in cuts:
        at = to_output(pieces, cut.start)
        if at is not None and 0 < at:
            hook = hook_at(cut.start)
            breaks.append(Break(at, cut.start, CUT_BREAK_COST.get(cut.reason, -1.0)
                                + (lp.bonus_hook_ending if hook else 0.0), cut.reason, hook))

    words = episode.words
    for before, after in zip(words, words[1:]):
        gap = after.start - before.end
        if gap < 0.6:
            continue
        middle = (before.end + after.start) / 2
        at = to_output(pieces, middle)
        if at is None or at <= 0:
            continue
        s = min(seconds - 1, int(middle))
        # Never mid-fight, mid-cutscene, or while the characters are talking.
        allowed = (gap >= PAUSE_SEC and not episode.protected[s] and not episode.talking[s]
                   and (playing is None or playing[s]))
        if allowed:
            hook = hook_at(middle)
            breaks.append(Break(at, middle, -min(gap, 5.0) / 5.0
                                + (lp.bonus_hook_ending if hook else 0.0), "pause", hook))
        else:
            # Only used if nothing better exists for a whole part's length.
            breaks.append(Break(at, middle, FORCED_COST, "forced"))
    return sorted(breaks, key=lambda b: b.at)


def part_cost(minutes: float, settings: Settings, *, last: bool) -> float | None:
    """What a part this long costs; None if it's longer than allowed."""
    lp = settings.lets_play
    low, high = lp.normal_range_min
    if minutes > lp.story_extension_hard_max_min:
        return None
    cost = NEAR_TARGET_COST_PER_MIN * abs(minutes - lp.target_min)
    per_min = lp.penalties.per_min_outside_normal_range
    if minutes < low:
        # A short last piece is worse than a long one: it's a leftover.
        cost += per_min * (low - minutes) * (3.0 if last and minutes < lp.leftover.min_standalone_min else 1.0)
    elif minutes > high:
        cost += per_min * (minutes - high)
    if minutes > lp.story_extension_preferred_max_min:
        cost += lp.penalties.per_min_over_45 * (minutes - lp.story_extension_preferred_max_min)
    return cost


def split(total_sec: float, breaks: list[Break], settings: Settings) -> list[Break]:
    """The cheapest set of breaks. Returns the chosen breaks, in order."""
    points = [Break(0.0, 0.0, 0.0, "start")] + [b for b in breaks if 0 < b.at < total_sec] \
        + [Break(total_sec, 0.0, 0.0, "end")]
    hard = settings.lets_play.story_extension_hard_max_min * 60
    best = [float("inf")] * len(points)
    back = [-1] * len(points)
    best[0] = 0.0
    first = 0
    for j in range(1, len(points)):
        while points[j].at - points[first].at > hard:
            first += 1
        last = j == len(points) - 1
        for i in range(first, j):
            if best[i] == float("inf"):
                continue
            cost = part_cost((points[j].at - points[i].at) / 60, settings, last=last)
            if cost is None:
                continue
            total = best[i] + cost + points[j].cost
            if total < best[j]:
                best[j], back[j] = total, i
    chosen, j = [], len(points) - 1
    while back[j] > 0:
        j = back[j]
        chosen.append(points[j])
    return list(reversed(chosen))


def make_parts(total_sec: float, chosen: list[Break], pieces: list[tuple[float, float]]) -> list[Part]:
    edges = [0.0] + [b.at for b in chosen] + [total_sec]
    ends = [b.kind for b in chosen] + ["end"]
    hooks = [b.hook for b in chosen] + [False]
    parts = []
    for n, (a, b) in enumerate(zip(edges, edges[1:]), start=1):
        mine = range_pieces(pieces, a, b)
        parts.append(Part(n, a, b, mine[0][0] if mine else 0.0, mine[-1][1] if mine else 0.0,
                          ends[n - 1], hook=hooks[n - 1], flagged=ends[n - 1] == "forced"))
    return parts


def pieces_of_part(pieces: list[tuple[float, float]], part: Part) -> list[tuple[float, float]]:
    """The recording stretches that make up one part."""
    return range_pieces(pieces, part.start, part.end)


def range_pieces(pieces: list[tuple[float, float]], start: float, end: float) -> list[tuple[float, float]]:
    """The recording stretches that play between two moments of the trimmed episode."""
    found, out = [], 0.0
    for a, b in pieces:
        length = b - a
        lo, hi = max(start, out), min(end, out + length)
        if hi - lo > 0.05:
            found.append((a + (lo - out), a + (hi - out)))
        out += length
    return found
