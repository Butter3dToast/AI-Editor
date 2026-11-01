/* Import, rebuilt in the new design (Phase 4C-2; mockups/Import.dc.html).

   Two halves, switched in the header: From this PC (the raw folder's new
   recordings, ticked several at once, or a file anywhere) and From Twitch (a
   VOD checked, then downloaded and imported). Every import is a job in the one
   queue, so several run one after another. Answers come from import_screen.py.
   Only the list redraws as it refreshes: what you've typed and ticked stays. */
"use strict";

(() => {
  const { el, toast, post, NATIVE } = window.aie;
  const EVERY_MS = 4000;

  let body = null;
  let timer = null;
  let half = "pc";
  let files = [];
  let seen = "";
  const ticked = new Set();
  const form = { path: "", analyse: true, more: false, game: "", tracks: "", vod: "",
                 link: "", vodGame: "", chat: true, vodAnalyse: true, checked: null };

  /* A tick box in the designer's style (.check), as a real button. */
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

  function field(label, input, hint) {
    return el("div", { class: "field" }, el("label", {}, label), input,
              hint ? el("small", {}, hint) : null);
  }

  function input(key, attrs) {
    const box = el("input", { class: "input", type: "text", ...attrs });
    box.value = form[key];
    box.addEventListener("input", () => { form[key] = box.value; if (key === "path") count(); });
    return box;
  }

  /* --- From this PC ------------------------------------------------------------------ */

  function chosen() {
    const paths = files.filter((f) => ticked.has(f.path)).map((f) => f.path);
    if (form.path.trim()) paths.push(form.path.trim());
    return [...new Set(paths)];
  }

  function count() {
    const n = chosen().length;
    const go = body.querySelector("#imp-go");
    if (go) go.textContent = n > 1 ? `Import ${n}` : "Import";
    const more = body.querySelector("#imp-more");
    if (!more) return;
    const many = n > 1;
    more.querySelectorAll("input").forEach((box) => { box.disabled = many; });
    more.querySelector(".imp-many").hidden = !many;
  }

  function table() {
    const list = body.querySelector("#imp-list");
    const head = body.querySelector("#imp-head");
    if (!list) return;
    for (const path of [...ticked]) if (!files.some((f) => f.path === path)) ticked.delete(path);
    const ready = files.filter((f) => !f.still_recording && !f.in_jobs).length;
    head.textContent = `${raw} · ` + (files.length
      ? `${files.length} not imported yet` : "nothing new");
    if (!files.length) {
      list.className = "panel";
      list.replaceChildren(el("p", { class: "note" },
        "Nothing new in your raw folder. Recordings OBS saves there show up here by themselves."));
      return;
    }
    list.className = "panel flush";
    list.replaceChildren(el("table", {},
      el("thead", {}, el("tr", {}, el("th", { class: "imp-tick" },
        ready ? el("button", { type: "button", class: "imp-all", onclick: () => {
          const all = files.filter((f) => !f.still_recording && !f.in_jobs);
          const every = all.every((f) => ticked.has(f.path));
          all.forEach((f) => (every ? ticked.delete(f.path) : ticked.add(f.path)));
          table();
          count();
        } }, "All") : ""),
        ...["File", "Length", "Recorded", "Sound", "Game"].map((h) => el("th", {}, h)))),
      el("tbody", {}, ...files.map((f) => {
        const busy = f.still_recording || f.in_jobs;
        const on = ticked.has(f.path);
        return el("tr", {
          class: (on ? "on" : "") + (busy ? " imp-busy" : ""), "data-path": f.path,
          title: f.still_recording ? "OBS may still be recording this: it can be imported a "
            + "minute after it stops changing." : `${f.size} · saved ${f.when}`,
          onclick: busy ? null : () => {
            if (ticked.has(f.path)) ticked.delete(f.path); else ticked.add(f.path);
            table();
            count();
          },
        },
          el("td", { class: "imp-tick" }, busy
            ? el("span", { class: "state wait" }, f.in_jobs ? "In Jobs" : "Recording")
            : el("span", { class: "check", role: "checkbox", "aria-checked": String(on),
                           "aria-label": `Import ${f.name}` }, el("i", { class: on ? "tick" : "" }))),
          el("td", {}, el("b", {}, f.name)),
          el("td", {}, f.length),
          el("td", {}, f.recorded),
          el("td", {}, f.sound),
          el("td", { title: f.game_from ? `From ${f.game_from}` : "" },
             f.game || el("span", { class: "note imp-unknown" },
               "Not known: set it under Game (or in Library after)")));
      }))));
  }

  let raw = "";
  let games = [];

  function pc() {
    const path = input("path", { id: "imp-path", placeholder: "e.g. F:\\AI-Editor\\raw\\2026-10-02 19-55-01.mkv" });
    const browse = el("button", { class: "btn", type: "button", onclick: async () => {
      browse.disabled = true;
      try {
        const found = await post("/api/import/browse", { start: form.path });
        if (found.path) { form.path = found.path; path.value = found.path; count(); }
      } finally {
        browse.disabled = false;
      }
    } }, "Browse…");
    const list = el("datalist", { id: "imp-games" }, ...games.map((g) => el("option", { value: g })));
    const more = el("div", { class: "imp-more", id: "imp-more", hidden: "" },
      el("p", { class: "note imp-many", hidden: "" },
        "These are for one recording at a time. With several ticked, each one's game and "
        + "sound tracks are worked out by themselves."),
      el("div", { class: "row" },
        field("Game", input("game", { list: "imp-games", placeholder: "Worked out by itself" }),
              "Only if it gets it wrong. Type a new game's name if it isn't listed."),
        field("Sound tracks, in order", input("tracks", { placeholder: "mixed,mic,game,voice_chat" }),
              "Leave empty: worked out from your OBS setup (manual chapter 7).")),
      el("div", { class: "row" },
        field("Twitch link", input("vod", { placeholder: "https://www.twitch.tv/videos/…" }),
              "If this is a VOD you downloaded yourself: reads its game and date from Twitch.")),
      list);
    if (form.more) more.hidden = false;
    const go = el("button", { class: "btn primary", type: "button", id: "imp-go", onclick: async () => {
      go.disabled = true;
      try {
        const said = await post("/api/import/files", {
          paths: chosen(), analyse: form.analyse, game: form.game, tracks: form.tracks,
          vod: form.vod });
        if (said.said) toast(said.said);
        if (said.said && said.said.startsWith("Added")) {
          ticked.clear();
          form.path = ""; path.value = "";
        }
        seen = "";
        load();
      } finally {
        go.disabled = false;
      }
    } }, "Import");
    body.replaceChildren(
      el("section", { class: "sec" },
        el("header", {}, el("h3", {}, "New in your raw folder"), el("p", { id: "imp-head" }, raw)),
        el("div", { class: "panel flush", id: "imp-list" })),
      el("section", { class: "sec" },
        el("div", { class: "panel" },
          el("div", { class: "row imp-file" }, field("Or a file anywhere on this PC", path), browse),
          el("div", { class: "row imp-go" },
            tick("Analyse straight after importing", form.analyse, (on) => { form.analyse = on; }),
            el("div", { class: "spacer" }),
            el("button", { class: "btn quiet", type: "button", onclick: () => {
              form.more = !form.more;
              more.hidden = !form.more;
            } }, "Game, sound tracks, Twitch link…"),
            go),
          more),
        el("div", { class: "disclose" },
          "The game is worked out from the file name or the Stream Companion unless you set it "
          + "under Game. It can be changed later in Library.")));
    seen = "";
    table();
    count();
  }

  /* --- From Twitch -------------------------------------------------------------------- */

  function facts(found) {
    if (!found) return null;
    if (found.problem) return el("p", { class: "note imp-problem" }, found.problem);
    return el("div", {},
      el("dl", { class: "facts imp-facts" },
        ...[["Title", found.title], ["Length", found.length], ["Streamed", found.streamed]].map(
          ([k, v]) => el("div", {}, el("dt", {}, k), el("dd", {}, v))),
        el("div", {}, el("dt", {}, "Twitch deletes it"),
           el("dd", {}, el("span", { class: `state ${found.soon ? "wait" : "off"}` }, found.deletes)))),
      el("p", { class: "note imp-who" }, [found.channel, found.game].filter(Boolean).join(" · ")),
      found.warning ? el("p", { class: "note imp-problem" }, found.warning) : null);
  }

  function twitch() {
    const link = input("link", { type: "url", id: "imp-link",
                                 placeholder: "https://www.twitch.tv/videos/1234567890" });
    const shown = el("div", { id: "imp-vod" }, facts(form.checked));
    const check = el("button", { class: "btn", type: "button", onclick: async () => {
      check.disabled = true;
      check.textContent = "Checking…";
      try {
        form.checked = await post("/api/import/twitch/check", { link: form.link });
        shown.replaceChildren(facts(form.checked) || "");
      } finally {
        check.disabled = false;
        check.textContent = "Check";
      }
    } }, "Check");
    const go = el("button", { class: "btn primary", type: "button", onclick: async () => {
      go.disabled = true;
      try {
        const said = await post("/api/import/twitch", { link: form.link, game: form.vodGame,
                                                        chat: form.chat, analyse: form.vodAnalyse });
        if (said.said) toast(said.said);
      } finally {
        go.disabled = false;
      }
    } }, "Download and import");
    body.replaceChildren(el("section", { class: "sec" },
      el("header", {}, el("h3", {}, "A Twitch VOD"),
         el("p", {}, "Downloads it, imports it and attaches the chat")),
      el("div", { class: "panel" },
        el("div", { class: "row imp-file" }, field("Twitch link", link), check),
        shown,
        el("div", { class: "row imp-file" },
          field("Game", input("vodGame", { list: "imp-games", placeholder: "As Twitch says" }),
                "Only if Twitch has it wrong."),
          el("datalist", { id: "imp-games" }, ...games.map((g) => el("option", { value: g })))),
        el("div", { class: "row imp-go" },
          tick("Download the chat too", form.chat, (on) => { form.chat = on; }),
          tick("Analyse straight after importing", form.vodAnalyse, (on) => { form.vodAnalyse = on; }),
          el("div", { class: "spacer" }),
          go)),
      el("div", { class: "disclose" },
        "The VOD must be public. For a private one, download it from your Twitch dashboard, "
        + "then import the file on the From this PC side, pasting its link under “Sound tracks, "
        + "Twitch link…” there (next to Import).")));
  }

  /* --- the header's switch, and keeping the list fresh -------------------------------- */

  function switcher(actions) {
    const seg = el("div", { class: "seg", role: "group", "aria-label": "Import from" },
      ...[["pc", "From this PC"], ["twitch", "From Twitch"]].map(([id, label]) =>
        el("button", { type: "button", class: id === half ? "on" : "", "data-half": id,
                       onclick: () => {
                         half = id;
                         seg.querySelectorAll("button").forEach((b) =>
                           b.classList.toggle("on", b.dataset.half === id));
                         draw();
                       } }, label)));
    actions.replaceChildren(seg);
  }

  function draw() {
    if (half === "pc") pc(); else twitch();
  }

  async function load() {
    let found;
    try {
      found = await (await fetch("/api/import")).json();
    } catch (e) {
      return;
    }
    const first = !raw;
    files = found.files;
    raw = found.raw;
    games = found.games;
    if (first) return draw();
    const now = JSON.stringify(files);
    if (now === seen) return;
    seen = now;
    if (half === "pc") { table(); count(); }
  }

  NATIVE.import = {
    open(into, actions) {
      body = into;
      raw = "";
      switcher(actions);
      body.replaceChildren();
      load();
      clearInterval(timer);
      timer = setInterval(load, EVERY_MS);
    },
    close() {
      clearInterval(timer);
      timer = null;
    },
  };
})();
