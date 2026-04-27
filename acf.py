#!/usr/bin/env python3
"""Small CLI for generating and checking AI context framework directories."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import sysconfig
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parent


def find_template_dir() -> Path:
    source_template = ROOT / "template"
    if source_template.is_dir():
        return source_template

    installed_template = (
        Path(sysconfig.get_path("data"))
        / "share"
        / "ai-context-framework"
        / "template"
    )
    if installed_template.is_dir():
        return installed_template

    return source_template


TEMPLATE_DIR = find_template_dir()

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
    "worklog/Worklog_Index.md",
)

VALID_TASK_STATUSES = {"Active", "Paused", "Done", "Empty"}
VALID_DECISION_STATUSES = {"Active", "Proposed", "Superseded", "Rejected", "Deprecated"}
VALID_SOURCE_STATUSES = {"To Read", "Reading", "Read", "Useful", "Archived", "Rejected"}
PLACEHOLDER_RE = re.compile(r"【[^】]+】")
MARKDOWN_REF_RE = re.compile(r"`([^`\n]+\.md)`")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ADR_ID_RE = re.compile(r"^ADR-(\d{4})$")
DRAFT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
SOURCE_TABLE_HEADER = "| 资料 | 类型 | 链接或位置 | 状态 | 可信度 | 和本项目的关系 | 后续动作 |"
JSON_SCHEMA_VERSION = 1

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


@dataclass
class ContextLocation:
    project_root: Path
    context_root: Path
    profile: str


def json_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False))


def dry_run_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "dry_run", False))


def check_after_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "check_after", False))


def path_values(paths: Sequence[Path]) -> list[str]:
    return [str(path) for path in paths]


def check_payload(result: CheckResult) -> dict[str, object]:
    return {
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
    }


def check_error_code(result: CheckResult | None) -> str | None:
    if result is not None and not result.ok:
        return "check_failed"
    return None


def check_next_actions(result: CheckResult | None, strict: bool = False) -> list[str]:
    if result is None:
        return []
    command = "acf check --strict" if strict else "acf check"
    if result.errors:
        return [
            "Fix the reported errors.",
            f"Rerun `{command}`.",
        ]
    if result.warnings:
        return [
            "Review the reported warnings.",
            "Use `acf check --strict` when this context should reject placeholders.",
        ]
    return []


def write_next_actions(dry_run: bool, check_result: CheckResult | None) -> list[str]:
    if dry_run:
        return [
            "Review changed_files.",
            "Rerun the command without `--dry-run` to apply changes.",
        ]
    if check_result is not None and not check_result.ok:
        return [
            "Fix the reported check errors.",
            "Rerun the command after correction.",
        ]
    return []


def print_json(payload: dict[str, object]) -> None:
    payload.setdefault("schema_version", JSON_SCHEMA_VERSION)
    payload.setdefault("error_code", None)
    payload.setdefault("next_actions", [])
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def emit_write_result(
    args: argparse.Namespace,
    command: str,
    message: str,
    changed_files: Sequence[Path],
    check_result: CheckResult | None = None,
) -> int:
    dry_run = dry_run_enabled(args)
    payload: dict[str, object] = {
        "command": command,
        "ok": check_result.ok if check_result is not None else True,
        "error_code": check_error_code(check_result),
        "dry_run": dry_run,
        "changed_files": path_values(changed_files),
        "message": message,
        "next_actions": write_next_actions(dry_run, check_result),
    }
    if check_result is not None:
        payload["check"] = check_payload(check_result)

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


def maybe_check_after(args: argparse.Namespace, root: Path, profile: str | None = None) -> CheckResult | None:
    if not check_after_enabled(args) or dry_run_enabled(args):
        return None
    return check_context(root, profile or infer_context_profile(root), bool(getattr(args, "strict", False)))


def required_dirs(profile: str) -> tuple[str, ...]:
    return MINIMAL_DIRS if profile == "minimal" else STANDARD_DIRS


def required_files(profile: str) -> tuple[str, ...]:
    return MINIMAL_FILES if profile == "minimal" else STANDARD_FILES


def infer_context_profile(root: Path) -> str:
    standard_only_files = set(STANDARD_FILES) - set(MINIMAL_FILES)
    if any((root / rel_path).exists() for rel_path in standard_only_files):
        return "standard"
    return "minimal"


def is_context_root(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "AGENTS.md").is_file()
        and (path / "active" / "Context.md").is_file()
        and (path / "rules" / "Always_Active.md").is_file()
    )


def infer_project_root(context_root: Path) -> Path:
    if context_root.name == "ai" and context_root.parent.name == "docs":
        return context_root.parent.parent
    return context_root


def make_context_location(context_root: Path) -> ContextLocation:
    root = context_root.resolve()
    return ContextLocation(
        project_root=infer_project_root(root),
        context_root=root,
        profile=infer_context_profile(root),
    )


def discover_context(start: Path | None = None) -> ContextLocation:
    start_path = (start or Path.cwd()).resolve()
    current = start_path.parent if start_path.is_file() else start_path

    for directory in (current, *current.parents):
        if is_context_root(directory):
            return make_context_location(directory)

        docs_ai = directory / "docs" / "ai"
        if is_context_root(docs_ai):
            return make_context_location(docs_ai)

    raise SystemExit("could not find AI context directory; pass a context path or run `acf init docs/ai`")


def resolve_context_root(path: Path | None) -> Path:
    if path is not None:
        return path.resolve()
    return discover_context().context_root


def require_context_root(path: Path | None) -> Path:
    root = resolve_context_root(path)
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"context directory does not exist: {root}")
    return root


def resolve_status_location(path: Path | None) -> ContextLocation:
    if path is None:
        return discover_context()

    resolved = path.resolve()
    if is_context_root(resolved):
        return make_context_location(resolved)
    return discover_context(resolved)


def ensure_clean_target(target: Path, force: bool, dry_run: bool = False) -> None:
    if not target.exists():
        return
    if force:
        if dry_run:
            return
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


def infer_project_root(context_root: Path) -> Path:
    if context_root.parent.name.lower() == "docs":
        return context_root.parent.parent
    return context_root.parent


def display_path(path: Path) -> str:
    return path.as_posix()


def relative_display_path(path: Path, base: Path) -> str:
    try:
        return display_path(path.relative_to(base))
    except ValueError:
        return display_path(path)


def render_root_agents(project_name: str, context_rel: str) -> str:
    context_rel = context_rel.rstrip("/")
    return f"""# {project_name}

