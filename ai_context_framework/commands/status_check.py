"""Command handlers for context status and validation checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from ai_context_framework.constants import EXIT_CHECK_FAILED, EXIT_INPUT_ERROR
from ai_context_framework.context_budget import context_budget_warnings
from ai_context_framework.front_matter import parse_front_matter
from ai_context_framework.git_support import (
    current_branch,
    discover_git_project,
    list_registries,
    path_key,
)
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
ATTENTION_STATES = ("Now", "Next", "Waiting", "Retained")


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
                "attention": str(metadata.get("attention") or "Unspecified"),
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
        for value in _section_lines(lines, heading):
            _add_workstream_ids(value, ordered, seen)
    for line in _section_lines(lines, "## Now"):
        if "workstream" in line.casefold():
            _add_workstream_ids(line, ordered, seen)
    return ordered


GLOBAL_CONTEXT_FILE_ORDER = (
    "AGENTS.md",
    "rules/Always_Active.md",
    "active/Context.md",
    "active/Task_Plan.md",
    "active/Current_Task.md",
    "active/Workstreams.md",
)
SELECTION_SOURCE_PRIORITY = (
    "verified_worktree",
    "current_task",
    "explicit_cli",
)


def _global_context_files(root: Path) -> list[str]:
    """Return the bounded default context chain without opening Workstream details."""
    return [relative for relative in GLOBAL_CONTEXT_FILE_ORDER if (root / relative).is_file()]


def _global_entry(root: Path, reason: str) -> dict[str, object]:
    return {
        "kind": "global_context",
        "command": f"acf status {root} --json",
        "reason": reason,
        "priority": 1,
        "files": _global_context_files(root),
    }


def _dashboard_entry(root: Path, reason: str) -> dict[str, object]:
    return {
        "kind": "workstream_dashboard",
        "command": f"acf workstream dashboard {root} --json",
        "reason": reason,
        "priority": 1,
    }


def _verified_worktree_binding(
    root: Path,
    invocation_path: Path | None,
) -> tuple[str | None, list[str]]:
    """Return a Workstream ID only for a registry-verified linked worktree.

    Main checkouts and unregistered worktrees stay global-only. A registry that
    claims the current checkout but fails path/branch/common-dir validation is
    reported as an invalid explicit environment instead of being guessed.
    """
    if invocation_path is None:
        return None, []
    try:
        project = discover_git_project(invocation_path)
    except (SystemExit, OSError):
        return None, []
    if path_key(project.context_root) != path_key(root):
        return None, []
    if path_key(project.repo_root) == path_key(project.config.primary_checkout):
        return None, []
    try:
        registries = list_registries(project.common_dir)
    except (SystemExit, OSError) as exc:
        return None, [f"verified_worktree: registry_scan_failed: {exc}"]
    matches = [
        row
        for row in registries
        if isinstance(row.get("path"), str)
        and path_key(str(row["path"])) == path_key(project.repo_root)
    ]
    if not matches:
        return None, []
    if len(matches) > 1:
        ids = sorted(
            {
                str(row.get("workstream") or row.get("key") or "unknown").upper()
                for row in matches
            }
        )
        return None, ["verified_worktree: multiple_matching_registries: " + ", ".join(ids)]
    row = matches[0]
    raw_workstream = row.get("workstream")
    if not isinstance(raw_workstream, str) or not raw_workstream.strip():
        key = str(row.get("key") or "")
        if key.upper().startswith("WS"):
            return None, ["verified_worktree: registry_missing_workstream"]
        return None, []
    workstream_id = raw_workstream.strip().upper()
    errors: list[str] = []
    if str(row.get("state") or "active") != "active":
        errors.append(f"verified_worktree: registry_not_active: {workstream_id}")
    raw_common = row.get("git_common_dir")
    if not isinstance(raw_common, str) or path_key(raw_common) != path_key(project.common_dir):
        errors.append(f"verified_worktree: git_common_dir_mismatch: {workstream_id}")
    branch = current_branch(project.repo_root)
    if not branch:
        errors.append(f"verified_worktree: detached_head: {workstream_id}")
    elif str(row.get("branch") or "") != branch:
        errors.append(f"verified_worktree: branch_mismatch: {workstream_id}")
    return workstream_id, errors


def workstream_entry_payload(
    root: Path,
    *,
    explicit_workstream: str | None = None,
    invocation_path: Path | None = None,
) -> dict[str, object]:
    summaries = workstream_summaries(root)
    active_class = [item for item in summaries if item["status"] in ACTIVE_WORKSTREAM_STATUSES]
    active = [item for item in summaries if item["status"] == "Active"]
    blocked = [item for item in summaries if item["status"] == "Blocked"]
    ready = [item for item in summaries if item["status"] == "ReadyToMerge"]
    merging = [item for item in summaries if item["status"] == "Merging"]
    terminal = [item for item in summaries if item["status"] in {"Done", "Cancelled"}]
    current_task_workstreams = current_task_workstream_ids(root)
    by_id = {str(item["id"]).upper(): item for item in summaries}
    unresolved = [item for item in current_task_workstreams if item.upper() not in by_id]
    inactive_links = [
        item
        for item in current_task_workstreams
        if item.upper() in by_id
        and by_id[item.upper()]["status"] not in ACTIVE_WORKSTREAM_STATUSES
    ]
    attention_summary = {
        state: sum(1 for item in summaries if item.get("attention") == state)
        for state in ATTENTION_STATES
    }
    attention_now = [item for item in active_class if item.get("attention") == "Now"]
    attention_next = [item for item in active_class if item.get("attention") == "Next"]

    def make_entry(item: dict[str, object], reason: str, priority: int) -> dict[str, object]:
        kind = "workstream_context" if item["status"] == "Active" else "workstream_next_actions"
        command = (
            f"acf workstream context {item['id']} {root} --json"
            if kind == "workstream_context"
            else f"acf workstream next-actions {item['id']} {root} --json"
        )
        return {
            "kind": kind,
            "command": command,
            "reason": reason,
            "priority": priority,
            "workstream_id": item["id"],
            "status": item["status"],
            "attention": item.get("attention", "Unspecified"),
            "detail": item["detail"],
            "disclosure": "pointer_only",
        }

    bindings: list[dict[str, str]] = []
    if explicit_workstream:
        bindings.append(
            {"source": "explicit_cli", "workstream_id": explicit_workstream.upper()}
        )
    for workstream_id in current_task_workstreams:
        bindings.append(
            {"source": "current_task", "workstream_id": workstream_id.upper()}
        )
    worktree_workstream, worktree_errors = _verified_worktree_binding(root, invocation_path)
    if worktree_workstream:
        bindings.append(
            {"source": "verified_worktree", "workstream_id": worktree_workstream}
        )

    selection_errors = list(worktree_errors)
    selection_candidates: list[str] = []
    for binding in bindings:
        workstream_id = binding["workstream_id"]
        if workstream_id not in selection_candidates:
            selection_candidates.append(workstream_id)
        item = by_id.get(workstream_id)
        if item is None:
            selection_errors.append(
                f"{binding['source']}: workstream_not_found: {workstream_id}"
            )
        elif item["status"] not in ACTIVE_WORKSTREAM_STATUSES:
            selection_errors.append(
                f"{binding['source']}: workstream_not_active: "
                f"{workstream_id} ({item['status']})"
            )

    workstreams_initialized = (root / "active" / "Workstreams.md").exists()
    state = "NotInitialized" if not workstreams_initialized else (
        "GlobalOnly" if active_class else "Inactive"
    )
    context_mode = "global"
    disclosure_level = "global"
    selected_workstream: str | None = None
    selection_source: str | None = None
    selection_sources: list[str] = []
    selection_ok = True
    selection_error_code: str | None = None
    recommended = _global_entry(root, "no Workstream was explicitly selected")
    candidates: list[dict[str, object]] = []

    distinct_candidates = set(selection_candidates)
    if len(distinct_candidates) > 1:
        state = "SelectionConflict"
        selection_ok = False
        selection_error_code = "selection_conflict"
        recommended = _global_entry(
            root,
            "conflicting Workstream selections; remain in global context",
        )
        candidates = [
            make_entry(by_id[workstream_id], "conflicting explicit selection", index + 1)
            for index, workstream_id in enumerate(selection_candidates)
            if workstream_id in by_id
            and by_id[workstream_id]["status"] in ACTIVE_WORKSTREAM_STATUSES
        ]
    elif selection_errors:
        state = "SelectionInvalid"
        selection_ok = False
        selection_error_code = "selection_invalid"
        recommended = _global_entry(
            root,
            "invalid Workstream selection; remain in global context",
        )
        candidates = [
            make_entry(by_id[workstream_id], "valid portion of invalid selection", index + 1)
            for index, workstream_id in enumerate(selection_candidates)
            if workstream_id in by_id
            and by_id[workstream_id]["status"] in ACTIVE_WORKSTREAM_STATUSES
        ]
    elif len(selection_candidates) == 1:
        selected_workstream = selection_candidates[0]
        item = by_id[selected_workstream]
        selection_sources = [
            source
            for source in SELECTION_SOURCE_PRIORITY
            if any(binding["source"] == source for binding in bindings)
        ]
        selection_source = selection_sources[0]
        if "verified_worktree" in selection_sources:
            state = "WorktreeSelected"
        elif "current_task" in selection_sources:
            state = "CurrentTaskSelected"
        else:
            state = "Selected"
        context_mode = "workstream"
        disclosure_level = "workstream_pointer"
        recommended = make_entry(
            item,
            f"Workstream explicitly selected by {selection_source}",
            1,
        )
        candidates = [recommended]

    management_entry = (
        _dashboard_entry(root, "review Workstream portfolio without selecting one")
        if active_class
        else None
    )
    selected_context_files = (
        [str(by_id[selected_workstream]["detail"])] if selected_workstream else []
    )
    return {
        "workstream_state": state,
        "context_mode": context_mode,
        "disclosure_level": disclosure_level,
        "global_context_files": _global_context_files(root),
        "selected_workstream": selected_workstream,
        "selected_context_files": selected_context_files,
        "selection_source": selection_source,
        "selection_sources": selection_sources,
        "selection_bindings": bindings,
        "selection_candidates": selection_candidates,
        "selection_errors": selection_errors,
        "selection_ok": selection_ok,
        "selection_error_code": selection_error_code,
        "current_task_workstreams": current_task_workstreams,
        "unresolved_current_task_workstreams": unresolved,
        "inactive_current_task_workstreams": inactive_links,
        "active_workstreams": active,
        "ready_to_merge": ready,
        "blocked_workstreams": blocked,
        "merging_workstreams": merging,
        "terminal_retained_workstreams": terminal,
        "active_class_count": len(active_class),
        "deferred_workstream_count": len(active_class) - (1 if selected_workstream else 0),
        "attention_summary": attention_summary,
        "attention_candidates": [item["id"] for item in (*attention_now, *attention_next)],
        "management_entry": management_entry,
        "recommended_entry": recommended,
        "candidate_entries": candidates,
    }


def check_command(args: argparse.Namespace, *, check_context: CheckContext) -> int:
    root = resolve_context_root(args.path)
    profile = args.profile or infer_context_profile(root)
    result = check_context(root, profile, args.strict)
    invocation_path = Path(args.path).resolve() if args.path is not None else Path.cwd()
    routing = workstream_entry_payload(root, invocation_path=invocation_path)
    context_warnings = context_budget_warnings(root, routing)
    payload: dict[str, object] = {
        "command": "check",
        "context": str(root),
        "profile": profile,
        "strict": args.strict,
        "check": check_payload(result),
        "ok": result.ok,
        "error_code": check_error_code(result),
        "next_actions": check_next_actions(result, args.strict),
        "context_warnings": context_warnings,
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
    for warning in context_warnings:
        print("WARN: " + str(warning.get("message", warning)), file=sys.stderr)
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
    routing = workstream_entry_payload(
        location.context_root,
        explicit_workstream=getattr(args, "workstream", None),
        invocation_path=location.project_root,
    )
    selection_ok = bool(routing.get("selection_ok", True))
    overall_ok = result.ok and selection_ok
    error_code = check_error_code(result) or routing.get("selection_error_code")
    next_actions = check_next_actions(result, args.strict)
    if result.ok and not selection_ok:
        next_actions = [
            "Remain in global context and resolve the explicit Workstream selection."
        ]
    context_warnings = context_budget_warnings(location.context_root, routing)
    payload: dict[str, object] = {
        "command": "status",
        "project_root": str(location.project_root),
        "context": str(location.context_root),
        "profile": profile,
        "current_task": task_status or "Unknown",
        "strict": args.strict,
        "check": check_payload(result),
        "ok": overall_ok,
        "error_code": error_code,
        "next_actions": next_actions,
        "changed_files": [],
        "context_warnings": context_warnings,
        **routing,
    }
    if not result.ok:
        payload["message"] = f"check failed: {len(result.errors)} error(s), {len(result.warnings)} warning(s)"
    elif not selection_ok:
        payload["message"] = str(error_code or "Workstream selection failed")
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
        if not result.ok:
            return EXIT_CHECK_FAILED
        return 0 if selection_ok else EXIT_INPUT_ERROR

    print(f"project root: {location.project_root}")
    print(f"context: {location.context_root}")
    print(f"profile: {profile}")
    print(f"current task: {task_status or 'Unknown'}")
    print(f"check: {'passed' if result.ok else 'failed'}")
    print(f"workstream state: {routing.get('workstream_state')}")
    print(f"context mode: {routing.get('context_mode')}")
    if routing.get("selected_workstream"):
        print(f"selected workstream: {routing['selected_workstream']}")
    if result.errors:
        print(f"errors: {len(result.errors)}")
        for error in result.errors:
            print(f"ERROR: {error}")
    if result.warnings:
        print(f"warnings: {len(result.warnings)}")
        for warning in result.warnings:
            print(f"WARN: {warning}")
    for selection_error in routing.get("selection_errors", []):
        print(f"ERROR: {selection_error}")
    for warning in context_warnings:
        print("WARN: " + str(warning.get("message", warning)))

    if not result.ok:
        return EXIT_CHECK_FAILED
    return 0 if selection_ok else EXIT_INPUT_ERROR
