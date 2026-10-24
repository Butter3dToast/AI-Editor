"""How well AI-Editor knows you (Phase 3A-1): the measure Phase 3 is judged by.

Spec section 13, Phase 3: "done when the acceptance rate of suggested clips
measurably improves over several weeks of use". With "Only my 👍 clips" the
creator picks every clip in a video themselves, so a video's kept clips say
nothing. What does: where AI-Editor ranked the clips the creator rated.

- **Picked right**: of AI-Editor's top TOP clips in each stream (about a
  10-minute video's worth), the share of the rated ones that were liked.
- **Found your favourites**: of the liked clips, the share that were in its top TOP.

Liked is 👍 or 🔖 ("next video" is good, just saved for later). Weeks go by
when the stream was recorded, not when it was rated, so the line shows
whether new streams get better.

A clip's place in the list is written down the first time it's rated and never
changed, so learning (3A-2) can't flatter the numbers by re-scoring old streams.
Ratings from before 3A-1 take the places the list had when it first looked.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from ..config import Settings
from .taste import ranked

TOP = 20
RATED = ("thumbs_up", "thumbs_down", "next_video")


def ranking(conn: sqlite3.Connection, recording_id: int,
            settings: Settings | None = None) -> dict[str, tuple[int, int]]:
    """Each clip's place in the recording's list, best first: {clip id: (place, of)}.
    The order of the Clips tab: with ``settings``, your taste's where it's in use."""
    rows, _ = ranked(conn, settings, recording_id)
    return {r["clip_id"]: (n + 1, len(rows)) for n, r in enumerate(rows)}


def place(conn: sqlite3.Connection, clip_id: str, settings: Settings | None = None) -> dict:
    """{"rank": 4, "of": 40} for the clip as the list stands now, for its feedback row."""
    row = conn.execute("SELECT recording_id FROM clips WHERE clip_id = ?", (clip_id,)).fetchone()
    found = ranking(conn, row[0], settings).get(clip_id) if row else None
    return {"rank": found[0], "of": found[1]} if found else {}


def _write_down_missing(conn: sqlite3.Connection) -> None:
    """Ratings from before 3A-1 have no place written down: give them the usual
    score's (all there was then), once."""
    rows = conn.execute(
        "SELECT feedback.id, feedback.clip_id, clips.recording_id FROM feedback "
        "JOIN clips ON clips.clip_id = feedback.clip_id "
        f"WHERE action IN ({','.join('?' * len(RATED))}) AND detail_json IS NULL",
        RATED).fetchall()
    lists: dict[int, dict[str, tuple[int, int]]] = {}
    for row in rows:
        ranks = lists.setdefault(row["recording_id"], ranking(conn, row["recording_id"]))
        if row["clip_id"] in ranks:
            rank, of = ranks[row["clip_id"]]
            conn.execute("UPDATE feedback SET detail_json = ? WHERE id = ?",
                         (json.dumps({"rank": rank, "of": of}), row["id"]))
    if rows:
        conn.commit()


@dataclass
class Week:
    game: str
    monday: date
    streams: int = 0
    liked_top: int = 0      # liked clips in the top TOP
    rated_top: int = 0      # rated clips in the top TOP
    liked: int = 0          # liked clips, anywhere in the list

    @property
    def picked_right(self) -> float | None:
        return self.liked_top / self.rated_top if self.rated_top else None

    @property
    def found(self) -> float | None:
        return self.liked_top / self.liked if self.liked else None


def weeks(conn: sqlite3.Connection) -> list[Week]:
    """Per game and week of streaming, oldest first."""
    from ..recipes.highlights import recorded_at

    _write_down_missing(conn)
    first: dict[str, int] = {}
    for row in conn.execute(
            f"SELECT clip_id, detail_json FROM feedback WHERE action IN "
            f"({','.join('?' * len(RATED))}) AND undone = 0 ORDER BY id", RATED):
        if row["clip_id"] not in first and row["detail_json"]:
            rank = json.loads(row["detail_json"]).get("rank")
            if rank is not None:
                first[row["clip_id"]] = rank
    found: dict[tuple[str, date], Week] = {}
    streams: dict[tuple[str, date], set[int]] = {}
    recordings = {r["id"]: r for r in conn.execute("SELECT * FROM recordings")}
    for clip in conn.execute("SELECT clip_id, recording_id, user_rating, signals_json FROM clips "
                             "WHERE user_rating IS NOT NULL AND user_rating != 0"):
        rank = first.get(clip["clip_id"])
        rec = recordings.get(clip["recording_id"])
        if rank is None or rec is None:
            continue
        game = json.loads(clip["signals_json"] or "{}").get("game") or rec["game"] or "Other"
        day = recorded_at(rec).date()
        key = (game, day - timedelta(days=day.weekday()))
        week = found.setdefault(key, Week(*key))
        streams.setdefault(key, set()).add(rec["id"])
        liked = clip["user_rating"] > 0
        week.liked += liked
        if rank <= TOP:
            week.rated_top += 1
            week.liked_top += liked
    for key, week in found.items():
        week.streams = len(streams[key])
    return [found[k] for k in sorted(found)]


def _share(value: float | None, top: int, of: int) -> str:
    return "-" if value is None else f"**{value:.0%}** ({top} of {of})"


def scoreboard_text(conn: sqlite3.Connection) -> str:
    """For the Clips tab: a table per game, a line per week."""
    found = weeks(conn)
    if not found:
        return ("Nothing to measure yet: rate some clips 👍, 🔖 or 👎 and this fills in, "
                "week by week.")
    parts = [f"**Picked right**: of AI-Editor's top {TOP} clips in each stream, how many of "
             "the ones you rated you liked. **Found your favourites**: of the clips you liked, "
             f"how many were in its top {TOP}. Both should climb as it learns. Weeks are "
             "when you streamed. 🔖 counts as liked."]
    for game in dict.fromkeys(w.game for w in found):
        rows = [w for w in found if w.game == game]
        lines = [f"**{game}**", "", "| Week of | Streams | Picked right | Found your favourites |",
                 "|---|---|---|---|"]
        for w in rows:
            lines.append(f"| {w.monday.day} {w.monday:%b} | {w.streams} | "
                         f"{_share(w.picked_right, w.liked_top, w.rated_top)} | "
                         f"{_share(w.found, w.liked_top, w.liked)} |")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
