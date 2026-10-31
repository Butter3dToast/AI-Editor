"""Overnight work (Phase 3B): while you sleep, AI-Editor imports your new
recordings, analyses them and drafts their plans, for you to review in the
morning. It never renders and never deletes anything.

It runs inside the app, as one job in the Jobs list, at the start time set in
Settings (AI-Editor must be open then; the PC stays on). Each recording is
drafted once: a highlight plan and Shorts for a stream, the parts for a Let's
Play episode.

It gives way to you, using only what the anti-cheat rule allows (spec section
6): OBS, asked over its WebSocket whether it's recording or streaming, about
every 30 seconds, even in the middle of a step; and the graphics card's load
from NVIDIA's own nvidia-smi, a number with no program names, read before each
step while AI-Editor itself is idle. It never looks at which programs are
running. Giving way works like Pause: the step it was in starts over later,
finished steps are kept.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from ..config import Settings
from ..db import init_db
from ..errors import AIEditorError
from ..logging_setup import get_logger
from . import library, tasks
from .worker import PauseRequested, Reporter, TaskFailed, Worker

log = get_logger(__name__)

KEY = "overnight"               # its key in the Jobs list: one at a time
START_WINDOW_MIN = 60           # opened within this long after the start time, it still starts
OBS_EVERY_SEC = 30              # how often OBS is asked, during a step
WAIT_EVERY_SEC = 60             # while waiting, how often it looks again
GPU_SAMPLES, GPU_SAMPLE_SEC = 6, 10   # the card's load, read over about a minute

# Statuses of a night.
WAITING, WORKING, DONE, STOPPED, PAUSED, CLOSED, FAILED = (
    "waiting", "working", "done", "stopped", "paused", "closed", "failed")


class GiveWay(KeyboardInterrupt):
    """OBS started recording or streaming in the middle of a step. A
    KeyboardInterrupt, so the step stops exactly as Pause stops it."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class StopTime(KeyboardInterrupt):
    """The 'stop by' time came: done for tonight."""


# --- when -----------------------------------------------------------------------------


def _at(day: date, clock: str) -> datetime:
    hh, mm = clock.split(":")
    return datetime.combine(day, datetime.min.time()).replace(hour=int(hh), minute=int(mm))


def start_due(settings: Settings, now: datetime) -> datetime | None:
    """The start time that's due now, if any: within an hour after it, so a
    start isn't missed by a minute (and works across midnight)."""
    for day in (now.date(), now.date() - timedelta(days=1)):
        start = _at(day, settings.overnight.start)
        if start <= now < start + timedelta(minutes=START_WINDOW_MIN):
            return start
    return None


def stop_at(settings: Settings, began: datetime) -> datetime | None:
    """The first 'stop by' time after it began. None: until it's done."""
    if not settings.overnight.stop_by:
        return None
    stop = _at(began.date(), settings.overnight.stop_by)
    return stop if stop > began else stop + timedelta(days=1)


def due(conn: sqlite3.Connection, settings: Settings, now: datetime) -> datetime | None:
    """Tonight's start, if overnight work is on, it's time, and it hasn't run yet."""
    if not settings.overnight.enabled:
        return None
    start = start_due(settings, now)
    if start is None or conn.execute("SELECT 1 FROM overnight_nights WHERE night = ?",
                                     (start.date().isoformat(),)).fetchone():
        return None
    return start


# --- giving way -----------------------------------------------------------------------


class Obs:
    """Asks OBS whether it's recording or streaming, over the same WebSocket the
    Stream Companion uses (OBS takes several at once). OBS closed: not busy."""

    def __init__(self, settings: Settings, factory: Callable | None = None) -> None:
        self.settings = settings
        self._factory = factory
        self._client = None
        self.problem: str | None = None   # said once: why OBS can't be asked

    def _connect(self):
        from ..companion.obs import ObsClient

        o = self.settings.obs
        client = (self._factory() if self._factory else
                  ObsClient(o.websocket_host, o.websocket_port, o.websocket_password))
        client.connect()
        return client

    def busy(self) -> str | None:
        from ..companion.obs import ObsRequestFailed
        from ..errors import ObsNotReachable

        try:
            if self._client is None:
                self._client = self._connect()
            if self._client.output_status("record").active:
                return "OBS is recording"
            if self._client.output_status("stream").active:
                return "OBS is streaming"
            return None
        except ObsNotReachable:          # closed: nothing is being recorded
            self.close()
            return None
        except (AIEditorError, ObsRequestFailed) as exc:   # e.g. the password
            self.close()
            if self.problem is None:
                self.problem = (f"Couldn't ask OBS whether it's recording ({exc}), so only the "
                                "graphics card is watched.")
            return None

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001 -- closing a dead connection
                pass
        self._client = None


