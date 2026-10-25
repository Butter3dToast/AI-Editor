"""Where effects go: on the moments you marked with the Stream Companion.

Two kinds of big moment, each with its own effects:

* **Impact**: a sudden jump in the game's sound (a teamfight breaking out,
  an explosion, a burst of gunfire). A screen shake and a boom.
* **Reaction**: you, talking and suddenly louder than your normal talking.
  A flash, a hit and a punch-in zoom (2C-2a: the creator wanted the zoom on
  their reactions, the shake staying on the action).

Both at once gets all three.

**Only where you marked.** A mark (Numpad + or -) is pressed just *after*
something good, so each one gets one effect, on the biggest moment in the
MARK_WINDOW_SEC before the press. Clips you didn't mark get none. This
came from the 2C-1 tests (10 Oct): placed by loudness alone, across whole
clips, effects "seemed randomly placed", and a shake still "happened during
a random time ... didn't use the moments I captured with the companion".

**League's own events** (Phase 2E-2, the creator's choice on 10 Oct): your
multikills, your team's aces and steals get an effect by themselves, on
the exact second League says they happened. A mark with a kill of yours
in its stretch puts its effect exactly on that kill (the multikill, if
there is one) instead of the loudest second. Single kills alone get none,
so a one-sided game doesn't shake all the way through.

Within that stretch, a second that's **really big** wins first: the game's
sound jumping by MIN_JUMP_DB or more, or the creator *talking* clearly
louder than usual (MIN_SHOUT_Z). A bump at the mic with nothing said never
counts as a reaction. Otherwise the biggest the stretch has, judged against
the rest of that stream, because every game and mic is a different
loudness. (The sound recogniser's shout and explosion scores never passed
0.3 on the creator's streams: it hears a mixed track.)

**Your effect rules** (2H-3b): "a zoom on pentakills" gives every penta in
the video a zoom and nothing else, a single kill or a Dragon included when a
rule names them; "no effects when I die" leaves the moments where you die
without. A ruled moment isn't held to the effects a minute: you tick it in
Review, and your tick wins (24 Oct).

The analysis is per second, so each effect is then lined up with the
instant the sound starts, from the recording's own sound track: a flash
half a second late looks like a mistake.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import Settings
from ..recipes.plan import EditPlan
from . import Effect

IMPACT, REACTION = "impact", "reaction"
SOUNDS = {IMPACT: "boom", REACTION: "hit"}
FLASH_SEC = 0.3
SHAKE_SEC = 0.45
ZOOM_SEC = 0.9         # in, hold, and out again (zoom.py)
REPLAY_EVERY_SEC = 120.0   # at most one slow-motion replay per this much video
SFX_SEC = 1.0          # how long a sound effect is counted as (they fade out by then)
# Not in a clip's first or last moments: a flash on a cut looks like a glitch.
EDGE_SEC = 0.5
# A jump is measured against the few seconds before it...
RISE_BACK_SEC = 3
# ...but never against silence: coming back from a quiet moment isn't a jump.
QUIET_PERCENTILE = 20
# Lining up: where to look for the start of the sound, around its second.
ONSET_WINDOW = (-0.5, 1.0)
ONSET_FRAME_SEC = 0.01
ONSET_MIN_RISE_DB = 6.0   # less than this and there's no clear start: keep the second
TRACK_FOR = {IMPACT: ("game", "mixed"), REACTION: ("mic", "mixed")}
# Really big: how much louder than normal talking (in the stream's own
# spread of loudness) a reaction must be...
MIN_SHOUT_Z = 2.0
# ...and how far the game's sound must jump for an impact.
MIN_JUMP_DB = 10.0
MIN_SPEECH = 0.3          # a reaction is said: share of the second with words in it
# The stretch before a mark where its moment is looked for.
MARK_WINDOW_SEC = 20.0
# A mark pressed a little after a clip ends is still about that clip.
MARK_AFTER_SEC = 10.0
# Two moments an effect rule names this close are one fight: the bigger keeps its
# effects ("a zoom on every kill" put two zooms a second apart on a double kill, 24 Oct).
RULE_GAP_SEC = 2.0
# "Only on the biggest moments" (3A-3a): about three in a 10-minute video.
BIGGEST_PER_MIN = 0.3


def rise(db: np.ndarray, back: int = RISE_BACK_SEC) -> np.ndarray:
    """How much louder each second is than the few before it (dB)."""
    if db.size == 0:
        return db
    floor = float(np.percentile(db, QUIET_PERCENTILE))
    out = np.zeros_like(db, dtype=np.float32)
    for t in range(1, len(db)):
        before = db[max(0, t - back):t]
        out[t] = db[t] - max(float(np.median(before)), floor)
    return out


def rank(values: np.ndarray) -> np.ndarray:
    """Each second's place in the stream, 0 (the least) to 1 (the most): the
    share of its seconds below it. Equal seconds share a place, so a long run
    of identical quiet seconds can never count as big."""
    if values.size < 2:
        return np.zeros_like(values, dtype=np.float32)
    below = np.searchsorted(np.sort(values), values, side="left")
    return (below / (values.size - 1)).astype(np.float32)


@dataclass
class Stream:
    # Each second's rank in the stream, 0 (the least) to 1 (the most).
    impact: np.ndarray        # the game sound's jump; 0 where nothing jumped
    reaction: np.ndarray      # how loud against normal talking; 0 when not talking
    # Really big, by a fixed measure.
    big_impact: np.ndarray
    big_reaction: np.ndarray


def _signal(conn: sqlite3.Connection, recording_id: int, name: str, seconds: int) -> np.ndarray | None:
    rows = conn.execute("SELECT t_sec, value FROM signals WHERE recording_id = ? AND name = ?",
                        (recording_id, name)).fetchall()
    if not rows:
        return None
    values = np.zeros(seconds, dtype=np.float32)
    for t, v in rows:
        if 0 <= t < seconds:
            values[t] = v
    return values


def stream_of(conn: sqlite3.Connection, recording_id: int) -> Stream:
    row = conn.execute("SELECT duration_sec FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    seconds = int(math.ceil(row[0] or 0)) + 1 if row else 1
    game = _signal(conn, recording_id, "game_db", seconds)
    loud = _signal(conn, recording_id, "energy_z", seconds)
    talking = _signal(conn, recording_id, "speech", seconds)
    none = np.zeros(seconds, dtype=np.float32)
    impact, big_impact = none, none > 0
    if game is not None:
        jump = rise(game)
        impact, big_impact = rank(jump) * (jump > 0), jump >= MIN_JUMP_DB
    reaction, big_reaction = none, none > 0
    if loud is not None and talking is not None:
        said = talking >= MIN_SPEECH
        reaction, big_reaction = rank(loud) * said, (loud >= MIN_SHOUT_Z) & said
    return Stream(impact.astype(np.float32), reaction.astype(np.float32), big_impact,
                  big_reaction)


@dataclass
class Moment:
    segment: int
    second: int
    impact: float
    reaction: float
    big: bool = False      # really big, by the fixed measure
    both: bool = False     # really big both ways: all three effects
    at: float | None = None      # League's exact time, when it's on a League event
    label: str | None = None     # that event: "Triple kill"
    replay: bool = False         # big enough for a slow-motion replay (2C-2b)
    kinds: list[str] | None = None   # an effect rule's own effects (2H-3b)

    @property
    def strength(self) -> float:
        # League's events are certain; sound only suggests.
        return max(self.impact, self.reaction) + (1.0 if self.big else 0.0) + (
            1.0 if self.at is not None else 0.0)

    @property
    def why(self) -> str:
        return IMPACT if self.impact >= self.reaction else REACTION


def marks_of(conn: sqlite3.Connection, recording_id: int) -> list[float]:
    """When the creator pressed a marker key, in the recording's time."""
    from ..render.audio import markers_of

    return markers_of(conn, recording_id)


