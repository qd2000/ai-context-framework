#!/usr/bin/env python3
"""Small CLI for generating and checking AI context framework directories."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT / "template"

STANDARD_DIRS = (
    "active",
    "rules",
    "reference",
    "reference/sources",
    "decisions",
    "worklog",
    "worklog/daily",
    "archive",
)

STANDARD_FILES = (
    "AGENTS.md",
    "active/Context.md",
    "active/Current_Task.md",
    "rules/Always_Active.md",
    "rules/Project_Rules.md",
    "rules/Coding_Rules.md",
    "rules/Writing_Rules.md",
    "rules/Review_Rules.md",
    "rules/Rules_Index.md",
    "rules/Agent_Requested.md",
    "rules/Manual_Only.md",
    "reference/Project_Brief.md",
    "reference/Architecture.md",
    "reference/Tech_Context.md",
    "reference/Decisions_Index.md",
    "reference/Sources_Index.md",
    "reference/System_Manual.md",
    "decisions/ADR-0001-template.md",
    "worklog/Worklog_Index.md",
    "worklog/daily/YYYY-MM-DD.md",
)

MINIMAL_DIRS = (
    "active",
    "rules",
    "reference",
    "decisions",
    "worklog",
    "worklog/daily",
)

MINIMAL_FILES = (
    "AGENTS.md",
    "active/Context.md",
    "active/Current_Task.md",
    "rules/Always_Active.md",
    "rules/Project_Rules.md",
    "reference/Project_Brief.md",
    "reference/Decisions_Index.md",
    "reference/Sources_Index.md",
    "decisions/ADR-0001-template.md",
    "worklog/Worklog_Index.md",
    "worklog/daily/YYYY-MM-DD.md",
)

VALID_TASK_STATUSES = {"Active", "Paused", "Done", "Empty"}
VALID_DECISION_STATUSES = {"Active", "Proposed", "Superseded", "Rejected", "Deprecated"}
VALID_SOURCE_STATUSES = {"To Read", "Reading", "Read", "Useful", "Archived", "Rejected"}
PLACEHOLDER_RE = re.compile(r"【[^】]+】")
MARKDOWN_REF_RE = re.compile(r"`([^`\n]+\.md)`")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MINIMAL_AGENTS = """本文件告诉 AI 助手如何进入、理解和协助本项目。

本目录是简化版 AI 上下文根目录。默认只读取当前有效上下文和核心规则，其他资料按需读取。

---

## 默认读取顺序

1. `active/Context.md`
2. `rules/Always_Active.md`
3. `active/Current_Task.md`（仅当任务状态为 Active 时）

如果用户在当前消息中已给出明确任务，以用户当前消息为准。

---

## 目录结构

```text
active/      当前阶段上下文和当前任务
rules/       核心规则
reference/   长期背景、资料索引和决策索引
decisions/   重要决策详情
worklog/     整理后的工作记录
```

---

## 按需读取指引

| 场景 | 读取文件 |
|---|---|
| 需要理解长期背景 | `reference/Project_Brief.md` |
| 需要追溯重要决策 | `reference/Decisions_Index.md` -> `decisions/ADR-*.md` |
| 涉及项目通用约束 | `rules/Project_Rules.md` |
| 需要了解近期进展 | `worklog/Worklog_Index.md` |
| 涉及外部资料来源 | `reference/Sources_Index.md` |

---

## 事实源优先级

1. 用户当前消息
2. `active/Current_Task.md`
3. `active/Context.md`
4. `reference/Decisions_Index.md`
5. ADR 文件
6. `worklog/`

worklog 是历史过程记录，不等于当前事实。

---

## 会话结束回写建议

重要协作结束时，请给出以下建议，由用户决定是否写入：

