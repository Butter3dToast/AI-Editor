"""Matching a session log to the footage it belongs to (spec sections 7.1, 7.2).

When a recording is imported, this works out which Stream Companion session
produced it. That gives two things the rest of AI-Editor wants badly:

* **Your markers**, as moments in the recording's own timeline. They are the
  strongest highlight signal there is, because you chose them yourself.
* **Where the recording sits inside the Twitch VOD**, so chat lines up without
  anyone typing --starts-at.
* **League events** (kills, objectives, the result), logged from the game's
  own API while you played (league.py, Phase 2E).

Matching is by file first: OBS tells the Companion the exact file it is
writing, so that is proof. Times are the fallback, for recordings made before
the Companion existed, remuxed to another format, or moved.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..logging_setup import get_logger

log = get_logger(__name__)

# How far apart a recording and a session may start and still be the same one.
# OBS writes the file when recording starts, so in practice they agree to the
# second; this is slack for clock drift and for files copied from elsewhere.
TIME_TOLERANCE_SEC = 180.0

MARKER_SIGNALS = {"marker": "marker", "marker_short": "marker_short"}


@dataclass
class SessionMatch:
    session_id: str
    started_at: datetime
    stream_offset_sec: float | None  # how far into the stream this recording began
    matched_by: str  # "file" or "time"
    markers: int = 0
    short_markers: int = 0
    games: list[str] = field(default_factory=list)  # in the order they were played
    league: list[tuple[float, dict]] = field(default_factory=list)  # league_events()

    @property
    def marker_total(self) -> int:
        return self.markers + self.short_markers


def _started_events(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM companion_events WHERE event_type = 'obs_record_started' "
        "ORDER BY wall_clock"
    ).fetchall()


def _payload_path(row: sqlite3.Row) -> Path | None:
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except ValueError:
        return None
    path = payload.get("path")
    return Path(path) if path else None


def _same_file(logged: Path | None, source: Path) -> bool:
    # Same file, or the same recording remuxed (OBS can turn .mkv into .mp4).
    return logged is not None and (logged == source or logged.stem == source.stem)


def find_session(
    conn: sqlite3.Connection,
    *,
    source_file: Path,
    started_at: datetime | list[datetime] | None,
    recording_id: int | None = None,
) -> SessionMatch | None:
    """Which recording period in the session log produced this file.

    ``started_at``: when the recording began, or several guesses at it; the
    closest within TIME_TOLERANCE_SEC wins. A recording period already tied to
    another recording is never matched by time.
    """
    rows = _started_events(conn)
    if not rows:
        return None

    source = Path(source_file)
    for row in rows:
        if _same_file(_payload_path(row), source):
            return _match(row, "file")
    # A Companion that noticed the recording late (6-10 Oct 2026) hears its file
    # only when it stops: the recording period is the last start before that.
    for stop in conn.execute("SELECT * FROM companion_events WHERE event_type = "
                             "'obs_record_stopped' ORDER BY wall_clock").fetchall():
        if _same_file(_payload_path(stop), source):
            began = [r for r in rows if r["session_id"] == stop["session_id"]
                     and r["wall_clock"] <= stop["wall_clock"]]
            if began:
                return _match(began[-1], "file")

    guesses = [started_at] if isinstance(started_at, datetime) else list(started_at or [])
    best, best_gap = None, TIME_TOLERANCE_SEC
    for row in rows:
        if row["recording_id"] is not None and row["recording_id"] != recording_id:
            continue
        logged = datetime.fromisoformat(row["wall_clock"])
        for guess in guesses:
            gap = abs((logged - guess).total_seconds())
            if gap <= best_gap:
                best, best_gap = row, gap
    return _match(best, "time") if best is not None else None


def _match(row: sqlite3.Row, how: str) -> SessionMatch:
    return SessionMatch(
        session_id=row["session_id"],
        started_at=datetime.fromisoformat(row["wall_clock"]),
        stream_offset_sec=row["stream_time_sec"],
        matched_by=how,
    )


def started_at_of(source_file: Path, duration_sec: float | None) -> datetime | None:
    """When a recording began, guessed from the file: it is finished when written."""
    path = Path(source_file)
    if not path.exists():
        return None
    finished = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return finished - timedelta(seconds=duration_sec or 0)


# OBS names a recording after when it started, in the PC's own time:
# "2026-10-08 19-55-02.mkv".
_OBS_NAME = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ _](\d{2})-(\d{2})-(\d{2})")


def started_from_name(source_file: Path) -> datetime | None:
    """When OBS started the recording, from its file name; None for other names."""
    found = _OBS_NAME.search(Path(source_file).stem)
    if not found:
        return None
    try:
        return datetime(*map(int, found.groups())).astimezone(timezone.utc)
    except (ValueError, OSError):
        return None


def start_guesses(row: sqlite3.Row) -> list[datetime]:
    """Every fair guess at when a recording began, best first.

    OBS's file name is when it started. The date inside an OBS .mkv is when it
    *finished* (it is written last), so for OBS files that, less the length, is
    a guess too. A Twitch download's date is its real start.
    """
    duration = timedelta(seconds=row["duration_sec"] or 0)
    guesses = [started_from_name(Path(row["source_file"]))]
    if row["recorded_at"]:
        try:
            dated = datetime.fromisoformat(row["recorded_at"])
        except ValueError:
            dated = None
        if dated is not None:
            guesses.append(dated)
            if row["source_type"] == "local_obs":
                guesses.append(dated - duration)
    guesses.append(started_at_of(Path(row["source_file"]), row["duration_sec"]))
    return [g if g.tzinfo else g.replace(tzinfo=timezone.utc) for g in guesses if g is not None]


def found_text(match: SessionMatch | None) -> str:
    """What linking found, for the Jobs list: said either way (10 Oct: nothing
    told the creator their marks were missing)."""
    if match is None:
        return ("No Stream Companion log matched this recording, so none of your marks are in "
                "its clips. (Was the Companion running while you recorded?)")
    text = (f"Stream Companion log found: {match.markers} highlight mark(s) and "
            f"{match.short_markers} Shorts mark(s)")
    if match.games:
        text += f"; games played: {', '.join(match.games)}"
    if match.league:
        text += f"; League events: {league_summary(match.league)}"
    return text + "."


def unlinked_with_log(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Recordings with no session yet that one in the log would match now."""
    rows = conn.execute("SELECT * FROM recordings WHERE session_id IS NULL ORDER BY id").fetchall()
    return [r for r in rows if find_session(conn, source_file=Path(r["source_file"]),
                                             started_at=start_guesses(r), recording_id=r["id"])]


