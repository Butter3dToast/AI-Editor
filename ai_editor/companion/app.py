"""Stream Companion: the loop that runs alongside OBS (spec section 7.1).

It sleeps until OBS has something to say, so it costs next to nothing while
you play. If OBS isn't open yet, or closes, it checks again every few seconds
and carries on by itself.

Game safety (spec section 6, manual chapter 27): the Companion's only
connection is to OBS. It never looks at which programs are running, never
opens, reads or writes another program's memory, and never sends key presses
or mouse input anywhere. tests/test_game_safety.py enforces this for the
whole of AI-Editor.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from typing import Callable

from ..config import Settings
from ..errors import AIEditorError, HotkeyUnavailable, ObsNotReachable, ObsPasswordWrong, ObsTooOld
from ..logging_setup import get_logger
from . import sound
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


class Companion:
    def __init__(
        self,
        settings: Settings,
        *,
        client_factory: Callable[[Settings, queue.Queue], ObsClient] | None = None,
        session_log: SessionLog | None = None,
        clock: Callable[[], float] = time.monotonic,
        listener_factory: Callable[[dict, Callable[[str], None]], HotkeyListener] | None = None,
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
        self.markers: dict[str, int] = {"moment": 0, "short": 0}
        self.last_marker: str | None = None
        self.hotkey_problems: list[str] = []

    # --- Hotkeys -------------------------------------------------------------

    @property
    def hotkeys(self) -> dict[str, str]:
        return {"moment": self.settings.companion.mark_moment_hotkey,
                "short": self.settings.companion.mark_short_hotkey}

    def start_hotkeys(self) -> None:
        """Reserve the marker keys with Windows. Problems are shown, never fatal."""
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

    # --- Main loop -----------------------------------------------------------

    def step(self, wait: float = 1.0) -> None:
        """Do whatever is due, waiting at most ``wait`` seconds for something to happen."""
        if (self.client is None or not self.client.connected) and self._clock() >= self._next_attempt:
            self._try_connect()
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
        self._catch_up()

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
        elif event_type == "ExitStarted":
            if self.log.active:
                self.log.log("obs_closing")

    def _output_changed(self, output: str, data: dict) -> None:
        state = data.get("outputState")
        other = "stream" if output == "record" else "record"
        path = data.get("outputPath") or None
        if state == STARTED:
            this = self._duration(output) or 0.0
            self.log.started(output, this, other_sec=self._duration(other), path=path)
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
        if self.listener is not None:
            self.listener.stop()
        if self.client is not None:
            self.client.close()

    def hotkey_summary(self) -> str:
        """What the status panel shows under "Markers"."""
        parts = []
        for name, label in (("moment", "moment"), ("short", "Short-worthy")):
            key = self.hotkeys[name]
            if self.listener is not None and name not in self.listener.registered:
                parts.append(f"{describe(key)}: [red]not available[/red]")
            else:
                parts.append(f"{describe(key)} = {label}")
        return "   ".join(parts)


def _default_client(settings: Settings, events: queue.Queue) -> ObsClient:
    return ObsClient(settings.obs.websocket_host, settings.obs.websocket_port,
                     settings.obs.websocket_password, events=events)
