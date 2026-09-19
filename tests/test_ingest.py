"""Phase 1A: importing a recording.

The end-to-end tests use short generated clips. The real proof is importing
the creator's own 2-hour recording, which is the Phase 1A acceptance test.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections import namedtuple

import pytest

from ai_editor import ingest
from ai_editor.db import init_db
from ai_editor.errors import InvalidTrackRoles, LowDiskSpace, MediaProcessingFailed
from ai_editor.ffmpeg import AudioStream, MediaInfo, find_binary
from ai_editor.jobs import COMPLETE, FAILED, PAUSED

from .conftest import make_video, needs_ffmpeg


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    yield connection
    connection.close()


def _info(width=1920, height=1080, tracks=1, duration=7563.5):
    return MediaInfo(
        path=None,  # type: ignore[arg-type]
        container="mp4",
        duration_sec=duration,
        size_bytes=13_815_944_782,
        video_codec="h264",
        width=width,
        height=height,
        fps=60.0,
        audio=[
            AudioStream(i + 1, "aac", 2, "stereo", 44_100, 195_064, None, None)
            for i in range(tracks)
        ],
    )


def _stream_facts(path):
    """What ffprobe says about a file's streams, for checking our outputs."""
    result = subprocess.run(
        [
            str(find_binary("ffprobe")), "-v", "error", "-print_format", "json",
            "-show_streams", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)["streams"]


# --- Sizing and labels -----------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ((1920, 1080), (960, 540)),   # the creator's recordings
        ((1280, 720), (960, 540)),
        ((2560, 1080), (1280, 540)),  # ultrawide keeps its shape
        ((640, 360), (640, 360)),     # never upscaled
        ((1080, 1920), (304, 540)),   # vertical source
    ],
)
def test_proxy_size(source, expected):
    assert ingest.proxy_size(_info(*source), 540) == expected


def test_proxy_size_is_always_even():
    """H.264 refuses odd dimensions."""
    for w, h in ((1366, 768), (1600, 900), (1333, 999)):
        pw, ph = ingest.proxy_size(_info(w, h), 540)
        assert pw % 2 == 0 and ph % 2 == 0


def test_track_labels_in_order():
    roles = ingest.parse_track_roles("mixed, mic, game, voice_chat", _info(tracks=4))
    assert roles == {1: "mixed", 2: "mic", 3: "game", 4: "voice_chat"}


def test_wrong_number_of_track_labels():
    with pytest.raises(InvalidTrackRoles) as excinfo:
        ingest.parse_track_roles("mixed,mic", _info(tracks=1))
    assert "1 audio track" in excinfo.value.user_message()


def test_unknown_track_label():
    with pytest.raises(InvalidTrackRoles) as excinfo:
        ingest.parse_track_roles("microphone", _info(tracks=1))
    assert "microphone" in excinfo.value.user_message()


# --- Disk space ------------------------------------------------------------


def test_space_estimate_for_the_creators_recording():
    """2h06m, one stereo 44.1 kHz track: roughly 1.3 GB WAV + up to 2.8 GB proxy."""
    estimate = ingest.estimate_ingest_bytes(_info())
    assert 3 * 1024**3 < estimate < 6 * 1024**3


def test_refuses_to_start_without_space(settings, monkeypatch):
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(ingest.shutil, "disk_usage", lambda _p: usage(100, 99, 1024**3))
    with pytest.raises(LowDiskSpace) as excinfo:
        ingest.check_space(settings, 5 * 1024**3)
    assert "5.0 GB" in excinfo.value.user_message()


def test_warns_when_space_gets_low(settings, monkeypatch):
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(ingest.shutil, "disk_usage", lambda _p: usage(0, 0, 60 * 1024**3))
    settings.storage.low_space_warning_gb = 100
    warning = ingest.check_space(settings, 5 * 1024**3)
    assert warning and "55 GB" in warning


# --- Registration ----------------------------------------------------------


