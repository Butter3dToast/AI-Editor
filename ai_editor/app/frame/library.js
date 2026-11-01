/* Library, rebuilt in the new design (Phase 4C-1; mockups/Main.dc.html).

   Every recording in one list, newest first, with a filter for streams and
   Let's Plays and a search; click one and its details open underneath, with
   Who's talking folded away there. The header's buttons: Import, and Analyse
   for the recording picked. Answers come from library_screen.py. */
"use strict";

(() => {
  const { el, toast, post, NATIVE } = window.aie;
  const EVERY_MS = 3000;

  let body = null;
  let actions = null;
  let timer = null;
  let list = [];
  let seen = "";               // the list as last drawn: redrawn only when it changes
  let picked = null;
  let filter = "all";
  let search = "";
  let shownFacts = "";
  let voicesOpen = false;

  const FILTERS = [["all", "All"], ["streams", "Streams"], ["lets", "Let's Plays"]];

  function shown() {
    const words = search.trim().toLowerCase();
    return list.filter((r) => (filter === "all" || (filter === "lets") === r.lets_play)
      && (!words || `${r.name} ${r.game}`.toLowerCase().includes(words)));
  }

  /* --- the list --------------------------------------------------------------------- */

  function table() {
    const rows = shown();
    const panel = body.querySelector("#lib-list");
    if (!rows.length) {
      panel.className = "panel";
      panel.replaceChildren(el("p", { class: "note" },
        list.length ? "No recordings match." : ""));
      return;
    }
    panel.className = "panel flush";
    panel.replaceChildren(el("table", {},
      el("thead", {}, el("tr", {}, ...["Recording", "Game", "Length", "Recorded", "Clips",
                                       "Status"].map((h) => el("th", {}, h)))),
      el("tbody", {}, ...rows.map((r) => el("tr", {
        class: r.id === picked ? "on" : "", "data-id": String(r.id),
        onclick: () => pick(r.id),
      },
        el("td", {}, el("b", {}, r.name)),
        el("td", {}, r.game || "-"),
        el("td", {}, r.length),
        el("td", {}, r.recorded),
        el("td", {}, r.clips ? String(r.clips) : "—"),
        el("td", {}, el("span", { class: `state ${r.state}` }, r.status)))))));
  }

  function header() {
    actions.replaceChildren(
      el("button", { class: "btn", type: "button", onclick: () => window.aie.show("import") },
         "Import"));
    const row = list.find((r) => r.id === picked);
    if (row && row.status !== "Video deleted") {   // carries on where it stopped, if it did
      actions.append(el("button", { class: "btn primary", type: "button", onclick: analyse },
                        `Analyse #${row.id}`));
    }
  }

  async function load() {
    let found;
    try {
      found = await (await fetch("/api/library")).json();
    } catch (e) {
      return;
    }
    list = found.recordings;
    const now = JSON.stringify([list, filter, search, picked]);
    if (now === seen) return;
    seen = now;
    if (!list.length) return empty();
    if (!body.querySelector("#lib-list")) build();
    if (picked === null || !list.some((r) => r.id === picked)) picked = list[0].id;
    table();
    header();
    details();
  }

  /* --- no recordings yet: the designer's empty screen ------------------------------- */

  function empty() {
    actions.replaceChildren();
    body.replaceChildren(el("div", { class: "panel" }, el("div", { class: "empty" },
      el("b", {}, "No recordings yet"),
      el("p", {}, "Point AI-Editor at a stream or a Let's Play recording and it finds the "
                  + "moments worth keeping. Your file is read where it is and never changed."),
      el("div", { class: "row tight" },
        el("button", { class: "btn primary", type: "button",
                       onclick: () => window.aie.show("import") }, "Import a recording"),
        el("button", { class: "btn quiet", type: "button",
                       onclick: () => window.aie.show("settings") }, "Set your raw folder")))));
  }

  function build() {
    const seg = el("div", { class: "seg", role: "group", "aria-label": "Show" },
      ...FILTERS.map(([id, label]) => el("button", {
        type: "button", class: id === filter ? "on" : "", "data-filter": id,
        onclick: () => {
          filter = id;
          seg.querySelectorAll("button").forEach((b) =>
            b.classList.toggle("on", b.dataset.filter === id));
          seen = "";
          load();
        },
      }, label)));
    const box = el("input", { class: "input lib-search", type: "search",
                              placeholder: "Search recordings", "aria-label": "Search recordings" });
    box.value = search;
    box.addEventListener("input", () => { search = box.value; seen = ""; load(); });
    body.replaceChildren(
      el("section", { class: "sec" },
        el("div", { class: "row lib-tools" }, seg, el("div", { class: "spacer" }), box),
        el("div", { class: "panel flush", id: "lib-list" })),
      el("section", { class: "sec", id: "lib-details" }));
  }

  function pick(id) {
    if (picked !== id) voicesOpen = false;
    picked = id;
    seen = "";
    load();
  }

  /* --- the picked recording ---------------------------------------------------------- */

  async function details() {
    const id = picked;
    let found;
    try {
      const reply = await fetch(`/api/library/${id}`);
      if (!reply.ok) return;
      found = await reply.json();
    } catch (e) {
      return;
    }
    if (id !== picked) return;
    const now = JSON.stringify(found);
    if (now === shownFacts && body.querySelector("#lib-details").childElementCount) return;
    shownFacts = now;
    const facts = found.facts.map(([label, value]) =>
      el("div", {}, el("dt", {}, label), el("dd", {}, value)));
    const buttons = el("div", { class: "row tight lib-buttons" });
    if (found.preview) {
      buttons.append(el("button", { class: "btn", type: "button",
        onclick: async () => { const r = await post(`/api/library/${id}/watch`); if (r.said) toast(r.said); },
      }, "Watch the preview copy"));
    }
    if (!found.gone) {
      buttons.append(el("button", { class: "btn quiet", type: "button",
        onclick: async () => { const r = await post(`/api/library/${id}/explore`); if (r.said) toast(r.said); },
      }, "Show in Explorer"));
    }
    // The game, set or put right here (1 Nov: one came in with none, so it wasn't a Let's
    // Play). A list of every game: a typed box with suggestions only listed the game
    // already in it. "Another game…" opens a box for a new one.
    const OTHER = "(another game)";   // not a game anyone would type
    const known = found.games.includes(found.game) || !found.game ? found.games
      : [found.game, ...found.games];
    const pick = el("select", { class: "input", id: "lib-game-box", "aria-label": "Game" },
      found.game ? null : el("option", { value: "" }, "Not known"),
      ...known.map((g) => el("option", { value: g }, g)),
      el("option", { value: OTHER }, "Another game…"));
    pick.value = found.game || "";
    const typed = el("input", { class: "input", type: "text", hidden: "",
                                placeholder: "The game's name", "aria-label": "Another game" });
    pick.addEventListener("change", () => {
      typed.hidden = pick.value !== OTHER;
      if (!typed.hidden) typed.focus();
    });
    const saveGame = async () => {
      const r = await post(`/api/library/${id}/game`,
                           { game: pick.value === OTHER ? typed.value : pick.value });
      if (r.said) toast(r.said);
      seen = "";
      shownFacts = "";
      load();
    };
    typed.addEventListener("keydown", (e) => { if (e.key === "Enter") saveGame(); });
    const gameRow = el("div", { class: "row tight lib-game" },
      el("label", { for: "lib-game-box" }, "Game"), pick, typed,
      el("button", { class: "btn", type: "button", onclick: saveGame }, "Save game"),
      found.game ? null : el("span", { class: "lib-game-warn" },
        "Not known, so it counts as a stream. Set it, and a Let's Play game goes to Let's Play."));
    const panel = el("div", { class: "panel" },
      el("dl", { class: "facts" }, ...facts),
      gameRow,
      found.gone ? el("p", { class: "note lib-gone" },
        "The video is deleted or moved. Its clips, transcript and everything you taught "
        + "AI-Editor are kept, and its clips can still be watched; finished videos can't be "
        + "made from it. Moved it? Import it from its new place to relink it.") : null,
      el("p", { class: "note lib-file" }, found.file),
      found.league.length ? el("details", { class: "lib-more" },
        el("summary", {}, `League events · ${found.league_summary}`),
        el("ul", { class: "lib-events" }, ...found.league.map(([t, text]) =>
          el("li", {}, el("span", {}, t), text)))) : null,
      buttons.childElementCount ? buttons : null,
      whosTalking(id));
    body.querySelector("#lib-details").replaceChildren(
      el("header", {}, el("h3", {}, found.name), el("p", {}, found.line)), panel);
  }

  async function analyse() {
    const said = await post(`/api/library/${picked}/analyse`);
    if (said.said) toast(said.said);
    seen = "";
    load();
  }

  /* --- Who's talking: your friends on Discord, folded away --------------------------- */

  function whosTalking(id) {
    const box = el("details", { class: "lib-more lib-voices" },
      el("summary", {}, "Who's talking (your friends on Discord)"));
    const inside = el("div", { class: "lib-voice-list" });
    box.append(inside);
    if (voicesOpen) { box.open = true; voices(id, inside); }
    box.addEventListener("toggle", () => {
      voicesOpen = box.open;
      if (box.open) voices(id, inside);
    });
    return box;
  }

  async function voices(id, inside) {
    let found;
    try {
      found = await (await fetch(`/api/library/${id}/voices`)).json();
    } catch (e) {
      return;
    }
    const plain = (text) => String(text).replace(/\*\*/g, "");
    const rows = found.voices.map((v) => {
      const name = el("input", { class: "input", type: "text", placeholder: "Who is it?",
                                 "aria-label": `Voice ${v.label}'s name` });
      name.value = v.named;
      const save = async () => {
        const r = await post(`/api/library/${id}/voices/${v.label}/name`, { name: name.value });
        if (r.said) toast(plain(r.said));
        voices(id, inside);
      };
      name.addEventListener("keydown", (e) => { if (e.key === "Enter") save(); });
      const sound = el("audio", { controls: "", preload: "none",
                                  src: `/api/library/${id}/voices/${v.label}.wav` });
      return el("div", { class: "lib-voice" },
        el("div", { class: "lib-voice-said" }, plain(v.said)),
        sound,
        el("div", { class: "row tight" }, name,
          el("button", { class: "btn primary", type: "button", onclick: save }, "Save name"),
          v.named ? el("button", { class: "btn quiet", type: "button", onclick: async () => {
            const r = await post(`/api/library/${id}/voices/${v.label}/not`);
            if (r.said) toast(plain(r.said));
            voices(id, inside);
          } }, "That's not them") : null));
    });
    inside.replaceChildren(
      el("p", { class: "note" }, found.intro),
      ...(rows.length ? rows : [el("p", { class: "note" },
        "No voices to name in this stream yet. If friends were on Discord, press Analyse: it "
        + "writes down their words and tells their voices apart (a few minutes; only the new "
        + "steps run).")]),
      el("p", { class: "note" }, found.friends.length
        ? `Your friends so far: ${found.friends.join(", ")}` : "No friends named yet."));
  }

  /* --- opened and closed by the frame ------------------------------------------------- */

  NATIVE.library = {
    open(into, headerActions) {
      body = into;
      actions = headerActions;
      seen = "";
      shownFacts = "";
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
