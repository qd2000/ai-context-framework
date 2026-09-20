"""CLI handlers for optional Git worktree lifecycle management."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_context_framework.git_support import (
    ALLOWED_NON_WORKSTREAM_KINDS,
    discover_git_project,
    target_payload,
)
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.validators.checks import validate_workstream_id
from ai_context_framework.worktree_artifacts import (
    build_artifact_plan,
    load_artifact_plan,
    migrate_artifacts,
    parse_artifact_overrides,
    write_artifact_plan,
)
from ai_context_framework.worktree_merge_contracts import MergeRetryPolicy
from ai_context_framework.worktree_service import (
    apply_close,
    apply_create,
    apply_merge,
    apply_retire,
    apply_sync,
    attach_workstream,
    audit_project,
    list_payload,
    plan_close,
    plan_create,
    plan_merge,
    plan_retire,
    plan_sync,
    resolve_non_workstream_target,
    resolve_workstream_target,
    resume_operation,
    target_from_registry,
    verify_target,
)


def _emit(args: argparse.Namespace, command: str, payload: dict[str, Any], *, exit_code: int = 0) -> int:
    result = {
        "command": command,
        "ok": exit_code == 0 and bool(payload.get("ok", True)),
        "error_code": None,
        "next_actions": [],
        **payload,
    }
    set_result_payload(args, result)
    if json_enabled(args):
        print_json(result)
    else:
        status = result.get("status")
        if status:
            print(f"status: {status}")
        target = result.get("target")
        if isinstance(target, dict):
            if target.get("branch"):
                print(f"branch: {target['branch']}")
            if target.get("path"):
                print(f"worktree: {target['path']}")
        if command == "worktree list":
            for row in result.get("worktrees", []):
                if isinstance(row, dict):
                    print(
                        f"{row.get('path')}\t{row.get('branch') or 'detached'}\t"
                        f"{'clean' if row.get('clean') else 'dirty' if row.get('clean') is False else 'unknown'}"
                    )
        if command == "worktree audit":
            for finding in result.get("findings", []):
                if isinstance(finding, dict):
                    print(f"{finding.get('severity')}\t{finding.get('code')}\t{finding.get('path', '')}")
    return exit_code


def _project(args: argparse.Namespace):
    return discover_git_project(getattr(args, "path", None))


def _create_target(args: argparse.Namespace, project):
    workstream_id = getattr(args, "workstream", None)
    kind = getattr(args, "kind", None)
    slug = getattr(args, "slug", None)
    if workstream_id:
        target, info = resolve_workstream_target(
            project,
            workstream_id,
            slug_override=slug,
        )
        return target, info
    if kind:
        if not slug:
            raise SystemExit("worktree_slug_required: --kind requires --slug")
        return resolve_non_workstream_target(project, kind, slug), None
    raise SystemExit("worktree_target_required: pass --workstream or --kind")


def _existing_target(args: argparse.Namespace, project):
    workstream = getattr(args, "workstream", None)
    target = getattr(args, "target", None)
    return target_from_registry(
        project,
        workstream_id=workstream,
        target_path=target,
    )


def worktree_create_command(args: argparse.Namespace) -> int:
    project = _project(args)
    target, workstream_info = _create_target(args, project)
    activation_actions = (
        [
            f"Activate the Workstream before execution: acf workstream set {workstream_info.workstream_id} --status Active"
        ]
        if workstream_info is not None and workstream_info.status == "Open"
        else []
    )
    plan = plan_create(project, target)
    if not args.apply:
        return _emit(
            args,
            "worktree create",
            {
                **plan,
                "applied": False,
                "ok": True,
                "next_actions": [
                    "Review the plan and rerun with --apply to create or resume the worktree.",
                    *activation_actions,
                ],
            },
        )
    result = apply_create(
        project,
        target,
        operation_id=getattr(args, "operation_id", None),
    )
    return _emit(
        args,
        "worktree create",
        {**result, "applied": True, "ok": True, "next_actions": activation_actions},
    )


def worktree_attach_command(args: argparse.Namespace) -> int:
    project = _project(args)
    result = attach_workstream(
        project,
        workstream_id=args.workstream,
        target_path=args.target,
        slug_override=args.slug,
        apply=args.apply,
    )
    return _emit(
        args,
        "worktree attach",
        {
            **result,
            "applied": bool(args.apply),
            "ok": True,
            "next_actions": []
            if args.apply
            else ["Review the attachment plan and rerun with --apply."],
        },
    )


def worktree_verify_command(args: argparse.Namespace) -> int:
    project = _project(args)
    if args.workstream and args.slug:
        target, _ = resolve_workstream_target(
            project, args.workstream, slug_override=args.slug
        )
    else:
        target = _existing_target(args, project)
    result = verify_target(project, target)
    return _emit(
        args,
        "worktree verify",
        {**result, "status": "verified" if result["ok"] else "invalid"},
        exit_code=0 if result["ok"] else 1,
    )


def worktree_list_command(args: argparse.Namespace) -> int:
    project = _project(args)
    return _emit(
        args,
        "worktree list",
        {**list_payload(project), "status": "listed", "ok": True},
    )


def worktree_audit_command(args: argparse.Namespace) -> int:
    project = _project(args)
    result = audit_project(project)
    return _emit(
        args,
        "worktree audit",
        {**result, "status": "passed" if result["ok"] else "findings"},
        exit_code=0 if result["ok"] else 1,
    )


def worktree_sync_command(args: argparse.Namespace) -> int:
    project = _project(args)
    target = _existing_target(args, project)
    plan = plan_sync(project, target)
    if not args.apply:
        return _emit(
            args,
            "worktree sync",
            {
                **plan,
                "applied": False,
                "ok": True,
                "next_actions": []
                if plan["status"] == "already_up_to_date"
                else ["Review the merge preview and rerun with --apply."],
            },
        )
    result = apply_sync(project, target)
    return _emit(
        args,
        "worktree sync",
        {**result, "applied": True, "ok": True},
    )


def worktree_merge_plan_command(args: argparse.Namespace) -> int:
    project = _project(args)
    target = _existing_target(args, project)
    result = plan_merge(project, target)
    return _emit(
        args,
        "worktree merge-plan",
        {**result, "ok": True},
    )


def worktree_merge_command(args: argparse.Namespace) -> int:
    project = _project(args)
    target = _existing_target(args, project)
    plan = plan_merge(project, target)
    if not args.apply:
        return _emit(
            args,
            "worktree merge",
            {
                **plan,
                "applied": False,
                "ok": True,
                "next_actions": []
                if plan["status"] == "already_merged"
                else ["Review the integration-worktree merge plan and rerun with --apply."],
            },
        )
    policy = MergeRetryPolicy(
        max_replans=args.max_replans,
        conflict_replans=args.conflict_replans,
        lock_wait_timeout_seconds=args.lock_wait_timeout,
        state_wait_timeout_seconds=args.wait_timeout,
        initial_delay_seconds=args.initial_delay,
        max_delay_seconds=args.max_delay,
        jitter_ratio=args.jitter_ratio,
    )
    overrides = parse_artifact_overrides(
        required=args.artifact_required or [],
        references=args.artifact_reference or [],
        caches=args.artifact_cache or [],
        discardable=args.artifact_discardable or [],
    )
    result = apply_merge(
        project,
        target,
        message=args.message,
        pre_checks=args.pre_check_json or [],
        post_checks=args.post_check_json or [],
        retry_policy=policy,
        artifact_overrides=overrides,
        operation_id=args.operation_id,
    )
    success_statuses = {"merged", "already_merged"}
    exit_code = 0 if result["status"] in success_statuses else 1
    error_by_status = {
        "pre_check_failed": "worktree_pre_merge_check_failed",
        "candidate_checks_failed": "worktree_post_merge_check_failed",
        "conflict_resolution_required": "merge_conflicts_detected",
        "artifact_handoff_required": "artifact_handoff_required",
        "paused_retryable": "worktree_merge_paused_retryable",
        "merged_post_verify_failed": "worktree_post_merge_verify_failed",
    }
    return _emit(
        args,
        "worktree merge",
        {
            **result,
            "applied": True,
            "ok": exit_code == 0,
            "error_code": None if exit_code == 0 else error_by_status.get(result["status"], "worktree_merge_incomplete"),
            "next_actions": []
            if exit_code == 0
            else [str(result.get("next_action") or "Inspect the operation journal and resume safely.")],
        },
        exit_code=exit_code,
    )


def worktree_artifact_plan_command(args: argparse.Namespace) -> int:
    project = _project(args)
    target = _existing_target(args, project)
    from ai_context_framework.git_support import rev_parse

    payload = build_artifact_plan(
        target_key=target.key,
        source_head=rev_parse(project.repo_root, target.branch),
        source_path=target.path,
        overrides=parse_artifact_overrides(
            required=args.required or [],
            references=args.reference or [],
            caches=args.cache or [],
            discardable=args.discardable or [],
        ),
        cache_patterns=project.config.artifact_cache_patterns,
        discardable_patterns=project.config.artifact_discardable_patterns,
    )
    manifest_path = None
    if args.apply:
        manifest_path = str(write_artifact_plan(project.common_dir, payload))
    return _emit(
        args,
        "worktree artifact-plan",
        {
            "status": payload["status"],
            "applied": bool(args.apply),
            "target": target_payload(target),
            "manifest_path": manifest_path,
            "manifest": payload,
            "ok": True,
            "next_actions": []
            if payload["status"] == "verified"
            else ["Classify unknown entries and rerun artifact-plan --apply or artifact-migrate."],
        },
    )


def worktree_artifact_migrate_command(args: argparse.Namespace) -> int:
    project = _project(args)
    target = _existing_target(args, project)
    payload = load_artifact_plan(project.common_dir, target.key)
    if payload is None:
        raise SystemExit(f"artifact_manifest_not_found: {target.key}")
    if not args.apply:
        return _emit(
            args,
            "worktree artifact-migrate",
            {
                "status": "migration_planned",
                "applied": False,
                "target": target_payload(target),
                "manifest": payload,
                "ok": True,
                "next_actions": ["Review the manifest and rerun with --apply."],
            },
        )
    result = migrate_artifacts(project.common_dir, payload, source_path=target.path)
    exit_code = 0 if result["promotion_ready"] else 1
    return _emit(
        args,
        "worktree artifact-migrate",
        {
            **result,
            "applied": True,
            "target": target_payload(target),
            "ok": exit_code == 0,
            "error_code": None if exit_code == 0 else "artifact_handoff_incomplete",
            "next_actions": []
            if exit_code == 0
            else ["Classify unknown entries or repair failed destinations, then retry."],
        },
        exit_code=exit_code,
    )


def worktree_close_command(args: argparse.Namespace) -> int:
    project = _project(args)
    target = _existing_target(args, project)
    plan = plan_close(project, target)
    if not args.apply:
        return _emit(
            args,
            "worktree close",
            {
                **plan,
                "applied": False,
                "ok": True,
                "next_actions": []
                if plan["status"] == "already_closed"
                else ["Complete artifact handoff first."]
                if plan["status"] == "artifact_handoff_required"
                else ["Review the close plan and rerun with --apply."],
            },
        )
    result = apply_close(
        project,
        target,
        wait_timeout_seconds=args.wait_timeout,
        operation_id=args.operation_id,
    )
    return _emit(
        args,
        "worktree close",
        {**result, "applied": True, "ok": True},
    )


def worktree_retire_command(args: argparse.Namespace) -> int:
    project = _project(args)
    target = _existing_target(args, project)
    plan = plan_retire(
        project,
        target,
        disposition=getattr(args, "disposition", None),
        evidence_ref=getattr(args, "evidence_ref", None),
    )
    if not args.apply:
        return _emit(
            args,
            "worktree retire",
            {
                **plan,
                "applied": False,
                "ok": True,
                "next_actions": []
                if plan["status"] == "already_retired"
                else ["Complete artifact handoff first."]
                if plan["status"] == "artifact_handoff_required"
                else [
                    "Review the retire plan and rerun with --apply; the branch is preserved."
                ],
            },
        )
    result = apply_retire(
        project,
        target,
        disposition=getattr(args, "disposition", None),
        evidence_ref=getattr(args, "evidence_ref", None),
        wait_timeout_seconds=args.wait_timeout,
        operation_id=args.operation_id,
    )
    return _emit(
        args,
        "worktree retire",
        {**result, "applied": True, "ok": True},
    )


def register_retire_parser(subparsers, add_json_argument) -> None:
    parser = subparsers.add_parser(
        "retire",
        help=(
            "retire a registered worktree whose branch stays intentionally non-mergeable "
            "after its required commits are preserved elsewhere"
        ),
    )
    parser.add_argument("path", nargs="?", type=Path)
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--workstream", type=validate_workstream_id)
    identity.add_argument("--target", type=Path)
    parser.add_argument(
        "--disposition",
        default=None,
        help="retirement disposition; the first version supports curated_handoff",
    )
    parser.add_argument(
        "--evidence-ref",
        default=None,
        help="required durable evidence that this branch's required commits are preserved elsewhere",
    )
    parser.add_argument(
        "--preserve-branch",
        action="store_true",
        default=True,
        help="assert that the branch is preserved; retirement never deletes a branch",
    )
    parser.add_argument("--wait-timeout", type=int, default=120)
    parser.add_argument("--operation-id", default=None)
    parser.add_argument("--apply", action="store_true")
    add_json_argument(parser)
    parser.set_defaults(func=worktree_retire_command)


def worktree_resume_command(args: argparse.Namespace) -> int:
    project = _project(args)
    if not args.apply:
        from ai_context_framework.git_support import load_operation

        operation = load_operation(project.common_dir, args.operation_id)
        return _emit(
            args,
            "worktree resume",
            {
                "status": "resume_planned",
                "applied": False,
                "ok": True,
                "operation": operation,
                "next_actions": ["Review the journal and rerun with --apply."],
            },
        )
    result = resume_operation(project, args.operation_id)
    return _emit(
        args,
        "worktree resume",
        {**result, "applied": True, "ok": True},
    )


def register_worktree_parsers(
    subparsers: Any, add_json_argument: Callable[..., None]
) -> None:
    """Register the whole `worktree` parser tree (moved out of ``runtime.build_parser``).

    This module owns its handlers, so they are referenced directly rather than
    injected.
    """

    worktree_parser = subparsers.add_parser(
        "worktree",
        help="manage optional Git branches and linked worktrees",
    )
    worktree_subparsers = worktree_parser.add_subparsers(dest="worktree_command", required=True)

    worktree_create_parser = worktree_subparsers.add_parser(
        "create",
        help="plan or create a Workstream or classified non-Workstream worktree",
    )
    worktree_create_parser.add_argument("path", nargs="?", type=Path, help="context path or project directory")
    create_identity = worktree_create_parser.add_mutually_exclusive_group(required=True)
    create_identity.add_argument("--workstream", type=validate_workstream_id)
    create_identity.add_argument("--kind", choices=ALLOWED_NON_WORKSTREAM_KINDS)
    worktree_create_parser.add_argument("--slug", default=None, help="task slug; required for non-Workstream targets and optional override for Workstreams")
    worktree_create_parser.add_argument("--operation-id", default=None, help="optional stable operation id for recovery")
    worktree_create_parser.add_argument("--apply", action="store_true", help="perform the planned Git changes")
    add_json_argument(worktree_create_parser)
    worktree_create_parser.set_defaults(func=worktree_create_command)

    worktree_attach_parser = worktree_subparsers.add_parser("attach", help="bind and verify an existing standard worktree")
    worktree_attach_parser.add_argument("path", nargs="?", type=Path)
    worktree_attach_parser.add_argument("--workstream", type=validate_workstream_id, required=True)
    worktree_attach_parser.add_argument("--target", type=Path, required=True)
    worktree_attach_parser.add_argument("--slug", default=None)
    worktree_attach_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_attach_parser)
    worktree_attach_parser.set_defaults(func=worktree_attach_command)

    worktree_verify_parser = worktree_subparsers.add_parser("verify", help="verify repository, branch, path, registry, and reservation identity")
    worktree_verify_parser.add_argument("path", nargs="?", type=Path)
    verify_identity = worktree_verify_parser.add_mutually_exclusive_group(required=True)
    verify_identity.add_argument("--workstream", type=validate_workstream_id)
    verify_identity.add_argument("--target", type=Path)
    worktree_verify_parser.add_argument("--slug", default=None)
    add_json_argument(worktree_verify_parser)
    worktree_verify_parser.set_defaults(func=worktree_verify_command)

    worktree_list_parser = worktree_subparsers.add_parser("list", help="list Git worktrees and ACF bindings")
    worktree_list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(worktree_list_parser)
    worktree_list_parser.set_defaults(func=worktree_list_command)

    worktree_audit_parser = worktree_subparsers.add_parser("audit", help="audit detached, prunable, misplaced, or stale worktrees")
    worktree_audit_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(worktree_audit_parser)
    worktree_audit_parser.set_defaults(func=worktree_audit_command)

    worktree_sync_parser = worktree_subparsers.add_parser("sync", help="merge the primary branch into a clean worktree branch")
    worktree_sync_parser.add_argument("path", nargs="?", type=Path)
    sync_identity = worktree_sync_parser.add_mutually_exclusive_group(required=True)
    sync_identity.add_argument("--workstream", type=validate_workstream_id)
    sync_identity.add_argument("--target", type=Path)
    worktree_sync_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_sync_parser)
    worktree_sync_parser.set_defaults(func=worktree_sync_command)

    worktree_merge_plan_parser = worktree_subparsers.add_parser("merge-plan", help="plan an integration-worktree merge and protected fast-forward promotion")
    worktree_merge_plan_parser.add_argument("path", nargs="?", type=Path)
    merge_plan_identity = worktree_merge_plan_parser.add_mutually_exclusive_group(required=True)
    merge_plan_identity.add_argument("--workstream", type=validate_workstream_id)
    merge_plan_identity.add_argument("--target", type=Path)
    add_json_argument(worktree_merge_plan_parser)
    worktree_merge_plan_parser.set_defaults(func=worktree_merge_plan_command)

    worktree_merge_parser = worktree_subparsers.add_parser("merge", help="merge in a temporary integration worktree, validate, migrate artifacts, and promote")
    worktree_merge_parser.add_argument("path", nargs="?", type=Path)
    merge_identity = worktree_merge_parser.add_mutually_exclusive_group(required=True)
    merge_identity.add_argument("--workstream", type=validate_workstream_id)
    merge_identity.add_argument("--target", type=Path)
    worktree_merge_parser.add_argument("--message", default=None)
    worktree_merge_parser.add_argument("--operation-id", default=None, help="optional stable operation id")
    worktree_merge_parser.add_argument("--pre-check-json", action="append", default=None, help="JSON argv array executed in the source worktree before merge")
    worktree_merge_parser.add_argument("--post-check-json", action="append", default=None, help="JSON argv array executed in the temporary integration worktree")
    worktree_merge_parser.add_argument("--max-replans", type=int, default=8)
    worktree_merge_parser.add_argument("--conflict-replans", type=int, default=3)
    worktree_merge_parser.add_argument("--lock-wait-timeout", type=int, default=300)
    worktree_merge_parser.add_argument("--wait-timeout", type=int, default=600)
    worktree_merge_parser.add_argument("--initial-delay", type=float, default=0.5)
    worktree_merge_parser.add_argument("--max-delay", type=float, default=15.0)
    worktree_merge_parser.add_argument("--jitter-ratio", type=float, default=0.20)
    worktree_merge_parser.add_argument("--artifact-required", action="append", default=None, metavar="PATH=DEST")
    worktree_merge_parser.add_argument("--artifact-reference", action="append", default=None, metavar="PATH=DEST")
    worktree_merge_parser.add_argument("--artifact-cache", action="append", default=None, metavar="PATH")
    worktree_merge_parser.add_argument("--artifact-discardable", action="append", default=None, metavar="PATH")
    worktree_merge_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_merge_parser)
    worktree_merge_parser.set_defaults(func=worktree_merge_command)

    worktree_artifact_plan_parser = worktree_subparsers.add_parser("artifact-plan", help="classify ignored/untracked worktree artifacts before promotion or close")
    worktree_artifact_plan_parser.add_argument("path", nargs="?", type=Path)
    artifact_plan_identity = worktree_artifact_plan_parser.add_mutually_exclusive_group(required=True)
    artifact_plan_identity.add_argument("--workstream", type=validate_workstream_id)
    artifact_plan_identity.add_argument("--target", type=Path)
    worktree_artifact_plan_parser.add_argument("--required", action="append", default=None, metavar="PATH=DEST")
    worktree_artifact_plan_parser.add_argument("--reference", action="append", default=None, metavar="PATH=DEST")
    worktree_artifact_plan_parser.add_argument("--cache", action="append", default=None, metavar="PATH")
    worktree_artifact_plan_parser.add_argument("--discardable", action="append", default=None, metavar="PATH")
    worktree_artifact_plan_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_artifact_plan_parser)
    worktree_artifact_plan_parser.set_defaults(func=worktree_artifact_plan_command)

    worktree_artifact_migrate_parser = worktree_subparsers.add_parser("artifact-migrate", help="copy/reference artifacts and verify their digests")
    worktree_artifact_migrate_parser.add_argument("path", nargs="?", type=Path)
    artifact_migrate_identity = worktree_artifact_migrate_parser.add_mutually_exclusive_group(required=True)
    artifact_migrate_identity.add_argument("--workstream", type=validate_workstream_id)
    artifact_migrate_identity.add_argument("--target", type=Path)
    worktree_artifact_migrate_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_artifact_migrate_parser)
    worktree_artifact_migrate_parser.set_defaults(func=worktree_artifact_migrate_command)

    worktree_close_parser = worktree_subparsers.add_parser("close", help="remove an already-merged clean worktree after artifact handoff")
    worktree_close_parser.add_argument("path", nargs="?", type=Path)
    close_identity = worktree_close_parser.add_mutually_exclusive_group(required=True)
    close_identity.add_argument("--workstream", type=validate_workstream_id)
    close_identity.add_argument("--target", type=Path)
    worktree_close_parser.add_argument("--wait-timeout", type=int, default=120)
    worktree_close_parser.add_argument("--operation-id", default=None)
    worktree_close_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_close_parser)
    worktree_close_parser.set_defaults(func=worktree_close_command)

    register_retire_parser(worktree_subparsers, add_json_argument)

    worktree_resume_parser = worktree_subparsers.add_parser("resume", help="inspect or resume a journaled create/merge/close/retire operation")
    worktree_resume_parser.add_argument("operation_id")
    worktree_resume_parser.add_argument("path", nargs="?", type=Path)
    worktree_resume_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_resume_parser)
    worktree_resume_parser.set_defaults(func=worktree_resume_command)
