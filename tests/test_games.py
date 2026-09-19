"""Game name suggestion and normalisation."""

from __future__ import annotations

import pytest

from ai_editor.games import canonical_game, suggest_game


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Lets Play - The Blood Of DawnWalker - EP 1", "The Blood of Dawnwalker"),
        ("2026-09-14_tarkov", "Escape from Tarkov"),
        ("EFT raid night", "Escape from Tarkov"),
        ("League of Legends ranked", "League of Legends"),
        ("lol_stream_0914", "League of Legends"),
        ("WARDOGS chaos", "Wardogs"),
        ("2026-09-19 22-14-03", None),
    ],
)
def test_suggest_game(text, expected):
    assert suggest_game(text) == expected


def test_aliases_match_whole_words_only():
    assert suggest_game("lollipop_review") is None
    assert suggest_game("leftovers") is None  # contains "eft" but isn't Tarkov


def test_two_games_in_one_title_is_ambiguous():
    assert suggest_game("tarkov then league") is None


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("tarkov", "Escape from Tarkov"),
        ("the blood of dawnwalker", "The Blood of Dawnwalker"),
        ("LoL", "League of Legends"),
        ("Hollow Knight", "Hollow Knight"),
    ],
)
def test_canonical_game(typed, expected):
    assert canonical_game(typed) == expected
