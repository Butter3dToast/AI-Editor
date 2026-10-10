"""One score per second: how good a moment is (spec section 7.3).

Everything analysis heard -- the creator's markers, laughter, shouting,
gunfire, sudden loudness, chat -- is on a different scale. Sound recognition
gives 0 to 1; loudness and chat come as z-scores ("how unusual for this
recording"); a marker is simply pressed or not. Each is first brought onto the
same 0-1 scale, then added up with the weights from Settings, so changing a
weight means what a creator would expect.

Two details that matter more than the weights:

* **Markers count backwards.** They are pressed *after* the good bit, so a
  press lifts the minute before it (settings: marker_lookback_sec), not the
  moment of the press.
* **Peaks are judged on a few seconds together.** A single loud second is
  usually a door slam; a good moment stays interesting for several seconds,
  so the score is smoothed before peaks are picked.

League's own events (kills, multikills, objectives; analysis/game_events.py)
join in as signals of their own, each spread over the fight leading up to
it. Your deaths only count when you react to them, and League time outside a
match (queue, champion select, the lobby) scores nothing unless you marked it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import numpy as np

from ..config import Settings

# Signals that arrive as z-scores rather than 0-1.
ZSCORE_SIGNALS = ("energy_z", "chat_z")
# Signals where a marker press means "the good bit is just before this".
MARKER_SIGNALS = ("marker", "marker_short")
# League events (game_events.py): each lifts the fight leading up to it.
EVENT_SIGNALS = ("lol_kill", "lol_multikill", "lol_objective", "lol_ace", "lol_death",
                 "lol_fight")
# Your deaths only count when you react to them: the creator's choice
# (2026-10-10). Quiet deaths are ordinary; the loud or laughing ones are
# the funny Short-worthy moments.
DEATH_SIGNAL = "lol_death"
REACTION_SIGNALS = ("laughter", "scream", "shout", "energy_z")
REACTION_LOUD = 0.5          # energy_z on the 0-1 scale: half of "as loud as it gets"
REACTION_NEAR_SEC = 6

HYPE_SIGNAL = "hype"

# What kinds of thing can be happening at once. A moment that is a fight *and*
# a reaction is worth more than either alone -- the creator picked exactly
# those two out of the first ranked list, and rejected the one that was only
# loud. The bonus counts kinds, not signals, so three sounds of laughter do
# not pretend to be three different reasons.
SIGNAL_KINDS = {
    "marker": "your pick", "marker_short": "your pick",
    "laughter": "reaction", "scream": "reaction", "shout": "reaction",
    "gunfire": "action", "explosion": "action",
    "lol_kill": "action", "lol_multikill": "action", "lol_objective": "action",
    "lol_ace": "action", "lol_death": "action", "lol_fight": "action",
    "chat_z": "audience",
    "energy_z": "loud",
}

COMBINATION_PART = "combination"


def load_signals(conn: sqlite3.Connection, recording_id: int, seconds: int) -> dict[str, np.ndarray]:
    """Every stored signal for a recording, each padded to ``seconds`` long."""
    rows = conn.execute(
        "SELECT name, t_sec, value FROM signals WHERE recording_id = ? AND name != ?",
        (recording_id, HYPE_SIGNAL),
    ).fetchall()
    signals: dict[str, np.ndarray] = {}
    for row in rows:
        values = signals.get(row["name"])
        if values is None:
            values = signals[row["name"]] = np.zeros(seconds, dtype=np.float32)
        if 0 <= row["t_sec"] < seconds:
            values[row["t_sec"]] = row["value"]
    return signals


def marker_curve(
    presses: np.ndarray, *, lookback_sec: float, lookahead_sec: float
) -> np.ndarray:
    """Spread each marker press over the moment it was meant for.

    Full strength at the press and for the seconds just before it, easing off
    towards the start of the look-back window: the further back from the
    press, the less likely that second is what the creator meant.
    """
    seconds = len(presses)
    curve = np.zeros(seconds, dtype=np.float32)
    back, ahead = int(round(lookback_sec)), int(round(lookahead_sec))
    for second in np.nonzero(presses)[0]:
        start = max(0, int(second) - back)
        for t in range(start, min(seconds, int(second) + ahead + 1)):
            if t <= second:
                # 0.4 at the far end of the look-back, 1.0 at the press.
                age = (second - t) / max(1, back)
                strength = 1.0 - 0.6 * age
            else:
                strength = 1.0
            curve[t] = max(curve[t], strength)
    return curve


def reacting(unit_values: dict[str, np.ndarray], seconds: int, threshold: float) -> np.ndarray:
    """True around each second where you react: laughing, screaming, shouting,
    or clearly louder than usual, within REACTION_NEAR_SEC either side."""
    found = np.zeros(seconds, dtype=bool)
    for name in REACTION_SIGNALS:
        values = unit_values.get(name)
        if values is not None:
            found |= values >= (REACTION_LOUD if name == "energy_z" else threshold)
    if not found.any():
        return found
    window = np.ones(2 * REACTION_NEAR_SEC + 1)
    return np.convolve(found.astype(np.float32), window, mode="same") > 0


def to_unit_scale(name: str, values: np.ndarray, *, zscore_full_scale: float) -> np.ndarray:
    """Bring one signal onto 0-1, whatever scale it arrived in."""
    if name in ZSCORE_SIGNALS:
        return np.clip(values / zscore_full_scale, 0.0, 1.0)
    return np.clip(values, 0.0, 1.0)


def sustained(values: np.ndarray, window_sec: float) -> np.ndarray:
    """How much of the last few seconds this sound filled.

    Gunfire is the reason this exists. On the creator's Wardogs stream, single
    bursts of shooting at nothing scored as highly as real firefights; judged
    over fifteen seconds, the fights stand out and the stray shots fade.
    """
    window = max(1, int(round(window_sec)))
    if window == 1 or values.size == 0:
        return values
    kernel = np.ones(window, dtype=np.float32) / window
    # Centred, so a fight is loudest in its middle rather than at its end.
    return np.convolve(values, kernel, mode="same").astype(np.float32)


def combination_bonus(
    unit_values: dict[str, np.ndarray], seconds: int, *, bonus: float, threshold: float
) -> tuple[np.ndarray, np.ndarray]:
    """Reward moments where more than one kind of thing is happening.

    Judged against the creator's own verdicts on ten Wardogs clips: all three
    they liked had a fight *and* them reacting; all five they rejected had
    only one of the two. What made the difference was ``threshold``: the
    sound model hears the creator's laughter faintly (13-15% sure in the
    clips they liked), so at 30% it never counted as a reaction. From 8% to
    12% the three good clips ranked 1, 2, 3 whatever the bonus. Allowing a
    few seconds between the fight and the reaction was tried and made no
    difference, since the score is already smoothed over several seconds.

    Returns the bonus per second and how many kinds were present.
    """
    kinds: dict[str, np.ndarray] = {}
    for name, values in unit_values.items():
        kind = SIGNAL_KINDS.get(name)
        if kind is None:
            continue
        present = (values >= threshold).astype(np.float32)
        kinds[kind] = np.maximum(kinds[kind], present) if kind in kinds else present
    if not kinds:
        return np.zeros(seconds, dtype=np.float32), np.zeros(seconds, dtype=np.float32)
    count = np.sum(list(kinds.values()), axis=0)
    return (bonus * np.maximum(count - 1, 0)).astype(np.float32), count


def dark_seconds(signals: dict[str, np.ndarray], seconds: int, level: float,
                 min_run: int = 1) -> np.ndarray | None:
    """True for each second the picture is black, or None if brightness wasn't measured.

    Only stretches at least ``min_run`` seconds long count: a loading screen
    lasts a while; a flicker, or the screen going black for a moment when you
    crash, doesn't. On the creator's Wardogs stream one dark frame every 6
    seconds (a blinking effect) chopped a conversation into three 4-second
    clips, and a 5-second crash blackout cut the crash off its own clip.
    """
    brightness = signals.get("brightness")
    if brightness is None or not brightness.size:
        return None
    dark = np.resize(brightness, seconds) <= level
    if min_run > 1 and dark.any():
        edges = np.diff(np.concatenate(([0], dark.astype(np.int8), [0])))
        for begin, finish in zip(np.nonzero(edges == 1)[0], np.nonzero(edges == -1)[0]):
            if finish - begin < min_run:
                dark[begin:finish] = False
    return dark


def smooth(values: np.ndarray, window_sec: float) -> np.ndarray:
    """Average over a few seconds, so one odd second can't make a peak."""
    window = max(1, int(round(window_sec)))
    if window == 1 or values.size == 0:
        return values
    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(values, kernel, mode="same").astype(np.float32)


