"""Finished videos: an edit plan cut from the original recordings (spec 7.9).

Previews come from the small preview copies. A finished video goes back to
the recording itself, full size and frame rate, encoded on the graphics card
(NVENC). How:

1. Each segment is cut and encoded on its own, frame-exact, its sound rebuilt
   from the right tracks (render/audio.py), with any marker beep filtered
   out, and faded over a few milliseconds at each end so no join clicks.
   The sound stays uncompressed until the end so nothing is encoded twice.
2. The segments are joined as they are, then the whole video's loudness is
   measured and set in one go (about -14 LUFS, what YouTube plays at). One
   setting for the whole video, so a quiet clip stays quieter than a loud one
   the way it was, and no clip's level jumps. A limiter keeps the loudest
   peaks from going over (loudness_filter).

The video appears under its real name only once it's complete: a render
stopped half-way never looks finished.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..config import Effects, RenderPreset, Settings
from ..effects import Effect, for_plan as effects_for_plan, summary as effects_summary
from ..effects import picture as picture_fx, sfx
from ..errors import LowDiskSpace, MediaFileNotFound, MediaProcessingFailed
from ..ffmpeg import measure_loudness, nvenc_encoders, run_ffmpeg
from ..logging_setup import get_logger
from ..recipes.plan import EditPlan
from ..analysis.captions import Cue, realistic_timing, segment_cues
from ..analysis.clips import load_words
from .audio import AudioChoice, beep_filters, plan_audio
from .captions import short_document, write_ass
from .vertical import Vertical, picture_graph

log = get_logger(__name__)

FOLDER = "videos"
SHORTS_FOLDER = "shorts"
AUDIO_RATE = 48000
AUDIO_BITRATE = "320k"
FADE_SEC = 0.015      # at every join: too short to hear as a dip, long enough to stop a click
TRUE_PEAK_DB = -1.5   # headroom so YouTube's own encoding doesn't clip
# The most any peak is held down to reach YouTube's loudness. 9 dB made the
# characters' voices in EP 1 sound distorted (raised 11 dB from -25 LUFS, its
# loudest lines held down by up to 4.4 dB); at 3 dB the limiter is inaudible.
MAX_LIMITING_DB = 3.0
# Every finished video is tagged as the standard HD colours OBS records in, so
# players don't guess (a wrong guess looks washed out or too dark).
COLOUR = ["-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709",
          "-color_trc", "bt709"]
# Waiting for a video that's open in a player to be let go, before keeping both.
REPLACE_TRIES = 6
REPLACE_WAIT_SEC = 0.5
# Uncompressed float sound while working: 48 kHz stereo, 4 bytes a sample.
WORKING_AUDIO_BYTES_PER_SEC = AUDIO_RATE * 2 * 4


@dataclass
class RenderResult:
    path: Path
    length_sec: float
    encoder: str                      # what encoded the picture
    seconds_taken: float
    audio: dict[int, AudioChoice] = field(default_factory=dict)  # per recording
    captions: int | None = None       # how many were burned in; None = captions off
    notes: list[str] = field(default_factory=list)

    @property
    def beeps_removed(self) -> int:
        return sum(len(c.beeps) for c in self.audio.values())


def video_path(settings: Settings, plan: EditPlan, *, captions: bool = False) -> Path:
    """Captioned and plain versions are named apart, so one never replaces the other."""
    if plan.recipe == "shorts":  # always captioned: one file, its own folder
        return settings.folders.output / SHORTS_FOLDER / f"{plan.plan_id}.mp4"
    return settings.folders.output / FOLDER / f"{plan.plan_id}{' captions' if captions else ''}.mp4"


def vertical_of(settings: Settings, plan: EditPlan) -> Vertical:
    """A Short's layout: the one chosen in Review, else the game's."""
    shorts = settings.shorts
    game = plan.game or ""
    layout = (plan.source or {}).get("layout") or shorts.layout_for(game)
    facecam = shorts.facecam.get(game)
    if layout == "facecam_top" and facecam is None:
        layout = "crop"  # no facecam marked for this game (yet)
    return Vertical(layout, shorts.crop_centre.get(game, 0.5), facecam, shorts.facecam_share,
                    shorts.fill_for(game))


def bits(rate: str) -> int:
    """'16M' -> 16000000."""
    rate = rate.strip().upper()
    scale = {"K": 1_000, "M": 1_000_000}.get(rate[-1:], 1)
    return int(float(rate[:-1] if scale > 1 else rate) * scale)


def frame_exact(seconds: float, fps: int) -> float:
    """A length that's a whole number of frames, so joins never drift."""
    return max(1, round(seconds * fps)) / fps