def marks_in(marks: list[float], seg_in: float, seg_out: float) -> list[float]:
    """The marks about this clip: pressed during it, or just after it ends."""
    return [p for p in marks if seg_in < p <= seg_out + MARK_AFTER_SEC]


def marked_moment(stream: Stream, segment: int, seg_in: float, seg_out: float,
                  press: float) -> Moment | None:
    """The biggest moment in the stretch before a mark, inside the clip. None
    if that stretch isn't in the clip, or nothing happens in it."""
    first = int(math.ceil(max(seg_in + EDGE_SEC, press - MARK_WINDOW_SEC)))
    last = int(math.floor(min(seg_out - EDGE_SEC, press))) - 1   # second t runs to t + 1
    best = None
    for t in range(max(first, 0), min(last, len(stream.impact) - 1) + 1):
        if stream.impact[t] == 0 and stream.reaction[t] == 0:
            continue
        bi, br = bool(stream.big_impact[t]), bool(stream.big_reaction[t])
        m = Moment(segment, t, float(stream.impact[t]), float(stream.reaction[t]),
                   big=bi or br, both=bi and br, replay=bi)
        if best is None or m.strength > best.strength:
            best = m
    return best


# --- League events (analysis/game_events.py) -----------------------------------------


def league_of(conn: sqlite3.Connection, recording_id: int) -> list[tuple[float, dict]]:
    from ..companion.link import league_events

    return league_events(conn, recording_id)


