"""Stream Companion: the loop that runs alongside OBS (spec section 7.1).

It sleeps until OBS has something to say, so it costs next to nothing while
you play. If OBS isn't open yet, or closes, it checks again every few seconds
and carries on by itself.

Game safety (spec section 6, manual chapter 27): the Companion talks to OBS,
and during League matches to League's own read-only Live Client Data API on
this PC (league.py, Phase 2E). It never looks at which programs are running,
never opens, reads or writes another program's memory, and never sends key
presses or mouse input anywhere. tests/test_game_safety.py enforces this for
the whole of AI-Editor.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field
from typing import Callable

from ..config import Settings
from ..errors import AIEditorError, HotkeyUnavailable, ObsNotReachable, ObsPasswordWrong, ObsTooOld
from ..logging_setup import get_logger
from ..games import game_for_scene
from . import league, obs_markers, sound
from .hotkeys import HotkeyListener, describe
from .obs import DISCONNECTED, ObsClient, ObsRequestFailed
from .session import OUTPUTS, SessionLog

log = get_logger(__name__)

RETRY_SECONDS = 5.0
# How long OBS's audio setup is trusted before asking it again (see mark()).
SOUND_RECHECK_SECONDS = 30.0

# Pressing a marker hotkey arrives on the same queue as OBS's own events.
HOTKEY = "_Hotkey"
MARKER_KINDS = {"moment": "marker", "short": "marker_short"}

# obs-websocket output states that change what the log records.
STARTED = "OBS_WEBSOCKET_OUTPUT_STARTED"
STOPPED = "OBS_WEBSOCKET_OUTPUT_STOPPED"
PAUSED = "OBS_WEBSOCKET_OUTPUT_PAUSED"
RESUMED = "OBS_WEBSOCKET_OUTPUT_RESUMED"
RECONNECTING = "OBS_WEBSOCKET_OUTPUT_RECONNECTING"
RECONNECTED = "OBS_WEBSOCKET_OUTPUT_RECONNECTED"


@dataclass
class Status:
    """What the Companion window shows."""

    obs: str = "connecting"  # connecting | connected | waiting | password | too_old
    obs_version: str | None = None
    message: str | None = None
    # Why the confirmation sound is staying silent, in words, or None if it plays.
    sound_off_because: str | None = None


@dataclass
class LeagueStatus:
    """What the Companion knows about the League match going on, if any."""

    state: str = "off"   # off | not_league | waiting | match | problem
    match: str | None = None
    seen: set = field(default_factory=set)
    tally: league.Tally = field(default_factory=league.Tally)
    problem: str | None = None

    def text(self) -> str | None:
        """One line for the Companion window, or None when there's nothing to say."""
        if self.state == "match":
            return f"match running: {self.tally.text()}"
        if self.state == "waiting":
            return "waiting for a match"
        if self.state == "problem":
            return f"can't read events: {self.problem}"
        return None


