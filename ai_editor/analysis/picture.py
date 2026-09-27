"""What the picture shows, second by second: brightness, motion, and the HUD.

* **Brightness.** Found on the creator's Wardogs streams: a clip that scored
  well on audio was 48 seconds of a black screen while they set up an OBS
  scene. A black second can't be a moment. Black screens are also loading
  screens, which the Let's Play recipe removes.
* **Motion** -- how much the picture changes from one second to the next,
  0 = identical. Tells a menu, the map or the inventory (still) from play.
* **HUD** -- whether the game's on-screen display (health bar, compass, quest
  list) is showing. It disappears in cutscenes, which the Let's Play recipe
  must never cut. On the creator's Dawnwalker EP 1, gameplay scored 0.33-0.72
  and every cutscene 0.02-0.05, dark night-time play included. Nothing about
  a particular game is built in: the HUD is learned from each recording as
  the sharp edges that stay in the same place most of the time, while the
  world's edges move. Edges that never change at all (an OBS overlay) don't
  count, because they're there in cutscenes too.

One pass over the preview copy, decoding only its keyframes -- one per
second, which is exactly the rate needed. EP 1 (2 h 6 min): 21 seconds, where
decoding every frame took over 12 minutes.
"""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..ffmpeg import run_ffmpeg

WIDTH, HEIGHT = 480, 270   # enough to see a health bar; small enough to be quick
# Motion is measured on a small copy, where noise averages out (a loading
# screen reads 0.0, not the flicker of compression).
BLOCK = 8                  # 480 x 270 -> 60 x 33 blocks
EDGE_LEVEL = 24            # a brightness step this sharp is an edge
HUD_RATE = (0.30, 0.92)    # an edge here this often (but not always) is HUD
MIN_HUD_PIXELS = 50        # fewer than this: no HUD found, so say nothing about it
CHUNK = 400                # frames handled at once, to keep memory small
VIDEO_RANGE = 219 / 255     # full-range grey -> video-range brightness steps


def _edges(frames: np.ndarray) -> np.ndarray:
    x = frames.astype(np.int16)
    across = np.zeros_like(x)
    across[..., 1:] = np.abs(np.diff(x, axis=-1))
    down = np.zeros_like(x)
    down[..., 1:, :] = np.abs(np.diff(x, axis=-2))
    return np.maximum(across, down) >= EDGE_LEVEL


def _small(frames: np.ndarray) -> np.ndarray:
    h = (HEIGHT // BLOCK) * BLOCK
    x = frames[:, :h, :].astype(np.float32)
    return x.reshape(len(x), h // BLOCK, BLOCK, WIDTH // BLOCK, BLOCK).mean(axis=(2, 4))


def picture_signals(frames: np.ndarray) -> dict[str, list[float]]:
    """Brightness, motion and HUD from one grey frame per second."""
    n = len(frames)
    brightness = np.zeros(n, dtype=np.float32)
    motion = np.zeros(n, dtype=np.float32)
    rate = np.zeros((HEIGHT, WIDTH), dtype=np.float64)
    sampled = 0
    previous = None
    for i in range(0, n, CHUNK):
        chunk = np.asarray(frames[i:i + CHUNK])
        brightness[i:i + len(chunk)] = chunk.reshape(len(chunk), -1).mean(axis=1)
        small = _small(chunk)
        if previous is not None:
            small_with_previous = np.concatenate([previous[None], small])
        else:
            small_with_previous = np.concatenate([small[:1], small])
        motion[i:i + len(chunk)] = np.abs(np.diff(small_with_previous, axis=0)).mean(axis=(1, 2))
        previous = small[-1]
        edges = _edges(chunk[::3])  # every third second is plenty to learn from
        rate += edges.sum(axis=0)
        sampled += len(edges)
    rate /= max(sampled, 1)
    hud_mask = (rate >= HUD_RATE[0]) & (rate <= HUD_RATE[1])

    # FFmpeg's grey is full range (black 0, white 255); every threshold in
    # AI-Editor was set on video range (black 16, white 235), which is what
    # this step measured before. Converted back, so a loading screen is 17.
    result = {"brightness": np.round(brightness * VIDEO_RANGE + 16, 1).tolist(),
              "motion": np.round(motion * VIDEO_RANGE, 2).tolist()}
    if hud_mask.sum() >= MIN_HUD_PIXELS:
        hud = np.zeros(n, dtype=np.float32)
        for i in range(0, n, CHUNK):
            hud[i:i + CHUNK] = _edges(np.asarray(frames[i:i + CHUNK]))[:, hud_mask].mean(axis=1)
        result["hud"] = np.round(hud, 3).tolist()
    return result


def measure_picture(
    video: Path,
    work_dir: Path,
    duration_sec: float,
    on_progress: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Each second's brightness (0 black - 255 white), motion (0 = still) and HUD (0-1)."""
    work_dir.mkdir(parents=True, exist_ok=True)
    raw = work_dir / "frames.gray"
    try:
        run_ffmpeg(
            # Keyframes only (the preview copy has one a second); fps=1 keeps
            # exactly one frame per second even if a copy has fewer or more.
            ["-skip_frame", "nokey", "-i", str(video), "-an",
             "-vf", f"fps=1,scale={WIDTH}:{HEIGHT},format=gray",
             "-f", "rawvideo", str(raw)],
            duration_sec=duration_sec,
            on_progress=(lambda f: on_progress(f * 0.8)) if on_progress else None,
            what="measuring the picture",
        )
        frames = np.memmap(raw, dtype=np.uint8, mode="r").reshape(-1, HEIGHT, WIDTH)
        result = picture_signals(frames)
        del frames
        gc.collect()  # let go of the file, so Windows allows deleting it
    finally:
        raw.unlink(missing_ok=True)
    if on_progress:
        on_progress(1.0)
    return result
