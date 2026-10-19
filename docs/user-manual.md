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
| **Reference video** | A video whose editing you like (a YouTube link or a file on this PC), used to build a Style Profile. |
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

### 5.1 Opening AI-Editor (the app window)

Double-click **AI-Editor** on your desktop (the purple play-button icon).

- A black window opens first. It says **AI-Editor is running**. **Leave it open** while you use AI-Editor. **Closing it quits AI-Editor.**
- A moment later, AI-Editor opens in your web browser. It's a page on your own PC, not a website. Nothing goes online, and nothing else on your network can see it. (The address is `http://127.0.0.1:7865`, where 127.0.0.1 means "this PC".)
- Closed the browser tab by mistake? Double-click the desktop icon again. It reopens the page; it doesn't start a second copy.
- After you close the black window, the browser page shows **"Connection to the server was lost"**. That's expected: AI-Editor has quit. Close the tab.
- Quitting while a job is running is safe. The job pauses, along with any FFmpeg or Twitch download it started. Next time, press **Resume** (11.3). Finished steps aren't repeated.

**Shortcut missing?** In a terminal in the AI-Editor folder, run `.\.venv\Scripts\ai-editor shortcut`. It puts the icon back on your desktop.

**"Another program is using port 7865"?** Something else is using AI-Editor's address. Run `ai-editor app --port 7866` instead.

### 5.2 The local AI (Ollama)

AI-Editor uses an AI model that runs on your own graphics card, through a free program called **Ollama**. It reads what was said in each clip and looks at a few frames, then describes the clip and rates it (12.3). Nothing is sent online.

1. Install Ollama from **ollama.com** (Download → Windows). It starts with Windows and sits in the tray. If it's closed, AI-Editor starts it when needed.
2. In AI-Editor, open **Settings → AI (on this PC)** and click **Download model**. The model, **Gemma 4 12B**, is about 8 GB and downloads once. Progress shows under **Jobs**; a paused download carries on where it stopped.
3. The line at the top of that section says **Ready: gemma4:12b**. From then on, clips are rated at the end of every analysis.

Everything else in AI-Editor works without it. Untick **Use the local AI** in Settings to switch it off.

**Don't run it while you play.** The AI and your game share the graphics card. If a game is running, rating crawls and can make the game stutter, so AI-Editor stops after one slow answer and tells you (E035). Press **Resume** in Jobs when you've finished playing.

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
| **Mark moment** | **Numpad +** | Logs a great moment. |
| **Mark Short-worthy** | **Numpad −** | Logs a moment that would make a great Short. |

Click a box and press your preferred key combination to change it. Two things to know when choosing:

- **While the Companion runs, that key belongs to it**, and your games won't see it. That's the price of doing this the safe way (chapter 27). Numpad + and Numpad − are good defaults because games rarely use them.
- **The numpad's Enter key can't be used.** Windows can't tell it apart from the main Enter key here, so reserving it would take Enter away from every program. AI-Editor refuses it rather than doing that.

Tip: if you have a Stream Deck or spare mouse buttons, assign F13–F24 to them and use those.

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
- `sfx/` — sound effects (boom, hit).
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
| Spotify (or whatever plays your music) | 1 and 5 |

3. Close the window.
4. **Settings → Output → Recording**: under **Audio Track**, tick **1 to 5**, so all five are recorded.

**Tip:** Using **Application Audio Capture** for the game and for Discord (instead of Desktop Audio) keeps them properly separated. Notification sounds and music players then won't leak into the game track.

**Music (Spotify) on track 5.** Finished videos are rebuilt from tracks 2–5, so each sound can be handled on its own: your music is added back underneath, kept out of the way of talking (19.2e). Recordings from before you added track 5 still work: AI-Editor takes the music out of track 1 instead. Only play DMCA-free music if it goes in your videos. Each source ticks only its own track besides 1: if the microphone were also on track 3, say, the finished video would have your voice in it twice.

### 7.4 Enable the OBS WebSocket (for Stream Companion)

1. In OBS, click **Tools → WebSocket Server Settings**.
2. Tick **Enable WebSocket server**.
3. Leave the **Server Port** as `4455` unless you have a reason to change it.
4. Keep **Enable Authentication** ticked.
5. Click **Show Connect Info**, then click **Copy** next to **Server Password**.
6. Click **OK**.
7. In AI-Editor's setup wizard (until the app window arrives: run `ai-editor setup-obs` in a terminal with OBS open), paste the password. It doesn't show as you type or paste; press **Enter**.
8. You should see **Connected to OBS** and the OBS version.

The password is only saved once OBS accepts it, in `config/settings.local.yaml`. That file stays on your PC: it's never uploaded to GitHub, and it isn't part of `settings.yaml`. The password itself never travels, even to OBS: AI-Editor answers a one-time question from OBS that proves it knows the password.

### 7.4a Marker keys in OBS (so they work inside games)

Some games, League of Legends among them, stop other programs' hotkeys from working while the game is in front: on your first League stream with the Companion, Numpad + only worked after alt-tabbing out. OBS's own hotkeys keep working in games, so OBS catches your marker keys and passes them on to the Companion.

1. With OBS open, run `ai-editor setup-obs --markers`. It adds a scene called **AI-Editor markers** with two empty, invisible sources: **Mark moment** and **Mark Short**. Running it again changes nothing.
2. In OBS: **File → Settings → Hotkeys**, and type **Mark** in the filter box at the top.
3. Under **AI-Editor markers**, click the box next to **Show 'Mark moment'** and press **Numpad +**.
4. Click the box next to **Show 'Mark Short'** and press **Numpad −**.
5. Leave both **Hide** boxes empty (the Companion switches them back off itself) and click **OK**.

The **AI-Editor markers** scene is never put on air, so viewers can't see or hear anything. Don't add it to your other scenes, and don't switch to it. You can delete it any time; the Companion's **Keys** line will then tell you it's missing.

**Why this is safe for your accounts:** OBS catches the key exactly as it does for your other OBS hotkeys, and the Companion only hears from OBS. AI-Editor has no keyboard code involved at all.

If you'd rather the Companion catch the keys itself (for games that don't block it), set `marker_keys: windows` under `companion:` in `config/settings.yaml`.

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

1. Do chapter 7.4 once (connect AI-Editor to OBS).
2. In AI-Editor, the **Stream Companion** line near the top says **Not running**. Click **Start**.
3. It opens in a window of its own, "AI-Editor Stream Companion". Leave that window open (minimised is fine) while you play. **It keeps going if you close AI-Editor or the browser.**
4. The line in AI-Editor turns green and shows what it's doing, every second:
   - **OBS connected**, or **waiting for OBS to open** (normal while OBS is closed; it checks every 5 seconds).
   - **Live since 19:55**, **Recording since 19:55**.
   - The game on screen, from your OBS scene (8.1b).
   - How many moments you've marked, and when the last was.
   - During a League match: **League: match running: 4/1/6, double kill, 1 objective** (8.3).
5. When you've finished, click **Stop**. (Or close its own window.)

Its window can't be stopped or paused by accident: **Ctrl+C does nothing there** (so copying something while it has focus is safe), and clicking inside it doesn't pause it. If something unexpected goes wrong mid-stream, it notes it in the log file and carries on rather than closing.

It can't run twice: **Start** while it's already running just says so.

**Always start Stream Companion before you go live or start recording.** If it wasn't running, AI-Editor still works, but without markers, scene changes (which keep clips out of "BRB" and your ending screen) and League events.

**Not built yet:** a tray icon, and starting it with Windows.

#### 8.1a Starting it from the command line

1. Do chapter 7.4 once (connect AI-Editor to OBS).
2. Open a terminal in the AI-Editor folder with the venv active and run `ai-editor companion`.
3. A small status panel appears. Leave that window open (minimised is fine) while you play:

| Line | Shows |
|---|---|
| **OBS** | **Connected (OBS 32.x)**, or **Not connected**, which is normal while OBS is closed. It checks again every 5 seconds. |
| **Recording** / **Streaming** | **On since 21:30:05**, or **Off**. |
| **Keys** | **set in OBS: Show 'Mark moment', Show 'Mark Short'** when chapter 7.4a is done. If it says **not set up in OBS yet**, do 7.4a. |
| **Session** | The session name, from the moment you record or go live. |
| **Game** | The game on screen, from your OBS scene (see 8.1b). **—** on a scene that isn't a game, like "Brb". |
| **League** | **waiting for a match** while you record on your League scene, then **match running: 4/1/6, double kill** (kills/deaths/assists) during one (8.3). |
| **Logged** | How many things it has noted since you started it. |

4. When you've finished, click **Stop** in AI-Editor, or close that window. (Ctrl+C doesn't stop it, so it can't be stopped by accident mid-stream.)

It uses next to no computer power: it sleeps until OBS tells it something changed.

#### 8.1b Which game you're playing

If you have **one OBS scene per game**, the Companion notes every time you switch scene. So when you play Wardogs and then switch to Tarkov halfway through a stream, AI-Editor knows which part of the recording is which game. It uses that to:

- label each clip with its game (a Tarkov moment in a Wardogs stream stays a Tarkov moment);
- include that recording when you make highlights of **either** game;
- set the recording's game to whichever was played longest, if you didn't give one at import.

A scene named after its game is recognised on its own: "Wardogs", "Escape From Tarkov", "League of legends" and "The Blood Of Dawnwalker" all work, whatever the capital letters. Scenes like "Brb", "Start With Timer" or "Ending Screen" aren't a game, and nothing changes while they're showing.

If a scene's name doesn't say the game (say, "Scene 2"), tell AI-Editor in `config/settings.yaml`:

```yaml
companion:
  scene_games:
    Scene 2: Escape from Tarkov
```

### 8.2 Using markers

- Press **Mark moment** (**Numpad +**) right after something great happens. You don't need to be precise; AI-Editor looks at the moments leading up to your press.
- Press **Mark Short-worthy** (**Numpad −**) when a moment would make a great Short.
- The **Marked** line in the Companion counts up. There's no sound: see below.
- Marking while OBS isn't recording still saves the marker, but there's no footage to attach it to.

**No confirmation sound, on purpose.** There used to be a click when you marked. On your 26 Sep League stream it reached viewers through your **microphone**: a stand-up mic hears your headphones or speakers, and the compressor on it lifts quiet sounds. Nothing in OBS's settings can show that happening, so the click is off by default and should stay off. Marking through OBS (chapter 7.4a) is reliable without it. If you ever switch it back on (`confirmation_sound: true`), the Companion still keeps it silent while OBS captures Desktop Audio, but it can't protect you from the mic hearing it.

Markers are the strongest signal AI-Editor has. Even a few per stream noticeably improves highlights.

**What happens to them:** when you import the recording, AI-Editor works out which session produced it — from the file OBS was writing, or from the time if the file was renamed or converted. Your markers then appear at the top of the moments list as **"You marked these"**, with their time in that recording. If a session was never matched, the **In library** column in `ai-editor sessions` stays empty.

`ai-editor companion --test-sound` plays both marker sounds, only useful if you switch the sound back on.

### 8.3 League of Legends events

When a League match loads, Stream Companion reads League's own **Live Client Data API**: a small, official, read-only feed that the League game itself runs on your PC during a match, made by Riot for tools like this one. It logs, each at the exact second it happened in your recording:

- your kills, deaths and assists (and everyone else's kills, for spotting team fights);
- double, triple, quadra and penta kills, aces and first blood;
- Dragons (which kind), Baron, Rift Herald, Voidgrubs and Atakhan, turrets and inhibitors, and whether one was **stolen**;
- when the match started, and whether you won.

You don't need to do anything, set up an account, or get a key. The times come from the game's own clock, so an event lands on the right second in your recording even though the Companion only asks every couple of seconds.

**When it asks:** only while OBS is recording or streaming, and only while your scene is your League scene (or a scene that isn't a game, like "Brb"). On your Wardogs or Tarkov scenes it doesn't ask at all. Outside a match (lobby, champion select) League doesn't answer, which is normal: the **League** line says **waiting for a match**.

**After you import the recording**, the import message adds a line like *"League events: 2 matches (1 won), 9/4/12, triple kill, 3 objectives"*. In the **Library**, pick the recording and open **Every League event** under its details: each one with its time in the recording (`1:02:13 · Triple kill`), so you can jump there in a video player and check. Turrets your teammates take aren't listed, to keep it short, but they're still logged.

**What uses them** (Phase 2E-2, version 0.15):

- **Picking clips.** Every kill of yours lifts the fight leading up to it (12 seconds before, 3 after), and multikills, aces and your team's objectives more. Champions dying close together count as a **team fight**. Your **deaths** only count when you react: laughing, shouting, or clearly louder than usual. A quiet death isn't a highlight; a loud one often is.
- **Clean edges.** A clip doesn't end while champions are still dying, so the kill that pays the fight off stays in. A match starting or ending works like a scene change: a clip never runs across it.
- **Downtime.** Queue, champion select, loading and the post-game lobby (League time outside a match) are never picked, unless you marked a moment there. A gap of more than 12 minutes between logged matches is left alone: that's more likely a match the Companion didn't see.
- **Reasons you can read.** The **Why** column in Review and the Clips tab say what happened: **Kill**, **2 kills**, **Triple kill**, **Penta kill**, **Ace**, **Baron steal**, **Victory**. A clip's details in the Clips tab list its League events with their times.
- **Effects** (19.2d) and **Shorts** (17): your multikills, aces and steals.
- **Titles and chapters.** The local AI is told the clip's League events, so a chapter can be called "Triple kill in bot lane" when it really was one.

Recordings made before version 0.14 have no League events; they keep working as before.

**Switching it off:** `companion.league_events: false` in `config/settings.yaml`.

**Is it safe for my account?** Yes: see chapter 27. It's Riot's documented feature, read-only, on your own PC, and the Companion checks that the answer really comes from League before using it.

### 8.4 Session log

Right-click the tray icon → **View session log** to see markers and events from today's sessions. AI-Editor matches these to your footage automatically during import: by the file OBS was writing (told when recording starts or stops), or else by when the recording started (from OBS's file name, like `2026-10-08 19-55-02.mkv`, or the file's own dates).

**The import always says what it found** in the Jobs list: "Stream Companion log found: 5 highlight mark(s) and 11 Shorts mark(s)…", or "No Stream Companion log matched this recording, so none of your marks are in its clips." The line above the Clips list says the same for each recording ("your marks: 5 highlight, 11 Shorts", or "no Stream Companion log linked").

If a log turns up for a recording that had none (as for the streams of 6-9 October 2026, when the Companion noticed OBS recording a moment late), AI-Editor links it the next time it starts and cuts that recording's clips again with your marks in, shown in Jobs as **Finding your Stream Companion marks**. Your 👍/👎, adjusted cuts and clips used in videos stay as they are. Your mark wins over a 👎 you gave a clip of the same moment that didn't have the mark.

From the command line: `ai-editor sessions` lists recent sessions, and `ai-editor sessions <session>` shows one in full. Each line has the time it happened, how far into the stream it was, and how far into the recording.

A **session** runs from the moment OBS starts recording or streaming until both have stopped. If you go live and OBS starts recording a few seconds later, the **Recording started** line shows how far into the stream that was. That's exactly how far into the Twitch VOD your recording begins, which is what lines chat up with it.

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

1. Open the **Import** tab.
2. Pick the recording from **New in your raw folder**. It lists the videos in your Raw footage folder that aren't imported yet, newest first, with their size and date. (Recording somewhere else? Click **Browse...**, or paste the file's location.)
3. Choose the **game**, or leave it empty. AI-Editor then works it out from the file name or from the Stream Companion's session. Not listed? Type its name.
4. Leave **Analyse straight after importing** ticked. This is usually what you want.
5. Click **Import**. The job appears under **Jobs** at the top, with a progress bar for each step. You can use the other tabs meanwhile.

**More options** (usually not needed):
- **Sound tracks, in order:** only if AI-Editor guessed the tracks wrong, e.g. `mixed,mic,game,voice_chat`.
- **Twitch link:** for a VOD you downloaded yourself (10.3). AI-Editor reads the game and stream date from Twitch.

**Good to know**
- **Your recording is never copied, moved or changed.** AI-Editor reads it where it is.
- **A file OBS is still recording isn't imported.** If the file changed in the last minute, AI-Editor asks you to stop recording first.
- **Not built yet:** choosing the layout (facecam position).

### 10.1a Importing from the command line

> **[Engineer: the command-line version of 10.1. The app window is now the main way to import; this stays for testing.]**

1. Open a terminal in the AI-Editor folder and turn on its Python environment:

   ```powershell
   cd C:\Users\trent\Desktop\Projects\AI-Editor
   .\.venv\Scripts\Activate.ps1
   ```

2. Import your recording. Put the file path in quotes:

   ```powershell
   ai-editor import "D:\path\to\your recording.mp4"
   ```

3. AI-Editor shows what it found: the game (guessed from the file name), the length, resolution, and audio tracks. Then two progress bars run:
   - **Making preview copy (proxy)** — a small 540p, 30 fps copy used for previews and analysis.
   - **Extracting audio tracks** — each audio track saved separately for analysis.
4. When it finishes, it shows how long each step took and where the preview copy is. Open it in any video player to check it.

**Options**

| Option | What it does | Example |
|---|---|---|
| `--game` | Sets the game when the file name doesn't say. | `--game "Escape from Tarkov"` |
| `--tracks` | Labels the audio tracks in order, if the guess is wrong. | `--tracks mixed,mic,game,voice_chat` |

**Good to know**

- **Your recording is never copied or changed.** AI-Editor reads it where it is. The preview copy and audio go in your cache folder, under `recordings\<a long code>\`.
- **Running the same import again is instant.** Finished work is reused.
- **Stopping partway is safe.** Press `Ctrl + C`. Run the same command again later and it carries on from where it stopped.
- **Moved a recording?** Import it from its new location. AI-Editor recognises it and updates where it looks, rather than starting over.
- **See everything you've imported** with `ai-editor library`.

### 10.2 Import a Twitch VOD

1. On Twitch, go to your channel → **Videos**, open the VOD, and copy the link from your browser's address bar.
2. In AI-Editor's **Import** tab, scroll to **A Twitch VOD** and paste the link.
3. Click **Check** (optional). It shows the VOD's title, game and length, and warns you if Twitch deletes it soon.
4. Leave **Download the chat too** and **Analyse straight after importing** ticked.
5. Set the **game** only if Twitch has it wrong.
6. Click **Download and import**. The video goes into your Raw footage folder. Progress shows under **Jobs**.

The VOD must be public. For a private one, download it from your Twitch dashboard, then import the file (10.1) with its link under **More options**.

**Important:** Twitch deletes VODs after a limited time depending on your account type. AI-Editor shows a warning for VODs close to expiring. Download VODs soon after streaming.

Because Twitch VODs have one mixed audio track, AI-Editor automatically separates your voice from game sound and teammates using your voice sample. This adds some time to analysis.

### 10.2a Twitch VODs from the command line (until the app window arrives)

> **[Engineer: command-line versions of 10.2 and 10.3, used while AI-Editor is being built.]**

**A public VOD: one command does everything.** It downloads the video into your Raw footage folder, imports it, and attaches the chat:

```powershell
ai-editor import-twitch "https://www.twitch.tv/videos/2875855539"
```

Links from **Content → Video Producer** in your Twitch dashboard work too, and so does just the number. The game is read from Twitch, so you don't need `--game`. Add `--no-chat` to skip the chat.

**A private VOD:** Twitch won't let AI-Editor download it (error E041). Either make it public for a few minutes, or download it yourself from **Video Producer** and import the file, giving the link so the game and stream date still come from Twitch:

```powershell
ai-editor import "F:\AI-Editor\raw\Twitch Vod.mp4" --vod "<the VOD's link>"
```

(Without a link, use `--source twitch --game Wardogs` instead.)

**Adding chat later**, for example once the VOD is public:

```powershell
ai-editor attach-chat 3 "<the VOD's link>"
```

AI-Editor shows how many messages it found, from how many viewers, and the busiest moments. Messages from chat bots such as StreamElements are ignored (Settings → Twitch → Ignored chatters).

### 10.3 Using both a local recording and the VOD

If you recorded locally *and* want chat data:

1. Import the **local recording** first.
2. Open it in the Library, click **Attach Twitch chat**, and paste the VOD link.
3. AI-Editor downloads only the chat and lines it up with your recording.

From the command line: `ai-editor attach-chat <recording number> "<VOD link>"`.

**If the Stream Companion was running, you don't have to line anything up.** It logged how far into the stream your recording began, and AI-Editor uses that number, telling you which one it used. If it wasn't running, chat lines up from the start of the recording, and you can correct it with `--starts-at <seconds>` — usually 0–5 seconds if OBS starts recording automatically when you go live.

### 10.4 Games that show up in one session

If the Stream Companion was running and you have one OBS scene per game, this is automatic: see 8.1b. Otherwise, open the recording in the Library, click **Game sections**, and mark where each game starts.

---

### 10.5 The Library

The **Library** tab lists every recording you've imported, newest first:

| Column | Shows |
|---|---|
| Sound | **4 tracks** (separate mic, game, Discord) or **1 mixed track** |
| Status | **Analysed**, **Not analysed yet**, **Analysis paused** or **Analysis failed**, **Import unfinished**, or **Video deleted (kept for learning)** (deleted or moved; see 23.4) |
| Clips | How many candidate clips analysis found |
| Chat | Twitch chat messages attached. For a VOD without chat, how many days Twitch still keeps it |

Use the search box above the table to filter it. Click a row, or pick it under **Recording**, to see its details. Then:

- **Analyse (or resume):** analyses it, or carries on where it stopped. It finishes an unfinished import first.
- **Watch the preview copy:** opens the small preview copy in your video player. After analysis, VLC shows its subtitles by itself.
- **Show the file in Explorer:** opens the folder with the original recording selected.

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
8. Asks the local AI (5.2) about each clip: a rating out of 10, a one-line summary, and whether it works as a Short (12.3). About 2 minutes per stream. Skipped, with a note, if the AI isn't set up.
9. Saves everything into your Clip Library.

### 11.1a Analysing from the command line (until the app window arrives)

> **[Engineer: this section covers the command-line tool used while AI-Editor is being built. The app window arrives in Phase 1H.]**

1. Import the recording first (chapter 10.1a). Then find its number:

   ```powershell
   ai-editor library
   ```

2. Analyse it, using its number (or its file path in quotes):

   ```powershell
   ai-editor analyze 1
   ```

3. **The first time only**, AI-Editor downloads two AI models, about 4.6 GB altogether, into your Models folder. After that, analysis works offline.
4. Four progress bars run:
   - **Preparing audio** — makes small copies of the audio in the form the AI models expect.
   - **Transcribing speech** — writes down every word, with the moment it was said.
   - **Listening for laughter, shouts, gunfire** — recognises those sounds second by second.
   - **Measuring loudness** — how loud each second is, to find silence and sudden spikes.
   - **Finding scene changes** — where the picture cuts to a menu, loading screen or scoreboard, so clips don't run into one. About 3 minutes per 2 hours.
   - **Checking for black screens** — how bright the picture is each second, so a black screen never becomes a clip. About a minute per 2 hours.
5. When it's done, AI-Editor shows **what it heard**: how much talking, how much near-silence, and a list of **moments to check** with times such as `0:41:07`.

**Checking the results yourself**

- **The transcript:** open the preview copy (its path is shown at the end) in **VLC**. The subtitles appear by themselves, because AI-Editor saves them next to the preview copy with the same name. Watch a few minutes: are the words right, and do they appear as they're said?
- **The moments:** in VLC, press `Ctrl + T` and type a time from the list to jump there. Is there really laughter, shouting or gunfire at that moment?
- **Loudest moments** are the seconds that are loudest *compared with the rest of that recording*; the number shows how far above normal (for example `1.5x`). On a single mixed track these include the game's loud moments as well as yours.
- To see the list again later without re-analysing: `ai-editor moments 1`.

**Good to know**

- **One mixed audio track?** Then the transcript includes everyone audible — in-game characters, teammates — not only you. With OBS set up as in chapter 7, AI-Editor transcribes your microphone track alone.
- **"Set aside" phrases.** Over music or loud game sound, the speech-recognition AI sometimes "hears" words nobody said — very often YouTube-style sign-offs such as *"see you next time"*. AI-Editor sets aside phrases that are both unsure **and** unnaturally slow, and says how many it set aside. It never removes words just because of *what* they say, so your real sign-offs are kept.
- **Stopping partway is safe.** Press `Ctrl + C`; run the same command again later and it carries on.
- **Changed the silence threshold?** Run `ai-editor analyze` again — it takes seconds, because nothing slow is redone; the saved results are simply re-read with the new setting.

### 11.1b Ranking the best moments (until the app window arrives)

Analysis records *what* it heard, second by second. Ranking turns all of it into one number per second — **how good is this moment** — so the best bits can be found without watching the whole recording.

```powershell
ai-editor score 1
```

You get the best moments, highest first, with the reason each one scored:

| Column | Means |
|---|---|
| **Time** | Where to jump to in the preview copy. |
| **Score** | Compared with this recording's own best moment, which always scores 1.00. A 2-hour stream and a quiet Let's Play are both scored on their own terms. |
| **Why** | Which signals lifted it: *you marked it*, *laughter*, *gunfire*, *chat busy*, *loud*, *talking*. |

It also lists anything it couldn't use — for example *chat busy* on a local recording with no chat attached, or *you marked it* when the Stream Companion wasn't running.

**What counts, and how much,** is in Settings under `scoring` (chapter 24). The defaults:

- **Your markers count most.** They also count *backwards*: you press after the good bit, so a press lifts the **minute before** it, easing off the further back it goes. That's `marker_lookback_sec`.
- Then laughter, screaming, shouting, chat activity, explosions, gunfire, and sudden loudness.
- Silence counts against a moment, and talking counts slightly for it.

Scores are worked out fresh each time, so changing a weight and running `ai-editor score` again is instant — nothing is re-analysed. Attaching chat or importing markers changes them too.

**This is the list to argue with.** Jump to the times in VLC and tell your engineer which are wrong; the weights exist to be corrected.

### 11.1c Clips (until the app window arrives)

After analysis, AI-Editor cuts the best moments into **clips**: the candidates every video recipe chooses from later. You don't have to do anything for this — it happens at the end of every analysis, and takes a couple of seconds.

```powershell
ai-editor clips 1
ai-editor clips 1 --export 10
```

The first lists the clips, best first, with start and end, length, score, why it scored, and what was said. The second also saves the best 10 as small videos in your Outputs folder, under `clip-previews\Recording 1 - <title>`, named by rank, time and score, each with its subtitles beside it. Add `--open` to open that folder in File Explorer. (Typing a folder's path into the terminal doesn't open it — PowerShell tries to run it as a command.)

**How the edges are chosen**

1. The **core** is the stretch around a peak that stays above half its score. A long fight is one clip, not a dozen.
2. **Context before:** 30 seconds before the core, because the cause of a reaction comes before it — the joke before the laugh, the fight before the kill.
3. **After:** 4 seconds, so the reaction finishes.
4. **Scene changes:** a clip never opens on, or runs on into, a menu, loading screen, respawn screen or scoreboard. Cutscenes cut between camera angles every few seconds, and those don't stop a clip. Neither does a change with action right before it — getting downed mid-fight is a scene change too, and the fight belongs in the clip.
5. **Clean edges:** a clip ends where you **stop talking** — at least a second of quiet, running up to 10 seconds longer if that's what it takes, rather than stopping on a full stop while you carry on. Starts move up to 6 seconds to land on a pause or the start of a sentence. Neither edge is ever inside a word. If you're talking straight through a scene change, the half-word is dropped rather than cut in two.
6. Clips are 15–90 seconds. The recipes trim them further to fit each video.

Clips you've rated, pinned or used in a video are never replaced when clips are rebuilt.

### 11.2 How long it takes

For a 2-hour recording, expect **around 45–50 minutes**, a bit longer for Twitch VODs. Your PC can be used for light tasks meanwhile, but avoid gaming during analysis; the AI uses your graphics card heavily.

### 11.3 The job queue

**Jobs**, at the top of the window, lists everything you've started. One job runs at a time, because they all need the graphics card. The rest wait their turn. Each job shows a progress bar per step, how long it's taken, and what it found.

- **Pause:** stops the running job at its next progress update, and holds the waiting ones. Use it before you game or stream, so AI-Editor isn't using the graphics card. The step it was in starts again from 0% on Resume. A half-made preview copy can't be continued, only redone. Every step that had already finished is kept.
- **Resume:** carries on with paused jobs, and retries any that stopped with a problem. Finished steps are not repeated.
- **Clear finished:** tidies finished jobs off the list.

If your PC restarts or AI-Editor closes during analysis, reopen AI-Editor and press **Analyse (or resume)** on that recording in the **Library** (10.5). Finished steps are not repeated.

**Not built yet:** reordering jobs, running overnight at a set time, and shutting down the PC when finished.

---

## 12. The Clip Browser

The **Clips** tab shows every moment AI-Editor found in a recording, best first.

### 12.1 What you see for each clip

1. Pick a **Recording**. Under **Show**, choose **Not used yet** (the default), **All**, or **Rated**. A line above the list counts its clips and your ratings, how many minutes of video your unused 👍 clips make, and your marks from the Stream Companion (8.4). A clip with your mark in it has a ⭐ in front of its **Why** ("⭐ you marked it (Short)"), here and in Review.
2. Each row is one clip:

| Column | Shows |
|---|---|
| Time | Where it is in the recording |
| Length | How long the clip is in the library. Generous on purpose, so nothing good is lost |
| In a video | How long it is once a highlight video trims it to its moment: about 15 s of lead-up, never more than 50 s, never cut mid-word. "-" means it can't go in (rated down, or during "BRB") |
| Score | 0 to 1. Higher is better. A moment you marked scores 1.00 |
| Why | What made it stand out: you marked it, laughter, shouting, gunfire, chat busy, loud... |
| AI says | The local AI's rating out of 10 and what happens, e.g. "7/10 Teamfight engagement and multi-kill" (12.3) |
| You said | Your words in it |
| Rated | 👍 or 👎 if you've rated it |
| Used | **yes** once a rendered video uses it |

3. **Click a clip** to play it beside the list. It plays from the preview copy, so it starts straight away; the finished video is full quality. Underneath are what the AI says about it, all its words, its game, and the video it's used in.

**Not built yet:** thumbnails, pinning, trimming, and filtering by game or date.

### 12.2 Rating clips

Click a clip, then:

- 👍 **Good clip:** **it goes into your next highlight video**, whatever its score, so you see it in Review for the final check. Already made the video? Add it there with **Add a clip** (18.2).
- 👎 **Not good:** that moment never goes into a highlight video, even a moment you marked, and even if the clip is cut slightly differently later.
- **Clear rating:** undo either.

Every rating is kept, with what the clip sounded like, so AI-Editor can learn what you like (Phase 3). Rating even 10–20 clips a week helps.

### 12.3 What the AI says

For every clip, the local AI (5.2) reads what was said and what chat wrote, looks at three frames, and gives:

- **A rating out of 10**, for viewers who weren't watching live.
- **A one-line summary**, like "Streamer rages over teammate throwing a significant lead". Publish Prep names the chapters and writes the description from these (chapter 20).
- **Why** it gave that rating, and **tags** (funny, fail, clutch, fight...).
- Whether it **makes sense on its own**, which is what a Short needs.

Clips are rated at the end of each analysis. For recordings analysed earlier, pick the recording and click **Rate with AI**. Only clips it hasn't seen are asked about, and the column fills in when the job finishes. (From the command line: `ai-editor rate 10`.)

**The rating doesn't choose your clips yet.** On your League stream of 2 October, the AI put a clip you liked above one you rejected only about half the time. The usual score did that about 80% of the time. Three still frames can't show a teamfight the way the sounds and your markers do. So the AI's rating is shown but not used to pick. **Settings → AI** shows, for each game, how often it agrees with your 👍 and 👎. If it starts beating the usual score for a game, turn up **How much the AI's rating counts**.

---

## 13. Style Profiles (teaching AI-Editor a look)

A Style Profile is a saved editing look, measured from videos whose editing you like: how fast the cuts are, how much silence is left in, the opening teaser, zooms, sound effects and captions. You can have as many as you like, such as "League Highlights" and "League Shorts".

**What a profile does, and doesn't.** It sets the *pace and the amounts*: how fast, how often, how strong, how captions look. It **never switches an effect or burned-in captions on**: they stay off by default, and you switch them on per video in Review or in Settings. A profile only decides how often and how strong they are when you do.

### 13.0 Using a profile

1. In the profile, tick the **game(s)** and the **kinds of video** it's for, and click **Save profile**.
2. In **Create video**, the **Style profile** box picks that profile by itself when the game and kind of video match. Change it there if you like, or choose **No profile (my Settings)**.
3. Make the plan. Review's summary starts with a **Style:** line saying what the profile changed, for example *"Style: League of legends, clips about 26 s, no teaser, when switched on: at most 0.5 zooms a minute (1.25x) and 0.1 sound effects a minute."*

The profile's values are copied into the plan when it's made. Changing the profile later doesn't change plans already made; to use the new values, make the plan again.

**What each slider changes:**

| Slider | Changes |
|---|---|
| Cuts per minute | How long **highlight** clips run (2.3 a minute: about 26 s each). Your marked moments keep their own length. Not Shorts (one clip) or Let's Plays (parts are split their own way). |
| Opening teaser | The highlight teaser's length; **0 = no teaser**. |
| Longest silence left in | **Let's Plays only**: the silence trim (never below 5 s). |
| Zooms / sound effects per minute | **At most** that many, on the biggest moments, when you've switched them on. 0 means none of that kind. |
| Zoom strength | How far zooms push in, when switched on. |
| Caption size / height | Burned-in captions, when switched on. |
| Caption words at once | Shorts' captions, when switched on. |

### 13.1 Creating a profile from reference videos

1. Go to the **Style Profiles** tab. Type a name under **New profile** and click **Create**.
2. Choose which **games** and which **videos** (Highlights, Shorts, Let's Plays) it's for.
3. Add **2–5 reference videos**:
   - **YouTube links**: paste them, one per line, and click **Add links**.
   - **A video file on this PC**: click **Add a video file...** and pick it.
4. Click **Analyse references**. It runs under **Jobs**: about **4–6 minutes per 10 minutes of video**. Long videos are measured over their first 30 minutes.
5. When it's done, the reference table shows what each video measured, and the sliders show the middle of them. The AI's notes are underneath.
6. Adjust anything you want (13.2) and click **Save profile**.

**Tip:** 2–3 videos from the *same* creator give a clearer style than mixing lots of creators. Pick videos like the ones you want to make: same kind of game, same kind of video (tall Shorts for a Shorts profile).

**Your videos and files:**

- A YouTube link is downloaded small (480p) into AI-Editor's working folder, measured, then **deleted**. Only the numbers and the AI's notes are kept. Downloading uses yt-dlp. If YouTube links stop working after YouTube changes something, updating it usually fixes it: in the AI-Editor folder, run `.venv\Scripts\python -m pip install -U yt-dlp`.
- A file on this PC is only **read**, never copied, changed or deleted. **Take off the list** removes it from the profile only.
- Downloading may conflict with YouTube's terms. If you'd rather not, save the video yourself and add it as a file.

**The AI's notes** (Gemma) come at the end: it looks at 8 frames of each video and lists the editing techniques it sees, such as "text pop-ups on kills" or "facecam in the bottom-left". They're for you to read; they don't change any video. They use the graphics card, so run Analyse when you're not playing. If a game has the card, the AI stops and the measurements are kept; **Measure them all again** later gets the notes.

### 13.2 Profile settings explained

Every measurement is an estimate, which is why there are sliders. Under each slider, **Your references** lists what each video measured, so you can spot an odd one out.

| Setting | What it measures and controls | How it's measured |
|---|---|---|
| **Cuts per minute** | How often the picture jumps to another moment | Picture changes, leaving out a game's own shop, scoreboard and camera jumps (the HUD carries straight on across those) |
| **Longest silence left in** | How long nobody talks before the editor cuts (seconds) | The long end of the gaps between talking |
| **Opening teaser** | How long the first shot runs before the first cut (seconds; 0 = none) | The first cut in the first 25 seconds |
| **Zooms per minute**, **Zoom strength** | How often it punches in, and how far (0.2 = 1.2 times). Only used when zooms are on | Each frame against the one before, blown up: a quick, exact match is an editor's zoom. A game's own camera zoom (a scope, League's mouse wheel) creeps in over seconds and isn't counted |
| **Sound effects per minute** | How often a sound effect plays. Only used when sound effects are on | Meme sounds only: whoosh, boing, air horn, ding, record scratch. Booms and hits can't be told apart from a game's own sounds or music |
| **Caption size** | How tall caption text is (% of the picture's height). Only used when captions are on | Text read off the screen: big, near the middle, and changing. A game's own text, menus and scoreboards are left out |
| **Caption height above the bottom** | Where captions sit (%) | The same |
| **Caption words on screen at once** | A few words at a time, or whole sentences | The same |

**Also measured** (shown under the sliders): how much of each video has talking, how long a shot usually lasts, which meme sounds were heard, and whether it's a tall video.

**Back to the measured values** puts the sliders back to what the references measured (or your own settings if nothing is measured yet). Click **Save profile** to keep them.

### 13.3 Editing, renaming, and deleting

- **Edit**: change the sliders, games or videos anytime and click **Save profile**.
- **Add or remove references**, then **Analyse references** again. Only new ones are measured, unless you tick **Measure them all again**.
- **Rename or delete**: under **Rename or delete**. Deleting removes the profile and its measurements; no video or file is touched.

---

## 14. Rules (your editing tips)

Rules are tips you write in normal English, like *"Keep League highlight clips under 20 seconds"*. Your local AI (Gemma) turns each one into a rule AI-Editor knows, and AI-Editor tells you in its own words exactly what it will do. Nothing is saved until you say so.

### 14.1 Adding a rule

1. Open the **Rules** tab.
2. Type your tip under **Your tip**, for example: *"No teaser in League highlights."*
3. Click **Understand it** (or press Enter). It takes a second or two; the first time a few seconds more, while the AI loads. It uses the graphics card, so don't do it mid-game.
4. AI-Editor says what it will do, for example: **AI-Editor will:** *League of Legends highlights: no opening teaser.* That sentence is written by AI-Editor from the rule itself, not by the AI, so it's exactly what will happen.
5. Check **For these games** and **For these videos** underneath. The AI fills them in from your tip; change them if it got them wrong. Empty means everywhere.
6. If it's right, click **Save**. If not, click **Try again** and say it differently, ideally with a number.

### 14.2 What a rule can change

| Kind of rule | You might write | What it changes |
|---|---|---|
| Clip length | "Keep League highlight clips under 20 seconds", "Shorts between 20 and 40 seconds" | How long each clip may be (highlights and Shorts) |
| Video length | "Highlights at least 12 minutes", "Dawnwalker parts about 40 minutes" | The length of a highlight video, or of each Let's Play part (the range around it moves too, 15.2) |
| Teaser | "No teaser in League highlights", "An 8 second teaser" | Whether a video opens with a teaser, and how long (highlights, Shorts) |
| Clip order | "Clips in the order they happened" | The order of a highlight video's clips (16.2) |
| Quality bar | "Only really good clips for Wardogs" | How good a clip must be to go into highlights. "Really good" became 0.90, only the very best: say a number ("quality bar 0.7") if that's too strict |
| Let's Play silences | "Cut silences longer than 10 seconds in Dawnwalker" | How long a silence may run before it's cut down |
| Caption look | "Bigger captions on Shorts", "2 words at a time" | Size, height and words at a time. Only when captions are on |
| Effect amounts | "At most 1 zoom a minute" | How many effects at most. Only when they're on |
| Your three tips (16.2, 19.2d, 19.2e) | "Ensure the action is always within the clip", "Make sure the video sound is never over my voice", "Suggest where an effect can work and which effect" | Their switches, so you can turn one off for one game: "Don't keep the game under my voice in League" |

**What a rule can't do:**
- **Speed anything up:** you chose never to (2C). AI-Editor says so and saves nothing.
- **Switch effects or captions on:** you tick those in Review, to be sure they went in right. Kept as a 📝 note.
- **Choose moments**, like "Always include pentakills", "Never use clips where I die" or "Add a zoom on pentakills": those are moment rules, coming in 2H-3. Kept as a 📝 note until then.
- **Anything AI-Editor can't see yet**, like boss fights or horse riding. Kept as a 📝 note.

### 14.3 Writing good rules

- **Use numbers where you can.** "Under 20 seconds" works; "short clips" is kept as a note, because AI-Editor won't make up a number you didn't give.
- **One idea per rule.** Split "no teaser and shorter clips" into two rules.
- **Say which game** if it's for one game only, and which kind of video if it's only for one.

On 19 Oct these all came out right: your three tips (every time, five tries each), "Keep League highlight clips under 20 seconds", "Dawnwalker parts about 40 minutes", "No teaser in League highlights", "Cut silences longer than 10 seconds in Dawnwalker", "Only use the really good clips for Wardogs", "Shorts between 20 and 40 seconds" and "Make the captions bigger on Shorts". "Speed up horse riding" was refused, and "Add a zoom on pentakills" kept as a note for 2H-3.

### 14.4 Which rule wins?

When instructions disagree, AI-Editor follows this order (top wins):

1. **Your rules.** Two rules that disagree (the same thing, for the same game and videos): the **newer** one wins, and the list says so: *⚠ r002 (newer) says otherwise, so that one wins.*
2. **The style profile** chosen in Create video (chapter 13).
3. **Settings.**

### 14.5 When rules are used

- **By themselves**, on every new video they match: its game and its kind of video. Review's summary lists them on a **Rules:** line, like *Rules: r001 League of Legends highlights: clips 20 seconds long at most.*
- **A plan keeps a copy** of the rules it was made with. Changing, switching off or deleting a rule later never changes a plan you've already reviewed; to use the new rules, make the plan again.

### 14.6 Your rules: on, off and delete

**Your rules** lists every rule and note, newest first: its number (r001, r002...), **✅ On** or **⬜ Off**, what it does, and your own words.

- **On and off:** pick a rule under **Rule**; the **On** tick box shows whether it's on. Untick it to make new videos without the rule (it stays in the list), tick it to use it again.
- **Delete:** pick it, click **Delete**, then **Yes, delete it**. Only you can delete a rule; AI-Editor never removes one by itself.
- **Notes** (📝) don't change the edit. They're kept so nothing you wrote is lost, ready for when AI-Editor can act on them.

---

## 15. Creating a Let's Play (parts)

### 15.1 Quick start

1. Go to **Create video**, and choose **Let's Play**.
2. Pick the **Episode recording**. Let's Play games are listed first.
3. Click **Make the plan**. It takes seconds and shows under **Jobs**, then opens in **Review**.
4. Review lists the **parts**: how long each is, and where it is in the recording. **Click a part** to watch how it starts. **Quick preview of the selected part** makes a watchable version of the whole part, cuts included, in seconds.
5. Check the **Episode number** (read from the recording's name, e.g. "EP 1"). Choose **All parts** or one part. Then **Render the finished video** (chapter 19).

To move where parts end, use the Part Planner (15.4).

### 15.1a From the command line (until the app window arrives)

```powershell
ai-editor letsplay 1 --open
```

This trims the episode, recording **1** here, and saves it as a draft Let's Play plan. It removes only what a viewer would skip:

| What goes | When |
|---|---|
| **Loading screens** | A black, completely still screen for 2 seconds or more. Night-time play is dark too, but the camera moves, so it stays. |
| **Menus, the map, the inventory** | A still picture for 5 seconds or more, **unless you're talking over it**. |
| **Long silences** | Nobody talking and nothing happening for over **20 seconds**, cut down to 3 seconds either side, and only during play (see below). |
| **Starting / BRB / ending screens** | When the Stream Companion was running, anything shown on a non-game OBS scene. |

What **never** goes: anyone talking (you, or the game's characters), a fight (swords included), a moment that scored well, and **cutscenes**. The tool knows a cutscene because the game's HUD (health bar, compass, quest list) disappears. It learns where your HUD is from each recording by itself. Nothing is ever sped up, and no cut lands mid-word.

It prints how many minutes each kind of cut removed, and a list of every cut with its time in the recording. It also makes a **cuts reel** in `plan-previews`: every cut with 4 seconds either side, so you see exactly how each jump will look. Turn subtitles on in VLC to see which cut is which and why. `--open` opens the folder.

Then it **splits the trimmed episode into parts** of about 30 minutes (the rules are in chapter 15.3) and prints a table: each part's length, where it starts and ends in your recording, and what it ends on. A loading screen is the best place to end; a pause in talking is fine. **(hook)** means it ends right after a strong moment. If a part had to end without a clean break, it's marked **no clean break: check it**.

It also makes a **splits reel**: the last 20 seconds of each part and the first 10 of the next, so you can judge every split in a couple of minutes. To watch whole parts, add `--parts`: each part gets its own preview, which takes a few minutes. `--no-reel` and `--no-splits` skip the reels.

Happy with the parts? Render them as finished videos with `ai-editor render <plan>` (chapter 19.2a).

**Story missions (The Blood of Dawnwalker).** The first time you make an episode's plan, AI-Editor reads the game's **quest tracker** (top right: the time of day, then the quest you're following, such as "Where Loyalty Lies") every 15 seconds, from the preview copy. That takes about 4-5 minutes for a 2-hour episode, shows under Jobs as **Reading the quest tracker**, and is kept, so it never runs twice for the same episode (it works even after you've deleted the recording). It uses a small text reader that runs offline on the processor, leaving the graphics card alone.

With that, a part is **never split in the middle of a quest** if it can be helped: it ends just before the quest begins, or runs on to its end (up to 45 minutes, 60 at most). Every quest the tracker shows counts; the "Rescue your family" line above it doesn't. Just after a quest ends, and as the time of day changes (Noon → Afternoon), are good places to end a part. A quest longer than an hour still has to be split: that part is flagged, with the quest's name, for you to check. The plan's notes list the quests it found.

### 15.2 Length settings explained

| Setting | Default | What it does |
|---|---|---|
| **Mode** | **Split** | *Split* makes several parts from one session. *Condense* makes one shorter video. |
| **Target part length** | **30 min** | The ideal length for each part. |
| **Normal range** | **25–35 min** | Parts inside this range count as "on target." |
| **Story extension, preferred max** | **45 min** | How long a part may run to avoid splitting a story mission. |
| **Story extension, hard max** | **60 min** | A part will never go past this. |
| **Trim level** | **Light** | *Light* keeps more exploration and chat. *Standard* is balanced. *Tight* removes more. |
| **Silence** | **20 s** | Nobody talking and nothing happening for longer than this is cut down, leaving 3 seconds either side. |
| **Menus** | **5 s** | A still picture (menu, map, inventory) for this long is cut, unless you're talking over it. |
| **Leftover minimum** | **15 min** | A last part shorter than this is a leftover: it joins the part before it. |
| **Recap at start** | Off | Adds a "previously on" recap (max 15 seconds). |
| **Hook endings** | On | Prefers ending parts right after an exciting moment. |
| **Speed-up indicator** | On | Shows a small fast-forward icon during sped-up travel. |

### 15.3 How AI-Editor decides where to split

AI-Editor follows these rules, in order:

1. **Never** splits during a cutscene, dialogue, choice, or fight.
2. **Avoids** splitting in the middle of a quest (Dawnwalker: any quest its tracker shows, read from the screen). Exploration between quests can be split anywhere sensible.
3. Looks for the best break between **25 and 35 minutes**: a quest completion, day/night change, the end of a fight, or a loading screen.
4. If a story mission is still going, the part is **extended** until the mission ends, ideally by **45 minutes**.
5. If the mission still isn't over at **60 minutes**, it splits at the gentlest point available (between scenes or at a fade), adds a "To be continued" card, and flags it for you to check.
6. After a longer part, the remaining parts **go back to about 30 minutes**.
7. When two break points are equally good, it picks the one **right after an exciting moment**, so viewers want to watch the next part.
8. **No leftovers:** a last part under **15 minutes** joins the part before it, so every part from a recording stays in that recording's episode (nothing is carried to the next session: each one opens on your intro). A short last part stays only if joining it would make a part over **60 minutes** and no split can move to make room; the plan's notes then say so.

**How many parts will I get?** Usually about **four** from a 2-hour session. Sometimes three or five, because loading screens and menus are removed and story missions vary. AI-Editor never adds boring footage just to make four parts. If you're regularly getting three, try **Trim level: Light** (default) or record a little longer.

### 15.4 The Part Planner

In **Review**, a Let's Play's parts bar is also the Part Planner: one block per part, sized by its length, with a handle at each split.

- **Drag a split's handle** left or right to move where a part ends. It snaps to the nearest **safe break** as you drag (a loading screen, a menu, a pause in talking, where a quest ends), never mid-word, mid-talk or mid-cutscene, and shows where it will land.
- **Double-click the bar** to add a split there (at the nearest safe break).
- **×** above a split joins the two parts either side of it.
- A split drawn **red** ends a part in the middle of a quest; the **Ends on** column under the bar says which.
- Times under the handles are in the recording, the same as the table.
- A part is never longer than 60 minutes or shorter than 2: a move that would break that is refused, and the message says why.
- If a change leaves the last part under 15 minutes, it's still made, and the message points it out (*"Part 5 is only 0:09:00: × joins it to Part 4."*). It's your call.
- **↶ Undo** takes back any of these, like every change in Review. Make a quick preview of a part to watch it as it now is.

### 15.5 Numbering and series

- Go to **Series** to manage your Dawnwalker playthrough.
- Part numbers continue across sessions automatically (Part 1, 2, 3, ...).
- To fix numbering, click **Series → Edit numbering**.

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

1. Go to **Create video**, and choose **Highlights**.
2. **Game:** leave **All my streams** for stream highlights of every game you played (Let's Plays stay out), or pick one game.
3. **Only these streams** (optional): leave it empty and AI-Editor uses the oldest streams' unused clips first, then the next stream's. Or pick the streams yourself.
4. **Length in minutes:** 10 by default. That's the **least** it will be: it never comes out shorter while there are good clips left, and it may run a little over. Every moment you marked with the Stream Companion and every clip you gave a 👍 always goes in, so lots of them make a longer video.

When the Stream Companion was running, no clip runs into your "BRB", "Starting" or "Ending Screen" scenes: each one stops half a second before you switched, and a moment during "BRB" isn't used.
5. Check the **Style profile** box: a profile made for this game and highlights is picked by itself (chapter 13.0). Or choose **No profile (my Settings)**.
6. Click **Make the plan**. It shows under **Jobs**, then opens in **Review** (chapter 18).

### 16.1a From the command line (until the app window arrives)

```powershell
ai-editor highlights --open
```

This makes **stream highlights**: the best **unused** clips from all your analysed streams, whatever games you played, so a stream where you switched from Wardogs to Tarkov gives a mixed video. Recordings of your **Let's Play games** are left out: those become Let's Play episodes instead (chapter 15). The Let's Play games are listed in `config/settings.yaml` under `lets_play: games:`, and The Blood of Dawnwalker is there already.

For **one game only**, add `--game`:

```powershell
ai-editor highlights --game Wardogs --open
```

That takes clips of that game only, including the Wardogs part of a stream where you also played something else (the Stream Companion knows which part was which: 8.1b).

Either way, it builds a highlight video plan. It also saves a quick, low-resolution **preview** to watch (in your Outputs folder under `plan-previews`), and `--open` opens that folder. To use only certain recordings instead: `--from 3` or `--from 3,6,7`. To change the length: `--minutes 8`.

What it does:

1. **Only good clips.** Anything below the quality bar (**Minimum clip score**) is left out, even if the video comes up short. Clips you pinned or marked with the Stream Companion always go in.
2. **Several streams when needed.** If one stream doesn't have enough good moments, it carries on with the next, oldest first: for example 4 minutes from Monday's stream and 6 from Tuesday's.
3. **Trimmed to the moment.** Each clip starts 15 seconds before its moment and is at most 50 seconds long, still never cutting anyone off mid-word or opening mid-sentence. When a moment is too long, a joke keeps its build-up, but a **fight keeps its end**, where the kill is.
4. **In the order it happened.** A 5–15 second teaser first, then the clips as they happened on stream (oldest stream first), and the teased moment in full at the end, the way you laid out your own League video. The teaser is, in order: a moment you **marked with Numpad +** during the stream; otherwise the moment where **you react most** (laughing, getting loud, shouting). Sound can't tell what's *funny*, only how loud you are, so to choose it yourself, add `--teaser` with the clip's **#** from the list the last run showed: `ai-editor highlights --game Wardogs --teaser 5`. The teased clip also closes the video. The teaser ends where you stop talking.

   **Picking the exact moment.** After watching a video, name the moment you want as the teaser by its time in that video: `ai-editor highlights --game "League of Legends" --teaser-at 6:36-6:42`. The teaser is exactly that, with a second either side so it doesn't start or stop abruptly (never mid-word), and the whole clip it's from closes the video. Giving only where it starts (`--teaser-at 6:36`) ends it the usual way, at a pause. Use the same `--game` as the video you watched. The times must be inside one clip.

If there isn't enough good material, it says so and makes the shorter video rather than padding it. Analyse another stream of the game and run it again.

The plan starts as a **draft**: run it as often as you like. When you're happy:

```powershell
ai-editor approve highlights_wardogs_2026-09-26_1
```

Approving marks its clips as used, so the next highlight video carries on with the clips that are left. `ai-editor plans` lists every plan and whether it's approved.

The preview is only for judging the choices. The finished video, in full quality with captions, is made in the rendering step (chapter 19).

### 16.2 Highlight settings explained

| Setting | Default | What it does |
|---|---|---|
| **Target length** | 10 min | The least the video will be: it can run over, never under while good clips are left. Never padded with weak clips: if there aren't enough, it says so. |
| **Games** | All in selected recordings | Mix games or keep one game only. |
| **Minimum clip score** | 0.55 | The quality bar: clips below it aren't picked, even if the video comes up short. Clips you 👍 and moments you marked always go in, whatever their score. |
| **Fill order** | Oldest first | When one stream runs out of good clips: *Oldest first* uses up the earliest stream before moving to the next; *Best first* takes the highest-scoring clips from any stream. |
| **Lead-in / longest clip** | 15 s / 50 s | How much of the build-up each clip keeps, and the most any one clip can run, so the video keeps its pace. |
| **Start clips before a fight that's already going** | On | When a fight is already going where a clip would start (the game's sound among its loudest, gunfire, or League champions dying), the clip starts a second before the fight began instead, as long as it stays within the longest clip. When it can't, Review's clip list marks it **⚠ starts mid-fight (8 s already gone)**: click it and use **Adjust the cut** (18.3) if it needs it. Shorts too. Clips whose cut you adjusted are left as they are. **Settings → Highlights**. |
| **Hook** | On | Opens with a 5–15 second teaser of the best moment. |
| **Ordering** | Timeline | *Timeline* (as it happened, the teaser's clip saved for the end; with no teaser, simply as it happened), *Chronological* (strictly as it happened), *Balanced* (mixes intense and calmer clips), or *Best last* (builds to the strongest). |
| **Allow reused clips** | Off | Whether clips already used in other highlight videos can appear. |
| **Always include pinned clips** | On | Your pinned clips are always used. |
| **Always include markers** | On | Moments you marked with the hotkey always go in. |

### 16.3 Tips

- Mark moments during your stream. It's the single best way to get great highlights.
- If the video feels repetitive, increase **Minimum clip score** or choose **Balanced** ordering (`highlights.ordering` in `settings.yaml`).
- Combine a week of streams for a "Best of the week" video.

---

## 17. Creating Shorts and TikToks

Vertical clips are built entirely inside AI-Editor and rendered here. The finished file is 1080×1920 at 60 frames a second, the right size for YouTube Shorts, TikTok and Instagram Reels, so the same file works on all of them.

### 17.1 Quick start

1. Analyse the recording, and ideally **Rate with AI** (12.3): the AI's "makes sense on its own" check is what picks good Shorts.
2. **Create video → Shorts**, pick the stream or recording, and click **Make the plan**. A couple of seconds later Jobs lists up to five suggestions, and why each was picked:
   - every moment you marked as Short-worthy while live (**Numpad −**), always, even past five;
   - then League's big moments: your multikills, your team's aces, and steals (8.3);
   - then clips you gave a 👍 that make sense on their own;
   - then the AI's best clips that make sense on their own.

   Never a 👎 moment, a "BRB" screen, or a moment that's already a Short. Being in a highlight video doesn't count: Shorts are how viewers find your long videos.
3. In **Review**, each suggestion is its own plan (**Video plan** → *Short: ...*). If it starts too late or ends too early, click its row and **adjust the cut** (18.3). Choose **How the game fills the tall frame**, then **Quick preview** to watch it as it will look, in a few seconds. In the preview, the faint red areas are what the apps' buttons and text cover; the red line marks what stays free (17.3). The shading isn't in the finished Short. Each layout's preview is kept: switch back and the one you made is there, and it's there again next time you open the Short.
4. **Render the finished video**: about 15 seconds. It's saved in `output\shorts`. Rendering marks the moment as used, so the next suggestions are different moments.
5. **Publish** writes a title, a line or two and hashtags (20). Once the long video the moment is in is on YouTube, paste its link in *that* video's Publish section (**This video's YouTube link**): every Short from it then says **Full video:** with the link.

A Short from a story game (Dawnwalker) is flagged: check it doesn't give away the plot before you upload it.

From the command line: `ai-editor shorts 7` lists the suggestions; `ai-editor shorts 7 --render 1,3` renders them.

### 17.2 What a Short looks like

**Length:** 15–60 seconds. Each one opens about 25 seconds before its moment and runs 3 seconds past it so your reaction finishes. (It used to open 8 seconds before, but the moment AI-Editor finds is often you reacting, which comes after the play: on 10 Oct five Shorts started after what you were reacting to.) A Short from your **Numpad −** mark runs from about 45 seconds before your press to 5 seconds after it, since the good bit comes before you press. It never starts or ends mid-word. If a cut is still wrong, adjust it in Review (18.3).

**Layout.** You don't have a facecam yet, so the game fills the frame in one of two ways:

| Layout | Looks like | Default for |
|---|---|---|
| **Zoomed centre** (`crop`) | The middle of the screen, zoomed in, filling 75% of the phone's height with a thin band of blur above and below, so health bars and the ability bar aren't cut off at the sides. | League of Legends, Escape from Tarkov, Wardogs: the champion or crosshair is in the middle |
| **Whole picture** (`fit`) | The full game, sharp across the middle, a blurred copy of it above and below. Nothing is cut off, but it's smaller. | The Blood of Dawnwalker: wide story scenes |

How far it's zoomed is `shorts.crop_fill` (0.75; 1 fills the whole height, lower shows more of the sides), or per game in `shorts.crop_fills` (League is 0.65: its fights spread wide). To use the other layout for a single Short: `ai-editor shorts 7 --render 2 --layout fit`. To change a game's default, edit `shorts.layouts` in `settings.yaml`.

**When you get a facecam:** mark where it is in your OBS scene once, under `shorts.facecam` (for example `League of Legends: { x: 0.0, y: 0.7, w: 0.2, h: 0.3 }`, as shares of the picture). From then on that game's Shorts put your facecam across the top third and the game below it. (In the window, you'll draw the box instead.)

**Captions:** off unless you tick **Burn in captions** for the Short in Review, like every video. When on: big, bold, 3 words at a time, the word you're saying lit up in yellow. Only your words. Recordings with just one mixed sound track get none for Let's Play games, because the characters' lines can't be told apart from yours (19.2c). Change them with `captions.shorts_size`, `shorts_words` and `shorts_highlight`.

### 17.3 Safe zones (important for TikTok)

Each app covers parts of the screen with its own buttons, your username and the caption text. AI-Editor keeps your captions clear of them.

- **Universal** (the default, `shorts.platform`) avoids the covered areas of YouTube Shorts, TikTok and Reels at once: the bottom 26% and the right-hand 20%. One file, uploaded everywhere.
- The margins are in `shorts.safe_zones`, because the apps change their layouts now and then.

**Not built yet:** separate versions per platform.

### 17.4 Adjusting a Short

On the Review screen for Shorts you can:

- Drag the **gameplay crop box** to reposition it.
- Drag the **facecam box** to resize or move it.
- Edit **caption text** if a word was misheard.
- Change the **start and end** of the clip.

**Built so far:** switching the layout (17.1). **Not built yet:** moving the crop or facecam box by dragging, editing caption words, and changing the start and end.

### 17.5 Using Shorts to grow your channel

- Make Shorts from the same session as your Let's Play parts or highlight video.
- Publish Prep adds a line in the Short's description pointing to the full video. Paste the link once the full video is live.
- Tip: Shorts from funny deaths and big reactions often work best for new viewers, while story moments are best saved for the full episodes.

---

## 18. The Review screen

Every video goes through Review before rendering. Nothing is final until you render it.

### 18.1 Layout

- **Video plan:** every plan you've made, newest first, with the stream it's from ("League of Legends highlights · 8 Oct stream · Highlights, 15.8 min, draft"). It opens on the newest one. Making a plan again from the **same** stream(s) replaces its old draft (never a rendered one); a plan from another stream is kept.
- **Delete this plan** (beside Video plan): takes the plan on show out of the list, after you confirm. Only the plan goes (and its Undo history): a finished video stays in your output folder, its clips stay marked as used, and your clips, ratings and what AI-Editor learns from them all stay. AI-Editor never deletes a plan by itself, and deleting quick previews from the folder doesn't remove plans: use this.
- **↶ Undo / ↷ Redo:** see 18.4.
- **The length bar:** how long the video is against its target, one block per clip, as wide as the clip is long. The teaser is amber, a clip with a slow-motion replay is purple (and marked ⟲), the dashed line is your target. Highlights: about 10 minutes, never below; the note turns amber when the video is under it. A Short: 60 seconds at most. A Let's Play: one block per part, aiming for 25-35 minutes each. Hover a block to see what it is; click it to pick that clip (or part), the same as clicking its row.
- **The list** (highlights and Shorts): every piece in order. The teaser first, then each clip, with where it lands in the video, which stream it's from, where it starts in that stream, its length, score, and why it's in.
- **The parts** (Let's Plays): see 15.1.
- **Player** (right): click a row (or a block on the bar) to watch that piece, from the preview copy.
- **Quick preview of the whole video:** a low-resolution version of the whole thing, made in seconds, that plays in the same player.

### 18.2 Things you can do (highlights)

**Drag a clip to move it:** grab its row (the ⠿ on the left, or anywhere on the row) and drop it where you want it; a line shows where it will land. The teaser always opens the video, so it can't be dragged.

Or click a row first, then:

- **Use as teaser:** the video opens with a few seconds of this clip's best moment, and ends on the clip in full, paying the teaser off.
- **Or the teaser from an exact moment:** type the time in the quick preview or render, e.g. `6:36-6:42`, or just where it starts, `6:36`, and click **Use this moment**. AI-Editor adds a second either side and never starts or stops mid-word.
- **Remove:** takes the clip out. **The next best clip fills the gap**, in the same place, so the video stays at least its target length (16.1). If the clip was the teaser's moment, the teaser and the ending move to your next best. Removed clips never come back into this video.
- **Move up / Move down:** changes the order one place, if you'd rather not drag. The teaser always stays first.
- **Move the clicked clip to #:** type a number from the list's **#** column and click **Move**: the clip jumps straight there.
- **Sort by time:** puts everything back in the order it happened: the teaser first, the clips as they happened, the teaser's own clip saved for the end.
- **Taking the teaser out** (Remove on the teaser) also moves its clip, saved for the end, back to where it happened: with no teaser, nothing sets that ending up.
- **Add a clip that isn't in the video:** lists the clips from the same streams that aren't in it, your 👍 clips first, then the best (including ones under the quality bar: you're the judge here). Pick one to watch it in the player, then **Add to video**. It goes in where it happened in the stream; move it from there. A clip that fills the gap after a **Remove** slots in by time the same way.

Changes are saved straight away. You can close AI-Editor and carry on later. Everything you change is kept, so AI-Editor can learn from it (chapter 22).

### 18.3 Adjust the cut (highlights and Shorts)

When AI-Editor found the right moment but cut it too late or too early, fix it yourself. Click the clip's row, and **Adjust clip** appears under the player:

- **Start** and **End**: where the clip starts and ends in the recording, to a tenth of a second.
- **◀ 5 s**, **◀ 1 s**, **1 s ▶**, **5 s ▶**: move that edge earlier or later. The player shows the result straight away: from the new start, or the last few seconds up to the new end.
- **Start here** / **End here**: play the clip, pause the player where you want the edge, and press it.
- Or type a time in **Start** or **End** (`1:34:52`, or `34:52.5`) and press Enter.
- **Watch 30 s either side**: plays from half a minute before the clip to half a minute after, so you can see what was cut off. You can move the start back past where AI-Editor's clip began, as far as you like.
- **Play the new cut**, then **Save the new cut**.

Saving moves each edge at most half a second, only so it never cuts you off mid-word, and shows the times it used. A Short can be at most 60 seconds. Captions, effects and chapters follow the new cut by themselves; make a quick preview to watch it, then render.

**AI-Editor remembers your cut.** The clip in the Clips library takes your start and end, so the next highlight video or Short with that moment uses your version, and analysing the recording again never replaces it.

### 18.4 Undo and Redo

**↶ Undo** takes back your last change to this video; press it again to go further back. **↷ Redo** does again what you undid. The button says what it would undo or redo, e.g. "↶ Undo removing clip 4".

- It covers every change in Review: removing, moving and dragging, the teaser, adding a clip, adjusting a cut, the effect switches and each effect's ticks, between clips, music, a Short's layout, and fixing, hiding or putting back a caption line (18.5).
- Each video has its own history, and it's kept when you close AI-Editor.
- Undoing a cut you adjusted puts the clip in the Clips library back as it was, too.
- **A misclick teaches nothing:** what AI-Editor keeps for learning (chapter 22) marks an undone change as undone.
- Making a new change after undoing ends Redo for what you undid.
- The upload text (titles, description, tags) is never undone: change that by hand, and **Keep my changes**.
- Making a plan again in Create video starts it with a fresh history.

### 18.5 Fixing captions (highlights and Shorts)

Speech recognition mishears names and slang ("zonya" for Zhonya's). Click a clip's row, and **Captions for clip N** appears under the player, below Adjust the cut:

- **Caption lines:** the clip's captions as they show in the video, each with where it starts in the clip. ✎ marks a line you've fixed, ⊘ one you've hidden. Click a line to hear it (the player plays just that line) and to fix it.
- **This line:** change the words, then **Save line** (or press Enter). Each word keeps its own time, so the caption stays in sync with your voice; type more or fewer words and they're shared over the line's time.
- **Hide this line:** it's never shown as a caption, but its words stay in the transcript ("You said", what the AI writes). **Show this line** brings it back.
- **Put back the original:** the line as it was first heard, shown again.
- **Play this line:** hear it again.

**A fix goes everywhere** that moment is used: every video and Short with it, the **You said** column in Clips, and what the AI writes about it. Analysing the stream again keeps your fixes and hidden lines. **Undo** takes back a fix, a hide or a put-back like any other change in Review.

**Remembering a fix.** When you change one word to another, AI-Editor asks: *"Always write zonya as Zhonya's? It's heard 3 more times in 2 streams."* **Yes, everywhere** fixes it in every stream now, and in new streams as they're analysed. Check the count before saying yes: a common word ("not") can be in hundreds of places. **Settings → Captions and sound** lists the fixes you've remembered; **Forget this fix** puts every word it changed back as it was heard. (Undo doesn't take back a remembered fix: forget it in Settings.)

Captions are only in a video when **Burn in captions** is ticked (off by default); tick it and make a quick preview to see your fixes.

---

## 19. Rendering and exporting

### 19.1 Preview render

In Review, click **Quick preview of the whole video** (or **of the selected part** for a Let's Play). It's made from the preview copies in seconds, and plays in Review's player. Use it to check the order and pacing before the full render.

Quick previews are kept. Opening a plan in Review shows its last one, ready to play (and, for a Let's Play, choosing a part under **Parts** shows that part's). If you've changed the plan since, it says so: make a new one to see the changes.

### 19.2 Final render

1. In Review, tick **Burn in captions** if you want your words on screen (chapter 19.2c). It's off by default.
2. For a Let's Play, check the **Episode number**, and choose **All parts** or one.
3. Click **Render the finished video**. Progress shows under **Jobs**.
4. When it's finished, click **Open the finished video**. Finished files are in your output folder, under `videos`: a highlight video by its plan's name, a Let's Play part as "Game - EP 1 - Part 2".

Rendering marks the plan's clips as **used**, so the next highlight video carries on with fresh ones. Remove a clip and render again, and that clip is free again.

Expected times: about 3½ minutes for a 12-minute highlight, about 7 minutes for a 30-minute part. The sound is balanced for YouTube.

**Not built yet in the window:** choosing another preset (1080p30, vertical). It's set in `settings.yaml` (`render.preset`).

### 19.2a From the command line (until the app window arrives)

1. See your plans, numbered newest first:

   ```
   ai-editor plans
   ```

2. Render one by its number (or its full name):

   ```
   ai-editor render 2
   ```

   With no number, it renders your newest highlight video. Add `--open` to open the folder when it's done.

3. The video is saved in your Output folder, under `videos`, named after the plan (for example `highlights_league-of-legends_2026-09-27_1.mp4`). It only appears there once it's complete. A render you stop part-way leaves nothing half-made behind.

What the render does:

- **Full quality from your original recording**, not the preview copy: 1920×1080 at 60 fps, encoded on your graphics card. The picture and sound are exact to the frame at every join.
- **Clean joins.** The sound fades over a few thousandths of a second at every cut, too short to hear as a dip but enough to stop a click.
- **YouTube loudness, without squashing.** The whole video is turned up or down in one go toward about −14 LUFS (YouTube's level), so a quiet moment stays quieter than a loud one, the way it was. Only the loudest peaks are held down, by 3 dB at most, which you can't hear. A recording made very quiet (EP 1 was −25 LUFS) is raised only as far as that allows, so it ends up a little under YouTube's level, but never distorted. Turn it up in your player if it's too quiet.
- **Never blasting.** A video is never turned up past where your normal talking would be at YouTube's level (on your League streams, about 10 dB). A Short with no talking in it would otherwise have its music and game raised to where your voice usually is: Short_09 (10 Oct) was raised 31 dB and its music blasted, next to 07 and 08 at about 9. Now it plays its music and game as loud as your other videos of that stream do; it's quieter overall, because there's no voice in it. The render says so when this happens.
- **Rebuilt from your separate tracks** when the recording has them (chapter 7.3): your mic, the game and Discord, each handled on its own, with **the music from your stream** added back underneath (19.2e). A recording without real separate tracks (a Twitch VOD, or an OBS recording from before your tracks were set up) uses the mixed track, exactly as the stream sounded, music and all. The render says which it used.
- **Marker beeps are taken out.** On the 26 Sep stream the Companion's click reached your microphone. Each click is found by its sound, only near a marker you pressed, and that one pitch is filtered out for half a second, leaving your voice and the game around it untouched. The click is off now (chapter 24), so new recordings don't have any.

A 10-minute highlight takes about 3 minutes.

**Let's Play episodes** render every part as its own video, in one go:

```
ai-editor render 1
```

- Each part is named ready to upload: `The Blood of Dawnwalker - EP 1 - Part 1.mp4`, `... - Part 2.mp4`, and so on.
- `--part 2` renders just that part, for example after a change.
- The episode number comes from the recording's name ("... EP 1"). If the name doesn't have one, add `--episode 2`.
- **Title card (off).** A part can open with its name, e.g. "Ep 1 – Part 2", in large bold letters in the middle of the picture, fading in and out over the first 4 seconds. It's off because the YouTube title already says it. To turn it on, set `title_card: "Ep {episode} – Part {part}"` under `lets_play` in Settings (`title_card_sec` sets how long).
- A two-hour episode takes about half an hour to render, all parts together.

### 19.2b Vertical clips: render here, not in Resolve

Vertical clips are composed inside AI-Editor: the crop, the stacked facecam, and the captions are all part of the plan. Those layout effects don't transfer reliably into other editors, so:

- **Recommended:** render Shorts and TikToks directly in AI-Editor. They come out as finished files, ready to upload.
- If you do export a vertical project, AI-Editor automatically pre-renders the vertical segments onto a 1080×1920 timeline, so Resolve or Kdenlive shows them exactly as designed. You can add extra polish there, but the layout is already baked in.

### 19.2c Captions (your words on screen)

Captions are **off** unless you ask for them. For one video:

```
ai-editor render 2 --captions
```

To have them on every time, set `captions: highlights: true` (or `lets_play: true`) in Settings (chapter 24). `--no-captions` turns them off for one video.

A captioned video is saved as `<plan> captions.mp4`, next to the plain one. Making one never replaces the other, so you can keep both and choose.

How they look: bold white letters with a black edge, a sentence or two at a time, centred near the bottom. The height is set per kind of video, to clear what the game draws there:

- **Highlights:** 12% up from the bottom, above League's ability bar.
- **Let's Plays:** 22% up, above the game's own subtitles (Dawnwalker's sit 9–15% up), which captions never cover.

What's captioned:

- **Only your words**, from your mic track. The words are exactly as transcribed, including the spelling fixes (chapter 24). Nothing is added or reworded, and swearing is shown as you said it.
- **Let's Plays need your mic on its own track.** In a recording with only a mixed track, the game characters' lines are in the transcript too: EP 1 would have captioned Anca's "How about Petronius?" under the game's own subtitle. So a Let's Play recording without a separate mic track gets no captions, and the render says so. Your OBS is set up for separate tracks now (chapter 7.3), so new recordings are fine.
- **Highlights from older streams** (before 27 Sep, one mixed track) can include a friend's words from Discord, and the odd game voice. Telling voices apart comes in a later phase.

### 19.2d Effects on the big moments

AI-Editor can add a few effects to the biggest moments of your highlights and Shorts by itself. Nothing to place by hand.

**Off unless you tick them, for now.** In the first test their timing felt random, so they stay off by default until you've tried them with League's own events (8.3). Tick them per video in **Review** whenever you want them.

| What happens | Effect |
|---|---|
| A sudden jump in the game's sound (a teamfight breaking out, an explosion) | A **screen shake** and a **boom** |
| You, suddenly much louder than your normal talking | A **flash**, a **hit** and a **punch-in zoom** |
| Both at once | All three |

**Only on the moments you marked.** Each time you press a marker key (Numpad + or −) during a stream, that moment gets one effect: on the biggest moment in the 20 seconds before your press, since you press just after something happens. A really big moment wins first: the game's sound jumping by 10 dB or more, or you *talking* clearly louder than your normal talking (a bump at the mic never counts). At most 1.5 a minute in highlights (3 in Shorts).

**League's own moments** (when the Stream Companion logged the match, 8.3): your **multikills**, your team's **aces** and **steals** get a shake and a boom by themselves, exactly on the second League says they happened (and the flash too if you're shouting about it). A mark with a kill or objective of yours in its 20 seconds puts its effect exactly on that, the biggest one if there are several. A single kill on its own gets none, so a one-sided game doesn't shake all the way through. **Each effect** names them: "Clip 3 at 1:40: Baron steal: shake + boom".

**Lined up to the instant.** Each effect starts exactly when the sound does, to the hundredth of a second, from the recording's own sound tracks.

**What it looks and sounds like:**

- **Flash:** the picture brightens at once and fades back over a third of a second.
- **Screen shake:** the picture jolts about for under half a second, settling as it goes. Nothing is zoomed.
- **Punch-in zoom:** on your reactions only (the shake stays on the action): the picture pushes in quickly to 1.2 times its size towards the middle of the screen, holds a moment and eases back out, in under a second. The video doesn't get longer. How far it pushes in is `effects.zoom_strength` (0.2).
- **Sound effects:** as loud as the moment they're on (3 dB under it), and never far under the clip's loudest moment, so a boom on a quiet game moment is still heard.
- Captions stay still and clear on top: they never shake or flash.

**Switching them on and off:**

- **For one video:** in **Review**, under **Finish it**, tick or untick **Flash**, **Screen shake**, **Sound effects**, **Punch-in zoom** and **Slow-motion replay**. Make a quick preview to see and hear them; a kept preview says when the effects have changed since it was made.
- **Suggested, one moment at a time:** **Suggested effects on the big moments**, under **Finish it**, lists every big moment with the effects that suit it, like "Clip 3 at 1:42: Triple kill: shake + replay + boom" (the time is where it is in the video). Nothing is ticked until you tick it. Tick a moment and it gets exactly those effects; the rest get none. A moment already ticked keeps the effects it has: "(now: shake)" says when that's fewer than suggested. It stays as you set it even if you move or trim its clip.
  - Ticking **Flash**, **Screen shake** and the rest above it instead puts those kinds on every ticked moment: the same everywhere again.
  - The suggestions come from what AI-Editor knows about each moment: a jump in the game's sound suits a shake and a boom (and a replay when it's one of your biggest), you reacting suits a flash, a zoom and a hit.
  - To go back to the list as it was before 2H (only the moments with effects, all ticked, untick to leave one out), untick **Suggest effects in Review** in **Settings → Effects**.
- **For every new video:** **Settings → Effects**, per kind of video. All off for now; Let's Plays have none unless you tick some there.
- **How many:** **Settings → Effects**, big moments per minute.

**Your own sound effects.** Until you add some, AI-Editor uses its own starter boom and hit, made from scratch, so there's no copyright question; they're basic, and real recorded ones sound far better. A good free source made for exactly this: **YouTube Studio → Audio Library → Sound effects** (free to use in YouTube videos); Pixabay's sound effects are another. Not CapCut's: its sounds are licensed for use inside CapCut only. To use yours, click **Open my sound effects folder** in **Settings → Effects** and drop files (.wav, .mp3, .ogg or .flac) into its **boom** or **hit** folder, or anywhere in it with the word in the name (`boom_02.wav`). With several of a kind, each moment gets one, and the same video always gets the same ones. Use only sounds you're allowed to use on YouTube (chapter 27).

**Between clips.** Highlights cut straight from one clip to the next. To slide instead, pick **Slide** under **Between clips** in **Review** (for one video) or **Settings → Effects** (for every new one): like a sliding door, the next clip slides in over the last one from the right, easing in and settling, over 0.8 seconds, while the sound crossfades. Both clips play during the slide, so each one makes the video 0.8 seconds shorter (the chapters and the times in Review allow for it). A clip too short to lose 0.8 seconds at each end keeps hard cuts.

**Slow-motion replays.** After your biggest moments, the moment plays at normal speed first; then its last 3 seconds play again at half speed (6 seconds), and the clip carries on where it left off. "Biggest" means your multikills, your team's aces and steals, or, in games without League's events, a marked moment where the game's sound jumps hard.

- **What you hear:** the game's sound, slowed with its pitch kept natural, and no voices (yours and Discord's are left out, so nobody comes out slow and deep). The music from your stream carries on underneath at normal speed, as if nothing had paused, and picks up from there when the clip resumes: the song never jumps or repeats. Quick previews have the stream's sound as it was, so a preview's replay has the voices in it too, slowed; the finished video doesn't.
- **Where:** 1.5 seconds after the moment, so it lands and you start reacting first, moved to a gap between your words so you're never cut off. Never in a clip's last half second or inside a slide.
- **How many:** one per clip at most, and no more than one every 2 minutes of video; one in a Short. A Short never goes over 60 seconds for one: if it would, it's left out (and the render says so).
- **Each one makes the video 6 seconds longer.** The chapters, the times in Review and the **Each effect** list all allow for it ("Clip 5 at 2:48: shake + replay").

(Freeze frames were left out: your choice.)

### 19.2e The music from your stream

The DMCA-free music you play on stream goes in your finished videos, as viewers heard it: highlights, Shorts and Let's Plays.

- **Out of the way of talking.** While you or a Discord friend talks, the music is kept at least 15 dB under the voice, lowered only as much as that needs and only there (never more than 12 dB), easing down and back up. Your music usually sits about 17 dB under your voice already, so mostly it plays exactly as on stream. A blip at the mic with nothing said never dips it.
- **The game under your voice, too.** While *you* talk, the game's sound is kept at least 10 dB under your voice, the same way: only as far as needed, only there (never more than 12 dB), and straight back up after. A Discord friend talking doesn't lower it. On your League streams the game sits far under your voice (about 45 dB), so it's never lowered there; on Dawnwalker it is now and then, by about 4 dB, mostly over cutscenes and fights you talk through. It needs the game on its own track in OBS (7.3), so recordings with only one track keep it as recorded. Switch it off in **Settings → Captions and sound** (**Keep the game under my voice**).
- **Smooth at cuts.** Each clip of a highlight video comes from a different point in the song, so the music alone fades in and out over a third of a second at each cut, while your voice and the game still cut cleanly.
- **Where it comes from.** From track 5 when your recording has one (7.3). Older recordings: AI-Editor takes everything else out of the mixed track, which leaves just the music. Recordings with only one track keep it exactly as recorded.
- **Switching it off:** for one video, untick **Music from your stream** in **Review → Finish it**; for every video, **Settings → Captions and sound**.
- **Quick previews** have the stream's sound as it was (the preview copy has only the mixed track), so the lowering (of the music and the game) and the cut fades are in the finished video only.

Only use music you're allowed to use on YouTube: commercial songs usually get a video claimed (chapter 27).

### 19.3 Exporting to DaVinci Resolve (free)

The backup route, for the odd video you'd rather fine-tune by hand. Your finished videos come from **Render the finished video**; you never need Resolve for them.

1. In Review, click **Export to DaVinci Resolve**. A Let's Play saves one timeline per part: all of them, or the one chosen under **Parts**. The folder opens with the timeline selected.

   (From the command line: `ai-editor export 2`, using the plan's number from `ai-editor plans`.)

2. The files are saved in your Output folder, under `timelines`:
   - `<name>.fcpxml`: the timeline.
   - `<name>.srt`: your words as subtitles, if you want them.
3. In DaVinci Resolve, create or open a project.
4. Go to **File → Import → Timeline** and pick the `.fcpxml`.
5. If Resolve asks where the media is, point it at your recordings folder (`F:/AI-Editor/raw`).
6. For captions: **File → Import → Subtitle**, pick the `.srt`, and drag it onto the timeline's subtitle track.

What comes across:

- **Every clip in its place, frame-exact,** cut from your original recordings, not copies.
- **A marker on each highlight clip** saying why it's there ("Clip 3: laughter, loud").

What doesn't come across, because it happens while AI-Editor renders:

- The sound clean-up: music left out, marker beeps filtered, loudness. Resolve plays the recording's own tracks.
- Burned-in captions. The `.srt` stands in for them.

If Resolve can't open an `.mkv` recording, use a newer Resolve, or remux the recording to `.mp4` in OBS (**File → Remux Recordings**), which takes seconds and loses nothing.

### 19.4 Exporting to Kdenlive

Not built yet. Resolve's timeline format (19.3) was enough as a backup. Ask for it if you ever switch to Kdenlive.

---

## 20. Publish Prep

Everything to paste into YouTube when you upload: title ideas, a description with chapters, tags, and thumbnail frames. It's at the bottom of **Review**, under **Publish**. The local AI writes it (chapter 5.2), from what it said about each clip (12.3) and what you said. Nothing is uploaded for you.

1. Open the video's plan in **Review**. For a Let's Play, fill in the **Episode number** (it goes in the titles), and under **Parts** choose one part, or leave **All parts** to do every part.
2. Click **Write titles, description and chapters**. It shows under Jobs: about 20 seconds per video, thumbnails included. Not while you're gaming (5.2).
3. The text appears below. Pick a title idea and it goes in the **Title** box. Each box has a copy button (top right).
4. Change anything you like, then click **Keep my changes**.

It's also saved as a text file beside the finished video, with the same name (`... .txt`), whenever you write it, keep changes, or render. You can do it before or after rendering.

**Changed the video since?** If you remove, add or move clips after writing the text, Publish says **the chapter times may be off: write it again.**

### 20.1 Titles

3–5 ideas, plain and descriptive, the style you chose: *"Wardogs Highlights - Holding the Zone with Friends"*. No clickbait, capitals or emoji.

Let's Play titles keep your series pattern, and the AI writes only the end: *"The Blood of Dawnwalker - EP 1 Part 2: Caring for Mum"*. Change the pattern with `publish.lets_play_title` in `settings.yaml`. For Dawnwalker (and any game listed in `shorts.spoiler_check_games`) it's told not to give away twists or the ending. Always double-check anyway.

### 20.2 Description and tags

2–4 sentences in your own voice about what happens, then the chapters, then the lines you put in **Settings → Publish → Under every description** (your Twitch link and when you stream). 8–15 tags, the game's name first: paste them in YouTube Studio under **Show more → Tags**.

### 20.3 Chapters

Paste the description as it is and YouTube makes chapters from the times in it. The times come from the video plan, to the frame, so they match the finished video exactly.

- **Highlights:** one chapter per clip, named after what happens in it. The teaser is **Intro** (or, if it's under 10 seconds, part of the first chapter).
- **Let's Plays:** a chapter about every 5 minutes (`publish.chapter_every_min`), always where one kept piece meets the next.

YouTube's rules are followed automatically: the first chapter starts at `0:00`, every chapter lasts at least 10 seconds, and with fewer than three chapters none are listed (YouTube would ignore them).

### 20.4 Thumbnails

AI-Editor takes 12 full-size frames from the video's strongest moments (at least 20 seconds apart), the AI looks at each one, and the best 6 are kept, best first (`publish.thumbnails`). Blurry frames, menus, maps, loading screens and dark frames are marked down. They show in Review, and the PNG files are in `output\thumbnails\<the plan's name>`. Open one in a free tool such as GIMP, Photopea, or Canva's free plan to add text and your face.

### 20.5 Linking Shorts to full videos

Once a long video is uploaded, paste its YouTube link in its Publish section (**This video's YouTube link → Save the link**). The Publish text of every Short whose moment is in that video then includes **Full video:** and the link. A Short's Publish section says which video it's from, and whether its link is saved yet.

### 20.6 Release planning

Not built yet.

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
- Queue waiting, champion select, loading screens and the post-game lobby, when the Stream Companion logged the match (8.3).

**Tips**
- Always run **Stream Companion** during League. Without it there are no League events, and AI-Editor goes by sound, your markers and chat alone.
- No account setup or keys are needed for League data.
- Kills, multikills, aces and steals score high for highlights, and the big ones become Short suggestions and get effects (8.3).

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

Open the **Storage** tab. It shows:
- **Drives:** free space on each drive AI-Editor uses, and a warning if one drops below your level (100 GB to start with; change it in Settings).
- **What's using it:** your recordings, AI-Editor's working copies, finished videos, and quick previews.
- **Each recording:** the recording file itself, then what AI-Editor keeps for it:

| Column | What it is | Needed for |
|---|---|---|
| Sound tracks | Your mic, game and Discord, pulled out of the recording | Clean sound in finished videos (music left out, beeps removed) |
| Preview copy | The small 540p copy | Playing clips in the window, quick previews |
| Working files | What analysis left behind: prepared sound, AI-separated voices | Nothing, once a recording is analysed |
| Analysis data | Words, sounds, scenes | Everything: clips, scores, plans |

A **Leftover** row is a folder from a recording no longer in the library.

AI-Editor also warns you before importing if free space is low.

### 23.2 Freeing space

1. In **Storage**, pick the recordings under **Recordings to tidy** (or **Pick all**).
2. Click **Free working files**. It says how much it freed (about 1–2 GB per stream).

Nothing is lost: clips, ratings, plans, preview copies and sound tracks all stay. If you ever analyse that recording again, the working files are simply made again. It won't run while a job is running.

**AI-Editor never deletes your raw recordings.** Delete them yourself once you're sure you've uploaded everything you want.

**Not built yet:** freeing the sound tracks and preview copies too, and deleting quick previews.

### 23.3 Moving footage to another drive

If you move raw files, open the project and click **Relink media** to point AI-Editor to the new location.

### 23.4 Deleting a stream once its videos are made

Streams take a lot of space, so it's fine to delete a recording from your recordings folder once you've made its highlights and Shorts. **What AI-Editor learned from it stays**, because it lives in AI-Editor's own library, not in the video file: your 👍 and 👎, the clips you removed or moved, the cuts you adjusted, the transcript, every second's analysis and the League events.

After you delete it:

- The Library shows it as **Video deleted (kept for learning)**.
- Its clips can still be browsed, watched, rated and adjusted (that uses the smaller preview copy in the cache).
- New highlight videos leave it out, and say so ("Left out 3 recordings whose video was deleted"); it can't be picked for a Short or Let's Play (**(video deleted)** in the list). Nothing new can be rendered from it.
- Finished videos you already made are separate files in your output folder and aren't affected.

AI-Editor itself never deletes your recordings: only you do. An automatic test checks every place in AI-Editor that deletes anything (all of them are its own temporary and working files, and Storage clean-up only ever touches its cache), and fails if a new one appears until it's been checked.

---

## 24. Settings reference

The **Settings** tab has the ones you'll change most: your folders (each with an **Open** button), and the main options for highlights, captions, Let's Plays, the Stream Companion and Twitch. Click **Save settings**: they work straight away, and are saved on this PC only (`config/settings.local.yaml`, beside your OBS password). A value AI-Editor can't use is refused with the reason, and nothing is saved.

The **Publish** section has the lines under every description and the Let's Play title pattern (chapter 20). The **AI (on this PC)** section shows whether the local AI is ready, with **Download model**, and how often it agrees with you (12.3).

You can change the recordings and output folders there. The cache and models folders are set in `config/settings.yaml`, because moving them means moving their files too. Every other setting is in `config/settings.yaml` as well:

| Area | Setting | Default | What it does |
|---|---|---|---|
| Folders | Raw / Cache / Outputs / Assets / Models | Set in wizard | Where files go. |
| Performance | Run AI on | GPU | Leave on GPU. |
| Performance | Unload AI models between steps | On | Prevents running out of graphics memory. |
| Performance | Proxy resolution | 540p | Size of preview copies. |
| Performance | Proxy frame rate | 30 fps (10–60) | Smoothness of preview copies. Higher makes smoother previews but bigger, slower-to-make copies. Your finished videos always use the original frame rate, whatever this is set to. |
| Tools | FFmpeg folder | Empty (found automatically) | Only set this if the setup check can't find FFmpeg. Point it at the folder containing `ffmpeg.exe`. |
| Queue | Overnight start time | Off | Starts the queue automatically. |
| Companion | Mark moment hotkey | `numpad+` | Logs a moment. While the Companion runs, this key belongs to it and games won't see it, so pick one they don't use. Numpad keys, F13–F24 and combinations such as `ctrl+alt+m` all work; the numpad's Enter key can't (chapter 6, step 5). |
| Companion | Mark Short-worthy hotkey | `numpad-` | Logs a Short moment. |
| Companion | Confirmation sound | Off | A click when you mark. Off because a microphone can pick it up and send it to your stream, which happened on 26 Sep (chapter 8.2). |
| Companion | Start with Windows | Off | Launches Companion at startup. |
| Companion | League events (`league_events`) | On | Logs your kills, deaths, multikills, objectives and the result from League's official local game data during matches (chapter 8.3). |
| OBS | WebSocket port / password | 4455 / from OBS | OBS connection. Set the password with `ai-editor setup-obs` (chapter 7.4), which keeps it in `config/settings.local.yaml` on this PC only. |
| Analysis | Transcription model | `large-v3` | Which speech-recognition AI writes your transcripts. `large-v3` is the most accurate and still transcribes 2 hours in about 3 minutes on your PC. `large-v3-turbo` is several times faster but misses more unclear speech. Changing it re-transcribes recordings the next time you analyse them. |
| Analysis | Voice separation | Twitch VODs only (`vods`) | On a recording with one mixed audio track, splits the sound into voices and everything else (music, combat) before analysing it, so the game's music can't hide your speech or trick the speech recognition. `vods` does this for Twitch VODs only; `mixed` for any single-track recording; `off` never. Recordings with a separate microphone track never need it. Takes about 2 minutes per 2 hours. The separated sound is only used for analysis, never in your videos. |
| Analysis | Language | English (`en`) | The language you speak on stream. `auto` works it out from the first 30 seconds, which is a little slower and can guess wrong if the recording opens with music. |
| Analysis | Voice detector | Auto | Whether AI-Editor skips parts with no speech before transcribing. **Auto** uses it only on a separate microphone track, where it's reliable and stops the AI inventing words over silence. On a mixed track it's off, because there it misses speech under game music. **On** or **Off** force it either way. |
| Analysis | Silence threshold | −50 dB (−90 to −10) | Anything quieter than this counts as silence. Raise it (towards −40) if quiet background hum stops AI-Editor spotting dead air. Changing it takes effect the next time you run analyze, without redoing the slow steps. |
| Analysis | Sound listening window | 2 seconds (1–10) | How much audio is heard at once when listening for laughter, shouting and gunfire. Longer is steadier but can blur two quick moments together. |
| Scoring | Weights | Markers 4.0; laughter 2.5; screaming 1.2; chat 1.2; shouting 1.0; explosions 0.9; gunfire 0.8; loudness 0.5; talking 0.2; silence −0.5. League (8.3): your kill 1.0; multikill 2.0 (a penta counts fully); ace 1.2; objective 1.0; a death you react to 1.0; team fight 0.8 | How much each thing lifts a moment's score (chapter 11.1b). Raise the one you think is being missed, lower the one that keeps winning wrongly. A weight for a signal a recording doesn't have is simply skipped. |
| Scoring | Sustain | Gunfire 15 s, explosions 10 s | Sounds that only mean something when they keep going. One shot is someone testing their gun; fifteen seconds of it is a firefight. Raise it to ignore short bursts, lower it to catch quick exchanges. |
| Scoring | Combination bonus / threshold | 1.2 / 0.1 | Added for each extra *kind* of thing happening at once — a fight **and** a reaction beats either alone. Kinds are: your markers, reactions (laughter, shouting, screaming), action (gunfire, explosions), audience (chat), and loudness. The threshold is how strong a signal must be to count; it's low on purpose, because the sound model hears laughter faintly. Every Wardogs clip you liked had both a fight and you reacting; every one you rejected had only one. Set the bonus to 0 to score every signal on its own. |
| Scoring | Marker look-back / look-ahead | 60 s / 10 s | How far either side of a marker press counts as the moment you meant. You press *after* the good bit, so the look-back is the important one. Too short and the build-up is missed; too long and ordinary play gets lifted with it. |
| Scoring | Smoothing | 5 seconds | How many seconds are judged together. Higher favours moments that stay good; lower lets a single loud second win. |
| Scoring | Z-score full scale | 3.0 | How unusual loudness or chat activity has to be to count as "as high as it gets". Lower makes AI-Editor more excitable. |
| Clips | Minimum score | 0.2 | How good a moment must be (1.0 = the recording's best) to become a clip. Lower gives more clips to choose from; higher, only the standouts. At 0.2 a 2-hour stream gives about 20–25 clips. |
| Clips | Lead-in / tail | 30 s / 4 s | Context before the moment and after it. Generous on purpose: videos trim clips down, but can't add back what was left out. Raise the lead-in if clips start too late to understand what happened. |
| Clips | Length | 15–90 s | Shortest and longest clip. A clip boxed in by two menus can be shorter. |
| Clips | Snap distance / pause | 6 s / 0.5 s | How far an edge may move to land on a pause or sentence end, and how long a gap in speech counts as a pause. |
| Clips | Fight run-on | Shooting within 10 s, up to 30 s more | A clip doesn't end while the fight is still going: if gunfire comes back within 10 seconds it's the same fight, and the clip follows it for up to 30 seconds more. In a highlight, the clip starts later instead, so the moment and the end of the fight both stay in. |
| Scoring | Black screen level | 24 (0–255) | A picture this dark counts as a black screen (loading, setting up a scene). It is never a moment, whatever is said over it, and clips don't start or end on one. |
| Scoring | Black screen length | 10 s | A black screen must last this long to count: a loading screen or setting up a scene. Shorter ones are part of the moment, like the screen going black when you crash or die, or a blinking effect. |
| Clips | Ending pause / run-on | 1 s / 10 s | A clip only ends where you then stay quiet for at least this long (a breath between sentences doesn't count), and may run up to 10 s longer to get there, so it never cuts you off mid-thought. |
| Clips | Start before a fight (`clips.keep_fights_whole`, `fight_loud_percentile`) | On, 90 | A video's clip starts before a fight already going (16.2). The game's sound counts as fighting in its loudest seconds: the top 10% of that recording (90). |
| Clips | Busy scene changes | More than 3 within 30 s | Scene changes closer together than this are camera editing (cutscenes), so they don't stop a clip. Lower it if clips run into menus; raise it if cutscene clips start too late. |
| Analysis | Spelling fixes | talk of → Tarkov, tarkoff → Tarkov, war dogs → Wardogs | Words the speech recognition mishears, and what you really said. Game and friends' names it doesn't know come out as ordinary words that sound alike. Add your own in `settings.yaml` under `spellings:` as `heard: meant`; they apply the next time you analyse, without transcribing again. (Telling the AI the names beforehand was tried and dropped: it started "hearing" the names, and "Thank you for watching", over game noise.) |
| Analysis | Scene threshold | 5.0 | How different the picture must look to count as a scene change. Lower finds more (including fast camera turns); higher misses quick menus. Changing it re-runs only scene detection. |
| Let's Play | Mode / target / range / extension / trim level | Split / 30 / 25–35 / 45–60 / Light | See chapter 15.2. |
| Let's Play | Title card | Empty (none), 4 s | Text shown over the start of every part, e.g. `Ep {episode} – Part {part}`; `{episode}` and `{part}` are filled in. Off because the YouTube title says it. |
| Highlights | Target length / min score / fill order / lead-in / longest clip / ordering | 10 min / 0.55 / Oldest first / 15 s / 50 s / Timeline | See chapter 16.2. |
| Shorts | Length / lead-in / captions | 15–60 s / 25 s (marked: 45 s before your press, 5 s after) / Off | See chapter 17.2. Burned-in captions are always off unless you tick them for a video. |
| Render | Encoder | NVENC H.264 | Fast GPU encoding. |
| Render | Loudness target | About −14 LUFS | Suits YouTube's volume level. |
| Captions | Highlights / Let's Plays | Off / Off | Burn your words into finished videos of that kind, every time. Off: add `--captions` to one render instead (chapter 19.2c). |
| Captions | Font / size / bold / outline | Arial / 64 / On / 4 | The look: letter height in pixels on a 1080p picture, and the black edge around the letters. |
| Captions | Position | 0.12 highlights, 0.22 Let's Plays | How far up from the bottom, as a share of the picture's height. Raise it if captions cover something a game draws at the bottom. |
| Render | Preset | `youtube_1080p60` | Which size and frame rate a finished video uses (the table in chapter 19.2). |
| Render | Include Discord | On | Your friends on Discord in finished videos. Only possible when Discord has its own track (chapter 7.3). Recordings with just a mixed track always have everything in. |
| Storage | Low space warning | 100 GB | When to warn. |
| Twitch | VOD keep days | 14 (1–365) | How long Twitch keeps your VODs: 7 days for regular accounts, 14 for Affiliates, 60 for Partners, Turbo and Prime. AI-Editor warns when a VOD is within 3 days of being deleted. |
| Twitch | Download quality | `1080p60` | The quality AI-Editor downloads VODs in. |
| Render | Music from your stream in videos (`render.include_stream_music`) | On | Your stream's music under the talking (19.2e). Only for DMCA-free music. |
| Render | Keep the game under my voice (`render.game_under_voice`) | On | The game's sound kept at least 10 dB under your voice, only where needed (19.2e). Needs the game on its own track. |
| Effects | Which are on (`effects.highlights`, `shorts`, `lets_play`) | none, until Phase 2E | Per kind of video; each video can change its own in Review (19.2d). |
| Effects | Effects per minute (`effects.highlights_per_min`, `shorts_per_min`) | 1.5 / 3 | At most: one per moment you marked with the Stream Companion. |
| Effects | Sound effects volume (`effects.sfx_volume_db`) | -3 dB | Against the moment they're on. |
| Effects | Between clips (`effects.between_clips`) | `cut` | Highlights: `cut`, or `slide` (the next clip slides in over the last, 19.2d). |
| Effects | Suggest effects in Review (`effects.suggest`) | On | Review lists each big moment with the effects that suit it, none ticked (19.2d). |
| Effects | Flash / shake strength (`effects.flash_strength`, `shake_strength`) | 0.35 / 0.02 | 1 would flash white; the shake's swing as a share of the picture's height. |
| Shorts | Suggestions per stream (`shorts.per_recording`) | 5 (1–20) | Your Numpad − moments always, then the best others up to this (17.1). |
| Shorts | Length (`shorts.min_length_sec`, `max_length_sec`) | 15–60 s | How long a Short may be. |
| Shorts | Lead-in (`shorts.lead_in_sec`) / after (`tail_sec`) | 8 s / 3 s | How long before its moment a Short opens, and how long it runs on after. |
| Shorts | Layout (`shorts.default_layout`, `shorts.layouts`) | `crop`; Dawnwalker `fit` | Zoomed centre, or the whole picture over a blurred copy (17.2). |
| Shorts | Crop centre (`shorts.crop_centre`) | 0.5 per game | Where the zoomed crop sits, left (0) to right (1). |
| Shorts | Zoom (`shorts.crop_fill`, `crop_fills`) | 0.75; League 0.65 | How much of the height the zoomed game fills; lower keeps more of the sides (17.2). |
| Shorts | Facecam (`shorts.facecam`) | none | Where your facecam is, per game. A game with one gets facecam on top (17.2). |
| Shorts | Platform (`shorts.platform`) | `universal` | Which apps' buttons the captions avoid (17.3). |
| Captions | Shorts size / words / highlight (`captions.shorts_size`, `shorts_words`, `shorts_highlight`) | 88 / 3 / `#FFD400` | Letter height on a 1920-high picture, words at once, and the colour of the word being said. |
| Publish | Let's Play title (`publish.lets_play_title`) | `{game} - EP {episode} Part {part}: {subtitle}` | The series pattern; the AI writes `{subtitle}` (20.1). |
| Publish | Description footer (`publish.description_footer`) | (empty) | Lines added under every description, e.g. your Twitch link. |
| Publish | Thumbnails (`publish.thumbnails`) | 6 (1–12) | Frames kept, best first (20.4). |
| Publish | Let's Play chapters every (`publish.chapter_every_min`) | 5 minutes (1–30) | How often a Let's Play part gets a chapter (20.3). |
| AI | Use the local AI (`llm.enabled`) | On | Rate and describe each clip with the local AI (5.2, 12.3). Off: everything else works as before. |
| AI | Model (`llm.model`) | `gemma4:12b` | The Ollama model. It must be able to look at pictures. About 8 GB. |
| AI | Address (`llm.host`) | `http://127.0.0.1:11434` | Where Ollama answers. Only this PC is allowed. |
| AI | How much the AI's rating counts (`llm.rating_weight`) | 0 (0–1) | The share of a clip's score that is the AI's rating. 0: shown, but it doesn't change which clips are picked (12.3). |
| AI | Frames per clip (`llm.frames_per_clip`) | 3 (0–8) | Pictures from each clip the AI looks at. More is slower. |
| AI | Temperature (`llm.temperature`) | 0.2 | How much its answers vary. Low, so the same clip gets the same rating. |
| Twitch | Ignored chatters | StreamElements, Nightbot, Moobot, Streamlabs, Fossabot, Sery_Bot, WizeBot, SoundAlerts | Chat bots post automatically, so their messages never count as viewers reacting. Add any other bot your channel uses. |
| Tools | Tools folder | Empty (a `tools` folder next to your Models folder) | Where helper programs, such as the Twitch downloader, are kept. |
| Logging | Screen detail level | WARNING | How much AI-Editor prints while it works. WARNING shows only problems. INFO also shows each step as it happens. The log file always records full detail, whatever this is set to. |
| Game profiles | Screen reading (per game) | On | Turn off if detection breaks after a game update. |

---

## 25. Troubleshooting

Every message AI-Editor shows you ends with a code in brackets, like `(Help: manual chapter 25, code E004)`. Find that code below for what it means and what to do.

> **[Engineer: this list grows with each phase. Codes E001–E052 exist as of Phase 1D.]**

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
| **E013** | AI-Editor could not process that video file | FFmpeg, the tool doing the video work, stopped with an error partway through. AI-Editor already tries three methods for preview copies (full graphics card, part graphics card, processor only) before showing this. | Check the recording plays normally in a video player. If it does, run the same command again. If it fails a second time, use **Copy diagnostic info** and send it to your engineer. The details are in the log file. |
| **E014** | The audio track labels don't match this recording | You gave a different number of labels than the recording has tracks, or used a label AI-Editor doesn't know. | Give exactly one label per track, in order. Valid labels: `mixed`, `mic`, `game`, `voice_chat`, `unknown`. Run `ai-editor probe "<file>"` to see how many tracks there are. |
| **E015** | AI-Editor doesn't have that recording in its library | You gave a library number that doesn't exist, or a file that hasn't been imported. | Run `ai-editor library` to see your recordings and their numbers. If the file is new, import it first (chapter 10.1a). |
| **E016** | That recording hasn't finished importing | Analysis reads the audio tracks that importing saves, and one or more of them is missing — for example after cleaning up the cache. | Run the same `ai-editor import` command again. Anything already finished is reused, so it's quick. |
| **E030** | AI-Editor could not download an AI model it needs | The first analysis downloads two AI models (about 4.6 GB in total), once. This needs an internet connection. | Check your connection and run the same command again. Half-finished downloads are cleaned up automatically, and the next try starts fresh. |
| **E031** | Your graphics card ran out of memory | The AI models need several gigabytes of graphics memory. A game, OBS, or a browser with many tabs may be using it. | Close games, OBS, and other graphics-heavy programs, then run the same command again. Finished steps are kept. |
| **E032** | AI-Editor couldn't reach its local AI (Ollama) | Ollama isn't installed, or it couldn't be started. | Install Ollama from ollama.com (5.2), or open it from the Start menu, then try again. Everything else works without it. |
| **E033** | The AI model isn't downloaded | The model is downloaded once (about 8 GB), then everything runs offline. | **Settings → AI → Download model**, then try again. |
| **E034** | The local AI gave an answer AI-Editor couldn't use | It happens now and then with AI models. That clip is skipped; the others are rated. | Click **Rate with AI** again: only the clips without an answer are asked about. |
| **E035** | The local AI was far too slow, so AI-Editor stopped it | Almost always a game (or another program) using the graphics card. Carrying on would slow your game down and take hours. | Press **Resume** in Jobs when you've finished playing. Clips already rated are kept. |
| **E040** | That doesn't look like a Twitch VOD link | AI-Editor couldn't find a VOD number in what you gave it. | Open the VOD on Twitch and copy the link from your browser (`twitch.tv/videos/...`), or copy it from **Content → Video Producer** in your Twitch dashboard. Both kinds of link work, and so does just the number. |
| **E041** | Twitch won't share that VOD | The VOD is private, unpublished, subscriber-only, or expired. Twitch treats a VOD that isn't public as if it doesn't exist. | In your Twitch dashboard open **Content → Video Producer** and make the VOD public while you download it; you can change it back afterwards. Or download it there yourself and import the file: `ai-editor import "<file>" --source twitch`. |
| **E042** | The download from Twitch didn't finish | The internet connection dropped, or Twitch stopped responding. | Check your connection and run the same command again. |
| **E050** | AI-Editor could not reach OBS | OBS isn't open, its WebSocket server is switched off, or the port doesn't match. The Stream Companion shows this as **Not connected** and keeps checking every 5 seconds, so you can simply open OBS. | Open OBS. If it still says this, follow chapter 7.4: **Tools → WebSocket Server Settings**, tick **Enable WebSocket server**, and check the **Server Port** is `4455`. |
| **E051** | OBS didn't accept AI-Editor's password | OBS asks for a password before any program can connect. None has been saved yet, or the password in OBS changed (clicking **Generate Password** in OBS makes a new one). | Run `ai-editor setup-obs` and paste the password from **Tools → WebSocket Server Settings → Show Connect Info**. |
| **E052** | This version of OBS can't talk to AI-Editor | The WebSocket server AI-Editor uses is built into OBS 28 and newer. | Update OBS from obsproject.com. |
| **E053** | AI-Editor could not set up a marker hotkey | Another program already reserved that key, or it isn't a key Windows can reserve (the numpad's Enter key is the common one). The Companion carries on; only that one key doesn't work. | Pick different keys in Settings and start the Companion again. Numpad + and Numpad − work well. |
| **E020** | A job could not finish | A step failed. The steps that already finished were kept. | Open the **Queue** and press **Resume**. It continues from the step that failed, without repeating finished work. |

### Stream Companion says "OBS: Not connected"
- Make sure OBS is open. The Companion checks again every 5 seconds, so there's no need to restart it.
- Check **Tools → WebSocket Server Settings** in OBS: server enabled, port matches AI-Editor.
- If it says **Password not accepted**, run `ai-editor setup-obs` again (code **E051**).
- Run `ai-editor doctor`: its **OBS** line tells you whether AI-Editor can reach OBS right now.

### I closed the Companion (or OBS) in the middle of a recording
Start it again. When it reconnects it asks OBS what's running and logs anything it missed. Those lines show **noticed after it happened** in `ai-editor sessions`. The start of a recording is still exact, because OBS reports how long it's been recording. Markers you pressed while it was closed aren't kept, so start it again soon.

### The Companion closed by itself
Fixed in version 0.11.1. Before that, it could close when it saved its status at the very moment the app window was reading it, which happened once on 5 October. Now it tries again a moment later, and anything else unexpected is noted in the log file (`cache/logs/ai-editor.log`) while it carries on. If it ever does close, start it again and send that log file along.

### League events aren't being logged
- Events only appear during a loaded match, not in lobby or champion select.
- OBS must be recording or streaming, and your **League** scene showing. On another game's scene the Companion doesn't ask (8.3). If your League scene's name doesn't say "League", add it under `scene_games` (8.1b).
- Starting the Companion mid-match is fine: it picks up everything from the start of the match. Events from before the recording began are kept but have no place in the recording.
- During a match, the Companion's **League** line should say **match running**. If it says **can't read events: couldn't confirm it's League's own server**, something answered that wasn't signed by Riot; nothing from it is used. Restart League, and send the log file (`cache/logs/ai-editor.log`) if it keeps happening.
- Check `companion.league_events` isn't set to `false`.

### My hotkey doesn't do anything
- Check the **Keys** line in the Companion. If it says **not set up in OBS yet**, do chapter 7.4a. If it says **set in OBS** but pressing does nothing, open OBS's **Settings → Hotkeys**, filter on **Mark**, and check **Show 'Mark moment'** has your key.
- If a key works outside a game but not inside it, the game is blocking other programs' hotkeys: use OBS for the keys (chapter 7.4a). That's the default.
- With `marker_keys: windows`: if the **Keys** line says **not available**, another program (Discord, OBS, a game launcher) reserved that key first: pick a different one in Settings (code **E053**).
- The **Marked** line counts up on every press. If it counts up but the marker isn't where you expected, check `ai-editor sessions` — a marker pressed while OBS wasn't recording has nothing to attach to.
- Games started **as administrator** can stop Windows passing the key on. Run the Stream Companion as administrator too (right-click the terminal → Run as administrator).
- The Companion must be running. It only reserves the keys while its window is open, which is also why your games get those keys back the moment you close it.

### "Not enough graphics memory" / analysis crashes
- Close games and other GPU-heavy apps during analysis.
- Make sure **Unload AI models between steps** is on.
- In Settings, choose a smaller AI model size.

### Analysis is very slow
- Check the Queue: AI-Editor may be running voice separation (Twitch VODs take longer).
- Make sure **Run AI on** is set to GPU.
- Update NVIDIA drivers.

### Subtitles don't appear when I play the preview copy in VLC
AI-Editor saves the subtitles as `proxy.srt` next to `proxy.mp4`, and VLC normally loads them by itself. If you opened the preview copy **before** analysis finished, VLC may have remembered it as having no subtitles.
1. With the preview copy playing, press **`V`** to switch through subtitle tracks.
2. Or open **Subtitle → Sub Track** and choose `proxy.srt` if it's listed.
3. If it isn't listed, choose **Subtitle → Add Subtitle File…** and pick `proxy.srt` from the same folder, or drag `proxy.srt` onto the VLC window.
4. Still nothing? Close VLC completely and open the preview copy again.

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
- **Stream Companion**, the only part that runs while you play, talks to **OBS**, and during League matches to **League's own Live Client Data API** on your PC (8.3): Riot's official, read-only feed, at `127.0.0.1:2999`, which only ever *asks* what happened. Nothing else. It doesn't look at which programs are running, doesn't touch the game in any way, and never presses keys for you. Its hotkeys are registered the same way Discord's and OBS's own hotkeys are, through Windows' standard hotkey feature. It doesn't use a keyboard hook, which is what key-logging and macro tools use.
- These rules are checked automatically: every time AI-Editor is built, a test scans all of its code and fails if anything that could touch a game appears.
- League events come from Riot's official, built-in local game data feature (the Live Client Data API). No Riot account, key or web service is involved: the feed never leaves your PC. The automatic test also checks that the Companion can only ask that one address, and only read from it.
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
