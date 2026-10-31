"""Backups (31 Oct): the library and your Settings, never your OBS password;
a restore that can be undone; never deleted by AI-Editor."""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from datetime import datetime

import pytest
import yaml

from ai_editor import backup
from ai_editor.config import local_settings_path, save_local_settings
from ai_editor.db import init_db

PASSWORD = "obs-secret-123"


@pytest.fixture
def ready(settings, tmp_path):
    folder = tmp_path / "Google Drive" / "AI-Editor backups"
    folder.mkdir(parents=True)
    settings.backup.folder = folder
    conn = init_db(settings.db_path)
    conn.execute("INSERT INTO issues (made_at, source, what) VALUES ('now', 'you', 'first')")
    conn.commit()
    conn.close()
    save_local_settings(settings.source_path, {("obs", "websocket_password"): PASSWORD,
                                               ("highlights", "target_length_min"): 12.0})
    return settings


def issues_in(settings) -> list[str]:
    conn = init_db(settings.db_path)
    try:
        return [r[0] for r in conn.execute("SELECT what FROM issues ORDER BY id")]
    finally:
        conn.close()


def test_a_backup_holds_the_library_and_settings_but_never_the_password(ready):
    path = backup.make(ready, now=datetime(2026, 10, 31, 18, 5))
    assert path.name == "AI-Editor backup 2026-10-31 18-05.zip"
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        library = z.read(backup.DB_NAME)
        saved = z.read(backup.SETTINGS_NAME).decode("utf-8")
        info = json.loads(z.read(backup.INFO_NAME))
    assert names == {"ai-editor.db", "settings.local.yaml", "backup.json", "about.txt"}
    assert PASSWORD not in saved and "websocket_password" not in saved
    assert yaml.safe_load(saved)["highlights"]["target_length_min"] == 12.0
    copy = sqlite3.connect(":memory:")
    copy.deserialize(library)                    # opens on its own, as one file
    assert copy.execute("SELECT what FROM issues").fetchone()[0] == "first"
    assert info["schema"] == copy.execute("PRAGMA user_version").fetchone()[0]


def test_two_in_the_same_minute_never_overwrite(ready):
    when = datetime(2026, 10, 31, 18, 5)
    first, second = backup.make(ready, now=when), backup.make(ready, now=when)
    assert first != second and first.exists() and second.name.endswith("18-05 (2).zip")


def test_restore_puts_it_back_and_can_be_undone(ready):
    made = backup.make(ready, now=datetime(2026, 10, 1, 9, 0))
    conn = init_db(ready.db_path)
    conn.execute("INSERT INTO issues (made_at, source, what) VALUES ('now', 'you', 'later')")
    conn.commit()
    conn.close()
    save_local_settings(ready.source_path, {("highlights", "target_length_min"): 20.0,
                                            ("obs", "websocket_password"): "new-password"})
    before = backup.restore(ready, made)
    assert issues_in(ready) == ["first"]
    local = yaml.safe_load(local_settings_path(ready.source_path).read_text(encoding="utf-8"))
    assert local["highlights"]["target_length_min"] == 12.0          # the backup's
    assert local["obs"]["websocket_password"] == "new-password"       # this PC's, kept
    assert "before restore" in before.name
    backup.restore(ready, before)                                     # and undone
    assert issues_in(ready) == ["first", "later"]


def test_a_backup_from_a_newer_ai_editor_or_damaged_is_refused(ready):
    made = backup.make(ready)
    with zipfile.ZipFile(made) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    info = json.loads(parts[backup.INFO_NAME])
    info["schema"] = 999
    newer = made.with_name("AI-Editor backup 2030-01-01 00-00.zip")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in parts.items():
            z.writestr(name, json.dumps(info) if name == backup.INFO_NAME else data)
    newer.write_bytes(buffer.getvalue())
    with pytest.raises(backup.BackupProblem, match="newer AI-Editor"):
        backup.restore(ready, newer)
    broken = made.with_name("AI-Editor backup 2030-01-02 00-00.zip")
    broken.write_bytes(b"not a zip")
    with pytest.raises(backup.BackupProblem, match="can't be read"):
        backup.restore(ready, broken)
    assert issues_in(ready) == ["first"]                              # nothing changed


def test_listed_newest_first_and_weekly_due(ready):
    assert backup.due(ready)                                          # none yet
    backup.make(ready, now=datetime(2026, 10, 20, 9, 0))
    backup.make(ready, now=datetime(2026, 10, 24, 9, 0), note="before restore")
    found = backup.listed(ready)
    assert [f.made.day for f in found] == [24, 20]
    assert found[0].label().endswith("(before restore)")
    assert not backup.due(ready, now=datetime(2026, 10, 30, 9, 0))
    assert backup.due(ready, now=datetime(2026, 10, 31, 9, 0))
    ready.backup.weekly = False
    assert not backup.due(ready, now=datetime(2026, 12, 1))
    assert "2 backup(s)" in backup.summary(ready) and "never deletes" in backup.summary(ready)


def test_no_folder_no_backup(settings, tmp_path):
    assert "Pick a folder" in backup.summary(settings) and not backup.due(settings)
    settings.backup.folder = tmp_path / "unplugged USB"
    with pytest.raises(backup.BackupProblem, match="no folder"):
        backup.make(settings)


def test_the_job_says_where_it_went(ready):
    from ai_editor.app.backup_panel import job

    lines = []

    class Report:
        def progress(self, *a):
            pass

        def say(self, text):
            lines.append(text)

    job(ready)(Report())
    assert lines[0].startswith("Saved AI-Editor backup ") and "AI-Editor backups" in lines[0]
