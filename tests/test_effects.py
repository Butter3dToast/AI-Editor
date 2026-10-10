"""Effects on the big moments (Phase 2C-1): where they go, how they look and sound."""

from __future__ import annotations

import subprocess

import numpy as np
import pytest
import soundfile as sf

from ai_editor import effects
from ai_editor.db import init_db
from ai_editor.effects import Effect, flash, placement, sfx, shake, zoom
from ai_editor.effects import picture as picture_fx
from ai_editor.recipes.plan import EditPlan, Segment

from .conftest import FFMPEG, make_video, needs_ffmpeg

RATE = 48000


# --- Where they go ------------------------------------------------------------------------


def test_equal_seconds_share_a_place_so_a_quiet_run_is_never_big():
    values = np.array([0.0] * 97 + [1.0, 2.0, 3.0])
    ranks = placement.rank(values)
    assert ranks[:97].max() == 0.0          # not 0.0 ... 0.97 by position
    assert ranks[-1] == 1.0 and ranks[-3] > 0.97


def test_coming_back_from_silence_isnt_a_jump():
    quiet, loud = -90.0, -40.0
    db = np.array([-40.0] * 50 + [quiet] * 3 + [loud] + [-40.0] * 10 + [-25.0] + [-40.0] * 5)
    jumps = placement.rise(db)
    assert jumps[53] == pytest.approx(0.0)   # silence, then normal: nothing happened
    assert jumps[64] == pytest.approx(15.0)  # suddenly 15 dB louder: something did


def stream(impact, big=()):
    impact = np.array(impact, dtype=np.float32)
    big_impact = np.zeros(impact.size, dtype=bool)
    big_impact[list(big)] = True
    none = np.zeros_like(impact)
    return placement.Stream(impact, none, big_impact, none > 0)


def test_a_marks_moment_is_the_biggest_in_the_seconds_before_the_press():
    ranks = [0.5] * 60
    ranks[20], ranks[30], ranks[35], ranks[50] = 0.99, 0.9, 0.95, 1.0
    s = stream(ranks, big=[30])
    # Pressed at 40: looks back 20 s. 30 is really big, so it beats 35 and 20
    # (higher ranks in the stream, but not really big); 50 comes after the press.
    m = placement.marked_moment(s, 0, 10.0, 59.0, 40.0)
    assert (m.second, m.big, m.why) == (30, True, "impact")
    # Only inside the clip, clear of its first and last half second.
    m = placement.marked_moment(s, 0, 32.0, 59.0, 40.0)
    assert m.second == 35
    assert placement.marked_moment(s, 0, 41.0, 59.0, 40.0) is None


def test_the_marks_about_a_clip_include_one_pressed_just_after_it():
    marks = [5.0, 25.0, 38.0, 70.0]
    assert placement.marks_in(marks, 10.0, 30.0) == [25.0, 38.0]


def test_moments_are_spread_over_the_clips_not_bunched_in_one():
    found = [placement.Moment(0, t, 0.99 - t / 1000, 0) for t in (10, 20, 30, 40)]
    found += [placement.Moment(1, 15, 0.98, 0)]
    chosen = placement.pick(found, count=3, gap_sec=6, per_segment={0: 1, 1: 1})
    assert [(m.segment, m.second) for m in chosen] == [(0, 10), (1, 15)]
    # Without a per-clip limit: the strongest, kept apart.
    chosen = placement.pick(found, count=3, gap_sec=15)
    assert [(m.segment, m.second) for m in chosen] == [(0, 10), (0, 30), (1, 15)]


def test_how_many_follows_the_amount_per_minute():
    assert placement.how_many(1.5, 600, True) == 15
    assert placement.how_many(1.5, 20, True) == 1     # a short video with a big moment gets one
    assert placement.how_many(1.5, 600, False) == 0   # nothing big: nothing forced
    assert placement.how_many(0.0, 600, True) == 0


