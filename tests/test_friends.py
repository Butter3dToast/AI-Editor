"""Your friends on Discord in captions (Phase 2I-1)."""

from __future__ import annotations

import subprocess

import numpy as np
import pytest

from ai_editor.analysis import caption_edit
from ai_editor.analysis.captions import FRIEND, FRIEND_IDX, Word, segment_cues
from ai_editor.config import Captions
from ai_editor.db import init_db
from ai_editor.render.captions import ass_colour, ass_document, short_document

from .conftest import FFMPEG, needs_ffmpeg


def words(text: str, start: float, speaker: str | None = None, step: float = 0.4) -> list[Word]:
    return [Word(w, start + i * step, start + i * step + 0.3, 1.0, speaker)
            for i, w in enumerate(text.split())]


MINE = words("we take this fight now.", 1.0)
THEIRS = words("no way, behind you!", 1.4, FRIEND)


def test_each_speaker_gets_lines_of_their_own_yours_first():
    cues = segment_cues(sorted(MINE + THEIRS, key=lambda w: w.start), 0.0, 10.0)
    assert [(c.text, c.speaker) for c in cues] == [("we take this fight now.", None),
                                                   ("no way, behind you!", FRIEND)]


def test_friends_lines_are_light_blue_and_written_after_yours():
    cues = segment_cues(THEIRS + MINE, 0.0, 10.0)
    doc = ass_document(cues, width=1920, height=1080, style=Captions(), place=0.08)
    blue = ass_colour("#7FD4FF")
    assert f"Style: Friend,Arial,64,{blue},{blue}," in doc
    events = [line for line in doc.splitlines() if line.startswith("Dialogue")]
    assert ",Default,," in events[0] and ",Friend,," in events[1]


def test_shorts_light_up_your_friends_words_in_their_colour():
    doc = short_document(MINE + THEIRS, 0.0, 10.0, width=1080, height=1920, style=Captions(),
                         zone=type("Zone", (), {"bottom": 0.1, "right": 0.1})())
    events = [line for line in doc.splitlines() if line.startswith("Dialogue")]
    theirs = [e for e in events if "behind" in e]
    assert theirs and all("{\\c" + ass_colour("#7FD4FF") + "&}" in e for e in theirs)
    assert not any(ass_colour("#7FD4FF") in e for e in events if "fight" in e)
    assert events.index(theirs[0]) > max(i for i, e in enumerate(events) if "fight" in e)


@needs_ffmpeg
def test_when_you_both_talk_their_line_is_drawn_above_yours(tmp_path):
    """The subtitle renderer stacks lines on screen at once in the order they're
    written: yours first, so theirs goes on top."""
    cues = segment_cues(MINE + THEIRS, 0.0, 10.0)
    (tmp_path / "c.ass").write_text(ass_document(cues, width=640, height=360, style=Captions(),
                                                 place=0.08), encoding="utf-8")
    frame = tmp_path / "f.rgb"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=640x360:d=3", "-vf", "subtitles=filename=c.ass",
                    "-ss", "2.0", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24",
                    str(frame)], check=True, cwd=tmp_path)
    picture = np.frombuffer(frame.read_bytes(), np.uint8).reshape(360, 640, 3).astype(int)
    r, g, b = picture[..., 0], picture[..., 1], picture[..., 2]
    white = np.nonzero((r > 200) & (g > 200) & (b > 200))[0]
    blue = np.nonzero((r < 170) & (g > 170) & (b > 220))[0]
    assert len(white) and len(blue)
    assert blue.mean() < white.mean()       # higher on screen


# --- In the library ------------------------------------------------------------------------


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                       "duration_sec, imported_at) VALUES (1, 'h', 'local_obs', 'r.mkv', 60, 'now')")
    rows = [(1, i, w.text, w.start, w.end, None) for i, w in enumerate(MINE)]
    rows += [(1, FRIEND_IDX + i, w.text, w.start, w.end, FRIEND) for i, w in enumerate(THEIRS)]
    connection.executemany("INSERT INTO transcript_words (recording_id, idx, word, start_sec, "
                           "end_sec, speaker) VALUES (?, ?, ?, ?, ?, ?)", rows)
    connection.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                       "created_at) VALUES ('c', 1, 0, 10, 0.5, 'now')")
    connection.commit()
    yield connection
    connection.close()


def test_review_lists_your_friends_lines_on_their_own(conn):
    found = caption_edit.lines(conn, 1, 0.0, 10.0)
    assert [(line.text, line.friend) for line in found] == [
        ("we take this fight now.", False), ("no way, behind you!", True)]
    assert found[1].first >= FRIEND_IDX


def test_fixing_a_friends_line_never_changes_what_you_said(conn):
    line = caption_edit.lines(conn, 1, 0.0, 10.0)[1]
    caption_edit.save_line(conn, 1, line.first, line.last, "no way, behind you mate!")
    said = conn.execute("SELECT transcript FROM clips").fetchone()[0]
    assert said == "we take this fight now."
    assert caption_edit.lines(conn, 1, 0.0, 10.0)[1].text == "no way, behind you mate!"


def test_analysing_again_keeps_a_fix_on_the_right_persons_word(conn):
    # You and a friend saying a word at the same moment: the fix stays on whose it was.
    conn.execute("INSERT INTO transcript_words (recording_id, idx, word, start_sec, end_sec, "
                 "speaker) VALUES (1, 99, 'way,', 1.8, 2.1, NULL)")
    conn.execute("UPDATE transcript_words SET word = 'WAY,', original = 'way,' "
                 "WHERE idx = ?", (FRIEND_IDX + 1,))
    kept = caption_edit.keep_fixes(conn, 1)
    conn.execute("UPDATE transcript_words SET word = original, original = NULL "
                 "WHERE original IS NOT NULL")
    caption_edit.put_fixes_back(conn, 1, kept)
    rows = dict(conn.execute("SELECT idx, word FROM transcript_words WHERE word LIKE '%way%'"))
    assert rows == {99: "way,", FRIEND_IDX + 1: "WAY,"}


def test_a_discord_track_that_copies_your_mic_is_left_alone(conn, tmp_path):
    import soundfile as sf

    from ai_editor.analysis.pipeline import friends_track

    rng = np.random.default_rng(1)
    voice, chat = rng.normal(0, 0.1, 48000 * 40), rng.normal(0, 0.1, 48000 * 40)
    for name, sound in (("mic", voice), ("copy", voice), ("chat", chat)):
        sf.write(tmp_path / f"{name}.wav", sound, 48000)

    def tracks(chat_file):
        conn.execute("DELETE FROM audio_tracks")
        conn.executemany("INSERT INTO audio_tracks (recording_id, stream_index, role, "
                         "extracted_path) VALUES (1, ?, ?, ?)",
                         [(1, "mic", str(tmp_path / "mic.wav")),
                          (3, "voice_chat", str(tmp_path / chat_file))])

    tracks("chat.wav")
    assert friends_track(conn, 1) == (3, tmp_path / "chat.wav")
    tracks("copy.wav")
    assert friends_track(conn, 1) is None
    tracks("missing.wav")
    assert friends_track(conn, 1) is None
