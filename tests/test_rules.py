"""Your editing tips, as rules (Phase 2H-2)."""

from __future__ import annotations

import pytest

from ai_editor.db import init_db
from ai_editor.recipes.plan import EditPlan, Segment
from ai_editor.rules import kinds, store
from ai_editor.rules.kinds import Rule
from ai_editor.rules.understand import question, schema, to_rule, understand

GAMES = ["League of Legends", "The Blood of Dawnwalker", "Wardogs"]


# --- What each kind of rule changes, and says ---------------------------------------------------


def test_clip_length_for_highlights_and_shorts(settings):
    rule = Rule("clip_length", {"min_seconds": 20, "max_seconds": 40}, ["League of Legends"],
                ["shorts"])
    assert rule.said() == "League of Legends Shorts: clips 20–40 seconds long."
    shorts = kinds.apply(settings, [rule], "shorts").shorts
    assert (shorts.min_length_sec, shorts.max_length_sec) == (20, 40)
    hl = kinds.apply(settings, [Rule("clip_length", {"max_seconds": 20})], "highlights")
    assert hl.highlights.max_clip_sec == 20 and hl.clips.min_length_sec < 20
    assert settings.highlights.max_clip_sec == 50          # your own settings: untouched
    assert Rule("clip_length", {"max_seconds": 20}).said() == \
        "Every video: clips 20 seconds long at most."


def test_part_length_keeps_its_range_around_it(settings):
    lp = kinds.apply(settings, [Rule("video_length", {"minutes": 40})], "letsplay").lets_play
    assert lp.target_min == 40 and lp.normal_range_min[0] < 40 < lp.normal_range_min[1]
    lp.check_consistency()
    hl = kinds.apply(settings, [Rule("video_length", {"minutes": 12})], "highlights")
    assert hl.highlights.target_length_min == 12


def test_teaser_order_quality_and_silence(settings):
    s = kinds.apply(settings, [Rule("teaser", {"on": False})], "highlights")
    assert s.highlights.hook is False
    s = kinds.apply(settings, [Rule("teaser", {"on": True, "seconds": 8})], "highlights")
    assert s.highlights.hook and s.highlights.hook_seconds == (5.0, 11.0)
    assert kinds.apply(settings, [Rule("teaser", {"on": False})], "shorts").shorts.hook is False
    s = kinds.apply(settings, [Rule("clip_order", {"order": "chronological"})], "highlights")
    assert s.highlights.ordering == "chronological"
    s = kinds.apply(settings, [Rule("quality_bar", {"level": 0.75})], "highlights")
    assert s.highlights.min_clip_score == 0.75
    s = kinds.apply(settings, [Rule("silence", {"seconds": 10})], "letsplay")
    assert s.lets_play.dead_air_sec == 10
    # A kind of video a rule doesn't work on: left as it is.
    assert kinds.apply(settings, [Rule("silence", {"seconds": 10})], "highlights") == settings


def test_captions_and_effects_only_how_never_whether(settings):
    s = kinds.apply(settings, [Rule("caption_look", {"size_scale": 1.5, "words": 2})], "shorts")
    assert s.captions.shorts_size == round(88 * 1.5) and s.captions.shorts_words == 2
    assert s.shorts.captions is False and s.captions.highlights is False   # still off
    s = kinds.apply(settings, [Rule("effect_amount", {"per_minute": 1, "effect": "zoom"})],
                    "highlights")
    assert s.effects.kind_per_min == {"zoom": 1.0} and s.effects.highlights == []
    assert Rule("effect_amount", {"per_minute": 1, "effect": "zoom"}).said() == \
        "Every video: at most 1 zoom a minute (when they're on)."


def test_your_three_tips_can_be_switched_per_game(settings):
    rule = Rule("switch", {"switch": "game_under_voice", "on": False}, ["League of Legends"])
    assert rule.said() == "League of Legends, every video: not: the game is kept under your voice."
    assert kinds.apply(settings, [rule], "letsplay").render.game_under_voice is False
    s = kinds.apply(settings, [Rule("switch", {"switch": "whole_fights", "on": False})], "shorts")
    assert s.clips.keep_fights_whole is False


