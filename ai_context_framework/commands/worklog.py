"""Worklog command handler and rendering helpers."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

from ai_context_framework.constants import (
    ANCHOR_NOT_FOUND,
    APPEND_FORCE_CONFLICT,
    EXIT_INPUT_ERROR,
    EXIT_SAFETY_REFUSED,
    TARGET_EXISTS_APPEND_REQUIRED,
)
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
from ai_context_framework.markdown import append_section_text, section_insert_after_line
from ai_context_framework.models import CheckResult
from ai_context_framework.paths import context_json_path, require_context_root
from ai_context_framework.tables import clean_table_cell


CheckAfter = Callable[[argparse.Namespace, Path], CheckResult | None]


def render_worklog_daily(log_date: str, summary: str, conclusion: str) -> str:
    return f"""本文件记录当天整理后的项目工作记录。

请注意：本文件是历史过程记录，不是当前事实源。  
当前事实请查看 `active/Context.md`。

---

## 今日完成

- {summary}

---

## 今日讨论 / AI 协作

- 通过 `acf.py new worklog` 生成本工作记录，并更新 `worklog/Worklog_Index.md`。

---

## 有价值的结论

- {conclusion}

如果这些结论已经成为当前事实，请同步更新到 `active/Context.md`。

---

## 重要决策候选

- 无。

如果确认生效，请同步更新到：

- `reference/Decisions_Index.md`
- `decisions/`

---

## 无效尝试

- 无。

---

## 新发现的问题

- 无。

---

## 原始日志位置

- 无。

注意：不要把原始日志全文写入本文件。

---

## 需要同步更新的文件

- `active/Context.md`：视情况更新。
- `reference/Decisions_Index.md`：视情况更新。
- `rules/`：视情况更新。
- `archive/`：视情况归档。

---

## 下一步候选

- 无。

