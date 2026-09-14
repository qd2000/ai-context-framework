"""Observer V2 target semantic-review and presentation-maintenance state.

This module owns only user-level derived Observer state under ``observer_dir``.
It deliberately does not modify project Markdown/Git state and does not acquire
Writer continuation ownership.  The semantic content itself is supplied by an
Agent after authority review; ACF only validates identity, lifecycle,
concurrency, source fingerprints, and audit history.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any

from ai_context_framework.automation_contracts import (
    OBSERVER_PRIMARY_VISUALIZATION_KINDS,
    OBSERVER_PRESENTATION_TYPES,
    OBSERVER_SEMANTIC_REVIEW_DECISIONS,
)
from ai_context_framework.observability import atomic_write_text
from ai_context_framework.observer_storage import (
    SEMANTIC_SENSITIVE_VALUE_RE,
    SemanticSensitiveValueError,
)


OBSERVER_PRESENTATION_STATE_SCHEMA = "acf.observer.presentation-state.v1"
OBSERVER_PRESENTATION_TARGET_SCHEMA = "acf.observer.presentation-target.v1"
OBSERVER_SEMANTIC_REVIEW_STATE_SCHEMA = "acf.observer.semantic-review-state.v1"
OBSERVER_PRESENTATION_REQUEST_SCHEMA = "acf.observer.presentation-request.v1"
OBSERVER_PRESENTATION_RULE_SCHEMA = "acf.observer.presentation-rule.v1"
OBSERVER_TRANSIENT_PATCH_SCHEMA = "acf.observer.transient-presentation-patch.v1"
OBSERVER_PRESENTATION_EVENT_SCHEMA = "acf.observer.presentation-event.v1"
OBSERVER_TARGET_NARRATIVE_SCHEMA = "acf.observer.target-narrative.v1"
OBSERVER_TARGET_PROBLEM_SCHEMA = "acf.observer.target-problem.v1"
OBSERVER_PRIMARY_VISUALIZATION_SCHEMA = "acf.observer.primary-visualization.v1"

_TARGET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_RUNTIME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

PROBLEM_EXPECTEDNESS = {"expected", "unexpected", "unknown"}
PROBLEM_HANDLERS = {"agent_self", "human_approval", "human_action", "external_system", "other_project"}
PROBLEM_SCOPE_RELATIONS = {
    "in_scope",
    "cross_cutting",
    "out_of_scope",
    "tooling_dependency",
    "external_dependency",
}
PROBLEM_BLOCKING_IMPACTS = {"non_blocking", "degrading", "blocks_current_step", "blocks_task"}
PROBLEM_PLAN_IMPACTS = {"none", "local_adjustment", "route_change", "major_replan"}
PROBLEM_STATUSES = {
    "detected",
    "investigating",
    "working",
    "waiting",
    "transferred",
    "deferred",
    "resolved",
}
TRANSIENT_PRESENTATION_DENSITIES = {"compact", "balanced", "detailed"}
TRANSIENT_EMPHASIS_SECTIONS = {
    "goal",
    "route",
    "current_position",
    "recent_proof",
    "problems",
    "next_logic",
    "runs",
    "alerts",
}
PRIMARY_VISUALIZATION_KINDS = set(OBSERVER_PRIMARY_VISUALIZATION_KINDS)
PRIMARY_VISUALIZATION_CONFIDENCE = {"high", "medium", "low"}
PRIMARY_VISUALIZATION_DIRECTIONS = {"minimize", "maximize", "neutral"}


class ObserverPresentationError(ValueError):
    """Raised when target semantic/presentation runtime state is invalid."""


class ObserverPresentationConcurrencyError(ObserverPresentationError):
    def __init__(self, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__("observer_presentation_revision_changed")


class ObserverPresentationSourceMismatch(ObserverPresentationError):
    def __init__(self, expected: str, current: str):
        self.expected = expected
        self.current = current
        super().__init__("observer_target_semantic_source_changed")


class ObserverPresentationViewChanged(ObserverPresentationError):
    def __init__(
        self,
        expected_revision: int,
        current_revision: int,
        expected_fingerprint: str,
        current_fingerprint: str,
    ):
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        self.expected_fingerprint = expected_fingerprint
        self.current_fingerprint = current_fingerprint
        super().__init__("observer_presentation_view_changed")


class ObserverPresentationSemanticEscalationRequired(ObserverPresentationError):
    def __init__(self, signals: list[str]):
        self.signals = signals
        super().__init__("observer_presentation_semantic_escalation_required")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _stable_digest(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validated_text(value: object, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ObserverPresentationError(f"observer {field} is required")
        return None
    if not isinstance(value, str):
        raise ObserverPresentationError(f"observer {field} must be text")
    cleaned = value.strip()
    if not cleaned:
        if required:
            raise ObserverPresentationError(f"observer {field} is required")
        return None
    if SEMANTIC_SENSITIVE_VALUE_RE.search(cleaned):
        raise SemanticSensitiveValueError(f"sensitive credential-like value refused in observer {field}")
    return cleaned


def _validated_refs(values: object, field: str, *, required: bool = False) -> list[str]:
    if values is None:
        values = []
    if not isinstance(values, list):
        raise ObserverPresentationError(f"observer {field} must be a list")
    refs: list[str] = []
    for value in values:
        cleaned = _validated_text(value, field, required=True)
        assert cleaned is not None
        refs.append(cleaned)
    refs = list(dict.fromkeys(refs))
    if required and not refs:
        raise ObserverPresentationError(f"observer {field} requires at least one reference")
    return refs


def _validated_target_id(value: object) -> str:
    if not isinstance(value, str) or not _TARGET_ID_RE.fullmatch(value):
        raise ObserverPresentationError("observer presentation target_id is invalid")
    return value


def _validated_runtime_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _RUNTIME_ID_RE.fullmatch(value):
        raise ObserverPresentationError(f"observer {field} is invalid")
    return value


def observer_presentation_paths(project: Any) -> dict[str, Path]:
    root = Path(project.observer_dir) / "presentation"
    return {
        "root": root,
        "state": root / "state.json",
        "events": root / "events.jsonl",
    }


def _default_target_state(target_id: str) -> dict[str, object]:
    return {
        "schema_version": OBSERVER_PRESENTATION_TARGET_SCHEMA,
        "target_id": target_id,
        "revision": 0,
        "presentation_revision": 0,
        "updated_at": None,
        "current_review": None,
        "active_transient_patch": None,
        "one_shot_requests": [],
        "durable_rules": [],
    }


def _default_state(project: Any) -> dict[str, object]:
    return {
        "schema_version": OBSERVER_PRESENTATION_STATE_SCHEMA,
        "project_id": project.project_id,
        "revision": 0,
        "updated_at": None,
        "targets": {},
    }


def _validated_request(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ObserverPresentationError("observer one-shot request must be an object")
    request_id = _validated_runtime_id(value.get("request_id"), "request_id")
    target_id = _validated_target_id(value.get("target_id"))
    status = value.get("status")
    if status not in {"active", "consumed"}:
        raise ObserverPresentationError(f"observer one-shot request status is invalid: {status}")
    result = {
        "schema_version": OBSERVER_PRESENTATION_REQUEST_SCHEMA,
        "request_id": request_id,
        "target_id": target_id,
        "status": status,
        "reviewed_intent": _validated_text(value.get("reviewed_intent"), "reviewed_intent", required=True),
        "scope": _validated_text(value.get("scope"), "scope", required=True),
        "rationale": _validated_text(value.get("rationale"), "rationale", required=True),
        "evidence_refs": _validated_refs(value.get("evidence_refs"), "evidence_refs", required=True),
        "created_at": _validated_text(value.get("created_at"), "created_at", required=True),
        "consumed_at": _validated_text(value.get("consumed_at"), "consumed_at"),
        "consumed_by_review_id": _validated_text(value.get("consumed_by_review_id"), "consumed_by_review_id"),
    }
    if status == "active" and (result["consumed_at"] or result["consumed_by_review_id"]):
        raise ObserverPresentationError("active one-shot request cannot carry consumed metadata")
    if status == "consumed" and not result["consumed_by_review_id"]:
        raise ObserverPresentationError("consumed one-shot request requires consumed_by_review_id")
    return result


def _validated_rule(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ObserverPresentationError("observer durable rule must be an object")
    rule_id = _validated_runtime_id(value.get("rule_id"), "rule_id")
    target_id = _validated_target_id(value.get("target_id"))
    status = value.get("status")
    if status not in {"active", "superseded", "withdrawn"}:
        raise ObserverPresentationError(f"observer durable rule status is invalid: {status}")
    result = {
        "schema_version": OBSERVER_PRESENTATION_RULE_SCHEMA,
        "rule_id": rule_id,
        "target_id": target_id,
        "status": status,
        "reviewed_intent": _validated_text(value.get("reviewed_intent"), "reviewed_intent", required=True),
        "scope": _validated_text(value.get("scope"), "scope", required=True),
        "rationale": _validated_text(value.get("rationale"), "rationale", required=True),
        "evidence_refs": _validated_refs(value.get("evidence_refs"), "evidence_refs", required=True),
        "created_at": _validated_text(value.get("created_at"), "created_at", required=True),
        "supersedes": _validated_text(value.get("supersedes"), "supersedes"),
        "superseded_by": _validated_text(value.get("superseded_by"), "superseded_by"),
        "withdrawn_at": _validated_text(value.get("withdrawn_at"), "withdrawn_at"),
        "withdraw_reason": _validated_text(value.get("withdraw_reason"), "withdraw_reason"),
    }
    return result


def _validated_transient_patch(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ObserverPresentationError("observer transient presentation patch must be an object")
    target_id = _validated_target_id(value.get("target_id"))
    density = value.get("density")
    if density not in TRANSIENT_PRESENTATION_DENSITIES:
        raise ObserverPresentationError(f"observer transient presentation density is invalid: {density}")
    presentation_type = value.get("presentation_type")
    if presentation_type is not None and presentation_type not in OBSERVER_PRESENTATION_TYPES:
        raise ObserverPresentationError(
            f"observer transient presentation_type is invalid: {presentation_type}"
        )
    emphasis = value.get("emphasize_sections") or []
    if not isinstance(emphasis, list):
        raise ObserverPresentationError("observer transient emphasize_sections must be a list")
    normalized_emphasis: list[str] = []
    for item in emphasis:
        if item not in TRANSIENT_EMPHASIS_SECTIONS:
            raise ObserverPresentationError(f"observer transient emphasis section is invalid: {item}")
        if item not in normalized_emphasis:
            normalized_emphasis.append(item)
    return {
        "schema_version": OBSERVER_TRANSIENT_PATCH_SCHEMA,
        "patch_id": _validated_runtime_id(value.get("patch_id"), "patch_id"),
        "target_id": target_id,
        "reviewed_intent": _validated_text(value.get("reviewed_intent"), "reviewed_intent", required=True),
        "scope": _validated_text(value.get("scope"), "scope", required=True),
        "rationale": _validated_text(value.get("rationale"), "rationale", required=True),
        "evidence_refs": _validated_refs(value.get("evidence_refs"), "evidence_refs", required=True),
        "created_at": _validated_text(value.get("created_at"), "created_at", required=True),
        "base_review_id": _validated_runtime_id(value.get("base_review_id"), "base_review_id"),
        "density": density,
        "presentation_type": presentation_type,
        "emphasize_sections": normalized_emphasis,
    }


def _validated_problem(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ObserverPresentationError("observer target problem must be an object")
    problem_id = _validated_runtime_id(value.get("problem_id"), "problem_id")
    result = {
        "schema_version": OBSERVER_TARGET_PROBLEM_SCHEMA,
        "problem_id": problem_id,
        "title": _validated_text(value.get("title"), "problem.title", required=True),
        "summary": _validated_text(value.get("summary"), "problem.summary", required=True),
        "expectedness": value.get("expectedness"),
        "handler": value.get("handler"),
        "scope_relation": value.get("scope_relation"),
        "blocking_impact": value.get("blocking_impact"),
        "plan_impact": value.get("plan_impact"),
        "status": value.get("status"),
        "route_ref": _validated_text(value.get("route_ref"), "problem.route_ref"),
        "node_ref": _validated_text(value.get("node_ref"), "problem.node_ref"),
        "transfer_ref": _validated_text(value.get("transfer_ref"), "problem.transfer_ref"),
        "evidence_refs": _validated_refs(value.get("evidence_refs"), "problem.evidence_refs", required=True),
    }
    enum_checks = (
        ("expectedness", PROBLEM_EXPECTEDNESS),
        ("handler", PROBLEM_HANDLERS),
        ("scope_relation", PROBLEM_SCOPE_RELATIONS),
        ("blocking_impact", PROBLEM_BLOCKING_IMPACTS),
        ("plan_impact", PROBLEM_PLAN_IMPACTS),
        ("status", PROBLEM_STATUSES),
    )
    for field, allowed in enum_checks:
        if result[field] not in allowed:
            raise ObserverPresentationError(f"observer problem {field} is invalid: {result[field]}")
    if result["handler"] == "other_project" and not result["transfer_ref"]:
        raise ObserverPresentationError("observer other_project problem requires transfer_ref")
    return result


def _validated_graph_visualization_spec(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ObserverPresentationError(f"observer {field} must be an object")
    raw_nodes = value.get("nodes") or []
    raw_edges = value.get("edges") or []
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ObserverPresentationError(f"observer {field}.nodes requires at least one item")
    if not isinstance(raw_edges, list):
        raise ObserverPresentationError(f"observer {field}.edges must be a list")
    nodes: list[dict[str, object]] = []
    node_ids: set[str] = set()
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            raise ObserverPresentationError(f"observer {field}.nodes[{index}] must be an object")
        node_id = _validated_runtime_id(raw.get("id"), f"{field}.nodes[{index}].id")
        if node_id in node_ids:
            raise ObserverPresentationError(f"observer {field} duplicate node id: {node_id}")
        node_ids.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "title": _validated_text(raw.get("title"), f"{field}.nodes[{index}].title", required=True),
                "status": _validated_text(raw.get("status"), f"{field}.nodes[{index}].status", required=True),
                "summary": _validated_text(raw.get("summary"), f"{field}.nodes[{index}].summary", required=True),
                "evidence_refs": _validated_refs(
                    raw.get("evidence_refs"),
                    f"{field}.nodes[{index}].evidence_refs",
                    required=True,
                ),
            }
        )
    edges: list[dict[str, object]] = []
    for index, raw in enumerate(raw_edges):
        if not isinstance(raw, dict):
            raise ObserverPresentationError(f"observer {field}.edges[{index}] must be an object")
        source = _validated_runtime_id(raw.get("from"), f"{field}.edges[{index}].from")
        target = _validated_runtime_id(raw.get("to"), f"{field}.edges[{index}].to")
        if source not in node_ids or target not in node_ids:
            raise ObserverPresentationError(f"observer {field} edge references an unknown node")
        edges.append(
            {
                "from": source,
                "to": target,
                "label": _validated_text(raw.get("label"), f"{field}.edges[{index}].label"),
                "evidence_refs": _validated_refs(
                    raw.get("evidence_refs"),
                    f"{field}.edges[{index}].evidence_refs",
                ),
            }
        )
    result: dict[str, object] = {"nodes": nodes, "edges": edges}
    for ref_field in ("current_node_refs", "next_node_refs"):
        if ref_field not in value:
            continue
        refs = _validated_refs(value.get(ref_field), f"{field}.{ref_field}")
        unknown = [ref for ref in refs if ref not in node_ids]
        if unknown:
            raise ObserverPresentationError(
                f"observer {field}.{ref_field} references an unknown node: {unknown[0]}"
            )
        result[ref_field] = refs
    return result


def _validated_metric_trend_spec(value: object) -> dict[str, object]:
    field = "primary_visualization.spec"
    if not isinstance(value, dict):
        raise ObserverPresentationError(f"observer {field} must be an object")
    direction = value.get("direction") or "neutral"
    if direction not in PRIMARY_VISUALIZATION_DIRECTIONS:
        raise ObserverPresentationError(f"observer metric_trend direction is invalid: {direction}")
    raw_series = value.get("series") or []
    if not isinstance(raw_series, list) or not raw_series:
        raise ObserverPresentationError("observer metric_trend series requires at least one item")
    series: list[dict[str, object]] = []
    series_ids: set[str] = set()
    for series_index, raw in enumerate(raw_series):
        if not isinstance(raw, dict):
            raise ObserverPresentationError(
                f"observer metric_trend series[{series_index}] must be an object"
            )
        series_id = _validated_runtime_id(raw.get("id"), f"metric_trend.series[{series_index}].id")
        if series_id in series_ids:
            raise ObserverPresentationError(f"observer metric_trend duplicate series id: {series_id}")
        series_ids.add(series_id)
        raw_points = raw.get("points") or []
        if not isinstance(raw_points, list) or not raw_points:
            raise ObserverPresentationError(
                f"observer metric_trend series[{series_index}].points requires at least one item"
            )
        points: list[dict[str, object]] = []
        for point_index, raw_point in enumerate(raw_points):
            if not isinstance(raw_point, dict):
                raise ObserverPresentationError(
                    f"observer metric_trend series[{series_index}].points[{point_index}] must be an object"
                )
            x_value = raw_point.get("x")
            if isinstance(x_value, bool) or not isinstance(x_value, (int, float, str)):
                raise ObserverPresentationError("observer metric_trend point x must be finite number or text")
            if isinstance(x_value, (int, float)) and not isfinite(float(x_value)):
                raise ObserverPresentationError("observer metric_trend point x must be finite")
            if isinstance(x_value, str):
                x_value = _validated_text(x_value, "metric_trend.point.x", required=True)
            y_value = raw_point.get("y")
            if isinstance(y_value, bool) or not isinstance(y_value, (int, float)) or not isfinite(float(y_value)):
                raise ObserverPresentationError("observer metric_trend point y must be a finite number")
            points.append(
                {
                    "x": x_value,
                    "y": y_value,
                    "label": _validated_text(raw_point.get("label"), "metric_trend.point.label"),
                    "evidence_refs": _validated_refs(
                        raw_point.get("evidence_refs"),
                        "metric_trend.point.evidence_refs",
                        required=True,
                    ),
                }
            )
        series.append(
            {
                "id": series_id,
                "title": _validated_text(
                    raw.get("title"),
                    f"metric_trend.series[{series_index}].title",
                    required=True,
                ),
                "unit": _validated_text(raw.get("unit"), f"metric_trend.series[{series_index}].unit"),
                "points": points,
            }
        )
    return {
        "x_label": _validated_text(value.get("x_label"), f"{field}.x_label", required=True),
        "y_label": _validated_text(value.get("y_label"), f"{field}.y_label", required=True),
        "direction": direction,
        "series": series,
    }


def _validated_status_matrix_spec(value: object) -> dict[str, object]:
    field = "primary_visualization.spec"
    if not isinstance(value, dict):
        raise ObserverPresentationError(f"observer {field} must be an object")
    raw_items = value.get("items") or []
    if not isinstance(raw_items, list) or not raw_items:
        raise ObserverPresentationError("observer status_matrix items requires at least one item")
    items: list[dict[str, object]] = []
    item_ids: set[str] = set()
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise ObserverPresentationError(f"observer status_matrix items[{index}] must be an object")
        item_id = _validated_runtime_id(raw.get("id"), f"status_matrix.items[{index}].id")
        if item_id in item_ids:
            raise ObserverPresentationError(f"observer status_matrix duplicate item id: {item_id}")
        item_ids.add(item_id)
        items.append(
            {
                "id": item_id,
                "title": _validated_text(raw.get("title"), f"status_matrix.items[{index}].title", required=True),
                "status": _validated_text(raw.get("status"), f"status_matrix.items[{index}].status", required=True),
                "summary": _validated_text(raw.get("summary"), f"status_matrix.items[{index}].summary", required=True),
                "evidence_refs": _validated_refs(
                    raw.get("evidence_refs"),
                    f"status_matrix.items[{index}].evidence_refs",
                    required=True,
                ),
            }
        )
    current_refs = _validated_refs(value.get("current_item_refs"), "status_matrix.current_item_refs")
    unknown = [ref for ref in current_refs if ref not in item_ids]
    if unknown:
        raise ObserverPresentationError(
            f"observer status_matrix current_item_refs references an unknown item: {unknown[0]}"
        )
    return {"items": items, "current_item_refs": current_refs}


def _validated_primary_visualization(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ObserverPresentationError("observer primary_visualization must be an object")
    schema_version = value.get("schema_version")
    if schema_version != OBSERVER_PRIMARY_VISUALIZATION_SCHEMA:
        raise ObserverPresentationError(
            f"unsupported observer primary_visualization schema: {schema_version}"
        )
    kind = value.get("kind")
    if kind not in PRIMARY_VISUALIZATION_KINDS:
        raise ObserverPresentationError(f"observer primary_visualization kind is invalid: {kind}")
    confidence = value.get("confidence")
    if confidence is not None and confidence not in PRIMARY_VISUALIZATION_CONFIDENCE:
        raise ObserverPresentationError(
            f"observer primary_visualization confidence is invalid: {confidence}"
        )
    raw_spec = value.get("spec")
    if kind == "metric_trend":
        spec = _validated_metric_trend_spec(raw_spec)
    elif kind == "status_matrix":
        spec = _validated_status_matrix_spec(raw_spec)
    else:
        spec = _validated_graph_visualization_spec(raw_spec, field="primary_visualization.spec")
    result = {
        "schema_version": OBSERVER_PRIMARY_VISUALIZATION_SCHEMA,
        "kind": kind,
        "title": _validated_text(value.get("title"), "primary_visualization.title", required=True),
        "primary_progress_question": _validated_text(
            value.get("primary_progress_question"),
            "primary_visualization.primary_progress_question",
            required=True,
        ),
        "reason": _validated_text(value.get("reason"), "primary_visualization.reason", required=True),
        "evidence_refs": _validated_refs(
            value.get("evidence_refs"),
            "primary_visualization.evidence_refs",
            required=True,
        ),
        "spec": spec,
    }
    if confidence is not None:
        result["confidence"] = confidence
    return result


def _validated_narrative(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ObserverPresentationError("observer target narrative must be an object")
    recent_proof = value.get("recent_proof")
    if not isinstance(recent_proof, list) or not recent_proof:
        raise ObserverPresentationError("observer target narrative recent_proof requires at least one item")
    normalized_proof = [
        _validated_text(item, "target_narrative.recent_proof", required=True)
        for item in recent_proof
    ]
    route_nodes = value.get("route_nodes") or []
    route_edges = value.get("route_edges") or []
    if not isinstance(route_nodes, list) or not isinstance(route_edges, list):
        raise ObserverPresentationError("observer target narrative route_nodes/route_edges must be lists")
    nodes: list[dict[str, object]] = []
    node_ids: set[str] = set()
    for index, raw in enumerate(route_nodes):
        if not isinstance(raw, dict):
            raise ObserverPresentationError(f"observer target narrative route_nodes[{index}] must be an object")
        node_id = _validated_runtime_id(raw.get("id"), f"route_nodes[{index}].id")
        if node_id in node_ids:
            raise ObserverPresentationError(f"observer target narrative duplicate route node id: {node_id}")
        node_ids.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "title": _validated_text(raw.get("title"), f"route_nodes[{index}].title", required=True),
                "status": _validated_text(raw.get("status"), f"route_nodes[{index}].status", required=True),
                "summary": _validated_text(raw.get("summary"), f"route_nodes[{index}].summary", required=True),
                "evidence_refs": _validated_refs(raw.get("evidence_refs"), f"route_nodes[{index}].evidence_refs"),
            }
        )
    edges: list[dict[str, object]] = []
    for index, raw in enumerate(route_edges):
        if not isinstance(raw, dict):
            raise ObserverPresentationError(f"observer target narrative route_edges[{index}] must be an object")
        source = _validated_runtime_id(raw.get("from"), f"route_edges[{index}].from")
        target = _validated_runtime_id(raw.get("to"), f"route_edges[{index}].to")
        if source not in node_ids or target not in node_ids:
            raise ObserverPresentationError("observer target narrative route edge references an unknown node")
        edges.append(
            {
                "from": source,
                "to": target,
                "label": _validated_text(raw.get("label"), f"route_edges[{index}].label"),
            }
        )
    result = {
        "schema_version": OBSERVER_TARGET_NARRATIVE_SCHEMA,
        "overall_goal": _validated_text(value.get("overall_goal"), "target_narrative.overall_goal", required=True),
        "route_summary": _validated_text(value.get("route_summary"), "target_narrative.route_summary", required=True),
        "current_position": _validated_text(value.get("current_position"), "target_narrative.current_position", required=True),
        "why_now": _validated_text(value.get("why_now"), "target_narrative.why_now", required=True),
        "recent_proof": normalized_proof,
        "next_logic": _validated_text(value.get("next_logic"), "target_narrative.next_logic", required=True),
        "evidence_refs": _validated_refs(value.get("evidence_refs"), "target_narrative.evidence_refs", required=True),
        "route_nodes": nodes,
        "route_edges": edges,
    }
    for field in ("current_node_refs", "next_node_refs"):
        if field not in value:
            continue
        refs = _validated_refs(value.get(field), f"target_narrative.{field}")
        unknown = [ref for ref in refs if ref not in node_ids]
        if unknown:
            raise ObserverPresentationError(
                f"observer target narrative {field} references an unknown route node: {unknown[0]}"
            )
        result[field] = refs
    if "primary_visualization" in value:
        result["primary_visualization"] = _validated_primary_visualization(
            value.get("primary_visualization")
        )
    return result


def _validated_review(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ObserverPresentationError("observer semantic review must be an object")
    review_id = _validated_runtime_id(value.get("review_id"), "review_id")
    target_id = _validated_target_id(value.get("target_id"))
    decision = value.get("decision")
    if decision not in OBSERVER_SEMANTIC_REVIEW_DECISIONS:
        raise ObserverPresentationError(f"observer semantic review decision is invalid: {decision}")
    presentation_type = value.get("presentation_type")
    if presentation_type not in OBSERVER_PRESENTATION_TYPES:
        raise ObserverPresentationError(f"observer presentation_type is invalid: {presentation_type}")
    problems = [_validated_problem(row) for row in value.get("problems") or []]
    narrative = _validated_narrative(value.get("narrative"))
    route_node_ids = {
        str(row.get("id"))
        for row in narrative.get("route_nodes") or []
        if isinstance(row, dict) and row.get("id")
    }
    for problem in problems:
        node_ref = problem.get("node_ref")
        if node_ref and str(node_ref) not in route_node_ids:
            raise ObserverPresentationError(
                f"observer target problem node_ref references an unknown route node: {node_ref}"
            )
    return {
        "schema_version": OBSERVER_SEMANTIC_REVIEW_STATE_SCHEMA,
        "review_id": review_id,
        "target_id": target_id,
        "semantic_revision": int(value.get("semantic_revision") or 0),
        "reviewed_at": _validated_text(value.get("reviewed_at"), "reviewed_at", required=True),
        "source_fingerprint": _validated_text(value.get("source_fingerprint"), "source_fingerprint", required=True),
        "authority_fingerprint": _validated_text(value.get("authority_fingerprint"), "authority_fingerprint", required=True),
        "authority_reread": bool(value.get("authority_reread")),
        "decision": decision,
        "reason": _validated_text(value.get("reason"), "reason", required=True),
        "evidence_refs": _validated_refs(value.get("evidence_refs"), "evidence_refs", required=True),
        "map_relevant_signals": _validated_refs(value.get("map_relevant_signals"), "map_relevant_signals"),
        "presentation_type": presentation_type,
        "narrative": narrative,
        "problems": problems,
        "consumed_one_shot_request_ids": [
            _validated_runtime_id(item, "consumed_one_shot_request_id")
            for item in value.get("consumed_one_shot_request_ids") or []
        ],
        "active_durable_rule_ids": [
            _validated_runtime_id(item, "active_durable_rule_id")
            for item in value.get("active_durable_rule_ids") or []
        ],
    }


def _validated_target_state(value: object, target_id: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ObserverPresentationError("observer presentation target state must be an object")
    if value.get("schema_version") != OBSERVER_PRESENTATION_TARGET_SCHEMA:
        raise ObserverPresentationError(
            f"unsupported observer presentation target schema: {value.get('schema_version')}"
        )
    if _validated_target_id(value.get("target_id")) != target_id:
        raise ObserverPresentationError("observer presentation target state identity mismatch")
    current_review = value.get("current_review")
    transient_patch = value.get("active_transient_patch")
    return {
        "schema_version": OBSERVER_PRESENTATION_TARGET_SCHEMA,
        "target_id": target_id,
        "revision": int(value.get("revision") or 0),
        "presentation_revision": int(value.get("presentation_revision") or 0),
        "updated_at": value.get("updated_at"),
        "current_review": _validated_review(current_review) if current_review is not None else None,
        "active_transient_patch": (
            _validated_transient_patch(transient_patch) if transient_patch is not None else None
        ),
        "one_shot_requests": [_validated_request(row) for row in value.get("one_shot_requests") or []],
        "durable_rules": [_validated_rule(row) for row in value.get("durable_rules") or []],
    }


def read_presentation_state(project: Any) -> dict[str, object]:
    path = observer_presentation_paths(project)["state"]
    if not path.is_file():
        return _default_state(project)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObserverPresentationError(f"cannot read observer presentation state: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != OBSERVER_PRESENTATION_STATE_SCHEMA:
        raise ObserverPresentationError(
            f"unsupported observer presentation state schema: {raw.get('schema_version') if isinstance(raw, dict) else None}"
        )
    if raw.get("project_id") != project.project_id:
        raise ObserverPresentationError("observer presentation state project_id does not match current project")
    targets_raw = raw.get("targets") or {}
    if not isinstance(targets_raw, dict):
        raise ObserverPresentationError("observer presentation targets must be an object")
    targets: dict[str, object] = {}
    for key, value in targets_raw.items():
        target_id = _validated_target_id(key)
        targets[target_id] = _validated_target_state(value, target_id)
    return {
        "schema_version": OBSERVER_PRESENTATION_STATE_SCHEMA,
        "project_id": project.project_id,
        "revision": int(raw.get("revision") or 0),
        "updated_at": raw.get("updated_at"),
        "targets": targets,
    }


def _read_semantic_review_history_with_diagnostics(
    project: Any,
    target_id: str,
) -> tuple[list[dict[str, object]], list[str]]:
    """Read valid semantic-review history while retaining local journal errors.

    Presentation history is append-only and may outlive older validation
    contracts.  One malformed or legacy-incompatible event must not erase all
    otherwise-valid archived reviews from the human-facing history view.  The
    caller still receives fail-visible diagnostics for every skipped event.
    """

    target_id = _validated_target_id(target_id)
    path = observer_presentation_paths(project)["events"]
    if not path.is_file():
        return [], []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ObserverPresentationError(f"cannot read observer presentation history: {exc}") from exc

    reviews: list[dict[str, object]] = []
    diagnostics: list[str] = []
    seen_review_ids: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            diagnostics.append(f"cannot read observer presentation history line {line_number}: {exc}")
            continue
        if not isinstance(event, dict) or event.get("schema_version") != OBSERVER_PRESENTATION_EVENT_SCHEMA:
            diagnostics.append(f"unsupported observer presentation history event at line {line_number}")
            continue
        if event.get("project_id") != project.project_id:
            diagnostics.append(f"observer presentation history project_id mismatch at line {line_number}")
            continue
        if event.get("target_id") != target_id or event.get("event_kind") != "semantic_review_applied":
            continue
        try:
            review = _validated_review(event.get("review"))
        except ObserverPresentationError as exc:
            diagnostics.append(
                f"cannot read observer presentation history line {line_number}: {exc}"
            )
            continue
        review_id = str(review["review_id"])
        if review_id in seen_review_ids:
            continue
        seen_review_ids.add(review_id)
        reviews.append(review)
    reviews.sort(
        key=lambda row: (
            int(row.get("semantic_revision") or 0),
            str(row.get("reviewed_at") or ""),
            str(row.get("review_id") or ""),
        )
    )
    return reviews, diagnostics


def read_semantic_review_history(project: Any, target_id: str) -> list[dict[str, object]]:
    """Read durable semantic-review versions from the presentation event journal.

    Current state intentionally keeps only the latest reviewed semantics.  The
    append-only event journal is the authority for older reviewed versions, so
    history views must read that journal instead of reconstructing old maps
    from today's target state.  This strict public helper preserves the prior
    contract for callers that require the whole journal to validate cleanly;
    the dashboard projection uses the diagnostic reader so valid history can
    remain visible when one legacy event is incompatible.
    """

    reviews, diagnostics = _read_semantic_review_history_with_diagnostics(project, target_id)
    if diagnostics:
        raise ObserverPresentationError(diagnostics[0])
    return reviews


def _write_state(project: Any, state: dict[str, object]) -> dict[str, object]:
    path = observer_presentation_paths(project)["state"]
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    payload["revision"] = int(payload.get("revision") or 0) + 1
    payload["updated_at"] = _utc_now_iso()
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return payload


def _append_event(project: Any, event: dict[str, object]) -> None:
    path = observer_presentation_paths(project)["events"]
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing and not existing.endswith(("\n", "\r")):
        existing += "\n"
    atomic_write_text(path, existing + json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _target_state(state: dict[str, object], target_id: str) -> dict[str, object]:
    targets = state["targets"]
    assert isinstance(targets, dict)
    current = targets.get(target_id)
    if current is None:
        current = _default_target_state(target_id)
        targets[target_id] = current
    assert isinstance(current, dict)
    return current


def _check_target_revision(target_state: dict[str, object], expected_revision: int) -> None:
    current = int(target_state.get("revision") or 0)
    if expected_revision != current:
        raise ObserverPresentationConcurrencyError(expected_revision, current)


def _active_durable_rules(target_state: dict[str, object]) -> list[dict[str, object]]:
    return [
        row
        for row in target_state.get("durable_rules") or []
        if isinstance(row, dict) and row.get("status") == "active"
    ]


def target_presentation_projection(target_state: dict[str, object]) -> dict[str, object]:
    review = target_state.get("current_review")
    review_projection = None
    if isinstance(review, dict):
        review_projection = {
            "review_id": review.get("review_id"),
            "semantic_revision": review.get("semantic_revision"),
            "source_fingerprint": review.get("source_fingerprint"),
            "presentation_type": review.get("presentation_type"),
            "narrative": review.get("narrative"),
            "problems": review.get("problems"),
        }
    return {
        "current_review": review_projection,
        "active_durable_rules": _active_durable_rules(target_state),
        "active_transient_patch": target_state.get("active_transient_patch"),
    }


def target_presentation_fingerprint(target_state: dict[str, object]) -> str:
    return _stable_digest(target_presentation_projection(target_state))


def _check_presentation_view(
    target_state: dict[str, object],
    expected_revision: int,
    expected_fingerprint: str,
) -> None:
    current_revision = int(target_state.get("presentation_revision") or 0)
    current_fingerprint = target_presentation_fingerprint(target_state)
    if expected_revision != current_revision or expected_fingerprint != current_fingerprint:
        raise ObserverPresentationViewChanged(
            expected_revision,
            current_revision,
            expected_fingerprint,
            current_fingerprint,
        )


def _bump_presentation_revision(target_state: dict[str, object]) -> None:
    target_state["presentation_revision"] = int(target_state.get("presentation_revision") or 0) + 1


def _mutate_target_state(
    project: Any,
    state: dict[str, object],
    target_state: dict[str, object],
    event_kind: str,
    event_payload: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    target_state["revision"] = int(target_state.get("revision") or 0) + 1
    target_state["updated_at"] = _utc_now_iso()
    written = _write_state(project, state)
    event = {
        "schema_version": OBSERVER_PRESENTATION_EVENT_SCHEMA,
        "project_id": project.project_id,
        "target_id": target_state["target_id"],
        "target_revision": target_state["revision"],
        "state_revision": written["revision"],
        "event_kind": event_kind,
        "observed_at": target_state["updated_at"],
        **event_payload,
    }
    event["event_id"] = f"presentation-event-{_stable_digest(event)[:24]}"
    _append_event(project, event)
    return target_state, event


def target_semantic_source_projection(target_view: dict[str, object]) -> dict[str, object]:
    """Return target-local facts that independently invalidate semantic state."""

    target = target_view.get("target") if isinstance(target_view.get("target"), dict) else {}
    workstreams: list[dict[str, object]] = []
    for raw in target_view.get("workstreams") or []:
        if not isinstance(raw, dict):
            continue
        machine = raw.get("machine_state") if isinstance(raw.get("machine_state"), dict) else {}
        workstreams.append(
            {
                "id": raw.get("id"),
                "title": raw.get("title"),
                "status": raw.get("status"),
                "attention": raw.get("attention"),
                "goal": raw.get("goal"),
                "source_consistency": raw.get("source_consistency"),
                "execution": machine.get("execution"),
                "health": machine.get("health"),
                "health_reasons": list(machine.get("health_reasons") or []),
            }
        )
    continuations: list[dict[str, object]] = []
    for raw in target_view.get("continuations") or []:
        if not isinstance(raw, dict):
            continue
        latest = raw.get("latest_round") if isinstance(raw.get("latest_round"), dict) else {}
        effects = raw.get("effects") if isinstance(raw.get("effects"), dict) else {}
        continuations.append(
            {
                "task_id": raw.get("task_id"),
                "workstream_id": raw.get("workstream_id"),
                "stage": raw.get("stage"),
                "status": raw.get("status"),
                "objective": raw.get("objective"),
                "next_action": raw.get("next_action"),
                "round_generation": latest.get("generation"),
                "round_phase": latest.get("phase"),
                "round_milestone": latest.get("milestone"),
                "round_evidence_refs": list(latest.get("evidence_refs") or []),
                "unresolved_effect_count": int(effects.get("unresolved_count") or 0),
            }
        )
    workstreams.sort(key=lambda row: str(row.get("id") or ""))
    continuations.sort(key=lambda row: (str(row.get("task_id") or ""), str(row.get("workstream_id") or "")))
    return {
        "target": {
            "target_id": target.get("target_id"),
            "mode": target.get("mode"),
            "title": target.get("title"),
            "automation_ref": target.get("automation_ref"),
            "workstream_id": target.get("workstream_id"),
            "continuation_task_id": target.get("continuation_task_id"),
            "route_ref": target.get("route_ref"),
        },
        "workstreams": workstreams,
        "continuations": continuations,
    }


def target_semantic_source_fingerprint(target_view: dict[str, object]) -> str:
    return _stable_digest(target_semantic_source_projection(target_view))


def presentation_status(project: Any, target_views: dict[str, object]) -> dict[str, object]:
    state = read_presentation_state(project)
    stored_targets = state["targets"]
    assert isinstance(stored_targets, dict)
    rows: list[dict[str, object]] = []
    for view in target_views.get("targets") or []:
        if not isinstance(view, dict):
            continue
        target = view.get("target") if isinstance(view.get("target"), dict) else {}
        target_id = _validated_target_id(target.get("target_id"))
        current_fingerprint = target_semantic_source_fingerprint(view)
        target_state = stored_targets.get(target_id)
        if not isinstance(target_state, dict):
            target_state = _default_target_state(target_id)
        review = target_state.get("current_review")
        try:
            review_history, history_diagnostics = _read_semantic_review_history_with_diagnostics(
                project,
                target_id,
            )
            review_history_error = (
                history_diagnostics[0]
                if len(history_diagnostics) == 1
                else (
                    f"{history_diagnostics[0]} (+{len(history_diagnostics) - 1} more history errors)"
                    if history_diagnostics
                    else None
                )
            )
        except ObserverPresentationError as exc:
            review_history = []
            review_history_error = str(exc)
        if not isinstance(review, dict):
            semantic_status = "not_reviewed"
        elif review.get("source_fingerprint") == current_fingerprint:
            semantic_status = "current"
        else:
            semantic_status = "stale"
        rows.append(
            {
                "target_id": target_id,
                "target_revision": int(target_state.get("revision") or 0),
                "presentation_revision": int(target_state.get("presentation_revision") or 0),
                "presentation_fingerprint": target_presentation_fingerprint(target_state),
                "source_fingerprint": current_fingerprint,
                "semantic_status": semantic_status,
                "current_review": review,
                "review_history": review_history,
                "review_history_error": review_history_error,
                "active_transient_patch": target_state.get("active_transient_patch"),
                "active_one_shot_requests": [
                    row for row in target_state.get("one_shot_requests") or []
                    if isinstance(row, dict) and row.get("status") == "active"
                ],
                "active_durable_rules": [
                    row for row in target_state.get("durable_rules") or []
                    if isinstance(row, dict) and row.get("status") == "active"
                ],
            }
        )
    return {
        "schema_version": OBSERVER_PRESENTATION_STATE_SCHEMA,
        "project_id": project.project_id,
        "state_revision": state["revision"],
        "targets": rows,
    }


def attach_presentation_status(project: Any, target_views: dict[str, object]) -> dict[str, object]:
    """Attach target-local semantic review state without bloating the snapshot builder."""

    presentation = presentation_status(project, target_views)
    by_target = {
        str(row.get("target_id")): row
        for row in presentation.get("targets") or []
        if isinstance(row, dict) and row.get("target_id")
    }
    for target_view in target_views.get("targets") or []:
        if not isinstance(target_view, dict):
            continue
        target = target_view.get("target") if isinstance(target_view.get("target"), dict) else {}
        target_view["semantic_review"] = by_target.get(str(target.get("target_id") or ""))
    return presentation


def presentation_alert_specs(presentation: object) -> list[dict[str, object]]:
    """Return fail-visible alert inputs for target semantic lifecycle state."""

    specs: list[dict[str, object]] = []
    if not isinstance(presentation, dict):
        return specs
    for row in presentation.get("targets") or []:
        if not isinstance(row, dict):
            continue
        target_id = str(row.get("target_id") or "unknown")
        semantic_status = str(row.get("semantic_status") or "not_reviewed")
        current_review = row.get("current_review") if isinstance(row.get("current_review"), dict) else {}
        if semantic_status == "stale":
            specs.append(
                {
                    "alert_key": f"target:{target_id}:semantic-review-stale",
                    "severity": "warning",
                    "title": f"{target_id} 的 Target Narrative / Map Review 已落后",
                    "explanation": "该 target 自身的 meaning-relevant Workstream/continuation facts 已变化；旧 target narrative 保留用于追溯，但在重新读取 authority 并完成 Map Review 前不能当作当前路线语义。",
                    "canonical_identity": {"type": "observer_target", "id": target_id},
                    "provenance": [
                        {
                            "source": "observer_presentation",
                            "review_id": current_review.get("review_id"),
                            "stored_source_fingerprint": current_review.get("source_fingerprint"),
                            "current_source_fingerprint": row.get("source_fingerprint"),
                        }
                    ],
                }
            )
        elif semantic_status == "not_reviewed":
            specs.append(
                {
                    "alert_key": f"target:{target_id}:semantic-review-missing",
                    "severity": "warning",
                    "title": f"{target_id} 尚未形成 Target Narrative / Map Review",
                    "explanation": "该 target 已进入显式 Observer Target Registry，但还没有与当前 target facts 绑定的审计语义复核；展示层应保持 fail-visible，而不是从 fingerprint 或旧 Workstream 文本自动拼装路线。",
                    "canonical_identity": {"type": "observer_target", "id": target_id},
                    "provenance": [
                        {
                            "source": "observer_presentation",
                            "current_source_fingerprint": row.get("source_fingerprint"),
                        }
                    ],
                }
            )
        active_requests = [
            item
            for item in row.get("active_one_shot_requests") or []
            if isinstance(item, dict)
        ]
        if active_requests:
            specs.append(
                {
                    "alert_key": f"target:{target_id}:map-review-request-pending",
                    "severity": "warning",
                    "title": f"{target_id} 有待消费的一次性 Map Review 请求",
                    "explanation": "交互式 reviewed intent 已记录为 one-shot semantic review request；它必须由下一次正式 target semantic review 显式消费或继续保持 active，不能靠普通 render/snapshot 静默清除。",
                    "canonical_identity": {"type": "observer_target", "id": target_id},
                    "provenance": [
                        {
                            "source": "observer_presentation",
                            "request_ids": [item.get("request_id") for item in active_requests],
                        }
                    ],
                }
            )
    return specs


def add_one_shot_review_request(
    project: Any,
    *,
    target_id: str,
    request_id: str,
    expected_target_revision: int,
    reviewed_intent: str,
    scope: str,
    rationale: str,
    evidence_refs: list[str],
) -> tuple[dict[str, object], dict[str, object]]:
    target_id = _validated_target_id(target_id)
    request_id = _validated_runtime_id(request_id, "request_id")
    state = read_presentation_state(project)
    target_state = _target_state(state, target_id)
    _check_target_revision(target_state, expected_target_revision)
    for row in target_state.get("one_shot_requests") or []:
        if isinstance(row, dict) and row.get("request_id") == request_id:
            raise ObserverPresentationError("observer one-shot request_id already exists")
    request = _validated_request(
        {
            "schema_version": OBSERVER_PRESENTATION_REQUEST_SCHEMA,
            "request_id": request_id,
            "target_id": target_id,
            "status": "active",
            "reviewed_intent": reviewed_intent,
            "scope": scope,
            "rationale": rationale,
            "evidence_refs": evidence_refs,
            "created_at": _utc_now_iso(),
            "consumed_at": None,
            "consumed_by_review_id": None,
        }
    )
    target_state.setdefault("one_shot_requests", []).append(request)
    return _mutate_target_state(
        project,
        state,
        target_state,
        "one_shot_request_added",
        {"request": request},
    )


def add_durable_rule(
    project: Any,
    *,
    target_id: str,
    rule_id: str,
    expected_target_revision: int,
    reviewed_intent: str,
    scope: str,
    rationale: str,
    evidence_refs: list[str],
    supersedes: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    target_id = _validated_target_id(target_id)
    rule_id = _validated_runtime_id(rule_id, "rule_id")
    state = read_presentation_state(project)
    target_state = _target_state(state, target_id)
    _check_target_revision(target_state, expected_target_revision)
    rules = target_state.setdefault("durable_rules", [])
    assert isinstance(rules, list)
    if any(isinstance(row, dict) and row.get("rule_id") == rule_id for row in rules):
        raise ObserverPresentationError("observer durable rule_id already exists")
    normalized_supersedes = _validated_text(supersedes, "supersedes")
    if normalized_supersedes:
        previous = next(
            (row for row in rules if isinstance(row, dict) and row.get("rule_id") == normalized_supersedes),
            None,
        )
        if not isinstance(previous, dict) or previous.get("status") != "active":
            raise ObserverPresentationError("observer superseded durable rule must be active")
        previous["status"] = "superseded"
        previous["superseded_by"] = rule_id
    rule = _validated_rule(
        {
            "schema_version": OBSERVER_PRESENTATION_RULE_SCHEMA,
            "rule_id": rule_id,
            "target_id": target_id,
            "status": "active",
            "reviewed_intent": reviewed_intent,
            "scope": scope,
            "rationale": rationale,
            "evidence_refs": evidence_refs,
            "created_at": _utc_now_iso(),
            "supersedes": normalized_supersedes,
            "superseded_by": None,
            "withdrawn_at": None,
            "withdraw_reason": None,
        }
    )
    rules.append(rule)
    _bump_presentation_revision(target_state)
    return _mutate_target_state(
        project,
        state,
        target_state,
        "durable_rule_added" if not normalized_supersedes else "durable_rule_superseded",
        {"rule": rule, "supersedes": normalized_supersedes},
    )


def withdraw_durable_rule(
    project: Any,
    *,
    target_id: str,
    rule_id: str,
    expected_target_revision: int,
    reason: str,
    evidence_refs: list[str],
) -> tuple[dict[str, object], dict[str, object]]:
    target_id = _validated_target_id(target_id)
    rule_id = _validated_runtime_id(rule_id, "rule_id")
    state = read_presentation_state(project)
    target_state = _target_state(state, target_id)
    _check_target_revision(target_state, expected_target_revision)
    rules = target_state.get("durable_rules") or []
    rule = next((row for row in rules if isinstance(row, dict) and row.get("rule_id") == rule_id), None)
    if not isinstance(rule, dict) or rule.get("status") != "active":
        raise ObserverPresentationError("observer durable rule must be active before withdraw")
    reason = _validated_text(reason, "withdraw_reason", required=True) or ""
    refs = _validated_refs(evidence_refs, "withdraw evidence_refs", required=True)
    rule["status"] = "withdrawn"
    rule["withdrawn_at"] = _utc_now_iso()
    rule["withdraw_reason"] = reason
    _bump_presentation_revision(target_state)
    return _mutate_target_state(
        project,
        state,
        target_state,
        "durable_rule_withdrawn",
        {"rule_id": rule_id, "reason": reason, "evidence_refs": refs},
    )


def apply_transient_patch(
    project: Any,
    *,
    target_view: dict[str, object],
    patch_id: str,
    expected_target_revision: int,
    expected_presentation_revision: int,
    expected_presentation_fingerprint: str,
    reviewed_intent: str,
    scope: str,
    rationale: str,
    evidence_refs: list[str],
    density: str = "balanced",
    presentation_type: str | None = None,
    emphasize_sections: list[str] | None = None,
    semantic_risk_signals: list[str] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Apply one immediate presentation-only patch against exact current semantics.

    The patch may change visual density, presentation type, or emphasis only.  Any
    declared semantic-risk signal is refused and escalated to formal Map Review.
    """

    target = target_view.get("target") if isinstance(target_view.get("target"), dict) else {}
    target_id = _validated_target_id(target.get("target_id"))
    patch_id = _validated_runtime_id(patch_id, "patch_id")
    risks = _validated_refs(semantic_risk_signals, "semantic_risk_signals")
    if risks:
        raise ObserverPresentationSemanticEscalationRequired(risks)
    state = read_presentation_state(project)
    target_state = _target_state(state, target_id)
    _check_target_revision(target_state, expected_target_revision)
    expected_fingerprint = _validated_text(
        expected_presentation_fingerprint,
        "expected_presentation_fingerprint",
        required=True,
    ) or ""
    _check_presentation_view(
        target_state,
        expected_presentation_revision,
        expected_fingerprint,
    )
    review = target_state.get("current_review")
    if not isinstance(review, dict):
        raise ObserverPresentationError(
            "observer transient presentation patch requires a current semantic review"
        )
    current_source_fingerprint = target_semantic_source_fingerprint(target_view)
    if review.get("source_fingerprint") != current_source_fingerprint:
        raise ObserverPresentationSourceMismatch(
            str(review.get("source_fingerprint") or ""),
            current_source_fingerprint,
        )
    patch = _validated_transient_patch(
        {
            "schema_version": OBSERVER_TRANSIENT_PATCH_SCHEMA,
            "patch_id": patch_id,
            "target_id": target_id,
            "reviewed_intent": reviewed_intent,
            "scope": scope,
            "rationale": rationale,
            "evidence_refs": evidence_refs,
            "created_at": _utc_now_iso(),
            "base_review_id": review.get("review_id"),
            "density": density,
            "presentation_type": presentation_type,
            "emphasize_sections": emphasize_sections or [],
        }
    )
    previous = target_state.get("active_transient_patch")
    target_state["active_transient_patch"] = patch
    _bump_presentation_revision(target_state)
    return _mutate_target_state(
        project,
        state,
        target_state,
        "transient_patch_applied",
        {"patch": patch, "replaced_patch": previous},
    )


