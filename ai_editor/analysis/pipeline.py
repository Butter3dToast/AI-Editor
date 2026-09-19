"""The analysis job: turn an imported recording into per-second signals.

Steps, each resumable and cached like the import (spec sections 3 and 5):

1. prepare_audio  -- resample the imported WAVs to what each model wants
2. transcribe     -- Whisper, word by word                        (GPU)
3. sound_events   -- laughter, shouting, gunfire...              (GPU)
4. loudness       -- per-second volume of voice and game tracks   (CPU)

The two GPU steps run one after the other and each unloads its model before
the next begins (spec section 3). Every step writes a file; the database is
then filled from those files. Files are the source of truth, so a setting that
only affects how results are *read* (the silence threshold) takes effect
without re-running anything.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from ..config import Settings
from ..errors import NotImported, RecordingNotFound
from ..ffmpeg import content_hash, run_ffmpeg
from ..ingest import recording_cache_dir
from ..jobs import JobQueue, make_cache_key
from ..logging_setup import get_logger
from . import audio_signals, captions
from .sound_events import detect_sound_events
from .transcript import accepted_words, transcribe, voice_detector_on

log = get_logger(__name__)

# Bump when a step's output changes meaning, so old results are regenerated.
ANALYSIS_VERSION = 3

STEPS = ("prepare_audio", "transcribe", "sound_events", "loudness")

ProgressCallback = Callable[[str, float], None]


# --- Finding the recording and its tracks ----------------------------------


def resolve_recording(conn: sqlite3.Connection, target: str) -> sqlite3.Row:
    """Accept a library number ("1") or a file path."""
    target = target.strip().strip('"')
    if target.isdigit():
        row = conn.execute("SELECT * FROM recordings WHERE id = ?", (int(target),)).fetchone()
        if row is None:
            raise RecordingNotFound(f"There is no recording number {target}")
        return row

    path = Path(target)
    if not path.exists():
        raise RecordingNotFound(f"No file at {target}")
    # Matched by content, so a recording that was moved is still found.
    row = conn.execute(
        "SELECT * FROM recordings WHERE content_hash = ?", (content_hash(path),)
    ).fetchone()
    if row is None:
        raise RecordingNotFound(f"{path.name} hasn't been imported yet")
    return row


@dataclass(frozen=True)
class TrackChoice:
    """Which imported track each kind of analysis listens to."""

    voice_index: int
    voice_role: str
    voice_wav: Path
    game_index: int
    game_role: str
    game_wav: Path

    @property
    def separate_game_track(self) -> bool:
        return self.game_index != self.voice_index


def choose_tracks(conn: sqlite3.Connection, recording_id: int) -> TrackChoice:
    """The creator's voice from the mic track, game sound from the game track.

    With OBS set up per manual chapter 7 those are separate tracks. With one
    mixed track (a Twitch VOD, or EP 1), both come from the same place, and
    the transcript will contain whoever else was speaking too.
    """
    rows = conn.execute(
        "SELECT stream_index, role, extracted_path FROM audio_tracks "
        "WHERE recording_id = ? ORDER BY stream_index",
        (recording_id,),
    ).fetchall()
    missing = [r for r in rows if not r["extracted_path"] or not Path(r["extracted_path"]).exists()]
    if not rows or missing:
        raise NotImported()

    by_role = {r["role"]: r for r in rows}

    def pick(*preferences: str) -> sqlite3.Row:
        for role in preferences:
            if role in by_role:
                return by_role[role]
        return rows[0]

    voice = pick("mic", "mixed")
    game = pick("game", "mixed")
    return TrackChoice(
        voice["stream_index"], voice["role"], Path(voice["extracted_path"]),
        game["stream_index"], game["role"], Path(game["extracted_path"]),
    )


# --- Steps -----------------------------------------------------------------


def prepare_audio(
    tracks: TrackChoice, out_dir: Path, duration: float,
    on_progress: Callable[[float], None] | None,
) -> Path:
    """Mono copies at the rates the models were trained on.

    Whisper expects 16 kHz and PANNs 32 kHz. Resampling once with FFmpeg here
    is quicker than each model doing it in Python, and the small mono files are
    what the later steps read.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    finals = [out_dir / "voice_16k.wav", out_dir / "voice_32k.wav"]
    args = ["-i", str(tracks.voice_wav)]
    for final, rate in zip(finals, (16_000, 32_000)):
        args += ["-map", "0:a:0", "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le",
                 "-rf64", "auto", str(final.with_suffix(".partial.wav"))]
    if tracks.separate_game_track:
        finals.append(out_dir / "game_32k.wav")
        args += ["-i", str(tracks.game_wav), "-map", "1:a:0", "-ac", "1", "-ar", "32000",
                 "-c:a", "pcm_s16le", "-rf64", "auto",
                 str(finals[-1].with_suffix(".partial.wav"))]

    try:
        run_ffmpeg(args, duration_sec=duration, on_progress=on_progress,
                   what="preparing audio for analysis")
    except BaseException:
        for final in finals:
            final.with_suffix(".partial.wav").unlink(missing_ok=True)
        raise
    for final in finals:
        final.with_suffix(".partial.wav").replace(final)
    return out_dir


