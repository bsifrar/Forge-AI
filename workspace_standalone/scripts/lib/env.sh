#!/bin/bash

set -euo pipefail

workspace_app_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

workspace_project_root() {
    cd "$(workspace_app_root)/.." && pwd
}

load_workspace_env() {
    local project_root app_root
    app_root="$(workspace_app_root)"
    project_root="$(workspace_project_root)"

    if [[ -f "$project_root/.env.workspace" ]]; then
        set -a
        source "$project_root/.env.workspace"
        set +a
    fi

    if [[ -f "$project_root/.env.workspace.secret" ]]; then
        set -a
        source "$project_root/.env.workspace.secret"
        set +a
    fi

    # Legacy fallback during transition only.
    if [[ -f "$app_root/.env" ]]; then
        set -a
        source "$app_root/.env"
        set +a
    fi

    if [[ -n "${WORKSPACE_API_KEY:-}" && -z "${WORKSPACE_OPENAI_API_KEY:-}" ]]; then
        export WORKSPACE_OPENAI_API_KEY="$WORKSPACE_API_KEY"
    fi
}
