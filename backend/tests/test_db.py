import sqlite3
import tempfile
import unittest
from pathlib import Path
from workspace.db import Database


class DatabaseTests(unittest.TestCase):
    def test_migrations_repeat_and_transactions_rollback(self):
        with tempfile.TemporaryDirectory(dir='.cache/tmp') as directory:
            db = Database(Path(directory), migrations={1:Path("backend/workspace/schema.sql").read_text()})
            db.initialize()
            db.initialize()
            with db.connect() as con:
                self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 1)
                self.assertEqual(con.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                with db.connect() as con:
                    con.execute("INSERT INTO courses(id,name,code,semester,color,created_at) VALUES ('a','Course','','','#333','now')")
                    con.execute("INSERT INTO document_courses(document_id,course_id) VALUES ('missing','a')")
            with db.connect() as con:
                self.assertEqual(con.execute('SELECT count(*) FROM courses').fetchone()[0], 0)

    def test_upgrade_keeps_data_and_creates_recovery_snapshot(self):
        with tempfile.TemporaryDirectory(dir='.cache/tmp') as directory:
            root=Path(directory)
            first={1:'CREATE TABLE example(id TEXT PRIMARY KEY);'}
            db=Database(root,migrations=first)
            db.initialize()
            with db.connect() as con:
                con.execute("INSERT INTO example VALUES ('kept')")
            upgraded=Database(root,migrations={**first,2:'ALTER TABLE example ADD COLUMN title TEXT DEFAULT "untitled";'})
            upgraded.initialize()
            with upgraded.connect() as con:
                self.assertEqual(con.execute('SELECT title FROM example WHERE id="kept"').fetchone()[0],'untitled')
                self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertTrue((root/'migration-backups'/'before-v2.sqlite3').is_file())
            broken=Database(root,migrations={**first,2:'SELECT 1;',3:'ALTER TABLE example ADD COLUMN flag TEXT; INVALID SQL;'})
            with self.assertRaises(sqlite3.OperationalError):
                broken.initialize()
            with upgraded.connect() as con:
                self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],2)
                self.assertNotIn('flag',[r[1] for r in con.execute('PRAGMA table_info(example)')])
