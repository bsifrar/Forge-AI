#!/bin/bash

set -euo pipefail

workspace_app_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

workspace_project_root() {
    cd "$(workspace_app_root)/.." && pwd
}

_load_workspace_file() {
    local file="$1"
    [[ -f "$file" ]] || return 0
    while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
        local line key value
        line="${raw_line#${raw_line%%[![:space:]]*}}"
        [[ -z "$line" || "$line" == \\#* || "$line" != *=* ]] && continue
        key="${line%%=*}"
        value="${line#*=}"
        key="${key//[[:space:]]/}"
        value="${value#\"}"
        value="${value%\"}"
        value="${value#\'}"
        value="${value%\'}"
        if [[ -z "${!key:-}" ]]; then
            export "$key=$value"
        fi
    done < "$file"
}

load_workspace_env() {
    local project_root app_root
    app_root="$(workspace_app_root)"
    project_root="$(workspace_project_root)"

    _load_workspace_file "$project_root/.env.workspace"
    _load_workspace_file "$project_root/.env.workspace.secret"

    if [[ -f "$app_root/.env" ]]; then
        _load_workspace_file "$app_root/.env"
    fi

    if [[ -n "${WORKSPACE_API_KEY:-}" && -z "${WORKSPACE_OPENAI_API_KEY:-}" ]]; then
        export WORKSPACE_OPENAI_API_KEY="$WORKSPACE_API_KEY"
    fi
}
