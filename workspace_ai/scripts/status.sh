#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/env.sh"
load_workspace_env

WORKSPACE_HOST="${WORKSPACE_HOST:-127.0.0.1}"
WORKSPACE_PORT="${WORKSPACE_PORT:-8092}"
WORKSPACE_ADAPTER_MODE="${WORKSPACE_ADAPTER_MODE:-null}"
WORKSPACE_EXTERNAL_BASE_URL="${WORKSPACE_EXTERNAL_BASE_URL:-http://127.0.0.1:8080}"
WORKSPACE_DB_PATH="${WORKSPACE_STORAGE_PATH:-$ROOT_DIR/storage/workspace.db}"
WORKSPACE_LOG_DIR="${WORKSPACE_STACK_LOG_DIR:-$ROOT_DIR/.runtime_logs}"

fetch() {
    local label="$1"
    local url="$2"
    echo "== $label =="
    if curl -fsS "$url" 2>/dev/null; then
        echo ""
    else
        echo "unreachable"
    fi
    echo ""
}

human_size() {
    local path="$1"
    if [[ ! -e "$path" ]]; then
        echo "0B"
        return
    fi
    du -sh "$path" 2>/dev/null | awk '{print $1}'
}

path_bytes() {
    local path="$1"
    if [[ ! -e "$path" ]]; then
        echo 0
        return
    fi
    python3 -c 'from pathlib import Path; import sys; p = Path(sys.argv[1]); print(0 if not p.exists() else (p.stat().st_size if p.is_file() else sum(x.stat().st_size for x in p.rglob("*") if x.is_file())))' "$path"
}

size_warning() {
    local bytes="$1"
    local warn_at="$2"
    local critical_at="$3"
    local label="$4"
    if (( bytes >= critical_at )); then
        echo "critical: $label exceeds threshold"
    elif (( bytes >= warn_at )); then
        echo "warning: $label exceeds threshold"
    fi
}

DB_BYTES="$(path_bytes "$WORKSPACE_DB_PATH")"
LOG_BYTES="$(path_bytes "$WORKSPACE_LOG_DIR")"
DB_WARNING="$(size_warning "$DB_BYTES" $((500 * 1024 * 1024)) $((2 * 1024 * 1024 * 1024)) "workspace.db")"
LOG_WARNING="$(size_warning "$LOG_BYTES" $((1024 * 1024 * 1024)) $((5 * 1024 * 1024 * 1024)) "runtime logs")"

echo "Workspace Status"
echo "Workspace host:   $WORKSPACE_HOST"
echo "Workspace port:   $WORKSPACE_PORT"
echo "Adapter mode:  $WORKSPACE_ADAPTER_MODE"
if [[ "$WORKSPACE_ADAPTER_MODE" == "null" ]]; then
    echo "Mode note:     local-only development mode (no external dependency required)"
else
    echo "Mode note:     EXTERNAL MODE ACTIVE — using remote adapter at $WORKSPACE_EXTERNAL_BASE_URL"
fi
echo "Workspace DB:    $(human_size "$WORKSPACE_DB_PATH") ($WORKSPACE_DB_PATH)"
echo "Runtime logs:   $(human_size "$WORKSPACE_LOG_DIR") ($WORKSPACE_LOG_DIR)"
if [[ -n "$DB_WARNING" ]]; then
    echo "DB warning:     $DB_WARNING"
fi
if [[ -n "$LOG_WARNING" ]]; then
    echo "Log warning:    $LOG_WARNING"
fi
echo ""

if [[ "$WORKSPACE_ADAPTER_MODE" == "external" ]]; then
    fetch "External Service Root" "$WORKSPACE_EXTERNAL_BASE_URL/"
    fetch "External Service Memory Status" "$WORKSPACE_EXTERNAL_BASE_URL/smb/status"
fi

fetch "Workspace UI Health" "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/health"
fetch "Workspace Status" "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/workspace/status"
fetch "Workspace Adapter Status" "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/workspace/adapter/status"
fetch "Workspace Settings" "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/workspace/settings"
