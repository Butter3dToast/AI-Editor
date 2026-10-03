"""The app window (spec section 9): a page in the browser, on this PC only.

Started from the desktop shortcut (``ai-editor app``). It serves on
127.0.0.1, which only this PC can reach: nothing is shared online, and
nothing on the network can see it. The console window it runs in says so;
closing that window quits AI-Editor.

Phase 1H-1: Library and Import, with every long job's progress shown live.
"""

from __future__ import annotations

import html
import logging
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

# Before Gradio loads: it would otherwise report usage to its makers.
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

# Loaded here, not inside build(): Gradio reads the click handlers' type hints
# (gr.SelectData) to know what to hand them, and can only resolve names that
# live at module level. Inside build(), a clicked row arrived as None.
import gradio as gr  # noqa: E402

from .. import __product_name__, __version__  # noqa: E402
from ..config import PROJECT_ROOT, Settings  # noqa: E402
from ..db import init_db  # noqa: E402
from ..errors import AIEditorError  # noqa: E402
from ..games import canonical_game  # noqa: E402
from ..logging_setup import get_logger  # noqa: E402
from . import companion_panel, library, manage_tabs, tasks, video_tabs  # noqa: E402
from ..companion import status as companion_status  # noqa: E402
from .worker import DONE, FAILED, PAUSED, RUNNING, WAITING, Task, Worker  # noqa: E402
from .worker import submitted as submitted_message  # noqa: E402

log = get_logger(__name__)

ADDRESS = "127.0.0.1"  # this PC only, never the network
PORT = 7865
ICON = Path(__file__).with_name("ai-editor.ico")

BADGES = {
    WAITING: ("Waiting", "wait"),
    RUNNING: ("Running", "run"),
    DONE: ("Finished", "done"),
    PAUSED: ("Paused", "pause"),
    FAILED: ("Stopped: problem", "fail"),
}

CSS = """
.aie-jobs { display: flex; flex-direction: column; gap: 10px; }
.aie-idle { opacity: .7; padding: 4px 2px; }
.aie-job { border: 1px solid var(--border-color-primary); border-radius: 10px; padding: 10px 14px;
           background: var(--block-background-fill); }
.aie-head { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
.aie-title { font-weight: 600; }
.aie-meta { font-size: .85em; opacity: .75; white-space: nowrap; }
.aie-badge { font-size: .8em; padding: 1px 8px; border-radius: 999px; margin-left: 8px; }
.aie-run { background: #7c3aed; color: white; }
.aie-done { background: #15803d; color: white; }
.aie-wait, .aie-pause { background: #a16207; color: white; }
.aie-fail { background: #b91c1c; color: white; }
.aie-step { display: grid; grid-template-columns: minmax(140px, 1fr) 2fr 44px; gap: 10px;
            align-items: center; font-size: .9em; margin-top: 6px; }
.aie-bar { height: 8px; border-radius: 4px; background: var(--border-color-primary); overflow: hidden; }
.aie-bar > div { height: 100%; background: #7c3aed; }
.aie-lines { margin: 8px 0 0; padding-left: 18px; font-size: .9em; }
.aie-error { color: #dc2626; margin-top: 6px; }
.aie-companion { padding: 6px 2px; }
.aie-companion.off { opacity: .8; }
.aie-player { width: 100%; max-height: 440px; background: #000; border-radius: 8px; }
.aie-player-empty { padding: 60px 16px; text-align: center; opacity: .7; border-radius: 8px;
                    border: 1px dashed var(--border-color-primary); }
.aie-player-note { font-size: .85em; opacity: .75; margin-top: 4px; }
@media (max-width: 640px) { .aie-step { grid-template-columns: 1fr 1fr 40px; } }
"""


