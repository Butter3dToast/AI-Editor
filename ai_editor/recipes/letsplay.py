"""Recipe A: a Let's Play episode, trimmed and split into parts (spec section 7.6).

Step 1 (this file, Phase 1F-2a) is the always-trim pass: what a viewer would
skip anyway goes, and nothing else.

* **Loading and black screens** go.
* **Menus, the map, the inventory** (a still picture) go -- unless you're
  talking over them. The creator: "keep if I'm talking".
* **Silence** (nobody talking, nothing happening) longer than 20 seconds is
  cut down, leaving a few seconds either side so the jump isn't jarring.
* Never cut: anyone talking (the creator, or the game's characters), a fight,
  a cutscene, or a moment that scored well. Never mid-word.
* Nothing is sped up. The creator: "don't speed up my voice ... rather cut
  the parts out".

Everything here is decided from the analysis already stored; nothing is
re-analysed, so the plan can be remade in seconds.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import numpy as np

from ..analysis.clips import action_signal, load_words, realistic
from ..analysis.hype import build, dark_seconds, load_signals
from ..analysis.captions import clock
from ..config import Settings
from .plan import EditPlan, Segment, discard_drafts, new_plan_id, save_plan

# How many seconds each side of a cut are left in, by what's being cut.
LOADING_MARGIN_SEC = 0.3   # straight to the next scene; a loading screen is never missed
MENU_MARGIN_SEC = 1.0      # a moment of the menu, so the viewer sees where they are
# Words closer than this to a cut count as talking: the edge never clips a breath.
WORD_PAD_SEC = 0.3
# A loading screen barely changes at all: only its spinner moves.
LOADING_STILL_LEVEL = 0.5
# A cut shorter than this saves nothing and adds a jump.
MIN_CUT_SEC = 1.5
# Kept pieces shorter than this, between two cuts, are cut too: a 1-second
# flash of gameplay between two jumps looks like a glitch.
MIN_KEPT_SEC = 2.0

REASONS = {
    "loading": "loading / black screen",
    "menu": "menu / map / inventory",
    "silence": "long silence",
    "stream_screen": "starting / BRB / ending screen",
}


@dataclass
class Cut:
    start: float
    end: float
    reason: str  # a key of REASONS

    @property
    def length(self) -> float:
        return self.end - self.start


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) of each stretch of True seconds."""
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.nonzero(edges == 1)[0].tolist(), np.nonzero(edges == -1)[0].tolist()))


def talking_seconds(words, signals: dict[str, np.ndarray], seconds: int,
                    level: float = 0.5) -> np.ndarray:
    """Seconds in which anyone is talking: the creator (their words, or their
    voice heard) or the game's characters (speech heard on the game track)."""
    talking = np.zeros(seconds, dtype=bool)
    for w in words:
        a = max(0, int(w.start - WORD_PAD_SEC))
        b = min(seconds, int(np.ceil(w.end + WORD_PAD_SEC)))
        talking[a:b] = True
    for name in ("speech", "dialogue"):
        values = signals.get(name)
        if values is not None and values.size:
            talking |= np.resize(values, seconds) >= level
    return talking


def protected_seconds(score: np.ndarray, signals: dict[str, np.ndarray],
                      seconds: int, settings: Settings) -> np.ndarray:
    """Seconds never cut, even when nobody is talking: good moments and fights,
    sword fights included.

    Cutscenes are protected by what's in them -- the characters talking,
    which counts as talking -- not by camera cuts. Dense scene changes mark a
    cutscene on Wardogs, but Dawnwalker's ordinary play has 8-25 a minute, and
    treating them as cutscenes protected 84% of EP 1 from trimming.
    """
    lp = settings.lets_play
    protected = np.resize(score, seconds) >= lp.protect_score
    # Gunfire and explosions, and sword fights: Dawnwalker's fights make no
    # gunfire, and a silent one on EP 1 (94:44) was nearly cut as "silence".
    found = [a for a in (action_signal(signals), signals.get("melee")) if a is not None and a.size]
    action = np.maximum.reduce([np.resize(a, seconds) for a in found]) if found else None
    if action is not None:
        fight = action >= settings.clips.fight_level
        for a, b in _runs(fight):  # the quiet moments between shots are still the fight
            protected[max(0, a - int(settings.clips.fight_gap_sec)):
                      min(seconds, b + int(settings.clips.fight_gap_sec))] = True
    return protected


