"""The local AI (spec sections 3, 4 and 7): Ollama, on this PC only.

Ollama runs the language model on the graphics card and answers on
127.0.0.1:11434. Nothing is sent online: the only internet use is the
one-time model download, which Ollama does itself.

One model at a time on the card (spec section 3). A batch of questions keeps
the model loaded between them (loading it again for every clip would take
longer than the answers), and ``session()`` unloads it the moment the batch
ends, whether it finished, failed or was paused.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from .config import Settings
from .errors import AiAnswerUnreadable, AiModelMissing, AiNotRunning, AiTooSlow
from .logging_setup import get_logger

log = get_logger(__name__)

# While a batch runs, the model stays loaded this long between questions.
BATCH_KEEP_ALIVE = "5m"
# One answer normally takes 2-3 seconds, plus up to half a minute to load the
# model first. Far longer means a game has the graphics card (E035).
ANSWER_TIMEOUT_SEC = 90.0
START_WAIT_SEC = 20.0


def _url(settings: Settings, path: str) -> str:
    return settings.llm.host.rstrip("/") + path


def _request(settings: Settings, path: str, body: dict | None = None,
             timeout: float = 10.0) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(_url(settings, path), data=data,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310 (local only)
        return json.loads(reply.read().decode("utf-8") or "null")


def running(settings: Settings) -> str | None:
    """Ollama's version if it's answering, else None."""
    try:
        return _request(settings, "/api/version", timeout=2.0).get("version")
    except (OSError, ValueError, AttributeError):
        return None


def start(settings: Settings) -> str:
    """Make sure Ollama is answering, starting it if it's installed but closed.

    Ollama normally starts with Windows and sits in the tray. If it was
    closed, starting it here saves the creator a trip to the Start menu.
    """
    version = running(settings)
    if version:
        return version
    exe = shutil.which("ollama")
    if exe is None:
        raise AiNotRunning("Ollama isn't installed.")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    # Its own process, not tied to AI-Editor: other programs may use it too.
    subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags)
    deadline = time.monotonic() + START_WAIT_SEC
    while time.monotonic() < deadline:
        time.sleep(0.5)
        version = running(settings)
        if version:
            return version
    raise AiNotRunning("Ollama didn't start.")


def installed_models(settings: Settings) -> list[str]:
    try:
        return [m["name"] for m in _request(settings, "/api/tags").get("models", [])]
    except (OSError, ValueError, AttributeError):
        return []


def has_model(settings: Settings, name: str | None = None) -> bool:
    name = name or settings.llm.model
    if not name:
        return False
    found = installed_models(settings)
    # "gemma4" and "gemma4:latest" are the same model to Ollama.
    return name in found or (":" not in name and f"{name}:latest" in found)


def ready(settings: Settings) -> bool:
    """Switched on, Ollama answering, and the model downloaded."""
    return bool(settings.llm.enabled and settings.llm.model and running(settings)
                and has_model(settings))


def status(settings: Settings) -> str:
    """One line for Settings and the doctor."""
    if not settings.llm.enabled:
        return "Switched off (llm.enabled)."
    version = running(settings)
    if not version:
        return ("Ollama isn't running. It starts by itself when needed, if it's installed "
                "(manual 5.2).")
    if not has_model(settings):
        return f"Ollama {version} is running, but {settings.llm.model} isn't downloaded yet."
    return f"Ready: {settings.llm.model} on Ollama {version}."


def pull(settings: Settings, on_progress: Callable[[float], None] | None = None,
         name: str | None = None) -> None:
    """Download the model (once). Ollama keeps partial downloads, so a paused
    or failed download carries on where it stopped next time."""
    name = name or settings.llm.model
    if not name:
        raise AiModelMissing("No model is chosen (llm.model).")
    start(settings)
    request = urllib.request.Request(
        _url(settings, "/api/pull"), data=json.dumps({"model": name, "stream": True}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as reply:  # noqa: S310
            for line in reply:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("error"):
                    raise AiModelMissing(f"Ollama said: {event['error']}")
                if on_progress and event.get("total"):
                    on_progress(min(1.0, event.get("completed", 0) / event["total"]))
    except urllib.error.URLError as exc:
        raise AiModelMissing(f"The download stopped: {exc.reason}") from exc
    if on_progress:
        on_progress(1.0)


def unload(settings: Settings) -> None:
    """Hand the graphics card's memory back now (spec section 3: keep_alive 0)."""
    if not settings.llm.model:
        return
    try:
        _request(settings, "/api/generate", {"model": settings.llm.model, "keep_alive": 0},
                 timeout=30.0)
    except (OSError, ValueError):
        log.info("Couldn't ask Ollama to unload %s (it frees it by itself soon)",
                 settings.llm.model)


@contextmanager
def session(settings: Settings) -> Iterator[None]:
    """A batch of questions: the model loads once and is unloaded at the end."""
    start(settings)
    if not has_model(settings):
        raise AiModelMissing(f"{settings.llm.model} isn't downloaded yet.")
    try:
        yield
    finally:
        unload(settings)


def ask(settings: Settings, system: str, prompt: str, *, schema: dict,
        images: list[bytes] | None = None, keep_alive: str | int = BATCH_KEEP_ALIVE,
        timeout: float = ANSWER_TIMEOUT_SEC) -> dict:
    """One question, answered as JSON in the shape ``schema`` describes.

    Ollama constrains the answer to the schema, so it always parses; a
    model that still returns something unusable raises AiAnswerUnreadable.
    """
    message: dict[str, Any] = {"role": "user", "content": prompt}
    if images:
        message["images"] = [base64.b64encode(i).decode("ascii") for i in images]
    body = {
        "model": settings.llm.model,
        "messages": [{"role": "system", "content": system}, message],
        "stream": False,
        "format": schema,
        "think": False,  # a short, direct answer; thinking out loud only adds time here
        "keep_alive": keep_alive,
        "options": {"temperature": settings.llm.temperature},
    }
    try:
        reply = _request(settings, "/api/chat", body, timeout=timeout)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise AiAnswerUnreadable(f"Ollama said: {detail}") from exc
    except TimeoutError as exc:
        raise AiTooSlow() from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise AiTooSlow() from exc
        raise AiNotRunning(f"{exc.reason}") from exc
    except OSError as exc:
        raise AiNotRunning(f"{exc}") from exc
    text = (reply or {}).get("message", {}).get("content", "")
    try:
        answer = json.loads(text)
    except ValueError as exc:
        raise AiAnswerUnreadable(f"It answered: {text[:200]!r}") from exc
    if not isinstance(answer, dict):
        raise AiAnswerUnreadable(f"It answered: {text[:200]!r}")
    return answer
