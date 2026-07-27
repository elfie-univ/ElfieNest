#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ============================================================================
# 运行状态探测：源码开发路径与安装后运行路径必须严格分开。
# ============================================================================

detect_runtime_mode() {
    local script_dir="$1"

    # 安装目录标志：存在 resources/python-core/ 或 manifest.json
    if [ -d "$script_dir/resources/python-core" ] || [ -f "$script_dir/manifest.json" ]; then
        echo "installed_runtime"
        return
    fi

    # 源码树标志：存在 pyproject.toml 或 scripts/serve.py
    if [ -f "$script_dir/pyproject.toml" ] || [ -f "$script_dir/scripts/serve.py" ]; then
        echo "source_development"
        return
    fi

    echo "unknown"
}

MODE="$(detect_runtime_mode "$SCRIPT_DIR")"

case "$MODE" in
    installed_runtime)
        # 安装后运行：直接调 Python Core（依赖已打包）
        exec "$SCRIPT_DIR/resources/python-core/ElfieNestCore" "$@"
        ;;
    source_development)
        # 源码开发：先检查；首次缺依赖时再补齐，成功前不进入菜单。
        if ! "$SCRIPT_DIR/scripts/bootstrap.sh" report --tier=dev >/dev/null; then
            echo "  ℹ️ 首次准备，正在安装开发依赖..."
            if ! "$SCRIPT_DIR/scripts/bootstrap.sh" ensure --tier=dev; then
                echo "  ❌ 依赖检查失败，请按提示修复" >&2
                exit 1
            fi
        fi
        ;;
    unknown)
        echo "❌ 无法识别运行模式：既不是源码树也不是安装目录" >&2
        exit 1
        ;;
esac

# ============================================================================
# 开发模式：命令分发与交互菜单（从原 elfienest.sh 迁移）
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
