"""Using a style profile on a video (Phase 2G-2)."""

from __future__ import annotations

import pytest

from ai_editor.db import init_db
from ai_editor.recipes.plan import EditPlan, Segment
from ai_editor.style import apply as A
from ai_editor.style import profiles

# What the creator's favourite League YouTuber's first video measured (11 Oct).
LEAGUE = {"cuts_per_min": 2.3, "dead_air_sec": 12.1, "hook_sec": 0.0, "zooms_per_min": 0.5,
          "zoom_strength": 0.25, "sfx_per_min": 0.1, "caption_size": 4.2,
          "caption_position": 22.8, "caption_words": 1.0}


def test_cuts_per_minute_set_how_long_highlight_clips_run(settings):
    assert A.clip_lengths(settings, 0.0) is None
    # Clips mostly run to their longest, so that's set just over the average wanted.
    shortest, longest = A.clip_lengths(settings, 2.3)          # about 26 s
    assert shortest == settings.clips.min_length_sec and longest == pytest.approx(28.7, abs=0.1)
    shortest, longest = A.clip_lengths(settings, 8.0)          # a fast style: 7.5 s
    assert longest == pytest.approx(8.25) and shortest == pytest.approx(7.25)


def test_a_profile_changes_a_copy_of_the_settings_for_one_kind_of_video(settings):
    before = settings.model_dump()
    hl = A.apply(settings, LEAGUE, "highlights")
    assert hl.highlights.max_clip_sec == pytest.approx(28.7, abs=0.1)
    assert hl.highlights.hook is False                         # 0 s: no teaser
    assert hl.effects.kind_per_min == {"zoom": 0.5, "sfx": 0.1}
    assert hl.effects.zoom_strength == 0.25
    assert hl.captions.size == round(0.042 / 1.3 * 1080)       # 35 px on 1080
    assert hl.captions.position.highlights == pytest.approx(0.228)
    assert hl.lets_play.dead_air_sec == settings.lets_play.dead_air_sec   # Let's Plays only
    lp = A.apply(settings, LEAGUE, "letsplay")
    assert lp.lets_play.dead_air_sec == pytest.approx(12.1)
    assert lp.highlights.max_clip_sec == settings.highlights.max_clip_sec
    assert lp.captions.position.lets_play == pytest.approx(0.228)
    short = A.apply(settings, {**LEAGUE, "hook_sec": 10}, "shorts")
    assert short.captions.shorts_words == 1 and short.highlights.hook == settings.highlights.hook
    teaser = A.apply(settings, {**LEAGUE, "hook_sec": 10}, "highlights").highlights
    assert teaser.hook and teaser.hook_seconds == (7.0, 13.0)
    assert A.apply(settings, {"dead_air_sec": 1.0}, "letsplay").lets_play.dead_air_sec == 5.0
    assert settings.model_dump() == before                     # the creator's own: untouched
    # Effects stay as switched: a profile never switches one on.
    assert hl.effects.highlights == settings.effects.highlights


def test_a_plan_keeps_its_profiles_values_and_is_made_again_with_them(settings):
    plan = EditPlan("hl", "highlights", "t", "League of Legends", 600, [Segment(1, 0, 30)])
    assert A.styled(settings, plan) is settings
    assert A.summary(plan) is None
    conn = init_db(settings.db_path)
    pid = profiles.create(conn, "League of legends")
    profiles.save(conn, pid, games=["League of Legends"], recipes=["highlights"], values=LEAGUE)
    A.stamp(plan, profiles.load(conn, pid), settings)
    profiles.save(conn, pid, games=[], recipes=[], values={**LEAGUE, "cuts_per_min": 9})
    assert plan.source["style"]["values"]["cuts_per_min"] == 2.3   # a copy, as made
    assert A.styled(settings, plan).highlights.max_clip_sec == pytest.approx(28.7, abs=0.1)
    said = A.summary(plan)
    assert said.startswith("Style: League of legends, clips about 26 s, no teaser")
    assert "at most 0.5 zooms a minute (1.25x)" in said
    conn.close()


def test_the_profile_for_the_game_and_kind_of_video_is_picked_by_itself(settings):
    conn = init_db(settings.db_path)
    league = profiles.create(conn, "League")
    profiles.save(conn, league, games=["League of Legends"], recipes=["highlights", "shorts"],
                  values={})
    loose = profiles.create(conn, "Not ticked")      # no games or videos ticked: never by itself
    assert A.matching(conn, settings, "League of Legends", "highlights") == league
    assert A.matching(conn, settings, "league of legends", "shorts") == league
    assert A.matching(conn, settings, "League of Legends", "letsplay") is None
    assert A.matching(conn, settings, "Wardogs", "highlights") is None
    assert A.matching(conn, settings, None, "highlights") is None
    assert loose != league
    conn.close()
