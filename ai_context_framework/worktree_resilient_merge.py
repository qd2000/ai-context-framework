"""Resilient worktree merge executor using one temporary integration worktree."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ai_context_framework.git_support import (
    GitProject,
    WorktreeTarget,
    atomic_write_json,
    branch_exists,
    is_ancestor,
    is_clean,
    list_worktrees,
    load_operation,
    new_operation_id,
    operation_path,
    read_registry,
    record_for_path,
    rev_parse,
    run_git,
    safe_file_key,
    semantic_status,
    target_payload,
    update_operation,
    write_registry,
)
from ai_context_framework.worktree_artifacts import (
    build_artifact_plan,
    load_artifact_plan,
    migrate_artifacts,
    write_artifact_plan,
)
from ai_context_framework.worktree_collision import (
    analyze_primary_collisions,
    build_candidate_from_tip,
)
from ai_context_framework.worktree_merge_contracts import (
    DEFAULT_MERGE_RETRY_POLICY,
    MergeOperationState,
    MergeRetryPolicy,
    artifact_handoff_ready_for_promotion,
    build_merge_operation_v2,
    validate_merge_operation_v2,
)
from ai_context_framework.worktree_retry import (
    LockLease,
    acquire_lock_with_wait,
    refresh_lock,
    release_owned_lock,
    retry_delay,
)
from ai_context_framework.worktree_status import capture_git_worktree_snapshot, comparison_key


PlanFactory = Callable[[], dict[str, Any]]
CheckRunner = Callable[[Path, str], dict[str, Any]]


def execute_resilient_merge(
    project: GitProject,
    target: WorktreeTarget,
    *,
    plan_factory: PlanFactory,
    check_runner: CheckRunner,
    message: str | None,
    pre_checks: Sequence[str],
    post_checks: Sequence[str],
    artifact_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    retry_policy: MergeRetryPolicy = DEFAULT_MERGE_RETRY_POLICY,
    operation_id: str | None = None,
) -> dict[str, Any]:
    retry_policy.validate()
    plan = plan_factory()
    if plan["status"] == "already_merged":
        return plan
    source_head = str(plan["source_head"])
    primary_head = str(plan["primary_head"])
    op_id = operation_id or new_operation_id(f"worktree-merge-{target.key}")
    integration_branch, integration_path = integration_identity(project, target, op_id, 0)
    operation = build_merge_operation_v2(
        operation_id=op_id,
        target_key=target.key,
        source_branch=target.branch,
        source_path=str(target.path),
        source_head=source_head,
        primary_branch=target.base_branch,
        primary_checkout=str(project.config.primary_checkout),
        primary_head=primary_head,
        integration_branch=integration_branch,
        integration_path=str(integration_path),
        retry_policy=retry_policy,
    )
    operation["target"] = target_payload(target)
    operation["message"] = message
    operation["pre_checks_argv"] = list(pre_checks)
    operation["post_checks_argv"] = list(post_checks)
    operation["artifact_overrides"] = {
        path: dict(value) for path, value in (artifact_overrides or {}).items()
    }
    _save_operation(project, operation)

    target_lease: LockLease | None = None
    try:
        target_lease, waits = acquire_lock_with_wait(
            project.common_dir,
            key=f"{target.key}-lifecycle",
            operation_id=op_id,
            command="worktree.merge",
            target_key=target.key,
            policy=retry_policy,
            expected_primary_head=primary_head,
            expected_source_head=source_head,
        )
        operation["attempts"]["lock_waits"] += waits
        _set_state(project, operation, MergeOperationState.SOURCE_VERIFYING, "run_pre_checks")
        pre_results = [check_runner(target.path, raw) for raw in pre_checks]
        operation["checks"]["pre"] = pre_results
        if any(not row["ok"] for row in pre_results):
            return _pause(
                project,
                operation,
                state=MergeOperationState.MANUAL_ACTION_REQUIRED,
                reason="worktree_pre_merge_check_failed",
                next_action="fix_source_and_resume",
                status="pre_check_failed",
            )
        _set_state(project, operation, MergeOperationState.SOURCE_VERIFIED, "build_integration_candidate")
        return _build_validate_and_promote(
            project,
            target,
            operation=operation,
            plan_factory=plan_factory,
            check_runner=check_runner,
            post_checks=post_checks,
            artifact_overrides=artifact_overrides or {},
            retry_policy=retry_policy,
        )
    except BaseException as exc:
        if isinstance(exc, SystemExit) and str(exc).startswith("worktree_operation_lock_timeout"):
            return _pause(
                project,
                operation,
                state=MergeOperationState.PAUSED_RETRYABLE,
                reason="primary_or_target_lock_timeout",
                next_action="resume_merge_operation",
                status="paused_retryable",
            )
        operation["state"] = MergeOperationState.FAILED_TERMINAL.value
        operation["resume_allowed"] = True
        operation["pause_reason"] = f"{type(exc).__name__}: {exc}"
        operation["next_action"] = "inspect_operation_and_resume"
        _save_operation(project, operation)
        raise
    finally:
        if target_lease is not None:
            release_owned_lock(target_lease)


def resume_resilient_merge(
    project: GitProject,
    operation_id: str,
    *,
    target: WorktreeTarget,
    plan_factory: PlanFactory,
    check_runner: CheckRunner,
) -> dict[str, Any]:
    operation = load_operation(project.common_dir, operation_id)
    validate_merge_operation_v2(operation)
    if operation.get("target_key") != target.key:
        raise SystemExit("merge_operation_target_mismatch")
    state = MergeOperationState(str(operation["state"]))
    if state in {MergeOperationState.MERGED, MergeOperationState.READY_TO_CLOSE, MergeOperationState.CLOSED}:
        return {
            "status": "merged" if state is not MergeOperationState.CLOSED else "closed",
            "operation_id": operation_id,
            "merge_commit": operation.get("merge_commit"),
            "target": target_payload(target),
        }
    retry_policy = MergeRetryPolicy(**dict(operation["retry_policy"]))
    target_lease, waits = acquire_lock_with_wait(
        project.common_dir,
        key=f"{target.key}-lifecycle",
        operation_id=operation_id,
        command="worktree.merge.resume",
        target_key=target.key,
        policy=retry_policy,
        expected_primary_head=str(operation["primary"]["head"]),
        expected_source_head=str(operation["source"]["head"]),
    )
    operation["attempts"]["lock_waits"] += waits
    try:
        integration_path = Path(str(operation["integration"]["path"]))
        if not integration_path.is_dir():
            raise SystemExit("integration_worktree_missing")
        if not is_clean(integration_path):
            return _pause(
                project,
                operation,
                state=(
                    MergeOperationState.CONFLICT_RESOLUTION_REQUIRED
                    if state is MergeOperationState.CONFLICT_RESOLUTION_REQUIRED
                    else MergeOperationState.MANUAL_ACTION_REQUIRED
                ),
                reason=(
                    "integration_conflicts_not_resolved"
                    if state is MergeOperationState.CONFLICT_RESOLUTION_REQUIRED
                    else "integration_worktree_dirty"
                ),
                next_action="resolve and commit integration changes, then resume",
                status=(
                    "conflict_resolution_required"
                    if state is MergeOperationState.CONFLICT_RESOLUTION_REQUIRED
                    else "manual_action_required"
                ),
            )
        tip = rev_parse(integration_path, "HEAD")
        source_head = str(operation["source"]["head"])
        if not is_ancestor(project.repo_root, source_head, tip):
            raise SystemExit("integration_tip_missing_source_head")
        operation["integration"]["tip"] = tip
        _set_state(project, operation, MergeOperationState.CANDIDATE_READY, "validate_candidate")
        for _attempt in range(retry_policy.max_replans + 1):
            result = _continue_existing_candidate(
                project,
                target,
                operation=operation,
                plan_factory=plan_factory,
                check_runner=check_runner,
                post_checks=list(operation.get("post_checks_argv") or []),
                retry_policy=retry_policy,
            )
            if result.get("status") != "replan_required":
                return result
            current_primary = rev_parse(project.repo_root, target.base_branch)
            if is_ancestor(project.repo_root, current_primary, rev_parse(integration_path, "HEAD")):
                operation["integration"]["base_head"] = current_primary
                continue
            merged_primary = run_git(
                integration_path,
                (
                    "merge",
                    "--no-ff",
                    current_primary,
                    "-m",
                    f"Integrate latest {target.base_branch} for {target.key}",
                ),
                check=False,
            )
            operation["attempts"]["replans"] += 1
            if merged_primary.returncode != 0:
                conflicts = _unmerged_paths(integration_path)
                operation["integration"]["conflicts"] = conflicts
                return _pause(
                    project,
                    operation,
                    state=MergeOperationState.CONFLICT_RESOLUTION_REQUIRED,
                    reason="latest_primary_merge_conflicts",
                    next_action=f"resolve conflicts in {integration_path} and resume",
                    status="conflict_resolution_required",
                    extra={"integration_path": str(integration_path), "conflicts": conflicts},
                )
            operation["integration"]["base_head"] = current_primary
            operation["integration"]["tip"] = rev_parse(integration_path, "HEAD")
            _save_operation(project, operation)
        return _pause(
            project,
            operation,
            state=MergeOperationState.PAUSED_RETRYABLE,
            reason="primary_churn",
            next_action="resume_merge_operation",
            status="paused_retryable",
        )
    finally:
        release_owned_lock(target_lease)


def integration_identity(
    project: GitProject,
    target: WorktreeTarget,
    operation_id: str,
    replan_count: int,
) -> tuple[str, Path]:
    suffix = safe_file_key(operation_id)[-20:].lower()
    target_name = safe_file_key(target.key).lower()
    attempt = f"-r{replan_count}" if replan_count else ""
    branch = f"{project.config.branch_prefix}/integration-{target_name}-{suffix}{attempt}"
    path = project.config.worktree_root / ".acf-integration" / f"{safe_file_key(operation_id)}{attempt}"
    return branch, path


def cleanup_integration(
    project: GitProject,
    *,
    path: Path,
    branch: str,
    expected_tip: str | None,
) -> dict[str, Any]:
    result = {"path": str(path), "branch": branch, "worktree_removed": False, "branch_removed": False}
    record = record_for_path(list_worktrees(project.repo_root), path)
    if record is not None:
        status = semantic_status(path)
        if not status["clean"]:
            result["status"] = "dirty_retained"
            return result
        stat_only_paths = [str(value) for value in status["stat_only_paths"]]
        remove_args: tuple[str, ...] = (
            "worktree",
            "remove",
            *(("--force",) if stat_only_paths else ()),
            str(path),
        )
        removed = run_git(project.repo_root, remove_args, check=False)
        if removed.returncode != 0:
            result["status"] = "worktree_remove_failed"
            result["stderr"] = removed.stderr
            return result
        result["worktree_removed"] = True
        result["semantic_force"] = bool(stat_only_paths)
        result["stat_only_paths"] = stat_only_paths
    elif not path.exists():
        result["worktree_removed"] = True
    if branch_exists(project.repo_root, branch):
        ref = f"refs/heads/{branch}"
        args = ("update-ref", "-d", ref, expected_tip) if expected_tip else ("update-ref", "-d", ref)
        deleted = run_git(project.repo_root, args, check=False)
        if deleted.returncode == 0:
            result["branch_removed"] = True
        else:
            result["status"] = "branch_remove_failed"
            result["stderr"] = deleted.stderr
            return result
    else:
        result["branch_removed"] = True
    result["status"] = "cleaned"
    return result


def _build_validate_and_promote(
    project: GitProject,
    target: WorktreeTarget,
    *,
    operation: dict[str, Any],
    plan_factory: PlanFactory,
    check_runner: CheckRunner,
    post_checks: Sequence[str],
    artifact_overrides: Mapping[str, Mapping[str, Any]],
    retry_policy: MergeRetryPolicy,
) -> dict[str, Any]:
    for replan_count in range(retry_policy.max_replans + 1):
        operation["attempts"]["replans"] = replan_count
        fresh = plan_factory()
        if fresh["status"] == "already_merged":
            operation["merge_commit"] = fresh["primary_head"]
            _set_state(project, operation, MergeOperationState.MERGED, "close_source_when_ready")
            return {**fresh, "operation_id": operation["operation_id"]}
        source_head = str(fresh["source_head"])
        if source_head != str(operation["source"]["head"]):
            operation["source"]["head"] = source_head
            pre_results = [check_runner(target.path, raw) for raw in operation.get("pre_checks_argv", [])]
            operation["checks"]["pre"] = pre_results
            if any(not row["ok"] for row in pre_results):
                return _pause(
                    project,
                    operation,
                    state=MergeOperationState.MANUAL_ACTION_REQUIRED,
                    reason="worktree_pre_merge_check_failed_after_source_advance",
                    next_action="fix_source_and_resume",
                    status="pre_check_failed",
                )
        primary_head = str(fresh["primary_head"])
        operation["primary"]["head"] = primary_head
        branch, path = integration_identity(project, target, str(operation["operation_id"]), replan_count)
        operation["integration"].update(
            {"branch": branch, "path": str(path), "base_head": primary_head, "tip": None, "conflicts": []}
        )
        _set_state(project, operation, MergeOperationState.INTEGRATION_CREATING, "create_integration_worktree")
        _ensure_clean_integration_slot(project, path=path, branch=branch)
        path.parent.mkdir(parents=True, exist_ok=True)
        created = run_git(
            project.repo_root,
            ("worktree", "add", "-b", branch, str(path), primary_head),
            check=False,
        )
        if created.returncode != 0:
            raise SystemExit(f"integration_worktree_create_failed: {created.stderr.strip()}")
        _set_state(project, operation, MergeOperationState.INTEGRATION_READY, "merge_source_in_integration")
        merge_message = operation.get("message") or _default_merge_message(target)
        merged = run_git(
            path,
            ("merge", "--no-ff", source_head, "-m", str(merge_message)),
            check=False,
        )
        if merged.returncode != 0:
            current_primary = rev_parse(project.repo_root, target.base_branch)
            if (
                current_primary != primary_head
                and operation["attempts"]["conflict_replans"] < retry_policy.conflict_replans
            ):
                operation["attempts"]["conflict_replans"] += 1
                run_git(path, ("merge", "--abort"), check=False)
                cleanup = cleanup_integration(
                    project,
                    path=path,
                    branch=branch,
                    expected_tip=rev_parse(path, "HEAD"),
                )
                operation.setdefault("cleanup", []).append(cleanup)
                _save_operation(project, operation)
                continue
            conflicts = _unmerged_paths(path)
            operation["integration"]["conflicts"] = conflicts
            operation["integration"]["merge_stderr"] = merged.stderr
            return _pause(
                project,
                operation,
                state=MergeOperationState.CONFLICT_RESOLUTION_REQUIRED,
                reason="merge_conflicts_detected",
                next_action=f"resolve conflicts in {path} and resume operation",
                status="conflict_resolution_required",
                extra={"integration_path": str(path), "conflicts": conflicts},
            )
        tip = rev_parse(path, "HEAD")
        operation["integration"]["tip"] = tip
        _set_state(project, operation, MergeOperationState.CANDIDATE_READY, "validate_candidate")
        result = _continue_existing_candidate(
            project,
            target,
            operation=operation,
            plan_factory=plan_factory,
            check_runner=check_runner,
            post_checks=post_checks,
            retry_policy=retry_policy,
            artifact_overrides=artifact_overrides,
        )
        if result.get("status") == "replan_required":
            cleanup = cleanup_integration(
                project,
                path=path,
                branch=branch,
                expected_tip=tip,
            )
            operation.setdefault("cleanup", []).append(cleanup)
            _save_operation(project, operation)
            continue
        return result
    return _pause(
        project,
        operation,
        state=MergeOperationState.PAUSED_RETRYABLE,
        reason="primary_churn",
        next_action="resume_merge_operation",
        status="paused_retryable",
    )


def _continue_existing_candidate(
    project: GitProject,
    target: WorktreeTarget,
    *,
    operation: dict[str, Any],
    plan_factory: PlanFactory,
    check_runner: CheckRunner,
    post_checks: Sequence[str],
    retry_policy: MergeRetryPolicy,
    artifact_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    path = Path(str(operation["integration"]["path"]))
    branch = str(operation["integration"]["branch"])
    tip = str(operation["integration"].get("tip") or rev_parse(path, "HEAD"))
    source_head = str(operation["source"]["head"])
    _set_state(project, operation, MergeOperationState.CANDIDATE_VALIDATING, "run_post_checks")
    post_results = [check_runner(path, raw) for raw in post_checks]
    operation["checks"]["post"] = post_results
    if any(not row["ok"] for row in post_results):
        return _pause(
            project,
            operation,
            state=MergeOperationState.MANUAL_ACTION_REQUIRED,
            reason="worktree_post_merge_check_failed",
            next_action=f"repair candidate in {path} and resume",
            status="candidate_checks_failed",
            extra={"integration_path": str(path), "post_checks": post_results},
        )
    _set_state(project, operation, MergeOperationState.CANDIDATE_VALIDATED, "plan_and_migrate_artifacts")
    manifest = load_artifact_plan(project.common_dir, target.key)
    if manifest is None or manifest.get("source_head") != source_head:
        manifest = build_artifact_plan(
            target_key=target.key,
            source_head=source_head,
            source_path=target.path,
            overrides=artifact_overrides or operation.get("artifact_overrides") or {},
            cache_patterns=project.config.artifact_cache_patterns,
            discardable_patterns=project.config.artifact_discardable_patterns,
        )
        write_artifact_plan(project.common_dir, manifest)
    operation["artifact_handoff"] = {
        "status": manifest.get("status"),
        "manifest_path": str(project.common_dir / "acf" / "artifacts" / f"{safe_file_key(target.key)}.json"),
    }
    _set_state(project, operation, MergeOperationState.ARTIFACTS_MIGRATING, "migrate_artifacts")
    artifact_result = migrate_artifacts(
        project.common_dir,
        manifest,
        source_path=target.path,
    )
    operation["artifact_handoff"].update(
        {"status": artifact_result["status"], "promotion_ready": artifact_result["promotion_ready"]}
    )
    if not artifact_result["promotion_ready"]:
        return _pause(
            project,
            operation,
            state=MergeOperationState.MANUAL_ACTION_REQUIRED,
            reason="artifact_handoff_incomplete",
            next_action="classify or repair artifacts, then resume",
            status="artifact_handoff_required",
            extra={"artifact_handoff": artifact_result},
        )
    _set_state(project, operation, MergeOperationState.ARTIFACTS_VERIFIED, "wait_for_safe_promotion")
    return _promote_candidate(
        project,
        target,
        operation=operation,
        plan_factory=plan_factory,
        retry_policy=retry_policy,
        candidate_tip=tip,
        integration_path=path,
        integration_branch=branch,
    )


def _promote_candidate(
    project: GitProject,
    target: WorktreeTarget,
    *,
    operation: dict[str, Any],
    plan_factory: PlanFactory,
    retry_policy: MergeRetryPolicy,
    candidate_tip: str,
    integration_path: Path,
    integration_branch: str,
) -> dict[str, Any]:
    _set_state(project, operation, MergeOperationState.WAITING_PROMOTION, "wait_for_primary_window")
    window = _wait_for_primary_window(
        project,
        target,
        operation=operation,
        retry_policy=retry_policy,
        candidate_tip=candidate_tip,
    )
    if window["status"] == "replan_required":
        return window
    if window["status"] != "ready":
        return _pause(
            project,
            operation,
            state=MergeOperationState.PAUSED_RETRYABLE,
            reason=str(window["reason"]),
            next_action="wait for primary state to stabilize and resume",
            status="paused_retryable",
            extra={"primary_window": window},
        )
    _set_state(project, operation, MergeOperationState.WAITING_PROMOTION, "acquire_primary_promotion_lock")
    lease: LockLease | None = None
    try:
        lease, waits = acquire_lock_with_wait(
            project.common_dir,
            key="primary-promotion",
            operation_id=str(operation["operation_id"]),
            command="worktree.merge.promote",
            target_key=target.key,
            policy=retry_policy,
            expected_primary_head=str(operation["primary"]["head"]),
            expected_source_head=str(operation["source"]["head"]),
        )
        operation["attempts"]["lock_waits"] += waits
        fresh = plan_factory()
        current_primary = str(fresh["primary_head"])
        if current_primary != str(operation["integration"]["base_head"]):
            return {"status": "replan_required", "reason": "primary_head_advanced"}
        before = capture_git_worktree_snapshot(
            project.config.primary_checkout,
            include_ignored=False,
        )
        candidate = build_candidate_from_tip(
            project.repo_root,
            primary_head=current_primary,
            candidate_tip=candidate_tip,
            source_head=str(operation["source"]["head"]),
        )
        collisions = analyze_primary_collisions(
            project.config.primary_checkout,
            snapshot=before,
            candidate=candidate,
        )
        operation["primary_protection"]["before"] = before
        operation["primary_protection"]["identical_overlap_paths"] = collisions[
            "identical_overlap_paths"
        ]
        operation["primary_protection"]["divergent_overlap_paths"] = collisions[
            "divergent_overlap_paths"
        ]
        if before["sequencer"]["active"] or before["index_lock"] or not collisions["allowed"]:
            return {
                "status": "replan_required",
                "reason": "primary_window_changed_after_lock",
            }
        quarantine = _quarantine_identical_untracked(
            project,
            operation_id=str(operation["operation_id"]),
            snapshot=before,
            identical_paths=collisions["identical_overlap_paths"],
        )
        operation["primary_protection"]["quarantine"] = quarantine
        _save_operation(project, operation)
        refresh_lock(
            lease,
            state=MergeOperationState.PROMOTING.value,
            expected_primary_head=current_primary,
            expected_source_head=str(operation["source"]["head"]),
        )
        _set_state(project, operation, MergeOperationState.PROMOTING, "fast_forward_primary")
        promoted = run_git(
            project.config.primary_checkout,
            ("merge", "--ff-only", candidate_tip),
            check=False,
        )
        if promoted.returncode != 0:
            _restore_quarantine(project, quarantine)
            current = rev_parse(project.repo_root, target.base_branch)
            if current != current_primary:
                return {"status": "replan_required", "reason": "primary_head_advanced_during_promotion"}
            return _pause(
                project,
                operation,
                state=MergeOperationState.PAUSED_RETRYABLE,
                reason="primary_fast_forward_refused",
                next_action="inspect primary local state and resume",
                status="paused_retryable",
                extra={"stderr": promoted.stderr, "stdout": promoted.stdout},
            )
        merge_commit = rev_parse(project.repo_root, target.base_branch)
        if merge_commit != candidate_tip:
            raise SystemExit("primary_promotion_identity_mismatch")
        after = capture_git_worktree_snapshot(
            project.config.primary_checkout,
            include_ignored=False,
        )
        protection = verify_primary_local_protection(
            before,
            after,
            candidate_paths=candidate["changed_paths"],
            identical_paths=collisions["identical_overlap_paths"],
        )
        operation["primary_protection"]["after"] = after
        operation["primary_protection"]["verification"] = protection
        if not protection["ok"]:
            operation["merge_commit"] = merge_commit
            _set_state(project, operation, MergeOperationState.POST_VERIFY, "repair_primary_protection_failure")
            return _pause(
                project,
                operation,
                state=MergeOperationState.MANUAL_ACTION_REQUIRED,
                reason="primary_local_state_changed_during_promotion",
                next_action="inspect protected local paths; do not reset main",
                status="merged_post_verify_failed",
                extra={"merge_commit": merge_commit, "protection": protection},
            )
        _discard_verified_quarantine(project, quarantine)
        operation["merge_commit"] = merge_commit
        _set_state(project, operation, MergeOperationState.PROMOTED, "update_registry")
        registry = read_registry(project.common_dir, target.key)
        if registry:
            row = dict(registry)
            row.update({"state": "merged", "merge_commit": merge_commit})
            write_registry(project.common_dir, target.key, row)
        cleanup = cleanup_integration(
            project,
            path=integration_path,
            branch=integration_branch,
            expected_tip=candidate_tip,
        )
        operation["cleanup"] = [cleanup]
        _set_state(project, operation, MergeOperationState.MERGED, "close_source_when_ready")
        return {
            "status": "merged",
            "merge_commit": merge_commit,
            "operation_id": operation["operation_id"],
            "target": target_payload(target),
            "candidate": candidate,
            "collisions": collisions,
            "primary_protection": protection,
            "artifact_handoff": operation["artifact_handoff"],
            "cleanup": cleanup,
            "pre_checks": operation["checks"]["pre"],
            "post_checks": operation["checks"]["post"],
        }
    finally:
        if lease is not None:
            release_owned_lock(lease)


def _wait_for_primary_window(
    project: GitProject,
    target: WorktreeTarget,
    *,
    operation: dict[str, Any],
    retry_policy: MergeRetryPolicy,
    candidate_tip: str,
) -> dict[str, Any]:
    started = time.monotonic()
    attempt = 0
    last_reason = "primary_not_stable"
    last_snapshot: dict[str, Any] | None = None
    last_collisions: dict[str, Any] | None = None
    while True:
        current_primary = rev_parse(project.repo_root, target.base_branch)
        if current_primary != str(operation["integration"]["base_head"]):
            return {"status": "replan_required", "reason": "primary_head_advanced"}
        snapshot = capture_git_worktree_snapshot(
            project.config.primary_checkout,
            include_ignored=False,
        )
        candidate = build_candidate_from_tip(
            project.repo_root,
            primary_head=current_primary,
            candidate_tip=candidate_tip,
            source_head=str(operation["source"]["head"]),
        )
        collisions = analyze_primary_collisions(
            project.config.primary_checkout,
            snapshot=snapshot,
            candidate=candidate,
        )
        last_snapshot = snapshot
        last_collisions = collisions
        if snapshot["sequencer"]["active"]:
            last_reason = "primary_git_operation_active"
        elif snapshot["index_lock"]:
            last_reason = "primary_index_lock_active"
        elif not collisions["allowed"]:
            last_reason = "primary_path_collision"
        else:
            operation["attempts"]["state_waits"] += attempt
            _save_operation(project, operation)
            return {
                "status": "ready",
                "snapshot": snapshot,
                "candidate": candidate,
                "collisions": collisions,
                "wait_attempts": attempt,
            }
        elapsed = time.monotonic() - started
        if elapsed >= retry_policy.state_wait_timeout_seconds:
            operation["attempts"]["state_waits"] += attempt
            _save_operation(project, operation)
            return {
                "status": "timeout",
                "reason": last_reason,
                "snapshot": last_snapshot,
                "collisions": last_collisions,
                "wait_attempts": attempt,
            }
        delay = min(
            retry_delay(retry_policy, attempt, seed=str(operation["operation_id"])),
            retry_policy.state_wait_timeout_seconds - elapsed,
        )
        attempt += 1
        time.sleep(delay)


def _quarantine_identical_untracked(
    project: GitProject,
    *,
    operation_id: str,
    snapshot: Mapping[str, Any],
    identical_paths: Sequence[str],
) -> list[dict[str, Any]]:
    identical_keys = {comparison_key(path) for path in identical_paths}
    untracked_or_ignored: dict[str, str] = {}
    for row in snapshot.get("entries", []):
        if not isinstance(row, Mapping):
            continue
        path = str(row.get("path") or "")
        key = comparison_key(path)
        if key in identical_keys and row.get("record_type") in {"untracked", "ignored"}:
            untracked_or_ignored[key] = path
    if not untracked_or_ignored:
        return []
    root = project.common_dir / "acf" / "quarantine" / safe_file_key(operation_id)
    records: list[dict[str, Any]] = []
    for key, relative_path in sorted(untracked_or_ignored.items()):
        source = project.config.primary_checkout / Path(relative_path)
        if not source.exists() and not source.is_symlink():
            continue
        destination = root / Path(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
        records.append(
            {
                "comparison_key": key,
                "relative_path": relative_path,
                "source": str(source),
                "quarantine": str(destination),
                "state": "quarantined",
            }
        )
    return records


def _restore_quarantine(project: GitProject, records: Sequence[Mapping[str, Any]]) -> None:
    for record in reversed(list(records)):
        quarantine = Path(str(record.get("quarantine") or ""))
        source = Path(str(record.get("source") or ""))
        if not quarantine.exists() and not quarantine.is_symlink():
            continue
        if source.exists() or source.is_symlink():
            raise SystemExit(f"quarantine_restore_collision: {source}")
        source.parent.mkdir(parents=True, exist_ok=True)
        os.replace(quarantine, source)
    _cleanup_quarantine_root(project, records)


def _discard_verified_quarantine(
    project: GitProject,
    records: Sequence[Mapping[str, Any]],
) -> None:
    for record in records:
        quarantine = Path(str(record.get("quarantine") or ""))
        if quarantine.is_dir() and not quarantine.is_symlink():
            shutil.rmtree(quarantine)
        else:
            try:
                quarantine.unlink()
            except FileNotFoundError:
                pass
    _cleanup_quarantine_root(project, records)


def _cleanup_quarantine_root(
    project: GitProject,
    records: Sequence[Mapping[str, Any]],
) -> None:
    if not records:
        return
    root = project.common_dir / "acf" / "quarantine"
    for record in records:
        path = Path(str(record.get("quarantine") or "")).parent
        while path != root.parent and path.is_relative_to(root):
            try:
                path.rmdir()
            except OSError:
                break
            if path == root:
                break
            path = path.parent


def verify_primary_local_protection(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    candidate_paths: Sequence[str],
    identical_paths: Sequence[str],
) -> dict[str, Any]:
    candidate_keys = {comparison_key(path) for path in candidate_paths}
    identical_keys = {comparison_key(path) for path in identical_paths}
    before_entries = _entries_by_key(before)
    after_entries = _entries_by_key(after)
    before_states = _states_by_key(before)
    after_states = _states_by_key(after)
    changed: list[str] = []
    protected = sorted(
        (set(before_entries) | set(before_states)) - candidate_keys,
    )
    for key in protected:
        if before_entries.get(key) != after_entries.get(key) or before_states.get(key) != after_states.get(key):
            changed.append(key)
    unresolved_identical: list[str] = []
    for key in identical_keys:
        entries = after_entries.get(key, [])
        if entries:
            unresolved_identical.append(key)
    return {
        "ok": not changed and not unresolved_identical,
        "protected_path_keys": protected,
        "changed_protected_path_keys": changed,
        "unresolved_identical_path_keys": unresolved_identical,
    }


def _entries_by_key(snapshot: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in snapshot.get("entries", []):
        if not isinstance(row, Mapping):
            continue
        key = str(row.get("comparison_key") or comparison_key(str(row.get("path") or "")))
        normalized = {
            name: row.get(name)
            for name in (
                "record_type",
                "path",
                "original_path",
                "index_status",
                "worktree_status",
                "mode_index",
                "oid_index",
            )
        }
        result.setdefault(key, []).append(normalized)
    for rows in result.values():
        rows.sort(key=lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False))
    return result


def _states_by_key(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("comparison_key")): {
            name: row.get(name)
            for name in ("path", "kind", "size", "mode", "sha256", "link_target")
        }
        for row in snapshot.get("path_states", [])
        if isinstance(row, Mapping) and row.get("comparison_key")
    }


def _ensure_clean_integration_slot(project: GitProject, *, path: Path, branch: str) -> None:
    record = record_for_path(list_worktrees(project.repo_root), path)
    if record is not None or path.exists() or branch_exists(project.repo_root, branch):
        tip = rev_parse(project.repo_root, branch) if branch_exists(project.repo_root, branch) else None
        cleanup = cleanup_integration(project, path=path, branch=branch, expected_tip=tip)
        if cleanup["status"] != "cleaned":
            raise SystemExit(f"integration_slot_not_clean: {cleanup['status']}")


def _unmerged_paths(path: Path) -> list[str]:
    output = run_git(path, ("diff", "--name-only", "--diff-filter=U", "-z"), check=False).stdout
    return sorted({value for value in output.split("\0") if value}, key=comparison_key)


def _default_merge_message(target: WorktreeTarget) -> str:
    if target.workstream_id:
        return f"Merge {target.workstream_id} worktree"
    return f"Merge {target.kind or 'worktree'} {target.slug or target.branch}"


def _pause(
    project: GitProject,
    operation: dict[str, Any],
    *,
    state: MergeOperationState,
    reason: str,
    next_action: str,
    status: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    operation["state"] = state.value
    operation["pause_reason"] = reason
    operation["next_action"] = next_action
    operation["resume_allowed"] = True
    _save_operation(project, operation)
    return {
        "status": status,
        "operation_id": operation["operation_id"],
        "pause_reason": reason,
        "next_action": next_action,
        "resume_allowed": True,
        "target": operation.get("target"),
        **dict(extra or {}),
    }


def _set_state(
    project: GitProject,
    operation: dict[str, Any],
    state: MergeOperationState,
    next_action: str,
) -> None:
    operation["state"] = state.value
    operation["next_action"] = next_action
    operation["pause_reason"] = None
    _save_operation(project, operation)


def _save_operation(project: GitProject, operation: dict[str, Any]) -> None:
    from ai_context_framework.worktree_merge_contracts import utc_now

    operation["updated_at"] = utc_now()
    validate_merge_operation_v2(operation)
    atomic_write_json(operation_path(project.common_dir, str(operation["operation_id"])), operation)
