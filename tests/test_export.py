"""Resolve timelines (FCPXML): the backup route for fine-tuning by hand."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ai_editor.export.fcpxml import Source, fcpxml, frame_duration
from ai_editor.recipes.plan import EditPlan, Segment

SOURCES = {
    9: Source(Path("F:/AI-Editor/raw/2026-09-26 19-55-09.mkv"), 8141.5, 60.0, 1920, 1080, 4),
    3: Source(Path("F:/AI-Editor/raw/Twitch Vod.mp4"), 6752.1, 59.94, 1920, 1080, 1),
}


def timeline(plan: EditPlan, **kwargs) -> ET.Element:
    text = fcpxml(plan, SOURCES, name="Test", fps=60, width=1920, height=1080, **kwargs)
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>')
    return ET.fromstring(text.split("\n", 2)[2])


def test_clips_follow_each_other_frame_exact_from_the_original_recordings():
    plan = EditPlan("p", "highlights", "T", None, 600,
                    [Segment(9, 7911.4, 7919.4, kind="teaser"), Segment(9, 442.283, 495.0),
                     Segment(3, 100.0, 130.5)])
    root = timeline(plan)
    clips = root.findall(".//spine/asset-clip")
    assert [c.get("offset") for c in clips] == ["0s", "480/60s", "3643/60s"]
    assert [c.get("duration") for c in clips] == ["480/60s", "3163/60s", "1830/60s"]
    assert clips[1].get("start") == f"{round(442.283 * 60)}/60s"
    assert root.find(".//sequence").get("duration") == f"{480 + 3163 + 1830}/60s"
    assets = {a.get("id"): a for a in root.findall(".//asset")}
    assert assets[clips[0].get("ref")].get("src") == "file:///F:/AI-Editor/raw/2026-09-26%2019-55-09.mkv"
    assert assets[clips[0].get("ref")].get("audioSources") == "4"  # mic, game, Discord and the mix


def test_each_recording_and_frame_rate_is_listed_once():
    plan = EditPlan("p", "highlights", "T", None, 600,
                    [Segment(9, 0, 10), Segment(3, 0, 10), Segment(9, 20, 30)])
    root = timeline(plan)
    assert len(root.findall(".//asset")) == 2
    ids = [e.get("id") for e in root.find("resources")]
    assert len(ids) == len(set(ids))  # every resource has its own id
    rates = {f.get("frameDuration") for f in root.findall(".//format")}
    assert rates == {"1/60s", "1001/60000s"}  # the Twitch VOD is 59.94


def test_markers_say_why_each_clip_is_there():
    plan = EditPlan("p", "highlights", "T", None, 600,
                    [Segment(9, 10, 20, kind="teaser", reasons=["marker"])])
    root = timeline(plan, note=lambda n, s: f"Teaser: {', '.join(s.reasons)}")
    marker = root.find(".//asset-clip/marker")
    assert marker.get("value") == "Teaser: marker" and marker.get("start") == "600/60s"


def test_frame_lengths():
    assert frame_duration(60) == "1/60s" and frame_duration(30.0) == "1/30s"
    assert frame_duration(59.94) == "1001/60000s" and frame_duration(29.97) == "1001/30000s"
