"""Style profiles: measuring reference videos and keeping profiles (Phase 2G-1)."""

from __future__ import annotations

import numpy as np
import pytest

from ai_editor.db import init_db
from ai_editor.style import measure as M
from ai_editor.style import profiles
from ai_editor.style.measure import Measured, TextBox, ZoomStep
from ai_editor.style.profiles import ProfileProblem


def measured(**kw) -> Measured:
    base = dict(duration_sec=600.0, measured_sec=600.0, portrait=False, cuts_per_min=2.0,
                shot_sec=20.0, speech_share=0.4, dead_air_sec=6.0, zooms_per_min=1.0,
                zoom_strength=0.2, sfx_per_min=0.5)
    return Measured(**{**base, **kw})


# --- Cuts, silence, the teaser ---------------------------------------------------------


def test_shots_and_the_teaser():
    assert M.shots([10.0, 25.0], 40.0) == [10.0, 15.0, 15.0]
    assert M.hook([1.0, 8.4, 30.0]) == 8.4          # the first cut after 2 s
    assert M.hook([40.0]) is None                   # not in the first 25 s: no teaser


def test_dead_air_is_the_long_end_of_the_gaps_between_talking():
    speech = [(i * 10.0, i * 10.0 + 8.0) for i in range(30)]   # 2 s gaps
    speech[10] = (100.0, 101.0)                                 # one 9 s gap
    assert M.dead_air(speech, 300.0) == pytest.approx(2.0)
    assert M.dead_air([(0.0, 5.0)], 300.0) is None              # hardly anyone talks


