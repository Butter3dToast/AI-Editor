"""The Part Planner: moving where a Let's Play's parts end (Phase 2F-2).

What the creator chose (2026-10-11): drag the split points on Review's parts
bar; each snaps to the nearest safe break (a loading screen, a pause in
talking, where a quest ends...), never mid-word or mid-cutscene. Double-click
the bar to add a split, the x on a split to remove it. Undo covers it all.

The safe breaks are the ones the recipe found when it made the plan
(parts.break_points), kept with the plan by their time in the recording, so
moving a split needs no analysis. A part is never longer than the hard
maximum (60 minutes) or shorter than MIN_PART_SEC.
"""

from __future__ import annotations

import sqlite3

from ..analysis.captions import clock
from ..config import Settings
from .parts import Break, range_pieces, to_output
from .plan import EditPlan, Segment
from .review import Change

# Shorter than this isn't a part.
MIN_PART_SEC = 120.0
# A split moves to the nearest safe break this close to where it was dropped.
SNAP_WITHIN_SEC = 300.0
KINDS = {"loading": "a loading screen", "menu": "a menu or map", "silence": "a quiet stretch",
         "stream_screen": "a starting/BRB screen", "pause": "a pause in talking"}


def pieces_of(plan: EditPlan) -> list[tuple[float, float]]:
    """The kept stretches of the recording, in order, whichever part they're in."""
    pieces: list[list[float]] = []
    for s in plan.segments:
        if pieces and abs(pieces[-1][1] - s.src_in) < 0.01:
            pieces[-1][1] = s.src_out
        else:
            pieces.append([s.src_in, s.src_out])
    return [(a, b) for a, b in pieces]


def splits_of(plan: EditPlan) -> list[float]:
    """Where each part but the last ends, in seconds into the trimmed episode."""
    out, at, current = [], 0.0, None
    for s in plan.segments:
        if current is not None and s.part != current:
            out.append(at)
        current = s.part
        at += s.length
    return out


def total_of(plan: EditPlan) -> float:
    return sum(s.length for s in plan.segments)


def stored(breaks: list[Break]) -> list[list]:
    """Safe breaks, compact, by their time in the recording (kept in plan.source)."""
    return [[round(b.source, 2), b.kind, round(b.cost, 2), b.hook, b.story, b.mission]
            for b in breaks if b.kind != "forced"]


def _rebuild(conn: sqlite3.Connection, settings: Settings, plan: EditPlan) -> list[list]:
    """A plan made before the planner: find its safe breaks again (seconds)."""
    from ..analysis.quests import story_of
    from .letsplay import kept_pieces, load_episode, trim
    from .parts import break_points

    row = conn.execute("SELECT * FROM recordings WHERE id = ?",
                       (plan.segments[0].recording_id,)).fetchone()
    episode = load_episode(conn, settings, row)
    cuts = trim(conn, settings, row, episode)
    pieces = kept_pieces(cuts, float(row["duration_sec"]))
    return stored(break_points(episode, cuts, pieces, settings, story_of(conn, row["id"])))


def safe_breaks(conn: sqlite3.Connection, settings: Settings, plan: EditPlan) -> list[Break]:
    """Every safe place a part can end, at its time in this plan's trimmed episode."""
    plan.source = dict(plan.source or {})
    if "breaks" not in plan.source:
        plan.source["breaks"] = _rebuild(conn, settings, plan)
    pieces = pieces_of(plan)
    found = []
    for source, kind, cost, hook, story, mission in plan.source["breaks"]:
        at = to_output(pieces, source)
        if at is not None:
            found.append(Break(at, source, cost, kind, hook, mission, story))
    return sorted(found, key=lambda b: b.at)


def _snap(breaks: list[Break], at: float, lo: float, hi: float) -> Break | None:
    """The safe break nearest ``at`` that leaves both neighbours a real part."""
    near = [b for b in breaks if lo + MIN_PART_SEC <= b.at <= hi - MIN_PART_SEC
            and abs(b.at - at) <= SNAP_WITHIN_SEC]
    return min(near, key=lambda b: (abs(b.at - at), b.cost)) if near else None


def _info(b: Break | None) -> dict:
    if b is None:
        return {"ends_on": "end", "hook": False, "story": None, "mission": None, "flagged": False}
    return {"ends_on": b.kind, "hook": b.hook, "story": b.story, "mission": b.mission,
            "flagged": b.mission is not None}


