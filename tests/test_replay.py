"""Slow-motion replays after the big moments (Phase 2C-2b)."""

from __future__ import annotations

import json
import subprocess

import numpy as np
import pytest

from ai_editor import effects
from ai_editor.analysis.captions import Word
from ai_editor.db import init_db
from ai_editor.effects import Effect
from ai_editor.recipes.plan import EditPlan, Segment
from ai_editor.render import replay, slide

from .conftest import FFMPEG, make_video, needs_ffmpeg


def plan_of(*segments, recipe="highlights"):
    return EditPlan("r", recipe, "t", None, 600, list(segments))


def big(at):
    return Effect("replay", at, replay.LENGTH_SEC, "impact", label="Triple kill")


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                       "duration_sec, imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 600, 'now')")
    connection.commit()
    yield connection
    connection.close()


def test_a_replay_goes_just_after_its_moment_and_replays_the_seconds_before(conn):
    plan = plan_of(Segment(1, 100.0, 130.0))
    found = replay.inserts(conn, plan, [[big(110.0)]], [30.0], [])
    r = found[0][0]
    assert (r.offset, r.window, r.window_length) == (11.5, 7.5, 3.0)   # 1.5 s after; 2.5 before to 0.5 after
    assert r.length == 6.0 and replay.extra(found) == [6.0]
    assert replay.shift(5.0, found[0]) == 5.0 and replay.shift(20.0, found[0]) == 26.0


def test_it_waits_for_a_gap_between_your_words(conn):
    conn.executemany("INSERT INTO transcript_words (recording_id, idx, word, start_sec, end_sec) "
                     "VALUES (1, ?, ?, ?, ?)", [(0, "no", 111.2, 111.9), (1, "way", 112.0, 112.4)])
    conn.commit()
    r = replay.inserts(conn, plan_of(Segment(1, 100.0, 130.0)), [[big(110.0)]], [30.0], [])[0][0]
    assert 11.9 <= r.offset <= 12.6     # not inside "no" or "way"


def test_none_at_a_clips_very_edge_or_inside_a_slide_or_over_a_shorts_limit(conn):
    edge = replay.inserts(conn, plan_of(Segment(1, 100.0, 111.0)), [[big(110.0)]], [11.0], [])
    assert edge == [[]]       # it would go after the clip ends
    two = plan_of(Segment(1, 100.0, 112.5), Segment(1, 200.0, 220.0))
    assert replay.inserts(conn, two, [[big(110.0)], []], [12.5, 20.0], [0.0])[0]
    slid = replay.inserts(conn, two, [[big(110.0)], []], [12.5, 20.0], [0.8])
    assert slid[0] == []       # 11.5 s is inside the slide's 0.8 s and the 0.5 s before it
    short = plan_of(Segment(1, 100.0, 156.0), recipe="shorts")
    assert replay.inserts(conn, short, [[big(110.0)]], [56.0], [], longest=60.0) == [[]]
    assert replay.inserts(conn, short, [[big(110.0)]], [56.0], [], longest=None)[0]


def test_a_clip_with_a_replay_becomes_three_pieces_and_the_music_runs_on(conn):
    found = replay.inserts(conn, plan_of(Segment(1, 100.0, 130.0)), [[big(110.0)]], [30.0], [])
    items = slide.layout([30.0], [], found, [[6.0]])
    assert [type(i).__name__ for i in items] == ["Piece", "Replay", "Piece"]
    before, middle, after = items
    assert (before.offset, before.length, before.cut_in, before.soft_out) == (0.0, 11.5, True, True)
    assert (middle.length, middle.music_skip) == (6.0, 0.0)
    assert (after.offset, after.length, after.soft_in, after.cut_in) == (11.5, 18.5, True, False)
    assert after.music_skip == 6.0


def test_replays_are_off_unless_switched_on_and_only_on_big_moments(conn, settings):
    plan = plan_of(Segment(1, 100.0, 130.0))
    assert replay.for_plan(conn, settings, plan, 60) == [[]]
    from ai_editor.effects import placement

    triple = placement.Moment(0, 110, 1.0, 0.0, big=True, at=110.0, label="Triple kill",
                              replay=True)
    single = placement.Moment(0, 110, 1.0, 0.0, big=True, at=110.0, label="Kill")
    assert [e.kind for e in placement.effects_at(triple, 110.0, ["replay"])] == ["replay"]
    assert placement.effects_at(single, 110.0, ["replay"]) == []


# --- The real thing ---------------------------------------------------------------------------


def frame(path, seconds) -> np.ndarray:
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(path),
                          "-frames:v", "1", "-vf", "scale=96:54", "-f", "rawvideo", "-pix_fmt",
                          "gray", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).astype(float)