class Companion:
    def __init__(
        self,
        settings: Settings,
        *,
        client_factory: Callable[[Settings, queue.Queue], ObsClient] | None = None,
        session_log: SessionLog | None = None,
        clock: Callable[[], float] = time.monotonic,
        listener_factory: Callable[[dict, Callable[[str], None]], HotkeyListener] | None = None,
        league_factory: Callable[[queue.Queue, Callable[[], float]], league.Watcher] | None = None,
    ) -> None:
        self.settings = settings
        self._client_factory = client_factory or _default_client
        self.log = session_log or SessionLog(settings.db_path)
        self.log.resume()  # a recording that was still going when we last closed
        self.status = Status()
        self.client: ObsClient | None = None
        self.inbox: queue.Queue[tuple[str, dict]] = queue.Queue()
        self._clock = clock
        self._next_attempt = 0.0
        self._was_connected = False
        self._listener_factory = listener_factory or HotkeyListener
        self.listener: HotkeyListener | None = None
        self._sound_checked_at = 0.0
        self.scene: str | None = None
        self.markers: dict[str, int] = {"moment": 0, "short": 0}
        self.last_marker: str | None = None
        self.hotkey_problems: list[str] = []
        # The marker sources in OBS, when the keys are bound there (obs_markers).
        self.obs_markers: dict[str, int] = {}
        self.league = (league_factory or _default_league)(self.inbox, clock)
        self.league_status = LeagueStatus()

    # --- Hotkeys -------------------------------------------------------------

    @property
    def hotkeys(self) -> dict[str, str]:
        return {"moment": self.settings.companion.mark_moment_hotkey,
                "short": self.settings.companion.mark_short_hotkey}

    @property
    def keys_in_obs(self) -> bool:
        return self.settings.companion.marker_keys == "obs"

    def start_hotkeys(self) -> None:
        """Reserve the marker keys with Windows. Problems are shown, never fatal.

        Not when OBS catches the keys: then the Companion leaves them alone.
        """
        if self.keys_in_obs:
            return
        try:
            self.listener = self._listener_factory(self.hotkeys, self._on_hotkey)
            self.listener.start()
        except HotkeyUnavailable as exc:
            self.listener = None
            self.hotkey_problems = [exc.user_message()]
            return
        self.hotkey_problems = list(self.listener.failures.values())

    def _on_hotkey(self, name: str) -> None:
        """Called on the hotkey thread: hand it straight over to the main loop."""
        self.inbox.put((HOTKEY, {"name": name}))

    # --- League events (league.py) ---------------------------------------------

    def start_league(self) -> None:
        """Start asking League for events, when it's switched on in Settings."""
        if self.settings.companion.league_events:
            self.league.start()

    @property
    def league_wanted(self) -> bool:
        """Ask League only while OBS records or streams, and not on another game's scene."""
        return (self.settings.companion.league_events and self.log.active
                and self.game in (None, league.LEAGUE))

    def _league_polled(self, poll: league.Poll) -> None:
        status = self.league_status
        if poll.match is None:
            status.state = "problem" if poll.problem else "waiting"
            status.problem = poll.problem
            return
        if not self.log.active:
            return
        match = poll.match
        if match.key != status.match:
            # A new match, or the Companion restarted during one: count what's logged.
            status.match, status.seen, status.tally = match.key, set(), league.Tally()
            for payload in self.log.logged_league(match.key):
                status.seen.add(payload.get("id"))
                status.tally.add(payload)
        status.state, status.problem = "match", None
        fresh = [e for e in match.events if e.get("EventID") not in status.seen]
        if not fresh:
            return
        record_now, stream_now = self._duration("record"), self._duration("stream")
        waited = max(0.0, self._clock() - poll.at)   # since League answered
        for event in fresh:
            status.seen.add(event.get("EventID"))
            payload = league.describe(event, match)
            if payload is None:
                continue
            ago = max(0.0, match.game_time - payload["game_time"]) + waited
            self.log.league(payload, ago_sec=ago, record_now=record_now, stream_now=stream_now)
            status.tally.add(payload)

    # --- Main loop -----------------------------------------------------------

    def step(self, wait: float = 1.0) -> None:
        """Do whatever is due, waiting at most ``wait`` seconds for something to happen."""
        if (self.client is None or not self.client.connected) and self._clock() >= self._next_attempt:
            self._try_connect()
        self.league.wanted = self.league_wanted
        if not self.league.wanted:
            self.league_status.state = "not_league" if self.log.active and self.game else "off"
        try:
            event_type, data = self.inbox.get(timeout=wait)
        except queue.Empty:
            return
        self.handle(event_type, data)

    def _try_connect(self) -> None:
        client = self._client_factory(self.settings, self.inbox)
        try:
            version = client.connect()
        except ObsNotReachable:
            self._set_waiting("waiting", None)
            return
        except (ObsPasswordWrong, ObsTooOld) as exc:
            # Retrying won't fix these, but OBS settings can change while we
            # wait, so keep trying slowly rather than giving up.
            self._set_waiting("password" if isinstance(exc, ObsPasswordWrong) else "too_old",
                              exc.user_message())
            return
        self.client = client
        self.status = Status(obs="connected", obs_version=version,
                             sound_off_because=self._sound_check(client))
        if self._was_connected and self.log.active:
            self.log.log("obs_reconnected")
        self._was_connected = True
        was_active = self.log.active
        self._catch_up()
        self._read_scene()
        self._find_obs_markers()
        if self.log.active and not was_active:
            self._log_scene()  # started (or resumed) mid-session: note the game now

    def _sound_check(self, client: ObsClient) -> str | None:
        """Decide whether the confirmation click can be heard by anyone else."""
        self._sound_checked_at = self._clock()
        if not self.settings.companion.confirmation_sound:
            return "turned off in Settings"
        desktop = sound.desktop_audio_source(client)
        if desktop:
            return (f"OBS is capturing \"{desktop}\", which records everything this PC "
                    "plays, so your viewers would hear the click")
        return None

    def _set_waiting(self, state: str, message: str | None) -> None:
        self.client = None
        self.status = Status(obs=state, message=message)
        self._next_attempt = self._clock() + RETRY_SECONDS

    def _catch_up(self) -> None:
        """Log anything OBS started or stopped while we weren't connected."""
        statuses = self._statuses()
        if statuses is None:
            return
        for output in OUTPUTS:
            other = statuses["record" if output == "stream" else "stream"]
            this = statuses[output]
            self.log.sync(output, this.active, this.duration_sec, this.paused,
                          other_sec=other.duration_sec if other.active else None)

    def _statuses(self):
        try:
            return {output: self.client.output_status(output) for output in OUTPUTS}
        except (AIEditorError, ObsRequestFailed) as exc:
            log.warning("Couldn't read OBS output status: %s", exc)
            return None

    # --- Events --------------------------------------------------------------

    def handle(self, event_type: str, data: dict) -> None:
        if event_type == HOTKEY:
            self.mark(data.get("name", "moment"))
            return
        if event_type == league.INBOX:
            self._league_polled(data["poll"])
            return
        if event_type == DISCONNECTED:
            if self.log.active:
                self.log.log("obs_disconnected")
            self.client = None
            self.status = Status(obs="waiting")
            self._next_attempt = self._clock() + RETRY_SECONDS
            return
        if event_type == "RecordStateChanged":
            self._output_changed("record", data)
        elif event_type == "StreamStateChanged":
            self._output_changed("stream", data)
        elif event_type == "RecordFileChanged":
            record = self._duration("record")
            self.log.file_changed(data.get("newOutputPath", ""), record)
        elif event_type == "CurrentProgramSceneChanged":
            self.scene = data.get("sceneName")
            self._log_scene()
        elif event_type == "SceneItemEnableStateChanged":
            name = obs_markers.pressed(data, self.obs_markers)
            if name:
                self.mark(name)
                self._rearm(name)
        elif event_type in ("SceneCreated", "SceneRemoved", "SceneItemCreated", "SceneItemRemoved"):
            if self.keys_in_obs:
                self._find_obs_markers()  # set up, or taken apart, while we run
        elif event_type == "ExitStarted":
            if self.log.active:
                self.log.log("obs_closing")

    # --- Marker keys bound in OBS ----------------------------------------------

    def _find_obs_markers(self) -> None:
        if not self.keys_in_obs or self.client is None:
            return
        try:
            self.obs_markers = obs_markers.find(self.client)
        except (AIEditorError, ObsRequestFailed) as exc:
            log.warning("Couldn't look for the marker scene in OBS: %s", exc)
            return
        # Left switched on (OBS closed mid-press, say): the next press would
        # change nothing, so OBS wouldn't report it.
        for name in self.obs_markers:
            self._rearm(name)

    def _rearm(self, name: str) -> None:
        item = self.obs_markers.get(name)
        if item is None or self.client is None:
            return
        try:
            obs_markers.rearm(self.client, item)
        except (AIEditorError, ObsRequestFailed) as exc:
            log.warning("Couldn't switch the %s marker back off in OBS: %s", name, exc)

    # --- Scenes: which game is on screen ---------------------------------------

    @property
    def game(self) -> str | None:
        return game_for_scene(self.scene, self.settings.companion.scene_games)

    def _read_scene(self) -> None:
        try:
            self.scene = self.client.current_scene() if self.client else None
        except (AIEditorError, ObsRequestFailed) as exc:
            log.warning("Couldn't read the current OBS scene: %s", exc)

    def _log_scene(self) -> None:
        """Note the scene (and game) in the session log, while recording or streaming."""
        if self.log.active:
            self.log.scene_changed(self.scene, self.game, record_sec=self._duration("record"),
                                   stream_sec=self._duration("stream"))

    def _output_changed(self, output: str, data: dict) -> None:
        state = data.get("outputState")
        other = "stream" if output == "record" else "record"
        path = data.get("outputPath") or None
        if state == STARTED:
            this = self._duration(output) or 0.0
            was_active = self.log.active
            self.log.started(output, this, other_sec=self._duration(other), path=path)
            # Which game the session, or this recording, opens on. A recording
            # started after going live needs its own entry: the one logged at
            # the start of the stream has no place in the recording's timeline.
            if not was_active or output == "record":
                self._log_scene()
        elif state == STOPPED:
            self.log.stopped(output, other_sec=self._duration(other), path=path)
        elif state in (PAUSED, RESUMED) and output == "record":
            record = self._duration("record")
            self.log.paused(state == PAUSED, record or 0.0, self._duration("stream"))
        elif state in (RECONNECTING, RECONNECTED) and output == "stream":
            # The stream dropped: the VOD may have a gap or restart here.
            self.log.log("obs_stream_reconnecting" if state == RECONNECTING
                         else "obs_stream_reconnected", record_sec=self._duration("record"))

    def mark(self, name: str = "moment") -> bool:
        """Log a marker at this moment. Returns False if OBS wasn't running."""
        placed = self.log.mark(
            MARKER_KINDS.get(name, "marker"),
            record_sec=self._duration("record"),
            stream_sec=self._duration("stream"),
        )
        self.markers[name] = self.markers.get(name, 0) + 1
        self.last_marker = self.log.now().astimezone().strftime("%H:%M:%S")
        # Unmuting Desktop Audio mid-stream must not leave a stale "safe" answer.
        if (self.client is not None and self.client.connected
                and self._clock() - self._sound_checked_at > SOUND_RECHECK_SECONDS):
            self.status.sound_off_because = self._sound_check(self.client)
        if self.status.sound_off_because is None:
            sound.play(sound.click_file(self.settings.folders.cache / "companion",
                                        short_worthy=name == "short",
                                        level=self.settings.companion.sound_volume))
        if not placed:
            log.warning("Marker pressed while OBS was not recording or streaming")
        return placed

    def _duration(self, output: str) -> float | None:
        """How far into ``output`` OBS is now, or None if it isn't running."""
        if self.client is None:
            return None
        try:
            status = self.client.output_status(output)
        except (AIEditorError, ObsRequestFailed) as exc:
            log.warning("Couldn't read OBS %s status: %s", output, exc)
            return None
        if not status.active:
            return None
        self.log.note_duration(output, status.duration_sec)
        return status.duration_sec

    def close(self) -> None:
        self.league.stop()
        if self.listener is not None:
            self.listener.stop()
        if self.client is not None:
            self.client.close()

    def hotkey_summary(self) -> str:
        """What the status panel shows under "Keys"."""
        if self.keys_in_obs:
            if self.client is None:
                return "[dim]set in OBS; waiting for OBS[/dim]"
            if not self.obs_markers:
                return ("[red]not set up in OBS yet[/red]: run [bold]ai-editor setup-obs "
                        "--markers[/bold] (manual 7.4a)")
            names = [f"Show '{obs_markers.MARKER_SOURCES[n]}'" for n in ("moment", "short")
                     if n in self.obs_markers]
            return "set in OBS: " + ", ".join(names)
        parts = []
        for name, label in (("moment", "moment"), ("short", "Short-worthy")):
            key = self.hotkeys[name]
            if self.listener is not None and name not in self.listener.registered:
                parts.append(f"{describe(key)}: [red]not available[/red]")
            else:
                parts.append(f"{describe(key)} = {label}")
        return "   ".join(parts)


def _default_league(inbox: queue.Queue, clock: Callable[[], float]) -> league.Watcher:
    return league.Watcher(inbox, clock=clock)


def _default_client(settings: Settings, events: queue.Queue) -> ObsClient:
    return ObsClient(settings.obs.websocket_host, settings.obs.websocket_port,
                     settings.obs.websocket_password, events=events)
