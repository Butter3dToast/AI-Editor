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
