"""High-level Workstream ID reservation on the configured primary branch.

This optional command is intentionally separate from ``workstream add`` and
from all worktree commands. It creates one narrow reservation commit but never
creates a Git branch or linked worktree. Interrupted reservations are resumed
from a Git-common-dir operation journal without guessing a new ID.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Mapping

from ai_context_framework.git_support import (
    acquire_operation_lock,
    canonical_path,
    commit_for_path,
    create_operation,
    current_branch,
    discover_git_project,
    git_path_in_ref_exists,
    is_ancestor,
    is_clean_except,
    load_operation,
    new_operation_id,
    next_workstream_id,
    porcelain_status_path,
    release_operation_lock,
    rev_parse,
    run_git,
    scan_used_workstream_numbers,
    staged_paths,
    status_porcelain,
    update_operation,
    validate_slug,
)
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.models import WorkstreamEntry


@dataclass(frozen=True)
class WorkstreamReserveDependencies:
    symbols: dict[str, Any]


_MODULE_OWNED_NAMES: set[str] | None = None


def _bind(deps: WorkstreamReserveDependencies) -> None:
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


def reserved_workspace_section(slug: str) -> str:
    return (
        "\n---\n\n## Workspace\n\n"
        f"- slug: {slug}\n"
        "- mode: none\n"
        "- note: Worktree is optional and is created only by a separate `acf worktree create` call.\n"
    )


def _emit(args: argparse.Namespace, payload: dict[str, object]) -> int:
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"status: {payload.get('status')}")
        if payload.get("id"):
            print(f"workstream: {payload['id']}")
        if payload.get("reservation_commit"):
            print(f"commit: {payload['reservation_commit']}")
    return 0


def _require_primary(project: Any) -> None:
    if project.project_root.resolve() != project.config.primary_checkout.resolve():
        raise SystemExit(
            f"reservation_requires_primary_checkout: use {project.config.primary_checkout}"
        )
    if current_branch(project.config.primary_checkout) != project.config.primary_branch:
        raise SystemExit(
            f"primary_branch_mismatch: expected {project.config.primary_branch}"
        )


def _build_spec(
    args: argparse.Namespace,
    project: Any,
    root: Any,
    *,
    selected_id: str,
    slug: str,
    used_id_count: int,
) -> dict[str, Any]:
    read_scope = [
        normalized_read_claim(value)
        for value in (args.read_scope or ["active/Context.md", "active/Task_Plan.md"])
    ]
    write_scope = [
        normalized_write_claim(value, selected_id)[2]
        for value in (args.write_scope or [workstream_write_scope(selected_id)])
    ]
    depends_on = list(args.depends_on or [])
    output = args.output.strip() if args.output else "待补充。"
    goal = args.goal.strip() if args.goal else "待补充。"
    has_shared_scope = any(value.startswith("shared:") for value in write_scope)
    merge_owner = args.merge_owner or (selected_id if has_shared_scope else None)
    coordination = args.coordination or ("serial" if has_shared_scope else None)
    detail_path = workstream_details_dir(root) / f"{selected_id}.md"
    index_path = workstream_index_path(root)
    planned_detail = render_workstream_detail(
        selected_id,
        args.title.strip(),
        args.owner.strip(),
        depends_on,
        read_scope,
        write_scope,
        output,
        goal,
        args.type,
        args.attention,
        merge_owner,
        coordination,
    ).rstrip() + reserved_workspace_section(slug)
    entry = {
        "workstream_id": selected_id,
        "status": "Open",
        "title": args.title.strip(),
        "owner": args.owner.strip(),
        "write_scope": ", ".join(write_scope),
        "depends_on": ",".join(depends_on) if depends_on else "无。",
        "output": output,
        "detail": workstream_detail_rel(selected_id),
    }
    return {
        "workstream_id": selected_id,
        "slug": slug,
        "title": args.title.strip(),
        "owner": args.owner.strip(),
        "workstream_type": args.type,
        "detail_path": str(detail_path),
        "index_path": str(index_path),
        "detail_relative": detail_path.relative_to(project.repo_root).as_posix(),
        "index_relative": index_path.relative_to(project.repo_root).as_posix(),
        "planned_detail": planned_detail,
        "entry": entry,
        "message": args.message or f"文档：登记{selected_id}任务占位",
        "primary_branch": project.config.primary_branch,
        "base_commit": rev_parse(project.repo_root, project.config.primary_branch),
        "used_id_count": used_id_count,
    }


def _normalized_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _entry_from_spec(spec: Mapping[str, Any]) -> WorkstreamEntry:
    raw = spec.get("entry")
    if not isinstance(raw, Mapping):
        raise SystemExit("operation_journal_invalid: reservation entry missing")
    try:
        return WorkstreamEntry(
            workstream_id=str(raw["workstream_id"]),
            status=str(raw["status"]),
            title=str(raw["title"]),
            owner=str(raw["owner"]),
            write_scope=str(raw["write_scope"]),
            depends_on=str(raw["depends_on"]),
            output=str(raw["output"]),
            detail=str(raw["detail"]),
        )
    except KeyError as exc:
        raise SystemExit("operation_journal_invalid: incomplete reservation entry") from exc


def _plan_payload(project: Any, spec: Mapping[str, Any], *, status: str) -> dict[str, object]:
    return {
        "command": "workstream reserve",
        "ok": True,
        "error_code": None,
        "status": status,
        "id": str(spec["workstream_id"]),
        "slug": str(spec["slug"]),
        "detail": str(spec["detail_path"]),
        "index": str(spec["index_path"]),
        "primary_checkout": str(project.config.primary_checkout),
        "primary_branch": project.config.primary_branch,
        "applied": False,
        "changed_files": [str(spec["detail_path"]), str(spec["index_path"])],
        "used_id_count": int(spec.get("used_id_count") or 0),
        "next_actions": [
            "Review the reservation plan and rerun with --apply. Worktree creation remains a separate command."
        ],
    }


def _reservation_commit_if_complete(project: Any, spec: Mapping[str, Any]) -> str | None:
    workstream_id = str(spec["workstream_id"])
    detail_relative = str(spec["detail_relative"])
    main_ref = project.config.primary_branch
    if not git_path_in_ref_exists(project.repo_root, main_ref, detail_relative):
        return None
    commit = commit_for_path(project.repo_root, main_ref, detail_relative)
    if commit and is_ancestor(project.repo_root, commit, main_ref):
        return commit
    raise SystemExit(
        f"workstream_reservation_conflict: {workstream_id} detail exists without a valid primary reservation commit"
    )


def _allowed_dirty_paths(root: Any, project: Any, spec: Mapping[str, Any]) -> set[str]:
    return {
        (root / ".acf.lock").relative_to(project.repo_root).as_posix(),
        str(spec["detail_relative"]),
        str(spec["index_relative"]),
    }


def _apply_spec(project: Any, root: Any, operation: dict[str, Any], spec: Mapping[str, Any]) -> str:
    completed_commit = _reservation_commit_if_complete(project, spec)
    if completed_commit:
        update_operation(
            project.common_dir,
            operation,
            status="completed",
            resume_allowed=False,
            reservation_commit=completed_commit,
        )
        return completed_commit

    current_primary = rev_parse(project.repo_root, project.config.primary_branch)
    if current_primary != str(spec["base_commit"]):
        raise SystemExit(
            f"primary_branch_advanced: expected {spec['base_commit']}, current {current_primary}"
        )
    allowed = _allowed_dirty_paths(root, project, spec)
    unexpected = [
        porcelain_status_path(line)
        for line in status_porcelain(project.config.primary_checkout)
        if porcelain_status_path(line) not in allowed
    ]
    if unexpected:
        raise SystemExit(
            "primary_checkout_dirty: unexpected paths " + ", ".join(sorted(unexpected))
        )

    detail_path = canonical_path(str(spec["detail_path"]))
    index_path = canonical_path(str(spec["index_path"]))
    planned_detail = str(spec["planned_detail"])
    entry = _entry_from_spec(spec)
    entries = parse_workstream_index(root)
    existing_entry = next(
        (row for row in entries if row.workstream_id == entry.workstream_id), None
    )
    if detail_path.exists():
        if _normalized_text(detail_path.read_text(encoding="utf-8")) != _normalized_text(planned_detail):
            raise SystemExit(
                f"workstream_reservation_conflict: {detail_path} content differs from journal"
            )
    else:
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail_path.write_text(planned_detail, encoding="utf-8")
    if existing_entry is not None and existing_entry != entry:
        raise SystemExit(
            f"workstream_reservation_conflict: index row for {entry.workstream_id} differs from journal"
        )
    if existing_entry is None:
        write_workstream_index(root, [*entries, entry])

    check_result = check_context(root, infer_context_profile(root), False)
    if not check_result.ok:
        raise SystemExit("check_failed: " + "; ".join(check_result.errors))
    relative_paths = [str(spec["detail_relative"]), str(spec["index_relative"])]
    run_git(project.config.primary_checkout, ("add", "--", *relative_paths))
    actual_staged = sorted(staged_paths(project.config.primary_checkout))
    if actual_staged != sorted(relative_paths):
        raise SystemExit(
            "workstream_reservation_stage_mismatch: staged files differ from reservation files"
        )
    run_git(project.config.primary_checkout, ("commit", "-m", str(spec["message"])))
    commit = rev_parse(project.config.primary_checkout, "HEAD")
    update_operation(
        project.common_dir,
        operation,
        status="completed",
        resume_allowed=False,
        reservation_commit=commit,
    )
    return commit


def _resume(
    args: argparse.Namespace,
    project: Any,
    root: Any,
    operation_id: str,
) -> int:
    operation = load_operation(project.common_dir, operation_id)
    if operation.get("command") != "workstream.reserve":
        raise SystemExit(
            f"operation_resume_unsupported: {operation.get('command', 'unknown')}"
        )
    spec = operation.get("reservation")
    if not isinstance(spec, Mapping):
        raise SystemExit("operation_journal_invalid: reservation specification missing")
    payload = _plan_payload(project, spec, status="reservation_resume_planned")
    payload["operation_id"] = operation_id
    payload["operation"] = operation
    if not args.apply:
        return _emit(args, payload)
    lock = acquire_operation_lock(
        project.common_dir, "workstream-reservation", operation_id
    )
    try:
        commit = _apply_spec(project, root, operation, spec)
    except BaseException as exc:
        update_operation(
            project.common_dir,
            operation,
            status="failed",
            resume_allowed=True,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
    finally:
        release_operation_lock(lock)
    payload.update(
        {
            "status": "reserved",
            "applied": True,
            "reservation_commit": commit,
            "next_actions": [
                f"Create an optional worktree only when needed: acf worktree create --workstream {spec['workstream_id']} --apply"
            ],
        }
    )
    return _emit(args, payload)


def workstream_reserve_command(
    args: argparse.Namespace, *, deps: WorkstreamReserveDependencies
) -> int:
    """Plan, apply, or resume a globally unique Workstream reservation."""

    _bind(deps)
    project = discover_git_project(args.path)
    root = require_context_root(args.path)
    _require_primary(project)
    if args.resume_operation:
        return _resume(args, project, root, args.resume_operation)
    missing = [
        name
        for name in ("title", "slug", "owner")
        if not isinstance(getattr(args, name, None), str)
        or not getattr(args, name).strip()
    ]
    if missing:
        raise SystemExit(
            "workstream_reservation_fields_required: " + ", ".join(missing)
        )
    slug = validate_slug(args.slug)
    evidence = scan_used_workstream_numbers(project)
    explicit_id = bool(args.id)
    if explicit_id:
        selected_id = args.id.upper()
        if int(selected_id[2:]) in evidence:
            raise SystemExit(f"workstream_duplicate_id: {selected_id}")
    else:
        selected_id, evidence = next_workstream_id(project)
    spec = _build_spec(
        args,
        project,
        root,
        selected_id=selected_id,
        slug=slug,
        used_id_count=len(evidence),
    )
    payload = _plan_payload(project, spec, status="reservation_planned")
    if not args.apply:
        return _emit(args, payload)

    context_lock_rel = (root / ".acf.lock").relative_to(project.repo_root).as_posix()
    if not is_clean_except(project.config.primary_checkout, [context_lock_rel]):
        raise SystemExit(f"primary_checkout_dirty: {project.config.primary_checkout}")
    operation_id = new_operation_id("workstream.reserve")
    lock = acquire_operation_lock(
        project.common_dir, "workstream-reservation", operation_id
    )
    operation: dict[str, Any] | None = None
    try:
        fresh_evidence = scan_used_workstream_numbers(project)
        if int(selected_id[2:]) in fresh_evidence:
            if explicit_id:
                raise SystemExit(f"workstream_duplicate_id: {selected_id}")
            selected_id, fresh_evidence = next_workstream_id(project)
            spec = _build_spec(
                args,
                project,
                root,
                selected_id=selected_id,
                slug=slug,
                used_id_count=len(fresh_evidence),
            )
            payload = _plan_payload(project, spec, status="reservation_planned")
        operation = create_operation(
            project.common_dir,
            command="workstream.reserve",
            target=None,
            operation_id=operation_id,
            extra={"reservation": spec},
        )
        commit = _apply_spec(project, root, operation, spec)
    except BaseException as exc:
        if operation is not None:
            update_operation(
                project.common_dir,
                operation,
                status="failed",
                resume_allowed=True,
                error=f"{type(exc).__name__}: {exc}",
            )
        raise
    finally:
        release_operation_lock(lock)

    payload.update(
        {
            "status": "reserved",
            "applied": True,
            "reservation_commit": commit,
            "operation_id": operation_id,
            "next_actions": [
                f"Create an optional worktree only when needed: acf worktree create --workstream {spec['workstream_id']} --apply"
            ],
        }
    )
    return _emit(args, payload)


_MODULE_OWNED_NAMES = set(globals())
