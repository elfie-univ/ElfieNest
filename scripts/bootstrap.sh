#!/bin/bash
# ElfieNest 统一依赖编排器
# 用法: bootstrap <check|ensure|report> [--tier=dev|prod]

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
if [[ "$TIER" != "dev" && "$TIER" != "prod" ]]; then
    echo "${RED}❌ Tier 必须是 dev 或 prod，当前: $TIER${RESET}" >&2
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
    if check_python; then
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
    if [[ "$TIER" == "prod" ]]; then
        sync_args="$sync_args --no-dev"
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

check_pnpm() {
    local pnpm_version
    pnpm_version="$(pnpm --version 2>/dev/null || true)"

    if [[ -z "$pnpm_version" ]]; then
        return 1
    fi

    return 0
}

ensure_pnpm() {
    if check_pnpm; then
        echo "${GREEN}  ✅ pnpm 已就绪${RESET}"
        return 0
    fi

    echo "${CYAN}  🔧 正在安装 pnpm...${RESET}"
    npm install -g pnpm@latest
    echo "${GREEN}  ✅ pnpm 已安装${RESET}"
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

check_godot_web() {
    local godot_dir="$PROJECT_ROOT/build/components/godot-web"

    [[ -f "$godot_dir/elfienest.html" ]] && \
    [[ -f "$godot_dir/elfienest.js" ]] && \
    [[ -f "$godot_dir/elfienest.wasm" ]] && \
    [[ -f "$godot_dir/elfienest.pck" ]]
}

ensure_godot_web() {
    if check_godot_web; then
        echo "${GREEN}  ✅ Godot Web Runtime 已就绪${RESET}"
        return 0
    fi

    echo "${YELLOW}  ⚠️  Godot Web Runtime 缺失${RESET}" >&2
    echo "     请安装 Godot 4.7 编辑器 + Web Export Templates" >&2
    echo "     然后运行: ./elfienest.sh build-godot-web" >&2
    return 2  # 部分成功（警告）
}

check_ollama() {
    # 检查本地 bin 目录
    if [[ -x "$PROJECT_ROOT/ai_runtime/setup/bin/ollama" ]]; then
        return 0
    fi

    # 检查系统 PATH
    if command -v ollama >/dev/null 2>&1; then
        return 0
    fi

    return 1
}

ensure_ollama() {
    if check_ollama; then
        echo "${GREEN}  ✅ Ollama 已就绪${RESET}"
        return 0
    fi

    echo "${CYAN}  🔧 正在检查 Ollama...${RESET}"

    # 跨平台支持
    case "$(uname)" in
        Darwin)
            # macOS: 使用 Python 脚本下载
            echo "${CYAN}  📥 正在为 macOS 下载 Ollama...${RESET}"
            if ! "$PROJECT_ROOT/.venv/bin/python" -c "from ai_runtime.setup.runtime_setup import download_ollama_macos; import sys; sys.exit(0 if download_ollama_macos() else 1)" >&2; then
                echo "${RED}  ❌ Ollama 下载失败${RESET}" >&2
                return 1
            fi
            echo "${GREEN}  ✅ Ollama 已下载${RESET}"
            ;;
        Linux)
            # Linux: 提示用户安装
            echo "${YELLOW}  ⚠️  请在 Linux 上安装 Ollama:${RESET}" >&2
            echo "     curl -fsSL https://ollama.com/install.sh | sh" >&2
            echo "     或访问: https://ollama.com/download/linux" >&2
            return 2
            ;;
        MINGW*|MSYS*|CYGWIN*)
            # Windows: 提示用户下载
            echo "${YELLOW}  ⚠️  请在 Windows 上下载安装 Ollama:${RESET}" >&2
            echo "     https://ollama.com/download/windows" >&2
            return 2
            ;;
        *)
            echo "${YELLOW}  ⚠️  未知平台，请手动安装 Ollama: https://ollama.com${RESET}" >&2
            return 2
            ;;
    esac

    return 0
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
    local desktop_dir="$PROJECT_ROOT/desktop"
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

    local desktop_dir="$PROJECT_ROOT/desktop"

    if [[ ! -f "$desktop_dir/package.json" ]]; then
        echo "${YELLOW}  ⚠️  desktop/package.json 不存在，跳过 Electron${RESET}"
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

# ============================================================================
# 主流程
# ============================================================================

main() {
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

    # Godot web（所有 tier，只检查不强制装）
    echo "📦 Godot Web Runtime"
    if [[ "$ACTION" == "ensure" ]]; then
        ensure_godot_web
        local godot_result=$?
        if [[ $godot_result -eq 2 ]]; then
            has_warning=true
        elif [[ $godot_result -ne 0 ]]; then
            exit_code=1
        fi
    else
        if check_godot_web; then
            echo "${GREEN}  ✅ Godot Web Runtime 已就绪${RESET}"
        else
            echo "${YELLOW}  ⚠️  Godot Web Runtime 缺失（不影响启动）${RESET}"
            has_warning=true
        fi
    fi
    echo ""

    # Ollama（prod tier 或 dev tier）
    echo "📦 Ollama"
    if [[ "$ACTION" == "ensure" ]]; then
        ensure_ollama
        local ollama_result=$?
        if [[ $ollama_result -eq 2 ]]; then
            has_warning=true
        elif [[ $ollama_result -ne 0 ]]; then
            exit_code=1
        fi
    else
        if check_ollama; then
            echo "${GREEN}  ✅ Ollama 已就绪${RESET}"
        else
            echo "${YELLOW}  ⚠️  Ollama 缺失（需要安装）${RESET}"
            has_warning=true
        fi
    fi
    echo ""

    # ELFIE_HOME（prod tier）
    if [[ "$TIER" == "prod" ]]; then
        echo "📦 数据目录"
        if [[ "$ACTION" == "ensure" ]]; then
            ensure_elfie_home || exit_code=1
        else
            if check_elfie_home; then
                echo "${GREEN}  ✅ ELFIE_HOME 已就绪${RESET}"
            else
                echo "${YELLOW}  ⚠️  ELFIE_HOME 缺失（首次运行会自动创建）${RESET}"
            fi
        fi
        echo ""
    fi

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
