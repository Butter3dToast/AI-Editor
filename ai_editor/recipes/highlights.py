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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

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
from ..analysis.pipeline import load_scene_cuts
from ..config import Settings
from .plan import EditPlan, Segment, discard_drafts, new_plan_id, save_plan

# A video counts as on target within this share of the target (spec section 7.6).
TOLERANCE = 0.15
# How much of the teaser comes before the peak of the moment.
TEASER_BEFORE_PEAK = 0.6


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


def recordings_for(conn: sqlite3.Connection, settings: Settings, *, game: str | None,
                   recording_ids: list[int] | None) -> list[sqlite3.Row]:
    """The recordings a highlight video draws from.

    By number, if given. For one game: recordings of that game, plus any
    where the Stream Companion saw that game's OBS scene (a Wardogs stream
    that turned into Tarkov). Otherwise every stream: all recordings except
    Let's Play episodes (lets_play.games) -- "because we are doing stream
    highlights we are taking all the games that were played". A recording
    whose game isn't known is still a stream, so it is included.
    """
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
           recordings: list[sqlite3.Row], *, game: str | None = None) -> list[Candidate]:
    """Every clip that may go into the video, trimmed to its moment.

    With ``game``, only clips from that game: each clip knows its own game
    when the Companion logged the OBS scenes, else it takes its recording's.
    """
    h = settings.highlights
    found: list[Candidate] = []
    for row in recordings:
        refresh_clips(conn, settings, row)  # a couple of seconds; always current
        words = realistic(load_words(conn, row["id"]))
        cuts = load_scene_cuts(settings, row)
        score = load_signal(conn, row["id"], "hype")
        signals = load_signals(conn, row["id"], int(row["duration_sec"]))
        action = action_signal(signals)
        dark = dark_seconds(signals, int(row["duration_sec"]), settings.scoring.dark_level,
                            settings.scoring.dark_min_sec)
        when = recorded_at(row)
        for clip in conn.execute("SELECT * FROM clips WHERE recording_id = ?", (row["id"],)):
            if clip["used_in_json"] and not h.allow_reused_clips:
                continue
            summary = json.loads(clip["signals_json"] or "{}")
            marked = "marker" in summary or "marker_short" in summary
            must = (h.always_include_pinned and bool(clip["pinned"])) or \
                   (h.always_include_markers and marked)
            if clip["score"] < h.min_clip_score and not must:
                continue
            if clip["user_rating"] is not None and clip["user_rating"] < 0:
                continue  # thumbs down
            clip_game = summary.get("game") or row["game"]
            if game and clip_game != game:
                continue
            core = tuple(summary.get("core") or (int(clip["start_sec"]), int(clip["end_sec"])))
            peak = int(summary.get("peak", (core[0] + core[1]) // 2))
            candidate = Candidate(
                clip["clip_id"], row["id"], clip["start_sec"], clip["end_sec"], clip["score"],
                peak, (int(core[0]), int(core[1])), summary.get("reasons", []), when, must,
                game=clip_game, marked=marked,
            )
            candidate.src_in, candidate.src_out = trim(
                candidate, words, cuts, float(row["duration_sec"]), score, settings,
                action=action, dark=dark)
            candidate.reaction = reaction_strength(signals, candidate.src_in, candidate.src_out,
                                                   settings.scoring.zscore_full_scale)
            found.append(candidate)
    return found


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
    limit = target_sec * (1 + TOLERANCE)
    chosen = [c for c in candidates if c.must_include]
    total = sum(c.length for c in chosen)
    rest = [c for c in candidates if not c.must_include]
    if fill_order == "oldest_first":
        # Use up one stream's good clips, best first, before moving to the next.
        rest.sort(key=lambda c: (c.recorded, -c.score))
    else:
        rest.sort(key=lambda c: -c.score)
    for candidate in rest:
        if total >= target_sec:
            break
        if total + candidate.length <= limit:
            chosen.append(candidate)
            total += candidate.length
    return chosen


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
    """Strong opener, alternating intensity, best moment last (spec section 7.6)."""
    if ordering == "chronological":
        return sorted(chosen, key=lambda c: (c.recorded, c.src_in))
    finale = best_of(chosen, pick) if chosen else None
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


def build_highlights(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    game: str | None,
    recording_ids: list[int] | None = None,
    target_min: float | None = None,
    teaser_clip: str | None = None,
) -> HighlightResult:
    """``teaser_clip``: a clip id to open with (and end on), instead of the automatic pick."""
    h = settings.highlights
    target = (target_min or h.target_length_min) * 60
    recordings = recordings_for(conn, settings, game=game, recording_ids=recording_ids)
    candidates = gather(conn, settings, recordings, game=game)
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
    if best is not None and h.hook:
        words = realistic(load_words(conn, best.recording_id))
        length = sum(h.hook_seconds) / 2
        t_in, t_out = teaser(best, words, length, shortest=h.hook_seconds[0],
                             longest=h.hook_seconds[1], end_pause=settings.clips.end_pause_sec)
        plan.segments.append(Segment(best.recording_id, round(t_in, 3), round(t_out, 3),
                                     kind="teaser", clip_id=best.clip_id, score=best.score,
                                     reasons=best.reasons, game=best.game))
    for c in chosen:
        plan.segments.append(Segment(c.recording_id, round(c.src_in, 3), round(c.src_out, 3),
                                     kind="clip", clip_id=c.clip_id, score=c.score,
                                     reasons=c.reasons, game=c.game))

    if not chosen:
        plan.notes.append("No clips passed the quality bar. Lower highlights.min_clip_score "
                          "in Settings, or analyse more recordings of this game.")
    elif plan.total_sec < target * (1 - TOLERANCE):
        plan.notes.append(
            f"Only {plan.total_sec / 60:.1f} of {target / 60:.0f} minutes: that's all the good, "
            f"unused material in {len(recordings)} recording(s). Analyse another stream of this "
            "game and make the video again to fill it.")
    save_plan(conn, plan)
    return HighlightResult(plan, available, len({c.recording_id for c in chosen}), len(recordings))
