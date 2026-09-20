"""The session log: what OBS did, and exactly when (spec section 7.1).

A session runs from the moment OBS starts streaming or recording until both
have stopped. Each row in companion_events carries this PC's clock time, the
anchor that lines everything up with footage later, plus how far into the
stream and the recording OBS was at that moment, taken from OBS itself.

The one number that matters most for a recording made while streaming: the
stream time when the recording started. That is how far into the Twitch VOD
the recording begins, so chat (and markers) line up without guessing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .. import db

OUTPUTS = ("stream", "record")

# A resumed connection that finds the recording this much shorter than when
# the connection dropped means OBS started a new one in the meantime.
RESTART_TOLERANCE_SEC = 2.0

# How stale a session may be and still be picked up when the Companion starts.
# Long enough to cover closing it by accident mid-stream, short enough that
# yesterday's unfinished session never swallows today's recording.
RESUME_WITHIN_HOURS = 12.0


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class OutputState:
    active: bool = False
    paused: bool = False
    started_wall: datetime | None = None  # when this output's time 0 was, by this PC's clock
    last_duration_sec: float = 0.0
    path: str | None = None


@dataclass
class SessionLog:
    db_path: Path
    now: Callable[[], datetime] = utc_now
    session_id: str | None = None
    outputs: dict[str, OutputState] = field(
        default_factory=lambda: {name: OutputState() for name in OUTPUTS}
    )
    events_logged: int = 0

    @property
    def active(self) -> bool:
        return any(state.active for state in self.outputs.values())

    # --- Writing -----------------------------------------------------------

    def log(
        self,
        event_type: str,
        *,
        wall: datetime | None = None,
        stream_sec: float | None = None,
        record_sec: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self.session_id is None:
            self.session_id = (wall or self.now()).astimezone().strftime("%Y%m%d-%H%M%S")
        with db.session(self.db_path) as conn:
            conn.execute(
                "INSERT INTO companion_events (session_id, event_type, wall_clock, "
                "stream_time_sec, recording_time_sec, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self.session_id,
                    event_type,
                    (wall or self.now()).isoformat(timespec="milliseconds"),
                    _round(stream_sec),
                    _round(record_sec),
                    json.dumps(payload) if payload else None,
                ),
            )
        self.events_logged += 1

    # --- OBS says an output changed -----------------------------------------

    def started(
        self,
        output: str,
        duration_sec: float,
        *,
        other_sec: float | None = None,
        path: str | None = None,
        noticed_late: bool = False,
    ) -> None:
        """``duration_sec``: how far in OBS already is (near 0 unless noticed late).

        ``other_sec``: how far into the *other* output OBS is right now, when
        it is running, which is what lines a recording up with its VOD.
        """
        now = self.now()
        state = self.outputs[output]
        state.active, state.paused = True, False
        state.started_wall = now - timedelta(seconds=duration_sec)
        state.last_duration_sec = duration_sec
        state.path = path or state.path
        payload: dict[str, Any] = {}
        if path:
            payload["path"] = path
        if noticed_late:
            # The Companion was started (or reconnected) after OBS began.
            payload["noticed_late"] = True
        # Time 0 of this output, expressed in the other output's time.
        other_at_start = None if other_sec is None else other_sec - duration_sec
        self.log(
            f"obs_{output}_started",
            wall=state.started_wall,
            stream_sec=0.0 if output == "stream" else other_at_start,
            record_sec=0.0 if output == "record" else other_at_start,
            payload=payload,
        )

    def stopped(
        self, output: str, *, other_sec: float | None = None, path: str | None = None,
        noticed_late: bool = False,
    ) -> None:
        state = self.outputs[output]
        if not state.active:
            return
        now = self.now()
        payload: dict[str, Any] = {}
        if path or state.path:
            payload["path"] = path or state.path
        if noticed_late:
            payload["noticed_late"] = True
        length = (now - state.started_wall).total_seconds() if state.started_wall else None
        self.log(
            f"obs_{output}_stopped",
            wall=now,
            stream_sec=length if output == "stream" else other_sec,
            record_sec=length if output == "record" else other_sec,
            payload=payload,
        )
        self.outputs[output] = OutputState()
        if not self.active:
            self.session_id = None  # the next start begins a new session

    def paused(self, paused: bool, record_sec: float, stream_sec: float | None = None) -> None:
        state = self.outputs["record"]
        if not state.active or state.paused == paused:
            return
        state.paused = paused
        state.last_duration_sec = record_sec
        self.log("obs_record_paused" if paused else "obs_record_resumed",
                 record_sec=record_sec, stream_sec=stream_sec)

    def mark(self, kind: str, *, record_sec: float | None = None,
             stream_sec: float | None = None) -> bool:
        """Log a marker. False means OBS wasn't recording, so it can't be placed."""
        placeable = record_sec is not None or stream_sec is not None
        self.log(kind, record_sec=record_sec, stream_sec=stream_sec,
                 payload=None if placeable else {"while_idle": True})
        return placeable

    def file_changed(self, path: str, record_sec: float | None = None) -> None:
        """OBS split the recording into a new file (automatic file splitting)."""
        self.outputs["record"].path = path
        self.log("obs_record_file_changed", record_sec=record_sec, payload={"path": path})

    # --- Catching up after (re)connecting ------------------------------------

    def sync(self, output: str, active: bool, duration_sec: float, paused: bool = False,
             other_sec: float | None = None) -> None:
        """Bring the log in line with what OBS reports after a (re)connection."""
        state = self.outputs[output]
        if active:
            if state.active and duration_sec + RESTART_TOLERANCE_SEC >= state.last_duration_sec:
                state.last_duration_sec = duration_sec  # the same output carried on
                if output == "record":
                    self.paused(paused, duration_sec)
                return
            if state.active:  # stopped and started again while we weren't connected
                self.stopped(output, noticed_late=True)
            self.started(output, duration_sec, other_sec=other_sec, noticed_late=True)
            self.outputs[output].paused = paused
        elif state.active:
            self.stopped(output, noticed_late=True)

    def resume(self) -> None:
        """Pick up a session that was still going when the Companion last closed.

        Without this, closing the Companion during a recording and starting it
        again logs that recording as if it had just begun.
        """
        with db.session(self.db_path) as conn:
            latest = conn.execute(
                "SELECT session_id, MAX(wall_clock) AS last FROM companion_events "
                "GROUP BY session_id ORDER BY last DESC LIMIT 1"
            ).fetchone()
            if latest is None:
                return
            age_hours = (self.now() - datetime.fromisoformat(latest["last"])).total_seconds() / 3600
            if age_hours > RESUME_WITHIN_HOURS:
                return
            rows = conn.execute(
                "SELECT * FROM companion_events WHERE session_id = ? ORDER BY wall_clock, id",
                (latest["session_id"],),
            ).fetchall()

        outputs = {name: OutputState() for name in OUTPUTS}
        for row in rows:
            for output in OUTPUTS:
                if row["event_type"] == f"obs_{output}_started":
                    payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
                    outputs[output] = OutputState(
                        active=True,
                        started_wall=datetime.fromisoformat(row["wall_clock"]),
                        path=payload.get("path"),
                    )
                elif row["event_type"] == f"obs_{output}_stopped":
                    outputs[output] = OutputState()
        if any(state.active for state in outputs.values()):
            self.outputs = outputs
            self.session_id = latest["session_id"]

    def note_duration(self, output: str, duration_sec: float) -> None:
        if self.outputs[output].active:
            self.outputs[output].last_duration_sec = duration_sec


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 3)
