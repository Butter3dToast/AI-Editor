"""Measuring how a reference video is edited (spec 7.4, Phase 2G-1).

Each measurement is an estimate, which is why the profile has sliders:

* **Cuts**: PySceneDetect's AdaptiveDetector, the one used on recordings
  (analysis/scenes.py), then only the real edits: after an edit the whole
  picture is somewhere else, but after a game's shop, scoreboard or camera
  jump the still parts of the screen (the HUD) carry straight on. Measured on
  the creator's League recording: 70% of the still parts carried on across
  those (median), 20% across a real edit. Cuts per minute and the typical shot
  length.
* **Silence kept**: where someone is talking (the Silero voice detector that
  comes with faster-whisper, on the processor). The gaps between talking show
  how much dead air the editor left in: the long end of them (90th
  percentile) is about the most they allowed.
* **Zooms**: an editor's punch-in is the frame before, blown up. So each
  frame (6 a second) is compared with the one before blown up 1.03-1.5 times
  and lined up, and the other way round for a zoom back out: a match much
  closer than the plain difference is a zoom. A game's camera moving forward
  doesn't match, because the world shifts in perspective and the HUD stays
  put. Tested on 30 minutes of League, Wardogs and Dawnwalker gameplay: no
  zooms found; on a copy with six 1.25x punch-ins added: all six, at 1.25.
  (Matching points between frames with ORB was tried first: about 2 false
  zooms a minute on Wardogs.)
* **Meme sounds**: the PANNs sound model's whoosh, boing, air horn, ding and
  record-scratch classes jumping up. Booms and hits can't be told from a
  game's own sounds or the music: AI-Editor's own starter boom, mixed into a
  highlight, was heard as "drum", and sudden jumps in loudness came 5-18 a
  minute from plain gameplay. The meme sounds came up 0-0.3 a minute from
  plain gameplay (a Dawnwalker sword swing is a whoosh), so they're counted;
  booms and hits aren't.
* **Captions**: RapidOCR on a frame every few seconds. Text near the middle,
  big enough, mostly letters, and changing (a game's own text stays put)
  counts as a caption, but not on a screen full of text (a menu or
  scoreboard). On the creator's League highlight, the game's own text was
  2.5-3.6% of the picture high; burned-in captions are 4.5-6%. Captions: how
  often, how big, how high, how many words at once.
* **Opening teaser**: how long the first shot runs before the first cut,
  when that's within the first 25 seconds.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from ..config import Settings
from ..ffmpeg import _BACKGROUND, find_binary, probe, run_ffmpeg
from ..logging_setup import get_logger

log = get_logger(__name__)

# Longer references are measured over their first half hour: plenty to see a style.
MAX_SEC = 30 * 60

# --- Cuts ----------------------------------------------------------------------------
# A cut across which this share of the still parts of the picture carry on is
# a menu or camera jump, not an edit (see above).
CUT_CARRIES_ON = 0.4
STILL_LEVEL = 4            # grey levels: a pixel this steady is "still"...
SAME_LEVEL = 6             # ...and this close after the cut, "carried on"

# --- Zooms ---------------------------------------------------------------------------
ZOOM_FPS = 6
ZOOM_WIDTH = 320
ZOOM_SCALES = (1.03, 1.06, 1.1, 1.15, 1.2, 1.25, 1.3, 1.4, 1.5)
ZOOM_MATCH = 0.3           # blown up, it differs this much of the plain difference at most
ZOOM_MIN_SCALE = 1.1       # a zoom grows the picture this much at least (all at once or over steps)
ZOOM_MAX_SCALE = 1.6       # an editor's punch-in; more is the game's own camera (a scope, the wheel)
ZOOM_MAX_STEPS = 6         # and it's over within a second; a slow creep is the game's camera
ZOOM_GAP_SEC = 2.0         # one zoom, not two, for a punch-in and its settle
ZOOM_HOLD_SEC = 10.0       # a zoom back out this soon after a zoom in is the same zoom

# --- Sound effects ---------------------------------------------------------------------
SFX_GROUPS: dict[str, tuple[str, ...]] = {
    "whoosh": ("Whoosh, swoosh, swish", "Zing"),
    "cartoon": ("Boing", "Squish", "Sound effect", "Fart"),
    "horn": ("Air horn, truck horn",),
    "ding": ("Ding", "Chime", "Ding-dong", "Bell", "Cash register"),
    "scratch": ("Scratching (performance technique)",),
}
SFX_LEVEL = 0.25           # a group's probability jumping past this...
SFX_GAP_SEC = 2.0          # ...at least this long after its last one

# --- Captions ----------------------------------------------------------------------------
OCR_EVERY_SEC = 2.0
OCR_MAX_LOOKS = 240
OCR_HEIGHT = 360           # landscape; a portrait video is read 360 wide
CAPTION_MIDDLE = (0.2, 0.8)  # the box's centre, across the picture
CAPTION_MIN_HEIGHT = 0.04    # of the picture's height
STATIC_SHARE = 0.2           # the same text in this share of looks is the game's, not a caption
MENU_BOXES = 8               # this much text in the middle of a frame: a menu or scoreboard
MENU_TEXT_HEIGHT = 0.025     # (counting text at least this high, away from the edges, where
MENU_ROWS = (0.15, 0.8)      # a game's HUD sits: League's ability bar is full of numbers)

# --- Opening teaser -------------------------------------------------------------------------
HOOK_MIN_SEC = 2.0
HOOK_MAX_SEC = 25.0


@dataclass
class Measured:
    """One reference video, measured. None: couldn't tell (e.g. nobody talks)."""

    duration_sec: float
    measured_sec: float
    portrait: bool
    cuts_per_min: float
    shot_sec: float | None
    speech_share: float
    dead_air_sec: float | None
    zooms_per_min: float
    zoom_strength: float | None      # 0.2: pushes in to 1.2 times
    sfx_per_min: float                 # meme sounds only (see above)
    sfx_kinds: dict[str, int] = field(default_factory=dict)
    caption_share: float = 0.0       # of the looks while someone talks
    caption_size: float | None = None      # text height, share of the picture's height
    caption_position: float | None = None  # its bottom, up from the picture's bottom
    caption_words: float | None = None
    hook_sec: float | None = None
    # Where something was happening (zooms, meme sounds): where the AI looks first.
    moments: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Measured":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


