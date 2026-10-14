import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def data_dir():
    return Path(os.environ.get('AWE_DATA_DIR', Path.home() / '.local/share/agent-waiting-experience')).expanduser()


class Store:
    def __init__(self, root=None):
        os.umask(0o077)
        self.root = Path(root) if root else data_dir()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.path = self.root / 'timeline.db'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, provider TEXT NOT NULL, state TEXT NOT NULL,
                    turn_id TEXT NOT NULL, started REAL NOT NULL, updated REAL NOT NULL,
                    event TEXT NOT NULL, detail TEXT NOT NULL, opened_turn TEXT DEFAULT '',
                    sequence REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS transitions (
                    id INTEGER PRIMARY KEY, session_id TEXT, turn_id TEXT, state TEXT,
                    event TEXT, timestamp REAL);
                CREATE TABLE IF NOT EXISTS imports (
                    path TEXT PRIMARY KEY, provider TEXT, size INTEGER, mtime INTEGER,
                    session_id TEXT, events INTEGER, extractor_version INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS timeline (
                    event_id TEXT PRIMARY KEY, date TEXT NOT NULL, title TEXT NOT NULL,
                    summary TEXT NOT NULL, category TEXT NOT NULL, kind TEXT NOT NULL,
                    source_session_id TEXT NOT NULL, source_provider TEXT NOT NULL,
                    source_path TEXT NOT NULL, source_line INTEGER NOT NULL,
                    source_hash TEXT NOT NULL, confidence REAL NOT NULL,
                    read_at REAL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS timeline_date ON timeline(date DESC);
            ''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(imports)')}
            if 'extractor_version' not in columns:
                db.execute('ALTER TABLE imports ADD COLUMN extractor_version INTEGER NOT NULL DEFAULT 0')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))

    def clear_history(self):
        # Serialize deletion with imports, so an in-flight import cannot restore deleted history.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('PRAGMA secure_delete=ON')
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('history_enabled', 'false'))
            db.execute('DELETE FROM timeline')
            db.execute('DELETE FROM imports')
        with self.connect() as db:
            db.execute('VACUUM')
        (self.root / 'human-review.csv').unlink(missing_ok=True)

