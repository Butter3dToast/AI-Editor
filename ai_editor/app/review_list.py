"""Review's length bar and clip list (Phase 2D-1).

What the creator chose (2026-10-10): drag the rows of the clip list to
reorder them, and a bar above it with one block per clip, sized by its
length, against the target: about 10 minutes for highlights (never below),
60 seconds at most for a Short, the part length for a Let's Play. The teaser
and clips with a slow-motion replay have their own colour. Clicking a block
picks that clip, the same as clicking its row.

Built here as HTML, so it can be checked without the window; the window
shows it in one gr.HTML with LIST_CSS and LIST_JS. The page tells Python
what happened through two events: "click" with the row clicked, "submit"
with a drag's from and to (row indexes in the plan, the order after the move).
"""

from __future__ import annotations

from html import escape

from ..analysis.captions import clock
from ..config import Settings
from ..recipes.plan import EditPlan
from .videos import recorded_days, short_clock, timeline, why


def _bar(blocks: list[dict], scale: float, target: float | None, note: str, tone: str) -> str:
    """The bar: blocks as wide as their share of ``scale`` seconds, and a target line."""
    parts = []
    for b in blocks:
        width = max(0.0, b["sec"]) / scale * 100 if scale > 0 else 0
        sel = " sel" if b.get("selected") else ""
        parts.append(f"<div class='aie-block {b['kind']}{sel}' data-row='{b['row']}' "
                     f"style='width:{width:.3f}%' title='{escape(b['title'], quote=True)}'>"
                     f"<span>{escape(b['label'])}</span></div>")
    marker = ""
    if target and scale > 0:
        at = min(100.0, target / scale * 100)
        marker = (f"<div class='aie-target' style='left:{at:.3f}%' "
                  f"title='Target {short_clock(target)}'></div>")
    return (f"<div class='aie-bar-note {tone}'>{note}</div>"
            f"<div class='aie-bar'>{''.join(parts)}{marker}</div>")


def length_bar(conn, plan: EditPlan, settings: Settings, selected: int | None = None) -> str:
    """The bar for any plan: clips (highlights, Shorts) or parts (Let's Play)."""
    if plan.recipe == "letsplay":
        return _parts_bar(plan, settings, selected)
    line = timeline(conn, plan, settings)
    blocks, number = [], 0
    for n, s in enumerate(plan.segments):
        # What this clip adds to the video: up to where the next one starts sliding in.
        sec = (line.starts[n + 1] - line.starts[n]) if n + 1 < len(plan.segments) \
            else line.lengths[n]
        teaser = s.kind == "teaser"
        number += 0 if teaser else 1
        kind = "teaser" if teaser else ("replay" if line.replays[n] else f"clip c{number % 2}")
        label = "T" if teaser else f"{n + 1}" + (" ⟲" if line.replays[n] else "")
        title = (("Teaser" if teaser else f"#{n + 1}") + f" · at {short_clock(line.starts[n])}"
                 + f" · {line.lengths[n]:.0f} s"
                 + (" with a slow-motion replay" if line.replays[n] else "")
                 + (f" · {why(s.reasons)}" if s.reasons else ""))
        blocks.append({"row": n, "sec": sec, "kind": kind, "label": label, "title": title,
                       "selected": n == selected})
    total = line.total
    if plan.recipe == "shorts":
        most = settings.shorts.max_length_sec
        tone = "over" if total > most + 0.5 else "ok"
        note = (f"<b>{total:.0f} s</b> of the {most:.0f} s most a Short can be"
                if tone == "ok" else f"<b>{total:.0f} s</b>: over the {most:.0f} s a Short "
                                     "can be. Adjust the cut to shorten it.")
        return _bar(blocks, max(total, most), most, note, tone)
    target = plan.target_sec
    if total + 0.5 >= target:
        tone, note = "ok", (f"<b>{short_clock(total)}</b> long · over your "
                            f"{short_clock(target)} target ✓")
    else:
        tone, note = "under", (f"<b>{short_clock(total)}</b> long · "
                               f"{short_clock(target - total)} under your "
                               f"{short_clock(target)} target")
    return _bar(blocks, max(total, target), target, note, tone)


