"""The anti-cheat rule, enforced (spec section 6, manual chapter 27).

AI-Editor must never read or write game memory, inject into or hook a game,
or automate input. Rather than trusting that to care, this test fails the
build if any part of AI-Editor so much as mentions the Windows functions or
Python libraries those things need.

The Stream Companion registers its hotkeys the way Discord and OBS do,
through Windows' own hotkey registration, and talks to nothing but OBS.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "ai_editor"

FORBIDDEN = {
    # Other programs' memory.
    "OpenProcess": "opens another program",
    "ReadProcessMemory": "reads another program's memory",
    "WriteProcessMemory": "writes another program's memory",
    "VirtualAllocEx": "puts code into another program",
    "CreateRemoteThread": "runs code inside another program",
    "NtReadVirtualMemory": "reads another program's memory",
    # Hooking.
    "SetWindowsHookEx": "hooks every key press or mouse move system-wide",
    "LoadLibrary": "loads code the way injectors do",
    # Automated input.
    "SendInput": "fakes key presses or mouse input",
    "keybd_event": "fakes key presses",
    "mouse_event": "fakes mouse input",
    "PostMessage": "sends input to another window",
    "GetAsyncKeyState": "polls the keyboard the way cheats and keyloggers do",
    # Looking at what is running.
    "EnumProcesses": "lists running programs",
    "CreateToolhelp32Snapshot": "lists running programs",
    "FindWindow": "looks for another program's window",
}

FORBIDDEN_IMPORTS = {
    "psutil": "lists and inspects running programs",
    "pymem": "reads game memory",
    "pynput": "hooks the keyboard and fakes input",
    "keyboard": "hooks the keyboard system-wide",
    "mouse": "hooks the mouse system-wide",
    "pyautogui": "fakes key presses and mouse input",
    "pydirectinput": "fakes game input",
    "win32api": "broad Windows access; use ctypes for the one call needed",
    "frida": "injects into programs",
}

SOURCES = sorted(PACKAGE.rglob("*.py"))


def test_there_is_code_to_check():
    assert len(SOURCES) > 10


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_no_game_interaction_anywhere(path):
    text = path.read_text(encoding="utf-8")
    problems = [f"{name} ({why})" for name, why in FORBIDDEN.items()
                if re.search(rf"\b{name}", text)]
    for module, why in FORBIDDEN_IMPORTS.items():
        if re.search(rf"^\s*(import|from)\s+{module}\b", text, re.MULTILINE):
            problems.append(f"import {module} ({why})")
    assert not problems, f"{path.name} uses: " + ", ".join(problems)


NETWORK = ("requests", "urllib", "http.client", "http", "socket", "aiohttp", "httpx")
LEAGUE = PACKAGE / "companion" / "league.py"


def test_the_companion_only_talks_to_obs_and_league():
    """Its network connections: the OBS WebSocket, and League's own local API (Phase 2E)."""
    companion = PACKAGE / "companion"
    for path in companion.rglob("*.py"):
        if path == LEAGUE:
            continue
        text = path.read_text(encoding="utf-8")
        for network in NETWORK:
            assert not re.search(rf"^\s*(import|from)\s+{network}\b", text, re.MULTILINE), \
                f"{path.name} imports {network}"


def test_league_events_only_ask_league_on_this_pc():
    """Riot's read-only Live Client Data API on 127.0.0.1:2999, and nowhere else:
    no other address, port or web site, and only ever a GET."""
    text = LEAGUE.read_text(encoding="utf-8")
    code = re.sub(r'""".*?"""', "", text, flags=re.DOTALL)        # not the explanations
    code = "\n".join(line.split("#")[0] for line in code.splitlines())
    assert set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", code)) == {"127.0.0.1"}
    assert re.search(r"^HOST = \"127\.0\.0\.1\"$", code, re.MULTILINE)
    assert re.search(r"^PORT = 2999$", code, re.MULTILINE)
    assert re.findall(r"HTTPSConnection\(([^,]+), ([^,]+),", code) == [("HOST", "PORT")]
    assert re.findall(r"\.request\(\"(\w+)\"", code) == ["GET"]
    assert not re.search(r"https?://|localhost|\.com\b|\.net\b", code)
    assert not re.search(r"CERT_NONE|_create_unverified_context|verify\s*=\s*False", code)