def clear_transient_patch(
    project: Any,
    *,
    target_id: str,
    expected_target_revision: int,
    expected_presentation_revision: int,
    expected_presentation_fingerprint: str,
    reason: str,
    evidence_refs: list[str],
) -> tuple[dict[str, object], dict[str, object]]:
    target_id = _validated_target_id(target_id)
    state = read_presentation_state(project)
    target_state = _target_state(state, target_id)
    _check_target_revision(target_state, expected_target_revision)
    expected_fingerprint = _validated_text(
        expected_presentation_fingerprint,
        "expected_presentation_fingerprint",
        required=True,
    ) or ""
    _check_presentation_view(
        target_state,
        expected_presentation_revision,
        expected_fingerprint,
    )
    patch = target_state.get("active_transient_patch")
    if not isinstance(patch, dict):
        raise ObserverPresentationError("observer transient presentation patch is not active")
    normalized_reason = _validated_text(reason, "clear_reason", required=True) or ""
    refs = _validated_refs(evidence_refs, "clear evidence_refs", required=True)
    target_state["active_transient_patch"] = None
    _bump_presentation_revision(target_state)
    return _mutate_target_state(
        project,
        state,
        target_state,
        "transient_patch_cleared",
        {"patch": patch, "reason": normalized_reason, "evidence_refs": refs},
    )


