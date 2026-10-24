"""A finished video is saved under the title kept in Review (0.25.1)."""

from __future__ import annotations

import subprocess

from ai_editor import publish
from ai_editor.ffmpeg import concat_list, measure_loudness, stream_lengths
from ai_editor.recipes.plan import EditPlan
from ai_editor.render import names, parts as lp
from ai_editor.render.final import video_path

from .conftest import FFMPEG, needs_ffmpeg


def plan_of(recipe: str = "highlights", title: str | None = None, part: int | None = None) -> EditPlan:
    plan = EditPlan(f"{recipe}_league_2026-10-24_1", recipe, "League highlights", "League of Legends",
                    600.0, [])
    if title is not None:
        made = publish.Publish(["An idea"], "", [], [], [], "", "", edited={"title": title})
        plan.publish[publish.key_of(part)] = made.as_dict()
    return plan


def test_without_a_kept_title_it_has_the_usual_name(settings):
    plan = plan_of()
    usual = video_path(settings, plan)
    assert names.target(usual, plan, None, False) == usual
    assert usual.name == "highlights_league_2026-10-24_1.mp4"


def test_it_is_saved_under_the_kept_title_and_found_there_again(settings):
    plan = plan_of(title='PENTA?! | My "best" game')
    path = names.target(video_path(settings, plan, captions=True), plan, None, True)
    assert path.name == "PENTA! My best game captions.mp4"
    assert path.parent == settings.folders.output / "videos"
    names.remember(plan, None, True, path)
    assert video_path(settings, plan, captions=True) == path
    assert video_path(settings, plan).name == "highlights_league_2026-10-24_1.mp4"  # not rendered


def test_never_over_another_videos_file(settings):
    plan = plan_of(title="Penta kill")
    folder = video_path(settings, plan).parent
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Penta kill.mp4").write_bytes(b"another video")
    path = names.target(video_path(settings, plan), plan, None, False)
    assert path.name == "Penta kill (2).mp4"
    # Its own file, rendered again, is replaced as before.
    names.remember(plan, None, False, path)
    path.write_bytes(b"this one")
    assert names.target(video_path(settings, plan), plan, None, False) == path


def test_lets_play_parts_and_shorts(settings):
    plan = plan_of("letsplay", title="Dawnwalker EP 4 Part 2: The tower", part=2)
    usual = lp.part_path(settings, plan, 4, 2)
    assert names.target(usual, plan, 2, False).name == "Dawnwalker EP 4 Part 2 The tower.mp4"
    assert names.target(lp.part_path(settings, plan, 4, 1), plan, 1, False) == \
        lp.part_path(settings, plan, 4, 1)   # part 1 has no title of its own
    short = plan_of("shorts", title="Baron steal")
    path = names.target(video_path(settings, short, captions=True), short, None, True)
    assert path.name == "Baron steal.mp4" and path.parent.name == "shorts"


def test_a_very_long_title_is_cut_at_a_word():
    name = names.clean("word " * 60)
    assert len(name) <= names.LONGEST and name.endswith("word")


@needs_ffmpeg
def test_a_title_with_an_apostrophe_renders(tmp_path):
    """24 Oct: "Well Don't Mind If I Do" stopped at 85%, measuring its loudness."""
    work = tmp_path / "Well Don't Mind If I Do (rendering)"
    work.mkdir()
    pieces = [work / f"{n:03d}.mp4" for n in range(2)]
    for piece in pieces:
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30",
                        "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1", "-shortest",
                        "-c:v", "libx264", "-c:a", "aac", str(piece)], check=True)
    listing = work / "pieces.txt"
    listing.write_text(concat_list(pieces), encoding="utf-8")
    joined = ["-f", "concat", "-safe", "0", "-i", str(listing)]
    assert measure_loudness(joined, target_lufs=-14.0, true_peak=-1.5) is not None
    out = work / "joined.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", *joined, "-c", "copy", str(out)], check=True)
    assert abs(stream_lengths(out)["video"] - 2.0) < 0.1
