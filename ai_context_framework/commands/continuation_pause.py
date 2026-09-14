"""Pause/resume adapters for bounded Continuation state."""

from __future__ import annotations

import argparse
from typing import Any


def _continuation():
    from ai_context_framework.commands import continuation

    return continuation


def continuation_pause_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            marker = {
                "schema_version": core.PAUSE_SCHEMA,
                "task_id": control["task_id"],
                "reason": core._validate_public_input_text(args.reason, field="reason"),
                "requested_by": core._validate_public_input_text(
                    str(args.requested_by or "user"),
                    field="requested_by",
                ),
                "created_at": core._iso(),
            }
            core._write_json(paths["pause"], marker)
            snapshot = core._lease_snapshot(paths, control)
            state = core._load_state(paths)
            if snapshot["state"] != "active":
                state["status"] = "paused"
                state["next_action"] = "Wait for an explicit continuation resume action."
                state["updated_at"] = core._iso()
                state = core._write_state(paths["state"], state)
            return {
                "status": "pause_requested" if snapshot["state"] == "active" else "paused",
                "pause": marker,
                "active_lease": snapshot["state"] == "active",
            }

    return core._guarded(args, "continuation pause", operation)


def continuation_resume_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            snapshot = core._lease_snapshot(paths, control)
            if snapshot["state"] == "active":
                raise core.ContinuationBusy("cannot resume while an active round still owns the lease")
            if not paths["pause"].exists():
                raise core.ContinuationError(
                    "pause marker is not present",
                    code="continuation_not_paused",
                )
            state = core._load_state(paths)
            state["status"] = "ready"
            state["next_action"] = core._validate_public_input_text(
                args.next_action,
                field="next_action",
            )
            state["updated_at"] = core._iso()
            state = core._write_state(paths["state"], state)
            paths["pause"].unlink(missing_ok=False)
            return {"status": "ready", "state": state, "next_action": state["next_action"]}

    return core._guarded(args, "continuation resume", operation)


__all__ = ["continuation_pause_command", "continuation_resume_command"]
