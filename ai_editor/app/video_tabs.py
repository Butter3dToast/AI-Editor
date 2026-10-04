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
from ..recipes import review
from ..recipes.plan import save_plan
from . import library, tasks, videos
from .worker import DONE, Worker, submitted

ALL_STREAMS = "All my streams"
ALL_PARTS = "All parts"
WHOLE_VIDEO = "Quick preview of the whole video"
ONE_PART = "Quick preview of the selected part"
PLAN_WIDTHS = ["6%", "10%", "16%", "12%", "9%", "8%", "39%"]
PART_WIDTHS = ["10%", "20%", "45%", "25%"]


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

    # --- Clips -------------------------------------------------------------------------
    with gr.Tab("Clips", id="clips"):
        with gr.Row():
            clip_rec = gr.Dropdown(choices=read(videos.analysed_choices, settings), value=None,
                                   label="Recording", scale=3)
            clip_show = gr.Radio(videos.SHOW, value=videos.SHOW[0], label="Show", scale=2)
            ai_btn = gr.Button("Rate with AI", scale=1)
        clip_ids = gr.State([])
        clip_sel = gr.State(None)
        clip_counts = gr.Markdown()
        with gr.Row():
            with gr.Column(scale=3):
                clip_tbl = gr.Dataframe(headers=videos.CLIP_COLUMNS, interactive=False, wrap=True,
                                        max_height=560,
                                        column_widths=["4%", "10%", "7%", "7%", "6%", "13%",
                                                       "22%", "19%", "6%", "6%"])
            with gr.Column(scale=2):
                clip_player = gr.HTML(videos.player(None, note="Pick a recording, then click a "
                                                               "clip to watch it here."))
                clip_info = gr.Markdown()
                with gr.Row():
                    good_btn = gr.Button("👍 Good clip")
                    bad_btn = gr.Button("👎 Not good")
                    unrate_btn = gr.Button("Clear rating")
                clip_msg = gr.Markdown()

    # --- Create video --------------------------------------------------------------------
    with gr.Tab("Create video", id="create"):
        kind = gr.Radio(["Highlights", "Let's Play"], value="Highlights", label="What to make")
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
        with gr.Group(visible=False) as lp_group:
            lp_rec = gr.Dropdown(choices=episode_choices(), value=None, label="Episode recording",
                                 info="Trimmed (loading screens, silent menus, long pauses) and "
                                      "split into parts of about "
                                      f"{settings.lets_play.target_min:.0f} minutes.")
        make_btn = gr.Button("Make the plan", variant="primary")
        make_msg = gr.Markdown()

    # --- Review --------------------------------------------------------------------------
    with gr.Tab("Review", id="review") as review_tab:
        plan_pick = gr.Dropdown(choices=plans_now, value=plans_now[0][1] if plans_now else None,
                                label="Video plan", info="Newest first")
        summary = gr.Markdown()
        sel = gr.State(None)
        # Kept inside a tab: anything placed straight in the tab bar shifts the
        # tabs after it, and Gradio 6 then showed Storage and Settings twice.
        seen = gr.State(-1)
        handled = gr.State({"plan_id": 0, "preview": 0})
        add_spots = gr.State({})
        with gr.Row():
            with gr.Column(scale=3):
                plan_tbl = gr.Dataframe(headers=videos.PLAN_COLUMNS, interactive=False, wrap=True,
                                        max_height=520, column_widths=PLAN_WIDTHS)
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
                               "whole video."))
                preview_btn = gr.Button(WHOLE_VIDEO)
        gr.Markdown("### Finish it")
        with gr.Row():
            captions_box = gr.Checkbox(value=settings.captions.highlights,
                                       label="Burn in captions (your words)")
            episode_box = gr.Number(label="Episode number", precision=0, visible=False)
            part_pick = gr.Dropdown(choices=[ALL_PARTS], value=ALL_PARTS, label="Parts",
                                    visible=False)
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
        thumbs = gr.Gallery(label="Thumbnail frames, best first (full size, in "
                                  "output/thumbnails)", columns=3, height=420,
                            buttons=["download", "fullscreen"], interactive=False)

    # --- Clips: handlers ----------------------------------------------------------------

    def clips_view(recording_id, show):
        """The table, its clip ids, and the counts line."""
        conn = init_db(settings.db_path)
        try:
            lengths = videos.video_lengths(conn, settings, int(recording_id))
            rows, ids = videos.clip_table(conn, int(recording_id), show, lengths)
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
            message = read(videos.rate, clip_id, rating)
            table, ids, counts = clips_view(recording_id, show)
            if rating == 1:
                message += (" It goes into your next highlight video. To put it in one you've "
                            "already made, use 'Add a clip' in Review.")
            return table, ids, message, counts
        return apply

    for button, rating in ((good_btn, 1), (bad_btn, -1), (unrate_btn, None)):
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

    # --- Create video: handlers ---------------------------------------------------------

    kind.change(lambda k: (gr.update(visible=k == "Highlights"), gr.update(visible=k != "Highlights")),
                kind, [hl_group, lp_group])

    def make(what, game, chosen, minutes, episode_rec, reuse=False):
        if what == "Highlights":
            game = None if not game or game == ALL_STREAMS else canonical_game(game)
            ids = [int(x) for x in chosen] if chosen else None
            label = game or "stream"
            return submitted(worker, worker.submit(
                f"Making a {label} highlights plan", f"make:highlights:{game}",
                tasks.make_highlights(settings, game=game, recording_ids=ids,
                                      minutes=float(minutes) if minutes else None,
                                      reuse=bool(reuse))))
        if episode_rec is None:
            return "Pick the episode's recording first."
        return submitted(worker, worker.submit(
            f"Making a Let's Play plan from #{episode_rec}", f"make:letsplay:{episode_rec}",
            tasks.make_letsplay(settings, int(episode_rec))))

    make_btn.click(lambda *a: make(*a) + " When it's finished, it opens in Review.",
                   [kind, hl_game, hl_from, hl_minutes, lp_rec, hl_reuse], make_msg)

    # --- Review: handlers ---------------------------------------------------------------

    def table_for(plan):
        if plan.recipe == "letsplay":
            return pd.DataFrame(videos.part_table(plan), columns=videos.PART_COLUMNS)
        return pd.DataFrame(read(videos.plan_table, plan), columns=videos.PLAN_COLUMNS)

    def shaped_table(plan):
        widths = PART_WIDTHS if plan is not None and plan.recipe == "letsplay" else PLAN_WIDTHS
        return gr.Dataframe(value=table_for(plan) if plan is not None
                            else pd.DataFrame(columns=videos.PLAN_COLUMNS), column_widths=widths)

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
        else:
            extra = read(review.addable, settings, plan)
        return (videos.plan_summary(plan, status), shaped_table(plan),
                *show_editing(not lets_play, extra),
                gr.Number(visible=lets_play, value=episode),
                gr.Dropdown(visible=lets_play, choices=[ALL_PARTS, *parts], value=ALL_PARTS),
                gr.Checkbox(value=settings.captions.lets_play if lets_play
                            else settings.captions.highlights),
                gr.Button(value=ONE_PART if lets_play else WHOLE_VIDEO),
                empty, None, "", "", spots(extra))

    def spots(extra) -> dict:
        """Where each addable clip is, to play it: {clip id: [recording, in, out]}."""
        return {e[1]: list(e[2:]) for e in extra}

    def show_editing(visible: bool, extra) -> list:
        return [gr.update(visible=visible, choices=[e[:2] for e in extra], value=None)
                if part is add_pick else gr.update(visible=visible) for part in highlight_only]

    plan_outputs =[summary, plan_tbl, *highlight_only, episode_box, part_pick, captions_box,
                    preview_btn, review_player, sel, review_msg, finish_msg, add_spots]
    plan_pick.change(show_plan, plan_pick, plan_outputs)
    ui.load(show_plan, plan_pick, plan_outputs)
    # Again on opening the tab: Gradio 6 drops "hide this" sent to a tab that
    # isn't on screen yet, so a Let's Play could open showing highlight buttons.
    review_tab.select(show_plan, plan_pick, plan_outputs)

    def pick_row(plan_id, evt: gr.SelectData):
        row = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        plan, _ = read(videos.get_plan, plan_id)
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
            conn = init_db(settings.db_path)
            try:
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
    add_btn.click(edit("add"), [plan_pick, sel, add_pick], edit_outputs)
    sort_btn.click(edit("sort"), [plan_pick, sel], edit_outputs)
    move_to_btn.click(edit("move_to"), [plan_pick, sel, position], edit_outputs)
    remove_btn.click(edit("remove"), [plan_pick, sel], edit_outputs)
    up_btn.click(edit("up"), [plan_pick, sel], edit_outputs)
    down_btn.click(edit("down"), [plan_pick, sel], edit_outputs)
    teaser_btn.click(edit("teaser"), [plan_pick, sel], edit_outputs)
    moment_btn.click(edit("moment"), [plan_pick, sel, moment], edit_outputs)

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
            return "", empty, "", "", "", []
        number = publish_part(plan, part)
        made = publish.saved(plan, number)
        which = f"part {number}" if number else "this video"
        if made is None:
            note = (f"Nothing written for {which} yet. **Write titles, description and "
                    "chapters** asks the local AI (about a minute, with the thumbnails). Its "
                    "summaries of the clips are what it writes from.")
            return note, empty, "", "", "", []
        note = f"For {which}, written {made.made_at[:16].replace('T', ' ')} (UTC)."
        if publish.is_stale(plan, number, made):
            note += (" **The video has changed since, so the chapter times may be off: write "
                     "it again.**")
        if plan.recipe == "letsplay" and len(publish_parts(plan)) > 1:
            note += " Choose another part under **Parts** to see its text."
        return (note, gr.update(choices=made.titles, value=None),
                made.title or (made.titles[0] if made.titles else ""),
                publish.description_text(settings, made), ", ".join(publish.tags_of(made)),
                [(str(t.path), f"{t.rating}/10 {t.reason}") for t in made.thumbnails
                 if t.path.is_file()])

    def publish_parts(plan) -> list[str]:
        return list(plan.publish)

    publish_outputs = [publish_msg, title_pick, title_box, desc_box, tags_box, thumbs]
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

    def tick(seen_version, done, recording, plan_id, show, part):
        version = worker.version
        if version == seen_version:
            return (gr.skip(),) * 16 + (done, seen_version)
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
        plans = read(videos.plan_choices)
        ids = [p[1] for p in plans]
        chosen = new_plan if new_plan in ids else plan_id if plan_id in ids else \
            (ids[0] if ids else None)
        plan, status = read(videos.get_plan, chosen)
        # The AI's verdicts just arrived for the recording on show: fill them in.
        clip_view = clips_view(recording, show) if rated else (gr.skip(),) * 3
        publish_view = show_publish(plan_id, part) if wrote else (gr.skip(),) * 6
        return (
            *clip_view,
            *publish_view,
            gr.update(choices=recordings,
                      value=recording if recording in [r[1] for r in recordings] else None),
            gr.update(choices=plans, value=chosen),
            gr.update(choices=read(videos.analysed_choices, settings, lets_play=False)),
            gr.update(choices=episode_choices()),
            videos.player(preview_file, note="Quick preview") if preview_file else gr.skip(),
            "Your new plan is open below." if new_plan else gr.skip(),
            videos.plan_summary(plan, status) if plan is not None else gr.skip(),
            done, version,
        )

    timer.tick(tick, [seen, handled, clip_rec, plan_pick, clip_show, part_pick],
               [clip_tbl, clip_ids, clip_counts, *publish_outputs, clip_rec, plan_pick, hl_from,
                lp_rec,
                review_player, review_msg, summary, handled, seen],
               show_progress="hidden")