def tone_level(path, start, seconds, hz) -> float:
    """How strong one tone is in a stretch of the video's sound (relative)."""
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{start}", "-t", f"{seconds}",
                          "-i", str(path), "-ac", "1", "-ar", "8000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1 / 8000)
    return float(spectrum[np.abs(freqs - hz) < 8].max())


@needs_ffmpeg
def test_a_render_replays_the_moment_at_half_speed_with_the_game_and_no_voices(conn, settings,
                                                                               tmp_path):
    from ai_editor.ffmpeg import probe
    from ai_editor.render.final import render_plan

    # Three tracks: the mix (220 Hz), the mic (330 Hz), the game (440 Hz).
    video = make_video(tmp_path / "rec.mp4", width=640, height=360, fps=30, seconds=60,
                       audio_tracks=3)
    conn.execute("UPDATE recordings SET source_file = ?, width = 640, height = 360, duration_sec = 60",
                 (str(video),))
    import soundfile as sf

    t = np.arange(60 * 48000) / 48000
    tones = {"mixed": 220, "mic": 330, "game": 440}
    for index, (role, hz) in enumerate(tones.items(), start=1):
        wav = tmp_path / f"{role}.wav"     # the tracks AI-Editor extracts at import
        sf.write(str(wav), (0.2 * np.sin(2 * np.pi * hz * t)).astype(np.float32), 48000)
        conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role, extracted_path) "
                     "VALUES (1, ?, ?, ?)", (index, role, str(wav)))
    # A triple kill at 45 s (League's own event, logged by the Companion).
    conn.execute("INSERT INTO companion_events (session_id, event_type, wall_clock, "
                 "recording_time_sec, recording_id, payload_json) VALUES ('s', 'league', 'now', "
                 "45.0, 1, ?)", (json.dumps({"kind": "multikill", "streak": 3, "text": "Triple kill",
                                             "match": "m"}),))
    conn.commit()
    settings.performance.device = "cpu"
    settings.render.include_stream_music = False
    plan = plan_of(Segment(1, 40.0, 52.0))
    effects.set_switches(plan, ["replay"])
    slow = render_plan(conn, settings, plan, target=tmp_path / "replay.mp4")
    assert slow.length_sec == pytest.approx(18.0)
    assert probe(slow.path).duration_sec == pytest.approx(18.0, abs=0.1)
    effects.set_switches(plan, [])
    plain = render_plan(conn, settings, plan, target=tmp_path / "plain.mp4")
    same = lambda a, b: np.abs(a - b).mean() < 3
    # Up to 6.5 s: the clip as it was. 6.5-12.5: 42.5-45.5 s again, at half speed.
    # Then the rest of the clip, 6 s later than before.
    assert same(frame(slow.path, 3.0), frame(plain.path, 3.0))
    assert same(frame(slow.path, 6.5 + 2.0), frame(plain.path, 2.5 + 1.0))
    assert same(frame(slow.path, 6.5 + 4.0), frame(plain.path, 2.5 + 2.0))
    assert same(frame(slow.path, 14.0), frame(plain.path, 8.0))
    # The replay's sound: the game (440 Hz), not the mic (330 Hz).
    game, mic = tone_level(slow.path, 7.5, 4.0, 440), tone_level(slow.path, 7.5, 4.0, 330)
    assert game > 20 * mic
    assert tone_level(slow.path, 1.0, 4.0, 330) > 20 * mic   # the mic is there outside it


def test_chapters_after_a_replay_start_later():
    from ai_editor.publish import placed, sections

    plan = plan_of(Segment(1, 100.0, 130.0), Segment(1, 200.0, 230.0))
    assert [round(t) for t, _ in placed(plan, 60, [], [6.0, 0.0])] == [0, 36]
    assert [round(s.end) for s in sections(plan, 60, 300.0, [], [6.0, 0.0])] == [36, 66]


def test_the_review_list_times_moments_after_a_replay_later(conn, settings):
    conn.executemany(
        "INSERT INTO companion_events (session_id, event_type, wall_clock, recording_time_sec, "
        "recording_id, payload_json) VALUES ('s', 'league', 'now', ?, 1, ?)",
        [(110.0, json.dumps({"kind": "multikill", "streak": 3, "text": "Triple kill", "match": "m"})),
         (125.0, json.dumps({"kind": "ace", "text": "Ace", "match": "m"}))])
    conn.commit()
    settings.effects.highlights = ["shake", "replay"]
    settings.effects.highlights_per_min = 6.0
    plan = plan_of(Segment(1, 100.0, 130.0))
    labels = [label for label, _ in effects.moments(conn, settings, plan)]
    # One replay per clip: the triple kill's. The ace comes 6 s later in the video.
    assert labels == ["Clip 1 at 0:10: Triple kill: shake + replay", "Clip 1 at 0:31: Ace: shake"]
