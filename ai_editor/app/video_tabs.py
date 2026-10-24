"""The Clips, Create video and Review tabs (Phase 1H-2).

What the creator chose (2026-10-03): thumbs up/down on clips, kept for
learning later; Review can choose the teaser, remove a clip (the next best
fills the gap: "about 10 min, never below") and move clips up and down.
Clips play in the window from the preview copy.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import gradio as gr
import pandas as pd

from ..cli import _moment_in, clip_note
from ..config import Settings
from ..db import init_db
from ..errors import AIEditorError
from ..games import canonical_game
from ..recipes import history, review
from ..recipes.plan import save_plan
from ..style.apply import NO_PROFILE
from . import library, review_list, tasks, videos
from .worker import DONE, Worker, submitted

ALL_STREAMS = "All my streams"
NO_STYLE = -1   # the Style profile box: no profile, the Settings as they are
# Create video's "Which clips" (3A-1): a video is one or the other, never both.
CLIP_CHOICES = [("My 👍 clips", "liked"), ("My 🔖 next-video clips", "saved"),
                ("AI-Editor picks", "any")]
ALL_PARTS = "All parts"
WHOLE_VIDEO = "Quick preview of the whole video"
SHORT_PREVIEW = "Quick preview (vertical, the apps' button areas shaded)"
LAYOUTS = [("Zoomed centre", "crop"), ("Whole picture", "fit")]
EFFECT_CHOICES = [("Flash", "flash"), ("Screen shake", "shake"), ("Sound effects", "sfx"),
                  ("Punch-in zoom", "zoom"), ("Slow-motion replay", "replay")]
BETWEEN_CHOICES = [("Hard cut", "cut"), ("Slide", "slide")]
ONE_PART = "Quick preview of the selected part"
PLAN_WIDTHS = ["6%", "10%", "16%", "12%", "9%", "8%", "39%"]
PART_WIDTHS = ["8%", "14%", "30%", "48%"]
# Adjust the cut: earlier or later by 5 or 1 seconds.
NUDGES = ("◀ 5 s", "◀ 1 s", "1 s ▶", "5 s ▶")


def cut_clock(seconds: float) -> str:
    """1:34:52.4: a time in the recording, to the tenth of a second."""
    whole = max(0.0, float(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:04.1f}"


def parse_clock(text: str | None) -> float | None:
    """'1:34:52.4', '34:52' or '5692' as seconds; None if it isn't a time."""
    parts = (text or "").strip().split(":")
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return None
    if not 1 <= len(values) <= 3 or any(v < 0 for v in values):
        return None
    seconds = 0.0
    for v in values:
        seconds = seconds * 60 + v
    return seconds


