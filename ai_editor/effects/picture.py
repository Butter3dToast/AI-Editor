"""A segment's picture effects joined up: flashes, then shakes."""

from __future__ import annotations

from ..config import Effects
from . import Effect, flash, shake


def graph(effects: list[Effect], seg_in: float, height: int, fx: Effects,
          source: str, out: str) -> list[str]:
    """Graph pieces from ``[source]`` to ``[out]``; empty if the segment has none."""
    bright = flash.filter_text(effects, seg_in, fx.flash_strength)
    shaking = any(e.kind == "shake" for e in effects)
    if not bright and not shaking:
        return []
    pieces = []
    if bright:
        flashed = f"{out}_flashed" if shaking else out
        pieces.append(f"[{source}]{bright}[{flashed}]")
        source = flashed
    if shaking:
        pieces += shake.graph(effects, seg_in, height, fx.shake_strength, source, out)
    return pieces