def link_recording(conn: sqlite3.Connection, recording_id: int) -> SessionMatch | None:
    """Tie a recording to its session, and turn its markers into signals.

    Safe to run again: the markers are rewritten, not added twice.
    """
    row = conn.execute(
        "SELECT source_file, source_type, duration_sec, recorded_at FROM recordings WHERE id = ?",
        (recording_id,),
    ).fetchone()
    if row is None:
        return None

    match = find_session(conn, source_file=Path(row["source_file"]),
                         started_at=start_guesses(row), recording_id=recording_id)
    if match is None:
        return None

    # The recording ends when it stops, or when the footage runs out.
    ends_at = match.started_at + timedelta(seconds=(row["duration_sec"] or 0) + 1)
    markers = conn.execute(
        "SELECT * FROM companion_events WHERE session_id = ? AND event_type IN "
        "('marker', 'marker_short') AND wall_clock >= ? AND wall_clock <= ? "
        "AND recording_time_sec IS NOT NULL ORDER BY wall_clock",
        (match.session_id, match.started_at.isoformat(timespec="milliseconds"),
         ends_at.isoformat(timespec="milliseconds")),
    ).fetchall()

    conn.execute("UPDATE recordings SET session_id = ? WHERE id = ?",
                 (match.session_id, recording_id))
    conn.execute(
        "UPDATE companion_events SET recording_id = ? WHERE session_id = ? "
        "AND wall_clock >= ? AND wall_clock <= ?",
        (recording_id, match.session_id, match.started_at.isoformat(timespec="milliseconds"),
         ends_at.isoformat(timespec="milliseconds")),
    )
    conn.executemany(
        "DELETE FROM signals WHERE recording_id = ? AND name = ?",
        [(recording_id, name) for name in MARKER_SIGNALS.values()],
    )
    for marker in markers:
        name = MARKER_SIGNALS.get(marker["event_type"])
        if name is None:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO signals (recording_id, t_sec, name, value) VALUES (?, ?, ?, 1)",
            (recording_id, int(marker["recording_time_sec"]), name),
        )
        if name == "marker":
            match.markers += 1
        else:
            match.short_markers += 1

    match.league = league_events(conn, recording_id)
    from ..analysis.game_events import store_signals

    store_signals(conn, recording_id, match.league, int(row["duration_sec"] or 0) + 1)
    # The games played, from the OBS scenes. Fill in the recording's game if
    # none was given at import: the one played longest.
    timeline = game_timeline(conn, recording_id)
    match.games = list(dict.fromkeys(g for _, g in timeline if g))
    main = main_game(timeline, float(row["duration_sec"] or 0))
    if main:
        conn.execute("UPDATE recordings SET game = ? WHERE id = ? AND game IS NULL",
                     (main, recording_id))
    conn.commit()
    log.info("Recording #%s matched session %s by %s (%d markers)",
             recording_id, match.session_id, match.matched_by, match.marker_total)
    return match


# Worth listing for the creator: everything about them, every big fight, the
# monsters, and the buildings they took themselves (the rest are a lot of turrets).
LISTED = {"kill", "death", "assist", "multikill", "ace", "aced", "first_blood", "objective",
          "game_start", "game_end"}


