"""Subtitle cues and SRT output."""

from __future__ import annotations

from ai_editor.analysis.captions import Word, build_cues, clock, srt_time, to_srt, write_srt


def _words(*spec):
    return [Word(text, start, end) for text, start, end in spec]


def test_pause_starts_a_new_cue():
    cues = build_cues(_words(("Hello", 0.0, 0.4), ("there.", 0.5, 0.9), ("Later", 5.0, 5.4)))
    assert [c.text for c in cues] == ["Hello there.", "Later"]
    # Held to the 1-second minimum so it can be read (the next cue is at 5.0).
    assert (cues[0].start, cues[0].end) == (0.0, 1.0)


def test_long_speech_is_split_to_stay_readable():
    words = [Word(f"word{i}", i * 0.3, i * 0.3 + 0.25) for i in range(40)]
    cues = build_cues(words, max_chars=84, max_duration=6.0)
    assert len(cues) > 1
    assert all(len(c.text) <= 84 for c in cues)
    assert all(c.end - c.start <= 6.0 for c in cues)
    assert " ".join(c.text for c in cues) == " ".join(w.text for w in words), "no word lost"


def _timed(sentence, start, per_word=0.3):
    return [Word(t, start + i * per_word, start + i * per_word + 0.25)
            for i, t in enumerate(sentence.split())]


def test_sentences_are_not_cut_in_the_middle():
    """From EP 1: "...You'll get your answers. I" / "can promise you that." """
    words = (_timed("Where is everyone? What did he do to them?", 0.0)
             + _timed("You'll get your answers. I can promise you that.", 2.7))
    texts = [c.text for c in build_cues(words)]
    assert "You'll get your answers." in texts
    assert "I can promise you that." in texts
    assert all(not t.endswith(" I") for t in texts)


def test_very_short_sentences_join_the_next():
    texts = [c.text for c in build_cues(_timed("Still. Go then. I'll check my house.", 0.0))]
    assert texts == ["Still. Go then. I'll check my house."]


def test_long_sentence_splits_at_a_comma():
    words = _timed(
        "Maybe someone managed to break through the gate and run away from the soldiers, "
        "or maybe they hid in the cellar until morning came.", 0.0, per_word=0.2)
    cues = build_cues(words)
    assert len(cues) == 2
    assert cues[0].text.endswith("soldiers,")


def test_no_fragment_flashes_by():
    """From EP 1: "there?" was on screen for 0.18 s."""
    words = _timed("The Brachyr is gone. And who's that? Over there?", 0.0, per_word=0.25)
    for cue in build_cues(words):
        assert cue.end - cue.start >= 1.0 or cue.text.count(" ") >= 2


def test_minimum_display_time_never_overlaps_the_next_cue():
    words = [Word("Jesus.", 0.0, 0.3), Word("Where", 1.5, 1.8), Word("is", 1.8, 1.9),
             Word("everyone", 1.9, 2.3), Word("in", 2.3, 2.4), Word("this", 2.4, 2.6),
             Word("village?", 2.6, 3.0)]
    cues = build_cues(words, max_gap=1.0)
    assert cues[0].text == "Jesus."
    assert cues[0].end == 1.0
    assert all(a.end <= b.start for a, b in zip(cues, cues[1:]))


def test_srt_timestamp_format():
    assert srt_time(0) == "00:00:00,000"
    assert srt_time(3723.456) == "01:02:03,456"


def test_clock_is_what_you_type_into_a_player():
    assert clock(5) == "0:00:05"
    assert clock(3723.9) == "1:02:03"


def test_srt_document():
    text = to_srt(build_cues(_words(("Hi", 1.0, 1.5))))
    assert text == "1\n00:00:01,000 --> 00:00:02,000\nHi\n"  # held for the 1 s minimum


def test_srt_file_is_marked_as_utf8(tmp_path):
    """The BOM stops Windows players mangling accented words."""
    path = write_srt(build_cues(_words(("Café", 0.0, 0.5))), tmp_path / "t.srt")
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "Café" in raw.decode("utf-8-sig")
