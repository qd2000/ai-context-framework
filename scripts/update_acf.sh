#!/usr/bin/env sh
set -eu

package="${ACF_PACKAGE:-ai-context-framework}"
index="${ACF_INDEX:-}"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv was not found on PATH. Install uv first, then rerun this script." >&2
    exit 1
fi

set -- tool upgrade
if [ -n "$index" ]; then
    set -- "$@" --index "$index"
fi
if [ "${ACF_REINSTALL:-0}" = "1" ]; then
    set -- "$@" --reinstall
fi
set -- "$@" "$package"
uv "$@"
uv tool update-shell

echo "Upgraded $package. Restart the shell if acf is not yet available on PATH."
