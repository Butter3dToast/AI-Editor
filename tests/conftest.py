"""Shared test helpers.

Test media is generated with FFmpeg on the fly rather than committed to the
repository: a few seconds of test pattern and tones is enough to exercise
every code path, and nothing large ever lands in git.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from ai_editor import ffmpeg
from ai_editor.config import load_settings
from ai_editor.errors import FFmpegNotFound


def _ffmpeg_path() -> str | None:
    try:
        return str(ffmpeg.find_binary("ffmpeg"))
    except FFmpegNotFound:
        return None


FFMPEG = _ffmpeg_path()

needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="FFmpeg is not installed")


def make_video(
    path: Path,
    *,
    width: int = 1280,
    height: int = 720,
    fps: int = 60,
    seconds: float = 4.0,
    audio_tracks: int = 1,
) -> Path:
    """Write a short test-pattern video with the given number of audio tracks."""
    args = [
        FFMPEG, "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate={fps}:duration={seconds}",
    ]
    for track in range(audio_tracks):
        args += ["-f", "lavfi", "-i", f"sine=frequency={220 + 110 * track}:duration={seconds}"]
    args += ["-map", "0:v"]
    for track in range(audio_tracks):
        args += ["-map", f"{track + 1}:a"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)]
    subprocess.run(args, check=True, capture_output=True)
    return path


@pytest.fixture
def settings(tmp_path):
    """Settings whose five folders all live in a throwaway directory."""
    root = tmp_path.as_posix()
    path = tmp_path / "settings.yaml"
    path.write_text(
        textwrap.dedent(
            f"""
            folders:
              raw: {root}/raw
              cache: {root}/cache
              output: {root}/output
              assets: {root}/assets
              models: {root}/models
            storage:
              low_space_warning_gb: 0
            """
        ),
        encoding="utf-8",
    )
    return load_settings(path)
