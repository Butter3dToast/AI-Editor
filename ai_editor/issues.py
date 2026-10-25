"""Issues: problems written down, with what's needed to fix them (0.32.0).

The creator describes a problem in the Issues tab ("EP 5 Part 1 loses the
game's sound at 16:39"), and AI-Editor adds the details an engineer would
otherwise dig for: its version, the video's plan, the recording's tracks,
the log lines around it, and the settings. AI-Editor also writes down its own
problems by itself: a job that failed, a render whose sound check had to
make a piece's sound again.

Each issue is a row in the library and a plain text file in the cache's
"issues" folder, so the next session can be told "check the issues". Nothing
is sent anywhere. Private values never go in: the OBS password and anything
named like a password, secret, token or key are taken out of the settings,
and out of the log lines too.
"""

from __future__ import annotations

import json
import platform
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .config import Settings

FOLDER = "issues"
OPEN, FIXED = "open", "fixed"
YOU, AI_EDITOR = "you", "ai-editor"
LOG_TAIL_LINES = 120     # the last lines of the log
LOG_PLAN_LINES = 40      # and the last that name the video's plan
LOG_TAIL_BYTES = 600_000
PRIVATE = re.compile(r"(password|passwd|secret|token|api[_-]?key|(^|_)key$)", re.IGNORECASE)
HIDDEN = "[hidden]"


def folder(settings: Settings) -> Path:
    return settings.folders.cache / FOLDER


def _private_values(value: Any, found: set[str], private: bool = False) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _private_values(v, found, private or bool(PRIVATE.search(str(k))))
    elif isinstance(value, list):
        for v in value:
            _private_values(v, found, private)
    elif private and isinstance(value, str) and value:
        found.add(value)


