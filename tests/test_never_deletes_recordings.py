"""AI-Editor never deletes your recordings: only you do (the creator, 10 Oct 2026).

The creator deletes streams from the raw folder once their videos are made.
That must only ever be their own doing. Rather than trusting that to care,
this test lists every place in AI-Editor that deletes a file or folder, each
reviewed: they are all AI-Editor's own temporary or working files. Adding a
new one fails the build until someone checks it and adds it here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "ai_editor"

DELETES = re.compile(r"\.unlink\(|\bos\.remove\(|\bos\.unlink\(|\brmtree\(|\.rmdir\(|send2trash")

# Every deletion, per file, and what it deletes. None of these is a recording.
REVIEWED = {
    "twitch.py": 2,             # the downloader tool's zip; a VOD download that failed half-way
    "publish.py": 3,            # old thumbnails AI-Editor made, in the output folder
    "ingest.py": 2,             # half-made preview copies and sound tracks, in the cache
    "models.py": 4,             # half-downloaded or damaged AI model files, in the models folder
    "companion/status.py": 1,   # the Companion's status and stop files, in the cache
    "render/final.py": 2,       # a render's working folder, and an unfinished render
    "recipes/preview.py": 2,    # quick previews' working folders
    "cli.py": 1,                # the setup check's own write-test file
    "analysis/previews.py": 1,  # an old clip preview AI-Editor made
    "analysis/picture.py": 1,   # a temporary frame dump, in the cache
    "analysis/pipeline.py": 1,  # a half-written sound file, in the cache
    "analysis/separation.py": 3,  # voice separation's working files, in the cache
    "app/storage.py": 1,        # Storage clean-up: inside the cache only (tested below)
}


def deletions() -> dict[str, int]:
    found: dict[str, int] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        count = len(DELETES.findall(path.read_text(encoding="utf-8")))
        if count:
            found[path.relative_to(PACKAGE).as_posix()] = count
    return found


def test_every_deletion_is_one_that_was_checked():
    assert deletions() == REVIEWED, (
        "A deletion was added or removed. Check it can never touch a recording (the raw "
        "folder), then update REVIEWED.")


def test_storage_clean_up_refuses_anything_outside_the_cache(tmp_path):
    from ai_editor.app.storage import _remove

    cache, raw = tmp_path / "cache", tmp_path / "raw"
    (cache / "recordings" / "abc").mkdir(parents=True)
    raw.mkdir()
    stream = raw / "2026-10-07 19-55-03.mkv"
    stream.write_bytes(b"a stream")
    for target in (raw, stream, cache, cache / "recordings", tmp_path):
        with pytest.raises(ValueError):
            _remove(target, cache)
    assert stream.exists()
    _remove(cache / "recordings" / "abc", cache)
    assert not (cache / "recordings" / "abc").exists()