注意：下一步候选不等于当前任务。  
如果某个候选下一步被选为当前任务，请写入 `active/Current_Task.md`。
"""


def worklog_index_row(log_date: str, summary: str, conclusion: str) -> str:
    return (
        f"| {log_date} | {clean_table_cell(summary)} | {clean_table_cell(conclusion)} | "
        f"`worklog/daily/{log_date}.md` |"
    )


def row_date(row: str) -> str:
    cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
    return cells[0] if cells else ""


def update_worklog_index(index_path: Path, log_date: str, summary: str, conclusion: str, force: bool) -> None:
    if not index_path.exists():
        raise SystemExit(f"worklog index does not exist: {index_path}")

    lines = index_path.read_text(encoding="utf-8").splitlines()
    header_index = next(
        (index for index, line in enumerate(lines) if line.strip() == "| 日期 | 摘要 | 关键结论 | 详情 |"),
        None,
    )
    if header_index is None or header_index + 1 >= len(lines):
        raise SystemExit(f"worklog index table was not found: {index_path}")

    table_start = header_index + 2
    table_end = table_start
    while table_end < len(lines) and lines[table_end].strip().startswith("|"):
        table_end += 1

    existing_rows = lines[table_start:table_end]
    if any(row_date(row) == log_date for row in existing_rows) and not force:
        raise SystemExit(f"worklog index already contains date: {log_date}")

    new_row = worklog_index_row(log_date, summary, conclusion)
    kept_rows = [
        row
        for row in existing_rows
        if row_date(row) not in {log_date, "暂无"} and row.strip()
    ]
    rows = kept_rows + [new_row]
    rows.sort(key=row_date, reverse=True)

    updated = lines[:table_start] + rows + lines[table_end:]
    index_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def append_worklog_cell(existing: str, addition: str) -> str:
    addition = clean_table_cell(addition)
    if not addition or addition == "无。":
        return existing or "无。"
    if not existing or existing == "无。":
        return addition
    return f"{existing}; 追加：{addition}"


def update_worklog_index_append(index_path: Path, log_date: str, summary: str, conclusion: str) -> None:
    if not index_path.exists():
        raise SystemExit(f"worklog index does not exist: {index_path}")

    lines = index_path.read_text(encoding="utf-8").splitlines()
    header_index = next(
        (index for index, line in enumerate(lines) if line.strip() == "| 日期 | 摘要 | 关键结论 | 详情 |"),
        None,
    )
    if header_index is None or header_index + 1 >= len(lines):
        raise SystemExit(f"worklog index table was not found: {index_path}")

    table_start = header_index + 2
    table_end = table_start
    while table_end < len(lines) and lines[table_end].strip().startswith("|"):
        table_end += 1

    rows = [row for row in lines[table_start:table_end] if row_date(row) != "暂无" and row.strip()]
    updated_rows: list[str] = []
    replaced = False
    for row in rows:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if cells and cells[0] == log_date:
            while len(cells) < 4:
                cells.append("")
            cells[1] = append_worklog_cell(cells[1], summary)
            cells[2] = append_worklog_cell(cells[2], conclusion)
            row = f"| {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |"
            replaced = True
        updated_rows.append(row)

    if not replaced:
        updated_rows.append(worklog_index_row(log_date, summary, conclusion))
    updated_rows.sort(key=row_date, reverse=True)

    updated = lines[:table_start] + updated_rows + lines[table_end:]
    index_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def emit_worklog_error(
    args: argparse.Namespace,
    root: Path,
    target: Path,
    error_code: str,
    message: str,
    exit_code: int,
) -> int:
    payload: dict[str, object] = {
        "command": "new worklog",
        "ok": False,
        "error_code": error_code,
        "message": message,
        "target": context_json_path(root, target),
        "next_actions": error_next_actions(error_code),
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    return exit_code


def emit_worklog_result(
    args: argparse.Namespace,
    root: Path,
    message: str,
    changed_files: Sequence[Path],
    *,
    action: str,
    target: Path,
    anchor: str | None,
    created: bool,
    appended: bool,
    index_updated: bool,
    insert_after_line: int | None = None,
    check_result: CheckResult | None = None,
) -> int:
    dry_run = dry_run_enabled(args)
    changed = [context_json_path(root, path) for path in changed_files]
    payload: dict[str, object] = {
        "command": "new worklog",
        "ok": check_result.ok if check_result is not None else True,
        "error_code": check_error_code(check_result),
        "dry_run": dry_run,
        "changed_files": changed,
        "message": message,
        "next_actions": write_next_actions(dry_run, check_result, changed_files),
        "action": action,
        "target": context_json_path(root, target),
        "anchor": anchor,
        "created": created,
        "appended": appended,
        "index_updated": index_updated,
        "warnings": [],
    }
    if dry_run:
        payload["would_change"] = bool(changed_files)
        payload["operation"] = action
    if insert_after_line is not None:
        payload["insert_after_line"] = insert_after_line
    if check_result is not None:
        payload["check"] = check_payload(check_result)
    set_result_payload(args, payload)

    if json_enabled(args):
        print_json(payload)
    else:
        print(message)
        label = "would change" if dry_run else "changed"
        for changed_file in changed_files:
            print(f"{label}: {changed_file}")
        if check_result is not None:
            print(f"check: {'passed' if check_result.ok else 'failed'}")
            for error in check_result.errors:
                print(f"ERROR: {error}", file=sys.stderr)
            for warning in check_result.warnings:
                print(f"WARN: {warning}", file=sys.stderr)
    return 0 if check_result is None or check_result.ok else 1


def new_worklog_command(args: argparse.Namespace, *, maybe_check_after: CheckAfter) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)

    log_date = args.date or date.today().isoformat()
    summary = args.summary.strip()
    conclusion = args.conclusion.strip()
    if not summary:
        raise SystemExit("worklog summary cannot be empty")
    if not conclusion:
        conclusion = "无。"

    daily_dir = root / "worklog" / "daily"
    daily_path = daily_dir / f"{log_date}.md"
    index_path = root / "worklog" / "Worklog_Index.md"
    if not index_path.exists():
        raise SystemExit(f"worklog index does not exist: {index_path}")

    append = bool(getattr(args, "append", False))
    if append and args.force:
        return emit_worklog_error(
            args,
            root,
            daily_path,
            APPEND_FORCE_CONFLICT,
            "Use either --append or --force, not both.",
            EXIT_INPUT_ERROR,
        )

    changed_files = [daily_path, index_path]
    if daily_path.exists() and append:
        anchor = "## 今日完成"
        try:
            existing = daily_path.read_text(encoding="utf-8")
            insert_after_line = section_insert_after_line(existing, anchor)
            updated = append_section_text(existing, anchor, f"- {summary}")
            if conclusion != "无。":
                updated = append_section_text(updated, "## 有价值的结论", f"- {conclusion}")
        except SystemExit:
            return emit_worklog_error(
                args,
                root,
                daily_path,
                ANCHOR_NOT_FOUND,
                f"Worklog append anchor was not found: {anchor}",
                EXIT_INPUT_ERROR,
            )

        if not dry_run:
            daily_path.write_text(updated, encoding="utf-8")
            update_worklog_index_append(index_path, log_date, summary, conclusion)
        check_result = maybe_check_after(args, root)
        action = "would append" if dry_run else "appended"
        return emit_worklog_result(
            args,
            root,
            f"{action} worklog {daily_path}",
            changed_files,
            action="append",
            target=daily_path,
            anchor=anchor,
            created=False,
            appended=True,
            index_updated=True,
            insert_after_line=insert_after_line,
            check_result=check_result,
        )

    if daily_path.exists() and not args.force:
        return emit_worklog_error(
            args,
            root,
            daily_path,
            TARGET_EXISTS_APPEND_REQUIRED,
            "Worklog already exists. Use --append to add an entry or --force to replace it.",
            EXIT_SAFETY_REFUSED,
        )

    if not dry_run:
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_path.write_text(render_worklog_daily(log_date, summary, conclusion), encoding="utf-8")
        update_worklog_index(index_path, log_date, summary, conclusion, args.force)
    check_result = maybe_check_after(args, root)
    action = "would create" if dry_run else "created"
    return emit_worklog_result(
        args,
        root,
        f"{action} worklog {daily_path}",
        changed_files,
        action="create",
        target=daily_path,
        anchor=None,
        created=True,
        appended=False,
        index_updated=True,
        check_result=check_result,
    )
