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
    alerts = [row for row in safe_current.get("alerts") or [] if isinstance(row, dict)]
    self_alerts = [row for row in safe_self_alerts if isinstance(row, dict)] if isinstance(safe_self_alerts, list) else []
    all_alerts = self_alerts + alerts
    overall = _overall_health(safe_current, self_alerts)
    current_data_age = safe_status.get("data_age") if isinstance(safe_status.get("data_age"), dict) else {}
    active_count = sum(1 for row in workstreams if str(row.get("status") or "").casefold() in {"active", "blocked", "merging", "readytomerge"})
    cards = "".join(_workstream_card_html(safe_current, row) for row in workstreams)
    alerts_html = "".join(_dashboard_alert_html(row) for row in all_alerts) or '<p class="muted">当前没有需要关注的 Alert。</p>'
    timeline = _timeline_html(
        safe_events if isinstance(safe_events, list) else [],
        safe_interpretations if isinstance(safe_interpretations, list) else [],
    )
    latest_proof: list[str] = []
    for row in workstreams:
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
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.62 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}} a{{color:var(--blue)}} code{{font:12.5px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;color:#344054}} .page{{max-width:1280px;margin:auto;padding:24px}} h1{{font-size:24px;line-height:1.25;margin:0 0 4px}} h2{{font-size:19px;margin:0 0 14px}} h3{{font-size:17px;margin:0}} h4{{font-size:14px;margin:0 0 6px}} p{{margin:6px 0 12px}} ul{{margin:6px 0 12px;padding-left:20px}} .muted{{color:var(--muted)}} .canonical{{color:var(--muted);font-size:13px;margin-top:4px}} .top{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}} .summary-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0 22px}} .metric,.panel,.workstream-card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}} .metric{{padding:14px}} .metric strong{{display:block;font-size:18px;margin-top:3px}} .panel{{padding:18px;margin:0 0 18px}} .toolbar{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}} input,select{{font:inherit;border:1px solid var(--line);border-radius:8px;background:#fff;padding:8px 10px;min-height:38px}} input{{flex:1;min-width:220px}} .workstream-list{{display:grid;gap:14px}} .workstream-card{{padding:18px}} .card-header{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}} .badge-row{{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}} .badge{{display:inline-flex;align-items:center;gap:4px;border:1px solid currentColor;border-radius:999px;padding:2px 8px;font-size:12.5px;white-space:nowrap}} .tone-critical,.tone-text-critical{{color:var(--red)}} .tone-warning,.tone-text-warning{{color:var(--amber)}} .tone-healthy{{color:var(--green)}} .tone-active{{color:var(--blue)}} .tone-muted{{color:var(--muted)}} .tone-border-critical{{border-left:4px solid var(--red)!important}} .tone-border-warning{{border-left:4px solid var(--amber)!important}} .tone-border-active{{border-left:4px solid var(--blue)!important}} .semantic-notice{{background:var(--gray-bg);border-radius:8px;padding:9px 11px;margin:12px 0;font-size:13px}} .logic-grid,.technical-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 18px;margin-top:14px}} .logic-grid section{{border-top:1px solid var(--line);padding-top:10px}} .span-two{{grid-column:1/-1}} details{{border-top:1px solid var(--line);margin-top:14px;padding-top:10px}} summary{{cursor:pointer;font-weight:600;color:#344054}} .breakable{{word-break:break-all}} .alert{{border:1px solid var(--line);border-radius:9px;padding:12px 14px;margin:9px 0;background:#fff}} .alert-title{{font-weight:700}} .timeline-item{{display:grid;grid-template-columns:160px 1fr;gap:14px;border-left:2px solid var(--line);padding:5px 0 14px 14px;margin-left:5px}} .timeline-item time{{font-size:12.5px;color:var(--muted)}} .semantic-event{{border-left-color:var(--blue)}} .glossary-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}} .glossary-item{{border:1px solid var(--line);border-radius:8px;padding:12px}} .hidden{{display:none!important}} .empty{{padding:18px;color:var(--muted);text-align:center}} footer{{color:var(--muted);font-size:12.5px;padding:6px 0 20px}}
@media(max-width:760px){{.page{{padding:14px}}.top,.card-header{{display:block}}.summary-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.logic-grid,.technical-grid,.glossary-grid{{grid-template-columns:1fr}}.span-two{{grid-column:auto}}.badge-row{{justify-content:flex-start;margin-top:10px}}.timeline-item{{grid-template-columns:1fr;gap:2px}}}}
</style>
</head>
<body>
<main class="page">
  <header class="top"><div><h1>{_html_text(title)}</h1><div class="muted">最后观察：{_html_text(_dashboard_display_time(safe_current.get('observed_at')))} · 数据状态：{_html_text(current_data_age.get('state'))}</div></div><div class="badge tone-{_html_text(overall)}"><span aria-hidden="true">{health_icon}</span> Overall Health：{_html_text(health_label)}</div></header>
  <section class="summary-grid" aria-label="项目总览">
    <div class="metric"><span class="muted">Active Workstreams</span><strong>{active_count}</strong></div>
    <div class="metric"><span class="muted">当前 Alerts</span><strong>{len(all_alerts)}</strong></div>
    <div class="metric"><span class="muted">Observer data age</span><strong>{_html_text(current_data_age.get('state'))}</strong></div>
    <div class="metric"><span class="muted">Semantic coverage</span><strong>{_html_text((safe_current.get('semantic') or {}).get('status') if isinstance(safe_current.get('semantic'),dict) else None)}</strong></div>
  </section>
  <section class="panel"><h2>最近重大进展</h2><ul>{latest_html}</ul></section>
  <section class="panel" id="alerts"><h2>当前 Alerts</h2>{alerts_html}</section>
  <section class="panel"><h2>Workstreams</h2><div class="toolbar"><input id="search" type="search" placeholder="搜索 Workstream、canonical term、目标或下一步" aria-label="搜索"><select id="health-filter" aria-label="按健康状态筛选"><option value="all">全部健康状态</option><option value="critical">Critical</option><option value="warning">Warning</option><option value="healthy">Healthy</option></select></div><div class="workstream-list" id="workstreams">{cards or '<p class="empty">当前没有 Workstream。</p>'}</div></section>
  <section class="panel"><h2>Meaningful Timeline</h2><div id="timeline">{timeline}</div></section>
  <section class="panel"><h2>Semantic Glossary</h2><div class="glossary-grid" id="glossary">{glossary_html}</div></section>
  <footer>Observer 只解释本地事实，不参与 Writer control plane。Dashboard 为静态自包含文件，不需要 HTTP 服务。页面时间统一显示北京时间 (UTC+08:00)，底层 canonical state/history 仍使用 UTC。</footer>
</main>
<script id="observer-data" type="application/json">{embedded_json}</script>
<script>
(()=>{{const search=document.getElementById('search'),health=document.getElementById('health-filter');const apply=()=>{{const q=(search.value||'').trim().toLowerCase(),h=health.value;document.querySelectorAll('.workstream-card').forEach(card=>{{const text=card.dataset.search||'',okQ=!q||text.includes(q),okH=h==='all'||card.dataset.health===h;card.classList.toggle('hidden',!(okQ&&okH));}});document.querySelectorAll('.glossary-item').forEach(item=>item.classList.toggle('hidden',!!q&&!(item.dataset.search||'').includes(q)));}};search.addEventListener('input',apply);health.addEventListener('change',apply);}})();
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