def video_codec(settings: Settings, preset: RenderPreset, encoder: str) -> list[str]:
    rate = bits(preset.bitrate)
    common = ["-b:v", str(rate), "-maxrate", str(rate * 3 // 2), "-bufsize", str(rate * 2),
              "-g", str(preset.fps * 2)]
    if encoder.endswith("_nvenc"):
        return ["-c:v", encoder, "-preset", settings.render.nvenc_preset, "-tune", "hq",
                "-rc", "vbr", *common, "-spatial-aq", "1", "-temporal-aq", "1",
                "-profile:v", "high" if encoder == "h264_nvenc" else "main"]
    return ["-c:v", "libx264", "-preset", "medium", *common, "-profile:v", "high"]


def segment_args(source: Path, seg_in: float, length: float, audio: AudioChoice,
                 preset: RenderPreset, source_size: tuple[int, int], codec: list[str],
                 target: Path, *, gpu_decode: bool, captions: str | None = None,
                 vertical: Vertical | None = None, effects: list[Effect] | None = None,
                 sounds: list[sfx.Placed] | None = None, fx: Effects | None = None) -> list[str]:
    """FFmpeg arguments for one segment: picture, rebuilt sound, beeps out, soft edges.

    ``captions``: an ASS file's name, in the folder FFmpeg runs in. A bare name
    because a Windows path's drive colon ("C:") clashes with how filter options are written.
    ``vertical``: a Short's tall picture (render/vertical.py), made from the 16:9 one.
    ``effects``, ``sounds``: flashes and shakes on the picture, sound effects in
    the mix (effects/). The captions go on after, so they never shake or flash.
    """
    finish = ([f"subtitles=filename={captions}"] if captions else []) + ["format=yuv420p"]
    moves = picture_fx.graph(effects or [], seg_in, preset.height, fx or Effects(),
                             "pic", "moved")
    made = "pic" if moves else "v"
    if vertical is not None:
        graph = [picture_graph(vertical, source_size, preset, finish=[] if moves else finish,
                               out=made)]
    else:
        picture = [f"fps={preset.fps}"]
        if source_size != (preset.width, preset.height):
            picture.append(f"scale={preset.width}:{preset.height}:flags=lanczos")
        picture += ["setsar=1", *([] if moves else finish)]
        graph = [f"[0:v:0]{','.join(picture)}[{made}]"]
    if moves:
        graph += [*moves, f"[moved]{','.join(finish)}[v]"]

    notches = beep_filters(audio.beeps, seg_in, seg_in + length)
    for n, stream in enumerate(audio.streams):
        chain = [f"aresample={AUDIO_RATE}", "aformat=sample_fmts=fltp:channel_layouts=stereo"]
        if stream == audio.voice:
            chain += notches
        graph.append(f"[0:{stream}]{','.join(chain)}[a{n}]")
    inputs = "".join(f"[a{n}]" for n in range(len(audio.streams)))
    extra, labels = sfx.chains(sounds or [], 1, AUDIO_RATE)
    graph += extra
    inputs += "".join(labels)
    count = len(audio.streams) + len(labels)
    # normalize=0: add the tracks together the way OBS mixes them, not averaged.
    mix = f"amix=inputs={count}:normalize=0:duration=first," if count > 1 else ""
    fade = min(FADE_SEC, length / 4)
    graph.append(f"{inputs}{mix}afade=t=in:d={fade},afade=t=out:st={length - fade:.4f}:d={fade}[a]")

    return [
        *(["-hwaccel", "cuda"] if gpu_decode else []),
        "-ss", f"{seg_in:.3f}", "-i", str(source), *sfx.input_args(sounds or []),
        "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]",
        "-t", f"{length:.4f}",
        *codec, *COLOUR,
        "-c:a", "pcm_f32le", "-ar", str(AUDIO_RATE),
        str(target),
    ]


def loudness_filter(measured_lufs: float, true_peak_db: float, target_lufs: float) -> str:
    """One gain for the whole video, and a limiter for the few peaks it pushes too high.

    FFmpeg's own loudness leveller (loudnorm) can't raise a video whose peaks
    would go over, so it quietly switches to evening out loud and quiet parts
    itself: on the League highlight it lifted quiet stretches by up to 16 dB,
    changing how the stream sounded, and still ended at -16.7 LUFS where
    YouTube plays at -14 (YouTube turns loud videos down, never quiet ones
    up). Instead: one gain, and a limiter that holds down only the peaks
    that would go over, for a moment -- by MAX_LIMITING_DB at most, beyond
    which the video is left quieter rather than squashed: a quiet recording
    stays a little quiet, but never distorts. It works at 4x the sample rate
    so it catches the peaks between samples too, and lets go slowly so it
    doesn't pump.
    """
    gain = target_lufs - measured_lufs
    gain = min(gain, TRUE_PEAK_DB - true_peak_db + MAX_LIMITING_DB)
    limit = 10 ** (TRUE_PEAK_DB / 20)
    return (f"volume={gain:.2f}dB,aresample={AUDIO_RATE * 4},"
            f"alimiter=limit={limit:.4f}:attack=10:release=200:level=0:latency=1,"
            f"aresample={AUDIO_RATE}")


def move_into_place(unfinished: Path, target: Path, notes: list[str],
                    tries: int = REPLACE_TRIES) -> Path:
    """Give the finished video its real name. Where it is now.

    Windows won't replace a video that's open: playing in VLC, or in Review's
    player. On 10 Oct, rendering the same Short a third time to compare its
    effects stopped at the very end because the second was still playing. So
    wait a moment, then keep both: the new one is saved beside it as "(2)".
    """
    for attempt in range(tries):
        try:
            unfinished.replace(target)
            return target
        except PermissionError:
            if attempt + 1 < tries:
                time.sleep(REPLACE_WAIT_SEC)
    n = 2
    while (beside := target.with_name(f"{target.stem} ({n}){target.suffix}")).exists():
        n += 1
    unfinished.replace(beside)
    notes.append(f"{target.name} was open in a video player, so it was kept and this one is "
                 f"saved beside it as {beside.name}.")
    return beside


def _check_space(folder: Path, seconds: float, preset: RenderPreset) -> None:
    video = bits(preset.bitrate) * 1.5 / 8 * seconds
    needed = int(2 * video + WORKING_AUDIO_BYTES_PER_SEC * seconds)  # the pieces, then the video
    free = shutil.disk_usage(folder).free
    if free < needed:
        raise LowDiskSpace(f"This video needs about {needed / 1024**3:,.1f} GB while it renders and "
                           f"only {free / 1024**3:,.1f} GB is free where the output folder is")


def render_plan(
    conn: sqlite3.Connection,
    settings: Settings,
    plan: EditPlan,
    on_progress: Callable[[float], None] | None = None,
    *,
    target: Path | None = None,
    captions: bool | None = None,
    title: str | None = None,
) -> RenderResult:
    """``captions``: burn them in; None = as Settings say for this kind of video.
    ``title``: a title card over the first seconds ("Ep 1 – Part 2")."""
    began = time.monotonic()
    lets_play = plan.recipe == "letsplay"
    short = plan.recipe == "shorts"
    if captions is None:
        captions = (settings.shorts.captions if short else settings.captions.lets_play
                    if lets_play else settings.captions.highlights)
    preset = settings.render.presets[settings.shorts.preset if short else settings.render.preset]
    vertical = vertical_of(settings, plan) if short else None
    target = target or video_path(settings, plan, captions=captions)
    target.parent.mkdir(parents=True, exist_ok=True)
    lengths = [frame_exact(s.length, preset.fps) for s in plan.segments]
    total = sum(lengths)
    _check_space(target.parent, total, preset)

    sources = {}
    for row in conn.execute(
            f"SELECT id, source_file, width, height FROM recordings WHERE id IN "
            f"({','.join('?' * len(plan.recording_ids))})", plan.recording_ids):
        path = Path(row["source_file"])
        if not path.is_file():
            raise MediaFileNotFound(f"Recording #{row['id']}: {path}")
        sources[row["id"]] = (path, (row["width"] or preset.width, row["height"] or preset.height))
    audio = {rid: plan_audio(conn, settings, rid) for rid in plan.recording_ids}
    notes: list[str] = []
    captioned = set(plan.recording_ids) if captions else set()
    story = lets_play or (short and plan.game in settings.lets_play.games)
    if captions and story:
        # A mixed track's transcript has the characters' lines in it too
        # ("How about Petronius?" -- Anca, EP 1), and captions are the
        # creator's words only, never the game's dialogue (spec 7.6).
        for rid in plan.recording_ids:
            if not audio[rid].separate:
                captioned.discard(rid)
                notes.append(f"No captions from recording #{rid}: it has only a mixed sound track, so "
                             "the game's dialogue can't be told apart from your voice. Recordings with "
                             "your mic on its own track (manual 7.3) get captions.")

    # Fastest first; each step down trades speed for working on more PCs.
    attempts = []
    if settings.performance.device == "gpu" and settings.render.encoder in nvenc_encoders():
        attempts = [(settings.render.encoder, True), (settings.render.encoder, False)]
    attempts.append(("libx264", False))

    effects = effects_for_plan(conn, settings, plan)
    if any(effects):
        notes.append(f"Effects: {effects_summary(effects)}.")
    heard: dict[int, list[Path]] = {}   # the tracks each recording's sound is made from

    work = target.with_name(target.stem + " (rendering)")
    work.mkdir(parents=True, exist_ok=True)
    unfinished = target.with_name(target.stem + " (rendering).mp4")
    pieces: list[Path] = []
    words: dict[int, list] = {}
    caption_count = 0
    done = 0.0
    try:
        for index, (segment, length) in enumerate(zip(plan.segments, lengths)):
            source, size = sources[segment.recording_id]
            piece = work / f"{index:03d}.mkv"
            cues = []
            if segment.recording_id in captioned and segment.captions:
                if segment.recording_id not in words:
                    words[segment.recording_id] = load_words(conn, segment.recording_id)
                cues = segment_cues(words[segment.recording_id], segment.src_in, segment.src_in + length)
                caption_count += len(cues)
            card = (Cue(0.0, min(settings.lets_play.title_card_sec, length), title)
                    if title and index == 0 else None)
            subtitles = None
            if short and cues:
                ass = work / f"{index:03d}.ass"
                # Word by word, so each lights up when it's heard: Whisper
                # stretches some words' starts back into the pause before them.
                ass.write_text(short_document(
                    realistic_timing(words[segment.recording_id]), segment.src_in,
                    segment.src_in + length,
                    width=preset.width, height=preset.height, style=settings.captions,
                    zone=settings.shorts.safe_zone()), encoding="utf-8")
                subtitles = ass.name
            elif cues or card:
                subtitles = write_ass(cues, work / f"{index:03d}.ass", width=preset.width,
                                      height=preset.height, style=settings.captions, title=card,
                                      place=settings.captions.position.lets_play if lets_play
                                      else settings.captions.position.highlights).name
            sounds = []
            if any(e.kind == "sfx" for e in effects[index]):
                rid = segment.recording_id
                if rid not in heard:
                    heard[rid] = sfx.tracks(conn, rid, audio[rid].streams)
                sounds = sfx.place(settings, effects[index], segment.src_in,
                                   segment.src_in + length, heard[rid], plan.plan_id)
            while True:
                encoder, gpu_decode = attempts[0]
                args = segment_args(source, segment.src_in, length, audio[segment.recording_id],
                                    preset, size, video_codec(settings, preset, encoder), piece,
                                    gpu_decode=gpu_decode, captions=subtitles, vertical=vertical,
                                    effects=effects[index], sounds=sounds, fx=settings.effects)
                try:
                    run_ffmpeg(args, duration_sec=length, what="rendering part of a video", cwd=work,
                               on_progress=(lambda f, d=done: on_progress(0.85 * (d + f * length) / total))
                               if on_progress else None)
                    break
                except MediaProcessingFailed:
                    if len(attempts) == 1:
                        raise
                    log.warning("Rendering with %s%s failed; trying a slower way", encoder,
                                " and GPU decoding" if gpu_decode else "")
                    attempts.pop(0)
            pieces.append(piece)
            done += length

        listing = work / "pieces.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in pieces), encoding="utf-8")
        joined = ["-f", "concat", "-safe", "0", "-i", str(listing)]
        target_lufs = settings.render.loudness_target_lufs
        stats = measure_loudness(joined, target_lufs=target_lufs, true_peak=TRUE_PEAK_DB)
        if on_progress:
            on_progress(0.9)
        loudness = "anull" if stats is None else loudness_filter(
            float(stats["input_i"]), float(stats["input_tp"]), target_lufs)
        run_ffmpeg([*joined, "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
                    "-af", loudness, "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", str(AUDIO_RATE),
                    "-movflags", "+faststart", str(unfinished)],
                   duration_sec=total, what="finishing a video",
                   on_progress=(lambda f: on_progress(0.9 + 0.1 * f)) if on_progress else None)
        target = move_into_place(unfinished, target, notes)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        unfinished.unlink(missing_ok=True)
    if on_progress:
        on_progress(1.0)
    return RenderResult(target, total, attempts[0][0], time.monotonic() - began, audio,
                        caption_count if captions else None, notes)
