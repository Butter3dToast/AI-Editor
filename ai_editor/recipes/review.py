"""Review: the creator's changes to a highlight plan (spec section 9, item 8).

What the creator chose for the first version (2026-10-03): choose the
teaser, remove a clip, move clips up and down. A removed clip is replaced by
the next best one, the same way the recipe filled the video in the first
place, because the target length is a floor: "about 10 min, never below".

Every change is logged as feedback (spec section 7.10), so Phase 3 can learn
from what the creator takes out and what they open with.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from ..analysis.captions import clock
from ..config import Settings
from .highlights import (
    Candidate,
    best_of,
    gather,
    recorded_at,
    recordings_for,
    short_note,
    teaser_segment,
    top_up,
)
from .plan import EditPlan, Segment


@dataclass
class Change:
    plan: EditPlan
    message: str
    added: list[Segment] = field(default_factory=list)


def clip_indexes(plan: EditPlan) -> list[int]:
    """Where the clips are in the plan (everything but the teaser)."""
    return [n for n, s in enumerate(plan.segments) if s.kind != "teaser"]


def teaser_index(plan: EditPlan) -> int | None:
    return next((n for n, s in enumerate(plan.segments) if s.kind == "teaser"), None)


def clips_sec(plan: EditPlan) -> float:
    return sum(s.length for s in plan.segments if s.kind != "teaser")


def log_feedback(conn: sqlite3.Connection, action: str, plan: EditPlan, segment: Segment | None,
                 **detail) -> None:
    """One row of what the creator did, for learning their taste later."""
    features = clip_id = None
    if segment is not None and segment.clip_id:
        row = conn.execute("SELECT signals_json FROM clips WHERE clip_id = ?",
                           (segment.clip_id,)).fetchone()
        # Re-cutting a recording can replace a draft's clips, so the clip may
        # be gone from the library; what it was is still worth keeping.
        if row:
            features, clip_id = row["signals_json"], segment.clip_id
        detail = {"clip": segment.clip_id, "recording": segment.recording_id,
                  "at": [segment.src_in, segment.src_out], "reasons": segment.reasons,
                  "score": segment.score, **detail}
    conn.execute(
        "INSERT INTO feedback (ts, action, clip_id, plan_id, game, features_json, detail_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), action, clip_id,
         plan.plan_id, (segment.game if segment else None) or plan.game, features,
         json.dumps(detail)))
    conn.commit()


def _candidates(conn: sqlite3.Connection, settings: Settings, plan: EditPlan, *,
                quality_bar: bool = True) -> list[Candidate]:
    source = plan.source or {}
    recordings = recordings_for(conn, settings, game=source.get("game", plan.game),
                                recording_ids=source.get("recording_ids"))
    in_plan = {s.clip_id for s in plan.segments if s.clip_id}
    return gather(conn, settings, recordings, game=source.get("game", plan.game), refresh=False,
                  allow=in_plan, quality_bar=quality_bar, reuse=bool(source.get("reuse")))


def _as_candidate(segment: Segment, known: dict[str, Candidate]) -> Candidate:
    """The recipe's view of a clip in the plan, at the length it has in the plan."""
    found = known.get(segment.clip_id or "")
    if found is None:  # e.g. rated down since: still in the plan, so still usable
        found = Candidate(segment.clip_id or "", segment.recording_id, segment.src_in,
                          segment.src_out, segment.score or 0.0, int(segment.src_in),
                          (int(segment.src_in), int(segment.src_out)), segment.reasons,
                          datetime.now(timezone.utc), False, game=segment.game)
    return replace(found, src_in=segment.src_in, src_out=segment.src_out)


def _segment(c: Candidate) -> Segment:
    return Segment(c.recording_id, round(c.src_in, 3), round(c.src_out, 3), kind="clip",
                   clip_id=c.clip_id, score=c.score, reasons=c.reasons, game=c.game)


