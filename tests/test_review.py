"""Review: removing (with the gap filled), moving, and choosing the teaser."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ai_editor.app import videos
from ai_editor.db import init_db
from ai_editor.recipes import review
from ai_editor.recipes.highlights import Candidate, top_up
from ai_editor.recipes.plan import EditPlan, Segment, approve_plan, save_plan

DAY = datetime(2026, 10, 1, tzinfo=timezone.utc)


def cand(name: str, score: float, start: float, length: float = 60.0,
         reaction: float = 0.3) -> Candidate:
    c = Candidate(name, 1, start, start + length, score, int(start + length / 2),
                  (int(start), int(start + length)), ["laughter"], DAY, False)
    c.src_in, c.src_out, c.reaction = start, start + length, reaction
    return c


def seg(c: Candidate, kind: str = "clip") -> Segment:
    return Segment(1, c.src_in, c.src_out, kind=kind, clip_id=c.clip_id, score=c.score,
                   reasons=c.reasons)


@pytest.fixture
def conn(settings, tmp_path):
    connection = init_db(settings.db_path)
    video = tmp_path / "x.mkv"   # the recording's video is still there (has_video)
    video.write_bytes(b"x")
    connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                       "duration_sec, imported_at, analysis_status) VALUES "
                       "(1, 'h', 'local_obs', ?, 7200, '2026-10-01T20:00:00', 'complete')",
                       (str(video),))
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def library(monkeypatch):
    """Ten clips: five in the plan (best last, as the recipe orders), five spare."""
    pool = [cand(f"c{n}", 0.9 - n * 0.02, n * 100.0, reaction=0.9 - n * 0.05) for n in range(10)]
    monkeypatch.setattr(review, "_candidates", lambda conn, settings, plan: list(pool))
    return pool


def plan_of(pool: list[Candidate], target_sec: float = 300.0) -> EditPlan:
    best = pool[0]
    teaser = Segment(1, best.src_in + 20, best.src_in + 30, kind="teaser", clip_id=best.clip_id)
    clips = [seg(c) for c in (pool[1], pool[2], pool[3], pool[4], best)]
    return EditPlan("highlights_streams_test_1", "highlights", "Stream highlights", None,
                    target_sec, [teaser, *clips], source={"game": None, "recording_ids": None})


def ids(plan: EditPlan) -> list[str]:
    return [("T:" if s.kind == "teaser" else "") + (s.clip_id or "") for s in plan.segments]


def test_a_removed_clip_is_replaced_by_the_next_best_in_its_place(conn, settings, library):
    plan = plan_of(library)
    change = review.remove(conn, settings, plan, 2)  # c2
    # In its place in time (c5 is at 8:20), before the finale it pays off.
    assert ids(change.plan) == ["T:c0", "c1", "c3", "c4", "c5", "c0"]
    assert review.clips_sec(change.plan) >= plan.target_sec  # never below the target
    assert change.plan.source["removed"] == ["c2"] and "Replaced with 1 clip" in change.message
    action, detail = conn.execute("SELECT action, detail_json FROM feedback").fetchone()
    assert action == "removed" and json.loads(detail)["clip"] == "c2"


def test_a_removed_clip_never_comes_back(conn, settings, library):
    plan = plan_of(library)
    review.remove(conn, settings, plan, 2)
    review.remove(conn, settings, plan, 4)  # now c5
    assert "c2" not in ids(plan) and "c5" not in ids(plan) and "c6" in ids(plan)


def test_removing_the_finale_moves_the_teaser_and_ending_to_the_next_best(conn, settings, library):
    plan = plan_of(library)
    change = review.remove(conn, settings, plan, 5)  # c0: the teaser's moment
    assert change.plan.segments[0].kind == "teaser" and change.plan.segments[0].clip_id == "c1"
    assert change.plan.segments[-1].clip_id == "c1"  # the payoff is the teaser's moment again
    assert ids(change.plan).count("c1") == 1 and "next best" in change.message


def test_when_good_clips_run_out_it_says_so_instead_of_padding(conn, settings, library):
    plan = plan_of(library[:5])
    library[5:] = []
    change = review.remove(conn, settings, plan, 2)
    assert not change.added and "Only 4.0 of 5 minutes" in change.message


def test_removing_the_teaser_puts_its_clip_back_where_it_happened(conn, settings, library):
    """Saved for the end only because the teaser showed it first (11 Oct)."""
    plan = plan_of(library)
    change = review.remove(conn, settings, plan, 0)
    assert ids(change.plan) == ["c0", "c1", "c2", "c3", "c4"]
    assert "Teaser taken out" in change.message and "back to where it happened" in change.message
    # Another order of the clips keeps its ending.
    settings.highlights.ordering = "best_last"
    plan = plan_of(library)
    assert ids(review.remove(conn, settings, plan, 0).plan) == ["c1", "c2", "c3", "c4", "c0"]


def test_clips_move_up_and_down_around_the_teaser(conn, library):
    plan = plan_of(library)
    assert review.move(conn, plan, 2, -1).message == "Moved up."
    assert ids(plan)[:3] == ["T:c0", "c2", "c1"]
    assert review.move(conn, plan, 1, -1).message == "It's already first."
    assert review.move(conn, plan, 5, +1).message == "It's already last."
    assert "teaser always opens" in review.move(conn, plan, 0, +1).message


def test_the_chosen_teaser_opens_the_video_and_its_clip_ends_it(conn, settings, library):
    plan = plan_of(library)
    change = review.use_as_teaser(conn, settings, plan, 3)  # c3
    # The old finale (c0, at 0:00) goes back to its place in the story.
    assert ids(change.plan) == ["T:c3", "c0", "c1", "c2", "c4", "c3"]
    teaser = change.plan.segments[0]
    assert library[3].src_in <= teaser.src_in < teaser.src_out <= library[3].src_out
    change = review.use_as_teaser(conn, settings, plan, 2, moment=(110.0, 116.0))  # c1
    assert ids(change.plan) == ["T:c1", "c0", "c2", "c3", "c4", "c1"]
    assert change.plan.segments[0].clip_id == "c1"
    assert (change.plan.segments[0].src_in, change.plan.segments[0].src_out) == (109.0, 117.0)


def test_the_target_is_a_floor_even_when_only_long_clips_are_left():
    """'About 10 min, never below; above is fine.'"""
    long = [cand(f"l{n}", 0.8, n * 200.0, length=120) for n in range(3)]
    added = top_up(long, 560, 600, "best_first")
    assert len(added) == 1 and 560 + added[0].length >= 600  # runs over, never short


def test_approving_again_frees_clips_taken_out_since(conn):
    for name in ("a", "b"):
        conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, created_at) "
                     "VALUES (?, 1, 0, 10, 'now')", (name,))
    plan = EditPlan("p1", "highlights", "T", None, 600,
                    [Segment(1, 0, 10, clip_id="a"), Segment(1, 20, 30, clip_id="b")])
    save_plan(conn, plan)
    approve_plan(conn, "p1")
    plan.segments.pop()
    save_plan(conn, plan)
    approve_plan(conn, "p1")
    used = dict(conn.execute("SELECT clip_id, used_in_json FROM clips").fetchall())
    assert json.loads(used["a"]) == ["p1"] and used["b"] is None


# --- what the tabs show ---------------------------------------------------------------


def test_the_player_plays_just_the_clip_from_the_preview_copy(tmp_path):
    proxy = tmp_path / "my recordings" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"x")
    page = videos.player(proxy, 61.5, 95)
    assert "/gradio_api/file=" in page and "my%20recordings/proxy.mp4?v=" in page
    assert "#t=61.50,95.00'" in page


def test_a_video_made_again_under_the_same_name_gets_a_new_address(tmp_path):
    """11 Oct: a new plan with the same name as one replaced; its new 12.9-minute
    preview played as the old 5:07 one, frozen, from the browser's stored copy."""
    import os
    import re

    from ai_editor.app.videos import player

    video = tmp_path / "highlights_league-of-legends_2026-10-11_1.mp4"
    video.write_bytes(b"old")
    os.utime(video, ns=(1_000_000_000, 1_000_000_000))
    before = re.search(r"src='([^']+)'", player(video)).group(1)
    video.write_bytes(b"new")
    os.utime(video, ns=(2_000_000_000, 2_000_000_000))
    after = re.search(r"src='([^']+)'", player(video)).group(1)
    assert before != after and before.split("?")[0] == after.split("?")[0]
    assert "Pick something" in videos.player(None) and "<video" not in videos.player(tmp_path / "no")


