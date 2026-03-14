#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
source "$ROOT_DIR/scripts/lib/env.sh"
load_workspace_env

LOG_DIR="${WORKSPACE_STACK_LOG_DIR:-$ROOT_DIR/.runtime_logs}"
mkdir -p "$LOG_DIR"

WORKSPACE_HOST="${WORKSPACE_HOST:-127.0.0.1}"
WORKSPACE_PORT="${WORKSPACE_PORT:-8092}"
WORKSPACE_ADAPTER_MODE="${WORKSPACE_ADAPTER_MODE:-null}"
WORKSPACE_EXTERNAL_BASE_URL="${WORKSPACE_EXTERNAL_BASE_URL:-http://127.0.0.1:8080}"
WORKSPACE_MODEL="${WORKSPACE_MODEL:-gpt-5.4}"
WORKSPACE_DAILY_CAP="${WORKSPACE_DAILY_CAP:-20}"
WORKSPACE_HOURLY_CAP="${WORKSPACE_HOURLY_CAP:-30}"
WORKSPACE_INPUT_PRICE="${WORKSPACE_INPUT_PRICE:-2.5}"
WORKSPACE_OUTPUT_PRICE="${WORKSPACE_OUTPUT_PRICE:-15}"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
    echo "Missing $ROOT_DIR/.venv/bin/python"
    echo "Run: $ROOT_DIR/scripts/install.sh"
    exit 1
fi

if lsof -ti tcp:"$WORKSPACE_PORT" >/dev/null 2>&1; then
    echo "Workspace port $WORKSPACE_PORT already in use."
    echo "Stop it with: $ROOT_DIR/scripts/stop.sh"
    exit 1
fi

if [[ "$WORKSPACE_ADAPTER_MODE" == "external" ]]; then
    echo "Checking external memory service dependency at $WORKSPACE_EXTERNAL_BASE_URL ..."
    if ! curl -fsS "$WORKSPACE_EXTERNAL_BASE_URL/" >/dev/null 2>&1 || ! curl -fsS "$WORKSPACE_EXTERNAL_BASE_URL/smb/status" >/dev/null 2>&1; then
        echo "External memory service is not healthy at $WORKSPACE_EXTERNAL_BASE_URL"
        echo "Start the external memory service separately, or set WORKSPACE_ADAPTER_MODE=null"
        exit 1
    fi
fi

echo "Starting Workspace on $WORKSPACE_HOST:$WORKSPACE_PORT ..."
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT"
export WORKSPACE_HOST="$WORKSPACE_HOST"
export WORKSPACE_PORT="$WORKSPACE_PORT"
export WORKSPACE_ADAPTER_MODE="$WORKSPACE_ADAPTER_MODE"
export WORKSPACE_EXTERNAL_BASE_URL="$WORKSPACE_EXTERNAL_BASE_URL"
export WORKSPACE_MODEL="$WORKSPACE_MODEL"
export WORKSPACE_DAILY_CAP="$WORKSPACE_DAILY_CAP"
export WORKSPACE_HOURLY_CAP="$WORKSPACE_HOURLY_CAP"
export WORKSPACE_INPUT_PRICE="$WORKSPACE_INPUT_PRICE"
export WORKSPACE_OUTPUT_PRICE="$WORKSPACE_OUTPUT_PRICE"
export WORKSPACE_OPENAI_API_KEY="${WORKSPACE_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}"

if command -v setsid >/dev/null 2>&1; then
    # Prefer a fresh session when available so the API process survives the parent shell lifecycle.
    nohup setsid "$ROOT_DIR/.venv/bin/python" -m workspace_ai.app.main </dev/null >"$LOG_DIR/workspace.log" 2>&1 &
else
    nohup "$ROOT_DIR/.venv/bin/python" -m workspace_ai.app.main </dev/null >"$LOG_DIR/workspace.log" 2>&1 &
fi

WORKSPACE_PID=$!
echo "$WORKSPACE_PID" > "$LOG_DIR/workspace.pid"

for _ in {1..45}; do
    if curl -fsS "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/health" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! curl -fsS "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/health" >/dev/null 2>&1; then
    echo "Workspace did not become healthy. Check $LOG_DIR/workspace.log"
    exit 1
fi

cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT"
"$ROOT_DIR/.venv/bin/python" -m workspace_ai.workspace_terminal.app settings   --api-enabled true   --model "$WORKSPACE_MODEL"   --daily-cap "$WORKSPACE_DAILY_CAP"   --hourly-cap "$WORKSPACE_HOURLY_CAP"   --input-price "$WORKSPACE_INPUT_PRICE"   --output-price "$WORKSPACE_OUTPUT_PRICE" >/dev/null

if ! curl -fsS "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/health" >/dev/null 2>&1; then
    echo "Workspace exited after startup. Check $LOG_DIR/workspace.log"
    exit 1
fi

sleep 2
if ! curl -fsS "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/health" >/dev/null 2>&1; then
    echo "Workspace became unhealthy immediately after startup. Check $LOG_DIR/workspace.log"
    exit 1
fi

echo "Workspace is ready."
echo "UI:   http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/"
echo "Logs: $LOG_DIR"
echo "Mode: $WORKSPACE_ADAPTER_MODE"
echo "PID:  $WORKSPACE_PID"