本仓库使用 AI context framework 管理项目上下文。

默认从项目 AI 上下文进入：

1. 先读取 `{context_rel}/AGENTS.md`
2. 再按其中的读取顺序读取当前有效上下文

## 仓库级约定

- 文档内容默认使用中文。
- 文件名和目录名使用英文。
- 不依赖特定 AI 模型或私有上下文格式。
- `{context_rel}/` 是本项目的 AI 上下文目录。
- 不要把上下文目录中的模板占位内容当作当前项目事实。
"""


def write_root_agents(context_root: Path, force: bool) -> Path | None:
    project_root = infer_project_root(context_root)
    root_agents = project_root / "AGENTS.md"
    if root_agents.exists() and root_agents.is_dir():
        raise SystemExit(f"root AGENTS.md path is a directory: {root_agents}")
    if root_agents.exists() and not force:
        return None

    context_rel = relative_display_path(context_root, project_root)
    project_name = project_root.name or "Project"
    root_agents.write_text(render_root_agents(project_name, context_rel), encoding="utf-8")
    return root_agents


def planned_root_agents_path(context_root: Path, force: bool) -> Path | None:
    project_root = infer_project_root(context_root)
    root_agents = project_root / "AGENTS.md"
    if root_agents.exists() and root_agents.is_dir():
        raise SystemExit(f"root AGENTS.md path is a directory: {root_agents}")
    if root_agents.exists() and not force:
        return None
    return root_agents


def planned_init_files(target: Path, profile: str, force_root_agent: bool) -> list[Path]:
    files = STANDARD_FILES if profile == "standard" else MINIMAL_FILES
    changed_files = [target / rel_path for rel_path in files]
    root_agents = planned_root_agents_path(target, force_root_agent)
    if root_agents is not None:
        changed_files.append(root_agents)
    return changed_files


def dynamic_minimal_rel_files(source: Path) -> list[str]:
    rel_files: list[str] = []
    dynamic_groups = (
        ("decisions", "ADR-*.md", {"ADR-0001-template.md"}),
        ("worklog/daily", "*.md", {"YYYY-MM-DD.md"}),
    )
    for dirname, pattern, excluded_names in dynamic_groups:
        src_dir = source / dirname
        if not src_dir.exists():
            continue
        for src in sorted(src_dir.glob(pattern)):
            if not src.is_file() or src.name in excluded_names:
                continue
            rel_files.append(src.relative_to(source).as_posix())
    return rel_files


def planned_simplify_files(source: Path, target: Path) -> list[Path]:
    rel_files = list(MINIMAL_FILES) + dynamic_minimal_rel_files(source)
    return [target / rel_path for rel_path in rel_files]


def copy_dynamic_minimal_files(source: Path, target: Path) -> None:
    for rel_path in dynamic_minimal_rel_files(source):
        src = source / rel_path
        dst = target / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def remove_markdown_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        return text
    end = next(
        (
            index
            for index, line in enumerate(lines[start + 1 :], start=start + 1)
            if line.strip().startswith("## ")
        ),
        len(lines),
    )
    updated = lines[:start] + lines[end:]
    return "\n".join(updated).rstrip() + "\n"


def remove_worklog_example_block(text: str) -> str:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == "填写示例："), None)
    if start is None:
        return text
    end = next(
        (
            index
            for index, line in enumerate(lines[start + 1 :], start=start + 1)
            if line.strip() == "---"
        ),
        len(lines),
    )
    updated = lines[:start] + lines[end:]
    return "\n".join(updated).rstrip() + "\n"


def sanitize_minimal_indexes(target: Path) -> None:
    decisions_index = target / "reference" / "Decisions_Index.md"
    if decisions_index.exists():
        decisions_index.write_text(
            remove_markdown_section(read_text(decisions_index), "## 示例"),
            encoding="utf-8",
        )

    worklog_index = target / "worklog" / "Worklog_Index.md"
    if worklog_index.exists():
        worklog_index.write_text(
            remove_worklog_example_block(read_text(worklog_index)),
            encoding="utf-8",
        )


def write_minimal_overrides(target: Path) -> None:
    (target / "AGENTS.md").write_text(MINIMAL_AGENTS, encoding="utf-8")
    sanitize_minimal_indexes(target)


def validate_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date `{value}`, expected YYYY-MM-DD") from exc
    return value


def clean_table_cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "/")


def table_cell(value: str, default: str = "无。") -> str:
    value = value.strip()
    return clean_table_cell(value or default)


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

    lines = read_text(index_path).splitlines()
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


def existing_adr_numbers(decisions_dir: Path) -> list[int]:
    if not decisions_dir.exists():
        return []
    numbers: list[int] = []
    for path in decisions_dir.glob("ADR-*.md"):
        match = re.match(r"ADR-(\d{4})\.md$", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return sorted(numbers)


def next_adr_id(decisions_dir: Path) -> str:
    numbers = existing_adr_numbers(decisions_dir)
    next_number = (numbers[-1] + 1) if numbers else 1
    return f"ADR-{next_number:04d}"


def validate_adr_id(value: str) -> str:
    if not ADR_ID_RE.match(value):
        raise argparse.ArgumentTypeError("ADR id must use ADR-0001 format")
    return value


def validate_draft_name(value: str) -> str:
    if not DRAFT_NAME_RE.match(value):
        raise argparse.ArgumentTypeError("draft name may only contain letters, digits, dot, underscore, and hyphen")
    return value


def render_adr(
    adr_id: str,
    title: str,
    status: str,
    adr_date: str,
    summary: str,
    decision: str,
    context: str,
) -> str:
    return f"""ADR：{title}

