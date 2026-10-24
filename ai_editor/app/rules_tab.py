"""The Rules tab (Phase 2H-2): your editing tips, as rules.

Type a tip, press Understand it: the local AI turns it into a rule, and
AI-Editor says back what it will do, in its own words, from the rule itself.
Where it applies can be changed before saving. Saved rules are listed with a
switch each; a newer rule wins over an older one it disagrees with.
"""

from __future__ import annotations

from dataclasses import asdict

import gradio as gr

from ..config import Settings
from ..db import init_db
from ..errors import AIEditorError, AiTooSlow
from ..rules import store
from ..rules.kinds import KINDS, VIDEOS, Rule
from . import library

RULE_COLUMNS = ["Rule", "On", "What it does", "Your words"]
VIDEO_CHOICES = [(label[0].upper() + label[1:], key) for key, label in VIDEOS.items()]
INTRO = ("Write an editing tip the way you'd say it, like *\"Keep League highlight clips under "
         "20 seconds\"*, *\"Dawnwalker parts about 40 minutes\"* or *\"Never use clips where I "
         "die\"*. The local AI turns it into "
         "a rule and AI-Editor tells you exactly what it will do; nothing is saved until you "
         "press Save. Rules apply by themselves to every new video they match, and win over "
         "the style profile. They never switch effects or captions on: you tick those in "
         "Review. A tip AI-Editor can't act on yet is kept as a 📝 note.")


def rows(saved: list[store.Saved]) -> list[list[str]]:
    over = store.clashes(saved)
    out = []
    for s in reversed(saved):            # newest first
        said = s.rule.said()
        if s.rule_id in over:
            said += f" ⚠ {over[s.rule_id]} (newer) says otherwise, so that one wins."
        out.append([s.rule_id, "✅ On" if s.enabled else "⬜ Off", said, s.tip])
    return out


def choices(saved: list[store.Saved]) -> list[tuple[str, str]]:
    return [(f"{s.rule_id} · {s.rule.said()[:70]}", s.rule_id) for s in reversed(saved)]


