#!/bin/bash
# Runtime dependency checks and preparation for the bootstrap orchestrator.

PNPM_VERSION="10.12.1"
GODOT_TOOLCHAIN_VERSION="4.7.1"
GODOT_DOWNLOAD_ENDPOINT="https://downloads.godotengine.org/"
GODOT_RESOLVED_BIN=""
GODOT_RESOLVED_USER_HOME=""

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

godot_toolchain_root() {
    printf '%s\n' "${ELFIE_DEV_HOME:-$HOME/.elfienest-dev}/toolchains/godot/$GODOT_TOOLCHAIN_VERSION"
}

godot_user_home() {
    printf '%s\n' "${ELFIE_DEV_HOME:-$HOME/.elfienest-dev}/godot-user-home"
}

godot_managed_root_is_safe() {
    local candidate="$1"
    local developer_home="${ELFIE_DEV_HOME:-$HOME/.elfienest-dev}"
    local expected="$developer_home/toolchains/godot/$GODOT_TOOLCHAIN_VERSION"

    [[ "$candidate" == "$expected" ]] && \
    [[ "$candidate" != "/" ]] && \
    [[ "$candidate" != "$developer_home" ]] && \
    [[ "$candidate" != "$developer_home/toolchains" ]]
}

godot_download_url() {
    local platform="$1"
    local slug="$2"

    printf '%s?flavor=stable&platform=%s&slug=%s&version=%s\n' \
        "$GODOT_DOWNLOAD_ENDPOINT" "$platform" "$slug" "$GODOT_TOOLCHAIN_VERSION"
}

godot_binary_has_required_version() {
    local binary="$1"
    local version

    [[ -x "$binary" ]] || return 1
    version="$("$binary" --version 2>/dev/null || true)"
    [[ "$version" == *"$GODOT_TOOLCHAIN_VERSION"* ]]
}

