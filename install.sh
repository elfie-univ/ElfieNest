#!/bin/bash
# ElfieNest 用户级安装脚本

set -euo pipefail
umask 077

if (( EUID == 0 )); then
    builtin printf '%s\n' "❌ ElfieNest 只支持用户级安装，请不要使用 root 或 sudo。" >&2
    exit 1
fi

echo ""
echo "🦊 ElfieNest 安装脚本"
echo "======================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
PYTHON_VERSION_FILE="$PROJECT_ROOT/.python-version"
INSTALL_HELPERS="$PROJECT_ROOT/scripts/elfienest_install_helpers.sh"
RUNTIME_DEPENDENCY_CHECK='import edge_tts, fastapi, httpx, multipart, pydantic, rich, uvicorn, websockets, yaml'
COMMAND_NAME="elfienest"
UNINSTALL_COMMAND_NAME="uninstall-elfienest"
ENVIRONMENT_ONLY=false
INSTALL_LOG_PATH=""
STAGED_WRAPPER=""
STAGED_UNINSTALLER=""

case "${1:-}" in
    "") ;;
    --env-only) ENVIRONMENT_ONLY=true ;;
    *)
        echo "❌ 未知安装参数: $1" >&2
        echo "   用法: ./install.sh [--env-only]" >&2
        exit 2
        ;;
esac
if [ "$#" -gt 1 ]; then
    echo "❌ 安装脚本最多接受一个参数" >&2
    exit 2
fi

if [ ! -f "$INSTALL_HELPERS" ]; then
    echo "❌ 缺少安装辅助脚本: $INSTALL_HELPERS" >&2
    exit 1
fi
# shellcheck source=scripts/elfienest_install_helpers.sh
source "$INSTALL_HELPERS"

cleanup_install_artifacts() {
    [ -z "$INSTALL_LOG_PATH" ] || rm -f -- "$INSTALL_LOG_PATH"
    [ -z "$STAGED_WRAPPER" ] || rm -f -- "$STAGED_WRAPPER"
    [ -z "$STAGED_UNINSTALLER" ] || rm -f -- "$STAGED_UNINSTALLER"
}

trap cleanup_install_artifacts EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$PROJECT_ROOT"
INSTALL_LOG_PATH="$(mktemp "${TMPDIR:-/tmp}/elfienest-install.XXXXXX")"

read_pinned_python_version() {
    local version

    if [ ! -f "$PYTHON_VERSION_FILE" ]; then
        echo "❌ 缺少 Python 版本文件: $PYTHON_VERSION_FILE" >&2
        return 1
    fi

    version="$(tr -d '[:space:]' < "$PYTHON_VERSION_FILE")"
    if [[ ! "$version" =~ ^3\.9\.[0-9]+$ ]]; then
        echo "❌ .python-version 必须固定到 CPython 3.9 的完整补丁版本" >&2
        return 1
    fi
    printf '%s\n' "$version"
}

PYTHON_VERSION="$(read_pinned_python_version)"

python_is_pinned_version() {
    "$1" -c 'import platform, sys; ok = sys.implementation.name == "cpython" and platform.python_version() == sys.argv[1]; raise SystemExit(0 if ok else 1)' "$PYTHON_VERSION" >/dev/null 2>&1
}

python_has_runtime_dependencies() {
    python_is_pinned_version "$1" || return 1
    "$1" -c "$RUNTIME_DEPENDENCY_CHECK" >/dev/null 2>&1
}

resolve_custom_python() {
    local candidate="$1"
    local resolved

    resolved="$(command -v "$candidate" 2>/dev/null || true)"
    [ -n "$resolved" ] || resolved="$candidate"
    if [ ! -x "$resolved" ] || ! python_is_pinned_version "$resolved"; then
        echo "❌ ELFIENEST_PYTHON 必须指向 CPython $PYTHON_VERSION 可执行文件" >&2
        return 1
    fi
    printf '%s\n' "$resolved"
}

ensure_project_venv() {
    local python_request
    local uv_bin
    local venv_python="$PROJECT_ROOT/.venv/bin/python3"

    uv_bin="$(command -v uv 2>/dev/null || true)"
    if [ -z "$uv_bin" ]; then
        echo "❌ 未找到 uv，无法创建锁定的 CPython $PYTHON_VERSION 环境"
        echo "   macOS: brew install uv"
        echo "   其他平台: https://docs.astral.sh/uv/getting-started/installation/"
        return 1
    fi

    if [ -n "${ELFIENEST_PYTHON:-}" ]; then
        python_request="$(resolve_custom_python "$ELFIENEST_PYTHON")"
    else
        python_request="$PYTHON_VERSION"
        echo "🐍 正在准备 CPython $PYTHON_VERSION..."
        if ! "$uv_bin" python install "$PYTHON_VERSION" >> "$INSTALL_LOG_PATH" 2>&1; then
            echo "❌ CPython $PYTHON_VERSION 安装失败，最近日志:"
            tail -40 "$INSTALL_LOG_PATH" || true
            return 1
        fi
    fi

    echo "📦 正在按 uv.lock 同步项目依赖..."
    echo "   详情日志: $INSTALL_LOG_PATH"
    if ! UV_PROJECT_ENVIRONMENT="$PROJECT_ROOT/.venv" "$uv_bin" sync --locked --no-dev --python "$python_request" >> "$INSTALL_LOG_PATH" 2>&1; then
        echo "❌ 锁定环境同步失败，最近日志:"
        tail -40 "$INSTALL_LOG_PATH" || true
        return 1
    fi

    if ! python_has_runtime_dependencies "$venv_python"; then
        echo "❌ 同步后的环境不满足 CPython $PYTHON_VERSION 或运行依赖要求"
        return 1
    fi
    echo "✅ CPython $PYTHON_VERSION 与锁定依赖已就绪"
}

