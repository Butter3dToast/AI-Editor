"""Review's finishing touches in the new design (Phase 4F-2), as JSON for the frame.

The tabs under the clip list: Captions (burned in or not, kept with the plan --
the creator, 1 Nov -- and fixing caption lines) and Effects & music (the effects,
each moment, between clips, the stream's music, a Short's layout, the effect
nudge). And Render: a panel to check what the video will have first, with Open
the finished video and Export to DaVinci Resolve (and a Let's Play's episode and
parts). Every change is the same as today's Review makes, one Undo step each;
effects and captions stay off unless the creator switches them on.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Here, not in add_routes: FastAPI reads the handlers' types by name from this
# module (4B: imported inside a function, Request wasn't found).
from fastapi import Body, Request
from fastapi.responses import JSONResponse

from ..config import Settings
from ..db import init_db
from ..errors import AIEditorError
from ..recipes import history
from ..recipes.plan import save_plan
from . import tasks, videos
from .worker import DONE, FAILED, RUNNING, WAITING, Worker

LAYOUTS = {"crop": "Zoomed centre", "fit": "Whole picture", "facecam_top": "Facecam on top"}


def captions_on(settings: Settings, plan) -> bool:
    """Burned in or not: this plan's own choice (4F-2), else the Settings' (off)."""
    chosen = (plan.source or {}).get("captions")
    if chosen is not None:
        return bool(chosen)
    return (settings.captions.lets_play if plan.recipe == "letsplay"
            else settings.shorts.captions if plan.recipe == "shorts"
            else settings.captions.highlights)


def music_on(settings: Settings, plan) -> bool:
    return bool((plan.source or {}).get("music", settings.render.include_stream_music))


def _suggesting(settings: Settings, plan) -> bool:
    from ..style.apply import styled

    return plan.recipe != "letsplay" and styled(settings, plan).effects.suggest   # 2H-2


def finishing(conn, settings: Settings, plan_id: str) -> dict | None:
    """What the Captions and Effects & music tabs show for a plan."""
    from ..effects import LABELS, moments, suggestions, switches
    from ..render.final import vertical_of
    from ..render.slide import between

    plan, _ = videos.get_plan(conn, plan_id)
    if plan is None:
        return None
    on = switches(settings, plan)
    if _suggesting(settings, plan):
        found = suggestions(conn, settings, plan)
        each = {"suggested": True, "items": [{"key": s.key, "label": s.label, "on": s.on}
                                             for s in found]}
    else:
        off = set((plan.source or {}).get("effects_off", []))
        found = moments(conn, settings, plan) if plan.recipe != "letsplay" else []
        each = {"suggested": False, "items": [{"key": k, "label": label, "on": k not in off}
                                              for label, k in found]}
    layout = None
    if plan.recipe == "shorts":
        names = dict(LAYOUTS)
        if plan.game not in settings.shorts.facecam:
            names.pop("facecam_top")
        layout = {"value": vertical_of(settings, plan).layout,
                  "choices": [[k, v] for k, v in names.items()]}
    return {
        "captions": captions_on(settings, plan),
        "effects": [{"key": k, "label": LABELS[k], "on": k in on} for k in LABELS],
        "each": each,
        "between": between(settings, plan) if plan.recipe == "highlights" else None,
        "music": music_on(settings, plan),
        "layout": layout,
        "nudge": nudge(conn, settings),
        "lets_play": plan.recipe == "letsplay",
    }


def nudge(conn, settings: Settings) -> dict | None:
    """'In your last 5 videos AI-Editor suggested flashes 24 times, and you used 2.'"""
    from ..learning.nudges import PLURALS, effect_nudge

    found = effect_nudge(conn, settings)
    if found is None:
        return None
    return {"kind": found.kind, "text": found.text.replace("**", ""),
            "biggest": found.kind not in settings.effects.only_biggest,
            "never": f"Stop suggesting {PLURALS[found.kind]}"}


# --- changes: one Undo step each, as in today's Review ------------------------------------


def _log_ticks(conn, plan, before, after, where, labels) -> None:
    """Each effect ticked or unticked, for learning (3A-1); undone with the change."""
    from ..recipes.review import log_feedback

    for action, keys in (("effect_on", set(after) - set(before)),
                         ("effect_off", set(before) - set(after))):
        for key in sorted(keys):
            log_feedback(conn, action, plan, None, effect=key, where=where,
                         label=labels.get(key, key))


def change(settings: Settings, plan_id: str, what: str, value) -> str:
    """captions, effects, each, between, music or layout: the plan's own choice."""
    from ..effects import (LABELS, KINDS, for_plan, moments, set_moments_on, set_switches,
                           suggestions, summary, switches, use_suggestions)

    conn = init_db(settings.db_path)
    try:
        plan, status = videos.get_plan(conn, plan_id)
        if plan is None:
            return "Pick a plan first."
        if what == "captions":
            with history.step(conn, plan_id, "burned-in captions"):
                plan.source["captions"] = bool(value)
                save_plan(conn, plan, status)
            return ("Your words will be burned into this video." if value
                    else "No burned-in captions in this video.")
        if what == "music":
            with history.step(conn, plan_id, "music from your stream"):
                plan.source["music"] = bool(value)
                save_plan(conn, plan, status)
            return ("The music from your stream will be in this video, kept under the talking."
                    if value else "No music from your stream in this video.")
        if what == "between":
            if plan.recipe != "highlights" or value not in ("cut", "slide"):
                return "Between clips is for highlight videos."
            with history.step(conn, plan_id, "between clips"):
                plan.source["between"] = value
                save_plan(conn, plan, status)
            return ("Each clip slides in over the last. Make a quick preview to see it."
                    if value == "slide" else "Hard cuts between clips.")
        if what == "layout":
            if plan.recipe != "shorts" or value not in LAYOUTS:
                return "The layout is for Shorts."
            with history.step(conn, plan_id, "the Short's layout"):
                plan.source["layout"] = value
                save_plan(conn, plan, status)
            return f"This Short will use {LAYOUTS[value]}. Make a quick preview to see it."
        if what == "effects":
            chosen = [k for k in KINDS if k in (value or [])]
            with history.step(conn, plan_id, "the effects"):
                before = switches(settings, plan)
                set_switches(plan, chosen)
                save_plan(conn, plan, status)
                _log_ticks(conn, plan, before, chosen, "video", LABELS)
            if not chosen:
                return "No effects in this video."
            return (f"Effects in this video: {', '.join(LABELS[k] for k in chosen)}. Make a "
                    "quick preview to see and hear them.")
        if what == "each":
            kept = list(value or [])
            if _suggesting(settings, plan):
                with history.step(conn, plan_id, "the suggested effects"):
                    found = suggestions(conn, settings, plan)
                    use_suggestions(conn, settings, plan, kept)
                    save_plan(conn, plan, status)
                    _log_ticks(conn, plan, [s.key for s in found if s.on], kept, "moment",
                               {s.key: s.label for s in found})
                if not kept:
                    return "No effects in this video."
                return (f"{len(kept)} moment{'s' if len(kept) != 1 else ''} with effects: "
                        f"{summary(for_plan(conn, settings, plan))}. Make a quick preview to "
                        "see and hear them.")
            listed = moments(conn, settings, plan)
            every = [k for _, k in listed]
            with history.step(conn, plan_id, "each effect's ticks"):
                off = set((plan.source or {}).get("effects_off", []))
                set_moments_on(plan, every, kept)
                save_plan(conn, plan, status)
                _log_ticks(conn, plan, [k for k in every if k not in off],
                           [k for k in kept if k in every], "moment",
                           {k: label for label, k in listed})
            left = len(every) - len(set(kept) & set(every))
            return (f"{len(every) - left} of {len(every)} moments keep their effects. Make a "
                    "quick preview to see and hear them.")
        return "That isn't something Review can change."
    finally:
        conn.close()


