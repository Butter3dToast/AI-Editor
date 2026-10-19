"""The creator's three tips, built in (Phase 2H-1): the action inside the clip,
the game never over their voice, and effects suggested for them to tick."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest
import soundfile as sf

from ai_editor import effects
from ai_editor.analysis import fights
from ai_editor.analysis.captions import Word
from ai_editor.app import review_list
from ai_editor.db import init_db
from ai_editor.recipes.highlights import Candidate, whole_fight
from ai_editor.recipes.plan import EditPlan, Segment
from ai_editor.render import music

from .conftest import FFMPEG, needs_ffmpeg

QUIET, LOUD = -60.0, -50.0


def game_sound(seconds: int, loud: list[tuple[int, int]]) -> np.ndarray:
    """The game's loudness each second: quiet, with loud stretches (a fight)."""
    db = np.full(seconds, QUIET, dtype=np.float32)
    for a, b in loud:
        db[a:b] = LOUD
    return db


# --- Tip 1: "Ensure the action is always within the clip" ---------------------------------------


def test_a_fight_going_on_where_a_clip_starts_is_followed_back_to_where_it_began(settings):
    # One loud second at 90 and a fight from 100 to 130: like the 10 Oct League clip
    # that opened at 46:32, two deaths into a fight that began at 46:27.
    fight = fights.fighting({"game_db": game_sound(300, [(90, 91), (100, 130)])}, settings)
    assert fights.began(fight, 110.0, settings) == 100.0    # not the lone second before it
    assert fights.start_before(fight, 110.0, settings) == 99.0
    assert fights.began(fight, 135.0, settings) is None     # it was over by then
    assert fights.began(fight, 98.0, settings) is None      # not started yet: the clip has it all


def test_a_long_fight_is_followed_back_only_so_far(settings):
    fight = fights.fighting({"game_db": game_sound(300, [(120, 200)])}, settings)
    assert fights.began(fight, 190.0, settings) == 190.0 - settings.clips.fight_extend_sec


def test_leagues_deaths_count_as_fighting_too(settings):
    """The first champions died before the game got loud: the fight began with them."""
    deaths = np.zeros(300, dtype=np.float32)
    deaths[[100, 102]] = 0.5
    fight = fights.fighting({"lol_fight": deaths, "game_db": game_sound(300, [(104, 115)])},
                            settings)
    assert fights.began(fight, 107.0, settings) == 100.0


def candidate(start: float, src_in: float, src_out: float) -> Candidate:
    c = Candidate("c1", 1, start, src_out, 0.8, int(src_in) + 10, (int(src_in), int(src_out)),
                  [], datetime(2026, 10, 10, tzinfo=timezone.utc), False)
    c.src_in, c.src_out = src_in, src_out
    return c


def test_a_clip_starts_before_the_fight_as_far_as_its_length_allows(settings):
    fight = fights.fighting({"game_db": game_sound(300, [(100, 130)])}, settings)
    roomy = candidate(70.0, 110.0, 140.0)
    whole_fight(roomy, fight, 50.0, [], [], [], settings)
    assert roomy.src_in == 99.0 and roomy.src_out == 140.0   # all of it, the end as it was
    tight = candidate(70.0, 110.0, 140.0)
    whole_fight(tight, fight, 35.0, [], [], [], settings)
    assert tight.src_in == 105.0                              # as far as 35 s allows
    library = candidate(104.0, 110.0, 140.0)
    whole_fight(library, fight, 50.0, [], [], [], settings)
    assert library.src_in == 104.0                            # never before the library clip
    settings.clips.keep_fights_whole = False
    off = candidate(70.0, 110.0, 140.0)
    whole_fight(off, fight, 50.0, [], [], [], settings)
    assert off.src_in == 110.0                                # switched off: as before


def test_a_moved_start_never_lands_inside_a_word(settings):
    fight = fights.fighting({"game_db": game_sound(300, [(100, 130)])}, settings)
    words = [Word("hey", 98.8, 99.4)]
    c = candidate(70.0, 110.0, 140.0)
    whole_fight(c, fight, 50.0, words, [98.8, 99.4], [98.8], settings)
    assert c.src_in == 98.8


