#!/bin/sh

set -eu

install_owned_launcher() {
    target="$1"
    launcher="$2"

    if [ -L "$launcher" ]; then
        current_target="$(readlink "$launcher")"
        if [ "$current_target" = "$target" ]; then
            return
        fi
        echo "Refusing to replace launcher not owned by ElfieNest: $launcher -> $current_target" >&2
        exit 1
    fi
    if [ -e "$launcher" ]; then
        echo "Refusing to replace launcher not owned by ElfieNest: $launcher" >&2
        exit 1
    fi

    ln -s "$target" "$launcher"
}

app_root="/opt/ElfieNest"
gui="$app_root/elfienest-gui"
if [ ! -x "$gui" ]; then
    echo "ElfieNest GUI executable is missing after installation: $gui" >&2
    exit 1
fi

cli="$app_root/resources/management-cli/ElfieNestCli"
if [ ! -x "$cli" ]; then
    echo "ElfieNest management CLI is missing after installation: $cli" >&2
    exit 1
fi

install -d -m 0755 /usr/bin /usr/local/bin
install_owned_launcher "$gui" /usr/bin/elfienest-gui
install_owned_launcher "$cli" /usr/local/bin/elfienest
