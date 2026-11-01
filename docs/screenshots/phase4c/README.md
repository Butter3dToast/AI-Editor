# Phase 4C: Library and Import in the new design

For the designer: the first two screens rebuilt from `mockups/` (0.40.0), drawn by the
window itself rather than today's screens inside the frame.

| File | What it shows |
|---|---|
| `library-dark.png` | Library, dark: All · Streams · Let's Plays, search, the list with status dots, the picked recording's details below (Who's talking folded at the foot) |
| `library-light.png` | The same, light |
| `import-dark.png` | Import, From this PC, dark: the raw folder's new recordings with two ticked, so the button reads **Import 2** |
| `import-light.png` | The same, light |
| `import-twitch-dark.png` | Import, From Twitch, after **Check**: the VOD's details, Twitch deleting it soon in amber |

**The data is made up** (a demo library): no real streams, names or folders. The
demo's folder is shown as `F:\AI-Editor`, as in the mockups.

What differs from the mockups, and why:

- **Library:** the details panel has more than the mockup's four facts (length,
  video, where it came from, when imported, clips found), then the file's place,
  League events (folded) and **Who's talking** (folded): today's Library has all of
  these, and the creator wanted them kept. Sound and Chat moved here from the list,
  as in the mockup.
- **Library header:** "Analyse #N" is there for every recording except one whose video
  is deleted; it also carries on an analysis that stopped.
- **Import:** each new recording has a **tick box**, with **All** at the head of that
  column: the creator imports a week's streams at once (they still run one after
  another). A file OBS is still writing shows **Recording** instead, and one already
  queued **In Jobs**.
- **Import, More options** ("Sound tracks, Twitch link…") opens the game, sound tracks
  and Twitch link below the Import row. With several ticked they're greyed out, with a
  line saying why: they're for one recording at a time.
- **From this PC / From Twitch** is the `.seg` in the header, as in the mockup; the
  Twitch half adds the game box ("only if Twitch has it wrong") and a second tick,
  "Analyse straight after importing".
