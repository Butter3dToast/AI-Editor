"""Adjusting a clip's cut in Review, and Shorts that keep the build-up (10 Oct)."""

from __future__ import annotations

import json

import pytest

from ai_editor.analysis.captions import Word
from ai_editor.analysis.clips import Clip, store_clips, word_boundaries
from ai_editor.app.video_tabs import cut_clock, parse_clock
from ai_editor.config import Captions, Effects, Shorts
from ai_editor.db import init_db
from ai_editor.recipes import review, shorts
from ai_editor.recipes.plan import EditPlan, Segment

from .test_shorts import cand


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    connection.execute(
        "INSERT INTO recordings (id, content_hash, source_type, source_file, duration_sec, "
        "imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 600, 'now')")
    # Talking from 100 s: "one" 100.0-100.6, "two" 100.8-101.5, ..., one word a second.
    connection.executemany(
        "INSERT INTO transcript_words (recording_id, idx, word, start_sec, end_sec) "
        "VALUES (1, ?, ?, ?, ?)",
        [(i, f"w{i}", 100.0 + i, 100.6 + i) for i in range(60)])
    connection.execute(
        "INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, signals_json, "
        "created_at) VALUES ('c1', 1, 120, 150, 0.8, ?, 'now')",
        (json.dumps({"reasons": ["laughter"], "peak": 145, "core": [140, 146]}),))
    connection.commit()
    yield connection
    connection.close()


def plan_of(recipe="highlights"):
    return EditPlan("p", recipe, "t", None, 600,
                    [Segment(1, 130.0, 150.0, kind="clip", clip_id="c1")])


def test_a_cut_can_reach_back_before_the_clip_and_the_library_keeps_it(conn, settings):
    change = review.adjust(conn, settings, plan_of(), 0, 112.3, 148.3)
    s = change.plan.segments[0]
    # Both are mid-word ("w12", "w48"): out to the gaps before and after them.
    assert (s.src_in, s.src_out) == (111.8, 148.8)
    assert "now runs 0:01:51-0:02:28" in change.message
    clip = conn.execute("SELECT start_sec, end_sec, signals_json, transcript FROM clips").fetchone()
    assert (clip[0], clip[1]) == (111.8, 148.8)
    assert json.loads(clip[2])["adjusted"] and clip[3].startswith("w12")
    row = conn.execute("SELECT action, detail_json FROM feedback").fetchone()
    assert row[0] == "adjusted" and json.loads(row[1])["before"] == [130.0, 150.0]


def test_a_cut_on_a_gap_between_words_stays_exactly_there(conn, settings):
    s = review.adjust(conn, settings, plan_of(), 0, 112.8, 148.9).plan.segments[0]
    assert (s.src_in, s.src_out) == (112.8, 148.9)


def test_a_short_stays_within_the_limit_and_a_cut_has_some_length(conn, settings):
    change = review.adjust(conn, settings, plan_of("shorts"), 0, 60.0, 150.0)
    assert "at most 60" in change.message and change.plan.segments[0].src_in == 130.0
    assert "at least" in review.adjust(conn, settings, plan_of(), 0, 140.0, 140.5).message
    short = review.adjust(conn, settings, plan_of("shorts"), 0, 100.0, 150.0).plan
    assert short.target_sec == pytest.approx(50.0, abs=0.7)


def test_an_adjusted_clip_survives_cutting_the_recording_again(conn, settings):
    review.adjust(conn, settings, plan_of(), 0, 112.8, 148.9)
    store_clips(conn, 1, [Clip(300.0, 330.0, 315, 0.5, (310, 320))], signals={}, words=[])
    kept = conn.execute("SELECT clip_id, start_sec FROM clips ORDER BY start_sec").fetchall()
    assert [tuple(r) for r in kept] == [("c1", 112.8), ("rec1_000300000", 300.0)]


def test_times_are_typed_and_shown_to_the_tenth():
    assert parse_clock("1:34:52.4") == pytest.approx(5692.4)
    assert parse_clock("34:52") == 2092 and parse_clock("95") == 95
    assert parse_clock("soon") is None and parse_clock("1:2:3:4") is None
    assert cut_clock(5692.44) == "1:34:52.4"


# --- Shorts keep the build-up ---------------------------------------------------------------


def test_a_short_from_your_mark_ends_just_after_the_press(settings):
    c = cand("m", 5706.0, length=95.0)          # the clip: 5706-5801, marked at 5778
    words = [Word("x", t, t + 0.5) for t in (5732.8, 5782.7)]
    shorts.around_mark(c, [5778.0], settings, words, word_boundaries(words),
                       [w.start for w in words])
    # 45 s before the press and 5 s after, each moved out of the word it landed in.
    assert 5732.5 < c.src_in <= 5732.8 and 5783.2 <= c.src_out < 5783.6


def test_a_short_opens_well_before_its_moment_and_captions_are_off():
    s = Shorts()
    assert s.lead_in_sec == 25 and not s.captions
    assert not Captions().highlights and not Captions().lets_play
    assert Effects().highlights == Effects().shorts == Effects().lets_play == []


def test_heavy_video_work_runs_below_normal_priority():
    import subprocess
    import sys

    from ai_editor import ffmpeg

    if sys.platform == "win32":
        assert ffmpeg._BACKGROUND & subprocess.BELOW_NORMAL_PRIORITY_CLASS
        assert ffmpeg._BACKGROUND & subprocess.CREATE_NO_WINDOW


# --- Streams deleted once their videos are made (10 Oct) ----------------------------------------


def test_new_highlights_leave_out_recordings_whose_video_was_deleted(settings, tmp_path):
    from ai_editor.recipes.highlights import build_highlights, recordings_for
    from ai_editor.recipes.shorts import build_shorts

    conn = init_db(settings.db_path)
    kept = tmp_path / "kept.mkv"
    kept.write_bytes(b"x")
    for rid, path in ((1, kept), (2, tmp_path / "deleted.mkv")):
        conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                     "duration_sec, imported_at, analysis_status, game) VALUES "
                     "(?, ?, 'local_obs', ?, 600, 'now', 'complete', 'Wardogs')",
                     (rid, f"h{rid}", str(path)))
    conn.commit()
    assert [r["id"] for r in recordings_for(conn, settings, game="Wardogs",
                                            recording_ids=None)] == [1]
    assert len(recordings_for(conn, settings, game="Wardogs", recording_ids=None,
                              need_video=False)) == 2
    plan = build_highlights(conn, settings, game="Wardogs").plan
    assert any("Left out 1 recording whose video was deleted (#2)" in n for n in plan.notes)
    shorts = build_shorts(conn, settings, 2)
    assert not shorts.plans and "video was deleted" in shorts.notes[0]
    conn.close()
