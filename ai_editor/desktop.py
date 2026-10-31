"""AI-Editor in its own window (Phase 4A): the same page as ``ai-editor app``,
without the browser tab and without the black console window.

The page is still served on 127.0.0.1, which only this PC can reach; the
window shows it with WebView2, the Edge engine built into Windows 11. Closing
the window ends AI-Editor: a running job is paused first, and resumes next
time, as when the console window was closed.

* **One window.** Opening AI-Editor again brings the open window to the front.
* **Already open in the browser** (``ai-editor app``): the window shows that
  one, and closing the window leaves it running.
* **No WebView2:** the page opens in the browser instead, and a small message
  box stands in for the console: OK closes AI-Editor.
* **A crash is never silent:** it's written to the log, and a message says so.
"""

from __future__ import annotations

import ctypes
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

from . import __product_name__, __version__
from .config import Settings

MUTEX = "Local\\AI-Editor-window"
FRONT_FILE = "bring-to-front"     # touched by a second start: the open window comes forward
ALREADY_EXISTS = 183
STOP_WAIT_SEC = 10.0               # a running job's time to pause on close
INFO, ERROR = 0x40, 0x10           # message box icons


def message(text: str, *, icon: int = INFO) -> None:
    """A Windows message box: the window's only way to speak without a console."""
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text, __product_name__, icon)


def _quiet_streams() -> None:
    """Without a console, print() and tracebacks have nowhere to go and fail."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115


def _crash_hook(log_path: Path):
    def hook(kind, value, tb):
        import logging

        logging.getLogger("ai_editor.desktop").critical("AI-Editor stopped unexpectedly",
                                                        exc_info=(kind, value, tb))
        message(f"AI-Editor ran into a problem and has to close ({kind.__name__}: {value}).\n\n"
                f"The details are in the log file:\n{log_path}\n\nThe Issues tab can copy them "
                "for you next time.", icon=ERROR)
    return hook


def first_window():
    """A handle that says "the window is open", or None if another one already is."""
    if sys.platform != "win32":
        return object()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, MUTEX)
    if ctypes.get_last_error() == ALREADY_EXISTS:
        return None
    return handle


def front_file(settings: Settings) -> Path:
    return settings.folders.cache / "app" / FRONT_FILE


def ask_to_come_forward(settings: Settings) -> None:
    path = front_file(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(time.time()), encoding="utf-8")


def watch_for_second_start(settings: Settings, window, every: float = 0.5) -> None:
    """Bring the window forward whenever AI-Editor is started again."""
    path = front_file(settings)

    def stamp():
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    seen = stamp()
    while True:
        time.sleep(every)
        now = stamp()
        if now is not None and now != seen:
            seen = now
            try:
                window.restore()
                window.show()
                window.on_top = True    # to the front, then back to normal
                window.on_top = False
            except Exception:  # noqa: BLE001 -- the window may be closing
                pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pause_jobs(worker, wait: float = STOP_WAIT_SEC) -> None:
    """Pause a running job and give it a moment to stop cleanly."""
    from .app.worker import RUNNING

    worker.pause()
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline and any(t.status == RUNNING for t in worker.snapshot()):
        time.sleep(0.2)


def main() -> None:
    """The desktop shortcut: AI-Editor in its own window."""
    _quiet_streams()
    from .config import load_settings
    from .errors import AIEditorError
    from .ffmpeg import configure_tool_paths
    from .logging_setup import setup_logging

    try:
        settings = load_settings()
    except AIEditorError as exc:
        message(exc.user_message(), icon=ERROR)
        return
    configure_tool_paths(settings.tools.ffmpeg_dir)
    log_path = setup_logging(settings.log_dir, settings.logging.level)
    sys.excepthook = _crash_hook(log_path)

    from .childproc import hide_consoles

    hide_consoles()
    window_open = first_window()
    if window_open is None:
        ask_to_come_forward(settings)
        return

    from .app import window as app_window
    from .logging_setup import get_logger

    log = get_logger(__name__)
    port = app_window.PORT
    running = app_window.already_running(port)
    ui = worker = None
    if running is None:            # another program has the usual port
        port = free_port()
    if not running:
        ui, worker = app_window.start(settings, port=port, open_browser=False)
    url = app_window.url_for(port)
    log.info("%s %s in its own window, at %s", __product_name__, __version__, url)
    try:
        import webview

        win = webview.create_window(__product_name__, url, width=1512, height=982,
                                    min_size=(1100, 760), background_color="#0b0b10")
        threading.Thread(target=watch_for_second_start, args=(settings, win),
                         name="ai-editor-front", daemon=True).start()
        webview.start()            # returns when the window is closed
    except Exception as exc:  # noqa: BLE001 -- no WebView2: the browser, as before
        log.warning("Couldn't open AI-Editor's own window (%s); using the browser", exc)
        webbrowser.open(url)
        message("AI-Editor couldn't open its own window, so it opened in your browser "
                "instead.\n\nKeep this message open while you use AI-Editor. Click OK to close "
                "AI-Editor.")
    finally:
        if worker is not None:
            pause_jobs(worker)
        if ui is not None:
            ui.close()
