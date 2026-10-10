"""Effects on the big moments of a video (spec 7.8), placed by AI-Editor itself.

Phase 2C-1: a flash, a screen shake and a sound effect. Each is its own
module returning a piece of FFmpeg filter graph (flash.py, shake.py, sfx.py);
placement.py decides where they go.

Effects aren't stored in the plan: they're worked out from the analysis each
time a video is previewed or rendered, so trimming a clip or adding one in
Review never leaves an effect behind on a moment that's gone. The same plan
always gets the same effects. What the plan keeps is which kinds are on for
that video (``plan.source["effects"]``), when changed from the Settings, and
the single moments switched off in Review (``plan.source["effects_off"]``,
by recording and time, so they stay off however the clips are moved).

Sliding between clips is in render/slide.py.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..config import Settings
from ..recipes.plan import EditPlan

KINDS = ("flash", "shake", "sfx")
LABELS = {"flash": "Flash", "shake": "Screen shake", "sfx": "Sound effects"}


@dataclass(frozen=True)
class Effect:
    kind: str            # flash | shake | sfx
    at: float            # when, in the recording's time (seconds)
    length: float        # seconds
    why: str             # "impact" (a jump in the game's sound) | "reaction" (you)
    sound: str | None = None   # sfx: boom | hit

    def within(self, seg_in: float) -> float:
        """When it starts, counted from the start of a segment beginning at ``seg_in``."""
        return self.at - seg_in

    def as_dict(self) -> dict:
        return {"type": self.kind, "at": round(self.at, 3), "duration": round(self.length, 3),
                "why": self.why, **({"sound": self.sound} if self.sound else {})}


def switches(settings: Settings, plan: EditPlan) -> list[str]:
    """The kinds of effect on for this video: its own choice, else the Settings'."""
    chosen = (plan.source or {}).get("effects")
    if chosen is None:
        chosen = settings.effects.on_for(plan.recipe)
    return [k for k in KINDS if k in chosen]


def set_switches(plan: EditPlan, kinds: list[str]) -> None:
    plan.source["effects"] = [k for k in KINDS if k in kinds]


def moment_key(recording_id: int, at: float) -> str:
    """One moment's name, for switching it off: where it is in the recording."""
    return f"{recording_id}:{at:.1f}"


def _placed(conn: sqlite3.Connection, settings: Settings, plan: EditPlan) -> list[list[Effect]]:
    from .placement import place

    on = switches(settings, plan)
    if not on:
        return [[] for _ in plan.segments]
    return place(conn, settings, plan, on)


def for_plan(conn: sqlite3.Connection, settings: Settings, plan: EditPlan) -> list[list[Effect]]:
    """Each segment's effects, in order, without the moments switched off in Review."""
    off = set((plan.source or {}).get("effects_off", []))
    return [[e for e in effects if moment_key(seg.recording_id, e.at) not in off]
            for seg, effects in zip(plan.segments, _placed(conn, settings, plan))]


def moments(conn: sqlite3.Connection, settings: Settings,
            plan: EditPlan) -> list[tuple[str, str]]:
    """Every moment with effects, switched off or not, for Review: (label, key).
    'Clip 3 at 1:42: shake + boom'."""
    from ..publish import clock, placed
    from ..render.final import frame_exact
    from ..render.slide import overlaps

    fps = settings.render.presets[settings.render.preset].fps
    found = []
    slides = overlaps(settings, plan, [frame_exact(s.length, fps) for s in plan.segments], fps)
    begins = [start for start, _ in placed(plan, fps, slides)]
    for index, (seg, effects) in enumerate(zip(plan.segments, _placed(conn, settings, plan))):
        start = begins[index]
        times = sorted({e.at for e in effects})
        for at in times:
            here = [e for e in effects if e.at == at]
            what = [e.kind for e in here if e.kind != "sfx"] + [e.sound for e in here
                                                                  if e.kind == "sfx" and e.sound]
            found.append((f"Clip {index + 1} at {clock(start + at - seg.src_in)}: "
                          f"{' + '.join(what)}", moment_key(seg.recording_id, at)))
    return found


def set_moments_on(plan: EditPlan, all_keys: list[str], kept: list[str]) -> None:
    """Switch off every moment in ``all_keys`` that isn't ``kept``."""
    plan.source["effects_off"] = [k for k in all_keys if k not in set(kept)]


def summary(effects: list[list[Effect]]) -> str:
    """'4 flashes, 3 shakes, 7 sound effects', for messages."""
    counts = {k: sum(1 for seg in effects for e in seg if e.kind == k) for k in KINDS}
    names = {"flash": ("flash", "flashes"), "shake": ("shake", "shakes"),
             "sfx": ("sound effect", "sound effects")}
    parts = [f"{n} {names[k][n != 1]}" for k, n in counts.items() if n]
    return ", ".join(parts) or "no effects"
