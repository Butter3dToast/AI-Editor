"""The music from the stream in finished videos, kept out of the way of talking (Phase 2C-3a)."""

from __future__ import annotations

import subprocess

import numpy as np
import pytest

from ai_editor.db import init_db
from ai_editor.recipes.plan import EditPlan, Segment
from ai_editor.render import music
from ai_editor.render.final import music_fades

from .conftest import FFMPEG, needs_ffmpeg

W = music.WINDOW_SEC


def windows(seconds: float, level: float) -> np.ndarray:
    return np.full(int(round(seconds / W)), level)


# --- Kept under the talking ----------------------------------------------------------------


def test_music_well_under_your_voice_is_left_alone():
    """The creator's music sat about 17 dB under their voice: nothing to do."""
    voice = np.concatenate([windows(2, -120), windows(3, -26), windows(2, -120)])
    assert not music.lowering(windows(7, -48), voice).any()


def test_music_covering_the_talking_is_lowered_there_only():
    voice = np.concatenate([windows(2, -120), windows(3, -30), windows(3, -120)])
    cut = music.lowering(windows(8, -40), voice)
    assert cut[int(3 / W)] == pytest.approx(-5.0)        # to 15 dB under the voice
    assert cut[0] == 0 and cut[-1] == 0                    # not before or after
    found = music.stretches(cut)
    assert len(found) == 1 and found[0][2] == pytest.approx(-5.0)


def test_a_blip_at_the_mic_with_nothing_said_doesnt_dip_the_music():
    """7 Oct: a 50 ms blip of the noise gate opening once dipped the music 16 dB."""
    voice = windows(4, -120)
    voice[40] = -47.0
    voice[60] = -35.0          # louder, but over in a moment
    assert not music.lowering(windows(4, -48), voice).any()


def test_a_piece_shorter_than_a_second_works_too():
    """10 Oct: a slide's 0.8 s ends broke the working-out (16 windows, a 20-window second)."""
    voice = windows(0.8, -30)
    cut = music.lowering(windows(0.8, -40), voice)
    assert len(cut) == len(voice) and cut.min() == pytest.approx(-5.0)


def test_the_music_is_never_lowered_by_more_than_the_limit():
    voice = np.concatenate([windows(2, -30), windows(2, -120)])
    cut = music.lowering(windows(4, -10), voice)
    assert cut.min() == pytest.approx(-music.MAX_LOWER_DB)


def test_lowered_stretches_close_together_become_one():
    cut = np.zeros(100)
    cut[10:20] = -4
    cut[24:30] = -6           # 0.2 s later: don't bob up in between
    cut[80:90] = -3
    assert music.stretches(cut) == [(0.5, 1.5, -6.0), (4.0, 4.5, -3.0)]


def test_the_lowering_eases_down_and_back_up():
    text = music.volume_text([(2.0, 4.0, -6.0)])
    assert text.startswith("volume='1-") and text.endswith("':eval=frame")
    assert "(t-1.850)/0.15" in text and "(4.500-t)/0.5" in text
    assert music.volume_text([]) is None


# --- In the mix ---------------------------------------------------------------------------------


def test_the_music_layer_is_the_mix_with_the_other_tracks_turned_upside_down():
    source = music.MusicSource([1], [2, 3, 4])
    pieces, label = music.graph(source, [], 30.0, 48000, fade_in=True, fade_out=False)
    assert label == "[music]"
    assert any(p.startswith("[0:2]") and "volume=-1[mus_sub0]" in p for p in pieces)
    assert "amix=inputs=4:normalize=0" in pieces[-1]
    assert "afade=t=in:d=0.300" in pieces[-1] and "t=out" not in pieces[-1]


def test_the_music_fades_at_cuts_but_not_where_the_recording_carries_on():
    plan = EditPlan("p", "highlights", "t", None, 600,
                    [Segment(1, 0, 10), Segment(1, 10.0, 20), Segment(1, 50, 60)])
    assert music_fades(plan) == [(True, False), (False, True), (True, True)]


