#!/bin/bash
# ElfieNest unified dependency orchestrator
# Usage: bootstrap <check|ensure|report|hooks> [--tier=dev|build]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/elfienest-uv-cache}"

# Default arguments
TIER="dev"
ACTION="check"

# Colored output
RED=$'\e[1;31m'
GREEN=$'\e[1;32m'
YELLOW=$'\e[1;33m'
CYAN=$'\e[1;36m'
RESET=$'\e[0m'

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        check|ensure|report|hooks)
            ACTION="$1"
            shift
            ;;
        --tier=*)
            TIER="${1#*=}"
            shift
            ;;
        --tier)
            TIER="$2"
            shift 2
            ;;
        *)
            echo "${RED}❌ Unknown argument: $1${RESET}" >&2
            exit 1
            ;;
    esac
done

# Validate tier
if [[ "$TIER" != "dev" && "$TIER" != "build" ]]; then
    echo "${RED}❌ Tier must be dev or build, got: $TIER${RESET}" >&2
    exit 1
fi

# Read the pinned Python version
PYTHON_VERSION_FILE="$PROJECT_ROOT/.python-version"
if [[ ! -f "$PYTHON_VERSION_FILE" ]]; then
    echo "${RED}❌ Missing Python version file: $PYTHON_VERSION_FILE${RESET}" >&2
    exit 1
fi

PINNED_PYTHON_VERSION="$(tr -d '[:space:]' < "$PYTHON_VERSION_FILE")"
if [[ ! "$PINNED_PYTHON_VERSION" =~ ^3\.9\.[0-9]+$ ]]; then
    echo "${RED}❌ .python-version must pin a full Python 3.9 patch version.${RESET}" >&2
    exit 1
fi

# ============================================================================
# Idempotent check functions
# ============================================================================

check_python() {
    local venv_python
    venv_python="$(project_python 2>/dev/null || true)"

    if [[ -z "$venv_python" || ! -f "$venv_python" ]]; then
        return 1
    fi

    # Check version
    if ! "$venv_python" -c "import platform, sys; ok = sys.implementation.name == 'cpython' and platform.python_version() == sys.argv[1]; raise SystemExit(0 if ok else 1)" "$PINNED_PYTHON_VERSION" 2>/dev/null; then
        return 1
    fi

    # Check runtime dependencies
    local runtime_check='import fastapi, httpx, multipart, pydantic, rich, uvicorn, websockets, yaml'
    if ! "$venv_python" -c "$runtime_check" 2>/dev/null; then
        return 1
    fi

    return 0
}

check_dev_python_tools() {
    [[ -x "$PROJECT_ROOT/.venv/bin/pre-commit" ]] && \
        [[ -x "$PROJECT_ROOT/.venv/bin/ruff" ]]
}

ensure_python() {
    if check_python && \
        [[ "${ELFIENEST_FORCE_LOCKED_SYNC:-0}" != "1" ]] && \
        { [[ "$TIER" != "dev" ]] || check_dev_python_tools; }; then
        echo "${GREEN}  ✅ Python $PINNED_PYTHON_VERSION is ready${RESET}"
        return 0
    fi

    echo "${CYAN}  🔧 Preparing Python environment...${RESET}"

    # Check uv
    local uv_bin
    uv_bin="$(command -v uv 2>/dev/null || true)"
    if [[ -z "$uv_bin" ]]; then
        echo "${RED}  ❌ Missing uv package manager${RESET}" >&2
        echo "     macOS: brew install uv" >&2
        echo "     Other platforms: https://docs.astral.sh/uv/getting-started/installation/" >&2
        return 1
    fi

    # Install Python
    if ! "$uv_bin" python install "$PINNED_PYTHON_VERSION" >&2; then
        echo "${RED}  ❌ Failed to install Python $PINNED_PYTHON_VERSION${RESET}" >&2
        return 1
    fi

    # Sync dependencies
    local sync_args="--locked"
    if [[ "$TIER" == "build" ]]; then
        sync_args="$sync_args --no-dev --extra release"
    else
        sync_args="$sync_args --extra dev"
    fi

    if ! UV_PROJECT_ENVIRONMENT="$PROJECT_ROOT/.venv" "$uv_bin" sync $sync_args >&2; then
        echo "${RED}  ❌ Dependency sync failed${RESET}" >&2
        return 1
    fi

    echo "${GREEN}  ✅ Python environment is ready${RESET}"
}