def remove(conn: sqlite3.Connection, settings: Settings, plan: EditPlan, index: int) -> Change:
    """Take out one piece. A clip is replaced by the next best; the teaser just goes."""
    segment = plan.segments[index]
    plan.segments.pop(index)
    log_feedback(conn, "removed", plan, segment, kind=segment.kind)
    if segment.kind == "teaser":
        return Change(plan, "Teaser taken out: the video now starts with its first clip. "
                            "Pick a clip and press 'Use as teaser' to add one back.")

    plan.source = dict(plan.source or {})
    plan.source["removed"] = [*plan.source.get("removed", []), segment.clip_id]
    candidates = _candidates(conn, settings, plan)
    known = {c.clip_id: c for c in candidates}
    message = f"Clip taken out ({segment.length:.0f}s)."

    # The teaser shows the moment the video ends on. If that clip went, both move
    # to the best of what's left, so they still match.
    t = teaser_index(plan)
    if t is not None and plan.segments[t].clip_id == segment.clip_id:
        remaining = [_as_candidate(plan.segments[n], known) for n in clip_indexes(plan)]
        if remaining:
            best = best_of(remaining)
            spot = next(n for n in clip_indexes(plan) if plan.segments[n].clip_id == best.clip_id)
            moved = plan.segments.pop(spot)
            plan.segments.append(moved)
            plan.segments[teaser_index(plan)] = teaser_segment(conn, settings, best)
            message += " It was the teaser's moment, so the teaser and ending are now your next best."
        else:
            plan.segments.pop(t)

    taken = {s.clip_id for s in plan.segments} | set(plan.source["removed"])
    covered = [(s.recording_id, s.src_in, s.src_out) for s in plan.segments]
    pool = [c for c in candidates if c.clip_id not in taken and not any(
        rid == c.recording_id and a < c.src_out and c.src_in < b for rid, a, b in covered)]
    fill_order = settings.highlights.fill_order
    added = [_segment(c) for c in top_up(pool, clips_sec(plan), plan.target_sec, fill_order)]
    if settings.highlights.ordering == "timeline":
        for new in added:
            insert_by_time(conn, plan, new)
    else:
        # The new clips go where the old one was, so the rest of the order holds:
        # after the teaser, and (with a teaser) before the finale it pays off.
        if teaser_index(plan) is not None:
            spot = max(1, min(index, len(plan.segments) - 1))
        else:
            spot = min(index, len(plan.segments))
        plan.segments[spot:spot] = added
    if added:
        message += (f" Replaced with {len(added)} clip(s) ({sum(s.length for s in added):.0f}s), "
                    f"so the video is {plan.total_sec / 60:.1f} min.")
    elif clips_sec(plan) >= plan.target_sec:
        message += (f" Still {plan.total_sec / 60:.1f} min, over the {plan.target_sec / 60:.0f} "
                    "minute target, so nothing else was needed.")
    if clips_sec(plan) < plan.target_sec:
        recordings = len({c.recording_id for c in candidates}) or len(plan.recording_ids)
        message += " " + short_note(clips_sec(plan), plan.target_sec, recordings)
    return Change(plan, message, added)


def move(conn: sqlite3.Connection, plan: EditPlan, index: int, step: int) -> Change:
    """Swap a clip with the one before (-1) or after (+1). The teaser stays first."""
    clips = clip_indexes(plan)
    if index not in clips:
        return Change(plan, "The teaser always opens the video. Move the clips around it.")
    position = clips.index(index) + step
    if not 0 <= position < len(clips):
        return Change(plan, "It's already " + ("first." if step < 0 else "last."))
    other = clips[position]
    plan.segments[index], plan.segments[other] = plan.segments[other], plan.segments[index]
    log_feedback(conn, "reordered", plan, plan.segments[other], step=step)
    return Change(plan, "Moved " + ("up." if step < 0 else "down."))


def use_as_teaser(conn: sqlite3.Connection, settings: Settings, plan: EditPlan, index: int,
                  moment: tuple[float, float] | None = None) -> Change:
    """Open with this clip's moment, and end the video on the clip in full.

    ``moment``: the stretch to show, in recording time; else the automatic
    pick (the reaction's peak, ending at a pause).
    """
    segment = plan.segments[index]
    if segment.kind == "teaser":
        return Change(plan, "That's already the teaser. Pick one of the clips.")
    known = {c.clip_id: c for c in _candidates(conn, settings, plan)}
    best = _as_candidate(segment, known)
    teaser = teaser_segment(conn, settings, best, moment)
    t = teaser_index(plan)
    old_finale = None
    if t is not None and settings.highlights.ordering == "timeline":
        old = plan.segments[t].clip_id
        spot = next((n for n in reversed(clip_indexes(plan)) if plan.segments[n].clip_id == old),
                    None)
        if spot is not None and spot != index:
            old_finale = plan.segments.pop(spot)
            index -= 1 if spot < index else 0
    plan.segments.pop(index)
    plan.segments.append(segment)  # the payoff: the full moment ends the video
    t = teaser_index(plan)
    if t is None:
        plan.segments.insert(0, teaser)
    else:
        plan.segments[t] = teaser
    if old_finale is not None:
        insert_by_time(conn, plan, old_finale)  # back in its place in the story
    log_feedback(conn, "teaser_chosen", plan, segment,
                 moment=list(moment) if moment else None)
    return Change(plan, f"Teaser set ({teaser.length:.0f}s). That clip now ends the video in full.")


