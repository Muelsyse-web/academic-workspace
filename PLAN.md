# Local Academic Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver the full approved local academic workspace and prove each scenario in ACCEPTANCE.md.
**Architecture:** Single local FastAPI server, SQLite/file persistence, React TypeScript frontend. Parsers and providers return typed data; application services own transactions and citation validation.
**Tech Stack:** React, Vite, FastAPI, SQLite FTS5, pypdf, python-pptx, python-docx, pytest, Vitest, Playwright.

## Milestones and file responsibilities

- [x] M1: User approved SPEC.md and ARCHITECTURE.md on 2026-10-13.
- [ ] M2–M3: `backend/workspace/db.py`, `schema.sql`, `app.py`, `security.py`; migrations, local authentication, courses, dashboard. Tests: `backend/tests/test_core.py`.
- [ ] M4: `parsing.py`, `documents.py`, `jobs.py`; immutable originals, typed locators, background jobs, incremental versions, relations. Tests: `test_parsing.py`, `test_documents.py`.
- [ ] M5: `search.py`; FTS5, Chinese fallback, scoped search, pagination. Tests: `test_search.py`.
- [ ] M6: `providers.py`, `ai.py`; local provider configuration, embeddings, citations, sessions, scoped agent API. Tests: `test_ai.py`.
- [ ] M7: `notes.py`; Markdown, citations, stable internal links, search, export. Tests: `test_notes.py`.
- [ ] M8: `learning.py`; flashcards, SM-2, quizzes, attempts, weak topics, generation. Tests: `test_learning.py`.
- [ ] M9: `frontend/src/` pages and shared components; complete connected UI, accessibility, themes, narrow screens. Tests: Vitest and `frontend/e2e/workspace.spec.ts`.
- [ ] M10: `backup.py`, scripts, README, independent review; backup/restore, portable merge, process restart, performance and all acceptance evidence.

## Execution contract

Each module uses red → implementation → green → review → commit. Exact first subsystem tasks are in `docs/plans/01-foundation.md`; later subsystem plans will be written against the verified interfaces before those modules begin. This avoids guessing integration interfaces. All M1–M10 scope remains required.

## Shared API contracts for first subsystem

`create_app(data_dir: pathlib.Path | None = None) -> FastAPI` stores DB and service handles in `app.state`. All endpoint paths start `/api/v1`. Collection responses use JSON arrays; item responses use objects. IDs are UUID hex strings. Times are UTC ISO strings.

- `GET /health`: public readiness and schema version; no private data.
- `POST /session`: loopback same-origin bootstrap, sets HttpOnly SameSite=Strict local session; responds with CSRF token for `X-CSRF-Token` on writes.
- `GET/POST /courses`; `PATCH/DELETE /courses/{id}`. Course fields: id, name, code, semester, color.
- `POST /documents` multipart files and optional course_id: returns document objects with job_id and status. Upload is streaming and bounded.
- `GET /documents?course_id=&kind=&q=`; `GET /documents/{id}`; `PATCH /documents/{id}` metadata; `POST /documents/{id}/reindex`; `GET /documents/{id}/original`.
- `GET /documents/{id}/units?version_id=` returns source units (id, locator_type, locator, heading, text); `GET /jobs` shows durable statuses.
- `GET /search?q=&course_id=&document_id=&kind=&limit=&offset=` returns `{mode,hits,total}`, each hit includes chunk_id, document_id, version_id, title, locator_type, locator, text.
- `GET /dashboard` returns actual counts and recent activity.

## Integration verification

Run `.venv/bin/python -m pytest`; in frontend run `npm test -- --run`, `npm run build`, and `npm run test:e2e`. Run real backend in isolated data path for process-restart and restore verification. Capture results and remaining gaps in PROGRESS.md and ACCEPTANCE.md. Readiness requires full original scope; no milestone alone completes the Goal.
