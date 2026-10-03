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


def part_numbers(plan: EditPlan) -> list[int]:
    return sorted({s.part for s in plan.segments if s.part is not None})


def part_plan(plan: EditPlan, part: int) -> EditPlan:
    return EditPlan(f"{plan.plan_id}_part{part}", plan.recipe, f"{plan.title} - Part {part}",
                    plan.game, 0, [s for s in plan.segments if s.part == part], dict(plan.output))


def part_path(settings: Settings, plan: EditPlan, episode: int, part: int, *,
              captions: bool = False) -> Path:
    name = f"{plan.game or 'Lets Play'} - EP {episode} - Part {part}{' captions' if captions else ''}"
    return settings.folders.output / FOLDER / f"{NOT_IN_FILENAMES.sub('', name).strip()}.mp4"


def title_card(settings: Settings, episode: int, part: int) -> str | None:
    text = settings.lets_play.title_card.format(episode=episode, part=part).strip()
    return text or None
