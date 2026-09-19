# AI-Editor User Manual

**Draft version 1.0** — released with the project specification (v2.0), 18 September 2026.

> **Note for the engineer**
>
> This manual describes how the software is *designed* to work; it was written before the software existed, so treat it as the target experience and as the second half of the specification.
>
> As you build each phase:
> 1. Replace every placeholder screen name, button label, menu path, and default value with the real ones.
> 2. Add screenshots wherever **[Screenshot]** appears, plus any others that help.
> 3. Complete the settings reference (chapter 24) and add a troubleshooting entry (chapter 25) for every error message the app can produce.
> 4. Confirm the third-party menu paths marked with **[Engineer: ...]**, such as OBS, DaVinci Resolve, and Kdenlive, against current versions.
> 5. Review the updated manual with the creator at the end of each phase. If a step is hard to describe in plain words, that usually means the interface needs simplifying, not the wording.
>
> Standard to aim for: the creator should be able to do everything in this manual without asking anyone for help.

---

## Contents

1. Welcome
2. How AI-Editor works (the big picture)
3. Key words explained
4. What you need
5. Installing AI-Editor
6. First-time setup wizard
7. Setting up OBS (step by step)
8. Stream Companion
9. Your everyday workflow
10. Importing footage
11. Analysis
12. The Clip Browser
13. Style Profiles (teaching AI-Editor a look)
14. Rules (your editing tips)
15. Creating a Let's Play (parts)
16. Creating a Highlight video
17. Creating Shorts and TikToks
18. The Review screen
19. Rendering and exporting
20. Publish Prep
21. Game guides
22. How AI-Editor learns from you
23. Storage and cleanup
24. Settings reference
25. Troubleshooting
26. Frequently asked questions
27. Staying safe (accounts, copyright, music)

---

## 1. Welcome

AI-Editor is your personal assistant editor. It watches your streams and recordings, finds the best moments, cuts out the boring parts, adds effects in the style you like, and prepares videos for YouTube.

It makes three kinds of videos:

- **Let's Play parts** — full sessions split into roughly 30-minute episodes, with loading screens, menus, and dead air removed.
- **Highlight videos** — your best moments from one or more streams, about 10 minutes long.
- **Shorts** — vertical clips under a minute to attract new viewers.

Everything runs on your own PC. It is free, works offline once set up, and never uploads anything without you.

AI-Editor does most of the work, but **you stay in charge**. It always shows you its plan before making a final video, and you can change anything.

---

## 2. How AI-Editor works (the big picture)

Every video goes through the same journey:

1. **Record or stream** in OBS. While you play, the **Stream Companion** notes important moments (and League of Legends match events).
2. **Import** your footage into AI-Editor: a Twitch VOD link or a local OBS recording.
3. **Analysis** runs once per recording. AI-Editor transcribes what you say, listens for laughter, shouting, and gunfire, reads chat activity, and scores every moment.
4. Everything it finds goes into your **Clip Library**.
5. You **Create a video** by choosing a recipe (Let's Play, Highlights, or Short), a **Style Profile** (the look), and your **Rules** (your tips).
6. AI-Editor builds an **Edit Plan** and shows it on the **Review screen**.
7. You adjust anything you want, then **Render** the final video or **Export** it to DaVinci Resolve or Kdenlive for polishing.
8. **Publish Prep** gives you title ideas, a description, chapters, and thumbnail frames.
9. Every change you make during review teaches AI-Editor your taste for next time.

Because analysis only happens once, you can make a Let's Play, a highlight video, *and* several Shorts from the same recording without waiting again.

---

## 3. Key words explained

| Word | What it means |
|---|---|
| **VOD** | "Video on demand." The saved copy of your Twitch stream that you download. |
| **Local recording** | A video OBS saves directly to your PC. Better quality than a VOD. |
| **Audio track** | A separate layer of sound in a recording, such as only your mic or only game sound. |
| **Stream Companion** | A small helper app that runs while you stream or record and logs moments. |
| **Marker** | A note you create by pressing a hotkey when something great happens. |
| **Analysis** | AI-Editor studying a recording to find moments. Happens once per recording. |
| **Clip** | A short moment AI-Editor found, like a funny death or a clutch fight. |
| **Clip Library** | The collection of all clips from all your recordings. |
| **Score** | How strong AI-Editor thinks a moment is, from 0 (boring) to 1 (amazing). |
| **Keep score** | In Let's Plays, how important a section is to keep. |
| **Style Profile** | A saved editing look: how fast the cuts are, how often it zooms, caption style, and so on. |
| **Reference video** | A YouTube video whose editing you like, used to build a Style Profile. |
| **Rule** | A tip you write in plain English, like "never cut boss fights." |
| **Recipe** | The type of video: Let's Play, Highlights, or Short. |
| **Edit Plan** | AI-Editor's full plan for a video, before it's rendered. |
| **Part** | One episode of a Let's Play. |
| **Protected** | A section AI-Editor won't cut, like a cutscene. |
| **Pinned** | A section you've told AI-Editor to always keep. |
| **Trim level** | How aggressively AI-Editor removes quiet or slow sections (Light, Standard, Tight). |
| **Render** | Turning the Edit Plan into a finished video file. |
| **Export** | Saving the Edit Plan as a timeline you can open in DaVinci Resolve or Kdenlive. |
| **Proxy** | A small, low-quality copy of your video used for faster previews. |
| **Cache** | Temporary working files. Safe to clean up after a project is finished. |
| **NVENC** | Your NVIDIA graphics card's built-in video encoder. Makes rendering fast. |
| **VRAM** | Your graphics card's memory. Your RTX 4070 Ti has 12 GB. |
| **Hook** | The first few seconds of a video, designed to grab attention. |

---

## 4. What you need

### Hardware (your PC)

- NVIDIA RTX 4070 Ti (12 GB VRAM) — used for AI and fast rendering.
- Intel Core i5 14th gen, 64 GB RAM.
- One NVMe drive with plenty of free space. Plan for **roughly 50–100 GB free** per 2-hour recording while you're working on it (raw file, working files, and finished videos). You can free most of this afterward (see chapter 23).

### Free software

| Software | Why you need it |
|---|---|
| **OBS Studio** (version 28 or newer) | Streaming and recording. |
| **AI-Editor** | The editor itself. The installer sets up everything else it needs (FFmpeg, AI runtime, AI models). |
| **Up-to-date NVIDIA drivers** | Required for AI and NVENC. |
| **DaVinci Resolve (free)** or **Kdenlive** *(optional)* | Only if you want to polish videos further after AI-Editor. |

### Accounts

- Your **Twitch** account (only to find your VOD links).
- Your **YouTube** account for uploading.
- **No** Riot developer account, no API keys, and no paid subscriptions are needed.

---

## 5. Installing AI-Editor

> **[Engineer: replace with the real installer steps.]**

1. Download the AI-Editor installer.
2. Double-click it and follow the prompts. Choose an install location on your NVMe drive.
3. The installer will download the AI models. This is a large download (several gigabytes) and only happens once. Keep your PC on and connected.
4. When installation finishes, open **AI-Editor** from the Start menu.
5. The **First-time setup wizard** opens automatically (chapter 6).

### Updating AI-Editor

1. Open **Help → Check for updates**.
2. If an update is available, click **Update**. Your projects, profiles, and rules are kept.
3. Read **Help → What's new** to see what changed.

### Backing up your settings

Your Style Profiles, Rules, learned preferences, and Clip Library live in AI-Editor's database. Back them up regularly:

1. Go to **Settings → Backup**.
2. Click **Create backup** and choose a location (for example a USB drive or cloud folder).
3. To restore, click **Restore backup** and pick the backup file.

Backups do **not** include your video files.

---

## 6. First-time setup wizard

The wizard walks you through everything once. Each step has a **Test** button so you know it worked. You can rerun it anytime from **Settings → Run setup wizard**.

### Step 1: Choose your folders

AI-Editor asks for five folders. Create them on your NVMe drive first, for example inside `D:\AI-Editor\`.

| Folder | What goes in it | Example |
|---|---|---|
| **Raw footage** | Twitch VOD downloads and OBS recordings | `D:\AI-Editor\raw` |
| **Working cache** | Temporary files during analysis | `D:\AI-Editor\cache` |
| **Outputs** | Finished videos, exported timelines, thumbnails | `D:\AI-Editor\output` |
| **Assets** | Your music, sound effects, fonts, overlay images | `D:\AI-Editor\assets` |
| **Models** | AI model files | `D:\AI-Editor\models` |

**Tip:** Set OBS to save recordings straight into your Raw footage folder so you never have to move files.

### Step 2: Check your graphics card

Click **Test GPU**. You should see your RTX 4070 Ti listed with 12 GB of memory and "NVENC available." If not, update your NVIDIA drivers and try again.

### Step 3: Record your voice sample

This lets AI-Editor recognize *your* voice, especially on Twitch VODs where your voice is mixed with game sound and teammates.

1. Choose your microphone from the list.
2. Click **Record** and read the text on screen out loud for about 30 seconds. Speak normally, the way you do on stream.
3. Click **Test** to confirm it recognizes you.

Re-record if you change microphones.

### Step 4: Connect to OBS

1. Complete **chapter 7.4** (enable the OBS WebSocket) first.
2. Enter the **port** (usually `4455`) and **password** from OBS.
3. Click **Test connection**. You should see "Connected to OBS."

### Step 5: Set your hotkeys

| Hotkey | Default | What it does |
|---|---|---|
| **Mark moment** | `Ctrl + Alt + M` | Logs a great moment. |
| **Mark Short-worthy** | `Ctrl + Alt + S` | Logs a moment that would make a great Short. |

Click a box and press your preferred key combination to change it. Choose keys that **don't clash** with your games or OBS. Tip: if you have a Stream Deck or spare mouse buttons, assign them there.

### Step 6: Draw your layouts

A layout tells AI-Editor where your facecam and gameplay are on screen. You make one per game (or per OBS scene).

1. Click **Add layout** and give it a name, like "Tarkov layout."
2. Pick a frame from a recording, or load a screenshot of your OBS scene.
3. Drag a box around your **facecam**.
4. Drag a box around the **main gameplay area** (usually the whole screen).
5. Optionally drag a box around **important game UI** (kill feed, subtitles) so captions avoid covering it.
6. Assign the layout to a game.
7. Click **Save**.

If you move your facecam later, edit the layout.

### Step 7: Add your assets (optional now)

Put these in your Assets folder:

- `music/` — background music that's licensed for YouTube (for example from the YouTube Audio Library).
- `sfx/` — sound effects (whoosh, boom, etc.).
- `fonts/` — fonts for captions.
- `overlays/` — images such as emojis or memes you own or are allowed to use.

AI-Editor never adds music or sound effects you didn't provide.

---

## 7. Setting up OBS (step by step)

These settings are free and make a **big** difference to how good AI-Editor's edits are. Menu names are from OBS Studio 30; they may differ slightly in other versions.

### 7.1 Why separate audio tracks matter

Normally a recording mixes your voice, game sound, and Discord into one sound. AI-Editor can separate them using AI, but it's never perfect. If OBS records each sound on its own **track**, AI-Editor knows exactly when *you* are talking, which improves captions, reaction detection, and clean cuts.

Our standard track setup:

| Track | Contains |
|---|---|
| 1 | Everything mixed (what viewers hear) |
| 2 | Your microphone only |
| 3 | Game audio only |
| 4 | Discord / voice chat only |

### 7.2 Recording settings

1. Open OBS → **Settings → Output**.
2. Set **Output Mode** to **Advanced**.
3. Open the **Recording** tab.
4. **Recording Path:** your AI-Editor Raw footage folder.
5. **Recording Format:** **MKV** (if OBS crashes, the recording is still safe).
6. **Audio Track:** tick **1, 2, 3, and 4**.
7. **Video Encoder:** **NVIDIA NVENC H.264** (or HEVC).
8. **Rate Control:** **CQP**, with a **CQ Level** around **18–22** (lower number = higher quality and bigger files).
9. Go to **Settings → Advanced → Recording** and tick **Automatically remux to mp4** if you prefer MP4 files. AI-Editor works with both.
10. Click **Apply**.

### 7.3 Assign sounds to tracks

1. In OBS, click **Edit → Advanced Audio Properties**.
2. For each audio source, tick the track boxes:

| Source | Tick tracks |
|---|---|
| Microphone | 1 and 2 |
| Desktop Audio or Game Capture audio | 1 and 3 |
| Discord (use an **Application Audio Capture** source set to Discord) | 1 and 4 |

3. Close the window.

**Tip:** Using **Application Audio Capture** for the game and for Discord (instead of Desktop Audio) keeps them properly separated. Notification sounds and music players then won't leak into the game track.

### 7.4 Enable the OBS WebSocket (for Stream Companion)

1. In OBS, click **Tools → WebSocket Server Settings**.
2. Tick **Enable WebSocket server**.
3. Leave the **Server Port** as `4455` unless you have a reason to change it.
4. Keep **Enable Authentication** ticked.
5. Click **Show Connect Info** and copy the **password** into AI-Editor's setup wizard.
6. Click **OK**.

### 7.5 Record while you stream (strongly recommended)

Twitch VODs only keep one mixed audio track and are lower quality. Recording locally at the same time gives AI-Editor much better material. Your RTX 4070 Ti can stream and record at the same time.

1. **Settings → General → Output**: tick **Automatically record when streaming**.
2. In **Settings → Output → Recording**, make sure the encoder is its own NVENC encoder (not "Use stream encoder"), so the recording is higher quality than the stream.
3. Click **Apply**.

If you do this, import the **local recording** into AI-Editor and use the Twitch VOD only for chat (chapter 10.3).

### 7.6 Twitch VOD track (optional)

If you play music on stream that isn't licensed for VODs, OBS can keep it out of the Twitch VOD:

1. **Settings → Output → Streaming** tab.
2. Enable **Twitch VOD Track** and choose a track that doesn't include the music.

---

## 8. Stream Companion

Stream Companion is a small app that runs in the background while you stream or record. It uses almost no computer power.

### 8.1 Starting it

1. Open **Stream Companion** from the Start menu, or tick **Settings → Start Stream Companion with Windows**.
2. An icon appears in the system tray (bottom-right of your taskbar).
3. Right-click the icon to see its status:
   - **OBS: Connected** — ready.
   - **Recording / Streaming: Active** — it is logging.
   - **League: Match detected** — League events are being logged.

**Always start Stream Companion before you go live or start recording.** If it wasn't running, AI-Editor still works, but without markers and League events.

### 8.2 Using markers

- Press **Mark moment** (`Ctrl + Alt + M`) right after something great happens. You don't need to be precise; AI-Editor looks at the moments leading up to your press.
- Press **Mark Short-worthy** (`Ctrl + Alt + S`) when a moment would make a great Short.
- You'll hear a quiet click (only you, not your stream) to confirm. You can turn this sound off in Companion settings.

Markers are the strongest signal AI-Editor has. Even a few per stream noticeably improves highlights.

### 8.3 League of Legends events

When a League match loads, Stream Companion automatically reads League's built-in, official local game data and logs kills, deaths, assists, multikills, objectives, and the result. You don't need to do anything, set up any account, or get any key.

It only works during an actual match (not in the lobby or champion select). This is normal.

### 8.4 Session log

Right-click the tray icon → **View session log** to see markers and events from today's sessions. AI-Editor matches these to your footage automatically during import.

---

## 9. Your everyday workflow

### 9.1 Stream day (Wardogs, League, Tarkov)

**Before going live**
1. Open **Stream Companion** and check it says **OBS: Connected**.
2. Go live in OBS (local recording starts automatically if you set it up).

**While streaming**
3. Press your **marker hotkeys** on great moments.

**After the stream**
4. Open AI-Editor → **Import** → add the local recording (and/or paste the Twitch VOD link for chat).
5. Tag the **game** and click **Start analysis**. Let it run (or queue it overnight).
6. When analysis finishes, go to **Create video** → **Highlights** or **Shorts**.
7. Review, render, and upload.

### 9.2 Let's Play recording day (The Blood of Dawnwalker)

1. Open **Stream Companion**.
2. Start recording in OBS. Play for about 2 hours.
3. Press markers on big moments (reveals, funny deaths, boss wins).
4. Stop recording.
5. In AI-Editor, **Import** the recording, tag **The Blood of Dawnwalker**, and start analysis.
6. **Create video** → **Let's Play**. AI-Editor proposes parts (usually about four 30-minute parts).
7. Check the split points on the Review screen, render all parts, and schedule your uploads.
8. Make a couple of **Shorts** from the same session to promote the parts.

### 9.3 Suggested weekly routine

- Queue analysis for every new recording overnight.
- Each morning, review and render what's ready.
- Once a week, check **Learning** suggestions (chapter 22) and clean up old cache (chapter 23).

---

## 10. Importing footage

### 10.1 Import a local OBS recording

1. Click **Import → Local recording**.
2. Choose the file from your Raw footage folder.
3. AI-Editor checks the file and shows the audio tracks it found. Confirm which track is which (it remembers this for next time).
4. Choose the **game**.
5. Choose the **layout** (facecam position).
6. Click **Import**.

### 10.2 Import a Twitch VOD

1. On Twitch, go to your channel → **Videos**, open the VOD, and copy the link from your browser's address bar.
2. In AI-Editor, click **Import → Twitch VOD**.
3. Paste the link.
4. Tick **Download chat** (recommended).
5. Choose the **game** and **layout**.
6. Click **Download and import**. Progress appears in the job queue.

**Important:** Twitch deletes VODs after a limited time depending on your account type. AI-Editor shows a warning for VODs close to expiring. Download VODs soon after streaming.

Because Twitch VODs have one mixed audio track, AI-Editor automatically separates your voice from game sound and teammates using your voice sample. This adds some time to analysis.

### 10.3 Using both a local recording and the VOD

If you recorded locally *and* want chat data:

1. Import the **local recording** first.
2. Open it in the Library, click **Attach Twitch chat**, and paste the VOD link.
3. AI-Editor downloads only the chat and lines it up with your recording.

### 10.4 Games that show up in one session

If you switch games during a stream, open the recording in the Library, click **Game sections**, and mark where each game starts. AI-Editor can suggest these automatically.

---

## 11. Analysis

### 11.1 What analysis does

For each recording AI-Editor:

1. Makes a small preview copy (proxy).
2. Separates voices (Twitch VODs only).
3. Transcribes everything you say, word by word.
4. Detects silence, loud moments, laughter, shouting, gunfire, and explosions.
5. Reads chat activity (if available).
6. Adds your markers and League events.
7. Detects game-specific moments (see chapter 21).
8. Uses local AI to rate moments as funny, intense, clutch, story-important, or boring, and writes a one-line summary.
9. Saves everything into your Clip Library.

### 11.2 How long it takes

For a 2-hour recording, expect **around 45–50 minutes**, a bit longer for Twitch VODs. Your PC can be used for light tasks meanwhile, but avoid gaming during analysis; the AI uses your graphics card heavily.

### 11.3 The job queue

Open **Queue** to see all jobs.

- **Pause / Resume** — stop a job and continue later without losing progress.
- **Reorder** — drag jobs to change which runs first.
- **Run overnight** — tick this to start the queue at a set time (for example 2:00 AM).
- **Shut down PC when finished** — optional.

If your PC restarts or AI-Editor closes during analysis, just reopen AI-Editor and press **Resume**. Finished steps are not repeated.

---

## 12. The Clip Browser

The Clip Browser shows every moment AI-Editor found.

### 12.1 What you see for each clip

- **Thumbnail and preview** — click to play.
- **Score** — 0 to 1. Higher is better.
- **Tags** — for example *funny*, *clutch*, *fail*, *boss fight*.
- **Summary** — a short description.
- **Signals** — icons for what made it stand out: marker, laughter, shouting, gunfire, chat spike, game event.
- **Used in** — which videos already use this clip.

### 12.2 Filtering and sorting

Filter by game, recording, date, tag, minimum score, "not used yet," or "marked by me." Sort by score, date, or length.

### 12.3 Rating clips

- 👍 **Thumbs up** — "this is a good moment." AI-Editor learns what you like.
- 👎 **Thumbs down** — "not a good moment."
- 📌 **Pin** — always consider this clip for highlights and Shorts.
- **Trim** — drag the start and end handles if the clip starts too early or ends too late.

Rating even 10–20 clips per week helps AI-Editor learn fast.

---

## 13. Style Profiles (teaching AI-Editor a look)

A Style Profile is a saved editing look. You can have as many as you like, such as "Tarkov Hype Highlights," "League Shorts," and "Dawnwalker Chill Let's Play."

### 13.1 Creating a profile from reference videos

1. Go to **Style Profiles → New profile**.
2. Give it a name.
3. Choose which **games** and **recipes** it's for.
4. Paste links to **2–5 YouTube videos** whose editing you like, or add local video files. Pick videos similar to what you want to make (same kind of game, same length).
5. Click **Analyze references**. This takes a few minutes per video.
6. AI-Editor shows a **draft profile** with sliders and a list of techniques it noticed.
7. Adjust anything you want (chapter 13.2).
8. Click **Save**.

**Tip:** 2–3 videos from the *same* creator gives a clearer, more consistent style than mixing lots of different creators.

**Note:** AI-Editor's measurements are estimates. Always check the sliders feel right.

### 13.2 Profile settings explained

| Setting | What it controls | Lower value | Higher value |
|---|---|---|---|
| **Cuts per minute** | How often the shot changes | Relaxed, natural pacing | Fast, energetic pacing |
| **Max dead air** | Longest silence allowed before cutting (seconds) | Tight, snappy | More breathing room |
| **Zooms per minute** | How often it punches in | Subtle | Very dynamic |
| **Zoom triggers** | What causes zooms (shout, laughter, kill, marker) | — | — |
| **Zoom strength** | How far it zooms in (1.1 = slight, 1.5 = strong) | Subtle | Dramatic |
| **Captions** | On or off | — | — |
| **Caption style** | Word pop, full sentence, karaoke highlight | — | — |
| **Caption position** | Where captions sit | — | — |
| **Caption size** | Small, medium, large | Less intrusive | Easier to read on phones |
| **Sound effects per minute** | How often SFX play | Clean | Meme-heavy |
| **SFX categories** | Which folders from your SFX library to use | — | — |
| **Music** | Background music on or off | — | — |
| **Music volume under speech** | How much music drops when you talk (dB) | Music stays loud | Music ducks away |
| **Hook length** | Seconds for the opening teaser | Quick start | Longer tease |
| **Technique notes** | Extra ideas found in references (e.g., "freeze frame on deaths") | — | — |

**Preview:** click **Preview on a sample clip** to see the profile applied before saving.

### 13.3 Recommended starting points

| Video type | Cuts/min | Zooms/min | Captions | SFX/min | Music |
|---|---|---|---|---|---|
| Dawnwalker Let's Play | Low (3–6) | Low (0.5–1) | Commentary only, medium | Very low (0–0.5) | Off (game music is part of the experience) |
| Highlights | High (10–16) | Medium (2–4) | Word pop, large | Medium (1–3) | Low, ducked |
| Shorts | Very high (15–25) | High (3–6) | Word pop, large, center | Medium (2–4) | Optional |

### 13.4 Editing, copying, and deleting

- **Edit** — change sliders anytime. Existing videos aren't affected until you recreate them.
- **Duplicate** — copy a profile to make a variation.
- **Delete** — removes the profile. Videos already rendered are untouched.

---

## 14. Rules (your editing tips)

Rules are tips you write in normal English. AI-Editor turns each into a precise instruction and shows you how it understood it.

### 14.1 Adding a rule

1. Go to **Rules → New rule**.
2. Type your tip, for example: *"Never cut during boss fights in Dawnwalker."*
3. Choose the **scope**: all videos, a specific game, a specific recipe, or both.
4. Click **Interpret**.
5. AI-Editor shows its understanding in plain words, for example: *"In The Blood of Dawnwalker, protect any section tagged as a boss fight from being cut."*
6. If it's right, click **Save**. If not, click **Rephrase** and try different wording, or adjust the fields manually.

### 14.2 Writing good rules

- **Be specific.** "Cut silences over 2 seconds" works better than "cut boring bits."
- **One idea per rule.** Split "cut loading screens and add zooms on kills" into two rules.
- **Use numbers where you can.** Seconds, minutes, how often.
- **Say which game** if it only applies to one.

### 14.3 Example rules

**Everywhere**
- "Cut any silence longer than 1.5 seconds in highlights and Shorts."
- "Never cut in the middle of a sentence."
- "Don't use the same clip in more than one Short."

**The Blood of Dawnwalker**
- "Never cut cutscenes or dialogue."
- "Speed up horseback travel longer than 30 seconds to 4 times speed."
- "If I die to the same boss more than twice, keep only the first and last attempt and show an attempt counter."
- "Don't caption in-game dialogue."

**Escape from Tarkov**
- "Cut stash and flea market time completely."
- "Speed up looting when I'm not talking."
- "Always keep the 30 seconds before a raid ends."

**League of Legends**
- "Cut champion select except the last 10 seconds."
- "Always include multikills in highlights."
- "Add a slow-motion replay on pentakills."

**Wardogs**
- "Cut the loadout menu."
- "Speed up helicopter flights with no fighting."
- "Zoom on my face when a vehicle explodes near me."

### 14.4 Which rule wins?

When instructions disagree, AI-Editor follows this order (top wins):

1. **Your rules**
2. Game defaults
3. Style Profile
4. What AI-Editor learned from your feedback
5. General defaults

### 14.5 Rules AI-Editor can't fully understand

If a tip doesn't match anything AI-Editor can do precisely, it saves it as a **note**. The AI still reads notes when choosing clips, so they still help. Notes are shown with a 📝 icon.

### 14.6 Turning rules on and off

Each rule has a switch. Turn a rule off to test a video without it, without deleting it.

---

## 15. Creating a Let's Play (parts)

### 15.1 Quick start

1. Go to **Create video → Let's Play**.
2. Choose the **recording**.
3. Choose the **Style Profile** (for example "Dawnwalker Chill Let's Play").
4. Check the **Length settings** (defaults below are already set for Dawnwalker).
5. Click **Build plan**.
6. The **Part Planner** shows the proposed parts. Review and adjust (chapter 15.4).
7. Click **Continue to review**, then render.

### 15.2 Length settings explained

| Setting | Default | What it does |
|---|---|---|
| **Mode** | **Split** | *Split* makes several parts from one session. *Condense* makes one shorter video. |
| **Target part length** | **30 min** | The ideal length for each part. |
| **Normal range** | **25–35 min** | Parts inside this range count as "on target." |
| **Story extension, preferred max** | **45 min** | How long a part may run to avoid splitting a story mission. |
| **Story extension, hard max** | **60 min** | A part will never go past this. |
| **Trim level** | **Light** | *Light* keeps more exploration and chat. *Standard* is balanced. *Tight* removes more. |
| **Leftover handling** | **Carry to next session** | What happens to a short leftover piece at the end of a session. |
| **Leftover minimum** | **15 min** | Pieces shorter than this are treated as leftovers. |
| **Recap at start** | Off | Adds a "previously on" recap (max 15 seconds). |
| **Hook endings** | On | Prefers ending parts right after an exciting moment. |
| **Speed-up indicator** | On | Shows a small fast-forward icon during sped-up travel. |

### 15.3 How AI-Editor decides where to split

AI-Editor follows these rules, in order:

1. **Never** splits during a cutscene, dialogue, choice, or fight.
2. **Avoids** splitting in the middle of a main story mission. Side quests and exploration can be split anywhere sensible.
3. Looks for the best break between **25 and 35 minutes**: a quest completion, day/night change, the end of a fight, or a loading screen.
4. If a story mission is still going, the part is **extended** until the mission ends, ideally by **45 minutes**.
5. If the mission still isn't over at **60 minutes**, it splits at the gentlest point available (between scenes or at a fade), adds a "To be continued" card, and flags it for you to check.
6. After a longer part, the remaining parts **go back to about 30 minutes**.
7. When two break points are equally good, it picks the one **right after an exciting moment**, so viewers want to watch the next part.

**How many parts will I get?** Usually about **four** from a 2-hour session. Sometimes three or five, because loading screens and menus are removed and story missions vary. AI-Editor never adds boring footage just to make four parts. If you're regularly getting three, try **Trim level: Light** (default) or record a little longer.

### 15.4 The Part Planner

The Part Planner shows your session as a long bar with split points.

- Each **part** shows its number, length, and a one-line summary.
- Parts over 35 minutes show a 📖 **story extension** badge explaining why.
- Flagged splits (inside a mission) show a ⚠️ icon.
- **Drag a split point** left or right to move it. It snaps to the nearest safe break point. Hold `Shift` to move it freely.
- **Add split** — click on the bar where you want a new split.
- **Remove split** — right-click a split point → **Remove**. The two parts join.
- **Re-plan** — click to let AI-Editor recalculate everything after your change.

### 15.5 Numbering and series

- Go to **Series** to manage your Dawnwalker playthrough.
- Part numbers continue across sessions automatically (Part 1, 2, 3, ...).
- To fix numbering, click **Series → Edit numbering**.
- Leftover pieces carried over from the last session appear at the start of the next session's first part, labelled **Carried over**.

### 15.6 Condense mode (one video per session)

Use Condense when you want a single video from a session.

1. Set **Mode** to **Condense** and pick a target, like 30 or 60 minutes.
2. AI-Editor removes loading screens, menus, and dead air, speeds up travel, then removes the lowest-value sections until it reaches your target.
3. Before removing anything, it checks whether that section sets up something later (like picking up a quest item). Those sections are kept or shortened.
4. Where big chunks are removed, a short transition or text card (such as "Later...") is added so viewers aren't confused.

**If story content doesn't fit:** AI-Editor won't secretly cut story. It will ask whether you want to switch to Split mode, use a longer target, or choose specific cutscenes to shorten.

---

## 16. Creating a Highlight video

### 16.1 Quick start

1. Go to **Create video → Highlights**.
2. Choose one or more **recordings** (you can combine several streams).
3. Choose the **Style Profile**.
4. Set **Target length** (default **10 minutes**).
5. Click **Build plan**.
6. Review and render.

### 16.2 Highlight settings explained

| Setting | Default | What it does |
|---|---|---|
| **Target length** | 10 min | Final video length (within about ±10%). |
| **Games** | All in selected recordings | Mix games or keep one game only. |
| **Minimum clip score** | 0.6 | Clips below this aren't considered. Lower it if you don't get enough clips. |
| **Hook** | On | Opens with a 5–15 second teaser of the best moment. |
| **Ordering** | Balanced | *Chronological*, *Balanced* (mixes intense and calmer clips), or *Best last* (builds to the strongest). |
| **Allow reused clips** | Off | Whether clips already used in other highlight videos can appear. |
| **Always include pinned clips** | On | Your pinned clips are always used. |
| **Always include markers** | On | Moments you marked with the hotkey are prioritized. |

### 16.3 Tips

- Mark moments during your stream. It's the single best way to get great highlights.
- If the video feels repetitive, increase **Minimum clip score** or choose **Balanced** ordering.
- Combine a week of streams for a "Best of the week" video.

---

## 17. Creating Shorts and TikToks

Vertical clips are built entirely inside AI-Editor and rendered here by default. The finished file is 1080×1920, the correct size for YouTube Shorts, TikTok, and Instagram Reels, so the same file works on all of them.

### 17.1 Quick start

1. Go to **Create video → Shorts**.
2. Choose recordings, or pick clips directly from the Clip Browser (select clips → **Make Shorts**).
3. Choose the **Style Profile**.
4. Choose **how many Shorts** to make.
5. Click **Build plan**.
6. Review each Short and render.

### 17.2 Short settings explained

| Setting | Default | What it does |
|---|---|---|
| **Length** | 15–60 seconds | AI-Editor picks the best length per clip within this range. Both platforms allow longer clips, but under 60 seconds tends to perform best. |
| **Platforms** | Universal | *YouTube Shorts*, *TikTok*, or *Universal* (safe for both). Controls where captions sit so platform buttons don't cover them. |
| **Layout** | Facecam top, gameplay bottom | Facecam takes the top third, gameplay the bottom two thirds. |
| **Gameplay crop** | Game default | Usually the center of the screen for shooters. |
| **Follow action** | Off | Moves the crop to follow movement on screen. |
| **Hook** | On | Starts on the reaction or adds a text teaser in the first 1–2 seconds. |
| **Captions** | Word pop, large, center | Bold captions for viewers watching without sound. |
| **Must make sense alone** | On | Skips clips that need context to understand. |
| **Link to full video** | On | Remembers which long video the Short came from. |
| **Spoiler check** | On (Dawnwalker) | Flags story Shorts for your approval. |

### 17.3 Safe zones (important for TikTok)

Each platform covers parts of the screen with its own buttons, username, and caption text. AI-Editor keeps your captions and the action clear of those areas.

- **Universal** (default) avoids the covered areas of *both* platforms, so you can upload the same file to YouTube Shorts and TikTok.
- Choosing a single platform gives you slightly more usable screen space.
- On the Review screen, tick **Show safe zones** to see shaded overlays of what each platform covers.

If you want separate versions, tick **Render per-platform variants**. You'll get one file per platform with captions positioned for each.

### 17.4 Adjusting a Short

On the Review screen for Shorts you can:

- Drag the **gameplay crop box** to reposition it.
- Drag the **facecam box** to resize or move it.
- Edit **caption text** if a word was misheard.
- Change the **start and end** of the clip.

### 17.5 Using Shorts to grow your channel

- Make Shorts from the same session as your Let's Play parts or highlight video.
- Publish Prep adds a line in the Short's description pointing to the full video. Paste the link once the full video is live.
- Tip: Shorts from funny deaths and big reactions often work best for new viewers, while story moments are best saved for the full episodes.

---

## 18. The Review screen

Every video goes through Review before rendering. Nothing is final until you say so.

### 18.1 Layout **[Screenshot]**

- **Preview player** (top) — plays the edit as planned.
- **Length bar** — your whole source recording, colored by what happens to each section.
- **Segment list** — every piece in the video, in order.
- **Effects panel** — effects on the selected segment.
- **Buttons** — Preview render, Render, Export, Save plan.

### 18.2 Length bar colors

| Color | Meaning |
|---|---|
| **Green** | Kept |
| **Gray** | Trimmed (removed) |
| **Blue** | Sped up |
| **Purple** | Protected (story, won't be cut) |
| **Gold** | Pinned by you (always kept) |
| **Red line** | Split point between parts |

Drag the **target length slider** to watch the bar update live and see exactly what would be cut.

### 18.3 Things you can do

- **Play** any segment by clicking it.
- **Reorder** segments by dragging (Highlights and Shorts).
- **Trim** a segment by dragging its edges.
- **Remove** a segment: select it and press `Delete`.
- **Restore** a trimmed section: click a gray area on the length bar → **Keep this**.
- **Pin** a section: right-click → **Pin**.
- **Unprotect** a story section: right-click → **Allow cutting** (use carefully).
- **Toggle effects**: switch individual zooms, captions, SFX, or text on or off.
- **Edit captions**: click caption text to fix mistakes.
- **Undo / Redo**: `Ctrl + Z` / `Ctrl + Y`.

Every change you make here teaches AI-Editor (chapter 22).

### 18.4 Saving and coming back

Click **Save plan** to keep your work. Find saved plans under **Projects**. You can close AI-Editor and continue later.

---

## 19. Rendering and exporting

### 19.1 Preview render

Click **Preview render** for a quick, low-quality version. Use it to check pacing and effects before the full render. It's much faster.

### 19.2 Final render

1. Click **Render**.
2. Choose a preset:

| Preset | Resolution | Use for |
|---|---|---|
| **YouTube 1080p60** | 1920×1080, 60 fps | Let's Play parts and highlights |
| **YouTube 1080p30** | 1920×1080, 30 fps | Smaller files, slower-paced content |
| **Vertical 1080×1920 60 fps** | Vertical | YouTube Shorts and TikTok |
| **Vertical 1080×1920 30 fps** | Vertical | Smaller vertical files |

3. Click **Start render**. Progress shows in the Queue.
4. Finished files appear in your **Outputs** folder, named by project and part number.

For Let's Plays, **Render all parts** queues every part at once.

Expected times: a 30-minute part around 10 minutes, a 10-minute highlight under 10 minutes, a Short under 2 minutes. Audio is automatically balanced to suit YouTube.

### 19.2b Vertical clips: render here, not in Resolve

Vertical clips are composed inside AI-Editor: the crop, the stacked facecam, and the captions are all part of the plan. Those layout effects don't transfer reliably into other editors, so:

- **Recommended:** render Shorts and TikToks directly in AI-Editor. They come out as finished files, ready to upload.
- If you do export a vertical project, AI-Editor automatically pre-renders the vertical segments onto a 1080×1920 timeline, so Resolve or Kdenlive shows them exactly as designed. You can add extra polish there, but the layout is already baked in.

### 19.3 Exporting to DaVinci Resolve (free)

Use this when you want to polish further.

1. On the Review screen click **Export → DaVinci Resolve (FCPXML)**.
2. Tick **Pre-render effects** if you want zooms, captions, and effects to come across exactly (recommended). Without it, only cuts and markers transfer.
3. Choose where to save.
4. In DaVinci Resolve, create or open a project.
5. Go to **File → Import → Timeline** and choose the exported file.
6. When asked, point Resolve to your media (your Raw footage folder and the export's media folder).
7. Your timeline appears with all cuts and markers.

### 19.4 Exporting to Kdenlive

1. Click **Export → Kdenlive (OpenTimelineIO)**.
2. Tick **Pre-render effects** if wanted.
3. In Kdenlive, use the **OpenTimelineIO import** option in the File menu (exact menu name can vary between Kdenlive versions).
4. Relink media if asked.

> **[Engineer: confirm and update these menu paths against current Resolve and Kdenlive versions.]**

---

## 20. Publish Prep

After rendering, open **Publish Prep** for each video.

### 20.1 Titles

AI-Editor suggests 3–5 titles. Click one to copy it, or edit it. For Let's Plays, titles follow your series format, for example *"The Blood of Dawnwalker — Part 7: [episode summary]"*.

Spoiler check is on for Dawnwalker, so titles avoid giving away major story moments. Always double-check anyway.

### 20.2 Description and tags

A ready-to-paste description with a summary, chapters, and tags. Edit freely. You can save a **description template** (for example with your Twitch link and socials) in **Settings → Publish templates**.

### 20.3 Chapters

AI-Editor writes chapter timestamps. YouTube requires the first chapter to start at `0:00`, at least three chapters, and each chapter at least 10 seconds long. AI-Editor follows these rules automatically.

### 20.4 Thumbnails

AI-Editor exports several frames with your strongest reactions and most exciting moments as PNG images in your Outputs folder. Open them in a free tool such as GIMP, Photopea, or Canva's free plan to add text and design your thumbnail.

### 20.5 Linking Shorts to full videos

After uploading a full video, paste its YouTube link into **Publish Prep → Linked video**. Every Short made from that video updates its description with the link.

### 20.6 Release planning

For Let's Plays, **Series → Release plan** lists parts in order. Add your planned upload dates to keep a steady schedule. AI-Editor does not upload for you.

---

## 21. Game guides

### 21.1 The Blood of Dawnwalker (Let's Play)

**What AI-Editor detects**
- Cutscenes (HUD disappears, letterbox bars, in-game subtitles).
- Dialogue and choices.
- Quest start and completion notifications.
- Day/night transitions.
- Combat, boss fights, deaths.

**What gets trimmed or sped up**
- Loading screens, menus, inventory, map, crafting — trimmed.
- Long travel — sped up.
- Repeated failed attempts — optional (use a rule).

**What's protected**
- Cutscenes, dialogue, choices. Main story missions are not split unless a part reaches 60 minutes.

**Tips**
- Record game audio on its own track (chapter 7) so dialogue stays clear under your commentary.
- Turn on in-game subtitles. They help AI-Editor detect dialogue, and captions are placed so they don't cover them.
- Keep your facecam away from where in-game subtitles appear.
- Press **Mark moment** after big story reveals. They make great hook endings.

### 21.2 League of Legends (streams)

**What AI-Editor detects**
- From League's official local game data (via Stream Companion): kills, deaths, assists, multikills, aces, objectives, game start and end.
- From audio and video: your reactions, chat spikes.

**What gets trimmed**
- Queue waiting, champion select, loading screens, long dead timers, post-game lobby.

**Tips**
- Always run **Stream Companion** during League. Without it, AI-Editor falls back to reading the screen, which is less accurate.
- No account setup or keys are needed for League data.
- Pentakills and outplays automatically score very high for highlights and Shorts.

### 21.3 Escape from Tarkov (streams)

**What AI-Editor detects**
- Gunfights (from game audio).
- Raid results from the end-of-raid screen (survived, killed, missing).
- Tense moments (quiet talking followed by gunfire).
- Extractions.

**What gets trimmed or sped up**
- Stash, flea market, hideout, raid loading — trimmed.
- Quiet looting and walking — sped up or cut.

**Tips**
- AI-Editor only looks at your recording. It never touches the game, so it's safe with BattlEye.
- Markers are especially valuable in Tarkov, because long quiet stretches can hide great moments.
- A rule like "always keep the 30 seconds before a raid ends" makes extraction moments land well.

### 21.4 Wardogs (streams)

**What AI-Editor detects**
- Firefights and explosions (from game audio).
- Vehicle moments (tanks, helicopters, big explosions).
- Match results.
- Kill feed reading, when enabled.

**What gets trimmed or sped up**
- Loadout and shop menus, redeploy waits — trimmed.
- Long drives and flights with no action — sped up.

**Tips**
- Wardogs is in early access, so its screens change with updates. If kill feed or match result detection stops working after a game update, go to **Settings → Game profiles → Wardogs → Detection** and turn off screen reading until AI-Editor is updated. Audio detection keeps working.
- Markers are the most reliable signal for Wardogs right now.

---

## 22. How AI-Editor learns from you

AI-Editor doesn't retrain AI. Instead it quietly remembers your decisions and adjusts.

### 22.1 What it learns from

- Thumbs up / down in the Clip Browser.
- Segments you remove, restore, trim, or reorder on the Review screen.
- Effects you switch off.
- Split points you move.

### 22.2 What changes

- **Clip scoring** — the kinds of moments you keep score higher; the kinds you remove score lower. Learned separately for each game.
- **Effect suggestions** — if you keep removing an effect, AI-Editor asks whether to use it less. Example: *"You've removed 8 zooms this week. Lower zoom frequency in 'Tarkov Hype Highlights'?"* Click **Yes**, **No**, or **Ask me later**.

### 22.3 Viewing and resetting

- **Learning → Summary** shows what AI-Editor has learned in plain language, for example *"You prefer funny deaths over long fights in Tarkov."*
- **Learning → Reset** clears learned preferences for one game or all games. Your profiles and rules are not affected.

---

## 23. Storage and cleanup

Everything lives on one drive, so keeping an eye on space matters.

### 23.1 Checking space

**Storage** shows:
- Free space on your drive.
- Space used by each project (raw, cache, outputs).
- Total cache size.

AI-Editor warns you before starting a job if free space is low (default warning below **100 GB**, adjustable in Settings).

### 23.2 Cleaning up a finished project

1. Go to **Storage**, select the project.
2. Choose a cleanup option:

| Option | Deletes | Keeps | Can you still make new videos from it? |
|---|---|---|---|
| **Clean cache** | Preview copies, separated audio, temporary files | Raw footage, analysis, outputs | Yes, fully |
| **Clean cache + outputs** | Cache and rendered videos | Raw footage and analysis | Yes, re-render when needed |
| **Archive** | Everything except analysis data | Analysis data (very small) | Only if you re-add the raw file later |

3. Click **Clean up** and confirm.

**AI-Editor never deletes your raw footage automatically.** Delete raw files yourself once you're sure you've uploaded everything you want.

### 23.3 Moving footage to another drive

If you move raw files, open the project and click **Relink media** to point AI-Editor to the new location.

---

## 24. Settings reference

> **[Engineer: complete this table with every setting, its exact default, and valid range.]**

| Area | Setting | Default | What it does |
|---|---|---|---|
| Folders | Raw / Cache / Outputs / Assets / Models | Set in wizard | Where files go. |
| Performance | Run AI on | GPU | Leave on GPU. |
| Performance | Unload AI models between steps | On | Prevents running out of graphics memory. |
| Performance | Proxy resolution | 540p | Size of preview copies. |
| Queue | Overnight start time | Off | Starts the queue automatically. |
| Companion | Mark moment hotkey | Ctrl+Alt+M | Logs a moment. |
| Companion | Mark Short-worthy hotkey | Ctrl+Alt+S | Logs a Short moment. |
| Companion | Confirmation sound | On | Quiet click when marking. |
| Companion | Start with Windows | Off | Launches Companion at startup. |
| OBS | WebSocket port / password | 4455 / from OBS | OBS connection. |
| Analysis | Transcription model | Large (turbo) | Accuracy of transcripts. |
| Analysis | Voice separation for VODs | On | Separates your voice from game audio. |
| Let's Play | Mode / target / range / extension / trim level | Split / 30 / 25–35 / 45–60 / Light | See chapter 15.2. |
| Highlights | Target length / min score / ordering | 10 min / 0.6 / Balanced | See chapter 16.2. |
| Shorts | Length / layout / captions | 15–60 s / Facecam top / Word pop | See chapter 17.2. |
| Render | Encoder | NVENC H.264 | Fast GPU encoding. |
| Render | Loudness target | About −14 LUFS | Suits YouTube's volume level. |
| Storage | Low space warning | 100 GB | When to warn. |
| Game profiles | Screen reading (per game) | On | Turn off if detection breaks after a game update. |

---

## 25. Troubleshooting

Every message AI-Editor shows you ends with a code in brackets, like `(Help: manual chapter 25, code E004)`. Find that code below for what it means and what to do.

> **[Engineer: this list grows with each phase. Codes E001–E020 exist as of Phase 0.]**

### Error codes

| Code | Message | What it means | What to do |
|---|---|---|---|
| **E001** | AI-Editor could not find FFmpeg | FFmpeg is the tool that reads and writes your video files. Either it isn't installed, or you installed it while this window was already open — Windows only tells *newly opened* windows where new programs live. | **First, close the window and open a new one**, then try again. That fixes it most of the time. If it doesn't, install FFmpeg, or set `tools.ffmpeg_dir` in Settings to the folder containing `ffmpeg.exe`. |
| **E002** | Your graphics card's video encoder (NVENC) is not available | NVENC is the part of your NVIDIA card that makes rendering fast. | Update your NVIDIA drivers and restart your PC, then run the setup check again. |
| **E003** | AI-Editor cannot write to one of its folders | One of your five folders is missing, read-only, or on a disconnected drive. | Check the folder still exists and the drive is connected, or pick a different folder in Settings. |
| **E004** | There is not enough free space to start this job | A 2-hour recording plus its working files can need tens of gigabytes. | Free some space, or clean up finished projects under Storage (chapter 23). |
| **E005** | A setting has a value AI-Editor cannot use | A setting is out of range or contradicts another one — for example a 30-minute target with a 40–50 minute normal range. | Correct the value in Settings. To start over, delete `config/settings.yaml` and the defaults come back. |
| **E010** | AI-Editor cannot find that video file | The file was moved, renamed, or its drive was disconnected. | Open the project and click **Relink media** to point at the new location (chapter 23.3). |
| **E011** | AI-Editor could not read that video file | The file may be incomplete, still being recorded, or in a format AI-Editor doesn't handle. | Make sure OBS has finished writing the file, then import it again. |
| **E012** | That recording has no audio | AI-Editor needs sound to find moments, transcribe speech, and place cuts. | Check your OBS audio settings (chapter 7) and record again. |
| **E020** | A job could not finish | A step failed. The steps that already finished were kept. | Open the **Queue** and press **Resume**. It continues from the step that failed, without repeating finished work. |

### Stream Companion says "OBS: Not connected"
- Make sure OBS is open.
- Check **Tools → WebSocket Server Settings** in OBS: server enabled, port matches AI-Editor.
- Re-copy the password from **Show Connect Info**.
- Check Windows Firewall isn't blocking AI-Editor (allow it on private networks).

### League events aren't being logged
- Events only appear during a loaded match, not in lobby or champion select.
- Make sure Stream Companion was running *before* the match started.
- Restart Stream Companion and check the tray status says **League: Match detected** during a game.

### My hotkey doesn't do anything
- Another app (game, Discord, OBS) may use the same keys. Choose a different combination.
- Some games block hotkeys when running as administrator. Try running Stream Companion as administrator too.

### "Not enough graphics memory" / analysis crashes
- Close games and other GPU-heavy apps during analysis.
- Make sure **Unload AI models between steps** is on.
- In Settings, choose a smaller AI model size.

### Analysis is very slow
- Check the Queue: AI-Editor may be running voice separation (Twitch VODs take longer).
- Make sure **Run AI on** is set to GPU.
- Update NVIDIA drivers.

### Captions have wrong words
- Click caption text on the Review screen to fix it.
- Re-record your voice sample if you changed microphones.
- Use separate audio tracks in OBS (chapter 7) for much better accuracy.

### Captions show teammates or game dialogue
- Confirm the correct mic track in the recording's **Audio tracks** settings.
- For VODs, re-record your voice sample for better recognition.
- Make sure the rule/setting "caption creator voice only" is on.

### Twitch VOD won't download
- Check the link is copied correctly and the VOD still exists (it may have expired).
- Subscriber-only VODs may need to be made public temporarily.

### A cutscene got cut in my Let's Play
- On Review, click the gray section → **Keep this**.
- Turn on in-game subtitles for future recordings; it improves detection.
- Add the rule "Never cut cutscenes or dialogue."

### I'm only getting 3 parts instead of 4
- This is normal for some sessions. Try **Trim level: Light**, or drag split points in the Part Planner.

### DaVinci Resolve shows media offline after import
- Right-click the clips → **Relink** and point to your Raw footage folder and the export's media folder.

### Wardogs detection stopped working after a game update
- Turn off **Screen reading** for Wardogs in Settings → Game profiles. Audio detection continues. Update AI-Editor when a fix is available.

### Getting help
Click **Help → Copy diagnostic info** and share it with your engineer. It includes logs and settings but no video files.

---

## 26. Frequently asked questions

**Does AI-Editor cost anything?**
No. It uses only free software and runs on your own PC.

**Does it need the internet?**
Only for installing, updating, downloading Twitch VODs and chat, and downloading reference videos. Analysis and editing work offline.

**Will it upload to YouTube for me?**
No. It prepares everything, and you upload yourself.

**Can it get my game accounts banned?**
AI-Editor is designed never to touch your games. It only reads your recordings, Twitch chat, OBS, and League's official local game data. See chapter 27.

**Does it train AI on my videos or send them anywhere?**
No. Nothing leaves your PC. It learns your preferences by remembering your choices locally.

**Can I use it for other games?**
Yes. Any game works with general detection (audio, reactions, markers, chat). The four supported games get extra game-specific detection.

**Can I play games while analysis runs?**
Not recommended. Analysis uses your graphics card heavily. Run it overnight or while you're away.

**What if I don't like any of AI-Editor's edits?**
Everything is adjustable on the Review screen, and every change teaches it. You can also export to DaVinci Resolve or Kdenlive and edit manually.

**Can I make a Short from a moment AI-Editor didn't find?**
Yes. On a recording's timeline, select a range → **Create clip**, then **Make Short**.

---

## 27. Staying safe (accounts, copyright, music)

### Your game accounts
- AI-Editor never reads game memory, injects into games, or automates input.
- Escape from Tarkov (BattlEye), League of Legends (Vanguard), and Wardogs anti-cheat are not affected by AI-Editor because it only works with your recordings.
- League events come from Riot's official, built-in local game data feature.
- Don't install third-party add-ons that claim to "improve detection" by reading games directly.

### Music and sound effects
- Only put music and sound effects you're allowed to use on YouTube in your Assets folder (for example tracks from the YouTube Audio Library).
- AI-Editor never adds music you didn't provide.

### Reference videos
- Reference videos are only studied on your PC to learn a style. AI-Editor never puts their footage into your videos.
- Downloading YouTube videos may go against YouTube's Terms of Service. You can use local files instead.

### Game footage
- Each game publisher has its own rules for monetizing videos of their games (Riot Games, Battlestate Games, Team17/Bulkhead, Bandai Namco/Rebel Wolves). Check their video policies before monetizing.

---

---

## Document information

| Item | Detail |
|---|---|
| Manual version | 1.0 (pre-build draft) |
| Written for | AI-Editor, as described in *Stream Auto-Editor — Project Specification v2.0* |
| Maintained by | The engineer, updated with every release |
| Where it lives | `docs/user-manual.md` in the project repository, and in the app under **Help** |

**Update checklist for each release**

- [ ] New or changed screens documented, with screenshots.
- [ ] Settings reference (chapter 24) matches the app exactly.
- [ ] New error messages added to troubleshooting (chapter 25).
- [ ] Game guides (chapter 21) updated after game patches that change detection.
- [ ] Menu paths for OBS, DaVinci Resolve, and Kdenlive re-checked.
- [ ] Glossary updated with any new terms.
- [ ] Reviewed with the creator.