def addable(conn: sqlite3.Connection, settings: Settings,
            plan: EditPlan) -> list[tuple[str, str, int, float, float]]:
    """(label, clip id, recording, in, out) for clips that could be added:
    thumbs up first, then the best. ``in`` and ``out`` are as they'd be in the video.

    From the same streams as the plan, not already in it and not rated down;
    clips under the quality bar too, since the creator is the judge here.
    """
    in_plan = {s.clip_id for s in plan.segments}
    covered = [(s.recording_id, s.src_in, s.src_out) for s in plan.segments]
    pool = [c for c in _candidates(conn, settings, plan, quality_bar=False)
            if c.clip_id not in in_plan and not any(
                rid == c.recording_id and a < c.src_out and c.src_in < b for rid, a, b in covered)]
    pool.sort(key=lambda c: (not c.liked, -c.score, c.recording_id, c.src_in))
    said = {r["clip_id"]: (r["transcript"] or "").strip() for r in conn.execute(
        f"SELECT clip_id, transcript FROM clips WHERE clip_id IN ({','.join('?' * len(pool))})",
        [c.clip_id for c in pool])} if pool else {}
    labels = []
    for c in pool:
        words = said.get(c.clip_id, "")
        quote = f' "{words[:50]}{"..." if len(words) > 50 else ""}"' if words else ""
        labels.append((f"{'👍 ' if c.liked else ''}#{c.recording_id} at {clock(c.src_in)} · "
                       f"{c.length:.0f}s · score {c.score:.2f}{quote}", c.clip_id,
                       c.recording_id, c.src_in, c.src_out))
    return labels


def add(conn: sqlite3.Connection, settings: Settings, plan: EditPlan, clip_id: str) -> Change:
    """Put a clip in, just before the finale (or at the end with no teaser)."""
    found = next((c for c in _candidates(conn, settings, plan, quality_bar=False)
                  if c.clip_id == clip_id), None)
    if found is None:
        return Change(plan, "That clip can't be added any more (rated down, used, or gone).")
    if any(s.clip_id == clip_id and s.kind != "teaser" for s in plan.segments):
        return Change(plan, "That clip is already in the video.")
    segment = _segment(found)
    if settings.highlights.ordering == "timeline":
        insert_by_time(conn, plan, segment)
    else:
        has_finale = teaser_index(plan) is not None and clip_indexes(plan)
        spot = len(plan.segments) - 1 if has_finale else len(plan.segments)
        plan.segments.insert(spot, segment)
    plan.source = dict(plan.source or {})
    plan.source["removed"] = [c for c in plan.source.get("removed", []) if c != clip_id]
    log_feedback(conn, "added", plan, segment)
    where = ("in its place in time" if settings.highlights.ordering == "timeline"
             else "just before the finale")
    return Change(plan, f"Added ({segment.length:.0f}s), {where}. The video is now "
                        f"{plan.total_sec / 60:.1f} min.", [segment])


def _times(conn: sqlite3.Connection, plan: EditPlan, extra: Segment | None = None):
    """A sort key for a clip: when its stream was recorded, then where in it."""
    ids = {s.recording_id for s in plan.segments} | ({extra.recording_id} if extra else set())
    when = {r["id"]: recorded_at(r) for r in conn.execute(
        f"SELECT * FROM recordings WHERE id IN ({','.join('?' * len(ids))})", list(ids))}
    far = datetime.max.replace(tzinfo=timezone.utc)
    return lambda s: (when.get(s.recording_id, far), s.src_in)


def _finale(plan: EditPlan) -> int | None:
    """Where the teaser's payoff is: its clip, last. None without a teaser."""
    t = teaser_index(plan)
    clips = clip_indexes(plan)
    if t is None or not clips or plan.segments[clips[-1]].clip_id != plan.segments[t].clip_id:
        return None
    return clips[-1]


def insert_by_time(conn: sqlite3.Connection, plan: EditPlan, segment: Segment) -> None:
    """Put a clip where it happened in the story: after the teaser, before the finale."""
    key = _times(conn, plan, segment)
    finale = _finale(plan)
    spot = finale if finale is not None else len(plan.segments)
    for n in clip_indexes(plan):
        if n != finale and key(plan.segments[n]) > key(segment):
            spot = min(spot, n)
            break
    plan.segments.insert(spot, segment)


