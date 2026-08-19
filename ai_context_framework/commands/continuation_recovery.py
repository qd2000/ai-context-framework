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

from ai_context_framework import continuation_coordination, continuation_recovery, continuation_rounds
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


def validate_recovery_effect_reconciliations(
    effect_journal: Mapping[str, Any],
    observation: Mapping[str, Any],
    *,
    task_id: str,
    receipt: Mapping[str, Any],
) -> list[dict[str, Any]]:
    core = _continuation()
    try:
        return continuation_recovery.validate_effect_reconciliations(
            effect_journal,
            observation,
            task_id=task_id,
            reconciliations=receipt.get("effect_reconciliations", []),
            owner_ended=receipt["assertions"].get("owner_ended") is True,
        )
    except continuation_recovery.ContinuationRecoveryError as exc:
        raise core.ContinuationError(str(exc), code=exc.code, exit_code=3) from exc


def apply_recovery_effect_reconciliations(
    effect_journal: Mapping[str, Any],
    *,
    task_id: str,
    generation: int,
    reconciliations: list[dict[str, Any]],
    reconcile_id: str,
    now: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    core = _continuation()
    try:
        return continuation_recovery.apply_effect_reconciliations(
            effect_journal,
            task_id=task_id,
            generation=generation,
            reconciliations=reconciliations,
            reconcile_id=reconcile_id,
            now=now,
        )
    except continuation_rounds.ContinuationRoundError as exc:
        raise core._round_error(exc) from exc


def validate_recovery_inputs(
    root: Path,
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
    *,
    task_id: str | None,
    reconcile_id: str,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
]:
    core = _continuation()
    try:
        receipt = continuation_recovery.validate_reconcile_receipt(
            core._read_json(paths["reconcile"], label="reconcile")
        )
    except continuation_recovery.ContinuationRecoveryError as exc:
        raise core.ContinuationError(str(exc), code=exc.code) from exc
    if receipt["task_id"] != control["task_id"]:
        raise core.ContinuationError("reconcile receipt task mismatch", code="reconcile_invalid")
    if receipt["receipt_id"] != reconcile_id:
        raise core.ContinuationError(
            "reconcile receipt id does not match",
            code="reconcile_mismatch",
            exit_code=3,
        )
    if receipt["decision"] != "eligible":
        raise core.ContinuationError(
            "reconcile receipt does not authorize recovery",
            code="recovery_not_authorized",
            exit_code=3,
            details={"reasons": receipt["reasons"]},
        )
    status, observation = reconcile_observation(root, task_id)
    if dict(receipt["observation"]) != observation:
        raise core.ContinuationError(
            "continuation state changed after reconciliation",
            code="reconciliation_stale",
            exit_code=3,
            details={"recorded": receipt["observation"], "current": observation},
            next_actions=["Run `acf continuation reconcile` again against the current state."],
        )
    effect_journal = core._load_effect_journal(paths, control)
    effect_reconciliations = validate_recovery_effect_reconciliations(
        effect_journal,
        observation,
        task_id=str(control["task_id"]),
        receipt=receipt,
    )
    return receipt, status, observation, effect_journal, effect_reconciliations


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
            effect_keys = list(args.effect_key or [])
            effect_terminal_statuses = list(args.effect_terminal_status or [])
            effect_external_ids = list(args.effect_external_id or [])
            effect_milestones = list(args.effect_milestone or [])
            effect_requested = any(
                (effect_keys, effect_terminal_statuses, effect_external_ids, effect_milestones)
            ) or bool(args.effect_not_started) or bool(args.effect_evidence_ref or [])
            effect_reconciliations: list[dict[str, Any]] = []
            if effect_requested:
                if not effect_keys or len(effect_keys) != len(effect_terminal_statuses):
                    raise core.ContinuationError(
                        "ownerless effect reconciliation requires one terminal status for each effect key",
                        code="effect_reconcile_incomplete",
                    )
                if args.effect_not_started and (len(effect_keys) != 1 or effect_external_ids):
                    raise core.ContinuationError(
                        "effect-not-started accepts exactly one effect key and cannot be combined with an external id",
                        code="effect_identity_conflict",
                    )
                if not args.effect_not_started and len(effect_external_ids) != len(effect_keys):
                    raise core.ContinuationError(
                        "ownerless effect reconciliation requires one external id for each effect key unless effect-not-started is asserted",
                        code="effect_reconcile_incomplete",
                    )
                if effect_milestones and len(effect_milestones) != len(effect_keys):
                    raise core.ContinuationError(
                        "ownerless effect reconciliation requires either no milestones or one milestone for each effect key",
                        code="effect_reconcile_incomplete",
                    )
                effect_evidence_refs = list(
                    dict.fromkeys(args.effect_evidence_ref or [])
                )[: core.MAX_LIST_ITEMS]
                for evidence_ref in effect_evidence_refs:
                    core._validate_text(evidence_ref, field="effect_evidence_ref")
                effects = core._load_effect_journal(paths, status["control"], require_existing=True)
                try:
                    for index, effect_key in enumerate(effect_keys):
                        effect_reconciliations.append(
                            continuation_recovery.build_effect_reconciliation(
                                effects,
                                observation,
                                task_id=str(status["control"]["task_id"]),
                                logical_key=core._validate_text(effect_key, field="effect_key"),
                                external_id=(
                                    None
                                    if args.effect_not_started
                                    else core._validate_text(
                                        effect_external_ids[index],
                                        field="effect_external_id",
                                    )
                                ),
                                terminal_status=str(effect_terminal_statuses[index]),
                                milestone=(effect_milestones[index] if effect_milestones else None),
                                evidence_refs=effect_evidence_refs,
                                owner_ended=bool(args.owner_ended),
                                not_started=bool(args.effect_not_started),
                            )
                        )
                except continuation_recovery.ContinuationRecoveryError as exc:
                    raise core.ContinuationError(str(exc), code=exc.code) from exc
            accepted_head = str(args.accept_head).strip() if args.accept_head else None
            decision, reasons = continuation_recovery.reconcile_decision(
                status,
                observation,
                owner_ended=bool(args.owner_ended),
                accepted_head=accepted_head,
                evidence_refs=evidence_refs,
                effect_reconciliations=effect_reconciliations,
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
                "effect_reconciliations": effect_reconciliations,
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
                if effect_reconciliations:
                    receipt["effect_reconciliations"] = effect_reconciliations
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
    reconcile.add_argument(
        "--effect-key",
        action="append",
        default=None,
        help="existing deterministic effect key to reconcile from external terminal evidence; repeat with the matching terminal-status/external-id to reconcile multiple effects atomically",
    )
    reconcile.add_argument(
        "--effect-terminal-status",
        action="append",
        choices=tuple(sorted(continuation_rounds.TERMINAL_EFFECT_STATUSES)),
        default=None,
        help="authoritatively observed terminal status for an effect; repeat in the same order as --effect-key",
    )
    reconcile.add_argument(
        "--effect-external-id",
        action="append",
        default=None,
        help="existing durable external identity; repeat in the same order as --effect-key and each value must exactly match the prepared effect",
    )
    reconcile.add_argument(
        "--effect-not-started",
        action="store_true",
        help="assert that a still-prepared effect never crossed the external submission boundary; requires failed status, no external id, and external authority evidence",
    )
    reconcile.add_argument(
        "--effect-milestone",
        action="append",
        default=None,
        help="compact terminal milestone to record if recovery succeeds; when repeated effect keys are used, provide one milestone per key or omit milestones",
    )
    reconcile.add_argument(
        "--effect-evidence-ref",
        action="append",
        default=None,
        help="external authority evidence for the terminal effect observation; can be repeated",
    )
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
