"""Ingest: bring a recording into the clip library (spec section 7.2).

Importing does four things:

1. Registers the recording: metadata from ffprobe, a content hash, a game tag,
   and a role for every audio track.
2. Makes a proxy -- a small, low frame rate copy used for previews and
   analysis. Final renders always read the original file.
3. Extracts every audio track to WAV, the format the analysis stages read.
4. Records all of it so re-importing is instant (spec section 5).

Source files are read where they are and never copied or modified. Working
files go under ``<cache>/recordings/<content hash>/``, so everything belonging
to one recording can be found, measured, and cleaned up together (spec
section 10).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import Settings
from .errors import (
    InvalidTrackRoles,
    LowDiskSpace,
    MediaProcessingFailed,
    MediaUnreadable,
    NoAudioTrack,
)
from .ffmpeg import MediaInfo, content_hash, nvenc_encoders, probe, run_ffmpeg
from .games import canonical_game, suggest_game
from .jobs import JobQueue, make_cache_key
from .logging_setup import get_logger

log = get_logger(__name__)

TRACK_ROLES = ("mixed", "mic", "game", "voice_chat", "unknown")

# Bump these when the way a proxy or audio file is made changes meaning, so
# files made the old way are regenerated instead of silently reused.
PROXY_VERSION = 1
AUDIO_VERSION = 1

# Generous upper bound on proxy bitrate, used only to estimate disk space.
_PROXY_BITS_PER_SEC = 3_000_000

ProgressCallback = Callable[[str, float], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Registration ----------------------------------------------------------


@dataclass
class Registration:
    recording_id: int
    content_hash: str
    info: MediaInfo
    is_new: bool
    game: str | None
    track_roles: dict[int, str]
    relinked_from: str | None = None


def parse_track_roles(text: str, info: MediaInfo) -> dict[int, str]:
    """Turn "mixed,mic,game,voice_chat" into {stream index: role}.

    Labels are given in track order. Manual chapter 10.1 step 3: the creator
    confirms which track is which.
    """
    labels = [part.strip().lower() for part in text.split(",") if part.strip()]
    if len(labels) != len(info.audio):
        raise InvalidTrackRoles(
            f"This recording has {len(info.audio)} audio track(s) but "
            f"{len(labels)} label(s) were given"
        )
    unknown = [label for label in labels if label not in TRACK_ROLES]
    if unknown:
        raise InvalidTrackRoles(
            f"Unrecognised label(s): {', '.join(unknown)}. "
            f"Use: {', '.join(TRACK_ROLES)}"
        )
    return {stream.index: label for stream, label in zip(info.audio, labels)}


def register_recording(
    conn: sqlite3.Connection,
    path: str | Path,
    *,
    game: str | None = None,
    track_roles: str | None = None,
    source_type: str | None = None,
) -> Registration:
    """Add a recording to the library, or find it if it's already there.

    The same file imported twice is matched by content hash, not by path, so a
    recording that was moved is recognised and its location updated rather
    than analysed a second time.
    """
    media_path = Path(path).resolve()
    info = probe(media_path)
    if info.video_codec is None:
        raise MediaUnreadable(f"{media_path.name} has no video stream")
    if not info.audio:
        raise NoAudioTrack(media_path.name)

    roles = parse_track_roles(track_roles, info) if track_roles else info.track_roles_guess()
    chosen_game = canonical_game(game) if game else suggest_game(media_path.stem)
    digest = content_hash(media_path)

    existing = conn.execute(
        "SELECT id, source_file, game FROM recordings WHERE content_hash = ?", (digest,)
    ).fetchone()

    if existing:
        recording_id = existing["id"]
        relinked_from = None
        if existing["source_file"] != str(media_path):
            relinked_from = existing["source_file"]
            conn.execute(
                "UPDATE recordings SET source_file = ? WHERE id = ?",
                (str(media_path), recording_id),
            )
            log.info("Recording #%d moved: %s -> %s", recording_id, relinked_from, media_path)
        if source_type:
            conn.execute("UPDATE recordings SET source_type = ? WHERE id = ?",
                         (source_type, recording_id))
        if game:
            conn.execute("UPDATE recordings SET game = ? WHERE id = ?", (chosen_game, recording_id))
        else:
            chosen_game = existing["game"]
        if track_roles:
            for index, role in roles.items():
                conn.execute(
                    "UPDATE audio_tracks SET role = ? WHERE recording_id = ? AND stream_index = ?",
                    (role, recording_id, index),
                )
        else:
            roles = {
                row["stream_index"]: row["role"]
                for row in conn.execute(
                    "SELECT stream_index, role FROM audio_tracks WHERE recording_id = ?",
                    (recording_id,),
                )
            }
        conn.commit()
        return Registration(recording_id, digest, info, False, chosen_game, roles, relinked_from)

    recorded_at = datetime.fromtimestamp(media_path.stat().st_mtime, timezone.utc)
    cursor = conn.execute(
        "INSERT INTO recordings (content_hash, source_type, source_file, game, title, "
        "duration_sec, width, height, fps, container, video_codec, size_bytes, "
        "recorded_at, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            digest,
            source_type or "local_obs",
            str(media_path),
            chosen_game,
            media_path.stem,
            info.duration_sec,
            info.width,
            info.height,
            info.fps,
            info.container,
            info.video_codec,
            info.size_bytes,
            recorded_at.isoformat(timespec="seconds"),
            _now(),
        ),
    )
    recording_id = int(cursor.lastrowid or 0)
    for stream in info.audio:
        conn.execute(
            "INSERT INTO audio_tracks (recording_id, stream_index, role, codec, "
            "channels, sample_rate, bit_rate) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                recording_id,
                stream.index,
                roles.get(stream.index, "unknown"),
                stream.codec,
                stream.channels,
                stream.sample_rate,
                stream.bit_rate,
            ),
        )
    conn.commit()
    log.info("Registered recording #%d: %s", recording_id, media_path.name)
    return Registration(recording_id, digest, info, True, chosen_game, roles)


# --- Disk space ------------------------------------------------------------


def estimate_ingest_bytes(info: MediaInfo) -> int:
    """Upper estimate of the working files an import will write.

    Uncompressed 16-bit WAV is the bulk of it: about 10 MB per minute per
    stereo track at 44.1 kHz.
    """
    duration = info.duration_sec or 0.0
    proxy = duration * _PROXY_BITS_PER_SEC / 8
    audio = sum(
        duration * (s.sample_rate or 48_000) * (s.channels or 2) * 2 for s in info.audio
    )
    return int((proxy + audio) * 1.2)


def check_space(settings: Settings, needed_bytes: int) -> str | None:
    """Refuse to start when the cache drive can't hold the job.

    Returns a warning when the job fits but leaves less free space than the
    creator's warning threshold (manual chapter 23.1). Better to stop before
    starting than to fill the drive an hour in.
    """
    folder = settings.folders.cache
    folder.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(folder).free
    gb = 1024**3
    if free < needed_bytes:
        raise LowDiskSpace(
            f"This import needs about {needed_bytes / gb:,.1f} GB and only "
            f"{free / gb:,.1f} GB is free where the cache folder is"
        )
    left_after = (free - needed_bytes) / gb
    if left_after < settings.storage.low_space_warning_gb:
        return (
            f"After this import about {left_after:,.0f} GB will be free, below "
            f"your warning level of {settings.storage.low_space_warning_gb:,.0f} GB."
        )
    return None


# --- Proxy -----------------------------------------------------------------


def proxy_size(info: MediaInfo, target_height: int) -> tuple[int, int]:
    """Proxy width and height: the source aspect ratio at the target height.

    Never upscales, and keeps both sides even, which H.264 requires.
    """
    src_w, src_h = info.width or 1920, info.height or 1080
    height = min(target_height, src_h)
    height -= height % 2
    width = round(src_w * height / src_h / 2) * 2
    return width, height


def _proxy_audio_stream(info: MediaInfo, roles: dict[int, str]) -> int:
    """The mixed track, so the proxy sounds like what viewers hear."""
    for stream in info.audio:
        if roles.get(stream.index) == "mixed":
            return stream.index
    return info.audio[0].index


def _proxy_attempts(
    source: Path,
    target: Path,
    width: int,
    height: int,
    fps: int,
    audio_index: int,
    use_gpu: bool,
) -> list[tuple[str, list[str]]]:
    """FFmpeg argument lists to try in order, fastest first.

    Full GPU (decode, resize, encode all on the card) is quickest, but CUDA
    decoding can refuse unusual source formats, so each step down gives up a
    little speed for a lot more compatibility.

    Keyframes every second (-g = fps) make scrubbing the proxy responsive.
    """
    common_out = [
        "-map", "0:v:0",
        "-map", f"0:{audio_index}",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-movflags", "+faststart",
        str(target),
    ]
    nvenc = [
        "-c:v", "h264_nvenc", "-preset", "p4",
        "-rc", "vbr", "-cq", "30", "-b:v", "0", "-maxrate", "3M", "-bufsize", "6M",
        "-g", str(fps),
    ]
    attempts: list[tuple[str, list[str]]] = []
    if use_gpu:
        attempts.append((
            "GPU decode and encode",
            [
                "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
                "-i", str(source),
                "-vf", f"fps={fps},scale_cuda={width}:{height}",
                *nvenc, *common_out,
            ],
        ))
        attempts.append((
            "CPU decode, GPU encode",
            [
                "-i", str(source),
                "-vf", f"fps={fps},scale={width}:{height}",
                *nvenc, *common_out,
            ],
        ))
    attempts.append((
        "CPU only",
        [
            "-i", str(source),
            "-vf", f"fps={fps},scale={width}:{height}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-g", str(fps),
            *common_out,
        ],
    ))
    return attempts


def make_proxy(
    settings: Settings,
    source: Path,
    info: MediaInfo,
    roles: dict[int, str],
    output: Path,
    on_progress: Callable[[float], None] | None = None,
) -> str:
    """Write the proxy to ``output``. Returns the method that worked.

    Writes to a .partial file and renames at the end, so an interrupted proxy
    can never be mistaken for a finished one.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + ".partial" + output.suffix)
    width, height = proxy_size(info, settings.performance.proxy_resolution)
    use_gpu = settings.performance.device == "gpu" and "h264_nvenc" in nvenc_encoders()

    last_error: MediaProcessingFailed | None = None
    for method, args in _proxy_attempts(
        source,
        partial,
        width,
        height,
        settings.performance.proxy_fps,
        _proxy_audio_stream(info, roles),
        use_gpu,
    ):
        try:
            run_ffmpeg(
                args,
                duration_sec=info.duration_sec,
                on_progress=on_progress,
                what=f"making the preview copy ({method})",
            )
        except MediaProcessingFailed as exc:
            log.warning("Proxy via %s failed; trying the next method", method)
            last_error = exc
            partial.unlink(missing_ok=True)
            continue
        os.replace(partial, output)
        log.info("Proxy made via %s: %s", method, output)
        return method

    assert last_error is not None
    raise last_error


