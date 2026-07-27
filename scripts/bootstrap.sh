#!/bin/bash
# ElfieNest 统一依赖编排器
# 用法: bootstrap <check|ensure|report> [--tier=dev|build]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 默认参数
TIER="dev"
ACTION="check"

# 颜色输出
RED=$'\e[1;31m'
GREEN=$'\e[1;32m'
YELLOW=$'\e[1;33m'
CYAN=$'\e[1;36m'
RESET=$'\e[0m'

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        check|ensure|report)
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
            echo "${RED}❌ 未知参数: $1${RESET}" >&2
            exit 1
            ;;
    esac
done

# 验证 tier
if [[ "$TIER" != "dev" && "$TIER" != "build" ]]; then
    echo "${RED}❌ Tier 必须是 dev 或 build，当前: $TIER${RESET}" >&2
    exit 1
fi

# 读取固定 Python 版本
PYTHON_VERSION_FILE="$PROJECT_ROOT/.python-version"
if [[ ! -f "$PYTHON_VERSION_FILE" ]]; then
    echo "${RED}❌ 缺少 Python 版本文件: $PYTHON_VERSION_FILE${RESET}" >&2
    exit 1
fi

PINNED_PYTHON_VERSION="$(tr -d '[:space:]' < "$PYTHON_VERSION_FILE")"
if [[ ! "$PINNED_PYTHON_VERSION" =~ ^3\.9\.[0-9]+$ ]]; then
    echo "${RED}❌ .python-version 必须固定到 Python 3.9 的完整补丁版本。${RESET}" >&2
    exit 1
fi

# ============================================================================
# 检测函数（幂等）
# ============================================================================

check_python() {
    local venv_python="$PROJECT_ROOT/.venv/bin/python3"

    if [[ ! -x "$venv_python" ]]; then
        return 1
    fi

    # 检查版本
    if ! "$venv_python" -c "import platform, sys; ok = sys.implementation.name == 'cpython' and platform.python_version() == sys.argv[1]; raise SystemExit(0 if ok else 1)" "$PINNED_PYTHON_VERSION" 2>/dev/null; then
        return 1
    fi

    # 检查运行依赖
    local runtime_check='import fastapi, httpx, multipart, pydantic, rich, uvicorn, websockets, yaml'
    if ! "$venv_python" -c "$runtime_check" 2>/dev/null; then
        return 1
    fi

    return 0
}

ensure_python() {
    if check_python && [[ "${ELFIENEST_FORCE_LOCKED_SYNC:-0}" != "1" ]]; then
        echo "${GREEN}  ✅ Python $PINNED_PYTHON_VERSION 已就绪${RESET}"
        return 0
    fi

    echo "${CYAN}  🔧 正在准备 Python 环境...${RESET}"

    # 检查 uv
    local uv_bin
    uv_bin="$(command -v uv 2>/dev/null || true)"
    if [[ -z "$uv_bin" ]]; then
        echo "${RED}  ❌ 缺少 uv 包管理器${RESET}" >&2
        echo "     macOS: brew install uv" >&2
        echo "     其他: https://docs.astral.sh/uv/getting-started/installation/" >&2
        return 1
    fi

    # 安装 Python
    if ! "$uv_bin" python install "$PINNED_PYTHON_VERSION" >&2; then
        echo "${RED}  ❌ Python $PINNED_PYTHON_VERSION 安装失败${RESET}" >&2
        return 1
    fi

    # 同步依赖
    local sync_args="--locked"
    if [[ "$TIER" == "build" ]]; then
        sync_args="$sync_args --no-dev --extra release"
    fi

    if ! UV_PROJECT_ENVIRONMENT="$PROJECT_ROOT/.venv" "$uv_bin" sync $sync_args >&2; then
        echo "${RED}  ❌ 依赖同步失败${RESET}" >&2
        return 1
    fi

    echo "${GREEN}  ✅ Python 环境已就绪${RESET}"
}

check_node() {
    local node_version
    node_version="$(node --version 2>/dev/null || true)"

    if [[ -z "$node_version" ]]; then
        return 1
    fi

    # 检查版本 >= 20
    local major_version
    major_version="$(echo "$node_version" | sed 's/^v//' | cut -d. -f1)"

    if [[ "$major_version" -lt 20 ]]; then
        echo "${YELLOW}  ⚠️  Node.js 版本过低: $node_version (需要 >= 20)${RESET}" >&2
        return 1
    fi

    return 0
}

