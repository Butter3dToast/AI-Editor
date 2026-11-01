"""Phase 4F-1: Review rebuilt in the new design (editing the cut), inside the window.
Today's Review in the browser is left exactly as it was."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_editor.app import review_screen, videos
from ai_editor.app.worker import DONE, Worker
from ai_editor.db import init_db
from ai_editor.recipes.plan import EditPlan, Segment, save_plan

GUARD = {"X-AI-Editor": "1"}
PLAN = "highlights_wardogs_2026-11-01_1"


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
    """One Wardogs stream and a highlight plan of it: a teaser and three clips."""
    video = settings.folders.raw / "stream.mkv"
    proxy = settings.folders.cache / "recordings" / "h1" / "proxy.mp4"
    for path in (video, proxy):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    conn = init_db(settings.db_path)
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, game, "
                 "duration_sec, imported_at, recorded_at, analysis_status, proxy_path) "
                 "VALUES (1, 'h1', 'local_obs', ?, 'Wardogs', 7200, '2026-10-28T21:00:00+00:00', "
                 "'2026-10-28T20:14:03+00:00', 'complete', ?)", (str(video), str(proxy)))
    for cid, start, end in (("a", 3858, 3882), ("b", 1000, 1020), ("c", 2000, 2030)):
        conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                     "signals_json, created_at) VALUES (?, 1, ?, ?, 0.9, ?, 'now')",
                     (cid, start, end, json.dumps({"reasons": ["marker", "gunfire"]})))
    save_plan(conn, EditPlan(PLAN, "highlights", "Wardogs highlights", "Wardogs", 600, [
        Segment(1, 3870, 3876, kind="teaser", clip_id="a", game="Wardogs", score=0.9),
        Segment(1, 3858, 3882, clip_id="a", game="Wardogs", score=0.9,
                reasons=["marker", "gunfire"]),
        Segment(1, 1000, 1020, clip_id="b", game="Wardogs", score=0.8, reasons=["laughter"]),
        Segment(1, 2000, 2030, clip_id="c", game="Wardogs", score=0.7)]))
    conn.commit()
    conn.close()


def test_review_shows_the_plan_the_designers_way(client, library):
    found = client.get("/api/review").json()                  # none asked: the newest
    plan = found["plan"]
    assert plan["id"] == PLAN and plan["title"] == "Wardogs highlights"
    assert plan["line"] == "Draft · 3 clips · 1:20" and plan["editable"]
    assert found["plans"][0]["id"] == PLAN and found["plans"][0]["status"] == "draft"
    assert [r["label"] for r in found["rows"]] == ["T", "2", "3", "4"]
    first = found["rows"][1]
    assert (first["from"], first["at"], first["length"]) == ("Wardogs", "1:04:18", "24 s")
    assert first["why"].startswith("⭐") and found["rows"][0]["why"].startswith("Teaser · ")
    bar = found["bar"]
    assert [b["kind"] for b in bar["blocks"]][:2] == ["teaser", "c1"]
    assert bar["tone"] == "under" and "under your 10:00 target" in bar["rest"]
    assert 0 < bar["target"] <= 100
    assert found["undo"] is None and found["preview"] is None
    assert client.get("/api/review?plan=nonsense").json()["plan"]["id"] == PLAN


def test_a_clips_details_beside_the_player(client, library):
    found = client.get(f"/api/review/{PLAN}/clip/1").json()
    facts = dict(found["facts"])
    assert facts["From"].startswith("Wardogs") and facts["Starts"] == "1:04:18"
    assert facts["Ends"] == "1:04:42" and facts["Why it's in"].startswith("⭐")
    assert facts["Captions"] == "Off" and facts["Effects"] == "Off"    # off by default
    assert found["video"].startswith("/classic/gradio_api/file=") and "proxy.mp4?v=" in found["video"]
    assert (found["start"], found["end"], found["rid"]) == (3858, 3882, 1)
    assert client.get(f"/api/review/{PLAN}/clip/9").status_code == 404


def test_a_change_is_one_undo_step_as_in_todays_review(client, library):
    url = f"/api/review/{PLAN}"
    assert client.post(f"{url}/edit", json={"action": "move_to", "index": 3,
                                             "extra": 2}).status_code == 403
    said = client.post(f"{url}/edit", headers=GUARD,
                       json={"action": "move_to", "index": 3, "extra": 2}).json()
    assert said == {"said": "Moved to #2.", "selected": 1}
    found = client.get(url.replace(f"/{PLAN}", f"?plan={PLAN}")).json()
    assert [r["at"] for r in found["rows"]][1:] == ["0:33:20", "1:04:18", "0:16:40"]
    assert found["undo"] == "moving clip 4 to #2"
    assert client.post(f"{url}/undo", headers=GUARD).json()["said"] == \
        "Undone: moving clip 4 to #2."
    assert client.post(f"{url}/redo", headers=GUARD).json()["said"] == \
        "Redone: moving clip 4 to #2."
    # The teaser stays first, and nonsense is refused.
    assert "teaser always opens" in client.post(f"{url}/edit", headers=GUARD, json={
        "action": "move_to", "index": 0, "extra": 3}).json()["said"]
    assert client.post(f"{url}/edit", headers=GUARD, json={
        "action": "explode", "index": 1}).json()["said"] == "That isn't something Review can do."
    assert client.post(f"{url}/edit", headers=GUARD, json={
        "action": "remove", "index": 99}).json()["said"] == "Click a clip in the list first."


def test_a_new_cut_is_saved_only_when_it_changed(client, library):
    url = f"/api/review/{PLAN}/cut"
    same = {"start": 3858, "end": 3882, "was": [3858, 3882], "rid": 1}
    assert client.post(url, headers=GUARD, json={"cut": same}).json()["said"].startswith(
        "Nothing to save")
    assert client.post(url, headers=GUARD, json={"cut": dict(same, end=3858.5)}).json()[
        "said"] == "The end must be after the start."
    gone = dict(same, start=3850, was=[1, 2])
    assert "changed since you clicked it" in client.post(url, headers=GUARD,
                                                         json={"cut": gone}).json()["said"]


def test_quick_preview_is_a_job_watched_until_ready(client, library, settings):
    url = f"/api/review/{PLAN}/preview"
    assert client.post(url, json={}).status_code == 403
    said = client.post(url, headers=GUARD, json={"part": None}).json()
    assert said["said"].startswith("Making the quick preview")
    worker = client.worker
    assert worker.snapshot()[0].key == f"preview:{PLAN}:None"
    assert client.get(f"/api/review/job/{said['job']}").json() == {"state": "waiting"}
    made = settings.folders.output / "previews" / "p.mp4"
    made.parent.mkdir(parents=True, exist_ok=True)
    made.write_bytes(b"x")
    with worker._lock:
        worker._tasks[0].status = DONE
        worker._tasks[0].result = {"preview": str(made)}
    ready = client.get(f"/api/review/job/{said['job']}").json()
    assert ready["state"] == "ready" and "p.mp4?v=" in ready["url"]


def test_deleting_plans_and_todays_review_on_the_same_plan(client, library):
    assert client.post("/api/review/classic", json={"plan": PLAN}).status_code == 403
    client.post("/api/review/classic", headers=GUARD, json={"plan": PLAN})
    assert videos.WANTED.take() == PLAN and videos.WANTED.take() is None   # taken once
    assert client.post("/api/review/delete", json={"plans": [PLAN]}).status_code == 403
    assert client.post("/api/review/delete", headers=GUARD,
                       json={"plans": [PLAN]}).json()["said"] == "Deleted 1 plan from the list."
    assert client.get("/api/review").json() == {"plans": [], "plan": None,
                                                "version": client.worker.version}


def test_the_frame_draws_review_itself():
    frame = Path(review_screen.__file__).with_name("frame")
    page = (frame / "index.html").read_text(encoding="utf-8")
    assert '<script src="/frame/review.js"></script>' in page
    script = (frame / "review.js").read_text(encoding="utf-8")
    assert "NATIVE.review" in script and ".innerHTML" not in script   # text, never markup
    # The creator's choices: pinned like Clips, tabs under the list, Today's Review.
    assert 'class: "stage clip-stage rv-stage"' in script
    assert '"Effects & music"' in script and 'window.aie.classic("Review")' in script
    # Deleting is only ever the creator's doing, asked once more.
    assert script.count("window.confirm(") == 2
    # Create video hands its new plan over.
    create = (frame / "create.js").read_text(encoding="utf-8")
    assert 'window.aie.show("review", { plan })' in create
    # Today's Review takes the plan the window asks for.
    tabs = Path(videos.__file__).with_name("video_tabs.py").read_text(encoding="utf-8")
    assert "wanted = videos.WANTED.take()" in tabs and "chosen = wanted if wanted in ids" in tabs
