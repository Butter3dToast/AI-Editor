"""Shorts: picking the moments, the tall picture, and the word-by-word captions."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ai_editor.analysis.ai_rating import Note
from ai_editor.analysis.captions import Word
from ai_editor.config import Box, RenderPreset, Shorts
from ai_editor.recipes import shorts
from ai_editor.recipes.highlights import Candidate
from ai_editor.recipes.plan import EditPlan, is_short, used_in
from ai_editor.render.captions import ass_colour, phrases, short_document
from ai_editor.render.final import vertical_of, video_path
from ai_editor.render.vertical import Vertical, crop_window, picture_graph

VERTICAL = RenderPreset(width=1080, height=1920, fps=60, bitrate="12M")
DAY = datetime(2026, 10, 2, tzinfo=timezone.utc)


# --- the tall picture -------------------------------------------------------------------


def test_the_crop_is_the_middle_of_the_screen_never_past_an_edge():
    assert crop_window((1920, 1080), 9 / 16, 0.5) == (608, 1080, 656, 0)
    assert crop_window((1920, 1080), 9 / 16, 0.0)[2] == 0          # pushed to the left edge
    assert crop_window((1920, 1080), 9 / 16, 1.0)[2] == 1920 - 608  # ...and the right


def test_each_layout_makes_a_1080_by_1920_picture():
    crop = picture_graph(Vertical("crop"), (1920, 1080), VERTICAL, finish=["format=yuv420p"])
    assert "crop=608:1080:656:0,scale=1080:1920" in crop and crop.endswith("[v]")
    fit = picture_graph(Vertical("fit"), (1920, 1080), VERTICAL, finish=["format=yuv420p"])
    # Converted before the split: GPU-decoded pictures came out green otherwise.
    assert "format=yuv420p,split=2" in fit and "boxblur" in fit and "overlay" in fit
    cam = picture_graph(Vertical("facecam_top", facecam=Box(x=0.0, y=0.7, w=0.2, h=0.3)),
                        (1920, 1080), VERTICAL, finish=[])
    assert "crop=384:324:0:756" in cam and "vstack" in cam and "1080:634" in cam


def test_the_layout_follows_the_game_and_a_facecam_once_marked(settings):
    plan = EditPlan("shorts_x_1", "shorts", "Short", "League of Legends", 30)
    assert vertical_of(settings, plan).layout == "crop"
    plan.game = "The Blood of Dawnwalker"
    assert vertical_of(settings, plan).layout == "fit"
    plan.source = {"layout": "crop"}  # switched for this one Short
    assert vertical_of(settings, plan).layout == "crop"
    plan.source = {"layout": "facecam_top"}  # but no facecam marked yet
    assert vertical_of(settings, plan).layout == "crop"
    settings.shorts.facecam["League of Legends"] = Box(x=0.0, y=0.7, w=0.2, h=0.3)
    plan.game, plan.source = "League of Legends", {}
    assert vertical_of(settings, plan).layout == "facecam_top"


def test_a_facecam_box_must_fit_in_the_picture():
    with pytest.raises(ValueError):
        Box(x=0.9, y=0.0, w=0.2, h=0.2)
    assert Shorts(facecam={"Wardogs": {"x": 0, "y": 0, "w": 0.2, "h": 0.2}}).layout_for(
        "Wardogs") == "facecam_top"


def test_shorts_have_their_own_folder(settings):
    plan = EditPlan("shorts_wardogs_2026-10-04_1", "shorts", "Short", "Wardogs", 30)
    assert video_path(settings, plan, captions=True).parent.name == "shorts"


# --- captions: a few words, the one being said lit up -----------------------------------


def words(*spec):
    return [Word(text, start, end, 1.0) for text, start, end in spec]


def test_words_are_grouped_as_they_are_said():
    said = words(("no", 0.0, 0.2), ("way", 0.25, 0.5), ("he", 0.55, 0.7), ("flashed", 0.75, 1.1),
                 ("in.", 1.15, 1.3), ("Wow", 2.5, 2.8))
    assert [[w.text for w in g] for g in phrases(said, 3)] == [
        ["no", "way", "he"], ["flashed", "in."], ["Wow"]]  # three at most; full stop; pause


def test_each_word_is_lit_while_it_is_said(settings):
    said = words(("no", 10.0, 10.2), ("way", 10.3, 10.6), ("he", 10.7, 10.9))
    doc = short_document(said, 9.0, 20.0, width=1080, height=1920, style=settings.captions,
                         zone=settings.shorts.safe_zone())
    events = [line for line in doc.splitlines() if line.startswith("Dialogue")]
    lit = ass_colour("#FFD400")
    assert lit == "&H0000D4FF" and len(events) == 3
    assert events[0].startswith("Dialogue: 0,0:00:01.00,0:00:01.30,")  # from the Short's start
    assert f"{{\\c{lit}&}}way" in events[1] and events[1].count(lit) == 1
    # Above the platforms' buttons: the bottom safe zone plus a gap.
    style = next(line for line in doc.splitlines() if line.startswith("Style: Short"))
    assert style.split(",")[-2] == str(round(1920 * (0.26 + 0.06)))


# --- choosing the moments ----------------------------------------------------------------


def cand(clip_id, start, score=0.5, length=40.0, liked=False):
    c = Candidate(clip_id, 1, start, start + length, score, int(start + 20),
                  (int(start + 15), int(start + 25)), [], DAY, False, liked=liked)
    c.src_in, c.src_out = start, start + length
    return c


def row(signals=None, used=None):
    return {"signals_json": json.dumps(signals or {}), "used_in_json": used}


def note(clip_id, rating, alone=True):
    return Note(clip_id, 1, 0, 0, rating, f"summary {clip_id}", "", [], alone, "m", 1)


def test_marked_moments_first_then_the_ais_stand_alone_picks(settings):
    settings.shorts.per_recording = 3
    cands = [cand("a", 0), cand("b", 100), cand("c", 200), cand("d", 300), cand("e", 400),
             cand("f", 500, liked=True)]
    clips = {"a": row(), "b": row({"marker_short": 1.0}), "c": row(), "d": row(),
             "e": row(used=json.dumps(["shorts_wardogs_1"])), "f": row()}
    notes = {"a": note("a", 9), "c": note("c", 6), "d": note("d", 10, alone=False),
             "e": note("e", 10), "f": note("f", 4)}
    picks, rated = shorts.choose(cands, clips, notes, settings)
    assert rated and [(p.candidate.clip_id, p.why) for p in picks] == [
        ("b", "marked"), ("f", "liked"), ("a", "ai")]  # d doesn't stand alone; e is a Short


def test_every_marked_moment_is_suggested_even_past_the_number(settings):
    settings.shorts.per_recording = 2
    cands = [cand(x, n * 100) for n, x in enumerate("abc")] + [cand("z", 900)]
    clips = {x: row({"marker_short": 1.0}) for x in "abc"} | {"z": row()}
    picks, _ = shorts.choose(cands, clips, {"z": note("z", 10)}, settings)
    assert [p.candidate.clip_id for p in picks] == ["a", "b", "c"]


def test_without_the_ais_verdicts_the_best_scores_are_used(settings):
    cands = [cand("a", 0, 0.4), cand("b", 100, 0.9), cand("short", 200, 0.99, length=5)]
    picks, rated = shorts.choose(cands, {k: row() for k in ("a", "b", "short")}, {}, settings)
    assert not rated and [p.candidate.clip_id for p in picks] == ["b", "a"]  # 5 s is too short


def test_shorts_and_long_videos_use_clips_up_separately():
    used = json.dumps(["highlights_wardogs_1", "shorts_wardogs_2026-10-04_1"])
    assert used_in(used, shorts=False) == ["highlights_wardogs_1"]
    assert used_in(used, shorts=True) == ["shorts_wardogs_2026-10-04_1"]
    assert is_short("shorts_x_1") and not is_short("highlights_x_1")


def test_no_short_runs_over_the_limit():
    c = cand("a", 100, length=68.0)
    shorts.within_limit(c, 60.0, [], [], [])
    assert c.length == pytest.approx(60.0) and c.src_out == 168.0  # the payoff end is kept


def test_zoomed_out_keeps_more_of_the_sides_over_a_band_of_blur():
    """2026-10-05: at full height League's health bars were cut off ("zoom out a tad")."""
    graph = picture_graph(Vertical("crop", fill=0.85), (1920, 1080), VERTICAL, finish=[])
    assert "crop=714:1080:603:0,scale=1080:1632" in graph  # 714 wide, not 608
    assert "boxblur" in graph and "overlay=0:(H-h)/2" in graph


