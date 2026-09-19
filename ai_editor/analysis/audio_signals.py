"""Per-second audio signals: loudness, silence, energy spikes, speech coverage.

Spec section 7.3 stores every signal once per second. These functions are pure
numpy so they can be tested exactly, without any AI model involved.

The spec suggests librosa for RMS; a plain numpy RMS over one-second blocks is
the same calculation, streams a two-hour file without loading it all, and
avoids pulling librosa's heavier dependencies into this step.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import soundfile as sf

FLOOR_DB = -100.0  # What digital silence is recorded as, instead of -infinity.


def per_second_db(
    path: str | Path,
    on_progress: Callable[[float], None] | None = None,
) -> np.ndarray:
    """RMS loudness of each second of a WAV file, in dBFS.

    0 dB is the loudest a digital file can be; normal speech sits roughly
    between -30 and -15. The final partial second is measured on what exists.
    """
    info = sf.info(str(path))
    rate = info.samplerate
    total = max(1, math.ceil(info.frames / rate))
    values: list[float] = []
    for block in sf.blocks(str(path), blocksize=rate, dtype="float32", always_2d=True):
        mono = block.mean(axis=1)
        rms = float(np.sqrt(np.mean(mono * mono))) if mono.size else 0.0
        values.append(20 * math.log10(rms) if rms > 1e-5 else FLOOR_DB)
        if on_progress and len(values) % 60 == 0:
            on_progress(min(1.0, len(values) / total))
    if on_progress:
        on_progress(1.0)
    return np.array(values, dtype=np.float32)


def robust_zscore(
    values: np.ndarray,
    ignore_below: float = -80.0,
    baseline_mask: np.ndarray | None = None,
    min_baseline_seconds: int = 30,
) -> np.ndarray:
    """How unusual each second's loudness is for *this* recording.

    Spec section 7.3: energy spikes are "z-scored against the recording's
    baseline". Median and MAD are used instead of mean and standard deviation
    so a handful of very loud moments can't drag the baseline up and hide
    themselves. Silent seconds are left out of the baseline, then scored.

    A result of 3 means "much louder than usual for this recording", which is
    what makes it comparable between a quiet Let's Play and a loud stream.

    ``baseline_mask`` picks which seconds define "usual" -- in practice, the
    seconds where someone is talking. Measured against *all* seconds, the
    quiet gaps between sentences widen the spread so much that nothing stands
    out: on the creator's mic-track test the strongest second scored 1.8,
    against talking level 2.3; on EP 1, 1.5 against 2.5. With too few talking
    seconds to judge (under 30), every non-silent second is used instead.
    """
    usable = values[values > ignore_below]
    if baseline_mask is not None:
        talking = values[(baseline_mask[: len(values)] > 0) & (values > ignore_below)]
        if talking.size >= min_baseline_seconds:
            usable = talking
    if usable.size < 2:
        return np.zeros_like(values)
    median = float(np.median(usable))
    mad = float(np.median(np.abs(usable - median))) * 1.4826
    if mad < 1e-6:
        return np.zeros_like(values)
    return np.clip((values - median) / mad, -10.0, 10.0).astype(np.float32)


def silence_mask(*loudness_tracks: np.ndarray, threshold_db: float) -> np.ndarray:
    """1 where every given track is quieter than the threshold, else 0.

    With separate tracks, dead air means neither the creator nor the game is
    making sound; one loud track is enough to make a second not silent.
    """
    length = min(len(track) for track in loudness_tracks)
    quiet = np.ones(length, dtype=bool)
    for track in loudness_tracks:
        quiet &= track[:length] < threshold_db
    return quiet.astype(np.float32)


def speech_coverage(words: Iterable[tuple[float, float]], seconds: int) -> np.ndarray:
    """Fraction of each second (0-1) covered by transcribed words.

    This is the "is the creator talking" signal. On a mixed track, loudness
    can't tell speech from game music, but a word timestamp can.
    """
    coverage = np.zeros(seconds, dtype=np.float32)
    for start, end in words:
        start, end = max(0.0, start), min(float(seconds), end)
        second = int(start)
        while second < end and second < seconds:
            overlap = min(end, second + 1) - max(start, second)
            if overlap > 0:
                coverage[second] += overlap
            second += 1
    return np.clip(coverage, 0.0, 1.0)


def window_starts(seconds: int, window: float) -> np.ndarray:
    """Start times (whole seconds) of overlapping windows, one second apart."""
    last = max(0, math.ceil(seconds - window))
    return np.arange(0, last + 1, dtype=np.int64)


def spread_to_seconds(
    window_scores: np.ndarray, starts: np.ndarray, window: float, seconds: int
) -> np.ndarray:
    """Turn scores for overlapping windows into one score per second.

    Sound recognition hears a few seconds at a time. Each second takes the
    highest score of any window that covers it, so a one-second laugh isn't
    diluted by the quiet either side of it.
    """
    if window_scores.ndim == 1:
        window_scores = window_scores[:, None]
    result = np.zeros((seconds, window_scores.shape[1]), dtype=np.float32)
    span = max(1, math.ceil(window))
    for index, start in enumerate(starts):
        end = min(seconds, int(start) + span)
        if end > start:
            np.maximum(result[start:end], window_scores[index], out=result[start:end])
    return result


def top_moments(
    values: np.ndarray, *, count: int, min_gap: int, threshold: float
) -> list[tuple[int, float]]:
    """The strongest seconds, at least ``min_gap`` seconds apart.

    Without the gap, one long scream would fill the whole list with
    neighbouring seconds of the same moment.
    """
    order = np.argsort(values)[::-1]
    chosen: list[tuple[int, float]] = []
    for second in order:
        value = float(values[second])
        if value < threshold:
            break
        if all(abs(int(second) - taken) >= min_gap for taken, _ in chosen):
            chosen.append((int(second), value))
            if len(chosen) == count:
                break
    return sorted(chosen)
