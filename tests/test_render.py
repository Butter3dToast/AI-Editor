"""Finished videos: the right sound, beeps out, frame-exact joins."""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from ai_editor.db import init_db
from ai_editor.recipes.plan import EditPlan, Segment
from ai_editor.render.audio import beep_filters, choose_tracks, find_beeps
from ai_editor.render.final import bits, frame_exact, segment_args

from .conftest import make_video, needs_ffmpeg

RATE = 48000


def noise(seconds: float, level: float = 0.05, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).normal(0, level, int(seconds * RATE)).astype(np.float32)


def write(path, mono):
    sf.write(str(path), np.stack([mono, mono], axis=1), RATE)
    return path


# --- Beeps -------------------------------------------------------------------------------


def test_a_recorded_click_is_found_after_its_marker(tmp_path):
    """26 Sep: the click reached the mic about 0.6 s after each press."""
    sound = noise(30)
    at = int(10.6 * RATE)
    sound[at:at + int(0.16 * RATE)] += 0.3 * np.sin(2 * np.pi * 1000 * np.arange(int(0.16 * RATE)) / RATE)
    beeps = find_beeps(write(tmp_path / "mic.wav", sound), [10.0, 20.0])
    assert len(beeps) == 1  # none after the second press: its click wasn't recorded
    assert beeps[0][0] < 10.6 < 10.76 < beeps[0][1]


def test_ordinary_sound_is_never_taken_for_a_beep(tmp_path):
    t = np.arange(30 * RATE) / RATE
    voice = noise(30) + 0.2 * np.sin(2 * np.pi * 180 * t) * (np.sin(2 * np.pi * 3 * t) > 0)
    assert find_beeps(write(tmp_path / "mic.wav", voice.astype(np.float32)), [5.0, 15.0]) == []


def test_beep_filters_only_touch_their_own_segment():
    beeps = [(100.55, 101.05), (300.0, 300.5)]
    inside = beep_filters(beeps, 90.0, 120.0)
    assert inside and all("between(t,10.550,11.050)" in f for f in inside)
    assert beep_filters(beeps, 200.0, 250.0) == []


# --- Which tracks ------------------------------------------------------------------------


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    connection.execute(
        "INSERT INTO recordings (id, content_hash, source_type, source_file, duration_sec, "
        "imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 60, '2026-09-27T12:00:00')")
    connection.commit()
    yield connection
    connection.close()


def add_tracks(conn, tmp_path, sounds: dict[str, np.ndarray]):
    for index, (role, sound) in enumerate(sounds.items(), start=1):
        path = write(tmp_path / f"track_{index}.wav", sound)
        conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role, extracted_path) "
                     "VALUES (1, ?, ?, ?)", (index, role, str(path)))
    conn.commit()


def test_separate_tracks_with_the_stream_music_as_its_own_layer(conn, settings, tmp_path):
    mic, game, discord, music = (noise(60, seed=n) for n in range(4))
    add_tracks(conn, tmp_path, {"mixed": mic + game + discord + music, "mic": mic, "game": game,
                                "voice_chat": discord})
    choice = choose_tracks(conn, settings, 1)
    assert choice.separate and choice.streams == [2, 3, 4] and choice.voice == 2
    # The music: the mix with every separate track taken away (render/music.py).
    assert choice.music.added == [1] and choice.music.taken_away == [2, 3, 4]
    assert "music from your stream" in choice.describe()
    assert choose_tracks(conn, settings, 1, music=False).music is None


def test_copied_tracks_use_the_mix_as_the_stream_sounded(conn, settings, tmp_path):
    """Before 27 Sep the creator's "mic" track was the whole mix again."""
    everything, rest = noise(60, seed=1), noise(60, seed=2)
    add_tracks(conn, tmp_path, {"mixed": everything, "mic": everything.copy(), "game": rest,
                                "voice_chat": rest.copy()})
    choice = choose_tracks(conn, settings, 1)
    assert not choice.separate and choice.streams == [1] and choice.music is None
    assert "music and all" in choice.describe()


def test_discord_can_be_left_out(conn, settings, tmp_path):
    mic, game, discord = (noise(60, seed=n) for n in range(3))
    add_tracks(conn, tmp_path, {"mixed": mic + game + discord, "mic": mic, "game": game,
                                "voice_chat": discord})
    settings.render.include_voice_chat = False
    choice = choose_tracks(conn, settings, 1)
    assert choice.streams == [2, 3]
    assert choice.music.taken_away == [2, 3, 4]  # Discord is in the mix all the same


def test_a_spotify_track_of_its_own_is_used_as_it_is(conn, settings, tmp_path):
    """OBS track 5 (manual 7.3): nothing to take away."""
    mic, game, discord, music = (noise(60, seed=n) for n in range(4))
    add_tracks(conn, tmp_path, {"mixed": mic + game + discord + music, "mic": mic, "game": game,
                                "voice_chat": discord, "music": music})
    choice = choose_tracks(conn, settings, 1)
    assert choice.streams == [2, 3, 4] and choice.music.added == [5] and choice.music.own_track


# --- The render -------------------------------------------------------------------------


