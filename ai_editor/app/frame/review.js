/* Review, rebuilt in the new design (Phase 4F-1, editing the cut; mockups/Review.dc.html).

   The clip on a stage, pinned at the top while the rest scrolls (as Clips, the
   creator's choice, 1 Nov): the player with the designer's ◀ 1 s, 1 s ▶, Trim
   start to here, Trim end to here and Watch the whole video, the clip's details
   beside it with Remove and More…. Under it the length bar against the target,
   then tabs: the clips (drag to reorder, sort, a teaser from a moment, add a
   clip); Captions (burned in or not, fixing lines) and Effects & music (4F-2);
   Publish (4F-3a: the upload text, and a card per thumbnail frame with its
   Gemini prompt). Until the Part Planner is rebuilt (4F-3b) "Today's Review"
   opens today's screen on the same plan. Render opens a panel to check the
   video first, with Open and Export. Every change is one Undo step, as in
   today's Review. Answers come from review_screen.py, review_finish.py and
   review_publish.py. */
"use strict";

(() => {
  const { el, toast, post, line, NATIVE } = window.aie;
  const EVERY_MS = 5000;

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
  let shownTab = "";             // what the Captions or Effects tab last drew
  let lineKey = null;            // the caption line picked
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
                     title: "Titles, thumbnails and a Let's Play's Part Planner are still in "
                            + "today's Review until they're rebuilt" }, "Today's Review"),
      el("button", { class: "btn primary", type: "button", onclick: renderPanel }, "Render"));
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
    shownTab = "";
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
    lineKey = null;
    markRow();
    if (tab === "captions" || tab === "publish") tabs();
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
      "aria-selected": String(id === tab), onclick: () => { tab = id; shownTab = ""; tabs(); },
    }, label)));
    const into = $("#rv-tab");
    if (tab === "clips" || tab === "parts") { shownTab = ""; return list(into); }
    // Not again on every refresh: what's being typed in a caption line or a title would go.
    const key = JSON.stringify([tab, planId, tab === "captions" ? selected
      : tab === "publish" ? partShown() : null]);
    if (key === shownTab) return;
    shownTab = key;
    ({ captions: captionsTab, effects: effectsTab, publish: publishTab })[tab](into);
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

  /* --- 4F-2: Captions, Effects & music --------------------------------------------- */

  /* A tick box in the designer's style (.check), as a real button (as Import's). */
  function tick(label, on, change) {
    const box = el("button", { type: "button", class: "check", role: "checkbox",
                               "aria-checked": String(on) },
      el("i", { class: on ? "tick" : "" }), label);
    box.addEventListener("click", () => {
      const now = box.getAttribute("aria-checked") !== "true";
      box.setAttribute("aria-checked", String(now));
      box.querySelector("i").className = now ? "tick" : "";
      change(now);
    });
    return box;
  }

  /* One of the plan's own choices: kept, one Undo step, then everything drawn again. */
  async function setting(what, value) {
    const said = await post(`/api/review/${encodeURIComponent(planId)}/set`, { what, value });
    if (said.said) toast(said.said);
    seen = "";
    await load();
    if (selected !== null) details(false);
  }

  async function finishing() {
    try {
      return await (await fetch(`/api/review/${encodeURIComponent(planId)}/finishing`)).json();
    } catch (e) {
      return null;
    }
  }

  async function captionsTab(into) {
    const plan = planId;
    const fin = await finishing();
    if (!fin || plan !== planId) return;
    const box = el("div", { class: "panel rv-finish" },
      tick("Burn in captions (your words)", fin.captions, (on) => setting("captions", on)),
      el("p", { class: "note" }, "Off unless you tick it, and kept with this plan. Friends "
        + "on Discord show in their own colour when it's on."));
    const lines = el("div", { class: "rv-lines", id: "rv-lines" });
    // As today: a 30-minute part has hundreds of lines, so lines are fixed in highlights
    // and Shorts (the creator looked for them on a Let's Play, 1 Nov).
    const why = el("p", { class: "note" }, "Fixing caption lines one by one is for highlights "
      + "and Shorts. A Let's Play's captions are burned in as they were heard.");
    fill(into, box, fin.lets_play ? why : lines);
    if (!fin.lets_play) captionLines(lines);
  }

  async function captionLines(into) {
    if (selected === null) {
      return fill(into, el("p", { class: "note" },
        "Click a clip (in the list or the bar) to fix its caption lines here."));
    }
    const index = selected;
    let found;
    try {
      found = await (await fetch(`/api/review/${encodeURIComponent(planId)}/lines/${index}`)).json();
    } catch (e) {
      return;
    }
    if (index !== selected || !found.lines) return;
    const heading = el("h3", { class: "rv-lines-head" }, `Caption lines in ${found.what}`,
      el("span", { class: "note" }, found.lines.length
        ? ` · ${found.lines.length} line${found.lines.length === 1 ? "" : "s"} · ✎ fixed · ⊘ hidden`
        : " · nobody talks in it"));
    const rows = found.lines.map((ln) => el("button", {
      type: "button", class: `rv-line${ln.key === lineKey ? " on" : ""}${ln.hidden ? " off" : ""}`,
      onclick: () => { lineKey = ln.key; captionLines(into); playLine(ln); },
    }, el("span", { class: "rv-line-at" }, ln.at),
       ln.hidden ? "⊘ " : ln.edited ? "✎ " : "", ln.friend ? "👥 " : "", ln.text));
    const picked = found.lines.find((ln) => ln.key === lineKey);
    fill(into, heading, el("div", { class: "rv-line-list" }, ...rows),
      picked ? lineEditor(picked, into) : null,
      el("p", { class: "note" }, "Click a line to hear it. A fix shows in captions, \"You said\" "
        + "and what the AI writes, everywhere this moment is used."));
  }

  function playLine(ln) {
    if (!clip || !clip.video) return;
    whole = false;
    play(clip.video, Math.max(0, ln.start - 0.3), ln.end + 0.4);
  }

  function lineEditor(ln, into) {
    const text = el("input", { class: "input", type: "text", "aria-label": "This line" });
    text.value = ln.text;
    const act = async (action) => {
      const said = await post(`/api/review/${encodeURIComponent(planId)}/line`,
                              { index: selected, key: ln.key, action, text: text.value });
      if (said.said) toast(said.said);
      // The words may now make a different line: pick the one holding its first word.
      const first = Number(ln.key.split("-")[0]);
      seen = "";
      await load();
      const again = await (await fetch(`/api/review/${encodeURIComponent(planId)}/lines/${selected}`)).json();
      const now = (again.lines || []).find((l) => {
        const [a, b] = l.key.split("-").map(Number);
        return a <= first && first <= b;
      });
      lineKey = now ? now.key : null;
      await captionLines(into);
      if (said.offer) offer(into, said);
    };
    text.addEventListener("keydown", (e) => { if (e.key === "Enter") act("save"); });
    return el("div", { class: "rv-line-edit" },
      el("div", { class: "row tight" }, text,
        el("button", { class: "btn primary", type: "button", onclick: () => act("save") },
           "Save line")),
      el("div", { class: "row tight" },
        el("button", { class: "btn quiet", type: "button", onclick: () => playLine(ln) },
           "Play this line"),
        el("button", { class: "btn quiet", type: "button", onclick: () => act("hide") },
           ln.hidden ? "Show this line" : "Hide this line"),
        ln.edited ? el("button", { class: "btn quiet", type: "button", onclick: () => act("back") },
                       "Put back the original") : null));
  }

  /* "You wrote 'Baron' for 'barren' -- fix it everywhere?" (2D-2) */
  function offer(into, said) {
    const row = el("div", { class: "rv-offer" }, el("span", {}, said.offer_text),
      el("button", { class: "btn", type: "button", onclick: async () => {
        const r = await post("/api/review/remember", { heard: said.offer[0], meant: said.offer[1] });
        if (r.said) toast(r.said);
        row.remove();
        captionLines(into);
      } }, "Yes, everywhere"),
      el("button", { class: "btn quiet", type: "button", onclick: () => row.remove() },
         "No, just here"));
    into.append(row);
  }

  async function effectsTab(into) {
    const plan = planId;
    const fin = await finishing();
    if (!fin || plan !== planId) return;
    const parts = [];
    if (fin.nudge) {
      const n = fin.nudge;
      const answer = async (choice) => {
        const r = await post("/api/review/nudge", { kind: n.kind, choice });
        if (r.said) toast(r.said);
        shownTab = "";
        tabs();
      };
      parts.push(el("div", { class: "rv-offer" }, el("span", {}, n.text),
        n.biggest ? el("button", { class: "btn", type: "button", onclick: () => answer("biggest") },
                       "Only on the biggest moments") : null,
        el("button", { class: "btn quiet", type: "button", onclick: () => answer("never") }, n.never),
        el("button", { class: "btn quiet", type: "button", onclick: () => answer("keep") },
           "Keep as is")));
    }
    if (!fin.lets_play) {
      const chosen = new Set(fin.effects.filter((e) => e.on).map((e) => e.key));
      parts.push(el("section", { class: "rv-group" },
        el("h4", {}, "Effects on the big moments"),
        el("div", { class: "rv-ticks" }, ...fin.effects.map((e) => tick(e.label, e.on, (on) => {
          if (on) chosen.add(e.key); else chosen.delete(e.key);
          setting("effects", [...chosen]);
        }))),
        el("p", { class: "note" }, "For this video. All off unless you tick them. Make a quick "
          + "preview to see and hear them.")));
      if (fin.each.items.length) {
        const kept = new Set(fin.each.items.filter((m) => m.on).map((m) => m.key));
        parts.push(el("section", { class: "rv-group" },
          el("h4", {}, fin.each.suggested ? "Suggested effects on the big moments" : "Each effect"),
          el("div", { class: "rv-ticks rv-moments" }, ...fin.each.items.map((m) =>
            tick(m.label, m.on, (on) => {
              if (on) kept.add(m.key); else kept.delete(m.key);
              setting("each", [...kept]);
            }))),
          el("p", { class: "note" }, fin.each.suggested
            ? "The effects that suit each moment. Tick one to use them there: nothing is used "
              + "until you tick it."
            : "Untick one to leave just that moment out.")));
      }
    }
    if (fin.between) {
      parts.push(el("section", { class: "rv-group" }, el("h4", {}, "Between clips"),
        seg([["cut", "Hard cut"], ["slide", "Slide"]], fin.between, (v) => setting("between", v)),
        el("p", { class: "note" }, "Slide: the next clip slides in over the last.")));
    }
    if (fin.layout) {
      parts.push(el("section", { class: "rv-group" },
        el("h4", {}, "How the game fills the tall frame"),
        seg(fin.layout.choices, fin.layout.value, (v) => setting("layout", v)),
        el("p", { class: "note" }, "Then make a quick preview to see it.")));
    }
    if (fin.lets_play) {
      // The creator's choice in Phase 2: no effects in Let's Plays, and their cuts are
      // meant not to be noticed, so music is the only choice here (asked about, 1 Nov).
      parts.push(el("p", { class: "note" }, "A Let's Play has no effects (your choice), and its "
        + "cuts are always hard cuts so they aren't noticed. Effects and Between clips are for "
        + "highlights; effects for Shorts too."));
    }
    parts.push(el("section", { class: "rv-group" }, el("h4", {}, "Music"),
      tick("Music from your stream", fin.music, (on) => setting("music", on)),
      el("p", { class: "note" }, "Kept under the talking. Quick previews have the stream's "
        + "sound as it was.")));
    fill(into, el("div", { class: "panel rv-finish" }, ...parts));
  }

  /* --- Publish (4F-3a): the upload text, then a card per thumbnail frame -------------- */

  // A Let's Play's Publish follows the part clicked (the creator, 1 Nov).
  const partShown = () => (lets() && selected !== null && data.rows[selected]
    ? data.rows[selected].part : null);

  async function publishTab(into) {
    const plan = planId;
    const part = partShown();
    let pub;
    try {
      pub = await (await fetch(`/api/review/${encodeURIComponent(plan)}/publish`
        + (part ? `?part=${part}` : ""))).json();
    } catch (e) {
      return;
    }
    if (plan !== planId || !pub.kind) return;
    const lp = pub.kind === "letsplay";
    const [episode, guessed] = episodeBox(plan, pub);
    const ask = async (what, which) => {
      const said = await post(`/api/review/${encodeURIComponent(plan)}/publish/write`,
                              { what, episode: lp ? episode.value : null, part: which });
      if (said.said) toast(said.said);
      if (said.job !== undefined && said.job !== null) watchWriting(said.job, plan);
    };
    const button = (label, primary, onclick) => {
      const b = el("button", { class: primary ? "btn primary" : "btn", type: "button", onclick },
                   label);
      b.disabled = !pub.ai;
      return b;
    };
    const head = el("div", { class: "row tight rv-pub-head" },
      lp ? el("div", { class: "seg", role: "group", "aria-label": "Part" },
        ...pub.parts.map((n) => el("button", {
          type: "button", class: n === pub.part ? "on" : "",
          onclick: () => pick(data.rows.findIndex((r) => r.part === n)),
        }, `Part ${n}`))) : null,
      lp ? el("label", { class: "rv-pub-ep" }, "Episode", episode) : null,
      el("div", { class: "spacer" }),
      button(pub.written ? `Write ${lp ? `Part ${pub.part}` : "it"} again`
        : `Write titles, description and chapters${lp ? ` for Part ${pub.part}` : ""}`,
        true, () => ask("publish", pub.part)),
      lp && pub.parts.length > 1
        ? button(`Write all ${pub.parts.length} parts`, false, () => ask("publish", "all")) : null);
    const notes = el("div", { class: "rv-pub-notes" },
      el("p", { class: "note" }, pub.note),
      lp ? guessed : null,
      pub.stale ? el("p", { class: "note rv-warn" }, "The video has changed since, so the "
        + "chapter times may be off: write it again.") : null,
      pub.source ? el("p", { class: "note" }, pub.source) : null,
      pub.ai ? null : el("p", { class: "note rv-warn" }, "The local AI is switched off in "
        + "Settings (AI), so nothing can be written."));
    if (!pub.written) return fill(into, el("div", { class: "panel rv-finish" }, head, notes));

    const title = el("input", { class: "input", type: "text", "aria-label": "Title" });
    title.value = pub.title;
    const description = el("textarea", { class: "input rv-pub-desc", rows: "10",
                                         "aria-label": "Description, with chapters" });
    description.value = pub.description;
    const tags = el("input", { class: "input", type: "text", "aria-label": "Tags" });
    tags.value = pub.tags;
    const ideas = el("div", { class: "rv-pub-ideas" }, ...pub.titles.map((t) => el("button", {
      type: "button", class: `rv-pub-idea${t === pub.title ? " on" : ""}`,
      onclick: (e) => {
        title.value = t;
        ideas.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === e.currentTarget));
      },
    }, t)));
    const field = (label, box, help) => el("div", { class: "rv-group" },
      el("div", { class: "row tight rv-pub-label" }, el("h4", {}, label),
        el("div", { class: "spacer" }),
        el("button", { class: "btn quiet", type: "button",
                       onclick: () => copyText(box.value, `${label} copied.`) }, "Copy")),
      box, help ? el("p", { class: "note" }, help) : null);
    const keep = async () => {
      const said = await post(`/api/review/${encodeURIComponent(plan)}/publish/keep`, {
        part: pub.part, episode: lp ? episode.value : null, title: title.value,
        description: description.value, tags: tags.value });
      if (said.said) toast(said.said);
    };
    const parts = [head, notes,
      pub.titles.length ? el("section", { class: "rv-group" }, el("h4", {}, "Title ideas"),
        ideas, el("p", { class: "note" }, "Click one: it goes in the Title box.")) : null,
      field("Title", title),
      field("Description, with chapters", description,
            "Paste it into YouTube as it is: the chapter times make YouTube's chapters."),
      field("Tags", tags, "YouTube Studio: Show more > Tags."),
      el("div", { class: "row tight" },
        el("button", { class: "btn primary", type: "button", onclick: keep }, "Keep my changes"),
        el("span", { class: "note" }, "Kept over what the AI wrote, and saved beside the "
          + "finished video."))];
    if (pub.link !== null) {
      const link = el("input", { class: "input", type: "url", placeholder: "https://youtu.be/...",
                                 "aria-label": "This video's YouTube link" });
      link.value = pub.link;
      parts.push(el("section", { class: "rv-group" },
        el("h4", {}, `${lp ? `Part ${pub.part}'s` : "This video's"} YouTube link, once uploaded`),
        el("div", { class: "row tight rv-pub-link" }, link,
          el("button", { class: "btn", type: "button", onclick: async () => {
            const said = await post(`/api/review/${encodeURIComponent(plan)}/publish/link`,
                                    { part: pub.part, link: link.value });
            if (said.said) toast(said.said);
          } }, "Save the link")),
        el("p", { class: "note" }, "Shorts made from it then say \"Full video:\" with this link.")));
    }
    if (pub.kind !== "shorts") parts.push(thumbnails(pub, plan, ask));
    fill(into, el("div", { class: "panel rv-finish" }, ...parts));
  }

  /* A Let's Play's episode: kept with the plan once typed, so Render and Publish always
     show the same one; with no number in the name, the next after the game's last
     episode, marked as a guess (1 Nov: videos EP 6, upload text EP 1). */
  function episodeBox(plan, found) {
    const box = el("input", { class: "input rv-episode", type: "number", min: "1",
                              "aria-label": "Episode number" });
    box.value = found.episode ? String(found.episode) : "";
    const note = el("span", { class: "note rv-warn rv-guess" }, found.episode_after
      ? `Guessed: the next after EP ${found.episode_after}. Check it.`
      : found.episode ? "" : "Not in the recording's name: type it.");
    note.hidden = !note.textContent;
    box.addEventListener("change", async () => {
      note.hidden = true;
      await post(`/api/review/${encodeURIComponent(plan)}/episode`, { episode: box.value });
    });
    return [box, note];
  }

  /* Each frame with its prompt: what's pasted into the Gemini app together sits together. */
  function thumbnails(pub, plan, ask) {
    const prompted = pub.thumbnails.filter((t) => t.prompt);
    const cards = pub.thumbnails.map((t, i) => el("figure", { class: "rv-thumb" },
      el("img", { src: t.url, alt: `Thumbnail frame ${i + 1}`, loading: "lazy" }),
      el("figcaption", {},
        el("div", { class: "rv-thumb-why" }, el("b", {}, `${i + 1} · ${t.rating}/10`), ` ${t.reason}`),
        t.prompt ? el("p", { class: "rv-thumb-prompt" }, t.prompt) : null,
        el("div", { class: "row tight rv-thumb-buttons" },
          el("button", { class: "btn", type: "button", onclick: () => copyPicture(t.url) },
             "Copy the picture"),
          t.prompt ? el("button", { class: "btn", type: "button",
            onclick: () => copyText(t.prompt, "Prompt copied: paste it in Gemini with the picture.") },
            "Copy the prompt") : null,
          el("button", { class: "btn quiet", type: "button", onclick: async () => {
            const said = await post(`/api/review/${encodeURIComponent(plan)}/publish/frame`,
                                    { n: t.n, part: pub.part });
            if (said.said) toast(said.said);
          } }, "Open the frame")))));
    const again = el("button", { class: "btn quiet", type: "button",
                                 onclick: () => ask("prompts", pub.part) },
                     prompted.length ? "Write the prompts again" : "Write thumbnail prompts");
    again.disabled = !pub.ai || !pub.thumbnails.length;
    return el("section", { class: "rv-group" },
      el("div", { class: "row tight rv-pub-label" }, el("h4", {}, "Thumbnails for the Gemini app"),
        el("div", { class: "spacer" }), again),
      el("p", { class: "note" }, pub.thumbnails.length
        ? (prompted.length
          ? "Copy the picture and paste it into the Gemini app (Ctrl+V), then copy its prompt "
            + "and paste that too. Nothing is sent from here."
          : "No prompts for these frames yet: Write thumbnail prompts asks the local AI (about "
            + "half a minute).")
        : "No thumbnail frames: write it again to pick them."),
      cards.length ? el("div", { class: "rv-thumbs" }, ...cards) : null);
  }

  async function copyText(text, said) {
    try {
      await navigator.clipboard.writeText(text);
      toast(said);
    } catch (e) {
      toast("Couldn't copy: select the text and press Ctrl+C.");
    }
  }

  async function copyPicture(url) {
    try {
      const picture = await (await fetch(url)).blob();
      const png = picture.type === "image/png" ? picture
        : await new Promise((done) => {    // the clipboard takes PNG only
          const img = new Image();
          img.onload = () => {
            const c = Object.assign(document.createElement("canvas"),
                                    { width: img.naturalWidth, height: img.naturalHeight });
            c.getContext("2d").drawImage(img, 0, 0);
            c.toBlob(done, "image/png");
          };
          img.src = URL.createObjectURL(picture);
        });
      await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
      toast("Picture copied: paste it in Gemini (Ctrl+V).");
    } catch (e) {
      toast("Couldn't copy the picture: use Open the frame and drag it in instead.");
    }
  }

  /* When the writing's done, the tab shows it (wherever you are, a note says so). */
  function watchWriting(job, plan) {
    const check = setInterval(async () => {
      let found;
      try {
        found = await (await fetch(`/api/review/publish-job/${job}`)).json();
      } catch (e) {
        return;
      }
      if (found.state === "waiting") return;
      clearInterval(check);
      if (found.state === "failed") return toast(found.error);
      if (found.state !== "ready") return;
      if (planId === plan && tab === "publish" && window.aie.current() === "review") {
        shownTab = "";
        tabs();
        toast("Written. It's here in Publish.");
      } else {
        toast("The upload text is written.", { label: "Show it", onclick: () => {
          tab = "publish";
          shownTab = "";
          window.aie.show("review", { plan });
        } });
      }
    }, 2000);
  }

  function seg(choices, value, change) {
    const box = el("div", { class: "seg", role: "group" }, ...choices.map(([id, label]) =>
      el("button", { type: "button", class: id === value ? "on" : "", "data-id": id,
                     onclick: () => {
                       box.querySelectorAll("button").forEach((b) =>
                         b.classList.toggle("on", b.dataset.id === id));
                       change(id);
                     } }, label)));
    return box;
  }

  /* --- 4F-2: Render, after a last look; Open and Export -------------------------------- */

  async function renderPanel() {
    let found;
    try {
      found = await (await fetch(`/api/review/${encodeURIComponent(planId)}/render`)).json();
    } catch (e) {
      return;
    }
    const plan = planId;
    const [episode, guessed] = episodeBox(plan, found);
    const part = el("select", { class: "input", "aria-label": "Parts" },
      el("option", { value: "all" }, "All parts"),
      ...found.parts.map((n) => el("option", { value: String(n) }, `Part ${n}`)));
    const choice = () => ({ episode: found.lets_play ? episode.value : null,
                            part: found.lets_play ? part.value : null });
    const dialog = el("dialog", { class: "rv-dialog" });
    const close = () => { dialog.close(); dialog.remove(); };
    const go = async (what) => {
      const said = await post(`/api/review/${encodeURIComponent(plan)}/${what}`, choice());
      if (said.said) toast(said.said);
      if (what === "render" && said.job !== undefined) { close(); watchRender(said.job, plan, choice()); }
    };
    fill(dialog,
      el("h3", {}, `Ready to render "${found.title}"?`),
      el("div", { class: "rv-check" }, ...found.rows.map(([k, v]) =>
        el("div", { class: "kv" }, el("span", {}, k), el("b", {}, v)))),
      found.lets_play ? el("div", { class: "row tight rv-lp" },
        el("label", {}, "Episode", episode), el("label", {}, "Parts", part), guessed) : null,
      el("p", { class: "note" }, "About 3 minutes per 10 minutes of video, in Jobs. "
        + (found.lets_play
          ? "Each part is a video of its own, named with the episode and part number. "
          : found.shorts
            ? "Rendering marks the clips as used in a Short, so the next Shorts carry on with "
              + "fresh ones. "
            : "Rendering marks the clips as used, so the next highlight video carries on with "
              + "fresh ones. ")
        + "Change anything above in the Captions and Effects & music tabs."),
      el("div", { class: "row tight rv-dialog-buttons" },
        el("button", { class: "btn primary", type: "button", onclick: () => go("render") },
           "Render it"),
        el("button", { class: "btn", type: "button", onclick: () => go("open") },
           "Open the finished video"),
        found.shorts ? null : el("button", { class: "btn quiet", type: "button",
                                             onclick: () => go("export") },
                                 "Export to DaVinci Resolve"),
        el("div", { class: "spacer" }),
        el("button", { class: "btn quiet", type: "button", onclick: close }, "Close")));
    dialog.addEventListener("cancel", close);
    document.getElementById("app").append(dialog);   // inside the app: its colours
    dialog.showModal();
  }

  /* When a render finishes: a note with Open it, wherever you are. */
  function watchRender(job, plan, choice) {
    const check = setInterval(async () => {
      let found;
      try {
        found = await (await fetch(`/api/review/render-job/${job}`)).json();
      } catch (e) {
        return;
      }
      if (found.state === "waiting") return;
      clearInterval(check);
      if (found.state === "failed") return toast(found.error);
      if (found.state === "ready") {
        toast("Your video is rendered.", { label: "Open it", onclick: async () => {
          const said = await post(`/api/review/${encodeURIComponent(plan)}/open`, choice);
          if (said.said) toast(said.said);
        } });
      }
    }, 2000);
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