@needs_ffmpeg
def test_register_creates_library_rows(conn, tmp_path):
    video = make_video(tmp_path / "Lets Play - The Blood Of DawnWalker - EP 9.mp4", audio_tracks=4)
    reg = ingest.register_recording(conn, video)

    assert reg.is_new
    assert reg.game == "The Blood of Dawnwalker", "game should be guessed from the filename"
    row = conn.execute("SELECT * FROM recordings WHERE id = ?", (reg.recording_id,)).fetchone()
    assert row["width"] == 1280 and row["height"] == 720
    assert row["source_type"] == "local_obs"
    roles = [
        r["role"] for r in conn.execute(
            "SELECT role FROM audio_tracks WHERE recording_id = ? ORDER BY stream_index",
            (reg.recording_id,),
        )
    ]
    assert roles == ["mixed", "mic", "game", "voice_chat"]


@needs_ffmpeg
def test_registering_twice_finds_the_same_recording(conn, tmp_path):
    video = make_video(tmp_path / "ep.mp4")
    first = ingest.register_recording(conn, video, game="tarkov")
    second = ingest.register_recording(conn, video)
    assert second.recording_id == first.recording_id
    assert not second.is_new
    assert second.game == "Escape from Tarkov"
    assert conn.execute("SELECT COUNT(*) FROM recordings").fetchone()[0] == 1


@needs_ffmpeg
def test_moved_file_is_relinked_not_reimported(conn, tmp_path):
    original = make_video(tmp_path / "ep.mp4")
    first = ingest.register_recording(conn, original)

    moved_dir = tmp_path / "moved"
    moved_dir.mkdir()
    moved = shutil.move(str(original), moved_dir / "ep.mp4")
    second = ingest.register_recording(conn, moved)

    assert second.recording_id == first.recording_id
    assert second.relinked_from == str(original.resolve())
    stored = conn.execute("SELECT source_file FROM recordings").fetchone()[0]
    assert stored == str(moved_dir.joinpath("ep.mp4").resolve())


@needs_ffmpeg
def test_relabelling_tracks_on_reimport(conn, tmp_path):
    video = make_video(tmp_path / "ep.mp4", audio_tracks=2)
    ingest.register_recording(conn, video)
    reg = ingest.register_recording(conn, video, track_roles="mic,game")
    assert list(reg.track_roles.values()) == ["mic", "game"]


# --- The full import -------------------------------------------------------


@needs_ffmpeg
def test_full_import(conn, settings, tmp_path):
    video = make_video(tmp_path / "ep.mp4", fps=60, audio_tracks=4)
    fractions: list[tuple[str, float]] = []

    result = ingest.ingest_recording(
        conn, settings, video, game="The Blood of Dawnwalker",
        on_progress=lambda step, f: fractions.append((step, f)),
    )

    assert result.status == COMPLETE, result.error_message

    # Proxy: 540p, 30 fps, one audio track, playable.
    streams = _stream_facts(result.proxy_path)
    video_stream = next(s for s in streams if s["codec_type"] == "video")
    assert (video_stream["width"], video_stream["height"]) == (960, 540)
    assert video_stream["r_frame_rate"] == "30/1"
    assert sum(s["codec_type"] == "audio" for s in streams) == 1

    # Audio: one uncompressed WAV per source track.
    assert len(result.audio_paths) == 4
    for wav in result.audio_paths:
        (stream,) = _stream_facts(wav)
        assert stream["codec_name"] == "pcm_s16le"

    # Library points at the files.
    rec = conn.execute("SELECT proxy_path FROM recordings").fetchone()
    assert rec["proxy_path"] == str(result.proxy_path)
    extracted = [r[0] for r in conn.execute("SELECT extracted_path FROM audio_tracks")]
    assert all(extracted)

    # Progress was reported for both steps and reached the end.
    assert ("proxy", 1.0) in fractions and ("audio", 1.0) in fractions

    # Nothing half-written left behind.
    assert not list(result.cache_dir.rglob("*.partial*"))


