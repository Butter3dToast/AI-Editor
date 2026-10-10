"""What the Clips, Create video and Review tabs show (spec section 9, items 4, 7 and 8).

Plain functions over the database, kept apart from the window so they can be
tested without it.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from ..analysis.ai_rating import notes_for
from ..analysis.captions import clock
from ..cli import SIGNAL_LABELS
from ..config import Settings
from ..recipes.plan import APPROVED, EditPlan, load_plan, used_in

CLIP_COLUMNS = ["#", "Time", "Length", "In a video", "Score", "Why", "AI says", "You said",
                "Rated", "Used"]
PLAN_COLUMNS = ["#", "In the video", "From", "Starts at", "Length", "Score", "Why"]
PART_COLUMNS = ["Part", "Length", "In the recording", "Pieces"]
SHOW = ["Not used yet", "All", "Rated"]
RATINGS = {1: "👍", -1: "👎"}


def short_clock(seconds: float) -> str:
    """'4:05', or '1:02:03' past an hour: a time in the finished video."""
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def why(reasons: list[str]) -> str:
    return ", ".join(SIGNAL_LABELS.get(r, r) for r in reasons) or "-"


def player(path: str | Path | None, start: float | None = None, end: float | None = None,
           *, note: str = "", autoplay: bool = True) -> str:
    """An in-page video player, optionally playing only start..end.

    Served by the window itself (only files in AI-Editor's own cache and
    output folders are allowed), and played from that point by the browser:
    "#t=start,end" makes it start there and stop at the end.
    """
    if not path or not Path(path).is_file():
        return ("<div class='aie-player-empty'>" + html.escape(note or "Pick something to play it here.")
                + "</div>")
    url = "/gradio_api/file=" + quote(Path(path).as_posix(), safe="/:")
    if start is not None:
        url += f"#t={start:.2f}" + (f",{end:.2f}" if end is not None else "")
    caption = f"<div class='aie-player-note'>{html.escape(note)}</div>" if note else ""
    play = " autoplay" if autoplay else ""
    return (f"<video class='aie-player' src='{url}' controls{play} preload='metadata'>"
            f"</video>{caption}")


def proxy_of(conn, recording_id: int) -> Path | None:
    row = conn.execute("SELECT proxy_path FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    return Path(row["proxy_path"]) if row and row["proxy_path"] else None


def analysed_choices(conn, settings: Settings, *, lets_play: bool | None = None) -> list[tuple[str, int]]:
    """(label, id) for analysed recordings, newest first.

    ``lets_play``: True for Let's Play games only, False for streams only.
    """
    episodes = {g.lower() for g in settings.lets_play.games}
    rows = conn.execute("SELECT id, title, source_file, game FROM recordings WHERE "
                        "analysis_status = 'complete' ORDER BY COALESCE(recorded_at, imported_at) "
                        "DESC").fetchall()
    out = []
    for r in rows:
        is_episode = (r["game"] or "").lower() in episodes
        if lets_play is not None and is_episode != lets_play:
            continue
        out.append((f"#{r['id']}  {r['title'] or Path(r['source_file']).stem}"
                    + (f"  ({r['game']})" if r["game"] else ""), r["id"]))
    return out


# --- Clips ------------------------------------------------------------------------


def video_lengths(conn, settings: Settings, recording_id: int) -> dict[str, float]:
    """How long each clip is once a highlight video trims it to its moment.

    Clips that can't go in (rated down, or during "BRB") aren't listed.
    """
    from ..recipes.highlights import gather

    row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    if row is None or row["analysis_status"] != "complete":
        return {}
    every = {r[0] for r in conn.execute("SELECT clip_id FROM clips WHERE recording_id = ?",
                                        (recording_id,))}
    return {c.clip_id: c.length for c in gather(conn, settings, [row], refresh=False,
                                                allow=every, quality_bar=False)}


def clip_summary(conn, settings: Settings, recording_id: int,
                 lengths: dict[str, float] | None = None) -> str:
    """'34 clips · 18 👍 · 21 👎 · your unused 👍 clips make about 14.2 min of video'."""
    lengths = video_lengths(conn, settings, recording_id) if lengths is None else lengths
    rows = conn.execute("SELECT clip_id, user_rating, used_in_json FROM clips "
                        "WHERE recording_id = ?", (recording_id,)).fetchall()
    up = [r for r in rows if (r["user_rating"] or 0) > 0]
    down = sum((r["user_rating"] or 0) < 0 for r in rows)
    fresh = sum(lengths.get(r["clip_id"], 0.0) for r in up
                if not used_in(r["used_in_json"], shorts=False))
    text = f"**{len(rows)} clips** · {len(up)} 👍 · {down} 👎"
    if up:
        text += (f" · your unused 👍 clips make about **{fresh / 60:.1f} min** of video "
                 "(each trimmed to its moment)")
    return text


def clip_table(conn, recording_id: int, show: str = "Not used yet",
               lengths: dict[str, float] | None = None) -> tuple[list[list], list[str]]:
    """The recording's clips, best first: the table's rows, and each row's clip id.

    ``lengths``: each clip's length in a video (video_lengths), for that column.
    """
    rows = conn.execute("SELECT * FROM clips WHERE recording_id = ? ORDER BY score DESC",
                        (recording_id,)).fetchall()
    lengths = lengths or {}
    notes = notes_for(conn, recording_id, rows)
    table, ids = [], []
    for row in rows:
        used = used_in(row["used_in_json"], shorts=False)
        in_shorts = used_in(row["used_in_json"], shorts=True)
        if show == "Not used yet" and used:
            continue
        if show == "Rated" and row["user_rating"] is None:
            continue
        summary = json.loads(row["signals_json"] or "{}")
        said = (row["transcript"] or "").strip()
        note = notes.get(row["clip_id"])
        table.append([
            len(table) + 1,
            f"{clock(row['start_sec'])}-{clock(row['end_sec'])}",
            f"{row['end_sec'] - row['start_sec']:.0f}s",
            f"{lengths[row['clip_id']]:.0f}s" if row["clip_id"] in lengths else "-",
            f"{row['score']:.2f}",
            why(summary.get("reasons", [])),
            f"{note.stars} {note.summary}" if note else "-",
            said[:70] + ("..." if len(said) > 70 else "") or "-",
            RATINGS.get(row["user_rating"], "-"),
            " + ".join((["video"] if used else []) + (["Short"] if in_shorts else [])) or "-",
        ])
        ids.append(row["clip_id"])
    return table, ids


def clip_details(conn, clip_id: str) -> str:
    row = conn.execute("SELECT * FROM clips WHERE clip_id = ?", (clip_id,)).fetchone()
    if row is None:
        return ""
    summary = json.loads(row["signals_json"] or "{}")
    lines = [f"**{clock(row['start_sec'])}-{clock(row['end_sec'])}** in the recording, "
             f"score {row['score']:.2f}: {why(summary.get('reasons', []))}."]
    if summary.get("game"):
        lines.append(f"Game: {summary['game']}.")
    happened = json.loads(row["game_events_json"] or "[]")
    if happened:
        lines.append("**League:** " + "; ".join(f"{clock(e['t'])} {e['text']}" for e in happened)
                     + ".")
    note = notes_for(conn, row["recording_id"], [row]).get(clip_id)
    if note:
        alone = ("Makes sense on its own (a Short)" if note.stands_alone
                 else "Needs the rest of the stream to make sense")
        lines.append(f"**AI says {note.stars}:** {note.summary}. _{note.reason}_ "
                     f"{alone}." + (f" Tags: {', '.join(note.tags)}." if note.tags else ""))
    used = json.loads(row["used_in_json"] or "[]")
    if used:
        lines.append(f"Used in: {', '.join(used)}.")
    lines.append(f"> {row['transcript']}" if row["transcript"] else "_No words in this clip._")
    return "\n\n".join(lines)


def rate(conn, clip_id: str, rating: int | None) -> str:
    """Thumbs up (1), down (-1) or cleared (None); kept for learning later (spec 7.10)."""
    row = conn.execute("SELECT recording_id, signals_json FROM clips WHERE clip_id = ?",
                       (clip_id,)).fetchone()
    if row is None:
        return "That clip isn't in the library any more."
    conn.execute("UPDATE clips SET user_rating = ? WHERE clip_id = ?", (rating, clip_id))
    game = (json.loads(row["signals_json"] or "{}").get("game")
            or (conn.execute("SELECT game FROM recordings WHERE id = ?",
                             (row["recording_id"],)).fetchone() or [None])[0])
    action = {1: "thumbs_up", -1: "thumbs_down", None: "rating_cleared"}[rating]
    conn.execute("INSERT INTO feedback (ts, action, clip_id, game, features_json) "
                 "VALUES (?, ?, ?, ?, ?)",
                 (datetime.now(timezone.utc).isoformat(timespec="seconds"), action, clip_id, game,
                  row["signals_json"]))
    conn.commit()
    return {1: "👍 Saved. Clips like this one are what AI-Editor learns to look for.",
            -1: "👎 Saved. This moment won't go into a highlight video.",
            None: "Rating cleared."}[rating]


# --- Plans ------------------------------------------------------------------------


# --- Quick previews, kept: one per plan, per Let's Play part, per Short layout ---------


def preview_file(settings: Settings, plan: EditPlan, part: int | None = None,
                 layout: str | None = None) -> Path:
    from ..recipes.preview import FOLDER
    from ..render.final import vertical_of

    name = plan.plan_id
    if plan.recipe == "shorts":
        name += f" {layout or vertical_of(settings, plan).layout}"
    elif part is not None:
        name += f" part {part}"
    return settings.folders.output / FOLDER / f"{name}.mp4"


def shown_in_preview(settings: Settings, plan: EditPlan, part: int | None = None) -> str:
    """What a quick preview shows: the cuts, and which effects are on."""
    from ..effects import switches
    from ..publish import fingerprint
    from ..render.parts import part_plan

    from ..render.slide import between

    shown = part_plan(plan, part) if part else plan
    key = f"{fingerprint(shown)}:{','.join(switches(settings, plan))}"
    off = ",".join(sorted((plan.source or {}).get("effects_off", [])))
    # Added in 2C-3b, only when used, so previews made before still match.
    if between(settings, plan) != "cut" or off:
        key += f":{between(settings, plan)}:{off}"
    return key


def remember_preview(settings: Settings, path: Path, plan: EditPlan,
                     part: int | None = None) -> None:
    """Note beside a preview which version of the plan it shows."""
    path.with_suffix(".json").write_text(
        json.dumps({"fingerprint": shown_in_preview(settings, plan, part)}), encoding="utf-8")


def last_preview(settings: Settings, plan: EditPlan, part: int | None = None,
                 layout: str | None = None) -> str | None:
    """The quick preview already made for this plan (part, layout), ready to play
    -- not started, and saying if the plan has changed since. None if there isn't one."""
    path = preview_file(settings, plan, part, layout)
    if not path.is_file():
        return None
    made = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d %b, %H:%M")
    note = f"Your quick preview from {made}."
    try:
        kept = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))["fingerprint"]
        if kept != shown_in_preview(settings, plan, part):
            note += " The plan has changed since: make a new one to see the changes."
    except (OSError, ValueError, KeyError):
        pass
    return player(path, note=note, autoplay=False)


