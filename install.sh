#!/bin/bash
# ElfieNest 用户级安装脚本

set -euo pipefail
umask 077

if (( EUID == 0 )); then
    builtin printf '%s\n' "❌ ElfieNest 只支持用户级安装，请不要使用 root 或 sudo。" >&2
    exit 1
fi

if [[ -n "${ELFIENEST_PYTHON:-}" ]]; then
    builtin printf '%s\n' "❌ 不支持 ELFIENEST_PYTHON；安装必须使用仓库固定的 CPython 3.9.25。" >&2
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
NATIVE_INSTALL_HELPERS="$PROJECT_ROOT/scripts/native_install_artifact.sh"
COMMAND_NAME="elfienest"
UNINSTALL_COMMAND_NAME="uninstall-elfienest"
INSTALL_LOG_PATH=""
STAGED_WRAPPER=""
STAGED_UNINSTALLER=""
RELEASE_ARTIFACT_PATH=""

if [ "$#" -gt 0 ]; then
    echo "❌ 安装脚本不接受参数" >&2
    echo "   请直接运行 ./install.sh 完成完整安装。" >&2
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
    [ -z "$RELEASE_ARTIFACT_PATH" ] || rm -f -- "$RELEASE_ARTIFACT_PATH"
}

trap cleanup_install_artifacts EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$PROJECT_ROOT"
INSTALL_LOG_PATH="$(mktemp "${TMPDIR:-/tmp}/elfienest-install.XXXXXX")"
if [ ! -f "$NATIVE_INSTALL_HELPERS" ]; then
    echo "❌ 缺少原生应用安装辅助脚本: $NATIVE_INSTALL_HELPERS" >&2
    exit 1
fi
# shellcheck source=scripts/native_install_artifact.sh
source "$NATIVE_INSTALL_HELPERS"

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

project_python_executable() {
    local unix_python="$PROJECT_ROOT/.venv/bin/python"
    local windows_python="$PROJECT_ROOT/.venv/Scripts/python.exe"

    if [ -x "$unix_python" ]; then
        printf '%s\n' "$unix_python"
    elif [ -x "$windows_python" ]; then
        printf '%s\n' "$windows_python"
    else
        echo "❌ 缺少仓库受控的 Python 运行时。" >&2
        return 1
    fi
}

PYTHON_VERSION="$(read_pinned_python_version)"
NATIVE_TARGET="$(current_native_target)" || exit 1
APPLICATION_ROOT="$(native_application_root "$NATIVE_TARGET")" || exit 1
CLI_PATH="$(native_cli_path "$NATIVE_TARGET" "$APPLICATION_ROOT")" || exit 1
if ! ensure_safe_user_install_dir "${APPLICATION_ROOT%/*}"; then
    echo "❌ 原生应用目录不属于当前用户的安全 HOME 路径: ${APPLICATION_ROOT%/*}" >&2
    exit 1
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
write_managed_wrapper "$STAGED_WRAPPER" "$CLI_PATH"
write_managed_uninstaller \
    "$STAGED_UNINSTALLER" \
    "$INSTALLED_WRAPPER" \
    "$INSTALLED_UNINSTALLER" \
    "$APPLICATION_ROOT" \
    "$CLI_PATH"

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

# 调用 bootstrap.sh 准备所有运行时依赖
if ! ELFIENEST_FORCE_LOCKED_SYNC=1 "$SCRIPT_DIR/scripts/bootstrap.sh" ensure --tier=prod; then
    echo "❌ 运行时依赖准备失败" >&2
    exit 1
fi

if ! configure_user_path "$INSTALL_DIR"; then
    echo "❌ PATH 配置失败，ElfieNest 未修改任何命令入口。" >&2
    exit 1
fi
if ! validate_user_install_dir "$INSTALL_DIR"; then
    echo "❌ 安装期间目录安全属性发生变化，未修改任何命令入口。" >&2
    exit 1
fi

RELEASE_ARTIFACT_PATH="$(mktemp "${TMPDIR:-/tmp}/elfienest-release-artifact.XXXXXX")"
PROJECT_PYTHON="$(project_python_executable)" || exit 1
if ! "$PROJECT_PYTHON" "$PROJECT_ROOT/scripts/release.py" \
    --target "$NATIVE_TARGET" \
    --artifact-output "$RELEASE_ARTIFACT_PATH"; then
    echo "❌ 本机原生应用构建失败，已保留旧应用与旧命令。" >&2
    exit 1
fi
IFS= read -r RELEASE_ARTIFACT < "$RELEASE_ARTIFACT_PATH" || true
if [ -z "${RELEASE_ARTIFACT:-}" ] || [ ! -f "$RELEASE_ARTIFACT" ]; then
    echo "❌ 原生构建没有产生可安装的发行物。" >&2
    exit 1
fi
if ! install_native_artifact "$NATIVE_TARGET" "$RELEASE_ARTIFACT" "$APPLICATION_ROOT"; then
    echo "❌ 原生应用安装失败，已保留旧命令。" >&2
    exit 1
fi
if ! validate_native_application_root "$NATIVE_TARGET" "$APPLICATION_ROOT"; then
    echo "❌ 原生应用安装后的资源校验失败。" >&2
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