def test_a_video_can_have_its_music_switched_off(settings, tmp_path):
    from ai_editor.render.audio import AudioChoice
    from ai_editor.config import RenderPreset
    from ai_editor.render.final import segment_args

    choice = AudioChoice([2, 3], 2, True, music=music.MusicSource([1], [2, 3]))
    args = segment_args(tmp_path / "rec.mkv", 0.0, 5.0, choice,
                        RenderPreset(width=1920, height=1080, fps=60, bitrate="16M"),
                        (1920, 1080), ["-c:v", "libx264"], tmp_path / "o.mkv", gpu_decode=False)
    graph = args[args.index("-filter_complex") + 1]
    assert "[a0][a1][music]amix=inputs=3:normalize=0" in graph
    choice.music = None
    graph = segment_args(tmp_path / "rec.mkv", 0.0, 5.0, choice,
                         RenderPreset(width=1920, height=1080, fps=60, bitrate="16M"),
                         (1920, 1080), ["-c:v", "libx264"], tmp_path / "o.mkv", gpu_decode=False)
    assert "[music]" not in " ".join(graph)


# --- The real thing ------------------------------------------------------------------------------


def tone_level(path, hz: float) -> float:
    """How loud one pitch is in a video's sound (dB)."""
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-ac", "1", "-ar", "8000", "-f",
                          "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x)))) / len(x)
    freqs = np.fft.rfftfreq(len(x), 1 / 8000)
    near = (freqs > hz - 5) & (freqs < hz + 5)
    return float(20 * np.log10(spectrum[near].max() + 1e-12))


@needs_ffmpeg
def test_the_music_is_recovered_from_the_mix_and_nothing_else_is(settings, tmp_path):
    """Mic 300 Hz, game 500 Hz, music 700 Hz: OBS's mix is all three; the
    video gets mic and game from their own tracks and the music from the mix."""
    rec = tmp_path / "rec.mkv"
    tone = lambda hz: f"sine=frequency={hz}:duration=6:sample_rate=48000"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc=size=320x180:rate=30:duration=6",
                    "-f", "lavfi", "-i", tone(300), "-f", "lavfi", "-i", tone(500),
                    "-f", "lavfi", "-i", tone(700), "-filter_complex",
                    "[1][2][3]amix=inputs=3:normalize=0[mix]",
                    "-map", "0:v", "-map", "[mix]", "-map", "1:a", "-map", "2:a",
                    "-c:v", "libx264", "-c:a", "pcm_s16le", str(rec)], check=True)
    conn = init_db(settings.db_path)
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, width, "
                 "height, duration_sec, imported_at) VALUES (1, 'h', 'local_obs', ?, 320, 180, "
                 "6, 'now')", (str(rec),))
    for index, role in ((1, "mixed"), (2, "mic"), (3, "game")):
        wav = tmp_path / f"track_{index}.wav"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(rec), "-map", f"0:{index}",
                        str(wav)], check=True)
        conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role, extracted_path) "
                     "VALUES (1, ?, ?, ?)", (index, role, str(wav)))
    conn.commit()
    from ai_editor.render.final import render_plan

    settings.performance.device = "cpu"
    plan = EditPlan("m_1", "highlights", "t", None, 600, [Segment(1, 1.0, 5.0)])
    with_music = render_plan(conn, settings, plan, target=tmp_path / "with.mp4").path
    plan.source["music"] = False
    without = render_plan(conn, settings, plan, target=tmp_path / "without.mp4").path
    conn.close()
    assert tone_level(with_music, 700) > tone_level(without, 700) + 30   # the music, back in
    # Mic and game once each, not twice (from the mix as well, which would be +6 dB);
    # the loudness pass sets each video a little differently.
    for hz in (300, 500):
        assert tone_level(with_music, hz) == pytest.approx(tone_level(without, hz), abs=3.0)
