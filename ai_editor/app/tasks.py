"""The window's long jobs: import a recording, fetch a Twitch VOD, analyse.

Each does what its command does (`import`, `import-twitch`, `analyze`) and
reuses the same code, reporting to the window instead of the console. Each
opens its own database connection, because it runs on the worker's thread.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..cli import ANALYSIS_LABELS, STEP_LABELS, _duration, _safe_filename
from ..companion.link import found_text, link_recording
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
    report.say(found_text(link_recording(conn, recording_id)))
    report.say(f"Imported #{recording_id}.")
    return recording_id


def find_marks(settings: Settings) -> Job:
    """Link Stream Companion logs to recordings that have none, and cut their
    clips again with the marks in. Run once at start when there are any (10 Oct:
    6-9 Oct streams had none linked). Ratings, adjusted cuts and used clips stay."""
    from ..analysis.clips import refresh_clips
    from ..companion.link import unlinked_with_log

    def run(report: Reporter) -> None:
        conn = init_db(settings.db_path)
        try:
            for row in unlinked_with_log(conn):
                name = Path(row["source_file"]).stem
                text = found_text(link_recording(conn, row["id"]))
                if row["analysis_status"] == "complete":
                    clips, _ = refresh_clips(conn, settings, row)
                    text += f" Its clips are cut again with them: {len(clips or [])} clips."
                report.say(f"#{row['id']} {name}: {text}")
        finally:
            conn.close()

    return run


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


def _with_style(conn, settings: Settings, profile: int | None, recipe: str,
                game: str | None = None):
    """(settings to make the plan with, (the profile or None, the rules)): a style
    profile's values in, if one was chosen (Phase 2G-2), then your rules for this
    game and kind of video (2H-2), which win over the profile."""
    from ..rules import store
    from ..style import profiles
    from ..style.apply import apply

    found = profiles.load(conn, profile) if profile is not None else None
    if found is not None:
        settings = apply(settings, found.current(settings), recipe)
    settings, rules = store.with_rules(conn, settings, game, recipe)
    return settings, (found, rules)


def _stamp(conn, settings: Settings, plans, used, report: Reporter) -> None:
    """Keep the profile's values and the rules in each plan just made, and say
    what they changed."""
    from ..recipes.plan import save_plan
    from ..rules import store
    from ..style.apply import stamp, summary

    profile, rules = used
    if profile is None and not rules:
        return
    for plan in plans:
        if profile is not None:
            stamp(plan, profile, settings)
        if rules:
            store.stamp(plan, rules)
        save_plan(conn, plan)
    if plans:
        for said in (summary(plans[0]), store.summary(plans[0])):
            if said:
                report.say(said)


def make_highlights(settings: Settings, *, game: str | None, recording_ids: list[int] | None,
                    minutes: float | None, reuse: bool = False, profile: int | None = None,
                    only_liked: bool | None = None) -> Job:
    """`ai-editor highlights`: a draft plan for Review. ``profile``: a style profile's id."""

    def run(report: Reporter) -> None:
        from ..recipes.highlights import build_highlights

        conn = init_db(settings.db_path)
        try:
            report.progress("Choosing the best clips", 0.0)
            used, style = _with_style(conn, settings, profile, "highlights", game)
            result = build_highlights(conn, used, game=game, recording_ids=recording_ids,
                                      target_min=minutes, reuse=reuse, only_liked=only_liked)
            report.progress("Choosing the best clips", 1.0)
            plan = result.plan
            _stamp(conn, settings, [plan], style, report)
            report.say(f"{plan.title}: {plan.total_sec / 60:.1f} min from "
                       f"{result.recordings_used} of {result.recordings_searched} recording(s), "
                       f"{len(plan.segments)} piece(s). Open Review to check it.")
            for note in plan.notes:
                report.say(note)
            report.keep(plan_id=plan.plan_id)
        finally:
            conn.close()

    return run


def make_letsplay(settings: Settings, recording_id: int, profile: int | None = None) -> Job:
    """`ai-editor letsplay`: trim the episode and split it into parts."""

    def run(report: Reporter) -> None:
        from ..recipes.letsplay import build_letsplay

        conn = init_db(settings.db_path)
        try:
            row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
            if row is None or row["analysis_status"] != "complete":
                raise TaskFailed(f"Recording #{recording_id} isn't analysed yet. Analyse it in "
                                 "the Library first.")
            from ..recipes.highlights import has_video
            from ..recipes.shorts import GONE

            if not has_video(row):
                raise TaskFailed(f"Recording #{recording_id}: {GONE}")
            from ..analysis.quests import ensure_read, is_read, plays

            if plays(row["game"]) and not is_read(conn, row["id"]):
                # Once per episode, a few minutes: the quests, so no part
                # is split in the middle of one.
                ensure_read(conn, row, lambda f: report.progress("Reading the quest tracker", f))
            report.progress("Trimming and splitting into parts", 0.0)
            used, style = _with_style(conn, settings, profile, "letsplay", row["game"])
            result = build_letsplay(conn, used, row)
            report.progress("Trimming and splitting into parts", 1.0)
            _stamp(conn, settings, [result.plan], style, report)
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


