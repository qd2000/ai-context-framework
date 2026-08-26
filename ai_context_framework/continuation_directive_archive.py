"""Crash-safe terminal rollover and audit history for continuation directives.

The current ``directives.json`` journal remains the bounded actionable inbox.
Only complete terminal directive chains are eligible for rollover. Pending or
adopted directive chains remain entirely in the current journal, while
terminal chains can be removed even when their revisions are interleaved with
active authority. Archive-first/current-second writes deliberately tolerate an
exact duplicate window: history loading de-duplicates exact event identities,
so a crash between those two atomic writes loses no authority and converges on
the next mutation.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ai_context_framework import continuation_directives
from ai_context_framework.observability import atomic_write_text


ARCHIVE_SCHEMA = "acf.continuation.directive-archive.v1"
ARCHIVE_PATTERN = "directives.archive.*.json"
ROLLOVER_EVENT_RATIO = 0.75
ROLLOVER_BYTE_RATIO = 0.75
STALE_ADOPTED_HOURS = 24
STALE_HIGH_PRIORITY_PENDING_HOURS = 24
HIGH_PRIORITY_THRESHOLD = 80

_ARCHIVE_RE = re.compile(r"^directives\.archive\.(\d{6})\.json$")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
    )


def archive_paths(current_path: Path) -> list[Path]:
    paths = [
        path
        for path in current_path.parent.glob(ARCHIVE_PATTERN)
        if path.is_file() and _ARCHIVE_RE.match(path.name)
    ]
    return sorted(paths, key=lambda path: int(_ARCHIVE_RE.match(path.name).group(1)))  # type: ignore[union-attr]


def _event_digest(events: list[Mapping[str, Any]]) -> str:
    return hashlib.sha256(
        json.dumps(events, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validated_archive(path: Path, *, task_id: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise continuation_directives.DirectiveError(
            f"directive archive is unreadable: {path.name}", code="directive_archive_invalid"
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != ARCHIVE_SCHEMA:
        raise continuation_directives.DirectiveError(
            f"directive archive schema is invalid: {path.name}", code="directive_archive_invalid"
        )
    if payload.get("task_id") != task_id:
        raise continuation_directives.DirectiveError(
            f"directive archive task identity mismatch: {path.name}", code="directive_archive_invalid"
        )
    raw_events = payload.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise continuation_directives.DirectiveError(
            f"directive archive events are invalid: {path.name}", code="directive_archive_invalid"
        )
    events: list[dict[str, Any]] = []
    for raw in raw_events:
        if not isinstance(raw, Mapping):
            raise continuation_directives.DirectiveError(
                f"directive archive event is invalid: {path.name}", code="directive_archive_invalid"
            )
        revision = raw.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise continuation_directives.DirectiveError(
                f"directive archive revision is invalid: {path.name}", code="directive_archive_invalid"
            )
        events.append(continuation_directives._validate_event(raw, expected_revision=revision))
    events.sort(key=lambda item: int(item["revision"]))
    if payload.get("first_revision") != events[0]["revision"] or payload.get("last_revision") != events[-1]["revision"]:
        raise continuation_directives.DirectiveError(
            f"directive archive revision range is invalid: {path.name}", code="directive_archive_invalid"
        )
    if payload.get("event_digest") != _event_digest(events):
        raise continuation_directives.DirectiveError(
            f"directive archive digest mismatch: {path.name}", code="directive_archive_invalid"
        )
    return {**payload, "events": events}


def _archive_events(current_path: Path, *, task_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    paths: list[str] = []
    for path in archive_paths(current_path):
        archive = _validated_archive(path, task_id=task_id)
        events.extend(dict(item) for item in archive["events"])
        paths.append(str(path))
    return events, paths


def history_journal(
    current_path: Path,
    current: Mapping[str, Any],
    *,
    task_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current_journal = continuation_directives.validate_journal(current, task_id=task_id)
    archived, paths = _archive_events(current_path, task_id=task_id)
    by_event_id: dict[str, dict[str, Any]] = {}
    by_revision: dict[int, dict[str, Any]] = {}
    for raw in [*archived, *current_journal["events"]]:
        event = dict(raw)
        event_id = str(event["event_id"])
        revision = int(event["revision"])
        existing_id = by_event_id.get(event_id)
        if existing_id is not None and existing_id != event:
            raise continuation_directives.DirectiveError(
                f"directive archive/current event identity conflict: {event_id}",
                code="directive_archive_invalid",
            )
        existing_revision = by_revision.get(revision)
        if existing_revision is not None and existing_revision != event:
            raise continuation_directives.DirectiveError(
                f"directive archive/current revision conflict: {revision}",
                code="directive_archive_invalid",
            )
        by_event_id[event_id] = event
        by_revision[revision] = event
    revision = int(current_journal["revision"])
    expected = list(range(1, revision + 1))
    if sorted(by_revision) != expected:
        raise continuation_directives.DirectiveError(
            "directive archive/current history has a revision gap",
            code="directive_archive_invalid",
        )
    events = [by_revision[index] for index in expected]
    combined = {
        "schema_version": continuation_directives.DIRECTIVE_JOURNAL_SCHEMA,
        "task_id": task_id,
        "base_revision": 0,
        "revision": revision,
        "events": events,
    }
    audit_digest = _event_digest(events)
    return combined, {
        "archive_count": len(paths),
        "archive_paths": paths,
        "history_event_count": len(events),
        "history_revision": revision,
        "history_digest": audit_digest,
    }


def history_directives(
    current_path: Path,
    current: Mapping[str, Any],
    *,
    task_id: str,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    history, audit = history_journal(current_path, current, task_id=task_id)
    items = list(continuation_directives._project_events(history["events"]).values())
    if status is not None:
        normalized = status.strip().lower()
        if normalized not in continuation_directives.DIRECTIVE_STATUSES:
            raise continuation_directives.DirectiveError(f"unsupported directive status: {status}")
        items = [item for item in items if item["status"] == normalized]
    items.sort(
        key=lambda item: (
            0 if item["status"] == "pending" else 1,
            -int(item["priority"]),
            -int(item["last_revision"]),
        )
    )
    return items, audit


def show_history_directive(
    current_path: Path,
    current: Mapping[str, Any],
    *,
    task_id: str,
    directive_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = continuation_directives._directive_id(directive_id)
    items, audit = history_directives(current_path, current, task_id=task_id)
    for item in items:
        if item["id"] == normalized:
            return item, audit
    raise continuation_directives.DirectiveError(
        f"directive not found: {normalized}", code="directive_not_found"
    )


def _archivable_terminal_events(current: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return whole event chains for directives that are already terminal.

    Current journal revisions may become sparse after rollover. The global
    ``revision`` remains monotonic, while history reconstruction across current
    and archives proves that every revision is present exactly once (apart from
    the tolerated exact duplicate crash window).
    """

    projected = {
        str(item["id"]): item
        for item in continuation_directives.project_directives(current)
    }
    terminal_ids = {
        directive_id
        for directive_id, item in projected.items()
        if item["status"] in continuation_directives.TERMINAL_DIRECTIVE_STATUSES
    }
    return [
        dict(event)
        for event in current["events"]
        if str(event["directive_id"]) in terminal_ids
    ]


