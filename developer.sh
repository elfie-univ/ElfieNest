#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_VERSION_FILE="$SCRIPT_DIR/.python-version"
PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"

if [[ -n "${ELFIENEST_PYTHON:-}" ]]; then
  echo "❌ Developer Tool 不接受 ELFIENEST_PYTHON；必须使用项目锁定的 CPython 3.9.25 环境。" >&2
  exit 1
fi

if [[ ! -f "$PYTHON_VERSION_FILE" ]]; then
  echo "❌ 缺少 Python 版本文件: $PYTHON_VERSION_FILE" >&2
  exit 1
fi

PINNED_PYTHON_VERSION="$(tr -d '[:space:]' < "$PYTHON_VERSION_FILE")"
if [[ ! "$PINNED_PYTHON_VERSION" =~ ^3\.9\.[0-9]+$ ]]; then
  echo "❌ .python-version 必须固定到 CPython 3.9 的完整补丁版本。" >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "❌ Developer Tool 需要项目锁定环境: $SCRIPT_DIR/.venv/bin/python3" >&2
  echo "💡 请先运行 ./install.sh" >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import platform, sys; ok = sys.implementation.name == "cpython" and platform.python_version() == sys.argv[1]; raise SystemExit(0 if ok else 1)' "$PINNED_PYTHON_VERSION" >/dev/null 2>&1; then
  echo "❌ Developer Tool 必须使用项目锁定的 CPython $PINNED_PYTHON_VERSION 环境。" >&2
  echo "💡 请运行 ./elfienest.sh version 补齐开发环境，或运行 ./install.sh 安装本机应用。" >&2
  exit 1
fi

cd "$SCRIPT_DIR"
if [[ "${1:-}" == "build-godot-web" ]]; then
  shift
  exec "$PYTHON_BIN" scripts/build_godot_web.py "$@"
fi
if [[ "${1:-}" == "build-godot-dedicated" ]]; then
  shift
  exec "$PYTHON_BIN" scripts/build_godot_dedicated.py "$@"
fi
if [[ "${1:-}" == "build-devtools-web" ]]; then
  shift
  exec "$PYTHON_BIN" scripts/build_devtools_web.py "$@"
fi
case "${1:-}" in
  elfie-lab|nest-lab)
    "$PYTHON_BIN" scripts/build_godot_web.py --ensure
    "$PYTHON_BIN" scripts/build_devtools_web.py --ensure
    ;;
esac
exec "$PYTHON_BIN" -m devtools "$@"
