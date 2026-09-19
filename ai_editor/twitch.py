"""Twitch VODs and chat, through TwitchDownloader (spec sections 4 and 7.2).

TwitchDownloader is a free, open-source command-line tool. AI-Editor fetches a
pinned release into the tools folder the first time it's needed, the same way
AI models are fetched, so the creator never installs it by hand.

Only public VODs can be downloaded. Private, unpublished and subscriber-only
VODs look to Twitch like they don't exist; the fix is to make the VOD public,
or download it from the Twitch dashboard and import the file (manual 10.2).
Downloading with the creator's Twitch login token is deliberately not offered:
it means storing a credential, for something a public toggle solves.
"""

from __future__ import annotations

import json
import re
import subprocess
import zipfile
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .errors import InvalidVodLink, TwitchDownloadFailed, VodNotAvailable
from .ffmpeg import find_binary
from .logging_setup import FILE_ONLY, get_logger
from .models import download

log = get_logger(__name__)

TWITCH_DOWNLOADER_VERSION = "1.56.5"
TWITCH_DOWNLOADER_URL = (
    "https://github.com/lay295/TwitchDownloader/releases/download/"
    f"{TWITCH_DOWNLOADER_VERSION}/TwitchDownloaderCLI-{TWITCH_DOWNLOADER_VERSION}-Windows-x64.zip"
)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PERCENT = re.compile(r"(\d{1,3})%")
_STAGE = re.compile(r"\[(\d+)/(\d+)\]")


def progress_from_line(line: str) -> float | None:
    """Overall 0-1 progress from a TwitchDownloader status line.

    Its downloads run in stages that each count 0-100% ("Downloading 40% [2/4]",
    then "Verifying Parts 0% [3/4]"). Read naively, the bar would jump back to
    zero at every stage, so each stage is given its share of the whole.
    """
    percents = _PERCENT.findall(line)
    if not percents:
        return None
    fraction = min(1.0, int(percents[-1]) / 100)
    stage = _STAGE.search(line)
    if stage:
        number, total = int(stage.group(1)), int(stage.group(2))
        if 0 < number <= total:
            return (number - 1 + fraction) / total
    return fraction


# --- Links -----------------------------------------------------------------


def parse_vod_id(text: str) -> str:
    """The VOD number from a link, a dashboard link, or the number itself.

    Accepts twitch.tv/videos/2874991382, the Video Producer link
    dashboard.twitch.tv/u/<name>/content/video-producer/edit/2874991382, and
    plain 2874991382.
    """
    value = text.strip().strip('"').strip()
    if value.isdigit() and len(value) >= 6:
        return value
    match = re.search(r"(?:/videos/|/video-producer/edit/|[?&]video=v?)(\d{6,})", value)
    if match:
        return match.group(1)
    raise InvalidVodLink(f"Got {value[:80]!r}")


# --- The tool --------------------------------------------------------------


def tools_folder(settings: Settings) -> Path:
    return settings.tools.folder or settings.folders.models.parent / "tools"


def cli_path(settings: Settings) -> Path:
    """TwitchDownloaderCLI.exe, fetched on first use."""
    folder = tools_folder(settings) / "TwitchDownloader"
    exe = folder / "TwitchDownloaderCLI.exe"
    if exe.exists():
        return exe
    archive = download(TWITCH_DOWNLOADER_URL, folder / "cli.zip", min_bytes=10_000_000,
                       what="Twitch downloader tool (about 50 MB)")
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(folder)
    archive.unlink(missing_ok=True)
    if not exe.exists():
        raise TwitchDownloadFailed("The Twitch downloader tool was incomplete")
    return exe


def _run(
    settings: Settings,
    args: list[str],
    *,
    what: str,
    on_progress: Callable[[float], None] | None = None,
) -> str:
    """Run TwitchDownloader; return what it printed. Errors become plain language."""
    command = [str(cli_path(settings)), *args, "--banner", "false"]
    log.debug("TwitchDownloader (%s): %s", what, subprocess.list2cmdline(command))
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", creationflags=_NO_WINDOW,
    )
    output: list[str] = []
    tail: deque[str] = deque(maxlen=40)
    try:
        for line in process.stdout or ():
            output.append(line)
            tail.append(line)
            if on_progress:
                fraction = progress_from_line(line)
                if fraction is not None:
                    on_progress(fraction)
        process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise

    text = "".join(output)
    if process.returncode != 0:
        log.error("TwitchDownloader failed while %s (exit %s):\n%s",
                  what, process.returncode, "".join(tail), extra=FILE_ONLY)
        if "Invalid VOD" in text or "deleted/expired" in text:
            raise VodNotAvailable()
        raise TwitchDownloadFailed(f"This happened while {what}")
    if on_progress:
        on_progress(1.0)
    return text


