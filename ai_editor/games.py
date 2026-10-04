"""The games AI-Editor knows about.

For now this is only names and aliases, so a recording can be tagged with a
game at import (spec section 7.2). Full game profiles -- signal weights,
downtime to trim, detection templates -- arrive as plugins in later phases
(spec section 8). Any other game still works with general detection; it just
gets no game-specific extras (manual chapter 26).
"""

from __future__ import annotations

import re

# Canonical name -> words that identify it in a filename or stream title.
# Aliases are matched as whole words, so "lol" will not match inside "lollipop".
KNOWN_GAMES: dict[str, tuple[str, ...]] = {
    "The Blood of Dawnwalker": ("dawnwalker",),
    "Escape from Tarkov": ("tarkov", "eft"),
    "League of Legends": ("league of legends", "league", "lol"),
    "Wardogs": ("wardogs",),
}


# What makes a good moment in each game, and what's downtime (spec section 8),
# in words the local AI reads before it rates a clip (analysis/ai_rating.py).
GAME_NOTES: dict[str, str] = {
    "League of Legends": (
        "Good: teamfights, kills and multikills, outplays, Baron/Dragon/Herald fights and "
        "steals, turret dives, aces, a big swing in a fight, deaths with a big reaction. "
        "The gameplay itself is often the highlight even when nobody talks. "
        "Downtime: champion select, the shop, the loading screen, waiting to respawn, "
        "laning with nothing happening, the post-game lobby and stats."),
    "Wardogs": (
        "A 100-player tactical shooter: three teams fight over a control zone, with "
        "vehicles and helicopters. Good: firefights, kills, holding or taking the zone, "
        "vehicle chaos, big explosions, funny moments with teammates. "
        "Downtime: loadout and shop menus, waiting to redeploy, long drives or flights "
        "with no action, the end-of-match screen."),
    "Escape from Tarkov": (
        "Long quiet stretches, then sudden fights. Good: firefights, tense whispering "
        "before shooting, kills, deaths with a reaction, extracting. "
        "Downtime: stash and inventory, flea market, hideout, raid loading, looting and "
        "walking with no talking."),
    "The Blood of Dawnwalker": (
        "A story-driven dark fantasy RPG. Good: boss fights, deaths with a reaction, big "
        "story moments and choices, funny commentary. "
        "Downtime: menus, inventory, the map, crafting, loading, long travel."),
}


def game_notes(game: str | None) -> str:
    return GAME_NOTES.get(canonical_game(game), "") if game else ""


def _normalise(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def suggest_game(text: str) -> str | None:
    """Guess the game from a filename or stream title. None if unsure."""
    haystack = _normalise(text)
    matches = [
        name
        for name, aliases in KNOWN_GAMES.items()
        if any(_normalise(alias) in haystack for alias in aliases)
    ]
    # Two different games in one title is ambiguous; better to ask than guess.
    return matches[0] if len(matches) == 1 else None


def game_for_scene(scene: str | None, overrides: dict[str, str] | None = None) -> str | None:
    """Which game an OBS scene shows: from Settings first, then from its name.

    None for scenes that aren't a game, such as "Starting Soon" or "BRB".
    """
    if not scene:
        return None
    for name, game in (overrides or {}).items():
        if name.strip().lower() == scene.strip().lower():
            return canonical_game(game)
    return suggest_game(scene)


def canonical_game(name: str) -> str:
    """Map "tarkov" or "the blood of dawnwalker" to the known spelling.

    Unknown games are kept exactly as typed.
    """
    cleaned = name.strip()
    lowered = _normalise(cleaned)
    for canonical, aliases in KNOWN_GAMES.items():
        if lowered == _normalise(canonical) or any(lowered == _normalise(a) for a in aliases):
            return canonical
    return cleaned
