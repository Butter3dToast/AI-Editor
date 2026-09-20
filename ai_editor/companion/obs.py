"""Talking to OBS through its built-in WebSocket server (obs-websocket 5).

This is how the Stream Companion knows what is happening while you play: OBS
tells it when streaming and recording start and stop, and answers "how far
into the recording are we?" when a marker is pressed. The connection is to OBS
on this PC only; nothing here goes near a game (spec section 6).

Protocol: github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md
"""

from __future__ import annotations

import base64
import hashlib
import json
import queue
import struct
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from ..errors import AIEditorError, ObsNotReachable, ObsPasswordWrong, ObsTooOld
from ..logging_setup import FILE_ONLY, get_logger

log = get_logger(__name__)

OP_HELLO = 0
OP_IDENTIFY = 1
OP_IDENTIFIED = 2
OP_EVENT = 5
OP_REQUEST = 6
OP_REQUEST_RESPONSE = 7

RPC_VERSION = 1

# Only what the Companion needs: General (OBS is closing) and Outputs (stream
# and recording state). OBS then doesn't send anything else.
SUBSCRIBE_GENERAL = 1 << 0
SUBSCRIBE_OUTPUTS = 1 << 6

CLOSE_AUTHENTICATION_FAILED = 4009
CLOSE_UNSUPPORTED_RPC_VERSION = 4010

# Put on the event queue when the connection ends, so the consumer hears about
# it in the same place as everything else.
DISCONNECTED = "_Disconnected"


class Transport(Protocol):
    def send(self, text: str) -> None: ...
    def recv(self) -> str: ...
    def close(self) -> None: ...


class TransportClosed(Exception):
    """The connection ended. ``code`` is the WebSocket close code, if OBS sent one."""

    def __init__(self, code: int | None = None, reason: str = "") -> None:
        super().__init__(f"connection closed ({code}): {reason}")
        self.code = code
        self.reason = reason


class ObsRequestFailed(Exception):
    """OBS answered a request with an error. Internal: never shown as-is."""


class WebSocketTransport:
    """websocket-client, reduced to send / receive text / close."""

    def __init__(self, url: str, timeout: float) -> None:
        import websocket

        self._errors: tuple[type[BaseException], ...] = (OSError, websocket.WebSocketException)
        self._close_opcode = websocket.ABNF.OPCODE_CLOSE
        try:
            self._ws = websocket.create_connection(url, timeout=timeout)
        except self._errors as exc:
            raise TransportClosed(None, str(exc)) from exc

    def settimeout(self, seconds: float | None) -> None:
        self._ws.settimeout(seconds)

    def send(self, text: str) -> None:
        try:
            self._ws.send(text)
        except self._errors as exc:
            raise TransportClosed(None, str(exc)) from exc

    def recv(self) -> str:
        try:
            opcode, data = self._ws.recv_data()
        except self._errors as exc:
            raise TransportClosed(None, str(exc)) from exc
        if opcode == self._close_opcode:
            code = struct.unpack("!H", data[:2])[0] if len(data) >= 2 else None
            raise TransportClosed(code, data[2:].decode("utf-8", "replace"))
        return data.decode("utf-8") if isinstance(data, bytes) else data

    def close(self) -> None:
        try:
            self._ws.close()
        except self._errors:
            pass


def auth_string(password: str, salt: str, challenge: str) -> str:
    """The response OBS expects to its password challenge.

    The password itself is never sent: only a hash of it mixed with a
    one-time challenge from OBS.
    """
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


@dataclass(frozen=True)
class OutputStatus:
    """What OBS says about its stream or its recording right now."""

    active: bool
    paused: bool
    duration_sec: float  # how far into this stream or recording OBS is


class _Waiter:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.response: dict[str, Any] | None = None


