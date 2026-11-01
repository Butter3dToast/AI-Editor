"""Review's Publish tab in the new design (Phase 4F-3a), as JSON for the frame.

What today's Review has under Publish: Write titles, description and chapters, the
title ideas, the Title, Description and Tags to copy, Keep my changes, the video's
YouTube link, and the thumbnail frames with their prompts for the Gemini app. Each
frame and its prompt now sit together on one card (the creator, 1 Nov), with Copy
the picture beside Copy the prompt. A Let's Play shows the part clicked in Parts.
The same jobs and the same saved text as today's Review; nothing is sent online.
"""

from __future__ import annotations

import subprocess

# Here, not in add_routes: FastAPI reads the handlers' types by name from this
# module (4B: imported inside a function, Request wasn't found).
from fastapi import Body, Request
from fastapi.responses import JSONResponse

from ..config import Settings
from ..db import init_db
from ..recipes.plan import save_plan
from . import tasks, videos
from .review_finish import remember_episode
from .review_screen import file_url
from .worker import DONE, FAILED, RUNNING, WAITING, Worker


def _part(plan, part) -> int | None:
    """A Let's Play's part on show: the one clicked, else its first. None otherwise."""
    from ..render.parts import part_numbers

    if plan.recipe != "letsplay":
        return None
    numbers = part_numbers(plan)
    try:
        wanted = int(part) if part not in (None, "") else None
    except (TypeError, ValueError):
        wanted = None
    return wanted if wanted in numbers else (numbers[0] if numbers else None)


def _episode(episode) -> int | None:
    try:
        return int(episode) if episode not in (None, "") else None
    except (TypeError, ValueError):
        return None


def view(conn, settings: Settings, plan_id: str, part=None) -> dict | None:
    """Everything the tab shows for the video, Short or part on show."""
    from .. import publish
    from ..render.parts import episode_for, part_numbers

    plan, _ = videos.get_plan(conn, plan_id)
    if plan is None:
        return None
    number = _part(plan, part)
    shorts = plan.recipe == "shorts"
    which = f"Part {number}" if number else "this Short" if shorts else "this video"
    episode, after = episode_for(conn, plan) if plan.recipe == "letsplay" else (None, None)
    out = {"kind": plan.recipe, "part": number,
           "parts": part_numbers(plan) if plan.recipe == "letsplay" else [],
           "episode": episode, "episode_after": after,
           "which": which, "ai": settings.llm.enabled, "written": False,
           "link": None if shorts else publish.link_of(plan, number), "source": "",
           "thumbnails": [], "titles": [], "title": "", "description": "", "tags": "",
           "ideas": [], "who": "", "who_from": ""}
    if plan.recipe == "highlights":
        out["who"], out["who_from"] = publish.thumbnail_who(conn, plan)
    full = ""
    if shorts:
        full, from_video = publish.full_video_link(conn, plan)
        if from_video:
            out["source"] = (f"It's from {from_video}: " + (
                "its link goes in the description." if full else
                "paste that video's YouTube link in its Publish tab, and the description here "
                "links to it."))
    made = publish.saved(plan, number)
    if made is None:
        out["note"] = (f"Nothing written for {which} yet. Write asks the local AI for a title, "
                       "a line or two and hashtags (a few seconds; Shorts have no chapters or "
                       "thumbnail)." if shorts else
                       f"Nothing written for {which} yet. Write asks the local AI for title "
                       "ideas, a description with chapters, tags, thumbnail frames, and "
                       + ("three thumbnail ideas for the Gemini app" if plan.recipe == "highlights"
                          else "a thumbnail prompt for each frame")
                       + " (about a minute). Its summaries of the clips are what it writes "
                       "from.")
        return out
    out.update(written=True, titles=made.titles,
               title=made.title or (made.titles[0] if made.titles else ""),
               description=publish.description_text(settings, made, full or None),
               tags=", ".join(publish.tags_of(made)),
               stale=publish.is_stale(plan, number, made),
               note=f"For {which}, written {made.made_at[:16].replace('T', ' ')} (UTC).")
    if not shorts:
        out["thumbnails"] = [{"n": n, "url": file_url(t.path), "rating": t.rating,
                              "reason": t.reason, "prompt": t.prompt}
                             for n, t in enumerate(made.thumbnails) if t.path.is_file()]
    out["ideas"] = made.prompts
    return out


def save_who(settings: Settings, plan_id: str, who: str) -> str:
    """Who's on a highlight's thumbnail, typed in Publish: kept with the plan."""
    conn = init_db(settings.db_path)
    try:
        plan, status = videos.get_plan(conn, plan_id)
        if plan is None:
            return "Pick a plan first."
        if plan.recipe != "highlights":
            return "Only a highlight video's thumbnail ideas feature who you played."
        who = " ".join((who or "").split())[:80]
        plan.source = {**(plan.source or {}), "thumbnail_who": who}
        save_plan(conn, plan, status)
    finally:
        conn.close()
    return (f"Kept: {who}. Write the ideas again to use it." if who
            else "Cleared: League's game data is used when there is some.")


