"""Phase 4E: Create video rebuilt in the new design, inside the window.
Today's Create video in the browser is left exactly as it was."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_editor.app import create_screen
from ai_editor.app.worker import DONE, FAILED, Worker
from ai_editor.db import init_db

GUARD = {"X-AI-Editor": "1"}


@pytest.fixture
def client(settings):
    import gradio as gr
    from fastapi.testclient import TestClient

    from ai_editor.app import frame_api

    worker = Worker()
    worker._start = lambda: None          # jobs stay queued: nothing really runs
    with gr.Blocks() as ui:
        gr.Markdown("today's screens")
    ui.queue()
    app = frame_api.build_app(settings, ui, worker, mount_kwargs={})
    with TestClient(app) as c:
        c.worker = worker
        yield c


@pytest.fixture
def library(settings):
    """Two Wardogs streams (28 and 23 Oct), a League one whose video is deleted, and a
    Dawnwalker episode (a Let's Play game by default)."""
    conn = init_db(settings.db_path)
    rows = [(1, "Wardogs", "2026-10-28T20:00:00+00:00", 7200, True),
            (2, "Wardogs", "2026-10-23T20:00:00+00:00", 5400, True),
            (3, "League of Legends", "2026-10-25T20:00:00+00:00", 3600, False),
            (4, "The Blood of Dawnwalker", "2026-10-30T19:00:00+00:00", 6300, True)]
    for rid, game, when, length, kept in rows:
        video = settings.folders.raw / f"rec{rid}.mkv"
        if kept:
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(b"x")
        conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, game, "
                     "duration_sec, imported_at, recorded_at, analysis_status) "
                     "VALUES (?, ?, 'local_obs', ?, ?, ?, ?, ?, 'complete')",
                     (rid, f"h{rid}", str(video), game, length, when, when))
    clips = [("a", 1, 0.91, None, "[]"), ("b", 1, 0.88, 1, "[]"), ("c", 1, 0.95, -1, "[]"),
             ("d", 1, 0.97, None, json.dumps(["highlights_wardogs_1"])),
             ("e", 2, 0.86, 2, "[]")]
    for cid, rid, score, rating, used in clips:
        conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                     "user_rating, used_in_json, created_at) VALUES (?, ?, 0, 20, ?, ?, ?, 'now')",
                     (cid, rid, score, rating, used))
    for t in (100.0, 900.0):
        conn.execute("INSERT INTO companion_events (session_id, event_type, wall_clock, "
                     "recording_time_sec, recording_id) VALUES ('s', 'marker_short', 'now', ?, 1)",
                     (t,))
    conn.commit()
    conn.close()


def test_highlights_show_what_it_will_use_oldest_first(client, library):
    found = client.get("/api/create/highlights").json()
    assert found["games"][0] == "All my streams"
    assert "The Blood of Dawnwalker" not in found["games"]           # Let's Plays stay out
    assert found["minutes"] == 10.0 and found["which"] == "liked" and found["oldest"]
    rows = found["rows"]
    # Oldest first; the League stream's video is deleted, so it can't be used.
    assert [r["id"] for r in rows] == [2, 1]
    wardogs = rows[1]
    # 👎 never goes in; a clip already in a video only with "Use clips already in a video".
    assert (wardogs["free"], wardogs["liked"], wardogs["saved"]) == (2, 1, 0)
    assert rows[0]["saved"] == 1
    assert client.get("/api/create/highlights?reuse=true").json()["rows"][1]["free"] == 3
    assert [r["id"] for r in client.get(
        "/api/create/highlights?game=League of Legends").json()["rows"]] == []
    assert client.get("/api/create/nonsense").status_code == 404


def test_lets_play_and_shorts_pick_from_a_list(client, library):
    lets = client.get("/api/create/letsplay").json()
    assert [(r["id"], r["parts"]) for r in lets["rows"]] == [(4, 4)]   # 105 min, ~30 each
    assert lets["target"] == 30.0
    every = client.get("/api/create/letsplay?streams=true").json()["rows"]
    assert [r["id"] for r in every] == [4, 1, 2]                        # newest first
    shorts = client.get("/api/create/shorts").json()["rows"]
    assert [(r["id"], r["marks"], r["clips"]) for r in shorts] == [(4, 0, 0), (1, 2, 4), (2, 0, 1)]


def test_the_style_profile_is_picked_by_itself(client, library, settings):
    from ai_editor.style import profiles

    conn = init_db(settings.db_path)
    try:
        pid = profiles.create(conn, "Wardogs Hype")
        conn.execute("UPDATE style_profiles SET games_json = ?, applies_to_json = ? WHERE id = ?",
                     (json.dumps(["Wardogs"]), json.dumps(["highlights", "shorts"]), pid))
        conn.commit()
    finally:
        conn.close()
    assert client.get("/api/create/highlights").json()["picked_style"] is None
    found = client.get("/api/create/highlights?game=Wardogs").json()
    assert found["picked_style"] == pid and found["styles"] == [{"id": pid, "name": "Wardogs Hype"}]
    assert client.get("/api/create/shorts?recording=1").json()["picked_style"] == pid
    assert client.get("/api/create/letsplay?recording=4").json()["picked_style"] is None


