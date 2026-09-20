"""Command handlers for Knowledge workflows."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Sequence

from ai_context_framework.json_contract import dry_run_enabled, emit_write_result, json_enabled, print_json, set_result_payload
from ai_context_framework.front_matter import format_front_matter, parse_front_matter
from ai_context_framework.markers import (
    KNOWLEDGE_INDEX_MARKER_END,
    KNOWLEDGE_INDEX_MARKER_START,
    insert_generated_marker_block_after_heading,
    replace_generated_marker_block,
)
from ai_context_framework.markdown import append_section_text, replace_section_text
from ai_context_framework.models import CheckResult, KnowledgeEntry
from ai_context_framework.paths import require_context_root
from ai_context_framework.tables import find_table, render_table_row, split_table_line
from ai_context_framework.validators.checks import validate_knowledge_id
from ai_context_framework.constants import VALID_KNOWLEDGE_STATUSES


MaybeCheckAfter = Callable[[argparse.Namespace, Path, str | None], CheckResult | None]


@dataclass(frozen=True)
class KnowledgeDependencies:
    maybe_check_after: MaybeCheckAfter
    resolve_context_existing_path: Callable[..., Any]
    slugify_file_stem: Callable[..., Any]
    render_knowledge_draft: Callable[..., Any]
    knowledge_index_path: Callable[..., Any]
    read_text: Callable[..., Any]
    render_knowledge_index: Callable[..., Any]
    collect_knowledge_sync_rows: Callable[..., Any]
    skipped_missing_generated_knowledge_details: Callable[..., Any]
    render_knowledge_index_table: Callable[..., Any]
    resolve_knowledge_draft: Callable[..., Any]
    knowledge_title_from_text: Callable[..., Any]
    extract_heading_value: Callable[..., Any]
    safe_section_body_from_text: Callable[..., Any]
    similar_knowledge_entries: Callable[..., Any]
    collect_knowledge_entries: Callable[..., Any]
    next_knowledge_id: Callable[..., Any]
    update_knowledge_index: Callable[..., Any]
    knowledge_detail_path: Callable[..., Any]
    knowledge_table_header: str
    valid_knowledge_statuses: set[str]


def knowledge_draft_command(args: argparse.Namespace, *, deps: KnowledgeDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    title = args.title.strip()
    if not title:
        raise SystemExit("knowledge title cannot be empty")
    sources = [source.strip() for source in args.source if source.strip()]
    if not sources:
        raise SystemExit("knowledge draft requires at least one --source")
    for source in sources:
        deps.resolve_context_existing_path(root, source)
    draft_dir = root / "worklog" / "knowledge-drafts"
    draft_path = draft_dir / f"{date.today().isoformat()}-{deps.slugify_file_stem(title)}.md"
    if draft_path.exists() and not args.force:
        raise SystemExit(f"knowledge draft already exists: {draft_path}")
    if not dry_run:
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(
            deps.render_knowledge_draft(
                title,
                sources,
                args.tag,
                args.summary,
                getattr(args, "evidence", None),
                getattr(args, "applies_to", None),
                getattr(args, "not_applies_to", None),
                getattr(args, "read_when", None),
                getattr(args, "from_workstream", None),
            ),
            encoding="utf-8",
        )
    check_result = deps.maybe_check_after(args, root, None)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "knowledge draft", f"{action} knowledge draft {draft_path}", [draft_path], check_result)


def knowledge_sync_command(args: argparse.Namespace, *, deps: KnowledgeDependencies) -> int:
    root = require_context_root(args.path)
    index_path = deps.knowledge_index_path(root)
    if index_path.exists():
        original = deps.read_text(index_path)
    else:
        original = deps.render_knowledge_index()

    rows, skipped, warnings = deps.collect_knowledge_sync_rows(root)
    skipped.extend(deps.skipped_missing_generated_knowledge_details(root, original))
    generated_table = deps.render_knowledge_index_table(rows)

    if KNOWLEDGE_INDEX_MARKER_START in original or KNOWLEDGE_INDEX_MARKER_END in original:
        updated, changed = replace_generated_marker_block(
            original,
            KNOWLEDGE_INDEX_MARKER_START,
            KNOWLEDGE_INDEX_MARKER_END,
            generated_table,
        )
        initialized_marker = False
    elif args.init_marker:
        updated, changed = insert_generated_marker_block_after_heading(
            original,
            "## Knowledge 条目",
            KNOWLEDGE_INDEX_MARKER_START,
            KNOWLEDGE_INDEX_MARKER_END,
            generated_table,
            replace_empty_table_header=deps.knowledge_table_header,
        )
        initialized_marker = True
    else:
        raise SystemExit("generated_marker_missing: reference/Knowledge_Index.md is missing ACF:KNOWLEDGE:INDEX-GENERATED markers")

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
        "knowledge sync",
        f"{action} Knowledge index generated block",
        changed_files,
        check_result,
        extra_payload=extra_payload,
        warnings=warnings,
    )


def knowledge_apply_command(args: argparse.Namespace, *, deps: KnowledgeDependencies) -> int:
    draft_arg = getattr(args, "draft_option", None) or args.draft
    context_arg = args.path
    if getattr(args, "draft_option", None) is not None and context_arg is None:
        context_arg = args.draft
    root = require_context_root(context_arg)
    dry_run = dry_run_enabled(args)
    draft_path = deps.resolve_knowledge_draft(root, draft_arg)
    text = deps.read_text(draft_path)
    metadata, body, _diagnostics = parse_front_matter(text)
    title = deps.knowledge_title_from_text(text, draft_path.stem)
    status = deps.extract_heading_value(draft_path, "## 状态") or "Draft"
    if isinstance(metadata.get("status"), str):
        status = str(metadata["status"])
    if status not in deps.valid_knowledge_statuses:
        raise SystemExit(f"invalid knowledge status: {status}")
    tags = deps.extract_heading_value(draft_path, "## 标签") or "未分类"
    if isinstance(metadata.get("tags"), list) and metadata["tags"]:
        tags = ", ".join(metadata["tags"])
    summary = deps.extract_heading_value(draft_path, "## 摘要") or "无。"
    candidate = KnowledgeEntry(
        knowledge_id="KNEW",
        title=title,
        status=status,
        summary=summary,
        conclusion=deps.safe_section_body_from_text(text, "## 结论"),
        path=draft_path,
    )
    similar = deps.similar_knowledge_entries(candidate, deps.collect_knowledge_entries(root))
    if similar and not args.allow_similar and not dry_run:
        ids = ", ".join(str(item["id"]) for item in similar)
        raise SystemExit(f"similar knowledge already exists; use --allow-similar to apply anyway: {ids}")
    knowledge_id = deps.next_knowledge_id(root)
    destination = root / "reference" / "knowledge" / f"{knowledge_id}-{deps.slugify_file_stem(title)}.md"
    if destination.exists():
        raise SystemExit(f"knowledge file already exists: {destination}")
    changed = [destination, deps.knowledge_index_path(root)]
    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if metadata:
            metadata["id"] = knowledge_id
            metadata.setdefault("status", status)
            updated_body = body.replace("# K-草案：", f"# {knowledge_id}：", 1)
            updated_text = format_front_matter(metadata, updated_body)
        else:
            updated_text = text.replace("# K-草案：", f"# {knowledge_id}：", 1)
        destination.write_text(updated_text, encoding="utf-8")
        deps.update_knowledge_index(root, knowledge_id, title, status, tags, summary, destination.relative_to(root).as_posix())
    check_result = deps.maybe_check_after(args, root, None)
    action = "would apply" if dry_run else "applied"
    warnings = [f"similar knowledge detected: {item['id']} {item['title']}" for item in similar]
    return emit_write_result(
        args,
        "knowledge apply",
        f"{action} knowledge {knowledge_id}",
        changed,
        check_result,
        extra_payload={"similar_knowledge": similar},
        warnings=warnings,
    )


def knowledge_list_command(args: argparse.Namespace, *, deps: KnowledgeDependencies) -> int:
    root = require_context_root(args.path)
    rows: list[dict[str, str]] = []
    index_path = deps.knowledge_index_path(root)
    if index_path.exists():
        table = find_table(deps.read_text(index_path).splitlines(), deps.knowledge_table_header)
        for line in deps.read_text(index_path).splitlines()[table.body_start : table.body_end]:
            cells = split_table_line(line)
            if len(cells) >= 6 and cells[0] != "暂无":
                rows.append(dict(zip(["ID", "标题", "状态", "标签", "摘要", "详情"], cells)))
    payload: dict[str, object] = {
        "command": "knowledge list",
        "ok": True,
        "context": str(root),
        "knowledge": rows,
        "error_code": None,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        for row in rows:
            print(f"{row.get('ID')} {row.get('状态')} {row.get('标题')}")
    return 0


def knowledge_show_command(args: argparse.Namespace, *, deps: KnowledgeDependencies) -> int:
    root = require_context_root(args.path)
    detail = deps.knowledge_detail_path(root, args.id)
    text = deps.read_text(detail)
    payload: dict[str, object] = {
        "command": "knowledge show",
        "ok": True,
        "context": str(root),
        "id": args.id,
        "file": str(detail),
        "body": text,
        "error_code": None,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(text)
    return 0


def knowledge_mark_command(args: argparse.Namespace, *, deps: KnowledgeDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    detail = deps.knowledge_detail_path(root, args.id)
    original = deps.read_text(detail)
    metadata, body, _diagnostics = parse_front_matter(original)
    if metadata:
        metadata["status"] = args.status
        text = format_front_matter(metadata, replace_section_text(body, "## 状态", args.status))
    else:
        text = replace_section_text(original, "## 状态", args.status)
    if args.status == "Promoted" and not args.promoted_to.strip():
        raise SystemExit("--promoted-to is required when status is Promoted")
    if args.promoted_to.strip():
        addition = f"\n\nPromoted to: `{args.promoted_to.strip()}`"
        text = append_section_text(text, "## 与现有事实源的关系", addition)
    if not dry_run:
        detail.write_text(text, encoding="utf-8")
        index_path = deps.knowledge_index_path(root)
        lines = deps.read_text(index_path).splitlines()
        table = find_table(lines, deps.knowledge_table_header)
        rows = lines[table.body_start : table.body_end]
        updated_rows = []
        for row in rows:
            cells = split_table_line(row)
            if len(cells) >= 6 and cells[0] == args.id:
                cells[2] = args.status
                row = render_table_row(cells)
            updated_rows.append(row)
        index_path.write_text("\n".join(lines[: table.body_start] + updated_rows + lines[table.body_end :]).rstrip() + "\n", encoding="utf-8")
    check_result = deps.maybe_check_after(args, root, None)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(
        args,
        "knowledge mark",
        f"{action} knowledge {args.id}",
        [detail, deps.knowledge_index_path(root)],
        check_result,
        extra_payload={"id": args.id, "status": args.status},
    )


def register_knowledge_parsers(
    subparsers: Any,
    add_json_argument: Callable[..., None],
    add_write_arguments: Callable[..., None],
    *,
    draft_handler: Callable[..., int],
    apply_handler: Callable[..., int],
    list_handler: Callable[..., int],
    show_handler: Callable[..., int],
    mark_handler: Callable[..., int],
    sync_handler: Callable[..., int],
) -> None:
    """Register the `knowledge` group (moved out of ``runtime.build_parser``).

    Handlers are injected because the CLI binds the ``runtime_parts`` adapters that
    supply each handler's dependencies.
    """

    knowledge_parser = subparsers.add_parser("knowledge", help="manage reusable knowledge drafts and entries")
    knowledge_subparsers = knowledge_parser.add_subparsers(dest="knowledge_command", required=True)

    knowledge_draft_parser = knowledge_subparsers.add_parser("draft", help="create a reviewable knowledge draft")
    knowledge_draft_parser.add_argument("path", nargs="?", type=Path)
    knowledge_draft_parser.add_argument("--title", required=True, help="knowledge title")
    knowledge_draft_parser.add_argument("--source", action="append", required=True, help="source path inside context; can be repeated")
    knowledge_draft_parser.add_argument("--from-workstream", default=None, help="Workstream id that produced this draft")
    knowledge_draft_parser.add_argument("--evidence", action="append", default=None, help="evidence path; can be repeated")
    knowledge_draft_parser.add_argument("--applies-to", action="append", default=None, help="applicable scenario; can be repeated")
    knowledge_draft_parser.add_argument("--not-applies-to", action="append", default=None, help="non-applicable scenario; can be repeated")
    knowledge_draft_parser.add_argument("--read-when", action="append", default=None, help="read recommendation trigger; can be repeated")
    knowledge_draft_parser.add_argument("--tag", default="未分类", help="knowledge tags")
    knowledge_draft_parser.add_argument("--summary", default="待补充。", help="one-line summary")
    knowledge_draft_parser.add_argument("--force", action="store_true", help="replace existing draft")
    add_write_arguments(knowledge_draft_parser)
    knowledge_draft_parser.set_defaults(func=draft_handler)

    knowledge_apply_parser = knowledge_subparsers.add_parser("apply", help="apply a knowledge draft")
    knowledge_apply_parser.add_argument("draft", type=Path, help="draft path")
    knowledge_apply_parser.add_argument("path", nargs="?", type=Path, help="context path")
    knowledge_apply_parser.add_argument("--draft", dest="draft_option", type=Path, default=None, help="draft path when the positional argument is the context path")
    knowledge_apply_parser.add_argument("--allow-similar", action="store_true", help="apply even when similar Knowledge exists")
    add_write_arguments(knowledge_apply_parser)
    knowledge_apply_parser.set_defaults(func=apply_handler)

    knowledge_list_parser = knowledge_subparsers.add_parser("list", help="list knowledge entries")
    knowledge_list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(knowledge_list_parser)
    knowledge_list_parser.set_defaults(func=list_handler)

    knowledge_show_parser = knowledge_subparsers.add_parser("show", help="show a knowledge entry")
    knowledge_show_parser.add_argument("path", nargs="?", type=Path)
    knowledge_show_parser.add_argument("--id", type=validate_knowledge_id, required=True, help="knowledge id")
    add_json_argument(knowledge_show_parser)
    knowledge_show_parser.set_defaults(func=show_handler)

    knowledge_mark_parser = knowledge_subparsers.add_parser("mark", help="mark knowledge status")
    knowledge_mark_parser.add_argument("path", nargs="?", type=Path)
    knowledge_mark_parser.add_argument("--id", type=validate_knowledge_id, required=True, help="knowledge id")
    knowledge_mark_parser.add_argument("--status", choices=tuple(sorted(VALID_KNOWLEDGE_STATUSES)), required=True)
    knowledge_mark_parser.add_argument("--promoted-to", default="", help="target authority when status is Promoted")
    add_write_arguments(knowledge_mark_parser)
    knowledge_mark_parser.set_defaults(func=mark_handler)

    knowledge_sync_parser = knowledge_subparsers.add_parser("sync", help="sync the generated Knowledge index block")
    knowledge_sync_parser.add_argument("path", nargs="?", type=Path)
    knowledge_sync_parser.add_argument("--init-marker", action="store_true", help="insert generated markers when missing")
    add_write_arguments(knowledge_sync_parser)
    knowledge_sync_parser.set_defaults(func=sync_handler)
