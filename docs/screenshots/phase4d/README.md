# Phase 4D: Clips in the new design

For the designer: Clips rebuilt from `mockups/Clips.dc.html` (0.41.0), drawn by the
window itself.

| File | What it shows |
|---|---|
| `clips-dark.png` | Clips as it opens on a clip: the stage (player, rating buttons, the clip's details beside it), the filter and recording, the list |
| `clips-rating-dark.png` | After rating with the keys and moving down the list: the stage stays pinned at the top while the list scrolls under it |
| `clips-light.png` | The first, light |

**The data is made up** (a demo library): no real streams, names or folders. The
picture is a test pattern standing in for a stream's preview copy.

What differs from the mockups, and why:

- **The stage is pinned** (`position: sticky`) and the list scrolls under it: the
  creator rates a whole stream at a time and didn't want to scroll back up to the
  video after each clip.
- **The player is about half the window's height** (46vh), not the mockup's 440px
  minimum: on the creator's screen the bigger player pushed the buttons and list off
  screen. It's the browser's own video player (play, time, sound, fullscreen), so the
  mockup's transport bar with the mark isn't drawn separately.
- **A key hint** sits under the rating buttons: 1 👍 · 2 🔖 · 3 👎 · 0 clear · ↑ ↓ ·
  Space. A rating moves on to the next clip and plays it.
- **The details panel** has more than the mockup's five rows (At, In a video, Your
  taste, Game, Used), then labelled parts in the facts' small capitals: AI SAYS n/10,
  YOU SAID, and LEAGUE and USED IN when a clip has them. It scrolls on its own when a
  clip has a lot to say.
- **Above the list**, beside the mockup's filter and recording: "Streams whose video is
  deleted" (their clips can still be rated, to teach AI-Editor), and a line with the
  clip counts and how many minutes of video the 👍 clips make.
- **The header** keeps the mockup's Rate with AI and Make a video; its line says the
  recording, how many clips were found and how many aren't used yet.
