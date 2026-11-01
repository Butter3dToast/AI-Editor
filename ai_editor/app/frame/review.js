/* Review, rebuilt in the new design (Phase 4F-1, editing the cut; mockups/Review.dc.html).

   The clip on a stage, pinned at the top while the rest scrolls (as Clips, the
   creator's choice, 1 Nov): the player with the designer's ◀ 1 s, 1 s ▶, Trim
   start to here, Trim end to here and Watch the whole video, the clip's details
   beside it with Remove and More…. Under it the length bar against the target,
   then tabs: the clips (drag to reorder, sort, a teaser from a moment, add a
   clip); Captions, Effects & music and Publish come in 4F-2 and 4F-3, and until
   then "Today's Review" opens today's screen on the same plan. Every change is
   one Undo step, as in today's Review. Answers come from review_screen.py. */
"use strict";

(() => {
  const { el, toast, post, line, NATIVE } = window.aie;
  const EVERY_MS = 5000;
  const LATER = {
    captions: "Fixing caption lines (and whether they're burned in)",
    effects: "Effects on each moment, music from your stream and what happens between clips",
    publish: "Titles, description, chapters, your YouTube link and thumbnail prompts",
  };

  let body = null;
  let actions = null;
  let timer = null;
  let planId = null;
  let data = null;
  let seen = "";
  let selected = null;           // the row on the stage
  let clip = null;               // its details and where it plays from
  let cut = null;                // a new start and end, not saved yet
  let stopAt = null;
  let whole = false;             // the stage is playing the quick preview
  let tab = "clips";
  let moreOpen = false;
  let dragFrom = null;
  const ticked = new Set();      // Delete several plans
  const watching = new Set();    // quick previews being made

  const $ = (sel) => body.querySelector(sel);
  /* Put these in ``node``, leaving out the empty ones: replaceChildren writes a null out
     as the word "null" (4D: the Clips details showed it). */
  const fill = (node, ...kids) => node.replaceChildren(...kids.filter((k) => k !== null
    && k !== undefined && k !== false));
  const clockOf = (t) => {
    const s = Math.max(0, Math.round(t * 10) / 10);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = (s % 60).toFixed(1).padStart(4, "0");
    return `${h}:${String(m).padStart(2, "0")}:${sec}`;   // as the details write it: 0:10:00
  };
  const secondsOf = (text) => {
    const parts = String(text).trim().split(":").map(Number);
    if (!parts.length || parts.some((n) => Number.isNaN(n) || n < 0) || parts.length > 3) return null;
    return parts.reduce((total, n) => total * 60 + n, 0);
  };
  const lets = () => data && data.plan && data.plan.recipe === "letsplay";

  /* --- the header ------------------------------------------------------------------- */

  function header() {
    const p = data && data.plan;
    if (!p) { actions.replaceChildren(); return; }
    line(`${p.title} · ${p.line}`);
    const undo = el("button", { class: "btn quiet", type: "button", onclick: () => step("undo"),
                                title: data.undo ? `Undo ${data.undo}` : "Nothing to undo" },
                    "↶ Undo");
    const redo = el("button", { class: "btn quiet", type: "button", onclick: () => step("redo"),
                                title: data.redo ? `Redo ${data.redo}` : "Nothing to redo" },
                    "↷ Redo");
    undo.disabled = !data.undo;
    redo.disabled = !data.redo;
    fill(actions, undo, redo,
      el("button", { class: "btn", type: "button", onclick: preview }, "Quick preview"),
      el("button", { class: "btn quiet", type: "button", onclick: today,
                     title: "Rendering, captions, effects, titles and a Let's Play's Part "
                            + "Planner are still in today's Review until they're rebuilt" },
         "Today's Review"));
  }

  async function today() {
    if (planId) await post("/api/review/classic", { plan: planId });
    window.aie.classic("Review");
  }

  /* --- the whole screen --------------------------------------------------------------- */

  async function load() {
    let found;
    try {
      const reply = await fetch(`/api/review?plan=${encodeURIComponent(planId || "")}`);
      if (!reply.ok) return;
      found = await reply.json();
    } catch (e) {
      return;
    }
    delete found.version;
    const now = JSON.stringify(found);
    if (now === seen) return;
    const other = !data || !found.plan || !data.plan || found.plan.id !== data.plan.id;
    seen = now;
    data = found;
    if (!data.plan) return empty();
    planId = data.plan.id;
    if (other) {
      selected = null;
      clip = null;
      cut = null;
      whole = false;
      moreOpen = false;
      if (tab === "clips" && lets()) tab = "parts";
      if (tab === "parts" && !lets()) tab = "clips";
      build();
    }
    if (selected !== null && selected >= data.rows.length) selected = data.rows.length - 1;
    header();
    plansBox();
    lengthBar();
    tabs();
    if (selected !== null) details(false);
    else if (other) stageIdle();
  }

  function empty() {
    actions.replaceChildren();
    line("No drafts waiting");
    body.replaceChildren(el("div", { class: "panel" }, el("div", { class: "empty" },
      el("b", {}, "No video plans yet"),
      el("p", {}, "Make one in Create video: it opens here, ready to change before anything "
                  + "renders."),
      el("button", { class: "btn primary", type: "button",
                     onclick: () => window.aie.show("create") }, "Create video"))));
  }

  function build() {
    body.replaceChildren(
      el("section", { class: "sec rv-plans" },
        el("div", { class: "row tight rv-plan-row" },
          el("select", { class: "input", id: "rv-plan", "aria-label": "Video plan",
                         onchange: (e) => { planId = e.target.value; seen = ""; data = null; load(); } }),
          el("button", { class: "btn quiet", type: "button", onclick: deleteOne }, "Delete this plan")),
        el("ul", { class: "rv-notes", id: "rv-notes" }),
        el("details", { class: "lib-more rv-several", id: "rv-several",
                        ontoggle: (e) => { if (e.target.open) several(); } },
          el("summary", {}, "Delete several plans"),
          el("div", { id: "rv-several-in" }))),
      stage(),
      el("section", { class: "sec rv-bar-sec" },
        el("p", { class: "rv-bar-note", id: "rv-bar-note" }),
        el("div", { class: "lenbar", id: "rv-bar" }),
        el("div", { class: "legend", id: "rv-legend" })),
      el("section", { class: "sec" },
        el("div", { class: "seg rv-tabs", id: "rv-tabs", role: "tablist" }),
        el("div", { id: "rv-tab" })));
  }

  /* --- the plan, and deleting plans (only when you say so, asked once more) ----------- */

  function plansBox() {
    const box = $("#rv-plan");
    box.replaceChildren(...data.plans.map((p) => el("option", { value: p.id }, p.label)));
    box.value = data.plan.id;
    $("#rv-notes").replaceChildren(...data.plan.notes.map((n) => el("li", {}, n)));
    if ($("#rv-several").open) several();
  }

  async function deleteOne() {
    const p = data.plan;
    const made = p.rendered ? "Its finished video stays in your output folder, and its clips "
      + "stay marked as used. " : "";
    if (!window.confirm(`Delete "${p.title}" (${p.id}) from the list?\n\n${made}Its clips, `
                        + "your ratings and what AI-Editor learns from them all stay. This "
                        + "can't be undone.")) return;
    const said = await post("/api/review/delete", { plans: [p.id] });
    if (said.said) toast(said.said);
    planId = null;
    seen = "";
    load();
  }

  function several() {
    const inside = $("#rv-several-in");
    for (const id of [...ticked]) if (!data.plans.some((p) => p.id === id)) ticked.delete(id);
    const box = (p) => {
      const on = ticked.has(p.id);
      const b = el("button", { type: "button", class: "check", role: "checkbox",
                               "aria-checked": String(on), onclick: () => {
        if (ticked.has(p.id)) ticked.delete(p.id); else ticked.add(p.id);
        several();
      } }, el("i", { class: on ? "tick" : "" }), p.label);
      return b;
    };
    inside.replaceChildren(
      el("p", { class: "note" }, "Newest first. Only the plans leave the list: finished videos "
        + "stay in your output folder, and clips and ratings stay."),
      el("div", { class: "rv-tick-list" }, ...data.plans.map(box)),
      el("div", { class: "row tight" },
        el("button", { class: "btn quiet", type: "button", onclick: () => {
          data.plans.filter((p) => p.status === "draft").forEach((p) => ticked.add(p.id));
          several();
        } }, "Tick every draft"),
        el("button", { class: "btn quiet", type: "button",
                       onclick: () => { ticked.clear(); several(); } }, "Untick all"),
        el("button", { class: "btn", type: "button", onclick: deleteTicked },
           "Delete the ticked plans")));
  }

  async function deleteTicked() {
    if (!ticked.size) return toast("Tick the plans to delete first.");
    const rendered = data.plans.filter((p) => ticked.has(p.id) && p.status === "rendered").length;
    const n = ticked.size;
    const made = rendered ? `${rendered} of them ${rendered === 1 ? "is" : "are"} rendered: the `
      + "finished videos stay in your output folder, and their clips stay marked as used. " : "";
    if (!window.confirm(`Delete ${n} plan${n === 1 ? "" : "s"} from the list?\n\n${made}Their `
                        + "clips, your ratings and what AI-Editor learns from them all stay. "
                        + "This can't be undone.")) return;
    const said = await post("/api/review/delete", { plans: [...ticked] });
    if (said.said) toast(said.said);
    if (ticked.has(planId)) planId = null;
    ticked.clear();
    seen = "";
    load();
  }

  /* --- the stage: player, trim buttons, details ---------------------------------------- */

  function stage() {
    const video = el("video", { class: "clip-video", id: "rv-video", controls: "",
                                preload: "metadata" });
    video.addEventListener("timeupdate", () => {
      if (stopAt !== null && video.currentTime >= stopAt) { video.pause(); stopAt = null; }
    });
    const btn = (label, onclick, quiet) => el("button", {
      class: quiet ? "btn quiet" : "btn", type: "button", onclick }, label);
    return el("section", { class: "stage clip-stage rv-stage", id: "rv-stage" },
      el("div", { class: "view" },
        el("div", { class: "clip-screen" }, video,
           el("div", { class: "clip-empty", id: "rv-empty" }, "")),
        el("div", { class: "row tight rv-trim", id: "rv-trim" },
          btn("◀ 1 s", () => nudge(-1)), btn("1 s ▶", () => nudge(1)),
          btn("Trim start to here", () => trimHere("start"), true),
          btn("Trim end to here", () => trimHere("end"), true),
          el("div", { class: "spacer" }),
          btn("Watch the whole video", watchWhole, true)),
        el("div", { class: "rv-cut", id: "rv-cut", hidden: "" })),
      el("div", { class: "meta", id: "rv-meta" }));
  }

  function stageIdle() {
    const video = $("#rv-video");
    video.pause();
    if (data.preview) {
      play(data.preview.url, 0, null, false);
      showNote(data.preview.note);
    } else {
      video.hidden = true;
      $("#rv-empty").hidden = false;
      $("#rv-empty").textContent = lets()
        ? "Click a part to watch how it starts. Quick preview shows a whole part."
        : "Click a clip to watch it here, or make a quick preview of the whole video.";
    }
    whole = !!data.preview;
    $("#rv-trim").hidden = lets();
    $("#rv-meta").replaceChildren(el("p", { class: "note" }, lets()
      ? "A Let's Play's parts are moved in the Part Planner, which is still in Today's Review."
      : "Click a clip in the list to see its details and change its cut."));
  }

  function showNote(text) {
    const box = $("#rv-cut");
    box.hidden = !text;
    box.replaceChildren(el("span", { class: "note" }, text || ""));
  }

  function play(url, start, end, go = true) {
    const video = $("#rv-video");
    $("#rv-empty").hidden = true;
    video.hidden = false;
    const at = () => {
      video.currentTime = Math.max(0, start);
      stopAt = end;
      if (go) video.play().catch(() => {});
    };
    if (video.getAttribute("src") !== url) {
      video.src = url;
      video.addEventListener("loadedmetadata", at, { once: true });
    } else {
      at();
    }
  }

  function noVideo(text) {
    const video = $("#rv-video");
    video.pause();
    video.hidden = true;
    $("#rv-empty").hidden = false;
    $("#rv-empty").textContent = text;
  }

  async function pick(index) {
    selected = index;
    cut = null;
    moreOpen = false;
    whole = false;
    markRow();
    await details(true);
  }

  async function details(start) {
    const index = selected;
    let found;
    try {
      const reply = await fetch(`/api/review/${encodeURIComponent(planId)}/clip/${index}`);
      if (!reply.ok) return;
      found = await reply.json();
    } catch (e) {
      return;
    }
    if (index !== selected) return;
    const moved = !clip || clip.start !== found.start || clip.end !== found.end
      || clip.rid !== found.rid;
    clip = found;
    $("#rv-trim").hidden = lets();
    if (start || (moved && !whole)) {
      if (!clip.video) noVideo("This recording has no preview copy to play.");
      else play(clip.video, clip.start, clip.end, start);
    }
    meta();
    cutLine();
  }

  function meta() {
    const parts = clip.facts.map(([k, v]) => el("div", { class: "kv" },
      el("span", {}, k), el("b", {}, v)));
    const edits = data.plan.editable && !lets();
    const buttons = el("div", { class: "row tight rv-meta-buttons" },
      edits ? el("button", { class: "btn", type: "button",
                             onclick: () => change("remove", selected) }, "Remove") : null,
      lets() ? null : el("button", { class: "btn quiet", type: "button", "aria-expanded":
        String(moreOpen), onclick: () => { moreOpen = !moreOpen; meta(); } }, "More…"));
    fill($("#rv-meta"), ...parts, buttons, moreOpen ? more(edits) : null);
  }

  /* More…: the rest of today's buttons for one clip. */
  function more(edits) {
    const start = el("input", { class: "input", type: "text", "aria-label": "Start" });
    const end = el("input", { class: "input", type: "text", "aria-label": "End" });
    start.value = clockOf(cut ? cut.start : clip.start);
    end.value = clockOf(cut ? cut.end : clip.end);
    const typed = () => {
      const a = secondsOf(start.value);
      const b = secondsOf(end.value);
      if (a === null || b === null) return toast("Write the times like 1:04:18 or 4:18.");
      setCut(a, b);
    };
    [start, end].forEach((box) => box.addEventListener("keydown", (e) => {
      if (e.key === "Enter") typed();
    }));
    const to = el("input", { class: "input rv-to", type: "number", min: "1", placeholder: "#",
                             "aria-label": "Move it to number" });
    return el("div", { class: "rv-more" },
      edits && !clip.teaser ? el("button", { class: "btn quiet", type: "button",
        onclick: () => change("teaser", selected) }, "Use as teaser") : null,
      edits && !clip.teaser ? el("div", { class: "row tight" }, to,
        el("button", { class: "btn quiet", type: "button",
                       onclick: () => change("move_to", selected, to.value) }, "Move to #"))
        : null,
      el("button", { class: "btn quiet", type: "button", onclick: () => {
        const c = cut || clip;
        whole = false;
        play(clip.video, c.start - 30, c.end + 30);
      } }, "Watch 30 s either side"),
      el("div", { class: "rv-times" },
        el("label", {}, "Start", start), el("label", {}, "End", end),
        el("button", { class: "btn quiet", type: "button", onclick: typed }, "Use these times")));
  }

  /* --- trimming: a new cut, saved only when you say ----------------------------------- */

  function nudge(by) {
    const video = $("#rv-video");
    if (video.hidden) return;
    video.pause();
    video.currentTime = Math.max(0, video.currentTime + by);
    stopAt = null;
  }

  function trimHere(edge) {
    if (!clip || whole || lets()) {
      return toast("Click a clip in the list first: trimming changes one clip.");
    }
    const video = $("#rv-video");
    // Not loaded, the player says 0:00: a trim from there made a 10-minute clip (demo, 1 Nov).
    if (video.hidden || video.readyState < 1) {
      return toast("The video hasn't loaded, so there's no point to trim to. Play the clip first.");
    }
    const t = video.currentTime;
    const c = cut || clip;
    setCut(edge === "start" ? t : c.start, edge === "end" ? t : c.end);
  }

  function setCut(start, end) {
    if (end - start < 1) return toast("The end must be after the start.");
    cut = { start, end };
    if (Math.abs(start - clip.start) < 0.05 && Math.abs(end - clip.end) < 0.05) cut = null;
    cutLine();
    if (moreOpen) meta();
  }

  function cutLine() {
    const box = $("#rv-cut");
    if (!cut) { box.hidden = true; box.replaceChildren(); return; }
    box.hidden = false;
    box.replaceChildren(
      el("span", {}, el("b", {}, "New cut: "),
         `${clockOf(cut.start)} – ${clockOf(cut.end)} · ${(cut.end - cut.start).toFixed(1)} s · `,
         el("span", { class: "rv-unsaved" }, "not saved yet")),
      el("div", { class: "spacer" }),
      el("button", { class: "btn quiet", type: "button", onclick: () => {
        whole = false;
        play(clip.video, cut.start, cut.end);
      } }, "Play the new cut"),
      el("button", { class: "btn quiet", type: "button", onclick: () => {
        cut = null;
        cutLine();
        if (moreOpen) meta();
      } }, "Put it back"),
      el("button", { class: "btn primary", type: "button", onclick: saveCut }, "Save the new cut"));
  }

  async function saveCut() {
    const said = await post(`/api/review/${encodeURIComponent(planId)}/cut`, { cut: {
      start: cut.start, end: cut.end, was: [clip.start, clip.end], rid: clip.rid } });
    if (said.said) toast(said.said);
    if (said.selected !== undefined && said.selected !== null) selected = said.selected;
    cut = null;
    seen = "";
    await load();
    if (selected !== null) {
      await details(false);
      play(clip.video, clip.start, clip.end);
    }
  }

  /* --- the length bar ----------------------------------------------------------------- */

  function lengthBar() {
    const b = data.bar;
    const note = $("#rv-bar-note");
    note.className = `rv-bar-note ${b.tone}`;
    note.replaceChildren(el("b", {}, b.strong), b.rest);
    fill($("#rv-bar"),
      ...b.blocks.map((k) => el("div", {
        class: `blk ${k.kind}${k.row === selected ? " sel" : ""}`, "data-row": String(k.row),
        style: `width:${k.width.toFixed(3)}%`, title: k.title, onclick: () => pick(k.row),
      }, k.width > 2.2 ? k.label : "")),
      b.target !== null ? el("div", { class: "target", style: `left:min(${b.target.toFixed(3)}%, calc(100% - 3px))`,
                                      title: "Your target" }) : null);
    const kinds = new Set(b.blocks.map((k) => k.kind));
    const key = (colour, text) => el("span", {}, el("i", { class: `blk ${colour}` }), text);
    fill($("#rv-legend"),
      kinds.has("teaser") ? key("teaser", "Teaser") : null,
      key("c1", lets() ? "Part" : "Clip"),
      kinds.has("replay") ? key("replay", "Slow-motion replay") : null,
      b.target !== null ? el("span", {}, el("i", { class: "rv-target-key" }),
        data.plan.recipe === "shorts" ? "The most a Short can be" : "Your target") : null);
  }

  /* --- the tabs under it: the clips here; the rest in 4F-2 and 4F-3 ------------------- */

  function tabs() {
    const names = [[lets() ? "parts" : "clips", lets() ? "Parts" : "Clips"],
                   ["captions", "Captions"], ["effects", "Effects & music"],
                   ["publish", "Publish"]];
    $("#rv-tabs").replaceChildren(...names.map(([id, label]) => el("button", {
      type: "button", class: id === tab ? "on" : "", role: "tab",
      "aria-selected": String(id === tab), onclick: () => { tab = id; tabs(); },
    }, label)));
    const into = $("#rv-tab");
    if (tab === "clips" || tab === "parts") return list(into);
    into.replaceChildren(el("div", { class: "panel rv-later" },
      el("p", {}, `${LATER[tab]} ${tab === "publish" ? "come" : "comes"} here in the next part `
        + "of the rebuild. For now they're in today's Review, which opens on this plan."),
      el("button", { class: "btn", type: "button", onclick: today }, "Open today's Review")));
  }

  function markRow() {
    body.querySelectorAll("#rv-list tbody tr").forEach((tr) =>
      tr.classList.toggle("on", Number(tr.dataset.row) === selected));
    body.querySelectorAll("#rv-bar .blk").forEach((b) =>
      b.classList.toggle("sel", Number(b.dataset.row) === selected));
  }

  function list(into) {
    const heads = lets() ? ["Part", "Length", "In the recording", "Ends on"]
      : ["", "#", "From", "At", "Length", "Why it's in"];
    const edits = data.plan.editable;
    const table = el("table", {},
      el("thead", {}, el("tr", {}, ...heads.map((h) => el("th", {}, h)))),
      el("tbody", {}, ...data.rows.map((r) => {
        const tr = el("tr", { class: r.n === selected ? "on" : "", "data-row": String(r.n),
                              onclick: () => pick(r.n) },
          ...(lets() ? [el("td", {}, el("b", {}, r.label)), el("td", {}, r.length),
                        el("td", {}, r.at), el("td", {}, r.why)]
            : [el("td", { class: "rv-handle", title: edits && !r.teaser ? "Drag to move" : "" },
                  edits && !r.teaser ? "⠿" : ""),
               el("td", {}, el("b", {}, r.label)),
               el("td", {}, r.from, r.day ? el("span", { class: "note rv-day" }, r.day) : null),
               el("td", {}, r.at), el("td", {}, r.length),
               el("td", { class: r.why.startsWith("⚠") ? "rv-why warn" : "rv-why" }, r.why)]));
        if (edits && !r.teaser) dragging(tr, r.n);
        return tr;
      })));
    const panel = el("div", { class: "panel flush", id: "rv-list" }, table);
    fill(into, panel,
      edits ? el("p", { class: "note rv-tip" }, "Click a clip to watch it and trim it. Drag a "
        + "clip by its row to move it; the teaser always opens the video.") : null,
      edits ? tools() : null);
  }

  function dragging(tr, n) {
    tr.draggable = true;
    tr.addEventListener("dragstart", (e) => {
      dragFrom = n;
      e.dataTransfer.effectAllowed = "move";
      tr.classList.add("rv-dragging");
    });
    tr.addEventListener("dragend", () => tr.classList.remove("rv-dragging"));
    tr.addEventListener("dragover", (e) => { e.preventDefault(); tr.classList.add("rv-over"); });
    tr.addEventListener("dragleave", () => tr.classList.remove("rv-over"));
    tr.addEventListener("drop", (e) => {
      e.preventDefault();
      tr.classList.remove("rv-over");
      if (dragFrom === null || dragFrom === n) return;
      const from = dragFrom;
      dragFrom = null;
      change("move_to", from, n + 1);
    });
  }

  /* Under the list: today's other buttons for the whole video. */
  function tools() {
    const moment = el("input", { class: "input", type: "text",
                                 placeholder: "6:36-6:42, or just where it starts: 6:36",
                                 "aria-label": "The teaser from an exact moment" });
    const add = el("select", { class: "input", "aria-label": "Add a clip that isn't in the video" },
      el("option", { value: "" }, "Loading the clips that could go in…"));
    let spots = {};
    fetch(`/api/review/${encodeURIComponent(planId)}/addable`).then((r) => r.json()).then((f) => {
      spots = Object.fromEntries(f.clips.map((c) => [c.id, c]));
      add.replaceChildren(el("option", { value: "" }, f.clips.length
        ? "Pick a clip to watch it, then add it" : "No other clips from these streams"),
        ...f.clips.map((c) => el("option", { value: c.id }, c.label)));
    }).catch(() => {});
    add.addEventListener("change", () => {
      const c = spots[add.value];
      if (!c) return;
      whole = false;
      if (!c.video) return noVideo("This clip's stream has no preview copy to play.");
      play(c.video, c.start, c.end);
      showNote("Not in the video yet. Add it with Add to video.");
    });
    return el("div", { class: "rv-tools" },
      el("div", { class: "row tight" },
        el("button", { class: "btn quiet", type: "button",
                       onclick: () => change("sort", 0) }, "Sort by time")),
      el("div", { class: "field" }, el("label", {}, "The teaser from an exact moment"),
        el("div", { class: "row tight" }, moment,
          el("button", { class: "btn quiet", type: "button",
                         onclick: () => change("moment", null, moment.value) }, "Use this moment")),
        el("small", {}, "The time in the quick preview or render of this plan as it is now, "
                        + "inside one clip.")),
      el("div", { class: "field" }, el("label", {}, "Add a clip that isn't in the video"),
        el("div", { class: "row tight" }, add,
          el("button", { class: "btn quiet", type: "button",
                         onclick: () => change("add", 0, add.value) }, "Add to video")),
        el("small", {}, "🔖 and 👍 clips first, then the best. Pick one to watch it here.")));
  }

  /* --- changes, Undo and Redo, the quick preview --------------------------------------- */

  async function change(action, index, extra) {
    const said = await post(`/api/review/${encodeURIComponent(planId)}/edit`,
                            { action, index, extra: extra === undefined ? null : extra });
    if (said.said) toast(said.said);
    if (said.selected !== undefined) selected = said.selected;
    cut = null;
    seen = "";
    await load();
    if (selected !== null && data.rows[selected]) markRow();
  }

  async function step(which) {
    const said = await post(`/api/review/${encodeURIComponent(planId)}/${which}`);
    if (said.said) toast(said.said);
    cut = null;
    seen = "";
    load();
  }

  async function preview() {
    const part = lets() && clip ? clip.part : null;
    const said = await post(`/api/review/${encodeURIComponent(planId)}/preview`, { part });
    if (said.said) toast(said.said);
    if (said.job !== undefined && said.job !== null) watch(said.job, planId);
  }

  function watchWhole() {
    if (!data.preview) return toast("Make a quick preview first (Quick preview, at the top).");
    whole = true;
    play(data.preview.url, 0, null);
    showNote(data.preview.note);
  }

  let watcher = null;
  function watch(job, plan) {
    watching.add(JSON.stringify([job, plan]));
    if (!watcher) watcher = setInterval(check, 1500);
  }

  /* Runs while a preview is being made, wherever you are in the window. */
  async function check() {
    for (const key of [...watching]) {
      const [job, plan] = JSON.parse(key);
      let found;
      try {
        found = await (await fetch(`/api/review/job/${job}`)).json();
      } catch (e) {
        continue;
      }
      if (found.state === "waiting") continue;
      watching.delete(key);
      if (found.state === "failed") { toast(found.error); continue; }
      if (found.state !== "ready") continue;
      if (window.aie.current() === "review" && body && planId === plan && $("#rv-video")) {
        toast("Your quick preview is ready.");
        seen = "";
        await load();
        whole = true;
        play(found.url, 0, null);
        showNote(data.preview ? data.preview.note : "");
      } else {
        toast("Your quick preview is ready.", { label: "Watch it in Review",
          onclick: () => window.aie.show("review", { plan }) });
      }
    }
    if (!watching.size) { clearInterval(watcher); watcher = null; }
  }

  /* --- opened and closed by the frame ------------------------------------------------- */

  NATIVE.review = {
    open(into, headerActions, extra) {
      body = into;
      actions = headerActions;
      if (extra && extra.plan) planId = extra.plan;
      seen = "";
      data = null;
      body.replaceChildren();
      load();
      clearInterval(timer);
      timer = setInterval(load, EVERY_MS);
    },
    close() {
      clearInterval(timer);
      timer = null;
      const video = body && body.querySelector("#rv-video");
      if (video) video.pause();
    },
  };
})();
