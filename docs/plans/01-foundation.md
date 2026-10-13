# Foundation and document search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Create a persistent, authenticated local course/document/search API with real five-format parsing.
**Architecture:** sqlite3 repository helper with migration SQL; application factory and middleware; parser independent of storage; bounded durable indexing worker.
**Tech Stack:** Python 3.13, FastAPI, sqlite3, pypdf, python-pptx, python-docx, pytest.

### Task 1: Dependency and test harness
- [x] Create project-local venv and ignores.
- [ ] Install requirements with `PIP_CACHE_DIR=$PWD/.cache/pip TMPDIR=$PWD/.cache/tmp .venv/bin/pip install -r requirements.txt`.
- [ ] Freeze versions into requirements.lock for reproducible setup.

### Task 2: Database and authenticated course API
Files: `backend/workspace/{__init__,db,app,security}.py`, `backend/workspace/schema.sql`, `backend/tests/test_core.py`.
- [ ] Write a failing API test using a temporary directory and the application factory:
```python
with TestClient(create_app(tmp_path), base_url='http://localhost') as client:
    assert client.get('/api/v1/courses').status_code == 401
    token = client.post('/api/v1/session').json()['csrf_token']
    created = client.post('/api/v1/courses', json={'name':'Machine Learning','code':'COMP3340','semester':'2026 Fall'}, headers={'X-CSRF-Token':token})
    assert created.status_code == 201
    assert client.get('/api/v1/courses').json()[0]['code'] == 'COMP3340'
```
- [ ] Run `.venv/bin/python -m pytest backend/tests/test_core.py -v`; require missing API failure.
- [ ] Implement schema migrations with SQLite foreign_keys/WAL/busy_timeout; request-safe connections via context manager. Use JSON row mapping, UUID IDs, UTC timestamps. Bootstrap rejects foreign Origin/Host and non-loopback access. Persist only token hashes; cookie sessions are in-memory and expire on restart.
- [ ] Add tests for CSRF rejection, course validation, update/delete and independent app restart reading the same DB. Implement to green.
- [ ] Commit only verified source/tests/docs.

### Task 3: Standalone parser
Files: `backend/workspace/parsing.py`, `backend/tests/test_parsing.py`, `scripts/generate_fixtures.py`.
- [ ] Write and run failing tests generating PDF, PPTX, DOCX, TXT and Markdown files in temp paths. Assert exact locator and text for two units; headings, tables, UTF-8 and empty/scanned inputs covered.
- [ ] Implement `parse_document(path: Path, kind: str) -> list[dict]`; dict keys `locator_type` (page/slide/paragraph/line), `locator` (positive int), `heading`, `text`. PDF page and PPTX slide are real 1-based indexes. DOCX uses paragraph/ordered table-block numbers, never page labels. TXT/MD split into bounded line blocks with start line. Preserve meaningful empty PDF/slide units for missing-text indication.
- [ ] Reject unsupported, corrupt, encrypted, oversized expanded Office ZIP archives with `ValueError` user-facing errors. Archive limits: 10000 members, 256 MiB expanded, no path traversal, no >1000 compression ratio for entries >1 MiB.
- [ ] Run `.venv/bin/python -m pytest backend/tests/test_parsing.py -v` to green and report scope/limitations.

### Task 4: Import, index and source routes
Files: `backend/workspace/documents.py`, `jobs.py`, `backend/tests/test_documents.py`.
- [ ] Failing tests: upload returns durable job, ready document is searchable, repeated hash deduplicates original, reindex creates new immutable version, old version remains addressable. Corrupt import returns failed job without destroying prior index.
- [ ] Store SHA-256 blobs under owned `originals/`; validate extension before accepting, stream in 1 MiB chunks with 100 MiB cap. Reject bad course IDs. Use per-app bounded worker; on lifespan startup recover queued/interrupted jobs.
- [ ] Store version and units/chunks in a transaction and switch active_version after success; set needs_attention when extracted text is empty. Routes expose units and original by DB ID only.
- [ ] Test metadata tags/topics/favorite/related IDs and course relation updates; implement no path-based read access.
- [ ] Run core/documents/parser tests and commit.

### Task 5: Bilingual search
Files: `backend/workspace/search.py`, `backend/tests/test_search.py`.
- [ ] Failing tests use English, Chinese 1/2/long characters and punctuation; assert course/file/type isolation, pagination, exact locators and version selection.
- [ ] Index text in FTS5 unicode61 for English and use parameterized substring fallback for Han/short queries. Escape LIKE special characters and quote FTS terms, never interpolate query syntax. Rank FTS hits plus matching substring candidates with deduplication. Document fallback latency honestly.
- [ ] Implement search route and actual dashboard counts/activities. Run all first-subsystem tests and record verified evidence.
