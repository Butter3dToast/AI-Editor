"""Command line interface.

Phase 0 ships the setup check (`doctor`) and a couple of small helpers. The
Gradio interface arrives in Phase 1H; until then this is how the tool is driven
and tested.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from . import __product_name__, __version__
from .config import DEFAULT_SETTINGS_PATH, Settings, load_settings
from .db import SCHEMA_VERSION, current_version, init_db
from .errors import AIEditorError
from .ffmpeg import (
    configure_tool_paths,
    content_hash,
    find_binary,
    nvenc_encoders,
    probe,
)
from .companion.link import link_recording, stream_offset
from .games import canonical_game
from .ingest import Registration, ingest_recording
from .logging_setup import setup_logging

app = typer.Typer(
    name="ai-editor",
    help=f"{__product_name__} - local assistant editor for streams and Let's Plays.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

OK = "[green]OK[/green]"
WARN = "[yellow]CHECK[/yellow]"
FAIL = "[red]FAIL[/red]"


def _load(settings_path: Path | None) -> Settings:
    """Load settings, turning any failure into a readable message and exit."""
    try:
        settings = load_settings(settings_path)
    except AIEditorError as exc:
        console.print(f"[red]{exc.user_message()}[/red]")
        raise typer.Exit(code=1) from exc
    configure_tool_paths(settings.tools.ffmpeg_dir)
    return settings


@app.command()
def version() -> None:
    """Show the AI-Editor version."""
    console.print(f"{__product_name__} {__version__}")


@app.command()
def doctor(
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Check that everything AI-Editor needs is present and working.

    This is the command behind the setup wizard's Test buttons (manual chapter
    6). It never changes anything.
    """
    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)

    table = Table(title=f"{__product_name__} setup check", header_style="bold")
    table.add_column("Check")
    table.add_column("Status", justify="center")
    table.add_column("Detail", overflow="fold")

    problems = 0

    # --- Settings ---
    table.add_row("Settings file", OK, str(settings.source_path))

    # --- FFmpeg ---
    # A missing FFmpeg makes the NVENC check impossible, not failed. Reporting
    # both as failures sent the creator hunting for a graphics driver problem
    # that did not exist, so the cause is reported once and the checks that
    # depend on it say plainly that they could not run.
    ffmpeg_found = True
    for binary in ("ffmpeg", "ffprobe"):
        try:
            path = find_binary(binary)
            table.add_row(binary.capitalize(), OK, str(path))
        except AIEditorError as exc:
            problems += 1
            ffmpeg_found = False
            table.add_row(binary.capitalize(), FAIL, exc.user_message())

    # --- GPU encoding ---
    if not ffmpeg_found:
        table.add_row(
            "GPU encoding (NVENC)",
            WARN,
            "Could not be checked, because FFmpeg was not found (see above).",
        )
    else:
        try:
            encoders = nvenc_encoders()
            if settings.render.encoder in encoders:
                table.add_row("GPU encoding (NVENC)", OK, ", ".join(sorted(encoders)))
            elif encoders:
                problems += 1
                table.add_row(
                    "GPU encoding (NVENC)",
                    WARN,
                    f"'{settings.render.encoder}' not found. Available: "
                    f"{', '.join(sorted(encoders))}",
                )
            else:
                problems += 1
                table.add_row(
                    "GPU encoding (NVENC)",
                    FAIL,
                    "No NVENC encoders. Update your NVIDIA drivers and restart.",
                )
        except AIEditorError as exc:
            problems += 1
            table.add_row("GPU encoding (NVENC)", FAIL, exc.user_message())

    # --- Graphics card ---
    gpu = _gpu_summary()
    table.add_row("Graphics card", OK if gpu else WARN, gpu or "nvidia-smi not found")

    # --- Folders ---
    for name, folder in settings.folders.all().items():
        status, detail = _check_folder(folder)
        if status is FAIL:
            problems += 1
        table.add_row(f"Folder: {name}", status, detail)

    # --- Database ---
    try:
        conn = init_db(settings.db_path)
        found = current_version(conn)
        conn.close()
        detail = f"{settings.db_path} (schema v{found})"
        if found != SCHEMA_VERSION:
            problems += 1
            table.add_row("Clip library", WARN, f"{detail}, expected v{SCHEMA_VERSION}")
        else:
            table.add_row("Clip library", OK, detail)
    except Exception as exc:  # noqa: BLE001
        problems += 1
        table.add_row("Clip library", FAIL, str(exc))

    # --- OBS ---
    # OBS being closed is normal, so only a refused password counts as a problem.
    from .companion.obs import ObsClient
    from .errors import ObsNotReachable

    client = ObsClient(settings.obs.websocket_host, settings.obs.websocket_port,
                       settings.obs.websocket_password, timeout=2.0)
    try:
        table.add_row("OBS (Stream Companion)", OK, f"Connected to OBS {client.connect()}")
    except ObsNotReachable:
        table.add_row("OBS (Stream Companion)", WARN,
                      "Not reachable. Fine if OBS is closed; otherwise see manual chapter 7.4.")
    except AIEditorError as exc:
        problems += 1
        table.add_row("OBS (Stream Companion)", FAIL, exc.user_message())
    finally:
        client.close()

    console.print(table)

    if problems:
        console.print(
            f"\n[yellow]{problems} thing(s) need attention.[/yellow] "
            "See the detail column above."
        )
        raise typer.Exit(code=1)
    console.print("\n[green]Everything checks out.[/green]")


def _gpu_summary() -> str | None:
    """Ask nvidia-smi for the card name, memory and driver. None if absent."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        result = subprocess.run(
            [
                smi,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=20.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else None


def _check_folder(folder: Path) -> tuple[str, str]:
    """Confirm a folder exists, is writable, and report free space."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe_file = folder / ".ai-editor-write-test"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
    except OSError as exc:
        return FAIL, f"{folder} - not writable ({exc.strerror or exc})"

    usage = shutil.disk_usage(folder)
    free_gb = usage.free / 1024**3
    return OK, f"{folder} ({free_gb:,.0f} GB free)"