def _clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def activity_html(jobs: list[Task], now: float | None = None) -> str:
    """The jobs list: what's running, how far along, and what happened."""
    if not jobs:
        return ("<div class='aie-idle'>Nothing running. Jobs you start (importing, analysing) "
                "show their progress here, and keep going while you use the other tabs.</div>")
    now = time.monotonic() if now is None else now
    cards = []
    for job in jobs:
        badge, style = BADGES[job.status]
        took = ""
        if job.started is not None:
            took = _clock((job.finished or now) - job.started)
            took = f"{'for' if job.status == RUNNING else 'took'} {took}"
        steps = "".join(
            f"<div class='aie-step'><span>{html.escape(label)}</span>"
            f"<div class='aie-bar'><div style='width:{fraction * 100:.1f}%'></div></div>"
            f"<span>{fraction * 100:.0f}%</span></div>"
            for label, fraction in job.steps.items())
        lines = "".join(f"<li>{html.escape(line)}</li>" for line in job.lines[-8:])
        error = f"<div class='aie-error'>{html.escape(job.error)}</div>" if job.error else ""
        cards.append(
            f"<div class='aie-job'><div class='aie-head'><div><span class='aie-title'>"
            f"{html.escape(job.title)}</span><span class='aie-badge aie-{style}'>{badge}</span>"
            f"</div><span class='aie-meta'>{took}</span></div>{steps}"
            + (f"<ul class='aie-lines'>{lines}</ul>" if lines else "") + error + "</div>")
    return "<div class='aie-jobs'>" + "".join(cards) + "</div>"


def row_id(evt: gr.SelectData):
    """The library number of the table row that was clicked."""
    row = evt.row_value
    return int(row[0]) if row else gr.skip()


