"""The tall 9:16 picture of a Short, from a 16:9 recording (spec 7.6 Recipe C, 7.8 Layout).

The creator has no facecam yet (2026-10-04), so the game fills the frame,
in one of two ways chosen per game and switchable per Short:

    crop          fit                facecam_top (once a facecam is marked)
  ┌───────┐    ┌───────┐             ┌───────┐
  │       │    │ ░blur░│             │ face  │  the facecam, zoomed to the width
  │ GAME, │    │┌─────┐│             ├───────┤
  │ centre│    ││GAME ││             │ GAME, │  the game's centre below it
  │ zoomed│    │└─────┘│             │ centre│
  │       │    │ ░blur░│             │       │
  └───────┘    └───────┘             └───────┘

crop keeps the middle of the screen, where League's champion and a
shooter's crosshair are; fit keeps everything, smaller, over a blurred,
darkened copy of itself. Each is a piece of FFmpeg filter graph, from the
recording's picture ([0:v:0]) to the finished one ([v]).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Box, RenderPreset

# The blurred background is made small, blurred, then scaled up: the same
# look as blurring at full size, for a fraction of the work.
BLUR_SIZE = (270, 480)
BLUR_RADIUS = 10
BLUR_DARKEN = -0.05
# Pictures decoded on the graphics card are converted before being split in two:
# without it the blurred copy came out green on the right (FFmpeg, -hwaccel cuda).
SPLIT_FORMAT = "format=yuv420p"


@dataclass
class Vertical:
    layout: str = "crop"          # crop | fit | facecam_top
    centre: float = 0.5           # where the crop sits, left to right
    facecam: Box | None = None
    facecam_share: float = 0.33   # of the frame's height
    fill: float = 1.0             # crop: how much of the height the game fills


def even(n: float) -> int:
    """Video sizes must be even numbers, and at least 2."""
    return max(2, int(round(n / 2)) * 2)


def even_at(n: float) -> int:
    """A position, on an even pixel (the edge itself, 0, included)."""
    return max(0, int(round(n / 2)) * 2)


def crop_window(size: tuple[int, int], aspect: float, centre: float) -> tuple[int, int, int, int]:
    """The widest stretch of the picture with this width:height, centred on
    ``centre`` (0-1, left to right) but never past an edge. (w, h, x, y)."""
    width, height = size
    w = min(width, even(height * aspect))
    h = height if w < width else min(height, even(width / aspect))
    x = int(round(min(max(centre * width - w / 2, 0), width - w)))
    return w, h, x, (height - h) // 2


def _blurred(source: str, W: int, H: int) -> str:
    """The background: the picture filling the frame, blurred and a little darker."""
    bw, bh = BLUR_SIZE
    return (f"[{source}]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
            f"boxblur={BLUR_RADIUS}:2,scale={W}:{H},eq=brightness={BLUR_DARKEN}[bg]")


def picture_graph(vertical: Vertical, size: tuple[int, int], preset: RenderPreset, *,
                  finish: list[str], out: str = "v") -> str:
    """Filter graph text from [0:v:0] to [``out``]. ``finish``: filters for the tall
    picture once it's made (captions, colour format)."""
    W, H = preset.width, preset.height
    start = f"[0:v:0]fps={preset.fps}"
    end = ",".join(["setsar=1", *finish])
    if vertical.layout == "fit":
        return ";".join([
            f"{start},{SPLIT_FORMAT},split=2[bgsrc][fgsrc]",
            _blurred("bgsrc", W, H),
            f"[fgsrc]scale={W}:-2:flags=lanczos[fg]",
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{end}[{out}]",
        ])
    if vertical.layout == "facecam_top" and vertical.facecam is not None:
        cam_h = even(H * vertical.facecam_share)
        game_h = H - cam_h
        box = vertical.facecam
        fx, fy = even_at(box.x * size[0]), even_at(box.y * size[1])
        fw, fh = even(box.w * size[0]), even(box.h * size[1])
        gw, gh, gx, gy = crop_window(size, W / game_h, vertical.centre)
        return ";".join([
            f"{start},{SPLIT_FORMAT},split=2[camsrc][gamesrc]",
            f"[camsrc]crop={fw}:{fh}:{fx}:{fy},scale={W}:{cam_h}:force_original_aspect_ratio="
            f"increase:flags=lanczos,crop={W}:{cam_h}[cam]",
            f"[gamesrc]crop={gw}:{gh}:{gx}:{gy},scale={W}:{game_h}:flags=lanczos[game]",
            f"[cam][game]vstack=inputs=2,{end}[{out}]",
        ])
    if vertical.fill < 1.0:
        # Zoomed out a little: a wider slice of the game, a band of blur above and below.
        game_h = even(H * vertical.fill)
        w, h, x, y = crop_window(size, W / game_h, vertical.centre)
        return ";".join([
            f"{start},{SPLIT_FORMAT},split=2[bgsrc][fgsrc]",
            _blurred("bgsrc", W, H),
            f"[fgsrc]crop={w}:{h}:{x}:{y},scale={W}:{game_h}:flags=lanczos[fg]",
            f"[bg][fg]overlay=0:(H-h)/2,{end}[{out}]",
        ])
    w, h, x, y = crop_window(size, W / H, vertical.centre)
    return f"{start},crop={w}:{h}:{x}:{y},scale={W}:{H}:flags=lanczos,{end}[{out}]"
