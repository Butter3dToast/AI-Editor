"""What a finished video's file is called (0.25.1).

The title you kept in Review's upload text, when there is one: "when I render
the video, it gets saved with that title that was given to it before
rendering" (the creator, 24 Oct). Without one, the usual name: the plan's id,
or "Game - EP 4 - Part 1" for a Let's Play part.

The name a video was saved under is kept in its plan (plan.source["files"]),
so AI-Editor finds it again (Open the video, the upload text beside it) even
after the title changes. A new title is used the next time it's rendered; the
old file stays where it is, since AI-Editor never deletes a video. Never over
another video's file: a second "Penta kill!" is saved as "Penta kill! (2)".
"""

from __future__ import annotations

import re
from pathlib import Path

from ..recipes.plan import EditPlan

FILES = "files"
NOT_IN_FILENAMES = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
LONGEST = 150   # characters, before " captions": Windows paths stop at 260


def key(plan: EditPlan, part: int | None, captions: bool) -> str:
    """'video', 'video captions', 'part 2'... A Short has one file, always captioned."""
    captions = captions and plan.recipe != "shorts"
    return f"{f'part {part}' if part else 'video'}{' captions' if captions else ''}"


def saved_as(plan: EditPlan, part: int | None, captions: bool) -> str | None:
    return ((plan.source or {}).get(FILES) or {}).get(key(plan, part, captions))


def found(usual: Path, plan: EditPlan, part: int | None, captions: bool) -> Path:
    """Where the video is: the name it was saved under, else the usual one."""
    name = saved_as(plan, part, captions)
    return usual.with_name(name) if name else usual


def clean(title: str) -> str:
    """A title as a file name: no characters Windows refuses, not too long."""
    name = " ".join(NOT_IN_FILENAMES.sub("", title).split())
    if len(name) > LONGEST:
        name = name[:LONGEST].rsplit(" ", 1)[0] or name[:LONGEST]
    return name.rstrip(". ")


def target(usual: Path, plan: EditPlan, part: int | None, captions: bool) -> Path:
    """Where to save it now: the kept title, if there is one."""
    from ..publish import saved

    text = saved(plan, part)
    title = clean(text.title) if text is not None and text.title else ""
    if not title:
        return found(usual, plan, part, captions)
    name = title + (" captions" if captions and plan.recipe != "shorts" else "")
    mine = saved_as(plan, part, captions)
    path, n = usual.with_name(f"{name}.mp4"), 2
    while path.exists() and path.name != mine:
        path, n = usual.with_name(f"{name} ({n}).mp4"), n + 1
    return path


def remember(plan: EditPlan, part: int | None, captions: bool, path: Path) -> None:
    plan.source = dict(plan.source or {})
    files = dict(plan.source.get(FILES) or {})
    files[key(plan, part, captions)] = path.name
    plan.source[FILES] = files
