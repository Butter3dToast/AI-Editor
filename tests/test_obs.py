"""Connecting to OBS: logging in, asking questions, hearing events."""

from __future__ import annotations

import pytest

from ai_editor.companion.obs import DISCONNECTED, SUBSCRIBE_OUTPUTS, ObsClient, auth_string
from ai_editor.errors import ObsNotReachable, ObsPasswordWrong, ObsTooOld

from .fake_obs import CHALLENGE, SALT, FakeObs


def client_for(obs: FakeObs, password: str = "secret") -> ObsClient:
    return ObsClient("127.0.0.1", 4455, password, timeout=2.0, transport_factory=obs.factory)


def test_auth_string_matches_the_protocol_documentation():
    """The worked example from obs-websocket's protocol.md."""
    assert auth_string("supersecretpassword", SALT, CHALLENGE) == (
        "1Ct943GAT+6YQUUX47Ia/ncufilbe6+oD6lY+5kaCu4="
    )


def test_connects_and_reports_the_obs_version():
    obs = FakeObs()
    client = client_for(obs)
    try:
        assert client.connect() == "32.2.2"
        assert client.connected
        # Only the events the Companion needs are asked for.
        assert obs.identified_with["eventSubscriptions"] & SUBSCRIBE_OUTPUTS
    finally:
        client.close()


def test_the_password_itself_is_never_sent():
    obs = FakeObs()
    client = client_for(obs)
    try:
        client.connect()
        assert "secret" not in str(obs.identified_with)
    finally:
        client.close()


def test_obs_without_a_password_needs_none():
    obs = FakeObs(password=None)
    client = client_for(obs, password="")
    try:
        assert client.connect() == "32.2.2"
    finally:
        client.close()


def test_wrong_password_is_e051():
    with pytest.raises(ObsPasswordWrong):
        client_for(FakeObs(), password="nope").connect()


def test_no_saved_password_is_e051_and_says_so():
    with pytest.raises(ObsPasswordWrong, match="No password has been saved"):
        client_for(FakeObs(), password="").connect()


def test_obs_closed_is_e050():
    with pytest.raises(ObsNotReachable):
        client_for(FakeObs(running=False)).connect()


def test_old_obs_is_e052():
    with pytest.raises(ObsTooOld):
        client_for(FakeObs(rpc_version=0)).connect()


def test_something_else_on_the_port_is_e050():
    class NotObs:
        def send(self, text): pass
        def recv(self): return "HTTP/1.1 400 Bad Request"
        def close(self): pass

    client = ObsClient("127.0.0.1", 4455, "x", transport_factory=lambda url, t: NotObs())
    with pytest.raises(ObsNotReachable, match="Something other than OBS"):
        client.connect()


def test_output_status_in_seconds():
    obs = FakeObs()
    obs.set_output("record", True, seconds=754.25, paused=True)
    client = client_for(obs)
    try:
        client.connect()
        status = client.output_status("record")
        assert status.active and status.paused
        assert status.duration_sec == pytest.approx(754.25)
        assert not client.output_status("stream").active
    finally:
        client.close()


def test_events_arrive_on_the_queue():
    obs = FakeObs()
    client = client_for(obs)
    try:
        client.connect()
        obs.output_event("record", "STARTED", path="F:/AI-Editor/raw/a.mkv")
        event_type, data = client.events.get(timeout=2)
        assert event_type == "RecordStateChanged"
        assert data["outputPath"] == "F:/AI-Editor/raw/a.mkv"
    finally:
        client.close()


def test_obs_closing_is_reported_once():
    obs = FakeObs()
    client = client_for(obs)
    client.connect()
    obs.drop()
    assert client.events.get(timeout=2) == (DISCONNECTED, {})
    assert not client.connected
    with pytest.raises(ObsNotReachable):
        client.request("GetVersion")


def test_closing_it_ourselves_is_not_a_disconnection():
    obs = FakeObs()
    client = client_for(obs)
    client.connect()
    client.close()
    assert client.events.empty()
