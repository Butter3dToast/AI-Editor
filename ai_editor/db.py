"""The clip library: SQLite schema, migrations, and connection handling.

Spec section 5 sets the core principle: analyse a recording once, then let all
three recipes read from this database. That only works if the schema is settled
before the analysis code is written, so the full shape is created here in Phase
0 even though most tables stay empty until later phases.

Schema changes go in a new MIGRATIONS entry, never by editing an old one.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 9


_V1 = """
-- Imported recordings: one row per source video (spec section 7.2).
CREATE TABLE recordings (
    id              INTEGER PRIMARY KEY,
    content_hash    TEXT    NOT NULL UNIQUE,   -- sampled hash; see media.content_hash
    source_type     TEXT    NOT NULL,          -- local_obs | twitch_vod
    source_file     TEXT    NOT NULL,
    game            TEXT,
    title           TEXT,
    duration_sec    REAL,
    width           INTEGER,
    height          INTEGER,
    fps             REAL,
    container       TEXT,
    video_codec     TEXT,
    size_bytes      INTEGER,
    proxy_path      TEXT,
    layout_id       INTEGER REFERENCES layouts(id) ON DELETE SET NULL,
    session_id      TEXT,                      -- links to companion_events
    twitch_vod_id   TEXT,
    recorded_at     TEXT,
    imported_at     TEXT    NOT NULL,
    analysis_status TEXT    NOT NULL DEFAULT 'pending',
    notes           TEXT
);
CREATE INDEX idx_recordings_game ON recordings(game);
CREATE INDEX idx_recordings_status ON recordings(analysis_status);

-- Audio tracks found in a recording. A local OBS recording set up per manual
-- chapter 7 has four; a Twitch VOD has one mixed track.
CREATE TABLE audio_tracks (
    id              INTEGER PRIMARY KEY,
    recording_id    INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    stream_index    INTEGER NOT NULL,
    role            TEXT    NOT NULL DEFAULT 'unknown',  -- mixed|mic|game|voice_chat|music|unknown
    codec           TEXT,
    channels        INTEGER,
    sample_rate     INTEGER,
    bit_rate        INTEGER,
    extracted_path  TEXT,                      -- WAV pulled out for analysis
    separated_path  TEXT,                      -- Demucs vocal stem, when separation ran
    UNIQUE(recording_id, stream_index)
);

-- Per-second signal timeline (spec section 7.3). Long and narrow on purpose:
-- new signal types need no schema change.
CREATE TABLE signals (
    recording_id    INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    t_sec           INTEGER NOT NULL,
    name            TEXT    NOT NULL,          -- rms|silence|laughter|gunfire|chat_velocity|hype|...
    value           REAL    NOT NULL,
    PRIMARY KEY (recording_id, t_sec, name)
) WITHOUT ROWID;
CREATE INDEX idx_signals_name ON signals(recording_id, name);

-- Word-level transcript. Word timestamps are required for captions and for
-- never cutting mid-word (spec section 7.3).
CREATE TABLE transcript_words (
    id              INTEGER PRIMARY KEY,
    recording_id    INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    idx             INTEGER NOT NULL,
    word            TEXT    NOT NULL,
    start_sec       REAL    NOT NULL,
    end_sec         REAL    NOT NULL,
    confidence      REAL,
    speaker         TEXT,                      -- 'creator' once speaker ID runs (Phase 2)
    UNIQUE(recording_id, idx)
);
CREATE INDEX idx_words_time ON transcript_words(recording_id, start_sec);

-- Candidate clips (spec section 7.3 "Clip library record").
CREATE TABLE clips (
    clip_id         TEXT    PRIMARY KEY,
    recording_id    INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    start_sec       REAL    NOT NULL,
    end_sec         REAL    NOT NULL,
    score           REAL    NOT NULL DEFAULT 0,
    signals_json    TEXT,
    game_events_json TEXT,
    llm_tags_json   TEXT,
    llm_summary     TEXT,
    transcript      TEXT,
    used_in_json    TEXT,
    user_rating     INTEGER,                   -- 1 thumbs up, -1 thumbs down, NULL unrated
    pinned          INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL
);
CREATE INDEX idx_clips_score ON clips(score DESC);
CREATE INDEX idx_clips_recording ON clips(recording_id, start_sec);

