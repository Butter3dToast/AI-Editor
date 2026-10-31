# Changelog

Written so the creator can understand what changed, not only the engineer
(specification section 14.3).

## 0.37.0 — Backup button, and the manual brought up to date — 31 October 2026

**New**

- **Settings → Backup**: saves your library (ratings, your taste, plans, rules,
  style profiles, issues) and your Settings changes as one zip in the folder
  you pick, e.g. inside Google Drive for desktop so it's on your Drive. Your
  165 MB library makes about 42 MB, in a few seconds.
- **Once a week by itself** while AI-Editor is open (switch off in Settings),
  and **Back up now** any time.
- **Restore**: puts a backup's library and Settings back, after backing up the
  library as it is now, so a restore can be undone.

**Good to know**

- Your OBS password, and any other password or key, is never in a backup.
  Restoring keeps the one on this PC.
- AI-Editor never deletes a backup: Settings shows how much space they take.

**The manual, tidied**

- Chapter 22 (how AI-Editor learns) describes what was really built in
  Phase 3; the old "Learning → Summary" and "Reset" were never built.
- What's built for Shorts (start and end, caption words) and Clips is now
  stated correctly; old "until the app window arrives" headings are gone; the
  Settings chapter lists every section.

## 0.36.0 — Phase 3D: Thumbnail prompts for Gemini — 31 October 2026

**New**

- **Thumbnail prompts**: for a highlight video or a Let's Play part, the local
  AI looks at each of the 5 best thumbnail frames and writes a prompt to paste
  into the Gemini app with that frame attached. Gemini makes the thumbnail
  under your own subscription. They're in Review under the thumbnail frames,
  each with a copy button and **Open the frame**.
- They're written along with the titles. **Write thumbnail prompts** writes
  them for videos prepared before, or again.
- **Highlights stay clean** (no text on the picture). **Let's Play parts** say
  their episode and part ("EP 6 PART 2"): change the words in Settings →
  Publish. Story games are told not to give anything away.
- **Your thumbnail look** (Settings → Publish) is added to every prompt, so
  your thumbnails look like a set.

**Good to know**

- **AI-Editor sends nothing online.** The Gemini API can't use your
  subscription (it bills separately, and Gemini 4 Argon there makes no
  pictures), so there's no key and no charge: you paste the prompt yourself.
- Shorts have no prompts: YouTube uses a frame from the Short itself.

## 0.35.0 — Phase 3B: Overnight work — 31 October 2026

**New**

- **Overnight work** (Settings → Overnight work, off until you switch it on):
  at the time you set, AI-Editor imports the new recordings in your raw
  folder, finishes any import or analysis that was cut short, and drafts the
  plans: a highlight plan and 3 Shorts for each new stream, the parts for each
  new Let's Play episode. They wait in Review. **It never renders and never
  deletes anything**, and each recording is drafted only once.
- **It gives way to you**: it asks OBS whether it's recording or streaming
  about every 30 seconds, and stops the step it's in if so; and before each
  step it waits while the graphics card is busier than your level (60%), for
  a game. It never looks at which programs are running (the anti-cheat rule).
  The step it gave way in starts again later; finished steps are kept.
- **Stop by**: an optional time it stops at even if it isn't finished; the
  rest carries on the next night. **Run it now** starts it straight away.
- **A morning note** at the top of the window says what it did. Anything that
  went wrong with a recording goes in the Issues tab, and the night carries on.
