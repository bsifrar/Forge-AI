#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$ROOT_DIR/workspace_ai"

cmd="${1:-help}"
shift || true

case "$cmd" in
  install)
    exec "$APP_DIR/scripts/install.sh" "$@"
    ;;
  start|status|smoke)
    export WORKSPACE_ADAPTER_MODE="${WORKSPACE_ADAPTER_MODE:-null}"
    case "$cmd" in
      start) exec "$APP_DIR/scripts/start.sh" "$@" ;;
      status) exec "$APP_DIR/scripts/status.sh" "$@" ;;
      smoke) exec "$APP_DIR/scripts/smoke_test.sh" "$@" ;;
    esac
    ;;
  stop)
    exec "$APP_DIR/scripts/stop.sh" "$@"
    ;;
  secrets)
    exec "$APP_DIR/scripts/check_secrets.sh" "$@"
    ;;
  help|-h|--help)
    cat <<'EOF'
Workspace-AI launcher

Usage:
  ./workspace.sh install
  ./workspace.sh start
  ./workspace.sh stop
  ./workspace.sh status
  ./workspace.sh smoke
  ./workspace.sh secrets

Defaults:
  start/status/smoke run in local null mode unless you explicitly set WORKSPACE_ADAPTER_MODE=external.
EOF
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    exec "$0" help
    ;;
esac
