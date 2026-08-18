#!/usr/bin/env bash
# Run one real Godot validation from an authorized host shell.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$PROJECT_ROOT/godot_project"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
SCRIPT_TO_RUN="${1:-res://scripts/test/test_scene_resource_contract.gd}"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "❌ Repository Python toolchain not found: $PYTHON_BIN" >&2
    exit 2
fi
if [[ ! -f "$PROJECT_DIR/project.godot" ]]; then
    echo "❌ Godot project not found: $PROJECT_DIR" >&2
    exit 2
fi

GUARD_ARGS=(
    --project "$PROJECT_DIR"
    --script "$SCRIPT_TO_RUN"
)
if [[ -n "${GODOT_BIN:-}" ]]; then
    GUARD_ARGS+=(--godot "$GODOT_BIN")
fi

echo "Checking the host process table before Godot validation..."
"$PYTHON_BIN" \
    "$PROJECT_ROOT/.agents/skills/godot-project-operator/scripts/godot_guard.py" \
    status "${GUARD_ARGS[@]}"

echo "Running exactly one synchronous headless Godot validation: $SCRIPT_TO_RUN"
exec "$PYTHON_BIN" \
    "$PROJECT_ROOT/.agents/skills/godot-project-operator/scripts/godot_guard.py" \
    validate "${GUARD_ARGS[@]}"
