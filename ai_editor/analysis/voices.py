"""Telling your friends' voices apart, and who they are (Phase 2I-2).

Your friends on Discord share one track (2I-1). Here each stretch of their
talking gets a voice "fingerprint" (a WeSpeaker model run by sherpa-onnx, on
the processor, nothing leaving this PC), and the stretches that sound alike are
grouped: Voice A, Voice B... per stream, the one who talks most first.

You name a voice once ("Chris"), in the Library. Their fingerprint is kept with
the name, so every stream analysed after that, and every earlier stream with an
unnamed voice that sounds the same, knows Chris by itself. Captions then say
who's talking, in their own colour: "Chris: let's go get him!" (the creator
chose both, 24 Oct).

Only stretches where words were heard are fingerprinted: the Discord track also
carries game sound through your friends' microphones, which grouped as a voice
of its own when the whole track was used (24 Oct test on the 22 Sep Wardogs
stream).

A word's speaker in transcript_words:
  NULL           you
  "friend"       a friend, not told apart (too little of them, or not grouped yet)
  "voice:B"      Voice B of this stream, not named yet
  "friend:7"     a friend you named (friends.id 7)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..logging_setup import get_logger
from .captions import FRIEND

log = get_logger(__name__)

LONGEST_SEC = 6.0       # a longer stretch is fingerprinted in parts of at most this
SHORTEST_SEC = 0.6      # less talking than this isn't fingerprinted
STRETCH_GAP_SEC = 0.5   # words closer than this are one stretch of talking
# Fingerprints closer than this (1 - cosine) are one voice. 0.45 on the 22 Sep
# Wardogs stream: two friends who answer each other came apart, and two who said
# less; 0.5 and up made them all one voice, 0.35 split one friend into several.
GROUP_DISTANCE = 0.45
# A voice this alike (cosine) to a named friend is them. On the 22 Sep stream the
# same friend in two halves was 0.93-0.94 alike, two different friends 0.75 at most.
SAME_FRIEND = 0.85
SOUNDS_LIKE = 0.75      # below SAME_FRIEND but this alike: "a bit like Chris?"
MIN_VOICE_SEC = 8.0     # less talking than this in a stream isn't a voice to name
SAMPLE_SEC = 8.0        # the sample you play when naming a voice
VOICE_PREFIX, FRIEND_PREFIX = "voice:", "friend:"
# Each named friend's own colour, in turn: clear of your white and the yellow
# that lights up the word being said in Shorts. Unnamed voices stay light blue.
PALETTE = ("#8CFF8C", "#FF9ED8", "#FFB46B", "#C8A2FF", "#7FFFEA", "#FF7F7F", "#B8E986")


def stretches(words: list[dict]) -> list[tuple[float, float, list[int]]]:
    """(start, end, word numbers) of each stretch of talking."""
    out: list[tuple[float, float, list[int]]] = []
    for i, w in enumerate(words):
        if out and w["s"] - out[-1][1] < STRETCH_GAP_SEC:
            start, _, idx = out[-1]
            out[-1] = (start, max(out[-1][1], w["e"]), [*idx, i])
        else:
            out.append((w["s"], w["e"], [i]))
    return out


def parts(start: float, end: float) -> list[tuple[float, float]]:
    """A stretch of talking as fingerprinted: whole, or in even parts of at most
    LONGEST_SEC. A whole stretch hears far more of a voice than short windows do:
    1.5 s windows split one friend into several voices and left a third of their
    words without one (24 Oct)."""
    if end - start < SHORTEST_SEC:
        return []
    n = max(1, int(np.ceil((end - start) / LONGEST_SEC)))
    cuts = np.linspace(start, end, n + 1)
    return [(float(cuts[k]), float(cuts[k + 1])) for k in range(n)]


def _print(model, audio: np.ndarray, rate: int, start: float, end: float) -> np.ndarray:
    stream = model.create_stream()
    stream.accept_waveform(rate, audio[int(start * rate):int(end * rate)])
    stream.input_finished()
    found = np.asarray(model.compute(stream), dtype=np.float32)
    return found / (np.linalg.norm(found) or 1.0)


def group(prints: np.ndarray) -> np.ndarray:
    """A group number for each fingerprint: alike ones together."""
    if len(prints) < 2:
        return np.zeros(len(prints), dtype=int)
    from scipy.cluster.hierarchy import fcluster, linkage

    return fcluster(linkage(prints, "average", metric="cosine"), GROUP_DISTANCE,
                    "distance") - 1


def tell_apart(model, wav: Path, words: list[dict]) -> dict:
    """What voices.json holds: each word's voice ("A", "B"... or None) and each
    voice's fingerprint, talking time and a sample to play. ``words`` are your
    friends' words as stored ({"w", "s", "e"}), in order. Every word of one part
    of a stretch of talking has the same voice."""
    import soundfile as sf

    audio, rate = sf.read(str(wav), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    pieces = []   # (start, end, word numbers)
    for s, e, idx in stretches(words):
        for a, b in parts(s, e):
            mine = [i for i in idx if a <= (words[i]["s"] + words[i]["e"]) / 2 <= b]
            if mine:
                pieces.append((a, b, mine))
    if not pieces:
        return {"words": [None] * len(words), "voices": {}}
    prints = np.stack([_print(model, audio, rate, a, b) for a, b, _ in pieces])
    groups = group(prints)
    labels: list[int | None] = [None] * len(words)
    for (_, _, idx), g in zip(pieces, groups):
        for i in idx:
            labels[i] = int(g)

    talk: dict[int, float] = {}
    first: dict[int, int] = {}
    for i, g in enumerate(labels):
        if g is not None:
            talk[g] = talk.get(g, 0.0) + words[i]["e"] - words[i]["s"]
            first.setdefault(g, i)
    # Most talking first; as much talking: whoever spoke first.
    kept = [g for g in sorted(talk, key=lambda g: (-round(talk[g], 1), first[g]))
            if talk[g] >= MIN_VOICE_SEC]
    letters = {g: chr(ord("A") + n) for n, g in enumerate(kept[:26])}
    voices = {}
    for g, letter in letters.items():
        mean = prints[groups == g].mean(axis=0)
        longest = max(((b - a, a, b) for (a, b, _), h in zip(pieces, groups) if h == g),
                      default=(0, 0, 0))
        voices[letter] = {"voice": (mean / (np.linalg.norm(mean) or 1.0)).round(5).tolist(),
                          "seconds": round(talk[g], 1),
                          "sample": [round(longest[1], 2),
                                     round(min(longest[2], longest[1] + SAMPLE_SEC), 2)]}
    return {"words": [letters.get(g) if g is not None else None for g in labels],
            "voices": voices}


# --- Named friends --------------------------------------------------------------------------


@dataclass
class Friend:
    id: int
    name: str
    colour: str
    voice: np.ndarray
    seconds: float

    @property
    def speaker(self) -> str:
        return f"{FRIEND_PREFIX}{self.id}"


def friends(conn: sqlite3.Connection) -> list[Friend]:
    return [Friend(r["id"], r["name"], r["colour"], np.asarray(json.loads(r["voice_json"])),
                   r["seconds"])
            for r in conn.execute("SELECT * FROM friends ORDER BY name COLLATE NOCASE")]


def cast(conn: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """{speaker: (name, colour)} for captions."""
    return {f.speaker: (f.name, f.colour) for f in friends(conn)}


def match(known: list[Friend], voice: np.ndarray) -> Friend | None:
    """The named friend this voice sounds like, if any is alike enough."""
    best = max(known, key=lambda f: float(f.voice @ voice), default=None)
    return best if best is not None and float(best.voice @ voice) >= SAME_FRIEND else None


def store(conn: sqlite3.Connection, recording_id: int, found: dict) -> dict[str, str]:
    """Keep a stream's voices, each recognised as a named friend when it sounds
    like one. Returns {letter: speaker} for its words."""
    conn.execute("DELETE FROM voices WHERE recording_id = ?", (recording_id,))
    known = friends(conn)
    speakers = {}
    for letter, v in found.get("voices", {}).items():
        voice = np.asarray(v["voice"], dtype=np.float32)
        who = match(known, voice)
        conn.execute("INSERT INTO voices (recording_id, label, voice_json, seconds, sample_start, "
                     "sample_end, friend_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (recording_id, letter, json.dumps(v["voice"]), v["seconds"], v["sample"][0],
                      v["sample"][1], who.id if who else None))
        speakers[letter] = who.speaker if who else f"{VOICE_PREFIX}{letter}"
    return speakers


@dataclass
class Voice:
    label: str
    seconds: float
    sample: tuple[float, float]
    friend: Friend | None
    sounds_like: Friend | None = None   # the nearest named friend, when not named

    def said(self) -> str:
        minutes, seconds = divmod(int(self.seconds), 60)
        talk = f"{minutes} min {seconds:02d} s" if minutes else f"{seconds} s"
        who = (f" · {self.friend.name}" if self.friend else
               f" · not named yet (a bit like {self.sounds_like.name}?)" if self.sounds_like
               else " · not named yet")
        return f"Voice {self.label} · {talk} of talking{who}"


def stream_voices(conn: sqlite3.Connection, recording_id: int) -> list[Voice]:
    known = {f.id: f for f in friends(conn)}
    out = []
    for r in conn.execute("SELECT * FROM voices WHERE recording_id = ? ORDER BY label",
                          (recording_id,)):
        voice = np.asarray(json.loads(r["voice_json"]), dtype=np.float32)
        nearest = max(known.values(), key=lambda f: float(f.voice @ voice), default=None)
        out.append(Voice(r["label"], r["seconds"], (r["sample_start"], r["sample_end"]),
                         known.get(r["friend_id"]),
                         nearest if nearest is not None
                         and float(nearest.voice @ voice) >= SOUNDS_LIKE else None))
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def name_voice(conn: sqlite3.Connection, recording_id: int, label: str, name: str) -> str:
    """Name a stream's voice. A new name becomes a new friend; a name you've used
    before adds this voice to theirs. Unnamed voices in other streams that sound
    the same get the name too."""
    name = " ".join((name or "").split())
    if not name:
        return "Type their name first."
    row = conn.execute("SELECT * FROM voices WHERE recording_id = ? AND label = ?",
                       (recording_id, label)).fetchone()
    if row is None:
        return "That voice has gone: pick the recording again."
    voice = np.asarray(json.loads(row["voice_json"]), dtype=np.float32)
    old = conn.execute("SELECT * FROM friends WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if old is None:
        used = {r[0] for r in conn.execute("SELECT colour FROM friends")}
        count = conn.execute("SELECT COUNT(*) FROM friends").fetchone()[0]
        colour = next((c for c in PALETTE if c not in used), PALETTE[count % len(PALETTE)])
        friend_id = conn.execute(
            "INSERT INTO friends (name, colour, voice_json, seconds, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, colour, json.dumps(voice.round(5).tolist()), row["seconds"], _now())).lastrowid
    else:
        friend_id = old["id"]
        had = np.asarray(json.loads(old["voice_json"]), dtype=np.float32)
        weight = old["seconds"] + row["seconds"]
        mean = (had * old["seconds"] + voice * row["seconds"]) / (weight or 1.0)
        mean /= np.linalg.norm(mean) or 1.0
        conn.execute("UPDATE friends SET voice_json = ?, seconds = ? WHERE id = ?",
                     (json.dumps(mean.round(5).tolist()), weight, friend_id))
    _link(conn, recording_id, label, friend_id)

    # The same voice, unnamed, in other streams.
    friend = next(f for f in friends(conn) if f.id == friend_id)
    also = 0
    for r in conn.execute("SELECT recording_id, label, voice_json FROM voices WHERE "
                          "friend_id IS NULL AND recording_id != ?", (recording_id,)).fetchall():
        if float(friend.voice @ np.asarray(json.loads(r["voice_json"]))) >= SAME_FRIEND:
            _link(conn, r["recording_id"], r["label"], friend_id)
            also += 1
    conn.commit()
    return (f"Voice {label} is **{friend.name}** now, in their own colour."
            + (f" Found in {also} other stream{'s' if also != 1 else ''} too: named there as well."
               if also else ""))


def _link(conn: sqlite3.Connection, recording_id: int, label: str, friend_id: int | None) -> None:
    """A stream's voice as a friend (or unnamed again), its words with it."""
    old = conn.execute("SELECT friend_id FROM voices WHERE recording_id = ? AND label = ?",
                       (recording_id, label)).fetchone()
    was = f"{FRIEND_PREFIX}{old[0]}" if old and old[0] else f"{VOICE_PREFIX}{label}"
    now = f"{FRIEND_PREFIX}{friend_id}" if friend_id else f"{VOICE_PREFIX}{label}"
    conn.execute("UPDATE voices SET friend_id = ? WHERE recording_id = ? AND label = ?",
                 (friend_id, recording_id, label))
    # Only this voice's words (transcript_words.voice): another voice of the same
    # friend in this stream keeps its own.
    conn.execute("UPDATE transcript_words SET speaker = ? WHERE recording_id = ? AND speaker = ? "
                 "AND voice = ?", (now, recording_id, was, label))