def _reacting(stream: Stream, t: float) -> bool:
    lo, hi = max(0, int(t) - 2), min(len(stream.big_reaction), int(t) + 3)
    return bool(stream.big_reaction[lo:hi].any())


def event_moment(stream: Stream, segment: int, t: float, event: dict) -> Moment:
    """An effect on a League event: an impact (shake and boom), and the flash
    too when you're reacting to it."""
    from ..analysis.game_events import big, reasons

    label = (reasons([(t, event)]) or [str(event.get("text") or "")])[0]
    both = _reacting(stream, t)
    return Moment(segment, int(t), 1.0, 1.0 if both else 0.0, big=True, both=both, at=t,
                  label=label, replay=big(event))


def big_events(events: list[tuple[float, dict]], seg_in: float,
               seg_out: float) -> list[tuple[float, dict]]:
    """Your multikills, aces and steals, inside the clip (not on its edges)."""
    from ..analysis.game_events import big

    return [(t, e) for t, e in events if big(e)
            and seg_in + EDGE_SEC <= t <= seg_out - EDGE_SEC - SHAKE_SEC]


def marked_kill(events: list[tuple[float, dict]], seg_in: float, seg_out: float,
                press: float) -> tuple[float, dict] | None:
    """What you marked, when League saw it: the biggest moment of yours in the
    stretch before the press, inside the clip. A multikill, ace or steal first,
    then the longest streak, then an objective of your team's, then your last kill."""
    from ..analysis.game_events import big, counts_for_us

    low = max(seg_in + EDGE_SEC, press - MARK_WINDOW_SEC)
    high = min(seg_out - EDGE_SEC - SHAKE_SEC, press)
    yours = [(t, e) for t, e in events if low <= t <= high
             and (e.get("kind") in ("kill", "multikill", "ace") or counts_for_us(e))]
    if not yours:
        return None
    return max(yours, key=lambda k: (big(k[1]), int(k[1].get("streak") or 0),
                                     k[1].get("kind") == "objective", k[0]))


