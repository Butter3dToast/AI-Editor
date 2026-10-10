"""A flash: the picture brightens at once, then fades back over a third of a second.

One FFmpeg ``eq`` filter for all of a segment's flashes, switched on only
while one is happening, so every other frame passes through untouched.
"""

from __future__ import annotations

from . import Effect


def _when(e: Effect, seg_in: float) -> tuple[float, float]:
    start = e.within(seg_in)
    return start, start + e.length


def enable(effects: list[Effect], seg_in: float) -> str:
    """'between(t,a,b)+...': true while any of them is on (FFmpeg's time, t)."""
    return "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in (_when(e, seg_in) for e in effects))


def filter_text(effects: list[Effect], seg_in: float, strength: float) -> str | None:
    """The filter, or None if this segment has no flash. ``strength``: 1 is white."""
    flashes = [e for e in effects if e.kind == "flash"]
    if not flashes:
        return None
    # Full strength at the start, fading in a straight line to nothing.
    level = "+".join(f"between(t,{a:.3f},{b:.3f})*(1-(t-{a:.3f})/{b - a:.3f})"
                     for a, b in (_when(e, seg_in) for e in flashes))
    return (f"eq=brightness='{strength:.3f}*({level})':eval=frame:"
            f"enable='{enable(flashes, seg_in)}'")