def build(settings: Settings, worker: Worker):
    def connect():
        return init_db(settings.db_path)

    def read(fn, *args):
        conn = connect()
        try:
            return fn(conn, *args)
        finally:
            conn.close()

    def new_file_choices():
        return [(f.label(), str(f.path)) for f in read(library.new_recordings, settings)]

    with gr.Blocks(title=__product_name__, analytics_enabled=False) as ui:
        gr.Markdown(f"# {__product_name__}\n<sub>Version {__version__}. Runs on this PC only. "
                    "To quit, close the black AI-Editor window.</sub>")

        with gr.Accordion("Jobs", open=True):
            activity = gr.HTML(activity_html(worker.snapshot()))
            with gr.Row():
                pause_btn = gr.Button("Pause", size="sm")
                resume_btn = gr.Button("Resume", size="sm")
                clear_btn = gr.Button("Clear finished", size="sm")
            jobs_msg = gr.Markdown()

        with gr.Accordion("Stream Companion", open=True):
            with gr.Row():
                companion_line = gr.HTML(companion_panel.status_html(
                    companion_status.read(companion_status.folder(settings))))
                companion_start = gr.Button("Start", size="sm", scale=0, min_width=90)
                companion_stop = gr.Button("Stop", size="sm", scale=0, min_width=90)
            companion_msg = gr.Markdown()

        timer = gr.Timer(1.0)
        with gr.Tabs():
            # --- Library ------------------------------------------------------
            with gr.Tab("Library", id="library"):
                table = gr.Dataframe(value=read(library.library_table, settings),
                                     headers=library.COLUMNS, interactive=False, wrap=True,
                                     show_search="search", max_height=420,
                                     column_widths=["5%", "20%", "15%", "10%", "14%", "9%",
                                                    "10%", "6%", "11%"])
                with gr.Row():
                    pick = gr.Dropdown(choices=read(library.recording_choices), value=None,
                                       label="Recording", info="Or click its row above",
                                       scale=4)
                    refresh_btn = gr.Button("Refresh", size="sm", scale=0, min_width=100)
                details = gr.Markdown()
                with gr.Row():
                    analyse_btn = gr.Button("Analyse (or resume)", variant="primary")
                    preview_btn = gr.Button("Watch the preview copy")
                    folder_btn = gr.Button("Show the file in Explorer")
                library_msg = gr.Markdown()

            # --- Import -------------------------------------------------------
            with gr.Tab("Import", id="import"):
                gr.Markdown("### A recording on this PC\nThe file is read where it is: never "
                            "copied, moved or changed.")
                with gr.Row():
                    new_files = gr.Dropdown(choices=new_file_choices(), value=None,
                                            label="New in your raw folder",
                                            info=f"Not imported yet, newest first ({settings.folders.raw})",
                                            scale=4)
                    rescan_btn = gr.Button("Look again", size="sm", scale=0, min_width=110)
                with gr.Row():
                    path_box = gr.Textbox(label="Recording file", scale=4,
                                          placeholder=r"Pick one above, Browse, or paste e.g. "
                                                      r"F:\AI-Editor\raw\2026-10-02 19-55-01.mkv")
                    browse_btn = gr.Button("Browse...", size="sm", scale=0, min_width=110)
                game_box = gr.Dropdown(choices=read(library.game_choices), value=None,
                                       allow_custom_value=True, label="Game",
                                       info="Leave empty to work it out from the file name or "
                                            "the Stream Companion. Type a new game's name if "
                                            "it isn't listed.")
                with gr.Accordion("More options", open=False):
                    tracks_box = gr.Textbox(
                        label="Sound tracks, in order",
                        placeholder="mixed,mic,game,voice_chat",
                        info="Leave empty: worked out from the OBS setup in manual chapter 7.")
                    vod_box = gr.Textbox(
                        label="Twitch link, if this is a VOD you downloaded yourself",
                        info="Reads the game and stream date from Twitch.")
                file_analyse = gr.Checkbox(True, label="Analyse straight after importing")
                import_btn = gr.Button("Import", variant="primary")
                import_msg = gr.Markdown()

                gr.Markdown("---\n### A Twitch VOD\nDownloads the video into your raw folder, "
                            "imports it, and attaches the chat. The VOD must be public; for a "
                            "private one, download it from your Twitch dashboard and import the "
                            "file above (with its link under More options).")
                with gr.Row():
                    link_box = gr.Textbox(label="Twitch link",
                                          placeholder="https://www.twitch.tv/videos/1234567890",
                                          scale=4)
                    check_btn = gr.Button("Check", size="sm", scale=0, min_width=110)
                vod_info = gr.Markdown()
                twitch_game = gr.Dropdown(choices=read(library.game_choices), value=None,
                                          allow_custom_value=True, label="Game",
                                          info="Only if Twitch has it wrong.")
                with gr.Row():
                    twitch_chat = gr.Checkbox(True, label="Download the chat too")
                    twitch_analyse = gr.Checkbox(True, label="Analyse straight after importing")
                download_btn = gr.Button("Download and import", variant="primary")
                twitch_msg = gr.Markdown()

            video_tabs.build(settings, worker, timer, ui)
            manage_tabs.build(settings, worker)

        seen = gr.State(-1)

        timer.tick(lambda: companion_panel.status_html(
            companion_status.read(companion_status.folder(settings))), None, companion_line,
            show_progress="hidden")
        companion_start.click(lambda: companion_panel.start(settings), None, companion_msg)
        companion_stop.click(lambda: companion_panel.stop(settings), None, companion_msg)

        # --- Jobs -------------------------------------------------------------

        def submitted(task: Task | None) -> str:
            return submitted_message(worker, task)

        def tick(seen_version, current_pick, current_new):
            jobs_view = activity_html(worker.snapshot())
            version = worker.version
            if version == seen_version:
                return jobs_view, gr.skip(), gr.skip(), gr.skip(), gr.skip(), seen_version
            choices = read(library.recording_choices)
            files = new_file_choices()
            return (
                jobs_view,
                read(library.library_table, settings),
                gr.update(choices=choices,
                          value=current_pick if current_pick in [c[1] for c in choices] else None),
                read(library.recording_details, settings, current_pick) if current_pick else "",
                gr.update(choices=files,
                          value=current_new if current_new in [f[1] for f in files] else None),
                version,
            )

        timer.tick(tick, [seen, pick, new_files], [activity, table, pick, details, new_files, seen],
                   show_progress="hidden")

        def pause():
            n = worker.pause()
            return ("Pausing: the running job stops at its next progress update. Press Resume "
                    "to carry on; finished steps won't be repeated." if n else "Nothing to pause.")

        def resume():
            n = worker.resume()
            return f"Resuming {n} job(s)." if n else "Nothing paused."

        pause_btn.click(pause, None, jobs_msg)
        resume_btn.click(resume, None, jobs_msg)
        clear_btn.click(lambda: (worker.clear_finished(), "")[1], None, jobs_msg)

        # --- Library ------------------------------------------------------------

        def show(recording_id):
            if recording_id is None:
                return ""
            return read(library.recording_details, settings, int(recording_id))

        pick.change(show, pick, details)

        table.select(row_id, None, pick)

        def refresh():
            worker.version += 1  # the next tick redraws everything
            return ""

        refresh_btn.click(refresh, None, library_msg)

        def recording(recording_id):
            if recording_id is None:
                return None
            conn = connect()
            try:
                row = conn.execute(
                    "SELECT r.*, (SELECT COUNT(*) FROM audio_tracks a WHERE a.recording_id = r.id) "
                    "AS tracks, (SELECT COUNT(*) FROM audio_tracks a WHERE a.recording_id = r.id "
                    "AND a.extracted_path IS NOT NULL) AS tracks_ready "
                    "FROM recordings r WHERE r.id = ?", (int(recording_id),)).fetchone()
            finally:
                conn.close()
            return row

        def analyse(recording_id):
            row = recording(recording_id)
            if row is None:
                return "Pick a recording first."
            name = row["title"] or Path(row["source_file"]).stem
            status = library.status_of(row)
            if status == "File missing":
                return (f"The recording isn't at {row['source_file']} any more. If you moved it, "
                        "import it from its new place: it's recognised and relinked.")
            if status == "Import unfinished":
                return submitted(worker.submit(
                    f"Importing and analysing #{row['id']} {name}",
                    f"import:{str(row['source_file']).lower()}",
                    tasks.import_file(settings, Path(row["source_file"]), analyse=True)))
            return submitted(worker.submit(f"Analysing #{row['id']} {name}",
                                           f"analyse:{row['id']}",
                                           tasks.analyse(settings, row["id"])))

        analyse_btn.click(analyse, pick, library_msg)

        def watch(recording_id):
            row = recording(recording_id)
            if row is None:
                return "Pick a recording first."
            proxy = Path(row["proxy_path"] or "")
            if not row["proxy_path"] or not proxy.is_file():
                return "This recording has no preview copy yet. Import it to make one."
            os.startfile(proxy)  # noqa: S606 -- the PC's video player, on our own file
            return ("Opened in your video player. Once analysed, its subtitles load by "
                    "themselves in VLC.")

        preview_btn.click(watch, pick, library_msg)

        def explore(recording_id):
            row = recording(recording_id)
            if row is None:
                return "Pick a recording first."
            source = Path(row["source_file"])
            if not source.exists():
                return f"The file isn't at {source} any more."
            subprocess.Popen(["explorer", "/select,", str(source)])  # noqa: S603,S607
            return ""

        folder_btn.click(explore, pick, library_msg)

        # --- Import -------------------------------------------------------------

        new_files.change(lambda chosen: chosen or gr.skip(), new_files, path_box)
        rescan_btn.click(lambda: gr.update(choices=new_file_choices(), value=None), None, new_files)

        def browse(current):
            start = Path(current).parent if current and Path(current).parent.is_dir() \
                else settings.folders.raw
            chosen = library.browse_for_video(start)
            return chosen or gr.skip()

        browse_btn.click(browse, path_box, path_box)

        def import_recording(path_text, game, track_text, vod_link, then_analyse):
            path, problem = library.check_importable(path_text)
            if problem:
                return problem
            vod_link = (vod_link or "").strip() or None
            if vod_link:
                from .. import twitch

                try:
                    twitch.parse_vod_id(vod_link)
                except AIEditorError as exc:
                    return exc.user_message()
            what = "Importing and analysing" if then_analyse else "Importing"
            return submitted(worker.submit(
                f"{what} {path.name}", f"import:{str(path).lower()}",
                tasks.import_file(settings, path, game=canonical_game(game) if game else None,
                                  tracks=(track_text or "").strip() or None, vod_link=vod_link,
                                  analyse=then_analyse)))

        import_btn.click(import_recording, [path_box, game_box, tracks_box, vod_box, file_analyse],
                         import_msg)

        def check_vod(link):
            from .. import twitch
            from ..cli import _duration

            try:
                vod_id = twitch.parse_vod_id(link or "")
                info = twitch.vod_info(settings, vod_id)
            except AIEditorError as exc:
                return exc.user_message()
            lines = [f"**{info.title or 'Twitch VOD'}**",
                     f"{info.channel or '?'} · {info.game or 'game unknown'} · "
                     f"{_duration(info.length_sec)} · streamed {library.when(info.created_at.isoformat()) if info.created_at else '?'}"]
            warning = twitch.expiry_warning(info, settings.twitch.vod_keep_days)
            if warning:
                lines.append(f"**{warning}**")
            return "\n\n".join(lines)

        check_btn.click(check_vod, link_box, vod_info)

        def download(link, game, chat, then_analyse):
            from .. import twitch

            try:
                vod_id = twitch.parse_vod_id(link or "")
            except AIEditorError as exc:
                return exc.user_message()
            return submitted(worker.submit(
                f"Twitch VOD {vod_id}", f"twitch:{vod_id}",
                tasks.import_twitch(settings, link, game=canonical_game(game) if game else None,
                                    chat=chat, analyse=then_analyse)))

        download_btn.click(download, [link_box, twitch_game, twitch_chat, twitch_analyse],
                           twitch_msg)

    return ui


