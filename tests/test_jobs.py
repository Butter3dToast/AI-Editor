"""The resumable job queue.

These tests exist because of one promise in manual chapter 11.3: if the PC
restarts during analysis, pressing Resume continues without repeating finished
steps. That is the behaviour being pinned down here.
"""

from __future__ import annotations

import pytest

from ai_editor.db import init_db
from ai_editor.errors import LowDiskSpace
from ai_editor.jobs import COMPLETE, FAILED, PAUSED, QUEUED, JobQueue, make_cache_key


@pytest.fixture
def queue(tmp_path):
    conn = init_db(tmp_path / "library.db")
    yield JobQueue(conn)
    conn.close()


def test_enqueue_and_fetch(queue):
    job_id = queue.enqueue("analyse", {"path": "ep1.mp4"})
    job = queue.get(job_id)
    assert job is not None
    assert job.job_type == "analyse"
    assert job.payload["path"] == "ep1.mp4"
    assert job.status == QUEUED


def test_priority_order(queue):
    queue.enqueue("analyse", priority=100)
    urgent = queue.enqueue("render", priority=10)
    assert queue.next_queued().id == urgent


def test_pause_removes_job_from_the_queue(queue):
    job_id = queue.enqueue("analyse")
    queue.pause(job_id)
    assert queue.get(job_id).status == PAUSED
    assert queue.next_queued() is None
    queue.resume(job_id)
    assert queue.next_queued().id == job_id


def test_steps_run_in_order(queue):
    job_id = queue.enqueue("analyse")
    ran: list[str] = []
    steps = [
        (name, make_cache_key("hash", name), lambda n=name: (ran.append(n), "")[1])
        for name in ("proxy", "audio", "transcribe")
    ]
    queue.run(job_id, steps)

    assert ran == ["proxy", "audio", "transcribe"]
    job = queue.get(job_id)
    assert job.status == COMPLETE
    assert job.progress == 1.0


def test_finished_steps_are_skipped_on_rerun(queue):
    """The heart of resumability: a second run repeats nothing."""
    job_id = queue.enqueue("analyse")
    calls: list[str] = []

    def steps():
        return [
            (name, make_cache_key("hash-abc", name), lambda n=name: (calls.append(n), "")[1])
            for name in ("proxy", "audio")
        ]

    queue.run(job_id, steps())
    assert calls == ["proxy", "audio"]

    queue.run(job_id, steps())
    assert calls == ["proxy", "audio"], "finished steps must not run again"


def test_resume_continues_from_the_failed_step(queue):
    """A crash mid-analysis keeps earlier work and retries only what failed."""
    job_id = queue.enqueue("analyse")
    calls: list[str] = []
    fail_on_audio = True

    def proxy() -> str:
        calls.append("proxy")
        return "F:/cache/proxy.mp4"

    def audio() -> str:
        calls.append("audio")
        if fail_on_audio:
            raise LowDiskSpace("only 2 GB free")
        return "F:/cache/audio.wav"

    def transcribe() -> str:
        calls.append("transcribe")
        return ""

    def steps():
        return [
            ("proxy", make_cache_key("h", "proxy"), proxy),
            ("audio", make_cache_key("h", "audio"), audio),
            ("transcribe", make_cache_key("h", "transcribe"), transcribe),
        ]

    queue.run(job_id, steps())

    job = queue.get(job_id)
    assert job.status == FAILED
    assert job.step == "audio"
    assert calls == ["proxy", "audio"]
    assert "not enough free space" in queue.conn.execute(
        "SELECT error_message FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()[0].lower()

    # Fix the problem and resume: proxy is skipped, audio retried.
    fail_on_audio = False
    queue.resume(job_id)
    assert queue.get(job_id).status == QUEUED

    queue.run(job_id, steps())
    assert calls == ["proxy", "audio", "audio", "transcribe"]
    assert queue.get(job_id).status == COMPLETE


def test_cache_is_shared_between_jobs(queue):
    """Spec section 5: re-importing the same file reuses finished work."""
    calls: list[str] = []
    key = make_cache_key("same-file-hash", "proxy")

    first = queue.enqueue("analyse")
    queue.run(first, [("proxy", key, lambda: (calls.append("x"), "")[1])])

    second = queue.enqueue("analyse")
    queue.run(second, [("proxy", key, lambda: (calls.append("x"), "")[1])])

    assert calls == ["x"], "a second job with the same cache key must reuse the result"


def test_different_inputs_produce_different_cache_keys():
    assert make_cache_key("hash-a", "proxy") != make_cache_key("hash-b", "proxy")
    assert make_cache_key("hash-a", "proxy") != make_cache_key("hash-a", "audio")
    assert make_cache_key("hash-a", "proxy") == make_cache_key("hash-a", "proxy")


def test_unexpected_errors_do_not_escape_as_tracebacks(queue):
    """Spec section 14.2: the creator sees a message, not a stack trace."""
    job_id = queue.enqueue("analyse")

    def explode() -> str:
        raise ValueError("some internal detail")

    queue.run(job_id, [("boom", make_cache_key("h", "boom"), explode)])

    job = queue.get(job_id)
    assert job.status == FAILED
    message = queue.conn.execute(
        "SELECT error_message FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()[0]
    assert "Resume" in message
    assert "ValueError" not in message


def test_progress_advances(queue):
    job_id = queue.enqueue("analyse")
    seen: list[float] = []

    def record() -> str:
        seen.append(queue.get(job_id).progress)
        return ""

    queue.run(
        job_id,
        [(n, make_cache_key("h", n), record) for n in ("a", "b", "c", "d")],
    )
    assert seen == [0.0, 0.25, 0.5, 0.75]
    assert queue.get(job_id).progress == 1.0
