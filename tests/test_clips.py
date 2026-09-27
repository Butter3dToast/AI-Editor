"""Clips with clean edges: peaks, context, scene changes, and never mid-word."""

from __future__ import annotations

import json

import numpy as np
import pytest

from ai_editor.analysis.captions import Word
from ai_editor.analysis.clips import (
    Clip,
    build_clips,
    clean_ends,
    clean_starts,
    clip_id,
    find_cores,
    fit_edges,
    store_clips,
)
from ai_editor.config import Clips
from ai_editor.db import init_db

DURATION = 600.0


def bump(seconds: int, centre: int, width: int, height: float = 1.0) -> np.ndarray:
    score = np.zeros(seconds, dtype=np.float32)
    score[centre - width:centre + width + 1] = height
    return score


def talking(start: float, end: float, *, every: float = 0.5, sentence_every: int = 8) -> list[Word]:
    """Words back to back, a full stop every few words."""
    words, t, n = [], start, 0
    while t + 0.4 <= end:
        n += 1
        words.append(Word(f"word{n}" + ("." if n % sentence_every == 0 else ""),
                          round(t, 3), round(t + 0.4, 3)))
        t = round(t + every, 3)
    return words


def inside_any_word(t: float, words: list[Word]) -> bool:
    return any(w.start < t < w.end for w in words)


# --- Peaks ---------------------------------------------------------------------


def test_a_long_fight_is_one_core_not_many_peaks():
    score = np.zeros(300, dtype=np.float32)
    score[100:160] = np.linspace(0.6, 1.0, 60)
    cores = find_cores(score, min_score=0.35, core_fraction=0.5)
    assert len(cores) == 1
    peak, value, left, right = cores[0]
    assert (left, right) == (100, 159)


def test_weak_moments_are_not_clips():
    score = bump(300, 150, 5, 0.2)
    assert find_cores(score, min_score=0.35, core_fraction=0.5) == []


def test_best_moment_first():
    score = bump(300, 50, 3, 0.5) + bump(300, 200, 3, 0.9)
    assert [c[0] for c in find_cores(score, min_score=0.35, core_fraction=0.5)][0] in range(197, 204)


# --- Edges ---------------------------------------------------------------------


def test_the_clip_starts_well_before_the_reaction():
    """The cause of laughter comes before it."""
    start, end = fit_edges((300, 305), 302, words=[], cuts=[], duration=DURATION, settings=Clips())
    assert start <= 300 - 15
    assert end >= 306


def test_never_starts_or_ends_mid_word():
    words = talking(250, 350)
    start, end = fit_edges((300, 305), 302, words=words, cuts=[], duration=DURATION,
                           settings=Clips())
    assert not inside_any_word(start, words)
    assert not inside_any_word(end, words)


def test_edges_prefer_the_end_of_a_sentence():
    words = talking(250, 350, sentence_every=6)
    sentence_ends = [w.end for w in words if w.text.endswith(".")]
    start, end = fit_edges((300, 305), 302, words=words, cuts=[], duration=DURATION,
                           settings=Clips())
    # The end lands just after some sentence's last word.
    assert min(abs(end - e) for e in sentence_ends) < 0.5


def test_a_full_stop_is_not_an_end_if_you_keep_talking():
    """League: ended on "Keep her alive." with "I..." 0.36 s later."""
    words = talking(290, 316, every=0.5, sentence_every=4)  # full stops, but no pauses
    words += talking(320, 330, every=0.5, sentence_every=100)  # after a real 4 s pause
    _, end = fit_edges((300, 305), 302, words=words, cuts=[], duration=DURATION,
                       settings=Clips(tail_sec=4))
    last_before_pause = max(w.end for w in words if w.end < 317)
    assert last_before_pause <= end <= 320.0


def test_an_end_can_run_on_to_let_a_thought_finish():
    """Up to end_extend_sec past the planned end, if that's where the pause is."""
    words = talking(290, 318.5, every=0.5, sentence_every=100)  # talking non-stop to 318.4
    _, end = fit_edges((300, 305), 302, words=words, cuts=[], duration=DURATION,
                       settings=Clips(tail_sec=4, end_extend_sec=10))
    assert end >= 318.4


