"""Phase 4B: the new frame in the window, its Jobs panel and time guesses.
The browser version (ai-editor app) is left exactly as it was."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

from ai_editor.app import estimate
from ai_editor.app.worker import DONE, PAUSED, RUNNING, Reporter, Task, Worker
from ai_editor.db import init_db


def wait_idle(worker, seconds=5):
    deadline = time.monotonic() + seconds
    while worker.busy() and time.monotonic() < deadline:
        time.sleep(0.02)


# --- the worker times each step ---------------------------------------------------------


def test_each_finished_step_is_timed_and_kept_when_the_job_is_done():
    worker, kept = Worker(), []
    worker.on_done = kept.append

    def job(report):
        report.progress("Making preview copy (proxy)", 0.0)
        time.sleep(0.05)
        report.progress("Making preview copy (proxy)", 1.0)
        report.progress("Transcribing speech", 0.5)
        time.sleep(0.15)
        report.progress("Transcribing speech", 1.0)
        report.progress("Transcribing speech", 1.0)          # said twice: timed once
        report.progress("Waiting: OBS is recording", 1.0)     # waiting is never timed

    worker.submit("Importing x", "import:x", job)
    wait_idle(worker)
    assert kept and [label for label, _ in kept[0].timings] == [
        "Making preview copy (proxy)", "Transcribing speech"]
    proxy, speech = (seconds for _, seconds in kept[0].timings)
    # Lower bounds exact; upper ones loose, for a PC busy with the other tests.
    assert 0.04 <= proxy < 0.6 and 0.14 <= speech < 1.5


def test_a_cards_own_resume_resumes_only_that_job():
    worker = Worker()
    worker._tasks = [Task(1, "a", "analyse:1", lambda r: None, status=PAUSED),
                     Task(2, "b", "analyse:2", lambda r: None, status=PAUSED)]
    worker._start = lambda: None
    assert worker.resume(2) == 1
    assert [t.status for t in worker._tasks] == [PAUSED, "waiting"]


# --- about how long a job has left ------------------------------------------------------


@pytest.fixture
def conn(settings):
    c = init_db(settings.db_path)
    c.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, duration_sec, "
              "imported_at) VALUES (1, 'h1', 'local_obs', 'a.mkv', 3 * 3600, 'now'), "
              "(2, 'h2', 'local_obs', 'b.mkv', 2 * 3600, 'now')")
    c.commit()
    yield c
    c.close()


def past_analysis(conn, recording_id: int, minutes: dict[str, float]) -> None:
    """An analysis that finished, as the resumable jobs write it down (before 4B)."""
    cur = conn.execute("INSERT INTO jobs (job_type, payload_json, recording_id, status, "
                       "created_at) VALUES ('analyze', '{}', ?, 'complete', 'now')",
                       (recording_id,))
    start = datetime(2026, 10, 30, 20, 0)
    for name, took in minutes.items():
        end = start + timedelta(minutes=took)
        conn.execute("INSERT INTO job_steps (job_id, step_name, status, started_at, finished_at) "
                     "VALUES (?, ?, 'complete', ?, ?)",
                     (cur.lastrowid, name, start.isoformat(), end.isoformat()))
        start = end
    conn.commit()


def test_the_guess_comes_from_this_pcs_own_past_jobs(conn):
    # A 3-hour stream: scene changes took 6 minutes, transcribing 1.
    past_analysis(conn, 1, {"transcribe": 1.0, "scenes": 6.0})
    task = Task(9, "Analysing #2", "analyse:2", lambda r: None, status=RUNNING,
                steps={"Transcribing speech": 1.0, "Finding scene changes (menus, loading)": 0.5})
    past = estimate.history(conn)
    # The 2-hour stream's scene changes: 4 minutes in all, half done.
    assert estimate.left(task, past, estimate.size_of(conn, task)) == pytest.approx(120, abs=1)
    assert estimate.words(120) == "about 2 min left"
    assert estimate.words(30) == "under a minute left"


def test_no_history_no_guess(conn):
    task = Task(9, "Analysing #2", "analyse:2", lambda r: None, status=RUNNING,
                steps={"Transcribing speech": 0.4})
    assert estimate.left(task, estimate.history(conn), 7200) is None
    past_analysis(conn, 1, {"transcribe": 1.0})
    task.steps["AI rating the clips"] = 0.1          # running, but never timed here
    assert estimate.left(task, estimate.history(conn), 7200) is None


def test_steps_only_some_recordings_have_are_not_expected(conn):
    """Separating voices only runs for Twitch VODs: not part of an OBS stream's guess."""
    past_analysis(conn, 1, {"separate_voices": 30.0, "transcribe": 1.0})
    for _ in range(2):
        past_analysis(conn, 1, {"transcribe": 1.0})
    task = Task(9, "Analysing #2", "analyse:2", lambda r: None, status=RUNNING,
                steps={"Transcribing speech": 0.0})
    left = estimate.left(task, estimate.history(conn), 7200)
    assert left == pytest.approx(40, abs=1)           # transcribing only: 1 min per 3 h