def test_each_kind_of_moment_gets_its_own_effects():
    impact = placement.Moment(0, 5, 0.99, 0.5, big=True)
    reaction = placement.Moment(0, 5, 0.5, 0.99, big=True)
    both = placement.Moment(0, 5, 0.98, 0.99, big=True, both=True)
    on = ["flash", "shake", "sfx"]
    kinds = lambda m: [(e.kind, e.sound) for e in placement.effects_at(m, 5.0, on)]
    assert kinds(impact) == [("shake", None), ("sfx", "boom")]
    assert kinds(reaction) == [("flash", None), ("sfx", "hit")]
    assert kinds(both) == [("flash", None), ("shake", None), ("sfx", "boom")]
    assert [e.kind for e in placement.effects_at(both, 5.0, ["sfx"])] == ["sfx"]
    # The zoom goes on your reactions; the shake stays on the action (2C-2a).
    zoomed = lambda m: [e.kind for e in placement.effects_at(m, 5.0, ["shake", "zoom"])]
    assert zoomed(impact) == ["shake"] and zoomed(reaction) == ["zoom"]
    assert zoomed(both) == ["shake", "zoom"]


def make_wav(path, seconds, events, level=0.01):
    """Quiet noise with a loud burst at each (start, seconds)."""
    rng = np.random.default_rng(1)
    x = rng.normal(0, level, int(seconds * RATE)).astype(np.float32)
    for start, length in events:
        a, b = int(start * RATE), int((start + length) * RATE)
        x[a:b] += rng.normal(0, 0.3, b - a).astype(np.float32)
    sf.write(str(path), np.stack([x, x], axis=1), RATE)
    return path


def test_an_effect_lines_up_with_the_instant_the_sound_starts(tmp_path):
    wav = make_wav(tmp_path / "game.wav", 10, [(4.37, 0.6)])
    assert placement.onset(wav, 4) == pytest.approx(4.37, abs=0.02)
    assert placement.onset(make_wav(tmp_path / "flat.wav", 10, []), 4) is None


def test_a_sound_already_going_at_the_window_edge_isnt_taken_for_the_start(tmp_path):
    # Loud from before the window opens, then a bigger burst: the edge of the
    # window must not look like the loudest moment (5 Oct, League Short).
    wav = make_wav(tmp_path / "game.wav", 10, [(3.0, 3.0), (4.6, 0.3), (4.6, 0.3)])
    found = placement.onset(wav, 4)
    assert found is None or 4.4 < found < 4.7


# --- Switching them on and off ---------------------------------------------------------------


def test_each_video_follows_the_settings_unless_switched_in_review(settings):
    plan = EditPlan("p", "highlights", "t", None, 600, [Segment(1, 0, 10)])
    assert effects.switches(settings, plan) == []  # off until League's events place them (2E)
    settings.effects.highlights = ["flash", "shake", "sfx"]
    assert effects.switches(settings, plan) == ["flash", "shake", "sfx"]
    effects.set_switches(plan, ["sfx", "flash"])
    assert effects.switches(settings, plan) == ["flash", "sfx"]
    effects.set_switches(plan, [])
    assert effects.switches(settings, plan) == []
    lets_play = EditPlan("lp", "letsplay", "t", None, 600, [Segment(1, 0, 10)])
    assert effects.switches(settings, lets_play) == []  # the creator's choice: none


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    connection.execute(
        "INSERT INTO recordings (id, content_hash, source_type, source_file, duration_sec, "
        "imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 60, '2026-10-05T12:00:00')")
    game = [-40.0] * 61
    game[30] = -20.0   # a jump in the game's sound
    game[50] = -32.0   # a smaller jump: not big enough
    loud = [0.0] * 61
    loud[45] = 4.0     # the creator shouting
    loud[52] = 4.0     # just as loud, but no words: a bump at the mic
    talking = [0.0] * 61
    talking[44:47] = [1.0, 1.0, 1.0]
    connection.executemany("INSERT INTO signals (recording_id, t_sec, name, value) VALUES "
                           "(1, ?, ?, ?)", [(t, "game_db", v) for t, v in enumerate(game)]
                           + [(t, "energy_z", v) for t, v in enumerate(loud)]
                           + [(t, "speech", v) for t, v in enumerate(talking)])
    # The creator's marks, pressed just after each moment.
    connection.executemany("INSERT INTO companion_events (session_id, event_type, wall_clock, "
                           "recording_time_sec, recording_id) VALUES ('s', ?, 'now', ?, 1)",
                           [("marker", 33.0), ("marker_short", 48.0)])
    connection.commit()
    yield connection
    connection.close()


