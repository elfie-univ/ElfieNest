#!/bin/bash
# User-level entry point and file safety functions for install.sh.

path_contains_dir() {
    local dir="$1"
    [[ ":$PATH:" == *":$dir:"* ]]
}

directory_mode_is_safe() {
    local dir="$1"
    local mode

    if mode="$(/usr/bin/stat -f '%Lp' "$dir" 2>/dev/null)" \
        && [[ "$mode" =~ ^[0-7]{3,4}$ ]]; then
        :
    elif mode="$(/usr/bin/stat -c '%a' "$dir" 2>/dev/null)" \
        && [[ "$mode" =~ ^[0-7]{3,4}$ ]]; then
        :
    else
        return 1
    fi
    (( (8#$mode & 8#022) == 0 ))
}

validate_user_install_dir() {
    local current="$1"

    case "$current" in
        "$HOME"|"$HOME"/*) ;;
        *) return 1 ;;
    esac
    while true; do
        if [ "$current" != "$HOME" ] && [ -L "$current" ]; then
            return 1
        fi
        [ -d "$current" ] || return 1
        [ -w "$current" ] || return 1
        [ -O "$current" ] || return 1
        directory_is_within_home "$current" || return 1
        directory_mode_is_safe "$current" || return 1
        [ "$current" != "$HOME" ] || return 0
        current="${current%/*}"
    done
}

ensure_safe_user_install_dir() {
    local dir="$1"
    local parent

    case "$dir" in
        "$HOME"|"$HOME"/*) ;;
        *) return 1 ;;
    esac
    if [ -e "$dir" ] || [ -L "$dir" ]; then
        validate_user_install_dir "$dir"
        return
    fi
    if [ "$dir" = "$HOME" ]; then
        mkdir -p "$dir" 2>/dev/null || return 1
    else
        parent="${dir%/*}"
        ensure_safe_user_install_dir "$parent" || return 1
        mkdir "$dir" 2>/dev/null || [ -d "$dir" ] || return 1
    fi
    validate_user_install_dir "$dir"
}

choose_user_install_dir() {
    local dir
    local path_dirs

    IFS=":" read -r -a path_dirs <<< "$PATH"
    for dir in "${path_dirs[@]}"; do
        if { [ "$dir" = "$HOME/.local/bin" ] || [ "$dir" = "$HOME/bin" ]; } \
            && { [ -e "$dir/elfienest" ] \
                || [ -L "$dir/elfienest" ] \
                || [ -e "$dir/uninstall-elfienest" ] \
                || [ -L "$dir/uninstall-elfienest" ]; } \
            && ensure_safe_user_install_dir "$dir"; then
            printf '%s\n' "$dir"
            return
        fi
    done
    for dir in "${path_dirs[@]}"; do
        [ -n "$dir" ] || continue
        if { [ "$dir" = "$HOME/.local/bin" ] || [ "$dir" = "$HOME/bin" ]; } \
            && ensure_safe_user_install_dir "$dir"; then
            printf '%s\n' "$dir"
            return
        fi
    done

    if ! ensure_safe_user_install_dir "$HOME/.local/bin"; then
        echo "❌ Cannot create safe user command directory: $HOME/.local/bin" >&2
        return 1
    fi
    printf '%s\n' "$HOME/.local/bin"
}

configure_user_path() {
    local install_dir="$1"
    local grep_status
    local path_line='export PATH="$HOME/.local/bin:$PATH"'
    local profile_file
    local shell_name

    if path_contains_dir "$install_dir"; then
        echo "✅ $install_dir is already in current PATH, this terminal can use elfienest directly"
        return
    fi
    if [ "$install_dir" != "$HOME/.local/bin" ]; then
        echo "❌ Cannot auto-configure non-standard user command directory: $install_dir" >&2
        return 1
    fi

    shell_name="${SHELL##*/}"
    if [ "$shell_name" = "bash" ]; then
        profile_file="$HOME/.bashrc"
    else
        profile_file="$HOME/.zshrc"
    fi

    if ! touch "$profile_file" 2>/dev/null; then
        echo "❌ Cannot create or update PATH config file: $profile_file" >&2
        return 1
    fi
    if grep -Fqx "$path_line" "$profile_file" 2>/dev/null; then
        echo "✅ $profile_file already contains PATH configuration"
    else
        grep_status=$?
        if [ "$grep_status" -ne 1 ]; then
            echo "❌ Cannot read PATH config file: $profile_file" >&2
            return 1
        fi
        if ! {
            builtin printf '\n'
            builtin printf '%s\n' "# ElfieNest CLI"
            builtin printf '%s\n' "$path_line"
        } >> "$profile_file"; then
            echo "❌ Cannot write to PATH config file: $profile_file" >&2
            return 1
        fi
        echo "✅ PATH configuration written to: $profile_file"
    fi
    echo "✅ New terminals can use elfienest directly"
    echo "ℹ️  Current terminal can run directly: $install_dir/elfienest"
}

write_managed_wrapper() {
    local output_path="$1"
    local cli_path="$2"

    {
        printf '#!/bin/bash\n'
        printf '# ElfieNest managed wrapper v2\n'
        printf 'set -eu\n'
        printf 'CLI_PATH=%q\n' "$cli_path"
        printf 'exec "$CLI_PATH" "$@"\n'
    } > "$output_path"
    chmod 0755 "$output_path"
}

write_managed_uninstaller() {
    local output_path="$1"
    local wrapper_path="$2"
    local uninstaller_path="$3"
    local application_root="$4"
    local cli_path="$5"
    local desktop_file="${6:-}"
    local icon_file="${7:-}"
    local source_icon="${8:-}"

    {
        printf '#!/bin/bash\n'
        printf '# ElfieNest managed uninstaller v2\n'
        printf 'set -eu\n'
        printf 'umask 077\n'
        printf 'WRAPPER_PATH=%q\n' "$wrapper_path"
        printf 'UNINSTALLER_PATH=%q\n' "$uninstaller_path"
        printf 'APPLICATION_ROOT=%q\n' "$application_root"
        printf 'CLI_PATH=%q\n' "$cli_path"
        printf 'DESKTOP_FILE=%q\n' "$desktop_file"
        printf 'ICON_FILE=%q\n' "$icon_file"
        printf 'SOURCE_ICON=%q\n' "$source_icon"
        printf '%s\n' 'wrapper_is_managed() {'
        printf '%s\n' '    local expected_cli_line'
        printf '%s\n' '    local line_count'
        printf '%s\n' '    [ -f "$WRAPPER_PATH" ] || return 1'
        printf '%s\n' '    [ ! -L "$WRAPPER_PATH" ] || return 1'
        printf '%s\n' "    printf -v expected_cli_line 'CLI_PATH=%q' \"\$CLI_PATH\""
        printf '%s\n' '    line_count="$(wc -l < "$WRAPPER_PATH" | tr -d '\''[:space:]'\'')"'
        printf '%s\n' '    [ "$line_count" = "5" ] || return 1'
        printf '%s\n' '    grep -Fqx '\''#!/bin/bash'\'' "$WRAPPER_PATH" || return 1'
        printf '%s\n' '    grep -Fqx '\''# ElfieNest managed wrapper v2'\'' "$WRAPPER_PATH" || return 1'
        printf '%s\n' '    grep -Fqx '\''set -eu'\'' "$WRAPPER_PATH" || return 1'
        printf '%s\n' '    grep -Fqx "$expected_cli_line" "$WRAPPER_PATH" || return 1'
        printf '%s\n' '    grep -Fqx '\''exec "$CLI_PATH" "$@"'\'' "$WRAPPER_PATH" || return 1'
        printf '%s\n' '}'
        printf '%s\n' 'application_is_managed() {'
        printf '%s\n' '    [ -d "$APPLICATION_ROOT" ] || return 1'
        printf '%s\n' '    [ ! -L "$APPLICATION_ROOT" ] || return 1'
        printf '%s\n' '    [ -f "$CLI_PATH" ] || return 1'
        printf '%s\n' '    [ ! -L "$CLI_PATH" ] || return 1'
        printf '%s\n' '    [ -x "$CLI_PATH" ] || return 1'
        printf '%s\n' '}'
        printf '%s\n' 'remove_linux_xdg_integration() {'
        printf '%s\n' '    if [ -n "$DESKTOP_FILE" ] && { [ -e "$DESKTOP_FILE" ] || [ -L "$DESKTOP_FILE" ]; }; then'
        printf '%s\n' '        [ -f "$DESKTOP_FILE" ] && [ ! -L "$DESKTOP_FILE" ] || return 1'
        printf '%s\n' '        grep -Fqx "Exec=$APPLICATION_ROOT/AppRun" "$DESKTOP_FILE" || return 1'
        printf '%s\n' '        rm -f -- "$DESKTOP_FILE"'
        printf '%s\n' '    fi'
        printf '%s\n' '    if [ -n "$ICON_FILE" ] && [ -n "$SOURCE_ICON" ] && [ -e "$ICON_FILE" ]; then'
        printf '%s\n' '        [ -f "$ICON_FILE" ] && [ ! -L "$ICON_FILE" ] && [ -f "$SOURCE_ICON" ] && [ ! -L "$SOURCE_ICON" ] || return 1'
        printf '%s\n' '        cmp -s "$ICON_FILE" "$SOURCE_ICON" || return 1'
        printf '%s\n' '        rm -f -- "$ICON_FILE"'
        printf '%s\n' '    fi'
        printf '%s\n' '}'
        printf '%s\n' 'if [ -L "$UNINSTALLER_PATH" ]; then'
        printf '%s\n' '    echo "❌ Uninstall entry is a symlink, refusing to operate: $UNINSTALLER_PATH" >&2'
        printf '%s\n' '    exit 1'
        printf '%s\n' 'fi'
        printf '%s\n' 'if [ -e "$WRAPPER_PATH" ] || [ -L "$WRAPPER_PATH" ]; then'
        printf '%s\n' '    if ! wrapper_is_managed; then'
        printf '%s\n' '        echo "❌ elfienest command has been modified, refusing to delete: $WRAPPER_PATH" >&2'
        printf '%s\n' '        exit 1'
        printf '%s\n' '    fi'
        printf '%s\n' '    rm -f -- "$WRAPPER_PATH"'
        printf '%s\n' 'fi'
        printf '%s\n' 'if [ -e "$APPLICATION_ROOT" ] || [ -L "$APPLICATION_ROOT" ]; then'
        printf '%s\n' '    if ! application_is_managed; then'
        printf '%s\n' '        echo "❌ Application directory has been modified, refusing to delete: $APPLICATION_ROOT" >&2'
        printf '%s\n' '        exit 1'
        printf '%s\n' '    fi'
        printf '%s\n' '    remove_linux_xdg_integration || {'
        printf '%s\n' '        echo "❌ XDG application integration has been modified, refusing to delete: $DESKTOP_FILE" >&2'
        printf '%s\n' '        exit 1'
        printf '%s\n' '    }'
        printf '%s\n' '    rm -rf -- "$APPLICATION_ROOT"'
        printf '%s\n' 'fi'
        printf '%s\n' 'rm -f -- "$UNINSTALLER_PATH"'
        printf '%s\n' 'echo "✅ ElfieNest uninstalled"'
    } > "$output_path"
    chmod 0755 "$output_path"
}

managed_file_matches() {
    local installed_path="$1"
    local expected_path="$2"

    [ -f "$installed_path" ] || return 1
    [ ! -L "$installed_path" ] || return 1
    cmp -s "$installed_path" "$expected_path"
}

previous_wrapper_matches() {
    local wrapper_path="$1"
    local project_root="$2"

    [ -f "$wrapper_path" ] || return 1
    [ ! -L "$wrapper_path" ] || return 1
    cmp -s "$wrapper_path" <(
        printf '#!/bin/bash\n# ElfieNest managed wrapper v1\nPROJECT_ROOT=%q\nexec "\$PROJECT_ROOT/elfienest.sh" "\$@"\n' \
            "$project_root"
    ) && return 0
    cmp -s "$wrapper_path" <(
        printf '#!/bin/bash\n# ElfieNest project: %s\ncd "%s"\nexec ./elfienest.sh "$@"\n' \
            "$project_root" \
            "$project_root"
    )
}

previous_uninstaller_matches() {
    local uninstaller_path="$1"
    local wrapper_path="$2"

    [ -f "$uninstaller_path" ] || return 1
    [ ! -L "$uninstaller_path" ] || return 1
    cmp -s "$uninstaller_path" <(
        printf '#!/bin/bash\nrm -f "%s"\nrm -f "%s"\necho "✅ ElfieNest uninstalled"\n' \
            "$wrapper_path" \
            "$uninstaller_path"
    )
}

legacy_wrapper_matches() {
    local wrapper_path="$1"
    local project_root="$2"

    [ -f "$wrapper_path" ] || return 1
    [ ! -L "$wrapper_path" ] || return 1
    cmp -s "$wrapper_path" <(
        printf '#!/bin/bash\ncd "%s"\n./elfie.sh "$@"\n' "$project_root"
    )
}

legacy_uninstaller_matches() {
    local uninstaller_path="$1"
    local wrapper_path="$2"

    [ -f "$uninstaller_path" ] || return 1
    [ ! -L "$uninstaller_path" ] || return 1
    cmp -s "$uninstaller_path" <(
        printf '#!/bin/bash\nrm -f "%s"\nrm -f "%s"\necho "✅ ElfieNest uninstalled"\n' \
            "$wrapper_path" \
            "$uninstaller_path"
    )
}

remove_legacy_installation_if_same_project() {
    local old_path="$1"
    local project_root="$2"
    local old_dir
    local old_uninstaller

    old_dir="${old_path%/*}"
    old_uninstaller="$old_dir/uninstall-elfie"

    if legacy_wrapper_matches "$old_path" "$project_root"; then
        if [ ! -w "$old_dir" ] || ! rm -f -- "$old_path"; then
            echo "⚠️ Cannot auto-clean old entry, please delete manually after verification: $old_path" >&2
            return 0
        fi
        echo "🧹 Cleaned old entry: $old_path"
        if legacy_uninstaller_matches "$old_uninstaller" "$old_path"; then
            if rm -f -- "$old_uninstaller"; then
                echo "🧹 Cleaned old uninstall entry: $old_uninstaller"
            else
                echo "⚠️ Cannot auto-clean old uninstall entry, please delete manually: $old_uninstaller" >&2
            fi
        fi
        return 0
    fi

    if [ ! -e "$old_path" ] \
        && [ ! -L "$old_path" ] \
        && legacy_uninstaller_matches "$old_uninstaller" "$old_path"; then
        if [ ! -w "$old_dir" ] || ! rm -f -- "$old_uninstaller"; then
            echo "⚠️ Cannot auto-clean old uninstall entry, please delete manually: $old_uninstaller" >&2
            return 0
        fi
        echo "🧹 Cleaned old uninstall entry: $old_uninstaller"
    fi
}

legacy_installation_matches() {
    local old_path="$1"
    local project_root="$2"
    local old_uninstaller="${old_path%/*}/uninstall-elfie"

    legacy_wrapper_matches "$old_path" "$project_root" && return 0
    [ ! -e "$old_path" ] || return 1
    [ ! -L "$old_path" ] || return 1
    legacy_uninstaller_matches "$old_uninstaller" "$old_path"
}

directory_is_within_home() {
    local canonical_dir
    local canonical_home
    local dir="$1"

    canonical_home="$(builtin cd -P -- "$HOME" 2>/dev/null && builtin pwd -P)" \
        || return 1
    canonical_dir="$(builtin cd -P -- "$dir" 2>/dev/null && builtin pwd -P)" \
        || return 1
    case "$canonical_dir" in
        "$canonical_home"|"$canonical_home"/*) return 0 ;;
        *) return 1 ;;
    esac
}

warn_legacy_system_install_if_same_project() {
    local old_path="$1"
    local project_root="$2"
    local old_uninstaller="${old_path%/*}/uninstall-elfie"

    legacy_installation_matches "$old_path" "$project_root" || return 0
    echo "⚠️ Detected old system entry: $old_path" >&2
    echo "   ElfieNest will not auto-modify /usr/local/bin. Please clean manually after verifying new command works." >&2
    if legacy_uninstaller_matches "$old_uninstaller" "$old_path"; then
        printf '   sudo rm -f -- %q %q\n' "$old_path" "$old_uninstaller" >&2
    else
        printf '   sudo rm -f -- %q\n' "$old_path" >&2
    fi
}

migrate_legacy_installations() {
    local project_root="$1"
    local install_dir="$2"
    local system_legacy_path="$3"
    local dir
    local -a candidates
    local -a path_dirs

    candidates=("$install_dir" "$HOME/bin" "$HOME/.local/bin")
    IFS=":" read -r -a path_dirs <<< "$PATH"
    candidates+=("${path_dirs[@]}")

    for dir in "${candidates[@]}"; do
        [ -n "$dir" ] || continue
        [ -d "$dir" ] || continue
        directory_is_within_home "$dir" || continue
        remove_legacy_installation_if_same_project "$dir/elfie" "$project_root"
    done

    warn_legacy_system_install_if_same_project \
        "$system_legacy_path" \
        "$project_root"
}

reject_shadowing_command() {
    local command_name="$1"
    local intended_path="$2"
    local resolved

    resolved="$(command -v "$command_name" 2>/dev/null || true)"
    if [ -n "$resolved" ] && [ "$resolved" != "$intended_path" ]; then
        echo "❌ Another $command_name command exists earlier in PATH: $resolved" >&2
        echo "   Please remove conflicting command first. ElfieNest did not modify any entries." >&2
        return 1
    fi
}
