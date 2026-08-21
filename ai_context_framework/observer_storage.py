"""Observer user-level storage, history, and lock primitives.

This module deliberately contains no Writer/control-plane operations.  It is
the narrow write side of Project Observer: all paths are rooted under the
resolved user-level Observer directory supplied by the caller.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_context_framework.observability import atomic_write_text


OBSERVER_HISTORY_INDEX_SCHEMA = "acf.observer.history-index.v1"
OBSERVER_LOCK_SCHEMA = "acf.observer.lock.v1"
OBSERVER_SEMANTIC_SCHEMA = "acf.observer.semantic.v1"
OBSERVER_INTERPRETATION_SCHEMA = "acf.observer.interpretation.v1"
OBSERVER_GLOSSARY_SCHEMA = "acf.observer.glossary.v1"
OBSERVER_LOCK_RECLAIM_GRACE_SECONDS = 60
OBSERVER_SEMANTIC_CONFIDENCE = {"authoritative", "high", "medium", "low"}
SEMANTIC_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(?:-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|"
    r"\b(?:api[_ -]?key|password|passwd|fence[_ -]?token|credential|access[_ -]?token|"
    r"refresh[_ -]?token|license[_ -]?key|private[_ -]?key)\b\s*[:=]\s*\S+|"
    r"\bsk-[A-Za-z0-9_-]{20,})"
)


class ObserverLockedError(RuntimeError):
    def __init__(self, path: Path, owner: dict[str, object] | None = None):
        self.path = path
        self.owner = owner or {}
        super().__init__(f"observer_locked: {path}")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def observer_paths(project: Any) -> dict[str, Path]:
    root = project.observer_dir
    return {
        "root": root,
        "current": root / "state" / "current.json",
        "timeline": root / "state" / "timeline.jsonl",
        "observations": root / "state" / "observations.jsonl",
        "alerts": root / "state" / "alerts.jsonl",
        "runs": root / "state" / "runs.jsonl",
        "status": root / "observer_status.json",
        "lock": root / "lock.json",
        "dashboard": root / "dashboard.html",
        "history": root / "history",
        "history_index": root / "history" / "index.json",
        "semantic": root / "semantic",
        "interpretations": root / "semantic" / "interpretations.jsonl",
        "glossary": root / "semantic" / "glossary.json",
        "workstreams": root / "workstreams",
    }


def semantic_workstream_path(project: Any, workstream_id: str) -> Path:
    return observer_paths(project)["workstreams"] / workstream_id / "current.json"


def _stable_digest(payload: object) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def semantic_source_projection(
    workstream: dict[str, object],
    continuations: list[dict[str, object]],
) -> dict[str, object]:
    """Return stable facts that an interpretation is allowed to explain.

    Volatile owner heartbeats are deliberately excluded.  Stage, status,
    next action, machine health class, and durable round milestone/evidence
    remain because changes to those facts can invalidate a human narrative.
    """

    workstream_id = str(workstream.get("id") or "")
    related: list[dict[str, object]] = []
    for row in continuations:
        if row.get("workstream_id") != workstream_id:
            continue
        latest = row.get("latest_round") if isinstance(row.get("latest_round"), dict) else {}
        related.append(
            {
                "task_id": row.get("task_id"),
                "stage": row.get("stage"),
                "status": row.get("status"),
                "next_action": row.get("next_action"),
                "objective": row.get("objective"),
                "round_phase": latest.get("phase"),
                "round_milestone": latest.get("milestone"),
                "round_evidence_refs": list(latest.get("evidence_refs") or []),
                "effect_status_counts": (row.get("effects") or {}).get("status_counts")
                if isinstance(row.get("effects"), dict)
                else {},
                "unresolved_effect_count": (row.get("effects") or {}).get("unresolved_count")
                if isinstance(row.get("effects"), dict)
                else 0,
            }
        )
    related.sort(key=lambda row: (str(row.get("task_id") or ""), str(row.get("stage") or "")))
    machine = workstream.get("machine_state") if isinstance(workstream.get("machine_state"), dict) else {}
    return {
        "workstream": {
            "id": workstream.get("id"),
            "title": workstream.get("title"),
            "status": workstream.get("status"),
            "attention": workstream.get("attention"),
            "goal": workstream.get("goal"),
            "source_consistency": workstream.get("source_consistency"),
            "execution": machine.get("execution"),
            "health": machine.get("health"),
            "health_reasons": list(machine.get("health_reasons") or []),
        },
        "continuations": related,
    }


def semantic_source_fingerprint(
    workstream: dict[str, object],
    continuations: list[dict[str, object]],
) -> str:
    return _stable_digest(semantic_source_projection(workstream, continuations))


def semantic_interpretation_status(
    project: Any,
    workstream: dict[str, object],
    continuations: list[dict[str, object]],
) -> dict[str, object]:
    workstream_id = str(workstream.get("id") or "")
    source_fingerprint = semantic_source_fingerprint(workstream, continuations)
    current = _read_json_object(semantic_workstream_path(project, workstream_id))
    if current is None:
        return {
            "schema_version": OBSERVER_SEMANTIC_SCHEMA,
            "status": "not_interpreted",
            "source_fingerprint": source_fingerprint,
            "interpretation_version": 0,
            "interpretation": None,
        }
    current_source = current.get("source_fingerprint")
    status = "current" if current_source == source_fingerprint else "stale"
    return {
        "schema_version": OBSERVER_SEMANTIC_SCHEMA,
        "status": status,
        "source_fingerprint": source_fingerprint,
        "interpretation_version": current.get("interpretation_version") or 0,
        "interpretation": current,
    }


def attach_semantic_interpretations(
    project: Any,
    workstreams: list[dict[str, object]],
    continuations: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    enriched: list[dict[str, object]] = []
    counts = {"current": 0, "stale": 0, "not_interpreted": 0}
    for workstream in workstreams:
        item = dict(workstream)
        semantic = semantic_interpretation_status(project, item, continuations)
        status = str(semantic.get("status") or "not_interpreted")
        counts[status] = counts.get(status, 0) + 1
        item["semantic"] = semantic
        enriched.append(item)
    overall = "current" if counts["current"] and not counts["stale"] and not counts["not_interpreted"] else "partial"
    if not workstreams:
        overall = "empty"
    elif counts["current"] == 0 and counts["stale"] == 0:
        overall = "not_interpreted"
    glossary = read_glossary(project)
    return enriched, {
        "schema_version": OBSERVER_SEMANTIC_SCHEMA,
        "status": overall,
        "workstream_counts": counts,
        "glossary_term_count": len(glossary.get("terms") or {}),
    }


class SemanticSourceMismatch(RuntimeError):
    def __init__(self, expected: str, current: str):
        self.expected = expected
        self.current = current
        super().__init__("observer_semantic_source_changed")


class SemanticSensitiveValueError(ValueError):
    pass


def _validate_semantic_text(value: str, field: str) -> str:
    cleaned = value.strip()
    if SEMANTIC_SENSITIVE_VALUE_RE.search(cleaned):
        raise SemanticSensitiveValueError(f"sensitive credential-like value refused in {field}")
    return cleaned


def _confidence_notice(confidence: str) -> str | None:
    if confidence == "low":
        return "暂译/当前理解"
    if confidence == "medium":
        return "当前理解"
    return None


def apply_semantic_interpretation(
    project: Any,
    *,
    workstream: dict[str, object],
    continuations: list[dict[str, object]],
    expected_source_fingerprint: str,
    human_title: str,
    current_focus: str,
    why_now: str,
    recent_proof: list[str],
    implication: str,
    next_step: str,
    confidence: str,
    provenance_refs: list[str],
) -> tuple[dict[str, object], bool]:
    """Persist one versioned human interpretation against an exact fact set."""

    confidence = confidence.strip().casefold()
    if confidence not in OBSERVER_SEMANTIC_CONFIDENCE:
        raise ValueError(f"invalid semantic confidence: {confidence}")
    source_fingerprint = semantic_source_fingerprint(workstream, continuations)
    if expected_source_fingerprint != source_fingerprint:
        raise SemanticSourceMismatch(expected_source_fingerprint, source_fingerprint)
    workstream_id = str(workstream.get("id") or "")
    if not workstream_id:
        raise ValueError("semantic interpretation requires a Workstream id")
    fields = {
        "human_title": _validate_semantic_text(human_title, "human_title"),
        "current_focus": _validate_semantic_text(current_focus, "current_focus"),
        "why_now": _validate_semantic_text(why_now, "why_now"),
        "recent_proof": [_validate_semantic_text(item, "recent_proof") for item in recent_proof if item.strip()],
        "implication": _validate_semantic_text(implication, "implication"),
        "next_step": _validate_semantic_text(next_step, "next_step"),
        "confidence": confidence,
        "confidence_notice": _confidence_notice(confidence),
        "provenance": [
            {"ref": _validate_semantic_text(item, "provenance")}
            for item in provenance_refs
            if item.strip()
        ],
    }
    for name in ("human_title", "current_focus", "why_now", "implication", "next_step"):
        if not fields[name]:
            raise ValueError(f"semantic interpretation requires {name}")
    if not fields["recent_proof"]:
        raise ValueError("semantic interpretation requires at least one recent_proof")
    if not fields["provenance"]:
        raise ValueError("semantic interpretation requires at least one provenance reference")
    current_path = semantic_workstream_path(project, workstream_id)
    previous = _read_json_object(current_path)
    comparable = {
        "source_fingerprint": source_fingerprint,
        "canonical_identity": {
            "type": "workstream",
            "id": workstream_id,
            "title": workstream.get("title"),
        },
        **fields,
    }
    previous_comparable = None
    if previous:
        previous_comparable = {
            key: previous.get(key)
            for key in comparable
        }
    if previous_comparable == comparable:
        return previous, False
    previous_version = int(previous.get("interpretation_version") or 0) if previous else 0
    interpreted_at = utc_now_iso()
    payload = {
        "schema_version": OBSERVER_INTERPRETATION_SCHEMA,
        "project_id": project.project_id,
        "workstream_id": workstream_id,
        "interpretation_version": previous_version + 1,
        "interpreted_at": interpreted_at,
        **comparable,
    }
    history_identity = {
        "workstream_id": workstream_id,
        "interpretation_version": payload["interpretation_version"],
        "source_fingerprint": source_fingerprint,
        "content": fields,
    }
    payload["interpretation_id"] = f"semantic-{_stable_digest(history_identity)[:20]}"
    payload["event_kind"] = "semantic_interpretation_updated"
    payload["previous_interpretation_id"] = previous.get("interpretation_id") if previous else None
    write_json_atomic(current_path, payload)
    append_jsonl_unique(observer_paths(project)["interpretations"], payload, id_field="interpretation_id")
    return payload, True


def read_glossary(project: Any) -> dict[str, object]:
    payload = _read_json_object(observer_paths(project)["glossary"])
    if payload is not None:
        return payload
    return {
        "schema_version": OBSERVER_GLOSSARY_SCHEMA,
        "project_id": project.project_id,
        "updated_at": None,
        "terms": {},
    }


def set_glossary_term(
    project: Any,
    *,
    term: str,
    human_term: str,
    explanation: str,
    confidence: str,
    provenance_refs: list[str],
) -> tuple[dict[str, object], bool]:
    confidence = confidence.strip().casefold()
    if confidence not in OBSERVER_SEMANTIC_CONFIDENCE:
        raise ValueError(f"invalid semantic confidence: {confidence}")
    term = _validate_semantic_text(term, "term")
    human_term = _validate_semantic_text(human_term, "human_term")
    explanation = _validate_semantic_text(explanation, "explanation")
    if not term or not human_term or not explanation:
        raise ValueError("glossary term, human term, and explanation are required")
    glossary = read_glossary(project)
    terms = dict(glossary.get("terms") or {})
    next_entry = {
        "canonical_term": term,
        "human_term": human_term,
        "explanation": explanation,
        "confidence": confidence,
        "confidence_notice": _confidence_notice(confidence),
        "provenance": [
            {"ref": _validate_semantic_text(item, "provenance")}
            for item in provenance_refs
            if item.strip()
        ],
    }
    if terms.get(term) == next_entry:
        return glossary, False
    terms[term] = next_entry
    payload = {
        "schema_version": OBSERVER_GLOSSARY_SCHEMA,
        "project_id": project.project_id,
        "updated_at": utc_now_iso(),
        "terms": dict(sorted(terms.items())),
    }
    write_json_atomic(observer_paths(project)["glossary"], payload)
    return payload, True


def _read_json_object(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_jsonl_objects(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    rows: list[dict[str, object]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        return []
    return rows


def _parse_utc_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _continuation_lease_liveness(
    lease: dict[str, object] | None,
    control: dict[str, object],
) -> dict[str, object]:
    if not lease:
        return {
            "state": "absent",
            "heartbeat_age_seconds": None,
            "expires_at": None,
            "stale_after_seconds": None,
        }
    now = datetime.now(timezone.utc)
    expires = _parse_utc_iso(lease.get("expires_at"))
    heartbeat = _parse_utc_iso(lease.get("last_heartbeat_at")) or _parse_utc_iso(lease.get("issued_at"))
    stale_after_minutes = control.get("stale_after_minutes")
    stale_after_seconds = (
        float(stale_after_minutes) * 60
        if isinstance(stale_after_minutes, (int, float)) and stale_after_minutes > 0
        else None
    )
    heartbeat_age = max(0.0, (now - heartbeat).total_seconds()) if heartbeat is not None else None
    if expires is not None and now >= expires:
        state = "expired"
    elif stale_after_seconds is not None and heartbeat_age is not None and heartbeat_age > stale_after_seconds:
        state = "stale"
    elif heartbeat is not None:
        state = "fresh"
    else:
        state = "unknown"
    return {
        "state": state,
        "heartbeat_age_seconds": round(heartbeat_age, 3) if heartbeat_age is not None else None,
        "expires_at": lease.get("expires_at"),
        "stale_after_seconds": stale_after_seconds,
    }


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    """Atomically append one JSONL record while preserving interrupted tails."""

    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing and not existing.endswith(("\n", "\r")):
        existing += "\n"
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    atomic_write_text(path, existing + line)


def ensure_jsonl_file(path: Path) -> None:
    if path.exists():
        return
    atomic_write_text(path, "")


def _jsonl_contains_id(path: Path, *, field: str, value: str) -> bool:
    if not path.is_file():
        return False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and payload.get(field) == value:
                    return True
    except OSError:
        return False
    return False


def append_jsonl_unique(path: Path, payload: dict[str, object], *, id_field: str) -> bool:
    raw_id = payload.get(id_field)
    if not isinstance(raw_id, str) or not raw_id:
        raise ValueError(f"{id_field} must be a non-empty string")
    if _jsonl_contains_id(path, field=id_field, value=raw_id):
        return False
    append_jsonl(path, payload)
    return True


def _record_month(payload: dict[str, object], timestamp_field: str) -> str | None:
    parsed = _parse_utc_iso(payload.get(timestamp_field))
    if parsed is None:
        return None
    return f"{parsed.year:04d}-{parsed.month:02d}"


def rotate_jsonl_monthly(
    path: Path,
    history_root: Path,
    *,
    stream_name: str,
    timestamp_field: str,
    id_field: str,
    current_month: str | None = None,
) -> list[dict[str, object]]:
    """Move completed-month JSONL records to lossless history shards."""

    if not path.is_file():
        return []
    current_month = current_month or utc_now_iso()[:7]
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return []
    retained: list[str] = []
    partitions: dict[str, list[dict[str, object]]] = {}
    for raw_line in raw_lines:
        normalized_line = raw_line if raw_line.endswith(("\n", "\r")) else raw_line + "\n"
        if not raw_line.strip():
            retained.append(normalized_line)
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            retained.append(normalized_line)
            continue
        if not isinstance(payload, dict):
            retained.append(normalized_line)
            continue
        month = _record_month(payload, timestamp_field)
        raw_id = payload.get(id_field)
        if month is None or month >= current_month or not isinstance(raw_id, str) or not raw_id:
            retained.append(normalized_line)
            continue
        partitions.setdefault(month, []).append(payload)

    if not partitions:
        return []

    rotations: list[dict[str, object]] = []
    for month, payloads in sorted(partitions.items()):
        shard_path = history_root / stream_name / f"{month}.jsonl"
        appended = 0
        for payload in payloads:
            if append_jsonl_unique(shard_path, payload, id_field=id_field):
                appended += 1
        rotations.append(
            {
                "stream": stream_name,
                "month": month,
                "shard_path": str(shard_path),
                "records_moved": len(payloads),
                "records_appended": appended,
            }
        )
    atomic_write_text(path, "".join(retained))
    return rotations


def refresh_history_index(project: Any) -> dict[str, object]:
    paths = observer_paths(project)
    history_root = paths["history"]
    shards: list[dict[str, object]] = []
    if history_root.is_dir():
        for shard_path in sorted(history_root.glob("*/*.jsonl")):
            rows = _read_jsonl_objects(shard_path)
            timestamps: list[str] = []
            for row in rows:
                for field in ("observed_at", "started_at", "finished_at"):
                    value = row.get(field)
                    if isinstance(value, str) and _parse_utc_iso(value) is not None:
                        timestamps.append(value)
                        break
            shards.append(
                {
                    "stream": shard_path.parent.name,
                    "month": shard_path.stem,
                    "path": shard_path.relative_to(project.observer_dir).as_posix(),
                    "record_count": len(rows),
                    "first_at": min(timestamps) if timestamps else None,
                    "last_at": max(timestamps) if timestamps else None,
                }
            )
    live_streams: list[dict[str, object]] = []
    for stream_name, path_key_name, timestamp_field in (
        ("timeline", "timeline", "observed_at"),
        ("observations", "observations", "observed_at"),
        ("alerts", "alerts", "observed_at"),
        ("runs", "runs", "started_at"),
        ("interpretations", "interpretations", "interpreted_at"),
    ):
        rows = _read_jsonl_objects(paths[path_key_name])
        timestamps = [
            str(row[timestamp_field])
            for row in rows
            if isinstance(row.get(timestamp_field), str) and _parse_utc_iso(row.get(timestamp_field)) is not None
        ]
        live_streams.append(
            {
                "stream": stream_name,
                "path": paths[path_key_name].relative_to(project.observer_dir).as_posix(),
                "record_count": len(rows),
                "first_at": min(timestamps) if timestamps else None,
                "last_at": max(timestamps) if timestamps else None,
            }
        )
    payload = {
        "schema_version": OBSERVER_HISTORY_INDEX_SCHEMA,
        "project_id": project.project_id,
        "generated_at": utc_now_iso(),
        "shard_count": len(shards),
        "record_count": sum(int(row["record_count"]) for row in shards),
        "live_record_count": sum(int(row["record_count"]) for row in live_streams),
        "total_record_count": sum(int(row["record_count"]) for row in shards + live_streams),
        "shards": shards,
        "live_streams": live_streams,
    }
    write_json_atomic(paths["history_index"], payload)
    return payload


def read_observer_history_stream(project: Any, stream_name: str) -> list[dict[str, object]]:
    """Reconstruct one complete logical stream from archived shards + live data."""

    paths = observer_paths(project)
    specs: dict[str, tuple[str, str, str]] = {
        "timeline": ("timeline", "event_id", "observed_at"),
        "observations": ("observations", "observation_id", "observed_at"),
        "alerts": ("alerts", "alert_event_id", "observed_at"),
        "runs": ("runs", "run_id", "started_at"),
        "interpretations": ("interpretations", "interpretation_id", "interpreted_at"),
    }
    if stream_name not in specs:
        raise ValueError(f"unknown observer history stream: {stream_name}")
    path_key_name, id_field, timestamp_field = specs[stream_name]
    candidates = sorted((paths["history"] / stream_name).glob("*.jsonl"))
    candidates.append(paths[path_key_name])
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for candidate in candidates:
        for row in _read_jsonl_objects(candidate):
            raw_id = row.get(id_field)
            if isinstance(raw_id, str) and raw_id:
                if raw_id in seen:
                    continue
                seen.add(raw_id)
            rows.append(row)

    minimum = datetime.min.replace(tzinfo=timezone.utc)
    rows.sort(
        key=lambda row: (
            _parse_utc_iso(row.get(timestamp_field)) or minimum,
            str(row.get(id_field) or ""),
        )
    )
    return rows


def rotate_observer_history(project: Any) -> list[dict[str, object]]:
    paths = observer_paths(project)
    stream_specs = (
        ("timeline", "timeline", "observed_at", "event_id"),
        ("observations", "observations", "observed_at", "observation_id"),
        ("alerts", "alerts", "observed_at", "alert_event_id"),
        ("runs", "runs", "started_at", "run_id"),
        ("interpretations", "interpretations", "interpreted_at", "interpretation_id"),
    )
    rotations: list[dict[str, object]] = []
    for path_key_name, stream_name, timestamp_field, id_field in stream_specs:
        rotations.extend(
            rotate_jsonl_monthly(
                paths[path_key_name],
                paths["history"],
                stream_name=stream_name,
                timestamp_field=timestamp_field,
                id_field=id_field,
            )
        )
    refresh_history_index(project)
    return rotations


def _process_is_alive(pid: object) -> bool | None:
    if not isinstance(pid, int) or pid <= 0:
        return None
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            process_query_limited_information = 0x1000
            still_active = 259
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
            if not handle:
                error = ctypes.get_last_error()
                if error in {87, 1168}:
                    return False
                if error == 5:
                    return None
                return False
            try:
                exit_code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return None
                return exit_code.value == still_active
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    except OSError:
        return None
    return True


def _lock_age_seconds(owner: dict[str, object] | None) -> float | None:
    if not owner:
        return None
    started = _parse_utc_iso(owner.get("started_at"))
    if started is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - started).total_seconds())


def _lock_is_confidently_abandoned(owner: dict[str, object] | None) -> bool:
    age = _lock_age_seconds(owner)
    if age is None or age < OBSERVER_LOCK_RECLAIM_GRACE_SECONDS:
        return False
    return _process_is_alive(owner.get("pid")) is False


def observer_lock_health(owner: dict[str, object] | None) -> dict[str, object]:
    """Classify an Observer lock without mutating or reclaiming it."""

    if owner is None:
        return {
            "state": "idle",
            "age_seconds": None,
            "process_alive": None,
            "reclaimable": False,
        }
    age = _lock_age_seconds(owner)
    alive = _process_is_alive(owner.get("pid"))
    reclaimable = bool(age is not None and age >= OBSERVER_LOCK_RECLAIM_GRACE_SECONDS and alive is False)
    if reclaimable:
        state = "abandoned"
    elif alive is True:
        state = "active"
    elif alive is None:
        state = "unknown"
    else:
        state = "grace"
    return {
        "state": state,
        "age_seconds": round(age, 3) if age is not None else None,
        "process_alive": alive,
        "reclaimable": reclaimable,
        "run_id": owner.get("run_id"),
        "pid": owner.get("pid"),
        "started_at": owner.get("started_at"),
    }


def acquire_observer_lock(project: Any, run_id: str) -> tuple[Path, dict[str, object] | None]:
    paths = observer_paths(project)
    lock_path = paths["lock"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": OBSERVER_LOCK_SCHEMA,
        "project_id": project.project_id,
        "run_id": run_id,
        "pid": os.getpid(),
        "started_at": utc_now_iso(),
    }
    recovered_owner: dict[str, object] | None = None
    for _attempt in range(2):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError as exc:
            owner = _read_json_object(lock_path)
            if not _lock_is_confidently_abandoned(owner):
                raise ObserverLockedError(lock_path, owner) from exc
            quarantine = lock_path.with_name(f".{lock_path.name}.abandoned-{run_id}")
            try:
                os.replace(lock_path, quarantine)
            except FileNotFoundError:
                continue
            except OSError as replace_exc:
                raise ObserverLockedError(lock_path, owner) from replace_exc
            recovered_owner = owner
            try:
                quarantine.unlink()
            except OSError:
                pass
    else:
        raise ObserverLockedError(lock_path, _read_json_object(lock_path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
    except Exception:
        try:
            lock_path.unlink()
        except OSError:
            pass
        raise
    return lock_path, recovered_owner


def release_observer_lock(lock_path: Path, run_id: str) -> None:
    current = _read_json_object(lock_path)
    if current is not None and current.get("run_id") != run_id:
        return
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return
