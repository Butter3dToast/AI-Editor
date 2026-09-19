"""Voice separation: un-mixing a single audio track (spec section 7.3).

A Twitch VOD -- or any recording made without separate OBS tracks -- has the
creator, the game and any voice chat mixed into one track. Demucs splits it
into "vocals" (anyone speaking) and everything else (music, combat, ambience).

It cannot tell voices apart: the creator, in-game characters and teammates all
land in "vocals". Telling the creator from other voices is speaker
identification, in Phase 2.

The separated audio is only ever used for analysis. Finished videos always
use the original sound.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from ..config import Settings
from ..errors import OutOfGraphicsMemory
from ..ffmpeg import run_ffmpeg
from ..logging_setup import get_logger
from ..models import is_out_of_memory, separation_model

log = get_logger(__name__)

SAMPLE_RATE = 44_100          # What htdemucs was trained on.
BLOCK_SECONDS = 300           # Processed five minutes at a time...
CONTEXT_SECONDS = 5           # ...with this much extra either side, trimmed off,
                              # so there is no seam where two blocks meet.

VOCALS_FILE = "vocals.wav"
BACKING_FILE = "backing.wav"


def block_ranges(total_frames: int, rate: int = SAMPLE_RATE) -> list[tuple[int, int, int, int]]:
    """(read_start, read_end, keep_start, keep_end) for each block, in frames.

    Each block is read with context on both sides; only the middle part is
    kept. The kept parts tile the whole recording exactly, with no overlap.
    """
    block, context = BLOCK_SECONDS * rate, CONTEXT_SECONDS * rate
    ranges = []
    for keep_start in range(0, total_frames, block):
        keep_end = min(total_frames, keep_start + block)
        ranges.append((max(0, keep_start - context), min(total_frames, keep_end + context),
                       keep_start, keep_end))
    return ranges


def separate_voices(
    settings: Settings,
    mixed_wav: Path,
    out_dir: Path,
    duration_sec: float,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Write ``vocals.wav`` and ``backing.wav`` (both 44.1 kHz stereo) to out_dir."""
    import torch
    from demucs.apply import apply_model

    out_dir.mkdir(parents=True, exist_ok=True)
    mix = out_dir / "mix_44k.partial.wav"
    vocals_partial = out_dir / "vocals.partial.wav"
    backing_partial = out_dir / "backing.partial.wav"

    def report(fraction: float) -> None:
        if on_progress:
            on_progress(min(1.0, fraction))

    try:
        # Resampled to what the model expects. First 5% of the progress bar.
        run_ffmpeg(
            ["-i", str(mixed_wav), "-ac", "2", "-ar", str(SAMPLE_RATE),
             "-c:a", "pcm_s16le", "-rf64", "auto", str(mix)],
            duration_sec=duration_sec,
            on_progress=lambda f: report(0.05 * f),
            what="preparing audio for voice separation",
        )

        with separation_model(settings) as (model, device), \
                sf.SoundFile(str(mix)) as source, \
                sf.SoundFile(str(vocals_partial), "w", SAMPLE_RATE, 2, "PCM_16", format="RF64") as vocals_out, \
                sf.SoundFile(str(backing_partial), "w", SAMPLE_RATE, 2, "PCM_16", format="RF64") as backing_out:
            vocals_index = list(model.sources).index("vocals")  # type: ignore[attr-defined]
            ranges = block_ranges(source.frames)

            for number, (read_start, read_end, keep_start, keep_end) in enumerate(ranges):
                source.seek(read_start)
                chunk = source.read(read_end - read_start, dtype="float32", always_2d=True)
                vocals, backing = _separate_block(model, device, chunk, vocals_index, apply_model, torch)
                keep = slice(keep_start - read_start, keep_end - read_start)
                vocals_out.write(vocals[keep])
                backing_out.write(backing[keep])
                report(0.05 + 0.95 * (number + 1) / len(ranges))

        vocals_partial.replace(out_dir / VOCALS_FILE)
        backing_partial.replace(out_dir / BACKING_FILE)
    except BaseException:
        vocals_partial.unlink(missing_ok=True)
        backing_partial.unlink(missing_ok=True)
        raise
    finally:
        mix.unlink(missing_ok=True)

    report(1.0)
    log.info("Separated voices from %s", mixed_wav.name)
    return out_dir


def _separate_block(model, device, chunk: np.ndarray, vocals_index: int, apply_model, torch):
    """Separate one block. Returns (vocals, everything else), each (frames, 2)."""
    frames = chunk.shape[0]
    mono = chunk.mean(axis=1)
    mean, std = float(mono.mean()), float(mono.std())
    if std < 1e-6 or not math.isfinite(std):
        # Digital silence: nothing to separate, and the model would divide by zero.
        silent = np.zeros((frames, 2), dtype=np.float32)
        return silent, silent

    # Normalised as the Demucs command-line tool does, then restored.
    tensor = torch.from_numpy(((chunk - mean) / std).T.copy())[None]
    try:
        with torch.inference_mode():
            sources = apply_model(model, tensor, device=device, split=True,
                                  overlap=0.25, progress=False)[0]
    except Exception as exc:  # noqa: BLE001
        if is_out_of_memory(exc):
            raise OutOfGraphicsMemory() from exc
        raise
    sources = sources * std + mean
    vocals = sources[vocals_index]
    backing = sources.sum(dim=0) - vocals
    return (np.clip(vocals.T.cpu().numpy(), -1, 1).astype(np.float32),
            np.clip(backing.T.cpu().numpy(), -1, 1).astype(np.float32))
