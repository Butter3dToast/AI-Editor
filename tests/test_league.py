"""League events from Riot's Live Client Data API (Phase 2E-1)."""

from __future__ import annotations

import json
import queue
import socket
import ssl
import time

import pytest

from ai_editor.companion import league
from ai_editor.companion.app import Companion
from ai_editor.companion.link import league_events, league_summary, link_recording, listed
from ai_editor.companion.obs import ObsClient
from ai_editor.companion.session import SessionLog
from ai_editor.db import init_db

from .fake_obs import FakeObs
from .test_companion import Clock, pump, rows


def player(riot_id: str, champion: str, team: str) -> dict:
    return {"riotId": riot_id, "riotIdGameName": riot_id.split("#")[0],
            "summonerName": riot_id, "championName": champion, "team": team, "isBot": False}


PLAYERS = [player("Butter3dToast#EUW", "Jinx", "ORDER"), player("Friend#EUW", "Thresh", "ORDER"),
           player("Foe#KR1", "Zed", "CHAOS"), player("Other#NA1", "Ahri", "CHAOS")]


def answer(game_time: float, *events: dict) -> dict:
    """What League's allgamedata says, cut down to what AI-Editor reads."""
    return {"activePlayer": {"riotId": "Butter3dToast#EUW", "riotIdGameName": "Butter3dToast",
                             "summonerName": "Butter3dToast#EUW"},
            "allPlayers": PLAYERS,
            "events": {"Events": [{"EventID": i, **e} for i, e in enumerate(events)]},
            "gameData": {"gameTime": game_time, "gameMode": "CLASSIC"}}


def kill(t, killer, victim, assisters=()):
    return {"EventName": "ChampionKill", "EventTime": t, "KillerName": killer,
            "VictimName": victim, "Assisters": list(assisters)}


def said(event: dict) -> dict | None:
    match = league.match_of(answer(100.0, event))
    return league.describe(match.events[0], match)


# --- What each event means for you ------------------------------------------------------------


def test_kills_deaths_and_assists_are_yours_whichever_way_names_are_written():
    assert said(kill(10, "Butter3dToast", "Foe"))["text"] == "You killed Zed"
    assert said(kill(10, "butter3dtoast#euw", "Foe#KR1"))["kind"] == "kill"
    assert said(kill(10, "Foe", "Butter3dToast"))["text"] == "Killed by Zed"
    assert said(kill(10, "Turret_T2_L_03_A", "Butter3dToast"))["text"] == "Killed by a turret"
    helped = said(kill(10, "Friend", "Other", ["Butter3dToast"]))
    assert (helped["kind"], helped["text"]) == ("assist", "Assist: Thresh killed Ahri")
    assert said(kill(10, "Friend", "Other"))["kind"] == "team_kill"
    assert said(kill(10, "Other", "Friend"))["kind"] == "enemy_kill"


def test_multikills_aces_and_the_result():
    triple = said({"EventName": "Multikill", "EventTime": 5, "KillerName": "Butter3dToast",
                   "KillStreak": 3})
    assert (triple["kind"], triple["text"], triple["streak"]) == ("multikill", "Triple kill", 3)
    assert said({"EventName": "Multikill", "EventTime": 5, "KillerName": "Foe",
                 "KillStreak": 2})["text"] == "Zed: Double kill"
    assert said({"EventName": "Ace", "EventTime": 5, "Acer": "Friend",
                 "AcingTeam": "ORDER"})["kind"] == "ace"
    assert said({"EventName": "Ace", "EventTime": 5, "Acer": "Foe",
                 "AcingTeam": "CHAOS"})["kind"] == "aced"
    assert said({"EventName": "FirstBlood", "EventTime": 5,
                 "Recipient": "Butter3dToast"})["kind"] == "first_blood"
    assert said({"EventName": "GameEnd", "EventTime": 5, "Result": "Win"})["text"] == "Victory"
    assert said({"EventName": "GameEnd", "EventTime": 5, "Result": "Lose"})["result"] == "lose"
    assert said({"EventName": "MinionsSpawning", "EventTime": 65}) is None


