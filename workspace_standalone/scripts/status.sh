#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/env.sh"
load_workspace_env

WORKSPACE_HOST="${WORKSPACE_HOST:-127.0.0.1}"
WORKSPACE_PORT="${WORKSPACE_PORT:-8091}"
WORKSPACE_ADAPTER_MODE="${WORKSPACE_ADAPTER_MODE:-null}"
WORKSPACE_SYNAPSE_BASE_URL="${WORKSPACE_SYNAPSE_BASE_URL:-http://127.0.0.1:8080}"

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

echo "Vector Status"
echo "Vector host:   $WORKSPACE_HOST"
echo "Vector port:   $WORKSPACE_PORT"
echo "Adapter mode:  $WORKSPACE_ADAPTER_MODE"
echo ""

if [[ "$WORKSPACE_ADAPTER_MODE" == "synapse" ]]; then
    fetch "Synapse Root (external)" "$WORKSPACE_SYNAPSE_BASE_URL/"
    fetch "Synapse SMB Status (external)" "$WORKSPACE_SYNAPSE_BASE_URL/smb/status"
fi

fetch "Vector UI Health" "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/health"
fetch "Vector Status" "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/workspace/status"
fetch "Vector Adapter Status" "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/workspace/adapter/status"
fetch "Vector Settings" "http://${WORKSPACE_HOST}:${WORKSPACE_PORT}/workspace/settings"
