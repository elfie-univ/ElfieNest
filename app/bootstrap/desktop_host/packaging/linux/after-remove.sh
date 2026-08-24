#!/bin/sh

set -eu

remove_owned_launcher() {
    launcher="$1"
    expected_target="$2"

    if [ -L "$launcher" ] && [ "$(readlink "$launcher")" = "$expected_target" ]; then
        rm -f "$launcher"
    fi
}

launcher="/usr/local/bin/elfienest"
cli="/opt/ElfieNest/resources/management-cli/ElfieNestCli"
remove_owned_launcher "$launcher" "$cli"

gui_launcher="/usr/bin/elfienest-gui"
gui="/opt/ElfieNest/elfienest-gui"
remove_owned_launcher "$gui_launcher" "$gui"