def test_objectives_say_whose_and_whether_stolen():
    dragon = said({"EventName": "DragonKill", "EventTime": 5, "DragonType": "Fire",
                   "Stolen": "False", "KillerName": "Friend", "Assisters": []})
    assert (dragon["text"], dragon["ours"], dragon["stolen"]) == ("Your team took Fire Dragon", True, False)
    steal = said({"EventName": "BaronKill", "EventTime": 5, "Stolen": "True",
                  "KillerName": "Butter3dToast", "Assisters": []})
    assert (steal["text"], steal["by_me"]) == ("You stole Baron", True)
    assert said({"EventName": "DragonKill", "EventTime": 5, "DragonType": "Elder",
                 "Stolen": "False", "KillerName": "Foe"})["text"] == "The enemy took Elder Dragon"
    # Turret_T2 is the red side's turret: we're blue (ORDER), so we took it.
    turret = said({"EventName": "TurretKilled", "EventTime": 5,
                   "TurretKilled": "Turret_T2_C_05_A", "KillerName": "Minion_T1L1S01N0001"})
    assert (turret["text"], turret["ours"]) == ("Your team took a turret", True)
    lost = said({"EventName": "InhibKilled", "EventTime": 5, "InhibKilled": "Barracks_T1_L1",
                 "KillerName": "Foe"})
    assert lost["text"] == "The enemy took an inhibitor" and not lost["ours"]


def test_an_event_league_adds_later_is_still_logged_in_words():
    new = said({"EventName": "AtakhanSpawn", "EventTime": 5})
    assert (new["kind"], new["text"]) == ("other", "Atakhan Spawn")


def test_the_same_match_has_the_same_key_and_a_new_one_doesnt():
    first = league.match_of(answer(10.0)).key
    assert league.match_of(answer(900.0)).key == first
    other = answer(10.0)
    other["allPlayers"] = PLAYERS[:3] + [player("Other#NA1", "Lux", "CHAOS")]
    assert league.match_of(other).key != first


def test_still_loading_is_no_match():
    with pytest.raises(league.NoMatch):
        league.match_of({"activePlayer": {}, "events": {"Events": []}})


def test_the_tally_counts_your_side():
    tally = league.Tally()
    for event in (kill(1, "Butter3dToast", "Foe"), kill(2, "Foe", "Butter3dToast"),
                  {"EventName": "Multikill", "EventTime": 3, "KillerName": "Butter3dToast",
                   "KillStreak": 2},
                  {"EventName": "BaronKill", "EventTime": 4, "Stolen": "False",
                   "KillerName": "Friend"}):
        tally.add(said(event))
    assert tally.text() == "1/1/0, double kill, 1 objective"


# --- Asking League ------------------------------------------------------------------------


def test_riots_certificate_loads():
    context = league.secure_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert league.secure_context(relaxed=True).verify_mode == ssl.CERT_REQUIRED


def test_nothing_answering_means_no_match(monkeypatch):
    with socket.socket() as spare:          # a port nothing listens on
        spare.bind(("127.0.0.1", 0))
        port = spare.getsockname()[1]
    monkeypatch.setattr(league, "PORT", port)
    with pytest.raises(league.NoMatch):
        league.ask(league.secure_context())


def test_the_watcher_retries_the_certificate_relaxed_once_then_says_so():
    calls = []

    def fetch(context):
        calls.append(context)
        raise league.CertificateProblem("unknown signature")

    watcher = league.Watcher(queue.Queue(), fetch=fetch)
    poll = watcher.poll_once()
    assert len(calls) == 2 and poll.match is None and "confirm" in poll.problem


def test_the_watcher_only_asks_when_wanted():
    inbox: queue.Queue = queue.Queue()
    asked = []
    watcher = league.Watcher(inbox, fetch=lambda c: asked.append(1) or answer(5.0))
    watcher.start()
    time.sleep(0.3)
    assert asked == [] and inbox.empty()
    watcher.wanted = True
    kind, data = inbox.get(timeout=3)
    watcher.stop()
    assert kind == league.INBOX and data["poll"].match.game_time == 5.0


# --- Logged at the right second in the recording ------------------------------------------------


class NoWatcher:
    def __init__(self, inbox, clock) -> None:
        self.wanted = False

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


@pytest.fixture
def rig(settings):
    init_db(settings.db_path).close()
    settings.companion.confirmation_sound = False
    obs = FakeObs()
    clock = Clock()
    log = SessionLog(settings.db_path, now=clock)

    def make() -> Companion:
        return Companion(
            settings,
            client_factory=lambda s, events: ObsClient("127.0.0.1", 4455, "secret", timeout=2.0,
                                                       transport_factory=obs.factory, events=events),
            session_log=log, league_factory=NoWatcher)

    companion = make()
    yield obs, clock, companion, make
    companion.close()


def recording(obs, companion, seconds: float) -> None:
    companion.step(wait=0.1)
    obs.switch_scene("League of legends")
    pump(companion)
    obs.set_output("record", True, seconds=seconds)
    obs.output_event("record", "STARTED", path="F:/AI-Editor/raw/league.mkv")
    pump(companion)


def poll(companion: Companion, data: dict, waited: float = 0.0) -> None:
    match = league.match_of(data)
    companion.handle(league.INBOX, {"poll": league.Poll(time.monotonic() - waited, match)})