def test_the_clip_list_is_best_first_and_ratings_are_kept_for_learning(conn):
    for clip_id, score, used in (("a", 0.6, None), ("b", 0.9, None), ("c", 0.8, '["p1"]')):
        conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                     "signals_json, transcript, used_in_json, created_at) VALUES "
                     "(?, 1, 60, 90, ?, ?, 'oh no', ?, 'now')",
                     (clip_id, score, json.dumps({"reasons": ["laughter"]}), used))
    rows, clip_ids = videos.clip_table(conn, 1)
    assert clip_ids == ["b", "a"] and rows[0][4] == "0.90"
    assert rows[0][5] == "-" and rows[0][6] == "laughter"   # no taste learned yet
    assert videos.clip_table(conn, 1, "All")[1] == ["b", "c", "a"]
    assert "👎" in videos.rate(conn, "a", -1)
    assert videos.clip_table(conn, 1, "Rated")[1] == ["a"]
    assert videos.clip_table(conn, 1, "Rated")[0][0][9] == "👎"
    assert videos.clip_table(conn, 1, lengths={"b": 48.4})[0][0][3] == "48s"
    action, features = conn.execute("SELECT action, features_json FROM feedback").fetchone()
    assert action == "thumbs_down" and "laughter" in features


def test_the_plan_list_shows_where_each_piece_lands(conn, library):
    rows = videos.plan_table(conn, plan_of(library))
    assert [r[1] for r in rows[:3]] == ["Teaser", "0:10", "1:10"] and rows[1][3] == "0:01:40"


