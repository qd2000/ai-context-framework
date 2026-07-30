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
from ai_context_framework.validators.checks import WORKSTREAM_ID_TOKEN_RE


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


def _section_lines(lines: list[str], heading: str) -> list[str]:
    for index, line in enumerate(lines):
        if line.strip() != heading:
            continue
        section: list[str] = []
        for candidate in lines[index + 1:]:
            if candidate.strip().startswith("## "):
                break
            section.append(candidate)
        return section
    return []


def _heading_value(lines: list[str], heading: str) -> str | None:
    section = _section_lines(lines, heading)
    values = [line.strip() for line in section if line.strip() and not line.strip().startswith("---")]
    return values[0] if values else None


def _add_workstream_ids(value: str, ordered: list[str], seen: set[str]) -> None:
    for workstream_id in WORKSTREAM_ID_TOKEN_RE.findall(value):
        if workstream_id not in seen:
            seen.add(workstream_id)
            ordered.append(workstream_id)


def current_task_workstream_ids(root: Path) -> list[str]:
    task_path = root / "active" / "Current_Task.md"
    if not task_path.exists():
        return []
    lines = task_path.read_text(encoding="utf-8").splitlines()
    if _heading_value(lines, "## \u5f53\u524d\u4efb\u52a1\u72b6\u6001") != "Active":
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for heading in ("## \u5f53\u524d\u6267\u884c\u7ebf", "## Workstream", "## \u6240\u5c5e Workstream", "## \u5f53\u524d Workstream"):
        value = _heading_value(lines, heading)
        if value:
            _add_workstream_ids(value, ordered, seen)
    for line in _section_lines(lines, "## Now"):
        if "workstream" in line.casefold():
            _add_workstream_ids(line, ordered, seen)
    return ordered


def workstream_entry_payload(root: Path) -> dict[str, object]:
    summaries = workstream_summaries(root)
    active_class = [item for item in summaries if item["status"] in ACTIVE_WORKSTREAM_STATUSES]
    active = [item for item in summaries if item["status"] == "Active"]
    blocked = [item for item in summaries if item["status"] == "Blocked"]
    ready = [item for item in summaries if item["status"] == "ReadyToMerge"]
    merging = [item for item in summaries if item["status"] == "Merging"]
    terminal = [item for item in summaries if item["status"] in {"Done", "Cancelled"}]
    current_task_workstreams = current_task_workstream_ids(root)
    current_task_ids = set(current_task_workstreams)
    focused = [item for item in active_class if str(item["id"]) in current_task_ids]
    state = "NotInitialized" if not (root / "active" / "Workstreams.md").exists() else ("ActiveClassPresent" if active_class else "Inactive")
    recommended: dict[str, object] = {"kind": "none", "priority": 1, "reason": "no active Workstream"}
    candidates: list[dict[str, object]] = []

    def make_entry(item: dict[str, object], reason: str, priority: int) -> dict[str, object]:
        kind = "workstream_context" if item["status"] == "Active" else "workstream_next_actions"
        command = f"acf workstream context {item['id']} {root} --json" if kind == "workstream_context" else f"acf workstream next-actions {item['id']} {root} --json"
        return {
            "kind": kind,
            "command": command,
            "reason": reason,
            "priority": priority,
            "workstream_id": item["id"],
            "status": item["status"],
            "detail": item["detail"],
        }

    if len(focused) == 1:
        state = "Focused"
        recommended = make_entry(focused[0], f"Current_Task links to {focused[0]['status']} Workstream", 1)
        candidates = [recommended]
    elif len(focused) > 1:
        state = "Ambiguous"
        recommended = {
            "kind": "workstream_dashboard",
            "command": f"acf workstream dashboard {root} --json",
            "reason": "Current_Task links multiple active-class Workstreams",
            "priority": 1,
        }
        candidates = [
            make_entry(item, f"Current_Task links to {item['status']} Workstream", index + 1)
            for index, item in enumerate(focused)
        ]
    elif current_task_workstreams:
        state = "CurrentTaskLinkUnresolved"
        recommended = {
            "kind": "workstream_dashboard",
            "command": f"acf workstream dashboard {root} --json",
            "reason": "Current_Task Workstream link is not active-class",
            "priority": 1,
        }
    elif len(active_class) == 1:
        item = active_class[0]
        recommended = make_entry(item, f"single {item['status']} Workstream", 1)
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
            make_entry(item, f"{item['status']} Workstream", index + 1)
            for index, item in enumerate(active_class)
        ]
    return {
        "workstream_state": state,
        "current_task_workstreams": current_task_workstreams,
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
