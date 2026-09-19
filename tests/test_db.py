"""Clip library schema and migrations."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from ai_editor.db import SCHEMA_VERSION, current_version, init_db, migrate, session

EXPECTED_TABLES = {
    "recordings",
    "audio_tracks",
    "signals",
    "transcript_words",
    "clips",
    "companion_events",
    "chat_messages",
    "layouts",
    "style_profiles",
    "rules",
    "edit_plans",
    "series",
    "series_parts",
    "feedback",
    "jobs",
    "job_steps",
}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@pytest.fixture
def conn(tmp_path):
    connection = init_db(tmp_path / "library.db")
    yield connection
    connection.close()


def _table_names(conn):
    return {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def test_all_tables_created(conn):
    assert EXPECTED_TABLES <= _table_names(conn)


def test_version_recorded(conn):
    assert current_version(conn) == SCHEMA_VERSION


def test_migrate_is_idempotent(conn):
    """Opening an existing library must not re-run migrations."""
    assert migrate(conn) == SCHEMA_VERSION
    assert migrate(conn) == SCHEMA_VERSION
    assert EXPECTED_TABLES <= _table_names(conn)


def test_foreign_keys_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO audio_tracks (recording_id, stream_index) VALUES (?, ?)",
            (999, 0),
        )


def _insert_recording(conn, content_hash="abc123"):
    cursor = conn.execute(
        "INSERT INTO recordings (content_hash, source_type, source_file, game, "
        "duration_sec, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            content_hash,
            "local_obs",
            "F:/AI-Editor/raw/ep1.mp4",
            "The Blood of Dawnwalker",
            7563.5,
            _now(),
        ),
    )
    return cursor.lastrowid


def test_content_hash_is_unique(conn):
    """Importing the same file twice must not create a second recording."""
    _insert_recording(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_recording(conn)


def test_cascade_delete_removes_children(conn):
    """Removing a recording must not leave orphaned signals or clips behind."""
    rec_id = _insert_recording(conn)
    conn.execute(
        "INSERT INTO signals (recording_id, t_sec, name, value) VALUES (?, ?, ?, ?)",
        (rec_id, 10, "rms", 0.5),
    )
    conn.execute(
        "INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("c0001", rec_id, 10.0, 40.0, 0.87, _now()),
    )
    conn.commit()

    conn.execute("DELETE FROM recordings WHERE id = ?", (rec_id,))
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0] == 0


def test_signals_are_one_row_per_second_per_name(conn):
    """Spec section 7.3 stores signals per second; the key must prevent duplicates."""
    rec_id = _insert_recording(conn)
    conn.execute(
        "INSERT INTO signals (recording_id, t_sec, name, value) VALUES (?, ?, ?, ?)",
        (rec_id, 42, "laughter", 0.7),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO signals (recording_id, t_sec, name, value) VALUES (?, ?, ?, ?)",
            (rec_id, 42, "laughter", 0.9),
        )
    # A different signal at the same second is fine.
    conn.execute(
        "INSERT INTO signals (recording_id, t_sec, name, value) VALUES (?, ?, ?, ?)",
        (rec_id, 42, "gunfire", 0.9),
    )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 2


def test_clip_record_round_trips(conn):
    """The clip shape from spec section 7.3 must store and read back intact."""
    rec_id = _insert_recording(conn)
    signals = {"audio_peak": 2.9, "laughter": 0.74, "marker": True}
    conn.execute(
        "INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
        "signals_json, llm_tags_json, llm_summary, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "twitch_2291847711_c0042",
            rec_id,
            5321.4,
            5358.9,
            0.87,
            json.dumps(signals),
            json.dumps(["clutch", "funny"]),
            "Wins a 1v3 at extract with almost no health.",
            _now(),
        ),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM clips WHERE clip_id = ?", ("twitch_2291847711_c0042",)
    ).fetchone()
    assert row["score"] == 0.87
    assert json.loads(row["signals_json"])["marker"] is True
    assert json.loads(row["llm_tags_json"]) == ["clutch", "funny"]
    assert row["user_rating"] is None
    assert row["pinned"] == 0


def test_series_part_numbers_are_unique(conn):
    """Part numbering continues across sessions and must not collide."""
    series_id = conn.execute(
        "INSERT INTO series (name, game, created_at) VALUES (?, ?, ?)",
        ("Dawnwalker Playthrough", "The Blood of Dawnwalker", _now()),
    ).lastrowid
    conn.execute(
        "INSERT INTO series_parts (series_id, part_number) VALUES (?, ?)", (series_id, 1)
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO series_parts (series_id, part_number) VALUES (?, ?)",
            (series_id, 1),
        )


def test_session_rolls_back_on_error(tmp_path):
    db_path = tmp_path / "library.db"
    with pytest.raises(RuntimeError):
        with session(db_path) as conn:
            conn.execute(
                "INSERT INTO layouts (name, created_at) VALUES (?, ?)",
                ("Tarkov layout", _now()),
            )
            raise RuntimeError("boom")

    with session(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM layouts").fetchone()[0] == 0
