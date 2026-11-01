"""The Review screen in the new design (Phase 4F-1: editing the cut), as JSON for the frame.

The designer's Review (mockups/Review.dc.html): the clip on a stage with its trim
buttons and details, pinned at the top while the rest scrolls (as Clips, the
creator's choice, 1 Nov); the length bar against the target; the clip list, with
tabs beside it for what comes in 4F-2 and 4F-3 (captions, effects and music,
publishing, a Let's Play's parts). Until those are built, "Today's Review" opens
today's screen inside the window on the same plan.

Every change goes through the same code as today's Review (recipes.review, one
undo step each in recipes.history), so what AI-Editor learns from it is the
same. Today's Review keeps working as it is in the browser.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

# Here, not in add_routes: FastAPI reads the handlers' types by name from this
# module (4B: imported inside a function, Request wasn't found).
from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse

from ..analysis import fights
from ..analysis.captions import clock
from ..config import Settings
from ..db import init_db
from ..errors import AIEditorError
from ..recipes import history, review
from ..recipes.plan import APPROVED, EditPlan, save_plan
from ..style.apply import styled
from . import tasks, videos
from .worker import DONE, FAILED, RUNNING, WAITING, Worker

EFFECTS = {"flash": "Flash", "shake": "Screen shake", "sfx": "Sound effects",
           "zoom": "Punch-in zoom", "replay": "Slow-motion replay"}


def file_url(path: Path) -> str:
    """Where the window plays a file from AI-Editor's own cache or output folder."""
    return (f"/classic/gradio_api/file={quote(path.as_posix(), safe='/:')}"
            f"?v={path.stat().st_mtime_ns}")


def plans(conn) -> list[dict]:
    """Every plan, newest first, as today's Video plan box lists them."""
    statuses = videos.plan_statuses(conn)
    return [{"id": pid, "label": label, "status": statuses.get(pid, "draft")}
            for label, pid in videos.plan_choices(conn)]


def bar(conn, plan: EditPlan, settings: Settings) -> dict:
    """The length bar (review_list.length_bar), as data: each block's share of the
    bar, the target line, and the line above it."""
    if plan.recipe == "letsplay":
        numbers = sorted({s.part for s in plan.segments if s.part is not None})
        lengths = [sum(s.length for s in plan.segments if s.part == n) for n in numbers]
        total = sum(lengths) or 1.0
        low, high = settings.lets_play.normal_range_min
        off = any(not low * 60 <= sec <= high * 60 for sec in lengths)
        return {"blocks": [{"row": i, "kind": f"c{i % 2}", "label": f"Part {n}",
                            "title": f"Part {n} · {videos.short_clock(sec)}",
                            "width": sec / total * 100}
                           for i, (n, sec) in enumerate(zip(numbers, lengths))],
                "target": None, "tone": "under" if off else "ok",
                "strong": f"{len(numbers)} part{'s' if len(numbers) != 1 else ''}",
                "rest": ": " + " · ".join(videos.short_clock(s) for s in lengths)
                        + f" (aim for {low:.0f}-{high:.0f} min each)"}
    line = videos.timeline(conn, plan, settings)
    total = line.total
    if plan.recipe == "shorts":
        goal = settings.shorts.max_length_sec
        tone = "over" if total > goal + 0.5 else "ok"
        strong, rest = f"{total:.0f} s", (f" of the {goal:.0f} s most a Short can be"
                                         if tone == "ok" else
                                         f": over the {goal:.0f} s a Short can be. "
                                         "Trim a clip to shorten it.")
    else:
        goal = plan.target_sec
        tone = "ok" if total + 0.5 >= goal else "under"
        strong = videos.short_clock(total)
        rest = (f" long · over your {videos.short_clock(goal)} target ✓" if tone == "ok" else
                f" long · {videos.short_clock(goal - total)} under your "
                f"{videos.short_clock(goal)} target")
    scale = max(total, goal) or 1.0
    blocks, number = [], 0
    for n, s in enumerate(plan.segments):
        sec = (line.starts[n + 1] - line.starts[n]) if n + 1 < len(plan.segments) \
            else line.lengths[n]
        teaser = s.kind == "teaser"
        number += 0 if teaser else 1
        blocks.append({
            "row": n, "width": max(0.0, sec) / scale * 100,
            "kind": "teaser" if teaser else "replay" if line.replays[n] else f"c{number % 2}",
            "label": "T" if teaser else str(n + 1),
            "title": (("Teaser" if teaser else f"#{n + 1}")
                      + f" · at {videos.short_clock(line.starts[n])} · {line.lengths[n]:.0f} s"
                      + (" with a slow-motion replay" if line.replays[n] else "")),
        })
    return {"blocks": blocks, "target": min(100.0, goal / scale * 100), "tone": tone,
            "strong": strong, "rest": rest}


