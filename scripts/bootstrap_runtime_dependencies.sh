#!/bin/bash
# Runtime dependency checks and preparation for the bootstrap orchestrator.

PNPM_VERSION="10.12.1"
GODOT_PROJECT_VERSION=""
GODOT_DOWNLOAD_ENDPOINT="https://downloads.godotengine.org/"
GODOT_RESOLVED_BIN=""
GODOT_RESOLVED_USER_HOME=""

project_python() {
    local candidate
    for candidate in \
        "$PROJECT_ROOT/.venv/Scripts/python.exe" \
        "$PROJECT_ROOT/.venv/Scripts/python" \
        "$PROJECT_ROOT/.venv/bin/python3" \
        "$PROJECT_ROOT/.venv/bin/python"; do
        if [[ -f "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

godot_project_version() {
    local python_bin

    python_bin="$(project_python 2>/dev/null || true)"
    if [[ -z "$python_bin" ]]; then
        echo "❌ Repository Python environment is unavailable for reading project.godot." >&2
        return 1
    fi

    PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        "$python_bin" -m infrastructure.godot.runner project-version \
        --project "$PROJECT_ROOT/godot_project"
}

load_godot_project_version() {
    if [[ -n "$GODOT_PROJECT_VERSION" ]]; then
        return 0
    fi
    GODOT_PROJECT_VERSION="$(godot_project_version)" || return 1
    if [[ ! "$GODOT_PROJECT_VERSION" =~ ^[0-9]+\.[0-9]+$ ]]; then
        echo "❌ Invalid Godot compatibility version in godot_project/project.godot." >&2
        GODOT_PROJECT_VERSION=""
        return 1
    fi
}

check_pnpm() {
    local package_dir="$1"
    local pnpm_bin
    local pnpm_version

    pnpm_bin="$(command -v pnpm 2>/dev/null || true)"
    [[ -n "$pnpm_bin" ]] || return 1

    pnpm_version="$(cd "$package_dir" && "$pnpm_bin" --version 2>/dev/null || true)"
    [[ "$pnpm_version" == "$PNPM_VERSION" ]]
}

ensure_pnpm() {
    local package_dir="$1"
    local npx_bin
    local pnpm_version

    if check_pnpm "$package_dir"; then
        echo "${GREEN}  ✅ pnpm $PNPM_VERSION ready${RESET}"
        return 0
    fi

    npx_bin="$(command -v npx 2>/dev/null || true)"
    if [[ -z "$npx_bin" ]]; then
        echo "${RED}  ❌ pnpm $PNPM_VERSION is unavailable and npx was not found${RESET}" >&2
        return 1
    fi

    echo "${CYAN}  🔧 Preparing repository-pinned pnpm $PNPM_VERSION...${RESET}"
    if ! pnpm_version="$(cd "$package_dir" && "$npx_bin" --yes "pnpm@${PNPM_VERSION}" --version)"; then
        echo "${RED}  ❌ Failed to prepare repository-pinned pnpm $PNPM_VERSION${RESET}" >&2
        return 1
    fi
    if [[ "$pnpm_version" != "$PNPM_VERSION" ]]; then
        echo "${RED}  ❌ pnpm version mismatch (need $PNPM_VERSION)${RESET}" >&2
        return 1
    fi
    echo "${GREEN}  ✅ pnpm $PNPM_VERSION ready through npx${RESET}"
}

run_pnpm() {
    local package_dir="$1"
    shift

    if check_pnpm "$package_dir"; then
        local pnpm_bin
        pnpm_bin="$(command -v pnpm)"
        (cd "$package_dir" && "$pnpm_bin" "$@")
        return
    fi

    local npx_bin
    npx_bin="$(command -v npx)"
    (cd "$package_dir" && "$npx_bin" --yes "pnpm@${PNPM_VERSION}" "$@")
}

check_godot_web() {
    local godot_dir="$PROJECT_ROOT/build/components/godot-web"

    [[ -f "$godot_dir/elfienest.html" ]] && \
    [[ -f "$godot_dir/elfienest.js" ]] && \
    [[ -f "$godot_dir/elfienest.wasm" ]] && \
    [[ -f "$godot_dir/elfienest.pck" ]]
}

godot_toolchain_root() {
    load_godot_project_version || return 1
    printf '%s\n' "${ELFIE_DEV_HOME:-$HOME/.elfienest-dev}/toolchains/godot/$GODOT_PROJECT_VERSION"
}

godot_user_home() {
    printf '%s\n' "${ELFIE_DEV_HOME:-$HOME/.elfienest-dev}/godot-user-home"
}

godot_managed_root_is_safe() {
    local candidate="$1"
    local developer_home="${ELFIE_DEV_HOME:-$HOME/.elfienest-dev}"
    local expected

    load_godot_project_version || return 1
    expected="$developer_home/toolchains/godot/$GODOT_PROJECT_VERSION"

    [[ "$candidate" == "$expected" ]] && \
    [[ "$candidate" != "/" ]] && \
    [[ "$candidate" != "$developer_home" ]] && \
    [[ "$candidate" != "$developer_home/toolchains" ]]
}

godot_download_url() {
    local platform="$1"
    local slug="$2"

    load_godot_project_version || return 1
    printf '%s?flavor=stable&platform=%s&slug=%s&version=%s\n' \
        "$GODOT_DOWNLOAD_ENDPOINT" "$platform" "$slug" "$GODOT_PROJECT_VERSION"
}

godot_template_version() {
    local staging_root="$1"
    local version_file
    local version

    version_file="$(find "$staging_root" -type f -name version.txt -print -quit 2>/dev/null || true)"
    if [[ -z "$version_file" ]]; then
        echo "❌ Godot Export Templates archive does not contain version.txt." >&2
        return 1
    fi
    version="$(sed -n '1p' "$version_file" | tr -d '\r')"
    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?\.[A-Za-z0-9_-]+([.][A-Za-z0-9_-]+)*$ ]]; then
        echo "❌ Godot Export Templates version.txt is invalid: $version" >&2
        return 1
    fi
    printf '%s\n' "$version"
}

godot_runner_version() {
    local binary="$1"
    local python_bin

    python_bin="$(project_python 2>/dev/null || true)"
    if [[ -z "$python_bin" ]]; then
        echo "❌ Repository Python environment is unavailable for the Godot runner." >&2
        return 1
    fi

    PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        "$python_bin" -m infrastructure.godot.runner version --binary "$binary"
}

godot_binary_has_required_version() {
    local binary="$1"
    local version

    load_godot_project_version || return 1
    [[ -x "$binary" ]] || return 1
    version="$(godot_runner_version "$binary")" || return 1
    # The shared runner intentionally normalizes patch/suffixes to major.minor.
    [[ "$version" == "$GODOT_PROJECT_VERSION" ]] || return 1
}

find_existing_godot_binary() {
    local candidate
    local command_name

    if [[ -n "${GODOT_BIN:-}" ]]; then
        if godot_binary_has_required_version "$GODOT_BIN" >/dev/null; then
            GODOT_RESOLVED_BIN="$GODOT_BIN"
            GODOT_RESOLVED_USER_HOME=""
            return 0
        fi
        return 1
    fi
    for command_name in godot4 godot Godot; do
        candidate="$(command -v "$command_name" 2>/dev/null || true)"
        if [[ -n "$candidate" ]] && godot_binary_has_required_version "$candidate" >/dev/null; then
            GODOT_RESOLVED_BIN="$candidate"
            GODOT_RESOLVED_USER_HOME=""
            return 0
        fi
    done
    for candidate in \
        "/Applications/Godot.app/Contents/MacOS/Godot" \
        "$HOME/Applications/Godot.app/Contents/MacOS/Godot"; do
        if godot_binary_has_required_version "$candidate" >/dev/null; then
            GODOT_RESOLVED_BIN="$candidate"
            GODOT_RESOLVED_USER_HOME=""
            return 0
        fi
    done
    return 1
}

check_godot_toolchain() {
    local managed_root
    local managed_binary
    local managed_user_home

    load_godot_project_version || return 1
    GODOT_RESOLVED_BIN=""
    GODOT_RESOLVED_USER_HOME=""
    managed_root="$(godot_toolchain_root)"
    managed_user_home="$(godot_user_home)"
    managed_binary="$(find "$managed_root" -type f \( -name Godot -o -name 'Godot*.x86_64' -o -name 'Godot*.exe' \) -perm -u=x 2>/dev/null | head -n 1)"
    if [[ -n "$managed_binary" ]] && godot_binary_has_required_version "$managed_binary" >/dev/null; then
        GODOT_RESOLVED_BIN="$managed_binary"
        GODOT_RESOLVED_USER_HOME="$managed_user_home"
        return 0
    fi
    find_existing_godot_binary
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
    local template_version_file
    local template_version
    local template_contents

    load_godot_project_version || return 1
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
            echo "${RED}  ❌ Current platform does not support automatic Godot setup: $(uname -s) $(uname -m)${RESET}" >&2
            return 1
            ;;
    esac
    if ! command -v curl >/dev/null 2>&1 || ! command -v unzip >/dev/null 2>&1; then
        echo "${RED}  ❌ Automatic Godot installation requires curl and unzip.${RESET}" >&2
        return 1
    fi
    editor_archive="$(mktemp "${TMPDIR:-/tmp}/elfienest-godot-editor.XXXXXX")"
    template_archive="$(mktemp "${TMPDIR:-/tmp}/elfienest-godot-templates.XXXXXX")"
    editor_staging="$(mktemp -d "${TMPDIR:-/tmp}/elfienest-godot-editor.XXXXXX")"
    template_staging="$(mktemp -d "${TMPDIR:-/tmp}/elfienest-godot-templates.XXXXXX")"

    echo "${CYAN}  📥 Downloading official Godot $GODOT_PROJECT_VERSION editor...${RESET}"
    if ! curl --fail --location --retry 3 --output "$editor_archive" "$(godot_download_url "$editor_platform" "$editor_slug")"; then
        echo "${RED}  ❌ Godot editor download failed.${RESET}" >&2
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi
    if ! unzip -q "$editor_archive" -d "$editor_staging"; then
        echo "${RED}  ❌ Godot editor extraction failed.${RESET}" >&2
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi
    echo "${CYAN}  📥 Downloading official Godot Web Export Templates...${RESET}"
    if ! curl --fail --location --retry 3 --output "$template_archive" "$(godot_download_url "templates" "export_templates.tpz")"; then
        echo "${RED}  ❌ Godot Web Export Templates download failed.${RESET}" >&2
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi
    if ! unzip -q "$template_archive" -d "$template_staging"; then
        echo "${RED}  ❌ Godot Web Export Templates extraction failed.${RESET}" >&2
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi
    template_version_file="$(find "$template_staging" -type f -name version.txt -print -quit 2>/dev/null || true)"
    if ! template_version="$(godot_template_version "$template_staging")"; then
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi
    case "$template_version" in
        "$GODOT_PROJECT_VERSION".*) ;;
        *)
            echo "${RED}  ❌ Godot Export Templates $template_version are outside compatibility line $GODOT_PROJECT_VERSION.${RESET}" >&2
            rm -f -- "$editor_archive" "$template_archive"
            rm -rf -- "$editor_staging" "$template_staging"
            return 1
            ;;
    esac
    template_contents="$(dirname "$template_version_file")"

    if ! godot_managed_root_is_safe "$root"; then
        echo "${RED}  ❌ Refusing to clean non-managed Godot directory: $root${RESET}" >&2
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi
    managed_root="$root"
    rm -rf -- "$managed_root"
    mkdir -p -- "$root" "$user_home/export_templates/$template_version"
    cp -R "$editor_staging"/* "$root/"
    cp -R "$template_contents"/. "$user_home/export_templates/$template_version/"
    editor_binary="$(find "$root" -type f \( -name Godot -o -name 'Godot*.x86_64' -o -name 'Godot*.exe' \) -perm -u+x | head -n 1)"
    if [[ -z "$editor_binary" ]] || ! godot_binary_has_required_version "$editor_binary" >/dev/null; then
        echo "${RED}  ❌ Godot editor post-install version verification failed.${RESET}" >&2
        rm -f -- "$editor_archive" "$template_archive"
        rm -rf -- "$editor_staging" "$template_staging"
        return 1
    fi
    GODOT_RESOLVED_BIN="$editor_binary"
    GODOT_RESOLVED_USER_HOME="$user_home"
    rm -f -- "$editor_archive" "$template_archive"
    rm -rf -- "$editor_staging" "$template_staging"
    echo "${GREEN}  ✅ Godot $GODOT_PROJECT_VERSION compatibility line and Web Export Templates $template_version ready${RESET}"
}

ensure_godot_toolchain() {
    local choice

    load_godot_project_version || return 1
    if check_godot_toolchain; then
        return 0
    fi
    echo "${YELLOW}  ⚠️ Source development/compilation requires the Godot $GODOT_PROJECT_VERSION compatibility line and matching Web Export Templates.${RESET}" >&2
    echo "     They are only used to export Godot Web Runtime from source, will not be included in official ElfieNest packages." >&2
    if [[ ! -t 0 ]]; then
        echo "${RED}  ❌ Non-interactive environment cannot confirm Godot installation; please install first or set GODOT_BIN.${RESET}" >&2
        return 1
    fi
    printf '     Install from official Godot source now? [y/N/path] ' >&2
    read -r choice
    case "$choice" in
        Y|y|yes|YES) install_official_godot_toolchain ;;
        ""|n|N|no|NO)
            echo "${RED}  ❌ Godot is required for source development/compilation, cancelled.${RESET}" >&2
            return 1
            ;;
        *)
            if godot_binary_has_required_version "$choice" >/dev/null; then
                GODOT_RESOLVED_BIN="$choice"
                GODOT_RESOLVED_USER_HOME=""
                return 0
            fi
            echo "${RED}  ❌ Specified Godot path is unavailable or outside compatibility line $GODOT_PROJECT_VERSION.${RESET}" >&2
            return 1
            ;;
    esac
}

ensure_godot_web() {
    if check_godot_web; then
        echo "${GREEN}  ✅ Godot Web Runtime ready${RESET}"
        return 0
    fi

    echo "${RED}  ❌ Godot Web Runtime missing; full product cannot start${RESET}" >&2
    if ! ensure_godot_toolchain; then
        return 1
    fi
    if [[ -n "$GODOT_RESOLVED_USER_HOME" ]]; then
        local python_bin
        python_bin="$(project_python)" || {
            echo "${RED}  ❌ Repository Python environment is unavailable.${RESET}" >&2
            return 1
        }
        if ! GODOT_BIN="$GODOT_RESOLVED_BIN" GODOT_USER_HOME="$GODOT_RESOLVED_USER_HOME" \
            "$python_bin" "$PROJECT_ROOT/scripts/build_godot_web.py" --ensure; then
            echo "${RED}  ❌ Godot compatibility line $GODOT_PROJECT_VERSION or matching Web Export Templates cannot export Web Runtime.${RESET}" >&2
            return 1
        fi
    else
        local python_bin
        python_bin="$(project_python)" || {
            echo "${RED}  ❌ Repository Python environment is unavailable.${RESET}" >&2
            return 1
        }
        if ! GODOT_BIN="$GODOT_RESOLVED_BIN" \
            "$python_bin" "$PROJECT_ROOT/scripts/build_godot_web.py" --ensure; then
            echo "${RED}  ❌ Godot compatibility line $GODOT_PROJECT_VERSION or matching Web Export Templates cannot export Web Runtime.${RESET}" >&2
            return 1
        fi
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
            echo "${GREEN}  ✅ Ollama ready (external runtime healthy)${RESET}"
            return 0
            ;;
    esac

    echo "${YELLOW}  ⚠️  Ollama optional and not installed.${RESET}"
    echo "     It provides local offline fallback when network is down or cloud unavailable; please install after confirming in Setup."
    return 2
}
