"""Your friends on Discord, by name (Phase 2I-2).

Library -> Who's talking: a stream's voices (Voice A, B...), each with a sample
to play and a name to give once. Settings -> Your friends: rename, recolour or
forget a friend. Only the creator names or forgets anyone; AI-Editor only
recognises a voice it has been told about.
"""

from __future__ import annotations

from pathlib import Path

import gradio as gr

from ..analysis import voices
from ..config import Settings
from ..db import init_db
from ..ffmpeg import run_ffmpeg
from ..ingest import recording_cache_dir

INTRO = ("Your friends on Discord, told apart by their voices. Play each voice and type a "
         "name once: AI-Editor then knows them in every stream, and captions say who's "
         "talking, in their own colour.")


def _read(settings: Settings, fn, *args):
    conn = init_db(settings.db_path)
    try:
        return fn(conn, *args)
    finally:
        conn.close()


def voice_choices(settings: Settings, recording_id) -> list[tuple[str, str]]:
    if recording_id is None:
        return []
    return [(v.said(), v.label) for v in _read(settings, voices.stream_voices, int(recording_id))]


def friend_names(settings: Settings) -> list[str]:
    return [f.name for f in _read(settings, voices.friends)]


def known_line(settings: Settings) -> str:
    names = friend_names(settings)
    return ("Your friends so far: " + ", ".join(f"**{n}**" for n in names)) if names else         "No friends named yet."


def sample(settings: Settings, recording_id: int, label: str) -> str | None:
    """A few seconds of the voice, from the Discord track, to play."""
    conn = init_db(settings.db_path)
    try:
        row = conn.execute("SELECT content_hash FROM recordings WHERE id = ?",
                           (recording_id,)).fetchone()
        voice = conn.execute("SELECT sample_start, sample_end FROM voices WHERE recording_id = ? "
                             "AND label = ?", (recording_id, label)).fetchone()
        chat = conn.execute("SELECT extracted_path FROM audio_tracks WHERE recording_id = ? AND "
                            "role = 'voice_chat'", (recording_id,)).fetchone()
    finally:
        conn.close()
    if row is None or voice is None or chat is None or not chat[0] or not Path(chat[0]).exists():
        return None
    folder = recording_cache_dir(settings, row[0]) / "analysis" / "voice samples"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"voice {label} {voice[0]:.1f}.wav"
    if not out.exists():
        run_ffmpeg(["-ss", f"{voice[0]:.2f}", "-t", f"{max(1.0, voice[1] - voice[0]):.2f}",
                    "-i", str(chat[0]), "-ac", "1", str(out)], what="cutting a voice sample")
    return str(out)


def build_library(settings: Settings, pick) -> None:
    """The Library's Who's talking box, for the recording picked there."""
    with gr.Accordion("Who's talking (your friends on Discord)", open=False):
        gr.Markdown(INTRO)
        with gr.Row():
            voice_pick = gr.Dropdown(choices=[], value=None, label="Voice", scale=3,
                                     info="The one who talks most is Voice A.")
            heard = gr.Audio(label="Their voice", type="filepath", interactive=False, scale=2)
        known = gr.Markdown(known_line(settings))
        with gr.Row():
            name_box = gr.Textbox(label="Who is it?", scale=3, max_lines=1,
                                  info="Their name. Someone you've named before: the same name, "
                                       "and this voice joins theirs.")
            name_btn = gr.Button("Save name", variant="primary", scale=0, min_width=120)
            not_btn = gr.Button("That's not them", scale=0, min_width=140)
        voice_msg = gr.Markdown()

    def listed(recording_id, keep=None):
        found = voice_choices(settings, recording_id)
        if recording_id is not None and not found:
            note = ("No voices to name in this stream yet. If friends were on Discord, click "
                    "**Analyse (or resume)**: it writes down their words and tells their voices "
                    "apart (a few minutes, only the new steps run).")
        else:
            note = ""
        value = keep if keep in [v for _, v in found] else (found[0][1] if found else None)
        return gr.update(choices=found, value=value), note

    def picked(recording_id, label):
        if recording_id is None or label is None:
            return None, ""
        current = next((v for v in _read(settings, voices.stream_voices, int(recording_id))
                        if v.label == label), None)
        named = current.friend.name if current and current.friend else ""
        return sample(settings, int(recording_id), label), named

    def save(recording_id, label, name):
        if recording_id is None or label is None:
            return gr.skip(), "Pick a recording and a voice first.", gr.skip()
        said = _read(settings, voices.name_voice, int(recording_id), label, name or "")
        return listed(recording_id, label)[0], said, known_line(settings)

    def not_them(recording_id, label):
        if recording_id is None or label is None:
            return gr.skip(), "Pick a recording and a voice first."
        said = _read(settings, voices.unname_voice, int(recording_id), label)
        return listed(recording_id, label)[0], said

    pick.change(listed, pick, [voice_pick, voice_msg])
    voice_pick.change(picked, [pick, voice_pick], [heard, name_box])
    name_btn.click(save, [pick, voice_pick, name_box], [voice_pick, voice_msg, known])
    name_box.submit(save, [pick, voice_pick, name_box], [voice_pick, voice_msg, known])
    not_btn.click(not_them, [pick, voice_pick], [voice_pick, voice_msg])


