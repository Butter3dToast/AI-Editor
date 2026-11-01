"""Phase 4F-2: finishing a video in the new Review -- captions, effects and music,
fixing caption lines, Render (after a last look), Open and Export. Effects and
burned-in captions stay off unless the creator switches them on."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_editor.app import review_finish
from ai_editor.app.worker import Worker
from ai_editor.db import init_db
from ai_editor.recipes.plan import EditPlan, Segment, save_plan

GUARD = {"X-AI-Editor": "1"}
PLAN = "highlights_wardogs_2026-11-01_1"
SHORT = "shorts_wardogs_2026-11-01_1"


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
    """A Wardogs stream with words said in its first clip, a highlight plan and a Short."""
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
    for n, (word, t) in enumerate((("no", 3860.0), ("way", 3860.4), ("he's", 3860.8),
                                   ("still", 3861.2), ("alive", 3861.6))):
        conn.execute("INSERT INTO transcript_words (recording_id, idx, word, start_sec, "
                     "end_sec) VALUES (1, ?, ?, ?, ?)", (n, word, t, t + 0.35))
    save_plan(conn, EditPlan(PLAN, "highlights", "Wardogs highlights", "Wardogs", 600, [
        Segment(1, 3858, 3882, clip_id="a", game="Wardogs", score=0.9),
        Segment(1, 1000, 1020, clip_id="b", game="Wardogs", score=0.8)]))
    save_plan(conn, EditPlan(SHORT, "shorts", "Wardogs Short", "Wardogs", 60, [
        Segment(1, 1000, 1030, clip_id="b", game="Wardogs", score=0.8)]))
    conn.commit()
    conn.close()


def test_everything_starts_off(client, library):
    fin = client.get(f"/api/review/{PLAN}/finishing").json()
    assert fin["captions"] is False                                  # defaults off, always
    assert [e["on"] for e in fin["effects"]] == [False] * 5
    assert [e["label"] for e in fin["effects"]][:2] == ["Flash", "Screen shake"]
    assert fin["between"] == "cut" and fin["layout"] is None and not fin["lets_play"]
    short = client.get(f"/api/review/{SHORT}/finishing").json()
    assert short["between"] is None and short["layout"]["value"] in ("crop", "fit")
    assert [k for k, _ in short["layout"]["choices"]][:2] == ["crop", "fit"]


def test_captions_are_kept_with_the_plan_and_undone(client, library):
    url = f"/api/review/{PLAN}"
    assert client.post(f"{url}/set", json={"what": "captions", "value": True}).status_code == 403
    said = client.post(f"{url}/set", headers=GUARD, json={"what": "captions", "value": True})
    assert said.json()["said"] == "Your words will be burned into this video."
    assert client.get(f"{url}/finishing").json()["captions"] is True     # kept with the plan
    facts = dict(client.get(f"{url}/clip/0").json()["facts"])
    assert facts["Captions"] == "On · your words"
    assert client.get(f"/api/review?plan={PLAN}").json()["undo"] == "burned-in captions"
    client.post(f"{url}/undo", headers=GUARD)
    assert client.get(f"{url}/finishing").json()["captions"] is False


def test_effects_music_between_and_layout(client, library, settings):
    url = f"/api/review/{PLAN}/set"
    said = client.post(url, headers=GUARD, json={"what": "effects", "value": ["shake", "flash"]})
    assert said.json()["said"].startswith("Effects in this video: Flash, Screen shake.")
    fin = client.get(f"/api/review/{PLAN}/finishing").json()
    assert [e["key"] for e in fin["effects"] if e["on"]] == ["flash", "shake"]
    assert client.post(url, headers=GUARD, json={"what": "between", "value": "slide"}).json()[
        "said"].startswith("Each clip slides in")
    client.post(url, headers=GUARD, json={"what": "music", "value": False})
    fin = client.get(f"/api/review/{PLAN}/finishing").json()
    assert fin["between"] == "slide" and fin["music"] is False
    assert client.post(url, headers=GUARD, json={"what": "layout", "value": "fit"}).json()[
        "said"] == "The layout is for Shorts."
    assert client.post(f"/api/review/{SHORT}/set", headers=GUARD, json={
        "what": "layout", "value": "fit"}).json()["said"].startswith("This Short will use Whole")
    assert client.post(url, headers=GUARD, json={"what": "nonsense"}).json()["said"] == \
        "That isn't something Review can change."
    # What was ticked is kept for learning (3A-1), as in today's Review.
    conn = init_db(settings.db_path)
    try:
        ticks = [json.loads(r[0])["effect"] for r in conn.execute(
            "SELECT detail_json FROM feedback WHERE action = 'effect_on' ORDER BY id")]
    finally:
        conn.close()
    assert ticks == ["flash", "shake"]


def test_fixing_a_caption_line(client, library):
    found = client.get(f"/api/review/{PLAN}/lines/0").json()
    assert found["what"] == "clip 1"
    line = found["lines"][0]
    assert line["text"] == "no way he's still alive" and line["at"] == "0:02"
    url = f"/api/review/{PLAN}/line"
    said = client.post(url, headers=GUARD, json={"index": 0, "key": line["key"],
                                                 "action": "save",
                                                 "text": "no way he's still alive!"}).json()
    assert "said" in said
    again = client.get(f"/api/review/{PLAN}/lines/0").json()["lines"][0]
    assert again["text"] == "no way he's still alive!" and again["edited"]
    client.post(url, headers=GUARD, json={"index": 0, "key": again["key"], "action": "hide"})
    assert client.get(f"/api/review/{PLAN}/lines/0").json()["lines"][0]["hidden"]
    client.post(url, headers=GUARD, json={"index": 0, "key": again["key"], "action": "back"})
    back = client.get(f"/api/review/{PLAN}/lines/0").json()["lines"][0]
    assert back["text"] == "no way he's still alive"
    assert client.post(url, headers=GUARD, json={"index": 0, "key": "9-9",
                                                 "action": "save"}).json()["said"] == \
        "Click a caption line first."


def test_render_after_a_last_look(client, library, monkeypatch):
    from ai_editor.app import tasks

    asked = {}
    monkeypatch.setattr(tasks, "render", lambda settings, plan_id, **kw: asked.update(
        kw, plan=plan_id) or (lambda report: None))
    check = client.get(f"/api/review/{PLAN}/render").json()
    rows = dict(check["rows"])
    assert rows["Captions"] == "Off" and rows["Effects"] == "None"
    assert rows["Between clips"] == "Hard cuts" and rows["Length"].startswith("0:44 (target")
    assert not check["lets_play"] and not check["shorts"]
    client.post(f"/api/review/{PLAN}/set", headers=GUARD, json={"what": "captions",
                                                                "value": True})
    assert client.post(f"/api/review/{PLAN}/render", json={}).status_code == 403
    said = client.post(f"/api/review/{PLAN}/render", headers=GUARD, json={}).json()
    assert said["said"].startswith("Rendering:") and said["job"]
    assert asked == {"plan": PLAN, "captions": True, "episode": None, "parts": None}
    assert client.get(f"/api/review/render-job/{said['job']}").json() == {"state": "waiting"}
    assert "Press Render it first" in client.post(f"/api/review/{PLAN}/open", headers=GUARD,
                                                  json={}).json()["said"]
    assert client.post(f"/api/review/{SHORT}/export", headers=GUARD,
                       json={}).json()["said"].startswith("Shorts are finished here")


def test_the_frame_draws_the_finishing_tabs_itself():
    frame = Path(review_finish.__file__).with_name("frame")
    script = (frame / "review.js").read_text(encoding="utf-8")
    assert "function captionsTab" in script and "function effectsTab" in script
    assert "function renderPanel" in script and '"Render it"' in script
    assert ".innerHTML" not in script                           # text, never markup
    assert '"Burn in captions (your words)"' in script
    assert json.dumps("Export to DaVinci Resolve") in script
