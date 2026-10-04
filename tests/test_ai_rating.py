"""The local AI: talking to Ollama, rating clips, and keeping its verdicts."""

from __future__ import annotations

import json
import urllib.error

import pytest

from ai_editor import llm
from ai_editor.analysis import ai_rating
from ai_editor.config import Llm
from ai_editor.db import init_db
from ai_editor.errors import AiAnswerUnreadable, AiTooSlow


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                       "game, duration_sec, imported_at, analysis_status) VALUES "
                       "(1, 'h', 'local_obs', 'x.mkv', 'League of Legends', 7200, "
                       "'2026-10-01T20:00:00', 'complete')")
    connection.commit()
    yield connection
    connection.close()


def add_clip(conn, clip_id: str, start: float, end: float, score: float = 0.5,
             rating: int | None = None, signals: dict | None = None) -> None:
    conn.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                 "signals_json, user_rating, created_at) VALUES (?, 1, ?, ?, ?, ?, ?, 'now')",
                 (clip_id, start, end, score, json.dumps(signals or {"reasons": ["laughter"],
                                                                    "peak": start + 20}), rating))
    conn.commit()


def note(clip_id: str, start: float, end: float, rating: float = 7.0) -> ai_rating.Note:
    return ai_rating.Note(clip_id, 1, start, end, rating, "Baron steal", "Big swing.",
                          ["clutch"], True, "gemma4:12b", ai_rating.PROMPT_VERSION)


def clips(conn):
    return conn.execute("SELECT * FROM clips ORDER BY start_sec").fetchall()


# --- how much the rating counts ------------------------------------------------------


def test_the_rating_counts_only_as_much_as_settings_say():
    n = note("a", 0, 30, rating=10)
    assert ai_rating.blended(0.4, n, 0.0) == 0.4  # the default: shown, not used to pick
    assert ai_rating.blended(0.4, n, 0.25) == pytest.approx(0.55)
    assert ai_rating.blended(0.4, note("a", 0, 30, rating=1), 0.5) == pytest.approx(0.2)
    assert ai_rating.blended(0.4, None, 0.25) == 0.4  # not rated yet: unchanged


def test_scores_follow_the_weight_and_the_switch(conn, settings):
    add_clip(conn, "a", 100, 140, score=0.4)
    ai_rating.save(conn, note("a", 100, 140, rating=10))
    settings.llm.rating_weight = 0.25
    assert ai_rating.scores_for(conn, settings, 1, clips(conn))["a"] == pytest.approx(0.55)
    settings.llm.enabled = False
    assert ai_rating.scores_for(conn, settings, 1, clips(conn))["a"] == 0.4


# --- verdicts outlive clips being cut again ----------------------------------------------


def test_a_recut_clip_keeps_the_verdict_on_the_same_moment(conn):
    ai_rating.save(conn, note("old", 100, 160))
    add_clip(conn, "same", 104, 158)    # cut again, a few seconds different
    add_clip(conn, "other", 150, 220)   # mostly a different moment
    found = ai_rating.notes_for(conn, 1, clips(conn))
    assert found["same"].summary == "Baron steal"
    assert "other" not in found


def test_only_clips_without_a_current_verdict_are_asked_about(conn, settings):
    add_clip(conn, "a", 0, 30)
    add_clip(conn, "b", 100, 130)
    add_clip(conn, "c", 200, 230)
    ai_rating.save(conn, note("a", 0, 30))
    stale = note("b", 100, 130)
    stale.prompt_version = ai_rating.PROMPT_VERSION - 1  # the question has changed since
    ai_rating.save(conn, stale)
    assert {c["clip_id"] for c in ai_rating.unrated(conn, settings, 1)} == {"b", "c"}


def test_rating_saves_each_answer_and_carries_on_where_it_stopped(conn, settings, monkeypatch):
    for i in range(3):
        add_clip(conn, f"c{i}", i * 100, i * 100 + 40)
    asked = []

    def fake_ask(settings_, system, prompt, *, schema, images=None, **_):
        asked.append(prompt)
        if len(asked) == 2:
            raise KeyboardInterrupt  # paused mid-way
        return {"summary": "Pentakill", "reason": "Huge.", "tags": ["kill", "kill", "nope"],
                "stands_alone": True, "rating": 12}

    unloaded = []
    monkeypatch.setattr(llm, "start", lambda s: "0.35.1")
    monkeypatch.setattr(llm, "has_model", lambda s, name=None: True)
    monkeypatch.setattr(llm, "unload", lambda s: unloaded.append(True))
    monkeypatch.setattr(llm, "ask", fake_ask)
    with pytest.raises(KeyboardInterrupt):
        ai_rating.rate_recording(conn, settings, 1)
    assert unloaded  # the graphics card is handed back even when paused
    assert conn.execute("SELECT COUNT(*) FROM ai_clip_notes").fetchone()[0] == 1

    result = ai_rating.rate_recording(conn, settings, 1)
    assert (result.rated, result.already) == (2, 1)
    saved = ai_rating.notes_for(conn, 1, clips(conn))["c0"]
    assert saved.rating == 10 and saved.tags == ["kill"] and saved.stands_alone


def test_an_unusable_answer_skips_that_clip_only(conn, settings, monkeypatch):
    add_clip(conn, "a", 0, 30)
    add_clip(conn, "b", 100, 130)
    answers = iter([AiAnswerUnreadable("garbled"),
                    {"summary": "x", "reason": "y", "tags": [], "stands_alone": False,
                     "rating": 3}])

    def fake_ask(*args, **kwargs):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(llm, "start", lambda s: "0.35.1")
    monkeypatch.setattr(llm, "has_model", lambda s, name=None: True)
    monkeypatch.setattr(llm, "unload", lambda s: None)
    monkeypatch.setattr(llm, "ask", fake_ask)
    result = ai_rating.rate_recording(conn, settings, 1)
    assert (result.rated, result.failed) == (1, 1)


