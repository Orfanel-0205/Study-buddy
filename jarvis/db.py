"""SQLite storage shared by tasks, conversations, change proposals and the activity log.

Everything lives in a single file, jarvis.db, inside the Jarvis data folder.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = [
    # version 1
    """
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        due_date TEXT,
        priority TEXT NOT NULL DEFAULT 'medium',
        status TEXT NOT NULL DEFAULT 'todo',
        project TEXT NOT NULL DEFAULT '',
        project_path TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        parent_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT
    );
    CREATE INDEX idx_tasks_parent ON tasks(parent_id);

    CREATE TABLE conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'general',
        project_path TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'general',
        sources TEXT NOT NULL DEFAULT '[]',
        model TEXT NOT NULL DEFAULT '',
        stopped INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_messages_conv ON messages(conversation_id);

    CREATE TABLE proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_root TEXT NOT NULL,
        path TEXT NOT NULL,
        kind TEXT NOT NULL,
        new_content TEXT,
        original_exists INTEGER NOT NULL,
        original_hash TEXT NOT NULL DEFAULT '',
        written_hash TEXT NOT NULL DEFAULT '',
        diff TEXT NOT NULL DEFAULT '',
        warnings TEXT NOT NULL DEFAULT '[]',
        note TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT 'assistant',
        status TEXT NOT NULL DEFAULT 'pending',
        backup_path TEXT NOT NULL DEFAULT '',
        error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        summary TEXT NOT NULL,
        details TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_actions_session ON actions(session_id);
    """,
    # version 2: phones paired with this computer
    """
    CREATE TABLE devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        last_seen TEXT,
        revoked_at TEXT
    );
    """,
    # version 3: cached embeddings for search by meaning (key = hash of model + text)
    """
    CREATE TABLE embeddings (
        key TEXT PRIMARY KEY,
        vec BLOB NOT NULL
    );
    """,
    # version 4: images in chat messages, and flashcards for studying
    """
    ALTER TABLE messages ADD COLUMN images TEXT NOT NULL DEFAULT '[]';

    CREATE TABLE decks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
        front TEXT NOT NULL,
        back TEXT NOT NULL,
        ease REAL NOT NULL DEFAULT 2.5,
        interval INTEGER NOT NULL DEFAULT 0,
        reps INTEGER NOT NULL DEFAULT 0,
        lapses INTEGER NOT NULL DEFAULT 0,
        due TEXT NOT NULL,
        last_reviewed TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX idx_cards_deck ON cards(deck_id);
    CREATE INDEX idx_cards_due ON cards(due);
    """,
    # version 5: two-way sync between Jarvis on the laptop and Jarvis on the phone.
    # Every task, deck and card gets a permanent id (uid) shared by both copies, and deletions
    # leave a small record so the other copy deletes the item too.
    """
    ALTER TABLE tasks ADD COLUMN uid TEXT;
    ALTER TABLE decks ADD COLUMN uid TEXT;
    ALTER TABLE cards ADD COLUMN uid TEXT;
    UPDATE tasks SET uid = lower(hex(randomblob(16))) WHERE uid IS NULL;
    UPDATE decks SET uid = lower(hex(randomblob(16))) WHERE uid IS NULL;
    UPDATE cards SET uid = lower(hex(randomblob(16))) WHERE uid IS NULL;
    CREATE UNIQUE INDEX idx_tasks_uid ON tasks(uid);
    CREATE UNIQUE INDEX idx_decks_uid ON decks(uid);
    CREATE UNIQUE INDEX idx_cards_uid ON cards(uid);

    CREATE TRIGGER tasks_new_uid AFTER INSERT ON tasks WHEN NEW.uid IS NULL
    BEGIN UPDATE tasks SET uid = lower(hex(randomblob(16))) WHERE id = NEW.id; END;
    CREATE TRIGGER decks_new_uid AFTER INSERT ON decks WHEN NEW.uid IS NULL
    BEGIN UPDATE decks SET uid = lower(hex(randomblob(16))) WHERE id = NEW.id; END;
    CREATE TRIGGER cards_new_uid AFTER INSERT ON cards WHEN NEW.uid IS NULL
    BEGIN UPDATE cards SET uid = lower(hex(randomblob(16))) WHERE id = NEW.id; END;

    CREATE TABLE deletions (
        kind TEXT NOT NULL,
        uid TEXT NOT NULL,
        deleted_at TEXT NOT NULL,
        PRIMARY KEY (kind, uid)
    );
    CREATE TRIGGER tasks_deleted AFTER DELETE ON tasks BEGIN
        INSERT OR REPLACE INTO deletions (kind, uid, deleted_at)
        VALUES ('task', OLD.uid, strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'));
    END;
    CREATE TRIGGER decks_deleted AFTER DELETE ON decks BEGIN
        INSERT OR REPLACE INTO deletions (kind, uid, deleted_at)
        VALUES ('deck', OLD.uid, strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'));
    END;
    CREATE TRIGGER cards_deleted AFTER DELETE ON cards BEGIN
        INSERT OR REPLACE INTO deletions (kind, uid, deleted_at)
        VALUES ('card', OLD.uid, strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'));
    END;

    CREATE TABLE sync_state (
        peer TEXT PRIMARY KEY,
        last_pull TEXT NOT NULL DEFAULT '',
        last_push TEXT NOT NULL DEFAULT '',
        last_ok TEXT NOT NULL DEFAULT '',
        last_error TEXT NOT NULL DEFAULT ''
    );
    """,
    # v6: coding practice progress (kept on each device; not synced)
    """
    CREATE TABLE practice (
        exercise_id TEXT PRIMARY KEY,
        code TEXT NOT NULL DEFAULT '',
        attempts INTEGER NOT NULL DEFAULT 0,
        best INTEGER NOT NULL DEFAULT 0,
        total INTEGER NOT NULL DEFAULT 0,
        solved_at TEXT,
        updated_at TEXT NOT NULL
    );
    """,
    # v7: progress tracking. Tasks get an area (study / dev) so studying and developing are counted
    # separately; every flashcard review is logged (and synced) for the progress charts.
    """
    ALTER TABLE tasks ADD COLUMN area TEXT NOT NULL DEFAULT '';
    UPDATE tasks SET area = 'dev' WHERE project != '';
    CREATE TABLE study_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT UNIQUE,
        card_uid TEXT NOT NULL DEFAULT '',
        deck_uid TEXT NOT NULL DEFAULT '',
        grade TEXT NOT NULL,
        reviewed_at TEXT NOT NULL
    );
    CREATE INDEX idx_reviews_at ON study_reviews(reviewed_at);
    CREATE TRIGGER study_reviews_new_uid AFTER INSERT ON study_reviews WHEN NEW.uid IS NULL
    BEGIN UPDATE study_reviews SET uid = lower(hex(randomblob(16))) WHERE id = NEW.id; END;
    """,
    # v8: check-ins (how you feel before studying or coding; synced) and daily Coding Focus totals
    """
    CREATE TABLE checkins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT UNIQUE,
        at TEXT NOT NULL,
        mood INTEGER NOT NULL,
        energy INTEGER NOT NULL,
        stress INTEGER NOT NULL,
        sleep_hours REAL,
        body TEXT NOT NULL DEFAULT '[]',
        note TEXT NOT NULL DEFAULT '',
        context TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX idx_checkins_at ON checkins(at);
    CREATE TRIGGER checkins_new_uid AFTER INSERT ON checkins WHEN NEW.uid IS NULL
    BEGIN UPDATE checkins SET uid = lower(hex(randomblob(16))) WHERE id = NEW.id; END;
    CREATE TABLE focus_days (
        day TEXT PRIMARY KEY,
        coding_seconds INTEGER NOT NULL DEFAULT 0,
        alerts INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    );
    """,
]


def now_iso() -> str:
    # Milliseconds, so sync can tell apart two edits made in the same second. This format still
    # sorts correctly against older second-precision times ("...:05+00:00" < "...:05.123+00:00").
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _migrate(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for i, script in enumerate(SCHEMA[version:], start=version + 1):
                conn.executescript(script)
                conn.execute(f"PRAGMA user_version = {i}")
