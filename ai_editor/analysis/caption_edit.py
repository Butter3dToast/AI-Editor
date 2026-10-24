"""Fixing captions in Review (Phase 2D-2).

What the creator chose (2026-10-10):

* **Line by line.** A clip's captions are shown as the lines they appear as;
  the creator fixes a line's text and saves it.
* **Fixed everywhere.** The transcript itself is corrected, so every video,
  Short, "You said" and what the AI writes get the right word. The word as
  first heard is kept (``original``) so a line can be put back.
* **Hiding a line** keeps it out of captions only: its words stay in the
  transcript for the AI, titles and "You said", and it can be shown again.
* **Remembered fixes.** After a one-word fix ("zonya" -> "Zhonya's"),
  AI-Editor offers to always write it that way: in every stream, and in new
  ones as they're analysed (word_fixes). Settings lists them; forgetting one
  puts the words it changed back.

Your friends' lines (Phase 2I) are listed too, as their own lines: they're
fixed, hidden and put back the same way, and never change "You said".

Timing stays tied to the creator's voice: each word row keeps its own time.
Typing more or fewer words than a line had shares them out over the line's
words in order, so they stay in sync; a word with no new text left is blank
and shows nothing.
"""

from __future__ import annotations

import difflib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .captions import YOURS, Word, _text, build_cues
from .transcript import _EDGE_PUNCTUATION, _bare

ROW_FIELDS = ("idx", "word", "original", "hidden", "fixed_by")


@dataclass
class Line:
    """One caption line, and the transcript words it's made of."""
    first: int          # idx of its first word
    last: int           # idx of its last word
    start: float        # in the recording
    end: float
    text: str
    hidden: bool
    edited: bool        # any of its words changed from what was heard
    friend: bool = False   # said by a friend on Discord (Phase 2I)

    @property
    def key(self) -> str:
        return f"{self.first}-{self.last}"


def _rows(conn: sqlite3.Connection, recording_id: int, src_in: float, src_out: float):
    return conn.execute(
        "SELECT idx, word, start_sec, end_sec, confidence, original, hidden, speaker "
        "FROM transcript_words WHERE recording_id = ? AND start_sec >= ? AND end_sec <= ? "
        "ORDER BY start_sec, idx",
        (recording_id, src_in, src_out)).fetchall()


def lines(conn: sqlite3.Connection, recording_id: int, src_in: float,
          src_out: float) -> list[Line]:
    """The caption lines of one stretch of a recording, as they show in a video
    (captions.build_cues), hidden ones included so they can be shown again. Yours
    and each friend's make lines of their own, in time order."""
    every = _rows(conn, recording_id, src_in, src_out)
    found: list[Line] = []
    for who in dict.fromkeys(r["speaker"] for r in every):
        found += _lines_of([r for r in every if r["speaker"] == who], who is not None)
    return sorted(found, key=lambda line: (line.start, line.friend))


def _lines_of(rows, friend: bool) -> list[Line]:
    words = [Word(r["word"], r["start_sec"], r["end_sec"], r["confidence"] or 1.0) for r in rows]
    found: list[Line] = []
    p = 0
    for cue in build_cues(words):
        group = []
        while p < len(rows) and _text(words[q] for q in group) != cue.text:
            group.append(p)
            p += 1
        while p < len(rows) and not rows[p]["word"].strip():   # blanked words join the line
            group.append(p)
            p += 1
        if not group or _text(words[q] for q in group) != cue.text:
            break       # never guess: what's listed is only what matched
        part = [rows[q] for q in group]
        found.append(Line(min(r["idx"] for r in part), max(r["idx"] for r in part),
                          part[0]["start_sec"], part[-1]["end_sec"], cue.text,
                          all(r["hidden"] for r in part if r["word"].strip()),
                          any(r["original"] is not None for r in part), friend))
    return found


def _line_rows(conn: sqlite3.Connection, recording_id: int, first: int, last: int):
    return conn.execute(
        "SELECT idx, word, original, start_sec, end_sec FROM transcript_words "
        "WHERE recording_id = ? AND idx BETWEEN ? AND ? ORDER BY start_sec, idx",
        (recording_id, first, last)).fetchall()


