"""Transparent terminal-effect rollover for long-running continuation tasks.

``effects.json`` remains the bounded current journal. Completed/failed records
may be moved into bounded archive segments when the current journal cannot
accept another effect. Full terminal records are retained so deterministic
logical-key replay protection is never lost.

Mutating helpers assume the caller already holds the continuation state lock.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from ai_context_framework import continuation_rounds
from ai_context_framework.observability import atomic_write_text


ARCHIVE_PATTERN = "effects.archive.*.json"
_ARCHIVE_RE = re.compile(r"^effects\.archive\.(\d{6})\.json$")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise continuation_rounds.ContinuationRoundError(
            f"effect archive is unreadable: {path.name}", code="effect_journal_invalid"
        ) from exc
    if not isinstance(value, dict):
        raise continuation_rounds.ContinuationRoundError(
            f"effect archive must be an object: {path.name}", code="effect_journal_invalid"
        )
    return value


def archive_paths(current_path: Path) -> list[Path]:
    paths = [
        path
        for path in current_path.parent.glob(ARCHIVE_PATTERN)
        if path.is_file() and _ARCHIVE_RE.match(path.name)
    ]
    return sorted(paths, key=lambda path: int(_ARCHIVE_RE.match(path.name).group(1)))  # type: ignore[union-attr]


def _load_archive(path: Path, *, task_id: str) -> dict[str, Any]:
    journal = continuation_rounds.validate_effect_journal(_read_json(path), task_id=task_id)
    if any(
        record["status"] not in continuation_rounds.TERMINAL_EFFECT_STATUSES
        for record in journal["effects"]
    ):
        raise continuation_rounds.ContinuationRoundError(
            f"effect archive contains unresolved records: {path.name}",
            code="effect_journal_invalid",
        )
    return journal


def _load_archives(current_path: Path, *, task_id: str) -> list[tuple[Path, dict[str, Any]]]:
    return [(path, _load_archive(path, task_id=task_id)) for path in archive_paths(current_path)]


def _history_records(
    current: Mapping[str, Any], archives: Iterable[tuple[Path, Mapping[str, Any]]]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for _, journal in archives:
        for raw in journal["effects"]:
            record = dict(raw)
            key = str(record["logical_key"])
            existing = by_key.get(key)
            if existing is not None:
                if existing != record:
                    raise continuation_rounds.ContinuationRoundError(
                        f"effect archive identity conflict: {key}", code="effect_identity_conflict"
                    )
                continue
            by_key[key] = record
            records.append(record)
    for raw in current["effects"]:
        record = dict(raw)
        key = str(record["logical_key"])
        existing = by_key.get(key)
        if existing is not None:
            if existing != record:
                raise continuation_rounds.ContinuationRoundError(
                    f"effect archive/current identity conflict: {key}",
                    code="effect_identity_conflict",
                )
            continue
        by_key[key] = record
        records.append(record)
    return records


def _summary(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    by_status = {status: 0 for status in sorted(continuation_rounds.EFFECT_STATUSES)}
    unresolved: list[str] = []
    terminal: list[str] = []
    total = 0
    for record in records:
        total += 1
        status = str(record["status"])
        by_status[status] += 1
        target = terminal if status in continuation_rounds.TERMINAL_EFFECT_STATUSES else unresolved
        target.append(str(record["logical_key"]))
    return {"total": total, "by_status": by_status, "unresolved": unresolved, "terminal": terminal}


def _existing_effect(
    records: Iterable[Mapping[str, Any]],
    *,
    logical_key: str,
    kind: str,
    external_id: str | None,
) -> dict[str, Any] | None:
    target = next((dict(item) for item in records if item["logical_key"] == logical_key), None)
    if target is None:
        return None
    if target["kind"] != kind:
        raise continuation_rounds.ContinuationRoundError(
            "logical effect key already exists with another kind", code="effect_identity_conflict"
        )
    if external_id is not None and target["external_id"] != external_id:
        raise continuation_rounds.ContinuationRoundError(
            "logical effect key already exists with another external id",
            code="effect_identity_conflict",
        )
    return target


def _next_archive_index(paths: Iterable[Path]) -> int:
    values = [int(_ARCHIVE_RE.match(path.name).group(1)) for path in paths]  # type: ignore[union-attr]
    return max(values, default=0) + 1


def _archive_chunks(records: Iterable[Mapping[str, Any]], *, task_id: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for raw in records:
        record = dict(raw)
        candidate = continuation_rounds.empty_effect_journal(task_id)
        candidate["effects"] = [*current, record]
        try:
            validated = continuation_rounds.validate_effect_journal(candidate, task_id=task_id)
        except continuation_rounds.ContinuationRoundError as exc:
            if exc.code not in {"effect_journal_invalid", "journal_full"} or not current:
                raise
            chunk = continuation_rounds.empty_effect_journal(task_id)
            chunk["effects"] = current
            chunks.append(continuation_rounds.validate_effect_journal(chunk, task_id=task_id))
            current = [record]
            single = continuation_rounds.empty_effect_journal(task_id)
            single["effects"] = current
            continuation_rounds.validate_effect_journal(single, task_id=task_id)
        else:
            current = list(validated["effects"])
    if current:
        chunk = continuation_rounds.empty_effect_journal(task_id)
        chunk["effects"] = current
        chunks.append(continuation_rounds.validate_effect_journal(chunk, task_id=task_id))
    return chunks


def list_history(
    current_path: Path, current: Mapping[str, Any], *, task_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    current_journal = continuation_rounds.validate_effect_journal(current, task_id=task_id)
    archives = _load_archives(current_path, task_id=task_id)
    records = _history_records(current_journal, archives)
    return records, _summary(records), [str(path) for path, _ in archives]


def validate_history(current_path: Path, current: Mapping[str, Any], *, task_id: str) -> None:
    current_journal = continuation_rounds.validate_effect_journal(current, task_id=task_id)
    _history_records(current_journal, _load_archives(current_path, task_id=task_id))


def prepare_with_rollover(
    current_path: Path,
    current: Mapping[str, Any],
    *,
    task_id: str,
    generation: int,
    logical_key: str,
    kind: str,
    external_id: str | None,
    milestone: str | None,
    evidence_refs: Iterable[str],
    now: str,
) -> tuple[dict[str, Any], dict[str, Any], bool, dict[str, Any], dict[str, Any]]:
    """Prepare an effect and roll terminal history only when capacity is exhausted."""

    current_journal = continuation_rounds.validate_effect_journal(current, task_id=task_id)
    archives = _load_archives(current_path, task_id=task_id)
    history = _history_records(current_journal, archives)
    existing = _existing_effect(
        history,
        logical_key=logical_key.strip(),
        kind=kind.strip(),
        external_id=external_id,
    )
    if existing is not None:
        return (
            current_journal,
            existing,
            False,
            _summary(history),
            {"rolled_over": False, "archive_files_created": []},
        )

    try:
        updated, effect, created = continuation_rounds.prepare_effect(
            current_journal,
            task_id=task_id,
            generation=generation,
            logical_key=logical_key,
            kind=kind,
            external_id=external_id,
            milestone=milestone,
            evidence_refs=evidence_refs,
            now=now,
        )
    except continuation_rounds.ContinuationRoundError as exc:
        if exc.code not in {"effect_journal_full", "journal_full"}:
            raise
    else:
        if created:
            _write_json(current_path, updated)
        records = _history_records(updated, archives)
        return (
            updated,
            effect,
            created,
            _summary(records),
            {"rolled_over": False, "archive_files_created": []},
        )

    terminal = [
        dict(record)
        for record in current_journal["effects"]
        if record["status"] in continuation_rounds.TERMINAL_EFFECT_STATUSES
    ]
    unresolved = [
        dict(record)
        for record in current_journal["effects"]
        if record["status"] not in continuation_rounds.TERMINAL_EFFECT_STATUSES
    ]
    if not terminal:
        raise continuation_rounds.ContinuationRoundError(
            "effect journal is full and contains no safely archivable terminal records",
            code="effect_journal_full",
        )

    archived_by_key = {
        str(record["logical_key"]): dict(record)
        for _, journal in archives
        for record in journal["effects"]
    }
    new_archive_records: list[dict[str, Any]] = []
    for record in terminal:
        existing_archived = archived_by_key.get(str(record["logical_key"]))
        if existing_archived is None:
            new_archive_records.append(record)
        elif existing_archived != record:
            raise continuation_rounds.ContinuationRoundError(
                f"effect archive/current identity conflict: {record['logical_key']}",
                code="effect_identity_conflict",
            )

    pruned = continuation_rounds.empty_effect_journal(task_id)
    pruned["effects"] = unresolved
    pruned = continuation_rounds.validate_effect_journal(pruned, task_id=task_id)
    try:
        updated, effect, created = continuation_rounds.prepare_effect(
            pruned,
            task_id=task_id,
            generation=generation,
            logical_key=logical_key,
            kind=kind,
            external_id=external_id,
            milestone=milestone,
            evidence_refs=evidence_refs,
            now=now,
        )
    except continuation_rounds.ContinuationRoundError as exc:
        if exc.code in {"effect_journal_full", "journal_full"}:
            raise continuation_rounds.ContinuationRoundError(
                "unresolved effects alone exhaust the effect journal capacity",
                code="effect_journal_full",
            ) from exc
        raise

    archive_files_created: list[str] = []
    if new_archive_records:
        chunks = _archive_chunks(new_archive_records, task_id=task_id)
        next_index = _next_archive_index(path for path, _ in archives)
        for offset, chunk in enumerate(chunks):
            archive_path = current_path.parent / f"effects.archive.{next_index + offset:06d}.json"
            _write_json(archive_path, chunk)
            archive_files_created.append(str(archive_path))
    _write_json(current_path, updated)

    archives = _load_archives(current_path, task_id=task_id)
    history = _history_records(updated, archives)
    return (
        updated,
        effect,
        created,
        _summary(history),
        {
            "rolled_over": True,
            "archived_terminal_count": len(terminal),
            "archive_files_created": archive_files_created,
        },
    )


def update_across_history(
    current_path: Path,
    current: Mapping[str, Any],
    *,
    task_id: str,
    generation: int,
    logical_key: str,
    status: str | None,
    external_id: str | None,
    milestone: str | None,
    evidence_refs: Iterable[str],
    now: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Update every exact duplicate location for one effect key.

    Duplicates are tolerated only for crash recovery when an archive write
    succeeded immediately before the current journal replacement. Updating all
    matching locations keeps that recovery state convergent.
    """

    current_journal = continuation_rounds.validate_effect_journal(current, task_id=task_id)
    archives = _load_archives(current_path, task_id=task_id)
    locations: list[tuple[Path | None, dict[str, Any]]] = []
    if any(record["logical_key"] == logical_key for record in current_journal["effects"]):
        locations.append((None, current_journal))
    for path, journal in archives:
        if any(record["logical_key"] == logical_key for record in journal["effects"]):
            locations.append((path, journal))
    if not locations:
        raise continuation_rounds.ContinuationRoundError(
            "effect key is not prepared", code="effect_missing"
        )

    updated_current = current_journal
    result: dict[str, Any] | None = None
    archive_updates: list[tuple[Path, dict[str, Any]]] = []
    for path, journal in locations:
        updated, effect = continuation_rounds.update_effect(
            journal,
            task_id=task_id,
            generation=generation,
            logical_key=logical_key,
            status=status,
            external_id=external_id,
            milestone=milestone,
            evidence_refs=evidence_refs,
            now=now,
        )
        result = effect
        if path is None:
            updated_current = updated
        else:
            archive_updates.append((path, updated))
    for path, updated in archive_updates:
        _write_json(path, updated)
    if any(path is None for path, _ in locations):
        _write_json(current_path, updated_current)
    assert result is not None
    archives = _load_archives(current_path, task_id=task_id)
    history = _history_records(updated_current, archives)
    return updated_current, result, _summary(history)


__all__ = [
    "ARCHIVE_PATTERN",
    "archive_paths",
    "list_history",
    "prepare_with_rollover",
    "update_across_history",
    "validate_history",
]