def test_a_rule_applies_to_its_games_and_videos_only():
    rule = Rule("clip_length", {"max_seconds": 20}, ["League of Legends"], ["highlights"])
    assert rule.applies_to("league of legends", "highlights")
    assert not rule.applies_to("Wardogs", "highlights")
    assert not rule.applies_to("League of Legends", "shorts")
    assert not rule.applies_to(None, "highlights")
    assert Rule("clip_length", {"max_seconds": 20}).applies_to(None, "shorts")
    assert not Rule("clip_length", {"max_seconds": 20}).applies_to(None, "letsplay")


# --- From the AI's form to a rule -----------------------------------------------------------


def test_the_ais_form_becomes_a_rule_and_only_its_own_values_are_kept():
    found = to_rule({"kind": "clip_length", "games": ["league of legends"], "videos": ["shorts"],
                     "max_seconds": 40, "min_seconds": 20, "minutes": 5, "on": True}, GAMES)
    assert found.rule.params == {"min_seconds": 20.0, "max_seconds": 40.0}
    assert found.rule.games == ["League of Legends"]            # the library's spelling
    assert found.message == "League of Legends Shorts: clips 20–40 seconds long."
    switch = to_rule({"kind": "switch", "games": [], "videos": [],
                      "which_switch": "game_under_voice", "on": True}, GAMES)
    assert switch.rule.said() == "Every video: the game is kept under your voice."


def test_what_isnt_a_rule_says_why():
    no_number = to_rule({"kind": "clip_length", "games": [], "videos": []}, GAMES)
    assert no_number.rule.is_note and "with a number" in no_number.message
    faster = to_rule({"kind": "speed_up", "games": [], "videos": [], "why_note": "horse rides"},
                     GAMES)
    assert not faster.savable and "never speeds" in faster.message
    on = to_rule({"kind": "effects_on", "games": [], "videos": []}, GAMES)
    assert on.rule.is_note and on.savable and "tick them in Review" in on.message
    wrong_video = to_rule({"kind": "silence", "games": [], "videos": ["shorts"], "seconds": 5},
                          GAMES)
    assert wrong_video.rule.is_note and "Let's Plays" in wrong_video.message
    other = to_rule({"kind": "note", "games": [], "videos": [], "why_note": "more jokes"}, GAMES)
    assert other.rule.said() == "📝 Note: more jokes" and "won't change the edit" in other.message


def test_the_question_lists_every_kind_and_the_form_matches(settings, monkeypatch):
    asked = question('Keep "League" clips short', GAMES)
    assert all(f"- {k}:" in asked for k in kinds.KINDS) and "League of Legends" in asked
    form = schema(GAMES)
    assert form["properties"]["games"]["items"]["enum"] == GAMES
    assert set(form["required"]) == {"kind", "games", "videos"}
    from ai_editor import llm

    monkeypatch.setattr(llm, "ask", lambda *a, **k: {"kind": "teaser", "games": [],
                                                      "videos": ["highlights"], "on": False})
    assert understand(settings, "No teaser in highlights", GAMES).message == \
        "Every game's highlights: no opening teaser."


# --- Kept, switched, disagreeing --------------------------------------------------------------


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    yield connection
    connection.close()


def test_rules_are_kept_switched_and_deleted(conn):
    first = store.add(conn, "League clips under 20 s",
                      Rule("clip_length", {"max_seconds": 20}, ["League of Legends"],
                           ["highlights"]))
    second = store.add(conn, "Actually 25", Rule("clip_length", {"max_seconds": 25},
                                                 [], ["highlights"]))
    note = store.add(conn, "More jokes", Rule("note", {}, why_note="more jokes"))
    assert (first, second, note) == ("r001", "r002", "r003")
    assert [s.rule_id for s in store.matching(conn, "League of Legends", "highlights")] == \
        ["r001", "r002"]                                       # oldest first: the newer wins
    assert store.clashes(store.every(conn)) == {"r001": "r002"}
    store.switch(conn, "r002", False)
    assert [s.rule_id for s in store.matching(conn, "League of Legends", "highlights")] == ["r001"]
    assert store.clashes(store.every(conn)) == {}
    assert store.delete(conn, "r001") and store.get(conn, "r001") is None
    assert store.add(conn, "again", Rule("teaser", {"on": False})) == "r004"