def _parts_bar(plan: EditPlan, settings: Settings, selected: int | None) -> str:
    numbers = sorted({s.part for s in plan.segments if s.part is not None})
    lengths = [sum(s.length for s in plan.segments if s.part == n) for n in numbers]
    low, high = settings.lets_play.normal_range_min
    blocks = [{"row": i, "sec": sec, "kind": f"clip c{i % 2}", "label": f"Part {n}",
               "title": f"Part {n} · {short_clock(sec)}", "selected": i == selected}
              for i, (n, sec) in enumerate(zip(numbers, lengths))]
    off = [n for n, sec in zip(numbers, lengths) if not low * 60 <= sec <= high * 60]
    note = (f"<b>{len(numbers)} part{'s' if len(numbers) != 1 else ''}</b>: "
            + " · ".join(short_clock(sec) for sec in lengths)
            + f" (aim for {low:.0f}-{high:.0f} min each)")
    return _bar(blocks, sum(lengths), None, note, "under" if off else "ok")


def clip_rows(conn, plan: EditPlan, settings: Settings, selected: int | None = None) -> str:
    """The list: one row per piece, in order. Clips can be dragged; the teaser can't."""
    days = recorded_days(conn)
    starts = timeline(conn, plan, settings).starts
    head = ("<div class='aie-row aie-head'><span></span><span>#</span><span>In the video</span>"
            "<span>From</span><span>Starts at</span><span>Length</span><span>Score</span>"
            "<span>Why</span></div>")
    rows = []
    for n, s in enumerate(plan.segments):
        teaser = s.kind == "teaser"
        drag = "" if teaser else " draggable='true' data-clip='1'"
        handle = "" if teaser else "<span class='aie-handle' title='Drag to move'>⠿</span>"
        cells = [str(n + 1), "Teaser" if teaser else short_clock(starts[n]),
                 f"#{s.recording_id} · {days.get(s.recording_id, '')}", clock(s.src_in),
                 f"{s.length:.0f}s", f"{s.score:.2f}" if s.score is not None else "-",
                 why(s.reasons)]
        sel = " sel" if n == selected else ""
        rows.append(f"<div class='aie-row{' teaser' if teaser else ''}{sel}' data-row='{n}'{drag}>"
                    f"{handle or '<span></span>'}"
                    + "".join(f"<span>{escape(c)}</span>" for c in cells) + "</div>")
    tip = ("<div class='aie-tip'>Click a clip to watch it and adjust its cut. Drag a clip by its "
           "row to move it; the teaser always opens the video.</div>") if len(rows) > 1 else ""
    return f"{tip}<div class='aie-rows'>{head}{''.join(rows)}</div>"


def review_list(conn, plan: EditPlan | None, settings: Settings,
                selected: int | None = None) -> str:
    """What the gr.HTML above Review's buttons shows: the bar, and the list for
    highlights and Shorts (a Let's Play keeps its table of parts)."""
    if plan is None or not plan.segments:
        return ""
    bar = length_bar(conn, plan, settings, selected)
    if plan.recipe == "letsplay":
        return bar
    return bar + clip_rows(conn, plan, settings, selected)