@pytest.fixture
def conn(settings, tmp_path):
    connection = init_db(settings.db_path)
    video = tmp_path / "x.mkv"
    video.write_bytes(b"x")
    connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                       "duration_sec, imported_at, analysis_status) VALUES "
                       "(1, 'h', 'local_obs', ?, 300, '2026-10-10T20:00:00', 'complete')",
                       (str(video),))
    connection.executemany("INSERT INTO signals (recording_id, t_sec, name, value) VALUES "
                           "(1, ?, 'game_db', ?)",
                           [(t, float(v)) for t, v in enumerate(game_sound(300, [(100, 130)]))])
    connection.commit()
    fights._cache.clear()
    yield connection
    connection.close()
    fights._cache.clear()


def test_review_marks_a_clip_that_starts_mid_fight(conn, settings):
    assert fights.missed(conn, settings, 1, 110.0) == 10.0
    assert fights.missed(conn, settings, 1, 101.0) is None     # a second: not worth a mark
    plan = EditPlan("hl", "highlights", "t", None, 600, [Segment(1, 110, 140, clip_id="a"),
                                                         Segment(1, 200, 230, clip_id="b")])
    page = review_list.clip_rows(conn, plan, settings)
    assert page.count("⚠ starts mid-fight (10 s already gone)") == 1
    assert "Adjust the cut" in page
    settings.clips.keep_fights_whole = False
    assert "⚠" not in review_list.clip_rows(conn, plan, settings)


# --- Tip 2: "Make sure the video sound is never over my voice" ----------------------------------


W = music.WINDOW_SEC


def windows(seconds: float, level: float) -> np.ndarray:
    return np.full(int(round(seconds / W)), level)


def test_the_game_is_kept_under_your_voice_only_as_far_as_needed():
    voice = np.concatenate([windows(2, -120), windows(3, -30), windows(3, -120)])
    cut = music.lowering(windows(8, -36), voice, keep_under=music.GAME_KEEP_UNDER_DB)
    assert cut[int(3 / W)] == pytest.approx(-4.0)          # to 10 dB under the voice
    assert cut[0] == 0 and cut[-1] == 0                     # loud as ever between words
    # League, 11 Oct: the game 45 dB under the creator's talking. Left alone.
    league = music.lowering(windows(8, -75), voice, keep_under=music.GAME_KEEP_UNDER_DB)
    assert not league.any()


def test_the_games_level_and_your_voices_are_read_from_their_tracks(tmp_path):
    rate = 8000
    t = np.arange(rate * 4) / rate
    game = 0.3 * np.sin(2 * np.pi * 220 * t)
    voice = np.where((t >= 1) & (t < 3), 0.1 * np.sin(2 * np.pi * 440 * t), 0.0)
    sf.write(tmp_path / "game.wav", game.astype(np.float32), rate)
    sf.write(tmp_path / "mic.wav", voice.astype(np.float32), rate)
    game_db, voice_db = music.voice_levels(tmp_path / "game.wav", tmp_path / "mic.wav", 0.0, 4.0)
    lowered = music.stretches(music.lowering(game_db, voice_db,
                                             keep_under=music.GAME_KEEP_UNDER_DB))
    # From just before you start (held over the gaps between words, like the music).
    assert len(lowered) == 1 and 0.7 < lowered[0][0] < 1.1 and 2.9 < lowered[0][1] < 3.3
    assert lowered[0][2] == pytest.approx(-music.MAX_LOWER_DB)   # 10 dB over it: as far as allowed
    assert music.voice_levels(None, tmp_path / "mic.wav", 0.0, 4.0) is None