def answer_nudge(settings: Settings, kind: str, choice: str) -> str:
    """Only on the biggest moments / stop suggesting it / keep as is (3A-3a)."""
    from ..learning.nudges import answer
    from .manage_tabs import apply

    if choice not in ("biggest", "never", "keep"):
        return "That isn't an answer."
    conn = init_db(settings.db_path)
    try:
        said, new = answer(conn, settings, kind, choice)
    except AIEditorError as exc:
        return f"Not saved: {exc.user_message()}"
    finally:
        conn.close()
    apply(settings, new)
    return said.replace("**", "")


# --- caption lines (Phase 2D-2) ------------------------------------------------------------


def _segment(conn, plan_id: str, index: int):
    plan, _ = videos.get_plan(conn, plan_id)
    if plan is None or plan.recipe == "letsplay" or not 0 <= index < len(plan.segments):
        return None, None
    s = plan.segments[index]
    return s, ("the teaser" if s.kind == "teaser" else f"clip {index + 1}")


def caption_lines(conn, plan_id: str, index: int) -> dict | None:
    """The clip's lines: where each is in the clip, ✎ fixed, ⊘ hidden, 👥 a friend."""
    from ..analysis import caption_edit

    s, what = _segment(conn, plan_id, index)
    if s is None:
        return None
    found = caption_edit.lines(conn, s.recording_id, s.src_in, s.src_out)
    return {"what": what, "rid": s.recording_id, "lines": [{
        "key": ln.key, "text": ln.text, "hidden": ln.hidden, "edited": ln.edited,
        "friend": ln.friend, "start": ln.start, "end": ln.end,
        "at": videos.short_clock(max(0.0, ln.start - s.src_in)),
    } for ln in found]}


