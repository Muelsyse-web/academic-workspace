CREATE TABLE conversations(
 id TEXT PRIMARY KEY, title TEXT NOT NULL, course_id TEXT,
 document_ids TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE messages(
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('user','assistant')),content TEXT NOT NULL,
 status TEXT NOT NULL,sources TEXT NOT NULL DEFAULT '[]',created_at TEXT NOT NULL
);
CREATE INDEX messages_conversation ON messages(conversation_id,created_at);
CREATE TABLE embeddings(
 chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
 provider TEXT NOT NULL,model TEXT NOT NULL,dimension INTEGER NOT NULL,
 vector TEXT NOT NULL,created_at TEXT NOT NULL,
 PRIMARY KEY(chunk_id,provider,model)
);
CREATE TABLE embedding_runs(
 id TEXT PRIMARY KEY,status TEXT NOT NULL,progress INTEGER NOT NULL DEFAULT 0,
 provider TEXT NOT NULL,model TEXT NOT NULL,error TEXT,created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX embedding_active ON embedding_runs((1)) WHERE status IN ('queued','processing');
CREATE TABLE embedding_staging(
 run_id TEXT NOT NULL REFERENCES embedding_runs(id) ON DELETE CASCADE,
 chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
 dimension INTEGER NOT NULL,vector TEXT NOT NULL,PRIMARY KEY(run_id,chunk_id)
);