def apply_semantic_review(
    project: Any,
    *,
    target_view: dict[str, object],
    expected_target_revision: int,
    expected_source_fingerprint: str,
    review_id: str,
    authority_fingerprint: str,
    authority_reread: bool,
    decision: str,
    reason: str,
    evidence_refs: list[str],
    map_relevant_signals: list[str],
    presentation_type: str,
    narrative: dict[str, object],
    problems: list[dict[str, object]] | None = None,
    consume_one_shot_request_ids: list[str] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    target = target_view.get("target") if isinstance(target_view.get("target"), dict) else {}
    target_id = _validated_target_id(target.get("target_id"))
    review_id = _validated_runtime_id(review_id, "review_id")
    current_source_fingerprint = target_semantic_source_fingerprint(target_view)
    expected_source_fingerprint = _validated_text(
        expected_source_fingerprint,
        "expected_source_fingerprint",
        required=True,
    ) or ""
    if expected_source_fingerprint != current_source_fingerprint:
        raise ObserverPresentationSourceMismatch(expected_source_fingerprint, current_source_fingerprint)
    authority_fingerprint = _validated_text(authority_fingerprint, "authority_fingerprint", required=True) or ""
    if decision not in OBSERVER_SEMANTIC_REVIEW_DECISIONS:
        raise ObserverPresentationError(f"observer semantic review decision is invalid: {decision}")
    if presentation_type not in OBSERVER_PRESENTATION_TYPES:
        raise ObserverPresentationError(f"observer presentation_type is invalid: {presentation_type}")
    signals = _validated_refs(map_relevant_signals, "map_relevant_signals")
    if signals and not authority_reread:
        raise ObserverPresentationError("map-relevant signals require authority reread before semantic review")
    normalized_problems = [_validated_problem(row) for row in problems or []]
    if decision == "unchanged" and any(
        row.get("plan_impact") in {"route_change", "major_replan"} for row in normalized_problems
    ):
        raise ObserverPresentationError("route-impacting problem requires a map-changing semantic review decision")
    normalized_narrative = _validated_narrative(narrative)
    refs = _validated_refs(evidence_refs, "semantic review evidence_refs", required=True)

    state = read_presentation_state(project)
    target_state = _target_state(state, target_id)
    _check_target_revision(target_state, expected_target_revision)
    active_requests = {
        str(row.get("request_id")): row
        for row in target_state.get("one_shot_requests") or []
        if isinstance(row, dict) and row.get("status") == "active"
    }
    consume_ids = [
        _validated_runtime_id(item, "consume_one_shot_request_id")
        for item in consume_one_shot_request_ids or []
    ]
    unknown = [item for item in consume_ids if item not in active_requests]
    if unknown:
        raise ObserverPresentationError(
            f"observer one-shot request is not active for semantic review: {unknown[0]}"
        )
    active_rule_ids = [
        str(row.get("rule_id"))
        for row in target_state.get("durable_rules") or []
        if isinstance(row, dict) and row.get("status") == "active"
    ]
    previous = target_state.get("current_review")
    previous_semantic_revision = (
        int(previous.get("semantic_revision") or 0) if isinstance(previous, dict) else 0
    )
    review = _validated_review(
        {
            "schema_version": OBSERVER_SEMANTIC_REVIEW_STATE_SCHEMA,
            "review_id": review_id,
            "target_id": target_id,
            "semantic_revision": previous_semantic_revision + 1,
            "reviewed_at": _utc_now_iso(),
            "source_fingerprint": current_source_fingerprint,
            "authority_fingerprint": authority_fingerprint,
            "authority_reread": authority_reread,
            "decision": decision,
            "reason": reason,
            "evidence_refs": refs,
            "map_relevant_signals": signals,
            "presentation_type": presentation_type,
            "narrative": normalized_narrative,
            "problems": normalized_problems,
            "consumed_one_shot_request_ids": consume_ids,
            "active_durable_rule_ids": active_rule_ids,
        }
    )
    expired_transient_patch = target_state.get("active_transient_patch")
    target_state["current_review"] = review
    target_state["active_transient_patch"] = None
    _bump_presentation_revision(target_state)
    if consume_ids:
        consumed_at = review["reviewed_at"]
        retained: list[dict[str, object]] = []
        for row in target_state.get("one_shot_requests") or []:
            if not isinstance(row, dict):
                continue
            if row.get("request_id") in consume_ids:
                consumed = dict(row)
                consumed["status"] = "consumed"
                consumed["consumed_at"] = consumed_at
                consumed["consumed_by_review_id"] = review_id
                # Consumed one-shot guidance leaves active state immediately.
                review.setdefault("consumed_one_shot_requests", []).append(_validated_request(consumed))
                continue
            retained.append(row)
        target_state["one_shot_requests"] = retained
    return _mutate_target_state(
        project,
        state,
        target_state,
        "semantic_review_applied",
        {"review": review, "expired_transient_patch": expired_transient_patch},
    )


__all__ = [
    "OBSERVER_PRESENTATION_EVENT_SCHEMA",
    "OBSERVER_PRESENTATION_REQUEST_SCHEMA",
    "OBSERVER_PRESENTATION_RULE_SCHEMA",
    "OBSERVER_PRESENTATION_STATE_SCHEMA",
    "OBSERVER_TRANSIENT_PATCH_SCHEMA",
    "OBSERVER_SEMANTIC_REVIEW_STATE_SCHEMA",
    "OBSERVER_TARGET_NARRATIVE_SCHEMA",
    "OBSERVER_TARGET_PROBLEM_SCHEMA",
    "ObserverPresentationConcurrencyError",
    "ObserverPresentationError",
    "ObserverPresentationSemanticEscalationRequired",
    "ObserverPresentationSourceMismatch",
    "ObserverPresentationViewChanged",
    "add_durable_rule",
    "add_one_shot_review_request",
    "apply_transient_patch",
    "apply_semantic_review",
    "attach_presentation_status",
    "clear_transient_patch",
    "observer_presentation_paths",
    "presentation_alert_specs",
    "presentation_status",
    "read_presentation_state",
    "read_semantic_review_history",
    "target_semantic_source_fingerprint",
    "target_semantic_source_projection",
    "target_presentation_fingerprint",
    "target_presentation_projection",
    "withdraw_durable_rule",
]
