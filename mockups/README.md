# UI mockups — the Phase 4 design target

Twenty-two artboards showing what AI-Editor should look like once it runs in its own
window: every screen in dark and in light, the Jobs rail in each of its states, and the
empty states. Build the window against these; `../packaging.md` covers the window and
installer themselves.

## Viewing them

Open any `.dc.html` file in a browser — each one is self-contained apart from
`theme.css` beside it. `Main.dc.html` (Library) is the entry point, and the sidebar links
work, so you can click through the whole dark set, and the whole light set from
`Library-light.dc.html`.

They also live on a design canvas where they sit side by side and can be commented on.
Ask Trent for that link; it is private until shared.

These copies differ from the canvas ones in two harmless ways, both marked in the files:
the canvas runtime's `support.js` tag is removed (it belongs to the design tool, not to
AI-Editor, and nothing here needs it), and `theme.css` ends with two rules that lay the
pages out correctly when opened as plain files.

## What is here

| File | Screen |
|---|---|
| `Main.dc.html` | Library (the entry artboard) |
| `Import.dc.html` | Import — local file and Twitch VOD |
| `Clips.dc.html` | Clips — the viewing stage and clip list |
| `Create.dc.html` | Create video |
| `Review.dc.html` | Review — stage, length bar, clip list |
| `Style.dc.html` | Style Profiles |
| `Rules.dc.html` | Rules |
| `Storage.dc.html` | Storage |
| `Settings.dc.html` | Settings |
| `Issues.dc.html` | Issues |
| `*-light.dc.html` | The same ten in the light theme |
| `Jobs.dc.html` | The Jobs rail: collapsed, mid-job, paused and stopped, overnight |
| `Empty.dc.html` | Empty states: no recordings, not analysed, no plan, clips used up, no profiles |
| `theme.css` | Every token and component, both themes |
| `canvas.json` | Where each artboard sits on the canvas; not needed to view them |

## The rules behind the design

- **Hairlines, not boxes.** Layers step up slightly in value and are separated by a 1px
  line. No stacked bordered cards, no shadows, no stripes.
- **Colour means state.** A coloured dot marks running, finished, waiting or stopped.
  Violet marks the selected row and the one primary button on a screen. Nothing is tinted
  for decoration.
- **The picture is the brightest thing.** On Clips, Review and Style the player is the
  widest element on the screen, with its controls under it and lists below that.
- **Space.** 36px around the body, 36px between sections, 24px inside panels, 50px table
  rows, 14px body text. If something looks cramped, that scale has been broken.
- **Ten tabs became a grouped sidebar** (Make / Teach it / App) with counts.
- **Jobs is a right-hand rail**, collapsed to a 52px strip when nothing is running and
  opening by itself when a job starts.

Theme follows Windows. The two themes are the same markup with a different token block on
`.app` — see the top of `theme.css`.

## Status

These are mockups: static HTML with no behaviour. Numbers, file names and clip
descriptions in them are made up for illustration. Where a mockup and the current app
disagree, the mockup is the target, except where the app does something the mockup
simply does not show yet.