-- Stream Companion output (spec section 7.1). Written while the creator plays,
-- matched to a recording during ingest.
CREATE TABLE companion_events (
    id                  INTEGER PRIMARY KEY,
    session_id          TEXT    NOT NULL,
    event_type          TEXT    NOT NULL,      -- marker|marker_short|obs_*|lol_event
    wall_clock          TEXT    NOT NULL,      -- ISO timestamp, the anchor for alignment
    stream_time_sec     REAL,
    recording_time_sec  REAL,
    payload_json        TEXT,
    recording_id        INTEGER REFERENCES recordings(id) ON DELETE SET NULL
);
CREATE INDEX idx_events_session ON companion_events(session_id, wall_clock);
CREATE INDEX idx_events_recording ON companion_events(recording_id);

-- Twitch chat, used for the chat-velocity signal (streams only).
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY,
    recording_id    INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    t_sec           REAL    NOT NULL,
    username        TEXT,
    message         TEXT
);
CREATE INDEX idx_chat_time ON chat_messages(recording_id, t_sec);

-- Facecam / gameplay / UI rectangles drawn once per game layout
-- (spec section 7.2, manual chapter 6 step 6).
CREATE TABLE layouts (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    game            TEXT,
    facecam_json    TEXT,
    gameplay_json   TEXT,
    ui_regions_json TEXT,
    created_at      TEXT    NOT NULL
);

