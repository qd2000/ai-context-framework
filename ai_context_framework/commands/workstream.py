"""Command handlers for Workstream workflows.

This module is a transitional Workstream extraction. Command handlers and
local Workstream workflow helpers live here; shared legacy helpers and constants
are injected from the compatibility shim until the remaining domains are split.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from ai_context_framework.models import WorkstreamArchiveAssessment, WorkstreamDetail, WorkstreamEntry


@dataclass(frozen=True)
class WorkstreamDependencies:
    symbols: dict[str, Any]


_MODULE_OWNED_NAMES: set[str] | None = None


def _bind(deps: WorkstreamDependencies) -> None:
    module_globals = globals()
    owned_names = _MODULE_OWNED_NAMES
    for name, value in deps.symbols.items():
        if name.startswith("__"):
            continue
        if owned_names is not None and name in owned_names:
            continue
        if owned_names is None and name in module_globals:
            continue
        module_globals[name] = value


def workstream_init_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    index_path = workstream_index_path(root)
    details_dir = workstream_details_dir(root)
    archive_dir = workstream_archive_dir(root)
    changed = [path for path in (index_path, details_dir, archive_dir) if not path.exists()]

    if not dry_run:
        details_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)
        if not index_path.exists():
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(render_workstream_index(), encoding="utf-8")

    check_result = maybe_check_after(args, root)
    action = "would initialize" if dry_run else "initialized"
    return emit_write_result(
        args,
        "workstream init",
        f"{action} Workstream layer",
        changed,
        check_result,
        extra_payload={
            "initialized": True,
            "index": str(index_path),
            "details_dir": str(details_dir),
            "archive_dir": str(archive_dir),
        },
    )


def workstream_status_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    initialized = workstream_initialized(root)
    entries = parse_workstream_index(root) if initialized else []
    payload: dict[str, object] = {
        "command": "workstream status",
        "context": str(root),
        "initialized": initialized,
        "index": str(workstream_index_path(root)),
        "details_dir": str(workstream_details_dir(root)),
        "archive_dir": str(workstream_archive_dir(root)),
        "state": workstream_index_state(root, entries) if initialized else "NotInitialized",
        "counts": workstream_counts(entries),
        "ok": True,
        "next_actions": [] if initialized else error_next_actions("workstream_not_initialized"),
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"workstream initialized: {initialized}")
        print(f"state: {payload['state']}")
        if not initialized:
            print("next action: acf workstream init")
    return 0


def workstream_list_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    entries = parse_workstream_index(root)
    payload: dict[str, object] = {
        "command": "workstream list",
        "context": str(root),
        "initialized": True,
        "state": workstream_index_state(root, entries),
        "counts": workstream_counts(entries),
        "workstreams": [workstream_entry_payload(entry) for entry in entries],
        "ok": True,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        for entry in entries:
            print(f"{entry.workstream_id}\t{entry.status}\t{entry.title}")
        if not entries:
            print("no workstreams")
    return 0


def parse_archive_candidates_today(value: str | None) -> date:
    if value is None:
        return date.today()
    normalized = value.strip()
    if not DATE_RE.match(normalized):
        raise SystemExit("workstream_archive_candidates_invalid_today: --today must use YYYY-MM-DD")
    return date.fromisoformat(normalized)


def parse_workstream_archive_date(value: str | None, option_name: str = "--date") -> date:
    if value is None:
        return date.today()
    normalized = value.strip()
    if not DATE_RE.match(normalized):
        raise SystemExit(f"workstream_archive_candidates_invalid_today: {option_name} must use YYYY-MM-DD")
    return date.fromisoformat(normalized)


def current_execution_workstream_ids(root: Path) -> set[str]:
    task_file = root / "active" / "Current_Task.md"
    if not task_file.exists():
        return set()
    current_line = extract_heading_value(task_file, "## 当前执行线")
    if not meaningful_ref_value(current_line):
        return set()
    return set(WORKSTREAM_ID_TOKEN_RE.findall(current_line or ""))


def active_task_stage_workstream_refs(root: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    plan_path = task_plan_path(root)
    if not plan_path.exists():
        return {}, {}
    try:
        rows = read_task_stage_rows(plan_path)
    except SystemExit as exc:
        raise SystemExit(f"workstream_archive_candidates_plan_unreadable: {exc}") from exc

    active_refs: dict[str, list[str]] = {}
    focus_refs: dict[str, list[str]] = {}
    focus = extract_heading_value(plan_path, "## 当前焦点") or ""
    for row in rows:
        stage_id = row.get("ID", "")
        owner_value = row.get("归属 Workstream", "")
        workstream_ids = WORKSTREAM_ID_TOKEN_RE.findall(owner_value)
        if not workstream_ids:
            continue
        if row.get("状态") not in {"Done", "Skipped", "Superseded"}:
            for workstream_id in workstream_ids:
                active_refs.setdefault(workstream_id, []).append(stage_id)
        if focus == stage_id:
            for workstream_id in workstream_ids:
                focus_refs.setdefault(workstream_id, []).append(stage_id)
    return active_refs, focus_refs


def workstream_archive_candidate_reason(detail: WorkstreamDetail, today: date) -> str:
    keep_until = detail.metadata.get("keep_active_until")
    if isinstance(keep_until, str) and DATE_RE.match(keep_until) and date.fromisoformat(keep_until) < today:
        return f"keep_active_until {keep_until} is expired."
    return "terminal Workstream is no longer blocked by keep-active metadata or current-plan references."


def workstream_archive_blockers(
    detail: WorkstreamDetail,
    today: date,
    current_execution_refs: set[str],
    active_stage_refs: dict[str, list[str]],
    focus_stage_refs: dict[str, list[str]],
) -> list[str]:
    blockers: list[str] = []
    workstream_id = detail.workstream_id
    status = detail.metadata.get("status")
    if workstream_id in current_execution_refs:
        blockers.append("referenced_by_current_task_execution_line")
    if workstream_id in active_stage_refs:
        blockers.append("referenced_by_current_task_stage")
    if workstream_id in focus_stage_refs:
        blockers.append("referenced_by_current_plan_focus")

    if status == "Done":
        merge_targets = detail.metadata.get("merge_targets")
        has_merge_targets = isinstance(merge_targets, list) and any(str(target).strip() for target in merge_targets)
        if workstream_section_missing(detail.body, "## 证据"):
            blockers.append("missing_evidence")
        if required_field_missing(detail.metadata.get("merge_resolution")):
            blockers.append("missing_merge_resolution")
        if has_merge_targets and not merge_request_has_required_fields(detail.body):
            blockers.append("missing_merge_request")
    elif status == "Cancelled" and workstream_section_missing(detail.body, "## 取消原因"):
        blockers.append("missing_cancellation_reason")

    keep_until = detail.metadata.get("keep_active_until")
    if isinstance(keep_until, str) and DATE_RE.match(keep_until):
        if date.fromisoformat(keep_until) >= today:
            blockers.append("keep_active_until_not_expired")
    elif not required_field_missing(keep_until):
        blockers.append("invalid_keep_active_until")

    return list(dict.fromkeys(blockers))


def workstream_archive_candidate_payload(root: Path, detail: WorkstreamDetail, today: date, blockers: Sequence[str]) -> dict[str, object]:
    keep_until = detail.metadata.get("keep_active_until")
    return {
        "id": detail.workstream_id,
        "status": detail.metadata.get("status", "Unknown"),
        "title": detail.metadata.get("title", "Unknown"),
        "detail": detail.path.as_posix(),
        "archive_target": (root / WORKSTREAM_ARCHIVE_DIR_REL / f"{detail.workstream_id}.md").as_posix(),
        "keep_active_until": keep_until if isinstance(keep_until, str) else None,
        "reason": workstream_archive_candidate_reason(detail, today),
        "blocked_by": list(blockers),
    }


def collect_workstream_archive_assessments(root: Path, today: date) -> list[WorkstreamArchiveAssessment]:
    entries = parse_workstream_index(root)
    current_execution_refs = current_execution_workstream_ids(root)
    active_stage_refs, focus_stage_refs = active_task_stage_workstream_refs(root)
    assessments: list[WorkstreamArchiveAssessment] = []
    for entry in entries:
        detail = read_workstream_detail(root, entry.workstream_id)
        status = detail.metadata.get("status")
        if status not in {"Done", "Cancelled"}:
            continue
        blockers = workstream_archive_blockers(detail, today, current_execution_refs, active_stage_refs, focus_stage_refs)
        assessments.append(
            WorkstreamArchiveAssessment(
                detail=detail,
                blockers=tuple(blockers),
                reason=workstream_archive_candidate_reason(detail, today),
            )
        )
    return assessments


def workstream_archive_assessment_payload(root: Path, assessment: WorkstreamArchiveAssessment, today: date) -> dict[str, object]:
    return workstream_archive_candidate_payload(root, assessment.detail, today, assessment.blockers)


def count_by_key(items: Sequence[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key)
        if isinstance(value, list):
            values = [str(candidate) for candidate in value if candidate]
        else:
            values = [str(value)] if value else []
        for candidate in values:
            counts[candidate] = counts.get(candidate, 0) + 1
    return counts


def workstream_archive_candidates_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    today = parse_archive_candidates_today(args.today)
    candidates: list[dict[str, object]] = []
    blocked: list[dict[str, object]] = []

    assessments = collect_workstream_archive_assessments(root, today)
    for assessment in assessments:
        payload = workstream_archive_assessment_payload(root, assessment, today)
        if assessment.blockers:
            blocked.append(payload)
        else:
            candidates.append(payload)

    next_actions: list[str] = []
    if candidates:
        next_actions.append("Review candidates and create an explicit archive draft or future archive command; this command does not move files.")
    if blocked:
        next_actions.append("Resolve blockers before archiving terminal Workstreams that remain active.")
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "workstream archive-candidates",
        "ok": True,
        "context": str(root),
        "today": today.isoformat(),
        "changed_files": [],
        "candidates": candidates,
        "blocked": blocked,
        "summary": {
            "terminal_total": len(assessments),
            "candidate_total": len(candidates),
            "blocked_total": len(blocked),
            "by_blocker": count_by_key(blocked, "blocked_by"),
        },
        "error_code": None,
        "next_actions": next_actions,
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        if not candidates:
            print("no archive candidates")
        for candidate in candidates:
            print(f"{candidate['id']}\t{candidate['status']}\t{candidate['reason']}")
        if blocked:
            print(f"blocked terminal workstreams: {len(blocked)}")
    return 0


def workstream_archive_draft_path(root: Path, draft_date: date, name: str | None) -> Path:
    suffix = f"-{slugify_file_stem(name)}" if name else ""
    return root / "worklog" / "archive-drafts" / f"{draft_date.isoformat()}{suffix}.md"


def workstream_archive_blocker_action(blocker: str) -> str:
    actions = {
        "keep_active_until_not_expired": "等待 keep_active_until 到期，或人工确认后更新 keep-active metadata。",
        "referenced_by_current_task_execution_line": "先完成、清空或切换 active/Current_Task.md 的当前执行线。",
        "referenced_by_current_plan_focus": "先移动 active/Task_Plan.md 当前焦点或完成相关阶段。",
        "referenced_by_current_task_stage": "先完成、跳过或重排引用该 Workstream 的当前 Task Stage。",
        "missing_merge_resolution": "先补充 Done Workstream 的 merge_resolution。",
        "missing_evidence": "先补充 Done Workstream 的证据。",
        "missing_merge_request": "先补充合并请求，或移除不再适用的 merge_targets。",
        "missing_cancellation_reason": "先补充 Cancelled Workstream 的取消原因。",
        "invalid_keep_active_until": "修正 keep_active_until 为 YYYY-MM-DD 或移除该字段。",
    }
    return actions.get(blocker, "人工复核该 blocker 后再决定是否归档。")


def render_workstream_archive_draft(
    root: Path,
    draft_path: Path,
    draft_date: date,
    candidates: Sequence[dict[str, object]],
    blocked: Sequence[dict[str, object]],
) -> str:
    rel_draft = draft_path.relative_to(root).as_posix()
    context_arg = relative_display_path(root, Path.cwd())
    lines = [
        f"# Workstream 归档草案：{draft_date.isoformat()}",
        "",
        "本文件是待人工或 AI 审阅的归档清单，不是归档结果。真正归档必须显式运行建议命令。",
        "",
        "## 摘要",
        "",
        f"- candidates: {len(candidates)}",
        f"- blocked: {len(blocked)}",
        "- source: acf workstream archive-candidates",
        "",
        "## 可归档候选",
        "",
    ]
    if not candidates:
        lines.append("- 无。")
    for item in candidates:
        workstream_id = str(item["id"])
        reason = f"reviewed in {rel_draft}"
        lines.extend(
            [
                f"### {workstream_id}",
                "",
                f"- status: {item.get('status')}",
                f"- detail: {relative_display_path(Path(str(item.get('detail'))), root)}",
                f"- archive_target: {relative_display_path(Path(str(item.get('archive_target'))), root)}",
                f"- reason: {item.get('reason')}",
                "- suggested_command:",
                "",
                "```bash",
                f"uv run acf workstream archive {workstream_id} {context_arg} --reason \"{reason}\" --json",
                "```",
                "",
            ]
        )

    lines.extend(["## 暂不归档", ""])
    if not blocked:
        lines.append("- 无。")
    for item in blocked:
        blockers = [str(blocker) for blocker in item.get("blocked_by", [])] if isinstance(item.get("blocked_by"), list) else []
        lines.extend(
            [
                f"### {item.get('id')}",
                "",
                f"- status: {item.get('status')}",
                f"- detail: {relative_display_path(Path(str(item.get('detail'))), root)}",
                f"- blocked_by: {', '.join(blockers) if blockers else '无。'}",
                f"- reason: {item.get('reason')}",
                "- suggested_action:",
            ]
        )
        for blocker in blockers:
            lines.append(f"  - {blocker}: {workstream_archive_blocker_action(blocker)}")
        lines.append("")

    lines.extend(
        [
            "## 审阅记录",
            "",
            "- approved:",
            "- rejected:",
            "- notes:",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def workstream_archive_draft_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    draft_date = parse_workstream_archive_date(args.date)
    dry_run = dry_run_enabled(args)
    draft_path = workstream_archive_draft_path(root, draft_date, args.name)
    assessments = collect_workstream_archive_assessments(root, draft_date)
    candidates: list[dict[str, object]] = []
    blocked: list[dict[str, object]] = []
    for assessment in assessments:
        payload = workstream_archive_assessment_payload(root, assessment, draft_date)
        if assessment.blockers:
            blocked.append(payload)
        else:
            candidates.append(payload)
    planned_draft = render_workstream_archive_draft(root, draft_path, draft_date, candidates, blocked)
    if draft_path.exists() and not args.force and not dry_run:
        raise SystemExit(f"workstream_archive_draft_exists: {draft_path.relative_to(root).as_posix()}")
    if not dry_run:
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(planned_draft, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would create" if dry_run else "created"
    return emit_write_result(
        args,
        "workstream archive-draft",
        f"{action} Workstream archive draft {draft_path.relative_to(root).as_posix()}",
        [draft_path],
        check_result,
        extra_payload={
            "draft_path": draft_path.relative_to(root).as_posix(),
            "candidate_count": len(candidates),
            "blocked_count": len(blocked),
            "planned_draft": planned_draft if dry_run else None,
        },
    )


def active_workstream_index_matches(entries: Sequence[WorkstreamEntry], workstream_id: str) -> list[WorkstreamEntry]:
    return [entry for entry in entries if entry.workstream_id == workstream_id]


def workstream_archive_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    archive_date = parse_workstream_archive_date(args.date)
    dry_run = dry_run_enabled(args)
    reason = required_workstream_reason(args, "archive")
    entries = parse_workstream_index(root)
    matches = active_workstream_index_matches(entries, args.id)
    if len(matches) > 1:
        raise SystemExit(f"workstream_archive_duplicate_index: {args.id} appears multiple times in {WORKSTREAM_INDEX_REL}")
    warnings: list[str] = []
    if not matches:
        warnings.append(f"{WORKSTREAM_INDEX_REL} has no row for {args.id}; continuing with detail file")
    detail = read_workstream_detail(root, args.id)
    status = str(detail.metadata.get("status", ""))
    if status not in {"Done", "Cancelled"}:
        raise SystemExit(f"workstream_archive_blocked: {args.id} status is {status or 'Unknown'}")

    blockers = workstream_archive_blockers(
        detail,
        archive_date,
        current_execution_workstream_ids(root),
        *active_task_stage_workstream_refs(root),
    )
    if blockers:
        raise SystemExit(f"workstream_archive_blocked: {args.id} blocked_by={','.join(blockers)}")

    source_rel = detail.path.relative_to(root).as_posix()
    archive_rel = f"{WORKSTREAM_ARCHIVE_DIR_REL}/{args.id}.md"
    archive_path = root / archive_rel
    if archive_path.exists():
        raise SystemExit(f"workstream_archive_target_exists: {archive_rel}")
    source_text = read_text(detail.path)
    if has_workstream_archive_marker(source_text):
        raise SystemExit(f"workstream_archive_target_exists: {args.id} already contains archive marker")

    kept_entries = [entry for entry in entries if entry.workstream_id != args.id]
    changed: list[Path] = [archive_path, detail.path, archive_index_path(root)]
    if matches:
        changed.append(workstream_index_path(root))
    active_gitkeep = workstream_details_dir(root) / ".gitkeep"
    remaining_details = [path for path in workstream_details_dir(root).glob("*.md") if path.resolve() != detail.path.resolve()]
    if not remaining_details and not active_gitkeep.exists():
        changed.append(active_gitkeep)

    if not dry_run:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        updated_archive_text = source_text.rstrip() + "\n\n---\n\n" + workstream_archive_marker(archive_date, source_rel, archive_rel, reason)
        archive_path.write_text(updated_archive_text, encoding="utf-8")
        detail.path.unlink()
        if matches:
            write_workstream_index(root, kept_entries)
        if not remaining_details:
            active_gitkeep.parent.mkdir(parents=True, exist_ok=True)
            active_gitkeep.touch(exist_ok=True)
        index_path = archive_index_path(root)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        if not index_path.exists():
            index_path.write_text(render_archive_index(), encoding="utf-8")
        append_archive_index_entry(index_path, archive_date.isoformat(), "workstream", args.id, source_rel, archive_rel, status, reason)

    check_result = maybe_check_after(args, root)
    action = "would archive" if dry_run else "archived"
    return emit_write_result(
        args,
        "workstream archive",
        f"{action} Workstream {args.id}",
        changed,
        check_result,
        extra_payload={
            "archived_id": args.id,
            "source_path": source_rel,
            "archive_path": archive_rel,
            "status": status,
            "blocked_by": [],
        },
        warnings=warnings,
    )


def workstream_sync_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    index_path = workstream_index_path(root)
    current_text = read_text(index_path)
    entries = parse_workstream_index(root)
    planned_entries = synced_workstream_entries(root, entries)
    planned_text = render_workstream_index_text(root, planned_entries)
    changed = [index_path] if planned_text != current_text else []
    if changed and not dry_run:
        index_path.write_text(planned_text, encoding="utf-8")

    check_result = maybe_check_after(args, root)
    action = "would sync" if dry_run else "synced"
    extra_payload: dict[str, object] = {
        "synced": bool(changed),
        "workstreams": [workstream_entry_payload(entry) for entry in planned_entries],
    }
    if dry_run and changed:
        extra_payload["preview"] = {"path": WORKSTREAM_INDEX_REL, "content": planned_text}
    return emit_write_result(
        args,
        "workstream sync",
        f"{action} Workstream index",
        changed,
        check_result,
        extra_payload=extra_payload,
    )


def workstream_show_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    detail = read_workstream_detail(root, args.id)
    merge_request = safe_section_body_from_text(detail.body, "## 合并请求")
    evidence = safe_section_body_from_text(detail.body, "## 证据")
    payload: dict[str, object] = {
        "command": "workstream show",
        "context": str(root),
        "id": args.id,
        "detail": str(detail.path),
        "metadata": detail.metadata,
        "normalized_read_scope": normalize_scope_values(detail.metadata.get("read_scope")),
        "normalized_write_scope": normalize_typed_scope_values(detail.metadata.get("write_scope")),
        "merge_request": merge_request,
        "evidence": evidence,
        "diagnostics": [diagnostic_payload(diagnostic) for diagnostic in detail.diagnostics],
        "ok": True,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"id: {args.id}")
        print(f"detail: {detail.path}")
        print(f"status: {detail.metadata.get('status', 'Unknown')}")
        print(f"title: {detail.metadata.get('title', 'Unknown')}")
    return 0


def workstream_add_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    entries = parse_workstream_index(root)
    if workstream_id_exists(root, args.id, entries):
        raise SystemExit(f"workstream_duplicate_id: {args.id}")

    dry_run = dry_run_enabled(args)
    detail_path = workstream_details_dir(root) / f"{args.id}.md"
    read_scope = [normalized_read_claim(value) for value in (args.read_scope or ["active/Context.md", "active/Task_Plan.md"])]
    write_scope = [normalized_write_claim(value, args.id)[2] for value in (args.write_scope or [workstream_write_scope(args.id)])]
    depends_on = args.depends_on or []
    output = args.output.strip() if args.output else "待补充。"
    goal = args.goal.strip() if args.goal else "待补充。"
    workstream_kind = args.type
    entry = WorkstreamEntry(
        workstream_id=args.id,
        status="Open",
        title=args.title.strip(),
        owner=args.owner.strip(),
        write_scope=", ".join(write_scope),
        depends_on=",".join(depends_on) if depends_on else "无。",
        output=output,
        detail=workstream_detail_rel(args.id),
    )
    changed = [detail_path, workstream_index_path(root)]
    if not dry_run:
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail_path.write_text(
            render_workstream_detail(
                args.id,
                args.title.strip(),
                args.owner.strip(),
                depends_on,
                read_scope,
                write_scope,
                output,
                goal,
                workstream_kind,
            ),
            encoding="utf-8",
        )
        write_workstream_index(root, [*entries, entry])

    check_result = maybe_check_after(args, root)
    action = "would add" if dry_run else "added"
    return emit_write_result(
        args,
        "workstream add",
        f"{action} Workstream {args.id}",
        changed,
        check_result,
        extra_payload={"id": args.id, "type": workstream_kind, "status": "Open", "detail": str(detail_path)},
    )


def workstream_set_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    goal = args.goal.strip() if args.goal is not None else None
    if args.status is None and goal is None:
        raise SystemExit("workstream_update_required: set requires --status or --goal")
    if goal == "":
        raise SystemExit("workstream_update_required: --goal cannot be empty")
    if args.status in {"ReadyToMerge", "Done"}:
        raise SystemExit(f"workstream_invalid_transition: use workstream {'ready' if args.status == 'ReadyToMerge' else 'done'} for {args.status}")
    if args.status is not None:
        section_updates = {"## 目标": goal} if goal is not None else None
        changed = update_workstream_status(root, args.id, args.status, section_updates, dry_run)
        status = args.status
    else:
        detail = read_workstream_detail(root, args.id)
        updated_text = format_front_matter(
            detail.metadata,
            replace_or_append_section(detail.body, "## 目标", goal or ""),
            WORKSTREAM_METADATA_FIELDS,
        )
        changed = [detail.path]
        if not dry_run:
            detail.path.write_text(updated_text, encoding="utf-8")
        status = workstream_detail_metadata_value(detail, "status", "Unknown")
    check_result = maybe_check_after(args, root)
    action = "would set" if dry_run else "set"
    message_target = f"to {status}" if args.status is not None else "goal"
    return emit_write_result(
        args,
        "workstream set",
        f"{action} Workstream {args.id} {message_target}",
        changed,
        check_result,
        extra_payload={"id": args.id, "status": status, "goal": goal},
    )


def required_workstream_reason(args: argparse.Namespace, command: str) -> str:
    reason = (args.reason or "").strip()
    if not reason:
        raise SystemExit(f"workstream_reason_required: {command} requires --reason")
    return reason


def workstream_block_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    reason = required_workstream_reason(args, "block")
    changed = update_workstream_status(root, args.id, "Blocked", {"## 阻塞原因": reason}, dry_run)
    check_result = maybe_check_after(args, root)
    action = "would block" if dry_run else "blocked"
    return emit_write_result(
        args,
        "workstream block",
        f"{action} Workstream {args.id}",
        changed,
        check_result,
        extra_payload={"id": args.id, "status": "Blocked", "reason": reason},
    )


def workstream_cancel_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    reason = required_workstream_reason(args, "cancel")
    changed = update_workstream_status(root, args.id, "Cancelled", {"## 取消原因": reason}, dry_run)
    check_result = maybe_check_after(args, root)
    action = "would cancel" if dry_run else "cancelled"
    return emit_write_result(
        args,
        "workstream cancel",
        f"{action} Workstream {args.id}",
        changed,
        check_result,
        extra_payload={"id": args.id, "status": "Cancelled", "reason": reason},
    )


def read_workstream_merge_summary(args: argparse.Namespace) -> str:
    summary = (args.summary or "").strip()
    input_path = getattr(args, "input", None)
    if summary and input_path is not None:
        raise SystemExit("use either --summary or --input, not both")
    if input_path is not None:
        resolved = input_path.resolve()
        if not resolved.is_file():
            raise SystemExit(f"merge-request input file does not exist: {resolved}")
        summary = resolved.read_text(encoding="utf-8").strip()
    if not summary:
        raise SystemExit("workstream_missing_merge_request: merge-request requires --summary or --input")
    return summary


def render_workstream_merge_request(
    targets: Sequence[str],
    summary: str,
    verification: str,
    questions: Sequence[str],
    conflicts: Sequence[str],
    strategy: str,
) -> str:
    target_lines = "\n".join(f"- {target}" for target in targets)
    question_lines = "\n".join(f"- {question}" for question in questions) if questions else "无。"
    conflict_lines = "\n".join(f"- {conflict}" for conflict in conflicts) if conflicts else "无。"
    return f"""### 需要合并到哪里

