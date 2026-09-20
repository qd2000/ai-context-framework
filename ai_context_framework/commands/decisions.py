"""Command handlers for decision index maintenance."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai_context_framework.json_contract import dry_run_enabled, emit_write_result
from ai_context_framework.markers import (
    DECISIONS_INDEX_MARKER_END,
    DECISIONS_INDEX_MARKER_START,
    insert_generated_marker_block_after_heading,
    replace_generated_marker_block,
)
from ai_context_framework.models import CheckResult
from ai_context_framework.paths import require_context_root


MaybeCheckAfter = Callable[[argparse.Namespace, Path, str | None], CheckResult | None]


@dataclass(frozen=True)
class DecisionsDependencies:
    maybe_check_after: MaybeCheckAfter
    decisions_index_path: Callable[..., Any]
    read_text: Callable[..., Any]
    collect_decision_sync_rows: Callable[..., Any]
    skipped_missing_generated_decision_details: Callable[..., Any]
    render_decisions_index_table: Callable[..., Any]


def decisions_sync_command(args: argparse.Namespace, *, deps: DecisionsDependencies) -> int:
    root = require_context_root(args.path)
    index_path = deps.decisions_index_path(root)
    if not index_path.exists():
        raise SystemExit(f"sync_source_invalid: decisions index does not exist: {index_path}")
    original = deps.read_text(index_path)
    rows, skipped, warnings = deps.collect_decision_sync_rows(root)
    skipped.extend(deps.skipped_missing_generated_decision_details(root, original))
    generated_table = deps.render_decisions_index_table(rows)

    if DECISIONS_INDEX_MARKER_START in original or DECISIONS_INDEX_MARKER_END in original:
        updated, changed = replace_generated_marker_block(
            original,
            DECISIONS_INDEX_MARKER_START,
            DECISIONS_INDEX_MARKER_END,
            generated_table,
        )
        initialized_marker = False
    elif args.init_marker:
        updated, changed = insert_generated_marker_block_after_heading(
            original,
            "## 当前有效决策",
            DECISIONS_INDEX_MARKER_START,
            DECISIONS_INDEX_MARKER_END,
            generated_table,
            replace_empty_table_header="| ID | 标题 | 状态 | 摘要 | 详情 |",
        )
        initialized_marker = True
    else:
        raise SystemExit("generated_marker_missing: reference/Decisions_Index.md is missing ACF:DECISIONS:INDEX-GENERATED markers")

    changed_files = [index_path] if changed else []
    if changed_files and not dry_run_enabled(args):
        index_path.write_text(updated, encoding="utf-8")
    check_result = deps.maybe_check_after(args, root, None)
    action = "would sync" if dry_run_enabled(args) else "synced"
    extra_payload: dict[str, object] = {
        "generated_count": len(rows),
        "skipped_items": skipped,
        "initialized_marker": initialized_marker,
    }
    if dry_run_enabled(args):
        extra_payload["planned_block"] = generated_table
    return emit_write_result(
        args,
        "decisions sync",
        f"{action} Decisions index generated block",
        changed_files,
        check_result,
        extra_payload=extra_payload,
        warnings=warnings,
    )


def register_decisions_parser(
    subparsers: Any, add_write_arguments: Callable[..., None], handler: Callable[..., int]
) -> None:
    """Register the `decisions` group (moved out of ``runtime.build_parser``)."""

    decisions_parser = subparsers.add_parser("decisions", help="manage decision index sync")
    decisions_subparsers = decisions_parser.add_subparsers(dest="decisions_command", required=True)

    decisions_sync_parser = decisions_subparsers.add_parser("sync", help="sync the generated Decisions index block")
    decisions_sync_parser.add_argument("path", nargs="?", type=Path)
    decisions_sync_parser.add_argument("--init-marker", action="store_true", help="insert generated markers when missing")
    add_write_arguments(decisions_sync_parser)
    decisions_sync_parser.set_defaults(func=handler)
