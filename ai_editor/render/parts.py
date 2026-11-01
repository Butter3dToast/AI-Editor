"""A Let's Play episode's parts as finished videos, ready to upload.

The Let's Play recipe splits a trimmed episode into parts (recipes/parts.py)
and numbers each piece of the plan with its part. Each part renders as its
own video, named for uploading ("The Blood of Dawnwalker - EP 1 - Part 2"),
with a simple title card over its first seconds ("Ep 1 – Part 2"): the
creator writes the real titles when uploading.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..config import Settings
from ..recipes.plan import EditPlan
from .final import FOLDER

# "EP 1", "EP1", "Ep. 3", "Episode 12" -- how the creator names recordings.
EPISODE = re.compile(r"\b(?:episode|ep)\.?\s*(\d+)\b", re.IGNORECASE)
NOT_IN_FILENAMES = re.compile(r'[<>:"/\\|?*]')


def episode_number(*texts: str | None) -> int | None:
    """The episode number in a recording's name, if it has one."""
    for text in texts:
        found = EPISODE.findall(text or "")
        if found:
            return int(found[-1])
    return None


def episode_of(conn, plan: EditPlan) -> int | None:
    """The episode number, from the plan's title or its recordings' names."""
    rows = conn.execute(f"SELECT title, source_file FROM recordings WHERE id IN "
                        f"({','.join('?' * len(plan.recording_ids))})",
                        plan.recording_ids).fetchall()
    return episode_number(plan.title, *(r["title"] for r in rows),
                          *(Path(r["source_file"]).stem for r in rows))


def _known_episode(conn, plan: EditPlan) -> int | None:
    """The episode a plan was given or named with, or the one its upload text says."""
    if (plan.source or {}).get("episode"):
        return int(plan.source["episode"])
    named = episode_of(conn, plan) if plan.segments else None
    if named:
        return named
    titles = [t for made in (plan.publish or {}).values()
              for t in [*(made.get("titles") or []), (made.get("edited") or {}).get("title")]]
    return episode_number(*titles)


def episode_for(conn, plan: EditPlan) -> tuple[int | None, int | None]:
    """The episode to show for a Let's Play: the one given to this plan (kept with it,
    4F-3a), else the one in its name. With neither, a guess: the next after the last
    episode of the game's earlier Let's Plays (1 Nov: #35 was named by date, and its
    upload text went out as EP 1 while its videos were EP 6). Returns (episode, the
    episode it follows when guessed, else None)."""
    if (plan.source or {}).get("episode"):
        return int(plan.source["episode"]), None
    named = episode_of(conn, plan) if plan.segments else None
    if named:
        return named, None
    rows = conn.execute(
        "SELECT plan_json FROM edit_plans WHERE recipe = 'letsplay' AND plan_id != ? AND "
        "created_at < COALESCE((SELECT created_at FROM edit_plans WHERE plan_id = ?), '9')",
        (plan.plan_id, plan.plan_id)).fetchall()
    earlier = [EditPlan.from_json(r["plan_json"]) for r in rows]
    found = [n for n in (_known_episode(conn, p) for p in earlier if p.game == plan.game) if n]
    return (max(found) + 1, max(found)) if found else (None, None)


def part_numbers(plan: EditPlan) -> list[int]:
    return sorted({s.part for s in plan.segments if s.part is not None})


def part_plan(plan: EditPlan, part: int) -> EditPlan:
    return EditPlan(f"{plan.plan_id}_part{part}", plan.recipe, f"{plan.title} - Part {part}",
                    plan.game, 0, [s for s in plan.segments if s.part == part], dict(plan.output))


def part_path(settings: Settings, plan: EditPlan, episode: int, part: int, *,
              captions: bool = False) -> Path:
    from . import names

    name = f"{plan.game or 'Lets Play'} - EP {episode} - Part {part}{' captions' if captions else ''}"
    usual = settings.folders.output / FOLDER / f"{NOT_IN_FILENAMES.sub('', name).strip()}.mp4"
    return names.found(usual, plan, part, captions)   # saved under its title, if it had one


def title_card(settings: Settings, episode: int, part: int) -> str | None:
    text = settings.lets_play.title_card.format(episode=episode, part=part).strip()
    return text or None
