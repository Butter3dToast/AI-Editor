"""The app window's workings: the jobs list, the library view, importing."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_editor.app import library
from ai_editor.app.window import activity_html
from ai_editor.app.worker import DONE, FAILED, PAUSED, RUNNING, WAITING, TaskFailed, Worker
from ai_editor.childproc import keep_with_us
from ai_editor.db import init_db
from ai_editor.errors import RecordingNotFound


def wait_for(condition, timeout: float = 5.0) -> None:
    end = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.01)


def status(worker: Worker, task_id: int) -> str:
    return next(t.status for t in worker.snapshot() if t.id == task_id)


# --- the jobs list --------------------------------------------------------------


def test_jobs_run_one_at_a_time_in_order_and_report_progress():
    worker, order, gate = Worker(), [], threading.Event()

    def first(report):
        report.progress("Step one", 0.5)
        gate.wait(5)
        order.append(1)
        report.say("First done.")

    a = worker.submit("First", "a", first)
    b = worker.submit("Second", "b", lambda report: order.append(2))
    wait_for(lambda: next(t for t in worker.snapshot() if t.id == a.id).steps)
    assert status(worker, a.id) == RUNNING and status(worker, b.id) == WAITING
    assert next(t for t in worker.snapshot() if t.id == a.id).steps == {"Step one": 0.5}
    gate.set()
    wait_for(lambda: status(worker, b.id) == DONE)
    assert order == [1, 2] and status(worker, a.id) == DONE
    assert next(t for t in worker.snapshot() if t.id == a.id).lines == ["First done."]
    assert not worker.busy()


def test_the_same_job_is_never_queued_twice_while_unfinished():
    worker, gate = Worker(), threading.Event()
    assert worker.submit("Analyse #1", "analyse:1", lambda r: gate.wait(5)) is not None
    assert worker.submit("Analyse #1", "analyse:1", lambda r: None) is None
    gate.set()
    wait_for(lambda: not worker.busy())
    assert worker.submit("Analyse #1", "analyse:1", lambda r: None) is not None  # finished: fine


def test_pause_stops_the_running_job_and_holds_the_rest_then_resume_runs_it_again():
    worker, runs, release = Worker(), [], threading.Event()

    def long(report):
        runs.append("start")
        while not release.is_set():
            report.progress("Working", 0.3)  # where a pause takes effect
            time.sleep(0.01)
        runs.append("end")

    a = worker.submit("Long", "a", long)
    b = worker.submit("Next", "b", lambda r: runs.append("next"))
    wait_for(lambda: status(worker, a.id) == RUNNING)
    assert worker.pause() == 2
    wait_for(lambda: status(worker, a.id) == PAUSED)
    assert status(worker, b.id) == PAUSED and runs == ["start"]
    assert "'Working' at 30%" in next(t for t in worker.snapshot() if t.id == a.id).lines[-1]

    release.set()
    assert worker.resume() == 2
    wait_for(lambda: status(worker, b.id) == DONE)
    assert runs == ["start", "start", "end", "next"]


def test_a_problem_stops_only_that_job_with_a_plain_message():
    worker = Worker()

    def broken(report):
        raise RecordingNotFound("There is no recording number 42")

    a = worker.submit("Broken", "a", broken)
    b = worker.submit("Fine", "b", lambda r: None)
    c = worker.submit("Gave up", "c", lambda r: (_ for _ in ()).throw(TaskFailed("Out of space.")))
    wait_for(lambda: not worker.busy())
    jobs = {t.id: t for t in worker.snapshot()}
    assert jobs[a.id].status == FAILED and "42" in jobs[a.id].error
    assert jobs[b.id].status == DONE
    assert jobs[c.id].error == "Out of space."
    worker.clear_finished()
    assert [t.id for t in worker.snapshot()] == [a.id, c.id]


def test_the_jobs_list_shows_progress_and_never_runs_what_a_title_contains():
    worker, gate = Worker(), threading.Event()

    def job(report):
        report.progress("Transcribing speech", 0.25)
        report.say("Library #3 <b>")
        gate.wait(5)

    worker.submit("<script>alert(1)</script>", "x", job)
    wait_for(lambda: worker.snapshot()[0].lines)
    page = activity_html(worker.snapshot(), now=time.monotonic())
    gate.set()
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "Transcribing speech" in page and "width:25.0%" in page and "25%" in page
    assert "Library #3 &lt;b&gt;" in page and "Running" in page
    assert "Nothing running" in activity_html([])


# --- the library ------------------------------------------------------------------


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    yield connection
    connection.close()


def add_recording(conn, rid: int, source: Path, **values) -> None:
    row = dict(content_hash=f"h{rid}", source_type="local_obs", source_file=str(source),
               duration_sec=7200.0, imported_at="2026-10-01T20:00:00+00:00", title=source.stem)
    row.update(values)
    conn.execute(f"INSERT INTO recordings (id, {', '.join(row)}) VALUES (?, "
                 f"{', '.join('?' * len(row))})", (rid, *row.values()))
    conn.commit()


def test_the_library_shows_each_recordings_state_in_plain_words(conn, settings, tmp_path):
    raw = settings.folders.raw
    raw.mkdir(parents=True, exist_ok=True)
    done, half, gone = raw / "done.mkv", raw / "half.mkv", raw / "gone.mkv"
    for path in (done, half):
        path.write_bytes(b"x")
    proxy = tmp_path / "proxy.mp4"
    proxy.write_bytes(b"x")
    add_recording(conn, 1, done, proxy_path=str(proxy), analysis_status="complete",
                  game="Wardogs", recorded_at="2026-09-30T19:00:00+00:00")
    add_recording(conn, 2, half, recorded_at="2026-10-01T19:00:00+00:00")
    add_recording(conn, 3, gone, recorded_at="2026-09-01T19:00:00+00:00")
    for track in range(4):
        conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role, extracted_path) "
                     "VALUES (1, ?, 'mic', 'x.wav')", (track,))
    conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role) VALUES (2, 1, 'mixed')")
    conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, created_at) "
                 "VALUES ('c', 1, 0, 30, 'now')")
    conn.commit()

    rows = library.library_table(conn, settings)
    assert [r[0] for r in rows] == [2, 1, 3]  # newest recording first
    by_id = {r[0]: dict(zip(library.COLUMNS, r)) for r in rows}
    assert by_id[1]["Status"] == "Analysed" and by_id[1]["Clips"] == 1
    assert by_id[1]["Sound"] == "4 tracks" and by_id[1]["Length"] == "2h 00m 00s"
    assert by_id[2]["Status"] == "Import unfinished" and by_id[2]["Sound"] == "1 mixed track"
    assert by_id[3]["Status"] == "Video deleted (kept for learning)"
    assert library.recording_choices(conn)[1] == ("#1  done  (Wardogs)", 1)
    text = library.recording_details(conn, settings, 1)
    assert "**Clips found:** 1" in text and "track 0 mic" in text and "Wardogs" in text


def test_a_twitch_vod_without_chat_says_how_long_twitch_keeps_it(conn, settings):
    made = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    add_recording(conn, 1, Path("vod.mp4"), source_type="twitch_vod", twitch_vod_id="123",
                  recorded_at=made.isoformat())
    row = conn.execute("SELECT r.*, 0 AS chat_count FROM recordings r").fetchone()
    assert library.chat_of(row, settings, made + timedelta(days=4)) == \
        "Not attached; about 10 day(s) left on Twitch"
    assert "may have deleted" in library.chat_of(row, settings, made + timedelta(days=15))
    assert library.days_left(None, 14) is None


def test_new_recordings_are_the_raw_videos_not_yet_imported(conn, settings):
    raw = settings.folders.raw
    raw.mkdir(parents=True, exist_ok=True)
    old, new, imported = raw / "old.mkv", raw / "new.mkv", raw / "imported.mkv"
    for path in (old, new, imported, raw / "notes.txt", raw / "VOD.partial.mp4"):
        path.write_bytes(b"x" * 10)
    os.utime(old, (time.time() - 7200, time.time() - 7200))
    os.utime(new, (time.time() - 3600, time.time() - 3600))
    add_recording(conn, 1, Path(str(imported).upper()))  # matched whatever the letter case
    found = library.new_recordings(conn, settings)
    assert [f.path.name for f in found] == ["new.mkv", "old.mkv"]
    assert not found[0].still_recording and "new.mkv  (0 MB" in found[0].label()


def test_a_file_obs_may_still_be_writing_is_not_imported(tmp_path):
    video = tmp_path / "2026-10-03 19-55-00.mkv"
    video.write_bytes(b"x")
    path, problem = library.check_importable(f'"{video}"')
    assert path is None and "still recording" in problem
    os.utime(video, (time.time() - 600, time.time() - 600))
    assert library.check_importable(str(video)) == (video, None)
    assert "no file" in library.check_importable(str(tmp_path / "nope.mkv"))[1]
    notes = tmp_path / "notes.txt"
    notes.write_text("x")
    os.utime(notes, (time.time() - 600, time.time() - 600))
    assert "doesn't look like a video" in library.check_importable(str(notes))[1]
    assert "Pick a recording" in library.check_importable("  ")[1]


# --- closing AI-Editor ends what it started ------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows job objects")
def test_child_programs_end_when_ai_editor_ends(tmp_path):
    """A stand-in for AI-Editor starts a long child, ties it, and is killed.

    The child beats a heartbeat file; once AI-Editor is gone, the beat stops.
    """
    beat = tmp_path / "beat"
    child = "\n".join(["import time", "n = 0", "while True:", "    n += 1",
                       f"    open({str(beat)!r}, 'w').write(str(n))", "    time.sleep(0.05)"])
    parent = subprocess.Popen([sys.executable, "-c", f"""
