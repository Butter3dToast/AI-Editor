"""Moment rules: which moments always or never go in (Phase 2H-3a)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ai_editor.db import init_db
from ai_editor.recipes import highlights
from ai_editor.recipes.highlights import Candidate
from ai_editor.recipes.shorts import choose
from ai_editor.rules import kinds, store
from ai_editor.rules.kinds import Rule
from ai_editor.rules.moments import MomentRule, found, verdict
from ai_editor.rules.understand import to_rule

GAMES = ["League of Legends", "The Blood of Dawnwalker", "Wardogs"]
LOL = "League of Legends"


def ev(kind: str, **more) -> tuple[float, dict]:
    return 0.0, {"kind": kind, **more}


# --- Seeing the moments in a clip --------------------------------------------------------------


def test_league_moments_from_its_events():
    moments = found([ev("multikill", streak=4), ev("death"),
                     ev("objective", monster="Baron", ours=True, stolen=True),
                     ev("objective", monster="Elder Dragon", ours=True),
                     ev("objective", monster="Turret", ours=False, by_me=False),
                     ev("game_end", result="lose")], [], None, False)
    # A quadra is a double and a triple too ("triple kills" means a triple or bigger).
    assert moments == {"kill", "double_kill", "triple_kill", "quadra_kill", "death", "baron",
                       "steal", "stolen_baron", "dragon", "elder_dragon", "defeat"}


def test_baron_steals_means_a_stolen_baron():
    """24 Oct: Gemma's form for "Baron steals" is [baron, steal]: not "Baron or any steal"."""
    rule = MomentRule("r006", "always", ["baron", "steal"])
    stolen = ev("objective", monster="Baron", ours=True, stolen=True)
    taken = ev("objective", monster="Baron", ours=True)
    dragon = ev("objective", monster="Cloud Dragon", ours=True, stolen=True)
    assert verdict([rule], LOL, found([stolen], [], None, False), liked=False,
                   marked=False) == ("in", "r006: Baron steal")
    for other in (taken, dragon):
        assert verdict([rule], LOL, found([other], [], None, False), liked=False,
                       marked=False) is None
    assert "where your side steals Baron," in Rule("moment", {"which": "always",
                                                              "moments": ["baron", "steal"]}).said()


def test_heard_moments_your_mark_and_the_ais_guesses():
    moments = found([], ["laughter", "energy_z", "explosion", "speech"], {"rage", "kill"}, True)
    assert moments == {"laughter", "shouting", "gunfire", "marked", "rage"}


# --- Always, never, and the creator's exceptions (24 Oct) ---------------------------------------


NEVER_DIE = MomentRule("r001", "never", ["death"])


def test_never_keeps_out_a_clip_where_you_just_die():
    assert verdict([NEVER_DIE], LOL, {"death"}, liked=False, marked=False) == ("out", "r001: you die")


def test_dying_in_a_good_fight_is_still_a_good_clip():
    for good in ("kill", "ace", "baron", "steal"):
        assert verdict([NEVER_DIE], LOL, {"death", good}, liked=False, marked=False) is None


def test_your_thumbs_up_or_mark_beats_a_never_rule():
    assert verdict([NEVER_DIE], LOL, {"death"}, liked=True, marked=False) is None
    assert verdict([NEVER_DIE], LOL, {"death"}, liked=False, marked=True) is None


def test_only_bad_luck_gets_the_good_fight_exception():
    never_rage = MomentRule("r002", "never", ["rage"])
    assert verdict([never_rage], LOL, {"rage", "kill"}, liked=False, marked=False)[0] == "out"


def test_always_puts_in_a_triple_or_bigger():
    always = MomentRule("r003", "always", ["triple_kill"])
    assert verdict([always], LOL, found([ev("multikill", streak=5)], [], None, False),
                   liked=False, marked=False) == ("in", "r003: Triple kill")
    assert verdict([always], LOL, found([ev("multikill", streak=2)], [], None, False),
                   liked=False, marked=False) is None


