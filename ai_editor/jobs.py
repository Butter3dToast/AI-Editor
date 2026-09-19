"""The resumable job queue.

Spec section 3: "Long jobs must be resumable and safe to run overnight in a
batch queue." Manual chapter 11.3 promises the creator that if the PC restarts
mid-analysis, pressing Resume continues without repeating finished steps.

Both promises come from the same idea: a job is a named list of steps, each
step records a cache key when it finishes, and a step whose cache key already
exists is skipped. The cache key combines the recording's content hash with the
step's own inputs, so re-importing the same file reuses last time's work
(spec section 5).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .errors import AIEditorError, JobFailed
from .logging_setup import get_logger

log = get_logger(__name__)

QUEUED = "queued"
RUNNING = "running"
PAUSED = "paused"
COMPLETE = "complete"
FAILED = "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_cache_key(*parts: object) -> str:
    """Stable key from a step's inputs. Order matters; values are stringified."""
    digest = hashlib.blake2b(digest_size=16)
    for part in parts:
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


@dataclass
class Job:
    id: int
    job_type: str
    payload: dict[str, Any]
    recording_id: int | None
    status: str
    progress: float
    step: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Job:
        return cls(
            id=row["id"],
            job_type=row["job_type"],
            payload=json.loads(row["payload_json"] or "{}"),
            recording_id=row["recording_id"],
            status=row["status"],
            progress=row["progress"],
            step=row["step"],
        )


