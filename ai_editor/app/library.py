"""What the Library and Import tabs show (spec section 9, items 1 and 2).

Plain functions over the database and the raw folder, kept apart from the
window so they can be tested without it.
"""

from __future__ import annotations

import html
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..analysis.captions import clock
from ..cli import _duration
from ..companion.link import league_events, league_summary, listed
from ..config import Settings
from ..games import KNOWN_GAMES

VIDEO_TYPES = {".mkv", ".mp4", ".mov", ".flv", ".ts", ".m4v", ".webm"}
STILL_RECORDING_SEC = 60  # a file changed this recently may be one OBS is still writing

COLUMNS = ["#", "Recording", "Game", "Length", "Recorded", "Sound", "Status", "Clips", "Chat"]

STATUS = {
    "complete": "Analysed",
    "running": "Analysing",
    "paused": "Analysis paused",
    "failed": "Analysis failed",
    "pending": "Not analysed yet",
}


def when(iso: str | None) -> str:
    """'26 Sep 2026, 21:10' in the PC's own time zone."""
    if not iso:
        return "-"
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().strftime("%d %b %Y, %H:%M").lstrip("0")


def size_text(size: int) -> str:
    return f"{size / 1024**3:,.1f} GB" if size >= 1024**3 else f"{size / 1024**2:,.0f} MB"


def _rows(conn) -> list:
    return conn.execute(
        "SELECT r.*, "
        "(SELECT COUNT(*) FROM audio_tracks a WHERE a.recording_id = r.id) AS tracks, "
        "(SELECT COUNT(*) FROM audio_tracks a WHERE a.recording_id = r.id "
        " AND a.extracted_path IS NOT NULL) AS tracks_ready, "
        "(SELECT COUNT(*) FROM clips c WHERE c.recording_id = r.id) AS clip_count, "
        "(SELECT COUNT(*) FROM chat_messages m WHERE m.recording_id = r.id) AS chat_count "
        "FROM recordings r ORDER BY COALESCE(r.recorded_at, r.imported_at) DESC"
    ).fetchall()


# Deleted after its videos were made (the creator's way, 10 Oct), or moved.
VIDEO_GONE = "Video deleted (kept for learning)"


def status_of(row) -> str:
    if not Path(row["source_file"]).exists():
        return VIDEO_GONE
    imported = (row["proxy_path"] and Path(row["proxy_path"]).exists()
                and row["tracks"] and row["tracks_ready"] == row["tracks"])
    if not imported:
        return "Import unfinished"
    return STATUS.get(row["analysis_status"], row["analysis_status"])


def chat_of(row, settings: Settings, now: datetime | None = None) -> str:
    if row["chat_count"]:
        return f"{row['chat_count']:,} messages"
    if not row["twitch_vod_id"]:
        return "-"
    left = days_left(row["recorded_at"], settings.twitch.vod_keep_days, now)
    if left is None:
        return "Not attached"
    if left <= 0:
        return "Not attached; Twitch may have deleted the VOD"
    return f"Not attached; about {left:.0f} day(s) left on Twitch"


def days_left(recorded_at: str | None, keep_days: int, now: datetime | None = None) -> float | None:
    """Days until Twitch deletes the VOD (spec section 7.2)."""
    if not recorded_at:
        return None
    try:
        made = datetime.fromisoformat(recorded_at)
    except ValueError:
        return None
    if made.tzinfo is None:
        made = made.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return keep_days - (now - made).total_seconds() / 86400


def library_table(conn, settings: Settings) -> list[list]:
    """One row per recording, newest first, in COLUMNS order."""
    table = []
    for row in _rows(conn):
        tracks = row["tracks"]
        table.append([
            row["id"],
            row["title"] or Path(row["source_file"]).stem,
            row["game"] or "-",
            _duration(row["duration_sec"]),
            when(row["recorded_at"] or row["imported_at"]),
            f"{tracks} tracks" if tracks > 1 else "1 mixed track" if tracks else "-",
            status_of(row),
            row["clip_count"] or "-",
            chat_of(row, settings),
        ])
    return table


def recording_choices(conn) -> list[tuple[str, int]]:
    """(label, id) pairs for picking a recording, newest first."""
    return [(f"#{r['id']}  {r['title'] or Path(r['source_file']).stem}"
             + (f"  ({r['game']})" if r["game"] else ""), r["id"]) for r in _rows(conn)]