def build(settings: Settings, worker: Worker, timer: gr.Timer, ui: gr.Blocks) -> None:
    """Add the three tabs. Call inside the window's gr.Tabs()."""

    def read(fn, *args, **kwargs):
        conn = init_db(settings.db_path)
        try:
            return fn(conn, *args, **kwargs)
        finally:
            conn.close()

    def stream_games() -> list[str]:
        episodes = {g.lower() for g in settings.lets_play.games}
        return [g for g in read(library.game_choices) if g.lower() not in episodes]

    def episode_choices() -> list[tuple[str, int]]:
        # Let's Play games first, then everything else analysed.
        return (read(videos.analysed_choices, settings, lets_play=True)
                + read(videos.analysed_choices, settings, lets_play=False))

    plans_now = read(videos.plan_choices)

    def style_choices() -> list[tuple[str, int]]:
        from ..style import profiles as style_profiles

        return [(NO_PROFILE, NO_STYLE), *read(style_profiles.names)]

    def recording_game(recording_id) -> str | None:
        if recording_id is None:
            return None
        row = read(lambda c: c.execute("SELECT game FROM recordings WHERE id = ?",
                                       (int(recording_id),)).fetchone())
        return row["game"] if row else None

    def auto_style(what, game, episode_rec, short_rec):
        """The profile made for this game and kind of video, else none."""
        from ..style.apply import matching

        recipe = {"Highlights": "highlights", "Let's Play": "letsplay"}.get(what, "shorts")
        if what == "Highlights":
            game = None if not game or game == ALL_STREAMS else canonical_game(game)
        else:
            game = recording_game(episode_rec if what == "Let's Play" else short_rec)
        found = read(matching, settings, game, recipe)
        return gr.update(choices=style_choices(), value=found if found is not None else NO_STYLE)

    # --- Clips -------------------------------------------------------------------------
    with gr.Tab("Clips", id="clips") as clips_tab:
        with gr.Row():
            clip_rec = gr.Dropdown(choices=read(videos.analysed_choices, settings), value=None,
                                   label="Recording", scale=3)
            clip_show = gr.Radio(videos.SHOW, value=videos.SHOW[0], label="Show", scale=2)
            ai_btn = gr.Button("Rate with AI", scale=1)
        clip_deleted = gr.Checkbox(False, label="Show streams whose video is deleted",
                                   info="Their clips and ratings are kept for learning: rate "
                                        "them here to teach AI-Editor. No video can be made "
                                        "from them.")
        clip_ids = gr.State([])
        clip_sel = gr.State(None)
        clip_counts = gr.Markdown()
        with gr.Row():
            with gr.Column(scale=3):
                clip_tbl = gr.Dataframe(headers=videos.CLIP_COLUMNS, interactive=False, wrap=True,
                                        max_height=560,
                                        column_widths=["4%", "9%", "6%", "6%", "6%", "6%",
                                                       "12%", "21%", "18%", "6%", "6%"])
            with gr.Column(scale=2):
                clip_player = gr.HTML(videos.player(None, note="Pick a recording, then click a "
                                                               "clip to watch it here."))
                clip_info = gr.Markdown()
                with gr.Row():
                    good_btn = gr.Button("👍 Good clip")
                    later_btn = gr.Button("🔖 Next video")
                    bad_btn = gr.Button("👎 Not good")
                    unrate_btn = gr.Button("Clear rating")
                clip_msg = gr.Markdown()
        with gr.Accordion("How well AI-Editor knows you", open=False) as knows_box:
            knows = gr.Markdown()

    # --- Create video --------------------------------------------------------------------
    with gr.Tab("Create video", id="create") as create_tab:
        kind = gr.Radio(["Highlights", "Let's Play", "Shorts"], value="Highlights",
                        label="What to make")
        with gr.Group(visible=True) as hl_group:
            hl_game = gr.Dropdown(choices=[ALL_STREAMS, *stream_games()], value=ALL_STREAMS,
                                  label="Game",
                                  info="All my streams: every game you played (Let's Plays stay "
                                       "out). Or just one game.")
            hl_from = gr.Dropdown(choices=read(videos.analysed_choices, settings, lets_play=False),
                                  multiselect=True, value=[], label="Only these streams (optional)",
                                  info="Leave empty and AI-Editor uses the oldest streams' unused "
                                       "clips first, then the next.")
            hl_minutes = gr.Number(value=settings.highlights.target_length_min, minimum=1,
                                   maximum=60, label="Length in minutes",
                                   info="The least it will be. It may run a little over.")
            hl_reuse = gr.Checkbox(value=False, label="Use clips already in a video",
                                   info="Rendering a video uses its clips up, so the next one has "
                                        "fresh clips. Tick this to make another video from the "
                                        "same streams anyway.")
            hl_liked = gr.Radio(CLIP_CHOICES,
                                value="liked" if settings.highlights.only_liked else "any",
                                label="Which clips",
                                info="My 👍 clips: exactly the clips you gave a 👍, nothing "
                                     "added to reach the length. My 🔖 clips: the ones you "
                                     "saved for this next video. With none, AI-Editor picks. "
                                     "AI-Editor's own picks never take a 🔖 clip.")
        with gr.Group(visible=False) as lp_group:
            lp_rec = gr.Dropdown(choices=episode_choices(), value=None, label="Episode recording",
                                 info="Trimmed (loading screens, silent menus, long pauses) and "
                                      "split into parts of about "
                                      f"{settings.lets_play.target_min:.0f} minutes.")
        with gr.Group(visible=False) as sh_group:
            sh_rec = gr.Dropdown(choices=read(videos.analysed_choices, settings), value=None,
                                 label="Stream or recording",
                                 info="Up to five suggestions, each 15-60 seconds and vertical: "
                                      "your Numpad - moments first, then the AI's picks that make "
                                      "sense on their own.")
        # Phase 2G-2: picked by itself for the game and kind of video, changeable.
        style_pick = gr.Dropdown(choices=style_choices(), value=NO_STYLE, label="Style profile",
                                 info="Picked by itself when a profile is made for this game and "
                                      "kind of video (Style Profiles). It sets the pace and "
                                      "amounts; it never switches effects or captions on.")
        make_btn = gr.Button("Make the plan", variant="primary")
        make_msg = gr.Markdown()

    # --- Review --------------------------------------------------------------------------
    with gr.Tab("Review", id="review") as review_tab:
        with gr.Row(equal_height=True):
            plan_pick = gr.Dropdown(choices=plans_now,
                                    value=plans_now[0][1] if plans_now else None,
                                    label="Video plan", info="Newest first", scale=6)
            delete_btn = gr.Button("Delete this plan", size="sm", variant="stop", scale=1,
                                   min_width=140)
        # Only when the creator says so, and asked once more.
        with gr.Row(visible=False) as confirm_row:
            confirm_note = gr.Markdown()
            yes_btn = gr.Button("Yes, delete it", variant="stop", scale=0, min_width=140)
            no_btn = gr.Button("Keep it", scale=0, min_width=110)
        # Several at once (24 Oct: one by one was "very painful"), asked once more too.
        with gr.Accordion("Delete several plans", open=False) as bulk_box:
            bulk_pick = gr.CheckboxGroup(choices=[], label="Tick the plans to delete",
                                         info="Newest first. Only the plans leave the list: "
                                              "finished videos stay in your output folder, and "
                                              "clips and ratings stay.")
            with gr.Row():
                bulk_drafts = gr.Button("Tick every draft", size="sm", scale=0, min_width=150)
                bulk_none = gr.Button("Untick all", size="sm", scale=0, min_width=110)
                bulk_btn = gr.Button("Delete the ticked plans", size="sm", variant="stop",
                                     scale=0, min_width=190)
            with gr.Row(visible=False) as bulk_confirm:
                bulk_note = gr.Markdown()
                bulk_yes = gr.Button("Yes, delete them", variant="stop", scale=0, min_width=150)
                bulk_no = gr.Button("Keep them", scale=0, min_width=110)
        summary = gr.Markdown()
        sel = gr.State(None)
        # Kept inside a tab: anything placed straight in the tab bar shifts the
        # tabs after it, and Gradio 6 then showed Storage and Settings twice.
        seen = gr.State(-1)
        handled = gr.State({"plan_id": 0, "preview": 0})
        add_spots = gr.State({})
        undo_note = gr.State("")    # what Undo or Redo just did, shown once all is redrawn
        with gr.Row():
            with gr.Column(scale=3):
                with gr.Row():
                    undo_btn = gr.Button("↶ Undo", size="sm", interactive=False, scale=1)
                    redo_btn = gr.Button("↷ Redo", size="sm", interactive=False, scale=1)
                # The length bar, and the clips to click and drag (Phase 2D-1).
                clip_list = gr.HTML("", css_template=review_list.LIST_CSS,
                                    js_on_load=review_list.LIST_JS, elem_id="aie-clip-list")
                # A Let's Play's parts: the list above shows only their bar.
                plan_tbl = gr.Dataframe(headers=videos.PART_COLUMNS, interactive=False, wrap=True,
                                        max_height=520, column_widths=PART_WIDTHS, visible=False)
                # Highlights only: hidden for a Let's Play.
                with gr.Row():
                    teaser_btn = gr.Button("Use as teaser")
                    remove_btn = gr.Button("Remove")
                    up_btn = gr.Button("Move up")
                    down_btn = gr.Button("Move down")
                with gr.Row():
                    position = gr.Number(label="Move the clicked clip to #", precision=0,
                                         minimum=1, scale=2)
                    move_to_btn = gr.Button("Move", scale=1)
                    sort_btn = gr.Button("Sort by time", scale=2)
                with gr.Row():
                    moment = gr.Textbox(label="Or the teaser from an exact moment",
                                        placeholder="6:36-6:42, or just where it starts: 6:36",
                                        info="The time in the quick preview or render of this plan "
                                             "as it is now, inside one clip.", scale=3)
                    moment_btn = gr.Button("Use this moment", scale=1)
                with gr.Row():
                    add_pick = gr.Dropdown(choices=[], value=None, scale=3,
                                           label="Add a clip that isn't in the video",
                                           info="👍 clips first, then the best. Pick one to watch "
                                                "it, then add it.")
                    add_btn = gr.Button("Add to video", scale=1)
                highlight_only = [teaser_btn, remove_btn, up_btn, down_btn, position,
                                  move_to_btn, sort_btn, moment, moment_btn, add_pick, add_btn]
                review_msg = gr.Markdown()
            with gr.Column(scale=2):
                review_player = gr.HTML(videos.player(
                    None, note="Click a row to watch it here, or make a quick preview of the "
                               "whole video."), elem_id="aie-review-player")
                preview_btn = gr.Button(WHOLE_VIDEO)
                layout_pick = gr.Radio(LAYOUTS, value="crop", visible=False,
                                       label="How the game fills the tall frame",
                                       info="Then make a quick preview to see it.")
                # Adjust the cut: brought forward from Phase 2D (the creator, 10 Oct).
                with gr.Group(visible=False) as adjust_box:
                    adjust_info = gr.Markdown()
                    start_txt = gr.Textbox(label="Start", max_lines=1,
                                           info="In the recording. Type a time and press Enter, "
                                                "or use the buttons below.")
                    with gr.Row():
                        start_nudges = [gr.Button(label, min_width=50, size="sm")
                                        for label in NUDGES]
                        start_here = gr.Button("Start here", min_width=80, size="sm")
                    end_txt = gr.Textbox(label="End", max_lines=1,
                                         info="Or pause the player above where you want it, and "
                                              "press 'here'.")
                    with gr.Row():
                        end_nudges = [gr.Button(label, min_width=50, size="sm")
                                      for label in NUDGES]
                        end_here = gr.Button("End here", min_width=80, size="sm")
                    with gr.Row():
                        around_btn = gr.Button("Watch 30 s either side")
                        play_cut_btn = gr.Button("Play the new cut")
                    save_cut_btn = gr.Button("Save the new cut", variant="primary")
                    here_time = gr.Number(visible=False)
                pending_cut = gr.State(None)
                # Fixing captions, line by line (Phase 2D-2).
                with gr.Group(visible=False) as lines_box:
                    lines_info = gr.Markdown()
                    line_pick = gr.Radio([], label="Caption lines",
                                         info="Click a line to hear it and fix it. ✎ fixed, "
                                              "⊘ hidden.")
                    line_txt = gr.Textbox(label="This line", max_lines=3,
                                          info="Fix the words and save: the fix goes everywhere "
                                               "this moment is used.")
                    with gr.Row():
                        save_line_btn = gr.Button("Save line", variant="primary", size="sm")
                        hide_line_btn = gr.Button("Hide this line", size="sm")
                        back_line_btn = gr.Button("Put back the original", size="sm")
                        play_line_btn = gr.Button("Play this line", size="sm")
                    with gr.Row(visible=False) as remember_row:
                        remember_note = gr.Markdown()
                        remember_yes = gr.Button("Yes, everywhere", size="sm", scale=0,
                                                 min_width=130)
                        remember_no = gr.Button("No, just here", size="sm", scale=0,
                                                min_width=110)
                lines_state = gr.State(None)
                offer_state = gr.State(None)
        gr.Markdown("### Finish it")
        with gr.Row():
            captions_box = gr.Checkbox(value=settings.captions.highlights,
                                       label="Burn in captions (your words)")
            music_box = gr.Checkbox(value=settings.render.include_stream_music,
                                    label="Music from your stream",
                                    info="Kept under the talking. Quick previews have the "
                                         "stream's sound as it was.")
            effects_box = gr.CheckboxGroup(
                EFFECT_CHOICES, value=settings.effects.highlights,
                label="Effects on the big moments",
                info="For this video. Make a quick preview to see and hear them.")
            episode_box = gr.Number(label="Episode number", precision=0, visible=False)
            part_pick = gr.Dropdown(choices=[ALL_PARTS], value=ALL_PARTS, label="Parts",
                                    visible=False)
        with gr.Row():
            between_pick = gr.Radio(BETWEEN_CHOICES, value=settings.effects.between_clips,
                                    label="Between clips", visible=False,
                                    info="Slide: the next clip slides in over the last.")
            moments_box = gr.CheckboxGroup([], value=[], label="Each effect", visible=False,
                                           info="Untick one to leave just that moment out.")
        with gr.Row():
            render_btn = gr.Button("Render the finished video", variant="primary")
            open_btn = gr.Button("Open the finished video")
            export_btn = gr.Button("Export to DaVinci Resolve")
        finish_msg = gr.Markdown(
            "Rendering takes about 3 minutes per 10 minutes of video, and shows under Jobs. It "
            "marks the clips as used, so the next highlight video carries on with fresh ones.")
        gr.Markdown("### Publish")
        publish_btn = gr.Button("Write titles, description and chapters")
        publish_msg = gr.Markdown()
        title_pick = gr.Radio(choices=[], label="Title ideas",
                              info="Pick one: it goes in the box below, ready to copy.")
        title_box = gr.Textbox(label="Title", buttons=["copy"], max_lines=1)
        desc_box = gr.Textbox(label="Description, with chapters", lines=10, buttons=["copy"],
                              info="Paste it into YouTube as it is: the chapter times make "
                                   "YouTube's chapters.")
        tags_box = gr.Textbox(label="Tags", buttons=["copy"],
                              info="YouTube Studio: Show more > Tags.")
        keep_btn = gr.Button("Keep my changes")
        with gr.Row(visible=False) as link_row:
            link_box = gr.Textbox(label="This video's YouTube link, once uploaded", scale=4,
                                  placeholder="https://youtu.be/...",
                                  info="Shorts made from it then say \"Full video:\" with "
                                       "this link.")
            link_btn = gr.Button("Save the link", scale=1)
        thumbs = gr.Gallery(label="Thumbnail frames, best first (full size, in "
                                  "output/thumbnails)", columns=3, height=420,
                            buttons=["download", "fullscreen"], interactive=False)

    # --- Clips: handlers ----------------------------------------------------------------

    def clips_view(recording_id, show):
        """The table, its clip ids, and the counts line."""
        conn = init_db(settings.db_path)
        try:
            lengths = videos.video_lengths(conn, settings, int(recording_id))
            rows, ids = videos.clip_table(conn, int(recording_id), show, lengths, settings)
            counts = videos.clip_summary(conn, settings, int(recording_id), lengths)
        finally:
            conn.close()
        return pd.DataFrame(rows, columns=videos.CLIP_COLUMNS), ids, counts

    def load_clips(recording_id, show):
        if recording_id is None:
            return (pd.DataFrame(columns=videos.CLIP_COLUMNS), [],
                    videos.player(None, note="Pick a recording."), "", None, "")
        table, ids, counts = clips_view(recording_id, show)
        return (table, ids, videos.player(None, note=f"{len(ids)} clip(s). Click one to watch "
                                                       "it."), "", None, counts)

    clip_outputs = [clip_tbl, clip_ids, clip_player, clip_info, clip_sel, clip_counts]
    clip_rec.change(load_clips, [clip_rec, clip_show], clip_outputs)

    def clip_recordings(deleted, recording):
        found = read(videos.analysed_choices, settings, deleted=bool(deleted))
        return gr.update(choices=found,
                         value=recording if recording in [r[1] for r in found] else None)

    clip_deleted.change(clip_recordings, [clip_deleted, clip_rec], clip_rec)
    clip_show.change(load_clips, [clip_rec, clip_show], clip_outputs)

    def pick_clip(ids, recording_id, evt: gr.SelectData):
        row = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        if recording_id is None or not 0 <= row < len(ids):
            return gr.skip(), gr.skip(), None
        clip_id = ids[row]
        conn = init_db(settings.db_path)
        try:
            clip = conn.execute("SELECT start_sec, end_sec FROM clips WHERE clip_id = ?",
                                (clip_id,)).fetchone()
            proxy = videos.proxy_of(conn, int(recording_id))
            info = videos.clip_details(conn, clip_id)
        finally:
            conn.close()
        return videos.player(proxy, clip["start_sec"], clip["end_sec"]), info, clip_id

    clip_tbl.select(pick_clip, [clip_ids, clip_rec], [clip_player, clip_info, clip_sel])

    def rater(rating):
        def apply(clip_id, recording_id, show):
            if clip_id is None:
                return gr.skip(), gr.skip(), "Click a clip first.", gr.skip()
            message = read(videos.rate, clip_id, rating, settings)
            table, ids, counts = clips_view(recording_id, show)
            if rating == 1:
                message += (" It goes into your next highlight video. To put it in one you've "
                            "already made, use 'Add a clip' in Review.")
            elif rating == 2:
                message += (" To make that video: Create video → Which clips → "
                            "My 🔖 next-video clips.")
            return table, ids, message, counts
        return apply

    for button, rating in ((good_btn, 1), (later_btn, 2), (bad_btn, -1), (unrate_btn, None)):
        button.click(rater(rating), [clip_sel, clip_rec, clip_show],
                     [clip_tbl, clip_ids, clip_msg, clip_counts])

    def rate_with_ai(recording_id):
        if recording_id is None:
            return "Pick a recording first."
        if not settings.llm.enabled:
            return "The AI is switched off in Settings (AI)."
        return submitted(worker, worker.submit(
            f"AI rating the clips of #{recording_id}", f"rate:{recording_id}",
            tasks.rate_clips(settings, int(recording_id))))

    ai_btn.click(rate_with_ai, clip_rec, clip_msg)

    def scoreboard():
        from ..learning.scoreboard import scoreboard_text

        return read(scoreboard_text)

    for event in (knows_box.expand, clips_tab.select):
        event(scoreboard, None, knows)

    # --- Create video: handlers ---------------------------------------------------------

    kind.change(lambda k: (gr.update(visible=k == "Highlights"),
                           gr.update(visible=k == "Let's Play"), gr.update(visible=k == "Shorts")),
                kind, [hl_group, lp_group, sh_group])

    def make(what, game, chosen, minutes, episode_rec, reuse=False, short_rec=None,
             style=NO_STYLE, which=None):
        profile = None if style in (None, NO_STYLE) else int(style)
        if what == "Shorts":
            if short_rec is None:
                return "Pick the stream or recording first."
            return submitted(worker, worker.submit(
                f"Suggesting Shorts from #{short_rec}", f"make:shorts:{short_rec}",
                tasks.make_shorts(settings, int(short_rec), profile)))
        if what == "Highlights":
            game = None if not game or game == ALL_STREAMS else canonical_game(game)
            ids = [int(x) for x in chosen] if chosen else None
            label = game or "stream"
            return submitted(worker, worker.submit(
                f"Making a {label} highlights plan", f"make:highlights:{game}",
                tasks.make_highlights(settings, game=game, recording_ids=ids,
                                      minutes=float(minutes) if minutes else None,
                                      reuse=bool(reuse), profile=profile,
                                      only_liked=None if which is None else which == "liked",
                                      saved=which == "saved")))
        if episode_rec is None:
            return "Pick the episode's recording first."
        return submitted(worker, worker.submit(
            f"Making a Let's Play plan from #{episode_rec}", f"make:letsplay:{episode_rec}",
            tasks.make_letsplay(settings, int(episode_rec), profile)))

    make_btn.click(lambda *a: make(*a) + " When it's finished, it opens in Review.",
                   [kind, hl_game, hl_from, hl_minutes, lp_rec, hl_reuse, sh_rec, style_pick,
                    hl_liked],
                   make_msg)
    for picker in (kind, hl_game, lp_rec, sh_rec):
        picker.change(auto_style, [kind, hl_game, lp_rec, sh_rec], style_pick)
    create_tab.select(auto_style, [kind, hl_game, lp_rec, sh_rec], style_pick)

    # --- Review: handlers ---------------------------------------------------------------

    def table_for(plan):
        """A Let's Play's parts. Highlights and Shorts show their clips in clip_list."""
        if plan.recipe == "letsplay":
            return pd.DataFrame(videos.part_table(plan), columns=videos.PART_COLUMNS)
        return gr.skip()

    def shaped_table(plan):
        lets_play = plan is not None and plan.recipe == "letsplay"
        return gr.Dataframe(value=table_for(plan) if lets_play
                            else pd.DataFrame(columns=videos.PART_COLUMNS), visible=lets_play)

    def list_view(plan_id, selected=None):
        """The length bar and clip list, and what Undo and Redo would do."""
        conn = init_db(settings.db_path)
        try:
            plan, _ = videos.get_plan(conn, plan_id)
            body = review_list.review_list(conn, plan, settings, selected)
            back, again = history.can(conn, plan_id if plan is not None else None)
        finally:
            conn.close()
        return (body,
                gr.Button(value=f"↶ Undo {back}" if back else "↶ Undo", interactive=bool(back)),
                gr.Button(value=f"↷ Redo {again}" if again else "↷ Redo",
                          interactive=bool(again)))

    list_outputs = [clip_list, undo_btn, redo_btn]

    def show_plan(plan_id):
        plan, status = read(videos.get_plan, plan_id)
        empty = videos.player(None, note="Click a row to watch it here, or make a quick preview.")
        if plan is None:
            return ("No video plans yet. Make one in Create video.", shaped_table(None),
                    *show_editing(True, []), gr.Number(visible=False),
                    gr.Dropdown(visible=False), gr.Checkbox(), gr.Button(value=WHOLE_VIDEO),
                    empty, None, "", "", {})
        lets_play = plan.recipe == "letsplay"
        parts = [f"Part {n}" for n in sorted({s.part for s in plan.segments if s.part})]
        episode = None
        extra = []
        if lets_play:
            from ..render.parts import episode_of

            episode = read(episode_of, plan)
        elif plan.recipe == "highlights":
            extra = read(review.addable, settings, plan)
        shown = None if lets_play else videos.last_preview(settings, plan)
        return (videos.plan_summary(plan, status), shaped_table(plan),
                *show_editing(plan.recipe == "highlights", extra),
                gr.Number(visible=lets_play, value=episode),
                gr.Dropdown(visible=lets_play, choices=[ALL_PARTS, *parts], value=ALL_PARTS),
                gr.Checkbox(value=settings.captions.lets_play if lets_play
                            else settings.shorts.captions if plan.recipe == "shorts"
                            else settings.captions.highlights),
                gr.Button(value=ONE_PART if lets_play else SHORT_PREVIEW
                          if plan.recipe == "shorts" else WHOLE_VIDEO),
                shown or empty, None, "", "", spots(extra))

    def spots(extra) -> dict:
        """Where each addable clip is, to play it: {clip id: [recording, in, out]}."""
        return {e[1]: list(e[2:]) for e in extra}

    def show_editing(visible: bool, extra) -> list:
        return [gr.update(visible=visible, choices=[e[:2] for e in extra], value=None)
                if part is add_pick else gr.update(visible=visible) for part in highlight_only]

    plan_outputs = [summary, plan_tbl, *highlight_only, episode_box, part_pick, captions_box,
                    preview_btn, review_player, sel, review_msg, finish_msg, add_spots]
    plan_pick.change(show_plan, plan_pick, plan_outputs)
    ui.load(show_plan, plan_pick, plan_outputs)
    # Again on opening the tab: Gradio 6 drops "hide this" sent to a tab that
    # isn't on screen yet, so a Let's Play could open showing highlight buttons.
    review_tab.select(show_plan, plan_pick, plan_outputs)
    for event in (plan_pick.change, review_tab.select, ui.load):
        event(list_view, plan_pick, list_outputs)

    def show_layout(plan_id):
        from ..render.final import vertical_of

        plan, _ = read(videos.get_plan, plan_id)
        if plan is None or plan.recipe != "shorts":
            return gr.Radio(visible=False)
        choices = LAYOUTS + ([("Facecam on top", "facecam_top")]
                             if plan.game in settings.shorts.facecam else [])
        return gr.Radio(visible=True, choices=choices, value=vertical_of(settings, plan).layout)

    for event in (plan_pick.change, review_tab.select, ui.load):
        event(show_layout, plan_pick, layout_pick)

    def set_layout(plan_id, layout):
        conn = init_db(settings.db_path)
        try:
            plan, status = videos.get_plan(conn, plan_id)
            if plan is None or plan.recipe != "shorts" or not layout:
                return gr.skip(), gr.skip()
            with history.step(conn, plan_id, "the Short's layout"):
                plan.source["layout"] = layout
                save_plan(conn, plan, status)
        finally:
            conn.close()
        name = dict((v, k) for k, v in LAYOUTS).get(layout, layout)
        shown = videos.last_preview(settings, plan, layout=layout)
        if shown:
            return f"This Short will use **{name}**. Here's its quick preview.", shown
        return (f"This Short will use **{name}**. Make a quick preview to see it.",
                videos.player(None, note=f"No quick preview of {name} yet."))

    layout_pick.input(set_layout, [plan_pick, layout_pick], [review_msg, review_player]).then(
        list_view, [plan_pick, sel], list_outputs)

    def show_effects(plan_id):
        from ..effects import switches

        plan, _ = read(videos.get_plan, plan_id)
        return gr.CheckboxGroup(value=[] if plan is None else switches(settings, plan))

    for event in (plan_pick.change, review_tab.select, ui.load):
        event(show_effects, plan_pick, effects_box)

    def log_ticks(conn, plan, before, after, where, labels=None):
        """Each effect ticked or unticked, for learning (3A-1); undone with the change."""
        from ..recipes.review import log_feedback

        labels = labels or {}
        for action, keys in (("effect_on", set(after) - set(before)),
                             ("effect_off", set(before) - set(after))):
            for key in sorted(keys):
                log_feedback(conn, action, plan, None, effect=key, where=where,
                             label=labels.get(key, key))

    def set_effects(plan_id, chosen):
        from ..effects import LABELS, set_switches, switches

        conn = init_db(settings.db_path)
        try:
            plan, status = videos.get_plan(conn, plan_id)
            if plan is None:
                return "Pick a plan first."
            with history.step(conn, plan_id, "the effects"):
                before = switches(settings, plan)
                set_switches(plan, chosen or [])
                save_plan(conn, plan, status)
                log_ticks(conn, plan, before, chosen or [], "video", LABELS)
        finally:
            conn.close()
        if not chosen:
            return "No effects in this video."
        names = ", ".join(LABELS[k] for k in chosen)
        return f"Effects in this video: **{names}**. Make a quick preview to see and hear them."

    effects_changed = effects_box.input(set_effects, [plan_pick, effects_box], review_msg)

    def suggesting(plan) -> bool:
        from ..style.apply import styled

        return (plan is not None and plan.recipe != "letsplay"
                and styled(settings, plan).effects.suggest)   # a rule may switch it (2H-2)

    def show_moments(plan_id):
        """Each moment with effects, ticked unless switched off; hidden when there are none.
        With suggestions (2H-1): every big moment and the effects that suit it,
        ticked where it has them."""
        from ..effects import moments, suggestions

        conn = init_db(settings.db_path)
        try:
            plan, _ = videos.get_plan(conn, plan_id)
            if suggesting(plan):
                found = suggestions(conn, settings, plan)
                if not found:
                    return gr.CheckboxGroup(choices=[], value=[], visible=False)
                return gr.CheckboxGroup(
                    choices=[(s.label, s.key) for s in found],
                    value=[s.key for s in found if s.on], visible=True,
                    label="Suggested effects on the big moments",
                    info="The effects that suit each moment. Tick one to use them there: "
                         "nothing is used until you tick it.")
            found = [] if plan is None else moments(conn, settings, plan)
        finally:
            conn.close()
        if not found:
            return gr.CheckboxGroup(choices=[], value=[], visible=False)
        off = set((plan.source or {}).get("effects_off", []))
        return gr.CheckboxGroup(choices=found, value=[k for _, k in found if k not in off],
                                visible=True, label="Each effect",
                                info="Untick one to leave just that moment out.")

    for event in (plan_pick.change, review_tab.select, ui.load):
        event(show_moments, plan_pick, moments_box)
    # Once the switches are saved: replays change the video's length.
    effects_changed.then(show_moments, plan_pick, moments_box).then(
        list_view, [plan_pick, sel], list_outputs)

    def set_moments(plan_id, kept):
        from ..effects import (moments, set_moments_on, suggestions, summary, for_plan,
                               use_suggestions)

        conn = init_db(settings.db_path)
        try:
            plan, status = videos.get_plan(conn, plan_id)
            if plan is None:
                return "Pick a plan first."
            if suggesting(plan):
                with history.step(conn, plan_id, "the suggested effects"):
                    found = suggestions(conn, settings, plan)
                    use_suggestions(conn, settings, plan, kept or [])
                    save_plan(conn, plan, status)
                    log_ticks(conn, plan, [s.key for s in found if s.on], kept or [], "moment",
                              {s.key: s.label for s in found})
                if not kept:
                    return "No effects in this video."
                return (f"{len(kept)} moment{'s' if len(kept) != 1 else ''} with effects: "
                        f"{summary(for_plan(conn, settings, plan))}. Make a quick preview to "
                        "see and hear them.")
            listed = moments(conn, settings, plan)
            every = [k for _, k in listed]
            with history.step(conn, plan_id, "each effect's ticks"):
                off = set((plan.source or {}).get("effects_off", []))
                set_moments_on(plan, every, kept or [])
                save_plan(conn, plan, status)
                log_ticks(conn, plan, [k for k in every if k not in off],
                          [k for k in kept or [] if k in every], "moment",
                          {k: label for label, k in listed})
        finally:
            conn.close()
        left_out = len(every) - len(set(kept or []) & set(every))
        return (f"{len(every) - left_out} of {len(every)} moments keep their effects. Make a quick "
                "preview to see and hear them.")

    # Ticking suggestions changes the video's kinds too: show them, and the list again.
    moments_box.input(set_moments, [plan_pick, moments_box], review_msg).then(
        show_effects, plan_pick, effects_box).then(
        show_moments, plan_pick, moments_box).then(
        list_view, [plan_pick, sel], list_outputs)

    def show_between(plan_id):
        from ..render.slide import between

        plan, _ = read(videos.get_plan, plan_id)
        if plan is None or plan.recipe != "highlights":
            return gr.Radio(visible=False)
        return gr.Radio(visible=True, value=between(settings, plan))

    for event in (plan_pick.change, review_tab.select, ui.load):
        event(show_between, plan_pick, between_pick)

    def set_between(plan_id, choice):
        conn = init_db(settings.db_path)
        try:
            plan, status = videos.get_plan(conn, plan_id)
            if plan is None:
                return "Pick a plan first."
            with history.step(conn, plan_id, "between clips"):
                plan.source["between"] = choice
                save_plan(conn, plan, status)
        finally:
            conn.close()
        return ("Each clip slides in over the last. Make a quick preview to see it."
                if choice == "slide" else "Hard cuts between clips.")

    between_pick.input(set_between, [plan_pick, between_pick], review_msg).then(
        list_view, [plan_pick, sel], list_outputs)

    def show_music(plan_id):
        plan, _ = read(videos.get_plan, plan_id)
        on = settings.render.include_stream_music if plan is None else \
            (plan.source or {}).get("music", settings.render.include_stream_music)
        return gr.Checkbox(value=bool(on))

    for event in (plan_pick.change, review_tab.select, ui.load):
        event(show_music, plan_pick, music_box)

    def set_music(plan_id, on):
        conn = init_db(settings.db_path)
        try:
            plan, status = videos.get_plan(conn, plan_id)
            if plan is None:
                return "Pick a plan first."
            with history.step(conn, plan_id, "music from your stream"):
                plan.source["music"] = bool(on)
                save_plan(conn, plan, status)
        finally:
            conn.close()
        return ("The music from your stream will be in this video, kept under the talking."
                if on else "No music from your stream in this video.")

    music_box.input(set_music, [plan_pick, music_box], review_msg).then(
        list_view, [plan_pick, sel], list_outputs)

    def part_preview(plan_id, part):
        plan, _ = read(videos.get_plan, plan_id)
        if plan is None or plan.recipe != "letsplay" or part in (None, ALL_PARTS):
            return gr.skip()
        return videos.last_preview(settings, plan, int(part.split()[-1])) or gr.skip()

    part_pick.input(part_preview, [plan_pick, part_pick], review_player)

    def selected_row(evt) -> int | None:
        """The row a click picked: from the table (SelectData), or clip_list's trigger."""
        index = getattr(evt, "index", None) if isinstance(evt, gr.SelectData) else \
            (getattr(evt, "_data", None) or {}).get("row")
        row = index[0] if isinstance(index, (list, tuple)) else index
        return int(row) if isinstance(row, (int, float)) else None

    def pick_row(plan_id, evt: gr.EventData):
        row = selected_row(evt)
        plan, _ = read(videos.get_plan, plan_id)
        if row is None:
            return gr.skip(), gr.skip(), gr.skip()
        if plan is None:
            return gr.skip(), None, gr.skip()
        if plan.recipe == "letsplay":
            numbers = sorted({s.part for s in plan.segments if s.part})
            if not 0 <= row < len(numbers):
                return gr.skip(), None, gr.skip()
            first = next(s for s in plan.segments if s.part == numbers[row])
            proxy = read(videos.proxy_of, first.recording_id)
            return (videos.player(proxy, first.src_in, first.src_out,
                                  note=f"The start of part {numbers[row]}, up to its first cut. "
                                       "Quick preview shows the whole part as it will be."),
                    row, gr.update(value=f"Part {numbers[row]}"))
        if not 0 <= row < len(plan.segments):
            return gr.skip(), None, gr.skip()
        s = plan.segments[row]
        proxy = read(videos.proxy_of, s.recording_id)
        return videos.player(proxy, s.src_in, s.src_out), row, gr.skip()

    plan_tbl.select(pick_row, plan_pick, [review_player, sel, part_pick])
    clip_list.click(pick_row, plan_pick, [review_player, sel, part_pick])

    # --- Adjust the cut ------------------------------------------------------------------

    def cut_view(cut: dict | None, note: str = "", play: tuple[float, float] | None = None):
        """What the adjust panel shows for a cut that isn't saved yet."""
        if not cut:
            return gr.update(visible=False), None, "", "", "", gr.skip()
        length = cut["end"] - cut["start"]
        saved = (abs(cut["start"] - cut["was"][0]) < 0.05 and abs(cut["end"] - cut["was"][1]) < 0.05)
        info = (f"**Adjust clip {cut['index'] + 1}**: {cut_clock(cut['start'])} to "
                f"{cut_clock(cut['end'])} in the recording, {length:.1f} s."
                + ("" if saved else " **Not saved yet.**") + (f" {note}" if note else ""))
        player = gr.skip()
        if play is not None:
            proxy = read(videos.proxy_of, cut["rid"])
            player = videos.player(proxy, max(0.0, play[0]), play[1],
                                   note=f"{cut_clock(play[0])} to {cut_clock(play[1])}")
        return (gr.update(visible=True), cut, info, cut_clock(cut["start"]),
                cut_clock(cut["end"]), player)

    cut_outputs = [adjust_box, pending_cut, adjust_info, start_txt, end_txt, review_player]

    def open_cut(plan_id, evt: gr.EventData):
        row = selected_row(evt)
        plan, _ = read(videos.get_plan, plan_id)
        if plan is None or plan.recipe == "letsplay" or row is None \
                or not 0 <= row < len(plan.segments):
            return cut_view(None)
        s = plan.segments[row]
        cut = {"plan": plan_id, "index": row, "rid": s.recording_id, "start": s.src_in,
               "end": s.src_out, "was": [s.src_in, s.src_out]}
        return cut_view(cut)[:-1] + (gr.skip(),)   # the row's own player is already showing it

    plan_tbl.select(open_cut, plan_pick, cut_outputs)
    clip_list.click(open_cut, plan_pick, cut_outputs)
    for event in (plan_pick.change, review_tab.select):
        event(lambda: cut_view(None), None, cut_outputs)

    def moved(cut, edge, value, note=""):
        if not cut:
            return cut_view(None)
        new = dict(cut, **{edge: max(0.0, float(value))})
        if new["end"] - new["start"] < 1.0:
            return cut_view(cut, "The end must be after the start.")
        cut = new
        # Watch the edge that moved: the new start onwards, or the last seconds to the end.
        play = ((cut["start"], cut["end"]) if edge == "start"
                else (max(cut["start"], cut["end"] - 6.0), cut["end"]))
        return cut_view(cut, note, play)

    def nudge(edge, delta):
        return lambda cut: moved(cut, edge, (cut or {}).get(edge, 0.0) + delta) if cut \
            else cut_view(None)

    for button, delta in zip(start_nudges, (-5, -1, 1, 5)):
        button.click(nudge("start", delta), pending_cut, cut_outputs)
    for button, delta in zip(end_nudges, (-5, -1, 1, 5)):
        button.click(nudge("end", delta), pending_cut, cut_outputs)

    def typed(edge):
        def apply(cut, text):
            seconds = parse_clock(text)
            if seconds is None:
                return cut_view(cut, f"Couldn't read \"{text}\": write it like 1:34:52 or 34:52.")
            if cut and abs(seconds - cut[edge]) < 0.05:
                return (gr.skip(),) * len(cut_outputs)   # only clicked in and out of the box
            return moved(cut, edge, seconds)
        return apply

    # Enter, or clicking anywhere else: a typed time counts either way.
    for box, edge in ((start_txt, "start"), (end_txt, "end")):
        box.submit(typed(edge), [pending_cut, box], cut_outputs)
        box.blur(typed(edge), [pending_cut, box], cut_outputs)

    # Where the player is paused, read in the browser.
    here_js = ("(cut, t) => { const v = document.querySelector('#aie-review-player video'); "
               "return [cut, v ? v.currentTime : -1]; }")

    def here(edge):
        def apply(cut, t):
            if t is None or t < 0:
                return cut_view(cut, "Play the clip in the player above first, and pause it "
                                     "where you want it.")
            return moved(cut, edge, t)
        return apply

    start_here.click(here("start"), [pending_cut, here_time], cut_outputs, js=here_js)
    end_here.click(here("end"), [pending_cut, here_time], cut_outputs, js=here_js)

    around_btn.click(lambda cut: cut_view(cut, "", (cut["start"] - 30.0, cut["end"] + 30.0))
                     if cut else cut_view(None), pending_cut, cut_outputs)
    play_cut_btn.click(lambda cut: cut_view(cut, "", (cut["start"], cut["end"]))
                       if cut else cut_view(None), pending_cut, cut_outputs)

    def save_cut(plan_id, cut, start_text, end_text):
        if not cut or cut.get("plan") != plan_id:
            return gr.skip(), gr.skip(), "Click a clip in the list first.", *cut_view(None)
        # What's in the boxes is what's saved, Enter pressed or not (10 Oct: a
        # typed start and end were ignored because Save came straight after).
        for edge, text in (("start", start_text), ("end", end_text)):
            seconds = parse_clock(text)
            if seconds is None:
                return (gr.skip(), gr.skip(), f"Couldn't read the {edge} \"{text}\": write it "
                        "like 1:34:52 or 34:52.", *cut_view(cut))
            cut = dict(cut, **{edge: seconds})
        if cut["end"] - cut["start"] < 1.0:
            return gr.skip(), gr.skip(), "The end must be after the start.", *cut_view(cut)
        if abs(cut["start"] - cut["was"][0]) < 0.05 and abs(cut["end"] - cut["was"][1]) < 0.05:
            return (gr.skip(), gr.skip(), "Nothing to save: that's the cut it already has. "
                    "Change the start or end first.", *cut_view(cut))
        conn = init_db(settings.db_path)
        try:
            plan, status = videos.get_plan(conn, plan_id)
            # The clip may have moved in the list since it was clicked: find it again.
            index = next((n for n, s in enumerate(plan.segments)
                          if s.recording_id == cut["rid"] and abs(s.src_in - cut["was"][0]) < 0.01
                          and abs(s.src_out - cut["was"][1]) < 0.01), None)
            if index is None:
                return (gr.skip(), gr.skip(), "That clip has changed since you clicked it: "
                        "click it again.", *cut_view(None))
            segment = plan.segments[index]
            what = ("the teaser's cut" if segment.kind == "teaser"
                    else f"clip {index + 1}'s cut")
            with history.step(conn, plan_id, f"adjusting {what}", clips=[segment.clip_id]):
                change = review.adjust(conn, settings, plan, index, cut["start"], cut["end"])
                if change.plan.segments[index].src_in == cut["was"][0] and \
                        change.plan.segments[index].src_out == cut["was"][1]:
                    return gr.skip(), gr.skip(), change.message, *cut_view(cut)
                save_plan(conn, change.plan, status)
        finally:
            conn.close()
        s = change.plan.segments[index]
        cut = dict(cut, index=index, start=s.src_in, end=s.src_out, was=[s.src_in, s.src_out])
        return (videos.plan_summary(change.plan, status), table_for(change.plan), change.message,
                *cut_view(cut, "Saved.", (s.src_in, s.src_out)))

    save_cut_btn.click(save_cut, [plan_pick, pending_cut, start_txt, end_txt],
                       [summary, plan_tbl, review_msg, *cut_outputs]).then(
        list_view, [plan_pick, sel], list_outputs)

    def play_addable(clip_id, where):
        if not clip_id or clip_id not in where:
            return gr.skip()
        recording_id, start, end = where[clip_id]
        return videos.player(read(videos.proxy_of, recording_id), start, end,
                             note="Not in the video yet. Add it with 'Add to video'.")

    add_pick.input(play_addable, [add_pick, add_spots], review_player)

    def edit(action):
        def apply(plan_id, index, extra=""):
            """``extra``: the moment typed (action "moment"), or the clip to add ("add")."""
            plan, status = read(videos.get_plan, plan_id)
            skip = (gr.skip(), gr.skip())
            if plan is None or plan.recipe == "letsplay":
                return gr.skip(), gr.skip(), "Pick a highlight plan first.", index, *skip
            moment_range = None
            if action == "moment":
                found = _moment_in(plan, extra or "", settings)
                if found is None:
                    return (gr.skip(), gr.skip(), "That time isn't inside one clip of this plan. "
                            "Write it like 6:36-6:42, or 6:36.", index, *skip)
                clip_id, moment_range = found
                index = next((n for n, s in enumerate(plan.segments)
                              if s.clip_id == clip_id and s.kind != "teaser"), None)
            if action == "add":
                if not extra:
                    return gr.skip(), gr.skip(), "Pick a clip to add first.", index, *skip
                index = 0
            if action == "sort":
                index = 0
            if action == "move_to" and not extra:
                return gr.skip(), gr.skip(), "Type the number to move it to first.", index, *skip
            if index is None or not 0 <= index < len(plan.segments):
                return gr.skip(), gr.skip(), "Click a row in the list first.", index, *skip
            number = index + 1
            teaser = plan.segments[index].kind == "teaser"
            what = {"add": "adding a clip", "sort": "sorting by time",
                    "move_to": f"moving clip {number} to #{int(extra or 0)}",
                    "remove": "removing the teaser" if teaser else f"removing clip {number}",
                    "up": f"moving clip {number} up", "down": f"moving clip {number} down",
                    }.get(action, "choosing the teaser")
            conn = init_db(settings.db_path)
            try:
                with history.step(conn, plan_id, what):
                    if action == "add":
                        change = review.add(conn, settings, plan, extra)
                        index = None
                    elif action == "sort":
                        change = review.sort_by_time(conn, plan)
                        index = None
                    elif action == "move_to":
                        change = review.move_to(conn, plan, index, int(extra))
                        if change.message.startswith("Moved to #"):
                            index = int(change.message.removeprefix("Moved to #").rstrip(".")) - 1
                    elif action == "remove":
                        change = review.remove(conn, settings, plan, index)
                        index = None
                    elif action in ("up", "down"):
                        step = -1 if action == "up" else 1
                        change = review.move(conn, plan, index, step)
                        if change.message.startswith("Moved"):
                            clips = review.clip_indexes(plan)
                            index = clips[clips.index(index) + step] if index in clips else index
                    else:
                        change = review.use_as_teaser(conn, settings, plan, index, moment_range)
                        index = None
                    save_plan(conn, change.plan, status)
                # What's in the video changed, so what could be added did too.
                extra = None
                if action in ("add", "remove"):
                    extra = review.addable(conn, settings, change.plan)
            except AIEditorError as exc:
                return gr.skip(), gr.skip(), exc.user_message(), index, *skip
            finally:
                conn.close()
            if extra is None:
                lists = skip
            else:
                lists = (gr.update(choices=[e[:2] for e in extra], value=None), spots(extra))
            return (videos.plan_summary(change.plan, status), table_for(change.plan),
                    change.message, index, *lists)
        return apply

    edit_outputs = [summary, plan_tbl, review_msg, sel, add_pick, add_spots]
    for button, action, inputs in ((add_btn, "add", [plan_pick, sel, add_pick]),
                                   (sort_btn, "sort", [plan_pick, sel]),
                                   (move_to_btn, "move_to", [plan_pick, sel, position]),
                                   (remove_btn, "remove", [plan_pick, sel]),
                                   (up_btn, "up", [plan_pick, sel]),
                                   (down_btn, "down", [plan_pick, sel]),
                                   (teaser_btn, "teaser", [plan_pick, sel]),
                                   (moment_btn, "moment", [plan_pick, sel, moment])):
        button.click(edit(action), inputs, edit_outputs).then(
            list_view, [plan_pick, sel], list_outputs)

    def dropped(plan_id, evt: gr.EventData):
        """A clip dragged to a new place in the list (``from`` and ``to`` are rows), or
        the Part Planner: a split moved, added or joined on a Let's Play's parts bar."""
        data = getattr(evt, "_data", None) or {}
        if data.get("action") in ("move", "add", "join"):
            return plan_parts(plan_id, data)
        if not isinstance(data.get("from"), (int, float)) or not isinstance(data.get("to"),
                                                                              (int, float)):
            return (gr.skip(),) * len(edit_outputs)
        return edit("move_to")(plan_id, int(data["from"]), int(data["to"]) + 1)

    def plan_parts(plan_id, data):
        """The Part Planner (Phase 2F-2): one undo step per change."""
        from ..recipes import planner

        skip = (gr.skip(),) * 3
        try:
            split = int(data.get("split", -1))
            at = float(data.get("at", -1))
        except (TypeError, ValueError):
            return (gr.skip(), gr.skip(), "That didn't work: try again.", *skip)
        conn = init_db(settings.db_path)
        try:
            plan, status = videos.get_plan(conn, plan_id)
            if plan is None or plan.recipe != "letsplay":
                return (gr.skip(),) * len(edit_outputs)
            before = list(plan.segments)
            had_breaks = "breaks" in (plan.source or {})
            what = {"move": f"moving where part {split + 1} ends", "add": "adding a split",
                    "join": f"joining parts {split + 1} and {split + 2}"}[data["action"]]
            with history.step(conn, plan_id, what):
                if data["action"] == "move":
                    change = planner.move_split(conn, settings, plan, split, at)
                elif data["action"] == "add":
                    change = planner.add_split(conn, settings, plan, at)
                else:
                    change = planner.remove_split(settings, plan, split)
                if plan.segments != before:
                    save_plan(conn, plan, status)
            if plan.segments == before and not had_breaks:
                save_plan(conn, plan, status)   # its safe breaks, found once: not a change
        finally:
            conn.close()
        return (videos.plan_summary(plan, status), table_for(plan), change.message, None,
                gr.skip(), gr.skip())

    def parts_choices(plan_id):
        plan, _ = read(videos.get_plan, plan_id)
        if plan is None or plan.recipe != "letsplay":
            return gr.skip()
        parts = [f"Part {n}" for n in sorted({s.part for s in plan.segments if s.part})]
        return gr.update(choices=[ALL_PARTS, *parts], value=ALL_PARTS)

    clip_list.submit(dropped, plan_pick, edit_outputs).then(
        list_view, [plan_pick, sel], list_outputs).then(parts_choices, plan_pick, part_pick)

    # --- Deleting a plan: the creator's doing only, asked once more -----------------------

    def ask_delete(plan_id):
        plan, status = read(videos.get_plan, plan_id)
        if plan is None:
            return gr.Row(visible=False), ""
        made = ("Its finished video stays in your output folder, and its clips stay marked as "
                "used. " if status == "approved" else "")
        return gr.Row(visible=True), (
            f"**Delete \"{plan.title}\" ({plan.plan_id}) from the list?** {made}Its clips, "
            "your ratings and what AI-Editor learns from them all stay. This can't be undone.")

    delete_btn.click(ask_delete, plan_pick, [confirm_row, confirm_note])
    no_btn.click(lambda: gr.Row(visible=False), None, confirm_row)
    plan_pick.change(lambda: gr.Row(visible=False), None, confirm_row)

    def delete(plan_id):
        from ..recipes.plan import delete_plan

        if not plan_id or not read(delete_plan, plan_id):
            return gr.Row(visible=False), gr.skip()
        gr.Info(f"Deleted {plan_id} from the list.")
        plans = read(videos.plan_choices)
        return gr.Row(visible=False), gr.update(value=plans[0][1] if plans else None)

    # First on to the newest plan, then the deleted one off the list: both at
    # once, Gradio 6 kept showing the deleted plan's name in the box.
    def bulk_list(ticked=None):
        plans = read(videos.plan_choices)
        still = {p for _, p in plans}
        return gr.update(choices=plans, value=[p for p in ticked or [] if p in still])

    yes_btn.click(delete, plan_pick, [confirm_row, plan_pick]).then(
        lambda: gr.update(choices=read(videos.plan_choices)), None, plan_pick).then(
        bulk_list, bulk_pick, bulk_pick)
    bulk_box.expand(bulk_list, bulk_pick, bulk_pick)
    bulk_drafts.click(lambda: [p for p, s in read(videos.plan_statuses).items() if s == "draft"],
                      None, bulk_pick)
    bulk_none.click(lambda: [], None, bulk_pick)

    def ask_bulk(ticked):
        if not ticked:
            gr.Info("Tick the plans to delete first.")
            return gr.Row(visible=False), ""
        statuses = read(videos.plan_statuses)
        rendered = sum(statuses.get(p) == "rendered" for p in ticked)
        made = (f"{rendered} of them {'is' if rendered == 1 else 'are'} rendered: the finished "
                "videos stay in your output folder, and their clips stay marked as used. "
                if rendered else "")
        return gr.Row(visible=True), (
            f"**Delete {len(ticked)} plan{'s' if len(ticked) != 1 else ''} from the list?** "
            f"{made}Their clips, your ratings and what AI-Editor learns from them all stay. "
            "This can't be undone.")

    bulk_btn.click(ask_bulk, bulk_pick, [bulk_confirm, bulk_note])
    bulk_no.click(lambda: gr.Row(visible=False), None, bulk_confirm)
    bulk_pick.input(lambda: gr.Row(visible=False), None, bulk_confirm)

    def delete_ticked(ticked, current):
        from ..recipes.plan import delete_plans

        gone = read(delete_plans, list(ticked or []))
        if gone:
            gr.Info(f"Deleted {gone} plan{'s' if gone != 1 else ''} from the list.")
        plans = read(videos.plan_choices)
        still = {p for _, p in plans}
        keep = current if current in still else (plans[0][1] if plans else None)
        return (gr.Row(visible=False), gr.update(choices=plans, value=[]),
                gr.update(value=keep))

    # As with one plan: first on to a plan that's still there, then the list.
    bulk_yes.click(delete_ticked, [bulk_pick, plan_pick],
                   [bulk_confirm, bulk_pick, plan_pick]).then(
        lambda: gr.update(choices=read(videos.plan_choices)), None, plan_pick)

    # --- Fixing captions, line by line (Phase 2D-2) ------------------------------------------

    from ..analysis import caption_edit

    def line_label(line, src_in: float) -> str:
        mark = " ⊘" if line.hidden else (" ✎" if line.edited else "")
        who = "👥 " if line.friend else ""    # a friend on Discord (Phase 2I)
        return f"{videos.short_clock(max(0.0, line.start - src_in))}{mark}  {who}{line.text}"

    def lines_of(state):
        return read(caption_edit.lines, state["rid"], state["in"], state["out"])

    def lines_radio(state, near: int | None = None):
        """The clip's lines; ``near``: pick the line holding that word again."""
        found = lines_of(state)
        value = None
        if near is not None:
            value = next((ln.key for ln in found if ln.first <= near <= ln.last), None)
        return gr.update(choices=[(line_label(ln, state["in"]), ln.key) for ln in found],
                         value=value)

    def no_lines():
        return (gr.update(visible=False), None, "", gr.update(choices=[], value=None), "",
                gr.update(visible=False))

    lines_outputs = [lines_box, lines_state, lines_info, line_pick, line_txt, remember_row]

    def open_lines(plan_id, evt: gr.EventData):
        row = selected_row(evt)
        plan, _ = read(videos.get_plan, plan_id)
        if plan is None or plan.recipe == "letsplay" or row is None \
                or not 0 <= row < len(plan.segments):
            return no_lines()
        s = plan.segments[row]
        what = "the teaser" if s.kind == "teaser" else f"clip {row + 1}"
        state = {"plan": plan_id, "index": row, "rid": s.recording_id, "in": s.src_in,
                 "out": s.src_out, "what": what}
        found = lines_of(state)
        info = (f"**Captions for {what}**: {len(found)} line(s). " if found else
                f"**Captions for {what}**: nobody talks in it. ")
        info += ("A fix shows in captions, \"You said\" and what the AI writes. Captions are "
                 "only in a video when **Burn in captions** is ticked.")
        return (gr.update(visible=True), state, info,
                gr.update(choices=[(line_label(ln, s.src_in), ln.key) for ln in found],
                          value=None), "", gr.update(visible=False))

    clip_list.click(open_lines, plan_pick, lines_outputs)
    for event in (plan_pick.change, review_tab.select):
        event(no_lines, None, lines_outputs)

    def the_line(state, key):
        if not state or not key:
            return None
        return next((ln for ln in lines_of(state) if ln.key == key), None)

    def pick_line(state, key):
        line = the_line(state, key)
        if line is None:
            return gr.skip(), gr.skip(), gr.skip()
        proxy = read(videos.proxy_of, state["rid"])
        return (line.text, gr.update(value="Show this line" if line.hidden else "Hide this line"),
                videos.player(proxy, max(0.0, line.start - 0.3), line.end + 0.4,
                              note="This caption line."))

    line_pick.input(pick_line, [lines_state, line_pick], [line_txt, hide_line_btn, review_player])
    play_line_btn.click(pick_line, [lines_state, line_pick],
                        [line_txt, hide_line_btn, review_player])

    def line_change(action):
        def apply(plan_id, state, key, text):
            line = the_line(state, key)
            if line is None:
                return (gr.skip(),) * 3 + ("Click a caption line first.", gr.skip(), gr.skip(),
                                           gr.skip())
            what = state.get("what", "this clip")
            label = {"save": f"fixing a caption in {what}",
                     "hide": (f"showing a caption line in {what}" if line.hidden
                              else f"hiding a caption line in {what}"),
                     "back": f"putting back a caption line in {what}"}[action]
            offer = None
            conn = init_db(settings.db_path)
            try:
                with history.step(conn, plan_id, label, words=(state["rid"], line.first,
                                                               line.last)):
                    if action == "save":
                        saved = caption_edit.save_line(conn, state["rid"], line.first,
                                                       line.last, text or "")
                        message, offer = saved.message, saved.offer
                    elif action == "hide":
                        caption_edit.hide_line(conn, state["rid"], line.first, line.last,
                                               not line.hidden)
                        message = ("Shown in captions again." if line.hidden else
                                   "Hidden from captions. Its words stay in the transcript.")
                    else:
                        caption_edit.put_back(conn, state["rid"], line.first, line.last)
                        message = "Put back as it was first heard."
            finally:
                conn.close()
            radio = lines_radio(state, line.first)
            now = next((ln for ln in lines_of(state) if ln.first <= line.first <= ln.last), None)
            row = ((gr.update(visible=True), read(caption_edit.offer_text, *offer)) if offer
                   else (gr.update(visible=False), ""))
            return (radio, now.text if now else gr.skip(),
                    gr.update(value="Show this line" if now and now.hidden else "Hide this line"),
                    message, *row, offer)
        return apply

    line_outputs = [line_pick, line_txt, hide_line_btn, review_msg, remember_row, remember_note,
                    offer_state]
    for button, action in ((save_line_btn, "save"), (hide_line_btn, "hide"),
                           (back_line_btn, "back")):
        button.click(line_change(action), [plan_pick, lines_state, line_pick, line_txt],
                     line_outputs).then(list_view, [plan_pick, sel], list_outputs)
    line_txt.submit(line_change("save"), [plan_pick, lines_state, line_pick, line_txt],
                    line_outputs).then(list_view, [plan_pick, sel], list_outputs)

    def remember(offer, state, key):
        if not offer:
            return gr.update(visible=False), gr.skip(), gr.skip()
        message = read(caption_edit.remember, *offer)
        return (gr.update(visible=False), message,
                lines_radio(state, int(key.split("-")[0])) if state and key else gr.skip())

    remember_yes.click(remember, [offer_state, lines_state, line_pick],
                       [remember_row, review_msg, line_pick])
    remember_no.click(lambda: gr.update(visible=False), None, remember_row)

    # --- Undo and Redo (Phase 2D-1): kept after AI-Editor closes ----------------------------

    def stepper(fn):
        def apply(plan_id):
            if not plan_id:
                return "Pick a plan first."
            return read(fn, plan_id)
        return apply

    for button, fn in ((undo_btn, history.undo), (redo_btn, history.redo)):
        # Everything Review shows about the plan, again, then what was undone.
        (button.click(stepper(fn), plan_pick, undo_note)
         .then(show_plan, plan_pick, plan_outputs)
         .then(show_layout, plan_pick, layout_pick)
         .then(show_effects, plan_pick, effects_box)
         .then(show_moments, plan_pick, moments_box)
         .then(show_between, plan_pick, between_pick)
         .then(show_music, plan_pick, music_box)
         .then(lambda: cut_view(None), None, cut_outputs)
         .then(no_lines, None, lines_outputs)
         .then(list_view, plan_pick, list_outputs)
         .then(lambda note: note, undo_note, review_msg))

    def preview(plan_id, part):
        plan, _ = read(videos.get_plan, plan_id)
        if plan is None:
            return "Pick a plan first."
        number = None
        if plan.recipe == "letsplay":
            if part in (None, ALL_PARTS):
                return "Pick one part to preview (click its row, or choose it under Parts)."
            number = int(part.split()[-1])
        what = f"part {number} of " if number else ""
        return submitted(worker, worker.submit(
            f"Quick preview of {what}{plan.title}", f"preview:{plan_id}:{number}",
            tasks.quick_preview(settings, plan_id, number)))

    preview_btn.click(preview, [plan_pick, part_pick], review_msg)

    def chosen_parts(part):
        return None if part in (None, ALL_PARTS) else [int(part.split()[-1])]

    def render(plan_id, captions, episode, part):
        plan, _ = read(videos.get_plan, plan_id)
        if plan is None:
            return "Pick a plan first."
        if plan.recipe == "letsplay" and not episode:
            return "Fill in the episode number first."
        return submitted(worker, worker.submit(
            f"Rendering {plan.title}", f"render:{plan_id}",
            tasks.render(settings, plan_id, captions=bool(captions),
                         episode=int(episode) if episode else None, parts=chosen_parts(part))))

    render_btn.click(render, [plan_pick, captions_box, episode_box, part_pick], finish_msg)

    def finished_videos(plan, captions, episode, part) -> list[Path]:
        from ..render import parts as lp
        from ..render.final import video_path

        if plan.recipe != "letsplay":
            return [video_path(settings, plan, captions=bool(captions))]
        if not episode:
            return []
        numbers = chosen_parts(part) or lp.part_numbers(plan)
        return [lp.part_path(settings, plan, int(episode), n, captions=bool(captions))
                for n in numbers]

    def open_video(plan_id, captions, episode, part):
        plan, _ = read(videos.get_plan, plan_id)
        if plan is None:
            return "Pick a plan first."
        made = [p for p in finished_videos(plan, captions, episode, part) if p.is_file()]
        if not made:
            return ("Not rendered yet" + (" with captions" if captions else " without captions")
                    + ". Press Render first.")
        os.startfile(made[0])  # noqa: S606 -- the PC's video player, on our own file
        return f"Opened {made[0].name}" + (f" (and {len(made) - 1} more part(s) in "
                                           f"{made[0].parent})" if len(made) > 1 else "") + "."

    open_btn.click(open_video, [plan_pick, captions_box, episode_box, part_pick], finish_msg)

    def export(plan_id, episode, part):
        from ..export.timeline import export_plan

        plan, _ = read(videos.get_plan, plan_id)
        if plan is None:
            return "Pick a plan first."
        if plan.recipe == "shorts":
            return ("Shorts are finished here: the tall layout and captions don't carry over to "
                    "Resolve, so there's nothing to export (manual 19.2b). Render it instead.")
        if plan.recipe == "letsplay" and not episode:
            return "Fill in the episode number first."
        try:
            result = read(export_plan, settings, plan, episode=int(episode) if episode else None,
                          parts=chosen_parts(part), note=clip_note)
        except AIEditorError as exc:
            return exc.user_message()
        subprocess.Popen(["explorer", "/select,", str(result.saved[0])])  # noqa: S603,S607
        lines = ["Saved (the folder is open):", *[f"- `{p.name}`" for p in result.saved],
                 "In DaVinci Resolve: File > Import > Timeline, and pick the .fcpxml (manual 19.3)."]
        if result.missing:
            lines.append(f"Resolve won't find {'; '.join(result.missing)}: relink it there.")
        return "\n".join(lines)

    export_btn.click(export, [plan_pick, episode_box, part_pick], finish_msg)

    # --- Publish -------------------------------------------------------------------------

    def publish_part(plan, part) -> int | None:
        """A Let's Play shows one part's text: the one chosen, or part 1."""
        if plan is None or plan.recipe != "letsplay":
            return None
        from ..render import parts as lp

        numbers = lp.part_numbers(plan)
        chosen = chosen_parts(part)
        return chosen[0] if chosen else (numbers[0] if numbers else None)

    def show_publish(plan_id, part):
        from .. import publish

        plan, _ = read(videos.get_plan, plan_id)
        empty = gr.update(choices=[], value=None)
        if plan is None:
            return "", empty, "", "", "", gr.Gallery(value=[], visible=True),                 gr.Row(visible=False), ""
        number = publish_part(plan, part)
        made = publish.saved(plan, number)
        which = f"part {number}" if number else "this Short" if plan.recipe == "shorts" \
            else "this video"
        link_row = gr.Row(visible=plan.recipe != "shorts")
        link = publish.link_of(plan, number)
        full, from_video = (read(publish.full_video_link, plan) if plan.recipe == "shorts"
                            else ("", ""))
        if plan.recipe == "shorts" and from_video:
            source = (f" It's from **{from_video}**: " + (
                "its link goes in the description." if full else
                "paste that video's YouTube link in its Publish section, and the description "
                "here links to it."))
        else:
            source = ""
        if made is None:
            if plan.recipe == "shorts":
                note = (f"Nothing written for {which} yet. **Write titles, description and "
                        "chapters** asks the local AI for a title, a line or two and hashtags "
                        "(a few seconds; Shorts have no chapters or thumbnail).")
            else:
                note = (f"Nothing written for {which} yet. **Write titles, description and "
                        "chapters** asks the local AI (about a minute, with the thumbnails). Its "
                        "summaries of the clips are what it writes from.")
            return note + source, empty, "", "", "", gallery(plan, []), link_row, link
        note = f"For {which}, written {made.made_at[:16].replace('T', ' ')} (UTC)." + source
        if publish.is_stale(plan, number, made):
            note += (" **The video has changed since, so the chapter times may be off: write "
                     "it again.**")
        if plan.recipe == "letsplay" and len(publish_parts(plan)) > 1:
            note += " Choose another part under **Parts** to see its text."
        return (note, gr.update(choices=made.titles, value=None),
                made.title or (made.titles[0] if made.titles else ""),
                publish.description_text(settings, made, full), ", ".join(publish.tags_of(made)),
                gallery(plan, [(str(t.path), f"{t.rating}/10 {t.reason}")
                               for t in made.thumbnails if t.path.is_file()]),
                link_row, link)

    def gallery(plan, pictures):
        return gr.Gallery(value=pictures, visible=plan.recipe != "shorts")

    def publish_parts(plan) -> list[str]:
        return list(plan.publish)

    publish_outputs = [publish_msg, title_pick, title_box, desc_box, tags_box, thumbs, link_row,
                       link_box]
    plan_pick.change(show_publish, [plan_pick, part_pick], publish_outputs)
    part_pick.change(show_publish, [plan_pick, part_pick], publish_outputs)
    review_tab.select(show_publish, [plan_pick, part_pick], publish_outputs)
    ui.load(show_publish, [plan_pick, part_pick], publish_outputs)
    title_pick.input(lambda t: t or gr.skip(), title_pick, title_box)

    def write_publish(plan_id, episode, part):
        plan, _ = read(videos.get_plan, plan_id)
        if plan is None:
            return "Pick a plan first."
        if not settings.llm.enabled:
            return "The local AI is switched off in Settings (AI)."
        if plan.recipe == "letsplay" and not episode:
            return "Fill in the episode number first: it goes in the titles."
        return submitted(worker, worker.submit(
            f"Writing the upload text for {plan.title}", f"publish:{plan_id}:{part}",
            tasks.write_publish(settings, plan_id, parts=chosen_parts(part),
                                episode=int(episode) if episode else None)))

    publish_btn.click(write_publish, [plan_pick, episode_box, part_pick], publish_msg)

    def save_link(plan_id, part, link):
        from .. import publish

        conn = init_db(settings.db_path)
        try:
            plan, status = videos.get_plan(conn, plan_id)
            if plan is None:
                return "Pick a plan first."
            publish.set_link(plan, publish_part(plan, part), link or "")
            save_plan(conn, plan, status)
        finally:
            conn.close()
        return ("Saved. Shorts from this video now link to it." if (link or "").strip()
                else "Link removed.")

    link_btn.click(save_link, [plan_pick, part_pick, link_box], publish_msg)

    def keep_changes(plan_id, part, episode, title, description, tags):
        from .. import publish

        conn = init_db(settings.db_path)
        try:
            found = videos.get_plan(conn, plan_id)
            plan, status = found
            if plan is None:
                return "Pick a plan first."
            number = publish_part(plan, part)
            made = publish.saved(plan, number)
            if made is None:
                return "Write the text first, then change it."
            made.edited = {"title": (title or "").strip(), "description": description or "",
                           "tags": [t.strip() for t in (tags or "").split(",") if t.strip()]}
            plan.publish[publish.key_of(number)] = made.as_dict()
            save_plan(conn, plan, status)
        finally:
            conn.close()
        beside = tasks.publish_videos(settings, plan, number, int(episode) if episode else None)
        for video in beside:
            publish.write_text_beside(settings, made, video)
        return "Kept." + (f" Saved beside the video too: {beside[0].with_suffix('.txt').name}."
                          if beside else " It's saved beside the video when you render it.")

    keep_btn.click(keep_changes, [plan_pick, part_pick, episode_box, title_box, desc_box,
                                  tags_box], publish_msg)

    # --- keeping up with finished jobs ---------------------------------------------------

    def tick(seen_version, done, recording, plan_id, show, part, deleted=False):
        version = worker.version
        if version == seen_version:
            return (gr.skip(),) * 19 + (done, seen_version)
        done = dict(done)
        new_plan = preview_file = None
        rated = wrote = False
        for task in worker.snapshot():
            if task.status != DONE:
                continue
            if "publish" in task.result and task.id > done.get("publish", 0):
                done["publish"] = task.id
                wrote = wrote or task.result["publish"] == plan_id
            if "rated" in task.result and task.id > done.get("rated", 0):
                done["rated"] = task.id
                rated = rated or (recording is not None and task.result["rated"] == int(recording))
            if "plan_id" in task.result and task.id > done["plan_id"]:
                new_plan, done["plan_id"] = task.result["plan_id"], task.id
            if "preview" in task.result and task.id > done["preview"]:
                preview_file, done["preview"] = task.result["preview"], task.id
        recordings = read(videos.analysed_choices, settings)
        clip_recs = read(videos.analysed_choices, settings, deleted=bool(deleted))
        plans = read(videos.plan_choices)
        ids = [p[1] for p in plans]
        chosen = new_plan if new_plan in ids else plan_id if plan_id in ids else \
            (ids[0] if ids else None)
        plan, status = read(videos.get_plan, chosen)
        # The AI's verdicts just arrived for the recording on show: fill them in.
        clip_view = clips_view(recording, show) if rated else (gr.skip(),) * 3
        publish_view = show_publish(plan_id, part) if wrote else (gr.skip(),) * 8
        return (
            *clip_view,
            *publish_view,
            gr.update(choices=clip_recs,
                      value=recording if recording in [r[1] for r in clip_recs] else None),
            gr.update(choices=plans, value=chosen),
            gr.update(choices=read(videos.analysed_choices, settings, lets_play=False)),
            gr.update(choices=episode_choices()),
            gr.update(choices=recordings),
            videos.player(preview_file, note="Quick preview") if preview_file else gr.skip(),
            "Your new plan is open below." if new_plan else gr.skip(),
            videos.plan_summary(plan, status) if plan is not None else gr.skip(),
            done, version,
        )

    timer.tick(tick, [seen, handled, clip_rec, plan_pick, clip_show, part_pick, clip_deleted],
               [clip_tbl, clip_ids, clip_counts, *publish_outputs, clip_rec, plan_pick, hl_from,
                lp_rec, sh_rec,
                review_player, review_msg, summary, handled, seen],
               show_progress="hidden")
