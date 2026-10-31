"""Phase 4A: AI-Editor in its own window, and the check before every job."""

from __future__ import annotations

import subprocess
import sys
import threading
import time

import pytest

from ai_editor import desktop, hardware, llm
from ai_editor.app.worker import DONE, FAILED, Worker

GB = 1_000_000_000


@pytest.fixture
def pc(monkeypatch):
    """A PC like the creator's: FFmpeg, an RTX with 12 GB, room on the drive,
    the AI (gemma4:12b, ~7.6 GB) downloaded."""
    state = {"ffmpeg": True, "card": hardware.Card("NVIDIA GeForce RTX 4070", 12.0),
             "free": 500.0, "model": int(7.6 * GB), "nvenc": {"h264_nvenc"}}
    monkeypatch.setattr(hardware, "_has_ffmpeg", lambda: state["ffmpeg"])
    monkeypatch.setattr(hardware, "card", lambda: state["card"])
    monkeypatch.setattr(hardware, "_free_gb", lambda folder: state["free"])
    monkeypatch.setattr(llm, "model_size", lambda s: state["model"])
    import ai_editor.ffmpeg as ffmpeg

    monkeypatch.setattr(ffmpeg, "nvenc_encoders", lambda: state["nvenc"])
    return state


def test_on_the_creators_pc_everything_just_starts(settings, pc):
    for key in ("import:x", "analyse:1", "render:p", "publish:p:None", "prompts:p:None",
                "overnight", "backup", "companion:marks"):
        assert hardware.check(settings, key) == (None, []), key


def test_a_job_that_cant_work_is_stopped_with_the_reason(settings, pc):
    pc["ffmpeg"] = False
    assert "FFmpeg isn't installed" in hardware.check(settings, "render:p")[0]
    assert hardware.check(settings, "rate:1")[0] is None          # the AI alone needs no FFmpeg
    pc["ffmpeg"], pc["card"] = True, None
    assert "needs an NVIDIA graphics card" in hardware.check(settings, "analyse:1")[0]
    assert "needs an NVIDIA" in hardware.check(settings, "import:x",
                                               "Importing and analysing x.mkv")[0]
    assert hardware.check(settings, "import:x", "Importing x.mkv")[0] is None   # no analysis
    pc["card"], pc["free"] = hardware.Card("RTX", 12.0), 2.0
    assert "Only 2.0 GB free" in hardware.check(settings, "render:p")[0]


def test_a_smaller_card_is_slower_never_stopped(settings, pc):
    """The creator's choice: the same AI everywhere, for its sharpness."""
    pc["card"] = hardware.Card("NVIDIA GeForce RTX 5070 Laptop GPU", 8.0)
    problem, slower = hardware.check(settings, "analyse:1")
    assert problem is None
    assert slower == ["Your graphics card has 8 GB and the local AI needs about 9 GB, so part "
                      "of it runs on the processor: slower, same answers."]
    pc["nvenc"] = set()
    assert "encoded on the processor" in hardware.check(settings, "render:p")[1][0]


def test_the_worker_checks_before_each_job(pc):
    worker, ran, failed = Worker(), [], []
    worker.precheck = lambda task: (("No FFmpeg.", []) if task.key == "render:p"
                                    else (None, ["Slower: small card."]))
    worker.on_failure = lambda task, error: failed.append(task.key)
    stopped = worker.submit("Rendering", "render:p", lambda r: ran.append("render"))
    slow = worker.submit("Analysing", "analyse:1", lambda r: ran.append("analyse"))
    deadline = time.monotonic() + 5
    while worker.busy() and time.monotonic() < deadline:
        time.sleep(0.02)
    jobs = {t.key: t for t in worker.snapshot()}
    assert ran == ["analyse"]                                  # the stopped one never ran
    assert jobs[stopped.key].status == FAILED and jobs[stopped.key].error == "No FFmpeg."
    assert jobs[slow.key].status == DONE and "Slower: small card." in jobs[slow.key].lines
    assert failed == []      # this PC can't do it: not a fault for the Issues tab


def test_a_broken_check_never_stops_a_job(settings, monkeypatch):
    monkeypatch.setattr(hardware, "check", lambda *a: 1 / 0)
    task = type("T", (), {"key": "render:p", "title": "x"})()
    assert hardware.precheck(settings)(task) == (None, [])


# --- the window ---------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' named mutex")
def test_only_one_window(monkeypatch):
    monkeypatch.setattr(desktop, "MUTEX", f"Local\\AI-Editor-test-{time.time()}")
    first = desktop.first_window()
    assert first is not None and desktop.first_window() is None


def test_a_second_start_brings_the_window_forward(settings):
    calls = []

    class Window:
        def restore(self):
            calls.append("restore")

        def show(self):
            calls.append("show")

        on_top = False

    threading.Thread(target=desktop.watch_for_second_start, args=(settings, Window(), 0.05),
                     daemon=True).start()
    time.sleep(0.2)
    desktop.ask_to_come_forward(settings)
    deadline = time.monotonic() + 3
    while not calls and time.monotonic() < deadline:
        time.sleep(0.05)
    assert calls[:2] == ["restore", "show"]


