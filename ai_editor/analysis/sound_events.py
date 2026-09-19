"""Hearing laughter, shouting, screaming, gunfire and explosions (spec 7.3).

The PANNs model recognises 527 kinds of sound. Several of its classes mean the
same thing for editing purposes ("Giggle", "Chuckle, chortle", "Belly laugh"
are all laughter), so they are combined into a handful of groups by taking the
strongest member.

Which track is listened to matters (spec section 7.3): reactions come from the
creator's voice, fights come from the game. With separate OBS tracks, each
group listens to the right one; with a single mixed track, everything listens
to that.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from ..config import Settings
from ..errors import OutOfGraphicsMemory
from ..logging_setup import get_logger
from ..models import audioset_labels, is_out_of_memory, sound_model
from .audio_signals import spread_to_seconds, window_starts
from .panns_cnn14 import SAMPLE_RATE

log = get_logger(__name__)

SOUND_GROUPS: dict[str, tuple[str, ...]] = {
    "laughter": ("Laughter", "Baby laughter", "Giggle", "Snicker", "Belly laugh",
                 "Chuckle, chortle"),
    "shout": ("Shout", "Yell", "Battle cry", "Bellow", "Children shouting"),
    "scream": ("Screaming",),
    "gunfire": ("Gunshot, gunfire", "Machine gun", "Fusillade", "Artillery fire", "Cap gun"),
    "explosion": ("Explosion", "Boom"),
    "music": ("Music",),
}

VOICE_GROUPS = ("laughter", "shout", "scream")
GAME_GROUPS = ("gunfire", "explosion", "music")

_BATCH = 32


def group_columns(labels: list[str]) -> dict[str, list[int]]:
    """Map each group to the model output columns it's made of."""
    position = {label: i for i, label in enumerate(labels)}
    columns: dict[str, list[int]] = {}
    for group, names in SOUND_GROUPS.items():
        found = [position[name] for name in names if name in position]
        missing = [name for name in names if name not in position]
        if missing:
            log.warning("Sound labels not found for %s: %s", group, missing)
        if found:
            columns[group] = found
    return columns


def _score_file(
    model: object,
    device: str,
    path: Path,
    columns: dict[str, list[int]],
    groups: tuple[str, ...],
    seconds: int,
    window: float,
    on_progress: Callable[[float], None] | None,
) -> dict[str, np.ndarray]:
    import torch

    audio, rate = sf.read(str(path), dtype="float32", always_2d=False)
    if rate != SAMPLE_RATE:
        raise ValueError(f"{path.name} is {rate} Hz; the sound model needs {SAMPLE_RATE}")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    window_samples = int(window * SAMPLE_RATE)
    starts = window_starts(seconds, window)
    needed = int(starts[-1]) * SAMPLE_RATE + window_samples
    if audio.size < needed:
        audio = np.pad(audio, (0, needed - audio.size))

    wanted = [g for g in groups if g in columns]
    scores = np.zeros((len(starts), len(wanted)), dtype=np.float32)

    with torch.inference_mode():
        for first in range(0, len(starts), _BATCH):
            batch_starts = starts[first:first + _BATCH]
            batch = np.stack([
                audio[s * SAMPLE_RATE: s * SAMPLE_RATE + window_samples] for s in batch_starts
            ])
            try:
                probs = model(torch.from_numpy(batch).to(device)).cpu().numpy()  # type: ignore[operator]
            except Exception as exc:  # noqa: BLE001
                if is_out_of_memory(exc):
                    raise OutOfGraphicsMemory() from exc
                raise
            for j, group in enumerate(wanted):
                scores[first:first + len(batch_starts), j] = probs[:, columns[group]].max(axis=1)
            if on_progress:
                on_progress(min(1.0, (first + len(batch_starts)) / len(starts)))

    per_second = spread_to_seconds(scores, starts, window, seconds)
    return {group: per_second[:, j] for j, group in enumerate(wanted)}


def detect_sound_events(
    settings: Settings,
    voice_32k: Path,
    game_32k: Path | None,
    seconds: int,
    on_progress: Callable[[float], None] | None = None,
) -> dict[str, list[float]]:
    """Per-second probability (0-1) of each sound group.

    ``game_32k`` is None when there is no separate game track, in which case
    every group listens to the one (mixed) track.
    """
    columns = group_columns(audioset_labels(settings))
    window = settings.analysis.event_window_sec
    jobs = (
        [(voice_32k, VOICE_GROUPS), (game_32k, GAME_GROUPS)]
        if game_32k is not None
        else [(voice_32k, VOICE_GROUPS + GAME_GROUPS)]
    )

    results: dict[str, np.ndarray] = {}
    with sound_model(settings) as (model, device):
        for index, (path, groups) in enumerate(jobs):
            def scaled(fraction: float, index: int = index) -> None:
                if on_progress:
                    on_progress((index + fraction) / len(jobs))

            results.update(
                _score_file(model, device, path, columns, groups, seconds, window, scaled)
            )

    if on_progress:
        on_progress(1.0)
    return {group: [round(float(v), 4) for v in values] for group, values in results.items()}
