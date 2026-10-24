"""Your rules, kept in the library (the rules table, spec 7.5) and stamped into plans.

A plan keeps a copy of the rules it was made with (plan.source["rules"]), as
it does a style profile's values: everything that refills, previews or renders
it reads them from there (style/apply.styled), so a rule changed later never
quietly changes a plan already reviewed. To use the new rules, make the plan
again.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ..config import Settings
from .kinds import KINDS, Rule, apply

if TYPE_CHECKING:
    from ..recipes.plan import EditPlan


@dataclass
class Saved:
    id: int
    rule_id: str              # "r001"
    tip: str                  # your words
    rule: Rule
    enabled: bool
    created_at: str


def _row(r: sqlite3.Row) -> Saved:
    scope = json.loads(r["scope_json"] or "{}")
    data = json.loads(r["rule_json"] or "{}")
    rule = Rule(data.get("kind", "note"), data.get("params") or {}, scope.get("games") or [],
                scope.get("videos") or [], data.get("why_note", ""), r["rule_id"])
    return Saved(r["id"], r["rule_id"], r["source_text"], rule, bool(r["enabled"]),
                 r["created_at"])


def every(conn: sqlite3.Connection) -> list[Saved]:
    """All rules and notes, oldest first (a newer rule wins over an older one)."""
    return [_row(r) for r in conn.execute("SELECT * FROM rules ORDER BY id")]


def get(conn: sqlite3.Connection, rule_id: str) -> Saved | None:
    row = conn.execute("SELECT * FROM rules WHERE rule_id = ?", (rule_id,)).fetchone()
    return _row(row) if row else None


def add(conn: sqlite3.Connection, tip: str, rule: Rule) -> str:
    """Save a rule (or a note). Returns its id, "r001"."""
    n = (conn.execute("SELECT MAX(id) FROM rules").fetchone()[0] or 0) + 1
    while conn.execute("SELECT 1 FROM rules WHERE rule_id = ?", (f"r{n:03d}",)).fetchone():
        n += 1
    rule_id = f"r{n:03d}"
    conn.execute(
        "INSERT INTO rules (rule_id, source_text, scope_json, rule_json, enabled, is_note, "
        "created_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
        (rule_id, tip.strip(), json.dumps({"games": rule.games, "videos": rule.videos}),
         json.dumps({"kind": rule.kind, "params": rule.params, "why_note": rule.why_note,
                     "said": rule.said()}),
         int(rule.is_note), datetime.now(timezone.utc).isoformat(timespec="seconds")))
    conn.commit()
    return rule_id


def switch(conn: sqlite3.Connection, rule_id: str, on: bool) -> None:
    conn.execute("UPDATE rules SET enabled = ? WHERE rule_id = ?", (int(on), rule_id))
    conn.commit()


def delete(conn: sqlite3.Connection, rule_id: str) -> bool:
    """Only when you press Delete: AI-Editor never removes a rule by itself."""
    gone = conn.execute("DELETE FROM rules WHERE rule_id = ?", (rule_id,)).rowcount
    conn.commit()
    return gone > 0


def matching(conn: sqlite3.Connection, game: str | None, video: str) -> list[Saved]:
    """The switched-on rules for this game and kind of video, oldest first."""
    return [s for s in every(conn) if s.enabled and s.rule.applies_to(game, video)]


def clashes(saved: list[Saved]) -> dict[str, str]:
    """{older rule: newer rule that overrides it}: same kind and value, overlapping
    places (an empty list is everywhere). The newer wins; the Rules tab says so."""
    found: dict[str, str] = {}
    live = [s for s in saved if s.enabled and not s.rule.is_note]
    for i, old in enumerate(live):
        for new in live[i + 1:]:
            a, b = old.rule, new.rule
            if a.kind != b.kind:
                continue
            if a.kind == "switch":
                same = a.params.get("switch") == b.params.get("switch")
            elif a.kind in ("moment", "effect_on_moment"):   # about the same moment
                same = bool(set(a.params.get("moments") or []) & set(b.params.get("moments") or []))
            else:
                same = bool(set(a.params) & set(b.params))   # they set the same value
            if not same:
                continue
            games = not a.games or not b.games or \
                {g.casefold() for g in a.games} & {g.casefold() for g in b.games}
            videos = not a.videos or not b.videos or set(a.videos) & set(b.videos)
            if games and videos:
                found[old.rule_id] = new.rule_id
    return found


# --- In plans ----------------------------------------------------------------------------------


def with_rules(conn: sqlite3.Connection, settings: Settings, game: str | None,
               video: str) -> tuple[Settings, list[Saved]]:
    """(settings with the matching rules in, those rules): for making a plan."""
    found = matching(conn, game, video)
    return apply(settings, [s.rule for s in found], video), found


def stamp(plan: "EditPlan", found: list[Saved]) -> None:
    """Keep a copy of the rules a plan was made with."""
    plan.source = dict(plan.source or {})
    plan.source["rules"] = [{"id": s.rule_id, "kind": s.rule.kind, "params": s.rule.params,
                             "games": s.rule.games, "said": s.rule.said()} for s in found]


def stamped(plan: "EditPlan") -> list[Rule]:
    return [Rule(r["kind"], r.get("params") or {}, list(r.get("games") or []), id=r.get("id", ""))
            for r in (plan.source or {}).get("rules") or [] if r.get("kind") in KINDS]


def summary(plan: "EditPlan") -> str | None:
    """Review's line: which rules the plan was made with."""
    rules = (plan.source or {}).get("rules") or []
    if not rules:
        return None
    return "Rules: " + "; ".join(f"{r['id']} {r['said'].rstrip('.')}" for r in rules) + "."
