"""The Stream Companion's session log, driven by a fake OBS."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from ai_editor.companion.app import Companion
from ai_editor.companion.obs import ObsClient
from ai_editor.companion.session import SessionLog
from ai_editor.db import init_db

from .fake_obs import FakeObs

T0 = datetime(2026, 9, 19, 19, 0, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def rig(settings):
    init_db(settings.db_path).close()
    settings.companion.confirmation_sound = False  # no beeping during tests
    obs = FakeObs()
    clock = Clock()
    companion = Companion(
        settings,
        client_factory=lambda s, events: ObsClient("127.0.0.1", 4455, "secret", timeout=2.0,
                                                   transport_factory=obs.factory, events=events),
        session_log=SessionLog(settings.db_path, now=clock),
    )
    yield obs, clock, companion
    companion.close()


def pump(companion: Companion, events: int = 1) -> None:
    """Handle the next ``events`` things OBS says."""
    for _ in range(events):
        event_type, data = companion.inbox.get(timeout=2)
        companion.handle(event_type, data)


def rows(settings):
    conn = init_db(settings.db_path)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM companion_events ORDER BY id")]
    finally:
        conn.close()


def connect(companion: Companion) -> None:
    companion.step(wait=0.1)
    assert companion.status.obs == "connected"


def test_waits_quietly_while_obs_is_closed(rig, settings):
    obs, _, companion = rig
    obs.running = False
    companion.step(wait=0.01)
    assert companion.status.obs == "waiting"
    assert rows(settings) == []


def test_a_recording_is_logged_start_to_finish(rig, settings):
    obs, clock, companion = rig
    connect(companion)
    obs.set_output("record", True, seconds=0.1)
    obs.output_event("record", "STARTED", path="F:/AI-Editor/raw/2026-09-19 20-00-00.mkv")
    pump(companion)
    assert companion.log.active

    clock.advance(600)
    obs.set_output("record", False)
    obs.output_event("record", "STOPPED", path="F:/AI-Editor/raw/2026-09-19 20-00-00.mkv")
    pump(companion)

    started, stopped = rows(settings)
    assert started["event_type"] == "obs_record_started"
    assert started["recording_time_sec"] == 0.0
    assert started["stream_time_sec"] is None  # not streaming
    # Time 0 is when the recording began, not when the news arrived.
    assert datetime.fromisoformat(started["wall_clock"]) == T0 - timedelta(seconds=0.1)
    assert json.loads(started["payload_json"])["path"].endswith(".mkv")
    assert stopped["event_type"] == "obs_record_stopped"
    assert stopped["recording_time_sec"] == pytest.approx(600.1)
    assert started["session_id"] == stopped["session_id"]
    assert not companion.log.active


def test_recording_started_during_a_stream_knows_its_place_in_the_vod(rig, settings):
    """The number that replaces attach-chat --starts-at."""
    obs, clock, companion = rig
    connect(companion)
    obs.set_output("stream", True, seconds=0.0)
    obs.output_event("stream", "STARTED")
    pump(companion)

    clock.advance(3.5)
    obs.set_output("stream", True, seconds=3.5)
    obs.set_output("record", True, seconds=0.0)
    obs.output_event("record", "STARTED", path="F:/AI-Editor/raw/r.mkv")
    pump(companion)

    stream_row, record_row = rows(settings)
    assert stream_row["event_type"] == "obs_stream_started"
    assert record_row["stream_time_sec"] == pytest.approx(3.5)
    assert record_row["session_id"] == stream_row["session_id"]


def test_one_session_until_both_stop(rig, settings):
    obs, clock, companion = rig
    connect(companion)
    for output in ("stream", "record"):
        obs.set_output(output, True)
        obs.output_event(output, "STARTED")
        pump(companion)
    obs.set_output("record", False)
    obs.output_event("record", "STOPPED")
    pump(companion)
    assert companion.log.active  # still streaming
    obs.set_output("stream", False)
    obs.output_event("stream", "STOPPED")
    pump(companion)
    assert len({r["session_id"] for r in rows(settings)}) == 1

    clock.advance(3600)
    obs.set_output("record", True)
    obs.output_event("record", "STARTED")
    pump(companion)
    assert len({r["session_id"] for r in rows(settings)}) == 2


def test_pause_and_resume(rig, settings):
    obs, clock, companion = rig
    connect(companion)
    obs.set_output("record", True)
    obs.output_event("record", "STARTED")
    pump(companion)
    obs.set_output("record", True, seconds=120, paused=True)
    obs.output_event("record", "PAUSED")
    pump(companion)
    obs.output_event("record", "RESUMED")
    pump(companion)
    kinds = [r["event_type"] for r in rows(settings)]
    assert kinds == ["obs_record_started", "obs_record_paused", "obs_record_resumed"]
    assert rows(settings)[1]["recording_time_sec"] == 120


def test_started_after_obs_began_recording(rig, settings):
    """Companion opened late: it still logs when the recording really began."""
    obs, _, companion = rig
    obs.set_output("record", True, seconds=300)
    connect(companion)
    (row,) = rows(settings)
    assert row["event_type"] == "obs_record_started"
    assert datetime.fromisoformat(row["wall_clock"]) == T0 - timedelta(seconds=300)
    assert json.loads(row["payload_json"])["noticed_late"] is True


def test_obs_closing_and_coming_back(rig, settings):
    obs, clock, companion = rig
    connect(companion)
    obs.set_output("record", True)
    obs.output_event("record", "STARTED")
    pump(companion)

    obs.drop()
    pump(companion)
    assert companion.status.obs == "waiting"

    # OBS came back with the same recording still going.
    clock.advance(30)
    obs.set_output("record", True, seconds=30)
    companion._next_attempt = 0
    connect(companion)
    kinds = [r["event_type"] for r in rows(settings)]
    assert kinds == ["obs_record_started", "obs_disconnected", "obs_reconnected"]


def test_a_new_recording_while_disconnected_is_noticed(rig, settings):
    obs, clock, companion = rig
    connect(companion)
    obs.set_output("record", True, seconds=0)
    obs.output_event("record", "STARTED")
    pump(companion)
    clock.advance(600)
    obs.set_output("record", True, seconds=600)
    companion._duration("record")  # the Companion last saw it 10 minutes in

    obs.drop()
    pump(companion)
    clock.advance(60)
    obs.set_output("record", True, seconds=20)  # a fresh recording, 20 s old
    companion._next_attempt = 0
    connect(companion)
    kinds = [r["event_type"] for r in rows(settings)]
    assert kinds[-2:] == ["obs_record_stopped", "obs_record_started"]


def test_a_marker_records_its_place_in_the_recording(rig, settings):
    obs, clock, companion = rig
    connect(companion)
    obs.set_output("record", True)
    obs.output_event("record", "STARTED")
    pump(companion)

    clock.advance(754)
    obs.set_output("record", True, seconds=754)
    companion.inbox.put(("_Hotkey", {"name": "moment"}))
    pump(companion)

    marker = rows(settings)[-1]
    assert marker["event_type"] == "marker"
    assert marker["recording_time_sec"] == pytest.approx(754)
    assert marker["payload_json"] is None
    assert companion.markers["moment"] == 1


def test_a_short_worthy_marker_is_its_own_kind(rig, settings):
    obs, _, companion = rig
    connect(companion)
    obs.set_output("record", True)
    obs.output_event("record", "STARTED")
    pump(companion)
    companion.mark("short")
    assert rows(settings)[-1]["event_type"] == "marker_short"
    assert companion.markers == {"moment": 0, "short": 1}


def test_a_marker_while_nothing_is_recording_still_counts_but_says_so(rig, settings):
    _, _, companion = rig
    connect(companion)
    assert companion.mark("moment") is False
    marker = rows(settings)[-1]
    assert marker["event_type"] == "marker"
    assert json.loads(marker["payload_json"])["while_idle"] is True


def test_markers_work_even_with_obs_closed(rig, settings):
    obs, _, companion = rig
    obs.running = False
    companion.step(wait=0.01)
    assert companion.mark("moment") is False
    assert rows(settings)[-1]["event_type"] == "marker"


def test_restarting_mid_recording_does_not_log_it_twice(rig, settings):
    """The bug the creator's first test found."""
    obs, clock, companion = rig
    connect(companion)
    obs.set_output("record", True)
    obs.output_event("record", "STARTED", path="F:/AI-Editor/raw/r.mkv")
    pump(companion)
    companion.close()

    clock.advance(45)
    obs.set_output("record", True, seconds=45)
    again = Companion(
        settings,
        client_factory=lambda s, events: ObsClient("127.0.0.1", 4455, "secret", timeout=2.0,
                                                   transport_factory=obs.factory, events=events),
        session_log=SessionLog(settings.db_path, now=clock),
    )
    try:
        connect(again)
        assert [r["event_type"] for r in rows(settings)] == ["obs_record_started"]
        assert again.log.session_id == companion.log.session_id
        # And it still knows the recording is running, so markers land correctly.
        again.mark("moment")
        assert rows(settings)[-1]["recording_time_sec"] == pytest.approx(45)
    finally:
        again.close()


