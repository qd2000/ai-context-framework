"""Global usage-log project inventory command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from ai_context_framework.constants import JSON_SCHEMA_VERSION
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.observability import acf_home, usage_project_dir
from ai_context_framework.paths import infer_context_profile, infer_project_root, is_context_root


def projects_root_from_log_root(value: Path | None) -> Path:
    root = (value.expanduser().resolve() if value is not None else acf_home())
    return root if root.name == "projects" else root / "projects"


def read_jsonl_events(path: Path) -> tuple[list[dict[str, object]], int]:
    events: list[dict[str, object]] = []
    bad_lines = 0
    if not path.exists():
        return events, bad_lines
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            bad_lines += 1
            continue
        if isinstance(event, dict):
            events.append(event)
    return events, bad_lines


def command_counts(events: Iterable[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        command = str(event.get("command") or "unknown")
        counts[command] = counts.get(command, 0) + 1
    return counts


def error_counts(events: Iterable[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        code = event.get("error_code")
        if code:
            key = str(code)
            counts[key] = counts.get(key, 0) + 1
    return counts


def top_commands(events: Iterable[dict[str, object]], limit: int = 8) -> list[dict[str, object]]:
    counts = command_counts(events)
    return [
        {"command": command, "count": count}
        for command, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def is_synthetic_project_id(project_id: str) -> bool:
    prefixes = (
        "acf-",
        "init-status-check-",
        "human-note",
        "worklog",
        "workstream",
        "plan-reference-",
        "task-stage-",
        "new-object-",
        "tmp",
        "Temp-",
        "wheel-context-",
        "matrix-project-",
        "standard-project-",
    )
    return project_id.startswith(prefixes)


def context_classification(context: Path) -> str:
    if context.name == "template":
        return "template_context"
    lowered_parts = [part.lower() for part in context.parts]
    if any("archive" in part for part in lowered_parts) or context.parent.name.upper() == "TEMP":
        return "archive_or_temp_context"
    return "resolved_context"


def context_match_payload(context: Path) -> dict[str, object]:
    project_root = infer_project_root(context).resolve()
    return {
        "resolved_project_root": str(project_root),
        "context_root": str(context.resolve()),
        "context_profile": infer_context_profile(context),
        "classification": context_classification(context),
    }


def context_match_priority(payload: dict[str, object]) -> int:
    context_root = str(payload.get("context_root") or "").replace("\\", "/")
    classification = str(payload.get("classification") or "")
    if context_root.endswith("/docs/ai"):
        return 0
    if classification == "resolved_context":
        return 1
    if classification == "archive_or_temp_context":
        return 2
    if classification == "template_context":
        return 3
    return 4


def event_context_match(events: list[dict[str, object]]) -> dict[str, object] | None:
    for event in reversed(events):
        context_value = event.get("context_root")
        if isinstance(context_value, str) and context_value.strip():
            context = Path(context_value).expanduser().resolve()
            if is_context_root(context):
                return context_match_payload(context)
            project_value = event.get("project_root")
            return {
                "resolved_project_root": str(Path(project_value).expanduser().resolve()) if isinstance(project_value, str) and project_value.strip() else None,
                "context_root": str(context),
                "context_profile": None,
                "classification": "missing_path",
            }
        project_value = event.get("project_root")
        if isinstance(project_value, str) and project_value.strip():
            project_root = Path(project_value).expanduser().resolve()
            for candidate in (project_root / "docs" / "ai", project_root / "docs-acf" / "ai"):
                if is_context_root(candidate):
                    return context_match_payload(candidate)
            return {
                "resolved_project_root": str(project_root),
                "context_root": None,
                "context_profile": None,
                "classification": "missing_path",
            }
    return None


def scan_context_roots(scan_roots: list[Path]) -> dict[str, dict[str, object]]:
    resolved: dict[str, dict[str, object]] = {}
    for root in scan_roots:
        root = root.expanduser().resolve()
        if not root.exists():
            continue
        candidates = [root] if is_context_root(root) else []
        for agents in root.rglob("AGENTS.md"):
            parent = agents.parent
            if is_context_root(parent):
                candidates.append(parent)
        for context in candidates:
            project_root = infer_project_root(context).resolve()
            project_id = usage_project_dir(project_root).name
            payload = context_match_payload(context)
            existing = resolved.get(project_id)
            if existing is not None and context_match_priority(existing) <= context_match_priority(payload):
                continue
            resolved[project_id] = payload
    return resolved


def collect_log_projects(
    *,
    log_root: Path | None,
    scan_roots: list[Path],
    min_events: int,
    include_unresolved: bool,
) -> dict[str, object]:
    projects_root = projects_root_from_log_root(log_root)
    scanned = scan_context_roots(scan_roots)
    rows: list[dict[str, object]] = []
    raw_project_count = 0
    raw_event_count = 0
    bad_line_count = 0
    resolved_context_count = 0
    classification_counts: dict[str, int] = {}
    if projects_root.exists():
        for directory in sorted(path for path in projects_root.iterdir() if path.is_dir()):
            log_path = directory / "logs" / "usage.jsonl"
            if not log_path.exists():
                continue
            events, bad_lines = read_jsonl_events(log_path)
            raw_project_count += 1
            raw_event_count += len(events)
            bad_line_count += bad_lines
            project_id = directory.name
            context_match = scanned.get(project_id) or event_context_match(events)
            if context_match is not None:
                classification = str(context_match["classification"])
                if classification == "resolved_context":
                    resolved_context_count += 1
            elif is_synthetic_project_id(project_id):
                classification = "synthetic_or_test_like"
            else:
                classification = "unresolved_log"
            classification_counts[classification] = classification_counts.get(classification, 0) + 1
            if len(events) < min_events:
                continue
            if classification in {"unresolved_log", "synthetic_or_test_like", "missing_path"} and not include_unresolved:
                continue
            first = events[0].get("timestamp") if events else None
            latest = events[-1].get("timestamp") if events else None
            row: dict[str, object] = {
                "project_id": project_id,
                "event_count": len(events),
                "first_event_at": first,
                "latest_event_at": latest,
                "classification": classification,
                "top_commands": top_commands(events),
                "error_counts": error_counts(events),
                "log_path": str(log_path),
            }
            if context_match is not None:
                row.update(context_match)
            rows.append(row)
    for project_id, scan_match in scanned.items():
        if projects_root.exists() and (projects_root / project_id / "logs" / "usage.jsonl").exists():
            continue
        classification = str(scan_match["classification"])
        if min_events > 0:
            continue
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
        if classification == "resolved_context":
            resolved_context_count += 1
        row = {
            "project_id": project_id,
            "event_count": 0,
            "first_event_at": None,
            "latest_event_at": None,
            "classification": classification,
            "top_commands": [],
            "error_counts": {},
            **scan_match,
        }
        rows.append(row)
    rows.sort(key=lambda item: (str(item.get("latest_event_at") or ""), str(item.get("project_id"))), reverse=True)
    return {
        "command": "log projects",
        "ok": True,
        "acf_home": str(projects_root.parent),
        "projects_root": str(projects_root),
        "raw_project_count": raw_project_count,
        "raw_event_count": raw_event_count,
        "bad_line_count": bad_line_count,
        "resolved_context_count": resolved_context_count,
        "classification_counts": classification_counts,
        "projects": rows,
    }


def log_projects_command(args: argparse.Namespace) -> int:
    payload = collect_log_projects(
        log_root=getattr(args, "log_root", None),
        scan_roots=getattr(args, "scan_root", None) or [],
        min_events=max(0, int(getattr(args, "min_events", 0) or 0)),
        include_unresolved=bool(getattr(args, "include_unresolved", False)),
    )
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"projects: {payload['raw_project_count']}")
        print(f"events: {payload['raw_event_count']}")
    return 0
