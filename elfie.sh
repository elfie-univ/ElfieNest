#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
WEB_DEPENDENCY_CHECK='import fastapi, uvicorn, multipart'

python_has_web_dependencies() {
    "$1" -c "$WEB_DEPENDENCY_CHECK" >/dev/null 2>&1
}

repair_project_venv() {
    if [ "${ELFIE_SKIP_AUTO_REPAIR:-}" = "1" ]; then
        return 1
    fi
    if [ ! -x "$SCRIPT_DIR/install.sh" ]; then
        return 1
    fi

    echo "  🔧 检测到 .venv 缺少依赖，正在自动修复..." >&2
    if ! ELFIE_SKIP_AUTO_REPAIR=1 "$SCRIPT_DIR/install.sh" >&2; then
        echo "  ❌ 自动修复失败，请重新运行: $SCRIPT_DIR/install.sh" >&2
        return 1
    fi
    echo "" >&2
}

select_python() {
    local venv_python="$SCRIPT_DIR/.venv/bin/python3"

    if [ -x "$venv_python" ] && python_has_web_dependencies "$venv_python"; then
        echo "$venv_python"
        return
    fi

    repair_project_venv
    if python_has_web_dependencies "$venv_python"; then
        echo "$venv_python"
        return
    fi

    if python_has_web_dependencies "python3"; then
        echo "  ⚠️  .venv 自动修复失败，临时使用系统 python3。" >&2
        echo "  💡 可重新运行: $SCRIPT_DIR/install.sh" >&2
        echo "" >&2
        echo "python3"
        return
    fi

    if [ -x "$venv_python" ]; then
        echo "$venv_python"
    else
        echo "python3"
    fi
}

PYTHON_BIN="$(select_python)"

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
    echo "    serve          启动服务"
    echo "    config         配置系统（交互式 TUI）"
    echo "    status         查看服务状态"
    echo "    models         列出可用模型"
    echo "    providers      管理 AI 服务商"
    echo "    stats          显示使用统计"
    echo "    session        管理会话"
    echo "    logs           查看日志"
    echo "    db             数据库工具"
    echo "    web            启动服务并打开浏览器"
    echo "    version        显示版本信息"
    echo "    setup          首次设置向导"
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
    echo "    elfie> serve --fallback        # 启动服务（内置引擎）"
    echo "    elfie> serve --force           # 强制重启"
    echo "    elfie> config                  # 进入配置界面"
    echo "    elfie> status                  # 查看状态"
    echo "    elfie> help                    # 显示帮助"
    echo "    elfie> exit                    # 退出"
    echo ""
}

interactive_mode() {
    show_logo
    show_help
    while true; do
        echo -n "elfie> "
        read -r cmd args
        case "$cmd" in
            ""|exit|quit|q) echo ""; echo "  再见！🦊"; echo ""; exit 0 ;;
            help|h|?) show_help ;;
            serve) "$PYTHON_BIN" scripts/serve.py $args ;;
            config) "$PYTHON_BIN" scripts/elfie.py config ;;
            status) "$PYTHON_BIN" scripts/elfie.py status ;;
            models) "$PYTHON_BIN" scripts/elfie.py models ;;
            stats) "$PYTHON_BIN" scripts/elfie.py stats ;;
            logs) "$PYTHON_BIN" scripts/elfie.py logs ;;
            db) "$PYTHON_BIN" scripts/elfie.py db $args ;;
            providers) "$PYTHON_BIN" scripts/elfie.py providers ;;
            session) "$PYTHON_BIN" scripts/elfie.py session ;;
            version|v) "$PYTHON_BIN" scripts/elfie.py version ;;
            restart) "$PYTHON_BIN" scripts/elfie.py restart ;;
            stop) "$PYTHON_BIN" scripts/elfie.py stop ;;
            setup) "$PYTHON_BIN" scripts/elfie.py setup ;;
            web) "$PYTHON_BIN" scripts/elfie.py web ;;
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
    if [ "$command" = "serve" ]; then
        shift
        has_serve_arg=true
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
        "$PYTHON_BIN" scripts/elfie.py "$@"
    fi
fi
