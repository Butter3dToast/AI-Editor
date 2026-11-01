"""Phase 4C-2: Import rebuilt in the new design, inside the window.
Today's Import in the browser is left exactly as it was."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_editor.app import import_screen
from ai_editor.app.worker import RUNNING, Task, Worker
from ai_editor.db import init_db

GUARD = {"X-AI-Editor": "1"}
OLD = time.time() - 3600          # finished an hour ago: not still being recorded


@pytest.fixture
def client(settings):
    import gradio as gr
    from fastapi.testclient import TestClient

    from ai_editor.app import frame_api

    worker = Worker()
    worker._start = lambda: None          # jobs stay queued: nothing really imports
    with gr.Blocks() as ui:
        gr.Markdown("today's screens")
    ui.queue()
    app = frame_api.build_app(settings, ui, worker, mount_kwargs={})
    with TestClient(app) as c:
        c.worker = worker
        yield c


def video(settings, name: str, *, when: float = OLD) -> Path:
    path = settings.folders.raw / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * 1000)
    os.utime(path, (when, when))
    return path


def probed(found):
    return {"length": "2:11:44", "duration": 7904.0, "sound": "5 tracks"}


# --- the raw folder's list ----------------------------------------------------------------


def test_new_files_with_their_game_and_whats_busy(settings):
    video(settings, "2026-10-30 19-02-11.mkv")
    video(settings, "Dawnwalker ep 10.mkv")
    video(settings, "2026-11-01 21-00-00.mkv", when=time.time())       # OBS still writing it
    video(settings, "notes.txt")
    queued = video(settings, "2026-10-29 18-55-20.mkv")
    busy = [Task(1, "Importing", f"import:{str(queued).lower()}", None, status=RUNNING)]
    conn = init_db(settings.db_path)
    try:
        found = {f["name"]: f for f in import_screen.new_files(conn, settings, probed, busy)}
    finally:
        conn.close()
    assert set(found) == {"2026-10-30 19-02-11.mkv", "Dawnwalker ep 10.mkv",
                          "2026-11-01 21-00-00.mkv", "2026-10-29 18-55-20.mkv"}
    stream = found["2026-10-30 19-02-11.mkv"]
    assert stream["length"] == "2:11:44" and stream["sound"] == "5 tracks"
    assert stream["when"].startswith("Fri 30 Oct")          # from OBS's name: when it began
    assert found["Dawnwalker ep 10.mkv"]["game"] == "The Blood of Dawnwalker"
    assert found["Dawnwalker ep 10.mkv"]["game_from"] == "the file name"
    recording = found["2026-11-01 21-00-00.mkv"]
    assert recording["still_recording"] and recording["sound"] == "-"   # not even probed
    assert found["2026-10-29 18-55-20.mkv"]["in_jobs"]


def test_the_companion_says_which_game(settings):
    path = video(settings, "2026-10-30 19-02-11.mkv")
    conn = init_db(settings.db_path)
    try:
        rows = [("obs_scene", "2026-10-30T18:59:00+00:00", {"scene": "Wardogs", "game": "Wardogs"}),
                ("obs_record_started", "2026-10-30T19:02:11+00:00", {"path": str(path)}),
                ("obs_scene", "2026-10-30T20:10:00+00:00",
                 {"scene": "Tarkov", "game": "Escape from Tarkov"}),
                ("obs_scene", "2026-10-31T09:00:00+00:00", {"scene": "x", "game": "Too late"})]
        conn.executemany("INSERT INTO companion_events (session_id, event_type, wall_clock, "
                         "payload_json) VALUES ('s1', ?, ?, ?)",
                         [(kind, at, json.dumps(payload)) for kind, at, payload in rows])
        conn.commit()
        found = import_screen.new_files(conn, settings, probed, [])
    finally:
        conn.close()
    assert found[0]["game"] == "Wardogs + Escape from Tarkov"     # the scene set before recording too
    assert found[0]["game_from"] == "the Stream Companion"


# --- importing ----------------------------------------------------------------------------


def test_several_ticked_are_queued_one_after_another(client, settings, monkeypatch):
    from ai_editor.app import tasks

    made = []
    monkeypatch.setattr(tasks, "import_file", lambda settings, path, **kw: made.append(
        (path.name, kw)) or (lambda report: None))
    a = video(settings, "2026-10-30 19-02-11.mkv")
    b = video(settings, "2026-10-29 18-55-20.mkv")
    assert client.post("/api/import/files", json={"paths": [str(a)]}).status_code == 403
    said = client.post("/api/import/files", headers=GUARD, json={
        "paths": [str(a), str(b), str(a)], "analyse": True, "game": "Wardogs",
        "tracks": "mixed,mic", "vod": "https://www.twitch.tv/videos/2875855539"}).json()["said"]
    assert said == "Added 2 to Jobs: they run one after another."
    # The one-file options are left out with several: each works its own out.
    assert [kw["game"] for _, kw in made] == [None, None]
    assert [kw["tracks"] for _, kw in made] == [None, None]
    assert [kw["vod_link"] for _, kw in made] == [None, None]
    assert [t.title for t in client.worker.snapshot()] == [
        "Importing and analysing 2026-10-30 19-02-11.mkv",
        "Importing and analysing 2026-10-29 18-55-20.mkv"]
    again = client.post("/api/import/files", headers=GUARD, json={"paths": [str(a)]}).json()
    assert again["said"] == "That's already in Jobs."
    listed = {f["name"]: f for f in client.get("/api/import").json()["files"]}
    assert listed["2026-10-30 19-02-11.mkv"]["in_jobs"]


def test_one_file_keeps_its_options(client, settings, monkeypatch):
    from ai_editor.app import tasks

    made = []
    monkeypatch.setattr(tasks, "import_file", lambda settings, path, **kw: made.append(kw)
                        or (lambda report: None))
    a = video(settings, "stream.mkv")
    said = client.post("/api/import/files", headers=GUARD, json={
        "paths": [str(a)], "analyse": False, "game": "tarkov", "tracks": " mixed,mic ",
        "vod": "https://www.twitch.tv/videos/2875855539"}).json()["said"]
    assert said == "Added to Jobs."
    assert made == [{"game": "Escape from Tarkov", "tracks": "mixed,mic",
                     "vod_link": "https://www.twitch.tv/videos/2875855539", "analyse": False}]
    assert client.worker.snapshot()[0].title == "Importing stream.mkv"


def test_what_cant_be_imported_says_why(client, settings):
    fresh = video(settings, "2026-11-01 21-00-00.mkv", when=time.time())
    said = client.post("/api/import/files", headers=GUARD,
                       json={"paths": [str(fresh), "C:/nowhere/x.mkv"]}).json()["said"]
    assert "changed in the last minute" in said and "There's no file at" in said
    assert client.post("/api/import/files", headers=GUARD, json={"paths": []}).json()["said"] \
        .startswith("Tick a recording")
    bad = client.post("/api/import/files", headers=GUARD,
                      json={"paths": [str(video(settings, "a.mkv"))], "vod": "not a link"})
    assert "Twitch" in bad.json()["said"] and client.worker.snapshot() == []


def test_a_twitch_vod_checked_then_queued(client, settings, monkeypatch):
    from ai_editor import twitch
    from ai_editor.app import tasks

    made = datetime(2026, 10, 30, 19, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(twitch, "vod_info", lambda settings, vod_id: twitch.VodInfo(
        vod_id, "Tarkov nights", "Butter3dToast96", made, 7904.0, "Escape from Tarkov"))
    assert client.post("/api/import/twitch/check", json={"link": "x"}).status_code == 403
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    found = import_screen.check_vod(settings, "https://www.twitch.tv/videos/2875855539", now)
    assert found["title"] == "Tarkov nights" and found["length"] == "2:11:44"
    assert found["deletes"].startswith("in ") and found["deletes"].endswith("days")
    assert import_screen.check_vod(settings, "no link here")["problem"]
    queued = []
    monkeypatch.setattr(tasks, "import_twitch", lambda settings, link, **kw: queued.append(kw)
                        or (lambda report: None))
    said = client.post("/api/import/twitch", headers=GUARD, json={
        "link": "https://www.twitch.tv/videos/2875855539", "chat": False}).json()["said"]
    assert said == "Added to Jobs." and queued == [{"game": None, "chat": False, "analyse": True}]
    assert client.worker.snapshot()[0].key == "twitch:2875855539"


def test_the_frame_draws_import_itself():
    frame = Path(import_screen.__file__).with_name("frame")
    page = (frame / "index.html").read_text(encoding="utf-8")
    assert '<script src="/frame/import.js"></script>' in page
    script = (frame / "import.js").read_text(encoding="utf-8")
    assert "NATIVE.import" in script and ".innerHTML" not in script   # text, never markup
