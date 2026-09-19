"""Chat activity per second (spec section 7.3: "messages per 10 s, z-scored").

Chat is attached to a recording separately from audio analysis, because it
comes from Twitch rather than from the recording itself -- and often later,
or for a local recording made while streaming (manual 10.3).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import Settings
from ..errors import RecordingNotFound
from ..ingest import recording_cache_dir
from ..logging_setup import FILE_ONLY, get_logger
from .. import twitch

log = get_logger(__name__)

WINDOW_SEC = 10
CHAT_SIGNALS = ("chat_rate", "chat_z")


def chat_rate(times: list[float], seconds: int, window: int = WINDOW_SEC) -> np.ndarray:
    """Messages in the ``window`` seconds centred on each second."""
    per_second = np.zeros(seconds, dtype=np.float32)
    for t in times:
        second = int(t)
        if 0 <= second < seconds:
            per_second[second] += 1
    kernel = np.ones(window, dtype=np.float32)
    return np.convolve(per_second, kernel, mode="same").astype(np.float32)


def chat_zscore(rate: np.ndarray) -> np.ndarray:
    """How unusually busy chat is, compared with this stream's normal.

    A small channel's chat is mostly silent, which makes the median-based
    score used for loudness zero everywhere. Mean and standard deviation still
    pick out the moments when several people type at once.
    """
    if rate.size == 0 or float(rate.std()) < 1e-6:
        return np.zeros_like(rate)
    return np.clip((rate - rate.mean()) / rate.std(), -10.0, 10.0).astype(np.float32)


@dataclass
class ChatResult:
    recording_id: int
    vod_id: str
    messages: int
    bot_messages: int
    messages_in_recording: int
    chatters: int
    busiest: list[tuple[int, float]]
    expiry_warning: str | None


def attach_chat(
    conn: sqlite3.Connection,
    settings: Settings,
    recording_id: int,
    vod_link: str,
    *,
    recording_starts_at: float = 0.0,
    chat_file: Path | None = None,
) -> ChatResult:
    """Download a VOD's chat and line it up with a recording.

    ``recording_starts_at`` is how many seconds into the stream the recording
    began: 0 for the VOD itself; a few seconds for a local recording started
    with "Automatically record when streaming". In Phase 1D the Stream
    Companion's log supplies it automatically.

    ``chat_file`` uses an already-downloaded chat JSON instead (and in tests).
    """
    from .audio_signals import top_moments

    row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    if row is None:
        raise RecordingNotFound(f"There is no recording number {recording_id}")
    vod_id = twitch.parse_vod_id(vod_link)

    warning = None
    if chat_file is None:
        try:
            info = twitch.vod_info(settings, vod_id)
            warning = twitch.expiry_warning(info, settings.twitch.vod_keep_days)
        except Exception:  # noqa: BLE001 - the chat download below reports properly
            log.warning("Could not read VOD details for %s", vod_id, exc_info=True,
                        extra=FILE_ONLY)
        chat_file = twitch.download_chat(
            settings, vod_id,
            recording_cache_dir(settings, row["content_hash"]) / "chat" / f"chat_{vod_id}.json",
        )

    ignored = {name.lower() for name in settings.twitch.ignore_chatters}
    everything = twitch.load_chat(chat_file)
    messages = [m for m in everything if (m.username or "").lower() not in ignored]
    seconds = max(1, int(np.ceil(row["duration_sec"] or 0)))
    placed = [(m.t_sec - recording_starts_at, m) for m in messages]
    inside = [(t, m) for t, m in placed if 0 <= t < seconds]

    conn.execute("DELETE FROM chat_messages WHERE recording_id = ?", (recording_id,))
    conn.executemany(
        "INSERT INTO chat_messages (recording_id, t_sec, username, message) VALUES (?, ?, ?, ?)",
        [(recording_id, round(t, 3), m.username, m.text) for t, m in inside],
    )

    rate = chat_rate([t for t, _ in inside], seconds)
    z = chat_zscore(rate)
    conn.execute(
        f"DELETE FROM signals WHERE recording_id = ? AND name IN ({','.join('?' * len(CHAT_SIGNALS))})",
        (recording_id, *CHAT_SIGNALS),
    )
    conn.executemany(
        "INSERT INTO signals (recording_id, t_sec, name, value) VALUES (?, ?, ?, ?)",
        [(recording_id, t, name, float(v))
         for name, values in (("chat_rate", rate), ("chat_z", z))
         for t, v in enumerate(values)],
    )
    conn.execute("UPDATE recordings SET twitch_vod_id = ? WHERE id = ?", (vod_id, recording_id))
    conn.commit()

    log.info("Attached %d chat messages from VOD %s to recording #%d",
             len(inside), vod_id, recording_id)
    return ChatResult(
        recording_id=recording_id,
        vod_id=vod_id,
        messages=len(messages),
        bot_messages=len(everything) - len(messages),
        messages_in_recording=len(inside),
        chatters=len({m.username for _, m in inside if m.username}),
        busiest=top_moments(rate, count=8, min_gap=30, threshold=1.0),
        expiry_warning=warning,
    )
