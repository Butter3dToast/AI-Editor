"""The Storage and Settings tabs (Phase 1H-3).

What the creator chose (2026-10-03): Storage frees only the analysis working
files; Settings shows the folders and the main options for highlights,
captions, Let's Plays, the Stream Companion and Twitch. Changes go to the
private settings.local.yaml, so settings.yaml and its notes stay as they are,
and take effect straight away.
"""

from __future__ import annotations

import os
from pathlib import Path

import gradio as gr
import pandas as pd

from ..config import Settings, save_local_settings
from ..db import init_db
from ..errors import AIEditorError
from . import storage
from .worker import Worker

ORDERS = [("As it happened, the teaser's moment saved for last", "timeline"),
          ("Balanced: strong and calmer clips in turn", "balanced"),
          ("Strictly as it happened", "chronological"),
          ("Building up to the best", "best_last")]
VOD_DAYS = [("Regular: 7 days", 7), ("Affiliate: 14 days", 14),
            ("Partner, Turbo or Prime: 60 days", 60)]
FOLDERS = {"raw": "Your recordings (raw)", "cache": "AI-Editor's working copies (cache)",
           "output": "Finished videos and timelines (output)", "assets": "Assets",
           "models": "AI models"}
CHANGEABLE = ("raw", "output")  # moving the cache or models would mean moving their files too


def part_lengths(settings: Settings, minutes: float) -> dict[tuple[str, str], object]:
    """A new Let's Play part length, with the range around it kept consistent."""
    lp = settings.lets_play
    low, high = round(minutes * 5 / 6, 1), round(minutes * 7 / 6, 1)
    preferred = max(lp.story_extension_preferred_max_min, high)
    return {("lets_play", "target_min"): minutes,
            ("lets_play", "normal_range_min"): [low, high],
            ("lets_play", "story_extension_preferred_max_min"): preferred,
            ("lets_play", "story_extension_hard_max_min"):
                max(lp.story_extension_hard_max_min, preferred)}


def apply(live: Settings, new: Settings) -> None:
    """Make the running window use the new settings, everywhere at once."""
    for name in type(live).model_fields:
        setattr(live, name, getattr(new, name))


