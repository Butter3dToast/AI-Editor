"""A screen shake: the picture jolts about for under half a second, settling as it goes.

The picture is laid over itself, shifted, only while a shake is on: every
other frame passes through untouched, and nothing is zoomed. The few pixels
uncovered at the edge show the unshifted picture underneath, too briefly to
see. (Selecting only the shaking frames instead would make FFmpeg hold every
frame in between in memory, waiting for the next shake.)
"""

from __future__ import annotations

from . import Effect
from .flash import enable

# Two different speeds, so it wobbles rather than sliding back and forth.
X_HZ = 13.0
Y_HZ = 11.0


def offset(effects: list[Effect], seg_in: float, hz: float, phase: float) -> str:
    """How far it's moved at time t, as a share of the full swing (-1 to 1), fading to 0."""
    return "+".join(
        f"between(t,{e.within(seg_in):.3f},{e.within(seg_in) + e.length:.3f})"
        f"*(1-(t-{e.within(seg_in):.3f})/{e.length:.3f})*sin(2*PI*{hz:g}*t+{phase:g})"
        for e in effects)


def graph(effects: list[Effect], seg_in: float, height: int, strength: float,
          source: str, out: str) -> list[str] | None:
    """Filter graph pieces from ``[source]`` to ``[out]``, or None if there's no shake."""
    shakes = [e for e in effects if e.kind == "shake"]
    if not shakes:
        return None
    swing = max(2, round(strength * height))
    on = enable(shakes, seg_in)
    x = f"{swing}*({offset(shakes, seg_in, X_HZ, 0.0)})"
    y = f"{swing * 0.6:g}*({offset(shakes, seg_in, Y_HZ, 1.0)})"
    return [
        # Converted first: split pictures decoded on the graphics card came out
        # green otherwise (render/vertical.py, SPLIT_FORMAT).
        f"[{source}]format=yuv420p,split=2[{out}_base][{out}_moved]",
        f"[{out}_base][{out}_moved]overlay=x='{x}':y='{y}':eval=frame:enable='{on}'[{out}]",
    ]