def ruled_events(events: list[tuple[float, dict]], seg_in: float, seg_out: float, rules,
                 game: str | None) -> list[tuple[float, dict, object]]:
    """(time, event, rule) for the League events inside the clip an effect rule names."""
    from ..rules import moments as moment_rules

    out = []
    # A multikill comes at the same second as its kill: named by the bigger one.
    for t, e in sorted(events, key=lambda te: (te[0], -int(te[1].get("streak") or 0))):
        if not seg_in + EDGE_SEC <= t <= seg_out - EDGE_SEC - SHAKE_SEC:
            continue
        rule = moment_rules.effect_for(rules, game, moment_rules.found([(t, e)], [], None, False))
        if rule is not None:
            out.append((t, e, rule))
    return out


def weight(event: dict | None) -> int:
    """Which of two moments in one fight is bigger: a longer streak, an ace, an objective."""
    if not event:
        return 0
    return (10 * int(event.get("streak") or 0) + 5 * (event.get("kind") == "ace")
            + 3 * (event.get("kind") == "objective") + 1)


def apart(found: list[Moment], weights: dict[int, int]) -> list[Moment]:
    """No two within RULE_GAP_SEC in a clip: the bigger stays."""
    kept: list[Moment] = []
    for m in sorted(found, key=lambda m: -weights.get(id(m), 0)):
        if not any(k.segment == m.segment and abs((k.at or k.second) - (m.at or m.second))
                   < RULE_GAP_SEC for k in kept):
            kept.append(m)
    return kept


def ruled(m: Moment, rule) -> Moment:
    """The moment with the rule's effects in place of its own."""
    m.kinds = list(rule.effects)
    m.replay = "replay" in rule.effects
    m.label = f"{m.label or 'your mark'} 📌 {rule.id}"
    return m


def pick(found: list[Moment], count: int, gap_sec: float,
         per_segment: dict[int, int] | None = None) -> list[Moment]:
    """The strongest, kept apart within a clip, at most ``count`` in all and
    ``per_segment[i]`` in segment i."""
    chosen: list[Moment] = []
    taken: dict[int, int] = {}
    for m in sorted(found, key=lambda m: (-m.strength, m.segment, m.second)):
        if len(chosen) >= count:
            break
        if per_segment is not None and taken.get(m.segment, 0) >= per_segment.get(m.segment, 1):
            continue
        if any(c.segment == m.segment and abs(c.second - m.second) < gap_sec for c in chosen):
            continue
        chosen.append(m)
        taken[m.segment] = taken.get(m.segment, 0) + 1
    return sorted(chosen, key=lambda m: (m.segment, m.second))


def how_many(per_min: float, total_sec: float, found: bool) -> int:
    """The most for the whole video; at least one when there's a moment at all."""
    if per_min <= 0 or not found:
        return 0
    return max(1, int(round(per_min * total_sec / 60)))


# --- Lining up with the sound --------------------------------------------------------


def track_path(conn: sqlite3.Connection, recording_id: int, why: str) -> Path | None:
    for role in TRACK_FOR[why]:
        row = conn.execute("SELECT extracted_path FROM audio_tracks WHERE recording_id = ? AND "
                           "role = ? AND extracted_path IS NOT NULL", (recording_id, role)).fetchone()
        if row and Path(row[0]).is_file():
            return Path(row[0])
    return None


