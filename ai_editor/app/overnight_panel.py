"""Overnight work in the window (3B): the morning note at the top, and its
section in Settings."""

from __future__ import annotations

import gradio as gr

from ..config import Settings, save_local_settings
from ..db import init_db
from ..errors import AIEditorError
from . import overnight
from .worker import Worker, submitted


def _read(settings: Settings, fn, *args):
    conn = init_db(settings.db_path)
    try:
        return fn(conn, *args)
    finally:
        conn.close()


def build_note(settings: Settings, ui: gr.Blocks) -> None:
    """The morning note, under the title, until you press OK."""
    with gr.Row(visible=False) as row:
        note = gr.Markdown()
        ok = gr.Button("OK", size="sm", scale=0, min_width=80)
    shown = gr.State(None)

    def look():
        found = _read(settings, overnight.morning_note, settings)
        if found is None:
            return gr.update(visible=False), "", None
        night_id, text = found
        return gr.update(visible=True), "🌙 " + text, night_id

    def close(night_id):
        if night_id is not None:
            _read(settings, overnight.mark_seen, night_id)
        return gr.update(visible=False), None

    ui.load(look, None, [row, note, shown])
    gr.Timer(30.0).tick(look, None, [row, note, shown], show_progress="hidden")
    ok.click(close, shown, [row, shown])


def card_text(settings: Settings) -> str:
    load = overnight.gpu_load()
    if load is None:
        return "Graphics card: couldn't read it (nvidia-smi not found)."
    level = settings.overnight.gpu_busy_percent
    return (f"Graphics card right now: **{load:.0f}%** "
            f"({'busy: it would wait' if load >= level else 'free'} at your level of {level}%).")


def build_settings(settings: Settings, worker: Worker) -> None:
    """Settings, Overnight work."""
    n = settings.overnight
    with gr.Accordion("Overnight work", open=True):
        gr.Markdown(
            "While you sleep, AI-Editor imports new recordings from your raw folder, analyses "
            "them and drafts their plans for Review: a highlight plan and Shorts for each "
            "stream, the parts for each Let's Play episode. **It never renders and never "
            "deletes anything.** AI-Editor must be open at the start time.\n\n"
            "It waits while OBS records or streams, and while the graphics card is busy (a "
            "game). It never looks at which programs are running.")
        with gr.Row():
            night_on = gr.Checkbox(value=n.enabled, label="Work overnight")
            night_start = gr.Textbox(value=n.start, label="Start at", max_lines=1,
                                     info="24-hour clock, e.g. 02:00")
            night_stop = gr.Textbox(value=n.stop_by or "", label="Stop by", max_lines=1,
                                    placeholder="Empty: until it's done",
                                    info="e.g. 10:00: stops then, even if not finished")
        with gr.Row():
            night_level = gr.Slider(10, 100, value=n.gpu_busy_percent, step=5,
                                    label="Wait while the graphics card is busier than (%)",
                                    info="Your card idles at about 26-38%. A game goes well "
                                         "above.")
            night_shorts = gr.Number(value=n.shorts, minimum=0, maximum=10, precision=0,
                                     label="Shorts per new stream")
        card = gr.Markdown()
        with gr.Row():
            card_btn = gr.Button("Read the graphics card", size="sm")
            save_btn = gr.Button("Save overnight work", variant="primary", size="sm")
            now_btn = gr.Button("Run it now", size="sm")
        night_msg = gr.Markdown(_read(settings, overnight.last_night))

    card_btn.click(lambda: card_text(settings), None, card)

    def save(on, start, stop, level, shorts):
        changes = {("overnight", "enabled"): bool(on),
                   ("overnight", "start"): (start or "").strip(),
                   ("overnight", "stop_by"): (stop or "").strip() or None,
                   ("overnight", "gpu_busy_percent"): int(level),
                   ("overnight", "shorts"): int(shorts or 0)}
        try:
            new = save_local_settings(settings.source_path, changes)
        except AIEditorError as exc:
            return gr.skip(), gr.skip(), f"Not saved: {exc.user_message()}"
        from .manage_tabs import apply

        apply(settings, new)
        n = settings.overnight
        when = f"{n.start}" + (f" until {n.stop_by}" if n.stop_by else ", until it's done")
        said = (f"Saved. Overnight work starts at {when}, while AI-Editor is open."
                if n.enabled else "Saved. Overnight work is off.")
        return n.start, n.stop_by or "", said

    save_btn.click(save, [night_on, night_start, night_stop, night_level, night_shorts],
                   [night_start, night_stop, night_msg])

    def start_now():
        task = overnight.run_now(settings, worker)
        if task is None:
            return "Overnight work is already in the Jobs list."
        return submitted(worker, task) + (" It still waits while OBS records or streams, or the "
                                          "graphics card is busy.")

    now_btn.click(start_now, None, night_msg)