def make_shorts(settings: Settings, recording_id: int, profile: int | None = None) -> Job:
    """`ai-editor shorts`: up to five suggested Shorts, each its own plan for Review."""

    def run(report: Reporter) -> None:
        from ..recipes.shorts import WHY, build_shorts

        conn = init_db(settings.db_path)
        try:
            report.progress("Choosing the moments", 0.0)
            row = conn.execute("SELECT game FROM recordings WHERE id = ?",
                               (recording_id,)).fetchone()
            used, style = _with_style(conn, settings, profile, "shorts",
                                      row["game"] if row else None)
            result = build_shorts(conn, used, recording_id)
            report.progress("Choosing the moments", 1.0)
            _stamp(conn, settings, result.plans, style, report)
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
                remember_preview(settings, path, plan)
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
            remember_preview(settings, path, whole, part)
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
        from ..recipes.plan import save_plan
        from ..render import names, parts as lp
        from ..render.final import render_plan, video_path

        conn = init_db(settings.db_path)
        try:
            found = load_plan(conn, plan_id)
            if found is None:
                raise TaskFailed("That plan isn't there any more.")
            plan, status = found
            jobs = [(plan, None, "Rendering",
                     dict(target=video_path(settings, plan, captions=captions)))]
            if plan.recipe == "letsplay":
                if episode is None:
                    raise TaskFailed("Which episode is this? Fill in the episode number in "
                                     "Review and render again.")
                numbers = lp.part_numbers(plan)
                jobs = [(lp.part_plan(plan, n), n, f"Part {n} of {len(numbers)}",
                         dict(target=lp.part_path(settings, plan, episode, n, captions=captions),
                              title=lp.title_card(settings, episode, n)))
                        for n in numbers if not parts or n in parts]
            videos = []
            for job, part, label, extra in jobs:
                # Saved under the title you kept in Review, if there is one.
                extra["target"] = names.target(extra["target"], plan, part, captions)
                result = render_plan(conn, settings, job, lambda f, label=label:
                                     report.progress(label, f), captions=captions, **extra)
                names.remember(plan, part, captions, result.path)
                save_plan(conn, plan, status)
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


# --- Phase 2G-1: style profiles ----------------------------------------------------------


def analyse_references(settings: Settings, profile_id: int, *, again: bool = False) -> Job:
    """Measure a style profile's reference videos (those not measured yet, or all
    ``again``), then the AI's notes on what it sees in them."""

    def run(report: Reporter) -> None:
        from ..style import profiles
        from ..style.references import ReferenceProblem, analyse

        conn = init_db(settings.db_path)
        try:
            profile = profiles.load(conn, profile_id)
            if profile is None:
                raise TaskFailed("That style profile has been deleted.")
            todo = [r for r in profile.references if again or r.measured is None]
            if not todo:
                report.say("Every reference is measured already. Tick \"Measure them all "
                           "again\" to redo them.")
                return
            frames: dict[int, tuple[list[bytes], object]] = {}
            for n, ref in enumerate(todo, start=1):
                head = f"Video {n} of {len(todo)}"
                try:
                    result = analyse(settings, ref, lambda step, f, head=head:
                                     report.progress(f"{head}: {step}", f))
                except ReferenceProblem as exc:
                    profiles.store_error(conn, ref.id, str(exc))
                    report.say(f"{ref.name}: {exc}")
                    continue
                profiles.store_measured(conn, ref.id, title=result.title, measured=result.measured)
                frames[ref.id] = (result.frames, result.measured)
                m = result.measured
                report.say(f"{result.title or ref.name}: {m.cuts_per_min:g} cuts a minute, "
                           f"{m.zooms_per_min:g} zooms a minute, captions "
                           f"{m.caption_share:.0%} of the time.")
            _style_notes(conn, settings, profile_id, frames, report)
            report.say("Done. The draft profile is in Style Profiles.")
            report.keep(style_profile=profile_id)
        finally:
            conn.close()

    return run


def _style_notes(conn, settings: Settings, profile_id: int, frames: dict, report: Reporter) -> None:
    """The AI's look at the frames just taken (``frames``: reference id -> (JPEGs,
    what it measured)), then its summing up for the profile. A video whose answer
    can't be used is skipped; the others still get their notes."""
    from .. import llm
    from ..errors import AiAnswerUnreadable, AiTooSlow
    from ..style import notes, profiles

    if not any(shots for shots, _ in frames.values()):
        return
    why_not = notes.available(settings, _try_start)
    if why_not:
        report.say(f"No AI notes this time: {why_not}. The measurements are kept.")
        return
    try:
        with llm.session(settings):
            for n, (ref_id, (shots, measured)) in enumerate(frames.items(), start=1):
                report.progress("AI looking at the references", (n - 1) / len(frames))
                try:
                    profiles.store_notes(conn, ref_id, notes.look(settings, shots, measured))
                except AiAnswerUnreadable:
                    report.say(f"Video {n}: the AI's answer couldn't be used, so it has no "
                               "notes this time.")
            report.progress("AI looking at the references", 1.0)
            profile = profiles.load(conn, profile_id)
            summed = notes.sum_up(settings, [r.notes for r in profile.references if r.notes])
            profiles.store_profile_notes(conn, profile_id, summed)
    except AiTooSlow:
        report.say("The AI was far too slow, so it stopped: probably a game has the graphics "
                   "card. The measurements are kept; Measure them all again later for its notes.")
    except AIEditorError as exc:
        report.say(f"No AI notes this time: {exc.user_message()} The measurements are kept.")
