"""Explicit Observer V2 target registry and target-local run projection.

Targets are user-level display/runtime configuration.  They do not replace
project Markdown authority and they deliberately do not infer targets from
Workstream/worktree existence.  Only rows explicitly registered in
``observer/targets.json`` participate in target-local projections.
"""

from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_context_framework.observability import atomic_write_text
from ai_context_framework.observer_storage import SEMANTIC_SENSITIVE_VALUE_RE, SemanticSensitiveValueError


OBSERVER_TARGET_REGISTRY_SCHEMA = "acf.observer.targets.v1"
OBSERVER_TARGET_SCHEMA = "acf.observer.target.v1"
OBSERVER_TARGET_RUN_SCHEMA = "acf.observer.target-run.v1"
OBSERVER_TARGET_RUN_EVENT_SCHEMA = "acf.observer.target-run-event.v1"
OBSERVER_PROJECT_OVERVIEW_DECISION_SCHEMA = "acf.observer.project-overview-decision.v1"
OBSERVER_EXPECTED_TARGET_REGISTRY_SCHEMA = "acf.observer.expected-targets.v1"
OBSERVER_TARGET_REGISTRY_HEALTH_SCHEMA = "acf.observer.target-registry-health.v1"

TARGET_MODES = {"fixed_workstream", "project_dynamic"}
OVERVIEW_DECISIONS = {"undecided", "enabled", "disabled"}
RUN_RESULTS = {"success", "failed", "blocked", "cancelled", "partial"}
_TARGET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_TARGET_CONTRACT_FIELDS = (
    "mode",
    "title",
    "automation_ref",
    "workstream_id",
    "continuation_task_id",
    "route_ref",
)


class ObserverTargetRegistryError(ValueError):
    """Raised when the explicit target registry is invalid or unsafe."""