def test_only_the_game_track_is_turned_down_in_the_mix(settings, tmp_path):
    from ai_editor.render.audio import AudioChoice
    from ai_editor.render.final import segment_args

    choice = AudioChoice([2, 3, 4], 2, True, game=3)
    args = segment_args(tmp_path / "r.mkv", 0.0, 5.0, choice,
                        settings.render.presets["youtube_1080p60"], (1920, 1080), [],
                        tmp_path / "o.mkv", gpu_decode=False, game_lowered=[(1.0, 3.0, -4.0)])
    graph = args[args.index("-filter_complex") + 1].split(";")
    game = next(g for g in graph if g.startswith("[1:3]"))   # the sound: the second input
    assert "volume='if(isnan(t),1,1-" in game
    assert not any("volume='if(isnan(t),1,1-" in g for g in graph if g.startswith(("[1:2]", "[1:4]")))
    assert "the game kept under your voice" in choice.describe()


def test_the_game_is_found_on_its_own_track_and_the_switch_turns_it_off(settings, tmp_path):
    from ai_editor.render.audio import choose_tracks

    from .test_render import add_tracks, noise

    connection = init_db(settings.db_path)
    connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                       "duration_sec, imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 60, "
                       "'2026-10-10T12:00:00')")
    mic, game, discord = (noise(60, seed=n) for n in range(3))
    add_tracks(connection, tmp_path, {"mixed": mic + game + discord, "mic": mic, "game": game,
                                      "voice_chat": discord})
    choice = choose_tracks(connection, settings, 1)
    assert choice.game == 3 and choice.game_path.name == "track_3.wav"
    assert choice.mic_path.name == "track_2.wav"     # your voice only: not Discord
    settings.render.game_under_voice = False
    assert choose_tracks(connection, settings, 1).game is None
    connection.close()


# --- Tip 3: "Suggest where an effect can work and which effect" ---------------------------------


@pytest.fixture
def moments(settings):
    """A jump in the game's sound at 30 s and the creator shouting at 45 s, both marked."""
    connection = init_db(settings.db_path)
    connection.execute(
        "INSERT INTO recordings (id, content_hash, source_type, source_file, duration_sec, "
        "imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 60, '2026-10-05T12:00:00')")
    game = [-40.0] * 61
    game[30] = -20.0
    loud = [0.0] * 61
    loud[45] = 4.0
    talking = [0.0] * 61
    talking[44:47] = [1.0, 1.0, 1.0]
    connection.executemany("INSERT INTO signals (recording_id, t_sec, name, value) VALUES "
                           "(1, ?, ?, ?)", [(t, "game_db", v) for t, v in enumerate(game)]
                           + [(t, "energy_z", v) for t, v in enumerate(loud)]
                           + [(t, "speech", v) for t, v in enumerate(talking)])
    connection.executemany("INSERT INTO companion_events (session_id, event_type, wall_clock, "
                           "recording_time_sec, recording_id) VALUES ('s', ?, 'now', ?, 1)",
                           [("marker", 33.0), ("marker_short", 48.0)])
    connection.commit()
    settings.effects.highlights_per_min = 6.0
    yield connection
    connection.close()


def two_clips() -> EditPlan:
    return EditPlan("p", "highlights", "t", None, 600, [Segment(1, 20, 40), Segment(1, 40, 55)])


def test_each_big_moment_is_suggested_with_the_effects_that_suit_it_none_ticked(moments,
                                                                               settings):
    plan = two_clips()
    found = effects.suggestions(moments, settings, plan)
    assert [s.label for s in found] == ["Clip 1 at 0:10: shake + replay + boom",
                                        "Clip 2 at 0:25: flash + zoom + hit"]
    assert not any(s.on for s in found)                       # nothing until ticked
    assert effects.for_plan(moments, settings, plan) == [[], []]
    lets_play = EditPlan("lp", "letsplay", "t", None, 600, [Segment(1, 20, 55)])
    assert effects.suggestions(moments, settings, lets_play) == []   # no effects there


