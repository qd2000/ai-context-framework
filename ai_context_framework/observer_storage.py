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
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

from ai_context_framework.observability import atomic_write_text
from ai_context_framework.observer_dashboard import (
    primary_visualization_kind_label,
    problem_dimension_label,
    render_primary_visualization,
    render_relation_diagram,
    render_target_execution_summary,
    render_target_run_history,
    run_source_label,
)
from ai_context_framework.observer_runtime_storage import (
    _continuation_lease_liveness,
    _parse_utc_iso,
    _read_json_object,
    _read_jsonl_objects,
    append_jsonl,
    append_jsonl_unique,
    ensure_jsonl_file,
    read_observer_history_stream,
    refresh_history_index,
    rotate_jsonl_monthly,
    rotate_observer_history,
    write_json_atomic,
)


OBSERVER_HISTORY_INDEX_SCHEMA = "acf.observer.history-index.v1"
OBSERVER_LOCK_SCHEMA = "acf.observer.lock.v1"
OBSERVER_SEMANTIC_SCHEMA = "acf.observer.semantic.v1"
OBSERVER_INTERPRETATION_SCHEMA = "acf.observer.interpretation.v1"
OBSERVER_GLOSSARY_SCHEMA = "acf.observer.glossary.v1"
OBSERVER_PROJECT_NARRATIVE_SCHEMA = "acf.observer.project-narrative.v1"
OBSERVER_PROJECT_NARRATIVE_EVENT_SCHEMA = "acf.observer.project-narrative-event.v1"
OBSERVER_DASHBOARD_SCHEMA = "acf.observer.dashboard.v1"
OBSERVER_DASHBOARD_TIMEZONE = timezone(timedelta(hours=8), name="UTC+08:00")
OBSERVER_LOCK_RECLAIM_GRACE_SECONDS = 60
OBSERVER_SEMANTIC_CONFIDENCE = {"authoritative", "high", "medium", "low"}
SEMANTIC_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(?:-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|"
    r"\b(?:api[_ -]?key|password|passwd|fence[_ -]?token|credential|access[_ -]?token|"
    r"refresh[_ -]?token|token|license(?:[_ -]?key)?|private[_ -]?key)\b\s*[:=]\s*\S+|"
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
        "project_narrative": root / "semantic" / "project_narrative.json",
        "project_narratives": root / "semantic" / "project_narratives.jsonl",
        "workstreams": root / "workstreams",
    }