def test_the_preview_shades_what_the_apps_cover(settings):
    from ai_editor.recipes.preview import safe_zone_boxes

    boxes = safe_zone_boxes(settings.shorts.safe_zone())
    assert len(boxes) == 4 and "y=ih*0.740" in boxes[0] and boxes[-1].endswith("t=2")


def test_story_shorts_are_flagged_and_listed_as_shorts(settings):
    from ai_editor.app.videos import kind_of

    assert kind_of(EditPlan("shorts_x_1", "shorts", "Short", None, 30)) == "Short"
    assert "The Blood of Dawnwalker" in settings.shorts.spoiler_check_games


def test_a_preview_made_earlier_is_found_again_per_layout(settings):
    """2026-10-05: "once a preview is made, we should be able to find it"."""
    from ai_editor.app import videos
    from ai_editor.recipes.plan import Segment

    plan = EditPlan("shorts_wardogs_1", "shorts", "Short", "Wardogs", 30,
                    [Segment(1, 100, 130)])
    assert videos.last_preview(settings, plan) is None
    crop = videos.preview_file(settings, plan)
    fit = videos.preview_file(settings, plan, layout="fit")
    assert crop.name == "shorts_wardogs_1 crop.mp4" and fit.name == "shorts_wardogs_1 fit.mp4"
    crop.parent.mkdir(parents=True, exist_ok=True)
    crop.write_bytes(b"video")
    videos.remember_preview(settings, crop, plan)
    shown = videos.last_preview(settings, plan)
    assert "autoplay" not in shown and "changed since" not in shown
    assert videos.last_preview(settings, plan, layout="fit") is None  # not made for that one
    plan.source["effects"] = ["sfx"]  # effects switched off in Review since
    assert "changed since" in videos.last_preview(settings, plan)
    plan.source.pop("effects")
    plan.segments[0].src_out = 135  # changed in Review since
    assert "changed since" in videos.last_preview(settings, plan)