def test_a_ticked_suggestion_gets_its_effects_and_nothing_else_does(moments, settings):
    plan = two_clips()
    shout = effects.suggestions(moments, settings, plan)[1]
    effects.use_suggestions(moments, settings, plan, [shout.key])
    placed = effects.for_plan(moments, settings, plan)
    assert placed[0] == []                                    # the other moment: untouched
    assert [e.kind for e in placed[1]] == ["flash", "zoom", "sfx"]
    assert effects.switches(settings, plan) == ["flash", "sfx", "zoom"]
    assert [s.on for s in effects.suggestions(moments, settings, plan)] == [False, True]
    effects.use_suggestions(moments, settings, plan, [])
    assert effects.for_plan(moments, settings, plan) == [[], []]
    assert effects.switches(settings, plan) == []


def test_a_moment_keeps_the_effects_it_had_when_another_is_ticked(moments, settings):
    """Shake only on the jump (ticked for the whole video); ticking the shout as
    suggested mustn't add its boom to the jump."""
    plan = two_clips()
    effects.set_switches(plan, ["shake"])
    jump, shout = effects.suggestions(moments, settings, plan)
    assert jump.on and jump.label == "Clip 1 at 0:10: shake + replay + boom (now: shake)"
    effects.use_suggestions(moments, settings, plan, [jump.key, shout.key])
    placed = effects.for_plan(moments, settings, plan)
    assert [e.kind for e in placed[0]] == ["shake"]
    assert [e.kind for e in placed[1]] == ["flash", "zoom", "sfx"]
    # Kinds for the whole video again: the same everywhere.
    effects.set_switches(plan, ["shake", "sfx"])
    assert "effects_picked" not in plan.source
    assert [e.kind for e in effects.for_plan(moments, settings, plan)[0]] == ["shake", "sfx"]


def test_a_quick_preview_of_other_ticks_is_a_new_preview(moments, settings):
    from ai_editor.app.videos import shown_in_preview

    plan = two_clips()
    jump, shout = effects.suggestions(moments, settings, plan)
    effects.use_suggestions(moments, settings, plan, [shout.key])
    before = shown_in_preview(settings, plan)
    effects.use_suggestions(moments, settings, plan, [jump.key, shout.key])
    assert shown_in_preview(settings, plan) != before


@needs_ffmpeg
def test_a_render_turns_the_game_down_under_your_voice_and_nothing_else(settings, tmp_path):
    """Mic 300 Hz, game 500 Hz and louder than the voice: the finished video has the
    game turned down against the voice (by the most allowed), the voice as it was."""
    import subprocess

    from ai_editor.render.final import render_plan

    from .test_music import tone_level

    rec = tmp_path / "rec.mkv"
    tone = lambda hz, level: f"sine=frequency={hz}:duration=6:sample_rate=48000,volume={level}"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc=size=320x180:rate=30:duration=6",
                    # FFmpeg's tone is 1/8 of full scale: -23 dB and -13 dB.
                    "-f", "lavfi", "-i", tone(300, 0.8), "-f", "lavfi", "-i", tone(500, 2.4),
                    "-filter_complex", "[1][2]amix=inputs=2:normalize=0[mix]",
                    "-map", "0:v", "-map", "[mix]", "-map", "1:a", "-map", "2:a",
                    "-c:v", "libx264", "-c:a", "pcm_s16le", str(rec)], check=True)
    connection = init_db(settings.db_path)
    connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                       "width, height, duration_sec, imported_at) VALUES (1, 'h', 'local_obs', "
                       "?, 320, 180, 6, 'now')", (str(rec),))
    for index, role in ((1, "mixed"), (2, "mic"), (3, "game")):
        wav = tmp_path / f"track_{index}.wav"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(rec), "-map", f"0:{index}",
                        str(wav)], check=True)
        connection.execute("INSERT INTO audio_tracks (recording_id, stream_index, role, "
                           "extracted_path) VALUES (1, ?, ?, ?)", (index, role, str(wav)))
    connection.commit()
    settings.performance.device = "cpu"
    plan = EditPlan("g_1", "highlights", "t", None, 600, [Segment(1, 1.0, 5.0)],
                    source={"music": False})
    under = render_plan(connection, settings, plan, target=tmp_path / "under.mp4").path
    settings.render.game_under_voice = False
    as_was = render_plan(connection, settings, plan, target=tmp_path / "as_was.mp4").path
    connection.close()
    gap_under = tone_level(under, 500) - tone_level(under, 300)
    gap_as_was = tone_level(as_was, 500) - tone_level(as_was, 300)
    assert gap_as_was - gap_under == pytest.approx(music.MAX_LOWER_DB, abs=2.0)


