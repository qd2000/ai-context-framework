"""Command handlers for review, audit, and curation draft workflows."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from ai_context_framework.constants import (
    DEFAULT_STALE_DAYS,
    EXIT_SAFETY_REFUSED,
    JSON_SCHEMA_VERSION,
)
from ai_context_framework.validators.checks import validate_date, validate_draft_name
from ai_context_framework.json_contract import (
    check_error_code,
    check_payload,
    dry_run_enabled,
    error_next_actions,
    json_enabled,
    print_json,
    set_result_payload,
    write_next_actions,
)
from ai_context_framework.models import CheckResult
from ai_context_framework.paths import relative_display_path, require_context_root


MaybeCheckAfter = Callable[[argparse.Namespace, Path, str | None], CheckResult | None]


@dataclass(frozen=True)
class ReviewAuditCurateDependencies:
    maybe_check_after: MaybeCheckAfter
    parse_iso_date_value: Callable[..., Any]
    collect_review_stale_items: Callable[..., Any]
    review_stale_summary: Callable[..., Any]
    review_stale_next_actions: Callable[..., Any]
    collect_audit_context_candidates: Callable[..., Any]
    audit_context_summary: Callable[..., Any]
    audit_context_next_actions: Callable[..., Any]
    curation_draft_path: Callable[..., Any]
    render_curation_draft: Callable[..., Any]


def review_stale_command(args: argparse.Namespace, *, deps: ReviewAuditCurateDependencies) -> int:
    root = require_context_root(args.path)
    if args.days <= 0:
        raise SystemExit("--days must be greater than 0")
    today_value = deps.parse_iso_date_value(args.today) if args.today else date.today()
    if today_value is None:
        raise SystemExit("invalid --today date")
    stale_items = deps.collect_review_stale_items(root, args.days, today_value)
    warnings = [str(item["reason"]) for item in stale_items]
    payload: dict[str, object] = {
        "command": "review stale",
        "ok": True,
        "context": str(root),
        "days": args.days,
        "today": today_value.isoformat(),
        "summary": deps.review_stale_summary(stale_items),
        "warnings": warnings,
        "stale_items": stale_items,
        "error_code": None,
        "next_actions": deps.review_stale_next_actions(stale_items),
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        if stale_items:
            print(f"review stale: {len(stale_items)} candidate(s)")
        else:
            print("review stale: clean (0 candidate(s))")
        grouped: dict[str, list[dict[str, object]]] = {}
        for item in stale_items:
            grouped.setdefault(str(item.get("kind") or "unknown"), []).append(item)
        for kind in sorted(grouped):
            print(f"{kind}:")
            for item in grouped[kind]:
                item_id = f" {item['id']}" if "id" in item else ""
                print(f"- {item['path']}{item_id}: {item['signal']} - {item['reason']}")
        for action in payload["next_actions"]:
            print(f"next: {action}")
    return 0


def audit_context_command(args: argparse.Namespace, *, deps: ReviewAuditCurateDependencies) -> int:
    root = require_context_root(args.path)
    today_value = date.today()
    candidates = deps.collect_audit_context_candidates(root, today_value)
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "ok": True,
        "command": "audit context",
        "context": str(root),
        "candidates": candidates,
        "summary": deps.audit_context_summary(candidates),
        "next_actions": deps.audit_context_next_actions(candidates),
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        if candidates:
            print(f"audit context: {len(candidates)} candidate(s)")
        else:
            print("audit context: clean (0 candidate(s))")
        grouped: dict[str, list[dict[str, object]]] = {}
        for candidate in candidates:
            grouped.setdefault(str(candidate.get("kind") or "unknown"), []).append(candidate)
        for kind in sorted(grouped):
            print(f"{kind}:")
            for candidate in grouped[kind]:
                print(f"- {candidate['path']}: {candidate['severity']} - {candidate['reason']}")
        for action in payload["next_actions"]:
            print(f"next: {action}")
    return 0


def curate_draft_command(args: argparse.Namespace, *, deps: ReviewAuditCurateDependencies) -> int:
    root = require_context_root(args.path)
    if args.days <= 0:
        raise SystemExit("--days must be greater than 0")
    today_value = deps.parse_iso_date_value(args.today) if args.today else date.today()
    if today_value is None:
        raise SystemExit("invalid --today date")
    stale_items = deps.collect_review_stale_items(root, args.days, today_value)
    stale_summary = deps.review_stale_summary(stale_items)
    draft_path = deps.curation_draft_path(root, today_value, args.name)
    rel_draft_path = relative_display_path(draft_path, root)
    dry_run = dry_run_enabled(args)
    changed_files: list[Path] = []
    created = False
    message: str

    if not stale_items:
        message = "curate draft: clean; no stale candidates, no draft created"
    else:
        if draft_path.exists() and not dry_run:
            payload = {
                "command": "curate draft",
                "ok": False,
                "error_code": "curation_draft_exists",
                "draft_path": rel_draft_path,
                "created": False,
                "stale_summary": stale_summary,
                "stale_items": stale_items,
                "changed_files": [],
                "message": f"curation draft already exists: {rel_draft_path}",
                "next_actions": error_next_actions("curation_draft_exists"),
            }
            set_result_payload(args, payload)
            if json_enabled(args):
                print_json(payload)
            else:
                print(f"ERROR: {payload['message']}", file=sys.stderr)
            return EXIT_SAFETY_REFUSED
        changed_files = [draft_path]
        message = f"would create curation draft {rel_draft_path}" if dry_run else f"created curation draft {rel_draft_path}"
        if not dry_run:
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text(
                deps.render_curation_draft(today_value, args.days, stale_items, stale_summary),
                encoding="utf-8",
            )
            created = True

    check_result = deps.maybe_check_after(args, root, None)
    payload: dict[str, object] = {
        "command": "curate draft",
        "ok": check_result.ok if check_result is not None else True,
        "error_code": check_error_code(check_result),
        "dry_run": dry_run,
        "draft_path": rel_draft_path if stale_items else None,
        "created": created,
        "stale_summary": stale_summary,
        "stale_items": stale_items,
        "changed_files": [relative_display_path(path, root) for path in changed_files],
        "message": message,
        "next_actions": write_next_actions(dry_run, check_result, changed_files)
        if stale_items
        else deps.review_stale_next_actions(stale_items),
    }
    if dry_run and stale_items:
        payload["planned_draft"] = deps.render_curation_draft(today_value, args.days, stale_items, stale_summary)
    if check_result is not None:
        payload["check"] = check_payload(check_result)
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(message)
        if stale_items:
            label = "would change" if dry_run else "changed"
            for changed_file in changed_files:
                print(f"{label}: {relative_display_path(changed_file, root)}")
        for action in payload["next_actions"]:
            print(f"next: {action}")
    return 0 if check_result is None or check_result.ok else 1


def register_review_parser(
    subparsers: Any, add_json_argument: Callable[..., None], handler: Callable[..., int]
) -> None:
    """Register the read-only `review` parser group.

    Moved out of ``runtime.build_parser`` so the CLI aggregator stays thin. Both
    the argument helper and the handler are injected: the CLI binds the
    ``runtime_parts`` adapter that supplies the handler's dependencies, not the
    raw command function defined in this module.
    """

    review_parser = subparsers.add_parser("review", help="run read-only context review checks")
    review_subparsers = review_parser.add_subparsers(dest="review_command", required=True)

    review_stale_parser = review_subparsers.add_parser("stale", help="report stale attention-entry candidates")
    review_stale_parser.add_argument("path", nargs="?", type=Path)
    review_stale_parser.add_argument("--days", type=int, default=DEFAULT_STALE_DAYS, help="age threshold in days")
    review_stale_parser.add_argument("--today", type=validate_date, default=None, help="override today's date for deterministic checks")
    add_json_argument(review_stale_parser)
    review_stale_parser.set_defaults(func=handler)


def register_audit_parser(
    subparsers: Any, add_json_argument: Callable[..., None], handler: Callable[..., int]
) -> None:
    """Register the read-only `audit` parser group (moved out of ``build_parser``)."""

    audit_parser = subparsers.add_parser("audit", help="run read-only context audit checks")
    audit_subparsers = audit_parser.add_subparsers(dest="audit_command", required=True)

    audit_context_parser = audit_subparsers.add_parser("context", help="report context audit candidates")
    audit_context_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(audit_context_parser)
    audit_context_parser.set_defaults(func=handler)


def register_curate_parser(
    subparsers: Any,
    add_json_argument: Callable[..., None],
    add_write_arguments: Callable[..., None],
    handler: Callable[..., int],
) -> None:
    """Register the `curate` parser group (moved out of ``build_parser``)."""

    curate_parser = subparsers.add_parser("curate", help="create attention governance drafts")
    curate_subparsers = curate_parser.add_subparsers(dest="curate_command", required=True)

    curate_draft_parser = curate_subparsers.add_parser("draft", help="draft curation notes from review stale signals")
    curate_draft_parser.add_argument("path", nargs="?", type=Path)
    curate_draft_parser.add_argument("--days", type=int, default=DEFAULT_STALE_DAYS, help="age threshold in days")
    curate_draft_parser.add_argument("--today", type=validate_date, default=None, help="override today's date for deterministic drafts")
    curate_draft_parser.add_argument("--name", type=validate_draft_name, default=None, help="draft file name without .md")
    add_write_arguments(curate_draft_parser)
    curate_draft_parser.set_defaults(func=handler)
