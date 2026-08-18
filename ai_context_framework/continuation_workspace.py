"""Bounded Git-workspace ownership metadata for continuation rounds.

This module deliberately does not edit project files.  It records compact
path/status/content digests so continuation can distinguish protected external
dirty state from paths explicitly owned by the current fenced round.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


WORKSPACE_SCHEMA = "acf.continuation.workspace.v2"
LEGACY_WORKSPACE_SCHEMA = "acf.continuation.workspace.v1"
ENTRY_SCHEMA = "acf.continuation.workspace-entry.v1"
CONFLICT_SCHEMA = "acf.continuation.workspace-conflict.v1"

MAX_ENTRIES = 256
MAX_PATH_BYTES = 1024
MAX_MANIFEST_BYTES = 128 * 1024


class ContinuationWorkspaceError(ValueError):
    def __init__(self, message: str, *, code: str = "workspace_manifest_invalid") -> None:
        super().__init__(message)
        self.code = code


def _text(value: Any, *, field: str, max_bytes: int = MAX_PATH_BYTES) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContinuationWorkspaceError(f"{field} must be a non-empty string")
    text = value.strip()
    if len(text.encode("utf-8")) > max_bytes:
        raise ContinuationWorkspaceError(f"{field} exceeds {max_bytes} bytes")
    return text


def normalize_path(value: str) -> str:
    text = _text(value, field="path").replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        raise ContinuationWorkspaceError("workspace path must be repository-relative", code="workspace_path_invalid")
    parts = [part for part in text.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ContinuationWorkspaceError("workspace path escapes the repository", code="workspace_path_invalid")
    if any("*" in part or "?" in part for part in parts):
        raise ContinuationWorkspaceError("workspace intent paths must be concrete", code="workspace_path_invalid")
    return "/".join(parts)


def paths_overlap(left: str, right: str) -> bool:
    left_norm = normalize_path(left)
    right_norm = normalize_path(right)
    return (
        left_norm == right_norm
        or left_norm.startswith(right_norm.rstrip("/") + "/")
        or right_norm.startswith(left_norm.rstrip("/") + "/")
    )


def path_matches_scope(path_value: str, scope_value: str) -> bool:
    path_value = path_value.replace("\\", "/")
    scope_value = scope_value.replace("\\", "/")
    while path_value.startswith("./"):
        path_value = path_value[2:]
    while scope_value.startswith("./"):
        scope_value = scope_value[2:]
    if "*" in scope_value:
        return fnmatch.fnmatch(path_value, scope_value)
    return path_value == scope_value or path_value.startswith(scope_value.rstrip("/") + "/")


def _run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise ContinuationWorkspaceError(
            completed.stderr.strip() or "git workspace inspection failed",
            code="workspace_git_failed",
        )
    return completed.stdout


def _entry_digest(root: Path, path_value: str, status: str) -> str:
    path = root / Path(path_value)
    digest = hashlib.sha256()
    digest.update(status.encode("utf-8"))
    digest.update(b"\0")
    try:
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        elif path.is_file():
            digest.update(b"file\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        elif path.exists():
            digest.update(b"other\0")
            digest.update(str(path.stat().st_mode).encode("ascii"))
        else:
            digest.update(b"missing")
    except OSError as exc:
        raise ContinuationWorkspaceError(
            f"cannot digest workspace path {path_value}: {exc}",
            code="workspace_digest_failed",
        ) from exc
    return digest.hexdigest()


def git_snapshot(root: Path) -> dict[str, Any]:
    root = root.resolve()
    head = _run_git(root, "rev-parse", "HEAD").strip()
    raw = _run_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    tokens = raw.split("\0")
    entries: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        if len(token) < 4:
            raise ContinuationWorkspaceError("unexpected git porcelain entry", code="workspace_git_invalid")
        status = token[:2]
        path_value = token[3:]
        paths = [path_value]
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            if index >= len(tokens) or not tokens[index]:
                raise ContinuationWorkspaceError("rename source is missing", code="workspace_git_invalid")
            paths.append(tokens[index])
            index += 1
        for candidate in paths:
            normalized = normalize_path(candidate)
            entries.append(
                {
                    "schema_version": ENTRY_SCHEMA,
                    "path": normalized,
                    "status": status,
                    "digest": _entry_digest(root, normalized, status),
                }
            )
    entries.sort(key=lambda item: item["path"])
    if len(entries) > MAX_ENTRIES:
        raise ContinuationWorkspaceError("workspace manifest entry limit exceeded", code="workspace_manifest_full")
    return {"head": head, "entries": entries}


def _entry(value: Mapping[str, Any]) -> dict[str, str]:
    record = dict(value)
    if set(record) != {"schema_version", "path", "status", "digest"} or record.get("schema_version") != ENTRY_SCHEMA:
        raise ContinuationWorkspaceError("workspace entry schema is invalid")
    path_value = normalize_path(_text(record.get("path"), field="path"))
    status = _text(record.get("status"), field="status", max_bytes=16)
    digest = _text(record.get("digest"), field="digest", max_bytes=128)
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ContinuationWorkspaceError("workspace entry digest is invalid")
    return {"schema_version": ENTRY_SCHEMA, "path": path_value, "status": status, "digest": digest}


def _entries(values: Any, *, field: str) -> list[dict[str, str]]:
    if not isinstance(values, list) or len(values) > MAX_ENTRIES:
        raise ContinuationWorkspaceError(f"{field} must be a bounded list")
    result = [_entry(value) for value in values if isinstance(value, Mapping)]
    if len(result) != len(values):
        raise ContinuationWorkspaceError(f"{field} contains a non-object entry")
    paths = [item["path"] for item in result]
    if len(paths) != len(set(paths)):
        raise ContinuationWorkspaceError(f"{field} contains duplicate paths")
    return sorted(result, key=lambda item: item["path"])


def _conflicts(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list) or len(values) > MAX_ENTRIES:
        raise ContinuationWorkspaceError("conflicts must be a bounded list")
    result: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ContinuationWorkspaceError("workspace conflict must be an object")
        record = dict(value)
        if set(record) != {"schema_version", "path", "reason"} or record.get("schema_version") != CONFLICT_SCHEMA:
            raise ContinuationWorkspaceError("workspace conflict schema is invalid")
        result.append(
            {
                "schema_version": CONFLICT_SCHEMA,
                "path": normalize_path(_text(record.get("path"), field="path")),
                "reason": _text(record.get("reason"), field="reason", max_bytes=512),
            }
        )
    return result


def _bounded(payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ContinuationWorkspaceError("workspace manifest exceeds bounded size", code="workspace_manifest_full")


def validate_manifest(payload: Mapping[str, Any], *, task_id: str) -> dict[str, Any]:
    manifest = dict(payload)
    legacy_allowed = {
        "schema_version",
        "task_id",
        "baseline_head",
        "generation",
        "baseline_external",
        "write_intents",
        "runner_owned",
        "unexpected_nonoverlap",
        "conflicts",
        "last_observed_at",
    }
    if manifest.get("schema_version") == LEGACY_WORKSPACE_SCHEMA and set(manifest) == legacy_allowed:
        manifest = {
            "schema_version": WORKSPACE_SCHEMA,
            "task_id": manifest.get("task_id"),
            "baseline_head": manifest.get("baseline_head"),
            "generation": manifest.get("generation"),
            "baseline_external": manifest.get("baseline_external"),
            "write_intents": manifest.get("write_intents"),
            "task_owned": manifest.get("runner_owned"),
            "unexpected_nonoverlap": manifest.get("unexpected_nonoverlap"),
            "conflicts": manifest.get("conflicts"),
            "last_observed_at": manifest.get("last_observed_at"),
        }
    allowed = {
        "schema_version",
        "task_id",
        "baseline_head",
        "generation",
        "baseline_external",
        "write_intents",
        "task_owned",
        "unexpected_nonoverlap",
        "conflicts",
        "last_observed_at",
    }
    if manifest.get("schema_version") != WORKSPACE_SCHEMA or set(manifest) != allowed:
        raise ContinuationWorkspaceError("workspace manifest schema is invalid")
    if manifest.get("task_id") != task_id:
        raise ContinuationWorkspaceError("workspace manifest task identity mismatch")
    generation = manifest.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise ContinuationWorkspaceError("workspace generation is invalid")
    intents = manifest.get("write_intents")
    if not isinstance(intents, list) or len(intents) > MAX_ENTRIES:
        raise ContinuationWorkspaceError("write_intents must be a bounded list")
    normalized_intents = [normalize_path(_text(item, field="write_intent")) for item in intents]
    if len(normalized_intents) != len(set(normalized_intents)):
        raise ContinuationWorkspaceError("write_intents contain duplicates")
    result = {
        "schema_version": WORKSPACE_SCHEMA,
        "task_id": task_id,
        "baseline_head": _text(manifest.get("baseline_head"), field="baseline_head", max_bytes=128),
        "generation": generation,
        "baseline_external": _entries(manifest.get("baseline_external"), field="baseline_external"),
        "write_intents": sorted(normalized_intents),
        "task_owned": _entries(manifest.get("task_owned"), field="task_owned"),
        "unexpected_nonoverlap": _entries(manifest.get("unexpected_nonoverlap"), field="unexpected_nonoverlap"),
        "conflicts": _conflicts(manifest.get("conflicts")),
        "last_observed_at": _text(manifest.get("last_observed_at"), field="last_observed_at", max_bytes=128),
    }
    _bounded(result)
    return result


def new_manifest(*, task_id: str, snapshot: Mapping[str, Any], now: str) -> dict[str, Any]:
    payload = {
        "schema_version": WORKSPACE_SCHEMA,
        "task_id": task_id,
        "baseline_head": str(snapshot["head"]),
        "generation": 0,
        "baseline_external": list(snapshot["entries"]),
        "write_intents": [],
        "task_owned": [],
        "unexpected_nonoverlap": [],
        "conflicts": [],
        "last_observed_at": now,
    }
    return validate_manifest(payload, task_id=task_id)


def begin_generation(
    manifest: Mapping[str, Any],
    *,
    task_id: str,
    generation: int,
    snapshot: Mapping[str, Any],
    now: str,
) -> dict[str, Any]:
    current = observe_handoff(
        manifest,
        task_id=task_id,
        snapshot=snapshot,
        now=now,
    )
    if current["conflicts"]:
        raise ContinuationWorkspaceError(
            "task-owned workspace changed during ownerless handoff",
            code="workspace_conflict",
        )
    task_paths = [entry["path"] for entry in current["task_owned"]]
    retained_intents = [
        intent
        for intent in current["write_intents"]
        if any(paths_overlap(intent, path_value) for path_value in task_paths)
    ]
    baseline_external = _entry_map(
        [*current["baseline_external"], *current["unexpected_nonoverlap"]]
    )
    payload = {
        "schema_version": WORKSPACE_SCHEMA,
        "task_id": task_id,
        "baseline_head": str(snapshot["head"]),
        "generation": generation,
        "baseline_external": list(baseline_external.values()),
        "write_intents": retained_intents,
        "task_owned": list(current["task_owned"]),
        "unexpected_nonoverlap": [],
        "conflicts": [],
        "last_observed_at": now,
    }
    return validate_manifest(payload, task_id=task_id)


def recover_generation(
    manifest: Mapping[str, Any],
    *,
    task_id: str,
    previous_generation: int,
    generation: int,
    snapshot: Mapping[str, Any],
    now: str,
) -> dict[str, Any]:
    """Transfer evidence-backed dirty ownership into a fenced generation.

    Recovery preserves the interrupted task's declared write intents and
    attributable task-owned WIP.  Unrelated dirty state remains external and
    conflicts still fail closed.
    """

    if isinstance(previous_generation, bool) or not isinstance(previous_generation, int) or previous_generation < 1:
        raise ContinuationWorkspaceError(
            "previous workspace generation is invalid",
            code="workspace_generation_mismatch",
        )
    if isinstance(generation, bool) or not isinstance(generation, int) or generation <= previous_generation:
        raise ContinuationWorkspaceError(
            "recovery workspace generation must advance",
            code="workspace_generation_mismatch",
        )
    current = validate_manifest(manifest, task_id=task_id)
    if int(current["generation"]) != previous_generation:
        raise ContinuationWorkspaceError(
            "workspace manifest generation does not match interrupted owner",
            code="workspace_generation_mismatch",
        )
    current = classify(current, task_id=task_id, snapshot=snapshot, now=now)
    if current["conflicts"]:
        raise ContinuationWorkspaceError(
            "workspace contains ambiguous/conflicting dirty state",
            code="workspace_conflict",
        )
    payload = {
        **current,
        "baseline_head": str(snapshot["head"]),
        "generation": generation,
        "last_observed_at": now,
    }
    return validate_manifest(payload, task_id=task_id)


def _entry_map(values: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["path"]): dict(item) for item in values}


def classify(
    manifest: Mapping[str, Any],
    *,
    task_id: str,
    snapshot: Mapping[str, Any],
    now: str,
) -> dict[str, Any]:
    current = validate_manifest(manifest, task_id=task_id)
    baseline = _entry_map(current["baseline_external"])
    previous_task_owned = _entry_map(current["task_owned"])
    observed = _entry_map(snapshot["entries"])
    intents = list(current["write_intents"])
    baseline_external: list[dict[str, Any]] = []
    task_owned: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []
    conflicts: list[dict[str, str]] = []

    for path_value in baseline:
        live = observed.get(path_value)
        if any(paths_overlap(path_value, intent) for intent in intents):
            conflicts.append(
                {
                    "schema_version": CONFLICT_SCHEMA,
                    "path": path_value,
                    "reason": "write_intent_overlaps_baseline_external",
                }
            )
        elif live is not None:
            # The protected external owner may keep editing its own unrelated
            # path while this continuation round runs.  Refresh the observed
            # digest rather than turning unrelated human/agent activity into a
            # false parallelism blocker.
            baseline_external.append(live)

    for path_value, previous in previous_task_owned.items():
        live = observed.get(path_value)
        has_intent = any(paths_overlap(path_value, intent) for intent in intents)
        if live is None:
            if not has_intent:
                conflicts.append(
                    {
                        "schema_version": CONFLICT_SCHEMA,
                        "path": path_value,
                        "reason": "task_owned_changed_without_intent",
                    }
                )
            # With an active write intent, disappearance means the owner
            # intentionally cleaned, reverted, or committed the path.
            continue
        changed = live["status"] != previous["status"] or live["digest"] != previous["digest"]
        if changed and not has_intent:
            conflicts.append(
                {
                    "schema_version": CONFLICT_SCHEMA,
                    "path": path_value,
                    "reason": "task_owned_changed_without_intent",
                }
            )
        task_owned.append(live if has_intent else previous)

    for path_value, live in observed.items():
        if path_value in baseline or path_value in previous_task_owned:
            continue
        if any(paths_overlap(path_value, baseline_path) for baseline_path in baseline):
            conflicts.append(
                {
                    "schema_version": CONFLICT_SCHEMA,
                    "path": path_value,
                    "reason": "baseline_path_overlap",
                }
            )
        elif any(paths_overlap(path_value, task_path) for task_path in previous_task_owned):
            conflicts.append(
                {
                    "schema_version": CONFLICT_SCHEMA,
                    "path": path_value,
                    "reason": "task_owned_path_overlap",
                }
            )
        elif any(paths_overlap(path_value, intent) for intent in intents):
            task_owned.append(live)
        else:
            unexpected.append(live)

    payload = {
        **current,
        "task_owned": task_owned,
        "unexpected_nonoverlap": unexpected,
        "conflicts": conflicts,
        "last_observed_at": now,
    }
    return validate_manifest(payload, task_id=task_id)


def observe_handoff(
    manifest: Mapping[str, Any],
    *,
    task_id: str,
    snapshot: Mapping[str, Any],
    now: str,
) -> dict[str, Any]:
    """Observe an ownerless handoff without silently re-attributing task WIP.

    External dirty paths may continue changing while no continuation owner is
    present.  Task-owned WIP is different: its recorded status/content digest
    must remain unchanged until a new fenced generation claims it.  Any drift
    is provenance ambiguity and therefore a real workspace conflict.
    """

    current = validate_manifest(manifest, task_id=task_id)
    expected_task_owned = _entry_map(current["task_owned"])
    observed = _entry_map(snapshot["entries"])
    classified = classify(current, task_id=task_id, snapshot=snapshot, now=now)
    drift_conflicts: list[dict[str, str]] = []
    for path_value, expected in expected_task_owned.items():
        live = observed.get(path_value)
        if (
            live is None
            or live["status"] != expected["status"]
            or live["digest"] != expected["digest"]
        ):
            drift_conflicts.append(
                {
                    "schema_version": CONFLICT_SCHEMA,
                    "path": path_value,
                    "reason": "task_owned_handoff_drift",
                }
            )
    if not drift_conflicts:
        return classified
    payload = {
        **classified,
        "task_owned": list(current["task_owned"]),
        "conflicts": [*classified["conflicts"], *drift_conflicts],
        "last_observed_at": now,
    }
    return validate_manifest(payload, task_id=task_id)


def handoff_generation(
    manifest: Mapping[str, Any],
    *,
    task_id: str,
    snapshot: Mapping[str, Any],
    now: str,
) -> dict[str, Any]:
    """Prepare a normal lease release while retaining uncommitted task WIP."""

    current = classify(manifest, task_id=task_id, snapshot=snapshot, now=now)
    if current["conflicts"]:
        return current
    task_paths = [entry["path"] for entry in current["task_owned"]]
    retained_intents = [
        intent
        for intent in current["write_intents"]
        if any(paths_overlap(intent, path_value) for path_value in task_paths)
    ]
    baseline_external = _entry_map(
        [*current["baseline_external"], *current["unexpected_nonoverlap"]]
    )
    payload = {
        **current,
        "baseline_head": str(snapshot["head"]),
        "baseline_external": list(baseline_external.values()),
        "write_intents": retained_intents,
        "unexpected_nonoverlap": [],
        "last_observed_at": now,
    }
    return validate_manifest(payload, task_id=task_id)


def add_intents(
    manifest: Mapping[str, Any],
    *,
    task_id: str,
    paths: Sequence[str],
    allowed_scopes: Sequence[str],
    candidate_paths: Mapping[str, Sequence[str]],
    snapshot: Mapping[str, Any],
    now: str,
) -> dict[str, Any]:
    current = classify(manifest, task_id=task_id, snapshot=snapshot, now=now)
    if current["conflicts"]:
        raise ContinuationWorkspaceError(
            "workspace already contains ambiguous/conflicting dirty state",
            code="workspace_conflict",
        )
    existing_external = [
        *current["baseline_external"],
        *current["unexpected_nonoverlap"],
    ]
    intents = list(current["write_intents"])
    for raw_path in paths:
        path_value = normalize_path(raw_path)
        candidates = list(candidate_paths.get(path_value) or [path_value])
        if allowed_scopes and not any(
            path_matches_scope(candidate, scope)
            for candidate in candidates
            for scope in allowed_scopes
        ):
            raise ContinuationWorkspaceError(
                f"write intent is outside Workstream write_scope: {path_value}",
                code="workspace_intent_out_of_scope",
            )
        conflict = next(
            (
                str(entry["path"])
                for entry in existing_external
                if paths_overlap(path_value, str(entry["path"]))
            ),
            None,
        )
        if conflict is not None:
            raise ContinuationWorkspaceError(
                f"write intent overlaps protected external dirty path: {conflict}",
                code="workspace_intent_conflict",
            )
        if path_value not in intents:
            intents.append(path_value)
    payload = {**current, "write_intents": sorted(intents), "last_observed_at": now}
    return validate_manifest(payload, task_id=task_id)


def summary(manifest: Mapping[str, Any], *, task_id: str) -> dict[str, Any]:
    current = validate_manifest(manifest, task_id=task_id)
    ownership_payload = {key: value for key, value in current.items() if key != "last_observed_at"}
    encoded = json.dumps(ownership_payload, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    return {
        "generation": current["generation"],
        "baseline_head": current["baseline_head"],
        "manifest_digest": hashlib.sha256(encoded).hexdigest(),
        "baseline_external_paths": [entry["path"] for entry in current["baseline_external"]],
        "write_intent_paths": list(current["write_intents"]),
        "task_owned_paths": [entry["path"] for entry in current["task_owned"]],
        # Backward-compatible JSON alias for v0.0.3.63 development clients.
        "runner_owned_paths": [entry["path"] for entry in current["task_owned"]],
        "unexpected_nonoverlap_paths": [entry["path"] for entry in current["unexpected_nonoverlap"]],
        "conflicts": list(current["conflicts"]),
        "has_conflicts": bool(current["conflicts"]),
        "last_observed_at": current["last_observed_at"],
    }


__all__ = [
    "ContinuationWorkspaceError",
    "LEGACY_WORKSPACE_SCHEMA",
    "WORKSPACE_SCHEMA",
    "add_intents",
    "begin_generation",
    "classify",
    "git_snapshot",
    "handoff_generation",
    "new_manifest",
    "normalize_path",
    "observe_handoff",
    "path_matches_scope",
    "paths_overlap",
    "recover_generation",
    "summary",
    "validate_manifest",
]
