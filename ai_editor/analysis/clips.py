"""From a score per second to clips with clean edges (spec section 7.3).

    1. Find the peaks in the score. Each peak's *core* is the stretch around it
       that stays above half its height.
    2. Add context: a lead-in before the core, because the cause of a reaction
       comes before it (the creator: "it could have happened 10 or 30 seconds
       before"), and a short tail so the reaction can finish.
    3. Respect scene changes: a clip never opens on, or runs on into, a menu,
       loading screen or scoreboard. If the picture cuts during the lead-in, the
       clip starts after the cut; if it cuts during the tail, it ends before it.
    4. Land each edge on a clean point -- a pause, the end of a sentence, a
       scene change -- and never inside a word.

Nothing here decides what a finished video contains. The recipes (Phase 1F)
choose among these clips, trim them, and order them. These are the candidates
in the clip library, analysed once and reused by every recipe (spec section 5).
"""

from __future__ import annotations

import bisect
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

import numpy as np

from ..config import Clips as ClipSettings
from .captions import SENTENCE_END, Word

# Breathing room either side of a word when an edge is moved off it.
WORD_PAD_BEFORE = 0.12
WORD_PAD_AFTER = 0.2
# Edges placed next to a scene change sit this far to its safe side.
CUT_PAD = 0.05
# No spoken word takes longer than this. Whisper sometimes stretches a word's
# start back over the music before it: on the creator's Wardogs stream it
# reported one "don't" as lasting 12 seconds. The word itself is at the end.
MAX_WORD_SEC = 1.5


def realistic(words: Sequence[Word]) -> list[Word]:
    """Words sorted, with stretched starts pulled in to at most MAX_WORD_SEC."""
    return [
        Word(w.text, max(w.start, w.end - MAX_WORD_SEC), w.end, w.probability)
        for w in sorted(words, key=lambda w: w.start)
    ]


def word_boundaries(words: Sequence[Word]) -> list[float]:
    """Every point where cutting splits no word: gaps, and where one word meets the next."""
    points: list[float] = []
    for i, word in enumerate(words):
        after = words[i + 1] if i + 1 < len(words) else None
        if i == 0:
            points.append(max(0.0, word.start - WORD_PAD_BEFORE))
        if after is None:
            points.append(word.end + WORD_PAD_AFTER)
        elif after.start >= word.end:
            # Mid-gap; when words touch, exactly where they meet.
            points.append(word.end + (after.start - word.end) / 2)
    return sorted(points)


@dataclass
class Clip:
    start: float
    end: float
    peak_sec: int
    score: float
    core: tuple[int, int]
    reasons: list[tuple[str, float]] = field(default_factory=list)

    @property
    def length(self) -> float:
        return self.end - self.start


# --- Peaks -----------------------------------------------------------------


def find_cores(
    score: np.ndarray, *, min_score: float, core_fraction: float
) -> list[tuple[int, float, int, int]]:
    """(peak second, peak score, core start, core end), best first.

    Takes the highest second not already used, grows it while the score stays
    above ``core_fraction`` of that height, then repeats. A long fight becomes
    one core rather than a dozen neighbouring peaks.
    """
    taken = np.zeros(len(score), dtype=bool)
    cores: list[tuple[int, float, int, int]] = []
    for second in np.argsort(score)[::-1]:
        second = int(second)
        value = float(score[second])
        if value < min_score:
            break
        if taken[second]:
            continue
        floor = value * core_fraction
        left = second
        while left > 0 and not taken[left - 1] and score[left - 1] >= floor:
            left -= 1
        right = second
        while right < len(score) - 1 and not taken[right + 1] and score[right + 1] >= floor:
            right += 1
        taken[left:right + 1] = True
        cores.append((second, value, left, right))
    return cores


# --- Clean edges -------------------------------------------------------------


def clean_starts(words: Sequence[Word], cuts: Sequence[float], pause: float) -> list[float]:
    """Moments a clip can start at without starting mid-thought."""
    points = [0.0]
    for i, word in enumerate(words):
        if i == 0:
            points.append(max(0.0, word.start - WORD_PAD_BEFORE))
            continue
        before = words[i - 1]
        gap = word.start - before.end
        if gap >= pause or before.text.rstrip().endswith(SENTENCE_END):
            points.append(max(before.end, word.start - min(WORD_PAD_BEFORE, gap / 2)))
    points += [cut + CUT_PAD for cut in cuts]
    return sorted(points)


def clean_ends(words: Sequence[Word], cuts: Sequence[float], pause: float) -> list[float]:
    """Moments a clip can end at without cutting someone off."""
    points: list[float] = []
    for i, word in enumerate(words):
        after = words[i + 1] if i + 1 < len(words) else None
        gap = (after.start - word.end) if after else float("inf")
        if gap >= pause or word.text.rstrip().endswith(SENTENCE_END):
            points.append(word.end + min(WORD_PAD_AFTER, gap / 2))
    points += [cut - CUT_PAD for cut in cuts]
    return sorted(points)


