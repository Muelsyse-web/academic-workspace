# Source-linked Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Persist Markdown notes with genuine source quotes, stable backlinks, course/topic association and portable exports.
**Architecture:** A dedicated FastAPI router uses shared app.state.db. A versioned SQL migration adds notes and link tables without changing existing sources. UI editing and safe rendering consume these APIs.
**Tech Stack:** Python sqlite3/FastAPI, React TypeScript, existing Markdown/KaTeX component, pytest/Vitest.

### Backend contract
Files owned by note worker: `backend/workspace/notes.py`, `backend/workspace/notes_schema.sql`, `backend/tests/test_notes.py`. Main integrates schema as migration 2 and router in app.py.

- [ ] Write failing API tests for CRUD and true source links; init module schema explicitly in isolated app fixture until main integration.
- [ ] Router prefix `/api/v1`: GET/POST `/notes`, GET/PATCH/DELETE `/notes/{id}`, GET `/notes/{id}/export`, GET `/notes/export` (define before dynamic route). POST returns 201, DELETE 204.
- [ ] Notes fields: id, title, body, course_id nullable, topic, tags string[], created_at, updated_at; source array fields document_id, version_id, locator_type, locator, quote. Validate quote substring exists at same document/version/locator. Invalid sources return 422; transaction leaves old note intact on invalid edit.
- [ ] GET `/notes?q=&course_id=&topic=` searches title/body in English and Chinese with literal substring or FTS tokens, parameterized queries. Detail includes sources, outgoing_links, backlinks, unresolved_links. Resolve `[[Title]]` only when unique; retain old raw-title→target-id edges through target rename. Broken links stay explicit.
- [ ] Single export is UTF-8 Markdown with readable source references; batch export ZIP contains Markdown and JSON manifest preserving core note metadata and references. No credentials or user-controlled archive paths.
- [ ] Tests include two-note backlinks, target rename without link breakage, same-title ambiguity, multi-course filters, invalid quote rollback, single/bulk export, real persistence across app recreation.
- [ ] Run `.venv/bin/python -m pytest backend/tests/test_notes.py --basetemp=.cache/notes-tests -q`, self-review, report files/results, main conducts independent spec/quality review.

### UI contract (main agent)
Files: `frontend/src/pages/Notes.tsx`, new component tests and E2E assertions.
- [ ] Add note list with title/body search and course selector, create/edit form, responsive editor/preview, save indicator, unsaved-navigation warning.
- [ ] Show source links, backlinks and unresolved titles, export current/bulk notes, link editor to documents/selected quote.
- [ ] Extend browser flow: choose actual source text → create note → see math preview → save → reload and open reference.
