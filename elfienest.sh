#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ============================================================================
# Runtime mode detection (based on Electron supervisor_config.ts:55-60)
# ============================================================================

detect_runtime_mode() {
    local script_dir="$1"

    # Install directory flags: resources/python-core/ or manifest.json
    if [ -d "$script_dir/resources/python-core" ] || [ -f "$script_dir/manifest.json" ]; then
        echo "installed_runtime"
        return
    fi

    # Source tree flags: pyproject.toml or scripts/serve.py
    if [ -f "$script_dir/pyproject.toml" ] || [ -f "$script_dir/scripts/serve.py" ]; then
        echo "source_development"
        return
    fi

    echo "unknown"
}

MODE="$(detect_runtime_mode "$SCRIPT_DIR")"

case "$MODE" in
    installed_runtime)
        export ELFIENEST_RUNTIME_MODE="release"
        # Production mode: direct Python Core call (dependencies packaged)
        exec "$SCRIPT_DIR/resources/python-core/ElfieNestCore" "$@"
        ;;
    source_development)
        export ELFIENEST_RUNTIME_MODE="development"
        export ELFIENEST_SOURCE_ROOT="$SCRIPT_DIR"
        # Source target selection is independent from the installed product
        # namespace.  The Python dispatcher resolves the source task first;
        # only its short-lived child scope receives ELFIE_HOME.
        unset ELFIE_HOME
        # Development mode: silent dependency check, only show install when missing.
        # Help is a shell-owned command and piped command streams should not trigger
        # a dependency installation before they can report their requested output.
        skip_dependency_repair=false
        skip_dependency_check=false
        case "${ELFIENEST_SKIP_AUTO_REPAIR:-0}" in
            1|true|TRUE|yes|YES) skip_dependency_repair=true ;;
        esac
        if [[ $# -gt 0 ]]; then
            case "$1" in
                help|h|\?|--help|-h) skip_dependency_check=true ;;
            esac
        elif [[ ! -t 0 ]]; then
            skip_dependency_check=true
        fi
        if [[ "$skip_dependency_check" != "true" ]]; then
            if ! "$SCRIPT_DIR/scripts/bootstrap.sh" check --tier=dev >/dev/null 2>&1; then
                if [[ "$skip_dependency_repair" == "true" ]]; then
                    echo "  ❌ Dependency installation failed: automatic repair is disabled by ELFIENEST_SKIP_AUTO_REPAIR" >&2
                    exit 1
                fi
                echo "  🦊 Detected missing dependencies, installing..." >&2
                if ! "$SCRIPT_DIR/scripts/bootstrap.sh" ensure --tier=dev; then
                    echo "  ❌ Dependency installation failed, please fix as instructed" >&2
                    exit 1
                fi
            fi
        fi
        ;;
    unknown)
        echo "❌ Cannot detect runtime mode: neither source tree nor install directory" >&2
        exit 1
        ;;
esac

# ============================================================================
# Development mode: command dispatch and interactive menu
# ============================================================================

PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"

show_logo() {
    clear
    CYAN=$'\e[1;36m'
    YELLOW=$'\e[1;33m'
    RESET=$'\e[0m'
    echo ""
    echo "${CYAN}███████╗██╗     ███████╗██╗███████╗     ${YELLOW}███╗   ██╗███████╗███████╗████████╗${RESET}"
    echo "${CYAN}██╔════╝██║     ██╔════╝██║██╔════╝     ${YELLOW}████╗  ██║██╔════╝██╔════╝╚══██╔╝${RESET}"
    echo "${CYAN}█████╗  ██║     █████╗  ██║█████╗       ${YELLOW}██╔██╗ ██║█████╗  ███████╗   ██║   ${RESET}"
    echo "${CYAN}██╔══╝  ██║     ██╔══╝  ██║██╔══╝       ${YELLOW}██║╚██╗██║██╔══╝  ╚════██║   ██║   ${RESET}"
    echo "${CYAN}███████╗███████╗██║     ██║███████╗     ${YELLOW}██║ ╚████║███████╗███████║   ██║   ${RESET}"
    echo "${CYAN}╚══════╝╚══════╝╚═╝     ╚═╝╚══════╝     ${YELLOW}╚═╝  ╚═══╝╚══════╝╚══════╝   ╚═╝   ${RESET}"
    echo ""
    echo "            🦊 Embodied AI Creature Simulation"
    echo ""
}

show_help() {
    echo "  ┌─────────────────────────────────────────────────────────┐"
    echo "  │  Commands                                               │"
    echo "  └─────────────────────────────────────────────────────────┘"
    echo ""
    echo "    serve*         Run service in foreground (dev mode)"
    echo "    start*         Start background service"
    echo "    restart*       Force restart service"
    echo "    stop*          Stop current service"
    echo "    status*        Show service and port status"
    echo "    web            Open Web console for an already running service"
    echo "    mobile         Show mobile access URL and QR code"
    echo "    config         Provider, model, Food and tool configuration (interactive menu)"
    echo "    owner          Owner account menu"
    echo "    doctor         Run local diagnostics and auto-repair"
    echo "    db*            Database tools"
    echo "    version        Show version info"
    echo "    help           Show this help"
    echo "    exit           Exit interactive mode"
    echo ""
    echo "  ┌─────────────────────────────────────────────────────────┐"
    echo "  │  Examples                                               │"
    echo "  └─────────────────────────────────────────────────────────┘"
    echo ""
    echo "    elfienest> serve              # Start with the configured model"
    echo "    elfienest> exit                # Exit"
    echo ""
}

interactive_mode() {
    exec "$PYTHON_BIN" scripts/elfienest.py --interactive
}

if [ $# -eq 0 ]; then
    interactive_mode
else
    command="$1"
    case "$command" in
    restart)
        "$PYTHON_BIN" scripts/elfienest.py "$@"
        ;;
    serve)
        shift
        "$PYTHON_BIN" scripts/elfienest.py serve "$@"
        ;;
    help|h|\?|--help|-h)
        show_logo
        show_help
        exit 0
        ;;
    v)
        "$PYTHON_BIN" scripts/elfienest.py version
        ;;
    *)
        "$PYTHON_BIN" scripts/elfienest.py "$@"
        ;;
    esac
fi