## 状态

{status}

---

## 日期

{adr_date}

---

## 背景

{context}

---

## 问题

需要记录该决策，使 `reference/Decisions_Index.md` 和 ADR 详情保持同步，并避免后续协作重复讨论同一取舍。

---

## 决策

{decision}

---

## 理由

1. {summary}
2. 该决策已经进入项目维护流程，需要成为可追溯事实。
3. ADR 文件提供比索引摘要更完整的背景和后续评估入口。

---

## 考虑过的替代方案

### 方案 A：只更新索引，不生成 ADR

优点：

- 文件更少。
- 短期维护成本更低。

缺点：

- 缺少背景、理由和重新评估条件。
- 后续 AI 协作容易只看到结论，看不到取舍过程。

为什么没有选择：

本项目要求重要决策可追溯，索引只应保存摘要。

---

## 后果

### 正面影响

- 决策摘要和详情文件同步生成。
- 后续检查可以验证 ADR 状态和索引状态一致。

### 负面影响或代价

- 每个重要决策会增加一个 Markdown 文件。
- 自动生成内容仍需要人工或主代理审阅语义质量。

---

## 适用范围

适用于：

- 本仓库当前 dogfooding 和 CLI 维护流程。

不适用于：

- 通用模板使用者的强制流程。

---

## 重新评估条件