def line_change(settings: Settings, plan_id: str, index: int, key: str, action: str,
                text: str = "") -> dict:
    """Save, hide or show, put back: one Undo step, the fix everywhere the moment is used."""
    from ..analysis import caption_edit

    conn = init_db(settings.db_path)
    try:
        s, what = _segment(conn, plan_id, index)
        line = None
        if s is not None:
            line = next((ln for ln in caption_edit.lines(conn, s.recording_id, s.src_in,
                                                         s.src_out) if ln.key == key), None)
        if line is None:
            return {"said": "Click a caption line first."}
        if action not in ("save", "hide", "back"):
            return {"said": "That isn't something a caption line can do."}
        label = {"save": f"fixing a caption in {what}",
                 "hide": (f"showing a caption line in {what}" if line.hidden
                          else f"hiding a caption line in {what}"),
                 "back": f"putting back a caption line in {what}"}[action]
        offer = None
        with history.step(conn, plan_id, label, words=(s.recording_id, line.first, line.last)):
            if action == "save":
                saved = caption_edit.save_line(conn, s.recording_id, line.first, line.last,
                                               text or "")
                said, offer = saved.message, saved.offer
            elif action == "hide":
                caption_edit.hide_line(conn, s.recording_id, line.first, line.last,
                                       not line.hidden)
                said = ("Shown in captions again." if line.hidden else
                        "Hidden from captions. Its words stay in the transcript.")
            else:
                caption_edit.put_back(conn, s.recording_id, line.first, line.last)
                said = "Put back as it was first heard."
        out = {"said": said.replace("**", "")}
        if offer:
            out["offer"] = list(offer)
            out["offer_text"] = caption_edit.offer_text(conn, *offer).replace("**", "")
        return out
    finally:
        conn.close()


def remember_fix(settings: Settings, heard: str, meant: str) -> str:
    from ..analysis import caption_edit

    conn = init_db(settings.db_path)
    try:
        return caption_edit.remember(conn, heard, meant).replace("**", "")
    finally:
        conn.close()


# --- Render, Open, Export ---------------------------------------------------------------


def render_check(conn, settings: Settings, plan_id: str) -> dict | None:
    """The panel before rendering: what the video will have, and what's already made."""
    from ..effects import LABELS, switches
    from ..render.parts import episode_for, part_numbers
    from ..render.final import vertical_of
    from ..render.slide import between

    plan, status = videos.get_plan(conn, plan_id)
    if plan is None:
        return None
    lets_play = plan.recipe == "letsplay"
    on = [LABELS[k] for k in switches(settings, plan)]
    rows = [["Captions", "Burned in · your words" if captions_on(settings, plan) else "Off"],
            ["Music", "From your stream, under the talking" if music_on(settings, plan)
             else "None"],
            ["Effects", " · ".join(on) if on else "None"]]
    if plan.recipe == "highlights":
        rows.append(["Between clips", "Slide" if between(settings, plan) == "slide"
                     else "Hard cuts"])
    if plan.recipe == "shorts":
        rows.append(["Layout", LAYOUTS.get(vertical_of(settings, plan).layout, "-")])
    line = videos.timeline(conn, plan, settings)
    if lets_play:
        rows.append(["Length", f"{videos.short_clock(plan.total_sec)} in "
                               f"{len(part_numbers(plan))} parts"])
    elif plan.recipe == "shorts":
        rows.append(["Length", f"{line.total:.0f} s"])
    else:
        rows.append(["Length", f"{videos.short_clock(line.total)} (target "
                               f"{videos.short_clock(plan.target_sec)})"])
    episode, after = episode_for(conn, plan) if lets_play else (None, None)
    return {"title": plan.title, "rows": rows, "lets_play": lets_play,
            "episode": episode, "episode_after": after,
            "parts": part_numbers(plan) if lets_play else [],
            "shorts": plan.recipe == "shorts", "rendered": status == "approved"}


