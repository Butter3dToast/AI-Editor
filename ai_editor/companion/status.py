"""The Stream Companion's status, for the app window (Phase 1H-3).

The Companion runs in its own window, so it keeps going when the app window
closes. Each second it writes what it's doing to a small file in the cache
folder; the app reads that to show its status, and leaves a "stop" file to
ask it to stop. Both stay on this PC: the Companion still talks to nothing
but OBS.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

STATUS_FILE = "status.json"
STOP_FILE = "stop-requested"
FRESH_SEC = 15.0  # written every second, but connecting to OBS can hold it up a few
WRITE_TRIES = 5
WRITE_RETRY_SEC = 0.02


def folder(settings) -> Path:
    return settings.folders.cache / "companion"


def snapshot(app_) -> dict:
    """What the Companion is doing, as plain values."""
    outputs = {}
    for output in ("record", "stream"):
        state = app_.log.outputs[output]
        outputs[output] = {
            "on": bool(state.active),
            "since": state.started_wall.astimezone().strftime("%H:%M")
            if state.active and state.started_wall else None,
            "paused": bool(state.paused),
        }
    return {
        "updated": time.time(),
        "obs": app_.status.obs,
        "obs_version": app_.status.obs_version,
        "record": outputs["record"],
        "stream": outputs["stream"],
        "scene": app_.scene,
        "game": app_.game,
        "session": app_.log.session_id,
        "markers": app_.markers["moment"],
        "shorts": app_.markers["short"],
        "last_marker": app_.last_marker,
        "message": app_.status.message,
    }


def write(where: Path, status: dict, tries: int = WRITE_TRIES) -> bool:
    """Save the status. False if Windows wouldn't let us this second; never raises.

    Windows refuses to replace a file while another program has it open, and
    the app window opens this one every second to read it. When the two meet,
    try again a moment later; if it's still busy, skip this second (the next
    write is a second away). A missed status line must never stop the Companion.
    """
    temporary = where / (STATUS_FILE + ".tmp")
    try:
        where.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(status), encoding="utf-8")
    except OSError:
        return False
    for attempt in range(tries):
        try:
            os.replace(temporary, where / STATUS_FILE)  # never half-written when read
            return True
        except OSError:
            if attempt + 1 < tries:
                time.sleep(WRITE_RETRY_SEC)
    return False


def read(where: Path, now: float | None = None) -> dict | None:
    """The running Companion's status, or None if it isn't running."""
    try:
        status = json.loads((where / STATUS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    now = time.time() if now is None else now
    return status if now - status.get("updated", 0) <= FRESH_SEC else None


def clear(where: Path) -> None:
    for name in (STATUS_FILE, STOP_FILE):
        (where / name).unlink(missing_ok=True)


def request_stop(where: Path) -> None:
    where.mkdir(parents=True, exist_ok=True)
    (where / STOP_FILE).write_text("stop", encoding="utf-8")


def stop_requested(where: Path) -> bool:
    return (where / STOP_FILE).exists()