1. 后续 `new adr` 命令支持更完整的交互式字段。
2. 决策索引结构发生变化。
3. 该决策带来的维护成本超过收益。

---

## 相关文件

- `reference/Decisions_Index.md`
- `active/Context.md`
- `worklog/Worklog_Index.md`
"""


def normalize_items(values: Sequence[str] | None, fallback: Sequence[str]) -> list[str]:
    items = [value.strip() for value in values or [] if value.strip()]
    return items or list(fallback)


def numbered_list(items: Sequence[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def bullet_list(items: Sequence[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_current_task(
    status: str,
    title: str,
    goals: Sequence[str],
    background: str,
    inputs: Sequence[str],
    outputs: Sequence[str],
    success: Sequence[str],
    failures: Sequence[str],
    constraints: Sequence[str],
    non_goals: Sequence[str],
    questions: Sequence[str],
) -> str:
    return f"""本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

{status}

说明：

- Active：当前任务正在进行
- Paused：当前任务暂停
- Done：当前任务已完成
- Empty：暂无需要写入文件的当前任务

---

## 任务名称

{title}

---

## 本次任务目标

{numbered_list(goals)}

---

## 任务背景

{background}

---

## 输入材料

{bullet_list(inputs)}

---

## 输出要求

{bullet_list(outputs)}

---

## 成功标准

{numbered_list(success)}

---

## 失败信号

{numbered_list(failures)}

---

## 约束条件

{numbered_list(constraints)}

---

## 不允许做的事

{bullet_list(non_goals)}

---

## 需要 AI 协助判断的问题

{numbered_list(questions)}

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应归档到 archive 的历史内容。
"""


def sanitize_draft_input(text: str) -> str:
    return text.replace("`", "'").replace("【", "[").replace("】", "]").strip()


def render_writeback_draft(draft_name: str, input_text: str) -> str:
    sanitized_input = sanitize_draft_input(input_text) or "无。"
    return f"""本文件是会话结束回写草案，不是当前事实源。

请人工审阅后，再决定是否使用 CLI 或手工方式写入权威上下文。

---

## 草案名称

{draft_name}

---

## 原始回写建议

```text
{sanitized_input}
```

---

## active/Context.md 候选

- 待人工判断是否存在应写入 `active/Context.md` 的当前阶段事实。
- 不要把历史过程直接写入当前事实。

---

## active/Current_Task.md 候选

- 待人工判断当前任务状态是否需要更新。
- 如需更新，优先使用 `uv run python acf.py new task ...`。

---

## reference/Decisions_Index.md / ADR 候选

- 待人工判断是否存在需要升格为 ADR 的重要决策。
- 如需新增决策，优先使用 `uv run python acf.py new adr ...`。

---

## worklog 候选

- 待人工判断是否需要写入当天整理后工作记录。
- 如需新增或更新，优先使用 `uv run python acf.py new worklog ...`。

---

## source 候选

- 待人工判断是否需要新增资料索引。
- 如需新增或更新，优先使用 `uv run python acf.py new source ...`。

---

## archive 候选

- 待人工判断是否有历史材料需要归档。
- archive 只保存历史归档，不作为当前事实源。

---

## 审阅清单

