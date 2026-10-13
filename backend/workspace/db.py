"""SQLite lifecycle and short, transaction-scoped connections."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid4().hex


class Database:
    def __init__(self, root: Path, migrations=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'workspace.sqlite3'
        self.maintenance = threading.RLock()
        self.migrations = migrations if migrations is not None else {1: Path(__file__).with_name("schema.sql").read_text(), 2: Path(__file__).with_name("notes_schema.sql").read_text(), 4: Path(__file__).with_name("learning_schema.sql").read_text()}
        if migrations is None:
            for source in sorted(Path(__file__).with_name("migrations").glob("*.sql")):
                self.migrations[int(source.stem.split("_",1)[0])] = source.read_text()

    @contextmanager
    def connect(self):
        with self.maintenance:
            con = sqlite3.connect(self.path, timeout=15)
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA foreign_keys=ON')
            con.execute('PRAGMA busy_timeout=15000')
            try:
                with con:
                    yield con
            finally:
                con.close()

    def initialize(self):
        with self.connect() as con:
            con.execute('PRAGMA journal_mode=WAL')
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version > max(self.migrations):
                raise RuntimeError('Database is newer than this application. Upgrade the application.')
            for target, schema in sorted(self.migrations.items()):
                if target <= version:
                    continue
                if version:
                    backups = self.root/'migration-backups'
                    backups.mkdir(exist_ok=True)
                    with sqlite3.connect(backups/f'before-v{target}.sqlite3') as snapshot:
                        con.backup(snapshot)
                con.executescript('BEGIN IMMEDIATE;\n' + schema)
                con.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
                con.execute('INSERT INTO schema_migrations VALUES (?,?)', (target, now()))
                con.execute(f'PRAGMA user_version={int(target)}')
                con.commit()
                version = target

    def all(self, sql, args=()):
        with self.connect() as con:
            return [dict(row) for row in con.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def activity(self, con, kind, description):
        con.execute('INSERT INTO activities VALUES (?,?,?,?)', (new_id(), kind, description, now()))