def _games(conn) -> dict[int, str]:
    return {r["id"]: r["game"] or "" for r in conn.execute("SELECT id, game FROM recordings")}


def rows(conn, plan: EditPlan, settings: Settings) -> list[dict]:
    """The list: # · From · At · Length · Why it's in (review_list.clip_rows' facts)."""
    if plan.recipe == "letsplay":
        return [{"n": i, "label": f"Part {r[0]}", "length": r[1], "at": r[2], "why": r[3],
                 "from": "", "day": "", "teaser": False}
                for i, r in enumerate(videos.part_table(plan))]
    days, games = videos.recorded_days(conn), _games(conn)
    own = styled(settings, plan)   # its rules may switch the fight check off (2H-1)
    out = []
    for n, s in enumerate(plan.segments):
        teaser = s.kind == "teaser"
        said = videos.why(s.reasons)
        cut_off = None if teaser else fights.missed(conn, own, s.recording_id, s.src_in)
        if cut_off is not None:
            far = cut_off >= settings.clips.fight_extend_sec - 1
            gone = f"{settings.clips.fight_extend_sec:.0f}+" if far else f"{cut_off:.0f}"
            said = f"⚠ starts mid-fight ({gone} s already gone) · {said}"
        out.append({"n": n, "label": "T" if teaser else str(n + 1), "teaser": teaser,
                    "from": s.game or games.get(s.recording_id) or f"#{s.recording_id}",
                    "day": days.get(s.recording_id, ""), "at": clock(s.src_in),
                    "length": f"{s.length:.0f} s",
                    "why": ("Teaser · " + said) if teaser else said})
    return out


def preview(settings: Settings, plan: EditPlan, part: int | None = None) -> dict | None:
    """The quick preview already made (videos.last_preview), to play: its address and
    whether the plan has changed since."""
    path = videos.preview_file(settings, plan, part)
    if not path.is_file():
        return None
    import json
    from datetime import datetime

    made = datetime.fromtimestamp(path.stat().st_mtime)
    note = f"Your quick preview from {made.day} {made:%b, %H:%M}."
    try:
        kept = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))["fingerprint"]
        if kept != videos.shown_in_preview(settings, plan, part):
            note += " The plan has changed since: make a new one to see the changes."
    except (OSError, ValueError, KeyError):
        pass
    return {"url": file_url(path), "note": note}


def captions_default(settings: Settings, plan: EditPlan) -> bool:
    """Burned in or not: the plan's own choice (4F-2), else the Settings' (off)."""
    from .review_finish import captions_on

    return captions_on(settings, plan)


def screen(conn, settings: Settings, plan_id: str | None) -> dict:
    """Everything Review shows for one plan (the newest when none is asked for)."""
    every = plans(conn)
    if not every:
        return {"plans": [], "plan": None}
    if plan_id not in {p["id"] for p in every}:
        plan_id = every[0]["id"]
    plan, status = videos.get_plan(conn, plan_id)
    back, again = history.can(conn, plan_id)
    from ..effects import switches
    from ..rules.store import summary as rules_summary
    from ..style.apply import summary as style_summary

    clips = sum(s.kind != "teaser" for s in plan.segments)
    length = (f"{plan.total_sec:.0f} s" if plan.recipe == "shorts"
              else videos.short_clock(plan.total_sec))
    lets_play = plan.recipe == "letsplay"
    parts = len({s.part for s in plan.segments if s.part}) if lets_play else 0
    return {
        "plans": every,
        "plan": {
            "id": plan.plan_id, "title": plan.title, "recipe": plan.recipe,
            "kind": videos.kind_of(plan), "rendered": status == APPROVED,
            "line": " · ".join([("Rendered" if status == APPROVED else "Draft"),
                                f"{parts} part{'s' if parts != 1 else ''}" if lets_play
                                else f"{clips} clip{'s' if clips != 1 else ''}", length]),
            "notes": [n for n in (style_summary(plan), rules_summary(plan)) if n]
                     + list(plan.notes),
            "editable": plan.recipe == "highlights",
            "captions": captions_default(settings, plan),
            "effects": [EFFECTS[k] for k in switches(settings, plan) if k in EFFECTS],
        },
        "bar": bar(conn, plan, settings), "rows": rows(conn, plan, settings),
        "undo": back, "redo": again,
        "preview": None if lets_play else preview(settings, plan),
    }


