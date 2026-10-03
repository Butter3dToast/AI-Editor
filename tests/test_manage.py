"""Storage, Settings and the Stream Companion panel (Phase 1H-3)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from ai_editor.app import companion_panel, manage_tabs, storage
from ai_editor.companion import status
from ai_editor.config import load_settings, local_settings_path, save_local_settings
from ai_editor.db import init_db
from ai_editor.errors import SettingsInvalid
from ai_editor.ingest import recording_cache_dir


def put(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


# --- Storage -------------------------------------------------------------------------------


@pytest.fixture
def library(settings):
    """One analysed recording with every kind of file, and one leftover folder."""
    conn = init_db(settings.db_path)
    raw = settings.folders.raw / "stream.mkv"
    put(raw, 5000)
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, title, "
                 "duration_sec, imported_at, analysis_status) VALUES (1, 'abc', 'local_obs', ?, "
                 "'stream', 60, '2026-10-01T20:00:00', 'complete')", (str(raw),))
    conn.commit()
    folder = recording_cache_dir(settings, "abc")
    put(folder / "audio" / "track_1.wav", 4000)
    put(folder / "proxy.mp4", 2000)
    put(folder / "analysis" / "transcript.json", 30)
    put(folder / "analysis" / "prepared" / "voice_16k.wav", 1000)
    put(folder / "analysis" / "separated" / "vocals.wav", 700)
    put(settings.folders.cache / "recordings" / "gone" / "analysis" / "x.json", 50)
    yield conn, folder, raw
    conn.close()


def test_storage_shows_what_each_recording_uses(settings, library):
    conn, folder, _ = library
    usages = storage.recording_usage(conn, settings)
    mine, leftover = usages
    assert (mine.raw, mine.sound, mine.preview, mine.working, mine.analysis) == \
        (5000, 4000, 2000, 1700, 30)
    assert leftover.recording_id is None and leftover.working == 50
    text = storage.overview(settings, usages)
    assert "free of" in text and "Never deleted by AI-Editor" in text


def test_freeing_working_files_keeps_everything_a_video_needs(settings, library):
    conn, folder, raw = library
    usages = storage.recording_usage(conn, settings)
    freed = storage.free_working_files(settings, usages, {1, "gone"})
    assert freed == 1750
    assert not (folder / "analysis" / "prepared").exists()
    assert not (folder / "analysis" / "separated").exists()
    assert not (settings.folders.cache / "recordings" / "gone").exists()
    for kept in (folder / "audio" / "track_1.wav", folder / "proxy.mp4",
                 folder / "analysis" / "transcript.json", raw):
        assert kept.is_file()


def test_clean_up_never_deletes_outside_the_cache(settings, library, tmp_path):
    conn, _, raw = library
    usage = storage.recording_usage(conn, settings)[0]
    usage.folder = raw.parent  # as if something went wrong: the raw folder
    usage.recording_id = None
    with pytest.raises(ValueError, match="Refusing"):
        storage.free_working_files(settings, [usage], {raw.parent.name})
    assert raw.is_file()


# --- Settings ------------------------------------------------------------------------------


def test_saving_settings_keeps_the_obs_password_and_only_what_changed(settings):
    local = local_settings_path(settings.source_path)
    local.write_text("obs:\n  websocket_password: secret\n", encoding="utf-8")
    new = save_local_settings(settings.source_path, {("highlights", "target_length_min"): 12.0,
                                                     ("captions", "highlights"): True})
    assert new.highlights.target_length_min == 12 and new.captions.highlights
    saved = yaml.safe_load(local.read_text(encoding="utf-8"))
    assert saved["obs"]["websocket_password"] == "secret"
    assert saved["highlights"] == {"target_length_min": 12.0}
    assert load_settings(settings.source_path).captions.highlights


def test_a_bad_setting_is_refused_and_nothing_is_written(settings):
    local = local_settings_path(settings.source_path)
    with pytest.raises(SettingsInvalid):
        save_local_settings(settings.source_path, {("highlights", "min_clip_score"): 7})
    with pytest.raises(SettingsInvalid):
        save_local_settings(settings.source_path, {("lets_play", "title_card"): "Ep {season}"})
    assert not local.exists()


def test_a_new_part_length_keeps_the_lets_play_settings_consistent(settings):
    for minutes in (15.0, 30.0, 45.0, 60.0):
        new = save_local_settings(settings.source_path, manage_tabs.part_lengths(settings,
                                                                                 minutes))
        assert new.lets_play.target_min == minutes
        settings = new


def test_saved_settings_reach_the_running_window(settings):
    new = save_local_settings(settings.source_path, {("highlights", "ordering"): "balanced"})
    live = settings
    manage_tabs.apply(live, new)
    assert live.highlights.ordering == "balanced"
    assert manage_tabs._plain(Path("F:/x")) == str(Path("F:/x"))
    assert manage_tabs._plain((25.0, 35.0)) == [25.0, 35.0]


# --- the Stream Companion panel -------------------------------------------------------------


def test_the_companion_counts_as_running_while_its_status_is_fresh(tmp_path):
    state = {"updated": time.time(), "obs": "connected", "obs_version": "31",
             "record": {"on": True, "since": "19:55", "paused": False},
             "stream": {"on": True, "since": "19:55", "paused": False}, "scene": "League",
             "game": "League of Legends", "session": "s", "markers": 3, "shorts": 1,
             "last_marker": "21:04:05", "message": None}
    status.write(tmp_path, state)
    current = status.read(tmp_path)
    assert current is not None
    line = companion_panel.status_html(current)
    assert "Running" in line and "Live since 19:55" in line and "Recording since 19:55" in line
    assert "League of Legends" in line and "3 marked, 1 Short-worthy (last at 21:04:05)" in line
    assert status.read(tmp_path, now=time.time() + status.FRESH_SEC + 1) is None
    assert "Not running" in companion_panel.status_html(None)


def test_stop_is_a_request_the_companion_sees(tmp_path):
    assert not status.stop_requested(tmp_path)
    status.request_stop(tmp_path)
    assert status.stop_requested(tmp_path)
    status.clear(tmp_path)
    assert not status.stop_requested(tmp_path)


def test_starting_twice_is_refused(settings):
    status.write(status.folder(settings), {"updated": time.time(), "obs": "waiting"})
    assert "already running" in companion_panel.start(settings)
