"""Reading Dawnwalker's quest tracker for story missions (Phase 2F-1).

The rows below are real reads of the creator's 10 Oct episode (recording 15),
noise and all.
"""

from __future__ import annotations

from ai_editor.analysis import quests
from ai_editor.analysis.quests import Sighting
from ai_editor.db import init_db


def box(y, x=0.0, h=10.0):
    return [(x, y - h / 2), (x + 50, y - h / 2), (x + 50, y + h / 2), (x, y + h / 2)]


def test_a_row_read_in_two_pieces_is_one_row_again():
    rows = quests.rows_of([box(10), box(30), box(52, x=60), box(50, x=0), box(70)],
                          ["Afternoon", "The Blood of Dawnwalker", "Lies", "Where Loyalty",
                           "Search the attic"])
    assert rows == ["Afternoon", "The Blood of Dawnwalker", "Where Loyalty Lies", "Search the attic"]


def test_the_time_of_day_quest_and_step_are_found_by_where_they_sit():
    s = quests.parse(["Aftemoon", "The Blood of Dawnwalker", "Rescue your family • 12 days left",
                      "Where Loyalty Lies", "Find out what happened to the"], 970.0)
    assert (s.time_of_day, s.quest, s.step) == ("Afternoon", "Where Loyalty Lies",
                                                "Find out what happened to the")
    # Nothing legible (a cutscene): no quest, not a guess.
    assert quests.parse(["37", "After"], 1105.0).quest is None


def look(t, quest, tod="Afternoon"):
    return Sighting(t, tod, quest, None)


def test_missions_allow_for_misreadings():
    seen = ([look(t, "Where Loyalty Lies") for t in range(0, 300, 10)]
            + [look(300, "Where Loyalty Lles"), look(310, "What Moves the Dead")]   # misread, lone
            + [look(t, "Where Loyalty Lies") for t in range(320, 600, 10)]
            + [look(t, "What Moves the Dead", "Morning") for t in range(700, 900, 10)])
    found = quests.missions(seen, every=10.0)
    assert [(m.name, m.start, m.end) for m in found] == [("Where Loyalty Lies", 0, 600),
                                                         ("What Moves the Dead", 700, 900)]
    assert quests.day_changes(seen) == [700]


def test_a_noisy_time_of_day_isnt_a_change():
    seen = [look(0, None, "Noon"), look(10, None, "Noon"), look(20, None, "Night"),
            look(30, None, "Noon"), look(40, None, "Afternoon"), look(50, None, "Afternoon")]
    assert quests.day_changes(seen) == [40]


def test_readings_are_kept_and_say_they_were_read(settings):
    conn = init_db(settings.db_path)
    try:
        conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                     "duration_sec, imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 60, 'now')")
        assert not quests.is_read(conn, 1)
        quests.store(conn, 1, [look(0, "Where Loyalty Lies"), Sighting(10, None, None, None)])
        assert quests.is_read(conn, 1) and quests.load(conn, 1) == [look(0, "Where Loyalty Lies")]
    finally:
        conn.close()


# --- Splitting around quests --------------------------------------------------------------

from ai_editor.analysis.quests import Mission, Story  # noqa: E402
from ai_editor.recipes.parts import Break, make_parts, split, with_story  # noqa: E402


def pauses(total_min: float):
    return [Break(t, t, -0.3, "pause") for t in range(60, int(total_min * 60), 60)]


def parts_of(total_min, story, settings):
    total = total_min * 60
    breaks = with_story(pauses(total_min), story, settings)
    return make_parts(total, split(total, breaks, settings), [(0.0, total)])


def test_a_part_stretches_to_finish_a_quest(settings):
    """A quest from 20 to 62 minutes is never split: a part ends as it begins or
    runs on to its end, past the usual 35 minutes."""
    story = Story([Mission("Where Loyalty Lies", 20 * 60, 62 * 60)], [])
    parts = parts_of(120, story, settings)
    assert not any(20 * 60 + 20 < p.end < 62 * 60 - 20 for p in parts)
    holding = next(p for p in parts if p.start < 40 * 60 < p.end)
    assert holding.end >= 62 * 60 - 20 and holding.length > 35 * 60
    assert not any(p.flagged for p in parts)


def test_a_quest_longer_than_an_hour_is_split_and_flagged(settings):
    story = Story([Mission("What Moves the Dead", 5 * 60, 115 * 60)], [])
    parts = parts_of(120, story, settings)
    assert all(p.length <= 60 * 60 for p in parts)
    assert parts[0].mission == "What Moves the Dead" and parts[0].flagged


def test_the_time_of_day_turning_is_a_good_place_to_end(settings):
    story = Story([], [31 * 60 + 30])
    assert parts_of(60, story, settings)[0].story == "time of day"


def test_review_says_what_each_part_ends_on():
    from ai_editor.app.videos import ends_on

    assert ends_on({"ends_on": "loading", "story": "quest end", "hook": True}) == \
        "loading screen · quest ends · hook"
    assert ends_on({"ends_on": "pause", "mission": "Who Pulls the Strings"}).startswith(
        '⚠ in the middle of "Who Pulls the Strings"')
    assert ends_on(None) == "-"      # a plan made before 2F
