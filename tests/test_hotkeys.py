"""Marker hotkeys: reading what the creator typed, and reserving it with Windows."""

from __future__ import annotations

import sys
import threading

import pytest

from ai_editor.companion.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    HotkeyListener,
    describe,
    parse_hotkey,
)
from ai_editor.errors import HotkeyUnavailable

VK_ADD = 0x6B
VK_SUBTRACT = 0x6D
VK_F13 = 0x7C

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows hotkeys")


@pytest.mark.parametrize(
    "text, modifiers, key",
    [
        ("numpad+", 0, VK_ADD),
        ("Numpad +", 0, VK_ADD),
        ("numpad-", 0, VK_SUBTRACT),
        ("f13", 0, VK_F13),
        ("ctrl+alt+m", MOD_CONTROL | MOD_ALT, ord("M")),
        ("Ctrl+Shift+4", MOD_CONTROL | MOD_SHIFT, ord("4")),
    ],
)
def test_reading_hotkeys(text, modifiers, key):
    hotkey = parse_hotkey(text)
    assert hotkey.key == key
    assert hotkey.modifiers == modifiers | MOD_NOREPEAT


def test_holding_the_key_down_only_marks_once():
    assert parse_hotkey("numpad+").modifiers & MOD_NOREPEAT


def test_numpad_enter_is_refused_with_a_reason():
    with pytest.raises(HotkeyUnavailable, match="Numpad \\+ or Numpad -"):
        parse_hotkey("numpadenter")
    with pytest.raises(HotkeyUnavailable, match="main Enter key"):
        parse_hotkey("enter")


@pytest.mark.parametrize("text", ["", "banana", "ctrl+", "hyper+m", "ctrl+banana"])
def test_keys_windows_cannot_use_are_refused_plainly(text):
    with pytest.raises(HotkeyUnavailable) as caught:
        parse_hotkey(text)
    assert "Traceback" not in caught.value.user_message()
    assert "E053" in caught.value.user_message()


def test_describe_for_the_status_panel():
    assert describe("numpad+") == "Numpad +"
    assert describe("ctrl+alt+m") == "Ctrl + Alt + M"


@windows_only
def test_registers_and_releases_real_windows_hotkeys():
    """Uses keys nothing else is likely to want, and gives them straight back."""
    pressed: list[str] = []
    listener = HotkeyListener(
        {"moment": "ctrl+alt+shift+f23", "short": "ctrl+alt+shift+f24"}, pressed.append
    )
    listener.start()
    try:
        assert set(listener.registered) == {"moment", "short"}, listener.failures
    finally:
        listener.stop()
    assert not any(t.name == "hotkeys" and t.is_alive() for t in threading.enumerate())


@windows_only
def test_a_key_another_program_holds_is_reported_not_raised():
    first = HotkeyListener({"moment": "ctrl+alt+shift+f22"}, lambda name: None)
    first.start()
    second = HotkeyListener({"moment": "ctrl+alt+shift+f22"}, lambda name: None)
    second.start()
    try:
        assert "moment" not in second.registered
        assert "already using" in second.failures["moment"]
    finally:
        second.stop()
        first.stop()
