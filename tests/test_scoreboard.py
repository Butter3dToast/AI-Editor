"""How well AI-Editor knows you (3A-1): where it ranked the clips you rated."""

from __future__ import annotations

import json

import pytest

from ai_editor.app import videos
from ai_editor.db import init_db
from ai_editor.learning import scoreboard


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    # Two League streams in different weeks (12 and 19 Oct are Mondays).
    for rid, day in ((1, "2026-10-14T20:00:00+00:00"), (2, "2026-10-21T20:00:00+00:00")):
        connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                           "duration_sec, imported_at, recorded_at, game, analysis_status) VALUES "
                           "(?, ?, 'twitch_vod', 'gone.mkv', 7200, ?, ?, 'League of Legends', "
                           "'complete')", (rid, f"h{rid}", day, day))
        for n in range(30):   # c1_0 is the best, c1_29 the worst
            connection.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, "
                               "score, signals_json, created_at) VALUES (?, ?, ?, ?, ?, '{}', "
                               "'now')", (f"c{rid}_{n}", rid, n * 60, n * 60 + 30, 1 - n / 30))
    connection.commit()
    yield connection
    connection.close()


def test_picked_right_and_found_your_favourites(conn):
    for clip in ("c1_0", "c1_1", "c1_25"):
        videos.rate(conn, clip, 1)
    videos.rate(conn, "c1_2", -1)
    videos.rate(conn, "c1_3", 2)          # 🔖 counts as liked
    week = scoreboard.weeks(conn)[0]
    assert (week.game, str(week.monday), week.streams) == ("League of Legends", "2026-10-12", 1)
    assert (week.liked_top, week.rated_top, week.liked) == (3, 4, 4)
    assert week.picked_right == 0.75 and week.found == 0.75
    text = scoreboard.scoreboard_text(conn)
    assert "**League of Legends**" in text and "| 12 Oct | 1 | **75%** (3 of 4) |" in text


def test_a_clips_place_is_the_one_it_had_when_rated(conn):
    """Learning (3A-2) re-scores clips: that mustn't flatter streams already rated."""
    videos.rate(conn, "c2_29", 1)                      # rated at the bottom of the list
    conn.execute("UPDATE clips SET score = 5 WHERE clip_id = 'c2_29'")   # now it's the best
    videos.rate(conn, "c2_29", 1)                      # rated again: the first place counts
    week = scoreboard.weeks(conn)[-1]
    assert (week.liked_top, week.liked) == (0, 1) and week.found == 0.0


def test_ratings_from_before_get_the_places_of_the_first_look(conn):
    conn.execute("INSERT INTO feedback (ts, action, clip_id, game) VALUES "
                 "('2026-10-15T10:00:00+00:00', 'thumbs_up', 'c1_4', 'League of Legends')")
    conn.execute("UPDATE clips SET user_rating = 1 WHERE clip_id = 'c1_4'")
    conn.commit()
    assert scoreboard.weeks(conn)[0].liked_top == 1
    detail = conn.execute("SELECT detail_json FROM feedback").fetchone()[0]
    assert json.loads(detail) == {"rank": 5, "of": 30}


def test_a_cleared_rating_counts_for_nothing(conn):
    videos.rate(conn, "c1_0", 1)
    videos.rate(conn, "c1_0", None)
    assert scoreboard.weeks(conn) == []
    assert "Nothing to measure yet" in scoreboard.scoreboard_text(conn)
