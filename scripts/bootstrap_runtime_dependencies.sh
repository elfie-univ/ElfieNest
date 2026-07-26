#!/bin/bash
# Runtime dependency checks and preparation for the bootstrap orchestrator.

PNPM_VERSION="10.12.1"

check_pnpm() {
    local pnpm_version
    pnpm_version="$(pnpm --version 2>/dev/null || true)"
    [[ "$pnpm_version" == "$PNPM_VERSION" ]]
}

ensure_pnpm() {
    if check_pnpm; then
        echo "${GREEN}  ✅ pnpm $PNPM_VERSION 已就绪${RESET}"
        return 0
    fi

    echo "${CYAN}  🔧 正在安装 pnpm $PNPM_VERSION...${RESET}"
    if ! npm install -g "pnpm@${PNPM_VERSION}" >&2; then
        echo "${RED}  ❌ pnpm $PNPM_VERSION 安装失败${RESET}" >&2
        return 1
    fi
    if ! check_pnpm; then
        echo "${RED}  ❌ pnpm 版本不匹配（需要 $PNPM_VERSION）${RESET}" >&2
        return 1
    fi
    echo "${GREEN}  ✅ pnpm $PNPM_VERSION 已安装${RESET}"
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

    echo "${RED}  ❌ Godot Web Runtime 缺失；完整产品无法启动${RESET}" >&2
    echo "     请安装 Godot 4.7 编辑器 + Web Export Templates" >&2
    echo "     然后运行: ./elfienest.sh build-godot-web" >&2
    return 1
}

ollama_capability_state() {
    local managed_ollama="$PROJECT_ROOT/ai_runtime/setup/bin/ollama"
    local external_ollama

    if [[ -x "$managed_ollama" ]]; then
        printf '%s\n' "managed"
        return 0
    fi

    external_ollama="$(command -v ollama 2>/dev/null || true)"
    if [[ -n "$external_ollama" ]] && "$external_ollama" list >/dev/null 2>&1; then
        printf '%s\n' "external"
        return 0
    fi

    printf '%s\n' "fallback"
}

check_ollama() {
    [[ "$(ollama_capability_state)" != "fallback" ]]
}

ensure_ollama() {
    local capability
    capability="$(ollama_capability_state)"
    case "$capability" in
        managed)
            echo "${GREEN}  ✅ Ollama 已就绪（托管运行时）${RESET}"
            return 0
            ;;
        external)
            echo "${GREEN}  ✅ Ollama 已就绪（外部运行时健康）${RESET}"
            return 0
            ;;
    esac

    echo "${CYAN}  🔧 正在检查 Ollama...${RESET}"
    case "$(uname)" in
        Darwin)
            echo "${CYAN}  📥 正在为 macOS 下载 Ollama...${RESET}"
            if "$PROJECT_ROOT/.venv/bin/python" -c "from ai_runtime.setup.runtime_setup import download_ollama_macos; import sys; sys.exit(0 if download_ollama_macos() else 1)" >&2 && check_ollama; then
                echo "${GREEN}  ✅ Ollama 已下载并可用${RESET}"
                return 0
            fi
            ;;
        Linux)
            echo "${YELLOW}  ⚠️  Linux 未自动安装 Ollama${RESET}" >&2
            echo "     建议安装: https://ollama.com/download/linux" >&2
            ;;
        MINGW*|MSYS*|CYGWIN*)
            echo "${YELLOW}  ⚠️  Windows 未自动安装 Ollama${RESET}" >&2
            echo "     建议安装: https://ollama.com/download/windows" >&2
            ;;
        *)
            echo "${YELLOW}  ⚠️  未知平台，无法自动安装 Ollama${RESET}" >&2
            ;;
    esac

    echo "${YELLOW}     继续使用 fallback：本地模型能力不可用；安装后重新运行 ./elfienest.sh。${RESET}" >&2
    return 2
}
