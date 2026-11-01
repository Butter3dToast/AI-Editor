/* Create video, rebuilt in the new design (Phase 4E; mockups/Create.dc.html).

   Highlights, Let's Play or Shorts in the header. Highlights: the game, length,
   style profile and which clips, then "What it will use", the streams in reach,
   oldest first; tick streams there to use only those (the creator, 1 Nov).
   Let's Play and Shorts: click the recording in the list. Make the plan starts
   the same job today's Create video starts; when the plan is ready it opens in
   Review if you're still here, else a note offers to open it. Answers come from
   create_screen.py. Only the lists redraw as they refresh: what you've typed,
   picked and ticked stays. */
"use strict";

(() => {
  const { el, toast, post, line, NATIVE } = window.aie;
  const EVERY_MS = 5000;
  const KINDS = [["highlights", "Highlights"], ["letsplay", "Let's Play"], ["shorts", "Shorts"]];
  const ALL_STREAMS = "All my streams";
  const NO_STYLE = -1;

  let body = null;
  let actions = null;
  let timer = null;
  let kind = "highlights";
  let data = null;
  let seen = "";
  let built = "";               // the kind whose form is on screen
  const form = { game: ALL_STREAMS, minutes: null, which: null, reuse: false, style: null,
                 recording: null, streams: false };
  const ticked = new Set();
  let handedOver = null;        // the stream Clips' Make a video brought

  const $ = (sel) => body.querySelector(sel);

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

  function field(label, input, hint, id) {
    return el("div", { class: "field" }, el("label", id ? { for: id } : {}, label), input,
              hint ? el("small", {}, hint) : null);
  }

  /* --- the header: which kind of video ---------------------------------------------- */

  function header() {
    const seg = el("div", { class: "seg", role: "group", "aria-label": "What to make" },
      ...KINDS.map(([id, label]) => el("button", {
        type: "button", class: id === kind ? "on" : "", "data-kind": id,
        onclick: () => {
          if (kind === id) return;
          kind = id;
          form.style = null;
          form.recording = null;
          seg.querySelectorAll("button").forEach((b) =>
            b.classList.toggle("on", b.dataset.kind === id));
          reload();
        },
      }, label)));
    actions.replaceChildren(seg);
  }

  function reload() {
    seen = "";
    built = "";
    data = null;
    body.replaceChildren();
    load();
  }

  async function load() {
    const query = new URLSearchParams({ reuse: form.reuse, streams: form.streams });
    if (kind === "highlights") query.set("game", form.game);
    if (form.recording !== null) query.set("recording", form.recording);
    const asked = kind;
    let found;
    try {
      const reply = await fetch(`/api/create/${kind}?${query}`);
      if (!reply.ok) return;
      found = await reply.json();
    } catch (e) {
      return;
    }
    if (asked !== kind) return;
    const now = JSON.stringify(found);
    if (now === seen && built === kind) return;
    seen = now;
    data = found;
    if (kind === "highlights") {
      if (form.minutes === null) form.minutes = data.minutes;
      if (form.which === null) form.which = data.which;
      const ids = new Set(data.rows.map((r) => r.id));
      if (handedOver !== null) {
        if (ids.has(handedOver)) ticked.add(handedOver);
        else toast("That stream's video is deleted or moved, so no video can be made from it.");
        handedOver = null;
      }
      for (const id of [...ticked]) if (!ids.has(id)) ticked.delete(id);
    }
    if (built !== kind) build();
    styles();
    table();
  }

  /* --- the form ---------------------------------------------------------------------- */

  function build() {
    built = kind;
    if (kind === "highlights") return buildHighlights();
    const lets = kind === "letsplay";
    body.replaceChildren(
      el("section", { class: "sec" },
        el("div", { class: "panel" },
          el("div", { class: "row" }, styleField()),
          el("p", { class: "note cv-about" }, lets
            ? "Trimmed (loading screens, silent menus, long pauses) and split into parts of "
              + `about ${Math.round(data.target)} minutes.`
            : "Up to five suggestions, each 15 to 60 seconds and vertical: your Numpad − "
              + "moments first, then the AI's picks that make sense on their own."))),
      el("section", { class: "sec" },
        el("header", {}, el("h3", {}, lets ? "Which episode" : "Which stream or recording"),
           el("p", {}, "Click one to make the plan from it")),
        lets ? el("div", { class: "row tight cv-tools" },
          tick("Show my streams too", form.streams, (on) => { form.streams = on; load(); }))
          : null,
        el("div", { class: "panel flush", id: "cv-list" }),
        go()));
  }

  function buildHighlights() {
    const game = el("select", { class: "input", id: "cv-game" });
    game.addEventListener("change", () => { form.game = game.value; form.style = null; load(); });
    const minutes = el("input", { class: "input", id: "cv-len", type: "number", min: "1",
                                  max: "60", step: "1" });
    minutes.value = form.minutes;
    minutes.addEventListener("input", () => { form.minutes = minutes.value; });
    const which = el("div", { class: "row tight cv-which", role: "group",
                              "aria-label": "Which clips" });
    body.replaceChildren(
      el("section", { class: "sec" },
        el("div", { class: "panel" },
          el("div", { class: "row" },
            field("Game", game, "All my streams: every game you played (Let's Plays stay out). "
                  + "Or just one game.", "cv-game"),
            el("div", { class: "field cv-len" }, el("label", { for: "cv-len" }, "Length"),
               el("div", { class: "row tight cv-minutes" }, minutes,
                  el("span", { class: "note" }, "minutes")),
               el("small", {}, "The least it will be. It may run a little over."))),
          el("div", { class: "row cv-gap" }, styleField()),
          el("div", { class: "row cv-gap" },
            el("div", { class: "field" }, el("label", {}, "Which clips"), which,
               el("small", { id: "cv-which-note" }, "")))),
        el("details", { class: "cv-fold" },
          el("summary", { class: "disclose" },
             "Pick particular streams, or reuse clips already in a video"),
          el("div", { class: "cv-fold-in" },
            el("p", { class: "note" }, "To use only particular streams, tick them in the list "
              + "below. With none ticked, AI-Editor uses every stream in the list."),
            tick("Use clips already in a video", form.reuse, (on) => { form.reuse = on; load(); }),
            el("small", { class: "note" }, "Rendering a video uses its clips up, so the next one "
              + "has fresh clips. Tick this to make another video from the same streams anyway.")))),
      el("section", { class: "sec" },
        el("header", {}, el("h3", {}, "What it will use"), el("p", { id: "cv-order" }, "")),
        el("div", { class: "panel flush", id: "cv-list" }),
        go()));
    game.replaceChildren(...data.games.map((g) => el("option", { value: g }, g)));
    game.value = data.games.includes(form.game) ? form.game : ALL_STREAMS;
  }

  function styleField() {
    const pick = el("select", { class: "input", id: "cv-style" });
    pick.addEventListener("change", () => { form.style = Number(pick.value); });
    return field("Style profile", pick, "Picked by itself when a profile is made for this game "
      + "and kind of video (Style Profiles). It sets the pace and amounts; it never switches "
      + "effects or captions on.", "cv-style");
  }

  /* The profile picked by itself for the game or recording, until you change it. */
  function styles() {
    const pick = $("#cv-style");
    if (!pick) return;
    const auto = data.picked_style === null ? NO_STYLE : data.picked_style;
    pick.replaceChildren(
      el("option", { value: String(NO_STYLE) }, "No profile (my Settings)"),
      ...data.styles.map((s) => el("option", { value: String(s.id) },
        s.id === data.picked_style ? `${s.name} (picked for this game)` : s.name)));
    pick.value = String(form.style === null ? auto : form.style);
  }

  function go() {
    return el("div", { class: "row cv-go" },
      el("button", { class: "btn primary", type: "button", id: "cv-make", onclick: make },
         "Make the plan"),
      el("span", { class: "note", id: "cv-said" }, "Under a minute. It opens in Review."));
  }

  /* --- the lists --------------------------------------------------------------------- */

  function table() {
    if (kind === "highlights") return reach();
    const panel = $("#cv-list");
    const lets = kind === "letsplay";
    if (!data.rows.length) {
      panel.className = "panel";
      panel.replaceChildren(el("p", { class: "note" }, lets
        ? "No analysed Let's Play recording with its video. Tick Show my streams too, or "
          + "add the game to your Let's Play games in Settings."
        : "No analysed recording with its video yet. Import one and analyse it first."));
    } else {
      panel.className = "panel flush";
      const heads = ["Recording", "Game", "Length", "Recorded",
                     ...(lets ? ["Parts"] : ["Your marks", "Clips"])];
      panel.replaceChildren(el("table", {},
        el("thead", {}, el("tr", {}, ...heads.map((h) => el("th", {}, h)))),
        el("tbody", {}, ...data.rows.map((r) => el("tr", {
          class: r.id === form.recording ? "on" : "", "data-id": String(r.id),
          onclick: () => { form.recording = r.id; form.style = null; load(); },
        },
          el("td", {}, el("b", {}, r.name)),
          el("td", {}, r.game || "-"),
          el("td", {}, r.length),
          el("td", {}, r.recorded),
          ...(lets ? [el("td", {}, `about ${r.parts}`)]
                   : [el("td", {}, r.marks ? String(r.marks) : "—"),
                      el("td", {}, String(r.clips))]))))));
    }
    const ready = data.rows.some((r) => r.id === form.recording);
    $("#cv-make").disabled = !ready;
    if (!ready) $("#cv-said").textContent = "Click a recording above first.";
    else if ($("#cv-said").textContent === "Click a recording above first.") {
      $("#cv-said").textContent = "Under a minute. It opens in Review.";
    }
  }

  function reach() {
    const panel = $("#cv-list");
    const rows = data.rows;
    const counted = ticked.size ? rows.filter((r) => ticked.has(r.id)) : rows;
    pills(counted);
    $("#cv-order").textContent = ticked.size
      ? `Only the ${ticked.size === 1 ? "stream" : `${ticked.size} streams`} you ticked`
      : data.oldest ? "Oldest unused clips first, so the next video starts fresh"
        : "The best clips first, from all of these";
    $("#cv-make").disabled = !rows.length;
    if (!rows.length) {
      panel.className = "panel";
      panel.replaceChildren(el("p", { class: "note" }, form.game === ALL_STREAMS
        ? "No analysed stream with its video yet. Import one and analyse it first."
        : `No analysed ${form.game} stream with its video yet.`));
      return;
    }
    panel.className = "panel flush";
    const all = rows.every((r) => ticked.has(r.id));
    panel.replaceChildren(el("table", {},
      el("thead", {}, el("tr", {},
        el("th", { class: "cv-tick" }, el("button", { type: "button", class: "imp-all",
          onclick: () => {
            rows.forEach((r) => (all ? ticked.delete(r.id) : ticked.add(r.id)));
            reach();
          } }, all ? "None" : "All")),
        ...["Stream", "Recorded", form.reuse ? "Clips" : "Clips free", "Your 👍 · 🔖"]
          .map((h) => el("th", {}, h)))),
      el("tbody", {}, ...rows.map((r) => {
        const on = ticked.has(r.id);
        return el("tr", {
          class: (on ? "on" : "") + (r.free ? "" : " cv-spent"), "data-id": String(r.id),
          onclick: () => {
            if (ticked.has(r.id)) ticked.delete(r.id); else ticked.add(r.id);
            reach();
          },
        },
          el("td", { class: "cv-tick" }, el("span", { class: "check", role: "checkbox",
            "aria-checked": String(on), "aria-label": `Use only ${r.name}` },
            el("i", { class: on ? "tick" : "" }))),
          el("td", {}, el("b", {}, r.game || r.name),
             r.game ? el("span", { class: "note cv-name" }, r.name) : null),
          el("td", {}, r.recorded),
          el("td", {}, String(r.free)),
          el("td", {}, r.liked || r.saved ? `${r.liked} · ${r.saved}` : "—"));
      }))));
  }

  /* Which clips: the design's pills, with how many of yours there are to use. */
  function pills(rows) {
    const liked = rows.reduce((n, r) => n + r.liked, 0);
    const saved = rows.reduce((n, r) => n + r.saved, 0);
    const box = $(".cv-which");
    const choices = [["any", "AI-Editor picks"], ["liked", `My 👍 clips (${liked})`],
                     ["saved", `My 🔖 clips (${saved})`]];
    box.replaceChildren(...choices.map(([id, label]) => el("button", {
      type: "button", class: `pill${id === form.which ? " on" : ""}`, "aria-pressed":
        String(id === form.which), onclick: () => { form.which = id; pills(rows); },
    }, label)));
    $("#cv-which-note").textContent = {
      any: "AI-Editor picks the best clips to reach the length. Its own picks never take a "
        + "🔖 clip.",
      liked: "Exactly the clips you gave a 👍, nothing added to reach the length."
        + (liked ? "" : " You have none here yet: rate some in Clips."),
      saved: "The clips you saved for this next video."
        + (saved ? "" : " You have none here yet: press 🔖 Next video in Clips."),
    }[form.which];
  }

  /* --- making the plan, and opening it when it's ready ------------------------------- */

  async function make() {
    const choice = { kind, style: form.style === null
      ? (data.picked_style === null ? NO_STYLE : data.picked_style) : form.style };
    if (kind === "highlights") {
      Object.assign(choice, { game: form.game, minutes: form.minutes, which: form.which,
                              reuse: form.reuse, recordings: [...ticked] });
    } else {
      choice.recording = form.recording;
    }
    const said = await post("/api/create/make", choice);
    if (said.said) {
      toast(said.said);
      const note = $("#cv-said");
      if (note) note.textContent = said.said;
    }
    if (said.job !== undefined && said.job !== null) watch(said.job);
  }

  const waiting = new Set();
  let watcher = null;

  function watch(job) {
    waiting.add(job);
    if (!watcher) watcher = setInterval(check, 1500);
  }

  /* Runs while a plan is being made, wherever you are in the window. */
  async function check() {
    for (const job of [...waiting]) {
      let found;
      try {
        found = await (await fetch(`/api/create/job/${job}`)).json();
      } catch (e) {
        continue;
      }
      if (found.state === "waiting") continue;
      waiting.delete(job);
      if (found.state === "ready") ready();
      else if (found.state === "failed") toast(found.error);
    }
    if (!waiting.size) { clearInterval(watcher); watcher = null; }
  }

  function ready() {
    if (window.aie.current() === "create") {
      toast("Your plan is ready. Here it is in Review.");
      window.aie.show("review");
    } else {
      toast("Your plan is ready.", { label: "Open in Review",
                                     onclick: () => window.aie.show("review") });
    }
    const note = body && $("#cv-said");
    if (note) note.textContent = "Under a minute. It opens in Review.";
  }

  /* --- opened and closed by the frame ------------------------------------------------- */

  NATIVE.create = {
    async open(into, headerActions, extra) {
      body = into;
      actions = headerActions;
      line("Builds a plan you can change before anything renders");
      if (extra && extra.recording !== undefined) {
        // Clips' Make a video: Highlights with that stream ticked, or its Let's Play.
        try {
          const from = await (await fetch(`/api/create/from/${extra.recording}`)).json();
          kind = from.kind;
          form.style = null;
          if (kind === "letsplay") {
            form.recording = from.recording;
          } else {
            form.game = ALL_STREAMS;
            ticked.clear();
            handedOver = from.recording;
          }
        } catch (e) { /* opens as it was left */ }
        if (window.aie.current() !== "create") return;   // gone elsewhere meanwhile
      }
      header();
      reload();
      clearInterval(timer);
      timer = setInterval(load, EVERY_MS);
    },
    close() {
      clearInterval(timer);
      timer = null;
    },
  };
})();