check_node() {
    local node_version
    node_version="$(node --version 2>/dev/null || true)"

    if [[ -z "$node_version" ]]; then
        return 1
    fi

    # Check version >= 20
    local major_version
    major_version="$(echo "$node_version" | sed 's/^v//' | cut -d. -f1)"

    if [[ "$major_version" -lt 20 ]]; then
        echo "${YELLOW}  ⚠️  Node.js version is too old: $node_version (requires >= 20)${RESET}" >&2
        return 1
    fi

    return 0
}

ensure_node() {
    if check_node; then
        echo "${GREEN}  ✅ Node.js is ready${RESET}"
        return 0
    fi

    echo "${RED}  ❌ Missing Node.js 20+${RESET}" >&2
    echo "     macOS: brew install node" >&2
    echo "     Or use nvm: nvm install 20" >&2
    echo "     Other platforms: https://nodejs.org/" >&2
    return 1
}

check_frontend() {
    [[ -f "$PROJECT_ROOT/build/web/manifest.json" ]]
}

ensure_frontend() {
    if check_frontend; then
        echo "${GREEN}  ✅ Frontend build artifacts are ready${RESET}"
        return 0
    fi

    echo "${CYAN}  🔧 Building frontend...${RESET}"

    local frontend_dir="$PROJECT_ROOT/app/interfaces/web/frontend"

    if [[ ! -d "$frontend_dir" ]]; then
        echo "${RED}  ❌ Frontend directory does not exist: $frontend_dir${RESET}" >&2
        return 1
    fi

    # Check Node and the package-scoped pnpm release.
    ensure_node || return 1
    ensure_pnpm "$frontend_dir" || return 1

    # Install dependencies
    if ! run_pnpm "$frontend_dir" install --frozen-lockfile >&2; then
        echo "${RED}  ❌ Failed to install frontend dependencies${RESET}" >&2
        return 1
    fi

    # Build
    if ! run_pnpm "$frontend_dir" build >&2; then
        echo "${RED}  ❌ Frontend build failed${RESET}" >&2
        return 1
    fi

    echo "${GREEN}  ✅ Frontend build completed${RESET}"
}

check_elfie_home() {
    local elfie_home="${ELFIE_HOME:-$HOME/.elfienest}"
    [[ -d "$elfie_home" ]]
}

ensure_elfie_home() {
    if check_elfie_home; then
        echo "${GREEN}  ✅ ELFIE_HOME is ready${RESET}"
        return 0
    fi

    echo "${CYAN}  🔧 Creating data directory...${RESET}"

    local python_bin
    python_bin="$(project_python)" || return 1
    if ! "$python_bin" -c "from app.bootstrap.system_wiring.entrypoints import ensure_elfie_home; ensure_elfie_home()" >&2; then
        echo "${RED}  ❌ Failed to create ELFIE_HOME${RESET}" >&2
        return 1
    fi

    echo "${GREEN}  ✅ ELFIE_HOME has been created${RESET}"
}

check_electron() {
    local desktop_dir="$PROJECT_ROOT/app/interfaces/desktop"
    local electron_bin="$desktop_dir/node_modules/.bin/electron"
    local desktop_main="$PROJECT_ROOT/build/components/desktop-interface/main.js"
    local host_main="$PROJECT_ROOT/app/bootstrap/desktop_host/host_main.mjs"
    local authority_main="$PROJECT_ROOT/infrastructure/godot/lifecycle/electron/authority_main.mjs"

    [[ -x "$electron_bin" ]] && \
    (cd "$desktop_dir" && node -e "const electron = require('electron'); process.exit(typeof electron === 'string' && electron.length > 0 ? 0 : 1)") >/dev/null 2>&1 && \
    [[ -f "$desktop_main" ]] && \
    [[ -f "$host_main" ]] && \
    [[ -f "$authority_main" ]]
}

