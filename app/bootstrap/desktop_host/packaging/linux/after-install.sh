#!/bin/sh

set -eu

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
ln -sfn "$gui" /usr/bin/elfienest-gui
ln -sfn "$cli" /usr/local/bin/elfienest
chmod 755 /usr/local/bin/elfienest
