# Project development rules

- Scope is this project directory only. Never read existing personal course files for development.
- Use `.venv/bin/python`, `.cache/tmp`, `.cache/pip`, `.cache/npm`, project-local browser downloads. No external paid APIs, public servers, or private document uploads.
- SPEC.md and ARCHITECTURE.md were approved by the user on 2026-10-13. Proceed with implementation and routine choices without repeated design approval.
- Use `feat/local-academic-workspace`; the new repository itself isolates the user's original directories.
- Keep parser, DB, search, provider, learning, and API/UI boundaries clear. Use parameterized SQL and migrations.
- Write meaningful failing tests before business logic. Run relevant pytest, Vitest, build and Playwright checks. Record actual results in PROGRESS.md; distinguish mock from real model tests.
- User authorized subagents: give disjoint file ownership; do not revert others' edits. Main agent integrates and reviews.
- Preserve source files, actual locators, and immutable citation versions. Never invent DOCX page numbers or model evidence.
- Keep code/data/caches inside project. Bind loopback only. Do not commit secrets, originals, runtime data or dependency directories.
