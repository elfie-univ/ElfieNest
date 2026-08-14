#!/bin/bash
# Source-free release bootstrap contract.  The published wrapper supplies this script.

set -euo pipefail
umask 077

DEFAULT_MANIFEST_URL="https://elfienest.com/releases/manifest.json"
DRY_RUN=0
NO_LAUNCH=0
MANIFEST_SOURCE="$DEFAULT_MANIFEST_URL"

if ! declare -F install_native_artifact >/dev/null 2>&1; then
    REMOTE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    # Local source execution uses the same helpers; published output embeds them.
    # shellcheck source=scripts/elfienest_install_helpers.sh
    source "$REMOTE_SCRIPT_DIR/elfienest_install_helpers.sh"
    # shellcheck source=scripts/native_install_artifact.sh
    source "$REMOTE_SCRIPT_DIR/native_install_artifact.sh"
fi

usage() {
    printf '%s\n' "usage: remote_install.sh [--dry-run] [--no-launch] [--manifest <path-or-url>] [--version]"
}

current_target() {
    if [[ -n "${ELFIENEST_TEST_TARGET:-}" ]]; then
        case "$ELFIENEST_TEST_TARGET" in
            darwin-arm64|darwin-x64|win32-x64|linux-x64) printf '%s\n' "$ELFIENEST_TEST_TARGET" ; return 0 ;;
            *) return 1 ;;
        esac
    fi
    case "$(uname -s)" in
        Darwin)
            case "$(uname -m)" in
                arm64) printf '%s\n' "darwin-arm64" ;;
                x86_64) printf '%s\n' "darwin-x64" ;;
                *) return 1 ;;
            esac
            ;;
        Linux)
            [[ "$(uname -m)" == "x86_64" ]] || return 1
            printf '%s\n' "linux-x64"
            ;;
        *) return 1 ;;
    esac
}

download_to() {
    local source="$1"
    local destination="$2"
    if [[ -f "$source" ]]; then
        cp -- "$source" "$destination"
        return
    fi
    command -v curl >/dev/null 2>&1 || return 1
    curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 -- "$source" --output "$destination"
}

parse_manifest() {
    local manifest="$1"
    local target="$2"
    local compact
    local version
    local entry

    compact="$(tr -d '[:space:]' < "$manifest")"
    version="$(printf '%s' "$compact" | sed -n 's/^{"schema_version":1,"version":"\([^"]*\)".*$/\1/p')"
    entry="$(printf '%s' "$compact" | sed -n "s/.*{\\\"target\\\":\\\"${target}\\\",\\\"url\\\":\\\"\([^\\\"]*\)\\\",\\\"size\\\":\([0-9][0-9]*\),\\\"sha256\\\":\\\"\([0-9a-f][0-9a-f]*\)\\\"}.*/\1|\2|\3/p")"
    [[ -n "$version" && -n "$entry" ]] || return 1
    IFS='|' read -r RELEASE_VERSION ARTIFACT_URL ARTIFACT_SIZE ARTIFACT_SHA256 <<< "$version|$entry"
    [[ "$ARTIFACT_SIZE" =~ ^[0-9]+$ && "$ARTIFACT_SHA256" =~ ^[0-9a-f]{64}$ ]] || return 1
}

artifact_filename_for_target() {
    case "$1" in
        darwin-arm64|darwin-x64) printf '%s\n' "ElfieNest.dmg" ;;
        win32-x64) printf '%s\n' "ElfieNest.exe" ;;
        linux-x64) printf '%s\n' "ElfieNest.AppImage" ;;
        *) return 1 ;;
    esac
}

artifact_sha256() {
    local artifact="$1"
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -- "$artifact" | awk '{print $1}'
        return
    fi
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -- "$artifact" | awk '{print $1}'
        return
    fi
    return 1
}

install_verified_artifact() {
    local artifact="$1"
    local application_root
    local cli_path
    local install_dir
    local wrapper
    local uninstaller
    local desktop_file=""
    local icon_file=""
    local source_icon=""

    application_root="$(native_application_root "$TARGET")" || return 1
    validate_native_application_destination "$TARGET" "$application_root" || return 1
    install_native_artifact "$TARGET" "$artifact" "$application_root" || return 1
    validate_native_application_root "$TARGET" "$application_root" || return 1
    if [[ "$TARGET" == "linux-x64" ]]; then
        install_linux_xdg_integration "$application_root" || return 1
        desktop_file="$(native_linux_desktop_file)"
        icon_file="$(native_linux_icon_file)"
        source_icon="$application_root/.DirIcon"
    fi
    cli_path="$(native_cli_path "$TARGET" "$application_root")" || return 1
    install_dir="$(choose_user_install_dir)" || return 1
    validate_user_install_dir "$install_dir" || return 1
    configure_user_path "$install_dir" || return 1
    wrapper="$install_dir/elfienest"
    uninstaller="$install_dir/uninstall-elfienest"
    write_managed_wrapper "$wrapper" "$cli_path"
    write_managed_uninstaller \
        "$uninstaller" "$wrapper" "$uninstaller" "$application_root" "$cli_path" \
        "$desktop_file" "$icon_file" "$source_icon"
    chmod 0755 "$wrapper" "$uninstaller"
    if (( NO_LAUNCH == 0 )); then
        launch_native_application "$TARGET" "$application_root" || return 1
    fi
}

while (( $# > 0 )); do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --no-launch) NO_LAUNCH=1 ;;
        --manifest)
            (( $# >= 2 )) || { usage >&2; exit 2; }
            MANIFEST_SOURCE="$2"
            shift
            ;;
        --version)
            printf '%s\n' "ElfieNest remote bootstrap 0.1.0-beta.1"
            exit 0
            ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
    shift
done

TARGET="$(current_target)" || { printf '%s\n' "unsupported-platform" >&2; exit 1; }
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/elfienest-bootstrap.XXXXXX")"
trap 'rm -rf -- "$TEMP_DIR"' EXIT HUP INT TERM
MANIFEST_PATH="$TEMP_DIR/manifest.json"
download_to "$MANIFEST_SOURCE" "$MANIFEST_PATH" || { printf '%s\n' "manifest-download-failed" >&2; exit 1; }
parse_manifest "$MANIFEST_PATH" "$TARGET" || { printf '%s\n' "manifest-invalid-or-target-missing" >&2; exit 1; }

printf 'target=%s\nversion=%s\nartifact_url=%s\napplication_root=%s\n' \
    "$TARGET" "$RELEASE_VERSION" "$ARTIFACT_URL" "platform-native-root"
if (( DRY_RUN == 1 )); then
    exit 0
fi

ARTIFACT_PATH="$TEMP_DIR/$(artifact_filename_for_target "$TARGET")" || exit 1
download_to "$ARTIFACT_URL" "$ARTIFACT_PATH" || { printf '%s\n' "artifact-download-failed" >&2; exit 1; }
[[ "$(wc -c < "$ARTIFACT_PATH" | tr -d '[:space:]')" == "$ARTIFACT_SIZE" ]] || {
    printf '%s\n' "artifact-size-mismatch" >&2
    exit 1
}
[[ "$(artifact_sha256 "$ARTIFACT_PATH")" == "$ARTIFACT_SHA256" ]] || {
    printf '%s\n' "artifact-checksum-mismatch" >&2
    exit 1
}
install_verified_artifact "$ARTIFACT_PATH" || {
    printf '%s\n' "native-install-failed" >&2
    exit 1
}
printf '%s\n' "remote-bootstrap-installed target=$TARGET version=$RELEASE_VERSION"