@dataclass
class HypeResult:
    score: np.ndarray                       # 0-1 per second
    parts: dict[str, np.ndarray] = field(default_factory=dict)  # each signal's contribution
    missing: list[str] = field(default_factory=list)  # weighted signals not in this recording


def hype_score(signals: dict[str, np.ndarray], settings: Settings, seconds: int,
               downtime: np.ndarray | None = None) -> HypeResult:
    """Combine the signals into one score per second, between 0 and 1.

    ``downtime``: seconds that are never a moment unless marked (League
    outside a match, game_events.downtime)."""
    scoring = settings.scoring
    total = np.zeros(seconds, dtype=np.float32)
    parts: dict[str, np.ndarray] = {}
    unit_values: dict[str, np.ndarray] = {}
    missing: list[str] = []

    for name, weight in scoring.weights.items():
        values = signals.get(name)
        if values is None or not values.size:
            if weight > 0 and name not in EVENT_SIGNALS:  # only League with the Companion has them
                missing.append(name)
            continue
        values = np.resize(values, seconds) if values.size != seconds else values
        if name in MARKER_SIGNALS:
            values = marker_curve(values, lookback_sec=scoring.marker_lookback_sec,
                                  lookahead_sec=scoring.marker_lookahead_sec)
        elif name in EVENT_SIGNALS:
            # Each press-like event, scaled by its own size (a penta beats a double).
            values = _spread(values, scoring)
        else:
            values = to_unit_scale(name, values, zscore_full_scale=scoring.zscore_full_scale)
        if name in scoring.sustain_sec:
            values = sustained(values, scoring.sustain_sec[name])
        unit_values[name] = values
        contribution = (weight * values).astype(np.float32)
        parts[name] = contribution
        total += contribution

    if DEATH_SIGNAL in unit_values:
        gated = unit_values[DEATH_SIGNAL] * reacting(unit_values, seconds,
                                                     scoring.combination_threshold)
        unit_values[DEATH_SIGNAL] = gated
        parts[DEATH_SIGNAL] = (scoring.weights[DEATH_SIGNAL] * gated).astype(np.float32)
        total = sum(parts.values(), np.zeros(seconds, dtype=np.float32))

    bonus, _ = combination_bonus(
        unit_values, seconds,
        bonus=scoring.combination_bonus, threshold=scoring.combination_threshold,
    )
    if bonus.any():
        parts[COMBINATION_PART] = bonus
        total += bonus

    marked = sum((parts[name] for name in MARKER_SIGNALS if name in parts),
                 np.zeros(seconds, dtype=np.float32))
    dark = dark_seconds(signals, seconds, scoring.dark_level, scoring.dark_min_sec)

    def settle(values: np.ndarray) -> np.ndarray:
        values = smooth(values, scoring.smooth_sec)
        # Nothing worth keeping scores below zero; the silence weight is a
        # penalty, not a reason to rank below "nothing happened at all".
        values = np.maximum(values, 0.0)
        # A black screen is never a moment, whatever is said over it (a
        # Wardogs clip was 48 s of black while the creator set up a scene).
        if dark is not None:
            values[dark] = 0.0
        # League outside a match, unless you marked it.
        if downtime is not None and downtime.size:
            values[np.resize(downtime, seconds) & (marked <= 0)] = 0.0
        return values

    total, unmarked = settle(total), settle(total - marked)
    # Scored against this recording's own best moment, so a quiet Let's Play
    # and a loud stream are both usable, and 1.0 always means "its best".
    # Measured on the creator's 1h52m Wardogs stream: scaling to a percentile
    # instead (even 99.5) flattened the top of the list -- eleven moments all
    # scored exactly 1.00 and the ranking said nothing. The single best second
    # is the honest ceiling. Smoothing has already removed lone odd seconds.
    #
    # The best *unmarked* moment sets that ceiling; your markers then go on
    # top. On the creator's first League stream with the Companion, 8 markers
    # set the ceiling instead and pushed every other moment under the quality
    # bar: 8 clips from 2h15m, all of them marked.
    ceiling = float(unmarked.max()) if unmarked.size else 0.0
    if ceiling <= 1e-6:
        ceiling = float(total.max()) if total.size else 0.0
    if ceiling > 1e-6:
        total = np.clip(total / ceiling, 0.0, 1.0)
    return HypeResult(score=total.astype(np.float32), parts=parts, missing=missing)