def kind_of(plan: EditPlan) -> str:
    return {"letsplay": "Let's Play", "shorts": "Short"}.get(plan.recipe, "Highlights")


def plan_choices(conn) -> list[tuple[str, str]]:
    """(label, plan id) for every plan, newest first."""
    out = []
    for row in conn.execute("SELECT plan_id, plan_json, status FROM edit_plans "
                            "ORDER BY created_at DESC, rowid DESC"):
        plan = EditPlan.from_json(row["plan_json"])
        kind = kind_of(plan)
        state = "rendered" if row["status"] == APPROVED else "draft"
        length = (f"{plan.total_sec:.0f} s" if plan.recipe == "shorts"
                  else f"{plan.total_sec / 60:.1f} min")
        out.append((f"{plan.title}  ·  {kind}, {length}, {state}  "
                    f"({plan.plan_id})", plan.plan_id))
    return out


def plan_table(conn, plan: EditPlan, settings: Settings | None = None) -> list[list]:
    """A highlight plan's pieces in order, PLAN_COLUMNS. With ``settings``, the
    times allow for slides between clips (render/slide.py)."""
    from ..render.slide import overlaps, starts
    def day(iso: str | None) -> str:
        try:
            return datetime.fromisoformat(iso).astimezone().strftime("%d %b").lstrip("0")
        except (TypeError, ValueError):
            return ""

    days = {r["id"]: day(r["recorded_at"] or r["imported_at"])
            for r in conn.execute("SELECT id, recorded_at, imported_at FROM recordings")}
    lengths = [s.length for s in plan.segments]
    slides = overlaps(settings, plan, lengths, 60) if settings else []
    rows = []
    for n, (s, position) in enumerate(zip(plan.segments, starts(lengths, slides))):
        where = "Teaser" if s.kind == "teaser" else short_clock(position)
        rows.append([n + 1, where, f"#{s.recording_id} · {days.get(s.recording_id, '')}",
                     clock(s.src_in), f"{s.length:.0f}s",
                     f"{s.score:.2f}" if s.score is not None else "-", why(s.reasons)])
    return rows


