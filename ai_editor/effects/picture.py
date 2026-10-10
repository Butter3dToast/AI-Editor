"""A segment's picture effects joined up: flashes, then zooms, then shakes."""

from __future__ import annotations

from ..config import Effects
from . import Effect, flash, shake, zoom


def graph(effects: list[Effect], seg_in: float, height: int, fx: Effects,
          source: str, out: str) -> list[str]:
    """Graph pieces from ``[source]`` to ``[out]``; empty if the segment has none."""
    bright = flash.filter_text(effects, seg_in, fx.flash_strength)
    shaking = any(e.kind == "shake" for e in effects)
    zooming = any(e.kind == "zoom" for e in effects)
    if not bright and not shaking and not zooming:
        return []
    pieces = []
    if bright:
        flashed = f"{out}_flashed" if shaking or zooming else out
        pieces.append(f"[{source}]{bright}[{flashed}]")
        source = flashed
    if zooming:
        zoomed = f"{out}_zoomed" if shaking else out
        pieces += zoom.graph(effects, seg_in, fx.zoom_strength, source, zoomed)
        source = zoomed
    if shaking:
        pieces += shake.graph(effects, seg_in, height, fx.shake_strength, source, out)
    return pieces
