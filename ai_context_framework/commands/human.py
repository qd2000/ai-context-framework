"""Command handlers for human-layer index workflows."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai_context_framework.constants import JSON_SCHEMA_VERSION
from ai_context_framework.json_contract import dry_run_enabled, emit_write_result, json_enabled, print_json, set_result_payload
from ai_context_framework.models import CheckResult
from ai_context_framework.paths import require_context_root


MaybeCheckAfter = Callable[[argparse.Namespace, Path, str | None], CheckResult | None]


@dataclass(frozen=True)
class HumanDependencies:
    maybe_check_after: MaybeCheckAfter
    sync_human_index: Callable[..., Any]
    human_index_row_to_payload: Callable[..., Any]
    human_index_path: Callable[..., Any]
    read_human_index_rows: Callable[..., Any]
    count_by_key: Callable[..., Any]
    find_human_index_row: Callable[..., Any]
    write_human_index: Callable[..., Any]


def human_index_sync_command(args: argparse.Namespace, *, deps: HumanDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    changed, rows, index_path = deps.sync_human_index(root, dry_run=dry_run)
    changed_files = [index_path] if changed or dry_run else []
    check_result = deps.maybe_check_after(args, root, None)
    action = "would sync" if dry_run else "synced"
    return emit_write_result(
        args,
        "human index sync",
        f"{action} human index",
        changed_files,
        check_result,
        extra_payload={
            "indexed_total": len(rows),
            "items": [deps.human_index_row_to_payload(row) for row in rows],
        },
    )


def human_list_command(args: argparse.Namespace, *, deps: HumanDependencies) -> int:
    root = require_context_root(args.path)
    index_path = deps.human_index_path(root)
    if not index_path.exists():
        raise SystemExit("human_index_missing: human/Human_Index.md does not exist; run `acf upgrade` or `acf human index sync`")
    rows = deps.read_human_index_rows(index_path)
    items = [deps.human_index_row_to_payload(row) for row in rows]
    if args.status:
        items = [item for item in items if item.get("status") == args.status]
    if args.type:
        items = [item for item in items if item.get("type") == args.type]
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "human list",
        "ok": True,
        "context": str(root),
        "changed_files": [],
        "items": items,
        "summary": {
            "total": len(items),
            "by_status": deps.count_by_key(items, "status"),
            "by_type": deps.count_by_key(items, "type"),
        },
        "error_code": None,
        "next_actions": ["No human index items matched."] if not items else [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        if not items:
            print("no human index items")
        for item in items:
            print(f"{item['id'] or item['path']} [{item['status']}] {item['title']}")
    return 0


def human_mark_command(args: argparse.Namespace, *, deps: HumanDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    index_path = deps.human_index_path(root)
    if not index_path.exists():
        raise SystemExit("human_index_missing: human/Human_Index.md does not exist; run `acf upgrade` or `acf human index sync`")
    rows = deps.read_human_index_rows(index_path)
    target = deps.find_human_index_row(rows, args.target)
    if target is None:
        raise SystemExit(f"human_index_item_not_found: {args.target}")
    target["状态"] = args.status
    if args.extracted_to:
        target["已整理到"] = args.extracted_to.strip()
    if args.note:
        target["备注"] = args.note.strip()
    changed = deps.write_human_index(index_path, rows, dry_run)
    changed_files = [index_path] if changed or dry_run else []
    check_result = deps.maybe_check_after(args, root, None)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(
        args,
        "human mark",
        f"{action} human index item {args.target}",
        changed_files,
        check_result,
        extra_payload={"item": deps.human_index_row_to_payload(target)},
    )
