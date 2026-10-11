"""Effects on the big moments of a video (spec 7.8), placed by AI-Editor itself.

Phase 2C-1: a flash, a screen shake and a sound effect; 2C-2a a punch-in
zoom (zoom.py); 2C-2b a slow-motion replay (render/replay.py: it changes the
video's length, so the renderer builds it). Each is its own
module returning a piece of FFmpeg filter graph (flash.py, shake.py, sfx.py);
placement.py decides where they go.

Effects aren't stored in the plan: they're worked out from the analysis each
time a video is previewed or rendered, so trimming a clip or adding one in
Review never leaves an effect behind on a moment that's gone. The same plan
always gets the same effects. What the plan keeps is which kinds are on for
that video (``plan.source["effects"]``), when changed from the Settings, and
the single moments switched off in Review (``plan.source["effects_off"]``,
by recording and time, so they stay off however the clips are moved).

**Suggestions** (Phase 2H-1, the creator's tip "suggest where an effect can
work and which effect"): Review lists every big moment with the effects that
suit it -- all the kinds placed, as placement.py would with every one on --
none ticked until the creator ticks them. A ticked moment gets exactly those
(``plan.source["effects_picked"]``: its kinds, by recording and time); the
video's kinds become the ones its ticked moments use, and every other moment
is switched off. Ticking kinds for the whole video in Review goes back to the
same kinds everywhere.

Sliding between clips is in render/slide.py.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from ..config import Settings
from ..recipes.plan import EditPlan

KINDS = ("flash", "shake", "sfx", "zoom", "replay")
LABELS = {"flash": "Flash", "shake": "Screen shake", "sfx": "Sound effects",
          "zoom": "Punch-in zoom", "replay": "Slow-motion replay"}
# A moment placed with every kind on and with fewer is the same moment within
# this: a zoom keeps its moment further in from a clip's end (placement.py).
NEAR_SEC = 1.0


@dataclass(frozen=True)
class Effect:
    kind: str            # flash | shake | sfx
    at: float            # when, in the recording's time (seconds)
    length: float        # seconds
    why: str             # "impact" (a jump in the game's sound) | "reaction" (you)
    sound: str | None = None   # sfx: boom | hit
    label: str | None = None   # the League event it's on: "Triple kill"

    def within(self, seg_in: float) -> float:
        """When it starts, counted from the start of a segment beginning at ``seg_in``."""
        return self.at - seg_in

    def as_dict(self) -> dict:
        return {"type": self.kind, "at": round(self.at, 3), "duration": round(self.length, 3),
                "why": self.why, **({"sound": self.sound} if self.sound else {}),
                **({"label": self.label} if self.label else {})}


def switches(settings: Settings, plan: EditPlan) -> list[str]:
    """The kinds of effect on for this video: its own choice, else the Settings'."""
    chosen = (plan.source or {}).get("effects")
    if chosen is None:
        chosen = settings.effects.on_for(plan.recipe)
    return [k for k in KINDS if k in chosen]


def set_switches(plan: EditPlan, kinds: list[str]) -> None:
    """The kinds for the whole video: the same everywhere, so moments picked
    with their own effects (suggestions) go back to them."""
    plan.source["effects"] = [k for k in KINDS if k in kinds]
    plan.source.pop("effects_picked", None)


def moment_key(recording_id: int, at: float) -> str:
    """One moment's name, for switching it off: where it is in the recording."""
    return f"{recording_id}:{at:.1f}"


def _placed(conn: sqlite3.Connection, settings: Settings, plan: EditPlan) -> list[list[Effect]]:
    from ..style.apply import styled
    from .placement import place

    settings = styled(settings, plan)   # its style profile's amounts (2G-2)

    on = switches(settings, plan)
    if not on:
        return [[] for _ in plan.segments]
    return place(conn, settings, plan, on)


def _picked(plan: EditPlan) -> list[tuple[int, float, set[str]]]:
    """The moments ticked from suggestions: (recording, time, their kinds)."""
    found = []
    for key, kinds in ((plan.source or {}).get("effects_picked") or {}).items():
        recording, _, at = key.partition(":")
        found.append((int(recording), float(at), set(kinds)))
    return found


def _kept(plan: EditPlan, every: list[list[Effect]]) -> list[list[Effect]]:
    """Without the moments switched off in Review, and a picked moment's effects
    only the ones it was picked with."""
    off = set((plan.source or {}).get("effects_off", []))
    picked = _picked(plan)
    out = []
    for seg, effects in zip(plan.segments, every):
        kept = []
        for e in effects:
            if moment_key(seg.recording_id, e.at) in off:
                continue
            own = next((kinds for rid, at, kinds in picked
                        if rid == seg.recording_id and abs(at - e.at) <= NEAR_SEC), None)
            if own is None or e.kind in own:
                kept.append(e)
        out.append(kept)
    return out


def for_plan(conn: sqlite3.Connection, settings: Settings, plan: EditPlan) -> list[list[Effect]]:
    """Each segment's effects, in order, without the moments switched off in Review."""
    return _kept(plan, _placed(conn, settings, plan))


def _begins(conn: sqlite3.Connection, settings: Settings, plan: EditPlan,
            kept: list[list[Effect]]) -> tuple[list[float], list]:
    """Where each clip starts in the finished video, and its replays, for labels."""
    from ..publish import placed
    from ..render.final import frame_exact
    from ..render.replay import extra, for_plan as replays_for
    from ..render.slide import overlaps

    fps = settings.render.presets[settings.render.preset].fps
    slides = overlaps(settings, plan, [frame_exact(s.length, fps) for s in plan.segments], fps)
    replays = replays_for(conn, settings, plan, fps, kept)   # as the video will have them
    return [start for start, _ in placed(plan, fps, slides, extra(replays))], replays


