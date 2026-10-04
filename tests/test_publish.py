"""Upload text and thumbnails: chapters that match the video, titles in the creator's style."""

from __future__ import annotations

import pytest

from ai_editor import llm, publish
from ai_editor.config import Publish as PublishSettings
from ai_editor.db import init_db
from ai_editor.recipes.plan import EditPlan, Segment, load_plan, save_plan


def highlight_plan(teaser_sec: float = 8.0) -> EditPlan:
    segments = [Segment(1, 500, 500 + teaser_sec, kind="teaser", clip_id="c3")]
    for n, start in enumerate((100, 200, 300, 500)):
        segments.append(Segment(1, start, start + 40, clip_id=f"c{n}"))
    return EditPlan("highlights_test_1", "highlights", "Stream highlights", "Wardogs", 600,
                    segments)


def letsplay_plan() -> EditPlan:
    # Part 1: twelve 1-minute pieces; part 2: two.
    segments = [Segment(1, n * 100, n * 100 + 60, kind="piece", part=1) for n in range(12)]
    segments += [Segment(1, 2000 + n * 100, 2060 + n * 100, kind="piece", part=2)
                 for n in range(2)]
    return EditPlan("letsplay_test_1", "letsplay", "Dawnwalker EP 3", "The Blood of Dawnwalker",
                    1800, segments)


# --- chapters -------------------------------------------------------------------------


def test_a_highlight_video_gets_a_chapter_per_clip_the_short_teaser_joining_the_first():
    found = publish.sections(highlight_plan(teaser_sec=8.0), 60, 300)
    assert [round(s.start) for s in found] == [0, 48, 88, 128]
    assert [p.kind for p in found[0].pieces] == ["teaser", "clip"] and found[0].name is None


def test_a_long_teaser_is_its_own_chapter_called_intro():
    found = publish.sections(highlight_plan(teaser_sec=12.0), 60, 300)
    assert found[0].name == "Intro" and len(found) == 5


def test_a_lets_play_part_gets_a_chapter_about_every_five_minutes():
    from ai_editor.render.parts import part_plan

    found = publish.sections(part_plan(letsplay_plan(), 1), 60, 300)
    assert [round(s.start) for s in found] == [0, 300, 600]
    assert all(len(s.pieces) == 5 for s in found[:2])


def test_chapter_times_are_whole_frames_like_the_render():
    plan = highlight_plan()
    plan.segments[1].src_out = 140.0083  # not a whole number of frames at 60 fps
    times = [t for t, _ in publish.placed(plan, 60)]
    assert times[2] == pytest.approx(48.0)


def test_youtube_chapter_format_and_names_without_times():
    assert publish.clock(0) == "0:00" and publish.clock(245) == "4:05"
    assert publish.clock(3723) == "1:02:03"
    assert publish.chapter_name("0:00 - Post-game analysis") == "Post-game analysis"
    assert publish.chapter_name("12:25 Final fight") == "Final fight"
    assert publish.chapter_name("Baron at 20:00") == "Baron at 20:00"


# --- titles and text ---------------------------------------------------------------------


def test_lets_play_titles_keep_the_series_pattern_even_when_the_ai_repeats_it(settings):
    plan = letsplay_plan()
    titles = publish.full_titles(settings, plan, [
        "Caring for Mum",
        "The Blood of Dawnwalker - EP 3 Part 2: The Blood of Dawnwalker - EP 3 Part 2: Fishing",
        "Caring for Mum."], part=2, episode=3)
    assert titles == ["The Blood of Dawnwalker - EP 3 Part 2: Caring for Mum",
                      "The Blood of Dawnwalker - EP 3 Part 2: Fishing"]


def test_the_title_pattern_must_have_room_for_the_ais_part():
    with pytest.raises(ValueError):
        PublishSettings(lets_play_title="{game} EP {episode}")
    with pytest.raises(ValueError):
        PublishSettings(lets_play_title="{game} {season}: {subtitle}")


def made(chapters=((0, "Intro"), (10, "Zone fight"), (58, "Helicopter crash"))) -> publish.Publish:
    return publish.Publish(["Wardogs Highlights - Holding the Zone"], "We held the zone.",
                           ["Wardogs", "highlights"], list(chapters), [], "abc", "2026-10-04")


