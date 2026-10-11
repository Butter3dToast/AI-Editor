"""The Part Planner: moving, adding and removing a Let's Play's splits (Phase 2F-2)."""

from __future__ import annotations

from ai_editor.recipes import planner
from ai_editor.recipes.plan import EditPlan, Segment

MIN = 60.0


def lp_plan(splits_min=(30, 60), total_min=90, cut=(40, 41)):
    """A 90-minute recording with one minute cut out at 40, in parts at 30 and 60
    minutes of the trimmed episode; a safe break every 5 minutes of the recording."""
    pieces = [(0.0, cut[0] * MIN), (cut[1] * MIN, (total_min + 1) * MIN)]
    plan = EditPlan("l", "letsplay", "t", "The Blood of Dawnwalker", 1800, [])
    plan.segments = []
    bounds = [0.0, *[m * MIN for m in splits_min], sum(b - a for a, b in pieces)]
    from ai_editor.recipes.parts import range_pieces

    for n, (a, b) in enumerate(zip(bounds, bounds[1:]), start=1):
        plan.segments += [Segment(1, x, y, kind="piece", part=n) for x, y in range_pieces(pieces, a, b)]
    breaks = [[t * MIN, "pause", -0.5, False, None, None] for t in range(5, total_min + 1, 5)
              if not cut[0] <= t <= cut[1]]
    breaks.append([44 * MIN, "loading", -3.0, False, "quest end", None])
    breaks.append([72 * MIN, "pause", 49.5, False, None, "What Moves the Dead"])
    plan.source = {"breaks": breaks,
                   "parts": [{"number": n, "ends_on": "pause"} for n in range(1, len(bounds))]}
    return plan


def lengths(plan):
    out = {}
    for s in plan.segments:
        out[s.part] = out.get(s.part, 0.0) + s.length
    return [round(v / MIN, 1) for _, v in sorted(out.items())]


def test_the_parts_and_splits_are_read_back_from_the_plan():
    plan = lp_plan()
    assert planner.splits_of(plan) == [30 * MIN, 60 * MIN]
    assert planner.pieces_of(plan) == [(0.0, 40 * MIN), (41 * MIN, 91 * MIN)]
    assert lengths(plan) == [30, 30, 30]


def test_a_dragged_split_snaps_to_the_nearest_safe_break(settings):
    plan = lp_plan()
    change = planner.move_split(None, settings, plan, 0, 33.4 * MIN)
    assert planner.splits_of(plan) == [35 * MIN, 60 * MIN] and lengths(plan) == [35, 25, 30]
    assert "Part 1 now ends at 0:35:00, on a pause in talking" in change.message
    # The loading screen where a quest ends: 44 min in the recording, 43 in the episode.
    change = planner.move_split(None, settings, plan, 1, 43.2 * MIN)
    assert planner.splits_of(plan)[1] == 43 * MIN
    assert plan.source["parts"][1]["story"] == "quest end" and "the quest ends" in change.message


def test_a_split_never_lands_where_its_not_safe_or_makes_a_part_too_long(settings):
    plan = lp_plan()
    before = list(plan.segments)
    assert "No safe place" in planner.move_split(None, settings, plan, 0, 120 * MIN).message
    plan = lp_plan(splits_min=(30, 60), total_min=130)
    assert "longer than 60" in planner.move_split(None, settings, plan, 1, 125 * MIN).message
    assert lp_plan().segments == before


def test_adding_and_removing_splits(settings):
    plan = lp_plan()
    change = planner.add_split(None, settings, plan, 46 * MIN)
    assert lengths(plan) == [30, 14, 16, 30] and "4 parts now" in change.message
    assert [p["number"] for p in plan.source["parts"]] == [1, 2, 3, 4]
    planner.remove_split(settings, plan, 1)
    assert lengths(plan) == [30, 30, 30]
    planner.remove_split(settings, plan, 0)
    assert lengths(plan) == [60, 30]
    assert "60 minutes at most" in planner.remove_split(settings, plan, 0).message


def test_a_split_in_the_middle_of_a_quest_is_flagged(settings):
    plan = lp_plan()
    change = planner.move_split(None, settings, plan, 1, 71 * MIN)
    assert planner.splits_of(plan)[1] == 71 * MIN      # 72 in the recording
    assert plan.source["parts"][1]["mission"] == "What Moves the Dead"
    assert "in the middle of \"What Moves the Dead\"" in change.message


def test_the_parts_bar_has_a_handle_at_each_split_in_recording_time(settings):
    from ai_editor.app import review_list

    page = review_list.review_list(None, lp_plan(), settings)
    assert page.count("class='aie-split'") == 2 and page.count("aie-split-x") == 2
    # The second split: 60 minutes into the episode is 61 into the recording (a minute was cut).
    assert "<span class='aie-split-at'>1:01:00</span>" in page
    assert "data-breaks='[300, " in page and "aie-row" not in page
