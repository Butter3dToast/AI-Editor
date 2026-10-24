"""Your taste (3A-2): learned per game, used only where it beats the usual score."""

from __future__ import annotations

import json

import numpy as np
import pytest

from ai_editor.app import videos
from ai_editor.db import init_db
from ai_editor.learning import taste
from ai_editor.learning.scoreboard import ranking


def add_stream(conn, rid: int, clips: int = 12, seed: int = 0, game: str = "League of Legends"):
    """A stream where you like the quiet clips and not the chatty ones, whatever
    their usual score says (the creator's League ratings, 24 Oct)."""
    rng = np.random.RandomState(seed)
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                 "duration_sec, imported_at, game, analysis_status) VALUES "
                 "(?, ?, 'twitch_vod', 'gone.mkv', 7200, '2026-10-20T20:00:00', ?, 'complete')",
                 (rid, f"h{rid}", game))
    for n in range(clips):
        chatty = n % 2 == 0
        words = " ".join(["so"] * (90 if chatty else 10))
        conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                     "signals_json, transcript, user_rating, created_at) VALUES "
                     "(?, ?, ?, ?, ?, ?, ?, ?, 'now')",
                     (f"r{rid}c{n}", rid, n * 100, n * 100 + 30, round(rng.uniform(0.3, 0.9), 3),
                      json.dumps({"reasons": ["speech"], "core": [n * 100, n * 100 + 30]}),
                      words, -1 if chatty else 1))


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    for rid in range(1, 5):
        add_stream(connection, rid, seed=rid)
    connection.commit()
    yield connection
    connection.close()


def test_it_learns_your_taste_and_uses_it_where_it_beats_the_usual_score(conn, settings):
    found = taste.tastes(conn)["League of Legends"]
    assert found.ratings == 48 and found.better
    assert found.taste > 0.9 and found.usual < found.taste
    assert "League of Legends" in taste.in_use(conn, settings)
    assert "**in use**" in taste.status_text(conn, settings)


def test_it_changes_the_order_never_the_scale(conn, settings):
    rows, liking = taste.ranked(conn, settings, 1)
    usual = sorted((r["score"] for r in rows), reverse=True)
    reordered = taste.reordered({r["clip_id"]: r["score"] for r in rows}, liking)
    assert sorted(reordered.values(), reverse=True) == pytest.approx(usual, abs=1e-4)  # same scores
    # The quiet clips (odd numbers) come first now.
    assert all(int(r["clip_id"].split("c")[1]) % 2 == 1 for r in rows[:6])
    assert liking[rows[0]["clip_id"]] > 0.5 > liking[rows[-1]["clip_id"]]


def test_the_clips_tab_and_the_scoreboard_follow_it(conn, settings):
    table, ids = videos.clip_table(conn, 1, "All", settings=settings)
    assert int(ids[0].split("c")[1]) % 2 == 1 and table[0][5].endswith("%")
    assert ranking(conn, 1, settings)[ids[0]][0] == 1
    # Without settings (the scoreboard's past ratings): the usual score's order.
    assert list(ranking(conn, 1)) == [r["clip_id"] for r in conn.execute(
        "SELECT clip_id FROM clips WHERE recording_id = 1 ORDER BY score DESC, start_sec")]


def test_switched_off_the_usual_score_picks(conn, settings):
    settings.learning.taste = False
    assert taste.in_use(conn, settings) == {}
    rows, liking = taste.ranked(conn, settings, 1)
    assert liking == {} and rows[0]["score"] == max(r["score"] for r in rows)
    assert "switched off below" in taste.status_text(conn, settings)


def test_not_used_where_it_does_no_better(conn, settings):
    taste.tastes(conn)
    conn.execute("UPDATE taste_models SET taste_check = 0.6, usual_check = 0.7")
    conn.commit()
    assert taste.in_use(conn, settings) == {}
    assert "not used: the usual score does as well or better" in taste.status_text(conn, settings)


def test_too_few_ratings_or_streams_learn_nothing(settings):
    conn = init_db(settings.db_path)
    add_stream(conn, 1, clips=20)
    conn.commit()
    assert taste.tastes(conn)["League of Legends"].model is None
    assert "starts learning at 30" in taste.status_text(conn, settings)
    add_stream(conn, 2, clips=20, seed=2)   # 40 ratings, but from 2 streams
    conn.commit()
    found = taste.tastes(conn)["League of Legends"]
    assert found.model is not None and found.taste is None and not found.better
    assert "too few streams to test fairly" in taste.status_text(conn, settings)
    conn.close()


def test_each_game_learns_on_its_own(conn, settings):
    add_stream(conn, 9, clips=6, game="Wardogs")
    conn.commit()
    found = taste.tastes(conn)
    assert found["Wardogs"].model is None and found["League of Legends"].better
    assert set(taste.in_use(conn, settings)) == {"League of Legends"}


def test_it_learns_again_after_twenty_new_ratings(conn, settings):
    first = taste.tastes(conn)["League of Legends"].learned_at
    conn.execute("UPDATE taste_models SET learned_at = 'earlier'")
    conn.commit()
    add_stream(conn, 5, clips=19, seed=5)
    conn.commit()
    assert taste.tastes(conn)["League of Legends"].learned_at == "earlier"   # 19: not yet
    conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                 "signals_json, user_rating, created_at) VALUES "
                 "('extra', 5, 5000, 5030, 0.5, '{}', 1, 'now')")
    conn.commit()
    again = taste.tastes(conn)["League of Legends"]
    assert again.learned_at != "earlier" and again.ratings == 68 and first


def test_highlights_pick_by_your_taste(conn, settings, monkeypatch):
    from ai_editor.recipes import highlights

    monkeypatch.setattr(highlights, "refresh_clips", lambda *a: None)
    conn.execute("UPDATE recordings SET source_file = ?", (str(settings.db_path),))  # has video
    taste.tastes(conn)
    # A new stream, nothing rated yet (a 👎 would keep a clip out anyway).
    conn.execute("UPDATE clips SET user_rating = NULL WHERE recording_id = 1")
    conn.commit()
    rows = conn.execute("SELECT * FROM recordings WHERE id = 1").fetchall()
    picked = {c.clip_id: c.score for c in highlights.gather(conn, settings, rows, refresh=False,
                                                            quality_bar=False)}
    assert len(picked) == 12
    best = sorted(picked, key=picked.get, reverse=True)[:6]
    assert all(int(c.split("c")[1]) % 2 == 1 for c in best)   # the quiet ones
    settings.learning.taste = False
    picked = {c.clip_id: c.score for c in highlights.gather(conn, settings, rows, refresh=False,
                                                            quality_bar=False)}
    usual = conn.execute("SELECT clip_id FROM clips WHERE recording_id = 1 "
                         "ORDER BY score DESC").fetchone()[0]
    assert max(picked, key=picked.get) == usual


def test_ties_at_the_top_score_go_by_your_taste():
    """Many League clips score 1.00: among them too, your taste picks."""
    scores = {"a": 1.0, "b": 1.0, "c": 1.0, "d": 0.4}
    order = taste.reordered(scores, {"a": 0.2, "b": 0.9, "c": 0.5, "d": 0.1})
    assert sorted(order, key=order.get, reverse=True) == ["b", "c", "a", "d"]
    assert order["b"] == 1.0 and order["d"] == pytest.approx(0.4, abs=1e-5)
