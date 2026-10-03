"""Timelines for DaVinci Resolve (FCPXML): the backup route (spec section 7.9).

The creator finishes videos inside AI-Editor; this is for the odd video
they'd rather fine-tune by hand. An edit plan becomes a Resolve timeline:
every clip in its place, cut from the original recording (not a copy), with
a marker on each saying why it's there. Resolve: File > Import > Timeline.

What carries over is the edit -- which stretches, in what order. What
AI-Editor does while rendering doesn't: the rebuilt sound (music left
out, marker beeps filtered, loudness) and burned-in captions. The captions
come as a subtitle file beside the timeline instead, which Resolve imports
onto a subtitle track.

Written by hand rather than through OpenTimelineIO: FCPXML is the one
format Resolve's free version imports reliably, and it needs no extra
download for something used rarely.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import Callable

from ..recipes.plan import EditPlan, Segment

VERSION = "1.9"  # FCPXML version that Resolve 17 and later import


@dataclass(frozen=True)
class Source:
    """What the timeline needs to know about one recording."""
    path: Path
    duration_sec: float
    fps: float
    width: int
    height: int
    audio_tracks: int


def frame_duration(fps: float) -> str:
    """'1/60s', or '1001/60000s' for 59.94."""
    whole = round(fps)
    if abs(fps - whole) < 0.01:
        return f"1/{whole}s"
    return f"1001/{round(fps * 1.001) * 1000}s"


def at(frames: int, fps: int) -> str:
    """A time FCPXML's way: a whole number of frames over the frame rate."""
    return "0s" if frames == 0 else f"{frames}/{fps}s"


def fcpxml(plan: EditPlan, sources: dict[int, Source], *, name: str, fps: int, width: int,
           height: int, note: Callable[[int, Segment], str] | None = None) -> str:
    """``note(n, segment)``: the marker text for the n-th segment."""
    root = ET.Element("fcpxml", version=VERSION)
    resources = ET.SubElement(root, "resources")
    ET.SubElement(resources, "format", id="r0", frameDuration=frame_duration(fps),
                  width=str(width), height=str(height), colorSpace="1-1-1 (Rec. 709)")
    ids = (f"r{n}" for n in count(1))
    formats = {(frame_duration(fps), width, height): "r0"}
    assets: dict[int, str] = {}
    for rid in plan.recording_ids:
        src = sources[rid]
        shape = (frame_duration(src.fps), src.width, src.height)
        if shape not in formats:
            formats[shape] = next(ids)
            ET.SubElement(resources, "format", id=formats[shape], frameDuration=frame_duration(src.fps),
                          width=str(src.width), height=str(src.height),
                          colorSpace="1-1-1 (Rec. 709)")
        assets[rid] = next(ids)
        ET.SubElement(resources, "asset", id=assets[rid], name=src.path.stem, start="0s",
                      duration=at(int(src.duration_sec * fps), fps), hasVideo="1",
                      format=formats[shape], hasAudio="1" if src.audio_tracks else "0",
                      audioSources=str(max(1, src.audio_tracks)), audioChannels="2",
                      audioRate="48000", src=src.path.resolve().as_uri())

    frames = [max(1, round(s.length * fps)) for s in plan.segments]
    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="AI-Editor")
    project = ET.SubElement(event, "project", name=name)
    sequence = ET.SubElement(project, "sequence", format="r0", duration=at(sum(frames), fps),
                             tcStart="0s", tcFormat="NDF", audioLayout="stereo", audioRate="48k")
    spine = ET.SubElement(sequence, "spine")
    offset = 0
    for n, (segment, length) in enumerate(zip(plan.segments, frames), start=1):
        start = round(segment.src_in * fps)
        clip = ET.SubElement(spine, "asset-clip", ref=assets[segment.recording_id],
                             name=f"{n:02d} {sources[segment.recording_id].path.stem}",
                             offset=at(offset, fps), start=at(start, fps),
                             duration=at(length, fps), tcFormat="NDF")
        if note is not None:
            ET.SubElement(clip, "marker", start=at(start, fps), duration=f"1/{fps}s",
                          value=note(n, segment))
        offset += length

    ET.indent(root)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n'
            + ET.tostring(root, encoding="unicode") + "\n")


def write_fcpxml(path: Path, *args, **kwargs) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fcpxml(*args, **kwargs), encoding="utf-8")
    return path


def sources_for(conn, plan: EditPlan) -> dict[int, Source]:
    rows = conn.execute(
        "SELECT r.id, r.source_file, r.duration_sec, r.fps, r.width, r.height, "
        "(SELECT COUNT(*) FROM audio_tracks a WHERE a.recording_id = r.id) AS tracks "
        f"FROM recordings r WHERE r.id IN ({','.join('?' * len(plan.recording_ids))})",
        plan.recording_ids).fetchall()
    return {r["id"]: Source(Path(r["source_file"]), r["duration_sec"] or 0.0, r["fps"] or 60.0,
                            r["width"] or 1920, r["height"] or 1080, r["tracks"]) for r in rows}