def test_the_click_is_silent_when_obs_captures_desktop_audio(rig, settings):
    obs, _, companion = rig
    settings.companion.confirmation_sound = True
    obs.inputs.append({"inputName": "Desktop Audio", "inputKind": "wasapi_output_capture"})
    connect(companion)
    assert "Desktop Audio" in companion.status.sound_off_because


def test_the_click_plays_when_only_the_game_is_captured(rig, settings):
    obs, _, companion = rig
    settings.companion.confirmation_sound = True
    connect(companion)
    assert companion.status.sound_off_because is None


def test_a_muted_desktop_audio_source_is_not_a_problem(rig, settings):
    obs, _, companion = rig
    settings.companion.confirmation_sound = True
    obs.inputs.append({"inputName": "Desktop Audio", "inputKind": "wasapi_output_capture"})
    obs.muted.add("Desktop Audio")
    connect(companion)
    assert companion.status.sound_off_because is None


def test_unmuting_desktop_audio_mid_session_silences_the_click(rig, settings, monkeypatch):
    obs, _, companion = rig
    settings.companion.confirmation_sound = True
    connect(companion)
    assert companion.status.sound_off_because is None

    played: list = []
    monkeypatch.setattr("ai_editor.companion.sound.play", played.append)
    obs.inputs.append({"inputName": "Desktop Audio", "inputKind": "wasapi_output_capture"})
    companion._sound_checked_at -= 60  # as if the last check was a minute ago
    companion.mark("moment")
    assert "Desktop Audio" in companion.status.sound_off_because
    assert played == []


def test_a_refused_password_is_shown_and_retried_later(settings):
    init_db(settings.db_path).close()
    obs = FakeObs()
    companion = Companion(settings, client_factory=lambda s, events: ObsClient(
        "127.0.0.1", 4455, "wrong", timeout=2.0, transport_factory=obs.factory, events=events))
    started = time.monotonic()
    companion.step(wait=0.05)
    assert companion.status.obs == "password"
    assert "E051" in companion.status.message
    assert time.monotonic() - started < 1.0
