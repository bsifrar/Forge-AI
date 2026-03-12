#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT_DIR/.." && pwd)"

if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a
    source "$ROOT_DIR/.env"
    set +a
fi

WORKSPACE_HOST="${WORKSPACE_HOST:-127.0.0.1}"
WORKSPACE_PORT="${WORKSPACE_PORT:-8091}"

source "$ROOT_DIR/.venv/bin/activate"
export PYTHONPATH="$REPO_ROOT"

curl -fsS "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/health" >/dev/null
curl -fsS "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/workspace/status" >/dev/null
python -m workspace_standalone.workspace_terminal.app settings >/dev/null

echo "Vector smoke test passed."