def test_steps_done_before_are_not_still_to_come(conn):
    """4C-1, the creator's test: analysing #33 again only ran AI rating (under a minute),
    but the guess counted every step of a whole analysis: "Analysing · 0%"."""
    full = Task(1, "Analysing #1", "analyse:1", lambda r: None, status=DONE,
                timings=[("Transcribing speech", 60.0), ("Finding scene changes (menus, loading)",
                                                          360.0), ("AI rating the clips", 30.0)])
    estimate.keep(conn, full, 3 * 3600)
    worker = Worker()
    task = Task(2, "Analysing #2", "analyse:2", lambda r: None, status=RUNNING)
    report = Reporter(worker, task)
    report.skipped("Transcribing speech")
    report.skipped("Finding scene changes (menus, loading)")
    report.skipped("Transcribing speech")                      # said twice: once
    report.progress("AI rating the clips", 0.5)
    assert task.steps == {"Transcribing speech": 1.0,
                          "Finding scene changes (menus, loading)": 1.0, "AI rating the clips": 0.5}
    # Only AI rating is left: half of its 20 s on a 2-hour stream.
    assert estimate.left(task, estimate.history(conn), 2 * 3600) == pytest.approx(10)
    # Kept as skipped, not as times: the next guess still expects them, at their real pace.
    report.progress("AI rating the clips", 1.0)
    task.status = DONE
    estimate.keep(conn, task, 2 * 3600)
    fresh = Task(3, "Analysing #3", "analyse:3", lambda r: None, status=RUNNING,
                 steps={"Transcribing speech": 0.0})
    # 60 s + 360 s still expected, plus AI rating (whose second run here took ~0 s).
    assert 420 <= estimate.left(fresh, estimate.history(conn), 3 * 3600) <= 451


def test_the_runner_says_which_steps_it_skipped(conn):
    from ai_editor.jobs import JobQueue

    queue = JobQueue(conn)
    job = queue.enqueue("analyze", {"recording_id": 1}, recording_id=1)
    ran, skipped = [], []
    steps = [("a", "key-a", lambda: ran.append("a") or ""),
             ("b", "key-b", lambda: ran.append("b") or "")]
    queue.run(job, steps, on_skip=skipped.append)
    assert ran == ["a", "b"] and skipped == []
    job = queue.enqueue("analyze", {"recording_id": 1}, recording_id=1)
    queue.run(job, steps, on_skip=skipped.append)              # both done before
    assert ran == ["a", "b"] and skipped == ["a", "b"]


def test_finished_jobs_are_kept_and_learned_from(conn):
    done = Task(3, "Rendering", "render:p", lambda r: None, status=DONE,
                timings=[("Rendering", 300.0)], result={"size_sec": 600.0})
    estimate.keep(conn, done, estimate.size_of(conn, done))
    running = Task(4, "Rendering", "render:q", lambda r: None, status=RUNNING,
                   steps={"Rendering": 0.5}, result={"size_sec": 1200.0, "parts": 1})
    # Half a video twice as long: 600 s of rendering's 1200 left... at 0.5 s a second.
    assert estimate.left(running, estimate.history(conn), 1200.0) == pytest.approx(300)


# --- the frame's answers ----------------------------------------------------------------


@pytest.fixture
def client(settings):
    import gradio as gr
    from fastapi.testclient import TestClient

    from ai_editor.app import frame_api

    worker = Worker()
    with gr.Blocks() as ui:
        gr.Markdown("today's screens")
    ui.queue()
    app = frame_api.build_app(settings, ui, worker, mount_kwargs={})
    with TestClient(app) as c:
        c.worker = worker
        yield c


