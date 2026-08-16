#!/bin/sh

set -eu

gui="/usr/bin/elfienest-gui"
if [ ! -e "$gui" ]; then
    echo "ElfieNest GUI launcher is missing after installation: $gui" >&2
    exit 1
fi

app_root="$(dirname "$(readlink -f "$gui")")"
cli="$app_root/resources/management-cli/ElfieNestCli"
if [ ! -x "$cli" ]; then
    echo "ElfieNest management CLI is missing after installation: $cli" >&2
    exit 1
fi

install -d -m 0755 /usr/local/bin
ln -sfn "$cli" /usr/local/bin/elfienest
chmod 755 /usr/local/bin/elfienest
