"""Small adapters for active Continuation owner liveness commands."""

from __future__ import annotations

import argparse
from datetime import timedelta
from typing import Any

from ai_context_framework.commands import continuation_workspace as continuation_workspace_commands


def _continuation():
    from ai_context_framework.commands import continuation

    return continuation


def continuation_assert_owner_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            snapshot = core._lease_snapshot(paths, control)
            lease, _owner_context = continuation_workspace_commands.assert_owner_context(
                args,
                paths,
                root=root,
                control=control,
                snapshot=snapshot,
            )
            git = core._git_identity(root)
            if git["branch"] != control["expected_branch"] or git["detached"]:
                raise core.ContinuationError(
                    "Git identity changed during active round",
                    code="workspace_mismatch",
                )
            return {
                "status": "owner_confirmed",
                "lease": core._public_lease(lease),
                "generation": lease.get("generation"),
                "liveness": snapshot.get("liveness"),
            }

    return core._guarded(args, "continuation assert-owner", operation)


def continuation_heartbeat_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            snapshot = core._lease_snapshot(paths, control)
            lease, _owner_context = continuation_workspace_commands.assert_owner_context(
                args,
                paths,
                root=root,
                control=control,
                snapshot=snapshot,
            )
            git = core._git_identity(root)
            if git["branch"] != control["expected_branch"] or git["detached"]:
                raise core.ContinuationError(
                    "Git identity changed during active round",
                    code="workspace_mismatch",
                )
            directive_context = core.continuation_directive_commands.directive_context(paths, control)
            directive_signal = core.continuation_directive_commands.observe_directive_context(
                lease,
                directive_context,
            )
            lease["last_heartbeat_at"] = core._iso()
            core._write_json(paths["lease"], lease)
            return {
                "status": "heartbeat_recorded",
                "lease": core._public_lease(lease),
                "generation": lease.get("generation"),
                "directive_signal": directive_signal,
            }

    return core._guarded(args, "continuation heartbeat", operation)


def continuation_renew_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            if paths["pause"].exists():
                raise core.ContinuationError(
                    "pause was requested; do not extend the active round",
                    code="continuation_paused",
                    exit_code=3,
                )
            snapshot = core._lease_snapshot(paths, control)
            lease, _owner_context = continuation_workspace_commands.assert_owner_context(
                args,
                paths,
                root=root,
                control=control,
                snapshot=snapshot,
            )
            git = core._git_identity(root)
            if git["branch"] != control["expected_branch"] or git["detached"]:
                raise core.ContinuationError(
                    "Git identity changed during active round",
                    code="workspace_mismatch",
                )
            ttl = int(args.ttl_minutes or control["lease_ttl_minutes"])
            if ttl < 1 or ttl > core.MAX_LEASE_TTL_MINUTES:
                raise core.ContinuationError("invalid lease TTL", code="timing_invalid")
            now = core._now()
            directive_context = core.continuation_directive_commands.directive_context(paths, control)
            directive_signal = core.continuation_directive_commands.observe_directive_context(
                lease,
                directive_context,
            )
            lease["last_heartbeat_at"] = core._iso(now)
            lease["last_renew_at"] = core._iso(now)
            lease["expires_at"] = core._iso(now + timedelta(minutes=ttl))
            core._write_json(paths["lease"], lease)
            return {
                "status": "renewed",
                "lease": core._public_lease(lease),
                "directive_signal": directive_signal,
            }

    return core._guarded(args, "continuation renew", operation)


__all__ = [
    "continuation_assert_owner_command",
    "continuation_heartbeat_command",
    "continuation_renew_command",
]
