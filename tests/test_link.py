"""Matching an imported recording to the session that produced it."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from ai_editor.companion.link import link_recording, started_at_of, stream_offset
from ai_editor.db import init_db

T0 = datetime(2026, 9, 20, 19, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    yield connection
    connection.close()


def add_recording(conn, source_file: str, duration_sec: float = 600.0, recorded_at=None) -> int:
    cursor = conn.execute(
        "INSERT INTO recordings (content_hash, source_type, source_file, duration_sec, "
        "recorded_at, imported_at) VALUES (?, 'local_obs', ?, ?, ?, ?)",
        (source_file, source_file, duration_sec,
         recorded_at.isoformat() if recorded_at else None, T0.isoformat()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def add_event(conn, session: str, event_type: str, *, at: datetime, record_sec=None,
              stream_sec=None, path=None) -> None:
    conn.execute(
        "INSERT INTO companion_events (session_id, event_type, wall_clock, stream_time_sec, "
        "recording_time_sec, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
        (session, event_type, at.isoformat(timespec="milliseconds"), stream_sec, record_sec,
         json.dumps({"path": path}) if path else None),
    )
    conn.commit()


def a_session(conn, session="S1", *, path="F:/raw/a.mkv", stream_sec=None, markers=(3, 10)):
    add_event(conn, session, "obs_record_started", at=T0, record_sec=0.0,
              stream_sec=stream_sec, path=path)
    for offset in markers:
        add_event(conn, session, "marker", at=T0 + timedelta(seconds=offset), record_sec=offset)


def test_matched_by_the_file_obs_was_writing(conn, settings):
    a_session(conn)
    recording_id = add_recording(conn, "F:/raw/a.mkv")
    match = link_recording(conn, recording_id)
    assert match is not None
    assert (match.matched_by, match.session_id, match.markers) == ("file", "S1", 2)


def test_markers_become_moments_in_the_recordings_own_timeline(conn, settings):
    a_session(conn, markers=(3, 10, 754))
    recording_id = add_recording(conn, "F:/raw/a.mkv", duration_sec=900)
    link_recording(conn, recording_id)
    rows = conn.execute(
        "SELECT t_sec, value FROM signals WHERE recording_id = ? AND name = 'marker' ORDER BY t_sec",
        (recording_id,),
    ).fetchall()
    assert [r["t_sec"] for r in rows] == [3, 10, 754]
    assert all(r["value"] == 1 for r in rows)


def test_running_import_again_does_not_double_the_markers(conn, settings):
    a_session(conn)
    recording_id = add_recording(conn, "F:/raw/a.mkv")
    link_recording(conn, recording_id)
    link_recording(conn, recording_id)
    count = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE recording_id = ? AND name = 'marker'", (recording_id,)
    ).fetchone()[0]
    assert count == 2


def test_a_remuxed_file_still_matches(conn, settings):
    """OBS records .mkv and can remux to .mp4 afterwards."""
    a_session(conn, path="F:/raw/2026-09-20 11-12-01.mkv")
    recording_id = add_recording(conn, "F:/raw/2026-09-20 11-12-01.mp4")
    assert link_recording(conn, recording_id).matched_by == "file"


def test_matched_by_time_when_the_file_is_unknown(conn, settings):
    a_session(conn, path=None)
    recording_id = add_recording(conn, "F:/raw/moved.mkv", recorded_at=T0 + timedelta(seconds=20))
    assert link_recording(conn, recording_id).matched_by == "time"


def test_a_recording_from_another_day_is_not_matched(conn, settings):
    a_session(conn, path=None)
    recording_id = add_recording(conn, "F:/raw/other.mkv", recorded_at=T0 + timedelta(hours=5))
    assert link_recording(conn, recording_id) is None


def test_markers_from_a_different_recording_in_the_same_session_stay_out(conn, settings):
    add_event(conn, "S1", "obs_record_started", at=T0, record_sec=0.0, path="F:/raw/first.mkv")
    add_event(conn, "S1", "marker", at=T0 + timedelta(seconds=30), record_sec=30)
    add_event(conn, "S1", "obs_record_stopped", at=T0 + timedelta(seconds=60), record_sec=60)
    add_event(conn, "S1", "obs_record_started", at=T0 + timedelta(seconds=120), record_sec=0.0,
              path="F:/raw/second.mkv")
    add_event(conn, "S1", "marker", at=T0 + timedelta(seconds=150), record_sec=30)

    first = add_recording(conn, "F:/raw/first.mkv", duration_sec=60)
    assert link_recording(conn, first).markers == 1


def test_the_stream_offset_is_what_chat_needs(conn, settings):
    a_session(conn, stream_sec=3.5)
    recording_id = add_recording(conn, "F:/raw/a.mkv")
    match = link_recording(conn, recording_id)
    assert match.stream_offset_sec == pytest.approx(3.5)
    assert stream_offset(conn, recording_id) == pytest.approx(3.5)


def test_no_session_log_at_all_is_not_a_problem(conn, settings):
    recording_id = add_recording(conn, "F:/raw/a.mkv")
    assert link_recording(conn, recording_id) is None
    assert stream_offset(conn, recording_id) is None


def test_a_recording_is_dated_from_the_file_when_nothing_else_says(tmp_path):
    path = tmp_path / "r.mkv"
    path.write_bytes(b"x")
    started = started_at_of(path, duration_sec=600)
    finished = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    assert started == finished - timedelta(seconds=600)
