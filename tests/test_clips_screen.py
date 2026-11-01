"""Phase 4D: Clips rebuilt in the new design, inside the window.
Today's Clips in the browser is left exactly as it was."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_editor.app import clips_screen
from ai_editor.app.worker import Worker
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
    """One analysed Wardogs stream with three clips, one used in a video, one with an AI note."""
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
    clips = [("a", 3858, 3882, 0.91, {"reasons": ["marker", "gunfire"], "game": "Wardogs"},
              "no way he's still alive", "[]"),
             ("b", 4360, 4379, 0.88, {"reasons": ["laughter"]}, "who called the helicopter",
              json.dumps(["highlights_wardogs_1"])),
             ("c", 2882, 2913, 0.84, {"reasons": ["gunfire"]}, "", "[]")]
    for cid, start, end, score, summary, said, used in clips:
        conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                     "signals_json, transcript, used_in_json, created_at) "
                     "VALUES (?, 1, ?, ?, ?, ?, ?, ?, 'now')",
                     (cid, start, end, score, json.dumps(summary), said, used))
    conn.execute("INSERT INTO ai_clip_notes VALUES ('a', 1, 3858, 3882, 8, 'Clutch 1v3 at the "
                 "extract', 'A real turnaround', '[\"clutch\"]', 0, 'demo', 1, 'now')")
    conn.commit()
    conn.close()


def test_the_list_has_the_designers_columns(client, library):
    found = client.get("/api/clips/1").json()                # Not used yet
    assert [c["id"] for c in found["clips"]] == ["a", "c"]
    first, second = found["clips"]
    assert first["what"] == "Clutch 1v3 at the extract" and first["marked"]      # the AI's line
    assert first["at"] == "1:04:18" and first["length"] == "24 s" and first["score"] == "0.91"
    assert second["what"] == "-"                             # no note, no words
    assert found["line"].startswith("Wardogs · ") and found["line"].endswith(
        " · 3 found · 2 not used yet")
    assert found["video"].startswith("/classic/gradio_api/file=") and "proxy.mp4?v=" in found["video"]
    assert "3 clips" in found["totals"] and "**" not in found["totals"]
    assert [c["id"] for c in client.get("/api/clips/1?show=all").json()["clips"]] == ["a", "b", "c"]
    assert client.get("/api/clips/1?show=rated").json()["clips"] == []
    assert client.get("/api/clips/1?show=nonsense").status_code == 404


def test_the_details_beside_the_player(client, library):
    found = client.get("/api/clips/clip/a").json()
    facts = dict(found["facts"])
    assert facts["At"] == "1:04:18–1:04:42" and facts["Score"] == "0.91"
    assert facts["Why"].startswith("⭐ Marked by you") and facts["Game"] == "Wardogs"
    assert facts["Used"] == "Not yet"
    assert found["ai"]["stars"] == "8/10" and found["said"] == "no way he's still alive"
    assert dict(client.get("/api/clips/clip/b").json()["facts"])["Used"] == "video"
    assert client.get("/api/clips/clip/nope").status_code == 404


def test_a_rating_is_kept_as_todays_clips_keeps_it(client, library, settings):
    assert client.post("/api/clips/clip/a/rate", json={"rating": 1}).status_code == 403
    said = client.post("/api/clips/clip/a/rate", headers=GUARD, json={"rating": 1}).json()["said"]
    assert said.startswith("👍 Saved.") and "next highlight video" in said
    said = client.post("/api/clips/clip/c/rate", headers=GUARD, json={"rating": 2}).json()["said"]
    assert said.startswith("🔖") and "My 🔖 next-video clips" in said
    client.post("/api/clips/clip/c/rate", headers=GUARD, json={"rating": None})
    assert client.post("/api/clips/clip/c/rate", headers=GUARD,
                       json={"rating": 7}).json()["said"] == "That isn't a rating."
    conn = init_db(settings.db_path)
    try:
        ratings = dict(conn.execute("SELECT clip_id, user_rating FROM clips").fetchall())
        kept = [r[0] for r in conn.execute("SELECT action FROM feedback ORDER BY id")]
    finally:
        conn.close()
    assert ratings == {"a": 1, "b": None, "c": None}
    assert kept == ["thumbs_up", "next_video", "rating_cleared"]     # what AI-Editor learns from
    assert [c["rated"] for c in client.get("/api/clips/1?show=rated").json()["clips"]] == ["👍"]


def test_lengths_are_kept_until_something_they_depend_on_changes(library, settings, monkeypatch):
    """Working them out took ~0.6 s a time on the creator's streams: rating lagged."""
    from ai_editor.app import videos

    worked = []

    def lengths(conn, settings, rid):
        worked.append(rid)
        return {"a": 20.0, "b": 15.0, "c": 25.0}

    monkeypatch.setattr(videos, "video_lengths", lengths)
    kept = clips_screen.Lengths()
    conn = init_db(settings.db_path)
    try:
        def look():
            return kept(conn, settings, 1)

        def rate(cid, rating):
            conn.execute("UPDATE clips SET user_rating = ? WHERE clip_id = ?", (rating, cid))
            conn.commit()

        assert look() == {"a": 20.0, "b": 15.0, "c": 25.0} and len(worked) == 1
        look()
        rate("a", 1)
        rate("b", 2)
        look()
        assert len(worked) == 1                            # 👍 and 🔖 change nothing here
        rate("c", -1)
        assert "c" not in look() and len(worked) == 1      # a 👎 is just left out
        rate("c", None)
        assert look()["c"] == 25.0 and len(worked) == 1    # back: its length was kept
        # A clip already 👎 when they were worked out wasn't in them: cleared, they're redone.
        rate("c", -1)
        kept._kept.clear()
        look()
        assert len(worked) == 2
        rate("c", None)
        assert look()["c"] == 25.0 and len(worked) == 3
        conn.execute("UPDATE clips SET used_in_json = '[\"highlights_x\"]' WHERE clip_id = 'a'")
        conn.commit()
        look()
        assert len(worked) == 4                            # used in a video
        settings.highlights.target_length_min += 1
        look()
        assert len(worked) == 5                            # a setting changed
        kept.EVERY_SEC = -1
        look()
        assert len(worked) == 6                            # and now and then regardless
    finally:
        conn.close()


