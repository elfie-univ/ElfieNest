#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ============================================================================
# Runtime state detection for source development or installed runtime
# ============================================================================

detect_runtime_state() {
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

RUNTIME_STATE="$(detect_runtime_state "$SCRIPT_DIR")"

case "$RUNTIME_STATE" in
    installed_runtime)
        # Production mode: direct Python Core call (dependencies packaged)
        exec "$SCRIPT_DIR/resources/python-core/ElfieNestCore" "$@"
        ;;
    source_development)
        # Development mode: silent dependency check, only show install when missing
        if ! "$SCRIPT_DIR/scripts/bootstrap.sh" report --tier=dev >/dev/null 2>&1; then
            if [ "${ELFIENEST_SKIP_AUTO_REPAIR:-0}" = "1" ]; then
                echo "  ❌ Dependency check failed; run ./elfienest.sh version to repair the development environment." >&2
                exit 1
            fi
            echo "  🦊 Detected missing dependencies, installing..." >&2
            if ! "$SCRIPT_DIR/scripts/bootstrap.sh" ensure --tier=dev; then
                echo "  ❌ Dependency installation failed, please fix as instructed" >&2
                exit 1
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
    echo "    stop           Stop current service"
    echo "    restart        Force restart current service"
    echo "    status         Show service and port status"
    echo "    web            Ensure service is running and open Web console"
    echo "    desktop        Launch packaged ElfieNest Desktop"
    echo "    mobile         Show mobile access URL and QR code"
    echo "    config         AI Runtime configuration (interactive menu)"
    echo "    owner          Owner account menu"
    echo "    doctor         Run local diagnostics and auto-repair"
    echo "    uninstall      Uninstall and data cleanup"
    echo "    setup          First-time setup wizard"
    echo "    version        Show version info"
    echo "    db*            Database tools"
    echo "    help           Show this help"
    echo "    exit           Exit interactive mode"
    echo ""
    echo "  ┌─────────────────────────────────────────────────────────┐"
    echo "  │  Commands with * support additional arguments          │"
    echo "  └─────────────────────────────────────────────────────────┘"
    echo ""
    echo "    serve --fallback       Use built-in engine (no Ollama)"
    echo "    serve --force          Force takeover conflicting ports"
    echo "    serve --port <PORT>    Specify HTTP port"
    echo "    serve --ws-port <PORT> Specify WebSocket port"
    echo "    start --port <PORT>    Specify HTTP port for background start"
    echo "    start --fallback       Use built-in engine for background start"
    echo ""
    echo "  ┌─────────────────────────────────────────────────────────┐"
    echo "  │  Examples                                               │"
    echo "  └─────────────────────────────────────────────────────────┘"
    echo ""
    echo "    elfienest> serve --fallback    # Dev mode with built-in engine"
    echo "    elfienest> exit                # Exit"
    echo ""
}

interactive_mode() {
    # Enable command history
    HISTFILE="${HOME}/.elfienest/.cli_history"
    mkdir -p "$(dirname "$HISTFILE")"
    touch "$HISTFILE" 2>/dev/null || true

    show_logo
    show_help
    while true; do
        echo -n "elfienest> "
        read -e -r -a argv
        cmd="${argv[0]}"
        args=("${argv[@]:1}")
        case "$cmd" in
            "" ) continue ;;
            exit|quit|q) echo ""; echo "  Goodbye! 🦊"; echo ""; exit 0 ;;
            help|h|?) show_help ;;
            serve) "$PYTHON_BIN" scripts/elfienest.py serve "${args[@]}" ;;
            config|owner|doctor|status|web|desktop|mobile|stop|restart|start|version|v|setup|uninstall|db)
                "$PYTHON_BIN" scripts/elfienest.py "$cmd" "${args[@]}" ;;
            *)
                echo ""
                echo "  ❌ Unknown command: $cmd"
                echo "  💡 Type 'help' to see available commands"
                echo ""
                ;;
        esac
    done
}

if [ $# -eq 0 ]; then
    interactive_mode
else
    command="$1"
    case "$command" in
    serve)
        shift
        "$PYTHON_BIN" scripts/elfienest.py serve "$@"
        ;;
    --help|-h)
        show_logo
        show_help
        exit 0
        ;;
    *)
        "$PYTHON_BIN" scripts/elfienest.py "$@"
        ;;
    esac
fi
