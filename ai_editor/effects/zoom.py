"""A punch-in zoom: the picture pushes in towards the middle, holds, and eases back out.

Phase 2C-2a. On the creator's reactions (their choice, 10 Oct): when they
shout or laugh at a moment they marked, or at a big League moment, while the
shake stays on the action itself (placement.py).

Like the shake, a copy of the picture is laid over itself only while a zoom
is on: the copy is scaled up, frame by frame, and centred over the original,
which it covers completely. Every other frame passes through untouched, and
the picture keeps its size, so nothing else needs to know about the zoom.
"""

from __future__ import annotations

from . import Effect
from .flash import enable

IN_SEC = 0.15     # pushing in: quick, so it lands with the reaction
OUT_SEC = 0.35    # easing back out: slower, so it settles


def _eased(x: str) -> str:
    """Smoothstep of ``x`` clipped to 0-1: starts and stops gently."""
    c = f"clip({x},0,1)"
    return f"({c})*({c})*(3-2*({c}))"


def amount(effects: list[Effect], seg_in: float) -> str:
    """How far in it is at time t, 0 (not zoomed) to 1 (all the way), for every zoom."""
    parts = []
    for e in effects:
        a = e.within(seg_in)
        b = a + e.length
        parts.append(f"between(t,{a:.3f},{b:.3f})*{_eased(f'(t-{a:.3f})/{IN_SEC}')}"
                     f"*{_eased(f'({b:.3f}-t)/{OUT_SEC}')}")
    return "+".join(parts)


def graph(effects: list[Effect], seg_in: float, strength: float,
          source: str, out: str) -> list[str] | None:
    """Filter graph pieces from ``[source]`` to ``[out]``, or None if there's no zoom.
    ``strength``: how much bigger at the most (0.2 is 1.2 times)."""
    zooms = [e for e in effects if e.kind == "zoom"]
    if not zooms:
        return None
    scale = f"(1+{strength:.3f}*({amount(zooms, seg_in)}))"
    on = enable(zooms, seg_in)
    return [
        # Converted first: split pictures decoded on the graphics card came out
        # green otherwise (render/vertical.py, SPLIT_FORMAT).
        f"[{source}]format=yuv420p,split=2[{out}_base][{out}_big]",
        f"[{out}_big]scale=w='trunc(iw*{scale}/2)*2':h='trunc(ih*{scale}/2)*2':"
        f"eval=frame[{out}_scaled]",
        f"[{out}_base][{out}_scaled]overlay=x='(main_w-overlay_w)/2':"
        f"y='(main_h-overlay_h)/2':eval=frame:enable='{on}'[{out}]",
    ]