def test_the_newer_rule_wins_and_games_are_respected():
    rules = [MomentRule("r001", "always", ["death"]), MomentRule("r002", "never", ["death"])]
    assert verdict(rules, LOL, {"death"}, liked=False, marked=False)[0] == "out"
    assert verdict(rules[::-1], LOL, {"death"}, liked=False, marked=False)[0] == "in"
    wardogs = [MomentRule("r005", "never", ["rage"], ["Wardogs"])]
    assert verdict(wardogs, LOL, {"rage"}, liked=False, marked=False) is None
    assert verdict(wardogs, "Wardogs", {"rage"}, liked=False, marked=False)[0] == "out"


# --- What AI-Editor says back ----------------------------------------------------------------


def test_the_read_back_says_exactly_what_will_happen():
    die = Rule("moment", {"which": "never", "moments": ["death"]})
    assert die.said() == (
        "Every game's highlights and Shorts: never use clips where you die, except ones where "
        "something good happens too (a kill, ace or objective) and ones you gave a 👍 or marked "
        "(League only: other games can't tell yet).")
    penta = Rule("moment", {"which": "always", "moments": ["penta_kill"]}, [LOL])
    assert penta.said() == ("League of Legends highlights and Shorts: always put in clips with "
                            "a penta kill, whatever their score.")
    rage = Rule("moment", {"which": "never", "moments": ["rage"]}, ["Wardogs"])
    assert rage.said() == ("Wardogs highlights and Shorts: never use clips the AI thinks are "
                           "rage (its guess), except ones you gave a 👍 or marked.")


def test_the_ais_form_becomes_a_moment_rule():
    made = to_rule({"kind": "moment", "games": [], "videos": ["highlights"], "which": "never",
                    "moments": ["death", "made_up"]}, GAMES)
    assert made.rule.kind == "moment" and made.rule.params == {"which": "never",
                                                               "moments": ["death"]}
    note = to_rule({"kind": "moment", "games": [], "videos": [], "which": "always",
                    "moments": []}, GAMES)
    assert note.rule.is_note
    effect = to_rule({"kind": "effect_on_moment", "games": [], "videos": []}, GAMES)
    assert effect.rule.is_note and "2H-3b" in effect.message


def test_two_rules_about_the_same_moment_clash():
    conn_rules = [store.Saved(1, "r001", "", Rule("moment", {"which": "always",
                                                             "moments": ["death"]}), True, ""),
                  store.Saved(2, "r002", "", Rule("moment", {"which": "never",
                                                             "moments": ["death", "aced"]}),
                              True, ""),
                  store.Saved(3, "r003", "", Rule("moment", {"which": "always",
                                                             "moments": ["baron"]}), True, "")]
    assert store.clashes(conn_rules) == {"r001": "r002"}


# --- In a real plan ---------------------------------------------------------------------------


@pytest.fixture
def conn(settings, tmp_path, monkeypatch):
    connection = init_db(settings.db_path)
    video = tmp_path / "x.mkv"
    video.write_bytes(b"x")
    connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                       "duration_sec, imported_at, analysis_status, game) VALUES "
                       "(1, 'h', 'local_obs', ?, 7200, '2026-10-01T20:00:00', 'complete', ?)",
                       (str(video), LOL))
    monkeypatch.setattr(highlights, "refresh_clips", lambda *a: None)
    settings.highlights.hook = False
    yield connection
    connection.close()


def add_clip(conn, clip_id, start, end, score, rating=None):
    summary = {"reasons": ["speech"], "peak": int(end - 10), "core": [int(start), int(end)]}
    conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                 "signals_json, user_rating, created_at) VALUES (?, 1, ?, ?, ?, ?, ?, 'now')",
                 (clip_id, start, end, score, json.dumps(summary), rating))


def league(conn, at, **event):
    conn.execute("INSERT INTO companion_events (session_id, event_type, wall_clock, recording_id, "
                 "recording_time_sec, payload_json) VALUES ('s', 'league', 'now', 1, ?, ?)",
                 (at, json.dumps(event)))


