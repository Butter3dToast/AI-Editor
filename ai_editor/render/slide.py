"""Sliding from one clip to the next (spec 7.8, Transitions): the creator's option.

The creator's pick of three samples (2026-10-10), "like a sliding door":
while the old clip is ending, the new one slides in over it from the right,
easing in and settling, over SLIDE_SEC. Hard cuts stay the default. The
sound crossfades over the same moment. (A whoosh on the cut came first; the
creator didn't like the sound.)

Both clips play at once while it slides, so each slide makes the video
SLIDE_SEC shorter: the last SLIDE_SEC of one clip and the first of the next
become the slide. A video is rendered a piece at a time, so a clip with a
slide becomes up to three pieces -- its middle, and its ends, which are
rendered on their own and then laid over each other (compose_args).
Everything carries on across those joins: effects, sound effects,
captions and music are worked out for the whole clip and each piece gets
its stretch of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..recipes.plan import EditPlan

SLIDE_SEC = 0.8
MIN_MIDDLE_SEC = 1.0      # a clip too short to keep this much between its slides cuts instead
CHOICES = [("Hard cut", "cut"), ("Slide", "slide")]


def between(settings: Settings, plan: EditPlan) -> str:
    """This video's choice, else the Settings'. Highlights only: a Short is one
    clip, and a Let's Play's cuts are meant not to be noticed."""
    if plan.recipe != "highlights":
        return "cut"
    chosen = (plan.source or {}).get("between") or settings.effects.between_clips
    return "slide" if chosen in ("slide", "whoosh") else "cut"   # "whoosh": tried, replaced


def overlaps(settings: Settings, plan: EditPlan, lengths: list[float], fps: int) -> list[float]:
    """For each cut between clips, how long the slide is (0 for a hard cut)."""
    cuts = max(0, len(plan.segments) - 1)
    if between(settings, plan) != "slide":
        return [0.0] * cuts
    d = max(1, round(SLIDE_SEC * fps)) / fps
    out = []
    for i in range(cuts):
        # Both clips must keep a middle once their slides are taken off.
        def room(j: int) -> bool:
            ends = (1 if j > 0 else 0) + (1 if j < cuts else 0)
            return lengths[j] - ends * d >= MIN_MIDDLE_SEC
        out.append(d if room(i) and room(i + 1) else 0.0)
    return out


def starts(lengths: list[float], slides: list[float]) -> list[float]:
    """Where each clip starts in the finished video (where it begins to slide in)."""
    out, t = [], 0.0
    for i, length in enumerate(lengths):
        out.append(t)
        t += length - (slides[i] if i < len(slides) else 0.0)
    return out


@dataclass(frozen=True)
class Piece:
    """A stretch of one clip, rendered on its own."""
    segment: int
    offset: float          # how far into the clip it starts (seconds)
    length: float
    cut_in: bool           # a hard cut before it (the sound fades in over a few ms)
    cut_out: bool


@dataclass(frozen=True)
class Slide:
    """The end of one clip with the start of the next sliding over it."""
    leaving: Piece
    arriving: Piece

    @property
    def length(self) -> float:
        return self.leaving.length


def layout(lengths: list[float], slides: list[float]) -> list[Piece | Slide]:
    """The pieces of the video, in order."""
    out: list[Piece | Slide] = []
    n = len(lengths)
    for i, length in enumerate(lengths):
        head = slides[i - 1] if i > 0 else 0.0
        tail = slides[i] if i < n - 1 else 0.0
        out.append(Piece(i, head, length - head - tail, cut_in=head == 0, cut_out=tail == 0))
        if tail:
            out.append(Slide(Piece(i, length - tail, tail, False, False),
                             Piece(i + 1, 0.0, tail, False, False)))
    return out


def compose_args(leaving: Path, arriving: Path, length: float, codec: list[str],
                 target: Path, extra: list[str]) -> list[str]:
    """FFmpeg arguments laying the arriving piece over the leaving one, sliding in
    from the right and settling, with the sound crossfading. ``extra``: output
    options, the same as the pieces either side (so they join without re-encoding)."""
    ease = f"clip(t/{length:.4f},0,1)"
    graph = ";".join([
        # The leaving picture holds its last frame should it end a frame early.
        f"[0:v]tpad=stop_mode=clone:stop_duration={length:.4f}[leaving]",
        f"[leaving][1:v]overlay=x='W*(1-({ease})*({ease})*(3-2*({ease})))':y=0:eval=frame,"
        f"trim=duration={length:.4f},setpts=PTS-STARTPTS,format=yuv420p[v]",
        # A hair shorter than the pieces, or FFmpeg can find it longer than they are.
        f"[0:a][1:a]acrossfade=d={length - 0.002:.4f}:c1=tri:c2=tri[a]",
    ])
    return ["-i", str(leaving), "-i", str(arriving), "-filter_complex", graph,
            "-map", "[v]", "-map", "[a]", "-t", f"{length:.4f}", *codec, *extra, str(target)]