def _regroup(plan: EditPlan, edges: list[float], infos: list[dict]) -> None:
    """Parts again, from where each ends (``edges``) and what it ends on (``infos``)."""
    pieces = pieces_of(plan)
    total = sum(b - a for a, b in pieces)
    first = plan.segments[0]
    bounds = [0.0, *edges, total]
    segments = []
    for number, (a, b) in enumerate(zip(bounds, bounds[1:]), start=1):
        segments += [Segment(first.recording_id, round(x, 3), round(y, 3), kind="piece",
                             game=first.game, part=number) for x, y in range_pieces(pieces, a, b)]
    plan.segments = segments
    plan.source["parts"] = [{"number": n, **info} for n, info in enumerate(infos, start=1)]


def _too_long(settings: Settings, length: float) -> bool:
    return length > settings.lets_play.story_extension_hard_max_min * 60 + 0.5


def _infos(plan: EditPlan) -> list[dict]:
    known = {p["number"]: p for p in (plan.source or {}).get("parts", [])}
    count = len(splits_of(plan)) + 1
    return [{k: v for k, v in known.get(n, _info(None)).items() if k != "number"}
            for n in range(1, count + 1)]


def _said(b: Break) -> str:
    what = KINDS.get(b.kind, b.kind)
    if b.story:
        what += " · " + {"quest end": "the quest ends", "time of day": "the time of day changes"
                         }.get(b.story, b.story)
    if b.mission:
        what += f" · ⚠ in the middle of \"{b.mission}\""
    return what


def move_split(conn: sqlite3.Connection, settings: Settings, plan: EditPlan, index: int,
               at: float) -> Change:
    """Part ``index + 1`` ends nearer ``at`` (seconds into the trimmed episode)."""
    edges = splits_of(plan)
    if not 0 <= index < len(edges):
        return Change(plan, "That split has gone: the parts changed. Try again.")
    total = total_of(plan)
    lo = edges[index - 1] if index > 0 else 0.0
    hi = edges[index + 1] if index + 1 < len(edges) else total
    found = _snap(safe_breaks(conn, settings, plan), at, lo, hi)
    if found is None:
        return Change(plan, f"No safe place to end a part near {clock(at)}: a part can't end "
                            "mid-talk or mid-cutscene, nor leave a part under 2 minutes.")
    if abs(found.at - edges[index]) < 0.5:
        return Change(plan, f"Part {index + 1} already ends there ({clock(found.at)}).")
    if _too_long(settings, found.at - lo) or _too_long(settings, hi - found.at):
        return Change(plan, "That would make a part longer than "
                            f"{settings.lets_play.story_extension_hard_max_min:.0f} minutes.")
    infos = _infos(plan)
    infos[index] = _info(found)
    edges[index] = found.at
    _regroup(plan, edges, infos)
    return Change(plan, f"Part {index + 1} now ends at {clock(found.at)}, on {_said(found)}: "
                        f"parts {index + 1} and {index + 2} are {clock(found.at - lo)} and "
                        f"{clock(hi - found.at)}.")


def add_split(conn: sqlite3.Connection, settings: Settings, plan: EditPlan, at: float) -> Change:
    """A new split near ``at``: one part becomes two."""
    edges = splits_of(plan)
    total = total_of(plan)
    bounds = [0.0, *edges, total]
    part = next((n for n in range(len(bounds) - 1) if bounds[n] <= at < bounds[n + 1]),
                len(bounds) - 2)
    found = _snap(safe_breaks(conn, settings, plan), at, bounds[part], bounds[part + 1])
    if found is None:
        return Change(plan, f"No safe place to split near {clock(at)} (parts need 2 minutes "
                            "at least, and never end mid-talk or mid-cutscene).")
    infos = _infos(plan)
    infos.insert(part, _info(found))
    edges.insert(part, found.at)
    _regroup(plan, edges, infos)
    return Change(plan, f"Part {part + 1} split at {clock(found.at)}, on {_said(found)}: "
                        f"{len(edges) + 1} parts now.")


def remove_split(settings: Settings, plan: EditPlan, index: int) -> Change:
    """Parts ``index + 1`` and ``index + 2`` become one."""
    edges = splits_of(plan)
    if not 0 <= index < len(edges):
        return Change(plan, "That split has gone: the parts changed. Try again.")
    total = total_of(plan)
    lo = edges[index - 1] if index > 0 else 0.0
    hi = edges[index + 1] if index + 1 < len(edges) else total
    if _too_long(settings, hi - lo):
        return Change(plan, f"Joined, parts {index + 1} and {index + 2} would be "
                            f"{clock(hi - lo)}: a part can be "
                            f"{settings.lets_play.story_extension_hard_max_min:.0f} minutes at most.")
    infos = _infos(plan)
    del infos[index]
    del edges[index]
    _regroup(plan, edges, infos)
    return Change(plan, f"Parts {index + 1} and {index + 2} joined: {clock(hi - lo)}, "
                        f"{len(edges) + 1} parts now.")
