"""League events as signals, reasons and match times (Phase 2E-2).

The Stream Companion logs what League's own API says happened
(companion/league.py); link_recording places each event in the recording.
From there they work like everything else analysis hears:

* **Signals**, one value at the second each event happened, written at
  import like your markers: your kills (lol_kill), multikills (lol_multikill,
  bigger for a bigger streak), your team's objectives and steals
  (lol_objective), aces (lol_ace), your deaths (lol_death: they only count
  when you react, see hype.py) and how many champions die around a moment
  (lol_fight: a team fight). hype.py spreads each over the fight leading up
  to it, the way a marker is spread over the minute before the press.
* **Reasons** in words, for the Review and Clips tabs: "Triple kill",
  "Baron steal". The creator's ask: any kill is a reason, from a single kill
  to a penta.
* **When matches run**, so queue, champion select, loading and the
  post-game lobby are never picked unless marked (the creator's choice,
  2026-10-10), and clips don't run across a match's start or end.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from ..companion.league import LEAGUE, MULTIKILLS

SIGNALS = ("lol_kill", "lol_multikill", "lol_objective", "lol_ace", "lol_death", "lol_fight")
# How much each objective is worth (0-1), and anything stolen counts fully.
OBJECTIVE_VALUE = {"Baron": 1.0, "Elder Dragon": 1.0, "Atakhan": 0.8, "Rift Herald": 0.6,
                   "Voidgrub": 0.3, "Turret": 0.3, "Inhibitor": 0.5}
DRAGON_VALUE = 0.7
# Champion kills, anyone's, at one second for lol_fight: four is a full fight.
FIGHT_FULL = 4.0
FIGHT_WINDOW_SEC = 8
# The match is still on screen for the Victory or Defeat banner after GameEnd.
END_SCREEN_SEC = 6.0
# Queue, champion select and loading take a few minutes. A longer gap between
# logged matches is more likely a match the Companion missed (closed, or
# started late), so it's scored as usual rather than thrown away.
MAX_DOWNTIME_SEC = 12 * 60
CHAMPION_KILLS = ("kill", "death", "assist", "team_kill", "enemy_kill")


def objective_value(event: dict) -> float:
    monster = str(event.get("monster") or "")
    if event.get("stolen"):
        return 1.0
    return OBJECTIVE_VALUE.get(monster, DRAGON_VALUE if "Dragon" in monster else 0.5)


def counts_for_us(event: dict) -> bool:
    """An objective that's good for you: your team's monster, a building you
    took yourself, or anything stolen by your side."""
    if event.get("kind") != "objective":
        return False
    if event.get("by_me"):
        return True
    building = event.get("monster") in ("Turret", "Inhibitor")
    return bool(event.get("ours")) and not building


def big(event: dict) -> bool:
    """A moment big enough for an effect and a Short suggestion on its own:
    your multikills, your team's aces, and steals by your side."""
    kind = event.get("kind")
    return (kind == "multikill" or kind == "ace"
            or (kind == "objective" and bool(event.get("stolen")) and counts_for_us(event)))


def signal_values(events: list[tuple[float, dict]], seconds: int) -> dict[str, dict[int, float]]:
    """{signal name: {second: value}} for a recording's events."""
    out: dict[str, dict[int, float]] = defaultdict(dict)

    def put(name: str, t: float, value: float) -> None:
        second = int(t)
        if 0 <= second < seconds:
            out[name][second] = max(out[name].get(second, 0.0), value)

    for t, event in events:
        kind = event.get("kind")
        if kind == "kill":
            put("lol_kill", t, 1.0)
        elif kind == "multikill":
            put("lol_multikill", t, min(1.0, 0.25 + 0.25 * (int(event.get("streak") or 2) - 1)))
        elif kind == "ace":
            put("lol_ace", t, 1.0)
        elif counts_for_us(event):
            put("lol_objective", t, objective_value(event))
        elif kind == "death":
            put("lol_death", t, 1.0)
    # A team fight: how many champions die within a few seconds of each other.
    kills = sorted(t for t, e in events if e.get("kind") in CHAMPION_KILLS)
    for t in kills:
        near = sum(1 for k in kills if abs(k - t) <= FIGHT_WINDOW_SEC)
        put("lol_fight", t, min(1.0, near / FIGHT_FULL))
    return dict(out)


def store_signals(conn: sqlite3.Connection, recording_id: int, events: list[tuple[float, dict]],
                  seconds: int) -> int:
    """Replace the recording's League signals with these events'. How many were written."""
    conn.executemany("DELETE FROM signals WHERE recording_id = ? AND name = ?",
                     [(recording_id, name) for name in SIGNALS])
    written = 0
    for name, values in signal_values(events, seconds).items():
        conn.executemany(
            "INSERT OR REPLACE INTO signals (recording_id, t_sec, name, value) VALUES (?, ?, ?, ?)",
            [(recording_id, t, name, v) for t, v in values.items()])
        written += len(values)
    return written


