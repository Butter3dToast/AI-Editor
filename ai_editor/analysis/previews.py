"""Clip previews: the chosen clips as small video files to watch and judge.

Cut from the preview copy, not the original, so a dozen of them take seconds.
These are for checking what AI-Editor picked and where it put the edges. The
finished videos are rendered from the original footage in Phase 1G.

Each preview gets a subtitle file of the same name beside it, so VLC shows
what was said, lined up with the clip.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Sequence

from ..config import Settings
from ..errors import MediaProcessingFailed
from ..ffmpeg import nvenc_encoders, run_ffmpeg
from ..logging_setup import get_logger
from .captions import Word, build_cues, clock, write_srt

log = get_logger(__name__)

FOLDER = "clip-previews"


def previews_folder(settings: Settings, recording_id: int, title: str | None) -> Path:
    # No "#" or other symbols: PowerShell reads "#" as the start of a comment,
    # so a path containing one breaks when typed or pasted into a terminal.
    safe = "".join(c if c.isalnum() or c in " -_()" else " " for c in (title or ""))
    safe = " ".join(safe.split())[:60]
    return settings.folders.output / FOLDER / f"Recording {recording_id} - {safe}".strip(" -")


def _name(rank: int, start: float, score: float) -> str:
    return f"{rank:02d}  {clock(start).replace(':', '-')}  score {score:.2f}"


def _encode_args(proxy: Path, start: float, length: float, target: Path, gpu: bool) -> list[str]:
    video = (["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "26", "-b:v", "0"]
             if gpu else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])
    return [
        # Seeking before the input is exact when re-encoding, and fast.
        "-ss", f"{start:.3f}", "-i", str(proxy), "-t", f"{length:.3f}",
        "-map", "0:v:0", "-map", "0:a:0?",
        *video,
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(target),
    ]


def export_previews(
    conn: sqlite3.Connection,
    settings: Settings,
    row: sqlite3.Row,
    words: Sequence[Word],
    *,
    count: int,
    on_progress: Callable[[float], None] | None = None,
) -> list[Path]:
    """Write the ``count`` best clips of a recording as preview videos."""
    proxy = Path(row["proxy_path"])
    clips = conn.execute(
        "SELECT start_sec, end_sec, score FROM clips WHERE recording_id = ? "
        "ORDER BY score DESC, start_sec LIMIT ?",
        (row["id"], count),
    ).fetchall()
    folder = previews_folder(settings, row["id"], row["title"])
    folder.mkdir(parents=True, exist_ok=True)
    # This folder only ever holds previews AI-Editor made, so old ones go.
    for old in list(folder.glob("*.mp4")) + list(folder.glob("*.srt")):
        old.unlink()

    gpu = settings.performance.device == "gpu" and "h264_nvenc" in nvenc_encoders()
    written: list[Path] = []
    for rank, clip in enumerate(clips, start=1):
        start, end = float(clip["start_sec"]), float(clip["end_sec"])
        target = folder / f"{_name(rank, start, clip['score'])}.mp4"
        try:
            run_ffmpeg(_encode_args(proxy, start, end - start, target, gpu),
                       what="cutting a clip preview")
        except MediaProcessingFailed:
            if not gpu:
                raise
            log.warning("GPU encoding failed for a preview; using the processor instead")
            run_ffmpeg(_encode_args(proxy, start, end - start, target, False),
                       what="cutting a clip preview")
        inside = [Word(w.text, w.start - start, w.end - start, w.probability)
                  for w in words if w.start >= start and w.end <= end]
        write_srt(build_cues(inside), target.with_suffix(".srt"))
        written.append(target)
        if on_progress:
            on_progress(rank / max(1, len(clips)))
    return written