def test_the_frame_and_todays_screens_are_served_together(client):
    assert "Starting" not in client.get("/").text and 'id="nav"' in client.get("/").text
    assert client.get("/frame/theme.css").status_code == 200
    assert client.get("/classic/").status_code == 200
    assert client.get("/config").json() == {"title": "AI-Editor", "aie_frame": True}


def test_the_sidebar_numbers_and_lines(client, settings):
    conn = init_db(settings.db_path)
    video = settings.folders.raw / "stream.mkv"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"x")
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                 "imported_at, analysis_status) VALUES (1, 'h', 'local_obs', ?, 'now', "
                 "'complete'), (2, 'g', 'local_obs', 'gone.mkv', 'now', 'complete')",
                 (str(video),))
    conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                 "signals_json, created_at) VALUES ('a', 1, 0, 30, 0.5, '{}', 'now'), "
                 "('b', 2, 0, 30, 0.5, '{}', 'now')")
    conn.execute("INSERT INTO issues (made_at, source, what) VALUES ('now', 'you', 'x')")
    conn.commit()
    conn.close()
    about = client.get("/api/frame").json()
    assert about["tallies"] == {"library": 1, "clips": 1, "review": 0, "issues": 1}
    # 4C-1: the designer's line, how many and the room left where they are.
    assert about["lines"]["library"].startswith("1 recording · ")
    assert " GB free on " in about["lines"]["library"] and about["lines"]["issues"] == "1 open"
    assert about["companion"]["running"] is False and about["note"] is None


def test_job_cards(client):
    worker = client.worker
    worker.submit("Wardogs highlights", "make:x", lambda r: r.say("10.4 min from 2 recordings"))
    wait_idle(worker)

    def short_of_space(report):
        raise RuntimeError("never")

    worker._tasks.append(Task(7, "Rendering Part 9", "render:p", short_of_space, status="failed",
                              error="Only 2.0 GB free on the drive with your output folder. "
                                    "Free some space first (Storage)."))
    cards = {c["title"]: c for c in client.get("/api/jobs").json()["jobs"]}
    done = cards["Wardogs highlights"]
    assert done["badge"] == "Finished" and done["meta"].startswith("took")
    assert done["lines"] == ["10.4 min from 2 recordings"]
    stopped = cards["Rendering Part 9"]
    assert stopped["state"] == "fail" and stopped["resume"]
    assert stopped["action"] == {"label": "Free up space", "screen": "storage"}


def test_no_web_page_can_press_the_buttons(client):
    for path in ("/api/jobs/pause", "/api/jobs/resume", "/api/jobs/clear",
                 "/api/companion/start", "/api/note/1/seen"):
        assert client.post(path).status_code == 403, path
    assert client.post("/api/jobs/pause", headers={"X-AI-Editor": "1"}).json() == {"held": 0}


# --- the browser version is as it was ---------------------------------------------------


def test_the_browser_way_starts_todays_window_as_before(settings, monkeypatch):
    import gradio as gr

    from ai_editor.app import window

    launched = {}
    monkeypatch.setattr(gr.Blocks, "launch", lambda self, **kw: launched.update(kw))
    for name in ("find_marks",):
        monkeypatch.setattr(window, name, lambda *a, **k: None)
    monkeypatch.setattr(window.overnight, "start_clock", lambda *a, **k: None)
    monkeypatch.setattr(window.backup_panel, "start_weekly", lambda *a, **k: None)
    ui, worker = window.start(settings, port=7865, open_browser=True)
    assert isinstance(ui, gr.Blocks) and launched["server_port"] == 7865
    assert launched["server_name"] == "127.0.0.1" and launched["inbrowser"] is True
    assert worker.on_done is not None        # its jobs' times are kept too, quietly


def test_todays_screens_only_hide_their_title_and_tabs_inside_the_frame():
    from ai_editor.app.window import CSS, HEAD

    assert 'asked.get("embed") !== "1") return' in HEAD    # nothing happens in the browser
    assert all(rule.startswith("html.aie-embed") for rule in
               [line for line in CSS.splitlines() if "aie-chrome" in line or "aie-tabs" in line])


# --- the window remembers where it was --------------------------------------------------


