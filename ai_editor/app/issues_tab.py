"""The Issues tab (0.32.0): problems written down, with their details (issues.py)."""

from __future__ import annotations

import gradio as gr
import pandas as pd

from .. import issues
from ..config import Settings
from ..db import init_db
from . import videos
from .worker import Task, Worker

COLUMNS = ["#", "When", "From", "What", "Video", "Status"]
SHOW = ["Open", "All"]
NO_VIDEO = ""

INTRO = ("Something wrong? Write it down here. AI-Editor adds the details needed to fix it: "
         "its version, the video's plan, the recording's sound tracks, the log lines around "
         "it, and your settings (the OBS password and any keys hidden). It also writes down "
         "its own problems by itself. Each issue is saved as a text file in "
         "**{folder}**: next time, just say \"check the issues\". Nothing is sent anywhere.")


def _read(settings: Settings, fn, *args, **kwargs):
    conn = init_db(settings.db_path)
    try:
        return fn(conn, *args, **kwargs)
    finally:
        conn.close()


def video_choices(settings: Settings) -> list[tuple[str, str]]:
    """Plans first (a video made), then recordings."""
    def found(conn):
        plans = [(f"Video: {label}", f"plan:{pid}") for label, pid in videos.plan_choices(conn)]
        recordings = [(f"Recording: {r['title'] or r['source_file']} (#{r['id']})", f"rec:{r['id']}")
                      for r in conn.execute("SELECT id, title, source_file FROM recordings "
                                            "ORDER BY id DESC")]
        return [("(none)", NO_VIDEO), *plans, *recordings]
    return _read(settings, found)


def table(settings: Settings, show: str) -> tuple[pd.DataFrame, list[int]]:
    found = _read(settings, issues.listed, open_only=show == "Open")
    rows = [[i.number, i.made_at[:16].replace("T", " "),
             "You" if i.source == issues.YOU else "AI-Editor", i.what, i.video,
             "Fixed" + (f" ({i.fixed_in})" if i.fixed_in else "") if i.status == issues.FIXED
             else "Open"] for i in found]
    return pd.DataFrame(rows, columns=COLUMNS), [i.id for i in found]


def summary(issue: issues.Issue) -> str:
    d = issue.details
    lines = [f"**{issue.number}: {issue.what}**",
             f"Recorded {issue.made_at[:16].replace('T', ' ')} by "
             f"{'you' if issue.source == issues.YOU else 'AI-Editor itself'}, "
             f"AI-Editor {d.get('ai_editor')}."]
    if issue.video:
        lines.append(f"Video: {issue.video}" + (f", at {issue.at}" if issue.at else ""))
    elif issue.at:
        lines.append(f"Where: {issue.at}")
    if d.get("error"):
        lines.append(f"AI-Editor said: _{d['error']}_")
    lines.append(f"{len(d.get('log', []))} log lines and your settings are kept with it.")
    return "\n\n".join(lines)


def build(settings: Settings, worker: Worker) -> None:
    """Add the Issues tab, and have the worker write down every job that fails."""
    def failed(task: Task, error: str) -> None:
        _read(settings, issues.from_job, settings, task.title, error, task.key)

    worker.on_failure = failed

    with gr.Tab("Issues", id="issues") as tab:
        gr.Markdown(INTRO.format(folder=issues.folder(settings)))
        with gr.Accordion("Report a problem", open=True):
            what = gr.Textbox(label="What's wrong", lines=3,
                              placeholder="e.g. EP 5 Part 1 loses the game's sound from 16:39")
            with gr.Row():
                which = gr.Dropdown(choices=video_choices(settings), value=NO_VIDEO,
                                    label="Which video (optional)", scale=3)
                where = gr.Textbox(label="Where (optional)", placeholder="e.g. 16:39", scale=1,
                                   max_lines=1)
            record_btn = gr.Button("Record it", variant="primary")
            record_msg = gr.Markdown()
        show = gr.Radio(SHOW, value=SHOW[0], label="Show")
        ids = gr.State([])
        picked = gr.State(None)
        listed = gr.Dataframe(headers=COLUMNS, interactive=False, wrap=True, max_height=360,
                              column_widths=["6%", "14%", "10%", "40%", "20%", "10%"])
        info = gr.Markdown("Click an issue to see it.")
        with gr.Row():
            status = gr.Radio([("Open", issues.OPEN), ("Fixed", issues.FIXED)],
                              value=issues.OPEN, label="Status", scale=1)
            fixed_in = gr.Textbox(label="Fixed in (version)", placeholder="e.g. 0.31.1",
                                  max_lines=1, scale=1)
            note = gr.Textbox(label="Note", scale=3, max_lines=3)
        save_btn = gr.Button("Save")
        save_msg = gr.Markdown()
        with gr.Accordion("Copy diagnostic info", open=False):
            gr.Markdown("Everything about the issue you clicked (or, with none clicked, how "
                        "things stand now), ready to copy and paste. Private values are hidden.")
            diag_btn = gr.Button("Get diagnostic info")
            diag = gr.Textbox(label="Diagnostic info", lines=14, max_lines=30, buttons=["copy"])

    def shown(show_what):
        frame, found = table(settings, show_what)
        return frame, found

    list_outputs = [listed, ids]
    for event in (tab.select, show.change):
        event(shown, show, list_outputs)
    tab.select(lambda: gr.Dropdown(choices=video_choices(settings)), None, which)

    def recorded(text, video, at, show_what):
        plan_id = video[5:] if video and video.startswith("plan:") else None
        recording = int(video[4:]) if video and video.startswith("rec:") else None
        try:
            issue = _read(settings, issues.record, settings, text, plan_id=plan_id,
                          recording_id=recording, at=at or "")
        except ValueError as exc:
            return str(exc), gr.skip(), gr.skip(), gr.skip()
        frame, found = table(settings, show_what)
        return (f"Recorded as **{issue.number}**, with its details. It's also saved in "
                f"{issues.folder(settings)}.", "", frame, found)

    record_btn.click(recorded, [what, which, where, show], [record_msg, what, listed, ids])

    def clicked(found, evt: gr.SelectData):
        row = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        if row is None or row >= len(found):
            return None, "Click an issue to see it.", gr.skip(), gr.skip(), gr.skip()
        issue = _read(settings, issues.get, found[row])
        if issue is None:
            return None, "That issue isn't there any more.", gr.skip(), gr.skip(), gr.skip()
        return issue.id, summary(issue), issue.status, issue.fixed_in, issue.note

    listed.select(clicked, ids, [picked, info, status, fixed_in, note])

    def saved(issue_id, new_status, version, text, show_what):
        if issue_id is None:
            return "Click an issue first.", gr.skip(), gr.skip()
        issue = _read(settings, issues.update, settings, issue_id, status=new_status,
                      fixed_in=version or "", note=text or "")
        frame, found = table(settings, show_what)
        return f"Saved {issue.number}.", frame, found

    save_btn.click(saved, [picked, status, fixed_in, note, show], [save_msg, listed, ids])
    diag_btn.click(lambda issue_id: _read(settings, issues.diagnostic_text, settings, issue_id),
                   picked, diag)