def test_lengths_are_whole_frames_so_joins_never_drift():
    assert frame_exact(10.0083, 60) == pytest.approx(10.0)
    assert frame_exact(10.01, 60) * 60 == pytest.approx(601)
    assert bits("16M") == 16_000_000 and bits("320k") == 320_000


def test_separate_tracks_are_added_together_and_only_the_voice_is_filtered(settings, tmp_path):
    from ai_editor.render.audio import AudioChoice

    preset = settings.render.presets["youtube_1080p60"]
    choice = AudioChoice([2, 3, 4], 2, True, beeps=[(12.0, 12.5)])
    graph = segment_args(tmp_path / "r.mkv", 10.0, 5.0, choice, preset, (1920, 1080), [],
                         tmp_path / "p.mkv", gpu_decode=False)
    graph = graph[graph.index("-filter_complex") + 1].split(";")
    assert "amix=inputs=3:normalize=0" in graph[-1]
    assert "bandreject" in graph[1] and "bandreject" not in graph[2] + graph[3]
    assert "scale" not in graph[0]  # same size as the recording: left alone


@needs_ffmpeg
def test_a_plan_renders_to_the_preset_frame_exact(conn, settings, tmp_path):
    from ai_editor.ffmpeg import probe
    from ai_editor.render.final import render_plan

    video = make_video(tmp_path / "rec.mp4", width=1280, height=720, fps=60, seconds=4)
    conn.execute("UPDATE recordings SET source_file = ?, width = 1280, height = 720", (str(video),))
    conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role) VALUES (1, 1, 'mixed')")
    conn.commit()
    settings.performance.device = "cpu"
    plan = EditPlan("test_1", "highlights", "Test", None, 60,
                    [Segment(1, 0.5, 1.5), Segment(1, 2.0, 3.2)])
    result = render_plan(conn, settings, plan)
    info = probe(result.path)
    assert (info.width, info.height, round(info.fps)) == (1920, 1080, 60)
    assert info.duration_sec == pytest.approx(2.2, abs=0.05)
    assert len(info.audio) == 1
    assert not list(result.path.parent.glob("*rendering*"))  # nothing half-made left behind


def test_loudness_is_one_gain_with_only_the_peaks_held_down():
    from ai_editor.render.final import MAX_LIMITING_DB, TRUE_PEAK_DB, loudness_filter

    assert loudness_filter(-16.7, -1.4, -14.0).startswith("volume=2.70dB")
    assert "alimiter" in loudness_filter(-16.7, -1.4, -14.0)
    # A mix peaking at full scale 20 LU under the target is raised only as far
    # as the limiter can take without squashing it.
    capped = loudness_filter(-34.0, 0.0, -14.0)
    assert capped.startswith(f"volume={TRUE_PEAK_DB + MAX_LIMITING_DB:.2f}dB")


# --- Captions -----------------------------------------------------------------------------


def test_captions_are_bold_white_with_a_black_edge_placed_by_recipe(settings):
    from ai_editor.analysis.captions import Cue
    from ai_editor.render.captions import ass_document

    cues = [Cue(1.0, 3.5, "They literally drove a car {at} me\\")]
    doc = ass_document(cues, width=1920, height=1080, style=settings.captions, place=0.22)
    style = next(line for line in doc.splitlines() if line.startswith("Style:")).split(",")
    assert style[1] == "Arial" and style[2] == "64" and style[7] == "-1"  # font, size, bold
    assert style[3] == "&H00FFFFFF" and style[5] == "&H00000000"        # white, black edge
    assert style[18] == "2" and style[21] == str(round(1080 * 0.22))     # bottom centre, 22% up
    assert "Dialogue: 0,0:00:01.00,0:00:03.50,Default,,0,0,0,,They literally drove a car (at) me/" in doc


def test_captions_scale_with_the_picture(settings):
    from ai_editor.render.captions import ass_document

    style = next(line for line in ass_document([], width=1080, height=1920, style=settings.captions,
                                               place=0.12).splitlines() if line.startswith("Style:"))
    assert style.split(",")[2] == str(round(64 * 1920 / 1080))


def test_captions_are_off_unless_turned_on(settings):
    assert not settings.captions.highlights and not settings.captions.lets_play


@needs_ffmpeg
def test_captions_burn_in_only_when_asked(conn, settings, tmp_path):
    from ai_editor.render.final import render_plan

    video = make_video(tmp_path / "rec.mp4", width=1920, height=1080, fps=60, seconds=4)
    conn.execute("UPDATE recordings SET source_file = ?, width = 1920, height = 1080", (str(video),))
    conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role) VALUES (1, 1, 'mixed')")
    for i, (word, start, end) in enumerate([("Nice", 0.6, 0.9), ("shot!", 1.0, 1.4)]):
        conn.execute("INSERT INTO transcript_words (recording_id, idx, word, start_sec, end_sec, "
                     "confidence) VALUES (1, ?, ?, ?, ?, 0.95)", (i, word, start, end))
    conn.commit()
    settings.performance.device = "cpu"
    plan = EditPlan("test_2", "highlights", "Test", None, 60, [Segment(1, 0.5, 3.0)])
    assert render_plan(conn, settings, plan).captions is None  # off by default
    assert render_plan(conn, settings, plan, captions=True).captions == 1