# --- what goes in: thumbs up, and staying inside the game's scene ----------------------


def add_clip(conn, clip_id, start, end, score, rating=None, marker=False, peak=None):
    summary = {"reasons": ["marker"] if marker else ["speech"],
               "peak": int(end - 10) if peak is None else peak,
               "core": [int(start), int(end)]}
    if marker:
        summary["marker"] = 1.0
    conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                 "signals_json, user_rating, created_at) VALUES (?, 1, ?, ?, ?, ?, ?, 'now')",
                 (clip_id, start, end, score, json.dumps(summary), rating))


def scene(conn, at, name, game):
    conn.execute("INSERT INTO companion_events (session_id, event_type, wall_clock, recording_id, "
                 "recording_time_sec, payload_json) VALUES ('s', 'obs_scene', 'now', 1, ?, ?)",
                 (at, json.dumps({"scene": name, "game": game})))


def test_a_thumbs_up_puts_a_clip_in_whatever_its_score(conn, settings):
    from ai_editor.recipes.highlights import gather, recordings_for

    add_clip(conn, "liked", 100, 140, 0.25, rating=1)
    add_clip(conn, "weak", 300, 340, 0.25)
    add_clip(conn, "disliked_marker", 500, 560, 1.0, rating=-1, marker=True)
    conn.commit()
    rows = recordings_for(conn, settings, game=None, recording_ids=[1])
    found = {c.clip_id: c for c in gather(conn, settings, rows, refresh=False)}
    assert set(found) == {"liked"} and found["liked"].must_include and found["liked"].liked
    everything = {c.clip_id for c in gather(conn, settings, rows, refresh=False, quality_bar=False)}
    assert everything == {"liked", "weak"}  # Review can add weaker clips; never a thumbs down


def test_a_clip_never_runs_into_the_ending_screen(conn, settings):
    """The first League stream's last marker ran 3 s into 'Ending Screen'."""
    from ai_editor.recipes.highlights import gather, recordings_for

    scene(conn, 0.0, "Starting Soon", None)
    scene(conn, 60.0, "League of legends", "League of Legends")
    scene(conn, 1000.0, "Brb", None)
    scene(conn, 1200.0, "League of legends", "League of Legends")
    scene(conn, 7000.0, "Ending Screen", None)
    add_clip(conn, "last", 6950, 7030, 1.0, marker=True, peak=6997)
    add_clip(conn, "pressed_late", 5000, 5100, 1.0, marker=True, peak=5090)
    scene(conn, 5080.0, "Ending Screen", None)  # a second, earlier ending: pressed after it
    scene(conn, 5200.0, "League of legends", "League of Legends")
    add_clip(conn, "first", 40, 100, 0.9)
    add_clip(conn, "brb", 1050, 1100, 0.9)
    conn.commit()
    rows = recordings_for(conn, settings, game=None, recording_ids=[1])
    found = {c.clip_id: c for c in gather(conn, settings, rows, refresh=False)}
    assert found["last"].src_out <= 6999.5 and found["first"].src_in >= 60.5
    assert found["pressed_late"].src_out <= 5079.5  # the gameplay before, not the ending
    assert "brb" not in found  # a moment during "BRB" isn't a highlight