def onset(path: Path, second: int) -> float | None:
    """When the sound that made ``second`` loud starts, to the hundredth of a second.

    The loudest instant near that second, then back to where it first got
    half-way there (in dB) from the level before it. None when there's no
    clear jump to line up with."""
    import soundfile as sf

    start = max(0.0, second + ONSET_WINDOW[0])
    try:
        with sf.SoundFile(str(path)) as f:
            rate = f.samplerate
            f.seek(min(int(start * rate), max(0, f.frames - 1)))
            x = f.read(int((ONSET_WINDOW[1] - ONSET_WINDOW[0]) * rate), dtype="float32",
                       always_2d=True).mean(axis=1)
    except (OSError, RuntimeError):
        return None
    step = max(1, int(rate * ONSET_FRAME_SEC))
    frames = len(x) // step
    if frames < 10:
        return None
    rms = np.sqrt(np.mean(x[:frames * step].reshape(frames, step) ** 2, axis=1))
    env = 20 * np.log10(rms + 1e-9)
    # Smoothed against its own edge values: padding with 0 dB would make the
    # window's ends look like the loudest moment.
    env = np.convolve(np.pad(env, 1, mode="edge"), np.ones(3) / 3, mode="valid")
    peak = int(env.argmax())
    before = env[:max(1, peak)]
    level = float(np.percentile(before, QUIET_PERCENTILE))
    if env[peak] - level < ONSET_MIN_RISE_DB:
        return None
    half = level + (env[peak] - level) / 2
    i = peak
    while i > 0 and env[i - 1] >= half:
        i -= 1
    return start + i * ONSET_FRAME_SEC


# --- The whole video ------------------------------------------------------------------


def effects_at(moment: Moment, at: float, on: list[str]) -> list[Effect]:
    why, both = moment.why, moment.both
    out = []
    if "flash" in on and (why == REACTION or both):
        out.append(Effect("flash", at, FLASH_SEC, why))
    if "shake" in on and (why == IMPACT or both):
        out.append(Effect("shake", at, SHAKE_SEC, why))
    if "zoom" in on and (why == REACTION or both):
        out.append(Effect("zoom", at, ZOOM_SEC, why))
    if "replay" in on and moment.replay:
        from ..render.replay import LENGTH_SEC

        out.append(Effect("replay", at, LENGTH_SEC, why))
    if moment.kinds is not None:   # an effect rule's: exactly those
        out = [Effect(kind, at, length, why) for kind, length in
               (("flash", FLASH_SEC), ("shake", SHAKE_SEC), ("zoom", ZOOM_SEC))
               if kind in moment.kinds and kind in on]
        if "replay" in moment.kinds and "replay" in on:
            from ..render.replay import LENGTH_SEC

            out.append(Effect("replay", at, LENGTH_SEC, why))
    if "sfx" in on and (moment.kinds is None or "sfx" in moment.kinds):
        sound = (IMPACT if "shake" in moment.kinds or not {"flash", "zoom"} & set(moment.kinds)
                 else REACTION) if moment.kinds is not None else IMPACT if both else why
        out.append(Effect("sfx", at, SFX_SEC, why, SOUNDS[sound]))
    if moment.label:
        out = [Effect(e.kind, e.at, e.length, e.why, e.sound, moment.label) for e in out]
    return out