def observer_status_payload(
    project: Any,
    *,
    acf_version: str,
    last_started: str | None,
    last_success: str | None,
    last_failure: str | None,
    last_duration_ms: int | None,
    last_run_id: str | None,
    last_run_status: str | None,
    worktrees_scanned: int,
    errors: list[str],
    data_age: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the persisted Observer self-health/status payload."""

    return {
        "schema_version": "acf.observer.status.v1",
        "project_id": project.project_id,
        "acf_version": acf_version,
        "last_started": last_started,
        "last_success": last_success,
        "last_failure": last_failure,
        "last_duration_ms": last_duration_ms,
        "last_run_id": last_run_id,
        "last_run_status": last_run_status,
        "worktrees_scanned": worktrees_scanned,
        "errors": errors,
        "data_age": data_age,
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

    Volatile owner heartbeats and terminal-effect accumulation are deliberately
    excluded.  Stage, status, next action, machine health class, durable
    ownership generation, unresolved effect risk, and round
    milestone/evidence remain because changes to those facts can invalidate a
    human narrative.
    """

    workstream_id = str(workstream.get("id") or "")
    related: list[dict[str, object]] = []
    for row in continuations:
        if row.get("workstream_id") != workstream_id:
            continue
        latest = row.get("latest_round") if isinstance(row.get("latest_round"), dict) else {}
        effects = row.get("effects") if isinstance(row.get("effects"), dict) else {}
        effect_counts = effects.get("status_counts") if isinstance(effects.get("status_counts"), dict) else {}
        related.append(
            {
                "task_id": row.get("task_id"),
                "stage": row.get("stage"),
                "status": row.get("status"),
                "next_action": row.get("next_action"),
                "objective": row.get("objective"),
                "round_generation": latest.get("generation"),
                "round_phase": latest.get("phase"),
                "round_milestone": latest.get("milestone"),
                "round_evidence_refs": list(latest.get("evidence_refs") or []),
                "effect_risk": {
                    "unresolved_count": int(effects.get("unresolved_count") or 0),
                    "prepared_count": int(effect_counts.get("prepared") or 0),
                    "active_count": int(effect_counts.get("active") or 0),
                    "unknown_count": int(effect_counts.get("unknown") or 0),
                },
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


_PROJECT_NARRATIVE_STATUSES = {
    "completed",
    "current",
    "active",
    "maintenance",
    "waiting",
    "warning",
    "critical",
    "blocked",
    "planned",
    "future",
    "unknown",
}


class ProjectNarrativeSourceMismatch(RuntimeError):
    def __init__(self, expected: str, current: str):
        self.expected = expected
        self.current = current
        super().__init__("observer_project_narrative_source_changed")


def _project_narrative_source_file(project: Any, raw_path: str) -> dict[str, object]:
    text = raw_path.strip()
    if not text:
        raise ValueError("project narrative source path is required")
    source = Path(text)
    if source.is_absolute() or ".." in source.parts:
        raise ValueError(f"project narrative source path must be project-relative: {text}")
    relative = Path(*source.parts)
    candidates = [
        (Path(project.invocation_root).resolve() / relative).resolve(),
        (Path(project.canonical_root).resolve() / relative).resolve(),
    ]
    selected: Path | None = None
    for candidate in candidates:
        root = Path(project.invocation_root).resolve() if candidate == candidates[0] else Path(project.canonical_root).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file():
            selected = candidate
            break
    if selected is None:
        raise ValueError(f"project narrative source file does not exist: {relative.as_posix()}")
    import hashlib

    data = selected.read_bytes()
    return {
        "path": relative.as_posix(),
        "content_digest": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def project_narrative_source_projection(
    project: Any,
    workstreams: list[dict[str, object]],
    continuations: list[dict[str, object]],
    source_paths: list[str],
) -> dict[str, object]:
    normalized_sources = [_project_narrative_source_file(project, item) for item in source_paths]
    unique_sources = {
        str(item["path"]): item
        for item in normalized_sources
    }
    workstream_rows: list[dict[str, object]] = []
    for row in workstreams:
        registry = row.get("registry") if isinstance(row.get("registry"), dict) else {}
        machine = row.get("machine_state") if isinstance(row.get("machine_state"), dict) else {}
        workstream_rows.append(
            {
                "id": row.get("id"),
                "title": row.get("title"),
                "status": row.get("status"),
                "attention": row.get("attention"),
                "goal": row.get("goal"),
                "source_consistency": row.get("source_consistency"),
                "registry_state": registry.get("state"),
                "execution": machine.get("execution"),
                "health": machine.get("health"),
            }
        )
    workstream_rows.sort(key=lambda row: str(row.get("id") or ""))
    continuation_rows: list[dict[str, object]] = []
    for row in continuations:
        effects = row.get("effects") if isinstance(row.get("effects"), dict) else {}
        continuation_rows.append(
            {
                "task_id": row.get("task_id"),
                "workstream_id": row.get("workstream_id"),
                "stage": row.get("stage"),
                "status": row.get("status"),
                "objective": row.get("objective"),
                "next_action": row.get("next_action"),
                "unresolved_effect_count": int(effects.get("unresolved_count") or 0),
            }
        )
    continuation_rows.sort(key=lambda row: (str(row.get("workstream_id") or ""), str(row.get("task_id") or "")))
    return {
        "project_id": project.project_id,
        "sources": [unique_sources[key] for key in sorted(unique_sources)],
        "workstreams": workstream_rows,
        "continuations": continuation_rows,
    }


def project_narrative_source_fingerprint(
    project: Any,
    workstreams: list[dict[str, object]],
    continuations: list[dict[str, object]],
    source_paths: list[str],
) -> str:
    return _stable_digest(
        project_narrative_source_projection(project, workstreams, continuations, source_paths)
    )


def project_narrative_status(
    project: Any,
    workstreams: list[dict[str, object]],
    continuations: list[dict[str, object]],
) -> dict[str, object]:
    current = _read_json_object(observer_paths(project)["project_narrative"])
    if current is None:
        return {
            "schema_version": OBSERVER_PROJECT_NARRATIVE_SCHEMA,
            "status": "not_interpreted",
            "source_fingerprint": None,
            "narrative_version": 0,
            "narrative": None,
        }
    source_paths = [str(item) for item in current.get("source_paths") or [] if str(item).strip()]
    try:
        source_fingerprint = project_narrative_source_fingerprint(
            project,
            workstreams,
            continuations,
            source_paths,
        )
        status = "current" if current.get("source_fingerprint") == source_fingerprint else "stale"
        source_error = None
    except (OSError, ValueError) as exc:
        source_fingerprint = None
        status = "stale"
        source_error = str(exc)
    return {
        "schema_version": OBSERVER_PROJECT_NARRATIVE_SCHEMA,
        "status": status,
        "source_fingerprint": source_fingerprint,
        "narrative_version": current.get("narrative_version") or 0,
        "source_error": source_error,
        "narrative": current,
    }


def _narrative_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"project narrative {field} must be text")
    cleaned = _validate_semantic_text(value, field)
    if not cleaned:
        raise ValueError(f"project narrative {field} is required")
    return cleaned


def _narrative_refs(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"project narrative {field} must be a list")
    refs = [_narrative_text(item, field) for item in value]
    if not refs:
        raise ValueError(f"project narrative {field} requires at least one reference")
    return list(dict.fromkeys(refs))


def _narrative_status(value: object, field: str) -> str:
    status = _narrative_text(value, field).casefold()
    if status not in _PROJECT_NARRATIVE_STATUSES:
        raise ValueError(f"unsupported project narrative status for {field}: {status}")
    return status


def validate_project_narrative_payload(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("project narrative input must be a JSON object")
    confidence = _narrative_text(value.get("confidence"), "confidence").casefold()
    if confidence not in OBSERVER_SEMANTIC_CONFIDENCE:
        raise ValueError(f"invalid project narrative confidence: {confidence}")
    overall = value.get("overall_goal")
    if not isinstance(overall, dict):
        raise ValueError("project narrative overall_goal must be an object")
    overall_goal = {
        "summary": _narrative_text(overall.get("summary"), "overall_goal.summary"),
        "provenance": _narrative_refs(overall.get("provenance"), "overall_goal.provenance"),
    }
    architecture = value.get("architecture")
    if not isinstance(architecture, dict):
        raise ValueError("project narrative architecture must be an object")
    raw_nodes = architecture.get("nodes")
    raw_edges = architecture.get("edges")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("project narrative architecture.nodes requires at least one node")
    if not isinstance(raw_edges, list):
        raise ValueError("project narrative architecture.edges must be a list")
    nodes: list[dict[str, object]] = []
    node_ids: set[str] = set()
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            raise ValueError(f"project narrative architecture.nodes[{index}] must be an object")
        node_id = _narrative_text(raw.get("id"), f"architecture.nodes[{index}].id")
        if node_id in node_ids:
            raise ValueError(f"duplicate project narrative architecture node id: {node_id}")
        node_ids.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "title": _narrative_text(raw.get("title"), f"architecture.nodes[{index}].title"),
                "category": _narrative_text(raw.get("category"), f"architecture.nodes[{index}].category"),
                "status": _narrative_status(raw.get("status"), f"architecture.nodes[{index}].status"),
                "summary": _narrative_text(raw.get("summary"), f"architecture.nodes[{index}].summary"),
                "provenance": _narrative_refs(raw.get("provenance"), f"architecture.nodes[{index}].provenance"),
            }
        )
    edges: list[dict[str, object]] = []
    for index, raw in enumerate(raw_edges):
        if not isinstance(raw, dict):
            raise ValueError(f"project narrative architecture.edges[{index}] must be an object")
        source_id = _narrative_text(raw.get("from"), f"architecture.edges[{index}].from")
        target_id = _narrative_text(raw.get("to"), f"architecture.edges[{index}].to")
        if source_id not in node_ids or target_id not in node_ids:
            raise ValueError(f"project narrative architecture edge references unknown node: {source_id}->{target_id}")
        edges.append(
            {
                "from": source_id,
                "to": target_id,
                "relation": _narrative_text(raw.get("relation"), f"architecture.edges[{index}].relation"),
                "summary": _narrative_text(raw.get("summary"), f"architecture.edges[{index}].summary"),
                "provenance": _narrative_refs(raw.get("provenance"), f"architecture.edges[{index}].provenance"),
            }
        )
    raw_milestones = value.get("milestones")
    if not isinstance(raw_milestones, list) or not raw_milestones:
        raise ValueError("project narrative milestones requires at least one milestone")
    milestone_ids: set[str] = set()
    for index, raw in enumerate(raw_milestones):
        if not isinstance(raw, dict):
            raise ValueError(f"project narrative milestones[{index}] must be an object")
        milestone_id = _narrative_text(raw.get("id"), f"milestones[{index}].id")
        if milestone_id in milestone_ids:
            raise ValueError(f"duplicate project narrative milestone id: {milestone_id}")
        milestone_ids.add(milestone_id)
    milestones: list[dict[str, object]] = []
    for index, raw in enumerate(raw_milestones):
        milestone_id = str(raw.get("id"))
        depends_on = [_narrative_text(item, f"milestones[{index}].depends_on") for item in raw.get("depends_on") or []]
        next_ids = [_narrative_text(item, f"milestones[{index}].next") for item in raw.get("next") or []]
        unknown = [item for item in depends_on + next_ids if item not in milestone_ids]
        if unknown:
            raise ValueError(f"project narrative milestone {milestone_id} references unknown milestone: {unknown[0]}")
        milestones.append(
            {
                "id": milestone_id,
                "title": _narrative_text(raw.get("title"), f"milestones[{index}].title"),
                "status": _narrative_status(raw.get("status"), f"milestones[{index}].status"),
                "depends_on": list(dict.fromkeys(depends_on)),
                "next": list(dict.fromkeys(next_ids)),
                "summary": _narrative_text(raw.get("summary"), f"milestones[{index}].summary"),
                "implication": _narrative_text(raw.get("implication"), f"milestones[{index}].implication"),
                "evidence": _narrative_refs(raw.get("evidence"), f"milestones[{index}].evidence"),
                "provenance": _narrative_refs(raw.get("provenance"), f"milestones[{index}].provenance"),
            }
        )
    current = value.get("current_position")
    if not isinstance(current, dict):
        raise ValueError("project narrative current_position must be an object")
    current_milestone = _narrative_text(current.get("milestone_id"), "current_position.milestone_id")
    if current_milestone not in milestone_ids:
        raise ValueError(f"project narrative current_position references unknown milestone: {current_milestone}")
    current_position = {
        "milestone_id": current_milestone,
        "summary": _narrative_text(current.get("summary"), "current_position.summary"),
        "next_logic": _narrative_text(current.get("next_logic"), "current_position.next_logic"),
        "provenance": _narrative_refs(current.get("provenance"), "current_position.provenance"),
    }
    return {
        "confidence": confidence,
        "confidence_notice": _confidence_notice(confidence),
        "overall_goal": overall_goal,
        "architecture": {"nodes": nodes, "edges": edges},
        "milestones": milestones,
        "current_position": current_position,
        "provenance": _narrative_refs(value.get("provenance"), "provenance"),
    }


def apply_project_narrative(
    project: Any,
    *,
    workstreams: list[dict[str, object]],
    continuations: list[dict[str, object]],
    expected_source_fingerprint: str,
    source_paths: list[str],
    narrative: object,
) -> tuple[dict[str, object], bool]:
    validated = validate_project_narrative_payload(narrative)
    projection = project_narrative_source_projection(project, workstreams, continuations, source_paths)
    source_fingerprint = _stable_digest(projection)
    if source_fingerprint != expected_source_fingerprint:
        raise ProjectNarrativeSourceMismatch(expected_source_fingerprint, source_fingerprint)
    normalized_paths = [str(row.get("path")) for row in projection.get("sources") or [] if isinstance(row, dict)]
    comparable = {
        "source_fingerprint": source_fingerprint,
        "source_paths": normalized_paths,
        **validated,
    }
    current_path = observer_paths(project)["project_narrative"]
    previous = _read_json_object(current_path)
    if previous is not None and {key: previous.get(key) for key in comparable} == comparable:
        return previous, False
    previous_version = int(previous.get("narrative_version") or 0) if previous else 0
    interpreted_at = utc_now_iso()
    payload = {
        "schema_version": OBSERVER_PROJECT_NARRATIVE_EVENT_SCHEMA,
        "project_id": project.project_id,
        "narrative_version": previous_version + 1,
        "interpreted_at": interpreted_at,
        **comparable,
    }
    identity = {
        "project_id": project.project_id,
        "narrative_version": payload["narrative_version"],
        "source_fingerprint": source_fingerprint,
        "content": validated,
    }
    payload["narrative_id"] = f"project-narrative-{_stable_digest(identity)[:20]}"
    payload["event_kind"] = "project_narrative_updated"
    payload["previous_narrative_id"] = previous.get("narrative_id") if previous else None
    write_json_atomic(current_path, payload)
    append_jsonl_unique(observer_paths(project)["project_narratives"], payload, id_field="narrative_id")
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


_DASHBOARD_SECRET_KEYS = {
    "fence_token",
    "fence_token_hash",
    "lease_id",
    "password",
    "passwd",
    "api_key",
    "access_token",
    "refresh_token",
    "token",
    "private_key",
    "credential",
    "credentials",
    "license_key",
    "license",
}


def sanitize_observer_payload(value: object) -> object:
    """Remove credential-like material before persisting or rendering Observer data."""

    if isinstance(value, dict):
        cleaned: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            normalized = key.casefold().replace("-", "_").replace(" ", "_")
            if normalized in _DASHBOARD_SECRET_KEYS or "secret" in normalized:
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = sanitize_observer_payload(raw_value)
        return cleaned
    if isinstance(value, list):
        return [sanitize_observer_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_observer_payload(item) for item in value]
    if isinstance(value, str) and SEMANTIC_SENSITIVE_VALUE_RE.search(value):
        return "[redacted]"
    return value


# Backward-compatible local alias for renderer call sites.  Observer state and
# HTML now share one sanitization contract so secrets cannot enter structured
# runtime state and later leak through another presentation layer.
sanitize_dashboard_payload = sanitize_observer_payload


def _html_text(value: object, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return escape(str(value), quote=True)


def _dashboard_display_time(value: object) -> str:
    """Render canonical UTC timestamps as Beijing time for human-facing HTML.

    Observer runtime state and history remain UTC. This conversion is only a
    presentation concern so ordering, dedupe, fingerprints, and cross-machine
    evidence continue to use one canonical time basis.
    """

    parsed = _parse_utc_iso(value)
    if parsed is None:
        return str(value or "—")
    local = parsed.astimezone(OBSERVER_DASHBOARD_TIMEZONE)
    return f"{local.strftime('%Y-%m-%d %H:%M:%S')} 北京时间 (UTC+08:00)"


def _health_rank(value: object) -> int:
    return {"critical": 3, "warning": 2, "healthy": 1}.get(str(value or "").casefold(), 0)


def _overall_health(current: dict[str, object], self_health_alerts: list[dict[str, object]]) -> str:
    candidates: list[str] = []
    for alert in list(current.get("alerts") or []) + self_health_alerts:
        if isinstance(alert, dict):
            severity = str(alert.get("severity") or "")
            if severity == "critical":
                candidates.append("critical")
            elif severity == "warning":
                candidates.append("warning")
    for workstream in current.get("workstreams") or []:
        if not isinstance(workstream, dict):
            continue
        machine = workstream.get("machine_state") if isinstance(workstream.get("machine_state"), dict) else {}
        candidates.append(str(machine.get("health") or ""))
    return max(candidates, key=_health_rank, default="healthy")


def _state_badge(kind: str, value: object) -> str:
    raw = str(value or "unknown")
    normalized = raw.casefold()
    if kind == "health":
        tone = normalized if normalized in {"healthy", "warning", "critical"} else "muted"
    elif kind == "execution":
        tone = "active" if normalized in {"running", "active"} else "warning" if "wait" in normalized else "muted"
    elif kind == "progress":
        tone = "healthy" if normalized == "advancing" else "warning" if normalized in {"slow", "regressing"} else "muted"
    else:
        tone = "muted"
    labels = {
        "healthy": "健康",
        "warning": "关注",
        "critical": "严重",
        "running": "运行中",
        "waiting_external": "等待外部结果",
        "idle": "空闲",
        "blocked": "阻塞",
        "done": "完成",
        "advancing": "推进中",
        "unchanged": "无新增",
        "slow": "推进较慢",
        "regressing": "回退",
        "unknown": "尚未判定",
    }
    icon = {"critical": "●", "warning": "▲", "healthy": "●", "active": "●", "muted": "○"}[tone]
    label = labels.get(normalized, raw)
    return f'<span class="badge tone-{tone}"><span aria-hidden="true">{icon}</span> {_html_text(label)}</span>'


def _dashboard_alert_html(alert: dict[str, object]) -> str:
    severity = str(alert.get("severity") or "info").casefold()
    severity_label = {"critical": "严重", "warning": "需要关注", "info": "提示"}.get(severity, severity)
    tone = severity if severity in {"critical", "warning"} else "active"
    icon = "●" if severity == "critical" else "▲" if severity == "warning" else "●"
    title = _html_text(alert.get("title") or alert.get("alert_key") or "Observer 提示")
    explanation = _html_text(alert.get("explanation"))
    return (
        f'<article class="alert tone-border-{tone}" data-health="{escape(tone)}">'
        f'<div class="alert-title"><span class="tone-text-{tone}" aria-hidden="true">{icon}</span> {title}</div>'
        f'<div class="muted">{_html_text(severity_label)}</div>'
        f'<p>{explanation}</p>'
        "</article>"
    )


def _continuation_for_workstream(current: dict[str, object], workstream_id: str) -> dict[str, object] | None:
    for row in current.get("continuations") or []:
        if isinstance(row, dict) and row.get("workstream_id") == workstream_id:
            return row
    return None


def _worktree_for_workstream(current: dict[str, object], workstream: dict[str, object]) -> dict[str, object] | None:
    selected = workstream.get("selected_source")
    for row in current.get("worktrees") or []:
        if isinstance(row, dict) and row.get("path") == selected:
            return row
    registry = workstream.get("registry") if isinstance(workstream.get("registry"), dict) else {}
    registry_path = registry.get("path")
    for row in current.get("worktrees") or []:
        if isinstance(row, dict) and row.get("path") == registry_path:
            return row
    return None


def _workstream_card_html(current: dict[str, object], row: dict[str, object]) -> str:
    workstream_id = str(row.get("id") or "unknown")
    machine = row.get("machine_state") if isinstance(row.get("machine_state"), dict) else {}
    semantic = row.get("semantic") if isinstance(row.get("semantic"), dict) else {}
    semantic_status = str(semantic.get("status") or "not_interpreted")
    interpretation = semantic.get("interpretation") if isinstance(semantic.get("interpretation"), dict) else {}
    usable_semantic = semantic_status == "current" and bool(interpretation)
    human_title = interpretation.get("human_title") if usable_semantic else row.get("title")
    confidence = interpretation.get("confidence") if usable_semantic else None
    confidence_notice = interpretation.get("confidence_notice") if usable_semantic else None
    search_parts = [
        workstream_id,
        str(row.get("title") or ""),
        str(human_title or ""),
        str(row.get("goal") or ""),
        str(interpretation.get("current_focus") or ""),
        str(interpretation.get("why_now") or ""),
        str(interpretation.get("next_step") or ""),
    ]
    continuation = _continuation_for_workstream(current, workstream_id) or {}
    worktree = _worktree_for_workstream(current, row) or {}
    related_proof = interpretation.get("recent_proof") if usable_semantic else []
    proof_html = "".join(f"<li>{_html_text(item)}</li>" for item in (related_proof or []))
    if not proof_html:
        proof_html = "<li class=\"muted\">当前尚无已确认的人类语义进展解释。</li>"
    semantic_notice = ""
    if semantic_status == "stale":
        semantic_notice = '<div class="semantic-notice tone-border-warning"><strong>▲ 语义解释已陈旧</strong>：底层项目事实已变化，以下主视图不会继续把旧解释当作当前事实。</div>'
    elif semantic_status != "current":
        semantic_notice = '<div class="semantic-notice"><strong>○ 尚未生成当前语义解释</strong>：暂时仅展示机器事实与 canonical identity。</div>'
    elif confidence_notice:
        semantic_notice = f'<div class="semantic-notice tone-border-warning"><strong>▲ {_html_text(confidence_notice)}</strong>：该解释置信度为 {_html_text(confidence)}，请同时核对 canonical identity 与 provenance。</div>'
    current_focus = interpretation.get("current_focus") if usable_semantic else continuation.get("next_action") or row.get("goal")
    why_now = interpretation.get("why_now") if usable_semantic else "当前语义解释尚未与最新事实绑定；请以机器状态和项目计划为准。"
    implication = interpretation.get("implication") if usable_semantic else "Observer 不会从缺失解释中推造项目结论。"
    next_step = interpretation.get("next_step") if usable_semantic else continuation.get("next_action") or "等待项目事实提供明确下一步。"
    provenance = interpretation.get("provenance") if usable_semantic else []
    provenance_html = "".join(
        f"<li><code>{_html_text(item.get('ref'))}</code></li>" for item in provenance if isinstance(item, dict)
    ) or "<li class=\"muted\">暂无语义 provenance。</li>"
    source_fingerprint = semantic.get("source_fingerprint")
    lease = continuation.get("lease") if isinstance(continuation.get("lease"), dict) else {}
    liveness = lease.get("liveness") if isinstance(lease.get("liveness"), dict) else {}
    effects = continuation.get("effects") if isinstance(continuation.get("effects"), dict) else {}
    search_value = escape(" ".join(search_parts).casefold(), quote=True)
    health_value = escape(str(machine.get("health") or "unknown").casefold(), quote=True)
    return f"""
<article class="workstream-card" data-search="{search_value}" data-health="{health_value}">
  <header class="card-header">
    <div>
      <h3>{_html_text(human_title)}</h3>
      <div class="canonical"><code>{_html_text(workstream_id)}</code> · 原始名称：{_html_text(row.get('title'))}</div>
    </div>
    <div class="badge-row">{_state_badge('execution', machine.get('execution'))}{_state_badge('progress', machine.get('progress'))}{_state_badge('health', machine.get('health'))}</div>
  </header>
  {semantic_notice}
  <div class="logic-grid">
    <section><h4>当前在解决什么</h4><p>{_html_text(current_focus)}</p></section>
    <section><h4>为什么现在做</h4><p>{_html_text(why_now)}</p></section>
    <section><h4>最近证明 / 排除 / 改变</h4><ul>{proof_html}</ul></section>
    <section><h4>这些结果意味着什么</h4><p>{_html_text(implication)}</p></section>
    <section class="span-two"><h4>下一步为什么这样走</h4><p>{_html_text(next_step)}</p></section>
  </div>
  <details>
    <summary>技术详情与 provenance</summary>
    <div class="technical-grid">
      <div><span class="muted">Canonical status</span><br><code>{_html_text(row.get('status'))}</code></div>
      <div><span class="muted">Branch / HEAD</span><br><code>{_html_text(worktree.get('branch'))}</code><br><code>{_html_text(worktree.get('head'))}</code></div>
      <div><span class="muted">Continuation stage</span><br><code>{_html_text(continuation.get('stage'))}</code></div>
      <div><span class="muted">Owner liveness</span><br><code>{_html_text(liveness.get('state'))}</code></div>
      <div><span class="muted">Unresolved effects</span><br><code>{_html_text(effects.get('unresolved_count'), '0')}</code></div>
      <div><span class="muted">Semantic confidence / version</span><br><code>{_html_text(confidence)}</code> / <code>{_html_text(semantic.get('interpretation_version'), '0')}</code></div>
      <div class="span-two"><span class="muted">Worktree</span><br><code class="breakable">{_html_text(worktree.get('path'))}</code></div>
      <div class="span-two"><span class="muted">Semantic source fingerprint</span><br><code class="breakable">{_html_text(source_fingerprint)}</code></div>
    </div>
    <h4>Provenance</h4><ul>{provenance_html}</ul>
  </details>
</article>"""


def _timeline_html(machine_events: list[dict[str, object]], interpretations: list[dict[str, object]]) -> str:
    combined: list[tuple[datetime, str]] = []
    kind_labels = {
        "workstream_discovered": "发现 Workstream",
        "workstream_status_changed": "Workstream 状态变化",
        "workstream_execution_changed": "执行状态变化",
        "workstream_health_changed": "健康状态变化",
        "continuation_discovered": "发现 continuation",
        "continuation_stage_changed": "阶段推进",
        "continuation_status_changed": "续跑状态变化",
        "continuation_next_action_changed": "下一步发生变化",
        "continuation_round_phase_changed": "执行阶段变化",
        "worktree_head_changed": "Git HEAD 推进",
    }
    for row in machine_events[-80:]:
        when = _parse_utc_iso(row.get("observed_at")) or datetime.min.replace(tzinfo=timezone.utc)
        kind = str(row.get("kind") or "project_event")
        identity = row.get("canonical_identity") if isinstance(row.get("canonical_identity"), dict) else {}
        identity_text = identity.get("id") or identity.get("task_id") or identity.get("path") or "project"
        before = row.get("before")
        after = row.get("after")
        body = (
            f'<article class="timeline-item"><time>{_html_text(_dashboard_display_time(row.get("observed_at")))}</time>'
            f'<div><strong>{_html_text(kind_labels.get(kind, kind))}</strong> · <code>{_html_text(identity_text)}</code>'
            f'<p class="muted">{_html_text(before)} → {_html_text(after)}</p></div></article>'
        )
        combined.append((when, body))
    for row in interpretations[-40:]:
        when = _parse_utc_iso(row.get("interpreted_at")) or datetime.min.replace(tzinfo=timezone.utc)
        proofs = row.get("recent_proof") if isinstance(row.get("recent_proof"), list) else []
        proof_text = "；".join(str(item) for item in proofs[:2])
        body = (
            f'<article class="timeline-item semantic-event"><time>{_html_text(_dashboard_display_time(row.get("interpreted_at")))}</time>'
            f'<div><strong>语义解释更新 v{_html_text(row.get("interpretation_version"))}</strong> · '
            f'<code>{_html_text(row.get("workstream_id"))}</code>'
            f'<p>{_html_text(row.get("human_title"))}</p><p class="muted">{_html_text(proof_text)}</p></div></article>'
        )
        combined.append((when, body))
    combined.sort(key=lambda pair: pair[0], reverse=True)
    return "".join(body for _when, body in combined[:60]) or '<p class="muted">暂无 meaningful progress event。</p>'


def _narrative_tone(status: object) -> str:
    value = str(status or "unknown").casefold()
    if value in {"critical", "blocked"}:
        return "critical"
    if value in {"warning", "waiting"}:
        return "warning"
    if value == "completed":
        return "healthy"
    if value in {"current", "active"}:
        return "active"
    if value == "maintenance":
        return "maintenance"
    return "muted"


def _human_state_label(value: object) -> str:
    raw = str(value or "unknown")
    labels = {
        "active": "进行中",
        "advancing": "推进中",
        "blocked": "受阻",
        "cancelled": "已取消",
        "completed": "已完成",
        "configured_empty": "已明确配置为空",
        "critical": "严重",
        "current": "当前",
        "empty": "无语义条目",
        "failed": "失败",
        "fresh": "新鲜",
        "future": "后续阶段",
        "healthy": "健康",
        "incomplete": "不完整",
        "interrupted": "已中断",
        "maintenance": "维护中",
        "not_interpreted": "尚未解释",
        "not_reviewed": "尚未复核",
        "planned": "待推进",
        "partial": "部分完成",
        "running": "运行中",
        "stale": "已陈旧",
        "success": "成功",
        "unconfigured": "尚未配置",
        "unknown": "未知",
        "waiting": "等待中",
        "warning": "需要关注",
    }
    return labels.get(raw.casefold(), raw)


def _presentation_type_label(value: object) -> str:
    raw = str(value or "text")
    labels = {
        "architecture": "架构图",
        "branch": "分支图",
        "dependency": "依赖图",
        "flow": "流程图",
        "hybrid": "混合视图",
        "multi_lane": "多泳道图",
        "roadmap": "路线图",
        "state_machine": "状态机图",
        "text": "文字视图",
        "timeline": "时间线",
        "tree": "树状图",
    }
    return labels.get(raw.casefold(), raw)


def _narrative_provenance_html(refs: object) -> str:
    values = [str(item) for item in refs or [] if str(item).strip()] if isinstance(refs, list) else []
    if not values:
        return '<span class="muted">provenance unavailable</span>'
    return "".join(f'<code class="provenance-ref">{_html_text(item)}</code>' for item in values)


def _project_narrative_html(current: dict[str, object]) -> str:
    semantic = current.get("project_narrative") if isinstance(current.get("project_narrative"), dict) else {}
    status = str(semantic.get("status") or "not_interpreted")
    narrative = semantic.get("narrative") if isinstance(semantic.get("narrative"), dict) else None
    if narrative is None:
        return (
            '<section class="panel project-map"><h2>项目地图 / Project Narrative</h2>'
            '<div class="semantic-notice"><strong>○ 尚未生成项目级叙事</strong>'
            '<p>Observer 仍可展示当前 Workstream 和 Timeline；缺少足够 authority 时不会为了填满项目地图而推造历史。</p></div></section>'
        )
    if status == "stale":
        return (
            '<section class="panel project-map" id="project-map">'
            '<div class="section-heading"><div><h2>项目地图 / Project Narrative</h2>'
            '<p class="muted">长期逻辑骨架，与最近事件 Timeline 分离。</p></div>'
            f'<span class="badge tone-warning">已陈旧 · v{_html_text(narrative.get("narrative_version"))}</span></div>'
            '<div class="semantic-notice tone-border-warning"><strong>▲ 项目地图已陈旧</strong>'
            '<p>底层项目 authority 已变化；旧项目地图仍保留在 Narrative 历史中用于追溯，但当前主页不会继续渲染旧关系图、里程碑或当前位置。完成新的 authority review 后才恢复当前地图。</p></div>'
            '<details><summary>Stale Narrative technical provenance</summary><div class="technical-grid">'
            f'<div><span class="muted">stored version</span><br><code>{_html_text(narrative.get("narrative_version"))}</code></div>'
            f'<div><span class="muted">current source fingerprint</span><br><code class="breakable">{_html_text(semantic.get("source_fingerprint"))}</code></div>'
            '</div></details></section>'
        )
    stale_notice = ""
    confidence = str(narrative.get("confidence") or "unknown")
    overall = narrative.get("overall_goal") if isinstance(narrative.get("overall_goal"), dict) else {}
    architecture = narrative.get("architecture") if isinstance(narrative.get("architecture"), dict) else {}
    nodes = [row for row in architecture.get("nodes") or [] if isinstance(row, dict)]
    edges = [row for row in architecture.get("edges") or [] if isinstance(row, dict)]
    milestones = [row for row in narrative.get("milestones") or [] if isinstance(row, dict)]
    current_position = narrative.get("current_position") if isinstance(narrative.get("current_position"), dict) else {}
    current_milestone = str(current_position.get("milestone_id") or "")

    architecture_diagram = render_relation_diagram(
        nodes,
        [{**row, "label": row.get("relation")} for row in edges],
        title="项目架构关系图",
        status_class=_narrative_tone,
        identity="project-architecture",
    )
    milestone_ids = {str(row.get("id")) for row in milestones if row.get("id")}
    milestone_nodes = [
        {
            "id": row.get("id"),
            "title": row.get("title"),
            "status": row.get("status"),
            "summary": row.get("summary"),
        }
        for row in milestones
        if row.get("id")
    ]
    milestone_edges: list[dict[str, object]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for row in milestones:
        source = str(row.get("id") or "")
        if not source:
            continue
        for target in row.get("next") or []:
            target_id = str(target)
            if target_id in milestone_ids and (source, target_id) not in seen_pairs:
                seen_pairs.add((source, target_id))
                milestone_edges.append({"from": source, "to": target_id, "label": "next"})
    for row in milestones:
        target = str(row.get("id") or "")
        if not target:
            continue
        for dependency in row.get("depends_on") or []:
            source = str(dependency)
            if source in milestone_ids and (source, target) not in seen_pairs:
                seen_pairs.add((source, target))
                milestone_edges.append({"from": source, "to": target, "label": "depends_on"})
    milestone_diagram = render_relation_diagram(
        milestone_nodes,
        milestone_edges,
        title="项目推进路线图",
        current_node_ids={current_milestone} if current_milestone else set(),
        status_class=_narrative_tone,
        identity="project-milestone-route",
    )
    milestone_html = "".join(
        (
            f'<article class="milestone {_narrative_tone(row.get("status"))} '
            f'{"is-current" if str(row.get("id") or "") == current_milestone else ""}">'
            f'<div class="milestone-marker" aria-hidden="true">{"●" if str(row.get("id") or "") == current_milestone else "○"}</div>'
            '<div class="milestone-body">'
            f'<div class="map-node-head"><strong>{_html_text(row.get("title"))}</strong>'
            f'<span class="badge tone-{_narrative_tone(row.get("status"))}">{_html_text(_human_state_label(row.get("status")))}</span></div>'
            f'<div class="canonical"><code>{_html_text(row.get("id"))}</code></div>'
            f'<p>{_html_text(row.get("summary"))}</p><p class="muted"><strong>意味着：</strong>{_html_text(row.get("implication"))}</p>'
            f'<div class="flow-meta"><span>depends_on: {_html_text(", ".join(str(item) for item in row.get("depends_on") or []) or "—")}</span>'
            f'<span>next: {_html_text(", ".join(str(item) for item in row.get("next") or []) or "—")}</span></div>'
            f'<details><summary>Evidence / Provenance</summary><div class="provenance-list">'
            f'{_narrative_provenance_html(row.get("evidence"))}{_narrative_provenance_html(row.get("provenance"))}'
            '</div></details></div></article>'
        )
        for row in milestones
    ) or '<p class="muted">暂无 milestone。</p>'
    return f"""
  <section class="panel project-map" id="project-map">
    <div class="section-heading"><div><h2>项目地图</h2><p class="muted">先看推进路线；架构、节点证据与技术来源按需展开。</p></div><span class="badge tone-{_narrative_tone(status)}">{_html_text(_human_state_label(status))} · v{_html_text(narrative.get('narrative_version'))}</span></div>
    {stale_notice}
    <section class="goal-card"><span class="target-eyebrow">整体目标</span><h3>{_html_text(overall.get('summary'))}</h3></section>
    <section class="map-section project-route-view"><div class="section-heading"><div><h3>项目推进路线</h3><p class="muted">完整阶段、当前路径与剩余路线。</p></div></div>{milestone_diagram}</section>
    <section class="project-current-strip tone-border-active"><div><span>当前</span><strong>{_html_text(current_position.get('summary'))}</strong></div><div><span>下一步</span><strong>{_html_text(current_position.get('next_logic'))}</strong></div></section>
    <details class="map-section project-architecture-view"><summary>查看项目架构图 · Architecture Map / 架构地图</summary>{architecture_diagram}</details>
    <details class="map-section project-route-details"><summary>逻辑里程碑流 / Project Evolution · 节点详情</summary><div class="milestone-flow">{milestone_html}</div></details>
    <details><summary>Project Narrative technical provenance</summary><div class="technical-grid"><div><span class="muted">confidence</span><br><code>{_html_text(confidence)}</code></div><div><span class="muted">source fingerprint</span><br><code class="breakable">{_html_text(semantic.get('source_fingerprint'))}</code></div><div class="span-two"><span class="muted">source paths</span><br>{_narrative_provenance_html(narrative.get('source_paths'))}</div><div class="span-two"><span class="muted">root provenance</span><br>{_narrative_provenance_html(narrative.get('provenance'))}</div></div></details>
  </section>"""


def _target_scope_ids(view: dict[str, object]) -> tuple[set[str], set[str]]:
    workstream_ids = {
        str(row.get("id"))
        for row in view.get("workstreams") or []
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row.get("id")
    }
    task_ids = {
        str(row.get("task_id"))
        for row in view.get("continuations") or []
        if isinstance(row, dict) and isinstance(row.get("task_id"), str) and row.get("task_id")
    }
    return workstream_ids, task_ids


def _identity_in_target_scope(identity: object, workstream_ids: set[str], task_ids: set[str]) -> bool:
    if not isinstance(identity, dict):
        return False
    identity_type = str(identity.get("type") or "")
    raw_id = str(identity.get("id") or "")
    raw_task_id = str(identity.get("task_id") or "")
    if identity_type == "workstream" or raw_id:
        if raw_id in workstream_ids:
            return True
    if identity_type == "continuation" or raw_task_id:
        if raw_task_id in task_ids:
            return True
    return False


def _target_alerts(current: dict[str, object], view: dict[str, object]) -> list[dict[str, object]]:
    workstream_ids, task_ids = _target_scope_ids(view)
    return [
        row
        for row in current.get("alerts") or []
        if isinstance(row, dict)
        and _identity_in_target_scope(row.get("canonical_identity"), workstream_ids, task_ids)
    ]


def _target_timeline_html(
    view: dict[str, object],
    machine_events: list[dict[str, object]],
    interpretations: list[dict[str, object]],
) -> str:
    workstream_ids, task_ids = _target_scope_ids(view)
    scoped_events = [
        row
        for row in machine_events
        if _identity_in_target_scope(row.get("canonical_identity"), workstream_ids, task_ids)
    ]
    scoped_interpretations = [
        row
        for row in interpretations
        if isinstance(row.get("workstream_id"), str) and row.get("workstream_id") in workstream_ids
    ]
    return _timeline_html(scoped_events, scoped_interpretations)


def _target_run_chain_html(runs: object) -> str:
    return render_target_run_history(runs, display_time=_dashboard_display_time)


def _target_semantic_history_html(view: dict[str, object], *, include_current: bool) -> str:
    semantic = view.get("semantic_review") if isinstance(view.get("semantic_review"), dict) else {}
    history_error = semantic.get("review_history_error")
    history = [row for row in semantic.get("review_history") or [] if isinstance(row, dict)]
    current_review = semantic.get("current_review") if isinstance(semantic.get("current_review"), dict) else {}
    current_review_id = str(current_review.get("review_id") or "")
    archived = [
        row
        for row in history
        if include_current or str(row.get("review_id") or "") != current_review_id
    ]
    history_warning = (
        '<div class="semantic-notice tone-border-warning"><strong>▲ 部分历史路线不可读</strong>'
        f'<p>{_html_text(history_error)}</p><p>其余通过校验的归档版本继续保留展示，不会用当前事实重写旧版本。</p></div>'
        if history_error
        else ""
    )
    if not archived:
        if not history_warning:
            return ""
        return f'<section class="target-semantic-history">{history_warning}</section>'

    target = view.get("target") if isinstance(view.get("target"), dict) else {}
    target_id = str(target.get("target_id") or "unknown")
    ordered_archived = list(reversed(archived))

    def comparison_facts(review: dict[str, object]) -> str:
        narrative = review.get("narrative") if isinstance(review.get("narrative"), dict) else {}
        node_rows = [row for row in narrative.get("route_nodes") or [] if isinstance(row, dict)]
        edge_rows = [row for row in narrative.get("route_edges") or [] if isinstance(row, dict)]
        nodes = {
            str(row.get("id")): {
                "title": str(row.get("title") or row.get("id") or "unknown"),
                "status": str(row.get("status") or "unknown"),
            }
            for row in node_rows
            if row.get("id")
        }
        edges = sorted(
            {
                (
                    str(row.get("from")),
                    str(row.get("to")),
                    str(row.get("label") or ""),
                )
                for row in edge_rows
                if row.get("from") and row.get("to")
            }
        )
        return json.dumps(
            {
                "nodes": nodes,
                "edges": [{"from": source, "to": target, "label": label} for source, target, label in edges],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def selector_options(*, selected_index: int | None = None) -> str:
        options: list[str] = []
        for index, review in enumerate(ordered_archived):
            selected = " selected" if selected_index == index else ""
            options.append(
                f'<option value="{escape(str(review.get("review_id") or "unknown"), quote=True)}"{selected}>'
                f'语义版本 {_html_text(review.get("semantic_revision"), "—")} · '
                f'{_html_text(review.get("review_id"), "unknown")} · '
                f'{_html_text(_dashboard_display_time(review.get("reviewed_at")))}'
                '</option>'
            )
        return "".join(options)

    focus_selector_options = selector_options(selected_index=0)
    comparison_controls = ""
    if len(ordered_archived) >= 2:
        comparison_controls = (
            '<div class="history-version-compare" '
            f'data-history-version-compare="{escape(target_id, quote=True)}">'
            '<strong>历史版本并排对比</strong>'
            '<div class="history-version-compare-controls">'
            '<label>版本 A：'
            f'<select data-history-version-compare-a>{selector_options(selected_index=0)}</select>'
            '</label>'
            '<label>版本 B：'
            f'<select data-history-version-compare-b>{selector_options(selected_index=1)}</select>'
            '</label>'
            '</div>'
            '<p class="muted">选择两份已归档语义后，页面会只保留这两版并排查看；'
            '这是历史事实对照，不会改写当前路线或自动推断节点等价关系。</p>'
            '<p class="history-version-compare-summary muted" data-history-version-compare-summary>'
            '差异摘要仅按已持久化的稳定 node id 与显式 relationship 比较；选择版本后在本地计算。</p>'
            '</div>'
        )
    items: list[str] = []
    for review in ordered_archived:
        narrative = review.get("narrative") if isinstance(review.get("narrative"), dict) else {}
        problems = [row for row in review.get("problems") or [] if isinstance(row, dict)]
        route_nodes = [row for row in narrative.get("route_nodes") or [] if isinstance(row, dict)]
        route_edges = [row for row in narrative.get("route_edges") or [] if isinstance(row, dict)]
        current_refs = narrative.get("current_node_refs") if "current_node_refs" in narrative else None
        review_id = str(review.get("review_id") or "unknown")
        facts = escape(comparison_facts(review), quote=True)
        diagram = render_relation_diagram(
            route_nodes,
            route_edges,
            title=f"历史路线版本 {review_id}",
            problem_node_ids={str(row.get("node_ref")) for row in problems if row.get("node_ref")},
            current_node_ids=(
                {str(item) for item in current_refs}
                if isinstance(current_refs, list)
                else None
            ),
            next_node_ids={str(item) for item in narrative.get("next_node_refs") or []},
            status_class=_narrative_tone,
            identity=f"target-{target_id}-history-{review_id}",
        )
        items.append(
            '<article class="target-semantic-history-version" '
            f'data-history-version="{escape(review_id, quote=True)}" '
            f'data-history-compare-facts="{facts}">'
            f'<h4>语义版本 {_html_text(review.get("semantic_revision"), "—")} · '
            f'<code>{_html_text(review_id)}</code></h4>'
            f'<p class="muted">复核时间：{_html_text(_dashboard_display_time(review.get("reviewed_at")))} · '
            f'决策：{_html_text(review.get("decision"))}。此版本仅用于历史追溯，不代表当前状态。</p>'
            f'<p>{_html_text(narrative.get("route_summary"), "该历史版本没有路线摘要。")}</p>'
            f'{diagram}'
            '</article>'
        )
    return (
        '<section class="target-semantic-history">'
        + history_warning
        + '<details><summary>历史路线版本 / 归档地图</summary>'
        '<p class="muted">历史版本保留各自复核时的事实与当前位置；不会用今天的状态重绘过去。'
        + (
            '当前路线图保持在上方，可选择一个历史版本并排对照。'
            if not include_current
            else '当前路线不可作为最新事实时，可从这里选择已归档版本逐个查看。'
        )
        + '</p>'
        '<label class="history-version-picker">历史版本：'
        f'<select data-history-version-picker="{escape(target_id, quote=True)}">{focus_selector_options}</select>'
        '</label>'
        '<p class="muted history-version-picker-help">启用页面脚本后，选择器会聚焦一个历史版本；禁用脚本时仍完整展示全部归档版本。</p>'
        + comparison_controls
        + '<div class="target-semantic-history-versions">'
        + "".join(items)
        + '</div>'
        + '</details></section>'
    )


def _target_semantic_story_html(view: dict[str, object]) -> tuple[str, str, set[str]]:
    semantic = view.get("semantic_review") if isinstance(view.get("semantic_review"), dict) else {}
    status = str(semantic.get("semantic_status") or "not_reviewed")
    review = semantic.get("current_review") if isinstance(semantic.get("current_review"), dict) else {}
    patch = semantic.get("active_transient_patch") if isinstance(semantic.get("active_transient_patch"), dict) else {}
    density = str(patch.get("density") or "balanced")
    emphasis = {str(item) for item in patch.get("emphasize_sections") or []}
    if status != "current" or not review:
        label = "目标路线尚未复核" if status == "not_reviewed" else "目标路线已陈旧"
        history_html = _target_semantic_history_html(view, include_current=True)
        return (
            f'<section class="target-story target-map-first is-stale"><div class="semantic-notice tone-border-warning"><strong>▲ {_html_text(label)}</strong>'
            '<p>当前路线不能作为最新事实展示；主区保持紧凑，不回退为原始执行文本。可从下方历史入口查看最近一次有效归档地图。</p></div>'
            f'{history_html}</section>',
            density,
            emphasis,
        )
    narrative = review.get("narrative") if isinstance(review.get("narrative"), dict) else {}
    problems = [row for row in review.get("problems") or [] if isinstance(row, dict)]
    proof_html = "".join(f"<li>{_html_text(item)}</li>" for item in narrative.get("recent_proof") or []) or '<li class="muted">暂无已复核的实质进展。</li>'
    problem_html = "".join(
        f'<article class="problem-card tone-border-{("critical" if row.get("blocking_impact") in {"blocks_task", "blocks_current_step"} else "warning")} "><strong>{_html_text(row.get("title"))}</strong><p>{_html_text(row.get("summary"))}</p><div class="muted">处理者：{_html_text(problem_dimension_label("handler", row.get("handler")))} · 阻塞影响：{_html_text(problem_dimension_label("blocking_impact", row.get("blocking_impact")))} · 计划影响：{_html_text(problem_dimension_label("plan_impact", row.get("plan_impact")))} · 状态：{_html_text(problem_dimension_label("status", row.get("status")))}</div></article>'
        for row in problems
    ) or '<p class="muted">当前复核没有需要单列的问题。</p>'
    presentation_type = patch.get("presentation_type") or review.get("presentation_type")
    target = view.get("target") if isinstance(view.get("target"), dict) else {}
    target_id = str(target.get("target_id") or "unknown")
    route_node_rows = [row for row in narrative.get("route_nodes") or [] if isinstance(row, dict)]
    route_edge_rows = [row for row in narrative.get("route_edges") or [] if isinstance(row, dict)]
    current_node_refs = narrative.get("current_node_refs") if "current_node_refs" in narrative else None
    primary_visualization = (
        narrative.get("primary_visualization")
        if isinstance(narrative.get("primary_visualization"), dict)
        else None
    )
    if primary_visualization:
        route_diagram = render_primary_visualization(
            primary_visualization,
            status_class=_narrative_tone,
            identity=f"target-{target_id}-primary-{primary_visualization.get('kind')}",
        )
        main_visualization_label = primary_visualization_kind_label(primary_visualization.get("kind"))
    else:
        route_diagram = render_relation_diagram(
            route_node_rows,
            route_edge_rows,
            title="目标完整路线关系图",
            problem_node_ids={str(row.get("node_ref")) for row in problems if row.get("node_ref")},
            current_node_ids=(
                {str(item) for item in current_node_refs}
                if isinstance(current_node_refs, list)
                else None
            ),
            next_node_ids={str(item) for item in narrative.get("next_node_refs") or []},
            status_class=_narrative_tone,
            identity=f"target-{target_id}-route",
        )
        main_visualization_label = "完整推进路线 · 通用 fallback"
    patch_notice = (
        '<details class="target-semantic-technical"><summary>展示调整详情</summary>'
        f'<p><strong>{_html_text(patch.get("patch_id"))}</strong> · {_html_text(patch.get("reviewed_intent"))}</p></details>'
        if patch
        else ""
    )
    history_html = _target_semantic_history_html(view, include_current=False)
    return (
        '<section class="target-story target-map-first">'
        '<div class="target-map-heading">'
        f'<div><span class="target-eyebrow">最终目标</span><h3>{_html_text(narrative.get("overall_goal"))}</h3></div>'
        f'<span class="badge tone-active">{_html_text(main_visualization_label)}</span></div>'
        '<div class="target-route-main" data-story-section="route">'
        f'<div class="target-route-caption"><strong>{_html_text(main_visualization_label)}</strong><span>{_html_text(narrative.get("route_summary"))}</span></div>'
        f'{route_diagram}</div>'
        '<div class="target-focus-strip">'
        f'<section class="target-focus-card is-current" data-story-section="current_position"><span>当前</span><strong>{_html_text(narrative.get("current_position"))}</strong><small>{_html_text(narrative.get("why_now"))}</small></section>'
        f'<section class="target-focus-card" data-story-section="recent_proof"><span>最近实质进展</span><ul>{proof_html}</ul></section>'
        f'<section class="target-focus-card" data-story-section="next_logic"><span>下一步</span><strong>{_html_text(narrative.get("next_logic"))}</strong></section>'
        '</div>'
        + (
            '<section class="target-problem-strip" data-story-section="problems"><h4>当前问题与影响</h4>'
            f'{problem_html}</section>'
            if problems
            else ""
        )
        + '<details class="target-semantic-technical"><summary>语义复核与技术来源</summary>'
        f'<p>复核：<code>{_html_text(review.get("review_id"))}</code></p>'
        f'<div class="provenance-list">{_narrative_provenance_html(narrative.get("evidence_refs"))}</div></details>'
        f'{patch_notice}{history_html}</section>',
        density,
        emphasis,
    )


def _target_view_html(
    current: dict[str, object],
    view: dict[str, object],
    machine_events: list[dict[str, object]],
    interpretations: list[dict[str, object]],
    *,
    active: bool,
) -> str:
    target = view.get("target") if isinstance(view.get("target"), dict) else {}
    target_id = str(target.get("target_id") or "unknown")
    local_current = dict(current)
    local_current["continuations"] = list(view.get("continuations") or [])
    workstreams = [row for row in view.get("workstreams") or [] if isinstance(row, dict)]
    cards = "".join(_workstream_card_html(local_current, row) for row in workstreams)
    if not cards:
        cards = '<p class="muted">该 target 当前没有匹配到 Workstream；Observer 不会从其他 Workstream 猜测替代内容。</p>'
    scoped_alerts = _target_alerts(current, view)
    alerts_html = "".join(_dashboard_alert_html(row) for row in scoped_alerts) or '<p class="muted">该目标当前没有告警。</p>'
    timeline = _target_timeline_html(view, machine_events, interpretations)
    story_html, density, emphasis = _target_semantic_story_html(view)
    execution_summary = render_target_execution_summary(view, scoped_alerts, display_time=_dashboard_display_time)
    return f"""
  <section class="target-panel {'is-active' if active else ''} density-{escape(density, quote=True)}" data-target-panel="{escape(target_id, quote=True)}">
    <div class="section-heading"><div><h2>{_html_text(target.get('title'))}</h2>
    <p class="muted">已注册自动任务 · 地图优先展示当前进度与下一步。</p></div>
    <span class="badge tone-active">已注册</span></div>
    {execution_summary}
    {story_html}
    <section class="target-subsection target-run-section {'is-emphasized' if 'runs' in emphasis else ''}"><div class="section-heading"><div><h3>Agent 运行记录</h3><p class="muted">默认只展示紧凑摘要；每次可归属运行仍可追溯。</p></div></div>{_target_run_chain_html(view.get('runs'))}</section>
    <details class="target-subsection target-secondary"><summary>执行范围与技术详情</summary><div class="workstream-list">{cards}</div></details>
    <details class="target-subsection target-secondary {'is-emphasized' if 'alerts' in emphasis else ''}"><summary>目标告警与原始诊断</summary>{alerts_html}</details>
    <details class="target-subsection target-secondary"><summary>目标时间线</summary>{timeline}</details>
  </section>"""


def _target_pages_html(
    current: dict[str, object],
    machine_events: list[dict[str, object]],
    interpretations: list[dict[str, object]],
) -> tuple[str, str, list[dict[str, object]]]:
    target_state = current.get("targets") if isinstance(current.get("targets"), dict) else {}
    views = [row for row in target_state.get("targets") or [] if isinstance(row, dict)]
    if not views:
        return (
            '<div class="target-tabs" role="tablist"><span class="muted">暂无已注册观测目标</span></div>',
            '<section class="panel"><div class="semantic-notice"><strong>○ 尚未注册观测目标</strong>'
            '<p>Dashboard 不会把 Workstream/worktree 的存在自动当成用户要观察的自动任务。请先通过正式 Target Registry 注册目标。</p></div></section>',
            [],
        )
    tabs: list[str] = []
    panels: list[str] = []
    scoped_alerts: list[dict[str, object]] = []
    for index, view in enumerate(views):
        target = view.get("target") if isinstance(view.get("target"), dict) else {}
        target_id = str(target.get("target_id") or f"target-{index}")
        tabs.append(
            f'<button class="target-tab {"is-active" if index == 0 else ""}" type="button" '
            f'data-target-tab="{escape(target_id, quote=True)}">{_html_text(target.get("title") or target_id)}</button>'
        )
        panels.append(_target_view_html(current, view, machine_events, interpretations, active=index == 0))
        scoped_alerts.extend(_target_alerts(current, view))
    deduped: dict[str, dict[str, object]] = {}
    for row in scoped_alerts:
        key = str(row.get("alert_key") or _stable_digest(row))
        deduped[key] = row
    return (
        '<div class="target-tabs" role="tablist">' + "".join(tabs) + "</div>",
        '<section class="panel target-pages">' + "".join(panels) + "</section>",
        list(deduped.values()),
    )


def render_dashboard_html(
    project: Any,
    *,
    current: dict[str, object],
    status: dict[str, object],
    machine_events: list[dict[str, object]],
    interpretations: list[dict[str, object]],
    glossary: dict[str, object],
    self_health_alerts: list[dict[str, object]] | None = None,
) -> str:
    """Render a self-contained, file://-safe Dashboard with no external assets."""

    safe_current = sanitize_dashboard_payload(current)
    safe_status = sanitize_dashboard_payload(status)
    safe_events = sanitize_dashboard_payload(machine_events)
    safe_interpretations = sanitize_dashboard_payload(interpretations)
    safe_glossary = sanitize_dashboard_payload(glossary)
    safe_self_alerts = sanitize_dashboard_payload(self_health_alerts or [])
    if not isinstance(safe_current, dict) or not isinstance(safe_status, dict):
        raise ValueError("dashboard requires object current/status payloads")
    workstreams = [row for row in safe_current.get("workstreams") or [] if isinstance(row, dict)]
    target_tabs_html, target_pages_html, target_alerts = _target_pages_html(
        safe_current,
        safe_events if isinstance(safe_events, list) else [],
        safe_interpretations if isinstance(safe_interpretations, list) else [],
    )
    registry_alerts = [row for row in safe_current.get("alerts") or [] if isinstance(row, dict) and isinstance(row.get("canonical_identity"), dict) and row["canonical_identity"].get("type") == "observer_target_registry"]
    alerts = target_alerts + registry_alerts
    self_alerts = [row for row in safe_self_alerts if isinstance(row, dict)] if isinstance(safe_self_alerts, list) else []
    all_alerts = self_alerts + alerts
    current_data_age = safe_status.get("data_age") if isinstance(safe_status.get("data_age"), dict) else {}
    target_state = safe_current.get("targets") if isinstance(safe_current.get("targets"), dict) else {}
    registry_health = target_state.get("registry_health") if isinstance(target_state.get("registry_health"), dict) else {}
    target_views = [row for row in target_state.get("targets") or [] if isinstance(row, dict)]
    registered_workstream_ids = {
        str(row.get("id"))
        for view in target_views
        for row in view.get("workstreams") or []
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    registered_workstreams = [row for row in workstreams if row.get("id") in registered_workstream_ids]
    visible_current = dict(safe_current)
    visible_current["alerts"] = alerts
    visible_current["workstreams"] = registered_workstreams
    overall = _overall_health(visible_current, self_alerts)
    active_count = sum(1 for row in registered_workstreams if str(row.get("status") or "").casefold() in {"active", "blocked", "merging", "readytomerge"})
    alerts_html = "".join(_dashboard_alert_html(row) for row in all_alerts) or '<p class="muted">当前没有需要关注的告警。</p>'
    overview = target_state.get("project_overview") if isinstance(target_state.get("project_overview"), dict) else {}
    overview_decision = str(overview.get("decision") or "undecided")
    if overview_decision == "enabled":
        project_map_html = _project_narrative_html(safe_current)
    elif overview_decision == "disabled":
        project_map_html = (
            '<section class="panel"><div class="semantic-notice"><strong>项目总览已由 authority 明确停用</strong>'
            f'<p>{_html_text(overview.get("reason"))}</p><div class="provenance-list">{_narrative_provenance_html(overview.get("evidence_refs"))}</div></div></section>'
        )
    else:
        project_map_html = (
            '<section class="panel"><div class="semantic-notice"><strong>项目总览尚未决策 / Project Overview</strong>'
            '<p>在 authority 明确支持统一目标/路线/架构之前，Observer 不会把异构 targets 强行拼成一个项目地图。</p></div></section>'
        )
    latest_proof: list[str] = []
    for row in registered_workstreams:
        semantic = row.get("semantic") if isinstance(row.get("semantic"), dict) else {}
        interpretation = semantic.get("interpretation") if semantic.get("status") == "current" and isinstance(semantic.get("interpretation"), dict) else {}
        for proof in interpretation.get("recent_proof") or []:
            if isinstance(proof, str) and proof not in latest_proof:
                latest_proof.append(proof)
    latest_html = "".join(f"<li>{_html_text(item)}</li>" for item in latest_proof[:4]) or '<li class="muted">尚无当前语义层确认的重大进展。</li>'
    glossary_terms = safe_glossary.get("terms") if isinstance(safe_glossary, dict) and isinstance(safe_glossary.get("terms"), dict) else {}
    glossary_html = "".join(
        f'<article class="glossary-item" data-search="{escape((str(term)+" "+str(entry.get("human_term") or "")+" "+str(entry.get("explanation") or "")).casefold(), quote=True)}">'
        f'<strong><code>{_html_text(term)}</code> → {_html_text(entry.get("human_term"))}</strong>'
        f'<p>{_html_text(entry.get("explanation"))}</p><span class="muted">confidence: {_html_text(entry.get("confidence"))}</span></article>'
        for term, entry in sorted(glossary_terms.items()) if isinstance(entry, dict)
    ) or '<p class="muted">暂无 glossary 条目。</p>'
    embedded = {
        "schema_version": OBSERVER_DASHBOARD_SCHEMA,
        "project": sanitize_dashboard_payload({"project_id": project.project_id, "canonical_root": str(project.canonical_root)}),
        "current": safe_current,
        "self_health": safe_status,
        "timeline": safe_events,
        "interpretations": safe_interpretations,
        "glossary": safe_glossary,
    }
    embedded_json = json.dumps(embedded, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    health_icon = "●" if overall == "critical" else "▲" if overall == "warning" else "●"
    health_label = {"critical": "严重", "warning": "需要关注", "healthy": "健康"}.get(overall, overall)
    title = f"{project.canonical_root.name} · Project Observer"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html_text(title)}</title>
<style>
:root{{--bg:#f6f8fb;--surface:#fff;--text:#1d2433;--muted:#667085;--line:#d9dee8;--blue:#1769d2;--blue-bg:#eef5ff;--green:#16784a;--green-bg:#edf9f2;--amber:#9a6700;--amber-bg:#fff8df;--red:#b42318;--red-bg:#fff0ee;--gray-bg:#f2f4f7;--shadow:0 1px 2px rgba(16,24,40,.06)}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.62 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}} a{{color:var(--blue)}} code{{font:12.5px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;color:#344054}} .page{{max-width:1280px;margin:auto;padding:24px}} h1{{font-size:24px;line-height:1.25;margin:0 0 4px}} h2{{font-size:19px;margin:0 0 14px}} h3{{font-size:17px;margin:0}} h4{{font-size:14px;margin:0 0 6px}} p{{margin:6px 0 12px}} ul{{margin:6px 0 12px;padding-left:20px}} .muted{{color:var(--muted)}} .canonical{{color:var(--muted);font-size:13px;margin-top:4px}} .top,.section-heading{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}} .top{{margin-bottom:18px}} .summary-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0 22px}} .metric,.panel,.workstream-card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}} .metric{{padding:14px}} .metric strong{{display:block;font-size:18px;margin-top:3px}} .panel{{padding:18px;margin:0 0 18px}} .toolbar{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}} input,select{{font:inherit;border:1px solid var(--line);border-radius:8px;background:#fff;padding:8px 10px;min-height:38px}} input{{flex:1;min-width:220px}} .workstream-list{{display:grid;gap:14px}} .workstream-card{{padding:18px}} .card-header{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}} .badge-row{{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}} .badge{{display:inline-flex;align-items:center;gap:4px;border:1px solid currentColor;border-radius:999px;padding:2px 8px;font-size:12.5px;white-space:nowrap}} .tone-critical,.tone-text-critical{{color:var(--red)}} .tone-warning,.tone-text-warning{{color:var(--amber)}} .tone-healthy{{color:var(--green)}} .tone-active{{color:var(--blue)}} .tone-maintenance{{color:#6941c6}} .tone-muted{{color:var(--muted)}} .tone-border-critical{{border-left:4px solid var(--red)!important}} .tone-border-warning{{border-left:4px solid var(--amber)!important}} .tone-border-healthy{{border-left:4px solid var(--green)!important}} .tone-border-active{{border-left:4px solid var(--blue)!important}} .tone-border-maintenance{{border-left:4px solid #6941c6!important}} .tone-border-muted{{border-left:4px solid #98a2b3!important}} .semantic-notice{{background:var(--gray-bg);border-radius:8px;padding:9px 11px;margin:12px 0;font-size:13px}} .logic-grid,.technical-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 18px;margin-top:14px}} .logic-grid section{{border-top:1px solid var(--line);padding-top:10px}} .span-two{{grid-column:1/-1}} details{{border-top:1px solid var(--line);margin-top:14px;padding-top:10px}} summary{{cursor:pointer;font-weight:600;color:#344054}} .breakable{{word-break:break-all}} .alert{{border:1px solid var(--line);border-radius:9px;padding:12px 14px;margin:9px 0;background:#fff}} .alert-title{{font-weight:700}} .timeline-item{{display:grid;grid-template-columns:160px 1fr;gap:14px;border-left:2px solid var(--line);padding:5px 0 14px 14px;margin-left:5px}} .timeline-item time{{font-size:12.5px;color:var(--muted)}} .semantic-event{{border-left-color:var(--blue)}} .glossary-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}} .glossary-item{{border:1px solid var(--line);border-radius:8px;padding:12px}} .project-map{{border-top:3px solid #4f46e5}} .goal-card{{background:#eef2ff;border:1px solid #c7d2fe;border-radius:10px;padding:14px;margin:12px 0 18px}} .map-section{{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}} .architecture-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:12px}} .map-node{{border:1px solid var(--line);border-radius:9px;padding:12px;background:#fff}} .map-node-head{{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}} .architecture-edges{{list-style:none;padding:0;margin:12px 0}} .map-edge{{display:grid;grid-template-columns:auto auto auto 1fr;gap:8px;align-items:center;border-top:1px dashed var(--line);padding:8px 0}} .milestone-flow{{display:grid;gap:0;margin-top:12px}} .milestone{{display:grid;grid-template-columns:28px 1fr;gap:10px;position:relative;padding-bottom:15px}} .milestone:not(:last-child)::before{{content:"";position:absolute;left:8px;top:22px;bottom:0;border-left:2px solid var(--line)}} .milestone-marker{{font-size:16px;color:#98a2b3;z-index:1;background:var(--surface)}} .milestone.is-current .milestone-marker{{color:var(--blue)}} .milestone.is-current .milestone-body{{background:var(--blue-bg);border-color:#b2d4ff}} .milestone-body{{border:1px solid var(--line);border-radius:9px;padding:11px 13px}} .flow-meta{{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);font-size:12.5px}} .current-position{{margin-top:14px;background:var(--blue-bg);border:1px solid #b2d4ff;border-radius:9px;padding:13px}} .provenance-list{{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}} .provenance-ref{{background:var(--gray-bg);border-radius:4px;padding:2px 5px}} .target-tabs{{display:flex;gap:8px;flex-wrap:wrap}} .target-tab{{font:inherit;border:1px solid var(--line);background:#fff;color:var(--text);border-radius:999px;padding:7px 12px;cursor:pointer}} .target-tab.is-active{{border-color:#1769d2;background:var(--blue-bg);color:var(--blue);font-weight:700}} .target-panel{{display:none}} .target-panel.is-active{{display:block}} .target-subsection{{border-top:1px solid var(--line);padding-top:14px;margin-top:16px}} .target-run{{border-left:3px solid #98a2b3;padding:8px 12px;margin:8px 0;background:var(--gray-bg);border-radius:0 8px 8px 0}} .target-decision-summary{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0;padding:12px;border:1px solid var(--line);border-radius:9px;background:var(--blue-bg)}} .target-decision-summary strong{{display:block;margin-top:2px}} .target-story{{border:1px solid var(--line);border-radius:10px;padding:14px;margin-top:14px;background:#fbfcfe}} .story-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}} .story-section{{border:1px solid var(--line);border-radius:8px;padding:11px;background:#fff}} .story-section.is-emphasized,.target-subsection.is-emphasized{{border-left:4px solid var(--blue);background:var(--blue-bg)}} .route-grid{{display:grid;gap:7px;margin-top:8px}} .route-node{{border-left:3px solid #98a2b3;padding:7px 9px;background:var(--gray-bg)}} .route-node .badge{{float:right}} .relation-diagram-shell{{margin:10px 0}} .relation-diagram{{display:block;width:100%;min-height:180px;border:1px solid var(--line);border-radius:10px;background:#fff}} .diagram-edge line{{stroke:#667085;stroke-width:2}} .diagram-edge text{{font-size:11px;fill:#475467;paint-order:stroke;stroke:#fff;stroke-width:4px}} .diagram-arrow path{{fill:#667085}} .diagram-node rect{{fill:#f8fafc;stroke:#98a2b3;stroke-width:2}} .diagram-node.tone-active rect{{fill:var(--blue-bg);stroke:var(--blue)}} .diagram-node.tone-healthy rect{{fill:var(--green-bg);stroke:var(--green)}} .diagram-node.tone-warning rect{{fill:var(--amber-bg);stroke:var(--amber)}} .diagram-node.tone-critical rect{{fill:var(--red-bg);stroke:var(--red)}} .diagram-title{{font-size:14px;font-weight:700;fill:#101828}} .diagram-status{{font-size:11px;fill:#475467}} .diagram-summary{{font-size:10.5px;fill:#667085}} .diagram-problem{{fill:var(--red)}} .diagram-problem-text{{font-size:12px;font-weight:700;fill:#fff}} .diagram-edge-details{{margin-top:6px}} .problem-card{{border:1px solid var(--line);border-radius:7px;padding:8px 10px;margin:6px 0}} .history-version-picker{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0}} .history-version-picker select{{min-width:min(100%,420px)}} .history-version-compare{{border:1px solid var(--line);border-radius:9px;padding:10px 12px;margin:10px 0;background:#fff}} .history-version-compare-controls{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}} .history-version-compare-controls label{{display:grid;gap:4px}} .history-version-compare-summary{{border-left:3px solid var(--blue);padding-left:9px;margin-top:10px}} .target-semantic-history-versions.is-history-compare-active{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}} .target-semantic-history-version.is-history-filtered{{display:none}} .density-compact .target-story,.density-compact .story-section{{padding:8px}} .density-detailed .story-grid{{gap:14px}} .hidden{{display:none!important}} .empty{{padding:18px;color:var(--muted);text-align:center}} footer{{color:var(--muted);font-size:12.5px;padding:6px 0 20px}}
.diagram-node.is-current>rect:first-of-type{{stroke-width:4}} .diagram-node.is-next>rect:first-of-type{{stroke-dasharray:7 4}} .diagram-current{{fill:var(--blue)!important;stroke:var(--blue)!important}} .diagram-current-text{{font-size:10px;font-weight:700;fill:#fff}} .diagram-next{{fill:#fff!important;stroke:var(--blue)!important;stroke-width:1.5!important}} .diagram-next-text{{font-size:9.5px;font-weight:700;fill:var(--blue)}}
.target-map-summary{{display:grid;grid-template-columns:190px 210px minmax(0,1fr);gap:10px;margin:10px 0 12px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:#fff}} .target-map-metric,.target-latest-outcome{{min-width:0}} .target-map-metric span,.target-latest-outcome span,.target-eyebrow,.project-current-strip span,.target-focus-card>span{{display:block;color:var(--muted);font-size:12px;font-weight:700;letter-spacing:.02em}} .target-map-metric strong,.target-latest-outcome strong{{display:block;margin-top:2px;line-height:1.35}} .target-map-metric small{{display:block;color:var(--muted);margin-top:2px}} .target-latest-outcome{{border-left:1px solid var(--line);padding-left:12px}} .target-map-first{{padding:12px;background:#fff}} .target-map-first.is-stale{{padding:10px}} .target-map-heading{{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:8px}} .target-map-heading h3{{font-size:18px;line-height:1.35;margin:2px 0 0}} .target-route-main{{margin-top:8px}} .target-route-caption{{display:flex;gap:10px;align-items:baseline;justify-content:space-between;margin-bottom:4px}} .target-route-caption>span{{color:var(--muted);font-size:13px;text-align:right;max-width:70%}} .target-map-first .relation-diagram{{min-height:240px}} .target-focus-strip{{display:grid;grid-template-columns:1fr 1.25fr 1fr;gap:8px;margin-top:8px}} .target-focus-card{{padding:9px 10px;border-top:2px solid var(--line);background:var(--gray-bg);border-radius:6px}} .target-focus-card.is-current{{border-top-color:var(--blue);background:var(--blue-bg)}} .target-focus-card strong{{display:block;line-height:1.35;margin-top:2px}} .target-focus-card small{{display:block;color:var(--muted);margin-top:4px}} .target-focus-card ul{{margin:3px 0 0;padding-left:18px}} .target-problem-strip{{margin-top:8px;padding-top:8px;border-top:1px solid var(--line)}} .target-problem-strip .problem-card{{padding:7px 9px;margin:5px 0}} .target-semantic-technical{{font-size:13px}} .target-secondary{{padding:8px 0;margin-top:8px}} .target-secondary>summary{{font-size:13px;color:var(--muted)}} .target-run-section{{margin-top:12px}} .target-run-table-wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:#fff}} .target-run-table{{width:100%;border-collapse:collapse;font-size:12.5px}} .target-run-table th{{text-align:left;color:var(--muted);font-weight:700;background:var(--gray-bg);padding:7px 8px;white-space:nowrap}} .target-run-table td{{padding:7px 8px;border-top:1px solid var(--line);vertical-align:top}} .target-run-table code{{font-size:11.5px}} .target-run-outcome{{min-width:220px}} .target-run-technical{{margin:0;padding:0;border:0}} .target-run-technical summary{{font-size:12px;font-weight:600;white-space:nowrap}} .run-evidence-list{{display:grid;gap:3px;margin-top:4px;max-width:460px}} .project-current-strip{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0;padding:10px 12px;background:var(--blue-bg);border-radius:8px}} .project-current-strip strong{{display:block;margin-top:2px}} .project-architecture-view,.project-route-details{{margin-top:8px}} .project-architecture-view>summary,.project-route-details>summary{{padding:6px 0}} .project-route-view .relation-diagram{{min-height:220px}}
.primary-visualization{{border:1px solid var(--line);border-radius:10px;padding:12px;background:#fff}} .primary-visualization-heading{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}} .primary-visualization-heading h4{{font-size:16px;line-height:1.4;margin:2px 0}} .primary-visualization-reason{{color:var(--muted);font-size:13px;margin:5px 0 8px}} .metric-trend-svg{{display:block;width:100%;min-height:220px;border:1px solid var(--line);border-radius:8px;background:#fff}} .metric-trend-svg text{{font-size:11px;fill:#475467}} .trend-legend{{display:flex;gap:12px;flex-wrap:wrap;margin:4px 0 8px;font-size:12px;color:var(--muted)}} .trend-legend-item{{border-right:1px solid var(--line);padding-right:12px}} .primary-visualization-data{{font-size:12.5px}} .status-matrix{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;margin-top:8px}} .status-matrix-item{{margin:0;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--gray-bg)}} .status-matrix-item.is-current{{border:2px solid var(--blue);background:var(--blue-bg)}} .status-matrix-item summary{{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;align-items:center}} .status-matrix-item summary em{{font-style:normal;color:var(--blue);font-size:11px}} .status-matrix-item p{{font-size:13px;margin:6px 0}}
@media(max-width:900px){{.target-map-summary,.target-focus-strip,.project-current-strip{{grid-template-columns:1fr}}.target-latest-outcome{{border-left:0;border-top:1px solid var(--line);padding:8px 0 0}}.target-route-caption{{display:block}}.target-route-caption>span{{display:block;max-width:none;text-align:left;margin-top:3px}}}}
@media(max-width:760px){{.page{{padding:14px}}.top,.section-heading,.card-header{{display:block}}.summary-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.logic-grid,.technical-grid,.glossary-grid,.architecture-grid,.story-grid,.history-version-compare-controls,.target-semantic-history-versions.is-history-compare-active{{grid-template-columns:1fr}}.span-two{{grid-column:auto}}.badge-row{{justify-content:flex-start;margin-top:10px}}.timeline-item{{grid-template-columns:1fr;gap:2px}}.map-edge{{grid-template-columns:auto auto auto;align-items:start}}.map-edge>span:last-of-type{{grid-column:1/-1}}}}
</style>
</head>
<body>
<main class="page">
  <header class="top"><div><h1>{_html_text(title)}</h1><div class="muted">最后观察：{_html_text(_dashboard_display_time(safe_current.get('observed_at')))} · 数据状态：{_html_text(_human_state_label(current_data_age.get('state')))}</div></div><div class="badge tone-{_html_text(overall)}"><span aria-hidden="true">{health_icon}</span> 整体健康：{_html_text(health_label)}</div></header>
  <section class="summary-grid" aria-label="项目总览">
    <div class="metric"><span class="muted">已注册观测目标</span><strong>{len(target_views)}</strong></div>
    <div class="metric"><span class="muted">当前告警</span><strong>{len(all_alerts)}</strong></div>
    <div class="metric"><span class="muted">目标完整性</span><strong>{_html_text(_human_state_label(registry_health.get('status')))}</strong></div>
    <div class="metric"><span class="muted">语义覆盖状态</span><strong>{_html_text(_human_state_label((safe_current.get('semantic') or {}).get('status') if isinstance(safe_current.get('semantic'),dict) else None))}</strong></div>
  </section>
  {project_map_html}
  <section class="panel target-navigation"><div class="section-heading"><div><h2>观测目标</h2><p class="muted">仅展示 Target Registry 中显式注册的自动任务目标。</p></div></div>{target_tabs_html}</section>
  {target_pages_html}
  <section class="panel"><h2>最近重大进展</h2><ul>{latest_html}</ul></section>
  <section class="panel" id="alerts"><h2>当前告警</h2>{alerts_html}</section>
  <section class="panel"><h2>语义词汇表 / Semantic Glossary</h2><div class="glossary-grid" id="glossary">{glossary_html}</div></section>
  <footer>Observer 只解释本地事实，不参与 Writer control plane。Dashboard 为静态自包含文件，不需要 HTTP 服务。页面时间统一显示北京时间 (UTC+08:00)，底层 canonical state/history 仍使用 UTC。</footer>
</main>
<script id="observer-data" type="application/json">{embedded_json}</script>
<script>
(()=>{{
  document.querySelectorAll('[data-target-tab]').forEach(tab=>tab.addEventListener('click',()=>{{
    const id=tab.dataset.targetTab;
    document.querySelectorAll('[data-target-tab]').forEach(item=>item.classList.toggle('is-active',item===tab));
    document.querySelectorAll('[data-target-panel]').forEach(panel=>panel.classList.toggle('is-active',panel.dataset.targetPanel===id));
  }}));
  document.querySelectorAll('[data-history-version-picker]').forEach(picker=>picker.addEventListener('change',()=>{{
    const details=picker.closest('details');
    if(!details)return;
    const selected=picker.value;
    const versions=details.querySelector('.target-semantic-history-versions');
    if(versions)versions.classList.remove('is-history-compare-active');
    details.querySelectorAll('[data-history-version]').forEach(item=>item.classList.toggle('is-history-filtered',item.dataset.historyVersion!==selected));
  }}));
  document.querySelectorAll('[data-history-version-compare]').forEach(compare=>{{
    const applyComparison=()=>{{
      const details=compare.closest('details');
      if(!details)return;
      const first=compare.querySelector('[data-history-version-compare-a]');
      const second=compare.querySelector('[data-history-version-compare-b]');
      if(!first||!second)return;
      const selected=new Set([first.value,second.value]);
      const versions=details.querySelector('.target-semantic-history-versions');
      if(versions)versions.classList.add('is-history-compare-active');
      details.querySelectorAll('[data-history-version]').forEach(item=>item.classList.toggle('is-history-filtered',!selected.has(item.dataset.historyVersion)));
      const summary=compare.querySelector('[data-history-version-compare-summary]');
      const firstItem=details.querySelector(`[data-history-version="${{first.value}}"]`);
      const secondItem=details.querySelector(`[data-history-version="${{second.value}}"]`);
      if(!summary||!firstItem||!secondItem)return;
      try{{
        const a=JSON.parse(firstItem.dataset.historyCompareFacts||'{{}}');
        const b=JSON.parse(secondItem.dataset.historyCompareFacts||'{{}}');
        const aNodes=a.nodes||{{}};
        const bNodes=b.nodes||{{}};
        const onlyA=Object.keys(aNodes).filter(id=>!(id in bNodes)).sort();
        const onlyB=Object.keys(bNodes).filter(id=>!(id in aNodes)).sort();
        const statusChanges=Object.keys(aNodes).filter(id=>id in bNodes&&aNodes[id].status!==bNodes[id].status).sort().map(id=>`${{id}}(${{aNodes[id].status}}↔${{bNodes[id].status}})`);
        const edgeKey=edge=>`${{edge.from}}→${{edge.to}}${{edge.label?`[${{edge.label}}]`:''}}`;
        const aEdges=new Set((a.edges||[]).map(edgeKey));
        const bEdges=new Set((b.edges||[]).map(edgeKey));
        const onlyAEdges=[...aEdges].filter(key=>!bEdges.has(key)).sort();
        const onlyBEdges=[...bEdges].filter(key=>!aEdges.has(key)).sort();
        const show=items=>items.length?items.join('、'):'无';
        summary.textContent=`稳定 ID 差异：仅 A 有节点：${{show(onlyA)}}；仅 B 有节点：${{show(onlyB)}}；状态不同：${{show(statusChanges)}}；仅 A 有关系：${{show(onlyAEdges)}}；仅 B 有关系：${{show(onlyBEdges)}}。`;
      }}catch(error){{
        summary.textContent='历史版本差异摘要不可计算；并排原始归档仍保持可读，未尝试猜测或修补历史事实。';
      }}
    }};
    compare.querySelectorAll('select').forEach(picker=>picker.addEventListener('change',applyComparison));
  }});
}})();
</script>
</body></html>"""


def write_dashboard(
    project: Any,
    *,
    current: dict[str, object],
    status: dict[str, object],
    machine_events: list[dict[str, object]],
    interpretations: list[dict[str, object]],
    glossary: dict[str, object],
    self_health_alerts: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    html = render_dashboard_html(
        project,
        current=current,
        status=status,
        machine_events=machine_events,
        interpretations=interpretations,
        glossary=glossary,
        self_health_alerts=self_health_alerts,
    )
    if "<!doctype html>" not in html.casefold() or "observer-data" not in html:
        raise ValueError("dashboard render validation failed")
    if SEMANTIC_SENSITIVE_VALUE_RE.search(html):
        raise ValueError("dashboard render contains credential-like material")
    path = observer_paths(project)["dashboard"]
    atomic_write_text(path, html)
    return {
        "schema_version": OBSERVER_DASHBOARD_SCHEMA,
        "status": "success",
        "rendered_at": utc_now_iso(),
        "path": str(path),
        "size_bytes": len(html.encode("utf-8")),
        "content_digest": _stable_digest(html),
    }


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