def test_scenes_that_are_not_a_game_count_as_one_stretch():
    from ai_editor.companion.link import scene_span

    timeline = [(0.0, None), (0.7, None), (300.0, "League"), (4600.0, None), (4800.0, "League"),
                (10700.0, None)]
    assert scene_span(timeline, 5000, 10785) == (4800.0, 10700.0, "League")
    assert scene_span(timeline, 100, 10785) == (0.0, 300.0, None)
    assert scene_span(timeline, 10750, 10785) == (10700.0, 10785, None)
    assert scene_span([], 50, 600) == (0.0, 600, None)
    from ai_editor.companion.link import game_spans

    assert game_spans(timeline, 10785) == [(300.0, 4600.0, "League"), (4800.0, 10700.0, "League")]


def test_review_can_add_a_clip_before_the_finale(conn, settings, library, monkeypatch):
    from ai_editor.recipes import review as r

    plan = plan_of(library)
    extra = cand("extra", 0.3, 5000.0)
    extra.liked = True
    pool = [*library, extra]
    monkeypatch.setattr(r, "_candidates", lambda conn, settings, plan, **_: list(pool))
    options = r.addable(conn, settings, plan)
    assert options[0][1] == "extra" and options[0][0].startswith("👍 #1 at 1:23:20 · 60s")
    assert "c0" not in [o[1] for o in options]  # already in the video
    change = r.add(conn, settings, plan, "extra")
    assert ids(change.plan)[-2:] == ["extra", "c0"] and "in its place in time" in change.message
    assert "already in" in r.add(conn, settings, plan, "extra").message
    early = cand("early", 0.3, 150.0)
    pool.append(early)
    assert ids(r.add(conn, settings, plan, "early").plan)[:4] == ["T:c0", "c1", "early", "c2"]


def test_with_balanced_order_an_added_clip_goes_just_before_the_finale(conn, settings, library,
                                                                        monkeypatch):
    from ai_editor.recipes import review as r

    balanced = settings.model_copy(update={"highlights": settings.highlights.model_copy(
        update={"ordering": "balanced"})})
    plan = plan_of(library)
    pool = [*library, cand("early", 0.3, 150.0)]
    monkeypatch.setattr(r, "_candidates", lambda conn, settings, plan, **_: list(pool))
    change = r.add(conn, balanced, plan, "early")
    assert ids(change.plan)[-2:] == ["early", "c0"] and "just before the finale" in change.message
    change = r.remove(conn, balanced, plan_of(library), 2)  # c2: the refill takes its place
    assert ids(change.plan)[2] == "c5"


def test_sort_by_time_keeps_the_teaser_first_and_its_clip_last(conn, library):
    plan = plan_of(library)
    plan.segments[1], plan.segments[4] = plan.segments[4], plan.segments[1]  # c4 .. c1
    change = review.sort_by_time(conn, plan)
    assert ids(change.plan) == ["T:c0", "c1", "c2", "c3", "c4", "c0"]
    assert "saved for the end" in change.message


def test_move_to_a_number_in_one_go(conn, library):
    plan = plan_of(library)
    assert review.move_to(conn, plan, 4, 2).message == "Moved to #2."  # c4 to the top
    assert ids(plan) == ["T:c0", "c4", "c1", "c2", "c3", "c0"]
    assert review.move_to(conn, plan, 1, 1).message == "It's already #2."  # never above the teaser
    assert review.move_to(conn, plan, 1, 99).message == "Moved to #6."
    assert "teaser always opens" in review.move_to(conn, plan, 0, 3).message


def test_your_mark_beats_a_thumbs_down_on_a_clip_that_did_not_have_it(conn, settings):
    """6-9 Oct: clips were rated before the Companion's marks were linked."""
    from ai_editor.recipes.highlights import gather, recordings_for

    add_clip(conn, "old_cut", 100, 140, 0.5, rating=-1)              # turned down, no mark
    add_clip(conn, "marked_now", 120, 200, 0.5, marker=True)         # the same moment, marked
    add_clip(conn, "turned_down_marked", 500, 560, 1.0, rating=-1, marker=True)
    add_clip(conn, "recut_of_that", 510, 580, 1.0, marker=True)      # still turned down
    conn.commit()
    rows = recordings_for(conn, settings, game=None, recording_ids=[1])
    found = {c.clip_id for c in gather(conn, settings, rows, refresh=False, quality_bar=False)}
    assert found == {"marked_now"}


