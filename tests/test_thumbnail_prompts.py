"""Thumbnail prompts (3D): written by the local AI for the creator to paste into
the Gemini app with the frame, under their own subscription. Nothing is sent
online. Highlights stay clean; Let's Play parts say their episode and part."""

from __future__ import annotations

import json
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


IDEAS = {"ideas": ["Gwen leaping into a teamfight in the jungle at night.",
                   "Gwen holding the Baron pit alone, snips flying.",
                   "Gwen turning a fight under her own tower."]}


@pytest.fixture
def ideas_asked(monkeypatch):
    seen = []

    def fake_ask(settings_, system, prompt, *, schema, images=None, **_):
        seen.append({"system": system, "prompt": prompt, "images": images, "schema": schema})
        return dict(IDEAS)

    monkeypatch.setattr(llm, "ask", fake_ask)
    return seen


def test_a_highlight_gets_three_ideas_about_the_whole_video(settings, ideas_asked):
    """1 Nov: prompts made from single frames had Gemini redraw the creator's League
    champions, or add what wasn't there. A highlight video now gets three ideas about the
    whole video, featuring the champion played, and no frame is needed."""
    conn = init_db(settings.db_path)
    plan = EditPlan("highlights_streams_1", "highlights", "Stream highlights", None, 600,
                    [Segment(1, 0, 60, game="League of Legends"),
                     Segment(2, 0, 30, game="League of Legends"), Segment(3, 0, 30, game="Wardogs")],
                    source={"thumbnail_who": "Gwen"})
    found = publish.video_prompts(conn, settings, plan, title="Teamfights and Rank Grind",
                                  chapters=["Baron steal", "Turret dive"])
    assert len(found) == 3 and ideas_asked[0]["images"] is None        # no frame to redraw
    first = found[0]
    assert first.startswith('Make a YouTube thumbnail, 16:9 (1280x720), for my League of '
                            'Legends highlights video: "Teamfights and Rank Grind".')
    assert "Feature Gwen, the champion I played, big and in front, in the official League of " \
           "Legends splash-art style." in first                    # the game most clips are from
    assert "The scene: Gwen leaping into a teamfight in the jungle at night." in first
    assert "If a screenshot is attached, use it only for my champion's skin" in first
    assert "Don't add any text." in first and "Don't add real people, faces" in first
    question = ideas_asked[0]["prompt"]
    assert "The creator played Gwen." in question and "Baron steal; Turret dive" in question
    # Nobody known: "my champion", and the local AI is told so.
    plan.source = {}
    found = publish.video_prompts(conn, settings, plan, title="t", chapters=[])
    assert "Feature my champion, big and in front" in found[0]
    assert "isn't known" in ideas_asked[1]["prompt"]
    # A frame-by-frame prompt is for Let's Play parts only; Shorts get neither.
    assert publish.thumbnail_prompts(settings, plan, [], part=None, episode=None, title="t",
                                     chapters=[]) == []
    assert publish.video_prompts(conn, settings, plan_of("letsplay"), title="t", chapters=[]) == []
    conn.close()


def test_who_you_played_comes_from_leagues_own_data(settings):
    """League's game data says which champion is yours: the Companion now logs it with each
    event, and a highlight's thumbnail features the one you played most."""
    from ai_editor.companion import league

    match = league.match_of({
        "gameData": {"gameTime": 300.0}, "events": {"Events": []},
        "activePlayer": {"riotId": "Butter3dToast#EUW"},
        "allPlayers": [{"riotId": "Butter3dToast#EUW", "championName": "Gwen", "team": "ORDER"},
                       {"riotId": "Someone#1", "championName": "Aatrox", "team": "CHAOS"}]})
    assert match.my_champion == "Gwen"
    said = league.describe({"EventName": "ChampionKill", "EventID": 3, "EventTime": 250.0,
                            "KillerName": "Butter3dToast", "VictimName": "Someone"}, match)
    assert said["played"] == "Gwen"
    conn = init_db(settings.db_path)
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                 "imported_at) VALUES (1, 'h', 'local_obs', 'x.mkv', 'now')")
    for champion in ["Gwen", "Gwen", "Jinx", None]:
        payload = {"kind": "kill"} | ({"played": champion} if champion else {})
        conn.execute("INSERT INTO companion_events (session_id, event_type, wall_clock, "
                     "payload_json, recording_id) VALUES ('s', 'league', 'now', ?, 1)",
                     (json.dumps(payload),))
    plan = EditPlan("highlights_x_1", "highlights", "t", "League of Legends", 600,
                    [Segment(1, 0, 60)])
    assert publish.thumbnail_who(conn, plan) == ("Gwen and Jinx", "league")
    plan.source = {"thumbnail_who": "Gwen"}
    assert publish.thumbnail_who(conn, plan) == ("Gwen", "typed")      # yours wins
    plan.segments = [Segment(2, 0, 60)]
    plan.source = {}
    assert publish.thumbnail_who(conn, plan) == ("", "")                # before this update
    conn.close()


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
    publish.thumbnail_prompts(settings, plan_of("letsplay"), thumbs, part=2, episode=6,
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
    thumbs = publish.thumbnail_prompts(settings, plan_of("letsplay"), frames(tmp_path, 2),
                                       part=2, episode=6, title="t", chapters=[])
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
    plan = plan_of("letsplay")
    plan.publish[publish.key_of(2)] = publish.Publish(
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
    tasks.write_prompts(settings, plan.plan_id, episode=6)(report)
    saved = publish.saved(load_plan(conn, plan.plan_id)[0], 2)
    assert all(t.prompt for t in saved.thumbnails) and report.kept == {"prompts": plan.plan_id}
    assert "League Highlights" in asked[0]["prompt"] and "Baron steal" in asked[0]["prompt"]
    # A highlight video's ideas, written again: no frames needed.
    monkeypatch.setattr(llm, "ask", lambda *a, **k: {"ideas": ["One.", "Two.", "Three."]})
    video = plan_of("highlights")
    video.publish[publish.key_of(None)] = publish.Publish(
        ["League Highlights"], "d", [], [], [], "f", "now").as_dict()
    save_plan(conn, video)
    tasks.write_prompts(settings, video.plan_id)(report)
    saved = publish.saved(load_plan(conn, video.plan_id)[0], None)
    assert [p.split("The scene: ")[1].splitlines()[0] for p in saved.prompts] == [
        "One.", "Two.", "Three."]
    assert report.lines[-1] == "3 thumbnail ideas. They're in Review, under Publish."
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
