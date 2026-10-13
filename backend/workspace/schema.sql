CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS courses(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL DEFAULT '',
 semester TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#3e6656', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blobs(hash TEXT PRIMARY KEY, size INTEGER NOT NULL, kind TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(
 id TEXT PRIMARY KEY, blob_hash TEXT NOT NULL REFERENCES blobs(hash), title TEXT NOT NULL,
 filename TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
 active_version TEXT, favorite INTEGER NOT NULL DEFAULT 0, topic TEXT NOT NULL DEFAULT '',
 tags TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL,
 UNIQUE(blob_hash)
);
CREATE TABLE IF NOT EXISTS document_courses(
 document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
 PRIMARY KEY(document_id,course_id)
);
CREATE TABLE IF NOT EXISTS document_links(
 source_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 target_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 PRIMARY KEY(source_id,target_id), CHECK(source_id<>target_id)
);
CREATE TABLE IF NOT EXISTS document_versions(
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL, parser_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_units(
 id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
 locator_type TEXT NOT NULL, locator INTEGER NOT NULL CHECK(locator>0),
 heading TEXT NOT NULL DEFAULT '', text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks(
 id TEXT PRIMARY KEY, unit_id TEXT NOT NULL REFERENCES source_units(id) ON DELETE CASCADE,
 version_id TEXT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
 document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 text TEXT NOT NULL, ordinal INTEGER NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED,text, tokenize='unicode61');
CREATE TRIGGER IF NOT EXISTS chunks_delete AFTER DELETE ON chunks BEGIN DELETE FROM chunks_fts WHERE chunk_id=old.id; END;
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0, error TEXT,
 attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS jobs_active_document ON jobs(document_id) WHERE status IN ('queued','processing');
CREATE TABLE IF NOT EXISTS activities(id TEXT PRIMARY KEY, kind TEXT NOT NULL, description TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_tokens(id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, scope TEXT NOT NULL CHECK(scope IN ('read','write')), created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS units_version ON source_units(version_id,locator);
CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id,version_id);