find_existing_godot_binary() {
    local candidate
    local command_name

    if [[ -n "${GODOT_BIN:-}" ]]; then
        if godot_binary_has_required_version "$GODOT_BIN"; then
            printf '%s\n' "$GODOT_BIN"
            return 0
        fi
        return 1
    fi
    for command_name in godot4 godot Godot; do
        candidate="$(command -v "$command_name" 2>/dev/null || true)"
        if [[ -n "$candidate" ]] && godot_binary_has_required_version "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    for candidate in \
        "/Applications/Godot.app/Contents/MacOS/Godot" \
        "$HOME/Applications/Godot.app/Contents/MacOS/Godot"; do
        if godot_binary_has_required_version "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

check_godot_toolchain() {
    local managed_root
    local managed_binary

    managed_root="$(godot_toolchain_root)"
    managed_binary="$(find "$managed_root" -type f \( -name Godot -o -name 'Godot*.x86_64' -o -name 'Godot*.exe' \) -perm -u+x 2>/dev/null | head -n 1)"
    if [[ -n "$managed_binary" ]] && godot_binary_has_required_version "$managed_binary"; then
        return 0
    fi
    [[ -n "$(find_existing_godot_binary || true)" ]]
}

install_official_godot_toolchain() {
    local root
    local user_home
    local editor_archive
    local template_archive
    local editor_staging
    local template_staging
    local editor_platform
    local editor_slug
    local editor_binary
    local managed_root

    root="$(godot_toolchain_root)"
    user_home="$(godot_user_home)"
    case "$(uname -s):$(uname -m)" in
        Darwin:arm64|Darwin:x86_64)
            editor_platform="macos.universal"
            editor_slug="macos.universal.zip"
            ;;
        Linux:x86_64|Linux:amd64)
            editor_platform="linux.x86_64"
            editor_slug="linux.x86_64.zip"
            ;;
        MINGW*:x86_64|MSYS*:x86_64|CYGWIN*:x86_64)
            editor_platform="windows.x86_64"
            editor_slug="win64.exe.zip"
            ;;
        *)
            echo "${RED}  ❌ 当前平台不支持自动准备 Godot: $(uname -s) $(uname -m)${RESET}" >&2
            return 1
            ;;
    esac
    if ! command -v curl >/dev/null 2>&1 || ! command -v unzip >/dev/null 2>&1; then
        echo "${RED}  ❌ 自动安装 Godot 需要 curl 和 unzip。${RESET}" >&2
        return 1
    fi
    editor_archive="$(mktemp "${TMPDIR:-/tmp}/elfienest-godot-editor.XXXXXX")"
    template_archive="$(mktemp "${TMPDIR:-/tmp}/elfienest-godot-templates.XXXXXX")"
    editor_staging="$(mktemp -d "${TMPDIR:-/tmp}/elfienest-godot-editor.XXXXXX")"
    template_staging="$(mktemp -d "${TMPDIR:-/tmp}/elfienest-godot-templates.XXXXXX")"

    echo "${CYAN}  📥 正在下载官方 Godot $GODOT_TOOLCHAIN_VERSION 编辑器...${RESET}"
    if ! curl --fail --location --retry 3 --output "$editor_archive" "$(godot_download_url "$editor_platform" "$editor_slug")"; then
        echo "${RED}  ❌ Godot 编辑器下载失败。${RESET}" >&2
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi
    if ! unzip -q "$editor_archive" -d "$editor_staging"; then
        echo "${RED}  ❌ Godot 编辑器解压失败。${RESET}" >&2
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi
    echo "${CYAN}  📥 正在下载官方 Godot Web Export Templates...${RESET}"
    if ! curl --fail --location --retry 3 --output "$template_archive" "$(godot_download_url "templates" "export_templates.tpz")"; then
        echo "${RED}  ❌ Godot Web Export Templates 下载失败。${RESET}" >&2
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi
    if ! unzip -q "$template_archive" -d "$template_staging"; then
        echo "${RED}  ❌ Godot Web Export Templates 解压失败。${RESET}" >&2
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi

    if ! godot_managed_root_is_safe "$root"; then
        echo "${RED}  ❌ 拒绝清理非受管 Godot 目录: $root${RESET}" >&2
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi
    managed_root="$root"
    rm -rf -- "$managed_root"
    mkdir -p -- "$root" "$user_home/export_templates/$GODOT_TOOLCHAIN_VERSION.stable"
    cp -R "$editor_staging"/* "$root/"
    cp -R "$template_staging"/* "$user_home/export_templates/$GODOT_TOOLCHAIN_VERSION.stable/"
    editor_binary="$(find "$root" -type f \( -name Godot -o -name 'Godot*.x86_64' -o -name 'Godot*.exe' \) -perm -u+x | head -n 1)"
    if [[ -z "$editor_binary" ]] || ! godot_binary_has_required_version "$editor_binary"; then
        echo "${RED}  ❌ Godot 编辑器安装后版本校验失败。${RESET}" >&2
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi
    GODOT_RESOLVED_BIN="$editor_binary"
    GODOT_RESOLVED_USER_HOME="$user_home"
    rm -f -- "$editor_archive" "$template_archive"
    rm -rf -- "$editor_staging" "$template_staging"
    echo "${GREEN}  ✅ Godot $GODOT_TOOLCHAIN_VERSION 与 Web Export Templates 已准备${RESET}"
}

ensure_godot_toolchain() {
    local existing_binary
    local choice
    local managed_root
    local managed_binary
    local managed_user_home

    managed_root="$(godot_toolchain_root)"
    managed_user_home="$(godot_user_home)"
    managed_binary="$(find "$managed_root" -type f \( -name Godot -o -name 'Godot*.x86_64' -o -name 'Godot*.exe' \) -perm -u+x 2>/dev/null | head -n 1)"
    if [[ -n "$managed_binary" ]] && godot_binary_has_required_version "$managed_binary"; then
        GODOT_RESOLVED_BIN="$managed_binary"
        GODOT_RESOLVED_USER_HOME="$managed_user_home"
        return 0
    fi
    existing_binary="$(find_existing_godot_binary || true)"
    if [[ -n "$existing_binary" ]]; then
        GODOT_RESOLVED_BIN="$existing_binary"
        return 0
    fi
    echo "${YELLOW}  ⚠️ 源码开发/编译需要 Godot $GODOT_TOOLCHAIN_VERSION 与同版本 Web Export Templates。${RESET}" >&2
    echo "     它们只用于从源码导出 Godot Web Runtime，不会进入正式 ElfieNest 安装包。" >&2
    if [[ ! -t 0 ]]; then
        echo "${RED}  ❌ 非交互环境不能确认安装 Godot；请先安装或设置 GODOT_BIN。${RESET}" >&2
        return 1
    fi
    printf '     现在从 Godot 官方源安装？[Y/n/path] ' >&2
    read -r choice
    case "${choice:-Y}" in
        Y|y|yes|YES) install_official_godot_toolchain ;;
        n|N|no|NO)
            echo "${RED}  ❌ Godot 是源码开发/编译的必需依赖，已取消。${RESET}" >&2
            return 1
            ;;
        *)
            if godot_binary_has_required_version "$choice"; then
                GODOT_RESOLVED_BIN="$choice"
                return 0
            fi
            echo "${RED}  ❌ 指定的 Godot 路径不可用或不是 $GODOT_TOOLCHAIN_VERSION。${RESET}" >&2
            return 1
            ;;
    esac
}

ensure_godot_web() {
    if check_godot_web; then
        echo "${GREEN}  ✅ Godot Web Runtime 已就绪${RESET}"
        return 0
    fi

    echo "${RED}  ❌ Godot Web Runtime 缺失；完整产品无法启动${RESET}" >&2
    if ! ensure_godot_toolchain; then
        return 1
    fi
    if [[ -n "$GODOT_RESOLVED_USER_HOME" ]]; then
        if ! GODOT_BIN="$GODOT_RESOLVED_BIN" GODOT_USER_HOME="$GODOT_RESOLVED_USER_HOME" \
            "$PROJECT_ROOT/.venv/bin/python3" "$PROJECT_ROOT/scripts/build_godot_web.py" --ensure; then
            echo "${RED}  ❌ Godot 4.7.1 或同版本 Web Export Templates 无法导出 Web Runtime。${RESET}" >&2
            return 1
        fi
    elif ! GODOT_BIN="$GODOT_RESOLVED_BIN" \
        "$PROJECT_ROOT/.venv/bin/python3" "$PROJECT_ROOT/scripts/build_godot_web.py" --ensure; then
        echo "${RED}  ❌ Godot 4.7.1 或同版本 Web Export Templates 无法导出 Web Runtime。${RESET}" >&2
        return 1
    fi
    check_godot_web
}

ollama_capability_state() {
    local external_ollama

    external_ollama="$(command -v ollama 2>/dev/null || true)"
    if [[ -n "$external_ollama" ]] && "$external_ollama" list >/dev/null 2>&1; then
        printf '%s\n' "external"
        return 0
    fi

    printf '%s\n' "optional_missing"
}

ensure_ollama() {
    local capability
    capability="$(ollama_capability_state)"
    case "$capability" in
        external)
            echo "${GREEN}  ✅ Ollama 已就绪（外部运行时健康）${RESET}"
            return 0
            ;;
    esac

    echo "${YELLOW}  ⚠️  Ollama 可选且尚未安装。${RESET}"
    echo "     它是断网或云端不可用时的本地离线保障；请在 Setup 中确认后安装。"
    return 2
}
