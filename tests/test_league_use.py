"""League events picking clips, giving reasons and placing effects (Phase 2E-2)."""

from __future__ import annotations

import json

import numpy as np
import pytest

from ai_editor.analysis import game_events as ge
from ai_editor.analysis.clips import Clip, store_clips
from ai_editor.analysis.hype import hype_score
from ai_editor.db import init_db
from ai_editor.effects import placement
from ai_editor.recipes import shorts
from ai_editor.recipes.plan import EditPlan, Segment

from .test_shorts import cand, note, row


def ev(kind, match="m1", **extra):
    return {"kind": kind, "match": match, "text": extra.pop("text", kind), **extra}


KILL, DEATH = ev("kill", text="You killed Zed"), ev("death", text="Killed by Zed")


def triple():
    return ev("multikill", streak=3, text="Triple kill")


# --- Signals ------------------------------------------------------------------------------


def test_each_event_becomes_a_signal_at_its_second():
    values = ge.signal_values([
        (10.4, KILL), (12.0, ev("assist")), (13.2, ev("enemy_kill")), (13.9, ev("team_kill")),
        (13.9, triple()), (30.0, ev("objective", monster="Baron", ours=True)),
        (40.0, ev("objective", monster="Turret", ours=True)),          # a teammate's turret
        (45.0, ev("objective", monster="Fire Dragon", ours=False)),    # theirs
        (50.0, ev("objective", monster="Fire Dragon", ours=False, stolen=True, by_me=True)),
        (60.0, ev("ace")), (70.0, DEATH)], 100)
    assert values["lol_kill"] == {10: 1.0}
    assert values["lol_multikill"] == {13: 0.75}
    assert values["lol_objective"] == {30: 1.0, 50: 1.0}
    assert values["lol_ace"] == {60: 1.0} and values["lol_death"] == {70: 1.0}
    assert values["lol_fight"][13] == 1.0      # four champions down within seconds


def test_the_reasons_name_any_kill_from_one_to_a_penta():
    assert ge.reasons([(1, KILL)]) == ["Kill"]
    assert ge.reasons([(1, KILL), (30, KILL)]) == ["2 kills"]
    assert ge.reasons([(1, KILL)] * 4 + [(5, triple())]) == ["Triple kill", "+1 kill"]
    assert ge.reasons([(1, ev("multikill", streak=5))])[0] == "Penta kill"
    assert ge.reasons([(1, KILL), (2, ev("objective", monster="Baron", ours=True, stolen=True)),
                       (3, ev("game_end", result="win"))]) == ["Baron steal", "Victory", "Kill"]
    assert ge.reasons([(1, DEATH)]) == ["Death"]
    assert ge.reasons([(1, ev("enemy_kill"))]) == []


def test_matches_run_from_loading_in_to_the_end_screen():
    events = [(100.0, ev("game_start", game_time=0.0)), (400.0, KILL),
              (1900.0, ev("game_end", result="win")),
              (2500.0, ev("kill", match="m2", game_time=60.0))]   # joined a minute in
    spans = ge.matches(events, 3000.0)
    assert [(s.start, s.end) for s in spans] == [(100.0, 1906.0), (2440.0, 3000.0)]
    assert ge.boundaries(spans, 3000.0) == [100.0, 1906.0, 2440.0]
    down = ge.downtime(spans, 3000, league_parts=[(0.0, 2700.0)])
    assert down[50] and not down[500] and down[2000] and not down[2600]
    assert not ge.downtime(spans, 3000, league_parts=[(0.0, 2700.0)])[2750]


def test_a_long_gap_is_probably_a_match_the_companion_missed():
    spans = [ge.Span(0.0, 1800.0), ge.Span(4000.0, 5800.0)]   # 37 minutes apart
    down = ge.downtime(spans, 6400)
    assert not down[3000]          # scored as usual
    assert down[6000]              # 10 minutes after the last match: the lobby


# --- Scoring ------------------------------------------------------------------------------


def score(settings, seconds=200, downtime=None, **signals):
    arrays = {}
    for name, points in signals.items():
        values = np.zeros(seconds, dtype=np.float32)
        for t, v in points.items():
            values[t] = v
        arrays[name] = values
    return hype_score(arrays, settings, seconds, downtime=downtime)


def test_a_kill_lifts_the_fight_before_it(settings):
    result = score(settings, lol_kill={100: 1.0}, speech={150: 1.0})
    assert result.score[95] > 0.5 and result.score[100] == pytest.approx(1.0, abs=0.05)
    assert result.score[60] == 0


def test_a_death_only_counts_when_you_react(settings):
    quiet = score(settings, lol_death={100: 1.0}, speech={150: 1.0})
    assert "lol_death" not in quiet.parts or not quiet.parts["lol_death"].any()
    loud = score(settings, lol_death={100: 1.0}, energy_z={102: 3.0}, speech={150: 1.0})
    assert loud.parts["lol_death"][100] > 0


