"""Effects on the big moments of a video (spec 7.8), placed by AI-Editor itself.

Phase 2C-1: a flash, a screen shake and a sound effect. Each is its own
module returning a piece of FFmpeg filter graph (flash.py, shake.py, sfx.py);
placement.py decides where they go.

Effects aren't stored in the plan: they're worked out from the analysis each
time a video is previewed or rendered, so trimming a clip or adding one in
Review never leaves an effect behind on a moment that's gone. The same plan
always gets the same effects. What the plan keeps is which kinds are on for
that video (``plan.source["effects"]``), when changed from the Settings.
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
    sound: str | None = None   # sfx: boom | hit | whoosh

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


def for_plan(conn: sqlite3.Connection, settings: Settings, plan: EditPlan) -> list[list[Effect]]:
    """Each segment's effects, in order. Empty lists when they're all off."""
    from .placement import place

    on = switches(settings, plan)
    if not on:
        return [[] for _ in plan.segments]
    return place(conn, settings, plan, on)


def summary(effects: list[list[Effect]]) -> str:
    """'4 flashes, 3 shakes, 7 sound effects', for messages."""
    counts = {k: sum(1 for seg in effects for e in seg if e.kind == k) for k in KINDS}
    names = {"flash": ("flash", "flashes"), "shake": ("shake", "shakes"),
             "sfx": ("sound effect", "sound effects")}
    parts = [f"{n} {names[k][n != 1]}" for k, n in counts.items() if n]
    return ", ".join(parts) or "no effects"
