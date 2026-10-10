"""Slow-motion replays after the big moments (Phase 2C-2b, spec 7.8 Pacing).

The creator's choices (10 Oct): the moment plays at normal speed first; then
its last few seconds play again at half speed, and the video carries on.
During the replay you hear the game's sound slowed down (its pitch kept
natural) without the voices, so nobody comes out slow and deep, and the
stream's music carries on underneath, at normal speed, as if nothing had
paused. Off by default, like every effect.

Where: placement.py puts a "replay" effect on your multikills, your team's
aces and steals, and on marked moments with a really big jump in the game's
sound (games without League's events). This module turns each into a stretch
of the video:

* **The replay**: from BEFORE_SEC before the moment to AFTER_SEC after it,
  at SPEED, so 3 seconds of game become 6 of video.
* **Where it goes**: INSERT_AFTER_SEC after the moment, so the kill lands and
  you start reacting first; moved to the nearest gap between your words
  within SNAP_SEC, so you're never cut off mid-word.

The clip is rendered in pieces either side of it, like a slide
(render/slide.py). The music in the rest of the clip carries on from where
the replay left it, so the song never jumps or repeats.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..config import Settings
from ..recipes.plan import EditPlan

SPEED = 0.5
BEFORE_SEC = 2.5
AFTER_SEC = 0.5
INSERT_AFTER_SEC = 1.5
SNAP_SEC = 1.0
# Not right at a clip's ends: the clip carries on a little either side of it.
MARGIN_SEC = 0.5
LENGTH_SEC = (BEFORE_SEC + AFTER_SEC) / SPEED


@dataclass(frozen=True)
class Insert:
    """One replay inside a clip, in the clip's own time (seconds from its start)."""
    offset: float          # where the replay goes
    window: float          # where the replayed stretch starts
    window_length: float   # how much of the game is replayed
    at: float              # the moment, in the recording's time
    label: str | None = None

    @property
    def length(self) -> float:
        return self.window_length / SPEED


def _snap(t: float, words, low: float, high: float) -> float:
    """The nearest gap between words to ``t``, within SNAP_SEC, inside [low, high]."""
    from ..analysis.clips import nearest_bound, word_at, word_boundaries

    starts = [w.start for w in words]
    if not word_at(t, words, starts):
        return t
    moved = nearest_bound(word_boundaries(words), t, max(low, t - SNAP_SEC),
                          min(high, t + SNAP_SEC), outward=+1)
    return moved if not word_at(moved, words, starts) else t


def inserts(conn: sqlite3.Connection, plan: EditPlan, effects: list[list],
            lengths: list[float], slides: list[float],
            longest: float | None = None) -> list[list[Insert]]:
    """Each segment's replays. ``slides``: the clip ends taken by slides, which a
    replay can't go in. ``longest``: a Short's limit; a replay that would take it
    over is left out."""
    from ..analysis.clips import load_words, realistic

    words: dict[int, list] = {}
    out: list[list[Insert]] = []
    total = sum(lengths) - sum(slides)
    for i, (segment, fx) in enumerate(zip(plan.segments, effects)):
        found: list[Insert] = []
        head = slides[i - 1] if i > 0 and i - 1 < len(slides) else 0.0
        tail = slides[i] if i < len(slides) else 0.0
        low, high = head + MARGIN_SEC, lengths[i] - tail - MARGIN_SEC
        for e in sorted((e for e in fx if e.kind == "replay"), key=lambda e: e.at):
            moment = e.at - segment.src_in
            window = max(0.0, moment - BEFORE_SEC)
            window_end = min(lengths[i], moment + AFTER_SEC)
            if window_end - window < 1.0:
                continue
            if segment.recording_id not in words:
                words[segment.recording_id] = realistic(load_words(conn, segment.recording_id))
            spoken = [w for w in words[segment.recording_id]]
            where = _snap(segment.src_in + moment + INSERT_AFTER_SEC, spoken,
                          segment.src_in + low, segment.src_in + high) - segment.src_in
            if not low <= where <= high:
                continue
            insert = Insert(round(where, 3), round(window, 3), round(window_end - window, 3),
                            e.at, e.label)
            if longest is not None and total + insert.length > longest + 0.01:
                continue   # a Short can't go over its limit
            if found and where - found[-1].offset < found[-1].length:
                continue
            found.append(insert)
            total += insert.length
        out.append(found)
    return out


def extra(found: list[list[Insert]]) -> list[float]:
    """How much longer each clip gets from its replays."""
    return [sum(r.length for r in clip) for clip in found]


def for_plan(conn: sqlite3.Connection, settings: Settings, plan: EditPlan, fps: int,
             effects: list[list] | None = None) -> list[list[Insert]]:
    """The plan's replays, worked out the same way wherever the video's times
    are needed (rendering, previews, chapters, Review). Nothing, quickly, when
    replays are off for this video."""
    from ..effects import for_plan as effects_for_plan, switches
    from . import slide
    from .final import frame_exact

    none = [[] for _ in plan.segments]
    if "replay" not in switches(settings, plan):
        return none
    effects = effects if effects is not None else effects_for_plan(conn, settings, plan)
    lengths = [frame_exact(s.length, fps) for s in plan.segments]
    slides = slide.overlaps(settings, plan, lengths, fps)
    longest = settings.shorts.max_length_sec if plan.recipe == "shorts" else None
    return inserts(conn, plan, effects, lengths, slides, longest)


def video_lengths(conn: sqlite3.Connection, settings: Settings, plan: EditPlan,
                  fps: int) -> list[float]:
    """Each clip's length in the finished video, replays included (frame-exact)."""
    from .final import frame_exact

    more = extra(for_plan(conn, settings, plan, fps))
    return [frame_exact(s.length, fps) + more[i] for i, s in enumerate(plan.segments)]


def shift(t: float, clip: list[Insert]) -> float:
    """A time in the clip (seconds from its start) as a time in the finished clip,
    after the replays before it."""
    return t + sum(r.length for r in clip if r.offset <= t)