@needs_ffmpeg
def test_a_lets_play_from_a_mixed_track_is_never_captioned(conn, settings, tmp_path):
    """EP 1: the mixed track's transcript had Anca's lines in it, already subtitled by the game."""
    from ai_editor.render.final import render_plan

    video = make_video(tmp_path / "rec.mp4", width=1920, height=1080, fps=60, seconds=4)
    conn.execute("UPDATE recordings SET source_file = ?, width = 1920, height = 1080", (str(video),))
    conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role) VALUES (1, 1, 'mixed')")
    conn.execute("INSERT INTO transcript_words (recording_id, idx, word, start_sec, end_sec, confidence) "
                 "VALUES (1, 0, 'Petronius?', 1.0, 1.6, 0.95)")
    conn.commit()
    settings.performance.device = "cpu"
    plan = EditPlan("lp", "letsplay", "Test", None, 60, [Segment(1, 0.5, 3.0, kind="piece")])
    result = render_plan(conn, settings, plan, captions=True)
    assert result.captions == 0 and "mixed sound track" in result.notes[0]


# --- Let's Play parts ---------------------------------------------------------------------


def test_the_episode_number_comes_from_the_recording_name():
    from ai_editor.render.parts import episode_number

    assert episode_number("Lets Play - The Blood Of DawnWalker - EP 1") == 1
    assert episode_number(None, "Dawnwalker EP12 final") == 12
    assert episode_number("Episode 3") == 3
    assert episode_number("2026-09-19 11-56-48", "Repeat after me") is None  # "Repeat" isn't "EP"


def test_each_part_is_named_ready_to_upload_with_its_title_card(settings):
    from ai_editor.render.parts import part_numbers, part_path, part_plan, title_card

    plan = EditPlan("letsplay_x_1", "letsplay", "T", "The Blood of Dawnwalker", 0,
                    [Segment(1, 0, 900, kind="piece", part=1), Segment(1, 960, 1800, kind="piece", part=1),
                     Segment(1, 1800, 3600, kind="piece", part=2)])
    assert part_numbers(plan) == [1, 2]
    assert [s.src_in for s in part_plan(plan, 1).segments] == [0, 960]
    assert part_path(settings, plan, 1, 2).name == "The Blood of Dawnwalker - EP 1 - Part 2.mp4"
    assert part_path(settings, plan, 1, 2, captions=True).name.endswith("Part 2 captions.mp4")
    assert title_card(settings, 2, 1) is None  # off unless asked for: the YouTube title says it
    settings.lets_play.title_card = "Ep {episode} – Part {part}"
    assert title_card(settings, 2, 1) == "Ep 2 – Part 1"


def test_the_title_card_is_big_centred_and_fades(settings):
    from ai_editor.analysis.captions import Cue
    from ai_editor.render.captions import ass_document

    doc = ass_document([], width=1920, height=1080, style=settings.captions, place=0.22,
                       title=Cue(0.0, 4.0, "Ep 1 – Part 2"))
    title = next(line for line in doc.splitlines() if line.startswith("Style: Title")).split(",")
    assert int(title[2]) > settings.captions.size and title[18] == "5"  # larger, middle of the picture
    assert doc.rstrip().endswith(r"Title,,0,0,0,,{\fad(500,500)}Ep 1 – Part 2")


@needs_ffmpeg
def test_a_part_renders_with_its_title_card(conn, settings, tmp_path):
    from ai_editor.render.final import render_plan

    video = make_video(tmp_path / "rec.mp4", width=1920, height=1080, fps=60, seconds=4)
    conn.execute("UPDATE recordings SET source_file = ?, width = 1920, height = 1080", (str(video),))
    conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role) VALUES (1, 1, 'mixed')")
    conn.commit()
    settings.performance.device = "cpu"
    plan = EditPlan("lp", "letsplay", "Test", None, 60, [Segment(1, 0.5, 3.0, kind="piece", part=1)])
    result = render_plan(conn, settings, plan, title="Ep 1 – Part 1")
    assert result.path.is_file() and result.captions is None


def test_a_video_open_in_a_player_is_kept_and_the_new_one_saved_beside_it(tmp_path):
    """10 Oct: rendering a Short again while the last one was playing stopped at 100%."""
    import sys

    from ai_editor.render.final import move_into_place

    target = tmp_path / "short.mp4"
    target.write_bytes(b"old")
    new = tmp_path / "short (rendering).mp4"
    new.write_bytes(b"new")
    notes = []
    if sys.platform == "win32":
        with open(target, "rb"):  # playing in VLC
            saved = move_into_place(new, target, notes, tries=2)
        assert saved.name == "short (2).mp4" and saved.read_bytes() == b"new"
        assert target.read_bytes() == b"old" and "open in a video player" in notes[0]
    new.write_bytes(b"newer")
    assert move_into_place(new, target, notes) == target and target.read_bytes() == b"newer"
