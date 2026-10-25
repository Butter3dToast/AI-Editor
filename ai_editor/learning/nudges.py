"""Effect nudges (Phase 3A-3a): "suggested 24 times, you used 2. Change that?"

Spec section 7.10: "if the creator repeatedly deletes an effect type, lower its
frequency and ask". Review only suggests effects, none ticked (2H-1), so what
says "not this one" is an effect suggested again and again and left unticked.
Each render writes down what was suggested and used (effects.log_used); once an
effect has been suggested often enough and hardly used, Review asks.

Nothing changes unless the creator answers, and an answer only ever cuts down
suggestions: effects are off by default and stay that way. Both answers are
Settings (effects.only_biggest, effects.not_suggested), changed back there.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from ..config import Settings, save_local_settings

LAST_VIDEOS = 10    # looks at the videos suggesting it, at most this many back
MIN_VIDEOS = 3
MIN_SUGGESTED = 10
MOSTLY_UNUSED = 0.15
ASK_AGAIN_AFTER = 10   # videos, after any answer
ANSWERS = ("biggest", "never", "keep")


@dataclass
class Nudge:
    kind: str
    videos: int
    suggested: int
    used: int

    @property
    def text(self) -> str:
        from ..effects import LABELS

        name = PLURALS.get(self.kind, LABELS[self.kind].lower())
        return (f"In your last {self.videos} videos AI-Editor suggested **{name}** "
                f"{self.suggested} times, and you used {self.used}. Change that?")


PLURALS = {"flash": "flashes", "shake": "screen shakes", "sfx": "sound effects",
           "zoom": "punch-in zooms", "replay": "slow-motion replays"}


def _videos(conn: sqlite3.Connection) -> list[tuple[int, dict]]:
    """(feedback id, tally) per rendered video, newest first; a video rendered
    again counts once, as it was last."""
    latest: dict[str, tuple[int, dict]] = {}
    for row in conn.execute("SELECT id, plan_id, detail_json FROM feedback WHERE "
                            "action = 'effects_used' AND undone = 0 ORDER BY id"):
        latest[row["plan_id"]] = (row["id"], json.loads(row["detail_json"] or "{}"))
    return sorted(latest.values(), key=lambda v: -v[0])


def _answered(conn: sqlite3.Connection) -> dict[str, int]:
    """{effect: the feedback id of the last answer about it}."""
    found = {}
    for row in conn.execute("SELECT id, detail_json FROM feedback WHERE action = 'nudge_answer' "
                            "ORDER BY id"):
        found[json.loads(row["detail_json"])["effect"]] = row["id"]
    return found


def effect_nudge(conn: sqlite3.Connection, settings: Settings) -> Nudge | None:
    """The effect most often suggested and left unused, if there's one to ask about."""
    from ..effects import KINDS

    videos = _videos(conn)
    answered = _answered(conn)
    found = []
    for kind in KINDS:
        if kind in settings.effects.not_suggested:
            continue
        since = [t for i, t in videos if i > answered.get(kind, 0)]
        if kind in answered and len(since) < ASK_AGAIN_AFTER:
            continue
        offering = [t for t in since if t.get("offered", {}).get(kind)][:LAST_VIDEOS]
        suggested = sum(t["offered"][kind] for t in offering)
        used = sum(t.get("used", {}).get(kind, 0) for t in offering)
        if len(offering) >= MIN_VIDEOS and suggested >= MIN_SUGGESTED and \
                used / suggested < MOSTLY_UNUSED:
            found.append(Nudge(kind, len(offering), suggested, used))
    return min(found, key=lambda n: (n.used / n.suggested, -n.suggested)) if found else None


def answer(conn: sqlite3.Connection, settings: Settings, kind: str,
           choice: str) -> tuple[str, Settings]:
    """Keep the answer, and the setting it means. Returns what to say, and the
    settings as they now are."""
    from ..effects import LABELS

    if choice not in ANSWERS:
        raise ValueError(choice)
    conn.execute("INSERT INTO feedback (ts, action, detail_json) VALUES (?, 'nudge_answer', ?)",
                 (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  json.dumps({"effect": kind, "answer": choice})))
    conn.commit()
    name = PLURALS.get(kind, LABELS[kind].lower())
    fx = settings.effects
    if choice == "keep":
        return (f"Kept as it is. AI-Editor won't ask about {name} again for "
                f"{ASK_AGAIN_AFTER} videos.", settings)
    field, said = (("only_biggest", f"{name.capitalize()} are now only suggested on the biggest "
                                    "moments")
                   if choice == "biggest" else
                   ("not_suggested", f"{name.capitalize()} aren't suggested any more"))
    now = list(getattr(fx, field))
    if kind not in now:
        now.append(kind)
    new = save_local_settings(settings.source_path, {("effects", field): now})
    return (said + ". To change it back: Settings → Effects → "
            + ("Only on the biggest moments" if choice == "biggest" else "Don't suggest") + ".",
            new)
