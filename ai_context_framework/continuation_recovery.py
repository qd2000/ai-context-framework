"""Pure validation and decision helpers for continuation orphan recovery."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from ai_context_framework import continuation_rounds


RECONCILE_SCHEMA = "acf.continuation.reconcile.v1"
RECOVERY_SCHEMA = "acf.continuation.recovery.v1"


class ContinuationRecoveryError(ValueError):
    def __init__(self, message: str, *, code: str = "reconcile_invalid") -> None:
        super().__init__(message)
        self.code = code


def json_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def coordination_recovery_digest(
    coordination: Mapping[str, Any],
    *,
    owner_generation: int | None,
) -> str:
    """Digest only coordination state that can change recovery authority.

    Coordination attempts are append-only scheduler bookkeeping.  A new
    contender registering after an eligible reconcile receipt must not make
    that receipt stale when the challenged owner, challenge outcome, HEAD,
    workspace, rounds, and effects are unchanged.  The current owner's
    nonterminal challenge does affect recovery authority, so retain its stable
    identity/timing/status fields while deliberately excluding contender IDs
    and top-level ``updated_at``.
    """

    if coordination.get("state") == "absent":
        return json_digest(
            {
                "state": "absent",
                "task_id": coordination.get("task_id"),
                "owner_generation": owner_generation,
            }
        )

    challenges: list[dict[str, Any]] = []
    raw_challenges = coordination.get("challenges")
    if isinstance(raw_challenges, list):
        for raw in raw_challenges:
            if not isinstance(raw, Mapping):
                continue
            if raw.get("owner_generation") != owner_generation:
                continue
            if raw.get("status") not in {"open", "timed_out"}:
                continue
            challenges.append(
                {
                    "challenge_id": raw.get("challenge_id"),
                    "owner_generation": raw.get("owner_generation"),
                    "opened_at": raw.get("opened_at"),
                    "deadline_at": raw.get("deadline_at"),
                    "status": raw.get("status"),
                    "acknowledged_at": raw.get("acknowledged_at"),
                    "acknowledged_lease_id": raw.get("acknowledged_lease_id"),
                    "acknowledged_runner_id": raw.get("acknowledged_runner_id"),
                    "timed_out_at": raw.get("timed_out_at"),
                    "resolved_at": raw.get("resolved_at"),
                    "resolution": raw.get("resolution"),
                    "recovery_generation": raw.get("recovery_generation"),
                    "reconcile_receipt_id": raw.get("reconcile_receipt_id"),
                }
            )
    challenges.sort(key=lambda item: (str(item.get("opened_at") or ""), str(item.get("challenge_id") or "")))
    return json_digest(
        {
            "schema_version": coordination.get("schema_version"),
            "task_id": coordination.get("task_id"),
            "owner_generation": owner_generation,
            "challenges": challenges,
        }
    )


def build_observation(
    status: Mapping[str, Any],
    *,
    rounds: Mapping[str, Any],
    effects: Mapping[str, Any],
    coordination: Mapping[str, Any],
    coordination_summary: Mapping[str, Any],
    task_id: str,
) -> dict[str, Any]:
    lease_payload = status["lease"].get("lease")
    lease = dict(lease_payload) if isinstance(lease_payload, Mapping) else {}
    workspace_payload = status.get("workspace")
    workspace = dict(workspace_payload) if isinstance(workspace_payload, Mapping) else {}
    forfeiture_candidates: list[dict[str, Any]] = []
    raw_challenges = coordination_summary.get("challenges")
    if isinstance(raw_challenges, list):
        for raw in raw_challenges:
            if not isinstance(raw, Mapping) or raw.get("ownership_forfeiture_candidate") is not True:
                continue
            forfeiture_candidates.append(
                {
                    "challenge_id": raw.get("challenge_id"),
                    "owner_generation": raw.get("owner_generation"),
                    "deadline_at": raw.get("deadline_at"),
                    "timed_out_at": raw.get("timed_out_at"),
                }
            )
    return {
        "lease_state": status["lease"]["state"],
        "lease_id": lease.get("lease_id"),
        "lease_generation": lease.get("generation"),
        "liveness": status["lease"].get("liveness"),
        "lease_head": lease.get("head"),
        "control_generation": int(status["control"].get("generation", 0)),
        "state_status": status["state"]["status"],
        "current_head": status["git"]["head"],
        "workspace_state": workspace.get("state"),
        "workspace_generation": workspace.get("generation"),
        "workspace_manifest_digest": workspace.get("manifest_digest"),
        "workspace_has_conflicts": bool(workspace.get("has_conflicts")),
        "workspace_unclassified_paths": list(workspace.get("unclassified_paths") or []),
        "workspace_baseline_external_paths": list(workspace.get("baseline_external_paths") or []),
        "workspace_task_owned_paths": list(workspace.get("task_owned_paths") or []),
        "workspace_runner_owned_paths": list(workspace.get("runner_owned_paths") or []),
        "workspace_unexpected_nonoverlap_paths": list(workspace.get("unexpected_nonoverlap_paths") or []),
        "round_digest": json_digest(rounds),
        "effect_digest": json_digest(effects),
        "coordination_digest": coordination_recovery_digest(
            coordination,
            owner_generation=(int(lease["generation"]) if isinstance(lease.get("generation"), int) else None),
        ),
        "ownership_forfeiture_candidates": forfeiture_candidates,
        "latest_round": continuation_rounds.latest_round(rounds, task_id=task_id),
        "effect_summary": continuation_rounds.effect_summary(effects, task_id=task_id),
    }


def reconcile_decision(
    status: Mapping[str, Any],
    observation: Mapping[str, Any],
    *,
    owner_ended: bool,
    accepted_head: str | None,
    evidence_refs: Sequence[str],
    effect_reconciliations: Sequence[Mapping[str, Any]] = (),
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not bool(status.get("ok")):
        reasons.append("continuation_identity_invalid")
    if status.get("pause") is not None:
        reasons.append("paused")

    lease_state = observation.get("lease_state")
    liveness = observation.get("liveness")
    lease_generation = observation.get("lease_generation")
    raw_forfeiture_candidates = observation.get("ownership_forfeiture_candidates")
    forfeiture_candidates = (
        [item for item in raw_forfeiture_candidates if isinstance(item, Mapping)]
        if isinstance(raw_forfeiture_candidates, list)
        else []
    )
    ownership_forfeited = any(
        item.get("owner_generation") == lease_generation and isinstance(item.get("challenge_id"), str)
        for item in forfeiture_candidates
    )
    if lease_state not in {"active", "expired"}:
        reasons.append("recoverable_lease_missing")
    if lease_state == "active":
        if ownership_forfeited:
            pass
        elif liveness == "fresh":
            reasons.append("active_owner_live")
        elif liveness in {"stale", "legacy_unknown"}:
            if not owner_ended:
                reasons.append("owner_end_not_proven")
        else:
            reasons.append("active_owner_liveness_invalid")

    workspace_state = observation.get("workspace_state")
    workspace_generation = observation.get("workspace_generation")
    workspace_digest = observation.get("workspace_manifest_digest")
    workspace_has_conflicts = bool(observation.get("workspace_has_conflicts"))
    workspace_unclassified_paths = list(observation.get("workspace_unclassified_paths") or [])
    if workspace_has_conflicts:
        reasons.append("workspace_conflict")
    if workspace_state == "valid" and lease_generation is not None and workspace_generation != lease_generation:
        reasons.append("workspace_generation_mismatch")
    if workspace_state == "absent" and workspace_unclassified_paths:
        reasons.append("workspace_provenance_missing")
    if workspace_state == "valid" and (not isinstance(workspace_digest, str) or not workspace_digest):
        reasons.append("workspace_manifest_digest_missing")

    latest_round = observation.get("latest_round")
    if lease_generation is not None:
        if not isinstance(latest_round, Mapping):
            reasons.append("round_record_missing")
        elif (
            latest_round.get("generation") != lease_generation
            or latest_round.get("lease_id") != observation.get("lease_id")
            or latest_round.get("phase") == "released"
        ):
            reasons.append("round_record_mismatch")

    current_head = str(observation.get("current_head") or "")
    lease_head = str(observation.get("lease_head") or "")
    if current_head and lease_head and current_head != lease_head:
        if accepted_head != current_head:
            reasons.append("head_change_unaccepted")
    elif accepted_head is not None and accepted_head != current_head:
        reasons.append("accepted_head_mismatch")

    effect_summary = observation.get("effect_summary")
    if isinstance(effect_summary, Mapping):
        unresolved = [str(value) for value in effect_summary.get("unresolved") or []]
        reconciled_keys = {
            str(item.get("logical_key"))
            for item in effect_reconciliations
            if isinstance(item, Mapping)
            and item.get("effect_digest") == observation.get("effect_digest")
            and isinstance(item.get("logical_key"), str)
        }
        if any(key not in reconciled_keys for key in unresolved):
            reasons.append("unresolved_effects")

    if (owner_ended or accepted_head is not None) and not evidence_refs:
        reasons.append("recovery_evidence_required")
    return ("eligible" if not reasons else "blocked"), reasons


def ownership_forfeited(observation: Mapping[str, Any]) -> bool:
    lease_generation = observation.get("lease_generation")
    raw_candidates = observation.get("ownership_forfeiture_candidates")
    if not isinstance(raw_candidates, list):
        return False
    return any(
        isinstance(item, Mapping)
        and item.get("owner_generation") == lease_generation
        and isinstance(item.get("challenge_id"), str)
        and bool(str(item.get("challenge_id")).strip())
        for item in raw_candidates
    )


def build_effect_reconciliation(
    effects: Mapping[str, Any],
    observation: Mapping[str, Any],
    *,
    task_id: str,
    logical_key: str,
    external_id: str | None,
    terminal_status: str,
    milestone: str | None,
    evidence_refs: Sequence[str],
    owner_ended: bool,
    not_started: bool = False,
    local_terminal: bool = False,
) -> dict[str, Any]:
    if not owner_ended and not ownership_forfeited(observation):
        raise ContinuationRecoveryError(
            "ownerless effect reconciliation requires owner-ended or ownership-forfeiture evidence",
            code="effect_reconcile_owner_not_ended",
        )
    if terminal_status not in continuation_rounds.TERMINAL_EFFECT_STATUSES:
        raise ContinuationRecoveryError(
            "ownerless effect reconciliation requires a terminal effect status",
            code="effect_status_invalid",
        )
    refs = [str(value).strip() for value in evidence_refs if str(value).strip()]
    refs = list(dict.fromkeys(refs))
    if not refs:
        raise ContinuationRecoveryError(
            "ownerless effect reconciliation requires external authority evidence",
            code="effect_reconcile_evidence_required",
        )
    journal = continuation_rounds.validate_effect_journal(effects, task_id=task_id)
    target = next(
        (record for record in journal["effects"] if record["logical_key"] == logical_key),
        None,
    )
    if target is None:
        raise ContinuationRecoveryError(
            "effect key is not prepared",
            code="effect_missing",
        )
    observed_status = str(target["status"])
    if observed_status in continuation_rounds.TERMINAL_EFFECT_STATUSES:
        raise ContinuationRecoveryError(
            "effect is already terminal and does not need ownerless reconciliation",
            code="effect_already_terminal",
        )
    stored_external_id = target.get("external_id")
    if not_started and local_terminal:
        raise ContinuationRecoveryError(
            "effect reconciliation modes are mutually exclusive",
            code="effect_identity_conflict",
        )
    if not_started:
        if observed_status != "prepared":
            raise ContinuationRecoveryError(
                "only a still-prepared effect can be reconciled as not started",
                code="effect_not_started_status_invalid",
            )
        if terminal_status != "failed":
            raise ContinuationRecoveryError(
                "an effect proven not started can only be reconciled as failed",
                code="effect_not_started_status_invalid",
            )
        if isinstance(stored_external_id, str) and stored_external_id.strip():
            raise ContinuationRecoveryError(
                "an effect with a durable external identity cannot be reconciled as not started",
                code="effect_identity_conflict",
            )
        if external_id is not None:
            raise ContinuationRecoveryError(
                "effect-not-started cannot be combined with an external identity",
                code="effect_identity_conflict",
            )
    elif local_terminal:
        if observed_status not in {"prepared", "active"}:
            raise ContinuationRecoveryError(
                "only a prepared or active effect can use local terminal reconciliation without an external identity",
                code="effect_local_terminal_status_invalid",
            )
        if isinstance(stored_external_id, str) and stored_external_id.strip():
            raise ContinuationRecoveryError(
                "an effect with a durable external identity must use identity-matched reconciliation",
                code="effect_identity_conflict",
            )
        if external_id is not None:
            raise ContinuationRecoveryError(
                "local terminal reconciliation cannot be combined with an external identity",
                code="effect_identity_conflict",
            )
    else:
        if not isinstance(stored_external_id, str) or not stored_external_id.strip():
            raise ContinuationRecoveryError(
                "effect has no durable external identity to reconcile",
                code="effect_identity_missing",
            )
        if external_id != stored_external_id:
            raise ContinuationRecoveryError(
                "effect external identity does not match the prepared effect",
                code="effect_identity_conflict",
            )
    effect_digest = observation.get("effect_digest")
    if not isinstance(effect_digest, str) or not effect_digest:
        raise ContinuationRecoveryError(
            "effect observation digest is missing",
            code="reconcile_invalid",
        )
    resolved_milestone = (
        str(milestone).strip() if isinstance(milestone, str) and milestone.strip() else terminal_status
    )
    result = {
        "effect_id": str(target["effect_id"]),
        "logical_key": str(target["logical_key"]),
        "kind": str(target["kind"]),
        "external_id": None if (not_started or local_terminal) else stored_external_id,
        "observed_status": observed_status,
        "terminal_status": terminal_status,
        "milestone": resolved_milestone,
        "evidence_refs": refs,
        "effect_digest": effect_digest,
    }
    if not_started:
        result["not_started"] = True
    if local_terminal:
        result["local_terminal"] = True
    return result


def validate_effect_reconciliations(
    effects: Mapping[str, Any],
    observation: Mapping[str, Any],
    *,
    task_id: str,
    reconciliations: Sequence[Mapping[str, Any]],
    owner_ended: bool,
) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in reconciliations:
        if not isinstance(raw, Mapping):
            raise ContinuationRecoveryError("effect reconciliation assertion is invalid")
        item = dict(raw)
        required = {
            "effect_id",
            "logical_key",
            "kind",
            "external_id",
            "observed_status",
            "terminal_status",
            "milestone",
            "evidence_refs",
            "effect_digest",
        }
        if not required.issubset(item) or not set(item).issubset(
            required | {"not_started", "local_terminal"}
        ):
            raise ContinuationRecoveryError("effect reconciliation assertion schema is invalid")
        logical_key = item.get("logical_key")
        if not isinstance(logical_key, str) or not logical_key.strip() or logical_key in seen:
            raise ContinuationRecoveryError("effect reconciliation logical key is invalid")
        seen.add(logical_key)
        rebuilt = build_effect_reconciliation(
            effects,
            observation,
            task_id=task_id,
            logical_key=logical_key,
            external_id=(
                str(item["external_id"])
                if isinstance(item.get("external_id"), str) and str(item["external_id"]).strip()
                else None
            ),
            terminal_status=str(item.get("terminal_status") or ""),
            milestone=str(item.get("milestone") or ""),
            evidence_refs=(
                [str(value) for value in item.get("evidence_refs")]
                if isinstance(item.get("evidence_refs"), list)
                else []
            ),
            owner_ended=owner_ended,
            not_started=item.get("not_started") is True,
            local_terminal=item.get("local_terminal") is True,
        )
        if rebuilt != item:
            raise ContinuationRecoveryError(
                "effect reconciliation assertion no longer matches the observed effect",
                code="reconciliation_stale",
            )
        validated.append(rebuilt)
    return validated


def apply_effect_reconciliations(
    effects: Mapping[str, Any],
    *,
    task_id: str,
    generation: int,
    reconciliations: Sequence[Mapping[str, Any]],
    reconcile_id: str,
    now: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    journal = continuation_rounds.validate_effect_journal(effects, task_id=task_id)
    applied: list[dict[str, Any]] = []
    for item in reconciliations:
        journal, effect = continuation_rounds.update_effect(
            journal,
            task_id=task_id,
            generation=generation,
            logical_key=str(item["logical_key"]),
            status=str(item["terminal_status"]),
            external_id=(str(item["external_id"]) if isinstance(item.get("external_id"), str) else None),
            milestone=str(item["milestone"]),
            evidence_refs=[
                *[str(value) for value in item["evidence_refs"]],
                f"reconcile:{reconcile_id}",
            ],
            now=now,
        )
        applied.append(effect)
    return journal, applied


def validate_reconcile_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    receipt = dict(payload)
    required = {
        "schema_version",
        "receipt_id",
        "task_id",
        "created_at",
        "decision",
        "reasons",
        "reason",
        "evidence_refs",
        "assertions",
        "observation",
    }
    allowed = required | {"effect_reconciliations"}
    if receipt.get("schema_version") != RECONCILE_SCHEMA or not required.issubset(receipt) or not set(receipt).issubset(allowed):
        raise ContinuationRecoveryError("reconcile receipt schema is invalid")
    if receipt.get("decision") not in {"eligible", "blocked"}:
        raise ContinuationRecoveryError("reconcile receipt decision is invalid")
    for field in ("receipt_id", "task_id", "created_at", "reason"):
        value = receipt.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ContinuationRecoveryError(f"reconcile receipt {field} is invalid")
    try:
        parsed = datetime.fromisoformat(str(receipt["created_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContinuationRecoveryError("reconcile receipt created_at is invalid") from exc
    if parsed.tzinfo is None:
        raise ContinuationRecoveryError("reconcile receipt created_at must include timezone")
    if not isinstance(receipt.get("reasons"), list) or not isinstance(receipt.get("evidence_refs"), list):
        raise ContinuationRecoveryError("reconcile receipt lists are invalid")
    assertions = receipt.get("assertions")
    observation = receipt.get("observation")
    if not isinstance(assertions, Mapping) or set(assertions) != {"owner_ended", "accepted_head"}:
        raise ContinuationRecoveryError("reconcile receipt assertions are invalid")
    if not isinstance(assertions.get("owner_ended"), bool):
        raise ContinuationRecoveryError("reconcile owner_ended assertion is invalid")
    if assertions.get("accepted_head") is not None and not isinstance(assertions.get("accepted_head"), str):
        raise ContinuationRecoveryError("reconcile accepted_head assertion is invalid")
    if not isinstance(observation, Mapping):
        raise ContinuationRecoveryError("reconcile receipt observation is invalid")
    effect_reconciliations = receipt.get("effect_reconciliations", [])
    if not isinstance(effect_reconciliations, list):
        raise ContinuationRecoveryError("reconcile receipt effect_reconciliations is invalid")
    receipt["effect_reconciliations"] = effect_reconciliations
    return receipt


__all__ = [
    "RECONCILE_SCHEMA",
    "RECOVERY_SCHEMA",
    "coordination_recovery_digest",
    "ContinuationRecoveryError",
    "build_observation",
    "build_effect_reconciliation",
    "apply_effect_reconciliations",
    "json_digest",
    "ownership_forfeited",
    "reconcile_decision",
    "validate_effect_reconciliations",
    "validate_reconcile_receipt",
]
