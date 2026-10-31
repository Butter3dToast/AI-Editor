"""Overnight work (3B): imports, analyses and drafts while you sleep; gives way
to OBS and a busy graphics card; never renders, never deletes."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from ai_editor.app import overnight, tasks
from ai_editor.app.worker import PauseRequested, Worker
from ai_editor.db import init_db
from ai_editor.games import game_for_scene, suggest_game
from ai_editor.recipes.plan import EditPlan, Segment

NIGHT = datetime(2026, 11, 1, 2, 0)


class Report:
    """The job's reporter, as the Jobs list would get it."""

    def __init__(self):
        self.lines, self.steps, self.pause_after = [], [], None

    def progress(self, label, fraction):
        self.steps.append(label)
        if self.pause_after is not None and len(self.steps) > self.pause_after:
            raise PauseRequested()

    def say(self, text):
        self.lines.append(text)

    def keep(self, **result):
        pass


class FakeObs:
    """OBS's answers, one per question; then not recording."""

    def __init__(self, answers=()):
        self.answers, self.asked, self.problem = list(answers), 0, None

    def busy(self):
        self.asked += 1
        return self.answers.pop(0) if self.answers else None

    def close(self):
        pass


@pytest.fixture
def conn(settings):
    settings.folders.raw.mkdir(parents=True, exist_ok=True)
    connection = init_db(settings.db_path)
    yield connection
    connection.close()


def add_recording(conn, settings, rid, *, game="League of Legends", status="complete",
                  video=True, imported=True):
    source = settings.folders.raw / f"stream {rid}.mkv"
    if video:
        source.write_bytes(b"video")
    proxy = settings.folders.cache / f"proxy {rid}.mp4"
    proxy.parent.mkdir(parents=True, exist_ok=True)
    proxy.write_bytes(b"proxy")
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, game, "
                 "duration_sec, proxy_path, imported_at, analysis_status) VALUES "
                 "(?, ?, 'local_obs', ?, ?, 7200, ?, '2026-10-31T20:00:00', ?)",
                 (rid, f"h{rid}", str(source), game, str(proxy), status))
    conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role, extracted_path) "
                 "VALUES (?, 1, 'mic', ?)", (rid, "mic.wav" if imported else None))
    conn.commit()


def save(conn, recipe, rid, parts=0):
    from ai_editor.recipes.plan import new_plan_id, save_plan

    segments = [Segment(rid, n * 60, n * 60 + 30, part=n + 1 if parts else None)
                for n in range(max(parts, 1))]
    plan = EditPlan(new_plan_id(conn, recipe, "g"), recipe, "t", "g", 600, segments)
    save_plan(conn, plan)
    return plan.plan_id


@pytest.fixture
def fake_steps(monkeypatch, settings):
    """Import, analysis and drafting without FFmpeg or the GPU."""
    calls = []

    def ingest(conn, settings_, path, report, **kw):
        calls.append(("import", path.name))
        rid = 100 + len([c for c in calls if c[0] == "import"])
        conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                     "game, imported_at, proxy_path) VALUES (?, ?, 'local_obs', ?, ?, 'now', ?)",
                     (rid, f"n{rid}", str(path), "League of Legends", str(path)))
        conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, extracted_path) "
                     "VALUES (?, 1, 'x.wav')", (rid,))
        conn.commit()
        return rid

    def analyse(conn, settings_, rid, report):
        calls.append(("analyse", rid))
        for n in range(3):
            report.progress("Transcribing", n / 3)
        conn.execute("UPDATE recordings SET analysis_status = 'complete' WHERE id = ?", (rid,))
        conn.commit()

    def job(recipe, parts=0, count=1):
        def make(settings_, rid=None, *a, recording_ids=None, **kw):
            rid = rid if rid is not None else recording_ids[0]
            n = settings_.shorts.per_recording if recipe == "shorts" else count

            def run(report):
                calls.append((recipe, rid))
                report.progress("Choosing", 1.0)
                c = init_db(settings.db_path)
                for _ in range(n):
                    save(c, recipe, rid, parts)
                c.close()
            return run
        return make

    monkeypatch.setattr(tasks, "_ingest", ingest)
    monkeypatch.setattr(tasks, "_analyse", analyse)
    monkeypatch.setattr(tasks, "make_highlights", job("highlights"))
    monkeypatch.setattr(tasks, "make_shorts", job("shorts"))
    monkeypatch.setattr(tasks, "make_letsplay", job("letsplay", parts=4))
    return calls


def run_night(settings, *, obs=None, gpu=lambda: 30.0, now=None, report=None, night="2026-11-01"):
    report = report or Report()
    clock = iter(range(0, 10**9, 31))      # every reading 31 s on: OBS is asked each time
    job = overnight.night_job(settings, night, began=NIGHT, obs=obs or FakeObs(), gpu=gpu,
                              sleep=lambda s: None, clock=lambda: next(clock),
                              now=now or (lambda: NIGHT))
    job(report)
    return report


