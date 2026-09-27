"""Brightness, motion and the HUD, from one grey frame per second."""

from __future__ import annotations

import numpy as np

from ai_editor.analysis.picture import HEIGHT, WIDTH, picture_signals


def frames_of(seconds: int, *, hud: set[int], black: set[int] = frozenset()):
    """Gameplay: a smooth world that moves, with an object crossing it. The HUD:
    a bar that stays put. Black: black."""
    x = np.arange(WIDTH)[None, :]
    y = np.arange(HEIGHT)[:, None]
    frames = np.zeros((seconds, HEIGHT, WIDTH), dtype=np.uint8)
    for t in range(seconds):
        if t in black:
            frames[t] = 0  # full-range grey: black is 0
            continue
        world = 90 + 40 * np.sin((x + 13 * t) / 37.0) * np.cos((y - 5 * t) / 29.0)
        frames[t] = world.astype(np.uint8)
        left = (t * 23) % (WIDTH - 60)
        frames[t, 100:160, left:left + 60] = 200  # something moving through the scene
        if t in hud:
            frames[t, 250:258, 10:120] = 230  # a health bar, same place every second
    return frames


def test_the_hud_is_there_in_play_and_gone_in_a_cutscene():
    play = set(range(0, 40)) | set(range(60, 100))  # 20..60 minus: a cutscene at 40-60
    signals = picture_signals(frames_of(100, hud=play))
    hud = np.array(signals["hud"])
    assert hud[:40].mean() > 3 * hud[40:60].mean()
    assert hud[60:].mean() > 3 * hud[40:60].mean()


def test_black_and_still_is_measured():
    signals = picture_signals(frames_of(30, hud=set(range(30)), black=set(range(10, 20))))
    brightness, motion = np.array(signals["brightness"]), np.array(signals["motion"])
    assert 16 <= brightness[12:18].max() <= 18  # video range: black is 16, as before
    assert motion[12:19].max() < 0.5            # a loading screen doesn't move
    assert motion[2:9].min() > 1.0              # play does


def test_no_hud_found_says_nothing_about_it():
    signals = picture_signals(frames_of(30, hud=set()))
    assert "hud" not in signals
