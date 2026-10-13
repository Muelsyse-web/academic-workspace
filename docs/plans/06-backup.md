# Backup, Restore and Portable Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Preserve all core data across restart, backup/restore and portable export/import without leaking credentials or corrupting the current library.
**Architecture:** SQLite backup API plus content-addressed originals under one maintenance lock. Validate imports in project-local staging first. Restore rejects active indexing/inference and retains a recovery point before switching data.
**Tech Stack:** sqlite3, zipfile, hashlib, FastAPI UploadFile/FileResponse, pytest.

### Backup and restore
Files: `backend/workspace/backup.py`, `backend/tests/test_backup.py`.
- [ ] Test-first `/backup` GET returns ZIP containing consistent SQLite snapshot, originals and SHA256 manifest. Exclude provider-secret, agent token records, logs, caches and migration backups. Use streamed file reads/temporary output instead of loading whole library into RAM.
- [ ] `/restore` POST multipart archive and explicit confirmation restores after integrity/checksum/schema/foreign-key validation. Reject path traversal, symlinks, duplicates, unsupported archive/schema, excessive expansion and checksum mismatch; leave current data intact on failure.
- [ ] Reject active document/embedding jobs or live generation before replacement. Keep recovery database and originals; restore old state if final replacement fails. Invalidate Agent tokens and browser sessions; UI reconnects local session.
- [ ] Tests preserve course/document/note/source/conversation/review data and hashes; corrupt backups cannot overwrite current DB. Verify restore into a fresh app and existing app; new app restart reads restored state.

### Portable merge and UI
Main agent owns portable export/import and Settings UI.
- [ ] JSON+originals portable archive explicitly versioned, separate from replace-library restore. Map IDs and relationships, de-duplicate blobs, preserve evidence versions and study records, report conflicts before merge and reject invalid entries transactionally.
- [ ] Settings offers backup download, restore file and confirmation, portable export and import preview/confirm; shows maintenance errors and progress.
- [ ] End-to-end backup/restore and process restart tested with project-local synthetic data. README documents recovery paths and limits honestly.