def unname_voice(conn: sqlite3.Connection, recording_id: int, label: str) -> str:
    """'That's not them': the voice is unnamed again in this stream only."""
    _link(conn, recording_id, label, None)
    conn.commit()
    return f"Voice {label} isn't named any more in this stream."


def rename(conn: sqlite3.Connection, friend_id: int, name: str) -> str:
    name = " ".join((name or "").split())
    if not name:
        return "Type the new name first."
    clash = conn.execute("SELECT id FROM friends WHERE name = ? COLLATE NOCASE",
                         (name,)).fetchone()
    if clash and clash[0] != friend_id:
        return f"There's already a friend called {name}."
    conn.execute("UPDATE friends SET name = ? WHERE id = ?", (name, friend_id))
    conn.commit()
    return f"Renamed to {name}: every caption with them says so."


def recolour(conn: sqlite3.Connection, friend_id: int, colour: str) -> str:
    import re

    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", colour or ""):
        return "Pick a colour first."
    conn.execute("UPDATE friends SET colour = ? WHERE id = ?", (colour.upper(), friend_id))
    conn.commit()
    return "Colour saved."


def forget(conn: sqlite3.Connection, friend_id: int) -> str:
    """Only when you press Forget: their name and fingerprint go; their voices in
    each stream are unnamed again (their words stay, in light blue)."""
    row = conn.execute("SELECT name FROM friends WHERE id = ?", (friend_id,)).fetchone()
    if row is None:
        return "That friend has already gone."
    for r in conn.execute("SELECT recording_id, label FROM voices WHERE friend_id = ?",
                          (friend_id,)).fetchall():
        _link(conn, r["recording_id"], r["label"], None)
    conn.execute("DELETE FROM friends WHERE id = ?", (friend_id,))
    conn.commit()
    return f"Forgot {row['name']}. Their lines stay in captions, unnamed."
