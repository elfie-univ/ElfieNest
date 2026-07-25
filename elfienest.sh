#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PYTHON_VERSION_FILE="$SCRIPT_DIR/.python-version"
RUNTIME_DEPENDENCY_CHECK='import fastapi, httpx, multipart, pydantic, rich, uvicorn, websockets, yaml'

if [ ! -f "$PYTHON_VERSION_FILE" ]; then
    echo "  ❌ 缺少 Python 版本文件: $PYTHON_VERSION_FILE" >&2
    exit 1
fi

PINNED_PYTHON_VERSION="$(tr -d '[:space:]' < "$PYTHON_VERSION_FILE")"
if [[ ! "$PINNED_PYTHON_VERSION" =~ ^3\.9\.[0-9]+$ ]]; then
    echo "  ❌ .python-version 必须固定到 Python 3.9 的完整补丁版本。" >&2
    exit 1
fi

python_has_runtime_dependencies() {
    python_is_pinned_version "$1" || return 1
    "$1" -c "$RUNTIME_DEPENDENCY_CHECK" >/dev/null 2>&1
}

python_is_pinned_version() {
    "$1" -c 'import platform, sys; ok = sys.implementation.name == "cpython" and platform.python_version() == sys.argv[1]; raise SystemExit(0 if ok else 1)' "$PINNED_PYTHON_VERSION" >/dev/null 2>&1
}

repair_project_venv() {
    if [ "${ELFIENEST_SKIP_AUTO_REPAIR:-${ELFIE_SKIP_AUTO_REPAIR:-}}" = "1" ]; then
        return 1
    fi
    if [ ! -x "$SCRIPT_DIR/install.sh" ]; then
        return 1
    fi

    echo "  🔧 检测到 .venv 缺失、版本不匹配或依赖不完整，正在自动修复..." >&2
    if ! ELFIENEST_SKIP_AUTO_REPAIR=1 "$SCRIPT_DIR/install.sh" --env-only >&2; then
        echo "  ❌ 自动修复失败，请重新运行: $SCRIPT_DIR/install.sh" >&2
        return 1
    fi
    echo "" >&2
}

select_python() {
    local venv_python="$SCRIPT_DIR/.venv/bin/python3"

    if [ -x "$venv_python" ] && python_has_runtime_dependencies "$venv_python"; then
        echo "$venv_python"
        return
    fi

    repair_project_venv
    if python_has_runtime_dependencies "$venv_python"; then
        echo "$venv_python"
        return
    fi

    if [ ! -x "$venv_python" ]; then
        echo "  ❌ 项目运行环境不可用：缺少 .venv 中的 CPython $PINNED_PYTHON_VERSION。" >&2
    elif ! python_is_pinned_version "$venv_python"; then
        echo "  ❌ 项目运行环境不可用：.venv 解释器版本错误；必须使用 CPython $PINNED_PYTHON_VERSION。" >&2
    else
        echo "  ❌ 项目运行环境不可用：解释器版本正确，但运行依赖缺失或不完整。" >&2
    fi
    echo "  💡 请按锁文件修复环境: $SCRIPT_DIR/install.sh --env-only" >&2
    return 1
}

if ! PYTHON_BIN="$(select_python)"; then
    exit 1
fi

show_logo() {
    clear
    CYAN=$'\e[1;36m'
    YELLOW=$'\e[1;33m'
    RESET=$'\e[0m'
    echo ""
    echo "${CYAN}███████╗██╗     ███████╗██╗███████╗     ${YELLOW}███╗   ██╗███████╗███████╗████████╗${RESET}"
    echo "${CYAN}██╔════╝██║     ██╔════╝██║██╔════╝     ${YELLOW}████╗  ██║██╔════╝██╔════╝╚══██╔══╝${RESET}"
    echo "${CYAN}█████╗  ██║     █████╗  ██║█████╗       ${YELLOW}██╔██╗ ██║█████╗  ███████╗   ██║   ${RESET}"
    echo "${CYAN}██╔══╝  ██║     ██╔══╝  ██║██╔══╝       ${YELLOW}██║╚██╗██║██╔══╝  ╚════██║   ██║   ${RESET}"
    echo "${CYAN}███████╗███████╗██║     ██║███████╗     ${YELLOW}██║ ╚████║███████╗███████║   ██║   ${RESET}"
    echo "${CYAN}╚══════╝╚══════╝╚═╝     ╚═╝╚══════╝     ${YELLOW}╚═╝  ╚═══╝╚══════╝╚══════╝   ╚═╝   ${RESET}"
    echo ""
    echo "            🦊 仿生生命体系统 - Embodied AI Creature Simulation"
    echo ""
}

