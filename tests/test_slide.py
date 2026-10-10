"""Sliding between clips, and switching single moments' effects off (Phase 2C-3b)."""

from __future__ import annotations

import subprocess

import numpy as np
import pytest

from ai_editor import effects
from ai_editor.config import Effects
from ai_editor.db import init_db
from ai_editor.effects import sfx
from ai_editor.recipes.plan import EditPlan, Segment
from ai_editor.render import slide

from .conftest import FFMPEG, make_video, needs_ffmpeg


def highlights(*segments) -> EditPlan:
    return EditPlan("hl_1", "highlights", "t", None, 600, list(segments))


def test_a_hard_cut_unless_the_video_or_settings_say_slide(settings):
    plan = highlights(Segment(1, 0, 10), Segment(1, 20, 30))
    assert slide.between(settings, plan) == "cut"
    settings.effects.between_clips = "slide"
    assert slide.between(settings, plan) == "slide"
    plan.source["between"] = "cut"     # chosen for this video in Review
    assert slide.between(settings, plan) == "cut"
    plan.source["between"] = "whoosh"  # tried first, before the slide replaced it
    assert slide.between(settings, plan) == "slide"
    assert Effects(between_clips="whoosh").between_clips == "slide"
    short = EditPlan("s", "shorts", "t", None, 60, [Segment(1, 0, 30)])
    assert slide.between(settings, short) == "cut"


def test_each_slide_is_whole_frames_and_too_short_a_clip_cuts(settings):
    settings.effects.between_clips = "slide"
    plan = highlights(Segment(1, 0, 10), Segment(1, 20, 22), Segment(1, 30, 40), Segment(1, 50, 60))
    # The 2-second clip can't lose 0.8 s at both ends and keep a second: cuts either side.
    assert slide.overlaps(settings, plan, [10.0, 2.0, 10.0, 10.0], 60) == [0.0, 0.0, 0.8]
    assert slide.overlaps(settings, plan, [10.0, 2.6, 10.0, 10.0], 30) == pytest.approx(
        [0.8, 0.8, 0.8])


def test_clips_start_in_the_video_where_they_begin_to_slide_in():
    assert slide.starts([10.0, 12.0, 5.0], [0.8, 0.0]) == pytest.approx([0.0, 9.2, 21.2])


def test_a_clip_with_slides_becomes_its_middle_and_its_ends():
    items = slide.layout([10.0, 12.0, 5.0], [0.8, 0.0])
    assert [type(i).__name__ for i in items] == ["Piece", "Slide", "Piece", "Piece"]
    first, between, second, third = items
    assert (first.offset, first.length, first.cut_in, first.cut_out) == (0.0, 9.2, True, False)
    assert (between.leaving.segment, between.leaving.offset, between.leaving.length) == (0, 9.2, 0.8)
    assert (between.arriving.segment, between.arriving.offset) == (1, 0.0)
    assert (second.offset, second.length, second.cut_in, second.cut_out) == (0.8, 11.2, False, True)
    assert (third.offset, third.length, third.cut_in) == (0.0, 5.0, True)


def test_the_slide_eases_in_from_the_right_and_the_sound_crossfades(tmp_path):
    args = slide.compose_args(tmp_path / "a.mkv", tmp_path / "b.mkv", 0.8, ["-c:v", "x"],
                              tmp_path / "o.mkv", ["-c:a", "pcm_f32le"])
    graph = args[args.index("-filter_complex") + 1]
    assert "overlay=x='W*(1-(clip(t/0.8000,0,1))*(clip(t/0.8000,0,1))*(3-2*" in graph
    assert "acrossfade=d=0.7980" in graph and args[-1].endswith("o.mkv")


def test_a_sound_effect_carries_on_into_the_next_piece(settings):
    boom = sfx.starter(sfx.starter_folder(settings), "boom")   # 1.2 s long
    placed = [sfx.Placed(boom, 8.8, -10.0)]
    assert sfx.within_piece(placed, 0.0, 9.2) == [sfx.Placed(boom, 8.8, -10.0, 0.0)]
    rest = sfx.within_piece(placed, 9.2, 0.8)
    assert rest[0].at == 0.0 and rest[0].skip == pytest.approx(0.4)
    assert sfx.within_piece(placed, 10.5, 2.0) == []    # over by then