def write(settings: Settings, worker: Worker, plan_id: str, what: str, episode=None,
          part=None) -> dict:
    """Write the text (with thumbnails and prompts) or only the prompts, as today's
    buttons do. ``part``: a part's number, or "all" for every part."""
    conn = init_db(settings.db_path)
    try:
        plan, _ = videos.get_plan(conn, plan_id)
    finally:
        conn.close()
    if plan is None:
        return {"said": "Pick a plan first."}
    if not settings.llm.enabled:
        return {"said": "The local AI is switched off in Settings (AI)."}
    episode = _episode(episode)
    if plan.recipe == "letsplay" and not episode:
        return {"said": "Fill in the episode number first: it goes in the titles and on the "
                        "thumbnails."}
    remember_episode(settings, plan_id, episode)
    parts = None if part == "all" or plan.recipe != "letsplay" else [_part(plan, part)]
    label = "All parts" if parts is None else f"Part {parts[0]}"   # today's job names
    if what == "prompts":
        task = worker.submit(f"Writing thumbnail prompts for {plan.title}",
                             f"prompts:{plan_id}:{label}",
                             tasks.write_prompts(settings, plan_id, parts=parts, episode=episode))
    else:
        task = worker.submit(f"Writing the upload text for {plan.title}",
                             f"publish:{plan_id}:{label}",
                             tasks.write_publish(settings, plan_id, parts=parts, episode=episode))
    if task is None:
        return {"said": "That's already being written, in Jobs."}
    ahead = sum(t.status in (WAITING, RUNNING) for t in worker.snapshot()) - 1
    return {"said": "Writing it with the local AI, in Jobs. It shows here when it's done."
                    + (f" It starts after the {ahead} job{'s' if ahead != 1 else ''} ahead "
                       "of it." if ahead > 0 else ""), "job": task.id}


def keep(settings: Settings, plan_id: str, part, episode, title: str, description: str,
         tags: str) -> str:
    """Keep my changes: kept over the AI's, and saved beside a finished video."""
    from .. import publish

    conn = init_db(settings.db_path)
    try:
        plan, status = videos.get_plan(conn, plan_id)
        if plan is None:
            return "Pick a plan first."
        number = _part(plan, part)
        made = publish.saved(plan, number)
        if made is None:
            return "Write the text first, then change it."
        made.edited = {"title": (title or "").strip(), "description": description or "",
                       "tags": [t.strip() for t in (tags or "").split(",") if t.strip()]}
        plan.publish[publish.key_of(number)] = made.as_dict()
        save_plan(conn, plan, status)
    finally:
        conn.close()
    remember_episode(settings, plan_id, episode)
    beside = tasks.publish_videos(settings, plan, number, _episode(episode))
    for video in beside:
        publish.write_text_beside(settings, made, video)
    return "Kept." + (f" Saved beside the video too: {beside[0].with_suffix('.txt').name}."
                      if beside else " It's saved beside the video when you render it.")


def save_link(settings: Settings, plan_id: str, part, link: str) -> str:
    from .. import publish

    conn = init_db(settings.db_path)
    try:
        plan, status = videos.get_plan(conn, plan_id)
        if plan is None:
            return "Pick a plan first."
        if plan.recipe == "shorts":
            return "A Short links to its full video, not the other way round."
        publish.set_link(plan, _part(plan, part), link or "")
        save_plan(conn, plan, status)
    finally:
        conn.close()
    return ("Saved. Shorts from this video now link to it." if (link or "").strip()
            else "Link removed.")


def open_frame(settings: Settings, plan_id: str, part, n: int) -> str:
    """Explorer with the frame picked: the path comes from the saved plan, never the page."""
    from .. import publish

    conn = init_db(settings.db_path)
    try:
        plan, _ = videos.get_plan(conn, plan_id)
    finally:
        conn.close()
    made = publish.saved(plan, _part(plan, part)) if plan is not None else None
    if made is None or not 0 <= n < len(made.thumbnails) or not made.thumbnails[n].path.is_file():
        return "That frame isn't there any more: write it again."
    subprocess.Popen(["explorer", "/select,", str(made.thumbnails[n].path)])  # noqa: S603,S607
    return ""


def job(worker: Worker, job_id: int) -> dict:
    task = next((t for t in worker.snapshot() if t.id == job_id), None)
    if task is None:
        return {"state": "gone"}
    if task.status == DONE:
        return {"state": "ready", "said": (task.lines or [""])[-1]}
    if task.status == FAILED:
        return {"state": "failed", "error": task.error or "The writing stopped."}
    return {"state": "waiting"}


# --- its addresses in the frame's server (frame_api.py) --------------------------------


def add_routes(app, frame, guarded) -> None:
    settings, worker = frame.settings, frame.worker
    no_cache = {"Cache-Control": "no-store"}

    @app.get("/api/review/publish-job/{job_id}")
    def publish_job(job_id: int):
        return JSONResponse(job(worker, job_id), headers=no_cache)

    @app.get("/api/review/{plan_id}/publish")
    def shown(plan_id: str, part: str | None = None):
        conn = init_db(settings.db_path)
        try:
            return JSONResponse(view(conn, settings, plan_id, part) or {}, headers=no_cache)
        finally:
            conn.close()

    @app.post("/api/review/{plan_id}/publish/write")
    def written(plan_id: str, request: Request, what: str = Body("publish"),
                episode=Body(None), part=Body(None)):
        guarded(request)
        return write(settings, worker, plan_id, what, episode, part)

    @app.post("/api/review/{plan_id}/publish/keep")
    def kept(plan_id: str, request: Request, part=Body(None), episode=Body(None),
             title: str = Body(""), description: str = Body(""), tags: str = Body("")):
        guarded(request)
        return {"said": keep(settings, plan_id, part, episode, title, description, tags)}

    @app.post("/api/review/{plan_id}/publish/link")
    def linked(plan_id: str, request: Request, part=Body(None), link: str = Body("")):
        guarded(request)
        return {"said": save_link(settings, plan_id, part, link)}

    @app.post("/api/review/{plan_id}/publish/who")
    def who_typed(plan_id: str, request: Request, who: str = Body("", embed=True)):
        guarded(request)
        return {"said": save_who(settings, plan_id, who)}

    @app.post("/api/review/{plan_id}/publish/frame")
    def frame_open(plan_id: str, request: Request, n: int = Body(...), part=Body(None)):
        guarded(request)
        return {"said": open_frame(settings, plan_id, part, n)}
