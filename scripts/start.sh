#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
mkdir -p .cache/tmp var/data
export TMPDIR="$PWD/.cache/tmp"
if [ ! -x .venv/bin/python ]; then
  echo 'Python environment missing. Follow README setup first.' >&2
  exit 1
fi
if [ ! -f frontend/dist/index.html ]; then
  echo 'Frontend build missing. Run npm --prefix frontend run build.' >&2
  exit 1
fi
exec .venv/bin/python -m uvicorn workspace.app:create_app --factory --app-dir backend --host 127.0.0.1 --port "${WORKSPACE_PORT:-8765}" --no-access-log
