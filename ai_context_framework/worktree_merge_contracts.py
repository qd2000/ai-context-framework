"""Stable contracts for the resilient worktree merge pipeline.

The first implementation phase intentionally keeps these contracts separate from
``worktree_service``.  Later phases can adopt them without changing the schema
or retry defaults while the currently released merge behavior remains intact.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping


MERGE_OPERATION_SCHEMA_VERSION = "acf.git_operation.v2"
ARTIFACT_HANDOFF_SCHEMA_VERSION = "acf.artifact_handoff.v1"
MERGE_STRATEGY = "temporary_integration_worktree"
PROMOTION_STRATEGY = "fast_forward"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MergeOperationState(str, Enum):
    PLANNED = "PLANNED"
    SOURCE_VERIFYING = "SOURCE_VERIFYING"
    SOURCE_VERIFIED = "SOURCE_VERIFIED"
    ARTIFACTS_PLANNING = "ARTIFACTS_PLANNING"
    ARTIFACTS_PLANNED = "ARTIFACTS_PLANNED"
    INTEGRATION_CREATING = "INTEGRATION_CREATING"
    INTEGRATION_READY = "INTEGRATION_READY"
    MERGING_SOURCE = "MERGING_SOURCE"
    CONFLICT_RESOLUTION_REQUIRED = "CONFLICT_RESOLUTION_REQUIRED"
    CANDIDATE_READY = "CANDIDATE_READY"
    CANDIDATE_VALIDATING = "CANDIDATE_VALIDATING"
    CANDIDATE_VALIDATED = "CANDIDATE_VALIDATED"
    ARTIFACTS_MIGRATING = "ARTIFACTS_MIGRATING"
    ARTIFACTS_VERIFIED = "ARTIFACTS_VERIFIED"
    WAITING_PROMOTION = "WAITING_PROMOTION"
    PROMOTING = "PROMOTING"
    PROMOTED = "PROMOTED"
    POST_VERIFY = "POST_VERIFY"
    MERGED = "MERGED"
    READY_TO_CLOSE = "READY_TO_CLOSE"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    PAUSED_RETRYABLE = "PAUSED_RETRYABLE"
    MANUAL_ACTION_REQUIRED = "MANUAL_ACTION_REQUIRED"
    FAILED_TERMINAL = "FAILED_TERMINAL"


class ArtifactClassification(str, Enum):
    REQUIRED = "required"
    RETAINED_REFERENCE = "retained_reference"
    REPRODUCIBLE_CACHE = "reproducible_cache"
    DISCARDABLE = "discardable"
    UNKNOWN = "unknown"


class ArtifactEntryStatus(str, Enum):
    PLANNED = "planned"
    COPIED = "copied"
    VERIFIED = "verified"
    ACKNOWLEDGED = "acknowledged"
    UNCLASSIFIED = "unclassified"
    FAILED = "failed"


@dataclass(frozen=True)
class MergeRetryPolicy:
    max_replans: int = 8
    conflict_replans: int = 3
    lock_wait_timeout_seconds: int = 300
    state_wait_timeout_seconds: int = 600
    initial_delay_seconds: float = 0.5
    max_delay_seconds: float = 15.0
    jitter_ratio: float = 0.20

    def validate(self) -> None:
        if self.max_replans < 0:
            raise ValueError("max_replans must be non-negative")
        if self.conflict_replans < 0:
            raise ValueError("conflict_replans must be non-negative")
        if self.lock_wait_timeout_seconds < 0:
            raise ValueError("lock_wait_timeout_seconds must be non-negative")
        if self.state_wait_timeout_seconds < 0:
            raise ValueError("state_wait_timeout_seconds must be non-negative")
        if self.initial_delay_seconds <= 0:
            raise ValueError("initial_delay_seconds must be positive")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("max_delay_seconds must be >= initial_delay_seconds")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")

    def to_payload(self) -> dict[str, int | float]:
        self.validate()
        return asdict(self)


DEFAULT_MERGE_RETRY_POLICY = MergeRetryPolicy()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_merge_operation_v2(
    *,
    operation_id: str,
    target_key: str,
    source_branch: str,
    source_path: str,
    source_head: str,
    primary_branch: str,
    primary_checkout: str,
    primary_head: str,
    integration_branch: str,
    integration_path: str,
    retry_policy: MergeRetryPolicy = DEFAULT_MERGE_RETRY_POLICY,
    timestamp: str | None = None,
) -> dict[str, Any]:
    for name, value in {
        "operation_id": operation_id,
        "target_key": target_key,
        "source_branch": source_branch,
        "source_path": source_path,
        "source_head": source_head,
        "primary_branch": primary_branch,
        "primary_checkout": primary_checkout,
        "primary_head": primary_head,
        "integration_branch": integration_branch,
        "integration_path": integration_path,
    }.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    now = timestamp or utc_now()
    payload: dict[str, Any] = {
        "schema_version": MERGE_OPERATION_SCHEMA_VERSION,
        "operation_id": operation_id,
        "command": "worktree.merge",
        "state": MergeOperationState.PLANNED.value,
        "target_key": target_key,
        "merge_strategy": MERGE_STRATEGY,
        "promotion_strategy": PROMOTION_STRATEGY,
        "source": {
            "branch": source_branch,
            "path": source_path,
            "head": source_head,
        },
        "primary": {
            "branch": primary_branch,
            "checkout": primary_checkout,
            "head": primary_head,
        },
        "integration": {
            "branch": integration_branch,
            "path": integration_path,
            "base_head": primary_head,
            "tip": None,
            "conflicts": [],
        },
        "retry_policy": retry_policy.to_payload(),
        "attempts": {
            "replans": 0,
            "conflict_replans": 0,
            "lock_waits": 0,
            "state_waits": 0,
        },
        "checks": {"pre": [], "post": []},
        "primary_protection": {
            "before": None,
            "after": None,
            "identical_overlap_paths": [],
            "divergent_overlap_paths": [],
        },
        "artifact_handoff": {
            "status": "not_planned",
            "manifest_path": None,
        },
        "steps": {},
        "resume_allowed": True,
        "pause_reason": None,
        "next_action": "verify_source",
        "created_at": now,
        "updated_at": now,
    }
    validate_merge_operation_v2(payload)
    return payload


def validate_merge_operation_v2(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != MERGE_OPERATION_SCHEMA_VERSION:
        raise ValueError("invalid merge operation schema_version")
    if payload.get("command") != "worktree.merge":
        raise ValueError("merge operation command must be worktree.merge")
    if payload.get("merge_strategy") != MERGE_STRATEGY:
        raise ValueError("merge operation must use temporary integration worktree")
    if payload.get("promotion_strategy") != PROMOTION_STRATEGY:
        raise ValueError("merge operation must use fast-forward promotion")

    operation_id = payload.get("operation_id")
    target_key = payload.get("target_key")
    if not isinstance(operation_id, str) or not operation_id:
        raise ValueError("operation_id must be a non-empty string")
    if not isinstance(target_key, str) or not target_key:
        raise ValueError("target_key must be a non-empty string")

    try:
        MergeOperationState(str(payload.get("state")))
    except ValueError as exc:
        raise ValueError("invalid merge operation state") from exc

    source = _require_mapping(payload, "source")
    primary = _require_mapping(payload, "primary")
    integration = _require_mapping(payload, "integration")
    for owner, values, fields in (
        ("source", source, ("branch", "path", "head")),
        ("primary", primary, ("branch", "checkout", "head")),
        ("integration", integration, ("branch", "path", "base_head")),
    ):
        for field in fields:
            value = values.get(field)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{owner}.{field} must be a non-empty string")

    retry = _require_mapping(payload, "retry_policy")
    policy = MergeRetryPolicy(
        max_replans=_require_int(retry, "max_replans"),
        conflict_replans=_require_int(retry, "conflict_replans"),
        lock_wait_timeout_seconds=_require_int(retry, "lock_wait_timeout_seconds"),
        state_wait_timeout_seconds=_require_int(retry, "state_wait_timeout_seconds"),
        initial_delay_seconds=_require_number(retry, "initial_delay_seconds"),
        max_delay_seconds=_require_number(retry, "max_delay_seconds"),
        jitter_ratio=_require_number(retry, "jitter_ratio"),
    )
    policy.validate()

    if not isinstance(payload.get("resume_allowed"), bool):
        raise ValueError("resume_allowed must be boolean")
    if not isinstance(payload.get("steps"), Mapping):
        raise ValueError("steps must be an object")


def build_artifact_handoff_v1(
    *,
    target_key: str,
    source_head: str,
    entries: Iterable[Mapping[str, Any]],
    timestamp: str | None = None,
) -> dict[str, Any]:
    if not target_key:
        raise ValueError("target_key must be a non-empty string")
    if not source_head:
        raise ValueError("source_head must be a non-empty string")
    now = timestamp or utc_now()
    payload: dict[str, Any] = {
        "schema_version": ARTIFACT_HANDOFF_SCHEMA_VERSION,
        "target_key": target_key,
        "source_head": source_head,
        "status": "planned",
        "entries": [dict(entry) for entry in entries],
        "created_at": now,
        "updated_at": now,
    }
    validate_artifact_handoff_v1(payload)
    return payload


def validate_artifact_handoff_v1(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != ARTIFACT_HANDOFF_SCHEMA_VERSION:
        raise ValueError("invalid artifact handoff schema_version")
    if not isinstance(payload.get("target_key"), str) or not payload.get("target_key"):
        raise ValueError("target_key must be a non-empty string")
    if not isinstance(payload.get("source_head"), str) or not payload.get("source_head"):
        raise ValueError("source_head must be a non-empty string")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("entries must be an array")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("artifact entry must be an object")
        relative_path = entry.get("relative_path")
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError("artifact relative_path must be a non-empty string")
        normalized = _validate_relative_path(relative_path)
        if normalized in seen:
            raise ValueError(f"duplicate artifact relative_path: {normalized}")
        seen.add(normalized)

        try:
            classification = ArtifactClassification(str(entry.get("classification")))
        except ValueError as exc:
            raise ValueError(f"invalid artifact classification for {normalized}") from exc
        try:
            status = ArtifactEntryStatus(str(entry.get("status")))
        except ValueError as exc:
            raise ValueError(f"invalid artifact status for {normalized}") from exc

        transfer = entry.get("transfer")
        if transfer not in {"copy", "reference", "none"}:
            raise ValueError(f"invalid artifact transfer for {normalized}")
        destination = entry.get("destination")
        rationale = entry.get("rationale")

        if classification is ArtifactClassification.REQUIRED:
            if transfer != "copy" or not isinstance(destination, str) or not destination:
                raise ValueError(f"required artifact needs copy destination: {normalized}")
        elif classification is ArtifactClassification.RETAINED_REFERENCE:
            if transfer != "reference" or not isinstance(destination, str) or not destination:
                raise ValueError(f"retained_reference needs stable destination: {normalized}")
        elif classification in {
            ArtifactClassification.REPRODUCIBLE_CACHE,
            ArtifactClassification.DISCARDABLE,
        }:
            if transfer != "none" or not isinstance(rationale, str) or not rationale:
                raise ValueError(f"{classification.value} needs rationale: {normalized}")
        elif classification is ArtifactClassification.UNKNOWN:
            if status is not ArtifactEntryStatus.UNCLASSIFIED:
                raise ValueError(f"unknown artifact must be unclassified: {normalized}")

        size = entry.get("size")
        if size is not None and (not isinstance(size, int) or isinstance(size, bool) or size < 0):
            raise ValueError(f"invalid artifact size for {normalized}")
        digest = entry.get("sha256")
        if digest is not None and (not isinstance(digest, str) or not _SHA256_RE.match(digest)):
            raise ValueError(f"invalid artifact sha256 for {normalized}")
        if status is ArtifactEntryStatus.VERIFIED and (size is None or digest is None):
            raise ValueError(f"verified artifact needs size and sha256: {normalized}")


def artifact_handoff_ready_for_promotion(payload: Mapping[str, Any]) -> bool:
    validate_artifact_handoff_v1(payload)
    for entry in payload["entries"]:
        classification = ArtifactClassification(entry["classification"])
        status = ArtifactEntryStatus(entry["status"])
        if classification is ArtifactClassification.UNKNOWN:
            return False
        if classification in {
            ArtifactClassification.REQUIRED,
            ArtifactClassification.RETAINED_REFERENCE,
        }:
            if status is not ArtifactEntryStatus.VERIFIED:
                return False
        elif status is not ArtifactEntryStatus.ACKNOWLEDGED:
            return False
    return True


def _validate_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or normalized.startswith("/"):
        raise ValueError(f"artifact path must be relative: {value}")
    return path.as_posix()


def _require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _require_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _require_number(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} must be a number")
    return float(value)
