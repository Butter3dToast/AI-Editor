"""About how long a job has left (4B): learned from this PC's own past jobs.

Every finished job's steps are timed (worker.py) and kept (step_times), with
how much it worked on: the recording's length for an import or analysis, the
video's for a render. A step that took 6 minutes on a 3-hour stream is about
2 minutes per hour of recording, so a new 2-hour stream's is about 4. The
guess for a running job adds up its unfinished steps that way.

Imports and analyses before 4B were timed too (job_steps), so those have a
guess from the start. A step that has never run on this PC has no history:
then there's no guess at all, rather than a wrong one (the creator's choice,
31 Oct: "B", not a guess from the bar alone).
"""

from __future__ import annotations

import re
import sqlite3
import statistics
import uuid
from datetime import datetime

from .worker import Task

RUNS_KEPT = 10                 # the latest runs of each kind count
MIN_SIZE_SEC = 60.0            # shorter than this, a step's time isn't per minute of anything
PART = re.compile(r"^Part \d+ of \d+$")


def kind_of(key: str) -> str:
    return key.split(":", 1)[0]


def _labels() -> tuple[dict[str, str], dict[str, str]]:
    from ..cli import ANALYSIS_LABELS, STEP_LABELS

    return STEP_LABELS, ANALYSIS_LABELS


def keep(conn: sqlite3.Connection, task: Task, size_sec: float | None) -> None:
    """A finished job's step times, for next time."""
    if not task.timings:
        return
    run = uuid.uuid4().hex
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    conn.executemany(
        "INSERT INTO step_times (kind, run, position, step, seconds, size_sec, made_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(kind_of(task.key), run, n, label, round(seconds, 2), size_sec, now)
         for n, (label, seconds) in enumerate(task.timings)])
    conn.commit()


def keep_finished(settings, task: Task) -> None:
    """worker.on_done: keep a finished job's step times (the window and the
    browser alike, so the guesses learn from every job)."""
    from ..db import init_db

    conn = init_db(settings.db_path)
    try:
        keep(conn, task, size_of(conn, task))
    finally:
        conn.close()


def _from_steps(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Imports and analyses timed before 4B, from the resumable jobs' own record."""
    ingest, analysis = _labels()
    runs: dict[str, list[dict]] = {}
    rows = conn.execute(
        "SELECT j.id, j.job_type, s.step_name, s.started_at, s.finished_at, r.duration_sec "
        "FROM job_steps s JOIN jobs j ON j.id = s.job_id "
        "LEFT JOIN recordings r ON r.id = j.recording_id "
        "WHERE s.started_at IS NOT NULL AND s.finished_at IS NOT NULL AND j.status = 'complete' "
        "ORDER BY j.id DESC, s.id").fetchall()
    by_job: dict[int, dict] = {}
    for job_id, job_type, name, started, finished, duration in rows:
        names = ingest if job_type == "ingest" else analysis if job_type == "analyze" else None
        if names is None or name not in names:
            continue
        try:
            seconds = (datetime.fromisoformat(finished) - datetime.fromisoformat(started)) \
                .total_seconds()
        except ValueError:
            continue
        run = by_job.setdefault(job_id, {"kind": "import" if job_type == "ingest" else "analyse",
                                         "steps": [], "size": duration})
        run["steps"].append((names[name], max(0.0, seconds)))
    for run in by_job.values():
        runs.setdefault(run["kind"], []).append(run)
    return runs


def history(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """{kind: its latest runs, newest first}: each {"steps": [(label, seconds)], "size"}."""
    runs: dict[str, list[dict]] = {}
    rows = conn.execute("SELECT kind, run, step, seconds, size_sec FROM step_times "
                        "ORDER BY id DESC").fetchall()
    order: dict[str, dict] = {}
    for kind, run, step, seconds, size in rows:
        if run not in order:
            order[run] = {"kind": kind, "steps": [], "size": size}
            runs.setdefault(kind, []).append(order[run])
        order[run]["steps"].insert(0, (step, seconds))
    for kind, old in _from_steps(conn).items():
        runs.setdefault(kind, []).extend(old)
    return {kind: found[:RUNS_KEPT] for kind, found in runs.items()}


def _rate(runs: list[dict], label: str) -> float | None:
    """Seconds per second of recording or video for this step; None if never run."""
    found = [seconds / run["size"] for run in runs if run["size"] and run["size"] >= MIN_SIZE_SEC
             for step, seconds in run["steps"] if step == label]
    return statistics.median(found) if found else None


def left(task: Task, past: dict[str, list[dict]], size: float | None) -> float | None:
    """Seconds left for a running job, or None when there's no fair guess."""
    if not size or size < MIN_SIZE_SEC:
        return None
    kind = kind_of(task.key)
    if kind == "render":
        return _render_left(task, past.get("render", []), size)
    groups = [past.get(kind, [])]
    if kind in ("import", "twitch") and "analys" in task.title.lower():
        groups.append(past.get("analyse", []))     # importing, then analysing
    runs = [run for group in groups for run in group]
    if not runs:
        return None
    expected: list[str] = []
    for group in groups:
        # The steps most jobs of this kind have: separating voices, say, only
        # runs for Twitch VODs, so it isn't expected of an OBS recording.
        counts: dict[str, int] = {}
        for run in group:
            for label in dict.fromkeys(label for label, _ in run["steps"]):
                counts[label] = counts.get(label, 0) + 1
        expected += [label for label, n in counts.items()
                     if n * 2 >= len(group) and label not in expected]
    for label in task.steps:              # and any it has now
        if label not in expected:
            expected.append(label)
    total = 0.0
    for label in expected:
        done = task.steps.get(label, 0.0)
        if done >= 1.0:
            continue
        rate = _rate(runs, label)
        if rate is None:
            if label in task.steps:       # running, never timed: no fair guess
                return None
            continue                      # a step only some jobs have (voices apart)
        total += rate * size * (1.0 - done)
    return total


def _render_left(task: Task, runs: list[dict], size: float) -> float | None:
    """A render's steps are its parts: the whole render's pace, per second of video."""
    rates = [sum(s for _, s in run["steps"]) / run["size"] for run in runs
             if run["size"] and run["size"] >= MIN_SIZE_SEC]
    if not rates or not task.steps:
        return None
    parts = task.result.get("parts") or len(task.steps)
    done = sum(task.steps.values()) / max(1, parts)
    return statistics.median(rates) * size * max(0.0, 1.0 - done)


def size_of(conn: sqlite3.Connection, task: Task) -> float | None:
    """How much the job works on: a recording's length, or a video's."""
    if task.result.get("size_sec"):
        return float(task.result["size_sec"])
    recording = task.result.get("recording_id")
    if recording is None and kind_of(task.key) == "analyse":
        recording = task.key.split(":", 1)[1]
    if recording is None:
        return None
    row = conn.execute("SELECT duration_sec FROM recordings WHERE id = ?",
                       (int(recording),)).fetchone()
    return float(row[0]) if row and row[0] else None


def words(seconds: float | None) -> str:
    if seconds is None:
        return ""
    if seconds < 60:
        return "under a minute left"
    return f"about {round(seconds / 60)} min left"