def test_the_window_opens_where_you_left_it(settings):
    from types import SimpleNamespace

    from ai_editor import desktop

    screen = SimpleNamespace(x=0, y=0, width=2560, height=1440)
    assert desktop.saved_geometry(settings, [screen]) == desktop.SIZE      # first time
    desktop.keep_geometry(settings, SimpleNamespace(x=300, y=120, width=1600, height=1000))
    assert desktop.saved_geometry(settings, [screen]) == {"x": 300, "y": 120, "width": 1600,
                                                          "height": 1000}
    # That monitor is gone: back to the usual size, on a screen that's there.
    assert desktop.saved_geometry(settings, [SimpleNamespace(x=0, y=0, width=200,
                                                             height=200)]) == desktop.SIZE


def test_maximised_opens_maximised_and_restore_has_a_smaller_size(settings):
    from types import SimpleNamespace

    from ai_editor import desktop

    class Event:
        def __init__(self):
            self.handlers = []

        def __iadd__(self, handler):
            self.handlers.append(handler)
            return self

        def set(self):
            for handler in self.handlers:
                handler()

    screen = SimpleNamespace(x=0, y=0, width=2560, height=1440)
    events = SimpleNamespace(maximized=Event(), minimized=Event(), restored=Event())
    normal = SimpleNamespace(x=300, y=120, width=1600, height=1000, events=events)
    state = desktop.track_state(normal)
    desktop.keep_geometry(settings, normal, state)                 # closed at normal size
    # Maximised, then closed: the window reports the screen's size, which isn't kept.
    events.maximized.set()
    big = SimpleNamespace(x=-8, y=-8, width=2576, height=1408)
    desktop.keep_geometry(settings, big, state)
    assert desktop.saved_geometry(settings, [screen]) == {"x": 300, "y": 120, "width": 1600,
                                                          "height": 1000, "maximized": True}
    # Restored, then minimised and closed from the taskbar: the normal size is kept.
    events.restored.set()
    events.minimized.set()
    desktop.keep_geometry(settings, SimpleNamespace(x=-32000, y=-32000, width=160, height=28), state)
    assert desktop.saved_geometry(settings, [screen]) == {"x": 300, "y": 120, "width": 1600,
                                                          "height": 1000}


def test_a_maximised_size_kept_before_the_fix_opens_maximised(settings):
    import json
    from types import SimpleNamespace

    from ai_editor import desktop

    path = desktop.geometry_file(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"x": -8, "y": -8, "width": 2576, "height": 1408}), encoding="utf-8")
    screen = SimpleNamespace(x=0, y=0, width=2560, height=1440)
    assert desktop.saved_geometry(settings, [screen]) == {**desktop.SIZE, "maximized": True}


# --- light or dark, kept (1 Nov) -----------------------------------------------------------


def test_the_theme_you_choose_is_kept_whatever_windows_says(client, settings):
    from ai_editor.config import load_settings

    assert 'data-theme="auto"' in client.get("/").text            # follows Windows at first
    assert client.post("/api/theme/dark").status_code == 403       # no web page can change it
    assert client.post("/api/theme/dark", headers={"X-AI-Editor": "1"}).json() == {"theme": "dark"}
    assert 'data-theme="dark"' in client.get("/").text             # opens dark, no flash
    assert client.get("/api/frame").json()["theme"] == "dark"
    assert load_settings(settings.source_path).appearance.theme == "dark"   # in your settings
    assert client.post("/api/theme/purple", headers={"X-AI-Editor": "1"}).status_code == 404


def test_the_starting_screen_uses_it_too(settings, monkeypatch):
    from ai_editor import desktop

    monkeypatch.setattr(desktop, "light_windows", lambda: True)
    settings.appearance.theme = "dark"
    assert '<html class="dark">' in desktop.starting_page("dark") and not desktop.looks_light(settings)
    settings.appearance.theme = "auto"
    assert desktop.looks_light(settings)                          # Windows is light


def test_clips_stack_and_fit_only_inside_the_frame():
    from ai_editor.app.window import CSS

    rules = [line for line in CSS.splitlines() if "aie-clips" in line]
    assert rules and all(line.lstrip().startswith(("html.aie-embed", "width:", "white-space:"))
                         for line in rules)


def test_player_keeps_a_video_shape_inside_the_frame():
    # Gradio adds a stronger copy of every rule, so the frame's must win with
    # !important; the browser version keeps its own player rule as it was.
    from ai_editor.app.window import CSS

    start = CSS.index("html.aie-embed .aie-player {")
    rule = CSS[start:CSS.index("}", start)]
    assert "aspect-ratio: 16 / 9 !important" in rule and "max-height: none !important" in rule
    assert ".aie-player { width: 100%; max-height: 440px;" in CSS