def clip(conn, settings: Settings, plan_id: str, index: int) -> dict | None:
    """One row: where it plays from, and its details beside the player."""
    plan, _ = videos.get_plan(conn, plan_id)
    if plan is None:
        return None
    if plan.recipe == "letsplay":
        numbers = sorted({s.part for s in plan.segments if s.part})
        if not 0 <= index < len(numbers):
            return None
        pieces = [s for s in plan.segments if s.part == numbers[index]]
        first = pieces[0]
        proxy = videos.proxy_of(conn, first.recording_id)
        return {"index": index, "part": numbers[index], "rid": first.recording_id,
                "start": first.src_in, "end": first.src_out,
                "video": file_url(proxy) if proxy and proxy.is_file() else "",
                "facts": [["Part", str(numbers[index])],
                          ["Length", videos.short_clock(sum(s.length for s in pieces))],
                          ["In the recording", f"{clock(first.src_in)}–{clock(pieces[-1].src_out)}"],
                          ["Plays", "Its start, up to its first cut"]]}
    if not 0 <= index < len(plan.segments):
        return None
    s = plan.segments[index]
    days, games = videos.recorded_days(conn), _games(conn)
    line = videos.timeline(conn, plan, settings)
    proxy = videos.proxy_of(conn, s.recording_id)
    teaser = s.kind == "teaser"
    from ..effects import switches

    on = [EFFECTS[k] for k in switches(settings, plan) if k in EFFECTS]
    return {
        "index": index, "teaser": teaser, "rid": s.recording_id, "clip": s.clip_id,
        "start": s.src_in, "end": s.src_out,
        "video": file_url(proxy) if proxy and proxy.is_file() else "",
        "facts": [
            ["From", ", ".join(x for x in (s.game or games.get(s.recording_id) or
                                            f"#{s.recording_id}", days.get(s.recording_id))
                               if x)],
            ["Starts", clock(s.src_in)], ["Ends", clock(s.src_out)],
            ["Length", f"{s.length:.1f} s"],
            ["In the video", "Opens it (teaser)" if teaser
             else f"at {videos.short_clock(line.starts[index])}"],
            ["Why it's in", videos.why(s.reasons)],
            ["Captions", ("On · your words" if s.captions else "Hidden for this clip")
             if captions_default(settings, plan) else "Off"],
            ["Effects", " · ".join(on) if on else "Off"],
        ],
    }


# --- changes: the same as today's Review's buttons ---------------------------------------


WHAT = {"add": "adding a clip", "sort": "sorting by time"}


def edit(settings: Settings, plan_id: str, action: str, index: int | None,
         extra=None) -> dict:
    """Remove, teaser, moment teaser, move to #, sort by time, add a clip: one undo
    step each. {"said", "selected"}: what happened, and the row to keep picked."""
    conn = init_db(settings.db_path)
    try:
        plan, status = videos.get_plan(conn, plan_id)
        if plan is None or plan.recipe != "highlights":
            return {"said": "Only a highlight video's clips can be changed like this."}
        moment = None
        if action == "moment":
            from ..cli import _moment_in

            found = _moment_in(plan, str(extra or ""), settings)
            if found is None:
                return {"said": "That time isn't inside one clip of this plan. Write it like "
                                "6:36-6:42, or 6:36."}
            clip_id, moment = found
            index = next((n for n, s in enumerate(plan.segments)
                          if s.clip_id == clip_id and s.kind != "teaser"), None)
        if action in ("add", "sort"):
            index = 0
            if action == "add" and not extra:
                return {"said": "Pick a clip to add first."}
        if action == "move_to":
            try:
                extra = int(extra)
            except (TypeError, ValueError):
                return {"said": "Type the number to move it to first."}
        if action not in ("remove", "teaser", "moment", "move_to", "add", "sort"):
            return {"said": "That isn't something Review can do."}
        if index is None or not 0 <= index < len(plan.segments):
            return {"said": "Click a clip in the list first."}
        number = index + 1
        teaser = plan.segments[index].kind == "teaser"
        what = WHAT.get(action) or {
            "move_to": f"moving clip {number} to #{extra}",
            "remove": "removing the teaser" if teaser else f"removing clip {number}",
        }.get(action, "choosing the teaser")
        selected = None
        with history.step(conn, plan_id, what):
            if action == "add":
                change = review.add(conn, settings, plan, str(extra))
            elif action == "sort":
                change = review.sort_by_time(conn, plan)
            elif action == "move_to":
                change = review.move_to(conn, plan, index, extra)
                if change.message.startswith("Moved to #"):
                    selected = int(change.message.removeprefix("Moved to #").rstrip(".")) - 1
            elif action == "remove":
                change = review.remove(conn, settings, plan, index)
                selected = min(index, len(change.plan.segments) - 1)
            else:
                change = review.use_as_teaser(conn, settings, plan, index, moment)
            save_plan(conn, change.plan, status)
        return {"said": change.message, "selected": selected}
    except AIEditorError as exc:
        return {"said": exc.user_message()}
    finally:
        conn.close()


