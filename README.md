# AI-Editor

A local, free assistant editor that turns stream recordings and Let's Play recordings
into YouTube long-form videos, highlight compilations, and vertical Shorts.

Built to the two handover documents in [`docs/source/`](docs/source/), which are
kept frozen as the agreed reference:

| Document | Role |
|---|---|
| `stream-auto-editor-spec.md` | What to build, in what order. Section numbers are cited throughout the code. |
| `streamcut-user-manual.md` | The original creator-facing draft, written before the software existed. |

The **living** manual — the one kept accurate as each phase lands — is
[`docs/user-manual.md`](docs/user-manual.md). Edit that one, never the drafts in
`docs/source/`.

Everything runs offline on one PC. No paid services, no subscriptions, and
**no interaction with any game process** — see specification section 6, which is
a hard rule, not a preference.

---

## Current state

| Phase | Scope | Status |
|---|---|---|
| **0** | Foundation: settings, database schema, job queue, FFmpeg layer, setup check | **Complete** |
| **1A** | Ingest: local OBS recordings, proxies, audio extraction | **Complete** |
| 1B | Audio analysis: transcription, silence, audio events | Not started |
| 1C | Twitch VOD download, chat, Demucs voice separation | Not started |
| 1D | Stream Companion: OBS WebSocket, marker hotkeys | Not started |
| 1E | Scoring and clip segmentation | Not started |
| 1F | Recipes: highlights, Let's Play split optimiser | Not started |
| 1G | Rendering (NVENC), captions, OTIO/FCPXML export | Not started |
| 1H | Gradio interface, storage management | Not started |
| 2 | Shorts, League events, story protection, style profiles, rules, effects | Not started |
| 3 | Feedback learning, OCR events, batch processing | Not started |

---

## Running from source

Requires Python 3.11+, FFmpeg with NVENC, and an NVIDIA GPU.

```powershell
# From the project root
.\.venv\Scripts\Activate.ps1      # or: py -3.11 -m venv .venv  (first time)
pip install -e ".[dev]"

ai-editor doctor                  # Check the setup
ai-editor probe "path\to\recording.mp4" --hash
ai-editor import "path\to\recording.mp4"    # Proxy + audio into the library
ai-editor library                 # List imported recordings
pytest
```

`ai-editor doctor` verifies FFmpeg, NVENC, the GPU, all five folders, and the
clip library. It changes nothing and is safe to run at any time. It is the same
check behind the setup wizard's Test buttons (manual chapter 6).

---

## Architecture

```
ai_editor/
  config.py          Settings loading and validation (config/settings.yaml)
  db.py              SQLite clip library: schema and migrations
  jobs.py            Resumable job queue with content-hash step caching
  ffmpeg.py          FFmpeg/ffprobe wrapper, media probing, content hashing
  ingest.py          Import: registration, proxy (GPU with fallbacks), audio
  games.py           Known games and filename-based game suggestion
  errors.py          Plain-language errors, each mapped to a manual entry
  logging_setup.py   File logs get tracebacks; the creator never does
  cli.py             Command line interface
```

### Two ideas hold the design together

**Analyse once, output many** (spec section 5). A recording is analysed a single
time into the clip library; the three recipes only read from it. Making a new
Short from last week's stream takes seconds, not another analysis pass.

**Every long step is resumable** (spec section 3). A job is a list of named
steps, each with a cache key derived from the source file's content hash plus
that step's inputs. A finished step is skipped — even if a *different* job
finished it. This is what makes manual chapter 11.3's promise true: if the PC
restarts mid-analysis, Resume continues without repeating work.

### The content hash

Hashing a 13 GB recording end to end costs minutes per import. Instead
`ffmpeg.content_hash` combines the file size with 8 MB sampled from the start,
middle, and end — 0.3 seconds on a 12.87 GB file. Re-encoding or trimming
changes the hash, so the analysis is correctly redone.

---

## Adding things

**A new game profile** — game profiles are plugins (spec section 8). Detection
templates such as OCR regions live in editable data files, never hard-coded,
because game UIs change with patches.

**A new error** — subclass `AIEditorError` in `errors.py`, add it to
`ALL_ERRORS`, and add a row to manual chapter 25. `tests/test_errors.py` fails
the build if you forget the manual.

**A schema change** — add a new entry to `MIGRATIONS` in `db.py`. Never edit an
existing migration.

---

## Documentation is a deliverable

Specification section 14.4: *a phase is not done until the manual, in-app help,
and troubleshooting entries are updated for every feature in that phase.* The
creator should be able to complete every workflow using only
[`docs/user-manual.md`](docs/user-manual.md).
