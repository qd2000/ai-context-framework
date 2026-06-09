"""Command handlers for context status and validation checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from ai_context_framework.constants import EXIT_CHECK_FAILED
from ai_context_framework.front_matter import parse_front_matter
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
ACTIVE_WORKSTREAM_STATUSES = {"Active", "Blocked", "ReadyToMerge", "Merging"}


def workstream_summaries(root: Path) -> list[dict[str, object]]:
    details_dir = root / "active" / "workstreams"
    if not details_dir.exists():
        return []
    summaries: list[dict[str, object]] = []
    for path in sorted(details_dir.glob("WS*.md")):
        metadata, _body, diagnostics = parse_front_matter(path.read_text(encoding="utf-8"))
        if diagnostics:
            continue
        workstream_id = str(metadata.get("id") or path.stem)
        summaries.append(
            {
                "id": workstream_id,
                "status": str(metadata.get("status") or "Unknown"),
                "title": str(metadata.get("title") or workstream_id),
                "owner": str(metadata.get("owner") or "未分配"),
                "detail": path.relative_to(root).as_posix(),
                "current_stage": metadata.get("current_stage") if isinstance(metadata.get("current_stage"), str) else None,
                "type": str(metadata.get("type") or "Task"),
            }
        )
    return summaries


def workstream_entry_payload(root: Path) -> dict[str, object]:
    summaries = workstream_summaries(root)
    active_class = [item for item in summaries if item["status"] in ACTIVE_WORKSTREAM_STATUSES]
    active = [item for item in summaries if item["status"] == "Active"]
    blocked = [item for item in summaries if item["status"] == "Blocked"]
    ready = [item for item in summaries if item["status"] == "ReadyToMerge"]
    merging = [item for item in summaries if item["status"] == "Merging"]
    terminal = [item for item in summaries if item["status"] in {"Done", "Cancelled"}]
    state = "NotInitialized" if not (root / "active" / "Workstreams.md").exists() else ("ActiveClassPresent" if active_class else "Inactive")
    recommended: dict[str, object] = {"kind": "none", "priority": 1, "reason": "no active Workstream"}
    candidates: list[dict[str, object]] = []
    if len(active_class) == 1:
        item = active_class[0]
        kind = "workstream_context" if item["status"] == "Active" else "workstream_next_actions"
        command = f"acf workstream context {item['id']} {root} --json" if kind == "workstream_context" else f"acf workstream next-actions {item['id']} {root} --json"
        recommended = {
            "kind": kind,
            "command": command,
            "reason": f"single {item['status']} Workstream",
            "priority": 1,
            "workstream_id": item["id"],
            "status": item["status"],
            "detail": item["detail"],
        }
        candidates = [recommended]
    elif len(active_class) > 1:
        state = "Ambiguous"
        recommended = {
            "kind": "workstream_dashboard",
            "command": f"acf workstream dashboard {root} --json",
            "reason": "multiple active-class Workstreams",
            "priority": 1,
        }
        candidates = [
            {
                "kind": "workstream_context" if item["status"] == "Active" else "workstream_next_actions",
                "command": f"acf workstream context {item['id']} {root} --json",
                "reason": f"{item['status']} Workstream",
                "priority": index + 1,
                "workstream_id": item["id"],
                "status": item["status"],
                "detail": item["detail"],
            }
            for index, item in enumerate(active_class)
        ]
    return {
        "workstream_state": state,
        "active_workstreams": active,
        "ready_to_merge": ready,
        "blocked_workstreams": blocked,
        "merging_workstreams": merging,
        "terminal_retained_workstreams": terminal,
        "recommended_entry": recommended,
        "candidate_entries": candidates,
    }


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
        "changed_files": [],
        **workstream_entry_payload(location.context_root),
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
