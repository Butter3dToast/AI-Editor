"""The sound of a finished video: which tracks, and the marker beeps taken out.

**Which tracks.** OBS records a mixed track (what the stream heard) and, set
up as in manual chapter 7, separate tracks for the mic, the game and Discord.
A finished video is rebuilt from the separate ones where they really are
separate: the music playing on stream (Spotify) is only on the mixed track,
and music on YouTube gets videos claimed. Until 27 Sep the creator's OBS put
the same sound on several tracks -- the "mic" track was a copy of the mixed
one -- so every recording is checked, and one without real separate tracks
uses the mixed track, exactly as the stream sounded.

**Beeps.** On the 26 Sep League stream the Companion's confirmation click
reached the microphone (a stand-up mic hears the headphones) at all 8
markers: a pure 1 kHz tone about 0.6 s after each press. Each one is found by
its shape, near a marker only, and a narrow filter takes out that one pitch
for half a second, so the voice and game around it are untouched.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..config import Settings
from ..logging_setup import get_logger

log = get_logger(__name__)

# Tracks rebuilt into a finished video's sound, in this order.
SEPARATE_ROLES = ("mic", "game", "voice_chat")

# Two tracks count as copies when what differs is this far below what's there
# (a million times quieter). OBS encodes a copied track identically, so a copy
# differs by nothing at all; real separate tracks differ by the whole game.
COPY_LEVEL = 1e-6
SAMPLE_POINTS = (0.1, 0.3, 0.5, 0.7, 0.9)  # where in the recording to compare
SAMPLE_SEC = 10.0

# The Companion's clicks (companion/sound.py): 1 kHz, then for a Short a
# second blip at 1.5 kHz. The template is the shortest blip, so both match.
BEEP_HZ = (1000.0, 1500.0)
BEEP_TEMPLATE_SEC = 0.10
BEEP_SEARCH_SEC = (-0.5, 2.5)      # around the marker press
BEEP_MATCH = 0.6                   # 0.80-0.98 on 26 Sep; ordinary sound 0.2 or less
BEEP_SPAN_SEC = (-0.12, 0.45)      # what to filter, from where the match is (up to 0.06 s into a 0.16 s blip)
NOTCH_WIDTH_HZ = 150


@dataclass
class AudioChoice:
    streams: list[int]                 # stream indexes mixed together
    voice: int                         # the stream the creator's voice (and any beep) is on
    separate: bool                     # rebuilt from separate tracks (stream music left out)
    beeps: list[tuple[float, float]] = field(default_factory=list)  # recording time

    music_by_choice: bool = False      # the mixed track because Settings asked for the music

    def describe(self) -> str:
        if self.separate:
            return "your separate mic, game and Discord tracks (music on stream left out)"
        if self.music_by_choice:
            return "the stream's mixed track, music included (Settings: keep the stream's music)"
        return "the stream's mixed track, as viewers heard it"


def _read(path: Path, start_sec: float, seconds: float):
    import soundfile as sf

    with sf.SoundFile(str(path)) as f:
        rate = f.samplerate
        start = max(0, min(int(start_sec * rate), f.frames - 1))
        f.seek(start)
        x = f.read(int(seconds * rate), dtype="float32", always_2d=True)
    return x.mean(axis=1), rate


def is_copy(a: Path, b: Path) -> bool:
    """Whether two extracted tracks hold the same sound."""
    import soundfile as sf

    length = min(sf.info(str(a)).duration, sf.info(str(b)).duration)
    differs = there = 0.0
    for point in SAMPLE_POINTS:
        x, _ = _read(a, length * point, SAMPLE_SEC)
        y, _ = _read(b, length * point, SAMPLE_SEC)
        n = min(len(x), len(y))
        differs += float(np.sum((x[:n] - y[:n]) ** 2))
        there += float(np.sum(x[:n] ** 2) + np.sum(y[:n] ** 2))
    return there > 0 and differs <= COPY_LEVEL * there


def choose_tracks(conn: sqlite3.Connection, settings: Settings, recording_id: int) -> AudioChoice:
    rows = conn.execute("SELECT stream_index, role, extracted_path FROM audio_tracks "
                        "WHERE recording_id = ? ORDER BY stream_index", (recording_id,)).fetchall()
    if not rows:
        raise ValueError(f"Recording #{recording_id} has no audio tracks listed")
    by_role = {r["role"]: r for r in rows}
    mixed = by_role.get("mixed") or rows[0]
    fallback = AudioChoice([mixed["stream_index"]], mixed["stream_index"], False)
    if settings.render.include_stream_music:
        fallback.music_by_choice = True
        return fallback

    wanted = [role for role in SEPARATE_ROLES
              if role in by_role and (role != "voice_chat" or settings.render.include_voice_chat)]
    if "mic" not in wanted or "game" not in wanted:
        return fallback
    paths = {role: Path(by_role[role]["extracted_path"] or "") for role in wanted}
    paths["mixed"] = Path(mixed["extracted_path"] or "")
    if not all(p.is_file() for p in paths.values()):
        log.warning("Recording #%s: its extracted tracks are missing, so the mixed track is used",
                    recording_id)
        return fallback
    # A separate track that's really the whole mix, or a copy of another one,
    # would put everything in twice.
    if is_copy(paths["mic"], paths["mixed"]) or is_copy(paths["game"], paths["mixed"]) \
            or is_copy(paths["mic"], paths["game"]):
        return fallback
    if "voice_chat" in wanted and (is_copy(paths["voice_chat"], paths["game"])
                                   or is_copy(paths["voice_chat"], paths["mic"])
                                   or is_copy(paths["voice_chat"], paths["mixed"])):
        wanted.remove("voice_chat")
    mic = by_role["mic"]["stream_index"]
    return AudioChoice([by_role[role]["stream_index"] for role in wanted], mic, True)


def beep_match(x: np.ndarray, rate: int, hz: float) -> np.ndarray:
    """How much each moment looks like a pure tone of ``hz`` (0-1)."""
    from scipy.signal import fftconvolve

    tone = np.sin(2 * np.pi * hz * np.arange(int(BEEP_TEMPLATE_SEC * rate)) / rate)
    if len(x) < len(tone):
        return np.zeros(0)
    fit = np.abs(fftconvolve(x, tone[::-1], "valid"))
    energy = np.sqrt(np.clip(fftconvolve(x ** 2, np.ones(len(tone)), "valid"), 0, None))
    return fit / (energy * np.sqrt(np.sum(tone ** 2)) + 1e-9)


def find_beeps(wav: Path, markers: list[float]) -> list[tuple[float, float]]:
    """The stretches to filter: one per marker whose click was recorded."""
    found = []
    for press in markers:
        start = max(0.0, press + BEEP_SEARCH_SEC[0])
        x, rate = _read(wav, start, BEEP_SEARCH_SEC[1] - BEEP_SEARCH_SEC[0])
        match = beep_match(x, rate, BEEP_HZ[0])
        if match.size and match.max() >= BEEP_MATCH:
            at = start + int(match.argmax()) / rate
            found.append((at + BEEP_SPAN_SEC[0], at + BEEP_SPAN_SEC[1]))
    return found


def markers_of(conn: sqlite3.Connection, recording_id: int) -> list[float]:
    return [r[0] for r in conn.execute(
        "SELECT recording_time_sec FROM companion_events WHERE recording_id = ? AND "
        "event_type IN ('marker', 'marker_short') AND recording_time_sec IS NOT NULL "
        "ORDER BY recording_time_sec", (recording_id,))]


def plan_audio(conn: sqlite3.Connection, settings: Settings, recording_id: int) -> AudioChoice:
    """Everything the renderer needs to know about one recording's sound."""
    choice = choose_tracks(conn, settings, recording_id)
    markers = markers_of(conn, recording_id)
    if markers:
        row = conn.execute("SELECT extracted_path FROM audio_tracks WHERE recording_id = ? AND "
                           "stream_index = ?", (recording_id, choice.voice)).fetchone()
        wav = Path(row["extracted_path"]) if row and row["extracted_path"] else None
        if wav and wav.is_file():
            choice.beeps = find_beeps(wav, markers)
        else:
            log.warning("Recording #%s: can't check for marker beeps, its extracted sound is missing",
                        recording_id)
    return choice


def beep_filters(beeps: list[tuple[float, float]], seg_in: float, seg_out: float) -> list[str]:
    """FFmpeg filters taking the beeps out of one segment (times from its start)."""
    filters = []
    for a, b in beeps:
        if b <= seg_in or a >= seg_out:
            continue
        lo, hi = max(0.0, a - seg_in), min(seg_out, b) - seg_in
        when = f"between(t,{lo:.3f},{hi:.3f})"
        for hz in BEEP_HZ:
            # Twice over: one pass takes the tone down about 20 dB, two put it
            # under the background.
            filters += [f"bandreject=f={hz:.0f}:width_type=h:width={NOTCH_WIDTH_HZ}:enable='{when}'"] * 2
    return filters
