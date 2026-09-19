"""Voice separation: when it runs, how audio is split into blocks, and that the
analysis uses the separated audio.

Demucs itself is replaced by a fake in the pipeline tests (it was run for real
on the creator's EP 1); block tiling and the decision logic are tested exactly.
"""

from __future__ import annotations

import shutil

import pytest

from ai_editor.analysis import pipeline
from ai_editor.analysis.separation import BACKING_FILE, VOCALS_FILE, block_ranges
from ai_editor.db import init_db
from ai_editor.ingest import ingest_recording
from ai_editor.jobs import COMPLETE

from .conftest import make_video, needs_ffmpeg
from .test_analysis import FakeModels


def test_blocks_tile_the_recording_exactly():
    rate = 100
    total = 1234 * rate
    ranges = block_ranges(total, rate)
    kept = [(ks, ke) for _, _, ks, ke in ranges]
    assert kept[0][0] == 0 and kept[-1][1] == total
    assert all(a[1] == b[0] for a, b in zip(kept, kept[1:])), "no gaps, no overlaps"


def test_blocks_read_extra_audio_either_side():
    rate = 100
    ranges = block_ranges(900 * rate, rate)
    read_start, read_end, keep_start, keep_end = ranges[1]
    assert read_start == keep_start - 5 * rate
    assert read_end == keep_end + 5 * rate
    first = ranges[0]
    assert first[0] == 0, "nothing before the start to read"


def test_short_recording_is_one_block():
    assert len(block_ranges(60 * 44_100)) == 1


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    yield connection
    connection.close()


def _row_and_tracks(conn, settings, tmp_path, *, tracks=1, source="local_obs"):
    video = make_video(tmp_path / f"{source}-{tracks}.mp4", seconds=4.0, audio_tracks=tracks)
    rec_id = ingest_recording(conn, settings, video, source_type=source).registration.recording_id
    row = conn.execute("SELECT * FROM recordings WHERE id = ?", (rec_id,)).fetchone()
    return rec_id, row, pipeline.choose_tracks(conn, rec_id)


@needs_ffmpeg
@pytest.mark.parametrize(
    ("mode", "source", "expected"),
    [
        ("vods", "twitch_vod", True),
        ("vods", "local_obs", False),   # the spec's default: VODs only
        ("mixed", "local_obs", True),
        ("off", "twitch_vod", False),
    ],
)
def test_when_separation_runs(conn, settings, tmp_path, mode, source, expected):
    settings.analysis.voice_separation = mode
    _, row, tracks = _row_and_tracks(conn, settings, tmp_path, source=source)
    assert pipeline.needs_separation(settings, row, tracks) is expected


@needs_ffmpeg
def test_never_needed_with_a_separate_mic_track(conn, settings, tmp_path):
    settings.analysis.voice_separation = "mixed"
    _, row, tracks = _row_and_tracks(conn, settings, tmp_path, tracks=4)
    assert pipeline.needs_separation(settings, row, tracks) is False


@needs_ffmpeg
def test_analysis_uses_the_separated_audio(conn, settings, tmp_path, monkeypatch):
    fakes = FakeModels(monkeypatch)
    calls: list = []

    def fake_separate(settings_, mixed_wav, out_dir, duration, on_progress=None):
        calls.append(mixed_wav)
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(mixed_wav, out_dir / VOCALS_FILE)
        shutil.copy(mixed_wav, out_dir / BACKING_FILE)
        return out_dir

    monkeypatch.setattr(pipeline, "separate_voices", fake_separate)
    rec_id, _, _ = _row_and_tracks(conn, settings, tmp_path, source="twitch_vod")

    result = pipeline.analyze_recording(conn, settings, str(rec_id))
    assert result.status == COMPLETE, result.error_message
    assert [s.name for s in result.steps][0] == "separate_voices"
    assert len(calls) == 1 and calls[0].name == "track_1.wav"

    voice, game = fakes.event_paths[0]
    assert game is not None and game.name == "game_32k.wav", "game sound heard separately"
    assert conn.execute("SELECT DISTINCT source_role FROM transcript_words").fetchone()[0] == "separated"

    again = pipeline.analyze_recording(conn, settings, str(rec_id))
    assert all(s.reused for s in again.steps) and len(calls) == 1


@needs_ffmpeg
def test_switching_separation_redoes_the_analysis(conn, settings, tmp_path, monkeypatch):
    """Results from separated and unseparated audio must never be mixed up."""
    fakes = FakeModels(monkeypatch)
    monkeypatch.setattr(pipeline, "separate_voices", lambda s, m, o, d, p=None: (
        o.mkdir(parents=True, exist_ok=True), shutil.copy(m, o / VOCALS_FILE),
        shutil.copy(m, o / BACKING_FILE), o)[-1])
    rec_id, _, _ = _row_and_tracks(conn, settings, tmp_path, source="twitch_vod")

    settings.analysis.voice_separation = "off"
    pipeline.analyze_recording(conn, settings, str(rec_id))
    settings.analysis.voice_separation = "vods"
    pipeline.analyze_recording(conn, settings, str(rec_id))
    assert fakes.transcribe_calls == 2