show_help() {
    echo "  ┌─────────────────────────────────────────────────────────┐"
    echo "  │  命令列表                                               │"
    echo "  └─────────────────────────────────────────────────────────┘"
    echo ""
    echo "    serve*         开发/诊断模式前台运行服务并实时显示日志"
    echo "    start*         后台启动服务（已运行时不重复启动）"
    echo "    stop           停止当前服务"
    echo "    restart        强制重启当前服务"
    echo "    status         查看服务与端口状态"
    echo "    web            确保服务可用并打开 Web 管理台"
    echo "    desktop        显式启动打包版 ElfieNest Desktop"
    echo "    config         配置中心（方向键菜单）"
    echo "    owner          Owner 账户菜单"
    echo "    doctor         本地诊断并自动修复"
    echo "    build-godot-web 构建浏览器 3D Runtime"
    echo "    db*            数据库维护工具"
    echo "    version        显示版本信息"
    echo "    setup          首次设置向导"
    echo "    developer      Developer Tool（仅开发者）"
    echo ""
    echo "  ┌─────────────────────────────────────────────────────────┐"
    echo "  │  带 * 命令支持参数                                      │"
    echo "  └─────────────────────────────────────────────────────────┘"
    echo ""
    echo "    serve --fallback       使用内置引擎（不连 Ollama）"
    echo "    serve --force          强制接管冲突端口"
    echo "    serve --port <端口>    指定 HTTP 端口"
    echo "    serve --ws-port <端口> 指定 WebSocket 端口"
    echo "    start --port <端口>    后台启动时指定 HTTP 端口"
    echo "    start --fallback       后台启动时使用内置引擎"
    echo ""
    echo "  ┌─────────────────────────────────────────────────────────┐"
    echo "  │  使用示例                                               │"
    echo "  └─────────────────────────────────────────────────────────┘"
    echo ""
    echo "    elfienest> serve --fallback    # 开发诊断前台服务（内置引擎）"
    echo "    elfienest> start               # 后台启动"
    echo "    elfienest> config              # 进入配置中心"
    echo "    elfienest> owner               # Owner 账户菜单"
    echo "    elfienest> doctor              # 运行诊断"
    echo "    elfienest> web                 # 打开 Web 管理台"
    echo "    elfienest> help                # 显示帮助"
    echo "    elfienest> exit                # 退出"
    echo ""
}

interactive_mode() {
    show_logo
    show_help
    while true; do
        echo -n "elfienest> "
        read -r -a argv
        cmd="${argv[0]}"
        args=("${argv[@]:1}")
        case "$cmd" in
            "" ) continue ;;
            exit|quit|q) echo ""; echo "  再见！🦊"; echo ""; exit 0 ;;
            help|h|?) show_help ;;
            serve) "$PYTHON_BIN" scripts/serve.py "${args[@]}" ;;
            build-godot-web) "$SCRIPT_DIR/developer.sh" build-godot-web "${args[@]}" ;;
            developer|dev) "$SCRIPT_DIR/developer.sh" "${args[@]}" ;;
            config|owner|doctor|status|web|desktop|stop|restart|start|version|v|setup)
                "$PYTHON_BIN" scripts/elfienest.py "$cmd" "${args[@]}" ;;
            db) "$PYTHON_BIN" scripts/elfienest.py db "${args[@]}" ;;
            *)
                echo ""
                echo "  ❌ 未知命令: $cmd"
                echo "  💡 输入 'help' 查看帮助"
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
        "$PYTHON_BIN" scripts/serve.py "$@"
        ;;
    build-godot-web)
        shift
        "$SCRIPT_DIR/developer.sh" build-godot-web "$@"
        ;;
    developer|dev)
        shift
        "$SCRIPT_DIR/developer.sh" "$@"
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
