"""The local AI turning a tip into a rule (Phase 2H-2).

Gemma fills in a form: which kind of rule (kinds.KINDS), where it applies, and
the values, and nothing else: Ollama holds it to the form's shape. Only the
values that kind of rule takes are kept, and the read-back is AI-Editor's own
(kinds.Rule.said), so a misunderstanding shows before anything is saved.

The examples in the question are deliberately not the creator's own test tips
("Ensure the action is always within the clip", "Make sure the video sound is
never over my voice", "Suggest where an effect can work and which effect"), so
those test whether it understands, not whether it can copy.

On the graphics card, only when you press the button: a few seconds, longer
the first time while the model loads.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import llm
from ..config import Settings
from .kinds import EFFECTS, KINDS, ORDERS, REFUSED, SWITCHES, VIDEOS, Rule
from .moments import EFFECT_NAMES, MOMENTS, NO_EFFECTS, WHICH, exact

# The values each kind keeps: its own, plus the ones it may have.
ACCEPTS = {"clip_length": ("min_seconds", "max_seconds"), "video_length": ("minutes",),
           "teaser": ("on", "seconds"), "clip_order": ("order",), "quality_bar": ("level",),
           "silence": ("seconds",), "caption_look": ("size_scale", "words", "height_percent"),
           "effect_amount": ("per_minute", "effect"), "switch": ("switch", "on"),
           "moment": ("which", "moments"), "effect_on_moment": ("moments", "effects")}
# The form's name for a value, where it differs: "switch" is also a kind's name, and with
# both Gemma left the value out 2 times in 5.
FORM_NAME = {"switch": "which_switch"}
NUMBERS = ("min_seconds", "max_seconds", "minutes", "seconds", "level", "size_scale",
           "height_percent", "per_minute")

SYSTEM = """You turn a streamer's editing tips into settings for AI-Editor, the program that
edits their stream recordings into highlight videos, Shorts and Let's Play episodes. You
fill in a form; you never make up kinds of rule or values the tip doesn't give."""

QUESTION = """The streamer's tip: "{tip}"

Pick the ONE kind of rule it is:
{kinds}
- speed_up: speeding anything up (AI-Editor never does)
- effects_on: switching effects or captions on or off for good
- note: anything else, or more than one idea at once

games: the games it names, from: {games}. Empty if it doesn't name one.
videos: the kinds of video it names: highlights, shorts, letsplay. Empty if it doesn't say.
Fill in only the values the tip gives, for the kind you picked; leave out the rest.
why_note: for speed_up, effects_on or note, a few words on what the tip wants.

Examples (not the streamer's own):
"Wardogs clips should be at most 25 seconds" -> kind clip_length, games [Wardogs], max_seconds 25
"I want my Dawnwalker parts to be around 40 minutes" -> kind video_length, games [The Blood of Dawnwalker], videos [letsplay], minutes 40
"Don't open highlights with a teaser" -> kind teaser, videos [highlights], on false
"Bigger captions on Shorts" -> kind caption_look, videos [shorts], size_scale 1.3
"Always use the clips where I get first blood" -> kind moment, which always, moments [first_blood]
"Keep the clips where my team gets aced out of my highlights" -> kind moment, videos [highlights], which never, moments [aced]
"Add a zoom whenever I get a triple kill" -> kind effect_on_moment, moments [triple_kill], effects [zoom]
"Turn my eliminations into slow motion with a boom" -> kind effect_on_moment, moments [kill], effects [replay, sfx]
"Make it faster when I'm walking around" -> kind speed_up"""


def schema(games: list[str]) -> dict:
    number = {"type": "number"}
    return {"type": "object", "properties": {
        "kind": {"enum": [*KINDS, *REFUSED, "note"]},
        "games": {"type": "array", "items": {"enum": games} if games else {"type": "string"}},
        "videos": {"type": "array", "items": {"enum": list(VIDEOS)}},
        **{name: number for name in NUMBERS},
        "words": {"type": "integer"},
        "on": {"type": "boolean"},
        "order": {"enum": list(ORDERS)},
        "effect": {"enum": list(EFFECTS)},
        FORM_NAME["switch"]: {"enum": list(SWITCHES)},
        "which": {"enum": list(WHICH)},
        "moments": {"type": "array", "items": {"enum": list(MOMENTS)}},
        "effects": {"type": "array", "items": {"enum": [*EFFECT_NAMES, NO_EFFECTS]}},
        "why_note": {"type": "string", "maxLength": 120},
    }, "required": ["kind", "games", "videos"]}


@dataclass
class Understood:
    rule: Rule
    message: str          # what AI-Editor says about it
    savable: bool = True  # speeding up isn't even kept as a note


def question(tip: str, games: list[str]) -> str:
    kinds = "\n".join(f"- {k.name}: {k.about}" for k in KINDS.values())
    return QUESTION.format(tip=tip.strip().replace('"', "'"), kinds=kinds,
                           games=", ".join(games) or "(none yet)")