def test_rate_with_ai_is_a_job(client, library, settings, monkeypatch):
    from ai_editor.app import tasks

    monkeypatch.setattr(tasks, "rate_clips", lambda settings, rid: (lambda report: None))
    assert client.post("/api/clips/1/ai").status_code == 403
    assert client.post("/api/clips/1/ai", headers=GUARD).json()["said"] == "Added to Jobs."
    assert client.worker.snapshot()[0].key == "rate:1"
    settings.llm.enabled = False
    assert "switched off" in client.post("/api/clips/2/ai", headers=GUARD).json()["said"]


def test_recordings_to_pick_and_how_well_it_knows_you(client, library):
    found = client.get("/api/clips/recordings").json()["recordings"]
    assert [(r["id"], r["game"], r["gone"]) for r in found] == [(1, "Wardogs", False)]
    assert client.get("/api/clips/knows").json() == {"top": 20, "games": []}


def test_the_frame_draws_clips_itself():
    frame = Path(clips_screen.__file__).with_name("frame")
    page = (frame / "index.html").read_text(encoding="utf-8")
    assert '<script src="/frame/clips.js"></script>' in page
    script = (frame / "clips.js").read_text(encoding="utf-8")
    assert "NATIVE.clips" in script and ".innerHTML" not in script   # text, never markup
    # The creator's choices: pinned stage, keys, on to the next clip after a rating.
    css = (frame / "frame.css").read_text(encoding="utf-8")
    assert ".clip-stage { position: sticky;" in css and "max-height: 46vh" in css
    assert 'const KEYS = { "1": 1, "2": 2, "3": -1, "0": null };' in script
    assert "on to the next clip, and play it" in script
    # The creator's test: the arrows only scrolled the list. Heard first (capture),
    # by any name, and kept from the page.
    assert 'window.addEventListener("keydown", keys, true)' in script
    assert 'Down: "ArrowDown"' in script and "Digit|Numpad" in script
    assert "event.stopPropagation();" in script
    # And no empty part written out as "null" in the details (replaceChildren would).
    assert "replaceChildren(...parts)" in script