def _said(effects: list[Effect]) -> str:
    """'shake + boom'."""
    return " + ".join([e.kind for e in effects if e.kind != "sfx"]
                      + [e.sound for e in effects if e.kind == "sfx" and e.sound])


def moments(conn: sqlite3.Connection, settings: Settings,
            plan: EditPlan) -> list[tuple[str, str]]:
    """Every moment with effects, switched off or not, for Review: (label, key).
    'Clip 3 at 1:42: shake + boom'."""
    from ..publish import clock
    from ..render.replay import shift

    found = []
    every = _placed(conn, settings, plan)
    begins, replays = _begins(conn, settings, plan, _kept(plan, every))
    for index, (seg, effects) in enumerate(zip(plan.segments, every)):
        start = begins[index]
        times = sorted({e.at for e in effects})
        for at in times:
            here = [e for e in effects if e.at == at]
            label = next((e.label for e in here if e.label), None)
            later = shift(at - seg.src_in, replays[index]) - (at - seg.src_in)
            found.append((f"Clip {index + 1} at {clock(start + at - seg.src_in + later)}: "
                          + (f"{label}: " if label else "") + _said(here),
                          moment_key(seg.recording_id, at)))
    return found


@dataclass
class Suggestion:
    """One big moment, and the effects that suit it (2H-1)."""
    key: str                     # moment_key: its recording and time
    recording_id: int
    at: float
    kinds: list[str]             # the effects that suit it, in KINDS order
    text: str                    # 'Clip 3 at 1:42: Triple kill: shake + replay + boom'
    on: bool = False             # it has effects in the video now
    now: list[str] = field(default_factory=list)   # which

    @property
    def label(self) -> str:
        if self.on and self.now and set(self.now) != set(self.kinds):
            return f"{self.text} (now: {' + '.join(self.now)})"
        return self.text


def suggestions(conn: sqlite3.Connection, settings: Settings,
                plan: EditPlan) -> list[Suggestion]:
    """Every big moment with the effects that suit it, and whether it has them
    now. None for Let's Plays (no effects there: the creator's choice)."""
    from ..publish import clock
    from ..render.replay import shift
    from ..style.apply import styled
    from .placement import place

    if plan.recipe == "letsplay":
        return []
    every = place(conn, styled(settings, plan), plan, list(KINDS))
    kept = for_plan(conn, settings, plan)
    begins, replays = _begins(conn, settings, plan, kept)
    found = []
    for index, (seg, effects) in enumerate(zip(plan.segments, every)):
        for at in sorted({e.at for e in effects}):
            here = [e for e in effects if e.at == at]
            label = next((e.label for e in here if e.label), None)
            later = shift(at - seg.src_in, replays[index]) - (at - seg.src_in)
            has = [e for e in kept[index] if abs(e.at - at) <= NEAR_SEC]
            found.append(Suggestion(
                moment_key(seg.recording_id, at), seg.recording_id, at,
                [k for k in KINDS if any(e.kind == k for e in here)],
                f"Clip {index + 1} at {clock(begins[index] + at - seg.src_in + later)}: "
                + (f"{label}: " if label else "") + _said(here),
                on=bool(has), now=[k for k in KINDS if any(e.kind == k for e in has)]))
    return found


def use_suggestions(conn: sqlite3.Connection, settings: Settings, plan: EditPlan,
                    ticked: list[str]) -> None:
    """Effects on the ticked moments only: each the ones suggested for it (or,
    ticked already, the ones it has)."""
    every = suggestions(conn, settings, plan)
    want = set(ticked)
    before = dict((plan.source or {}).get("effects_picked") or {})
    picked = {s.key: before.get(s.key) or (s.now if s.on else s.kinds)
              for s in every if s.key in want}
    plan.source = dict(plan.source or {})
    plan.source["effects"] = [k for k in KINDS if any(k in kinds for kinds in picked.values())]
    plan.source["effects_picked"] = picked
    plan.source["effects_off"] = []
    chosen = [s for s in every if s.key in want]
    off = set()
    for seg, effects in zip(plan.segments, _placed(conn, settings, plan)):
        for e in effects:
            if not any(s.recording_id == seg.recording_id and abs(s.at - e.at) <= NEAR_SEC
                       for s in chosen):
                off.add(moment_key(seg.recording_id, e.at))
    plan.source["effects_off"] = sorted(off)


def set_moments_on(plan: EditPlan, all_keys: list[str], kept: list[str]) -> None:
    """Switch off every moment in ``all_keys`` that isn't ``kept``."""
    plan.source["effects_off"] = [k for k in all_keys if k not in set(kept)]


def summary(effects: list[list[Effect]]) -> str:
    """'4 flashes, 3 shakes, 7 sound effects', for messages."""
    counts = {k: sum(1 for seg in effects for e in seg if e.kind == k) for k in KINDS}
    names = {"flash": ("flash", "flashes"), "shake": ("shake", "shakes"),
             "sfx": ("sound effect", "sound effects"), "zoom": ("zoom", "zooms"),
             "replay": ("slow-motion replay", "slow-motion replays")}
    parts = [f"{n} {names[k][n != 1]}" for k, n in counts.items() if n]
    return ", ".join(parts) or "no effects"
