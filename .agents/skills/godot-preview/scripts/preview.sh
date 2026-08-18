#!/bin/bash

set -euo pipefail

SCRIPT_TO_RUN="${1:-}"
if [ -z "$SCRIPT_TO_RUN" ]; then
    echo "Usage: $0 <validation-script>" >&2
    exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../../../.." && pwd)
PROJECT_DIR="$REPO_ROOT/godot_project"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python3"

if [ ! -x "$PYTHON_BIN" ]; then
    echo "Controlled ElfieNest Python toolchain not found: $PYTHON_BIN" >&2
    exit 2
fi
if [ ! -f "$PROJECT_DIR/project.godot" ]; then
    echo "Godot project not found: $PROJECT_DIR" >&2
    exit 2
fi

echo "Running one synchronous headless Godot validation: $SCRIPT_TO_RUN"
exec "$PYTHON_BIN" \
    "$REPO_ROOT/.agents/skills/godot-project-operator/scripts/godot_guard.py" \
    validate \
    --project "$PROJECT_DIR" \
    --script "$SCRIPT_TO_RUN"
