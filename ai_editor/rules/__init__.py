"""Your editing tips, as rules (spec section 7.5, Phase 2H-2).

You write a tip in plain English; the local AI turns it into one of the
kinds of rule AI-Editor knows (kinds.py), AI-Editor says back what it will do
in its own words (from the rule, not the AI's), and it's saved only when you
say so (store.py). A tip it can't act on is kept as a note.

What the creator chose (2026-10-11):

* A rule never switches effects or captions on: they're ticked in Review,
  "to ensure it was done/added correctly".
* A tip AI-Editor can't act on is kept as a note, marked as not changing the
  edit yet.
* Rules win over the style profile, which wins over Settings. A plan keeps a
  copy of the rules it was made with (like a style profile), so changing a
  rule never quietly changes a plan already reviewed.
* Two rules that disagree: the newer one wins, and the Rules tab says so.
* Rules apply by themselves to every new plan they match; switch one off to
  make a video without it.
"""
