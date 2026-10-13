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

## Setup and checks

Run commands from the project root. Python dependencies are pinned in `requirements.lock`; frontend versions are resolved by `frontend/package-lock.json`. Use `python3 -m venv .venv`, then install with `PIP_CACHE_DIR="$PWD/.cache/pip" TMPDIR="$PWD/.cache/tmp" .venv/bin/python -m pip install -r requirements.lock` and `npm --prefix frontend --cache "$PWD/.cache/npm" ci`. Create cache directories first. Do not replace locked installs with unpinned upgrades.

- Backend: `TMPDIR="$PWD/.cache/tmp" .venv/bin/python -m pytest`.
- UI: `npm --prefix frontend test -- --run` and `npm --prefix frontend run build`.
- E2E: build first, then `npm --prefix frontend run test:e2e`. Current config uses the already installed Google Chrome (`channel: "chrome"`); do not download another browser outside the project. Ports 8766 and 18765 must be free. E2E uses `.cache/e2e-runs` and `scripts/mock_model_server.py`, separate from daily data and real inference.
- Local run: `./scripts/start.sh`, loopback port 8767, default `var/data`. Custom `WORKSPACE_DATA_DIR` must stay inside this project for development. Do not run multiple backends against one data directory.
- Generate synthetic fixtures with `.venv/bin/python scripts/generate_fixtures.py`; never substitute personal course files.

## Implementation contracts

`Database.migrations` includes the base/notes/learning schemas and numbered SQL files under `backend/workspace/migrations`; apply them in numerical order. Current version is 5. Adding a migration also requires reviewing backup schema validation and portable column/schema validation. Do not rewrite historical migrations to alter an existing user's database.

Preserve immutable document versions and validated source quotes through edits, reindex, backup and portable ID remapping. Folder `relative_path` is metadata only. Same-content portable imports keep the destination document metadata and active version; same-name courses/notes create separate records. Keep these rules explicit in previews and docs.

Provider credentials stay in `provider-secret.json` with mode `0600`, never in SQLite, backups or portable exports. Never print actual secrets in test logs or examples. Real LM Studio service/model readiness must be checked separately from Mock; do not start services, load/download models or change model storage outside the project without authorization for that external action.

Coordinate disjoint file ownership before delegated edits. Respect another agent's owned files and uncommitted changes. Update README/ARCHITECTURE when behavior changes; record only executed checks in PROGRESS/ACCEPTANCE. An implemented feature or checked PLAN item does not establish final acceptance, and previously passing tests do not prove later changes pass.

Diagnostics use `backend/workspace/diagnostics.py` and the application lifecycle. Keep `logs/workspace.log` under the data directory, with UTC timestamps, 1 MiB rotation and 3 backups. Log request failures using registered route templates and exception class names only; never raw URLs, arguments, tracebacks containing private input, or credentials. Preserve the self-origin CSP; inline styles are required for React/KaTeX. Logs stay out of exports.