def test_a_plan_gets_its_effects_on_its_big_moments(conn, settings):
    settings.effects.highlights = ["flash", "shake", "sfx"]
    settings.effects.highlights_per_min = 6.0  # room for all of them in 35 seconds
    plan = EditPlan("p", "highlights", "t", None, 600, [Segment(1, 20, 40), Segment(1, 40, 55)])
    placed = effects.for_plan(conn, settings, plan)
    assert [(e.kind, e.at, e.sound) for e in placed[0]] == [("shake", 30.0, None),
                                                           ("sfx", 30.0, "boom")]
    assert [(e.kind, e.at, e.sound) for e in placed[1]] == [("flash", 45.0, None),
                                                           ("sfx", 45.0, "hit")]
    assert effects.summary(placed) == "1 flash, 1 shake, 2 sound effects"
    effects.set_switches(plan, [])
    assert effects.for_plan(conn, settings, plan) == [[], []]


def test_a_clip_you_didnt_mark_gets_no_effects(conn, settings):
    """10 Oct: a shake "during a random time ... didn't use the moments I captured"."""
    settings.effects.highlights = ["flash", "shake", "sfx"]
    plan = EditPlan("p", "highlights", "t", None, 600, [Segment(1, 0, 20)])
    assert effects.for_plan(conn, settings, plan) == [[]]


# --- How they look -------------------------------------------------------------------------


def test_a_flash_is_only_switched_on_while_it_happens():
    text = flash.filter_text([Effect("flash", 12.5, 0.3, "reaction")], 10.0, 0.35)
    assert text.startswith("eq=brightness='0.350*(between(t,2.500,2.800)*(1-(t-2.500)/0.300))'")
    assert "enable='between(t,2.500,2.800)'" in text
    assert flash.filter_text([Effect("shake", 12.5, 0.45, "impact")], 10.0, 0.35) is None


def test_a_shake_moves_the_picture_only_while_it_happens():
    pieces = shake.graph([Effect("shake", 5.0, 0.45, "impact")], 0.0, 1080, 0.02, "in", "out")
    assert pieces[0] == "[in]format=yuv420p,split=2[out_base][out_moved]"
    assert "enable='between(t,5.000,5.450)'" in pieces[1] and pieces[1].endswith("[out]")
    assert "22*(" in pieces[1]  # 2% of 1080 pixels


def test_a_zoom_pushes_in_only_while_it_happens():
    pieces = zoom.graph([Effect("zoom", 5.0, 0.9, "reaction")], 0.0, 0.2, "in", "out")
    assert pieces[0] == "[in]format=yuv420p,split=2[out_base][out_big]"
    assert "scale=w='trunc(iw*(1+0.200*(between(t,5.000,5.900)" in pieces[1]
    assert "enable='between(t,5.000,5.900)'" in pieces[2] and pieces[2].endswith("[out]")
    assert zoom.graph([Effect("shake", 5.0, 0.45, "impact")], 0.0, 0.2, "in", "out") is None


def test_picture_effects_chain_flash_zoom_then_shake():
    from ai_editor.config import Effects

    every = [Effect("flash", 1.0, 0.3, "reaction"), Effect("zoom", 1.0, 0.9, "reaction"),
             Effect("shake", 1.0, 0.45, "impact")]
    pieces = picture_fx.graph(every, 0.0, 1080, Effects(), "pic", "moved")
    assert pieces[0].endswith("[moved_flashed]") and pieces[1].startswith("[moved_flashed]")
    assert pieces[3].endswith("[moved_zoomed]") and pieces[4].startswith("[moved_zoomed]")
    assert pieces[-1].endswith("[moved]")


