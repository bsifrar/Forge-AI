#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
source "$ROOT_DIR/scripts/lib/env.sh"
load_workspace_env

WORKSPACE_HOST="${WORKSPACE_HOST:-127.0.0.1}"
WORKSPACE_PORT="${WORKSPACE_PORT:-8092}"

export PYTHONPATH="$REPO_ROOT"

curl -fsS "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/health" >/dev/null
curl -fsS "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/workspace/status" >/dev/null
"$ROOT_DIR/.venv/bin/python" -m workspace_ai.workspace_terminal.app settings >/dev/null

echo "Workspace smoke test passed."