def sort_by_time(conn: sqlite3.Connection, plan: EditPlan) -> Change:
    """Teaser first, the clips as they happened, the teaser's clip saved for last."""
    key = _times(conn, plan)
    t = teaser_index(plan)
    finale = _finale(plan)
    teaser = [plan.segments[t]] if t is not None else []
    last = [plan.segments[finale]] if finale is not None else []
    middle = sorted((plan.segments[n] for n in clip_indexes(plan) if n != finale), key=key)
    plan.segments[:] = [*teaser, *middle, *last]
    log_feedback(conn, "sorted_by_time", plan, None)
    return Change(plan, "In the order it happened" + (", the teaser's clip saved for the end."
                                                       if last else "."))


def move_to(conn: sqlite3.Connection, plan: EditPlan, index: int, position: int) -> Change:
    """Move a clip to row ``position`` (as numbered in the list). The teaser stays first."""
    clips = clip_indexes(plan)
    if index not in clips:
        return Change(plan, "The teaser always opens the video. Move the clips around it.")
    target = min(max(position - 1, clips[0]), clips[-1])
    if target == index:
        return Change(plan, f"It's already #{index + 1}.")
    segment = plan.segments.pop(index)
    plan.segments.insert(target, segment)
    log_feedback(conn, "reordered", plan, segment, to=target + 1)
    return Change(plan, f"Moved to #{target + 1}.")


# --- Adjusting a cut (brought forward from Phase 2D, the creator's ask on 10 Oct) ----------

# A saved edge moves at most this far to land between two words.
SNAP_SEC = 0.5
SHORTEST_SEC = 2.0


def _snap(t: float, words, starts: list[float], bounds: list[float], outward: int) -> float:
    """``t``, or the nearest gap between words within SNAP_SEC if ``t`` is mid-word."""
    from ..analysis.clips import nearest_bound, word_at

    if not word_at(t, words, starts):
        return t
    moved = nearest_bound(bounds, t, t - SNAP_SEC, t + SNAP_SEC, outward=outward)
    return moved if abs(moved - t) <= SNAP_SEC else t


def adjust(conn: sqlite3.Connection, settings: Settings, plan: EditPlan, index: int,
           start: float, end: float) -> Change:
    """Give one piece of a plan a new start and end in its recording.

    Anywhere in the recording, not only inside the clip AI-Editor cut: the
    point is to win back what was cut off. Each edge moves at most half a
    second to land between two words (the creator's choice). The clip in the
    library takes the new cut too, so the next video with that moment gets it.
    """
    from ..analysis.clips import load_words, realistic, word_boundaries

    segment = plan.segments[index]
    row = conn.execute("SELECT duration_sec FROM recordings WHERE id = ?",
                       (segment.recording_id,)).fetchone()
    duration = float(row["duration_sec"] or 0) if row else end
    start, end = max(0.0, float(start)), min(duration, float(end))
    if end - start < SHORTEST_SEC:
        return Change(plan, f"The end must be at least {SHORTEST_SEC:.0f} seconds after the start.")
    longest = settings.shorts.max_length_sec
    if plan.recipe == "shorts" and end - start > longest + 0.01:
        return Change(plan, f"That's {end - start:.0f} seconds: a Short can be at most "
                            f"{longest:.0f}. Move the start later or the end earlier.")
    words = realistic(load_words(conn, segment.recording_id))
    starts, bounds = [w.start for w in words], word_boundaries(words)
    snapped_start = _snap(start, words, starts, bounds, outward=-1)
    snapped_end = _snap(end, words, starts, bounds, outward=+1)
    if snapped_end - snapped_start >= SHORTEST_SEC:
        start, end = snapped_start, snapped_end
    before = (segment.src_in, segment.src_out)
    plan.segments[index] = replace(segment, src_in=round(start, 3), src_out=round(end, 3))
    if plan.recipe == "shorts":
        plan.target_sec = sum(s.length for s in plan.segments)
    log_feedback(conn, "adjusted", plan, segment, before=list(before), after=[start, end])

    if segment.clip_id and segment.kind != "teaser":
        clip = conn.execute("SELECT signals_json FROM clips WHERE clip_id = ?",
                            (segment.clip_id,)).fetchone()
        if clip is not None:
            summary = json.loads(clip["signals_json"] or "{}")
            summary["adjusted"] = True
            said = " ".join(w.text for w in words if w.start >= start and w.end <= end)
            conn.execute("UPDATE clips SET start_sec = ?, end_sec = ?, signals_json = ?, "
                         "transcript = ? WHERE clip_id = ?",
                         (round(start, 3), round(end, 3), json.dumps(summary), said,
                          segment.clip_id))
            conn.commit()

    what = "The teaser" if segment.kind == "teaser" else f"Clip {index + 1}"
    return Change(plan, f"{what} now runs {clock(start)}-{clock(end)} in the recording "
                        f"({end - start:.0f} s; it was {clock(before[0])}-{clock(before[1])}). "
                        "Make a quick preview to watch it in the video.")
