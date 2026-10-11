"""Using a style profile on a video (Phase 2G-2).

What the creator chose (2026-10-11): Create video picks the profile made for
that game and kind of video by itself, shows it, and it can be changed (or
"No profile", the Settings as they are). The profile's values are copied into
the plan when it's made (plan.source["style"]), so changing the profile later
never quietly changes a plan already reviewed; to use it again, make the plan
again. Everything that makes, refills, previews or renders a plan reads them
through ``styled()``.

What each slider changes, and only there:

* **Cuts per minute** -> how long highlight clips run (60 / cuts a minute, on
  average). Not Shorts (one clip) or Let's Plays (parts are split their own way).
* **Opening teaser** -> the highlight teaser's length; 0: no teaser.
* **Longest silence left in** -> the Let's Play silence trim only (the
  creator's choice: highlight and Short clips already end when you stop
  talking).
* **Zooms / sound effects per minute** -> at most that many of each, on the
  biggest moments; **zoom strength** -> how far. Only when they're switched on:
  a profile never switches an effect on.
* **Caption size, height** -> the burned-in captions (Let's Plays and
  highlights; size for Shorts too); **words at once** -> Shorts. Only when
  captions are switched on.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from ..config import Settings

if TYPE_CHECKING:
    from ..recipes.plan import EditPlan

# Caption text, as OCR boxes it, is about 1.3 times the font size (profiles.BOX_PER_FONT).
BOX_PER_FONT = 1.3
NO_PROFILE = "No profile (my Settings)"
# Highlight clips mostly run to their longest (see clip_lengths): it's set this much over
# the average a profile asks for.
LONGEST_PER_AVERAGE = 1.1


def clip_lengths(settings: Settings, cuts_per_min: float) -> tuple[float, float] | None:
    """(shortest, longest) highlight clip for an average of 60 / ``cuts_per_min``
    seconds. None: leave them as they are.

    Clips mostly run to the longest they may: on the creator's League streams,
    with the usual 50 s longest, the middle clip was 46.9 s. So the longest is
    set just over the average wanted, not twice it (that gave 37 s for 26)."""
    if cuts_per_min <= 0.2:
        return None
    average = 60.0 / cuts_per_min
    longest = min(300.0, max(4.0, average * LONGEST_PER_AVERAGE))
    shortest = min(settings.clips.min_length_sec, max(3.0, longest - 1))
    return shortest, longest


def apply(settings: Settings, values: dict[str, float], recipe: str) -> Settings:
    """``settings`` with a profile's ``values`` in, for one kind of video. A copy:
    the creator's own settings are never changed."""
    v = values
    h, lp, fx, cap = (settings.highlights, settings.lets_play, settings.effects,
                      settings.captions)
    if recipe == "highlights":
        lengths = clip_lengths(settings, v.get("cuts_per_min", 0.0))
        h_update = {}
        if lengths:
            h_update["max_clip_sec"] = round(lengths[1], 1)
        if "hook_sec" in v:
            teaser = float(v["hook_sec"])
            if teaser < 2:
                h_update["hook"] = False
            else:
                h_update.update(hook=True, hook_seconds=(max(2.0, teaser - 3), teaser + 3))
        h = h.model_copy(update=h_update)
        clips = settings.clips
        if lengths and lengths[0] < clips.min_length_sec:
            clips = clips.model_copy(update={"min_length_sec": lengths[0]})
    else:
        clips = settings.clips
    if recipe == "letsplay" and "dead_air_sec" in v:
        lp = lp.model_copy(update={"dead_air_sec": max(5.0, min(300.0, float(v["dead_air_sec"])))})
    caps = {kind: float(v[key]) for kind, key in (("zoom", "zooms_per_min"), ("sfx", "sfx_per_min"))
            if key in v}
    fx = fx.model_copy(update={
        "kind_per_min": caps,
        **({"zoom_strength": max(0.05, min(0.5, float(v["zoom_strength"])))}
           if "zoom_strength" in v else {})})
    cap_update = {}
    if "caption_size" in v:
        share = float(v["caption_size"]) / 100 / BOX_PER_FONT
        cap_update["size"] = max(20, min(160, round(share * 1080)))
        cap_update["shorts_size"] = max(30, min(200, round(share * 1920)))
    if "caption_position" in v:
        up = max(0.0, min(0.8, float(v["caption_position"]) / 100))
        cap_update["position"] = cap.position.model_copy(
            update={"lets_play" if recipe == "letsplay" else "highlights": up})
    if "caption_words" in v:
        cap_update["shorts_words"] = max(1, min(6, round(float(v["caption_words"]))))
    cap = cap.model_copy(update=cap_update)
    return settings.model_copy(update={"highlights": h, "lets_play": lp, "effects": fx,
                                       "captions": cap, "clips": clips})


def styled(settings: Settings, plan: "EditPlan | None") -> Settings:
    """The settings to make, refill, preview or render ``plan`` with: its style
    profile's values in, if it was made with one."""
    style = ((plan.source or {}).get("style") if plan is not None else None) or {}
    if not style.get("values"):
        return settings
    return apply(settings, style["values"], plan.recipe)


def stamp(plan: "EditPlan", profile, settings: Settings) -> None:
    """Keep the profile's values in the plan, as saved (or as measured, if never
    saved). A copy: later changes to the profile don't reach it."""
    plan.source = dict(plan.source or {})
    plan.source["style"] = {"id": profile.id, "name": profile.name,
                            "values": profile.current(settings)}


def matching(conn: sqlite3.Connection, settings: Settings, game: str | None,
             recipe: str) -> int | None:
    """The profile made for this game and kind of video, if there is one: both
    ticked on the profile. (Several: the most recently changed.)"""
    import json

    want = (game or "").casefold()
    for row in conn.execute("SELECT id, games_json, applies_to_json FROM style_profiles "
                            "ORDER BY updated_at DESC, id DESC"):
        games = [g.casefold() for g in json.loads(row["games_json"] or "[]")]
        kinds = json.loads(row["applies_to_json"] or "[]")
        if recipe in kinds and want and want in games:
            return int(row["id"])
    return None


def summary(plan: "EditPlan") -> str | None:
    """One line for Review: which profile, and what it changed for this kind of video."""
    style = (plan.source or {}).get("style") or {}
    v = style.get("values")
    if not v:
        return None
    said = []
    if plan.recipe == "highlights":
        if v.get("cuts_per_min", 0) > 0.2:
            said.append(f"clips about {60 / v['cuts_per_min']:.0f} s")
        said.append("no teaser" if v.get("hook_sec", 0) < 2 else f"a {v['hook_sec']:.0f} s teaser")
    if plan.recipe == "letsplay":
        said.append(f"silences over {max(5.0, v.get('dead_air_sec', 20)):.0f} s cut down")
    else:
        said.append(f"when switched on: at most {v.get('zooms_per_min', 0):g} zooms a minute "
                    f"({1 + v.get('zoom_strength', 0.2):.2f}x) and {v.get('sfx_per_min', 0):g} "
                    "sound effects a minute")
    if "caption_size" in v:
        said.append(f"captions {v['caption_size']:g}% high when on")
    return f"Style: {style.get('name', 'a profile')}, " + ", ".join(said) + "."
