"""Moment rules: which moments always go in, and which never do (Phase 2H-3a).

"Always include pentakills", "Never use clips where I die". A moment rule
works like a thumbs up or down you only say once: a clip with an "always"
moment goes in whatever its score, one with a "never" moment stays out.

What the creator chose (2026-10-24):

* **Your own pick wins.** A clip you gave a thumbs up or marked is never kept
  out by a rule. With Only my thumbs-up clips, "always" rules add nothing
  either: the thumbs-up list is the video, and Review lists the clips an
  "always" rule matched first in Add a clip.
* **Bad luck in a good fight is still a good clip.** A "never" rule about
  bad luck (your death, your team aced, a defeat) leaves a clip in when
  something good happens in it too: a kill, an ace or an objective. Other
  "never" rules ("never rage clips") don't.
* **"Triple kills" means a triple or bigger.**
* **"Baron steals" means a stolen Baron**: steal with an objective is that
  objective, stolen, not "Baron or any steal" (Gemma's form for it on 24 Oct).
* **Clips are never cut**: a clip is in or out.
* A newer rule wins over an older one, as for every rule.

Each moment is looked for only where it can be seen. League's are exact, from
League itself (game_events), in the stretch of the clip that's in the video.
The heard ones are what made the clip a clip (its reasons). The AI's tags are
its guess, and said so.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from ..analysis.game_events import counts_for_us

LEAGUE, HEARD, GUESS = "league", "heard", "guess"


@dataclass(frozen=True)
class Moment:
    name: str
    source: str
    clips: str        # "clips {this}": "with a penta kill", "where you die"
    short: str        # in Review: "📌 r004: Penta kill"
    about: str = ""   # for the AI, where the name isn't enough


MOMENTS: dict[str, Moment] = {m.name: m for m in [
    Moment("kill", LEAGUE, "where you get a kill", "your kill", "any kill of the streamer's"),
    Moment("double_kill", LEAGUE, "with a double kill or bigger", "Double kill"),
    Moment("triple_kill", LEAGUE, "with a triple kill or bigger", "Triple kill"),
    Moment("quadra_kill", LEAGUE, "with a quadra or penta kill", "Quadra kill"),
    Moment("penta_kill", LEAGUE, "with a penta kill", "Penta kill", "pentakill, penta"),
    Moment("death", LEAGUE, "where you die", "you die", "the streamer dies"),
    Moment("ace", LEAGUE, "where your team aces the enemy", "Ace"),
    Moment("aced", LEAGUE, "where your team gets aced", "your team aced",
           "the streamer's team is aced"),
    Moment("first_blood", LEAGUE, "where you get first blood", "First blood"),
    Moment("dragon", LEAGUE, "where your team takes a dragon", "Dragon", "any dragon, drake"),
    Moment("elder_dragon", LEAGUE, "where your team takes the Elder Dragon", "Elder Dragon"),
    Moment("baron", LEAGUE, "where your team takes Baron", "Baron", "Baron Nashor"),
    Moment("herald", LEAGUE, "where your team takes the Rift Herald", "Rift Herald"),
    Moment("voidgrubs", LEAGUE, "where your team takes Voidgrubs", "Voidgrubs"),
    Moment("atakhan", LEAGUE, "where your team takes Atakhan", "Atakhan"),
    Moment("turret", LEAGUE, "where you take a turret", "your turret", "tower"),
    Moment("inhibitor", LEAGUE, "where you take an inhibitor", "your inhibitor"),
    Moment("steal", LEAGUE, "where your side steals an objective", "a steal",
           "stealing Baron, a dragon or another objective"),
    Moment("victory", LEAGUE, "where you win the match", "Victory"),
    Moment("defeat", LEAGUE, "where you lose the match", "Defeat"),
    Moment("marked", HEARD, "you marked with the Stream Companion", "your mark",
           "a moment the streamer marked with the hotkey"),
    Moment("laughter", HEARD, "with laughter", "laughter", "laughing"),
    Moment("shouting", HEARD, "where you shout or react loudly", "a loud reaction",
           "shouting, screaming, a loud reaction"),
    Moment("gunfire", HEARD, "with gunfire or explosions", "gunfire", "gunfire, explosions"),
    *[Moment(tag, GUESS, f"the AI thinks are {tag} (its guess)", f"{tag} (AI's guess)",
             f"clips the AI tagged {tag}")
      for tag in ("funny", "fail", "rage", "clutch", "scary", "teamwork", "banter")],
]}
WHICH = {"always": "always put in clips", "never": "never use clips"}
# Bad luck: a "never" rule about these leaves a clip in when something good happens too.
BAD_LUCK = {"death", "aced", "defeat"}
GOOD = {"kill", "ace", "first_blood", "dragon", "elder_dragon", "baron", "herald", "voidgrubs",
        "atakhan", "turret", "inhibitor", "steal"}
MONSTER = {"Baron": "baron", "Rift Herald": "herald", "Voidgrub": "voidgrubs",
           "Atakhan": "atakhan", "Turret": "turret", "Inhibitor": "inhibitor"}
MULTIKILL = {2: "double_kill", 3: "triple_kill", 4: "quadra_kill", 5: "penta_kill"}
# Objectives that can be stolen: "steal" with one of these is that one, stolen.
STOLEN = {"dragon": "a dragon", "elder_dragon": "the Elder Dragon", "baron": "Baron",
          "herald": "the Rift Herald", "voidgrubs": "Voidgrubs", "atakhan": "Atakhan"}
HEARD_REASONS = {"laughter": "laughter", "shout": "shouting", "scream": "shouting",
                 "energy_z": "shouting", "gunfire": "gunfire", "explosion": "gunfire",
                 "marker": "marked", "marker_short": "marked"}


@dataclass
class MomentRule:
    id: str                                         # "r004"
    which: str                                      # "always" | "never"
    moments: list[str]
    games: list[str] = field(default_factory=list)  # empty: every game

    def label(self, hit: list[str]) -> str:
        """'r004: Penta kill', 'r006: Baron steal', for Review."""
        return f"{self.id}: " + ", ".join(
            f"{MOMENTS[m.removeprefix('stolen_')].short} steal" if m.startswith("stolen_")
            else MOMENTS[m].short for m in hit)

    def hits(self, moments: set[str]) -> list[str]:
        """Which of its moments the clip has."""
        return matches(self.moments, moments)


def _stolen(names: list[str]) -> list[str]:
    """With "steal", the objectives it's about: 'Baron steals' -> [baron]."""
    return [m for m in names if m in STOLEN] if "steal" in names else []