# --- The sums, kept apart from reading the video so they can be tested -------------------


def shots(cuts: list[float], length: float) -> list[float]:
    """How long each shot runs, from the cuts between them."""
    edges = [0.0, *[c for c in sorted(cuts) if 0 < c < length], length]
    return [b - a for a, b in zip(edges, edges[1:]) if b - a > 0.05]


def carried_on(before2: np.ndarray, before: np.ndarray, after: np.ndarray) -> float:
    """The share of the picture's still parts (steady from ``before2`` to ``before``)
    that are the same in ``after``. 0.0 if hardly anything was still (frames as float32)."""
    still = np.abs(before - before2) < STILL_LEVEL
    if still.sum() < 200:
        return 0.0
    same = np.abs(after - before) < SAME_LEVEL
    return float(same[still].mean())


def edits(cuts: list[float], carried: list[float], fps: float) -> list[float]:
    """The cuts that are edits: those the still parts of the picture don't carry
    on across. ``carried[n]``: carried_on() for frame n (taken ``fps`` a second)."""
    out = []
    for c in cuts:
        n = int(np.ceil(c * fps - 1e-6))
        near = [carried[k] for k in (n, n + 1) if 0 <= k < len(carried)]
        if not near or min(near) < CUT_CARRIES_ON:
            out.append(c)
    return out


