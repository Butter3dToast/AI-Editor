"""The Let's Play trim: what goes, and what must never go."""

from __future__ import annotations

import numpy as np
import pytest

from ai_editor.recipes.letsplay import Cut, kept_pieces, plan_cuts, protected_seconds

S = 300  # a five-minute stretch of an episode


def cut_up(settings, *, talking=(), protected=(), dark=(), motion=None, hud=None, off_game=()):
    def mask(ranges):
        m = np.zeros(S, dtype=bool)
        for a, b in ranges:
            m[a:b] = True
        return m

    moving = np.full(S, 6.0, dtype=np.float32) if motion is None else motion
    return plan_cuts(seconds=S, talking=mask(talking), protected=mask(protected), dark=mask(dark),
                     motion=moving, hud=hud, off_game=mask(off_game) if off_game else None,
                     settings=settings)


def still(ranges, level=0.0):
    m = np.full(S, 6.0, dtype=np.float32)
    for a, b in ranges:
        m[a:b] = level
    return m


def test_a_loading_screen_goes_all_but_a_moment(settings):
    cuts = cut_up(settings, talking=[(0, 100), (112, 300)], dark=[(100, 112)],
                  motion=still([(100, 112)]))
    assert [c.reason for c in cuts] == ["loading"]
    assert cuts[0].start == pytest.approx(100.3) and cuts[0].end == pytest.approx(111.7)


def test_night_time_play_is_not_a_loading_screen(settings):
    """EP 1: dark gameplay (the camera moving) was cut as "loading"."""
    cuts = cut_up(settings, talking=[(0, 100), (112, 300)], dark=[(100, 112)])  # dark, but moving
    assert cuts == []


def test_a_menu_goes_unless_you_are_talking(settings):
    menu = still([(100, 110)], level=0.3)
    assert [c.reason for c in cut_up(settings, talking=[(0, 100), (110, 300)], motion=menu)] == ["menu"]
    assert cut_up(settings, talking=[(0, 300)], motion=menu) == []


def test_long_silence_is_cut_down_leaving_a_little_either_side(settings):
    cuts = cut_up(settings, talking=[(0, 100), (140, 300)])  # 40 s of quiet play
    assert [c.reason for c in cuts] == ["silence"]
    assert (cuts[0].start, cuts[0].end) == (103.0, 137.0)


def test_a_short_pause_is_kept(settings):
    assert cut_up(settings, talking=[(0, 100), (118, 300)]) == []  # 18 s: under 20


def test_a_quiet_cutscene_is_never_cut(settings):
    """EP 1: 10 of 24 "silences" were quiet moments in cutscenes -- no HUD."""
    hud = np.full(S, 0.4, dtype=np.float32)
    hud[100:140] = 0.04
    assert cut_up(settings, talking=[(0, 100), (140, 300)], hud=hud) == []


def test_quiet_play_with_the_hud_showing_is_cut(settings):
    hud = np.full(S, 0.4, dtype=np.float32)
    assert [c.reason for c in cut_up(settings, talking=[(0, 100), (140, 300)], hud=hud)] == ["silence"]


def test_a_fight_is_never_cut(settings):
    assert cut_up(settings, talking=[(0, 100), (140, 300)], protected=[(95, 145)]) == []


def test_a_sword_fight_counts_as_a_fight(settings):
    """EP 1, 94:44: a silent sword fight, no gunfire, nearly cut as silence."""
    melee = np.zeros(S, dtype=np.float32)
    melee[110:125] = 0.35
    protected = protected_seconds(np.zeros(S), {"melee": melee}, S, settings)
    assert protected[110:125].all()
    assert protected[100] and protected[134]  # the pauses between blows are still the fight


def test_starting_and_ending_screens_go_whatever_is_said(settings):
    cuts = cut_up(settings, talking=[(0, 300)], off_game=[(0, 30), (270, 300)])
    assert [(c.start, c.end, c.reason) for c in cuts] == [(0, 30, "stream_screen"),
                                                        (270, 300, "stream_screen")]


def test_what_is_kept_is_everything_else():
    cuts = [Cut(10, 20, "loading"), Cut(50, 60, "silence")]
    assert kept_pieces(cuts, 100) == [(0.0, 10), (20, 50), (60, 100)]


# --- Splitting into parts ------------------------------------------------------------

from ai_editor.recipes.parts import Break, make_parts, part_cost, range_pieces, split  # noqa: E402


def pauses(total_min: float, every_sec: float = 60.0, kind: str = "pause", cost: float = -0.3):
    return [Break(t, t, cost, kind) for t in np.arange(every_sec, total_min * 60, every_sec)]


def lengths(total_min: float, breaks, settings) -> list[float]:
    total = total_min * 60
    return [round(p.length / 60, 1) for p in make_parts(total, split(total, breaks, settings),
                                                          [(0.0, total)])]


def test_two_hours_make_about_four_thirty_minute_parts(settings):
    parts = lengths(120, pauses(120), settings)
    assert len(parts) == 4 and all(25 <= p <= 35 for p in parts)


def test_a_loading_screen_is_a_better_end_than_a_pause(settings):
    breaks = pauses(60) + [Break(33 * 60 + 20, 0, -3.0, "loading")]
    chosen = split(60 * 60, breaks, settings)
    assert [b.kind for b in chosen] == ["loading"]


def test_a_hook_ending_wins_among_good_breaks(settings):
    breaks = pauses(60) + [Break(27 * 60 + 30, 0, -0.3 + settings.lets_play.bonus_hook_ending,
                                 "pause", hook=True)]
    assert split(60 * 60, breaks, settings)[0].hook


def test_a_short_leftover_joins_the_previous_part(settings):
    """70 minutes: two parts of 35, not 30 + 30 + a 10-minute scrap."""
    parts = lengths(70, pauses(70), settings)
    assert len(parts) == 2 and min(parts) >= 25


def test_no_clean_break_for_an_hour_stretches_a_part_but_never_past_sixty(settings):
    """A long story stretch with nothing allowed: the part stretches, up to the hard cap."""
    breaks = [Break(50 * 60, 0, -0.3, "pause")] + [Break(t, t, 50.0, "forced")
                                                    for t in range(60, 100 * 60, 60)]
    chosen = split(100 * 60, breaks, settings)
    total = 100 * 60
    parts = make_parts(total, chosen, [(0.0, total)])
    assert all(p.length <= 60 * 60 for p in parts)
    assert parts[0].ends_on == "pause"  # the clean break at 50 min, not a forced one at 30


def test_part_lengths_cost_nothing_much_in_range_and_a_lot_beyond_45(settings):
    assert part_cost(30, settings, last=False) < part_cost(35, settings, last=False) < 1
    assert part_cost(50, settings, last=False) > part_cost(40, settings, last=False) + 20
    assert part_cost(61, settings, last=False) is None


def test_a_part_spans_the_kept_pieces_around_cuts():
    pieces = [(0.0, 100.0), (130.0, 200.0), (260.0, 400.0)]  # 60 s and 30 s were cut
    assert range_pieces(pieces, 90, 180) == [(90.0, 100.0), (130.0, 200.0), (260.0, 270.0)]