def plan_cuts(*, seconds: int, talking: np.ndarray, protected: np.ndarray,
              dark: np.ndarray | None, motion: np.ndarray | None,
              hud: np.ndarray | None = None, off_game: np.ndarray | None = None,
              settings: Settings) -> list[Cut]:
    """What the always-trim pass removes, in time order.

    ``hud`` (0-1 per second) says whether the game's on-screen display shows;
    ``off_game`` marks seconds the Stream Companion saw a non-game OBS scene.
    """
    lp = settings.lets_play
    none = np.zeros(seconds, dtype=bool)
    moving = np.resize(motion, seconds) if motion is not None and motion.size else None
    still = (moving < lp.still_level) if moving is not None else none
    # A loading screen is black AND still. Dawnwalker at night is nearly as
    # dark (brightness 21-26 against a loading screen's 17) but the camera
    # moves: on EP 1, night-time play with the health bar showing was cut as
    # "loading" until stillness was required too.
    frozen = (moving < LOADING_STILL_LEVEL) if moving is not None else ~none
    black = (dark & frozen) if dark is not None else none
    # Silence is only cut during play. With the HUD gone and nobody talking,
    # it's a cutscene or a choice: on EP 1, 10 of 24 "silences" were quiet
    # moments in cutscenes (close-ups, a fire, a dialogue choice).
    playing = (np.resize(hud, seconds) >= lp.hud_level) if hud is not None and hud.size else None

    cuts: list[Cut] = []
    # Your "Starting soon", "BRB" and "Stream ended" screens aren't the episode.
    if off_game is not None:
        cuts += [Cut(float(s), float(e), "stream_screen") for s, e in _runs(off_game)]
    quiet = ~talking & ~protected & ~(off_game if off_game is not None else none)
    for a, b in _runs(quiet):
        removed = np.zeros(b - a, dtype=bool)
        for kind, mask, shortest, margin in (
            ("loading", black[a:b], lp.loading_min_sec, LOADING_MARGIN_SEC),
            ("menu", still[a:b] & ~black[a:b], lp.still_min_sec, MENU_MARGIN_SEC),
        ):
            for s, e in _runs(mask):
                if e - s >= shortest:
                    cuts.append(Cut(a + s + margin, a + e - margin, kind))
                    removed[s:e] = True
        # What's left of this quiet stretch: plain silence, if it's play.
        left = ~removed if playing is None else (~removed & playing[a:b])
        for s, e in _runs(left):
            if e - s > lp.dead_air_sec:
                keep = lp.dead_air_keep_sec
                cuts.append(Cut(a + s + keep, a + e - keep, "silence"))
    return _tidy(sorted(cuts, key=lambda c: c.start), seconds)


def _tidy(cuts: list[Cut], seconds: int) -> list[Cut]:
    """Join cuts with a sliver between them; drop cuts too short to matter."""
    merged: list[Cut] = []
    for cut in cuts:
        cut = Cut(max(0.0, cut.start), min(float(seconds), cut.end), cut.reason)
        if merged and cut.start - merged[-1].end < MIN_KEPT_SEC:
            last = merged[-1]
            # The longer part names the join.
            reason = last.reason if last.length >= cut.length else cut.reason
            merged[-1] = Cut(last.start, max(last.end, cut.end), reason)
        else:
            merged.append(cut)
    return [c for c in merged if c.length >= MIN_CUT_SEC]


def kept_pieces(cuts: list[Cut], duration: float) -> list[tuple[float, float]]:
    """The recording minus the cuts: what the episode is made of."""
    pieces, at = [], 0.0
    for cut in cuts:
        if cut.start > at:
            pieces.append((at, cut.start))
        at = max(at, cut.end)
    if at < duration:
        pieces.append((at, duration))
    return pieces


@dataclass
class Episode:
    """One recording's stored analysis, as the Let's Play recipe reads it."""

    seconds: int
    words: list
    score: np.ndarray
    signals: dict[str, np.ndarray]
    talking: np.ndarray
    protected: np.ndarray
    off_game: np.ndarray | None


def load_episode(conn: sqlite3.Connection, settings: Settings, row: sqlite3.Row) -> Episode:
    seconds = int(row["duration_sec"])
    signals = load_signals(conn, row["id"], seconds)
    score = np.resize(build(conn, settings, row["id"], seconds).score, seconds)
    words = realistic(load_words(conn, row["id"]))
    return Episode(seconds, words, score, signals,
                   talking=talking_seconds(words, signals, seconds),
                   protected=protected_seconds(score, signals, seconds, settings),
                   off_game=_off_game(conn, row["id"], seconds))


def trim(conn: sqlite3.Connection, settings: Settings, row: sqlite3.Row,
         episode: Episode | None = None) -> list[Cut]:
    """The always-trim pass for one recording, from its stored analysis."""
    e = episode or load_episode(conn, settings, row)
    return plan_cuts(
        seconds=e.seconds, talking=e.talking, protected=e.protected,
        dark=dark_seconds(e.signals, e.seconds, settings.scoring.dark_level,
                          settings.lets_play.loading_min_sec),
        motion=e.signals.get("motion"), hud=e.signals.get("hud"), off_game=e.off_game,
        settings=settings,
    )


