#!/usr/bin/env python3
"""Compatibility shim for the ACF CLI.

The package runtime lives under :mod:`ai_context_framework`. This top-level
module remains importable for legacy scripts and for ``python acf.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ai_context_framework import runtime as _runtime
from ai_context_framework.version import VERSION


ROOT = _runtime.ROOT


def main(argv: Sequence[str] | None = None) -> int:
    _runtime.ROOT = ROOT
    _runtime._sync_runtime_part_globals()
    return _runtime.main(argv)


def __getattr__(name: str) -> Any:
    _runtime.ROOT = ROOT
    _runtime._sync_runtime_part_globals()
    try:
        return getattr(_runtime, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
