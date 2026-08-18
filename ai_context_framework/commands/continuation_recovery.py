"""Formal continuation reconciliation command orchestration.

This adapter keeps bounded coordination evidence and reconcile receipt
construction out of the main continuation controller.  Recovery itself stays
in the controller because it owns the lease/workspace/round state transition.
"""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path
from typing import Any, Mapping

from ai_context_framework import continuation_coordination, continuation_recovery
from ai_context_framework.commands import continuation_coordination as coordination_commands


def _continuation():
    # Lazy import avoids a module cycle because the main continuation module
    # imports this adapter for its public command alias.
    from ai_context_framework.commands import continuation

    return continuation


def reconcile_observation(
    root: Path,
    task_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    core = _continuation()
    status = core._status(root, task_id)
    paths = core._paths(root, task_id)
    control = status["control"]
    rounds = core._load_round_journal(paths, control)
    effects = core._load_effect_journal(paths, control)
    now = core._iso()
    if paths["coordination"].exists():
        coordination_state, _ = coordination_commands.refresh_coordination_timeouts(
            paths,
            control,
            now=now,
        )
        try:
            coordination_summary = continuation_coordination.summary(
                coordination_state,
                task_id=str(control["task_id"]),
                now=now,
            )
        except continuation_coordination.ContinuationCoordinationError as exc:
            raise coordination_commands.coordination_error(exc) from exc
        coordination_observation: Mapping[str, Any] = coordination_state
    else:
        # A synthesized empty coordination state has a moving updated_at and
        # would make a no-contention receipt stale on every subsequent read.
        coordination_observation = {
            "state": "absent",
            "task_id": str(control["task_id"]),
        }
        coordination_summary = {"challenges": []}
    observation = continuation_recovery.build_observation(
        status,
        rounds=rounds,
        effects=effects,
        coordination=coordination_observation,
        coordination_summary=coordination_summary,
        task_id=str(control["task_id"]),
    )
    return status, observation


def continuation_reconcile_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            status, observation = reconcile_observation(root, args.task_id)
            evidence_refs = list(dict.fromkeys(args.evidence_ref or []))[: core.MAX_LIST_ITEMS]
            for evidence_ref in evidence_refs:
                core._validate_text(evidence_ref, field="evidence_ref")
            accepted_head = str(args.accept_head).strip() if args.accept_head else None
            decision, reasons = continuation_recovery.reconcile_decision(
                status,
                observation,
                owner_ended=bool(args.owner_ended),
                accepted_head=accepted_head,
                evidence_refs=evidence_refs,
            )
            result: dict[str, Any] = {
                "status": "reconciled",
                "decision": decision,
                "eligible_for_recover": decision == "eligible",
                "reasons": reasons,
                "observation": observation,
                "assertions": {
                    "owner_ended": bool(args.owner_ended),
                    "accepted_head": accepted_head,
                },
                "evidence_refs": evidence_refs,
                "recorded": False,
            }
            if args.record:
                reason = core._validate_text(args.reason, field="reason")
                receipt = {
                    "schema_version": continuation_recovery.RECONCILE_SCHEMA,
                    "receipt_id": str(uuid.uuid4()),
                    "task_id": status["control"]["task_id"],
                    "created_at": core._iso(),
                    "decision": decision,
                    "reasons": reasons,
                    "reason": reason,
                    "evidence_refs": evidence_refs,
                    "assertions": result["assertions"],
                    "observation": observation,
                }
                core._write_json(paths["reconcile"], receipt)
                result["recorded"] = True
                result["receipt"] = receipt
            return result

    return core._guarded(args, "continuation reconcile", operation)


def register_recovery_parsers(subparsers, add_json_argument) -> None:
    reconcile = subparsers.add_parser(
        "reconcile",
        help="classify an interrupted round, including bounded dirty ownership, and optionally record an auditable recovery decision",
        description="Classify an interrupted round using lease/effect/workspace ownership evidence and optionally record an auditable recovery decision.",
    )
    reconcile.add_argument("path", nargs="?", type=Path)
    reconcile.add_argument("--task-id", default=None)
    reconcile.add_argument("--owner-ended", action="store_true")
    reconcile.add_argument("--accept-head", default=None)
    reconcile.add_argument("--evidence-ref", action="append", default=None)
    reconcile.add_argument("--reason", default=None)
    reconcile.add_argument("--record", action="store_true")
    add_json_argument(reconcile)
    reconcile.set_defaults(func=continuation_reconcile_command)

    recover = subparsers.add_parser(
        "recover",
        help="fence an interrupted owner and transfer evidence-backed WIP using one eligible reconcile receipt",
        description="Fence an interrupted owner and transfer evidence-backed write intent/WIP ownership using one eligible reconcile receipt.",
    )
    recover.add_argument("path", nargs="?", type=Path)
    recover.add_argument("--task-id", default=None)
    recover.add_argument("--reconcile-id", required=True)
    recover.add_argument("--runner-id", required=True)
    recover.add_argument("--ttl-minutes", type=int, default=None)
    add_json_argument(recover)
    recover.set_defaults(func=_continuation().continuation_recover_command)


__all__ = [
    "continuation_reconcile_command",
    "reconcile_observation",
    "register_recovery_parsers",
]
