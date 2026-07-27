#!/bin/bash
# ElfieNest user-level installation script

set -euo pipefail
umask 077

if (( EUID == 0 )); then
    builtin printf '%s\n' "❌ ElfieNest only supports user-level installation. Do not use root or sudo." >&2
    exit 1
fi

if [[ -n "${ELFIENEST_PYTHON:-}" ]]; then
    builtin printf '%s\n' "❌ ELFIENEST_PYTHON is not supported; installation must use the repo-pinned CPython 3.9.25." >&2
    exit 1
fi

echo ""
echo "🦊 ElfieNest Installation Script"
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
    echo "❌ Installation script does not accept arguments" >&2
    echo "   Please run ./install.sh directly to complete full installation." >&2
    exit 2
fi

if [ ! -f "$INSTALL_HELPERS" ]; then
    echo "❌ Missing installation helper script: $INSTALL_HELPERS" >&2
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
    echo "❌ Missing native app installation helper script: $NATIVE_INSTALL_HELPERS" >&2
    exit 1
fi
# shellcheck source=scripts/native_install_artifact.sh
source "$NATIVE_INSTALL_HELPERS"

read_pinned_python_version() {
    local version

    if [ ! -f "$PYTHON_VERSION_FILE" ]; then
        echo "❌ Missing Python version file: $PYTHON_VERSION_FILE" >&2
        return 1
    fi

    version="$(tr -d '[:space:]' < "$PYTHON_VERSION_FILE")"
    if [[ ! "$version" =~ ^3\.9\.[0-9]+$ ]]; then
        echo "❌ .python-version must be pinned to a complete CPython 3.9 patch version" >&2
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
        echo "❌ Missing repo-controlled Python runtime." >&2
        return 1
    fi
}

PYTHON_VERSION="$(read_pinned_python_version)"
NATIVE_TARGET="$(current_native_target)" || exit 1
APPLICATION_ROOT="$(native_application_root "$NATIVE_TARGET")" || exit 1
CLI_PATH="$(native_cli_path "$NATIVE_TARGET" "$APPLICATION_ROOT")" || exit 1
DESKTOP_FILE=""
ICON_FILE=""
SOURCE_ICON=""
if [[ "$NATIVE_TARGET" == "linux-x64" ]]; then
    DESKTOP_FILE="$(native_linux_desktop_file)"
    ICON_FILE="$(native_linux_icon_file)"
    SOURCE_ICON="$APPLICATION_ROOT/.DirIcon"
fi
if ! validate_native_application_destination "$NATIVE_TARGET" "$APPLICATION_ROOT"; then
    echo "❌ Native app directory does not match safe installation location for current platform: $APPLICATION_ROOT" >&2
    exit 1
fi

echo "📦 Installation mode: User installation"
INSTALL_DIR="$(choose_user_install_dir)"
if ! validate_user_install_dir "$INSTALL_DIR"; then
    echo "❌ Installation directory is not under current user's safe HOME path: $INSTALL_DIR" >&2
    exit 1
fi
echo "📍 Installation location: $INSTALL_DIR"
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
    "$CLI_PATH" \
    "$DESKTOP_FILE" \
    "$ICON_FILE" \
    "$SOURCE_ICON"

if path_contains_dir "$INSTALL_DIR"; then
    reject_shadowing_command "$COMMAND_NAME" "$INSTALLED_WRAPPER"
fi

INSTALL_ACTION="Install"
if [ -e "$INSTALLED_WRAPPER" ] || [ -L "$INSTALLED_WRAPPER" ]; then
    if ! managed_file_matches "$INSTALLED_WRAPPER" "$STAGED_WRAPPER" \
        && ! previous_wrapper_matches "$INSTALLED_WRAPPER" "$PROJECT_ROOT"; then
        echo "❌ Command already exists from another project, refusing to overwrite: $INSTALLED_WRAPPER"
        exit 1
    fi
    INSTALL_ACTION="Update"
fi
if [ -e "$INSTALLED_UNINSTALLER" ] || [ -L "$INSTALLED_UNINSTALLER" ]; then
    if ! managed_file_matches "$INSTALLED_UNINSTALLER" "$STAGED_UNINSTALLER" \
        && ! previous_uninstaller_matches \
            "$INSTALLED_UNINSTALLER" \
            "$INSTALLED_WRAPPER"; then
        echo "❌ Uninstall command already exists from another project, refusing to overwrite: $INSTALLED_UNINSTALLER"
        exit 1
    fi
fi

# Call bootstrap.sh to prepare all runtime dependencies
if ! ELFIENEST_FORCE_LOCKED_SYNC=1 "$SCRIPT_DIR/scripts/bootstrap.sh" ensure --tier=build; then
    echo "❌ Runtime dependency preparation failed" >&2
    exit 1
fi

if ! configure_user_path "$INSTALL_DIR"; then
    echo "❌ PATH configuration failed, ElfieNest did not modify any command entry points." >&2
    exit 1
fi
if ! validate_user_install_dir "$INSTALL_DIR"; then
    echo "❌ Directory security properties changed during installation, no command entry points modified." >&2
    exit 1
fi

RELEASE_ARTIFACT_PATH="$(mktemp "${TMPDIR:-/tmp}/elfienest-release-artifact.XXXXXX")"
PROJECT_PYTHON="$(project_python_executable)" || exit 1
if "$PROJECT_PYTHON" "$PROJECT_ROOT/scripts/release.py" \
    --target "$NATIVE_TARGET" \
    --source-install-artifact-output "$RELEASE_ARTIFACT_PATH"; then
    RELEASE_BUILD_STATUS=0
else
    RELEASE_BUILD_STATUS=$?
fi
if [[ "$RELEASE_BUILD_STATUS" -ne 0 && "$RELEASE_BUILD_STATUS" -ne 3 ]]; then
    echo "❌ Native application build failed, old app and old commands preserved." >&2
    exit 1
fi
IFS= read -r RELEASE_ARTIFACT < "$RELEASE_ARTIFACT_PATH" || true
if [ -z "${RELEASE_ARTIFACT:-}" ] || [ ! -f "$RELEASE_ARTIFACT" ]; then
    echo "❌ Native build did not produce any installable artifacts." >&2
    exit 1
fi
if ! install_native_artifact "$NATIVE_TARGET" "$RELEASE_ARTIFACT" "$APPLICATION_ROOT"; then
    echo "❌ Native application installation failed, old commands preserved." >&2
    exit 1
fi
if ! validate_native_application_root "$NATIVE_TARGET" "$APPLICATION_ROOT"; then
    echo "❌ Native application post-install resource verification failed." >&2
    exit 1
fi
if [[ "$NATIVE_TARGET" == "linux-x64" ]] \
    && ! install_linux_xdg_integration "$APPLICATION_ROOT"; then
    echo "❌ Linux application menu integration failed, installed app preserved." >&2
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

echo "✅ ${INSTALL_ACTION}ed elfienest command"
echo ""
echo "🎉 Installation complete!"
if ! launch_native_application "$NATIVE_TARGET" "$APPLICATION_ROOT"; then
    echo "⚠️  Application installed, but cannot auto-launch; please start from application menu or elfienest command." >&2
fi
echo ""
echo "Usage:"
echo "  elfienest              # Enter interactive main menu"
echo "  elfienest serve        # Start service"
echo "  elfienest --fallback   # Start with built-in engine"
echo "  elfienest config       # Configure system"
echo "  elfienest status       # View status"
echo "  elfienest --help       # View help"
echo ""