def build(settings: Settings) -> None:
    """Add the tab. Call inside the window's gr.Tabs()."""

    def read(fn, *args, **kwargs):
        conn = init_db(settings.db_path)
        try:
            return fn(conn, *args, **kwargs)
        finally:
            conn.close()

    with gr.Tab("Rules", id="rules") as tab:
        gr.Markdown(INTRO)
        with gr.Row():
            tip = gr.Textbox(label="Your tip", lines=2, scale=5,
                             placeholder="e.g. No teaser in League highlights")
            understand_btn = gr.Button("Understand it", variant="primary", scale=1)
        understood = gr.Markdown()
        with gr.Column(visible=False) as check:
            gr.Markdown("Where it applies (change it if the AI got it wrong; empty means "
                        "everywhere):")
            with gr.Row():
                games = gr.Dropdown(choices=read(library.game_choices), value=[],
                                    multiselect=True, allow_custom_value=True,
                                    label="For these games", scale=3)
                videos = gr.CheckboxGroup(VIDEO_CHOICES, value=[], label="For these videos",
                                          scale=2)
            with gr.Row():
                save_btn = gr.Button("Save", variant="primary")
                again_btn = gr.Button("Try again")
        pending = gr.State(None)
        gr.Markdown("### Your rules")
        table = gr.Dataframe(headers=RULE_COLUMNS, value=read(lambda c: rows(store.every(c))),
                             interactive=False, wrap=True, max_height=420,
                             column_widths=["7%", "6%", "52%", "35%"])
        with gr.Row():
            pick = gr.Dropdown(choices=read(lambda c: choices(store.every(c))), value=None,
                               label="Rule", scale=4)
            # The creator, 19 Oct: a toggle, "so I know if the rule is on".
            enabled = gr.Checkbox(False, label="On", interactive=False, scale=1,
                                  info="Untick to make new videos without it.")
            delete_btn = gr.Button("Delete", size="sm", variant="stop", scale=1)
        with gr.Row(visible=False) as confirm_row:
            gr.Markdown("Delete this rule? Videos already made with it keep it.")
            yes_btn = gr.Button("Yes, delete it", variant="stop", size="sm")
            keep_btn = gr.Button("Keep it", size="sm")
        msg = gr.Markdown()

    def listing():
        saved = read(store.every)
        return rows(saved), gr.update(choices=choices(saved), value=None)

    def understand_tip(text):
        from ..rules.understand import understand
        from ..style import notes
        from .tasks import _try_start

        hidden = (gr.update(visible=False), gr.skip(), gr.skip(), None)
        if not (text or "").strip():
            return ("Write a tip first.", *hidden)
        why_not = notes.available(settings, _try_start)
        if why_not:
            return (f"The AI can't read it right now: {why_not}.", *hidden)
        known = read(library.game_choices)
        try:
            result = understand(settings, text, known)
        except AiTooSlow:
            return ("The AI was far too slow, which usually means a game is using the graphics "
                    "card. Try again when you're not playing.", *hidden)
        except AIEditorError as exc:
            return (exc.user_message(), *hidden)
        rule = result.rule
        if not result.savable:
            return (f"**{result.message}**", *hidden)
        said = f"**AI-Editor will:** {result.message}" if not rule.is_note else \
            f"**{result.message}**\n\n{rule.said()}"
        return (said, gr.update(visible=True), gr.update(choices=known, value=rule.games),
                gr.update(value=rule.videos), asdict(rule))

    def rescope(rule, game_list, video_list):
        """Where it applies, changed by hand: say it again."""
        if not rule:
            return gr.skip(), rule
        rule = {**rule, "games": list(game_list or []), "videos": list(video_list or [])}
        r = Rule(**rule)
        if not r.is_note and r.videos and not set(r.videos) & set(KINDS[r.kind].videos):
            allowed = " and ".join(VIDEOS[v] for v in KINDS[r.kind].videos)
            return f"That rule only works on {allowed}: tick one of those.", rule
        return (f"**AI-Editor will:** {r.said()}" if not r.is_note else r.said()), rule

    def save(text, rule):
        if not rule:
            return gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), None, \
                "Press Understand it first."
        r = Rule(**rule)
        if not r.is_note and r.videos and not set(r.videos) & set(KINDS[r.kind].videos):
            return gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), rule, \
                "Tick a kind of video that rule works on first."
        rule_id = read(store.add, text, r)
        table_rows, pick_update = listing()
        return (table_rows, pick_update, "", gr.update(visible=False), "", None,
                f"Saved as {rule_id}. New videos it matches use it from now on.")

    def picked(rule_id):
        """The tick box shows the picked rule's state."""
        found = read(store.get, rule_id) if rule_id else None
        if found is None:
            return gr.update(value=False, interactive=False)
        return gr.update(value=found.enabled, interactive=True)

    def toggle(rule_id, on):
        if not rule_id or read(store.get, rule_id) is None:
            return gr.skip(), "Pick a rule first."
        read(store.switch, rule_id, bool(on))
        state = "on" if on else "off: new videos are made without it"
        return rows(read(store.every)), f"{rule_id} is {state}."

    def delete(rule_id):
        if not rule_id:
            return gr.skip(), gr.skip(), gr.update(visible=False), "Pick a rule first."
        read(store.delete, rule_id)
        table_rows, pick_update = listing()
        return table_rows, pick_update, gr.update(visible=False), f"{rule_id} deleted."

    understand_btn.click(understand_tip, tip, [understood, check, games, videos, pending])
    tip.submit(understand_tip, tip, [understood, check, games, videos, pending])
    games.input(rescope, [pending, games, videos], [understood, pending])
    videos.input(rescope, [pending, games, videos], [understood, pending])
    save_btn.click(save, [tip, pending], [table, pick, understood, check, tip, pending, msg])
    again_btn.click(lambda: ("", gr.update(visible=False), None, ""), None,
                    [understood, check, pending, msg])
    pick.change(picked, pick, enabled)
    enabled.input(toggle, [pick, enabled], [table, msg])
    delete_btn.click(lambda r: gr.update(visible=bool(r)), pick, confirm_row)
    keep_btn.click(lambda: gr.update(visible=False), None, confirm_row)
    yes_btn.click(delete, pick, [table, pick, confirm_row, msg])
    tab.select(listing, None, [table, pick])
