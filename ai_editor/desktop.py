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


# --- Where the window was (4B): opened again where you left it ---------------------

SIZE = {"width": 1512, "height": 982}


def geometry_file(settings: Settings) -> Path:
    return settings.folders.cache / "app" / "window.json"


def _read_geometry(settings: Settings) -> dict:
    import json

    try:
        return json.loads(geometry_file(settings).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def saved_geometry(settings: Settings, screens=None) -> dict:
    """Where the window was last time, if it's still on a screen; else the usual size.

    Maximised last time: maximised again, and the restore button goes back to the
    size it had before (1 Nov: the maximised size was kept as the normal size, so
    restore had nothing smaller to go back to).
    """
    found = _read_geometry(settings)
    maximized = {"maximized": True} if found.get("maximized") else {}
    try:
        x, y, width, height = (int(found[k]) for k in ("x", "y", "width", "height"))
    except (ValueError, KeyError, TypeError):
        return {**SIZE, **maximized}
    if screens is None:
        try:
            import webview

            screens = webview.screens
        except Exception:  # noqa: BLE001 -- no screens to ask: the usual size
            screens = []
    # The title bar must be on a screen (a second monitor may have gone).
    on = [s for s in screens if s.x <= x + 100 <= s.x + s.width and s.y <= y + 10 <= s.y + s.height]
    if not on or width < 600 or height < 400:
        return {**SIZE, **maximized}
    if width >= on[0].width:   # a maximised window kept before 0.39.0
        return {**SIZE, "maximized": True}
    return {"x": x, "y": y, "width": width, "height": height, **maximized}


def track_state(window, maximized: bool = False) -> dict:
    """Follow the window being maximised, minimised and restored, for keep_geometry."""
    state = {"maximized": maximized, "minimized": False}
    window.events.maximized += lambda: state.update(maximized=True, minimized=False)
    window.events.minimized += lambda: state.update(minimized=True)
    window.events.restored += lambda: state.update(maximized=False, minimized=False)
    return state


def keep_geometry(settings: Settings, window, state: dict | None = None) -> None:
    """window.events.closing: remember where the window is.

    Only its normal size and place: maximised or minimised, the window's size is
    the screen's (or nowhere), so the normal one from before is kept with a note.
    """
    import json

    state = state or {}
    try:
        if state.get("maximized") or state.get("minimized"):
            found = {k: v for k, v in _read_geometry(settings).items()
                     if k in ("x", "y", "width", "height")}
        else:
            found = {"x": window.x, "y": window.y, "width": window.width, "height": window.height}
        if state.get("maximized"):
            found["maximized"] = True
        path = geometry_file(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(found), encoding="utf-8")
    except Exception:  # noqa: BLE001 -- only a convenience
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


# --- The starting screen (0.38.1) ---------------------------------------------------
# The window opens at once with this, and the bar moves as each real step
# finishes; the page replaces it when it's ready. Colours from the Phase 4
# design (mockups/theme.css), dark or light as Windows is set.

STARTING = """<!doctype html><html class="THEME_HERE"><head><meta charset="utf-8"><style>
:root{--bg:#111113;--ink:#ececef;--dim:#8d9099;--track:rgba(255,255,255,.08);--accent:#a78bfa;
--bad:#f87171}
@media (prefers-color-scheme: light){:root:not(.dark){--bg:#f7f7f8;--ink:#18181b;--dim:#6b6e78;
--track:rgba(0,0,0,.09);--accent:#6d28d9;--bad:#b91c1c}}
:root.light{--bg:#f7f7f8;--ink:#18181b;--dim:#6b6e78;--track:rgba(0,0,0,.09);--accent:#6d28d9;
--bad:#b91c1c}
html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--ink);font-family:"Segoe UI",system-ui,sans-serif;
display:flex;align-items:center;justify-content:center;-webkit-font-smoothing:antialiased;
cursor:default;user-select:none}
.box{width:320px;display:flex;flex-direction:column;gap:14px}
h1{margin:0;font-size:21px;font-weight:600;letter-spacing:-.3px}
.bar{height:4px;border-radius:2px;background:var(--track);overflow:hidden}
.bar div{height:100%;width:4%;background:var(--accent);border-radius:2px;
transition:width 2.4s cubic-bezier(.2,.8,.2,1)}
.step{color:var(--dim);font-size:13px;min-height:20px}
.step.bad{color:var(--bad)}
.ver{color:var(--dim);font-size:12px;margin-top:18px}
</style></head><body><div class="box">
<h1>Starting AI-Editor</h1>
<div class="bar"><div id="fill"></div></div>
<div class="step" id="step">Opening the window</div>
<div class="ver">VERSION_HERE</div>
</div><script>
window.step = function (fraction, text, bad) {
  document.getElementById("fill").style.width = Math.round(fraction * 100) + "%";
  var s = document.getElementById("step");
  s.textContent = text;
  s.className = bad ? "step bad" : "step";
};
</script></body></html>"""

# The steps, and how far along the bar each one ends. Loading the editor is the
# long one (about 3.5 s: Gradio and the screens), so the bar glides into it.
STEPS = (("Loading the editor", 0.62), ("Opening your library", 0.9), ("Almost there", 0.97))


def starting_page(theme: str = "auto") -> str:
    """``theme``: auto (as Windows is set), light or dark: the one chosen in the window."""
    return STARTING.replace("VERSION_HERE", f"Version {__version__}").replace(
        "THEME_HERE", theme if theme in ("light", "dark") else "auto")


def looks_light(settings: Settings) -> bool:
    theme = settings.appearance.theme
    return theme == "light" or (theme == "auto" and light_windows())


def light_windows() -> bool:
    """Windows' own setting for apps: light or dark (a registry read)."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows"
                            r"\CurrentVersion\Themes\Personalize") as key:
            return bool(winreg.QueryValueEx(key, "AppsUseLightTheme")[0])
    except OSError:
        return False


def show_step(window, fraction: float, text: str, bad: bool = False) -> None:
    """Move the bar on the starting screen. Harmless if the page isn't there yet."""
    import json

    try:
        window.evaluate_js(f"window.step && window.step({fraction}, {json.dumps(text)}, "
                           f"{'true' if bad else 'false'})")
    except Exception:  # noqa: BLE001 -- the starting screen is only decoration
        pass


def boot(settings: Settings, window, started: dict) -> None:
    """Behind the starting screen: load the editor, start the page, show it.
    ``started`` gets the page and the jobs, for closing them later."""
    from .logging_setup import get_logger

    log = get_logger(__name__)
    try:
        show_step(window, STEPS[0][1], STEPS[0][0])
        from .app import window as app_window

        port = app_window.PORT
        running = app_window.already_running(port)
        if running is None:            # another program has the usual port
            port = free_port()
        show_step(window, STEPS[1][1], STEPS[1][0])
        if not running:
            started["ui"], started["worker"] = app_window.start(settings, port=port,
                                                                open_browser=False, frame=True)
        show_step(window, STEPS[2][1], STEPS[2][0])
        url = app_window.url_for(port)
        started["url"] = url
        log.info("%s %s in its own window, at %s", __product_name__, __version__, url)
        window.load_url(url)
    except Exception as exc:  # noqa: BLE001 -- said on the starting screen, written down
        log.exception("AI-Editor couldn't start")
        show_step(window, 1.0, f"AI-Editor couldn't start ({type(exc).__name__}: {exc}). The "
                               "details are in the log file. Close this window and try again.",
                  bad=True)


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

    from .logging_setup import get_logger

    log = get_logger(__name__)
    started: dict = {}
    try:
        import webview

        geometry = saved_geometry(settings)
        win = webview.create_window(__product_name__, html=starting_page(settings.appearance.theme),
                                    min_size=(1100, 760),
                                    background_color="#f7f7f8" if looks_light(settings) else "#111113",
                                    **geometry)
        state = track_state(win, maximized=geometry.get("maximized", False))
        win.events.closing += lambda: keep_geometry(settings, win, state)
        threading.Thread(target=watch_for_second_start, args=(settings, win),
                         name="ai-editor-front", daemon=True).start()
        webview.start(boot, (settings, win, started))   # returns when the window is closed
    except Exception as exc:  # noqa: BLE001 -- no WebView2: the browser, as before
        log.warning("Couldn't open AI-Editor's own window (%s); using the browser", exc)
        if "url" not in started:
            boot(settings, _NoWindow(), started)
        if "url" in started:
            webbrowser.open(started["url"])
            message("AI-Editor couldn't open its own window, so it opened in your browser "
                    "instead.\n\nKeep this message open while you use AI-Editor. Click OK to "
                    "close AI-Editor.")
    finally:
        if started.get("worker") is not None:
            pause_jobs(started["worker"])
        if started.get("ui") is not None:
            started["ui"].close()


class _NoWindow:
    """Stands in for the window when there's none: the browser fallback."""

    def evaluate_js(self, script):
        pass

    def load_url(self, url):
        pass