def _write_json(path: Path, data: object) -> str:
    partial = path.with_suffix(".partial.json")
    partial.write_text(json.dumps(data), encoding="utf-8")
    partial.replace(path)
    return str(path)


# --- The whole analysis ----------------------------------------------------


@dataclass
class StepReport:
    name: str
    reused: bool
    seconds: float = 0.0


@dataclass
class AnalysisResult:
    recording_id: int
    job_id: int
    status: str
    error_message: str | None
    analysis_dir: Path
    srt_path: Path | None
    proxy_srt_path: Path | None
    tracks: TrackChoice
    steps: list[StepReport] = field(default_factory=list)


def analyze_recording(
    conn: sqlite3.Connection,
    settings: Settings,
    target: str,
    *,
    on_progress: ProgressCallback | None = None,
    on_started: Callable[[sqlite3.Row, TrackChoice], None] | None = None,
) -> AnalysisResult:
    """Run (or resume) the analysis of one imported recording."""
    row = resolve_recording(conn, target)
    recording_id = row["id"]
    tracks = choose_tracks(conn, recording_id)
    if on_started:
        on_started(row, tracks)

    duration = float(row["duration_sec"] or 0.0)
    seconds = max(1, int(np.ceil(duration)))
    digest = row["content_hash"]
    out_dir = recording_cache_dir(settings, digest) / "analysis"
    # Resampled audio gets its own folder: the step is judged "done" by its
    # folder existing, and the results written beside it mustn't count.
    prepared = out_dir / "prepared"
    voice_16k, voice_32k = prepared / "voice_16k.wav", prepared / "voice_32k.wav"
    game_32k = prepared / "game_32k.wav" if tracks.separate_game_track else None

    queue = JobQueue(conn)
    queue.recover_interrupted()
    open_job = queue.find_open("analyze", recording_id)
    if open_job:
        queue.resume(open_job.id)
        job_id = open_job.id
    else:
        job_id = queue.enqueue("analyze", {"recording_id": recording_id}, recording_id=recording_id)

    conn.execute("UPDATE recordings SET analysis_status = 'running' WHERE id = ?", (recording_id,))
    conn.commit()

    ran: dict[str, float] = {}

    def timed(name: str, action: Callable[[], str]) -> Callable[[], str]:
        def run() -> str:
            # Show the bar straight away: loading an AI model can take a while
            # before the step reports any progress of its own.
            if on_progress:
                on_progress(name, 0.0)
            started = time.monotonic()
            output = action()
            ran[name] = time.monotonic() - started
            return output
        return run

    def reporter(step: str) -> Callable[[float], None]:
        return queue.step_reporter(job_id, step, STEPS.index(step), len(STEPS), on_progress)

    track_key = (tracks.voice_index, tracks.game_index)
    detector = voice_detector_on(settings.analysis.voice_detector, tracks.voice_role)
    steps = [
        (
            "prepare_audio",
            make_cache_key(digest, "prepare_audio", ANALYSIS_VERSION, *track_key),
            timed("prepare_audio", lambda: str(
                prepare_audio(tracks, prepared, duration, reporter("prepare_audio"))
            )),
        ),
        (
            "transcribe",
            make_cache_key(digest, "transcribe", ANALYSIS_VERSION, tracks.voice_index,
                           settings.analysis.transcription_model, settings.analysis.language,
                           detector),
            timed("transcribe", lambda: _write_json(
                out_dir / "transcript.json",
                transcribe(settings, voice_16k, duration, reporter("transcribe"),
                           use_voice_detector=detector),
            )),
        ),
        (
            "sound_events",
            make_cache_key(digest, "sound_events", ANALYSIS_VERSION, *track_key,
                           settings.analysis.event_window_sec),
            timed("sound_events", lambda: _write_json(
                out_dir / "sound_events.json",
                detect_sound_events(settings, voice_32k, game_32k, seconds,
                                    reporter("sound_events")),
            )),
        ),
        (
            "loudness",
            make_cache_key(digest, "loudness", ANALYSIS_VERSION, *track_key),
            timed("loudness", lambda: _write_json(
                out_dir / "loudness.json",
                _measure_loudness(voice_16k, game_32k, reporter("loudness")),
            )),
        ),
    ]
    try:
        queue.run(job_id, steps)
    except KeyboardInterrupt:
        conn.execute("UPDATE recordings SET analysis_status = 'paused' WHERE id = ?", (recording_id,))
        conn.commit()
        raise

    job = queue.get(job_id)
    status = job.status if job else "unknown"
    error = conn.execute("SELECT error_message FROM jobs WHERE id = ?", (job_id,)).fetchone()[0]

    srt_path = proxy_srt = None
    if status == "complete":
        srt_path, proxy_srt = store_results(conn, settings, row, tracks, out_dir, seconds)
    conn.execute(
        "UPDATE recordings SET analysis_status = ? WHERE id = ?",
        ("complete" if status == "complete" else "failed", recording_id),
    )
    conn.commit()

    return AnalysisResult(
        recording_id=recording_id,
        job_id=job_id,
        status=status,
        error_message=error,
        analysis_dir=out_dir,
        srt_path=srt_path,
        proxy_srt_path=proxy_srt,
        tracks=tracks,
        steps=[StepReport(name, name not in ran, ran.get(name, 0.0)) for name in STEPS],
    )