def gpu_load() -> float | None:
    """How busy the graphics card is right now (%), from nvidia-smi. Only the
    number: no program names. None without an NVIDIA card."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        result = subprocess.run([smi, "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                                capture_output=True, text=True, timeout=20,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return float(result.stdout.strip().splitlines()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


class Watch:
    """Handed to each step in place of the job's reporter: its progress reports
    pass through here, and between them OBS is asked (every 30 s) and the stop
    time checked. Also does the waiting, before each step."""

    def __init__(self, settings: Settings, report: Reporter, *, stop: datetime | None,
                 obs: Obs, gpu: Callable[[], float | None] = gpu_load,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = datetime.now) -> None:
        self.settings, self.report, self.stop = settings, report, stop
        self.obs, self.gpu, self.sleep, self.clock, self.now = obs, gpu, sleep, clock, now
        self._asked = clock()
        self.waited: dict[str, float] = {}   # reason -> seconds waited

    # The Reporter's three calls, so a step can't tell the difference.
    def progress(self, label: str, fraction: float) -> None:
        self._check()
        self.report.progress(label, fraction)

    def say(self, text: str) -> None:
        self.report.say(text)

    def keep(self, **result) -> None:
        self.report.keep(**result)

    def _check(self) -> None:
        if self.stop is not None and self.now() >= self.stop:
            raise StopTime()
        if self.clock() - self._asked >= OBS_EVERY_SEC:
            self._asked = self.clock()
            reason = self.obs.busy()
            if reason:
                raise GiveWay(reason)

    def card_busy(self) -> str | None:
        """The card's load over about a minute, AI-Editor itself idle."""
        readings = []
        for n in range(GPU_SAMPLES):
            if n:
                self._pause(GPU_SAMPLE_SEC, "Checking the graphics card is free")
            load = self.gpu()
            if load is None:
                return None
            readings.append(load)
        average = sum(readings) / len(readings)
        if average >= self.settings.overnight.gpu_busy_percent:
            return f"the graphics card is busy ({average:.0f}%)"
        return None

    def wait_until_free(self) -> None:
        """Before each step: wait while OBS records or streams, or the card is
        busy. The stop time ends the night; Pause in Jobs still works."""
        said = None
        while True:
            if self.stop is not None and self.now() >= self.stop:
                raise StopTime()
            reason = self.obs.busy() or self.card_busy()
            self._asked = self.clock()
            if reason is None:
                return
            if reason != said:
                self.report.say(f"Waiting: {reason}. Looking again every minute.")
                said = reason
            key = "OBS" if reason.startswith("OBS") else "the graphics card"
            self.waited[key] = self.waited.get(key, 0.0) + WAIT_EVERY_SEC
            self._pause(WAIT_EVERY_SEC, f"Waiting: {reason}")

    def _pause(self, seconds: float, label: str) -> None:
        """Sleep in small steps, so Pause in Jobs gets through at once."""
        left = seconds
        while left > 0:
            self.report.progress(label, 0.0)   # raises PauseRequested on Pause
            step = min(5.0, left)
            self.sleep(step)
            left -= step


# --- what's left to do ------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    kind: str           # import | finish | draft
    key: str            # what it is, so a problem isn't tried twice in a night
    label: str
    path: Path | None = None
    recording_id: int | None = None


def _rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT r.*, (SELECT COUNT(*) FROM audio_tracks a WHERE a.recording_id = r.id) AS tracks, "
        "(SELECT COUNT(*) FROM audio_tracks a WHERE a.recording_id = r.id AND a.extracted_path "
        "IS NOT NULL) AS tracks_ready FROM recordings r ORDER BY r.id").fetchall()


def name_of(row) -> str:
    return f"#{row['id']} {row['title'] or Path(row['source_file']).stem}"


def planned(conn: sqlite3.Connection) -> set[int]:
    """Recordings already in a plan of yours, or drafted overnight before."""
    found = {r[0] for r in conn.execute("SELECT recording_id FROM overnight_drafts")}
    for row in conn.execute("SELECT recording_ids_json FROM edit_plans"):
        found.update(json.loads(row[0] or "[]"))
    return found


