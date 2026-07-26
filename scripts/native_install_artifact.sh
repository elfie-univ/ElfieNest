#!/bin/bash
# Platform-native application installation helpers for source-built artifacts.

native_cli_path() {
    local target="$1"
    local application_root="$2"
    local executable="ElfieNestCli"

    case "$target" in
        darwin-arm64|darwin-x64)
            printf '%s\n' "$application_root/Contents/Resources/management-cli/$executable"
            ;;
        win32-x64)
            printf '%s\n' "$application_root/resources/management-cli/$executable.exe"
            ;;
        linux-x64)
            printf '%s\n' "$application_root/resources/management-cli/$executable"
            ;;
        *) return 1 ;;
    esac
}

validate_native_application_root() {
    local target="$1"
    local application_root="$2"
    local cli_path

    cli_path="$(native_cli_path "$target" "$application_root")" || return 1
    [[ -d "$application_root" && ! -L "$application_root" \
        && -f "$cli_path" && ! -L "$cli_path" && -x "$cli_path" ]]
}

replace_native_application_root() {
    local target="$1"
    local source_root="$2"
    local destination_root="$3"
    local destination_parent
    local staging_parent
    local staged_root
    local backup_root

    validate_native_application_root "$target" "$source_root" || {
        echo "native-install-source-invalid target=$target path=$source_root" >&2
        return 1
    }
    destination_parent="${destination_root%/*}"
    mkdir -p -- "$destination_parent" || return 1
    staging_parent="$(mktemp -d "$destination_parent/.elfienest-app.XXXXXX")" || return 1
    staged_root="$staging_parent/${destination_root##*/}"
    backup_root="$destination_parent/.${destination_root##*/}.backup.$$"

    if ! cp -R -- "$source_root" "$staged_root"; then
        rm -rf -- "$staging_parent"
        return 1
    fi
    if ! validate_native_application_root "$target" "$staged_root"; then
        rm -rf -- "$staging_parent"
        echo "native-install-staging-invalid target=$target" >&2
        return 1
    fi
    if [[ -e "$destination_root" || -L "$destination_root" ]]; then
        if [[ ! -d "$destination_root" || -L "$destination_root" \
            || -e "$backup_root" || -L "$backup_root" ]]; then
            rm -rf -- "$staging_parent"
            echo "native-install-destination-invalid path=$destination_root" >&2
            return 1
        fi
        if ! mv -- "$destination_root" "$backup_root"; then
            rm -rf -- "$staging_parent"
            return 1
        fi
    fi
    if ! mv -- "$staged_root" "$destination_root"; then
        [[ ! -e "$backup_root" && ! -L "$backup_root" ]] || mv -- "$backup_root" "$destination_root"
        rm -rf -- "$staging_parent"
        return 1
    fi
    rm -rf -- "$staging_parent"
    if [[ -e "$backup_root" || -L "$backup_root" ]]; then
        [[ -d "$backup_root" && ! -L "$backup_root" ]] || return 1
        rm -rf -- "$backup_root"
    fi
}

install_macos_app_bundle() {
    local source_bundle="$1"
    local destination_bundle="$2"
    local target="${3:-darwin-x64}"

    replace_native_application_root "$target" "$source_bundle" "$destination_bundle"
}

install_macos_dmg() {
    local artifact="$1"
    local destination_bundle="$2"
    local target="$3"
    local mountpoint
    local bundle
    local result

    [[ -f "$artifact" && "$artifact" == *.dmg ]] || return 1
    mountpoint="$(mktemp -d "${TMPDIR:-/tmp}/elfienest-dmg.XXXXXX")" || return 1
    if ! hdiutil attach -nobrowse -readonly -mountpoint "$mountpoint" "$artifact" >/dev/null; then
        rmdir -- "$mountpoint" 2>/dev/null || true
        return 1
    fi
    bundle="$mountpoint/ElfieNest.app"
    replace_native_application_root "$target" "$bundle" "$destination_bundle"
    result=$?
    hdiutil detach "$mountpoint" >/dev/null 2>&1 || true
    rmdir -- "$mountpoint" 2>/dev/null || true
    return "$result"
}

install_windows_nsis() {
    local artifact="$1"
    local destination_root="$2"
    local destination_parent="${destination_root%/*}"
    local staging_parent
    local staged_root
    local result

    [[ -f "$artifact" && "$artifact" == *.exe ]] || return 1
    mkdir -p -- "$destination_parent" || return 1
    staging_parent="$(mktemp -d "$destination_parent/.elfienest-nsis.XXXXXX")" || return 1
    staged_root="$staging_parent/ElfieNest"
    "$artifact" /S "/D=$staged_root"
    result=$?
    if (( result == 0 )); then
        replace_native_application_root "win32-x64" "$staged_root" "$destination_root"
        result=$?
    fi
    rm -rf -- "$staging_parent"
    return "$result"
}

install_linux_appimage() {
    local artifact="$1"
    local destination_root="$2"
    local staging_parent
    local staged_artifact
    local result

    [[ -f "$artifact" && "$artifact" == *.AppImage ]] || return 1
    staging_parent="$(mktemp -d "${TMPDIR:-/tmp}/elfienest-appimage.XXXXXX")" || return 1
    staged_artifact="$staging_parent/ElfieNest.AppImage"
    cp -- "$artifact" "$staged_artifact" || {
        rm -rf -- "$staging_parent"
        return 1
    }
    chmod 0755 "$staged_artifact"
    if ! (cd "$staging_parent" && ./ElfieNest.AppImage --appimage-extract >/dev/null); then
        rm -rf -- "$staging_parent"
        return 1
    fi
    replace_native_application_root "linux-x64" "$staging_parent/squashfs-root" "$destination_root"
    result=$?
    rm -rf -- "$staging_parent"
    return "$result"
}

install_native_artifact() {
    local target="$1"
    local artifact="$2"
    local destination_root="$3"

    case "$target" in
        darwin-arm64|darwin-x64) install_macos_dmg "$artifact" "$destination_root" "$target" ;;
        win32-x64) install_windows_nsis "$artifact" "$destination_root" ;;
        linux-x64) install_linux_appimage "$artifact" "$destination_root" ;;
        *) return 1 ;;
    esac
}

native_application_root() {
    local target="$1"

    case "$target" in
        darwin-arm64|darwin-x64) printf '%s\n' "$HOME/Applications/ElfieNest.app" ;;
        win32-x64) printf '%s\n' "${LOCALAPPDATA:-$HOME/AppData/Local}/Programs/ElfieNest" ;;
        linux-x64) printf '%s\n' "$HOME/.local/opt/ElfieNest" ;;
        *) return 1 ;;
    esac
}

current_native_target() {
    local system_name
    local machine

    system_name="$(uname -s)"
    machine="$(uname -m)"
    case "$system_name:$machine" in
        Darwin:arm64|Darwin:aarch64) printf '%s\n' "darwin-arm64" ;;
        Darwin:x86_64) printf '%s\n' "darwin-x64" ;;
        MINGW*:x86_64|MSYS*:x86_64|CYGWIN*:x86_64) printf '%s\n' "win32-x64" ;;
        Linux:x86_64|Linux:amd64) printf '%s\n' "linux-x64" ;;
        *)
            echo "native-install-host-unsupported system=$system_name machine=$machine" >&2
            return 1
            ;;
    esac
}