def test_closing_the_window_pauses_a_running_job():
    worker, started = Worker(), threading.Event()

    def long_job(report):
        started.set()
        while True:
            report.progress("Transcribing", 0.5)
            time.sleep(0.02)

    worker.submit("Analysing #1", "analyse:1", long_job)
    started.wait(5)
    desktop.pause_jobs(worker, wait=5)
    assert worker.snapshot()[0].status == "paused"


def test_a_crash_is_written_down_and_said(tmp_path, monkeypatch):
    said = []
    monkeypatch.setattr(desktop, "message", lambda text, icon=0: said.append(text))
    try:
        raise ValueError("boom")
    except ValueError:
        desktop._crash_hook(tmp_path / "ai-editor.log")(*sys.exc_info())
    assert "ValueError: boom" in said[0] and "ai-editor.log" in said[0]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console flags")
def test_helper_programs_get_no_console_window_unless_they_ask(monkeypatch):
    from ai_editor import childproc

    seen = []
    original = subprocess.Popen.__init__

    def record(self, *args, creationflags=0, **kwargs):
        seen.append(creationflags)
        raise OSError("not really started")

    monkeypatch.setattr(subprocess.Popen, "__init__", record)
    monkeypatch.delattr(subprocess.Popen, "_aie_no_console", raising=False)
    childproc.hide_consoles()
    for flags in (0, subprocess.CREATE_NEW_CONSOLE):
        with pytest.raises(OSError):
            subprocess.Popen(["ffmpeg"], creationflags=flags)
    monkeypatch.setattr(subprocess.Popen, "__init__", original)
    assert seen == [subprocess.CREATE_NO_WINDOW, subprocess.CREATE_NEW_CONSOLE]


def test_the_window_entry_point_never_replaces_the_command_line():
    """Windows file names ignore case: "AI-Editor" would overwrite ai-editor.exe."""
    import tomllib
    from pathlib import Path

    project = tomllib.loads((Path(desktop.__file__).parents[1] / "pyproject.toml")
                            .read_text(encoding="utf-8"))["project"]
    console, gui = project["scripts"], project["gui-scripts"]
    assert gui == {"ai-editor-window": "ai_editor.desktop:main"}
    assert not {n.lower() for n in console} & {n.lower() for n in gui}


# --- the starting screen (0.38.1) -------------------------------------------------------


class FakeWindow:
    def __init__(self):
        self.calls = []

    def evaluate_js(self, script):
        self.calls.append(("js", script))

    def load_url(self, url):
        self.calls.append(("load", url))


def test_the_starting_screen_moves_with_each_real_step_then_shows_the_page(settings,
                                                                            monkeypatch):
    from ai_editor.app import window as app_window

    monkeypatch.setattr(app_window, "already_running", lambda port: False)
    monkeypatch.setattr(app_window, "start",
                        lambda s, port, open_browser: ("the page", "the jobs"))
    win, started = FakeWindow(), {}
    desktop.boot(settings, win, started)
    steps = [c[1] for c in win.calls if c[0] == "js"]
    assert [s.split(", ")[1] for s in steps] == ['"Loading the editor"', '"Opening your library"',
                                                 '"Almost there"']
    assert steps[0].startswith("window.step && window.step(0.62,")
    assert win.calls[-1] == ("load", "http://127.0.0.1:7865/")
    assert started == {"ui": "the page", "worker": "the jobs", "url": "http://127.0.0.1:7865/"}


def test_if_the_browser_version_is_open_the_window_shows_that_one(settings, monkeypatch):
    from ai_editor.app import window as app_window

    monkeypatch.setattr(app_window, "already_running", lambda port: True)
    monkeypatch.setattr(app_window, "start", lambda *a, **k: 1 / 0)   # never a second server
    started = {}
    desktop.boot(settings, FakeWindow(), started)
    assert started == {"url": "http://127.0.0.1:7865/"}               # nothing of ours to close


def test_a_start_that_fails_says_so_on_the_starting_screen(settings, monkeypatch):
    from ai_editor.app import window as app_window

    monkeypatch.setattr(app_window, "already_running", lambda port: False)

    def broken(*a, **k):
        raise RuntimeError("the library is locked")

    monkeypatch.setattr(app_window, "start", broken)
    win = FakeWindow()
    desktop.boot(settings, win, {})
    last = win.calls[-1][1]
    assert "couldn't start (RuntimeError: the library is locked)" in last and last.endswith("true)")
    assert not any(c[0] == "load" for c in win.calls)


def test_the_starting_screen_has_the_bar_and_both_themes():
    page = desktop.starting_page()
    assert "Starting AI-Editor" in page and 'id="fill"' in page
    assert "prefers-color-scheme: light" in page and f"Version {desktop.__version__}" in page
    assert "http" not in page                                          # nothing from online