def gaps(speech: list[tuple[float, float]], length: float) -> list[float]:
    """The silences between stretches of talking (not before the first or after the last)."""
    out = []
    for (_, end), (start, _) in zip(speech, speech[1:]):
        if start - end > 0.25:
            out.append(start - end)
    return out


def dead_air(speech: list[tuple[float, float]], length: float) -> float | None:
    """About the longest silence the editor left between talking; None if hardly anyone talks."""
    talked = sum(b - a for a, b in speech)
    found = gaps(speech, length)
    if talked < 0.1 * length or len(found) < 5:
        return None
    return round(float(np.percentile(found, 90)), 1)


@dataclass
class ZoomStep:
    """One frame against the one before: the best blow-up each way and how well it matched."""

    grow_in: float     # the frame before, blown up this much, looks most like this one
    err_in: float
    grow_out: float    # this one, blown up, looks most like the frame before (a zoom out)
    err_out: float
    plain: float       # how different the two are as they are (or just shifted)

    def zoomed(self, way: str) -> float:
        """How far it zoomed ``way`` ("in"/"out"), 1.0 if it didn't."""
        grow, err = (self.grow_in, self.err_in) if way == "in" else (self.grow_out, self.err_out)
        return grow if grow > 1.0 and err <= ZOOM_MATCH * max(self.plain, 0.5) else 1.0


def zoom_events(steps: list[ZoomStep], fps: float) -> list[tuple[float, float]]:
    """Zooms: (time, how far: 0.25 is 1.25 times). A zoom can be all at once or
    over a few frames (a second at most); zooming back out after it is the same
    zoom, and a zoom out alone means one came in too gently to see. On the
    creator's League recording, the game's own camera zooming (the mouse wheel)
    crept in over several seconds, up to 4.7 times: not counted."""
    found: list[tuple[float, str, float]] = []
    for way in ("in", "out"):
        grown, start = 1.0, None
        for i, step in enumerate([*steps, None]):
            g = step.zoomed(way) if step is not None else 1.0
            if g > 1.0:
                grown, start = grown * g, i if start is None else start
                continue
            if (start is not None and ZOOM_MIN_SCALE <= grown <= ZOOM_MAX_SCALE
                    and i - start <= ZOOM_MAX_STEPS):
                found.append(((start + 1) / fps, way, grown))
            grown, start = 1.0, None
    events: list[tuple[float, float]] = []
    last_in = None
    for t, way, grown in sorted(found):
        if events and t - events[-1][0] < ZOOM_GAP_SEC:
            continue
        if way == "out" and last_in is not None and t - last_in <= ZOOM_HOLD_SEC:
            last_in = None
            continue
        events.append((round(t, 2), round(grown - 1.0, 2)))
        last_in = t if way == "in" else None
    return events


def sfx_events(per_second: dict[str, np.ndarray]) -> list[tuple[float, str]]:
    """(second, kind) each time a sound effect group jumps past SFX_LEVEL."""
    found: list[tuple[float, str]] = []
    for kind, values in per_second.items():
        last = -SFX_GAP_SEC
        above = False
        for t, p in enumerate(values):
            if p >= SFX_LEVEL and not above and t - last >= SFX_GAP_SEC:
                found.append((float(t), kind))
                last = t
            above = p >= SFX_LEVEL
    return sorted(found)


@dataclass
class TextBox:
    t: float
    text: str
    x: float        # centre, share of the width
    top: float      # share of the height, from the top
    bottom: float
    height: float