def build_settings(settings: Settings) -> None:
    """Settings -> Your friends: rename, recolour, forget."""
    def choices():
        return [(f"{f.name}", f.id) for f in _read(settings, voices.friends)]

    with gr.Accordion("Your friends (Discord)", open=False) as box:
        gr.Markdown("Friends you've named in **Library → Who's talking**. Their captions say "
                    "their name, in their colour.")
        with gr.Row():
            who = gr.Dropdown(choices=choices(), value=None, label="Friend", scale=2)
            new_name = gr.Textbox(label="Name", scale=2)
            colour = gr.ColorPicker(label="Caption colour", scale=1)
        with gr.Row():
            rename_btn = gr.Button("Save name", scale=0, min_width=120)
            colour_btn = gr.Button("Save colour", scale=0, min_width=120)
            forget_btn = gr.Button("Forget them", variant="stop", scale=0, min_width=120)
        with gr.Row(visible=False) as confirm:
            confirm_note = gr.Markdown()
            yes_btn = gr.Button("Yes, forget them", variant="stop", scale=0, min_width=150)
            no_btn = gr.Button("Keep them", scale=0, min_width=110)
        friend_msg = gr.Markdown()

    def shown(friend_id):
        found = next((f for f in _read(settings, voices.friends) if f.id == friend_id), None)
        if found is None:
            return "", None
        return found.name, found.colour

    def refreshed(keep=None):
        found = choices()
        return gr.update(choices=found, value=keep if keep in [i for _, i in found] else None)

    def do(fn, *args):
        def run(friend_id, *values):
            if friend_id is None:
                return gr.skip(), "Pick a friend first."
            said = _read(settings, fn, int(friend_id), *values)
            return refreshed(friend_id), said
        return run

    def ask(friend_id):
        if friend_id is None:
            return gr.Row(visible=False), ""
        name = shown(friend_id)[0]
        return gr.Row(visible=True), (f"**Forget {name}?** Their name, colour and voice go; their "
                                      "lines stay in captions, unnamed (light blue). You can "
                                      "name them again any time.")

    def forgotten(friend_id):
        said = _read(settings, voices.forget, int(friend_id)) if friend_id is not None else ""
        return gr.Row(visible=False), refreshed(), said

    box.expand(lambda keep: refreshed(keep), who, who)
    who.change(shown, who, [new_name, colour])
    rename_btn.click(do(voices.rename), [who, new_name], [who, friend_msg])
    colour_btn.click(do(voices.recolour), [who, colour], [who, friend_msg])
    forget_btn.click(ask, who, [confirm, confirm_note])
    no_btn.click(lambda: gr.Row(visible=False), None, confirm)
    yes_btn.click(forgotten, who, [confirm, who, friend_msg])