def league_rows(settings) -> list[tuple[float | None, str]]:
    return [(r["recording_time_sec"], json.loads(r["payload_json"])["text"])
            for r in rows(settings) if r["event_type"] == "league"]


def test_events_land_where_they_happened_by_the_games_clock(rig, settings):
    obs, clock, companion, _ = rig
    recording(obs, companion, seconds=0.0)
    assert companion.league_wanted
    obs.set_output("record", True, seconds=600.0)   # ten minutes into the recording
    # The game clock says 400 s; the kill was at 390 s and the answer is 0.5 s old.
    poll(companion, answer(400.0, {"EventName": "GameStart", "EventTime": 0.0},
                           kill(390.0, "Butter3dToast", "Foe")), waited=0.5)
    logged = league_rows(settings)
    assert [text for _, text in logged] == ["Match started", "You killed Zed"]
    assert [t for t, _ in logged] == [pytest.approx(199.5, abs=0.05), pytest.approx(589.5, abs=0.05)]
    assert companion.league_status.text() == "match running: 1/0/0"


def test_each_event_is_logged_once_even_after_a_restart(rig, settings):
    obs, _, companion, make = rig
    recording(obs, companion, seconds=100.0)
    events = [kill(50.0, "Butter3dToast", "Foe")]
    poll(companion, answer(60.0, *events))
    poll(companion, answer(62.0, *events))
    assert len(league_rows(settings)) == 1
    # The Companion closed mid-match and started again: same session, same match.
    again = make()
    again.log.resume()
    again.step(wait=0.1)
    events.append(kill(70.0, "Foe", "Butter3dToast"))
    poll(again, answer(72.0, *events))
    assert [t for _, t in league_rows(settings)] == ["You killed Zed", "Killed by Zed"]
    assert again.league_status.tally.text() == "1/1/0"
    again.close()


def test_an_event_from_before_the_recording_has_no_place_in_it(rig, settings):
    obs, _, companion, _ = rig
    recording(obs, companion, seconds=30.0)       # recording started late in the match
    poll(companion, answer(500.0, kill(100.0, "Butter3dToast", "Foe")))
    assert league_rows(settings) == [(None, "You killed Zed")]


def test_not_asked_on_another_games_scene_or_when_switched_off(rig, settings):
    obs, _, companion, _ = rig
    recording(obs, companion, seconds=10.0)
    obs.switch_scene("Wardogs")
    pump(companion)
    companion.step(wait=0.01)
    assert not companion.league.wanted and companion.league_status.state == "not_league"
    obs.switch_scene("League of legends")
    pump(companion)
    settings.companion.league_events = False
    companion.step(wait=0.01)
    assert not companion.league.wanted


def test_no_match_says_waiting(rig):
    obs, _, companion, _ = rig
    recording(obs, companion, seconds=10.0)
    companion.handle(league.INBOX, {"poll": league.Poll(time.monotonic(), None)})
    assert companion.league_status.text() == "waiting for a match"


# --- After import ---------------------------------------------------------------------------


def test_the_import_lists_the_events_in_the_recordings_time(rig, settings, tmp_path):
    obs, clock, companion, _ = rig
    recording(obs, companion, seconds=0.0)
    obs.set_output("record", True, seconds=300.0)
    clock.advance(300)
    poll(companion, answer(200.0, {"EventName": "GameStart", "EventTime": 0.0},
                           kill(150.0, "Butter3dToast", "Foe"),
                           {"EventName": "Multikill", "EventTime": 160.0,
                            "KillerName": "Butter3dToast", "KillStreak": 2},
                           {"EventName": "TurretKilled", "EventTime": 170.0,
                            "TurretKilled": "Turret_T2_L_03_A", "KillerName": "Friend"},
                           {"EventName": "GameEnd", "EventTime": 199.0, "Result": "Win"}))
    clock.advance(10)
    obs.set_output("record", False)
    obs.output_event("record", "STOPPED", path="F:/AI-Editor/raw/league.mkv")
    pump(companion)

    conn = init_db(settings.db_path)
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, duration_sec, "
                 "imported_at) VALUES (1, 'h', 'local_obs', 'F:/AI-Editor/raw/league.mkv', 310, "
                 "'2026-10-10T12:00:00')")
    match = link_recording(conn, 1)
    found = league_events(conn, 1)
    conn.close()
    assert [round(t) for t, _ in found] == [100, 250, 260, 270, 299]
    assert [e["text"] for _, e in found if listed(e)] == [
        "Match started", "You killed Zed", "Double kill", "Victory"]   # not a teammate's turret
    assert league_summary(match.league) == "1 match (1 won), 1/0/0, double kill"