def remember_episode(settings: Settings, plan_id: str, episode) -> None:
    """A Let's Play keeps the episode typed for it, so Render and Publish always show
    the same one (1 Nov: the videos went out as EP 6, their upload text as EP 1)."""
    try:
        episode = int(episode) if episode not in (None, "") else None
    except (TypeError, ValueError):
        return
    if not episode or episode < 1:
        return
    conn = init_db(settings.db_path)
    try:
        plan, status = videos.get_plan(conn, plan_id)
        if plan is not None and plan.recipe == "letsplay"                 and (plan.source or {}).get("episode") != episode:
            plan.source = {**(plan.source or {}), "episode": episode}
            save_plan(conn, plan, status)
    finally:
        conn.close()


def _parts(part) -> list[int] | None:
    try:
        return [int(part)] if part not in (None, "", "all") else None
    except (TypeError, ValueError):
        return None


def render(settings: Settings, worker: Worker, plan_id: str, episode=None, part=None) -> dict:
    """The same job as today's Render, with the plan's own captions choice."""
    conn = init_db(settings.db_path)
    try:
        plan, _ = videos.get_plan(conn, plan_id)
    finally:
        conn.close()
    if plan is None:
        return {"said": "Pick a plan first."}
    try:
        episode = int(episode) if episode not in (None, "") else None
    except (TypeError, ValueError):
        return {"said": "The episode is a number, like 6."}
    if plan.recipe == "letsplay" and not episode:
        return {"said": "Fill in the episode number first."}
    remember_episode(settings, plan_id, episode)
    task = worker.submit(f"Rendering {plan.title}", f"render:{plan_id}",
                         tasks.render(settings, plan_id, captions=captions_on(settings, plan),
                                      episode=episode, parts=_parts(part)))
    if task is None:
        return {"said": "That video is already rendering, in Jobs."}
    ahead = sum(t.status in (WAITING, RUNNING) for t in worker.snapshot()) - 1
    return {"said": "Rendering: about 3 minutes per 10 minutes of video, in Jobs."
                    + ("" if plan.recipe == "letsplay" else " It marks the clips as used, so "
                       "the next video carries on with fresh ones.")
                    + (f" It starts after the {ahead} job{'s' if ahead != 1 else ''} ahead "
                       "of it." if ahead > 0 else ""), "job": task.id}


def finished(settings: Settings, plan, episode=None, part=None) -> list[Path]:
    """Where today's Review looks for the finished video(s)."""
    from ..render import parts as lp
    from ..render.final import video_path

    captions = captions_on(settings, plan)
    if plan.recipe != "letsplay":
        return [video_path(settings, plan, captions=captions)]
    if not episode:
        return []
    numbers = _parts(part) or lp.part_numbers(plan)
    return [lp.part_path(settings, plan, int(episode), n, captions=captions) for n in numbers]


def open_finished(settings: Settings, plan_id: str, episode=None, part=None) -> str:
    conn = init_db(settings.db_path)
    try:
        plan, _ = videos.get_plan(conn, plan_id)
    finally:
        conn.close()
    if plan is None:
        return "Pick a plan first."
    made = [p for p in finished(settings, plan, episode, part) if p.is_file()]
    if not made:
        return ("Not rendered yet" + (" with captions" if captions_on(settings, plan)
                                      else " without captions") + ". Press Render it first.")
    os.startfile(made[0])  # noqa: S606 -- the PC's video player, on our own file
    return f"Opened {made[0].name}" + (f" (and {len(made) - 1} more part(s) in the same "
                                       "folder)" if len(made) > 1 else "") + "."