def test_make_the_plan_starts_todays_job(client, library, monkeypatch):
    from ai_editor.app import tasks

    asked = {}
    monkeypatch.setattr(tasks, "make_highlights",
                        lambda settings, **kw: asked.update(kw) or (lambda report: None))
    monkeypatch.setattr(tasks, "make_letsplay", lambda s, rid, p: (lambda report: None))
    assert client.post("/api/create/make", json={"kind": "highlights"}).status_code == 403
    said = client.post("/api/create/make", headers=GUARD, json={
        "kind": "highlights", "game": "All my streams", "minutes": "12", "which": "saved",
        "reuse": True, "recordings": [2], "style": -1}).json()
    assert said["said"].startswith("Making the plan. It opens in Review")
    assert asked == {"game": None, "recording_ids": [2], "minutes": 12.0, "reuse": True,
                     "profile": None, "only_liked": False, "saved": True}
    job = said["job"]
    # The same streams again would replace that draft: it watches the one being made.
    again = client.post("/api/create/make", headers=GUARD, json={
        "kind": "highlights", "minutes": "20", "recordings": [2]}).json()
    assert again["job"] == job and "already being made" in again["said"]
    # Other streams, or all of them, queue a plan of their own (1 Nov).
    other = client.post("/api/create/make", headers=GUARD, json={
        "kind": "highlights", "recordings": [3, 1]}).json()
    every = client.post("/api/create/make", headers=GUARD, json={"kind": "highlights"}).json()
    assert len({job, other["job"], every["job"]}) == 3
    assert client.post("/api/create/make", headers=GUARD, json={
        "kind": "highlights", "minutes": "90"}).json()["said"] == \
        "The length is between 1 and 60 minutes."
    assert client.post("/api/create/make", headers=GUARD, json={
        "kind": "letsplay"}).json()["said"] == "Pick the episode's recording first."
    lp = client.post("/api/create/make", headers=GUARD,
                     json={"kind": "letsplay", "recording": 4}).json()
    assert [t.key for t in client.worker.snapshot()] == [
        "make:highlights:None:2", "make:highlights:None:1,3", "make:highlights:None:all",
        "make:letsplay:4"]
    assert lp["job"] == client.worker.snapshot()[3].id


def test_a_finished_plan_is_found_to_open_in_review(client, library):
    worker = client.worker
    task = worker.submit("Making a plan", "make:highlights:None", lambda report: None)
    assert client.get(f"/api/create/job/{task.id}").json() == {"state": "waiting"}
    with worker._lock:
        worker._tasks[0].status = DONE
        worker._tasks[0].result = {"plan_id": "highlights_stream_3"}
    assert client.get(f"/api/create/job/{task.id}").json()["plan"] == "highlights_stream_3"
    with worker._lock:
        worker._tasks[0].status = FAILED
        worker._tasks[0].error = "No clips left to use."
    assert client.get(f"/api/create/job/{task.id}").json() == {
        "state": "failed", "error": "No clips left to use."}
    assert client.get("/api/create/job/999").json() == {"state": "gone"}


def test_clips_make_a_video_opens_on_the_right_kind(client, library):
    assert client.get("/api/create/from/1").json() == {"kind": "highlights", "recording": 1}
    assert client.get("/api/create/from/4").json() == {"kind": "letsplay", "recording": 4}


def test_the_frame_draws_create_video_itself():
    frame = Path(create_screen.__file__).with_name("frame")
    page = (frame / "index.html").read_text(encoding="utf-8")
    assert '<script src="/frame/create.js"></script>' in page
    script = (frame / "create.js").read_text(encoding="utf-8")
    assert "NATIVE.create" in script and ".innerHTML" not in script   # text, never markup
    # The creator's choices: open in Review if still here, else a note with a button.
    assert 'window.aie.current() === "create"' in script and '"Open in Review"' in script
    # ...but only when it's the one plan being made: several queued each say so instead.
    assert 'window.aie.current() === "create" && queued === 1' in script
    # The creator's test: a recording with no style profile couldn't be picked, because the
    # screen only redrew when the server's answer changed.
    assert "JSON.stringify([found, form.recording])" in script
    assert "form.recording = r.id; form.style = null; table(); load();" in script
    clips = (frame / "clips.js").read_text(encoding="utf-8")
    assert 'window.aie.show("create", rec === null ? undefined : { recording: rec })' in clips
