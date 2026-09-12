"""Transactional local storage. No database server is required."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 display_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','learner')),
 language TEXT NOT NULL DEFAULT 'es', password_salt TEXT NOT NULL,
 password_hash TEXT NOT NULL, password_iterations INTEGER NOT NULL,
 created_at REAL NOT NULL, default_password INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 created_at REAL NOT NULL, expires_at REAL NOT NULL, last_activity REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS session_owner ON sessions(user_id);
CREATE TABLE IF NOT EXISTS bank_versions (
 bank_id TEXT NOT NULL, version TEXT NOT NULL, manifest TEXT NOT NULL,
 questions TEXT NOT NULL, digest TEXT NOT NULL, imported_at REAL NOT NULL,
 PRIMARY KEY(bank_id, version)
);
CREATE TABLE IF NOT EXISTS banks (
 id TEXT PRIMARY KEY, current_version TEXT NOT NULL, settings TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1,
 FOREIGN KEY(id,current_version) REFERENCES bank_versions(bank_id,version)
);
CREATE TABLE IF NOT EXISTS decks (
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 bank_id TEXT NOT NULL, bank_version TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(user_id,bank_id,bank_version),
 FOREIGN KEY(bank_id,bank_version) REFERENCES bank_versions(bank_id,version)
);
CREATE TABLE IF NOT EXISTS attempts (
 id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 bank_id TEXT NOT NULL, bank_version TEXT NOT NULL, kind TEXT NOT NULL,
 status TEXT NOT NULL, started_at REAL NOT NULL, deadline REAL NOT NULL,
 finished_at REAL, duration INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
 metadata TEXT NOT NULL, payload TEXT NOT NULL, result TEXT,
 FOREIGN KEY(bank_id,bank_version) REFERENCES bank_versions(bank_id,version)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_per_user ON attempts(user_id) WHERE status='active';
CREATE INDEX IF NOT EXISTS attempt_history ON attempts(user_id,bank_id,finished_at DESC);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), action TEXT NOT NULL,
 bank_id TEXT, details TEXT NOT NULL, created_at REAL NOT NULL
);
"""

class Storage:
    def __init__(self, path: Path, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.lock = threading.RLock()
        with self.connection() as con:
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 3, 4):
                raise ValueError('Incompatible database. Use a version 3/4 database or a new data directory.')
            # Execute individual statements to keep schema creation transactional.
            for statement in SCHEMA.split(';'):
                if statement.strip():
                    con.execute(statement)
            # Old sessions have no reliable activity timestamp beyond sign-in.
            columns = {row['name'] for row in con.execute('PRAGMA table_info(sessions)')}
            if 'last_activity' not in columns:
                con.execute('ALTER TABLE sessions ADD COLUMN last_activity REAL')
                con.execute('UPDATE sessions SET last_activity=created_at')
            # Version 4 adds RUSH snapshots using existing JSON columns.
            # The marker prevents older engines from misinterpreting these attempts.
            con.execute('PRAGMA user_version=4')
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def connection(self):
        with self.lock:
            con = sqlite3.connect(self.path, timeout=20)
            con.row_factory = sqlite3.Row
            try:
                con.execute('PRAGMA foreign_keys=ON')
                con.execute('PRAGMA busy_timeout=20000')
                con.execute('BEGIN IMMEDIATE')
                yield con
                con.commit()
            except BaseException:
                con.rollback()
                raise
            finally:
                con.close()
