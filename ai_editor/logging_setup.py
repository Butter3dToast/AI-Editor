"""Logging.

Two audiences, two destinations:

* The log file gets everything, tracebacks included. It is what the creator
  sends when they click "Copy diagnostic info" (spec section 14.2).
* The console/UI gets plain-language messages only. Spec section 14.2 is
  explicit that raw stack traces are never shown to the creator.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

from .errors import AIEditorError

LOG_FILENAME = "ai-editor.log"
_configured = False


class _PlainLanguageFilter(logging.Filter):
    """Replace an AIEditorError's console text with its creator-facing message."""

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        if isinstance(exc, AIEditorError):
            record.msg = exc.user_message()
            record.args = ()
            record.exc_info = None  # Traceback still reaches the file handler.
        return True


def setup_logging(log_dir: str | Path, level: str = "INFO") -> Path:
    """Configure file and console logging. Safe to call more than once."""
    global _configured

    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / LOG_FILENAME

    root = logging.getLogger()
    if _configured:
        return log_path

    root.setLevel(logging.DEBUG)

    file_handler = RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s | %(message)s")
    )
    root.addHandler(file_handler)

    console = RichHandler(rich_tracebacks=False, show_path=False, markup=False)
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.addFilter(_PlainLanguageFilter())
    console.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(console)

    _configured = True
    return log_path


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