def todo(conn: sqlite3.Connection, settings: Settings, skip: set[str] = frozenset()) -> list[Item]:
    """Everything still to do tonight, in order: new recordings, then unfinished
    imports and analyses, then drafts. A recording whose video is gone is left."""
    items = [Item("import", f"import:{str(f.path).lower()}", f.path.name, path=f.path)
             for f in reversed(library.new_recordings(conn, settings))   # oldest first
             if not f.still_recording]
    drafts = []
    done = planned(conn)
    for row in _rows(conn):
        status = library.status_of(row)
        if status == library.VIDEO_GONE:
            continue
        if status == "Import unfinished" or row["analysis_status"] != "complete":
            items.append(Item("finish", f"finish:{row['id']}", name_of(row),
                              path=Path(row["source_file"]), recording_id=row["id"]))
        elif row["id"] not in done:
            drafts.append(Item("draft", f"draft:{row['id']}", name_of(row),
                               recording_id=row["id"]))
    return [i for i in items + drafts if i.key not in skip]


def is_lets_play(settings: Settings, game: str | None) -> bool:
    return bool(game) and game.lower() in {g.lower() for g in settings.lets_play.games}


# --- doing it ---------------------------------------------------------------------------


DOING = {"import": "Importing", "finish": "Finishing", "draft": "Drafting"}
FAILED_TO = {"import": "import or analyse", "finish": "import or analyse", "draft": "draft"}


def do_import(conn, settings: Settings, item: Item, watch: Watch, done: dict) -> None:
    """A new recording, or one whose import or analysis didn't finish."""
    recording_id = item.recording_id
    if item.kind == "import" or library.status_of(
            next(r for r in _rows(conn) if r["id"] == recording_id)) == "Import unfinished":
        recording_id = tasks._ingest(conn, settings, item.path, watch, game=None, tracks=None,
                                     source_type="local_obs")
        if item.kind == "import":
            done["imported"].append(item.label)
    tasks._analyse(conn, settings, recording_id, watch)
    row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    done["analysed"].append(name_of(row))


def do_draft(conn, settings: Settings, item: Item, watch: Watch, night_id: int,
             done: dict) -> None:
    """The plans for one recording, as drafts for Review. Never rendered."""
    from ..recipes.plan import load_plan

    row = conn.execute("SELECT * FROM recordings WHERE id = ?", (item.recording_id,)).fetchone()
    game = row["game"]
    if is_lets_play(settings, game):
        tasks.make_letsplay(settings, row["id"])(watch)
    else:
        tasks.make_highlights(settings, game=game, recording_ids=[row["id"]], minutes=None)(watch)
        if settings.overnight.shorts:
            fewer = settings.model_copy(update={"shorts": settings.shorts.model_copy(
                update={"per_recording": settings.overnight.shorts})})
            tasks.make_shorts(fewer, row["id"])(watch)
    made = [r for r in conn.execute("SELECT plan_id, recipe, recording_ids_json FROM edit_plans")
            if row["id"] in json.loads(r["recording_ids_json"] or "[]")]
    entry = {"name": name_of(row), "highlights": 0, "shorts": 0, "parts": 0}
    for plan in made:
        if plan["recipe"] == "letsplay":
            found = load_plan(conn, plan["plan_id"])
            entry["parts"] += len({s.part for s in found[0].segments if s.part}) if found else 0
        elif plan["recipe"] in entry:
            entry[plan["recipe"]] += 1
    conn.execute("INSERT OR REPLACE INTO overnight_drafts (recording_id, night_id, plan_ids_json, "
                 "made_at) VALUES (?, ?, ?, ?)",
                 (row["id"], night_id, json.dumps([p["plan_id"] for p in made]), _now()))
    conn.commit()
    done["drafted"].append(entry)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _save(conn, night_id: int, status: str, done: dict, finished: bool = False) -> None:
    conn.execute("UPDATE overnight_nights SET status = ?, done_json = ?"
                 + (", finished_at = ?" if finished else "") + " WHERE id = ?",
                 (status, json.dumps(done, ensure_ascii=False))
                 + ((_now(),) if finished else ()) + (night_id,))
    conn.commit()