-- Style profiles learned from reference videos (spec section 7.4).
CREATE TABLE style_profiles (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    games_json      TEXT,
    applies_to_json TEXT,
    profile_json    TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

-- Plain-English tips compiled into structured rules (spec section 7.5).
-- is_note marks tips the compiler could not turn into a precise rule; those are
-- still passed to the LLM as guidance (manual chapter 14.5).
CREATE TABLE rules (
    id              INTEGER PRIMARY KEY,
    rule_id         TEXT    NOT NULL UNIQUE,
    source_text     TEXT    NOT NULL,
    scope_json      TEXT,
    rule_json       TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    is_note         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL
);

-- Edit plans (spec section 7.7): what the renderer and exporter read and the
-- review screen edits.
CREATE TABLE edit_plans (
    id                  INTEGER PRIMARY KEY,
    plan_id             TEXT    NOT NULL UNIQUE,
    recipe              TEXT    NOT NULL,      -- lets_play|highlights|shorts
    recording_ids_json  TEXT    NOT NULL,
    profile_id          INTEGER REFERENCES style_profiles(id) ON DELETE SET NULL,
    plan_json           TEXT    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'draft',
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL
);

-- Let's Play series numbering across sessions (spec section 7.6).
CREATE TABLE series (
    id                  INTEGER PRIMARY KEY,
    name                TEXT    NOT NULL UNIQUE,
    game                TEXT,
    next_part_number    INTEGER NOT NULL DEFAULT 1,
    settings_json       TEXT,
    created_at          TEXT    NOT NULL
);

CREATE TABLE series_parts (
    id              INTEGER PRIMARY KEY,
    series_id       INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    part_number     INTEGER NOT NULL,
    plan_id         TEXT    REFERENCES edit_plans(plan_id) ON DELETE SET NULL,
    recording_id    INTEGER REFERENCES recordings(id) ON DELETE SET NULL,
    start_sec       REAL,
    end_sec         REAL,
    title           TEXT,
    release_date    TEXT,
    status          TEXT    NOT NULL DEFAULT 'planned',
    carried_over    INTEGER NOT NULL DEFAULT 0,
    UNIQUE(series_id, part_number)
);

-- Every decision the creator makes in review (spec section 7.10). No model
-- training: this is the record that preference fitting reads later.
CREATE TABLE feedback (
    id              INTEGER PRIMARY KEY,
    ts              TEXT    NOT NULL,
    action          TEXT    NOT NULL,          -- accept|reject|trim|reorder|effect_removed|...
    clip_id         TEXT    REFERENCES clips(clip_id) ON DELETE SET NULL,
    plan_id         TEXT,
    game            TEXT,
    features_json   TEXT,
    detail_json     TEXT
);
CREATE INDEX idx_feedback_game ON feedback(game, action);

-- Resumable job queue (spec section 3: long jobs must survive a restart).
CREATE TABLE jobs (
    id              INTEGER PRIMARY KEY,
    job_type        TEXT    NOT NULL,
    payload_json    TEXT,
    recording_id    INTEGER REFERENCES recordings(id) ON DELETE CASCADE,
    status          TEXT    NOT NULL DEFAULT 'queued',  -- queued|running|paused|complete|failed
    priority        INTEGER NOT NULL DEFAULT 100,
    progress        REAL    NOT NULL DEFAULT 0,
    step            TEXT,
    error_code      TEXT,
    error_message   TEXT,
    created_at      TEXT    NOT NULL,
    started_at      TEXT,
    finished_at     TEXT
);
CREATE INDEX idx_jobs_status ON jobs(status, priority, id);

-- One row per finished step, so a resumed job skips completed work.
-- cache_key is derived from the source hash plus the step's inputs, which is
-- how reruns skip finished work (spec section 5).
CREATE TABLE job_steps (
    id              INTEGER PRIMARY KEY,
    job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    step_name       TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending',
    cache_key       TEXT,
    output_path     TEXT,
    started_at      TEXT,
    finished_at     TEXT,
    UNIQUE(job_id, step_name)
);
CREATE INDEX idx_job_steps_cache ON job_steps(cache_key);
"""


# Phase 1B: which audio track a transcript came from. Captions must be the
# creator's voice only (spec section 7.6); a transcript of the mixed track also
# contains game dialogue and teammates, and later stages need to know that.
_V2 = """
ALTER TABLE transcript_words ADD COLUMN source_role TEXT;
"""


# Phase 2A: the local AI's verdict on each clip. Its own table, not columns
# on clips, because unrated clips are deleted and cut again whenever a video
# is made (refresh_clips); the verdict must outlive that. Matched to a clip
# by its id, or failing that by the stretch of recording it covers.
_V3 = """
CREATE TABLE ai_clip_notes (
    clip_id         TEXT    PRIMARY KEY,
    recording_id    INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    start_sec       REAL    NOT NULL,
    end_sec         REAL    NOT NULL,
    rating          REAL    NOT NULL,          -- 1-10
    summary         TEXT,
    reason          TEXT,
    tags_json       TEXT,
    stands_alone    INTEGER,                   -- 1: makes sense without context (Shorts)
    model           TEXT    NOT NULL,
    prompt_version  INTEGER NOT NULL,
    created_at      TEXT    NOT NULL
);
CREATE INDEX idx_ai_notes_recording ON ai_clip_notes(recording_id, start_sec);
"""


# Phase 2D: Undo and Redo in Review, kept after AI-Editor closes (the
# creator's choice). Each row is one change to a plan: the plan before and
# after, the library clips it re-cut, and the feedback it logged. An undone
# change's feedback is marked undone, so a misclick teaches nothing; whatever
# learns from feedback later must skip those rows.
_V4 = """
CREATE TABLE plan_history (
    id              INTEGER PRIMARY KEY,
    plan_id         TEXT    NOT NULL REFERENCES edit_plans(plan_id) ON DELETE CASCADE,
    what            TEXT    NOT NULL,          -- "removing clip 4", in plain words
    before_json     TEXT    NOT NULL,
    after_json      TEXT    NOT NULL,
    clips_json      TEXT,                      -- [{clip_id, before, after}] for re-cut clips
    feedback_json   TEXT,                      -- ids of the feedback rows it logged
    undone          INTEGER NOT NULL DEFAULT 0,
    made_at         TEXT    NOT NULL
);
CREATE INDEX idx_plan_history ON plan_history(plan_id, id);
ALTER TABLE feedback ADD COLUMN undone INTEGER NOT NULL DEFAULT 0;
"""


# Phase 2D-2: fixing captions in Review. A fixed word is fixed in the
# transcript itself, so every video, Short, title and AI summary gets it; the
# word as first heard is kept in `original` so it can be put back. A hidden
# word is never shown as a caption but stays in the transcript. word_fixes are
# the fixes the creator asked to remember: every stream, and new ones too.
_V5 = """
ALTER TABLE transcript_words ADD COLUMN original TEXT;
ALTER TABLE transcript_words ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0;
ALTER TABLE transcript_words ADD COLUMN fixed_by INTEGER;
CREATE TABLE word_fixes (
    id              INTEGER PRIMARY KEY,
    wrong           TEXT    NOT NULL UNIQUE,   -- as heard, lower case, no punctuation
    right           TEXT    NOT NULL,          -- as it should be written
    created_at      TEXT    NOT NULL
);
ALTER TABLE plan_history ADD COLUMN words_json TEXT;
"""


# Phase 2F-1: what Dawnwalker's quest tracker said, read every few seconds
# from the preview copy (analysis/quests.py), so parts aren't split mid-quest.
# quest_reads says a recording has been read, even if nothing was legible.
_V6 = """
CREATE TABLE quest_log (
    recording_id    INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    t_sec           REAL    NOT NULL,
    time_of_day     TEXT,
    quest           TEXT,
    step            TEXT,
    PRIMARY KEY (recording_id, t_sec)
);
CREATE TABLE quest_reads (
    recording_id    INTEGER PRIMARY KEY REFERENCES recordings(id) ON DELETE CASCADE,
    every_sec       REAL    NOT NULL,
    reader          TEXT    NOT NULL,
    read_at         TEXT    NOT NULL
);
"""


# Phase 2G-1: style profiles. A profile is an editing look measured from
# reference videos (style/measure.py) and set with sliders. Only the numbers
# and the AI's notes are kept: never the videos, frames or sound. The table
# from version 1 is used as it is: games_json, applies_to_json (the kinds of
# video) and profile_json (the sliders as saved; {} until then); the draft
# comes from the references' measurements.
_V7 = """
ALTER TABLE style_profiles ADD COLUMN notes_json TEXT NOT NULL DEFAULT '[]';
CREATE TABLE style_references (
    id              INTEGER PRIMARY KEY,
    profile_id      INTEGER NOT NULL REFERENCES style_profiles(id) ON DELETE CASCADE,
    source          TEXT    NOT NULL,          -- a YouTube link or a file on this PC
    title           TEXT,
    duration_sec    REAL,
    measured_json   TEXT,                      -- empty until analysed
    notes_json      TEXT,                      -- what the AI saw in its frames
    error           TEXT,
    analysed_at     TEXT,
    UNIQUE (profile_id, source)
);
"""


# Phase 2I-2: your friends on Discord, told apart. A friend is a name, a caption
# colour and a voice fingerprint (the average of every stretch named theirs);
# each stream's voices are kept with what they sound like, so naming one names
# the same voice in other streams. transcript_words.voice: the stream's voice a
# friend's word was heard in ("A", "B"...), so a name can be taken back.
_V8 = """
ALTER TABLE transcript_words ADD COLUMN voice TEXT;
CREATE TABLE friends (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    colour          TEXT    NOT NULL,
    voice_json      TEXT    NOT NULL,
    seconds         REAL    NOT NULL DEFAULT 0,   -- how much talking the fingerprint is from
    created_at      TEXT    NOT NULL
);
CREATE TABLE voices (
    recording_id    INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    label           TEXT    NOT NULL,              -- "A", "B"... most talking first
    voice_json      TEXT    NOT NULL,
    seconds         REAL    NOT NULL,
    sample_start    REAL    NOT NULL,
    sample_end      REAL    NOT NULL,
    friend_id       INTEGER REFERENCES friends(id) ON DELETE SET NULL,
    PRIMARY KEY (recording_id, label)
);
"""


# Your taste per game (Phase 3A-2, learning/taste.py): the learned model, and how
# it did against the usual score when tested, which decides whether it's used.
_V9 = """
CREATE TABLE taste_models (
    game            TEXT    PRIMARY KEY,
    model_json      TEXT,                      -- NULL: too few ratings yet
    ratings         INTEGER NOT NULL,
    taste_check     REAL,                      -- liked above disliked, this model
    usual_check     REAL,                      -- the same, the usual score
    learned_at      TEXT    NOT NULL
);
"""

MIGRATIONS: dict[int, str] = {1: _V1, 2: _V2, 3: _V3, 4: _V4, 5: _V5, 6: _V6, 7: _V7, 8: _V8,
                              9: _V9}


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open the library, creating its folder if needed, with sane pragmas.

    WAL lets the UI read while a job writes; foreign keys are off by default in
    SQLite and must be switched on per connection.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection) -> int:
    """Apply any migrations newer than the database's recorded version."""
    version = current_version(conn)
    for target in sorted(MIGRATIONS):
        if target > version:
            conn.executescript(MIGRATIONS[target])
            conn.execute(f"PRAGMA user_version = {target}")
            version = target
    conn.commit()
    return version


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Open the library and bring its schema up to date, keeping a copy first."""
    conn = connect(db_path)
    version = current_version(conn)
    if 0 < version < SCHEMA_VERSION:
        keep_copy(conn, Path(db_path), version)
    migrate(conn)
    return conn


def keep_copy(conn: sqlite3.Connection, db_path: Path, version: int) -> Path:
    """A whole copy of the library as it was, beside it, before it's upgraded:
    "library.before-v9.db". Never deleted by AI-Editor; delete it yourself once
    the new version has been working for a while."""
    target = db_path.with_name(f"{db_path.stem}.before-v{SCHEMA_VERSION}{db_path.suffix}")
    if not target.exists():
        copy = sqlite3.connect(target)
        try:
            conn.backup(copy)
        finally:
            copy.close()
    return target


@contextmanager
def session(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Short-lived connection that commits on success and rolls back on error."""
    conn = init_db(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