def save_cut(settings: Settings, plan_id: str, cut: dict) -> dict:
    """A clip's new start and end (today's Adjust the cut): snapped between words, the
    library's clip re-cut too, one undo step."""
    try:
        start, end = float(cut["start"]), float(cut["end"])
        was = [float(cut["was"][0]), float(cut["was"][1])]
        rid = int(cut["rid"])
    except (KeyError, TypeError, ValueError, IndexError):
        return {"said": "Click a clip in the list first."}
    if end - start < 1.0:
        return {"said": "The end must be after the start."}
    if abs(start - was[0]) < 0.05 and abs(end - was[1]) < 0.05:
        return {"said": "Nothing to save: that's the cut it already has."}
    conn = init_db(settings.db_path)
    try:
        plan, status = videos.get_plan(conn, plan_id)
        if plan is None or plan.recipe == "letsplay":
            return {"said": "A Let's Play's parts are changed in the Part Planner."}
        # The clip may have moved in the list since it was clicked: find it again.
        index = next((n for n, s in enumerate(plan.segments)
                      if s.recording_id == rid and abs(s.src_in - was[0]) < 0.01
                      and abs(s.src_out - was[1]) < 0.01), None)
        if index is None:
            return {"said": "That clip has changed since you clicked it: click it again."}
        segment = plan.segments[index]
        what = "the teaser's cut" if segment.kind == "teaser" else f"clip {index + 1}'s cut"
        with history.step(conn, plan_id, f"adjusting {what}", clips=[segment.clip_id]):
            change = review.adjust(conn, settings, plan, index, start, end)
            now = change.plan.segments[index]
            if now.src_in == was[0] and now.src_out == was[1]:
                return {"said": change.message, "selected": index}
            save_plan(conn, change.plan, status)
        return {"said": change.message, "selected": index}
    finally:
        conn.close()


def step(settings: Settings, plan_id: str, back: bool) -> str:
    conn = init_db(settings.db_path)
    try:
        return (history.undo if back else history.redo)(conn, plan_id)
    finally:
        conn.close()


def addable(conn, settings: Settings, plan_id: str) -> list[dict]:
    """Clips that could go in (review.addable): 🔖 and 👍 first, then the best."""
    plan, _ = videos.get_plan(conn, plan_id)
    if plan is None or plan.recipe != "highlights":
        return []
    videos_of: dict[int, str] = {}
    for rid in {s.recording_id for s in plan.segments}:
        proxy = videos.proxy_of(conn, rid)
        videos_of[rid] = file_url(proxy) if proxy and proxy.is_file() else ""
    return [{"id": cid, "label": label, "rid": rid, "start": a, "end": b,
             "video": videos_of.get(rid, "")}
            for label, cid, rid, a, b in review.addable(conn, settings, plan)]