LIST_CSS = """
.aie-bar-note { font-size: 0.95em; margin: 2px 0 6px; color: var(--body-text-color); }
.aie-bar-note.under, .aie-bar-note.over { color: #b45309; }
.aie-bar { position: relative; display: flex; height: 34px; border-radius: 6px;
           overflow: visible; background: var(--background-fill-secondary);
           border: 1px solid var(--border-color-primary); margin-bottom: 10px; }
.aie-block { height: 100%; box-sizing: border-box; border-right: 1px solid
             var(--background-fill-primary); cursor: pointer; overflow: hidden;
             display: flex; align-items: center; justify-content: center; color: #fff;
             font-size: 12px; white-space: nowrap; min-width: 2px; }
.aie-block span { overflow: hidden; text-overflow: clip; padding: 0 2px; }
.aie-block.c0 { background: #2563eb; }
.aie-block.c1 { background: #3b82f6; }
.aie-block.teaser { background: #d97706; }
.aie-block.replay { background: #7c3aed; }
.aie-block:hover { filter: brightness(1.15); }
.aie-block.sel { outline: 3px solid var(--body-text-color); outline-offset: -3px; }
.aie-target { position: absolute; top: -5px; bottom: -5px; width: 0;
              border-left: 2px dashed var(--body-text-color); pointer-events: none; }
.aie-tip { font-size: 0.85em; color: var(--body-text-color-subdued); margin-bottom: 4px; }
.aie-rows { max-height: 520px; overflow-y: auto; border: 1px solid var(--border-color-primary);
            border-radius: 6px; }
.aie-row { display: grid; grid-template-columns: 22px 34px 70px 100px 72px 56px 52px 1fr;
           gap: 6px; padding: 6px 8px; border-bottom: 1px solid var(--border-color-primary);
           cursor: pointer; align-items: center; font-size: 0.92em;
           color: var(--body-text-color); background: var(--background-fill-primary); }
.aie-row:hover { background: var(--background-fill-secondary); }
.aie-row.sel { background: var(--color-accent-soft); }
.aie-row.teaser { border-left: 4px solid #d97706; }
.aie-head { font-weight: 600; cursor: default; background: var(--background-fill-secondary);
            position: sticky; top: 0; z-index: 1; }
.aie-handle { cursor: grab; color: var(--body-text-color-subdued); font-size: 16px;
              user-select: none; }
.aie-row.dragging { opacity: 0.4; }
.aie-row.drop-before { box-shadow: inset 0 3px 0 var(--color-accent); }
.aie-row.drop-after { box-shadow: inset 0 -3px 0 var(--color-accent); }
"""

# Clicks and drags, read in the page and handed to Python with trigger().
LIST_JS = """
let from = null;
const clear = () => element.querySelectorAll('.drop-before, .drop-after, .dragging')
    .forEach(x => x.classList.remove('drop-before', 'drop-after', 'dragging'));
element.addEventListener('click', (e) => {
    const hit = e.target.closest('[data-row]');
    if (!hit) return;
    const row = hit.dataset.row;
    element.querySelectorAll('.sel').forEach(x => x.classList.remove('sel'));
    element.querySelectorAll(`[data-row="${row}"]`).forEach(x => x.classList.add('sel'));
    trigger('click', {row: parseInt(row)});
});
element.addEventListener('dragstart', (e) => {
    const row = e.target.closest && e.target.closest('.aie-row[data-clip]');
    if (!row) return;
    from = parseInt(row.dataset.row);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(from));
    row.classList.add('dragging');
});
element.addEventListener('dragover', (e) => {
    if (from === null) return;
    const row = e.target.closest('.aie-row[data-clip]');
    if (!row) return;
    e.preventDefault();
    const box = row.getBoundingClientRect();
    const after = e.clientY > box.top + box.height / 2;
    element.querySelectorAll('.drop-before, .drop-after')
        .forEach(x => x.classList.remove('drop-before', 'drop-after'));
    row.classList.add(after ? 'drop-after' : 'drop-before');
});
element.addEventListener('drop', (e) => {
    if (from === null) return;
    e.preventDefault();
    const row = e.target.closest('.aie-row[data-clip]');
    const moving = from;
    from = null;
    clear();
    if (!row) return;
    const box = row.getBoundingClientRect();
    const before = parseInt(row.dataset.row) + (e.clientY > box.top + box.height / 2 ? 1 : 0);
    const to = before - (moving < before ? 1 : 0);
    if (to !== moving) trigger('submit', {from: moving, to: to});
});
element.addEventListener('dragend', () => { from = null; clear(); });
"""
