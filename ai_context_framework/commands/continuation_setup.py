"""CLI adapter for bounded continuation init/configure commands.

``init`` records the immutable identity of one long-lived continuation task
(worktree, branch, bootstrap HEAD, timing profile) plus its first workspace
provenance baseline; ``configure`` can only retune timing while no round owns
the lease.  They live outside the workspace command adapter so every module
stays inside the repository's agent-friendly size budget.
"""

from __future__ import annotations

import argparse
from typing import Any

from ai_context_framework import continuation_workspace
from ai_context_framework.commands import continuation_workspace as continuation_workspace_commands


def _core():
    # Imported lazily to avoid a module-import cycle: the main continuation
    # controller imports this adapter for backwards-compatible command aliases.
    from ai_context_framework.commands import continuation

    return continuation


def continuation_init_command(args: argparse.Namespace) -> int:
    core = _core()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        task_id = str(args.task_id or args.workstream or "").strip()
        if not task_id:
            raise core.ContinuationError("--task-id or --workstream is required", code="task_id_required")
        title = core._validate_public_input_text(args.title, field="title")
        objective = core._validate_public_input_text(args.objective, field="objective")
        stage = core._validate_public_input_text(args.stage or "bootstrap", field="stage")
        next_action = core._validate_public_input_text(
            args.next_action or "Refresh local authority and execute the current default plan.",
            field="next_action",
        )
        plan_refs = [
            core._validate_public_input_text(value, field="plan_ref")
            for value in (args.plan_ref or [])
        ]
        git = core._git_identity(root)
        if git["detached"] or not git["branch"]:
            raise core.ContinuationError("continuation init refuses detached HEAD", code="detached_head")
        expected_branch = str(args.expected_branch or git["branch"])
        if expected_branch != git["branch"]:
            raise core.ContinuationError("current branch does not match --expected-branch", code="branch_mismatch")
        workstream = core._workstream_verification(root, args.workstream)
        if args.workstream and not workstream.get("ok"):
            raise core.ContinuationError(
                "ACF worktree verification failed",
                code="workstream_verification_failed",
                details={"workstream": workstream},
            )
        timing_profile, timing = continuation_workspace_commands.timing_values(
            profile=args.profile,
            interval_minutes=args.interval_minutes,
            lease_ttl_minutes=args.lease_ttl_minutes,
            renew_interval_minutes=args.renew_interval_minutes,
            heartbeat_interval_minutes=args.heartbeat_interval_minutes,
            stale_after_minutes=args.stale_after_minutes,
        )
        directory = core._task_parent(root) / core._safe_key(task_id)
        paths = {
            "directory": directory,
            "lock": directory / "state.lock",
            "control": directory / "control.json",
            "state": directory / "state.json",
            "lease": directory / "lease.json",
            "pause": directory / "pause.json",
            "receipt": directory / "last_run.json",
            "rounds": directory / "rounds.json",
            "effects": directory / "effects.json",
            "coordination": directory / "coordination.json",
            "workspace": directory / "workspace.json",
            "workspace_reconcile": directory / "last_workspace_reconcile.json",
            "handoff_takeover": directory / "last_handoff_takeover.json",
            "reconcile": directory / "reconcile.json",
            "recovery": directory / "last_recovery.json",
        }
        if paths["control"].exists() and not args.force:
            raise core.ContinuationError(
                "continuation task is already initialized",
                code="continuation_exists",
                next_actions=["Use `acf continuation doctor` or rerun init with --force after review."],
            )
        now = core._iso()
        snapshot = continuation_workspace_commands.workspace_current_snapshot(root)
        try:
            manifest = continuation_workspace.new_manifest(
                task_id=task_id,
                snapshot=snapshot,
                now=now,
            )
        except continuation_workspace.ContinuationWorkspaceError as exc:
            raise continuation_workspace_commands.workspace_error(exc) from exc
        control = {
            "schema_version": core.CONTROL_SCHEMA,
            "task_id": task_id,
            "title": title,
            "objective": objective,
            "workspace_root": str(root),
            "expected_branch": expected_branch,
            "bootstrap_head": git["head"],
            "workstream_id": args.workstream,
            "timing_profile": timing_profile,
            **timing,
            "history_policy": "local_first",
            "created_at": now,
            "updated_at": now,
        }
        state = {
            "schema_version": core.STATE_SCHEMA,
            "task_id": task_id,
            "objective": objective,
            "status": "ready",
            "stage": stage,
            "next_action": next_action,
            "updated_at": now,
            "completed": ["Initialized ACF bounded continuation control."],
            "constraints": [
                "Use the configured fixed Git worktree and branch.",
                "Treat local project state as authoritative; do not reconstruct state from chat history by default.",
                "Do not repeat an uncertain non-idempotent operation.",
                "Finish runner-owned writes with the project-required checkpoint; preserve unrelated external dirty state.",
            ],
            "evidence_refs": [],
            "open_questions": [],
            "plan_refs": plan_refs,
            "verification": ["Continuation control initialized with a bounded Git workspace baseline."],
        }
        directory.mkdir(parents=True, exist_ok=True)
        if not paths["lock"].exists():
            paths["lock"].write_bytes(b"0")
        core._write_json(paths["control"], control)
        core._write_state(paths["state"], state)
        core._write_json(paths["workspace"], manifest)
        if args.force:
            for stale in (
                paths["lease"],
                paths["pause"],
                paths["receipt"],
                paths["rounds"],
                paths["effects"],
                paths["coordination"],
                paths["workspace"],
                paths["workspace_reconcile"],
                paths["handoff_takeover"],
                paths["reconcile"],
                paths["recovery"],
            ):
                stale.unlink(missing_ok=True)
            core._write_json(paths["workspace"], manifest)
        return {
            "status": "initialized",
            "task_id": task_id,
            "workspace_root": str(root),
            "branch": expected_branch,
            "state_dir": str(directory),
            "workstream": workstream,
            "workspace": continuation_workspace.summary(manifest, task_id=task_id),
            "next_action": state["next_action"],
        }

    return core._guarded(args, "continuation init", operation)