def part_table(plan: EditPlan) -> list[list]:
    """A Let's Play's parts, PART_COLUMNS."""
    rows = []
    for number in sorted({s.part for s in plan.segments if s.part is not None}):
        pieces = [s for s in plan.segments if s.part == number]
        rows.append([number, short_clock(sum(s.length for s in pieces)),
                     f"{clock(pieces[0].src_in)}-{clock(pieces[-1].src_out)}", len(pieces)])
    return rows


def plan_summary(plan: EditPlan, status: str) -> str:
    kind = kind_of(plan)
    length = (f"**{plan.total_sec:.0f} s**, vertical 1080×1920" if plan.recipe == "shorts"
              else f"**{plan.total_sec / 60:.1f} min**")
    lines = [f"### {plan.title}",
             f"{kind} · {length}"
             + (f" (target {plan.target_sec / 60:.0f})" if plan.recipe == "highlights" else "")
             + f" · {'rendered' if status == APPROVED else 'draft'} · `{plan.plan_id}`"]
    lines += [f"- {note}" for note in plan.notes]
    return "\n\n".join(lines[:2]) + ("\n\n" + "\n".join(lines[2:]) if lines[2:] else "")


def get_plan(conn, plan_id: str | None) -> tuple[EditPlan, str] | tuple[None, None]:
    found = load_plan(conn, plan_id) if plan_id else None
    return found if found else (None, None)
