# Phase 4 — The window and the installer

**For:** the engineer, alongside `docs/source/stream-auto-editor-spec.md`
**Target:** AI-Editor launches like any other Windows program — an icon, its own window, no
console, no browser tab, no port to think about.
**Design to build against:** the UI mockups canvas (22 artboards: ten screens in dark and
light, the Jobs rail in every state, and the empty states).

---

## 1. What stays, and what changes

The interface stays HTML and CSS. What changes is the shell around it.

| Today | After Phase 4 |
|---|---|
| `ai-editor app` opens a console window | No console at all |
| The page opens in the default browser at `127.0.0.1:7865` | The page renders in AI-Editor's own window |
| "Leave this window open while you use AI-Editor" | Closing the window closes the program |
| Port clashes need `--port 7866` | A free port is chosen automatically |
| Desktop shortcut points at `ai-editor.exe app` | Start menu entry, desktop icon, uninstaller |

The local server keeps running exactly as it does now; it just stops being something the
creator can see. This is the same arrangement VS Code, Discord, Slack and Obsidian use, so
nothing here is unusual.

**Not in scope:** rewriting the UI in a native toolkit, code signing (see §7), auto-update
beyond a version check, and any change to the analysis or render pipeline.

---

## 2. Step one: the window

Add `ai_editor/desktop.py`. It starts the existing server on a free port with
`open_browser=False`, waits for it to answer, then opens a WebView2 window pointed at it.

**Dependency:** `pywebview>=5.0`. On Windows it uses WebView2, which ships with Windows 11
and with current Windows 10, so nothing extra is distributed. If `WebView2Loader` is
missing, pywebview raises at window creation — catch it and fall back to the old browser
path with a plain-English message, so the app never simply fails to appear.

Sketch, to be fitted to the real code:

```python
"""The desktop window: the same page as `ai-editor app`, in its own window."""
from __future__ import annotations

import socket
import threading
import time
import urllib.request

import webview  # pywebview

from . import __product_name__, __version__
from .app import window as app_window
from .config import load_settings


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(url: str, timeout: float = 90.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + "config", timeout=2):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def main() -> None:
    settings = load_settings()
    port = app_window.PORT
    if app_window.already_running(port) is not False:
        port = _free_port()

    threading.Thread(
        target=app_window.serve,
        args=(settings,),
        kwargs={"port": port, "open_browser": False},
        daemon=True,
    ).start()

    url = app_window.url_for(port)
    if not _wait_until_up(url):
        raise SystemExit("AI-Editor could not start. See the log in your logs folder.")

    webview.create_window(
        f"{__product_name__} {__version__}",
        url,
        width=1512, height=982, min_size=(1100, 760),
        confirm_close=False,
    )
    webview.start()   # returns when the window closes
```

Points that matter:

- **Closing the window ends the program.** `serve` runs on a daemon thread, so when
  `webview.start()` returns the process exits. Before it does, run the same tidy-up the
  console close does today: `JobQueue.recover_interrupted()` already handles jobs that were
  cut short at next start, so nothing is lost either way, but a clean `worker.pause()` on
  close is better than relying on recovery.
- **Already running.** If a window is already open, bring it to the front rather than
  starting a second server. A named mutex (`CreateMutexW`) or a lock file in
  `%LOCALAPPDATA%\AI-Editor` is enough; today's `already_running` check only tells you a
  port is busy.
- **Startup takes a few seconds** while Gradio builds the page. Use pywebview's splash or
  simply create the window first with a small local loading page, then navigate — a window
  that appears instantly feels far better than a delayed one.
- **`os.startfile` and Explorer still work** from inside the window: they are separate
  processes, unaffected by the webview.
- **Downloads and file pickers:** `library.browse_for_video` already uses a native dialog,
  so nothing changes there. Anything that relied on the browser's own download behaviour
  needs checking.

---

## 3. Step two: no console

Two independent causes, both must be fixed:

1. **The launcher.** Console entry points in `[project.scripts]` build `ai-editor.exe`,
   which allocates a console. Add GUI entry points, which build console-less exes:

   ```toml
   [project.gui-scripts]
   "AI-Editor" = "ai_editor.desktop:main"
   "AI-Editor Companion" = "ai_editor.companion.app:main"
   ```

   These land in `.venv\Scripts\AI-Editor.exe` and are what the shortcut and installer
   point at. Keep `[project.scripts] ai-editor` exactly as it is — the CLI is still the way
   to run things by hand, and every `ai-editor …` command in the README must keep working.

2. **`print` and tracebacks.** With no console attached, `sys.stdout` and `sys.stderr` can
   be `None` on Windows, and a bare `print` then raises. Audit the startup path (the banner
   in `serve` prints several lines) and route everything through `logging_setup` instead.
   Install a `sys.excepthook` that writes the traceback to the log and shows a short
   message box, so a crash is never silent.

Update `make_shortcut` to target `AI-Editor.exe` with no arguments, and update manual
chapter 5 and the README's "Running from source" accordingly.

---

## 4. Step three: packaging

Two routes. Take the first now; the second only matters if the app ever goes to another PC.

### Route A — portable folder plus installer (recommended)

Ship the project with its virtual environment inside it, and let the installer place it and
make the shortcuts. No freezing, no hidden-import archaeology, and upgrades are a file copy.

```
AI-Editor\
  app\              the ai_editor package and config\
  runtime\          the virtual environment (python.exe, Scripts\AI-Editor.exe, site-packages)
  tools\            ffmpeg.exe, TwitchDownloaderCLI.exe
  AI-Editor.lnk     → runtime\Scripts\AI-Editor.exe
```

Expect 8–12 GB with CUDA PyTorch. That is unavoidable in any route; it is the CUDA
libraries, not the packaging.

### Route B — PyInstaller one-folder

Only if a genuinely self-contained build is wanted. Be aware before starting:

- **One-folder, never one-file.** One-file unpacks gigabytes to `%TEMP%` on every launch.
- **Data-heavy packages need collecting**, or the app builds and then fails at runtime:
  `--collect-all gradio --collect-all gradio_client --collect-all faster_whisper
  --collect-all demucs --collect-all sherpa_onnx --collect-all scenedetect`, plus
  `rapidocr` and `torchlibrosa`. Gradio ships a frontend build and templates that
  PyInstaller does not find on its own.
- **Torch and CUDA DLLs** are the bulk of the output and the slowest part of the build.
- **Models are never bundled.** Whisper, PANNs, WeSpeaker and the Ollama model are
  downloaded on first run, as they are today.

Either way, keep FFmpeg and TwitchDownloaderCLI as files beside the app, resolved through
settings, not bundled into the binary. Use an **LGPL FFmpeg build**: the app uses NVENC, so
the GPL-only encoders are not needed, and this keeps redistribution clean.

### The installer (Inno Setup, free)

```
[Setup]
AppName=AI-Editor
AppVersion=0.37.0
DefaultDirName={localappdata}\AI-Editor
PrivilegesRequired=lowest
DisableDirPage=no
UninstallDisplayIcon={app}\runtime\Scripts\AI-Editor.exe
OutputBaseFilename=AI-Editor-Setup-0.37.0

[Icons]
Name: "{autoprograms}\AI-Editor"; Filename: "{app}\runtime\Scripts\AI-Editor.exe"
Name: "{autodesktop}\AI-Editor"; Filename: "{app}\runtime\Scripts\AI-Editor.exe"; Tasks: desktopicon
Name: "{userstartup}\AI-Editor Companion"; Filename: "{app}\runtime\Scripts\AI-Editor Companion.exe"; Tasks: companionstartup
```

- **Per-user install** (`{localappdata}`, `PrivilegesRequired=lowest`) avoids the admin
  prompt and the Program Files write problems.
- **The Companion gets its own shortcut and its own optional startup entry**, so it can run
  without the main window open — it already runs as a separate process.
- **Uninstall removes the program only.** Recordings, the cache, outputs, the clip library
  and settings all live in the creator's own folders on F: and must survive. Say so on the
  uninstall page.