# --- Even volume: a video without talking isn't blasted (11 Oct) ----------------------------------


def test_a_video_is_never_turned_up_past_where_your_talking_would_be(settings):
    """Short_09 (no talking) was raised 31 dB to YouTube's level, its music with it;
    07 and 08 (a shout each) about 9. The creator talks at -23.7 dB on that stream."""
    from ai_editor.render.final import boost_limit, loudness_filter

    connection = init_db(settings.db_path)
    connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                       "duration_sec, imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 100, "
                       "'2026-10-10T20:00:00')")
    rows = [(t, "speech", 1.0 if t < 40 else 0.0) for t in range(100)]
    rows += [(t, "voice_db", -23.7 if t < 40 else -100.0) for t in range(100)]
    connection.executemany("INSERT INTO signals (recording_id, t_sec, name, value) VALUES "
                           "(1, ?, ?, ?)", rows)
    connection.commit()
    plan = EditPlan("s", "shorts", "t", None, 35, [Segment(1, 60, 95)])
    most = boost_limit(connection, settings, plan)
    assert most == pytest.approx(-14.0 + 23.7)
    assert loudness_filter(-44.9, -33.0, -14.0, most).startswith("volume=9.70dB")   # not 30.9
    assert loudness_filter(-23.4, -3.0, -14.0, most).startswith("volume=4.50dB")    # as before
    # Under 30 seconds of talking in the whole stream: nothing to go by.
    connection.execute("DELETE FROM signals WHERE name = 'speech' AND t_sec >= 20")
    assert boost_limit(connection, settings, plan) is None
    connection.close()


# --- The frozen EP 4 (19 Oct): a piece whose picture stops early is never kept ----------------


@needs_ffmpeg
def test_a_piece_whose_picture_stops_early_is_caught(tmp_path):
    import subprocess

    from ai_editor.errors import MediaProcessingFailed
    from ai_editor.ffmpeg import stream_lengths
    from ai_editor.render.final import check_whole

    def piece(name: str, picture: float, sound: float):
        out = tmp_path / name
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"testsrc=size=160x90:rate=60:duration={picture}", "-f", "lavfi", "-i",
                        f"sine=frequency=440:duration={sound}:sample_rate=48000",
                        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "pcm_f32le", str(out)],
                       check=True)
        return out

    whole = piece("whole.mkv", 5.0, 5.0)
    assert stream_lengths(whole) == {"video": pytest.approx(5.0, abs=0.05),
                                     "audio": pytest.approx(5.0, abs=0.05)}
    check_whole(whole, 5.0)
    frozen = piece("frozen.mkv", 3.0, 5.0)        # the sound carries on: a freeze
    with pytest.raises(MediaProcessingFailed):
        check_whole(frozen, 5.0)


def test_the_picture_and_the_sound_are_read_from_separate_openings(settings, tmp_path):
    """Read once, with four sound tracks mixed, FFmpeg ended long pieces' picture early."""
    from ai_editor.render.audio import AudioChoice
    from ai_editor.render.final import segment_args

    choice = AudioChoice([2, 3, 4, 5], 2, True)
    args = segment_args(tmp_path / "r.mkv", 1784.0, 910.0, choice,
                        settings.render.presets["youtube_1080p60"], (1920, 1080), [],
                        tmp_path / "o.mkv", gpu_decode=True)
    assert args.count("-i") == 2 and args.count(str(tmp_path / "r.mkv")) == 2
    graph = args[args.index("-filter_complex") + 1]
    assert graph.startswith("[0:v:0]") and "[1:2]" in graph and "[0:2]" not in graph
