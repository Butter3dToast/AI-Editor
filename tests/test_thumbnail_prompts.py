"""Thumbnail prompts (3D): written by the local AI for the creator to paste into
the Gemini app with the frame, under their own subscription. Nothing is sent
online. Highlights stay clean; Let's Play parts say their episode and part."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ai_editor import llm, publish
from ai_editor.config import SettingsInvalid, save_local_settings
from ai_editor.db import init_db
from ai_editor.recipes.plan import EditPlan, Segment, load_plan, save_plan

ANSWER = {"subject": "Jinx firing her rocket launcher into the enemy team.",
          "boost": "Crop in on Jinx, brighten the explosion, add a glow around the rocket."}


def plan_of(recipe: str, game: str = "League of Legends") -> EditPlan:
    part = 2 if recipe == "letsplay" else None
    return EditPlan(f"{recipe}_x_1", recipe, "A video", game, 600,
                    [Segment(1, 0, 300, part=part)])


def frames(tmp_path: Path, count: int) -> list[publish.Thumbnail]:
    found = []
    for n in range(count):
        path = tmp_path / f"thumbnail {n + 1}.png"
        path.write_bytes(b"png")
        found.append(publish.Thumbnail(path, 9 - n, "sharp"))
    return found


@pytest.fixture
def asked(monkeypatch):
    seen = []

    def fake_ask(settings_, system, prompt, *, schema, images=None, **_):
        seen.append({"system": system, "prompt": prompt, "images": images})
        return dict(ANSWER)

    monkeypatch.setattr(llm, "ask", fake_ask)
    return seen


def test_a_highlight_prompt_has_no_text_on_the_picture(settings, tmp_path, asked):
    thumbs = publish.thumbnail_prompts(settings, plan_of("highlights"), frames(tmp_path, 2),
                                       part=None, episode=None, title="League Highlights",
                                       chapters=["Baron steal"])
    prompt = thumbs[0].prompt
    assert prompt.startswith("Turn the attached screenshot from League of Legends into a "
                             "YouTube thumbnail, 16:9 (1280x720).")
    assert ANSWER["subject"] in prompt and ANSWER["boost"] in prompt
    assert "Don't add any text." in prompt and "Add the text" not in prompt
    assert "Don't add people, faces" in prompt          # no facecam
    assert asked[0]["images"] == [b"png"]                # the AI looked at the frame itself


def test_a_lets_play_prompt_says_its_episode_and_part(settings, tmp_path, asked):
    thumbs = publish.thumbnail_prompts(settings, plan_of("letsplay", "The Blood of Dawnwalker"),
                                       frames(tmp_path, 1), part=2, episode=6, title="EP 6",
                                       chapters=[])
    assert 'Add the text "EP 6 PART 2" in big, bold letters' in thumbs[0].prompt
    assert "must not give away twists" in asked[0]["prompt"]   # a story game: no spoilers


def test_the_lets_play_text_and_your_look_are_yours(settings, tmp_path, asked):
    settings.publish.thumbnail_text = "{game} EP {episode}"
    settings.publish.thumbnail_style = "bold yellow text, purple glow"
    lp = publish.thumbnail_prompts(settings, plan_of("letsplay", "Crimson Desert"),
                                   frames(tmp_path, 1), part=1, episode=3, title="t",
                                   chapters=[])[0].prompt
    assert '"Crimson Desert EP 3"' in lp and lp.count("Style: bold yellow text, purple glow") == 1
    settings.publish.thumbnail_text = ""
    lp = publish.thumbnail_prompts(settings, plan_of("letsplay"), frames(tmp_path, 1), part=1,
                                   episode=3, title="t", chapters=[])[0].prompt
    assert "Don't add any text." in lp


def test_only_the_best_frames_get_one_and_shorts_none(settings, tmp_path, asked):
    thumbs = frames(tmp_path, 6)
    thumbs[1].path.unlink()                              # you deleted that one
    publish.thumbnail_prompts(settings, plan_of("highlights"), thumbs, part=None, episode=None,
                              title="t", chapters=[])
    assert [bool(t.prompt) for t in thumbs] == [True, False, True, True, True, True]
    assert len(asked) == publish.PROMPTS
    asked.clear()
    short = publish.thumbnail_prompts(settings, plan_of("shorts"), frames(tmp_path, 2),
                                      part=None, episode=None, title="t", chapters=[])
    assert not asked and not any(t.prompt for t in short)


def test_a_frame_the_ai_cant_read_is_left_without(settings, tmp_path, monkeypatch):
    def unreadable(*a, **k):
        raise llm.AiAnswerUnreadable("nonsense")

    monkeypatch.setattr(llm, "ask", unreadable)
    thumbs = publish.thumbnail_prompts(settings, plan_of("highlights"), frames(tmp_path, 2),
                                       part=None, episode=None, title="t", chapters=[])
    assert not any(t.prompt for t in thumbs)


def test_prompts_are_kept_with_the_plan(settings, tmp_path):
    text = publish.Publish(["t"], "d", ["x"], [(0.0, "Intro")],
                           [publish.Thumbnail(tmp_path / "a.png", 8, "r", "the prompt")],
                           "f", "now")
    assert publish.Publish.from_dict(text.as_dict()).thumbnails[0].prompt == "the prompt"
    old = text.as_dict()
    del old["thumbnails"][0]["prompt"]                  # written before 3D
    assert publish.Publish.from_dict(old).thumbnails[0].prompt == ""


def test_write_prompts_for_frames_already_picked(settings, tmp_path, asked, monkeypatch):
    from ai_editor.app import tasks

    monkeypatch.setattr(llm, "start", lambda s: "x")
    monkeypatch.setattr(llm, "has_model", lambda s, name=None: True)
    monkeypatch.setattr(llm, "unload", lambda s: None)
    conn = init_db(settings.db_path)
    plan = plan_of("highlights")
    plan.publish[publish.key_of(None)] = publish.Publish(
        ["League Highlights"], "d", [], [(0.0, "Baron steal")], frames(tmp_path, 2), "f",
        "now").as_dict()
    save_plan(conn, plan)

    class Report:
        def __init__(self):
            self.lines, self.kept = [], {}

        def progress(self, *a):
            pass

        def say(self, text):
            self.lines.append(text)

        def keep(self, **k):
            self.kept.update(k)

    report = Report()
    tasks.write_prompts(settings, plan.plan_id)(report)
    saved = publish.saved(load_plan(conn, plan.plan_id)[0], None)
    assert all(t.prompt for t in saved.thumbnails) and report.kept == {"prompts": plan.plan_id}
    assert "League Highlights" in asked[0]["prompt"] and "Baron steal" in asked[0]["prompt"]
    conn.close()


def test_the_lets_play_text_setting_is_checked(settings):
    with pytest.raises(SettingsInvalid):
        save_local_settings(settings.source_path, {("publish", "thumbnail_text"): "EP {ep}"})


def test_nothing_is_sent_online():
    """No Gemini API: the creator pastes the prompt into the app themselves (31 Oct)."""
    source = Path(publish.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(urllib|http|requests|httpx|socket)\b", source,
                         re.MULTILINE)
    assert "googleapis" not in source and "generativelanguage" not in source