# --- starting it --------------------------------------------------------------


def url_for(port: int) -> str:
    return f"http://{ADDRESS}:{port}/"


def already_running(port: int) -> bool | None:
    """True if AI-Editor already answers on this port, False if nothing does.

    None if something else is using it.
    """
    try:
        with urllib.request.urlopen(url_for(port) + "config", timeout=3) as reply:  # noqa: S310
            return __product_name__ in reply.read(200_000).decode("utf-8", "replace")
    except OSError:
        return False


def recover(settings: Settings) -> None:
    """Jobs left 'running' when AI-Editor last closed were cut short: paused."""
    from ..jobs import JobQueue

    conn = init_db(settings.db_path)
    try:
        JobQueue(conn).recover_interrupted()
        conn.execute("UPDATE recordings SET analysis_status = 'paused' "
                     "WHERE analysis_status = 'running'")
        conn.commit()
    finally:
        conn.close()


def _ignore_dropped_connections(record: logging.LogRecord) -> bool:
    """A browser tab closing mid-request makes Windows' asyncio print a
    ConnectionResetError traceback in the black window. It's harmless, and
    alarming to see, so it's left out."""
    error = record.exc_info[1] if record.exc_info else None
    return not isinstance(error, ConnectionResetError)


def serve(settings: Settings, *, port: int = PORT, open_browser: bool = True) -> None:
    url = url_for(port)
    running = already_running(port)
    if running:
        print(f"{__product_name__} is already open at {url}")
        if open_browser:
            webbrowser.open(url)
        return
    if running is None:
        raise SystemExit(f"Another program is using port {port}. Start AI-Editor on another one: "
                         f"ai-editor app --port {port + 1}")

    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(f"{__product_name__} (close to quit)")
    recover(settings)
    logging.getLogger("asyncio").addFilter(_ignore_dropped_connections)
    worker = Worker()
    ui = build(settings, worker)
    print(f"\n  {__product_name__} {__version__} is running at {url}\n"
          "  Only this PC can open it.\n\n"
          "  Leave this window open while you use AI-Editor.\n"
          "  Close it to quit. Any job still running pauses and can be resumed next time.\n",
          flush=True)
    ui.queue(default_concurrency_limit=4).launch(
        server_name=ADDRESS, server_port=port, inbrowser=open_browser, share=False,
        show_error=True, quiet=True, ssr_mode=False, favicon_path=str(ICON),
        footer_links=[], allowed_paths=[str(settings.folders.cache / "recordings"),
                                       str(settings.folders.output)],
        theme=gr.themes.Soft(primary_hue="violet"), css=CSS)


# --- the desktop shortcut -------------------------------------------------------

_SHORTCUT = r"""
$desktop = [Environment]::GetFolderPath('Desktop')
$path = Join-Path $desktop 'AI-Editor.lnk'
$link = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
$link.TargetPath = $env:AIE_TARGET
$link.Arguments = 'app'
$link.WorkingDirectory = $env:AIE_FOLDER
$link.IconLocation = $env:AIE_ICON
$link.Description = 'Open AI-Editor'
$link.Save()
Write-Output $path
"""


def make_shortcut() -> Path:
    """Put 'AI-Editor' on the desktop: double-click to open the app window."""
    target = Path(sys.executable).with_name("ai-editor.exe")
    if not target.is_file():
        raise FileNotFoundError(f"Couldn't find {target}. Reinstall AI-Editor (README, step 3).")
    env = dict(os.environ, AIE_TARGET=str(target), AIE_FOLDER=str(PROJECT_ROOT),
               AIE_ICON=str(ICON))
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _SHORTCUT],
        capture_output=True, text=True, env=env, check=True)
    return Path(result.stdout.strip())