def test_the_description_is_ready_to_paste_with_chapters_and_footer(settings):
    settings.publish.description_footer = "Live on Twitch: twitch.tv/example"
    text = publish.description_text(settings, made())
    assert text == ("We held the zone.\n\n0:00 Intro\n0:10 Zone fight\n0:58 Helicopter crash\n\n"
                    "Live on Twitch: twitch.tv/example")
    # YouTube ignores fewer than three chapters, so they're left out.
    assert "0:00" not in publish.description_text(settings, made(chapters=((0, "A"), (30, "B"))))


def test_your_changes_are_kept_over_the_ais(settings, tmp_path):
    text = made()
    text.edited = {"title": "My title", "description": "My words", "tags": ["mine"]}
    again = publish.Publish.from_dict(text.as_dict())
    assert again.title == "My title" and publish.description_text(settings, again) == "My words"
    saved = publish.write_text_beside(settings, again, tmp_path / "video.mp4")
    content = saved.read_text(encoding="utf-8")
    assert saved.name == "video.txt" and "My title" in content and "mine" in content
    assert "Holding the Zone" not in content  # the chosen title replaces the ideas


def test_text_written_for_an_older_version_of_the_video_is_flagged():
    plan = highlight_plan()
    text = made()
    text.fingerprint = publish.fingerprint(plan)
    assert not publish.is_stale(plan, None, text)
    plan.segments.pop()
    assert publish.is_stale(plan, None, text)


# --- the whole thing, with the AI faked -------------------------------------------------


def test_prepare_names_only_the_real_chapters_and_keeps_it_with_the_plan(settings, monkeypatch):
    conn = init_db(settings.db_path)
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, game, "
                 "duration_sec, imported_at, analysis_status) VALUES (1, 'h', 'local_obs', "
                 "'x.mkv', 'Wardogs', 7200, 'now', 'complete')")
    conn.commit()
    asked = {}

    def fake_ask(settings_, system, prompt, *, schema, images=None, **_):
        asked["prompt"], asked["schema"] = prompt, schema
        return {"titles": ["Wardogs Highlights - Holding the Zone", "Wardogs Highlights - Chaos"],
                "description": "We held the zone.", "tags": ["highlights", "Wardogs Highlights"],
                "chapters": ["0:00 - Zone fight", "Helicopter crash", "Last stand", "Win"]}

    monkeypatch.setattr(llm, "start", lambda s: "0.35.1")
    monkeypatch.setattr(llm, "has_model", lambda s, name=None: True)
    monkeypatch.setattr(llm, "unload", lambda s: None)
    monkeypatch.setattr(llm, "ask", fake_ask)
    monkeypatch.setattr(publish, "thumbnails", lambda *a, **k: [])
    plan = highlight_plan(teaser_sec=12.0)
    result = publish.prepare(conn, settings, plan)
    assert asked["schema"]["properties"]["chapters"]["minItems"] == 4  # the Intro isn't asked
    assert "1. [0:12]" in asked["prompt"]
    assert [name for _, name in result.chapters] == ["Intro", "Zone fight", "Helicopter crash",
                                                     "Last stand", "Win"]
    assert result.tags[0] == "Wardogs" and not publish.is_stale(plan, None, result)

    plan.publish[publish.key_of(None)] = result.as_dict()
    save_plan(conn, plan)
    reloaded, _ = load_plan(conn, plan.plan_id)
    assert publish.saved(reloaded, None).titles[0] == "Wardogs Highlights - Holding the Zone"
    assert publish.saved(reloaded, 2) is None
    conn.close()


def test_thumbnail_moments_are_the_strongest_seconds_spread_out(settings):
    import numpy as np

    conn = init_db(settings.db_path)
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                 "duration_sec, imported_at) VALUES (1, 'h', 'local_obs', 'x.mkv', 1000, 'now')")
    hype = np.zeros(1000)
    hype[120], hype[121], hype[310], hype[505] = 1.0, 0.95, 0.8, 0.99  # 505: only the teaser
    conn.executemany("INSERT INTO signals (recording_id, t_sec, name, value) VALUES (1, ?, "
                     "'hype', ?)", [(t, float(v)) for t, v in enumerate(hype)])
    conn.commit()
    plan = highlight_plan()
    plan.segments = [Segment(1, 500, 510, kind="teaser")] + [
        Segment(1, 100, 140), Segment(1, 300, 340)]
    moments = publish.thumbnail_moments(conn, plan, count=3)
    assert moments[:2] == [(1, 120.5), (1, 310.5)]  # 121 is too close to 120; 505 is the teaser
    conn.close()
