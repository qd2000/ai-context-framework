"""Command handlers for task plan and current task workflows."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai_context_framework.json_contract import dry_run_enabled, emit_write_result, json_enabled, print_json, set_result_payload
from ai_context_framework.markdown import replace_section_text
from ai_context_framework.models import CheckResult, PlanReference
from ai_context_framework.paths import require_context_root


MaybeCheckAfter = Callable[[argparse.Namespace, Path, str | None], CheckResult | None]


@dataclass(frozen=True)
class PlanTaskDependencies:
    maybe_check_after: MaybeCheckAfter
    task_plan_path: Callable[..., Any]
    current_task_path: Callable[..., Any]
    plan_reference_payload: Callable[..., Any]
    normalize_plan_reference_path: Callable[..., Any]
    normalize_plan_reference_purpose: Callable[..., Any]
    ensure_plan_reference_target: Callable[..., Any]
    read_plan_references: Callable[..., Any]
    replace_or_add_plan_reference: Callable[..., Any]
    remove_plan_reference: Callable[..., Any]
    read_text: Callable[..., Any]
    write_plan_references_text: Callable[..., Any]
    sync_current_task_reference_text: Callable[..., Any]
    render_plan_reference: Callable[..., Any]
    read_task_rows: Callable[..., Any]
    read_task_stage_rows: Callable[..., Any]
    task_stage_payload: Callable[..., Any]
    validate_task_stage_parent: Callable[..., Any]
    validate_task_stage_workstream: Callable[..., Any]
    find_task_stage_row: Callable[..., Any]
    write_task_stage_rows: Callable[..., Any]
    find_task_row: Callable[..., Any]
    next_task_id: Callable[..., Any]
    write_task_rows: Callable[..., Any]
    set_plan_focus: Callable[..., Any]
    set_plan_status: Callable[..., Any]
    recommended_next_task: Callable[..., Any]
    extract_heading_value: Callable[..., Any]
    normalize_items: Callable[..., Any]
    render_task_plan: Callable[..., Any]
    extract_current_task_status: Callable[..., Any]
    blocked_dependency_ids: Callable[..., Any]
    build_task_start_fields: Callable[..., Any]
    render_empty_current_task: Callable[..., Any]


def plan_reference_list_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    plan_path = deps.task_plan_path(root)
    payload = {
        "command": "plan reference list",
        "ok": True,
        "context": str(root),
        **deps.plan_reference_payload(root, plan_path),
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        references = [PlanReference(item["path"], item["purpose"]) for item in payload["references"]]  # type: ignore[index]
        if references:
            print("\n".join(deps.render_plan_reference(reference) for reference in references))
        else:
            print("无。")
        for warning in payload.get("reference_warnings", []):
            print(f"WARN: {warning}", file=sys.stderr)
    return 0


def plan_reference_add_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    ref_path = deps.normalize_plan_reference_path(args.ref_path)
    reference = PlanReference(ref_path, deps.normalize_plan_reference_purpose(args.purpose))
    warnings = deps.ensure_plan_reference_target(root, ref_path, args.allow_missing)
    references, parse_warnings = deps.read_plan_references(plan_path)
    warnings.extend(parse_warnings)
    updated_references, _replaced = deps.replace_or_add_plan_reference(references, reference, force=args.force)

    changed_files: list[Path] = []
    original_plan = deps.read_text(plan_path)
    updated_plan = deps.write_plan_references_text(original_plan, updated_references)
    if updated_plan != original_plan:
        changed_files.append(plan_path)

    current_task = deps.current_task_path(root)
    updated_current_task: str | None = None
    if args.sync_current_task and current_task.exists():
        original_task = deps.read_text(current_task)
        updated_task, sync_warnings = deps.sync_current_task_reference_text(
            original_task,
            reference,
            operation="add",
            force=args.force,
        )
        warnings.extend(sync_warnings)
        if updated_task != original_task:
            updated_current_task = updated_task
            changed_files.append(current_task)

    if not dry_run:
        if updated_plan != original_plan:
            plan_path.write_text(updated_plan, encoding="utf-8")
        if updated_current_task is not None:
            current_task.write_text(updated_current_task, encoding="utf-8")

    check_result = deps.maybe_check_after(args, root, None)
    action = "would add" if dry_run else "added"
    return emit_write_result(
        args,
        "plan reference add",
        f"{action} plan reference {ref_path}",
        changed_files,
        check_result,
        extra_payload=deps.plan_reference_payload(root, plan_path) if not dry_run else {
            "references": [{"path": item.path, "purpose": item.purpose} for item in updated_references],
            "count": len(updated_references),
        },
        warnings=warnings,
    )


def plan_reference_remove_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    ref_path = deps.normalize_plan_reference_path(args.ref_path)
    references, parse_warnings = deps.read_plan_references(plan_path)
    warnings = list(parse_warnings)
    updated_references, removed = deps.remove_plan_reference(references, ref_path, missing_ok=args.missing_ok)

    changed_files: list[Path] = []
    original_plan = deps.read_text(plan_path)
    updated_plan = deps.write_plan_references_text(original_plan, updated_references)
    if updated_plan != original_plan:
        changed_files.append(plan_path)

    current_task = deps.current_task_path(root)
    updated_current_task: str | None = None
    if args.sync_current_task and removed is not None and current_task.exists():
        original_task = deps.read_text(current_task)
        updated_task, sync_warnings = deps.sync_current_task_reference_text(
            original_task,
            removed,
            operation="remove",
            force=False,
        )
        warnings.extend(sync_warnings)
        if updated_task != original_task:
            updated_current_task = updated_task
            changed_files.append(current_task)

    if not dry_run:
        if updated_plan != original_plan:
            plan_path.write_text(updated_plan, encoding="utf-8")
        if updated_current_task is not None:
            current_task.write_text(updated_current_task, encoding="utf-8")

    check_result = deps.maybe_check_after(args, root, None)
    action = "would remove" if dry_run else "removed"
    return emit_write_result(
        args,
        "plan reference remove",
        f"{action} plan reference {ref_path}",
        changed_files,
        check_result,
        extra_payload=deps.plan_reference_payload(root, plan_path) if not dry_run else {
            "references": [{"path": item.path, "purpose": item.purpose} for item in updated_references],
            "count": len(updated_references),
        },
        warnings=warnings,
    )


def plan_init_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    if plan_path.exists() and deps.extract_heading_value(plan_path, "## 大任务状态") == "Active" and not args.force:
        raise SystemExit(f"task plan is Active; use --force to replace it: {plan_path}")
    title = args.title.strip()
    if not title:
        raise SystemExit("plan title cannot be empty")
    goals = deps.normalize_items(args.goal, ("完成当前大任务。",))
    success = deps.normalize_items(args.success, ("大任务目标已完成并通过必要验证。",))
    if not dry_run:
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(deps.render_task_plan("Active", title, goals, success, "无。", []), encoding="utf-8")
    check_result = deps.maybe_check_after(args, root, None)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "plan init", f"{action} task plan {plan_path}", [plan_path], check_result)


def plan_add_task_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    rows = deps.read_task_rows(plan_path)
    task_id = args.id or deps.next_task_id(rows)
    if any(row.get("ID") == task_id for row in rows):
        raise SystemExit(f"task id already exists: {task_id}")
    title = args.title.strip()
    if not title:
        raise SystemExit("task title cannot be empty")
    rows.append(
        {
            "ID": task_id,
            "状态": "Pending",
            "子任务": title,
            "依赖": args.depends.strip() or "无。",
            "输出物": args.output.strip() or "无。",
            "证据": "无。",
            "下一步": args.next_action.strip() or "无。",
        }
    )
    if not dry_run:
        deps.write_task_rows(plan_path, rows)
    check_result = deps.maybe_check_after(args, root, None)
    action = "would add" if dry_run else "added"
    return emit_write_result(args, "plan add-task", f"{action} task {task_id} in {plan_path}", [plan_path], check_result)


def plan_set_task_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    rows = deps.read_task_rows(plan_path)
    row = deps.find_task_row(rows, args.id)
    if args.status:
        row["状态"] = args.status
    if args.title:
        row["子任务"] = args.title.strip()
    if args.depends is not None:
        row["依赖"] = args.depends.strip() or "无。"
    if args.output is not None:
        row["输出物"] = args.output.strip() or "无。"
    if args.evidence is not None:
        row["证据"] = args.evidence.strip() or "无。"
    if args.next_action is not None:
        row["下一步"] = args.next_action.strip() or "无。"
    if not dry_run:
        deps.write_task_rows(plan_path, rows)
    check_result = deps.maybe_check_after(args, root, None)
    action = "would update" if dry_run else "updated"
    return emit_write_result(args, "plan set-task", f"{action} task {args.id} in {plan_path}", [plan_path], check_result)


def plan_focus_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    rows = deps.read_task_rows(plan_path)
    deps.find_task_row(rows, args.id)
    if not dry_run:
        deps.set_plan_focus(plan_path, args.id)
    check_result = deps.maybe_check_after(args, root, None)
    action = "would focus" if dry_run else "focused"
    return emit_write_result(args, "plan focus", f"{action} task plan on {args.id}", [plan_path], check_result)


def plan_complete_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    rows = deps.read_task_rows(plan_path)
    unfinished = [
        row.get("ID", "")
        for row in rows
        if row.get("状态") not in {"Done", "Skipped", "Superseded"}
    ]
    if unfinished and not args.force:
        raise SystemExit(f"task plan has unfinished subtasks; use --force to complete anyway: {', '.join(unfinished)}")
    if not dry_run:
        deps.set_plan_status(plan_path, "Done")
        deps.set_plan_focus(plan_path, "无。")
    check_result = deps.maybe_check_after(args, root, None)
    action = "would complete" if dry_run else "completed"
    return emit_write_result(args, "plan complete", f"{action} task plan {plan_path}", [plan_path], check_result)


def plan_status_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    plan_path = deps.task_plan_path(root)
    rows = deps.read_task_rows(plan_path)
    payload: dict[str, object] = {
        "command": "plan status",
        "ok": True,
        "context": str(root),
        "plan_status": deps.extract_heading_value(plan_path, "## 大任务状态"),
        "title": deps.extract_heading_value(plan_path, "## 大任务名称"),
        "focus": deps.extract_heading_value(plan_path, "## 当前焦点"),
        "tasks": rows,
        "next_task": deps.recommended_next_task(rows),
        "error_code": None,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"plan: {payload['title']} ({payload['plan_status']})")
        print(f"focus: {payload['focus']}")
        for row in rows:
            print(f"{row.get('ID')}: {row.get('状态')} {row.get('子任务')}")
    return 0


def plan_stage_list_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    plan_path = deps.task_plan_path(root)
    payload: dict[str, object] = {
        "command": "plan stage list",
        "ok": True,
        "context": str(root),
        "plan": str(plan_path),
        "stages": [deps.task_stage_payload(row) for row in deps.read_task_stage_rows(plan_path)],
        "error_code": None,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        stages = payload["stages"]
        if not stages:
            print("no task stages")
        for row in stages:
            if isinstance(row, dict):
                print(f"{row.get('id')}\t{row.get('status')}\t{row.get('parent')}\t{row.get('title')}")
    return 0


def plan_stage_add_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    task_rows = deps.read_task_rows(plan_path)
    stage_rows = deps.read_task_stage_rows(plan_path)
    stage_id = args.id
    parent_task = args.parent
    deps.validate_task_stage_parent(task_rows, parent_task, stage_id)
    if deps.find_task_stage_row(stage_rows, stage_id) is not None:
        raise SystemExit(f"task_stage_duplicate_id: {stage_id}")
    title = (args.title or "").strip()
    if not title:
        raise SystemExit("task_stage_scope_invalid: stage title cannot be empty")
    workstream = (args.workstream or "无。").strip() or "无。"
    deps.validate_task_stage_workstream(root, workstream)
    row = {
        "ID": stage_id,
        "状态": "Pending",
        "父任务": parent_task,
        "名称": title,
        "归属 Workstream": workstream,
        "依赖": (args.depends or "无。").strip() or "无。",
        "输出物": (args.output or "待补充。").strip() or "待补充。",
        "证据": "无。",
        "下一步": (args.next_action or "待推进。").strip() or "待推进。",
    }
    if not dry_run:
        deps.write_task_stage_rows(plan_path, [*stage_rows, row])
    check_result = deps.maybe_check_after(args, root, None)
    action = "would add" if dry_run else "added"
    return emit_write_result(
        args,
        "plan stage add",
        f"{action} task stage {stage_id} in {plan_path}",
        [plan_path],
        check_result,
        extra_payload={"stage": deps.task_stage_payload(row)},
    )


def plan_stage_set_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    task_rows = deps.read_task_rows(plan_path)
    stage_rows = deps.read_task_stage_rows(plan_path)
    row = deps.find_task_stage_row(stage_rows, args.id)
    if row is None:
        raise SystemExit(f"task_stage_not_found: {args.id}")
    if args.parent is not None:
        parent_task = args.parent
        deps.validate_task_stage_parent(task_rows, parent_task, args.id)
        row["父任务"] = parent_task
    else:
        deps.validate_task_stage_parent(task_rows, row.get("父任务", ""), args.id)
    if args.status:
        row["状态"] = args.status
    if args.title is not None:
        title = args.title.strip()
        if not title:
            raise SystemExit("task_stage_scope_invalid: stage title cannot be empty")
        row["名称"] = title
    if args.workstream is not None:
        workstream = args.workstream.strip() or "无。"
        deps.validate_task_stage_workstream(root, workstream)
        row["归属 Workstream"] = workstream
    if args.depends is not None:
        row["依赖"] = args.depends.strip() or "无。"
    if args.output is not None:
        row["输出物"] = args.output.strip() or "无。"
    if args.evidence is not None:
        row["证据"] = args.evidence.strip() or "无。"
    if args.next_action is not None:
        row["下一步"] = args.next_action.strip() or "无。"
    if not dry_run:
        deps.write_task_stage_rows(plan_path, stage_rows)
    check_result = deps.maybe_check_after(args, root, None)
    action = "would update" if dry_run else "updated"
    return emit_write_result(
        args,
        "plan stage set",
        f"{action} task stage {args.id} in {plan_path}",
        [plan_path],
        check_result,
        extra_payload={"stage": deps.task_stage_payload(row)},
    )


def plan_stage_done_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    _task_rows = deps.read_task_rows(plan_path)
    stage_rows = deps.read_task_stage_rows(plan_path)
    row = deps.find_task_stage_row(stage_rows, args.id)
    if row is None:
        raise SystemExit(f"task_stage_not_found: {args.id}")
    evidence = (args.evidence or "").strip()
    if not evidence:
        raise SystemExit(f"task_stage_missing_evidence: {args.id}")
    row["状态"] = "Done"
    row["证据"] = evidence
    if args.next_action is not None:
        row["下一步"] = args.next_action.strip() or "无。"
    else:
        row["下一步"] = "无。"
    if not dry_run:
        deps.write_task_stage_rows(plan_path, stage_rows)
    check_result = deps.maybe_check_after(args, root, None)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(
        args,
        "plan stage done",
        f"{action} task stage {args.id} Done in {plan_path}",
        [plan_path],
        check_result,
        extra_payload={"stage_id": args.id, "status": "Done", "evidence": evidence},
    )


def task_start_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    task_path = deps.current_task_path(root)
    if task_path.exists() and deps.extract_current_task_status(task_path) == "Active" and not args.force:
        raise SystemExit(f"current task is Active; use --force to replace it: {task_path}")
    rows = deps.read_task_rows(plan_path)
    row = deps.find_task_row(rows, args.id)
    blocked = deps.blocked_dependency_ids(row, rows)
    if blocked and not args.force and not dry_run:
        raise SystemExit(f"task {args.id} has unfinished dependencies; use --force to start anyway: {', '.join(blocked)}")
    requested_workstreams: list[str] = []
    for value in args.workstream or []:
        workstream_id = value.strip().upper()
        if not workstream_id:
            continue
        if not re.fullmatch(r"WS\d{3}", workstream_id):
            raise SystemExit(f"workstream_invalid_id: {workstream_id}")
        if not (root / "active" / "workstreams" / f"{workstream_id}.md").exists():
            raise SystemExit(f"workstream_not_found: {workstream_id}")
        if workstream_id not in requested_workstreams:
            requested_workstreams.append(workstream_id)
    stage_workstreams: list[str] = []
    if not requested_workstreams:
        for stage in deps.read_task_stage_rows(plan_path):
            if stage.get("父任务") != args.id or stage.get("状态") in {"Done", "Skipped", "Superseded"}:
                continue
            for workstream_id in re.findall(r"WS\d{3}", stage.get("归属 Workstream", ""), re.IGNORECASE):
                if workstream_id not in stage_workstreams:
                    stage_workstreams.append(workstream_id)
    if len(stage_workstreams) > 1 and not requested_workstreams:
        raise SystemExit(
            "workstream_ambiguous: task has multiple active Workstream owners; "
            "pass --workstream explicitly"
        )
    workstreams = requested_workstreams or stage_workstreams
    fields = deps.build_task_start_fields(plan_path, row, rows, bool(blocked and args.force), workstreams)
    for candidate in rows:
        if candidate.get("状态") == "Active" and candidate.get("ID") != args.id:
            candidate["状态"] = "Pending"
    row["状态"] = "Active"
    if not dry_run:
        deps.write_task_rows(plan_path, rows)
        deps.set_plan_focus(plan_path, args.id)
        deps.set_plan_status(plan_path, "Active")
        task_path.write_text(str(fields["content"]), encoding="utf-8")
    check_result = deps.maybe_check_after(args, root, None)
    action = "would start" if dry_run else "started"
    return emit_write_result(
        args,
        "task start",
        f"{action} task {args.id}",
        [plan_path, task_path],
        check_result,
        extra_payload={
            "task_id": fields["task_id"],
            "generated_title": fields["generated_title"],
            "blocked_dependencies": fields["blocked_dependencies"],
            "workstreams": fields.get("workstreams", []),
        },
        warnings=fields["warnings"] if isinstance(fields["warnings"], list) else [],
    )


def task_done_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    task_path = deps.current_task_path(root)
    rows = deps.read_task_rows(plan_path)
    row = deps.find_task_row(rows, args.id)
    row["状态"] = "Done"
    row["证据"] = args.evidence.strip() or "已完成。"
    row["下一步"] = "无。"
    if not dry_run:
        deps.write_task_rows(plan_path, rows)
        if task_path.exists():
            task_path.write_text(replace_section_text(deps.read_text(task_path), "## 当前任务状态", "Done"), encoding="utf-8")
    check_result = deps.maybe_check_after(args, root, None)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(args, "task done", f"{action} task {args.id} done", [plan_path, task_path], check_result)


def task_block_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = deps.task_plan_path(root)
    rows = deps.read_task_rows(plan_path)
    row = deps.find_task_row(rows, args.id)
    row["状态"] = "Blocked"
    row["下一步"] = args.reason.strip() or "等待阻塞解除。"
    if not dry_run:
        deps.write_task_rows(plan_path, rows)
    check_result = deps.maybe_check_after(args, root, None)
    action = "would block" if dry_run else "blocked"
    return emit_write_result(args, "task block", f"{action} task {args.id}", [plan_path], check_result)


def task_clear_command(args: argparse.Namespace, *, deps: PlanTaskDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    task_path = deps.current_task_path(root)
    if not dry_run:
        task_path.write_text(deps.render_empty_current_task(), encoding="utf-8")
    check_result = deps.maybe_check_after(args, root, None)
    action = "would clear" if dry_run else "cleared"
    return emit_write_result(args, "task clear", f"{action} current task {task_path}", [task_path], check_result)
