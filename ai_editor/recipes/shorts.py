"""Recipe C: Shorts for YouTube, TikTok and Reels (spec 7.6).

Up to five suggestions per stream (the creator's choice, 2026-10-04), each
its own plan, so each can be reviewed, changed and rendered on its own:

1. Every moment the creator marked as Short-worthy while live (Numpad -).
2. League's big moments, from the game's own events (Phase 2E-2): your
   multikills, your team's aces and steals.
3. Clips they gave a 👍 that the AI says make sense on their own.
4. The AI's best clips that make sense on their own (spec: "the LLM checks
   that the clip makes sense without context").

A recording the AI hasn't rated falls back to the best-scoring clips, with a
note: the stand-alone check is what makes a good Short.

Each Short is the clip cut down to its moment, with clean edges: a few
seconds before it (straight into the action, the spec's "hook in the first
1-2 seconds"), 15-60 seconds long. Never a 👎 moment, never "BRB", never a
moment already in another Short. Being in a highlight video doesn't count:
Shorts are how viewers find the long videos.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from ..analysis.ai_rating import notes_for
from ..analysis.captions import clock
from ..config import Settings
from ..analysis.clips import load_words, realistic, word_boundaries
from .highlights import Candidate, gather, has_video, inside
from .plan import DRAFT, EditPlan, Segment, new_plan_id, save_plan, used_in

# Shorter than this share of shorts.min_length_sec (a clip that can't grow
# without crossing a scene change or a word), and it isn't suggested.
SHORTEST_SHARE = 0.67


@dataclass
class Pick:
    candidate: Candidate
    why: str              # "marked" | "league" | "liked" | "ai" | "score"
    summary: str = ""
    rating: float | None = None


@dataclass
class ShortsResult:
    plans: list[EditPlan] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def short_settings(settings: Settings) -> Settings:
    """The recipe's settings with Shorts' lengths in place of a highlight video's."""
    s = settings.shorts
    return settings.model_copy(update={
        "highlights": settings.highlights.model_copy(update={
            # Room to finish a sentence without passing the limit (within_limit).
            "lead_in_sec": s.lead_in_sec,
            "max_clip_sec": max(s.min_length_sec + 1,
                                s.max_length_sec - settings.clips.end_extend_sec)}),
        "clips": settings.clips.model_copy(update={
            "tail_sec": s.tail_sec, "min_length_sec": s.min_length_sec}),
    })


def choose(candidates: list[Candidate], clips: dict[str, sqlite3.Row], notes: dict,
           settings: Settings) -> tuple[list[Pick], bool]:
    """The Shorts to suggest, best first, and whether the AI's verdicts were there."""
    s = settings.shorts
    rated = bool(notes)
    tiers: list[tuple[int, float, float, Pick]] = []
    for c in candidates:
        row = clips[c.clip_id]
        if used_in(row["used_in_json"], shorts=True):
            continue  # already a Short
        if c.length < s.min_length_sec * SHORTEST_SHARE:
            continue
        summary = json.loads(row["signals_json"] or "{}")
        note = notes.get(c.clip_id)
        alone = note is not None and note.stands_alone
        rating = note.rating if note else None
        text = note.summary if note else ""
        if "marker_short" in summary:
            tiers.append((0, -(rating or 0), -c.score, Pick(c, "marked", text, rating)))
        elif summary.get("league_big"):
            # A penta speaks for itself: no need for the AI to say it stands alone.
            tiers.append((1, -(rating or 0), -c.score,
                          Pick(c, "league", text or (summary.get("reasons") or [""])[0], rating)))
        elif c.liked and (alone or not rated):
            tiers.append((2, -(rating or 0), -c.score, Pick(c, "liked", text, rating)))
        elif alone or not (s.must_make_sense_alone and rated):
            tiers.append((3, -(rating or 0), -c.score,
                          Pick(c, "ai" if rated else "score", text, rating)))
    chosen: list[Pick] = []
    for *_, pick in sorted(tiers, key=lambda t: t[:3]):
        c = pick.candidate
        if any(p.candidate.recording_id == c.recording_id and p.candidate.src_in < c.src_out
               and c.src_in < p.candidate.src_out for p in chosen):
            continue  # the same moment twice
        # Every marked moment is suggested, even past the usual number; the
        # others only up to it.
        if pick.why != "marked" and len(chosen) >= s.per_recording:
            break
        chosen.append(pick)
    return chosen, rated


GONE = ("Its video was deleted (or moved), so a finished video can't be made from it. Its clips and everything you taught AI-Editor about them are kept.")

# A mark pressed a little after its clip ends is still about it.
MARK_AFTER_SEC = 10.0


def short_presses(conn: sqlite3.Connection, recording_id: int) -> list[float]:
    """When you pressed Mark Short-worthy (Numpad -), in the recording's time."""
    return [r[0] for r in conn.execute(
        "SELECT recording_time_sec FROM companion_events WHERE recording_id = ? AND "
        "event_type = 'marker_short' AND recording_time_sec IS NOT NULL "
        "ORDER BY recording_time_sec", (recording_id,))]


