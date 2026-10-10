"""Sound effects: a boom or a hit on a big moment.

**Which sound.** Yours first: put files in ``assets/sfx/boom`` or
``assets/sfx/hit`` (or anywhere in ``assets/sfx`` with the word in the name,
like ``boom_01.wav``). Until there are any, AI-Editor uses a starter
set it makes itself, from scratch, the way the Companion's click is made:
no one else's sound, so no copyright question. With several, each moment
gets one picked by when it happens, so the same video always sounds the same.

**How loud.** As loud as the moment it's on, give or take
effects.sfx_volume_db: a boom that suits a teamfight would drown a quiet
chat. The moment, not the clip: on the creator's League Short the clip was
mostly quiet game sound (its loud parts -45 dB) around one shout at -15 dB,
and an effect matched to the clip was lost under the shout. But never far
under the clip's loudest moment either (FLOOR_UNDER_PEAK_DB): that stream's
game sound sat 20 dB under the creator's voice, and a boom matched to it was
barely there. The finished video's loudness is then set as a whole, as before.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import Settings
from . import Effect

NAMES = ("boom", "hit")
AUDIO_TYPES = {".wav", ".mp3", ".ogg", ".flac"}
RATE = 48000
STARTER_VERSION = 1
PEAK_DB = -1.0
LEVEL_WINDOW_SEC = 0.05
MOMENT_SEC = (-0.25, 0.75)       # "the moment": around where the effect starts
UNKNOWN_LEVEL_DB = -20.0         # when the recording's sound can't be read
FLOOR_UNDER_PEAK_DB = 12.0       # never quieter than this under the clip's loudest moment


# --- AI-Editor's own starter set -------------------------------------------------------


def _decay(t: np.ndarray, seconds: float) -> np.ndarray:
    return np.exp(-t / seconds)


def _attack(t: np.ndarray, seconds: float = 0.004) -> np.ndarray:
    return np.clip(t / seconds, 0.0, 1.0)


def _sweep(t: np.ndarray, start_hz: float, end_hz: float, over: float) -> np.ndarray:
    """A tone sliding from one pitch to another (exponentially), as its phase."""
    k = np.log(end_hz / start_hz) / over
    return 2 * np.pi * start_hz * (np.expm1(k * t) / k)


def _lowpass(x: np.ndarray, hz: float) -> np.ndarray:
    from scipy.signal import butter, sosfilt

    return sosfilt(butter(2, hz, "lowpass", fs=RATE, output="sos"), x)


def _bandpass(x: np.ndarray, low: float, high: float) -> np.ndarray:
    from scipy.signal import butter, sosfilt

    return sosfilt(butter(2, [low, high], "bandpass", fs=RATE, output="sos"), x)


def make_boom(rng: np.random.Generator) -> np.ndarray:
    """A deep thud that rumbles away: a falling low tone, a burst of dark noise."""
    t = np.arange(int(1.2 * RATE)) / RATE
    body = np.sin(_sweep(t, 95.0, 32.0, 1.2)) * _decay(t, 0.38)
    crack = _lowpass(rng.standard_normal(t.size), 500.0) * _decay(t, 0.07) * 1.6
    snap = _bandpass(rng.standard_normal(t.size), 1500.0, 6000.0) * _decay(t, 0.006) * 0.4
    return np.tanh(1.8 * (body + crack + snap) * _attack(t))


def make_hit(rng: np.random.Generator) -> np.ndarray:
    """A short punchy impact."""
    t = np.arange(int(0.45 * RATE)) / RATE
    body = np.sin(_sweep(t, 170.0, 55.0, 0.2)) * _decay(t, 0.09)
    smack = _bandpass(rng.standard_normal(t.size), 900.0, 4500.0) * _decay(t, 0.025) * 0.9
    return np.tanh(2.2 * (body + smack) * _attack(t, 0.002))


MAKERS = {"boom": make_boom, "hit": make_hit}


def starter(folder: Path, name: str) -> Path:
    """AI-Editor's own sound, made once and kept in the cache."""
    import soundfile as sf

    path = folder / f"{name}-v{STARTER_VERSION}.wav"
    if path.is_file():
        return path
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(sum(map(ord, name)))
    mono = MAKERS[name](rng)
    stereo = np.column_stack([mono, mono])
    stereo = stereo / (np.max(np.abs(stereo)) + 1e-9) * 10 ** (PEAK_DB / 20)
    temporary = path.with_suffix(".tmp.wav")
    sf.write(str(temporary), stereo.astype(np.float32), RATE, subtype="PCM_16")
    temporary.replace(path)
    return path


def starter_folder(settings: Settings) -> Path:
    return settings.folders.cache / "effects"


# --- Choosing --------------------------------------------------------------------------


def yours(settings: Settings, name: str) -> list[Path]:
    """The creator's own sounds of this kind, in a steady order."""
    root = settings.folders.assets / "sfx"
    if not root.is_dir():
        return []
    found = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_TYPES
             and (p.parent.name.lower() == name or name in p.stem.lower())]
    return sorted(set(found), key=lambda p: str(p).lower())


def choose(settings: Settings, name: str, key: str) -> Path:
    """One of your sounds of this kind, else AI-Editor's own. Always the same one for ``key``."""
    own = yours(settings, name)
    if not own:
        return starter(starter_folder(settings), name)
    pick = int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16) % len(own)
    return own[pick]


# --- How loud ---------------------------------------------------------------------------


