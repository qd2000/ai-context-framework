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
    tone = severity if severity in {"critical", "warning"} else "active"
    icon = "●" if severity == "critical" else "▲" if severity == "warning" else "●"
    title = _html_text(alert.get("title") or alert.get("alert_key") or "Observer 提示")
    explanation = _html_text(alert.get("explanation"))
    return (
        f'<article class="alert tone-border-{tone}" data-health="{escape(tone)}">'
        f'<div class="alert-title"><span class="tone-text-{tone}" aria-hidden="true">{icon}</span> {title}</div>'
        f'<div class="muted">{_html_text(severity.upper())}</div>'
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
            '<section class="panel project-map"><h2>Project Narrative / 项目地图</h2>'
            '<div class="semantic-notice"><strong>○ 尚未生成项目级叙事</strong>'
            '<p>Observer 仍可展示当前 Workstream 和 Timeline；缺少足够 authority 时不会为了填满项目地图而推造历史。</p></div></section>'
        )
    stale_notice = ""
    if status == "stale":
        stale_notice = (
            '<div class="semantic-notice tone-border-warning"><strong>▲ Project Narrative 已陈旧</strong>'
            '<p>底层项目 authority 已变化；旧项目地图仅保留为可追溯解释，不再当作当前事实。</p></div>'
        )
    confidence = str(narrative.get("confidence") or "unknown")
    overall = narrative.get("overall_goal") if isinstance(narrative.get("overall_goal"), dict) else {}
    architecture = narrative.get("architecture") if isinstance(narrative.get("architecture"), dict) else {}
    nodes = [row for row in architecture.get("nodes") or [] if isinstance(row, dict)]
    edges = [row for row in architecture.get("edges") or [] if isinstance(row, dict)]
    milestones = [row for row in narrative.get("milestones") or [] if isinstance(row, dict)]
    current_position = narrative.get("current_position") if isinstance(narrative.get("current_position"), dict) else {}
    current_milestone = str(current_position.get("milestone_id") or "")

    node_html = "".join(
        (
            f'<article class="map-node tone-border-{_narrative_tone(row.get("status"))}">'
            f'<div class="map-node-head"><strong>{_html_text(row.get("title"))}</strong>'
            f'<span class="badge tone-{_narrative_tone(row.get("status"))}">{_html_text(row.get("status"))}</span></div>'
            f'<div class="canonical"><code>{_html_text(row.get("id"))}</code> · {_html_text(row.get("category"))}</div>'
            f'<p>{_html_text(row.get("summary"))}</p><details><summary>Provenance</summary>'
            f'<div class="provenance-list">{_narrative_provenance_html(row.get("provenance"))}</div></details></article>'
        )
        for row in nodes
    ) or '<p class="muted">暂无 architecture node。</p>'
    edge_html = "".join(
        (
            '<li class="map-edge">'
            f'<code>{_html_text(row.get("from"))}</code> <span aria-hidden="true">→</span> '
            f'<code>{_html_text(row.get("to"))}</code> · <strong>{_html_text(row.get("relation"))}</strong>'
            f'<span>{_html_text(row.get("summary"))}</span>'
            f'<details><summary>Provenance</summary>{_narrative_provenance_html(row.get("provenance"))}</details></li>'
        )
        for row in edges
    ) or '<li class="muted">暂无 architecture edge。</li>'
    milestone_html = "".join(
        (
            f'<article class="milestone {_narrative_tone(row.get("status"))} '
            f'{"is-current" if str(row.get("id") or "") == current_milestone else ""}">'
            f'<div class="milestone-marker" aria-hidden="true">{"●" if str(row.get("id") or "") == current_milestone else "○"}</div>'
            '<div class="milestone-body">'
            f'<div class="map-node-head"><strong>{_html_text(row.get("title"))}</strong>'
            f'<span class="badge tone-{_narrative_tone(row.get("status"))}">{_html_text(row.get("status"))}</span></div>'
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
    <div class="section-heading"><div><h2>Project Narrative / 项目地图</h2><p class="muted">长期逻辑骨架，与最近事件 Timeline 分离。</p></div><span class="badge tone-{_narrative_tone(status)}">{_html_text(status)} · v{_html_text(narrative.get('narrative_version'))}</span></div>
    {stale_notice}
    <section class="goal-card"><h3>Overall Goal / 整体目标</h3><p>{_html_text(overall.get('summary'))}</p><div class="provenance-list">{_narrative_provenance_html(overall.get('provenance'))}</div></section>
    <section class="map-section"><h3>Architecture Map / 架构地图</h3><div class="architecture-grid">{node_html}</div><ul class="architecture-edges">{edge_html}</ul></section>
    <section class="map-section"><h3>Logical Milestone Flow / Project Evolution</h3><div class="milestone-flow">{milestone_html}</div></section>
    <section class="current-position tone-border-active"><h3>Current Position / 当前所在位置</h3><p><code>{_html_text(current_milestone)}</code> · {_html_text(current_position.get('summary'))}</p><p><strong>下一步逻辑：</strong>{_html_text(current_position.get('next_logic'))}</p><div class="provenance-list">{_narrative_provenance_html(current_position.get('provenance'))}</div></section>
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
    rows = [row for row in runs or [] if isinstance(row, dict)] if isinstance(runs, list) else []
    if not rows:
        return '<p class="muted">暂无可归属到该已注册自动任务的 run history。</p>'
    body: list[str] = []
    for row in reversed(rows[-12:]):
        duration = row.get("duration_seconds")
        lower_bound = row.get("lower_bound_duration_seconds")
        if isinstance(duration, (int, float)):
            duration_text = f"{duration:.1f}s"
        elif isinstance(lower_bound, (int, float)):
            duration_text = f"≥ {lower_bound:.1f}s (lower bound)"
        else:
            duration_text = "unknown"
        body.append(
            '<article class="target-run">'
            f'<div><strong>{_html_text(row.get("status"))}</strong> · '
            f'<code>{_html_text(row.get("run_id"))}</code></div>'
            f'<div class="muted">start: {_html_text(_dashboard_display_time(row.get("started_at")))} · '
            f'end: {_html_text(_dashboard_display_time(row.get("finished_at")), "—")} · '
            f'last activity: {_html_text(_dashboard_display_time(row.get("last_activity_at")), "—")} · '
            f'duration: {_html_text(duration_text)}</div>'
            f'<div>phase: <code>{_html_text(row.get("phase"))}</code> · outcome: '
            f'{_html_text(row.get("major_outcome"), "—")}</div>'
            '</article>'
        )
    return "".join(body)


def _target_semantic_story_html(view: dict[str, object]) -> tuple[str, str, set[str]]:
    semantic = view.get("semantic_review") if isinstance(view.get("semantic_review"), dict) else {}
    status = str(semantic.get("semantic_status") or "not_reviewed")
    review = semantic.get("current_review") if isinstance(semantic.get("current_review"), dict) else {}
    patch = semantic.get("active_transient_patch") if isinstance(semantic.get("active_transient_patch"), dict) else {}
    density = str(patch.get("density") or "balanced")
    emphasis = {str(item) for item in patch.get("emphasize_sections") or []}
    if status != "current" or not review:
        label = "Target Narrative 尚未复核" if status == "not_reviewed" else "Target Narrative 已陈旧"
        return (
            f'<section class="target-story"><div class="semantic-notice tone-border-warning"><strong>▲ {_html_text(label)}</strong>'
            '<p>当前 Dashboard 不会把旧路线语义伪装成最新事实；请先完成 target-local Map Review。</p></div></section>',
            density,
            emphasis,
        )
    narrative = review.get("narrative") if isinstance(review.get("narrative"), dict) else {}
    problems = [row for row in review.get("problems") or [] if isinstance(row, dict)]
    proof_html = "".join(f"<li>{_html_text(item)}</li>" for item in narrative.get("recent_proof") or [])
    route_nodes = "".join(
        f'<article class="route-node"><strong>{_html_text(row.get("title"))}</strong><span class="badge tone-{_narrative_tone(row.get("status"))}">{_html_text(row.get("status"))}</span><p>{_html_text(row.get("summary"))}</p></article>'
        for row in narrative.get("route_nodes") or [] if isinstance(row, dict)
    ) or '<p class="muted">当前复核没有结构化 route node。</p>'
    problem_html = "".join(
        f'<article class="problem-card tone-border-{("critical" if row.get("blocking_impact") in {"blocks_task", "blocks_current_step"} else "warning")} "><strong>{_html_text(row.get("title"))}</strong><p>{_html_text(row.get("summary"))}</p><div class="muted">处理者：{_html_text(row.get("handler"))} · 计划影响：{_html_text(row.get("plan_impact"))} · 状态：{_html_text(row.get("status"))}</div></article>'
        for row in problems
    ) or '<p class="muted">当前复核没有需要单列的问题。</p>'
    presentation_type = patch.get("presentation_type") or review.get("presentation_type")
    patch_notice = (
        f'<div class="semantic-notice"><strong>临时展示调整：{_html_text(patch.get("patch_id"))}</strong>'
        f'<p>{_html_text(patch.get("reviewed_intent"))}</p></div>' if patch else ""
    )
    def story_section(key: str, title: str, body: str) -> str:
        emphasized = " is-emphasized" if key in emphasis else ""
        return f'<section class="story-section{emphasized}" data-story-section="{escape(key)}"><h4>{_html_text(title)}</h4>{body}</section>'
    return (
        '<section class="target-story">'
        f'<div class="section-heading"><div><h3>目标、路线与当前决策</h3><p class="muted">当前 Map Review：<code>{_html_text(review.get("review_id"))}</code></p></div><span class="badge tone-active">{_html_text(presentation_type)}</span></div>'
        f'{patch_notice}<div class="story-grid">'
        f'{story_section("goal", "最终目标", f"<p>{_html_text(narrative.get("overall_goal"))}</p>")}'
        f'{story_section("route", "完整路线", f"<p>{_html_text(narrative.get("route_summary"))}</p><div class=\"route-grid\">{route_nodes}</div>")}'
        f'{story_section("current_position", "当前位置", f"<p>{_html_text(narrative.get("current_position"))}</p><p><strong>为什么现在做：</strong>{_html_text(narrative.get("why_now"))}</p>")}'
        f'{story_section("recent_proof", "最近证明 / 排除 / 改变", f"<ul>{proof_html}</ul>")}'
        f'{story_section("problems", "当前问题与计划影响", problem_html)}'
        f'{story_section("next_logic", "下一步及理由", f"<p>{_html_text(narrative.get("next_logic"))}</p>")}'
        '</div></section>',
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
    alerts_html = "".join(_dashboard_alert_html(row) for row in scoped_alerts) or '<p class="muted">该 target 当前没有 Alert。</p>'
    timeline = _target_timeline_html(view, machine_events, interpretations)
    story_html, density, emphasis = _target_semantic_story_html(view)
    route_ref = target.get("route_ref")
    route_html = f' · route <code>{_html_text(route_ref)}</code>' if route_ref else ""
    return f"""
  <section class="target-panel {'is-active' if active else ''} density-{escape(density, quote=True)}" data-target-panel="{escape(target_id, quote=True)}">
    <div class="section-heading"><div><h2>{_html_text(target.get('title'))}</h2>
    <p class="muted"><code>{_html_text(target_id)}</code> · {_html_text(target.get('mode'))} · automation <code>{_html_text(target.get('automation_ref'))}</code>{route_html}</p></div>
    <span class="badge tone-active">registered target</span></div>
    {story_html}
    <section class="target-subsection"><h3>当前执行范围</h3><div class="workstream-list">{cards}</div></section>
    <section class="target-subsection {'is-emphasized' if 'runs' in emphasis else ''}"><h3>Run chain / 自动任务运行历史</h3>{_target_run_chain_html(view.get('runs'))}</section>
    <section class="target-subsection {'is-emphasized' if 'alerts' in emphasis else ''}"><h3>Target Alerts</h3>{alerts_html}</section>
    <section class="target-subsection"><h3>Target Timeline</h3>{timeline}</section>
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
            '<div class="target-tabs" role="tablist"><span class="muted">No registered targets</span></div>',
            '<section class="panel"><div class="semantic-notice"><strong>○ 尚未注册 Observer target</strong>'
            '<p>Dashboard 不会把 Workstream/worktree 的存在自动当成用户要观察的 Scheduled Task。请先通过正式 Target Registry 注册目标。</p></div></section>',
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
    alerts = target_alerts
    self_alerts = [row for row in safe_self_alerts if isinstance(row, dict)] if isinstance(safe_self_alerts, list) else []
    all_alerts = self_alerts + alerts
    current_data_age = safe_status.get("data_age") if isinstance(safe_status.get("data_age"), dict) else {}
    target_state = safe_current.get("targets") if isinstance(safe_current.get("targets"), dict) else {}
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
    alerts_html = "".join(_dashboard_alert_html(row) for row in all_alerts) or '<p class="muted">当前没有需要关注的 Alert。</p>'
    overview = target_state.get("project_overview") if isinstance(target_state.get("project_overview"), dict) else {}
    overview_decision = str(overview.get("decision") or "undecided")
    if overview_decision == "enabled":
        project_map_html = _project_narrative_html(safe_current)
    elif overview_decision == "disabled":
        project_map_html = (
            '<section class="panel"><div class="semantic-notice"><strong>Project Overview disabled by authority decision</strong>'
            f'<p>{_html_text(overview.get("reason"))}</p><div class="provenance-list">{_narrative_provenance_html(overview.get("evidence_refs"))}</div></div></section>'
        )
    else:
        project_map_html = (
            '<section class="panel"><div class="semantic-notice"><strong>Project Overview 尚未决策</strong>'
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
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.62 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}} a{{color:var(--blue)}} code{{font:12.5px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;color:#344054}} .page{{max-width:1280px;margin:auto;padding:24px}} h1{{font-size:24px;line-height:1.25;margin:0 0 4px}} h2{{font-size:19px;margin:0 0 14px}} h3{{font-size:17px;margin:0}} h4{{font-size:14px;margin:0 0 6px}} p{{margin:6px 0 12px}} ul{{margin:6px 0 12px;padding-left:20px}} .muted{{color:var(--muted)}} .canonical{{color:var(--muted);font-size:13px;margin-top:4px}} .top,.section-heading{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}} .top{{margin-bottom:18px}} .summary-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0 22px}} .metric,.panel,.workstream-card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}} .metric{{padding:14px}} .metric strong{{display:block;font-size:18px;margin-top:3px}} .panel{{padding:18px;margin:0 0 18px}} .toolbar{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}} input,select{{font:inherit;border:1px solid var(--line);border-radius:8px;background:#fff;padding:8px 10px;min-height:38px}} input{{flex:1;min-width:220px}} .workstream-list{{display:grid;gap:14px}} .workstream-card{{padding:18px}} .card-header{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}} .badge-row{{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}} .badge{{display:inline-flex;align-items:center;gap:4px;border:1px solid currentColor;border-radius:999px;padding:2px 8px;font-size:12.5px;white-space:nowrap}} .tone-critical,.tone-text-critical{{color:var(--red)}} .tone-warning,.tone-text-warning{{color:var(--amber)}} .tone-healthy{{color:var(--green)}} .tone-active{{color:var(--blue)}} .tone-maintenance{{color:#6941c6}} .tone-muted{{color:var(--muted)}} .tone-border-critical{{border-left:4px solid var(--red)!important}} .tone-border-warning{{border-left:4px solid var(--amber)!important}} .tone-border-healthy{{border-left:4px solid var(--green)!important}} .tone-border-active{{border-left:4px solid var(--blue)!important}} .tone-border-maintenance{{border-left:4px solid #6941c6!important}} .tone-border-muted{{border-left:4px solid #98a2b3!important}} .semantic-notice{{background:var(--gray-bg);border-radius:8px;padding:9px 11px;margin:12px 0;font-size:13px}} .logic-grid,.technical-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 18px;margin-top:14px}} .logic-grid section{{border-top:1px solid var(--line);padding-top:10px}} .span-two{{grid-column:1/-1}} details{{border-top:1px solid var(--line);margin-top:14px;padding-top:10px}} summary{{cursor:pointer;font-weight:600;color:#344054}} .breakable{{word-break:break-all}} .alert{{border:1px solid var(--line);border-radius:9px;padding:12px 14px;margin:9px 0;background:#fff}} .alert-title{{font-weight:700}} .timeline-item{{display:grid;grid-template-columns:160px 1fr;gap:14px;border-left:2px solid var(--line);padding:5px 0 14px 14px;margin-left:5px}} .timeline-item time{{font-size:12.5px;color:var(--muted)}} .semantic-event{{border-left-color:var(--blue)}} .glossary-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}} .glossary-item{{border:1px solid var(--line);border-radius:8px;padding:12px}} .project-map{{border-top:3px solid #4f46e5}} .goal-card{{background:#eef2ff;border:1px solid #c7d2fe;border-radius:10px;padding:14px;margin:12px 0 18px}} .map-section{{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}} .architecture-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:12px}} .map-node{{border:1px solid var(--line);border-radius:9px;padding:12px;background:#fff}} .map-node-head{{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}} .architecture-edges{{list-style:none;padding:0;margin:12px 0}} .map-edge{{display:grid;grid-template-columns:auto auto auto 1fr;gap:8px;align-items:center;border-top:1px dashed var(--line);padding:8px 0}} .milestone-flow{{display:grid;gap:0;margin-top:12px}} .milestone{{display:grid;grid-template-columns:28px 1fr;gap:10px;position:relative;padding-bottom:15px}} .milestone:not(:last-child)::before{{content:"";position:absolute;left:8px;top:22px;bottom:0;border-left:2px solid var(--line)}} .milestone-marker{{font-size:16px;color:#98a2b3;z-index:1;background:var(--surface)}} .milestone.is-current .milestone-marker{{color:var(--blue)}} .milestone.is-current .milestone-body{{background:var(--blue-bg);border-color:#b2d4ff}} .milestone-body{{border:1px solid var(--line);border-radius:9px;padding:11px 13px}} .flow-meta{{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);font-size:12.5px}} .current-position{{margin-top:14px;background:var(--blue-bg);border:1px solid #b2d4ff;border-radius:9px;padding:13px}} .provenance-list{{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}} .provenance-ref{{background:var(--gray-bg);border-radius:4px;padding:2px 5px}} .target-tabs{{display:flex;gap:8px;flex-wrap:wrap}} .target-tab{{font:inherit;border:1px solid var(--line);background:#fff;color:var(--text);border-radius:999px;padding:7px 12px;cursor:pointer}} .target-tab.is-active{{border-color:#1769d2;background:var(--blue-bg);color:var(--blue);font-weight:700}} .target-panel{{display:none}} .target-panel.is-active{{display:block}} .target-subsection{{border-top:1px solid var(--line);padding-top:14px;margin-top:16px}} .target-run{{border-left:3px solid #98a2b3;padding:8px 12px;margin:8px 0;background:var(--gray-bg);border-radius:0 8px 8px 0}} .target-story{{border:1px solid var(--line);border-radius:10px;padding:14px;margin-top:14px;background:#fbfcfe}} .story-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}} .story-section{{border:1px solid var(--line);border-radius:8px;padding:11px;background:#fff}} .story-section.is-emphasized,.target-subsection.is-emphasized{{border-left:4px solid var(--blue);background:var(--blue-bg)}} .route-grid{{display:grid;gap:7px;margin-top:8px}} .route-node{{border-left:3px solid #98a2b3;padding:7px 9px;background:var(--gray-bg)}} .route-node .badge{{float:right}} .problem-card{{border:1px solid var(--line);border-radius:7px;padding:8px 10px;margin:6px 0}} .density-compact .target-story,.density-compact .story-section{{padding:8px}} .density-detailed .story-grid{{gap:14px}} .hidden{{display:none!important}} .empty{{padding:18px;color:var(--muted);text-align:center}} footer{{color:var(--muted);font-size:12.5px;padding:6px 0 20px}}
@media(max-width:760px){{.page{{padding:14px}}.top,.section-heading,.card-header{{display:block}}.summary-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.logic-grid,.technical-grid,.glossary-grid,.architecture-grid,.story-grid{{grid-template-columns:1fr}}.span-two{{grid-column:auto}}.badge-row{{justify-content:flex-start;margin-top:10px}}.timeline-item{{grid-template-columns:1fr;gap:2px}}.map-edge{{grid-template-columns:auto auto auto;align-items:start}}.map-edge>span:last-of-type{{grid-column:1/-1}}}}
</style>
</head>
<body>
<main class="page">
  <header class="top"><div><h1>{_html_text(title)}</h1><div class="muted">最后观察：{_html_text(_dashboard_display_time(safe_current.get('observed_at')))} · 数据状态：{_html_text(current_data_age.get('state'))}</div></div><div class="badge tone-{_html_text(overall)}"><span aria-hidden="true">{health_icon}</span> Overall Health：{_html_text(health_label)}</div></header>
  <section class="summary-grid" aria-label="项目总览">
    <div class="metric"><span class="muted">Registered targets</span><strong>{len(target_views)}</strong></div>
    <div class="metric"><span class="muted">当前 Alerts</span><strong>{len(all_alerts)}</strong></div>
    <div class="metric"><span class="muted">Observer data age</span><strong>{_html_text(current_data_age.get('state'))}</strong></div>
    <div class="metric"><span class="muted">Semantic coverage</span><strong>{_html_text((safe_current.get('semantic') or {}).get('status') if isinstance(safe_current.get('semantic'),dict) else None)}</strong></div>
  </section>
  {project_map_html}
  <section class="panel target-navigation"><div class="section-heading"><div><h2>Observer Targets</h2><p class="muted">仅展示 Target Registry 中显式注册的 scheduled-automation targets。</p></div></div>{target_tabs_html}</section>
  {target_pages_html}
  <section class="panel"><h2>最近重大进展</h2><ul>{latest_html}</ul></section>
  <section class="panel" id="alerts"><h2>当前 Alerts</h2>{alerts_html}</section>
  <section class="panel"><h2>Semantic Glossary</h2><div class="glossary-grid" id="glossary">{glossary_html}</div></section>
  <footer>Observer 只解释本地事实，不参与 Writer control plane。Dashboard 为静态自包含文件，不需要 HTTP 服务。页面时间统一显示北京时间 (UTC+08:00)，底层 canonical state/history 仍使用 UTC。</footer>
</main>
<script id="observer-data" type="application/json">{embedded_json}</script>
<script>
(()=>{{document.querySelectorAll('[data-target-tab]').forEach(tab=>tab.addEventListener('click',()=>{{const id=tab.dataset.targetTab;document.querySelectorAll('[data-target-tab]').forEach(item=>item.classList.toggle('is-active',item===tab));document.querySelectorAll('[data-target-panel]').forEach(panel=>panel.classList.toggle('is-active',panel.dataset.targetPanel===id));}}));}})();
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
        ("narratives", "project_narratives", "interpreted_at"),
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
        "narratives": ("project_narratives", "narrative_id", "interpreted_at"),
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
        ("project_narratives", "narratives", "interpreted_at", "narrative_id"),
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