def to_rule(answer: dict, games: list[str]) -> Understood:
    """The AI's form as a rule AI-Editor can stand behind, or a note saying why not."""
    kind = answer.get("kind")
    named = [g for g in answer.get("games") or [] if isinstance(g, str) and g.strip()]
    known = {g.casefold(): g for g in games}
    named = [known.get(g.casefold(), g.strip()) for g in named]
    videos = [v for v in answer.get("videos") or [] if v in VIDEOS]
    why = str(answer.get("why_note") or "").strip()
    if kind == "speed_up":
        return Understood(Rule("note", {}, named, videos, why or "speed something up"),
                          REFUSED["speed_up"], savable=False)
    if kind in REFUSED:
        return Understood(Rule("note", {}, named, videos, why or kind.replace("_", " ")),
                          REFUSED[kind])
    if kind not in KINDS:
        return Understood(Rule("note", {}, named, videos, why or "kept for later"),
                          "AI-Editor can't act on this one yet, so it would be kept as a note: "
                          "it won't change the edit.")
    spec = KINDS[kind]
    params = {}
    for name in ACCEPTS[kind]:
        value = answer.get(FORM_NAME.get(name, name))
        if value is None and name == "switch":
            # 2 times in 5 Gemma left out which one, naming it in why_note instead:
            # "...which corresponds to the whole_fights switch".
            value = next((s for s in SWITCHES if s in why), None)
        if name == "moments":
            value = list(dict.fromkeys(m for m in value or [] if m in MOMENTS)) or None
        elif name == "effects":
            value = list(dict.fromkeys(e for e in value or [] if e in EFFECT_NAMES)) or                 ([NO_EFFECTS] if NO_EFFECTS in (value or []) else None)
        elif name == "which" and value not in WHICH:
            value = None
        if value is None:
            continue
        if name in NUMBERS or name == "words":
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value != value or value < 0:     # NaN or below zero: not a value
                continue
        params[name] = value
    if kind == "switch" and "switch" in params:
        # A tip asking for something wants it on: Gemma named the switch for all three of the
        # creator's tips ("Make sure the video sound is never over my voice") and left on out.
        params.setdefault("on", True)
    missing = ([f for f in spec.fields if f not in params] if spec.needs_all
               else [] if any(f in params for f in spec.fields) else list(spec.fields))
    if missing:
        hint = {"moment": "naming the moment, like \"Always include pentakills\"",
                "effect_on_moment": "naming the moment and the effect, like \"A zoom on "
                                    "pentakills\""}.get(
            kind, "saying it with a number, like \"at most 20 seconds\"")
        return Understood(Rule("note", {}, named, videos, why or "kept for later"),
                          "AI-Editor couldn't tell from it "
                          + ("the number" if any(f in NUMBERS for f in missing) else "what to set")
                          + f", so it would be kept as a note. Try {hint}.")
    if kind == "effect_on_moment" and not all(exact(m) for m in params["moments"]):
        loose = [m for m in params["moments"] if not exact(m)]
        return Understood(Rule("note", {}, named, videos, why or "an effect on a moment"),
                          "An effect needs the exact second of its moment, and AI-Editor only "
                          "knows that for League's moments and your marks, not "
                          + ", ".join(m.replace("_", " ") for m in loose)
                          + ". So it would be kept as a note.")
    if videos and not set(videos) & set(spec.videos):
        allowed = " and ".join(VIDEOS[v] for v in spec.videos)
        return Understood(Rule("note", {}, named, videos, why or "kept for later"),
                          f"That only applies to {allowed}, so it would be kept as a note.")
    videos = [v for v in videos if v in spec.videos]
    rule = Rule(kind, params, named, videos)
    return Understood(rule, rule.said())


def understand(settings: Settings, tip: str, games: list[str]) -> Understood:
    """Ask the local AI what the tip means. Raises llm's errors when it can't answer."""
    answer = llm.ask(settings, SYSTEM, question(tip, games), schema=schema(games),
                     keep_alive="2m")
    kind = answer.get("kind")
    left_out = [n for n in FOLLOW_UP.get(kind, ())
                if answer.get(FORM_NAME.get(n, n)) in (None, [])]
    if left_out and not (kind == "switch" and any(s in str(answer.get("why_note")) for s in
                                                   SWITCHES)):
        answer = {**answer, **llm.ask(settings, SYSTEM, follow_up(tip, kind, left_out, games),
                                      schema=follow_up_schema(left_out, games),
                                      keep_alive="2m")}
    return to_rule(answer, games)


# A choice the form left empty is asked again on its own, with the answer required:
# for "Suggest where an effect can work and which effect" Gemma picked switch every time
# and left which one out 5 times in 5. Never a length or a time: "short clips" stays a
# note rather than the AI making up a number you didn't give.
FOLLOW_UP = {"switch": ("switch",), "clip_order": ("order",), "teaser": ("on",),
             "quality_bar": ("level",), "moment": ("which", "moments"),
             "effect_on_moment": ("moments", "effects")}


def follow_up(tip: str, kind: str, left_out: list[str], games: list[str]) -> str:
    return (question(tip, games) + f"\n\nYou picked the kind {kind}. Now fill in "
            + " and ".join(FORM_NAME.get(n, n) for n in left_out)
            + f", from the description of {kind} above.")


def follow_up_schema(left_out: list[str], games: list[str]) -> dict:
    whole = schema(games)["properties"]
    names = [FORM_NAME.get(n, n) for n in left_out]
    return {"type": "object", "properties": {n: whole[n] for n in names}, "required": names}