def recording_details(conn, settings: Settings, recording_id: int) -> str:
    """Markdown describing one recording."""
    row = next((r for r in _rows(conn) if r["id"] == recording_id), None)
    if row is None:
        return "That recording isn't in the library any more."
    tracks = conn.execute("SELECT stream_index, role FROM audio_tracks WHERE recording_id = ? "
                          "ORDER BY stream_index", (recording_id,)).fetchall()
    source = Path(row["source_file"])
    lines = [
        f"### #{row['id']}  {row['title'] or source.stem}",
        f"- **Status:** {status_of(row)}",
        f"- **Game:** {row['game'] or 'not set'}",
        f"- **Length:** {_duration(row['duration_sec'])}",
        f"- **Recorded:** {when(row['recorded_at'])}  (imported {when(row['imported_at'])})",
        f"- **From:** {'Twitch VOD ' + row['twitch_vod_id'] if row['twitch_vod_id'] else 'OBS on this PC'}",
    ]
    if row["width"]:
        lines.append(f"- **Video:** {row['width']}x{row['height']} at {row['fps'] or 0:.0f} fps")
    lines.append("- **Sound:** " + (", ".join(f"track {t['stream_index']} {t['role'].replace('_', ' ')}"
                                             for t in tracks) or "-"))
    if row["analysis_status"] == "complete":
        lines.append(f"- **Clips found:** {row['clip_count']}")
        notes = json.loads(row["notes"] or "{}")
        if notes.get("phrases_set_aside"):
            lines.append(f"- **Set aside:** {notes['phrases_set_aside']} phrase(s) that were "
                         "probably music or noise misheard as speech")
    lines.append(f"- **Chat:** {chat_of(row, settings)}")
    if row["session_id"]:
        markers = conn.execute(
            "SELECT COUNT(*) FROM companion_events WHERE session_id = ? "
            "AND event_type IN ('marker', 'marker_short')", (row["session_id"],)).fetchone()[0]
        lines.append(f"- **Stream Companion:** session {row['session_id']}, {markers} marker(s)")
        events = league_events(conn, recording_id)
        if events:
            lines.append(f"- **League events:** {league_summary(events)}")
            shown = [(t, e) for t, e in events if listed(e)]
            items = "".join(f"<li>{clock(t)} · {html.escape(e.get('text') or '')}</li>"
                            for t, e in shown)
            lines.append(f"\n<details><summary>Every League event ({len(shown)}): times in the "
                         f"recording</summary><ul>{items}</ul></details>\n")
    lines.append(f"- **File:** `{source}`" + ("" if source.exists() else
                 "  **(deleted or moved)**: its clips, transcript and everything you taught "
                 "AI-Editor are kept, and its clips can still be watched; finished videos "
                 "can't be made from it. Moved it? Import it from its new place to relink it."))
    return "\n".join(lines)


@dataclass(frozen=True)
class NewFile:
    path: Path
    size: int
    modified: float

    @property
    def still_recording(self) -> bool:
        return time.time() - self.modified < STILL_RECORDING_SEC

    def label(self) -> str:
        stamp = datetime.fromtimestamp(self.modified).strftime("%a %d %b, %H:%M")
        extra = "  (still being recorded?)" if self.still_recording else ""
        return f"{self.path.name}  ({size_text(self.size)}, {stamp}){extra}"


def new_recordings(conn, settings: Settings) -> list[NewFile]:
    """Videos in the raw folder that aren't in the library yet, newest first.

    Matched by file location. A recording that was moved shows up here too;
    importing it just relinks the library entry (it's matched by content).
    """
    known = {str(Path(r["source_file"])).lower()
             for r in conn.execute("SELECT source_file FROM recordings")}
    found = []
    try:
        entries = list(settings.folders.raw.iterdir())
    except OSError:
        return []
    for path in entries:
        if (path.suffix.lower() not in VIDEO_TYPES or ".partial" in path.name
                or str(path).lower() in known):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if path.is_file():
            found.append(NewFile(path, stat.st_size, stat.st_mtime))
    return sorted(found, key=lambda f: f.modified, reverse=True)


def game_choices(conn) -> list[str]:
    """The known games plus any others already in the library."""
    names = set(KNOWN_GAMES)
    names.update(r[0] for r in conn.execute("SELECT DISTINCT game FROM recordings "
                                            "WHERE game IS NOT NULL AND game != ''"))
    return sorted(names)


def check_importable(path_text: str) -> tuple[Path | None, str | None]:
    """The file to import, or a plain reason it can't be."""
    text = (path_text or "").strip().strip('"')
    if not text:
        return None, "Pick a recording from the list, or Browse to one."
    path = Path(text)
    if not path.is_file():
        return None, f"There's no file at {text}"
    if path.suffix.lower() not in VIDEO_TYPES:
        return None, f"{path.name} doesn't look like a video ({', '.join(sorted(VIDEO_TYPES))})."
    if time.time() - path.stat().st_mtime < STILL_RECORDING_SEC:
        return None, (f"{path.name} changed in the last minute. If OBS is still recording it, "
                      "stop the recording first, then import.")
    return path, None


_PICKER = """
import sys, tkinter
from tkinter import filedialog
root = tkinter.Tk()
root.withdraw()
root.attributes("-topmost", True)
name = filedialog.askopenfilename(
    parent=root, title="Pick a recording to import", initialdir=sys.argv[1],
    filetypes=[("Videos", "*.mkv *.mp4 *.mov *.flv *.ts *.m4v *.webm"), ("All files", "*.*")])
print(name or "", end="")
"""


def browse_for_video(start: Path) -> str:
    """Windows' own Open dialog, on top of the browser. '' if cancelled.

    Run as a separate small program: the dialog needs a thread of its own
    that the web server can't give it.
    """
    result = subprocess.run([sys.executable, "-c", _PICKER, str(start)], capture_output=True,
                            text=True, encoding="utf-8", timeout=600)
    return str(Path(result.stdout)) if result.stdout.strip() else ""
