"""The Stream Companion panel: start it, stop it, see what it's doing (Phase 1H-3).

The Companion runs in a window of its own ("AI-Editor Stream Companion"), so
closing the app window or the browser never stops it mid-stream. The panel
reads the status file it writes each second (companion/status.py).
"""

from __future__ import annotations

import html
import subprocess
import sys
import time
from pathlib import Path

from ..companion import status
from ..config import PROJECT_ROOT, Settings

OBS = {
    "connecting": "connecting to OBS...",
    "connected": "OBS connected",
    "waiting": "waiting for OBS to open",
    "password": "OBS didn't accept the password (manual 7.4)",
    "too_old": "OBS is too old: update it",
}


def status_html(current: dict | None) -> str:
    """One line saying what the Companion is doing."""
    if current is None:
        return ("<div class='aie-companion off'>⚪ <b>Not running.</b> Start it before you go "
                "live or record, so your markers and scene changes are logged.</div>")
    parts = [OBS.get(current.get("obs"), current.get("obs") or "")]
    for output, label in (("stream", "Live"), ("record", "Recording")):
        state = current.get(output) or {}
        if state.get("on"):
            parts.append(f"{label} since {state.get('since') or '?'}"
                         + (" (paused)" if state.get("paused") else ""))
    if current.get("game"):
        parts.append(current["game"])
    elif current.get("scene"):
        parts.append(f"scene \"{current['scene']}\"")
    marked = f"{current.get('markers', 0)} marked, {current.get('shorts', 0)} Short-worthy"
    if current.get("last_marker"):
        marked += f" (last at {current['last_marker']})"
    parts.append(marked)
    problem = current.get("message")
    good = current.get("obs") == "connected"
    return (f"<div class='aie-companion {'on' if good else 'warn'}'>{'🟢' if good else '🟡'} "
            f"<b>Running</b> · " + " · ".join(html.escape(p) for p in parts if p)
            + (f"<div class='aie-error'>{html.escape(problem)}</div>" if problem else "")
            + "</div>")


def start(settings: Settings) -> str:
    """Open the Companion in its own window. A message for the creator."""
    where = status.folder(settings)
    if status.read(where) is not None:
        return "It's already running: see its own window, or the line above."
    status.clear(where)
    program = Path(sys.executable).with_name("ai-editor.exe")
    if not program.is_file():
        return f"Couldn't find {program}. Start it with: ai-editor companion"
    # Its own console, not tied to this window: it keeps going if AI-Editor closes.
    subprocess.Popen([str(program), "companion"], cwd=PROJECT_ROOT,
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return ("Starting in its own window. It's ready when the line above turns green. Leave "
            "that window open while you play; it carries on if you close AI-Editor.")


def stop(settings: Settings, wait_sec: float = 8.0) -> str:
    where = status.folder(settings)
    if status.read(where) is None:
        return "It isn't running."
    status.request_stop(where)
    end = time.monotonic() + wait_sec
    while time.monotonic() < end:
        if status.read(where) is None:
            return "Stream Companion stopped."
        time.sleep(0.25)
    return "Asked it to stop. If its window is still open, close it there."
