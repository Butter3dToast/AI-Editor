"""The confirmation click: it must never reach the stream."""

from __future__ import annotations

import wave

from ai_editor.companion.sound import click_file


def test_the_click_is_short(tmp_path):
    path = click_file(tmp_path)
    with wave.open(str(path)) as f:
        assert f.getnchannels() == 1
        assert 0.05 < f.getnframes() / f.getframerate() < 0.6


def test_it_starts_with_silence_so_the_sound_device_can_wake(tmp_path):
    """Without this, Windows swallows the first sound after a quiet spell."""
    import array

    from ai_editor.companion.sound import SAMPLE_RATE, SILENCE_LEAD_SECONDS

    with wave.open(str(click_file(tmp_path))) as f:
        samples = array.array("h", f.readframes(f.getnframes()))
    lead = int(SAMPLE_RATE * SILENCE_LEAD_SECONDS)
    assert lead > 0
    assert not any(samples[:lead])


def peak(path) -> int:
    import array

    with wave.open(str(path)) as f:
        return max(abs(s) for s in array.array("h", f.readframes(f.getnframes())))


def test_it_is_loud_enough_to_notice(tmp_path):
    """Two earlier versions were too quiet to hear over a game."""
    assert peak(click_file(tmp_path)) > 0.85 * 32767


def test_the_volume_setting_changes_the_sound(tmp_path):
    quiet = click_file(tmp_path, level=0.3)
    loud = click_file(tmp_path, level=0.9)
    assert quiet != loud, "a different volume must not reuse the old file"
    assert peak(quiet) < peak(loud)


def test_the_two_markers_sound_different(tmp_path):
    moment = click_file(tmp_path).read_bytes()
    short = click_file(tmp_path, short_worthy=True).read_bytes()
    assert moment != short


def test_it_is_only_made_once(tmp_path):
    first = click_file(tmp_path)
    stamp = first.stat().st_mtime_ns
    assert click_file(tmp_path).stat().st_mtime_ns == stamp
