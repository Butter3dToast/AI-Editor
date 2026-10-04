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


# --- Shorts: a few words, the one being said lit up ------------------------------------

SHORT_BASE_HEIGHT = 1920   # captions.shorts_size is for a 1920-high picture
SHORT_LEFT_MARGIN = 0.06   # of the width; the right one is the platform's button column
SHORT_ABOVE_ZONE = 0.06    # of the height, between the captions and the bottom safe zone
PHRASE_GAP_SEC = 0.6       # a pause this long starts a new phrase
PHRASE_MAX_CHARS = 22      # ...and so does a phrase getting too long for one line
PHRASE_HOLD_SEC = 0.4      # a phrase stays up this long after its last word


def ass_colour(hex_rgb: str) -> str:
    """'#FFD400' -> '&H0000D4FF' (ASS is alpha, blue, green, red)."""
    r, g, b = hex_rgb[1:3], hex_rgb[3:5], hex_rgb[5:7]
    return f"&H00{b}{g}{r}".upper()


def phrases(words: Sequence, most: int) -> list[list]:
    """Words grouped the way they're said: at most ``most``, broken at pauses,
    full stops and lines too long to read at a glance."""
    found: list[list] = []
    for word in words:
        current = found[-1] if found else None
        if (current is None or len(current) >= most
                or word.start - current[-1].end >= PHRASE_GAP_SEC
                or current[-1].text.rstrip().endswith((".", "?", "!"))
                or len(" ".join(w.text.strip() for w in current + [word])) > PHRASE_MAX_CHARS):
            found.append([word])
        else:
            current.append(word)
    return found


def short_document(words: Sequence, start: float, end: float, *, width: int, height: int,
                   style: Captions, zone) -> str:
    """ASS captions for one Short: ``words`` with times in the recording,
    ``start``-``end`` the stretch the Short shows. Each phrase is on screen
    while it's said; each word in it is lit while it's being said."""
    scale = height / SHORT_BASE_HEIGHT
    white, edge = "&H00FFFFFF", "&H00000000"
    lit = ass_colour(style.shorts_highlight)
    fields = ["Short", style.font, str(round(style.shorts_size * scale)), white, white, edge,
              "&H80000000", "-1", "0", "0", "0", "100", "100", "0", "0", "1",
              f"{max(style.outline, 5) * scale * 1.6:g}", f"{2 * scale:g}", "2",
              str(round(width * SHORT_LEFT_MARGIN)), str(round(width * zone.right)),
              str(round(height * (zone.bottom + SHORT_ABOVE_ZONE))), "1"]
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: " + ",".join(fields), "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    shown = [w for w in words if w.start >= start and w.end <= end and w.text.strip()]
    groups = phrases(shown, style.shorts_words)
    for n, group in enumerate(groups):
        after = groups[n + 1][0].start if n + 1 < len(groups) else end
        group_end = min(group[-1].end + PHRASE_HOLD_SEC, after, end)
        for i, word in enumerate(group):
            on = group[0].start if i == 0 else word.start
            off = group[i + 1].start if i + 1 < len(group) else group_end
            if off <= on:
                continue
            text = " ".join(
                f"{{\\c{lit}&}}{ass_text(w.text)}{{\\c{white}&}}" if j == i else ass_text(w.text)
                for j, w in enumerate(group))
            lines.append(f"Dialogue: 0,{ass_time(on - start)},{ass_time(off - start)},Short,,"
                         f"0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def write_ass(cues: Sequence[Cue], path: Path, **kwargs) -> Path:
    path.write_text(ass_document(cues, **kwargs), encoding="utf-8")
    return path