class ObsClient:
    """One connection to OBS.

    Events arrive on ``events`` (a queue of (event type, data) pairs) rather
    than through callbacks, so whoever handles them is free to ask OBS
    questions while doing so.
    """

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        *,
        timeout: float = 5.0,
        transport_factory: Callable[[str, float], Transport] | None = None,
        events: queue.Queue[tuple[str, dict[str, Any]]] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._password = password
        self.timeout = timeout
        self._factory = transport_factory or WebSocketTransport
        self._transport: Transport | None = None
        self._pending: dict[str, _Waiter] = {}
        self._lock = threading.Lock()
        self._connected = threading.Event()
        self._closing = False
        # Shared with the Companion, so hotkey presses and OBS events queue up
        # together and are handled in the order they happened.
        self.events: queue.Queue[tuple[str, dict[str, Any]]] = events or queue.Queue()
        self.obs_version: str | None = None

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    # --- Connecting --------------------------------------------------------

    def connect(self) -> str:
        """Connect and log in. Returns the OBS version. Raises E050, E051 or E052."""
        try:
            self._transport = self._factory(self.url, self.timeout)
        except TransportClosed as exc:
            log.info("OBS not reachable at %s: %s", self.url, exc.reason, extra=FILE_ONLY)
            raise ObsNotReachable() from exc

        try:
            self._handshake()
        except TransportClosed as exc:
            self._transport.close()
            if exc.code == CLOSE_AUTHENTICATION_FAILED:
                raise ObsPasswordWrong() from exc
            if exc.code == CLOSE_UNSUPPORTED_RPC_VERSION:
                raise ObsTooOld() from exc
            log.info("OBS closed the connection while logging in: %s", exc, extra=FILE_ONLY)
            raise ObsNotReachable() from exc
        except (ValueError, KeyError, TypeError) as exc:
            # Something answered on the port, but it doesn't speak OBS.
            self._transport.close()
            log.warning("Unexpected reply on %s: %s", self.url, exc, extra=FILE_ONLY)
            raise ObsNotReachable("Something other than OBS answered on that port") from exc
        except AIEditorError:
            self._transport.close()
            raise

        settimeout = getattr(self._transport, "settimeout", None)
        if settimeout:
            settimeout(None)  # the reader waits as long as OBS stays quiet
        self._connected.set()
        threading.Thread(target=self._read_loop, name="obs-reader", daemon=True).start()
        self.obs_version = str(self.request("GetVersion").get("obsVersion", "unknown"))
        log.info("Connected to OBS %s at %s", self.obs_version, self.url)
        return self.obs_version

    def _handshake(self) -> None:
        assert self._transport is not None
        hello = self._expect(OP_HELLO)
        if int(hello.get("rpcVersion", 0)) < RPC_VERSION:
            raise ObsTooOld()
        identify: dict[str, Any] = {
            "rpcVersion": RPC_VERSION,
            "eventSubscriptions": SUBSCRIBE_GENERAL | SUBSCRIBE_OUTPUTS,
        }
        challenge = hello.get("authentication")
        if challenge:
            if not self._password:
                raise ObsPasswordWrong("No password has been saved in AI-Editor yet")
            identify["authentication"] = auth_string(
                self._password, challenge["salt"], challenge["challenge"]
            )
        self._send(OP_IDENTIFY, identify)
        self._expect(OP_IDENTIFIED)

    def _expect(self, op: int) -> dict[str, Any]:
        assert self._transport is not None
        while True:
            message = json.loads(self._transport.recv())
            if message["op"] == op:
                return message.get("d") or {}

    def _send(self, op: int, data: dict[str, Any]) -> None:
        assert self._transport is not None
        self._transport.send(json.dumps({"op": op, "d": data}))

    # --- Running -----------------------------------------------------------

    def _read_loop(self) -> None:
        assert self._transport is not None
        try:
            while True:
                message = json.loads(self._transport.recv())
                op, data = message.get("op"), message.get("d") or {}
                if op == OP_EVENT:
                    self.events.put((data.get("eventType", ""), data.get("eventData") or {}))
                elif op == OP_REQUEST_RESPONSE:
                    with self._lock:
                        waiter = self._pending.pop(data.get("requestId", ""), None)
                    if waiter:
                        waiter.response = data
                        waiter.done.set()
        except (TransportClosed, ValueError) as exc:
            if not self._closing:
                log.info("Connection to OBS ended: %s", exc, extra=FILE_ONLY)
        finally:
            self._connected.clear()
            with self._lock:
                waiters, self._pending = list(self._pending.values()), {}
            for waiter in waiters:
                waiter.done.set()  # response stays None: the request fails
            if not self._closing:
                self.events.put((DISCONNECTED, {}))

    def request(self, request_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Ask OBS something and wait for the answer."""
        if not self.connected:
            raise ObsNotReachable()
        request_id = uuid.uuid4().hex
        waiter = _Waiter()
        with self._lock:
            self._pending[request_id] = waiter
        payload: dict[str, Any] = {"requestType": request_type, "requestId": request_id}
        if data:
            payload["requestData"] = data
        try:
            self._send(OP_REQUEST, payload)
        except TransportClosed as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            raise ObsNotReachable() from exc

        if not waiter.done.wait(self.timeout) or waiter.response is None:
            with self._lock:
                self._pending.pop(request_id, None)
            raise ObsNotReachable("OBS stopped answering")
        status = waiter.response.get("requestStatus") or {}
        if not status.get("result"):
            raise ObsRequestFailed(f"{request_type}: {status.get('code')} {status.get('comment', '')}")
        return waiter.response.get("responseData") or {}

    def output_status(self, output: str) -> OutputStatus:
        """``output`` is "record" or "stream"."""
        data = self.request("GetRecordStatus" if output == "record" else "GetStreamStatus")
        return OutputStatus(
            active=bool(data.get("outputActive")),
            paused=bool(data.get("outputPaused", False)),
            duration_sec=float(data.get("outputDuration") or 0) / 1000.0,
        )

    def close(self) -> None:
        self._closing = True
        self._connected.clear()
        if self._transport is not None:
            self._transport.close()