import subprocess, sys, time
from ai_editor.childproc import keep_with_us
keep_with_us(subprocess.Popen([sys.executable, "-c", {child!r}]))
time.sleep(60)
"""], cwd=Path(__file__).resolve().parent.parent)

    def beats() -> int:
        try:
            return int(beat.read_text() or 0)
        except (OSError, ValueError):
            return 0

    wait_for(lambda: beats() > 2, timeout=30)
    parent.kill()  # like closing its window: no chance to tidy up
    parent.wait()
    time.sleep(1.0)
    last = beats()
    time.sleep(0.5)
    assert beats() == last, "the child kept running after AI-Editor ended"


def test_tying_a_finished_program_is_harmless():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    keep_with_us(process)


def test_gradio_hands_a_clicked_row_to_the_library():
    """Gradio only passes the clicked row if it can read the handler's type hint."""
    import gradio as gr
    from gradio.utils import get_type_hints

    from ai_editor.app.window import row_id

    assert get_type_hints(row_id)["evt"] is gr.SelectData


def test_pausing_says_which_step_starts_over():
    from ai_editor.app.worker import paused_note

    note = paused_note({"Making preview copy (proxy)": 1.0, "Extracting audio tracks": 0.06})
    assert "'Extracting audio tracks' at 6%" in note and "finished step is kept" in note
    assert paused_note({"Downloading": 1.0}) == "Paused. Resume carries on from here."


def test_the_tab_bar_holds_only_tabs(settings):
    """Anything else placed straight in it shifted the tabs after it: Gradio 6
    then showed Storage and Settings twice once they were clicked."""
    import gradio as gr

    from ai_editor.app.window import build

    ui = build(settings, Worker())
    tabs = next(b for b in ui.blocks.values() if isinstance(b, gr.Tabs))
    assert [c.label for c in tabs.children] == [
        "Library", "Import", "Clips", "Create video", "Review", "Storage", "Settings"]
    assert all(isinstance(c, gr.Tab) for c in tabs.children)
