/* The frame (Phase 4B): the sidebar, the header, the Jobs panel, the
   Companion and the morning note, kept up to date from AI-Editor's small JSON
   answers (frame_api.py). A rebuilt screen (4C on: library.js...) is drawn
   here; until a screen is rebuilt, the body shows today's screen for it, from
   /classic. Text from AI-Editor is always put in as text, never as markup,
   except the morning note, which the server makes safe first. */
"use strict";

const SCREENS = [
  ["Make", [["library", "Library"], ["import", "Import"], ["clips", "Clips"],
            ["create", "Create video"], ["review", "Review"]]],
  ["Teach it", [["style", "Style Profiles"], ["rules", "Rules"]]],
  ["App", [["storage", "Storage"], ["settings", "Settings"], ["issues", "Issues"]]],
];
const NAMES = Object.fromEntries(SCREENS.flatMap(([, items]) => items));
const GUARD = { "X-AI-Editor": "1" };   // every change carries it (frame_api.py)

const $ = (id) => document.getElementById(id);
const app = $("app");
let current = "library";
let about = { lines: {}, tallies: {} };
let railShut = false;          // closed by hand: stays closed until a new job starts
const seenJobs = new Set();

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function toast(text) {
  const box = $("toast");
  box.textContent = text;
  box.classList.add("on");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => box.classList.remove("on"), 4500);
}

async function post(path, body) {
  const headers = body === undefined ? GUARD : { ...GUARD, "Content-Type": "application/json" };
  const reply = await fetch(path, { method: "POST", headers,
                                    body: body === undefined ? undefined : JSON.stringify(body) });
  return reply.ok ? reply.json() : {};
}

/* The rebuilt screens add themselves here: { open(body, actions), close() }. */
const NATIVE = {};
/* A rebuilt screen may say its own line under the title (Clips: the recording's). */
const ownLines = {};
function line(text) {
  ownLines[current] = text;
  $("subtitle").textContent = text;
}
const lineOf = (id) => (ownLines[id] !== undefined ? ownLines[id] : about.lines[id] || "");
window.aie = { el, toast, post, show: (id) => show(id), line, NATIVE };

/* --- light or dark: auto (as Windows is set, live), or the one you chose ---------- */

const lightScheme = window.matchMedia("(prefers-color-scheme: light)");
let mode = app.dataset.theme || "auto";     // kept in your settings (frame_api.py)

function looks() {
  return mode === "auto" ? (lightScheme.matches ? "light" : "dark") : mode;
}

function theme() {
  const now = looks();
  app.classList.toggle("light", now === "light");
  app.classList.toggle("dark", now === "dark");
  document.documentElement.style.background = now === "light" ? "#f7f7f8" : "#111113";
  document.querySelectorAll("#theme button").forEach((b) =>
    b.classList.toggle("on", b.dataset.mode === mode));
  const frame = $("screen");                // today's screen inside follows
  try {
    if (frame.contentWindow && frame.contentWindow.aieTheme) frame.contentWindow.aieTheme(now);
  } catch (e) { /* still loading: it asks for the theme itself */ }
}
lightScheme.addEventListener("change", theme);
document.querySelectorAll("#theme button").forEach((b) => b.addEventListener("click", async () => {
  mode = b.dataset.mode;
  theme();
  await post(`/api/theme/${mode}`);
}));
window.aieLooks = looks;                    // for today's screen, as it loads
theme();

/* --- the sidebar and the screens ------------------------------------------------- */

function buildNav() {
  const nav = $("nav");
  for (const [group, items] of SCREENS) {
    nav.append(el("div", { class: "navlabel" }, group));
    nav.append(el("nav", { class: "nav" }, ...items.map(([id, name]) =>
      el("a", { "data-screen": id, onclick: () => show(id) }, name,
         el("em", { class: "tally", id: `tally-${id}` })))));
  }
}

function show(id) {
  if (current !== id && NATIVE[current] && NATIVE[current].close) NATIVE[current].close();
  current = id;
  document.querySelectorAll(".nav a").forEach((a) =>
    a.classList.toggle("on", a.dataset.screen === id));
  $("title").textContent = NAMES[id];
  $("subtitle").textContent = lineOf(id);
  $("actions").replaceChildren();
  const frame = $("screen");
  const native = NATIVE[id];
  $("native").hidden = !native;
  $("body").hidden = !!native;
  if (native) {
    native.open($("native"), $("actions"));
    // Today's screens load meanwhile, so the others open quickly.
    if (!frame.src) frame.src = `/classic/?embed=1&__theme=${looks()}&view=Clips`;
    return;
  }
  if (!frame.src) {
    frame.src = `/classic/?embed=1&__theme=${looks()}&view=${encodeURIComponent(NAMES[id])}`;
    return;
  }
  // Today's screens may still be drawing: try again for a few seconds.
  let tries = 0;
  const pick = () => {
    const there = frame.contentWindow && frame.contentWindow.aieShow;
    if ((there && frame.contentWindow.aieShow(NAMES[id])) || ++tries > 40 || current !== id) return;
    setTimeout(pick, 150);
  };
  pick();
}

