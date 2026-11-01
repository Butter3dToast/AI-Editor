# Phase 4F-1: Review in the new design (changing the cut)

For the designer: Review rebuilt from `mockups/Review.dc.html` (0.43.0), drawn by the
window itself. Captions, effects and music, rendering and publishing follow in 4F-2
and 4F-3.

| File | What it shows |
|---|---|
| `review-dark.png` | A clip on the stage: player, the trim buttons, details with Remove and More…; the length bar under it |
| `review-trim-dark.png` | After Trim end to here: the new cut waiting as "not saved yet", and More… open |
| `review-list-dark.png` | Scrolled down: the stage stays pinned; the tools under the list (sort, teaser from a moment, add a clip) |
| `review-light.png` | The first, light |

**The data is made up** (a demo library): no real streams, names or folders. The
picture is a test pattern standing in for a stream's preview copy.

What differs from the mockups, and why:

- **The stage is pinned** at the top while the rest scrolls, as in Clips (the creator's
  choice). The player is the browser's own, about half the window's height.
- **A trim isn't saved by itself**: it shows as "New cut … not saved yet" under the trim
  buttons, with Play the new cut, Put it back and Save the new cut.
- **More…** holds the rest of today's buttons for one clip: Use as teaser, Move to #,
  Watch 30 s either side, typed start and end.
- **The header** has Undo and Redo (each says what it would undo when pointed at), Quick
  preview, and "Today's Review" (opens the old screen on the same plan until 4F-2/4F-3).
  Render comes back to the header in 4F-2.
- **Above the stage:** the plan to show, Delete this plan and Delete several plans (both
  ask once more).
- **Under the length bar, tabs** (the creator's choice over the mockup's fold): Clips
  (Parts for a Let's Play), Captions, Effects & music, Publish.
- **The list** keeps the mockup's columns (# · From · At · Length · Why it's in) with a
  drag handle; the teaser can't be dragged, it always opens the video.