def with_rules(settings, *rules):
    return kinds.apply(settings, list(rules), "highlights")


@pytest.fixture
def stream(conn):
    add_clip(conn, "died", 100, 140, 0.9)
    league(conn, 130, kind="death")
    add_clip(conn, "died_in_a_fight", 1000, 1040, 0.9)
    league(conn, 1025, kind="kill")
    league(conn, 1030, kind="death")
    add_clip(conn, "weak_penta", 2000, 2040, 0.2)
    league(conn, 2030, kind="multikill", streak=5)
    add_clip(conn, "plain", 3000, 3040, 0.9)
    conn.commit()
    return conn


def ids(plan):
    return {s.clip_id for s in plan.segments}


def test_a_plan_follows_always_and_never(stream, settings):
    used = with_rules(settings, Rule("moment", {"which": "never", "moments": ["death"]}, id="r001"),
                      Rule("moment", {"which": "always", "moments": ["penta_kill"]}, id="r002"))
    plan = highlights.build_highlights(stream, used, game=LOL, recording_ids=[1]).plan
    assert ids(plan) == {"died_in_a_fight", "weak_penta", "plain"}
    penta = next(s for s in plan.segments if s.clip_id == "weak_penta")
    assert penta.reasons[0] == "📌 r002: Penta kill"   # under the quality bar, in all the same
    assert "r001 kept out 1 clip (you die). Add any of them back with Add a clip." in plan.notes


def test_without_rules_nothing_changes(stream, settings):
    plan = highlights.build_highlights(stream, settings, game=LOL, recording_ids=[1]).plan
    assert ids(plan) == {"died", "died_in_a_fight", "plain"}


def test_with_only_my_thumbs_up_clips_always_rules_add_nothing(stream, settings):
    stream.execute("UPDATE clips SET user_rating = 1 WHERE clip_id IN ('died', 'plain')")
    stream.commit()
    used = with_rules(settings, Rule("moment", {"which": "never", "moments": ["death"]}, id="r001"),
                      Rule("moment", {"which": "always", "moments": ["penta_kill"]}, id="r002"))
    plan = highlights.build_highlights(stream, used, game=LOL, recording_ids=[1]).plan
    assert ids(plan) == {"died", "plain"}   # your 👍 beats the never rule, and is the video


def test_review_offers_the_clips_rules_point_at_first(stream, settings):
    from ai_editor.recipes import review
    from ai_editor.rules.store import stamp

    used = with_rules(settings, Rule("moment", {"which": "never", "moments": ["death"]}, id="r001"))
    plan = highlights.build_highlights(stream, used, game=LOL, recording_ids=[1]).plan
    stamp(plan, [store.Saved(1, "r001", "", Rule("moment", {"which": "never",
                                                            "moments": ["death"]}), True, "")])
    offered = review.addable(stream, settings, plan)
    assert offered[0][1] == "died" and "kept out by r001" in offered[0][0]


def test_shorts_suggest_always_moments_right_after_your_marks(settings):
    day = datetime(2026, 10, 1, tzinfo=timezone.utc)

    def cand(name, start, ruled_in=""):
        c = Candidate(name, 1, start, start + 30, 0.5, int(start + 15), (int(start), int(start + 30)),
                      [], day, False, ruled_in=ruled_in)
        c.src_in, c.src_out = start, start + 30
        return c

    rows = {"marked": {"used_in_json": None, "signals_json": json.dumps({"marker_short": 1})},
            "big": {"used_in_json": None, "signals_json": json.dumps({"league_big": True})},
            "ruled": {"used_in_json": None, "signals_json": "{}"}}
    picks, _ = choose([cand("big", 0), cand("ruled", 100, "r002: Baron"), cand("marked", 200)],
                      rows, {}, settings)
    assert [p.candidate.clip_id for p in picks] == ["marked", "ruled", "big"]
    assert picks[1].why == "rule"
