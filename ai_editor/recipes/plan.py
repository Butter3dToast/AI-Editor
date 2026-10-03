"""Edit plans: a whole video described as data (spec section 7.7).

A recipe (highlights, Let's Play) writes a plan; the renderer (Phase 1G) and
the exporter read it; the review screen (Phase 1H) edits it. Nothing in a
plan is video: it lists which stretches of which recordings go where.

A plan starts as a **draft**. Drafts can be remade freely and never use up
clips. Approving a plan marks its clips as used, so the next highlight video
carries on with the clips that are left (spec section 7.6, Recipe B).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

DRAFT = "draft"
APPROVED = "approved"


@dataclass
class Segment:
    recording_id: int
    src_in: float
    src_out: float
    kind: str = "clip"           # clip | teaser | piece (of a Let's Play)
    clip_id: str | None = None
    game: str | None = None
    score: float | None = None
    reasons: list[str] = field(default_factory=list)
    captions: bool = True
    effects: list[dict[str, Any]] = field(default_factory=list)
    part: int | None = None      # a Let's Play episode's part number (1, 2, ...)

    @property
    def length(self) -> float:
        return self.src_out - self.src_in


@dataclass
class EditPlan:
    plan_id: str
    recipe: str
    title: str
    game: str | None
    target_sec: float
    segments: list[Segment] = field(default_factory=list)
    output: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # What the recipe drew from (game, recording numbers), and clips the
    # creator took out in Review, so a removed clip can be replaced the same way.
    source: dict[str, Any] = field(default_factory=dict)

    @property
    def total_sec(self) -> float:
        return sum(s.length for s in self.segments)

    @property
    def recording_ids(self) -> list[int]:
        seen: list[int] = []
        for segment in self.segments:
            if segment.recording_id not in seen:
                seen.append(segment.recording_id)
        return seen

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "EditPlan":
        data = json.loads(text)
        data["segments"] = [Segment(**s) for s in data.get("segments", [])]
        return cls(**data)


def _slug(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "streams").lower()).strip("-") or "streams"


def new_plan_id(conn: sqlite3.Connection, recipe: str, game: str | None) -> str:
    """e.g. highlights_wardogs_2026-09-26_2 -- readable, and unique."""
    stem = f"{recipe}_{_slug(game)}_{datetime.now().strftime('%Y-%m-%d')}"
    taken = {r[0] for r in conn.execute(
        "SELECT plan_id FROM edit_plans WHERE plan_id LIKE ?", (stem + "%",))}
    number = 1
    while f"{stem}_{number}" in taken:
        number += 1
    return f"{stem}_{number}"


def save_plan(conn: sqlite3.Connection, plan: EditPlan, status: str = DRAFT) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO edit_plans (plan_id, recipe, recording_ids_json, plan_json, status, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(plan_id) DO UPDATE SET plan_json = excluded.plan_json, "
        "recording_ids_json = excluded.recording_ids_json, status = excluded.status, "
        "updated_at = excluded.updated_at",
        (plan.plan_id, plan.recipe, json.dumps(plan.recording_ids), plan.to_json(), status,
         now, now),
    )
    conn.commit()


def discard_drafts(conn: sqlite3.Connection, recipe: str, game: str | None) -> int:
    """Remaking a draft replaces the old one instead of piling up copies."""
    rows = conn.execute(
        "SELECT plan_id, plan_json FROM edit_plans WHERE recipe = ? AND status = ?",
        (recipe, DRAFT),
    ).fetchall()
    doomed = [r["plan_id"] for r in rows if json.loads(r["plan_json"]).get("game") == game]
    conn.executemany("DELETE FROM edit_plans WHERE plan_id = ?", [(p,) for p in doomed])
    conn.commit()
    return len(doomed)


def latest_draft(conn: sqlite3.Connection, recipe: str, game: str | None = None) -> EditPlan | None:
    """The newest draft of this recipe: for one game, or any game when ``game`` is None."""
    rows = conn.execute(
        "SELECT plan_json FROM edit_plans WHERE recipe = ? AND status = ? ORDER BY updated_at DESC, "
        "rowid DESC", (recipe, DRAFT)).fetchall()
    for row in rows:
        plan = EditPlan.from_json(row["plan_json"])
        if game is None or plan.game == game:
            return plan
    return None


def load_plan(conn: sqlite3.Connection, plan_id: str) -> tuple[EditPlan, str] | None:
    row = conn.execute("SELECT plan_json, status FROM edit_plans WHERE plan_id = ?",
                       (plan_id,)).fetchone()
    return (EditPlan.from_json(row["plan_json"]), row["status"]) if row else None


def approve_plan(conn: sqlite3.Connection, plan_id: str) -> int:
    """Mark a plan final and its clips as used. Returns how many clips were marked."""
    found = load_plan(conn, plan_id)
    if found is None:
        return -1
    plan, _ = found
    in_plan = {s.clip_id for s in plan.segments if s.clip_id}
    # Clips taken out in Review after an earlier approval are free again.
    for row in conn.execute("SELECT clip_id, used_in_json FROM clips WHERE used_in_json LIKE ?",
                            (f'%"{plan_id}"%',)).fetchall():
        if row["clip_id"] not in in_plan:
            used = [p for p in json.loads(row["used_in_json"]) if p != plan_id]
            conn.execute("UPDATE clips SET used_in_json = ? WHERE clip_id = ?",
                         (json.dumps(used) if used else None, row["clip_id"]))
    marked = 0
    for clip_id in in_plan:
        row = conn.execute("SELECT used_in_json FROM clips WHERE clip_id = ?", (clip_id,)).fetchone()
        if row is None:
            continue
        used = json.loads(row["used_in_json"] or "[]")
        if plan_id not in used:
            used.append(plan_id)
            conn.execute("UPDATE clips SET used_in_json = ? WHERE clip_id = ?",
                         (json.dumps(used), clip_id))
            marked += 1
    conn.execute("UPDATE edit_plans SET status = ?, updated_at = ? WHERE plan_id = ?",
                 (APPROVED, datetime.now(timezone.utc).isoformat(timespec="seconds"), plan_id))
    conn.commit()
    return marked
