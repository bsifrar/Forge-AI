#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
source "$ROOT_DIR/scripts/lib/env.sh"
load_workspace_env

LOG_DIR="${WORKSPACE_STACK_LOG_DIR:-$ROOT_DIR/.runtime_logs}"
mkdir -p "$LOG_DIR"

WORKSPACE_HOST="${WORKSPACE_HOST:-127.0.0.1}"
WORKSPACE_PORT="${WORKSPACE_PORT:-8091}"
WORKSPACE_ADAPTER_MODE="${WORKSPACE_ADAPTER_MODE:-null}"
WORKSPACE_SYNAPSE_BASE_URL="${WORKSPACE_SYNAPSE_BASE_URL:-http://127.0.0.1:8080}"
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
    echo "Vector port $WORKSPACE_PORT already in use."
    echo "Stop it with: $ROOT_DIR/scripts/stop.sh"
    exit 1
fi

if [[ "$WORKSPACE_ADAPTER_MODE" == "synapse" ]]; then
    echo "Checking external Synapse dependency at $WORKSPACE_SYNAPSE_BASE_URL ..."
    if ! curl -fsS "$WORKSPACE_SYNAPSE_BASE_URL/" >/dev/null 2>&1 || ! curl -fsS "$WORKSPACE_SYNAPSE_BASE_URL/smb/status" >/dev/null 2>&1; then
        echo "Synapse is not healthy at $WORKSPACE_SYNAPSE_BASE_URL"
        echo "Start Synapse separately, or set WORKSPACE_ADAPTER_MODE=null"
        exit 1
    fi
fi

echo "Starting Vector on $WORKSPACE_HOST:$WORKSPACE_PORT ..."
(
    export PYTHONPATH="$REPO_ROOT"
    export WORKSPACE_HOST
    export WORKSPACE_PORT
    export WORKSPACE_ADAPTER_MODE
    export WORKSPACE_SYNAPSE_BASE_URL
    export WORKSPACE_MODEL
    export WORKSPACE_DAILY_CAP
    export WORKSPACE_HOURLY_CAP
    export WORKSPACE_INPUT_PRICE
    export WORKSPACE_OUTPUT_PRICE
    export WORKSPACE_OPENAI_API_KEY="${WORKSPACE_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}"
    cd "$REPO_ROOT"
    source "$ROOT_DIR/.venv/bin/activate"
    python -m workspace_standalone.app.main
) >"$LOG_DIR/workspace.log" 2>&1 &

WORKSPACE_PID=$!
echo "$WORKSPACE_PID" > "$LOG_DIR/workspace.pid"

for _ in {1..45}; do
    if curl -fsS "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/health" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! curl -fsS "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/health" >/dev/null 2>&1; then
    echo "Vector did not become healthy. Check $LOG_DIR/workspace.log"
    exit 1
fi

cd "$REPO_ROOT"
source "$ROOT_DIR/.venv/bin/activate"
export PYTHONPATH="$REPO_ROOT"
python -m workspace_standalone.workspace_terminal.app settings   --api-enabled true   --model "$WORKSPACE_MODEL"   --daily-cap "$WORKSPACE_DAILY_CAP"   --hourly-cap "$WORKSPACE_HOURLY_CAP"   --input-price "$WORKSPACE_INPUT_PRICE"   --output-price "$WORKSPACE_OUTPUT_PRICE" >/dev/null

echo "Vector is ready."
echo "UI:   http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/"
echo "Logs: $LOG_DIR"
echo "Mode: $WORKSPACE_ADAPTER_MODE"
echo "PID:  $WORKSPACE_PID"
