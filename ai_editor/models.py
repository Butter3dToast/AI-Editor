"""AI model loading, one model on the graphics card at a time.

Spec section 3: 12 GB of VRAM means "only one large model loaded at a time";
each stage unloads its model before the next loads. Every model here is used
through a context manager, and leaving the ``with`` block frees its memory
whether the stage finished, failed, or was interrupted.

Model files live in the creator's models folder (spec section 10) and are
downloaded once, the first time they're needed.
"""

from __future__ import annotations

import csv
import gc
import os
import sys
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import Settings
from .errors import ModelDownloadFailed, OutOfGraphicsMemory
from .logging_setup import get_logger

log = get_logger(__name__)

PANNS_CHECKPOINT_URL = "https://zenodo.org/record/3987831/files/Cnn14_mAP%3D0.431.pth?download=1"
PANNS_CHECKPOINT_NAME = "Cnn14_mAP=0.431.pth"
PANNS_CHECKPOINT_MIN_BYTES = 300_000_000
AUDIOSET_LABELS_URL = (
    "http://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/class_labels_indices.csv"
)


# --- GPU housekeeping ------------------------------------------------------


def _prepare_cuda_libraries() -> None:
    """Let faster-whisper find the NVIDIA libraries that PyTorch ships.

    faster-whisper's engine (CTranslate2) needs cuBLAS and cuDNN for CUDA 12.
    The CUDA 12 build of PyTorch includes exactly those DLLs in torch/lib, but
    Windows only searches there if told to.
    """
    if sys.platform != "win32":
        return
    try:
        import torch
    except ImportError:
        return
    lib_dir = Path(torch.__file__).parent / "lib"
    if lib_dir.is_dir():
        os.add_dll_directory(str(lib_dir))
        os.environ["PATH"] = str(lib_dir) + os.pathsep + os.environ.get("PATH", "")


def use_gpu(settings: Settings) -> bool:
    if settings.performance.device != "gpu":
        return False
    try:
        import torch
    except ImportError:
        return False
    return bool(torch.cuda.is_available())


def free_gpu_memory() -> None:
    """Hand graphics memory back after a model is finished with."""
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def is_out_of_memory(exc: BaseException) -> bool:
    """Both engines report running out of VRAM differently; catch either."""
    text = str(exc).lower()
    return "out of memory" in text or type(exc).__name__ == "OutOfMemoryError"


# --- Downloads -------------------------------------------------------------


def download(url: str, destination: Path, *, min_bytes: int = 1, what: str) -> Path:
    """Fetch a file once. A half-finished download never counts as done."""
    if destination.exists() and destination.stat().st_size >= min_bytes:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    log.warning("Downloading %s (one time only) to %s", what, destination)
    try:
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
    except (OSError, ValueError) as exc:
        partial.unlink(missing_ok=True)
        log.error("Download of %s from %s failed: %s", what, url, exc)
        raise ModelDownloadFailed(f"The {what} could not be downloaded") from exc
    if partial.stat().st_size < min_bytes:
        partial.unlink(missing_ok=True)
        raise ModelDownloadFailed(f"The {what} download was incomplete")
    os.replace(partial, destination)
    return destination


# --- Whisper (transcription) -----------------------------------------------


@contextmanager
def whisper_model(settings: Settings) -> Iterator[object]:
    """faster-whisper, on the GPU in float16 when available.

    Falls back to the processor (int8) without a GPU: much slower, but it
    still works.
    """
    _prepare_cuda_libraries()
    from faster_whisper import WhisperModel

    gpu = use_gpu(settings)
    device = "cuda" if gpu else "cpu"
    compute_type = settings.analysis.compute_type if gpu else "int8"
    root = settings.folders.models / "whisper"
    root.mkdir(parents=True, exist_ok=True)

    try:
        model = WhisperModel(
            settings.analysis.transcription_model,
            device=device,
            compute_type=compute_type,
            download_root=str(root),
        )
    except Exception as exc:  # noqa: BLE001 - classified below
        free_gpu_memory()
        if is_out_of_memory(exc):
            raise OutOfGraphicsMemory() from exc
        log.exception("Loading the transcription model failed")
        raise ModelDownloadFailed("The transcription model could not be loaded") from exc

    log.info("Transcription model %s loaded on %s (%s)",
             settings.analysis.transcription_model, device, compute_type)
    try:
        yield model
    finally:
        del model
        free_gpu_memory()


# --- PANNs (sound recognition) ---------------------------------------------


def audioset_labels(settings: Settings) -> list[str]:
    """The 527 sound class names, in the order the model outputs them."""
    path = download(
        AUDIOSET_LABELS_URL,
        settings.folders.models / "panns" / "class_labels_indices.csv",
        min_bytes=10_000,
        what="sound label list",
    )
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    return [row[2] for row in rows[1:]]


@contextmanager
def sound_model(settings: Settings) -> Iterator[tuple[object, str]]:
    """The Cnn14 sound-recognition model and the device it runs on."""
    import torch

    from .analysis.panns_cnn14 import Cnn14

    checkpoint = download(
        PANNS_CHECKPOINT_URL,
        settings.folders.models / "panns" / PANNS_CHECKPOINT_NAME,
        min_bytes=PANNS_CHECKPOINT_MIN_BYTES,
        what="sound recognition model (about 330 MB)",
    )
    device = "cuda" if use_gpu(settings) else "cpu"
    model = Cnn14()
    try:
        state = torch.load(checkpoint, map_location=device, weights_only=True)
        # strict=False: the checkpoint also carries the training-only
        # augmentation layer, which the inference copy leaves out. It has no
        # weights, so nothing that matters is skipped.
        missing, _unexpected = model.load_state_dict(state["model"], strict=False)
        if missing:
            raise RuntimeError(f"checkpoint is missing weights: {missing[:5]}")
        model.to(device).eval()
    except Exception as exc:  # noqa: BLE001
        free_gpu_memory()
        if is_out_of_memory(exc):
            raise OutOfGraphicsMemory() from exc
        log.exception("Loading the sound recognition model failed")
        checkpoint.unlink(missing_ok=True)  # Likely corrupt; fetch again next time.
        raise ModelDownloadFailed("The sound recognition model could not be loaded") from exc

    try:
        yield model, device
    finally:
        del model
        free_gpu_memory()
