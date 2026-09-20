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
from ai_context_framework import runtime_exports
from ai_context_framework.cli_arguments import add_json_argument, add_write_arguments
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
from ai_context_framework.commands import workstream_parsers
from ai_context_framework.commands import worktree as worktree_commands
from ai_context_framework.commands import continuation_group_parsers
from ai_context_framework.commands import observer as observer_commands
from ai_context_framework.commands import continuation_coordination as continuation_coordination_commands
from ai_context_framework.commands import continuation_execution as continuation_execution_commands
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
from ai_context_framework.commands.log import register_log_parsers
from ai_context_framework.sensitive_data import redact_credential_like_text
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
    SafeArgumentParser,
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
    refuse_retired_owner_arguments,
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
)
from ai_context_framework.version import VERSION


ROOT = Path(__file__).resolve().parents[1]

VALID_PLAN_STATUSES = {"Active", "Paused", "Done", "Empty"}
VALID_DECISION_STATUSES = {"Active", "Proposed", "Superseded", "Rejected", "Deprecated"}
VALID_WORKSTREAM_STAGE_STATUSES = {"Pending", "Active", "Blocked", "Done", "Skipped", "Cancelled"}
ACTIVE_WORKSTREAM_STATUSES = {"Active", "Blocked", "ReadyToMerge", "Merging"}
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
    runtime_exports.install_runtime_parts(globals(), _RUNTIME_PART_MODULES)
    _sync_runtime_part_globals()


def _sync_runtime_part_globals() -> None:
    for module in _RUNTIME_PART_MODULES:
        module.ROOT = ROOT


def set_root(root: Path) -> Path:
    """Bind ROOT and propagate it to the installed runtime parts.

    This is the supported entry point for relocating ROOT (the legacy top-level
    ``acf`` shim uses it). Assigning ``runtime.ROOT`` directly leaves the injected
    part modules pointing at the previous value, so callers must go through here.
    """

    global ROOT
    ROOT = root
    _sync_runtime_part_globals()
    return ROOT


_install_runtime_parts()


