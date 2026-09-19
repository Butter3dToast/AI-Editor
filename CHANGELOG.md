# Changelog

Written so the creator can understand what changed, not only the engineer
(specification section 14.3).

## 0.3.0 — Phase 1B: Listening to recordings — 19 September 2026

AI-Editor can now hear what happens in a recording.

**New**

- **Analyse a recording** with `ai-editor analyze 1` (the number from
  `ai-editor library`). AI-Editor:
  - writes down **every word** said, with the moment each word was spoken,
  - listens for **laughter, shouting, screaming, gunfire and explosions**,
  - measures how **loud** each second is, to find silence and sudden spikes,
  - lists **moments to check** with times you can jump to.
- **Subtitles you can check.** A subtitle file is saved next to the preview
  copy, so opening the preview in VLC shows the transcript automatically.
- **See the results again** any time with `ai-editor moments 1`.
- **Misheard phrases are set aside.** Over music, speech-recognition AI can
  "hear" words nobody said (often "see you next time"). Phrases that are both
  unsure and unnaturally slow are set aside. Words are never removed because
  of *what* they say, so your real sign-offs stay.
- The first analysis downloads two AI models (about 4.6 GB altogether) into
  your Models folder, once.
- **Fixed before release:** the first version transcribed in fast "batched"
  mode, which on your EP 1 silently skipped speech under game music: whole
  minutes with 0–4 words where there were over 70. Transcription now works
  through the recording one phrase at a time. EP 1 went from 4,838 to 6,389
  words, and still transcribes in under 2 minutes.
- **Voice detector "auto":** on a separate mic track, AI-Editor skips silent
  parts before transcribing (reliable, and stops invented words over silence);
  on a mixed track it listens to everything, because there the detector missed
  speech under music.
- **More accurate transcription model** (Whisper `large-v3` instead of
  `large-v3-turbo`). Compared on your own mic recording it heard "OBS" instead
  of "a BS" and "let's just see if this works" instead of "it's just a shit
  see this works"; on EP 1 it had 17% fewer unclear words. It takes about
  3 minutes for 2 hours instead of 2. One extra download (about 3 GB).
- **Short reactions over game music are kept** ("Look out!", "Oh, shit!")
  instead of being mistaken for noise.
- **Easier-to-read captions.** Captions end at the end of a sentence (very
  short ones join the next), long sentences split at a comma, and every caption
  stays on screen for at least a second. Before, lines were cut mid-sentence and
  fragments like "there?" flashed up for a fifth of a second.
- **"Unusually loud" now means louder than your normal talking**, not louder
  than the silences between sentences, which had hidden raised voices.
- Four new error messages (E015, E016, E030, E031), explained in manual
  chapter 25; four new settings in chapter 24.

**Changed**

- `ai-editor library` shows whether each recording has been analysed.
- Warnings from the AI libraries go to the log file instead of your screen.

## 0.2.0 — Phase 1A: Importing recordings — 19 September 2026

Your recordings can now be brought into AI-Editor.

**New**

- **Import a recording** with `ai-editor import "<file>"`. AI-Editor:
  - works out the game from the file name (or use `--game`),
  - makes a small **preview copy** (540p, 30 fps) for fast previews and
    analysis, using your graphics card,
  - saves each **audio track** separately so the next phase can transcribe it,
  - checks there is enough disk space *before* starting.
- **Your recording is never copied or changed.** It is read where it is.
- **Stop any time.** Press `Ctrl + C`; running the same command again carries
  on where it stopped.
- **Re-importing is instant.** Finished work is reused.
- **Moved a file?** Importing it from the new place is recognised as the same
  recording, not a new one.
- **See your library** with `ai-editor library`.
- Two new error messages, E013 and E014, explained in manual chapter 25.

**Changed**

- The screen now shows only warnings and problems while AI-Editor works. The
  full step-by-step detail still goes to the log file.

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