def _window_db(x: np.ndarray, rate: int) -> np.ndarray:
    step = max(1, int(rate * LEVEL_WINDOW_SEC))
    frames = len(x) // step
    if frames == 0:
        return np.array([-120.0])
    rms = np.sqrt(np.mean(x[:frames * step].reshape(frames, step) ** 2, axis=1))
    return 20 * np.log10(rms + 1e-9)


def loudest_db(path: Path) -> float:
    """A sound effect's loudest moment (dB): what's matched to the clip."""
    import soundfile as sf

    x, rate = sf.read(str(path), dtype="float32", always_2d=True)
    return float(_window_db(x.mean(axis=1), rate).max())


def tracks(conn: sqlite3.Connection, recording_id: int,
           streams: list[int] | None = None) -> list[Path]:
    """The extracted sound of the tracks a video is made from: ``streams`` (the
    render's choice), or else the mixed track, as the stream heard it (what
    the preview copies carry). The OBS mixed track can be far quieter than
    the separate ones added together: 20+ dB on the 3 Oct League stream."""
    rows = conn.execute("SELECT stream_index, role, extracted_path FROM audio_tracks WHERE "
                        "recording_id = ? AND extracted_path IS NOT NULL ORDER BY stream_index",
                        (recording_id,)).fetchall()
    if streams is not None:
        chosen = [r for r in rows if r[0] in streams]
    else:
        chosen = [r for r in rows if r[1] == "mixed"] or rows[:1]
    return [Path(r[2]) for r in chosen if Path(r[2]).is_file()]


def _read_db(track: Path, start: float, end: float) -> np.ndarray | None:
    import soundfile as sf

    try:
        with sf.SoundFile(str(track)) as f:
            rate = f.samplerate
            f.seek(min(int(start * rate), max(0, f.frames - 1)))
            x = f.read(int(max(0.1, end - start) * rate), dtype="float32", always_2d=True)
    except (OSError, RuntimeError):
        return None
    return _window_db(x.mean(axis=1), rate)


def loudest_between(sources: list[Path], start: float, end: float) -> float:
    """The loudest the video's sound gets in a stretch (dB): the tracks added
    together, as the render mixes them."""
    levels = [lv for lv in (_read_db(p, start, end) for p in sources) if lv is not None]
    if not levels:
        return UNKNOWN_LEVEL_DB
    n = min(len(lv) for lv in levels)
    power = sum(10 ** (lv[:n] / 10) for lv in levels)
    return float(10 * np.log10(power.max() + 1e-12))


# --- Into the mix ------------------------------------------------------------------------


@dataclass(frozen=True)
class Placed:
    path: Path
    at: float        # seconds into the segment
    gain_db: float
    skip: float = 0.0   # start this far into the sound (one carrying on into the next piece)


def place(settings: Settings, effects: list[Effect], seg_in: float, seg_out: float,
          sources: list[Path], key: str) -> list[Placed]:
    """The segment's sound effects: which file, when, how loud. ``sources``:
    the recording's tracks the video's sound is made from (tracks())."""
    out = []
    if not any(e.kind == "sfx" for e in effects):
        return out
    clip_peak = loudest_between(sources, seg_in, seg_out)
    loudness: dict[Path, float] = {}
    for e in effects:
        if e.kind != "sfx" or not e.sound:
            continue
        path = choose(settings, e.sound, f"{key}:{e.at:.2f}")
        if path not in loudness:
            loudness[path] = loudest_db(path)
        moment = loudest_between(sources, max(0.0, e.at + MOMENT_SEC[0]), e.at + MOMENT_SEC[1])
        level = max(moment, clip_peak - FLOOR_UNDER_PEAK_DB)
        gain = level + settings.effects.sfx_volume_db - loudness[path]
        out.append(Placed(path, max(0.0, e.within(seg_in)), round(gain, 2)))
    return out


def _seconds(path: Path, known: dict[Path, float] = {}) -> float:  # noqa: B006 -- a cache
    import soundfile as sf

    if path not in known:
        known[path] = sf.info(str(path)).duration
    return known[path]


def within_piece(placed: list[Placed], offset: float, length: float) -> list[Placed]:
    """A clip's sound effects for one piece of it, starting ``offset`` into the
    clip: those heard during it, one already playing carrying on where it was."""
    out = []
    for p in placed:
        start = p.at - offset
        if start >= length or start + _seconds(p.path) - p.skip <= 0:
            continue
        out.append(Placed(p.path, max(0.0, start), p.gain_db, p.skip + max(0.0, -start)))
    return out


def input_args(placed: list[Placed]) -> list[str]:
    return [arg for p in placed for arg in ("-i", str(p.path))]


def chains(placed: list[Placed], first_input: int, rate: int) -> tuple[list[str], list[str]]:
    """Graph pieces for each sound (inputs from ``first_input`` on), and their labels."""
    pieces, labels = [], []
    for n, p in enumerate(placed):
        label = f"sfx{n}"
        delay = int(round(p.at * 1000))
        trim = f"atrim=start={p.skip:.4f},asetpts=PTS-STARTPTS," if p.skip > 0 else ""
        pieces.append(f"[{first_input + n}:a:0]aresample={rate},"
                      f"aformat=sample_fmts=fltp:channel_layouts=stereo,{trim}"
                      f"volume={p.gain_db:.2f}dB,adelay={delay}:all=1[{label}]")
        labels.append(f"[{label}]")
    return pieces, labels
