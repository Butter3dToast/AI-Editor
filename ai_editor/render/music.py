"""The music from your stream in finished videos, kept out of your voice's way.

The creator plays DMCA-free music through Spotify on stream and wants it in
every video, as viewers heard it (2026-10-10) -- only lowered where it would
cover someone talking.

**Where it comes from.** The finished video's sound is rebuilt from the
separate mic, game and Discord tracks (render/audio.py), so the music has to
be added back as a layer of its own:

* A **music track** (OBS track 5, manual 7.3) when the recording has one.
* Otherwise the **mixed track minus everything else**: OBS adds the separate
  tracks into the mixed one sample for sample, so taking them away leaves
  just the music. On the 7 Oct stream what was left was the song, about
  17 dB under the creator's voice, and nothing of the voice (the creator
  listened: "sounds good"). FFmpeg can't subtract in its mixer (negative
  amix weights did nothing), so the tracks taken away are turned upside
  down (volume=-1) and added.

**Out of the way of talking.** While the creator or a Discord friend talks,
the music is kept at least KEEP_UNDER_DB under them, lowered only as much
as that needs, and only there. Mostly it plays exactly as on stream.

**At cuts.** Each clip of a highlight video comes from a different point in
the song, so the music alone fades in and out over MUSIC_FADE_SEC at a cut,
while voices and game still cut cleanly. Where one piece carries straight
on from the last, it doesn't.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

KEEP_UNDER_DB = 15.0        # music this far under talking, at least
MAX_LOWER_DB = 12.0         # and never lowered by more than this
# Someone talking: louder than this, for at least MIN_TALK_SEC in any second.
# The creator talks at about -26 dB (-40 at the quiet end); a 50 ms blip of
# the mic's noise gate opening, with nothing said, once dipped the music 16 dB.
TALKING_DB = -40.0
MIN_TALK_SEC = 0.3
WINDOW_SEC = 0.05
HOLD_SEC = 0.4              # between words: stay lowered, don't bob up and down
LOWER_SEC = 0.15            # how fast it goes down...
RAISE_SEC = 0.5             # ...and comes back up
MIN_CHANGE_DB = 1.0         # smaller than this isn't worth doing
MUSIC_FADE_SEC = 0.3
VOICE_ROLES = ("mic", "voice_chat")
PART_ROLES = ("mic", "game", "voice_chat")


@dataclass
class MusicSource:
    """Where a recording's music comes from, as FFmpeg streams (indexes)."""
    added: list[int]                 # the music track, or the mixed one
    taken_away: list[int] = field(default_factory=list)   # the other tracks, from the mix
    # The extracted copies, for working out where to lower it.
    added_paths: list[Path] = field(default_factory=list)
    taken_away_paths: list[Path] = field(default_factory=list)
    voice_paths: list[Path] = field(default_factory=list)

    @property
    def own_track(self) -> bool:
        return not self.taken_away


def source_of(conn: sqlite3.Connection, recording_id: int, parts: list[int]) -> MusicSource | None:
    """The music as its own layer, for a recording rebuilt from separate tracks.

    ``parts``: the separate tracks really in the mix (not copies), whatever
    the video uses: Discord left out of a video is still in the mixed track.
    None when there's no mixed track to take it from."""
    rows = conn.execute("SELECT stream_index, role, extracted_path FROM audio_tracks WHERE "
                        "recording_id = ? ORDER BY stream_index", (recording_id,)).fetchall()
    path = {r[0]: Path(r[2]) if r[2] else None for r in rows}
    by_role = {r[1]: r[0] for r in rows}
    voices = [path[by_role[role]] for role in VOICE_ROLES
              if role in by_role and by_role[role] in parts and path[by_role[role]]]
    if "music" in by_role:
        index = by_role["music"]
        return MusicSource([index], [], [p for p in [path[index]] if p], [], voices)
    if "mixed" not in by_role:
        return None
    mixed = by_role["mixed"]
    return MusicSource([mixed], list(parts), [p for p in [path[mixed]] if p],
                       [path[i] for i in parts if path.get(i)], voices)


# --- Where to lower it --------------------------------------------------------------------


def _read(path: Path, start: float, end: float) -> tuple[np.ndarray, int] | None:
    import soundfile as sf

    try:
        with sf.SoundFile(str(path)) as f:
            rate = f.samplerate
            f.seek(min(int(start * rate), max(0, f.frames - 1)))
            return f.read(int(max(0.0, end - start) * rate), dtype="float32", always_2d=True), rate
    except (OSError, RuntimeError):
        return None


def _levels(x: np.ndarray, rate: int) -> np.ndarray:
    step = max(1, int(rate * WINDOW_SEC))
    frames = len(x) // step
    mono = x[:frames * step].mean(axis=1) if x.ndim == 2 else x[:frames * step]
    rms = np.sqrt(np.mean(mono.reshape(frames, step) ** 2, axis=1))
    return 20 * np.log10(rms + 1e-9)