def export(settings: Settings, plan_id: str, episode=None, part=None) -> str:
    from ..cli import clip_note
    from ..export.timeline import export_plan

    conn = init_db(settings.db_path)
    try:
        plan, _ = videos.get_plan(conn, plan_id)
        if plan is None:
            return "Pick a plan first."
        if plan.recipe == "shorts":
            return ("Shorts are finished here: the tall layout and captions don't carry over "
                    "to Resolve, so there's nothing to export (manual 19.2b). Render it instead.")
        if plan.recipe == "letsplay" and not episode:
            return "Fill in the episode number first."
        remember_episode(settings, plan_id, episode)
        result = export_plan(conn, settings, plan, episode=int(episode) if episode else None,
                             parts=_parts(part), note=clip_note)
    except AIEditorError as exc:
        return exc.user_message()
    finally:
        conn.close()
    subprocess.Popen(["explorer", "/select,", str(result.saved[0])])  # noqa: S603,S607
    said = (f"Saved {', '.join(p.name for p in result.saved)} (the folder is open). In DaVinci "
            "Resolve: File > Import > Timeline, and pick the .fcpxml (manual 19.3).")
    if result.missing:
        said += f" Resolve won't find {'; '.join(result.missing)}: relink it there."
    return said


def render_job(worker: Worker, job_id: int) -> dict:
    task = next((t for t in worker.snapshot() if t.id == job_id), None)
    if task is None:
        return {"state": "gone"}
    if task.status == DONE:
        return {"state": "ready"}
    if task.status == FAILED:
        return {"state": "failed", "error": task.error or "The render stopped."}
    return {"state": "waiting"}


# --- its addresses in the frame's server (frame_api.py) --------------------------------


def add_routes(app, frame, guarded) -> None:
    settings, worker = frame.settings, frame.worker
    no_cache = {"Cache-Control": "no-store"}

    def read(fn, *args, **kwargs):
        conn = init_db(settings.db_path)
        try:
            return fn(conn, *args, **kwargs)
        finally:
            conn.close()

    @app.get("/api/review/render-job/{job_id}")
    def rendered(job_id: int):
        return JSONResponse(render_job(worker, job_id), headers=no_cache)

    @app.post("/api/review/nudge")
    def nudged(request: Request, kind: str = Body(...), choice: str = Body(...)):
        guarded(request)
        return {"said": answer_nudge(settings, kind, choice)}

    @app.post("/api/review/remember")
    def remember(request: Request, heard: str = Body(...), meant: str = Body(...)):
        guarded(request)
        return {"said": remember_fix(settings, heard, meant)}

    @app.get("/api/review/{plan_id}/finishing")
    def finish(plan_id: str):
        return JSONResponse(read(finishing, settings, plan_id) or {}, headers=no_cache)

    @app.post("/api/review/{plan_id}/set")
    def set_one(plan_id: str, request: Request, what: str = Body(...), value=Body(None)):
        guarded(request)
        return {"said": change(settings, plan_id, what, value)}

    @app.get("/api/review/{plan_id}/lines/{index}")
    def lines(plan_id: str, index: int):
        return JSONResponse(read(caption_lines, plan_id, index) or {}, headers=no_cache)

    @app.post("/api/review/{plan_id}/line")
    def line(plan_id: str, request: Request, index: int = Body(...), key: str = Body(...),
             action: str = Body(...), text: str = Body("")):
        guarded(request)
        return line_change(settings, plan_id, index, key, action, text)

    @app.get("/api/review/{plan_id}/render")
    def check(plan_id: str):
        return JSONResponse(read(render_check, settings, plan_id) or {}, headers=no_cache)

    @app.post("/api/review/{plan_id}/episode")
    def episode_typed(plan_id: str, request: Request, episode=Body(None, embed=True)):
        guarded(request)
        remember_episode(settings, plan_id, episode)
        return {}

    @app.post("/api/review/{plan_id}/render")
    def start(plan_id: str, request: Request, episode=Body(None), part=Body(None)):
        guarded(request)
        return render(settings, worker, plan_id, episode, part)

    @app.post("/api/review/{plan_id}/open")
    def open_video(plan_id: str, request: Request, episode=Body(None), part=Body(None)):
        guarded(request)
        return {"said": open_finished(settings, plan_id, episode, part)}

    @app.post("/api/review/{plan_id}/export")
    def to_resolve(plan_id: str, request: Request, episode=Body(None), part=Body(None)):
        guarded(request)
        return {"said": export(settings, plan_id, episode, part)}
