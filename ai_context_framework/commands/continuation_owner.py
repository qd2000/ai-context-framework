"""Small adapters for active Continuation owner liveness commands."""

from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

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


def continuation_migrate_legacy_token_file_command(args: argparse.Namespace) -> int:
    """Migrate one pre-.90 local token file without changing owner identity."""

    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            snapshot = core._lease_snapshot(paths, control)
            if snapshot.get("state") != "active":
                raise core.ContinuationError(
                    "an active fenced lease is required for owner-context migration",
                    code="owner_context_migration_not_available",
                    exit_code=3,
                )
            raw_lease = snapshot.get("lease")
            if not isinstance(raw_lease, Mapping):
                raise core.ContinuationError("active lease payload is missing", code="lease_invalid")
            generation = core._require_fenced_generation(raw_lease)
            verifier = raw_lease.get("fence_token_hash")
            if not isinstance(verifier, str) or not verifier:
                raise core.ContinuationError(
                    "active lease has no reusable-credential verifier to migrate",
                    code="owner_context_migration_not_available",
                    exit_code=3,
                )
            git = core._git_identity(root)
            if git["branch"] != control["expected_branch"] or git["detached"]:
                raise core.ContinuationError(
                    "Git identity changed during owner-context migration",
                    code="workspace_mismatch",
                    exit_code=3,
                )
            transport = continuation_workspace_commands.continuation_owner_context.inspect_owner_context_transport(
                paths["directory"],
                workspace_root=root,
                task_id=str(control["task_id"]),
                lease_id=str(raw_lease["lease_id"]),
                generation=generation,
                runner_id=str(raw_lease["runner_id"]),
                credential_verifier=verifier,
            )
            if not transport.get("migration_required"):
                raise core.ContinuationError(
                    "the active lease already has a current owner-context capability",
                    code="owner_context_migration_not_required",
                    exit_code=3,
                )
            try:
                owner_context = continuation_workspace_commands.continuation_owner_context.migrate_legacy_token_file(
                    paths["directory"],
                    legacy_token_file=args.legacy_token_file,
                    workspace_root=root,
                    task_id=str(control["task_id"]),
                    lease_id=str(raw_lease["lease_id"]),
                    generation=generation,
                    runner_id=str(raw_lease["runner_id"]),
                    credential_verifier=verifier,
                    created_at=str(raw_lease["issued_at"]),
                )
            except continuation_workspace_commands.continuation_owner_context.OwnerContextError as exc:
                raise continuation_workspace_commands._owner_context_error(exc) from exc
            lease = core._assert_lease_owner(
                snapshot,
                lease_id=owner_context.lease_id,
                fence_token=owner_context.credential,
                generation=owner_context.generation,
            )
            continuation_workspace_commands.continuation_owner_context.revoke_other_owner_contexts(
                paths["directory"],
                keep=owner_context.handle,
            )
            return {
                "status": "owner_context_migrated",
                "task_id": control["task_id"],
                "lease": core._public_lease(lease),
                "generation": generation,
                "owner_context": owner_context.public_handle(),
                "legacy_token_file_retired": True,
            }

    return core._guarded(args, "continuation owner migrate-legacy-token-file", operation)


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


def register_owner_parser(subparsers, add_json_argument) -> None:
    owner = subparsers.add_parser(
        "owner",
        help="manage local continuation owner-capability migration",
    )
    owner_subparsers = owner.add_subparsers(dest="continuation_owner_command", required=True)
    migrate = owner_subparsers.add_parser(
        "migrate-legacy-token-file",
        help="convert one pre-.90 local token file into the current owner-context capability",
    )
    migrate.add_argument("path", nargs="?", type=Path)
    migrate.add_argument("--task-id", default=None)
    migrate.add_argument("--legacy-token-file", type=Path, required=True)
    add_json_argument(migrate)
    migrate.set_defaults(func=continuation_migrate_legacy_token_file_command)


__all__ = [
    "continuation_assert_owner_command",
    "continuation_heartbeat_command",
    "continuation_migrate_legacy_token_file_command",
    "continuation_renew_command",
    "register_owner_parser",
]