def test_picture_effects_chain_flash_then_shake():
    from ai_editor.config import Effects

    both = [Effect("flash", 1.0, 0.3, "reaction"), Effect("shake", 1.0, 0.45, "impact")]
    pieces = picture_fx.graph(both, 0.0, 1080, Effects(), "pic", "moved")
    assert pieces[0].startswith("[pic]eq=") and pieces[0].endswith("[moved_flashed]")
    assert pieces[1].startswith("[moved_flashed]format=yuv420p,split")
    assert picture_fx.graph([Effect("sfx", 1.0, 1.0, "impact", "boom")], 0.0, 1080, Effects(),
                            "pic", "moved") == []


def test_segment_effects_go_under_the_captions_and_sounds_into_the_mix(tmp_path):
    from ai_editor.config import RenderPreset
    from ai_editor.render.audio import AudioChoice
    from ai_editor.render.final import segment_args

    sound = sfx.Placed(tmp_path / "boom.wav", 2.5, -12.0)
    args = segment_args(tmp_path / "rec.mkv", 10.0, 6.0, AudioChoice([1, 2], 1, True),
                        RenderPreset(width=1920, height=1080, fps=60, bitrate="16M"),
                        (1920, 1080), ["-c:v", "libx264"], tmp_path / "out.mkv", gpu_decode=False,
                        captions="000.ass", effects=[Effect("flash", 12.0, 0.3, "reaction")],
                        sounds=[sound])
    graph = args[args.index("-filter_complex") + 1]
    assert args[args.index("-i") + 1].endswith("rec.mkv")
    assert args[args.index(str(tmp_path / "boom.wav")) - 1] == "-i"
    assert graph.index("eq=brightness") < graph.index("subtitles=filename=000.ass")
    assert "volume=-12.00dB,adelay=2500:all=1[sfx0]" in graph
    assert "[a0][a1][sfx0]amix=inputs=3:normalize=0" in graph


# --- How they sound ---------------------------------------------------------------------------


def test_the_starter_sounds_are_made_once_and_not_too_loud(settings):
    folder = sfx.starter_folder(settings)
    for name in sfx.NAMES:
        path = sfx.starter(folder, name)
        x, rate = sf.read(str(path))
        assert rate == RATE and x.shape[1] == 2 and 0.3 < len(x) / rate < 1.5
        assert 20 * np.log10(np.abs(x).max()) == pytest.approx(sfx.PEAK_DB, abs=0.2)
    made = sfx.starter(folder, "boom").stat().st_mtime_ns
    assert sfx.starter(folder, "boom").stat().st_mtime_ns == made


def test_your_own_sounds_come_first_and_the_same_moment_always_gets_the_same(settings):
    assert sfx.choose(settings, "boom", "k").parent == sfx.starter_folder(settings)
    root = settings.folders.assets / "sfx"
    for folder in ("boom", "hit"):
        (root / folder).mkdir(parents=True)
    for name in ("boom/deep.wav", "boom/short.wav", "big_boom_02.mp3", "hit/punch.wav"):
        (root / name).write_bytes(b"")
    mine = {p.name for p in sfx.yours(settings, "boom")}
    assert mine == {"deep.wav", "short.wav", "big_boom_02.mp3"}
    assert sfx.choose(settings, "boom", "plan:12.00") == sfx.choose(settings, "boom", "plan:12.00")


def test_a_sound_effect_matches_its_moment_but_never_drowns(settings, tmp_path):
    # A quiet clip (-46 dB) with one shout (-16 dB) at 4 s.
    track = make_wav(tmp_path / "mix.wav", 10, [(4.0, 0.5)], level=0.005)
    settings.effects.sfx_volume_db = -3.0
    shout = Effect("sfx", 4.0, 1.0, "reaction", "hit")
    quiet = Effect("sfx", 7.0, 1.0, "impact", "boom")
    placed = sfx.place(settings, [shout, quiet], 0.0, 10.0, [track], "k")
    loudest = {p.path.stem.split("-")[0]: sfx.loudest_db(p.path) for p in placed}
    hit_level = placed[0].gain_db + loudest["hit"]
    boom_level = placed[1].gain_db + loudest["boom"]
    shout_db = sfx.loudest_between([track], 3.75, 4.75)
    assert hit_level == pytest.approx(shout_db - 3.0, abs=0.1)      # on the shout: just under it
    assert boom_level == pytest.approx(shout_db - sfx.FLOOR_UNDER_PEAK_DB - 3.0, abs=0.1)
    assert placed[0].at == 4.0