# --- One moment at a time ---------------------------------------------------------------------


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    connection.execute(
        "INSERT INTO recordings (id, content_hash, source_type, source_file, duration_sec, "
        "imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 60, '2026-10-10T12:00:00')")
    game = [-40.0] * 61
    game[30] = game[50] = -20.0
    connection.executemany("INSERT INTO signals (recording_id, t_sec, name, value) VALUES "
                           "(1, ?, 'game_db', ?)", list(enumerate(game)))
    connection.executemany("INSERT INTO companion_events (session_id, event_type, wall_clock, "
                           "recording_time_sec, recording_id) VALUES ('s', 'marker', 'now', ?, 1)",
                           [(33.0,), (53.0,)])
    connection.commit()
    yield connection
    connection.close()


def test_each_moment_is_listed_and_can_be_left_out_alone(conn, settings):
    settings.effects.highlights = ["flash", "shake", "sfx"]
    settings.effects.highlights_per_min = 6.0   # room for both in 28 seconds
    plan = highlights(Segment(1, 25, 40), Segment(1, 45, 58))
    found = effects.moments(conn, settings, plan)
    assert [label for label, _ in found] == ["Clip 1 at 0:05: shake + boom",
                                             "Clip 2 at 0:20: shake + boom"]
    effects.set_moments_on(plan, [k for _, k in found], [found[1][1]])
    placed = effects.for_plan(conn, settings, plan)
    assert placed[0] == [] and [e.kind for e in placed[1]] == ["shake", "sfx"]
    # Still listed, so it can be ticked back on; and it stays off wherever the clip moves.
    assert len(effects.moments(conn, settings, plan)) == 2
    plan.segments.reverse()
    assert [e.at for e in effects.for_plan(conn, settings, plan)[0]] == [50.0, 50.0]


def test_times_in_the_video_allow_for_the_slides(conn, settings):
    settings.effects.highlights = ["shake"]
    settings.effects.highlights_per_min = 6.0
    settings.effects.between_clips = "slide"
    plan = highlights(Segment(1, 25, 40), Segment(1, 45, 58))
    assert effects.moments(conn, settings, plan)[1][0] == "Clip 2 at 0:19: shake"  # 0:20 less 0.8


# --- The real thing ---------------------------------------------------------------------------


def frame(path, seconds) -> np.ndarray:
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(path),
                          "-frames:v", "1", "-vf", "scale=64:36", "-f", "rawvideo", "-pix_fmt",
                          "gray", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).astype(float).reshape(36, 64)


@needs_ffmpeg
def test_a_render_slides_the_next_clip_in_over_the_last(conn, settings, tmp_path):
    from ai_editor.ffmpeg import probe
    from ai_editor.render.final import render_plan

    video = make_video(tmp_path / "rec.mp4", width=640, height=360, fps=30, seconds=60)
    conn.execute("UPDATE recordings SET source_file = ?, width = 640, height = 360", (str(video),))
    conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role) VALUES (1, 1, 'mixed')")
    conn.commit()
    settings.performance.device = "cpu"
    plan = highlights(Segment(1, 2.0, 6.0), Segment(1, 20.0, 24.0))
    plan.source["between"] = "slide"
    slid = render_plan(conn, settings, plan, target=tmp_path / "slide.mp4")
    assert slid.length_sec == pytest.approx(7.2) and "Slides between clips: 1." in slid.notes
    assert probe(slid.path).duration_sec == pytest.approx(7.2, abs=0.1)
    plan.source["between"] = "cut"
    cut = render_plan(conn, settings, plan, target=tmp_path / "cut.mp4")
    same = lambda a, b: np.abs(a - b).mean() < 3
    assert same(frame(slid.path, 1.0), frame(cut.path, 1.0))            # before: the first clip
    assert same(frame(slid.path, 6.0), frame(cut.path, 6.8))            # after: the second, 0.8 s on
    halfway = frame(slid.path, 3.6)                                     # mid-slide: both
    left, right = halfway[:, :24], halfway[:, 40:]
    assert same(left, frame(cut.path, 3.6)[:, :24])                     # the old clip on the left
    assert not same(right, frame(cut.path, 3.6)[:, 40:])                # the new one sliding over
