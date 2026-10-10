# Changelog

Written so the creator can understand what changed, not only the engineer
(specification section 14.3).

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
