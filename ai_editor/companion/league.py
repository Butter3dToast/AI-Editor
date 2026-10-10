"""League of Legends events, from Riot's Live Client Data API (Phase 2E, spec 8.2).

While a match is loaded, League itself answers on
https://127.0.0.1:2999/liveclientdata/ with what has happened so far: every
kill, multikill, objective and the result, each with its game time. It is
Riot's own documented, read-only API for tools like this; no key, no account.
The Companion asks it every couple of seconds and logs each new event at its
place in the recording, so AI-Editor knows exactly when you got that triple
kill instead of guessing from the sound.

Game safety (spec section 6): this file talks to 127.0.0.1:2999 and nothing
else, only ever asks (GET), and never touches the game itself.
tests/test_game_safety.py checks both. Nothing answering there just means no
match is loaded (lobby, champion select, another game).
"""

from __future__ import annotations

import hashlib
import http.client
import json
import queue
import re
import ssl
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..logging_setup import get_logger

log = get_logger(__name__)

HOST = "127.0.0.1"
PORT = 2999
ALL_GAME_DATA = "/liveclientdata/allgamedata"
# Riot's public certificate authority for the game's local server, from the
# Game Client API page of developer.riotgames.com.
CERT = Path(__file__).with_name("riotgames.pem")
TIMEOUT_SEC = 1.5
POLL_SEC = 2.0   # during a match: events carry their own game time, so this only adds delay
IDLE_SEC = 5.0   # no match loaded

LEAGUE = "League of Legends"
EVENT = "league"           # companion_events.event_type
INBOX = "_League"          # a poll's answer, on the Companion's queue

MULTIKILLS = {2: "Double kill", 3: "Triple kill", 4: "Quadra kill", 5: "Penta kill"}
MONSTERS = {"DragonKill": "Dragon", "HeraldKill": "Rift Herald", "BaronKill": "Baron",
            "HordeKill": "Voidgrub", "AtakhanKill": "Atakhan"}
# Events that say nothing about a moment worth seeing.
IGNORED = {"MinionsSpawning", "FirstBrick", "InhibRespawningSoon", "InhibRespawned"}
TEAMS = {"T1": "ORDER", "T2": "CHAOS"}  # Turret_T1_..., Barracks_T2_...


class NoMatch(Exception):
    """Nothing answering: no match is loaded right now."""


class CertificateProblem(Exception):
    """Something answered, but couldn't prove it's League."""


# --- Asking the game -----------------------------------------------------------------------


def secure_context(relaxed: bool = False) -> ssl.SSLContext:
    """Only accept League's own local server: its certificate must be signed by Riot.

    The name isn't checked: it's 127.0.0.1 by number, which never leaves this PC,
    and Riot's certificate proves who answered. Riot's authority dates from 2013,
    before the extensions Python's strict mode wants, so strict mode is off.
    ``relaxed`` also accepts older signatures, still only Riot's.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=str(CERT))
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    if relaxed:
        context.set_ciphers("DEFAULT:@SECLEVEL=0")
    return context


def ask(context: ssl.SSLContext, path: str = ALL_GAME_DATA) -> Any:
    """What League says at ``path``. NoMatch if no match is loaded."""
    connection = http.client.HTTPSConnection(HOST, PORT, timeout=TIMEOUT_SEC, context=context)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
    except ssl.SSLCertVerificationError as exc:
        raise CertificateProblem(str(exc)) from exc
    except (OSError, http.client.HTTPException) as exc:
        raise NoMatch(str(exc)) from exc
    finally:
        connection.close()
    if response.status != 200:
        raise NoMatch(f"League answered {response.status}")  # still loading
    try:
        return json.loads(body)
    except ValueError as exc:
        raise NoMatch("League's answer wasn't readable yet") from exc


# --- What happened, from your side --------------------------------------------------------------


def _names(*values: Any) -> set[str]:
    """Every way a player's name is written: "Name#TAG" and "Name", any case."""
    found = set()
    for value in values:
        if isinstance(value, str) and value.strip():
            name = value.strip().lower()
            found.add(name)
            found.add(name.split("#")[0])
    return found


@dataclass
class Player:
    names: set[str]
    champion: str
    team: str


