#!/usr/bin/env python3
"""Small CLI for generating and checking AI context framework directories."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import inspect
import json
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from urllib.parse import unquote
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Sequence

from ai_context_framework.constants import (
    ANCHOR_NOT_FOUND,
    APPEND_FORCE_CONFLICT,
    EXIT_CHECK_FAILED,
    EXIT_INPUT_ERROR,
    EXIT_RUNTIME_ERROR,
    EXIT_SAFETY_REFUSED,
    JSON_SCHEMA_VERSION,
    LOCK_FILE_REL,
    TARGET_EXISTS_APPEND_REQUIRED,
)
from ai_context_framework.commands import versioning as versioning_commands
from ai_context_framework.commands import edit_link as edit_link_commands
from ai_context_framework.commands import worklog as worklog_commands
from ai_context_framework.commands import status_check as status_check_commands
from ai_context_framework.commands import init_upgrade as init_upgrade_commands
from ai_context_framework.commands import new_context as new_context_commands
from ai_context_framework.commands import decisions as decisions_commands
from ai_context_framework.commands import feedback as feedback_commands
from ai_context_framework.commands import human as human_commands
from ai_context_framework.commands import knowledge as knowledge_commands
from ai_context_framework.commands import links as links_commands
from ai_context_framework.commands import next_status as next_status_commands
from ai_context_framework.commands import archive as archive_commands
from ai_context_framework.commands import review_audit_curate as review_audit_curate_commands
from ai_context_framework.commands import doctor as doctor_commands
from ai_context_framework.commands import plan_task as plan_task_commands
from ai_context_framework.commands import workstream as workstream_commands
from ai_context_framework.commands import worktree as worktree_commands
from ai_context_framework.commands import continuation as continuation_commands, observer as observer_commands
from ai_context_framework.commands import continuation_coordination as continuation_coordination_commands
from ai_context_framework.commands.log import (
    build_usage_event,
    check_counts,
    command_label,
    log_disable_command,
    log_enable_command,
    log_feedback_command,
    log_issues_command,
    log_prune_command,
    log_status_command,
    log_summarize_command,
    log_tail_command,
    record_usage_event,
    relative_usage_paths,
    usage_loggable,
)
from ai_context_framework.commands.log_inventory import log_projects_command
from ai_context_framework.commands.edit_link import (
    LINKIFY_DEFAULT_DIRS,
    LINKIFY_DEFAULT_FILES,
    linkify_candidate_files,
    read_edit_input,
    resolve_context_file,
    resolve_context_markdown_file,
)
from ai_context_framework.commands.worklog import (
    append_worklog_cell,
    emit_worklog_error,
    emit_worklog_result,
    render_worklog_daily,
    row_date,
    update_worklog_index,
    update_worklog_index_append,
    worklog_index_row,
)
from ai_context_framework.commands.versioning import (
    installed_package_version,
    is_source_project_root,
    normalize_release_version,
    replace_regex_once,
)
from ai_context_framework.domains.tasks import (
    CURRENT_TASK_REFERENCE_PROMPT,
    PLAN_REFERENCE_BULLET_RE,
    PLAN_REFERENCE_EMPTY,
    PLAN_REFERENCE_HEADING,
    PLAN_REFERENCE_SECTION_INTRO,
    PLAN_REFERENCE_UPGRADE_PROMPT,
    current_task_has_active_status,
    normalize_plan_reference_path,
    normalize_plan_reference_purpose,
    parse_plan_references_from_body,
    read_plan_references,
    render_plan_reference,
    render_plan_reference_input,
    render_plan_reference_section,
    standard_reference_line_path,
    sync_current_task_reference_text,
    valid_plan_reference_input_lines,
    write_plan_references_text,
)
from ai_context_framework.front_matter import (
    diagnostic_codes,
    format_front_matter,
    parse_front_matter,
    required_field_missing,
    split_typed_scope,
    validate_front_matter,
    validate_scope_path,
)
from ai_context_framework.json_contract import (
    check_after_enabled,
    check_error_code,
    check_next_actions,
    check_payload,
    classify_cli_error,
    command_name_from_argv,
    dry_run_enabled,
    emit_cli_error,
    emit_write_result,
    error_next_actions,
    json_enabled,
    json_requested,
    path_values,
    print_json,
    set_result_payload,
    write_next_actions,
)
from ai_context_framework.locks import acquire_context_lock, lock_path_for_context, release_context_lock
from ai_context_framework.markers import (
    ACF_MARKER_RE,
    ACF_PLACEHOLDER_RE,
    ARCHIVE_INDEX_MARKER_END,
    ARCHIVE_INDEX_MARKER_START,
    ARCHIVE_RECORD_MARKER_END,
    ARCHIVE_RECORD_MARKER_START,
    DECISIONS_INDEX_MARKER_END,
    DECISIONS_INDEX_MARKER_START,
    KNOWLEDGE_INDEX_MARKER_END,
    KNOWLEDGE_INDEX_MARKER_START,
    LEGACY_UPGRADE_NOTES_END,
    LEGACY_UPGRADE_NOTES_START,
    LEGACY_WORKSTREAM_ARCHIVE_MARKER_END,
    LEGACY_WORKSTREAM_ARCHIVE_MARKER_START,
    PLACEHOLDER_RE,
    UPGRADE_NOTES_END,
    UPGRADE_NOTES_START,
    WORKSTREAM_ARCHIVE_MARKER_END,
    WORKSTREAM_ARCHIVE_MARKER_START,
    archive_record_marker,
    has_upgrade_notes_marker,
    has_workstream_archive_marker,
    insert_generated_marker_block_after_heading,
    is_acf_placeholder,
    legacy_acf_marker_warnings,
    legacy_placeholder_count,
    marker_fields,
    migrate_legacy_acf_markers,
    replace_generated_marker_block,
    workstream_archive_marker,
    workstream_archive_marker_fields,
)
from ai_context_framework.markdown import (
    MARKDOWN_LINK_RE,
    MARKDOWN_REF_RE,
    PATH_LIKE_RE,
    append_or_create_section,
    append_section_text,
    apply_section_body,
    clean_markdown_link_target,
    find_section,
    heading_level,
    insert_section_after,
    insert_section_before,
    is_local_link_ref,
    is_linkify_path_candidate,
    is_placeholder,
    is_uri_ref,
    iter_non_fenced_lines,
    linkify_markdown_text,
    markdown_link_target_for,
    markdown_heading_anchor_for,
    markdown_heading_anchors,
    markdown_heading_slug,
    markdown_sections,
    normalized_section_body_lines,
    normalize_ref_path,
    remove_markdown_section,
    replace_or_append_section,
    replace_section_text,
    render_markdown_link,
    render_markdown_link_target,
    resolve_ref,
    resolve_ref_path,
    rewrite_local_markdown_links_for_move,
    safe_section_body,
    safe_section_body_from_text,
    section_body,
    section_contains_child_heading,
    section_content_and_suffix,
    section_insert_after_line,
    should_check_ref,
    split_ref_fragment,
    strip_code_ticks,
    subsection_body,
    validate_local_markdown_link,
)
from ai_context_framework.models import (
    CheckResult,
    FrontMatterDiagnostic,
    FrontMatterSchema,
    KnowledgeEntry,
    PlanReference,
    SectionRange,
    TableRange,
    WorkstreamArchiveAssessment,
    WorkstreamDetail,
    WorkstreamEntry,
)
from ai_context_framework.observability import (
    atomic_write_text,
    usage_log_path,
    usage_lock_path,
)
from ai_context_framework.paths import (
    context_json_path,
    discover_context,
    display_path,
    infer_context_profile,
    infer_project_root,
    is_relative_to,
    is_context_root,
    make_context_location,
    relative_display_path,
    require_context_root,
    resolve_context_root,
    resolve_status_location,
    slugify_project_name,
)
from ai_context_framework.tables import (
    clean_table_cell,
    find_table,
    parse_cell_updates,
    parse_markdown_table_rows,
    render_table_row,
    split_table_line,
    table_cell,
    upsert_table_row,
)
from ai_context_framework.templates import (
    MINIMAL_DIRS,
    MINIMAL_FILES,
    STANDARD_DIRS,
    STANDARD_FILES,
    TEMPLATE_DIR,
    find_template_dir,
)
from ai_context_framework.validators.template_checks import (
    check_template_packaging,
    template_packaging_files_from_pyproject,
)
from ai_context_framework.validators.checks import (
    ADR_ID_RE,
    DATE_RE,
    DRAFT_NAME_RE,
    KNOWLEDGE_ID_RE,
    TASK_ID_RE,
    TASK_ID_TOKEN_RE,
    TASK_STAGE_ID_RE,
    TASK_STAGE_ID_TOKEN_RE,
    WORKSTREAM_ID_RE,
    WORKSTREAM_ID_TOKEN_RE,
    WORKSTREAM_STAGE_ID_RE,
    validate_adr_id,
    validate_date,
    validate_draft_name,
    validate_feedback_id,
    validate_human_note_id,
    validate_knowledge_id,
    validate_task_id,
    validate_task_stage_id,
    validate_workstream_id,
    validate_workstream_stage_id,
)
from ai_context_framework.version import VERSION


ROOT = Path(__file__).resolve().parents[1]

VALID_TASK_STATUSES = {"Active", "Paused", "Done", "Empty"}
VALID_PLAN_STATUSES = {"Active", "Paused", "Done", "Empty"}
VALID_SUBTASK_STATUSES = {"Pending", "Active", "Done", "Blocked", "Skipped", "Superseded"}
VALID_DECISION_STATUSES = {"Active", "Proposed", "Superseded", "Rejected", "Deprecated"}
VALID_SOURCE_STATUSES = {"To Read", "Reading", "Read", "Useful", "Archived", "Rejected"}
VALID_KNOWLEDGE_STATUSES = {"Draft", "Active", "Promoted", "Stale", "Rejected"}
VALID_FEEDBACK_STATUSES = {"Open", "Triaged", "Planned", "Done", "Rejected"}
VALID_HUMAN_NOTE_STATUSES = {"Open", "Triaged", "Done", "Rejected"}
VALID_HUMAN_INDEX_STATUSES = {"Open", "Reviewed", "Extracted", "Archived"}
VALID_WORKSTREAM_STATUSES = {"Proposed", "Open", "Active", "Blocked", "ReadyToMerge", "Merging", "Done", "Cancelled"}
VALID_WORKSTREAM_TYPES = {"Task", "Merge", "Maintenance"}
VALID_WORKSTREAM_ATTENTION = {"Now", "Next", "Waiting", "Retained"}
VALID_WORKSTREAM_STAGE_STATUSES = {"Pending", "Active", "Blocked", "Done", "Skipped", "Cancelled"}
VALID_MERGE_RESOLUTIONS = {"merged", "rejected", "no_merge_required", "archived"}
ACTIVE_WORKSTREAM_STATUSES = {"Active", "Blocked", "ReadyToMerge", "Merging"}
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
    "Proposed": {"Active", "Cancelled"},
    "Open": {"Active", "Cancelled"},
    "Active": {"Blocked", "ReadyToMerge", "Cancelled"},
    "Blocked": {"Active", "Cancelled"},
    "ReadyToMerge": {"Active", "Merging", "Done", "Cancelled"},
    "Merging": {"Active", "ReadyToMerge", "Done", "Cancelled"},
    "Done": set(),
    "Cancelled": set(),
}
SOURCE_TABLE_HEADER = "| 资料 | 类型 | 链接或位置 | 状态 | 可信度 | 和本项目的关系 | 后续动作 |"
RULES_INDEX_TABLE_HEADER = "| 文件 | 读取条件 | 作用 |"
TASK_TABLE_HEADER = "| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |"
TASK_STAGE_TABLE_HEADER = "| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |"
FEEDBACK_TABLE_HEADER = "| ID | 状态 | 类型 | 内容 | 来源 | 后续处理 |"
HUMAN_NOTE_TABLE_HEADER = "| ID | 状态 | 类型 | 内容 | 关联位置 | AI 处理建议 | 证据 |"
HUMAN_INDEX_TABLE_HEADER = "| ID | 状态 | 类型 | 标题 | 路径 | 日期 | 已整理到 | 备注 |"
KNOWLEDGE_TABLE_HEADER = "| ID | 标题 | 状态 | 标签 | 摘要 | 详情 |"
ARCHIVE_TABLE_HEADER = "| 日期 | 类型 | ID | 原路径 | 归档路径 | 状态 | 原因 |"
LEGACY_ARCHIVE_TABLE_HEADER = "| 日期 | 类型 | 标题 | 原因 | 详情 |"
WORKSTREAM_TABLE_HEADER = "| ID | 状态 | 标题 | Owner | 写入范围 | 依赖 | 输出物 | 详情 |"
WORKSTREAM_STAGE_TABLE_HEADER = "| ID | 状态 | 阶段 | 依赖 | 输出物 | 证据 | 下一步 |"
WORKSTREAM_INDEX_REL = "active/Workstreams.md"
WORKSTREAM_DIR_REL = "active/workstreams"
WORKSTREAM_ARCHIVE_DIR_REL = "archive/workstreams"
WORKSTREAM_METADATA_FIELDS = (
    "id",
    "type",
    "status",
    "attention",
    "owner",
    "title",
    "current_stage",
    "depends_on",
    "read_scope",
    "write_scope",
    "merge_targets",
    "merge_owner",
    "coordination",
    "merge_resolution",
    "keep_active_reason",
    "keep_active_until",
)
TEMPLATE_EXAMPLE_FILES = {"decisions/ADR-0001-template.md", "worklog/daily/YYYY-MM-DD.md"}
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


from ai_context_framework.runtime_parts import (
    archive_workstream as runtime_archive_workstream,
    check as runtime_check,
    core as runtime_core,
    doctor as runtime_doctor,
    knowledge_review as runtime_knowledge_review,
    objects as runtime_objects,
    plan_task as runtime_plan_task,
    upgrade as runtime_upgrade,
)

_RUNTIME_PART_MODULES = (
    runtime_core,
    runtime_objects,
    runtime_upgrade,
    runtime_plan_task,
    runtime_doctor,
    runtime_archive_workstream,
    runtime_knowledge_review,
    runtime_check,
)


def _install_runtime_parts() -> None:
    module_globals = globals()
    for module in _RUNTIME_PART_MODULES:
        for name, value in module.__dict__.items():
            if name.startswith("__") and name != "__getattr__":
                continue
            module_globals[name] = value
    for module in _RUNTIME_PART_MODULES:
        for name, value in module_globals.items():
            if name.startswith("__"):
                continue
            module.__dict__[name] = value
    _sync_runtime_part_globals()


def _sync_runtime_part_globals() -> None:
    for module in _RUNTIME_PART_MODULES:
        module.ROOT = ROOT


_install_runtime_parts()

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
    status_parser.add_argument(
        "--workstream",
        type=validate_workstream_id,
        default=None,
        help="explicitly select one Workstream context; omitted means global-only",
    )
    add_json_argument(status_parser)
    status_parser.set_defaults(func=status_command)

    next_parser = subparsers.add_parser("next", help="show the next low-risk context entry")
    next_parser.add_argument("path", nargs="?", type=Path)
    next_parser.add_argument(
        "--workstream",
        type=validate_workstream_id,
        default=None,
        help="explicitly select one Workstream context; omitted means global-only",
    )
    add_json_argument(next_parser)
    next_parser.set_defaults(func=next_status_commands.next_command)

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
            "Feedback_Inbox, Task_Plan, archive, archive/feedback, and Knowledge files/directories, "
            "and by safely refreshing recognized managed documentation sections such as AGENTS.md "
            "and reference/System_Manual.md. This command does "
            "not move old content, archive active tasks, or overwrite an Active "
            "Current_Task.md. Use --plan --json for read-only assessment and --dry-run --json "
            "to review changed_files before writing."
        ),
    )
    upgrade_parser.add_argument("path", nargs="?", type=Path)
    upgrade_parser.add_argument("--plan", action="store_true", help="print a read-only upgrade assessment plan")
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

    links_parser = subparsers.add_parser("links", help="manage structured link graph and generated backlinks")
    links_subparsers = links_parser.add_subparsers(dest="links_command", required=True)
    links_graph_parser = links_subparsers.add_parser("graph", help="print structured link graph")
    links_graph_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(links_graph_parser)
    links_graph_parser.set_defaults(func=links_commands.links_graph_command)

    links_check_parser = links_subparsers.add_parser("check", help="check structured link targets")
    links_check_parser.add_argument("path", nargs="?", type=Path)
    links_check_parser.add_argument("--strict", action="store_true", help="treat governance link breakage as errors")
    add_json_argument(links_check_parser)
    links_check_parser.set_defaults(func=links_commands.links_check_command)

    links_backlinks_parser = links_subparsers.add_parser("backlinks", help="show structured backlinks for a target")
    links_backlinks_parser.add_argument("target", help="target path")
    links_backlinks_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(links_backlinks_parser)
    links_backlinks_parser.set_defaults(func=links_commands.links_backlinks_command)

    links_sync_parser = links_subparsers.add_parser("sync-backlinks", help="preview or sync generated backlink blocks")
    links_sync_parser.add_argument("path", nargs="?", type=Path)
    links_sync_parser.add_argument("--apply", action="store_true", help="write generated backlink blocks")
    links_sync_parser.add_argument("--dry-run", action="store_true", help="report planned backlinks without writing")
    add_json_argument(links_sync_parser)
    links_sync_parser.set_defaults(func=links_commands.links_sync_backlinks_command)

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

    log_projects_parser = log_subparsers.add_parser("projects", help="summarize all usage-log projects")
    log_projects_parser.add_argument("--log-root", type=Path, default=None, help="ACF home or projects directory to read")
    log_projects_parser.add_argument("--scan-root", type=Path, action="append", default=None, help="scan for real context roots; can be repeated")
    log_projects_parser.add_argument("--min-events", type=int, default=0, help="minimum event count for listed projects")
    log_projects_parser.add_argument("--include-unresolved", action="store_true", help="include log-only projects not matched to scan roots")
    add_json_argument(log_projects_parser)
    log_projects_parser.set_defaults(func=log_projects_command)

    log_issues_parser = log_subparsers.add_parser(
        "issues",
        help="summarize structured continuation dogfood issues",
    )
    log_issues_parser.add_argument("path", nargs="?", type=Path)
    log_issues_parser.add_argument("--all-projects", action="store_true")
    log_issues_parser.add_argument("--open-only", action="store_true")
    log_issues_parser.add_argument("--limit", type=int, default=100)
    add_json_argument(log_issues_parser)
    log_issues_parser.set_defaults(func=log_issues_command)

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

    workstream_dashboard_parser = workstream_subparsers.add_parser("dashboard", help="show parallel Workstream safety dashboard")
    workstream_dashboard_parser.add_argument("path", nargs="?", type=Path)
    workstream_dashboard_parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS, help="days before an active Workstream is reported as stale")
    add_json_argument(workstream_dashboard_parser)
    workstream_dashboard_parser.set_defaults(func=workstream_dashboard_command)

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

    workstream_context_parser = workstream_subparsers.add_parser("context", help="print the AI execution context packet for one Workstream")
    workstream_context_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_context_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_context_parser)
    workstream_context_parser.set_defaults(func=workstream_context_command)

    workstream_next_actions_parser = workstream_subparsers.add_parser("next-actions", help="recommend safe next actions for a Workstream")
    workstream_next_actions_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_next_actions_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_next_actions_parser)
    workstream_next_actions_parser.set_defaults(func=workstream_next_actions_command)

    workstream_preflight_parser = workstream_subparsers.add_parser("preflight", help="check Workstream scope before editing")
    workstream_preflight_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_preflight_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_preflight_parser)
    workstream_preflight_parser.set_defaults(func=workstream_preflight_command)

    workstream_add_parser = workstream_subparsers.add_parser("add", help="create a Workstream detail and index row")
    workstream_add_parser.add_argument("path", nargs="?", type=Path)
    workstream_add_parser.add_argument("--id", type=validate_workstream_id, required=True, help="Workstream id, for example WS002")
    workstream_add_parser.add_argument("--type", choices=tuple(sorted(VALID_WORKSTREAM_TYPES)), default="Task", help="Workstream type")
    workstream_add_parser.add_argument("--title", required=True, help="Workstream title")
    workstream_add_parser.add_argument("--owner", required=True, help="Workstream owner")
    workstream_add_parser.add_argument("--depends-on", action="append", default=None, help="dependency id; can be repeated")
    workstream_add_parser.add_argument("--read-scope", action="append", default=None, help="recommended read scope; can be repeated")
    workstream_add_parser.add_argument("--write-scope", action="append", default=None, help="typed write scope, for example `assigned: active/Current_Task.md`; can be repeated")
    workstream_add_parser.add_argument("--output", default="待补充。", help="expected output summary")
    workstream_add_parser.add_argument("--goal", default=None, help="goal text written to the Workstream detail")
    workstream_add_parser.add_argument("--attention", choices=tuple(sorted(VALID_WORKSTREAM_ATTENTION)), default=None, help="attention state: Now, Next, Waiting, or Retained")
    add_write_arguments(workstream_add_parser)
    workstream_add_parser.set_defaults(func=workstream_add_command)

    workstream_reserve_parser = workstream_subparsers.add_parser(
        "reserve",
        help="reserve a unique Workstream ID on the primary branch without creating a worktree",
    )
    workstream_reserve_parser.add_argument("path", nargs="?", type=Path)
    workstream_reserve_parser.add_argument("--id", type=validate_workstream_id, default=None, help="optional explicit Workstream id")
    workstream_reserve_parser.add_argument("--type", choices=tuple(sorted(VALID_WORKSTREAM_TYPES)), default="Task")
    workstream_reserve_parser.add_argument("--title", default=None)
    workstream_reserve_parser.add_argument("--slug", default=None, help="portable lowercase task slug used if a worktree is created later")
    workstream_reserve_parser.add_argument("--owner", default=None)
    workstream_reserve_parser.add_argument("--depends-on", action="append", default=None)
    workstream_reserve_parser.add_argument("--read-scope", action="append", default=None)
    workstream_reserve_parser.add_argument("--write-scope", action="append", default=None)
    workstream_reserve_parser.add_argument("--output", default="待补充。")
    workstream_reserve_parser.add_argument("--goal", default=None)
    workstream_reserve_parser.add_argument("--attention", choices=tuple(sorted(VALID_WORKSTREAM_ATTENTION)), default=None)
    workstream_reserve_parser.add_argument("--merge-owner", type=validate_workstream_id, default=None)
    workstream_reserve_parser.add_argument("--coordination", choices=("parallel", "serial"), default=None)
    workstream_reserve_parser.add_argument("--message", default=None, help="reservation commit message")
    workstream_reserve_parser.add_argument("--resume-operation", default=None, help="resume one interrupted reservation journal")
    workstream_reserve_parser.add_argument("--apply", action="store_true", help="write and commit the reservation on the primary branch")
    add_json_argument(workstream_reserve_parser)
    workstream_reserve_parser.set_defaults(func=workstream_reserve_command)

    workstream_set_parser = workstream_subparsers.add_parser("set", help="set Workstream status through allowed transitions")
    workstream_set_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_set_parser.add_argument("path", nargs="?", type=Path)
    workstream_set_parser.add_argument("--status", choices=tuple(sorted(VALID_WORKSTREAM_STATUSES)), default=None)
    workstream_set_parser.add_argument("--goal", default=None, help="replace the Workstream goal section")
    workstream_set_parser.add_argument("--attention", choices=tuple(sorted(VALID_WORKSTREAM_ATTENTION)), default=None, help="attention state: Now, Next, Waiting, or Retained")
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

    workstream_merge_start_parser = workstream_subparsers.add_parser("merge-start", help="mark a Merge or Maintenance Workstream as Merging")
    workstream_merge_start_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_merge_start_parser.add_argument("path", nargs="?", type=Path)
    workstream_merge_start_parser.add_argument("--summary", default=None, help="optional merge-start note")
    add_write_arguments(workstream_merge_start_parser)
    workstream_merge_start_parser.set_defaults(func=workstream_merge_start_command)

    workstream_ready_parser = workstream_subparsers.add_parser("ready", help="mark a Workstream ReadyToMerge")
    workstream_ready_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_ready_parser.add_argument("path", nargs="?", type=Path)
    workstream_ready_parser.add_argument(
        "--human-approved",
        action="store_true",
        help="confirm that a human explicitly approved marking this Workstream ReadyToMerge",
    )
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

    workstream_scope_add_parser = workstream_subparsers.add_parser("scope-add", help="append read/write scope with reason and activity log")
    workstream_scope_add_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_scope_add_parser.add_argument("path", nargs="?", type=Path)
    workstream_scope_add_parser.add_argument("--read", action="append", default=None, help="read scope path; can be repeated")
    workstream_scope_add_parser.add_argument("--write", action="append", default=None, help="typed write scope; can be repeated")
    workstream_scope_add_parser.add_argument("--reason", required=True, help="reason for expanding scope")
    workstream_scope_add_parser.add_argument("--merge-owner", type=validate_workstream_id, default=None, help="Workstream that owns final merge for shared scope")
    workstream_scope_add_parser.add_argument("--coordination", choices=("parallel", "serial"), default=None, help="coordination mode for shared scope")
    add_write_arguments(workstream_scope_add_parser)
    workstream_scope_add_parser.set_defaults(func=workstream_scope_add_command)

    workstream_guard_parser = workstream_subparsers.add_parser("guard", help="check changed files against one Workstream write boundary")
    workstream_guard_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_guard_parser.add_argument("path", nargs="?", type=Path)
    workstream_guard_parser.add_argument("--file", action="append", default=None, help="explicit changed file; can be repeated")
    workstream_guard_parser.add_argument("--files", action="append", nargs="+", default=None, help="explicit changed files")
    workstream_guard_parser.add_argument("--from-git", action="store_true", help="read changed files from git")
    workstream_guard_parser.add_argument("--workspace", action="store_true", help="check the whole workspace")
    workstream_guard_parser.add_argument("--strict-workspace", action="store_true", help="fail on unrelated workspace changes")
    workstream_guard_parser.add_argument("--owned-only", action="store_true", help="disallow shared scope writes")
    workstream_guard_parser.add_argument("--changed-file", action="append", default=None, help="override git diff with explicit changed file; can be repeated")
    add_json_argument(workstream_guard_parser)
    workstream_guard_parser.set_defaults(func=workstream_guard_command)

    workstream_note_parser = workstream_subparsers.add_parser("note", help="append a note to a Workstream detail section")
    workstream_note_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_note_parser.add_argument("path", nargs="?", type=Path)
    workstream_note_parser.add_argument("--section", required=True, help="allowed note section")
    workstream_note_parser.add_argument("--text", default=None, help="note text")
    workstream_note_parser.add_argument("--input", type=Path, default=None, help="file containing note text")
    add_write_arguments(workstream_note_parser)
    workstream_note_parser.set_defaults(func=workstream_note_command)

    worktree_parser = subparsers.add_parser(
        "worktree",
        help="manage optional Git branches and linked worktrees",
    )
    worktree_subparsers = worktree_parser.add_subparsers(dest="worktree_command", required=True)

    worktree_create_parser = worktree_subparsers.add_parser(
        "create",
        help="plan or create a Workstream or classified non-Workstream worktree",
    )
    worktree_create_parser.add_argument("path", nargs="?", type=Path, help="context path or project directory")
    create_identity = worktree_create_parser.add_mutually_exclusive_group(required=True)
    create_identity.add_argument("--workstream", type=validate_workstream_id)
    create_identity.add_argument("--kind", choices=worktree_commands.ALLOWED_NON_WORKSTREAM_KINDS)
    worktree_create_parser.add_argument("--slug", default=None, help="task slug; required for non-Workstream targets and optional override for Workstreams")
    worktree_create_parser.add_argument("--operation-id", default=None, help="optional stable operation id for recovery")
    worktree_create_parser.add_argument("--apply", action="store_true", help="perform the planned Git changes")
    add_json_argument(worktree_create_parser)
    worktree_create_parser.set_defaults(func=worktree_commands.worktree_create_command)

    worktree_attach_parser = worktree_subparsers.add_parser("attach", help="bind and verify an existing standard worktree")
    worktree_attach_parser.add_argument("path", nargs="?", type=Path)
    worktree_attach_parser.add_argument("--workstream", type=validate_workstream_id, required=True)
    worktree_attach_parser.add_argument("--target", type=Path, required=True)
    worktree_attach_parser.add_argument("--slug", default=None)
    worktree_attach_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_attach_parser)
    worktree_attach_parser.set_defaults(func=worktree_commands.worktree_attach_command)

    worktree_verify_parser = worktree_subparsers.add_parser("verify", help="verify repository, branch, path, registry, and reservation identity")
    worktree_verify_parser.add_argument("path", nargs="?", type=Path)
    verify_identity = worktree_verify_parser.add_mutually_exclusive_group(required=True)
    verify_identity.add_argument("--workstream", type=validate_workstream_id)
    verify_identity.add_argument("--target", type=Path)
    worktree_verify_parser.add_argument("--slug", default=None)
    add_json_argument(worktree_verify_parser)
    worktree_verify_parser.set_defaults(func=worktree_commands.worktree_verify_command)

    worktree_list_parser = worktree_subparsers.add_parser("list", help="list Git worktrees and ACF bindings")
    worktree_list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(worktree_list_parser)
    worktree_list_parser.set_defaults(func=worktree_commands.worktree_list_command)

    worktree_audit_parser = worktree_subparsers.add_parser("audit", help="audit detached, prunable, misplaced, or stale worktrees")
    worktree_audit_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(worktree_audit_parser)
    worktree_audit_parser.set_defaults(func=worktree_commands.worktree_audit_command)

    worktree_sync_parser = worktree_subparsers.add_parser("sync", help="merge the primary branch into a clean worktree branch")
    worktree_sync_parser.add_argument("path", nargs="?", type=Path)
    sync_identity = worktree_sync_parser.add_mutually_exclusive_group(required=True)
    sync_identity.add_argument("--workstream", type=validate_workstream_id)
    sync_identity.add_argument("--target", type=Path)
    worktree_sync_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_sync_parser)
    worktree_sync_parser.set_defaults(func=worktree_commands.worktree_sync_command)

    worktree_merge_plan_parser = worktree_subparsers.add_parser("merge-plan", help="plan an integration-worktree merge and protected fast-forward promotion")
    worktree_merge_plan_parser.add_argument("path", nargs="?", type=Path)
    merge_plan_identity = worktree_merge_plan_parser.add_mutually_exclusive_group(required=True)
    merge_plan_identity.add_argument("--workstream", type=validate_workstream_id)
    merge_plan_identity.add_argument("--target", type=Path)
    add_json_argument(worktree_merge_plan_parser)
    worktree_merge_plan_parser.set_defaults(func=worktree_commands.worktree_merge_plan_command)

    worktree_merge_parser = worktree_subparsers.add_parser("merge", help="merge in a temporary integration worktree, validate, migrate artifacts, and promote")
    worktree_merge_parser.add_argument("path", nargs="?", type=Path)
    merge_identity = worktree_merge_parser.add_mutually_exclusive_group(required=True)
    merge_identity.add_argument("--workstream", type=validate_workstream_id)
    merge_identity.add_argument("--target", type=Path)
    worktree_merge_parser.add_argument("--message", default=None)
    worktree_merge_parser.add_argument("--operation-id", default=None, help="optional stable operation id")
    worktree_merge_parser.add_argument("--pre-check-json", action="append", default=None, help="JSON argv array executed in the source worktree before merge")
    worktree_merge_parser.add_argument("--post-check-json", action="append", default=None, help="JSON argv array executed in the temporary integration worktree")
    worktree_merge_parser.add_argument("--max-replans", type=int, default=8)
    worktree_merge_parser.add_argument("--conflict-replans", type=int, default=3)
    worktree_merge_parser.add_argument("--lock-wait-timeout", type=int, default=300)
    worktree_merge_parser.add_argument("--wait-timeout", type=int, default=600)
    worktree_merge_parser.add_argument("--initial-delay", type=float, default=0.5)
    worktree_merge_parser.add_argument("--max-delay", type=float, default=15.0)
    worktree_merge_parser.add_argument("--jitter-ratio", type=float, default=0.20)
    worktree_merge_parser.add_argument("--artifact-required", action="append", default=None, metavar="PATH=DEST")
    worktree_merge_parser.add_argument("--artifact-reference", action="append", default=None, metavar="PATH=DEST")
    worktree_merge_parser.add_argument("--artifact-cache", action="append", default=None, metavar="PATH")
    worktree_merge_parser.add_argument("--artifact-discardable", action="append", default=None, metavar="PATH")
    worktree_merge_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_merge_parser)
    worktree_merge_parser.set_defaults(func=worktree_commands.worktree_merge_command)

    worktree_artifact_plan_parser = worktree_subparsers.add_parser("artifact-plan", help="classify ignored/untracked worktree artifacts before promotion or close")
    worktree_artifact_plan_parser.add_argument("path", nargs="?", type=Path)
    artifact_plan_identity = worktree_artifact_plan_parser.add_mutually_exclusive_group(required=True)
    artifact_plan_identity.add_argument("--workstream", type=validate_workstream_id)
    artifact_plan_identity.add_argument("--target", type=Path)
    worktree_artifact_plan_parser.add_argument("--required", action="append", default=None, metavar="PATH=DEST")
    worktree_artifact_plan_parser.add_argument("--reference", action="append", default=None, metavar="PATH=DEST")
    worktree_artifact_plan_parser.add_argument("--cache", action="append", default=None, metavar="PATH")
    worktree_artifact_plan_parser.add_argument("--discardable", action="append", default=None, metavar="PATH")
    worktree_artifact_plan_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_artifact_plan_parser)
    worktree_artifact_plan_parser.set_defaults(func=worktree_commands.worktree_artifact_plan_command)

    worktree_artifact_migrate_parser = worktree_subparsers.add_parser("artifact-migrate", help="copy/reference artifacts and verify their digests")
    worktree_artifact_migrate_parser.add_argument("path", nargs="?", type=Path)
    artifact_migrate_identity = worktree_artifact_migrate_parser.add_mutually_exclusive_group(required=True)
    artifact_migrate_identity.add_argument("--workstream", type=validate_workstream_id)
    artifact_migrate_identity.add_argument("--target", type=Path)
    worktree_artifact_migrate_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_artifact_migrate_parser)
    worktree_artifact_migrate_parser.set_defaults(func=worktree_commands.worktree_artifact_migrate_command)

    worktree_close_parser = worktree_subparsers.add_parser("close", help="remove an already-merged clean worktree after artifact handoff")
    worktree_close_parser.add_argument("path", nargs="?", type=Path)
    close_identity = worktree_close_parser.add_mutually_exclusive_group(required=True)
    close_identity.add_argument("--workstream", type=validate_workstream_id)
    close_identity.add_argument("--target", type=Path)
    worktree_close_parser.add_argument("--wait-timeout", type=int, default=120)
    worktree_close_parser.add_argument("--operation-id", default=None)
    worktree_close_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_close_parser)
    worktree_close_parser.set_defaults(func=worktree_commands.worktree_close_command)

    worktree_resume_parser = worktree_subparsers.add_parser("resume", help="inspect or resume a journaled create/merge/close operation")
    worktree_resume_parser.add_argument("operation_id")
    worktree_resume_parser.add_argument("path", nargs="?", type=Path)
    worktree_resume_parser.add_argument("--apply", action="store_true")
    add_json_argument(worktree_resume_parser)
    worktree_resume_parser.set_defaults(func=worktree_commands.worktree_resume_command)

    observer_commands.register_observer_parser(subparsers, add_json_argument)

    continuation_parser = subparsers.add_parser(
        "continuation",
        help="manage bounded local continuation state for external AI schedulers",
    )
    continuation_subparsers = continuation_parser.add_subparsers(
        dest="continuation_command",
        required=True,
    )

    continuation_init_parser = continuation_subparsers.add_parser(
        "init",
        help="initialize bounded continuation state and capture the current Git workspace baseline",
    )
    continuation_init_parser.add_argument("path", nargs="?", type=Path)
    continuation_init_parser.add_argument("--task-id", default=None)
    continuation_init_parser.add_argument("--workstream", type=validate_workstream_id, default=None)
    continuation_init_parser.add_argument("--title", required=True)
    continuation_init_parser.add_argument("--objective", required=True)
    continuation_init_parser.add_argument("--stage", default="bootstrap")
    continuation_init_parser.add_argument("--next-action", default=None)
    continuation_init_parser.add_argument("--plan-ref", action="append", default=None)
    continuation_init_parser.add_argument("--expected-branch", default=None)
    continuation_init_parser.add_argument(
        "--profile",
        choices=tuple(sorted(continuation_commands.TIMING_PROFILES)),
        default="standard",
        help="timing profile; explicit timing flags override the selected profile",
    )
    continuation_init_parser.add_argument(
        "--interval-minutes",
        type=int,
        default=None,
    )
    continuation_init_parser.add_argument(
        "--lease-ttl-minutes",
        type=int,
        default=None,
    )
    continuation_init_parser.add_argument(
        "--renew-interval-minutes",
        type=int,
        default=None,
    )
    continuation_init_parser.add_argument("--heartbeat-interval-minutes", type=int, default=None)
    continuation_init_parser.add_argument("--stale-after-minutes", type=int, default=None)
    continuation_init_parser.add_argument("--force", action="store_true")
    add_json_argument(continuation_init_parser)
    continuation_init_parser.set_defaults(func=continuation_commands.continuation_init_command)

    continuation_commands.register_configure_parser(
        continuation_subparsers,
        add_json_argument,
    )

    continuation_doctor_parser = continuation_subparsers.add_parser(
        "doctor",
        help="verify Git/worktree identity and report whether a new round may claim",
    )
    continuation_doctor_parser.add_argument("path", nargs="?", type=Path)
    continuation_doctor_parser.add_argument("--task-id", default=None)
    add_json_argument(continuation_doctor_parser)
    continuation_doctor_parser.set_defaults(func=continuation_commands.continuation_doctor_command)

    continuation_claim_parser = continuation_subparsers.add_parser(
        "claim",
        help="claim one bounded continuation round",
    )
    continuation_claim_parser.add_argument("path", nargs="?", type=Path)
    continuation_claim_parser.add_argument("--task-id", default=None)
    continuation_claim_parser.add_argument("--runner-id", required=True)
    continuation_claim_parser.add_argument("--ttl-minutes", type=int, default=None)
    add_json_argument(continuation_claim_parser)
    continuation_claim_parser.set_defaults(func=continuation_commands.continuation_claim_command)

    continuation_assert_owner_parser = continuation_subparsers.add_parser(
        "assert-owner",
        help="verify that lease id, generation, and fence token still own the active round",
    )
    continuation_assert_owner_parser.add_argument("path", nargs="?", type=Path)
    continuation_assert_owner_parser.add_argument("--task-id", default=None)
    continuation_assert_owner_parser.add_argument("--lease-id", required=True)
    continuation_assert_owner_parser.add_argument("--generation", type=int, default=None)
    continuation_assert_owner_parser.add_argument("--fence-token", default=None)
    add_json_argument(continuation_assert_owner_parser)
    continuation_assert_owner_parser.set_defaults(
        func=continuation_commands.continuation_assert_owner_command
    )

    continuation_heartbeat_parser = continuation_subparsers.add_parser(
        "heartbeat",
        help="refresh runner liveness without extending the lease TTL",
    )
    continuation_heartbeat_parser.add_argument("path", nargs="?", type=Path)
    continuation_heartbeat_parser.add_argument("--task-id", default=None)
    continuation_heartbeat_parser.add_argument("--lease-id", required=True)
    continuation_heartbeat_parser.add_argument("--generation", type=int, default=None)
    continuation_heartbeat_parser.add_argument("--fence-token", default=None)
    add_json_argument(continuation_heartbeat_parser)
    continuation_heartbeat_parser.set_defaults(func=continuation_commands.continuation_heartbeat_command)

    continuation_commands.register_round_effect_parsers(
        continuation_subparsers,
        add_json_argument,
    )
    continuation_commands.register_workspace_parsers(
        continuation_subparsers,
        add_json_argument,
    )
    continuation_commands.register_coordination_parsers(
        continuation_subparsers,
        add_json_argument,
    )

    continuation_renew_parser = continuation_subparsers.add_parser(
        "renew",
        help="extend an active lease before it expires",
    )
    continuation_renew_parser.add_argument("path", nargs="?", type=Path)
    continuation_renew_parser.add_argument("--task-id", default=None)
    continuation_renew_parser.add_argument("--lease-id", required=True)
    continuation_renew_parser.add_argument("--generation", type=int, default=None)
    continuation_renew_parser.add_argument("--fence-token", default=None)
    continuation_renew_parser.add_argument("--ttl-minutes", type=int, default=None)
    add_json_argument(continuation_renew_parser)
    continuation_renew_parser.set_defaults(func=continuation_commands.continuation_renew_command)

    continuation_checkpoint_parser = continuation_subparsers.add_parser(
        "checkpoint",
        help="update compact continuation state while holding the active lease",
    )
    continuation_checkpoint_parser.add_argument("path", nargs="?", type=Path)
    continuation_checkpoint_parser.add_argument("--task-id", default=None)
    continuation_checkpoint_parser.add_argument("--lease-id", required=True)
    continuation_checkpoint_parser.add_argument("--generation", type=int, default=None)
    continuation_checkpoint_parser.add_argument("--fence-token", default=None)
    continuation_checkpoint_parser.add_argument(
        "--status",
        choices=tuple(sorted(continuation_commands.STATE_STATUSES)),
        default=None,
    )
    continuation_checkpoint_parser.add_argument("--stage", default=None)
    continuation_checkpoint_parser.add_argument("--next-action", default=None)
    continuation_checkpoint_parser.add_argument("--completed", action="append", default=None)
    continuation_checkpoint_parser.add_argument("--constraint", action="append", default=None)
    continuation_checkpoint_parser.add_argument(
        "--supersede-constraint",
        action="append",
        default=None,
        help="retire one exact current constraint superseded by newer authority; requires --evidence-ref",
    )
    continuation_checkpoint_parser.add_argument("--evidence-ref", action="append", default=None)
    continuation_checkpoint_parser.add_argument("--open-question", action="append", default=None)
    continuation_checkpoint_parser.add_argument(
        "--resolve-open-question",
        action="append",
        default=None,
        help="retire one exact current open question resolved by newer authority; requires --evidence-ref",
    )
    continuation_checkpoint_parser.add_argument("--plan-ref", action="append", default=None)
    continuation_checkpoint_parser.add_argument("--verification", action="append", default=None)
    add_json_argument(continuation_checkpoint_parser)
    continuation_checkpoint_parser.set_defaults(
        func=continuation_commands.continuation_checkpoint_command
    )

    continuation_release_parser = continuation_subparsers.add_parser(
        "release",
        help="finish a round, record a receipt, and release the active lease",
    )
    continuation_release_parser.add_argument("path", nargs="?", type=Path)
    continuation_release_parser.add_argument("--task-id", default=None)
    continuation_release_parser.add_argument("--lease-id", required=True)
    continuation_release_parser.add_argument("--generation", type=int, default=None)
    continuation_release_parser.add_argument("--fence-token", default=None)
    continuation_release_parser.add_argument(
        "--final-status",
        choices=tuple(sorted(continuation_commands.STATE_STATUSES - {"running"})),
        default=None,
    )
    continuation_release_parser.add_argument("--stage", default=None)
    continuation_release_parser.add_argument("--next-action", default=None)
    continuation_release_parser.add_argument("--verification", action="append", default=None)
    add_json_argument(continuation_release_parser)
    continuation_release_parser.set_defaults(func=continuation_commands.continuation_release_command)

    continuation_pause_parser = continuation_subparsers.add_parser(
        "pause",
        help="request a deterministic stop without killing an active external agent",
    )
    continuation_pause_parser.add_argument("path", nargs="?", type=Path)
    continuation_pause_parser.add_argument("--task-id", default=None)
    continuation_pause_parser.add_argument("--reason", required=True)
    continuation_pause_parser.add_argument("--requested-by", default="user")
    add_json_argument(continuation_pause_parser)
    continuation_pause_parser.set_defaults(func=continuation_commands.continuation_pause_command)

    continuation_resume_parser = continuation_subparsers.add_parser(
        "resume",
        help="resume a paused continuation after the active lease has ended",
    )
    continuation_resume_parser.add_argument("path", nargs="?", type=Path)
    continuation_resume_parser.add_argument("--task-id", default=None)
    continuation_resume_parser.add_argument("--next-action", required=True)
    add_json_argument(continuation_resume_parser)
    continuation_resume_parser.set_defaults(func=continuation_commands.continuation_resume_command)

    continuation_prompt_parser = continuation_subparsers.add_parser(
        "prompt",
        help="render a model-agnostic continuation protocol for an external agent",
    )
    continuation_prompt_parser.add_argument("path", nargs="?", type=Path)
    continuation_prompt_parser.add_argument("--task-id", default=None)
    continuation_prompt_parser.add_argument("--runner-id", default=None, help="optional current runner identity so the rendered protocol can distinguish owner vs duplicate wake")
    add_json_argument(continuation_prompt_parser)
    continuation_prompt_parser.set_defaults(func=continuation_commands.continuation_prompt_command)

    continuation_issue_parser = continuation_subparsers.add_parser(
        "issue",
        help="record one structured reusable dogfood issue in the user-level ACF log",
    )
    continuation_issue_parser.add_argument("path", nargs="?", type=Path)
    continuation_issue_parser.add_argument("--task-id", default=None)
    continuation_issue_parser.add_argument("--category", default="other")
    continuation_issue_parser.add_argument(
        "--severity",
        choices=("low", "medium", "high", "critical"),
        default="medium",
    )
    continuation_issue_parser.add_argument("--text", required=True)
    continuation_issue_parser.add_argument(
        "--resolve-fingerprint",
        default=None,
        help="append a resolution event for an existing aggregated issue fingerprint",
    )
    continuation_issue_parser.add_argument("--evidence-ref", action="append", default=None)
    continuation_issue_parser.add_argument("--related-command", default=None)
    continuation_issue_parser.add_argument("--runner-id", default="agent")
    add_json_argument(continuation_issue_parser)
    continuation_issue_parser.set_defaults(func=continuation_commands.continuation_issue_command)

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
    task_start_parser.add_argument("--workstream", action="append", default=None, help="override owning Workstream id; can be repeated")
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

    archive_sync_parser = archive_subparsers.add_parser("sync", help="sync the generated Archive index block")
    archive_sync_parser.add_argument("path", nargs="?", type=Path)
    archive_sync_parser.add_argument("--init-marker", action="store_true", help="insert generated markers when missing")
    add_write_arguments(archive_sync_parser)
    archive_sync_parser.set_defaults(func=archive_sync_command)

    decisions_parser = subparsers.add_parser("decisions", help="manage decision index sync")
    decisions_subparsers = decisions_parser.add_subparsers(dest="decisions_command", required=True)

    decisions_sync_parser = decisions_subparsers.add_parser("sync", help="sync the generated Decisions index block")
    decisions_sync_parser.add_argument("path", nargs="?", type=Path)
    decisions_sync_parser.add_argument("--init-marker", action="store_true", help="insert generated markers when missing")
    add_write_arguments(decisions_sync_parser)
    decisions_sync_parser.set_defaults(func=decisions_sync_command)

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
    knowledge_draft_parser.set_defaults(func=knowledge_draft_command)

    knowledge_apply_parser = knowledge_subparsers.add_parser("apply", help="apply a knowledge draft")
    knowledge_apply_parser.add_argument("draft", type=Path, help="draft path")
    knowledge_apply_parser.add_argument("path", nargs="?", type=Path, help="context path")
    knowledge_apply_parser.add_argument("--draft", dest="draft_option", type=Path, default=None, help="draft path when the positional argument is the context path")
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

    knowledge_sync_parser = knowledge_subparsers.add_parser("sync", help="sync the generated Knowledge index block")
    knowledge_sync_parser.add_argument("path", nargs="?", type=Path)
    knowledge_sync_parser.add_argument("--init-marker", action="store_true", help="insert generated markers when missing")
    add_write_arguments(knowledge_sync_parser)
    knowledge_sync_parser.set_defaults(func=knowledge_sync_command)

    draft_group_parser = subparsers.add_parser("draft", help="inspect reviewable drafts")
    draft_subparsers = draft_group_parser.add_subparsers(dest="draft_command", required=True)
    draft_status_parser = draft_subparsers.add_parser("status", help="list reviewable drafts without reading bodies")
    draft_status_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(draft_status_parser)
    draft_status_parser.set_defaults(func=next_status_commands.draft_status_command)

    feedback_parser = subparsers.add_parser("feedback", help="manage active/Feedback_Inbox.md lifecycle")
    feedback_subparsers = feedback_parser.add_subparsers(dest="feedback_command", required=True)

    feedback_list_parser = feedback_subparsers.add_parser("list", help="list feedback inbox rows")
    feedback_list_parser.add_argument("path", nargs="?", type=Path)
    feedback_list_parser.add_argument("--status", choices=tuple(sorted(VALID_FEEDBACK_STATUSES)), default=None)
    add_json_argument(feedback_list_parser)
    feedback_list_parser.set_defaults(func=feedback_list_command)

    feedback_candidates_parser = feedback_subparsers.add_parser("archive-candidates", help="list feedback rows ready for explicit archive")
    feedback_candidates_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(feedback_candidates_parser)
    feedback_candidates_parser.set_defaults(func=feedback_archive_candidates_command)

    feedback_triage_parser = feedback_subparsers.add_parser("triage", help="mark feedback Triaged and update next action")
    feedback_triage_parser.add_argument("path", nargs="?", type=Path)
    feedback_triage_parser.add_argument("id", type=validate_feedback_id)
    feedback_triage_parser.add_argument("--next-action", required=True, help="deterministic next handling step")
    feedback_triage_parser.add_argument("--evidence", default="", help="optional evidence or destination reference")
    add_write_arguments(feedback_triage_parser)
    feedback_triage_parser.set_defaults(func=feedback_triage_command)

    feedback_done_parser = feedback_subparsers.add_parser("done", help="mark feedback Done")
    feedback_done_parser.add_argument("path", nargs="?", type=Path)
    feedback_done_parser.add_argument("id", type=validate_feedback_id)
    feedback_done_parser.add_argument("--result", required=True, help="handling result")
    feedback_done_parser.add_argument("--evidence", required=True, help="evidence or destination reference")
    add_write_arguments(feedback_done_parser)
    feedback_done_parser.set_defaults(func=feedback_done_command)

    feedback_reject_parser = feedback_subparsers.add_parser("reject", help="mark feedback Rejected")
    feedback_reject_parser.add_argument("path", nargs="?", type=Path)
    feedback_reject_parser.add_argument("id", type=validate_feedback_id)
    feedback_reject_parser.add_argument("--reason", required=True, help="rejection reason")
    add_write_arguments(feedback_reject_parser)
    feedback_reject_parser.set_defaults(func=feedback_reject_command)

    feedback_archive_parser = feedback_subparsers.add_parser("archive", help="archive one Done or Rejected feedback row")
    feedback_archive_parser.add_argument("path", nargs="?", type=Path)
    feedback_archive_parser.add_argument("id", type=validate_feedback_id)
    feedback_archive_parser.add_argument("--reason", required=True, help="archive reason or destination evidence")
    feedback_archive_parser.add_argument("--date", type=validate_date, default=None, help="archive date in YYYY-MM-DD; defaults to today")
    add_write_arguments(feedback_archive_parser)
    feedback_archive_parser.set_defaults(func=feedback_archive_command)

    human_parser = subparsers.add_parser("human", help="manage human layer index and materials")
    human_subparsers = human_parser.add_subparsers(dest="human_command", required=True)

    human_index_parser = human_subparsers.add_parser("index", help="manage human/Human_Index.md")
    human_index_subparsers = human_index_parser.add_subparsers(dest="human_index_command", required=True)

    human_index_sync_parser = human_index_subparsers.add_parser("sync", help="sync human/Human_Index.md from notes, weekly, and reports")
    human_index_sync_parser.add_argument("path", nargs="?", type=Path)
    add_write_arguments(human_index_sync_parser)
    human_index_sync_parser.set_defaults(func=human_index_sync_command)

    human_list_parser = human_subparsers.add_parser("list", help="list human index items")
    human_list_parser.add_argument("path", nargs="?", type=Path)
    human_list_parser.add_argument("--status", choices=tuple(sorted(VALID_HUMAN_INDEX_STATUSES)), default=None)
    human_list_parser.add_argument("--type", default=None)
    add_json_argument(human_list_parser)
    human_list_parser.set_defaults(func=human_list_command)

    human_mark_parser = human_subparsers.add_parser("mark", help="mark a human index item by ID or path")
    human_mark_parser.add_argument("path", nargs="?", type=Path)
    human_mark_parser.add_argument("target", help="human index ID or path, for example H001 or reports/example.md")
    human_mark_parser.add_argument("--status", choices=tuple(sorted(VALID_HUMAN_INDEX_STATUSES)), required=True)
    human_mark_parser.add_argument("--extracted-to", default="", help="path or note describing where the material was organized")
    human_mark_parser.add_argument("--note", default="", help="status note")
    add_write_arguments(human_mark_parser)
    human_mark_parser.set_defaults(func=human_mark_command)

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

    doctor_parser = subparsers.add_parser("doctor", help="diagnose and safely repair context health issues")
    doctor_parser.add_argument("path", nargs="?", type=Path)
    doctor_parser.add_argument("--projects", nargs="+", type=Path, default=None, help="diagnose multiple projects independently")
    doctor_parser.add_argument("--fix", choices=("none", "safe", "evidence"), default="none", help="repair level to apply")
    doctor_parser.add_argument("--report", action="store_true", help="write a human-readable doctor report")
    doctor_parser.add_argument("--draft-semantic", action="store_true", help="write a reviewable semantic writeback draft")
    doctor_parser.add_argument("--today", type=validate_date, default=None, help="override today's date for deterministic checks")
    doctor_parser.add_argument("--force", action="store_true", help="replace an existing doctor report or semantic draft")
    add_write_arguments(doctor_parser)
    doctor_parser.set_defaults(func=doctor_command)

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
    task_parser.add_argument("--workstream", action="append", default=None, help="owning Workstream id; can be repeated")
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

    reference_parser = new_subparsers.add_parser("reference", help="create a reference Markdown document")
    reference_parser.add_argument("path", nargs="?", type=Path)
    reference_parser.add_argument("--file", default=None, help="target path under reference/, defaults to reference/<title-slug>.md")
    reference_parser.add_argument("--title", required=True, help="reference title")
    reference_parser.add_argument("--status", choices=("Draft", "Active", "Archived"), default="Draft")
    reference_parser.add_argument("--summary", required=True, help="one-line reference summary")
    reference_parser.add_argument("--body", action="append", default=None, help="reference body item; can be repeated")
    reference_parser.add_argument("--next-action", default="无。", help="next action for this reference")
    reference_parser.add_argument("--force", action="store_true", help="replace an existing reference file")
    add_write_arguments(reference_parser)
    reference_parser.set_defaults(func=new_reference_command)

    rule_parser = new_subparsers.add_parser("rule", help="create a rule file and update Rules_Index.md")
    rule_parser.add_argument("path", nargs="?", type=Path)
    rule_parser.add_argument("--file", default=None, help="target path under rules/, defaults to rules/<title-slug>.md")
    rule_parser.add_argument("--title", required=True, help="rule title")
    rule_parser.add_argument("--condition", required=True, help="when this rule should be read")
    rule_parser.add_argument("--purpose", required=True, help="one-line purpose for Rules_Index.md")
    rule_parser.add_argument("--rule", action="append", required=True, help="rule statement; can be repeated")
    rule_parser.add_argument("--rationale", default="", help="why this rule exists")
    rule_parser.add_argument("--scope", default="", help="where this rule applies")
    rule_parser.add_argument("--non-goal", default="", help="what this rule does not do")
    rule_parser.add_argument("--force", action="store_true", help="replace an existing rule file or index row")
    add_write_arguments(rule_parser)
    rule_parser.set_defaults(func=new_rule_command)

    feedback_parser = new_subparsers.add_parser("feedback", help="add a row to active/Feedback_Inbox.md")
    feedback_parser.add_argument("path", nargs="?", type=Path)
    feedback_parser.add_argument("--id", default=None, help="feedback id in F001 format; defaults to next id")
    feedback_parser.add_argument("--status", choices=tuple(sorted(VALID_FEEDBACK_STATUSES)), default="Open")
    feedback_parser.add_argument("--type", required=True, help="feedback type, for example 需求, 问题, 改进")
    feedback_parser.add_argument("--content", required=True, help="feedback content summary")
    feedback_parser.add_argument("--source", default=None, help="feedback source; defaults to today's date plus manual")
    feedback_parser.add_argument("--next-action", default="待 triage。", help="planned next handling step")
    feedback_parser.add_argument("--force", action="store_true", help="replace an existing feedback row with the same id")
    add_write_arguments(feedback_parser)
    feedback_parser.set_defaults(func=new_feedback_command)

    human_note_parser = new_subparsers.add_parser("human-note", help="add a row to human/Human_Notes.md")
    human_note_parser.add_argument("path", nargs="?", type=Path)
    human_note_parser.add_argument("--id", type=validate_human_note_id, default=None, help="human note id in H001 format; defaults to next id")
    human_note_parser.add_argument("--status", choices=tuple(sorted(VALID_HUMAN_NOTE_STATUSES)), default="Open")
    human_note_parser.add_argument("--type", required=True, help="human note type, for example 想法, 疑问, 计划")
    human_note_parser.add_argument("--content", required=True, help="human note content summary")
    human_note_parser.add_argument("--related", default="", help="related path or topic")
    human_note_parser.add_argument("--suggestion", default="", help="AI handling suggestion")
    human_note_parser.add_argument("--evidence", default="", help="optional evidence")
    human_note_parser.add_argument("--force", action="store_true", help="replace an existing human note row with the same id")
    add_write_arguments(human_note_parser)
    human_note_parser.set_defaults(func=new_human_note_command)

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
    _sync_runtime_part_globals()
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
        continuation_coordination_commands.emit_pending_challenge_probe(args)
        duration_ms = int((time.perf_counter() - started) * 1000)
        record_usage_event(args, exit_code, duration_ms)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