ensure_node() {
    if check_node; then
        echo "${GREEN}  ✅ Node.js 已就绪${RESET}"
        return 0
    fi

    echo "${RED}  ❌ 缺少 Node.js 20+${RESET}" >&2
    echo "     macOS: brew install node" >&2
    echo "     或使用 nvm: nvm install 20" >&2
    echo "     其他: https://nodejs.org/" >&2
    return 1
}

check_frontend() {
    [[ -f "$PROJECT_ROOT/build/web/manifest.json" ]]
}

ensure_frontend() {
    if check_frontend; then
        echo "${GREEN}  ✅ 前端构建产物已就绪${RESET}"
        return 0
    fi

    echo "${CYAN}  🔧 正在构建前端...${RESET}"

    # 检查 Node 和 pnpm
    ensure_node || return 1
    ensure_pnpm || return 1

    local frontend_dir="$PROJECT_ROOT/app/interfaces/web/frontend"

    if [[ ! -d "$frontend_dir" ]]; then
        echo "${RED}  ❌ 前端目录不存在: $frontend_dir${RESET}" >&2
        return 1
    fi

    cd "$frontend_dir"

    # 安装依赖
    if ! pnpm install --frozen-lockfile >&2; then
        echo "${RED}  ❌ 前端依赖安装失败${RESET}" >&2
        return 1
    fi

    # 构建
    if ! pnpm build >&2; then
        echo "${RED}  ❌ 前端构建失败${RESET}" >&2
        return 1
    fi

    cd "$PROJECT_ROOT"
    echo "${GREEN}  ✅ 前端构建完成${RESET}"
}

check_elfie_home() {
    local elfie_home="${ELFIE_HOME:-$HOME/.elfienest}"
    [[ -d "$elfie_home" ]]
}

ensure_elfie_home() {
    if check_elfie_home; then
        echo "${GREEN}  ✅ ELFIE_HOME 已就绪${RESET}"
        return 0
    fi

    echo "${CYAN}  🔧 正在创建数据目录...${RESET}"

    if ! "$PROJECT_ROOT/.venv/bin/python" -c "from ai_runtime.storage.data_home import ensure_elfie_home; ensure_elfie_home()" >&2; then
        echo "${RED}  ❌ ELFIE_HOME 创建失败${RESET}" >&2
        return 1
    fi

    echo "${GREEN}  ✅ ELFIE_HOME 已创建${RESET}"
}

check_electron() {
    local desktop_dir="$PROJECT_ROOT/app/interfaces/desktop"
    [[ -d "$desktop_dir/node_modules" ]]
}

ensure_electron() {
    if check_electron; then
        echo "${GREEN}  ✅ Electron 依赖已就绪${RESET}"
        return 0
    fi

    echo "${CYAN}  🔧 正在准备 Electron 依赖...${RESET}"

    ensure_node || return 1
    ensure_pnpm || return 1

    local desktop_dir="$PROJECT_ROOT/app/interfaces/desktop"

    if [[ ! -f "$desktop_dir/package.json" ]]; then
        echo "${YELLOW}  ⚠️  app/interfaces/desktop/package.json 不存在，跳过 Electron${RESET}"
        return 0
    fi

    cd "$desktop_dir"

    if ! pnpm install --frozen-lockfile >&2; then
        echo "${RED}  ❌ Electron 依赖安装失败${RESET}" >&2
        return 1
    fi

    cd "$PROJECT_ROOT"
    echo "${GREEN}  ✅ Electron 依赖已就绪${RESET}"
}

RUNTIME_DEPENDENCIES_HELPER="$SCRIPT_DIR/bootstrap_runtime_dependencies.sh"
if [[ ! -f "$RUNTIME_DEPENDENCIES_HELPER" ]]; then
    echo "${RED}❌ 缺少运行时依赖模块: $RUNTIME_DEPENDENCIES_HELPER${RESET}" >&2
    exit 1
fi
# shellcheck source=scripts/bootstrap_runtime_dependencies.sh
source "$RUNTIME_DEPENDENCIES_HELPER"

REPORT_HELPER="$SCRIPT_DIR/bootstrap_report.sh"
if [[ ! -f "$REPORT_HELPER" ]]; then
    echo "${RED}❌ 缺少依赖报告模块: $REPORT_HELPER${RESET}" >&2
    exit 1
fi
# shellcheck source=scripts/bootstrap_report.sh
source "$REPORT_HELPER"

