"""Command handlers for archive workflows."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai_context_framework.json_contract import dry_run_enabled, emit_write_result, json_enabled, print_json, set_result_payload
from ai_context_framework.markers import (
    ARCHIVE_INDEX_MARKER_END,
    ARCHIVE_INDEX_MARKER_START,
    insert_generated_marker_block_after_heading,
    replace_generated_marker_block,
)
from ai_context_framework.models import CheckResult
from ai_context_framework.paths import require_context_root
from ai_context_framework.tables import split_table_line


MaybeCheckAfter = Callable[[argparse.Namespace, Path, str | None], CheckResult | None]


@dataclass(frozen=True)
class ArchiveDependencies:
    maybe_check_after: MaybeCheckAfter
    archive_index_path: Callable[..., Any]
    read_text: Callable[..., Any]
    render_archive_index: Callable[..., Any]
    collect_archive_sync_rows: Callable[..., Any]
    skipped_missing_generated_archive_details: Callable[..., Any]
    render_archive_index_table: Callable[..., Any]
    archive_file: Callable[..., Any]
    current_task_path: Callable[..., Any]
    task_plan_path: Callable[..., Any]
    find_archive_table: Callable[..., Any]
    archive_table_header: str


def archive_sync_command(args: argparse.Namespace, *, deps: ArchiveDependencies) -> int:
    root = require_context_root(args.path)
    index_path = deps.archive_index_path(root)
    original = deps.read_text(index_path) if index_path.exists() else deps.render_archive_index()
    rows, skipped, warnings = deps.collect_archive_sync_rows(root)
    skipped.extend(deps.skipped_missing_generated_archive_details(root, original))
    generated_table = deps.render_archive_index_table(rows)

    if ARCHIVE_INDEX_MARKER_START in original or ARCHIVE_INDEX_MARKER_END in original:
        updated, changed = replace_generated_marker_block(
            original,
            ARCHIVE_INDEX_MARKER_START,
            ARCHIVE_INDEX_MARKER_END,
            generated_table,
        )
        initialized_marker = False
    elif args.init_marker:
        updated, changed = insert_generated_marker_block_after_heading(
            original,
            "## 归档条目",
            ARCHIVE_INDEX_MARKER_START,
            ARCHIVE_INDEX_MARKER_END,
            generated_table,
            replace_empty_table_header=deps.archive_table_header,
        )
        initialized_marker = True
    else:
        raise SystemExit("generated_marker_missing: archive/Archive_Index.md is missing ACF:ARCHIVE:INDEX-GENERATED markers")

    changed_files = [index_path] if changed or not index_path.exists() else []
    if changed_files and not dry_run_enabled(args):
        index_path.parent.mkdir(parents=True, exist_ok=True)
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
        "archive sync",
        f"{action} Archive index generated block",
        changed_files,
        check_result,
        extra_payload=extra_payload,
        warnings=warnings,
    )


def archive_current_task_command(args: argparse.Namespace, *, deps: ArchiveDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    changed = deps.archive_file(root, deps.current_task_path(root), "Task", args.reason, args.force, dry_run)
    check_result = deps.maybe_check_after(args, root, None)
    action = "would archive" if dry_run else "archived"
    return emit_write_result(args, "archive current-task", f"{action} current task", changed, check_result)


def archive_task_plan_command(args: argparse.Namespace, *, deps: ArchiveDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    changed = deps.archive_file(root, deps.task_plan_path(root), "Plan", args.reason, args.force, dry_run)
    check_result = deps.maybe_check_after(args, root, None)
    action = "would archive" if dry_run else "archived"
    return emit_write_result(args, "archive task-plan", f"{action} task plan", changed, check_result)


def archive_list_command(args: argparse.Namespace, *, deps: ArchiveDependencies) -> int:
    root = require_context_root(args.path)
    index_path = deps.archive_index_path(root)
    rows: list[dict[str, str]] = []
    if index_path.exists():
        lines = deps.read_text(index_path).splitlines()
        table, legacy = deps.find_archive_table(lines)
        keys = ["日期", "类型", "标题", "原因", "详情"] if legacy else ["日期", "类型", "ID", "原路径", "归档路径", "状态", "原因"]
        for line in lines[table.body_start : table.body_end]:
            cells = split_table_line(line)
            if len(cells) >= len(keys) and cells[0] != "暂无":
                rows.append(dict(zip(keys, cells)))
    payload: dict[str, object] = {
        "command": "archive list",
        "ok": True,
        "context": str(root),
        "archives": rows,
        "error_code": None,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        for row in rows:
            print(f"{row.get('日期')} {row.get('类型')} {row.get('ID') or row.get('标题')} {row.get('归档路径') or row.get('详情')}")
    return 0


def register_archive_parser(
    subparsers: Any,
    add_json_argument: Callable[..., None],
    add_write_arguments: Callable[..., None],
    *,
    current_task_handler: Callable[..., int],
    task_plan_handler: Callable[..., int],
    list_handler: Callable[..., int],
    sync_handler: Callable[..., int],
) -> None:
    """Register the `archive` group (moved out of ``runtime.build_parser``).

    Handlers are injected because the CLI binds the ``runtime_parts`` adapters that
    supply each handler's dependencies.
    """

    archive_parser = subparsers.add_parser("archive", help="archive inactive task context")
    archive_subparsers = archive_parser.add_subparsers(dest="archive_command", required=True)

    archive_task_parser = archive_subparsers.add_parser("current-task", help="archive active/Current_Task.md")
    archive_task_parser.add_argument("path", nargs="?", type=Path)
    archive_task_parser.add_argument("--reason", required=True, help="archive reason")
    archive_task_parser.add_argument("--force", action="store_true", help="archive even when Active")
    add_write_arguments(archive_task_parser)
    archive_task_parser.set_defaults(func=current_task_handler)

    archive_plan_parser = archive_subparsers.add_parser("task-plan", help="archive active/Task_Plan.md")
    archive_plan_parser.add_argument("path", nargs="?", type=Path)
    archive_plan_parser.add_argument("--reason", required=True, help="archive reason")
    archive_plan_parser.add_argument("--force", action="store_true", help="archive even when Active")
    add_write_arguments(archive_plan_parser)
    archive_plan_parser.set_defaults(func=task_plan_handler)

    archive_list_parser = archive_subparsers.add_parser("list", help="list archive index entries")
    archive_list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(archive_list_parser)
    archive_list_parser.set_defaults(func=list_handler)

    archive_sync_parser = archive_subparsers.add_parser("sync", help="sync the generated Archive index block")
    archive_sync_parser.add_argument("path", nargs="?", type=Path)
    archive_sync_parser.add_argument("--init-marker", action="store_true", help="insert generated markers when missing")
    add_write_arguments(archive_sync_parser)
    archive_sync_parser.set_defaults(func=sync_handler)