def why(parts: dict[str, np.ndarray], second: int, *, top: int = 3) -> list[tuple[str, float]]:
    """The signals that made this second score, strongest first."""
    found = [
        (name, float(values[second]))
        for name, values in parts.items()
        if second < len(values) and values[second] > 0.01
    ]
    found.sort(key=lambda pair: pair[1], reverse=True)
    return found[:top]


def store(conn: sqlite3.Connection, recording_id: int, score: np.ndarray) -> None:
    """Save the score as a signal of its own, replacing any earlier one."""
    conn.execute("DELETE FROM signals WHERE recording_id = ? AND name = ?",
                 (recording_id, HYPE_SIGNAL))
    conn.executemany(
        "INSERT INTO signals (recording_id, t_sec, name, value) VALUES (?, ?, ?, ?)",
        ((recording_id, t, HYPE_SIGNAL, float(v)) for t, v in enumerate(score) if v > 0.005),
    )
    conn.commit()


def _spread(values: np.ndarray, scoring) -> np.ndarray:
    """A League event lifts the fight before it (event_lookback_sec), at its own size."""
    out = np.zeros(len(values), dtype=np.float32)
    for second in np.nonzero(values)[0]:
        one = np.zeros(len(values), dtype=np.float32)
        one[second] = 1.0
        curve = marker_curve(one, lookback_sec=scoring.event_lookback_sec,
                             lookahead_sec=scoring.event_lookahead_sec)
        out = np.maximum(out, curve * float(min(1.0, values[second])))
    return out


def build(conn: sqlite3.Connection, settings: Settings, recording_id: int,
          seconds: int) -> HypeResult:
    """Score a recording second by second and store the result."""
    from .game_events import for_recording

    league = for_recording(conn, recording_id, seconds)
    result = hype_score(load_signals(conn, recording_id, seconds), settings, seconds,
                        downtime=league.downtime)
    store(conn, recording_id, result.score)
    return result
