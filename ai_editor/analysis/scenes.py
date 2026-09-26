"""Scene changes: where the picture cuts to something else (spec section 7.3).

Used for clip edges, so a clip never runs on into a menu, a loading screen or
a scoreboard, and never opens on one.

Why this detector, measured on 10 minutes of the creator's Wardogs stream and
checked frame by frame:

* FFmpeg's own scene filter: 5 cuts, all real, but it missed gameplay ->
  vendor menu and "Stream starting" -> black. Missing the menus is the one
  failure that matters here.
* PySceneDetect's ContentDetector: 26 cuts. Caught the menus, but fast camera
  turns in a firefight also counted as cuts.
* PySceneDetect's AdaptiveDetector at 5.0 (used): 9 cuts, every one real --
  menus, scoreboard, loading, jumping out of the helicopter. It judges each
  frame against the frames around it, so a quick turn doesn't look like a cut.
  It missed only a slow fade to black before the game began.

Reading every other frame halved the time but lost the gameplay -> vendor
menu cut, so every frame is read: about 2.3 minutes per 2 hours of preview.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..logging_setup import get_logger

log = get_logger(__name__)

# Progress is reported after each chunk of this many seconds.
CHUNK_SECONDS = 60.0


def detect_scene_cuts(
    video: Path,
    duration_sec: float,
    *,
    threshold: float = 5.0,
    on_progress: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Times (seconds) where the picture cuts, read from the preview copy."""
    from scenedetect import AdaptiveDetector, SceneManager, open_video

    stream = open_video(str(video))
    manager = SceneManager()
    manager.auto_downscale = True
    manager.add_detector(AdaptiveDetector(adaptive_threshold=threshold))

    # In chunks so progress can be shown; the detector carries on where it
    # stopped each time, so this finds exactly what one pass would.
    position = 0.0
    total = max(duration_sec, 1.0)
    while position < total:
        position = min(total, position + CHUNK_SECONDS)
        manager.detect_scenes(stream, end_time=position)
        if on_progress:
            on_progress(position / total)

    cuts = [round(scene[0].seconds, 3) for scene in manager.get_scene_list()][1:]
    log.info("Found %d scene changes in %s", len(cuts), video.name)
    return {"detector": "adaptive", "threshold": threshold, "cuts": cuts}