def snapshot(conn: sqlite3.Connection, recording_id: int, first: int, last: int) -> list[dict]:
    """The words of a line as they are now, for Undo."""
    return [dict(r) for r in conn.execute(
        f"SELECT {', '.join(ROW_FIELDS)} FROM transcript_words WHERE recording_id = ? "
        "AND idx BETWEEN ? AND ? ORDER BY idx", (recording_id, first, last))]


def restore(conn: sqlite3.Connection, recording_id: int, rows: list[dict]) -> None:
    """Put words back as a snapshot had them (Undo and Redo)."""
    conn.executemany(
        "UPDATE transcript_words SET word = ?, original = ?, hidden = ?, fixed_by = ? "
        "WHERE recording_id = ? AND idx = ?",
        [(r["word"], r["original"], r["hidden"], r["fixed_by"], recording_id, r["idx"])
         for r in rows])
    if rows:
        _refresh_said(conn, recording_id, [r["idx"] for r in rows])


def _set(conn: sqlite3.Connection, recording_id: int, row, text: str) -> None:
    """One word's new text, remembering what was first heard."""
    was = row["original"] if row["original"] is not None else row["word"]
    conn.execute("UPDATE transcript_words SET word = ?, original = ?, fixed_by = NULL "
                 "WHERE recording_id = ? AND idx = ?",
                 (text, None if text == was else was, recording_id, row["idx"]))