def test_a_plan_keeps_its_rules_and_they_win_over_the_style_profile(conn, settings):
    from ai_editor.style.apply import styled

    store.add(conn, "League clips under 20 s",
              Rule("clip_length", {"max_seconds": 20}, ["League of Legends"], ["highlights"]))
    plan = EditPlan("hl", "highlights", "t", "League of Legends", 600, [Segment(1, 0, 30)])
    plan.source = {"style": {"id": 1, "name": "League", "values": {"cuts_per_min": 2.3}}}
    assert styled(settings, plan).highlights.max_clip_sec == pytest.approx(28.7, abs=0.1)
    used, found = store.with_rules(conn, settings, "League of Legends", "highlights")
    store.stamp(plan, found)
    assert styled(settings, plan).highlights.max_clip_sec == 20    # the rule wins
    store.switch(conn, "r001", False)                                # changed later:
    assert styled(settings, plan).highlights.max_clip_sec == 20    # the plan keeps its copy
    assert store.summary(plan) == "Rules: r001 League of Legends highlights: clips 20 seconds long at most."


def test_making_a_plan_uses_and_stamps_the_rules(conn, settings):
    from ai_editor.app.tasks import _stamp, _with_style

    store.add(conn, "No teaser", Rule("teaser", {"on": False}, [], ["highlights"]))
    used, style = _with_style(conn, settings, None, "highlights", "Wardogs")
    assert used.highlights.hook is False and settings.highlights.hook is True
    said = []

    class Report:
        def say(self, text):
            said.append(text)

    plan = EditPlan("hl_x", "highlights", "t", "Wardogs", 600, [Segment(1, 0, 30)])
    _stamp(conn, settings, [plan], style, Report())
    assert plan.source["rules"][0]["id"] == "r001"
    assert said == ["Rules: r001 Every game's highlights: no opening teaser."]


def test_the_rules_tab_lists_newest_first_and_says_which_wins():
    from ai_editor.app.rules_tab import choices, rows

    saved = [store.Saved(1, "r001", "under 20", Rule("clip_length", {"max_seconds": 20}), True,
                         "now"),
             store.Saved(2, "r002", "under 25", Rule("clip_length", {"max_seconds": 25}), True,
                         "now")]
    table = rows(saved)
    assert [r[0] for r in table] == ["r002", "r001"]
    assert table[0][1] == "✅ On"           # 19 Oct: "so I know if the rule is on"
    assert "⚠ r002 (newer) says otherwise" in table[1][2]
    assert choices(saved)[0][1] == "r002"


def test_a_switch_named_without_on_or_off_means_on():
    """Gemma, 19 Oct, on "Make sure the video sound is never over my voice": the right
    switch, no on. All three of the creator's tips came back like that."""
    found = to_rule({"kind": "switch", "games": [], "videos": [], "which_switch": "game_under_voice",
                     "why_note": "Ensure video sound is never over the streamer's voice"}, GAMES)
    assert not found.rule.is_note and found.rule.params == {"switch": "game_under_voice", "on": True}
    assert found.message == "Every video: the game is kept under your voice."
    off = to_rule({"kind": "switch", "games": [], "videos": [], "which_switch": "whole_fights",
                   "on": False}, GAMES)
    assert off.rule.params["on"] is False
    # Which one left out, but named in why_note (Gemma, 2 times in 5):
    named = to_rule({"kind": "switch", "games": [], "videos": [], "why_note": "The tip wants the "
                     "action within the clip, which corresponds to the whole_fights switch."}, GAMES)
    assert named.rule.params == {"switch": "whole_fights", "on": True}


def test_a_choice_left_out_is_asked_again_on_its_own(settings, monkeypatch):
    """"Suggest where an effect can work and which effect": switch, which one left out."""
    from ai_editor import llm

    asked = []

    def ask(settings, system, prompt, *, schema, **_):
        asked.append(schema)
        if len(asked) == 1:
            return {"kind": "switch", "games": [], "videos": [],
                    "why_note": "The tip asks the AI to suggest where and which effects to use."}
        return {"which_switch": "suggest_effects"}

    monkeypatch.setattr(llm, "ask", ask)
    found = understand(settings, "Suggest where an effect can work and which effect", GAMES)
    assert found.message == "Every video: Review suggests effects for the big moments."
    assert asked[1]["required"] == ["which_switch"]
    # A length left out is never asked for: it would be a number you didn't give.
    asked.clear()
    monkeypatch.setattr(llm, "ask", lambda *a, **k: asked.append(1) or
                        {"kind": "clip_length", "games": [], "videos": []})
    assert understand(settings, "Short clips please", GAMES).rule.is_note and len(asked) == 1
