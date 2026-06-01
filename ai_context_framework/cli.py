"""Package CLI entrypoint."""

from __future__ import annotations

from collections.abc import Sequence

from ai_context_framework import runtime


def main(argv: Sequence[str] | None = None) -> int:
    return runtime.main(argv)
