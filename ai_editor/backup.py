"""Backups of what isn't on GitHub (31 Oct): the library (ratings, your taste,
plans, rules, style profiles, issues) and your Settings changes.

One zip per backup, in the folder chosen in Settings: a folder inside Google
Drive for desktop puts it on Drive, without AI-Editor going online. Made
while AI-Editor is open, in memory, so no half-written file is ever left and
nothing needs deleting. AI-Editor never deletes a backup.

Private values (the OBS password, any key) are never in a backup. Restoring
keeps the ones on this PC, and first backs up the library as it is, so a
restore can itself be undone.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .config import Settings, local_settings_path
from .db import SCHEMA_VERSION, connect, current_version, init_db
from .logging_setup import get_logger

log = get_logger(__name__)

PREFIX = "AI-Editor backup "
STAMP = "%Y-%m-%d %H-%M"
WEEK = timedelta(days=7)
DB_NAME, SETTINGS_NAME, ABOUT_NAME, INFO_NAME = (
    "ai-editor.db", "settings.local.yaml", "about.txt", "backup.json")
PRIVATE = re.compile(r"(password|passwd|secret|token|api[_-]?key|(^|_)key$)", re.IGNORECASE)
HEADER = "# Private settings for this PC only. Never committed to git (see .gitignore).\n"


class BackupProblem(Exception):
    """A backup or restore that can't be done, said plainly."""


@dataclass(frozen=True)
class Found:
    path: Path
    made: datetime
    size: int

    def label(self) -> str:
        note = self.path.stem[len(PREFIX) + len("2026-10-31 18-05"):].strip()
        return (f"{self.made.strftime('%a %d %b %Y, %H:%M')}  ({self.size / 1e6:.1f} MB)"
                + (f"  {note}" if note else ""))


def folder_problem(settings: Settings) -> str | None:
    folder = settings.backup.folder
    if folder is None:
        return "Pick a folder for backups first (Settings, Backup)."
    if not Path(folder).is_dir():
        return f"There's no folder at {folder}. Is the drive (or Google Drive) connected?"
    return None


def without_private(value: Any) -> Any:
    """The settings with every private value left out entirely."""
    if isinstance(value, dict):
        return {k: without_private(v) for k, v in value.items() if not PRIVATE.search(str(k))}
    if isinstance(value, list):
        return [without_private(v) for v in value]
    return value


def only_private(value: Any) -> Any:
    """Just the private values, where they sit, to put back after a restore."""
    if not isinstance(value, dict):
        return None
    kept = {}
    for k, v in value.items():
        if PRIVATE.search(str(k)):
            kept[k] = v
        elif (inner := only_private(v)):
            kept[k] = inner
    return kept


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _read_local(settings: Settings) -> dict:
    path = local_settings_path(settings.source_path)
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def library_bytes(settings: Settings) -> tuple[bytes, int]:
    """The whole library as it is now, and its layout version. Its header is set
    to the ordinary journal so the copy also opens as a single file."""
    conn = connect(settings.db_path)
    try:
        version = current_version(conn)
        data = bytearray(conn.serialize())
    finally:
        conn.close()
    data[18] = data[19] = 1     # WAL -> rollback journal: a copy is one file
    return bytes(data), version


def make(settings: Settings, *, note: str = "", now: datetime | None = None) -> Path:
    """A backup zip in the chosen folder. ``note``: why, e.g. "before restore"."""
    problem = folder_problem(settings)
    if problem:
        raise BackupProblem(problem)
    now = now or datetime.now()
    data, version = library_bytes(settings)
    info = {"version": __version__, "schema": version,
            "made_at": now.astimezone().isoformat(timespec="seconds"), "note": note}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr(DB_NAME, data)
        z.writestr(SETTINGS_NAME, HEADER + yaml.safe_dump(without_private(_read_local(settings)),
                                                          sort_keys=False, allow_unicode=True))
        z.writestr(INFO_NAME, json.dumps(info, indent=2))
        z.writestr(ABOUT_NAME, (
            f"AI-Editor {__version__} backup, {now.strftime('%d %B %Y, %H:%M')}.\n\n"
            f"{DB_NAME}: your library (ratings, your taste, plans, rules, style profiles, "
            "issues).\n"
            f"{SETTINGS_NAME}: your Settings changes. Your OBS password isn't in it.\n\n"
            "To restore: AI-Editor, Settings, Backup, pick this backup, Restore. Your videos "
            "and recordings aren't in a backup.\n"))
    folder = Path(settings.backup.folder)
    name = PREFIX + now.strftime(STAMP) + (f" ({note})" if note else "")
    target, n = folder / f"{name}.zip", 2
    while target.exists():
        target, n = folder / f"{name} ({n}).zip", n + 1
    target.write_bytes(buffer.getvalue())
    log.info("Backed up the library to %s", target)
    return target