class JobQueue:
    """Queue operations. Holds a connection; does not own it."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # --- queue management --------------------------------------------------

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any] | None = None,
        recording_id: int | None = None,
        priority: int = 100,
    ) -> int:
        cursor = self.conn.execute(
            "INSERT INTO jobs (job_type, payload_json, recording_id, priority, "
            "status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                job_type,
                json.dumps(payload or {}),
                recording_id,
                priority,
                QUEUED,
                _now(),
            ),
        )
        self.conn.commit()
        job_id = int(cursor.lastrowid or 0)
        log.info("Queued %s job #%d", job_type, job_id)
        return job_id

    def get(self, job_id: int) -> Job | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return Job.from_row(row) if row else None

    def next_queued(self) -> Job | None:
        """Highest-priority waiting job. Paused jobs are not picked up."""
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY priority ASC, id ASC LIMIT 1",
            (QUEUED,),
        ).fetchone()
        return Job.from_row(row) if row else None

    def list_jobs(self, status: str | None = None) -> list[Job]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY priority, id", (status,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM jobs ORDER BY priority, id"
            ).fetchall()
        return [Job.from_row(r) for r in rows]

    def find_open(self, job_type: str, recording_id: int) -> Job | None:
        """The unfinished job of this type for a recording, if there is one.

        Re-running an import should resume the job that was interrupted, not
        start a second one alongside it.
        """
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE job_type = ? AND recording_id = ? "
            "AND status IN (?, ?, ?) ORDER BY id DESC LIMIT 1",
            (job_type, recording_id, QUEUED, PAUSED, FAILED),
        ).fetchone()
        return Job.from_row(row) if row else None

    def recover_interrupted(self) -> int:
        """Mark jobs left 'running' by a crash or restart as paused.

        Nothing can genuinely be running when the app starts, because the app
        is the only thing that runs jobs. This must change if a separate
        background worker is ever added (Phase 3 batch processing), or it would
        pause that worker's live job.
        """
        cursor = self.conn.execute(
            "UPDATE jobs SET status = ? WHERE status = ?", (PAUSED, RUNNING)
        )
        self.conn.commit()
        if cursor.rowcount:
            log.info("Recovered %d interrupted job(s) as paused", cursor.rowcount)
        return cursor.rowcount

    def pause(self, job_id: int) -> None:
        self.conn.execute(
            "UPDATE jobs SET status = ? WHERE id = ? AND status IN (?, ?)",
            (PAUSED, job_id, QUEUED, RUNNING),
        )
        self.conn.commit()

    def resume(self, job_id: int) -> None:
        """Send a paused or failed job back to the queue.

        Finished steps keep their rows, so the run skips straight past them.
        """
        self.conn.execute(
            "UPDATE jobs SET status = ?, error_code = NULL, error_message = NULL "
            "WHERE id = ? AND status IN (?, ?)",
            (QUEUED, job_id, PAUSED, FAILED),
        )
        self.conn.commit()

    def set_progress(self, job_id: int, progress: float, step: str | None = None) -> None:
        self.conn.execute(
            "UPDATE jobs SET progress = ?, step = COALESCE(?, step) WHERE id = ?",
            (max(0.0, min(1.0, progress)), step, job_id),
        )
        self.conn.commit()

    # --- step tracking -----------------------------------------------------

    def step_is_done(self, job_id: int, step_name: str, cache_key: str) -> str | None:
        """Return the finished step's output path, or None if it must run.

        A step counts as done when *some* job finished it with this exact cache
        key -- not only this job. That is what lets a re-import of the same
        recording reuse the previous analysis.

        A step whose output file has since been deleted (cache cleanup, or by
        hand) is not done: trusting the record over the disk would hand later
        steps a path to nothing.
        """
        row = self.conn.execute(
            "SELECT output_path FROM job_steps WHERE cache_key = ? AND status = ? "
            "ORDER BY id DESC LIMIT 1",
            (cache_key, COMPLETE),
        ).fetchone()
        if row is None:
            return None
        # "" is a legitimate output for steps that write to the database only.
        output = row["output_path"] or ""
        if output and not Path(output).exists():
            log.info("Job #%d: cached output for '%s' is gone; redoing it", job_id, step_name)
            return None
        return output

    def start_step(self, job_id: int, step_name: str, cache_key: str) -> None:
        self.conn.execute(
            "INSERT INTO job_steps (job_id, step_name, status, cache_key, started_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(job_id, step_name) DO UPDATE SET "
            "status = excluded.status, cache_key = excluded.cache_key, "
            "started_at = excluded.started_at, finished_at = NULL",
            (job_id, step_name, RUNNING, cache_key, _now()),
        )
        self.conn.commit()

    def finish_step(self, job_id: int, step_name: str, output_path: str = "") -> None:
        self.conn.execute(
            "UPDATE job_steps SET status = ?, output_path = ?, finished_at = ? "
            "WHERE job_id = ? AND step_name = ?",
            (COMPLETE, output_path, _now(), job_id, step_name),
        )
        self.conn.commit()

    # --- running -----------------------------------------------------------

    def run(
        self,
        job_id: int,
        steps: list[tuple[str, str, Callable[[], str]]],
    ) -> None:
        """Run a job's steps in order, skipping any already finished.

        ``steps`` is a list of (step_name, cache_key, callable). The callable
        returns an output path, or "" when its result went to the database.

        A failure records the step and stops; the job can be resumed and picks
        up from that step. Errors are never re-raised as tracebacks to the UI.
        """
        self.conn.execute(
            "UPDATE jobs SET status = ?, started_at = COALESCE(started_at, ?) WHERE id = ?",
            (RUNNING, _now(), job_id),
        )
        self.conn.commit()

        total = len(steps) or 1
        try:
            for position, (name, cache_key, action) in enumerate(steps):
                cached = self.step_is_done(job_id, name, cache_key)
                if cached is not None:
                    log.info("Job #%d: step '%s' already done, skipping", job_id, name)
                    self.set_progress(job_id, (position + 1) / total, name)
                    continue

                log.info("Job #%d: running step '%s'", job_id, name)
                self.set_progress(job_id, position / total, name)
                self.start_step(job_id, name, cache_key)
                output = action()
                self.finish_step(job_id, name, output or "")
                self.set_progress(job_id, (position + 1) / total, name)

        except KeyboardInterrupt:
            # Ctrl+C or closing the window is a pause, not a failure: the step
            # that was cut short simply runs again on resume.
            self.conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (PAUSED, job_id))
            self.conn.commit()
            log.warning("Job #%d paused by the user", job_id)
            raise
        except AIEditorError as exc:
            self._fail(job_id, exc.code, exc.user_message())
            return
        except Exception as exc:  # noqa: BLE001 - the traceback goes to the log file
            log.exception("Job #%d failed unexpectedly", job_id)
            wrapped = JobFailed(str(exc))
            self._fail(job_id, wrapped.code, wrapped.user_message())
            return

        self.conn.execute(
            "UPDATE jobs SET status = ?, progress = 1.0, finished_at = ? WHERE id = ?",
            (COMPLETE, _now(), job_id),
        )
        self.conn.commit()
        log.info("Job #%d complete", job_id)

    def _fail(self, job_id: int, code: str, message: str) -> None:
        self.conn.execute(
            "UPDATE jobs SET status = ?, error_code = ?, error_message = ?, "
            "finished_at = ? WHERE id = ?",
            (FAILED, code, message, _now(), job_id),
        )
        self.conn.commit()
        log.error("Job #%d failed: %s", job_id, message)

    def drain(self) -> Iterator[Job]:
        """Yield queued jobs one at a time, highest priority first."""
        while (job := self.next_queued()) is not None:
            yield job
