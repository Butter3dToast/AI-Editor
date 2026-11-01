"""Phase 4C-1: the Library rebuilt in the new design, inside the window.
Today's Library in the browser is left exactly as it was."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ai_editor.app import library_screen
from ai_editor.app.worker import DONE, PAUSED, RUNNING, WAITING, Task, Worker
from ai_editor.db import init_db

GUARD = {"X-AI-Editor": "1"}


@pytest.fixture
def client(settings):
    import gradio as gr
    from fastapi.testclient import TestClient

    from ai_editor.app import frame_api

    worker = Worker()
    with gr.Blocks() as ui:
        gr.Markdown("today's screens")
    ui.queue()
    app = frame_api.build_app(settings, ui, worker, mount_kwargs={})
    with TestClient(app) as c:
        c.worker = worker
        yield c


def add(settings, rid: int, *, game="Wardogs", status="complete", exists=True, title=None,
        recorded="2026-10-28T20:14:03+00:00"):
    conn = init_db(settings.db_path)
    video = settings.folders.raw / f"stream {rid}.mkv"
    proxy = settings.folders.cache / f"proxy {rid}.mp4"
    if exists:
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"x")
        proxy.parent.mkdir(parents=True, exist_ok=True)
        proxy.write_bytes(b"x")
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, game, title, "
                 "duration_sec, imported_at, recorded_at, analysis_status, proxy_path) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (rid, f"h{rid}", "local_obs", str(video), game, title, 7904,
                  "2026-10-28T21:00:00+00:00", recorded, status, str(proxy)))
    conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role, extracted_path) "
                 "VALUES (?, 1, 'mic', 'x.wav')", (rid,))
    conn.commit()
    conn.close()
    return video


# --- how it reads -----------------------------------------------------------------------


def test_days_read_as_the_design_writes_them():
    now = datetime(2026, 11, 1, 12, 0).astimezone()
    at = lambda days: (now - timedelta(days=days)).isoformat()  # noqa: E731
    assert library_screen.short_day(at(0), now) == "Today"
    assert library_screen.short_day(at(1), now) == "Yesterday"
    assert library_screen.short_day(at(4), now) == (now - timedelta(days=4)).strftime("%a")
    assert library_screen.short_day(at(9), now) == "23 Oct"
    assert library_screen.short_day(at(400), now).endswith("2025")
    assert library_screen.short_day(None, now) == "-"
    assert library_screen.hms(7904) == "2:11:44" and library_screen.hms(None) == "-"


def test_the_status_comes_from_the_job_working_on_it():
    row = {"id": 4, "source_file": __file__, "proxy_path": __file__, "tracks": 1,
           "tracks_ready": 1, "analysis_status": "pending"}
    running = Task(1, "Analysing #4", "analyse:4", lambda r: None, status=RUNNING)
    assert library_screen.status(row, running, 62) == ("Analysing · 62%", "run")
    assert library_screen.status(row, running) == ("Analysing", "run")
    assert library_screen.status(row, running, 0) == ("Analysing", "run")    # no "0%"
    waiting = Task(2, "Importing x", "import:x", lambda r: None, status=WAITING)
    assert library_screen.status(row, waiting) == ("Waiting in Jobs", "wait")
    assert library_screen.status(row, None) == ("Not analysed", "off")
    gone = {**row, "source_file": "C:/nowhere/gone.mkv"}
    assert library_screen.status(gone, running) == ("Video deleted", "off")
    # A finished job is the library's say again; another recording's job isn't this one's.
    assert library_screen.task_for(row, [Task(3, "a", "analyse:4", None, status=DONE)]) is None
    assert library_screen.task_for(row, [Task(3, "a", "analyse:5", None, status=PAUSED)]) is None
    found = Task(5, "Importing", "import:y", None, status=PAUSED)
    found.result["recording_id"] = 4
    assert library_screen.task_for(row, [found]) is found


# --- the screen's answers -----------------------------------------------------------------


def test_the_list_newest_first_with_lets_plays_marked(client, settings):
    add(settings, 1, recorded="2026-10-21T20:00:00+00:00")
    add(settings, 2, game="The Blood of Dawnwalker", title="Dawnwalker ep 9",
        recorded="2026-10-26T20:00:00+00:00")
    add(settings, 3, status="pending", exists=False, recorded="2026-10-27T20:00:00+00:00")
    found = client.get("/api/library").json()["recordings"]
    assert [r["id"] for r in found] == [3, 2, 1]
    deleted, lets_play, stream = found
    assert deleted["status"] == "Video deleted" and deleted["state"] == "off"
    assert lets_play["lets_play"] and lets_play["name"] == "Dawnwalker ep 9"
    assert not stream["lets_play"] and stream["status"] == "Analysed"
    assert stream["length"] == "2:11:44" and stream["name"] == "stream 1"


def test_the_picked_recordings_details(client, settings):
    add(settings, 1)
    found = client.get("/api/library/1").json()
    facts = dict(found["facts"])
    assert facts["Sound"] == "1 mixed track" and facts["Companion"] == "Not linked"
    assert facts["Preview copy"] == "Ready" and facts["From"] == "OBS on this PC"
    assert found["line"].startswith("Wardogs · recorded ") and not found["gone"]
    assert client.get("/api/library/99").status_code == 404


def test_the_game_can_be_set_after_importing(client, settings):
    """1 Nov: a Dawnwalker episode named only by its date, with the Companion off, came
    in with no game, so it counted as a stream and Let's Play didn't list it."""
    add(settings, 35, game=None)
    found = client.get("/api/library/35").json()
    assert found["game"] == "" and "The Blood of Dawnwalker" in found["games"]
    assert "Crimson Desert" in found["games"] or "Crimson Desert" not in settings.lets_play.games
    settings.lets_play.games.append("Crimson Desert")
    assert "Crimson Desert" in client.get("/api/library/35").json()["games"]
    assert client.post("/api/library/35/game", json={"game": "x"}).status_code == 403
    said = client.post("/api/library/35/game", headers=GUARD,
                       json={"game": "  the blood of dawnwalker "}).json()["said"]
    assert said.startswith("#35 is now The Blood of Dawnwalker: a Let's Play episode")
    assert client.get("/api/library/35").json()["game"] == "The Blood of Dawnwalker"
    lets = client.get("/api/create/letsplay").json()["rows"]
    assert [r["id"] for r in lets] == [35]                         # now in Let's Play
    assert client.get("/api/create/highlights").json()["rows"] == []   # out of highlights
    assert client.post("/api/library/35/game", headers=GUARD,
                       json={"game": " "}).json()["said"] == "Type or pick the game first."
    assert client.post("/api/library/99/game", headers=GUARD, json={"game": "Wardogs"}).json()[
        "said"] == "That recording isn't in the library."


def test_analyse_is_a_job_queued_like_any_other(client, settings, monkeypatch):
    from ai_editor.app import tasks

    add(settings, 1)
    add(settings, 2, exists=False)
    monkeypatch.setattr(tasks, "analyse", lambda settings, rid: (lambda report: None))
    client.worker._start = lambda: None          # kept waiting, so it's still in Jobs
    assert client.post("/api/library/1/analyse").status_code == 403    # no web page can
    said = client.post("/api/library/1/analyse", headers=GUARD).json()["said"]
    assert said == "Added to Jobs."
    assert [t.key for t in client.worker.snapshot()] == ["analyse:1"]
    again = client.post("/api/library/1/analyse", headers=GUARD).json()["said"]
    assert again == "That's already in Jobs."
    gone = client.post("/api/library/2/analyse", headers=GUARD).json()["said"]
    assert "isn't at" in gone and len(client.worker.snapshot()) == 1
    listed = {r["id"]: r for r in client.get("/api/library").json()["recordings"]}
    assert listed[1]["status"] == "Waiting in Jobs"


def test_buttons_need_the_header_and_know_their_names(client, settings):
    add(settings, 1)
    for path in ("/api/library/1/watch", "/api/library/1/explore",
                 "/api/library/1/voices/A/name", "/api/library/1/voices/A/not"):
        assert client.post(path).status_code == 403, path
    assert client.post("/api/library/1/delete", headers=GUARD).status_code == 404
    assert client.get("/api/library/1/voices/a1.wav").status_code == 404   # not a voice's name


def test_whos_talking_names_a_voice(client, settings, monkeypatch):
    from ai_editor.analysis import voices

    add(settings, 1)
    named = []
    monkeypatch.setattr(voices, "name_voice",
                        lambda conn, rid, label, name: named.append((rid, label, name)) or
                        f"Voice {label} is **{name}** now, in their own colour.")
    said = client.post("/api/library/1/voices/A/name", headers=GUARD,
                       json={"name": "Rocco"}).json()["said"]
    assert named == [(1, "A", "Rocco")] and "Rocco" in said
    found = client.get("/api/library/1/voices").json()
    assert found["voices"] == [] and "Discord" in found["intro"]


def test_the_frame_draws_the_library_itself():
    frame = Path(library_screen.__file__).with_name("frame")
    page = (frame / "index.html").read_text(encoding="utf-8")
    assert '<script src="/frame/library.js"></script>' in page and 'id="native"' in page
    script = (frame / "library.js").read_text(encoding="utf-8")
    assert "NATIVE.library" in script and ".innerHTML" not in script   # text, never markup