def begin(conn: sqlite3.Connection, night: str | None) -> int:
    """Tonight's row (made once a night), or a new one for Run it now."""
    if night is not None:
        row = conn.execute("SELECT id FROM overnight_nights WHERE night = ?", (night,)).fetchone()
        if row:
            return row["id"]
    cur = conn.execute("INSERT INTO overnight_nights (night, started_at, status) VALUES (?, ?, ?)",
                       (night, _now(), WAITING))
    conn.commit()
    return cur.lastrowid


def night_job(settings: Settings, night: str | None, *, began: datetime | None = None,
              obs: Obs | None = None, gpu: Callable[[], float | None] = gpu_load,
              sleep: Callable[[float], None] = time.sleep,
              clock: Callable[[], float] = time.monotonic,
              now: Callable[[], datetime] = datetime.now) -> tasks.Job:
    """The night's work, as a job for the Jobs list. ``night``: its date, or
    None when started with Run it now."""

    def run(report: Reporter) -> None:
        from .. import issues

        conn = init_db(settings.db_path)
        watcher = obs or Obs(settings)
        night_id = begin(conn, night)
        done = {"imported": [], "analysed": [], "drafted": [], "problems": [], "waited": {},
                "issues": []}
        old = conn.execute("SELECT done_json FROM overnight_nights WHERE id = ?",
                           (night_id,)).fetchone()
        done.update(json.loads(old["done_json"] or "{}"))   # carrying on after a Pause
        watch = Watch(settings, report, stop=stop_at(settings, began or now()), obs=watcher,
                      gpu=gpu, sleep=sleep, clock=clock, now=now)
        skip: set[str] = set()
        status = None
        try:
            _save(conn, night_id, WORKING, done)
            while True:
                item = None
                try:
                    watch.wait_until_free()
                    items = todo(conn, settings, skip)
                    if not items:
                        break
                    item = items[0]
                    report.say(f"{DOING[item.kind]} {item.label}")
                    if item.kind == "draft":
                        do_draft(conn, settings, item, watch, night_id, done)
                    else:
                        do_import(conn, settings, item, watch, done)
                    skip.add(item.key)   # done: never twice in a night
                except GiveWay as why:
                    report.say(f"Gave way: {why.reason}. That step starts again once it's free.")
                except Exception as exc:  # noqa: BLE001 -- one recording's problem isn't the night's
                    if item is None:
                        raise
                    text = exc.user_message() if isinstance(exc, AIEditorError) else str(exc)
                    if not isinstance(exc, (AIEditorError, TaskFailed)):
                        log.exception("Overnight work: %s failed", item.label)
                    what = f"Overnight work couldn't {FAILED_TO[item.kind]} {item.label}"
                    report.say(f"{what}: {text}")
                    skip.add(item.key)
                    try:
                        found = issues.record(conn, settings, what, source=issues.AI_EDITOR,
                                              recording_id=item.recording_id, error=text)
                        done["issues"].append(found.id)
                    except Exception:  # noqa: BLE001 -- writing it down must not end the night
                        log.exception("Couldn't write down an overnight problem as an issue")
                    done["problems"].append(f"{item.label}: {text}")
                finally:
                    for key, seconds in watch.waited.items():
                        done["waited"][key] = done["waited"].get(key, 0) + seconds
                    watch.waited = {}
                    if watcher.problem and watcher.problem not in done["problems"]:
                        report.say(watcher.problem)
                        done["problems"].append(watcher.problem)
                    _save(conn, night_id, WORKING, done)
            status = DONE
        except StopTime:
            status = STOPPED
            report.say(f"Stopped at {settings.overnight.stop_by}, as set. The rest carries on "
                       "next night.")
        except PauseRequested:
            status = PAUSED
            _save(conn, night_id, PAUSED, done, finished=True)
            raise
        finally:
            watcher.close()
            if status in (DONE, STOPPED):
                _save(conn, night_id, status, done, finished=True)
                report.say(morning_text(done, status, settings))
            elif status is None:   # a problem ended it: Jobs and Issues say what
                _save(conn, night_id, FAILED, done, finished=True)
            conn.close()

    return run


# --- the morning note -------------------------------------------------------------------