def _next_archive_index(current_path: Path) -> int:
    values = [int(_ARCHIVE_RE.match(path.name).group(1)) for path in archive_paths(current_path)]  # type: ignore[union-attr]
    return max(values, default=0) + 1


def store_with_rollover(
    current_path: Path,
    journal: Mapping[str, Any],
    *,
    task_id: str,
    force: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Persist one journal mutation and transparently roll a safe terminal prefix."""

    current = continuation_directives.validate_journal(journal, task_id=task_id)
    pressure = continuation_directives.journal_pressure(current)
    requested = force or pressure["event_ratio"] >= ROLLOVER_EVENT_RATIO or pressure["byte_ratio"] >= ROLLOVER_BYTE_RATIO
    if not requested:
        _write_json(current_path, current)
        _, audit = history_journal(current_path, current, task_id=task_id)
        return current, {"rolled_over": False, "pressure": pressure, **audit}

    archivable = _archivable_terminal_events(current)
    if not archivable:
        _write_json(current_path, current)
        _, audit = history_journal(current_path, current, task_id=task_id)
        return current, {
            "rolled_over": False,
            "blocked_by_active_authority": True,
            "pressure": pressure,
            **audit,
        }

    archived, _ = _archive_events(current_path, task_id=task_id)
    archived_ids = {str(item["event_id"]): dict(item) for item in archived}
    new_events: list[dict[str, Any]] = []
    for event in archivable:
        existing = archived_ids.get(str(event["event_id"]))
        if existing is None:
            new_events.append(event)
        elif existing != event:
            raise continuation_directives.DirectiveError(
                f"directive archive/current event identity conflict: {event['event_id']}",
                code="directive_archive_invalid",
            )

    archive_file: str | None = None
    if new_events:
        archive_path = current_path.parent / f"directives.archive.{_next_archive_index(current_path):06d}.json"
        archive_payload = {
            "schema_version": ARCHIVE_SCHEMA,
            "task_id": task_id,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "first_revision": int(new_events[0]["revision"]),
            "last_revision": int(new_events[-1]["revision"]),
            "event_count": len(new_events),
            "event_digest": _event_digest(new_events),
            "events": new_events,
        }
        # Archive first. If the process dies before current replacement, exact
        # duplicates are intentionally tolerated and de-duplicated on load.
        _write_json(archive_path, archive_payload)
        archive_file = str(archive_path)

    archived_event_ids = {str(event["event_id"]) for event in archivable}
    pruned = {
        "schema_version": continuation_directives.DIRECTIVE_JOURNAL_SCHEMA,
        "task_id": task_id,
        "revision": int(current["revision"]),
        "events": [
            dict(item)
            for item in current["events"]
            if str(item["event_id"]) not in archived_event_ids
        ],
    }
    pruned = continuation_directives.validate_journal(pruned, task_id=task_id)
    _write_json(current_path, pruned)
    _, audit = history_journal(current_path, pruned, task_id=task_id)
    return pruned, {
        "rolled_over": True,
        "archived_event_count": len(archivable),
        "archive_file_created": archive_file,
        "pressure": continuation_directives.journal_pressure(pruned),
        **audit,
    }


def hygiene_findings(
    current_path: Path,
    current: Mapping[str, Any],
    *,
    task_id: str,
    now: str,
) -> dict[str, Any]:
    journal = continuation_directives.validate_journal(current, task_id=task_id)
    projected = continuation_directives.project_directives(journal)
    now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
    findings: list[dict[str, Any]] = []
    for item in projected:
        timestamp = str(item.get("status_changed_at") or item["created_at"])
        age_hours = max(
            0.0,
            (now_dt - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))).total_seconds() / 3600.0,
        )
        if item["status"] == "adopted" and age_hours >= STALE_ADOPTED_HOURS:
            findings.append({
                "code": "stale_adopted",
                "directive_id": item["id"],
                "age_hours": round(age_hours, 2),
                "semantic_decision_required": True,
            })
        if (
            item["status"] == "pending"
            and int(item["priority"]) >= HIGH_PRIORITY_THRESHOLD
            and age_hours >= STALE_HIGH_PRIORITY_PENDING_HOURS
        ):
            findings.append({
                "code": "stale_high_priority_pending",
                "directive_id": item["id"],
                "age_hours": round(age_hours, 2),
                "priority": item["priority"],
                "semantic_decision_required": True,
            })
        if (
            item["status"] == "adopted"
            and item.get("lifetime") == "durable"
            and not item.get("adoption_evidence_refs")
        ):
            findings.append({
                "code": "durable_adoption_missing_evidence",
                "directive_id": item["id"],
                "semantic_decision_required": False,
            })
    pressure = continuation_directives.journal_pressure(journal)
    if pressure["active_ratio"] >= 0.75:
        findings.append({"code": "active_count_pressure", "ratio": pressure["active_ratio"]})
    if pressure["event_ratio"] >= ROLLOVER_EVENT_RATIO or pressure["byte_ratio"] >= ROLLOVER_BYTE_RATIO:
        findings.append({
            "code": "rollover_pressure",
            "event_ratio": pressure["event_ratio"],
            "byte_ratio": pressure["byte_ratio"],
            "archivable_terminal_events": len(_archivable_terminal_events(journal)),
        })
    _, audit = history_journal(current_path, journal, task_id=task_id)
    return {
        "finding_count": len(findings),
        "findings": findings,
        "pressure": pressure,
        "archive": audit,
        "auto_resolve": False,
        "semantic_completion_inferred": False,
    }


__all__ = [
    "ARCHIVE_PATTERN",
    "ARCHIVE_SCHEMA",
    "archive_paths",
    "history_journal",
    "history_directives",
    "hygiene_findings",
    "show_history_directive",
    "store_with_rollover",
]