- `active/Context.md` 是否需要更新
- `active/Current_Task.md` 状态是否需要变化
- 是否需要新增 ADR 或更新 `reference/Decisions_Index.md`
- 是否需要新增 worklog 条目
"""


@dataclass
class CheckResult:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def required_dirs(profile: str) -> tuple[str, ...]:
    return MINIMAL_DIRS if profile == "minimal" else STANDARD_DIRS


def required_files(profile: str) -> tuple[str, ...]:
    return MINIMAL_FILES if profile == "minimal" else STANDARD_FILES


def ensure_clean_target(target: Path, force: bool) -> None:
    if not target.exists():
        return
    if force:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return
    if target.is_dir() and not any(target.iterdir()):
        return
    raise SystemExit(f"target already exists and is not empty: {target}")


def copy_selected_files(source: Path, target: Path, files: Sequence[str], dirs: Sequence[str]) -> None:
    for dirname in dirs:
        (target / dirname).mkdir(parents=True, exist_ok=True)
    for rel in files:
        src = source / rel
        dst = target / rel
        if not src.exists():
            raise SystemExit(f"template source file is missing: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def write_minimal_overrides(target: Path) -> None:
    (target / "AGENTS.md").write_text(MINIMAL_AGENTS, encoding="utf-8")


def init_command(args: argparse.Namespace) -> int:
    target = args.target.resolve()
    ensure_clean_target(target, args.force)
    if args.profile == "standard":
        shutil.copytree(TEMPLATE_DIR, target, dirs_exist_ok=True)
    else:
        copy_selected_files(TEMPLATE_DIR, target, MINIMAL_FILES, MINIMAL_DIRS)
        write_minimal_overrides(target)
    print(f"created {args.profile} context template at {target}")
    return 0


def simplify_command(args: argparse.Namespace) -> int:
    source = args.source.resolve()
    target = args.target.resolve()
    if not source.exists():
        raise SystemExit(f"source context does not exist: {source}")
    ensure_clean_target(target, args.force)
    copy_selected_files(source, target, MINIMAL_FILES, MINIMAL_DIRS)
    write_minimal_overrides(target)
    print(f"created minimal context at {target}")
    return 0


def iter_markdown_files(root: Path) -> Iterable[Path]:
    yield from sorted(root.rglob("*.md"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_current_task_status(path: Path) -> str | None:
    return extract_heading_value(path, "## 当前任务状态")


def extract_heading_value(path: Path, heading: str) -> str | None:
    text = read_text(path)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == heading:
            for candidate in lines[index + 1 :]:
                value = candidate.strip()
                if not value or value == "---":
                    continue
                return value
    return None


def should_check_ref(ref: str) -> bool:
    if "*" in ref:
        return False
    if ref.startswith(("http://", "https://", "file://")):
        return False
    if ref.startswith("<") or ref.startswith("$"):
        return False
    return True


def resolve_ref(root: Path, md_file: Path, ref: str) -> Path | None:
    normalized = ref.replace("\\", "/")
    root_candidate = root / normalized
    if root_candidate.exists():
        return root_candidate
    relative_candidate = md_file.parent / normalized
    if relative_candidate.exists():
        return relative_candidate
    return None


def is_placeholder(value: str) -> bool:
    return "【" in value and "】" in value


def parse_markdown_table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(set(cell) <= {"-", " "} for cell in cells):
            continue
        rows.append(cells)
    return rows


def strip_code_ticks(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def check_decisions(root: Path, errors: list[str]) -> None:
    index_path = root / "reference" / "Decisions_Index.md"
    if not index_path.exists():
        return
    rows = parse_markdown_table_rows(read_text(index_path))
    for cells in rows:
        if len(cells) < 5 or cells[0] in {"ID", "暂无"}:
            continue
        decision_id, _title, status, _summary, detail = cells[:5]
        if not decision_id.startswith("ADR-") or is_placeholder(decision_id):
            continue
        if is_placeholder(status) or not status:
            continue
        if status not in VALID_DECISION_STATUSES:
            errors.append(f"reference/Decisions_Index.md: invalid decision status `{status}` for {decision_id}")
            continue

        ref = strip_code_ticks(detail)
        if "template" in ref or not should_check_ref(ref):
            continue
        resolved = resolve_ref(root, index_path, ref)
        if resolved is None:
            continue
        adr_status = extract_heading_value(resolved, "## 状态")
        if adr_status and not is_placeholder(adr_status) and adr_status != status:
            rel_adr = resolved.relative_to(root).as_posix()
            errors.append(
                "reference/Decisions_Index.md: status mismatch for "
                f"{decision_id} ({status}) vs {rel_adr} ({adr_status})"
            )

    for adr_path in sorted((root / "decisions").glob("ADR-*.md")) if (root / "decisions").exists() else []:
        status = extract_heading_value(adr_path, "## 状态")
        if not status or is_placeholder(status):
            continue
        if status not in VALID_DECISION_STATUSES:
            rel_adr = adr_path.relative_to(root).as_posix()
            errors.append(f"{rel_adr}: invalid ADR status `{status}`")


def check_sources(root: Path, errors: list[str]) -> None:
    sources_path = root / "reference" / "Sources_Index.md"
    if not sources_path.exists():
        return
    text = read_text(sources_path)
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("- 状态："):
            continue
        status = stripped.removeprefix("- 状态：").strip()
        if is_placeholder(status):
            continue
        if status not in VALID_SOURCE_STATUSES:
            errors.append(f"reference/Sources_Index.md:{line_number}: invalid source status `{status}`")


def check_worklog(root: Path, errors: list[str]) -> None:
    index_path = root / "worklog" / "Worklog_Index.md"
    if not index_path.exists():
        return
    rows = parse_markdown_table_rows(read_text(index_path))
    for cells in rows:
        if len(cells) < 4 or cells[0] in {"日期", "暂无"}:
            continue
        date, _summary, _conclusion, detail = cells[:4]
        if date == "YYYY-MM-DD" or is_placeholder(date):
            continue
        if not DATE_RE.match(date):
            errors.append(f"worklog/Worklog_Index.md: invalid worklog date `{date}`")
        ref = strip_code_ticks(detail)
        if not ref:
            continue
        expected_suffix = f"{date}.md"
        if should_check_ref(ref) and not ref.endswith(expected_suffix):
            errors.append(
                "worklog/Worklog_Index.md: worklog detail path "
                f"`{ref}` does not match date `{date}`"
            )


def check_context(path: Path, profile: str, strict: bool) -> CheckResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not path.exists():
        return CheckResult([f"context directory does not exist: {path}"], [])
    if not path.is_dir():
        return CheckResult([f"context path is not a directory: {path}"], [])

    for dirname in required_dirs(profile):
        if not (path / dirname).is_dir():
            errors.append(f"missing directory: {dirname}")

    for rel in required_files(profile):
        file_path = path / rel
        if not file_path.is_file():
            errors.append(f"missing file: {rel}")
            continue
        if file_path.stat().st_size == 0:
            errors.append(f"empty required file: {rel}")

    task_file = path / "active" / "Current_Task.md"
    if task_file.exists():
        status = extract_current_task_status(task_file)
        if status not in VALID_TASK_STATUSES:
            errors.append(
                "active/Current_Task.md has no valid current task status "
                f"({', '.join(sorted(VALID_TASK_STATUSES))})"
            )

    check_decisions(path, errors)
    check_sources(path, errors)
    check_worklog(path, errors)

    for md_file in iter_markdown_files(path):
        rel_file = md_file.relative_to(path).as_posix()
        try:
            text = read_text(md_file)
        except UnicodeDecodeError as exc:
            errors.append(f"{rel_file}: not valid UTF-8 ({exc})")
            continue

        if "\ufffd" in text:
            errors.append(f"{rel_file}: contains Unicode replacement character")

        placeholders = PLACEHOLDER_RE.findall(text)
        if placeholders:
            message = f"{rel_file}: contains {len(placeholders)} placeholder(s)"
            if strict:
                errors.append(message)
            else:
                warnings.append(message)

        for ref in MARKDOWN_REF_RE.findall(text):
            if not should_check_ref(ref):
                continue
            if resolve_ref(path, md_file, ref) is None:
                errors.append(f"{rel_file}: broken markdown reference `{ref}`")

    return CheckResult(errors, warnings)


def check_command(args: argparse.Namespace) -> int:
    result = check_context(args.path.resolve(), args.profile, args.strict)
    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    for warning in result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    if result.ok:
        print(f"check passed: {args.path.resolve()}")
        return 0
    print(f"check failed: {len(result.errors)} error(s), {len(result.warnings)} warning(s)", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acf",
        description="Generate, simplify, and check AI context framework templates.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a context template")
    init_parser.add_argument("target", type=Path)
    init_parser.add_argument("--profile", choices=("standard", "minimal"), default="standard")
    init_parser.add_argument("--force", action="store_true", help="replace target if it exists")
    init_parser.set_defaults(func=init_command)

    simplify_parser = subparsers.add_parser("simplify", help="copy a minimal context from an existing one")
    simplify_parser.add_argument("source", type=Path)
    simplify_parser.add_argument("target", type=Path)
    simplify_parser.add_argument("--force", action="store_true", help="replace target if it exists")
    simplify_parser.set_defaults(func=simplify_command)

    check_parser = subparsers.add_parser("check", help="check context completeness")
    check_parser.add_argument("path", type=Path)
    check_parser.add_argument("--profile", choices=("standard", "minimal"), default="standard")
    check_parser.add_argument("--strict", action="store_true", help="treat placeholders as errors")
    check_parser.set_defaults(func=check_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
