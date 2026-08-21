"""Read-only continuation state discovery and explicit schema migration helpers.

This module never decides task ownership or liveness.  It only inspects the
user-level ACF_HOME continuation namespace, reports schema compatibility, and
prepares deterministic migrations for schemas that the current ACF explicitly
knows how to upgrade without discarding history.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from ai_context_framework import continuation_workspace


MIGRATION_RECEIPT_SCHEMA = "acf.continuation.state-migration.v1"
MAX_STATE_FILE_BYTES = 2 * 1024 * 1024

PRESERVED_HISTORY_FILES = (
    "control.json",
    "state.json",
    "rounds.json",
    "effects.json",
    "coordination.json",
    "reconcile.json",
    "last_recovery.json",
    "last_run.json",
    "pause.json",
    "lease.json",
)


class ContinuationInventoryError(RuntimeError):
    def __init__(self, message: str, *, code: str = "continuation_inventory_error") -> None:
        super().__init__(message)
        self.code = code


def path_key(value: str | Path) -> str:
    normalized = str(Path(value).expanduser().resolve(strict=False)).replace("\\", "/")
    return normalized.casefold() if os.name == "nt" else normalized


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_digest(path: Path) -> str | None:
    try:
        return sha256_bytes(path.read_bytes())
    except FileNotFoundError:
        return None


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, "absent"
    except OSError:
        return None, "unreadable"
    if len(raw) > MAX_STATE_FILE_BYTES:
        return None, "oversize"
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid_json"
    if not isinstance(value, dict):
        return None, "not_object"
    return value, None


def inspect_schema_file(
    path: Path,
    *,
    current: tuple[str, ...],
    legacy_migratable: tuple[str, ...] = (),
    required: bool = False,
) -> dict[str, Any]:
    payload, error = read_json_object(path)
    if error == "absent":
        return {
            "present": False,
            "required": required,
            "schema_version": None,
            "compatibility": "missing_required" if required else "absent",
        }
    if error is not None:
        return {
            "present": True,
            "required": required,
            "schema_version": None,
            "compatibility": error,
        }
    assert payload is not None
    schema = payload.get("schema_version")
    if not isinstance(schema, str) or not schema:
        compatibility = "schema_missing"
    elif schema in current:
        compatibility = "current"
    elif schema in legacy_migratable:
        compatibility = "legacy_migratable"
    else:
        compatibility = "unsupported"
    return {
        "present": True,
        "required": required,
        "schema_version": schema if isinstance(schema, str) else None,
        "compatibility": compatibility,
    }


def inspect_task_dir(
    directory: Path,
    *,
    contracts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    directory = directory.resolve(strict=False)
    schemas: dict[str, dict[str, Any]] = {}
    for filename, contract in contracts.items():
        schemas[filename] = inspect_schema_file(
            directory / filename,
            current=tuple(str(value) for value in contract.get("current", ())),
            legacy_migratable=tuple(
                str(value) for value in contract.get("legacy_migratable", ())
            ),
            required=bool(contract.get("required", False)),
        )

    blocking_states = {
        "missing_required",
        "unreadable",
        "oversize",
        "invalid_json",
        "not_object",
        "schema_missing",
        "unsupported",
    }
    blocked_files = sorted(
        filename
        for filename, item in schemas.items()
        if item["compatibility"] in blocking_states
    )
    migration_files = sorted(
        filename
        for filename, item in schemas.items()
        if item["compatibility"] == "legacy_migratable"
    )
    if blocked_files:
        compatibility = "blocked"
    elif migration_files:
        compatibility = "migration_available"
    else:
        compatibility = "current"

    control, control_error = read_json_object(directory / "control.json")
    control = control if control_error is None and control is not None else {}
    timing = {
        field: control.get(field)
        for field in (
            "interval_minutes",
            "lease_ttl_minutes",
            "renew_interval_minutes",
            "heartbeat_interval_minutes",
            "stale_after_minutes",
        )
    }
    return {
        "state_dir": str(directory),
        "project_key": directory.parent.parent.name if len(directory.parents) >= 2 else None,
        "task_key": directory.name,
        "task_id": control.get("task_id"),
        "workstream_id": control.get("workstream_id"),
        "workspace_root": control.get("workspace_root"),
        "expected_branch": control.get("expected_branch"),
        "control_generation": control.get("generation"),
        "timing_profile": control.get("timing_profile"),
        "timing": timing,
        "schemas": schemas,
        "compatibility": compatibility,
        "migration_required": bool(migration_files),
        "migration_files": migration_files,
        "blocked_files": blocked_files,
    }


def discover_tasks(
    acf_home: Path,
    *,
    contracts: Mapping[str, Mapping[str, Any]],
    workspace_root: Path | None = None,
    task_id: str | None = None,
) -> list[dict[str, Any]]:
    projects_root = acf_home.resolve(strict=False) / "projects"
    expected_workspace = path_key(workspace_root) if workspace_root is not None else None
    results: list[dict[str, Any]] = []
    if not projects_root.is_dir():
        return results
    for project_dir in sorted(path for path in projects_root.iterdir() if path.is_dir()):
        continuation_root = project_dir / "continuation"
        if not continuation_root.is_dir():
            continue
        for task_dir in sorted(path for path in continuation_root.iterdir() if path.is_dir()):
            item = inspect_task_dir(task_dir, contracts=contracts)
            if expected_workspace is not None:
                raw_workspace = item.get("workspace_root")
                if not isinstance(raw_workspace, str) or path_key(raw_workspace) != expected_workspace:
                    continue
            if task_id is not None and str(item.get("task_id") or "") != task_id:
                continue
            results.append(item)
    results.sort(
        key=lambda item: (
            str(item.get("workspace_root") or ""),
            str(item.get("task_id") or item.get("task_key") or ""),
        )
    )
    return results


def preserved_history_digests(directory: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for filename in PRESERVED_HISTORY_FILES:
        digest = file_digest(directory / filename)
        if digest is not None:
            result[filename] = digest
    for path in sorted(directory.glob("effects.archive.*.json")):
        if not path.is_file():
            continue
        digest = file_digest(path)
        if digest is not None:
            result[path.name] = digest
    return result


def workspace_migration_plan(directory: Path, *, task_id: str) -> dict[str, Any]:
    workspace_path = directory / "workspace.json"
    payload, error = read_json_object(workspace_path)
    if error == "absent":
        return {
            "migration_required": False,
            "status": "workspace_absent",
            "from_schema": None,
            "to_schema": continuation_workspace.WORKSPACE_SCHEMA,
        }
    if error is not None or payload is None:
        raise ContinuationInventoryError(
            f"workspace state cannot be inspected: {error}", code="continuation_migration_blocked"
        )
    schema = payload.get("schema_version")
    if schema == continuation_workspace.WORKSPACE_SCHEMA:
        return {
            "migration_required": False,
            "status": "current",
            "from_schema": schema,
            "to_schema": continuation_workspace.WORKSPACE_SCHEMA,
        }
    if schema not in {
        continuation_workspace.LEGACY_WORKSPACE_SCHEMA,
        continuation_workspace.LEGACY_WORKSPACE_SCHEMA_V2,
    }:
        raise ContinuationInventoryError(
            f"unsupported workspace schema: {schema}", code="continuation_migration_blocked"
        )
    try:
        migrated = continuation_workspace.validate_manifest(payload, task_id=task_id)
    except continuation_workspace.ContinuationWorkspaceError as exc:
        raise ContinuationInventoryError(
            str(exc), code="continuation_migration_blocked"
        ) from exc
    before = workspace_path.read_bytes()
    after = (
        json.dumps(migrated, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    return {
        "migration_required": True,
        "status": "migration_available",
        "from_schema": schema,
        "to_schema": continuation_workspace.WORKSPACE_SCHEMA,
        "before_sha256": sha256_bytes(before),
        "after_sha256": sha256_bytes(after),
        "payload": migrated,
    }


def migration_receipt(
    directory: Path,
    *,
    task_id: str,
    workspace_root: str,
    reason: str,
    migrated_at: str,
    plan: Mapping[str, Any],
    history_digests: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": MIGRATION_RECEIPT_SCHEMA,
        "task_id": task_id,
        "workspace_root": workspace_root,
        "state_dir": str(directory.resolve(strict=False)),
        "migrated_at": migrated_at,
        "reason": reason,
        "changes": [
            {
                "file": "workspace.json",
                "from_schema": plan.get("from_schema"),
                "to_schema": plan.get("to_schema"),
                "before_sha256": plan.get("before_sha256"),
                "after_sha256": plan.get("after_sha256"),
            }
        ],
        "preserved_history_digests": dict(sorted(history_digests.items())),
    }