- [ ] 已确认哪些内容应写入当前事实。
- [ ] 已确认哪些内容只是历史过程。
- [ ] 已确认是否需要新增 ADR。
- [ ] 已确认是否需要新增 worklog。
- [ ] 已确认是否需要新增 source。
- [ ] 已确认是否需要归档。
"""


def index_contains_id(index_path: Path, adr_id: str) -> bool:
    return any(cells and cells[0] == adr_id for cells in parse_markdown_table_rows(read_text(index_path)))


def update_decisions_index(
    index_path: Path,
    adr_id: str,
    title: str,
    status: str,
    summary: str,
) -> None:
    if not index_path.exists():
        raise SystemExit(f"decisions index does not exist: {index_path}")
    if index_contains_id(index_path, adr_id):
        raise SystemExit(f"decisions index already contains id: {adr_id}")

    lines = read_text(index_path).splitlines()
    if status == "Active":
        header = "| ID | 标题 | 状态 | 摘要 | 详情 |"
        new_row = f"| {adr_id} | {clean_table_cell(title)} | Active | {clean_table_cell(summary)} | `decisions/{adr_id}.md` |"
    else:
        header = "| ID | 标题 | 状态 | 摘要 | 需要确认的问题 |"
        new_row = (
            f"| {adr_id} | {clean_table_cell(title)} | Proposed | {clean_table_cell(summary)} | "
            f"详情：`decisions/{adr_id}.md` |"
        )

    header_index = next((index for index, line in enumerate(lines) if line.strip() == header), None)
    if header_index is None or header_index + 1 >= len(lines):
        raise SystemExit(f"decisions index table was not found: {index_path}")

    table_start = header_index + 2
    table_end = table_start
    while table_end < len(lines) and lines[table_end].strip().startswith("|"):
        table_end += 1

    existing_rows = lines[table_start:table_end]
    kept_rows = [row for row in existing_rows if row_date(row) != "暂无" and row.strip()]
    rows = kept_rows + [new_row]
    rows.sort(key=row_date)
    updated = lines[:table_start] + rows + lines[table_end:]
    index_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def source_index_row(
    title: str,
    source_type: str,
    location: str,
    status: str,
    credibility: str,
    relation: str,
    next_action: str,
) -> str:
    return (
        f"| {table_cell(title)} | {table_cell(source_type)} | {table_cell(location)} | {status} | "
        f"{table_cell(credibility, '未评估')} | {table_cell(relation)} | {table_cell(next_action)} |"
    )


def update_sources_index(
    index_path: Path,
    title: str,
    source_type: str,
    location: str,
    status: str,
    credibility: str,
    relation: str,
    next_action: str,
    force: bool,
) -> None:
    if not index_path.exists():
        raise SystemExit(f"sources index does not exist: {index_path}")

    lines = read_text(index_path).splitlines()
    header_index = next((index for index, line in enumerate(lines) if line.strip() == SOURCE_TABLE_HEADER), None)
    if header_index is None or header_index + 1 >= len(lines):
        raise SystemExit(f"sources index table was not found: {index_path}")

    table_start = header_index + 2
    table_end = table_start
    while table_end < len(lines) and lines[table_end].strip().startswith("|"):
        table_end += 1

    existing_rows = lines[table_start:table_end]
    if any(row_date(row) == title for row in existing_rows) and not force:
        raise SystemExit(f"sources index already contains source: {title}")

    new_row = source_index_row(title, source_type, location, status, credibility, relation, next_action)
    kept_rows = [
        row
        for row in existing_rows
        if row_date(row) not in {title, "暂无"} and row.strip()
    ]
    rows = kept_rows + [new_row]
    rows.sort(key=row_date)

    updated = lines[:table_start] + rows + lines[table_end:]
    index_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def init_command(args: argparse.Namespace) -> int:
    target = args.target.resolve()
    dry_run = dry_run_enabled(args)
    ensure_clean_target(target, args.force, dry_run=dry_run)
    changed_files = planned_init_files(target, args.profile, args.force_root_agent)
    if not dry_run:
        if args.profile == "standard":
            shutil.copytree(TEMPLATE_DIR, target, dirs_exist_ok=True)
        else:
            copy_selected_files(TEMPLATE_DIR, target, MINIMAL_FILES, MINIMAL_DIRS)
            write_minimal_overrides(target)
        write_root_agents(target, args.force_root_agent)
    check_result = maybe_check_after(args, target, args.profile)
    action = "would create" if dry_run else "created"
    return emit_write_result(
        args,
        "init",
        f"{action} {args.profile} context template at {target}",
        changed_files,
        check_result,
    )


def simplify_command(args: argparse.Namespace) -> int:
    source = args.source.resolve()
    target = args.target.resolve()
    if not source.exists():
        raise SystemExit(f"source context does not exist: {source}")
    dry_run = dry_run_enabled(args)
    ensure_clean_target(target, args.force, dry_run=dry_run)
    changed_files = planned_simplify_files(source, target)
    if not dry_run:
        copy_selected_files(source, target, MINIMAL_FILES, MINIMAL_DIRS)
        copy_dynamic_minimal_files(source, target)
        write_minimal_overrides(target)
    check_result = maybe_check_after(args, target, "minimal")
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "simplify", f"{action} minimal context at {target}", changed_files, check_result)


def new_worklog_command(args: argparse.Namespace) -> int:
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
    if daily_path.exists() and not args.force:
        raise SystemExit(f"worklog daily file already exists: {daily_path}")
    index_path = root / "worklog" / "Worklog_Index.md"
    if not index_path.exists():
        raise SystemExit(f"worklog index does not exist: {index_path}")

    changed_files = [daily_path, index_path]
    if not dry_run:
        daily_dir.mkdir(parents=True, exist_ok=True)
        daily_path.write_text(render_worklog_daily(log_date, summary, conclusion), encoding="utf-8")
        update_worklog_index(index_path, log_date, summary, conclusion, args.force)
    check_result = maybe_check_after(args, root)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "new worklog", f"{action} worklog {daily_path}", changed_files, check_result)


def new_adr_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)

    decisions_dir = root / "decisions"
    adr_id = args.id or next_adr_id(decisions_dir)
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
            render_adr(adr_id, title, args.status, adr_date, summary, decision, context),
            encoding="utf-8",
        )
        update_decisions_index(index_path, adr_id, title, args.status, summary)
    check_result = maybe_check_after(args, root)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "new adr", f"{action} ADR {adr_path}", changed_files, check_result)


def new_task_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)

    task_path = root / "active" / "Current_Task.md"
    if task_path.exists():
        current_status = extract_current_task_status(task_path)
        if current_status == "Active" and not args.force:
            raise SystemExit(f"current task is Active; use --force to replace it: {task_path}")

    title = args.title.strip()
    background = args.background.strip() or "该任务由当前维护流程创建，需要写入当前任务文件以便协作过程可追踪。"
    if not title:
        raise SystemExit("task title cannot be empty")

    goals = normalize_items(args.goal, ("完成当前任务。",))
    inputs = normalize_items(args.input, ("用户当前请求。", "`active/Context.md`。"))
    outputs = normalize_items(args.output, ("更新后的 `active/Current_Task.md`。",))
    success = normalize_items(args.success, ("任务目标已完成并通过必要验证。",))
    failures = normalize_items(args.failure, ("目标无法验证。", "任务范围需要重新确认。"))
    constraints = normalize_items(args.constraint, ("遵守当前项目规则。", "不引入无关依赖。"))
    non_goals = normalize_items(args.non_goal, ("无。",))
    questions = normalize_items(args.question, ("无。",))

    if not dry_run:
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(
            render_current_task(
                args.status,
                title,
                goals,
                background,
                inputs,
                outputs,
                success,
                failures,
                constraints,
                non_goals,
                questions,
            ),
            encoding="utf-8",
        )
    check_result = maybe_check_after(args, root)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "new task", f"{action} current task {task_path}", [task_path], check_result)


def new_source_command(args: argparse.Namespace) -> int:
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
        rows = parse_markdown_table_rows(read_text(index_path))
        if any(cells and cells[0] == title for cells in rows) and not args.force:
            raise SystemExit(f"sources index already contains source: {title}")
    else:
        update_sources_index(
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
    check_result = maybe_check_after(args, root)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "new source", f"{action} source entry {title}", [index_path], check_result)


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


def writeback_draft_command(args: argparse.Namespace) -> int:
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
        draft_path.write_text(render_writeback_draft(draft_name, input_text), encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "writeback draft", f"{action} writeback draft {draft_path}", [draft_path], check_result)


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
    rows = parse_markdown_table_rows(text)
    for cells in rows:
        if len(cells) < 7 or cells[0] in {"资料", "暂无"}:
            continue
        title, _source_type, _location, status, _credibility, _relation, _next_action = cells[:7]
        if is_placeholder(title) or is_placeholder(status) or not status:
            continue
        if status not in VALID_SOURCE_STATUSES:
            errors.append(f"reference/Sources_Index.md: invalid source status `{status}` for {title}")

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


def template_packaging_files_from_pyproject(pyproject_path: Path) -> set[str]:
    if not pyproject_path.exists():
        return set()
    text = read_text(pyproject_path)
    return {
        match.replace("\\", "/").removeprefix("template/")
        for match in re.findall(r'"(template/[^"]+)"', text)
    }


def check_template_packaging(root: Path, errors: list[str]) -> None:
    pyproject_path = ROOT / "pyproject.toml"
    if root.resolve() != TEMPLATE_DIR.resolve() or not pyproject_path.exists():
        return

    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    packaged_files = template_packaging_files_from_pyproject(pyproject_path)
    missing = sorted(actual_files - packaged_files)
    extra = sorted(packaged_files - actual_files)

    for rel_path in missing:
        errors.append(f"pyproject.toml: missing template data-file entry for `{rel_path}`")
    for rel_path in extra:
        errors.append(f"pyproject.toml: stale template data-file entry for `{rel_path}`")


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
    check_template_packaging(path, errors)

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
            elif not strict:
                warnings.append(message)

        for ref in MARKDOWN_REF_RE.findall(text):
            if not should_check_ref(ref):
                continue
            if resolve_ref(path, md_file, ref) is None:
                errors.append(f"{rel_file}: broken markdown reference `{ref}`")

    return CheckResult(errors, warnings)


def check_command(args: argparse.Namespace) -> int:
    root = resolve_context_root(args.path)
    profile = args.profile or infer_context_profile(root)
    result = check_context(root, profile, args.strict)
    if json_enabled(args):
        print_json(
            {
                "command": "check",
                "context": str(root),
                "profile": profile,
                "strict": args.strict,
                "check": check_payload(result),
                "ok": result.ok,
                "error_code": check_error_code(result),
                "next_actions": check_next_actions(result, args.strict),
            }
        )
        return 0 if result.ok else 1

    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    for warning in result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    if result.ok:
        print(f"check passed: {root}")
        return 0
    print(f"check failed: {len(result.errors)} error(s), {len(result.warnings)} warning(s)", file=sys.stderr)
    return 1


def status_command(args: argparse.Namespace) -> int:
    location = resolve_status_location(args.path)
    profile = args.profile or location.profile
    task_path = location.context_root / "active" / "Current_Task.md"
    task_status = extract_current_task_status(task_path) if task_path.exists() else None
    result = check_context(location.context_root, profile, args.strict)
    if json_enabled(args):
        print_json(
            {
                "command": "status",
                "project_root": str(location.project_root),
                "context": str(location.context_root),
                "profile": profile,
                "current_task": task_status or "Unknown",
                "strict": args.strict,
                "check": check_payload(result),
                "ok": result.ok,
                "error_code": check_error_code(result),
                "next_actions": check_next_actions(result, args.strict),
            }
        )
        return 0 if result.ok else 1

    print(f"project root: {location.project_root}")
    print(f"context: {location.context_root}")
    print(f"profile: {profile}")
    print(f"current task: {task_status or 'Unknown'}")
    print(f"check: {'passed' if result.ok else 'failed'}")
    if result.errors:
        print(f"errors: {len(result.errors)}")
        for error in result.errors:
            print(f"ERROR: {error}")
    if result.warnings:
        print(f"warnings: {len(result.warnings)}")
        for warning in result.warnings:
            print(f"WARN: {warning}")

    return 0 if result.ok else 1


def add_json_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="print machine-readable JSON")


def add_write_arguments(parser: argparse.ArgumentParser) -> None:
    add_json_argument(parser)
    parser.add_argument("--dry-run", action="store_true", help="validate and report changed files without writing")
    parser.add_argument("--check-after", action="store_true", help="run context check after writing")
    parser.add_argument("--strict", action="store_true", help="use strict mode for --check-after")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acf",
        description="Generate, simplify, and check AI context framework templates.",
    )
    parser.set_defaults(json=False)
    add_json_argument(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="show discovered context status")
    status_parser.add_argument("path", nargs="?", type=Path, help="context path or a directory inside a project")
    status_parser.add_argument("--profile", choices=("standard", "minimal"), default=None)
    status_parser.add_argument("--strict", action="store_true", help="treat placeholders as errors")
    add_json_argument(status_parser)
    status_parser.set_defaults(func=status_command)

    init_parser = subparsers.add_parser("init", help="create a context template")
    init_parser.add_argument("target", type=Path)
    init_parser.add_argument("--profile", choices=("standard", "minimal"), default="standard")
    init_parser.add_argument("--force", action="store_true", help="replace target if it exists")
    init_parser.add_argument("--force-root-agent", action="store_true", help="replace existing root AGENTS.md")
    add_write_arguments(init_parser)
    init_parser.set_defaults(func=init_command)

    simplify_parser = subparsers.add_parser("simplify", help="copy a minimal context from an existing one")
    simplify_parser.add_argument("source", type=Path)
    simplify_parser.add_argument("target", type=Path)
    simplify_parser.add_argument("--force", action="store_true", help="replace target if it exists")
    add_write_arguments(simplify_parser)
    simplify_parser.set_defaults(func=simplify_command)

    check_parser = subparsers.add_parser("check", help="check context completeness")
    check_parser.add_argument("path", nargs="?", type=Path)
    check_parser.add_argument("--profile", choices=("standard", "minimal"), default=None)
    check_parser.add_argument("--strict", action="store_true", help="treat placeholders as errors")
    add_json_argument(check_parser)
    check_parser.set_defaults(func=check_command)

    new_parser = subparsers.add_parser("new", help="create context entries")
    new_subparsers = new_parser.add_subparsers(dest="entry_type", required=True)

    worklog_parser = new_subparsers.add_parser("worklog", help="create a daily worklog and index row")
    worklog_parser.add_argument("path", nargs="?", type=Path)
    worklog_parser.add_argument("--date", type=validate_date, default=None, help="date in YYYY-MM-DD format")
    worklog_parser.add_argument("--summary", required=True, help="one-line worklog summary")
    worklog_parser.add_argument("--conclusion", default="无。", help="one-line key conclusion")
    worklog_parser.add_argument("--force", action="store_true", help="replace existing daily file and index row")
    add_write_arguments(worklog_parser)
    worklog_parser.set_defaults(func=new_worklog_command)

    adr_parser = new_subparsers.add_parser("adr", help="create an ADR and update the decisions index")
    adr_parser.add_argument("path", nargs="?", type=Path)
    adr_parser.add_argument("--id", type=validate_adr_id, default=None, help="ADR id in ADR-0001 format")
    adr_parser.add_argument("--date", type=validate_date, default=None, help="date in YYYY-MM-DD format")
    adr_parser.add_argument("--status", choices=("Active", "Proposed"), default="Proposed")
    adr_parser.add_argument("--title", required=True, help="ADR title")
    adr_parser.add_argument("--summary", required=True, help="one-line decision summary")
    adr_parser.add_argument("--decision", required=True, help="decision statement")
    adr_parser.add_argument("--context", default="", help="decision background")
    add_write_arguments(adr_parser)
    adr_parser.set_defaults(func=new_adr_command)

    task_parser = new_subparsers.add_parser("task", help="create or replace active/Current_Task.md")
    task_parser.add_argument("path", nargs="?", type=Path)
    task_parser.add_argument("--status", choices=tuple(sorted(VALID_TASK_STATUSES)), default="Active")
    task_parser.add_argument("--title", required=True, help="task title")
    task_parser.add_argument("--goal", action="append", required=True, help="task goal; can be repeated")
    task_parser.add_argument("--background", default="", help="task background")
    task_parser.add_argument("--input", action="append", default=None, help="input material; can be repeated")
    task_parser.add_argument("--output", action="append", default=None, help="expected output; can be repeated")
    task_parser.add_argument("--success", action="append", default=None, help="success criterion; can be repeated")
    task_parser.add_argument("--failure", action="append", default=None, help="failure signal; can be repeated")
    task_parser.add_argument("--constraint", action="append", default=None, help="task constraint; can be repeated")
    task_parser.add_argument("--non-goal", action="append", default=None, help="out-of-scope item; can be repeated")
    task_parser.add_argument("--question", action="append", default=None, help="question for AI judgment; can be repeated")
    task_parser.add_argument("--force", action="store_true", help="replace an Active current task")
    add_write_arguments(task_parser)
    task_parser.set_defaults(func=new_task_command)

    source_parser = new_subparsers.add_parser("source", help="create or update a source index entry")
    source_parser.add_argument("path", nargs="?", type=Path)
    source_parser.add_argument("--title", required=True, help="source title")
    source_parser.add_argument("--type", required=True, help="source type")
    source_parser.add_argument("--location", required=True, help="source URL or local path")
    source_parser.add_argument("--status", choices=tuple(sorted(VALID_SOURCE_STATUSES)), default="To Read")
    source_parser.add_argument("--credibility", default="未评估", help="source credibility")
    source_parser.add_argument("--relation", required=True, help="why the source is relevant")
    source_parser.add_argument("--next-action", default="无。", help="next action for this source")
    source_parser.add_argument("--force", action="store_true", help="replace an existing source row")
    add_write_arguments(source_parser)
    source_parser.set_defaults(func=new_source_command)

    writeback_parser = subparsers.add_parser("writeback", help="create reviewable writeback drafts")
    writeback_subparsers = writeback_parser.add_subparsers(dest="writeback_command", required=True)

    draft_parser = writeback_subparsers.add_parser("draft", help="create a session writeback draft")
    draft_parser.add_argument("path", nargs="?", type=Path)
    draft_parser.add_argument("--name", type=validate_draft_name, default=None, help="draft file name without .md")
    draft_parser.add_argument("--text", default="", help="writeback suggestion text")
    draft_parser.add_argument("--input", type=Path, default=None, help="file containing writeback suggestion text")
    draft_parser.add_argument("--force", action="store_true", help="replace an existing draft")
    add_write_arguments(draft_parser)
    draft_parser.set_defaults(func=writeback_draft_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