def around_mark(c: Candidate, presses: list[float], settings: Settings, words: list,
                bounds: list[float], starts: list[float]) -> None:
    """A Short from your mark: the good bit is before the press. From
    before_mark_sec before it to after_mark_sec after it, inside the library
    clip, never mid-word. Before 10 Oct these ran ~20 s past the press, and
    the 60 s limit then pushed the start past the build-up."""
    from ..analysis.clips import nearest_bound, word_at

    s = settings.shorts
    pressed = [p for p in presses if c.start <= p <= c.end + MARK_AFTER_SEC]
    if not pressed:
        return
    press = pressed[-1]
    start = max(c.start, press - s.before_mark_sec)
    end = min(c.end, press + s.after_mark_sec)
    if end - start < s.min_length_sec:
        start = max(c.start, end - s.min_length_sec)
    if word_at(start, words, starts):
        start = nearest_bound(bounds, start, c.start, end, outward=-1)
    if word_at(end, words, starts):
        end = nearest_bound(bounds, end, start, c.end, outward=+1)
    c.src_in, c.src_out = start, end


def within_limit(c: Candidate, longest: float, words: list, bounds: list[float],
                 starts: list[float]) -> None:
    """No Short over the limit (60 s): never ending mid-sentence can stretch a
    clip past it. The start moves later, so the payoff at the end stays."""
    if c.length > longest:
        c.src_in, c.src_out = inside(c.src_in, c.src_out, c.src_out - longest, c.src_out,
                                     bounds, words, starts)


WHY = {"marked": "you marked it as a Short", "league": "it's a big League moment",
       "liked": "you gave it a 👍",
       "ai": "the AI says it works on its own", "score": "it scored well"}


def build_shorts(conn: sqlite3.Connection, settings: Settings, recording_id: int) -> ShortsResult:
    """Suggest this recording's Shorts as draft plans, replacing earlier drafts."""
    row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    result = ShortsResult()
    if row is None or row["analysis_status"] != "complete":
        result.notes.append(f"Recording #{recording_id} isn't analysed yet.")
        return result
    if not has_video(row):
        result.notes.append(f"Recording #{recording_id}: " + GONE)
        return result
    candidates = gather(conn, short_settings(settings), [row], quality_bar=False, reuse=True)
    words = realistic(load_words(conn, recording_id))
    bounds, starts = word_boundaries(words), [w.start for w in words]
    clips = {c["clip_id"]: c for c in conn.execute(
        "SELECT * FROM clips WHERE recording_id = ?", (recording_id,))}
    presses = short_presses(conn, recording_id)
    for c in candidates:
        summary = json.loads(clips[c.clip_id]["signals_json"] or "{}")
        if "marker_short" in summary and not summary.get("adjusted"):
            around_mark(c, presses, settings, words, bounds, starts)
        within_limit(c, settings.shorts.max_length_sec, words, bounds, starts)
    notes = notes_for(conn, recording_id, list(clips.values()))
    picks, rated = choose(candidates, clips, notes, settings)
    discard_short_drafts(conn, recording_id)
    preset = settings.render.presets[settings.shorts.preset]
    for pick in picks:
        c = pick.candidate
        game = c.game or row["game"]
        plan = EditPlan(
            plan_id=new_plan_id(conn, "shorts", game),
            recipe="shorts",
            title=f"Short: {pick.summary or 'moment at ' + clock(c.src_in)}",
            game=game,
            target_sec=c.length,
            segments=[Segment(recording_id, round(c.src_in, 3), round(c.src_out, 3), kind="clip",
                              clip_id=c.clip_id, score=c.score, reasons=c.reasons, game=game)],
            output=preset.model_dump(),
        )
        plan.source = {"recording_ids": [recording_id], "game": game, "why": pick.why,
                       "layout": settings.shorts.layout_for(game), "rating": pick.rating}
        plan.notes.append(f"Suggested because {WHY[pick.why]}.")
        if game in settings.shorts.spoiler_check_games:
            # Spec 7.6: story Shorts are flagged for review before they go out.
            plan.notes.append("Story game: check it doesn't give away the plot before you "
                              "upload it.")
        save_plan(conn, plan)
        result.plans.append(plan)
    if not rated:
        result.notes.append("The AI hasn't rated this recording's clips, so these are simply the "
                            "best-scoring ones. Rate with AI (Clips) picks moments that make "
                            "sense on their own.")
    if not picks:
        result.notes.append("No moment here makes a Short: none that make sense on their own "
                            "and aren't already a Short. Mark Short-worthy moments with "
                            "Numpad - while live.")
    return result


def discard_short_drafts(conn: sqlite3.Connection, recording_id: int) -> int:
    """Suggesting again replaces the last suggestions, not the Shorts already rendered."""
    doomed = [r["plan_id"] for r in conn.execute(
        "SELECT plan_id, recording_ids_json FROM edit_plans WHERE recipe = 'shorts' AND status = ?",
        (DRAFT,)) if json.loads(r["recording_ids_json"]) == [recording_id]]
    conn.executemany("DELETE FROM edit_plans WHERE plan_id = ?", [(p,) for p in doomed])
    conn.commit()
    return len(doomed)