/* --- the sidebar's numbers, the header line, the Companion, the morning note ------ */

async function refresh() {
  try {
    about = await (await fetch("/api/frame")).json();
  } catch (e) {
    return;
  }
  $("version").textContent = about.version;
  for (const [id, n] of Object.entries(about.tallies || {})) {
    const tally = $(`tally-${id}`);
    if (tally) tally.textContent = n ? String(n) : "";
  }
  $("subtitle").textContent = lineOf(current);
  const c = about.companion || {};
  $("comp-title").textContent = c.title || "Companion";
  $("comp-detail").textContent = c.detail || "";
  const led = document.querySelector("#companion .led");
  led.className = "led" + (!c.running ? " off" : c.warn ? " warn" : "");
  const note = about.note;
  $("morning").hidden = !note;
  if (note) {
    $("morning-text").innerHTML = "🌙 " + note.html;   // made safe by the server
    $("morning-ok").onclick = async () => {
      await post(`/api/note/${note.id}/seen`);
      $("morning").hidden = true;
    };
  }
}

$("companion").addEventListener("click", async () => {
  const running = about.companion && about.companion.running;
  if (running && !window.confirm("Stop the Stream Companion? Markers and scene changes "
                                 + "aren't logged while it's off.")) return;
  const said = await post(`/api/companion/${running ? "stop" : "start"}`);
  if (said.said) toast(said.said);
  setTimeout(refresh, 1500);
});

/* --- Jobs ------------------------------------------------------------------------- */

function card(job) {
  const steps = job.steps.map(([label, f]) => el("div", { class: "step" },
    el("span", {}, label),
    el("div", { class: "bar" }, el("div", { class: f >= 1 ? "done" : "", style: `width:${f * 100}%` })),
    el("span", {}, `${Math.round(f * 100)}%`)));
  const buttons = [];
  if (job.resume) {
    buttons.push(el("button", { class: "btn", type: "button", onclick: async () => {
      await post(`/api/jobs/resume?id=${job.id}`);
      toast("Resuming: finished steps won't be repeated.");
      jobs();
    } }, "Resume"));
  }
  if (job.action) {
    buttons.push(el("button", { class: "btn quiet", type: "button",
                                onclick: () => show(job.action.screen) }, job.action.label));
  }
  return el("div", { class: "job" },
    el("div", { class: "jh" }, el("span", { class: "jt" }, job.title),
       el("span", { class: `state ${job.state}` }, job.badge)),
    job.meta ? el("div", { class: "jm" }, job.meta) : null,
    ...steps,
    job.lines.length ? el("ul", {}, ...job.lines.map((line) => el("li", {}, line))) : null,
    job.error ? el("div", { class: "err" }, job.error) : null,
    buttons.length ? el("div", { class: "row tight" }, ...buttons) : null);
}

function rail(list) {
  const box = $("rail");
  const active = list.filter((j) => j.state === "run" || j.badge === "Waiting");
  for (const job of active) {
    if (!seenJobs.has(job.id)) { seenJobs.add(job.id); railShut = false; }   // opens by itself
  }
  box.replaceChildren();
  if (!list.length || railShut) {
    box.className = "rail slim";
    box.append(
      el("button", { class: "open", type: "button", "aria-label": "Open the jobs panel",
                     onclick: () => { railShut = false; rail(list); } }, "‹"),
      el("h2", {}, "Jobs"),
      el("i", { class: active.length ? "busy" : "resting", "aria-hidden": "true" }));
    return;
  }
  box.className = "rail";
  box.append(el("div", { class: "head" }, el("h2", {}, "Jobs"),
    el("button", { class: "shut", type: "button", "aria-label": "Close the jobs panel",
                   onclick: () => { railShut = true; rail(list); } }, "›")));
  list.forEach((job) => box.append(card(job)));
  const tools = [];
  if (active.length) {
    tools.push(el("button", { class: "btn quiet", type: "button", onclick: async () => {
      await post("/api/jobs/pause");
      toast("Pausing: the running job stops at its next step. Resume carries on.");
      jobs();
    } }, "Pause all"));
  }
  if (list.some((j) => j.badge === "Finished")) {
    tools.push(el("button", { class: "btn quiet", type: "button", onclick: async () => {
      await post("/api/jobs/clear");
      jobs();
    } }, "Clear finished"));
  }
  if (tools.length) box.append(el("div", { class: "row tight" }, ...tools));
}

async function jobs() {
  try {
    rail((await (await fetch("/api/jobs")).json()).jobs);
  } catch (e) {
    /* AI-Editor is closing: nothing to show */
  }
}

/* --- start: once the rebuilt screens' own scripts have added themselves ------------- */

document.addEventListener("DOMContentLoaded", () => {
  buildNav();
  show(current);
  refresh();
  jobs();
  setInterval(jobs, 1000);
  setInterval(refresh, 5000);
});
