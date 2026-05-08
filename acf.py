#!/usr/bin/env python3
"""Small CLI for generating and checking AI context framework directories."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import sys
import sysconfig
import time
import unicodedata
from urllib.parse import unquote
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parent
VERSION = "v0.0.3.36"

TARGET_EXISTS_APPEND_REQUIRED = "TARGET_EXISTS_APPEND_REQUIRED"
APPEND_FORCE_CONFLICT = "APPEND_FORCE_CONFLICT"
ANCHOR_NOT_FOUND = "ANCHOR_NOT_FOUND"


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
    "human",
    "human/weekly",
    "human/reports",
    "rules",
    "reference",
    "reference/sources",
    "reference/knowledge",
    "decisions",
    "worklog",
    "worklog/daily",
    "worklog/knowledge-drafts",
    "archive",
    "archive/tasks",
    "archive/plans",
    "archive/feedback",
)

STANDARD_FILES = (
    "AGENTS.md",
    "active/Context.md",
    "active/Current_Task.md",
    "active/Feedback_Inbox.md",
    "active/Task_Plan.md",
    "human/Human_Notes.md",
    "human/weekly/.gitkeep",
    "human/reports/.gitkeep",
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
    "reference/Knowledge_Index.md",
    "reference/Context_Curation_Prompt.md",
    "reference/Sources_Index.md",
    "reference/sources/.gitkeep",
    "reference/knowledge/.gitkeep",
    "reference/System_Manual.md",
    "decisions/ADR-0001-template.md",
    "worklog/Worklog_Index.md",
    "worklog/daily/YYYY-MM-DD.md",
    "worklog/knowledge-drafts/.gitkeep",
    "archive/Archive_Index.md",
    "archive/tasks/.gitkeep",
    "archive/plans/.gitkeep",
    "archive/feedback/.gitkeep",
)

MINIMAL_DIRS = (
    "active",
    "rules",
    "reference",
    "reference/knowledge",
    "decisions",
    "worklog",
    "worklog/daily",
    "worklog/knowledge-drafts",
    "archive",
    "archive/tasks",
    "archive/plans",
    "archive/feedback",
)

MINIMAL_FILES = (
    "AGENTS.md",
    "active/Context.md",
    "active/Current_Task.md",
    "active/Feedback_Inbox.md",
    "active/Task_Plan.md",
    "rules/Always_Active.md",
    "rules/Project_Rules.md",
    "reference/Project_Brief.md",
    "reference/Decisions_Index.md",
    "reference/Knowledge_Index.md",
    "reference/Context_Curation_Prompt.md",
    "reference/Sources_Index.md",
    "reference/knowledge/.gitkeep",
    "worklog/Worklog_Index.md",
    "worklog/knowledge-drafts/.gitkeep",
    "archive/Archive_Index.md",
    "archive/tasks/.gitkeep",
    "archive/plans/.gitkeep",
    "archive/feedback/.gitkeep",
)

VALID_TASK_STATUSES = {"Active", "Paused", "Done", "Empty"}
VALID_PLAN_STATUSES = {"Active", "Paused", "Done", "Empty"}
VALID_SUBTASK_STATUSES = {"Pending", "Active", "Done", "Blocked", "Skipped", "Superseded"}
VALID_DECISION_STATUSES = {"Active", "Proposed", "Superseded", "Rejected", "Deprecated"}
VALID_SOURCE_STATUSES = {"To Read", "Reading", "Read", "Useful", "Archived", "Rejected"}
VALID_KNOWLEDGE_STATUSES = {"Draft", "Active", "Promoted", "Stale", "Rejected"}
VALID_WORKSTREAM_STATUSES = {"Open", "Active", "Blocked", "ReadyToMerge", "Done", "Cancelled"}
VALID_WORKSTREAM_STAGE_STATUSES = {"Pending", "Active", "Blocked", "Done", "Skipped", "Cancelled"}
VALID_MERGE_RESOLUTIONS = {"merged", "rejected", "no_merge_required", "archived"}
ACTIVE_WORKSTREAM_STATUSES = {"Active", "Blocked", "ReadyToMerge"}
DEFAULT_STALE_DAYS = 14
AUDIT_ACTIVE_SECTION_MAX_NONEMPTY_LINES = 80
WORKSTREAM_NOTE_SECTIONS = {
    "当前发现": "## 当前发现",
    "待合并结论": "## 待合并结论",
    "冲突风险": "## 冲突风险",
    "完成标准": "## 完成标准",
    "证据": "## 证据",
}
AUTHORITY_PATHS = {
    "AGENTS.md",
    "active/Context.md",
    "active/Current_Task.md",
    "active/Task_Plan.md",
    "active/Feedback_Inbox.md",
    "reference/Decisions_Index.md",
    "reference/Knowledge_Index.md",
}
AUTHORITY_GLOBS = (
    "rules/*.md",
    "decisions/*.md",
)
WORKSTREAM_STATE_TRANSITIONS = {
    "Open": {"Active", "Cancelled"},
    "Active": {"Blocked", "ReadyToMerge", "Cancelled"},
    "Blocked": {"Active", "Cancelled"},
    "ReadyToMerge": {"Done", "Cancelled"},
    "Done": set(),
    "Cancelled": set(),
}
PLACEHOLDER_RE = re.compile(r"【[^】]+】")
ACF_PLACEHOLDER_RE = re.compile(r"^【ACF:[A-Z0-9_:-]+(?:\|[^】]+)?】$")
MARKDOWN_REF_RE = re.compile(r"`([^`\n]+\.md)`")
MARKDOWN_LINK_RE = re.compile(r"(!?)\[([^\]\n]*)\]\(([^)\n]+)\)")
PATH_LIKE_RE = re.compile(
    r"(?<![\w./\\:-])"
    r"((?:\.{1,2}/)?(?:[A-Za-z0-9_.\-\u4e00-\u9fff]+/)+"
    r"[A-Za-z0-9_.\-\u4e00-\u9fff]+(?:\.[A-Za-z0-9]+)"
    r"(?:#[A-Za-z0-9_.%\-_\u4e00-\u9fff]+)?)"
)
LINKIFY_DEFAULT_DIRS = ("active", "reference", "rules", "decisions")
LINKIFY_DEFAULT_FILES = ("worklog/Worklog_Index.md", "archive/Archive_Index.md")
PLAN_REFERENCE_BULLET_RE = re.compile(
    r"^-\s+(?:`(?P<path>reference/[^`\n]+\.md)`|"
    r"\[(?P<link_path>reference/[^\]\n]+\.md)\]\([^)]+\))"
    r"[：:]\s*(?P<purpose>.+?)\s*$"
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ADR_ID_RE = re.compile(r"^ADR-(\d{4})$")
TASK_ID_RE = re.compile(r"^T(\d{3})$")
TASK_ID_TOKEN_RE = re.compile(r"\bT(\d{3})\b")
TASK_STAGE_ID_RE = re.compile(r"^T\d{3}\.\d+$")
TASK_STAGE_ID_TOKEN_RE = re.compile(r"\bT\d{3}\.\d+\b")
KNOWLEDGE_ID_RE = re.compile(r"^K(\d{3})$")
WORKSTREAM_ID_RE = re.compile(r"^WS(\d{3})$")
WORKSTREAM_ID_TOKEN_RE = re.compile(r"\bWS\d{3}\b")
WORKSTREAM_STAGE_ID_RE = re.compile(r"^WS\d{3}\.\d+$")
DRAFT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+\S.*$")
SOURCE_TABLE_HEADER = "| 资料 | 类型 | 链接或位置 | 状态 | 可信度 | 和本项目的关系 | 后续动作 |"
TASK_TABLE_HEADER = "| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |"
TASK_STAGE_TABLE_HEADER = "| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |"
FEEDBACK_TABLE_HEADER = "| ID | 状态 | 类型 | 内容 | 来源 | 后续处理 |"
KNOWLEDGE_TABLE_HEADER = "| ID | 标题 | 状态 | 标签 | 摘要 | 详情 |"
ARCHIVE_TABLE_HEADER = "| 日期 | 类型 | ID | 原路径 | 归档路径 | 状态 | 原因 |"
LEGACY_ARCHIVE_TABLE_HEADER = "| 日期 | 类型 | 标题 | 原因 | 详情 |"
WORKSTREAM_TABLE_HEADER = "| ID | 状态 | 标题 | Owner | 写入范围 | 依赖 | 输出物 | 详情 |"
WORKSTREAM_STAGE_TABLE_HEADER = "| ID | 状态 | 阶段 | 依赖 | 输出物 | 证据 | 下一步 |"
WORKSTREAM_INDEX_REL = "active/Workstreams.md"
WORKSTREAM_DIR_REL = "active/workstreams"
WORKSTREAM_ARCHIVE_DIR_REL = "archive/workstreams"
ACF_MARKER_RE = re.compile(r"<!--\s*ACF:([A-Z0-9_-]+):([A-Z0-9_-]+):(START|END)\s*-->")
WORKSTREAM_ARCHIVE_MARKER_START = "<!-- ACF:WORKSTREAM:ARCHIVE-RECORD:START -->"
WORKSTREAM_ARCHIVE_MARKER_END = "<!-- ACF:WORKSTREAM:ARCHIVE-RECORD:END -->"
LEGACY_WORKSTREAM_ARCHIVE_MARKER_START = "<!-- ACF:WORKSTREAM-ARCHIVE:START -->"
LEGACY_WORKSTREAM_ARCHIVE_MARKER_END = "<!-- ACF:WORKSTREAM-ARCHIVE:END -->"
PLAN_REFERENCE_HEADING = "## 规划依据"
PLAN_REFERENCE_EMPTY = "- 无。"
PLAN_REFERENCE_SECTION_INTRO = (
    "列出当前大任务必须对齐的 reference 设计、路线或差距文档；"
    "只放路径和一句话用途，不复制详细规划。"
)
PLAN_REFERENCE_UPGRADE_PROMPT = "- 使用 `acf plan reference add` 添加当前大任务必须对齐的 reference 规划依据。"
CURRENT_TASK_REFERENCE_PROMPT = "- 相关 reference 规划依据请查看 `active/Task_Plan.md` 的 `## 规划依据`。"
WORKSTREAM_METADATA_FIELDS = (
    "id",
    "status",
    "owner",
    "title",
    "current_stage",
    "depends_on",
    "read_scope",
    "write_scope",
    "merge_targets",
    "merge_resolution",
    "keep_active_reason",
    "keep_active_until",
)
JSON_SCHEMA_VERSION = 1
EXIT_CHECK_FAILED = 1
EXIT_INPUT_ERROR = 2
EXIT_SAFETY_REFUSED = 3
EXIT_RUNTIME_ERROR = 70
ACF_HOME_ENV = "ACF_HOME"
USAGE_LOG_CONFIG_NAME = "config.json"
USAGE_LOG_FILE_REL = "logs/usage.jsonl"
USAGE_LOCK_FILE_NAME = "usage.lock"
LOCK_FILE_REL = ".acf.lock"
TEMPLATE_EXAMPLE_FILES = {"decisions/ADR-0001-template.md", "worklog/daily/YYYY-MM-DD.md"}
UPGRADE_NOTES_START = "<!-- ACF:UPGRADE:NOTES:START -->"
UPGRADE_NOTES_END = "<!-- ACF:UPGRADE:NOTES:END -->"
LEGACY_UPGRADE_NOTES_START = "<!-- ACF:UPGRADE-NOTES:START -->"
LEGACY_UPGRADE_NOTES_END = "<!-- ACF:UPGRADE-NOTES:END -->"
KNOWLEDGE_TITLE_SIMILARITY_THRESHOLD = 0.85
KNOWLEDGE_BODY_SIMILARITY_THRESHOLD = 0.72
KNOWLEDGE_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
    "一个",
    "不是",
    "不要",
    "不能",
    "为了",
    "以及",
    "使用",
    "可以",
    "如果",
    "应该",
    "当前",
    "需要",
    "通过",
}

MINIMAL_AGENTS = """本文件告诉 AI 助手如何进入、理解和协助本项目。

本目录是简化版 AI 上下文根目录。默认只读取当前有效上下文和核心规则，其他资料按需读取。

---

## 默认读取顺序

1. `active/Context.md`
2. `rules/Always_Active.md`
3. `active/Feedback_Inbox.md`（仅当存在 Open 条目或需要整理人工反馈时）
4. `active/Task_Plan.md`（读取后按 `## 规划依据` 追溯当前大任务需要对齐的 reference 规划文档）
5. `active/Current_Task.md`（仅当任务状态为 Active 时）

如果用户在当前消息中已给出明确任务，以用户当前消息为准。

---

## CLI 辅助维护

如果项目可用 `acf` 命令，维护上下文时优先考虑使用它完成确定性操作。

- 开始维护前，可先运行 `acf status --json` 确认上下文位置和当前状态。
- 新增或更新当前计划、规划依据、当前任务、资料索引、知识草案、归档、worklog、ADR、section 或 table 时，优先考虑 `acf plan`（包括 `acf plan reference`）、`acf task`、`acf knowledge`、`acf archive`、`acf new`、`acf edit`、`acf writeback` 和 `acf check`。
- 需要参数细节时，先查看 `acf --help`；如果项目包含系统手册，再按需读取 System Manual。

`acf` 只负责结构化落盘、检查和草案生成，不替代人或 AI 对事实和语义的判断。

---

## 目录结构

```text
active/      当前阶段上下文、人工反馈 inbox、当前大任务计划和当前任务
rules/       核心规则
reference/   长期背景、资料索引、知识索引和决策索引
decisions/   重要决策详情
worklog/     整理后的工作记录
archive/     历史归档和 `archive/feedback/` 已处理反馈归档，默认不读取
```

---

## 按需读取指引

| 场景 | 读取文件 |
|---|---|
| 需要理解长期背景 | `reference/Project_Brief.md` |
| 需要整理人工反馈、问题、需求和计划碎片 | `active/Feedback_Inbox.md` |
| 需要追溯重要决策 | `reference/Decisions_Index.md` -> `decisions/ADR-*.md` |
| 涉及项目通用约束 | `rules/Project_Rules.md` |
| 需要了解近期进展 | `worklog/Worklog_Index.md` |
| 涉及外部资料来源 | `reference/Sources_Index.md` |
| 需要追溯可复用经验 | `reference/Knowledge_Index.md` -> `reference/knowledge/*.md` |
| 需要整理、归纳、精简上下文 | `reference/Context_Curation_Prompt.md` |

---

## 事实源优先级

1. 用户当前消息
2. `active/Current_Task.md`
3. `active/Task_Plan.md`
4. `active/Context.md`
5. `active/Feedback_Inbox.md`（只作为待整理信号，不作为已确认事实）
6. `reference/Decisions_Index.md`
7. ADR 文件
8. `reference/Knowledge_Index.md`
9. `worklog/`
10. `archive/`

knowledge 是可复用经验层，不是当前事实源；worklog 是历史过程记录，不等于当前事实；archive 默认不读取。

---

## 注意力治理与上下文预算

- 默认上下文只保留当前目标、当前事实、当前任务和下一步。
- 整理事实时优先读取 changed files、`active/`、相关索引和最近 worklog。
- 不为 curation 默认读取 archive 或全部历史日志；curation draft 不进入默认读取路径。
- 写入前必须判断唯一权威位置；能更新旧表述时，不追加重复事实。
- 低优先级文件不得重复完整表述高优先级事实；能引用权威位置时，不复制原文。

---

## 会话结束回写建议

重要协作结束时，AI 不应默认重复打印完整回写建议清单。先判断是否存在可确定写入的内容；有则优先落盘或生成可审阅草案，最终报告只列出实际变更、草案路径、验证结果和仍需人工判断的风险。

处理规则：

1. 当前任务或计划状态变化：优先使用 `acf task ...` 或 `acf plan ...` 更新 `active/Current_Task.md`、`active/Task_Plan.md`；工具不能表达时，再用 `acf edit ...` 精确更新相关 section 或表格。
2. 新的人工反馈、问题、需求碎片：优先写入或更新 `active/Feedback_Inbox.md`；如果无法确定归属，生成 `acf writeback draft ...` 草案，不把反馈直接写成当前事实。
3. 已验证的当前事实：只在与当前阶段仍相关、且证据明确时更新 `active/Context.md`；写入前先查旧表述，能 replace 时不 append；一次性过程不写入 Context。
4. 今日工作记录：完成了可复述的工作或验证后，优先使用 `acf new worklog ...` 记录整理后的摘要；同日已有记录且需要补记时使用 `--append --json`，需要重建时才使用 `--force`；不要写入原始日志或大段命令输出。
5. Knowledge 候选：优先使用 `acf knowledge draft ...` 生成草案；只有经审阅或任务明确要求时，才 apply 到 `reference/Knowledge_Index.md`。
6. Archive 候选：旧当前任务或旧大任务计划优先使用 `acf archive ...`；其他归档建议先生成 writeback 草案，等待人工确认归档位置。
7. ADR 或规则候选：已经形成稳定决策时使用 `acf new adr ...` 或更新 rules；只是建议或待确认事项时生成 writeback 草案。
8. 注意力治理候选：发现重复、过期或权威位置不清的信息时，生成 `acf writeback draft ...` 草案，列出当前事实变更、唯一权威位置、仅保留为历史的信息和待确认信号。

最终回复规则：

- 只报告本轮实际修改的文件、生成的草案、执行的检查和检查结果。
- 对没有变化的类别，不输出“无需更新”清单。
- 如果存在应回写但本轮不能安全落盘的内容，只报告草案路径或明确的人工待确认项。
- 不把 usage event log、原始测试输出、完整对话或 Feedback_Inbox 随想直接写入权威事实源。
- 不把 writeback draft 或 curation draft 加入默认读取路径。
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


@dataclass
class KnowledgeEntry:
    knowledge_id: str
    title: str
    status: str
    summary: str
    conclusion: str
    path: Path | None


@dataclass
class WorkstreamEntry:
    workstream_id: str
    status: str
    title: str
    owner: str
    write_scope: str
    depends_on: str
    output: str
    detail: str


@dataclass
class WorkstreamDetail:
    workstream_id: str
    path: Path
    metadata: dict[str, str | list[str]]
    body: str
    diagnostics: list[FrontMatterDiagnostic]


@dataclass(frozen=True)
class WorkstreamArchiveAssessment:
    detail: WorkstreamDetail
    blockers: tuple[str, ...]
    reason: str


@dataclass
class SectionRange:
    heading_index: int
    body_start: int
    body_end: int
    level: int


@dataclass(frozen=True)
class PlanReference:
    path: str
    purpose: str


@dataclass
class TableRange:
    header_index: int
    separator_index: int
    body_start: int
    body_end: int
    headers: list[str]


@dataclass
class FrontMatterDiagnostic:
    code: str
    message: str
    field: str | None = None
    line: int | None = None
    severity: str = "error"


@dataclass
class FrontMatterSchema:
    required_fields: tuple[str, ...] = ()
    allowed_fields: tuple[str, ...] | None = None
    scalar_fields: tuple[str, ...] = ()
    list_fields: tuple[str, ...] = ()
    enum_fields: dict[str, set[str]] = field(default_factory=dict)
    scope_fields: tuple[str, ...] = ()
    typed_scope_fields: tuple[str, ...] = ()
    scope_types: set[str] = field(
        default_factory=lambda: {"authority", "draft", "owned", "assigned", "evidence"}
    )


FRONT_MATTER_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
FRONT_MATTER_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
MARKDOWN_LIKE_SCOPE_PREFIXES = ("active/", "reference/", "decisions/", "rules/")


def diagnostic_codes(diagnostics: Sequence[FrontMatterDiagnostic]) -> list[str]:
    return [diagnostic.code for diagnostic in diagnostics]


def unsupported_front_matter_value(value: str) -> bool:
    stripped = value.strip()
    if stripped in {"|", ">"}:
        return True
    if stripped in {"true", "false", "True", "False"}:
        return True
    if FRONT_MATTER_NUMBER_RE.match(stripped):
        return True
    if stripped.startswith(("{", "[")) and stripped != "[]":
        return True
    if stripped.startswith(("'", '"')) or stripped.endswith(("'", '"')):
        return True
    return False


def parse_front_matter(
    text: str,
) -> tuple[dict[str, str | list[str]], str, list[FrontMatterDiagnostic]]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text, []

    end_index: int | None = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break

    if end_index is None:
        return (
            {},
            text,
            [
                FrontMatterDiagnostic(
                    "front_matter_unclosed",
                    "front matter opening marker has no closing marker",
                    line=1,
                )
            ],
        )

    metadata: dict[str, str | list[str]] = {}
    diagnostics: list[FrontMatterDiagnostic] = []
    current_list_key: str | None = None

    for line_number, raw_line in enumerate(lines[1:end_index], start=2):
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            continue

        if line.startswith("  - "):
            item = line[4:].strip()
            if current_list_key is None or not isinstance(metadata.get(current_list_key), list):
                diagnostics.append(
                    FrontMatterDiagnostic(
                        "front_matter_invalid_list_item",
                        "list item has no list field",
                        line=line_number,
                    )
                )
                continue
            if unsupported_front_matter_value(item):
                diagnostics.append(
                    FrontMatterDiagnostic(
                        "front_matter_unsupported_syntax",
                        "list item uses unsupported front matter syntax",
                        field=current_list_key,
                        line=line_number,
                    )
                )
                continue
            metadata[current_list_key].append(item)  # type: ignore[union-attr]
            continue

        current_list_key = None
        if line.startswith((" ", "\t")):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_unsupported_syntax",
                    "front matter only supports top-level fields and two-space list items",
                    line=line_number,
                )
            )
            continue

        if ":" not in line:
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_unsupported_syntax",
                    "front matter field must use KEY: VALUE syntax",
                    line=line_number,
                )
            )
            continue

        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not FRONT_MATTER_KEY_RE.match(key):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_invalid_key",
                    f"invalid front matter key: {key}",
                    field=key or None,
                    line=line_number,
                )
            )
            continue
        if key in metadata:
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_duplicate_key",
                    f"duplicate front matter key: {key}",
                    field=key,
                    line=line_number,
                )
            )
            continue

        if value == "[]":
            metadata[key] = []
        elif value == "":
            metadata[key] = []
            current_list_key = key
        elif unsupported_front_matter_value(value):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_unsupported_syntax",
                    "front matter value uses unsupported syntax",
                    field=key,
                    line=line_number,
                )
            )
        else:
            metadata[key] = value

    body = "".join(lines[end_index + 1 :])
    return metadata, body, diagnostics


def ordered_front_matter_keys(
    metadata: dict[str, str | list[str]], field_order: Sequence[str] | None
) -> list[str]:
    ordered: list[str] = []
    if field_order:
        ordered.extend(key for key in field_order if key in metadata)
    ordered.extend(sorted(key for key in metadata if key not in ordered))
    return ordered


def format_front_matter(
    metadata: dict[str, str | list[str]],
    body: str,
    field_order: Sequence[str] | None = None,
) -> str:
    lines = ["---"]
    for key in ordered_front_matter_keys(metadata, field_order):
        value = metadata[key]
        if isinstance(value, list):
            if value:
                lines.append(f"{key}:")
                lines.extend(f"  - {item}" for item in value)
            else:
                lines.append(f"{key}: []")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def required_field_missing(value: str | list[str] | None) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return not value
    return not value.strip()


def split_typed_scope(value: str) -> tuple[str | None, str | None]:
    if ":" not in value:
        return None, None
    scope_type, path = value.split(":", 1)
    return scope_type.strip(), path.strip()


def validate_scope_path(path_value: str, field_name: str) -> list[FrontMatterDiagnostic]:
    diagnostics: list[FrontMatterDiagnostic] = []
    normalized = path_value.replace("\\", "/")
    if normalized != path_value:
        diagnostics.append(
            FrontMatterDiagnostic(
                "front_matter_path_not_normalized",
                "scope path must use forward slashes",
                field=field_name,
            )
        )
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        diagnostics.append(
            FrontMatterDiagnostic(
                "front_matter_path_not_normalized",
                "scope path must be relative",
                field=field_name,
            )
        )
    if "//" in normalized:
        diagnostics.append(
            FrontMatterDiagnostic(
                "front_matter_path_not_normalized",
                "scope path contains duplicate separators",
                field=field_name,
            )
        )
    if (
        "*" not in normalized
        and normalized.startswith(MARKDOWN_LIKE_SCOPE_PREFIXES)
        and not normalized.endswith(".md")
    ):
        diagnostics.append(
            FrontMatterDiagnostic(
                "front_matter_path_missing_extension",
                "Markdown-like scope path must include .md extension",
                field=field_name,
            )
        )
    return diagnostics


def validate_front_matter(
    metadata: dict[str, str | list[str]],
    schema: FrontMatterSchema,
) -> list[FrontMatterDiagnostic]:
    diagnostics: list[FrontMatterDiagnostic] = []

    if schema.allowed_fields is not None:
        allowed = set(schema.allowed_fields)
        for key in metadata:
            if key not in allowed:
                diagnostics.append(
                    FrontMatterDiagnostic(
                        "front_matter_schema_failed",
                        f"field is not allowed: {key}",
                        field=key,
                    )
                )

    for field_name in schema.required_fields:
        if required_field_missing(metadata.get(field_name)):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"required field is missing or empty: {field_name}",
                    field=field_name,
                )
            )

    for field_name in schema.scalar_fields:
        if field_name in metadata and not isinstance(metadata[field_name], str):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"field must be a string: {field_name}",
                    field=field_name,
                )
            )

    for field_name in schema.list_fields:
        if field_name in metadata and not isinstance(metadata[field_name], list):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"field must be a list: {field_name}",
                    field=field_name,
                )
            )

    for field_name in schema.scope_fields:
        value = metadata.get(field_name)
        if value is None:
            continue
        if not isinstance(value, list):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"scope field must be a list: {field_name}",
                    field=field_name,
                )
            )
            continue
        for item in value:
            diagnostics.extend(validate_scope_path(item, field_name))

    for field_name, allowed_values in schema.enum_fields.items():
        value = metadata.get(field_name)
        if isinstance(value, str) and value not in allowed_values:
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"field has invalid value: {field_name}",
                    field=field_name,
                )
            )
        elif value is not None and not isinstance(value, str):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"enum field must be a string: {field_name}",
                    field=field_name,
                )
            )

    for field_name in schema.typed_scope_fields:
        value = metadata.get(field_name)
        if value is None:
            continue
        if not isinstance(value, list):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"typed scope field must be a list: {field_name}",
                    field=field_name,
                )
            )
            continue
        for item in value:
            scope_type, scope_path = split_typed_scope(item)
            if not scope_type or not scope_path or scope_type not in schema.scope_types:
                diagnostics.append(
                    FrontMatterDiagnostic(
                        "front_matter_scope_invalid",
                        f"scope item must use TYPE: PATH with an allowed type: {item}",
                        field=field_name,
                    )
                )
                continue
            diagnostics.extend(validate_scope_path(scope_path, field_name))

    return diagnostics


def json_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False))


def dry_run_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "dry_run", False))


def check_after_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "check_after", False))


def path_values(paths: Sequence[Path]) -> list[str]:
    return [str(path) for path in paths]


def set_result_payload(args: argparse.Namespace, payload: dict[str, object]) -> None:
    setattr(args, "_acf_result_payload", payload)


def get_result_payload(args: argparse.Namespace) -> dict[str, object]:
    payload = getattr(args, "_acf_result_payload", None)
    return payload if isinstance(payload, dict) else {}


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


def write_next_actions(dry_run: bool, check_result: CheckResult | None, changed_files: Sequence[Path] = ()) -> list[str]:
    if dry_run:
        if not changed_files:
            return ["No changes needed."]
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


def error_next_actions(error_code: str) -> list[str]:
    if error_code == "curation_draft_exists":
        return ["Review the existing curation draft; choose a different --name if a separate draft is needed."]
    if error_code == TARGET_EXISTS_APPEND_REQUIRED:
        return ["Rerun with `--append` to add an entry or `--force` to replace the daily worklog."]
    if error_code == APPEND_FORCE_CONFLICT:
        return ["Use either `--append` or `--force`, not both."]
    if error_code == ANCHOR_NOT_FOUND:
        return ["Stop and report the missing worklog anchor; do not guess an insertion point."]
    if error_code == "workstream_not_initialized":
        return ["Run `acf workstream init` for this context before using Workstream detail commands."]
    if error_code == "workstream_not_found":
        return ["Run `acf workstream list` to see available Workstream IDs."]
    if error_code == "workstream_schema_failed":
        return ["Fix the Workstream detail front matter, then rerun the command."]
    if error_code == "workstream_duplicate_id":
        return ["Choose an unused Workstream ID."]
    if error_code == "workstream_invalid_transition":
        return ["Review the Workstream state machine and use the next valid state."]
    if error_code == "workstream_reason_required":
        return ["Provide `--reason` so the blocker or cancellation is written to the detail file."]
    if error_code == "workstream_missing_merge_request":
        return ["Run `acf workstream merge-request ...` with target and summary before `ready`."]
    if error_code == "workstream_missing_evidence":
        return ["Provide `--evidence` so completion remains traceable."]
    if error_code == "workstream_missing_merge_resolution":
        return ["Provide `--merge-resolution` with one of: merged, rejected, no_merge_required, archived."]
    if error_code == "workstream_section_not_allowed":
        return ["Use one of the allowed Workstream note sections."]
    if error_code == "workstream_scope_invalid":
        return ["Use a normalized relative scope path and typed write scopes such as `assigned: src/foo.py`."]
    if error_code == "workstream_claim_conflict":
        return ["Choose a different write scope or resolve the conflicting active Workstream first."]
    if error_code == "workstream_owned_scope_invalid":
        return ["Use `owned:` only for the current Workstream detail file."]
    if error_code == "workstream_stage_duplicate_id":
        return ["Choose an unused Workstream stage ID in this Workstream detail file."]
    if error_code == "workstream_stage_scope_invalid":
        return ["Use a Workstream stage ID that belongs to the target Workstream, for example `WS004.2` in `WS004`."]
    if error_code == "workstream_stage_not_found":
        return ["Run `acf workstream stage list ...` and choose a registered stage ID."]
    if error_code == "workstream_stage_terminal":
        return ["Choose a non-terminal Workstream stage; terminal stages cannot be focused."]
    if error_code == "workstream_stage_active_conflict":
        return ["Resolve the existing Active stage first; this version does not automatically demote other Active stages."]
    if error_code == "workstream_stage_dependency_blocked":
        return ["Finish the dependent Workstream stage before focusing this stage."]
    if error_code == "workstream_stage_clear_current_required":
        return ["Pass `--clear-current` when completing the current Workstream stage."]
    if error_code == "workstream_archive_candidates_invalid_today":
        return ["Use `--today YYYY-MM-DD` or omit it to use the current date."]
    if error_code == "workstream_archive_candidates_plan_unreadable":
        return ["Fix active/Task_Plan.md or run `acf check` before reviewing archive candidates."]
    if error_code == "workstream_archive_draft_exists":
        return ["Review the existing archive draft, rerun with --name for a separate draft, or use --force to replace it."]
    if error_code == "workstream_archive_blocked":
        return ["Resolve the reported blocked_by items, then rerun the archive command."]
    if error_code == "workstream_archive_target_exists":
        return ["Review the existing archive target and choose a different manual recovery path before retrying."]
    if error_code == "workstream_archive_duplicate_index":
        return ["Fix duplicate rows in active/Workstreams.md before archiving."]
    if error_code == "task_stage_duplicate_id":
        return ["Choose an unused Task Stage ID in active/Task_Plan.md."]
    if error_code == "task_stage_scope_invalid":
        return ["Use a Task Stage ID that belongs to the parent task, for example `T001.2` under `T001`."]
    if error_code == "task_stage_parent_not_found":
        return ["Run `acf plan status ... --json` and choose an existing parent task ID."]
    if error_code == "task_stage_workstream_not_found":
        return ["Run `acf workstream list ... --json` or omit `--workstream` when no Workstream owner applies."]
    if error_code == "task_stage_not_found":
        return ["Run `acf plan stage list ... --json` and choose a registered Task Stage ID."]
    if error_code == "task_stage_missing_evidence":
        return ["Provide `--evidence` so Task Stage completion remains traceable."]
    if error_code == "input_error":
        return [
            "Check command arguments and paths.",
            "Rerun with `--help` if needed.",
        ]
    if error_code == "safety_refused":
        return [
            "Review the target state and changed files.",
            "Rerun with `--force` only if overwriting is intended.",
        ]
    if error_code == "runtime_error":
        return [
            "Inspect the error message.",
            "Rerun after fixing the unexpected failure.",
        ]
    return []


def classify_cli_error(message: str) -> tuple[str, int]:
    workstream_codes = (
        "workstream_not_initialized",
        "workstream_not_found",
        "workstream_schema_failed",
        "workstream_duplicate_id",
        "workstream_invalid_transition",
        "workstream_reason_required",
        "workstream_missing_merge_request",
        "workstream_missing_evidence",
        "workstream_missing_merge_resolution",
        "workstream_section_not_allowed",
        "workstream_scope_invalid",
        "workstream_claim_conflict",
        "workstream_owned_scope_invalid",
        "workstream_stage_duplicate_id",
        "workstream_stage_scope_invalid",
        "workstream_stage_not_found",
        "workstream_stage_terminal",
        "workstream_stage_active_conflict",
        "workstream_stage_dependency_blocked",
        "workstream_stage_clear_current_required",
        "workstream_archive_candidates_invalid_today",
        "workstream_archive_candidates_plan_unreadable",
        "workstream_archive_draft_exists",
        "workstream_archive_blocked",
        "workstream_archive_target_exists",
        "workstream_archive_duplicate_index",
    )
    task_stage_codes = (
        "task_stage_duplicate_id",
        "task_stage_scope_invalid",
        "task_stage_parent_not_found",
        "task_stage_workstream_not_found",
        "task_stage_not_found",
        "task_stage_missing_evidence",
    )
    for code in (*workstream_codes, *task_stage_codes):
        if message.startswith(f"{code}:"):
            return code, EXIT_INPUT_ERROR
    if message.startswith("curation_draft_exists:"):
        return "curation_draft_exists", EXIT_SAFETY_REFUSED
    safety_markers = (
        "already exists",
        "already contains",
        "current task is Active",
        "path is a directory",
        "similar knowledge",
        "target already exists",
        "unfinished dependencies",
        "outside context root",
        "context is locked",
    )
    if any(marker in message for marker in safety_markers):
        return "safety_refused", EXIT_SAFETY_REFUSED
    return "input_error", EXIT_INPUT_ERROR


def command_name_from_argv(argv: Sequence[str]) -> str | None:
    for token in argv:
        if token.startswith("-"):
            continue
        return token
    return None


def json_requested(argv: Sequence[str]) -> bool:
    return "--json" in argv


def emit_cli_error(argv: Sequence[str], message: str, error_code: str, exit_code: int) -> int:
    if json_requested(argv):
        print_json(
            {
                "command": command_name_from_argv(argv),
                "ok": False,
                "error_code": error_code,
                "message": message,
                "next_actions": error_next_actions(error_code),
            }
        )
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    return exit_code


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
    extra_payload: dict[str, object] | None = None,
    warnings: Sequence[str] = (),
) -> int:
    dry_run = dry_run_enabled(args)
    payload: dict[str, object] = {
        "command": command,
        "ok": check_result.ok if check_result is not None else True,
        "error_code": check_error_code(check_result),
        "dry_run": dry_run,
        "changed_files": path_values(changed_files),
        "message": message,
        "next_actions": write_next_actions(dry_run, check_result, changed_files),
    }
    if warnings:
        payload["warnings"] = list(warnings)
    if extra_payload:
        payload.update(extra_payload)
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
        for warning in warnings:
            print(f"WARN: {warning}", file=sys.stderr)

    return 0 if check_result is None or check_result.ok else 1


def lock_path_for_context(root: Path) -> Path:
    return root / LOCK_FILE_REL


def acquire_context_lock(root: Path, command: str) -> Path:
    lock_path = lock_path_for_context(root)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SystemExit(
            f"context is locked by another acf write command: {lock_path}; "
            "rerun after it finishes or remove the stale lock if no acf process is running"
        ) from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "schema_version": JSON_SCHEMA_VERSION,
                    "command": command,
                    "created_at": utc_now_iso(),
                    "pid": os.getpid(),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
    return lock_path


def release_context_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return


def write_command_context_root(args: argparse.Namespace) -> Path | None:
    command = getattr(args, "command", None)
    if command in {"init", "simplify"}:
        return None
    if command == "workstream":
        if getattr(args, "workstream_command", None) == "stage":
            if getattr(args, "workstream_stage_command", None) in {"add", "done"}:
                return require_context_root(getattr(args, "path", None))
            return None
        if getattr(args, "workstream_command", None) in {
            "init",
            "add",
            "set",
            "sync",
            "block",
            "cancel",
            "merge-request",
            "ready",
            "done",
            "archive-draft",
            "archive",
            "focus",
            "claim",
            "note",
        }:
            return require_context_root(getattr(args, "path", None))
        return None
    if command in {"upgrade", "new", "writeback", "plan", "task", "archive", "knowledge", "curate", "linkify"}:
        return require_context_root(getattr(args, "path", None))
    if command == "link":
        if getattr(args, "link_command", None) == "add":
            return require_context_root(getattr(args, "path", None))
        return None
    if command == "edit":
        return require_context_root(getattr(args, "context", None))
    return None


def run_with_context_lock(args: argparse.Namespace) -> int:
    if dry_run_enabled(args):
        return args.func(args)
    root = write_command_context_root(args)
    if root is None:
        return args.func(args)
    lock_path = acquire_context_lock(root, command_label(args))
    try:
        return args.func(args)
    finally:
        release_context_lock(lock_path)


def maybe_check_after(args: argparse.Namespace, root: Path, profile: str | None = None) -> CheckResult | None:
    if not check_after_enabled(args) or dry_run_enabled(args):
        return None
    return check_context(root, profile or infer_context_profile(root), bool(getattr(args, "strict", False)))


def required_dirs(profile: str) -> tuple[str, ...]:
    return MINIMAL_DIRS if profile == "minimal" else STANDARD_DIRS


def required_files(profile: str) -> tuple[str, ...]:
    return MINIMAL_FILES if profile == "minimal" else STANDARD_FILES


def required_files_for_check(root: Path, profile: str) -> tuple[str, ...]:
    files = required_files(profile)
    if root.resolve() == TEMPLATE_DIR.resolve():
        return files
    return tuple(rel for rel in files if rel not in TEMPLATE_EXAMPLE_FILES)


def human_layer_paths(root: Path) -> list[Path]:
    return [
        root / "human" / "Human_Notes.md",
        root / "human" / "weekly" / ".gitkeep",
        root / "human" / "reports" / ".gitkeep",
    ]


def skip_placeholder_check(root: Path, rel_file: str) -> bool:
    return root.resolve() != TEMPLATE_DIR.resolve() and rel_file in TEMPLATE_EXAMPLE_FILES


def is_acf_placeholder(value: str) -> bool:
    return ACF_PLACEHOLDER_RE.match(value) is not None


def legacy_placeholder_count(placeholders: Sequence[str]) -> int:
    return sum(1 for placeholder in placeholders if not is_acf_placeholder(placeholder))


LEGACY_ACF_MARKER_REPLACEMENTS = {
    LEGACY_UPGRADE_NOTES_START: UPGRADE_NOTES_START,
    LEGACY_UPGRADE_NOTES_END: UPGRADE_NOTES_END,
    LEGACY_WORKSTREAM_ARCHIVE_MARKER_START: WORKSTREAM_ARCHIVE_MARKER_START,
    LEGACY_WORKSTREAM_ARCHIVE_MARKER_END: WORKSTREAM_ARCHIVE_MARKER_END,
}


def migrate_legacy_acf_markers(text: str) -> str:
    updated = text
    for legacy, canonical in LEGACY_ACF_MARKER_REPLACEMENTS.items():
        updated = updated.replace(legacy, canonical)
    return updated


def legacy_acf_marker_warnings(rel_file: str, text: str) -> list[str]:
    warnings: list[str] = []
    if LEGACY_UPGRADE_NOTES_START in text or LEGACY_UPGRADE_NOTES_END in text:
        warnings.append(f"{rel_file}: legacy ACF marker `ACF:UPGRADE-NOTES` found; prefer `ACF:UPGRADE:NOTES`")
    if LEGACY_WORKSTREAM_ARCHIVE_MARKER_START in text or LEGACY_WORKSTREAM_ARCHIVE_MARKER_END in text:
        warnings.append(
            f"{rel_file}: legacy ACF marker `ACF:WORKSTREAM-ARCHIVE` found; prefer `ACF:WORKSTREAM:ARCHIVE-RECORD`"
        )
    return warnings


def has_upgrade_notes_marker(text: str) -> bool:
    return UPGRADE_NOTES_START in text or LEGACY_UPGRADE_NOTES_START in text


def has_workstream_archive_marker(text: str) -> bool:
    return WORKSTREAM_ARCHIVE_MARKER_START in text or LEGACY_WORKSTREAM_ARCHIVE_MARKER_START in text


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
    if context_root.name == "ai" and context_root.parent.name in {"docs", "docs-acf"}:
        return context_root.parent.parent
    if context_root.parent.name.lower() == "docs":
        return context_root.parent.parent
    return context_root.parent


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
        docs_acf_ai = directory / "docs-acf" / "ai"
        if is_context_root(docs_acf_ai):
            return make_context_location(docs_acf_ai)

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
    if context_root.name == "ai" and context_root.parent.name in {"docs", "docs-acf"}:
        return context_root.parent.parent
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


def context_json_path(root: Path, path: Path) -> str:
    return relative_display_path(path.resolve(), infer_project_root(root).resolve())


def slugify_project_name(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return slug or "project"


def acf_home() -> Path:
    override = os_environ_value(ACF_HOME_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".acf").resolve()


def os_environ_value(name: str) -> str:
    return os.environ.get(name, "").strip()


def usage_project_dir(project_root: Path) -> Path:
    resolved = project_root.resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
    return acf_home() / "projects" / f"{slugify_project_name(resolved.name)}-{digest}"


def usage_config_path(project_root: Path) -> Path:
    return usage_project_dir(project_root) / USAGE_LOG_CONFIG_NAME


def usage_log_path(project_root: Path) -> Path:
    return usage_project_dir(project_root) / USAGE_LOG_FILE_REL


def usage_lock_path(project_root: Path) -> Path:
    return usage_project_dir(project_root) / USAGE_LOCK_FILE_NAME


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)


def acquire_usage_lock(project_root: Path, timeout_seconds: float = 5.0) -> Path:
    lock_path = usage_lock_path(project_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "schema_version": JSON_SCHEMA_VERSION,
                            "created_at": utc_now_iso(),
                            "pid": os.getpid(),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
            return lock_path
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise SystemExit(f"usage log is locked: {lock_path}") from exc
            time.sleep(0.05)


def release_usage_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return


def read_usage_config(project_root: Path) -> dict[str, object]:
    config_path = usage_config_path(project_root)
    if not config_path.exists():
        return {"usage_log_enabled": True}
    try:
        data = json.loads(read_text(config_path))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False}
    return data if isinstance(data, dict) else {"enabled": False}


def write_usage_config(project_root: Path, enabled: bool) -> None:
    config_path = usage_config_path(project_root)
    lock_path = acquire_usage_lock(project_root)
    try:
        atomic_write_text(
            config_path,
            json.dumps(
                {
                    "schema_version": JSON_SCHEMA_VERSION,
                    "usage_log_enabled": enabled,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    finally:
        release_usage_lock(lock_path)


def usage_log_enabled(project_root: Path) -> bool:
    return bool(read_usage_config(project_root).get("usage_log_enabled", False))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_usage_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_usage_events(project_root: Path) -> list[dict[str, object]]:
    log_path = usage_log_path(project_root)
    if not log_path.exists():
        return []
    events: list[dict[str, object]] = []
    for line in read_text(log_path).splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def write_usage_events(project_root: Path, events: Sequence[dict[str, object]]) -> None:
    log_path = usage_log_path(project_root)
    text = "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in events)
    lock_path = acquire_usage_lock(project_root)
    try:
        atomic_write_text(log_path, text)
    finally:
        release_usage_lock(lock_path)


def append_usage_event(project_root: Path, event: dict[str, object]) -> None:
    log_path = usage_log_path(project_root)
    lock_path = acquire_usage_lock(project_root)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    finally:
        release_usage_lock(lock_path)


def usage_log_status_payload(project_root: Path) -> dict[str, object]:
    events = read_usage_events(project_root)
    latest = events[-1].get("timestamp") if events else None
    return {
        "command": "log status",
        "ok": True,
        "enabled": usage_log_enabled(project_root),
        "project_root": str(project_root),
        "config_path": str(usage_config_path(project_root)),
        "log_path": str(usage_log_path(project_root)),
        "event_count": len(events),
        "latest_event_at": latest,
    }


def summarize_usage_events(events: Sequence[dict[str, object]]) -> dict[str, object]:
    command_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    event_kind_counts: dict[str, int] = {}
    dry_run_count = 0
    changed_files_count = 0
    ok_count = 0
    for event in events:
        command = str(event.get("command") or "unknown")
        command_counts[command] = command_counts.get(command, 0) + 1
        event_kind = str(event.get("event_kind") or "usage")
        event_kind_counts[event_kind] = event_kind_counts.get(event_kind, 0) + 1
        if event.get("ok") is True:
            ok_count += 1
        error_code = event.get("error_code")
        if error_code:
            key = str(error_code)
            error_counts[key] = error_counts.get(key, 0) + 1
        if event.get("dry_run") is True:
            dry_run_count += 1
        changed_files = event.get("changed_files")
        if isinstance(changed_files, list):
            changed_files_count += len(changed_files)
    return {
        "event_count": len(events),
        "ok_count": ok_count,
        "failed_count": len(events) - ok_count,
        "command_counts": command_counts,
        "error_counts": error_counts,
        "event_kind_counts": event_kind_counts,
        "feedback_count": event_kind_counts.get("feedback", 0),
        "dry_run_count": dry_run_count,
        "changed_files_count": changed_files_count,
    }


def parse_usage_since(value: str) -> datetime:
    normalized = value.strip()
    if not normalized:
        raise SystemExit("--since cannot be empty")
    try:
        if DATE_RE.match(normalized):
            return datetime.fromisoformat(normalized).replace(tzinfo=timezone.utc)
        return parse_usage_timestamp(normalized) or datetime.fromisoformat(normalized).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise SystemExit(f"invalid --since value `{value}`, expected YYYY-MM-DD or ISO timestamp") from exc


def filter_usage_events(
    events: Sequence[dict[str, object]],
    since: datetime | None = None,
    commands: Sequence[str] = (),
    errors_only: bool = False,
) -> list[dict[str, object]]:
    command_set = {command.strip() for command in commands if command.strip()}
    filtered: list[dict[str, object]] = []
    for event in events:
        if since is not None:
            timestamp = parse_usage_timestamp(event.get("timestamp"))
            if timestamp is None or timestamp < since:
                continue
        if command_set and str(event.get("command") or "") not in command_set:
            continue
        if errors_only and event.get("ok") is True:
            continue
        filtered.append(event)
    return filtered


def command_label(args: argparse.Namespace) -> str:
    command = getattr(args, "command", "") or ""
    if command == "new":
        return f"new {getattr(args, 'entry_type', '')}".strip()
    if command == "writeback":
        return f"writeback {getattr(args, 'writeback_command', '')}".strip()
    if command == "edit":
        edit_target = getattr(args, "edit_target", "")
        if edit_target == "section":
            return f"edit section {getattr(args, 'section_command', '')}".strip()
        if edit_target == "table":
            return f"edit table {getattr(args, 'table_command', '')}".strip()
    if command == "log":
        return f"log {getattr(args, 'log_command', '')}".strip()
    if command == "version":
        return f"version {getattr(args, 'version_command', '')}".strip()
    if command == "plan":
        plan_command = getattr(args, "plan_command", "")
        if plan_command == "stage":
            return f"plan stage {getattr(args, 'plan_stage_command', '')}".strip()
        return f"plan {plan_command}".strip()
    if command == "task":
        return f"task {getattr(args, 'task_command', '')}".strip()
    if command == "archive":
        return f"archive {getattr(args, 'archive_command', '')}".strip()
    if command == "knowledge":
        return f"knowledge {getattr(args, 'knowledge_command', '')}".strip()
    if command == "review":
        return f"review {getattr(args, 'review_command', '')}".strip()
    if command == "audit":
        return f"audit {getattr(args, 'audit_command', '')}".strip()
    if command == "curate":
        return f"curate {getattr(args, 'curate_command', '')}".strip()
    if command == "workstream":
        return f"workstream {getattr(args, 'workstream_command', '')}".strip()
    if command == "link":
        return f"link {getattr(args, 'link_command', '')}".strip()
    return command


def usage_loggable(args: argparse.Namespace) -> bool:
    return getattr(args, "command", None) != "log"


def context_location_for_args(args: argparse.Namespace) -> ContextLocation:
    command = getattr(args, "command", None)
    if command == "status":
        return resolve_status_location(getattr(args, "path", None))
    if command == "check":
        return make_context_location(resolve_context_root(getattr(args, "path", None)))
    if command == "init":
        return make_context_location(getattr(args, "target").resolve())
    if command == "simplify":
        return make_context_location(getattr(args, "target").resolve())
    if command == "upgrade":
        return make_context_location(require_context_root(getattr(args, "path", None)))
    if command == "linkify":
        return make_context_location(require_context_root(getattr(args, "path", None)))
    if command == "link":
        return make_context_location(require_context_root(getattr(args, "path", None)))
    if command == "new":
        return make_context_location(require_context_root(getattr(args, "path", None)))
    if command == "writeback":
        return make_context_location(require_context_root(getattr(args, "path", None)))
    if command == "edit":
        return make_context_location(require_context_root(getattr(args, "context", None)))
    if command in {"plan", "task", "archive", "knowledge", "review", "audit", "workstream"}:
        return make_context_location(require_context_root(getattr(args, "path", None)))
    raise SystemExit("usage log is not available for this command")


def relative_usage_paths(values: object, project_root: Path) -> list[str]:
    if not isinstance(values, list):
        return []
    paths: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        paths.append(relative_display_path(Path(value).resolve(), project_root))
    return paths


def check_counts(payload: dict[str, object]) -> tuple[int, int]:
    check = payload.get("check")
    if not isinstance(check, dict):
        return 0, 0
    errors = check.get("errors")
    warnings = check.get("warnings")
    return (
        len(errors) if isinstance(errors, list) else 0,
        len(warnings) if isinstance(warnings, list) else 0,
    )


def build_usage_event(
    args: argparse.Namespace,
    location: ContextLocation,
    exit_code: int,
    duration_ms: int,
) -> dict[str, object]:
    payload = get_result_payload(args)
    error_count, warning_count = check_counts(payload)
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "timestamp": utc_now_iso(),
        "command": command_label(args),
        "cwd_rel": relative_display_path(Path.cwd().resolve(), location.project_root),
        "context_rel": relative_display_path(location.context_root, location.project_root),
        "profile": location.profile,
        "ok": bool(payload.get("ok", exit_code == 0)),
        "exit_code": exit_code,
        "error_code": payload.get("error_code"),
        "duration_ms": duration_ms,
        "dry_run": dry_run_enabled(args),
        "check_after": check_after_enabled(args),
        "strict": bool(getattr(args, "strict", False)),
        "json": json_enabled(args),
        "changed_files": relative_usage_paths(payload.get("changed_files"), location.project_root),
        "check_errors_count": error_count,
        "check_warnings_count": warning_count,
    }


def record_usage_event(args: argparse.Namespace, exit_code: int, duration_ms: int) -> None:
    if not usage_loggable(args):
        return
    try:
        location = context_location_for_args(args)
        if not usage_log_enabled(location.project_root):
            return
        append_usage_event(location.project_root, build_usage_event(args, location, exit_code, duration_ms))
    except BaseException:
        return


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


def section_insert_after_line(text: str, heading: str) -> int:
    lines = text.splitlines()
    section = find_section(lines, heading)
    insert_index = section.body_end
    while insert_index > section.body_start and not lines[insert_index - 1].strip():
        insert_index -= 1
    if insert_index > section.body_start and lines[insert_index - 1].strip() == "---":
        insert_index -= 1
        while insert_index > section.body_start and not lines[insert_index - 1].strip():
            insert_index -= 1
    return insert_index if insert_index > section.body_start else section.heading_index + 1


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


def validate_task_id(value: str) -> str:
    if not TASK_ID_RE.match(value):
        raise argparse.ArgumentTypeError("task id must use T001 format")
    return value


def validate_task_stage_id(value: str) -> str:
    if not TASK_STAGE_ID_RE.match(value):
        raise argparse.ArgumentTypeError("task stage id must use T001.1 format")
    return value


def validate_knowledge_id(value: str) -> str:
    if not KNOWLEDGE_ID_RE.match(value):
        raise argparse.ArgumentTypeError("knowledge id must use K001 format")
    return value


def validate_workstream_id(value: str) -> str:
    if not WORKSTREAM_ID_RE.match(value):
        raise argparse.ArgumentTypeError("workstream id must use WS001 format")
    return value


def validate_workstream_stage_id(value: str) -> str:
    if not WORKSTREAM_STAGE_ID_RE.match(value):
        raise argparse.ArgumentTypeError("workstream stage id must use WS001.1 format")
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
    plan: str,
    task_id: str,
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

## 所属大任务

{plan}

---

## 子任务 ID

{task_id}

---

## 当前执行线

无。

---

## 本次任务目标

{numbered_list(goals)}

---

## 任务背景

{background}

---

## 输入材料

当前任务应列出必要 active 文件和相关 reference 规划依据；不要只写 `active/Context.md`。

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
4. 应写入 `reference/Knowledge_Index.md` 或 Knowledge 条目的可复用经验。
5. 应归档到 archive 的历史内容。
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

## 当前事实变更候选

- 目标文件：
- 旧表述：
- 新表述：
- 建议动作：replace / append / remove / archive
- 原因：

---

## 唯一权威位置判断

- 信息类型：
- 权威位置：
- 其他位置是否已有重复：
- 建议处理：

---

## 应只保留为历史的信息

- 内容摘要：
- 建议位置：worklog / archive
- 不进入 active 的原因：

---

## 待确认信号

- 内容：
- 建议位置：Feedback_Inbox / writeback draft
- 需要谁确认：

---

## 可升格候选

- ADR 候选：
- Knowledge 候选：
- rules 候选：
- source 候选：

---

## 建议命令

- 当前任务或计划：优先使用 `acf task ...` 或 `acf plan ...`。
- 当前事实：优先使用 `acf edit section get|replace ...`，能 replace 时不 append。
- 历史过程：优先使用 `acf new worklog ...`。
- 可复用经验：优先使用 `acf knowledge draft ...`。
- 重要决策：优先使用 `acf new adr ...`。

---

## 审阅清单

- [ ] 已确认唯一权威位置。
- [ ] 已确认当前事实是 replace、append、remove 还是 archive。
- [ ] 已确认低优先级文件是否应改为引用而不是复制全文。
- [ ] 已确认哪些内容只保留为历史过程。
- [ ] 已确认哪些内容仍需人工判断。
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
            existing = read_text(daily_path)
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
    plan = getattr(args, "plan", "").strip() or "无。"
    task_id = getattr(args, "task_id", "").strip() or "无。"
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


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def resolve_context_markdown_file(root: Path, target: Path) -> Path:
    root = root.resolve()
    if target.is_absolute():
        resolved = target.resolve()
    else:
        root_candidate = (root / target).resolve()
        if not is_relative_to(root_candidate, root):
            raise SystemExit(f"target file is outside context root: {target}")

        cwd_candidate = (Path.cwd() / target).resolve()
        if cwd_candidate.exists() and is_relative_to(cwd_candidate, root):
            resolved = cwd_candidate
        else:
            resolved = root_candidate

    if not is_relative_to(resolved, root):
        raise SystemExit(f"target file is outside context root: {target}")
    if resolved.suffix.lower() != ".md":
        raise SystemExit(f"target file must be Markdown (.md): {resolved}")
    if not resolved.exists():
        raise SystemExit(f"target file does not exist: {resolved}")
    if not resolved.is_file():
        raise SystemExit(f"target path is not a file: {resolved}")
    return resolved


def resolve_context_file(root: Path, target: Path, *, must_exist: bool = True) -> Path:
    root = root.resolve()
    if target.is_absolute():
        resolved = target.resolve()
    else:
        root_candidate = (root / target).resolve()
        if not is_relative_to(root_candidate, root):
            raise SystemExit(f"target file is outside context root: {target}")

        cwd_candidate = (Path.cwd() / target).resolve()
        if cwd_candidate.exists() and is_relative_to(cwd_candidate, root):
            resolved = cwd_candidate
        else:
            resolved = root_candidate

    if not is_relative_to(resolved, root):
        raise SystemExit(f"target file is outside context root: {target}")
    if must_exist and not resolved.exists():
        raise SystemExit(f"target file does not exist: {resolved}")
    if must_exist and not resolved.is_file():
        raise SystemExit(f"target path is not a file: {resolved}")
    return resolved


def read_edit_input(args: argparse.Namespace) -> str:
    text = getattr(args, "text", None)
    input_path = getattr(args, "input", None)
    if text is not None and input_path is not None:
        raise SystemExit("use either --text or --input, not both")
    if text is not None:
        return text
    if input_path is not None:
        resolved = input_path.resolve()
        if not resolved.is_file():
            raise SystemExit(f"edit input file does not exist: {resolved}")
        return resolved.read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("edit command requires --text, --input, or stdin")


def markdown_link_target_for(md_file: Path, target_file: Path, fragment: str = "") -> str:
    relative = os.path.relpath(target_file, start=md_file.parent).replace("\\", "/")
    if fragment:
        relative = f"{relative}#{fragment}"
    return relative


def render_markdown_link(text: str, target: str) -> str:
    if any(char in target for char in " ()"):
        target = f"<{target}>"
    return f"[{text}]({target})"


def path_candidate_from_ref(root: Path, md_file: Path, ref_path: str, *, allow_missing: bool) -> Path | None:
    if not ref_path:
        return md_file
    resolved = resolve_ref_path(root, md_file, ref_path)
    if resolved is not None:
        return resolved
    if not allow_missing:
        return None
    normalized = normalize_ref_path(ref_path)
    if normalized.startswith(("../", "./")):
        candidate = (md_file.parent / normalized).resolve()
    else:
        candidate = (root / normalized).resolve()
    if not is_relative_to(candidate, root.resolve()):
        return None
    return candidate


def is_linkify_path_candidate(value: str) -> bool:
    candidate = clean_markdown_link_target(value.strip().strip("`"))
    if not is_local_link_ref(candidate):
        return False
    ref_path, _fragment = split_ref_fragment(candidate)
    if not ref_path or ref_path.endswith(("/", ".")):
        return False
    if " " in ref_path or "\t" in ref_path:
        return False
    if "/" not in ref_path and "\\" not in ref_path:
        return False
    return bool(Path(ref_path).suffix)


def linkify_candidate(
    root: Path,
    md_file: Path,
    candidate: str,
    *,
    allow_missing: bool,
) -> tuple[str | None, dict[str, str] | None]:
    display = candidate.strip().strip("`")
    if not is_linkify_path_candidate(display):
        return None, None
    ref_path, fragment = split_ref_fragment(clean_markdown_link_target(display))
    target_file = path_candidate_from_ref(root, md_file, ref_path, allow_missing=allow_missing)
    if target_file is None:
        return None, {"target": display, "reason": "missing target"}
    href = markdown_link_target_for(md_file, target_file, fragment)
    return render_markdown_link(display, href), None


def match_overlaps_spans(start: int, end: int, spans: Sequence[tuple[int, int]]) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in spans)


def replace_linkify_matches(
    line: str,
    pattern: re.Pattern[str],
    root: Path,
    md_file: Path,
    *,
    allow_missing: bool,
    protected_spans: Sequence[tuple[int, int]] = (),
) -> tuple[str, int, list[dict[str, str]]]:
    chunks: list[str] = []
    skipped: list[dict[str, str]] = []
    last = 0
    replacements = 0
    for match in pattern.finditer(line):
        if match_overlaps_spans(match.start(), match.end(), protected_spans):
            continue
        candidate = match.group(1)
        replacement, skip = linkify_candidate(root, md_file, candidate, allow_missing=allow_missing)
        if skip is not None:
            skipped.append(skip)
        if replacement is None:
            continue
        chunks.append(line[last : match.start()])
        chunks.append(replacement)
        last = match.end()
        replacements += 1
    if replacements == 0:
        return line, 0, skipped
    chunks.append(line[last:])
    return "".join(chunks), replacements, skipped


def linkify_markdown_text(
    root: Path,
    md_file: Path,
    text: str,
    *,
    allow_missing: bool,
) -> tuple[str, int, list[dict[str, str]]]:
    updated_lines: list[str] = []
    total = 0
    skipped: list[dict[str, str]] = []
    in_fence = False
    fence_marker = ""
    in_front_matter = False
    front_matter_done = False
    code_ref_re = re.compile(r"`([^`\n]+)`")
    for index, line in enumerate(text.splitlines()):
        if index == 0 and line.strip() == "---":
            in_front_matter = True
            updated_lines.append(line)
            continue
        if in_front_matter:
            updated_lines.append(line)
            if line.strip() == "---":
                in_front_matter = False
                front_matter_done = True
            continue
        if not front_matter_done and line.strip():
            front_matter_done = True

        stripped = line.lstrip()
        fence = re.match(r"^(```+|~~~+)", stripped)
        if fence:
            marker = fence.group(1)[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            updated_lines.append(line)
            continue
        if in_fence:
            updated_lines.append(line)
            continue

        link_spans = [(match.start(), match.end()) for match in MARKDOWN_LINK_RE.finditer(line)]
        line, count, line_skipped = replace_linkify_matches(
            line,
            code_ref_re,
            root,
            md_file,
            allow_missing=allow_missing,
            protected_spans=link_spans,
        )
        total += count
        skipped.extend(line_skipped)

        link_spans = [(match.start(), match.end()) for match in MARKDOWN_LINK_RE.finditer(line)]
        code_spans = [(match.start(), match.end()) for match in code_ref_re.finditer(line)]
        line, count, line_skipped = replace_linkify_matches(
            line,
            PATH_LIKE_RE,
            root,
            md_file,
            allow_missing=allow_missing,
            protected_spans=[*link_spans, *code_spans],
        )
        total += count
        skipped.extend(line_skipped)
        updated_lines.append(line)

    trailing_newline = "\n" if text.endswith("\n") else ""
    return "\n".join(updated_lines) + trailing_newline, total, skipped


def linkify_candidate_files(root: Path, args: argparse.Namespace) -> list[Path]:
    files: set[Path] = set()
    for dirname in LINKIFY_DEFAULT_DIRS:
        directory = root / dirname
        if directory.exists():
            files.update(path for path in directory.rglob("*.md") if path.is_file())
    for rel in LINKIFY_DEFAULT_FILES:
        file_path = root / rel
        if file_path.is_file():
            files.add(file_path)
    if getattr(args, "include_worklog_daily", False):
        daily = root / "worklog" / "daily"
        if daily.exists():
            files.update(path for path in daily.rglob("*.md") if path.is_file())
    if getattr(args, "include_archive", False):
        archive = root / "archive"
        if archive.exists():
            files.update(path for path in archive.rglob("*.md") if path.is_file())
    return sorted(files)


def linkify_command(args: argparse.Namespace) -> int:
    if getattr(args, "format", "markdown") != "markdown":
        raise SystemExit("linkify currently supports only --format markdown")
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    changed_files: list[Path] = []
    updated_entries: list[dict[str, object]] = []
    skipped_entries: list[dict[str, str]] = []
    for md_file in linkify_candidate_files(root, args):
        original = read_text(md_file)
        updated, replacements, skipped = linkify_markdown_text(
            root,
            md_file,
            original,
            allow_missing=bool(getattr(args, "allow_missing", False)),
        )
        rel_file = md_file.relative_to(root).as_posix()
        skipped_entries.extend({"file": rel_file, **entry} for entry in skipped)
        if updated == original:
            continue
        changed_files.append(md_file)
        updated_entries.append({"path": rel_file, "replacements": replacements})
        if not dry_run:
            atomic_write_text(md_file, updated)

    check_result = maybe_check_after(args, root)
    action = "would linkify" if dry_run else "linkified"
    return emit_write_result(
        args,
        "linkify",
        f"{action} {len(changed_files)} file(s)",
        changed_files,
        check_result,
        extra_payload={
            "format": args.format,
            "updated": updated_entries,
            "skipped": skipped_entries,
        },
    )


def link_add_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    target_file = resolve_context_markdown_file(root, args.file)
    link_target_file = resolve_context_file(root, args.target)
    target_fragment = ""
    if args.target_heading:
        if link_target_file.suffix.lower() != ".md":
            raise SystemExit("--target-heading requires a Markdown target file")
        anchor = markdown_heading_anchor_for(read_text(link_target_file), args.target_heading)
        if anchor is None:
            raise SystemExit(f"target heading was not found: {args.target_heading}")
        target_fragment = anchor
    link_href = markdown_link_target_for(target_file, link_target_file, target_fragment)
    context_target_display = link_target_file.relative_to(root).as_posix()
    default_text = f"{context_target_display}#{target_fragment}" if target_fragment else context_target_display
    link_text = args.text or default_text
    bullet = f"- {render_markdown_link(link_text, link_href)}"

    original = read_text(target_file)
    original_lines = original.splitlines()
    body = section_body(original_lines, find_section(original_lines, args.heading))
    duplicate_markers = {f"]({link_href})", f"](<{link_href}>)"}
    if not args.force and any(marker in body for marker in duplicate_markers):
        raise SystemExit(f"link already exists in section: {link_href}")
    updated = append_section_text(original, args.heading, bullet)
    changed_files = [target_file] if updated != original else []
    if changed_files and not dry_run:
        atomic_write_text(target_file, updated)

    check_result = maybe_check_after(args, root)
    action = "would add" if dry_run else "added"
    return emit_write_result(
        args,
        "link add",
        f"{action} link to {target_file}",
        changed_files,
        check_result,
        extra_payload={
            "file": target_file.relative_to(root).as_posix(),
            "heading": args.heading,
            "link": bullet,
            "target": context_target_display,
            "target_heading": args.target_heading,
        },
    )


def heading_level(line: str) -> int | None:
    match = MARKDOWN_HEADING_RE.match(line.strip())
    if match is None:
        return None
    return len(match.group(1))


def find_section(lines: Sequence[str], heading: str) -> SectionRange:
    expected = heading.strip()
    if heading_level(expected) is None:
        raise SystemExit(f"section heading must be a Markdown heading: {heading}")

    heading_index = next((index for index, line in enumerate(lines) if line.strip() == expected), None)
    if heading_index is None:
        raise SystemExit(f"section heading was not found: {heading}")

    level = heading_level(lines[heading_index])
    if level is None:
        raise SystemExit(f"section heading must be a Markdown heading: {heading}")

    body_start = heading_index + 1
    body_end = len(lines)
    for index in range(body_start, len(lines)):
        candidate_level = heading_level(lines[index])
        if candidate_level is not None and candidate_level <= level:
            body_end = index
            break

    return SectionRange(heading_index, body_start, body_end, level)


def section_content_and_suffix(lines: Sequence[str], section: SectionRange) -> tuple[list[str], list[str]]:
    content = list(lines[section.body_start : section.body_end])
    while content and not content[-1].strip():
        content.pop()

    suffix: list[str] = []
    if content and content[-1].strip() == "---":
        content.pop()
        while content and not content[-1].strip():
            content.pop()
        suffix = ["---", ""]

    while content and not content[0].strip():
        content.pop(0)

    return content, suffix


def section_body(lines: Sequence[str], section: SectionRange) -> str:
    content, _suffix = section_content_and_suffix(lines, section)
    return "\n".join(content).strip("\n")


def normalized_section_body_lines(text: str) -> list[str]:
    stripped = text.strip("\n")
    return stripped.splitlines() if stripped else []


def apply_section_body(
    lines: Sequence[str],
    section: SectionRange,
    body_lines: Sequence[str],
    suffix_lines: Sequence[str] | None = None,
) -> str:
    replacement = list(body_lines)
    new_section = [lines[section.heading_index], ""]
    new_section.extend(replacement)
    suffix = list(suffix_lines or [])
    if suffix:
        if replacement:
            new_section.append("")
        new_section.extend(suffix)
    elif replacement:
        new_section.append("")

    updated_lines = (
        list(lines[: section.heading_index])
        + new_section
        + list(lines[section.body_end :])
    )
    return "\n".join(updated_lines).rstrip() + "\n"


def replace_section_text(original: str, heading: str, replacement: str) -> str:
    lines = original.splitlines()
    section = find_section(lines, heading)
    _content, suffix = section_content_and_suffix(lines, section)
    return apply_section_body(lines, section, normalized_section_body_lines(replacement), suffix)


def append_section_text(original: str, heading: str, addition: str) -> str:
    lines = original.splitlines()
    section = find_section(lines, heading)
    body_lines, suffix = section_content_and_suffix(lines, section)
    addition_lines = normalized_section_body_lines(addition)
    if body_lines and addition_lines:
        body_lines.append("")
    body_lines.extend(addition_lines)
    return apply_section_body(lines, section, body_lines, suffix)


def insert_section_after(text: str, anchor_heading: str, heading: str, body: str) -> str:
    lines = text.splitlines()
    anchor = find_section(lines, anchor_heading)
    insert_at = anchor.body_end
    while insert_at > anchor.body_start and not lines[insert_at - 1].strip():
        insert_at -= 1
    if insert_at > anchor.body_start and lines[insert_at - 1].strip() == "---":
        insert_at -= 1
        while insert_at > anchor.body_start and not lines[insert_at - 1].strip():
            insert_at -= 1
    section_lines = ["", "---", "", heading, "", *normalized_section_body_lines(body), ""]
    updated = lines[:insert_at] + section_lines + lines[insert_at:]
    return "\n".join(updated).rstrip() + "\n"


def insert_section_before(text: str, anchor_heading: str, heading: str, body: str) -> str:
    lines = text.splitlines()
    anchor = find_section(lines, anchor_heading)
    insert_at = anchor.heading_index
    while insert_at > 0 and not lines[insert_at - 1].strip():
        insert_at -= 1
    section_lines = [heading, "", *normalized_section_body_lines(body), "", "---", ""]
    updated = lines[:insert_at] + section_lines + lines[insert_at:]
    return "\n".join(updated).rstrip() + "\n"


def normalize_plan_reference_path(value: str) -> str:
    normalized = strip_code_ticks(value).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or "\\" in normalized
        or any(part in {"", ".", ".."} for part in parts)
        or parts[0] != "reference"
        or not normalized.lower().endswith(".md")
    ):
        raise SystemExit("plan reference path must be a relative reference/*.md path")
    return "/".join(parts)


def normalize_plan_reference_purpose(value: str) -> str:
    purpose = value.strip()
    if not purpose:
        raise SystemExit("plan reference purpose cannot be empty")
    if purpose[-1] not in "。.！!?？":
        purpose += "。"
    return purpose


def render_plan_reference(reference: PlanReference) -> str:
    return f"- [{reference.path}](../{reference.path})：{reference.purpose}"


def render_plan_reference_input(reference: PlanReference) -> str:
    return f"[{reference.path}](../{reference.path})：{reference.purpose}"


def render_plan_reference_section(
    references: Sequence[PlanReference],
    *,
    placeholder: bool = False,
    upgrade_prompt: bool = False,
) -> str:
    if placeholder:
        bullets = [
            "- `reference/【规划依据文档 1】.md`：【该规划依据的用途】。",
            "- `reference/【规划依据文档 2】.md`：【该规划依据的用途】。",
        ]
    elif upgrade_prompt:
        bullets = [PLAN_REFERENCE_EMPTY, PLAN_REFERENCE_UPGRADE_PROMPT]
    else:
        bullets = [render_plan_reference(reference) for reference in references] or [PLAN_REFERENCE_EMPTY]
    return "\n".join([PLAN_REFERENCE_SECTION_INTRO, "", *bullets])


def parse_plan_references_from_body(body: str) -> tuple[list[PlanReference], list[str]]:
    references: list[PlanReference] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for raw_line in normalized_section_body_lines(body):
        line = raw_line.strip()
        if not line.startswith("-"):
            continue
        if line in {PLAN_REFERENCE_EMPTY, "- 暂无。", PLAN_REFERENCE_UPGRADE_PROMPT}:
            continue
        match = PLAN_REFERENCE_BULLET_RE.match(line)
        if not match:
            warnings.append(f"ignored non-standard plan reference line: {line}")
            continue
        if PLACEHOLDER_RE.search(line):
            continue
        path = normalize_plan_reference_path(match.group("path") or match.group("link_path") or "")
        purpose = normalize_plan_reference_purpose(match.group("purpose"))
        if path in seen:
            warnings.append(f"ignored duplicate plan reference path: {path}")
            continue
        seen.add(path)
        references.append(PlanReference(path, purpose))
    return references, warnings


def read_plan_references(plan_path: Path) -> tuple[list[PlanReference], list[str]]:
    section = find_section(read_text(plan_path).splitlines(), PLAN_REFERENCE_HEADING)
    return parse_plan_references_from_body(section_body(read_text(plan_path).splitlines(), section))


def write_plan_references_text(text: str, references: Sequence[PlanReference]) -> str:
    return replace_section_text(text, PLAN_REFERENCE_HEADING, render_plan_reference_section(references))


def valid_plan_reference_input_lines(plan_path: Path) -> list[str]:
    try:
        references, _warnings = read_plan_references(plan_path)
    except SystemExit:
        return [CURRENT_TASK_REFERENCE_PROMPT.removeprefix("- ")]
    return [render_plan_reference_input(reference) for reference in references] or [
        CURRENT_TASK_REFERENCE_PROMPT.removeprefix("- ")
    ]


def current_task_has_active_status(text: str) -> bool:
    try:
        section = find_section(text.splitlines(), "## 当前任务状态")
    except SystemExit:
        return False
    return section_body(text.splitlines(), section).splitlines()[0].strip() == "Active" if section_body(text.splitlines(), section).strip() else False


def standard_reference_line_path(line: str) -> str | None:
    match = PLAN_REFERENCE_BULLET_RE.match(line.strip())
    if not match or PLACEHOLDER_RE.search(line):
        return None
    return normalize_plan_reference_path(match.group("path") or match.group("link_path") or "")


def sync_current_task_reference_text(
    text: str,
    reference: PlanReference,
    *,
    operation: str,
    force: bool = False,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not current_task_has_active_status(text):
        warnings.append("active/Current_Task.md is not Active; skipped reference sync")
        return text, warnings
    lines = text.splitlines()
    try:
        section = find_section(lines, "## 输入材料")
    except SystemExit:
        warnings.append("active/Current_Task.md has no ## 输入材料 section; skipped reference sync")
        return text, warnings

    body_lines, suffix = section_content_and_suffix(lines, section)
    target_line = render_plan_reference(reference)
    existing_index: int | None = None
    nonstandard_same_path = False
    for index, line in enumerate(body_lines):
        line_path = standard_reference_line_path(line)
        if line_path == reference.path:
            existing_index = index
            break
        if f"`{reference.path}`" in line:
            nonstandard_same_path = True

    if operation == "add":
        if existing_index is not None:
            if body_lines[existing_index].strip() == target_line:
                return text, warnings
            if force:
                body_lines[existing_index] = target_line
            else:
                warnings.append(f"active/Current_Task.md already references `{reference.path}` with a different purpose")
                return text, warnings
        elif nonstandard_same_path:
            warnings.append(f"active/Current_Task.md contains a non-standard reference line for `{reference.path}`; skipped reference sync")
            return text, warnings
        else:
            stripped = [line.strip() for line in body_lines if line.strip()]
            if stripped == [PLAN_REFERENCE_EMPTY]:
                body_lines = [target_line]
            else:
                insert_at = len(body_lines)
                while insert_at > 0 and not body_lines[insert_at - 1].strip():
                    insert_at -= 1
                body_lines.insert(insert_at, target_line)
    elif operation == "remove":
        if existing_index is None:
            if nonstandard_same_path:
                warnings.append(f"active/Current_Task.md keeps a non-standard reference line for `{reference.path}`")
            return text, warnings
        if body_lines[existing_index].strip() == target_line:
            body_lines.pop(existing_index)
        else:
            warnings.append(f"active/Current_Task.md reference for `{reference.path}` differs from the plan entry; skipped reference sync")
            return text, warnings
    else:
        raise SystemExit(f"unknown reference sync operation: {operation}")

    return apply_section_body(lines, section, body_lines, suffix), warnings


def edit_section_get_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.context)
    target = resolve_context_markdown_file(root, args.file)
    lines = read_text(target).splitlines()
    section = find_section(lines, args.heading)
    body = section_body(lines, section)
    payload: dict[str, object] = {
        "command": "edit section get",
        "ok": True,
        "context": str(root),
        "file": str(target),
        "heading": args.heading,
        "body": body,
        "heading_line": section.heading_index + 1,
        "body_start_line": section.body_start + 1,
        "body_end_line": section.body_end,
    }
    set_result_payload(args, payload)

    if json_enabled(args):
        print_json(payload)
    else:
        print(body)
    return 0


def edit_section_replace_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.context)
    dry_run = dry_run_enabled(args)
    target = resolve_context_markdown_file(root, args.file)
    updated = replace_section_text(read_text(target), args.heading, read_edit_input(args))
    if not dry_run:
        target.write_text(updated, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would replace" if dry_run else "replaced"
    return emit_write_result(
        args,
        "edit section replace",
        f"{action} section {args.heading} in {target}",
        [target],
        check_result,
    )


def edit_section_append_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.context)
    dry_run = dry_run_enabled(args)
    target = resolve_context_markdown_file(root, args.file)
    updated = append_section_text(read_text(target), args.heading, read_edit_input(args))
    if not dry_run:
        target.write_text(updated, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would append" if dry_run else "appended"
    return emit_write_result(
        args,
        "edit section append",
        f"{action} to section {args.heading} in {target}",
        [target],
        check_result,
    )


def split_table_line(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def is_table_separator(line: str) -> bool:
    if not is_table_line(line):
        return False
    cells = split_table_line(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def table_header_matches(line: str, header: str | None) -> bool:
    if header is None:
        return True
    if not is_table_line(line):
        return False
    return split_table_line(line) == split_table_line(header)


def find_table(lines: Sequence[str], header: str | None) -> TableRange:
    for index, line in enumerate(lines[:-1]):
        if not table_header_matches(line, header):
            continue
        if not is_table_line(line) or not is_table_separator(lines[index + 1]):
            continue

        body_start = index + 2
        body_end = body_start
        while body_end < len(lines) and is_table_line(lines[body_end]):
            body_end += 1
        return TableRange(index, index + 1, body_start, body_end, split_table_line(line))

    if header is None:
        raise SystemExit("Markdown table was not found")
    raise SystemExit(f"Markdown table header was not found: {header}")


def parse_cell_updates(values: Sequence[str]) -> dict[str, str]:
    updates: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"table cell update must use COLUMN=VALUE: {value}")
        column, cell_value = value.split("=", 1)
        column = column.strip()
        if not column:
            raise SystemExit(f"table cell update has empty column name: {value}")
        updates[column] = cell_value.strip()
    return updates


def render_table_row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(clean_table_cell(cell) for cell in cells) + " |"


def upsert_table_row(
    original: str,
    header: str | None,
    key_column: str,
    key: str,
    cell_updates: dict[str, str],
) -> str:
    lines = original.splitlines()
    table = find_table(lines, header)
    headers = table.headers
    if key_column not in headers:
        raise SystemExit(f"table key column was not found: {key_column}")

    unknown_columns = sorted(set(cell_updates) - set(headers))
    if unknown_columns:
        raise SystemExit(f"table cell column was not found: {', '.join(unknown_columns)}")

    key_index = headers.index(key_column)
    updated_rows = list(lines[table.body_start : table.body_end])
    target_row_index: int | None = None
    for index, row in enumerate(updated_rows):
        row_cells = split_table_line(row)
        if len(row_cells) != len(headers):
            raise SystemExit(f"table row has {len(row_cells)} cells but header has {len(headers)} cells: {row}")
        if row_cells[key_index] == key:
            target_row_index = index
            break

    if target_row_index is None:
        row_cells = [""] * len(headers)
    else:
        row_cells = split_table_line(updated_rows[target_row_index])

    row_cells[key_index] = key
    for column, value in cell_updates.items():
        row_cells[headers.index(column)] = value

    rendered = render_table_row(row_cells)
    if target_row_index is None:
        updated_rows.append(rendered)
    else:
        updated_rows[target_row_index] = rendered

    updated_lines = list(lines[: table.body_start]) + updated_rows + list(lines[table.body_end :])
    return "\n".join(updated_lines).rstrip() + "\n"


def edit_table_upsert_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.context)
    dry_run = dry_run_enabled(args)
    target = resolve_context_markdown_file(root, args.file)
    updated = upsert_table_row(
        read_text(target),
        args.header,
        args.key_column,
        args.key,
        parse_cell_updates(args.cell),
    )
    if not dry_run:
        target.write_text(updated, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would upsert" if dry_run else "upserted"
    return emit_write_result(
        args,
        "edit table upsert",
        f"{action} table row {args.key} in {target}",
        [target],
        check_result,
    )


def slugify_file_stem(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = re.sub(r"[^\w.-]+", "-", normalized, flags=re.UNICODE).strip(".-_")
    return normalized or hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]


def normalize_release_version(value: str) -> tuple[str, str]:
    raw = value.strip()
    if raw.startswith("v"):
        raw = raw[1:]
    if not re.fullmatch(r"\d+(?:\.\d+)+", raw):
        raise SystemExit(f"invalid version `{value}`, expected for example v0.0.3.6")
    return f"v{raw}", raw


def replace_regex_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"could not update {label}")
    return updated


def version_files() -> list[Path]:
    root = require_source_project_root()
    files = [root / "acf.py", root / "pyproject.toml"]
    pkg_info = root / "ai_context_framework.egg-info" / "PKG-INFO"
    uv_lock = root / "uv.lock"
    if pkg_info.exists():
        files.append(pkg_info)
    if uv_lock.exists():
        files.append(uv_lock)
    return files


def is_source_project_root(path: Path) -> bool:
    pyproject_path = path / "pyproject.toml"
    acf_path = path / "acf.py"
    if not pyproject_path.exists() or not acf_path.exists():
        return False
    return 'name = "ai-context-framework"' in read_text(pyproject_path)


def discover_source_project_root(start: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if start is not None:
        candidates.extend([start.resolve(), *start.resolve().parents])
    candidates.append(ROOT)
    for candidate in candidates:
        if is_source_project_root(candidate):
            return candidate
    return None


def require_source_project_root() -> Path:
    root = discover_source_project_root(Path.cwd())
    if root is None:
        raise SystemExit("version set requires an ai-context-framework source checkout")
    return root


def installed_package_version() -> str | None:
    try:
        return importlib.metadata.version("ai-context-framework")
    except importlib.metadata.PackageNotFoundError:
        return None


def read_project_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {
        "cli": VERSION,
        "pyproject": None,
        "pkg_info": None,
        "uv_lock": None,
    }
    source_root = discover_source_project_root(Path.cwd())
    if source_root is None:
        versions["pkg_info"] = installed_package_version()
        return versions

    acf_path = source_root / "acf.py"
    pyproject_path = source_root / "pyproject.toml"
    pkg_info_path = source_root / "ai_context_framework.egg-info" / "PKG-INFO"
    uv_lock_path = source_root / "uv.lock"
    if acf_path.exists():
        match = re.search(r'^VERSION = "([^"]+)"', read_text(acf_path), flags=re.MULTILINE)
        if match:
            versions["cli"] = match.group(1)
    if pyproject_path.exists():
        match = re.search(r'^version = "([^"]+)"', read_text(pyproject_path), flags=re.MULTILINE)
        if match:
            versions["pyproject"] = match.group(1)
    if pkg_info_path.exists():
        match = re.search(r"^Version: (.+)$", read_text(pkg_info_path), flags=re.MULTILINE)
        if match:
            versions["pkg_info"] = match.group(1).strip()
    else:
        versions["pkg_info"] = installed_package_version()
    if uv_lock_path.exists():
        match = re.search(r'(?ms)name = "ai-context-framework".*?^version = "([^"]+)"', read_text(uv_lock_path))
        if match:
            versions["uv_lock"] = match.group(1)
    return versions


def version_show_command(args: argparse.Namespace) -> int:
    versions = read_project_versions()
    payload: dict[str, object] = {
        "command": "version show",
        "ok": True,
        "version": versions.get("cli"),
        "versions": versions,
        "error_code": None,
        "next_actions": [],
    }
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"version: {versions.get('cli')}")
        for key, value in versions.items():
            print(f"{key}: {value}")
    return 0


def version_set_command(args: argparse.Namespace) -> int:
    dry_run = dry_run_enabled(args)
    cli_version, package_version = normalize_release_version(args.value)
    root = require_source_project_root()
    changed = version_files()
    if not dry_run:
        acf_path = root / "acf.py"
        pyproject_path = root / "pyproject.toml"
        acf_path.write_text(
            replace_regex_once(read_text(acf_path), r'^VERSION = "[^"]+"', f'VERSION = "{cli_version}"', "acf.py VERSION"),
            encoding="utf-8",
        )
        pyproject_path.write_text(
            replace_regex_once(read_text(pyproject_path), r'^version = "[^"]+"', f'version = "{package_version}"', "pyproject.toml version"),
            encoding="utf-8",
        )
        pkg_info_path = root / "ai_context_framework.egg-info" / "PKG-INFO"
        if pkg_info_path.exists():
            pkg_info_path.write_text(
                replace_regex_once(read_text(pkg_info_path), r"^Version: .+$", f"Version: {package_version}", "PKG-INFO version"),
                encoding="utf-8",
            )
        uv_lock_path = root / "uv.lock"
        if uv_lock_path.exists():
            uv_lock_path.write_text(
                replace_regex_once(
                    read_text(uv_lock_path),
                    r'(?ms)(name = "ai-context-framework".*?^version = ")[^"]+(")',
                    rf"\g<1>{package_version}\2",
                    "uv.lock version",
                ),
                encoding="utf-8",
            )
    action = "would set" if dry_run else "set"
    return emit_write_result(
        args,
        "version set",
        f"{action} version to {cli_version}",
        changed,
        extra_payload={"version": cli_version, "package_version": package_version},
    )


def render_empty_task_plan() -> str:
    return render_task_plan(
        "Empty",
        "无。",
        ["无。"],
        ["无。"],
        "无。",
        [],
    )


def render_feedback_inbox() -> str:
    return """本文件记录人工临时反馈、问题、需求和计划碎片。

这里允许写得不规范。它的作用是先接住重要信号，再由人或 AI 后续整理到 `active/Task_Plan.md`、`active/Context.md`、ADR、worklog 或 Knowledge。

---

## 状态说明

- Open：尚未整理；AI 看到后应先判断归属，不直接视为当前事实。
- Triaged：已判断归属，但尚未完全落盘；后续处理必须说明目标文件、计划项或草案位置。
- Planned：已进入 `active/Task_Plan.md` 或当前任务，等待按计划完成。
- Done：已处理完成，后续处理列必须给出证据位置；只在近期或当前计划仍需引用时保留在 active 表中。
- Rejected：明确不采纳或不再适用，后续处理列必须说明拒绝原因或替代位置；只在近期仍有解释价值时保留。

---

## 反馈条目

| ID | 状态 | 类型 | 内容 | 来源 | 后续处理 |
|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |

---

## 使用规则

1. 人工可以直接追加粗糙描述，不要求一开始就结构化。
2. AI 看到 Open 条目时，应先判断是否需要转入任务计划、当前事实、ADR、worklog、rules、Knowledge 或 writeback 草案。
3. AI 不应把本文件中的随想直接当作已确认事实；只有转入对应事实源或计划后，才按目标文件的事实源级别使用。
4. 状态推进顺序通常是 Open -> Triaged -> Planned -> Done；不采纳时使用 Rejected，并在后续处理列说明原因。
5. Planned 条目必须引用 `active/Task_Plan.md` 的任务 ID、`active/Current_Task.md` 的任务名称，或明确说明等待哪一类落盘动作。
6. Done 或 Rejected 条目必须保留证据位置，例如计划任务、worklog、ADR、Context、Knowledge 草案或拒绝理由。
7. active 表只长期保留 Open、Triaged、Planned，以及当前大任务仍需解释的 Done/Rejected 条目。
8. 清理阈值：当 Done/Rejected 条目超过 10 条，或条目完成超过 30 天且不再支撑当前计划时，应整理到反馈归档。
9. 反馈归档位置使用 `archive/feedback/`，归档文件按月份命名为 YYYY-MM.md；归档摘要应记录 ID、状态、类型、内容摘要、处理结果和证据位置，不复制长过程。
10. AI 执行反馈清理时，应先确认条目已有证据位置，再移动或摘要归档；不能确定是否仍需保留时，生成 writeback 草案而不是删除。
"""


def render_human_notes() -> str:
    return """# Human Notes

本文件记录人工异步写入的随笔、疑问、注释、规划草稿和待确认修改。AI 必须先分类，不得直接把本文件内容当作已确认事实。

---

## Inbox

| ID | 状态 | 类型 | 内容 | 关联位置 | AI 处理建议 | 证据 |
|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |

---

## 使用规则

1. 本文件是 human 层入口，不是 active 当前事实源。
2. `[[双链]]` 只作为人工导航，不替代 ACF 需要解析的标准路径、front matter、heading 或 table。
3. 已确认事实应转写到 `active/Context.md`、`active/Task_Plan.md`、ADR、Knowledge 或 worklog。
4. weekly / reports 中的内容默认不进入 AI 必读路径，只有在回顾、汇报或路线复盘时按需读取。
"""


def render_task_plan(
    status: str,
    title: str,
    goals: Sequence[str],
    success: Sequence[str],
    focus: str,
    rows: Sequence[dict[str, str]],
) -> str:
    rendered_rows = [
        render_table_row(
            [
                row.get("ID", ""),
                row.get("状态", ""),
                row.get("子任务", ""),
                row.get("依赖", ""),
                row.get("输出物", ""),
                row.get("证据", ""),
                row.get("下一步", ""),
            ]
        )
        for row in rows
    ] or ["| 暂无 |  |  |  |  |  |  |"]
    return f"""本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

{status}

---

## 大任务名称

{title}

---

## 大任务目标

{numbered_list(goals)}

---

## 成功标准

{numbered_list(success)}

---

## 规划依据

{render_plan_reference_section(())}

---

## 当前焦点

{focus}

---

## 子任务

{TASK_TABLE_HEADER}
|---|---|---|---|---|---|---|
{chr(10).join(rendered_rows)}

---

## 任务阶段

{TASK_STAGE_TABLE_HEADER}
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 当前大任务依赖 reference 规划时，必须在 `## 规划依据` 列出路径和一句话用途。
4. 已失效的大任务计划应归档到 `archive/plans/`。
5. 不要把历史过程、完整日志或详细推理写入本文件。
"""


def render_archive_index() -> str:
    return f"""本文件记录历史归档索引。

请注意：

- archive 是历史材料，不是当前事实源。
- 默认不要读取 archive；只有需要追溯旧任务、旧计划或比较历史版本时才读取。

---

## 归档条目

{ARCHIVE_TABLE_HEADER}
|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |
"""


def render_knowledge_index() -> str:
    return f"""本文件记录可复用经验索引。

这里只保存从 worklog、ADR、任务复盘或评测中提炼出的经验、模式、反例和判断方法，不保存当前事实、不保存一次性过程、不重复 ADR 或 rules。

---

## Knowledge 状态说明

- Draft：初步提炼，待验证。
- Active：当前可复用经验。
- Promoted：已升级为 rules、ADR、手册或其他权威位置。
- Stale：可能过时，需要重新评估。
- Rejected：提炼错误或不再适用。

---

## Knowledge 条目

{KNOWLEDGE_TABLE_HEADER}
|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |

---

## 使用规则

1. Knowledge 不是当前事实源。
2. 每条 Knowledge 必须引用来源。
3. Knowledge 只记录可迁移判断，不复述当前状态。
4. 如果经验升级为强约束或重要决策，应标记为 Promoted，并指向新的权威位置。
"""


def upgrade_notes_block(target: str) -> str:
    if target == "agents":
        body = """## ACF Current Schema Upgrade Notes

- 默认读取顺序应包含 `active/Feedback_Inbox.md` 和 `active/Task_Plan.md`，并位于 `active/Current_Task.md` 之前。
- 结构化维护优先使用 `acf plan`、`acf plan reference`、`acf task`、`acf archive` 和 `acf knowledge`。
- `active/Task_Plan.md` 的 `## 规划依据` 用于追溯当前大任务必须对齐的 reference 文档。
- Feedback_Inbox 已处理条目的长期归档位置是 `archive/feedback/`。
- 旧任务或旧计划不会由 `acf upgrade` 自动移动；需要归档时显式运行 archive 命令。"""
    else:
        body = """## ACF Current Schema Upgrade Notes

- `acf upgrade [target]` 只补齐 Feedback_Inbox、Task_Plan、archive、archive/feedback、Knowledge 结构和 active -> reference 规划依据追溯入口。
- 推荐升级流程：`acf upgrade --dry-run --json` -> 审阅 changed_files -> `acf upgrade --check-after --json` -> `acf check --strict --json`。
- Active `active/Current_Task.md` 不会被覆盖，旧任务归档请显式使用 `acf archive current-task` 或 `acf archive task-plan`。"""
    return f"\n\n{UPGRADE_NOTES_START}\n{body}\n{UPGRADE_NOTES_END}\n"


def append_upgrade_notes_if_needed(text: str, target: str) -> str:
    text = migrate_legacy_acf_markers(text)
    if has_upgrade_notes_marker(text):
        return text
    return text.rstrip() + upgrade_notes_block(target)


def section_exists(text: str, heading: str) -> bool:
    try:
        find_section(text.splitlines(), heading)
    except SystemExit:
        return False
    return True


def template_section_body(rel_path: str, heading: str) -> str | None:
    path = TEMPLATE_DIR / rel_path
    if not path.exists():
        return None
    try:
        section = find_section(read_text(path).splitlines(), heading)
    except SystemExit:
        return None
    return section_body(read_text(path).splitlines(), section)


def replace_section_from_template(text: str, rel_path: str, heading: str) -> str:
    if not section_exists(text, heading):
        return text
    body = template_section_body(rel_path, heading)
    if body is None:
        return text
    return replace_section_text(text, heading, body)


def add_context_curation_prompt_entry(text: str) -> str:
    if "reference/Context_Curation_Prompt.md" in text:
        return text
    if has_upgrade_notes_marker(text):
        return text
    row = "| 需要整理、归纳、精简上下文 | `reference/Context_Curation_Prompt.md` |"
    sentence = "需要整理、归纳、精简上下文时，按需读取 `reference/Context_Curation_Prompt.md`。"
    system_manual_row = "| 需要了解系统详细用法 | `reference/System_Manual.md` |"
    knowledge_row_arrow = "| 需要追溯可复用经验 | `reference/Knowledge_Index.md` → `reference/knowledge/*.md` |"
    knowledge_row_ascii = "| 需要追溯可复用经验 | `reference/Knowledge_Index.md` -> `reference/knowledge/*.md` |"
    if system_manual_row in text:
        return text.replace(system_manual_row, f"{row}\n{system_manual_row}")
    if knowledge_row_arrow in text:
        return text.replace(knowledge_row_arrow, f"{knowledge_row_arrow}\n{row}")
    if knowledge_row_ascii in text:
        return text.replace(knowledge_row_ascii, f"{knowledge_row_ascii}\n{row}")
    cli_boundary = "`acf` 只负责结构化落盘、检查和草案生成，不替代人或 AI 对事实和语义的判断。"
    if cli_boundary in text:
        return text.replace(cli_boundary, f"{cli_boundary}\n\n{sentence}")
    cli_heading = "## CLI 辅助维护\n\n"
    if cli_heading in text:
        return text.replace(cli_heading, f"{cli_heading}{sentence}\n\n")
    if "acf new" in text or "acf plan" in text:
        return text.rstrip() + "\n\n" + sentence + "\n"
    return text


def upgraded_agents_text(text: str, include_human: bool = False) -> str:
    text = migrate_legacy_acf_markers(text)
    original = text
    text = text.replace("## 会话结束回写要求", "## 会话结束回写建议")
    if "active/Task_Plan.md" not in text:
        replacements = (
            (
                "3. `active/Current_Task.md`（仅当任务状态为 Active 时）",
                "3. `active/Task_Plan.md`\n4. `active/Current_Task.md`（仅当任务状态为 Active 时）",
            ),
            (
                "3. `active/Current_Task.md`（仅当该文件存在且任务状态为 Active 时）",
                "3. `active/Task_Plan.md`\n4. `active/Current_Task.md`（仅当该文件存在且任务状态为 Active 时）",
            ),
        )
        for old, new in replacements:
            text = text.replace(old, new)
    if "active/Feedback_Inbox.md" not in text and "active/Context.md" in text:
        text = text.replace(
            "2. `rules/Always_Active.md`\n3. `active/Task_Plan.md`",
            "2. `rules/Always_Active.md`\n3. `active/Feedback_Inbox.md`（仅当存在 Open 条目或需要整理人工反馈时）\n4. `active/Task_Plan.md`",
        )
        text = text.replace(
            "4. `active/Current_Task.md`",
            "5. `active/Current_Task.md`",
        )

    text = text.replace(
        "新增或更新当前任务、资料索引、worklog、ADR、section 或 table 时",
        "新增或更新当前计划、当前任务、资料索引、Knowledge 草案、归档、worklog、ADR、section 或 table 时",
    )
    text = text.replace(
        "新增或更新当前计划、当前任务、资料索引、Knowledge 草案、归档、worklog、ADR、section 或 table 时",
        "新增或更新当前计划、规划依据、当前任务、资料索引、Knowledge 草案、归档、worklog、ADR、section 或 table 时",
    )
    text = text.replace(
        "`acf plan`、`acf task`",
        "`acf plan`（包括 `acf plan reference`）、`acf task`",
    )
    text = text.replace(
        "新增或更新当前任务、资料索引、worklog、ADR、section 或 table 时",
        "新增或更新当前计划、当前任务、资料索引、Knowledge 草案、归档、worklog、ADR、section 或 table 时",
    )
    if "不应默认重复打印完整回写建议清单" not in text and section_exists(text, "## 会话结束回写建议"):
        text = replace_section_from_template(text, "AGENTS.md", "## 会话结束回写建议")
    if "active/Feedback_Inbox.md" not in text and section_exists(text, "## 事实源优先级"):
        text = replace_section_from_template(text, "AGENTS.md", "## 事实源优先级")
    if "## 注意力治理与上下文预算" not in text and "## 会话结束回写建议" in text:
        body = template_section_body("AGENTS.md", "## 注意力治理与上下文预算")
        if body is not None:
            text = text.replace(
                "## 会话结束回写建议",
                f"## 注意力治理与上下文预算\n\n{body}\n\n---\n\n## 会话结束回写建议",
            )
    if "archive/feedback" not in text and section_exists(text, "## 目录结构"):
        text = replace_section_from_template(text, "AGENTS.md", "## 目录结构")
    if include_human and "human/Human_Notes.md" not in text and not has_upgrade_notes_marker(text):
        for heading in ("## 目录结构", "## 按需读取指引", "## 事实源优先级", "## 目标信息来源"):
            if section_exists(text, heading):
                text = replace_section_from_template(text, "AGENTS.md", heading)
    text = add_context_curation_prompt_entry(text)
    if "active/Task_Plan.md" not in text and not has_upgrade_notes_marker(text):
        text = append_upgrade_notes_if_needed(text, "agents")
    elif "acf plan" not in text and not has_upgrade_notes_marker(text):
        text = append_upgrade_notes_if_needed(text, "agents")
    return text


def upgraded_feedback_inbox_text(text: str) -> str:
    text = migrate_legacy_acf_markers(text)
    if "archive/feedback/" in text and "只在近期或当前计划仍需引用时保留" in text:
        return text
    if section_exists(text, "## 状态说明"):
        text = replace_section_from_template(text, "active/Feedback_Inbox.md", "## 状态说明")
    if section_exists(text, "## 使用规则"):
        text = replace_section_from_template(text, "active/Feedback_Inbox.md", "## 使用规则")
    return text


def upgraded_project_rules_text(text: str) -> str:
    text = migrate_legacy_acf_markers(text)
    if "旧版本上下文" in text and "`acf upgrade`" in text and "upgrade compatibility" in text:
        return text
    addition = "- 修改模板目录结构、默认上下文结构或 `acf upgrade` 补齐逻辑时，必须评估旧版本上下文能否通过 `acf upgrade` 良好升级；新增结构应同步到 upgrade 文件清单、打包清单、文档、init/upgrade 测试和 upgrade compatibility runner。"
    return text.rstrip() + "\n" + addition + "\n"


def upgraded_system_manual_text(text: str) -> str:
    text = migrate_legacy_acf_markers(text)
    text = text.replace(
        "每次重要协作结束后，AI 应输出标准化的回写建议（格式见 AGENTS.md）。\n\n最终是否写入，由用户决定。",
        "重要协作结束后，AI 不应默认重复打印完整回写建议清单。应先判断哪些内容可以确定落盘，优先使用 `acf plan`、`acf task`、`acf edit`、`acf new worklog`、`acf knowledge draft`、`acf archive` 或 `acf writeback draft` 写入对应文件或草案。\n\n最终回复只报告实际修改的文件、生成的草案、执行的检查和仍需人工判断的风险。没有变化的类别不需要输出“无需更新”。",
    )
    text = text.replace(
        "Feedback_Inbox、Task_Plan、archive 和 Knowledge",
        "Feedback_Inbox、Task_Plan、archive、archive/feedback 和 Knowledge",
    )
    text = text.replace(
        "`active/Task_Plan.md`、archive 和 Knowledge",
        "`active/Task_Plan.md`、archive、archive/feedback 和 Knowledge",
    )
    if "acf upgrade [target]" not in text:
        marker = "### 14.2 常用命令"
        if marker not in text:
            marker = "### 15.2 常用命令"
        if marker in text:
            text = text.replace(
                marker,
                marker
                + "\n\n"
                + "- `acf upgrade [target]`：非破坏式补齐当前版本需要的 Feedback_Inbox、Task_Plan、archive、archive/feedback、Knowledge 结构和 active -> reference 规划依据追溯入口。\n"
                + "- `acf plan init|add-task|set-task|focus|complete|status [target]` / `acf plan reference list|add|remove [target]`：维护当前大任务计划、子任务板和 `## 规划依据`，并在完成后标记计划 Done。\n"
                + "- `acf task start|done|block|clear [target]`：从任务板启动、完成、阻塞或清空当前小任务。\n"
                + "- `acf archive current-task|task-plan|list [target]`：归档旧当前任务或旧大任务计划，并维护归档索引。\n",
            )
    if "旧版本上下文升级" not in text and "CLI 辅助工具" in text:
        insertion = """\n\n### 旧版本上下文升级\n\n推荐流程：`acf status --json` -> `acf upgrade --dry-run --json` -> 审阅 changed_files -> `acf upgrade --check-after --json` -> `acf check --strict --json`。\n\n`upgrade` 只补齐缺失结构和 active -> reference 规划依据追溯入口，不移动旧内容、不自动归档任务、不覆盖 Active `active/Current_Task.md`。旧任务或旧计划需要归档时，升级后显式运行 `acf archive current-task` 或 `acf archive task-plan`；已处理反馈需要长期保存时整理到 `archive/feedback/`。\n"""
        text = text.rstrip() + insertion + "\n"
    if "PowerShell 中反引号是转义字符" not in text:
        text = text.rstrip() + "\n\nPowerShell 中反引号是转义字符。写入包含 Markdown 反引号或多行正文时，优先使用 `--input <file>`。\n"
    if "Feedback_Inbox 生命周期" not in text and section_exists(text, "## 1. active/ 使用规则"):
        body = template_section_body("reference/System_Manual.md", "### 1.2 Feedback_Inbox 生命周期")
        if body is None:
            body = template_section_body("reference/System_Manual.md", "### 1.1 Feedback_Inbox 生命周期")
        if body is not None:
            marker = "\n---\n\n## 2. rules/ 读取策略"
            insertion = f"\n### 1.2 Feedback_Inbox 生命周期\n\n{body}\n\n---\n\n## 2. rules/ 读取策略"
            text = text.replace(marker, insertion)
    if "注意力治理规则" not in text and section_exists(text, "## 13. 更新项目上下文的规则"):
        text = replace_section_from_template(text, "reference/System_Manual.md", "## 13. 更新项目上下文的规则")
    if "Context_Curation_Prompt.md" not in text and "## 4. reference/ 使用规则" in text:
        prompt_row = "| 需要整理、归纳、精简上下文 | `reference/Context_Curation_Prompt.md` |"
        knowledge_row = "| 需要追溯可复用经验 | `reference/Knowledge_Index.md` |"
        if knowledge_row in text:
            text = text.replace(knowledge_row, f"{knowledge_row}\n{prompt_row}")
        prompt_note = "`Context_Curation_Prompt.md` 是按需读取的 AI 整理提示词模板。它用于帮助 AI 归纳、精简、去重并提出上下文整理建议；默认产物是整理建议，不是文件修改。除非用户明确要求落盘，否则不要根据该 prompt 自动修改上下文文件。"
        if prompt_note not in text and "不要默认读取所有 reference 文件。" in text:
            text = text.replace(
                "不要默认读取所有 reference 文件。",
                "不要默认读取所有 reference 文件。\n\n" + prompt_note,
            )
    if "上下文整理提示词模板" not in text and "## 5. reference/ 文件含义" in text:
        system_manual_line = "- **System_Manual.md**：本文件，系统详细使用手册。"
        prompt_line = "- **Context_Curation_Prompt.md**：上下文整理提示词模板，仅在需要整理、归纳、精简上下文时按需读取；不进入默认读取路径。"
        if system_manual_line in text:
            text = text.replace(system_manual_line, f"{prompt_line}\n{system_manual_line}")
    if "旧版本上下文升级" not in text and "CLI 辅助工具" in text:
        insertion = """\n\n### 旧版本上下文升级\n\n推荐流程：`acf status --json` -> `acf upgrade --dry-run --json` -> 审阅 changed_files -> `acf upgrade --check-after --json` -> `acf check --strict --json`。\n\n`upgrade` 只补齐缺失结构和 active -> reference 规划依据追溯入口，不移动旧内容、不自动归档任务、不覆盖 Active `active/Current_Task.md`。旧任务或旧计划需要归档时，升级后显式运行 `acf archive current-task` 或 `acf archive task-plan`；已处理反馈需要长期保存时整理到 `archive/feedback/`。\n"""
        text = text.rstrip() + insertion + "\n"
    if "修改 `template/`、默认上下文结构、打包清单或 `acf upgrade` 行为" not in text and "旧版本上下文升级" in text:
        addition = "\n\n维护本框架时，如果修改 `template/`、默认上下文结构、打包清单或 `acf upgrade` 行为，必须同时评估旧版本上下文的升级路径。新增结构应同步到 init 文件清单、upgrade 补齐清单、`pyproject.toml` data-files、文档、init/upgrade 单元测试和 upgrade compatibility runner；入口或手册变更不能安全重排旧文档时，应通过 marker notes 非破坏式提示。\n"
        text = text.rstrip() + addition
    if "acf upgrade [target]" not in text and not has_upgrade_notes_marker(text):
        text = append_upgrade_notes_if_needed(text, "manual")
    if "PowerShell 中反引号是转义字符" not in text:
        text = text.rstrip() + "\n\nPowerShell 中反引号是转义字符。写入包含 Markdown 反引号或多行正文时，优先使用 `--input <file>`。\n"
    return text


def upgraded_task_plan_text(text: str) -> tuple[str, str | None]:
    if section_exists(text, PLAN_REFERENCE_HEADING):
        return text, None
    body = render_plan_reference_section((), upgrade_prompt=True)
    try:
        return insert_section_after(text, "## 成功标准", PLAN_REFERENCE_HEADING, body), None
    except SystemExit:
        pass
    try:
        return insert_section_before(text, "## 当前焦点", PLAN_REFERENCE_HEADING, body), None
    except SystemExit:
        return text, "active/Task_Plan.md: could not safely insert ## 规划依据; no known anchor matched"


def upgraded_current_task_text(text: str) -> tuple[str, str | None]:
    if not current_task_has_active_status(text):
        return text, None
    try:
        section = find_section(text.splitlines(), "## 输入材料")
    except SystemExit:
        return text, "active/Current_Task.md: could not append plan reference prompt because ## 输入材料 was not found"
    if CURRENT_TASK_REFERENCE_PROMPT in text:
        return text, None
    body_lines, suffix = section_content_and_suffix(text.splitlines(), section)
    stripped = [line.strip() for line in body_lines if line.strip()]
    if stripped == [PLAN_REFERENCE_EMPTY]:
        body_lines = [CURRENT_TASK_REFERENCE_PROMPT]
    else:
        insert_at = len(body_lines)
        while insert_at > 0 and not body_lines[insert_at - 1].strip():
            insert_at -= 1
        body_lines.insert(insert_at, CURRENT_TASK_REFERENCE_PROMPT)
    return apply_section_body(text.splitlines(), section, body_lines, suffix), None


def ensure_upgrade_structure(root: Path, dry_run: bool) -> tuple[list[Path], list[str]]:
    profile = infer_context_profile(root)
    planned = [
        root / "active" / "Feedback_Inbox.md",
        root / "active" / "Task_Plan.md",
        root / "active" / "Current_Task.md",
        root / "archive" / "Archive_Index.md",
        root / "reference" / "Knowledge_Index.md",
        root / "reference" / "Context_Curation_Prompt.md",
        root / "archive" / "tasks" / ".gitkeep",
        root / "archive" / "plans" / ".gitkeep",
        root / "archive" / "feedback" / ".gitkeep",
        root / "reference" / "knowledge" / ".gitkeep",
        root / "worklog" / "knowledge-drafts" / ".gitkeep",
    ]
    if profile == "standard":
        planned.extend(human_layer_paths(root))
    changed = [path for path in planned if not path.exists()]
    agents = root / "AGENTS.md"
    feedback = root / "active" / "Feedback_Inbox.md"
    task_plan = root / "active" / "Task_Plan.md"
    current_task = root / "active" / "Current_Task.md"
    project_rules = root / "rules" / "Project_Rules.md"
    manual = root / "reference" / "System_Manual.md"
    warnings: list[str] = []
    if task_plan.exists():
        original_plan = read_text(task_plan)
        updated_plan, warning = upgraded_task_plan_text(original_plan)
        if updated_plan != original_plan:
            changed.append(task_plan)
        if warning:
            warnings.append(f"{task_plan}: {warning}")
    if current_task.exists():
        original_task = read_text(current_task)
        updated_task, warning = upgraded_current_task_text(original_task)
        if updated_task != original_task:
            changed.append(current_task)
        if warning:
            warnings.append(f"{current_task}: {warning}")
    if agents.exists():
        original_agents = read_text(agents)
        updated_agents = upgraded_agents_text(original_agents, include_human=profile == "standard")
        if updated_agents != original_agents:
            changed.append(agents)
            if not has_upgrade_notes_marker(original_agents) and has_upgrade_notes_marker(updated_agents):
                warnings.append(f"{agents}: append upgrade notes because no known AGENTS.md pattern matched")
    if feedback.exists():
        original_feedback = read_text(feedback)
        updated_feedback = upgraded_feedback_inbox_text(original_feedback)
        if updated_feedback != original_feedback:
            changed.append(feedback)
    if project_rules.exists():
        original_rules = read_text(project_rules)
        updated_rules = upgraded_project_rules_text(original_rules)
        if updated_rules != original_rules:
            changed.append(project_rules)
    if manual.exists():
        original_manual = read_text(manual)
        updated_manual = upgraded_system_manual_text(original_manual)
        if updated_manual != original_manual:
            changed.append(manual)
            if not has_upgrade_notes_marker(original_manual) and has_upgrade_notes_marker(updated_manual):
                warnings.append(f"{manual}: append upgrade notes because no known System_Manual.md pattern matched")

    if dry_run:
        return changed, warnings

    for path in planned:
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.name == "Task_Plan.md":
            path.write_text(render_empty_task_plan(), encoding="utf-8")
        elif path.name == "Feedback_Inbox.md":
            template_feedback = TEMPLATE_DIR / "active" / "Feedback_Inbox.md"
            path.write_text(read_text(template_feedback) if template_feedback.exists() else render_feedback_inbox(), encoding="utf-8")
        elif path.name == "Archive_Index.md":
            path.write_text(render_archive_index(), encoding="utf-8")
        elif path.name == "Knowledge_Index.md":
            path.write_text(render_knowledge_index(), encoding="utf-8")
        elif path.name == "Context_Curation_Prompt.md":
            template_prompt = TEMPLATE_DIR / "reference" / "Context_Curation_Prompt.md"
            path.write_text(read_text(template_prompt) if template_prompt.exists() else "", encoding="utf-8")
        elif path.name == "Human_Notes.md":
            template_human = TEMPLATE_DIR / "human" / "Human_Notes.md"
            path.write_text(read_text(template_human) if template_human.exists() else render_human_notes(), encoding="utf-8")
        else:
            path.write_text("", encoding="utf-8")

    if agents.exists():
        text = read_text(agents)
        updated = upgraded_agents_text(text)
        if updated != text:
            agents.write_text(updated, encoding="utf-8")

    if feedback.exists():
        text = read_text(feedback)
        updated = upgraded_feedback_inbox_text(text)
        if updated != text:
            feedback.write_text(updated, encoding="utf-8")

    if task_plan.exists():
        text = read_text(task_plan)
        updated, _warning = upgraded_task_plan_text(text)
        if updated != text:
            task_plan.write_text(updated, encoding="utf-8")

    if current_task.exists():
        text = read_text(current_task)
        updated, _warning = upgraded_current_task_text(text)
        if updated != text:
            current_task.write_text(updated, encoding="utf-8")

    if project_rules.exists():
        text = read_text(project_rules)
        updated = upgraded_project_rules_text(text)
        if updated != text:
            project_rules.write_text(updated, encoding="utf-8")

    if manual.exists():
        text = read_text(manual)
        updated = upgraded_system_manual_text(text)
        if updated != text:
            manual.write_text(updated, encoding="utf-8")

    return changed, warnings


def upgrade_managed_paths(root: Path) -> list[Path]:
    paths = [
        root / "active" / "Feedback_Inbox.md",
        root / "active" / "Task_Plan.md",
        root / "archive" / "Archive_Index.md",
        root / "reference" / "Knowledge_Index.md",
        root / "reference" / "Context_Curation_Prompt.md",
        root / "archive" / "tasks" / ".gitkeep",
        root / "archive" / "plans" / ".gitkeep",
        root / "archive" / "feedback" / ".gitkeep",
        root / "reference" / "knowledge" / ".gitkeep",
        root / "worklog" / "knowledge-drafts" / ".gitkeep",
        root / "AGENTS.md",
        root / "rules" / "Project_Rules.md",
        root / "reference" / "System_Manual.md",
    ]
    if infer_context_profile(root) == "standard":
        paths.extend(human_layer_paths(root))
    return paths


def upgrade_detected_features(root: Path) -> list[str]:
    features: list[str] = []
    feature_paths = [
        ("context_agents", root / "AGENTS.md"),
        ("task_plan", root / "active" / "Task_Plan.md"),
        ("feedback_inbox", root / "active" / "Feedback_Inbox.md"),
        ("archive", root / "archive" / "Archive_Index.md"),
        ("feedback_archive", root / "archive" / "feedback"),
        ("knowledge", root / "reference" / "Knowledge_Index.md"),
        ("context_curation_prompt", root / "reference" / "Context_Curation_Prompt.md"),
        ("system_manual", root / "reference" / "System_Manual.md"),
        ("human", root / "human" / "Human_Notes.md"),
        ("workstreams", root / "active" / "Workstreams.md"),
    ]
    for name, path in feature_paths:
        if path.exists():
            features.append(name)
    return features


def upgrade_contract_payload(root: Path, changed_files: Sequence[Path]) -> dict[str, object]:
    changed_resolved = {path.resolve() for path in changed_files}
    planned_changes = [
        {"path": str(path.resolve()), "action": "create_or_update"}
        for path in changed_files
    ]
    skipped_changes = [
        {"path": str(path.resolve()), "reason": "already_current"}
        for path in upgrade_managed_paths(root)
        if path.resolve() not in changed_resolved and path.exists()
    ]
    return {
        "detected_features": upgrade_detected_features(root),
        "planned_changes": planned_changes,
        "skipped_changes": skipped_changes,
    }


def upgrade_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    changed_files, warnings = ensure_upgrade_structure(root, dry_run)
    check_result = maybe_check_after(args, root)
    action = "would upgrade" if dry_run else "upgraded"
    return emit_write_result(
        args,
        "upgrade",
        f"{action} context structure at {root}",
        changed_files,
        check_result,
        extra_payload=upgrade_contract_payload(root, changed_files),
        warnings=warnings,
    )


def task_plan_path(root: Path) -> Path:
    return root / "active" / "Task_Plan.md"


def plan_reference_payload(root: Path, plan_path: Path) -> dict[str, object]:
    references, warnings = read_plan_references(plan_path)
    payload: dict[str, object] = {
        "references": [{"path": reference.path, "purpose": reference.purpose} for reference in references],
        "count": len(references),
    }
    if warnings:
        payload["reference_warnings"] = warnings
    return payload


def ensure_plan_reference_target(root: Path, ref_path: str, allow_missing: bool) -> list[str]:
    target = root / ref_path
    if target.exists():
        return []
    if allow_missing:
        return [f"plan reference target does not exist: {ref_path}"]
    raise SystemExit(f"plan reference target does not exist: {ref_path}; use --allow-missing to add it anyway")


def replace_or_add_plan_reference(
    references: Sequence[PlanReference],
    reference: PlanReference,
    *,
    force: bool,
) -> tuple[list[PlanReference], bool]:
    updated: list[PlanReference] = []
    replaced = False
    for existing in references:
        if existing.path == reference.path:
            if not force:
                raise SystemExit(f"plan reference already exists: {reference.path}; use --force to update it")
            updated.append(reference)
            replaced = True
        else:
            updated.append(existing)
    if not replaced:
        updated.append(reference)
    return updated, replaced


def remove_plan_reference(
    references: Sequence[PlanReference],
    path: str,
    *,
    missing_ok: bool,
) -> tuple[list[PlanReference], PlanReference | None]:
    removed: PlanReference | None = None
    kept: list[PlanReference] = []
    for reference in references:
        if reference.path == path:
            removed = reference
        else:
            kept.append(reference)
    if removed is None and not missing_ok:
        raise SystemExit(f"plan reference was not found: {path}; use --missing-ok for an idempotent no-op")
    return kept, removed


def plan_reference_list_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    plan_path = task_plan_path(root)
    payload = {
        "command": "plan reference list",
        "ok": True,
        "context": str(root),
        **plan_reference_payload(root, plan_path),
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        references = [PlanReference(item["path"], item["purpose"]) for item in payload["references"]]  # type: ignore[index]
        if references:
            print("\n".join(render_plan_reference(reference) for reference in references))
        else:
            print("无。")
        for warning in payload.get("reference_warnings", []):
            print(f"WARN: {warning}", file=sys.stderr)
    return 0


def plan_reference_add_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    ref_path = normalize_plan_reference_path(args.ref_path)
    reference = PlanReference(ref_path, normalize_plan_reference_purpose(args.purpose))
    warnings = ensure_plan_reference_target(root, ref_path, args.allow_missing)
    references, parse_warnings = read_plan_references(plan_path)
    warnings.extend(parse_warnings)
    updated_references, _replaced = replace_or_add_plan_reference(references, reference, force=args.force)

    changed_files: list[Path] = []
    original_plan = read_text(plan_path)
    updated_plan = write_plan_references_text(original_plan, updated_references)
    if updated_plan != original_plan:
        changed_files.append(plan_path)

    current_task = current_task_path(root)
    updated_current_task: str | None = None
    if args.sync_current_task and current_task.exists():
        original_task = read_text(current_task)
        updated_task, sync_warnings = sync_current_task_reference_text(
            original_task,
            reference,
            operation="add",
            force=args.force,
        )
        warnings.extend(sync_warnings)
        if updated_task != original_task:
            updated_current_task = updated_task
            changed_files.append(current_task)

    if not dry_run:
        if updated_plan != original_plan:
            plan_path.write_text(updated_plan, encoding="utf-8")
        if updated_current_task is not None:
            current_task.write_text(updated_current_task, encoding="utf-8")

    check_result = maybe_check_after(args, root)
    action = "would add" if dry_run else "added"
    return emit_write_result(
        args,
        "plan reference add",
        f"{action} plan reference {ref_path}",
        changed_files,
        check_result,
        extra_payload=plan_reference_payload(root, plan_path) if not dry_run else {
            "references": [{"path": item.path, "purpose": item.purpose} for item in updated_references],
            "count": len(updated_references),
        },
        warnings=warnings,
    )


def plan_reference_remove_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    ref_path = normalize_plan_reference_path(args.ref_path)
    references, parse_warnings = read_plan_references(plan_path)
    warnings = list(parse_warnings)
    updated_references, removed = remove_plan_reference(references, ref_path, missing_ok=args.missing_ok)

    changed_files: list[Path] = []
    original_plan = read_text(plan_path)
    updated_plan = write_plan_references_text(original_plan, updated_references)
    if updated_plan != original_plan:
        changed_files.append(plan_path)

    current_task = current_task_path(root)
    updated_current_task: str | None = None
    if args.sync_current_task and removed is not None and current_task.exists():
        original_task = read_text(current_task)
        updated_task, sync_warnings = sync_current_task_reference_text(
            original_task,
            removed,
            operation="remove",
            force=False,
        )
        warnings.extend(sync_warnings)
        if updated_task != original_task:
            updated_current_task = updated_task
            changed_files.append(current_task)

    if not dry_run:
        if updated_plan != original_plan:
            plan_path.write_text(updated_plan, encoding="utf-8")
        if updated_current_task is not None:
            current_task.write_text(updated_current_task, encoding="utf-8")

    check_result = maybe_check_after(args, root)
    action = "would remove" if dry_run else "removed"
    return emit_write_result(
        args,
        "plan reference remove",
        f"{action} plan reference {ref_path}",
        changed_files,
        check_result,
        extra_payload=plan_reference_payload(root, plan_path) if not dry_run else {
            "references": [{"path": item.path, "purpose": item.purpose} for item in updated_references],
            "count": len(updated_references),
        },
        warnings=warnings,
    )


def read_task_rows(plan_path: Path) -> list[dict[str, str]]:
    if not plan_path.exists():
        raise SystemExit(f"task plan does not exist: {plan_path}")
    table = find_table(read_text(plan_path).splitlines(), TASK_TABLE_HEADER)
    rows: list[dict[str, str]] = []
    for line in read_text(plan_path).splitlines()[table.body_start : table.body_end]:
        cells = split_table_line(line)
        if len(cells) < len(table.headers) or cells[0] == "暂无":
            continue
        rows.append(dict(zip(table.headers, cells)))
    return rows


def read_task_stage_rows(plan_path: Path) -> list[dict[str, str]]:
    if not plan_path.exists():
        raise SystemExit(f"task plan does not exist: {plan_path}")
    lines = read_text(plan_path).splitlines()
    try:
        table = find_table(lines, TASK_STAGE_TABLE_HEADER)
    except SystemExit:
        return []
    rows: list[dict[str, str]] = []
    for line in lines[table.body_start : table.body_end]:
        cells = split_table_line(line)
        if len(cells) < len(table.headers) or cells[0] == "暂无":
            continue
        rows.append(dict(zip(table.headers, cells)))
    return rows


def task_stage_parent_id(stage_id: str) -> str:
    return stage_id.split(".", 1)[0]


def require_task_stage_belongs_to_parent(parent_task: str, stage_id: str) -> None:
    if task_stage_parent_id(stage_id) != parent_task:
        raise SystemExit(f"task_stage_scope_invalid: {stage_id} does not belong to parent task {parent_task}")


def find_task_stage_row(rows: Sequence[dict[str, str]], stage_id: str) -> dict[str, str] | None:
    return next((row for row in rows if row.get("ID") == stage_id), None)


def task_stage_payload(row: dict[str, str]) -> dict[str, str]:
    return {
        "id": row.get("ID", ""),
        "status": row.get("状态", ""),
        "parent": row.get("父任务", ""),
        "title": row.get("名称", ""),
        "workstream": row.get("归属 Workstream", ""),
        "depends_on": row.get("依赖", ""),
        "output": row.get("输出物", ""),
        "evidence": row.get("证据", ""),
        "next_action": row.get("下一步", ""),
    }


def render_task_stage_rows(rows: Sequence[dict[str, str]]) -> list[str]:
    if not rows:
        return [render_table_row(["暂无", "", "", "", "", "", "", "", ""])]
    return [
        render_table_row(
            [
                row.get("ID", ""),
                row.get("状态", ""),
                row.get("父任务", ""),
                row.get("名称", ""),
                row.get("归属 Workstream", ""),
                row.get("依赖", ""),
                row.get("输出物", ""),
                row.get("证据", ""),
                row.get("下一步", ""),
            ]
        )
        for row in rows
    ]


def write_task_stage_rows(plan_path: Path, rows: Sequence[dict[str, str]]) -> None:
    text = read_text(plan_path)
    lines = text.splitlines()
    try:
        table = find_table(lines, TASK_STAGE_TABLE_HEADER)
    except SystemExit:
        table_text = "\n".join(
            [
                TASK_STAGE_TABLE_HEADER,
                "|---|---|---|---|---|---|---|---|---|",
                *render_task_stage_rows(rows),
            ]
        )
        plan_path.write_text(text.rstrip() + f"\n\n---\n\n## 任务阶段\n\n{table_text}\n", encoding="utf-8")
        return
    updated = lines[: table.body_start] + render_task_stage_rows(rows) + lines[table.body_end :]
    plan_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def validate_task_stage_parent(rows: Sequence[dict[str, str]], parent_task: str, stage_id: str) -> None:
    require_task_stage_belongs_to_parent(parent_task, stage_id)
    if not any(row.get("ID") == parent_task for row in rows):
        raise SystemExit(f"task_stage_parent_not_found: {parent_task}")


def validate_task_stage_workstream(root: Path, value: str) -> None:
    if not meaningful_ref_value(value):
        return
    workstream_ids = WORKSTREAM_ID_TOKEN_RE.findall(value)
    if not workstream_ids:
        raise SystemExit(f"task_stage_workstream_not_found: {value}")
    statuses = workstream_statuses_for_task_checks(root)
    missing = [workstream_id for workstream_id in workstream_ids if workstream_id not in statuses]
    if missing:
        raise SystemExit(f"task_stage_workstream_not_found: {', '.join(missing)}")


def write_task_rows(plan_path: Path, rows: Sequence[dict[str, str]]) -> None:
    text = read_text(plan_path)
    lines = text.splitlines()
    table = find_table(lines, TASK_TABLE_HEADER)
    rendered_rows = [
        render_table_row([row.get(header, "") for header in table.headers])
        for row in rows
    ] or ["| 暂无 |  |  |  |  |  |  |"]
    updated = lines[: table.body_start] + rendered_rows + lines[table.body_end :]
    plan_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def next_task_id(rows: Sequence[dict[str, str]]) -> str:
    numbers = []
    for row in rows:
        match = TASK_ID_RE.match(row.get("ID", ""))
        if match:
            numbers.append(int(match.group(1)))
    return f"T{((max(numbers) + 1) if numbers else 1):03d}"


def find_task_row(rows: Sequence[dict[str, str]], task_id: str) -> dict[str, str]:
    for row in rows:
        if row.get("ID") == task_id:
            return row
    raise SystemExit(f"task id was not found in active/Task_Plan.md: {task_id}")


def set_plan_focus(plan_path: Path, task_id: str) -> None:
    plan_path.write_text(replace_section_text(read_text(plan_path), "## 当前焦点", task_id), encoding="utf-8")


def set_plan_status(plan_path: Path, status: str) -> None:
    plan_path.write_text(replace_section_text(read_text(plan_path), "## 大任务状态", status), encoding="utf-8")


def task_dependencies_satisfied(row: dict[str, str], rows: Sequence[dict[str, str]]) -> bool:
    depends = row.get("依赖", "").strip()
    if not depends or depends in {"无。", "无", "None", "-"}:
        return True
    done_ids = {candidate.get("ID") for candidate in rows if candidate.get("状态") in {"Done", "Superseded", "Skipped"}}
    dependency_ids = TASK_ID_TOKEN_RE.findall(depends)
    if not dependency_ids:
        return True
    return all(f"T{number}" in done_ids for number in dependency_ids)


def dependency_task_ids(value: str) -> list[str]:
    return [f"T{number}" for number in TASK_ID_TOKEN_RE.findall(value or "")]


def blocked_dependency_ids(row: dict[str, str], rows: Sequence[dict[str, str]]) -> list[str]:
    row_by_id = {candidate.get("ID", ""): candidate for candidate in rows}
    blocked: list[str] = []
    for task_id in dependency_task_ids(row.get("依赖", "")):
        dependency = row_by_id.get(task_id)
        if dependency is None or dependency.get("状态") not in {"Done", "Superseded", "Skipped"}:
            blocked.append(task_id)
    return blocked


def meaningful_task_cell(value: str | None, fallback: str) -> str:
    value = (value or "").strip()
    if not value or value in {"无。", "无", "None", "-"}:
        return fallback
    return value


def build_task_start_fields(
    plan_path: Path,
    row: dict[str, str],
    rows: Sequence[dict[str, str]],
    forced_with_blocked_dependencies: bool,
) -> dict[str, object]:
    task_id = row.get("ID", "无。")
    title = meaningful_task_cell(row.get("子任务"), task_id)
    plan_title = extract_heading_value(plan_path, "## 大任务名称") or "active/Task_Plan.md"
    output = meaningful_task_cell(row.get("输出物"), "完成该子任务要求的输出物。")
    next_action = meaningful_task_cell(row.get("下一步"), f"完成子任务 {task_id}。")
    dependency_ids = dependency_task_ids(row.get("依赖", ""))
    blocked = blocked_dependency_ids(row, rows)
    dependency_summary = meaningful_task_cell(row.get("依赖"), "无明确依赖。")

    inputs = ["`active/Task_Plan.md`。", "`active/Context.md`。"]
    inputs.extend(valid_plan_reference_input_lines(plan_path))
    row_by_id = {candidate.get("ID", ""): candidate for candidate in rows}
    for dependency_id in dependency_ids:
        dependency = row_by_id.get(dependency_id)
        if dependency is None:
            inputs.append(f"依赖 {dependency_id}：任务板中未找到该依赖。")
            continue
        evidence = meaningful_task_cell(dependency.get("证据"), "尚无证据。")
        inputs.append(f"依赖 {dependency_id} 证据：{evidence}")

    failures = [
        "依赖任务未完成或证据不足。",
        "输出物无法通过检查或人工复核验证。",
        "执行中发现用户当前需求与任务板记录冲突。",
    ]
    constraints = [
        "遵守当前项目规则和默认读取顺序。",
        "保持 `active/Task_Plan.md` 与 `active/Current_Task.md` 状态同步。",
        "不要把一次性过程或当前事实直接写入 Knowledge。",
    ]
    if forced_with_blocked_dependencies:
        constraints.append(f"`--force` 启动时仍存在未完成依赖：{', '.join(blocked)}。")

    return {
        "task_id": task_id,
        "generated_title": title,
        "blocked_dependencies": blocked,
        "warnings": [f"blocked dependencies: {', '.join(blocked)}"] if blocked else [],
        "content": render_current_task(
            "Active",
            title,
            plan_title,
            task_id,
            [next_action, f"产出并验证输出物：{output}"],
            f"该任务来自 `active/Task_Plan.md` 中的子任务 {task_id}，所属大任务为“{plan_title}”。依赖记录：{dependency_summary}",
            inputs,
            [output],
            [
                f"输出物已完成：{output}",
                f"子任务 {task_id} 的完成证据已写回任务板。",
                "`acf plan status` 能显示任务板可继续推进。",
            ],
            failures,
            constraints,
            ["无。"],
            ["执行过程中是否发现应回写 Context、ADR、rules、Knowledge 或 archive 的内容？"],
        ),
    }


def recommended_next_task(rows: Sequence[dict[str, str]]) -> dict[str, str] | None:
    active = next((row for row in rows if row.get("状态") == "Active"), None)
    if active is not None:
        return active
    return next(
        (
            row
            for row in rows
            if row.get("状态") == "Pending" and task_dependencies_satisfied(row, rows)
        ),
        None,
    )


def plan_init_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    if plan_path.exists() and extract_heading_value(plan_path, "## 大任务状态") == "Active" and not args.force:
        raise SystemExit(f"task plan is Active; use --force to replace it: {plan_path}")
    title = args.title.strip()
    if not title:
        raise SystemExit("plan title cannot be empty")
    goals = normalize_items(args.goal, ("完成当前大任务。",))
    success = normalize_items(args.success, ("大任务目标已完成并通过必要验证。",))
    if not dry_run:
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(render_task_plan("Active", title, goals, success, "无。", []), encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "plan init", f"{action} task plan {plan_path}", [plan_path], check_result)


def plan_add_task_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    rows = read_task_rows(plan_path)
    task_id = args.id or next_task_id(rows)
    if any(row.get("ID") == task_id for row in rows):
        raise SystemExit(f"task id already exists: {task_id}")
    title = args.title.strip()
    if not title:
        raise SystemExit("task title cannot be empty")
    rows.append(
        {
            "ID": task_id,
            "状态": "Pending",
            "子任务": title,
            "依赖": args.depends.strip() or "无。",
            "输出物": args.output.strip() or "无。",
            "证据": "无。",
            "下一步": args.next_action.strip() or "无。",
        }
    )
    if not dry_run:
        write_task_rows(plan_path, rows)
    check_result = maybe_check_after(args, root)
    action = "would add" if dry_run else "added"
    return emit_write_result(args, "plan add-task", f"{action} task {task_id} in {plan_path}", [plan_path], check_result)


def plan_set_task_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    rows = read_task_rows(plan_path)
    row = find_task_row(rows, args.id)
    if args.status:
        row["状态"] = args.status
    if args.title:
        row["子任务"] = args.title.strip()
    if args.depends is not None:
        row["依赖"] = args.depends.strip() or "无。"
    if args.output is not None:
        row["输出物"] = args.output.strip() or "无。"
    if args.evidence is not None:
        row["证据"] = args.evidence.strip() or "无。"
    if args.next_action is not None:
        row["下一步"] = args.next_action.strip() or "无。"
    if not dry_run:
        write_task_rows(plan_path, rows)
    check_result = maybe_check_after(args, root)
    action = "would update" if dry_run else "updated"
    return emit_write_result(args, "plan set-task", f"{action} task {args.id} in {plan_path}", [plan_path], check_result)


def plan_focus_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    rows = read_task_rows(plan_path)
    find_task_row(rows, args.id)
    if not dry_run:
        set_plan_focus(plan_path, args.id)
    check_result = maybe_check_after(args, root)
    action = "would focus" if dry_run else "focused"
    return emit_write_result(args, "plan focus", f"{action} task plan on {args.id}", [plan_path], check_result)


def plan_complete_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    rows = read_task_rows(plan_path)
    unfinished = [
        row.get("ID", "")
        for row in rows
        if row.get("状态") not in {"Done", "Skipped", "Superseded"}
    ]
    if unfinished and not args.force:
        raise SystemExit(f"task plan has unfinished subtasks; use --force to complete anyway: {', '.join(unfinished)}")
    if not dry_run:
        set_plan_status(plan_path, "Done")
        set_plan_focus(plan_path, "无。")
    check_result = maybe_check_after(args, root)
    action = "would complete" if dry_run else "completed"
    return emit_write_result(args, "plan complete", f"{action} task plan {plan_path}", [plan_path], check_result)


def plan_status_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    plan_path = task_plan_path(root)
    rows = read_task_rows(plan_path)
    payload: dict[str, object] = {
        "command": "plan status",
        "ok": True,
        "context": str(root),
        "plan_status": extract_heading_value(plan_path, "## 大任务状态"),
        "title": extract_heading_value(plan_path, "## 大任务名称"),
        "focus": extract_heading_value(plan_path, "## 当前焦点"),
        "tasks": rows,
        "next_task": recommended_next_task(rows),
        "error_code": None,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"plan: {payload['title']} ({payload['plan_status']})")
        print(f"focus: {payload['focus']}")
        for row in rows:
            print(f"{row.get('ID')}: {row.get('状态')} {row.get('子任务')}")
    return 0


def plan_stage_list_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    plan_path = task_plan_path(root)
    payload: dict[str, object] = {
        "command": "plan stage list",
        "ok": True,
        "context": str(root),
        "plan": str(plan_path),
        "stages": [task_stage_payload(row) for row in read_task_stage_rows(plan_path)],
        "error_code": None,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        stages = payload["stages"]
        if not stages:
            print("no task stages")
        for row in stages:
            if isinstance(row, dict):
                print(f"{row.get('id')}\t{row.get('status')}\t{row.get('parent')}\t{row.get('title')}")
    return 0


def plan_stage_add_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    task_rows = read_task_rows(plan_path)
    stage_rows = read_task_stage_rows(plan_path)
    stage_id = args.id
    parent_task = args.parent
    validate_task_stage_parent(task_rows, parent_task, stage_id)
    if find_task_stage_row(stage_rows, stage_id) is not None:
        raise SystemExit(f"task_stage_duplicate_id: {stage_id}")
    title = (args.title or "").strip()
    if not title:
        raise SystemExit("task_stage_scope_invalid: stage title cannot be empty")
    workstream = (args.workstream or "无。").strip() or "无。"
    validate_task_stage_workstream(root, workstream)
    row = {
        "ID": stage_id,
        "状态": "Pending",
        "父任务": parent_task,
        "名称": title,
        "归属 Workstream": workstream,
        "依赖": (args.depends or "无。").strip() or "无。",
        "输出物": (args.output or "待补充。").strip() or "待补充。",
        "证据": "无。",
        "下一步": (args.next_action or "待推进。").strip() or "待推进。",
    }
    if not dry_run:
        write_task_stage_rows(plan_path, [*stage_rows, row])
    check_result = maybe_check_after(args, root)
    action = "would add" if dry_run else "added"
    return emit_write_result(
        args,
        "plan stage add",
        f"{action} task stage {stage_id} in {plan_path}",
        [plan_path],
        check_result,
        extra_payload={"stage": task_stage_payload(row)},
    )


def plan_stage_set_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    task_rows = read_task_rows(plan_path)
    stage_rows = read_task_stage_rows(plan_path)
    row = find_task_stage_row(stage_rows, args.id)
    if row is None:
        raise SystemExit(f"task_stage_not_found: {args.id}")
    if args.parent is not None:
        parent_task = args.parent
        validate_task_stage_parent(task_rows, parent_task, args.id)
        row["父任务"] = parent_task
    else:
        validate_task_stage_parent(task_rows, row.get("父任务", ""), args.id)
    if args.status:
        row["状态"] = args.status
    if args.title is not None:
        title = args.title.strip()
        if not title:
            raise SystemExit("task_stage_scope_invalid: stage title cannot be empty")
        row["名称"] = title
    if args.workstream is not None:
        workstream = args.workstream.strip() or "无。"
        validate_task_stage_workstream(root, workstream)
        row["归属 Workstream"] = workstream
    if args.depends is not None:
        row["依赖"] = args.depends.strip() or "无。"
    if args.output is not None:
        row["输出物"] = args.output.strip() or "无。"
    if args.evidence is not None:
        row["证据"] = args.evidence.strip() or "无。"
    if args.next_action is not None:
        row["下一步"] = args.next_action.strip() or "无。"
    if not dry_run:
        write_task_stage_rows(plan_path, stage_rows)
    check_result = maybe_check_after(args, root)
    action = "would update" if dry_run else "updated"
    return emit_write_result(
        args,
        "plan stage set",
        f"{action} task stage {args.id} in {plan_path}",
        [plan_path],
        check_result,
        extra_payload={"stage": task_stage_payload(row)},
    )


def plan_stage_done_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    _task_rows = read_task_rows(plan_path)
    stage_rows = read_task_stage_rows(plan_path)
    row = find_task_stage_row(stage_rows, args.id)
    if row is None:
        raise SystemExit(f"task_stage_not_found: {args.id}")
    evidence = (args.evidence or "").strip()
    if not evidence:
        raise SystemExit(f"task_stage_missing_evidence: {args.id}")
    row["状态"] = "Done"
    row["证据"] = evidence
    if args.next_action is not None:
        row["下一步"] = args.next_action.strip() or "无。"
    else:
        row["下一步"] = "无。"
    if not dry_run:
        write_task_stage_rows(plan_path, stage_rows)
    check_result = maybe_check_after(args, root)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(
        args,
        "plan stage done",
        f"{action} task stage {args.id} Done in {plan_path}",
        [plan_path],
        check_result,
        extra_payload={"stage_id": args.id, "status": "Done", "evidence": evidence},
    )


def current_task_path(root: Path) -> Path:
    return root / "active" / "Current_Task.md"


def render_empty_current_task() -> str:
    return render_current_task(
        "Empty",
        "无。",
        "无。",
        "无。",
        ["无。"],
        "暂无当前任务。",
        ["无。"],
        ["无。"],
        ["无。"],
        ["无。"],
        ["遵守当前项目规则。"],
        ["无。"],
        ["无。"],
    )


def task_start_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    task_path = current_task_path(root)
    if task_path.exists() and extract_current_task_status(task_path) == "Active" and not args.force:
        raise SystemExit(f"current task is Active; use --force to replace it: {task_path}")
    rows = read_task_rows(plan_path)
    row = find_task_row(rows, args.id)
    blocked = blocked_dependency_ids(row, rows)
    if blocked and not args.force and not dry_run:
        raise SystemExit(f"task {args.id} has unfinished dependencies; use --force to start anyway: {', '.join(blocked)}")
    fields = build_task_start_fields(plan_path, row, rows, bool(blocked and args.force))
    for candidate in rows:
        if candidate.get("状态") == "Active" and candidate.get("ID") != args.id:
            candidate["状态"] = "Pending"
    row["状态"] = "Active"
    if not dry_run:
        write_task_rows(plan_path, rows)
        set_plan_focus(plan_path, args.id)
        set_plan_status(plan_path, "Active")
        task_path.write_text(str(fields["content"]), encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would start" if dry_run else "started"
    return emit_write_result(
        args,
        "task start",
        f"{action} task {args.id}",
        [plan_path, task_path],
        check_result,
        extra_payload={
            "task_id": fields["task_id"],
            "generated_title": fields["generated_title"],
            "blocked_dependencies": fields["blocked_dependencies"],
        },
        warnings=fields["warnings"] if isinstance(fields["warnings"], list) else [],
    )


def task_done_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    task_path = current_task_path(root)
    rows = read_task_rows(plan_path)
    row = find_task_row(rows, args.id)
    row["状态"] = "Done"
    row["证据"] = args.evidence.strip() or "已完成。"
    row["下一步"] = "无。"
    if not dry_run:
        write_task_rows(plan_path, rows)
        if task_path.exists():
            task_path.write_text(replace_section_text(read_text(task_path), "## 当前任务状态", "Done"), encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(args, "task done", f"{action} task {args.id} done", [plan_path, task_path], check_result)


def task_block_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    plan_path = task_plan_path(root)
    rows = read_task_rows(plan_path)
    row = find_task_row(rows, args.id)
    row["状态"] = "Blocked"
    row["下一步"] = args.reason.strip() or "等待阻塞解除。"
    if not dry_run:
        write_task_rows(plan_path, rows)
    check_result = maybe_check_after(args, root)
    action = "would block" if dry_run else "blocked"
    return emit_write_result(args, "task block", f"{action} task {args.id}", [plan_path], check_result)


def task_clear_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    task_path = current_task_path(root)
    if not dry_run:
        task_path.write_text(render_empty_current_task(), encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would clear" if dry_run else "cleared"
    return emit_write_result(args, "task clear", f"{action} current task {task_path}", [task_path], check_result)


def archive_index_path(root: Path) -> Path:
    return root / "archive" / "Archive_Index.md"


def find_archive_table(lines: Sequence[str]) -> tuple[TableRange, bool]:
    try:
        return find_table(lines, ARCHIVE_TABLE_HEADER), False
    except SystemExit:
        return find_table(lines, LEGACY_ARCHIVE_TABLE_HEADER), True


def normalize_archive_rows(lines: Sequence[str], table: TableRange, legacy: bool) -> list[str]:
    rows: list[str] = []
    for line in lines[table.body_start : table.body_end]:
        cells = split_table_line(line)
        if not cells or cells[0] == "暂无":
            continue
        if legacy:
            if len(cells) < 5:
                continue
            archive_date, item_type, title, reason, detail = cells[:5]
            rows.append(render_table_row([archive_date, item_type, title, "无。", detail, "Archived", reason]))
        elif len(cells) >= 7:
            rows.append(render_table_row(cells[:7]))
    return rows


def append_archive_index_entry(
    index_path: Path,
    archive_date: str,
    item_type: str,
    item_id: str,
    source_path: str,
    archive_path: str,
    status: str,
    reason: str,
) -> None:
    text = read_text(index_path) if index_path.exists() else render_archive_index()
    lines = text.splitlines()
    table, legacy = find_archive_table(lines)
    rows = normalize_archive_rows(lines, table, legacy)
    rows.append(render_table_row([archive_date, item_type, item_id, source_path, f"`{archive_path}`", status, reason]))
    updated = (
        lines[: table.header_index]
        + [ARCHIVE_TABLE_HEADER, "|---|---|---|---|---|---|---|"]
        + rows
        + lines[table.body_end :]
    )
    index_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def update_archive_index(index_path: Path, archive_date: str, item_type: str, title: str, reason: str, detail: str) -> None:
    append_archive_index_entry(index_path, archive_date, item_type, title, "无。", detail, "Archived", reason)


def archive_file(root: Path, source: Path, kind: str, reason: str, force: bool, dry_run: bool) -> list[Path]:
    if not source.exists():
        raise SystemExit(f"archive source does not exist: {source}")
    if kind == "Task" and extract_current_task_status(source) == "Active" and not force:
        raise SystemExit("current task is Active; use --force to archive it")
    if kind == "Plan" and extract_heading_value(source, "## 大任务状态") == "Active" and not force:
        raise SystemExit("task plan is Active; use --force to archive it")
    title_heading = "## 任务名称" if kind == "Task" else "## 大任务名称"
    title = extract_heading_value(source, title_heading) or source.stem
    archive_date = date.today().isoformat()
    dirname = "tasks" if kind == "Task" else "plans"
    destination = root / "archive" / dirname / f"{archive_date}-{slugify_file_stem(title)}.md"
    index_path = archive_index_path(root)
    changed = [destination, index_path, source]
    if dry_run:
        return changed
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(read_text(source), encoding="utf-8")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if not index_path.exists():
        index_path.write_text(render_archive_index(), encoding="utf-8")
    update_archive_index(
        index_path,
        archive_date,
        kind,
        title,
        reason.strip() or "归档旧内容。",
        destination.relative_to(root).as_posix(),
    )
    if kind == "Task":
        source.write_text(render_empty_current_task(), encoding="utf-8")
    else:
        source.write_text(render_empty_task_plan(), encoding="utf-8")
    return changed


def archive_current_task_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    changed = archive_file(root, current_task_path(root), "Task", args.reason, args.force, dry_run)
    check_result = maybe_check_after(args, root)
    action = "would archive" if dry_run else "archived"
    return emit_write_result(args, "archive current-task", f"{action} current task", changed, check_result)


def archive_task_plan_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    changed = archive_file(root, task_plan_path(root), "Plan", args.reason, args.force, dry_run)
    check_result = maybe_check_after(args, root)
    action = "would archive" if dry_run else "archived"
    return emit_write_result(args, "archive task-plan", f"{action} task plan", changed, check_result)


def archive_list_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    index_path = archive_index_path(root)
    rows: list[dict[str, str]] = []
    if index_path.exists():
        lines = read_text(index_path).splitlines()
        table, legacy = find_archive_table(lines)
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


def workstream_index_path(root: Path) -> Path:
    return root / WORKSTREAM_INDEX_REL


def workstream_details_dir(root: Path) -> Path:
    return root / WORKSTREAM_DIR_REL


def workstream_archive_dir(root: Path) -> Path:
    return root / WORKSTREAM_ARCHIVE_DIR_REL


def workstream_initialized(root: Path) -> bool:
    return workstream_index_path(root).is_file()


def workstream_front_matter_schema() -> FrontMatterSchema:
    return FrontMatterSchema(
        required_fields=("id", "status", "owner", "title", "read_scope", "write_scope"),
        allowed_fields=WORKSTREAM_METADATA_FIELDS,
        scalar_fields=(
            "id",
            "status",
            "owner",
            "title",
            "current_stage",
            "merge_resolution",
            "keep_active_reason",
            "keep_active_until",
        ),
        list_fields=("depends_on", "read_scope", "write_scope", "merge_targets"),
        enum_fields={"status": VALID_WORKSTREAM_STATUSES, "merge_resolution": VALID_MERGE_RESOLUTIONS},
        scope_fields=("read_scope",),
        typed_scope_fields=("write_scope",),
    )


def normalize_scope_path(path_value: str) -> str:
    normalized = path_value.strip().replace("\\", "/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/")


def normalize_authority_match_path(path_value: str) -> str:
    normalized = normalize_scope_path(path_value)
    if normalized.startswith("docs/ai/"):
        return normalized.removeprefix("docs/ai/")
    return normalized


def normalize_scope_values(values: str | list[str] | None) -> list[str]:
    if not isinstance(values, list):
        return []
    return [normalize_scope_path(value) for value in values]


def normalize_typed_scope_values(values: str | list[str] | None) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        scope_type, scope_path = split_typed_scope(value)
        if scope_type and scope_path:
            normalized.append(f"{scope_type}: {normalize_scope_path(scope_path)}")
        else:
            normalized.append(value)
    return normalized


def is_authority_path(path_value: str) -> bool:
    normalized = normalize_authority_match_path(path_value)
    if normalized in AUTHORITY_PATHS:
        return True
    for pattern in AUTHORITY_GLOBS:
        if "/" in pattern:
            prefix, suffix = pattern.split("*", 1)
            if not normalized.startswith(prefix) or not normalized.endswith(suffix):
                continue
            inner = normalized[len(prefix) :]
            if suffix:
                inner = inner[: -len(suffix)]
            if inner and "/" not in inner:
                return True
    return False


def diagnostic_payload(diagnostic: FrontMatterDiagnostic) -> dict[str, object]:
    return {
        "code": diagnostic.code,
        "message": diagnostic.message,
        "field": diagnostic.field,
        "line": diagnostic.line,
        "severity": diagnostic.severity,
    }


def render_workstream_index() -> str:
    return f"""本文件记录显式启用的并行 Workstream 索引。

Workstream 是可选并行目标线协议，不是 agent runtime、调度器或权限系统。

默认读取规则：只有存在 Active、Blocked 或 ReadyToMerge workstream，或当前任务需要整理并行协作时，才读取本文件。没有这些状态时，本文件不进入默认上下文。

---

## Workstream 状态

Inactive

说明：当前没有 Active、Blocked 或 ReadyToMerge workstream。

---

## Workstreams

{WORKSTREAM_TABLE_HEADER}
|---|---|---|---|---|---|---|---|
| 暂无 | Empty | 无。 | 无。 | 无。 | 无。 | 无。 | 无。 |

---

## 使用规则

1. 本索引只保留低噪音摘要。
2. 单个 Workstream 详情文件是该 Workstream 的事实源。
3. Done / Cancelled workstream 只在当前计划仍需解释时保留在 active 区域。
4. 当前计划结束后，Done / Cancelled workstream 应归档到 archive/workstreams。
"""


def parse_workstream_index(root: Path) -> list[WorkstreamEntry]:
    index_path = workstream_index_path(root)
    if not index_path.exists():
        raise SystemExit(f"workstream_not_initialized: {WORKSTREAM_INDEX_REL} does not exist")

    lines = read_text(index_path).splitlines()
    try:
        table = find_table(lines, WORKSTREAM_TABLE_HEADER)
    except SystemExit as exc:
        raise SystemExit(f"workstream_schema_failed: {WORKSTREAM_INDEX_REL}: {exc}") from exc

    entries: list[WorkstreamEntry] = []
    for line in lines[table.body_start : table.body_end]:
        cells = split_table_line(line)
        if not cells or cells[0] in {"ID", "暂无"}:
            continue
        if len(cells) < 8:
            raise SystemExit(f"workstream_schema_failed: {WORKSTREAM_INDEX_REL} has a malformed Workstream row")
        entries.append(
            WorkstreamEntry(
                workstream_id=cells[0],
                status=cells[1],
                title=cells[2],
                owner=cells[3],
                write_scope=cells[4],
                depends_on=cells[5],
                output=cells[6],
                detail=strip_code_ticks(cells[7]),
            )
        )
    return entries


def workstream_index_state(root: Path, entries: Sequence[WorkstreamEntry]) -> str:
    status = extract_heading_value(workstream_index_path(root), "## Workstream 状态")
    if status:
        return status
    if any(entry.status in ACTIVE_WORKSTREAM_STATUSES for entry in entries):
        return "Active"
    return "Inactive"


def workstream_counts(entries: Sequence[WorkstreamEntry]) -> dict[str, int]:
    counts = {status: 0 for status in sorted(VALID_WORKSTREAM_STATUSES)}
    for entry in entries:
        counts[entry.status] = counts.get(entry.status, 0) + 1
    return counts


def workstream_entry_payload(entry: WorkstreamEntry) -> dict[str, object]:
    return {
        "id": entry.workstream_id,
        "status": entry.status,
        "title": entry.title,
        "owner": entry.owner,
        "write_scope": entry.write_scope,
        "depends_on": entry.depends_on,
        "output": entry.output,
        "detail": entry.detail,
    }


def resolve_workstream_detail_path(root: Path, workstream_id: str, entries: Sequence[WorkstreamEntry]) -> Path:
    resolved: Path
    for entry in entries:
        if entry.workstream_id == workstream_id:
            detail = entry.detail.strip()
            if detail and detail != "无。":
                resolved = (root / detail).resolve()
                break
    else:
        resolved = (workstream_details_dir(root) / f"{workstream_id}.md").resolve()
    if not is_relative_to(resolved, root):
        raise SystemExit(f"workstream_schema_failed: detail path is outside context root for {workstream_id}")
    return resolved


def read_workstream_detail(root: Path, workstream_id: str) -> WorkstreamDetail:
    entries = parse_workstream_index(root)
    detail_path = resolve_workstream_detail_path(root, workstream_id, entries)
    if not detail_path.exists():
        raise SystemExit(f"workstream_not_found: {workstream_id}")

    metadata, body, diagnostics = parse_front_matter(read_text(detail_path))
    diagnostics.extend(validate_front_matter(metadata, workstream_front_matter_schema()))
    metadata_id = metadata.get("id")
    if isinstance(metadata_id, str) and metadata_id != workstream_id:
        diagnostics.append(
            FrontMatterDiagnostic(
                "front_matter_schema_failed",
                f"workstream id mismatch: expected {workstream_id}, got {metadata_id}",
                field="id",
            )
        )
    if diagnostics:
        raise SystemExit(
            "workstream_schema_failed: "
            + "; ".join(
                f"{diagnostic.field + ': ' if diagnostic.field else ''}{diagnostic.message}"
                for diagnostic in diagnostics
            )
        )
    return WorkstreamDetail(workstream_id, detail_path, metadata, body, diagnostics)


def workstream_detail_rel(workstream_id: str) -> str:
    return f"{WORKSTREAM_DIR_REL}/{workstream_id}.md"


def workstream_write_scope(workstream_id: str) -> str:
    return f"owned: {workstream_detail_rel(workstream_id)}"


def workstream_id_exists(root: Path, workstream_id: str, entries: Sequence[WorkstreamEntry]) -> bool:
    if any(entry.workstream_id == workstream_id for entry in entries):
        return True
    candidates = [
        workstream_details_dir(root) / f"{workstream_id}.md",
        workstream_archive_dir(root) / f"{workstream_id}.md",
    ]
    return any(candidate.exists() for candidate in candidates)


def render_workstream_detail(
    workstream_id: str,
    title: str,
    owner: str,
    depends_on: Sequence[str],
    read_scope: Sequence[str],
    write_scope: Sequence[str],
    output: str,
    goal: str = "待补充。",
) -> str:
    metadata: dict[str, str | list[str]] = {
        "id": workstream_id,
        "status": "Open",
        "owner": owner,
        "title": title,
        "depends_on": list(depends_on),
        "read_scope": list(read_scope),
        "write_scope": list(write_scope),
    }
    body = f"""# {workstream_id} - {title}

## 边界说明

本 Workstream 的读取范围是推荐上下文，不是权限隔离。所有 agent 仍必须遵守项目级 AGENTS、rules 和人工指令。允许修改范围是协作契约，用于避免并行写入冲突。

---

## 目标

{goal or "待补充。"}

---

## 当前发现

无。

---

## 阻塞原因

无。

---

## 取消原因

无。

---

## 合并请求

无。

---

## 证据

无。

---

## 完成记录

无。

---

## 输出物

{output or "待补充。"}
"""
    return format_front_matter(metadata, body, WORKSTREAM_METADATA_FIELDS)


def replace_or_append_section(text: str, heading: str, replacement: str) -> str:
    try:
        return replace_section_text(text, heading, replacement)
    except SystemExit:
        return text.rstrip() + f"\n\n---\n\n{heading}\n\n{replacement.strip()}\n"


def append_or_create_section(text: str, heading: str, addition: str) -> str:
    try:
        return append_section_text(text, heading, addition)
    except SystemExit:
        return text.rstrip() + f"\n\n---\n\n{heading}\n\n{addition.strip()}\n"


def update_workstream_index_state_text(text: str, entries: Sequence[WorkstreamEntry]) -> str:
    state = "Active" if any(entry.status in ACTIVE_WORKSTREAM_STATUSES for entry in entries) else "Inactive"
    explanation = (
        "说明：存在 Active、Blocked 或 ReadyToMerge workstream。"
        if state == "Active"
        else "说明：当前没有 Active、Blocked 或 ReadyToMerge workstream。"
    )
    return replace_or_append_section(text, "## Workstream 状态", f"{state}\n\n{explanation}")


def render_workstream_index_text(root: Path, entries: Sequence[WorkstreamEntry]) -> str:
    index_path = workstream_index_path(root)
    text = read_text(index_path) if index_path.exists() else render_workstream_index()
    lines = text.splitlines()
    table = find_table(lines, WORKSTREAM_TABLE_HEADER)
    rows = [render_table_row([
        entry.workstream_id,
        entry.status,
        entry.title,
        entry.owner,
        entry.write_scope,
        entry.depends_on,
        entry.output,
        entry.detail,
    ]) for entry in entries]
    if not rows:
        rows = [render_table_row(["暂无", "Empty", "无。", "无。", "无。", "无。", "无。", "无。"])]
    updated = "\n".join(lines[: table.body_start] + rows + lines[table.body_end :]).rstrip() + "\n"
    return update_workstream_index_state_text(updated, entries)


def write_workstream_index(root: Path, entries: Sequence[WorkstreamEntry]) -> None:
    workstream_index_path(root).write_text(render_workstream_index_text(root, entries), encoding="utf-8")


def replace_workstream_entry(entries: Sequence[WorkstreamEntry], updated_entry: WorkstreamEntry) -> list[WorkstreamEntry]:
    replaced = False
    updated: list[WorkstreamEntry] = []
    for entry in entries:
        if entry.workstream_id == updated_entry.workstream_id:
            updated.append(updated_entry)
            replaced = True
        else:
            updated.append(entry)
    if not replaced:
        updated.append(updated_entry)
    return updated


def workstream_entry_from_detail(detail: WorkstreamDetail, existing_entry: WorkstreamEntry | None = None) -> WorkstreamEntry:
    metadata = detail.metadata
    write_scope = ", ".join(normalize_typed_scope_values(metadata.get("write_scope")))
    depends_on = metadata.get("depends_on")
    return WorkstreamEntry(
        workstream_id=detail.workstream_id,
        status=workstream_detail_metadata_value(detail, "status", existing_entry.status if existing_entry else "Open"),
        title=workstream_detail_metadata_value(detail, "title", existing_entry.title if existing_entry else detail.workstream_id),
        owner=workstream_detail_metadata_value(detail, "owner", existing_entry.owner if existing_entry else "未分配"),
        write_scope=write_scope or (existing_entry.write_scope if existing_entry else workstream_write_scope(detail.workstream_id)),
        depends_on=",".join(depends_on) if isinstance(depends_on, list) and depends_on else (existing_entry.depends_on if existing_entry else "无。"),
        output=existing_entry.output if existing_entry else "待补充。",
        detail=existing_entry.detail if existing_entry else workstream_detail_rel(detail.workstream_id),
    )


def synced_workstream_entries(root: Path, entries: Sequence[WorkstreamEntry]) -> list[WorkstreamEntry]:
    details_dir = workstream_details_dir(root)
    if not details_dir.is_dir():
        raise SystemExit(f"workstream_not_initialized: active/workstreams/ directory is missing")

    entry_by_id = {entry.workstream_id: entry for entry in entries}
    synced_entries = list(entries)
    errors: list[str] = []
    for path in sorted(details_dir.glob("WS*.md")):
        if not WORKSTREAM_ID_RE.match(path.stem):
            continue
        detail = parse_workstream_detail_for_check(root, path.stem, path, errors)
        if detail is None:
            continue
        synced_entries = replace_workstream_entry(synced_entries, workstream_entry_from_detail(detail, entry_by_id.get(detail.workstream_id)))
    if errors:
        raise SystemExit("workstream_schema_failed: " + "; ".join(errors))
    return synced_entries


def workstream_detail_metadata_value(detail: WorkstreamDetail, field_name: str, fallback: str) -> str:
    value = detail.metadata.get(field_name)
    return value if isinstance(value, str) and value.strip() else fallback


def update_workstream_status(
    root: Path,
    workstream_id: str,
    status: str,
    section_updates: dict[str, str] | None,
    dry_run: bool,
    metadata_updates: dict[str, str | list[str]] | None = None,
) -> list[Path]:
    entries = parse_workstream_index(root)
    detail = read_workstream_detail(root, workstream_id)
    current_status = workstream_detail_metadata_value(detail, "status", "")
    allowed = WORKSTREAM_STATE_TRANSITIONS.get(current_status, set())
    if status == current_status:
        return []
    if status not in allowed:
        raise SystemExit(f"workstream_invalid_transition: {workstream_id} {current_status} -> {status}")

    metadata = dict(detail.metadata)
    metadata["status"] = status
    if metadata_updates:
        metadata.update(metadata_updates)
    body = detail.body
    for heading, replacement in (section_updates or {}).items():
        body = replace_or_append_section(body, heading, replacement)
    updated_text = format_front_matter(metadata, body, WORKSTREAM_METADATA_FIELDS)

    existing_entry = next((entry for entry in entries if entry.workstream_id == workstream_id), None)
    updated_entry = WorkstreamEntry(
        workstream_id=workstream_id,
        status=status,
        title=workstream_detail_metadata_value(detail, "title", existing_entry.title if existing_entry else workstream_id),
        owner=workstream_detail_metadata_value(detail, "owner", existing_entry.owner if existing_entry else "未分配"),
        write_scope=", ".join(normalize_typed_scope_values(metadata.get("write_scope"))) or (existing_entry.write_scope if existing_entry else workstream_write_scope(workstream_id)),
        depends_on=",".join(metadata.get("depends_on", [])) if isinstance(metadata.get("depends_on"), list) else (existing_entry.depends_on if existing_entry else "无。"),
        output=existing_entry.output if existing_entry else "待补充。",
        detail=existing_entry.detail if existing_entry else workstream_detail_rel(workstream_id),
    )
    changed = [detail.path, workstream_index_path(root)]
    if not dry_run:
        detail.path.write_text(updated_text, encoding="utf-8")
        write_workstream_index(root, replace_workstream_entry(entries, updated_entry))
    return changed


def update_workstream_detail_metadata(
    root: Path,
    detail: WorkstreamDetail,
    metadata: dict[str, str | list[str]],
    dry_run: bool,
    sync_index_write_scope: bool = False,
) -> list[Path]:
    changed = [detail.path]
    if sync_index_write_scope:
        changed.append(workstream_index_path(root))
    if not dry_run:
        detail.path.write_text(format_front_matter(metadata, detail.body, WORKSTREAM_METADATA_FIELDS), encoding="utf-8")
        if sync_index_write_scope:
            entries = parse_workstream_index(root)
            existing_entry = next((entry for entry in entries if entry.workstream_id == detail.workstream_id), None)
            updated_entry = WorkstreamEntry(
                workstream_id=detail.workstream_id,
                status=workstream_detail_metadata_value(detail, "status", existing_entry.status if existing_entry else "Open"),
                title=workstream_detail_metadata_value(detail, "title", existing_entry.title if existing_entry else detail.workstream_id),
                owner=workstream_detail_metadata_value(detail, "owner", existing_entry.owner if existing_entry else "未分配"),
                write_scope=", ".join(normalize_typed_scope_values(metadata.get("write_scope"))),
                depends_on=",".join(metadata.get("depends_on", [])) if isinstance(metadata.get("depends_on"), list) else (existing_entry.depends_on if existing_entry else "无。"),
                output=existing_entry.output if existing_entry else "待补充。",
                detail=existing_entry.detail if existing_entry else workstream_detail_rel(detail.workstream_id),
            )
            write_workstream_index(root, replace_workstream_entry(entries, updated_entry))
    return changed


def workstream_init_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    index_path = workstream_index_path(root)
    details_dir = workstream_details_dir(root)
    archive_dir = workstream_archive_dir(root)
    changed = [path for path in (index_path, details_dir, archive_dir) if not path.exists()]

    if not dry_run:
        details_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)
        if not index_path.exists():
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_text(render_workstream_index(), encoding="utf-8")

    check_result = maybe_check_after(args, root)
    action = "would initialize" if dry_run else "initialized"
    return emit_write_result(
        args,
        "workstream init",
        f"{action} Workstream layer",
        changed,
        check_result,
        extra_payload={
            "initialized": True,
            "index": str(index_path),
            "details_dir": str(details_dir),
            "archive_dir": str(archive_dir),
        },
    )


def workstream_status_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    initialized = workstream_initialized(root)
    entries = parse_workstream_index(root) if initialized else []
    payload: dict[str, object] = {
        "command": "workstream status",
        "context": str(root),
        "initialized": initialized,
        "index": str(workstream_index_path(root)),
        "details_dir": str(workstream_details_dir(root)),
        "archive_dir": str(workstream_archive_dir(root)),
        "state": workstream_index_state(root, entries) if initialized else "NotInitialized",
        "counts": workstream_counts(entries),
        "ok": True,
        "next_actions": [] if initialized else error_next_actions("workstream_not_initialized"),
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"workstream initialized: {initialized}")
        print(f"state: {payload['state']}")
        if not initialized:
            print("next action: acf workstream init")
    return 0


def workstream_list_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    entries = parse_workstream_index(root)
    payload: dict[str, object] = {
        "command": "workstream list",
        "context": str(root),
        "initialized": True,
        "state": workstream_index_state(root, entries),
        "counts": workstream_counts(entries),
        "workstreams": [workstream_entry_payload(entry) for entry in entries],
        "ok": True,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        for entry in entries:
            print(f"{entry.workstream_id}\t{entry.status}\t{entry.title}")
        if not entries:
            print("no workstreams")
    return 0


def parse_archive_candidates_today(value: str | None) -> date:
    if value is None:
        return date.today()
    normalized = value.strip()
    if not DATE_RE.match(normalized):
        raise SystemExit("workstream_archive_candidates_invalid_today: --today must use YYYY-MM-DD")
    return date.fromisoformat(normalized)


def parse_workstream_archive_date(value: str | None, option_name: str = "--date") -> date:
    if value is None:
        return date.today()
    normalized = value.strip()
    if not DATE_RE.match(normalized):
        raise SystemExit(f"workstream_archive_candidates_invalid_today: {option_name} must use YYYY-MM-DD")
    return date.fromisoformat(normalized)


def current_execution_workstream_ids(root: Path) -> set[str]:
    task_file = root / "active" / "Current_Task.md"
    if not task_file.exists():
        return set()
    current_line = extract_heading_value(task_file, "## 当前执行线")
    if not meaningful_ref_value(current_line):
        return set()
    return set(WORKSTREAM_ID_TOKEN_RE.findall(current_line or ""))


def active_task_stage_workstream_refs(root: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    plan_path = task_plan_path(root)
    if not plan_path.exists():
        return {}, {}
    try:
        rows = read_task_stage_rows(plan_path)
    except SystemExit as exc:
        raise SystemExit(f"workstream_archive_candidates_plan_unreadable: {exc}") from exc

    active_refs: dict[str, list[str]] = {}
    focus_refs: dict[str, list[str]] = {}
    focus = extract_heading_value(plan_path, "## 当前焦点") or ""
    for row in rows:
        stage_id = row.get("ID", "")
        owner_value = row.get("归属 Workstream", "")
        workstream_ids = WORKSTREAM_ID_TOKEN_RE.findall(owner_value)
        if not workstream_ids:
            continue
        if row.get("状态") not in {"Done", "Skipped", "Superseded"}:
            for workstream_id in workstream_ids:
                active_refs.setdefault(workstream_id, []).append(stage_id)
        if focus == stage_id:
            for workstream_id in workstream_ids:
                focus_refs.setdefault(workstream_id, []).append(stage_id)
    return active_refs, focus_refs


def workstream_archive_candidate_reason(detail: WorkstreamDetail, today: date) -> str:
    keep_until = detail.metadata.get("keep_active_until")
    if isinstance(keep_until, str) and DATE_RE.match(keep_until) and date.fromisoformat(keep_until) < today:
        return f"keep_active_until {keep_until} is expired."
    return "terminal Workstream is no longer blocked by keep-active metadata or current-plan references."


def workstream_archive_blockers(
    detail: WorkstreamDetail,
    today: date,
    current_execution_refs: set[str],
    active_stage_refs: dict[str, list[str]],
    focus_stage_refs: dict[str, list[str]],
) -> list[str]:
    blockers: list[str] = []
    workstream_id = detail.workstream_id
    status = detail.metadata.get("status")
    if workstream_id in current_execution_refs:
        blockers.append("referenced_by_current_task_execution_line")
    if workstream_id in active_stage_refs:
        blockers.append("referenced_by_current_task_stage")
    if workstream_id in focus_stage_refs:
        blockers.append("referenced_by_current_plan_focus")

    if status == "Done":
        merge_targets = detail.metadata.get("merge_targets")
        has_merge_targets = isinstance(merge_targets, list) and any(str(target).strip() for target in merge_targets)
        if workstream_section_missing(detail.body, "## 证据"):
            blockers.append("missing_evidence")
        if required_field_missing(detail.metadata.get("merge_resolution")):
            blockers.append("missing_merge_resolution")
        if has_merge_targets and not merge_request_has_required_fields(detail.body):
            blockers.append("missing_merge_request")
    elif status == "Cancelled" and workstream_section_missing(detail.body, "## 取消原因"):
        blockers.append("missing_cancellation_reason")

    keep_until = detail.metadata.get("keep_active_until")
    if isinstance(keep_until, str) and DATE_RE.match(keep_until):
        if date.fromisoformat(keep_until) >= today:
            blockers.append("keep_active_until_not_expired")
    elif not required_field_missing(keep_until):
        blockers.append("invalid_keep_active_until")

    return list(dict.fromkeys(blockers))


def workstream_archive_candidate_payload(root: Path, detail: WorkstreamDetail, today: date, blockers: Sequence[str]) -> dict[str, object]:
    keep_until = detail.metadata.get("keep_active_until")
    return {
        "id": detail.workstream_id,
        "status": detail.metadata.get("status", "Unknown"),
        "title": detail.metadata.get("title", "Unknown"),
        "detail": detail.path.as_posix(),
        "archive_target": (root / WORKSTREAM_ARCHIVE_DIR_REL / f"{detail.workstream_id}.md").as_posix(),
        "keep_active_until": keep_until if isinstance(keep_until, str) else None,
        "reason": workstream_archive_candidate_reason(detail, today),
        "blocked_by": list(blockers),
    }


def collect_workstream_archive_assessments(root: Path, today: date) -> list[WorkstreamArchiveAssessment]:
    entries = parse_workstream_index(root)
    current_execution_refs = current_execution_workstream_ids(root)
    active_stage_refs, focus_stage_refs = active_task_stage_workstream_refs(root)
    assessments: list[WorkstreamArchiveAssessment] = []
    for entry in entries:
        detail = read_workstream_detail(root, entry.workstream_id)
        status = detail.metadata.get("status")
        if status not in {"Done", "Cancelled"}:
            continue
        blockers = workstream_archive_blockers(detail, today, current_execution_refs, active_stage_refs, focus_stage_refs)
        assessments.append(
            WorkstreamArchiveAssessment(
                detail=detail,
                blockers=tuple(blockers),
                reason=workstream_archive_candidate_reason(detail, today),
            )
        )
    return assessments


def workstream_archive_assessment_payload(root: Path, assessment: WorkstreamArchiveAssessment, today: date) -> dict[str, object]:
    return workstream_archive_candidate_payload(root, assessment.detail, today, assessment.blockers)


def count_by_key(items: Sequence[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key)
        if isinstance(value, list):
            values = [str(candidate) for candidate in value if candidate]
        else:
            values = [str(value)] if value else []
        for candidate in values:
            counts[candidate] = counts.get(candidate, 0) + 1
    return counts


def workstream_archive_candidates_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    today = parse_archive_candidates_today(args.today)
    candidates: list[dict[str, object]] = []
    blocked: list[dict[str, object]] = []

    assessments = collect_workstream_archive_assessments(root, today)
    for assessment in assessments:
        payload = workstream_archive_assessment_payload(root, assessment, today)
        if assessment.blockers:
            blocked.append(payload)
        else:
            candidates.append(payload)

    next_actions: list[str] = []
    if candidates:
        next_actions.append("Review candidates and create an explicit archive draft or future archive command; this command does not move files.")
    if blocked:
        next_actions.append("Resolve blockers before archiving terminal Workstreams that remain active.")
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "workstream archive-candidates",
        "ok": True,
        "context": str(root),
        "today": today.isoformat(),
        "changed_files": [],
        "candidates": candidates,
        "blocked": blocked,
        "summary": {
            "terminal_total": len(assessments),
            "candidate_total": len(candidates),
            "blocked_total": len(blocked),
            "by_blocker": count_by_key(blocked, "blocked_by"),
        },
        "error_code": None,
        "next_actions": next_actions,
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        if not candidates:
            print("no archive candidates")
        for candidate in candidates:
            print(f"{candidate['id']}\t{candidate['status']}\t{candidate['reason']}")
        if blocked:
            print(f"blocked terminal workstreams: {len(blocked)}")
    return 0


def workstream_archive_draft_path(root: Path, draft_date: date, name: str | None) -> Path:
    suffix = f"-{slugify_file_stem(name)}" if name else ""
    return root / "worklog" / "archive-drafts" / f"{draft_date.isoformat()}{suffix}.md"


def workstream_archive_blocker_action(blocker: str) -> str:
    actions = {
        "keep_active_until_not_expired": "等待 keep_active_until 到期，或人工确认后更新 keep-active metadata。",
        "referenced_by_current_task_execution_line": "先完成、清空或切换 active/Current_Task.md 的当前执行线。",
        "referenced_by_current_plan_focus": "先移动 active/Task_Plan.md 当前焦点或完成相关阶段。",
        "referenced_by_current_task_stage": "先完成、跳过或重排引用该 Workstream 的当前 Task Stage。",
        "missing_merge_resolution": "先补充 Done Workstream 的 merge_resolution。",
        "missing_evidence": "先补充 Done Workstream 的证据。",
        "missing_merge_request": "先补充合并请求，或移除不再适用的 merge_targets。",
        "missing_cancellation_reason": "先补充 Cancelled Workstream 的取消原因。",
        "invalid_keep_active_until": "修正 keep_active_until 为 YYYY-MM-DD 或移除该字段。",
    }
    return actions.get(blocker, "人工复核该 blocker 后再决定是否归档。")


def render_workstream_archive_draft(
    root: Path,
    draft_path: Path,
    draft_date: date,
    candidates: Sequence[dict[str, object]],
    blocked: Sequence[dict[str, object]],
) -> str:
    rel_draft = draft_path.relative_to(root).as_posix()
    context_arg = relative_display_path(root, Path.cwd())
    lines = [
        f"# Workstream 归档草案：{draft_date.isoformat()}",
        "",
        "本文件是待人工或 AI 审阅的归档清单，不是归档结果。真正归档必须显式运行建议命令。",
        "",
        "## 摘要",
        "",
        f"- candidates: {len(candidates)}",
        f"- blocked: {len(blocked)}",
        "- source: acf workstream archive-candidates",
        "",
        "## 可归档候选",
        "",
    ]
    if not candidates:
        lines.append("- 无。")
    for item in candidates:
        workstream_id = str(item["id"])
        reason = f"reviewed in {rel_draft}"
        lines.extend(
            [
                f"### {workstream_id}",
                "",
                f"- status: {item.get('status')}",
                f"- detail: {relative_display_path(Path(str(item.get('detail'))), root)}",
                f"- archive_target: {relative_display_path(Path(str(item.get('archive_target'))), root)}",
                f"- reason: {item.get('reason')}",
                "- suggested_command:",
                "",
                "```bash",
                f"uv run acf workstream archive {workstream_id} {context_arg} --reason \"{reason}\" --json",
                "```",
                "",
            ]
        )

    lines.extend(["## 暂不归档", ""])
    if not blocked:
        lines.append("- 无。")
    for item in blocked:
        blockers = [str(blocker) for blocker in item.get("blocked_by", [])] if isinstance(item.get("blocked_by"), list) else []
        lines.extend(
            [
                f"### {item.get('id')}",
                "",
                f"- status: {item.get('status')}",
                f"- detail: {relative_display_path(Path(str(item.get('detail'))), root)}",
                f"- blocked_by: {', '.join(blockers) if blockers else '无。'}",
                f"- reason: {item.get('reason')}",
                "- suggested_action:",
            ]
        )
        for blocker in blockers:
            lines.append(f"  - {blocker}: {workstream_archive_blocker_action(blocker)}")
        lines.append("")

    lines.extend(
        [
            "## 审阅记录",
            "",
            "- approved:",
            "- rejected:",
            "- notes:",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def workstream_archive_draft_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    draft_date = parse_workstream_archive_date(args.date)
    dry_run = dry_run_enabled(args)
    draft_path = workstream_archive_draft_path(root, draft_date, args.name)
    assessments = collect_workstream_archive_assessments(root, draft_date)
    candidates: list[dict[str, object]] = []
    blocked: list[dict[str, object]] = []
    for assessment in assessments:
        payload = workstream_archive_assessment_payload(root, assessment, draft_date)
        if assessment.blockers:
            blocked.append(payload)
        else:
            candidates.append(payload)
    planned_draft = render_workstream_archive_draft(root, draft_path, draft_date, candidates, blocked)
    if draft_path.exists() and not args.force and not dry_run:
        raise SystemExit(f"workstream_archive_draft_exists: {draft_path.relative_to(root).as_posix()}")
    if not dry_run:
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(planned_draft, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would create" if dry_run else "created"
    return emit_write_result(
        args,
        "workstream archive-draft",
        f"{action} Workstream archive draft {draft_path.relative_to(root).as_posix()}",
        [draft_path],
        check_result,
        extra_payload={
            "draft_path": draft_path.relative_to(root).as_posix(),
            "candidate_count": len(candidates),
            "blocked_count": len(blocked),
            "planned_draft": planned_draft if dry_run else None,
        },
    )


def workstream_archive_marker(archive_date: date, source_rel: str, archive_rel: str, reason: str) -> str:
    return f"""{WORKSTREAM_ARCHIVE_MARKER_START}
## 归档记录

- archived_at: {archive_date.isoformat()}
- source_path: {source_rel}
- archive_path: `{archive_rel}`
- archive_reason: {reason}
{WORKSTREAM_ARCHIVE_MARKER_END}
"""


def active_workstream_index_matches(entries: Sequence[WorkstreamEntry], workstream_id: str) -> list[WorkstreamEntry]:
    return [entry for entry in entries if entry.workstream_id == workstream_id]


def workstream_archive_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    archive_date = parse_workstream_archive_date(args.date)
    dry_run = dry_run_enabled(args)
    reason = required_workstream_reason(args, "archive")
    entries = parse_workstream_index(root)
    matches = active_workstream_index_matches(entries, args.id)
    if len(matches) > 1:
        raise SystemExit(f"workstream_archive_duplicate_index: {args.id} appears multiple times in {WORKSTREAM_INDEX_REL}")
    warnings: list[str] = []
    if not matches:
        warnings.append(f"{WORKSTREAM_INDEX_REL} has no row for {args.id}; continuing with detail file")
    detail = read_workstream_detail(root, args.id)
    status = str(detail.metadata.get("status", ""))
    if status not in {"Done", "Cancelled"}:
        raise SystemExit(f"workstream_archive_blocked: {args.id} status is {status or 'Unknown'}")

    blockers = workstream_archive_blockers(
        detail,
        archive_date,
        current_execution_workstream_ids(root),
        *active_task_stage_workstream_refs(root),
    )
    if blockers:
        raise SystemExit(f"workstream_archive_blocked: {args.id} blocked_by={','.join(blockers)}")

    source_rel = detail.path.relative_to(root).as_posix()
    archive_rel = f"{WORKSTREAM_ARCHIVE_DIR_REL}/{args.id}.md"
    archive_path = root / archive_rel
    if archive_path.exists():
        raise SystemExit(f"workstream_archive_target_exists: {archive_rel}")
    source_text = read_text(detail.path)
    if has_workstream_archive_marker(source_text):
        raise SystemExit(f"workstream_archive_target_exists: {args.id} already contains archive marker")

    kept_entries = [entry for entry in entries if entry.workstream_id != args.id]
    changed: list[Path] = [archive_path, detail.path, archive_index_path(root)]
    if matches:
        changed.append(workstream_index_path(root))
    active_gitkeep = workstream_details_dir(root) / ".gitkeep"
    remaining_details = [path for path in workstream_details_dir(root).glob("*.md") if path.resolve() != detail.path.resolve()]
    if not remaining_details and not active_gitkeep.exists():
        changed.append(active_gitkeep)

    if not dry_run:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        updated_archive_text = source_text.rstrip() + "\n\n---\n\n" + workstream_archive_marker(archive_date, source_rel, archive_rel, reason)
        archive_path.write_text(updated_archive_text, encoding="utf-8")
        detail.path.unlink()
        if matches:
            write_workstream_index(root, kept_entries)
        if not remaining_details:
            active_gitkeep.parent.mkdir(parents=True, exist_ok=True)
            active_gitkeep.touch(exist_ok=True)
        index_path = archive_index_path(root)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        if not index_path.exists():
            index_path.write_text(render_archive_index(), encoding="utf-8")
        append_archive_index_entry(index_path, archive_date.isoformat(), "workstream", args.id, source_rel, archive_rel, status, reason)

    check_result = maybe_check_after(args, root)
    action = "would archive" if dry_run else "archived"
    return emit_write_result(
        args,
        "workstream archive",
        f"{action} Workstream {args.id}",
        changed,
        check_result,
        extra_payload={
            "archived_id": args.id,
            "source_path": source_rel,
            "archive_path": archive_rel,
            "status": status,
            "blocked_by": [],
        },
        warnings=warnings,
    )


def workstream_sync_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    index_path = workstream_index_path(root)
    current_text = read_text(index_path)
    entries = parse_workstream_index(root)
    planned_entries = synced_workstream_entries(root, entries)
    planned_text = render_workstream_index_text(root, planned_entries)
    changed = [index_path] if planned_text != current_text else []
    if changed and not dry_run:
        index_path.write_text(planned_text, encoding="utf-8")

    check_result = maybe_check_after(args, root)
    action = "would sync" if dry_run else "synced"
    extra_payload: dict[str, object] = {
        "synced": bool(changed),
        "workstreams": [workstream_entry_payload(entry) for entry in planned_entries],
    }
    if dry_run and changed:
        extra_payload["preview"] = {"path": WORKSTREAM_INDEX_REL, "content": planned_text}
    return emit_write_result(
        args,
        "workstream sync",
        f"{action} Workstream index",
        changed,
        check_result,
        extra_payload=extra_payload,
    )


def workstream_show_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    detail = read_workstream_detail(root, args.id)
    merge_request = safe_section_body_from_text(detail.body, "## 合并请求")
    evidence = safe_section_body_from_text(detail.body, "## 证据")
    payload: dict[str, object] = {
        "command": "workstream show",
        "context": str(root),
        "id": args.id,
        "detail": str(detail.path),
        "metadata": detail.metadata,
        "normalized_read_scope": normalize_scope_values(detail.metadata.get("read_scope")),
        "normalized_write_scope": normalize_typed_scope_values(detail.metadata.get("write_scope")),
        "merge_request": merge_request,
        "evidence": evidence,
        "diagnostics": [diagnostic_payload(diagnostic) for diagnostic in detail.diagnostics],
        "ok": True,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"id: {args.id}")
        print(f"detail: {detail.path}")
        print(f"status: {detail.metadata.get('status', 'Unknown')}")
        print(f"title: {detail.metadata.get('title', 'Unknown')}")
    return 0


def workstream_add_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    entries = parse_workstream_index(root)
    if workstream_id_exists(root, args.id, entries):
        raise SystemExit(f"workstream_duplicate_id: {args.id}")

    dry_run = dry_run_enabled(args)
    detail_path = workstream_details_dir(root) / f"{args.id}.md"
    read_scope = [normalized_read_claim(value) for value in (args.read_scope or ["active/Context.md", "active/Task_Plan.md"])]
    write_scope = [normalized_write_claim(value, args.id)[2] for value in (args.write_scope or [workstream_write_scope(args.id)])]
    depends_on = args.depends_on or []
    output = args.output.strip() if args.output else "待补充。"
    goal = args.goal.strip() if args.goal else "待补充。"
    entry = WorkstreamEntry(
        workstream_id=args.id,
        status="Open",
        title=args.title.strip(),
        owner=args.owner.strip(),
        write_scope=", ".join(write_scope),
        depends_on=",".join(depends_on) if depends_on else "无。",
        output=output,
        detail=workstream_detail_rel(args.id),
    )
    changed = [detail_path, workstream_index_path(root)]
    if not dry_run:
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        detail_path.write_text(
            render_workstream_detail(
                args.id,
                args.title.strip(),
                args.owner.strip(),
                depends_on,
                read_scope,
                write_scope,
                output,
                goal,
            ),
            encoding="utf-8",
        )
        write_workstream_index(root, [*entries, entry])

    check_result = maybe_check_after(args, root)
    action = "would add" if dry_run else "added"
    return emit_write_result(
        args,
        "workstream add",
        f"{action} Workstream {args.id}",
        changed,
        check_result,
        extra_payload={"id": args.id, "status": "Open", "detail": str(detail_path)},
    )


def workstream_set_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    goal = args.goal.strip() if args.goal is not None else None
    if args.status is None and goal is None:
        raise SystemExit("workstream_update_required: set requires --status or --goal")
    if goal == "":
        raise SystemExit("workstream_update_required: --goal cannot be empty")
    if args.status in {"ReadyToMerge", "Done"}:
        raise SystemExit(f"workstream_invalid_transition: use workstream {'ready' if args.status == 'ReadyToMerge' else 'done'} for {args.status}")
    if args.status is not None:
        section_updates = {"## 目标": goal} if goal is not None else None
        changed = update_workstream_status(root, args.id, args.status, section_updates, dry_run)
        status = args.status
    else:
        detail = read_workstream_detail(root, args.id)
        updated_text = format_front_matter(
            detail.metadata,
            replace_or_append_section(detail.body, "## 目标", goal or ""),
            WORKSTREAM_METADATA_FIELDS,
        )
        changed = [detail.path]
        if not dry_run:
            detail.path.write_text(updated_text, encoding="utf-8")
        status = workstream_detail_metadata_value(detail, "status", "Unknown")
    check_result = maybe_check_after(args, root)
    action = "would set" if dry_run else "set"
    message_target = f"to {status}" if args.status is not None else "goal"
    return emit_write_result(
        args,
        "workstream set",
        f"{action} Workstream {args.id} {message_target}",
        changed,
        check_result,
        extra_payload={"id": args.id, "status": status, "goal": goal},
    )


def required_workstream_reason(args: argparse.Namespace, command: str) -> str:
    reason = (args.reason or "").strip()
    if not reason:
        raise SystemExit(f"workstream_reason_required: {command} requires --reason")
    return reason


def workstream_block_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    reason = required_workstream_reason(args, "block")
    changed = update_workstream_status(root, args.id, "Blocked", {"## 阻塞原因": reason}, dry_run)
    check_result = maybe_check_after(args, root)
    action = "would block" if dry_run else "blocked"
    return emit_write_result(
        args,
        "workstream block",
        f"{action} Workstream {args.id}",
        changed,
        check_result,
        extra_payload={"id": args.id, "status": "Blocked", "reason": reason},
    )


def workstream_cancel_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    reason = required_workstream_reason(args, "cancel")
    changed = update_workstream_status(root, args.id, "Cancelled", {"## 取消原因": reason}, dry_run)
    check_result = maybe_check_after(args, root)
    action = "would cancel" if dry_run else "cancelled"
    return emit_write_result(
        args,
        "workstream cancel",
        f"{action} Workstream {args.id}",
        changed,
        check_result,
        extra_payload={"id": args.id, "status": "Cancelled", "reason": reason},
    )


def read_workstream_merge_summary(args: argparse.Namespace) -> str:
    summary = (args.summary or "").strip()
    input_path = getattr(args, "input", None)
    if summary and input_path is not None:
        raise SystemExit("use either --summary or --input, not both")
    if input_path is not None:
        resolved = input_path.resolve()
        if not resolved.is_file():
            raise SystemExit(f"merge-request input file does not exist: {resolved}")
        summary = resolved.read_text(encoding="utf-8").strip()
    if not summary:
        raise SystemExit("workstream_missing_merge_request: merge-request requires --summary or --input")
    return summary


def render_workstream_merge_request(
    targets: Sequence[str],
    summary: str,
    verification: str,
    questions: Sequence[str],
    conflicts: Sequence[str],
    strategy: str,
) -> str:
    target_lines = "\n".join(f"- {target}" for target in targets)
    question_lines = "\n".join(f"- {question}" for question in questions) if questions else "无。"
    conflict_lines = "\n".join(f"- {conflict}" for conflict in conflicts) if conflicts else "无。"
    return f"""### 需要合并到哪里

{target_lines}

### 候选变更摘要

{summary}

### 需要人工判断的问题

{question_lines}

### 已知冲突

{conflict_lines}

### 验证结果

{verification}

### 建议合并方式

{strategy or "人工审阅后合并到对应权威上下文。"}"""


def subsection_body(text: str, heading: str) -> str:
    lines = text.splitlines()
    heading_index = next((index for index, line in enumerate(lines) if line.strip() == heading), None)
    if heading_index is None:
        return ""
    body_start = heading_index + 1
    body_end = len(lines)
    for index in range(body_start, len(lines)):
        if heading_level(lines[index]) is not None and heading_level(lines[index]) <= 3:
            body_end = index
            break
    return "\n".join(lines[body_start:body_end]).strip()


def merge_request_has_required_fields(body: str) -> bool:
    merge_request = safe_section_body_from_text(body, "## 合并请求")
    if not merge_request or merge_request.strip() == "无。":
        return False
    targets = [
        line.strip()[2:].strip()
        for line in subsection_body(merge_request, "### 需要合并到哪里").splitlines()
        if line.strip().startswith("- ")
    ]
    summary = subsection_body(merge_request, "### 候选变更摘要").strip()
    return bool([target for target in targets if target]) and bool(summary and summary != "无。")


def workstream_merge_request_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    detail = read_workstream_detail(root, args.id)
    targets = [target.strip() for target in (args.target or []) if target.strip()]
    if not targets:
        raise SystemExit("workstream_missing_merge_request: merge-request requires at least one --target")
    verification = (args.verification or "").strip()
    if not verification:
        raise SystemExit("workstream_missing_merge_request: merge-request requires --verification")
    summary = read_workstream_merge_summary(args)
    section = render_workstream_merge_request(
        targets,
        summary,
        verification,
        args.question or [],
        args.conflict or [],
        (args.strategy or "").strip(),
    )
    metadata = dict(detail.metadata)
    merge_targets, _merge_targets_changed = append_unique_values(metadata.get("merge_targets"), targets)
    metadata["merge_targets"] = merge_targets
    updated_text = format_front_matter(
        metadata,
        replace_or_append_section(detail.body, "## 合并请求", section),
        WORKSTREAM_METADATA_FIELDS,
    )
    changed = [detail.path]
    if not dry_run:
        detail.path.write_text(updated_text, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would update" if dry_run else "updated"
    return emit_write_result(
        args,
        "workstream merge-request",
        f"{action} merge request for Workstream {args.id}",
        changed,
        check_result,
        extra_payload={"id": args.id, "targets": targets, "summary": summary},
    )


def workstream_ready_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    detail = read_workstream_detail(root, args.id)
    current_status = workstream_detail_metadata_value(detail, "status", "")
    if "ReadyToMerge" not in WORKSTREAM_STATE_TRANSITIONS.get(current_status, set()):
        raise SystemExit(f"workstream_invalid_transition: {args.id} {current_status} -> ReadyToMerge")
    if not merge_request_has_required_fields(detail.body):
        raise SystemExit(f"workstream_missing_merge_request: {args.id}")
    changed = update_workstream_status(root, args.id, "ReadyToMerge", None, dry_run)
    check_result = maybe_check_after(args, root)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(
        args,
        "workstream ready",
        f"{action} Workstream {args.id} ReadyToMerge",
        changed,
        check_result,
        extra_payload={"id": args.id, "status": "ReadyToMerge"},
    )


def required_workstream_evidence(args: argparse.Namespace) -> str:
    evidence = (args.evidence or "").strip()
    if not evidence:
        raise SystemExit("workstream_missing_evidence: done requires --evidence")
    return evidence


def required_workstream_merge_resolution(args: argparse.Namespace) -> str:
    resolution = (args.merge_resolution or "").strip()
    if not resolution:
        raise SystemExit("workstream_missing_merge_resolution: done requires --merge-resolution")
    return resolution


def workstream_done_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    detail = read_workstream_detail(root, args.id)
    current_status = workstream_detail_metadata_value(detail, "status", "")
    if "Done" not in WORKSTREAM_STATE_TRANSITIONS.get(current_status, set()):
        raise SystemExit(f"workstream_invalid_transition: {args.id} {current_status} -> Done")
    evidence = required_workstream_evidence(args)
    merge_resolution = required_workstream_merge_resolution(args)
    section_updates = {"## 证据": evidence}
    completion = (args.summary or "").strip()
    if completion:
        section_updates["## 完成记录"] = completion
    changed = update_workstream_status(
        root,
        args.id,
        "Done",
        section_updates,
        dry_run,
        {"merge_resolution": merge_resolution},
    )
    check_result = maybe_check_after(args, root)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(
        args,
        "workstream done",
        f"{action} Workstream {args.id} Done",
        changed,
        check_result,
        extra_payload={"id": args.id, "status": "Done", "evidence": evidence, "merge_resolution": merge_resolution},
    )


def canonical_workstream_note_heading(section: str) -> str:
    normalized = section.strip().removeprefix("##").strip()
    heading = WORKSTREAM_NOTE_SECTIONS.get(normalized)
    if heading is None:
        allowed = ", ".join(sorted(WORKSTREAM_NOTE_SECTIONS))
        raise SystemExit(f"workstream_section_not_allowed: {section}; allowed: {allowed}")
    return heading


def workstream_note_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    detail = read_workstream_detail(root, args.id)
    heading = canonical_workstream_note_heading(args.section)
    note_text = read_edit_input(args).strip()
    if not note_text:
        raise SystemExit("workstream_section_not_allowed: note text cannot be empty")
    updated_text = format_front_matter(
        detail.metadata,
        append_or_create_section(detail.body, heading, note_text),
        WORKSTREAM_METADATA_FIELDS,
    )
    changed = [detail.path]
    if not dry_run:
        detail.path.write_text(updated_text, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would append" if dry_run else "appended"
    return emit_write_result(
        args,
        "workstream note",
        f"{action} note to {heading} for Workstream {args.id}",
        changed,
        check_result,
        extra_payload={"id": args.id, "section": heading},
    )


def normalized_write_claim(value: str, workstream_id: str) -> tuple[str, str, str]:
    scope_type, scope_path = split_typed_scope(value)
    if not scope_type or not scope_path:
        raise SystemExit(f"workstream_scope_invalid: write scope must use TYPE: PATH: {value}")
    if scope_type not in {"authority", "draft", "owned", "assigned", "evidence"}:
        raise SystemExit(f"workstream_scope_invalid: unsupported write scope type: {scope_type}")
    normalized_path = normalize_scope_path(scope_path)
    diagnostics = validate_scope_path(normalized_path, "write_scope")
    if diagnostics:
        raise SystemExit(f"workstream_scope_invalid: {diagnostics[0].message}: {value}")
    if scope_type == "owned" and normalized_path != workstream_detail_rel(workstream_id):
        raise SystemExit(f"workstream_owned_scope_invalid: {value}")
    return scope_type, normalized_path, f"{scope_type}: {normalized_path}"


def normalized_read_claim(value: str) -> str:
    normalized = normalize_scope_path(value)
    diagnostics = validate_scope_path(normalized, "read_scope")
    if diagnostics:
        raise SystemExit(f"workstream_scope_invalid: {diagnostics[0].message}: {value}")
    return normalized


def scope_paths_conflict(left: str, right: str) -> bool:
    left = normalize_scope_path(left)
    right = normalize_scope_path(right)
    if left == right:
        return True
    if "*" in left or "*" in right:
        return False
    return left.startswith(right.rstrip("/") + "/") or right.startswith(left.rstrip("/") + "/")


def check_workstream_write_claim_conflicts(
    root: Path,
    workstream_id: str,
    claims: Sequence[tuple[str, str, str]],
) -> None:
    exclusive_claims = [(scope_type, scope_path) for scope_type, scope_path, _item in claims if scope_type in {"authority", "assigned"}]
    if not exclusive_claims:
        return
    entries = parse_workstream_index(root)
    for entry in entries:
        if entry.workstream_id == workstream_id or entry.status not in ACTIVE_WORKSTREAM_STATUSES:
            continue
        detail = read_workstream_detail(root, entry.workstream_id)
        existing_scopes = detail.metadata.get("write_scope")
        if not isinstance(existing_scopes, list):
            continue
        for existing in existing_scopes:
            existing_type, existing_path = split_typed_scope(existing)
            if existing_type not in {"authority", "assigned"} or not existing_path:
                continue
            existing_path = normalize_scope_path(existing_path)
            for _claim_type, claim_path in exclusive_claims:
                if scope_paths_conflict(claim_path, existing_path):
                    raise SystemExit(
                        f"workstream_claim_conflict: {workstream_id} conflicts with {entry.workstream_id} on {claim_path}"
                    )


def append_unique_values(existing: str | list[str] | None, additions: Sequence[str]) -> tuple[list[str], bool]:
    values = list(existing) if isinstance(existing, list) else []
    changed = False
    for addition in additions:
        if addition not in values:
            values.append(addition)
            changed = True
    return values, changed


def workstream_claim_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    read_claims = [normalized_read_claim(value) for value in (args.read or [])]
    write_claims = [normalized_write_claim(value, args.id) for value in (args.write or [])]
    if not read_claims and not write_claims:
        raise SystemExit("workstream_scope_invalid: claim requires --read or --write")
    check_workstream_write_claim_conflicts(root, args.id, write_claims)
    warnings: list[str] = []
    for scope_type, scope_path, _item in write_claims:
        if scope_type == "draft" and args.id not in Path(scope_path).name:
            warnings.append(f"draft write scope should include {args.id} in the file name: {scope_path}")

    detail = read_workstream_detail(root, args.id)
    metadata = dict(detail.metadata)
    read_scope, read_changed = append_unique_values(metadata.get("read_scope"), read_claims)
    write_scope, write_changed = append_unique_values(metadata.get("write_scope"), [item for _scope_type, _scope_path, item in write_claims])
    metadata["read_scope"] = read_scope
    metadata["write_scope"] = write_scope
    if not read_changed and not write_changed:
        changed = []
    else:
        changed = update_workstream_detail_metadata(root, detail, metadata, dry_run, sync_index_write_scope=write_changed)
    check_result = maybe_check_after(args, root)
    action = "would update" if dry_run else "updated"
    return emit_write_result(
        args,
        "workstream claim",
        f"{action} scope claims for Workstream {args.id}",
        changed,
        check_result,
        extra_payload={"id": args.id, "read_scope": read_scope, "write_scope": write_scope},
        warnings=warnings,
    )


def workstream_stage_add_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    workstream_id = args.id
    stage_id = args.stage_id
    require_workstream_stage_belongs_to(workstream_id, stage_id)
    detail = read_workstream_detail(root, workstream_id)
    rows = read_workstream_stage_rows(detail.body)
    if find_workstream_stage_row(rows, stage_id) is not None:
        raise SystemExit(f"workstream_stage_duplicate_id: {stage_id}")
    title = (args.title or "").strip()
    if not title:
        raise SystemExit("workstream_stage_scope_invalid: stage title cannot be empty")
    row = {
        "ID": stage_id,
        "状态": "Pending",
        "阶段": title,
        "依赖": (args.depends or "无。").strip() or "无。",
        "输出物": (args.output or "待补充。").strip() or "待补充。",
        "证据": "无。",
        "下一步": (args.next_action or "待推进。").strip() or "待推进。",
    }
    updated_text = format_front_matter(
        detail.metadata,
        replace_or_append_workstream_stage_rows(detail.body, [*rows, row]),
        WORKSTREAM_METADATA_FIELDS,
    )
    changed = [detail.path]
    if not dry_run:
        detail.path.write_text(updated_text, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would add" if dry_run else "added"
    return emit_write_result(
        args,
        "workstream stage add",
        f"{action} stage {stage_id} for Workstream {workstream_id}",
        changed,
        check_result,
        extra_payload={"id": workstream_id, "stage": workstream_stage_payload(row)},
    )


def workstream_stage_list_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    detail = read_workstream_detail(root, args.id)
    rows = read_workstream_stage_rows(detail.body)
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "workstream stage list",
        "ok": True,
        "context": str(root),
        "id": args.id,
        "detail": str(detail.path),
        "current_stage": detail.metadata.get("current_stage"),
        "stages": [workstream_stage_payload(row) for row in rows],
        "error_code": None,
        "next_actions": [],
    }
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        for row in rows:
            print(f"{row.get('ID')}\t{row.get('状态')}\t{row.get('阶段')}")
        if not rows:
            print("no workstream stages")
    return 0


def assert_workstream_stage_dependencies_done(workstream_id: str, rows: Sequence[dict[str, str]], row: dict[str, str]) -> None:
    rows_by_id = {candidate.get("ID", ""): candidate for candidate in rows}
    blocked: list[str] = []
    for dependency_id in workstream_stage_dependency_tokens(row.get("依赖", "")):
        if not workstream_stage_belongs_to(workstream_id, dependency_id):
            continue
        dependency = rows_by_id.get(dependency_id)
        if dependency is None or dependency.get("状态") != "Done":
            blocked.append(dependency_id)
    if blocked:
        raise SystemExit(f"workstream_stage_dependency_blocked: {row.get('ID')} depends on {', '.join(blocked)}")


def workstream_focus_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    workstream_id = args.id
    stage_id = args.stage_id
    require_workstream_stage_belongs_to(workstream_id, stage_id)
    detail = read_workstream_detail(root, workstream_id)
    rows = read_workstream_stage_rows(detail.body)
    row = find_workstream_stage_row(rows, stage_id)
    if row is None:
        raise SystemExit(f"workstream_stage_not_found: {stage_id}")
    current_status = row.get("状态", "")
    if terminal_workstream_stage_status(current_status):
        raise SystemExit(f"workstream_stage_terminal: {stage_id} has status {current_status}")
    active_stage_ids = [candidate.get("ID", "") for candidate in rows if candidate.get("状态") == "Active" and candidate.get("ID") != stage_id]
    if active_stage_ids:
        raise SystemExit(f"workstream_stage_active_conflict: {workstream_id} already has Active stage {active_stage_ids[0]}")
    assert_workstream_stage_dependencies_done(workstream_id, rows, row)

    updated_rows: list[dict[str, str]] = []
    for candidate in rows:
        updated = dict(candidate)
        if updated.get("ID") == stage_id:
            updated["状态"] = "Active"
        updated_rows.append(updated)
    metadata = dict(detail.metadata)
    metadata["current_stage"] = stage_id
    updated_text = format_front_matter(
        metadata,
        replace_or_append_workstream_stage_rows(detail.body, updated_rows),
        WORKSTREAM_METADATA_FIELDS,
    )
    changed = [detail.path]
    if not dry_run:
        detail.path.write_text(updated_text, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would focus" if dry_run else "focused"
    return emit_write_result(
        args,
        "workstream focus",
        f"{action} Workstream {workstream_id} on stage {stage_id}",
        changed,
        check_result,
        extra_payload={"id": workstream_id, "current_stage": stage_id},
    )


def workstream_stage_done_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    workstream_id = args.id
    stage_id = args.stage_id
    require_workstream_stage_belongs_to(workstream_id, stage_id)
    evidence = required_workstream_evidence(args)
    detail = read_workstream_detail(root, workstream_id)
    rows = read_workstream_stage_rows(detail.body)
    row = find_workstream_stage_row(rows, stage_id)
    if row is None:
        raise SystemExit(f"workstream_stage_not_found: {stage_id}")
    current_status = row.get("状态", "")
    if current_status in {"Cancelled", "Skipped"}:
        raise SystemExit(f"workstream_stage_terminal: {stage_id} has status {current_status}")
    metadata = dict(detail.metadata)
    is_current_stage = metadata.get("current_stage") == stage_id
    if is_current_stage and not args.clear_current:
        raise SystemExit(f"workstream_stage_clear_current_required: {stage_id} is current_stage")
    if is_current_stage and args.clear_current:
        metadata.pop("current_stage", None)

    updated_rows: list[dict[str, str]] = []
    for candidate in rows:
        updated = dict(candidate)
        if updated.get("ID") == stage_id:
            updated["状态"] = "Done"
            updated["证据"] = evidence
            if args.next_action is not None:
                updated["下一步"] = args.next_action.strip() or "无。"
        updated_rows.append(updated)
    updated_text = format_front_matter(
        metadata,
        replace_or_append_workstream_stage_rows(detail.body, updated_rows),
        WORKSTREAM_METADATA_FIELDS,
    )
    changed = [detail.path]
    if not dry_run:
        detail.path.write_text(updated_text, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(
        args,
        "workstream stage done",
        f"{action} stage {stage_id} Done for Workstream {workstream_id}",
        changed,
        check_result,
        extra_payload={"id": workstream_id, "stage_id": stage_id, "status": "Done", "evidence": evidence},
    )


def resolve_context_existing_path(root: Path, value: str) -> Path:
    candidate = Path(strip_code_ticks(value))
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not is_relative_to(resolved, root):
        raise SystemExit(f"path is outside context root: {value}")
    if not resolved.exists():
        raise SystemExit(f"path does not exist: {value}")
    return resolved


def render_knowledge_draft(title: str, sources: Sequence[str], tags: str, summary: str) -> str:
    source_lines = "\n".join(f"- `{source}`" for source in sources)
    return f"""# K-草案：{title}

## 状态

Draft

## 标签

{tags or "未分类"}

## 摘要

{summary or "待补充。"}

## 结论

待提炼为一句可复用经验，不写当前事实。

## 适用场景

- 待补充。

## 不适用场景

- 待补充。

## 来源

{source_lines}

## 与现有事实源的关系

- 当前事实看：`active/Context.md`
- 相关任务看：`active/Task_Plan.md`

## 去重判断

待确认不是重复的 Context / ADR / rules / worklog。
"""


def knowledge_draft_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    title = args.title.strip()
    if not title:
        raise SystemExit("knowledge title cannot be empty")
    sources = [source.strip() for source in args.source if source.strip()]
    if not sources:
        raise SystemExit("knowledge draft requires at least one --source")
    for source in sources:
        resolve_context_existing_path(root, source)
    draft_dir = root / "worklog" / "knowledge-drafts"
    draft_path = draft_dir / f"{date.today().isoformat()}-{slugify_file_stem(title)}.md"
    if draft_path.exists() and not args.force:
        raise SystemExit(f"knowledge draft already exists: {draft_path}")
    if not dry_run:
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(render_knowledge_draft(title, sources, args.tag, args.summary), encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "knowledge draft", f"{action} knowledge draft {draft_path}", [draft_path], check_result)


def knowledge_index_path(root: Path) -> Path:
    return root / "reference" / "Knowledge_Index.md"


def existing_knowledge_numbers(root: Path) -> list[int]:
    numbers: list[int] = []
    index_path = knowledge_index_path(root)
    if index_path.exists():
        for cells in parse_markdown_table_rows(read_text(index_path)):
            if cells and (match := KNOWLEDGE_ID_RE.match(cells[0])):
                numbers.append(int(match.group(1)))
    knowledge_dir = root / "reference" / "knowledge"
    if knowledge_dir.exists():
        for path in knowledge_dir.glob("K*.md"):
            if match := re.match(r"K(\d{3})-", path.name):
                numbers.append(int(match.group(1)))
    return sorted(numbers)


def next_knowledge_id(root: Path) -> str:
    numbers = existing_knowledge_numbers(root)
    return f"K{((numbers[-1] + 1) if numbers else 1):03d}"


def update_knowledge_index(root: Path, knowledge_id: str, title: str, status: str, tags: str, summary: str, detail: str) -> None:
    index_path = knowledge_index_path(root)
    if not index_path.exists():
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(render_knowledge_index(), encoding="utf-8")
    lines = read_text(index_path).splitlines()
    table = find_table(lines, KNOWLEDGE_TABLE_HEADER)
    rows = [row for row in lines[table.body_start : table.body_end] if split_table_line(row)[0] not in {"暂无", knowledge_id}]
    rows.append(render_table_row([knowledge_id, title, status, tags or "未分类", summary or "无。", f"`{detail}`"]))
    updated = lines[: table.body_start] + rows + lines[table.body_end :]
    index_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def resolve_knowledge_draft(root: Path, draft: Path) -> Path:
    candidates = []
    if draft.is_absolute():
        candidates.append(draft.resolve())
    else:
        candidates.append((Path.cwd() / draft).resolve())
        candidates.append((root / draft).resolve())
    for candidate in candidates:
        if candidate.exists():
            if not is_relative_to(candidate, root):
                raise SystemExit(f"knowledge draft is outside context root: {draft}")
            return candidate
    raise SystemExit(f"knowledge draft does not exist: {draft}")


def safe_section_body_from_text(text: str, heading: str) -> str:
    try:
        lines = text.splitlines()
        return section_body(lines, find_section(lines, heading))
    except SystemExit:
        return ""


def knowledge_title_from_text(text: str, fallback: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first_line.startswith("# K-草案："):
        return first_line.replace("# K-草案：", "", 1).strip() or fallback
    if first_line.startswith("# "):
        title = re.sub(r"^#\s*K\d{3}[：:]\s*", "", first_line).strip()
        return title or fallback
    return fallback


def knowledge_tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).lower()
    normalized = re.sub(r"`[^`]*`", " ", normalized)
    raw_tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", normalized)
    tokens: set[str] = set()
    for token in raw_tokens:
        if token in KNOWLEDGE_STOPWORDS:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) > 2:
            tokens.update(token[index : index + 2] for index in range(len(token) - 1))
        else:
            tokens.add(token)
    return {token for token in tokens if token and token not in KNOWLEDGE_STOPWORDS}


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def knowledge_entry_from_file(path: Path, knowledge_id: str, title: str, status: str, summary: str) -> KnowledgeEntry:
    text = read_text(path)
    file_title = knowledge_title_from_text(text, title)
    return KnowledgeEntry(
        knowledge_id=knowledge_id,
        title=title or file_title,
        status=extract_heading_value(path, "## 状态") or status,
        summary=summary or safe_section_body_from_text(text, "## 摘要"),
        conclusion=safe_section_body_from_text(text, "## 结论"),
        path=path,
    )


def collect_knowledge_entries(root: Path) -> list[KnowledgeEntry]:
    entries: list[KnowledgeEntry] = []
    seen_paths: set[Path] = set()
    index_path = knowledge_index_path(root)
    if index_path.exists():
        for cells in parse_markdown_table_rows(read_text(index_path)):
            if len(cells) < 6 or cells[0] in {"ID", "暂无"}:
                continue
            knowledge_id, title, status, _tags, summary, detail = cells[:6]
            if status not in {"Active", "Draft"}:
                continue
            ref = strip_code_ticks(detail)
            if not ref:
                continue
            resolved = resolve_ref(root, index_path, ref) if should_check_ref(ref) else None
            if resolved is not None:
                seen_paths.add(resolved.resolve())
                entries.append(knowledge_entry_from_file(resolved, knowledge_id, title, status, summary))

    knowledge_dir = root / "reference" / "knowledge"
    if knowledge_dir.exists():
        for path in sorted(knowledge_dir.glob("K*.md")):
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            match = re.match(r"(K\d{3})-", path.name)
            knowledge_id = match.group(1) if match else path.stem
            status = extract_heading_value(path, "## 状态") or "Draft"
            if status not in {"Active", "Draft"}:
                continue
            text = read_text(path)
            entries.append(
                KnowledgeEntry(
                    knowledge_id=knowledge_id,
                    title=knowledge_title_from_text(text, path.stem),
                    status=status,
                    summary=safe_section_body_from_text(text, "## 摘要"),
                    conclusion=safe_section_body_from_text(text, "## 结论"),
                    path=path,
                )
            )
    return entries


def similar_knowledge_entries(
    candidate: KnowledgeEntry,
    entries: Sequence[KnowledgeEntry],
    exclude_ids: set[str] | None = None,
) -> list[dict[str, object]]:
    excluded = exclude_ids or set()
    candidate_title_tokens = knowledge_tokens(candidate.title)
    candidate_body_tokens = knowledge_tokens(f"{candidate.summary}\n{candidate.conclusion}")
    similar: list[dict[str, object]] = []
    for entry in entries:
        if entry.knowledge_id in excluded:
            continue
        title_score = jaccard_similarity(candidate_title_tokens, knowledge_tokens(entry.title))
        body_score = jaccard_similarity(candidate_body_tokens, knowledge_tokens(f"{entry.summary}\n{entry.conclusion}"))
        if title_score >= KNOWLEDGE_TITLE_SIMILARITY_THRESHOLD or body_score >= KNOWLEDGE_BODY_SIMILARITY_THRESHOLD:
            similar.append(
                {
                    "id": entry.knowledge_id,
                    "title": entry.title,
                    "status": entry.status,
                    "detail": entry.path.as_posix() if entry.path else "",
                    "title_similarity": round(title_score, 3),
                    "body_similarity": round(body_score, 3),
                }
            )
    return similar


def knowledge_similarity_messages(root: Path) -> list[str]:
    entries = collect_knowledge_entries(root)
    messages: list[str] = []
    for index, entry in enumerate(entries):
        for similar in similar_knowledge_entries(entry, entries[index + 1 :]):
            messages.append(
                "reference/Knowledge_Index.md: similar Knowledge entries "
                f"`{entry.knowledge_id}` and `{similar['id']}` "
                f"(title={similar['title_similarity']}, body={similar['body_similarity']})"
            )
    return messages


def knowledge_apply_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    draft_path = resolve_knowledge_draft(root, args.draft)
    text = read_text(draft_path)
    title = knowledge_title_from_text(text, draft_path.stem)
    status = extract_heading_value(draft_path, "## 状态") or "Draft"
    if status not in VALID_KNOWLEDGE_STATUSES:
        raise SystemExit(f"invalid knowledge status: {status}")
    tags = extract_heading_value(draft_path, "## 标签") or "未分类"
    summary = extract_heading_value(draft_path, "## 摘要") or "无。"
    candidate = KnowledgeEntry(
        knowledge_id="KNEW",
        title=title,
        status=status,
        summary=summary,
        conclusion=safe_section_body_from_text(text, "## 结论"),
        path=draft_path,
    )
    similar = similar_knowledge_entries(candidate, collect_knowledge_entries(root))
    if similar and not args.allow_similar and not dry_run:
        ids = ", ".join(str(item["id"]) for item in similar)
        raise SystemExit(f"similar knowledge already exists; use --allow-similar to apply anyway: {ids}")
    knowledge_id = next_knowledge_id(root)
    destination = root / "reference" / "knowledge" / f"{knowledge_id}-{slugify_file_stem(title)}.md"
    if destination.exists():
        raise SystemExit(f"knowledge file already exists: {destination}")
    changed = [destination, knowledge_index_path(root)]
    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text.replace("# K-草案：", f"# {knowledge_id}：", 1), encoding="utf-8")
        update_knowledge_index(root, knowledge_id, title, status, tags, summary, destination.relative_to(root).as_posix())
    check_result = maybe_check_after(args, root)
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


def knowledge_list_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    rows: list[dict[str, str]] = []
    index_path = knowledge_index_path(root)
    if index_path.exists():
        table = find_table(read_text(index_path).splitlines(), KNOWLEDGE_TABLE_HEADER)
        for line in read_text(index_path).splitlines()[table.body_start : table.body_end]:
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


def knowledge_detail_path(root: Path, knowledge_id: str) -> Path:
    index_path = knowledge_index_path(root)
    if index_path.exists():
        for cells in parse_markdown_table_rows(read_text(index_path)):
            if len(cells) >= 6 and cells[0] == knowledge_id:
                return resolve_context_existing_path(root, cells[5])
    raise SystemExit(f"knowledge id was not found: {knowledge_id}")


def knowledge_show_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    detail = knowledge_detail_path(root, args.id)
    text = read_text(detail)
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


def knowledge_mark_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    detail = knowledge_detail_path(root, args.id)
    text = replace_section_text(read_text(detail), "## 状态", args.status)
    if args.status == "Promoted" and not args.promoted_to.strip():
        raise SystemExit("--promoted-to is required when status is Promoted")
    if args.promoted_to.strip():
        addition = f"\n\nPromoted to: `{args.promoted_to.strip()}`"
        text = append_section_text(text, "## 与现有事实源的关系", addition)
    if not dry_run:
        detail.write_text(text, encoding="utf-8")
        # Keep index status in sync.
        index_path = knowledge_index_path(root)
        lines = read_text(index_path).splitlines()
        table = find_table(lines, KNOWLEDGE_TABLE_HEADER)
        rows = lines[table.body_start : table.body_end]
        updated_rows = []
        for row in rows:
            cells = split_table_line(row)
            if len(cells) >= 6 and cells[0] == args.id:
                cells[2] = args.status
                row = render_table_row(cells)
            updated_rows.append(row)
        index_path.write_text("\n".join(lines[: table.body_start] + updated_rows + lines[table.body_end :]).rstrip() + "\n", encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would mark" if dry_run else "marked"
    return emit_write_result(args, "knowledge mark", f"{action} knowledge {args.id}", [detail, knowledge_index_path(root)], check_result)


def parse_iso_date_value(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def iso_dates_in_text(text: str) -> list[date]:
    dates: list[date] = []
    for match in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", text):
        parsed = parse_iso_date_value(match.group(0))
        if parsed is not None:
            dates.append(parsed)
    return dates


def newest_date(values: Sequence[date]) -> date | None:
    return max(values) if values else None


def date_age_days(value: date | None, today_value: date) -> int | None:
    if value is None:
        return None
    return (today_value - value).days


def stale_item(
    root: Path,
    path: Path,
    kind: str,
    signal: str,
    reason: str,
    suggested_action: str,
    *,
    status: str | None = None,
    item_id: str | None = None,
    age_days: int | None = None,
) -> dict[str, object]:
    rel_path = relative_display_path(path, root)
    item: dict[str, object] = {
        "kind": kind,
        "signal": signal,
        "path": rel_path,
        "reason": reason,
        "age_days": age_days,
        "status": status,
        "suggested_action": suggested_action,
        # Compatibility field retained for one release cycle.
        "message": reason,
    }
    if item_id is not None:
        item["id"] = item_id
    return item


def review_marker_dates(text: str) -> list[date]:
    dates: list[date] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        lower = line.lower()
        if "last reviewed" not in lower and "上次审阅" not in line and "最近审阅" not in line:
            continue
        window = "\n".join(lines[index : index + 3])
        dates.extend(iso_dates_in_text(window))
    return dates


def review_current_task_stale(root: Path, days: int, today_value: date) -> list[dict[str, object]]:
    path = current_task_path(root)
    if not path.exists():
        return []
    status = extract_current_task_status(path) or ""
    if status != "Active":
        return []
    text = read_text(path)
    latest = newest_date(iso_dates_in_text(text))
    age = date_age_days(latest, today_value)
    if latest is None:
        return [
            stale_item(
                root,
                path,
                "current_task",
                "current_task_active_missing_update_date",
                "Current_Task is Active but no ISO update/review date was found.",
                "Review the active task and add/update a dated status note or finish/block/clear it.",
                status=status,
            )
        ]
    if age is not None and age > days:
        return [
            stale_item(
                root,
                path,
                "current_task",
                "current_task_active_stale",
                f"Current_Task has been Active for {age} days since the newest visible date.",
                "Review the active task and update, block, finish, or clear it.",
                status=status,
                age_days=age,
            )
        ]
    return []


def review_task_plan_stale(root: Path) -> list[dict[str, object]]:
    path = task_plan_path(root)
    if not path.exists():
        return []
    items: list[dict[str, object]] = []
    status = extract_heading_value(path, "## 大任务状态") or ""
    try:
        rows = read_task_rows(path)
    except SystemExit as exc:
        return [
            stale_item(
                root,
                path,
                "task_plan",
                "task_plan_unreadable",
                str(exc),
                "Fix Task_Plan structure before using it as a default attention source.",
                status=status or None,
            )
        ]

    terminal_statuses = {"Done", "Skipped", "Superseded"}
    unfinished = [row for row in rows if row.get("状态") not in terminal_statuses]
    if status == "Done" and unfinished:
        items.append(
            stale_item(
                root,
                path,
                "task_plan",
                "task_plan_done_with_unfinished_tasks",
                "Task_Plan is Done but still contains unfinished subtasks.",
                "Review the task board and either finish/archive tasks or correct the plan status.",
                status=status,
            )
        )
    if status == "Empty" and rows:
        items.append(
            stale_item(
                root,
                path,
                "task_plan",
                "task_plan_empty_with_tasks",
                "Task_Plan is Empty but still contains subtask rows.",
                "Clear stale rows or restore the correct plan status.",
                status=status,
            )
        )
    if status in {"Active", "Paused"} and rows and not unfinished:
        items.append(
            stale_item(
                root,
                path,
                "task_plan",
                "task_plan_open_status_with_terminal_tasks",
                "Task_Plan is Active/Paused but all subtasks are terminal.",
                "Review whether the plan should be completed or archived.",
                status=status,
            )
        )
    active_rows = [row for row in rows if row.get("状态") == "Active"]
    if len(active_rows) > 1:
        items.append(
            stale_item(
                root,
                path,
                "task_plan",
                "task_plan_multiple_active_subtasks",
                "Task_Plan has more than one Active subtask.",
                "Choose the current focus and reset other Active rows.",
                status=status or None,
            )
        )
    for row in rows:
        if row.get("状态") == "Blocked":
            items.append(
                stale_item(
                    root,
                    path,
                    "task_plan",
                    "task_plan_blocked_subtask",
                    f"Subtask {row.get('ID', '')} is Blocked.",
                    "Review the blocker and decide whether to unblock, rescope, or archive it.",
                    status="Blocked",
                    item_id=row.get("ID", "") or None,
                )
            )
    return items


def read_feedback_rows(path: Path) -> list[dict[str, str]]:
    table = find_table(read_text(path).splitlines(), FEEDBACK_TABLE_HEADER)
    rows: list[dict[str, str]] = []
    for line in read_text(path).splitlines()[table.body_start : table.body_end]:
        cells = split_table_line(line)
        if len(cells) < len(table.headers) or cells[0] == "暂无":
            continue
        rows.append(dict(zip(table.headers, cells)))
    return rows


def review_feedback_stale(root: Path, days: int, today_value: date) -> list[dict[str, object]]:
    path = root / "active" / "Feedback_Inbox.md"
    if not path.exists():
        return []
    try:
        rows = read_feedback_rows(path)
    except SystemExit as exc:
        return [
            stale_item(
                root,
                path,
                "feedback",
                "feedback_inbox_unreadable",
                str(exc),
                "Fix Feedback_Inbox structure before using it as an attention signal.",
            )
        ]
    items: list[dict[str, object]] = []
    watched_statuses = {"Open", "Triaged", "Planned"}
    for row in rows:
        status = row.get("状态", "")
        if status not in watched_statuses:
            continue
        row_text = "\n".join(row.values())
        latest = newest_date(iso_dates_in_text(row_text))
        age = date_age_days(latest, today_value)
        if latest is None:
            signal = "feedback_pending_missing_date"
            message = f"Feedback item {row.get('ID', '')} is {status} but has no ISO date for age checks."
            suggested = "Triaging can continue, but add evidence/date when carrying feedback across sessions."
        elif age is not None and age > days:
            signal = "feedback_pending_stale"
            message = f"Feedback item {row.get('ID', '')} is {status} and appears {age} days old."
            suggested = "Triage the feedback into a plan/current fact/draft, or close/archive it."
        else:
            continue
        items.append(
            stale_item(
                root,
                path,
                "feedback",
                signal,
                message,
                suggested,
                status=status,
                item_id=row.get("ID", "") or None,
                age_days=age,
            )
        )
    return items


def review_context_stale(root: Path, days: int, today_value: date) -> list[dict[str, object]]:
    path = root / "active" / "Context.md"
    if not path.exists():
        return []
    text = read_text(path)
    dates = review_marker_dates(text)
    latest = newest_date(dates)
    age = date_age_days(latest, today_value)
    if latest is None:
        return [
            stale_item(
                root,
                path,
                "context_review",
                "context_missing_review_marker",
                "Context does not contain a `Last reviewed` / `上次审阅` marker.",
                "Review current facts and add a section-level review marker when appropriate.",
            )
        ]
    if age is not None and age > days:
        return [
            stale_item(
                root,
                path,
                "context_review",
                "context_review_stale",
                f"Context review marker is {age} days old.",
                "Review current facts and refresh the review marker if still accurate.",
                age_days=age,
            )
        ]
    return []


def date_from_filename(path: Path) -> date | None:
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", path.name)
    if not match:
        return None
    return parse_iso_date_value(match.group(1))


def file_age_days(path: Path, today_value: date) -> int | None:
    named_date = date_from_filename(path)
    if named_date is not None:
        return date_age_days(named_date, today_value)
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return None
    return date_age_days(modified, today_value)


def review_knowledge_stale(root: Path, days: int, today_value: date) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    index_path = knowledge_index_path(root)
    if index_path.exists():
        try:
            table = find_table(read_text(index_path).splitlines(), KNOWLEDGE_TABLE_HEADER)
            for line in read_text(index_path).splitlines()[table.body_start : table.body_end]:
                cells = split_table_line(line)
                if len(cells) < 6 or cells[0] == "暂无":
                    continue
                knowledge_id, title, status, _tags, _summary, detail = cells[:6]
                if status != "Draft":
                    continue
                ref = strip_code_ticks(detail)
                resolved = resolve_ref(root, index_path, ref) if should_check_ref(ref) else None
                age = file_age_days(resolved, today_value) if resolved is not None else None
                if age is None:
                    signal = "knowledge_index_draft_missing_age"
                    message = f"Knowledge {knowledge_id} is Draft but has no reliable age signal."
                elif age > days:
                    signal = "knowledge_index_draft_stale"
                    message = f"Knowledge {knowledge_id} is Draft and appears {age} days old."
                else:
                    continue
                items.append(
                    stale_item(
                        root,
                        index_path,
                        "knowledge",
                        signal,
                        message,
                        "Apply, mark, promote, reject, or keep the draft with an explicit reason.",
                        status=status,
                        item_id=knowledge_id or title,
                        age_days=age,
                    )
                )
        except SystemExit as exc:
            items.append(
                stale_item(
                    root,
                    index_path,
                    "knowledge",
                    "knowledge_index_unreadable",
                    str(exc),
                    "Fix Knowledge_Index structure before relying on it.",
                )
            )

    draft_dir = root / "worklog" / "knowledge-drafts"
    if draft_dir.exists():
        for draft in sorted(draft_dir.glob("*.md")):
            age = file_age_days(draft, today_value)
            if age is not None and age <= days:
                continue
            signal = "knowledge_draft_stale" if age is not None else "knowledge_draft_missing_age"
            message = (
                f"Knowledge draft {draft.name} appears {age} days old."
                if age is not None
                else f"Knowledge draft {draft.name} has no reliable age signal."
            )
            items.append(
                stale_item(
                    root,
                    draft,
                    "knowledge_draft",
                    signal,
                    message,
                    "Apply, mark, rewrite, reject, or archive the draft after review.",
                    status="Draft",
                    age_days=age,
                )
            )
    return items


def review_stale_next_actions(stale_items: Sequence[dict[str, object]]) -> list[str]:
    if not stale_items:
        return ["No stale attention candidates found."]
    actions = ["Review stale_items as candidates, not semantic truth."]
    kinds = {str(item.get("kind") or "") for item in stale_items}
    if "current_task" in kinds:
        actions.append("Review active Current_Task status, update its dated note, or finish/block/clear it.")
    if "task_plan" in kinds:
        actions.append("Review Task_Plan status and subtask rows, then complete, unblock, archive, or correct them.")
    if "feedback" in kinds:
        actions.append("Triage Feedback_Inbox items into a plan, current fact, draft, close, or archive them.")
    if "context_review" in kinds:
        actions.append("Review active/Context.md current facts and refresh the review marker if still accurate.")
    if "knowledge" in kinds:
        actions.append("Review Knowledge_Index Draft entries and apply, mark, promote, reject, or keep them with a reason.")
    if "knowledge_draft" in kinds:
        actions.append("Review knowledge drafts and apply, mark, close, rewrite, or archive them.")
    actions.append("Use a writeback draft when the unique authority location is unclear.")
    return actions


def review_stale_summary(stale_items: Sequence[dict[str, object]]) -> dict[str, object]:
    by_kind: dict[str, int] = {}
    by_path: dict[str, int] = {}
    for item in stale_items:
        kind = str(item.get("kind") or "unknown")
        path = str(item.get("path") or "")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_path[path] = by_path.get(path, 0) + 1
    return {
        "total": len(stale_items),
        "by_kind": dict(sorted(by_kind.items())),
        "by_path": dict(sorted(by_path.items())),
    }


def collect_review_stale_items(root: Path, days: int, today_value: date) -> list[dict[str, object]]:
    stale_items: list[dict[str, object]] = []
    stale_items.extend(review_current_task_stale(root, days, today_value))
    stale_items.extend(review_task_plan_stale(root))
    stale_items.extend(review_feedback_stale(root, days, today_value))
    stale_items.extend(review_context_stale(root, days, today_value))
    stale_items.extend(review_knowledge_stale(root, days, today_value))
    return stale_items


def review_stale_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    if args.days <= 0:
        raise SystemExit("--days must be greater than 0")
    today_value = parse_iso_date_value(args.today) if args.today else date.today()
    if today_value is None:
        raise SystemExit("invalid --today date")
    stale_items = collect_review_stale_items(root, args.days, today_value)
    warnings = [str(item["reason"]) for item in stale_items]
    payload: dict[str, object] = {
        "command": "review stale",
        "ok": True,
        "context": str(root),
        "days": args.days,
        "today": today_value.isoformat(),
        "summary": review_stale_summary(stale_items),
        "warnings": warnings,
        "stale_items": stale_items,
        "error_code": None,
        "next_actions": review_stale_next_actions(stale_items),
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


def audit_candidate(
    root: Path,
    path: Path,
    kind: str,
    severity: str,
    reason: str,
    suggested_action: str,
    *,
    section: str | None = None,
) -> dict[str, object]:
    return {
        "kind": kind,
        "severity": severity,
        "path": relative_display_path(path.resolve(), root.resolve()),
        "section": section,
        "reason": reason,
        "suggested_action": suggested_action,
    }


def markdown_sections(text: str) -> list[tuple[int, str, list[str]]]:
    lines = text.splitlines()
    sections: list[tuple[int, str, list[str]]] = []
    for index, line in enumerate(lines):
        level = heading_level(line)
        if level is None:
            continue
        body_end = len(lines)
        for candidate_index in range(index + 1, len(lines)):
            candidate_level = heading_level(lines[candidate_index])
            if candidate_level is not None and candidate_level <= level:
                body_end = candidate_index
                break
        title = line.strip().lstrip("#").strip()
        sections.append((level, title, lines[index + 1 : body_end]))
    return sections


def section_contains_child_heading(body_lines: list[str]) -> bool:
    return any(heading_level(line) is not None for line in body_lines)


def audit_active_section_too_long(root: Path) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    active_paths = [
        root / "active" / "Context.md",
        root / "active" / "Current_Task.md",
        root / "active" / "Task_Plan.md",
        root / "active" / "Workstreams.md",
    ]
    details_dir = workstream_details_dir(root)
    if details_dir.is_dir():
        active_paths.extend(sorted(details_dir.glob("*.md")))
    for path in active_paths:
        if not path.exists():
            continue
        for level, section, body_lines in markdown_sections(read_text(path)):
            if level == 1 and section_contains_child_heading(body_lines):
                continue
            nonempty_count = sum(1 for line in body_lines if line.strip() and line.strip() != "---")
            if nonempty_count <= AUDIT_ACTIVE_SECTION_MAX_NONEMPTY_LINES:
                continue
            candidates.append(
                audit_candidate(
                    root,
                    path,
                    "active_section_too_long",
                    "P1-candidate",
                    (
                        f"section has {nonempty_count} non-empty lines, above the "
                        f"MVP threshold {AUDIT_ACTIVE_SECTION_MAX_NONEMPTY_LINES}."
                    ),
                    (
                        "Review whether this section should be shortened to current facts, split into narrower "
                        "sections, or moved to worklog/reference material."
                    ),
                    section=section,
                )
            )
    return candidates


def audit_current_task_stale(root: Path, today_value: date) -> list[dict[str, object]]:
    path = current_task_path(root)
    if not path.exists():
        return []
    status = extract_current_task_status(path) or ""
    if status != "Active":
        return []
    text = read_text(path)
    latest = newest_date(iso_dates_in_text(text))
    age = date_age_days(latest, today_value)
    if latest is not None and age is not None and age <= DEFAULT_STALE_DAYS:
        return []
    reason = (
        "Current_Task is Active but no ISO update/review date was found."
        if latest is None
        else f"Current_Task newest visible date is {latest.isoformat()}, {age} days old."
    )
    return [
        audit_candidate(
            root,
            path,
            "stale_current_task_or_workstream_stage",
            "P1-candidate",
            reason,
            "Review the active task and update, block, finish, or clear it.",
            section="当前任务状态",
        )
    ]


def parse_workstream_detail_for_audit(path: Path) -> WorkstreamDetail | None:
    try:
        metadata, body, diagnostics = parse_front_matter(read_text(path))
    except UnicodeDecodeError:
        return None
    if diagnostics:
        return None
    workstream_id = metadata.get("id")
    if not isinstance(workstream_id, str) or not WORKSTREAM_ID_RE.match(workstream_id):
        workstream_id = path.stem
    return WorkstreamDetail(workstream_id, path, metadata, body, diagnostics)


def audit_workstream_stage_stale(root: Path, today_value: date) -> list[dict[str, object]]:
    details_dir = workstream_details_dir(root)
    if not details_dir.is_dir():
        return []
    candidates: list[dict[str, object]] = []
    for path in sorted(details_dir.glob("WS*.md")):
        detail = parse_workstream_detail_for_audit(path)
        if detail is None:
            continue
        status = detail.metadata.get("status")
        if status not in ACTIVE_WORKSTREAM_STATUSES:
            continue
        current_stage = detail.metadata.get("current_stage")
        if not isinstance(current_stage, str) or not current_stage.strip():
            continue
        current_stage = current_stage.strip()
        rows = read_workstream_stage_rows(detail.body)
        current_row = next((row for row in rows if row.get("ID") == current_stage), None)
        if current_row is None or current_row.get("状态") != "Active":
            continue
        row_text = "\n".join(current_row.values())
        latest = newest_date(iso_dates_in_text(row_text))
        age = date_age_days(latest, today_value)
        if latest is not None and age is not None and age <= DEFAULT_STALE_DAYS:
            continue
        reason = (
            f"Workstream current_stage {current_stage} is Active but has no ISO update/review date in its stage row."
            if latest is None
            else f"Workstream current_stage {current_stage} newest visible date is {latest.isoformat()}, {age} days old."
        )
        candidates.append(
            audit_candidate(
                root,
                path,
                "stale_current_task_or_workstream_stage",
                "P1-candidate",
                reason,
                "Review the Workstream stage and update evidence/date, block it, or move focus to the next stage.",
                section="阶段",
            )
        )
    return candidates


def audit_terminal_conclusion_not_merged(root: Path) -> list[dict[str, object]]:
    details_dir = workstream_details_dir(root)
    if not details_dir.is_dir():
        return []
    candidates: list[dict[str, object]] = []
    for path in sorted(details_dir.glob("WS*.md")):
        detail = parse_workstream_detail_for_audit(path)
        if detail is None:
            continue
        status = detail.metadata.get("status")
        if status not in {"ReadyToMerge", "Done"}:
            continue
        merge_targets = detail.metadata.get("merge_targets")
        has_merge_targets = isinstance(merge_targets, list) and any(str(target).strip() for target in merge_targets)
        has_merge_request = merge_request_has_required_fields(detail.body)
        merge_resolution = detail.metadata.get("merge_resolution")
        if status == "ReadyToMerge" and (has_merge_targets or has_merge_request):
            candidates.append(
                audit_candidate(
                    root,
                    path,
                    "terminal_conclusion_not_merged",
                    "P0-candidate",
                    "ReadyToMerge workstream has merge inputs that still require review and merge resolution.",
                    "Review the merge request and either merge, reject, mark no_merge_required, or keep it ReadyToMerge.",
                    section="合并请求",
                )
            )
        elif status == "Done" and (has_merge_targets or has_merge_request) and not merge_resolution:
            candidates.append(
                audit_candidate(
                    root,
                    path,
                    "terminal_conclusion_not_merged",
                    "P0-candidate",
                    "Done workstream has merge inputs but no merge_resolution metadata.",
                    "Review whether the conclusion was merged, rejected, archived, or requires no authority merge.",
                    section="合并请求",
                )
            )
    return candidates


def audit_context_summary(candidates: Sequence[dict[str, object]]) -> dict[str, object]:
    by_kind: dict[str, int] = {}
    by_path: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for candidate in candidates:
        kind = str(candidate.get("kind") or "unknown")
        path = str(candidate.get("path") or "")
        severity = str(candidate.get("severity") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_path[path] = by_path.get(path, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1
    return {
        "total": len(candidates),
        "by_kind": dict(sorted(by_kind.items())),
        "by_path": dict(sorted(by_path.items())),
        "by_severity": dict(sorted(by_severity.items())),
    }


def audit_context_next_actions(candidates: Sequence[dict[str, object]]) -> list[str]:
    if not candidates:
        return ["No context audit candidates found."]
    actions = ["Review audit candidates as advisory signals; do not treat them as semantic truth."]
    kinds = {str(candidate.get("kind") or "") for candidate in candidates}
    if "active_section_too_long" in kinds:
        actions.append(
            "Review long active sections; shorten to current facts, split narrow sections, or move history to worklog/reference material."
        )
    if "stale_current_task_or_workstream_stage" in kinds:
        actions.append("Review stale current task or Workstream stage focus and update, block, finish, or clear it.")
    if "terminal_conclusion_not_merged" in kinds:
        actions.append("Review ReadyToMerge/Done Workstream merge state and decide whether authority context needs a merge.")
    return actions


def collect_audit_context_candidates(root: Path, today_value: date) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    candidates.extend(audit_active_section_too_long(root))
    candidates.extend(audit_current_task_stale(root, today_value))
    candidates.extend(audit_workstream_stage_stale(root, today_value))
    candidates.extend(audit_terminal_conclusion_not_merged(root))
    return candidates


def audit_context_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    today_value = date.today()
    candidates = collect_audit_context_candidates(root, today_value)
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "ok": True,
        "command": "audit context",
        "context": str(root),
        "candidates": candidates,
        "summary": audit_context_summary(candidates),
        "next_actions": audit_context_next_actions(candidates),
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


def curation_draft_path(root: Path, draft_date: date, name: str | None) -> Path:
    draft_name = f"{name}.md" if name else f"{draft_date.isoformat()}.md"
    return root / "worklog" / "curation-drafts" / draft_name


def markdown_value(value: object) -> str:
    if value is None:
        return "null"
    text = str(value)
    return text if text else "null"


def render_curation_draft(
    draft_date: date,
    days: int,
    stale_items: Sequence[dict[str, object]],
    summary: dict[str, object],
) -> str:
    lines: list[str] = [
        f"# 注意力治理草案：{draft_date.isoformat()}",
        "",
        "## 摘要",
        "",
        f"- stale candidates: {summary.get('total', len(stale_items))}",
        "- generated from: acf review stale",
        f"- days threshold: {days}",
        "",
    ]
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in stale_items:
        grouped.setdefault(str(item.get("kind") or "unknown"), []).append(item)
    for kind in sorted(grouped):
        lines.extend([f"## {kind}", ""])
        for index, item in enumerate(grouped[kind], start=1):
            lines.extend(
                [
                    f"### 候选 {index}",
                    "",
                    f"- path: {markdown_value(item.get('path'))}",
                    f"- signal: {markdown_value(item.get('signal'))}",
                    f"- reason: {markdown_value(item.get('reason'))}",
                    f"- age_days: {markdown_value(item.get('age_days'))}",
                    f"- status: {markdown_value(item.get('status'))}",
                    f"- suggested_action: {markdown_value(item.get('suggested_action'))}",
                    "- 人工复核：",
                    "- 建议处理：保留 / 更新 / 归档 / 关闭 / 生成 writeback draft",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def curate_draft_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    if args.days <= 0:
        raise SystemExit("--days must be greater than 0")
    today_value = parse_iso_date_value(args.today) if args.today else date.today()
    if today_value is None:
        raise SystemExit("invalid --today date")
    stale_items = collect_review_stale_items(root, args.days, today_value)
    stale_summary = review_stale_summary(stale_items)
    draft_path = curation_draft_path(root, today_value, args.name)
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
                render_curation_draft(today_value, args.days, stale_items, stale_summary),
                encoding="utf-8",
            )
            created = True

    check_result = maybe_check_after(args, root)
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
        else review_stale_next_actions(stale_items),
    }
    if dry_run and stale_items:
        payload["planned_draft"] = render_curation_draft(today_value, args.days, stale_items, stale_summary)
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
    if PLACEHOLDER_RE.search(ref):
        return False
    if ref.startswith(("http://", "https://", "file://")):
        return False
    if ref.startswith("<") or ref.startswith("$"):
        return False
    return True


def clean_markdown_link_target(value: str) -> str:
    target = value.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    return target


def split_ref_fragment(ref: str) -> tuple[str, str]:
    if "#" not in ref:
        return ref, ""
    target, fragment = ref.split("#", 1)
    return target, fragment


def is_uri_ref(ref: str) -> bool:
    return re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", ref) is not None


def is_local_link_ref(ref: str) -> bool:
    cleaned = clean_markdown_link_target(ref)
    if not cleaned or PLACEHOLDER_RE.search(cleaned) or "*" in cleaned:
        return False
    if cleaned in {"path", "url"}:
        return False
    if cleaned.startswith("$"):
        return False
    if is_uri_ref(cleaned):
        return False
    return True


def normalize_ref_path(ref: str) -> str:
    return unquote(ref.replace("\\", "/"))


def resolve_ref_path(root: Path, md_file: Path, ref: str) -> Path | None:
    normalized = normalize_ref_path(ref)
    root = root.resolve()
    project_root = infer_project_root(root).resolve()
    candidates = [
        (root / normalized).resolve(),
        (md_file.parent / normalized).resolve(),
        (project_root / normalized).resolve(),
    ]
    for candidate in candidates:
        if candidate.exists() and is_relative_to(candidate, project_root):
            return candidate
    return None


def resolve_ref(root: Path, md_file: Path, ref: str) -> Path | None:
    ref_path, _fragment = split_ref_fragment(clean_markdown_link_target(ref))
    return resolve_ref_path(root, md_file, ref_path)


def markdown_heading_slug(value: str) -> str:
    text = unicodedata.normalize("NFKC", value.strip()).lower()
    text = re.sub(r"\s+", "-", text)
    chars: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if char.isalnum() or category.startswith(("L", "N")):
            chars.append(char)
        elif char in {"-", "_"}:
            chars.append(char)
    slug = re.sub(r"-+", "-", "".join(chars)).strip("-")
    return slug


def markdown_heading_text(line: str) -> str | None:
    match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
    if not match:
        return None
    return re.sub(r"\s+#+\s*$", "", match.group(2)).strip()


def markdown_heading_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for line in text.splitlines():
        heading = markdown_heading_text(line)
        if heading is None:
            continue
        base = markdown_heading_slug(heading)
        index = seen.get(base, 0)
        seen[base] = index + 1
        anchors.add(base if index == 0 else f"{base}-{index}")
    return anchors


def markdown_heading_anchor_for(text: str, heading: str) -> str | None:
    wanted = heading.strip()
    if wanted.startswith("#"):
        wanted = wanted.lstrip("#").strip()
    seen: dict[str, int] = {}
    for line in text.splitlines():
        current = markdown_heading_text(line)
        if current is None:
            continue
        base = markdown_heading_slug(current)
        index = seen.get(base, 0)
        seen[base] = index + 1
        anchor = base if index == 0 else f"{base}-{index}"
        if current.strip() == wanted:
            return anchor
    return None


def iter_non_fenced_lines(text: str) -> Iterable[tuple[int, str]]:
    in_fence = False
    fence_marker = ""
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        fence = re.match(r"^(```+|~~~+)", stripped)
        if fence:
            marker = fence.group(1)[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if not in_fence:
            yield index, line


def validate_local_markdown_link(
    root: Path,
    md_file: Path,
    rel_file: str,
    raw_target: str,
    errors: list[str],
) -> None:
    target = clean_markdown_link_target(raw_target)
    if not is_local_link_ref(target):
        return
    target_ref, fragment = split_ref_fragment(target)
    if target_ref == "":
        target_path = md_file
    else:
        target_path = resolve_ref_path(root, md_file, target_ref)
        if target_path is None:
            errors.append(f"{rel_file}: broken markdown link `{target}`")
            return
    if fragment and target_path.suffix.lower() == ".md":
        anchors = markdown_heading_anchors(read_text(target_path))
        normalized_fragment = markdown_heading_slug(unquote(fragment))
        if fragment not in anchors and normalized_fragment not in anchors:
            errors.append(f"{rel_file}: broken markdown link anchor `{target}`")


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
    link_match = MARKDOWN_LINK_RE.fullmatch(value)
    if link_match:
        return link_match.group(2).strip() or clean_markdown_link_target(link_match.group(3))
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


def safe_section_body(path: Path, heading: str) -> str | None:
    try:
        lines = read_text(path).splitlines()
        return section_body(lines, find_section(lines, heading))
    except SystemExit:
        return None


def meaningful_ref_value(value: str | None) -> bool:
    normalized = (value or "").strip()
    return bool(normalized) and normalized not in {"无。", "无", "None", "Empty", "-"}


def workstream_statuses_for_task_checks(root: Path) -> dict[str, str]:
    if not workstream_index_path(root).exists():
        return {}
    try:
        entries = parse_workstream_index(root)
    except SystemExit:
        return {}
    statuses = {entry.workstream_id: entry.status for entry in entries}
    for entry in entries:
        try:
            detail_path = resolve_workstream_detail_path(root, entry.workstream_id, entries)
        except SystemExit:
            continue
        if not detail_path.exists():
            continue
        try:
            metadata, _body, _diagnostics = parse_front_matter(read_text(detail_path))
        except UnicodeDecodeError:
            continue
        detail_status = metadata.get("status")
        if isinstance(detail_status, str):
            statuses[entry.workstream_id] = detail_status
    return statuses


def check_current_execution_workstream(root: Path, errors: list[str]) -> None:
    task_file = root / "active" / "Current_Task.md"
    if not task_file.exists():
        return
    current_line = extract_heading_value(task_file, "## 当前执行线")
    if not meaningful_ref_value(current_line):
        return
    statuses = workstream_statuses_for_task_checks(root)
    for workstream_id in WORKSTREAM_ID_TOKEN_RE.findall(current_line or ""):
        status = statuses.get(workstream_id)
        if status is None:
            errors.append(f"active/Current_Task.md: current execution line references missing workstream `{workstream_id}`")
        elif status in {"Done", "Cancelled"}:
            errors.append(
                f"active/Current_Task.md: current execution line references terminal workstream `{workstream_id}` ({status})"
            )


def check_task_plan(root: Path, errors: list[str]) -> None:
    plan_path = root / "active" / "Task_Plan.md"
    if not plan_path.exists():
        return
    status = extract_heading_value(plan_path, "## 大任务状态")
    if status and not is_placeholder(status) and status not in VALID_PLAN_STATUSES:
        errors.append(f"active/Task_Plan.md: invalid plan status `{status}`")

    try:
        rows = read_task_rows(plan_path)
    except SystemExit as exc:
        errors.append(f"active/Task_Plan.md: {exc}")
        return
    try:
        stage_rows = read_task_stage_rows(plan_path)
    except SystemExit as exc:
        errors.append(f"active/Task_Plan.md: {exc}")
        return

    seen: set[str] = set()
    active_count = 0
    for row in rows:
        task_id = row.get("ID", "")
        task_status = row.get("状态", "")
        if not TASK_ID_RE.match(task_id):
            errors.append(f"active/Task_Plan.md: invalid subtask id `{task_id}`")
        if task_id in seen:
            errors.append(f"active/Task_Plan.md: duplicate subtask id `{task_id}`")
        seen.add(task_id)
        if task_status not in VALID_SUBTASK_STATUSES:
            errors.append(f"active/Task_Plan.md: invalid subtask status `{task_status}` for {task_id}")
        if task_status == "Active":
            active_count += 1
    if active_count > 1:
        errors.append("active/Task_Plan.md: more than one subtask is Active")

    stage_seen: set[str] = set()
    workstream_statuses = workstream_statuses_for_task_checks(root)
    for row in stage_rows:
        stage_id = row.get("ID", "")
        stage_status = row.get("状态", "")
        parent_task = row.get("父任务", "")
        if not TASK_STAGE_ID_RE.match(stage_id):
            errors.append(f"active/Task_Plan.md: invalid task stage id `{stage_id}`")
        if stage_id in stage_seen:
            errors.append(f"active/Task_Plan.md: duplicate task stage id `{stage_id}`")
        stage_seen.add(stage_id)
        if stage_status not in VALID_SUBTASK_STATUSES:
            errors.append(f"active/Task_Plan.md: invalid task stage status `{stage_status}` for {stage_id}")
        if not TASK_ID_RE.match(parent_task):
            errors.append(f"active/Task_Plan.md: task stage `{stage_id}` has invalid parent task `{parent_task}`")
        elif parent_task not in seen:
            errors.append(f"active/Task_Plan.md: task stage `{stage_id}` parent task `{parent_task}` does not exist")
        owner_value = row.get("归属 Workstream", "")
        if meaningful_ref_value(owner_value):
            owner_ids = WORKSTREAM_ID_TOKEN_RE.findall(owner_value)
            if not owner_ids:
                errors.append(f"active/Task_Plan.md: task stage `{stage_id}` has invalid workstream owner `{owner_value}`")
            for workstream_id in owner_ids:
                if workstream_id not in workstream_statuses:
                    errors.append(f"active/Task_Plan.md: task stage `{stage_id}` workstream `{workstream_id}` does not exist")

    focus = extract_heading_value(plan_path, "## 当前焦点")
    if focus and focus not in {"无。", "None", "Empty"} and not is_placeholder(focus) and focus not in seen and focus not in stage_seen:
        errors.append(f"active/Task_Plan.md: current focus `{focus}` does not match any subtask id")

    task_file = root / "active" / "Current_Task.md"
    if task_file.exists():
        task_id = extract_heading_value(task_file, "## 子任务 ID")
        if task_id and task_id not in {"无。", "None", "Empty"} and not is_placeholder(task_id):
            if TASK_STAGE_ID_RE.match(task_id):
                if task_id not in stage_seen:
                    errors.append(f"active/Current_Task.md: stage id `{task_id}` does not exist in active/Task_Plan.md")
            elif task_id not in seen:
                errors.append(f"active/Current_Task.md: subtask id `{task_id}` does not exist in active/Task_Plan.md")
    check_current_execution_workstream(root, errors)


def check_archive(root: Path, errors: list[str]) -> None:
    index_path = root / "archive" / "Archive_Index.md"
    if not index_path.exists():
        return
    rows = parse_markdown_table_rows(read_text(index_path))
    for cells in rows:
        if len(cells) < 5 or cells[0] in {"日期", "暂无"}:
            continue
        archive_date, _kind, _title, _reason, detail = cells[:5]
        if not DATE_RE.match(archive_date):
            errors.append(f"archive/Archive_Index.md: invalid archive date `{archive_date}`")
        ref = strip_code_ticks(detail)
        if should_check_ref(ref) and resolve_ref(root, index_path, ref) is None:
            errors.append(f"archive/Archive_Index.md: broken archive detail `{ref}`")


def check_knowledge(root: Path, errors: list[str], warnings: list[str], strict: bool) -> None:
    index_path = root / "reference" / "Knowledge_Index.md"
    indexed_refs: list[tuple[str, str, str]] = []
    if index_path.exists():
        rows = parse_markdown_table_rows(read_text(index_path))
        for cells in rows:
            if len(cells) < 6 or cells[0] in {"ID", "暂无"}:
                continue
            knowledge_id, _title, status, _tags, _summary, detail = cells[:6]
            if not KNOWLEDGE_ID_RE.match(knowledge_id):
                errors.append(f"reference/Knowledge_Index.md: invalid knowledge id `{knowledge_id}`")
            if status not in VALID_KNOWLEDGE_STATUSES:
                errors.append(f"reference/Knowledge_Index.md: invalid knowledge status `{status}` for {knowledge_id}")
            ref = strip_code_ticks(detail)
            indexed_refs.append((knowledge_id, status, ref))
            if should_check_ref(ref) and resolve_ref(root, index_path, ref) is None:
                errors.append(f"reference/Knowledge_Index.md: broken knowledge detail `{ref}`")

    for knowledge_id, index_status, ref in indexed_refs:
        resolved = resolve_ref(root, index_path, ref)
        if resolved is None:
            continue
        file_status = extract_heading_value(resolved, "## 状态")
        if file_status and file_status not in VALID_KNOWLEDGE_STATUSES:
            rel = resolved.relative_to(root).as_posix()
            errors.append(f"{rel}: invalid knowledge status `{file_status}`")
        if file_status and index_status != file_status:
            errors.append(f"reference/Knowledge_Index.md: status mismatch for {knowledge_id} ({index_status}) vs {ref} ({file_status})")

    knowledge_dir = root / "reference" / "knowledge"
    if not knowledge_dir.exists():
        return
    required_headings = (
        "## 状态",
        "## 结论",
        "## 适用场景",
        "## 不适用场景",
        "## 来源",
        "## 与现有事实源的关系",
        "## 去重判断",
    )
    fact_phrases = ("当前任务状态", "今日完成", "当前已支持")
    for path in sorted(knowledge_dir.glob("*.md")):
        rel = path.relative_to(root).as_posix()
        text = read_text(path)
        for heading in required_headings:
            body = safe_section_body(path, heading)
            if body is None or not body.strip():
                errors.append(f"{rel}: missing or empty required section `{heading}`")
            elif strict and any(placeholder in body for placeholder in ("待补充", "未分类", "无。")):
                errors.append(f"{rel}: section `{heading}` still contains placeholder-like draft content")
        status = extract_heading_value(path, "## 状态")
        if status and status not in VALID_KNOWLEDGE_STATUSES:
            errors.append(f"{rel}: invalid knowledge status `{status}`")
        if status == "Promoted" and "Promoted to:" not in text:
            errors.append(f"{rel}: Promoted knowledge must record promoted target")
        source_body = safe_section_body(path, "## 来源") or ""
        refs = MARKDOWN_REF_RE.findall(source_body)
        if not refs:
            errors.append(f"{rel}: knowledge source must contain at least one Markdown source reference")
        for ref in refs:
            if should_check_ref(ref) and resolve_ref(root, path, ref) is None:
                errors.append(f"{rel}: broken knowledge source `{ref}`")
        for phrase in fact_phrases:
            if phrase in text:
                message = f"{rel}: may contain current-fact wording `{phrase}`"
                if strict:
                    errors.append(message)
                else:
                    warnings.append(message)
    for message in knowledge_similarity_messages(root):
        if strict:
            errors.append(message)
        else:
            warnings.append(message)


def check_warn_or_error(message: str, errors: list[str], warnings: list[str], strict: bool) -> None:
    if strict:
        errors.append(message)
    else:
        warnings.append(message)


def parse_workstream_detail_for_check(root: Path, workstream_id: str, detail_path: Path, errors: list[str]) -> WorkstreamDetail | None:
    rel = detail_path.relative_to(root).as_posix() if is_relative_to(detail_path, root) else str(detail_path)
    try:
        metadata, body, diagnostics = parse_front_matter(read_text(detail_path))
    except UnicodeDecodeError as exc:
        errors.append(f"{rel}: not valid UTF-8 ({exc})")
        return None
    diagnostics.extend(validate_front_matter(metadata, workstream_front_matter_schema()))
    metadata_id = metadata.get("id")
    if isinstance(metadata_id, str) and metadata_id != workstream_id:
        diagnostics.append(
            FrontMatterDiagnostic(
                "front_matter_schema_failed",
                f"workstream id mismatch: expected {workstream_id}, got {metadata_id}",
                field="id",
            )
        )
    for diagnostic in diagnostics:
        suffix = f" ({diagnostic.field})" if diagnostic.field else ""
        errors.append(f"{rel}: {diagnostic.code}{suffix}: {diagnostic.message}")
    return WorkstreamDetail(workstream_id, detail_path, metadata, body, diagnostics)


def read_workstream_stage_rows(body: str) -> list[dict[str, str]]:
    lines = body.splitlines()
    try:
        table = find_table(lines, WORKSTREAM_STAGE_TABLE_HEADER)
    except SystemExit:
        return []
    rows: list[dict[str, str]] = []
    for line in lines[table.body_start : table.body_end]:
        cells = split_table_line(line)
        if len(cells) < len(table.headers) or cells[0] == "暂无":
            continue
        rows.append(dict(zip(table.headers, cells)))
    return rows


def workstream_stage_payload(row: dict[str, str]) -> dict[str, str]:
    return {
        "id": row.get("ID", ""),
        "status": row.get("状态", ""),
        "title": row.get("阶段", ""),
        "depends_on": row.get("依赖", ""),
        "output": row.get("输出物", ""),
        "evidence": row.get("证据", ""),
        "next_action": row.get("下一步", ""),
    }


def render_workstream_stage_rows(rows: Sequence[dict[str, str]]) -> list[str]:
    if not rows:
        return [render_table_row(["暂无", "Empty", "无。", "无。", "无。", "无。", "无。"])]
    return [
        render_table_row(
            [
                row.get("ID", ""),
                row.get("状态", ""),
                row.get("阶段", ""),
                row.get("依赖", ""),
                row.get("输出物", ""),
                row.get("证据", ""),
                row.get("下一步", ""),
            ]
        )
        for row in rows
    ]


def replace_or_append_workstream_stage_rows(body: str, rows: Sequence[dict[str, str]]) -> str:
    rendered_rows = render_workstream_stage_rows(rows)
    lines = body.splitlines()
    try:
        table = find_table(lines, WORKSTREAM_STAGE_TABLE_HEADER)
    except SystemExit:
        table_text = "\n".join(
            [
                WORKSTREAM_STAGE_TABLE_HEADER,
                "|---|---|---|---|---|---|---|",
                *rendered_rows,
            ]
        )
        return body.rstrip() + f"\n\n---\n\n## 阶段\n\n{table_text}\n"
    updated_lines = list(lines[: table.body_start]) + rendered_rows + list(lines[table.body_end :])
    return "\n".join(updated_lines).rstrip() + "\n"


def find_workstream_stage_row(rows: Sequence[dict[str, str]], stage_id: str) -> dict[str, str] | None:
    return next((row for row in rows if row.get("ID") == stage_id), None)


def require_workstream_stage_belongs_to(workstream_id: str, stage_id: str) -> None:
    if not workstream_stage_belongs_to(workstream_id, stage_id):
        raise SystemExit(f"workstream_stage_scope_invalid: {stage_id} does not belong to {workstream_id}")


def terminal_workstream_stage_status(status: str) -> bool:
    return status in {"Done", "Cancelled", "Skipped"}


def workstream_stage_dependency_tokens(value: str) -> list[str]:
    return re.findall(r"\bWS\d{3}\.\d+\b", value or "")


def workstream_stage_belongs_to(workstream_id: str, stage_id: str) -> bool:
    return stage_id.startswith(f"{workstream_id}.")


def workstream_section_missing(body: str, heading: str) -> bool:
    value = safe_section_body_from_text(body, heading).strip()
    return not value or value in {"无。", "待补充。", "None", "Empty"}


def check_workstream_stage_focus(root: Path, detail: WorkstreamDetail, errors: list[str], strict: bool) -> None:
    rel = detail.path.relative_to(root).as_posix()
    workstream_id = detail.workstream_id
    status = detail.metadata.get("status")
    current_stage = detail.metadata.get("current_stage")
    rows = read_workstream_stage_rows(detail.body)
    stage_by_id: dict[str, dict[str, str]] = {}
    active_stage_ids: list[str] = []

    for row in rows:
        stage_id = row.get("ID", "")
        stage_status = row.get("状态", "")
        if not WORKSTREAM_STAGE_ID_RE.match(stage_id):
            errors.append(f"{rel}: invalid workstream stage id `{stage_id}`")
        elif not workstream_stage_belongs_to(workstream_id, stage_id):
            errors.append(f"{rel}: workstream stage `{stage_id}` does not belong to {workstream_id}")
        if stage_id in stage_by_id:
            errors.append(f"{rel}: duplicate workstream stage id `{stage_id}`")
        stage_by_id[stage_id] = row
        if stage_status not in VALID_WORKSTREAM_STAGE_STATUSES:
            errors.append(f"{rel}: invalid workstream stage status `{stage_status}` for {stage_id}")
        evidence = row.get("证据")
        if strict and stage_status == "Done" and (required_field_missing(evidence) or evidence in {"无。", "待补充。"}):
            errors.append(f"{rel}: Done workstream stage `{stage_id}` missing evidence")
        if stage_status == "Active":
            active_stage_ids.append(stage_id)

    if isinstance(status, str) and status == "Active" and len(active_stage_ids) > 1:
        errors.append(f"{rel}: Active workstream has more than one Active stage")

    if isinstance(status, str) and status in {"Done", "Cancelled"} and active_stage_ids:
        errors.append(f"{rel}: terminal workstream has Active stage `{active_stage_ids[0]}`")

    if not isinstance(current_stage, str) or not current_stage.strip():
        return
    current_stage = current_stage.strip()
    if not WORKSTREAM_STAGE_ID_RE.match(current_stage):
        errors.append(f"{rel}: invalid current_stage `{current_stage}`")
        return
    if not workstream_stage_belongs_to(workstream_id, current_stage):
        errors.append(f"{rel}: current_stage `{current_stage}` does not belong to {workstream_id}")
        return
    current_row = stage_by_id.get(current_stage)
    if current_row is None:
        errors.append(f"{rel}: current_stage `{current_stage}` is not registered in `## 阶段`")
        return
    current_status = current_row.get("状态", "")
    if current_status in {"Done", "Cancelled", "Skipped"}:
        errors.append(f"{rel}: current_stage `{current_stage}` has terminal status `{current_status}`")
    if isinstance(status, str) and status in {"Done", "Cancelled"} and current_status not in {"Done", "Cancelled", "Skipped"}:
        errors.append(f"{rel}: terminal workstream has non-terminal current_stage `{current_stage}` ({current_status})")


def check_workstream_state_requirements(
    root: Path,
    detail: WorkstreamDetail,
    entry: WorkstreamEntry | None,
    errors: list[str],
    warnings: list[str],
    strict: bool,
) -> None:
    rel = detail.path.relative_to(root).as_posix()
    status = detail.metadata.get("status")
    if not isinstance(status, str):
        return
    merge_targets = detail.metadata.get("merge_targets")
    has_merge_targets = isinstance(merge_targets, list) and any(str(target).strip() for target in merge_targets)
    if status == "Active":
        for field_name in ("owner", "title", "read_scope", "write_scope"):
            if required_field_missing(detail.metadata.get(field_name)):
                errors.append(f"{rel}: Active workstream missing `{field_name}`")
        if workstream_section_missing(detail.body, "## 目标"):
            errors.append(f"{rel}: Active workstream missing `目标`")
        output_missing = required_field_missing(entry.output if entry else None) or (entry is not None and entry.output in {"无。", "待补充。"})
        if output_missing and workstream_section_missing(detail.body, "## 输出物"):
            errors.append(f"{rel}: Active workstream missing `输出物`")
    elif status == "Blocked":
        if workstream_section_missing(detail.body, "## 阻塞原因"):
            errors.append(f"{rel}: Blocked workstream missing blocker reason")
    elif status == "ReadyToMerge":
        if has_merge_targets and not merge_request_has_required_fields(detail.body):
            errors.append(f"{rel}: ReadyToMerge workstream declares merge_targets but is missing merge request")
        if not merge_request_has_required_fields(detail.body):
            errors.append(f"{rel}: ReadyToMerge workstream missing merge target or candidate summary")
    elif status == "Done":
        if has_merge_targets and not merge_request_has_required_fields(detail.body):
            errors.append(f"{rel}: Done workstream declares merge_targets but is missing merge request")
        if workstream_section_missing(detail.body, "## 证据"):
            errors.append(f"{rel}: Done workstream missing evidence")
        if required_field_missing(detail.metadata.get("merge_resolution")):
            errors.append(f"{rel}: Done workstream missing merge_resolution")
    elif status == "Cancelled":
        if workstream_section_missing(detail.body, "## 取消原因"):
            errors.append(f"{rel}: Cancelled workstream missing cancellation reason")
    if status in {"Done", "Cancelled"}:
        keep_reason = detail.metadata.get("keep_active_reason")
        keep_until = detail.metadata.get("keep_active_until")
        if required_field_missing(keep_reason):
            warnings.append(f"{rel}: terminal workstream remains active without keep_active_reason")
        if required_field_missing(keep_until):
            warnings.append(f"{rel}: terminal workstream remains active without keep_active_until")
        elif not isinstance(keep_until, str) or not DATE_RE.match(keep_until):
            errors.append(f"{rel}: invalid keep_active_until `{keep_until}`")
        elif strict:
            keep_until_date = date.fromisoformat(keep_until)
            if keep_until_date < date.today():
                errors.append(f"{rel}: keep_active_until `{keep_until}` is expired")


def check_workstream_scope_claims(root: Path, details: Sequence[WorkstreamDetail], errors: list[str], warnings: list[str], strict: bool) -> None:
    exclusive_claims: list[tuple[str, str, str, str]] = []
    for detail in details:
        status = detail.metadata.get("status")
        write_scope = detail.metadata.get("write_scope")
        if not isinstance(write_scope, list):
            continue
        rel = detail.path.relative_to(root).as_posix()
        for item in write_scope:
            scope_type, scope_path = split_typed_scope(item)
            if not scope_type or not scope_path or scope_type not in {"authority", "draft", "owned", "assigned", "evidence"}:
                errors.append(f"{rel}: invalid write_scope `{item}`")
                continue
            normalized_path = normalize_scope_path(scope_path)
            diagnostics = validate_scope_path(normalized_path, "write_scope")
            for diagnostic in diagnostics:
                errors.append(f"{rel}: {diagnostic.code} (write_scope): {diagnostic.message}")
            if scope_type in {"assigned", "owned"} and is_authority_path(normalized_path):
                check_warn_or_error(
                    f"{rel}: {scope_type}: {normalized_path} targets an authority path; use merge_targets and a merge request instead",
                    errors,
                    warnings,
                    strict,
                )
            if scope_type == "owned" and normalized_path != workstream_detail_rel(detail.workstream_id):
                errors.append(f"{rel}: owned write_scope must point to its own detail file")
            if scope_type == "draft" and detail.workstream_id not in Path(normalized_path).name:
                check_warn_or_error(
                    f"{rel}: draft write_scope should include {detail.workstream_id} in the file name: {normalized_path}",
                    errors,
                    warnings,
                    strict,
                )
            if isinstance(status, str) and status in ACTIVE_WORKSTREAM_STATUSES and scope_type in {"authority", "assigned"}:
                exclusive_claims.append((detail.workstream_id, rel, scope_type, normalized_path))
    for index, (left_id, left_rel, left_type, left_path) in enumerate(exclusive_claims):
        for right_id, right_rel, right_type, right_path in exclusive_claims[index + 1 :]:
            if scope_paths_conflict(left_path, right_path):
                errors.append(
                    "active/Workstreams.md: write scope conflict "
                    f"{left_id} {left_type}:{left_path} vs {right_id} {right_type}:{right_path} "
                    f"({left_rel}, {right_rel})"
                )


def check_workstreams(root: Path, errors: list[str], warnings: list[str], strict: bool) -> None:
    index_path = workstream_index_path(root)
    if not index_path.exists():
        return
    details_dir = workstream_details_dir(root)
    if not details_dir.is_dir():
        errors.append(f"{WORKSTREAM_INDEX_REL}: active/workstreams/ directory is missing")

    try:
        entries = parse_workstream_index(root)
    except SystemExit as exc:
        errors.append(str(exc))
        return

    entry_by_id: dict[str, WorkstreamEntry] = {}
    details: list[WorkstreamDetail] = []
    for entry in entries:
        if entry.workstream_id in entry_by_id:
            errors.append(f"{WORKSTREAM_INDEX_REL}: duplicate Workstream id `{entry.workstream_id}`")
            continue
        entry_by_id[entry.workstream_id] = entry
        if not WORKSTREAM_ID_RE.match(entry.workstream_id):
            errors.append(f"{WORKSTREAM_INDEX_REL}: invalid Workstream id `{entry.workstream_id}`")
        if entry.status not in VALID_WORKSTREAM_STATUSES:
            errors.append(f"{WORKSTREAM_INDEX_REL}: invalid Workstream status `{entry.status}` for {entry.workstream_id}")
        try:
            detail_path = resolve_workstream_detail_path(root, entry.workstream_id, entries)
        except SystemExit as exc:
            errors.append(str(exc))
            continue
        if not detail_path.exists():
            errors.append(f"{WORKSTREAM_INDEX_REL}: broken Workstream detail `{entry.detail}` for {entry.workstream_id}")
            continue
        detail = parse_workstream_detail_for_check(root, entry.workstream_id, detail_path, errors)
        if detail is None:
            continue
        details.append(detail)
        detail_status = detail.metadata.get("status")
        if isinstance(detail_status, str) and detail_status != entry.status:
            check_warn_or_error(
                f"{WORKSTREAM_INDEX_REL}: status mismatch for {entry.workstream_id} ({entry.status}) vs detail ({detail_status})",
                errors,
                warnings,
                strict,
            )
        detail_title = detail.metadata.get("title")
        if isinstance(detail_title, str) and detail_title != entry.title:
            check_warn_or_error(
                f"{WORKSTREAM_INDEX_REL}: title mismatch for {entry.workstream_id} ({entry.title}) vs detail ({detail_title})",
                errors,
                warnings,
                strict,
            )
        detail_owner = detail.metadata.get("owner")
        if isinstance(detail_owner, str) and detail_owner != entry.owner:
            check_warn_or_error(
                f"{WORKSTREAM_INDEX_REL}: owner mismatch for {entry.workstream_id} ({entry.owner}) vs detail ({detail_owner})",
                errors,
                warnings,
                strict,
            )
        check_workstream_state_requirements(root, detail, entry, errors, warnings, strict)
        check_workstream_stage_focus(root, detail, errors, strict)

    if details_dir.is_dir():
        for path in sorted(details_dir.glob("WS*.md")):
            match = WORKSTREAM_ID_RE.match(path.stem)
            if match and path.stem not in entry_by_id:
                message = f"{path.relative_to(root).as_posix()}: Workstream detail is missing from {WORKSTREAM_INDEX_REL}"
                check_warn_or_error(message, errors, warnings, strict)

    check_workstream_scope_claims(root, details, errors, warnings, strict)


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

    for rel in required_files_for_check(path, profile):
        file_path = path / rel
        if not file_path.is_file():
            errors.append(f"missing file: {rel}")
            continue
        if file_path.stat().st_size == 0 and file_path.name != ".gitkeep":
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
    check_task_plan(path, errors)
    check_archive(path, errors)
    check_knowledge(path, errors, warnings, strict)
    check_workstreams(path, errors, warnings, strict)
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

        placeholders = [] if skip_placeholder_check(path, rel_file) else PLACEHOLDER_RE.findall(text)
        if placeholders:
            message = f"{rel_file}: contains {len(placeholders)} placeholder(s)"
            if strict:
                errors.append(message)
            elif not strict:
                warnings.append(message)
            if path.resolve() == TEMPLATE_DIR.resolve():
                legacy_count = legacy_placeholder_count(placeholders)
                if legacy_count:
                    warnings.append(
                        f"{rel_file}: contains {legacy_count} legacy placeholder(s); prefer `【ACF:KEY|提示】`"
                    )

        for ref in MARKDOWN_REF_RE.findall(text):
            if not should_check_ref(ref):
                continue
            if not is_linkify_path_candidate(ref):
                continue
            if resolve_ref(path, md_file, ref) is None:
                errors.append(f"{rel_file}: broken markdown reference `{ref}`")

        for _line_number, line in iter_non_fenced_lines(text):
            for link_match in MARKDOWN_LINK_RE.finditer(line):
                validate_local_markdown_link(path, md_file, rel_file, link_match.group(3), errors)

        warnings.extend(legacy_acf_marker_warnings(rel_file, text))

    return CheckResult(errors, warnings)


def check_command(args: argparse.Namespace) -> int:
    root = resolve_context_root(args.path)
    profile = args.profile or infer_context_profile(root)
    result = check_context(root, profile, args.strict)
    payload: dict[str, object] = {
        "command": "check",
        "context": str(root),
        "profile": profile,
        "strict": args.strict,
        "check": check_payload(result),
        "ok": result.ok,
        "error_code": check_error_code(result),
        "next_actions": check_next_actions(result, args.strict),
    }
    if not result.ok:
        payload["message"] = f"check failed: {len(result.errors)} error(s), {len(result.warnings)} warning(s)"
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
        return 0 if result.ok else 1

    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    for warning in result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    if result.ok:
        print(f"check passed: {root}")
        return 0
    print(f"check failed: {len(result.errors)} error(s), {len(result.warnings)} warning(s)", file=sys.stderr)
    return EXIT_CHECK_FAILED


def status_command(args: argparse.Namespace) -> int:
    location = resolve_status_location(args.path)
    profile = args.profile or location.profile
    task_path = location.context_root / "active" / "Current_Task.md"
    task_status = extract_current_task_status(task_path) if task_path.exists() else None
    result = check_context(location.context_root, profile, args.strict)
    payload: dict[str, object] = {
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
    if not result.ok:
        payload["message"] = f"check failed: {len(result.errors)} error(s), {len(result.warnings)} warning(s)"
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
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


def log_enable_command(args: argparse.Namespace) -> int:
    location = resolve_status_location(args.path)
    write_usage_config(location.project_root, True)
    payload: dict[str, object] = {
        "command": "log enable",
        "ok": True,
        "enabled": True,
        "project_root": str(location.project_root),
        "config_path": str(usage_config_path(location.project_root)),
        "log_path": str(usage_log_path(location.project_root)),
    }
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"usage log enabled: {usage_log_path(location.project_root)}")
    return 0


def log_disable_command(args: argparse.Namespace) -> int:
    location = resolve_status_location(args.path)
    write_usage_config(location.project_root, False)
    payload: dict[str, object] = {
        "command": "log disable",
        "ok": True,
        "enabled": False,
        "project_root": str(location.project_root),
        "config_path": str(usage_config_path(location.project_root)),
        "log_path": str(usage_log_path(location.project_root)),
    }
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"usage log disabled: {usage_log_path(location.project_root)}")
    return 0


def log_status_command(args: argparse.Namespace) -> int:
    location = resolve_status_location(args.path)
    payload = usage_log_status_payload(location.project_root)
    if json_enabled(args):
        print_json(payload)
    else:
        state = "enabled" if payload["enabled"] else "disabled"
        print(f"usage log: {state}")
        print(f"project root: {payload['project_root']}")
        print(f"log path: {payload['log_path']}")
        print(f"events: {payload['event_count']}")
        if payload["latest_event_at"]:
            print(f"latest event: {payload['latest_event_at']}")
    return 0


def log_tail_command(args: argparse.Namespace) -> int:
    if args.limit < 0:
        raise SystemExit("log tail limit cannot be negative")
    location = resolve_status_location(args.path)
    events = read_usage_events(location.project_root)
    tail_events = events[-args.limit :] if args.limit else []
    payload: dict[str, object] = {
        "command": "log tail",
        "ok": True,
        "project_root": str(location.project_root),
        "log_path": str(usage_log_path(location.project_root)),
        "limit": args.limit,
        "event_count": len(tail_events),
        "events": tail_events,
    }
    if json_enabled(args):
        print_json(payload)
    else:
        for event in tail_events:
            print(json.dumps(event, ensure_ascii=False, sort_keys=True))
    return 0


def log_summarize_command(args: argparse.Namespace) -> int:
    if args.days is not None and args.days < 0:
        raise SystemExit("log summarize days cannot be negative")
    location = resolve_status_location(args.path)
    events = read_usage_events(location.project_root)
    since = parse_usage_since(args.since) if args.since else None
    if args.days is not None:
        days_since = datetime.now(timezone.utc) - timedelta(days=args.days)
        since = max(since, days_since) if since is not None else days_since
    filtered_events = filter_usage_events(events, since=since, commands=args.command_filter or (), errors_only=args.errors_only)
    payload: dict[str, object] = {
        "command": "log summarize",
        "ok": True,
        "project_root": str(location.project_root),
        "log_path": str(usage_log_path(location.project_root)),
        "filters": {
            "days": args.days,
            "since": args.since,
            "command": args.command_filter or [],
            "errors_only": args.errors_only,
        },
        "total_event_count": len(events),
        **summarize_usage_events(filtered_events),
    }
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"events: {payload['event_count']}")
        print(f"ok: {payload['ok_count']}")
        print(f"failed: {payload['failed_count']}")
        print(f"dry-run: {payload['dry_run_count']}")
        print(f"changed files: {payload['changed_files_count']}")
        print("commands:")
        for command, count in sorted(payload["command_counts"].items()):
            print(f"- {command}: {count}")
        if payload["error_counts"]:
            print("errors:")
            for error_code, count in sorted(payload["error_counts"].items()):
                print(f"- {error_code}: {count}")
    return 0


def read_log_feedback_input(args: argparse.Namespace) -> str:
    if args.text and args.input:
        raise SystemExit("use either --text or --input, not both")
    if args.text:
        return args.text
    if args.input:
        input_path = args.input.resolve()
        if not input_path.is_file():
            raise SystemExit(f"log feedback input file does not exist: {input_path}")
        return input_path.read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("log feedback requires --text, --input, or stdin")


def log_feedback_command(args: argparse.Namespace) -> int:
    location = resolve_status_location(args.path)
    if not usage_log_enabled(location.project_root):
        raise SystemExit("usage log is disabled for this project")
    text = read_log_feedback_input(args).strip()
    if not text:
        raise SystemExit("log feedback text cannot be empty")
    feedback_type = (args.type or "Feedback").strip() or "Feedback"
    source = (args.source or "manual").strip() or "manual"
    event: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "timestamp": utc_now_iso(),
        "event_kind": "feedback",
        "command": "log feedback",
        "cwd_rel": relative_display_path(Path.cwd().resolve(), location.project_root),
        "context_rel": relative_display_path(location.context_root, location.project_root),
        "profile": location.profile,
        "ok": True,
        "exit_code": 0,
        "error_code": None,
        "feedback_type": feedback_type,
        "source": source,
        "text": text,
    }
    if args.related_command:
        event["related_command"] = args.related_command.strip()
    append_usage_event(location.project_root, event)
    payload: dict[str, object] = {
        "command": "log feedback",
        "ok": True,
        "project_root": str(location.project_root),
        "log_path": str(usage_log_path(location.project_root)),
        "feedback_type": feedback_type,
        "source": source,
        "message": "recorded feedback event",
        "event": event,
    }
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"recorded feedback: {feedback_type}")
        print(f"log path: {payload['log_path']}")
    return 0


def log_prune_command(args: argparse.Namespace) -> int:
    if args.days < 0:
        raise SystemExit("log prune days cannot be negative")
    location = resolve_status_location(args.path)
    log_path = usage_log_path(location.project_root)
    events = read_usage_events(location.project_root)
    if args.days <= 0:
        kept_events: list[dict[str, object]] = []
    else:
        threshold = datetime.now(timezone.utc) - timedelta(days=args.days)
        kept_events = [
            event
            for event in events
            if (parse_usage_timestamp(event.get("timestamp")) or threshold) >= threshold
        ]
    removed_count = len(events) - len(kept_events)
    if events or log_path.exists():
        write_usage_events(location.project_root, kept_events)
    payload: dict[str, object] = {
        "command": "log prune",
        "ok": True,
        "project_root": str(location.project_root),
        "log_path": str(log_path),
        "days": args.days,
        "removed_count": removed_count,
        "kept_count": len(kept_events),
    }
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"removed events: {removed_count}")
        print(f"kept events: {len(kept_events)}")
    return 0


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
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
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

    upgrade_parser = subparsers.add_parser(
        "upgrade",
        help="non-destructively add missing files for the current context schema",
        description=(
            "Upgrade an existing AI context to the current schema by adding missing "
            "Feedback_Inbox, Task_Plan, archive, archive/feedback, and Knowledge files/directories. "
            "This command does "
            "not move old content, archive active tasks, or overwrite an Active "
            "Current_Task.md. Use --dry-run --json first to review changed_files."
        ),
    )
    upgrade_parser.add_argument("path", nargs="?", type=Path)
    add_write_arguments(upgrade_parser)
    upgrade_parser.set_defaults(func=upgrade_command)

    check_parser = subparsers.add_parser("check", help="check context completeness")
    check_parser.add_argument("path", nargs="?", type=Path)
    check_parser.add_argument("--profile", choices=("standard", "minimal"), default=None)
    check_parser.add_argument("--strict", action="store_true", help="treat placeholders as errors")
    add_json_argument(check_parser)
    check_parser.set_defaults(func=check_command)

    linkify_parser = subparsers.add_parser(
        "linkify",
        help="convert path references in context Markdown files to clickable Markdown links",
    )
    linkify_parser.add_argument("path", nargs="?", type=Path)
    linkify_parser.add_argument("--format", choices=("markdown",), default="markdown")
    linkify_parser.add_argument("--include-archive", action="store_true", help="also linkify archive detail files")
    linkify_parser.add_argument(
        "--include-worklog-daily",
        action="store_true",
        help="also linkify daily worklog files",
    )
    linkify_parser.add_argument("--allow-missing", action="store_true", help="linkify paths even when targets do not exist")
    add_write_arguments(linkify_parser)
    linkify_parser.set_defaults(func=linkify_command)

    link_parser = subparsers.add_parser("link", help="manage explicit Markdown links")
    link_subparsers = link_parser.add_subparsers(dest="link_command", required=True)

    link_add_parser = link_subparsers.add_parser("add", help="append a Markdown link bullet to a section")
    link_add_parser.add_argument("path", nargs="?", type=Path)
    link_add_parser.add_argument("file", type=Path, help="Markdown file inside the context root")
    link_add_parser.add_argument("--heading", required=True, help="exact section heading to append to")
    link_add_parser.add_argument("--target", type=Path, required=True, help="local target file inside the context root")
    link_add_parser.add_argument("--target-heading", default=None, help="target Markdown heading to link to")
    link_add_parser.add_argument("--text", default=None, help="link text; defaults to target path plus anchor")
    link_add_parser.add_argument("--force", action="store_true", help="allow duplicate links")
    add_write_arguments(link_add_parser)
    link_add_parser.set_defaults(func=link_add_command)

    log_parser = subparsers.add_parser("log", help="manage global acf usage logs")
    log_subparsers = log_parser.add_subparsers(dest="log_command", required=True)

    log_enable_parser = log_subparsers.add_parser("enable", help="enable user-global usage logging for this project")
    log_enable_parser.add_argument("path", nargs="?", type=Path, help="context path or a directory inside a project")
    add_json_argument(log_enable_parser)
    log_enable_parser.set_defaults(func=log_enable_command)

    log_disable_parser = log_subparsers.add_parser("disable", help="disable user-global usage logging for this project")
    log_disable_parser.add_argument("path", nargs="?", type=Path, help="context path or a directory inside a project")
    add_json_argument(log_disable_parser)
    log_disable_parser.set_defaults(func=log_disable_command)

    log_status_parser = log_subparsers.add_parser("status", help="show usage log status")
    log_status_parser.add_argument("path", nargs="?", type=Path, help="context path or a directory inside a project")
    add_json_argument(log_status_parser)
    log_status_parser.set_defaults(func=log_status_command)

    log_tail_parser = log_subparsers.add_parser("tail", help="show recent usage events")
    log_tail_parser.add_argument("path", nargs="?", type=Path, help="context path or a directory inside a project")
    log_tail_parser.add_argument("--limit", type=int, default=20, help="number of recent events to show")
    add_json_argument(log_tail_parser)
    log_tail_parser.set_defaults(func=log_tail_command)

    log_summarize_parser = log_subparsers.add_parser("summarize", help="summarize usage events")
    log_summarize_parser.add_argument("path", nargs="?", type=Path, help="context path or a directory inside a project")
    log_summarize_parser.add_argument("--days", type=int, default=None, help="summarize events from this many recent days")
    log_summarize_parser.add_argument("--since", default=None, help="summarize events since YYYY-MM-DD or ISO timestamp")
    log_summarize_parser.add_argument("--command", dest="command_filter", action="append", default=None, help="only include an exact command label; can be repeated")
    log_summarize_parser.add_argument("--errors-only", action="store_true", help="only include failed events")
    add_json_argument(log_summarize_parser)
    log_summarize_parser.set_defaults(func=log_summarize_command)

    log_feedback_parser = log_subparsers.add_parser("feedback", help="record explicit user feedback in the usage log")
    log_feedback_parser.add_argument("path", nargs="?", type=Path, help="context path or a directory inside a project")
    log_feedback_parser.add_argument("--text", default=None, help="feedback text to record explicitly")
    log_feedback_parser.add_argument("--input", type=Path, default=None, help="file containing feedback text")
    log_feedback_parser.add_argument("--type", default="Feedback", help="feedback type, for example Problem, Request, or UX")
    log_feedback_parser.add_argument("--source", default="manual", help="feedback source label")
    log_feedback_parser.add_argument("--related-command", default=None, help="optional related command label")
    add_json_argument(log_feedback_parser)
    log_feedback_parser.set_defaults(func=log_feedback_command)

    log_prune_parser = log_subparsers.add_parser("prune", help="remove old usage events")
    log_prune_parser.add_argument("path", nargs="?", type=Path, help="context path or a directory inside a project")
    log_prune_parser.add_argument("--days", type=int, default=30, help="keep events from this many recent days")
    add_json_argument(log_prune_parser)
    log_prune_parser.set_defaults(func=log_prune_command)

    version_parser = subparsers.add_parser("version", help="show or update project version metadata")
    version_subparsers = version_parser.add_subparsers(dest="version_command", required=True)

    version_show_parser = version_subparsers.add_parser("show", help="show version values from project files")
    add_json_argument(version_show_parser)
    version_show_parser.set_defaults(func=version_show_command)

    version_set_parser = version_subparsers.add_parser("set", help="update CLI and package version files")
    version_set_parser.add_argument("value", help="version value, for example v0.0.3.6")
    add_write_arguments(version_set_parser)
    version_set_parser.set_defaults(func=version_set_command)

    workstream_parser = subparsers.add_parser("workstream", help="manage optional parallel Workstream metadata")
    workstream_subparsers = workstream_parser.add_subparsers(dest="workstream_command", required=True)

    workstream_init_parser = workstream_subparsers.add_parser("init", help="enable the optional Workstream layer")
    workstream_init_parser.add_argument("path", nargs="?", type=Path)
    add_write_arguments(workstream_init_parser)
    workstream_init_parser.set_defaults(func=workstream_init_command)

    workstream_status_parser = workstream_subparsers.add_parser("status", help="show Workstream layer status")
    workstream_status_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_status_parser)
    workstream_status_parser.set_defaults(func=workstream_status_command)

    workstream_list_parser = workstream_subparsers.add_parser("list", help="list Workstream index entries")
    workstream_list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_list_parser)
    workstream_list_parser.set_defaults(func=workstream_list_command)

    workstream_archive_candidates_parser = workstream_subparsers.add_parser(
        "archive-candidates",
        help="report terminal Workstreams that can be considered for archive",
    )
    workstream_archive_candidates_parser.add_argument("path", nargs="?", type=Path)
    workstream_archive_candidates_parser.add_argument("--today", default=None, help="override current date for keep-active checks")
    add_json_argument(workstream_archive_candidates_parser)
    workstream_archive_candidates_parser.set_defaults(func=workstream_archive_candidates_command)

    workstream_archive_draft_parser = workstream_subparsers.add_parser(
        "archive-draft",
        help="create a reviewable Workstream archive draft",
    )
    workstream_archive_draft_parser.add_argument("path", nargs="?", type=Path)
    workstream_archive_draft_parser.add_argument("--date", default=None, help="draft date in YYYY-MM-DD; defaults to today")
    workstream_archive_draft_parser.add_argument("--name", type=validate_draft_name, default=None, help="optional draft name suffix")
    workstream_archive_draft_parser.add_argument("--force", action="store_true", help="replace an existing archive draft")
    add_write_arguments(workstream_archive_draft_parser)
    workstream_archive_draft_parser.set_defaults(func=workstream_archive_draft_command)

    workstream_archive_parser = workstream_subparsers.add_parser(
        "archive",
        help="archive one terminal Workstream detail and update indexes",
    )
    workstream_archive_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_archive_parser.add_argument("path", nargs="?", type=Path)
    workstream_archive_parser.add_argument("--reason", default=None, help="archive reason, usually referencing an archive draft")
    workstream_archive_parser.add_argument("--date", default=None, help="archive date in YYYY-MM-DD; defaults to today")
    add_write_arguments(workstream_archive_parser)
    workstream_archive_parser.set_defaults(func=workstream_archive_command)

    workstream_sync_parser = workstream_subparsers.add_parser("sync", help="sync Workstreams index rows from detail front matter")
    workstream_sync_parser.add_argument("path", nargs="?", type=Path)
    add_write_arguments(workstream_sync_parser)
    workstream_sync_parser.set_defaults(func=workstream_sync_command)

    workstream_stage_parser = workstream_subparsers.add_parser("stage", help="manage Workstream internal stages")
    workstream_stage_subparsers = workstream_stage_parser.add_subparsers(dest="workstream_stage_command", required=True)

    workstream_stage_add_parser = workstream_stage_subparsers.add_parser("add", help="register a Workstream internal stage")
    workstream_stage_add_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS004")
    workstream_stage_add_parser.add_argument("path", nargs="?", type=Path)
    workstream_stage_add_parser.add_argument("--id", dest="stage_id", type=validate_workstream_stage_id, required=True, help="stage id, for example WS004.2")
    workstream_stage_add_parser.add_argument("--title", required=True, help="stage title")
    workstream_stage_add_parser.add_argument("--depends", default="无。", help="stage dependencies")
    workstream_stage_add_parser.add_argument("--output", default="待补充。", help="expected stage output")
    workstream_stage_add_parser.add_argument("--next-action", default="待推进。", help="stage next action")
    add_write_arguments(workstream_stage_add_parser)
    workstream_stage_add_parser.set_defaults(func=workstream_stage_add_command)

    workstream_stage_list_parser = workstream_stage_subparsers.add_parser("list", help="list Workstream internal stages")
    workstream_stage_list_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS004")
    workstream_stage_list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_stage_list_parser)
    workstream_stage_list_parser.set_defaults(func=workstream_stage_list_command)

    workstream_stage_done_parser = workstream_stage_subparsers.add_parser("done", help="mark a Workstream internal stage done")
    workstream_stage_done_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS004")
    workstream_stage_done_parser.add_argument("stage_id", type=validate_workstream_stage_id, help="stage id, for example WS004.2")
    workstream_stage_done_parser.add_argument("path", nargs="?", type=Path)
    workstream_stage_done_parser.add_argument("--evidence", default=None, help="stage completion evidence")
    workstream_stage_done_parser.add_argument("--clear-current", action="store_true", help="clear current_stage when completing the focused stage")
    workstream_stage_done_parser.add_argument("--next-action", default=None, help="optional replacement next action")
    add_write_arguments(workstream_stage_done_parser)
    workstream_stage_done_parser.set_defaults(func=workstream_stage_done_command)

    workstream_focus_parser = workstream_subparsers.add_parser("focus", help="focus a Workstream on a registered internal stage")
    workstream_focus_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS004")
    workstream_focus_parser.add_argument("stage_id", type=validate_workstream_stage_id, help="stage id, for example WS004.2")
    workstream_focus_parser.add_argument("path", nargs="?", type=Path)
    add_write_arguments(workstream_focus_parser)
    workstream_focus_parser.set_defaults(func=workstream_focus_command)

    workstream_show_parser = workstream_subparsers.add_parser("show", help="show a Workstream detail file")
    workstream_show_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_show_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_show_parser)
    workstream_show_parser.set_defaults(func=workstream_show_command)

    workstream_add_parser = workstream_subparsers.add_parser("add", help="create a Workstream detail and index row")
    workstream_add_parser.add_argument("path", nargs="?", type=Path)
    workstream_add_parser.add_argument("--id", type=validate_workstream_id, required=True, help="Workstream id, for example WS002")
    workstream_add_parser.add_argument("--title", required=True, help="Workstream title")
    workstream_add_parser.add_argument("--owner", required=True, help="Workstream owner")
    workstream_add_parser.add_argument("--depends-on", action="append", default=None, help="dependency id; can be repeated")
    workstream_add_parser.add_argument("--read-scope", action="append", default=None, help="recommended read scope; can be repeated")
    workstream_add_parser.add_argument("--write-scope", action="append", default=None, help="typed write scope, for example `assigned: active/Current_Task.md`; can be repeated")
    workstream_add_parser.add_argument("--output", default="待补充。", help="expected output summary")
    workstream_add_parser.add_argument("--goal", default=None, help="goal text written to the Workstream detail")
    add_write_arguments(workstream_add_parser)
    workstream_add_parser.set_defaults(func=workstream_add_command)

    workstream_set_parser = workstream_subparsers.add_parser("set", help="set Workstream status through allowed transitions")
    workstream_set_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_set_parser.add_argument("path", nargs="?", type=Path)
    workstream_set_parser.add_argument("--status", choices=tuple(sorted(VALID_WORKSTREAM_STATUSES)), default=None)
    workstream_set_parser.add_argument("--goal", default=None, help="replace the Workstream goal section")
    add_write_arguments(workstream_set_parser)
    workstream_set_parser.set_defaults(func=workstream_set_command)

    workstream_block_parser = workstream_subparsers.add_parser("block", help="mark a Workstream blocked")
    workstream_block_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_block_parser.add_argument("path", nargs="?", type=Path)
    workstream_block_parser.add_argument("--reason", default=None, help="blocker reason")
    add_write_arguments(workstream_block_parser)
    workstream_block_parser.set_defaults(func=workstream_block_command)

    workstream_cancel_parser = workstream_subparsers.add_parser("cancel", help="cancel a Workstream")
    workstream_cancel_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_cancel_parser.add_argument("path", nargs="?", type=Path)
    workstream_cancel_parser.add_argument("--reason", default=None, help="cancellation reason")
    add_write_arguments(workstream_cancel_parser)
    workstream_cancel_parser.set_defaults(func=workstream_cancel_command)

    workstream_merge_parser = workstream_subparsers.add_parser("merge-request", help="write a reviewable merge request section")
    workstream_merge_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_merge_parser.add_argument("path", nargs="?", type=Path)
    workstream_merge_parser.add_argument("--target", action="append", required=True, help="merge target; can be repeated")
    workstream_merge_parser.add_argument("--summary", default=None, help="candidate change summary")
    workstream_merge_parser.add_argument("--verification", required=True, help="verification result")
    workstream_merge_parser.add_argument("--question", action="append", default=None, help="open question; can be repeated")
    workstream_merge_parser.add_argument("--conflict", action="append", default=None, help="known conflict; can be repeated")
    workstream_merge_parser.add_argument("--strategy", default="", help="suggested merge strategy")
    workstream_merge_parser.add_argument("--input", type=Path, default=None, help="file containing candidate change summary")
    add_write_arguments(workstream_merge_parser)
    workstream_merge_parser.set_defaults(func=workstream_merge_request_command)

    workstream_ready_parser = workstream_subparsers.add_parser("ready", help="mark a Workstream ReadyToMerge")
    workstream_ready_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_ready_parser.add_argument("path", nargs="?", type=Path)
    add_write_arguments(workstream_ready_parser)
    workstream_ready_parser.set_defaults(func=workstream_ready_command)

    workstream_done_parser = workstream_subparsers.add_parser("done", help="mark a ReadyToMerge Workstream done")
    workstream_done_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_done_parser.add_argument("path", nargs="?", type=Path)
    workstream_done_parser.add_argument("--evidence", default=None, help="completion evidence")
    workstream_done_parser.add_argument(
        "--merge-resolution",
        choices=tuple(sorted(VALID_MERGE_RESOLUTIONS)),
        default=None,
        help="final merge outcome: merged, rejected, no_merge_required, or archived",
    )
    workstream_done_parser.add_argument("--summary", default=None, help="optional completion record")
    add_write_arguments(workstream_done_parser)
    workstream_done_parser.set_defaults(func=workstream_done_command)

    workstream_claim_parser = workstream_subparsers.add_parser("claim", help="append Workstream read/write scope claims")
    workstream_claim_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_claim_parser.add_argument("path", nargs="?", type=Path)
    workstream_claim_parser.add_argument("--read", action="append", default=None, help="read scope path; can be repeated")
    workstream_claim_parser.add_argument("--write", action="append", default=None, help="typed write scope; can be repeated")
    add_write_arguments(workstream_claim_parser)
    workstream_claim_parser.set_defaults(func=workstream_claim_command)

    workstream_note_parser = workstream_subparsers.add_parser("note", help="append a note to a Workstream detail section")
    workstream_note_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_note_parser.add_argument("path", nargs="?", type=Path)
    workstream_note_parser.add_argument("--section", required=True, help="allowed note section")
    workstream_note_parser.add_argument("--text", default=None, help="note text")
    workstream_note_parser.add_argument("--input", type=Path, default=None, help="file containing note text")
    add_write_arguments(workstream_note_parser)
    workstream_note_parser.set_defaults(func=workstream_note_command)

    plan_parser = subparsers.add_parser("plan", help="manage active/Task_Plan.md")
    plan_subparsers = plan_parser.add_subparsers(dest="plan_command", required=True)

    plan_init_parser = plan_subparsers.add_parser("init", help="create or replace the active task plan")
    plan_init_parser.add_argument("path", nargs="?", type=Path)
    plan_init_parser.add_argument("--title", required=True, help="large task title")
    plan_init_parser.add_argument("--goal", action="append", required=True, help="large task goal; can be repeated")
    plan_init_parser.add_argument("--success", action="append", default=None, help="success criterion; can be repeated")
    plan_init_parser.add_argument("--force", action="store_true", help="replace an Active task plan")
    add_write_arguments(plan_init_parser)
    plan_init_parser.set_defaults(func=plan_init_command)

    plan_add_parser = plan_subparsers.add_parser("add-task", help="add a subtask to active/Task_Plan.md")
    plan_add_parser.add_argument("path", nargs="?", type=Path)
    plan_add_parser.add_argument("--id", type=validate_task_id, default=None, help="subtask id, for example T001")
    plan_add_parser.add_argument("--title", required=True, help="subtask title")
    plan_add_parser.add_argument("--depends", default="无。", help="dependency summary")
    plan_add_parser.add_argument("--output", default="无。", help="expected output")
    plan_add_parser.add_argument("--next-action", default="无。", help="next action")
    add_write_arguments(plan_add_parser)
    plan_add_parser.set_defaults(func=plan_add_task_command)

    plan_set_parser = plan_subparsers.add_parser("set-task", help="update a subtask row")
    plan_set_parser.add_argument("path", nargs="?", type=Path)
    plan_set_parser.add_argument("--id", type=validate_task_id, required=True, help="subtask id")
    plan_set_parser.add_argument("--status", choices=tuple(sorted(VALID_SUBTASK_STATUSES)), default=None)
    plan_set_parser.add_argument("--title", default=None)
    plan_set_parser.add_argument("--depends", default=None)
    plan_set_parser.add_argument("--output", default=None)
    plan_set_parser.add_argument("--evidence", default=None)
    plan_set_parser.add_argument("--next-action", default=None)
    add_write_arguments(plan_set_parser)
    plan_set_parser.set_defaults(func=plan_set_task_command)

    plan_focus_parser = plan_subparsers.add_parser("focus", help="set the current plan focus")
    plan_focus_parser.add_argument("path", nargs="?", type=Path)
    plan_focus_parser.add_argument("--id", type=validate_task_id, required=True, help="subtask id")
    add_write_arguments(plan_focus_parser)
    plan_focus_parser.set_defaults(func=plan_focus_command)

    plan_complete_parser = plan_subparsers.add_parser("complete", help="mark the task plan Done")
    plan_complete_parser.add_argument("path", nargs="?", type=Path)
    plan_complete_parser.add_argument("--force", action="store_true", help="complete even when subtasks are unfinished")
    add_write_arguments(plan_complete_parser)
    plan_complete_parser.set_defaults(func=plan_complete_command)

    plan_status_parser = plan_subparsers.add_parser("status", help="show task plan status")
    plan_status_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(plan_status_parser)
    plan_status_parser.set_defaults(func=plan_status_command)

    plan_reference_parser = plan_subparsers.add_parser("reference", help="manage plan reference basis entries")
    plan_reference_subparsers = plan_reference_parser.add_subparsers(dest="plan_reference_command", required=True)

    plan_reference_list_parser = plan_reference_subparsers.add_parser("list", help="list plan reference basis entries")
    plan_reference_list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(plan_reference_list_parser)
    plan_reference_list_parser.set_defaults(func=plan_reference_list_command)

    plan_reference_add_parser = plan_reference_subparsers.add_parser("add", help="add or update a plan reference basis entry")
    plan_reference_add_parser.add_argument("path", nargs="?", type=Path)
    plan_reference_add_parser.add_argument("--path", dest="ref_path", required=True, help="reference/*.md path")
    plan_reference_add_parser.add_argument("--purpose", required=True, help="one-sentence purpose for this reference")
    plan_reference_add_parser.add_argument("--allow-missing", action="store_true", help="allow adding a reference file path that does not exist yet")
    plan_reference_add_parser.add_argument("--force", action="store_true", help="update an existing reference with the same path")
    plan_reference_add_parser.add_argument("--sync-current-task", action="store_true", help="also sync a standard bullet into an Active Current_Task input list")
    add_write_arguments(plan_reference_add_parser)
    plan_reference_add_parser.set_defaults(func=plan_reference_add_command)

    plan_reference_remove_parser = plan_reference_subparsers.add_parser("remove", help="remove a plan reference basis entry")
    plan_reference_remove_parser.add_argument("path", nargs="?", type=Path)
    plan_reference_remove_parser.add_argument("--path", dest="ref_path", required=True, help="reference/*.md path")
    plan_reference_remove_parser.add_argument("--missing-ok", action="store_true", help="exit successfully when the reference is already absent")
    plan_reference_remove_parser.add_argument("--sync-current-task", action="store_true", help="also remove the exact standard bullet from an Active Current_Task input list")
    add_write_arguments(plan_reference_remove_parser)
    plan_reference_remove_parser.set_defaults(func=plan_reference_remove_command)

    plan_stage_parser = plan_subparsers.add_parser("stage", help="manage task stages in active/Task_Plan.md")
    plan_stage_subparsers = plan_stage_parser.add_subparsers(dest="plan_stage_command", required=True)

    plan_stage_list_parser = plan_stage_subparsers.add_parser("list", help="list task stages")
    plan_stage_list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(plan_stage_list_parser)
    plan_stage_list_parser.set_defaults(func=plan_stage_list_command)

    plan_stage_add_parser = plan_stage_subparsers.add_parser("add", help="add a task stage row")
    plan_stage_add_parser.add_argument("path", nargs="?", type=Path)
    plan_stage_add_parser.add_argument("--id", type=validate_task_stage_id, required=True, help="task stage id, for example T001.1")
    plan_stage_add_parser.add_argument("--parent", type=validate_task_id, required=True, help="parent subtask id")
    plan_stage_add_parser.add_argument("--title", required=True, help="stage title")
    plan_stage_add_parser.add_argument("--workstream", default="无。", help="optional owning Workstream id")
    plan_stage_add_parser.add_argument("--depends", default="无。", help="dependency summary")
    plan_stage_add_parser.add_argument("--output", default="待补充。", help="expected output")
    plan_stage_add_parser.add_argument("--next-action", default="待推进。", help="next action")
    add_write_arguments(plan_stage_add_parser)
    plan_stage_add_parser.set_defaults(func=plan_stage_add_command)

    plan_stage_set_parser = plan_stage_subparsers.add_parser("set", help="update a task stage row")
    plan_stage_set_parser.add_argument("path", nargs="?", type=Path)
    plan_stage_set_parser.add_argument("--id", type=validate_task_stage_id, required=True, help="task stage id")
    plan_stage_set_parser.add_argument("--status", choices=tuple(sorted(VALID_SUBTASK_STATUSES)), default=None)
    plan_stage_set_parser.add_argument("--parent", type=validate_task_id, default=None)
    plan_stage_set_parser.add_argument("--title", default=None)
    plan_stage_set_parser.add_argument("--workstream", default=None)
    plan_stage_set_parser.add_argument("--depends", default=None)
    plan_stage_set_parser.add_argument("--output", default=None)
    plan_stage_set_parser.add_argument("--evidence", default=None)
    plan_stage_set_parser.add_argument("--next-action", default=None)
    add_write_arguments(plan_stage_set_parser)
    plan_stage_set_parser.set_defaults(func=plan_stage_set_command)

    plan_stage_done_parser = plan_stage_subparsers.add_parser("done", help="mark a task stage Done")
    plan_stage_done_parser.add_argument("path", nargs="?", type=Path)
    plan_stage_done_parser.add_argument("--id", type=validate_task_stage_id, required=True, help="task stage id")
    plan_stage_done_parser.add_argument("--evidence", required=True, help="completion evidence")
    plan_stage_done_parser.add_argument("--next-action", default=None)
    add_write_arguments(plan_stage_done_parser)
    plan_stage_done_parser.set_defaults(func=plan_stage_done_command)

    task_group_parser = subparsers.add_parser("task", help="start, finish, block, or clear the current task")
    task_subparsers = task_group_parser.add_subparsers(dest="task_command", required=True)

    task_start_parser = task_subparsers.add_parser("start", help="start a subtask from active/Task_Plan.md")
    task_start_parser.add_argument("path", nargs="?", type=Path)
    task_start_parser.add_argument("--id", type=validate_task_id, required=True, help="subtask id")
    task_start_parser.add_argument("--force", action="store_true", help="replace an Active current task")
    add_write_arguments(task_start_parser)
    task_start_parser.set_defaults(func=task_start_command)

    task_done_parser = task_subparsers.add_parser("done", help="mark a subtask done")
    task_done_parser.add_argument("path", nargs="?", type=Path)
    task_done_parser.add_argument("--id", type=validate_task_id, required=True, help="subtask id")
    task_done_parser.add_argument("--evidence", required=True, help="completion evidence")
    add_write_arguments(task_done_parser)
    task_done_parser.set_defaults(func=task_done_command)

    task_block_parser = task_subparsers.add_parser("block", help="mark a subtask blocked")
    task_block_parser.add_argument("path", nargs="?", type=Path)
    task_block_parser.add_argument("--id", type=validate_task_id, required=True, help="subtask id")
    task_block_parser.add_argument("--reason", required=True, help="blocker reason")
    add_write_arguments(task_block_parser)
    task_block_parser.set_defaults(func=task_block_command)

    task_clear_parser = task_subparsers.add_parser("clear", help="reset active/Current_Task.md to Empty")
    task_clear_parser.add_argument("path", nargs="?", type=Path)
    add_write_arguments(task_clear_parser)
    task_clear_parser.set_defaults(func=task_clear_command)

    archive_parser = subparsers.add_parser("archive", help="archive inactive task context")
    archive_subparsers = archive_parser.add_subparsers(dest="archive_command", required=True)

    archive_task_parser = archive_subparsers.add_parser("current-task", help="archive active/Current_Task.md")
    archive_task_parser.add_argument("path", nargs="?", type=Path)
    archive_task_parser.add_argument("--reason", required=True, help="archive reason")
    archive_task_parser.add_argument("--force", action="store_true", help="archive even when Active")
    add_write_arguments(archive_task_parser)
    archive_task_parser.set_defaults(func=archive_current_task_command)

    archive_plan_parser = archive_subparsers.add_parser("task-plan", help="archive active/Task_Plan.md")
    archive_plan_parser.add_argument("path", nargs="?", type=Path)
    archive_plan_parser.add_argument("--reason", required=True, help="archive reason")
    archive_plan_parser.add_argument("--force", action="store_true", help="archive even when Active")
    add_write_arguments(archive_plan_parser)
    archive_plan_parser.set_defaults(func=archive_task_plan_command)

    archive_list_parser = archive_subparsers.add_parser("list", help="list archive index entries")
    archive_list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(archive_list_parser)
    archive_list_parser.set_defaults(func=archive_list_command)

    knowledge_parser = subparsers.add_parser("knowledge", help="manage reusable knowledge drafts and entries")
    knowledge_subparsers = knowledge_parser.add_subparsers(dest="knowledge_command", required=True)

    knowledge_draft_parser = knowledge_subparsers.add_parser("draft", help="create a reviewable knowledge draft")
    knowledge_draft_parser.add_argument("path", nargs="?", type=Path)
    knowledge_draft_parser.add_argument("--title", required=True, help="knowledge title")
    knowledge_draft_parser.add_argument("--source", action="append", required=True, help="source path inside context; can be repeated")
    knowledge_draft_parser.add_argument("--tag", default="未分类", help="knowledge tags")
    knowledge_draft_parser.add_argument("--summary", default="待补充。", help="one-line summary")
    knowledge_draft_parser.add_argument("--force", action="store_true", help="replace existing draft")
    add_write_arguments(knowledge_draft_parser)
    knowledge_draft_parser.set_defaults(func=knowledge_draft_command)

    knowledge_apply_parser = knowledge_subparsers.add_parser("apply", help="apply a knowledge draft")
    knowledge_apply_parser.add_argument("draft", type=Path, help="draft path")
    knowledge_apply_parser.add_argument("path", nargs="?", type=Path, help="context path")
    knowledge_apply_parser.add_argument("--allow-similar", action="store_true", help="apply even when similar Knowledge exists")
    add_write_arguments(knowledge_apply_parser)
    knowledge_apply_parser.set_defaults(func=knowledge_apply_command)

    knowledge_list_parser = knowledge_subparsers.add_parser("list", help="list knowledge entries")
    knowledge_list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(knowledge_list_parser)
    knowledge_list_parser.set_defaults(func=knowledge_list_command)

    knowledge_show_parser = knowledge_subparsers.add_parser("show", help="show a knowledge entry")
    knowledge_show_parser.add_argument("path", nargs="?", type=Path)
    knowledge_show_parser.add_argument("--id", type=validate_knowledge_id, required=True, help="knowledge id")
    add_json_argument(knowledge_show_parser)
    knowledge_show_parser.set_defaults(func=knowledge_show_command)

    knowledge_mark_parser = knowledge_subparsers.add_parser("mark", help="mark knowledge status")
    knowledge_mark_parser.add_argument("path", nargs="?", type=Path)
    knowledge_mark_parser.add_argument("--id", type=validate_knowledge_id, required=True, help="knowledge id")
    knowledge_mark_parser.add_argument("--status", choices=tuple(sorted(VALID_KNOWLEDGE_STATUSES)), required=True)
    knowledge_mark_parser.add_argument("--promoted-to", default="", help="target authority when status is Promoted")
    add_write_arguments(knowledge_mark_parser)
    knowledge_mark_parser.set_defaults(func=knowledge_mark_command)

    review_parser = subparsers.add_parser("review", help="run read-only context review checks")
    review_subparsers = review_parser.add_subparsers(dest="review_command", required=True)

    review_stale_parser = review_subparsers.add_parser("stale", help="report stale attention-entry candidates")
    review_stale_parser.add_argument("path", nargs="?", type=Path)
    review_stale_parser.add_argument("--days", type=int, default=DEFAULT_STALE_DAYS, help="age threshold in days")
    review_stale_parser.add_argument("--today", type=validate_date, default=None, help="override today's date for deterministic checks")
    add_json_argument(review_stale_parser)
    review_stale_parser.set_defaults(func=review_stale_command)

    audit_parser = subparsers.add_parser("audit", help="run read-only context audit checks")
    audit_subparsers = audit_parser.add_subparsers(dest="audit_command", required=True)

    audit_context_parser = audit_subparsers.add_parser("context", help="report context audit candidates")
    audit_context_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(audit_context_parser)
    audit_context_parser.set_defaults(func=audit_context_command)

    curate_parser = subparsers.add_parser("curate", help="create attention governance drafts")
    curate_subparsers = curate_parser.add_subparsers(dest="curate_command", required=True)

    curate_draft_parser = curate_subparsers.add_parser("draft", help="draft curation notes from review stale signals")
    curate_draft_parser.add_argument("path", nargs="?", type=Path)
    curate_draft_parser.add_argument("--days", type=int, default=DEFAULT_STALE_DAYS, help="age threshold in days")
    curate_draft_parser.add_argument("--today", type=validate_date, default=None, help="override today's date for deterministic drafts")
    curate_draft_parser.add_argument("--name", type=validate_draft_name, default=None, help="draft file name without .md")
    add_write_arguments(curate_draft_parser)
    curate_draft_parser.set_defaults(func=curate_draft_command)

    new_parser = subparsers.add_parser("new", help="create context entries")
    new_subparsers = new_parser.add_subparsers(dest="entry_type", required=True)

    worklog_parser = new_subparsers.add_parser("worklog", help="create a daily worklog and index row")
    worklog_parser.add_argument("path", nargs="?", type=Path)
    worklog_parser.add_argument("--date", type=validate_date, default=None, help="date in YYYY-MM-DD format")
    worklog_parser.add_argument("--summary", required=True, help="one-line worklog summary")
    worklog_parser.add_argument("--conclusion", default="无。", help="one-line key conclusion")
    worklog_parser.add_argument("--append", action="store_true", help="append to an existing daily worklog")
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
    task_parser.add_argument("--plan", default="无。", help="parent task plan title or path")
    task_parser.add_argument("--task-id", default="无。", help="subtask id in active/Task_Plan.md")
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

    edit_parser = subparsers.add_parser("edit", help="safely edit context Markdown files")
    edit_subparsers = edit_parser.add_subparsers(dest="edit_target", required=True)

    section_parser = edit_subparsers.add_parser("section", help="get or update a Markdown section")
    section_subparsers = section_parser.add_subparsers(dest="section_command", required=True)

    section_get_parser = section_subparsers.add_parser("get", help="print a section body")
    section_get_parser.add_argument("file", type=Path, help="Markdown file inside the context root")
    section_get_parser.add_argument("--heading", required=True, help="exact Markdown heading, for example '## 当前阶段'")
    section_get_parser.add_argument("--context", type=Path, default=None, help="context root; omitted to auto-discover")
    add_json_argument(section_get_parser)
    section_get_parser.set_defaults(func=edit_section_get_command)

    section_replace_parser = section_subparsers.add_parser("replace", help="replace a section body")
    section_replace_parser.add_argument("file", type=Path, help="Markdown file inside the context root")
    section_replace_parser.add_argument("--heading", required=True, help="exact Markdown heading to replace")
    section_replace_parser.add_argument("--text", default=None, help="replacement text")
    section_replace_parser.add_argument("--input", type=Path, default=None, help="file containing replacement text")
    section_replace_parser.add_argument("--context", type=Path, default=None, help="context root; omitted to auto-discover")
    add_write_arguments(section_replace_parser)
    section_replace_parser.set_defaults(func=edit_section_replace_command)

    section_append_parser = section_subparsers.add_parser("append", help="append text to a section body")
    section_append_parser.add_argument("file", type=Path, help="Markdown file inside the context root")
    section_append_parser.add_argument("--heading", required=True, help="exact Markdown heading to append to")
    section_append_parser.add_argument("--text", default=None, help="text to append")
    section_append_parser.add_argument("--input", type=Path, default=None, help="file containing text to append")
    section_append_parser.add_argument("--context", type=Path, default=None, help="context root; omitted to auto-discover")
    add_write_arguments(section_append_parser)
    section_append_parser.set_defaults(func=edit_section_append_command)

    table_parser = edit_subparsers.add_parser("table", help="update Markdown tables")
    table_subparsers = table_parser.add_subparsers(dest="table_command", required=True)

    table_upsert_parser = table_subparsers.add_parser("upsert", help="insert or update a Markdown table row")
    table_upsert_parser.add_argument("file", type=Path, help="Markdown file inside the context root")
    table_upsert_parser.add_argument("--header", default=None, help="exact table header line; omitted to use first table")
    table_upsert_parser.add_argument("--key-column", required=True, help="column used as the row key")
    table_upsert_parser.add_argument("--key", required=True, help="key value to update or append")
    table_upsert_parser.add_argument("--cell", action="append", required=True, help="cell update as COLUMN=VALUE; can be repeated")
    table_upsert_parser.add_argument("--context", type=Path, default=None, help="context root; omitted to auto-discover")
    add_write_arguments(table_upsert_parser)
    table_upsert_parser.set_defaults(func=edit_table_upsert_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    started = time.perf_counter()
    args: argparse.Namespace | None = None
    exit_code = 0
    try:
        args = parser.parse_args(argv_list)
        exit_code = run_with_context_lock(args)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            exit_code = exc.code
        else:
            message = str(exc.code)
            error_code, exit_code = classify_cli_error(message)
            if args is not None:
                set_result_payload(
                    args,
                    {
                        "command": command_label(args),
                        "ok": False,
                        "error_code": error_code,
                        "message": message,
                        "next_actions": error_next_actions(error_code),
                    },
                )
            emit_cli_error(argv_list, message, error_code, exit_code)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        message = str(exc)
        exit_code = EXIT_RUNTIME_ERROR
        if args is not None:
            set_result_payload(
                args,
                {
                    "command": command_label(args),
                    "ok": False,
                    "error_code": "runtime_error",
                    "message": message,
                    "next_actions": error_next_actions("runtime_error"),
                },
            )
        emit_cli_error(argv_list, message, "runtime_error", exit_code)

    if args is not None:
        duration_ms = int((time.perf_counter() - started) * 1000)
        record_usage_event(args, exit_code, duration_ms)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
