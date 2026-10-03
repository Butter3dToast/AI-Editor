"""Long jobs for the app window: one at a time, in the background.

Importing and analysing take minutes to hours, so the window hands them to
this worker and goes back to showing progress (spec section 9: "job queue with
progress and resume"). One job runs at a time because they all want the same
GPU and drive.

Pausing reuses what Ctrl+C already does in the command line: the job's next
progress report raises an interrupt, the step that was cut short is thrown
away, and FFmpeg or TwitchDownloader is stopped rather than left running.
Resuming runs the same job again, and every finished step is reused.
"""

from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from ..errors import AIEditorError
from ..logging_setup import get_logger

log = get_logger(__name__)

WAITING = "waiting"
RUNNING = "running"
DONE = "done"
PAUSED = "paused"
FAILED = "failed"
UNFINISHED = (WAITING, RUNNING, PAUSED, FAILED)


def paused_note(steps: dict[str, float]) -> str:
    """What a pause costs: the step it was in starts over, the rest are kept.

    A half-made preview copy or half-transcribed recording can't be carried
    on from the middle, only redone, so it shouldn't surprise anyone that
    Resume starts that bar from 0%.
    """
    cut = next((label for label, done in steps.items() if done < 1.0), None)
    if cut is None:
        return "Paused. Resume carries on from here."
    return (f"Paused during '{cut}' at {steps[cut]:.0%}. Resume starts that step again from "
            "the beginning; every finished step is kept.")


class PauseRequested(KeyboardInterrupt):
    """Raised inside a job when the creator presses Pause.

    A KeyboardInterrupt, so the import and analysis code treats it exactly
    like Ctrl+C: marked paused, nothing half-written kept.
    """


class TaskFailed(Exception):
    """A job that can't finish, with a message for the creator."""


@dataclass
class Task:
    id: int
    title: str
    key: str
    run: Callable[["Reporter"], None]
    status: str = WAITING
    steps: dict[str, float] = field(default_factory=dict)  # label -> 0..1, in order
    lines: list[str] = field(default_factory=list)  # what happened, in plain words
    error: str | None = None
    started: float | None = None
    finished: float | None = None
    result: dict = field(default_factory=dict)  # what it made, for the window to show

    def copy(self) -> Task:
        return Task(self.id, self.title, self.key, self.run, self.status, dict(self.steps),
                    list(self.lines), self.error, self.started, self.finished, dict(self.result))


class Reporter:
    """What a running job is handed, to say how it's getting on."""

    def __init__(self, worker: Worker, task: Task) -> None:
        self._worker = worker
        self._task = task

    def progress(self, label: str, fraction: float) -> None:
        self._check()
        with self._worker._lock:
            self._task.steps[label] = max(0.0, min(1.0, fraction))

    def keep(self, **result) -> None:
        """Hand something back to the window: a plan made, a video saved."""
        with self._worker._lock:
            self._task.result.update(result)

    def say(self, text: str) -> None:
        self._check()
        with self._worker._lock:
            self._task.lines.append(text)
            self._worker.version += 1

    def _check(self) -> None:
        if self._worker._pause.is_set():
            raise PauseRequested()


class Worker:
    """Runs submitted jobs one after another on a background thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._pause = threading.Event()
        self._tasks: list[Task] = []
        self._ids = itertools.count(1)
        self._thread: threading.Thread | None = None
        # Goes up whenever a job starts, finishes or says something, so the
        # window knows when the library might have changed.
        self.version = 0

    # --- for the window ---------------------------------------------------

    def submit(self, title: str, key: str, run: Callable[[Reporter], None]) -> Task | None:
        """Queue a job. None if the same thing is already in the list, unfinished."""
        with self._lock:
            if any(t.key == key and t.status in UNFINISHED for t in self._tasks):
                return None
            task = Task(next(self._ids), title, key, run)
            self._tasks.append(task)
            self.version += 1
            self._start()
            self._wake.notify()
            return task

    def pause(self) -> int:
        """Pause the running job and hold the waiting ones. Returns how many."""
        with self._lock:
            held = [t for t in self._tasks if t.status in (WAITING, RUNNING)]
            for task in held:
                if task.status == WAITING:
                    task.status = PAUSED
            if any(t.status == RUNNING for t in held):
                self._pause.set()
            self.version += 1
            return len(held)

    def resume(self) -> int:
        """Send paused and failed jobs back to the queue, in their order."""
        with self._lock:
            again = [t for t in self._tasks if t.status in (PAUSED, FAILED)]
            for task in again:
                task.status, task.error = WAITING, None
            self.version += 1
            self._start()
            self._wake.notify()
            return len(again)

    def clear_finished(self) -> None:
        with self._lock:
            self._tasks = [t for t in self._tasks if t.status != DONE]
            self.version += 1

    def snapshot(self) -> list[Task]:
        with self._lock:
            return [t.copy() for t in self._tasks]

    def busy(self) -> bool:
        with self._lock:
            return any(t.status in (WAITING, RUNNING) for t in self._tasks)

    # --- the background thread ------------------------------------------------

    def _start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, name="ai-editor-jobs", daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        while True:
            with self._lock:
                while (task := next((t for t in self._tasks if t.status == WAITING), None)) is None:
                    self._wake.wait()
                task.status, task.started, task.finished = RUNNING, time.monotonic(), None
                self._pause.clear()
                self.version += 1
            status, error = self._run(task)
            with self._lock:
                task.status, task.error, task.finished = status, error, time.monotonic()
                if status == PAUSED:
                    task.lines.append(paused_note(task.steps))
                self._pause.clear()
                self.version += 1

    def _run(self, task: Task) -> tuple[str, str | None]:
        try:
            task.run(Reporter(self, task))
        except KeyboardInterrupt:  # PauseRequested, or Ctrl+C in the console
            log.info("Job '%s' paused", task.title)
            return PAUSED, None
        except AIEditorError as exc:
            return FAILED, exc.user_message()
        except TaskFailed as exc:
            return FAILED, str(exc)
        except Exception as exc:  # noqa: BLE001 -- the details go to the log file
            log.exception("Job '%s' failed unexpectedly", task.title)
            return FAILED, (f"Something went wrong ({type(exc).__name__}: {exc}). "
                            "The details are in the log file.")
        return DONE, None


def submitted(worker: Worker, task: Task | None) -> str:
    """What to tell the creator after they start a job."""
    if task is None:
        return "That's already in the jobs list."
    waiting = sum(t.status in (WAITING, RUNNING) for t in worker.snapshot()) - 1
    return "Added to Jobs (top of the page)." + (
        f" It starts after the {waiting} ahead of it." if waiting > 0 else "")
