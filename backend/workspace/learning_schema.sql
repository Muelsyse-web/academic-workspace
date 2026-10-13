-- SM-2 v1 and manual quizzes; historical records intentionally retain snapshots.
CREATE TABLE IF NOT EXISTS flashcards(
 id TEXT PRIMARY KEY, front TEXT NOT NULL, back TEXT NOT NULL,
 course_id TEXT REFERENCES courses(id) ON DELETE SET NULL, topic TEXT NOT NULL DEFAULT '',
 sources TEXT NOT NULL DEFAULT '[]', due_at TEXT NOT NULL,
 ease REAL NOT NULL DEFAULT 2.5 CHECK(ease>=1.3), repetitions INTEGER NOT NULL DEFAULT 0,
 interval_days INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS flashcards_due ON flashcards(due_at);
CREATE INDEX IF NOT EXISTS flashcards_scope ON flashcards(course_id,topic);
CREATE TABLE IF NOT EXISTS reviews(
 id TEXT PRIMARY KEY, flashcard_id TEXT NOT NULL, course_id TEXT, topic TEXT NOT NULL,
 rating TEXT NOT NULL CHECK(rating IN ('again','hard','good','easy')),
 reviewed_at TEXT NOT NULL, due_at TEXT NOT NULL, ease REAL NOT NULL,
 repetitions INTEGER NOT NULL, interval_days INTEGER NOT NULL,
 algorithm TEXT NOT NULL DEFAULT 'sm2-v1', idempotency_key TEXT,
 UNIQUE(flashcard_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS reviews_card ON reviews(flashcard_id,reviewed_at);
CREATE TABLE IF NOT EXISTS quizzes(
 id TEXT PRIMARY KEY, title TEXT NOT NULL,
 course_id TEXT REFERENCES courses(id) ON DELETE SET NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quiz_questions(
 id TEXT PRIMARY KEY, quiz_id TEXT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL, content TEXT NOT NULL, UNIQUE(quiz_id,ordinal)
);
CREATE TABLE IF NOT EXISTS attempts(
 id TEXT PRIMARY KEY, quiz_id TEXT NOT NULL, quiz_title TEXT NOT NULL, course_id TEXT,
 score INTEGER NOT NULL, total INTEGER NOT NULL, created_at TEXT NOT NULL,
 idempotency_key TEXT, request_json TEXT NOT NULL,
 UNIQUE(quiz_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS attempt_answers(
 attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
 question_id TEXT NOT NULL, ordinal INTEGER NOT NULL, topic TEXT NOT NULL,
 selected TEXT NOT NULL, text TEXT NOT NULL, self_correct INTEGER,
 correct INTEGER NOT NULL CHECK(correct IN (0,1)), question TEXT NOT NULL,
 PRIMARY KEY(attempt_id,question_id), UNIQUE(attempt_id,ordinal)
);
CREATE INDEX IF NOT EXISTS attempts_scope ON attempts(course_id,created_at);
CREATE INDEX IF NOT EXISTS answers_topic ON attempt_answers(topic,correct);
