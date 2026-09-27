"""The highlights recipe: filling, ordering, the teaser, and using clips up."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from ai_editor.analysis.captions import Word
from ai_editor.db import init_db
from ai_editor.recipes.highlights import Candidate, order, select, teaser
from ai_editor.recipes.plan import EditPlan, Segment, approve_plan, load_plan, save_plan

DAY1 = datetime(2026, 9, 21, tzinfo=timezone.utc)
DAY2 = DAY1 + timedelta(days=1)


def cand(name: str, score: float, length: float, *, day=DAY1, must=False, peak=100) -> Candidate:
    c = Candidate(name, 1 if day == DAY1 else 2, 0.0, 200.0, score, peak, (peak - 5, peak + 5),
                  [], day, must)
    c.src_in, c.src_out = peak - length / 2, peak + length / 2
    return c


# --- Filling the target ------------------------------------------------------------


def test_fills_up_to_the_target_and_no_further():
    pool = [cand(f"c{i}", 0.9 - i * 0.01, 60) for i in range(20)]
    chosen = select(pool, 600, "best_first")
    total = sum(c.length for c in chosen)
    assert 600 <= total <= 600 * 1.15


def test_a_short_stream_makes_a_short_video_not_a_padded_one():
    """Only what passed the quality bar is in the pool; nothing else is added."""
    pool = [cand("a", 0.9, 60), cand("b", 0.8, 60)]
    chosen = select(pool, 600, "best_first")
    assert sum(c.length for c in chosen) == 120


def test_oldest_stream_is_used_up_before_the_next():
    """The creator: "4 min from the previous and 6 min from the next"."""
    older = [cand(f"old{i}", 0.6, 60, day=DAY1) for i in range(4)]
    newer = [cand(f"new{i}", 0.95, 60, day=DAY2) for i in range(10)]
    chosen = select(older + newer, 600, "oldest_first")
    assert {c.clip_id for c in chosen} >= {c.clip_id for c in older}
    assert sum(1 for c in chosen if c.recorded == DAY2) == 6


def test_best_first_ignores_which_stream():
    older = [cand(f"old{i}", 0.6, 60, day=DAY1) for i in range(4)]
    newer = [cand(f"new{i}", 0.95, 60, day=DAY2) for i in range(10)]
    chosen = select(older + newer, 600, "best_first")
    assert all(c.recorded == DAY2 for c in chosen)


def test_your_picks_always_go_in():
    pool = [cand(f"c{i}", 0.9, 60) for i in range(15)] + [cand("marked", 0.3, 40, must=True)]
    assert "marked" in {c.clip_id for c in select(pool, 600, "best_first")}


# --- Order -------------------------------------------------------------------------


def test_best_moment_is_last_and_second_best_opens():
    chosen = [cand(f"s{int(s * 100)}", s, 30) for s in (0.6, 0.9, 0.7, 1.0, 0.8, 0.65)]
    ordered = order(chosen, "balanced")
    assert ordered[-1].score == 1.0
    assert ordered[0].score == 0.9


def test_the_middle_alternates_intensity():
    chosen = [cand(f"s{i}", s, 30) for i, s in enumerate((1.0, 0.95, 0.9, 0.8, 0.7, 0.6, 0.55))]
    middle = [c.score for c in order(chosen, "balanced")[1:-1]]
    assert middle[0] < middle[1] > middle[2]  # calmer, stronger, calmer...


def test_every_clip_appears_exactly_once():
    chosen = [cand(f"s{i}", 0.5 + i / 20, 30) for i in range(9)]
    for ordering in ("balanced", "best_last", "chronological"):
        assert sorted(c.clip_id for c in order(chosen, ordering)) == sorted(c.clip_id for c in chosen)


def test_the_teaser_and_finale_are_where_you_react_most():
    """The creator picked the helicopter clip (strongest reaction) over the top score."""
    import numpy as np

    from ai_editor.recipes.highlights import best_of, reaction_strength

    signals = {"laughter": np.zeros(300, dtype=np.float32), "energy_z": np.zeros(300, dtype=np.float32)}
    signals["laughter"][120:130] = 0.4
    signals["energy_z"][120:130] = 3.0
    top_score = cand("mortar", 1.0, 30, peak=60)
    funniest = cand("helicopter", 0.85, 30, peak=125)
    top_score.reaction = reaction_strength(signals, 45, 75, 3.0)
    funniest.reaction = reaction_strength(signals, 110, 140, 3.0)
    assert best_of([top_score, funniest]) is funniest
    assert order([top_score, funniest, cand("x", 0.7, 30)], "balanced")[-1] is funniest


# --- The teaser --------------------------------------------------------------------


def test_the_teaser_shows_the_moment_itself():
    best = cand("best", 1.0, 40, peak=100)
    start, end = teaser(best, [], 10)
    assert start < 100 < end
    assert end - start == pytest.approx(10, abs=0.01)


def test_the_teaser_waits_for_you_to_stop_talking():
    """The first Wardogs teaser ended on "Bomb them, Trin, bomb" -- mid-phrase."""
    best = cand("best", 1.0, 40, peak=100)
    words, t = [], 90.0
    while t < 107.5:                       # talking non-stop until 107.5...
        words.append(Word("bomb", round(t, 3), round(t + 0.4, 3)))
        t = round(t + 0.45, 3)
    words.append(Word("them.", 112.0, 112.4))  # ...then after a real pause
    start, end = teaser(best, words, 10)
    assert end >= 107.4                    # not cut off mid-flow at ~10 s
    assert 5 <= end - start <= 15
    assert not any(w.start < end < w.end for w in words)


def test_the_teaser_never_cuts_mid_word():
    best = cand("best", 1.0, 40, peak=100)
    words, t = [], 80.0
    while t < 120:
        words.append(Word("go", round(t, 3), round(t + 0.35, 3)))
        t = round(t + 0.4, 3)
    start, end = teaser(best, words, 10)
    assert not any(w.start < start < w.end or w.start < end < w.end for w in words)


# --- Approving uses clips up --------------------------------------------------------


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    connection.execute(
        "INSERT INTO recordings (id, content_hash, source_type, source_file, duration_sec, "
        "imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 600, '2026-09-26T12:00:00')")
    for clip_id in ("a", "b"):
        connection.execute(
            "INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, created_at) "
            "VALUES (?, 1, 0, 30, 0.9, '2026-09-26T12:00:00')", (clip_id,))
    connection.commit()
    yield connection
    connection.close()


def test_approving_marks_the_clips_as_used(conn):
    plan = EditPlan("highlights_wardogs_2026-09-26_1", "highlights", "Wardogs highlights",
                    "Wardogs", 600, [Segment(1, 0, 10, kind="teaser", clip_id="a"),
                                     Segment(1, 0, 30, clip_id="a")])
    save_plan(conn, plan)
    assert approve_plan(conn, plan.plan_id) == 1  # the teaser and the clip are one clip
    used = json.loads(conn.execute("SELECT used_in_json FROM clips WHERE clip_id='a'").fetchone()[0])
    assert used == [plan.plan_id]
    assert conn.execute("SELECT used_in_json FROM clips WHERE clip_id='b'").fetchone()[0] is None
    assert load_plan(conn, plan.plan_id)[1] == "approved"


def test_a_plan_survives_being_saved_and_loaded(conn):
    plan = EditPlan("p1", "highlights", "T", "Wardogs", 600,
                    [Segment(1, 1.5, 9.25, clip_id="a", reasons=["laughter"])], notes=["n"])
    save_plan(conn, plan)
    loaded, status = load_plan(conn, "p1")
    assert loaded == plan and status == "draft"


def test_stream_highlights_take_every_game_but_not_lets_plays(settings):
    """ "Because we are doing stream highlights we are taking all the games that were played." """
    from ai_editor.recipes.highlights import recordings_for

    conn = init_db(settings.db_path)
    for rid, game in ((1, "Wardogs"), (2, "League of Legends"), (3, "The Blood of Dawnwalker"),
                      (4, None)):
        conn.execute(
            "INSERT INTO recordings (id, content_hash, source_type, source_file, game, duration_sec, "
            "imported_at, analysis_status) VALUES (?, ?, 'local_obs', 'r.mkv', ?, 600, "
            "'2026-09-26T12:00:00', 'complete')", (rid, f"h{rid}", game))
    conn.commit()
    try:
        streams = {r["id"] for r in recordings_for(conn, settings, game=None, recording_ids=None)}
        assert streams == {1, 2, 4}  # every stream, even one whose game isn't known; no Let's Play
        wardogs = {r["id"] for r in recordings_for(conn, settings, game="Wardogs", recording_ids=None)}
        assert wardogs == {1}
    finally:
        conn.close()


def test_the_teaser_you_pick_wins():
    from ai_editor.recipes.highlights import best_of

    loud, quiet = cand("loud", 1.0, 30, peak=60), cand("zap side", 0.6, 30, peak=160)
    loud.reaction, quiet.reaction = 0.6, 0.2
    assert best_of([loud, quiet]) is loud
    assert best_of([loud, quiet], pick="zap side") is quiet
    assert order([loud, quiet, cand("x", 0.7, 30)], "balanced", "zap side")[-1] is quiet


def test_a_moment_you_marked_is_the_teaser():
    """Sound can't tell what's funny; your Numpad+ press can."""
    from ai_editor.recipes.highlights import best_of

    loud, marked = cand("loud", 1.0, 30, peak=60), cand("marked", 0.6, 30, peak=160)
    loud.reaction, marked.reaction, marked.marked = 0.6, 0.2, True
    assert best_of([loud, marked]) is marked


def test_the_teaser_and_the_ending_are_the_same_moment_even_in_a_tie():
    """Two marked League moments tied; the teaser showed one and the video ended on the other."""
    from ai_editor.recipes.highlights import best_of

    a, b = cand("a", 1.0, 30, peak=60), cand("b", 1.0, 30, peak=160)
    for c in (a, b):
        c.marked, c.reaction = True, 0.3
    chosen = [a, b, cand("x", 0.7, 30), cand("y", 0.6, 30)]
    best = best_of(chosen)
    assert best_of(list(reversed(chosen))) is best
    assert order(chosen, "balanced", best.clip_id)[-1] is best