# --- when ---------------------------------------------------------------------------


def test_it_starts_at_the_time_set_once_a_night(conn, settings):
    settings.overnight.enabled = True
    assert overnight.due(conn, settings, datetime(2026, 11, 1, 1, 59)) is None
    assert overnight.due(conn, settings, datetime(2026, 11, 1, 2, 0)) == NIGHT
    assert overnight.due(conn, settings, datetime(2026, 11, 1, 2, 59)) == NIGHT
    assert overnight.due(conn, settings, datetime(2026, 11, 1, 3, 0)) is None   # opened too late
    overnight.begin(conn, "2026-11-01")
    assert overnight.due(conn, settings, datetime(2026, 11, 1, 2, 30)) is None   # already ran
    settings.overnight.enabled = False
    assert overnight.due(conn, settings, datetime(2026, 11, 2, 2, 0)) is None


def test_start_and_stop_times_work_across_midnight(settings):
    settings.overnight.start, settings.overnight.stop_by = "23:30", "07:00"
    assert overnight.start_due(settings, datetime(2026, 11, 2, 0, 10)) == datetime(2026, 11, 1, 23, 30)
    assert overnight.stop_at(settings, datetime(2026, 11, 1, 23, 30)) == datetime(2026, 11, 2, 7, 0)
    settings.overnight.stop_by = None
    assert overnight.stop_at(settings, NIGHT) is None


def test_the_clock_puts_it_in_jobs_once(conn, settings, monkeypatch):
    settings.overnight.enabled = True
    worker = Worker()
    monkeypatch.setattr(worker, "_start", lambda: None)   # don't run it
    assert overnight.check(settings, worker, NIGHT) is not None
    assert overnight.check(settings, worker, NIGHT) is None   # already in Jobs
    assert [t.key for t in worker.snapshot()] == ["overnight"]


# --- what it does -----------------------------------------------------------------------


def test_what_is_left_to_do(conn, settings):
    add_recording(conn, settings, 1)                          # analysed, never planned: draft
    add_recording(conn, settings, 2, status="paused")         # analysis cut short: finish
    add_recording(conn, settings, 3, imported=False)          # import cut short: finish
    add_recording(conn, settings, 4, video=False)             # you deleted it: left alone
    add_recording(conn, settings, 5)
    save(conn, "highlights", 5)                               # you made a plan: left alone
    new = settings.folders.raw / "2026-10-31 20-00-00.mkv"
    new.write_bytes(b"new")
    import os
    os.utime(new, (1, 1))                                     # finished recording long ago
    found = [(i.kind, i.recording_id) for i in overnight.todo(conn, settings)]
    assert found == [("import", None), ("finish", 2), ("finish", 3), ("draft", 1)]


def test_a_night_imports_analyses_and_drafts(conn, settings, fake_steps):
    settings.lets_play.games = ["The Blood of Dawnwalker"]
    add_recording(conn, settings, 1)
    add_recording(conn, settings, 2, game="The Blood of Dawnwalker")
    new = settings.folders.raw / "2026-10-31 20-00-00.mkv"
    new.write_bytes(b"new")
    import os
    os.utime(new, (1, 1))
    report = run_night(settings)
    assert fake_steps == [("import", new.name), ("analyse", 101), ("highlights", 1),
                          ("shorts", 1), ("letsplay", 2), ("highlights", 101), ("shorts", 101)]
    note = overnight.morning_note(conn, settings)[1]
    assert "imported 1 new recording; analysed 1 recording" in note
    assert "drafted 1 highlight plan and 3 Shorts for #1 stream 1" in note
    assert "drafted 4 Let's Play parts for #2" in note
    assert "nothing was rendered" in note and report.lines[-1] in note
    # Each recording is drafted once: the next night has nothing to do.
    fake_steps.clear()
    run_night(settings, night="2026-11-02")
    assert fake_steps == []
    assert "found nothing new to do" in overnight.morning_note(conn, settings)[1]


def test_the_shorts_number_is_its_own(conn, settings, fake_steps):
    settings.overnight.shorts = 2
    add_recording(conn, settings, 1)
    run_night(settings)
    assert len(json.loads(conn.execute("SELECT plan_ids_json FROM overnight_drafts")
                          .fetchone()[0])) == 3   # 1 highlight plan + 2 Shorts
    assert settings.shorts.per_recording == 5      # your own setting is untouched


# --- giving way -------------------------------------------------------------------------