def test_time_outside_a_match_scores_nothing_unless_marked(settings):
    down = np.zeros(200, dtype=bool)
    down[:50] = True
    result = score(settings, downtime=down, laughter={20: 1.0, 120: 1.0})
    assert result.score[20] == 0 and result.score[120] > 0
    marked = score(settings, downtime=down, laughter={20: 1.0, 120: 1.0}, marker={25: 1.0})
    assert marked.score[20] > 0


# --- Clips keep their events -----------------------------------------------------------------


def test_a_clips_league_events_are_its_first_reasons(settings):
    conn = init_db(settings.db_path)
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, duration_sec, "
                 "imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 200, 'now')")
    clip = Clip(80.0, 120.0, 100, 1.0, (95, 105), reasons=[("lol_kill", 1.0), ("laughter", 0.5)])
    events = [(97.0, KILL), (99.0, KILL), (99.0, ev("multikill", streak=2, text="Double kill")),
              (150.0, KILL)]
    store_clips(conn, 1, [clip], signals={}, words=[], league=events)
    stored = conn.execute("SELECT signals_json, game_events_json FROM clips").fetchone()
    conn.close()
    summary = json.loads(stored[0])
    assert summary["reasons"] == ["Double kill", "laughter"] and summary["league_big"]
    assert [e["text"] for e in json.loads(stored[1])] == ["You killed Zed", "You killed Zed",
                                                          "Double kill"]


# --- Effects ---------------------------------------------------------------------------------


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    connection.execute(
        "INSERT INTO recordings (id, content_hash, source_type, source_file, duration_sec, "
        "imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 300, '2026-10-10T12:00:00')")

    def league(t, payload):
        connection.execute("INSERT INTO companion_events (session_id, event_type, wall_clock, "
                           "recording_time_sec, recording_id, payload_json) VALUES "
                           "('s', 'league', 'now', ?, 1, ?)", (t, json.dumps(payload)))

    league(30.25, KILL)                               # a lone kill: no effect
    league(70.4, KILL)
    league(71.6, ev("multikill", streak=2, text="Double kill"))   # big: an effect by itself
    league(150.8, KILL)                               # a kill you then marked
    connection.execute("INSERT INTO companion_events (session_id, event_type, wall_clock, "
                       "recording_time_sec, recording_id) VALUES ('s', 'marker', 'now', 158.0, 1)")
    connection.commit()
    yield connection
    connection.close()


def test_effects_go_on_big_league_moments_and_snap_marks_to_the_kill(conn, settings):
    settings.effects.highlights_per_min = 6.0
    plan = EditPlan("hl", "highlights", "t", None, 600,
                    [Segment(1, 20, 40), Segment(1, 60, 90), Segment(1, 140, 165)])
    placed = placement.place(conn, settings, plan, ["shake", "sfx"])
    assert placed[0] == []
    assert {e.at for e in placed[1]} == {71.6} and placed[1][0].label == "Double kill"
    assert {e.at for e in placed[2]} == {150.8} and placed[2][0].label == "Kill"
    assert [e.kind for e in placed[1]] == ["shake", "sfx"]


def test_a_mark_just_after_a_steal_is_that_steal_not_a_second_effect():
    events = [(100.0, KILL), (110.0, ev("objective", monster="Baron", ours=True, stolen=True))]
    assert placement.marked_kill(events, 80.0, 130.0, 111.0)[0] == 110.0
    assert placement.marked_kill(events, 80.0, 130.0, 105.0)[0] == 100.0
    assert placement.marked_kill(events, 80.0, 130.0, 95.0) is None


def test_the_review_list_names_the_league_moment(conn, settings):
    from ai_editor import effects

    settings.effects.highlights = ["shake"]
    settings.effects.highlights_per_min = 6.0
    plan = EditPlan("hl", "highlights", "t", None, 600, [Segment(1, 60, 90)])
    assert effects.moments(conn, settings, plan)[0][0] == "Clip 1 at 0:11: Double kill: shake"


# --- Shorts --------------------------------------------------------------------------------


def test_big_league_moments_are_suggested_after_your_marked_ones(settings):
    settings.shorts.per_recording = 3
    cands = [cand("a", 0), cand("b", 100), cand("c", 200, liked=True), cand("d", 300)]
    clips = {"a": row(), "b": row({"marker_short": 1.0}), "c": row(),
             "d": row({"league_big": True, "reasons": ["Quadra kill"]})}
    picks, _ = shorts.choose(cands, clips, {"a": note("a", 9), "c": note("c", 5)}, settings)
    assert [(p.candidate.clip_id, p.why) for p in picks] == [
        ("b", "marked"), ("d", "league"), ("c", "liked")]
    assert picks[1].summary == "Quadra kill"
