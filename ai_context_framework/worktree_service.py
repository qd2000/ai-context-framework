"""Optional Git worktree lifecycle service used by the ACF CLI.

The service is deliberately separate from the existing Workstream commands.
Creating or updating a Workstream does not import this module and never creates
Git branches or worktrees implicitly.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ai_context_framework.front_matter import parse_front_matter
from ai_context_framework.worktree_artifacts import build_artifact_plan, load_artifact_plan
from ai_context_framework.worktree_collision import (
    analyze_primary_collisions,
    build_candidate_preview,
)
from ai_context_framework.worktree_merge_contracts import (
    DEFAULT_MERGE_RETRY_POLICY,
    MergeRetryPolicy,
    artifact_handoff_ready_for_promotion,
)
from ai_context_framework.worktree_status import capture_git_worktree_snapshot
from ai_context_framework.worktree_retry import (
    acquire_lock_with_wait,
    release_owned_lock,
    retry_delay,
)
from ai_context_framework.git_support import (
    GitCommandError,
    GitProject,
    WorktreeRecord,
    WorktreeTarget,
    acquire_operation_lock,
    branch_exists,
    build_non_workstream_target,
    build_workstream_target,
    canonical_path,
    commit_for_path,
    create_operation,
    current_branch,
    delete_registry,
    discover_git_project,
    git_common_dir,
    git_path_in_ref_exists,
    is_ancestor,
    is_clean,
    list_registries,
    list_worktrees,
    load_operation,
    merge_tree,
    path_key,
    read_registry,
    record_for_path,
    records_for_branch,
    release_operation_lock,
    rev_parse,
    run_git,
    status_porcelain,
    target_payload,
    update_operation,
    update_operation_step,
    validate_slug,
    write_registry,
)


WORKSPACE_SECTION_RE = re.compile(r"(?ms)^## Workspace\s*$\n(?P<body>.*?)(?=^## |\Z)")
WORKSPACE_FIELD_RE = re.compile(r"(?m)^-\s*([a-z_]+)\s*:\s*(.*?)\s*$")


@dataclass(frozen=True)
class WorkstreamInfo:
    workstream_id: str
    title: str
    status: str
    detail_path: Path
    relative_path: str
    slug: str | None


def read_workstream_info(project: GitProject, workstream_id: str) -> WorkstreamInfo:
    normalized = workstream_id.upper()
    detail_path = project.context_root / "active" / "workstreams" / f"{normalized}.md"
    if not detail_path.is_file():
        raise SystemExit(f"workstream_not_found: {normalized}")
    metadata, body, diagnostics = parse_front_matter(detail_path.read_text(encoding="utf-8"))
    if diagnostics:
        raise SystemExit(f"workstream_schema_failed: {normalized}")
    if str(metadata.get("id") or "").upper() != normalized:
        raise SystemExit(f"workstream_schema_failed: {normalized} id mismatch")
    slug: str | None = None
    section = WORKSPACE_SECTION_RE.search(body)
    if section:
        fields = {
            match.group(1): match.group(2).strip()
            for match in WORKSPACE_FIELD_RE.finditer(section.group("body"))
        }
        raw_slug = fields.get("slug")
        if raw_slug and raw_slug not in {"none", "null", "待定", "待补充"}:
            slug = validate_slug(raw_slug)
    relative_path = detail_path.relative_to(project.repo_root).as_posix()
    return WorkstreamInfo(
        workstream_id=normalized,
        title=str(metadata.get("title") or normalized),
        status=str(metadata.get("status") or "Unknown"),
        detail_path=detail_path,
        relative_path=relative_path,
        slug=slug,
    )


def resolve_workstream_target(
    project: GitProject, workstream_id: str, *, slug_override: str | None = None
) -> tuple[WorktreeTarget, WorkstreamInfo]:
    info = read_workstream_info(project, workstream_id)
    slug = validate_slug(slug_override) if slug_override else info.slug
    if not slug:
        raise SystemExit(
            f"worktree_slug_required: {info.workstream_id} has no Workspace slug; pass --slug"
        )
    primary_ref = project.config.primary_branch
    if not git_path_in_ref_exists(project.repo_root, primary_ref, info.relative_path):
        raise SystemExit(
            f"workstream_not_reserved_on_primary: {info.workstream_id} is not present in {primary_ref}"
        )
    reservation_commit = commit_for_path(project.repo_root, primary_ref, info.relative_path)
    if not reservation_commit:
        raise SystemExit(
            f"workstream_not_reserved_on_primary: no reservation commit for {info.workstream_id}"
        )
    base_commit = rev_parse(project.repo_root, primary_ref)
    target = build_workstream_target(
        project,
        workstream_id=info.workstream_id,
        slug=slug,
        base_commit=base_commit,
        reservation_path=info.relative_path,
        reservation_commit=reservation_commit,
    )
    return target, info


def resolve_non_workstream_target(project: GitProject, kind: str, slug: str) -> WorktreeTarget:
    return build_non_workstream_target(
        project,
        kind=kind,
        slug=slug,
        base_commit=rev_parse(project.repo_root, project.config.primary_branch),
    )


def _registered_record(project: GitProject, key: str) -> tuple[dict[str, Any] | None, WorktreeRecord | None]:
    registry = read_registry(project.common_dir, key)
    if registry is None:
        return None, None
    raw_path = registry.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise SystemExit(f"worktree_registry_invalid: {key} has no path")
    record = record_for_path(list_worktrees(project.repo_root), raw_path)
    return registry, record


def plan_create(project: GitProject, target: WorktreeTarget) -> dict[str, Any]:
    records = list_worktrees(project.repo_root)
    path_record = record_for_path(records, target.path)
    branch_records = records_for_branch(records, target.branch)
    branch_present = branch_exists(project.repo_root, target.branch)
    path_exists = target.path.exists()

    if len(branch_records) > 1:
        raise SystemExit(f"branch_already_checked_out: {target.branch}")
    if branch_records and path_key(branch_records[0].path) != path_key(target.path):
        raise SystemExit(
            f"branch_already_checked_out: {target.branch} at {branch_records[0].path}"
        )
    if path_record:
        if path_record.detached:
            raise SystemExit(f"detached_worktree_not_supported: {path_record.path}")
        if path_record.branch_short != target.branch:
            raise SystemExit(
                f"worktree_branch_mismatch: {path_record.path} uses {path_record.branch_short}"
            )
        actual_common = git_common_dir(path_record.path)
        if path_key(actual_common) != path_key(project.common_dir):
            raise SystemExit(
                f"git_common_dir_mismatch: {path_record.path} uses {actual_common}"
            )
        return {
            "status": "already_created",
            "branch_exists": True,
            "path_exists": True,
            "worktree_registered": True,
            "resumable": True,
            "target": target_payload(target),
        }
    if path_exists:
        try:
            actual_common = git_common_dir(target.path)
        except (SystemExit, GitCommandError) as exc:
            raise SystemExit(f"target_path_exists_not_worktree: {target.path}") from exc
        if path_key(actual_common) != path_key(project.common_dir):
            raise SystemExit(
                f"git_common_dir_mismatch: {target.path} uses {actual_common}"
            )
        raise SystemExit(f"orphan_target_path: {target.path} is not registered")
    if branch_present:
        if target.reservation_commit and not is_ancestor(
            project.repo_root, target.reservation_commit, target.branch
        ):
            raise SystemExit(
                f"worktree_branch_conflict: {target.branch} does not contain reservation {target.reservation_commit}"
            )
        return {
            "status": "branch_exists_path_missing",
            "branch_exists": True,
            "path_exists": False,
            "worktree_registered": False,
            "resumable": True,
            "target": target_payload(target),
        }
    return {
        "status": "ready_to_create",
        "branch_exists": False,
        "path_exists": False,
        "worktree_registered": False,
        "resumable": True,
        "target": target_payload(target),
    }


def verify_target(project: GitProject, target: WorktreeTarget) -> dict[str, Any]:
    records = list_worktrees(project.repo_root)
    record = record_for_path(records, target.path)
    issues: list[str] = []
    warnings: list[str] = []
    if record is None:
        issues.append("worktree_not_registered")
        return {
            "ok": False,
            "issues": issues,
            "warnings": warnings,
            "target": target_payload(target),
            "exists": target.path.exists(),
            "clean": None,
        }
    if record.detached:
        issues.append("detached_worktree")
    if record.prunable:
        issues.append("worktree_prunable")
    if record.branch_short != target.branch:
        issues.append("branch_mismatch")
    try:
        actual_common = git_common_dir(record.path)
    except SystemExit:
        actual_common = None
        issues.append("git_common_dir_unreadable")
    if actual_common is not None and path_key(actual_common) != path_key(project.common_dir):
        issues.append("git_common_dir_mismatch")
    branch_rows = records_for_branch(records, target.branch)
    if len(branch_rows) != 1:
        issues.append("branch_checkout_count_invalid")
    clean = is_clean(record.path)
    if not clean:
        warnings.append("worktree_dirty")
    head = record.head or rev_parse(record.path, "HEAD")
    if target.reservation_commit and not is_ancestor(
        project.repo_root, target.reservation_commit, head
    ):
        issues.append("reservation_commit_not_ancestor")
    registry = read_registry(project.common_dir, target.key)
    if registry is None:
        warnings.append("registry_missing")
    else:
        if path_key(str(registry.get("path") or "")) != path_key(target.path):
            issues.append("registry_path_mismatch")
        if str(registry.get("branch") or "") != target.branch:
            issues.append("registry_branch_mismatch")
    return {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "target": target_payload(target),
        "exists": record.path.is_dir(),
        "clean": clean,
        "head": head,
        "branch": record.branch_short,
        "git_common_dir": str(actual_common) if actual_common else None,
        "registry": registry,
    }


def apply_create(
    project: GitProject,
    target: WorktreeTarget,
    *,
    operation_id: str | None = None,
) -> dict[str, Any]:
    operation = create_operation(
        project.common_dir,
        command="worktree.create",
        target=target,
        operation_id=operation_id,
    )
    lock = acquire_operation_lock(
        project.common_dir, f"{target.key}-worktree", str(operation["operation_id"])
    )
    try:
        plan = plan_create(project, target)
        update_operation_step(
            project.common_dir,
            operation,
            "preflight",
            "completed",
            plan_status=plan["status"],
        )
        current_primary = rev_parse(project.repo_root, target.base_branch)
        if current_primary != target.base_commit and not branch_exists(
            project.repo_root, target.branch
        ):
            raise SystemExit(
                f"primary_branch_advanced: expected {target.base_commit}, current {current_primary}"
            )
        if not branch_exists(project.repo_root, target.branch):
            run_git(
                project.repo_root,
                ("branch", target.branch, target.base_commit),
            )
            update_operation_step(
                project.common_dir,
                operation,
                "branch_created",
                "completed",
                branch=target.branch,
                base_commit=target.base_commit,
            )
        else:
            update_operation_step(
                project.common_dir,
                operation,
                "branch_created",
                "already_completed",
                branch=target.branch,
            )
        records = list_worktrees(project.repo_root)
        if record_for_path(records, target.path) is None:
            target.path.parent.mkdir(parents=True, exist_ok=True)
            run_git(
                project.repo_root,
                ("worktree", "add", str(target.path), target.branch),
            )
            update_operation_step(
                project.common_dir,
                operation,
                "worktree_created",
                "completed",
                path=str(target.path),
            )
        else:
            update_operation_step(
                project.common_dir,
                operation,
                "worktree_created",
                "already_completed",
                path=str(target.path),
            )
        registry_path = write_registry(
            project.common_dir,
            target.key,
            {
                "workstream": target.workstream_id,
                "kind": target.kind,
                "slug": target.slug,
                "path": str(target.path),
                "branch": target.branch,
                "base_branch": target.base_branch,
                "base_commit": target.base_commit,
                "reservation_commit": target.reservation_commit,
                "git_common_dir": str(project.common_dir),
                "state": "active",
            },
        )
        update_operation_step(
            project.common_dir,
            operation,
            "registry_written",
            "completed",
            registry_path=str(registry_path),
        )
        verification = verify_target(project, target)
        if not verification["ok"]:
            raise SystemExit(
                "worktree_verification_failed: " + ",".join(verification["issues"])
            )
        update_operation_step(
            project.common_dir,
            operation,
            "verification",
            "completed",
        )
        update_operation(
            project.common_dir,
            operation,
            status="completed",
            resume_allowed=False,
            result_status=(
                "already_created" if plan["status"] == "already_created" else "created"
            ),
        )
        return {
            "status": operation["result_status"],
            "operation_id": operation["operation_id"],
            "target": target_payload(target),
            "verification": verification,
        }
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


def attach_workstream(
    project: GitProject,
    *,
    workstream_id: str,
    target_path: Path,
    slug_override: str | None,
    apply: bool,
) -> dict[str, Any]:
    expected, _info = resolve_workstream_target(
        project, workstream_id, slug_override=slug_override
    )
    path = canonical_path(target_path)
    records = list_worktrees(project.repo_root)
    record = record_for_path(records, path)
    if record is None:
        raise SystemExit(f"worktree_not_registered: {path}")
    if record.detached or not record.branch_short:
        raise SystemExit(f"detached_worktree_not_supported: {path}")
    actual_common = git_common_dir(path)
    if path_key(actual_common) != path_key(project.common_dir):
        raise SystemExit(f"git_common_dir_mismatch: {path} uses {actual_common}")
    if record.branch_short == project.config.primary_branch:
        raise SystemExit("primary_branch_not_allowed_for_linked_worktree")
    if record.branch_short != expected.branch or path_key(path) != path_key(expected.path):
        raise SystemExit(
            f"worktree_name_mismatch: expected {expected.branch} at {expected.path}"
        )
    existing = read_registry(project.common_dir, expected.key)
    if existing and path_key(str(existing.get("path") or "")) != path_key(path):
        raise SystemExit(
            f"workstream_already_bound: {workstream_id} at {existing.get('path')}"
        )
    payload = {
        "status": "ready_to_attach" if not existing else "already_attached",
        "target": target_payload(expected),
        "record": {
            "path": str(record.path),
            "branch": record.branch_short,
            "head": record.head,
        },
    }
    if apply:
        write_registry(
            project.common_dir,
            expected.key,
            {
                "workstream": expected.workstream_id,
                "kind": None,
                "slug": expected.slug,
                "path": str(path),
                "branch": expected.branch,
                "base_branch": expected.base_branch,
                "base_commit": expected.base_commit,
                "reservation_commit": expected.reservation_commit,
                "git_common_dir": str(project.common_dir),
                "state": "active",
            },
        )
        payload["status"] = "attached" if not existing else "already_attached"
        payload["verification"] = verify_target(project, expected)
    return payload


def target_from_registry(
    project: GitProject, *, workstream_id: str | None = None, target_path: Path | None = None
) -> WorktreeTarget:
    if workstream_id:
        key = workstream_id.upper()
        registry = read_registry(project.common_dir, key)
        if registry is None:
            target, _ = resolve_workstream_target(project, key)
            return target
    elif target_path is not None:
        expected = path_key(target_path)
        registry = next(
            (
                row
                for row in list_registries(project.common_dir)
                if isinstance(row.get("path"), str)
                and path_key(str(row["path"])) == expected
            ),
            None,
        )
        if registry is None:
            record = record_for_path(list_worktrees(project.repo_root), target_path)
            if record is None or not record.branch_short:
                raise SystemExit(f"worktree_not_registered: {target_path}")
            return WorktreeTarget(
                key=f"path:{path_key(target_path)}",
                branch=record.branch_short,
                path=canonical_path(target_path),
                base_branch=project.config.primary_branch,
                base_commit=rev_parse(project.repo_root, project.config.primary_branch),
            )
    else:
        raise SystemExit("worktree_target_required: pass --workstream or --target")

    if not isinstance(registry, Mapping):
        raise SystemExit("worktree_registry_invalid")
    raw_path = registry.get("path")
    branch = registry.get("branch")
    if not isinstance(raw_path, str) or not isinstance(branch, str):
        raise SystemExit("worktree_registry_invalid")
    return WorktreeTarget(
        key=str(registry.get("key") or workstream_id or f"path:{path_key(raw_path)}"),
        branch=branch,
        path=canonical_path(raw_path),
        base_branch=str(registry.get("base_branch") or project.config.primary_branch),
        base_commit=str(
            registry.get("base_commit")
            or rev_parse(project.repo_root, project.config.primary_branch)
        ),
        workstream_id=(
            str(registry.get("workstream"))
            if registry.get("workstream")
            else workstream_id.upper()
            if workstream_id
            else None
        ),
        kind=str(registry.get("kind")) if registry.get("kind") else None,
        slug=str(registry.get("slug")) if registry.get("slug") else None,
        reservation_commit=(
            str(registry.get("reservation_commit"))
            if registry.get("reservation_commit")
            else None
        ),
    )


def list_payload(project: GitProject) -> dict[str, Any]:
    registries = list_registries(project.common_dir)
    registry_by_path = {
        path_key(str(row.get("path"))): row
        for row in registries
        if isinstance(row.get("path"), str)
    }
    rows: list[dict[str, Any]] = []
    for record in list_worktrees(project.repo_root):
        registry = registry_by_path.get(path_key(record.path))
        rows.append(
            {
                "path": str(record.path),
                "head": record.head,
                "branch": record.branch_short,
                "detached": record.detached,
                "bare": record.bare,
                "prunable": record.prunable,
                "clean": is_clean(record.path) if record.path.exists() and not record.bare else None,
                "binding": registry,
            }
        )
    return {
        "primary_checkout": str(project.config.primary_checkout),
        "primary_branch": project.config.primary_branch,
        "worktree_root": str(project.config.worktree_root),
        "git_common_dir": str(project.common_dir),
        "worktrees": rows,
        "registries": registries,
    }


def audit_project(project: GitProject) -> dict[str, Any]:
    payload = list_payload(project)
    findings: list[dict[str, Any]] = []
    records = list_worktrees(project.repo_root)
    primary_key = path_key(project.config.primary_checkout)
    configured_root = path_key(project.config.worktree_root)
    record_paths = {path_key(record.path) for record in records}

    for record in records:
        if path_key(record.path) == primary_key:
            if record.branch_short != project.config.primary_branch:
                findings.append(
                    {
                        "severity": "error",
                        "code": "primary_branch_mismatch",
                        "path": str(record.path),
                        "actual": record.branch_short,
                        "expected": project.config.primary_branch,
                    }
                )
            continue
        if record.detached:
            findings.append(
                {
                    "severity": "error",
                    "code": "detached_worktree",
                    "path": str(record.path),
                }
            )
        if record.prunable:
            findings.append(
                {
                    "severity": "error",
                    "code": "prunable_worktree",
                    "path": str(record.path),
                    "detail": record.prunable,
                }
            )
        if not path_key(record.path).startswith(configured_root.rstrip("/") + "/"):
            findings.append(
                {
                    "severity": "warning",
                    "code": "worktree_outside_configured_root",
                    "path": str(record.path),
                }
            )
        if record.branch_short == project.config.primary_branch:
            findings.append(
                {
                    "severity": "error",
                    "code": "primary_branch_in_linked_worktree",
                    "path": str(record.path),
                }
            )
    for registry in payload["registries"]:
        raw_path = registry.get("path")
        if not isinstance(raw_path, str):
            findings.append(
                {
                    "severity": "error",
                    "code": "registry_path_missing",
                    "registry": registry.get("registry_path"),
                }
            )
            continue
        if path_key(raw_path) not in record_paths:
            findings.append(
                {
                    "severity": "error",
                    "code": "stale_registry",
                    "path": raw_path,
                    "registry": registry.get("registry_path"),
                }
            )
    payload["findings"] = findings
    payload["errors"] = [row for row in findings if row["severity"] == "error"]
    payload["warnings"] = [row for row in findings if row["severity"] == "warning"]
    payload["ok"] = not payload["errors"]
    return payload


def plan_sync(project: GitProject, target: WorktreeTarget) -> dict[str, Any]:
    verification = verify_target(project, target)
    if not verification["ok"]:
        raise SystemExit(
            "worktree_verification_failed: " + ",".join(verification["issues"])
        )
    if not verification["clean"]:
        raise SystemExit(f"worktree_dirty: {target.path}")
    source_head = rev_parse(project.repo_root, target.branch)
    primary_head = rev_parse(project.repo_root, target.base_branch)
    if is_ancestor(project.repo_root, primary_head, source_head):
        status = "already_up_to_date"
        preview = {"ok": True, "tree": source_head, "mode": "ancestor"}
    else:
        preview = merge_tree(project.repo_root, target.branch, target.base_branch)
        if not preview["ok"]:
            raise SystemExit("merge_conflicts_detected: syncing primary into worktree")
        status = "ready_to_sync"
    return {
        "status": status,
        "source_head": source_head,
        "primary_head": primary_head,
        "merge_preview": preview,
        "target": target_payload(target),
    }


def apply_sync(project: GitProject, target: WorktreeTarget) -> dict[str, Any]:
    plan = plan_sync(project, target)
    if plan["status"] == "already_up_to_date":
        return plan
    operation = create_operation(
        project.common_dir,
        command="worktree.sync",
        target=target,
        extra={"plan": plan},
    )
    lock = acquire_operation_lock(
        project.common_dir, f"{target.key}-worktree", str(operation["operation_id"])
    )
    try:
        fresh = plan_sync(project, target)
        if fresh["primary_head"] != plan["primary_head"]:
            raise SystemExit("primary_branch_advanced: rerun sync plan")
        result = run_git(
            target.path,
            ("merge", "--no-edit", str(fresh["primary_head"])),
        )
        head = rev_parse(project.repo_root, target.branch)
        update_operation(
            project.common_dir,
            operation,
            status="completed",
            resume_allowed=False,
            merge_stdout=result.stdout,
            head=head,
        )
        return {
            **fresh,
            "status": "synced",
            "head": head,
            "operation_id": operation["operation_id"],
        }
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


def _workstream_status_in_target(target: WorktreeTarget) -> str | None:
    if not target.workstream_id:
        return None
    context_candidates = [
        target.path / "docs" / "ai" / "active" / "workstreams" / f"{target.workstream_id}.md",
        target.path / "docs-acf" / "ai" / "active" / "workstreams" / f"{target.workstream_id}.md",
    ]
    for path in context_candidates:
        if not path.is_file():
            continue
        metadata, _body, diagnostics = parse_front_matter(path.read_text(encoding="utf-8"))
        if diagnostics:
            raise SystemExit(f"workstream_schema_failed: {target.workstream_id}")
        return str(metadata.get("status") or "Unknown")
    raise SystemExit(f"workstream_not_found: {target.workstream_id} in {target.path}")


def plan_merge(project: GitProject, target: WorktreeTarget) -> dict[str, Any]:
    verification = verify_target(project, target)
    if not verification["ok"]:
        raise SystemExit(
            "worktree_verification_failed: " + ",".join(verification["issues"])
        )
    if not verification["clean"]:
        raise SystemExit(f"worktree_dirty: {target.path}")
    if current_branch(project.config.primary_checkout) != project.config.primary_branch:
        raise SystemExit(
            f"primary_branch_mismatch: expected {project.config.primary_branch}"
        )
    status = _workstream_status_in_target(target)
    if status is not None and status not in {"ReadyToMerge", "Merging"}:
        raise SystemExit(
            f"workstream_not_ready_to_merge: {target.workstream_id} status is {status}"
        )
    source_head = rev_parse(project.repo_root, target.branch)
    primary_head = rev_parse(project.repo_root, target.base_branch)
    primary_snapshot = capture_git_worktree_snapshot(
        project.config.primary_checkout,
        include_ignored=False,
    )
    if (
        project.config.primary_dirty_policy == "require_clean"
        and primary_snapshot["entries"]
    ):
        raise SystemExit(f"primary_checkout_dirty: {project.config.primary_checkout}")
    if primary_snapshot["sequencer"]["active"]:
        recommended_action = "wait_for_primary_git_operation"
    elif primary_snapshot["index_lock"]:
        recommended_action = "wait_for_primary_index_lock"
    else:
        recommended_action = "build_integration_candidate"
    if is_ancestor(project.repo_root, source_head, primary_head):
        return {
            "status": "already_merged",
            "merge_allowed": False,
            "source_head": source_head,
            "primary_head": primary_head,
            "workstream_status": status,
            "target": target_payload(target),
            "primary_snapshot": primary_snapshot,
            "candidate": None,
            "collisions": None,
            "recommended_action": "close_source_when_ready",
            "merge_preview": {"ok": True, "mode": "ancestor", "tree": primary_head},
        }
    candidate = build_candidate_preview(
        project.repo_root,
        primary_head=primary_head,
        source_head=source_head,
    )
    collisions = analyze_primary_collisions(
        project.config.primary_checkout,
        snapshot=primary_snapshot,
        candidate=candidate,
    )
    branch_conflict = bool(collisions["branch_conflict"])
    if branch_conflict:
        recommended_action = "create_integration_worktree_for_conflict_resolution"
    elif collisions["divergent_overlap_paths"]:
        recommended_action = "wait_or_resolve_primary_paths"
    return {
        "status": "conflict_resolution_required" if branch_conflict else "ready_to_merge",
        "merge_allowed": True,
        "source_head": source_head,
        "primary_head": primary_head,
        "workstream_status": status,
        "target": target_payload(target),
        "primary_snapshot": primary_snapshot,
        "candidate": candidate,
        "collisions": collisions,
        "recommended_action": recommended_action,
        "merge_preview": candidate["merge_preview"],
    }


def run_check_argv(cwd: Path, raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit("worktree_check_argv_invalid: expected JSON array") from exc
    if not isinstance(payload, list) or not payload or not all(
        isinstance(item, str) and item for item in payload
    ):
        raise SystemExit("worktree_check_argv_invalid: expected non-empty string array")
    completed = subprocess.run(
        payload,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )
    return {
        "argv": payload,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "ok": completed.returncode == 0,
    }


def apply_merge(
    project: GitProject,
    target: WorktreeTarget,
    *,
    message: str | None,
    pre_checks: Sequence[str],
    post_checks: Sequence[str],
    retry_policy: MergeRetryPolicy = DEFAULT_MERGE_RETRY_POLICY,
    artifact_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    from ai_context_framework.worktree_resilient_merge import execute_resilient_merge

    return execute_resilient_merge(
        project,
        target,
        plan_factory=lambda: plan_merge(project, target),
        check_runner=run_check_argv,
        message=message,
        pre_checks=pre_checks,
        post_checks=post_checks,
        artifact_overrides=artifact_overrides,
        retry_policy=retry_policy,
        operation_id=operation_id,
    )


def plan_close(project: GitProject, target: WorktreeTarget) -> dict[str, Any]:
    records = list_worktrees(project.repo_root)
    record = record_for_path(records, target.path)
    branch_present = branch_exists(project.repo_root, target.branch)
    path_exists = target.path.exists()
    if record and not is_clean(record.path):
        raise SystemExit(f"worktree_dirty: {record.path}")
    if branch_present and not is_ancestor(
        project.repo_root, target.branch, project.config.primary_branch
    ):
        raise SystemExit(f"branch_not_merged: {target.branch}")
    artifact_payload = load_artifact_plan(project.common_dir, target.key)
    if record and artifact_payload is None:
        artifact_payload = build_artifact_plan(
            target_key=target.key,
            source_head=rev_parse(project.repo_root, target.branch),
            source_path=target.path,
            cache_patterns=project.config.artifact_cache_patterns,
            discardable_patterns=project.config.artifact_discardable_patterns,
        )
    artifact_ready = (
        True
        if artifact_payload is None
        else artifact_handoff_ready_for_promotion(artifact_payload)
    )
    if record is None and not branch_present and not path_exists:
        status = "already_closed"
    elif not artifact_ready:
        status = "artifact_handoff_required"
    else:
        status = "ready_to_close"
    return {
        "status": status,
        "target": target_payload(target),
        "worktree_registered": record is not None,
        "branch_exists": branch_present,
        "path_exists": path_exists,
        "artifact_handoff_ready": artifact_ready,
        "artifact_handoff": artifact_payload,
    }


def apply_close(
    project: GitProject,
    target: WorktreeTarget,
    *,
    wait_timeout_seconds: int = 120,
    operation_id: str | None = None,
) -> dict[str, Any]:
    plan = plan_close(project, target)
    if plan["status"] == "already_closed":
        delete_registry(project.common_dir, target.key)
        return plan
    if plan["status"] == "artifact_handoff_required":
        raise SystemExit(f"artifact_handoff_required: {target.key}")
    if operation_id:
        try:
            operation = load_operation(project.common_dir, operation_id)
        except SystemExit:
            operation = create_operation(
                project.common_dir,
                command="worktree.close",
                target=target,
                extra={"plan": plan, "wait_timeout_seconds": wait_timeout_seconds},
                operation_id=operation_id,
            )
        else:
            if operation.get("command") != "worktree.close":
                raise SystemExit(f"operation_resume_unsupported: {operation.get('command')}")
            operation["plan"] = plan
            operation["wait_timeout_seconds"] = wait_timeout_seconds
            operation["resume_allowed"] = True
            update_operation(
                project.common_dir,
                operation,
                status="closing",
                error=None,
            )
    else:
        operation = create_operation(
            project.common_dir,
            command="worktree.close",
            target=target,
            extra={"plan": plan, "wait_timeout_seconds": wait_timeout_seconds},
        )
    policy = MergeRetryPolicy(
        lock_wait_timeout_seconds=max(0, wait_timeout_seconds),
        state_wait_timeout_seconds=max(0, wait_timeout_seconds),
        initial_delay_seconds=1.0,
        max_delay_seconds=30.0,
        jitter_ratio=0.10,
    )
    lease = None
    try:
        lease, waits = acquire_lock_with_wait(
            project.common_dir,
            key=f"{target.key}-lifecycle",
            operation_id=str(operation["operation_id"]),
            command="worktree.close",
            target_key=target.key,
            policy=policy,
            timeout_seconds=wait_timeout_seconds,
        )
        update_operation(
            project.common_dir,
            operation,
            lock_waits=waits,
            status="closing",
        )
        fresh = plan_close(project, target)
        if fresh["status"] == "artifact_handoff_required":
            raise SystemExit(f"artifact_handoff_required: {target.key}")
        worktree_result = _close_remove_worktree_with_retry(
            project,
            target,
            timeout_seconds=wait_timeout_seconds,
            policy=policy,
        )
        update_operation_step(
            project.common_dir,
            operation,
            "worktree_removed",
            "completed" if worktree_result["removed"] else "not_present",
            **worktree_result,
        )
        branch_result = _close_delete_branch_with_retry(
            project,
            target,
            timeout_seconds=wait_timeout_seconds,
            policy=policy,
        )
        update_operation_step(
            project.common_dir,
            operation,
            "branch_deleted",
            "completed" if branch_result["removed"] else "not_present",
            **branch_result,
        )
        delete_registry(project.common_dir, target.key)
        update_operation(
            project.common_dir,
            operation,
            status="completed",
            resume_allowed=False,
        )
        return {
            **fresh,
            "status": "closed",
            "operation_id": operation["operation_id"],
            "worktree_cleanup": worktree_result,
            "branch_cleanup": branch_result,
        }
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
        if lease is not None:
            release_owned_lock(lease)


def _close_remove_worktree_with_retry(
    project: GitProject,
    target: WorktreeTarget,
    *,
    timeout_seconds: int,
    policy: MergeRetryPolicy,
) -> dict[str, Any]:
    started = time.monotonic()
    attempt = 0
    errors: list[str] = []
    while True:
        record = record_for_path(list_worktrees(project.repo_root), target.path)
        if record is None:
            if target.path.exists():
                raise SystemExit(f"orphan_target_path: {target.path}")
            return {"removed": False, "attempts": attempt, "errors": errors}
        if not is_clean(record.path):
            raise SystemExit(f"worktree_dirty: {record.path}")
        result = run_git(
            project.repo_root,
            ("worktree", "remove", str(target.path)),
            check=False,
        )
        if result.returncode == 0:
            return {"removed": True, "attempts": attempt + 1, "errors": errors}
        errors.append(result.stderr.strip() or result.stdout.strip())
        elapsed = time.monotonic() - started
        if elapsed >= timeout_seconds:
            raise SystemExit(f"worktree_close_timeout: {target.path}")
        delay = min(
            retry_delay(policy, attempt, seed=f"close:{target.key}"),
            timeout_seconds - elapsed,
        )
        attempt += 1
        time.sleep(delay)


def _close_delete_branch_with_retry(
    project: GitProject,
    target: WorktreeTarget,
    *,
    timeout_seconds: int,
    policy: MergeRetryPolicy,
) -> dict[str, Any]:
    started = time.monotonic()
    attempt = 0
    errors: list[str] = []
    while True:
        if not branch_exists(project.repo_root, target.branch):
            return {"removed": False, "attempts": attempt, "errors": errors}
        if not is_ancestor(project.repo_root, target.branch, target.base_branch):
            raise SystemExit(f"branch_not_merged: {target.branch}")
        result = run_git(
            project.repo_root,
            ("branch", "-d", target.branch),
            check=False,
        )
        if result.returncode == 0:
            return {"removed": True, "attempts": attempt + 1, "errors": errors}
        errors.append(result.stderr.strip() or result.stdout.strip())
        elapsed = time.monotonic() - started
        if elapsed >= timeout_seconds:
            raise SystemExit(f"worktree_branch_delete_timeout: {target.branch}")
        delay = min(
            retry_delay(policy, attempt, seed=f"close-branch:{target.key}"),
            timeout_seconds - elapsed,
        )
        attempt += 1
        time.sleep(delay)


def resume_operation(project: GitProject, operation_id: str) -> dict[str, Any]:
    operation = load_operation(project.common_dir, operation_id)
    raw_target = operation.get("target")
    if not isinstance(raw_target, Mapping):
        raise SystemExit(f"operation_journal_invalid: {operation_id} has no target")
    target = WorktreeTarget(
        key=str(raw_target.get("key") or ""),
        branch=str(raw_target.get("branch") or ""),
        path=canonical_path(str(raw_target.get("path") or "")),
        base_branch=str(raw_target.get("base_branch") or project.config.primary_branch),
        base_commit=str(
            raw_target.get("base_commit")
            or rev_parse(project.repo_root, project.config.primary_branch)
        ),
        workstream_id=(
            str(raw_target.get("workstream_id"))
            if raw_target.get("workstream_id")
            else None
        ),
        kind=str(raw_target.get("kind")) if raw_target.get("kind") else None,
        slug=str(raw_target.get("slug")) if raw_target.get("slug") else None,
        reservation_path=(
            str(raw_target.get("reservation_path"))
            if raw_target.get("reservation_path")
            else None
        ),
        reservation_commit=(
            str(raw_target.get("reservation_commit"))
            if raw_target.get("reservation_commit")
            else None
        ),
    )
    command = str(operation.get("command") or "")
    if command == "worktree.create":
        return apply_create(project, target)
    if command == "worktree.close":
        return apply_close(
            project,
            target,
            wait_timeout_seconds=int(operation.get("wait_timeout_seconds") or 120),
            operation_id=operation_id,
        )
    if command == "worktree.merge" and operation.get("schema_version") == "acf.git_operation.v2":
        from ai_context_framework.worktree_resilient_merge import resume_resilient_merge

        return resume_resilient_merge(
            project,
            operation_id,
            target=target,
            plan_factory=lambda: plan_merge(project, target),
            check_runner=run_check_argv,
        )
    raise SystemExit(f"operation_resume_unsupported: {command}")
