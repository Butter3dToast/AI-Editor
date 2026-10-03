"""Captions burned into a finished video: the creator's words, simple and bold.

White bold letters with a black edge, a sentence or two at a time, centred
near the bottom (spec 7.8; the creator chose "the simple bold version" to
start with). They're written as an ASS subtitle file that FFmpeg's libass
draws onto the picture, so the look is all in one style line below.

Where they sit is a share of the picture's height, so they clear what each
game draws there: League's ability bar along the bottom, and in Let's Plays
the game's own subtitles (Dawnwalker's sit 9-15% up), which captions must
never cover (spec 7.6).

Only the creator's words are captioned: the transcript comes from the mic
track where the recording has one. A recording with only a mixed track can
include friends on Discord too, until speaker recognition (Phase 2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..analysis.captions import Cue
from ..config import Captions

BASE_HEIGHT = 1080  # caption sizes in settings are for a 1080-high picture
SIDE_MARGIN = 0.08  # of the width, each side: long lines wrap before the edge
TITLE_SCALE = 1.75  # a part's title card, against the captions' size
TITLE_FADE_SEC = 0.5


def ass_time(seconds: float) -> str:
    """0:01:02.35 -- ASS's own timestamp, in hundredths."""
    cs = max(0, round(seconds * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def ass_text(text: str) -> str:
    """Words as ASS shows them: braces and backslashes would be read as styling."""
    return " ".join(text.replace("\\", "/").replace("{", "(").replace("}", ")").split())


def ass_document(cues: Sequence[Cue], *, width: int, height: int, style: Captions,
                 place: float, title: Cue | None = None) -> str:
    """``title``: a Let's Play part's title card ("Ep 1 – Part 2"), large in the
    middle of the picture, fading in and out."""
    scale = height / BASE_HEIGHT
    colour = "&H00FFFFFF"   # white (ASS colours are &HAABBGGRR)
    edge = "&H00000000"     # black
    shadow = "&H80000000"   # half-see-through black
    fields = [
        "Default", style.font, str(round(style.size * scale)), colour, colour, edge, shadow,
        "-1" if style.bold else "0", "0", "0", "0", "100", "100", "0", "0",
        "1", f"{style.outline * scale:g}", f"{scale:g}",  # outlined text with a slight shadow
        "2",  # bottom centre
        str(round(width * SIDE_MARGIN)), str(round(width * SIDE_MARGIN)), str(round(height * place)),
        "1",
    ]
    big = [*fields]
    big[0], big[2] = "Title", str(round(style.size * TITLE_SCALE * scale))
    big[16], big[18] = f"{style.outline * TITLE_SCALE * scale:g}", "5"  # thicker edge, centred
    big[19:22] = ["0", "0", "0"]
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: " + ",".join(fields),
        "Style: " + ",".join(big),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    lines += [f"Dialogue: 0,{ass_time(c.start)},{ass_time(c.end)},Default,,0,0,0,,{ass_text(c.text)}"
              for c in cues if c.end > c.start]
    if title is not None and title.end > title.start:
        fade = round(min(TITLE_FADE_SEC, (title.end - title.start) / 3) * 1000)
        lines.append(f"Dialogue: 1,{ass_time(title.start)},{ass_time(title.end)},Title,,0,0,0,,"
                     f"{{\\fad({fade},{fade})}}{ass_text(title.text)}")
    return "\n".join(lines) + "\n"


def write_ass(cues: Sequence[Cue], path: Path, **kwargs) -> Path:
    path.write_text(ass_document(cues, **kwargs), encoding="utf-8")
    return path