@dataclass
class Match:
    """One answer from League: the game clock now, and every event so far."""

    game_time: float
    events: list[dict]
    me: set[str] = field(default_factory=set)
    players: list[Player] = field(default_factory=list)
    key: str = ""  # the same for every answer from one match

    @property
    def my_team(self) -> str | None:
        return next((p.team for p in self.players if p.names & self.me), None)

    def player(self, name: Any) -> Player | None:
        wanted = _names(name)
        return next((p for p in self.players if p.names & wanted), None) if wanted else None

    def is_me(self, name: Any) -> bool:
        return bool(_names(name) & self.me)

    def who(self, name: Any) -> str:
        """A champion's name for a player, or plain words for the rest."""
        if self.is_me(name):
            return "you"
        player = self.player(name)
        if player:
            return player.champion
        text = str(name or "")
        if text.startswith("Turret"):
            return "a turret"
        if text.startswith("Minion"):
            return "minions"
        if text.startswith("SRU") or text.startswith("Sru"):
            return "a monster"
        return text or "someone"


def match_of(data: dict) -> Match:
    """League's allgamedata answer, as a Match."""
    try:
        game_time = float(data["gameData"]["gameTime"])
        events = list((data.get("events") or {}).get("Events") or [])
    except (KeyError, TypeError, ValueError) as exc:
        raise NoMatch("League's answer had no game clock yet") from exc
    active = data.get("activePlayer") or {}
    me = _names(active.get("riotId"), active.get("riotIdGameName"), active.get("summonerName"))
    players = [Player(_names(p.get("riotId"), p.get("riotIdGameName"), p.get("summonerName")),
                      str(p.get("championName") or "?"), str(p.get("team") or ""))
               for p in data.get("allPlayers") or []]
    # The same ten players on the same champions: the same match.
    who = sorted(f"{min(p.names) if p.names else ''}:{p.champion}" for p in players)
    key = hashlib.sha1("|".join(who).encode("utf-8")).hexdigest()[:12]
    return Match(game_time, events, me, players, key)


