"""Deterministic user-level authorization for Workstream closeout actions.

The closeout ledger deliberately lives under ``ACF_HOME`` rather than in the
project checkout.  Project Markdown remains the fact/plan authority; this
module only records the durable *authorization* that decides whether ACF may
perform a lifecycle transition automatically or must wait for explicit human
approval evidence.

Policy and approval evidence are separate record types.  A broad auto-close
policy therefore never becomes evidence that a specific Workstream received a
human approval, while an approval for one Workstream/action never transfers to
another action or Workstream.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ai_context_framework.front_matter import format_front_matter, parse_front_matter
from ai_context_framework.git_support import discover_git_project
from ai_context_framework.observability import acf_home, atomic_write_text, usage_project_dir
from ai_context_framework.paths import infer_project_root, resolve_status_location


LEDGER_SCHEMA = "acf.workstream.closeout-authorization.v1"
EVENT_SCHEMA = "acf.workstream.closeout-authorization-event.v1"
RESOLUTION_SCHEMA = "acf.workstream.closeout-authorization-resolution.v1"

CLOSEOUT_ACTIONS = frozenset({"ready", "merge", "done", "archive"})
POLICY_DECISIONS = frozenset({"auto", "manual", "deny"})
AUTHORIZATION_DISPOSITIONS = frozenset(
    {"auto_authorized", "human_approved", "approval_required", "denied"}
)
WORKSTREAM_CLASSES = frozenset({"ordinary", "merge", "maintenance"})

MAX_EVENTS = 2048
MAX_LEDGER_BYTES = 1024 * 1024
LOCK_TIMEOUT_SECONDS = 5.0


class CloseoutAuthorizationError(ValueError):
    """Validated closeout authorization input/storage failure."""

    def __init__(self, message: str, *, code: str = "closeout_authorization_invalid") -> None:
        super().__init__(message)
        self.code = code


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_project_root(project_root: Path) -> Path:
    resolved = project_root.resolve()
    try:
        return discover_git_project(resolved).config.primary_checkout.resolve()
    except (SystemExit, OSError):
        return resolved


def project_identity(path: Path | None) -> tuple[Path, Path]:
    location = resolve_status_location(path)
    project_root = canonical_project_root(location.project_root)
    return project_root, location.context_root.resolve()


def authorization_dir(project_root: Path) -> Path:
    canonical = canonical_project_root(project_root)
    return usage_project_dir(canonical) / "closeout"


def ledger_path(project_root: Path) -> Path:
    return authorization_dir(project_root) / "authorization.json"


def lock_path(project_root: Path) -> Path:
    return authorization_dir(project_root) / "authorization.lock"


def empty_ledger(project_root: Path) -> dict[str, Any]:
    canonical = canonical_project_root(project_root)
    return {
        "schema_version": LEDGER_SCHEMA,
        "project_id": usage_project_dir(canonical).name,
        "canonical_root": str(canonical),
        "revision": 0,
        "events": [],
    }


def load_ledger(project_root: Path) -> dict[str, Any]:
    path = ledger_path(project_root)
    if not path.exists():
        return empty_ledger(project_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CloseoutAuthorizationError(
            "closeout authorization ledger is unreadable",
            code="closeout_authorization_ledger_invalid",
        ) from exc
    if not isinstance(payload, Mapping):
        raise CloseoutAuthorizationError(
            "closeout authorization ledger must be an object",
            code="closeout_authorization_ledger_invalid",
        )
    return validate_ledger(payload, project_root=project_root)


def validate_ledger(payload: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    canonical = canonical_project_root(project_root)
    expected = empty_ledger(canonical)
    if payload.get("schema_version") != LEDGER_SCHEMA:
        raise CloseoutAuthorizationError(
            "closeout authorization ledger schema is invalid",
            code="closeout_authorization_migration_required",
        )
    if payload.get("project_id") != expected["project_id"]:
        raise CloseoutAuthorizationError(
            "closeout authorization project identity mismatch",
            code="closeout_authorization_ledger_invalid",
        )
    if Path(str(payload.get("canonical_root") or "")).resolve() != canonical:
        raise CloseoutAuthorizationError(
            "closeout authorization canonical root mismatch",
            code="closeout_authorization_ledger_invalid",
        )
    revision = payload.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise CloseoutAuthorizationError(
            "closeout authorization revision is invalid",
            code="closeout_authorization_ledger_invalid",
        )
    raw_events = payload.get("events")
    if not isinstance(raw_events, list) or len(raw_events) > MAX_EVENTS:
        raise CloseoutAuthorizationError(
            "closeout authorization event history is invalid or full",
            code="closeout_authorization_capacity_exceeded",
        )
    events: list[dict[str, Any]] = []
    previous = 0
    record_ids: set[str] = set()
    event_ids: set[str] = set()
    for raw in raw_events:
        if not isinstance(raw, Mapping):
            raise CloseoutAuthorizationError(
                "closeout authorization event must be an object",
                code="closeout_authorization_ledger_invalid",
            )
        event = dict(raw)
        if event.get("schema_version") != EVENT_SCHEMA:
            raise CloseoutAuthorizationError(
                "closeout authorization event schema is invalid",
                code="closeout_authorization_ledger_invalid",
            )
        event_revision = event.get("revision")
        if (
            isinstance(event_revision, bool)
            or not isinstance(event_revision, int)
            or event_revision <= previous
            or event_revision > revision
        ):
            raise CloseoutAuthorizationError(
                "closeout authorization event revision sequence is invalid",
                code="closeout_authorization_ledger_invalid",
            )
        previous = event_revision
        event_id = _required_text(event.get("event_id"), field="event_id", max_bytes=128)
        if event_id in event_ids:
            raise CloseoutAuthorizationError(
                f"duplicate closeout authorization event id: {event_id}",
                code="closeout_authorization_ledger_invalid",
            )
        event_ids.add(event_id)
        kind = str(event.get("event_kind") or "")
        if kind not in {"policy_set", "approval_recorded", "revoked"}:
            raise CloseoutAuthorizationError(
                f"unsupported closeout authorization event kind: {kind}",
                code="closeout_authorization_ledger_invalid",
            )
        _parse_timestamp(event.get("occurred_at"), field="occurred_at")
        try:
            _validate_event_payload(event, known_record_ids=record_ids)
        except CloseoutAuthorizationError as exc:
            if exc.code == "closeout_authorization_ledger_invalid":
                raise
            raise CloseoutAuthorizationError(
                str(exc),
                code="closeout_authorization_ledger_invalid",
            ) from exc
        if kind in {"policy_set", "approval_recorded"}:
            record_id = _required_text(event.get("record_id"), field="record_id", max_bytes=128)
            if record_id in record_ids:
                raise CloseoutAuthorizationError(
                    f"duplicate closeout authorization record id: {record_id}",
                    code="closeout_authorization_ledger_invalid",
                )
            record_ids.add(record_id)
        events.append(event)
    if revision != previous:
        raise CloseoutAuthorizationError(
            "closeout authorization ledger revision does not match event history",
            code="closeout_authorization_ledger_invalid",
        )
    encoded = json.dumps(
        {
            "schema_version": LEDGER_SCHEMA,
            "project_id": expected["project_id"],
            "canonical_root": str(canonical),
            "revision": revision,
            "events": events,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > MAX_LEDGER_BYTES:
        raise CloseoutAuthorizationError(
            "closeout authorization ledger exceeds capacity",
            code="closeout_authorization_capacity_exceeded",
        )
    return {
        "schema_version": LEDGER_SCHEMA,
        "project_id": expected["project_id"],
        "canonical_root": str(canonical),
        "revision": revision,
        "events": events,
    }


def workstream_class(workstream_type: str) -> str:
    normalized = (workstream_type or "Task").strip()
    if normalized == "Maintenance":
        return "maintenance"
    if normalized == "Merge":
        return "merge"
    return "ordinary"


def workstream_detail_path(context_root: Path, workstream_id: str) -> Path:
    active = context_root / "active" / "workstreams" / f"{workstream_id}.md"
    if active.is_file():
        return active
    archived = context_root / "archive" / "workstreams" / f"{workstream_id}.md"
    if archived.is_file():
        return archived
    raise CloseoutAuthorizationError(
        f"workstream not found for closeout authorization: {workstream_id}",
        code="workstream_not_found",
    )


def _without_markdown_sections(text: str, headings: set[str]) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped in headings:
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            kept.append(line.rstrip())
    return "\n".join(kept).strip() + "\n"


def workstream_authority_fingerprint(detail_path: Path, *, action: str | None = None) -> str:
    text = detail_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    # Activity timestamps are operational history, not closeout authority. A
    # new plan/scope/status/merge request/evidence section still changes the
    # fingerprint and therefore invalidates a stale per-action approval.
    #
    # Merge is a deliberate two-step closeout: `workstream merge-start`
    # authorizes ReadyToMerge -> Merging, and the worktree merge path checks
    # the same authorization again before the Git side effect.  That
    # deterministic transition must not invalidate the approval that allowed
    # it.  For the merge action only, treat ReadyToMerge/Merging as one
    # closeout phase and ignore the operational `当前发现` text written by
    # merge-start.  All other material metadata/body changes still alter the
    # fingerprint and stale the approval.
    if action is not None and _action(action) == "merge":
        metadata, body, diagnostics = parse_front_matter(text)
        if diagnostics:
            raise CloseoutAuthorizationError(
                "workstream schema failed for closeout authorization fingerprint",
                code="workstream_schema_failed",
            )
        normalized_metadata = dict(metadata)
        if normalized_metadata.get("status") in {"ReadyToMerge", "Merging"}:
            normalized_metadata["status"] = "<merge-closeout>"
        canonical_body = _without_markdown_sections(
            body,
            {"## Activity Log", "## 当前发现"},
        )
        canonical = format_front_matter(normalized_metadata, canonical_body)
    else:
        canonical = _without_markdown_sections(text, {"## Activity Log"})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def workstream_identity(
    context_root: Path,
    workstream_id: str,
    *,
    action: str | None = None,
) -> dict[str, str]:
    path = workstream_detail_path(context_root, workstream_id)
    metadata, _body, diagnostics = parse_front_matter(path.read_text(encoding="utf-8"))
    if diagnostics:
        raise CloseoutAuthorizationError(
            f"workstream schema failed for closeout authorization: {workstream_id}",
            code="workstream_schema_failed",
        )
    workstream_type = str(metadata.get("type") or "Task")
    return {
        "id": workstream_id,
        "type": workstream_type,
        "class": workstream_class(workstream_type),
        "fingerprint": workstream_authority_fingerprint(path, action=action),
        "detail_path": str(path),
    }


def resolve_for_path(path: Path | None, workstream_id: str, action: str) -> dict[str, Any]:
    project_root, context_root = project_identity(path)
    identity = workstream_identity(context_root, workstream_id, action=action)
    return resolve_authorization(
        project_root,
        workstream_id=identity["id"],
        workstream_type=identity["type"],
        workstream_class_name=identity["class"],
        action=action,
        workstream_fingerprint=identity["fingerprint"],
    )


def resolve_authorization(
    project_root: Path,
    *,
    workstream_id: str,
    workstream_type: str,
    workstream_class_name: str,
    action: str,
    workstream_fingerprint: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized_action = _action(action)
    ledger = load_ledger(project_root)
    projected = project_records(ledger, now=now)
    policies = [
        item
        for item in projected["policies"]
        if item["active"]
        and normalized_action in item["actions"]
        and _policy_applies(
            item,
            workstream_id=workstream_id,
            workstream_type=workstream_type,
            workstream_class_name=workstream_class_name,
        )
    ]
    effective_policy = max(policies, key=_policy_precedence, default=None)
    approvals = [
        item
        for item in projected["approvals"]
        if item["active"]
        and item["workstream_id"] == workstream_id
        and item["action"] == normalized_action
    ]
    matching_approvals = [
        item for item in approvals if item["workstream_fingerprint"] == workstream_fingerprint
    ]
    approval = max(matching_approvals, key=lambda item: int(item["revision"]), default=None)
    stale_approvals = [
        item["record_id"]
        for item in approvals
        if item["workstream_fingerprint"] != workstream_fingerprint
    ]

    decision = str(effective_policy["decision"]) if effective_policy else "manual"
    if decision == "deny":
        disposition = "denied"
        authorized = False
    elif decision == "auto":
        disposition = "auto_authorized"
        authorized = True
    elif approval is not None:
        disposition = "human_approved"
        authorized = True
    else:
        disposition = "approval_required"
        authorized = False

    next_actions: list[str] = []
    if disposition == "approval_required":
        next_actions = [
            "Record explicit approval evidence for this exact Workstream/action/current authority fingerprint, or apply an applicable durable auto-close policy.",
            "Do not use a naked --human-approved assertion as approval evidence.",
        ]
    elif disposition == "denied":
        next_actions = [
            "Review the effective deny policy and its authority evidence; revoke or supersede it only from newer/narrower user authority.",
        ]

    return {
        "schema_version": RESOLUTION_SCHEMA,
        "authorized": authorized,
        "disposition": disposition,
        "action": normalized_action,
        "workstream_id": workstream_id,
        "workstream_type": workstream_type,
        "workstream_class": workstream_class_name,
        "workstream_fingerprint": workstream_fingerprint,
        "effective_policy": _public_record(effective_policy),
        "approval": _public_record(approval),
        "stale_approval_record_ids": stale_approvals,
        "ledger_revision": int(ledger["revision"]),
        "ledger_path": str(ledger_path(project_root)),
        "next_actions": next_actions,
    }


def record_policy(
    project_root: Path,
    *,
    decision: str,
    actions: Sequence[str],
    actor: str,
    authority_source: str,
    evidence_refs: Sequence[str],
    workstream_id: str | None = None,
    workstream_type: str | None = None,
    workstream_class_name: str | None = None,
    authority_revision: str | None = None,
    authority_fingerprint: str | None = None,
    expires_at: str | None = None,
    supersedes: Sequence[str] = (),
) -> dict[str, Any]:
    normalized_decision = str(decision).strip().lower()
    if normalized_decision not in POLICY_DECISIONS:
        raise CloseoutAuthorizationError(f"unsupported policy decision: {decision}")
    normalized_actions = _actions(actions)
    scope = {
        "workstream_id": _optional_text(workstream_id, field="workstream_id", max_bytes=128),
        "workstream_type": _optional_text(workstream_type, field="workstream_type", max_bytes=64),
        "workstream_class": _optional_class(workstream_class_name),
    }
    event = {
        "schema_version": EVENT_SCHEMA,
        "event_id": _new_id("cae"),
        "event_kind": "policy_set",
        "record_id": _new_id("cap"),
        "occurred_at": utc_now_iso(),
        "actor": _required_text(actor, field="actor", max_bytes=256),
        "decision": normalized_decision,
        "actions": normalized_actions,
        "scope": scope,
        "authority": _authority(
            authority_source,
            authority_revision=authority_revision,
            authority_fingerprint=authority_fingerprint,
        ),
        "evidence_refs": _refs(evidence_refs),
        "expires_at": _optional_timestamp(expires_at, field="expires_at"),
        "supersedes": [_required_text(item, field="supersedes", max_bytes=128) for item in supersedes],
    }
    return _append_event(project_root, event)


def record_approval(
    project_root: Path,
    *,
    workstream_id: str,
    workstream_type: str,
    workstream_class_name: str,
    action: str,
    workstream_fingerprint: str,
    actor: str,
    authority_source: str,
    evidence_refs: Sequence[str],
    authority_revision: str | None = None,
    authority_fingerprint: str | None = None,
    expires_at: str | None = None,
    supersedes: Sequence[str] = (),
) -> dict[str, Any]:
    normalized_class = _optional_class(workstream_class_name)
    if normalized_class is None:
        raise CloseoutAuthorizationError("workstream_class is required")
    event = {
        "schema_version": EVENT_SCHEMA,
        "event_id": _new_id("cae"),
        "event_kind": "approval_recorded",
        "record_id": _new_id("caa"),
        "occurred_at": utc_now_iso(),
        "actor": _required_text(actor, field="actor", max_bytes=256),
        "workstream_id": _required_text(workstream_id, field="workstream_id", max_bytes=128),
        "workstream_type": _required_text(
            workstream_type,
            field="workstream_type",
            max_bytes=64,
        ),
        "workstream_class": normalized_class,
        "action": _action(action),
        "workstream_fingerprint": _fingerprint(workstream_fingerprint, field="workstream_fingerprint"),
        "authority": _authority(
            authority_source,
            authority_revision=authority_revision,
            authority_fingerprint=authority_fingerprint,
        ),
        "evidence_refs": _refs(evidence_refs),
        "expires_at": _optional_timestamp(expires_at, field="expires_at"),
        "supersedes": [_required_text(item, field="supersedes", max_bytes=128) for item in supersedes],
    }
    return _append_event(project_root, event)


def revoke_record(
    project_root: Path,
    *,
    record_id: str,
    actor: str,
    authority_source: str,
    evidence_refs: Sequence[str],
) -> dict[str, Any]:
    ledger = load_ledger(project_root)
    projected = project_records(ledger)
    known = {item["record_id"] for item in [*projected["policies"], *projected["approvals"]]}
    target = _required_text(record_id, field="record_id", max_bytes=128)
    if target not in known:
        raise CloseoutAuthorizationError(
            f"closeout authorization record not found: {target}",
            code="closeout_authorization_record_not_found",
        )
    event = {
        "schema_version": EVENT_SCHEMA,
        "event_id": _new_id("cae"),
        "event_kind": "revoked",
        "occurred_at": utc_now_iso(),
        "actor": _required_text(actor, field="actor", max_bytes=256),
        "target_record_id": target,
        "authority": _authority(authority_source),
        "evidence_refs": _refs(evidence_refs),
    }
    return _append_event(project_root, event)


def project_records(ledger: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, list[dict[str, Any]]]:
    current_time = now or datetime.now(timezone.utc)
    records: dict[str, dict[str, Any]] = {}
    revoked: set[str] = set()
    superseded: set[str] = set()
    for raw in ledger.get("events", []):
        event = dict(raw)
        kind = event.get("event_kind")
        if kind in {"policy_set", "approval_recorded"}:
            records[str(event["record_id"])] = event
            superseded.update(str(item) for item in event.get("supersedes", []))
        elif kind == "revoked":
            revoked.add(str(event.get("target_record_id") or ""))
    policies: list[dict[str, Any]] = []
    approvals: list[dict[str, Any]] = []
    for record_id, record in records.items():
        item = dict(record)
        expires = _parse_timestamp(item.get("expires_at"), field="expires_at", allow_none=True)
        expired = expires is not None and expires <= current_time
        item["revoked"] = record_id in revoked
        item["superseded"] = record_id in superseded
        item["expired"] = expired
        item["active"] = not (item["revoked"] or item["superseded"] or item["expired"])
        if item["event_kind"] == "policy_set":
            policies.append(item)
        else:
            approvals.append(item)
    return {"policies": policies, "approvals": approvals}


def list_authorizations(project_root: Path) -> dict[str, Any]:
    ledger = load_ledger(project_root)
    projected = project_records(ledger)
    return {
        "schema_version": LEDGER_SCHEMA,
        "project_id": ledger["project_id"],
        "canonical_root": ledger["canonical_root"],
        "revision": ledger["revision"],
        "ledger_path": str(ledger_path(project_root)),
        "policies": [_public_record(item) for item in projected["policies"]],
        "approvals": [_public_record(item) for item in projected["approvals"]],
    }


def _append_event(project_root: Path, raw_event: Mapping[str, Any]) -> dict[str, Any]:
    lock = _acquire_lock(project_root)
    try:
        ledger = load_ledger(project_root)
        if len(ledger["events"]) >= MAX_EVENTS:
            raise CloseoutAuthorizationError(
                "closeout authorization event capacity exceeded",
                code="closeout_authorization_capacity_exceeded",
            )
        event = dict(raw_event)
        event["revision"] = int(ledger["revision"]) + 1
        # Supersession is allowed only against a known record and remains
        # append-only/auditable rather than mutating the old record.
        known_records = {
            str(item.get("record_id"))
            for item in ledger["events"]
            if item.get("event_kind") in {"policy_set", "approval_recorded"}
        }
        for target in event.get("supersedes", []):
            if target not in known_records:
                raise CloseoutAuthorizationError(
                    f"closeout authorization superseded record not found: {target}",
                    code="closeout_authorization_record_not_found",
                )
        updated = dict(ledger)
        updated["revision"] = event["revision"]
        updated["events"] = [*ledger["events"], event]
        validated = validate_ledger(updated, project_root=project_root)
        atomic_write_text(
            ledger_path(project_root),
            json.dumps(validated, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        return {"ledger": validated, "event": event, "ledger_path": str(ledger_path(project_root))}
    finally:
        _release_lock(lock)


def _policy_applies(
    policy: Mapping[str, Any],
    *,
    workstream_id: str,
    workstream_type: str,
    workstream_class_name: str,
) -> bool:
    scope = policy.get("scope") or {}
    if not isinstance(scope, Mapping):
        return False
    scoped_id = scope.get("workstream_id")
    scoped_type = scope.get("workstream_type")
    scoped_class = scope.get("workstream_class")
    if scoped_id and scoped_id != workstream_id:
        return False
    if scoped_type and scoped_type != workstream_type:
        return False
    if scoped_class and scoped_class != workstream_class_name:
        return False
    return True


def _policy_precedence(policy: Mapping[str, Any]) -> tuple[int, int]:
    scope = policy.get("scope") or {}
    specificity = 0
    if isinstance(scope, Mapping):
        if scope.get("workstream_id"):
            specificity += 100
        if scope.get("workstream_type"):
            specificity += 10
        if scope.get("workstream_class"):
            specificity += 10
    return specificity, int(policy.get("revision") or 0)


def _public_record(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return {key: value for key, value in record.items() if key != "schema_version"} | {
        "schema_version": record.get("schema_version")
    }


def _authority(
    source: str,
    *,
    authority_revision: str | None = None,
    authority_fingerprint: str | None = None,
) -> dict[str, str | None]:
    return {
        "source": _required_text(source, field="authority_source", max_bytes=4096),
        "revision": _optional_text(authority_revision, field="authority_revision", max_bytes=512),
        "fingerprint": _optional_text(authority_fingerprint, field="authority_fingerprint", max_bytes=512),
    }


def _validate_event_payload(
    event: Mapping[str, Any],
    *,
    known_record_ids: set[str],
) -> None:
    """Validate the semantic payload of one persisted authorization event.

    The ledger is user-level authority, so loading it must fail closed on a
    syntactically valid but semantically malformed/tampered event rather than
    letting projection code raise incidental KeyError/TypeError exceptions or
    silently broaden authority.
    """

    _required_text(event.get("actor"), field="actor", max_bytes=256)
    authority = event.get("authority")
    if not isinstance(authority, Mapping):
        raise CloseoutAuthorizationError(
            "closeout authorization authority must be an object",
            code="closeout_authorization_ledger_invalid",
        )
    _required_text(authority.get("source"), field="authority_source", max_bytes=4096)
    _optional_text(authority.get("revision"), field="authority_revision", max_bytes=512)
    _optional_text(authority.get("fingerprint"), field="authority_fingerprint", max_bytes=512)

    evidence_refs = event.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        raise CloseoutAuthorizationError(
            "closeout authorization evidence_refs must be a list",
            code="closeout_authorization_ledger_invalid",
        )
    if _refs(evidence_refs) != evidence_refs:
        raise CloseoutAuthorizationError(
            "closeout authorization evidence_refs are not canonical",
            code="closeout_authorization_ledger_invalid",
        )

    kind = str(event.get("event_kind") or "")
    if kind == "revoked":
        target = _required_text(
            event.get("target_record_id"), field="target_record_id", max_bytes=128
        )
        if target not in known_record_ids:
            raise CloseoutAuthorizationError(
                f"closeout authorization revoked record not found: {target}",
                code="closeout_authorization_ledger_invalid",
            )
        return

    expires_at = event.get("expires_at")
    _parse_timestamp(expires_at, field="expires_at", allow_none=True)
    supersedes = event.get("supersedes")
    if not isinstance(supersedes, list):
        raise CloseoutAuthorizationError(
            "closeout authorization supersedes must be a list",
            code="closeout_authorization_ledger_invalid",
        )
    canonical_supersedes = [
        _required_text(item, field="supersedes", max_bytes=128) for item in supersedes
    ]
    if len(canonical_supersedes) != len(set(canonical_supersedes)):
        raise CloseoutAuthorizationError(
            "closeout authorization supersedes contains duplicates",
            code="closeout_authorization_ledger_invalid",
        )
    for target in canonical_supersedes:
        if target not in known_record_ids:
            raise CloseoutAuthorizationError(
                f"closeout authorization superseded record not found: {target}",
                code="closeout_authorization_ledger_invalid",
            )

    if kind == "policy_set":
        decision = str(event.get("decision") or "").strip().lower()
        if decision not in POLICY_DECISIONS:
            raise CloseoutAuthorizationError(
                f"unsupported policy decision: {decision}",
                code="closeout_authorization_ledger_invalid",
            )
        actions = event.get("actions")
        if not isinstance(actions, list) or _actions(actions) != actions:
            raise CloseoutAuthorizationError(
                "closeout authorization policy actions are not canonical",
                code="closeout_authorization_ledger_invalid",
            )
        scope = event.get("scope")
        if not isinstance(scope, Mapping):
            raise CloseoutAuthorizationError(
                "closeout authorization policy scope must be an object",
                code="closeout_authorization_ledger_invalid",
            )
        allowed_scope_keys = {"workstream_id", "workstream_type", "workstream_class"}
        if set(scope) - allowed_scope_keys:
            raise CloseoutAuthorizationError(
                "closeout authorization policy scope contains unsupported fields",
                code="closeout_authorization_ledger_invalid",
            )
        _optional_text(scope.get("workstream_id"), field="workstream_id", max_bytes=128)
        _optional_text(scope.get("workstream_type"), field="workstream_type", max_bytes=64)
        _optional_class(scope.get("workstream_class"))
        return

    _required_text(event.get("workstream_id"), field="workstream_id", max_bytes=128)
    _required_text(event.get("workstream_type"), field="workstream_type", max_bytes=64)
    workstream_class_name = _optional_class(event.get("workstream_class"))
    if workstream_class_name is None:
        raise CloseoutAuthorizationError(
            "workstream_class is required",
            code="closeout_authorization_ledger_invalid",
        )
    _action(str(event.get("action") or ""))
    _fingerprint(
        str(event.get("workstream_fingerprint") or ""),
        field="workstream_fingerprint",
    )


def _actions(values: Sequence[str]) -> list[str]:
    actions = sorted({_action(value) for value in values})
    if not actions:
        raise CloseoutAuthorizationError("at least one closeout action is required")
    return actions


def _action(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in CLOSEOUT_ACTIONS:
        raise CloseoutAuthorizationError(f"unsupported closeout action: {value}")
    return normalized


def _optional_class(value: str | None) -> str | None:
    normalized = _optional_text(value, field="workstream_class", max_bytes=64)
    if normalized is not None and normalized not in WORKSTREAM_CLASSES:
        raise CloseoutAuthorizationError(f"unsupported Workstream class: {normalized}")
    return normalized


def _refs(values: Sequence[str]) -> list[str]:
    refs = [_required_text(value, field="evidence_ref", max_bytes=4096) for value in values]
    if not refs:
        raise CloseoutAuthorizationError("closeout authorization requires at least one evidence reference")
    return list(dict.fromkeys(refs))


def _required_text(value: object, *, field: str, max_bytes: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise CloseoutAuthorizationError(f"{field} is required")
    if len(normalized.encode("utf-8")) > max_bytes:
        raise CloseoutAuthorizationError(f"{field} exceeds {max_bytes} bytes")
    return normalized


def _optional_text(value: object, *, field: str, max_bytes: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return _required_text(normalized, field=field, max_bytes=max_bytes)


def _fingerprint(value: str, *, field: str) -> str:
    normalized = _required_text(value, field=field, max_bytes=512)
    if len(normalized) < 12:
        raise CloseoutAuthorizationError(f"{field} is too short")
    return normalized


def _optional_timestamp(value: str | None, *, field: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    parsed = _parse_timestamp(value, field=field)
    assert parsed is not None
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_timestamp(value: object, *, field: str, allow_none: bool = False) -> datetime | None:
    if value is None and allow_none:
        return None
    normalized = str(value or "").strip()
    if not normalized and allow_none:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CloseoutAuthorizationError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CloseoutAuthorizationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:20]}"


def _acquire_lock(project_root: Path) -> Path:
    path = lock_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"pid": os.getpid(), "created_at": utc_now_iso()}) + "\n")
            return path
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise CloseoutAuthorizationError(
                    f"closeout authorization ledger is locked: {path}",
                    code="closeout_authorization_locked",
                ) from exc
            time.sleep(0.05)


def _release_lock(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


__all__ = [
    "AUTHORIZATION_DISPOSITIONS",
    "CLOSEOUT_ACTIONS",
    "LEDGER_SCHEMA",
    "POLICY_DECISIONS",
    "WORKSTREAM_CLASSES",
    "CloseoutAuthorizationError",
    "authorization_dir",
    "canonical_project_root",
    "ledger_path",
    "list_authorizations",
    "load_ledger",
    "project_identity",
    "record_approval",
    "record_policy",
    "resolve_authorization",
    "resolve_for_path",
    "revoke_record",
    "workstream_authority_fingerprint",
    "workstream_class",
    "workstream_identity",
]