def word_at(t: float, words: Sequence[Word], starts: Sequence[float]) -> Word | None:
    """The word being said at time ``t``, if any."""
    index = bisect.bisect_right(starts, t) - 1
    if index >= 0 and words[index].start < t < words[index].end:
        return words[index]
    return None


def _snap(target: float, points: Sequence[float], window: float, *, earlier: bool,
          low: float, high: float) -> float:
    """The clean point nearest ``target``, preferring earlier (starts) or later (ends)."""
    nearby = [p for p in points if abs(p - target) <= window and low <= p <= high]
    if not nearby:
        return target
    preferred = [p for p in nearby if (p <= target if earlier else p >= target)]
    pool = preferred or nearby
    return min(pool, key=lambda p: abs(p - target))


def walls(cuts: Sequence[float], *, busy_count: int, window: float) -> list[float]:
    """The scene changes a clip must not cross: the ones that stand alone.

    Measured on the creator's footage. Wardogs: 217 changes in 1h52, about one
    every 31 seconds -- menus, scoreboards, loading, the helicopter. EP 1 of
    Dawnwalker: 1,517 in 2h06, one every 5 seconds, because its cutscenes cut
    between camera angles constantly. Treating those as walls chopped the
    build-up off nearly every clip (median length 16 s, shortest 4 s). A menu
    is a change on its own; camera editing comes in runs.
    """
    ordered = sorted(cuts)
    kept = []
    for i, cut in enumerate(ordered):
        lo = bisect.bisect_left(ordered, cut - window)
        hi = bisect.bisect_right(ordered, cut + window)
        if hi - lo - 1 <= busy_count:  # others nearby, not counting itself
            kept.append(cut)
    return kept


EVENTFUL_LOOKBACK_SEC = 5


def _eventful_before(score: np.ndarray, cut: float, settings: ClipSettings) -> bool:
    """Was something worth clipping already happening just before this cut?"""
    end = int(cut)
    window = score[max(0, end - EVENTFUL_LOOKBACK_SEC):end]
    return bool(window.size) and float(window.mean()) >= settings.min_score


def _nearest_bound(bounds: Sequence[float], t: float, low: float, high: float,
                   *, outward: int) -> float:
    """The closest word boundary to ``t`` within [low, high], trying outward first."""
    index = bisect.bisect_left(bounds, t)
    earlier = [b for b in bounds[max(0, index - 50):index] if low <= b <= t]
    later = [b for b in bounds[index:index + 50] if t <= b <= high]
    first, second = (earlier[::-1], later) if outward < 0 else (later, earlier[::-1])
    if first:
        return first[0]
    if second:
        return second[0]
    return t


def fit_edges(
    core: tuple[int, int],
    peak: int,
    *,
    words: Sequence[Word],
    cuts: Sequence[float],
    duration: float,
    settings: ClipSettings,
    score: np.ndarray | None = None,
) -> tuple[float, float]:
    """Where a clip around this core should start and end."""
    core_start, core_end = float(core[0]), float(core[1] + 1)
    start = core_start - settings.lead_in_sec
    end = core_end + settings.tail_sec

    # Never open on, or run on into, another scene: menus, loading, scoreboard.
    # Camera cuts inside a cutscene don't count (see walls()); every cut is
    # still a clean place to put an edge.
    hard = walls(cuts, busy_count=settings.scene_busy_count, window=settings.scene_busy_window_sec)
    # A change in the lead-in only matters if nothing was happening before
    # it. On the creator's Wardogs stream, "fight -> downed" is a scene change
    # too; treating it as a wall cut the whole fight off the front of their
    # favourite clip, leaving 9 seconds. Before a menu or loading screen the
    # score is low; before getting downed it is high.
    if score is not None:
        hard = [c for c in hard if c > core_start or not _eventful_before(score, c, settings)]
    floor, ceiling = 0.0, duration
    before = [c for c in hard if start < c <= core_start]
    if before:
        floor = before[-1] + CUT_PAD
    after = [c for c in hard if core_end <= c < end]
    if after:
        ceiling = after[0] - CUT_PAD
    start, end = max(start, floor), min(end, ceiling)

    # Length limits. Too long: keep the part around the peak, with more
    # before it than after (the build-up matters more than the aftermath).
    if end - start > settings.max_length_sec:
        start = max(start, min(float(peak) - settings.max_length_sec * 0.65,
                               end - settings.max_length_sec))
        end = start + settings.max_length_sec
    if end - start < settings.min_length_sec:
        missing = settings.min_length_sec - (end - start)
        end = min(ceiling, end + missing)
        start = max(floor, end - settings.min_length_sec)

    starts = clean_starts(words, cuts, settings.pause_sec)
    ends = clean_ends(words, cuts, settings.pause_sec)
    start = _snap(start, starts, settings.snap_sec, earlier=True, low=floor, high=core_start)
    end = _snap(end, ends, settings.snap_sec, earlier=False, low=core_end, high=ceiling)

    # Last guard: whatever happened above, never inside a word. Move to the
    # nearest word boundary, outward if the scene limits allow it, inward if
    # not. Found on the creator's Wardogs stream, where 6 of 47 clips broke
    # this: talking straight through a scene change (stepping back would
    # cross the cut), and non-stop speech with no gap to step into -- which is
    # why the boundary between two touching words counts as a clean point.
    # The scene limits here are the cuts themselves, not the padded edges:
    # finishing a word right before the picture changes is still before it.
    word_starts = [w.start for w in words]
    bounds = word_boundaries(words)
    if word_at(start, words, word_starts):
        start = _nearest_bound(bounds, start, floor - CUT_PAD, core_start, outward=-1)
    if word_at(end, words, word_starts):
        end = _nearest_bound(bounds, end, core_end, ceiling + CUT_PAD, outward=+1)
    # Last resort, when no clean point exists outside the core: trim into it.
    # A slightly shorter clip is better than one that cuts someone off.
    if word_at(start, words, word_starts):
        start = _nearest_bound(bounds, start, floor - CUT_PAD, end, outward=+1)
    if word_at(end, words, word_starts):
        end = _nearest_bound(bounds, end, start, ceiling + CUT_PAD, outward=-1)

    return max(0.0, round(start, 3)), min(duration, round(end, 3))


