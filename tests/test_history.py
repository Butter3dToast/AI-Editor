"""Undo and Redo in Review, and the length bar and clip list (Phase 2D-1)."""

from __future__ import annotations

import json

import pytest

from ai_editor.app import review_list
from ai_editor.db import init_db
from ai_editor.effects import set_switches
from ai_editor.recipes import history, review
from ai_editor.recipes.plan import EditPlan, Segment, discard_drafts, load_plan, save_plan

from .test_review import cand, seg


@pytest.fixture
def conn(settings, tmp_path):
    connection = init_db(settings.db_path)
    video = tmp_path / "x.mkv"
    video.write_bytes(b"x")
    connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                       "duration_sec, imported_at, analysis_status) VALUES "
                       "(1, 'h', 'local_obs', ?, 7200, '2026-10-01T20:00:00', 'complete')",
                       (str(video),))
    connection.executemany(
        "INSERT INTO transcript_words (recording_id, idx, word, start_sec, end_sec) "
        "VALUES (1, ?, ?, ?, ?)", [(i, f"w{i}", 100.0 + i, 100.6 + i) for i in range(60)])
    connection.execute(
        "INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, signals_json, "
        "created_at) VALUES ('c1', 1, 100, 160, 0.8, ?, 'now')",
        (json.dumps({"reasons": ["laughter"]}),))
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def library(monkeypatch):
    pool = [cand(f"c{n}", 0.9 - n * 0.02, n * 100.0, reaction=0.9 - n * 0.05) for n in range(10)]
    monkeypatch.setattr(review, "_candidates", lambda conn, settings, plan, **_: list(pool))
    return pool


def plan_of(pool) -> EditPlan:
    best = pool[0]
    teaser = Segment(1, best.src_in + 20, best.src_in + 30, kind="teaser", clip_id=best.clip_id)
    clips = [seg(c) for c in (pool[1], pool[2], pool[3], pool[4], best)]
    return EditPlan("highlights_streams_test_1", "highlights", "Stream highlights", None, 300.0,
                    [teaser, *clips], source={"game": None, "recording_ids": None})


def ids(conn, plan_id="highlights_streams_test_1") -> list[str]:
    plan, _ = load_plan(conn, plan_id)
    return [("T:" if s.kind == "teaser" else "") + (s.clip_id or "") for s in plan.segments]


def change(conn, settings, plan, what, fn, *args):
    """A Review change, as the window makes it: one undo step."""
    with history.step(conn, plan.plan_id, what):
        done = fn(conn, settings, plan, *args) if fn is not review.move_to else fn(conn, plan, *args)
        save_plan(conn, done.plan)
    return done


def test_undo_takes_back_a_removal_and_its_refill_and_redo_does_it_again(conn, settings, library):
    plan = plan_of(library)
    save_plan(conn, plan)
    before = ids(conn)
    change(conn, settings, plan, "removing clip 3", review.remove, 2)
    after = ids(conn)
    assert after != before and "c5" in after          # c2 out, the next best in
    assert history.can(conn, plan.plan_id) == ("removing clip 3", None)
    assert history.undo(conn, plan.plan_id) == "Undone: removing clip 3."
    assert ids(conn) == before
    assert history.can(conn, plan.plan_id) == (None, "removing clip 3")
    assert history.redo(conn, plan.plan_id) == "Redone: removing clip 3."
    assert ids(conn) == after
    assert history.undo(conn, "highlights_streams_test_1") and history.undo(
        conn, "highlights_streams_test_1") == "Nothing to undo."


def test_an_undone_change_teaches_nothing(conn, settings, library):
    plan = plan_of(library)
    save_plan(conn, plan)
    change(conn, settings, plan, "removing clip 3", review.remove, 2)
    history.undo(conn, plan.plan_id)
    assert [tuple(r) for r in conn.execute("SELECT action, undone FROM feedback")] == [
        ("removed", 1)]
    history.redo(conn, plan.plan_id)
    assert conn.execute("SELECT undone FROM feedback").fetchone()[0] == 0


def test_steps_go_back_in_order_and_a_new_change_ends_redo(conn, settings, library):
    plan = plan_of(library)
    save_plan(conn, plan)
    first = ids(conn)
    change(conn, settings, plan, "moving clip 2 to #4", review.move_to, 1, 4)
    second = ids(conn)
    change(conn, settings, plan, "moving clip 4 to #2", review.move_to, 3, 2)
    history.undo(conn, plan.plan_id)
    assert ids(conn) == second
    history.undo(conn, plan.plan_id)
    assert ids(conn) == first
    assert history.can(conn, plan.plan_id) == (None, "moving clip 2 to #4")
    plan, _ = load_plan(conn, plan.plan_id)
    change(conn, settings, plan, "moving clip 3 to #5", review.move_to, 2, 5)
    assert history.can(conn, plan.plan_id) == ("moving clip 3 to #5", None)


def test_nothing_changed_is_not_a_step(conn, settings, library):
    plan = plan_of(library)
    save_plan(conn, plan)
    change(conn, settings, plan, "moving clip 2 to #2", review.move_to, 1, 2)   # already there
    assert history.can(conn, plan.plan_id) == (None, None)


