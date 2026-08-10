"""WS003 read-only next-entry and draft status commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_context_framework.constants import EXIT_INPUT_ERROR, JSON_SCHEMA_VERSION
from ai_context_framework.context_budget import context_budget_warnings
from ai_context_framework.commands.status_check import workstream_entry_payload
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.paths import require_context_root, resolve_status_location


def emit_query(args: argparse.Namespace, payload: dict[str, object]) -> int:
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        for warning in payload.get("context_warnings", []):
            if isinstance(warning, dict):
                print("WARN: " + str(warning.get("message", warning)))
        print(payload.get("recommended_entry") or payload.get("command"))
    return 0 if payload.get("ok", True) else EXIT_INPUT_ERROR


def next_command(args: argparse.Namespace) -> int:
    location = resolve_status_location(args.path)
    entry = workstream_entry_payload(
        location.context_root,
        explicit_workstream=getattr(args, "workstream", None),
        invocation_path=location.project_root,
    )
    context_warnings = context_budget_warnings(location.context_root, entry)
    payload = {
        "schema_version": JSON_SCHEMA_VERSION,
        "ok": bool(entry.get("selection_ok", True)),
        "command": "next",
        "context": str(location.context_root),
        "changed_files": [],
        "error_code": entry.get("selection_error_code"),
        "warnings": [],
        "context_warnings": context_warnings,
        "next_actions": [],
        **entry,
    }
    return emit_query(args, payload)


def draft_kind(path: Path) -> str:
    parts = set(path.parts)
    name = path.name
    if "knowledge-drafts" in parts:
        return "knowledge"
    if "archive-drafts" in parts:
        return "archive"
    if "curation-drafts" in parts:
        return "curation"
    if name.endswith("-doctor.md"):
        return "doctor_semantic"
    return "writeback"


def draft_status_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    draft_roots = [
        root / "worklog" / "writeback-drafts",
        root / "worklog" / "knowledge-drafts",
        root / "worklog" / "archive-drafts",
        root / "worklog" / "curation-drafts",
    ]
    drafts: list[dict[str, object]] = []
    for draft_root in draft_roots:
        if not draft_root.exists():
            continue
        for path in sorted(draft_root.glob("*.md")):
            drafts.append(
                {
                    "type": draft_kind(path),
                    "path": path.relative_to(root).as_posix(),
                    "age_days": None,
                    "next_action": "review",
                }
            )
    payload = {
        "schema_version": JSON_SCHEMA_VERSION,
        "ok": True,
        "command": "draft status",
        "context": str(root),
        "changed_files": [],
        "drafts": drafts,
        "error_code": None,
        "warnings": [],
        "next_actions": [],
    }
    return emit_query(args, payload)
