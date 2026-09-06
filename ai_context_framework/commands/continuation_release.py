"""Release and graceful-handoff adapter for continuation owners."""

from __future__ import annotations

import argparse
from typing import Any

from ai_context_framework import continuation_rounds, continuation_workspace
from ai_context_framework.commands import continuation as core
from ai_context_framework.commands import continuation_coordination as continuation_coordination_commands
from ai_context_framework.commands import continuation_workspace as continuation_workspace_commands


def continuation_release_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            handoff = bool(getattr(args, "handoff", False))
            if handoff and args.final_status is not None:
                raise core.ContinuationError(
                    "--handoff is mutually exclusive with --final-status",
                    code="continuation_release_mode_conflict",
                )

            control = core._load_control(paths, root)
            snapshot = core._lease_snapshot(paths, control)
            lease = core._assert_lease_owner(
                snapshot,
                lease_id=args.lease_id,
                fence_token=continuation_workspace_commands.resolve_fence_token(args),
                generation=args.generation,
            )
            generation = lease.get("generation")
            round_journal: dict[str, Any] | None = None
            if generation is not None:
                round_journal = core._load_round_journal(paths, control, require_existing=True)
            state = core._load_state(paths)
            git = core._git_identity(root)
            workspace_manifest = continuation_workspace_commands.load_workspace_manifest(paths, control)
            workspace_snapshot = continuation_workspace_commands.workspace_current_snapshot(root)
            workspace_summary: dict[str, Any] | None = None
            workspace_release_blocked = False
            workspace_block_reason: str | None = None
            if workspace_manifest is not None:
                try:
                    workspace_manifest = continuation_workspace.handoff_generation(
                        workspace_manifest,
                        task_id=str(control["task_id"]),
                        snapshot=workspace_snapshot,
                        now=core._iso(),
                    )
                except continuation_workspace.ContinuationWorkspaceError as exc:
                    raise continuation_workspace_commands.workspace_error(exc) from exc
                workspace_summary = continuation_workspace.summary(
                    workspace_manifest,
                    task_id=str(control["task_id"]),
                )
                workspace_release_blocked = bool(workspace_summary["has_conflicts"])
                if workspace_release_blocked:
                    workspace_block_reason = "workspace_conflict"
            elif workspace_snapshot["entries"]:
                workspace_release_blocked = True
                workspace_block_reason = "workspace_provenance_missing"

            pause = core._read_json(paths["pause"], label="pause") if paths["pause"].exists() else None
            outcome = "released"
            if pause is not None:
                state["status"] = "paused"
                state["next_action"] = "Wait for an explicit continuation resume action."
                outcome = "released_to_paused"
            elif workspace_release_blocked:
                state["status"] = "reconciling"
                state["next_action"] = "Reconcile ambiguous workspace ownership before another round."
                state["verification"] = core._append_unique(
                    state["verification"],
                    [f"Release failed closed because {workspace_block_reason or 'workspace ownership is ambiguous'}."],
                )
                outcome = "released_to_reconciling"
            else:
                if handoff:
                    if state["status"] != "running":
                        raise core.ContinuationError(
                            "--handoff requires the continuation state to remain running",
                            code="continuation_handoff_state_invalid",
                        )
                    outcome = "released_to_running_handoff"
                else:
                    final_status = args.final_status
                    if final_status is None:
                        final_status = "ready" if state["status"] == "running" else state["status"]
                    if final_status not in core.STATE_STATUSES - {"running"}:
                        raise core.ContinuationError("invalid final status", code="state_invalid")
                    state["status"] = final_status
                if args.stage:
                    state["stage"] = args.stage.strip()
                if args.next_action:
                    state["next_action"] = args.next_action.strip()
                state["verification"] = core._append_unique(state["verification"], args.verification or [])

            release_now = core._iso()
            finished_round: dict[str, Any] | None = None
            if round_journal is not None:
                try:
                    round_journal, finished_round = continuation_rounds.finish_round(
                        round_journal,
                        task_id=str(control["task_id"]),
                        generation=core._require_fenced_generation(lease),
                        lease_id=str(lease["lease_id"]),
                        reconciling=state["status"] == "reconciling",
                        milestone=outcome,
                        evidence_refs=[],
                        now=release_now,
                    )
                except continuation_rounds.ContinuationRoundError as exc:
                    raise core._round_error(exc) from exc
            state["updated_at"] = release_now
            state = core._write_state(paths["state"], state)
            if round_journal is not None:
                core._write_json(paths["rounds"], round_journal)
            if workspace_manifest is not None:
                core._write_json(paths["workspace"], workspace_manifest)
            receipt = {
                "schema_version": core.RECEIPT_SCHEMA,
                "task_id": control["task_id"],
                "lease_id": lease["lease_id"],
                "runner_id": lease["runner_id"],
                "generation": lease.get("generation"),
                "workspace_root": str(root),
                "branch": git["branch"],
                "head_before": lease["head"],
                "head_after": git["head"],
                "started_at": lease["issued_at"],
                "released_at": release_now,
                "outcome": outcome,
                "state_status": state["status"],
                "state_stage": state["stage"],
                "dirty_entries": git["dirty_entries"],
            }
            core._write_json(paths["receipt"], receipt)
            coordination_resolution = continuation_coordination_commands.record_owner_release(
                paths,
                control,
                lease,
                now=release_now,
            )
            paths["lease"].unlink(missing_ok=False)
            return {
                "ok": outcome in {"released", "released_to_running_handoff"},
                "status": outcome,
                "state": state,
                "receipt": receipt,
                "round": finished_round,
                "workspace": workspace_summary,
                "coordination_resolution": coordination_resolution,
                "next_action": state["next_action"],
            }

    return core._guarded(args, "continuation release", operation)


def register_release_parser(subparsers, add_json_argument) -> None:
    parser = subparsers.add_parser(
        "release",
        help="finish a round, record a receipt, and release the active lease",
    )
    parser.add_argument("path", nargs="?", type=core.Path)
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--lease-id", required=True)
    parser.add_argument("--generation", type=int, default=None)
    parser.add_argument("--fence-token", default=None)
    parser.add_argument(
        "--handoff",
        action="store_true",
        help=(
            "release the active owner for a graceful session handoff while preserving a running "
            "long-lived mission; mutually exclusive with --final-status"
        ),
    )
    parser.add_argument(
        "--final-status",
        choices=tuple(sorted(core.STATE_STATUSES - {"running"})),
        default=None,
    )
    parser.add_argument("--stage", default=None)
    parser.add_argument("--next-action", default=None)
    parser.add_argument("--verification", action="append", default=None)
    add_json_argument(parser)
    parser.set_defaults(func=continuation_release_command)


__all__ = ["continuation_release_command", "register_release_parser"]
