# Changelog

Written so the creator can understand what changed, not only the engineer
(specification section 14.3).

## 0.1.0 — Phase 0: Foundation — 19 September 2026

The skeleton everything else is built on. Nothing to click yet; this phase is
about making sure the ground is solid before the editing features land.

**New**

- **Setup check.** Run `ai-editor doctor` to confirm your PC is ready: it checks
  FFmpeg, your graphics card's fast encoder (NVENC), the card itself, all five
  folders and how much space each has, and the clip library. It changes nothing.
- **Recording inspector.** Run `ai-editor probe "<file>"` to see a recording's
  length, resolution, frame rate, and audio tracks. It warns you when a
  recording has only one mixed audio track, because separate tracks make
  captions and moment detection noticeably better (manual chapter 7).
- **Clip library.** The database that will hold every recording, clip,
  transcript, rule, and style profile.
- **Job queue.** Long jobs can be paused and resumed. If your PC restarts
  mid-way, finished steps are not repeated.
- **Settings file.** `config/settings.yaml` holds your folders and every
  default from the manual. Bad values are caught when the app starts, with a
  message that says what is wrong, rather than failing an hour into a render.
- **Plain-language errors.** Every error has a code (E001, E002, ...) matching
  an entry in manual chapter 25. Technical details go to the log file, not to
  you.

**Fixed during Phase 0 review**

- AI-Editor now finds FFmpeg even if you installed it while a terminal window
  was already open. Windows only tells newly opened windows about newly
  installed programs, so the setup check used to report FFmpeg as missing when
  it was sitting right there.
- The setup check no longer reports your graphics card encoder as broken when
  the real problem is a missing FFmpeg. It now says the check could not be run,
  and points at the actual cause.
- Messages about a missing `ffprobe` said "FFmpeg" instead, which sent you
  looking for the wrong thing.

**Notes**

- Your folders are set to `F:\AI-Editor\` for raw footage, cache, output and
  assets, and `E:\AI-Editor\models` for AI model files.
- The local AI model (Ollama) is installed but not used yet. It arrives in
  Phase 2 for moment rating, titles, and interpreting your written rules.
