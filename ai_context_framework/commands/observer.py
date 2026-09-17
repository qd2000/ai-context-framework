"""Retired Project Observer compatibility tombstone.

The Project Observer product surface (runtime snapshot/history, target
registry, presentation lifecycle, and Dashboard rendering) was retired in
``v0.0.3.92``.  This module keeps only a side-effect-free tombstone so older
callers receive a stable ``observer_retired`` error instead of an argparse
failure.

It deliberately does not import the former Observer implementation, read or
write Observer runtime state, inspect Git or continuation state, create
directories, or delete user data.  User-level Observer data on existing
machines is intentionally left untouched by upgrades.
"""

from __future__ import annotations

import argparse
import sys

from ai_context_framework.constants import EXIT_RUNTIME_ERROR, JSON_SCHEMA_VERSION
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload

OBSERVER_RETIRED_ERROR_CODE = "observer_retired"

OBSERVER_RETIRED_NEXT_ACTIONS = [
    "Use `acf status --json` for current context state.",
    "Use `acf workstream dashboard --json` for Workstream portfolio state.",
    "Use `acf continuation doctor --json` for continuation health.",
]


def _retired_payload() -> dict[str, object]:
    """Build the stable retired-command payload."""

    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "ok": False,
        "command": "observer",
        "error_code": OBSERVER_RETIRED_ERROR_CODE,
        "message": (
            "The `acf observer` product surface was retired in v0.0.3.92; "
            "no Observer runtime state is read or written."
        ),
        "changed_files": [],
        "next_actions": list(OBSERVER_RETIRED_NEXT_ACTIONS),
    }


def _json_requested(args: argparse.Namespace) -> bool:
    """Honor ``--json`` even when it trails a tolerated legacy argument tail."""

    if json_enabled(args):
        return True
    legacy_tail = getattr(args, "observer_args", None) or []
    return "--json" in legacy_tail


def observer_retired_command(args: argparse.Namespace) -> int:
    """Emit the retired notice without touching any runtime state."""

    payload = _retired_payload()
    set_result_payload(args, payload)
    if _json_requested(args):
        print_json(payload)
    else:
        print(
            "ERROR: the `acf observer` product surface was retired in v0.0.3.92; "
            "no Observer runtime state is read or written.",
            file=sys.stderr,
        )
        for action in OBSERVER_RETIRED_NEXT_ACTIONS:
            print(f"  - {action}", file=sys.stderr)
    return EXIT_RUNTIME_ERROR


def register_observer_parser(subparsers, add_json_argument) -> None:
    """Register the retired Observer tombstone without importing legacy code."""

    observer_parser = subparsers.add_parser(
        "observer",
        help="retired compatibility tombstone for the former Project Observer surface",
    )
    # Tolerate any former subcommand/option tail so old callers still receive the
    # stable `observer_retired` notice instead of an argparse usage error.
    observer_parser.add_argument("observer_args", nargs=argparse.REMAINDER)
    add_json_argument(observer_parser)
    observer_parser.set_defaults(func=observer_retired_command)
