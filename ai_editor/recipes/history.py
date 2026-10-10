"""Undo and Redo in Review (Phase 2D-1).

What the creator chose (2026-10-10): Undo and Redo for every change in
Review (remove, move, teaser, add, adjusting a cut, effect switches), kept
after AI-Editor closes. Each change is a row in plan_history with the plan
before and after it, so stepping back and forward is just putting one of
them back.

Two things a change touches outside the plan go back with it: a library
clip re-cut by "Adjust the cut", and the feedback the change logged, which
is marked undone so a misclick never teaches the AI anything.

The upload text (plan.publish) never goes back: it took the AI a minute to
write, and it isn't part of the edit.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from .plan import EditPlan

# Steps kept per video; the oldest go first.
KEEP = 200
CLIP_FIELDS = ("start_sec", "end_sec", "signals_json", "transcript")


def _plan_json(conn: sqlite3.Connection, plan_id: str) -> str | None:
    row = conn.execute("SELECT plan_json FROM edit_plans WHERE plan_id = ?", (plan_id,)).fetchone()
    return row["plan_json"] if row else None


def _clip_state(conn: sqlite3.Connection, clip_id: str) -> dict | None:
    row = conn.execute(f"SELECT {', '.join(CLIP_FIELDS)} FROM clips WHERE clip_id = ?",
                       (clip_id,)).fetchone()
    return dict(row) if row else None


def _edit_of(text: str) -> dict:
    """The parts of a plan an undo puts back: everything but the upload text."""
    data = json.loads(text)
    data.pop("publish", None)
    return data


@contextmanager
def step(conn: sqlite3.Connection, plan_id: str, what: str,
         clips: list[str | None] = ()) -> Iterator[None]:
    """Record whatever the body changes in a plan as one step to undo.

    ``what``: the change in plain words ("removing clip 4"), for the Undo
    button. ``clips``: library clips the change may re-cut. A body that ends
    up changing nothing records nothing.
    """
    before = _plan_json(conn, plan_id)
    newest = conn.execute("SELECT COALESCE(MAX(id), 0) FROM feedback").fetchone()[0]
    watched = [c for c in dict.fromkeys(clips) if c]
    clips_before = {c: _clip_state(conn, c) for c in watched}
    yield
    after = _plan_json(conn, plan_id)
    if before is None or after is None:
        return
    recut = [{"clip_id": c, "before": clips_before[c], "after": _clip_state(conn, c)}
             for c in watched if clips_before[c] != _clip_state(conn, c)]
    if _edit_of(before) == _edit_of(after) and not recut:
        return
    logged = [r[0] for r in conn.execute("SELECT id FROM feedback WHERE id > ? AND plan_id = ?",
                                         (newest, plan_id))]
    # A new change after stepping back: what was undone can't be redone any more.
    conn.execute("DELETE FROM plan_history WHERE plan_id = ? AND undone = 1", (plan_id,))
    conn.execute(
        "INSERT INTO plan_history (plan_id, what, before_json, after_json, clips_json, "
        "feedback_json, made_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (plan_id, what, before, after, json.dumps(recut), json.dumps(logged),
         datetime.now(timezone.utc).isoformat(timespec="seconds")))
    conn.execute(
        "DELETE FROM plan_history WHERE plan_id = ? AND id NOT IN (SELECT id FROM plan_history "
        "WHERE plan_id = ? ORDER BY id DESC LIMIT ?)", (plan_id, plan_id, KEEP))
    conn.commit()


def can(conn: sqlite3.Connection, plan_id: str | None) -> tuple[str | None, str | None]:
    """(what Undo would take back, what Redo would do again); None where there's nothing."""
    if not plan_id:
        return None, None
    back = conn.execute("SELECT what FROM plan_history WHERE plan_id = ? AND undone = 0 "
                        "ORDER BY id DESC LIMIT 1", (plan_id,)).fetchone()
    again = conn.execute("SELECT what FROM plan_history WHERE plan_id = ? AND undone = 1 "
                         "ORDER BY id LIMIT 1", (plan_id,)).fetchone()
    return (back["what"] if back else None), (again["what"] if again else None)


def _put_back(conn: sqlite3.Connection, plan_id: str, text: str) -> None:
    """The plan as ``text`` has it, keeping today's upload text and status."""
    plan = EditPlan.from_json(text)
    current = _plan_json(conn, plan_id)
    if current is not None:
        plan.publish = json.loads(current).get("publish", {})
    conn.execute("UPDATE edit_plans SET plan_json = ?, recording_ids_json = ?, updated_at = ? "
                 "WHERE plan_id = ?",
                 (plan.to_json(), json.dumps(plan.recording_ids),
                  datetime.now(timezone.utc).isoformat(timespec="seconds"), plan_id))


def _clips_to(conn: sqlite3.Connection, recut: list[dict], side: str) -> None:
    for clip in recut:
        state = clip[side]
        if state is None:
            continue
        # A clip cut again since (analysis ran again) is left as it is now.
        if _clip_state(conn, clip["clip_id"]) is None:
            continue
        conn.execute(f"UPDATE clips SET {', '.join(f'{f} = ?' for f in CLIP_FIELDS)} "
                     "WHERE clip_id = ?", (*[state[f] for f in CLIP_FIELDS], clip["clip_id"]))


def undo(conn: sqlite3.Connection, plan_id: str | None) -> str:
    """Take back the newest change. Returns what happened, in plain words."""
    row = conn.execute("SELECT * FROM plan_history WHERE plan_id = ? AND undone = 0 "
                       "ORDER BY id DESC LIMIT 1", (plan_id,)).fetchone() if plan_id else None
    if row is None:
        return "Nothing to undo."
    _put_back(conn, plan_id, row["before_json"])
    _clips_to(conn, json.loads(row["clips_json"] or "[]"), "before")
    logged = json.loads(row["feedback_json"] or "[]")
    conn.executemany("UPDATE feedback SET undone = 1 WHERE id = ?", [(i,) for i in logged])
    conn.execute("UPDATE plan_history SET undone = 1 WHERE id = ?", (row["id"],))
    conn.commit()
    return f"Undone: {row['what']}."


def redo(conn: sqlite3.Connection, plan_id: str | None) -> str:
    """Do again the change most recently undone."""
    row = conn.execute("SELECT * FROM plan_history WHERE plan_id = ? AND undone = 1 "
                       "ORDER BY id LIMIT 1", (plan_id,)).fetchone() if plan_id else None
    if row is None:
        return "Nothing to redo."
    _put_back(conn, plan_id, row["after_json"])
    _clips_to(conn, json.loads(row["clips_json"] or "[]"), "after")
    logged = json.loads(row["feedback_json"] or "[]")
    conn.executemany("UPDATE feedback SET undone = 0 WHERE id = ?", [(i,) for i in logged])
    conn.execute("UPDATE plan_history SET undone = 0 WHERE id = ?", (row["id"],))
    conn.commit()
    return f"Redone: {row['what']}."
