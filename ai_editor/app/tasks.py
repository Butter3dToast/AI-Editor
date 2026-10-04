"""The window's long jobs: import a recording, fetch a Twitch VOD, analyse.

Each does what its command does (`import`, `import-twitch`, `analyze`) and
reuses the same code, reporting to the window instead of the console. Each
opens its own database connection, because it runs on the worker's thread.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..cli import ANALYSIS_LABELS, STEP_LABELS, _duration, _safe_filename
from ..companion.link import link_recording
from ..config import Settings
from ..db import init_db
from ..errors import AIEditorError
from ..games import canonical_game
from ..ingest import ingest_recording
from .worker import Reporter, TaskFailed

Job = Callable[[Reporter], None]


def import_file(settings: Settings, path: Path, *, game: str | None = None,
                tracks: str | None = None, vod_link: str | None = None,
                analyse: bool = True) -> Job:
    """`ai-editor import`, then (by default) `ai-editor analyze`."""

    def run(report: Reporter) -> None:
        from .. import twitch

        vod_id = recorded_at = None
        chosen = game
        if vod_link:
            try:
                vod_id = twitch.parse_vod_id(vod_link)
                info = twitch.vod_info(settings, vod_id)
                chosen = chosen or (info.game and canonical_game(info.game))
                recorded_at = info.created_at.isoformat() if info.created_at else None
            except AIEditorError as exc:
                report.say(f"Couldn't read the VOD's details from Twitch, so importing "
                           f"without them. {exc.user_message()}")
        conn = init_db(settings.db_path)
        try:
            recording_id = _ingest(conn, settings, path, report, game=chosen, tracks=tracks,
                                   source_type="twitch_vod" if vod_link else "local_obs",
                                   vod_id=vod_id, recorded_at=recorded_at)
            if analyse:
                _analyse(conn, settings, recording_id, report)
        finally:
            conn.close()

    return run


def import_twitch(settings: Settings, link: str, *, game: str | None = None,
                  chat: bool = True, analyse: bool = True) -> Job:
    """`ai-editor import-twitch`: download, import, attach the chat, then analyse."""

    def run(report: Reporter) -> None:
        from .. import twitch
        from ..analysis.chat import attach_chat

        vod_id = twitch.parse_vod_id(link)
        info = twitch.vod_info(settings, vod_id)
        report.say(f"{info.title or 'Twitch VOD'} ({info.channel or '?'}, "
                   f"{info.game or 'game unknown'}, {_duration(info.length_sec)})")
        date = info.created_at.strftime("%Y-%m-%d") if info.created_at else "unknown date"
        target = (settings.folders.raw
                  / f"Twitch {date} {_safe_filename(info.title or vod_id)} ({vod_id}).mp4")
        if target.exists():
            report.say(f"Already downloaded: {target.name}")
        else:
            twitch.download_video(settings, vod_id, target,
                                  lambda f: report.progress("Downloading the VOD", f))
            report.say(f"Downloaded to {target}")

        conn = init_db(settings.db_path)
        try:
            recording_id = _ingest(
                conn, settings, target, report,
                game=game or (info.game and canonical_game(info.game)), tracks=None,
                source_type="twitch_vod", vod_id=vod_id,
                recorded_at=info.created_at.isoformat() if info.created_at else None)
            if chat:
                report.progress("Downloading the chat", 0.0)
                result = attach_chat(conn, settings, recording_id, vod_id)
                report.progress("Downloading the chat", 1.0)
                report.say(f"Chat attached: {result.messages_in_recording:,} messages from "
                           f"{result.chatters} viewer(s).")
                if result.expiry_warning:
                    report.say(result.expiry_warning)
            if analyse:
                _analyse(conn, settings, recording_id, report)
        finally:
            conn.close()

    return run


def analyse(settings: Settings, recording_id: int) -> Job:
    """`ai-editor analyze`: also resumes a paused or failed analysis."""

    def run(report: Reporter) -> None:
        conn = init_db(settings.db_path)
        try:
            _analyse(conn, settings, recording_id, report)
        finally:
            conn.close()

    return run


def _ingest(conn, settings: Settings, path: Path, report: Reporter, *, game, tracks,
            source_type, vod_id=None, recorded_at=None) -> int:
    def on_registered(reg, space_warning: str | None) -> None:
        info = reg.info
        report.say(f"Library #{reg.recording_id}"
                   + ("" if reg.is_new else " (already in the library, carrying on)")
                   + f": {reg.game or 'game not set'}, {_duration(info.duration_sec)}, "
                   + ", ".join(f"track {i} {role}" for i, role in reg.track_roles.items()))
        if reg.relinked_from:
            report.say(f"Found it moved from {reg.relinked_from}")
        if not info.is_multitrack and source_type != "twitch_vod":
            report.say("This recording has one mixed sound track, so your voice will be "
                       "separated from the game by AI: slower and less accurate than separate "
                       "tracks (manual 7.1-7.3).")
        if space_warning:
            report.say(f"Low space: {space_warning}")

    result = ingest_recording(
        conn, settings, path, game=game or None, track_roles=tracks or None,
        on_progress=lambda step, f: report.progress(STEP_LABELS.get(step, step), f),
        on_registered=on_registered, source_type=source_type, twitch_vod_id=vod_id,
        recorded_at=recorded_at)
    if result.status != "complete":
        raise TaskFailed(f"{result.error_message} Press Resume to try again; finished "
                         "steps won't be repeated.")
    recording_id = result.registration.recording_id
    match = link_recording(conn, recording_id)
    if match:
        detail = f"Stream Companion session found: {match.markers} marker(s)"
        if match.short_markers:
            detail += f" and {match.short_markers} Short-worthy"
        if match.games:
            detail += f"; games played: {', '.join(match.games)}"
        report.say(detail + ".")
    report.say(f"Imported #{recording_id}.")
    return recording_id


def _analyse(conn, settings: Settings, recording_id: int, report: Reporter) -> None:
    from ..analysis import analyze_recording
    from ..analysis.clips import refresh_clips

    def on_started(row, tracks) -> None:
        if tracks.voice_role != "mic":
            report.say("No separate microphone track: the transcript includes everyone "
                       "audible (game characters, teammates), not only you.")

    result = analyze_recording(
        conn, settings, str(recording_id),
        on_progress=lambda step, f: report.progress(ANALYSIS_LABELS.get(step, step), f),
        on_started=on_started)
    if result.status != "complete":
        raise TaskFailed(f"{result.error_message} Press Resume to try again; finished "
                         "steps won't be repeated.")
    row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    clips, _ = refresh_clips(conn, settings, row)
    report.say(f"Analysed #{recording_id}: {len(clips or [])} clips found.")
    if settings.llm.enabled:
        from .. import llm

        if llm.running(settings) is None and not _try_start(settings):
            report.say("The local AI (Ollama) isn't running, so clips weren't rated. Use Rate "
                       "with AI in Clips once it is (manual 5.2).")
        elif not llm.has_model(settings):
            report.say("The AI model isn't downloaded yet, so clips weren't rated. Settings, "
                       "AI: Download model.")
        else:
            try:
                _rate(conn, settings, recording_id, report)
            except AIEditorError as exc:  # the analysis itself is done and kept
                report.say(f"Clips weren't rated by the AI: {exc.user_message()}")


def _try_start(settings: Settings) -> bool:
    from .. import llm

    try:
        llm.start(settings)
        return True
    except AIEditorError:
        return False


def _rate(conn, settings: Settings, recording_id: int, report: Reporter) -> None:
    from ..analysis.ai_rating import rate_recording

    result = rate_recording(conn, settings, recording_id,
                            lambda f: report.progress("AI rating the clips", f))
    text = f"AI rated {result.rated} clip(s)"
    if result.already:
        text += f" ({result.already} already rated)"
    if result.failed:
        text += f"; {result.failed} gave an answer it couldn't use (Rate with AI tries again)"
    report.say(text + ". See the AI says column in Clips.")
    report.keep(rated=recording_id)


def _publish_beside(conn, settings: Settings, plan_id: str, episode: int | None) -> None:
    """The upload text, already written, saved beside the videos just rendered."""
    from .. import publish
    from ..recipes.plan import load_plan

    found = load_plan(conn, plan_id)
    if found is None:
        return
    plan = found[0]
    for key in plan.publish:
        part = int(key.split()[-1]) if key.startswith("part ") else None
        text = publish.saved(plan, part)
        link = publish.full_video_link(conn, plan)[0] if plan.recipe == "shorts" else None
        for video in publish_videos(settings, plan, part, episode):
            publish.write_text_beside(settings, text, video, full_video=link)


def rate_clips(settings: Settings, recording_id: int) -> Job:
    """`ai-editor rate`: the local AI's verdict on each clip it hasn't judged yet."""

    def run(report: Reporter) -> None:
        conn = init_db(settings.db_path)
        try:
            row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
            if row is None or row["analysis_status"] != "complete":
                raise TaskFailed(f"Recording #{recording_id} isn't analysed yet. Analyse it in "
                                 "the Library first.")
            _rate(conn, settings, recording_id, report)
        finally:
            conn.close()

    return run


def write_publish(settings: Settings, plan_id: str, *, parts: list[int] | None = None,
                  episode: int | None = None) -> Job:
    """Titles, description, tags, chapters and thumbnails (publish.py), for the
    video or each chosen part. Saved with the plan, and beside any finished video."""

    def run(report: Reporter) -> None:
        from .. import publish
        from ..recipes.plan import load_plan, save_plan
        from ..render import parts as lp

        conn = init_db(settings.db_path)
        try:
            found = load_plan(conn, plan_id)
            if found is None:
                raise TaskFailed("That plan isn't there any more.")
            plan, status = found
            numbers = [None]
            if plan.recipe == "letsplay":
                if episode is None:
                    raise TaskFailed("Which episode is this? Fill in the episode number in "
                                     "Review first.")
                numbers = parts or lp.part_numbers(plan)
            for n in numbers:
                label = f"Part {n}: " if n else ""
                result = publish.prepare(
                    conn, settings, plan, part=n, episode=episode,
                    on_progress=lambda step, f, label=label: report.progress(label + step, f))
                plan.publish[publish.key_of(n)] = result.as_dict()
                save_plan(conn, plan, status)
                report.say(f"{label}{len(result.titles)} title ideas, {len(result.chapters)} "
                           f"chapters, {len(result.thumbnails)} thumbnail frames. They're in "
                           "Review, under Publish.")
                link = publish.full_video_link(conn, plan)[0] if plan.recipe == "shorts" else None
                for video in publish_videos(settings, plan, n, episode):
                    publish.write_text_beside(settings, result, video, full_video=link)
                    report.say(f"Saved beside the video: {video.with_suffix('.txt').name}")
            report.keep(publish=plan_id)
        finally:
            conn.close()

    return run


def publish_videos(settings: Settings, plan, part: int | None, episode: int | None) -> list[Path]:
    """The finished video(s) this text belongs with, captioned or not, that exist."""
    from ..render import parts as lp
    from ..render.final import video_path

    if plan.recipe == "shorts":
        found = [video_path(settings, plan)]
    elif plan.recipe == "letsplay":
        if not (part and episode):
            return []
        found = [lp.part_path(settings, plan, episode, part, captions=c) for c in (False, True)]
    else:
        found = [video_path(settings, plan, captions=c) for c in (False, True)]
    return [p for p in found if p.is_file()]


def download_model(settings: Settings) -> Job:
    """Settings, AI: fetch the model once (Ollama keeps a paused download)."""

    def run(report: Reporter) -> None:
        from .. import llm

        llm.pull(settings, lambda f: report.progress(f"Downloading {settings.llm.model}", f))
        report.say(f"{settings.llm.model} is ready. Clips are rated after each analysis; use "
                   "Rate with AI in Clips for recordings analysed before.")

    return run


# --- Phase 1H-2: making, previewing and rendering videos ------------------------------


def make_highlights(settings: Settings, *, game: str | None, recording_ids: list[int] | None,
                    minutes: float | None, reuse: bool = False) -> Job:
    """`ai-editor highlights`: a draft plan for Review."""

    def run(report: Reporter) -> None:
        from ..recipes.highlights import build_highlights

        conn = init_db(settings.db_path)
        try:
            report.progress("Choosing the best clips", 0.0)
            result = build_highlights(conn, settings, game=game, recording_ids=recording_ids,
                                      target_min=minutes, reuse=reuse)
            report.progress("Choosing the best clips", 1.0)
            plan = result.plan
            report.say(f"{plan.title}: {plan.total_sec / 60:.1f} min from "
                       f"{result.recordings_used} of {result.recordings_searched} recording(s), "
                       f"{len(plan.segments)} piece(s). Open Review to check it.")
            for note in plan.notes:
                report.say(note)
            report.keep(plan_id=plan.plan_id)
        finally:
            conn.close()

    return run


def make_letsplay(settings: Settings, recording_id: int) -> Job:
    """`ai-editor letsplay`: trim the episode and split it into parts."""

    def run(report: Reporter) -> None:
        from ..recipes.letsplay import build_letsplay

        conn = init_db(settings.db_path)
        try:
            row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
            if row is None or row["analysis_status"] != "complete":
                raise TaskFailed(f"Recording #{recording_id} isn't analysed yet. Analyse it in "
                                 "the Library first.")
            report.progress("Trimming and splitting into parts", 0.0)
            result = build_letsplay(conn, settings, row)
            report.progress("Trimming and splitting into parts", 1.0)
            removed = sum(c.length for c in result.cuts)
            report.say(f"{result.duration_sec / 60:.1f} min trimmed to "
                       f"{(result.duration_sec - removed) / 60:.1f} min ({len(result.cuts)} cuts, "
                       f"nothing sped up), in {len(result.parts)} part(s). Open Review to check it.")
            for note in result.plan.notes:
                report.say(note)
            report.keep(plan_id=result.plan.plan_id)
        finally:
            conn.close()

    return run


def make_shorts(settings: Settings, recording_id: int) -> Job:
    """`ai-editor shorts`: up to five suggested Shorts, each its own plan for Review."""

    def run(report: Reporter) -> None:
        from ..recipes.shorts import WHY, build_shorts

        conn = init_db(settings.db_path)
        try:
            report.progress("Choosing the moments", 0.0)
            result = build_shorts(conn, settings, recording_id)
            report.progress("Choosing the moments", 1.0)
            for n, plan in enumerate(result.plans, 1):
                report.say(f"{n}. {plan.title.removeprefix('Short: ')} "
                           f"({plan.total_sec:.0f} s; {WHY[plan.source['why']]})")
            for note in result.notes:
                report.say(note)
            if result.plans:
                report.say(f"{len(result.plans)} Short(s) suggested. They're in Review: pick one "
                           "under Video plan.")
                report.keep(plan_id=result.plans[0].plan_id)
        finally:
            conn.close()

    return run


def quick_preview(settings: Settings, plan_id: str, part: int | None = None) -> Job:
    """A low-resolution version from the preview copies, to watch in the window."""

    def run(report: Reporter) -> None:
        from ..recipes.plan import load_plan
        from ..recipes.preview import FOLDER, render_preview
        from ..render import parts as lp

        conn = init_db(settings.db_path)
        try:
            found = load_plan(conn, plan_id)
            if found is None:
                raise TaskFailed("That plan isn't there any more.")
            plan = found[0]
            from .videos import preview_file, remember_preview

            target = preview_file(settings, plan, part)
            if plan.recipe == "shorts":
                from ..recipes.preview import render_short_preview

                path = render_short_preview(conn, settings, plan,
                                            lambda f: report.progress("Making a quick preview", f),
                                            target=target)
                remember_preview(path, plan)
                report.say("Quick preview ready. The faint red areas are covered by the apps' "
                           "buttons and text; the red line marks what stays free. They aren't in "
                           "the finished Short.")
                report.keep(preview=str(path))
                return
            whole = plan
            if part is not None:
                plan = lp.part_plan(plan, part)
            path = render_preview(conn, settings, plan,
                                  lambda f: report.progress("Making a quick preview", f),
                                  target=target)
            remember_preview(path, whole, part)
            report.say(f"Quick preview ready ({plan.total_sec / 60:.1f} min). It's playing in "
                       "Review.")
            report.keep(preview=str(path))
        finally:
            conn.close()

    return run


def render(settings: Settings, plan_id: str, *, captions: bool, episode: int | None = None,
           parts: list[int] | None = None) -> Job:
    """`ai-editor render`: the finished video(s), full quality.

    Rendering approves the plan: its clips count as used, so the next
    highlight video carries on with fresh ones.
    """

    def run(report: Reporter) -> None:
        from ..analysis.captions import clock
        from ..recipes.plan import approve_plan, load_plan
        from ..render import parts as lp
        from ..render.final import render_plan

        conn = init_db(settings.db_path)
        try:
            found = load_plan(conn, plan_id)
            if found is None:
                raise TaskFailed("That plan isn't there any more.")
            plan = found[0]
            jobs = [(plan, "Rendering", {})]
            if plan.recipe == "letsplay":
                if episode is None:
                    raise TaskFailed("Which episode is this? Fill in the episode number in "
                                     "Review and render again.")
                numbers = lp.part_numbers(plan)
                jobs = [(lp.part_plan(plan, n), f"Part {n} of {len(numbers)}",
                         dict(target=lp.part_path(settings, plan, episode, n, captions=captions),
                              title=lp.title_card(settings, episode, n)))
                        for n in numbers if not parts or n in parts]
            videos = []
            for job, label, extra in jobs:
                result = render_plan(conn, settings, job, lambda f, label=label:
                                     report.progress(label, f), captions=captions, **extra)
                videos.append(str(result.path))
                report.say(f"Saved {result.path.name} ({clock(result.length_sec)}).")
                for note in result.notes:
                    report.say(note)
            _publish_beside(conn, settings, plan_id, episode)
            marked = approve_plan(conn, plan_id)
            if plan.recipe == "shorts":
                report.say("Saved in output\\shorts. This moment won't be suggested as a Short "
                           "again (it can still go in a highlight video).")
            elif plan.recipe != "letsplay":
                report.say(f"{marked} clip(s) marked as used: the next highlight video carries "
                           "on with fresh ones.")
            report.keep(videos=videos)
        finally:
            conn.close()

    return run