# --- The real thing ------------------------------------------------------------------------------


def frame_at(video, seconds):
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", str(seconds), "-i", str(video),
                          "-frames:v", "1", "-vf", "scale=96:54", "-f", "rawvideo", "-pix_fmt",
                          "gray", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).astype(float)


@needs_ffmpeg
@needs_ffmpeg
def test_a_zoom_pushes_in_and_comes_back_out(conn, settings, tmp_path):
    from ai_editor.ffmpeg import probe
    from ai_editor.render.final import render_plan

    video = make_video(tmp_path / "rec.mp4", width=640, height=360, fps=30, seconds=60)
    conn.execute("UPDATE recordings SET source_file = ?, width = 640, height = 360", (str(video),))
    conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role) VALUES (1, 1, 'mixed')")
    conn.commit()
    settings.performance.device = "cpu"
    plan = EditPlan("fx_z", "highlights", "Test", None, 600, [Segment(1, 42.0, 48.0)])
    effects.set_switches(plan, ["zoom"])
    zoomed = render_plan(conn, settings, plan, target=tmp_path / "zoom.mp4")
    assert zoomed.notes == ["Effects: 1 zoom."]
    effects.set_switches(plan, [])
    plain = render_plan(conn, settings, plan, target=tmp_path / "plain.mp4")
    assert probe(zoomed.path).duration_sec == pytest.approx(probe(plain.path).duration_sec,
                                                           abs=0.02)
    at = 45.0 - 42.0 + 0.4    # held, all the way in
    assert np.abs(frame_at(zoomed.path, at) - frame_at(plain.path, at)).mean() > 5
    assert frame_at(zoomed.path, at).shape == frame_at(plain.path, at).shape
    for clear in (1.0, 5.5):  # before it, and once it has eased back out
        assert np.abs(frame_at(zoomed.path, clear) - frame_at(plain.path, clear)).mean() < 2.0


def test_a_render_has_its_effects_and_nothing_else_changes(conn, settings, tmp_path):
    from ai_editor.ffmpeg import probe
    from ai_editor.render.final import render_plan

    video = make_video(tmp_path / "rec.mp4", width=640, height=360, fps=30, seconds=60)
    conn.execute("UPDATE recordings SET source_file = ?, width = 640, height = 360", (str(video),))
    conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role) VALUES (1, 1, 'mixed')")
    conn.commit()
    settings.performance.device = "cpu"
    plan = EditPlan("fx_1", "highlights", "Test", None, 600, [Segment(1, 42.0, 48.0)])
    effects.set_switches(plan, ["flash", "shake", "sfx"])
    with_fx = render_plan(conn, settings, plan, target=tmp_path / "fx.mp4")
    assert with_fx.notes == ["Effects: 1 flash, 1 sound effect."]
    effects.set_switches(plan, [])
    plain = render_plan(conn, settings, plan, target=tmp_path / "plain.mp4")
    assert probe(with_fx.path).duration_sec == pytest.approx(probe(plain.path).duration_sec,
                                                            abs=0.02)
    flash_at = 45.0 - 42.0 + 0.05
    assert frame_at(with_fx.path, flash_at).mean() > frame_at(plain.path, flash_at).mean() + 20
    assert np.abs(frame_at(with_fx.path, 1.0) - frame_at(plain.path, 1.0)).mean() < 2.0


def test_only_really_big_moments_count_not_just_a_calm_streams_loudest(conn):
    """10 Oct: a flash on a bump at the mic, nothing said. "Randomly placed"."""
    s = placement.stream_of(conn, 1)
    assert s.big_impact[30] and not s.big_impact[50]       # 20 dB jump yes, 8 dB no
    assert s.big_reaction[45] and not s.big_reaction[52]   # a shout yes, a bump no
    assert s.reaction[52] == 0.0                            # nothing said: never a reaction
