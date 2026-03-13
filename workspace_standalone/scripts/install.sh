#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/env.sh"
load_workspace_env

PYTHON_BIN="${WORKSPACE_PYTHON_BIN:-python3.12}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Required interpreter not found: $PYTHON_BIN"
    echo "Set WORKSPACE_PYTHON_BIN to a supported Python, for example:"
    echo "  export WORKSPACE_PYTHON_BIN=python3.12"
    exit 1
fi

if [[ -x ".venv/bin/python" ]]; then
    EXISTING_VERSION="$(".venv/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    TARGET_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    if [[ -n "$EXISTING_VERSION" && "$EXISTING_VERSION" != "$TARGET_VERSION" ]]; then
        echo "Existing workspace venv uses Python $EXISTING_VERSION, but install target is Python $TARGET_VERSION."
        echo "Remove the old workspace venv and rerun:"
        echo "  rm -rf $ROOT_DIR/.venv"
        exit 1
    fi
fi

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "Vector environment ready."
echo "Venv: $ROOT_DIR/.venv"
echo "Start with: $ROOT_DIR/scripts/start.sh"