def test_undoing_an_adjusted_cut_puts_the_library_clip_back_too(conn, settings):
    plan = EditPlan("p", "highlights", "t", None, 600, [Segment(1, 130.0, 150.0, clip_id="c1")])
    save_plan(conn, plan)
    with history.step(conn, "p", "adjusting clip 1's cut", clips=["c1"]):
        done = review.adjust(conn, settings, plan, 0, 112.3, 148.3)
        save_plan(conn, done.plan)
    assert conn.execute("SELECT start_sec FROM clips").fetchone()[0] == 111.8
    history.undo(conn, "p")
    clip = conn.execute("SELECT start_sec, end_sec, signals_json FROM clips").fetchone()
    assert (clip[0], clip[1]) == (100, 160) and "adjusted" not in json.loads(clip[2])
    assert load_plan(conn, "p")[0].segments[0].src_in == 130.0
    history.redo(conn, "p")
    assert conn.execute("SELECT start_sec FROM clips").fetchone()[0] == 111.8


def test_undo_never_takes_back_the_upload_text_or_the_status(conn, settings):
    plan = EditPlan("p", "highlights", "t", None, 600, [Segment(1, 130.0, 150.0, clip_id="c1")])
    save_plan(conn, plan)
    with history.step(conn, "p", "the effects"):
        set_switches(plan, ["shake"])
        save_plan(conn, plan)
    plan.publish = {"video": {"titles": ["A title the AI took a minute over"]}}
    save_plan(conn, plan, "approved")
    history.undo(conn, "p")
    back, status = load_plan(conn, "p")
    assert back.publish == plan.publish and status == "approved"
    assert "effects" not in back.source        # the switches as they were: never set


def test_the_history_is_kept_and_goes_with_its_plan(conn, settings, library):
    plan = plan_of(library)
    save_plan(conn, plan)
    change(conn, settings, plan, "removing clip 3", review.remove, 2)
    again = init_db(settings.db_path)       # as after closing AI-Editor
    try:
        assert history.can(again, plan.plan_id) == ("removing clip 3", None)
    finally:
        again.close()
    discard_drafts(conn, "highlights", None, None)   # remade: the old plan and its history go
    assert conn.execute("SELECT COUNT(*) FROM plan_history").fetchone()[0] == 0


# --- The length bar and the list -------------------------------------------------------------


def test_the_bar_has_a_block_per_clip_against_the_target(conn, settings, library):
    plan = plan_of(library)     # a 10 s teaser and five 60 s clips: 5:10 against 5:00
    page = review_list.review_list(conn, plan, settings, selected=2)
    assert page.count("class='aie-block") == 6
    assert "class='aie-block teaser" in page and "5:10</b> long · over your 5:00 target" in page
    assert "aie-block clip c0 sel' data-row='2'" in page    # the clicked clip stands out
    plan.target_sec = 600.0
    page = review_list.review_list(conn, plan, settings)
    assert "4:50 under your 10:00 target" in page


def test_rows_are_dragged_but_the_teaser_stays_put(conn, settings, library):
    page = review_list.review_list(conn, plan_of(library), settings)
    rows = page.split("<div class='aie-row")[3:]     # past the list's box and heading
    assert "draggable" not in rows[0] and "Teaser" in rows[0]
    assert all("draggable='true'" in r for r in rows[1:])


def test_a_short_is_measured_against_its_60_seconds(conn, settings):
    short = EditPlan("s", "shorts", "t", None, 70, [Segment(1, 100.0, 170.0)])
    assert "70 s</b>: over the 60 s a Short can be" in review_list.review_list(conn, short,
                                                                              settings)


def test_a_lets_play_shows_its_parts_and_keeps_its_table(conn, settings):
    lp = EditPlan("l", "letsplay", "t", None, 1800,
                  [Segment(1, 0.0, 1500.0, kind="piece", part=1),
                   Segment(1, 1600.0, 3700.0, kind="piece", part=2)])
    page = review_list.review_list(conn, lp, settings)
    assert "2 parts</b>: 25:00 · 35:00" in page and "aie-row" not in page


def test_text_in_the_list_is_shown_not_run(conn, settings):
    plan = EditPlan("p", "highlights", "t", None, 60,
                    [Segment(1, 0.0, 30.0, reasons=["<script>alert(1)</script>"])])
    page = review_list.review_list(conn, plan, settings)
    assert "<script>" not in page and "&lt;script&gt;" in page


def test_deleting_a_plan_takes_only_the_plan_out_of_the_list(conn, settings, library):
    from ai_editor.recipes.plan import approve_plan, delete_plan

    plan = plan_of(library)
    save_plan(conn, plan)
    change(conn, settings, plan, "removing clip 3", review.remove, 2)
    conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                 "created_at) VALUES ('c1x', 1, 0, 10, 0.5, 'now')")
    approve_plan(conn, plan.plan_id)
    used = conn.execute("SELECT COUNT(*) FROM clips WHERE used_in_json IS NOT NULL").fetchone()[0]
    assert delete_plan(conn, plan.plan_id) and load_plan(conn, plan.plan_id) is None
    assert conn.execute("SELECT COUNT(*) FROM plan_history").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0] == 1   # still learnt from
    assert conn.execute("SELECT COUNT(*) FROM clips WHERE used_in_json IS NOT NULL"
                        ).fetchone()[0] == used
    assert not delete_plan(conn, plan.plan_id)


def test_several_ticked_plans_are_deleted_at_once_and_nothing_else(conn, settings, library):
    from ai_editor.app import videos
    from ai_editor.recipes.plan import approve_plan, delete_plans

    plans = []
    for n in range(3):
        plan = plan_of(library)
        plan.plan_id = f"highlights_streams_test_{n}"
        save_plan(conn, plan)
        plans.append(plan.plan_id)
    approve_plan(conn, plans[0])
    assert videos.plan_statuses(conn) == {plans[0]: "rendered", plans[1]: "draft",
                                          plans[2]: "draft"}
    assert delete_plans(conn, [plans[0], plans[2], "not_a_plan"]) == 2
    assert [p for _, p in videos.plan_choices(conn)] == [plans[1]]