def test_ending_at_a_scene_change_while_talking_is_not_clean():
    from ai_editor.analysis.clips import clean_ends

    words = [Word("still", 99.8, 100.3), Word("talking", 100.4, 100.9)]
    assert not any(abs(p - 99.95) < 0.01 for p in clean_ends(words, [100.0], pause=0.5))
    assert any(abs(p - 199.95) < 0.01 for p in clean_ends(words, [200.0], pause=0.5))


def test_a_clip_waits_for_the_fight_to_finish():
    """Wardogs: the clip ended with gunfire still coming -- the kills were after it."""
    action = np.zeros(600, dtype=np.float32)
    action[312:314] = 0.3   # bursts after the planned end (~309 s)...
    action[322:325] = 0.4
    action[331:333] = 0.3   # ...each within 10 s of the last
    _, end = fit_edges((300, 305), 302, words=[], cuts=[], duration=DURATION,
                       settings=Clips(), action=action)
    assert end >= 333


def test_a_quiet_moment_after_the_fight_ends_it():
    action = np.zeros(600, dtype=np.float32)
    action[330:333] = 0.4   # 20 s after the moment: a different fight
    _, end = fit_edges((300, 305), 302, words=[], cuts=[], duration=DURATION,
                       settings=Clips(), action=action)
    assert end < 320


def test_a_long_fight_keeps_its_end_and_starts_later():
    """The creator: "if it started a bit later ... and went till the end"."""
    action = np.zeros(600, dtype=np.float32)
    action[305:340:5] = 0.4  # shooting every 5 s, the last shot at 335
    settings = Clips(max_length_sec=50)
    start, end = fit_edges((300, 305), 302, words=[], cuts=[], duration=DURATION,
                           settings=settings, action=action)
    assert end >= 336
    assert start <= 297  # the moment itself is still in


def test_never_runs_on_into_a_menu():
    """A scene change just after the moment: stop before it."""
    start, end = fit_edges((300, 305), 302, words=[], cuts=[308.0], duration=DURATION,
                           settings=Clips())
    assert end <= 308.0


def test_never_opens_on_a_menu():
    """A scene change during the lead-in: start after it."""
    start, end = fit_edges((300, 305), 302, words=[], cuts=[290.0], duration=DURATION,
                           settings=Clips())
    assert start >= 290.0


def test_talking_across_a_scene_change_drops_the_half_word():
    """Both rules at once: after the menu, and not mid-word."""
    words = [Word("opening", 289.7, 290.4), Word("the", 290.5, 290.7), Word("menu.", 290.8, 291.2)]
    start, _ = fit_edges((300, 305), 302, words=words, cuts=[290.0], duration=DURATION,
                         settings=Clips())
    assert start >= 290.0
    assert not inside_any_word(start, words)

    words = [Word("look", 307.6, 308.3)]
    _, end = fit_edges((300, 305), 302, words=words, cuts=[308.0], duration=DURATION,
                       settings=Clips())
    assert end <= 308.0
    assert not inside_any_word(end, words)


def test_non_stop_talking_is_cut_where_two_words_meet():
    """No gap to step into: the join between two words is the clean point."""
    words, t = [], 250.0
    while t < 350:
        words.append(Word("go", round(t, 3), round(t + 0.3, 3)))
        t = round(t + 0.3, 3)
    start, end = fit_edges((300, 305), 302, words=words, cuts=[], duration=DURATION,
                           settings=Clips(snap_sec=0))
    assert not inside_any_word(start, words)
    assert not inside_any_word(end, words)


def test_a_stretched_word_is_judged_by_its_end():
    """Whisper once said "don't" lasted 12 seconds; the word is at the end."""
    from ai_editor.analysis.clips import realistic

    (word,) = realistic([Word("don't", 4999.26, 5011.34)])
    assert word.end == 5011.34
    assert word.end - word.start == pytest.approx(0.8)  # 0.3 s + 0.1 s a letter


def test_short_words_get_short_lengths():
    """"hit" reported as 1.9 s made its caption appear before it was said."""
    from ai_editor.analysis.clips import realistic

    hit, long_word = realistic([Word("hit", 10.0, 11.92), Word("unbelievably", 20.0, 23.0)])
    assert hit.end - hit.start == pytest.approx(0.6)
    assert long_word.end - long_word.start == pytest.approx(1.5)  # never more


