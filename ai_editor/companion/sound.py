"""The quiet click that confirms a marker -- and making sure nobody else hears it.

The creator's rule: viewers must never hear a random sound. Whether they would
depends on how OBS collects sound. A "Desktop Audio" source captures whatever
comes out of the speakers, including this click; "Application Audio Capture"
sources take sound from the game or Discord alone, so the click never reaches
the stream.

So before playing anything, the Companion asks OBS what it is capturing. If
any Desktop Audio source is live and not muted, the click stays off and the
Companion says why.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from ..logging_setup import get_logger

log = get_logger(__name__)

# OBS's own names for its sound sources.
DESKTOP_AUDIO_KIND = "wasapi_output_capture"  # everything the PC plays
SAMPLE_RATE = 44100


def desktop_audio_source(client) -> str | None:
    """The name of a live Desktop Audio source in OBS, if there is one."""
    try:
        inputs = client.request("GetInputList").get("inputs") or []
    except Exception as exc:  # noqa: BLE001  -- never let this stop a marker
        log.warning("Couldn't ask OBS about its audio sources: %s", exc)
        return None
    for source in inputs:
        if source.get("inputKind") != DESKTOP_AUDIO_KIND:
            continue
        name = source.get("inputName", "Desktop Audio")
        try:
            if client.request("GetInputMute", {"inputName": name}).get("inputMuted"):
                continue  # muted in OBS: viewers hear nothing from it
        except Exception as exc:  # noqa: BLE001
            log.warning("Couldn't check whether %s is muted: %s", name, exc)
        return name
    return None


# Loudness took two goes to get right. 70 ms at a quarter volume was inaudible;
# 110 ms at half volume was "very silent" over a game. Now close to the loudest
# a WAV can be, and long enough to register, with companion.sound_volume to
# turn it down. Longer also sounds louder, so the blips grew with the level.
DEFAULT_LEVEL = 0.9
TONES = {
    # name: (frequency, seconds) for each blip, in order. 1 kHz is where human
    # hearing is most sensitive, so it carries over game sound without being loud.
    "marker": [(1000.0, 0.16)],
    "marker-short": [(1000.0, 0.10), (1500.0, 0.14)],  # two rising blips
}
GAP_SECONDS = 0.04

# Windows powers the sound device down when nothing is playing, and waking it
# eats the beginning of the next sound. The creator heard the second marker
# sound but not the first, which is exactly that. A moment of silence in front
# of the blip gives the device time to wake, so the whole blip is heard.
SILENCE_LEAD_SECONDS = 0.18


def click_file(folder: Path, *, short_worthy: bool = False,
               level: float = DEFAULT_LEVEL) -> Path:
    """Write (once) the small WAV that confirms a marker.

    Made here rather than shipped as an asset, so there is no binary in the
    repository and nothing to go missing. One blip for a moment, two rising
    blips for a Short-worthy one, so they can be told apart without looking.
    """
    name = "marker-short" if short_worthy else "marker"
    level = min(1.0, max(0.05, float(level)))
    # The volume is part of the name, so changing the setting makes a new file
    # instead of quietly reusing the old one.
    path = folder / f"{name}-v4-{int(round(level * 100))}.wav"
    if path.exists():
        return path
    folder.mkdir(parents=True, exist_ok=True)
    samples = bytearray(2 * int(SAMPLE_RATE * SILENCE_LEAD_SECONDS))
    for index, (frequency, seconds) in enumerate(TONES[name]):
        if index:
            samples += bytes(2 * int(SAMPLE_RATE * GAP_SECONDS))  # silence between blips
        frames = int(SAMPLE_RATE * seconds)
        for i in range(frames):
            # Fade in and out, so it is a soft click rather than a cut-off beep.
            fade = min(1.0, i / 300, (frames - i) / 300)
            value = level * fade * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE)
            samples += struct.pack("<h", int(value * 32767))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(bytes(samples))
    return path


def play(path: Path) -> None:
    """Play it without waiting for it to finish."""
    try:
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception as exc:  # noqa: BLE001  -- a silent click is not a failure
        log.warning("Couldn't play the confirmation sound: %s", exc)