def _validate_runtime_text(value: object, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ObserverTargetRegistryError(f"observer {field} is required")
        return None
    if not isinstance(value, str):
        raise ObserverTargetRegistryError(f"observer {field} must be a string")
    cleaned = value.strip()
    if not cleaned:
        if required:
            raise ObserverTargetRegistryError(f"observer {field} is required")
        return None
    if SEMANTIC_SENSITIVE_VALUE_RE.search(cleaned):
        raise SemanticSensitiveValueError(f"sensitive credential-like value refused in observer {field}")
    return cleaned


def _validate_runtime_refs(values: object, field: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ObserverTargetRegistryError(f"observer {field} must be a list")
    refs: list[str] = []
    for value in values:
        cleaned = _validate_runtime_text(value, field, required=True)
        assert cleaned is not None
        refs.append(cleaned)
    return refs


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def observer_target_paths(project: Any) -> dict[str, Path]:
    root = Path(project.observer_dir)
    return {
        "registry": root / "targets.json",
        "targets_root": root / "targets",
        # Expected-target configuration deliberately lives beside observer/
        # rather than inside it.  Recreating or losing derived Observer runtime
        # state must not erase the explicit recovery contract itself.
        "expected_registry": root.parent / "observer_expected_targets.json",
    }


def _target_run_events_path(project: Any, target_id: str) -> Path:
    if not _TARGET_ID_RE.fullmatch(target_id):
        raise ObserverTargetRegistryError("observer target_id is invalid")
    return observer_target_paths(project)["targets_root"] / target_id / "run_events.jsonl"


def _default_overview_decision() -> dict[str, object]:
    return {
        "schema_version": OBSERVER_PROJECT_OVERVIEW_DECISION_SCHEMA,
        "decision": "undecided",
        "reason": None,
        "evidence_refs": [],
        "authority_fingerprint": None,
        "decided_at": None,
    }


def _default_registry(project: Any) -> dict[str, object]:
    return {
        "schema_version": OBSERVER_TARGET_REGISTRY_SCHEMA,
        "project_id": project.project_id,
        "revision": 0,
        "updated_at": None,
        "targets": [],
        "project_overview": _default_overview_decision(),
    }


def _default_expected_registry(project: Any) -> dict[str, object]:
    return {
        "schema_version": OBSERVER_EXPECTED_TARGET_REGISTRY_SCHEMA,
        "project_id": project.project_id,
        "revision": 0,
        "updated_at": None,
        "targets": [],
        "withdrawn_target_ids": [],
    }


def _validated_target(row: object) -> dict[str, object]:
    if not isinstance(row, dict):
        raise ObserverTargetRegistryError("observer target must be an object")
    target_id = row.get("target_id")
    mode = row.get("mode")
    title = row.get("title")
    automation_ref = row.get("automation_ref")
    if not isinstance(target_id, str) or not _TARGET_ID_RE.fullmatch(target_id):
        raise ObserverTargetRegistryError("observer target_id is invalid")
    if mode not in TARGET_MODES:
        raise ObserverTargetRegistryError(f"observer target mode is invalid: {mode}")
    normalized_title = _validate_runtime_text(title, "target title", required=True)
    normalized_automation_ref = _validate_runtime_text(
        automation_ref,
        "target automation_ref",
        required=True,
    )
    workstream_id = row.get("workstream_id")
    continuation_task_id = row.get("continuation_task_id")
    if mode == "fixed_workstream" and (not isinstance(workstream_id, str) or not workstream_id.strip()):
        raise ObserverTargetRegistryError("fixed_workstream target requires workstream_id")
    if mode == "project_dynamic" and (
        not isinstance(continuation_task_id, str) or not continuation_task_id.strip()
    ):
        raise ObserverTargetRegistryError("project_dynamic target requires continuation_task_id")
    normalized = dict(row)
    normalized["schema_version"] = OBSERVER_TARGET_SCHEMA
    normalized["target_id"] = target_id
    normalized["mode"] = mode
    normalized["title"] = normalized_title
    normalized["automation_ref"] = normalized_automation_ref
    normalized["workstream_id"] = (
        _validate_runtime_text(workstream_id, "target workstream_id")
        if workstream_id is not None
        else None
    )
    normalized["continuation_task_id"] = (
        _validate_runtime_text(continuation_task_id, "target continuation_task_id")
        if continuation_task_id is not None
        else None
    )
    route_ref = row.get("route_ref")
    normalized["route_ref"] = (
        _validate_runtime_text(route_ref, "target route_ref") if route_ref is not None else None
    )
    return normalized


def _validated_overview(value: object) -> dict[str, object]:
    if value is None:
        return _default_overview_decision()
    if not isinstance(value, dict):
        raise ObserverTargetRegistryError("project_overview must be an object")
    decision = value.get("decision")
    if decision not in OVERVIEW_DECISIONS:
        raise ObserverTargetRegistryError(f"project_overview decision is invalid: {decision}")
    result = dict(value)
    result["schema_version"] = OBSERVER_PROJECT_OVERVIEW_DECISION_SCHEMA
    result["decision"] = decision
    result["evidence_refs"] = _validate_runtime_refs(
        value.get("evidence_refs") or [],
        "project_overview evidence_refs",
    )
    if decision != "undecided":
        result["reason"] = _validate_runtime_text(
            value.get("reason"),
            "project_overview reason",
            required=True,
        )
        if not result["evidence_refs"]:
            raise ObserverTargetRegistryError("project_overview enabled/disabled decision requires evidence_refs")
        fingerprint = _validate_runtime_text(
            value.get("authority_fingerprint"),
            "project_overview authority_fingerprint",
            required=True,
        )
        if fingerprint is None:
            raise ObserverTargetRegistryError(
                "project_overview enabled/disabled decision requires authority_fingerprint"
            )
        result["authority_fingerprint"] = fingerprint
    else:
        result["reason"] = _validate_runtime_text(value.get("reason"), "project_overview reason")
        result["authority_fingerprint"] = _validate_runtime_text(
            value.get("authority_fingerprint"),
            "project_overview authority_fingerprint",
        )
    return result


def read_target_registry(project: Any) -> dict[str, object]:
    path = observer_target_paths(project)["registry"]
    if not path.is_file():
        return _default_registry(project)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObserverTargetRegistryError(f"cannot read observer target registry: {exc}") from exc
    if not isinstance(raw, dict):
        raise ObserverTargetRegistryError("observer target registry must be an object")
    if raw.get("schema_version") != OBSERVER_TARGET_REGISTRY_SCHEMA:
        raise ObserverTargetRegistryError(
            f"unsupported observer target registry schema: {raw.get('schema_version')}"
        )
    if raw.get("project_id") != project.project_id:
        raise ObserverTargetRegistryError("observer target registry project_id does not match current project")
    targets = [_validated_target(row) for row in raw.get("targets") or []]
    ids = [str(row["target_id"]) for row in targets]
    if len(ids) != len(set(ids)):
        raise ObserverTargetRegistryError("observer target registry contains duplicate target_id")
    return {
        "schema_version": OBSERVER_TARGET_REGISTRY_SCHEMA,
        "project_id": project.project_id,
        "revision": int(raw.get("revision") or 0),
        "updated_at": raw.get("updated_at"),
        "targets": sorted(targets, key=lambda row: str(row["target_id"])),
        "project_overview": _validated_overview(raw.get("project_overview")),
    }


def read_expected_target_registry(project: Any) -> dict[str, object]:
    path = observer_target_paths(project)["expected_registry"]
    if not path.is_file():
        return _default_expected_registry(project)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObserverTargetRegistryError(f"cannot read observer expected-target registry: {exc}") from exc
    if not isinstance(raw, dict):
        raise ObserverTargetRegistryError("observer expected-target registry must be an object")
    if raw.get("schema_version") != OBSERVER_EXPECTED_TARGET_REGISTRY_SCHEMA:
        raise ObserverTargetRegistryError(
            f"unsupported observer expected-target registry schema: {raw.get('schema_version')}"
        )
    if raw.get("project_id") != project.project_id:
        raise ObserverTargetRegistryError(
            "observer expected-target registry project_id does not match current project"
        )
    targets = [_validated_target(row) for row in raw.get("targets") or []]
    ids = [str(row["target_id"]) for row in targets]
    if len(ids) != len(set(ids)):
        raise ObserverTargetRegistryError("observer expected-target registry contains duplicate target_id")
    withdrawn_raw = raw.get("withdrawn_target_ids") or []
    if not isinstance(withdrawn_raw, list):
        raise ObserverTargetRegistryError("observer expected-target withdrawn_target_ids must be a list")
    withdrawn: list[str] = []
    for value in withdrawn_raw:
        if not isinstance(value, str) or not _TARGET_ID_RE.fullmatch(value):
            raise ObserverTargetRegistryError("observer expected-target withdrawn target_id is invalid")
        withdrawn.append(value)
    if len(withdrawn) != len(set(withdrawn)):
        raise ObserverTargetRegistryError("observer expected-target registry contains duplicate withdrawn target_id")
    overlap = sorted(set(ids) & set(withdrawn))
    if overlap:
        raise ObserverTargetRegistryError(
            "observer expected-target registry cannot configure and withdraw the same target_id: "
            + ", ".join(overlap)
        )
    return {
        "schema_version": OBSERVER_EXPECTED_TARGET_REGISTRY_SCHEMA,
        "project_id": project.project_id,
        "revision": int(raw.get("revision") or 0),
        "updated_at": raw.get("updated_at"),
        "targets": sorted(targets, key=lambda row: str(row["target_id"])),
        "withdrawn_target_ids": sorted(withdrawn),
    }


def _write_registry(project: Any, registry: dict[str, object]) -> dict[str, object]:
    path = observer_target_paths(project)["registry"]
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(registry)
    payload["revision"] = int(payload.get("revision") or 0) + 1
    payload["updated_at"] = _utc_now_iso()
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return payload


def _write_expected_registry(project: Any, registry: dict[str, object]) -> dict[str, object]:
    path = observer_target_paths(project)["expected_registry"]
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(registry)
    payload["revision"] = int(payload.get("revision") or 0) + 1
    payload["updated_at"] = _utc_now_iso()
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return payload


def _read_run_events(project: Any, target_id: str) -> list[dict[str, object]]:
    path = _target_run_events_path(project, target_id)
    if not path.is_file():
        return []
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            value = json.loads(raw_line)
            if not isinstance(value, dict) or value.get("schema_version") != OBSERVER_TARGET_RUN_EVENT_SCHEMA:
                raise ObserverTargetRegistryError("observer target run event stream contains an invalid record")
            event_kind = value.get("event_kind")
            run_id = value.get("run_id")
            if value.get("project_id") != project.project_id or value.get("target_id") != target_id:
                raise ObserverTargetRegistryError("observer target run event identity does not match its runtime scope")
            if event_kind not in {"start", "finish"} or not isinstance(run_id, str) or not _TARGET_ID_RE.fullmatch(run_id):
                raise ObserverTargetRegistryError("observer target run event identity is invalid")
            if value.get("event_id") != _run_event_id(target_id, run_id, str(event_kind)):
                raise ObserverTargetRegistryError("observer target run event id is invalid")
            if _parse_time(value.get("observed_at")) is None:
                raise ObserverTargetRegistryError("observer target run event observed_at is invalid")
            if event_kind == "finish" and value.get("result") not in RUN_RESULTS:
                raise ObserverTargetRegistryError("observer target run finish result is invalid")
            _validate_runtime_text(value.get("route_ref"), "target run route_ref")
            _validate_runtime_refs(value.get("evidence_refs") or [], "target run evidence_refs")
            if event_kind == "finish":
                _validate_runtime_text(value.get("major_outcome"), "target run major_outcome")
            key = (run_id, str(event_kind))
            if key in seen:
                raise ObserverTargetRegistryError("observer target run event stream contains a duplicate lifecycle event")
            seen.add(key)
            rows.append(value)
    except json.JSONDecodeError as exc:
        raise ObserverTargetRegistryError("observer target run event stream contains invalid JSON") from exc
    except OSError as exc:
        raise ObserverTargetRegistryError(f"cannot read observer target run event stream: {exc}") from exc
    return rows


def _append_run_event(project: Any, target_id: str, payload: dict[str, object]) -> None:
    path = _target_run_events_path(project, target_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing and not existing.endswith(("\n", "\r")):
        existing += "\n"
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    atomic_write_text(path, existing + line)


def _require_registered_target(project: Any, target_id: str) -> dict[str, object]:
    registry = read_target_registry(project)
    target = next((row for row in registry["targets"] if row.get("target_id") == target_id), None)
    if not isinstance(target, dict):
        raise ObserverTargetRegistryError(
            "observer target run marker requires an explicitly registered target"
        )
    return target


def _run_event_id(target_id: str, run_id: str, event_kind: str) -> str:
    digest = hashlib.sha256(f"{target_id}\0{run_id}\0{event_kind}".encode("utf-8")).hexdigest()[:24]
    return f"target-run-event-{digest}"


def record_target_run_start(
    project: Any,
    *,
    target_id: str,
    run_id: str,
    route_ref: str | None = None,
    evidence_refs: list[str] | None = None,
) -> tuple[dict[str, object], bool]:
    _require_registered_target(project, target_id)
    if not _TARGET_ID_RE.fullmatch(run_id):
        raise ObserverTargetRegistryError("observer target run_id is invalid")
    refs = _validate_runtime_refs(evidence_refs or [], "target run evidence_refs")
    normalized_route = _validate_runtime_text(route_ref, "target run route_ref")
    events = _read_run_events(project, target_id)
    existing = next(
        (row for row in events if row.get("run_id") == run_id and row.get("event_kind") == "start"),
        None,
    )
    if isinstance(existing, dict):
        if existing.get("route_ref") == normalized_route and existing.get("evidence_refs") == refs:
            return existing, False
        raise ObserverTargetRegistryError("observer target run start already exists with different metadata")
    if any(row.get("run_id") == run_id and row.get("event_kind") == "finish" for row in events):
        raise ObserverTargetRegistryError("observer target run finish exists without a matching start")
    payload = {
        "schema_version": OBSERVER_TARGET_RUN_EVENT_SCHEMA,
        "event_id": _run_event_id(target_id, run_id, "start"),
        "event_kind": "start",
        "project_id": project.project_id,
        "target_id": target_id,
        "run_id": run_id,
        "observed_at": _utc_now_iso(),
        "route_ref": normalized_route,
        "evidence_refs": refs,
    }
    _append_run_event(project, target_id, payload)
    return payload, True


def record_target_run_finish(
    project: Any,
    *,
    target_id: str,
    run_id: str,
    result: str,
    major_outcome: str | None = None,
    route_ref: str | None = None,
    evidence_refs: list[str] | None = None,
) -> tuple[dict[str, object], bool]:
    _require_registered_target(project, target_id)
    if not _TARGET_ID_RE.fullmatch(run_id):
        raise ObserverTargetRegistryError("observer target run_id is invalid")
    if result not in RUN_RESULTS:
        raise ObserverTargetRegistryError(f"observer target run result is invalid: {result}")
    events = _read_run_events(project, target_id)
    start = next(
        (row for row in events if row.get("run_id") == run_id and row.get("event_kind") == "start"),
        None,
    )
    if not isinstance(start, dict):
        raise ObserverTargetRegistryError("observer target run finish requires a durable start marker")
    refs = _validate_runtime_refs(evidence_refs or [], "target run evidence_refs")
    existing = next(
        (row for row in events if row.get("run_id") == run_id and row.get("event_kind") == "finish"),
        None,
    )
    normalized_outcome = _validate_runtime_text(major_outcome, "target run major_outcome")
    normalized_route = _validate_runtime_text(route_ref, "target run route_ref")
    if normalized_route is None:
        normalized_route = start.get("route_ref")
    if isinstance(existing, dict):
        comparable = {
            "result": result,
            "major_outcome": normalized_outcome,
            "route_ref": normalized_route,
            "evidence_refs": refs,
        }
        if all(existing.get(key) == value for key, value in comparable.items()):
            return existing, False
        raise ObserverTargetRegistryError("observer target run finish already exists with different metadata")
    payload = {
        "schema_version": OBSERVER_TARGET_RUN_EVENT_SCHEMA,
        "event_id": _run_event_id(target_id, run_id, "finish"),
        "event_kind": "finish",
        "project_id": project.project_id,
        "target_id": target_id,
        "run_id": run_id,
        "observed_at": _utc_now_iso(),
        "result": result,
        "major_outcome": normalized_outcome,
        "route_ref": normalized_route,
        "evidence_refs": refs,
    }
    _append_run_event(project, target_id, payload)
    return payload, True


def register_target(
    project: Any,
    *,
    target_id: str,
    mode: str,
    title: str,
    automation_ref: str,
    workstream_id: str | None = None,
    continuation_task_id: str | None = None,
    route_ref: str | None = None,
) -> tuple[dict[str, object], bool]:
    registry = read_target_registry(project)
    now = _utc_now_iso()
    existing = next((row for row in registry["targets"] if row.get("target_id") == target_id), None)
    candidate = _validated_target(
        {
            "schema_version": OBSERVER_TARGET_SCHEMA,
            "target_id": target_id,
            "mode": mode,
            "title": title,
            "automation_ref": automation_ref,
            "workstream_id": workstream_id,
            "continuation_task_id": continuation_task_id,
            "route_ref": route_ref,
            "registered_at": existing.get("registered_at") if isinstance(existing, dict) else now,
            "updated_at": now,
        }
    )
    if isinstance(existing, dict) and all(existing.get(key) == candidate.get(key) for key in _TARGET_CONTRACT_FIELDS):
        return registry, False
    targets = [row for row in registry["targets"] if row.get("target_id") != target_id]
    targets.append(candidate)
    registry["targets"] = sorted(targets, key=lambda row: str(row["target_id"]))
    return _write_registry(project, registry), True


def register_expected_target(
    project: Any,
    *,
    target_id: str,
    mode: str,
    title: str,
    automation_ref: str,
    workstream_id: str | None = None,
    continuation_task_id: str | None = None,
    route_ref: str | None = None,
) -> tuple[dict[str, object], bool]:
    registry = read_expected_target_registry(project)
    now = _utc_now_iso()
    existing = next((row for row in registry["targets"] if row.get("target_id") == target_id), None)
    candidate = _validated_target(
        {
            "schema_version": OBSERVER_TARGET_SCHEMA,
            "target_id": target_id,
            "mode": mode,
            "title": title,
            "automation_ref": automation_ref,
            "workstream_id": workstream_id,
            "continuation_task_id": continuation_task_id,
            "route_ref": route_ref,
            "registered_at": existing.get("registered_at") if isinstance(existing, dict) else now,
            "updated_at": now,
        }
    )
    comparable_fields = (
        "mode",
        "title",
        "automation_ref",
        "workstream_id",
        "continuation_task_id",
        "route_ref",
    )
    if isinstance(existing, dict) and all(existing.get(key) == candidate.get(key) for key in comparable_fields):
        return registry, False
    targets = [row for row in registry["targets"] if row.get("target_id") != target_id]
    targets.append(candidate)
    registry["targets"] = sorted(targets, key=lambda row: str(row["target_id"]))
    registry["withdrawn_target_ids"] = sorted(
        value for value in registry.get("withdrawn_target_ids") or [] if value != target_id
    )
    return _write_expected_registry(project, registry), True


def remove_target(project: Any, target_id: str) -> tuple[dict[str, object], bool]:
    registry = read_target_registry(project)
    retained = [row for row in registry["targets"] if row.get("target_id") != target_id]
    if len(retained) == len(registry["targets"]):
        return registry, False
    registry["targets"] = retained
    return _write_registry(project, registry), True


def remove_expected_target(project: Any, target_id: str) -> tuple[dict[str, object], bool]:
    registry = read_expected_target_registry(project)
    retained = [row for row in registry["targets"] if row.get("target_id") != target_id]
    if len(retained) == len(registry["targets"]):
        return registry, False
    registry["targets"] = retained
    withdrawn = {str(value) for value in registry.get("withdrawn_target_ids") or []}
    withdrawn.add(target_id)
    registry["withdrawn_target_ids"] = sorted(withdrawn)
    return _write_expected_registry(project, registry), True


def target_registry_health(
    project: Any,
    *,
    registry: dict[str, object] | None = None,
    expected_registry: dict[str, object] | None = None,
) -> dict[str, object]:
    actual = registry or read_target_registry(project)
    expected = expected_registry or read_expected_target_registry(project)
    actual_by_id = {
        str(row.get("target_id")): row
        for row in actual.get("targets") or []
        if isinstance(row, dict) and row.get("target_id")
    }
    expected_by_id = {
        str(row.get("target_id")): row
        for row in expected.get("targets") or []
        if isinstance(row, dict) and row.get("target_id")
    }
    actual_ids = set(actual_by_id)
    expected_ids = set(expected_by_id)
    withdrawn_ids = {
        str(value)
        for value in expected.get("withdrawn_target_ids") or []
        if isinstance(value, str) and value
    }
    missing = sorted(expected_ids - actual_ids)
    contract_conflicts = sorted(
        target_id
        for target_id in expected_ids & actual_ids
        if any(
            actual_by_id[target_id].get(field) != expected_by_id[target_id].get(field)
            for field in _TARGET_CONTRACT_FIELDS
        )
    )
    withdrawn_registered = sorted(withdrawn_ids & actual_ids)
    conflicts = sorted(set(contract_conflicts) | set(withdrawn_registered))
    expected_revision = int(expected.get("revision") or 0)
    if not expected_ids and expected_revision == 0:
        status = "unconfigured"
        reason = "expected_target_contract_not_configured"
    elif conflicts:
        status = "conflict"
        reason = "expected_target_configuration_conflict"
    elif not expected_ids:
        status = "configured_empty"
        reason = "expected_target_contract_intentionally_empty"
    elif missing:
        status = "incomplete"
        reason = "expected_targets_missing"
    else:
        status = "healthy"
        reason = "all_expected_targets_registered"
    return {
        "schema_version": OBSERVER_TARGET_REGISTRY_HEALTH_SCHEMA,
        "status": status,
        "reason": reason,
        "registered_count": len(actual_ids),
        "expected_count": len(expected_ids),
        "registered_target_ids": sorted(actual_ids),
        "expected_target_ids": sorted(expected_ids),
        "withdrawn_target_ids": sorted(withdrawn_ids),
        "missing_expected_target_ids": missing,
        "conflicting_expected_target_ids": conflicts,
        "contract_conflicting_target_ids": contract_conflicts,
        "withdrawn_registered_target_ids": withdrawn_registered,
        "recovery_available": bool(missing and expected_ids),
        "expected_registry_revision": expected_revision,
        "registry_revision": int(actual.get("revision") or 0),
    }


def recover_expected_targets(project: Any) -> tuple[dict[str, object], list[str], bool]:
    """Idempotently restore only explicitly configured expected targets."""

    expected = read_expected_target_registry(project)
    registry = read_target_registry(project)
    expected_by_id = {
        str(row.get("target_id")): row
        for row in expected.get("targets") or []
        if isinstance(row, dict) and row.get("target_id")
    }
    registered_ids = {
        str(row.get("target_id"))
        for row in registry.get("targets") or []
        if isinstance(row, dict) and row.get("target_id")
    }
    missing = sorted(set(expected_by_id) - registered_ids)
    if not missing:
        return registry, [], False
    targets = list(registry.get("targets") or [])
    targets.extend(dict(expected_by_id[target_id]) for target_id in missing)
    registry["targets"] = sorted(targets, key=lambda row: str(row.get("target_id") or ""))
    return _write_registry(project, registry), missing, True


def target_registry_alert_specs(target_state: object) -> list[dict[str, object]]:
    if not isinstance(target_state, dict):
        return []
    health = target_state.get("registry_health")
    if not isinstance(health, dict) or health.get("status") in {"healthy", "configured_empty"}:
        return []
    status = str(health.get("status") or "unconfigured")
    if status == "conflict":
        binding_conflicts = ", ".join(
            str(item) for item in health.get("contract_conflicting_target_ids") or []
        )
        withdrawn_registered = ", ".join(
            str(item) for item in health.get("withdrawn_registered_target_ids") or []
        )
        title = "Observer Target Registry 与 expected-target 配置冲突"
        details: list[str] = []
        if binding_conflicts:
            details.append(f"绑定不一致：{binding_conflicts}")
        if withdrawn_registered:
            details.append(f"已明确撤销但仍注册：{withdrawn_registered}")
        explanation = (
            "显式 expected-target contract 与当前 Target Registry 不一致（"
            + "；".join(details or ["unknown"])
            + "）。恢复流程不会覆盖现有 target 或复活已撤销 target；必须由有权 authority 明确统一配置。"
        )
    elif status == "incomplete":
        missing = ", ".join(str(item) for item in health.get("missing_expected_target_ids") or []) or "unknown"
        title = "Observer Target Registry 缺少明确预期目标"
        explanation = (
            f"显式 expected-target contract 要求的目标尚未全部注册：{missing}。"
            "Observer 不会把任意 Workstream 自动提升为 target；应使用正式 recovery 入口幂等恢复明确配置。"
        )
    else:
        title = "Observer expected-target recovery contract 尚未配置"
        explanation = (
            "当前没有独立的 expected-target 配置可用于 Observer runtime state 丢失后的恢复/完整性检查。"
            "在该 contract 明确配置前，Target Registry 不能被视为完整绿色观测面。"
        )
    return [
        {
            "alert_key": "observer:target-registry-health",
            "severity": "warning",
            "title": title,
            "explanation": explanation,
            "canonical_identity": {"type": "observer_target_registry", "id": "targets"},
            "provenance": [{"source": "observer_expected_targets", **health}],
        }
    ]


def set_project_overview_decision(
    project: Any,
    *,
    decision: str,
    reason: str | None = None,
    evidence_refs: list[str] | None = None,
    authority_fingerprint: str | None = None,
) -> tuple[dict[str, object], bool]:
    registry = read_target_registry(project)
    candidate = _validated_overview(
        {
            "schema_version": OBSERVER_PROJECT_OVERVIEW_DECISION_SCHEMA,
            "decision": decision,
            "reason": reason,
            "evidence_refs": evidence_refs or [],
            "authority_fingerprint": authority_fingerprint,
            "decided_at": None if decision == "undecided" else _utc_now_iso(),
        }
    )
    existing = registry.get("project_overview")
    comparable = ("decision", "reason", "evidence_refs", "authority_fingerprint")
    if isinstance(existing, dict) and all(existing.get(key) == candidate.get(key) for key in comparable):
        return registry, False
    registry["project_overview"] = candidate
    return _write_registry(project, registry), True


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _round_projection(
    target_id: str,
    row: dict[str, object],
    *,
    route_ref: object = None,
) -> dict[str, object]:
    started = _parse_time(row.get("started_at"))
    ended = _parse_time(row.get("ended_at"))
    updated = _parse_time(row.get("updated_at"))
    duration = max(0.0, (ended - started).total_seconds()) if started and ended else None
    lower_bound = max(0.0, ((updated or started) - started).total_seconds()) if started and not ended else None
    phase = str(row.get("phase") or "unknown")
    milestone = str(row.get("milestone") or "") or None
    if ended:
        status = "interrupted" if milestone == "superseded_by_recovery" else "completed"
    else:
        status = "incomplete"
    generation = row.get("generation")
    return {
        "schema_version": OBSERVER_TARGET_RUN_SCHEMA,
        "target_id": target_id,
        "run_id": f"continuation-g{generation}-{row.get('runner_id')}",
        "source": "continuation_round",
        "generation": generation,
        "runner_id": row.get("runner_id"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("ended_at"),
        "last_activity_at": row.get("updated_at"),
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "lower_bound_duration_seconds": round(lower_bound, 3) if lower_bound is not None else None,
        "status": status,
        "phase": phase,
        "major_outcome": milestone,
        "route_ref": _validate_runtime_text(route_ref, "target run route_ref"),
        "evidence_refs": list(row.get("evidence_refs") or []),
    }


def _target_matches_continuation(target: dict[str, object], row: dict[str, object]) -> bool:
    task_id = target.get("continuation_task_id")
    if task_id and row.get("task_id") != task_id:
        return False
    if target.get("mode") == "fixed_workstream":
        return row.get("workstream_id") == target.get("workstream_id")
    return bool(task_id and row.get("task_id") == task_id)


def continuation_round_history(target: dict[str, object], continuations: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for continuation in continuations:
        if not _target_matches_continuation(target, continuation):
            continue
        source_dir = continuation.get("source_dir")
        if not isinstance(source_dir, str) or not source_dir:
            continue
        path = Path(source_dir) / "rounds.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for raw in payload.get("rounds") or [] if isinstance(payload, dict) else []:
            if not isinstance(raw, dict):
                continue
            run = _round_projection(
                str(target["target_id"]),
                raw,
                route_ref=target.get("route_ref"),
            )
            run_id = str(run["run_id"])
            if run_id in seen:
                continue
            seen.add(run_id)
            rows.append(run)
    rows.sort(key=lambda row: (str(row.get("started_at") or ""), str(row.get("run_id") or "")))
    return rows


def target_marker_run_history(project: Any, target: dict[str, object]) -> list[dict[str, object]]:
    target_id = str(target["target_id"])
    events = _read_run_events(project, target_id)
    by_run: dict[str, dict[str, dict[str, object]]] = {}
    for event in events:
        run_id = event.get("run_id")
        event_kind = event.get("event_kind")
        if not isinstance(run_id, str) or event_kind not in {"start", "finish"}:
            continue
        by_run.setdefault(run_id, {})[str(event_kind)] = event
    rows: list[dict[str, object]] = []
    for run_id, pair in by_run.items():
        start = pair.get("start")
        if not isinstance(start, dict):
            continue
        finish = pair.get("finish")
        started = _parse_time(start.get("observed_at"))
        ended = _parse_time(finish.get("observed_at")) if isinstance(finish, dict) else None
        duration = max(0.0, (ended - started).total_seconds()) if started and ended else None
        result = finish.get("result") if isinstance(finish, dict) else None
        rows.append(
            {
                "schema_version": OBSERVER_TARGET_RUN_SCHEMA,
                "target_id": target_id,
                "run_id": run_id,
                "source": "observer_marker",
                "generation": None,
                "runner_id": None,
                "started_at": start.get("observed_at"),
                "finished_at": finish.get("observed_at") if isinstance(finish, dict) else None,
                "last_activity_at": (
                    finish.get("observed_at") if isinstance(finish, dict) else start.get("observed_at")
                ),
                "duration_seconds": round(duration, 3) if duration is not None else None,
                "lower_bound_duration_seconds": 0.0 if finish is None else None,
                "status": "completed" if finish is not None else "incomplete",
                "result": result,
                "phase": None,
                "major_outcome": finish.get("major_outcome") if isinstance(finish, dict) else None,
                "route_ref": (
                    finish.get("route_ref")
                    if isinstance(finish, dict) and finish.get("route_ref") is not None
                    else start.get("route_ref") or target.get("route_ref")
                ),
                "evidence_refs": list(
                    dict.fromkeys(
                        [
                            *[str(item) for item in start.get("evidence_refs") or []],
                            *(
                                [str(item) for item in finish.get("evidence_refs") or []]
                                if isinstance(finish, dict)
                                else []
                            ),
                        ]
                    )
                ),
            }
        )
    rows.sort(key=lambda row: (str(row.get("started_at") or ""), str(row.get("run_id") or "")))
    return rows


def build_target_views(
    project: Any,
    current: dict[str, object],
    *,
    target_ids: set[str] | None = None,
) -> dict[str, object]:
    registry = read_target_registry(project)
    expected_registry = read_expected_target_registry(project)
    workstreams = [row for row in current.get("workstreams") or [] if isinstance(row, dict)]
    continuations = [row for row in current.get("continuations") or [] if isinstance(row, dict)]
    views: list[dict[str, object]] = []
    for target in registry["targets"]:
        target_id = str(target.get("target_id") or "")
        if target_ids is not None and target_id not in target_ids:
            continue
        matched_continuations = [row for row in continuations if _target_matches_continuation(target, row)]
        workstream_ids = {
            str(row.get("workstream_id"))
            for row in matched_continuations
            if isinstance(row.get("workstream_id"), str) and row.get("workstream_id")
        }
        if target.get("mode") == "fixed_workstream" and target.get("workstream_id"):
            workstream_ids.add(str(target["workstream_id"]))
        matched_workstreams = [row for row in workstreams if row.get("id") in workstream_ids]
        continuation_runs = continuation_round_history(target, matched_continuations)
        marker_runs = target_marker_run_history(project, target)
        runs = sorted(
            [*continuation_runs, *marker_runs],
            key=lambda row: (str(row.get("started_at") or ""), str(row.get("run_id") or "")),
        )
        views.append(
            {
                "target": dict(target),
                "workstreams": matched_workstreams,
                "continuations": matched_continuations,
                "runs": runs,
                "latest_run": runs[-1] if runs else None,
            }
        )
    return {
        "schema_version": OBSERVER_TARGET_REGISTRY_SCHEMA,
        "project_id": project.project_id,
        "registry_revision": registry["revision"],
        "expected_registry_revision": expected_registry["revision"],
        "registry_health": target_registry_health(
            project,
            registry=registry,
            expected_registry=expected_registry,
        ),
        "project_overview": registry["project_overview"],
        "target_count": len(views),
        "targets": views,
    }