def _measure_loudness(
    voice_16k: Path, game_32k: Path | None, on_progress: Callable[[float], None] | None
) -> dict[str, list[float]]:
    def half(offset: float) -> Callable[[float], None]:
        return lambda f: on_progress(offset + f / 2) if on_progress else None

    result = {"voice_db": audio_signals.per_second_db(
        voice_16k, half(0.0) if game_32k else on_progress).round(2).tolist()}
    if game_32k is not None:
        result["game_db"] = audio_signals.per_second_db(game_32k, half(0.5)).round(2).tolist()
    return result


# --- Storing ---------------------------------------------------------------


def store_results(
    conn: sqlite3.Connection,
    settings: Settings,
    row: sqlite3.Row,
    tracks: TrackChoice,
    out_dir: Path,
    seconds: int,
) -> tuple[Path, Path | None]:
    """Replace this recording's transcript and signals with the saved results.

    Safe to repeat: the previous rows are removed first, so analysing twice
    never produces duplicates.
    """
    recording_id = row["id"]
    transcript = json.loads((out_dir / "transcript.json").read_text(encoding="utf-8"))
    events = json.loads((out_dir / "sound_events.json").read_text(encoding="utf-8"))
    loudness = json.loads((out_dir / "loudness.json").read_text(encoding="utf-8"))

    kept, dropped = accepted_words(transcript)
    words = [captions.Word(w["w"], w["s"], w["e"], w["p"]) for w in kept]
    for segment in dropped:
        log.info("Set aside likely mishearing at %.1fs: %r", segment["s"], segment["text"])

    conn.execute("DELETE FROM transcript_words WHERE recording_id = ?", (recording_id,))
    conn.executemany(
        "INSERT INTO transcript_words (recording_id, idx, word, start_sec, end_sec, "
        "confidence, source_role) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (recording_id, i, w.text, w.start, w.end, w.probability, tracks.voice_role)
            for i, w in enumerate(words)
        ],
    )

    voice_db = np.array(loudness["voice_db"], dtype=np.float32)
    game_db = np.array(loudness["game_db"], dtype=np.float32) if "game_db" in loudness else None
    speech = audio_signals.speech_coverage(((w.start, w.end) for w in words), seconds)
    signals: dict[str, np.ndarray] = {
        "voice_db": voice_db,
        # "Unusually loud" compared with normal talking, not with the silences.
        "energy_z": audio_signals.robust_zscore(voice_db, baseline_mask=speech >= 0.5),
        "silence": audio_signals.silence_mask(
            *([voice_db, game_db] if game_db is not None else [voice_db]),
            threshold_db=settings.analysis.silence_threshold_db,
        ),
        "speech": speech,
    }
    if game_db is not None:
        signals["game_db"] = game_db
    for group, values in events.items():
        signals[group] = np.array(values, dtype=np.float32)

    conn.execute("DELETE FROM signals WHERE recording_id = ?", (recording_id,))
    conn.executemany(
        "INSERT INTO signals (recording_id, t_sec, name, value) VALUES (?, ?, ?, ?)",
        (
            (recording_id, t, name, float(value))
            for name, values in signals.items()
            for t, value in enumerate(values[:seconds])
        ),
    )
    conn.commit()

    cues = captions.build_cues(words)
    srt_path = captions.write_srt(cues, out_dir / "transcript.srt")
    # A copy beside the proxy with the same name: VLC loads it automatically.
    proxy_srt = None
    if row["proxy_path"] and Path(row["proxy_path"]).exists():
        proxy_srt = captions.write_srt(cues, Path(row["proxy_path"]).with_suffix(".srt"))
    conn.execute(
        "UPDATE recordings SET notes = ? WHERE id = ?",
        (json.dumps({"phrases_set_aside": len(dropped)}), recording_id),
    )
    conn.commit()
    log.info("Stored %d words and %d signal types for recording #%d (%d phrases set aside)",
             len(words), len(signals), recording_id, len(dropped))
    return srt_path, proxy_srt
