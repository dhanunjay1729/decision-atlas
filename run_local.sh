#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Create the Python virtual environment using the README instructions first.' >&2
  exit 1
fi
if [[ ! -f dist/index.html ]]; then
  npm run build
fi
exec .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port "${DECISION_ATLAS_PORT:-8000}"
