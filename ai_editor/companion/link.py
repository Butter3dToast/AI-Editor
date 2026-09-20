"""Matching a session log to the footage it belongs to (spec sections 7.1, 7.2).

When a recording is imported, this works out which Stream Companion session
produced it. That gives two things the rest of AI-Editor wants badly:

* **Your markers**, as moments in the recording's own timeline. They are the
  strongest highlight signal there is, because you chose them yourself.
* **Where the recording sits inside the Twitch VOD**, so chat lines up without
  anyone typing --starts-at.

Matching is by file first: OBS tells the Companion the exact file it is
writing, so that is proof. Times are the fallback, for recordings made before
the Companion existed, remuxed to another format, or moved.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
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


def find_session(
    conn: sqlite3.Connection,
    *,
    source_file: Path,
    started_at: datetime | None,
) -> SessionMatch | None:
    """Which recording period in the session log produced this file."""
    rows = _started_events(conn)
    if not rows:
        return None

    source = Path(source_file)
    for row in rows:
        logged = _payload_path(row)
        if logged is None:
            continue
        # Same file, or the same recording remuxed (OBS can turn .mkv into .mp4).
        if logged == source or logged.stem == source.stem:
            return _match(row, "file")

    if started_at is None:
        return None
    best, best_gap = None, TIME_TOLERANCE_SEC
    for row in rows:
        gap = abs((datetime.fromisoformat(row["wall_clock"]) - started_at).total_seconds())
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


def link_recording(conn: sqlite3.Connection, recording_id: int) -> SessionMatch | None:
    """Tie a recording to its session, and turn its markers into signals.

    Safe to run again: the markers are rewritten, not added twice.
    """
    row = conn.execute(
        "SELECT source_file, duration_sec, recorded_at FROM recordings WHERE id = ?",
        (recording_id,),
    ).fetchone()
    if row is None:
        return None

    started_at = None
    if row["recorded_at"]:
        try:
            started_at = datetime.fromisoformat(row["recorded_at"])
        except ValueError:
            started_at = None
    if started_at is None:
        started_at = started_at_of(Path(row["source_file"]), row["duration_sec"])

    match = find_session(conn, source_file=Path(row["source_file"]), started_at=started_at)
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
    conn.commit()
    log.info("Recording #%s matched session %s by %s (%d markers)",
             recording_id, match.session_id, match.matched_by, match.marker_total)
    return match


def stream_offset(conn: sqlite3.Connection, recording_id: int) -> float | None:
    """How far into the stream this recording began, if the Companion saw it."""
    row = conn.execute(
        "SELECT e.stream_time_sec FROM companion_events e JOIN recordings r "
        "ON r.session_id = e.session_id WHERE r.id = ? AND e.event_type = 'obs_record_started' "
        "AND e.recording_id = ? AND e.stream_time_sec IS NOT NULL ORDER BY e.wall_clock LIMIT 1",
        (recording_id, recording_id),
    ).fetchone()
    return None if row is None else float(row["stream_time_sec"])