def captions(looks: list[list[TextBox]], talking: Callable[[float], bool]) -> dict:
    """Which text is captions, and what they look like. ``looks``: the text found in
    each frame read (one list per frame, maybe empty)."""
    if not looks:
        return {"caption_share": 0.0}
    seen = Counter(b.text.lower() for look in looks for b in {x.text.lower(): x for x in look}.values())
    static = {text for text, n in seen.items() if n >= max(3, STATIC_SHARE * len(looks))}

    def is_caption(b: TextBox) -> bool:
        letters = sum(ch.isalpha() for ch in b.text)
        return (CAPTION_MIDDLE[0] <= b.x <= CAPTION_MIDDLE[1] and b.height >= CAPTION_MIN_HEIGHT
                and letters >= 0.5 * len(b.text.replace(" ", ""))
                and any(sum(ch.isalpha() for ch in w) >= 3 for w in b.text.split())
                and b.text.lower() not in static)

    def is_menu(look: list[TextBox]) -> bool:
        return sum(1 for b in look if CAPTION_MIDDLE[0] <= b.x <= CAPTION_MIDDLE[1]
                   and MENU_ROWS[0] <= (b.top + b.bottom) / 2 <= MENU_ROWS[1]
                   and b.height >= MENU_TEXT_HEIGHT) >= MENU_BOXES

    found = [[] if is_menu(look) else [b for b in look if is_caption(b)] for look in looks]
    with_talk = [i for i, look in enumerate(looks) if talking(_time(look, i, looks))]
    pool = with_talk if len(with_talk) >= 5 else list(range(len(looks)))
    share = sum(1 for i in pool if found[i]) / len(pool)
    boxes = [max(f, key=lambda b: b.height) for f in found if f]
    if len(boxes) < 3:
        return {"caption_share": round(share, 2)}
    return {"caption_share": round(share, 2),
            "caption_size": round(float(np.median([b.height for b in boxes])), 3),
            "caption_position": round(float(np.median([1.0 - b.bottom for b in boxes])), 3),
            "caption_words": round(float(np.median([len(b.text.split()) for b in boxes])), 1)}


def _time(look: list[TextBox], i: int, looks: list[list[TextBox]]) -> float:
    return look[0].t if look else i * OCR_EVERY_SEC


def hook(cuts: list[float]) -> float | None:
    """The opening teaser's length: the first cut between 2 and 25 seconds in."""
    first = next((c for c in sorted(cuts) if c >= HOOK_MIN_SEC), None)
    return round(first, 1) if first is not None and first <= HOOK_MAX_SEC else None


# --- Reading the video ------------------------------------------------------------------


def measure(settings: Settings, video: Path, work: Path,
            on_progress: Callable[[str, float], None] | None = None) -> Measured:
    """Everything above, for one reference video. ``work``: a folder for its
    sound files (deleted by the caller). Progress: (step, 0-1)."""
    from ..analysis.scenes import detect_scene_cuts

    def step(label: str) -> Callable[[float], None]:
        return (lambda f: on_progress(label, f)) if on_progress else (lambda f: None)

    info = probe(video)
    duration = float(info.duration_sec or 0.0)
    length = min(duration, MAX_SEC)
    width, height = info.width or 16, info.height or 9
    portrait = height > width
    work.mkdir(parents=True, exist_ok=True)

    found = [c for c in detect_scene_cuts(video, length, on_progress=step("Finding the cuts"))["cuts"]
             if c < length]
    speech = _speech(video, work, length, step("Listening for talking"))
    sfx = _sfx(settings, video, work, length, step("Listening for sound effects"))
    zooms, carried = _picture(video, length, (width, height), step("Looking for zooms"))
    cuts = edits(found, carried, ZOOM_FPS)
    # An instant punch-in can look like a cut: it's a zoom, not a new shot.
    cuts = [c for c in cuts if not any(abs(c - t) <= 1.0 / ZOOM_FPS + 0.05 for t, _ in zooms)]
    looks = _read_text(video, length, (width, height), step("Reading captions"))

    def talking(t: float) -> bool:
        return any(a - 0.5 <= t <= b + 0.5 for a, b in speech)

    minutes = max(length / 60.0, 1e-6)
    lengths = shots(cuts, length)
    return Measured(
        duration_sec=round(duration, 1), measured_sec=round(length, 1), portrait=portrait,
        cuts_per_min=round(len(cuts) / minutes, 1),
        shot_sec=round(float(np.median(lengths)), 1) if lengths else None,
        speech_share=round(sum(b - a for a, b in speech) / max(length, 1e-6), 2),
        dead_air_sec=dead_air(speech, length),
        zooms_per_min=round(len(zooms) / minutes, 1),
        zoom_strength=round(float(np.median([s for _, s in zooms])), 2) if zooms else None,
        sfx_per_min=round(len(sfx) / minutes, 1),
        sfx_kinds=dict(Counter(kind for _, kind in sfx).most_common()),
        hook_sec=hook(cuts),
        moments=sorted({round(t, 1) for t in [*(t for t, _ in zooms), *(t for t, _ in sfx)]})[:200],
        **captions(looks, talking),
    )