- **Let's Play games in Settings**: add a new series' game by name (Settings →
  Let's Play), or remove a finished one. It's then recognised by its OBS scene
  and file names, like the four built-in games.

**Good to know**

- AI-Editor must be open at the start time (minimised is fine), with the PC on.
- A game started without OBS in the middle of a step is noticed when that step
  ends. Pause in Jobs always works.
- The library is upgraded (version 11); a full copy of it is kept beside it
  first (`ai-editor.before-v11.db`).
- Your raw folder has 6 recordings from 25-30 October not imported yet: the
  first night imports and drafts them all.

## 0.34.0 — Phase 3A-3b: The local AI learns from your verdicts — 25 October 2026

**New**

- **The local AI is shown your own verdicts** when it rates a clip: the 4 clips
  you liked and the 4 you didn't that you rated most recently, from other
  streams of the same game, with what happens in each, and asked to rate the
  way you would. It starts once a game has 4 of each.
- **It agrees with you more**: tried on 25 Oct on 317 of your League clips,
  each stream rated with examples from the others only, it put a clip you
  liked above one you didn't 63% of the time, against 54% without. Asking
  again without examples gave the same as before, so that's not chance.
- **Your taste uses the AI's rating where it helps**: with the same safety net,
  tested with and without it. League today: 71% with it, 68% without (on the
  321 clips the AI has rated with your examples), so it's in use. Your taste
  overall: 74%, the usual score 69%.
- Those 317 test ratings are kept in your library, so this works for League
  straight away.

**Good to know**

- Old clips keep the AI rating they had: they aren't rated again (your choice).
  New streams are rated with your examples when they're analysed.
- Those 317 kept their earlier tags; their "why" says they were rated again
  with your examples.

## 0.33.0 — Phase 3A-3a: Effect nudges — 25 October 2026

**New**

- **Review asks about effects you hardly use.** Every render writes down which
  effects Review suggested and which you used. Once one has been suggested at
  least 10 times over 3 or more videos and you used it under 15% of the time,
  Review asks under the effects: *"In your last 5 videos AI-Editor suggested
  slow-motion replays 24 times, and you used 2. Change that?"*
  - **Only on the biggest moments**: still suggested, about three times in a
    10-minute video.
  - **Stop suggesting it**: not offered any more.
  - **Keep as is**: nothing changes, and it won't ask about that effect again
    for 10 videos.
- **Your answers are Settings** (Settings → Effects → **Only on the biggest
  moments** and **Don't suggest**), kept in your private settings file and
  changed back there.

**Good to know**

- Nothing changes until you answer, and an answer only ever cuts suggestions
  down: nothing is ever ticked for you, so effects stay off by default.
- Let's Plays have no effects, so they don't count. Highlight videos and Shorts
  do. Leaving the suggestions unticked is exactly what it looks for.

## 0.32.0 — The Issues tab — 25 October 2026

**New**

- **An Issues tab** (the last tab) for writing problems down. Say what's
  wrong, and optionally which video and where ("16:39"), then click **Record
  it**. AI-Editor adds the details needed to fix it: its version, FFmpeg's and
  Windows', the video's plan, the recording and its sound tracks, the log
  lines that name that video plus the last 120, and your settings.
- **Private values never go in**: the OBS password and anything named like a
  password, secret, token or key show as [hidden], in the settings and in the
  log lines. Tried with your real settings: the password wasn't in the file.
- **AI-Editor writes down its own problems**, marked "From: AI-Editor": every
  job that fails, and every render whose sound check had to make a piece's
  sound again (that one already marked Fixed, since the video came out whole).
- **A list to work through**: Open or All, newest first. Click one to mark it
  Fixed, with the version it was fixed in and a note.
- **A text file per issue** in `cache\issues`, kept up to date. Next session,
  say "check the issues" and everything needed is there. Nothing is sent
  anywhere.
- **Copy diagnostic info**, at the bottom of the tab: everything about the
  issue you clicked (or how things stand now), ready to paste. Error messages
  have pointed to this button since Phase 1; it now exists.

**Good to know**

- Opening this version upgrades the library (one new table, for issues). A
  copy of it as it was is kept first, as `ai-editor.before-v10.db`.

## 0.31.1 — Fix: the game's sound no longer drops out of long Let's Play pieces — 25 October 2026

**Fixed**

- **EP 5 Part 1 lost the game's sound from 16:39 to the end**, with only your
  voice left. Your recording was fine, and so was the sound mix made on its
  own. The tool that renders (FFmpeg 9.0.1) lost the game track when it made
  the picture and four sound tracks of a 28-minute piece in one go, 12½
  minutes in. Part 2 was fine.
- **Each piece's picture and sound are now made separately**, then joined
  (copied, nothing lost). Both are simple jobs FFmpeg does reliably. A 30-minute
  part takes well under a minute longer.

**New**

- **Every render checks its own sound.** After each piece, AI-Editor compares
  the sound it made with your recording's tracks, second by second. Where the
  recording has sound and the render doesn't, it makes the sound again. If it's
  missing twice, the render stops and says where in the recording, rather than
  giving you a video with a hole in it. Tried on the broken Part 1: it found the
  hole at 16:38.
- **The sound and picture must both run to the end**, in each piece and in the
  finished video, or it isn't finished. Part 1 rendered again on 25 Oct, before
  AI-Editor was restarted with this fix, came out a second, different way
  wrong: its sound stopped altogether at 16:46 of 32:36. This check refuses
  that file.

**Done**

- EP 5 Part 1 rendered again with this fix on 25 Oct: the game's sound all
  the way through, picture and sound both 32:36, every piece's check passed,
  in the same 10 minutes as before. Part 2 didn't need it.

## 0.31.0 — Phase 3A-2: Your taste — 24 October 2026

**New**

- **AI-Editor learns your taste**, per game, from your 👍, 🔖 and 👎, and uses
  it to order your clips and pick them. It looks at the usual score, kills
  and multikills, your Shorts marks, how long the moment is, and how much
  talking there is. From your League ratings it learned that talking without
  action counts against a clip, and kills, your Shorts marks and longer
  fights count for it.
- **Only where it helps**: each time it learns, it tests itself on each
  stream using only your other streams, as a new stream would be. It's only
  used in a game where it beats the usual score. League today: **74%**
  against the usual score's 70% at putting a clip you liked above one you
  didn't, so it's in use. Wardogs starts learning at 30 ratings.
- It learns again after every 20 new ratings, in a fraction of a second, on
  this PC. Nothing new to install.
- **Clips tab**: a new **Your taste** column (how likely you are to like the
  clip), and the list in that order where it's in use.
- **Settings → Learning your taste**: the **Learn my taste** switch, and a
  line per game saying how it did and whether it's in use.
- **A copy of your library before every upgrade**: when a new version changes
  how the library is laid out, AI-Editor first saves a whole copy beside it
  (`ai-editor.before-v9.db`). It never deletes it.

**Good to know**

- It changes the order, never the bar: as many clips pass the quality bar
  as before. "My 👍 clips" and "My 🔖 clips" videos, your marks, 👎 and
  your rules work exactly as before.
- The manual described a Settings → Backup button that was never built. It
  now says how to back up by hand.

## 0.30.0 — Phase 3A-1: How well AI-Editor knows you — 24 October 2026

Phase 3 begins: AI-Editor learning your taste. This first step measures where
it stands and collects what it will learn from. Nothing about how clips are
picked has changed yet.

**New**

- **🔖 Next video** in the Clips tab, next to 👍 and 👎: a good clip you're
  saving for a later video. It never goes into the video you make now, not
  even when AI-Editor picks the clips itself. Shorts may still use it.
  AI-Editor learns from it like a 👍.
- **Create video → Which clips**: **My 👍 clips** (as before), **My 🔖
  next-video clips** (a video of exactly the clips you saved), or
  **AI-Editor picks**. One or the other, never both in one video. Once a
  rendered video uses a 🔖 clip, it turns into a 👍.
- **How well AI-Editor knows you**, at the bottom of the Clips tab: per game
  and per week you streamed, **Picked right** (of its top 20 clips in a
  stream, how many of the ones you rated you liked) and **Found your
  favourites** (of the clips you liked, how many were in its top 20). Your
  League starting point: 66 to 85% picked right, 45 to 73% found. Both
  should climb as it learns.
- **Kept for learning from now on**: where each clip sat in the list when
  you rated it, each effect you tick or untick in Review, and every clip that
  ends up in a rendered video or Short.
- From the command line: `ai-editor highlights --next-video`.

**Good to know**

- A clip's place in the list is written down when you first rate it and
  never changes, so the numbers stay fair when learning starts re-ranking
  clips. Editing a clip doesn't count against it. Ratings from before this
  version get their places the first time you open the box.

## 0.29.0 — Phase 2I-2: Who's who — 24 October 2026

**New**

- **A new analysis step, "Telling your friends' voices apart"**: it listens
  to your friends' talking on the Discord track and groups it into
  **Voice A, B, C…** (whoever talks most is A). Around 20 seconds for a
  2-hour stream, on the processor.
- **Library → Who's talking (your friends on Discord)**: pick a voice, play
  a few seconds of it, type their name and click **Save name**. Name someone
  once: matching voices in your other streams get the name too, and new
  streams know them by themselves.
- **Captions say who's talking**: "Chris: let's go get him!", in that
  friend's own colour. Voices you haven't named stay light blue.
- **That's not them** takes a name off one voice in one stream.
- **Settings → Your friends (Discord)**: rename a friend, change their
  caption colour, or forget them (asked once more; their lines stay, unnamed).
- **Let's Plays are never included**, so game characters' lines can't be
  captioned as a friend. A Discord track that's a copy of your game sound is
  now listened to (your 22 Sep stream records it that way).
- **Privacy:** AI-Editor now tells Gradio and the model download library not
  to send usage reports. The voice model (26 MB) is downloaded once into your
  models folder and runs offline.
- Tested on 24 Oct on your whole 22 Sep Wardogs stream: friends' words in
  3 minutes, voices told apart in 21 seconds, 7 voices found.

**Good to know**

- Over a long stream one friend can show up as two voices (their voice
  changes when they shout or laugh). Give both the same name and they join
  up. AI-Editor never joins them by itself, because a wrong name is worse
  than naming twice.
- Installed: `sherpa-onnx` (the voice fingerprinting), nothing else; torch
  is untouched.

## 0.28.0 — Phase 2I-1: Your friends in captions — 24 October 2026

**New**

- **Your friends on Discord are captioned**, whenever captions are on: their
  lines in light blue, yours in white. When you talk at the same time, theirs
  sits just above yours. In Shorts their words light up one by one like yours.
- **A new analysis step, "Writing down your friends' words (Discord)"**, from
  your Discord track (OBS track 4). It runs by itself for new streams; for one
  analysed before, click **Analyse (or resume)** and only the new step runs,
  a few minutes on the graphics card. A Discord track that's a copy of another
  track is left alone, so you're never captioned twice.
- **Fixing captions** in Review lists their lines too, marked 👥: fix, hide
  and put back the same way.
- **Their words are only for captions.** Clip scores, titles, the AI's
  ratings and "You said" stay yours alone.
- Tested on 24 Oct on 10 minutes of your 22 Sep Wardogs stream: 686 words,
  none set aside as mishearings, transcribed in 30 seconds.

**Good to know**

- In the quick preview of a highlight video, captions are plain subtitles, so
  your friends' lines show in white there. Finished videos and Short previews
  have the colours.
- Two friends talking straight after each other can share a line, until
  2I-2 tells their voices apart.

## 0.27.0 — Phase 2H-3b: Effects on a moment — 24 October 2026

**New**

- **Effect rules** in the Rules tab: "Add a zoom on pentakills", "A slow-mo
  replay on Baron steals", "Shake and boom on every kill", "No effects when I
  die". AI-Editor says back exactly what it will do before you save.
- **They never switch an effect on.** They change what Review suggests under
  **Suggested effects on the big moments**, marked with the rule: "Clip 4 at
  1:52: Kill 📌 r007: zoom". Nothing is ticked for you; tick one and the
  moment gets exactly those effects.
- **Your choices (24 Oct):** the rule's effects replace the moment's usual
  ones, and a moment you tick is never dropped by the effects-a-minute limits
  (a style profile's included).
- **New moments:** a rule reaches moments that get nothing today, like a
  single kill or a Dragon. Two it names within 2 seconds in one clip (a kill
  and the double kill straight after) get one effect, on the bigger.
- **"No effects when I die"** leaves those moments without, and out of the
  suggestions.
- Only moments with an exact second can carry an effect: League's and your
  marks. "A zoom when I laugh" is kept as a note, saying why.
- Tested on 24 Oct: six effect tips, two tries each, all right; on your
  19 Oct stream "A zoom on every kill" suggested 10 zooms, one per fight.

**Changed**

- A moment tip AI-Editor can't fully read now says to name the moment ("Always
  include pentakills"), not to give a number.

## 0.26.1 — Fix: deleted streams leave the lists — 24 October 2026

**Changed**

- **Streams whose video you deleted aren't listed any more** in Clips or
  Create video: the lists were mostly "(video deleted)". No video can be made
  from them, so Create video never shows them. In Clips, tick **Show streams
  whose video is deleted** to rate their clips anyway, which still teaches
  AI-Editor. The Library still lists everything, and nothing is removed from
  it: their analysis, ratings and League events all stay.

## 0.26.0 — Phase 2H-3a: Moment rules, always in or never in — 24 October 2026

**New**

- **Moment rules** in the Rules tab: "Always include pentakills", "Never use
  clips where I die", "Always put Baron steals in my Shorts", "Never use rage
  clips in Wardogs". AI-Editor says back exactly what it will do before you
  save, as for every rule.
- **The moments it knows.** League, exactly, from League itself: your kills,
  double to penta kills, your deaths, aces either way, first blood, every
  objective, steals, Victory and Defeat. Heard in any game: your marks,
  laughter, a loud reaction, gunfire. The AI's guesses in any game (funny,
  fail, rage, clutch, scary, teamwork, banter), and the rule says they're a
  guess.
- **Always:** the clip goes in like a 👍, whatever its score, and Review's
  **Why** says which rule: "📌 r004: Penta kill". **Never:** it stays out like
  a 👎; Review's summary says how many each rule kept out, and **Add a clip**
  lists them near the top, marked "kept out by r003".
- **Your choices (24 Oct):** your own 👍 or mark always beats a "never" rule.
  Dying in a good fight is still a good clip: a "never" rule about your death,
  your team getting aced or a defeat leaves a clip in when something good
  happens too (a kill, ace or objective). "Triple kills" means a triple or
  bigger. "Baron steals" means a stolen Baron. No clip is ever cut.
- **With Only my 👍 clips**, the video is still exactly your 👍 clips: "always"
  rules add nothing, and their clips come right after your 👍 ones in **Add a
  clip**.
- **Shorts:** "always" moments are suggested right after your Numpad −
  moments; "never" moments aren't suggested unless you marked them or gave
  them a 👍.
- Tested on 24 Oct: nine tips, three tries each, all right.

**Changed**

- "Add a zoom on pentakills" (an effect on a moment) is still kept as a note:
  that's 2H-3b.

## 0.25.1 — Fix: only your 👍 clips, videos named by their title — 24 October 2026

**Changed**

- **Only my 👍 clips** (Create video, Highlights, ticked by default). If you gave
  any clips a 👍, the highlight video is exactly those clips: no marked clips,
  and nothing added to reach the length. Vote for the clips you want in this
  video and leave the rest for the next one. Review's summary says how long they
  came to against the target, and **Remove** adds nothing in a clip's place
  (**Add a clip** still lists every clip). With no 👍 clips at all, AI-Editor
  picks them itself as before. Your marks still capture clips as before. Shorts
  are unchanged.
- **The Clips tab's minutes are what the video will be.** Each clip is counted
  at the length the game's style profile and your rules give it. On 24 Oct it
  said 12.2 min while the video, with the League profile's 25 s clips, came
  to 7.6.
- **Finished videos are named with your title.** Keep a title in Review's
  Publish section before rendering and the video (and its text file) is saved
  under it: "We Hit Those.mp4". Never over another video's file: a second one
  with the same title gets "(2)".

**New**

- **Delete several plans** in Review: tick them (or **Tick every draft**),
  then delete them all at once, asked once more. Only the plans leave the list.
- Switching tabs pauses a playing video.

**Fixed**

- A title with an apostrophe ("Well Don't Mind If I Do") stopped its render at
  85%.

## 0.25.0 — Phase 2H-2: Rules from your tips — 19 October 2026

**New**

- **The Rules tab.** Type a tip the way you'd say it ("Keep League highlight
  clips under 20 seconds") and press **Understand it**. Your local AI turns it
  into a rule, and AI-Editor says back exactly what it will do, in its own
  words: *League of Legends highlights: clips 20 seconds long at most.* Change
  which games and videos it's for if needed, then **Save**. Nothing is saved
  before that.
- **What a rule can change:** clip length, video or part length, the teaser,
  clip order, the quality bar, Let's Play silences, how captions look, how
  many effects at most, and your three tips' switches (per game too).
- **What it can't:** speed anything up (never: your choice), switch effects or
  captions on (you tick those in Review), or choose moments (2H-3). Those, and
  anything AI-Editor can't act on yet, are kept as 📝 notes.
- **Your rules** are listed newest first, **✅ On** or **⬜ Off**. Pick one and
  untick **On** to make new videos without it, or delete it. Two rules that
  disagree: the newer wins, and the list says so.
- Rules apply by themselves to every new video they match, and win over the
  style profile. A plan keeps a copy of the rules it was made with; Review's
  summary lists them on a **Rules:** line. There are no rules until you save
  one.
- Tested on 19 Oct: your three tips and nine others all came out right; your
  three every time (five tries each).

**Changed**

- Your Instagram, X, TikTok and YouTube links are under every description.

## 0.24.1 — Fix: Let's Play parts froze — 19 October 2026

**Fixed**

- **The picture froze partway through EP 4** while the sound carried on. Every
  piece of a part longer than about 6½ minutes lost its picture there. FFmpeg,
  reading the picture and your four separate sound tracks (mic, game, Discord,
  music) from the recording in one go, ran ahead on the sound and gave up on
  the picture. The recording is now opened twice, once for the picture and
  once for the sound. EP 4 Part 2 now renders whole (37:06, picture and sound).
  Highlights and Shorts were never long enough to be hit.
- The game or the music could go silent for a split second at the start of a
  piece.

**New**

- **A safety check on every render.** After each piece, AI-Editor checks the
  picture runs as long as the sound. If it doesn't, the piece is made again
  the slower way; if that fails too, the render stops and says so, instead of
  saving a frozen video as finished.
- FFmpeg's warnings now go in the log even when a render succeeds.

## 0.24.0 — Phase 2H-1: Your three tips — 11 October 2026

Your test tips for the Rules tab, built in first so the basic edit gets
cleaner. Each has its own switch in Settings; plans you already reviewed and
clips you adjusted are left as they are.

**New**

- **"Ensure the action is always within the clip."** When a fight is already
  going where a highlight or Short clip would start (the game's sound among
  its loudest, gunfire, or League champions dying), the clip starts a second
  before the fight began, as long as it stays within its length. When it
  can't, Review's list marks it **⚠ starts mid-fight (4 s already gone)**, for
  Adjust the cut. On your League streams: 1 clip in 230 moves, about 7 are
  marked. Settings → Highlights.
- **"Make sure the video sound is never over my voice."** While you talk, the
  game is kept at least 10 dB under your voice, only as far as needed, and
  straight back up after (Discord friends don't lower it). On your League
  streams the game is far under you already, so it's never touched; on
  Dawnwalker it's lowered now and then, by about 4 dB. Finished renders only,
  with the game on its own track. Settings → Captions and sound.
- **"Suggest where an effect can work and which effect."** Review's **Suggested
  effects on the big moments** lists every big moment with the effects that
  suit it ("Clip 12 at 5:35: Double kill: shake + replay"), none ticked. Tick
  one and that moment gets exactly those. Settings → Effects.

**Fixed**

- **A Short without talking blasted.** Short_09 was turned up 31 dB to
  YouTube's level, raising your stream's music with it, next to 07 and 08 at
  about 9. A video is now never turned up past where your normal talking would
  be at that level (about 10 dB on your League streams): its music and game
  sound as they do in your other videos. Of everything rendered so far, only
  six Shorts without talking would have come out differently.

## 0.23.0 — Phase 2G-2: Using a style profile — 11 October 2026

**New**

- **Create video has a Style profile box.** It picks the profile made for that
  game and kind of video by itself (tick them on the profile), and you can
  change it or choose "No profile (my Settings)".
- **What a profile changes**, and never switches anything on:
  - cuts per minute: how long highlight clips run (asking for 26 s clips gave
    29 s in the middle; 12 s gave 14.6 s; your marked moments keep their
    own length);
  - opening teaser: its length, or none;
  - longest silence left in: the Let's Play silence trim only;
  - zooms and sound effects: at most that many a minute each, on the biggest
    moments, when they're switched on; zoom strength;
  - captions: size, height, and words at once on Shorts, when switched on.
- Review's summary starts with a **Style:** line saying what the profile
  changed. A plan keeps a copy of the values it was made with.

**Changed**

- **With no teaser, "As it happened" is strictly as it happened.** The best
  clip was held back for the end even when no teaser set it up, so the last
  clip jumped back in time (0:50 after 2:06). Taking the teaser out in Review
  also moves its clip back to where it happened.

**Fixed**

- **Save profile** failed with an error ("build...") every time.
- **A new quick preview played the old one**, frozen with noise, when a new
  plan had the same name as one it replaced: the browser kept its copy of the
  old video. Each preview now has its own address.
- YouTube references: a download YouTube refuses ("403 Forbidden") is tried
  again, up to 3 times; error messages no longer show colour codes; videos
  over half an hour now download (they failed before).

## 0.22.0 — Phase 2G-1: Style profiles from reference videos — 11 October 2026

**New**

- **Style Profiles tab.** Give AI-Editor 2-5 videos whose editing you like
  (YouTube links, or video files on this PC) and press **Analyse references**.
  It measures how each one is edited and makes a draft profile with sliders:
  cuts per minute, the longest silence left in, the opening teaser, zooms
  (how often, how strong), sound effects, and caption size, height and words
  on screen. Adjust and save.
- What it measures, per video, is in a table, and under each slider, so an odd
  one out is easy to spot.
- The local AI looks at 8 frames of each video and notes editing techniques
  the numbers can't show (meme images, emojis, the facecam's place). It's told
  what was measured so it doesn't guess; expect a short list or none.
- A profile never switches effects or captions on: it sets how often and how
  strong they are when you do. Choosing a profile when making a video is next
  (2G-2).

**How the measuring was checked** (on the creator's own videos)

- Cuts: a game's shop, scoreboard and camera jumps aren't counted, only real
  edits (10.7 a minute on a League highlight before, 1.8 after; right).
- Zooms: all 6 of 6 added punch-ins found at the right strength; none in 30
  minutes of plain gameplay but League's own "DEFEAT" zoom.
- Captions: right size, height and word count; a game's own text and menus
  left out.
- Sound effects: only meme sounds (whoosh, boing, air horn, ding) are counted.
  Booms and hits can't be told from a game's own sounds or the music.

**Your videos**

- A YouTube link is downloaded small, measured, and deleted; only the numbers
  are kept. A file on this PC is only read, never changed or deleted.
- New: yt-dlp (downloads the YouTube references). If YouTube links stop
  working, updating it usually fixes it (manual chapter 13).

## 0.21.0 — Phase 2F-3: Short leftovers join the last part — 11 October 2026

**Changed**

- **No leftovers.** A Let's Play's last part under 15 minutes now always joins
  the part before it, so every part from a recording stays in that
  recording's episode. Before, the splitter usually avoided a scrap but could
  still leave one (40 + 48 + a 10-minute scrap after a long cutscene; now
  40 + 58).
- A short last part stays only when joining it would make a part over 60
  minutes and no split can move to make room. The plan's notes then say why.
- In the Part Planner, a drag or a new split that leaves the last part short
  is still made, and the message points it out ("× joins it to Part 4").

**Removed**

- Carrying a leftover to the next session's Part 1 (in the original plan, never
  built). The creator opens every recording on an intro and makes all its parts
  from it, so it's not wanted. The setting is gone from `settings.yaml`.

All of 2F is tested on real footage next Saturday.

## 0.20.0 — Phase 2F-2: The Part Planner — 11 October 2026

**New**

- **Move where a Let's Play's parts end**, on Review's parts bar: drag a
  split's handle and it snaps to the nearest safe break (a loading screen, a
  menu, a pause in talking, where a quest ends), never mid-word, mid-talk or
  mid-cutscene. Double-click the bar to add a split; × joins two parts.
- A split in the middle of a quest is drawn red, and the Ends on column names
  the quest. Times under the handles are in the recording, like the table.
- A part is never over 60 minutes or under 2: a move that would break that
  is refused, saying why. Undo and Redo cover every move.
- New plans keep their safe breaks; a plan made earlier finds them the first
  time you move a split (a few seconds).

Tested on a copy of the library; the creator tests it on real footage next
Saturday.

## 0.19.0 — Phase 2F-1: Story missions in Let's Plays — 11 October 2026

**New**

- **AI-Editor reads Dawnwalker's quest tracker** (top right: the time of day,
  then the quest you're following) every 15 seconds, the first time you make
  an episode's plan: about 4-5 minutes for a 2-hour episode, once, shown in
  Jobs as "Reading the quest tracker". It reads the preview copy, offline,
  on the processor only.
- **Parts aren't split in the middle of a quest** if it can be helped: a part
  ends just before a quest begins, or runs on to its end (up to 45 minutes,
  60 at most). Every quest the tracker shows counts; "Rescue your family"
  doesn't. Just after a quest ends, and as the time of day changes, are good
  places to end. A quest longer than an hour still has to be split: that part
  is flagged with the quest's name.
- **Review shows what each part ends on**: "loading screen · quest ends ·
  hook", or a warning when a part ends mid-quest. The plan's notes list the
  quests found.

On your 10 October episode, the old split ended Part 2 a minute and a half
into "What Moves the Dead" and Part 4 halfway through "Who Pulls the
Strings"; now all five parts end between quests.

**Installed:** RapidOCR, a small offline text reader (without its second
copy of OpenCV, which would clash with the one already used).

## 0.18.0 — Phase 2D-2: Fixing captions — 11 October 2026

**New**

- **Fix captions in Review**, line by line: click a clip, and its caption
  lines appear under the player, each with its time. Click a line to hear
  it, fix its words and save. Each word keeps its own time, so the caption
  stays in sync with your voice.
- **A fix goes everywhere** that moment is used: every video and Short with
  it, "You said" in Clips, and what the AI writes. The word as first heard is
  kept: **Put back the original** brings the line back as it was.
- **Hide a line**: never shown as a caption, but its words stay in the
  transcript for the AI and titles. **Show this line** brings it back.
- **Remember a fix**: after changing one word, AI-Editor asks whether to
  always write it that way, saying how many other places that would change.
  Yes fixes it in every stream now and in new ones as they're analysed.
  **Settings → Captions and sound** lists them; **Forget this fix** puts the
  words back.
- **Undo and Redo** cover caption fixes, hides and put-backs.
- Analysing a stream again keeps your caption fixes and hidden lines.
- Captions stay off by default: tick **Burn in captions** to see them.

This finishes Phase 2D, the full Review screen.

## 0.17.1 — Fix: your plans from different streams, and a shorter plan list — 10 October 2026

**Fixed**

- **Making a highlight plan threw away the unrendered draft from another
  stream** of the same game (your 8 October plan went when you made the 9
  October one). Now a new plan only replaces a draft from the same stream(s);
  the same goes for Let's Play episodes. Rendered plans are never replaced.

**New**

- **The stream's date in every plan's name**: "League of Legends highlights ·
  8 Oct stream · Highlights, 15.8 min, draft". Shorts say which stream they're
  from too. The From column in Review dates each clip by when the stream
  started.
- **Delete this plan** in Review, beside Video plan, after you confirm. Only
  the plan leaves the list (and its Undo history): a finished video stays in
  your output folder, its clips stay marked as used, and your clips, ratings
  and what AI-Editor learns all stay. AI-Editor never deletes a plan by itself.

## 0.17.0 — Phase 2D-1: Drag, the length bar, and Undo — 10 October 2026

**New**

- **Drag clips to reorder them** in Review: grab a row and drop it where you
  want it; a line shows where it lands. The teaser always opens the video, so
  it can't be dragged. Move up/down, Move to # and Sort by time are still there.
- **The length bar** above the list: one block per clip, as wide as the clip
  is long, against your target (about 10 minutes for highlights, never below;
  60 seconds at most for a Short; 25-35 minutes a part for a Let's Play). The
  teaser is amber, a clip with a slow-motion replay purple. Click a block to
  pick that clip, the same as clicking its row.
- **Undo and Redo** for every change in Review: removing, moving, dragging,
  the teaser, adding a clip, adjusting a cut, the effect switches and ticks,
  between clips, music, a Short's layout. The button says what it would undo.
  Each video keeps its own history after AI-Editor closes. Undoing an adjusted
  cut puts the clip in the library back too. An undone change is marked
  undone in what AI-Editor keeps for learning, so a misclick teaches nothing.
  The upload text is never undone.
- **⭐ on your marked clips**: a clip with your Stream Companion mark in it has a
  star in front of its Why, in Clips and in Review.

**Fixed**

- **Your Stream Companion marks from 6-9 October were missing from those
  streams' clips.** The Companion connected to OBS just after recording began,
  so it didn't hear the file's name, and the backup match by time read the
  date inside the .mkv, which OBS writes when recording *ends*: two hours out.
  Recordings now also match by the file named when recording stops, by the
  time in OBS's file name, and by the file's dates less its length. At start,
  AI-Editor links any recording that now matches and cuts its clips again
  with your marks in (your ratings, adjusted cuts and used clips stay): 69
  marks found across 6, 7, 8 and 9 October.
- **Importing now always says whether a Companion log was found**, with your
  marks counted, or that none matched; the line above the Clips list says the
  same for each recording.
- **Your mark beats a 👎 on a clip that didn't have it**: those streams were
  rated before their marks were linked, so a thumbs-down on a badly cut,
  unmarked clip no longer keeps your marked moment out.

## 0.16.0 — Phase 2C-2: Punch-in zoom and slow-motion replays — 10 October 2026

**New**

- **Punch-in zoom**: on your reactions (you shouting or laughing at a moment
  you marked, or at a big League moment), the picture pushes in to 1.2 times
  towards the middle, holds and eases back out, in under a second. The shake
  stays on the action. The video doesn't get longer.
- **Slow-motion replays**: after your biggest moments (multikills, aces and
  steals, or a marked moment where the game's sound jumps hard), the moment
  plays normally, then its last 3 seconds again at half speed, and the clip
  carries on. You hear the game slowed with its pitch kept, without voices;
  the stream's music carries on underneath and picks up from there, so the
  song never jumps or repeats. 1.5 seconds after the moment, never mid-word.
  One per clip at most, one every 2 minutes, one per Short; a Short never
  goes over 60 seconds for one. Each makes the video 6 seconds longer, and
  chapters, Review's times and the Each effect list allow for it.
- Both are **off by default**, like every effect: tick **Punch-in zoom** or
  **Slow-motion replay** for a video in Review, or in Settings → Effects.
  Let's Plays get neither.

**Changed**

- Freeze frames, first planned for 2C-2, are left out: your choice.

## 0.15.1 — Deleting streams once their videos are made — 10 October 2026

**Fixed**

- **New highlight videos leave out recordings whose video you deleted**, and say
  so ("Left out 3 recordings whose video was deleted"). Before, a plan could pick
  their clips, look fine in quick preview, and then fail at Render.
- Shorts and Let's Plays can't be started from a deleted recording, and explain
  why. The Library shows it as **Video deleted (kept for learning)**, and the
  Create video lists mark it **(video deleted)**. Its clips can still be watched,
  rated and adjusted, and everything you taught AI-Editor with it is kept.

**New**

- **Proof that AI-Editor never deletes your recordings**: a test lists every
  place it deletes anything (all its own temporary and working files) and fails
  if a new one appears until it's checked. Manual 23.4.

## 0.15.0 — Phase 2E-2: League events in your videos, and adjusting a cut — 10 October 2026

**New**

- **League's events pick your clips** (recordings where the Stream Companion
  logged the match). Any kill of yours lifts the fight leading up to it;
  multikills, aces, your team's objectives and team fights more. Your deaths
  only count when you react to them. A clip doesn't end while champions are
  still dying, and never runs across a match's start or end.
- **Downtime skipped**: queue, champion select, loading and the post-game lobby
  are never picked unless you marked them. A gap over 12 minutes between
  logged matches is left alone (more likely a match the Companion missed).
- **Reasons you can read**: "Kill", "2 kills", "Triple kill", "Penta kill",
  "Ace", "Baron steal", "Victory" in Review and the Clips tab; a clip's
  details list its League events with their times.
- **Effects on League's big moments**: your multikills, aces and steals get a
  shake and boom on the exact second; a mark with a kill or objective in it
  puts its effect on that. Single kills alone get none. Still off unless you
  tick them, like every effect.
- **Shorts**: multikills, aces and steals are suggested right after your
  Numpad - moments. The local AI is told the real events for titles and
  chapters.
- **Adjust the cut** in Review (brought forward from Phase 2D, your ask):
  click a clip, then move its start and end by 1 or 5 seconds, type a time,
  or use Start here / End here from the paused player; watch 30 seconds
  either side to see what was cut off, then save. Never mid-word. The clip in
  the library keeps your cut, and every adjustment is kept for learning.

**Changed**

- **Shorts keep the build-up**: they open 25 seconds before their moment
  (was 8, which started five of your Shorts after the play you were reacting
  to), and a Short from your mark runs from 45 seconds before the press to 5
  after (was about 20 after).
- **Burned-in captions on Shorts are off by default**, like every video.
- **AI-Editor's video work runs at below-normal priority**, so your desktop,
  browser, OBS and games always come first (your desktop froze while doing
  several things).

**Fixed**

- Save the new cut ignored times typed without pressing Enter.

## 0.14.0 — Phase 2E-1: League events from the game — 10 October 2026

**New**

- **The Stream Companion logs your League matches.** While you record or
  stream on your League scene, it asks League's own read-only Live Client
  Data API on this PC (Riot's official feature; no key or account) what
  happened: your kills, deaths and assists, double to penta kills, aces,
  first blood, Dragons, Baron, Herald, Voidgrubs, Atakhan, turrets and
  inhibitors (and steals), and whether you won. Each event is placed at its
  exact second in the recording, from the game's own clock.
- **A League line in the Companion**: "waiting for a match", then "match
  running: 4/1/6, double kill, 1 objective". Tested in the practice tool:
  "Match started" landed 62 seconds into the recording, right where League
  loaded.
- **After import**, a summary of the matches, and in the Library under the
  recording's details, **Every League event** with its time in the
  recording ("0:35:03 · Double kill"), to check against the video.
- The Companion checks the answer really comes from League (Riot's
  certificate), only asks on your League scene or a non-game one, and picks
  up where it left off if it's restarted mid-match. Switch it off with
  `companion.league_events: false`.

**Changed**

- The game-safety test now allows exactly one more connection for the
  Companion: League's API at 127.0.0.1:2999, read only. Manual 8.3 and 27.

## 0.13.0 — Phase 2C-3: Your stream's music, and sliding between clips — 10 October 2026

**New**

- **The music from your stream is in your videos**: the DMCA-free music you
  play on Spotify, as viewers heard it, in highlights, Shorts and Let's
  Plays. It's lowered only where it would cover you or a Discord friend
  talking, and fades in and out at each cut so the song doesn't jump
  between clips. Your separate mic, game and Discord tracks are still used,
  so the marker-click removal and the Discord switch work as before. Switch
  it off for one video in **Review → Finish it**, or for every video in
  **Settings → Captions and sound**.
- **Spotify on its own track (OBS track 5).** Recordings made since you set
  it up use it directly; older ones get the music by taking everything else
  out of the mixed track (you listened: "sounds good"). Manual 7.3.
- **Sliding between clips**, like a sliding door: the next clip slides in
  over the last one from the right, easing in and settling, while the sound
  crossfades. Pick **Slide** under **Between clips** in Review, or as the
  default in **Settings → Effects**. Hard cuts stay the default. Each slide
  makes the video 0.8 seconds shorter; chapter times allow for it.
- **A switch for every effect moment**: once effects are ticked for a video,
  **Each effect** in Review lists each moment ("Clip 5 at 2:48: shake +
  boom"). Untick one to leave just that moment out.

**Changed**

- The whoosh between clips, tried first, is gone: you preferred the slide.
- The import guesses track 5 is your music.

## 0.12.0 — Phase 2C-1: Effects on your marked moments — 10 October 2026

AI-Editor can now add effects to the moments you marked with the Stream
Companion, by itself. They're **off until you tick them** in Review: in the
first tests their timing felt random, so they stay optional until Phase 2E,
when League's own events (kills, objectives) place them too.

**New**

- **Flash, screen shake and sound effects**, each with its own switch: in
  **Review → Finish it** for one video, in **Settings → Effects** for every
  new one.
- **Only on your marks.** Each Numpad + or − press gets one effect, on the
  biggest moment in the 20 seconds before it: a sudden jump in the game's
  sound gets a shake and a boom, you shouting gets a flash and a hit. Clips
  you didn't mark get none, and a bump at the mic never counts.
- **Lined up to the instant** the sound starts, to the hundredth of a
  second. Captions stay still on top of them.
- **Sound effects at the right volume**: matched to the moment they're on,
  never lost under it.
- **Your own sounds**: **Settings → Effects → Open my sound effects folder**,
  then drop files into its boom, hit or whoosh folders. YouTube Studio's
  Audio Library has free sound effects for YouTube videos. Until then
  AI-Editor uses simple ones it makes itself.
- Quick previews include the effects, and a kept preview says when you've
  changed the switches since.
- Effects add no time to a render.

**Fixed**

- **Rendering a video again while the last one was open** (in VLC, or
  playing in Review) stopped at 100% with "Access is denied". Now the old one
  is kept and the new one is saved beside it as "(2)", so you can compare.

**Changed**

- The phase order: music and the Review switches (2C-3) come next, then
  League events (2E), then zooms, slow-motion and freeze frames (2C-2) and
  the full Review screen (2D), built on those events. Nothing is dropped:
  the README lists every phase still to do.

## 0.11.1 — Phase 2B fix: the Stream Companion stays open — 5 October 2026

**Fixed**

- **The Stream Companion could close by itself mid-stream.** Every second it
  saves a small status file that the app window reads; if both happened at
  the same instant, Windows refused the save and the Companion closed. It now
  tries again a moment later, and anything else unexpected is written to the
  log file while it carries on.
- **Ctrl+C no longer stops it.** Copying something while its window had focus
  closed it. Stop it with **Stop** in AI-Editor, or by closing its window.
- **Clicking inside its window no longer pauses it.** Windows freezes a
  terminal program while you select text in it, which would hold up your
  markers; that's switched off for the Companion.

## 0.11.0 — Phase 2B: Shorts — 4 October 2026

AI-Editor now makes vertical Shorts (1080×1920) from your streams: one file
that works on YouTube Shorts, TikTok and Instagram Reels.

**New**

- **Shorts**, in **Create video**: pick a stream and get up to five suggestions,
  each 15–60 seconds. Your Numpad − moments always come first, then the clips
  you liked, then the AI's picks that make sense on their own. Each one opens
  in **Review** like any other video.
- **Zoomed centre or whole picture**, per game and switchable per Short.
  League, Tarkov and Wardogs zoom in (League a little less, at 65%, so the
  fights stay in frame); Dawnwalker shows the whole picture over a blurred
  copy of itself.
- **Captions made for phones**: big, a short phrase at a time, with the word
  being said lit up in yellow.
- **Quick previews show the apps' buttons**: faint red areas mark where
  YouTube, TikTok and Instagram put their text and buttons, so you can see
  nothing important is hidden. They aren't in the finished Short.
- **Previews are kept.** Each Short keeps a preview per layout, and every plan
  shows its last preview when you open it in Review, saying if the plan has
  changed since.
- **Publish for Shorts**: short titles, a one-line description and hashtags.
  Paste a long video's YouTube link in its Publish section and the Shorts from
  it say "Full video:" with that link.
- **Spoiler check**: Shorts from story games (Dawnwalker) are flagged so you
  can check they don't give the story away.
- **A spot for a facecam**, ready for when you get one: a "facecam on top"
  layout switches on per game in the settings.

**Changed**

- A clip used in a Short can still go in a highlight video, and the other way
  round: the **Used** column in **Clips** says which.
- Shorts are mixed to -14 LUFS, YouTube's own level, so they sound as loud as
  other Shorts.

## 0.10.0 — Phase 2A: The local AI and publish prep — 4 October 2026

AI-Editor now has an AI of its own, running on your graphics card through
Ollama: nothing is sent online. It watches every clip and helps you upload.

**New**

- **The AI says what each clip is.** In **Clips**, every clip gets a rating out
  of 10 and a one-line summary ("Teamfight engagement and multi-kill"). Click a
  clip for the AI's reasons, tags, and whether it would work as a Short. Clips
  are rated at the end of each analysis (about 2 minutes per stream); **Rate
  with AI** does it for recordings analysed before.
- **The rating doesn't pick your clips yet.** On your League stream the AI
  agreed with your 👍/👎 about half the time, against about 80% for the usual
  score, so it's shown but not used. **Settings → AI** keeps count per game,
  and says when there are too few ratings to tell.
- **Publish**, at the bottom of **Review**: 3–5 plain, descriptive title ideas
  (Let's Plays keep "The Blood of Dawnwalker - EP 2 Part 1: ..." and avoid
  spoilers), a description with YouTube chapters that match the video exactly,
  tags, and the 6 best thumbnail frames as full-size PNGs. Copy buttons on
  each; **Keep my changes** saves your edits; a .txt with all of it is saved
  beside the finished video.
- **Your Twitch link and stream times** go under every description
  (**Settings → Publish**).
- **Keep the music from your stream** (Spotify), in **Settings → Captions and
  sound**. Off by default: commercial music usually gets YouTube videos claimed.
- **Use clips already in a video**, in **Create video**: make another video
  from streams whose clips you've already rendered.
- **Settings → AI**: whether it's ready, **Download model** (Gemma 4 12B,
  about 8 GB, once), switch it off, and how much its rating counts.

**Changed**

- Making a highlight video from streams whose good clips are all in rendered
  videos now says so, and what to do, instead of "no clips passed the quality
  bar".
- If a game is using the graphics card, the AI stops after one slow answer
  (instead of grinding on and slowing the game) and **Resume** carries on later.

## 0.9.0 — Phase 1H: The app window — 3 October 2026

AI-Editor now has a window: everything is done with buttons, from importing a
recording to rendering the finished video. Double-click the **AI-Editor**
icon on your desktop. It opens in your browser, on this PC only: nothing goes
online. Closing the black window quits it.

**New**

- **Jobs**, at the top: importing, analysing, rendering and previews run one
  at a time in the background, with a progress bar per step. **Pause** stops
  them (say, before you stream), **Resume** carries on, and finished steps are
  never repeated. Closing AI-Editor mid-job also stops FFmpeg and Twitch
  downloads, instead of leaving them running unseen.
- **Library**: every recording, its status, clips and chat, with Analyse (or
  resume), Watch the preview copy and Show in Explorer.
- **Import**: new recordings in your raw folder are listed, ready to pick, or
  Browse. A file OBS is still writing isn't imported. Twitch VODs: paste the
  link, Check, Download and import.
- **Clips**: every clip, best first. Click one to watch it in the window. A
  **👍 puts the clip in your next highlight video**, whatever its score; a 👎
  keeps that moment out. A line counts your ratings and how many minutes of
  video your 👍 clips make, and each clip shows its length once trimmed.
- **Create video**: highlights (all your streams, one game, or chosen
  streams) or a Let's Play episode, in one click.
- **Review**: the plan, clip by clip, each playable in the window.
  - Choose the teaser, from a clip or an exact moment.
  - **Remove** a clip and the next best fills its place, so the video never
    falls under its length.
  - **Add** any clip that isn't in it, 👍 ones first.
  - Move clips up, down or straight to a number. **Sort by time** puts them
    back in order.
  - **Quick preview** of the whole video in seconds; **Render** (captions on
    or off), **Open the finished video**, and **Export to DaVinci Resolve**.
  - Let's Plays show their parts, with the episode number filled in.
- **Storage**: free space on each drive, what each recording uses, and **Free
  working files** (about 1–2 GB per stream, nothing lost). Your recordings are
  never deleted.
- **Settings**: your folders and the main options for highlights, captions,
  Let's Plays, the Stream Companion and Twitch. Saved on this PC only, beside
  your OBS password, and they work straight away.
- **Stream Companion** panel: Start, Stop, and what it's doing (OBS, live or
  recording, game, markers), live. It runs in its own window and carries on
  if you close AI-Editor.

**Changed**

- **Highlights are in the order things happened**, with the teaser's moment
  saved for the end, like your own League layout. The length you set is now
  the least a video will be: it can run over, never under while good clips
  are left.
- **No clip runs into "BRB" or your ending screen.** Each one stops half a
  second before you switched scene (when the Stream Companion was running),
  and a moment during "BRB" isn't used.

## 0.8.0 — Phase 1G: Finished videos — 3 October 2026

AI-Editor now makes finished videos, start to end: full quality from your
original recordings, ready to upload.

**New**

- **`ai-editor render <plan>`** renders a plan at your recording's own size
  and frame rate (1080p60), on the graphics card: a 10-minute highlight in
  about 3 minutes, a half-hour Let's Play part in about 7. `ai-editor plans`
  numbers your plans, so `ai-editor render 2` is enough.
- **Clean joins.** Picture and sound are exact to the frame at every cut, and
  the sound fades over a few thousandths of a second so nothing clicks.
- **Sound for YouTube.** Each video is turned up or down in one go toward
  YouTube's level (-14 LUFS), keeping your stream's balance between loud and
  quiet. Only the loudest peaks are held down, by 3 dB at most, so nothing
  distorts; a very quiet recording ends up a little under YouTube's level.
- **Music on stream stays out.** Recordings with separate mic, game and
  Discord tracks are rebuilt from those, leaving Spotify (track 1 only) out
  of your uploads. Older recordings use the mixed track, as streamed.
- **Marker beeps removed.** The Companion's click that reached your mic on
  26 Sep is found near each marker and filtered out, leaving your voice
  untouched.
- **Captions, as an option** (`--captions`, off by default): bold white with a
  black edge, placed clear of each game's own on-screen text. Only your
  words: a Let's Play from a recording without a separate mic track gets
  none, so the characters' lines are never captioned. A captioned video is
  saved beside the plain one.
- **Let's Play parts** render in one go, named ready to upload ("The Blood of
  Dawnwalker - EP 1 - Part 2"); `--part 2` for one. A title card ("Ep 1 –
  Part 2") is available in Settings, off because the YouTube title says it.
- **`--teaser-at 6:36-6:42`** picks the teaser by its time in a video you
  watched: that moment opens the video, and its clip closes it.
- **`ai-editor export <plan>`** saves a DaVinci Resolve timeline and a
  subtitle file, for the odd video you'd rather fine-tune by hand.

**Fixed**

- Captions and preview subtitles join split words: "anti-air", not
  "anti -air".

## 0.7.0 — Phase 1F: Highlights and Let's Plays — 27 September 2026

AI-Editor now plans whole videos: 10-minute highlight compilations from your
streams, and Let's Play episodes trimmed and split into parts.

**New**

- **`ai-editor highlights`** builds a highlight video from your best unused
  moments, with a quick preview to watch. With no options it takes every
  stream, whatever you played (Wardogs, League, a Tarkov switch halfway
  through); `--game Wardogs` keeps to one game. Let's Play games
  (Dawnwalker) are never used. It fills 10 minutes from the oldest stream
  first ("4 minutes from the previous and 6 from the next"), never pads with
  weak clips, opens with a short teaser and ends on that moment in full.
- **The teaser is your call.** A moment you marked with Numpad + comes first;
  otherwise the one you reacted to most; `--teaser 5` picks clip 5 yourself.
- **`ai-editor approve`** marks a video final, so the next one carries on
  with the clips that are left. `ai-editor plans` lists them.
- **`ai-editor letsplay <recording>`** trims an episode and splits it into
  parts of about 30 minutes. It cuts loading screens, menus you don't talk
  over, and silences over 20 seconds (keeping 3 seconds either side). It
  never cuts anyone talking, a fight (swords included), a cutscene, or
  mid-word, and nothing is sped up. Parts end at a loading screen or a pause,
  preferably right after a strong moment. A cuts reel and a splits reel let
  you check every cut and every split in minutes; `--parts` previews each
  part in full. EP 1: 126 minutes became four parts of 29-33 minutes.
- **Cutscenes are recognised** because your HUD disappears. AI-Editor learns
  where the HUD is from each recording by itself.
- **The Companion knows which game you're on** from your OBS scene, so a
  mixed stream's clips each carry the right game.
- **Marker keys work inside League.** League switches other programs'
  hotkeys off while it's in front, so the keys are now caught by OBS itself:
  run `ai-editor setup-obs --markers` once and bind them in OBS (manual 7.4a).

**Better on your footage**

- **Fights keep their ending.** When a moment is too long for a highlight,
  a fight is trimmed from the front, so the kill stays in.
- **Short black screens stay.** A crash or death blackout you talk through
  is part of the moment; only 10 seconds or more counts as a loading screen.
  A blinking effect no longer chops clips into 4-second pieces.
- **No opening mid-sentence.** A clip that would start on "Chris, you ready…"
  now starts on "Hey Chris, you ready…".
- **Markers don't drown out everything else.** Eight markers used to leave
  exactly eight clips from a whole stream; now they go on top and the rest
  keep their ranking.
- **Game names are spelled right** ("talk of" → Tarkov, "war dogs" → Wardogs)
  by a spelling list you can add to. Hinting the names to the speech
  recognition was tried and dropped: it made it "hear" the hint, and "Thank
  you for watching", over game noise.
- The picture check (black screens, menus, cutscenes) is about 20 times
  faster: 37 seconds for a 2-hour episode.

**Fixed**

- **The marker click reached your stream** through your microphone on 26
  September. It's now off by default and should stay off; nothing in OBS's
  settings could have shown the problem.
- Going back to an older setting could reuse a result made with a newer one.

**Known limits** (later phases)

- Story missions aren't protected yet: reading "quest started / completed"
  off the screen comes with the game profiles in Phase 2.
- Part numbers don't yet carry on across episodes, and a short leftover
  isn't yet carried to the next session (the series manager).
- EP 1 has one mixed audio track, so it can't tell your silence from the
  game's. Recordings with separate tracks will trim more accurately.

## 0.6.0 — Phase 1E: Scoring and clips — 26 September 2026

AI-Editor now picks your best moments and cuts them into clips you can watch.

**New**

- **`ai-editor score <recording>`** ranks the best moments in a recording and
  says why each one scored: your markers, laughter, shouting, gunfire, chat,
  loudness.
- **`ai-editor clips <recording>`** cuts those moments into clips of 15–90
  seconds, and `--export 10 --open` saves the best 10 as small videos with
  subtitles and opens the folder. Clips are made automatically at the end of
  every analysis, in about 2 seconds.
- **Clean edges.** Each clip starts 30 seconds before the moment, so the
  build-up is there, and ends once the reaction finishes. It never cuts
  anyone off mid-word, and never opens on or runs into a menu, loading screen
  or respawn screen.
- **Scene detection** is a new analysis step (about 3 minutes per 2 hours).
  Re-analysing an older recording runs only this step.
- Clips you rate, pin or use in a video are never replaced when clips are
  rebuilt (ready for the review screen in Phase 1H).
- Everything is tunable under `scoring` and `clips` in Settings, and changes
  take effect in seconds, without re-analysing (manual chapters 11.1b, 11.1c
  and 24).

**Tuned on your footage**

- **Your markers count most**, and they count backwards: you press after the
  good bit, so a press lifts the minute before it.
- **Funny beats loud.** On the Wardogs stream the moment that won on loudness
  alone was ordinary; the ones you picked out had laughter in them.
- **A fight and a reaction together beat either alone.** Every clip you liked
  had both; every one you rejected had only one. Of the 14 clips you judged,
  the new top 5 are all keepers and 6–10 are all the ones you rejected.
- **Random shooting isn't a firefight:** gunfire is judged over 15 seconds.
- **Cutscenes don't chop clips.** Dawnwalker's cutscenes cut between camera
  angles every few seconds; those no longer count as scene changes that stop
  a clip. Neither does getting downed mid-fight.

**Fixed**

- Clip preview folders no longer have a `#` in their name, which broke
  typing the path into PowerShell.

**Known limits** (later phases)

- Spectating after you die sounds like a fight, so it can still score. The
  Wardogs game profile (Phase 2) will recognise the death and spectator
  screens.
- Long clips can take a while to reach the punchline, and some hold several
  jokes. Trimming and splitting them is the video recipes' job (Phase 1F,
  and Shorts in Phase 2).

## 0.5.0 — Phase 1D: Stream Companion — 20 September 2026

AI-Editor can now watch OBS while you play, and you can mark great moments as
they happen.

**New**

- **`ai-editor companion`**: a small window you leave open while you stream or
  record. It logs when OBS starts and stops recording and streaming, reconnects
  by itself if OBS closes, and uses next to no computer power.
- **Marker hotkeys:** **Numpad +** marks a moment, **Numpad -** marks one that
  would make a good Short. A quiet click confirms it. Markers are the strongest
  signal AI-Editor has, because you chose them yourself.
- **The click can never reach your stream.** Before playing it, the Companion
  asks OBS what it is capturing, and stays silent if a Desktop Audio source
  would pick it up. `ai-editor companion --test-sound` plays both sounds so you
  can check you'll hear them.
- **Your markers become moments.** Importing a recording matches it to the
  session that produced it — by the file OBS was writing, or by time if the
  file was renamed or converted — and your markers appear at the top of the
  moments list.
- **Chat lines itself up.** The Companion logs how far into the stream your
  local recording began, so `ai-editor attach-chat` no longer needs
  `--starts-at`.
- **`ai-editor sessions`** shows the session log, and `ai-editor sessions
  <session>` shows one in full.
- `ai-editor setup-obs` connects to OBS. The password is saved only in
  `config/settings.local.yaml`, which is never committed, and is only stored
  once OBS accepts it.
- `ai-editor doctor` now has an OBS line.
- Four new error messages (E050–E053) in manual chapter 25.

**Your game accounts**

The Companion talks to OBS and nothing else. It never looks at which programs
are running, never touches a game, and never presses keys for you. Its hotkeys
use the same standard Windows feature Discord and OBS use, not a keyboard hook.
A test now scans every line of AI-Editor and fails the build if anything that
could touch a game ever appears (manual chapter 27).

**Fixed**

- Closing the Companion during a recording and starting it again no longer logs
  that recording twice.
- The confirmation click was too quiet to hear. It is now louder and a little
  longer, and the Short-worthy one is two rising blips.

## 0.4.0 — Phase 1C: Twitch VODs, chat, and voice separation — 19 September 2026

Your stream footage and Twitch chat can now come into AI-Editor.

**New**

- **Download a VOD straight from Twitch:** `ai-editor import-twitch <link>`
  downloads a public VOD into your Raw footage folder, imports it, and attaches
  its chat. Links from your Twitch dashboard work too, and the game is read
  from Twitch.
- **Import a VOD you downloaded yourself:** `ai-editor import "<file>" --vod
  <link>` (or `--source twitch --game Wardogs` without a link). Useful for
  private VODs, which Twitch won't let AI-Editor download.
- **Chat activity:** `ai-editor attach-chat <recording> <link>` adds a VOD's
  chat to any recording, including a local recording made while streaming.
  Chat bots such as StreamElements are ignored, because they aren't viewers.
- **Voice separation:** on a recording with one mixed audio track, AI-Editor
  can split the sound into voices and everything else before analysing it. On
  by default for Twitch VODs; 2 hours take about 2 minutes. The separated
  sound is only used for analysis, never in your videos.
- **VOD expiry warnings:** Twitch deletes VODs after a while; AI-Editor warns
  when one is within 3 days of going.
- `ai-editor library` shows whether each recording is local or from Twitch,
  and whether it has chat.
- Three new error messages (E040, E041, E042) in manual chapter 25.

**Measured on your footage**

- Voice separation on EP 1: 2.2 minutes for 2 h 06 m, 2% more words, one fewer
  invented phrase. A modest gain for a Let's Play, which is why it stays off
  for local recordings by default; your separate OBS tracks already do better.
- The voice detector was checked on all three kinds of audio. It stays on for
  clean mic tracks only: on game-heavy audio it cut real short reactions
  ("Oh, fuck.", "No, no, no!").

**Fixed**

- Re-analysing a recording no longer wipes its chat activity.
- Technical error text from FFmpeg or the Twitch downloader can no longer
  appear on your screen; it goes to the log file only.

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
