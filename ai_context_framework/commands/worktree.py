"""CLI handlers for optional Git worktree lifecycle management."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ai_context_framework.git_support import (
    ALLOWED_NON_WORKSTREAM_KINDS,
    discover_git_project,
    target_payload,
)
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.worktree_service import (
    apply_close,
    apply_create,
    apply_merge,
    apply_sync,
    attach_workstream,
    audit_project,
    list_payload,
    plan_close,
    plan_create,
    plan_merge,
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
        target, _info = resolve_workstream_target(
            project,
            workstream_id,
            slug_override=slug,
        )
        return target
    if kind:
        if not slug:
            raise SystemExit("worktree_slug_required: --kind requires --slug")
        return resolve_non_workstream_target(project, kind, slug)
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
    target = _create_target(args, project)
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
                    "Review the plan and rerun with --apply to create or resume the worktree."
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
        {**result, "applied": True, "ok": True},
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
                else ["Review the merge plan and rerun with --apply."],
            },
        )
    result = apply_merge(
        project,
        target,
        message=args.message,
        pre_checks=args.pre_check_json or [],
        post_checks=args.post_check_json or [],
    )
    exit_code = 0 if result["status"] != "merged_checks_failed" else 1
    return _emit(
        args,
        "worktree merge",
        {
            **result,
            "applied": True,
            "ok": exit_code == 0,
            "error_code": None if exit_code == 0 else "worktree_post_merge_check_failed",
            "next_actions": []
            if exit_code == 0
            else ["Inspect failed post-merge checks and repair main; ACF does not reset the merge commit."],
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
                else ["Review the close plan and rerun with --apply."],
            },
        )
    result = apply_close(project, target)
    return _emit(
        args,
        "worktree close",
        {**result, "applied": True, "ok": True},
    )


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
