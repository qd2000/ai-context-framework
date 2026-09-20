"""Command handlers for feedback inbox workflows."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Sequence

from ai_context_framework.constants import JSON_SCHEMA_VERSION, VALID_FEEDBACK_STATUSES
from ai_context_framework.json_contract import dry_run_enabled, emit_write_result, json_enabled, print_json, set_result_payload
from ai_context_framework.models import CheckResult
from ai_context_framework.paths import require_context_root
from ai_context_framework.tables import parse_markdown_table_rows
from ai_context_framework.validators.checks import validate_date, validate_feedback_id


MaybeCheckAfter = Callable[[argparse.Namespace, Path, str | None], CheckResult | None]


@dataclass(frozen=True)
class FeedbackDependencies:
    maybe_check_after: MaybeCheckAfter
    feedback_inbox_path: Callable[..., Any]
    read_feedback_rows: Callable[..., Any]
    feedback_row_to_payload: Callable[..., Any]
    count_by_key: Callable[..., Any]
    update_feedback_row: Callable[..., Any]
    feedback_archive_path: Callable[..., Any]
    read_text: Callable[..., Any]
    find_feedback_row: Callable[..., Any]
    remove_feedback_row: Callable[..., Any]
    append_feedback_archive_row: Callable[..., Any]


def feedback_list_command(args: argparse.Namespace, *, deps: FeedbackDependencies) -> int:
    root = require_context_root(args.path)
    inbox_path = deps.feedback_inbox_path(root)
    rows = deps.read_feedback_rows(inbox_path)
    if args.status:
        rows = [row for row in rows if row.get("状态") == args.status]
    items = [deps.feedback_row_to_payload(row) for row in rows]
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "feedback list",
        "ok": True,
        "context": str(root),
        "changed_files": [],
        "items": items,
        "summary": {
            "total": len(items),
            "by_status": deps.count_by_key(items, "status"),
        },
        "error_code": None,
        "next_actions": ["No feedback items matched."] if not items else [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        if not items:
            print("no feedback items")
        for item in items:
            print(f"{item['id']}\t{item['status']}\t{item['type']}\t{item['content']}")
    return 0


def feedback_archive_candidates_command(args: argparse.Namespace, *, deps: FeedbackDependencies) -> int:
    root = require_context_root(args.path)
    rows = deps.read_feedback_rows(deps.feedback_inbox_path(root))
    candidates = [deps.feedback_row_to_payload(row) for row in rows if row.get("状态") in {"Done", "Rejected"}]
    blocked = [deps.feedback_row_to_payload(row) for row in rows if row.get("状态") not in {"Done", "Rejected"}]
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "feedback archive-candidates",
        "ok": True,
        "context": str(root),
        "changed_files": [],
        "candidates": candidates,
        "blocked": blocked,
        "summary": {
            "candidate_total": len(candidates),
            "blocked_total": len(blocked),
            "by_status": deps.count_by_key([*candidates, *blocked], "status"),
        },
        "error_code": None,
        "next_actions": ["Archive candidates with `acf feedback archive <ID> --reason ...`."] if candidates else [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        if not candidates:
            print("no feedback archive candidates")
        for item in candidates:
            print(f"{item['id']}\t{item['status']}\t{item['content']}")
    return 0


def feedback_triage_command(args: argparse.Namespace, *, deps: FeedbackDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    next_action = args.next_action.strip()
    if not next_action:
        raise SystemExit("feedback triage requires non-empty --next-action")
    evidence = args.evidence.strip() if args.evidence else ""
    updates = {"状态": "Triaged", "后续处理": next_action if not evidence else f"{next_action} 证据：{evidence}"}
    changed, row = deps.update_feedback_row(deps.feedback_inbox_path(root), args.id, updates, dry_run)
    changed_files = [deps.feedback_inbox_path(root)] if changed or dry_run else []
    check_result = deps.maybe_check_after(args, root, None)
    action = "would triage" if dry_run else "triaged"
    return emit_write_result(
        args,
        "feedback triage",
        f"{action} feedback {args.id}",
        changed_files,
        check_result,
        extra_payload={"id": args.id, "item": deps.feedback_row_to_payload(row)},
    )


def feedback_done_command(args: argparse.Namespace, *, deps: FeedbackDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    result = args.result.strip()
    evidence = args.evidence.strip()
    if not result:
        raise SystemExit("feedback done requires non-empty --result")
    if not evidence:
        raise SystemExit("feedback done requires non-empty --evidence")
    updates = {"状态": "Done", "后续处理": f"{result} 证据：{evidence}"}
    changed, row = deps.update_feedback_row(deps.feedback_inbox_path(root), args.id, updates, dry_run)
    changed_files = [deps.feedback_inbox_path(root)] if changed or dry_run else []
    check_result = deps.maybe_check_after(args, root, None)
    action = "would mark done" if dry_run else "marked done"
    return emit_write_result(
        args,
        "feedback done",
        f"{action} feedback {args.id}",
        changed_files,
        check_result,
        extra_payload={"id": args.id, "item": deps.feedback_row_to_payload(row)},
    )


def feedback_reject_command(args: argparse.Namespace, *, deps: FeedbackDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    reason = args.reason.strip()
    if not reason:
        raise SystemExit("feedback reject requires non-empty --reason")
    updates = {"状态": "Rejected", "后续处理": f"Rejected：{reason}"}
    changed, row = deps.update_feedback_row(deps.feedback_inbox_path(root), args.id, updates, dry_run)
    changed_files = [deps.feedback_inbox_path(root)] if changed or dry_run else []
    check_result = deps.maybe_check_after(args, root, None)
    action = "would reject" if dry_run else "rejected"
    return emit_write_result(
        args,
        "feedback reject",
        f"{action} feedback {args.id}",
        changed_files,
        check_result,
        extra_payload={"id": args.id, "item": deps.feedback_row_to_payload(row)},
    )


def feedback_archive_command(args: argparse.Namespace, *, deps: FeedbackDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    archive_date = date.fromisoformat(args.date) if args.date else date.today()
    reason = args.reason.strip()
    if not reason:
        raise SystemExit("feedback archive requires non-empty --reason")
    inbox_path = deps.feedback_inbox_path(root)
    rows = deps.read_feedback_rows(inbox_path)
    row = deps.find_feedback_row(rows, args.id)
    if row is None:
        raise SystemExit(f"feedback_not_found: {args.id}")
    if row.get("状态") not in {"Done", "Rejected"}:
        raise SystemExit(f"feedback_archive_blocked: {args.id} status is {row.get('状态', 'Unknown')}")
    archive_path = deps.feedback_archive_path(root, archive_date)
    if archive_path.exists():
        archive_rows = parse_markdown_table_rows(deps.read_text(archive_path))
        if any(len(cells) >= 2 and cells[1] == args.id for cells in archive_rows):
            raise SystemExit(f"feedback archive already contains id: {args.id}")
    inbox_changed, removed = deps.remove_feedback_row(inbox_path, args.id, dry_run)
    archive_changed = deps.append_feedback_archive_row(archive_path, archive_date, removed, reason, dry_run)
    changed_files = []
    if inbox_changed or dry_run:
        changed_files.append(inbox_path)
    if archive_changed or dry_run:
        changed_files.append(archive_path)
    check_result = deps.maybe_check_after(args, root, None)
    action = "would archive" if dry_run else "archived"
    return emit_write_result(
        args,
        "feedback archive",
        f"{action} feedback {args.id}",
        changed_files,
        check_result,
        extra_payload={
            "id": args.id,
            "archive_path": archive_path.relative_to(root).as_posix(),
            "item": deps.feedback_row_to_payload(removed),
        },
    )


def register_feedback_parsers(
    subparsers: Any,
    add_json_argument: Callable[..., None],
    add_write_arguments: Callable[..., None],
    *,
    list_handler: Callable[..., int],
    archive_candidates_handler: Callable[..., int],
    triage_handler: Callable[..., int],
    done_handler: Callable[..., int],
    reject_handler: Callable[..., int],
    archive_handler: Callable[..., int],
) -> None:
    """Register the `feedback` group (moved out of ``runtime.build_parser``).

    Handlers are injected because the CLI binds the ``runtime_parts`` adapters that
    supply each handler's dependencies.
    """

    feedback_parser = subparsers.add_parser("feedback", help="manage active/Feedback_Inbox.md lifecycle")
    feedback_subparsers = feedback_parser.add_subparsers(dest="feedback_command", required=True)

    feedback_list_parser = feedback_subparsers.add_parser("list", help="list feedback inbox rows")
    feedback_list_parser.add_argument("path", nargs="?", type=Path)
    feedback_list_parser.add_argument("--status", choices=tuple(sorted(VALID_FEEDBACK_STATUSES)), default=None)
    add_json_argument(feedback_list_parser)
    feedback_list_parser.set_defaults(func=list_handler)

    feedback_candidates_parser = feedback_subparsers.add_parser("archive-candidates", help="list feedback rows ready for explicit archive")
    feedback_candidates_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(feedback_candidates_parser)
    feedback_candidates_parser.set_defaults(func=archive_candidates_handler)

    feedback_triage_parser = feedback_subparsers.add_parser("triage", help="mark feedback Triaged and update next action")
    feedback_triage_parser.add_argument("path", nargs="?", type=Path)
    feedback_triage_parser.add_argument("id", type=validate_feedback_id)
    feedback_triage_parser.add_argument("--next-action", required=True, help="deterministic next handling step")
    feedback_triage_parser.add_argument("--evidence", default="", help="optional evidence or destination reference")
    add_write_arguments(feedback_triage_parser)
    feedback_triage_parser.set_defaults(func=triage_handler)

    feedback_done_parser = feedback_subparsers.add_parser("done", help="mark feedback Done")
    feedback_done_parser.add_argument("path", nargs="?", type=Path)
    feedback_done_parser.add_argument("id", type=validate_feedback_id)
    feedback_done_parser.add_argument("--result", required=True, help="handling result")
    feedback_done_parser.add_argument("--evidence", required=True, help="evidence or destination reference")
    add_write_arguments(feedback_done_parser)
    feedback_done_parser.set_defaults(func=done_handler)

    feedback_reject_parser = feedback_subparsers.add_parser("reject", help="mark feedback Rejected")
    feedback_reject_parser.add_argument("path", nargs="?", type=Path)
    feedback_reject_parser.add_argument("id", type=validate_feedback_id)
    feedback_reject_parser.add_argument("--reason", required=True, help="rejection reason")
    add_write_arguments(feedback_reject_parser)
    feedback_reject_parser.set_defaults(func=reject_handler)

    feedback_archive_parser = feedback_subparsers.add_parser("archive", help="archive one Done or Rejected feedback row")
    feedback_archive_parser.add_argument("path", nargs="?", type=Path)
    feedback_archive_parser.add_argument("id", type=validate_feedback_id)
    feedback_archive_parser.add_argument("--reason", required=True, help="archive reason or destination evidence")
    feedback_archive_parser.add_argument("--date", type=validate_date, default=None, help="archive date in YYYY-MM-DD; defaults to today")
    add_write_arguments(feedback_archive_parser)
    feedback_archive_parser.set_defaults(func=archive_handler)
