"""Effect nudges (3A-3a): an effect suggested again and again and hardly used."""

from __future__ import annotations

import json

import pytest

from ai_editor import effects
from ai_editor.config import local_settings_path
from ai_editor.db import init_db
from ai_editor.effects import Suggestion
from ai_editor.learning import nudges
from ai_editor.recipes.plan import EditPlan, Segment


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    yield connection
    connection.close()


def rendered(conn, n: int, offered: dict, used: dict | None = None, plan: str | None = None):
    conn.execute("INSERT INTO feedback (ts, action, plan_id, detail_json) VALUES "
                 "('now', 'effects_used', ?, ?)",
                 (plan or f"highlights_{n}", json.dumps({"offered": offered, "used": used or {}})))
    conn.commit()


def test_nothing_to_say_before_three_videos(conn, settings):
    assert nudges.effect_nudge(conn, settings) is None
    rendered(conn, 1, {"replay": 8})
    rendered(conn, 2, {"replay": 8})
    assert nudges.effect_nudge(conn, settings) is None


def test_an_effect_suggested_often_and_hardly_used_is_asked_about(conn, settings):
    for n in range(4):
        rendered(conn, n, {"replay": 6, "zoom": 6}, {"zoom": 3})
    found = nudges.effect_nudge(conn, settings)
    assert (found.kind, found.videos, found.suggested, found.used) == ("replay", 4, 24, 0)
    assert found.text == ("In your last 4 videos AI-Editor suggested **slow-motion replays** "
                          "24 times, and you used 0. Change that?")


def test_a_video_rendered_twice_counts_once(conn, settings):
    for _ in range(3):
        rendered(conn, 1, {"replay": 6}, plan="same")
    assert nudges.effect_nudge(conn, settings) is None


def test_keep_as_is_waits_ten_videos(conn, settings):
    for n in range(3):
        rendered(conn, n, {"replay": 6})
    said, same = nudges.answer(conn, settings, "replay", "keep")
    assert "won't ask about slow-motion replays again for 10 videos" in said and same is settings
    for n in range(9):
        rendered(conn, 10 + n, {"replay": 6})
    assert nudges.effect_nudge(conn, settings) is None
    rendered(conn, 30, {"replay": 6})
    assert nudges.effect_nudge(conn, settings).kind == "replay"


def test_the_answers_are_settings_kept_in_the_private_file(conn, settings):
    for n in range(3):
        rendered(conn, n, {"replay": 6, "zoom": 6})
    said, new = nudges.answer(conn, settings, "zoom", "biggest")
    assert new.effects.only_biggest == ["zoom"] and "only suggested on the biggest" in said
    said, new = nudges.answer(conn, new, "replay", "never")
    assert new.effects.not_suggested == ["replay"] and new.effects.only_biggest == ["zoom"]
    assert "Settings → Effects → Don't suggest" in said
    assert "not_suggested" in local_settings_path(settings.source_path).read_text()
    assert nudges.effect_nudge(conn, new) is None   # neither is asked about now


def test_stop_suggesting_takes_it_out_of_reviews_suggestions(conn, settings, monkeypatch):
    from ai_editor.effects import placement

    asked = []
    monkeypatch.setattr(placement, "place", lambda conn, s, plan, on: asked.append(on) or [[]])
    plan = EditPlan("p", "highlights", "Highlights", None, 600, [Segment(1, 0, 30)])
    settings.effects.not_suggested = ["replay"]
    effects.suggestions(conn, settings, plan)
    assert "replay" not in asked[0] and "zoom" in asked[0]


def test_only_the_biggest_moments_caps_it_like_a_style_profile(settings):
    from ai_editor.effects.placement import BIGGEST_PER_MIN, how_many

    assert how_many(BIGGEST_PER_MIN, 600, True) == 3   # about three in 10 minutes


def test_each_render_writes_down_what_was_suggested_and_used(conn, settings, monkeypatch):
    plan = EditPlan("p", "highlights", "Highlights", None, 600, [Segment(1, 0, 30)])
    monkeypatch.setattr(effects, "suggestions", lambda *a: [
        Suggestion("1:10", 1, 10, ["shake", "sfx", "replay"], "", on=True, now=["shake", "sfx"]),
        Suggestion("1:20", 1, 20, ["flash", "zoom"], "")])
    tally = effects.log_used(conn, settings, plan)
    assert tally["offered"]["replay"] == 1 and tally["used"] == {
        "flash": 0, "shake": 1, "sfx": 1, "zoom": 0, "replay": 0}
    row = conn.execute("SELECT plan_id, detail_json FROM feedback WHERE action = 'effects_used'"
                       ).fetchone()
    assert row["plan_id"] == "p" and json.loads(row["detail_json"])["moments"] == 2
    settings.effects.suggest = False
    assert effects.log_used(conn, settings, plan) is None   # nothing suggested: nothing to say
