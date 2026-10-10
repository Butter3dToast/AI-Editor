"""Recipe B: a highlight compilation (spec section 7.6).

    1. Gather the game's unused clips from every analysed recording, keeping
       only those over the quality bar -- plus any you pinned or marked.
    2. Fill the target length. When one stream runs out of good clips the
       next one continues ("4 min from the previous and 6 min from the next"),
       using as many streams as it takes. Nothing weak is added to fill time:
       a short video is better than a padded one.
    3. Trim each clip down to its moment, still never mid-word.
    4. Order it: a teaser of the best moment first, then a strong opener,
       alternating intensity through the middle, and the best moment in full
       at the end, paying off the teaser.

Game-aware trimming (Wardogs redeploy screens, League champion select) needs
the game profiles in Phase 2.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..analysis.ai_rating import scores_for
from ..analysis.captions import Word
from ..analysis.clips import (
    action_signal,
    clean_ends,
    fit_edges,
    sentence_ends,
    load_words,
    nearest_bound,
    realistic,
    refresh_clips,
    word_at,
    word_boundaries,
)
from ..analysis.hype import dark_seconds, load_signals
from ..analysis.moments import load_signal
from ..analysis.game_events import for_recording
from ..analysis.pipeline import load_scene_cuts
from ..config import Settings
from .plan import EditPlan, Segment, discard_drafts, new_plan_id, save_plan, used_in

# A video counts as on target within this share of the target (spec section 7.6).
TOLERANCE = 0.15
# How much of the teaser comes before the peak of the moment.
TEASER_BEFORE_PEAK = 0.6
# A moment the creator picked for the teaser gets this much either side, so
# it doesn't start or stop abruptly.
TEASER_PAD_SEC = 1.0
# How far a clip stays from an OBS scene change into "BRB" or "Ending Screen".
SCENE_MARGIN_SEC = 0.5


@dataclass
class Candidate:
    clip_id: str
    recording_id: int
    start: float
    end: float
    score: float
    peak: int
    core: tuple[int, int]
    reasons: list[str]
    recorded: datetime
    must_include: bool  # pinned, or marked with the Stream Companion
    game: str | None = None
    src_in: float = 0.0
    src_out: float = 0.0
    reaction: float = 0.0  # how strongly the creator reacts (see reaction_strength)
    marked: bool = False  # marked with the Stream Companion's hotkey
    liked: bool = False  # thumbs up in the Clips tab

    @property
    def length(self) -> float:
        return self.src_out - self.src_in


@dataclass
class HighlightResult:
    plan: EditPlan
    available_sec: float  # all the good, unused material there was
    recordings_used: int
    recordings_searched: int


def recorded_at(row: sqlite3.Row) -> datetime:
    """When a recording was made: Twitch's date, else the file's, else the import."""
    if row["recorded_at"]:
        try:
            return datetime.fromisoformat(row["recorded_at"]).astimezone(timezone.utc)
        except ValueError:
            pass
    path = Path(row["source_file"])
    if path.exists():
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.fromisoformat(row["imported_at"]).astimezone(timezone.utc)


def has_video(row: sqlite3.Row) -> bool:
    """Whether the recording's own video is still there. The creator deletes
    streams once their videos are made (10 Oct); what AI-Editor learned from
    them stays in the library, but nothing new can be rendered from them."""
    return Path(row["source_file"]).is_file()


def recordings_for(conn: sqlite3.Connection, settings: Settings, *, game: str | None,
                   recording_ids: list[int] | None,
                   need_video: bool = True) -> list[sqlite3.Row]:
    """The recordings a highlight video draws from.

    By number, if given. For one game: recordings of that game, plus any
    where the Stream Companion saw that game's OBS scene (a Wardogs stream
    that turned into Tarkov). Otherwise every stream: all recordings except
    Let's Play episodes (lets_play.games) -- "because we are doing stream
    highlights we are taking all the games that were played". A recording
    whose game isn't known is still a stream, so it is included.

    ``need_video``: leave out recordings whose video was deleted (has_video).
    """
    found = _recordings_for(conn, settings, game=game, recording_ids=recording_ids)
    return [r for r in found if has_video(r)] if need_video else found


def _recordings_for(conn: sqlite3.Connection, settings: Settings, *, game: str | None,
                    recording_ids: list[int] | None) -> list[sqlite3.Row]:
    if recording_ids:
        marks = ",".join("?" * len(recording_ids))
        rows = conn.execute(f"SELECT * FROM recordings WHERE id IN ({marks})", recording_ids)
    elif game:
        rows = conn.execute(
            "SELECT * FROM recordings WHERE game = ? OR id IN (SELECT recording_id FROM "
            "companion_events WHERE event_type = 'obs_scene' AND payload_json LIKE ?)",
            (game, f'%"game": "{game}"%'))
    else:
        episodes = [g.lower() for g in settings.lets_play.games]
        rows = conn.execute("SELECT * FROM recordings")
        return [r for r in rows.fetchall()
                if r["analysis_status"] == "complete" and (r["game"] or "").lower() not in episodes]
    return [r for r in rows.fetchall() if r["analysis_status"] == "complete"]


def gather(conn: sqlite3.Connection, settings: Settings,
           recordings: list[sqlite3.Row], *, game: str | None = None, refresh: bool = True,
           allow: set[str] | frozenset[str] = frozenset(),
           quality_bar: bool = True, reuse: bool = False) -> list[Candidate]:
    """Every clip that may go into the video, trimmed to its moment.

    With ``game``, only clips from that game: each clip knows its own game
    when the Companion logged the OBS scenes, else it takes its recording's.
    ``refresh=False`` skips re-cutting the clips (Review, where they were cut
    moments ago). ``allow``: clip ids to keep even though a plan uses them --
    the plan being reviewed, once it has been approved. ``quality_bar=False``
    keeps clips under the bar too: what the creator may add in Review.
    ``reuse``: clips already in a rendered video may come again (one video's
    choice, like highlights.allow_reused_clips for all of them).

    A clip you gave a thumbs up always goes in, like one you marked: "the
    thumbs up should mean that it should be in the video for review" (the
    creator, 2026-10-03). A thumbs down always keeps it out.
    """
    from ..companion.link import game_spans, game_timeline, scene_span

    h = settings.highlights
    found: list[Candidate] = []
    for row in recordings:
        if refresh:
            refresh_clips(conn, settings, row)  # a couple of seconds; always current
        words = realistic(load_words(conn, row["id"]))
        # A League match starting or ending is like a scene change (game_events.py).
        cuts = sorted(load_scene_cuts(settings, row)
                      + for_recording(conn, row["id"], int(row["duration_sec"] or 0)).cuts)
        score = load_signal(conn, row["id"], "hype")
        signals = load_signals(conn, row["id"], int(row["duration_sec"]))
        action = action_signal(signals)
        dark = dark_seconds(signals, int(row["duration_sec"]), settings.scoring.dark_level,
                            settings.scoring.dark_min_sec)
        timeline = game_timeline(conn, row["id"])
        bounds = word_boundaries(words)
        starts = [w.start for w in words]
        when = recorded_at(row)
        clips = conn.execute("SELECT * FROM clips WHERE recording_id = ?", (row["id"],)).fetchall()
        # A thumbs-down covers the moment, not just that clip: a re-cut clip
        # starting a little earlier must not bring it back.
        rejected = [(c["start_sec"], c["end_sec"]) for c in clips
                    if c["user_rating"] is not None and c["user_rating"] < 0]
        # The local AI's rating counts for llm.rating_weight of the score (0 by default).
        scores = scores_for(conn, settings, row["id"], clips)
        for clip in clips:
            if used_in(clip["used_in_json"], shorts=False) and not (h.allow_reused_clips or reuse) \
                    and clip["clip_id"] not in allow:
                continue
            summary = json.loads(clip["signals_json"] or "{}")
            marked = "marker" in summary or "marker_short" in summary
            liked = (clip["user_rating"] or 0) > 0
            must = liked or (h.always_include_pinned and bool(clip["pinned"])) or \
                (h.always_include_markers and marked)
            if quality_bar and scores[clip["clip_id"]] < h.min_clip_score and not must:
                continue
            if any(a < clip["end_sec"] and clip["start_sec"] < b for a, b in rejected):
                continue  # thumbs down
            clip_game = summary.get("game") or row["game"]
            if game and clip_game != game:
                continue
            core = tuple(summary.get("core") or (int(clip["start_sec"]), int(clip["end_sec"])))
            peak = int(summary.get("peak", (core[0] + core[1]) // 2))
            candidate = Candidate(
                clip["clip_id"], row["id"], clip["start_sec"], clip["end_sec"],
                scores[clip["clip_id"]], peak, (int(core[0]), int(core[1])), summary.get("reasons", []), when, must,
                game=clip_game, marked=marked, liked=liked,
            )
            adjusted = bool(summary.get("adjusted"))
            if adjusted:
                # You set this clip's start and end yourself in Review: used as it is.
                candidate.src_in, candidate.src_out = clip["start_sec"], clip["end_sec"]
            else:
                candidate.src_in, candidate.src_out = trim(
                    candidate, words, cuts, float(row["duration_sec"]), score, settings,
                    action=action, dark=dark)
            if timeline and not adjusted:
                # Never into "BRB" or the ending screen: the clip stays in the
                # scene its moment is in, ending at the last word before the switch
                # (the first League stream's last marker ran 3 s into "Ending Screen").
                start, end, on_screen = scene_span(timeline, peak, float(row["duration_sec"]))
                if on_screen is None:
                    # The moment is on a non-game screen (a marker pressed just after
                    # switching to "Ending Screen"): keep the gameplay it overlaps.
                    overlaps = [(min(e, candidate.src_out) - max(s, candidate.src_in), s, e)
                                for s, e, _ in game_spans(timeline, float(row["duration_sec"]))
                                if min(e, candidate.src_out) > max(s, candidate.src_in)]
                    if overlaps:
                        _, start, end = max(overlaps)
                    elif not must:
                        continue  # a moment during "BRB" isn't a highlight
                # Half a second clear of the switch: it's logged a moment after it
                # happens, and OBS may already be fading to the next scene.
                duration = float(row["duration_sec"])
                start = start + SCENE_MARGIN_SEC if start > 0 else start
                end = end - SCENE_MARGIN_SEC if end < duration else end
                candidate.src_in, candidate.src_out = inside(
                    candidate.src_in, candidate.src_out, start, end, bounds, words, starts)
                if candidate.length < 3:
                    continue
            candidate.reaction = reaction_strength(signals, candidate.src_in, candidate.src_out,
                                                   settings.scoring.zscore_full_scale)
            found.append(candidate)
    return found


def inside(src_in: float, src_out: float, start: float, end: float, bounds: list[float],
           words: list[Word], starts: list[float]) -> tuple[float, float]:
    """A clip pulled in to fit between ``start`` and ``end``, still never mid-word."""
    if src_in < start:
        src_in = start
        if word_at(src_in, words, starts):
            src_in = nearest_bound(bounds, src_in, src_in, src_out, outward=+1)
    if src_out > end:
        src_out = end
        if word_at(src_out, words, starts):
            src_out = nearest_bound(bounds, src_out, src_in, src_out, outward=-1)
    return src_in, src_out


def trim(c: Candidate, words: list[Word], cuts: list[float], duration: float,
         score: np.ndarray, settings: Settings,
         action: np.ndarray | None = None, dark: np.ndarray | None = None) -> tuple[float, float]:
    """The clip cut down to its moment, with the same clean-edge rules."""
    h = settings.highlights
    tighter = settings.clips.model_copy(update={
        "lead_in_sec": h.lead_in_sec,
        "max_length_sec": h.max_clip_sec,
        "min_length_sec": min(settings.clips.min_length_sec, h.max_clip_sec - 1),
    })
    start, end = fit_edges(c.core, c.peak, words=words, cuts=cuts, duration=duration,
                           settings=tighter, score=score if score.size else None,
                           action=action, dark=dark)
    # Never outside the library clip, whose edges are clean too.
    return max(start, c.start), min(end, c.end)


def select(candidates: list[Candidate], target_sec: float, fill_order: str) -> list[Candidate]:
    """Fill the target: your picks first, then clips in fill order."""
    chosen = [c for c in candidates if c.must_include]
    rest = [c for c in candidates if not c.must_include]
    return chosen + top_up(rest, sum(c.length for c in chosen), target_sec, fill_order)


def top_up(candidates: list[Candidate], total: float, target_sec: float,
           fill_order: str) -> list[Candidate]:
    """Clips to add, in fill order, until ``total`` seconds reaches the target.

    The target is a floor: "about 10 min, never below; above is fine" (the
    creator, 2026-10-03). Clips that fit within the tolerance go first; if
    that still falls short, the next ones go in anyway and it runs over.
    Only clips over the quality bar are ever candidates, so it never pads.
    """
    if fill_order == "oldest_first":
        # Use up one stream's good clips, best first, before moving to the next.
        ordered = sorted(candidates, key=lambda c: (c.recorded, -c.score))
    else:
        ordered = sorted(candidates, key=lambda c: -c.score)
    limit = target_sec * (1 + TOLERANCE)
    added: list[Candidate] = []
    for candidate in ordered:
        if total >= target_sec:
            break
        if total + candidate.length <= limit:
            added.append(candidate)
            total += candidate.length
    for candidate in ordered:
        if total >= target_sec:
            break
        if candidate not in added:
            added.append(candidate)
            total += candidate.length
    return added


REACTION_WINDOW_SEC = 10


def reaction_strength(signals: dict[str, np.ndarray], start: float, end: float,
                      zscore_full_scale: float) -> float:
    """The creator's strongest 10 seconds of reacting: laughing, getting loud, shouting.

    Laughter counts double because the sound model hears it faintly.
    """
    a, b = int(start), int(np.ceil(end))
    length = max(0, b - a)
    if not length:
        return 0.0
    zero = np.zeros(length, dtype=np.float32)

    def part(name: str) -> np.ndarray:
        values = signals.get(name)
        return zero if values is None else np.resize(values[a:b], length)

    reacting = np.maximum.reduce([
        np.clip(part("laughter") * 2, 0, 1),
        np.clip(part("energy_z") / zscore_full_scale, 0, 1),
        part("shout"), part("scream"),
    ])
    window = min(REACTION_WINDOW_SEC, length)
    return float(np.convolve(reacting, np.ones(window) / window, mode="valid").max())


def best_of(chosen: list[Candidate], pick: str | None = None) -> Candidate:
    """The one moment the teaser shows and the video ends on.

    In order: the clip you picked (``pick``, a clip id); else one you marked
    with the Stream Companion; else where you react most. Sound can't tell
    what's funny: the creator's favourite teaser ("I love how he pulled the
    Zap side at you") is funny for what's said, and scored low on reaction.

    Measured on the creator's first 10-minute Wardogs highlight: they named
    the helicopter clip "probs the funniest ... maybe this should actually be
    the teaser", and it had by far the strongest reaction (0.81 against 0.59
    for the next). The top-scoring clip used before was a mortar and some
    laughter (0.34), "not really anything good to be considered a teaser".
    Ties go to the higher score, so the teaser and the finale always agree.
    """
    picked = [c for c in chosen if c.clip_id == pick]
    if picked:
        return picked[0]
    pool = [c for c in chosen if c.marked] or chosen
    return max(pool, key=lambda c: (round(c.reaction, 2), c.score, c.core[1] - c.core[0],
                                    c.clip_id))


def order(chosen: list[Candidate], ordering: str, pick: str | None = None) -> list[Candidate]:
    """The order of the clips; ``ordering`` as in settings (highlights.ordering).

    timeline: as it happened, oldest stream first, with the best moment (the
    teaser's) saved for the end -- how the creator laid out their own video.
    balanced: strong opener, alternating intensity, best moment last (spec 7.6).
    """
    if ordering == "chronological":
        return sorted(chosen, key=lambda c: (c.recorded, c.src_in))
    finale = best_of(chosen, pick) if chosen else None
    if ordering == "timeline":
        return [*sorted((c for c in chosen if c is not finale),
                        key=lambda c: (c.recorded, c.src_in)), *([finale] if finale else [])]
    ranked = [finale] + sorted((c for c in chosen if c is not finale),
                               key=lambda c: c.score, reverse=True) if finale else []
    if ordering == "best_last" or len(ranked) < 3:
        return list(reversed(ranked))
    finale, opener, middle = ranked[0], ranked[1], ranked[2:]
    # Alternate: a strong one, then a calmer one, so the video breathes.
    alternating: list[Candidate] = []
    high, low = 0, len(middle) - 1
    take_high = False  # the opener was strong; follow it with a breather
    while high <= low:
        if take_high:
            alternating.append(middle[high])
            high += 1
        else:
            alternating.append(middle[low])
            low -= 1
        take_high = not take_high
    return [opener, *alternating, finale]


def teaser(best: Candidate, words: list[Word], seconds: float, *,
           shortest: float = 5.0, longest: float = 15.0, end_pause: float = 1.0) -> tuple[float, float]:
    """A few seconds of the best moment, to open the video.

    Ends where the creator stops talking, anywhere from ``shortest`` to
    ``longest`` seconds in. Cutting at exactly ``seconds`` ended the first
    Wardogs teaser on "Bomb them, Trin, bomb" -- mid-phrase. Tried in order:
    a real pause, a full stop, then simply between two words.
    """
    start = max(best.src_in, best.peak - seconds * TEASER_BEFORE_PEAK)
    bounds = word_boundaries(words)
    starts = [w.start for w in words]
    if word_at(start, words, starts):
        start = nearest_bound(bounds, start, best.src_in, best.peak, outward=-1)

    wanted = start + seconds
    low = max(start + shortest, min(best.peak + 1.0, start + longest))
    high = min(best.src_out, start + longest)
    for points in (clean_ends(words, [], end_pause), sentence_ends(words), bounds):
        inside = [p for p in points if low <= p <= high]
        if inside:
            return start, min(inside, key=lambda p: abs(p - wanted))
    end = min(best.src_out, wanted)
    if word_at(end, words, starts):
        end = nearest_bound(bounds, end, best.peak, best.src_out, outward=+1)
    return start, end


def teaser_from(moment: tuple[float, float], best: Candidate, words: list[Word], *,
                shortest: float = 5.0, longest: float = 15.0, end_pause: float = 1.0) -> tuple[float, float]:
    """The teaser the creator asked for: their moment, a second either side.

    ``moment`` is in recording time. Given only where it starts (both ends
    the same), it ends the usual way, at a pause 5-15 s in. The second
    either side never starts or stops mid-word.
    """
    a, b = moment
    bounds = word_boundaries(words)
    starts = [w.start for w in words]
    start = max(best.src_in, a - TEASER_PAD_SEC)
    if word_at(start, words, starts):
        start = nearest_bound(bounds, start, best.src_in, a, outward=-1)
    if b <= a:
        return teaser(replace(best, src_in=start, peak=start), words, longest, shortest=shortest,
                      longest=longest, end_pause=end_pause)
    end = min(best.src_out, b + TEASER_PAD_SEC)
    if word_at(end, words, starts):
        end = nearest_bound(bounds, end, b, best.src_out, outward=+1)
    return start, end


def nothing_left_note(conn: sqlite3.Connection, settings: Settings,
                      recordings: list[sqlite3.Row], game: str | None, reuse: bool) -> str:
    """Why there's nothing to put in the video, and what to do about it.

    Usually every good clip is already in a rendered video: rendering uses
    them up so the next video has fresh ones. On 2026-10-04 the creator tried
    to remake a rendered League video with the stream's music and was told
    only "no clips passed the quality bar".
    """
    if not reuse and gather(conn, settings, recordings, game=game, refresh=False, reuse=True):
        used = sorted({p for r in recordings for (u,) in conn.execute(
            "SELECT used_in_json FROM clips WHERE recording_id = ? AND used_in_json IS NOT NULL",
            (r["id"],)) for p in used_in(u, shorts=False)})
        return ("Every good clip from these streams is already in a rendered video ("
                + ", ".join(used) + "). To render that video again with new settings (like "
                "the stream's music), open it in Review and press Render. To make another "
                "video from the same clips, tick 'Use clips already in a video' in Create "
                "video.")
    return ("No clips passed the quality bar. Lower the quality bar in Settings, or analyse "
            "more recordings of this game.")


def short_note(clips_sec: float, target_sec: float, recordings: int) -> str:
    """Said whenever the clips come in under the target, which is a floor."""
    return (f"Only {clips_sec / 60:.1f} of {target_sec / 60:.0f} minutes: that's all the good, "
            f"unused material in {recordings} recording(s). Analyse another stream and make "
            "the video again to fill it.")


def teaser_segment(conn: sqlite3.Connection, settings: Settings, best: Candidate,
                   moment: tuple[float, float] | None = None) -> Segment:
    """The opening teaser, from ``best``: automatic, or the ``moment`` the creator named."""
    h = settings.highlights
    words = realistic(load_words(conn, best.recording_id))
    hook = dict(shortest=h.hook_seconds[0], longest=h.hook_seconds[1],
                end_pause=settings.clips.end_pause_sec)
    if moment is not None:
        t_in, t_out = teaser_from(moment, best, words, **hook)
    else:
        t_in, t_out = teaser(best, words, sum(h.hook_seconds) / 2, **hook)
    return Segment(best.recording_id, round(t_in, 3), round(t_out, 3), kind="teaser",
                   clip_id=best.clip_id, score=best.score, reasons=best.reasons, game=best.game)


def build_highlights(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    game: str | None,
    recording_ids: list[int] | None = None,
    target_min: float | None = None,
    teaser_clip: str | None = None,
    teaser_moment: tuple[float, float] | None = None,
    reuse: bool = False,
) -> HighlightResult:
    """``teaser_clip``: a clip id to open with (and end on), instead of the automatic pick.
    ``teaser_moment``: the stretch of it to open with (recording time), if the creator named one."""
    h = settings.highlights
    target = (target_min or h.target_length_min) * 60
    everything = recordings_for(conn, settings, game=game, recording_ids=recording_ids,
                                need_video=False)
    recordings = [r for r in everything if has_video(r)]
    deleted = [r for r in everything if not has_video(r)]
    candidates = gather(conn, settings, recordings, game=game, reuse=reuse)
    for c in candidates:
        if c.clip_id == teaser_clip:
            c.must_include = True  # the clip you picked is in the video, whatever else is
    available = sum(c.length for c in candidates)
    selected = select(candidates, target, h.fill_order)
    # Chosen once, so the teaser and the ending are always the same moment
    # (two marked League moments tied, and each broke the tie differently).
    best = best_of(selected, teaser_clip) if selected else None
    chosen = order(selected, h.ordering, best.clip_id if best else None)

    # One game named, or every clip from the same game: a game highlight.
    # Otherwise it's stream highlights, whatever was played.
    games = {c.game for c in chosen}
    game_name = game or (next(iter(games)) if len(games) == 1 else None)
    discard_drafts(conn, "highlights", game_name)
    plan = EditPlan(
        plan_id=new_plan_id(conn, "highlights", game_name),
        recipe="highlights",
        title=f"{game_name} highlights" if game_name else "Stream highlights",
        game=game_name,
        target_sec=target,
        output=settings.render.presets.get("youtube_1080p60").model_dump()
        if "youtube_1080p60" in settings.render.presets else {},
    )
    plan.source = {"game": game, "recording_ids": recording_ids, "removed": [], "reuse": reuse}
    if best is not None and h.hook:
        plan.segments.append(teaser_segment(
            conn, settings, best,
            teaser_moment if teaser_moment is not None and best.clip_id == teaser_clip else None))
    for c in chosen:
        plan.segments.append(Segment(c.recording_id, round(c.src_in, 3), round(c.src_out, 3),
                                     kind="clip", clip_id=c.clip_id, score=c.score,
                                     reasons=c.reasons, game=c.game))

    if deleted:
        names = ", ".join(f"#{r['id']}" for r in deleted)
        plan.notes.append(f"Left out {len(deleted)} recording{'s' if len(deleted) != 1 else ''} "
                          f"whose video was deleted ({names}): nothing can be rendered from "
                          "them. What you taught AI-Editor with them is kept.")
    if not chosen:
        plan.notes.append(nothing_left_note(conn, settings, recordings, game, reuse))
    elif sum(c.length for c in chosen) < target:
        plan.notes.append(short_note(sum(c.length for c in chosen), target, len(recordings)))
    save_plan(conn, plan)
    return HighlightResult(plan, available, len({c.recording_id for c in chosen}), len(recordings))
