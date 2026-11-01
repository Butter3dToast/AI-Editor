"""Phase 4F-3a: Review's Publish tab in the new design -- the upload text, the YouTube
link, and each thumbnail frame on a card with its prompt for the Gemini app. The same
jobs and the same saved text as today's Review; a Let's Play shows the part clicked."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor import publish
from ai_editor.app import review_publish
from ai_editor.app.worker import Worker
from ai_editor.db import init_db
from ai_editor.recipes.plan import EditPlan, Segment, load_plan, save_plan

GUARD = {"X-AI-Editor": "1"}
PLAN = "highlights_wardogs_2026-11-01_1"
LP = "letsplay_the-blood-of-dawnwalker_2026-11-01_1"
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


def written(settings, n_frames=2, prompts=True) -> dict:
    folder = settings.folders.output / "thumbnails" / "x"
    folder.mkdir(parents=True, exist_ok=True)
    thumbs = []
    for n in range(n_frames):
        path = folder / f"frame {n}.png"
        path.write_bytes(b"png")
        thumbs.append(publish.Thumbnail(path, 8 - n, "Clear fight", "Make it pop" if prompts else ""))
    thumbs.append(publish.Thumbnail(folder / "gone.png", 9, "Deleted since"))   # never shown
    return publish.Publish(["Holding the Zone", "Last One Standing"], "We held it.", ["wardogs"],
                           [(0.0, "Intro")], thumbs, "fp", "2026-11-01T20:15:00").as_dict()


@pytest.fixture
def library(settings):
    video = settings.folders.raw / "Dawnwalker EP 6.mkv"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"x")
    conn = init_db(settings.db_path)
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, game, "
                 "duration_sec, imported_at, analysis_status) VALUES (1, 'h1', 'local_obs', ?, "
                 "'Wardogs', 7200, '2026-10-28T21:00:00+00:00', 'complete'), (2, 'h2', "
                 "'local_obs', ?, 'The Blood of Dawnwalker', 7200, '2026-10-30T21:00:00+00:00', "
                 "'complete')", (str(video), str(video)))
    save_plan(conn, EditPlan(PLAN, "highlights", "Wardogs highlights", "Wardogs", 600, [
        Segment(1, 100, 140, clip_id="a", game="Wardogs")]))
    save_plan(conn, EditPlan(LP, "letsplay", "Dawnwalker EP 6", "The Blood of Dawnwalker", 0, [
        Segment(2, n * 600, n * 600 + 560, kind="piece", part=n // 2 + 1) for n in range(4)]))
    save_plan(conn, EditPlan(SHORT, "shorts", "Wardogs Short", "Wardogs", 60, [
        Segment(1, 100, 130, clip_id="a", game="Wardogs")]))
    conn.commit()
    conn.close()


def put(settings, plan_id, key, data):
    conn = init_db(settings.db_path)
    plan, status = load_plan(conn, plan_id)
    plan.publish[key] = data
    save_plan(conn, plan, status)
    conn.close()


def test_nothing_written_yet_says_what_write_does(client, library):
    hl = client.get(f"/api/review/{PLAN}/publish").json()
    assert not hl["written"] and hl["which"] == "this video" and hl["link"] == ""
    assert hl["note"].startswith("Nothing written for this video yet.")
    lp = client.get(f"/api/review/{LP}/publish").json()
    assert lp["parts"] == [1, 2] and lp["part"] == 1 and lp["episode"] == 6
    assert client.get(f"/api/review/{LP}/publish?part=2").json()["which"] == "Part 2"
    assert client.get(f"/api/review/{LP}/publish?part=9").json()["part"] == 1   # no such part
    short = client.get(f"/api/review/{SHORT}/publish").json()
    assert short["link"] is None and "Shorts have no chapters" in short["note"]


def test_written_text_and_a_card_per_frame(client, library, settings):
    put(settings, PLAN, "video", written(settings))
    found = client.get(f"/api/review/{PLAN}/publish").json()
    assert found["written"] and found["title"] == "Holding the Zone"
    assert found["titles"] == ["Holding the Zone", "Last One Standing"]
    assert found["description"].startswith("We held it.") and found["tags"] == "wardogs"
    cards = found["thumbnails"]
    assert [c["n"] for c in cards] == [0, 1]                 # the deleted frame isn't shown
    assert cards[0]["prompt"] == "Make it pop" and cards[0]["rating"] == 8
    assert cards[0]["url"].startswith("/classic/gradio_api/file=")
    short = client.get(f"/api/review/{SHORT}/publish").json()
    assert short["thumbnails"] == []


def test_keep_my_changes_and_the_link(client, library, settings):
    url = f"/api/review/{PLAN}/publish"
    edit = {"title": " My title ", "description": "Mine.", "tags": "a, b,", "part": None}
    assert client.post(f"{url}/keep", json=edit).status_code == 403
    said = client.post(f"{url}/keep", headers=GUARD, json=edit).json()["said"]
    assert said == "Write the text first, then change it."
    put(settings, PLAN, "video", written(settings))
    said = client.post(f"{url}/keep", headers=GUARD, json=edit).json()["said"]
    assert said.startswith("Kept.")
    found = client.get(url).json()
    assert found["title"] == "My title" and found["tags"] == "a, b"
    said = client.post(f"{url}/link", headers=GUARD,
                       json={"link": "https://youtu.be/abc"}).json()["said"]
    assert said.startswith("Saved. Shorts from this video now link to it.")
    assert client.get(url).json()["link"] == "https://youtu.be/abc"
    # A Let's Play part keeps its own link; a Short has none of its own.
    client.post(f"/api/review/{LP}/publish/link", headers=GUARD,
                json={"part": 2, "link": "https://youtu.be/p2"})
    assert client.get(f"/api/review/{LP}/publish?part=2").json()["link"] == "https://youtu.be/p2"
    assert client.get(f"/api/review/{LP}/publish?part=1").json()["link"] == ""
    assert "not the other way round" in client.post(
        f"/api/review/{SHORT}/publish/link", headers=GUARD, json={"link": "x"}).json()["said"]


def test_write_is_todays_job(client, library, settings):
    url = f"/api/review/{LP}/publish/write"
    settings.llm.enabled = False
    assert "switched off" in client.post(url, headers=GUARD, json={"part": 1}).json()["said"]
    settings.llm.enabled = True
    assert client.post(url, json={"part": 1}).status_code == 403
    said = client.post(url, headers=GUARD, json={"part": 1, "episode": ""}).json()["said"]
    assert said.startswith("Fill in the episode number first")
    one = client.post(url, headers=GUARD, json={"part": 2, "episode": "6"}).json()
    every = client.post(url, headers=GUARD, json={"part": "all", "episode": 6}).json()
    prompts = client.post(url, headers=GUARD,
                          json={"what": "prompts", "part": 2, "episode": 6}).json()
    keys = [t.key for t in client.worker.snapshot()]
    assert keys == [f"publish:{LP}:Part 2", f"publish:{LP}:All parts", f"prompts:{LP}:Part 2"]
    assert one["job"] != every["job"] != prompts["job"]
    again = client.post(url, headers=GUARD, json={"part": 2, "episode": 6}).json()
    assert again["said"] == "That's already being written, in Jobs."
    assert client.get(f"/api/review/publish-job/{one['job']}").json() == {"state": "waiting"}


def test_open_the_frame_from_the_saved_plan_only(client, library, settings, monkeypatch):
    opened = []
    monkeypatch.setattr(review_publish.subprocess, "Popen", lambda args: opened.append(args))
    put(settings, PLAN, "video", written(settings))
    url = f"/api/review/{PLAN}/publish/frame"
    assert client.post(url, json={"n": 0}).status_code == 403
    assert client.post(url, headers=GUARD, json={"n": 1}).json()["said"] == ""
    assert opened[0][:2] == ["explorer", "/select,"] and opened[0][2].endswith("frame 1.png")
    for n in (2, 7, -1):                               # deleted since, or not there at all
        assert "isn't there any more" in client.post(url, headers=GUARD, json={"n": n}).json()["said"]
    assert len(opened) == 1


def test_the_tab_is_drawn_by_the_window():
    script = (Path(review_publish.__file__).with_name("frame") / "review.js").read_text(
        encoding="utf-8")
    assert "publishTab" in script and ".innerHTML" not in script     # text, never markup
    # The creator's choices: frame and prompt on one card, the picture copied to paste.
    assert '"Copy the picture"' in script and "new ClipboardItem" in script
    assert '"Copy the prompt"' in script and '"Open the frame"' in script
    # A Let's Play's Publish follows the part clicked.
    assert "data.rows[selected].part" in script


def test_the_episode_is_kept_and_else_guessed(client, library, settings):
    """1 Nov: #35 was named by date, so both Episode boxes started empty; its videos went
    out as EP 6 and its upload text as EP 1. Now the plan keeps the one typed, and with
    none, the next after the game's last episode is offered as a guess."""
    dated = "letsplay_the-blood-of-dawnwalker_2026-11-02_1"
    conn = init_db(settings.db_path)
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, game, "
                 "duration_sec, imported_at, analysis_status) VALUES (3, 'h3', 'local_obs', "
                 "'2026-11-01 16-10-00.mkv', 'The Blood of Dawnwalker', 7200, "
                 "'2026-11-01T21:00:00+00:00', 'complete')")
    save_plan(conn, EditPlan(dated, "letsplay", "The Blood of Dawnwalker - 2026-11-01",
                             "The Blood of Dawnwalker", 0, [Segment(3, 0, 560, kind="piece", part=1)]))
    conn.execute("UPDATE edit_plans SET created_at = '2026-10-25T18:00:00' WHERE plan_id = ?", (LP,))
    conn.commit()
    conn.close()
    # Named by date: the next after EP 6 (the earlier plan's recording says EP 6).
    found = client.get(f"/api/review/{dated}/publish").json()
    assert (found["episode"], found["episode_after"]) == (7, 6)
    check = client.get(f"/api/review/{dated}/render").json()
    assert (check["episode"], check["episode_after"]) == (7, 6)
    # Typed once (in either box): kept, and both show it, no longer a guess.
    assert client.post(f"/api/review/{dated}/episode", json={"episode": "8"}).status_code == 403
    client.post(f"/api/review/{dated}/episode", headers=GUARD, json={"episode": "8"})
    for url in (f"/api/review/{dated}/publish", f"/api/review/{dated}/render"):
        found = client.get(url).json()
        assert (found["episode"], found["episode_after"]) == (8, None), url
    # Writing or rendering with another keeps that one; nonsense is ignored.
    settings.llm.enabled = True
    client.post(f"/api/review/{dated}/publish/write", headers=GUARD, json={"part": 1, "episode": 9})
    client.post(f"/api/review/{dated}/episode", headers=GUARD, json={"episode": "x"})
    client.post(f"/api/review/{dated}/episode", headers=GUARD, json={"episode": 0})
    assert client.get(f"/api/review/{dated}/render").json()["episode"] == 9
    # A plan named with its episode shows that, and a highlight video has none.
    assert client.get(f"/api/review/{LP}/publish").json()["episode_after"] is None
    assert client.get(f"/api/review/{PLAN}/publish").json()["episode"] is None
