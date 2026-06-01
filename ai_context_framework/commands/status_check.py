"""Command handlers for context status and validation checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from ai_context_framework.constants import EXIT_CHECK_FAILED
from ai_context_framework.json_contract import (
    check_error_code,
    check_next_actions,
    check_payload,
    json_enabled,
    print_json,
    set_result_payload,
)
from ai_context_framework.models import CheckResult
from ai_context_framework.paths import infer_context_profile, resolve_context_root, resolve_status_location


CheckContext = Callable[[Path, str, bool], CheckResult]
ExtractCurrentTaskStatus = Callable[[Path], str | None]


def check_command(args: argparse.Namespace, *, check_context: CheckContext) -> int:
    root = resolve_context_root(args.path)
    profile = args.profile or infer_context_profile(root)
    result = check_context(root, profile, args.strict)
    payload: dict[str, object] = {
        "command": "check",
        "context": str(root),
        "profile": profile,
        "strict": args.strict,
        "check": check_payload(result),
        "ok": result.ok,
        "error_code": check_error_code(result),
        "next_actions": check_next_actions(result, args.strict),
    }
    if not result.ok:
        payload["message"] = f"check failed: {len(result.errors)} error(s), {len(result.warnings)} warning(s)"
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
        return 0 if result.ok else 1

    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    for warning in result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    if result.ok:
        print(f"check passed: {root}")
        return 0
    print(f"check failed: {len(result.errors)} error(s), {len(result.warnings)} warning(s)", file=sys.stderr)
    return EXIT_CHECK_FAILED


def status_command(
    args: argparse.Namespace,
    *,
    check_context: CheckContext,
    extract_current_task_status: ExtractCurrentTaskStatus,
) -> int:
    location = resolve_status_location(args.path)
    profile = args.profile or location.profile
    task_path = location.context_root / "active" / "Current_Task.md"
    task_status = extract_current_task_status(task_path) if task_path.exists() else None
    result = check_context(location.context_root, profile, args.strict)
    payload: dict[str, object] = {
        "command": "status",
        "project_root": str(location.project_root),
        "context": str(location.context_root),
        "profile": profile,
        "current_task": task_status or "Unknown",
        "strict": args.strict,
        "check": check_payload(result),
        "ok": result.ok,
        "error_code": check_error_code(result),
        "next_actions": check_next_actions(result, args.strict),
    }
    if not result.ok:
        payload["message"] = f"check failed: {len(result.errors)} error(s), {len(result.warnings)} warning(s)"
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
        return 0 if result.ok else 1

    print(f"project root: {location.project_root}")
    print(f"context: {location.context_root}")
    print(f"profile: {profile}")
    print(f"current task: {task_status or 'Unknown'}")
    print(f"check: {'passed' if result.ok else 'failed'}")
    if result.errors:
        print(f"errors: {len(result.errors)}")
        for error in result.errors:
            print(f"ERROR: {error}")
    if result.warnings:
        print(f"warnings: {len(result.warnings)}")
        for warning in result.warnings:
            print(f"WARN: {warning}")

    return 0 if result.ok else 1