if [ "$ENVIRONMENT_ONLY" = true ]; then
    ensure_project_venv
    echo "🎉 项目环境配置完成！"
    exit 0
fi

echo "📦 安装模式: 用户安装"
INSTALL_DIR="$(choose_user_install_dir)"
if ! validate_user_install_dir "$INSTALL_DIR"; then
    echo "❌ 安装目录不属于当前用户的安全 HOME 路径: $INSTALL_DIR" >&2
    exit 1
fi
echo "📍 安装位置: $INSTALL_DIR"
echo ""

INSTALLED_WRAPPER="$INSTALL_DIR/$COMMAND_NAME"
INSTALLED_UNINSTALLER="$INSTALL_DIR/$UNINSTALL_COMMAND_NAME"
STAGED_WRAPPER="$(mktemp "$INSTALL_DIR/.elfienest-wrapper.XXXXXX")"
STAGED_UNINSTALLER="$(mktemp "$INSTALL_DIR/.elfienest-uninstaller.XXXXXX")"
write_managed_wrapper "$STAGED_WRAPPER" "$PROJECT_ROOT"
write_managed_uninstaller \
    "$STAGED_UNINSTALLER" \
    "$INSTALLED_WRAPPER" \
    "$INSTALLED_UNINSTALLER" \
    "$PROJECT_ROOT"

if path_contains_dir "$INSTALL_DIR"; then
    reject_shadowing_command "$COMMAND_NAME" "$INSTALLED_WRAPPER"
fi

INSTALL_ACTION="安装"
if [ -e "$INSTALLED_WRAPPER" ] || [ -L "$INSTALLED_WRAPPER" ]; then
    if ! managed_file_matches "$INSTALLED_WRAPPER" "$STAGED_WRAPPER" \
        && ! previous_wrapper_matches "$INSTALLED_WRAPPER" "$PROJECT_ROOT"; then
        echo "❌ 已存在不属于当前项目的命令，拒绝覆盖: $INSTALLED_WRAPPER"
        exit 1
    fi
    INSTALL_ACTION="更新"
fi
if [ -e "$INSTALLED_UNINSTALLER" ] || [ -L "$INSTALLED_UNINSTALLER" ]; then
    if ! managed_file_matches "$INSTALLED_UNINSTALLER" "$STAGED_UNINSTALLER" \
        && ! previous_uninstaller_matches \
            "$INSTALLED_UNINSTALLER" \
            "$INSTALLED_WRAPPER"; then
        echo "❌ 已存在不属于当前项目的卸载命令，拒绝覆盖: $INSTALLED_UNINSTALLER"
        exit 1
    fi
fi

ensure_project_venv

if ! configure_user_path "$INSTALL_DIR"; then
    echo "❌ PATH 配置失败，ElfieNest 未修改任何命令入口。" >&2
    exit 1
fi
if ! validate_user_install_dir "$INSTALL_DIR"; then
    echo "❌ 安装期间目录安全属性发生变化，未修改任何命令入口。" >&2
    exit 1
fi

mv -f -- "$STAGED_UNINSTALLER" "$INSTALLED_UNINSTALLER"
STAGED_UNINSTALLER=""
mv -f -- "$STAGED_WRAPPER" "$INSTALLED_WRAPPER"
STAGED_WRAPPER=""
chmod 0755 "$INSTALLED_WRAPPER" "$INSTALLED_UNINSTALLER"

migrate_legacy_installations \
    "$PROJECT_ROOT" \
    "$INSTALL_DIR" \
    "/usr/local/bin/elfie"

echo "✅ 已${INSTALL_ACTION} elfienest 命令"
echo ""
echo "🎉 安装完成！"
echo ""
echo "使用方法:"
echo "  elfienest              # 进入交互式主菜单"
echo "  elfienest serve        # 启动服务"
echo "  elfienest --fallback   # 使用内置引擎启动"
echo "  elfienest config       # 配置系统"
echo "  elfienest status       # 查看状态"
echo "  elfienest --help       # 查看帮助"
echo ""
