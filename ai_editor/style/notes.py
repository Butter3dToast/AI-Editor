"""The local AI's notes on a reference's editing techniques (spec 7.4, Phase 2G-1).

Gemma looks at a few frames of each reference -- where it zoomed or a meme
sound played, and some from the rest -- and lists the techniques an editor
added: text pop-ups, meme images, colour effects, the facecam's place...
It's told what AI-Editor measured (cuts, zooms, captions) and asked only for
what the numbers can't show: asked with examples and nothing to go by, it
listed "rapid cuts" and "zoom on the player's reaction" for a video of one
unbroken shot (the first video on YouTube).
Then it sums up all the references' notes into one short list for the
profile. Notes are for the creator to read; they don't change any video.

On the graphics card, so only when it isn't busy: the same check as the AI
rating (an answer far slower than usual means a game has the card).
"""

from __future__ import annotations

from typing import Callable

from .. import llm
from ..config import Settings
from .measure import Measured

MAX_NOTES = 8
PER_ASK = 4      # frames per question: Gemma reads a handful well, a pile badly
PER_LOOK = 6     # notes per question at most: asked for more, it listed the same thing over
                 # and over ("white text on the left... on the right...") until cut off

SYSTEM = """You study how YouTube gaming videos are edited, for a streamer who wants to edit
their own videos in a style they like. You only describe what an editor added on top
of the gameplay, never the game itself: not its HUD, menus, health bars or map."""

LOOK = """These are {n} frames from a video whose editing the streamer likes.
AI-Editor has already measured it: {measured}. So don't list cuts, zooms or captions.

List other things an editor added on top of the gameplay, if you clearly see them:
meme images, emojis, stickers, text pop-ups that aren't captions, colour effects,
borders or frames, split screens, the facecam's place, logos or channel names.
At most {most}, each different, as short phrases. Frames of plain gameplay show none
of these: then give an empty list. Never guess; leave out anything you're not sure of."""

SUM_UP = """Here are notes on the editing of {n} videos the streamer likes, one list per video:

{lists}

Sum them up as at most {most} short notes, most common first, each one technique. Say
how many of the videos it was seen in, like "(2 of 3 videos)". Leave out anything that
is about the game rather than the editing."""


def schema(most: int) -> dict:
    return {"type": "object", "properties": {"techniques": {
        "type": "array", "maxItems": most, "items": {"type": "string", "maxLength": 80}}},
        "required": ["techniques"]}


def facts(m: Measured) -> str:
    """What was measured, for the AI to go by rather than guess."""
    return (f"{m.cuts_per_min:g} cuts a minute, {m.zooms_per_min:g} zooms a minute, captions "
            f"{m.caption_share:.0%} of the time")


def look(settings: Settings, frames: list[bytes], measured: Measured) -> list[str]:
    """Techniques seen in one reference's frames (inside an llm.session)."""
    seen: list[str] = []
    for i in range(0, len(frames), PER_ASK):
        batch = frames[i:i + PER_ASK]
        answer = llm.ask(settings, SYSTEM,
                         LOOK.format(n=len(batch), measured=facts(measured), most=PER_LOOK),
                         schema=schema(PER_LOOK), images=batch)
        seen += [str(x).strip() for x in answer.get("techniques", []) if str(x).strip()]
    return _unique(seen)[:MAX_NOTES]


def sum_up(settings: Settings, per_video: list[list[str]]) -> list[str]:
    """One short list for the profile, from every reference's notes."""
    lists = [notes for notes in per_video if notes]
    if not lists:
        return []
    if len(lists) == 1:
        return lists[0][:MAX_NOTES]
    text = "\n".join(f"Video {n}: " + "; ".join(notes) for n, notes in enumerate(lists, 1))
    answer = llm.ask(settings, SYSTEM, SUM_UP.format(n=len(lists), lists=text, most=MAX_NOTES),
                     schema=schema(MAX_NOTES))
    return _unique([str(x).strip() for x in answer.get("techniques", [])])[:MAX_NOTES]


def _unique(items: list[str]) -> list[str]:
    seen, out = set(), []
    for item in items:
        key = item.lower().rstrip(".")
        if key not in seen:
            seen.add(key)
            out.append(item.rstrip("."))
    return out


def available(settings: Settings, start: Callable[[Settings], bool]) -> str | None:
    """None if the AI can look; otherwise why not, in plain words."""
    if not settings.llm.enabled:
        return "the AI is switched off in Settings (AI)"
    if not start(settings):
        return "the local AI (Ollama) couldn't be started"
    if not llm.has_model(settings):
        return f"the AI model ({settings.llm.model}) isn't downloaded yet (Settings → AI)"
    return None