def _count(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def morning_text(done: dict, status: str, settings: Settings) -> str:
    """What the night did, in a few plain sentences."""
    said = []
    if done.get("imported"):
        said.append(f"imported {_count(len(done['imported']), 'new recording')}")
    if done.get("analysed"):
        said.append(f"analysed {_count(len(done['analysed']), 'recording')}")
    for d in done.get("drafted", []):
        made = [_count(d[k], w) for k, w in (("highlights", "highlight plan"),
                                              ("shorts", "Short"), ("parts", "Let's Play part"))
                if d.get(k)]
        said.append(f"drafted {' and '.join(made) if made else 'nothing (too few good moments)'} "
                    f"for {d['name']}")
    text = ("Overnight work " + "; ".join(said) + "." if said
            else "Overnight work found nothing new to do.")
    if any(d.get("highlights") or d.get("shorts") or d.get("parts")
           for d in done.get("drafted", [])):
        text += " They're drafts in Review: nothing was rendered."
    waited = done.get("waited") or {}
    if waited:
        text += " Waited " + " and ".join(f"{v / 60:.0f} min for {k}" for k, v in waited.items()) + "."
    if status == STOPPED:
        text += (f" Stopped at {settings.overnight.stop_by} as set; the rest carries on next "
                 "night.")
    elif status == PAUSED:
        text += " Paused in Jobs: Resume carries on."
    elif status == FAILED:
        text += " A problem stopped it: see Jobs and the Issues tab."
    elif status == CLOSED:
        text += " AI-Editor was closed before it finished; the rest carries on next night."
    problems = done.get("problems") or []
    if problems:
        text += f" {_count(len(problems), 'problem')}: " + "; ".join(problems)
        if done.get("issues"):
            text += " (written down in the Issues tab)"
        text += "."
    return text


def morning_note(conn: sqlite3.Connection, settings: Settings) -> tuple[int, str] | None:
    """The last night's note, until you close it. None while it's still working."""
    row = conn.execute("SELECT * FROM overnight_nights WHERE seen = 0 AND status NOT IN (?, ?) "
                       "ORDER BY id DESC LIMIT 1", (WAITING, WORKING)).fetchone()
    if row is None:
        return None
    began = datetime.fromisoformat(row["started_at"])
    when = began.strftime("%a %d %b, %H:%M")
    if row["finished_at"]:
        when += "-" + datetime.fromisoformat(row["finished_at"]).strftime("%H:%M")
    return row["id"], f"**{when}.** " + morning_text(json.loads(row["done_json"] or "{}"),
                                                    row["status"], settings)


def mark_seen(conn: sqlite3.Connection, night_id: int) -> None:
    conn.execute("UPDATE overnight_nights SET seen = 1 WHERE id = ?", (night_id,))
    conn.commit()


def last_night(conn: sqlite3.Connection) -> str:
    """For Settings: when it last ran, and how that ended."""
    row = conn.execute("SELECT * FROM overnight_nights ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return "It hasn't run yet."
    when = datetime.fromisoformat(row["started_at"]).strftime("%a %d %b, %H:%M")
    return f"Last ran {when}: {row['status']}."


def recover(conn: sqlite3.Connection) -> None:
    """A night still 'working' when AI-Editor closed: it ended there."""
    conn.execute("UPDATE overnight_nights SET status = ?, finished_at = COALESCE(finished_at, ?) "
                 "WHERE status IN (?, ?)", (CLOSED, _now(), WAITING, WORKING))
    conn.commit()


# --- starting it ------------------------------------------------------------------------


def check(settings: Settings, worker: Worker, now: datetime | None = None):
    """Start tonight's work if it's due. The Task, or None."""
    conn = init_db(settings.db_path)
    try:
        start = due(conn, settings, now or datetime.now())
    finally:
        conn.close()
    if start is None:
        return None
    return worker.submit(f"Overnight work ({start.strftime('%a %d %b')})", KEY,
                         night_job(settings, start.date().isoformat(), began=start))


def run_now(settings: Settings, worker: Worker):
    """Settings, Run it now: the same work, started straight away."""
    return worker.submit("Overnight work (started by you)", KEY, night_job(settings, None))


def start_clock(settings: Settings, worker: Worker, every: float = 30.0) -> threading.Thread:
    """Looks at the clock every 30 seconds while AI-Editor is open."""

    def loop() -> None:
        while True:
            try:
                check(settings, worker)
            except Exception:  # noqa: BLE001 -- the clock must keep going
                log.exception("Overnight work: couldn't check the time")
            time.sleep(every)

    thread = threading.Thread(target=loop, name="ai-editor-overnight", daemon=True)
    thread.start()
    return thread
