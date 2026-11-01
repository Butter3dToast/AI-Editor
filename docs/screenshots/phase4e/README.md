# Phase 4E: Create video in the new design

For the designer: Create video rebuilt from `mockups/Create.dc.html` (0.42.0), drawn by
the window itself.

| File | What it shows |
|---|---|
| `create-dark.png` | Highlights as it opens: Game, Length, Style profile, Which clips, the fold, What it will use, Make the plan |
| `create-ticked-dark.png` | Two streams ticked (only those are used) and the fold open |
| `create-letsplay-dark.png` | Let's Play: the episode picked in the list, its style profile picked by itself |
| `create-shorts-dark.png` | Shorts: every recording, with the creator's Numpad − marks in each |
| `create-ready-dark.png` | The note when a plan is ready while the creator is on another screen (here Clips) |
| `create-light.png` | The first, light |

**The data is made up** (a demo library): no real streams, names or folders.

What differs from the mockups, and why:

- **What it will use has tick boxes**: ticking streams is the browser's "Only these
  streams" (the creator's choice, 1 Nov). With none ticked it uses them all, oldest
  unused clips first, and the line beside the heading says which.
- **"Best score" became "Your 👍 · 🔖"**: each stream's scores are scaled so its best
  clip is 1.00, so on the creator's library the column read 1.00 on every row.
- **Which clips** pills say how many 👍 and 🔖 clips there are in the streams it will
  use, with a line under them explaining the choice.
- **The fold** holds "Use clips already in a video" and says how to pick particular
  streams (the ticks).
- **Let's Play and Shorts** (not in the mockups): the style profile, a line on what the
  plan does, then a list like the Library's to click the recording in. Let's Play shows
  about how many parts each makes and has "Show my streams too"; Shorts shows the marks.
- **When the plan is ready** it opens in Review if the creator is still on Create video;
  otherwise the note in `create-ready-dark.png`, with Open in Review.
- **Clips' Make a video** opens here with that stream ticked (a Let's Play recording
  opens on Let's Play with it picked).
