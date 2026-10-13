#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
mkdir -p .cache/tmp docs/verification
export TMPDIR="$PWD/.cache/tmp"
export npm_config_cache="$PWD/.cache/npm"
.venv/bin/python scripts/generate_fixtures.py
.venv/bin/python -m pytest --junitxml=docs/verification/pytest.xml -q
npm --prefix frontend test -- --run --reporter=json --outputFile="$PWD/docs/verification/vitest.json"
npm --prefix frontend run build
npm --prefix frontend run test:e2e
.venv/bin/python scripts/verify_persistence.py
.venv/bin/python scripts/benchmark_search.py
