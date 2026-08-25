"""CLI adapter for structured continuation dogfood issues."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from ai_context_framework.observability import (
    append_usage_event,
    usage_log_enabled,
    usage_log_path,
    utc_now_iso,
)


def _continuation():
    # Lazy import avoids a module cycle while reusing the canonical
    # continuation workspace discovery, validation, and JSON contracts.
    from ai_context_framework.commands import continuation

    return continuation


def continuation_issue_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, object]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        control = core._load_control(paths, root)
        state = core._load_state(paths)
        if not usage_log_enabled(root):
            raise core.ContinuationError(
                "usage logging is disabled for this worktree",
                code="usage_log_disabled",
                next_actions=[
                    "Run `acf log enable` from the project context before recording dogfood issues."
                ],
            )
        category = str(args.category or "other").strip().lower() or "other"
        severity = str(args.severity or "medium").strip().lower()
        if severity not in {"low", "medium", "high", "critical"}:
            raise core.ContinuationError("unsupported issue severity", code="issue_invalid")
        text = core._validate_text(args.text, field="text")
        related_command = str(args.related_command or "").strip()
        resolve_fingerprint = str(args.resolve_fingerprint or "").strip().lower()
        if resolve_fingerprint:
            if not re.fullmatch(r"[0-9a-f]{20}", resolve_fingerprint):
                raise core.ContinuationError(
                    "issue fingerprint must be 20 lowercase hex characters",
                    code="issue_invalid",
                )
            fingerprint = resolve_fingerprint
            event_kind = "continuation_issue_resolution"
            command_status = "issue_resolved"
        else:
            normalized_text = " ".join(text.lower().split())
            fingerprint_seed = "|".join((category, related_command.lower(), normalized_text))
            fingerprint = hashlib.sha256(fingerprint_seed.encode("utf-8")).hexdigest()[:20]
            event_kind = "continuation_issue"
            command_status = "issue_recorded"
        event: dict[str, object] = {
            "schema_version": 1,
            "timestamp": utc_now_iso(),
            "event_kind": event_kind,
            "command": "continuation issue",
            "project_root": str(root),
            "workspace_root": str(root),
            "task_id": control["task_id"],
            "workstream_id": control.get("workstream_id"),
            "stage": state["stage"],
            "state_status": state["status"],
            "category": category,
            "severity": severity,
            "text": text,
            "fingerprint": fingerprint,
            "evidence_refs": list(dict.fromkeys(args.evidence_ref or []))[: core.MAX_LIST_ITEMS],
            "related_command": related_command or None,
            "runner_id": str(args.runner_id or "agent").strip() or "agent",
            "ok": True,
            "exit_code": 0,
            "error_code": None,
        }
        append_usage_event(root, event)
        return {
            "status": command_status,
            "task_id": control["task_id"],
            "fingerprint": fingerprint,
            "log_path": str(usage_log_path(root)),
            "issue": event,
        }

    return core._guarded(args, "continuation issue", operation)


def register_issue_parser(subparsers, add_json_argument) -> None:
    parser = subparsers.add_parser(
        "issue",
        help="record one structured reusable dogfood issue in the user-level ACF log",
    )
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--category", default="other")
    parser.add_argument(
        "--severity",
        choices=("low", "medium", "high", "critical"),
        default="medium",
    )
    parser.add_argument("--text", required=True)
    parser.add_argument(
        "--resolve-fingerprint",
        default=None,
        help="append a resolution event for an existing aggregated issue fingerprint",
    )
    parser.add_argument("--evidence-ref", action="append", default=None)
    parser.add_argument("--related-command", default=None)
    parser.add_argument("--runner-id", default="agent")
    add_json_argument(parser)
    parser.set_defaults(func=continuation_issue_command)