def scrub(value: Any) -> Any:
    """The settings with every private value replaced by [hidden]."""
    if isinstance(value, dict):
        return {k: (HIDDEN if PRIVATE.search(str(k)) and v not in ("", None, [], {})
                    else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def private_values(settings: Settings) -> set[str]:
    found: set[str] = set()
    _private_values(settings.model_dump(mode="json"), found)
    return found


def hide(text: str, secrets: set[str]) -> str:
    for secret in sorted(secrets, key=len, reverse=True):
        if len(secret) >= 3:
            text = text.replace(secret, HIDDEN)
    return text


def _log_lines(settings: Settings, plan_id: str | None) -> list[str]:
    path = settings.log_dir / "ai-editor.log"
    if not path.is_file():
        return []
    start = max(0, path.stat().st_size - LOG_TAIL_BYTES)
    with path.open("rb") as f:
        f.seek(start)
        lines = f.read().decode("utf-8", errors="replace").splitlines()
    if start:
        lines = lines[1:]   # read from the middle of a line
    # FFmpeg's command lines are long: what matters is which step, and when.
    lines = [line if len(line) < 600 else line[:600] + " ..." for line in lines]
    picked = [line for line in lines if plan_id and plan_id in line][-LOG_PLAN_LINES:]
    tail = lines[-LOG_TAIL_LINES:]
    return [*picked, *([("--- the last lines of the log ---")] if picked else []), *tail]


def _plan(conn: sqlite3.Connection, plan_id: str | None) -> dict | None:
    if not plan_id:
        return None
    row = conn.execute("SELECT * FROM edit_plans WHERE plan_id = ?", (plan_id,)).fetchone()
    if row is None:
        return {"plan_id": plan_id, "note": "not in the library any more"}
    plan = json.loads(row["plan_json"])
    return {"plan_id": plan_id, "title": plan.get("title"), "kind": row["recipe"],
            "status": row["status"], "recordings": json.loads(row["recording_ids_json"]),
            "pieces": len(plan.get("segments", [])),
            "parts": len((plan.get("source") or {}).get("parts") or []) or None,
            "made": row["created_at"], "changed": row["updated_at"]}


def _recording(conn: sqlite3.Connection, recording_id: int | None) -> dict | None:
    if recording_id is None:
        return None
    row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    if row is None:
        return {"recording_id": recording_id, "note": "not in the library any more"}
    tracks = [f"{t['stream_index']}: {t['role']}" for t in conn.execute(
        "SELECT stream_index, role FROM audio_tracks WHERE recording_id = ? ORDER BY "
        "stream_index", (recording_id,))]
    return {"recording_id": recording_id, "file": Path(row["source_file"]).name,
            "still there": Path(row["source_file"]).is_file(), "game": row["game"],
            "length_sec": row["duration_sec"], "analysis": row["analysis_status"],
            "sound tracks": tracks}


def _windows() -> str:
    """"Windows 11 (10.0.26300)": Python calls every Windows from 10 on "10"; 11's
    builds start at 22000."""
    build = platform.version()
    try:
        name = "11" if int(build.split(".")[2]) >= 22000 else platform.release()
    except (IndexError, ValueError):
        name = platform.release()
    return f"{platform.system()} {name} ({build})"


def details(conn: sqlite3.Connection, settings: Settings, *, plan_id: str | None = None,
            recording_id: int | None = None, error: str | None = None) -> dict:
    """Everything worth knowing about a problem, private values taken out."""
    from .ffmpeg import version

    try:
        ffmpeg = version()
    except Exception:   # noqa: BLE001 -- a missing FFmpeg is itself worth seeing here
        ffmpeg = "not found"
    if recording_id is None and plan_id:
        plan_row = conn.execute("SELECT recording_ids_json FROM edit_plans WHERE plan_id = ?",
                                (plan_id,)).fetchone()
        ids = json.loads(plan_row[0]) if plan_row else []
        recording_id = ids[0] if len(ids) == 1 else None
    secrets = private_values(settings)
    return {
        "ai_editor": __version__, "ffmpeg": ffmpeg,
        "windows": _windows(),
        "python": platform.python_version(),
        "error": hide(error, secrets) if error else None,
        "plan": _plan(conn, plan_id), "recording": _recording(conn, recording_id),
        "settings": scrub(settings.model_dump(mode="json")),
        "log": [hide(line, secrets) for line in _log_lines(settings, plan_id)],
    }


@dataclass
class Issue:
    id: int
    made_at: str
    source: str
    what: str
    plan_id: str | None
    recording_id: int | None
    at: str
    status: str
    fixed_in: str
    note: str
    details: dict

    @property
    def number(self) -> str:
        return f"#{self.id}"

    @property
    def video(self) -> str:
        if self.plan_id:
            title = (self.details.get("plan") or {}).get("title")
            return title or self.plan_id
        if self.recording_id is not None:
            return f"recording #{self.recording_id}"
        return ""


def _issue(row: sqlite3.Row) -> Issue:
    return Issue(row["id"], row["made_at"], row["source"], row["what"], row["plan_id"],
                 row["recording_id"], row["at_text"] or "", row["status"], row["fixed_in"] or "",
                 row["note"] or "", json.loads(row["details_json"] or "{}"))


def text(issue: Issue) -> str:
    """The issue as a plain text file: for the creator to read, and for the next session."""
    d = issue.details
    head = [f"Issue {issue.number}: {issue.what}",
            f"Recorded: {issue.made_at} by {'you' if issue.source == YOU else 'AI-Editor itself'}",
            f"Status: {issue.status}" + (f" (in {issue.fixed_in})" if issue.fixed_in else "")]
    if issue.video:
        head.append(f"Video: {issue.video}")
    if issue.at:
        head.append(f"Where: {issue.at}")
    if issue.note:
        head.append(f"Note: {issue.note}")
    body = [f"AI-Editor {d.get('ai_editor')}, {d.get('ffmpeg')}, {d.get('windows')}, "
            f"Python {d.get('python')}"]
    if d.get("error"):
        body += ["", "What AI-Editor said:", d["error"]]
    for key, name in (("plan", "The video's plan"), ("recording", "The recording")):
        if d.get(key):
            body += ["", f"{name}:", json.dumps(d[key], indent=2, ensure_ascii=False)]
    body += ["", "Log lines:", *d.get("log", []),
             "", "Settings (private values hidden):",
             json.dumps(d.get("settings", {}), indent=2, ensure_ascii=False)]
    return "\n".join(head + ["", *body]) + "\n"


def _write(settings: Settings, issue: Issue) -> Path:
    path = folder(settings) / f"issue {issue.id:04d}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text(issue), encoding="utf-8")
    return path


def get(conn: sqlite3.Connection, issue_id: int) -> Issue | None:
    row = conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
    return _issue(row) if row else None


def record(conn: sqlite3.Connection, settings: Settings, what: str, *, source: str = YOU,
           plan_id: str | None = None, recording_id: int | None = None, at: str = "",
           error: str | None = None, status: str = OPEN, note: str = "") -> Issue:
    """Write an issue down, with its details, in the library and as a text file."""
    what = " ".join((what or "").split())
    if not what:
        raise ValueError("Say what's wrong first.")
    found = details(conn, settings, plan_id=plan_id, recording_id=recording_id, error=error)
    cur = conn.execute(
        "INSERT INTO issues (made_at, source, what, plan_id, recording_id, at_text, status, note, "
        "details_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().astimezone().isoformat(timespec="seconds"), source, what, plan_id,
         recording_id, at.strip(), status, note.strip(), json.dumps(found, ensure_ascii=False)))
    conn.commit()
    issue = get(conn, cur.lastrowid)
    _write(settings, issue)
    return issue


def update(conn: sqlite3.Connection, settings: Settings, issue_id: int, *, status: str,
           fixed_in: str = "", note: str = "") -> Issue | None:
    conn.execute("UPDATE issues SET status = ?, fixed_in = ?, note = ? WHERE id = ?",
                 (status, fixed_in.strip(), note.strip(), issue_id))
    conn.commit()
    issue = get(conn, issue_id)
    if issue:
        _write(settings, issue)
    return issue


def listed(conn: sqlite3.Connection, *, open_only: bool = False) -> list[Issue]:
    query = "SELECT * FROM issues" + (" WHERE status = 'open'" if open_only else "") + \
        " ORDER BY id DESC"
    return [_issue(r) for r in conn.execute(query)]


def diagnostic_text(conn: sqlite3.Connection, settings: Settings,
                    issue_id: int | None = None) -> str:
    """Copy diagnostic info: the issue picked, or else how things stand now."""
    issue = get(conn, issue_id) if issue_id is not None else None
    if issue is not None:
        return text(issue)
    now = Issue(0, datetime.now().astimezone().isoformat(timespec="seconds"), YOU,
                "Diagnostic info (no issue picked)", None, None, "", OPEN, "", "",
                details(conn, settings))
    return text(now).replace("Issue #0: ", "", 1)


def from_job(conn: sqlite3.Connection, settings: Settings, title: str, error: str,
             key: str = "") -> Issue:
    """A job that failed, written down by AI-Editor itself."""
    plan_id = key.split(":", 1)[1] if key.startswith("render:") else None
    recording = re.search(r"#(\d+)", title)
    return record(conn, settings, f"The job '{title}' failed", source=AI_EDITOR,
                  plan_id=plan_id or None,
                  recording_id=int(recording.group(1)) if recording and not plan_id else None,
                  error=error)
