"""The Style Profiles tab (Phase 2G-1).

What the creator chose (2026-10-11): references from YouTube links or files
on this PC; a profile sets pace and amounts but never switches an effect or
captions on; the local AI notes the techniques it sees. Using a profile when
making a video comes in 2G-2.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import gradio as gr

from ..analysis.captions import clock
from ..config import Settings
from ..db import init_db
from ..style import profiles
from ..style.profiles import RECIPES, SLIDERS, ProfileProblem
from . import library, tasks
from .worker import DONE, Worker, submitted

REF_COLUMNS = ["Video", "Length", "Cuts/min", "Silence left in", "Zooms/min",
               "Meme sounds/min", "Captions", "Teaser", "Status"]
INTRO = ("A style profile is an editing look, measured from videos whose editing you like: "
         "how fast the cuts are, how much silence is left in, zooms, sound effects, captions. "
         "Add 2-5 reference videos (a YouTube link, or a file on this PC), analyse them, then "
         "adjust the sliders and save. Only the measurements are kept: a downloaded video is "
         "deleted once it's measured, and your own files are only read. A profile never "
         "switches effects or captions on; it sets how often and how strong they are when you "
         "do. Choosing a profile when you make a video comes next (Phase 2G-2).")


def _num(x, unit: str = "") -> str:
    return "–" if x is None else f"{x:g}{unit}"


def reference_rows(profile: profiles.Profile | None) -> list[list[str]]:
    rows = []
    for r in profile.references if profile else []:
        m = r.measured
        if r.error and m is None:
            status = f"Problem: {r.error}"
        elif m is None:
            status = "Not measured yet"
        else:
            when = datetime.fromisoformat(r.analysed_at).astimezone().strftime("%d %b") \
                if r.analysed_at else ""
            status = f"Measured {when}" + (" (first 30 min)" if m.measured_sec < m.duration_sec
                                           else "")
        if m is None:
            rows.append([r.name, "", "", "", "", "", "", "", status])
            continue
        rows.append([
            r.name, clock(r.duration_sec) if r.duration_sec else "",
            _num(m.cuts_per_min), _num(m.dead_air_sec, " s"),
            _num(m.zooms_per_min), _num(m.sfx_per_min),
            f"{m.caption_share:.0%} of the time",
            _num(m.hook_sec, " s") if m.hook_sec else "none", status])
    return rows


def what_else(profile: profiles.Profile) -> str:
    """The measurements that aren't sliders, in a line per reference."""
    lines = []
    for r in profile.references:
        m = r.measured
        if m is None:
            continue
        sounds = ", ".join(f"{k} {n}" for k, n in m.sfx_kinds.items()) or "none"
        lines.append(f"- **{r.name}**: talking {m.speech_share:.0%} of the time; a shot lasts "
                     f"{_num(m.shot_sec, ' s')}; meme sounds heard: {sounds}"
                     + (" (a tall video)" if m.portrait else ""))
    return "\n".join(lines)


def slider_info(slider: profiles.Slider, profile: profiles.Profile | None) -> str:
    found = [slider.measured(m) for m in (profile.measured if profile else [])]
    found = [f"{v:.3g}" for v in found if v is not None]
    return slider.info + (f" Your references: {' · '.join(found)}." if found else "")


def notes_text(profile: profiles.Profile) -> str:
    if profile.notes:
        return "**What the AI noticed** (for you to read; it doesn't change any video):\n" + \
            "\n".join(f"- {n}" for n in profile.notes)
    if profile.measured:
        return "*No AI notes yet.*"
    return ""