def listed(settings: Settings) -> list[Found]:
    """The backups in the chosen folder, newest first."""
    if folder_problem(settings):
        return []
    found = []
    for path in Path(settings.backup.folder).glob(PREFIX + "*.zip"):
        stamp = path.stem[len(PREFIX):len(PREFIX) + 16]
        try:
            made = datetime.strptime(stamp, STAMP)
        except ValueError:
            continue
        try:
            found.append(Found(path, made, path.stat().st_size))
        except OSError:
            continue
    return sorted(found, key=lambda f: (f.made, f.path.name), reverse=True)


def due(settings: Settings, now: datetime | None = None) -> bool:
    """A week since the last backup, with weekly backups on and a folder chosen."""
    if not settings.backup.weekly or folder_problem(settings):
        return False
    found = listed(settings)
    return not found or (now or datetime.now()) - found[0].made >= WEEK


def summary(settings: Settings) -> str:
    problem = folder_problem(settings)
    if problem:
        return problem
    found = listed(settings)
    if not found:
        return f"No backups in {settings.backup.folder} yet."
    total = sum(f.size for f in found) / 1e6
    return (f"{len(found)} backup(s) in {settings.backup.folder}, {total:.0f} MB in all. "
            f"Newest: {found[0].made.strftime('%a %d %b %Y, %H:%M')}. AI-Editor never deletes "
            "them: delete old ones yourself when you like.")


def restore(settings: Settings, path: Path) -> Path:
    """Put a backup's library and Settings back. Backs up the library as it is
    first (returned), so this can be undone. Private values on this PC are kept."""
    try:
        with zipfile.ZipFile(path) as z:
            data = z.read(DB_NAME)
            saved = yaml.safe_load(z.read(SETTINGS_NAME).decode("utf-8")) or {}
            info = json.loads(z.read(INFO_NAME))
    except (OSError, KeyError, zipfile.BadZipFile, ValueError) as exc:
        raise BackupProblem(f"{path.name} can't be read as an AI-Editor backup ({exc}).") from exc
    if int(info.get("schema", 0)) > SCHEMA_VERSION:
        raise BackupProblem(f"{path.name} was made by a newer AI-Editor ({info.get('version')}). "
                            "Update AI-Editor first.")
    copy = sqlite3.connect(":memory:")
    try:
        copy.deserialize(data)
        if copy.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise BackupProblem(f"The library in {path.name} is damaged. Try an older backup.")
        # The Settings are checked before anything changes.
        local = _merge(without_private(saved), only_private(_read_local(settings)) or {})
        _check_settings(settings, local)
        before = make(settings, note="before restore")
        live = connect(settings.db_path)
        try:
            copy.backup(live)
        finally:
            live.close()
    finally:
        copy.close()
    local_settings_path(settings.source_path).write_text(
        HEADER + yaml.safe_dump(local, sort_keys=False, allow_unicode=True), encoding="utf-8")
    init_db(settings.db_path).close()   # an older backup's layout is brought up to date
    log.warning("Restored the library and Settings from %s (before it: %s)", path, before)
    return before


def _check_settings(settings: Settings, local: dict) -> None:
    from .config import Settings as Model
    from .config import _merge as merge_yaml
    from .config import _read_yaml

    try:
        Model(**merge_yaml(_read_yaml(settings.source_path), local)).check_consistency()
    except Exception as exc:  # noqa: BLE001 -- said plainly, nothing changed
        raise BackupProblem(f"The Settings in that backup can't be used ({exc}). Nothing was "
                            "changed.") from exc
