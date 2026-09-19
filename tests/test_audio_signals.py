"""Per-second loudness, silence, spikes, speech coverage, window spreading."""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from ai_editor.analysis import audio_signals as sig


def _write_wav(path, pieces, rate=16_000):
    """pieces: list of (seconds, amplitude) -- amplitude 0 means silence."""
    t = np.arange(rate) / rate
    chunks = [
        (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        for seconds, amp in pieces
        for _ in range(seconds)
    ]
    sf.write(path, np.concatenate(chunks), rate, subtype="PCM_16")
    return path


def test_per_second_db_tracks_volume(tmp_path):
    wav = _write_wav(tmp_path / "a.wav", [(2, 0.5), (2, 0.0), (1, 0.05)])
    db = sig.per_second_db(wav)
    assert len(db) == 5
    # A sine at amplitude 0.5 has RMS 0.354, about -9 dBFS.
    assert db[0] == pytest.approx(-9.0, abs=0.5)
    assert db[2] == sig.FLOOR_DB, "digital silence is the floor, not -infinity"
    assert db[4] == pytest.approx(-29.0, abs=0.5)


def test_per_second_db_counts_a_partial_last_second(tmp_path):
    rate = 16_000
    audio = np.full(int(rate * 2.5), 0.1, dtype=np.float32)
    sf.write(tmp_path / "b.wav", audio, rate)
    assert len(sig.per_second_db(tmp_path / "b.wav")) == 3


def test_per_second_db_reports_progress(tmp_path):
    wav = _write_wav(tmp_path / "c.wav", [(3, 0.2)])
    seen: list[float] = []
    sig.per_second_db(wav, seen.append)
    assert seen[-1] == 1.0


def test_zscore_finds_the_spike():
    values = np.array([-30, -31, -29, -30, -32, -10, -30, -31], dtype=np.float32)
    z = sig.robust_zscore(values)
    assert int(np.argmax(z)) == 5
    assert z[5] > 3


def test_zscore_ignores_silence_when_setting_the_baseline():
    """Long silent stretches mustn't make ordinary talking look like a spike."""
    values = np.array([-100] * 50 + [-30, -31, -29, -30], dtype=np.float32)
    z = sig.robust_zscore(values)
    assert np.all(np.abs(z[50:]) < 3)


def test_zscore_of_flat_audio_is_zero():
    assert np.all(sig.robust_zscore(np.full(10, -30.0, dtype=np.float32)) == 0)


def test_silence_needs_every_track_quiet():
    voice = np.array([-60, -60, -20, -60], dtype=np.float32)
    game = np.array([-60, -10, -60, -60], dtype=np.float32)
    mask = sig.silence_mask(voice, game, threshold_db=-50)
    assert mask.tolist() == [1, 0, 0, 1]


def test_speech_coverage_splits_words_across_seconds():
    coverage = sig.speech_coverage([(0.5, 1.5), (3.0, 3.25)], seconds=5)
    assert coverage.tolist() == pytest.approx([0.5, 0.5, 0.0, 0.25, 0.0])


def test_speech_coverage_never_exceeds_one():
    coverage = sig.speech_coverage([(0.0, 1.0), (0.2, 0.9)], seconds=2)
    assert coverage[0] == 1.0


def test_window_starts_cover_the_whole_recording():
    starts = sig.window_starts(10, window=2)
    assert starts[0] == 0 and starts[-1] == 8


def test_spread_takes_the_strongest_window_per_second():
    """A laugh heard by one window isn't diluted by its quieter neighbours."""
    starts = sig.window_starts(5, window=2)          # windows at 0,1,2,3
    scores = np.array([0.0, 0.9, 0.1, 0.0], dtype=np.float32)
    per_second = sig.spread_to_seconds(scores, starts, 2, 5)[:, 0]
    assert per_second.tolist() == pytest.approx([0.0, 0.9, 0.9, 0.1, 0.0])


def test_top_moments_keeps_them_apart():
    """One long scream shouldn't fill the list with neighbouring seconds."""
    values = np.zeros(200, dtype=np.float32)
    values[10:15] = [0.9, 0.95, 0.99, 0.95, 0.9]
    values[100] = 0.8
    found = sig.top_moments(values, count=5, min_gap=30, threshold=0.5)
    assert found == [(12, pytest.approx(0.99)), (100, pytest.approx(0.8))]


def test_top_moments_respects_the_threshold():
    values = np.array([0.1, 0.2, 0.25], dtype=np.float32)
    assert sig.top_moments(values, count=3, min_gap=1, threshold=0.3) == []


def test_zscore_measured_against_talking_level():
    """Quiet gaps between sentences mustn't hide a shout."""
    rng = np.random.default_rng(0)
    talking = rng.normal(-30, 2, 60).astype(np.float32)
    gaps = rng.normal(-60, 2, 60).astype(np.float32)
    values = np.concatenate([talking, gaps, np.array([-18.0], dtype=np.float32)])
    is_talking = np.concatenate([np.ones(60), np.zeros(60), np.ones(1)])

    against_everything = sig.robust_zscore(values)[-1]
    against_talking = sig.robust_zscore(values, baseline_mask=is_talking)[-1]
    assert against_talking > 3 > against_everything


def test_zscore_falls_back_when_there_is_little_talking():
    values = np.array([-30, -31, -29, -10, -60, -60], dtype=np.float32)
    mask = np.array([1, 0, 0, 0, 0, 0])
    assert np.allclose(sig.robust_zscore(values, baseline_mask=mask), sig.robust_zscore(values))
