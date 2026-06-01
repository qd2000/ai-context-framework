"""JSON and CLI contract helpers shared by ACF commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from ai_context_framework.constants import JSON_SCHEMA_VERSION


def json_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False))


def dry_run_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "dry_run", False))


def check_after_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "check_after", False))


def path_values(paths: Sequence[Path]) -> list[str]:
    return [str(path) for path in paths]


def set_result_payload(args: argparse.Namespace, payload: dict[str, object]) -> None:
    setattr(args, "_acf_result_payload", payload)


def get_result_payload(args: argparse.Namespace) -> dict[str, object]:
    payload = getattr(args, "_acf_result_payload", None)
    return payload if isinstance(payload, dict) else {}


def command_name_from_argv(argv: Sequence[str]) -> str | None:
    for token in argv:
        if token.startswith("-"):
            continue
        return token
    return None


def json_requested(argv: Sequence[str]) -> bool:
    return "--json" in argv


def print_json(payload: dict[str, object]) -> None:
    payload.setdefault("schema_version", JSON_SCHEMA_VERSION)
    payload.setdefault("error_code", None)
    payload.setdefault("next_actions", [])
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
