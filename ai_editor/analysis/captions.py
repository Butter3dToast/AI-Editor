"""Grouping words into subtitle cues, and writing them as SRT.

In Phase 1B the SRT is a checking tool: dropped next to the proxy, VLC shows it
automatically, so the creator can watch whether the words are right and in
time. The same cue grouping feeds the burned-in captions in Phase 1G.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float
    probability: float = 1.0


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


SENTENCE_END = (".", "?", "!", "…")
CLAUSE_END = SENTENCE_END + (",", ";", ":")


def _text(words: Sequence[Word]) -> str:
    return " ".join(w.text.strip() for w in words if w.text.strip())


def build_cues(
    words: Sequence[Word],
    *,
    max_chars: int = 84,
    max_duration: float = 6.0,
    max_gap: float = 1.0,
    min_sentence_chars: int = 20,
    min_duration: float = 1.0,
) -> list[Cue]:
    """Group consecutive words into readable subtitle cues.

    Cutting only on length split sentences anywhere, and on EP 1 left
    fragments such as "there?" on screen for 0.18 s. So, in order:

    * a cue ends at the end of a sentence, once it holds at least
      ``min_sentence_chars`` (very short sentences like "Still." join the next);
    * a cue that would get too long to read (two lines of about 42
      characters) or stay up too long is split at its last comma or sentence
      end, and only mid-phrase when there is neither;
    * a pause longer than ``max_gap`` always starts a new cue;
    * every cue stays on screen at least ``min_duration`` seconds, as far as
      the next cue allows.
    """
    cues: list[Cue] = []
    current: list[Word] = []

    def flush(part: list[Word]) -> None:
        text = _text(part)
        if text:
            cues.append(Cue(part[0].start, part[-1].end, text))

    def too_big(part: list[Word], extra: Word) -> bool:
        return (
            len(_text([*part, extra])) > max_chars
            or extra.end - part[0].start > max_duration
        )

    for word in words:
        if current and word.start - current[-1].end > max_gap:
            flush(current)
            current = []
        elif current and too_big(current, word):
            # Prefer the last natural break that leaves words on both sides.
            cut = next(
                (i for i in range(len(current) - 1, -1, -1)
                 if current[i].text.strip().endswith(CLAUSE_END)),
                None,
            )
            if cut is not None and cut < len(current) - 1:
                flush(current[: cut + 1])
                current = current[cut + 1:]
                if current and too_big(current, word):
                    flush(current)
                    current = []
            else:
                flush(current)
                current = []

        current.append(word)
        if word.text.strip().endswith(SENTENCE_END) and len(_text(current)) >= min_sentence_chars:
            flush(current)
            current = []

    if current:
        flush(current)

    # Give very short cues time to be read, without overlapping the next one.
    for i, cue in enumerate(cues):
        if cue.end - cue.start < min_duration:
            limit = cues[i + 1].start if i + 1 < len(cues) else cue.start + min_duration
            cues[i] = Cue(cue.start, max(cue.end, min(cue.start + min_duration, limit)), cue.text)
    return cues


def srt_time(seconds: float) -> str:
    """00:01:02,345 -- SRT's own timestamp format, comma before milliseconds."""
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def clock(seconds: float) -> str:
    """1:02:03 -- the form a creator types into a video player's seek box."""
    whole = max(0, int(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def to_srt(cues: Sequence[Cue]) -> str:
    blocks = [
        f"{index}\n{srt_time(cue.start)} --> {srt_time(cue.end)}\n{cue.text}\n"
        for index, cue in enumerate(cues, start=1)
    ]
    return "\n".join(blocks)


def write_srt(cues: Sequence[Cue], path: Path) -> Path:
    # utf-8-sig: VLC and Windows players read the BOM as "this is UTF-8", which
    # keeps accented words and emoji from turning into garbage characters.
    path.write_text(to_srt(cues), encoding="utf-8-sig")
    return path