def _texture(seed=0, h=180, w=320) -> np.ndarray:
    rng = np.random.default_rng(seed)
    small = rng.uniform(0, 255, (h // 10, w // 10)).astype(np.float32)
    import cv2

    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)


def test_a_cut_is_an_edit_only_if_the_still_parts_dont_carry_on():
    a = _texture(1)
    after_menu = a.copy()
    after_menu[40:140, 80:240] = 255 - after_menu[40:140, 80:240]   # a menu opens in the middle
    elsewhere = _texture(2)                                          # another moment entirely
    assert M.carried_on(a, a, after_menu) > 0.6
    assert M.carried_on(a, a, elsewhere) < 0.2
    carried = [1.0, 1.0, M.carried_on(a, a, after_menu), 1.0, M.carried_on(a, a, elsewhere), 1.0]
    # Cuts found at frames 2 (the menu) and 4 (an edit), at 6 frames a second.
    assert M.edits([2 / 6, 4 / 6], carried, 6) == [pytest.approx(4 / 6)]


# --- Zooms --------------------------------------------------------------------------------


def test_a_punch_in_matches_the_frame_before_blown_up():
    a = _texture(3)
    zoomed = M._grown(a, 1.25)
    step = M.zoom_step(a, zoomed)
    assert step.grow_in == pytest.approx(1.25) and step.zoomed("in") == pytest.approx(1.25)
    # The camera panning is not a zoom.
    panned = np.roll(a, 12, axis=1)
    assert M.zoom_step(a, panned).zoomed("in") == 1.0
    # A different picture altogether isn't either.
    assert M.zoom_step(a, _texture(4)).zoomed("in") == 1.0


def _steps(zooms: dict[int, tuple[str, float]], n: int = 60) -> list[ZoomStep]:
    out = []
    for i in range(n):
        way, g = zooms.get(i, ("", 1.0))
        out.append(ZoomStep(g if way == "in" else 1.0, 0.5 if way == "in" else 9.0,
                            g if way == "out" else 1.0, 0.5 if way == "out" else 9.0, 10.0))
    return out


def test_zoom_events_count_a_punch_in_and_its_way_back_once():
    # In at frame 11 (2 s at 6 a second), back out 1 s later; another in at 41, held.
    steps = _steps({11: ("in", 1.25), 17: ("out", 1.25), 41: ("in", 1.2)})
    assert M.zoom_events(steps, 6) == [(2.0, 0.25), (7.0, 0.2)]
    # A slow zoom over three frames counts once, by how far it went in all.
    slow = _steps({20: ("in", 1.06), 21: ("in", 1.06), 22: ("in", 1.06)})
    assert M.zoom_events(slow, 6) == [(3.5, pytest.approx(0.19, abs=0.01))]
    # One small step alone isn't a zoom.
    assert M.zoom_events(_steps({20: ("in", 1.03)}), 6) == []


# --- Sound effects -------------------------------------------------------------------------


def test_meme_sounds_are_counted_when_they_jump_up():
    whoosh = np.zeros(20)
    whoosh[[3, 4, 10, 11, 12]] = 0.6     # two whooshes (3-4 and 10-12)
    ding = np.zeros(20)
    ding[15] = 0.3
    assert M.sfx_events({"whoosh": whoosh, "ding": ding}) == [(3.0, "whoosh"), (10.0, "whoosh"),
                                                              (15.0, "ding")]
    assert "boom" not in M.SFX_GROUPS    # can't be told from a game's own sounds


# --- Captions --------------------------------------------------------------------------------


def _box(t, text, x=0.5, bottom=0.88, height=0.07):
    return TextBox(t, text, x, bottom - height, bottom, height)


def test_captions_are_big_changing_text_in_the_middle():
    looks = []
    for i in range(20):
        t = i * 2.0
        look = [_box(t, f"word{i} and more", height=0.07),       # a caption, changing
                _box(t, "Butter3dToast1996", x=0.06, bottom=0.12, height=0.03),  # an overlay
                _box(t, "SHOP", x=0.5, bottom=0.4, height=0.05)]  # big, but always there
        looks.append(look)
    found = M.captions(looks, lambda t: True)
    assert found["caption_share"] == 1.0
    assert found["caption_size"] == pytest.approx(0.07)
    assert found["caption_position"] == pytest.approx(0.12)
    assert found["caption_words"] == 3.0


def test_a_games_own_text_and_menus_are_not_captions():
    small = [[_box(i * 2.0, f"Enemy slain {i}", height=0.03)] for i in range(10)]
    assert M.captions(small, lambda t: True)["caption_share"] == 0.0
    menu = [[_box(0.0, f"Item {k} name", x=0.3 + k * 0.03, bottom=0.2 + k * 0.06, height=0.045)
             for k in range(9)]]
    assert M.captions(menu * 3, lambda t: True)["caption_share"] == 0.0
    numbers = [[_box(i * 2.0, f"{1000 + i}/{i} 25%", height=0.06)] for i in range(10)]
    assert M.captions(numbers, lambda t: True)["caption_share"] == 0.0


# --- Where the AI looks ----------------------------------------------------------------------


def test_the_ai_looks_where_things_happen_and_through_the_rest():
    from ai_editor.style.references import frame_times

    times = frame_times(measured(measured_sec=90.0, moments=[12.0, 40.0]), count=6)
    assert len(times) == 6 and 12.3 in times and 40.3 in times
    assert all(0 < t < 90 for t in times)


# --- Profiles in the library -------------------------------------------------------------------


@pytest.fixture
def conn(settings):
    c = init_db(settings.db_path)
    yield c
    c.close()


def test_profiles_are_created_renamed_and_deleted(conn):
    pid = profiles.create(conn, "  League   Highlights ")
    assert profiles.names(conn) == [("League Highlights", pid)]
    with pytest.raises(ProfileProblem, match="already"):
        profiles.create(conn, "league highlights")
    with pytest.raises(ProfileProblem):
        profiles.create(conn, "  ")
    profiles.rename(conn, pid, "League Shorts")
    assert profiles.load(conn, pid).name == "League Shorts"
    profiles.add_reference(conn, pid, "https://www.youtube.com/watch?v=abc")
    profiles.delete(conn, pid)
    assert profiles.load(conn, pid) is None
    assert conn.execute("SELECT count(*) FROM style_references").fetchone()[0] == 0


def test_references_are_links_or_video_files(conn, tmp_path):
    pid = profiles.create(conn, "P")
    video = tmp_path / "mine.mp4"
    video.write_bytes(b"x")
    assert profiles.add_reference(conn, pid, "https://youtu.be/abc") == "https://youtu.be/abc"
    assert profiles.add_reference(conn, pid, f'"{video}"') == "mine.mp4"
    with pytest.raises(ProfileProblem, match="already"):
        profiles.add_reference(conn, pid, str(video))
    with pytest.raises(ProfileProblem, match="Can't find"):
        profiles.add_reference(conn, pid, str(tmp_path / "gone.mp4"))
    notes = tmp_path / "notes.txt"
    notes.write_text("hi")
    with pytest.raises(ProfileProblem, match="doesn't look like a video"):
        profiles.add_reference(conn, pid, str(notes))
    refs = profiles.load(conn, pid).references
    assert [r.is_link for r in refs] == [True, False]
    profiles.remove_reference(conn, refs[1].id)
    assert video.exists()     # only off the list: the file itself is never touched


def test_the_sliders_start_from_the_references_then_keep_what_was_saved(conn, settings):
    pid = profiles.create(conn, "P")
    # Nothing measured: the creator's own settings.
    empty = profiles.load(conn, pid).current(settings)
    assert empty["zoom_strength"] == settings.effects.zoom_strength
    assert empty["caption_words"] == settings.captions.shorts_words
    for n, (cuts, captions) in enumerate([(10.0, 0.05), (14.0, None), (12.0, 0.07)]):
        profiles.add_reference(conn, pid, f"https://youtu.be/{n}")
        ref = profiles.load(conn, pid).references[-1]
        profiles.store_measured(conn, ref.id, title=f"Video {n}",
                                measured=measured(cuts_per_min=cuts, caption_size=captions))
    draft = profiles.load(conn, pid).current(settings)
    assert draft["cuts_per_min"] == 12.0              # the middle one
    assert draft["caption_size"] == pytest.approx(6.0)   # % of the height; one couldn't tell
    profiles.save(conn, pid, games=["League of Legends"], recipes=["highlights"],
                  values={**draft, "cuts_per_min": 99, "zooms_per_min": 2.04})
    saved = profiles.load(conn, pid)
    assert saved.values["cuts_per_min"] == 30          # kept within the slider
    assert saved.values["zooms_per_min"] == 2.0
    assert saved.current(settings)["cuts_per_min"] == 30
    assert saved.draft(settings)["cuts_per_min"] == 12.0   # "back to the measured values"
    assert saved.games == ["League of Legends"] and saved.recipes == ["highlights"]


def test_a_references_working_folder_is_only_ever_deleted_inside_the_cache(settings):
    from ai_editor.style.references import tidy, working_folder

    folder = working_folder(settings, 7)
    (folder / "work").mkdir(parents=True)
    (folder / "reference.mp4").write_bytes(b"x")
    tidy(folder, settings)
    assert not folder.exists()
    raw = settings.folders.raw / "stream.mkv"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(b"a stream")
    for target in (settings.folders.raw, raw.parent, settings.folders.cache,
                   settings.folders.cache / "style"):
        with pytest.raises(ValueError):
            tidy(target, settings)
    assert raw.exists()


def test_the_job_measures_each_reference_and_keeps_going_past_a_bad_one(conn, settings,
                                                                        monkeypatch):
    from ai_editor.app import tasks
    from ai_editor.style import references

    pid = profiles.create(conn, "P")
    for link in ("https://youtu.be/good", "https://youtu.be/bad"):
        profiles.add_reference(conn, pid, link)

    def fake(settings_, ref, on_progress):
        on_progress("Finding the cuts", 1.0)
        if "bad" in ref.source:
            raise references.ReferenceProblem("Couldn't download it: private video.")
        return references.Result("A good one", measured(cuts_per_min=9.0), [])

    monkeypatch.setattr(references, "analyse", fake)
    said = []

    class Report:
        def progress(self, label, f):
            pass

        def say(self, text):
            said.append(text)

        def keep(self, **kw):
            said.append(kw)

    tasks.analyse_references(settings, pid)(Report())
    refs = profiles.load(conn, pid).references
    assert refs[0].measured.cuts_per_min == 9.0 and refs[0].title == "A good one"
    assert refs[1].measured is None and "private video" in refs[1].error
    assert {"style_profile": pid} in said
    # Again: only what isn't measured yet.
    said.clear()
    tasks.analyse_references(settings, pid)(Report())
    assert sum("private video" in str(s) for s in said) == 1


def test_the_ai_is_told_what_was_measured_and_kept_to_a_few_notes(settings, monkeypatch):
    from ai_editor import llm
    from ai_editor.style import notes

    asked = []

    def fake_ask(settings_, system, prompt, *, schema, images=None, **kw):
        asked.append((prompt, schema, len(images or [])))
        return {"techniques": ["Meme image pops up.", "meme image pops up", "Facecam bottom-left"]}

    monkeypatch.setattr(llm, "ask", fake_ask)
    got = notes.look(settings, [b"jpg"] * 6, measured(cuts_per_min=12.5, zooms_per_min=0.0))
    assert got == ["Meme image pops up", "Facecam bottom-left"]       # the same note once
    assert [n for _, _, n in asked] == [4, 2]                         # a few frames at a time
    prompt, schema, _ = asked[0]
    assert "12.5 cuts a minute, 0 zooms a minute" in prompt and "don't list cuts" in prompt
    assert schema["properties"]["techniques"]["maxItems"] == notes.PER_LOOK
