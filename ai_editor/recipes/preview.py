"""A quick watchable version of an edit plan, cut from the preview copies.

For judging a recipe's choices before anything is rendered properly: which
clips, in what order, trimmed where. It is low resolution and has no effects;
the real render from the original footage, with burned-in captions, is Phase
1G. Subtitles come as a file beside the video, so VLC shows them.

Each segment is encoded to the same size, frame rate and sound format, so the
pieces can be joined without encoding everything a second time.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Callable

from ..analysis.captions import Cue, Word, segment_cues, write_srt
from ..analysis.clips import load_words
from ..config import Settings
from ..errors import MediaProcessingFailed, NotImported
from ..ffmpeg import nvenc_encoders, run_ffmpeg
from ..logging_setup import get_logger
from .plan import EditPlan

log = get_logger(__name__)

FOLDER = "plan-previews"
HEIGHT = 540
FPS = 30


def preview_path(settings: Settings, plan: EditPlan) -> Path:
    return settings.folders.output / FOLDER / f"{plan.plan_id}.mp4"


def _encode(proxy: Path, start: float, length: float, target: Path, gpu: bool) -> list[str]:
    video = (["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "26", "-b:v", "0"]
             if gpu else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])
    return [
        "-ss", f"{start:.3f}", "-i", str(proxy), "-t", f"{length:.3f}",
        "-map", "0:v:0", "-map", "0:a:0?",
        # Same shape for every piece, whichever recording it came from.
        "-vf", f"scale=-2:{HEIGHT},fps={FPS},format=yuv420p",
        *video, "-g", str(FPS),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        str(target),
    ]


SHORT_SIZE = (540, 960)
SAFE_ZONE_SHADE = "red@0.12"
SAFE_ZONE_EDGE = "red@0.7"


def safe_zone_boxes(zone) -> list[str]:
    """Faint red where the apps' buttons and text cover a Short (preview only)."""
    boxes = []
    if zone.bottom:
        boxes.append(f"drawbox=x=0:y=ih*{1 - zone.bottom:.3f}:w=iw:h=ih*{zone.bottom:.3f}:"
                     f"color={SAFE_ZONE_SHADE}:t=fill")
    if zone.right:
        boxes.append(f"drawbox=x=iw*{1 - zone.right:.3f}:y=0:w=iw*{zone.right:.3f}:"
                     f"h=ih*{1 - zone.bottom:.3f}:color={SAFE_ZONE_SHADE}:t=fill")
    if zone.top:
        boxes.append(f"drawbox=x=0:y=0:w=iw*{1 - zone.right:.3f}:h=ih*{zone.top:.3f}:"
                     f"color={SAFE_ZONE_SHADE}:t=fill")
    # A thin line where the covered areas begin, so the free area is easy to see.
    free_w, top, bottom = 1 - zone.right, zone.top, 1 - zone.bottom
    boxes.append(f"drawbox=x=0:y=ih*{top:.3f}:w=iw*{free_w:.3f}:h=ih*{bottom - top:.3f}:"
                 f"color={SAFE_ZONE_EDGE}:t=2")
    return boxes