ensure_electron() {
    if check_electron; then
        echo "${GREEN}  ✅ Electron authority host is ready${RESET}"
        return 0
    fi

    echo "${CYAN}  🔧 Preparing Electron authority host...${RESET}"

    local desktop_dir="$PROJECT_ROOT/app/interfaces/desktop"

    if [[ ! -f "$desktop_dir/package.json" ]]; then
        echo "${YELLOW}  ⚠️  app/interfaces/desktop/package.json does not exist, skipping Electron${RESET}"
        return 0
    fi

    ensure_node || return 1
    ensure_pnpm "$desktop_dir" || return 1

    if ! run_pnpm "$desktop_dir" install --frozen-lockfile >&2; then
        echo "${RED}  ❌ Failed to install Electron dependencies${RESET}" >&2
        return 1
    fi

    if ! ELECTRON_MIRROR="${ELECTRON_MIRROR:-https://npmmirror.com/mirrors/electron/}" run_pnpm "$desktop_dir" rebuild electron >&2; then
        echo "${RED}  ❌ Failed to prepare Electron native runtime${RESET}" >&2
        return 1
    fi

    if ! run_pnpm "$desktop_dir" build >&2; then
        echo "${RED}  ❌ Electron authority host build failed${RESET}" >&2
        return 1
    fi

    if ! check_electron; then
        echo "${RED}  ❌ Electron authority host is still unavailable after preparation${RESET}" >&2
        return 1
    fi

    echo "${GREEN}  ✅ Electron authority host is ready${RESET}"
}

RUNTIME_DEPENDENCIES_HELPER="$SCRIPT_DIR/bootstrap_runtime_dependencies.sh"
if [[ ! -f "$RUNTIME_DEPENDENCIES_HELPER" ]]; then
    echo "${RED}❌ Missing runtime dependency module: $RUNTIME_DEPENDENCIES_HELPER${RESET}" >&2
    exit 1
fi
# shellcheck source=scripts/bootstrap_runtime_dependencies.sh
source "$RUNTIME_DEPENDENCIES_HELPER"

REPORT_HELPER="$SCRIPT_DIR/bootstrap_report.sh"
if [[ ! -f "$REPORT_HELPER" ]]; then
    echo "${RED}❌ Missing dependency report module: $REPORT_HELPER${RESET}" >&2
    exit 1
fi
# shellcheck source=scripts/bootstrap_report.sh
source "$REPORT_HELPER"

ensure_git_hooks() {
    local installer="$SCRIPT_DIR/architecture/install_git_hooks.sh"
    if [[ ! -x "$installer" ]]; then
        echo "${RED}  ❌ Missing Git hook installer: $installer${RESET}" >&2
        return 1
    fi
    bash "$installer"
}

# ============================================================================
# Main flow
# ============================================================================