# --- Putting it together -------------------------------------------------------


def build_clips(
    score: np.ndarray,
    *,
    words: Sequence[Word],
    cuts: Sequence[float],
    duration: float,
    settings: ClipSettings,
) -> list[Clip]:
    """All candidate clips in a recording, in time order."""
    words = realistic(words)
    chosen: list[Clip] = []
    for peak, value, left, right in find_cores(
        score, min_score=settings.min_score, core_fraction=settings.core_fraction
    ):
        start, end = fit_edges((left, right), peak, words=words, cuts=cuts,
                               duration=duration, settings=settings, score=score)
        if end - start < 1.0:
            continue
        clip = Clip(start, end, peak, round(value, 3), (left, right))
        overlapping = [c for c in chosen if c.start < clip.end and clip.start < c.end]
        if not overlapping:
            chosen.append(clip)
            continue
        # Two peaks whose clips overlap are one moment. Merge them if the
        # result isn't too long; otherwise the better one (found first) wins.
        merged_start = min([clip.start] + [c.start for c in overlapping])
        merged_end = max([clip.end] + [c.end for c in overlapping])
        if merged_end - merged_start <= settings.max_length_sec:
            best = max(overlapping, key=lambda c: c.score)
            for c in overlapping:
                chosen.remove(c)
            chosen.append(Clip(merged_start, merged_end, best.peak_sec, best.score,
                               (min(best.core[0], left), max(best.core[1], right))))
    return sorted(chosen, key=lambda c: c.start)


def explain(clip: Clip, parts: dict[str, np.ndarray], *, top: int = 3) -> list[tuple[str, float]]:
    """What made this clip score: the strongest contributions across its core."""
    left, right = clip.core
    found = [
        (name, float(values[left:right + 1].mean()))
        for name, values in parts.items()
        if right < len(values) and values[left:right + 1].mean() > 0.02
    ]
    found.sort(key=lambda pair: pair[1], reverse=True)
    return found[:top]


# --- The clip library ----------------------------------------------------------


def clip_id(recording_id: int, start: float) -> str:
    """Stable while the clip's start doesn't move, so feedback stays attached."""
    return f"rec{recording_id}_{int(round(start * 1000)):09d}"


def store_clips(
    conn: sqlite3.Connection,
    recording_id: int,
    clips: Sequence[Clip],
    *,
    signals: dict[str, np.ndarray],
    words: Sequence[Word],
) -> int:
    """Replace a recording's automatic clips. Clips you rated, pinned or used are kept."""
    conn.execute(
        "DELETE FROM clips WHERE recording_id = ? AND user_rating IS NULL AND pinned = 0 "
        "AND used_in_json IS NULL",
        (recording_id,),
    )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for clip in clips:
        a, b = int(clip.start), int(np.ceil(clip.end))
        summary = {name: round(float(values[a:b].max()), 3)
                   for name, values in signals.items() if values[a:b].size and values[a:b].max() > 0}
        summary["reasons"] = [name for name, _ in clip.reasons]
        text = " ".join(w.text for w in words if w.start >= clip.start and w.end <= clip.end)
        conn.execute(
            "INSERT OR IGNORE INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
            "signals_json, transcript, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (clip_id(recording_id, clip.start), recording_id, clip.start, clip.end,
             clip.score, json.dumps(summary), text, now),
        )
    conn.commit()
    return len(clips)


def load_words(conn: sqlite3.Connection, recording_id: int) -> list[Word]:
    return [
        Word(r["word"], r["start_sec"], r["end_sec"], r["confidence"] or 1.0)
        for r in conn.execute(
            "SELECT word, start_sec, end_sec, confidence FROM transcript_words "
            "WHERE recording_id = ? ORDER BY start_sec",
            (recording_id,),
        )
    ]
