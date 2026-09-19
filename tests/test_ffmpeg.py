"""FFmpeg discovery, probing, and content hashing.

Tests that need real media generate it with FFmpeg rather than shipping a
fixture file, and skip cleanly when FFmpeg is not installed.
"""

from __future__ import annotations

import subprocess

import pytest

from ai_editor import ffmpeg
from ai_editor.errors import FFmpegNotFound, MediaFileNotFound, MediaUnreadable


def _ffmpeg_path() -> str | None:
    """Resolve ffmpeg the same way the app does, not just via PATH.

    Checking PATH alone made these tests skip on a machine where FFmpeg was
    installed but the shell predated the install -- exactly the case the
    fallback search exists to handle.
    """
    try:
        return str(ffmpeg.find_binary("ffmpeg"))
    except FFmpegNotFound:
        return None


FFMPEG = _ffmpeg_path()

ffmpeg_available = pytest.mark.skipif(
    FFMPEG is None, reason="FFmpeg is not installed"
)


@pytest.fixture(scope="module")
def single_track_video(tmp_path_factory):
    """A 2-second clip with one audio track, like a Twitch VOD."""
    path = tmp_path_factory.mktemp("media") / "single.mp4"
    subprocess.run(
        [
            FFMPEG, "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


@pytest.fixture(scope="module")
def multi_track_video(tmp_path_factory):
    """A clip with four audio tracks, like an OBS recording set up per manual ch. 7."""
    path = tmp_path_factory.mktemp("media") / "multi.mkv"
    subprocess.run(
        [
            FFMPEG, "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=200:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=400:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=500:duration=2",
            "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:a", "-map", "4:a",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


@ffmpeg_available
def test_finds_binaries():
    assert ffmpeg.find_binary("ffmpeg").exists()
    assert ffmpeg.find_binary("ffprobe").exists()


@ffmpeg_available
def test_version_string():
    assert "ffmpeg version" in ffmpeg.version().lower()


@ffmpeg_available
def test_encoder_list_is_parsed():
    encoders = ffmpeg.available_encoders()
    assert "libx264" in encoders
    # Every entry should be a bare encoder name, not a description fragment.
    assert all(" " not in name for name in encoders)


@ffmpeg_available
def test_probe_reads_video_properties(single_track_video):
    info = ffmpeg.probe(single_track_video)
    assert info.width == 320
    assert info.height == 240
    assert info.fps == pytest.approx(30, abs=0.1)
    assert info.duration_sec == pytest.approx(2.0, abs=0.3)
    assert len(info.audio) == 1
    assert info.is_multitrack is False


@ffmpeg_available
def test_single_track_guesses_mixed(single_track_video):
    info = ffmpeg.probe(single_track_video)
    assert list(info.track_roles_guess().values()) == ["mixed"]


@ffmpeg_available
def test_multitrack_roles_follow_the_obs_convention(multi_track_video):
    """Manual chapter 7.1: tracks are 1 mixed, 2 mic, 3 game, 4 voice chat."""
    info = ffmpeg.probe(multi_track_video)
    assert info.is_multitrack is True
    assert len(info.audio) == 4
    assert list(info.track_roles_guess().values()) == [
        "mixed",
        "mic",
        "game",
        "voice_chat",
    ]


def test_missing_binary_names_the_right_program(monkeypatch):
    """The ffprobe failure must say ffprobe, not FFmpeg generally.

    Reported from a real setup check where every row blamed 'ffmpeg'.
    """
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ffmpeg, "_fallback_dirs", list)
    ffmpeg.find_binary.cache_clear()
    try:
        with pytest.raises(FFmpegNotFound) as excinfo:
            ffmpeg.find_binary("ffprobe")
        assert "'ffprobe'" in excinfo.value.user_message()
    finally:
        ffmpeg.find_binary.cache_clear()


def test_missing_binary_suggests_reopening_the_window(monkeypatch):
    """The usual cause is PATH not refreshed after installing FFmpeg."""
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ffmpeg, "_fallback_dirs", list)
    ffmpeg.find_binary.cache_clear()
    try:
        with pytest.raises(FFmpegNotFound) as excinfo:
            ffmpeg.find_binary("ffmpeg")
        assert "open a new one" in excinfo.value.user_message()
    finally:
        ffmpeg.find_binary.cache_clear()


def test_binary_found_in_a_fallback_folder_when_not_on_path(tmp_path, monkeypatch):
    """Installing FFmpeg and running the check immediately must still work."""
    tool_dir = tmp_path / "ffmpeg" / "bin"
    tool_dir.mkdir(parents=True)
    (tool_dir / "ffmpeg.exe").write_bytes(b"")

    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _name: None)
    ffmpeg.configure_tool_paths(tool_dir)
    try:
        assert ffmpeg.find_binary("ffmpeg") == tool_dir / "ffmpeg.exe"
    finally:
        ffmpeg.configure_tool_paths(None)


def test_configure_tool_paths_clears_the_cache(tmp_path, monkeypatch):
    """Changing the setting must take effect without restarting the app."""
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ffmpeg, "_fallback_dirs", list)
    ffmpeg.find_binary.cache_clear()
    with pytest.raises(FFmpegNotFound):
        ffmpeg.find_binary("ffmpeg")

    tool_dir = tmp_path / "bin"
    tool_dir.mkdir()
    (tool_dir / "ffmpeg.exe").write_bytes(b"")
    monkeypatch.undo()
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _name: None)
    ffmpeg.configure_tool_paths(tool_dir)
    try:
        assert ffmpeg.find_binary("ffmpeg").parent == tool_dir
    finally:
        ffmpeg.configure_tool_paths(None)


def test_probe_missing_file_is_readable(tmp_path):
    with pytest.raises(MediaFileNotFound) as excinfo:
        ffmpeg.probe(tmp_path / "nothing.mp4")
    assert "cannot find" in excinfo.value.user_message().lower()


@ffmpeg_available
def test_probe_garbage_file_is_readable(tmp_path):
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"this is not a video")
    with pytest.raises(MediaUnreadable):
        ffmpeg.probe(bad)


@ffmpeg_available
def test_content_hash_is_stable_and_distinct(single_track_video, multi_track_video):
    first = ffmpeg.content_hash(single_track_video)
    assert first == ffmpeg.content_hash(single_track_video)
    assert first != ffmpeg.content_hash(multi_track_video)


def test_content_hash_notices_a_changed_file(tmp_path):
    """A re-encoded or trimmed file must hash differently so analysis reruns."""
    path = tmp_path / "data.bin"
    path.write_bytes(b"A" * 1000)
    before = ffmpeg.content_hash(path)
    path.write_bytes(b"B" * 1000)
    assert ffmpeg.content_hash(path) != before


def test_content_hash_missing_file(tmp_path):
    with pytest.raises(MediaFileNotFound):
        ffmpeg.content_hash(tmp_path / "gone.mp4")


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("out_time_us=30000000\n", 0.25),
        ("out_time_us=120000000", 1.0),
        ("out_time_us=999999999999", 1.0),  # never past the end
        ("out_time_us=N/A", None),          # before the first frame
        ("frame=120", None),                # other keys ignored
        ("progress=continue", None),
    ],
)
def test_parse_progress_line(line, expected):
    assert ffmpeg.parse_progress_line(line, 120.0) == expected


def test_progress_without_a_duration_is_ignored():
    assert ffmpeg.parse_progress_line("out_time_us=5000000", None) is None