def levels(source: MusicSource, start: float, end: float) -> tuple[np.ndarray, np.ndarray] | None:
    """(music, voices) loudness in dB per WINDOW_SEC over a stretch. None when
    the extracted tracks are gone (Storage can free them): then nothing is lowered."""
    if not source.added_paths or len(source.taken_away_paths) != len(source.taken_away):
        return None
    reads = [_read(p, start, end) for p in source.added_paths + source.taken_away_paths]
    if any(r is None for r in reads):
        return None
    n = min(len(x) for x, _ in reads)
    rate = reads[0][1]
    music = sum(x[:n] for x, _ in reads[:len(source.added_paths)]) - sum(
        (x[:n] for x, _ in reads[len(source.added_paths):]), np.zeros_like(reads[0][0][:n]))
    voice = np.zeros_like(music)
    for p in source.voice_paths:
        r = _read(p, start, end)
        if r is not None:
            m = min(len(voice), len(r[0]))
            voice[:m] += r[0][:m]
    return _levels(music, rate), _levels(voice, rate)


def _around(x: np.ndarray, width: int) -> np.ndarray:
    """Each window's total over the ``width`` windows around it, the same length
    as ``x`` even when it's shorter than ``width`` (a slide's 0.8 s ends)."""
    full = np.convolve(x, np.ones(width), mode="full")
    return full[width // 2:width // 2 + len(x)]


def lowering(music_db: np.ndarray, voice_db: np.ndarray) -> np.ndarray:
    """How far to lower the music in each window (dB, 0 or less)."""
    loud = (voice_db > TALKING_DB).astype(float)
    second = max(1, int(round(1.0 / WINDOW_SEC)))
    talking = (loud > 0) & (_around(loud, second) * WINDOW_SEC
                            >= MIN_TALK_SEC)
    hold = max(1, int(round(HOLD_SEC / WINDOW_SEC)))
    held = _around(talking.astype(float), hold) > 0
    # The voice level to stay under: the loudness of the talking around it,
    # not every dip between syllables.
    voice = np.where(talking, voice_db, -np.inf)
    around = np.array([voice[max(0, i - hold):i + hold + 1].max() for i in range(len(voice))])
    need = np.where(held & np.isfinite(around),
                    np.clip((around - KEEP_UNDER_DB) - music_db, -MAX_LOWER_DB, 0.0), 0.0)
    return np.where(need <= -MIN_CHANGE_DB, need, 0.0)


def stretches(cut: np.ndarray) -> list[tuple[float, float, float]]:
    """(start, end, dB) stretches to lower, from the per-window amounts."""
    found = []
    i = 0
    while i < len(cut):
        if cut[i] >= 0:
            i += 1
            continue
        j = i
        while j < len(cut) and cut[j] < 0:
            j += 1
        found.append((i * WINDOW_SEC, j * WINDOW_SEC, float(cut[i:j].min())))
        i = j
    # Close together: one stretch, so it doesn't bob up between sentences.
    merged: list[tuple[float, float, float]] = []
    for a, b, db in found:
        if merged and a - merged[-1][1] < RAISE_SEC + LOWER_SEC:
            pa, _, pdb = merged[-1]
            merged[-1] = (pa, b, min(pdb, db))
        else:
            merged.append((a, b, db))
    return merged


def volume_text(lowered: list[tuple[float, float, float]]) -> str | None:
    """An FFmpeg volume filter lowering those stretches, easing in and out."""
    if not lowered:
        return None
    terms = []
    for a, b, db in lowered:
        depth = 1 - 10 ** (db / 20)
        down, up = max(0.0, a - LOWER_SEC), b + RAISE_SEC
        # 0 before, ramps to 1 by a, holds to b, ramps back to 0 by b + RAISE_SEC.
        shape = (f"clip(min((t-{down:.3f})/{LOWER_SEC},({up:.3f}-t)/{RAISE_SEC}),0,1)")
        terms.append(f"{depth:.4f}*{shape}")
    deepest = terms[0]
    for term in terms[1:]:
        deepest = f"max({deepest},{term})"
    return f"volume='1-{deepest}':eval=frame"


# --- Into the mix ------------------------------------------------------------------------


def graph(source: MusicSource, lowered: list[tuple[float, float, float]], length: float,
          rate: int, *, fade_in: bool, fade_out: bool, input: int = 0,
          skip: float = 0.0) -> tuple[list[str], str]:
    """Graph pieces making the music layer from the segment's input (``input``), and its
    label. ``skip``: start this far into it -- after a slow-motion replay, where
    the music carried on while the clip waited (render/replay.py)."""
    fmt = f"aresample={rate},aformat=sample_fmts=fltp:channel_layouts=stereo"
    if skip > 0:
        fmt = f"atrim=start={skip:.4f},asetpts=PTS-STARTPTS,{fmt}"
    pieces = [f"[{input}:{i}]{fmt}[mus_add{n}]" for n, i in enumerate(source.added)]
    pieces += [f"[{input}:{i}]{fmt},volume=-1[mus_sub{n}]"
               for n, i in enumerate(source.taken_away)]
    inputs = "".join(f"[mus_add{n}]" for n in range(len(source.added))) + "".join(
        f"[mus_sub{n}]" for n in range(len(source.taken_away)))
    count = len(source.added) + len(source.taken_away)
    chain = [f"amix=inputs={count}:normalize=0:duration=first"] if count > 1 else ["anull"]
    shaped = volume_text(lowered)
    if shaped:
        chain.append(shaped)
    fade = min(MUSIC_FADE_SEC, length / 4)
    if fade_in:
        chain.append(f"afade=t=in:d={fade:.3f}")
    if fade_out:
        chain.append(f"afade=t=out:st={length - fade:.4f}:d={fade:.3f}")
    pieces.append(f"{inputs}{','.join(chain)}[music]")
    return pieces, "[music]"
