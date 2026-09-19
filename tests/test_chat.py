"""Chat activity attached to a recording."""

from __future__ import annotations

import json

import numpy as np
import pytest

from ai_editor.analysis import chat, pipeline
from ai_editor.db import init_db
from ai_editor.ingest import ingest_recording
from ai_editor.jobs import COMPLETE

from .conftest import make_video, needs_ffmpeg


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    yield connection
    connection.close()


def _chat_file(path, messages):
    path.write_text(json.dumps({"comments": [
        {"content_offset_seconds": t, "commenter": {"display_name": who}, "message": {"body": text}}
        for t, who, text in messages
    ]}), encoding="utf-8")
    return path


def test_rate_counts_messages_in_a_ten_second_window():
    rate = chat.chat_rate([10.2, 11.0, 12.9], seconds=30)
    assert rate[11] == 3
    assert rate[0] == 0 and rate[29] == 0


def test_quiet_chat_scores_zero_everywhere():
    assert np.all(chat.chat_zscore(np.zeros(100, dtype=np.float32)) == 0)


def test_a_burst_stands_out_even_in_a_small_chat():
    rate = np.zeros(300, dtype=np.float32)
    rate[100:110] = 4
    assert chat.chat_zscore(rate)[105] > 3


@needs_ffmpeg
def test_attach_chat(conn, settings, tmp_path):
    video = make_video(tmp_path / "stream.mp4", seconds=30.0)
    rec_id = ingest_recording(conn, settings, video).registration.recording_id
    chat_json = _chat_file(tmp_path / "c.json", [
        (2, "StreamElements", "Butter3dToast is now live!"),
        (12, "viewer1", "LOL"), (13, "viewer2", "no way"), (14, "viewer1", "CLIP IT"),
        (95, "viewer3", "after the recording ended"),
    ])

    result = chat.attach_chat(conn, settings, rec_id, "2875855539", chat_file=chat_json)

    assert result.bot_messages == 1, "StreamElements is not the audience"
    assert result.messages_in_recording == 3
    assert result.chatters == 2
    assert result.busiest[0][0] in range(10, 17)
    stored = [r[0] for r in conn.execute("SELECT username FROM chat_messages ORDER BY t_sec")]
    assert stored == ["viewer1", "viewer2", "viewer1"]
    assert conn.execute("SELECT twitch_vod_id FROM recordings").fetchone()[0] == "2875855539"


@needs_ffmpeg
def test_chat_lines_up_with_a_recording_that_started_late(conn, settings, tmp_path):
    """A local recording that began 8 s into the stream: chat moves 8 s earlier."""
    video = make_video(tmp_path / "local.mp4", seconds=30.0)
    rec_id = ingest_recording(conn, settings, video).registration.recording_id
    chat_json = _chat_file(tmp_path / "c.json", [(5, "a", "before recording"), (20, "b", "hype")])

    chat.attach_chat(conn, settings, rec_id, "2875855539", chat_file=chat_json,
                     recording_starts_at=8.0)
    rows = conn.execute("SELECT t_sec, message FROM chat_messages").fetchall()
    assert [(r[0], r[1]) for r in rows] == [(12.0, "hype")]


@needs_ffmpeg
def test_reattaching_replaces_rather_than_duplicates(conn, settings, tmp_path):
    video = make_video(tmp_path / "s.mp4", seconds=20.0)
    rec_id = ingest_recording(conn, settings, video).registration.recording_id
    chat_json = _chat_file(tmp_path / "c.json", [(3, "a", "hi")])
    chat.attach_chat(conn, settings, rec_id, "2875855539", chat_file=chat_json)
    chat.attach_chat(conn, settings, rec_id, "2875855539", chat_file=chat_json)
    assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 1


@needs_ffmpeg
def test_chat_survives_re_analysis(conn, settings, tmp_path, monkeypatch):
    """Analysis used to wipe every signal it re-saved, chat included."""
    from .test_analysis import FakeModels

    FakeModels(monkeypatch)
    video = make_video(tmp_path / "s.mp4", seconds=20.0)
    rec_id = ingest_recording(conn, settings, video).registration.recording_id
    chat.attach_chat(conn, settings, rec_id, "2875855539",
                     chat_file=_chat_file(tmp_path / "c.json", [(3, "a", "hi")]))

    assert pipeline.analyze_recording(conn, settings, str(rec_id)).status == COMPLETE
    names = {r[0] for r in conn.execute("SELECT DISTINCT name FROM signals")}
    assert {"chat_rate", "chat_z", "speech"} <= names
