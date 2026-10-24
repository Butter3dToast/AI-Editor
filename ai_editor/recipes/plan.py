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
SHORTS_PREFIX = "shorts_"

# clips.user_rating. A 🔖 "Next video" clip is a good one saved for a later
# video (3A-1): learning counts it like a thumbs up, picking keeps it apart.
LIKED, SAVED, DISLIKED = 1, 2, -1


def is_short(plan_id: str) -> bool:
    return plan_id.startswith(SHORTS_PREFIX)


def used_in(used_json: str | None, *, shorts: bool) -> list[str]:
    """The plans a clip is used in: Shorts, or long videos. Each kind uses
    clips up for its own kind only -- a clip that's a Short can still be in a
    highlight video, and the other way round (Shorts point viewers to them)."""
    return [p for p in json.loads(used_json or "[]") if is_short(p) == shorts]


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
    # Upload text and thumbnails (publish.py), per video: "video", or "part 2".
    publish: dict[str, Any] = field(default_factory=dict)

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


def discard_drafts(conn: sqlite3.Connection, recipe: str, game: str | None,
                   streams: list[int] | None) -> int:
    """Remaking a draft replaces the old one instead of piling up copies: one of
    the same game from the same streams. ``streams``: the recordings asked for
    (None: all of them). A draft from other streams stays (10 Oct: a plan from
    the 8 Oct stream was replaced by one from the 9th)."""
    want = sorted(streams) if streams else None
    rows = conn.execute(
        "SELECT plan_id, plan_json, recording_ids_json FROM edit_plans WHERE recipe = ? "
        "AND status = ?", (recipe, DRAFT),
    ).fetchall()
    doomed = []
    for r in rows:
        data = json.loads(r["plan_json"])
        source = data.get("source") or {}
        had = (source["recording_ids"] if "recording_ids" in source
               else json.loads(r["recording_ids_json"]))
        if data.get("game") == game and (sorted(had) if had else None) == want:
            doomed.append(r["plan_id"])
    conn.executemany("DELETE FROM edit_plans WHERE plan_id = ?", [(p,) for p in doomed])
    conn.commit()
    return len(doomed)


def delete_plan(conn: sqlite3.Connection, plan_id: str) -> bool:
    """Take a plan out of the list, when the creator presses Delete in Review (10 Oct:
    the list had grown long). Only the plan and its Undo history go: finished videos
    and quick previews stay on disk, and the clips, ratings and feedback stay, its
    clips still marked as used."""
    gone = conn.execute("DELETE FROM edit_plans WHERE plan_id = ?", (plan_id,)).rowcount
    conn.commit()
    return gone > 0


def delete_plans(conn: sqlite3.Connection, plan_ids: list[str]) -> int:
    """Several plans ticked in Review, all at once (24 Oct: one by one was "very
    painful"). The same as delete_plan for each. How many went."""
    return sum(delete_plan(conn, plan_id) for plan_id in plan_ids)


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


def _log_used(conn: sqlite3.Connection, plan: EditPlan, clip_id: str) -> None:
    row = conn.execute("SELECT clips.signals_json, clips.user_rating, recordings.game "
                       "FROM clips JOIN recordings ON recordings.id = clips.recording_id "
                       "WHERE clip_id = ?", (clip_id,)).fetchone()
    short = is_short(plan.plan_id)
    if not short and row["user_rating"] == SAVED:
        conn.execute("UPDATE clips SET user_rating = ? WHERE clip_id = ?", (LIKED, clip_id))
    game = json.loads(row["signals_json"] or "{}").get("game") or row["game"] or plan.game
    conn.execute("INSERT INTO feedback (ts, action, clip_id, plan_id, game, features_json, "
                 "detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "in_short" if short else "in_video", clip_id, plan.plan_id, game,
                  row["signals_json"], json.dumps({"rating": row["user_rating"]})))


def approve_plan(conn: sqlite3.Connection, plan_id: str) -> int:
    """Mark a plan final and its clips as used. Returns how many clips were marked.

    Each newly used clip is logged as feedback (in_video or in_short): a clip
    that made it into something rendered is a small "good" hint for learning
    (3A-1). A 🔖 clip used in a video becomes a thumbs up: it's been used."""
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
            _log_used(conn, plan, clip_id)
            marked += 1
    conn.execute("UPDATE edit_plans SET status = ?, updated_at = ? WHERE plan_id = ?",
                 (APPROVED, datetime.now(timezone.utc).isoformat(timespec="seconds"), plan_id))
    conn.commit()
    return marked