@needs_ffmpeg
def test_reimport_reuses_finished_work(conn, settings, tmp_path):
    """Spec section 5: re-importing is instant."""
    video = make_video(tmp_path / "ep.mp4")
    ingest.ingest_recording(conn, settings, video)
    again = ingest.ingest_recording(conn, settings, video)

    assert again.status == COMPLETE
    assert [s.reused for s in again.steps] == [True, True]


@needs_ffmpeg
def test_deleted_proxy_is_remade(conn, settings, tmp_path):
    """After cache cleanup, only the missing piece is redone."""
    video = make_video(tmp_path / "ep.mp4")
    first = ingest.ingest_recording(conn, settings, video)
    first.proxy_path.unlink()

    again = ingest.ingest_recording(conn, settings, video)
    assert again.proxy_path.exists()
    assert [s.reused for s in again.steps] == [False, True]


@needs_ffmpeg
def test_failed_import_resumes_the_same_job(conn, settings, tmp_path, monkeypatch):
    video = make_video(tmp_path / "ep.mp4")
    real_make_proxy = ingest.make_proxy

    def broken(*_args, **_kwargs):
        raise MediaProcessingFailed("while testing")

    monkeypatch.setattr(ingest, "make_proxy", broken)
    failed = ingest.ingest_recording(conn, settings, video)
    assert failed.status == FAILED
    assert "E013" in failed.error_message

    monkeypatch.setattr(ingest, "make_proxy", real_make_proxy)
    retried = ingest.ingest_recording(conn, settings, video)
    assert retried.status == COMPLETE
    assert retried.job_id == failed.job_id, "should resume, not start a second job"


@needs_ffmpeg
def test_interrupted_import_is_paused_and_resumable(conn, settings, tmp_path, monkeypatch):
    """Ctrl+C mid-import pauses the job; running the command again continues it."""
    video = make_video(tmp_path / "ep.mp4")
    real_extract = ingest.extract_audio

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(ingest, "extract_audio", interrupted)
    with pytest.raises(KeyboardInterrupt):
        ingest.ingest_recording(conn, settings, video)
    job = conn.execute("SELECT id, status FROM jobs").fetchone()
    assert job["status"] == PAUSED

    monkeypatch.setattr(ingest, "extract_audio", real_extract)
    resumed = ingest.ingest_recording(conn, settings, video)
    assert resumed.status == COMPLETE
    assert resumed.job_id == job["id"]
    assert [s.reused for s in resumed.steps] == [True, False], "proxy was already done"


@needs_ffmpeg
def test_proxy_falls_back_when_a_method_fails(settings, tmp_path, monkeypatch):
    """If GPU decoding refuses a file, the next method takes over."""
    video = make_video(tmp_path / "ep.mp4")
    info = ingest.probe(video)
    real_attempts = ingest._proxy_attempts

    def with_a_broken_first_attempt(*args, **kwargs):
        good = real_attempts(*args, **kwargs)
        return [("deliberately broken", ["-i", "does-not-exist.mp4", str(args[1])]), *good]

    monkeypatch.setattr(ingest, "_proxy_attempts", with_a_broken_first_attempt)
    output = tmp_path / "proxy.mp4"
    method = ingest.make_proxy(settings, video, info, {1: "mixed"}, output)

    assert method != "deliberately broken"
    assert output.exists()
    assert not (tmp_path / "proxy.partial.mp4").exists()


@needs_ffmpeg
def test_proxy_uses_the_mixed_track(tmp_path):
    """The preview should sound like the video viewers hear, not just the mic."""
    info = _info(tracks=4)
    assert ingest._proxy_audio_stream(info, {1: "mic", 2: "mixed", 3: "game", 4: "voice_chat"}) == 2
    assert ingest._proxy_audio_stream(info, {1: "mic", 2: "game"}) == 1