def test_it_waits_while_obs_records(conn, settings, fake_steps):
    add_recording(conn, settings, 1)
    obs = FakeObs(["OBS is recording", "OBS is recording"])
    report = run_night(settings, obs=obs)
    assert "Waiting: OBS is recording. Looking again every minute." in report.lines
    assert fake_steps[0] == ("highlights", 1)      # only once OBS had stopped
    done = json.loads(conn.execute("SELECT done_json FROM overnight_nights").fetchone()[0])
    assert done["waited"] == {"OBS": 120}
    assert "Waited 2 min for OBS" in overnight.morning_note(conn, settings)[1]


def test_it_waits_while_the_graphics_card_is_busy(conn, settings, fake_steps):
    add_recording(conn, settings, 1)
    readings = iter([90.0] * 6 + [35.0] * 60)     # a game for a minute, then idle
    report = run_night(settings, gpu=lambda: next(readings))
    assert "Waiting: the graphics card is busy (90%). Looking again every minute." in report.lines
    assert fake_steps[0] == ("highlights", 1)


def test_it_gives_way_in_the_middle_of_a_step_and_starts_it_again(conn, settings, fake_steps):
    add_recording(conn, settings, 1, status="paused")
    # Free before the step; then OBS starts recording during it.
    obs = FakeObs([None, "OBS is recording", None])
    report = run_night(settings, obs=obs)
    assert any(line.startswith("Gave way: OBS is recording") for line in report.lines)
    assert fake_steps.count(("analyse", 1)) == 2   # cut short, then again from the start
    assert ("highlights", 1) in fake_steps


def test_it_stops_at_the_stop_by_time(conn, settings, fake_steps):
    settings.overnight.stop_by = "06:00"
    add_recording(conn, settings, 1)
    report = run_night(settings, now=lambda: datetime(2026, 11, 1, 6, 0))
    assert fake_steps == []
    assert "Stopped at 06:00, as set" in report.lines[-2]
    assert conn.execute("SELECT status FROM overnight_nights").fetchone()[0] == "stopped"


def test_pause_in_jobs_still_works(conn, settings, fake_steps):
    add_recording(conn, settings, 1, status="paused")
    report = Report()
    report.pause_after = 1
    with pytest.raises(PauseRequested):
        run_night(settings, report=report)
    assert conn.execute("SELECT status FROM overnight_nights").fetchone()[0] == "paused"


def test_a_problem_is_written_down_and_the_night_goes_on(conn, settings, fake_steps, monkeypatch):
    add_recording(conn, settings, 1, status="paused")
    add_recording(conn, settings, 2)

    def broken(conn_, settings_, rid, report):
        raise tasks.TaskFailed("The sound couldn't be read.")

    monkeypatch.setattr(tasks, "_analyse", broken)
    run_night(settings)
    assert fake_steps == [("highlights", 2), ("shorts", 2)]
    issue = conn.execute("SELECT * FROM issues").fetchone()
    assert issue["source"] == "ai-editor" and issue["recording_id"] == 1
    assert "couldn't import or analyse #1 stream 1" in issue["what"]
    assert "Issues tab" in overnight.morning_note(conn, settings)[1]


def test_the_morning_note_goes_once_you_press_ok(conn, settings, fake_steps):
    run_night(settings)
    night_id, _ = overnight.morning_note(conn, settings)
    overnight.mark_seen(conn, night_id)
    assert overnight.morning_note(conn, settings) is None


def test_a_night_cut_short_by_closing_ai_editor(conn, settings):
    overnight.begin(conn, "2026-11-01")
    overnight.recover(conn)
    assert "was closed before it finished" in overnight.morning_note(conn, settings)[1]


# --- the rules --------------------------------------------------------------------------

SOURCE = Path(overnight.__file__).read_text(encoding="utf-8")


def test_it_never_renders_or_deletes():
    code = re.sub(r'""".*?"""', "", SOURCE, flags=re.DOTALL)
    assert not re.search(r"\brender\b|quick_preview|publish", code)
    assert not re.search(r"\bDELETE\b|unlink|rmtree|os\.remove", code)


def test_it_only_reads_the_cards_load_never_program_names():
    """The anti-cheat rule (spec section 6): no list of running programs."""
    calls = re.findall(r"subprocess\.run\(\[([^\]]*)\]", SOURCE)
    assert calls == ['smi, "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"']
    assert "tasklist" not in SOURCE and "query-compute-apps" not in SOURCE


# --- Let's Play games you add -----------------------------------------------------------


def test_a_lets_play_game_you_add_is_recognised_by_name():
    added = ["Arc Raiders"]
    assert suggest_game("2026-11-02 Arc Raiders ep1", added) == "Arc Raiders"
    assert game_for_scene("ARC RAIDERS", {}, added) == "Arc Raiders"
    assert game_for_scene("Starting Soon", {}, added) is None
    assert suggest_game("2026-11-02 Arc Raiders ep1") is None     # not before it's added
    assert game_for_scene("Wardogs", {}, added) == "Wardogs"      # the known ones still work
