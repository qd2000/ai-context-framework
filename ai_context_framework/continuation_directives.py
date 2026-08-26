"""Durable user-authority directives for bounded continuation tasks.

Directives are deliberately small and mechanical.  They are not a second task
plan and they do not interpret user prose.  The journal only records auditable
user/agent authority events and projects the currently actionable inbox.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


DIRECTIVE_JOURNAL_SCHEMA = "acf.continuation.directive-journal.v1"
DIRECTIVE_EVENT_SCHEMA = "acf.continuation.directive-event.v1"
DIRECTIVE_SCHEMA = "acf.continuation.directive.v1"
DIRECTIVE_CONTEXT_SCHEMA = "acf.continuation.directive-context.v1"

DIRECTIVE_KINDS = frozenset({"requirement", "priority_change", "constraint", "plan_change"})
DIRECTIVE_LIFETIMES = frozenset({"transient", "durable", "unspecified"})
DIRECTIVE_STATUSES = frozenset({"pending", "adopted", "resolved", "superseded", "withdrawn"})
DIRECTIVE_EVENT_KINDS = frozenset({"added", "adopted", "resolved", "superseded", "withdrawn"})
TERMINAL_DIRECTIVE_STATUSES = frozenset({"resolved", "superseded", "withdrawn"})

MAX_DIRECTIVE_TEXT_BYTES = 4096
MAX_DIRECTIVE_REF_BYTES = 4096
MAX_DIRECTIVE_REFS = 64
MAX_ACTIVE_DIRECTIVES = 64
MAX_DIRECTIVE_EVENTS = 2048
MAX_DIRECTIVE_JOURNAL_BYTES = 1024 * 1024
MIN_PRIORITY = 0
MAX_PRIORITY = 100

_DIRECTIVE_ID_RE = re.compile(r"dir-[0-9a-f]{20}")
_EVENT_ID_RE = re.compile(r"dev-[0-9a-f]{20}")
_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(?:-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|"
    r"\b(?:api[_ -]?key|password|passwd|fence[_ -]?token|credential|access[_ -]?token|"
    r"refresh[_ -]?token|token|license(?:[_ -]?key)?|private[_ -]?key)\b\s*[:=]\s*\S+|"
    r"\bsk-[A-Za-z0-9_-]{20,})"
)


class DirectiveError(ValueError):
    def __init__(self, message: str, *, code: str = "directive_invalid") -> None:
        super().__init__(message)
        self.code = code


def empty_journal(task_id: str) -> dict[str, Any]:
    return {
        "schema_version": DIRECTIVE_JOURNAL_SCHEMA,
        "task_id": _nonempty(task_id, field="task_id"),
        "revision": 0,
        "events": [],
    }


def load_journal(path: Path, *, task_id: str) -> dict[str, Any]:
    if not path.exists():
        return empty_journal(task_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DirectiveError("directive journal is unreadable", code="directive_journal_invalid") from exc
    if not isinstance(payload, dict):
        raise DirectiveError("directive journal must be a JSON object", code="directive_journal_invalid")
    return validate_journal(payload, task_id=task_id)


def validate_journal(payload: Mapping[str, Any], *, task_id: str) -> dict[str, Any]:
    if payload.get("schema_version") != DIRECTIVE_JOURNAL_SCHEMA:
        raise DirectiveError("directive journal schema is invalid", code="directive_journal_invalid")
    if payload.get("task_id") != task_id:
        raise DirectiveError("directive journal task identity mismatch", code="directive_journal_invalid")
    revision = payload.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise DirectiveError("directive journal revision is invalid", code="directive_journal_invalid")
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        raise DirectiveError("directive journal events must be a list", code="directive_journal_invalid")
    if len(raw_events) > MAX_DIRECTIVE_EVENTS:
        raise DirectiveError(
            f"directive journal exceeds {MAX_DIRECTIVE_EVENTS} events",
            code="directive_capacity_exceeded",
        )
    events: list[dict[str, Any]] = []
    previous_revision = 0
    for value in raw_events:
        if not isinstance(value, Mapping):
            raise DirectiveError("directive event must be an object", code="directive_journal_invalid")
        event_revision = value.get("revision")
        if (
            isinstance(event_revision, bool)
            or not isinstance(event_revision, int)
            or event_revision < 1
            or event_revision <= previous_revision
            or event_revision > revision
        ):
            raise DirectiveError(
                "directive event revision sequence is invalid",
                code="directive_journal_invalid",
            )
        events.append(_validate_event(value, expected_revision=event_revision))
        previous_revision = event_revision
    if events and int(events[-1]["revision"]) > revision:
        raise DirectiveError("directive journal revision is behind events", code="directive_journal_invalid")
    encoded = json.dumps(
        {
            "schema_version": DIRECTIVE_JOURNAL_SCHEMA,
            "task_id": task_id,
            "revision": revision,
            "events": events,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > MAX_DIRECTIVE_JOURNAL_BYTES:
        raise DirectiveError(
            f"directive journal exceeds {MAX_DIRECTIVE_JOURNAL_BYTES} bytes",
            code="directive_capacity_exceeded",
        )
    projected = _project_events(events)
    active_count = sum(
        1 for item in projected.values() if item["status"] in {"pending", "adopted"}
    )
    if active_count > MAX_ACTIVE_DIRECTIVES:
        raise DirectiveError(
            f"active directive inbox exceeds {MAX_ACTIVE_DIRECTIVES} items",
            code="directive_capacity_exceeded",
        )
    return {
        "schema_version": DIRECTIVE_JOURNAL_SCHEMA,
        "task_id": task_id,
        "revision": revision,
        "events": events,
    }


def add_directive(
    journal: Mapping[str, Any],
    *,
    kind: str,
    priority: int,
    text: str,
    created_at: str,
    actor: str,
    lifetime: str = "unspecified",
    evidence_refs: Sequence[str] = (),
    supersedes: Sequence[str] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = validate_journal(journal, task_id=str(journal.get("task_id") or ""))
    projected = project_directives(current)
    active_count = sum(1 for item in projected if item["status"] in {"pending", "adopted"})
    if active_count >= MAX_ACTIVE_DIRECTIVES:
        raise DirectiveError(
            f"active directive inbox exceeds {MAX_ACTIVE_DIRECTIVES} items",
            code="directive_capacity_exceeded",
        )
    normalized_kind = _kind(kind)
    normalized_priority = _priority(priority)
    normalized_text = _text(text, field="text")
    normalized_actor = _text(actor, field="actor", max_bytes=256)
    normalized_lifetime = _lifetime(lifetime)
    normalized_refs = _refs(evidence_refs)
    normalized_supersedes = _directive_ids(supersedes, field="supersedes")
    known = {str(item["id"]) for item in projected}
    missing = [value for value in normalized_supersedes if value not in known]
    if missing:
        raise DirectiveError(f"superseded directive does not exist: {missing[0]}", code="directive_not_found")
    directive_id = _new_id("dir")
    event = {
        "schema_version": DIRECTIVE_EVENT_SCHEMA,
        "event_id": _new_id("dev"),
        "event_kind": "added",
        "directive_id": directive_id,
        "occurred_at": _timestamp(created_at, field="created_at"),
        "actor": normalized_actor,
        "kind": normalized_kind,
        "lifetime": normalized_lifetime,
        "priority": normalized_priority,
        "text": normalized_text,
        "supersedes": normalized_supersedes,
        "evidence_refs": normalized_refs,
        "note": None,
    }
    updated = _append_event(current, event)
    directive = show_directive(updated, directive_id)
    return updated, directive


def adopt_directive(
    journal: Mapping[str, Any],
    *,
    directive_id: str,
    occurred_at: str,
    actor: str,
    evidence_refs: Sequence[str] = (),
    note: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    current = validate_journal(journal, task_id=str(journal.get("task_id") or ""))
    item = show_directive(current, directive_id)
    if item["status"] == "adopted":
        return current, item, False
    if item["lifetime"] in {"durable", "transient"} and not _refs(evidence_refs):
        raise DirectiveError(
            f"{item['lifetime']} directive adoption requires durable evidence",
            code="directive_adoption_evidence_required",
        )
    return _transition(
        current,
        directive_id=directive_id,
        event_kind="adopted",
        allowed_from={"pending"},
        idempotent_status="adopted",
        occurred_at=occurred_at,
        actor=actor,
        evidence_refs=evidence_refs,
        note=note,
    )


def resolve_directive(
    journal: Mapping[str, Any],
    *,
    directive_id: str,
    occurred_at: str,
    actor: str,
    evidence_refs: Sequence[str] = (),
    note: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    return _transition(
        journal,
        directive_id=directive_id,
        event_kind="resolved",
        allowed_from={"pending", "adopted"},
        idempotent_status="resolved",
        occurred_at=occurred_at,
        actor=actor,
        evidence_refs=evidence_refs,
        note=note,
    )


def withdraw_directive(
    journal: Mapping[str, Any],
    *,
    directive_id: str,
    occurred_at: str,
    actor: str,
    evidence_refs: Sequence[str] = (),
    note: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    if not _refs(evidence_refs):
        raise DirectiveError(
            "directive withdrawal requires user or authoritative cancellation evidence",
            code="directive_withdrawal_evidence_required",
        )
    return _transition(
        journal,
        directive_id=directive_id,
        event_kind="withdrawn",
        allowed_from={"pending", "adopted"},
        idempotent_status="withdrawn",
        occurred_at=occurred_at,
        actor=actor,
        evidence_refs=evidence_refs,
        note=note,
    )


def supersede_directive(
    journal: Mapping[str, Any],
    *,
    directive_id: str,
    kind: str,
    priority: int,
    text: str,
    occurred_at: str,
    actor: str,
    lifetime: str | None = None,
    evidence_refs: Sequence[str] = (),
    note: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    current = validate_journal(journal, task_id=str(journal.get("task_id") or ""))
    prior = show_directive(current, directive_id)
    if prior["status"] not in {"pending", "adopted"}:
        raise DirectiveError(
            f"directive cannot be superseded from status {prior['status']}",
            code="directive_transition_invalid",
        )
    normalized_kind = _kind(kind)
    normalized_priority = _priority(priority)
    normalized_text = _text(text, field="text")
    normalized_actor = _text(actor, field="actor", max_bytes=256)
    normalized_lifetime = _lifetime(lifetime or str(prior.get("lifetime") or "unspecified"))
    normalized_refs = _refs(evidence_refs)
    replacement_id = _new_id("dir")
    replacement_event = {
        "schema_version": DIRECTIVE_EVENT_SCHEMA,
        "event_id": _new_id("dev"),
        "event_kind": "added",
        "directive_id": replacement_id,
        "occurred_at": _timestamp(occurred_at, field="occurred_at"),
        "actor": normalized_actor,
        "kind": normalized_kind,
        "lifetime": normalized_lifetime,
        "priority": normalized_priority,
        "text": normalized_text,
        "supersedes": [str(prior["id"])],
        "evidence_refs": normalized_refs,
        "note": None,
    }
    event = _transition_event(
        directive_id=directive_id,
        event_kind="superseded",
        occurred_at=occurred_at,
        actor=actor,
        evidence_refs=evidence_refs,
        note=note or f"Superseded by {replacement_id}",
        replacement_id=replacement_id,
    )
    # A supersede is one logical replacement and has zero net active-inbox
    # growth.  Append the replacement+transition as one in-memory batch so a
    # full (64/64) inbox can still replace an active directive without ever
    # persisting an over-capacity intermediate journal.
    updated = _append_events(current, [replacement_event, event])
    return updated, show_directive(updated, directive_id), show_directive(updated, replacement_id)


def list_directives(journal: Mapping[str, Any], *, status: str | None = None) -> list[dict[str, Any]]:
    items = project_directives(journal)
    if status is not None:
        normalized = status.strip().lower()
        if normalized not in DIRECTIVE_STATUSES:
            raise DirectiveError(f"unsupported directive status: {status}")
        items = [item for item in items if item["status"] == normalized]
    return sorted(
        items,
        key=lambda item: (
            0 if item["status"] == "pending" else 1,
            -int(item["priority"]),
            -int(item["last_revision"]),
        ),
    )


def show_directive(journal: Mapping[str, Any], directive_id: str) -> dict[str, Any]:
    normalized = _directive_id(directive_id)
    for item in project_directives(journal):
        if item["id"] == normalized:
            return item
    raise DirectiveError(f"directive not found: {normalized}", code="directive_not_found")


def project_directives(journal: Mapping[str, Any]) -> list[dict[str, Any]]:
    task_id = str(journal.get("task_id") or "")
    current = validate_journal(journal, task_id=task_id)
    return list(_project_events(list(current.get("events") or [])).values())


def directive_context(journal: Mapping[str, Any]) -> dict[str, Any]:
    current = validate_journal(journal, task_id=str(journal.get("task_id") or ""))
    projected = list(_project_events(current["events"]).values())
    pending = sorted(
        (item for item in projected if item["status"] == "pending"),
        key=lambda item: (-int(item["priority"]), -int(item["last_revision"])),
    )
    digest_payload = [
        {
            "id": item["id"],
            "kind": item["kind"],
            "priority": item["priority"],
            "text": item["text"],
            "supersedes": item["supersedes"],
        }
        for item in pending
    ]
    digest = hashlib.sha256(
        json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    latest = max(pending, key=lambda item: int(item["last_revision"])) if pending else None
    adopted = [item for item in projected if item["status"] == "adopted"]
    active = [item for item in projected if item["status"] in {"pending", "adopted"}]
    return {
        "schema_version": DIRECTIVE_CONTEXT_SCHEMA,
        "revision": int(current["revision"]),
        "digest": digest,
        "pending_count": len(pending),
        "adopted_count": len(adopted),
        "active_count": len(active),
        "pressure": journal_pressure(current),
        "authority_refresh_required": bool(pending),
        "latest_directive": _context_item(latest) if latest else None,
        "pending": [_context_item(item) for item in pending],
    }


def _transition(
    journal: Mapping[str, Any],
    *,
    directive_id: str,
    event_kind: str,
    allowed_from: set[str],
    idempotent_status: str,
    occurred_at: str,
    actor: str,
    evidence_refs: Sequence[str],
    note: str | None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    current = validate_journal(journal, task_id=str(journal.get("task_id") or ""))
    item = show_directive(current, directive_id)
    if item["status"] == idempotent_status:
        return current, item, False
    if item["status"] not in allowed_from:
        raise DirectiveError(
            f"directive cannot transition from {item['status']} to {idempotent_status}",
            code="directive_transition_invalid",
        )
    event = _transition_event(
        directive_id=str(item["id"]),
        event_kind=event_kind,
        occurred_at=occurred_at,
        actor=actor,
        evidence_refs=evidence_refs,
        note=note,
    )
    updated = _append_event(current, event)
    return updated, show_directive(updated, str(item["id"])), True


def _transition_event(
    *,
    directive_id: str,
    event_kind: str,
    occurred_at: str,
    actor: str,
    evidence_refs: Sequence[str],
    note: str | None,
    replacement_id: str | None = None,
) -> dict[str, Any]:
    if event_kind not in DIRECTIVE_EVENT_KINDS - {"added"}:
        raise DirectiveError(f"unsupported transition event: {event_kind}")
    return {
        "schema_version": DIRECTIVE_EVENT_SCHEMA,
        "event_id": _new_id("dev"),
        "event_kind": event_kind,
        "directive_id": _directive_id(directive_id),
        "occurred_at": _timestamp(occurred_at, field="occurred_at"),
        "actor": _text(actor, field="actor", max_bytes=256),
        "evidence_refs": _refs(evidence_refs),
        "note": _text(note, field="note") if note else None,
        "replacement_id": _directive_id(replacement_id) if replacement_id else None,
    }


def _append_event(journal: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    return _append_events(journal, [event])


def _append_events(
    journal: Mapping[str, Any], events_to_add: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    current = validate_journal(journal, task_id=str(journal.get("task_id") or ""))
    revision = int(current["revision"])
    events = list(current["events"])
    for event in events_to_add:
        revision += 1
        value = dict(event)
        value["revision"] = revision
        events.append(value)
    candidate = {
        "schema_version": DIRECTIVE_JOURNAL_SCHEMA,
        "task_id": current["task_id"],
        "revision": revision,
        "events": events,
    }
    return validate_journal(candidate, task_id=str(current["task_id"]))


def _project_events(events: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    projected: dict[str, dict[str, Any]] = {}
    for event in events:
        event_kind = str(event["event_kind"])
        directive_id = str(event["directive_id"])
        if event_kind == "added":
            if directive_id in projected:
                raise DirectiveError("duplicate directive id in journal", code="directive_journal_invalid")
            projected[directive_id] = {
                "schema_version": DIRECTIVE_SCHEMA,
                "id": directive_id,
                "created_at": event["occurred_at"],
                "updated_at": event["occurred_at"],
                "kind": event["kind"],
                "lifetime": event.get("lifetime", "unspecified"),
                "priority": event["priority"],
                "text": event["text"],
                "status": "pending",
                "supersedes": list(event.get("supersedes") or []),
                "superseded_by": None,
                "evidence_refs": list(event.get("evidence_refs") or []),
                "last_revision": event["revision"],
                "status_changed_at": event["occurred_at"],
                "adoption_evidence_refs": [],
            }
            continue
        item = projected.get(directive_id)
        if item is None:
            raise DirectiveError("directive transition precedes add event", code="directive_journal_invalid")
        status = str(item["status"])
        expected_from = {
            "adopted": {"pending"},
            "resolved": {"pending", "adopted"},
            "superseded": {"pending", "adopted"},
            "withdrawn": {"pending", "adopted"},
        }[event_kind]
        target = event_kind
        if status not in expected_from:
            raise DirectiveError(
                f"invalid directive event transition: {status}->{target}",
                code="directive_journal_invalid",
            )
        item["status"] = target
        item["updated_at"] = event["occurred_at"]
        item["last_revision"] = event["revision"]
        item["status_changed_at"] = event["occurred_at"]
        item["evidence_refs"] = list(
            dict.fromkeys([*item["evidence_refs"], *(event.get("evidence_refs") or [])])
        )[-MAX_DIRECTIVE_REFS:]
        if event_kind == "adopted":
            item["adoption_evidence_refs"] = list(event.get("evidence_refs") or [])
        if event_kind == "superseded":
            replacement_id = event.get("replacement_id")
            if replacement_id not in projected:
                raise DirectiveError(
                    "superseding replacement directive is missing",
                    code="directive_journal_invalid",
                )
            item["superseded_by"] = replacement_id
    return projected


def _validate_event(value: Any, *, expected_revision: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DirectiveError("directive event must be an object", code="directive_journal_invalid")
    if value.get("schema_version") != DIRECTIVE_EVENT_SCHEMA:
        raise DirectiveError("directive event schema is invalid", code="directive_journal_invalid")
    revision = value.get("revision")
    if revision != expected_revision:
        raise DirectiveError("directive event revision sequence is invalid", code="directive_journal_invalid")
    event_id = str(value.get("event_id") or "")
    if not _EVENT_ID_RE.fullmatch(event_id):
        raise DirectiveError("directive event id is invalid", code="directive_journal_invalid")
    event_kind = str(value.get("event_kind") or "")
    if event_kind not in DIRECTIVE_EVENT_KINDS:
        raise DirectiveError("directive event kind is invalid", code="directive_journal_invalid")
    directive_id = _directive_id(str(value.get("directive_id") or ""))
    event: dict[str, Any] = {
        "schema_version": DIRECTIVE_EVENT_SCHEMA,
        "event_id": event_id,
        "event_kind": event_kind,
        "directive_id": directive_id,
        "revision": expected_revision,
        "occurred_at": _timestamp(str(value.get("occurred_at") or ""), field="occurred_at"),
        "actor": _text(str(value.get("actor") or ""), field="actor", max_bytes=256),
        "evidence_refs": _refs(value.get("evidence_refs") or []),
        "note": _text(str(value["note"]), field="note") if value.get("note") else None,
    }
    if event_kind == "added":
        event.update(
            {
                "kind": _kind(str(value.get("kind") or "")),
                "lifetime": _lifetime(str(value.get("lifetime") or "unspecified")),
                "priority": _priority(value.get("priority")),
                "text": _text(str(value.get("text") or ""), field="text"),
                "supersedes": _directive_ids(value.get("supersedes") or [], field="supersedes"),
            }
        )
    elif event_kind == "superseded":
        event["replacement_id"] = _directive_id(str(value.get("replacement_id") or ""))
    else:
        event["replacement_id"] = None
    return event


def _context_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "kind": item["kind"],
        "lifetime": item.get("lifetime", "unspecified"),
        "priority": item["priority"],
        "text": item["text"],
        "created_at": item["created_at"],
        "supersedes": list(item.get("supersedes") or []),
        "evidence_refs": list(item.get("evidence_refs") or []),
    }


def journal_pressure(journal: Mapping[str, Any]) -> dict[str, Any]:
    current = validate_journal(journal, task_id=str(journal.get("task_id") or ""))
    projected = list(_project_events(current["events"]).values())
    active_count = sum(1 for item in projected if item["status"] in {"pending", "adopted"})
    encoded = json.dumps(
        current,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    event_count = len(current["events"])
    byte_count = len(encoded)
    return {
        "active_count": active_count,
        "active_limit": MAX_ACTIVE_DIRECTIVES,
        "event_count": event_count,
        "event_limit": MAX_DIRECTIVE_EVENTS,
        "byte_count": byte_count,
        "byte_limit": MAX_DIRECTIVE_JOURNAL_BYTES,
        "event_ratio": event_count / MAX_DIRECTIVE_EVENTS,
        "byte_ratio": byte_count / MAX_DIRECTIVE_JOURNAL_BYTES,
        "active_ratio": active_count / MAX_ACTIVE_DIRECTIVES,
    }


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:20]}"


def _nonempty(value: str, *, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise DirectiveError(f"{field} must be non-empty")
    return cleaned


def _text(value: str, *, field: str, max_bytes: int = MAX_DIRECTIVE_TEXT_BYTES) -> str:
    cleaned = _nonempty(value, field=field)
    if len(cleaned.encode("utf-8")) > max_bytes:
        raise DirectiveError(f"{field} exceeds {max_bytes} bytes", code="directive_bounds_exceeded")
    if _SENSITIVE_VALUE_RE.search(cleaned):
        raise DirectiveError(
            f"sensitive credential-like value refused in {field}",
            code="directive_sensitive_value_refused",
        )
    return cleaned


def _refs(values: Sequence[Any]) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise DirectiveError("evidence_refs must be a list", code="directive_bounds_exceeded")
    refs: list[str] = []
    for value in values:
        ref = _text(str(value), field="evidence_ref", max_bytes=MAX_DIRECTIVE_REF_BYTES)
        if ref not in refs:
            refs.append(ref)
    if len(refs) > MAX_DIRECTIVE_REFS:
        raise DirectiveError(
            f"evidence_refs exceeds {MAX_DIRECTIVE_REFS} items",
            code="directive_bounds_exceeded",
        )
    return refs


def _directive_ids(values: Sequence[Any], *, field: str) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise DirectiveError(f"{field} must be a list")
    result: list[str] = []
    for value in values:
        normalized = _directive_id(str(value))
        if normalized not in result:
            result.append(normalized)
    if len(result) > MAX_DIRECTIVE_REFS:
        raise DirectiveError(f"{field} exceeds {MAX_DIRECTIVE_REFS} items", code="directive_bounds_exceeded")
    return result


def _directive_id(value: str) -> str:
    cleaned = value.strip().lower()
    if not _DIRECTIVE_ID_RE.fullmatch(cleaned):
        raise DirectiveError(f"invalid directive id: {value}", code="directive_id_invalid")
    return cleaned


def _kind(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in DIRECTIVE_KINDS:
        raise DirectiveError(f"unsupported directive kind: {value}")
    return cleaned


def _lifetime(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in DIRECTIVE_LIFETIMES:
        raise DirectiveError(f"unsupported directive lifetime: {value}")
    return cleaned


def _priority(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DirectiveError("directive priority must be an integer")
    if value < MIN_PRIORITY or value > MAX_PRIORITY:
        raise DirectiveError(f"directive priority must be between {MIN_PRIORITY} and {MAX_PRIORITY}")
    return value


def _timestamp(value: str, *, field: str) -> str:
    cleaned = _nonempty(value, field=field)
    normalized = cleaned.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise DirectiveError(f"{field} is not a valid timestamp") from exc
    if parsed.tzinfo is None:
        raise DirectiveError(f"{field} must include timezone")
    return cleaned


__all__ = [
    "DIRECTIVE_CONTEXT_SCHEMA",
    "DIRECTIVE_EVENT_SCHEMA",
    "DIRECTIVE_JOURNAL_SCHEMA",
    "DIRECTIVE_KINDS",
    "DIRECTIVE_LIFETIMES",
    "DIRECTIVE_SCHEMA",
    "DIRECTIVE_STATUSES",
    "TERMINAL_DIRECTIVE_STATUSES",
    "DirectiveError",
    "add_directive",
    "adopt_directive",
    "directive_context",
    "empty_journal",
    "journal_pressure",
    "list_directives",
    "load_journal",
    "project_directives",
    "resolve_directive",
    "show_directive",
    "supersede_directive",
    "validate_journal",
    "withdraw_directive",
]
