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


def test_never_for_a_lets_play(conn, settings, tmp_path):
    """No friends on Discord there, and characters' lines must never be captioned as theirs."""
    import soundfile as sf

    from ai_editor.analysis.pipeline import friends_track

    sf.write(tmp_path / "chat.wav", np.random.default_rng(2).normal(0, 0.1, 48000 * 5), 48000)
    conn.execute("INSERT INTO audio_tracks (recording_id, stream_index, role, extracted_path) "
                 "VALUES (1, 3, 'voice_chat', ?)", (str(tmp_path / "chat.wav"),))
    conn.execute("UPDATE recordings SET game = ?", (settings.lets_play.games[0],))
    assert friends_track(conn, 1, settings) is None
    conn.execute("UPDATE recordings SET game = 'Wardogs'")
    assert friends_track(conn, 1, settings) is not None


# --- Telling voices apart (2I-2) ------------------------------------------------------------


class FakeVoiceModel:
    """Stands in for the voice model: a voice's fingerprint is the pitch it's
    sung at, so two made-up friends sound clearly different."""

    class Stream:
        def accept_waveform(self, rate, samples):
            self.rate, self.samples = rate, np.asarray(samples)

        def input_finished(self):
            pass

    def create_stream(self):
        return self.Stream()

    def compute(self, stream):
        spectrum = np.abs(np.fft.rfft(stream.samples, n=stream.rate))[100:900]
        top = int(np.argmax(spectrum)) if len(spectrum) else 0
        found = np.zeros(8)
        found[min(7, top // 100)] = 1.0
        return found.tolist()


def two_friends(tmp_path):
    """Friend one talks for 20 s, then friend two: their words and the sound."""
    import soundfile as sf

    rate = 16000
    sound = np.zeros(rate * 50, dtype=np.float32)
    said = []
    for start, pitch in ((2.0, 300), (26.0, 650)):
        t = np.arange(int(20 * rate)) / rate
        sound[int(start * rate):int(start * rate) + len(t)] = 0.3 * np.sin(2 * np.pi * pitch * t)
        said += [{"w": f"w{len(said) + i}", "s": start + i * 0.4, "e": start + i * 0.4 + 0.35,
                  "p": 0.9} for i in range(48)]
    sf.write(tmp_path / "friends_16k.wav", sound, rate)
    return tmp_path / "friends_16k.wav", said


def test_two_friends_become_two_voices(tmp_path):
    from ai_editor.analysis.voices import tell_apart

    wav, said = two_friends(tmp_path)
    found = tell_apart(FakeVoiceModel(), wav, said)
    assert set(found["voices"]) == {"A", "B"}
    assert found["words"][:48] == ["A"] * 48 and found["words"][48:] == ["B"] * 48
    assert found["voices"]["A"]["seconds"] == pytest.approx(48 * 0.35, abs=0.1)
    start, end = found["voices"]["B"]["sample"]
    assert 26.0 <= start < end <= 46.0 and end - start <= 8.0


@pytest.fixture
def library(settings, tmp_path):
    """Two streams with the same two friends, nobody named yet."""
    from ai_editor.analysis import voices

    connection = init_db(settings.db_path)
    wav, said = two_friends(tmp_path)
    found = voices.tell_apart(FakeVoiceModel(), wav, said)
    for rid in (1, 2):
        connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                           "duration_sec, imported_at) VALUES (?, ?, 'local_obs', 'r.mkv', 60, "
                           "'now')", (rid, f"h{rid}"))
        speakers = voices.store(connection, rid, found)
        connection.executemany(
            "INSERT INTO transcript_words (recording_id, idx, word, start_sec, end_sec, speaker, "
            "voice) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(rid, FRIEND_IDX + i, w["w"], w["s"], w["e"], speakers[v], v)
             for i, (w, v) in enumerate(zip(said, found["words"]))])
    connection.commit()
    yield connection
    connection.close()


def speakers_of(conn, rid):
    return {r[0] for r in conn.execute("SELECT DISTINCT speaker FROM transcript_words "
                                       "WHERE recording_id = ?", (rid,))}


def test_name_a_voice_once_and_it_is_known_everywhere(library, settings, tmp_path):
    from ai_editor.analysis import voices

    assert speakers_of(library, 1) == {"voice:A", "voice:B"}
    said = voices.name_voice(library, 1, "A", "Chris")
    assert "Found in 1 other stream too" in said
    chris = voices.friends(library)[0]
    assert speakers_of(library, 1) == speakers_of(library, 2) == {chris.speaker, "voice:B"}
    assert voices.cast(library) == {chris.speaker: ("Chris", voices.PALETTE[0])}

    # A new stream: Chris is known straight away; Voice B still waits for a name.
    wav, said_words = two_friends(tmp_path)
    found = voices.tell_apart(FakeVoiceModel(), wav, said_words)
    library.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                    "duration_sec, imported_at) VALUES (3, 'h3', 'local_obs', 'r.mkv', 60, 'now')")
    assert voices.store(library, 3, found) == {"A": chris.speaker, "B": "voice:B"}


def test_take_a_name_back_rename_recolour_and_forget(library):
    from ai_editor.analysis import voices

    voices.name_voice(library, 1, "B", "Toad")
    toad = voices.friends(library)[0]
    voices.unname_voice(library, 2, "B")                     # "That's not them", in stream 2
    assert speakers_of(library, 2) == {"voice:A", "voice:B"}
    assert toad.speaker in speakers_of(library, 1)
    assert "Renamed" in voices.rename(library, toad.id, "Toadie")
    voices.recolour(library, toad.id, "#123abc")
    assert voices.cast(library)[toad.speaker] == ("Toadie", "#123ABC")
    assert "Forgot Toadie" in voices.forget(library, toad.id)
    assert voices.friends(library) == [] and speakers_of(library, 1) == {"voice:A", "voice:B"}
    # Their words stay: only the name goes.
    assert library.execute("SELECT COUNT(*) FROM transcript_words WHERE recording_id = 1"
                           ).fetchone()[0] == 96


def test_captions_say_who_is_talking_in_their_colour():
    chris = "friend:7"
    cast = {chris: ("Chris", "#8CFF8C")}
    mine, theirs = words("we take this fight now.", 1.0), words("let's go get him!", 1.4, chris)
    cues = segment_cues(mine + theirs, 0.0, 10.0, cast)
    assert [c.text for c in cues] == ["we take this fight now.", "Chris: let's go get him!"]
    doc = ass_document(cues, width=1920, height=1080, style=Captions(), place=0.08, cast=cast)
    green = ass_colour("#8CFF8C")
    assert f"Style: Friend7,Arial,64,{green},{green}," in doc and ",Friend7,," in doc
    short = short_document(mine + theirs, 0.0, 10.0, width=1080, height=1920, style=Captions(),
                           zone=type("Zone", (), {"bottom": 0.1, "right": 0.1})(), cast=cast)
    assert any("Chris: " in line and green in line for line in short.splitlines())