def build(settings: Settings, worker: Worker, timer: gr.Timer) -> None:
    """Add the tab. Call inside the window's gr.Tabs()."""

    def read(fn, *args):
        conn = init_db(settings.db_path)
        try:
            return fn(conn, *args)
        finally:
            conn.close()

    first = (read(profiles.names) or [(None, None)])[0][1]

    with gr.Tab("Style Profiles", id="style") as tab:
        gr.Markdown(INTRO)
        with gr.Row():
            pick = gr.Dropdown(choices=read(profiles.names), value=first, label="Profile", scale=4)
            new_name = gr.Textbox(label="New profile", placeholder="e.g. League Highlights",
                                  scale=3)
            new_btn = gr.Button("Create", size="sm", scale=0, min_width=100)
        with gr.Column(visible=first is not None) as body:
            with gr.Row():
                games = gr.Dropdown(choices=read(library.game_choices), value=[],
                                    multiselect=True, allow_custom_value=True,
                                    label="For these games", scale=3)
                recipes = gr.CheckboxGroup(RECIPES, value=[], label="For these videos", scale=2)
            gr.Markdown("### Reference videos")
            refs_tbl = gr.Dataframe(headers=REF_COLUMNS, interactive=False, wrap=True,
                                    max_height=320,
                                    column_widths=["22%", "7%", "8%", "9%", "8%", "9%", "11%",
                                                   "7%", "19%"])
            with gr.Row():
                links = gr.Textbox(label="YouTube links, one per line", lines=2, scale=4,
                                   placeholder="https://www.youtube.com/watch?v=...")
                with gr.Column(scale=1, min_width=170):
                    add_links_btn = gr.Button("Add links", size="sm")
                    add_file_btn = gr.Button("Add a video file...", size="sm")
            with gr.Row():
                ref_pick = gr.Dropdown(choices=[], value=None, label="Reference", scale=4)
                remove_ref_btn = gr.Button("Take off the list", size="sm", scale=0,
                                           min_width=150)
            with gr.Row():
                again = gr.Checkbox(False, label="Measure them all again", scale=1)
                analyse_btn = gr.Button("Analyse references", variant="primary", scale=2)
            gr.Markdown("About 4-6 minutes per 10 minutes of video. The AI's notes come at the "
                        "end and use the graphics card, so run it when you're not playing.")
            gr.Markdown("### The profile")
            draft_note = gr.Markdown()
            sliders = {s.key: gr.Slider(s.minimum, s.maximum, step=s.step, label=s.label,
                                        info=s.info) for s in SLIDERS}
            ai_notes = gr.Markdown()
            more = gr.Markdown()
            with gr.Row():
                save_btn = gr.Button("Save profile", variant="primary")
                measured_btn = gr.Button("Back to the measured values")
            with gr.Accordion("Rename or delete", open=False):
                with gr.Row():
                    rename_box = gr.Textbox(label="New name", scale=4)
                    rename_btn = gr.Button("Rename", size="sm", scale=0, min_width=100)
                delete_btn = gr.Button("Delete this profile", variant="stop")
                with gr.Row(visible=False) as confirm_row:
                    gr.Markdown("Delete this profile and its measurements? Videos aren't "
                                "touched.")
                    yes_btn = gr.Button("Yes, delete it", variant="stop", size="sm")
                    keep_btn = gr.Button("Keep it", size="sm")
        msg = gr.Markdown()
        seen = gr.State(-1)
        handled = gr.State(0)

    view = [body, games, recipes, refs_tbl, ref_pick, draft_note, *sliders.values(), ai_notes,
            more, rename_box]

    def show(profile_id, *, values: dict | None = None):
        profile = read(profiles.load, profile_id)
        if profile is None:
            return (gr.update(visible=False), [], [], [], gr.update(choices=[], value=None), "",
                    *[gr.skip() for _ in SLIDERS], "", "", "")
        current = values or profile.current(settings)
        count = len(profile.measured)
        state = ("saved" if profile.values else
                 "not saved yet: showing what was measured" if count else
                 "not saved yet: showing your own settings until references are measured")
        note = (f"Measured from **{count} video{'s' if count != 1 else ''}**; {state}. "
                "The effects and captions themselves stay as you switch them: these set how "
                "often and how strong, and how captions look.")
        refs = [(r.name, r.id) for r in profile.references]
        return (gr.update(visible=True), profile.games, profile.recipes,
                reference_rows(profile), gr.update(choices=refs, value=None), note,
                *[gr.update(value=current[s.key], info=slider_info(s, profile)) for s in SLIDERS],
                notes_text(profile),
                ("**Also measured**\n" + what_else(profile)) if profile.measured else "",
                profile.name)

    def opened(profile_id):
        """The tab opened: the profiles as they are now, the one on show kept if it's still there."""
        found = read(profiles.names)
        ids = [i for _, i in found]
        chosen = profile_id if profile_id in ids else (ids[0] if ids else None)
        return (gr.update(choices=found, value=chosen), *show(chosen))

    tab.select(opened, pick, [pick, *view])
    pick.change(show, pick, view)

    def create(name):
        try:
            new_id = read(profiles.create, name)
        except ProfileProblem as exc:
            return gr.skip(), gr.skip(), str(exc)
        return gr.update(choices=read(profiles.names), value=new_id), "", \
            "Created. Now add 2-5 reference videos."

    new_btn.click(create, new_name, [pick, new_name, msg])

    def add_links(profile_id, text):
        if profile_id is None:
            return gr.skip(), "Create or pick a profile first."
        added, problems = [], []
        for line in (text or "").splitlines():
            if not line.strip():
                continue
            if not profiles.is_link(line):
                problems.append(f"{line.strip()} isn't a link (use Add a video file for files).")
                continue
            try:
                added.append(read(profiles.add_reference, int(profile_id), line))
            except ProfileProblem as exc:
                problems.append(str(exc))
        said = (f"Added {len(added)} link(s). " if added else "") + " ".join(problems)
        return ("" if added and not problems else gr.skip()), \
            (said or "Paste a YouTube link first.") + \
            (" Press Analyse references when they're all in." if added else "")

    add_links_btn.click(add_links, [pick, links], [links, msg]).then(show, pick, view)

    def add_file(profile_id):
        if profile_id is None:
            return "Create or pick a profile first."
        chosen = library.browse_for_video(settings.folders.output, "Pick a reference video")
        if not chosen:
            return gr.skip()
        try:
            shown = read(profiles.add_reference, int(profile_id), chosen)
        except ProfileProblem as exc:
            return str(exc)
        return f"Added {shown}. It's only read, never changed or deleted."

    add_file_btn.click(add_file, pick, msg).then(show, pick, view)

    def remove_ref(profile_id, reference_id):
        if reference_id is None:
            return "Pick the reference to take off the list."
        read(profiles.remove_reference, int(reference_id))
        return "Taken off the list (with what it measured)."

    remove_ref_btn.click(remove_ref, [pick, ref_pick], msg).then(show, pick, view)

    def analyse(profile_id, redo):
        if profile_id is None:
            return "Create or pick a profile first."
        profile = read(profiles.load, int(profile_id))
        if not profile.references:
            return "Add some reference videos first."
        return submitted(worker, worker.submit(
            f"Analysing the references of \"{profile.name}\"", f"style:{profile_id}",
            tasks.analyse_references(settings, int(profile_id), again=bool(redo))))

    analyse_btn.click(analyse, [pick, again], msg)

    def save(profile_id, game_list, recipe_list, *values):
        if profile_id is None:
            return "Create or pick a profile first."
        read(profiles.save, int(profile_id),
             games=game_list or [], recipes=recipe_list or [],
             values=dict(zip(sliders, values)))
        return "Saved."

    save_btn.click(save, [pick, games, recipes, *sliders.values()], msg).then(show, pick, view)

    def back_to_measured(profile_id):
        profile = read(profiles.load, profile_id)
        if profile is None:
            return (gr.skip(),) * len(SLIDERS) + ("",)
        values = profile.draft(settings)
        return (*[values[s.key] for s in SLIDERS],
                "Back to the measured values: Save profile to keep them."
                if profile.measured else "Back to your own settings (nothing measured yet).")

    measured_btn.click(back_to_measured, pick, [*sliders.values(), msg])

    def rename(profile_id, name):
        if profile_id is None:
            return gr.skip(), "Pick a profile first."
        try:
            read(profiles.rename, int(profile_id), name)
        except ProfileProblem as exc:
            return gr.skip(), str(exc)
        return gr.update(choices=read(profiles.names), value=profile_id), "Renamed."

    rename_btn.click(rename, [pick, rename_box], [pick, msg])

    delete_btn.click(lambda: gr.update(visible=True), None, confirm_row)
    keep_btn.click(lambda: gr.update(visible=False), None, confirm_row)

    def delete(profile_id):
        if profile_id is not None:
            read(profiles.delete, int(profile_id))
        left = read(profiles.names)
        return (gr.update(choices=left, value=left[0][1] if left else None),
                gr.update(visible=False), "Deleted.")

    yes_btn.click(delete, pick, [pick, confirm_row, msg]).then(show, pick, view)

    def tick(seen_version, done, profile_id):
        if worker.version == seen_version:
            return (gr.skip(),) * len(view) + (done, seen_version)
        finished = [t for t in worker.snapshot() if t.status == DONE and
                    "style_profile" in t.result and t.id > done]
        newest = max((t.id for t in finished), default=done)
        mine = any(t.result["style_profile"] == profile_id for t in finished)
        return (*(show(profile_id) if mine else (gr.skip(),) * len(view)), newest,
                worker.version)

    timer.tick(tick, [seen, handled, pick], [*view, handled, seen], show_progress="hidden")
