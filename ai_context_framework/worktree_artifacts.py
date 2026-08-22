"""Ignored/untracked artifact planning and verified migration for worktrees."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from ai_context_framework.git_support import (
    atomic_write_json,
    canonical_path,
    read_json_object,
    run_git,
    safe_file_key,
)
from ai_context_framework.worktree_merge_contracts import (
    ArtifactClassification,
    ArtifactEntryStatus,
    artifact_handoff_ready_for_promotion,
    build_artifact_handoff_v1,
    validate_artifact_handoff_v1,
)
from ai_context_framework.worktree_status import comparison_key, normalize_relative_path


def artifact_manifests_dir(common_dir: Path) -> Path:
    return common_dir / "acf" / "artifacts"


def artifact_manifest_path(common_dir: Path, target_key: str) -> Path:
    return artifact_manifests_dir(common_dir) / f"{safe_file_key(target_key)}.json"


def scan_source_artifacts(source: str | Path) -> list[dict[str, Any]]:
    root = canonical_path(source)
    untracked = _ls_files(root, ignored=False)
    ignored = _ls_files(root, ignored=True)
    rows: list[dict[str, Any]] = []
    for origin, paths in (("untracked", untracked), ("ignored", ignored)):
        for relative_path in paths:
            path = root / Path(relative_path)
            classification, status, transfer, rationale = _default_classification(relative_path)
            size = path.stat().st_size if path.is_file() else None
            digest = _sha256_file(path) if path.is_file() and size is not None else None
            rows.append(
                {
                    "relative_path": relative_path,
                    "origin": origin,
                    "classification": classification.value,
                    "status": status.value,
                    "transfer": transfer,
                    "destination": None,
                    "rationale": rationale,
                    "size": size,
                    "sha256": digest,
                }
            )
    rows.sort(key=lambda row: comparison_key(str(row["relative_path"])))
    return rows


def build_artifact_plan(
    *,
    target_key: str,
    source_head: str,
    source_path: str | Path,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
    cache_patterns: Iterable[str] = (),
    discardable_patterns: Iterable[str] = (),
) -> dict[str, Any]:
    entries = scan_source_artifacts(source_path)
    override_map = {
        comparison_key(normalize_relative_path(path)): dict(value)
        for path, value in (overrides or {}).items()
    }
    cache_pattern_list = tuple(normalize_relative_path(value) for value in cache_patterns)
    discardable_pattern_list = tuple(
        normalize_relative_path(value) for value in discardable_patterns
    )
    matched_override_keys: set[str] = set()
    for entry in entries:
        relative_path = str(entry["relative_path"])
        if _matches_patterns(relative_path, cache_pattern_list):
            _apply_override(
                entry,
                {
                    "classification": ArtifactClassification.REPRODUCIBLE_CACHE.value,
                    "status": ArtifactEntryStatus.ACKNOWLEDGED.value,
                    "transfer": "none",
                    "destination": None,
                    "rationale": "matched configured artifact_cache_patterns",
                },
            )
        if _matches_patterns(relative_path, discardable_pattern_list):
            _apply_override(
                entry,
                {
                    "classification": ArtifactClassification.DISCARDABLE.value,
                    "status": ArtifactEntryStatus.ACKNOWLEDGED.value,
                    "transfer": "none",
                    "destination": None,
                    "rationale": "matched configured artifact_discardable_patterns",
                },
            )
        key = comparison_key(relative_path)
        override = override_map.get(key)
        if override:
            _apply_override(entry, override)
            matched_override_keys.add(key)
    missing_overrides = sorted(set(override_map) - matched_override_keys)
    if missing_overrides:
        raise SystemExit(
            "artifact_override_path_not_found: " + ", ".join(missing_overrides)
        )
    payload = build_artifact_handoff_v1(
        target_key=target_key,
        source_head=source_head,
        entries=entries,
    )
    payload["source_path"] = str(canonical_path(source_path))
    payload["status"] = _manifest_status(payload)
    validate_artifact_handoff_v1(payload)
    return payload


def write_artifact_plan(common_dir: Path, payload: Mapping[str, Any]) -> Path:
    validate_artifact_handoff_v1(payload)
    path = artifact_manifest_path(common_dir, str(payload["target_key"]))
    atomic_write_json(path, payload)
    return path


def load_artifact_plan(common_dir: Path, target_key: str) -> dict[str, Any] | None:
    path = artifact_manifest_path(common_dir, target_key)
    if not path.is_file():
        return None
    payload = read_json_object(path, error_code="artifact_manifest_invalid")
    validate_artifact_handoff_v1(payload)
    return payload


def migrate_artifacts(
    common_dir: Path,
    payload: dict[str, Any],
    *,
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    validate_artifact_handoff_v1(payload)
    source = canonical_path(source_path or str(payload.get("source_path") or ""))
    if not source.is_dir():
        raise SystemExit(f"artifact_source_missing: {source}")

    results: list[dict[str, Any]] = []
    for entry in payload["entries"]:
        classification = ArtifactClassification(entry["classification"])
        if classification is ArtifactClassification.UNKNOWN:
            results.append({"path": entry["relative_path"], "status": "unclassified"})
            continue
        if classification in {
            ArtifactClassification.REPRODUCIBLE_CACHE,
            ArtifactClassification.DISCARDABLE,
        }:
            entry["status"] = ArtifactEntryStatus.ACKNOWLEDGED.value
            results.append({"path": entry["relative_path"], "status": "acknowledged"})
            continue
        source_file = source / Path(str(entry["relative_path"]))
        if not source_file.is_file():
            entry["status"] = ArtifactEntryStatus.FAILED.value
            results.append({"path": entry["relative_path"], "status": "source_missing"})
            continue
        expected_size = source_file.stat().st_size
        expected_digest = _sha256_file(source_file)
        entry["size"] = expected_size
        entry["sha256"] = expected_digest
        destination_raw = entry.get("destination")
        if not isinstance(destination_raw, str) or not destination_raw:
            entry["status"] = ArtifactEntryStatus.FAILED.value
            results.append({"path": entry["relative_path"], "status": "destination_missing"})
            continue
        destination = canonical_path(destination_raw)
        if classification is ArtifactClassification.RETAINED_REFERENCE:
            if destination.is_file() and _verified_file(destination, expected_size, expected_digest):
                entry["status"] = ArtifactEntryStatus.VERIFIED.value
                results.append({"path": entry["relative_path"], "status": "verified_reference"})
            else:
                entry["status"] = ArtifactEntryStatus.FAILED.value
                results.append({"path": entry["relative_path"], "status": "reference_mismatch"})
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file() and _verified_file(destination, expected_size, expected_digest):
            entry["status"] = ArtifactEntryStatus.VERIFIED.value
            results.append({"path": entry["relative_path"], "status": "already_verified"})
            continue
        temporary = _temporary_destination(destination)
        try:
            shutil.copy2(source_file, temporary)
            if not _verified_file(temporary, expected_size, expected_digest):
                raise OSError("copied artifact digest mismatch")
            os.replace(temporary, destination)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        if not _verified_file(destination, expected_size, expected_digest):
            entry["status"] = ArtifactEntryStatus.FAILED.value
            results.append({"path": entry["relative_path"], "status": "destination_verify_failed"})
            continue
        entry["status"] = ArtifactEntryStatus.VERIFIED.value
        results.append({"path": entry["relative_path"], "status": "verified"})

    payload["status"] = _manifest_status(payload)
    from ai_context_framework.worktree_merge_contracts import utc_now

    payload["updated_at"] = utc_now()
    write_artifact_plan(common_dir, payload)
    return {
        "status": payload["status"],
        "promotion_ready": artifact_handoff_ready_for_promotion(payload),
        "manifest_path": str(artifact_manifest_path(common_dir, str(payload["target_key"]))),
        "results": results,
        "manifest": payload,
    }


def parse_artifact_overrides(
    *,
    required: Iterable[str] = (),
    references: Iterable[str] = (),
    caches: Iterable[str] = (),
    discardable: Iterable[str] = (),
) -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = {}
    for value in required:
        path, destination = _split_path_destination(value, "required")
        overrides[path] = {
            "classification": ArtifactClassification.REQUIRED.value,
            "status": ArtifactEntryStatus.PLANNED.value,
            "transfer": "copy",
            "destination": destination,
            "rationale": "required artifact declared by merge operator",
        }
    for value in references:
        path, destination = _split_path_destination(value, "reference")
        overrides[path] = {
            "classification": ArtifactClassification.RETAINED_REFERENCE.value,
            "status": ArtifactEntryStatus.PLANNED.value,
            "transfer": "reference",
            "destination": destination,
            "rationale": "stable external reference declared by merge operator",
        }
    for path in caches:
        overrides[normalize_relative_path(path)] = {
            "classification": ArtifactClassification.REPRODUCIBLE_CACHE.value,
            "status": ArtifactEntryStatus.ACKNOWLEDGED.value,
            "transfer": "none",
            "destination": None,
            "rationale": "explicitly declared reproducible cache",
        }
    for path in discardable:
        overrides[normalize_relative_path(path)] = {
            "classification": ArtifactClassification.DISCARDABLE.value,
            "status": ArtifactEntryStatus.ACKNOWLEDGED.value,
            "transfer": "none",
            "destination": None,
            "rationale": "explicitly declared discardable output",
        }
    return overrides


def _ls_files(root: Path, *, ignored: bool) -> list[str]:
    args = ["ls-files", "--others", "--exclude-standard", "-z"]
    if ignored:
        args.insert(2, "--ignored")
    output = run_git(root, tuple(args)).stdout
    return sorted(
        {normalize_relative_path(value) for value in output.split("\0") if value},
        key=comparison_key,
    )


def _default_classification(
    relative_path: str,
) -> tuple[ArtifactClassification, ArtifactEntryStatus, str, str | None]:
    normalized = normalize_relative_path(relative_path)
    segments = tuple(part.casefold() for part in normalized.split("/") if part)
    if (
        (segments and segments[0] == ".venv")
        or "__pycache__" in segments
        or normalized.casefold().endswith((".pyc", ".pyo"))
        or any(part in {".pytest_cache", ".mypy_cache", ".ruff_cache"} for part in segments)
    ):
        return (
            ArtifactClassification.REPRODUCIBLE_CACHE,
            ArtifactEntryStatus.ACKNOWLEDGED,
            "none",
            "standard reproducible Python environment/cache artifact",
        )
    return (
        ArtifactClassification.UNKNOWN,
        ArtifactEntryStatus.UNCLASSIFIED,
        "none",
        None,
    )


def _matches_patterns(relative_path: str, patterns: Iterable[str]) -> bool:
    normalized = normalize_relative_path(relative_path)
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns)


def _apply_override(entry: dict[str, Any], override: Mapping[str, Any]) -> None:
    for key in ("classification", "status", "transfer", "destination", "rationale"):
        if key in override:
            entry[key] = override[key]


def _manifest_status(payload: Mapping[str, Any]) -> str:
    try:
        return "verified" if artifact_handoff_ready_for_promotion(payload) else "classification_or_migration_required"
    except ValueError:
        return "invalid"


def _split_path_destination(value: str, label: str) -> tuple[str, str]:
    if "=" not in value:
        raise SystemExit(f"artifact_{label}_invalid: expected RELATIVE_PATH=DESTINATION")
    path, destination = value.split("=", 1)
    path = normalize_relative_path(path.strip())
    destination = destination.strip()
    if not path or not destination:
        raise SystemExit(f"artifact_{label}_invalid: expected RELATIVE_PATH=DESTINATION")
    return path, destination


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _verified_file(path: Path, size: int, digest: str) -> bool:
    return path.is_file() and path.stat().st_size == size and _sha256_file(path) == digest


def _temporary_destination(destination: Path) -> Path:
    descriptor, raw = tempfile.mkstemp(
        prefix=f".{destination.name}.acf-partial-",
        dir=str(destination.parent),
    )
    os.close(descriptor)
    return Path(raw)