def make_preview(settings: Settings, worker: Worker, plan_id: str, part: int | None) -> dict:
    """Quick preview: a job, as today's button starts it. {"said", "job"}."""
    conn = init_db(settings.db_path)
    try:
        plan, _ = videos.get_plan(conn, plan_id)
    finally:
        conn.close()
    if plan is None:
        return {"said": "Pick a plan first."}
    if plan.recipe == "letsplay" and part is None:
        return {"said": "Click a part first: a Let's Play is previewed a part at a time."}
    part = part if plan.recipe == "letsplay" else None
    what = f"part {part} of " if part else ""
    key = f"preview:{plan_id}:{part}"
    task = worker.submit(f"Quick preview of {what}{plan.title}", key,
                         tasks.quick_preview(settings, plan_id, part))
    if task is None:
        same = next((t for t in worker.snapshot() if t.key == key
                     and t.status not in (DONE, FAILED)), None)
        return {"said": "That preview is already being made.", "job": same.id if same else None}
    ahead = sum(t.status in (WAITING, RUNNING) for t in worker.snapshot()) - 1
    return {"said": "Making the quick preview: it plays here when it's ready."
                    + (f" It starts after the {ahead} job{'s' if ahead != 1 else ''} ahead "
                       "of it." if ahead > 0 else ""), "job": task.id}


def preview_job(settings: Settings, worker: Worker, job_id: int) -> dict:
    task = next((t for t in worker.snapshot() if t.id == job_id), None)
    if task is None:
        return {"state": "gone"}
    if task.status == DONE and "preview" in task.result:
        path = Path(task.result["preview"])
        return {"state": "ready", "url": file_url(path) if path.is_file() else ""}
    if task.status in (DONE, FAILED):
        return {"state": "failed", "error": task.error or (task.lines or ["No preview made."])[-1]}
    return {"state": "waiting"}


def delete(settings: Settings, plan_ids: list[str]) -> str:
    """Off the list, only when the creator says so (the screen asks once more first).
    Finished videos, clips and ratings all stay."""
    from ..recipes.plan import delete_plans

    conn = init_db(settings.db_path)
    try:
        gone = delete_plans(conn, [p for p in plan_ids if p])
    finally:
        conn.close()
    return (f"Deleted {gone} plan{'s' if gone != 1 else ''} from the list." if gone
            else "Nothing was deleted.")


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

    @app.get("/api/review")
    def whole(plan: str | None = None):
        return JSONResponse({**read(screen, settings, plan), "version": worker.version},
                            headers=no_cache)

    @app.get("/api/review/job/{job_id}")
    def job(job_id: int):
        return JSONResponse(preview_job(settings, worker, job_id), headers=no_cache)

    @app.post("/api/review/delete")
    def delete_plans(request: Request, plans: list[str] = Body(..., embed=True)):
        guarded(request)
        return {"said": delete(settings, plans)}

    @app.post("/api/review/classic")
    def classic(request: Request, plan: str = Body(..., embed=True)):
        """Today's Review, inside the window, on this plan (until 4F-3)."""
        guarded(request)
        videos.WANTED.ask(plan)
        return {"ok": True}

    @app.get("/api/review/{plan_id}/clip/{index}")
    def one(plan_id: str, index: int):
        found = read(clip, settings, plan_id, index)
        if found is None:
            raise HTTPException(status_code=404)
        return JSONResponse(found, headers=no_cache)

    @app.get("/api/review/{plan_id}/addable")
    def can_add(plan_id: str):
        return JSONResponse({"clips": read(addable, settings, plan_id)}, headers=no_cache)

    @app.post("/api/review/{plan_id}/edit")
    def change(plan_id: str, request: Request, action: str = Body(...),
               index: int | None = Body(None), extra=Body(None)):
        guarded(request)
        return edit(settings, plan_id, action, index, extra)

    @app.post("/api/review/{plan_id}/cut")
    def cut(plan_id: str, request: Request, cut: dict = Body(..., embed=True)):
        guarded(request)
        return save_cut(settings, plan_id, cut)

    @app.post("/api/review/{plan_id}/undo")
    def undo(plan_id: str, request: Request):
        guarded(request)
        return {"said": step(settings, plan_id, back=True)}

    @app.post("/api/review/{plan_id}/redo")
    def redo(plan_id: str, request: Request):
        guarded(request)
        return {"said": step(settings, plan_id, back=False)}

    @app.post("/api/review/{plan_id}/preview")
    def quick(plan_id: str, request: Request, part: int | None = Body(None, embed=True)):
        guarded(request)
        return make_preview(settings, worker, plan_id, part)
