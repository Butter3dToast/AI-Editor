"""Turning the per-second signals into one score per second."""

from __future__ import annotations

import numpy as np
import pytest

from ai_editor.analysis.hype import (
    HYPE_SIGNAL,
    build,
    hype_score,
    load_signals,
    marker_curve,
    smooth,
    to_unit_scale,
    why,
)
from ai_editor.db import init_db

SECONDS = 600


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    connection.execute(
        "INSERT INTO recordings (id, content_hash, source_type, source_file, duration_sec, "
        "imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', ?, '2026-09-20T12:00:00')",
        (SECONDS,),
    )
    connection.commit()
    yield connection
    connection.close()


def put(conn, name: str, values: dict[int, float]) -> None:
    conn.executemany(
        "INSERT INTO signals (recording_id, t_sec, name, value) VALUES (1, ?, ?, ?)",
        [(t, name, v) for t, v in values.items()],
    )
    conn.commit()


# --- Markers ---------------------------------------------------------------


def test_a_marker_lifts_the_minute_before_the_press():
    """You press after the good bit, so that is what must score."""
    presses = np.zeros(300, dtype=np.float32)
    presses[200] = 1.0
    curve = marker_curve(presses, lookback_sec=60, lookahead_sec=10)
    assert curve[200] == pytest.approx(1.0)
    assert curve[199] > 0.9
    assert curve[145] > 0.3          # still counts a minute earlier
    assert curve[139] == 0.0         # beyond the look-back window
    assert curve[210] == pytest.approx(1.0)  # the reaction after the press
    assert curve[211] == 0.0


def test_the_further_back_the_weaker():
    presses = np.zeros(300, dtype=np.float32)
    presses[200] = 1.0
    curve = marker_curve(presses, lookback_sec=60, lookahead_sec=0)
    assert curve[150] < curve[180] < curve[199]


def test_two_markers_close_together_do_not_cancel_out():
    presses = np.zeros(300, dtype=np.float32)
    presses[100] = presses[110] = 1.0
    curve = marker_curve(presses, lookback_sec=60, lookahead_sec=10)
    assert curve[100] == pytest.approx(1.0)  # keeps the stronger of the two


# --- Scales ----------------------------------------------------------------


def test_zscores_become_zero_to_one():
    values = np.array([-2.0, 0.0, 1.5, 3.0, 9.0], dtype=np.float32)
    scaled = to_unit_scale("energy_z", values, zscore_full_scale=3.0)
    assert list(scaled) == [0.0, 0.0, 0.5, 1.0, 1.0]


def test_probabilities_are_left_alone():
    values = np.array([0.0, 0.3, 1.0], dtype=np.float32)
    assert list(to_unit_scale("laughter", values, zscore_full_scale=3.0)) == [0.0, 0.3, 1.0]


def test_smoothing_spreads_a_single_second():
    values = np.zeros(20, dtype=np.float32)
    values[10] = 1.0
    smoothed = smooth(values, 5)
    assert smoothed[10] == pytest.approx(0.2)
    assert smoothed[8] > 0 and smoothed[12] > 0
    assert smoothed[5] == 0


# --- Sustained sounds and combinations --------------------------------------


def test_a_burst_of_shooting_is_not_a_firefight(settings, conn):
    """The creator's complaint: "some are just random shooting"."""
    put(conn, "gunfire", {100: 1.0, 101: 1.0})                       # two seconds
    put(conn, "gunfire", {t: 1.0 for t in range(300, 340)})          # forty seconds
    result = build(conn, settings, 1, SECONDS)
    assert result.score[320] > 3 * result.score[100]


def test_a_fight_with_a_reaction_beats_a_fight_alone(settings, conn):
    put(conn, "gunfire", {t: 1.0 for t in range(100, 140)})
    put(conn, "gunfire", {t: 1.0 for t in range(300, 340)})
    put(conn, "laughter", {t: 0.8 for t in range(315, 325)})
    result = build(conn, settings, 1, SECONDS)
    assert result.score[320] > result.score[120]


