"""Shared argparse helpers for CLI parser registration.

These helpers used to live in ``ai_context_framework/runtime.py``. Command modules
cannot import runtime (runtime imports them, and the module-globals injection that
made that work is exactly what WS016 is removing), so the helpers move to a leaf
module that both runtime and the command modules can import directly.

Keeping them injectable as well means a ``register_*_parser`` function can either
import ``add_write_arguments`` itself or receive it as a parameter, without either
side depending on the other.
"""

from __future__ import annotations

import argparse


def add_json_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="print machine-readable JSON")


def add_write_arguments(parser: argparse.ArgumentParser) -> None:
    add_json_argument(parser)
    parser.add_argument("--dry-run", action="store_true", help="validate and report changed files without writing")
    parser.add_argument("--check-after", action="store_true", help="run context check after writing")
    parser.add_argument("--strict", action="store_true", help="use strict mode for --check-after")