def test_cutscene_camera_cuts_do_not_chop_the_build_up():
    """Dawnwalker's cutscenes cut every few seconds; those aren't menus."""
    cuts = [float(t) for t in range(250, 320, 5)]  # a camera cut every 5 s
    start, _ = fit_edges((300, 305), 302, words=[], cuts=cuts, duration=DURATION,
                         settings=Clips())
    assert start <= 285


def test_a_lone_menu_still_stops_the_clip():
    from ai_editor.analysis.clips import walls

    cuts = [100.0, 290.0, 500.0] + [float(t) for t in range(700, 760, 5)]
    hard = walls(cuts, busy_count=3, window=30)
    assert 290.0 in hard and 100.0 in hard
    assert not any(700 <= c < 760 for c in hard)


def test_getting_downed_mid_fight_does_not_cut_off_the_fight():
    """A scene change with action before it isn't a menu: keep the lead-in."""
    score = np.zeros(600, dtype=np.float32)
    score[280:310] = 0.8          # the fight, then the death at 298
    start, end = fit_edges((299, 305), 302, words=[], cuts=[298.0], duration=DURATION,
                           settings=Clips(), score=score)
    assert start < 290


def test_a_quiet_menu_before_the_moment_still_stops_the_lead_in():
    score = np.zeros(600, dtype=np.float32)
    score[299:310] = 0.8          # nothing before the menu closes at 298
    start, _ = fit_edges((299, 305), 302, words=[], cuts=[298.0], duration=DURATION,
                         settings=Clips(), score=score)
    assert start >= 298.0


def test_a_scene_change_inside_the_moment_is_left_alone():
    start, end = fit_edges((300, 320), 310, words=[], cuts=[310.0], duration=DURATION,
                           settings=Clips())
    assert start < 300 and end > 320


def test_length_limits():
    settings = Clips(min_length_sec=15, max_length_sec=60)
    short_start, short_end = fit_edges((300, 300), 300, words=[], cuts=[295.0, 303.0],
                                       duration=DURATION, settings=settings)
    assert short_end - short_start < 15  # boxed in by two scene changes: allowed to be short

    long_start, long_end = fit_edges((100, 400), 250, words=[], cuts=[], duration=DURATION,
                                     settings=settings)
    assert long_end - long_start == pytest.approx(60, abs=settings.snap_sec)
    assert long_start < 250 < long_end  # still around the peak


def test_the_recording_edges_are_respected():
    start, end = fit_edges((2, 5), 3, words=[], cuts=[], duration=10.0, settings=Clips())
    assert start == 0.0 and end <= 10.0


def test_clean_points_include_pauses_and_scene_changes():
    words = [Word("hello", 10.0, 10.4), Word("there.", 10.5, 10.9), Word("next", 13.0, 13.4)]
    assert any(abs(p - 13.0) < 0.2 for p in clean_starts(words, [], pause=0.5))
    assert any(abs(p - 10.9) < 0.3 for p in clean_ends(words, [], pause=0.5))
    assert 20.05 in clean_starts(words, [20.0], pause=0.5)


# --- Whole recordings ------------------------------------------------------------


def test_two_peaks_close_together_become_one_clip():
    score = bump(600, 300, 3, 0.9) + bump(600, 312, 3, 0.8)
    clips = build_clips(score, words=[], cuts=[], duration=DURATION, settings=Clips())
    assert len(clips) == 1


def test_far_apart_moments_are_separate_clips():
    score = bump(600, 100, 3, 0.9) + bump(600, 400, 3, 0.8)
    clips = build_clips(score, words=[], cuts=[], duration=DURATION, settings=Clips())
    assert len(clips) == 2
    assert clips[0].start < clips[1].start  # time order


def test_clips_never_overlap():
    rng = np.random.default_rng(3)
    score = np.convolve(rng.random(3000), np.ones(10) / 10, mode="same").astype(np.float32)
    score /= score.max()
    words = talking(0, 3000, every=0.6)
    clips = build_clips(score, words=words, cuts=[500.0, 1200.0], duration=3000.0,
                        settings=Clips(min_score=0.6))
    for a, b in zip(clips, clips[1:]):
        assert a.end <= b.start
    for clip in clips:
        assert not inside_any_word(clip.start, words)
        assert not inside_any_word(clip.end, words)


