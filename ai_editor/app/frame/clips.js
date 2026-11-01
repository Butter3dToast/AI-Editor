/* Clips, rebuilt in the new design (Phase 4D; mockups/Clips.dc.html).

   The designer's stage: the player with the rating buttons under it and the
   clip's details beside it, pinned at the top while the list scrolls under it
   (the creator, 1 Nov: no scrolling up and down). A rating moves on to the
   next clip and plays it; the keyboard rates too: 1 👍, 2 🔖, 3 👎, 0 clear,
   ↑ ↓ the clip before or after, Space play or pause. Answers come from
   clips_screen.py; a rating is kept exactly as today's Clips keeps it. */
"use strict";

(() => {
  const { el, toast, post, line, NATIVE } = window.aie;
  const EVERY_MS = 5000;
  const SHOWS = [["unused", "Not used yet"], ["all", "All"], ["rated", "Rated"]];
  const KEYS = { "1": 1, "2": 2, "3": -1, "0": null };

  let body = null;
  let actions = null;
  let timer = null;
  let recs = [];
  let rec = null;                // the recording shown
  let show = "unused";
  let deleted = false;
  let data = null;               // its clips
  let seen = "";
  let picked = null;             // the clip on the stage
  let stopAt = null;             // where it ends: the player pauses there
  let knowsOpen = false;

  const $ = (sel) => body.querySelector(sel);

  /* --- the stage: player, rating buttons, details --------------------------------- */

  function stage() {
    const video = el("video", { class: "clip-video", id: "clip-video", controls: "",
                                preload: "metadata" });
    video.addEventListener("timeupdate", () => {
      if (stopAt !== null && video.currentTime >= stopAt) { video.pause(); stopAt = null; }
    });
    const rate = (rating, label) => el("button", { class: "btn", type: "button",
      onclick: () => rateClip(rating) }, label);
    return el("section", { class: "stage clip-stage", id: "clip-stage" },
      el("div", { class: "view" },
        el("div", { class: "clip-screen" }, video,
           el("div", { class: "clip-empty", id: "clip-empty" }, "Pick a clip to watch it here.")),
        el("div", { class: "row tight clip-rate" },
          rate(1, "👍 Good clip"), rate(2, "🔖 Next video"), rate(-1, "👎 Not good"),
          el("div", { class: "spacer" }),
          el("button", { class: "btn quiet", type: "button", onclick: () => rateClip(null) },
             "Clear rating")),
        el("p", { class: "note clip-keys" },
          "Keys: 1 👍 · 2 🔖 · 3 👎 · 0 clear · ↑ ↓ the clip before or after · Space play or "
          + "pause. A rating moves on to the next clip.")),
      el("div", { class: "meta", id: "clip-meta" }));
  }

  function play(clip, start) {
    const video = $("#clip-video");
    const empty = $("#clip-empty");
    if (!data.video) {
      video.hidden = true;
      empty.hidden = false;
      empty.textContent = "This recording has no preview copy to play.";
      return;
    }
    video.hidden = false;
    empty.hidden = true;
    const go = () => {
      video.currentTime = clip.start;
      stopAt = clip.end;
      if (start) video.play().catch(() => {});
    };
    if (video.getAttribute("src") !== data.video) {
      video.src = data.video;
      video.addEventListener("loadedmetadata", go, { once: true });
    } else {
      go();
    }
  }

  async function meta(id) {
    let found;
    try {
      const reply = await fetch(`/api/clips/clip/${encodeURIComponent(id)}`);
      if (!reply.ok) return;
      found = await reply.json();
    } catch (e) {
      return;
    }
    if (id !== picked) return;
    const listed = data.clips.find((c) => c.id === id) || {};
    // A labelled part under the facts, in the design's small capitals (as Library's).
    const part = (label, ...lines) => el("section", { class: "clip-part" },
      el("h4", {}, label), ...lines.filter(Boolean).map((text) => el("p", {}, text)));
    const parts = [
      el("div", { class: "kv" }, el("span", {}, "Clip"),
         el("b", {}, [listed.n ? `#${listed.n}` : "", listed.length, found.rated]
           .filter(Boolean).join(" · "))),
      ...found.facts.map(([k, v]) => el("div", { class: "kv" }, el("span", {}, k), el("b", {}, v))),
    ];
    if (found.ai) {
      parts.push(part(`AI says ${found.ai.stars}`, found.ai.summary, found.ai.reason,
                      found.ai.alone + (found.ai.tags.length ? ` · ${found.ai.tags.join(", ")}` : "")));
    }
    if (found.league.length) {
      parts.push(part("League", ...found.league.map(([t, text]) => `${t} · ${text}`)));
    }
    parts.push(part("You said", found.said ? `“${found.said}”` : "No words in this clip."));
    if (found.used_in.length) parts.push(part("Used in", found.used_in.join(", ")));
    $("#clip-meta").replaceChildren(...parts);   // never a null: that showed as "null"
  }

  function pick(id, start) {
    const clip = data && data.clips.find((c) => c.id === id);
    if (!clip) return;
    picked = id;
    body.querySelectorAll("#clip-list tbody tr").forEach((tr) => {
      const on = tr.dataset.id === id;
      tr.classList.toggle("on", on);
      if (on && start) {
        tr.style.scrollMarginTop = `${$("#clip-stage").offsetHeight + 8}px`;
        tr.scrollIntoView({ block: "nearest" });
      }
    });
    play(clip, start);
    meta(id);
  }

  function move(by) {
    if (!data || !data.clips.length) return;
    const at = data.clips.findIndex((c) => c.id === picked);
    const next = Math.max(0, Math.min(data.clips.length - 1, at < 0 ? 0 : at + by));
    pick(data.clips[next].id, true);
  }

  async function rateClip(rating) {
    if (!picked) { toast("Click a clip first."); return; }
    const before = data.clips.map((c) => c.id);
    const was = picked;
    const said = await post(`/api/clips/clip/${encodeURIComponent(was)}/rate`, { rating });
    if (said.said) toast(said.said);
    await load(true);
    const now = new Set(data.clips.map((c) => c.id));
    let next = null;
    if (rating !== null) {      // on to the next clip, and play it
      next = before.slice(before.indexOf(was) + 1).find((id) => now.has(id));
    } else if (now.has(was)) {
      next = was;
    }
    if (!next && data.clips.length) {
      next = data.clips[Math.min(before.indexOf(was), data.clips.length - 1)].id;
    }
    if (next) pick(next, rating !== null);
  }

  /* --- the list ---------------------------------------------------------------------- */

  function table() {
    const panel = $("#clip-list");
    $("#clip-totals").textContent = data.totals;
    line(data.line);
    if (!data.clips.length) {
      panel.className = "panel";
      const everyUsed = show === "unused" && data.line.includes(" 0 not used yet");
      panel.replaceChildren(el("div", { class: "empty" },
        el("b", {}, everyUsed ? "Every clip is in a video" : "No clips here"),
        el("p", {}, everyUsed
          ? "All of this recording's clips have been used. Rendering uses clips up so the "
            + "next video starts fresh: turn reuse on in Create video if you want them again."
          : "Try All, or another recording.")));
      return;
    }
    panel.className = "panel flush";
    panel.replaceChildren(el("table", {},
      el("thead", {}, el("tr", {}, ...["#", "At", "Length", "Score", "What happens", "Rated"]
        .map((h) => el("th", {}, h)))),
      el("tbody", {}, ...data.clips.map((c) => el("tr", {
        class: c.id === picked ? "on" : "", "data-id": c.id, onclick: () => pick(c.id, true),
      },
        el("td", {}, el("b", {}, String(c.n))),
        el("td", {}, c.at),
        el("td", {}, c.length),
        el("td", {}, c.score),
        el("td", { class: "clip-what" }, (c.marked ? "⭐ " : "") + c.what),
        el("td", {}, c.rated || "—"))))));
  }

  async function load(force) {
    if (rec === null) return;
    let found;
    try {
      const reply = await fetch(`/api/clips/${rec}?show=${show}`);
      if (!reply.ok) return;
      found = await reply.json();
    } catch (e) {
      return;
    }
    const now = JSON.stringify([found.clips, found.totals, found.line]);
    if (!force && now === seen) return;
    seen = now;
    data = found;
    table();
    if (picked === null && data.clips.length) pick(data.clips[0].id, false);
    else if (picked !== null && data.clips.some((c) => c.id === picked)) meta(picked);
  }

  /* --- the recording, the filter, How well AI-Editor knows you ------------------------ */

  async function recordings() {
    try {
      recs = (await (await fetch(`/api/clips/recordings?deleted=${deleted}`)).json()).recordings;
    } catch (e) {
      recs = [];
    }
    if (!recs.some((r) => r.id === rec)) rec = recs.length ? recs[0].id : null;
  }

  function chooser() {
    const select = el("select", { class: "input clip-rec", "aria-label": "Recording" },
      ...recs.map((r) => el("option", { value: String(r.id) },
        `${r.name} · ${r.day}` + (r.game && r.game !== r.name ? ` · ${r.game}` : "")
        + (r.gone ? " (video deleted)" : ""))));
    if (rec !== null) select.value = String(rec);
    select.addEventListener("change", () => {
      rec = Number(select.value);
      picked = null;
      seen = "";
      load(true);
    });
    return select;
  }

  async function knows(box) {
    let found;
    try {
      found = await (await fetch("/api/clips/knows")).json();
    } catch (e) {
      return;
    }
    if (!found.games.length) {
      box.replaceChildren(el("p", { class: "note" },
        "Nothing to measure yet: rate some clips 👍, 🔖 or 👎 and this fills in, week by week."));
      return;
    }
    box.replaceChildren(
      el("p", { class: "note" }, `Picked right: of AI-Editor's top ${found.top} clips in each `
        + "stream, how many of the ones you rated you liked. Found your favourites: of the clips "
        + `you liked, how many were in its top ${found.top}. Both should climb as it learns. `
        + "🔖 counts as liked."),
      ...found.games.map((g) => el("div", { class: "panel flush clip-knows" },
        el("table", {},
          el("thead", {}, el("tr", {}, ...[g.game, "Streams", "Picked right",
                                          "Found your favourites"].map((h) => el("th", {}, h)))),
          el("tbody", {}, ...g.weeks.map((w) => el("tr", {},
            ...w.map((v, i) => el("td", {}, i === 0 ? `Week of ${v}` : String(v))))))))));
  }

  async function draw() {
    await recordings();
    if (rec === null) {
      line("Nothing analysed yet");
      body.replaceChildren(el("div", { class: "panel" }, el("div", { class: "empty" },
        el("b", {}, "Nothing to show yet"),
        el("p", {}, "Clips come from analysed recordings. Import a recording and analyse it, "
                    + "and its best moments show up here to watch and rate."),
        el("button", { class: "btn primary", type: "button",
                       onclick: () => window.aie.show("import") }, "Import a recording"))));
      return;
    }
    const seg = el("div", { class: "seg", role: "group", "aria-label": "Show" },
      ...SHOWS.map(([id, label]) => el("button", {
        type: "button", class: id === show ? "on" : "", "data-show": id,
        onclick: () => {
          show = id;
          seg.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.show === id));
          seen = "";
          load(true);
        },
      }, label)));
    const gone = el("button", { type: "button", class: "check", role: "checkbox",
                                "aria-checked": String(deleted),
                                title: "Their clips and ratings are kept for learning: rate them "
                                       + "here to teach AI-Editor. No video can be made from them." },
      el("i", { class: deleted ? "tick" : "" }), "Streams whose video is deleted");
    gone.addEventListener("click", async () => {
      deleted = !deleted;
      picked = null;
      seen = "";
      await draw();
    });
    const inside = el("div", { class: "clip-knows-box" });
    const fold = el("details", { class: "lib-more clip-fold" },
      el("summary", {}, "How well AI-Editor knows you"), inside);
    if (knowsOpen) { fold.open = true; knows(inside); }
    fold.addEventListener("toggle", () => { knowsOpen = fold.open; if (fold.open) knows(inside); });
    body.replaceChildren(stage(), el("section", { class: "sec" },
      el("div", { class: "row clip-tools" }, seg, el("div", { class: "spacer" }), gone, chooser()),
      el("p", { class: "note", id: "clip-totals" }),
      el("div", { class: "panel flush", id: "clip-list" }),
      fold));
    const keep = picked;
    picked = null;
    seen = "";
    await load(true);
    if (keep && data && data.clips.some((c) => c.id === keep)) pick(keep, false);
  }

  /* --- the keys ---------------------------------------------------------------------- */

  /* Which key, by name or by place: "ArrowDown" (or the older "Down"), "1" (or the
     number pad's), so a keyboard or a part of the window that names keys its own
     way still works (4D test: the arrows only scrolled the list). */
  function which(event) {
    const key = { Down: "ArrowDown", Up: "ArrowUp", Spacebar: " " }[event.key] || event.key;
    if (key in KEYS || key === "ArrowDown" || key === "ArrowUp" || key === " ") return key;
    const place = /^(?:Digit|Numpad)([0-3])$/.exec(event.code || "");
    if (place) return place[1];
    return { ArrowDown: "ArrowDown", ArrowUp: "ArrowUp", Space: " " }[event.code] || null;
  }

  function keys(event) {
    const there = event.target;
    if (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return;
    if (there.closest && there.closest("input, select, textarea, [contenteditable]")) return;
    const key = which(event);
    if (key === null) return;
    // Ours alone: not the page scrolling, the video's own controls, or a click on
    // the focused button (that would rate the clip again).
    event.preventDefault();
    event.stopPropagation();
    if (key in KEYS) {
      rateClip(KEYS[key]);
    } else if (key === "ArrowDown" || key === "ArrowUp") {
      move(key === "ArrowDown" ? 1 : -1);
    } else if (key === " ") {
      const video = $("#clip-video");
      if (video && !video.hidden) {
        if (video.paused) {
          const clip = data && data.clips.find((c) => c.id === picked);
          if (clip && (video.currentTime < clip.start || video.currentTime >= clip.end - 0.2)) {
            play(clip, true);
          } else {
            video.play().catch(() => {});
          }
        } else {
          video.pause();
        }
      }
    }
  }

  /* --- opened and closed by the frame ------------------------------------------------- */

  NATIVE.clips = {
    open(into, headerActions) {
      body = into;
      actions = headerActions;
      actions.replaceChildren(
        el("button", { class: "btn", type: "button", onclick: async () => {
          if (rec === null) return;
          const said = await post(`/api/clips/${rec}/ai`);
          if (said.said) toast(said.said);
        } }, "Rate with AI"),
        // 4E: opens Create video on Highlights with this stream ticked (a Let's Play: its own).
        el("button", { class: "btn primary", type: "button", onclick: () =>
          window.aie.show("create", rec === null ? undefined : { recording: rec }) }, "Make a video"));
      body.replaceChildren();
      draw();
      // Heard first (capture), before anything on the page can keep a key to itself.
      window.addEventListener("keydown", keys, true);
      clearInterval(timer);
      timer = setInterval(() => load(false), EVERY_MS);
    },
    close() {
      clearInterval(timer);
      timer = null;
      window.removeEventListener("keydown", keys, true);
      const video = body && body.querySelector("#clip-video");
      if (video) video.pause();
    },
  };
})();