# --- In words ---------------------------------------------------------------------------


def reasons(events: list[tuple[float, dict]]) -> list[str]:
    """What a clip's League events say about it, biggest first: "Triple kill",
    "2 kills", "Baron steal", "Ace", "Victory"."""
    found: list[tuple[int, str]] = []
    streak = max((int(e.get("streak") or 0) for _, e in events if e.get("kind") == "multikill"),
                 default=0)
    kills = sum(1 for _, e in events if e.get("kind") == "kill")
    if streak >= 2:
        found.append((100 + streak, MULTIKILLS.get(streak, f"{streak} kills")))
        extra = kills - streak
        if extra > 0:
            found.append((50, f"+{extra} kill{'s' if extra != 1 else ''}"))
    elif kills:
        found.append((50 + kills, "Kill" if kills == 1 else f"{kills} kills"))
    if any(e.get("kind") == "ace" for _, e in events):
        found.append((90, "Ace"))
    if any(e.get("kind") == "first_blood" for _, e in events):
        found.append((60, "First blood"))
    for _, e in events:
        if counts_for_us(e) and e.get("monster") not in ("Turret", "Inhibitor", "Voidgrub"):
            label = f"{e.get('monster')} steal" if e.get("stolen") else str(e.get("monster"))
            found.append((95 if e.get("stolen") else 70, label))
    if any(e.get("kind") == "game_end" and e.get("result") == "win" for _, e in events):
        found.append((80, "Victory"))
    deaths = sum(1 for _, e in events if e.get("kind") == "death")
    if deaths:
        found.append((10, "Death" if deaths == 1 else f"{deaths} deaths"))
    seen, out = set(), []
    for _, label in sorted(found, key=lambda pair: -pair[0]):
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out


def within(events: list[tuple[float, dict]], start: float, end: float) -> list[tuple[float, dict]]:
    return [(t, e) for t, e in events if start <= t <= end]


# --- When matches run --------------------------------------------------------------------


@dataclass
class Span:
    start: float
    end: float


def matches(events: list[tuple[float, dict]], duration: float) -> list[Span]:
    """Each match's stretch of the recording, from the game loading in to its end screen.

    A match whose start came before the recording begins at 0; one still
    going when the recording stopped runs to its end.
    """
    by_match: dict[str, list[tuple[float, dict]]] = defaultdict(list)
    for t, e in events:
        by_match[str(e.get("match"))].append((t, e))
    spans = []
    for found in by_match.values():
        found.sort(key=lambda pair: pair[0])
        first_t, first = found[0]
        # The game clock says how long before its first logged event the match began.
        start = max(0.0, first_t - float(first.get("game_time") or 0.0))
        ends = [t for t, e in found if e.get("kind") == "game_end"]
        end = min(duration, ends[-1] + END_SCREEN_SEC) if ends else duration
        spans.append(Span(start, max(start, end)))
    return sorted(spans, key=lambda s: s.start)


def boundaries(spans: list[Span], duration: float) -> list[float]:
    """Where matches start and end, as places a clip must not cross."""
    out = []
    for s in spans:
        if s.start > 0:
            out.append(s.start)
        if s.end < duration:
            out.append(s.end)
    return out


def downtime(spans: list[Span], seconds: int,
             league_parts: list[tuple[float, float]] | None = None) -> np.ndarray:
    """True for each second of League time that's outside a match: queue,
    champion select, loading, the post-game lobby. ``league_parts`` are the
    stretches where League is on screen (from the OBS scenes); None: all of it."""
    out = np.zeros(seconds, dtype=bool)
    for start, end in league_parts if league_parts is not None else [(0.0, float(seconds))]:
        out[max(0, int(start)):min(seconds, int(np.ceil(end)))] = True
    for span in spans:
        out[max(0, int(span.start)):min(seconds, int(np.ceil(span.end)))] = False
    edges = np.diff(np.concatenate(([0], out.astype(np.int8), [0])))
    for begin, finish in zip(np.nonzero(edges == 1)[0], np.nonzero(edges == -1)[0]):
        if finish - begin > MAX_DOWNTIME_SEC:
            out[begin:finish] = False
    return out


@dataclass
class RecordingEvents:
    events: list[tuple[float, dict]]
    spans: list[Span]
    downtime: np.ndarray | None
    cuts: list[float]


def for_recording(conn: sqlite3.Connection, recording_id: int, seconds: int) -> RecordingEvents:
    """Everything the League events say about one recording. Empty without events."""
    from ..companion.link import game_spans, game_timeline, league_events

    events = league_events(conn, recording_id)
    if not events:
        return RecordingEvents([], [], None, [])
    spans = matches(events, float(seconds))
    timeline = game_timeline(conn, recording_id)
    parts = ([(s, e) for s, e, g in game_spans(timeline, float(seconds)) if g == LEAGUE]
             if timeline else None)
    return RecordingEvents(events, spans, downtime(spans, seconds, parts),
                           boundaries(spans, float(seconds)))
