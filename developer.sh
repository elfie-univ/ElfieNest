#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${ELFIENEST_PYTHON:-$SCRIPT_DIR/.venv/bin/python3}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "❌ Developer Tool 需要项目锁定环境: $SCRIPT_DIR/.venv/bin/python3" >&2
  echo "💡 请先运行 ./install.sh" >&2
  exit 1
fi

cd "$SCRIPT_DIR"
if [[ "${1:-}" == "build-godot-web" ]]; then
  shift
  exec "$PYTHON_BIN" scripts/build_godot_web.py "$@"
fi
exec "$PYTHON_BIN" -m devtools "$@"
