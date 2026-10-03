"""Saving a plan as Resolve timelines, with a subtitle file of the creator's words.

Shared by `ai-editor export` and the app window's Export button.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..config import Settings
from ..recipes.plan import EditPlan, Segment
from .fcpxml import sources_for, write_fcpxml

FOLDER = "timelines"


@dataclass
class Exported:
    saved: list[Path] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # recordings Resolve won't find


def export_plan(conn: sqlite3.Connection, settings: Settings, plan: EditPlan, *,
                episode: int | None = None, parts: list[int] | None = None,
                note: Callable[[int, Segment], str] | None = None) -> Exported:
    """A highlight video as one timeline; a Let's Play as one per part.

    ``episode`` and ``parts`` are for Let's Plays (all parts if None).
    ``note(n, segment)`` writes each clip's marker.
    """
    from ..analysis.captions import Cue, segment_cues, write_srt
    from ..analysis.clips import load_words
    from ..render import parts as lp
    from ..render.audio import choose_tracks

    folder = settings.folders.output / FOLDER
    jobs = [(plan, plan.title, plan.plan_id)]
    if plan.recipe == "letsplay":
        wanted = parts or lp.part_numbers(plan)
        jobs = [(lp.part_plan(plan, n), lp.part_path(settings, plan, episode, n).stem,
                 lp.part_path(settings, plan, episode, n).stem) for n in wanted]

    preset = settings.render.presets[settings.render.preset]
    sources = sources_for(conn, plan)
    result = Exported(missing=[f"#{rid}: {s.path}" for rid, s in sources.items()
                               if not s.path.is_file()])
    # Never the game's dialogue (see render/final.py): a Let's Play's words
    # only come from a recording with the mic on its own track.
    speaking = {rid for rid in plan.recording_ids if plan.recipe != "letsplay"
                or choose_tracks(conn, settings, rid).separate}
    words = {rid: load_words(conn, rid) for rid in speaking}

    for job, name, stem in jobs:
        result.saved.append(write_fcpxml(folder / f"{stem}.fcpxml", job, sources, name=name,
                                         fps=preset.fps, width=preset.width, height=preset.height,
                                         note=note if plan.recipe != "letsplay" else None))
        cues, offset = [], 0.0
        for segment in job.segments:
            length = max(1, round(segment.length * preset.fps)) / preset.fps
            if segment.recording_id in words:
                cues += [Cue(c.start + offset, c.end + offset, c.text) for c in
                         segment_cues(words[segment.recording_id], segment.src_in,
                                      segment.src_in + length)]
            offset += length
        if cues:
            result.saved.append(write_srt(cues, folder / f"{stem}.srt"))
    return result
