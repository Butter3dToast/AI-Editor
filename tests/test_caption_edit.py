"""Fixing captions in Review, line by line (Phase 2D-2)."""

from __future__ import annotations

import pytest

from ai_editor.analysis import caption_edit as ce
from ai_editor.analysis.captions import segment_cues
from ai_editor.analysis.clips import load_words
from ai_editor.db import init_db
from ai_editor.recipes import history
from ai_editor.recipes.plan import EditPlan, Segment, save_plan

SAID = ["that", "was", "a", "waste", "of", "my", "TP.", "I", "feel", "like", "zonya", "is",
        "a", "death", "trap."]


def words(conn, recording_id, said, start=100.0):
    conn.executemany(
        "INSERT INTO transcript_words (recording_id, idx, word, start_sec, end_sec) "
        "VALUES (?, ?, ?, ?, ?)",
        [(recording_id, i, w, start + i * 0.5, start + i * 0.5 + 0.4) for i, w in enumerate(said)])


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    for rid in (1, 2):
        connection.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                           "duration_sec, imported_at) VALUES (?, ?, 'local_obs', 'r.mkv', 600, "
                           "'now')", (rid, f"h{rid}"))
    words(connection, 1, SAID)
    words(connection, 2, ["zonya,", "again", "zonya"], start=50.0)
    connection.execute("INSERT INTO clips (clip_id, recording_id, start_sec, end_sec, score, "
                       "transcript, created_at) VALUES ('c', 1, 99, 110, 0.5, 'old', 'now')")
    connection.commit()
    yield connection
    connection.close()


def line_with(conn, text, rid=1):
    return next(ln for ln in ce.lines(conn, rid, 90, 120) if text in ln.text)


def test_a_clips_captions_are_listed_as_the_lines_they_show_as(conn):
    found = ce.lines(conn, 1, 90, 120)
    shown = [c.text for c in segment_cues(load_words(conn, 1), 90, 120)]
    assert [ln.text for ln in found] == shown
    assert found[0].first == 0 and found[-1].last == len(SAID) - 1


def test_a_fixed_word_is_fixed_everywhere_and_the_original_kept(conn):
    line = line_with(conn, "zonya")
    saved = ce.save_line(conn, 1, line.first, line.last, "I feel like Zhonya's is a death trap.")
    assert saved.offer == ("zonya", "Zhonya's")
    assert "Zhonya's" in line_with(conn, "Zhonya").text and line_with(conn, "Zhonya").edited
    row = conn.execute("SELECT word, original, start_sec FROM transcript_words WHERE idx = 10 "
                       "AND recording_id = 1").fetchone()
    assert tuple(row) == ("Zhonya's", "zonya", 105.0)       # same word, same time
    assert "Zhonya's" in conn.execute("SELECT transcript FROM clips").fetchone()[0]
    ce.put_back(conn, 1, line.first, line.last)
    assert "zonya" in line_with(conn, "zonya").text and not line_with(conn, "zonya").edited


def test_more_or_fewer_words_share_the_lines_time(conn):
    line = line_with(conn, "zonya")
    ce.save_line(conn, 1, line.first, line.last, "I feel like Zhonya's hourglass is a death trap.")
    assert "Zhonya's hourglass is a death trap." in line_with(conn, "hourglass").text
    line = line_with(conn, "hourglass")
    ce.save_line(conn, 1, line.first, line.last, "Zhonya's is a trap.")
    assert line_with(conn, "Zhonya").text == "Zhonya's is a trap."
    times = [r[0] for r in conn.execute("SELECT start_sec FROM transcript_words WHERE "
                                        "recording_id = 1 ORDER BY idx")]
    assert times == [100.0 + i * 0.5 for i in range(len(SAID))]   # nothing moved in time


def test_a_hidden_line_is_left_out_of_captions_but_not_the_transcript(conn):
    line = line_with(conn, "waste")
    ce.hide_line(conn, 1, line.first, line.last, True)
    assert line_with(conn, "waste").hidden
    shown = " ".join(w.text for w in load_words(conn, 1, captions=True))
    assert "waste" not in shown and "death" in shown
    assert "waste" in " ".join(w.text for w in load_words(conn, 1))
    ce.hide_line(conn, 1, line.first, line.last, False)
    assert "waste" in " ".join(w.text for w in load_words(conn, 1, captions=True))


def test_a_remembered_fix_goes_everywhere_and_can_be_forgotten(conn):
    message = ce.remember(conn, "zonya", "Zhonya's")
    assert "3 more time(s) in 2 stream(s)" in message
    assert [w.text for w in load_words(conn, 2)] == ["Zhonya's,", "again", "Zhonya's"]
    (fix_id, heard, meant, count), = ce.remembered(conn)
    assert (heard, meant, count) == ("zonya", "Zhonya's", 3)
    # A new stream, analysed later, gets it too.
    conn.execute("INSERT INTO recordings (id, content_hash, source_type, source_file, "
                 "duration_sec, imported_at) VALUES (3, 'h3', 'local_obs', 'r.mkv', 60, 'now')")
    words(conn, 3, ["zonya"])
    assert ce.apply_remembered(conn, 3) == 1
    assert ce.forget(conn, fix_id) == 4
    assert [w.text for w in load_words(conn, 2)] == ["zonya,", "again", "zonya"]
    assert ce.remembered(conn) == []


def test_analysing_again_keeps_your_fixes(conn):
    line = line_with(conn, "waste")
    ce.save_line(conn, 1, line.first, line.last, "that was a waste of my teleport.")
    ce.hide_line(conn, 1, *(lambda ln: (ln.first, ln.last))(line_with(conn, "zonya")), True)
    kept = ce.keep_fixes(conn, 1)
    conn.execute("DELETE FROM transcript_words WHERE recording_id = 1")
    words(conn, 1, SAID)                      # the transcript stored again, as heard
    ce.put_fixes_back(conn, 1, kept)
    assert "teleport." in line_with(conn, "teleport").text
    assert line_with(conn, "zonya").hidden


def test_undo_puts_a_fixed_line_back(conn):
    save_plan(conn, EditPlan("p", "highlights", "t", None, 60, [Segment(1, 90, 120)]))
    line = line_with(conn, "zonya")
    with history.step(conn, "p", "fixing a caption", words=(1, line.first, line.last)):
        ce.save_line(conn, 1, line.first, line.last, "I feel like Zhonya's is a death trap.")
    assert history.can(conn, "p") == ("fixing a caption", None)
    history.undo(conn, "p")
    assert "zonya" in line_with(conn, "zonya").text
    history.redo(conn, "p")
    assert "Zhonya's" in line_with(conn, "Zhonya").text


def test_the_offer_says_how_much_remembering_would_change(conn):
    assert ce.how_often(conn, "zonya") == (3, 2)
    assert "3 more time(s) in 2 stream(s)" in ce.offer_text(conn, "zonya", "Zhonya's")
    assert "isn't anywhere else yet" in ce.offer_text(conn, "teleport", "TP")
