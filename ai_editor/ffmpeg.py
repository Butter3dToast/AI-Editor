"""FFmpeg and ffprobe: locating them, probing media, checking NVENC.

FFmpeg is the engine behind every cut, zoom, overlay and encode (spec section
4). Everything that shells out to it goes through here so there is one place
that knows where the binaries are and how to read their output.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable

from .errors import (
    FFmpegNotFound,
    MediaFileNotFound,
    MediaProcessingFailed,
    MediaUnreadable,
)
from .logging_setup import get_logger

log = get_logger(__name__)

# Windows: stop a console window flashing up for every probe.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# Folders searched when ffmpeg is not on PATH. Set from settings at startup.
_extra_dirs: tuple[Path, ...] = ()


def configure_tool_paths(ffmpeg_dir: str | Path | None) -> None:
    """Point the finder at an explicit FFmpeg folder from settings."""
    global _extra_dirs
    _extra_dirs = (Path(ffmpeg_dir),) if ffmpeg_dir else ()
    find_binary.cache_clear()


def _fallback_dirs() -> list[Path]:
    """Places FFmpeg commonly lands on Windows.

    Installing FFmpeg updates PATH, but only for windows opened afterwards. A
    creator who installs it and immediately runs the setup check would be told
    it is missing, which is both confusing and untrue. Searching the usual
    install folders makes that case just work.
    """
    local = os.environ.get("LOCALAPPDATA", "")
    candidates: list[Path] = [*_extra_dirs]

    if local:
        winget = Path(local) / "Microsoft" / "WinGet"
        candidates.append(winget / "Links")
        # winget keeps the real binaries in a versioned folder per package.
        packages = winget / "Packages"
        if packages.is_dir():
            for package in packages.glob("*FFmpeg*"):
                candidates.extend(package.glob("*/bin"))

    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if root:
            candidates.append(Path(root) / "ffmpeg" / "bin")
    candidates.append(Path("C:/ffmpeg/bin"))

    return [d for d in candidates if d.is_dir()]


@lru_cache(maxsize=4)
def find_binary(name: str) -> Path:
    """Locate ffmpeg or ffprobe, on PATH or in the usual install folders.

    Cached because `doctor` and every probe call ask repeatedly; the cache is
    cleared by configure_tool_paths.
    """
    found = shutil.which(name)
    if found:
        return Path(found)

    for directory in _fallback_dirs():
        for filename in (f"{name}.exe", name):
            candidate = directory / filename
            if candidate.is_file():
                return candidate

    raise FFmpegNotFound(
        f"'{name}', part of FFmpeg, is not on your PATH and was not in the "
        f"usual install folders"
    )


def _run(binary: Path, args: list[str], timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )


def version(name: str = "ffmpeg") -> str:
    """First line of `ffmpeg -version`, for the setup check and diagnostics."""
    result = _run(find_binary(name), ["-version"], timeout=30.0)
    return result.stdout.splitlines()[0] if result.stdout else "unknown"


def available_encoders() -> set[str]:
    """Encoder names FFmpeg reports, e.g. {'h264_nvenc', 'libx264', ...}."""
    result = _run(find_binary("ffmpeg"), ["-hide_banner", "-encoders"], timeout=30.0)
    names: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        # Encoder lines look like: " V....D h264_nvenc   NVIDIA NVENC H.264 encoder"
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
            names.add(parts[1])
    return names


def nvenc_encoders() -> set[str]:
    """The NVENC encoders present. Empty means no GPU encoding available."""
    return {e for e in available_encoders() if e.endswith("_nvenc")}


# --- Running long FFmpeg jobs ----------------------------------------------


def parse_progress_line(line: str, duration_sec: float | None) -> float | None:
    """Turn one line of `ffmpeg -progress` output into a 0-1 fraction.

    FFmpeg writes key=value lines; `out_time_us` is the position reached in
    the output, in microseconds. It reads "N/A" before the first frame.
    """
    key, _, value = line.strip().partition("=")
    if key != "out_time_us" or not duration_sec or duration_sec <= 0:
        return None
    try:
        seconds = int(value) / 1_000_000
    except ValueError:
        return None
    return max(0.0, min(1.0, seconds / duration_sec))


def run_ffmpeg(
    args: list[str],
    *,
    duration_sec: float | None = None,
    on_progress: Callable[[float], None] | None = None,
    what: str = "processing",
) -> None:
    """Run FFmpeg to completion, reporting progress as it goes.

    On failure the FFmpeg error text goes to the log file and the creator gets
    MediaProcessingFailed (spec section 14.2). If this process is interrupted
    (Ctrl+C, window closed), FFmpeg is killed rather than left running in the
    background still writing to disk.
    """
    command = [
        str(find_binary("ffmpeg")),
        "-hide_banner", "-nostdin", "-y",
        "-loglevel", "error",
        "-nostats", "-progress", "pipe:1",
        *args,
    ]
    log.debug("FFmpeg (%s): %s", what, subprocess.list2cmdline(command))

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
    )

    # stderr is drained on its own thread: if FFmpeg filled that pipe while we
    # were blocked reading stdout, both sides would wait on each other forever.
    errors: deque[str] = deque(maxlen=40)
    drain = threading.Thread(
        target=lambda: errors.extend(process.stderr or ()), daemon=True
    )
    drain.start()

    try:
        for line in process.stdout or ():
            fraction = parse_progress_line(line, duration_sec)
            if fraction is not None and on_progress:
                on_progress(fraction)
        process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise
    finally:
        drain.join(timeout=5)

    if process.returncode != 0:
        log.error(
            "FFmpeg failed while %s (exit %s):\n%s",
            what, process.returncode, "".join(errors).strip(),
        )
        raise MediaProcessingFailed(f"This happened while {what}")

    if on_progress:
        on_progress(1.0)


# --- Probing ---------------------------------------------------------------


@dataclass(frozen=True)
class AudioStream:
    index: int
    codec: str | None
    channels: int | None
    channel_layout: str | None
    sample_rate: int | None
    bit_rate: int | None
    title: str | None
    language: str | None


@dataclass(frozen=True)
class MediaInfo:
    """What ffprobe tells us about a source file."""

    path: Path
    container: str | None
    duration_sec: float | None
    size_bytes: int | None
    video_codec: str | None
    width: int | None
    height: int | None
    fps: float | None
    audio: list[AudioStream] = field(default_factory=list)

    @property
    def is_multitrack(self) -> bool:
        """True when OBS recorded separate tracks (manual chapter 7.1).

        With one mixed track we must separate the creator's voice with Demucs
        instead of using a clean mic track.
        """
        return len(self.audio) > 1

    def track_roles_guess(self) -> dict[int, str]:
        """Best guess at which track is which, by the OBS convention in the manual.

        Tracks are 1 mixed, 2 mic, 3 game, 4 voice chat. This is only a
        suggestion: import asks the creator to confirm, then remembers it.
        """
        convention = ["mixed", "mic", "game", "voice_chat"]
        if len(self.audio) == 1:
            return {self.audio[0].index: "mixed"}
        return {
            stream.index: (convention[i] if i < len(convention) else "unknown")
            for i, stream in enumerate(self.audio)
        }


def _parse_fraction(value: str | None) -> float | None:
    if not value or "/" not in value:
        return None
    num, _, den = value.partition("/")
    try:
        d = float(den)
        return float(num) / d if d else None
    except ValueError:
        return None


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def probe(path: str | Path) -> MediaInfo:
    """Read metadata from a media file.

    Raises MediaFileNotFound or MediaUnreadable so the caller can show the
    creator a plain-language message.
    """
    media_path = Path(path)
    if not media_path.exists():
        raise MediaFileNotFound(f"Looked for {media_path}")

    result = _run(
        find_binary("ffprobe"),
        [
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ],
        timeout=180.0,
    )
    if result.returncode != 0:
        raise MediaUnreadable(f"{media_path.name}: {result.stderr.strip()[:300]}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaUnreadable(f"{media_path.name}: unreadable metadata") from exc

    fmt = data.get("format", {})
    streams = data.get("streams", [])

    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    duration = fmt.get("duration")
    return MediaInfo(
        path=media_path,
        container=fmt.get("format_name"),
        duration_sec=float(duration) if duration else None,
        size_bytes=_as_int(fmt.get("size")),
        video_codec=video.get("codec_name") if video else None,
        width=_as_int(video.get("width")) if video else None,
        height=_as_int(video.get("height")) if video else None,
        fps=_parse_fraction(video.get("r_frame_rate")) if video else None,
        audio=[
            AudioStream(
                index=_as_int(s.get("index")) or 0,
                codec=s.get("codec_name"),
                channels=_as_int(s.get("channels")),
                channel_layout=s.get("channel_layout"),
                sample_rate=_as_int(s.get("sample_rate")),
                bit_rate=_as_int(s.get("bit_rate")),
                title=(s.get("tags") or {}).get("title"),
                language=(s.get("tags") or {}).get("language"),
            )
            for s in audio_streams
        ],
    )


# --- Content hashing -------------------------------------------------------

_HASH_CHUNK = 8 * 1024 * 1024  # 8 MB sampled from three places in the file


def content_hash(path: str | Path) -> str:
    """A fast, stable identifier for a source file.

    Spec section 5 keys every cached stage on "the source file's hash". Reading
    a 13 GB recording end to end just to compute that would cost minutes per
    import, so we hash the file size plus 8 MB from the start, middle and end.

    That is not a cryptographic guarantee, but two different recordings sharing
    an exact size *and* all three sampled regions is not a case that arises with
    video files. Re-encoding or trimming a file changes its hash, which is what
    we want: the analysis is then correctly redone.
    """
    media_path = Path(path)
    if not media_path.exists():
        raise MediaFileNotFound(f"Looked for {media_path}")

    size = media_path.stat().st_size
    digest = hashlib.blake2b(digest_size=16)
    digest.update(str(size).encode())

    with media_path.open("rb") as handle:
        if size <= _HASH_CHUNK * 3:
            digest.update(handle.read())
        else:
            for offset in (0, size // 2, size - _HASH_CHUNK):
                handle.seek(offset)
                digest.update(handle.read(_HASH_CHUNK))

    return digest.hexdigest()
