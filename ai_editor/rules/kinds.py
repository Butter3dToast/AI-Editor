"""The kinds of rule AI-Editor knows, what each changes, and how it's said back.

Each kind changes Settings for one kind of video, on a copy: never the
creator's own. Its read-back is written here from the rule itself, so what the
Rules tab says is exactly what will happen, whatever the AI understood.

Moment rules (2H-3a, rules/moments.py) say which moments always or never go
in, and effect rules (2H-3b) which effects suit a moment: they choose clips and
effects rather than change Settings, so apply() hands them on in
settings.moment_rules for the recipes and effects/placement.py.

Not rules, on purpose (2H-2): speeding anything up (the creator's choice in 2C: never); switching effects or
captions on (ticked in Review).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..config import Settings
from . import moments as moment_rules

VIDEOS = {"highlights": "highlights", "shorts": "Shorts", "letsplay": "Let's Plays"}
ORDERS = {"timeline": "as it happened, the teaser's moment saved for last",
          "chronological": "strictly as it happened",
          "balanced": "strong and calmer clips in turn",
          "best_last": "building up to the best"}
EFFECTS = {"all": "effects", "flash": "flashes", "shake": "screen shakes",
           "sfx": "sound effects", "zoom": "zooms", "replay": "slow-motion replays"}
SWITCHES = {"whole_fights": "clips start before a fight that's already going",
            "game_under_voice": "the game is kept under your voice",
            "suggest_effects": "Review suggests effects for the big moments"}


@dataclass(frozen=True)
class Kind:
    name: str
    about: str                       # for the AI: what it's for, and which fields it fills
    videos: tuple[str, ...]          # the kinds of video it can change
    fields: tuple[str, ...]          # the values it needs, at least one of them
    apply: Callable[[Settings, dict, str], Settings]
    say: Callable[[dict], str]
    needs_all: bool = False          # every field, not just one


def _clamp(x, low: float, high: float) -> float:
    return max(low, min(high, float(x)))


def _copy(settings: Settings, part: str, **values) -> Settings:
    section = getattr(settings, part)
    return settings.model_copy(update={part: section.model_copy(update=values)})


# --- Clip length ----------------------------------------------------------------------------


def _clip_length(s: Settings, p: dict, video: str) -> Settings:
    low, high = p.get("min_seconds"), p.get("max_seconds")
    if video == "shorts":
        sh = s.shorts
        high = _clamp(high, 10, 180) if high is not None else sh.max_length_sec
        low = _clamp(low, 3, high - 1) if low is not None else min(sh.min_length_sec, high - 1)
        return _copy(s, "shorts", min_length_sec=low, max_length_sec=high)
    if video == "highlights":
        high = _clamp(high, 10, 300) if high is not None else s.highlights.max_clip_sec
        s = _copy(s, "highlights", max_clip_sec=high)
        low = _clamp(low, 3, high - 1) if low is not None else min(s.clips.min_length_sec,
                                                                    high - 1)
        return _copy(s, "clips", min_length_sec=low)
    return s


def _say_clip_length(p: dict) -> str:
    low, high = p.get("min_seconds"), p.get("max_seconds")
    if low is not None and high is not None:
        return f"clips {low:g}–{high:g} seconds long"
    if high is not None:
        return f"clips {high:g} seconds long at most"
    return f"clips at least {low:g} seconds long"


# --- Video length ---------------------------------------------------------------------------


def _video_length(s: Settings, p: dict, video: str) -> Settings:
    minutes = p["minutes"]
    if video == "highlights":
        return _copy(s, "highlights", target_length_min=_clamp(minutes, 1, 60))
    if video == "letsplay":
        minutes = _clamp(minutes, 10, 90)
        lp = s.lets_play
        low, high = round(minutes * 5 / 6, 1), round(minutes * 7 / 6, 1)
        preferred = max(lp.story_extension_preferred_max_min, high)
        return _copy(s, "lets_play", target_min=minutes, normal_range_min=(low, high),
                     story_extension_preferred_max_min=preferred,
                     story_extension_hard_max_min=max(lp.story_extension_hard_max_min,
                                                      preferred))
    return s


def _say_video_length(p: dict) -> str:
    return f"about {p['minutes']:g} minutes long (highlights: at least that)"


# --- Teaser, order, quality ----------------------------------------------------------------


def _teaser(s: Settings, p: dict, video: str) -> Settings:
    on = bool(p["on"])
    if video == "shorts":
        return _copy(s, "shorts", hook=on)
    if video == "highlights":
        if not on:
            return _copy(s, "highlights", hook=False)
        seconds = p.get("seconds")
        if seconds is None:
            return _copy(s, "highlights", hook=True)
        seconds = _clamp(seconds, 3, 30)
        return _copy(s, "highlights", hook=True,
                     hook_seconds=(max(2.0, seconds - 3), seconds + 3))
    return s


def _say_teaser(p: dict) -> str:
    if not p["on"]:
        return "no opening teaser"
    seconds = p.get("seconds")
    return f"an opening teaser of about {seconds:g} seconds" if seconds is not None \
        else "an opening teaser"


def _order(s: Settings, p: dict, video: str) -> Settings:
    return _copy(s, "highlights", ordering=p["order"]) if video == "highlights" else s


def _say_order(p: dict) -> str:
    return f"clips in order: {ORDERS[p['order']]}"


def _quality(s: Settings, p: dict, video: str) -> Settings:
    return _copy(s, "highlights", min_clip_score=_clamp(p["level"], 0.2, 0.9)) \
        if video == "highlights" else s


def _say_quality(p: dict) -> str:
    return f"quality bar {_clamp(p['level'], 0.2, 0.9):.2f} (usually 0.55; higher, only the best)"


# --- Let's Play silences --------------------------------------------------------------------


def _silence(s: Settings, p: dict, video: str) -> Settings:
    return _copy(s, "lets_play", dead_air_sec=_clamp(p["seconds"], 5, 300)) \
        if video == "letsplay" else s


def _say_silence(p: dict) -> str:
    return f"silences longer than {_clamp(p['seconds'], 5, 300):g} seconds cut down"


# --- Captions and effects: how, never whether ------------------------------------------------


def _captions(s: Settings, p: dict, video: str) -> Settings:
    c = s.captions
    update = {}
    if p.get("size_scale") is not None:
        scale = _clamp(p["size_scale"], 0.5, 2.0)
        update.update(size=int(_clamp(round(c.size * scale), 20, 160)),
                      shorts_size=int(_clamp(round(c.shorts_size * scale), 30, 200)))
    if p.get("words") is not None and video == "shorts":
        update["shorts_words"] = int(_clamp(round(p["words"]), 1, 6))
    if p.get("height_percent") is not None:
        place = "lets_play" if video == "letsplay" else "highlights"
        update["position"] = c.position.model_copy(
            update={place: _clamp(p["height_percent"], 0, 80) / 100})
    return _copy(s, "captions", **update) if update else s


def _say_captions(p: dict) -> str:
    said = []
    if p.get("size_scale") is not None:
        scale = _clamp(p["size_scale"], 0.5, 2.0)
        said.append(f"captions {scale:g}× the size" if scale != 1 else "captions their usual size")
    if p.get("words") is not None:
        words = int(_clamp(round(p["words"]), 1, 6))
        said.append(f"{words} word{'s' if words != 1 else ''} at a time on Shorts")
    if p.get("height_percent") is not None:
        said.append(f"captions {_clamp(p['height_percent'], 0, 80):g}% up from the bottom")
    return ", ".join(said) + " (when captions are on)"


def _effects(s: Settings, p: dict, video: str) -> Settings:
    if video not in ("highlights", "shorts"):
        return s
    rate = _clamp(p["per_minute"], 0, 10)
    effect = p.get("effect") or "all"
    if effect == "all":
        return _copy(s, "effects", **{f"{video}_per_min": rate})
    caps = dict(s.effects.kind_per_min)
    caps[effect] = rate
    return _copy(s, "effects", kind_per_min=caps)


def _say_effects(p: dict) -> str:
    rate = _clamp(p["per_minute"], 0, 10)
    effect = EFFECTS[p.get("effect") or "all"]
    if rate == 1:
        effect = {"flashes": "flash"}.get(effect, effect.removesuffix("s"))
    return f"at most {rate:g} {effect} a minute (when they're on)"


# --- Your three tips (2H-1), switched per game or kind of video --------------------------------


SWITCH_SETTING = {"whole_fights": ("clips", "keep_fights_whole"),
                  "game_under_voice": ("render", "game_under_voice"),
                  "suggest_effects": ("effects", "suggest")}


def _switch(s: Settings, p: dict, video: str) -> Settings:
    part, name = SWITCH_SETTING[p["switch"]]
    return _copy(s, part, **{name: bool(p["on"])})


def _say_switch(p: dict) -> str:
    said = SWITCHES[p["switch"]]
    return said if p["on"] else f"not: {said}"


# --- Moment rules (2H-3a): which moments always or never go in ----------------------------------


def _moment(s: Settings, p: dict, video: str) -> Settings:
    return s   # chooses clips, not settings: see apply()


KINDS: dict[str, Kind] = {k.name: k for k in [
    Kind("clip_length", "how long each clip may be, in seconds: min_seconds and/or max_seconds",
         ("highlights", "shorts"), ("min_seconds", "max_seconds"), _clip_length,
         _say_clip_length),
    Kind("video_length", "how long the whole video (highlights) or each part (Let's Plays) "
         "should be: minutes", ("highlights", "letsplay"), ("minutes",), _video_length,
         _say_video_length),
    Kind("teaser", "whether a video opens with a teaser of its best moment: on (true/false), "
         "and its length in seconds", ("highlights", "shorts"), ("on",), _teaser, _say_teaser),
    Kind("clip_order", "the order of a highlight video's clips: order is one of "
         + ", ".join(f"{k} ({v})" for k, v in ORDERS.items()), ("highlights",), ("order",),
         _order, _say_order),
    Kind("quality_bar", "how good a clip must be to go into a highlight video: level from 0.2 "
         "(anything decent) to 0.9 (only the very best); usually 0.55", ("highlights",),
         ("level",), _quality, _say_quality),
    Kind("silence", "in Let's Plays, how long a silence may run before it's cut down: seconds",
         ("letsplay",), ("seconds",), _silence, _say_silence),
    Kind("caption_look", "how burned-in captions look, never whether they're on: size_scale "
         "(1.3 for bigger, 0.8 for smaller), words at a time on Shorts, height_percent up from "
         "the bottom", ("highlights", "shorts", "letsplay"),
         ("size_scale", "words", "height_percent"), _captions, _say_captions),
    Kind("effect_amount", "how many effects at most, never whether they're on: per_minute, and "
         "effect: one of " + ", ".join(EFFECTS), ("highlights", "shorts"), ("per_minute",),
         _effects, _say_effects),
    Kind("switch", "switch one of these on or off: which_switch is whole_fights (start clips before a "
         "fight that's already going, so the action is all in the clip), game_under_voice (keep "
         "the game's sound under the streamer's voice), suggest_effects (suggest effects in "
         "Review); and on (true/false)", ("highlights", "shorts", "letsplay"),
         ("switch", "on"), _switch, _say_switch, needs_all=True),
    Kind("effect_on_moment", "which effects go on a moment: moments (from the list under "
         "moment; only League's and marked can carry an effect), and effects, one or more of "
         "flash, shake, sfx (a sound effect), zoom, replay (slow motion), or none for no "
         "effects there", ("highlights", "shorts"), ("moments", "effects"), _moment,
         moment_rules.effect_said, needs_all=True),
    Kind("moment", "which moments always go into the videos, or never do: which is always "
         "or never, and moments, one or more of: "
         + "; ".join(f"{m.name}" + (f" ({m.about})" if m.about else "")
                     for m in moment_rules.MOMENTS.values()),
         ("highlights", "shorts"), ("which", "moments"), _moment, moment_rules.said,
         needs_all=True),
]}

# Not rules: what the AI should answer for them, and what AI-Editor then says.
REFUSED = {
    "speed_up": "AI-Editor never speeds a video up: your choice (2C). Nothing to save.",
    "effects_on": "Rules don't switch effects or captions on: you tick them in Review, to be "
                  "sure they went in right. Kept as a note.",
}


@dataclass
class Rule:
    """One rule, as saved: what it is, and where it applies (empty: everywhere)."""
    kind: str                                   # a key of KINDS, or "note"
    params: dict = field(default_factory=dict)
    games: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    why_note: str = ""                          # for a note: why it isn't a rule
    id: str = ""                                # "r004", once saved

    @property
    def is_note(self) -> bool:
        return self.kind not in KINDS

    def where(self) -> str:
        """'League of Legends Shorts', 'Every video'."""
        kinds = KINDS.get(self.kind)
        videos = [v for v in self.videos if kinds is None or v in kinds.videos]
        if not videos and self.kind in ("moment", "effect_on_moment"):
            videos = list(kinds.videos)   # never Let's Plays: say so
        place = " and ".join(self.games)
        what = " and ".join(VIDEOS[v] for v in videos) if videos else ""
        if place and what:
            return f"{place} {what}"
        if place:
            return f"{place}, every video"
        return f"Every game's {what}" if what else "Every video"

    def said(self) -> str:
        """What it does, in AI-Editor's words: 'League of Legends Shorts: clips 20–40 seconds long.'"""
        if self.is_note:
            return f"📝 Note: {self.why_note or 'kept for later'}"
        text = f"{self.where()}: {KINDS[self.kind].say(self.params)}"
        if (self.kind in ("moment", "effect_on_moment") and moment_rules.league_only(self.params)
                and [g.casefold() for g in self.games] != ["league of legends"]):
            text += " (League only: other games can't tell yet)"
        return text + "."

    def applies_to(self, game: str | None, video: str) -> bool:
        kind = KINDS.get(self.kind)
        if kind is None or video not in kind.videos:
            return False
        if self.videos and video not in self.videos:
            return False
        if self.games:
            if game is None and self.kind in ("moment", "effect_on_moment"):
                return True   # every game's highlights: each clip's own game decides
            return game is not None and game.casefold() in {g.casefold() for g in self.games}
        return True


def apply(settings: Settings, rules: list[Rule], video: str) -> Settings:
    """``settings`` with ``rules`` in, oldest first, so a newer rule wins. A copy."""
    for rule in rules:
        kind = KINDS.get(rule.kind)
        if kind is None or video not in kind.videos:
            continue
        if rule.kind in ("moment", "effect_on_moment"):
            effect = rule.kind == "effect_on_moment"
            found = {"id": rule.id,
                     "which": "effect" if effect else rule.params.get("which", "always"),
                     "moments": list(rule.params.get("moments") or []), "games": rule.games,
                     "effects": [e for e in rule.params.get("effects") or []
                                 if e != moment_rules.NO_EFFECTS]}
            settings = settings.model_copy(update={
                "moment_rules": [*settings.moment_rules, found]})
        else:
            settings = kind.apply(settings, rule.params, video)
    return settings
