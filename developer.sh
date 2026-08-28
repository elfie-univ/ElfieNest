#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_VERSION_FILE="$SCRIPT_DIR/.python-version"
PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"

if [[ "${1:-}" == "docs" ]]; then
  shift
  if ! command -v pnpm >/dev/null 2>&1; then
    echo "❌ Docs preview requires pnpm 10.12.1 (Node.js 20+)." >&2
    echo "💡 Install the repository toolchain, then run ./developer.sh docs again." >&2
    exit 1
  fi
  if [[ ! -x "$SCRIPT_DIR/docs/node_modules/.bin/vitepress" ]]; then
    echo "❌ Docs preview dependencies are missing: $SCRIPT_DIR/docs/node_modules" >&2
    echo "💡 Run: pnpm --dir docs install --frozen-lockfile" >&2
    exit 1
  fi
  cd "$SCRIPT_DIR"
  exec pnpm --dir docs dev --host "${DOCS_HOST:-127.0.0.1}" --open "$@"
fi

if [[ -n "${ELFIENEST_PYTHON:-}" ]]; then
  echo "❌ Developer Tool does not accept ELFIENEST_PYTHON; must use the repo-pinned CPython 3.9.25 environment." >&2
  exit 1
fi

if [[ ! -f "$PYTHON_VERSION_FILE" ]]; then
  echo "❌ Missing Python version file: $PYTHON_VERSION_FILE" >&2
  exit 1
fi

PINNED_PYTHON_VERSION="$(tr -d '[:space:]' < "$PYTHON_VERSION_FILE")"
if [[ ! "$PINNED_PYTHON_VERSION" =~ ^3\.9\.[0-9]+$ ]]; then
  echo "❌ .python-version must be pinned to a complete CPython 3.9 patch version." >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "❌ Developer Tool requires repo-pinned environment: $SCRIPT_DIR/.venv/bin/python3" >&2
  echo "💡 Run ./elfienest.sh version to set up the development environment." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import platform, sys; ok = sys.implementation.name == "cpython" and platform.python_version() == sys.argv[1]; raise SystemExit(0 if ok else 1)' "$PINNED_PYTHON_VERSION" >/dev/null 2>&1; then
  echo "❌ Developer Tool must use the repo-pinned CPython $PINNED_PYTHON_VERSION environment." >&2
  echo "💡 Run ./elfienest.sh version to repair the development environment." >&2
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

# For --help or -h, skip builds and show help directly
if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
  exec "$PYTHON_BIN" -m devtools "$@"
fi

# For subcommand help, such as elfie-lab --help, skip builds too
if [[ "${2:-}" == "--help" ]] || [[ "${2:-}" == "-h" ]]; then
  exec "$PYTHON_BIN" -m devtools "$@"
fi

case "${1:-}" in
  elfie-lab|nest-lab)
    "$PYTHON_BIN" scripts/build_godot_web.py --ensure
    "$PYTHON_BIN" scripts/build_devtools_web.py --ensure
    ;;
  brain-eval)
    # The no-action form launches the unified web service, so keep the Nest
    # page usable even when this is the first command run on a clean checkout.
    case "${2:-}" in
      catalog|capture|compare|calibrate)
        ;;
      *)
        "$PYTHON_BIN" scripts/build_godot_web.py --ensure
        ;;
    esac
    "$PYTHON_BIN" scripts/build_devtools_web.py --ensure
    ;;
esac
exec "$PYTHON_BIN" -m devtools "$@"