def league_events(conn: sqlite3.Connection, recording_id: int) -> list[tuple[float, dict]]:
    """(seconds into the recording, event) for each League event placed in it, in order."""
    rows = conn.execute(
        "SELECT recording_time_sec, payload_json FROM companion_events WHERE recording_id = ? "
        "AND event_type = 'league' AND recording_time_sec IS NOT NULL "
        "ORDER BY recording_time_sec, id", (recording_id,)).fetchall()
    found = []
    for row in rows:
        try:
            found.append((float(row["recording_time_sec"]), json.loads(row["payload_json"] or "{}")))
        except ValueError:
            continue
    return found


def listed(event: dict) -> bool:
    """Whether the Library lists this League event."""
    if event.get("kind") not in LISTED:
        return False
    if event.get("monster") in ("Turret", "Inhibitor"):
        return bool(event.get("by_me"))
    return True


def league_summary(events: list[tuple[float, dict]]) -> str:
    """"2 matches (1 win), 9/4/12, a triple kill, 3 objectives" for a recording."""
    from .league import MULTIKILLS, Tally

    tally = Tally()
    matches, wins = set(), 0
    for _, event in events:
        tally.add(event)
        matches.add(event.get("match"))
        wins += event.get("kind") == "game_end" and event.get("result") == "win"
    count = len(matches)
    head = f"{count} match{'es' if count != 1 else ''}"
    if wins:
        head += f" ({wins} won)"
    return f"{head}, {tally.text()}"


def game_timeline(conn: sqlite3.Connection, recording_id: int) -> list[tuple[float, str | None]]:
    """(seconds into the recording, game) at each OBS scene change, in order.

    The creator has one OBS scene per game, so the Companion knows when a
    stream moves from Wardogs to Tarkov. Empty if it wasn't running.
    """
    rows = conn.execute(
        "SELECT recording_time_sec, payload_json FROM companion_events WHERE recording_id = ? "
        "AND event_type = 'obs_scene' AND recording_time_sec IS NOT NULL ORDER BY recording_time_sec, id",
        (recording_id,),
    ).fetchall()
    return [(float(r["recording_time_sec"]), json.loads(r["payload_json"] or "{}").get("game"))
            for r in rows]


def game_at(timeline: list[tuple[float, str | None]], t: float) -> str | None:
    """The game on screen at ``t`` seconds, per the timeline."""
    current = timeline[0][1] if timeline else None
    for at, game in timeline:
        if at > t:
            break
        current = game
    return current


def scene_span(timeline: list[tuple[float, str | None]], t: float,
               duration: float) -> tuple[float, float, str | None]:
    """The stretch around ``t`` with the same game on screen: (start, end, game).

    Several scenes in a row that aren't a game ("Starting Soon", "BRB") count
    as one stretch, as do two scenes of the same game.
    """
    if not timeline:
        return 0.0, duration, None
    index = max((i for i, (at, _) in enumerate(timeline) if at <= t), default=0)
    game = timeline[index][1]
    first = index
    while first > 0 and timeline[first - 1][1] == game:
        first -= 1
    last = index
    while last + 1 < len(timeline) and timeline[last + 1][1] == game:
        last += 1
    start = 0.0 if first == 0 else timeline[first][0]
    end = timeline[last + 1][0] if last + 1 < len(timeline) else duration
    return start, end, game


def game_spans(timeline: list[tuple[float, str | None]],
               duration: float) -> list[tuple[float, float, str]]:
    """Every stretch with a game on screen: (start, end, game), in order."""
    found: list[tuple[float, float, str]] = []
    t = 0.0
    while timeline and t < duration:
        start, end, game = scene_span(timeline, t, duration)
        if game:
            found.append((start, end, game))
        t = end if end > t else duration
    return found


def main_game(timeline: list[tuple[float, str | None]], duration: float) -> str | None:
    """The game played for longest in a recording."""
    totals: dict[str, float] = {}
    for (at, game), nxt in zip(timeline, timeline[1:] + [(duration, None)]):
        if game:
            totals[game] = totals.get(game, 0.0) + max(0.0, nxt[0] - at)
    return max(totals, key=totals.get) if totals else None


def stream_offset(conn: sqlite3.Connection, recording_id: int) -> float | None:
    """How far into the stream this recording began, if the Companion saw it."""
    row = conn.execute(
        "SELECT e.stream_time_sec FROM companion_events e JOIN recordings r "
        "ON r.session_id = e.session_id WHERE r.id = ? AND e.event_type = 'obs_record_started' "
        "AND e.recording_id = ? AND e.stream_time_sec IS NOT NULL ORDER BY e.wall_clock LIMIT 1",
        (recording_id, recording_id),
    ).fetchone()
    return None if row is None else float(row["stream_time_sec"])
