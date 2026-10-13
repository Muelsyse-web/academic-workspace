CREATE TABLE IF NOT EXISTS notes(
 id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
 course_id TEXT REFERENCES courses(id) ON DELETE SET NULL,
 topic TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS note_sources(
 note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL,
 document_id TEXT NOT NULL REFERENCES documents(id),
 version_id TEXT NOT NULL REFERENCES document_versions(id),
 locator_type TEXT NOT NULL, locator INTEGER NOT NULL CHECK(locator>0),
 quote TEXT NOT NULL CHECK(length(trim(quote))>0),
 PRIMARY KEY(note_id,ordinal)
);
CREATE TABLE IF NOT EXISTS note_links(
 source_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
 raw_title TEXT NOT NULL,
 target_id TEXT REFERENCES notes(id) ON DELETE SET NULL,
 deleted_target_id TEXT,
 PRIMARY KEY(source_id,raw_title)
);
CREATE TRIGGER IF NOT EXISTS note_target_delete BEFORE DELETE ON notes BEGIN
 UPDATE note_links SET deleted_target_id=old.id WHERE target_id=old.id;
END;
CREATE INDEX IF NOT EXISTS notes_course_topic ON notes(course_id,topic);
CREATE INDEX IF NOT EXISTS notes_title ON notes(title);
CREATE INDEX IF NOT EXISTS note_links_target ON note_links(target_id);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(note_id UNINDEXED,title,body,tokenize='unicode61');
CREATE TRIGGER IF NOT EXISTS notes_insert AFTER INSERT ON notes BEGIN
 INSERT INTO notes_fts(note_id,title,body) VALUES(new.id,new.title,new.body);
END;
CREATE TRIGGER IF NOT EXISTS notes_update AFTER UPDATE OF title,body ON notes BEGIN
 DELETE FROM notes_fts WHERE note_id=old.id;
 INSERT INTO notes_fts(note_id,title,body) VALUES(new.id,new.title,new.body);
END;
CREATE TRIGGER IF NOT EXISTS notes_delete AFTER DELETE ON notes BEGIN
 DELETE FROM notes_fts WHERE note_id=old.id;
END;
