#!/usr/bin/env python3
"""Compatibility shim for the ACF CLI.

The package runtime lives under :mod:`ai_context_framework`. This top-level
module remains importable for legacy scripts and for ``python acf.py``.

The shim never writes runtime internals: relocating ``ROOT`` goes through
:func:`ai_context_framework.runtime.set_root`, and the runtime parts are
re-synchronized only when the shim's ``ROOT`` actually differs from the one the
runtime already holds.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ai_context_framework import runtime as _runtime
from ai_context_framework.version import VERSION


ROOT = _runtime.ROOT


def _bind_root() -> None:
    if _runtime.ROOT != ROOT:
        _runtime.set_root(ROOT)


def main(argv: Sequence[str] | None = None) -> int:
    _bind_root()
    return _runtime.main(argv)


def __getattr__(name: str) -> Any:
    _bind_root()
    try:
        return getattr(_runtime, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