def _off_game(conn: sqlite3.Connection, recording_id: int, seconds: int) -> np.ndarray | None:
    """Seconds the Companion saw a scene that isn't a game, if it was running."""
    from ..companion.link import game_timeline

    timeline = game_timeline(conn, recording_id)
    if not timeline:
        return None
    off = np.zeros(seconds, dtype=bool)
    for i, (start, game) in enumerate(timeline):
        end = timeline[i + 1][0] if i + 1 < len(timeline) else seconds
        if game is None:
            off[max(0, int(start)):min(seconds, int(np.ceil(end)))] = True
    return off


# --- The plan and the cuts reel ----------------------------------------------------

REEL_CONTEXT_SEC = 4.0  # shown each side of a cut, so you judge the jump itself


@dataclass
class LetsPlayResult:
    plan: EditPlan
    cuts: list[Cut]
    duration_sec: float
    parts: list = field(default_factory=list)          # parts.Part, in order
    pieces: list = field(default_factory=list)         # what's kept, in the recording


def build_letsplay(conn: sqlite3.Connection, settings: Settings, row: sqlite3.Row) -> LetsPlayResult:
    """Trim one recording, split it into parts, and save it as a draft plan."""
    from .parts import break_points, make_parts, range_pieces, split

    episode = load_episode(conn, settings, row)
    cuts = trim(conn, settings, row, episode)
    duration = float(row["duration_sec"])
    pieces = kept_pieces(cuts, duration)
    total = sum(b - a for a, b in pieces)
    parts = make_parts(total, split(total, break_points(episode, cuts, pieces, settings), settings),
                       pieces)

    game = row["game"]
    discard_drafts(conn, "letsplay", game)
    plan = EditPlan(
        plan_id=new_plan_id(conn, "letsplay", game),
        recipe="letsplay",
        title=" - ".join(x for x in (game, row["title"]) if x) or "Let's Play",
        game=game,
        target_sec=settings.lets_play.target_min * 60,
        segments=[Segment(row["id"], round(a, 3), round(b, 3), kind="piece", game=game, part=p.number)
                  for p in parts for a, b in range_pieces(pieces, p.start, p.end)],
    )
    removed = sum(c.length for c in cuts)
    plan.notes.append(f"Trimmed {removed / 60:.1f} of {duration / 60:.1f} minutes in {len(cuts)} cuts; "
                      f"{len(parts)} part(s).")
    plan.notes += [f"Part {p.number} ends at a forced split: nothing cleaner within the length limit. "
                   "Check it." for p in parts if p.flagged]
    save_plan(conn, plan)
    return LetsPlayResult(plan, cuts, duration, parts, pieces)


def cuts_reel(result: LetsPlayResult, recording_id: int) -> tuple[EditPlan, list[str]]:
    """Every cut, with a few seconds either side: how each jump will look.

    Returns a plan to preview and a caption for each of its pieces.
    """
    reel = EditPlan(plan_id=f"{result.plan.plan_id} cuts", recipe="letsplay",
                    title="Cuts reel", game=result.plan.game, target_sec=0)
    labels: list[str] = []
    total = len(result.cuts)
    for n, cut in enumerate(result.cuts, start=1):
        before = max(0.0, cut.start - REEL_CONTEXT_SEC)
        after = min(result.duration_sec, cut.end + REEL_CONTEXT_SEC)
        label = (f"Cut {n} of {total} at {clock(cut.start)}: {REASONS[cut.reason]}, "
                 f"{cut.length:.0f} s removed")
        if cut.start - before > 0.1:
            reel.segments.append(Segment(recording_id, round(before, 3), round(cut.start, 3),
                                         kind="piece", captions=False))
            labels.append(label)
        if after - cut.end > 0.1:
            reel.segments.append(Segment(recording_id, round(cut.end, 3), round(after, 3),
                                         kind="piece", captions=False))
            labels.append(label)
    return reel, labels


SPLIT_BEFORE_SEC = 20.0  # the end of a part, to judge how it finishes
SPLIT_AFTER_SEC = 10.0   # and how the next one opens


def splits_reel(result: LetsPlayResult, recording_id: int) -> tuple[EditPlan, list[str]]:
    """The end of each part and the start of the next: how every split plays."""
    from .parts import range_pieces

    reel = EditPlan(plan_id=f"{result.plan.plan_id} splits", recipe="letsplay",
                    title="Splits reel", game=result.plan.game, target_sec=0)
    labels: list[str] = []
    for part, following in zip(result.parts, result.parts[1:]):
        ending = f"End of part {part.number} ({clock(part.length)} long, ends on {part.ends_on})"
        opening = f"Start of part {following.number}"
        for a, b in range_pieces(result.pieces, max(part.start, part.end - SPLIT_BEFORE_SEC), part.end):
            reel.segments.append(Segment(recording_id, round(a, 3), round(b, 3), kind="piece",
                                         captions=False))
            labels.append(ending)
        for a, b in range_pieces(result.pieces, following.start,
                                 min(following.end, following.start + SPLIT_AFTER_SEC)):
            reel.segments.append(Segment(recording_id, round(a, 3), round(b, 3), kind="piece",
                                         captions=False))
            labels.append(opening)
    return reel, labels