{target_lines}

### 候选变更摘要

{summary}

### 需要人工判断的问题

{question_lines}

### 已知冲突

{conflict_lines}

### 验证结果

{verification}

### 建议合并方式

{strategy or "人工审阅后合并到对应权威上下文。"}"""


def merge_request_has_required_fields(body: str) -> bool:
    merge_request = safe_section_body_from_text(body, "## 合并请求")
    if not merge_request or merge_request.strip() == "无。":
        return False
    targets = [
        line.strip()[2:].strip()
        for line in subsection_body(merge_request, "### 需要合并到哪里").splitlines()
        if line.strip().startswith("- ")
    ]
    summary = subsection_body(merge_request, "### 候选变更摘要").strip()
    return bool([target for target in targets if target]) and bool(summary and summary != "无。")


def workstream_merge_request_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    detail = read_workstream_detail(root, args.id)
    targets = [target.strip() for target in (args.target or []) if target.strip()]
    if not targets:
        raise SystemExit("workstream_missing_merge_request: merge-request requires at least one --target")
    verification = (args.verification or "").strip()
    if not verification:
        raise SystemExit("workstream_missing_merge_request: merge-request requires --verification")
    summary = read_workstream_merge_summary(args)
    section = render_workstream_merge_request(
        targets,
        summary,
        verification,
        args.question or [],
        args.conflict or [],
        (args.strategy or "").strip(),
    )
    metadata = dict(detail.metadata)
    merge_targets, _merge_targets_changed = append_unique_values(metadata.get("merge_targets"), targets)
    metadata["merge_targets"] = merge_targets
    updated_text = format_front_matter(
        metadata,
        replace_or_append_section(detail.body, "## 合并请求", section),
        WORKSTREAM_METADATA_FIELDS,
    )
    changed = [detail.path]
    if not dry_run:
        detail.path.write_text(updated_text, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would update" if dry_run else "updated"
    return emit_write_result(
        args,
        "workstream merge-request",
        f"{action} merge request for Workstream {args.id}",
        changed,
        check_result,
        extra_payload={"id": args.id, "targets": targets, "summary": summary},
    )


def workstream_ready_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    detail = read_workstream_detail(root, args.id)
    current_status = workstream_detail_metadata_value(detail, "status", "")
    if not getattr(args, "human_approved", False):
        raise SystemExit(f"workstream_human_approval_required: {args.id} ready requires --human-approved")
    if "ReadyToMerge" not in WORKSTREAM_STATE_TRANSITIONS.get(current_status, set()):
        raise SystemExit(f"workstream_invalid_transition: {args.id} {current_status} -> ReadyToMerge")
    if not merge_request_has_required_fields(detail.body):
        raise SystemExit(f"workstream_missing_merge_request: {args.id}")
    unfinished_stage = next(
        (
            row.get("ID", "")
            for row in read_workstream_stage_rows(detail.body)
            if row.get("状态") not in {"Done", "Skipped", "Cancelled"}
        ),
        "",
    )
    if unfinished_stage:
        raise SystemExit(f"workstream_stage_dependency_blocked: {args.id} has unfinished stage {unfinished_stage}")
    changed = update_workstream_status(root, args.id, "ReadyToMerge", None, dry_run)
    check_result = maybe_check_after(args, root)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(
        args,
        "workstream ready",
        f"{action} Workstream {args.id} ReadyToMerge",
        changed,
        check_result,
        extra_payload={"id": args.id, "status": "ReadyToMerge"},
    )


def required_workstream_evidence(args: argparse.Namespace) -> str:
    evidence = (args.evidence or "").strip()
    if not evidence:
        raise SystemExit("workstream_missing_evidence: done requires --evidence")
    return evidence


def required_workstream_merge_resolution(args: argparse.Namespace) -> str:
    resolution = (args.merge_resolution or "").strip()
    if not resolution:
        raise SystemExit("workstream_missing_merge_resolution: done requires --merge-resolution")
    return resolution


def workstream_done_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    detail = read_workstream_detail(root, args.id)
    current_status = workstream_detail_metadata_value(detail, "status", "")
    if "Done" not in WORKSTREAM_STATE_TRANSITIONS.get(current_status, set()):
        raise SystemExit(f"workstream_invalid_transition: {args.id} {current_status} -> Done")
    evidence = required_workstream_evidence(args)
    merge_resolution = required_workstream_merge_resolution(args)
    section_updates = {"## 证据": evidence}
    completion = (args.summary or "").strip()
    if completion:
        section_updates["## 完成记录"] = completion
    changed = update_workstream_status(
        root,
        args.id,
        "Done",
        section_updates,
        dry_run,
        {"merge_resolution": merge_resolution},
    )
    check_result = maybe_check_after(args, root)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(
        args,
        "workstream done",
        f"{action} Workstream {args.id} Done",
        changed,
        check_result,
        extra_payload={"id": args.id, "status": "Done", "evidence": evidence, "merge_resolution": merge_resolution},
    )


def canonical_workstream_note_heading(section: str) -> str:
    normalized = section.strip().removeprefix("##").strip()
    heading = WORKSTREAM_NOTE_SECTIONS.get(normalized)
    if heading is None:
        allowed = ", ".join(sorted(WORKSTREAM_NOTE_SECTIONS))
        raise SystemExit(f"workstream_section_not_allowed: {section}; allowed: {allowed}")
    return heading


def workstream_note_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    detail = read_workstream_detail(root, args.id)
    heading = canonical_workstream_note_heading(args.section)
    note_text = read_edit_input(args).strip()
    if not note_text:
        raise SystemExit("workstream_section_not_allowed: note text cannot be empty")
    updated_text = format_front_matter(
        detail.metadata,
        append_or_create_section(detail.body, heading, note_text),
        WORKSTREAM_METADATA_FIELDS,
    )
    changed = [detail.path]
    if not dry_run:
        detail.path.write_text(updated_text, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would append" if dry_run else "appended"
    return emit_write_result(
        args,
        "workstream note",
        f"{action} note to {heading} for Workstream {args.id}",
        changed,
        check_result,
        extra_payload={"id": args.id, "section": heading},
    )


def normalized_write_claim(value: str, workstream_id: str) -> tuple[str, str, str]:
    scope_type, scope_path = split_typed_scope(value)
    if not scope_type or not scope_path:
        raise SystemExit(f"workstream_scope_invalid: write scope must use TYPE: PATH: {value}")
    if scope_type not in {"authority", "draft", "owned", "assigned", "shared", "evidence"}:
        raise SystemExit(f"workstream_scope_invalid: unsupported write scope type: {scope_type}")
    normalized_path = normalize_scope_path(scope_path)
    diagnostics = validate_scope_path(normalized_path, "write_scope")
    if diagnostics:
        raise SystemExit(f"workstream_scope_invalid: {diagnostics[0].message}: {value}")
    return scope_type, normalized_path, f"{scope_type}: {normalized_path}"


def normalized_read_claim(value: str) -> str:
    normalized = normalize_scope_path(value)
    diagnostics = validate_scope_path(normalized, "read_scope")
    if diagnostics:
        raise SystemExit(f"workstream_scope_invalid: {diagnostics[0].message}: {value}")
    return normalized


def scope_paths_conflict(left: str, right: str) -> bool:
    left = normalize_scope_path(left)
    right = normalize_scope_path(right)
    if left == right:
        return True
    if "*" in left or "*" in right:
        return False
    return left.startswith(right.rstrip("/") + "/") or right.startswith(left.rstrip("/") + "/")


def check_workstream_write_claim_conflicts(
    root: Path,
    workstream_id: str,
    claims: Sequence[tuple[str, str, str]],
) -> None:
    exclusive_claims = [(scope_type, scope_path) for scope_type, scope_path, _item in claims if scope_type in {"authority", "assigned", "owned"}]
    if not exclusive_claims:
        return
    entries = parse_workstream_index(root)
    for entry in entries:
        if entry.workstream_id == workstream_id or entry.status not in ACTIVE_WORKSTREAM_STATUSES:
            continue
        detail = read_workstream_detail(root, entry.workstream_id)
        existing_scopes = detail.metadata.get("write_scope")
        if not isinstance(existing_scopes, list):
            continue
        for existing in existing_scopes:
            existing_type, existing_path = split_typed_scope(existing)
            if existing_type not in {"authority", "assigned", "owned"} or not existing_path:
                continue
            existing_path = normalize_scope_path(existing_path)
            for _claim_type, claim_path in exclusive_claims:
                if scope_paths_conflict(claim_path, existing_path):
                    raise SystemExit(
                        f"workstream_claim_conflict: {workstream_id} conflicts with {entry.workstream_id} on {claim_path}"
                    )


def append_unique_values(existing: str | list[str] | None, additions: Sequence[str]) -> tuple[list[str], bool]:
    values = list(existing) if isinstance(existing, list) else []
    changed = False
    for addition in additions:
        if addition not in values:
            values.append(addition)
            changed = True
    return values, changed


def append_workstream_activity(body: str, message: str) -> str:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    return append_or_create_section(body, "## Activity Log", f"- {timestamp}: {message}")


def workstream_scope_add_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    reason = (args.reason or "").strip()
    if not reason:
        raise SystemExit("workstream_reason_required: scope-add requires --reason")
    read_claims = [normalized_read_claim(value) for value in (args.read or [])]
    write_claims = [normalized_write_claim(value, args.id) for value in (args.write or [])]
    if not read_claims and not write_claims:
        raise SystemExit("workstream_scope_invalid: scope-add requires --read or --write")
    check_workstream_write_claim_conflicts(root, args.id, write_claims)

    detail = read_workstream_detail(root, args.id)
    metadata = dict(detail.metadata)
    if args.merge_owner is not None:
        metadata["merge_owner"] = args.merge_owner
    if args.coordination is not None:
        metadata["coordination"] = args.coordination
    read_scope, read_changed = append_unique_values(metadata.get("read_scope"), read_claims)
    write_scope, write_changed = append_unique_values(metadata.get("write_scope"), [item for _scope_type, _scope_path, item in write_claims])
    metadata["read_scope"] = read_scope
    metadata["write_scope"] = write_scope

    activity_bits: list[str] = []
    if read_claims:
        activity_bits.append("read_scope += " + ", ".join(read_claims))
    if write_claims:
        activity_bits.append("write_scope += " + ", ".join(item for _scope_type, _scope_path, item in write_claims))
    if args.merge_owner is not None:
        activity_bits.append(f"merge_owner = {args.merge_owner}")
    if args.coordination is not None:
        activity_bits.append(f"coordination = {args.coordination}")
    activity = "; ".join(activity_bits) + f"; reason: {reason}"
    body = append_workstream_activity(detail.body, activity)
    changed = [detail.path]
    if write_changed:
        changed.append(workstream_index_path(root))
    if not (read_changed or write_changed or args.merge_owner is not None or args.coordination is not None):
        changed = []
    if not dry_run and changed:
        detail.path.write_text(format_front_matter(metadata, body, WORKSTREAM_METADATA_FIELDS), encoding="utf-8")
        if write_changed:
            entries = parse_workstream_index(root)
            existing_entry = next((entry for entry in entries if entry.workstream_id == detail.workstream_id), None)
            write_workstream_index(root, replace_workstream_entry(entries, workstream_entry_from_detail(WorkstreamDetail(detail.workstream_id, detail.path, metadata, body, []), existing_entry)))
    check_result = maybe_check_after(args, root)
    action = "would update" if dry_run else "updated"
    return emit_write_result(
        args,
        "workstream scope-add",
        f"{action} scope for Workstream {args.id}",
        changed,
        check_result,
        extra_payload={
            "id": args.id,
            "read_scope": read_scope,
            "write_scope": write_scope,
            "reason": reason,
            "merge_owner": metadata.get("merge_owner"),
            "coordination": metadata.get("coordination"),
        },
    )


def workstream_context_payload(root: Path, detail: WorkstreamDetail) -> dict[str, object]:
    read_scope = normalize_scope_values(detail.metadata.get("read_scope"))
    write_scope = normalize_typed_scope_values(detail.metadata.get("write_scope"))
    status = workstream_detail_metadata_value(detail, "status", "Unknown")
    kind = workstream_type(detail)
    current_stage = detail.metadata.get("current_stage")
    forbidden = [
        "files outside this workstream write_scope",
        "owned files of other active workstreams",
        "authority files unless this workstream is Merge or Maintenance and explicitly declares authority scope",
    ]
    return {
        "id": detail.workstream_id,
        "type": kind,
        "status": status,
        "title": detail.metadata.get("title", detail.workstream_id),
        "owner": detail.metadata.get("owner", "未分配"),
        "detail": detail.path.relative_to(root).as_posix(),
        "current_stage": current_stage if isinstance(current_stage, str) else None,
        "read_scope": read_scope,
        "write_scope": write_scope,
        "merge_targets": detail.metadata.get("merge_targets") if isinstance(detail.metadata.get("merge_targets"), list) else [],
        "merge_owner": detail.metadata.get("merge_owner") if isinstance(detail.metadata.get("merge_owner"), str) else None,
        "coordination": detail.metadata.get("coordination") if isinstance(detail.metadata.get("coordination"), str) else None,
        "forbidden_scope": forbidden,
        "required_evidence": [
            "ReadyToMerge requires a merge request with target and summary.",
            "Done requires evidence and merge_resolution.",
            "Run `acf workstream guard <ID>` before ready/done.",
        ],
    }


def workstream_context_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    detail = read_workstream_detail(root, args.id)
    context = workstream_context_payload(root, detail)
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "workstream context",
        "ok": True,
        "context": str(root),
        "workstream": context,
        "error_code": None,
        "next_actions": [
            f"Read {context['detail']} first, then only the declared read_scope needed for this task.",
            f"Before changing status, run `acf workstream guard {args.id}`.",
        ],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"You are working on {args.id}.")
        print("")
        print(f"Type: {context['type']}")
        print(f"Status: {context['status']}")
        print(f"Detail: {context['detail']}")
        print("")
        print("Read first:")
        print(f"- {context['detail']}")
        for item in context["read_scope"]:
            print(f"- {item}")
        print("")
        print("You may write:")
        for item in context["write_scope"]:
            print(f"- {item}")
        print("")
        print("Do not write:")
        for item in context["forbidden_scope"]:
            print(f"- {item}")
        print("")
        print(f"Before ready/done: acf workstream guard {args.id}")
    return 0


def git_command_lines(project_root: Path, args: Sequence[str]) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"workstream_guard_git_unavailable: {result.stderr.strip() or result.stdout.strip() or 'git command failed'}")
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def git_toplevel(project_root: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"workstream_guard_git_unavailable: {result.stderr.strip() or 'not a git repository'}")
    return Path(result.stdout.strip()).resolve()


def workstream_changed_files(root: Path) -> list[str]:
    project_root = git_toplevel(infer_project_root(root))
    files: list[str] = []
    for args in (
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        files.extend(git_command_lines(project_root, args))
    return sorted(dict.fromkeys(files))


def changed_file_candidates(project_root: Path, root: Path, project_rel: str) -> list[str]:
    candidates = [normalize_scope_path(project_rel)]
    absolute = (project_root / project_rel).resolve()
    if is_relative_to(absolute, root.resolve()):
        candidates.append(absolute.relative_to(root.resolve()).as_posix())
    return sorted(dict.fromkeys(candidates))


def path_matches_scope(path_value: str, scope_value: str) -> bool:
    path_value = normalize_scope_path(path_value)
    scope_value = normalize_scope_path(scope_value)
    if "*" in scope_value:
        return fnmatch.fnmatch(path_value, scope_value)
    if path_value == scope_value:
        return True
    return path_value.startswith(scope_value.rstrip("/") + "/")


def workstream_direct_write_scopes(detail: WorkstreamDetail) -> list[tuple[str, str]]:
    kind = workstream_type(detail)
    scopes: list[tuple[str, str]] = []
    write_scope = detail.metadata.get("write_scope")
    if not isinstance(write_scope, list):
        return scopes
    merge_owner = detail.metadata.get("merge_owner")
    coordination = detail.metadata.get("coordination")
    for item in write_scope:
        scope_type, scope_path = split_typed_scope(item)
        if not scope_type or not scope_path:
            continue
        normalized_path = normalize_scope_path(scope_path)
        if scope_type in {"owned", "assigned", "draft", "evidence"}:
            scopes.append((scope_type, normalized_path))
        elif scope_type == "authority" and kind in {"Merge", "Maintenance"}:
            scopes.append((scope_type, normalized_path))
        elif scope_type == "shared" and (merge_owner == detail.workstream_id or (coordination == "serial" and kind in {"Merge", "Maintenance"})):
            scopes.append((scope_type, normalized_path))
    return scopes


def active_workstream_owned_scopes(root: Path, current_id: str) -> list[tuple[str, str, str]]:
    entries = parse_workstream_index(root)
    owned: list[tuple[str, str, str]] = []
    for entry in entries:
        if entry.workstream_id == current_id or entry.status not in ACTIVE_WORKSTREAM_STATUSES:
            continue
        detail = read_workstream_detail(root, entry.workstream_id)
        write_scope = detail.metadata.get("write_scope")
        if not isinstance(write_scope, list):
            continue
        for item in write_scope:
            scope_type, scope_path = split_typed_scope(item)
            if scope_type == "owned" and scope_path:
                owned.append((entry.workstream_id, detail.path.relative_to(root).as_posix(), normalize_scope_path(scope_path)))
    return owned


def guard_violations_for_files(
    root: Path,
    detail: WorkstreamDetail,
    changed_files: Sequence[str],
    project_root: Path,
) -> list[dict[str, str]]:
    direct_scopes = workstream_direct_write_scopes(detail)
    other_owned = active_workstream_owned_scopes(root, detail.workstream_id)
    kind = workstream_type(detail)
    violations: list[dict[str, str]] = []
    for project_rel in changed_files:
        candidates = changed_file_candidates(project_root, root, project_rel)
        matches_direct = any(
            path_matches_scope(candidate, scope_path)
            for candidate in candidates
            for _scope_type, scope_path in direct_scopes
        )
        conflict = next(
            (
                (other_id, other_path, owned_path)
                for other_id, other_path, owned_path in other_owned
                if any(path_matches_scope(candidate, owned_path) for candidate in candidates)
            ),
            None,
        )
        authority_changed = any(is_authority_path(candidate) for candidate in candidates)
        if conflict is not None:
            other_id, other_path, owned_path = conflict
            violations.append(
                {
                    "path": project_rel,
                    "reason": f"file is owned by active workstream {other_id}: {owned_path}",
                    "owner_detail": other_path,
                }
            )
            continue
        if authority_changed and kind == "Task":
            violations.append(
                {
                    "path": project_rel,
                    "reason": "Task workstream cannot directly write authority files; use merge-request",
                }
            )
            continue
        if not matches_direct:
            violations.append(
                {
                    "path": project_rel,
                    "reason": "changed file is outside direct write_scope",
                }
            )
    return violations


def workstream_guard_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    detail = read_workstream_detail(root, args.id)
    explicit_files = bool(args.changed_file)
    changed_files = [normalize_scope_path(value) for value in (args.changed_file or [])] if explicit_files else workstream_changed_files(root)
    project_root = infer_project_root(root).resolve() if explicit_files else git_toplevel(infer_project_root(root))
    violations = guard_violations_for_files(root, detail, changed_files, project_root)
    ok = not violations
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "workstream guard",
        "ok": ok,
        "context": str(root),
        "id": args.id,
        "changed_files": changed_files,
        "violations": violations,
        "error_code": None if ok else "workstream_guard_failed",
        "next_actions": [] if ok else ["Move the change into this Workstream write_scope, run scope-add with a reason, or create a Merge/Maintenance Workstream."],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        if ok:
            print(f"PASS: all changed files are allowed for {args.id}")
        else:
            print(f"FAIL: {len(violations)} changed file(s) are outside {args.id} write boundary")
            for violation in violations:
                print(f"- {violation['path']}: {violation['reason']}")
    return 0 if ok else EXIT_CHECK_FAILED


def workstream_merge_start_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    detail = read_workstream_detail(root, args.id)
    kind = workstream_type(detail)
    if kind not in {"Merge", "Maintenance"}:
        raise SystemExit(f"workstream_invalid_transition: {args.id} merge-start requires type Merge or Maintenance")
    current_status = workstream_detail_metadata_value(detail, "status", "")
    if "Merging" not in WORKSTREAM_STATE_TRANSITIONS.get(current_status, set()):
        raise SystemExit(f"workstream_invalid_transition: {args.id} {current_status} -> Merging")
    changed = update_workstream_status(
        root,
        args.id,
        "Merging",
        {"## 当前发现": (args.summary or "开始合并 ReadyToMerge 产物。").strip()},
        dry_run,
    )
    check_result = maybe_check_after(args, root)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(
        args,
        "workstream merge-start",
        f"{action} Workstream {args.id} Merging",
        changed,
        check_result,
        extra_payload={"id": args.id, "status": "Merging", "type": kind},
    )


def workstream_dashboard_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    entries = parse_workstream_index(root)
    details = [read_workstream_detail(root, entry.workstream_id) for entry in entries]
    errors: list[str] = []
    warnings: list[str] = []
    check_workstream_scope_claims(root, details, errors, warnings, strict=True)
    stale_days = args.stale_days
    today = date.today()
    stale: list[dict[str, str]] = []
    missing_evidence: list[dict[str, str]] = []
    authority_pending: list[dict[str, object]] = []
    for detail in details:
        status = workstream_detail_metadata_value(detail, "status", "Unknown")
        keep_until = detail.metadata.get("keep_active_until")
        if isinstance(keep_until, str) and DATE_RE.match(keep_until) and date.fromisoformat(keep_until) < today:
            stale.append({"id": detail.workstream_id, "reason": f"keep_active_until expired: {keep_until}"})
        elif status in ACTIVE_WORKSTREAM_STATUSES:
            age_days = (today - date.fromtimestamp(detail.path.stat().st_mtime)).days
            if age_days > stale_days:
                stale.append({"id": detail.workstream_id, "reason": f"detail not updated for {age_days} days"})
        if status in {"ReadyToMerge", "Done"} and workstream_section_missing(detail.body, "## 证据"):
            missing_evidence.append({"id": detail.workstream_id, "status": status})
        merge_targets = detail.metadata.get("merge_targets")
        if isinstance(merge_targets, list) and merge_targets and status in {"ReadyToMerge", "Merging"}:
            authority_pending.append({"id": detail.workstream_id, "status": status, "targets": merge_targets})

    by_status = workstream_counts(entries)
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "workstream dashboard",
        "ok": not errors,
        "context": str(root),
        "counts": by_status,
        "conflicts": errors,
        "warnings": warnings,
        "stale": stale,
        "missing_evidence": missing_evidence,
        "authority_writes_pending": authority_pending,
        "next_actions": [
            "Resolve conflicts before starting parallel work." if errors else "No write-scope conflicts detected.",
            "Use `acf workstream context <ID>` before executing a specific Workstream.",
            "Use `acf workstream guard <ID>` before ready/done.",
        ],
        "error_code": None if not errors else "workstream_dashboard_conflicts",
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"Active workstreams: {sum(by_status.get(status, 0) for status in ACTIVE_WORKSTREAM_STATUSES)}")
        print(f"ReadyToMerge: {by_status.get('ReadyToMerge', 0)}")
        print(f"Blocked: {by_status.get('Blocked', 0)}")
        print("")
        print("Conflicts:")
        if errors:
            for item in errors:
                print(f"- {item}")
        else:
            print("- none")
        print("")
        print("Authority writes pending:")
        if authority_pending:
            for item in authority_pending:
                print(f"- {item['id']} -> {', '.join(str(target) for target in item['targets'])}")
        else:
            print("- none")
        print("")
        print("Stale:")
        if stale:
            for item in stale:
                print(f"- {item['id']}: {item['reason']}")
        else:
            print("- none")
    return 0 if not errors else EXIT_CHECK_FAILED


def workstream_claim_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    read_claims = [normalized_read_claim(value) for value in (args.read or [])]
    write_claims = [normalized_write_claim(value, args.id) for value in (args.write or [])]
    if not read_claims and not write_claims:
        raise SystemExit("workstream_scope_invalid: claim requires --read or --write")
    check_workstream_write_claim_conflicts(root, args.id, write_claims)
    warnings: list[str] = []
    for scope_type, scope_path, _item in write_claims:
        if scope_type == "draft" and args.id not in Path(scope_path).name:
            warnings.append(f"draft write scope should include {args.id} in the file name: {scope_path}")

    detail = read_workstream_detail(root, args.id)
    metadata = dict(detail.metadata)
    read_scope, read_changed = append_unique_values(metadata.get("read_scope"), read_claims)
    write_scope, write_changed = append_unique_values(metadata.get("write_scope"), [item for _scope_type, _scope_path, item in write_claims])
    metadata["read_scope"] = read_scope
    metadata["write_scope"] = write_scope
    if not read_changed and not write_changed:
        changed = []
    else:
        changed = update_workstream_detail_metadata(root, detail, metadata, dry_run, sync_index_write_scope=write_changed)
    check_result = maybe_check_after(args, root)
    action = "would update" if dry_run else "updated"
    return emit_write_result(
        args,
        "workstream claim",
        f"{action} scope claims for Workstream {args.id}",
        changed,
        check_result,
        extra_payload={"id": args.id, "read_scope": read_scope, "write_scope": write_scope},
        warnings=warnings,
    )


def workstream_stage_add_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    workstream_id = args.id
    stage_id = args.stage_id
    require_workstream_stage_belongs_to(workstream_id, stage_id)
    detail = read_workstream_detail(root, workstream_id)
    rows = read_workstream_stage_rows(detail.body)
    if find_workstream_stage_row(rows, stage_id) is not None:
        raise SystemExit(f"workstream_stage_duplicate_id: {stage_id}")
    title = (args.title or "").strip()
    if not title:
        raise SystemExit("workstream_stage_scope_invalid: stage title cannot be empty")
    row = {
        "ID": stage_id,
        "状态": "Pending",
        "阶段": title,
        "依赖": (args.depends or "无。").strip() or "无。",
        "输出物": (args.output or "待补充。").strip() or "待补充。",
        "证据": "无。",
        "下一步": (args.next_action or "待推进。").strip() or "待推进。",
    }
    updated_text = format_front_matter(
        detail.metadata,
        replace_or_append_workstream_stage_rows(detail.body, [*rows, row]),
        WORKSTREAM_METADATA_FIELDS,
    )
    changed = [detail.path]
    if not dry_run:
        detail.path.write_text(updated_text, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would add" if dry_run else "added"
    return emit_write_result(
        args,
        "workstream stage add",
        f"{action} stage {stage_id} for Workstream {workstream_id}",
        changed,
        check_result,
        extra_payload={"id": workstream_id, "stage": workstream_stage_payload(row)},
    )


def workstream_stage_list_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    detail = read_workstream_detail(root, args.id)
    rows = read_workstream_stage_rows(detail.body)
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "workstream stage list",
        "ok": True,
        "context": str(root),
        "id": args.id,
        "detail": str(detail.path),
        "current_stage": detail.metadata.get("current_stage"),
        "stages": [workstream_stage_payload(row) for row in rows],
        "error_code": None,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        for row in rows:
            print(f"{row.get('ID')}\t{row.get('状态')}\t{row.get('阶段')}")
        if not rows:
            print("no workstream stages")
    return 0


def assert_workstream_stage_dependencies_done(workstream_id: str, rows: Sequence[dict[str, str]], row: dict[str, str]) -> None:
    rows_by_id = {candidate.get("ID", ""): candidate for candidate in rows}
    blocked: list[str] = []
    for dependency_id in workstream_stage_dependency_tokens(row.get("依赖", "")):
        if not workstream_stage_belongs_to(workstream_id, dependency_id):
            continue
        dependency = rows_by_id.get(dependency_id)
        if dependency is None or dependency.get("状态") != "Done":
            blocked.append(dependency_id)
    if blocked:
        raise SystemExit(f"workstream_stage_dependency_blocked: {row.get('ID')} depends on {', '.join(blocked)}")


def workstream_focus_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    workstream_id = args.id
    stage_id = args.stage_id
    require_workstream_stage_belongs_to(workstream_id, stage_id)
    detail = read_workstream_detail(root, workstream_id)
    rows = read_workstream_stage_rows(detail.body)
    row = find_workstream_stage_row(rows, stage_id)
    if row is None:
        raise SystemExit(f"workstream_stage_not_found: {stage_id}")
    current_status = row.get("状态", "")
    if terminal_workstream_stage_status(current_status):
        raise SystemExit(f"workstream_stage_terminal: {stage_id} has status {current_status}")
    active_stage_ids = [candidate.get("ID", "") for candidate in rows if candidate.get("状态") == "Active" and candidate.get("ID") != stage_id]
    if active_stage_ids:
        raise SystemExit(f"workstream_stage_active_conflict: {workstream_id} already has Active stage {active_stage_ids[0]}")
    assert_workstream_stage_dependencies_done(workstream_id, rows, row)

    updated_rows: list[dict[str, str]] = []
    for candidate in rows:
        updated = dict(candidate)
        if updated.get("ID") == stage_id:
            updated["状态"] = "Active"
        updated_rows.append(updated)
    metadata = dict(detail.metadata)
    metadata["current_stage"] = stage_id
    updated_text = format_front_matter(
        metadata,
        replace_or_append_workstream_stage_rows(detail.body, updated_rows),
        WORKSTREAM_METADATA_FIELDS,
    )
    changed = [detail.path]
    if not dry_run:
        detail.path.write_text(updated_text, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would focus" if dry_run else "focused"
    return emit_write_result(
        args,
        "workstream focus",
        f"{action} Workstream {workstream_id} on stage {stage_id}",
        changed,
        check_result,
        extra_payload={"id": workstream_id, "current_stage": stage_id},
    )


def workstream_stage_done_command(args: argparse.Namespace, *, deps: WorkstreamDependencies) -> int:
    _bind(deps)
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    workstream_id = args.id
    stage_id = args.stage_id
    require_workstream_stage_belongs_to(workstream_id, stage_id)
    evidence = required_workstream_evidence(args)
    detail = read_workstream_detail(root, workstream_id)
    rows = read_workstream_stage_rows(detail.body)
    row = find_workstream_stage_row(rows, stage_id)
    if row is None:
        raise SystemExit(f"workstream_stage_not_found: {stage_id}")
    current_status = row.get("状态", "")
    if current_status in {"Cancelled", "Skipped"}:
        raise SystemExit(f"workstream_stage_terminal: {stage_id} has status {current_status}")
    metadata = dict(detail.metadata)
    is_current_stage = metadata.get("current_stage") == stage_id
    if is_current_stage and not args.clear_current:
        raise SystemExit(f"workstream_stage_clear_current_required: {stage_id} is current_stage")
    if is_current_stage and args.clear_current:
        metadata.pop("current_stage", None)

    updated_rows: list[dict[str, str]] = []
    for candidate in rows:
        updated = dict(candidate)
        if updated.get("ID") == stage_id:
            updated["状态"] = "Done"
            updated["证据"] = evidence
            if args.next_action is not None:
                updated["下一步"] = args.next_action.strip() or "无。"
        updated_rows.append(updated)
    updated_text = format_front_matter(
        metadata,
        replace_or_append_workstream_stage_rows(detail.body, updated_rows),
        WORKSTREAM_METADATA_FIELDS,
    )
    changed = [detail.path]
    if not dry_run:
        detail.path.write_text(updated_text, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(
        args,
        "workstream stage done",
        f"{action} stage {stage_id} Done for Workstream {workstream_id}",
        changed,
        check_result,
        extra_payload={"id": workstream_id, "stage_id": stage_id, "status": "Done", "evidence": evidence},
    )


_MODULE_OWNED_NAMES = set(globals())
