"""Global hotkeys for marking moments (spec section 7.1).

How this stays safe for your game accounts (spec section 6): it asks Windows
to tell us when one specific key combination is pressed, using the same
standard Windows feature Discord and OBS use for their own hotkeys. It does
not watch the keyboard, does not read any other key, and is not connected to
any game. Windows delivers the press to this program and nowhere else.

The cost of that safety: while the Companion is running, the key it registered
belongs to it, so no other program sees that key. Pick keys your games don't
use. Numpad + and Numpad - are good choices.

One limit worth knowing: a game started as administrator can stop Windows
delivering the press. If a marker doesn't appear, run the Companion as
administrator too (manual chapter 25).
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

from ..errors import HotkeyUnavailable
from ..logging_setup import get_logger

log = get_logger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000  # holding the key down marks once, not hundreds of times

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MODIFIERS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "windows": MOD_WIN,
}

# Keys that can be told apart from any other key. Numpad Enter is deliberately
# missing: Windows cannot separate it from the main Enter key here, so
# registering it would take Enter away from every program.
NAMED_KEYS = {
    "numpad+": 0x6B, "numpadplus": 0x6B, "add": 0x6B,
    "numpad-": 0x6D, "numpadminus": 0x6D, "subtract": 0x6D,
    "numpad*": 0x6A, "multiply": 0x6A,
    "numpad/": 0x6F, "divide": 0x6F,
    "numpad.": 0x6E, "decimal": 0x6E,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "space": 0x20, "pause": 0x13, "scrolllock": 0x91,
}
NAMED_KEYS.update({f"numpad{n}": 0x60 + n for n in range(10)})
NAMED_KEYS.update({f"f{n}": 0x6F + n for n in range(1, 25)})  # F1 = 0x70 ... F24 = 0x87


@dataclass(frozen=True)
class Hotkey:
    modifiers: int
    key: int
    text: str  # what the creator typed, for messages


def parse_hotkey(text: str) -> Hotkey:
    """"numpad+", "ctrl+alt+m", "f13" -> what Windows needs."""
    cleaned = text.strip().lower().replace(" ", "")
    if not cleaned:
        raise HotkeyUnavailable("No key has been set")
    # Split on + without losing a trailing "+" as the key itself.
    parts: list[str] = []
    for piece in cleaned.split("+"):
        if piece:
            parts.append(piece)
        elif parts:
            parts[-1] += "+"
    if not parts:
        raise HotkeyUnavailable(f"'{text}' is not a key AI-Editor can use")

    modifiers = 0
    for part in parts[:-1]:
        if part not in MODIFIERS:
            raise HotkeyUnavailable(f"'{part}' in '{text}' is not Ctrl, Alt, Shift or Win")
        modifiers |= MODIFIERS[part]
    name = parts[-1]
    if name in NAMED_KEYS:
        key = NAMED_KEYS[name]
    elif len(name) == 1 and (name.isalpha() or name.isdigit()):
        key = ord(name.upper())
    elif name in ("enter", "return", "numpadenter"):
        raise HotkeyUnavailable(
            "Windows can't tell the numpad's Enter apart from the main Enter key, so "
            "AI-Editor would take Enter away from your games. Numpad + or Numpad - "
            "work well instead"
        )
    else:
        raise HotkeyUnavailable(f"'{text}' is not a key AI-Editor can use")
    return Hotkey(modifiers | MOD_NOREPEAT, key, text)


def describe(text: str) -> str:
    """"numpad+" -> "Numpad +", for the status panel."""
    pretty = {"numpad+": "Numpad +", "numpad-": "Numpad -", "numpad*": "Numpad *",
              "numpad/": "Numpad /", "numpad.": "Numpad ."}
    cleaned = text.strip().lower().replace(" ", "")
    if cleaned in pretty:
        return pretty[cleaned]
    return " + ".join(part.capitalize() for part in cleaned.split("+") if part)


class HotkeyListener:
    """Registers hotkeys and calls back (on its own thread) when one is pressed.

    Windows only delivers hotkey presses to the thread that registered them,
    and only through a message loop, so that loop lives here.
    """

    def __init__(self, hotkeys: dict[str, str], on_press: Callable[[str], None]) -> None:
        self._wanted = {name: parse_hotkey(text) for name, text in hotkeys.items() if text}
        self._on_press = on_press
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._thread_id: int | None = None
        self.registered: dict[str, Hotkey] = {}
        self.failures: dict[str, str] = {}  # name -> plain-language reason

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(5.0)

    def _run(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        ids: dict[int, str] = {}
        for index, (name, hotkey) in enumerate(self._wanted.items(), start=1):
            if user32.RegisterHotKey(None, index, hotkey.modifiers, hotkey.key):
                ids[index] = name
                self.registered[name] = hotkey
            else:
                self.failures[name] = (
                    f"Another program is already using {describe(hotkey.text)}"
                )
                log.warning("Could not register hotkey %s", hotkey.text)
        self._ready.set()

        message = wintypes.MSG()
        try:
            while True:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result in (0, -1):  # asked to stop, or something went wrong
                    break
                if message.message == WM_HOTKEY:
                    name = ids.get(int(message.wParam))
                    if name:
                        try:
                            self._on_press(name)
                        except Exception:  # noqa: BLE001
                            log.exception("Marker hotkey handler failed")
        finally:
            for index in ids:
                user32.UnregisterHotKey(None, index)

    def stop(self) -> None:
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