# --- The library -----------------------------------------------------------------


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    connection.execute(
        "INSERT INTO recordings (id, content_hash, source_type, source_file, duration_sec, "
        "imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 600, '2026-09-26T12:00:00')"
    )
    connection.commit()
    yield connection
    connection.close()


def test_stored_with_what_was_said_and_why(conn):
    words = [Word("what", 101.0, 101.3), Word("a", 101.4, 101.5), Word("shot!", 101.6, 102.0)]
    clip = Clip(100.0, 130.0, 110, 0.9, (105, 115), reasons=[("laughter", 2.0)])
    signals = {"laughter": np.full(600, 0.0, dtype=np.float32)}
    signals["laughter"][110] = 0.8
    store_clips(conn, 1, [clip], signals=signals, words=words)
    row = conn.execute("SELECT * FROM clips").fetchone()
    assert row["transcript"] == "what a shot!"
    assert json.loads(row["signals_json"])["laughter"] == pytest.approx(0.8)
    assert json.loads(row["signals_json"])["reasons"] == ["laughter"]
    assert row["clip_id"] == clip_id(1, 100.0)


def test_rebuilding_replaces_clips_but_keeps_ones_you_rated(conn):
    first = [Clip(100.0, 130.0, 110, 0.9, (105, 115)), Clip(300.0, 330.0, 310, 0.7, (305, 315))]
    store_clips(conn, 1, first, signals={}, words=[])
    conn.execute("UPDATE clips SET user_rating = 1 WHERE start_sec = 300")
    conn.commit()

    store_clips(conn, 1, [Clip(400.0, 430.0, 410, 0.8, (405, 415))], signals={}, words=[])
    starts = sorted(r[0] for r in conn.execute("SELECT start_sec FROM clips"))
    assert starts == [300.0, 400.0]


def test_a_clip_never_opens_on_or_runs_into_a_black_screen():
    dark = np.zeros(600, dtype=bool)
    dark[270:285] = True   # loading before the moment
    dark[309:320] = True   # respawn screen after it
    start, end = fit_edges((300, 305), 302, words=[], cuts=[], duration=DURATION,
                           settings=Clips(), dark=dark)
    assert start >= 285
    assert end <= 309


def test_a_fight_too_long_to_keep_whole_keeps_its_end():
    """The same Wardogs clip, reviewed twice: "take a later version of that clip
    ... you would hear me saying I killed someone". The moment ran 55 s, the
    video's clips are 50 s at most, and the old trim kept the walk in."""
    action = np.zeros(600, dtype=np.float32)
    action[[262, 280, 296, 301, 306, 312]] = 0.5   # shooting through to the end of the moment
    settings = Clips(max_length_sec=50, lead_in_sec=15)
    start, end = fit_edges((260, 314), 290, words=[], cuts=[], duration=DURATION,
                           settings=settings, action=action)
    assert end >= 314          # the payoff at the end is in
    assert end - start <= 50
    assert start <= 290        # and the moment itself


def test_a_long_moment_without_a_fight_keeps_its_build_up():
    """A joke then a laugh: the cause comes first, so trimming takes from the end."""
    settings = Clips(max_length_sec=50, lead_in_sec=15)
    start, end = fit_edges((260, 314), 290, words=[], cuts=[], duration=DURATION, settings=settings)
    assert start < 260


def test_a_clip_does_not_open_mid_sentence():
    """The helicopter clip opened on "Chris, you ready for some fun" -- the
    start fell in the short pause after "Hey"."""
    words = [Word("Hey", 283.1, 283.7), Word("Chris,", 285.0, 285.6), Word("you", 285.7, 285.8),
             Word("ready", 285.8, 285.9), Word("for", 285.9, 286.2), Word("some", 286.2, 286.9),
             Word("fun.", 286.9, 287.2)]
    start, _ = fit_edges((300, 305), 302, words=words, cuts=[], duration=DURATION,
                         settings=Clips(lead_in_sec=15))
    assert start <= 283.1


def test_stepping_back_stops_at_a_full_stop():
    from ai_editor.analysis.clips import phrase_start

    words = [Word("Done.", 10.0, 10.4), Word("Hey", 10.8, 11.1), Word("Chris", 11.9, 12.3)]
    assert 10.4 <= phrase_start(11.5, words, low=0, reach=6) <= 10.8