def test_the_combination_bonus_can_be_switched_off(settings, conn):
    put(conn, "gunfire", {t: 1.0 for t in range(300, 340)})
    put(conn, "laughter", {t: 0.8 for t in range(315, 325)})
    settings.scoring.combination_bonus = 0.0
    result = build(conn, settings, 1, SECONDS)
    assert "combination" not in result.parts


def test_the_same_kind_twice_is_not_a_combination(settings, conn):
    """Laughter and shouting are both reactions, so together they aren't 'several'."""
    put(conn, "laughter", {t: 0.9 for t in range(300, 320)})
    put(conn, "shout", {t: 0.9 for t in range(300, 320)})
    result = build(conn, settings, 1, SECONDS)
    assert "combination" not in result.parts


# --- The score -------------------------------------------------------------


def test_a_marked_moment_beats_a_noisy_one(settings, conn):
    put(conn, "marker", {300: 1.0})
    put(conn, "gunfire", {t: 0.9 for t in range(100, 140)})
    put(conn, "energy_z", {t: 3.0 for t in range(100, 140)})
    result = build(conn, settings, 1, SECONDS)
    assert result.score[295] > result.score[120]


def test_the_best_moment_scores_one(settings, conn):
    put(conn, "laughter", {t: 0.9 for t in range(200, 210)})
    result = build(conn, settings, 1, SECONDS)
    assert result.score.max() == pytest.approx(1.0)
    assert result.score.min() == 0.0


def test_silence_is_not_a_good_moment(settings, conn):
    put(conn, "silence", {t: 1.0 for t in range(0, 100)})
    put(conn, "speech", {t: 1.0 for t in range(200, 300)})
    result = build(conn, settings, 1, SECONDS)
    assert result.score[50] < result.score[250]
    assert result.score[50] == 0.0  # never below "nothing happened"


def test_weights_can_be_changed(settings, conn):
    put(conn, "gunfire", {t: 1.0 for t in range(100, 120)})
    put(conn, "laughter", {t: 1.0 for t in range(300, 320)})
    settings.scoring.weights = {"gunfire": 5.0, "laughter": 0.1}
    louder_guns = build(conn, settings, 1, SECONDS)
    assert louder_guns.score[110] > louder_guns.score[310]

    settings.scoring.weights = {"gunfire": 0.1, "laughter": 5.0}
    louder_laughs = build(conn, settings, 1, SECONDS)
    assert louder_laughs.score[310] > louder_laughs.score[110]


def test_the_score_is_stored_for_later(settings, conn):
    put(conn, "laughter", {t: 0.9 for t in range(200, 210)})
    build(conn, settings, 1, SECONDS)
    rows = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE recording_id = 1 AND name = ?", (HYPE_SIGNAL,)
    ).fetchone()[0]
    assert rows > 0


def test_scoring_twice_does_not_pile_up(settings, conn):
    put(conn, "laughter", {t: 0.9 for t in range(200, 210)})
    build(conn, settings, 1, SECONDS)
    first = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE recording_id = 1 AND name = ?", (HYPE_SIGNAL,)
    ).fetchone()[0]
    build(conn, settings, 1, SECONDS)
    again = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE recording_id = 1 AND name = ?", (HYPE_SIGNAL,)
    ).fetchone()[0]
    assert first == again


def test_the_hype_score_never_feeds_itself(settings, conn):
    put(conn, "laughter", {t: 0.9 for t in range(200, 210)})
    build(conn, settings, 1, SECONDS)
    assert HYPE_SIGNAL not in load_signals(conn, 1, SECONDS)


def test_a_recording_with_no_chat_says_what_is_missing(settings, conn):
    put(conn, "laughter", {200: 0.9})
    result = build(conn, settings, 1, SECONDS)
    assert "chat_z" in result.missing
    assert "laughter" not in result.missing


def test_why_explains_a_moment(settings, conn):
    put(conn, "marker", {300: 1.0})
    put(conn, "laughter", {t: 0.8 for t in range(290, 300)})
    result = build(conn, settings, 1, SECONDS)
    reasons = dict(why(result.parts, 295))
    assert "marker" in reasons
    assert reasons["marker"] > reasons["laughter"]  # markers weigh most


def test_an_empty_recording_scores_nothing(settings, conn):
    result = hype_score({}, settings, SECONDS)
    assert result.score.sum() == 0.0