def _speech(video: Path, work: Path, length: float,
            on_progress: Callable[[float], None]) -> list[tuple[float, float]]:
    """Stretches of talking (seconds)."""
    import soundfile as sf
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    wav = work / "speech16k.wav"
    run_ffmpeg(["-i", str(video), "-t", f"{length:.2f}", "-vn", "-ac", "1", "-ar", "16000",
                str(wav)], duration_sec=length, on_progress=lambda f: on_progress(f * 0.5),
               what="reading a reference's sound")
    audio, _ = sf.read(str(wav), dtype="float32")
    found = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=250))
    on_progress(1.0)
    return [(s["start"] / 16000, s["end"] / 16000) for s in found]


def _sfx(settings: Settings, video: Path, work: Path, length: float,
         on_progress: Callable[[float], None]) -> list[tuple[float, str]]:
    from ..analysis.panns_cnn14 import SAMPLE_RATE
    from ..analysis.sound_events import _score_file
    from ..models import audioset_labels, sound_model

    wav = work / "sound32k.wav"
    run_ffmpeg(["-i", str(video), "-t", f"{length:.2f}", "-vn", "-ac", "1", "-ar",
                str(SAMPLE_RATE), str(wav)], duration_sec=length,
               on_progress=lambda f: on_progress(f * 0.3), what="reading a reference's sound")
    position = {label: i for i, label in enumerate(audioset_labels(settings))}
    columns = {kind: [position[n] for n in names if n in position]
               for kind, names in SFX_GROUPS.items()}
    columns = {k: v for k, v in columns.items() if v}
    seconds = max(1, int(length))
    with sound_model(settings) as (model, device):
        scores = _score_file(model, device, wav, columns, tuple(columns), seconds,
                             settings.analysis.event_window_sec,
                             lambda f: on_progress(0.3 + 0.7 * f))
    return sfx_events(scores)


def _frames(video: Path, length: float, size: tuple[int, int], fps: float, gray: bool):
    """Frames from ``video`` at ``fps``, ``size`` (w, h), as numpy arrays."""
    w, h = size
    proc = subprocess.Popen(
        [str(find_binary("ffmpeg")), "-v", "error", "-t", f"{length:.2f}", "-i", str(video),
         "-vf", f"fps={fps:g},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt",
         "gray" if gray else "rgb24", "-"],
        stdout=subprocess.PIPE, creationflags=_BACKGROUND)
    size_bytes = w * h * (1 if gray else 3)
    try:
        while True:
            raw = proc.stdout.read(size_bytes)
            if len(raw) < size_bytes:
                break
            yield np.frombuffer(raw, np.uint8).reshape((h, w) if gray else (h, w, 3))
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def _picture(video: Path, length: float, size: tuple[int, int],
             on_progress: Callable[[float], None]) -> tuple[list[tuple[float, float]], list[float]]:
    """Zooms, and for each frame how much of the still picture carried on into it."""
    w = ZOOM_WIDTH
    h = _even(ZOOM_WIDTH * size[1] / size[0])
    steps: list[ZoomStep] = []
    carried: list[float] = []
    kept: list[np.ndarray] = []
    total = max(1, int(length * ZOOM_FPS))
    for n, frame in enumerate(_frames(video, length, (w, h), ZOOM_FPS, gray=True)):
        frame = frame.astype(np.float32)
        if kept:
            steps.append(zoom_step(kept[-1], frame))
        carried.append(carried_on(kept[-2], kept[-1], frame) if len(kept) >= 2 else 1.0)
        kept = [*kept[-1:], frame]
        if n % 60 == 0:
            on_progress(min(1.0, n / total))
    on_progress(1.0)
    return zoom_events(steps, ZOOM_FPS), carried


