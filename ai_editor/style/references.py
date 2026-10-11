"""Getting and measuring a reference video (Phase 2G-1).

A YouTube link is downloaded small (480p at most; only the first half hour
of a long video) into AI-Editor's working folder, measured, and deleted. A
file on this PC is only read where it is: never copied, changed or deleted.

Downloading uses yt-dlp, installed with the creator's go-ahead (2026-10-11).
It may conflict with YouTube's terms (spec section 16), which is why files
work too, and why nothing is kept but the numbers. When YouTube changes
something and downloads fail, updating yt-dlp usually fixes it.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..config import Settings
from ..ffmpeg import find_binary
from ..logging_setup import get_logger
from .measure import MAX_SEC, Measured, measure
from .profiles import Reference, is_link

log = get_logger(__name__)

# The AI looks at this many frames of each reference.
FRAMES = 8
FORMAT = "bv*[height<=480]+ba/b[height<=480]/b"


class ReferenceProblem(Exception):
    """A reference that couldn't be fetched or read, in plain words."""


@dataclass
class Result:
    title: str | None
    measured: Measured
    frames: list[bytes]      # JPEGs for the AI, from where things happen


def working_folder(settings: Settings, reference_id: int) -> Path:
    return settings.folders.cache / "style" / f"reference-{reference_id}"


def tidy(folder: Path, settings: Settings) -> None:
    """Delete a reference's working folder: only ever inside the cache's style folder."""
    root = (settings.folders.cache / "style").resolve()
    target = folder.resolve()
    if target == root or root not in target.parents:
        raise ValueError(f"Refusing to delete {folder}: not a reference's working folder")
    shutil.rmtree(target, ignore_errors=True)


def download(settings: Settings, url: str, folder: Path,
             on_progress: Callable[[float], None]) -> tuple[Path, str | None]:
    """The video at ``url``, small, into ``folder``. Returns (file, title)."""
    import yt_dlp
    from yt_dlp.utils import DownloadError, download_range_func

    def hook(d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                on_progress(min(0.99, d.get("downloaded_bytes", 0) / total))

    folder.mkdir(parents=True, exist_ok=True)
    options = {
        "format": FORMAT, "merge_output_format": "mp4", "noplaylist": True,
        "outtmpl": str(folder / "reference.%(ext)s"), "quiet": True, "no_warnings": True,
        "noprogress": True, "progress_hooks": [hook],
        "ffmpeg_location": str(find_binary("ffmpeg").parent),
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("_type") == "playlist":
                raise ReferenceProblem("That's a playlist: paste the link of one video.")
            if (info.get("duration") or 0) > MAX_SEC + 60:   # only what gets measured
                ydl.params["download_ranges"] = download_range_func(None, [(0, MAX_SEC)])
            ydl.process_ie_result(info, download=True)
    except DownloadError as exc:
        reason = str(exc).replace("ERROR: ", "").split("\n")[0][:200]
        raise ReferenceProblem(f"Couldn't download it: {reason}. If YouTube changed something, "
                               "updating yt-dlp usually fixes it (manual chapter 13).") from exc
    found = sorted(folder.glob("reference.*"), key=lambda p: p.stat().st_size, reverse=True)
    if not found:
        raise ReferenceProblem("The download didn't leave a video behind.")
    on_progress(1.0)
    return found[0], info.get("title")


def analyse(settings: Settings, reference: Reference,
            on_progress: Callable[[str, float], None]) -> Result:
    """Fetch (if it's a link), measure, and take frames for the AI. The working
    folder is deleted at the end, whatever happens."""
    from ..analysis.ai_rating import grab_frame

    folder = working_folder(settings, reference.id)
    try:
        if is_link(reference.source):
            video, title = download(settings, reference.source, folder,
                                    lambda f: on_progress("Downloading", f))
        else:
            video, title = Path(reference.source), Path(reference.source).stem
            if not video.is_file():
                raise ReferenceProblem(f"Can't find {video} any more.")
        measured = measure(settings, video, folder / "work", on_progress)
        frames = [f for f in (grab_frame(video, t) for t in frame_times(measured)) if f]
        return Result(title, measured, frames)
    finally:
        tidy(folder, settings)


def frame_times(m: Measured, count: int = FRAMES) -> list[float]:
    """Where the AI looks: where zooms and meme sounds were, then evenly through the rest."""
    span = max(1.0, m.measured_sec)
    picked = [t for t in m.moments if 1.0 <= t <= span - 1.0][: count // 2]
    step = span / (count - len(picked) + 1)
    even = [round(step * (i + 1), 1) for i in range(count - len(picked))]
    return sorted({round(t + 0.3, 1) for t in picked} | set(even))[:count]
