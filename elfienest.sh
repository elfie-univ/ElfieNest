#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PYTHON_VERSION_FILE="$SCRIPT_DIR/.python-version"
RUNTIME_DEPENDENCY_CHECK='import edge_tts, fastapi, httpx, multipart, pydantic, rich, uvicorn, websockets, yaml'

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

    echo "  ❌ 项目运行环境不可用；必须使用锁定的 Python $PINNED_PYTHON_VERSION。" >&2
    echo "  💡 请安装 uv 后重新运行: $SCRIPT_DIR/install.sh" >&2
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
    echo "    start          启动 ElfieNest Web 服务"
    echo "    serve          start 的兼容别名"
    echo "    build-godot-web 构建浏览器 3D Runtime"
    echo "    config         配置系统（交互式 TUI）"
    echo "    status         查看服务状态"
    echo "    models         列出可用模型"
    echo "    providers      管理 AI 服务商"
    echo "    stats          显示使用统计"
    echo "    session        管理会话"
    echo "    logs           查看日志"
    echo "    db             数据库工具"
    echo "    web            启动服务并打开浏览器"
    echo "    restart        重启 ElfieNest Web 服务"
    echo "    stop           停止 ElfieNest Web 服务"
    echo "    version        显示版本信息"
    echo "    setup          首次设置向导"
    echo "    admin          管理员账号管理（显示账号、重置密码）"
    echo ""
    echo "  ┌─────────────────────────────────────────────────────────┐"
    echo "  │  服务参数                                               │"
    echo "  └─────────────────────────────────────────────────────────┘"
    echo ""
    echo "    --fallback     使用内置引擎（不连 Ollama）"
    echo "    --force        强制重启（杀死占用端口的进程）"
    echo "    --port         指定 HTTP 端口"
    echo "    --ws-port      指定 WebSocket 端口"
    echo ""
    echo "  ┌─────────────────────────────────────────────────────────┐"
    echo "  │  使用示例                                               │"
    echo "  └─────────────────────────────────────────────────────────┘"
    echo ""
    echo "    elfienest> serve --fallback    # 启动服务（内置引擎）"
    echo "    elfienest> serve --force       # 强制重启"
    echo "    elfienest> config              # 进入配置界面"
    echo "    elfienest> status              # 查看状态"
    echo "    elfienest> admin               # 管理员账号管理"
    echo "    elfienest> help                # 显示帮助"
    echo "    elfienest> exit                # 退出"
    echo ""
}

interactive_mode() {
    show_logo
    show_help
    while true; do
        echo -n "elfienest> "
        read -r cmd args
        case "$cmd" in
            ""|exit|quit|q) echo ""; echo "  再见！🦊"; echo ""; exit 0 ;;
            help|h|?) show_help ;;
            start|serve) "$PYTHON_BIN" scripts/serve.py $args ;;
            build-godot-web) "$PYTHON_BIN" scripts/build_godot_web.py $args ;;
            config) "$PYTHON_BIN" scripts/elfienest.py config ;;
            status) "$PYTHON_BIN" scripts/elfienest.py status ;;
            models) "$PYTHON_BIN" scripts/elfienest.py models ;;
            stats) "$PYTHON_BIN" scripts/elfienest.py stats ;;
            logs) "$PYTHON_BIN" scripts/elfienest.py logs ;;
            db) "$PYTHON_BIN" scripts/elfienest.py db $args ;;
            providers) "$PYTHON_BIN" scripts/elfienest.py providers ;;
            session) "$PYTHON_BIN" scripts/elfienest.py session ;;
            version|v) "$PYTHON_BIN" scripts/elfienest.py version ;;
            restart) "$PYTHON_BIN" scripts/elfienest.py restart ;;
            stop) "$PYTHON_BIN" scripts/elfienest.py stop ;;
            setup) "$PYTHON_BIN" scripts/elfienest.py setup ;;
            admin) "$PYTHON_BIN" scripts/elfienest.py admin $args ;;
            web) "$PYTHON_BIN" scripts/elfienest.py web ;;
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
    SERVE_ARGS="--fallback --force --port --ws-port --no-seed-elfie"
    has_serve_arg=false
    command="$1"
    if [ "$command" = "start" ] || [ "$command" = "serve" ]; then
        shift
        has_serve_arg=true
    elif [ "$command" = "build-godot-web" ]; then
        shift
        "$PYTHON_BIN" scripts/build_godot_web.py "$@"
        exit $?
    else
        for arg in "$@"; do
            if [[ " $SERVE_ARGS " =~ " $arg " ]] || [[ "$arg" == --port=* ]] || [[ "$arg" == --ws-port=* ]]; then
                has_serve_arg=true
                break
            fi
        done
    fi
    if [ "$has_serve_arg" = true ]; then
        "$PYTHON_BIN" scripts/serve.py "$@"
    else
        "$PYTHON_BIN" scripts/elfienest.py "$@"
    fi
fi