def _grown(frame: np.ndarray, scale: float, shift: tuple[float, float] = (0.0, 0.0)) -> np.ndarray:
    """``frame`` blown up ``scale`` times about its middle, moved by ``shift``."""
    import cv2

    h, w = frame.shape
    m = np.float32([[scale, 0, (1 - scale) * w / 2 + shift[0]],
                    [0, scale, (1 - scale) * h / 2 + shift[1]]])
    return cv2.warpAffine(frame, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def _best_growth(a: np.ndarray, b: np.ndarray, inner) -> tuple[float, float]:
    """The blow-up of ``a`` (lined up) most like ``b``, and how different it still is."""
    import cv2

    h, w = a.shape
    best = (1.0, float("inf"))
    for scale in ZOOM_SCALES:
        grown = _grown(a, scale)
        (dx, dy), _ = cv2.phaseCorrelate(grown, b)
        if abs(dx) > w * 0.15 or abs(dy) > h * 0.15:   # off to one side: not a punch-in
            continue
        err = float(np.median(np.abs(b - _grown(a, scale, (dx, dy)))[inner]))
        if err < best[1]:
            best = (scale, err)
    return best


def zoom_step(a: np.ndarray, b: np.ndarray) -> ZoomStep:
    """Frame ``b`` against the frame before it, ``a`` (grey, float32). The plain
    difference is after the best shift, so a camera pan isn't taken for a zoom."""
    import cv2

    h, w = a.shape
    inner = (slice(int(h * 0.05), int(h * 0.95)), slice(int(w * 0.05), int(w * 0.95)))
    plain = float(np.median(np.abs(b - a)[inner]))
    (dx, dy), _ = cv2.phaseCorrelate(a, b)
    if abs(dx) <= w * 0.15 and abs(dy) <= h * 0.15:
        plain = min(plain, float(np.median(np.abs(b - _grown(a, 1.0, (dx, dy)))[inner])))
    grow_in, err_in = _best_growth(a, b, inner)
    grow_out, err_out = _best_growth(b, a, inner)
    return ZoomStep(grow_in, err_in, grow_out, err_out, plain)


def _read_text(video: Path, length: float, size: tuple[int, int],
               on_progress: Callable[[float], None]) -> list[list[TextBox]]:
    from ..analysis.quests import _reader

    portrait = size[1] > size[0]
    if portrait:
        w, h = OCR_HEIGHT, _even(OCR_HEIGHT * size[1] / size[0])
    else:
        w, h = _even(OCR_HEIGHT * size[0] / size[1]), OCR_HEIGHT
    every = max(OCR_EVERY_SEC, length / OCR_MAX_LOOKS)
    engine = _reader()
    looks: list[list[TextBox]] = []
    total = max(1, int(length / every))
    for n, frame in enumerate(_frames(video, length, (w, h), 1.0 / every, gray=False)):
        t = n * every
        result = engine(frame)
        found = []
        for box, text in zip(result.boxes if result.txts else [], result.txts or []):
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            found.append(TextBox(t, str(text).strip(), (min(xs) + max(xs)) / 2 / w,
                                 min(ys) / h, max(ys) / h, (max(ys) - min(ys)) / h))
        looks.append(found)
        on_progress(min(1.0, (n + 1) / total))
    return looks
