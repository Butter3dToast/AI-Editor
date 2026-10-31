"""Backups in the window (31 Oct): Settings, Backup, and the weekly backup."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import gradio as gr

from .. import backup
from ..config import Settings, load_settings, save_local_settings
from ..errors import AIEditorError
from ..logging_setup import get_logger
from . import library
from .worker import Reporter, TaskFailed, Worker, submitted

log = get_logger(__name__)

KEY = "backup"


def job(settings: Settings, note: str = ""):
    """A backup, as a job in the Jobs list."""

    def run(report: Reporter) -> None:
        report.progress("Backing up your library", 0.0)
        try:
            path = backup.make(settings, note=note)
        except (backup.BackupProblem, OSError) as exc:
            raise TaskFailed(f"Couldn't back up: {exc}") from exc
        report.progress("Backing up your library", 1.0)
        report.say(f"Saved {path.name} ({path.stat().st_size / 1e6:.1f} MB) in {path.parent}.")

    return run


def start_weekly(settings: Settings, worker: Worker, every: float = 3600.0) -> threading.Thread:
    """Once a week, while AI-Editor is open: looked at every hour."""

    def loop() -> None:
        while True:
            try:
                if backup.due(settings):
                    worker.submit("Backing up your library (weekly)", KEY, job(settings))
            except Exception:  # noqa: BLE001 -- the check must keep going
                log.exception("Couldn't check whether a backup is due")
            time.sleep(every)

    thread = threading.Thread(target=loop, name="ai-editor-backup", daemon=True)
    thread.start()
    return thread


def build_settings(settings: Settings, worker: Worker):
    """Settings, Backup. Returns what to refresh when Settings is opened."""
    b = settings.backup

    def choices():
        return [(f.label(), str(f.path)) for f in backup.listed(settings)]

    with gr.Accordion("Backup", open=True):
        gr.Markdown(
            "Saves your **library** (ratings, your taste, plans, rules, style profiles, issues) "
            "and your **Settings changes** as one zip. The AI-Editor program itself is on "
            "GitHub; your videos and recordings aren't in a backup. **Your OBS password is "
            "never in a backup.** A folder inside Google Drive for desktop puts every backup "
            "on your Drive. AI-Editor never deletes a backup.")
        with gr.Row():
            folder_box = gr.Textbox(value=str(b.folder or ""), label="Backup folder", scale=4,
                                    placeholder=r"e.g. G:\My Drive\AI-Editor backups")
            browse_btn = gr.Button("Browse...", size="sm", scale=0, min_width=110)
        with gr.Row():
            weekly_box = gr.Checkbox(value=b.weekly, label="Also back up once a week by itself",
                                     info="While AI-Editor is open, a week after the last one.")
            save_btn = gr.Button("Save backup settings", size="sm", scale=0, min_width=170)
            now_btn = gr.Button("Back up now", variant="primary", size="sm", scale=0,
                                min_width=130)
        status = gr.Markdown(backup.summary(settings))
        with gr.Row():
            pick = gr.Dropdown(choices=choices(), value=None, label="Restore a backup", scale=4,
                               info="Puts its library and Settings back. The library as it is "
                                    "now is backed up first, so this can be undone.")
            restore_btn = gr.Button("Restore...", variant="stop", size="sm", scale=0,
                                    min_width=110)
        with gr.Row(visible=False) as confirm:
            confirm_note = gr.Markdown()
            yes_btn = gr.Button("Yes, restore it", variant="stop", scale=0, min_width=150)
            no_btn = gr.Button("Keep it as it is", scale=0, min_width=140)
        msg = gr.Markdown()

    def refreshed(said=""):
        return backup.summary(settings), gr.update(choices=choices(), value=None), said

    def browse(current):
        start = Path(current) if current and Path(current).is_dir() else Path.home()
        return library.browse_for_folder(start, "Pick a folder for AI-Editor backups") or \
            gr.skip()

    browse_btn.click(browse, folder_box, folder_box)

    def save(folder, weekly):
        folder = (folder or "").strip().strip('"')
        if folder and not Path(folder).is_dir():
            return gr.skip(), gr.skip(), f"There's no folder at {folder}."
        try:
            new = save_local_settings(settings.source_path, {("backup", "folder"): folder or None,
                                                             ("backup", "weekly"): bool(weekly)})
        except AIEditorError as exc:
            return gr.skip(), gr.skip(), f"Not saved: {exc.user_message()}"
        from .manage_tabs import apply

        apply(settings, new)
        return refreshed("Saved." + (" The first weekly backup is made within the hour."
                                     if weekly and folder and backup.due(settings) else ""))

    save_btn.click(save, [folder_box, weekly_box], [status, pick, msg])

    def back_up_now():
        problem = backup.folder_problem(settings)
        if problem:
            return problem
        return submitted(worker, worker.submit("Backing up your library", KEY, job(settings)))

    now_btn.click(back_up_now, None, msg)

    def ask(chosen):
        if not chosen:
            return gr.Row(visible=False), "", "Pick a backup first."
        if worker.busy():
            return gr.Row(visible=False), "", ("Wait until the jobs in Jobs have finished (or "
                                               "pause them) before restoring.")
        name = Path(chosen).name
        return (gr.Row(visible=True),
                f"Restore **{name}**? Your library and Settings go back to how they were then: "
                "ratings, plans and changes made since are replaced (the library as it is now "
                "is backed up first). Your OBS password stays.", "")

    restore_btn.click(ask, pick, [confirm, confirm_note, msg])
    no_btn.click(lambda: (gr.Row(visible=False), "Nothing was changed."), None, [confirm, msg])

    def do_restore(chosen):
        if not chosen:
            return (gr.Row(visible=False), *refreshed("Pick a backup first."))
        if worker.busy():
            return (gr.Row(visible=False),
                    *refreshed("Wait until the jobs in Jobs have finished first."))
        try:
            before = backup.restore(settings, Path(chosen))
        except (backup.BackupProblem, OSError) as exc:
            return (gr.Row(visible=False), *refreshed(f"Not restored: {exc}"))
        from .manage_tabs import apply

        apply(settings, load_settings(settings.source_path))
        return (gr.Row(visible=False), *refreshed(
            f"Restored from {Path(chosen).name}. **Close AI-Editor (the black window) and open "
            f"it again** so every tab shows it. The library as it was is in {before.name}, if "
            "you want it back."))

    yes_btn.click(do_restore, pick, [confirm, status, pick, msg])
    # Backups made since (weekly, or Back up now) show when Settings is opened.
    return lambda: refreshed()[:2], [status, pick]