def test_a_new_plan_replaces_only_the_draft_from_the_same_streams(conn):
    """10 Oct: the 8 Oct stream's draft was replaced by a plan from the 9th."""
    from ai_editor.recipes.plan import discard_drafts, load_plan

    def draft(plan_id, streams):
        save_plan(conn, EditPlan(plan_id, "highlights", "t", "League of Legends", 600,
                                 [Segment(1, 0, 30)], source={"recording_ids": streams}))

    draft("eighth", [16])
    draft("ninth", [17])
    draft("all", None)
    assert discard_drafts(conn, "highlights", "League of Legends", [17]) == 1
    assert load_plan(conn, "ninth") is None
    assert load_plan(conn, "eighth") is not None and load_plan(conn, "all") is not None
    assert discard_drafts(conn, "highlights", "League of Legends", None) == 1   # "All my streams"


def test_each_plan_says_which_stream_it_is_from(conn):
    from datetime import datetime

    from ai_editor.app.videos import plan_choices, streams_of

    conn.execute("UPDATE recordings SET source_file = 'F:/raw/2026-10-08 19-55-02.mkv'")
    save_plan(conn, EditPlan("p", "highlights", "League of Legends highlights", None, 600,
                             [Segment(1, 0, 30)]))
    assert "League of Legends highlights  ·  8 Oct stream  ·  Highlights" in plan_choices(conn)[0][0]
    days = [datetime(2026, 10, d, 18).astimezone() for d in (7, 6, 7)]
    assert streams_of(days) == "6 + 7 Oct streams"
    assert streams_of([datetime(2026, 9, 30, 18).astimezone(), days[0]]) == "30 Sep + 7 Oct streams"


# --- Only my thumbs-up clips (0.25.1) --------------------------------------------------------


@pytest.fixture
def voted(conn, settings, monkeypatch):
    """Two 👍 clips, a marked clip and a good clip nobody voted on (24 Oct: the marked
    and the good ones went into a video made from 16 👍 clips)."""
    from ai_editor.recipes import highlights

    monkeypatch.setattr(highlights, "refresh_clips", lambda *a: None)
    settings.highlights.hook = False
    add_clip(conn, "liked_a", 100, 140, 0.4, rating=1)
    add_clip(conn, "liked_b", 1000, 1040, 0.3, rating=1)
    add_clip(conn, "marked", 2000, 2040, 1.0, marker=True)
    add_clip(conn, "good", 3000, 3040, 0.9)
    conn.commit()
    return highlights


def clip_ids(plan):
    return [s.clip_id for s in plan.segments]


def test_only_my_thumbs_up_clips_go_in(conn, settings, voted):
    plan = voted.build_highlights(conn, settings, game=None, recording_ids=[1]).plan
    assert clip_ids(plan) == ["liked_a", "liked_b"]
    assert plan.source["only_liked"] is True
    assert any(n.startswith("Only your 👍 clips: 2 clips") and "The target was 10" in n
               for n in plan.notes)


def test_with_no_thumbs_up_ai_editor_picks_them_itself(conn, settings, voted):
    conn.execute("UPDATE clips SET user_rating = NULL")
    conn.commit()
    plan = voted.build_highlights(conn, settings, game=None, recording_ids=[1]).plan
    assert set(clip_ids(plan)) == {"marked", "good"} and plan.source["only_liked"] is False


def test_unticked_it_fills_to_the_length_as_before(conn, settings, voted):
    plan = voted.build_highlights(conn, settings, game=None, recording_ids=[1],
                                  only_liked=False).plan
    assert set(clip_ids(plan)) == {"liked_a", "liked_b", "marked", "good"}


def test_removing_a_clip_from_a_thumbs_up_video_adds_nothing_by_itself(conn, settings, voted):
    plan = voted.build_highlights(conn, settings, game=None, recording_ids=[1]).plan
    change = review.remove(conn, settings, plan, 0)
    assert clip_ids(change.plan) == ["liked_b"] and not change.added
    assert "nothing was added in its place" in change.message
    # The unvoted clips can still be added by hand.
    assert {c for _, c, *_ in review.addable(conn, settings, plan)} >= {"marked", "good"}


def test_the_clips_tab_counts_clips_at_the_length_the_video_will_have(conn, settings):
    """24 Oct: the Clips tab said 12.2 min of 👍 clips; with the League profile's
    25 s clips the video came to 7.6."""
    from ai_editor.style import profiles

    pid = profiles.create(conn, "League of legends")
    profiles.save(conn, pid, games=["League of Legends"], recipes=["highlights"],
                  values={"cuts_per_min": 2.4})
    used, name = videos.made_with(conn, settings, "League of Legends")
    assert name == "League of legends" and used.highlights.max_clip_sec == 27.5
    used, name = videos.made_with(conn, settings, "Wardogs")
    assert name is None and used.highlights.max_clip_sec == settings.highlights.max_clip_sec


