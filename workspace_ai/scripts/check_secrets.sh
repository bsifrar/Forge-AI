#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

PATTERNS=(
  'sk-[A-Za-z0-9_-]{10,}'
  '(OPENAI_API_KEY|WORKSPACE_API_KEY|WORKSPACE_OPENAI_API_KEY)[[:space:]]*=[[:space:]]*["'']?(?![$\{])[A-Za-z0-9_-]{10,}'
)

EXCLUDES=(
  '--glob=!*.pyc'
  '--glob=!.git/**'
  '--glob=!.venv/**'
  '--glob=!.runtime_logs/**'
  '--glob=!workspace_ai/storage/**'
  '--glob=!.env.workspace'
  '--glob=!.env.workspace.secret'
)

found=0
for pattern in "${PATTERNS[@]}"; do
  if rg -n -P -e "$pattern" "${EXCLUDES[@]}" . >/tmp/workspace_secret_scan.out 2>/dev/null; then
    if [[ $found -eq 0 ]]; then
      echo "Potential secrets found in project files:"
    fi
    found=1
    cat /tmp/workspace_secret_scan.out
  fi
done
rm -f /tmp/workspace_secret_scan.out

if [[ $found -ne 0 ]]; then
  echo ""
  echo "Secret scan failed. Move real keys to .env.workspace.secret or local runtime storage."
  exit 1
fi

echo "Secret scan passed."
