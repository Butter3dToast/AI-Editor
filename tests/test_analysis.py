"""Phase 1B: the analysis job, end to end.

The two AI models are replaced with fakes so these tests run in seconds, need
no GPU and download nothing. The real models were exercised on an excerpt of
the creator's EP 1; the full recording is the Phase 1B acceptance test.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from ai_editor import models
from ai_editor.analysis import pipeline
from ai_editor.analysis.moments import build_report
from ai_editor.db import init_db
from ai_editor.errors import ModelDownloadFailed, NotImported, RecordingNotFound
from ai_editor.ingest import ingest_recording
from ai_editor.jobs import COMPLETE, PAUSED

from .conftest import make_video, needs_ffmpeg
from .test_transcript_filter import MUSIC_HALLUCINATION


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    yield connection
    connection.close()


def _shift(segment, by):
    return {**segment, "s": segment["s"] + by, "e": segment["e"] + by,
            "words": [{**w, "s": w["s"] + by, "e": w["e"] + by} for w in segment["words"]]}


class FakeModels:
    """Stands in for Whisper and PANNs, and counts how often each ran."""

    def __init__(self, monkeypatch):
        self.transcribe_calls = 0
        self.event_calls = 0
        self.event_paths: list = []
        self.detector_used: list[bool] = []
        monkeypatch.setattr(pipeline, "transcribe", self.transcribe)
        monkeypatch.setattr(pipeline, "detect_sound_events", self.events)

    def transcribe(self, settings, wav, duration, on_progress=None, *, use_voice_detector=True):
        self.transcribe_calls += 1
        self.detector_used.append(use_voice_detector)
        assert wav.exists(), "transcription must read the prepared 16 kHz file"
        if on_progress:
            on_progress(1.0)
        real = {
            "s": 0.5, "e": 1.5, "text": "Oh no",
            "avg_logprob": -0.1, "no_speech_prob": 0.0, "compression_ratio": 1.0,
            "words": [{"w": "Oh", "s": 0.5, "e": 0.9, "p": 0.99},
                      {"w": "no", "s": 0.9, "e": 1.5, "p": 0.98}],
        }
        # A hallucination moved into this clip's 4 seconds.
        fake = _shift(MUSIC_HALLUCINATION, -110.0)
        fake["words"] = [w for w in fake["words"] if w["e"] <= 4.0] or fake["words"][:2]
        return {"model": "fake", "language": "en", "language_probability": 1.0,
                "segments": [real, fake]}

    def events(self, settings, voice_32k, game_32k, seconds, on_progress=None):
        self.event_calls += 1
        self.event_paths.append((voice_32k, game_32k))
        laughter = [0.0] * seconds
        laughter[2] = 0.9
        return {"laughter": laughter, "shout": [0.0] * seconds, "scream": [0.0] * seconds,
                "gunfire": [0.0] * seconds, "explosion": [0.0] * seconds,
                "music": [0.1] * seconds}


def _imported(conn, settings, tmp_path, tracks=1, name="ep.mp4"):
    video = make_video(tmp_path / name, seconds=4.0, audio_tracks=tracks)
    result = ingest_recording(conn, settings, video)
    assert result.status == COMPLETE
    return result.registration.recording_id, video


# --- Finding recordings and tracks -----------------------------------------


@needs_ffmpeg
def test_recording_found_by_number_or_file(conn, settings, tmp_path):
    rec_id, video = _imported(conn, settings, tmp_path)
    assert pipeline.resolve_recording(conn, str(rec_id))["id"] == rec_id
    assert pipeline.resolve_recording(conn, str(video))["id"] == rec_id


def test_unknown_recording_number(conn):
    with pytest.raises(RecordingNotFound) as excinfo:
        pipeline.resolve_recording(conn, "42")
    assert "42" in excinfo.value.user_message()


@needs_ffmpeg
def test_file_that_was_never_imported(conn, tmp_path):
    video = make_video(tmp_path / "new.mp4", seconds=1.0)
    with pytest.raises(RecordingNotFound) as excinfo:
        pipeline.resolve_recording(conn, str(video))
    assert "hasn't been imported" in excinfo.value.user_message()


@needs_ffmpeg
def test_single_track_uses_it_for_everything(conn, settings, tmp_path):
    rec_id, _ = _imported(conn, settings, tmp_path, tracks=1)
    tracks = pipeline.choose_tracks(conn, rec_id)
    assert tracks.voice_role == tracks.game_role == "mixed"
    assert not tracks.separate_game_track


@needs_ffmpeg
def test_multitrack_listens_to_mic_and_game_separately(conn, settings, tmp_path):
    """Manual chapter 7 setup: voice from track 2, game sound from track 3."""
    rec_id, _ = _imported(conn, settings, tmp_path, tracks=4)
    tracks = pipeline.choose_tracks(conn, rec_id)
    assert (tracks.voice_role, tracks.game_role) == ("mic", "game")
    assert tracks.separate_game_track


@needs_ffmpeg
def test_missing_imported_audio_is_explained(conn, settings, tmp_path):
    rec_id, _ = _imported(conn, settings, tmp_path)
    wav = conn.execute("SELECT extracted_path FROM audio_tracks").fetchone()[0]
    from pathlib import Path
    Path(wav).unlink()
    with pytest.raises(NotImported):
        pipeline.choose_tracks(conn, rec_id)


# --- The analysis job ------------------------------------------------------


@needs_ffmpeg
def test_full_analysis(conn, settings, tmp_path, monkeypatch):
    fakes = FakeModels(monkeypatch)
    rec_id, _ = _imported(conn, settings, tmp_path)

    result = pipeline.analyze_recording(conn, settings, str(rec_id))
    assert result.status == COMPLETE, result.error_message

    # Transcript: the real phrase stored, the hallucination set aside.
    words = [r["word"] for r in conn.execute(
        "SELECT word FROM transcript_words WHERE recording_id = ? ORDER BY idx", (rec_id,))]
    assert words == ["Oh", "no"]
    assert conn.execute("SELECT DISTINCT source_role FROM transcript_words").fetchone()[0] == "mixed"

    # Signals: one value per second for each.
    names = {r[0] for r in conn.execute("SELECT DISTINCT name FROM signals")}
    assert {"voice_db", "energy_z", "silence", "speech", "laughter", "gunfire"} <= names
    assert "game_db" not in names, "no separate game track to measure"
    per_second = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE name = 'speech' AND recording_id = ?", (rec_id,)
    ).fetchone()[0]
    assert per_second == 4

    # Files: subtitles beside the proxy so VLC loads them automatically.
    assert result.proxy_srt_path and result.proxy_srt_path.exists()
    assert result.proxy_srt_path.stem == "proxy"
    assert "Oh no" in result.proxy_srt_path.read_text(encoding="utf-8-sig")

    # Status and report.
    assert conn.execute("SELECT analysis_status FROM recordings").fetchone()[0] == "complete"
    report = build_report(conn, rec_id)
    assert report.words == 2
    assert report.phrases_set_aside == 1
    assert report.events["laughter"] == [(2, pytest.approx(0.9))]
    assert fakes.transcribe_calls == fakes.event_calls == 1
    assert fakes.detector_used == [False], "mixed track: the detector would drop speech under music"


@needs_ffmpeg
def test_multitrack_prepares_a_separate_game_file(conn, settings, tmp_path, monkeypatch):
    fakes = FakeModels(monkeypatch)
    rec_id, _ = _imported(conn, settings, tmp_path, tracks=4)
    result = pipeline.analyze_recording(conn, settings, str(rec_id))
    assert result.status == COMPLETE
    voice, game = fakes.event_paths[0]
    assert game is not None and game.name == "game_32k.wav" and game.exists()
    assert "game_db" in {r[0] for r in conn.execute("SELECT DISTINCT name FROM signals")}
    assert conn.execute("SELECT DISTINCT source_role FROM transcript_words").fetchone()[0] == "mic"
    assert fakes.detector_used == [True], "clean mic track: the detector is reliable"


@needs_ffmpeg
def test_rerun_reuses_everything_and_creates_no_duplicates(conn, settings, tmp_path, monkeypatch):
    fakes = FakeModels(monkeypatch)
    rec_id, _ = _imported(conn, settings, tmp_path)
    pipeline.analyze_recording(conn, settings, str(rec_id))
    rows_before = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]

    again = pipeline.analyze_recording(conn, settings, str(rec_id))
    assert [s.reused for s in again.steps] == [True, True, True, True, True]
    assert fakes.transcribe_calls == 1, "Whisper must not run twice"
    assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == rows_before
    assert conn.execute("SELECT COUNT(*) FROM transcript_words").fetchone()[0] == 2


@needs_ffmpeg
def test_silence_threshold_change_needs_no_reanalysis(conn, settings, tmp_path, monkeypatch):
    """Results are re-read from saved files, so this setting applies instantly."""
    fakes = FakeModels(monkeypatch)
    rec_id, _ = _imported(conn, settings, tmp_path)
    pipeline.analyze_recording(conn, settings, str(rec_id))

    settings.analysis.silence_threshold_db = -10.0  # everything counts as quiet now
    pipeline.analyze_recording(conn, settings, str(rec_id))
    silent = conn.execute("SELECT SUM(value) FROM signals WHERE name = 'silence'").fetchone()[0]
    assert silent == 4
    assert fakes.transcribe_calls == 1


@needs_ffmpeg
def test_interrupted_analysis_resumes_without_redoing_transcription(
    conn, settings, tmp_path, monkeypatch
):
    fakes = FakeModels(monkeypatch)
    rec_id, _ = _imported(conn, settings, tmp_path)

    def ctrl_c(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "detect_sound_events", ctrl_c)
    with pytest.raises(KeyboardInterrupt):
        pipeline.analyze_recording(conn, settings, str(rec_id))
    assert conn.execute("SELECT status FROM jobs WHERE job_type='analyze'").fetchone()[0] == PAUSED
    assert conn.execute("SELECT analysis_status FROM recordings").fetchone()[0] == "paused"

    monkeypatch.setattr(pipeline, "detect_sound_events", fakes.events)
    resumed = pipeline.analyze_recording(conn, settings, str(rec_id))
    assert resumed.status == COMPLETE
    assert [s.reused for s in resumed.steps] == [True, True, False, False, False]
    assert fakes.transcribe_calls == 1


@needs_ffmpeg
def test_model_download_failure_is_a_resumable_failure(conn, settings, tmp_path, monkeypatch):
    FakeModels(monkeypatch)
    rec_id, _ = _imported(conn, settings, tmp_path)

    def offline(*_args, **_kwargs):
        raise ModelDownloadFailed("The transcription model could not be downloaded")

    monkeypatch.setattr(pipeline, "transcribe", offline)
    result = pipeline.analyze_recording(conn, settings, str(rec_id))
    assert result.status == "failed"
    assert "E030" in result.error_message
    assert conn.execute("SELECT analysis_status FROM recordings").fetchone()[0] == "failed"


# --- Model downloads -------------------------------------------------------


def test_download_saves_the_file(tmp_path):
    source = tmp_path / "model.bin"
    source.write_bytes(b"x" * 2048)
    target = models.download(source.as_uri(), tmp_path / "models" / "m.bin",
                             min_bytes=1024, what="test model")
    assert target.read_bytes() == b"x" * 2048


def test_download_is_skipped_when_already_present(tmp_path):
    target = tmp_path / "m.bin"
    target.write_bytes(b"y" * 2048)
    models.download("file:///does/not/exist", target, min_bytes=1024, what="test model")
    assert target.read_bytes() == b"y" * 2048


def test_failed_download_leaves_nothing_behind(tmp_path):
    target = tmp_path / "m.bin"
    with pytest.raises(ModelDownloadFailed):
        models.download((tmp_path / "missing.bin").as_uri(), target, what="test model")
    assert not target.exists()
    assert not list(tmp_path.glob("*.partial"))


def test_truncated_download_is_rejected(tmp_path):
    source = tmp_path / "small.bin"
    source.write_bytes(b"z" * 10)
    with pytest.raises(ModelDownloadFailed) as excinfo:
        models.download(source.as_uri(), tmp_path / "m.bin", min_bytes=1000, what="test model")
    assert "incomplete" in excinfo.value.user_message()


def test_out_of_memory_is_recognised_from_either_engine():
    assert models.is_out_of_memory(RuntimeError("CUDA out of memory. Tried to allocate"))
    assert models.is_out_of_memory(RuntimeError("CUDA failed with error out of memory"))
    assert not models.is_out_of_memory(RuntimeError("file not found"))


def test_sound_groups_map_to_label_columns():
    from ai_editor.analysis.sound_events import group_columns

    labels = ["Speech", "Laughter", "Giggle", "Gunshot, gunfire", "Music", "Screaming"]
    columns = group_columns(labels)
    assert columns["laughter"] == [1, 2]
    assert columns["gunfire"] == [3]
    assert columns["music"] == [4]
    assert "explosion" not in columns, "a group with no matching labels is skipped"


def test_json_results_round_trip(tmp_path):
    path = tmp_path / "x.json"
    pipeline._write_json(path, {"a": [1, 2]})
    assert json.loads(path.read_text()) == {"a": [1, 2]}
    assert not path.with_suffix(".partial.json").exists()


def test_windowed_scores_cover_every_second():
    from ai_editor.analysis.audio_signals import spread_to_seconds, window_starts

    starts = window_starts(7, 2.0)
    per_second = spread_to_seconds(np.ones((len(starts), 1), np.float32), starts, 2.0, 7)
    assert per_second[:, 0].tolist() == [1.0] * 7