def _yes(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def describe(event: dict, match: Match) -> dict | None:
    """One event as AI-Editor logs it: what it means for you, in words. None to skip."""
    name = str(event.get("EventName") or "")
    if name in IGNORED or "EventTime" not in event:
        return None
    out: dict[str, Any] = {"event": name, "id": event.get("EventID"),
                           "game_time": round(float(event["EventTime"]), 2), "match": match.key}
    mine = match.my_team

    if name == "ChampionKill":
        killer, victim = event.get("KillerName"), event.get("VictimName")
        assisters = event.get("Assisters") or []
        out["killer"], out["victim"] = match.who(killer), match.who(victim)
        if match.is_me(killer):
            out.update(kind="kill", text=f"You killed {match.who(victim)}")
        elif match.is_me(victim):
            out.update(kind="death", text=f"Killed by {match.who(killer)}")
        elif any(match.is_me(a) for a in assisters):
            out.update(kind="assist",
                       text=f"Assist: {match.who(killer)} killed {match.who(victim)}")
        else:
            side = match.player(killer)
            ours = side is not None and side.team == mine
            out.update(kind="team_kill" if ours else "enemy_kill",
                       text=f"{match.who(killer)} killed {match.who(victim)}")
    elif name == "Multikill":
        streak = int(event.get("KillStreak") or 0)
        label = MULTIKILLS.get(streak, f"{streak} kills")
        out["streak"] = streak
        if match.is_me(event.get("KillerName")):
            out.update(kind="multikill", text=label)
        else:
            out.update(kind="other_multikill", text=f"{match.who(event.get('KillerName'))}: {label}")
    elif name == "Ace":
        ours = event.get("AcingTeam") == mine
        out.update(kind="ace" if ours else "aced",
                   text="Your team aced them" if ours else "Your team was aced")
    elif name == "FirstBlood":
        if match.is_me(event.get("Recipient")):
            out.update(kind="first_blood", text="First blood!")
        else:
            out.update(kind="other", text=f"First blood: {match.who(event.get('Recipient'))}")
    elif name in MONSTERS:
        killer = event.get("KillerName")
        monster = MONSTERS[name]
        if name == "DragonKill":
            kind_of = str(event.get("DragonType") or "")
            monster = "Elder Dragon" if kind_of == "Elder" else f"{kind_of} Dragon".strip()
        side = match.player(killer)
        ours = side is not None and side.team == mine
        stolen = _yes(event.get("Stolen"))
        doer = "You" if match.is_me(killer) else "Your team" if ours else "The enemy"
        out.update(kind="objective", monster=monster, ours=ours, stolen=stolen,
                   by_me=match.is_me(killer),
                   text=f"{doer} {'stole' if stolen else 'took'} {monster}")
    elif name in ("TurretKilled", "InhibKilled"):
        building = "a turret" if name == "TurretKilled" else "an inhibitor"
        found = re.search(r"_(T[12])_", str(event.get("TurretKilled") or event.get("InhibKilled") or ""))
        owner = TEAMS.get(found.group(1)) if found else None
        ours = owner is not None and mine is not None and owner != mine
        by_me = match.is_me(event.get("KillerName"))
        text = ("You took " + building if by_me else
                "Your team took " + building if ours else
                "The enemy took " + building if owner else building.capitalize() + " fell")
        out.update(kind="objective", monster="Turret" if name == "TurretKilled" else "Inhibitor",
                   ours=ours, stolen=False, by_me=by_me, text=text)
    elif name == "GameStart":
        out.update(kind="game_start", text="Match started")
    elif name == "GameEnd":
        won = str(event.get("Result") or "").lower().startswith("win")
        out.update(kind="game_end", result="win" if won else "lose",
                   text="Victory" if won else "Defeat")
    else:
        out.update(kind="other", text=re.sub(r"(?<!^)(?=[A-Z])", " ", name))  # "AtakhanSpawn" -> words
    return out


# --- Counting, for the Companion window -------------------------------------------------------


@dataclass
class Tally:
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    best_multikill: int = 0
    objectives: int = 0   # monsters your team took, and anything you took yourself

    def add(self, payload: dict) -> None:
        building = payload.get("monster") in ("Turret", "Inhibitor")
        kind = payload.get("kind")
        if kind == "kill":
            self.kills += 1
        elif kind == "death":
            self.deaths += 1
        elif kind == "assist":
            self.assists += 1
        elif kind == "multikill":
            self.best_multikill = max(self.best_multikill, int(payload.get("streak") or 0))
        elif kind == "objective" and (payload.get("by_me") or (payload.get("ours")
                                                                and not building)):
            self.objectives += 1

    def text(self) -> str:
        parts = [f"{self.kills}/{self.deaths}/{self.assists}"]
        if self.best_multikill >= 2:
            parts.append(MULTIKILLS.get(self.best_multikill, "multikill").lower())
        if self.objectives:
            parts.append(f"{self.objectives} objective{'s' if self.objectives != 1 else ''}")
        return ", ".join(parts)


# --- Asking, every couple of seconds, beside the Companion -------------------------------------


@dataclass
class Poll:
    at: float                  # the Companion's clock when League answered
    match: Match | None        # None: no match loaded
    problem: str | None = None


class Watcher:
    """Asks League in the background and hands each answer to the Companion's queue.

    In the background so a slow answer (League is busy while a match loads) never
    holds up a marker press. It only asks while ``wanted`` is set: while you are
    recording or streaming, and not on another game's scene.
    """

    def __init__(self, inbox: queue.Queue, *, clock: Callable[[], float] = time.monotonic,
                 fetch: Callable[[ssl.SSLContext], Any] = ask) -> None:
        self.inbox = inbox
        self.wanted = False
        self._clock = clock
        self._fetch = fetch
        self._context: ssl.SSLContext | None = None
        self._relaxed = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="league-events", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=TIMEOUT_SEC + 1)

    def _run(self) -> None:
        while not self._stop.is_set():
            if not self.wanted:
                self._stop.wait(1.0)
                continue
            poll = self.poll_once()
            self.inbox.put((INBOX, {"poll": poll}))
            self._stop.wait(POLL_SEC if poll.match else IDLE_SEC)

    def poll_once(self) -> Poll:
        try:
            if self._context is None:
                self._context = secure_context(self._relaxed)
            data = self._fetch(self._context)
            return Poll(self._clock(), match_of(data))
        except CertificateProblem as exc:
            if not self._relaxed:
                # Riot's server may sign with an older method than Python accepts by
                # default; still only Riot's certificate is accepted.
                log.info("League's certificate needs the relaxed check: %s", exc)
                self._relaxed, self._context = True, None
                return self.poll_once()
            log.warning("Couldn't confirm League's local server is League: %s", exc)
            return Poll(self._clock(), None, "couldn't confirm it's League's own server")
        except NoMatch:
            return Poll(self._clock(), None)
        except Exception as exc:  # noqa: BLE001 -- a bad answer must never stop the Companion
            log.warning("League's answer couldn't be read: %s", exc)
            return Poll(self._clock(), None)
