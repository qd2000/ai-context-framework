"""Bounded continuation round and durable external-effect journals.

The journal is deliberately runtime-neutral.  It stores only compact phase,
identity, status, milestone, evidence-reference, and timestamp metadata.  Raw
tool output, transcripts, or runtime-specific payloads do not belong here.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


ROUND_JOURNAL_SCHEMA = "acf.continuation.round-journal.v1"
ROUND_RECORD_SCHEMA = "acf.continuation.round.v1"
EFFECT_JOURNAL_SCHEMA = "acf.continuation.effect-journal.v1"
EFFECT_RECORD_SCHEMA = "acf.continuation.effect.v1"

MAX_ROUNDS = 16
MAX_EFFECTS = 64
MAX_EVIDENCE_REFS = 32
MAX_JOURNAL_BYTES = 64 * 1024
MAX_KEY_BYTES = 256
MAX_VALUE_BYTES = 2048

ROUND_PHASES = frozenset(
    {
        "claimed",
        "executing",
        "waiting_external",
        "finalizing",
        "reconciling",
        "released",
    }
)
EFFECT_STATUSES = frozenset({"prepared", "active", "completed", "failed", "unknown"})
TERMINAL_EFFECT_STATUSES = frozenset({"completed", "failed"})

ROUND_TRANSITIONS: dict[str, frozenset[str]] = {
    "claimed": frozenset({"claimed", "executing", "waiting_external", "finalizing", "reconciling"}),
    "executing": frozenset({"executing", "waiting_external", "finalizing", "reconciling"}),
    "waiting_external": frozenset(
        {"waiting_external", "executing", "finalizing", "reconciling"}
    ),
    "finalizing": frozenset({"finalizing", "reconciling"}),
    "reconciling": frozenset(
        {"reconciling", "executing", "waiting_external", "finalizing"}
    ),
    "released": frozenset({"released"}),
}
EFFECT_TRANSITIONS: dict[str, frozenset[str]] = {
    "prepared": frozenset({"prepared", "active", "completed", "failed", "unknown"}),
    "active": frozenset({"active", "completed", "failed", "unknown"}),
    "unknown": frozenset({"unknown", "active", "completed", "failed"}),
    "completed": frozenset({"completed"}),
    "failed": frozenset({"failed"}),
}


class ContinuationRoundError(ValueError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def _text(value: Any, *, field: str, max_bytes: int = MAX_VALUE_BYTES) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContinuationRoundError(f"{field} must be a non-empty string", code="journal_invalid")
    text = value.strip()
    if len(text.encode("utf-8")) > max_bytes:
        raise ContinuationRoundError(f"{field} exceeds {max_bytes} bytes", code="journal_invalid")
    return text


def _optional_text(value: Any, *, field: str, max_bytes: int = MAX_VALUE_BYTES) -> str | None:
    if value is None:
        return None
    return _text(value, field=field, max_bytes=max_bytes)


def _timestamp(value: Any, *, field: str) -> str:
    text = _text(value, field=field, max_bytes=128)
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContinuationRoundError(f"{field} is not a valid timestamp", code="journal_invalid") from exc
    if parsed.tzinfo is None:
        raise ContinuationRoundError(f"{field} must include a timezone", code="journal_invalid")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _generation(value: Any, *, field: str = "generation") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContinuationRoundError(f"{field} must be a positive integer", code="journal_invalid")
    return value


def _refs(values: Any, *, field: str = "evidence_refs") -> list[str]:
    if not isinstance(values, list) or len(values) > MAX_EVIDENCE_REFS:
        raise ContinuationRoundError(
            f"{field} must be a list with at most {MAX_EVIDENCE_REFS} entries",
            code="journal_invalid",
        )
    result: list[str] = []
    for item in values:
        text = _text(item, field=field, max_bytes=MAX_VALUE_BYTES)
        if text not in result:
            result.append(text)
    return result


def _append_refs(existing: Iterable[str], additions: Iterable[str]) -> list[str]:
    result = list(existing)
    for value in additions:
        text = _text(value, field="evidence_ref", max_bytes=MAX_VALUE_BYTES)
        if text not in result:
            result.append(text)
        if len(result) > MAX_EVIDENCE_REFS:
            raise ContinuationRoundError(
                f"evidence_refs exceeds {MAX_EVIDENCE_REFS} entries",
                code="journal_full",
            )
    return result


def _bounded(payload: Mapping[str, Any]) -> None:
    try:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContinuationRoundError("journal is not JSON serializable", code="journal_invalid") from exc
    if len(encoded) > MAX_JOURNAL_BYTES:
        raise ContinuationRoundError(
            f"journal exceeds {MAX_JOURNAL_BYTES} bytes",
            code="journal_full",
        )


def empty_round_journal(task_id: str) -> dict[str, Any]:
    return {
        "schema_version": ROUND_JOURNAL_SCHEMA,
        "task_id": _text(task_id, field="task_id", max_bytes=MAX_KEY_BYTES),
        "rounds": [],
    }


def empty_effect_journal(task_id: str) -> dict[str, Any]:
    return {
        "schema_version": EFFECT_JOURNAL_SCHEMA,
        "task_id": _text(task_id, field="task_id", max_bytes=MAX_KEY_BYTES),
        "effects": [],
    }


def validate_round_journal(payload: Mapping[str, Any], *, task_id: str) -> dict[str, Any]:
    journal = dict(payload)
    allowed = {"schema_version", "task_id", "rounds"}
    if journal.get("schema_version") != ROUND_JOURNAL_SCHEMA or set(journal) != allowed:
        raise ContinuationRoundError("round journal schema is invalid", code="round_journal_invalid")
    expected_task = _text(task_id, field="task_id", max_bytes=MAX_KEY_BYTES)
    if journal.get("task_id") != expected_task:
        raise ContinuationRoundError("round journal task identity mismatch", code="round_journal_invalid")
    raw_rounds = journal.get("rounds")
    if not isinstance(raw_rounds, list) or len(raw_rounds) > MAX_ROUNDS:
        raise ContinuationRoundError("round journal is not bounded", code="round_journal_invalid")

    rounds: list[dict[str, Any]] = []
    generations: set[int] = set()
    for raw in raw_rounds:
        if not isinstance(raw, Mapping):
            raise ContinuationRoundError("round record must be an object", code="round_journal_invalid")
        record = dict(raw)
        record_allowed = {
            "schema_version",
            "generation",
            "lease_id",
            "runner_id",
            "phase",
            "milestone",
            "evidence_refs",
            "started_at",
            "updated_at",
            "ended_at",
        }
        if record.get("schema_version") != ROUND_RECORD_SCHEMA or set(record) != record_allowed:
            raise ContinuationRoundError("round record schema is invalid", code="round_journal_invalid")
        generation = _generation(record.get("generation"))
        if generation in generations:
            raise ContinuationRoundError("round generations must be unique", code="round_journal_invalid")
        generations.add(generation)
        phase = _text(record.get("phase"), field="phase", max_bytes=64)
        if phase not in ROUND_PHASES:
            raise ContinuationRoundError(f"unsupported round phase: {phase}", code="round_journal_invalid")
        started_at = _timestamp(record.get("started_at"), field="started_at")
        updated_at = _timestamp(record.get("updated_at"), field="updated_at")
        ended_at = (
            _timestamp(record.get("ended_at"), field="ended_at")
            if record.get("ended_at") is not None
            else None
        )
        if ended_at is not None and phase not in {"released", "reconciling"}:
            raise ContinuationRoundError(
                "only released or reconciling rounds may have ended_at",
                code="round_journal_invalid",
            )
        rounds.append(
            {
                "schema_version": ROUND_RECORD_SCHEMA,
                "generation": generation,
                "lease_id": _text(record.get("lease_id"), field="lease_id", max_bytes=128),
                "runner_id": _text(record.get("runner_id"), field="runner_id", max_bytes=MAX_KEY_BYTES),
                "phase": phase,
                "milestone": _optional_text(record.get("milestone"), field="milestone", max_bytes=MAX_KEY_BYTES),
                "evidence_refs": _refs(record.get("evidence_refs")),
                "started_at": started_at,
                "updated_at": updated_at,
                "ended_at": ended_at,
            }
        )
    result = {"schema_version": ROUND_JOURNAL_SCHEMA, "task_id": expected_task, "rounds": rounds}
    _bounded(result)
    return result


def effect_id(task_id: str, logical_key: str, kind: str) -> str:
    task = _text(task_id, field="task_id", max_bytes=MAX_KEY_BYTES)
    key = _text(logical_key, field="logical_key", max_bytes=MAX_KEY_BYTES)
    effect_kind = _text(kind, field="kind", max_bytes=MAX_KEY_BYTES)
    return hashlib.sha256(f"{task}\0{key}\0{effect_kind}".encode("utf-8")).hexdigest()


def validate_effect_journal(payload: Mapping[str, Any], *, task_id: str) -> dict[str, Any]:
    journal = dict(payload)
    allowed = {"schema_version", "task_id", "effects"}
    if journal.get("schema_version") != EFFECT_JOURNAL_SCHEMA or set(journal) != allowed:
        raise ContinuationRoundError("effect journal schema is invalid", code="effect_journal_invalid")
    expected_task = _text(task_id, field="task_id", max_bytes=MAX_KEY_BYTES)
    if journal.get("task_id") != expected_task:
        raise ContinuationRoundError("effect journal task identity mismatch", code="effect_journal_invalid")
    raw_effects = journal.get("effects")
    if not isinstance(raw_effects, list) or len(raw_effects) > MAX_EFFECTS:
        raise ContinuationRoundError("effect journal is not bounded", code="effect_journal_invalid")

    effects: list[dict[str, Any]] = []
    logical_keys: set[str] = set()
    effect_ids: set[str] = set()
    for raw in raw_effects:
        if not isinstance(raw, Mapping):
            raise ContinuationRoundError("effect record must be an object", code="effect_journal_invalid")
        record = dict(raw)
        record_allowed = {
            "schema_version",
            "effect_id",
            "logical_key",
            "kind",
            "external_id",
            "status",
            "milestone",
            "evidence_refs",
            "prepared_generation",
            "last_generation",
            "prepared_at",
            "updated_at",
        }
        if record.get("schema_version") != EFFECT_RECORD_SCHEMA or set(record) != record_allowed:
            raise ContinuationRoundError("effect record schema is invalid", code="effect_journal_invalid")
        logical_key = _text(record.get("logical_key"), field="logical_key", max_bytes=MAX_KEY_BYTES)
        kind = _text(record.get("kind"), field="kind", max_bytes=MAX_KEY_BYTES)
        expected_effect_id = effect_id(expected_task, logical_key, kind)
        if record.get("effect_id") != expected_effect_id:
            raise ContinuationRoundError("effect deterministic identity mismatch", code="effect_journal_invalid")
        if logical_key in logical_keys or expected_effect_id in effect_ids:
            raise ContinuationRoundError("effect identities must be unique", code="effect_journal_invalid")
        logical_keys.add(logical_key)
        effect_ids.add(expected_effect_id)
        status = _text(record.get("status"), field="status", max_bytes=64)
        if status not in EFFECT_STATUSES:
            raise ContinuationRoundError(f"unsupported effect status: {status}", code="effect_journal_invalid")
        prepared_generation = _generation(record.get("prepared_generation"), field="prepared_generation")
        last_generation = _generation(record.get("last_generation"), field="last_generation")
        if last_generation < prepared_generation:
            raise ContinuationRoundError(
                "effect last_generation predates prepared_generation",
                code="effect_journal_invalid",
            )
        effects.append(
            {
                "schema_version": EFFECT_RECORD_SCHEMA,
                "effect_id": expected_effect_id,
                "logical_key": logical_key,
                "kind": kind,
                "external_id": _optional_text(record.get("external_id"), field="external_id"),
                "status": status,
                "milestone": _optional_text(record.get("milestone"), field="milestone", max_bytes=MAX_KEY_BYTES),
                "evidence_refs": _refs(record.get("evidence_refs")),
                "prepared_generation": prepared_generation,
                "last_generation": last_generation,
                "prepared_at": _timestamp(record.get("prepared_at"), field="prepared_at"),
                "updated_at": _timestamp(record.get("updated_at"), field="updated_at"),
            }
        )
    result = {"schema_version": EFFECT_JOURNAL_SCHEMA, "task_id": expected_task, "effects": effects}
    _bounded(result)
    return result


def begin_round(
    journal: Mapping[str, Any],
    *,
    task_id: str,
    generation: int,
    lease_id: str,
    runner_id: str,
    now: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = validate_round_journal(journal, task_id=task_id)
    generation = _generation(generation)
    if any(record["generation"] == generation for record in current["rounds"]):
        raise ContinuationRoundError("round generation already exists", code="round_generation_conflict")
    rounds = list(current["rounds"])
    if len(rounds) >= MAX_ROUNDS:
        removable = next((index for index, record in enumerate(rounds) if record["phase"] == "released"), None)
        if removable is None:
            raise ContinuationRoundError("round journal has no safely prunable entry", code="round_journal_full")
        rounds.pop(removable)
    timestamp = _timestamp(now, field="now")
    record = {
        "schema_version": ROUND_RECORD_SCHEMA,
        "generation": generation,
        "lease_id": _text(lease_id, field="lease_id", max_bytes=128),
        "runner_id": _text(runner_id, field="runner_id", max_bytes=MAX_KEY_BYTES),
        "phase": "claimed",
        "milestone": "claimed",
        "evidence_refs": [],
        "started_at": timestamp,
        "updated_at": timestamp,
        "ended_at": None,
    }
    rounds.append(record)
    updated = validate_round_journal(
        {"schema_version": ROUND_JOURNAL_SCHEMA, "task_id": task_id, "rounds": rounds},
        task_id=task_id,
    )
    return updated, dict(updated["rounds"][-1])


def update_round(
    journal: Mapping[str, Any],
    *,
    task_id: str,
    generation: int,
    lease_id: str,
    phase: str | None,
    milestone: str | None,
    evidence_refs: Iterable[str],
    now: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = validate_round_journal(journal, task_id=task_id)
    generation = _generation(generation)
    target = next(
        (
            record
            for record in current["rounds"]
            if record["generation"] == generation and record["lease_id"] == lease_id
        ),
        None,
    )
    if target is None:
        raise ContinuationRoundError("active round is missing from journal", code="round_record_missing")
    current_phase = str(target["phase"])
    next_phase = current_phase if phase is None else _text(phase, field="phase", max_bytes=64)
    if next_phase == "released":
        raise ContinuationRoundError("progress cannot mark a round released", code="round_phase_invalid")
    if next_phase not in ROUND_PHASES or next_phase not in ROUND_TRANSITIONS[current_phase]:
        raise ContinuationRoundError(
            f"invalid round phase transition: {current_phase} -> {next_phase}",
            code="round_phase_invalid",
        )
    updated_record = dict(target)
    updated_record["phase"] = next_phase
    if milestone is not None:
        updated_record["milestone"] = _text(milestone, field="milestone", max_bytes=MAX_KEY_BYTES)
    updated_record["evidence_refs"] = _append_refs(updated_record["evidence_refs"], evidence_refs)
    updated_record["updated_at"] = _timestamp(now, field="now")
    rounds = [updated_record if record is target else record for record in current["rounds"]]
    updated = validate_round_journal(
        {"schema_version": ROUND_JOURNAL_SCHEMA, "task_id": task_id, "rounds": rounds},
        task_id=task_id,
    )
    result = next(record for record in updated["rounds"] if record["generation"] == generation)
    return updated, dict(result)


def finish_round(
    journal: Mapping[str, Any],
    *,
    task_id: str,
    generation: int,
    lease_id: str,
    reconciling: bool,
    milestone: str,
    evidence_refs: Iterable[str],
    now: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = validate_round_journal(journal, task_id=task_id)
    generation = _generation(generation)
    target = next(
        (
            record
            for record in current["rounds"]
            if record["generation"] == generation and record["lease_id"] == lease_id
        ),
        None,
    )
    if target is None:
        raise ContinuationRoundError("active round is missing from journal", code="round_record_missing")
    updated_record = dict(target)
    updated_record["phase"] = "reconciling" if reconciling else "released"
    updated_record["milestone"] = _text(milestone, field="milestone", max_bytes=MAX_KEY_BYTES)
    updated_record["evidence_refs"] = _append_refs(updated_record["evidence_refs"], evidence_refs)
    timestamp = _timestamp(now, field="now")
    updated_record["updated_at"] = timestamp
    updated_record["ended_at"] = timestamp
    rounds = [updated_record if record is target else record for record in current["rounds"]]
    updated = validate_round_journal(
        {"schema_version": ROUND_JOURNAL_SCHEMA, "task_id": task_id, "rounds": rounds},
        task_id=task_id,
    )
    result = next(record for record in updated["rounds"] if record["generation"] == generation)
    return updated, dict(result)


def prepare_effect(
    journal: Mapping[str, Any],
    *,
    task_id: str,
    generation: int,
    logical_key: str,
    kind: str,
    external_id: str | None,
    milestone: str | None,
    evidence_refs: Iterable[str],
    now: str,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    current = validate_effect_journal(journal, task_id=task_id)
    generation = _generation(generation)
    logical_key = _text(logical_key, field="logical_key", max_bytes=MAX_KEY_BYTES)
    kind = _text(kind, field="kind", max_bytes=MAX_KEY_BYTES)
    external_id = _optional_text(external_id, field="external_id")
    existing = next((record for record in current["effects"] if record["logical_key"] == logical_key), None)
    if existing is not None:
        if existing["kind"] != kind:
            raise ContinuationRoundError(
                "logical effect key already exists with another kind",
                code="effect_identity_conflict",
            )
        if external_id is not None and existing["external_id"] != external_id:
            raise ContinuationRoundError(
                "logical effect key already exists with another external id",
                code="effect_identity_conflict",
            )
        return current, dict(existing), False
    if len(current["effects"]) >= MAX_EFFECTS:
        raise ContinuationRoundError("effect journal is full", code="effect_journal_full")
    timestamp = _timestamp(now, field="now")
    record = {
        "schema_version": EFFECT_RECORD_SCHEMA,
        "effect_id": effect_id(task_id, logical_key, kind),
        "logical_key": logical_key,
        "kind": kind,
        "external_id": external_id,
        "status": "prepared",
        "milestone": (
            _text(milestone, field="milestone", max_bytes=MAX_KEY_BYTES)
            if milestone is not None
            else "prepared"
        ),
        "evidence_refs": _append_refs([], evidence_refs),
        "prepared_generation": generation,
        "last_generation": generation,
        "prepared_at": timestamp,
        "updated_at": timestamp,
    }
    updated = validate_effect_journal(
        {
            "schema_version": EFFECT_JOURNAL_SCHEMA,
            "task_id": task_id,
            "effects": [*current["effects"], record],
        },
        task_id=task_id,
    )
    result = next(item for item in updated["effects"] if item["logical_key"] == logical_key)
    return updated, dict(result), True


def update_effect(
    journal: Mapping[str, Any],
    *,
    task_id: str,
    generation: int,
    logical_key: str,
    status: str | None,
    external_id: str | None,
    milestone: str | None,
    evidence_refs: Iterable[str],
    now: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = validate_effect_journal(journal, task_id=task_id)
    generation = _generation(generation)
    logical_key = _text(logical_key, field="logical_key", max_bytes=MAX_KEY_BYTES)
    target = next((record for record in current["effects"] if record["logical_key"] == logical_key), None)
    if target is None:
        raise ContinuationRoundError("effect key is not prepared", code="effect_missing")
    current_status = str(target["status"])
    next_status = current_status if status is None else _text(status, field="status", max_bytes=64)
    if next_status not in EFFECT_STATUSES or next_status not in EFFECT_TRANSITIONS[current_status]:
        raise ContinuationRoundError(
            f"invalid effect status transition: {current_status} -> {next_status}",
            code="effect_status_invalid",
        )
    updated_record = dict(target)
    if external_id is not None:
        external_id = _text(external_id, field="external_id")
        if updated_record["external_id"] not in {None, external_id}:
            raise ContinuationRoundError(
                "effect external id cannot be replaced",
                code="effect_identity_conflict",
            )
        updated_record["external_id"] = external_id
    updated_record["status"] = next_status
    if milestone is not None:
        updated_record["milestone"] = _text(milestone, field="milestone", max_bytes=MAX_KEY_BYTES)
    updated_record["evidence_refs"] = _append_refs(updated_record["evidence_refs"], evidence_refs)
    updated_record["last_generation"] = generation
    updated_record["updated_at"] = _timestamp(now, field="now")
    effects = [updated_record if record is target else record for record in current["effects"]]
    updated = validate_effect_journal(
        {"schema_version": EFFECT_JOURNAL_SCHEMA, "task_id": task_id, "effects": effects},
        task_id=task_id,
    )
    result = next(item for item in updated["effects"] if item["logical_key"] == logical_key)
    return updated, dict(result)


def effect_summary(journal: Mapping[str, Any], *, task_id: str) -> dict[str, Any]:
    current = validate_effect_journal(journal, task_id=task_id)
    by_status = {status: 0 for status in sorted(EFFECT_STATUSES)}
    unresolved: list[str] = []
    terminal: list[str] = []
    for record in current["effects"]:
        status = str(record["status"])
        by_status[status] += 1
        if status in TERMINAL_EFFECT_STATUSES:
            terminal.append(str(record["logical_key"]))
        else:
            unresolved.append(str(record["logical_key"]))
    return {
        "total": len(current["effects"]),
        "by_status": by_status,
        "unresolved": unresolved,
        "terminal": terminal,
    }


def latest_round(journal: Mapping[str, Any], *, task_id: str) -> dict[str, Any] | None:
    current = validate_round_journal(journal, task_id=task_id)
    if not current["rounds"]:
        return None
    return dict(current["rounds"][-1])


__all__ = [
    "EFFECT_JOURNAL_SCHEMA",
    "EFFECT_STATUSES",
    "MAX_EFFECTS",
    "MAX_ROUNDS",
    "ROUND_JOURNAL_SCHEMA",
    "ROUND_PHASES",
    "TERMINAL_EFFECT_STATUSES",
    "ContinuationRoundError",
    "begin_round",
    "effect_summary",
    "empty_effect_journal",
    "empty_round_journal",
    "finish_round",
    "latest_round",
    "prepare_effect",
    "update_effect",
    "update_round",
    "validate_effect_journal",
    "validate_round_journal",
]