# --- 🔖 Next video (3A-1) --------------------------------------------------------------------


def test_a_next_video_clip_stays_out_of_the_video_made_now(conn, settings, voted):
    """24 Oct: "any clip that has the next video icon is to not go into the current video"."""
    add_clip(conn, "saved", 4000, 4040, 0.95, rating=2)
    conn.commit()
    plan = voted.build_highlights(conn, settings, game=None, recording_ids=[1]).plan
    assert clip_ids(plan) == ["liked_a", "liked_b"]
    plan = voted.build_highlights(conn, settings, game=None, recording_ids=[1],
                                  only_liked=False).plan
    assert "saved" not in clip_ids(plan)   # AI-Editor's own picks never take one
    assert "saved" not in {c for _, c, *_ in review.addable(conn, settings, plan)}


def test_my_next_video_clips_make_a_video_of_exactly_those(conn, settings, voted):
    add_clip(conn, "saved_a", 4000, 4040, 0.2, rating=2)
    add_clip(conn, "saved_b", 5000, 5040, 0.1, rating=2)
    conn.commit()
    plan = voted.build_highlights(conn, settings, game=None, recording_ids=[1], saved=True).plan
    assert clip_ids(plan) == ["saved_a", "saved_b"]
    assert plan.source["saved"] is True and plan.source["only_liked"] is True
    assert any(n.startswith("Only your 🔖 clips: 2 clips") for n in plan.notes)
    # Review: nothing comes in by itself, and the 🔖 clips are offered first.
    change = review.remove(conn, settings, plan, 0)
    assert clip_ids(change.plan) == ["saved_b"] and not change.added
    assert review.addable(conn, settings, plan)[0][1] == "saved_a"


def test_with_no_next_video_clips_ai_editor_picks_and_says_so(conn, settings, voted):
    plan = voted.build_highlights(conn, settings, game=None, recording_ids=[1], saved=True).plan
    assert set(clip_ids(plan)) == {"liked_a", "liked_b", "marked", "good"}
    assert plan.source["saved"] is False
    assert any("No 🔖 Next video clips" in n for n in plan.notes)


def test_a_used_next_video_clip_becomes_a_thumbs_up_and_is_logged(conn, settings, voted):
    add_clip(conn, "saved", 4000, 4040, 0.2, rating=2)
    conn.commit()
    plan = voted.build_highlights(conn, settings, game=None, recording_ids=[1], saved=True).plan
    approve_plan(conn, plan.plan_id)
    add_clip(conn, "short", 6000, 6040, 0.2, rating=2)
    short = EditPlan("shorts_test_1", "shorts", "A Short", None, 30,
                     [Segment(1, 6000, 6030, clip_id="short")])
    save_plan(conn, short)
    approve_plan(conn, short.plan_id)
    ratings = dict(conn.execute("SELECT clip_id, user_rating FROM clips"))
    assert ratings["saved"] == 1      # used in a video: it's a 👍 now
    assert ratings["short"] == 2      # a Short doesn't use it up for a video
    logged = conn.execute("SELECT action, clip_id FROM feedback WHERE action LIKE 'in_%' "
                          "ORDER BY id").fetchall()
    assert [tuple(r) for r in logged] == [("in_video", "saved"), ("in_short", "short")]
    approve_plan(conn, plan.plan_id)  # rendered again: not logged twice
    assert conn.execute("SELECT COUNT(*) FROM feedback WHERE action = 'in_video'").fetchone()[0] == 1


def test_the_next_video_button_is_saved_with_the_clips_place(conn, settings):
    add_clip(conn, "a", 100, 140, 0.9)
    add_clip(conn, "b", 200, 240, 0.5)
    conn.commit()
    assert "next video" in videos.rate(conn, "b", 2)
    action, detail = conn.execute("SELECT action, detail_json FROM feedback").fetchone()
    assert action == "next_video" and json.loads(detail) == {"rank": 2, "of": 2}
    assert "1 🔖" in videos.clip_summary(conn, settings, 1, {"b": 40.0})
    assert "your 🔖 clips about **0.7 min**" in videos.clip_summary(conn, settings, 1, {"b": 40.0})