# --- Audio -----------------------------------------------------------------


def audio_track_path(audio_dir: Path, stream_index: int) -> Path:
    return audio_dir / f"track_{stream_index}.wav"


def extract_audio(
    source: Path,
    info: MediaInfo,
    audio_dir: Path,
    on_progress: Callable[[float], None] | None = None,
) -> list[Path]:
    """Extract every audio track to 16-bit WAV in one pass over the file.

    One pass matters: reading a 13 GB recording once instead of once per track.
    Original sample rate and channels are kept; each analysis stage resamples
    to what its model wants. RF64 lifts plain WAV's 4 GB ceiling, which a long
    stream at 48 kHz stereo would otherwise hit after about 6 hours.
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    finals = [audio_track_path(audio_dir, s.index) for s in info.audio]
    partials = [p.with_name(p.stem + ".partial.wav") for p in finals]

    args = ["-i", str(source)]
    for stream, partial in zip(info.audio, partials):
        args += ["-map", f"0:{stream.index}", "-c:a", "pcm_s16le", "-rf64", "auto", str(partial)]

    try:
        run_ffmpeg(
            args,
            duration_sec=info.duration_sec,
            on_progress=on_progress,
            what="extracting the audio tracks",
        )
    except BaseException:
        for partial in partials:
            partial.unlink(missing_ok=True)
        raise

    for partial, final in zip(partials, finals):
        os.replace(partial, final)
    return finals


# --- The whole import ------------------------------------------------------


@dataclass
class StepReport:
    name: str
    reused: bool
    seconds: float
    output: str
    detail: str = ""


@dataclass
class IngestResult:
    registration: Registration
    job_id: int
    status: str
    error_message: str | None
    cache_dir: Path
    proxy_path: Path
    audio_paths: list[Path]
    steps: list[StepReport] = field(default_factory=list)
    space_warning: str | None = None


def recording_cache_dir(settings: Settings, digest: str) -> Path:
    return settings.folders.cache / "recordings" / digest


def ingest_recording(
    conn: sqlite3.Connection,
    settings: Settings,
    path: str | Path,
    *,
    game: str | None = None,
    track_roles: str | None = None,
    on_progress: ProgressCallback | None = None,
    on_registered: Callable[[Registration, str | None], None] | None = None,
    source_type: str | None = None,
    twitch_vod_id: str | None = None,
    recorded_at: str | None = None,
) -> IngestResult:
    """Import one local recording: register, check space, proxy, audio.

    Safe to call again on the same file at any time. Finished steps are
    reused, an interrupted import picks up where it stopped, and a moved file
    is relinked.
    """
    registration = register_recording(conn, path, game=game, track_roles=track_roles,
                                      source_type=source_type)
    if twitch_vod_id or recorded_at:
        # For a VOD, "recorded" is when the stream happened, not when the file
        # was downloaded -- that is what VOD expiry is counted from.
        conn.execute(
            "UPDATE recordings SET twitch_vod_id = COALESCE(?, twitch_vod_id), "
            "recorded_at = COALESCE(?, recorded_at) WHERE id = ?",
            (twitch_vod_id, recorded_at, registration.recording_id),
        )
        conn.commit()
    info = registration.info
    source = Path(path).resolve()

    space_warning = check_space(settings, estimate_ingest_bytes(info))
    if on_registered:
        on_registered(registration, space_warning)

    queue = JobQueue(conn)
    queue.recover_interrupted()
    open_job = queue.find_open("ingest", registration.recording_id)
    if open_job:
        queue.resume(open_job.id)
        job_id = open_job.id
    else:
        job_id = queue.enqueue(
            "ingest", {"path": str(source)}, recording_id=registration.recording_id
        )

    cache_dir = recording_cache_dir(settings, registration.content_hash)
    proxy_path = cache_dir / "proxy.mp4"
    audio_dir = cache_dir / "audio"
    audio_paths = [audio_track_path(audio_dir, s.index) for s in info.audio]
    width, height = proxy_size(info, settings.performance.proxy_resolution)

    reports: dict[str, StepReport] = {}
    step_names = ("proxy", "audio")

    def reporter(step: str) -> Callable[[float], None]:
        return queue.step_reporter(
            job_id, step, step_names.index(step), len(step_names), on_progress
        )

    def proxy_step() -> str:
        started = time.monotonic()
        method = make_proxy(
            settings, source, info, registration.track_roles, proxy_path, reporter("proxy")
        )
        reports["proxy"] = StepReport(
            "proxy", False, time.monotonic() - started, str(proxy_path), method
        )
        return str(proxy_path)

    def audio_step() -> str:
        started = time.monotonic()
        extract_audio(source, info, audio_dir, reporter("audio"))
        reports["audio"] = StepReport(
            "audio", False, time.monotonic() - started, str(audio_dir),
            f"{len(audio_paths)} track(s)",
        )
        return str(audio_dir)

    digest = registration.content_hash
    queue.run(
        job_id,
        [
            (
                "proxy",
                make_cache_key(
                    digest, "proxy", PROXY_VERSION, width, height,
                    settings.performance.proxy_fps,
                ),
                proxy_step,
            ),
            ("audio", make_cache_key(digest, "audio", AUDIO_VERSION), audio_step),
        ],
    )

    for name, output in (("proxy", str(proxy_path)), ("audio", str(audio_dir))):
        reports.setdefault(name, StepReport(name, True, 0.0, output))

    _sync_paths(conn, registration, proxy_path, audio_dir)

    job = queue.get(job_id)
    error = conn.execute(
        "SELECT error_message FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()["error_message"]

    return IngestResult(
        registration=registration,
        job_id=job_id,
        status=job.status if job else "unknown",
        error_message=error,
        cache_dir=cache_dir,
        proxy_path=proxy_path,
        audio_paths=audio_paths,
        steps=[reports["proxy"], reports["audio"]],
        space_warning=space_warning,
    )


def _sync_paths(
    conn: sqlite3.Connection, registration: Registration, proxy: Path, audio_dir: Path
) -> None:
    """Point the library at whatever working files actually exist on disk.

    Done after every import rather than only when a step runs, because a
    reused step belongs to an earlier job and never wrote this row.
    """
    conn.execute(
        "UPDATE recordings SET proxy_path = ? WHERE id = ?",
        (str(proxy) if proxy.exists() else None, registration.recording_id),
    )
    for stream in registration.info.audio:
        wav = audio_track_path(audio_dir, stream.index)
        conn.execute(
            "UPDATE audio_tracks SET extracted_path = ? "
            "WHERE recording_id = ? AND stream_index = ?",
            (str(wav) if wav.exists() else None, registration.recording_id, stream.index),
        )
    conn.commit()