main() {
    if [[ "$ACTION" == "hooks" ]]; then
        ensure_git_hooks
        return $?
    fi
    if [[ "$ACTION" == "report" ]]; then
        emit_bootstrap_report
        return $?
    fi

    echo ""
    echo "${CYAN}🦊 ElfieNest dependency check${RESET}"
    echo "   mode: ${TIER} | action: ${ACTION}"
    echo ""

    local exit_code=0
    local has_warning=false

    # Python (all tiers)
    echo "📦 Python runtime"
    if [[ "$ACTION" == "ensure" ]]; then
        ensure_python || exit_code=1
    else
        if check_python; then
            echo "${GREEN}  ✅ Python $PINNED_PYTHON_VERSION is ready${RESET}"
        else
            echo "${RED}  ❌ Python is missing or version mismatched${RESET}"
            exit_code=1
        fi
    fi
    echo ""

    if [[ "$ACTION" == "ensure" && "$TIER" == "dev" ]]; then
        echo "📦 Repository Git hooks"
        if [[ $exit_code -eq 0 ]]; then
            ensure_git_hooks || exit_code=1
        else
            echo "${YELLOW}  ⚠️  Skipped until the Python environment is ready${RESET}"
        fi
        echo ""
    fi

    # Node.js (dev tier)
    if [[ "$TIER" == "dev" ]]; then
        echo "📦 Node.js runtime"
        if [[ "$ACTION" == "ensure" ]]; then
            ensure_node || exit_code=1
        else
            if check_node; then
                echo "${GREEN}  ✅ Node.js is ready${RESET}"
            else
                echo "${RED}  ❌ Node.js is missing${RESET}"
                exit_code=1
            fi
        fi
        echo ""
    fi

    # Frontend (all tiers)
    echo "📦 Frontend build artifacts"
    if [[ "$ACTION" == "ensure" ]]; then
        ensure_frontend || exit_code=1
    else
        if check_frontend; then
            echo "${GREEN}  ✅ Frontend build artifacts are ready${RESET}"
        else
            echo "${RED}  ❌ Frontend build artifacts are missing${RESET}"
            exit_code=1
        fi
    fi
    echo ""

    # The exported Runtime is the product dependency. The source editor is
    # resolved lazily by ensure_godot_web only when an export is actually missing.
    echo "📦 Godot Web Runtime"
    if [[ "$ACTION" == "ensure" ]]; then
        ensure_godot_web || exit_code=1
    else
        if check_godot_web; then
            echo "${GREEN}  ✅ Godot Web Runtime is ready${RESET}"
        else
            echo "${RED}  ❌ Godot Web Runtime is missing; the full product cannot start${RESET}"
            exit_code=1
        fi
    fi
    echo ""

    # Ollama (optional capability; official install requires explicit Setup confirmation)
    echo "📦 Ollama"
    if [[ "$ACTION" == "ensure" ]]; then
        local ollama_result
        if ensure_ollama; then
            ollama_result=0
        else
            ollama_result=$?
        fi
        if [[ $ollama_result -eq 2 ]]; then
            has_warning=true
        elif [[ $ollama_result -ne 0 ]]; then
            exit_code=1
        fi
    else
        local ollama_capability
        ollama_capability="$(ollama_capability_state)"
        if [[ "$ollama_capability" == "managed" ]]; then
            echo "${GREEN}  ✅ Public Ollama is ready (optional capability)${RESET}"
        elif [[ "$ollama_capability" == "external" ]]; then
            echo "${GREEN}  ✅ Ollama is ready (external runtime healthy)${RESET}"
        else
            echo "${YELLOW}  ⚠️  Ollama is optional and not installed; configure offline fallback in Setup if needed${RESET}"
            has_warning=true
        fi
    fi
    echo ""

    # Electron（dev tier only）
    if [[ "$TIER" == "dev" ]]; then
        echo "📦 Electron authority host"
        if [[ "$ACTION" == "ensure" ]]; then
            ensure_electron || exit_code=1
        else
            if check_electron; then
                echo "${GREEN}  ✅ Electron authority host is ready${RESET}"
            else
                echo "${RED}  ❌ Electron authority host is missing; the full macOS/Windows product cannot start${RESET}"
                exit_code=1
            fi
        fi
        echo ""
    fi

    # Summary
    if [[ $exit_code -eq 0 ]]; then
        if [[ "$has_warning" == "true" ]]; then
            echo "${YELLOW}⚠️  Some optional dependencies are missing, but core features are available${RESET}"
        else
            echo "${GREEN}✅ All required dependencies are ready${RESET}"
        fi
    else
        echo "${RED}❌ Some dependencies are missing or failed${RESET}"
    fi

    echo ""
    return $exit_code
}

main