---

## 5. Where the data lives

One change is needed. `settings.local.yaml` and the database are resolved relative to
`PROJECT_ROOT` today, which is fine when running from source and wrong once installed —
the app folder gets replaced on every upgrade.

Move user data to `%LOCALAPPDATA%\AI-Editor\`: `settings.local.yaml`, the SQLite library,
logs, issue files and backups. Keep `config/settings.yaml` in the app folder as the
shipped defaults. The five media folders (raw, cache, output, assets, models) stay exactly
where the creator set them and are not touched.

Migration: on first run after upgrading, if the old project-relative files exist and the
new location is empty, copy them across and log that it happened.

---

## 6. Updating

A version check is enough; no auto-update machinery.

On start (quietly, in the background), fetch the latest release tag from GitHub. If it is
newer, show a line in the app: what changed, and a button that opens the release page.
Installing is running the new installer, which replaces the app folder and leaves user data
alone. If the check fails, say nothing — it must never block starting.

---

## 7. SmartScreen

The first launch of an unsigned installer shows "Windows protected your PC", and the way
past it is More info → Run anyway. That is expected for personal software and worth a line
in manual chapter 5.

It only disappears with an EV code-signing certificate (a few hundred euros a year), which
is not worth it for one PC. If AI-Editor is ever shared, revisit it then.

---

## 8. Machines without an NVIDIA GPU

The installed app will be run on a laptop with no CUDA and no NVENC. It must **start, show
its window, and say plainly what is missing** — never crash on launch, and never fail with
a CUDA traceback.

- Import, the Library, Clips, Review, Rules, Settings and Storage all work with no GPU.
- Analysing and rendering cannot. Disable those buttons and say why, in the same words
  `doctor` uses, rather than letting the job start and fail deep in the pipeline.
- Model loading must not happen at startup on a machine that cannot use the models.
- `doctor` must run and report the missing pieces without raising.

This is how the laptop gets used as an install test, and it is the right behaviour anyway.

---

## 9. Done when

Two tests, and they catch different things:

**A second Windows user account on the main PC** — same GPU, none of the development
folders. This catches "it only worked because the files were in F:\AI-Editor", and it is
the only one of the two that can analyse and render a real recording.

**The laptop** — proves the installer works on a machine that never had Python, the
virtual environment or the project. Expect the no-GPU behaviour in §8 there.

On the main PC's second account:

- [ ] Double-clicking the icon opens AI-Editor's own window with its icon and title.
- [ ] No console window appears at any point.
- [ ] The taskbar shows one AI-Editor entry, with the right icon.
- [ ] Launching it twice brings the existing window forward instead of starting a second copy.
- [ ] Analysing a two-hour recording works end to end, with the Jobs rail updating.
- [ ] Closing the window mid-job pauses it; reopening offers Resume and repeats no finished step.
- [ ] The Companion starts from its own shortcut, with the main window closed, and its hotkeys work in-game.
- [ ] Settings, the clip library, rules and style profiles survive an upgrade install.
- [ ] Uninstalling removes the program and leaves every recording, output and the library intact.
- [ ] `ai-editor doctor` and every other CLI command still work from the source checkout.
- [ ] The manual (chapters 5 and 6) and the README match what the installer actually does.

On the laptop:

- [ ] The installer runs with no admin prompt and no Python on the machine.
- [ ] The window opens and every screen renders.
- [ ] Analysing and rendering are disabled with a plain-English reason, and nothing crashes.
- [ ] `doctor` reports the missing GPU and NVENC without raising.
- [ ] Uninstalling leaves no AI-Editor folders behind except the creator's own media folders.

---

## 10. Order of work

1. `desktop.py` and the window, run from source. Nothing else changes.
2. GUI entry points, console removal, the stdout/excepthook audit.
3. User data moved to `%LOCALAPPDATA%`, with migration.
4. The portable folder layout and the Inno Setup script.
5. The clean-account test and the checklist above.
6. The version check, last.

Steps 1 and 2 already deliver most of what makes it feel like a real program; the installer
is the part that makes it one.