# --- VOD information -------------------------------------------------------


@dataclass(frozen=True)
class VodInfo:
    vod_id: str
    title: str | None
    channel: str | None
    created_at: datetime | None
    length_sec: float | None
    game: str | None = None

    def age_days(self, now: datetime | None = None) -> float | None:
        if self.created_at is None:
            return None
        now = now or datetime.now(timezone.utc)
        return (now - self.created_at).total_seconds() / 86400


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_info(raw: str, vod_id: str) -> VodInfo:
    """Read TwitchDownloader's `info --format raw` output, which is JSON.

    Raises VodNotAvailable when Twitch describes no video at all.
    """
    start = raw.find("{")
    if start < 0:
        raise TwitchDownloadFailed("Twitch returned no information about the VOD")
    data, _ = json.JSONDecoder().raw_decode(raw[start:])
    video = (data.get("data") or {}).get("video")
    if not video:
        # Twitch answers a private, unpublished or expired VOD with an empty
        # "video" -- not an error -- so this is where that case is caught.
        raise VodNotAvailable()
    owner = video.get("owner") or {}
    return VodInfo(
        vod_id=vod_id,
        title=video.get("title"),
        channel=owner.get("displayName") or owner.get("login"),
        created_at=_parse_time(video.get("createdAt") or video.get("created_at")),
        length_sec=float(video["lengthSeconds"]) if video.get("lengthSeconds") else None,
        game=(video.get("game") or {}).get("displayName"),
    )


def vod_info(settings: Settings, vod_id: str) -> VodInfo:
    return parse_info(
        _run(settings, ["info", "--id", vod_id, "--format", "Raw"], what="asking Twitch about the VOD"),
        vod_id,
    )


def expiry_warning(info: VodInfo, keep_days: int, now: datetime | None = None) -> str | None:
    """Twitch deletes VODs after a while (spec section 7.2). Warn in good time."""
    age = info.age_days(now)
    if age is None:
        return None
    left = keep_days - age
    if left <= 0:
        return f"This VOD is {age:.0f} days old and Twitch may already be deleting it."
    if left <= 3:
        return f"Twitch deletes this VOD in about {left:.0f} day(s). Download it soon."
    return None


# --- Downloads -------------------------------------------------------------


def download_chat(settings: Settings, vod_id: str, output: Path,
                  on_progress: Callable[[float], None] | None = None) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + ".partial.json")
    _run(settings, ["chatdownload", "--id", vod_id, "--output", str(partial),
                    "--collision", "Overwrite"],
         what="downloading the chat", on_progress=on_progress)
    partial.replace(output)
    return output


def download_video(settings: Settings, vod_id: str, output: Path,
                   on_progress: Callable[[float], None] | None = None) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + ".partial.mp4")
    temp = settings.folders.cache / "twitch-temp"
    temp.mkdir(parents=True, exist_ok=True)
    try:
        _run(settings, ["videodownload", "--id", vod_id, "--output", str(partial),
                        "--quality", settings.twitch.download_quality,
                        "--ffmpeg-path", str(find_binary("ffmpeg")),
                        "--temp-path", str(temp), "--collision", "Overwrite"],
             what="downloading the VOD", on_progress=on_progress)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(output)
    return output


# --- Chat files ------------------------------------------------------------


@dataclass(frozen=True)
class ChatMessage:
    t_sec: float
    username: str | None
    text: str


def load_chat(path: Path) -> list[ChatMessage]:
    """Messages from a TwitchDownloader chat JSON, in time order.

    Each comment carries ``content_offset_seconds``: seconds from the start
    of the VOD.
    """
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    messages = []
    for comment in data.get("comments", []):
        offset = comment.get("content_offset_seconds")
        if offset is None:
            continue
        commenter = comment.get("commenter") or {}
        message = comment.get("message") or {}
        messages.append(ChatMessage(
            float(offset),
            commenter.get("display_name") or commenter.get("name"),
            str(message.get("body", "")),
        ))
    return sorted(messages, key=lambda m: m.t_sec)
