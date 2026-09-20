"""Command handlers for creating context records and writeback drafts."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Sequence

from ai_context_framework.json_contract import dry_run_enabled, emit_write_result
from ai_context_framework.models import CheckResult
from ai_context_framework.paths import require_context_root
from ai_context_framework.tables import find_table, parse_markdown_table_rows
from ai_context_framework.validators.checks import validate_draft_name


MaybeCheckAfter = Callable[[argparse.Namespace, Path, str | None], CheckResult | None]


@dataclass(frozen=True)
class NewContextDependencies:
    maybe_check_after: MaybeCheckAfter
    next_adr_id: Callable[..., Any]
    render_adr: Callable[..., Any]
    update_decisions_index: Callable[..., Any]
    extract_current_task_status: Callable[..., Any]
    normalize_items: Callable[..., Any]
    render_current_task: Callable[..., Any]
    read_text: Callable[..., Any]
    update_sources_index: Callable[..., Any]
    normalize_new_object_target: Callable[..., Any]
    render_reference_document: Callable[..., Any]
    upsert_rules_index: Callable[..., Any]
    render_rule_document: Callable[..., Any]
    feedback_inbox_path: Callable[..., Any]
    read_feedback_rows: Callable[..., Any]
    next_feedback_id: Callable[..., Any]
    upsert_feedback_inbox: Callable[..., Any]
    human_notes_path: Callable[..., Any]
    read_table_rows_by_header: Callable[..., Any]
    next_human_note_id: Callable[..., Any]
    human_note_row: Callable[..., Any]
    row_date: Callable[..., Any]
    replace_table_rows: Callable[..., Any]
    human_index_path: Callable[..., Any]
    sync_human_index: Callable[..., Any]
    render_writeback_draft: Callable[..., Any]
    human_note_table_header: str


def new_adr_command(args: argparse.Namespace, *, deps: NewContextDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)

    decisions_dir = root / "decisions"
    adr_id = args.id or deps.next_adr_id(decisions_dir)
    adr_path = decisions_dir / f"{adr_id}.md"
    if adr_path.exists():
        raise SystemExit(f"ADR file already exists: {adr_path}")
    index_path = root / "reference" / "Decisions_Index.md"
    if not index_path.exists():
        raise SystemExit(f"decisions index does not exist: {index_path}")

    title = args.title.strip()
    summary = args.summary.strip()
    decision = args.decision.strip()
    context = args.context.strip() or "该决策由当前项目维护流程提出，需要进入 ADR 以便后续追溯。"
    if not title:
        raise SystemExit("ADR title cannot be empty")
    if not summary:
        raise SystemExit("ADR summary cannot be empty")
    if not decision:
        raise SystemExit("ADR decision cannot be empty")

    adr_date = args.date or date.today().isoformat()
    changed_files = [adr_path, index_path]
    if not dry_run:
        decisions_dir.mkdir(parents=True, exist_ok=True)
        adr_path.write_text(
            deps.render_adr(adr_id, title, args.status, adr_date, summary, decision, context),
            encoding="utf-8",
        )
        deps.update_decisions_index(index_path, adr_id, title, args.status, summary)
    check_result = deps.maybe_check_after(args, root, None)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "new adr", f"{action} ADR {adr_path}", changed_files, check_result)


def new_task_command(args: argparse.Namespace, *, deps: NewContextDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)

    task_path = root / "active" / "Current_Task.md"
    if task_path.exists():
        current_status = deps.extract_current_task_status(task_path)
        if current_status == "Active" and not args.force:
            raise SystemExit(f"current task is Active; use --force to replace it: {task_path}")

    title = args.title.strip()
    plan = getattr(args, "plan", "").strip() or "无。"
    task_id = getattr(args, "task_id", "").strip() or "无。"
    background = args.background.strip() or "该任务由当前维护流程创建，需要写入当前任务文件以便协作过程可追踪。"
    if not title:
        raise SystemExit("task title cannot be empty")

    goals = deps.normalize_items(args.goal, ("完成当前任务。",))
    inputs = deps.normalize_items(args.input, ("用户当前请求。", "`active/Context.md`。"))
    outputs = deps.normalize_items(args.output, ("更新后的 `active/Current_Task.md`。",))
    success = deps.normalize_items(args.success, ("任务目标已完成并通过必要验证。",))
    failures = deps.normalize_items(args.failure, ("目标无法验证。", "任务范围需要重新确认。"))
    constraints = deps.normalize_items(args.constraint, ("遵守当前项目规则。", "不引入无关依赖。"))
    non_goals = deps.normalize_items(args.non_goal, ("无。",))
    questions = deps.normalize_items(args.question, ("无。",))
    workstreams: list[str] = []
    for value in getattr(args, "workstream", None) or []:
        workstream_id = value.strip().upper()
        if not workstream_id:
            continue
        if not re.fullmatch(r"WS\d{3}", workstream_id):
            raise SystemExit(f"workstream_invalid_id: {workstream_id}")
        if not (root / "active" / "workstreams" / f"{workstream_id}.md").exists():
            raise SystemExit(f"workstream_not_found: {workstream_id}")
        if workstream_id not in workstreams:
            workstreams.append(workstream_id)

    if not dry_run:
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(
            deps.render_current_task(
                args.status,
                title,
                plan,
                task_id,
                goals,
                background,
                inputs,
                outputs,
                success,
                failures,
                constraints,
                non_goals,
                questions,
                workstreams,
            ),
            encoding="utf-8",
        )
    check_result = deps.maybe_check_after(args, root, None)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "new task", f"{action} current task {task_path}", [task_path], check_result)


def new_source_command(args: argparse.Namespace, *, deps: NewContextDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)

    title = args.title.strip()
    source_type = args.type.strip()
    location = args.location.strip()
    relation = args.relation.strip()
    credibility = args.credibility.strip() or "未评估"
    next_action = args.next_action.strip() or "无。"
    if not title:
        raise SystemExit("source title cannot be empty")
    if not source_type:
        raise SystemExit("source type cannot be empty")
    if not location:
        raise SystemExit("source location cannot be empty")
    if not relation:
        raise SystemExit("source relation cannot be empty")

    index_path = root / "reference" / "Sources_Index.md"
    if dry_run:
        if not index_path.exists():
            raise SystemExit(f"sources index does not exist: {index_path}")
        rows = parse_markdown_table_rows(deps.read_text(index_path))
        if any(cells and cells[0] == title for cells in rows) and not args.force:
            raise SystemExit(f"sources index already contains source: {title}")
    else:
        deps.update_sources_index(
            index_path,
            title,
            source_type,
            location,
            args.status,
            credibility,
            relation,
            next_action,
            args.force,
        )
    check_result = deps.maybe_check_after(args, root, None)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "new source", f"{action} source entry {title}", [index_path], check_result)


def new_reference_command(args: argparse.Namespace, *, deps: NewContextDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)

    title = args.title.strip()
    summary = args.summary.strip()
    next_action = args.next_action.strip() or "无。"
    if not title:
        raise SystemExit("reference title cannot be empty")
    if not summary:
        raise SystemExit("reference summary cannot be empty")
    body_items = deps.normalize_items(args.body, ("待补充。",))
    target = deps.normalize_new_object_target(
        root,
        args.file,
        title,
        "reference",
        forbidden_prefixes=("reference/knowledge/",),
    )
    if target.exists() and not args.force:
        raise SystemExit(f"reference file already exists: {target}")

    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            deps.render_reference_document(title, args.status, summary, body_items, next_action),
            encoding="utf-8",
        )
    check_result = deps.maybe_check_after(args, root, None)
    action = "would create" if dry_run else "created"
    rel = target.relative_to(root).as_posix()
    return emit_write_result(
        args,
        "new reference",
        f"{action} reference {rel}",
        [target],
        check_result,
        extra_payload={"target": rel},
    )


def new_rule_command(args: argparse.Namespace, *, deps: NewContextDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)

    title = args.title.strip()
    condition = args.condition.strip()
    purpose = args.purpose.strip()
    rationale = args.rationale.strip() or "该规则由当前上下文维护流程提出，用于降低后续协作歧义。"
    scope = args.scope.strip() or "本上下文内按读取条件触发的协作任务。"
    non_goal = args.non_goal.strip() or "不替代用户当前指令；不要求默认读取全部规则。"
    if not title:
        raise SystemExit("rule title cannot be empty")
    if not condition:
        raise SystemExit("rule condition cannot be empty")
    if not purpose:
        raise SystemExit("rule purpose cannot be empty")
    rules = deps.normalize_items(args.rule, ())
    if not rules:
        raise SystemExit("rule command requires at least one --rule")

    target = deps.normalize_new_object_target(root, args.file, title, "rules")
    if target.exists() and not args.force:
        raise SystemExit(f"rule file already exists: {target}")

    index_path = root / "rules" / "Rules_Index.md"
    index_changed = deps.upsert_rules_index(
        index_path,
        target.relative_to(root / "rules").as_posix(),
        condition,
        purpose,
        args.force,
        dry_run,
    )

    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            deps.render_rule_document(title, condition, rules, rationale, scope, non_goal),
            encoding="utf-8",
        )
    changed_files = [target]
    if index_changed or not index_path.exists() or dry_run:
        changed_files.append(index_path)
    check_result = deps.maybe_check_after(args, root, None)
    action = "would create" if dry_run else "created"
    rel = target.relative_to(root).as_posix()
    return emit_write_result(
        args,
        "new rule",
        f"{action} rule {rel}",
        changed_files,
        check_result,
        extra_payload={"target": rel, "index_updated": index_changed},
    )


def new_feedback_command(args: argparse.Namespace, *, deps: NewContextDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)

    inbox_path = deps.feedback_inbox_path(root)
    if not inbox_path.exists():
        raise SystemExit(f"feedback inbox does not exist: {inbox_path}")

    existing_rows = deps.read_feedback_rows(inbox_path)
    feedback_id = (args.id or deps.next_feedback_id(existing_rows)).strip()
    if not re.match(r"^F\d{3}$", feedback_id):
        raise SystemExit("feedback id must use FNNN format, for example F019")
    feedback_type = args.type.strip()
    content = args.content.strip()
    source = args.source.strip() if args.source else f"{date.today().isoformat()} manual"
    next_action = args.next_action.strip() or "待 triage。"
    if not feedback_type:
        raise SystemExit("feedback type cannot be empty")
    if not content:
        raise SystemExit("feedback content cannot be empty")
    if not source:
        raise SystemExit("feedback source cannot be empty")

    changed = deps.upsert_feedback_inbox(
        inbox_path,
        feedback_id,
        args.status,
        feedback_type,
        content,
        source,
        next_action,
        args.force,
        dry_run,
    )
    changed_files = [inbox_path] if changed or dry_run else []
    check_result = deps.maybe_check_after(args, root, None)
    action = "would create" if dry_run else "created"
    return emit_write_result(
        args,
        "new feedback",
        f"{action} feedback {feedback_id}",
        changed_files,
        check_result,
        extra_payload={"id": feedback_id},
    )


def new_human_note_command(args: argparse.Namespace, *, deps: NewContextDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)

    note_path = deps.human_notes_path(root)
    if not note_path.exists():
        raise SystemExit("human_notes_missing: human/Human_Notes.md does not exist; use a standard context or `acf new feedback`")

    existing_rows = deps.read_table_rows_by_header(note_path, deps.human_note_table_header)
    note_id = (args.id or deps.next_human_note_id(existing_rows)).strip()
    if not re.match(r"^H\d{3}$", note_id):
        raise SystemExit("human note id must use HNNN format, for example H001")
    note_type = args.type.strip()
    content = args.content.strip()
    related = args.related.strip() if args.related else "无。"
    suggestion = args.suggestion.strip() if args.suggestion else "AI 看到后先判断是否需要整理到 active、ADR、Knowledge 或 worklog。"
    evidence = args.evidence.strip() if args.evidence else "未整理。"
    if not note_type:
        raise SystemExit("human note type cannot be empty")
    if not content:
        raise SystemExit("human note content cannot be empty")

    text = deps.read_text(note_path)
    lines = text.splitlines()
    table = find_table(lines, deps.human_note_table_header)
    existing_lines = lines[table.body_start : table.body_end]
    if any(deps.row_date(row) == note_id for row in existing_lines) and not args.force:
        raise SystemExit(f"human notes already contains id: {note_id}")
    new_row = deps.human_note_row(note_id, args.status, note_type, content, related, suggestion, evidence)
    kept_rows = [row for row in existing_lines if deps.row_date(row) not in {note_id, "暂无"} and row.strip()]
    rows = kept_rows + [new_row]
    rows.sort(key=deps.row_date)
    updated_text = deps.replace_table_rows(text, deps.human_note_table_header, rows)
    changed = updated_text != text
    if changed and not dry_run:
        note_path.write_text(updated_text, encoding="utf-8")
    index_path = deps.human_index_path(root)
    index_changed = False
    if changed and not dry_run:
        index_changed, _rows, _index_path = deps.sync_human_index(root, dry_run=False, note_date=date.today().isoformat())
    elif changed or dry_run:
        index_changed = True
    changed_files = [note_path] if changed or dry_run else []
    if index_changed:
        changed_files.append(index_path)
    check_result = deps.maybe_check_after(args, root, None)
    action = "would create" if dry_run else "created"
    return emit_write_result(
        args,
        "new human-note",
        f"{action} human note {note_id}",
        changed_files,
        check_result,
        extra_payload={"id": note_id},
    )


def read_writeback_input(args: argparse.Namespace) -> str:
    if args.text and args.input:
        raise SystemExit("use either --text or --input, not both")
    if args.text:
        return args.text
    if args.input:
        input_path = args.input.resolve()
        if not input_path.is_file():
            raise SystemExit(f"writeback input file does not exist: {input_path}")
        return input_path.read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("writeback draft requires --text, --input, or stdin")


def writeback_draft_command(args: argparse.Namespace, *, deps: NewContextDependencies) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)

    draft_name = args.name or date.today().isoformat()
    input_text = read_writeback_input(args).strip()
    if not input_text:
        raise SystemExit("writeback input cannot be empty")

    draft_dir = root / "worklog" / "writeback-drafts"
    draft_path = draft_dir / f"{draft_name}.md"
    if draft_path.exists() and not args.force:
        raise SystemExit(f"writeback draft already exists: {draft_path}")

    if not dry_run:
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(deps.render_writeback_draft(draft_name, input_text), encoding="utf-8")
    check_result = deps.maybe_check_after(args, root, None)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "writeback draft", f"{action} writeback draft {draft_path}", [draft_path], check_result)


def register_writeback_parser(
    subparsers: Any,
    add_write_arguments: Callable[..., None],
    handler: Callable[..., int],
) -> None:
    """Register the `writeback` group (moved out of ``runtime.build_parser``)."""

    writeback_parser = subparsers.add_parser("writeback", help="create reviewable writeback drafts")
    writeback_subparsers = writeback_parser.add_subparsers(dest="writeback_command", required=True)

    draft_parser = writeback_subparsers.add_parser("draft", help="create a session writeback draft")
    draft_parser.add_argument("path", nargs="?", type=Path)
    draft_parser.add_argument("--name", type=validate_draft_name, default=None, help="draft file name without .md")
    draft_parser.add_argument("--text", default="", help="writeback suggestion text")
    draft_parser.add_argument("--input", type=Path, default=None, help="file containing writeback suggestion text")
    draft_parser.add_argument("--force", action="store_true", help="replace an existing draft")
    add_write_arguments(draft_parser)
    draft_parser.set_defaults(func=handler)
