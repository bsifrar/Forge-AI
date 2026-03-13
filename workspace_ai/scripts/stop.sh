#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/env.sh"
load_workspace_env

LOG_DIR="${WORKSPACE_STACK_LOG_DIR:-$ROOT_DIR/.runtime_logs}"
WORKSPACE_PORT="${WORKSPACE_PORT:-8092}"

stop_from_pidfile() {
    local pidfile="$1"
    if [[ -f "$pidfile" ]]; then
        local pid
        pid="$(cat "$pidfile" 2>/dev/null || true)"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 1
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        fi
        rm -f "$pidfile"
    fi
}

stop_port() {
    local port="$1"
    local pids
    pids="$(lsof -ti tcp:"$port" 2>/dev/null | sort -u || true)"
    if [[ -n "$pids" ]]; then
        kill $pids 2>/dev/null || true
        sleep 1
        pids="$(lsof -ti tcp:"$port" 2>/dev/null | sort -u || true)"
        if [[ -n "$pids" ]]; then
            kill -9 $pids 2>/dev/null || true
        fi
    fi
}

stop_from_pidfile "$LOG_DIR/workspace.pid"
stop_port "$WORKSPACE_PORT"

echo "Stopped Workspace on port $WORKSPACE_PORT."
