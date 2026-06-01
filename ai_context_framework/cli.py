"""Package CLI entrypoint skeleton for the WS002 migration.

This module is intentionally importable before it becomes the installed
console-script target. The active CLI implementation remains in acf.py until
the parser and command handlers have been migrated.
"""

from __future__ import annotations

from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Placeholder entrypoint until WS002 migrates parser/main into package."""
    _ = argv
    raise RuntimeError(
        "ai_context_framework.cli.main is not wired yet; use acf.py until WS002.6."
    )