def _share(rows, tokens: list[str]) -> list[str]:
    """``tokens`` shared out over ``rows`` in order: one each when the counts
    match, otherwise spread evenly (some rows get two words, or none)."""
    m, n = len(rows), len(tokens)
    return [" ".join(tokens[k * n // m:(k + 1) * n // m]) for k in range(m)]


@dataclass
class Saved:
    message: str
    # A one-word fix worth remembering: (as heard, as it should be), else None.
    offer: tuple[str, str] | None = None


def save_line(conn: sqlite3.Connection, recording_id: int, first: int, last: int,
              text: str) -> Saved:
    """A line's new text. Words that didn't change keep their own row (and time);
    the changed ones are shared out over the words they replace."""
    rows = _line_rows(conn, recording_id, first, last)
    new = text.split()
    if not rows:
        return Saved("That line has gone: click the clip again.")
    if not new:
        return Saved("Type the line's words, or press Hide this line to leave it out.")
    old = [r["word"].strip() for r in rows]
    texts = list(old)
    matcher = difflib.SequenceMatcher(a=[_bare(w) for w in old], b=[_bare(w) for w in new],
                                      autojunk=False)
    replaced, before = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            texts[i1:i2] = new[j1:j2]       # same words; punctuation or case may differ
        elif i1 == i2:                      # words added: they join the word before
            if i1 == 0:
                before += new[j1:j2]        # ...or the first word, once it's settled
            else:
                texts[i1 - 1] = " ".join([texts[i1 - 1], *new[j1:j2]]).strip()
        else:
            texts[i1:i2] = _share(rows[i1:i2], new[j1:j2])
            replaced.append((i2 - i1, j2 - j1, i1, j1))
    if before:
        texts[0] = " ".join([*before, texts[0]]).strip()
    for row, value in zip(rows, texts):
        if value != row["word"]:
            _set(conn, recording_id, row, value)
    _refresh_said(conn, recording_id, [r["idx"] for r in rows])
    conn.commit()
    offer = None
    if len(replaced) == 1 and replaced[0][:2] == (1, 1):
        _, _, i, j = replaced[0]
        heard, meant = _bare(old[i]), new[j].strip(_EDGE_PUNCTUATION)
        if heard and meant and heard != meant.lower():
            offer = (heard, meant)
    return Saved("Line saved." if texts != old else "Nothing changed in that line.", offer)


def hide_line(conn: sqlite3.Connection, recording_id: int, first: int, last: int,
              hidden: bool) -> None:
    conn.execute("UPDATE transcript_words SET hidden = ? WHERE recording_id = ? "
                 "AND idx BETWEEN ? AND ?", (1 if hidden else 0, recording_id, first, last))
    conn.commit()


def put_back(conn: sqlite3.Connection, recording_id: int, first: int, last: int) -> None:
    """The line as first heard: every fix in it undone, shown again."""
    conn.execute("UPDATE transcript_words SET word = original, original = NULL, fixed_by = NULL "
                 "WHERE recording_id = ? AND idx BETWEEN ? AND ? AND original IS NOT NULL",
                 (recording_id, first, last))
    conn.execute("UPDATE transcript_words SET hidden = 0 WHERE recording_id = ? "
                 "AND idx BETWEEN ? AND ?", (recording_id, first, last))
    _refresh_said(conn, recording_id, list(range(first, last + 1)))
    conn.commit()


def _refresh_said(conn: sqlite3.Connection, recording_id: int, idxs: list[int]) -> None:
    """The clips covering these words show what was said with the fix in."""
    if not idxs:
        return
    span = conn.execute(
        f"SELECT MIN(start_sec), MAX(end_sec) FROM transcript_words WHERE recording_id = ? "
        f"AND idx IN ({','.join('?' * len(idxs))})", (recording_id, *idxs)).fetchone()
    if span[0] is None:
        return
    for clip in conn.execute("SELECT clip_id, start_sec, end_sec FROM clips WHERE recording_id = ? "
                             "AND start_sec < ? AND end_sec > ?",
                             (recording_id, span[1], span[0])).fetchall():
        words = conn.execute(
            f"SELECT word FROM transcript_words WHERE recording_id = ? AND {YOURS} AND "
            "start_sec >= ? AND end_sec <= ? ORDER BY start_sec, idx",
            (recording_id, clip["start_sec"], clip["end_sec"])).fetchall()
        said = _text([Word(r["word"], 0.0, 0.0) for r in words])
        conn.execute("UPDATE clips SET transcript = ? WHERE clip_id = ?", (said, clip["clip_id"]))


# --- Remembered fixes ------------------------------------------------------------------


def _fixed(word: str, meant: str) -> str:
    """``meant`` with the punctuation ``word`` had around it ("zonya," -> "Zhonya's,")."""
    core = word.strip(_EDGE_PUNCTUATION)
    if not core:
        return word
    at = word.find(core)
    return word[:at] + meant + word[at + len(core):]


def _apply(conn: sqlite3.Connection, fix_id: int, heard: str, meant: str,
           recording_id: int | None = None) -> dict[int, int]:
    """Write ``meant`` for every word heard as ``heard``. Returns {recording: count}."""
    where = "AND recording_id = ?" if recording_id is not None else ""
    rows = conn.execute(
        f"SELECT recording_id, idx, word, original FROM transcript_words WHERE "
        f"lower(word) LIKE ? {where}",
        (f"%{heard}%", *(() if recording_id is None else (recording_id,)))).fetchall()
    counts: dict[int, int] = {}
    for r in rows:
        if _bare(r["word"]) != heard:
            continue
        conn.execute("UPDATE transcript_words SET word = ?, original = COALESCE(original, ?), "
                     "fixed_by = ? WHERE recording_id = ? AND idx = ?",
                     (_fixed(r["word"], meant), r["word"], fix_id, r["recording_id"], r["idx"]))
        counts[r["recording_id"]] = counts.get(r["recording_id"], 0) + 1
    for rid in counts:
        _refresh_said(conn, rid, [r["idx"] for r in rows if r["recording_id"] == rid])
    return counts


def how_often(conn: sqlite3.Connection, heard: str) -> tuple[int, int]:
    """(words, streams): how much remembering a fix of ``heard`` would change. A
    common word ("not") is in hundreds of places (10 Oct trial: 287 in 15 streams)."""
    heard = _bare(heard)
    found = [r["recording_id"] for r in conn.execute(
        "SELECT recording_id, word FROM transcript_words WHERE lower(word) LIKE ?",
        (f"%{heard}%",)) if _bare(r["word"]) == heard]
    return len(found), len(set(found))


def offer_text(conn: sqlite3.Connection, heard: str, meant: str) -> str:
    """The question after a one-word fix, with what saying yes would change."""
    words, streams = how_often(conn, heard)
    where = (f"It's heard **{words} more time(s) in {streams} stream(s)**: say yes only if "
             "it's wrong everywhere." if words else
             "It isn't anywhere else yet: new streams would get it.")
    return f"Always write **{heard}** as **{meant}**? {where}"


def remember(conn: sqlite3.Connection, heard: str, meant: str) -> str:
    """Always write ``heard`` as ``meant``: every stream now, and new ones as analysed."""
    heard = _bare(heard)
    conn.execute("INSERT INTO word_fixes (wrong, right, created_at) VALUES (?, ?, ?) "
                 "ON CONFLICT(wrong) DO UPDATE SET right = excluded.right",
                 (heard, meant, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    fix_id = conn.execute("SELECT id FROM word_fixes WHERE wrong = ?", (heard,)).fetchone()[0]
    counts = _apply(conn, fix_id, heard, meant)
    conn.commit()
    total = sum(counts.values())
    where = (f" {total} more time(s) in {len(counts)} stream(s)" if total
             else " (it isn't anywhere else yet)")
    return (f"From now on \"{heard}\" is written \"{meant}\": fixed{where}, and in new streams "
            "as they're analysed. Settings lists it, if you want it gone again.")


def remembered(conn: sqlite3.Connection) -> list[tuple[int, str, str, int]]:
    """(id, as heard, as written, words it fixed) for each remembered fix."""
    return [(r["id"], r["wrong"], r["right"], r["n"]) for r in conn.execute(
        "SELECT f.id, f.wrong, f.right, (SELECT COUNT(*) FROM transcript_words w "
        "WHERE w.fixed_by = f.id) AS n FROM word_fixes f ORDER BY f.wrong")]


def forget(conn: sqlite3.Connection, fix_id: int) -> int:
    """Stop a remembered fix, and put back every word it changed."""
    rows = conn.execute("SELECT recording_id, idx FROM transcript_words WHERE fixed_by = ?",
                        (fix_id,)).fetchall()
    conn.execute("UPDATE transcript_words SET word = original, original = NULL, fixed_by = NULL "
                 "WHERE fixed_by = ?", (fix_id,))
    conn.execute("DELETE FROM word_fixes WHERE id = ?", (fix_id,))
    for rid in {r["recording_id"] for r in rows}:
        _refresh_said(conn, rid, [r["idx"] for r in rows if r["recording_id"] == rid])
    conn.commit()
    return len(rows)


def apply_remembered(conn: sqlite3.Connection, recording_id: int) -> int:
    """A newly analysed recording gets every remembered fix."""
    total = 0
    for fix_id, heard, meant, _ in remembered(conn):
        total += sum(_apply(conn, fix_id, heard, meant, recording_id).values())
    conn.commit()
    return total


# --- Analysing again keeps the creator's fixes ---------------------------------------


def keep_fixes(conn: sqlite3.Connection, recording_id: int) -> list[dict]:
    """The creator's own fixes and hidden lines, before the transcript is stored again."""
    return [dict(r) for r in conn.execute(
        "SELECT start_sec, end_sec, word, original, hidden, speaker FROM transcript_words "
        "WHERE recording_id = ? AND fixed_by IS NULL AND (original IS NOT NULL OR hidden = 1)",
        (recording_id,))]


def put_fixes_back(conn: sqlite3.Connection, recording_id: int, kept: list[dict]) -> None:
    """Each kept fix onto the same word (same time, same word as heard) in the
    new transcript; then the remembered fixes."""
    for k in kept:
        heard = k["original"] if k["original"] is not None else k["word"]
        conn.execute(
            "UPDATE transcript_words SET word = ?, original = ?, hidden = ? WHERE recording_id = ? "
            "AND abs(start_sec - ?) < 0.01 AND abs(end_sec - ?) < 0.01 AND word = ? "
            "AND speaker IS ?",   # a friend's word at the same moment isn't yours
            (k["word"], k["original"], k["hidden"], recording_id, k["start_sec"], k["end_sec"],
             heard, k["speaker"]))
    apply_remembered(conn, recording_id)
