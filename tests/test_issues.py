"""Issues (0.32.0): problems written down with their details, private values hidden."""

from __future__ import annotations

import json

import pytest

from ai_editor import issues
from ai_editor.db import init_db
from ai_editor.recipes.plan import EditPlan, Segment, save_plan

SECRET = "hunter22-obs"


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                       "duration_sec, imported_at, game, analysis_status) VALUES (28, 'h', "
                       "'local_obs', 'F:/raw/2026-10-25 16-26-14.mkv', 6051.7, 'now', "
                       "'The Blood of Dawnwalker', 'complete')")
    for index, role in ((2, "mic"), (3, "game")):
        connection.execute("INSERT INTO audio_tracks (recording_id, stream_index, role, codec, "
                           "channels, sample_rate) VALUES (28, ?, ?, 'aac', 2, 48000)",
                           (index, role))
    save_plan(connection, EditPlan("letsplay_ep5", "letsplay", "EP 5", "The Blood of Dawnwalker",
                                   1800, [Segment(28, 0, 249.3), Segment(28, 251.7, 1959.0)]))
    connection.commit()
    settings.obs.websocket_password = SECRET
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    (settings.log_dir / "ai-editor.log").write_text(
        "2026-10-25 19:51:43 DEBUG FFmpeg (rendering part of a video) letsplay_ep5\n"
        f"2026-10-25 19:51:44 DEBUG connecting to OBS with {SECRET}\n"
        "2026-10-25 20:01:03 WARNING FFmpeg said, while finishing a video\n", encoding="utf-8")
    yield connection
    connection.close()


def test_an_issue_is_written_down_with_its_details(conn, settings):
    issue = issues.record(conn, settings, "EP 5 Part 1 loses the game's  sound",
                          plan_id="letsplay_ep5", at="16:39")
    assert issue.number == "#1" and issue.what == "EP 5 Part 1 loses the game's sound"
    d = issue.details
    assert d["plan"]["title"] == "EP 5" and d["plan"]["pieces"] == 2
    assert d["recording"]["file"] == "2026-10-25 16-26-14.mkv"   # its plan's one recording
    assert d["recording"]["sound tracks"] == ["2: mic", "3: game"]
    assert any("rendering part of a video" in line for line in d["log"])
    written = (issues.folder(settings) / "issue 0001.txt").read_text(encoding="utf-8")
    assert written.startswith("Issue #1: EP 5 Part 1 loses the game's sound")
    assert "Where: 16:39" in written and "Video: EP 5" in written


def test_private_values_never_go_in(conn, settings):
    settings.llm.model = "gemma4:12b"
    issue = issues.record(conn, settings, "Something", error=f"OBS refused {SECRET}")
    written = (issues.folder(settings) / "issue 0001.txt").read_text(encoding="utf-8")
    assert SECRET not in written and SECRET not in json.dumps(issue.details)
    assert issue.details["settings"]["obs"]["websocket_password"] == "[hidden]"
    assert "connecting to OBS with [hidden]" in written and "OBS refused [hidden]" in written
    assert issue.details["settings"]["llm"]["model"] == "gemma4:12b"   # not private


def test_an_issue_needs_words(conn, settings):
    with pytest.raises(ValueError, match="Say what's wrong"):
        issues.record(conn, settings, "   ")


def test_fixed_issues_say_in_which_version(conn, settings):
    issue = issues.record(conn, settings, "No game sound")
    issues.update(conn, settings, issue.id, status=issues.FIXED, fixed_in="0.31.1",
                  note="Picture and sound made apart")
    written = (issues.folder(settings) / "issue 0001.txt").read_text(encoding="utf-8")
    assert "Status: fixed (in 0.31.1)" in written and "Note: Picture and sound made apart" in written
    assert issues.listed(conn, open_only=True) == []
    assert [i.id for i in issues.listed(conn)] == [1]


def test_a_failed_job_is_written_down_by_ai_editor(conn, settings):
    rendering = issues.from_job(conn, settings, "Rendering EP 5", "The sound stopped",
                                "render:letsplay_ep5")
    assert rendering.source == issues.AI_EDITOR and rendering.plan_id == "letsplay_ep5"
    assert rendering.details["error"] == "The sound stopped"
    analysing = issues.from_job(conn, settings, "Analysing #28", "No space", "analyse:28")
    assert analysing.recording_id == 28 and analysing.plan_id is None


def test_the_worker_tells_about_every_failed_job(settings):
    import time

    from ai_editor.app.worker import TaskFailed, Worker

    told = []
    worker = Worker()
    worker.on_failure = lambda task, error: told.append((task.title, error))

    def fails(report):
        raise TaskFailed("That plan isn't there any more.")

    def breaks_the_hook(report):
        raise TaskFailed("again")

    worker.submit("Rendering EP 5", "render:x", fails)
    for _ in range(100):
        if told:
            break
        time.sleep(0.05)
    assert told == [("Rendering EP 5", "That plan isn't there any more.")]
    worker.on_failure = lambda task, error: 1 / 0   # writing it down fails: the queue goes on
    worker.submit("Again", "render:y", breaks_the_hook)
    worker.submit("Fine", "ok", lambda report: None)
    for _ in range(100):
        if worker.snapshot()[-1].status == "done":
            break
        time.sleep(0.05)
    assert worker.snapshot()[-1].status == "done"


def test_copy_diagnostic_info_with_and_without_an_issue(conn, settings):
    issue = issues.record(conn, settings, "No game sound", plan_id="letsplay_ep5")
    assert issues.diagnostic_text(conn, settings, issue.id).startswith("Issue #1: No game sound")
    now = issues.diagnostic_text(conn, settings)
    assert now.startswith("Diagnostic info (no issue picked)") and SECRET not in now
    assert "Settings (private values hidden):" in now