# ============================================================================
# 主流程
# ============================================================================

main() {
    if [[ "$ACTION" == "report" ]]; then
        emit_bootstrap_report
        return $?
    fi

    echo ""
    echo "${CYAN}🦊 ElfieNest 依赖检查${RESET}"
    echo "   模式: ${TIER} | 动作: ${ACTION}"
    echo ""

    local exit_code=0
    local has_warning=false

    # Python（所有 tier）
    echo "📦 Python 运行时"
    if [[ "$ACTION" == "ensure" ]]; then
        ensure_python || exit_code=1
    else
        if check_python; then
            echo "${GREEN}  ✅ Python $PINNED_PYTHON_VERSION 已就绪${RESET}"
        else
            echo "${RED}  ❌ Python 缺失或版本不匹配${RESET}"
            exit_code=1
        fi
    fi
    echo ""

    # Node.js（dev tier）
    if [[ "$TIER" == "dev" ]]; then
        echo "📦 Node.js 运行时"
        if [[ "$ACTION" == "ensure" ]]; then
            ensure_node || exit_code=1
        else
            if check_node; then
                echo "${GREEN}  ✅ Node.js 已就绪${RESET}"
            else
                echo "${RED}  ❌ Node.js 缺失${RESET}"
                exit_code=1
            fi
        fi
        echo ""
    fi

    # 前端（所有 tier）
    echo "📦 前端构建产物"
    if [[ "$ACTION" == "ensure" ]]; then
        ensure_frontend || exit_code=1
    else
        if check_frontend; then
            echo "${GREEN}  ✅ 前端构建产物已就绪${RESET}"
        else
            echo "${RED}  ❌ 前端构建产物缺失${RESET}"
            exit_code=1
        fi
    fi
    echo ""

    # Godot source toolchain + Web runtime（所有 bootstrap tier 的硬门）
    echo "📦 Godot 源码构建工具链"
    if [[ "$ACTION" == "ensure" ]]; then
        ensure_godot_toolchain || exit_code=1
    else
        if check_godot_toolchain; then
            echo "${GREEN}  ✅ Godot $GODOT_TOOLCHAIN_VERSION 编辑器已就绪${RESET}"
        else
            echo "${RED}  ❌ Godot $GODOT_TOOLCHAIN_VERSION 编辑器缺失或版本不匹配${RESET}" >&2
            exit_code=1
        fi
    fi
    echo ""

    echo "📦 Godot Web Runtime"
    if [[ "$ACTION" == "ensure" ]]; then
        ensure_godot_web || exit_code=1
    else
        if check_godot_web; then
            echo "${GREEN}  ✅ Godot Web Runtime 已就绪${RESET}"
        else
            echo "${RED}  ❌ Godot Web Runtime 缺失；完整产品无法启动${RESET}"
            exit_code=1
        fi
    fi
    echo ""

    # Ollama（可选能力；首次 Setup 才能经用户确认后调用官方安装）
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
            echo "${GREEN}  ✅ 公共 Ollama 已就绪（可选能力）${RESET}"
        elif [[ "$ollama_capability" == "external" ]]; then
            echo "${GREEN}  ✅ Ollama 已就绪（外部运行时健康）${RESET}"
        else
            echo "${YELLOW}  ⚠️  Ollama 可选且尚未安装：建议在 Setup 中配置离线保障${RESET}"
            has_warning=true
        fi
    fi
    echo ""

    # Electron（dev tier only）
    if [[ "$TIER" == "dev" ]]; then
        echo "📦 Electron 依赖"
        if [[ "$ACTION" == "ensure" ]]; then
            ensure_electron || exit_code=1
        else
            if check_electron; then
                echo "${GREEN}  ✅ Electron 依赖已就绪${RESET}"
            else
                echo "${YELLOW}  ⚠️  Electron 依赖缺失（改 desktop 才需要）${RESET}"
            fi
        fi
        echo ""
    fi

    # 总结
    if [[ $exit_code -eq 0 ]]; then
        if [[ "$has_warning" == "true" ]]; then
            echo "${YELLOW}⚠️  部分依赖缺失（警告），但不影响核心功能${RESET}"
        else
            echo "${GREEN}✅ 所有必需依赖已就绪${RESET}"
        fi
    else
        echo "${RED}❌ 部分依赖缺失或失败${RESET}"
    fi

    echo ""
    return $exit_code
}

main