def test_rating_stops_when_a_game_has_the_graphics_card(conn, settings, monkeypatch):
    # On 2026-10-04, with Tarkov running, one answer took over 5 minutes, not 2-3 s.
    for i in range(4):
        add_clip(conn, f"c{i}", i * 100, i * 100 + 40)
    clock = iter([0, 1, 4, 10, 190]).__next__  # the second answer took 3 s, the third 180
    monkeypatch.setattr(ai_rating.time, "monotonic", clock)
    monkeypatch.setattr(llm, "start", lambda s: "0.35.1")
    monkeypatch.setattr(llm, "has_model", lambda s, name=None: True)
    monkeypatch.setattr(llm, "unload", lambda s: None)
    monkeypatch.setattr(llm, "ask", lambda *a, **k: {"summary": "x", "reason": "y", "tags": [],
                                                     "stands_alone": False, "rating": 5})
    with pytest.raises(AiTooSlow):
        ai_rating.rate_recording(conn, settings, 1)
    assert conn.execute("SELECT COUNT(*) FROM ai_clip_notes").fetchone()[0] == 3  # kept


def test_an_answer_that_never_comes_is_reported_as_too_slow(settings, monkeypatch):
    def hang(*args, **kwargs):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(llm, "_request", hang)
    with pytest.raises(AiTooSlow):
        llm.ask(settings, "s", "p", schema={})


# --- what the AI is told -------------------------------------------------------------


def test_the_question_has_the_game_what_was_said_and_chat_without_bots(conn, settings):
    add_clip(conn, "a", 100, 160, signals={"reasons": ["laughter"], "peak": 130,
                                           "marker": 1.0})
    conn.executemany("INSERT INTO transcript_words (recording_id, idx, word, start_sec, end_sec) "
                     "VALUES (1, ?, ?, ?, ?)",
                     [(0, "no", 101.0, 101.3), (1, "way", 101.4, 101.7), (2, "baron", 110, 110.5)])
    conn.executemany("INSERT INTO chat_messages (recording_id, t_sec, username, message) "
                     "VALUES (1, ?, ?, ?)",
                     [(120, "viewer1", "LUL"), (121, "Nightbot", "Follow the stream!"),
                      (500, "viewer2", "later")])
    text = ai_rating.question(conn, settings, clips(conn)[0], "League of Legends")
    assert "Baron" in text and "champion select" in text  # the game's notes
    assert "[   1s] no way" in text and "[  10s] baron" in text
    assert "viewer1: LUL" in text and "Nightbot" not in text and "later" not in text
    assert "mark this moment" in text and "laughter" in text


def test_frames_come_from_the_build_up_the_moment_and_just_after():
    times = ai_rating.frame_times(100, 160, 150, 3)
    assert times == [142.0, 148.0, 154.0]
    assert all(100 < t < 160 for t in ai_rating.frame_times(100, 104, 150, 3))
    assert ai_rating.frame_times(100, 160, 150, 0) == []


# --- how often it agrees with the creator ---------------------------------------------


def test_agreement_is_measured_per_game_leaving_marked_clips_out(conn):
    add_clip(conn, "up1", 0, 30, score=0.9, rating=1)
    add_clip(conn, "up2", 100, 130, score=0.3, rating=1)
    add_clip(conn, "down", 200, 230, score=0.5, rating=-1)
    add_clip(conn, "marked", 300, 330, score=1.0, rating=1,
             signals={"reasons": [], "marker": 1.0})
    for clip_id, start, rating in (("up1", 0, 8), ("up2", 100, 6), ("down", 200, 7),
                                   ("marked", 300, 1)):
        ai_rating.save(conn, note(clip_id, start, start + 30, rating=rating))
    (found,) = ai_rating.agreement(conn)
    assert (found.game, found.liked, found.rejected) == ("League of Legends", 2, 1)
    assert found.ai == 0.5 and found.signals == 0.5
    text = ai_rating.agreement_text(conn)
    assert "50%" in text and "Too few to tell yet" in text  # 2 and 1 prove nothing


# --- talking to Ollama ----------------------------------------------------------------


def test_the_ai_must_be_on_this_pc():
    assert Llm(host="http://localhost:11434").host
    with pytest.raises(ValueError):
        Llm(host="http://example.com:11434")


def test_an_answer_that_isnt_json_is_reported_plainly(settings, monkeypatch):
    monkeypatch.setattr(llm, "_request", lambda *a, **k: {"message": {"content": "Sure! 7/10"}})
    with pytest.raises(AiAnswerUnreadable):
        llm.ask(settings, "system", "prompt", schema={})
    sent = {}

    def capture(settings_, path, body=None, timeout=0):
        sent.update(body)
        return {"message": {"content": '{"rating": 7}'}}

    monkeypatch.setattr(llm, "_request", capture)
    assert llm.ask(settings, "s", "p", schema={"type": "object"}, images=[b"jpg"]) == {"rating": 7}
    assert sent["messages"][1]["images"] == ["anBn"] and sent["think"] is False


def test_model_names_match_ollamas_latest_tag(settings, monkeypatch):
    monkeypatch.setattr(llm, "installed_models", lambda s: ["gemma4:latest", "qwen3:8b"])
    assert llm.has_model(settings, "gemma4") and llm.has_model(settings, "qwen3:8b")
    assert not llm.has_model(settings, "gemma4:12b")