def render_short_preview(conn: sqlite3.Connection, settings: Settings, plan: EditPlan,
                         on_progress: Callable[[float], None] | None = None, *,
                         target: Path | None = None) -> Path:
    """A Short as it will look -- tall, its layout, its captions -- from the
    preview copy, with the areas the apps cover shaded. Seconds, not minutes."""
    from ..analysis.captions import realistic_timing
    from ..config import RenderPreset
    from ..render.captions import short_document
    from ..render.final import vertical_of
    from ..render.vertical import picture_graph

    target = target or preview_path(settings, plan)
    target.parent.mkdir(parents=True, exist_ok=True)
    segment = plan.segments[0]
    row = conn.execute("SELECT proxy_path FROM recordings WHERE id = ?",
                       (segment.recording_id,)).fetchone()
    proxy = Path(row["proxy_path"]) if row and row["proxy_path"] else None
    if proxy is None or not proxy.exists():
        raise NotImported(f"The preview copy of recording #{segment.recording_id} is missing")
    width, height = SHORT_SIZE
    preset = RenderPreset(width=width, height=height, fps=FPS, bitrate="3M")
    zone = settings.shorts.safe_zone()
    work = target.with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    finish = []
    if settings.shorts.captions and segment.captions:
        words = realistic_timing(load_words(conn, segment.recording_id))
        (work / "captions.ass").write_text(short_document(
            words, segment.src_in, segment.src_out, width=width, height=height,
            style=settings.captions, zone=zone), encoding="utf-8")
        finish.append("subtitles=filename=captions.ass")
    finish += [*safe_zone_boxes(zone), "format=yuv420p"]
    from ..ffmpeg import probe

    info = probe(proxy)
    graph = picture_graph(vertical_of(settings, plan), (info.width or 960, info.height or 540),
                          preset, finish=finish)
    gpu = settings.performance.device == "gpu" and "h264_nvenc" in nvenc_encoders()

    def args(use_gpu: bool) -> list[str]:
        video = (["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "26", "-b:v", "0"]
                 if use_gpu else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])
        return ["-ss", f"{segment.src_in:.3f}", "-i", str(proxy), "-t", f"{segment.length:.3f}",
                "-filter_complex", graph, "-map", "[v]", "-map", "0:a:0?", *video,
                "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", str(target)]

    try:
        try:
            run_ffmpeg(args(gpu), duration_sec=segment.length, on_progress=on_progress, cwd=work,
                       what="making a Short's preview")
        except MediaProcessingFailed:
            if not gpu:
                raise
            run_ffmpeg(args(False), duration_sec=segment.length, on_progress=on_progress,
                       cwd=work, what="making a Short's preview")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if on_progress:
        on_progress(1.0)
    return target


def render_preview(
    conn: sqlite3.Connection,
    settings: Settings,
    plan: EditPlan,
    on_progress: Callable[[float], None] | None = None,
    *,
    labels: list[str] | None = None,
    target: Path | None = None,
) -> Path:
    """``labels``: a caption per segment shown instead of what was said (the
    Let's Play cuts reel names each cut). ``target``: where to save it."""
    target = target or preview_path(settings, plan)
    parts_dir = target.with_suffix("")  # a working folder beside it, removed at the end
    parts_dir.mkdir(parents=True, exist_ok=True)
    gpu = settings.performance.device == "gpu" and "h264_nvenc" in nvenc_encoders()

    proxies = {r["id"]: Path(r["proxy_path"]) for r in conn.execute(
        f"SELECT id, proxy_path FROM recordings WHERE id IN "
        f"({','.join('?' * len(plan.recording_ids))})", plan.recording_ids)}
    words: dict[int, list[Word]] = {}
    cues: list[Cue] = []
    parts: list[Path] = []
    offset = 0.0
    total = max(plan.total_sec, 1.0)
    try:
        for index, segment in enumerate(plan.segments):
            proxy = proxies.get(segment.recording_id)
            if proxy is None or not proxy.exists():
                raise NotImported(f"The preview copy of recording #{segment.recording_id} is missing")
            part = parts_dir / f"{index:03d}.mp4"
            args = _encode(proxy, segment.src_in, segment.length, part, gpu)
            try:
                run_ffmpeg(args, what="cutting part of a video preview")
            except MediaProcessingFailed:
                if not gpu:
                    raise
                gpu = False
                run_ffmpeg(_encode(proxy, segment.src_in, segment.length, part, False),
                           what="cutting part of a video preview")
            parts.append(part)

            if labels is not None:
                if labels[index]:
                    cues.append(Cue(offset, offset + segment.length, labels[index]))
            elif segment.captions:
                if segment.recording_id not in words:
                    words[segment.recording_id] = load_words(conn, segment.recording_id)
                cues += [Cue(c.start + offset, c.end + offset, c.text) for c in
                         segment_cues(words[segment.recording_id], segment.src_in, segment.src_out)]
            offset += segment.length
            if on_progress:
                on_progress(min(0.95, offset / total))

        listing = parts_dir / "parts.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
                    "-movflags", "+faststart", str(target)], what="joining a video preview")
        write_srt(cues, target.with_suffix(".srt"))
    finally:
        shutil.rmtree(parts_dir, ignore_errors=True)
    if on_progress:
        on_progress(1.0)
    return target
