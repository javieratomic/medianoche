#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'No se encuentra python3. Este instalador requiere SteamOS con Python 3.' >&2
    exit 1
fi
status=0
python3 "$HERE/install_steam.py" --bundle-dir "$HERE" "$@" || status=$?
if [ -t 0 ]; then
    printf '\nPulsa Intro para cerrar... '
    read -r answer || :
fi
exit "$status"
