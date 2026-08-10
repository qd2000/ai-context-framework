#!/usr/bin/env sh
set -eu

package="${ACF_PACKAGE:-ai-context-framework}"
version="${ACF_VERSION:-}"
index="${ACF_INDEX:-}"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv was not found on PATH. Install uv first, then rerun this script." >&2
    exit 1
fi

spec="$package"
if [ -n "$version" ]; then
    spec="$package==$version"
fi

set -- tool install
if [ -n "$index" ]; then
    set -- "$@" --index "$index"
fi
set -- "$@" "$spec"
uv "$@"
uv tool update-shell

echo "Installed $spec. Restart the shell if acf is not yet available on PATH."