@app.command("init-db")
def init_database(
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Create the clip library database, or bring its schema up to date."""
    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    conn = init_db(settings.db_path)
    version_found = current_version(conn)
    tables = [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    conn.close()
    console.print(f"Clip library ready at [bold]{settings.db_path}[/bold] (schema v{version_found})")
    console.print(f"{len(tables)} tables: {', '.join(tables)}")


@app.command("probe")
def probe_file(
    path: Path = typer.Argument(..., help="A video file to inspect"),
    show_hash: bool = typer.Option(False, "--hash", help="Also compute the content hash"),
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Inspect a recording: resolution, frame rate, and audio tracks.

    Useful for confirming an OBS recording really has the four separate audio
    tracks described in manual chapter 7.
    """
    _load(settings_path)  # Also tells the finder where FFmpeg lives.
    try:
        info = probe(path)
    except AIEditorError as exc:
        console.print(f"[red]{exc.user_message()}[/red]")
        raise typer.Exit(code=1) from exc

    table = Table(title=info.path.name, header_style="bold")
    table.add_column("Property")
    table.add_column("Value")

    duration = info.duration_sec or 0
    table.add_row("Container", info.container or "unknown")
    table.add_row(
        "Duration", f"{int(duration // 3600)}h {int(duration % 3600 // 60)}m {int(duration % 60)}s"
    )
    table.add_row("Video", f"{info.width}x{info.height} @ {info.fps:.0f} fps" if info.fps else "none")
    table.add_row("Codec", info.video_codec or "unknown")
    table.add_row("Size", f"{(info.size_bytes or 0) / 1024**3:,.2f} GiB")
    table.add_row("Audio tracks", str(len(info.audio)))
    console.print(table)

    if info.audio:
        roles = info.track_roles_guess()
        audio_table = Table(title="Audio tracks", header_style="bold")
        for column in ("Stream", "Likely role", "Codec", "Channels", "Sample rate", "Title"):
            audio_table.add_column(column)
        for stream in info.audio:
            audio_table.add_row(
                str(stream.index),
                roles.get(stream.index, "unknown"),
                stream.codec or "-",
                str(stream.channels or "-"),
                f"{stream.sample_rate:,} Hz" if stream.sample_rate else "-",
                stream.title or "-",
            )
        console.print(audio_table)

    if not info.is_multitrack:
        _single_track_warning()

    if show_hash:
        console.print(f"\nContent hash: [bold]{content_hash(path)}[/bold]")


def _single_track_warning() -> None:
    console.print(
        "\n[yellow]This recording has a single mixed audio track.[/yellow]\n"
        "Your voice must be separated from game sound by AI, which is slower "
        "and less accurate than separate tracks.\n"
        "See manual chapter 7.1-7.3 to record four separate tracks in OBS."
    )


def _duration(seconds: float | None) -> str:
    s = int(seconds or 0)
    return f"{s // 3600}h {s % 3600 // 60:02d}m {s % 60:02d}s"


def _elapsed(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60}m {s % 60:02d}s" if s >= 60 else f"{seconds:.1f}s"


def _size(path: Path) -> str:
    if path.is_dir():
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    elif path.exists():
        total = path.stat().st_size
    else:
        return "-"
    return f"{total / 1024**3:,.2f} GB" if total >= 1024**3 else f"{total / 1024**2:,.0f} MB"


STEP_LABELS = {
    "proxy": "Making preview copy (proxy)",
    "audio": "Extracting audio tracks",
}


@app.command("import")
def import_recording(
    path: Path = typer.Argument(..., help="The recording to import"),
    game: str = typer.Option(
        None, "--game", "-g",
        help="The game, e.g. \"The Blood of Dawnwalker\". Guessed from the filename if left out.",
    ),
    tracks: str = typer.Option(
        None, "--tracks", "-t",
        help="Audio track labels in order, e.g. mixed,mic,game,voice_chat. "
        "Guessed from the OBS setup in manual chapter 7 if left out.",
    ),
    source: str = typer.Option(
        "local", "--source",
        help="local (an OBS recording) or twitch (a VOD you downloaded yourself).",
    ),
    vod: str = typer.Option(
        None, "--vod",
        help="For a downloaded VOD: its Twitch link, so the game and stream date are "
        "read from Twitch. Implies --source twitch.",
    ),
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Import a recording: preview copy, audio, and library entry.

    The file is read where it is, never copied or changed. Safe to run again:
    finished work is reused, and an interrupted import continues where it
    stopped.
    """
    from . import twitch

    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    if source not in ("local", "twitch"):
        console.print("[red]--source must be local or twitch.[/red]")
        raise typer.Exit(code=1)

    vod_id = recorded_at = None
    if vod:
        source = "twitch"
        try:
            vod_id = twitch.parse_vod_id(vod)
            info = twitch.vod_info(settings, vod_id)
            game = game or (info.game and canonical_game(info.game))
            recorded_at = info.created_at.isoformat() if info.created_at else None
        except AIEditorError as exc:
            # The file is already here, so a VOD Twitch won't describe (private,
            # expired) only costs the extras. Carry on without them.
            console.print(f"[yellow]Couldn't read the VOD's details from Twitch; "
                          f"importing without them.[/yellow] {exc.user_message()}\n")

    conn = init_db(settings.db_path)
    try:
        _import_file(settings, conn, path, game=game, tracks=tracks,
                     source_type="twitch_vod" if source == "twitch" else "local_obs",
                     vod_id=vod_id, recorded_at=recorded_at)
    finally:
        conn.close()


def _import_file(settings, conn, path: Path, *, game, tracks, source_type, vod_id=None,
                 recorded_at=None) -> int:
    """Shared by import and import-twitch: progress bars, summary. Returns the recording id."""
    progress = _progress_bar()
    tasks: dict[str, TaskID] = {}

    def on_registered(reg: Registration, space_warning: str | None) -> None:
        info = reg.info
        table = Table(title=f"Importing: {info.path.name}", header_style="bold", show_header=False)
        table.add_column("Property")
        table.add_column("Value")
        table.add_row("Library entry", f"#{reg.recording_id} ({'new' if reg.is_new else 'already in library'})")
        table.add_row("Source", "Twitch VOD" if source_type == "twitch_vod" else "Local recording")
        table.add_row("Game", reg.game or "[yellow]not set - add --game[/yellow]")
        table.add_row("Length", _duration(info.duration_sec))
        table.add_row("Video", f"{info.width}x{info.height} @ {info.fps:.0f} fps" if info.fps else "-")
        table.add_row(
            "Audio tracks",
            ", ".join(f"{i}: {role}" for i, role in reg.track_roles.items()),
        )
        if reg.relinked_from:
            table.add_row("Moved from", reg.relinked_from)
        console.print(table)
        if not info.is_multitrack and source_type != "twitch_vod":
            _single_track_warning()
        if space_warning:
            console.print(f"\n[yellow]Low space:[/yellow] {space_warning}")
        console.print()
        progress.start()

    def on_progress(step: str, fraction: float) -> None:
        if step not in tasks:
            tasks[step] = progress.add_task(STEP_LABELS.get(step, step), total=1.0)
        progress.update(tasks[step], completed=fraction)

    started = time.monotonic()
    try:
        result = ingest_recording(
            conn, settings, path, game=game, track_roles=tracks,
            on_progress=on_progress, on_registered=on_registered,
            source_type=source_type, twitch_vod_id=vod_id, recorded_at=recorded_at,
        )
    except AIEditorError as exc:
        progress.stop()
        console.print(f"\n[red]{exc.user_message()}[/red]")
        raise typer.Exit(code=1) from exc
    except KeyboardInterrupt:
        progress.stop()
        console.print(
            "\n[yellow]Import paused.[/yellow] Run the same command again to "
            "continue; finished steps won't be repeated."
        )
        raise typer.Exit(code=130)
    finally:
        progress.stop()

    if result.status != "complete":
        console.print(f"\n[red]{result.error_message}[/red]")
        console.print("To try again, run the same import command. Finished steps won't be repeated.")
        raise typer.Exit(code=1)

    summary = Table(title="Import complete", header_style="bold")
    summary.add_column("Step")
    summary.add_column("Result")
    summary.add_column("Time", justify="right")
    summary.add_column("Size", justify="right")
    for step in result.steps:
        label = STEP_LABELS.get(step.name, step.name)
        outcome = "[cyan]reused (already done)[/cyan]" if step.reused else f"[green]done[/green] {step.detail}"
        summary.add_row(label, outcome, "-" if step.reused else _elapsed(step.seconds), _size(Path(step.output)))
    console.print(summary)
    console.print(f"Total time: {_elapsed(time.monotonic() - started)}")
    console.print(f"Preview copy: [bold]{result.proxy_path}[/bold]")
    console.print(f"Working files folder: {result.cache_dir}")

    recording_id = result.registration.recording_id
    match = link_recording(conn, recording_id)
    if match:
        detail = f"session {match.session_id}"
        if match.marker_total:
            detail += (f", [bold]{match.markers} moment(s) you marked[/bold]"
                       + (f" and {match.short_markers} Short-worthy" if match.short_markers else ""))
        else:
            detail += ", no markers"
        if match.stream_offset_sec is not None:
            detail += f"; this recording starts {match.stream_offset_sec:.0f}s into the stream"
        console.print(f"Stream Companion: {detail}")

    console.print(f"Next: [bold]ai-editor analyze {recording_id}[/bold]")
    return recording_id


def _safe_filename(text: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in " -_()[]" else " " for c in text)
    return " ".join(cleaned.split())[:80] or "Twitch VOD"


@app.command("import-twitch")
def import_twitch(
    link: str = typer.Argument(..., help="The VOD's Twitch link (or dashboard link, or number)"),
    game: str = typer.Option(None, "--game", "-g", help="Only if Twitch has the game wrong"),
    chat: bool = typer.Option(True, "--chat/--no-chat", help="Also download and attach the chat"),
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Download a Twitch VOD into your raw folder, import it, and attach its chat.

    The VOD must be public. For a private one, download it from your Twitch
    dashboard and use: ai-editor import "<file>" --vod <link>
    """
    from . import twitch
    from .analysis.chat import attach_chat

    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    try:
        vod_id = twitch.parse_vod_id(link)
        info = twitch.vod_info(settings, vod_id)
    except AIEditorError as exc:
        console.print(f"[red]{exc.user_message()}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]{info.title or 'Twitch VOD'}[/bold]  "
                  f"({info.channel or '?'}, {info.game or 'game unknown'}, "
                  f"{_duration(info.length_sec)})")
    warning = twitch.expiry_warning(info, settings.twitch.vod_keep_days)
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")

    date = info.created_at.strftime("%Y-%m-%d") if info.created_at else "unknown date"
    target = settings.folders.raw / f"Twitch {date} {_safe_filename(info.title or vod_id)} ({vod_id}).mp4"
    if target.exists():
        console.print(f"Already downloaded: {target}")
    else:
        progress = _progress_bar()
        task = progress.add_task("Downloading the VOD", total=1.0)
        progress.start()
        try:
            twitch.download_video(settings, vod_id, target,
                                  lambda f: progress.update(task, completed=f))
        except AIEditorError as exc:
            progress.stop()
            console.print(f"\n[red]{exc.user_message()}[/red]")
            raise typer.Exit(code=1) from exc
        except KeyboardInterrupt:
            progress.stop()
            console.print("\n[yellow]Download stopped.[/yellow] Run the same command to start it again.")
            raise typer.Exit(code=130)
        progress.stop()

    conn = init_db(settings.db_path)
    try:
        recording_id = _import_file(
            settings, conn, target,
            game=game or (info.game and canonical_game(info.game)), tracks=None,
            source_type="twitch_vod", vod_id=vod_id,
            recorded_at=info.created_at.isoformat() if info.created_at else None,
        )
        if chat:
            result = attach_chat(conn, settings, recording_id, vod_id)
            _print_chat(result)
    except AIEditorError as exc:
        console.print(f"\n[red]{exc.user_message()}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        conn.close()


@app.command("attach-chat")
def attach_chat_command(
    recording: str = typer.Argument(..., help="The recording's number from the library, or its file"),
    link: str = typer.Argument(..., help="The Twitch VOD whose chat to attach"),
    starts_at: float = typer.Option(
        None, "--starts-at",
        help="Seconds into the stream when this recording began. Worked out from the "
        "Stream Companion's session log when it was running; otherwise 0.",
    ),
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Add a Twitch VOD's chat to a recording (manual chapter 10.3).

    Works for the VOD itself, and for a local recording made while streaming,
    which keeps the better video and separate audio tracks but gains the chat.
    """
    from .analysis import resolve_recording
    from .analysis.chat import attach_chat

    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    conn = init_db(settings.db_path)
    try:
        row = resolve_recording(conn, recording)
        offset = starts_at
        if offset is None:
            offset = stream_offset(conn, row["id"])
            if offset is not None:
                console.print(
                    f"The Stream Companion logged this recording starting [bold]{offset:.0f}s"
                    "[/bold] into the stream; lining chat up with that."
                )
            else:
                offset = 0.0
        result = attach_chat(conn, settings, row["id"], link, recording_starts_at=offset)
        # Chat activity changes which moments are best, so score and cut again.
        if row["analysis_status"] == "complete":
            _refresh_clips(conn, settings, row)
    except AIEditorError as exc:
        console.print(f"[red]{exc.user_message()}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        conn.close()
    _print_chat(result)


def _print_chat(result) -> None:
    from .analysis.captions import clock

    table = Table(title=f"Chat from VOD {result.vod_id}", header_style="bold", show_header=False)
    table.add_column("Measure")
    table.add_column("Value")
    table.add_row("Messages", f"{result.messages_in_recording:,} from {result.chatters} viewer(s)")
    if result.bot_messages:
        table.add_row("Ignored", f"{result.bot_messages} from chat bots (see twitch.ignore_chatters)")
    table.add_row(
        "Busiest moments",
        "  ".join(f"{clock(t)} ({v:.0f} msgs)" for t, v in result.busiest) or "[dim]none yet[/dim]",
    )
    console.print(table)
    if result.expiry_warning:
        console.print(f"[yellow]{result.expiry_warning}[/yellow]")


ANALYSIS_LABELS = {
    "separate_voices": "Separating voices from game sound",
    "prepare_audio": "Preparing audio",
    "transcribe": "Transcribing speech",
    "sound_events": "Listening for laughter, shouts, gunfire",
    "loudness": "Measuring loudness",
    "scenes": "Finding scene changes (menus, loading)",
}


def _progress_bar() -> Progress:
    return Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TextColumn("elapsed,"),
        TimeRemainingColumn(),
        TextColumn("left"),
        console=console,
    )


@app.command("analyze")
def analyze(
    recording: str = typer.Argument(
        ..., help="The recording's number from the library, or its file path"
    ),
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Analyse an imported recording: transcript, loudness, and sound events.

    The first run downloads the AI models (once). Safe to stop with Ctrl+C and
    run again: finished steps are reused.
    """
    from .analysis import analyze_recording
    from .analysis.pipeline import TrackChoice

    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    conn = init_db(settings.db_path)
    progress = _progress_bar()
    tasks: dict[str, TaskID] = {}

    def on_started(row, tracks: TrackChoice) -> None:
        from .analysis.pipeline import needs_separation

        separating = needs_separation(settings, row, tracks)
        table = Table(title=f"Analysing: {row['title']}", header_style="bold", show_header=False)
        table.add_column("Property")
        table.add_column("Value")
        table.add_row("Library entry", f"#{row['id']}")
        table.add_row("Game", row["game"] or "-")
        table.add_row("Length", _duration(row["duration_sec"]))
        if separating:
            table.add_row("Voice from", f"track {tracks.voice_index} ({tracks.voice_role}), separated by AI")
            table.add_row("Game sound from", f"track {tracks.voice_index} ({tracks.voice_role}), separated by AI")
        else:
            table.add_row("Voice from", f"track {tracks.voice_index} ({tracks.voice_role})")
            table.add_row("Game sound from", f"track {tracks.game_index} ({tracks.game_role})")
        console.print(table)
        if tracks.voice_role != "mic":
            console.print(
                "\n[yellow]No separate microphone track.[/yellow] The transcript will "
                "include everyone audible, such as in-game characters and teammates, "
                "not only you."
                + (" Voice separation removes the game's music and sound effects first."
                   if separating else "")
            )
        console.print()
        progress.start()

    def on_progress(step: str, fraction: float) -> None:
        if step not in tasks:
            tasks[step] = progress.add_task(ANALYSIS_LABELS.get(step, step), total=1.0)
        progress.update(tasks[step], completed=fraction)

    started = time.monotonic()
    try:
        result = analyze_recording(
            conn, settings, recording, on_progress=on_progress, on_started=on_started
        )
    except AIEditorError as exc:
        progress.stop()
        console.print(f"\n[red]{exc.user_message()}[/red]")
        conn.close()
        raise typer.Exit(code=1) from exc
    except KeyboardInterrupt:
        progress.stop()
        console.print(
            "\n[yellow]Analysis paused.[/yellow] Run the same command again to "
            "continue; finished steps won't be repeated."
        )
        conn.close()
        raise typer.Exit(code=130)
    progress.stop()

    if result.status != "complete":
        console.print(f"\n[red]{result.error_message}[/red]")
        console.print("To try again, run the same analyze command. Finished steps won't be repeated.")
        conn.close()
        raise typer.Exit(code=1)

    summary = Table(title="Analysis complete", header_style="bold")
    summary.add_column("Step")
    summary.add_column("Result")
    summary.add_column("Time", justify="right")
    for step in result.steps:
        summary.add_row(
            ANALYSIS_LABELS.get(step.name, step.name),
            "[cyan]reused (already done)[/cyan]" if step.reused else "[green]done[/green]",
            "-" if step.reused else _elapsed(step.seconds),
        )
    console.print(summary)
    console.print(f"Total time: {_elapsed(time.monotonic() - started)}\n")

    _print_moments(conn, result.recording_id)
    # Everything needed to rank moments is now stored, so cut the clips straight away.
    row = conn.execute("SELECT * FROM recordings WHERE id = ?", (result.recording_id,)).fetchone()
    clips, _ = _refresh_clips(conn, settings, row) if row else (None, None)
    conn.close()
    if clips:
        console.print(f"\n[bold]{len(clips)} clips[/bold] found. See them with: "
                      f"[bold]ai-editor clips {result.recording_id} --export 10[/bold]")

    if result.proxy_srt_path:
        console.print(
            f"\n[bold]Check the transcript:[/bold] open the preview copy in VLC and "
            f"the subtitles load by themselves:\n  {result.proxy_srt_path.with_suffix('.mp4')}"
        )
    if result.srt_path:
        console.print(f"Subtitle file: {result.srt_path}")


@app.command("moments")
def moments(
    recording: str = typer.Argument(
        ..., help="The recording's number from the library, or its file path"
    ),
    top: int = typer.Option(8, "--top", "-n", help="How many moments to list per kind"),
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Show what analysis found in a recording, with times to check in the proxy."""
    from .analysis import resolve_recording

    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    conn = init_db(settings.db_path)
    try:
        row = resolve_recording(conn, recording)
    except AIEditorError as exc:
        console.print(f"[red]{exc.user_message()}[/red]")
        conn.close()
        raise typer.Exit(code=1) from exc
    if row["analysis_status"] != "complete":
        console.print(
            f"Recording #{row['id']} hasn't been analysed yet. Run: ai-editor analyze {row['id']}"
        )
        conn.close()
        raise typer.Exit(code=1)
    _print_moments(conn, row["id"], top)
    conn.close()


def _print_moments(conn, recording_id: int, top: int = 8) -> None:
    from .analysis.captions import clock
    from .analysis.moments import EVENT_LABELS, build_report

    report = build_report(conn, recording_id, top)

    overview = Table(title="What AI-Editor heard", header_style="bold", show_header=False)
    overview.add_column("Measure")
    overview.add_column("Value")
    overview.add_row("Words transcribed", f"{report.words:,}")
    overview.add_row(
        "Talking",
        f"{report.talking_pct:.0f}% of the recording"
        + ("" if report.source_role == "mic" else " (everyone audible, not only you)"),
    )
    overview.add_row("Near-silent", f"{report.silence_pct:.0f}% of the recording")
    if report.phrases_set_aside:
        overview.add_row(
            "Set aside",
            f"{report.phrases_set_aside} phrase(s) that were probably music or noise "
            "misheard as speech (details in the log file)",
        )
    console.print(overview)

    moments_table = Table(
        title="Moments to check (jump to these times in the preview copy)",
        header_style="bold",
    )
    moments_table.add_column("Kind")
    moments_table.add_column("Times  (confidence)")
    if report.markers:
        moments_table.add_row(
            "[bold]You marked these[/bold]",
            "  ".join(clock(t) + (" (Short)" if name == "marker_short" else "")
                      for t, name in report.markers),
        )
    moments_table.add_row(
        "Loudest moments" + ("" if report.source_role == "mic" else " (you and the game)"),
        "  ".join(f"{clock(t)} ({v:.1f}x)" for t, v in report.spikes) or "[dim]none found[/dim]",
    )
    for name, label in EVENT_LABELS.items():
        found = report.events.get(name)
        if found is None:
            continue
        moments_table.add_row(
            label,
            "  ".join(f"{clock(t)} ({v:.0%})" for t, v in found) or "[dim]none found[/dim]",
        )
    moments_table.add_row(
        "Longest stretches with no speech",
        "  ".join(f"{clock(s)}-{clock(e)}" for s, e in report.quiet_stretches)
        or "[dim]none over 20 s[/dim]",
    )
    console.print(moments_table)


@app.command("setup-obs")
def setup_obs(
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Connect AI-Editor to OBS and save the password (manual chapter 7.4).

    The password is typed in hidden and saved to config/settings.local.yaml,
    which stays on this PC and is never committed to git. It is only saved
    once OBS has accepted it.
    """
    from .companion.obs import ObsClient
    from .config import save_local_setting

    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    console.print(
        "In OBS: [bold]Tools → WebSocket Server Settings[/bold]. Tick [bold]Enable "
        "WebSocket server[/bold], click [bold]Show Connect Info[/bold], and copy the "
        "Server Password.\n"
    )
    password = typer.prompt("Paste the OBS password (it won't show as you type)",
                            hide_input=True, default="", show_default=False).strip()
    client = ObsClient(settings.obs.websocket_host, settings.obs.websocket_port, password)
    try:
        version = client.connect()
    except AIEditorError as exc:
        console.print(f"\n[red]{exc.user_message()}[/red]")
        console.print("Nothing was saved.")
        raise typer.Exit(code=1) from exc
    finally:
        client.close()

    saved = save_local_setting(settings.source_path or settings_path, "obs",
                               "websocket_password", password)
    console.print(f"\n[green]Connected to OBS {version}.[/green] Password saved to {saved} "
                  "(this PC only, never uploaded).")
    if not password:
        console.print("[yellow]OBS isn't asking for a password.[/yellow] That works, but any "
                      "program on your network could control OBS. Tick Enable Authentication "
                      "in OBS and run this again.")
    console.print("Next: [bold]ai-editor companion[/bold]")


@app.command("companion")
def companion(
    test_sound: bool = typer.Option(
        False, "--test-sound", help="Play both marker sounds and stop, to check you can hear them"
    ),
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Run the Stream Companion beside OBS (manual chapter 8).

    Start it before you go live or record, and leave the window open. It logs
    when OBS starts and stops streaming and recording, so markers and chat
    line up with your footage. Press Ctrl+C to stop it.
    """
    from rich.live import Live

    from .companion.app import Companion

    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    if test_sound:
        _play_marker_sounds(settings)
        return
    init_db(settings.db_path).close()
    app_ = Companion(settings)
    app_.start_hotkeys()
    for problem in app_.hotkey_problems:
        console.print(f"[yellow]{problem}[/yellow]")
    try:
        with Live(_companion_panel(app_), console=console, refresh_per_second=1) as live:
            while True:
                app_.step(wait=1.0)
                live.update(_companion_panel(app_))
    except KeyboardInterrupt:
        pass
    finally:
        app_.close()
    if app_.log.active:
        console.print("[yellow]Stream Companion stopped while OBS was still going.[/yellow] "
                      "Start it again soon; it will catch up with what it missed.")
    else:
        console.print("Stream Companion stopped.")


def _play_marker_sounds(settings: Settings) -> None:
    """Let the creator check they can hear the markers before going live."""
    from .companion import sound

    folder = settings.folders.cache / "companion"
    level = settings.companion.sound_volume
    for short_worthy, label in ((False, "Mark moment (Numpad +)"), (True, "Short-worthy (Numpad -)")):
        console.print(f"Playing: [bold]{label}[/bold]")
        sound.play(sound.click_file(folder, short_worthy=short_worthy, level=level))
        time.sleep(1.2)
    console.print(
        f"\nVolume is set to {level:g} of 1.0 (companion.sound_volume in Settings).\n"
        "Still too quiet? Windows' own volume applies on top: open the volume mixer "
        "(right-click the speaker icon in your taskbar) and check Python isn't turned down.\n"
        "To turn the sound off completely: set companion.confirmation_sound to false."
    )


def _companion_panel(app_) -> Table:
    obs_text = {
        "connecting": "[yellow]Connecting…[/yellow]",
        "connected": f"[green]Connected[/green] (OBS {app_.status.obs_version})",
        "waiting": "[yellow]Not connected[/yellow] - waiting for OBS (checking every 5 s)",
        "password": "[red]Password not accepted[/red]",
        "too_old": "[red]OBS too old[/red]",
    }[app_.status.obs]

    table = Table(title="AI-Editor Stream Companion", show_header=False, header_style="bold",
                  caption="Leave this open while you play. Ctrl+C to stop.")
    table.add_column("What", style="bold")
    table.add_column("Status")
    table.add_row("OBS", obs_text)
    for output, label in (("record", "Recording"), ("stream", "Streaming")):
        state = app_.log.outputs[output]
        if state.active and state.started_wall:
            since = state.started_wall.astimezone().strftime("%H:%M:%S")
            text = f"[green]On[/green] since {since}" + (" [yellow](paused)[/yellow]" if state.paused else "")
        else:
            text = "[dim]Off[/dim]"
        table.add_row(label, text)
    table.add_row("Session", app_.log.session_id or "[dim]starts when you record or go live[/dim]")
    marked = f"{app_.markers['moment']} moment, {app_.markers['short']} Short-worthy"
    if app_.last_marker:
        marked += f"  (last at {app_.last_marker})"
    table.add_row("Marked", marked)
    table.add_row("Keys", app_.hotkey_summary())
    if app_.status.sound_off_because:
        table.add_row("Sound", f"[dim]silent: {app_.status.sound_off_because}[/dim]")
    table.add_row("Logged", f"{app_.log.events_logged} event(s) this run")
    if app_.status.message:
        table.add_row("", f"[red]{app_.status.message}[/red]")
    return table


@app.command("sessions")
def sessions(
    session_id: str = typer.Argument(None, help="A session to show in full; leave out to list them"),
    last: int = typer.Option(10, "--last", "-n", help="How many recent sessions to list"),
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Show the Stream Companion's session log (manual chapter 8.4)."""
    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    conn = init_db(settings.db_path)
    try:
        if session_id:
            _print_session(conn, session_id)
        else:
            _print_sessions(conn, last)
    finally:
        conn.close()


def _local_time(iso: str) -> str:
    from datetime import datetime

    return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _print_sessions(conn, last: int) -> None:
    rows = conn.execute(
        "SELECT session_id, MIN(wall_clock) AS first, MAX(wall_clock) AS latest, COUNT(*) AS events, "
        "SUM(event_type = 'obs_record_started') AS recordings, "
        "SUM(event_type = 'obs_stream_started') AS streams, "
        "SUM(event_type IN ('marker', 'marker_short')) AS markers, "
        "(SELECT GROUP_CONCAT('#' || r.id, ' ') FROM recordings r "
        " WHERE r.session_id = companion_events.session_id) AS imported "
        "FROM companion_events GROUP BY session_id ORDER BY first DESC LIMIT ?",
        (last,),
    ).fetchall()
    if not rows:
        console.print("No sessions yet. Run [bold]ai-editor companion[/bold], then record or go live in OBS.")
        return
    table = Table(title="Stream Companion sessions", header_style="bold")
    for column in ("Session", "Started", "Last event", "Recorded", "Streamed", "Markers",
                   "Events", "In library"):
        table.add_column(column)
    for row in rows:
        table.add_row(row["session_id"], _local_time(row["first"]), _local_time(row["latest"]),
                      OK if row["recordings"] else "-", OK if row["streams"] else "-",
                      str(row["markers"]), str(row["events"]), row["imported"] or "-")
    console.print(table)
    console.print("Details: [bold]ai-editor sessions <session>[/bold]")


EVENT_LABELS = {
    "obs_record_started": "Recording started",
    "obs_record_stopped": "Recording stopped",
    "obs_record_paused": "Recording paused",
    "obs_record_resumed": "Recording resumed",
    "obs_record_file_changed": "Recording continued in a new file",
    "obs_stream_started": "Stream started",
    "obs_stream_stopped": "Stream stopped",
    "obs_stream_reconnecting": "Stream connection dropped",
    "obs_stream_reconnected": "Stream reconnected",
    "obs_disconnected": "Lost connection to OBS",
    "obs_reconnected": "Reconnected to OBS",
    "obs_closing": "OBS closed",
    "marker": "Marker",
    "marker_short": "Marker (Short-worthy)",
}


def _print_session(conn, session_id: str) -> None:
    import json

    from .analysis.captions import clock

    rows = conn.execute(
        "SELECT * FROM companion_events WHERE session_id = ? ORDER BY wall_clock, id", (session_id,)
    ).fetchall()
    if not rows:
        console.print(f"[red]No session called {session_id}.[/red] Run [bold]ai-editor sessions[/bold] to list them.")
        raise typer.Exit(code=1)
    table = Table(title=f"Session {session_id}", header_style="bold")
    for column in ("Time", "What happened", "Into stream", "Into recording", "Detail"):
        table.add_column(column)
    for row in rows:
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        detail = []
        if payload.get("path"):
            detail.append(Path(payload["path"]).name)
        if payload.get("noticed_late"):
            detail.append("[yellow]noticed after it happened[/yellow]")
        table.add_row(
            _local_time(row["wall_clock"]),
            EVENT_LABELS.get(row["event_type"], row["event_type"]),
            clock(row["stream_time_sec"]) if row["stream_time_sec"] is not None else "-",
            clock(row["recording_time_sec"]) if row["recording_time_sec"] is not None else "-",
            "; ".join(detail),
        )
    console.print(table)


SIGNAL_LABELS = {
    "marker": "you marked it",
    "marker_short": "you marked it (Short)",
    "laughter": "laughter",
    "scream": "screaming",
    "shout": "shouting",
    "gunfire": "gunfire",
    "explosion": "explosions",
    "chat_z": "chat busy",
    "energy_z": "loud",
    "speech": "talking",
    "combination": "several at once",
}


def _refresh_score(conn, settings: Settings, recording_id: int, duration_sec: float | None):
    """Work out the hype score from whatever signals the recording now has."""
    from .analysis.hype import build

    seconds = int(duration_sec or 0)
    if seconds <= 0:
        return None
    return build(conn, settings, recording_id, seconds)


def _refresh_clips(conn, settings: Settings, row):
    """Score the recording and cut its candidate clips. Instant: nothing is re-analysed.

    Returns (clips, score result), or (None, None) if there is nothing to score.
    """
    from .analysis.clips import build_clips, explain, load_words, store_clips
    from .analysis.hype import load_signals
    from .analysis.pipeline import load_scene_cuts

    result = _refresh_score(conn, settings, row["id"], row["duration_sec"])
    if result is None:
        return None, None
    words = load_words(conn, row["id"])
    clips = build_clips(result.score, words=words, cuts=load_scene_cuts(settings, row),
                        duration=float(row["duration_sec"]), settings=settings.clips)
    for clip in clips:
        clip.reasons = explain(clip, result.parts)
    store_clips(conn, row["id"], clips,
                signals=load_signals(conn, row["id"], len(result.score)), words=words)
    return clips, result


@app.command("score")
def score(
    recording: str = typer.Argument(
        ..., help="The recording's number from the library, or its file path"
    ),
    top: int = typer.Option(15, "--top", "-n", help="How many moments to list"),
    gap: int = typer.Option(45, "--gap", help="Seconds to keep between listed moments"),
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Rank the best moments in a recording (spec section 7.3).

    Everything analysis heard is combined into one score per second: your
    markers, laughter, shouting, gunfire, sudden loudness and chat. Cutting
    these into clips is the next step; this is the list to check first.
    """
    from .analysis import resolve_recording
    from .analysis.audio_signals import top_moments
    from .analysis.captions import clock
    from .analysis.hype import why

    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    conn = init_db(settings.db_path)
    try:
        row = resolve_recording(conn, recording)
        if row["analysis_status"] != "complete":
            console.print(f"Recording #{row['id']} hasn't been analysed yet. "
                          f"Run: ai-editor analyze {row['id']}")
            raise typer.Exit(code=1)
        result = _refresh_score(conn, settings, row["id"], row["duration_sec"])
    except AIEditorError as exc:
        console.print(f"[red]{exc.user_message()}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        conn.close()

    if result is None or not result.score.size:
        console.print("[yellow]Nothing to score in that recording.[/yellow]")
        raise typer.Exit(code=1)

    peaks = top_moments(result.score, count=top, min_gap=gap, threshold=0.15)
    table = Table(title=f"Best moments in #{row['id']}: {row['title']}", header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Time")
    table.add_column("Score", justify="right")
    table.add_column("Why")
    for place, (second, value) in enumerate(
        sorted(peaks, key=lambda p: p[1], reverse=True), start=1
    ):
        reasons = ", ".join(
            f"{SIGNAL_LABELS.get(name, name)}" for name, _ in why(result.parts, second)
        )
        table.add_row(str(place), clock(second), f"{value:.2f}", reasons or "-")
    console.print(table)
    console.print(
        "Scores are relative to this recording: 1.00 is its best moment.\n"
        "Jump to these times in the preview copy and tell me which are wrong."
    )
    if result.missing:
        console.print(
            "[dim]Not available in this recording: "
            + ", ".join(SIGNAL_LABELS.get(n, n) for n in result.missing)
            + ".[/dim]"
        )


@app.command("clips")
def clips_command(
    recording: str = typer.Argument(
        ..., help="The recording's number from the library, or its file path"
    ),
    top: int = typer.Option(20, "--top", "-n", help="How many clips to list"),
    export: int = typer.Option(
        0, "--export", "-e",
        help="Also save the best N clips as small videos you can watch (with subtitles)",
    ),
    open_folder: bool = typer.Option(
        False, "--open", help="Open the previews folder in File Explorer afterwards"
    ),
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Cut a recording's best moments into clips with clean edges (spec section 7.3).

    Each clip starts before the build-up, ends after the reaction, never cuts
    mid-word, and never runs into a menu or loading screen. Use --export to
    watch them.
    """
    from .analysis import resolve_recording
    from .analysis.captions import clock
    from .analysis.clips import load_words
    from .analysis.previews import export_previews, previews_folder

    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    conn = init_db(settings.db_path)
    try:
        row = resolve_recording(conn, recording)
        if row["analysis_status"] != "complete":
            console.print(f"Recording #{row['id']} hasn't been analysed yet. "
                          f"Run: ai-editor analyze {row['id']}")
            raise typer.Exit(code=1)
        clips, _ = _refresh_clips(conn, settings, row)
        if not clips:
            console.print("[yellow]No moment in that recording scored high enough to be a clip.[/yellow] "
                          "Lower clips.min_score in Settings to see more.")
            raise typer.Exit(code=1)

        ranked = sorted(clips, key=lambda c: c.score, reverse=True)
        table = Table(title=f"Clips in #{row['id']}: {row['title']}  ({len(clips)} found)",
                      header_style="bold")
        for column in ("#", "Start", "End", "Length", "Score", "Why", "What was said"):
            table.add_column(column, overflow="fold" if column == "What was said" else "ellipsis")
        words = load_words(conn, row["id"])
        for rank, clip in enumerate(ranked[:top], start=1):
            said = " ".join(w.text for w in words if clip.start <= w.start and w.end <= clip.end)
            table.add_row(
                str(rank), clock(clip.start), clock(clip.end), f"{clip.length:.0f}s",
                f"{clip.score:.2f}",
                ", ".join(SIGNAL_LABELS.get(n, n) for n, _ in clip.reasons) or "-",
                (said[:90] + "…") if len(said) > 90 else (said or "[dim]no speech[/dim]"),
            )
        console.print(table)

        if export:
            progress = _progress_bar()
            task = progress.add_task("Saving clip previews", total=1.0)
            progress.start()
            try:
                files = export_previews(conn, settings, row, words, count=export,
                                        on_progress=lambda f: progress.update(task, completed=f))
            finally:
                progress.stop()
            folder = previews_folder(settings, row["id"], row["title"])
            console.print(f"\n[green]{len(files)} previews saved[/green] to:\n  {folder}\n"
                          "Named by rank, start time and score. Open them in VLC; the "
                          "subtitles load by themselves.")
            if open_folder:
                import os

                os.startfile(folder)  # noqa: S606 -- opens File Explorer on our own folder
            else:
                console.print(f"To open the folder: [bold]ai-editor clips {row['id']} "
                              f"--export {export} --open[/bold]")
        else:
            console.print(f"Watch them: [bold]ai-editor clips {row['id']} --export 10 --open[/bold]")
    except AIEditorError as exc:
        console.print(f"[red]{exc.user_message()}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        conn.close()


@app.command("library")
def library(
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """List the recordings in the clip library."""
    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    conn = init_db(settings.db_path)
    rows = conn.execute(
        "SELECT r.*, "
        "(SELECT COUNT(*) FROM audio_tracks a WHERE a.recording_id = r.id) AS tracks, "
        "(SELECT COUNT(*) FROM audio_tracks a WHERE a.recording_id = r.id "
        " AND a.extracted_path IS NOT NULL) AS tracks_ready "
        "FROM recordings r ORDER BY r.imported_at DESC"
    ).fetchall()
    conn.close()

    if not rows:
        console.print("The library is empty. Import a recording with: ai-editor import \"<file>\"")
        return

    table = Table(title="Clip library", header_style="bold")
    for column in ("#", "Title", "Source", "Game", "Length", "Tracks", "Preview", "Audio",
                   "Analysed", "Chat", "Source found"):
        table.add_column(column)
    for row in rows:
        table.add_row(
            str(row["id"]),
            row["title"] or "-",
            "Twitch" if row["source_type"] == "twitch_vod" else "Local",
            row["game"] or "-",
            _duration(row["duration_sec"]),
            str(row["tracks"]),
            OK if row["proxy_path"] and Path(row["proxy_path"]).exists() else "-",
            OK if row["tracks"] and row["tracks_ready"] == row["tracks"] else "-",
            {"complete": OK, "running": "[yellow]running[/yellow]",
             "paused": "[yellow]paused[/yellow]", "failed": FAIL}.get(row["analysis_status"], "-"),
            OK if row["twitch_vod_id"] else "-",
            OK if Path(row["source_file"]).exists() else FAIL,
        )
    console.print(table)


if __name__ == "__main__":
    app()
