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
    settings_path: Path = typer.Option(
        DEFAULT_SETTINGS_PATH, "--settings", "-s", help="Path to settings.yaml"
    ),
) -> None:
    """Import a local OBS recording: preview copy, audio, and library entry.

    The file is read where it is, never copied or changed. Safe to run again:
    finished work is reused, and an interrupted import continues where it
    stopped.
    """
    settings = _load(settings_path)
    setup_logging(settings.log_dir, settings.logging.level)
    conn = init_db(settings.db_path)

    progress = Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TextColumn("elapsed,"),
        TimeRemainingColumn(),
        TextColumn("left"),
        console=console,
    )
    tasks: dict[str, TaskID] = {}

    def on_registered(reg: Registration, space_warning: str | None) -> None:
        info = reg.info
        table = Table(title=f"Importing: {info.path.name}", header_style="bold", show_header=False)
        table.add_column("Property")
        table.add_column("Value")
        table.add_row("Library entry", f"#{reg.recording_id} ({'new' if reg.is_new else 'already in library'})")
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
        if not info.is_multitrack:
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
        conn.close()

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


ANALYSIS_LABELS = {
    "prepare_audio": "Preparing audio",
    "transcribe": "Transcribing speech",
    "sound_events": "Listening for laughter, shouts, gunfire",
    "loudness": "Measuring loudness",
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
        table = Table(title=f"Analysing: {row['title']}", header_style="bold", show_header=False)
        table.add_column("Property")
        table.add_column("Value")
        table.add_row("Library entry", f"#{row['id']}")
        table.add_row("Game", row["game"] or "-")
        table.add_row("Length", _duration(row["duration_sec"]))
        table.add_row("Voice from", f"track {tracks.voice_index} ({tracks.voice_role})")
        table.add_row("Game sound from", f"track {tracks.game_index} ({tracks.game_role})")
        console.print(table)
        if tracks.voice_role != "mic":
            console.print(
                "\n[yellow]No separate microphone track.[/yellow] The transcript will "
                "include everyone audible, such as in-game characters and teammates, "
                "not only you."
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
    conn.close()

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
    for column in ("#", "Title", "Game", "Length", "Tracks", "Preview", "Audio", "Analysed",
                   "Source found"):
        table.add_column(column)
    for row in rows:
        table.add_row(
            str(row["id"]),
            row["title"] or "-",
            row["game"] or "-",
            _duration(row["duration_sec"]),
            str(row["tracks"]),
            OK if row["proxy_path"] and Path(row["proxy_path"]).exists() else "-",
            OK if row["tracks"] and row["tracks_ready"] == row["tracks"] else "-",
            {"complete": OK, "running": "[yellow]running[/yellow]",
             "paused": "[yellow]paused[/yellow]", "failed": FAIL}.get(row["analysis_status"], "-"),
            OK if Path(row["source_file"]).exists() else FAIL,
        )
    console.print(table)


if __name__ == "__main__":
    app()
