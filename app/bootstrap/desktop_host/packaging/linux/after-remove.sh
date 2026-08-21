#!/bin/sh

set -eu

launcher="/usr/local/bin/elfienest"
if [ -L "$launcher" ]; then
    target="$(readlink "$launcher")"
    case "$target" in
        */resources/management-cli/ElfieNestCli)
            rm -f "$launcher"
            ;;
    esac
fi

gui_launcher="/usr/bin/elfienest-gui"
if [ -L "$gui_launcher" ]; then
    target="$(readlink "$gui_launcher")"
    case "$target" in
        /opt/ElfieNest/elfienest-gui)
            rm -f "$gui_launcher"
            ;;
    esac
fi
