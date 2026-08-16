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