def build_parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(
        prog="acf",
        description="Generate, simplify, and check AI context framework templates.",
    )
    parser.set_defaults(json=False)
    add_json_argument(parser)
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_check_commands.register_status_parser(subparsers, add_json_argument, status_command)

    next_status_commands.register_next_parser(
        subparsers, add_json_argument, next_status_commands.next_command
    )

    init_upgrade_commands.register_init_parser(
        subparsers, add_write_arguments, init_command
    )

    init_upgrade_commands.register_simplify_parser(
        subparsers, add_write_arguments, simplify_command
    )

    init_upgrade_commands.register_upgrade_parser(
        subparsers, add_write_arguments, upgrade_command
    )

    status_check_commands.register_check_parser(subparsers, add_json_argument, check_command)

    edit_link_commands.register_linkify_parser(
        subparsers, add_write_arguments, linkify_command
    )

    edit_link_commands.register_link_parser(
        subparsers, add_write_arguments, link_add_command
    )

    links_commands.register_links_parser(subparsers, add_json_argument)

    register_log_parsers(
        subparsers,
        add_json_argument,
        enable_handler=log_enable_command,
        disable_handler=log_disable_command,
        status_handler=log_status_command,
        tail_handler=log_tail_command,
        summarize_handler=log_summarize_command,
        feedback_handler=log_feedback_command,
        prune_handler=log_prune_command,
    )

    versioning_commands.register_version_parser(
        subparsers,
        add_json_argument,
        add_write_arguments,
        show_handler=version_show_command,
        set_handler=version_set_command,
    )

    workstream_parsers.register_workstream_parsers(
        subparsers,
        add_json_argument,
        add_write_arguments,
        handlers={
            "init": workstream_init_command,
            "status": workstream_status_command,
            "list": workstream_list_command,
            "dashboard": workstream_dashboard_command,
            "archive-candidates": workstream_archive_candidates_command,
            "archive-draft": workstream_archive_draft_command,
            "archive": workstream_archive_command,
            "sync": workstream_sync_command,
            "stage-add": workstream_stage_add_command,
            "stage-list": workstream_stage_list_command,
            "stage-done": workstream_stage_done_command,
            "focus": workstream_focus_command,
            "show": workstream_show_command,
            "context": workstream_context_command,
            "next-actions": workstream_next_actions_command,
            "preflight": workstream_preflight_command,
            "add": workstream_add_command,
            "reserve": workstream_reserve_command,
            "set": workstream_set_command,
            "block": workstream_block_command,
            "cancel": workstream_cancel_command,
            "merge-request": workstream_merge_request_command,
            "merge-start": workstream_merge_start_command,
            "ready": workstream_ready_command,
            "done": workstream_done_command,
            "claim": workstream_claim_command,
            "scope-add": workstream_scope_add_command,
            "guard": workstream_guard_command,
            "note": workstream_note_command,
        },
    )

    worktree_commands.register_worktree_parsers(subparsers, add_json_argument)

    observer_commands.register_observer_parser(subparsers, add_json_argument)

    continuation_group_parsers.register_continuation_parser(subparsers, add_json_argument)

    plan_task_commands.register_plan_parsers(
        subparsers,
        add_json_argument,
        add_write_arguments,
        init_handler=plan_init_command,
        add_task_handler=plan_add_task_command,
        set_task_handler=plan_set_task_command,
        focus_handler=plan_focus_command,
        complete_handler=plan_complete_command,
        status_handler=plan_status_command,
        reference_list_handler=plan_reference_list_command,
        reference_add_handler=plan_reference_add_command,
        reference_remove_handler=plan_reference_remove_command,
        stage_list_handler=plan_stage_list_command,
        stage_add_handler=plan_stage_add_command,
        stage_set_handler=plan_stage_set_command,
        stage_done_handler=plan_stage_done_command,
    )

    plan_task_commands.register_task_parser(
        subparsers,
        add_write_arguments,
        start_handler=task_start_command,
        done_handler=task_done_command,
        block_handler=task_block_command,
        clear_handler=task_clear_command,
    )

    archive_commands.register_archive_parser(
        subparsers,
        add_json_argument,
        add_write_arguments,
        current_task_handler=archive_current_task_command,
        task_plan_handler=archive_task_plan_command,
        list_handler=archive_list_command,
        sync_handler=archive_sync_command,
    )

    decisions_commands.register_decisions_parser(
        subparsers, add_write_arguments, decisions_sync_command
    )

    knowledge_commands.register_knowledge_parsers(
        subparsers,
        add_json_argument,
        add_write_arguments,
        draft_handler=knowledge_draft_command,
        apply_handler=knowledge_apply_command,
        list_handler=knowledge_list_command,
        show_handler=knowledge_show_command,
        mark_handler=knowledge_mark_command,
        sync_handler=knowledge_sync_command,
    )

    next_status_commands.register_draft_parser(
        subparsers, add_json_argument, next_status_commands.draft_status_command
    )

    feedback_commands.register_feedback_parsers(
        subparsers,
        add_json_argument,
        add_write_arguments,
        list_handler=feedback_list_command,
        archive_candidates_handler=feedback_archive_candidates_command,
        triage_handler=feedback_triage_command,
        done_handler=feedback_done_command,
        reject_handler=feedback_reject_command,
        archive_handler=feedback_archive_command,
    )

    human_commands.register_human_parsers(
        subparsers,
        add_json_argument,
        add_write_arguments,
        index_sync_handler=human_index_sync_command,
        list_handler=human_list_command,
        mark_handler=human_mark_command,
    )

    review_audit_curate_commands.register_review_parser(
        subparsers, add_json_argument, review_stale_command
    )

    review_audit_curate_commands.register_audit_parser(
        subparsers, add_json_argument, audit_context_command
    )

    doctor_commands.register_doctor_parser(
        subparsers, add_write_arguments, doctor_command
    )

    review_audit_curate_commands.register_curate_parser(
        subparsers, add_json_argument, add_write_arguments, curate_draft_command
    )

    new_context_commands.register_new_parsers(
        subparsers,
        add_write_arguments,
        worklog_handler=new_worklog_command,
        adr_handler=new_adr_command,
        task_handler=new_task_command,
        source_handler=new_source_command,
        reference_handler=new_reference_command,
        rule_handler=new_rule_command,
        feedback_handler=new_feedback_command,
        human_note_handler=new_human_note_command,
    )

    new_context_commands.register_writeback_parser(
        subparsers, add_write_arguments, writeback_draft_command
    )

    edit_link_commands.register_edit_parsers(
        subparsers,
        add_json_argument,
        add_write_arguments,
        section_get_handler=edit_section_get_command,
        section_replace_handler=edit_section_replace_command,
        section_append_handler=edit_section_append_command,
        table_upsert_handler=edit_table_upsert_command,
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    argv_list, execution_child_argv = continuation_execution_commands.split_cli_child_argv(argv_list)
    refusal = refuse_retired_owner_arguments(argv_list)
    if refusal is not None:
        return refusal
    parser = build_parser()
    started = time.perf_counter()
    args: argparse.Namespace | None = None
    exit_code = 0
    try:
        args = parser.parse_args(argv_list)
        if execution_child_argv is not None:
            args.child_argv = execution_child_argv
        exit_code = run_with_context_lock(args)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            exit_code = exc.code
        else:
            message = redact_credential_like_text(str(exc.code))[0]
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
        message = redact_credential_like_text(str(exc))[0]
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