def continuation_configure_command(args: argparse.Namespace) -> int:
    core = _core()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            lease = core._lease_snapshot(paths, control)
            if lease["state"] == "active":
                raise core.ContinuationBusy(
                    "cannot reconfigure continuation timing while an active round owns the lease"
                )
            if not any(
                value is not None
                for value in (
                    args.profile,
                    args.interval_minutes,
                    args.lease_ttl_minutes,
                    args.renew_interval_minutes,
                    args.heartbeat_interval_minutes,
                    args.stale_after_minutes,
                )
            ):
                raise core.ContinuationError(
                    "configure requires --profile or at least one timing override",
                    code="timing_config_empty",
                )
            previous = {
                field: control[field]
                for field in (
                    "timing_profile",
                    "interval_minutes",
                    "lease_ttl_minutes",
                    "renew_interval_minutes",
                    "heartbeat_interval_minutes",
                    "stale_after_minutes",
                )
            }
            profile, timing = continuation_workspace_commands.timing_values(
                profile=args.profile,
                interval_minutes=args.interval_minutes,
                lease_ttl_minutes=args.lease_ttl_minutes,
                renew_interval_minutes=args.renew_interval_minutes,
                heartbeat_interval_minutes=args.heartbeat_interval_minutes,
                stale_after_minutes=args.stale_after_minutes,
                base=control,
            )
            control.update({"timing_profile": profile, **timing, "updated_at": core._iso()})
            core._write_json(paths["control"], control)
            return {
                "status": "configured",
                "task_id": control["task_id"],
                "previous": previous,
                "control": {"timing_profile": profile, **timing},
            }

    return core._guarded(args, "continuation configure", operation)


__all__ = [
    "continuation_configure_command",
    "continuation_init_command",
]
