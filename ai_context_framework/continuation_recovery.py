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
                    "contender_attempt_ids": list(raw.get("contender_attempt_ids") or []),
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
        "coordination_digest": json_digest(coordination),
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
    if isinstance(effect_summary, Mapping) and effect_summary.get("unresolved"):
        reasons.append("unresolved_effects")

    if (owner_ended or accepted_head is not None) and not evidence_refs:
        reasons.append("recovery_evidence_required")
    return ("eligible" if not reasons else "blocked"), reasons


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
    if receipt.get("schema_version") != RECONCILE_SCHEMA or set(receipt) != required:
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
    return receipt


__all__ = [
    "RECONCILE_SCHEMA",
    "RECOVERY_SCHEMA",
    "ContinuationRecoveryError",
    "build_observation",
    "json_digest",
    "reconcile_decision",
    "validate_reconcile_receipt",
]