def matches(names: list[str], moments: set[str]) -> list[str]:
    stolen = _stolen(names)
    hit = [f"stolen_{m}" for m in stolen if f"stolen_{m}" in moments]
    return hit + [m for m in names if m in moments and m != "steal" and m not in stolen]


def said(params: dict) -> str:
    """'never use clips where you die, except ones where something good happens too...'"""
    names = [m for m in params.get("moments") or [] if m in MOMENTS]
    which = params.get("which", "always")
    stolen = _stolen(names)
    parts = ([f"where your side steals {' or '.join(STOLEN[m] for m in stolen)}"] if stolen
             else []) + [MOMENTS[m].clips for m in names if not (stolen and (m == "steal"
                                                                             or m in stolen))]
    text = f"{WHICH.get(which, WHICH['always'])} " + " or ".join(parts)
    if which == "never":
        if set(names) <= BAD_LUCK:
            text += (", except ones where something good happens too (a kill, ace or "
                     "objective) and ones you gave a 👍 or marked")
        else:
            text += ", except ones you gave a 👍 or marked"
    else:
        text += ", whatever their score"
    return text


def league_only(params: dict) -> bool:
    names = [m for m in params.get("moments") or [] if m in MOMENTS]
    return bool(names) and all(MOMENTS[m].source == LEAGUE for m in names)


def rules_of(settings) -> list[MomentRule]:
    """The moment rules a plan is made with, oldest first (kinds.apply puts them in)."""
    return [MomentRule(r.get("id", ""), r.get("which", "always"), list(r.get("moments") or []),
                       list(r.get("games") or []))
            for r in getattr(settings, "moment_rules", None) or []]


def guesses_needed(rules: list[MomentRule]) -> bool:
    return any(MOMENTS[m].source == GUESS for r in rules for m in r.moments if m in MOMENTS)


def guesses(conn: sqlite3.Connection, recording_id: int, clips) -> dict[str, set[str]]:
    """{clip id: the AI's tags}, for the clips it has rated."""
    from ..analysis.ai_rating import notes_for

    return {cid: set(note.tags) for cid, note in notes_for(conn, recording_id, clips).items()}


def found(events: list[tuple[float, dict]], reasons: list[str], tags: set[str] | None,
          marked: bool) -> set[str]:
    """Every moment in a clip: League's ``events`` within it, what was heard (its
    ``reasons``), the AI's ``tags``, and whether you ``marked`` it."""
    out: set[str] = set()
    for _, e in events:
        kind = e.get("kind")
        if kind in ("kill", "first_blood"):
            out.add("kill")
            if kind == "first_blood":
                out.add("first_blood")
        elif kind == "multikill":
            out.add("kill")
            streak = int(e.get("streak") or 2)
            out.update(name for n, name in MULTIKILL.items() if streak >= n)
        elif kind in ("death", "ace", "aced"):
            out.add(kind)
        elif kind == "game_end":
            out.add("victory" if e.get("result") == "win" else "defeat")
        elif counts_for_us(e):
            monster = str(e.get("monster") or "")
            names = (["dragon"] + (["elder_dragon"] if monster == "Elder Dragon" else [])
                     if "Dragon" in monster else [MONSTER[monster]] if monster in MONSTER else [])
            out.update(names)
            if e.get("stolen"):
                out.add("steal")
                out.update(f"stolen_{n}" for n in names if n in STOLEN)
    out.update(HEARD_REASONS[r] for r in reasons if r in HEARD_REASONS)
    if marked:
        out.add("marked")
    out.update(t for t in tags or () if t in MOMENTS and MOMENTS[t].source == GUESS)
    return out


def verdict(rules: list[MomentRule], game: str | None, moments: set[str], *, liked: bool,
            marked: bool) -> tuple[str, str] | None:
    """('in' or 'out', its label) from the newest rule that has a say, or None."""
    for rule in reversed(rules):
        if rule.games and (game or "").casefold() not in {g.casefold() for g in rule.games}:
            continue
        hit = rule.hits(moments)
        if not hit:
            continue
        if rule.which == "never":
            if liked or marked:
                continue          # your own pick wins
            if set(hit) <= BAD_LUCK and moments & GOOD:
                continue          # bad luck in a good fight
            return "out", rule.label(hit)
        return "in", rule.label(hit)
    return None
