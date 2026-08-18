"""Bounded single-writer / multi-contender continuation coordination state.

This module deliberately stores only compact coordination metadata.  It does
not decide whether an owner is dead, grant write ownership, inspect project
files, or perform recovery.  Those decisions remain in the continuation
controller and later reconciliation stages.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


COORDINATION_SCHEMA = "acf.continuation.coordination.v1"
ATTEMPT_STATUSES = frozenset({"claim_candidate", "contender", "closed"})
CHALLENGE_STATUSES = frozenset({"open", "acknowledged", "timed_out", "resolved", "superseded"})
NONTERMINAL_CHALLENGE_STATUSES = frozenset({"open", "timed_out"})
CHALLENGE_RESOLUTIONS = frozenset({"owner_active", "owner_released"})
MAX_ATTEMPTS = 32
MAX_CHALLENGES = 16
MAX_CONTENDERS_PER_CHALLENGE = 16
MAX_RUNNER_ID_BYTES = 256
MAX_OBJECTIVE_BYTES = 1024
MAX_COORDINATION_BYTES = 64 * 1024


class ContinuationCoordinationError(RuntimeError):
    def __init__(self, message: str, *, code: str = "coordination_invalid") -> None:
        super().__init__(message)
        self.code = code


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _require_text(value: Any, *, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContinuationCoordinationError(f"{field} must be non-empty", code="coordination_invalid")
    text = value.strip()
    if _utf8_len(text) > maximum:
        raise ContinuationCoordinationError(f"{field} is too large", code="coordination_text_too_large")
    return text


def _parse_time(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ContinuationCoordinationError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContinuationCoordinationError(f"{field} is not a valid timestamp") from exc
    if parsed.tzinfo is None:
        raise ContinuationCoordinationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_uuid(value: Any, *, field: str) -> str:
    text = _require_text(value, field=field, maximum=64)
    try:
        uuid.UUID(text)
    except ValueError as exc:
        raise ContinuationCoordinationError(f"{field} must be a UUID") from exc
    return text


def new_state(*, task_id: str, now: str) -> dict[str, Any]:
    task = _require_text(task_id, field="task_id", maximum=256)
    _parse_time(now, field="updated_at")
    return {
        "schema_version": COORDINATION_SCHEMA,
        "task_id": task,
        "updated_at": now,
        "attempts": [],
        "challenges": [],
    }


def _validate_attempt(value: Mapping[str, Any]) -> dict[str, Any]:
    attempt_id = _validate_uuid(value.get("attempt_id"), field="attempt_id")
    runner_id = _require_text(value.get("runner_id"), field="runner_id", maximum=MAX_RUNNER_ID_BYTES)
    started_at = str(value.get("started_at") or "")
    _parse_time(started_at, field="started_at")
    objective_summary = _require_text(
        value.get("objective_summary"), field="objective_summary", maximum=MAX_OBJECTIVE_BYTES
    )
    owner_generation = value.get("observed_owner_generation")
    if owner_generation is not None and (isinstance(owner_generation, bool) or not isinstance(owner_generation, int) or owner_generation < 1):
        raise ContinuationCoordinationError("observed_owner_generation must be a positive integer or null")
    status = str(value.get("status") or "")
    if status not in ATTEMPT_STATUSES:
        raise ContinuationCoordinationError("attempt status is invalid")
    return {
        "attempt_id": attempt_id,
        "runner_id": runner_id,
        "started_at": started_at,
        "objective_summary": objective_summary,
        "observed_owner_generation": owner_generation,
        "status": status,
    }


def _validate_challenge(value: Mapping[str, Any], *, attempt_ids: set[str]) -> dict[str, Any]:
    challenge_id = _validate_uuid(value.get("challenge_id"), field="challenge_id")
    owner_generation = value.get("owner_generation")
    if isinstance(owner_generation, bool) or not isinstance(owner_generation, int) or owner_generation < 1:
        raise ContinuationCoordinationError("owner_generation must be a positive integer")
    opened_at = str(value.get("opened_at") or "")
    deadline_at = str(value.get("deadline_at") or "")
    opened = _parse_time(opened_at, field="opened_at")
    deadline = _parse_time(deadline_at, field="deadline_at")
    if deadline <= opened:
        raise ContinuationCoordinationError("challenge deadline must be after opened_at")
    status = str(value.get("status") or "")
    if status not in CHALLENGE_STATUSES:
        raise ContinuationCoordinationError("challenge status is invalid")
    raw_contenders = value.get("contender_attempt_ids")
    if not isinstance(raw_contenders, list) or not raw_contenders:
        raise ContinuationCoordinationError("challenge requires contender_attempt_ids")
    contenders: list[str] = []
    for item in raw_contenders:
        attempt_id = _validate_uuid(item, field="contender_attempt_id")
        if attempt_id not in attempt_ids:
            raise ContinuationCoordinationError("challenge references an unknown attempt")
        if attempt_id not in contenders:
            contenders.append(attempt_id)
    if len(contenders) > MAX_CONTENDERS_PER_CHALLENGE:
        raise ContinuationCoordinationError("challenge contender list exceeds bounded limit", code="coordination_capacity")
    acknowledged_at = value.get("acknowledged_at")
    if acknowledged_at is not None:
        acknowledged_at = str(acknowledged_at)
        _parse_time(acknowledged_at, field="acknowledged_at")
    acknowledged_lease_id = value.get("acknowledged_lease_id")
    if acknowledged_lease_id is not None:
        acknowledged_lease_id = _validate_uuid(acknowledged_lease_id, field="acknowledged_lease_id")
    acknowledged_runner_id = value.get("acknowledged_runner_id")
    if acknowledged_runner_id is not None:
        acknowledged_runner_id = _require_text(
            acknowledged_runner_id,
            field="acknowledged_runner_id",
            maximum=MAX_RUNNER_ID_BYTES,
        )
    timed_out_at = value.get("timed_out_at")
    if timed_out_at is not None:
        timed_out_at = str(timed_out_at)
        _parse_time(timed_out_at, field="timed_out_at")
    resolved_at = value.get("resolved_at")
    if resolved_at is not None:
        resolved_at = str(resolved_at)
        _parse_time(resolved_at, field="resolved_at")
    resolution = value.get("resolution")
    if resolution is not None:
        resolution = str(resolution)
        if resolution not in CHALLENGE_RESOLUTIONS:
            raise ContinuationCoordinationError("challenge resolution is invalid")
    return {
        "challenge_id": challenge_id,
        "owner_generation": owner_generation,
        "opened_at": opened_at,
        "deadline_at": deadline_at,
        "status": status,
        "contender_attempt_ids": contenders,
        "acknowledged_at": acknowledged_at,
        "acknowledged_lease_id": acknowledged_lease_id,
        "acknowledged_runner_id": acknowledged_runner_id,
        "timed_out_at": timed_out_at,
        "resolved_at": resolved_at,
        "resolution": resolution,
    }


def validate_state(value: Mapping[str, Any], *, task_id: str) -> dict[str, Any]:
    if value.get("schema_version") != COORDINATION_SCHEMA:
        raise ContinuationCoordinationError("coordination schema is invalid")
    if value.get("task_id") != task_id:
        raise ContinuationCoordinationError("coordination task identity does not match", code="coordination_identity_mismatch")
    updated_at = str(value.get("updated_at") or "")
    _parse_time(updated_at, field="updated_at")
    raw_attempts = value.get("attempts")
    raw_challenges = value.get("challenges")
    if not isinstance(raw_attempts, list) or not isinstance(raw_challenges, list):
        raise ContinuationCoordinationError("coordination attempts/challenges must be lists")
    attempts = [_validate_attempt(item) for item in raw_attempts if isinstance(item, Mapping)]
    if len(attempts) != len(raw_attempts):
        raise ContinuationCoordinationError("coordination attempt entry is invalid")
    attempt_ids = {str(item["attempt_id"]) for item in attempts}
    if len(attempt_ids) != len(attempts):
        raise ContinuationCoordinationError("coordination attempt ids must be unique")
    challenges = [
        _validate_challenge(item, attempt_ids=attempt_ids)
        for item in raw_challenges
        if isinstance(item, Mapping)
    ]
    if len(challenges) != len(raw_challenges):
        raise ContinuationCoordinationError("coordination challenge entry is invalid")
    challenge_ids = {str(item["challenge_id"]) for item in challenges}
    if len(challenge_ids) != len(challenges):
        raise ContinuationCoordinationError("coordination challenge ids must be unique")
    active_by_generation: dict[int, int] = {}
    for challenge in challenges:
        if challenge["status"] in NONTERMINAL_CHALLENGE_STATUSES:
            generation = int(challenge["owner_generation"])
            active_by_generation[generation] = active_by_generation.get(generation, 0) + 1
    if any(count > 1 for count in active_by_generation.values()):
        raise ContinuationCoordinationError("only one nonterminal challenge is allowed per owner generation")
    result = {
        "schema_version": COORDINATION_SCHEMA,
        "task_id": task_id,
        "updated_at": updated_at,
        "attempts": attempts,
        "challenges": challenges,
    }
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_COORDINATION_BYTES:
        raise ContinuationCoordinationError("coordination state exceeds bounded size", code="coordination_capacity")
    return result


def prune_state(state: Mapping[str, Any], *, task_id: str, now: str) -> dict[str, Any]:
    current = validate_state(state, task_id=task_id)
    challenges = list(current["challenges"])
    nonterminal = [item for item in challenges if item["status"] in NONTERMINAL_CHALLENGE_STATUSES]
    terminal = [item for item in challenges if item["status"] not in NONTERMINAL_CHALLENGE_STATUSES]
    terminal = sorted(terminal, key=lambda item: _parse_time(item["opened_at"], field="opened_at"), reverse=True)
    if len(nonterminal) > MAX_CHALLENGES:
        raise ContinuationCoordinationError("too many nonterminal challenges", code="coordination_capacity")
    kept_challenges = nonterminal + terminal[: max(0, MAX_CHALLENGES - len(nonterminal))]
    referenced = {
        attempt_id
        for challenge in kept_challenges
        for attempt_id in challenge["contender_attempt_ids"]
    }
    attempts = list(current["attempts"])
    referenced_attempts = [item for item in attempts if item["attempt_id"] in referenced]
    if len(referenced_attempts) > MAX_ATTEMPTS:
        raise ContinuationCoordinationError("too many challenge-referenced attempts", code="coordination_capacity")
    unreferenced = [item for item in attempts if item["attempt_id"] not in referenced]
    unreferenced = sorted(
        unreferenced,
        key=lambda item: _parse_time(item["started_at"], field="started_at"),
        reverse=True,
    )
    kept_attempts = referenced_attempts + unreferenced[: max(0, MAX_ATTEMPTS - len(referenced_attempts))]
    kept_attempt_ids = {item["attempt_id"] for item in kept_attempts}
    kept_challenges = [
        item
        for item in kept_challenges
        if all(attempt_id in kept_attempt_ids for attempt_id in item["contender_attempt_ids"])
    ]
    result = {
        "schema_version": COORDINATION_SCHEMA,
        "task_id": task_id,
        "updated_at": now,
        "attempts": sorted(kept_attempts, key=lambda item: item["started_at"]),
        "challenges": sorted(kept_challenges, key=lambda item: item["opened_at"]),
    }
    return validate_state(result, task_id=task_id)


def register_attempt(
    state: Mapping[str, Any],
    *,
    task_id: str,
    runner_id: str,
    objective_summary: str,
    observed_owner_generation: int | None,
    now: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = validate_state(state, task_id=task_id)
    runner = _require_text(runner_id, field="runner_id", maximum=MAX_RUNNER_ID_BYTES)
    objective = _require_text(objective_summary, field="objective_summary", maximum=MAX_OBJECTIVE_BYTES)
    _parse_time(now, field="started_at")
    if observed_owner_generation is not None and (
        isinstance(observed_owner_generation, bool)
        or not isinstance(observed_owner_generation, int)
        or observed_owner_generation < 1
    ):
        raise ContinuationCoordinationError("observed owner generation is invalid")
    attempt = {
        "attempt_id": str(uuid.uuid4()),
        "runner_id": runner,
        "started_at": now,
        "objective_summary": objective,
        "observed_owner_generation": observed_owner_generation,
        "status": "contender" if observed_owner_generation is not None else "claim_candidate",
    }
    updated = dict(current)
    updated["attempts"] = [*current["attempts"], attempt]
    updated["updated_at"] = now
    return prune_state(updated, task_id=task_id, now=now), attempt


def open_or_join_challenge(
    state: Mapping[str, Any],
    *,
    task_id: str,
    attempt_id: str,
    owner_generation: int,
    deadline_at: str,
    now: str,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    current = validate_state(state, task_id=task_id)
    _parse_time(now, field="opened_at")
    deadline = _parse_time(deadline_at, field="deadline_at")
    opened = _parse_time(now, field="opened_at")
    if deadline <= opened:
        raise ContinuationCoordinationError("challenge deadline must be in the future")
    if isinstance(owner_generation, bool) or not isinstance(owner_generation, int) or owner_generation < 1:
        raise ContinuationCoordinationError("owner generation is invalid")
    attempt = next((item for item in current["attempts"] if item["attempt_id"] == attempt_id), None)
    if attempt is None:
        raise ContinuationCoordinationError("attempt does not exist", code="coordination_attempt_missing")
    if attempt["status"] != "contender":
        raise ContinuationCoordinationError("only contender attempts may challenge an owner", code="coordination_not_contender")
    if attempt["observed_owner_generation"] != owner_generation:
        raise ContinuationCoordinationError(
            "attempt observed a different owner generation",
            code="coordination_owner_changed",
        )
    existing = next(
        (
            item
            for item in current["challenges"]
            if item["owner_generation"] == owner_generation
            and item["status"] in NONTERMINAL_CHALLENGE_STATUSES
        ),
        None,
    )
    created = existing is None
    if existing is None:
        challenge = {
            "challenge_id": str(uuid.uuid4()),
            "owner_generation": owner_generation,
            "opened_at": now,
            "deadline_at": deadline_at,
            "status": "open",
            "contender_attempt_ids": [attempt_id],
            "acknowledged_at": None,
            "acknowledged_lease_id": None,
            "acknowledged_runner_id": None,
            "timed_out_at": None,
            "resolved_at": None,
            "resolution": None,
        }
        challenges = [*current["challenges"], challenge]
    else:
        challenge = dict(existing)
        contenders = list(challenge["contender_attempt_ids"])
        if attempt_id not in contenders:
            if len(contenders) >= MAX_CONTENDERS_PER_CHALLENGE:
                raise ContinuationCoordinationError(
                    "challenge contender list exceeds bounded limit",
                    code="coordination_capacity",
                )
            contenders.append(attempt_id)
        challenge["contender_attempt_ids"] = contenders
        challenges = [
            challenge if item["challenge_id"] == challenge["challenge_id"] else item
            for item in current["challenges"]
        ]
    updated = dict(current)
    updated["challenges"] = challenges
    updated["updated_at"] = now
    return prune_state(updated, task_id=task_id, now=now), challenge, created


def advance_timeouts(
    state: Mapping[str, Any],
    *,
    task_id: str,
    now: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    current = validate_state(state, task_id=task_id)
    current_time = _parse_time(now, field="now")
    changed: list[dict[str, Any]] = []
    challenges: list[dict[str, Any]] = []
    for item in current["challenges"]:
        challenge = dict(item)
        if challenge["status"] == "open" and current_time >= _parse_time(
            challenge["deadline_at"], field="deadline_at"
        ):
            challenge["status"] = "timed_out"
            challenge["timed_out_at"] = now
            changed.append(challenge)
        challenges.append(challenge)
    if not changed:
        return current, []
    updated = dict(current)
    updated["challenges"] = challenges
    updated["updated_at"] = now
    return prune_state(updated, task_id=task_id, now=now), changed


def acknowledge_owner_activity(
    state: Mapping[str, Any],
    *,
    task_id: str,
    owner_generation: int,
    lease_id: str,
    runner_id: str,
    now: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    current, _ = advance_timeouts(state, task_id=task_id, now=now)
    lease = _validate_uuid(lease_id, field="lease_id")
    runner = _require_text(runner_id, field="runner_id", maximum=MAX_RUNNER_ID_BYTES)
    if isinstance(owner_generation, bool) or not isinstance(owner_generation, int) or owner_generation < 1:
        raise ContinuationCoordinationError("owner generation is invalid")
    challenge = next(
        (
            item
            for item in current["challenges"]
            if item["owner_generation"] == owner_generation
            and item["status"] in NONTERMINAL_CHALLENGE_STATUSES
        ),
        None,
    )
    if challenge is None:
        return current, None
    acknowledged = dict(challenge)
    acknowledged["status"] = "acknowledged"
    acknowledged["acknowledged_at"] = now
    acknowledged["acknowledged_lease_id"] = lease
    acknowledged["acknowledged_runner_id"] = runner
    acknowledged["resolution"] = "owner_active"
    updated = dict(current)
    updated["challenges"] = [
        acknowledged if item["challenge_id"] == acknowledged["challenge_id"] else item
        for item in current["challenges"]
    ]
    updated["updated_at"] = now
    return prune_state(updated, task_id=task_id, now=now), acknowledged


def resolve_owner_release(
    state: Mapping[str, Any],
    *,
    task_id: str,
    owner_generation: int,
    lease_id: str,
    runner_id: str,
    now: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    current, _ = advance_timeouts(state, task_id=task_id, now=now)
    lease = _validate_uuid(lease_id, field="lease_id")
    runner = _require_text(runner_id, field="runner_id", maximum=MAX_RUNNER_ID_BYTES)
    if isinstance(owner_generation, bool) or not isinstance(owner_generation, int) or owner_generation < 1:
        raise ContinuationCoordinationError("owner generation is invalid")
    challenge = next(
        (
            item
            for item in current["challenges"]
            if item["owner_generation"] == owner_generation
            and item["status"] in NONTERMINAL_CHALLENGE_STATUSES
        ),
        None,
    )
    if challenge is None:
        return current, None
    resolved = dict(challenge)
    resolved["status"] = "resolved"
    resolved["acknowledged_at"] = resolved.get("acknowledged_at") or now
    resolved["acknowledged_lease_id"] = resolved.get("acknowledged_lease_id") or lease
    resolved["acknowledged_runner_id"] = resolved.get("acknowledged_runner_id") or runner
    resolved["resolved_at"] = now
    resolved["resolution"] = "owner_released"
    updated = dict(current)
    updated["challenges"] = [
        resolved if item["challenge_id"] == resolved["challenge_id"] else item
        for item in current["challenges"]
    ]
    updated["updated_at"] = now
    return prune_state(updated, task_id=task_id, now=now), resolved


def summary(state: Mapping[str, Any], *, task_id: str, now: str) -> dict[str, Any]:
    current, _ = advance_timeouts(state, task_id=task_id, now=now)
    current_time = _parse_time(now, field="now")
    attempts = list(current["attempts"])
    challenges: list[dict[str, Any]] = []
    for item in current["challenges"]:
        challenge = dict(item)
        challenge["deadline_passed"] = bool(
            challenge["status"] in {"open", "timed_out"}
            and current_time >= _parse_time(challenge["deadline_at"], field="deadline_at")
        )
        challenge["ownership_forfeiture_candidate"] = challenge["status"] == "timed_out"
        challenges.append(challenge)
    return {
        "attempt_count": len(attempts),
        "challenge_count": len(challenges),
        "ownership_forfeiture_candidate_count": sum(
            1 for item in challenges if item["ownership_forfeiture_candidate"]
        ),
        "contender_count": sum(1 for item in attempts if item["status"] == "contender"),
        "claim_candidate_count": sum(1 for item in attempts if item["status"] == "claim_candidate"),
        "nonterminal_challenges": [
            item for item in challenges if item["status"] in NONTERMINAL_CHALLENGE_STATUSES
        ],
        "attempts": attempts,
        "challenges": challenges,
        "updated_at": current["updated_at"],
    }


__all__ = [
    "ATTEMPT_STATUSES",
    "CHALLENGE_RESOLUTIONS",
    "CHALLENGE_STATUSES",
    "acknowledge_owner_activity",
    "advance_timeouts",
    "COORDINATION_SCHEMA",
    "ContinuationCoordinationError",
    "MAX_ATTEMPTS",
    "MAX_CHALLENGES",
    "MAX_CONTENDERS_PER_CHALLENGE",
    "new_state",
    "open_or_join_challenge",
    "prune_state",
    "register_attempt",
    "resolve_owner_release",
    "summary",
    "validate_state",
]
