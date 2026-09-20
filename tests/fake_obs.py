"""A stand-in for OBS's WebSocket server, speaking the same protocol.

Lets the Companion be tested without OBS running: tests set what OBS is doing
(recording? for how long?) and push events, exactly as OBS would send them.
"""

from __future__ import annotations

import json
import queue
from typing import Any

from ai_editor.companion.obs import (
    CLOSE_AUTHENTICATION_FAILED,
    OP_EVENT,
    OP_HELLO,
    OP_IDENTIFIED,
    OP_IDENTIFY,
    OP_REQUEST,
    OP_REQUEST_RESPONSE,
    TransportClosed,
    auth_string,
)

SALT = "lM1GncleQOaCu9lT1yeUZhFYnqhsLLP1G5lAGo3ixaI="
CHALLENGE = "+IxH4CnCiqpX1rM9scsNynZzbOe4KhDeYcTNS3PDaeY="


class FakeObs:
    def __init__(self, password: str | None = "secret", *, rpc_version: int = 1,
                 running: bool = True, version: str = "32.2.2") -> None:
        self.password = password
        self.rpc_version = rpc_version
        self.running = running
        self.version = version
        self.outputs: dict[str, dict[str, Any]] = {
            "record": {"outputActive": False, "outputPaused": False, "outputDuration": 0},
            "stream": {"outputActive": False, "outputDuration": 0},
        }
        self.transports: list[FakeTransport] = []
        self.identified_with: dict[str, Any] | None = None
        # OBS's audio sources. The default is the setup manual chapter 7.3
        # recommends: the game and Discord captured per program, so nothing
        # captures what the PC as a whole plays.
        self.inputs: list[dict[str, Any]] = [
            {"inputName": "Mic/Aux", "inputKind": "wasapi_input_capture"},
            {"inputName": "Game", "inputKind": "wasapi_process_output_capture"},
        ]
        self.muted: set[str] = set()

    def factory(self, url: str, timeout: float) -> "FakeTransport":
        if not self.running:
            raise TransportClosed(None, "[WinError 10061] No connection could be made")
        transport = FakeTransport(self)
        self.transports.append(transport)
        return transport

    # --- What tests call ------------------------------------------------------

    def set_output(self, output: str, active: bool, seconds: float = 0.0, paused: bool = False) -> None:
        self.outputs[output]["outputActive"] = active
        self.outputs[output]["outputDuration"] = int(seconds * 1000)
        if output == "record":
            self.outputs[output]["outputPaused"] = paused

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        self.transports[-1].push({"op": OP_EVENT, "d": {
            "eventType": event_type, "eventIntent": 64, "eventData": data or {}}})

    def output_event(self, output: str, state: str, path: str | None = None) -> None:
        data: dict[str, Any] = {"outputActive": state.endswith(("STARTED", "RESUMED", "PAUSED")),
                                "outputState": f"OBS_WEBSOCKET_OUTPUT_{state}"}
        if output == "record":
            data["outputPath"] = path
        self.emit("RecordStateChanged" if output == "record" else "StreamStateChanged", data)

    def drop(self) -> None:
        """OBS closed, or the connection broke."""
        self.transports[-1].close_from_server(1001)

    # --- Protocol ------------------------------------------------------------

    def hello(self) -> dict[str, Any]:
        d: dict[str, Any] = {"obsWebSocketVersion": "5.6.3", "rpcVersion": self.rpc_version}
        if self.password is not None:
            d["authentication"] = {"challenge": CHALLENGE, "salt": SALT}
        return {"op": OP_HELLO, "d": d}

    def answer(self, request_type: str, data: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        if request_type == "GetVersion":
            return True, {"obsVersion": self.version, "obsWebSocketVersion": "5.6.3", "rpcVersion": 1}
        if request_type == "GetRecordStatus":
            return True, dict(self.outputs["record"])
        if request_type == "GetStreamStatus":
            return True, dict(self.outputs["stream"])
        if request_type == "GetInputList":
            return True, {"inputs": list(self.inputs)}
        if request_type == "GetInputMute":
            return True, {"inputMuted": data.get("inputName") in self.muted}
        return False, {}


class FakeTransport:
    def __init__(self, obs: FakeObs) -> None:
        self.obs = obs
        self.inbox: queue.Queue[str | TransportClosed] = queue.Queue()
        self.closed = False
        self.push(obs.hello())

    def push(self, message: dict[str, Any]) -> None:
        self.inbox.put(json.dumps(message))

    def close_from_server(self, code: int) -> None:
        self.inbox.put(TransportClosed(code, ""))

    def send(self, text: str) -> None:
        if self.closed:
            raise TransportClosed(None, "closed")
        message = json.loads(text)
        op, d = message["op"], message["d"]
        if op == OP_IDENTIFY:
            if d.get("rpcVersion", 0) > self.obs.rpc_version:
                self.close_from_server(4010)
                return
            if self.obs.password is not None:
                expected = auth_string(self.obs.password, SALT, CHALLENGE)
                if d.get("authentication") != expected:
                    self.close_from_server(CLOSE_AUTHENTICATION_FAILED)
                    return
            self.obs.identified_with = d
            self.push({"op": OP_IDENTIFIED, "d": {"negotiatedRpcVersion": 1}})
        elif op == OP_REQUEST:
            ok, data = self.obs.answer(d["requestType"], d.get("requestData") or {})
            self.push({"op": OP_REQUEST_RESPONSE, "d": {
                "requestType": d["requestType"], "requestId": d["requestId"],
                "requestStatus": {"result": ok, "code": 100 if ok else 204},
                "responseData": data}})

    def recv(self) -> str:
        try:
            item = self.inbox.get(timeout=30)
        except queue.Empty:
            item = TransportClosed(None, "test timed out")
        if isinstance(item, TransportClosed):
            self.closed = True
            raise item
        return item

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.inbox.put(TransportClosed(1000, "closed by client"))