def build(settings: Settings, worker: Worker) -> None:
    """Add the two tabs. Call inside the window's gr.Tabs()."""

    # --- Storage ---------------------------------------------------------------------
    with gr.Tab("Storage", id="space") as storage_tab:
        overview = gr.Markdown()
        usage_tbl = gr.Dataframe(headers=storage.COLUMNS, interactive=False, wrap=True,
                                 max_height=420,
                                 column_widths=["5%", "24%", "12%", "12%", "11%", "11%", "11%",
                                                "14%"])
        gr.Markdown("**Free working files** deletes what analysis left behind (prepared sound, "
                    "AI-separated voices, scratch files): about 1-2 GB per stream. Nothing is "
                    "lost: clips, ratings, plans, preview copies and sound tracks all stay, and "
                    "your recordings are never touched.")
        with gr.Row():
            tidy_pick = gr.Dropdown(choices=[], value=[], multiselect=True, scale=4,
                                    label="Recordings to tidy",
                                    info="Only analysed recordings are listed.")
            all_btn = gr.Button("Pick all", size="sm", scale=0, min_width=100)
        with gr.Row():
            free_btn = gr.Button("Free working files", variant="primary")
            look_btn = gr.Button("Look again")
        storage_msg = gr.Markdown()

    # --- Settings ----------------------------------------------------------------------
    with gr.Tab("Settings", id="options"):
        gr.Markdown("Changes are saved on this PC only (`config/settings.local.yaml`) and work "
                    "straight away. Everything else is in `config/settings.yaml`.")
        folder_boxes = {}
        with gr.Accordion("Folders", open=True):
            for name, label in FOLDERS.items():
                with gr.Row():
                    folder_boxes[name] = gr.Textbox(
                        value=str(getattr(settings.folders, name)), label=label, scale=5,
                        interactive=name in CHANGEABLE,
                        info=None if name in CHANGEABLE else
                        "Set in settings.yaml: moving it means moving its files too.")
                    open_btn = gr.Button("Open", size="sm", scale=0, min_width=80)
                    open_btn.click(lambda path: _open_folder(path), folder_boxes[name], None)
        h, c, lp = settings.highlights, settings.captions, settings.lets_play
        with gr.Accordion("Highlights", open=True):
            with gr.Row():
                hl_minutes = gr.Number(value=h.target_length_min, minimum=1, maximum=60,
                                       label="Length in minutes",
                                       info="The least a highlight video will be.")
                hl_bar = gr.Slider(0.2, 0.9, value=h.min_clip_score, step=0.01,
                                   label="Quality bar",
                                   info="Clips under it aren't picked. 👍 clips and marked "
                                        "moments always go in.")
            hl_order = gr.Radio(ORDERS, value=h.ordering, label="Order of the clips")
        with gr.Accordion("Captions", open=True):
            with gr.Row():
                cap_hl = gr.Checkbox(value=c.highlights, label="Burn in captions on highlights")
                cap_lp = gr.Checkbox(value=c.lets_play, label="Burn in captions on Let's Plays")
        with gr.Accordion("Let's Play", open=True):
            with gr.Row():
                lp_minutes = gr.Number(value=lp.target_min, minimum=10, maximum=90,
                                       label="Part length in minutes",
                                       info="Parts end at a natural break near this.")
                lp_card = gr.Textbox(value=lp.title_card, label="Title card on each part",
                                     placeholder="Empty for none, or e.g. Ep {episode} - Part {part}",
                                     info="{episode} and {part} are filled in.")
        with gr.Accordion("Stream Companion and Twitch", open=True):
            with gr.Row():
                comp_sound = gr.Checkbox(
                    value=settings.companion.confirmation_sound,
                    label="Click sound when you mark a moment",
                    info="Off by default: on 26 Sep it reached the stream through your mic.")
                comp_volume = gr.Slider(0.05, 1.0, value=settings.companion.sound_volume,
                                        step=0.05, label="Click volume")
            with gr.Row():
                vod_days = gr.Dropdown(VOD_DAYS, value=settings.twitch.vod_keep_days,
                                       allow_custom_value=True,
                                       label="How long Twitch keeps your VODs",
                                       info="For the 'days left on Twitch' warnings.")
                space_gb = gr.Number(value=settings.storage.low_space_warning_gb, minimum=0,
                                     label="Warn when free space drops below (GB)")
        save_btn = gr.Button("Save settings", variant="primary")
        settings_msg = gr.Markdown()

    # --- Storage: handlers -----------------------------------------------------------

    def read_usage():
        conn = init_db(settings.db_path)
        try:
            return storage.recording_usage(conn, settings)
        finally:
            conn.close()

    def tidy_choices(usages):
        return [(f"#{u.recording_id}  {u.title}  ({storage.size_text(u.working)} to free)"
                 if u.recording_id is not None else
                 f"Leftover folder {u.folder.name[:8]}...  ({storage.size_text(u.working)})",
                 u.recording_id if u.recording_id is not None else u.folder.name)
                for u in usages if u.working and u.status in ("Analysed", "Leftover")]

    def look(message=""):
        usages = read_usage()
        return (storage.overview(settings, usages),
                pd.DataFrame(storage.usage_table(usages), columns=storage.COLUMNS),
                gr.update(choices=tidy_choices(usages), value=[]), message)

    storage_outputs = [overview, usage_tbl, tidy_pick, storage_msg]
    storage_tab.select(look, None, storage_outputs)
    look_btn.click(look, None, storage_outputs)
    all_btn.click(lambda: gr.update(value=[c[1] for c in tidy_choices(read_usage())]), None,
                  tidy_pick)

    def free(chosen):
        if not chosen:
            return look("Pick the recordings to tidy first.")
        if worker.busy():
            return look("A job is running and may be using these files. Free them when "
                        "Jobs is quiet.")
        freed = storage.free_working_files(settings, read_usage(), set(chosen))
        return look(f"Freed **{storage.size_text(freed)}**.")

    free_btn.click(free, tidy_pick, storage_outputs)

    # --- Settings: handlers ----------------------------------------------------------

    def save(raw, output, minutes, bar, order, cap_h, cap_l, part, card, sound, volume, days,
             space):
        raw_path, output_path = Path(str(raw).strip().strip('"')), Path(str(output).strip().strip('"'))
        if not raw_path.is_dir():
            return f"There's no folder at {raw_path}."
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return f"Couldn't use {output_path} for finished videos: {exc}"
        changes = {
            ("folders", "raw"): str(raw_path), ("folders", "output"): str(output_path),
            ("highlights", "target_length_min"): float(minutes),
            ("highlights", "min_clip_score"): round(float(bar), 2),
            ("highlights", "ordering"): order,
            ("captions", "highlights"): bool(cap_h), ("captions", "lets_play"): bool(cap_l),
            ("lets_play", "title_card"): card or "",
            ("companion", "confirmation_sound"): bool(sound),
            ("companion", "sound_volume"): round(float(volume), 2),
            ("twitch", "vod_keep_days"): int(days),
            ("storage", "low_space_warning_gb"): float(space),
        }
        if float(part) != settings.lets_play.target_min:
            changes.update(part_lengths(settings, float(part)))
        # Only what changed: the rest keeps following settings.yaml.
        changes = {k: v for k, v in changes.items() if _plain(current(settings, k)) != _plain(v)}
        if not changes:
            return "Nothing changed."
        moved = output_path != settings.folders.output
        try:
            new = save_local_settings(settings.source_path, changes)
        except AIEditorError as exc:
            return f"Not saved: {exc.user_message()}"
        apply(settings, new)
        note = " Close and reopen AI-Editor to play videos from the new output folder here." \
            if moved else ""
        return "Saved. New highlight plans and renders use these from now on." + note

    save_btn.click(save, [folder_boxes["raw"], folder_boxes["output"], hl_minutes, hl_bar,
                          hl_order, cap_hl, cap_lp, lp_minutes, lp_card, comp_sound, comp_volume,
                          vod_days, space_gb], settings_msg)


def current(settings: Settings, key: tuple[str, str]):
    return getattr(getattr(settings, key[0]), key[1])


def _plain(value):
    """Compare settings as they'd be written: paths as text, pairs as lists."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def _open_folder(path: str) -> None:
    folder = Path(str(path).strip().strip('"'))
    if folder.is_dir():
        os.startfile(folder)  # noqa: S606 -- File Explorer on the creator's own folder