def place(conn: sqlite3.Connection, settings: Settings, plan: EditPlan,
          on: list[str]) -> list[list[Effect]]:
    from ..rules import moments as moment_rules

    fx = settings.effects
    rules = [r for r in moment_rules.rules_of(settings) if r.which == "effect"]
    by_rule: list[Moment] = []   # held to no limits: your tick wins
    weights: dict[int, int] = {}
    streams: dict[int, Stream] = {}
    marks: dict[int, list[float]] = {}
    league: dict[int, list[tuple[float, dict]]] = {}
    found: list[Moment] = []
    per_segment: dict[int, int] = {}
    for index, seg in enumerate(plan.segments):
        rid = seg.recording_id
        if rid not in marks:
            marks[rid] = marks_of(conn, rid)
            league[rid] = league_of(conn, rid)
        pressed = marks_in(marks[rid], seg.src_in, seg.src_out)
        biggest = big_events(league[rid], seg.src_in, seg.src_out)
        game = seg.game or plan.game
        named = ruled_events(league[rid], seg.src_in, seg.src_out, rules, game) if rules else []
        if not pressed and not biggest and not named:
            continue
        if rid not in streams:
            streams[rid] = stream_of(conn, rid)
        moments = [event_moment(streams[rid], index, t, e) for t, e in biggest]
        for p in pressed:
            kill = marked_kill(league[rid], seg.src_in, seg.src_out, p)
            m = (event_moment(streams[rid], index, *kill) if kill
                 else marked_moment(streams[rid], index, seg.src_in, seg.src_out, p))
            if m is not None and not any(o.at is not None and m.at is not None
                                         and abs(o.at - m.at) < 0.5 for o in moments):
                if rules:
                    said = moment_rules.found([kill] if kill else [], [], None, True)
                    rule = moment_rules.effect_for(rules, game, said)
                    if rule is not None:
                        by_rule.append(ruled(m, rule))
                        weights[id(m)] = weight(kill[1] if kill else None)
                        continue
                moments.append(m)
        for t, e, rule in named:
            if any(o.at is not None and abs(o.at - t) < 0.5 for o in by_rule
                   if o.segment == index):
                continue   # a mark already on it
            moments = [o for o in moments if o.at is None or abs(o.at - t) >= 0.5]
            by_rule.append(ruled(event_moment(streams[rid], index, t, e), rule))
            weights[id(by_rule[-1])] = weight(e)
        found += moments
        per_segment[index] = len(moments)
    chosen = pick(found, how_many(fx.per_min(plan.recipe), plan.total_sec, bool(found)),
                  fx.min_gap_sec, per_segment)
    # "No effects when I die": those rules' moments go without, and nothing else
    # lands on them.
    quiet = [m for m in by_rule if not m.kinds]
    chosen = [m for m in chosen if not any(
        q.segment == m.segment and abs((m.at or m.second) - (q.at or q.second)) <= 1.0
        for q in quiet)]
    ruled_now = apart([m for m in by_rule if m.kinds], weights)
    # Slow-motion replays: the biggest moments only, one per clip, and no more
    # than one every REPLAY_EVERY_SEC of video (one in a Short).
    allowed = 1 if plan.recipe == "shorts" else max(1, int(plan.total_sec // REPLAY_EVERY_SEC))
    replayed: set[int] = set()   # segments with one
    for m in sorted((m for m in chosen if m.replay), key=lambda m: -m.strength):
        if len(replayed) < allowed and m.segment not in replayed:
            replayed.add(m.segment)
        else:
            m.replay = False

    # A style profile's own limit per kind (2G-2): "at most 0.5 zooms a minute" keeps
    # zooms to the biggest moments; the other effects there still go.
    # Your "only on the biggest moments" answers (3A-3a) work the same way.
    rates = dict(fx.kind_per_min)
    for kind in fx.only_biggest:
        rates[kind] = min(rates.get(kind, BIGGEST_PER_MIN), BIGGEST_PER_MIN)
    allowed = {kind: {id(m) for m in sorted(chosen, key=lambda m: -m.strength)
                      [:how_many(rate, plan.total_sec, bool(chosen))]}
               for kind, rate in rates.items()}
    for m in ruled_now:
        for kind in allowed:
            allowed[kind].add(id(m))
    placed: list[list[Effect]] = [[] for _ in plan.segments]
    tracks: dict[tuple[int, str], Path | None] = {}
    for m in sorted(chosen + ruled_now, key=lambda m: (m.segment, m.at or m.second)):
        seg = plan.segments[m.segment]
        if m.at is not None:
            at = m.at   # League's own time: already exact
        else:
            key = (seg.recording_id, m.why)
            if key not in tracks:
                tracks[key] = track_path(conn, seg.recording_id, m.why)
            at = onset(tracks[key], m.second) if tracks[key] else None
            at = float(m.second) if at is None else at
        longest = ZOOM_SEC if "zoom" in on else SHAKE_SEC   # all of it inside the clip
        at = min(max(at, seg.src_in + EDGE_SEC), seg.src_out - EDGE_SEC - longest)
        placed[m.segment] += [e for e in effects_at(m, at, on)
                              if e.kind not in allowed or id(m) in allowed[e.kind]]
    return placed
