"""What the Storage tab shows, and freeing space (spec section 10).

Everything shares one drive, so the creator sees what takes the room. The
one clean-up they chose (2026-10-03) is the analysis working files: about
1-2 GB per stream, needed by nothing once a recording is analysed, and made
again if it's ever re-analysed. Raw recordings are never deleted, and
neither is anything a video needs: the sound tracks, the preview copy, the
analysis data, finished videos.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..ingest import recording_cache_dir
from .library import size_text

# The analysis's own working files: prepared sound, AI-separated voices, scratch.
WORKING = ("analysis/prepared", "analysis/separated", "analysis/work")

COLUMNS = ["#", "Recording", "Recording file", "Sound tracks", "Preview copy", "Working files",
           "Analysis data", "Status"]


def size_of(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if not path.is_dir():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


@dataclass
class Usage:
    recording_id: int | None  # None: a leftover from a recording no longer in the library
    title: str
    folder: Path
    raw: int
    sound: int
    preview: int
    working: int
    analysis: int
    status: str


def recording_usage(conn, settings: Settings) -> list[Usage]:
    """Each recording's share of the cache, newest first; leftovers last."""
    from .library import _rows, status_of

    found, known = [], set()
    for row in _rows(conn):
        folder = recording_cache_dir(settings, row["content_hash"])
        known.add(folder.name)
        source = Path(row["source_file"])
        working = sum(size_of(folder / w) for w in WORKING)
        sound = size_of(folder / "audio")
        preview = size_of(folder / "proxy.mp4") + size_of(folder / "proxy.srt")
        found.append(Usage(row["id"], row["title"] or source.stem, folder,
                           source.stat().st_size if source.is_file() else 0, sound, preview,
                           working, size_of(folder) - working - sound - preview, status_of(row)))
    base = settings.folders.cache / "recordings"
    if base.is_dir():
        for folder in sorted(base.iterdir()):
            if folder.is_dir() and folder.name not in known:
                found.append(Usage(None, "(not in the library any more)", folder, 0, 0, 0,
                                   size_of(folder), 0, "Leftover"))
    return found


def usage_table(usages: list[Usage]) -> list[list]:
    return [[u.recording_id or "-", u.title, size_text(u.raw) if u.raw else "-",
             size_text(u.sound), size_text(u.preview), size_text(u.working),
             size_text(u.analysis), u.status] for u in usages]


def overview(settings: Settings, usages: list[Usage]) -> str:
    """Free space on each drive, and what's in each folder (Markdown)."""
    folders = settings.folders
    drives: dict[str, list[str]] = {}
    for name, path in folders.all().items():
        drives.setdefault(Path(path).anchor.upper() or str(path), []).append(name)
    lines = ["#### Drives"]
    limit = settings.storage.low_space_warning_gb * 1024**3
    for anchor, names in drives.items():
        try:
            disk = shutil.disk_usage(anchor)
        except OSError:
            continue
        # "F:" not "F:\": a backslash would undo the bold in Markdown.
        line = (f"- **{anchor.rstrip(chr(92) + '/')}** {size_text(disk.free)} free of "
                f"{size_text(disk.total)} "
                f"({', '.join(names)})")
        if disk.free < limit:
            line += (f" **Below your {settings.storage.low_space_warning_gb:.0f} GB warning "
                     "level.**")
        lines.append(line)
    output = folders.output
    videos = size_of(output / "videos")
    previews = size_of(output / "plan-previews") + size_of(output / "clip-previews")
    raw_files = [f for f in folders.raw.iterdir() if f.is_file()] if folders.raw.is_dir() else []
    lines += [
        "#### What's using it",
        f"- **Your recordings** (raw folder): {size_text(sum(f.stat().st_size for f in raw_files))} "
        f"in {len(raw_files)} file(s). Never deleted by AI-Editor.",
        f"- **AI-Editor's working copies** (cache): "
        f"{size_text(sum(u.sound + u.preview + u.working + u.analysis for u in usages))}, "
        f"of which **{size_text(sum(u.working for u in usages))}** is working files you can free.",
        f"- **Finished videos**: {size_text(videos)}. **Quick previews and reels**: "
        f"{size_text(previews)}.",
    ]
    return "\n".join(lines)


def _remove(path: Path, cache: Path) -> int:
    """Delete a folder in AI-Editor's own cache, and nowhere else, ever."""
    base = (cache / "recordings").resolve()
    target = path.resolve()
    if base not in target.parents:
        raise ValueError(f"Refusing to delete {target}: it isn't in {base}")
    size = size_of(target)
    shutil.rmtree(target, ignore_errors=True)
    return size


def free_working_files(settings: Settings, usages: list[Usage], chosen: set) -> int:
    """Delete the working files of the chosen recordings (ids, or folder names
    for leftovers). Returns the bytes freed."""
    freed = 0
    cache = settings.folders.cache
    for u in usages:
        if (u.recording_id if u.recording_id is not None else u.folder.name) not in chosen:
            continue
        if u.recording_id is None:  # a leftover: the whole folder is spare
            freed += _remove(u.folder, cache)
            continue
        for part in WORKING:
            if (u.folder / part).exists():
                freed += _remove(u.folder / part, cache)
    return freed
