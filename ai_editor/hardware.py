"""Can this PC do the job? Checked before every job starts (Phase 4A).

AI-Editor runs on the creator's desktop and, once packaged, on other PCs too.
Rather than a job failing deep inside FFmpeg or CUDA, each job is checked
first, in plain words:

* **Stopped before it starts** only when it can't work: FFmpeg missing, no
  NVIDIA graphics card for analysis, or too little free space.
* **"This will be slower", and on it goes** when it works but slowly: a
  graphics card with less memory than the local AI needs, or no NVIDIA video
  encoder. The creator's choice (31 Oct): keep the same AI everywhere, for
  its sharpness, rather than offer a smaller one.

Everything here only reads: nvidia-smi's card name and memory, FFmpeg's
encoder list, Ollama's model list and the drive's free space.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .logging_setup import get_logger

log = get_logger(__name__)

MIN_FREE_GB = 5.0          # an import or a render needs room to write
AI_EXTRA_GB = 1.0          # the AI's working memory on top of its file size


@dataclass(frozen=True)
class Card:
    name: str
    memory_gb: float


def card() -> Card | None:
    """The NVIDIA graphics card, from nvidia-smi. None without one."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        out = subprocess.run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        name, memory = out.strip().splitlines()[0].rsplit(",", 1)
        return Card(name.strip(), float(memory) / 1024)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _has_ffmpeg() -> bool:
    from .errors import FFmpegNotFound
    from .ffmpeg import find_binary

    try:
        find_binary("ffmpeg")
        return True
    except FFmpegNotFound:
        return False


def _free_gb(folder: Path) -> float | None:
    for path in (folder, *folder.parents):
        if path.exists():
            return shutil.disk_usage(path).free / 1e9
    return None


@dataclass(frozen=True)
class Needs:
    ffmpeg: bool = False
    gpu: bool = False            # CUDA work: transcription, sound events
    ai: bool = False             # the local AI
    encoder: bool = False        # video encoding (falls back to the processor)
    space: str | None = None     # "cache" or "output": where it writes


# What each kind of job uses, by the start of its key in the Jobs list.
NEEDS = {
    "import": Needs(ffmpeg=True, encoder=True, space="cache"),
    "twitch": Needs(ffmpeg=True, encoder=True, space="cache"),
    "analyse": Needs(ffmpeg=True, gpu=True, ai=True),
    "rate": Needs(ai=True),
    "make": Needs(ffmpeg=True),
    "preview": Needs(ffmpeg=True, encoder=True, space="output"),
    "render": Needs(ffmpeg=True, encoder=True, space="output"),
    "publish": Needs(ffmpeg=True, ai=True),
    "prompts": Needs(ai=True),
    "style": Needs(ffmpeg=True, ai=True, space="cache"),
    "overnight": Needs(ffmpeg=True, gpu=True, ai=True, encoder=True, space="cache"),
}
WITH_ANALYSIS = Needs(ffmpeg=True, gpu=True, ai=True, encoder=True, space="cache")


def needs_for(key: str, title: str = "") -> Needs:
    kind = key.split(":", 1)[0]
    if kind in ("import", "twitch") and "analys" in title.lower():
        return WITH_ANALYSIS      # "Importing and analysing ..."
    return NEEDS.get(kind, Needs())


def check(settings: Settings, key: str, title: str = "") -> tuple[str | None, list[str]]:
    """(why it can't start, or None; things that will make it slower)."""
    needs = needs_for(key, title)
    slower: list[str] = []
    if needs.ffmpeg and not _has_ffmpeg():
        return ("FFmpeg isn't installed, or AI-Editor can't find it (error E001: manual "
                "chapter 25)."), slower
    if needs.space:
        folder = getattr(settings.folders, needs.space)
        free = _free_gb(folder)
        if free is not None and free < MIN_FREE_GB:
            return (f"Only {free:.1f} GB free on the drive with your {needs.space} folder "
                    f"({folder}). Free some space first (Storage)."), slower
    found = card() if (needs.gpu or needs.ai or needs.encoder) else None
    if needs.gpu and settings.performance.device == "gpu" and found is None:
        return ("Analysing needs an NVIDIA graphics card, and this PC doesn't have one (or its "
                "driver isn't installed)."), slower
    if needs.ai and settings.llm.enabled:
        note = ai_note(settings, found)
        if note:
            slower.append(note)
    if needs.encoder and settings.performance.device == "gpu":
        from .ffmpeg import nvenc_encoders

        try:
            has_encoder = bool(nvenc_encoders())
        except Exception:  # noqa: BLE001 -- FFmpeg itself is checked above
            has_encoder = True
        if not has_encoder:
            slower.append("No NVIDIA video encoder, so videos are encoded on the processor: "
                          "slower, same result.")
    return None, slower


def ai_note(settings: Settings, found: Card | None = None) -> str | None:
    """"Slower" when the card has less memory than the local AI needs. None if it fits."""
    from . import llm

    size = llm.model_size(settings)
    if not size:
        return None
    need = size / 1e9 + AI_EXTRA_GB
    found = found or card()
    if found is None:
        return (f"No NVIDIA graphics card: the local AI ({settings.llm.model}) runs on the "
                "processor, which is much slower.")
    if found.memory_gb < need:
        return (f"Your graphics card has {found.memory_gb:.0f} GB and the local AI needs about "
                f"{need:.0f} GB, so part of it runs on the processor: slower, same answers.")
    return None


def precheck(settings: Settings):
    """For Worker.precheck: the check, for each job as it starts."""
    def run(task) -> tuple[str | None, list[str]]:
        try:
            return check(settings, task.key, task.title)
        except Exception:  # noqa: BLE001 -- a check that breaks never stops a job
            log.exception("Couldn't check the PC for job '%s'", task.title)
            return None, []
    return run
