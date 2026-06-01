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
from ai_context_framework.commands import archive as archive_commands
from ai_context_framework.commands import review_audit_curate as review_audit_curate_commands
from ai_context_framework.commands import doctor as doctor_commands
from ai_context_framework.commands import plan_task as plan_task_commands
from ai_context_framework.commands import workstream as workstream_commands
from ai_context_framework.commands.log import (
    build_usage_event,
    check_counts,
    command_label,
    context_location_for_args,
    log_disable_command,
    log_enable_command,
    log_feedback_command,
    log_prune_command,
    log_status_command,
    log_summarize_command,
    log_tail_command,
    record_usage_event,
    relative_usage_paths,
    usage_loggable,
)
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
    "Merging": {"ReadyToMerge", "Done", "Cancelled"},
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


def write_command_context_root(args: argparse.Namespace) -> Path | None:
    command = getattr(args, "command", None)
    if command in {"init", "simplify"}:
        return None
    if command == "doctor":
        doctor_writes = (
            getattr(args, "fix", "none") != "none"
            or bool(getattr(args, "report", False))
            or bool(getattr(args, "draft_semantic", False))
        )
        if doctor_writes and not getattr(args, "projects", None):
            return require_context_root(getattr(args, "path", None))
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
            "merge-start",
            "ready",
            "done",
            "archive-draft",
            "archive",
            "focus",
            "claim",
            "scope-add",
            "note",
        }:
            return require_context_root(getattr(args, "path", None))
        return None
    if command in {"upgrade", "new", "writeback", "plan", "task", "archive", "decisions", "knowledge", "curate", "linkify"}:
        return require_context_root(getattr(args, "path", None))
    if command == "human":
        if getattr(args, "human_command", None) == "mark":
            return require_context_root(getattr(args, "path", None))
        if getattr(args, "human_command", None) == "index" and getattr(args, "human_index_command", None) == "sync":
            return require_context_root(getattr(args, "path", None))
        return None
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
        root / "human" / "Human_Index.md",
        root / "human" / "Human_Notes.md",
        root / "human" / "weekly" / ".gitkeep",
        root / "human" / "reports" / ".gitkeep",
    ]


def skip_placeholder_check(root: Path, rel_file: str) -> bool:
    return root.resolve() != TEMPLATE_DIR.resolve() and rel_file in TEMPLATE_EXAMPLE_FILES


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


def decisions_index_path(root: Path) -> Path:
    return root / "reference" / "Decisions_Index.md"


def decision_title_from_text(text: str, fallback: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    title = re.sub(r"^#\s*", "", first_line).strip()
    title = re.sub(r"^ADR-\d{4}\s*[-：:]\s*", "", title).strip()
    title = re.sub(r"^ADR[：:]\s*", "", title).strip()
    return title or fallback


def decision_summary_from_text(text: str) -> str:
    summary = safe_section_body_from_text(text, "## 摘要")
    if not summary:
        summary = safe_section_body_from_text(text, "## 决策")
    return next((line.strip() for line in summary.splitlines() if line.strip()), "") or "无。"


def render_decisions_index_table(rows: Sequence[dict[str, str]]) -> str:
    lines = [
        "| ID | 标题 | 状态 | 摘要 | 详情 |",
        "|---|---|---|---|---|",
    ]
    if rows:
        for row in rows:
            lines.append(render_table_row([row["id"], row["title"], row["status"], row["summary"], f"`{row['detail']}`"]))
    else:
        lines.append("| 暂无 |  |  |  |  |")
    return "\n".join(lines)


def collect_decision_sync_rows(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    warnings: list[str] = []
    decisions_dir = root / "decisions"
    if not decisions_dir.exists():
        return rows, skipped, warnings

    for path in sorted(decisions_dir.glob("ADR-*.md")):
        if path.name == "ADR-0001-template.md":
            continue
        match = re.match(r"^(ADR-\d{4})\.md$", path.name)
        rel = path.relative_to(root).as_posix()
        if match is None:
            skipped.append({"path": rel, "reason": "decision file name does not use ADR-NNNN.md"})
            continue
        status = extract_heading_value(path, "## 状态") or ""
        if status not in VALID_DECISION_STATUSES:
            skipped.append({"id": match.group(1), "path": rel, "reason": f"invalid or missing decision status `{status}`"})
            warnings.append(f"{rel}: skipped invalid or missing decision status `{status}`")
            continue
        text = read_text(path)
        rows.append(
            {
                "id": match.group(1),
                "title": decision_title_from_text(text, match.group(1)),
                "status": status,
                "summary": decision_summary_from_text(text),
                "detail": rel,
            }
        )
    return rows, skipped, warnings


def skipped_missing_generated_decision_details(root: Path, index_text: str) -> list[dict[str, str]]:
    if DECISIONS_INDEX_MARKER_START not in index_text or DECISIONS_INDEX_MARKER_END not in index_text:
        return []
    start = index_text.index(DECISIONS_INDEX_MARKER_START) + len(DECISIONS_INDEX_MARKER_START)
    end = index_text.index(DECISIONS_INDEX_MARKER_END, start)
    marker_body = index_text[start:end]
    skipped: list[dict[str, str]] = []
    index_path = decisions_index_path(root)
    for cells in parse_markdown_table_rows(marker_body):
        if len(cells) < 5 or cells[0] in {"ID", "暂无"}:
            continue
        ref = strip_code_ticks(cells[4])
        if should_check_ref(ref) and resolve_ref(root, index_path, ref) is None:
            skipped.append({"id": cells[0], "path": ref, "reason": "detail source is missing"})
    return skipped


def decisions_sync_command(args: argparse.Namespace) -> int:
    return decisions_commands.decisions_sync_command(
        args,
        deps=decisions_commands.DecisionsDependencies(
            maybe_check_after=maybe_check_after,
            decisions_index_path=decisions_index_path,
            read_text=read_text,
            collect_decision_sync_rows=collect_decision_sync_rows,
            skipped_missing_generated_decision_details=skipped_missing_generated_decision_details,
            render_decisions_index_table=render_decisions_index_table,
        ),
    )


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


def normalize_new_object_target(
    root: Path,
    raw_file: str | None,
    title: str,
    directory: str,
    *,
    forbidden_prefixes: Sequence[str] = (),
) -> Path:
    if raw_file:
        normalized = raw_file.replace("\\", "/").strip()
        if not normalized:
            raise SystemExit("target file cannot be empty")
        target = Path(normalized)
    else:
        target = Path(directory) / f"{slugify_file_stem(title)}.md"
        normalized = target.as_posix()

    if target.is_absolute():
        raise SystemExit("target file must be relative to the context root")
    if target.suffix.lower() != ".md":
        raise SystemExit("target file must be Markdown (.md)")
    if normalized.startswith("../") or "/../" in normalized or normalized in {".", ".."}:
        raise SystemExit("target file is outside context root")
    if not normalized.startswith(f"{directory}/"):
        raise SystemExit(f"target file must live under {directory}/")
    for prefix in forbidden_prefixes:
        if normalized.startswith(prefix):
            raise SystemExit(f"target file is managed by another command: {prefix}")

    resolved = (root / target).resolve()
    if not is_relative_to(resolved, root.resolve()):
        raise SystemExit("target file is outside context root")
    return resolved


def render_reference_document(title: str, status: str, summary: str, body_items: Sequence[str], next_action: str) -> str:
    body = "\n".join(f"{index}. {item}" for index, item in enumerate(body_items, start=1))
    return f"""# {title}

本文件记录可长期按需读取的 reference 内容。

---

## 状态

{status}

---

## 摘要

{summary}

---

## 内容

{body}

---

## 后续动作

{next_action}
"""


def render_rule_document(
    title: str,
    condition: str,
    rules: Sequence[str],
    rationale: str,
    scope: str,
    non_goal: str,
) -> str:
    rule_lines = "\n".join(f"{index}. {item}" for index, item in enumerate(rules, start=1))
    return f"""# {title}

本文件记录按需读取的项目规则。

---

## 读取条件

{condition}

---

## 规则

{rule_lines}

---

## 理由

{rationale}

---

## 适用范围

{scope}

---

## 非目标

{non_goal}
"""


def render_rules_index() -> str:
    template_path = TEMPLATE_DIR / "rules" / "Rules_Index.md"
    if template_path.exists():
        return read_text(template_path)
    return f"""本文件是规则系统索引。

规则按读取成本和触发条件分层。AI 不应默认读取全部规则，而应先读 `Always_Active.md`，再按任务类型补充读取。

## 默认规则

{RULES_INDEX_TABLE_HEADER}
|---|---|---|
| `Always_Active.md` | 每次协作默认读取 | 核心事实边界和上下文使用规则 |

## 按需规则

{RULES_INDEX_TABLE_HEADER}
|---|---|---|

## 冲突处理

1. 用户当前消息优先于规则文件。
2. 更具体的规则优先于更通用的规则。
3. 如果规则和事实源冲突，先指出冲突，再按事实源优先级判断。
4. 不确定时，只读取与当前任务直接相关的规则，避免扩大上下文噪音。
"""


def upsert_rules_index(
    index_path: Path,
    file_name: str,
    condition: str,
    purpose: str,
    force: bool,
    dry_run: bool,
) -> bool:
    if index_path.exists():
        lines = read_text(index_path).splitlines()
        created = False
    else:
        lines = render_rules_index().splitlines()
        created = True

    heading_index = next((index for index, line in enumerate(lines) if line.strip() == "## 按需规则"), None)
    if heading_index is None:
        raise SystemExit(f"rules index on-demand section was not found: {index_path}")
    header_index = next(
        (
            index
            for index in range(heading_index + 1, len(lines))
            if lines[index].strip() == RULES_INDEX_TABLE_HEADER
        ),
        None,
    )
    if header_index is None or header_index + 1 >= len(lines):
        raise SystemExit(f"rules index on-demand table was not found: {index_path}")

    table_start = header_index + 2
    table_end = table_start
    while table_end < len(lines) and lines[table_end].strip().startswith("|"):
        table_end += 1

    existing_rows = lines[table_start:table_end]
    file_cell = f"`{file_name}`"
    if any(row_date(row) == file_cell for row in existing_rows) and not force:
        raise SystemExit(f"rules index already contains rule: {file_name}")

    new_row = render_table_row([file_cell, condition, purpose])
    kept_rows = [row for row in existing_rows if row_date(row) not in {file_cell, "暂无"} and row.strip()]
    rows = kept_rows + [new_row]
    rows.sort(key=row_date)
    updated = lines[:table_start] + rows + lines[table_end:]
    updated_text = "\n".join(updated).rstrip() + "\n"
    changed = created or updated_text != (read_text(index_path) if index_path.exists() else "")
    if changed and not dry_run:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(updated_text, encoding="utf-8")
    return changed


def next_feedback_id(rows: Sequence[dict[str, str]]) -> str:
    numbers: list[int] = []
    for row in rows:
        match = re.match(r"^F(\d{3})$", row.get("ID", ""))
        if match:
            numbers.append(int(match.group(1)))
    return f"F{(max(numbers) + 1) if numbers else 1:03d}"


def next_human_note_id(rows: Sequence[dict[str, str]]) -> str:
    numbers: list[int] = []
    for row in rows:
        match = re.match(r"^H(\d{3})$", row.get("ID", ""))
        if match:
            numbers.append(int(match.group(1)))
    return f"H{(max(numbers) + 1) if numbers else 1:03d}"


def feedback_index_row(
    feedback_id: str,
    status: str,
    feedback_type: str,
    content: str,
    source: str,
    next_action: str,
) -> str:
    return render_table_row([feedback_id, status, feedback_type, content, source, next_action])


def human_note_row(
    note_id: str,
    status: str,
    note_type: str,
    content: str,
    related: str,
    suggestion: str,
    evidence: str,
) -> str:
    return render_table_row([note_id, status, note_type, content, related, suggestion, evidence])


def human_index_row(
    item_id: str,
    status: str,
    item_type: str,
    title: str,
    path: str,
    item_date: str,
    extracted_to: str,
    note: str,
) -> str:
    return render_table_row([item_id, status, item_type, title, path, item_date, extracted_to, note])


def replace_table_rows(
    text: str,
    header: str,
    rows: Sequence[str],
) -> str:
    lines = text.splitlines()
    table = find_table(lines, header)
    updated = lines[: table.body_start] + list(rows) + lines[table.body_end :]
    return "\n".join(updated).rstrip() + "\n"


def read_table_rows_by_header(path: Path, header: str) -> list[dict[str, str]]:
    text = read_text(path)
    table = find_table(text.splitlines(), header)
    rows: list[dict[str, str]] = []
    for line in text.splitlines()[table.body_start : table.body_end]:
        cells = split_table_line(line)
        if len(cells) < len(table.headers) or cells[0] == "暂无":
            continue
        rows.append(dict(zip(table.headers, cells)))
    return rows


def upsert_feedback_inbox(
    inbox_path: Path,
    feedback_id: str,
    status: str,
    feedback_type: str,
    content: str,
    source: str,
    next_action: str,
    force: bool,
    dry_run: bool,
) -> bool:
    if not inbox_path.exists():
        raise SystemExit(f"feedback inbox does not exist: {inbox_path}")

    text = read_text(inbox_path)
    lines = text.splitlines()
    table = find_table(lines, FEEDBACK_TABLE_HEADER)
    existing_rows = lines[table.body_start : table.body_end]
    if any(row_date(row) == feedback_id for row in existing_rows) and not force:
        raise SystemExit(f"feedback inbox already contains id: {feedback_id}")

    new_row = feedback_index_row(feedback_id, status, feedback_type, content, source, next_action)
    kept_rows = [
        row
        for row in existing_rows
        if row_date(row) not in {feedback_id, "暂无"} and row.strip()
    ]
    rows = kept_rows + [new_row]
    rows.sort(key=row_date)
    updated = lines[: table.body_start] + rows + lines[table.body_end :]
    updated_text = "\n".join(updated).rstrip() + "\n"
    changed = updated_text != text
    if changed and not dry_run:
        inbox_path.write_text(updated_text, encoding="utf-8")
    return changed


def feedback_inbox_path(root: Path) -> Path:
    return root / "active" / "Feedback_Inbox.md"


def human_notes_path(root: Path) -> Path:
    return root / "human" / "Human_Notes.md"


def human_index_path(root: Path) -> Path:
    return root / "human" / "Human_Index.md"


def feedback_archive_path(root: Path, archive_date: date) -> Path:
    return root / "archive" / "feedback" / f"{archive_date.strftime('%Y-%m')}.md"


def find_feedback_row(rows: Sequence[dict[str, str]], feedback_id: str) -> dict[str, str] | None:
    return next((row for row in rows if row.get("ID") == feedback_id), None)


def human_note_status_to_index_status(status: str) -> str:
    return {
        "Open": "Open",
        "Triaged": "Reviewed",
        "Done": "Extracted",
        "Rejected": "Archived",
    }.get(status, "Open")


def human_index_row_to_payload(row: dict[str, str]) -> dict[str, str]:
    return {
        "id": row.get("ID", ""),
        "status": row.get("状态", ""),
        "type": row.get("类型", ""),
        "title": row.get("标题", ""),
        "path": clean_human_index_path_cell(row.get("路径", "")),
        "date": row.get("日期", ""),
        "extracted_to": row.get("已整理到", ""),
        "note": row.get("备注", ""),
    }


def human_index_row_from_payload(row: dict[str, str]) -> str:
    return human_index_row(
        row.get("ID", ""),
        row.get("状态", ""),
        row.get("类型", ""),
        row.get("标题", ""),
        row.get("路径", ""),
        row.get("日期", ""),
        row.get("已整理到", ""),
        row.get("备注", ""),
    )


def read_human_index_rows(index_path: Path) -> list[dict[str, str]]:
    return read_table_rows_by_header(index_path, HUMAN_INDEX_TABLE_HEADER)


def clean_human_index_path_cell(value: str) -> str:
    cleaned = value.strip().strip("`")
    link_match = MARKDOWN_LINK_RE.fullmatch(cleaned)
    if link_match:
        cleaned = link_match.group(3)
    cleaned = clean_markdown_link_target(cleaned).replace("\\", "/").strip()
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if cleaned.startswith("human/"):
        cleaned = cleaned[len("human/") :]
    return cleaned


def human_index_key(row: dict[str, str]) -> str:
    item_id = row.get("ID", "").strip()
    if item_id and item_id != "暂无":
        return f"id:{item_id}"
    return f"path:{clean_human_index_path_cell(row.get('路径', ''))}"


def parse_date_from_text(value: str) -> str:
    match = re.search(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", value)
    return match.group(0) if match else "未标注"


def markdown_title(path: Path) -> str:
    try:
        for line in read_text(path).splitlines():
            match = re.match(r"^#\s+(.+?)\s*$", line)
            if match:
                return match.group(1).strip()
    except UnicodeDecodeError:
        pass
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.name


def human_note_index_item(row: dict[str, str], today: str | None = None) -> dict[str, str]:
    note_id = row.get("ID", "").strip()
    content = row.get("内容", "").strip()
    return {
        "ID": note_id,
        "状态": human_note_status_to_index_status(row.get("状态", "")),
        "类型": row.get("类型", "").strip() or "笔记",
        "标题": content[:80] if content else note_id,
        "路径": "Human_Notes.md",
        "日期": today or "未标注",
        "已整理到": "未整理。",
        "备注": row.get("AI 处理建议", "").strip() or "来自 Human_Notes.md。",
    }


def human_file_index_item(root: Path, path: Path, item_type: str) -> dict[str, str]:
    rel = path.relative_to(root / "human").as_posix()
    return {
        "ID": "",
        "状态": "Open",
        "类型": item_type,
        "标题": markdown_title(path),
        "路径": rel,
        "日期": parse_date_from_text(path.name),
        "已整理到": "未整理。",
        "备注": "由 human index sync 发现。",
    }


def collect_human_index_items(root: Path, *, note_date: str | None = None) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    note_path = human_notes_path(root)
    if note_path.exists():
        for row in read_table_rows_by_header(note_path, HUMAN_NOTE_TABLE_HEADER):
            note_id = row.get("ID", "").strip()
            if note_id and note_id != "暂无":
                items.append(human_note_index_item(row, note_date))
    for directory, item_type in ((root / "human" / "weekly", "weekly"), (root / "human" / "reports", "report")):
        if not directory.is_dir():
            continue
        for md_file in sorted(directory.glob("*.md")):
            items.append(human_file_index_item(root, md_file, item_type))
    return items


def merge_human_index_rows(existing_rows: Sequence[dict[str, str]], discovered: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    rows_by_key: dict[str, dict[str, str]] = {}
    ordered_keys: list[str] = []
    for row in existing_rows:
        key = human_index_key(row)
        if key in {"id:", "path:"}:
            continue
        rows_by_key[key] = dict(row)
        ordered_keys.append(key)
    for item in discovered:
        key = human_index_key(item)
        if key in {"id:", "path:"}:
            continue
        if key in rows_by_key:
            existing = rows_by_key[key]
            for field in ("类型", "标题", "日期"):
                current = existing.get(field, "").strip()
                candidate = item.get(field, "").strip()
                if current in {"", "未标注", "无。"} and candidate and candidate not in {"未标注", "无。"}:
                    existing[field] = candidate
            continue
        rows_by_key[key] = dict(item)
        ordered_keys.append(key)
    ordered_keys.sort(key=lambda key: (rows_by_key[key].get("日期", ""), rows_by_key[key].get("路径", ""), rows_by_key[key].get("ID", "")))
    return [rows_by_key[key] for key in ordered_keys]


def write_human_index(index_path: Path, rows: Sequence[dict[str, str]], dry_run: bool) -> bool:
    text = read_text(index_path) if index_path.exists() else render_human_index()
    rendered_rows = [human_index_row_from_payload(row) for row in rows] or ["| 暂无 |  |  |  |  |  |  |  |"]
    updated = replace_table_rows(text, HUMAN_INDEX_TABLE_HEADER, rendered_rows)
    changed = updated != text
    if changed and not dry_run:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(updated, encoding="utf-8")
    return changed


def sync_human_index(root: Path, dry_run: bool, *, note_date: str | None = None) -> tuple[bool, list[dict[str, str]], Path]:
    index_path = human_index_path(root)
    existed = index_path.exists()
    if not index_path.exists() and not dry_run:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(render_human_index(), encoding="utf-8")
    existing_rows = read_human_index_rows(index_path) if index_path.exists() else []
    rows = merge_human_index_rows(existing_rows, collect_human_index_items(root, note_date=note_date))
    changed = write_human_index(index_path, rows, dry_run) if index_path.exists() else True
    if not existed:
        changed = True
    return changed, rows, index_path


def find_human_index_row(rows: Sequence[dict[str, str]], target: str) -> dict[str, str] | None:
    normalized = clean_human_index_path_cell(target)
    for row in rows:
        if row.get("ID", "") == target:
            return row
        if clean_human_index_path_cell(row.get("路径", "")) == normalized:
            return row
    return None


def feedback_row_to_payload(row: dict[str, str]) -> dict[str, str]:
    return {
        "id": row.get("ID", ""),
        "status": row.get("状态", ""),
        "type": row.get("类型", ""),
        "content": row.get("内容", ""),
        "source": row.get("来源", ""),
        "next_action": row.get("后续处理", ""),
    }


def feedback_row_from_payload(row: dict[str, str]) -> str:
    return feedback_index_row(
        row.get("ID", ""),
        row.get("状态", ""),
        row.get("类型", ""),
        row.get("内容", ""),
        row.get("来源", ""),
        row.get("后续处理", ""),
    )


def update_feedback_row(
    inbox_path: Path,
    feedback_id: str,
    updates: dict[str, str],
    dry_run: bool,
) -> tuple[bool, dict[str, str]]:
    if not inbox_path.exists():
        raise SystemExit(f"feedback inbox does not exist: {inbox_path}")
    text = read_text(inbox_path)
    rows = read_feedback_rows(inbox_path)
    target = find_feedback_row(rows, feedback_id)
    if target is None:
        raise SystemExit(f"feedback_not_found: {feedback_id}")
    target.update(updates)
    rendered_rows = [feedback_row_from_payload(row) for row in rows]
    updated_text = replace_table_rows(text, FEEDBACK_TABLE_HEADER, rendered_rows)
    changed = updated_text != text
    if changed and not dry_run:
        inbox_path.write_text(updated_text, encoding="utf-8")
    return changed, target


def remove_feedback_row(
    inbox_path: Path,
    feedback_id: str,
    dry_run: bool,
) -> tuple[bool, dict[str, str]]:
    if not inbox_path.exists():
        raise SystemExit(f"feedback inbox does not exist: {inbox_path}")
    text = read_text(inbox_path)
    rows = read_feedback_rows(inbox_path)
    target = find_feedback_row(rows, feedback_id)
    if target is None:
        raise SystemExit(f"feedback_not_found: {feedback_id}")
    remaining = [row for row in rows if row.get("ID") != feedback_id]
    rendered_rows = [feedback_row_from_payload(row) for row in remaining] or ["| 暂无 |  |  |  |  |  |"]
    updated_text = replace_table_rows(text, FEEDBACK_TABLE_HEADER, rendered_rows)
    changed = updated_text != text
    if changed and not dry_run:
        inbox_path.write_text(updated_text, encoding="utf-8")
    return changed, target


def render_feedback_archive(archive_month: str) -> str:
    return f"""# Feedback Archive {archive_month}

本文件保存已从 active/Feedback_Inbox.md 移出的反馈条目。归档条目是历史记录，不是当前事实源。

| 归档日期 | ID | 状态 | 类型 | 内容 | 来源 | 处理结果 | 归档原因 |
|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |
"""


def append_feedback_archive_row(
    archive_path: Path,
    archive_date: date,
    row: dict[str, str],
    reason: str,
    dry_run: bool,
) -> bool:
    text = read_text(archive_path) if archive_path.exists() else render_feedback_archive(archive_path.stem)
    lines = text.splitlines()
    header = "| 归档日期 | ID | 状态 | 类型 | 内容 | 来源 | 处理结果 | 归档原因 |"
    table = find_table(lines, header)
    existing_rows = [
        line
        for line in lines[table.body_start : table.body_end]
        if row_date(line) not in {"暂无", archive_date.isoformat()} or split_table_line(line)[1:2] != [row.get("ID", "")]
    ]
    new_row = render_table_row(
        [
            archive_date.isoformat(),
            row.get("ID", ""),
            row.get("状态", ""),
            row.get("类型", ""),
            row.get("内容", ""),
            row.get("来源", ""),
            row.get("后续处理", ""),
            reason,
        ]
    )
    rendered_rows = existing_rows + [new_row]
    updated = lines[: table.body_start] + rendered_rows + lines[table.body_end :]
    updated_text = "\n".join(updated).rstrip() + "\n"
    changed = updated_text != text
    if changed and not dry_run:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_text(updated_text, encoding="utf-8")
    return changed


def init_command(args: argparse.Namespace) -> int:
    return init_upgrade_commands.init_command(
        args,
        maybe_check_after=maybe_check_after,
        ensure_clean_target=ensure_clean_target,
        planned_init_files=planned_init_files,
        copy_selected_files=copy_selected_files,
        write_minimal_overrides=write_minimal_overrides,
        write_root_agents=write_root_agents,
    )


def simplify_command(args: argparse.Namespace) -> int:
    return init_upgrade_commands.simplify_command(
        args,
        maybe_check_after=maybe_check_after,
        ensure_clean_target=ensure_clean_target,
        planned_simplify_files=planned_simplify_files,
        copy_selected_files=copy_selected_files,
        copy_dynamic_minimal_files=copy_dynamic_minimal_files,
        write_minimal_overrides=write_minimal_overrides,
    )


def new_worklog_command(args: argparse.Namespace) -> int:
    return worklog_commands.new_worklog_command(args, maybe_check_after=maybe_check_after)


def new_context_deps() -> new_context_commands.NewContextDependencies:
    return new_context_commands.NewContextDependencies(
        maybe_check_after=maybe_check_after,
        next_adr_id=next_adr_id,
        render_adr=render_adr,
        update_decisions_index=update_decisions_index,
        extract_current_task_status=extract_current_task_status,
        normalize_items=normalize_items,
        render_current_task=render_current_task,
        read_text=read_text,
        update_sources_index=update_sources_index,
        normalize_new_object_target=normalize_new_object_target,
        render_reference_document=render_reference_document,
        upsert_rules_index=upsert_rules_index,
        render_rule_document=render_rule_document,
        feedback_inbox_path=feedback_inbox_path,
        read_feedback_rows=read_feedback_rows,
        next_feedback_id=next_feedback_id,
        upsert_feedback_inbox=upsert_feedback_inbox,
        human_notes_path=human_notes_path,
        read_table_rows_by_header=read_table_rows_by_header,
        next_human_note_id=next_human_note_id,
        human_note_row=human_note_row,
        row_date=row_date,
        replace_table_rows=replace_table_rows,
        human_index_path=human_index_path,
        sync_human_index=sync_human_index,
        render_writeback_draft=render_writeback_draft,
        human_note_table_header=HUMAN_NOTE_TABLE_HEADER,
    )


def new_adr_command(args: argparse.Namespace) -> int:
    return new_context_commands.new_adr_command(args, deps=new_context_deps())


def new_task_command(args: argparse.Namespace) -> int:
    return new_context_commands.new_task_command(args, deps=new_context_deps())


def new_source_command(args: argparse.Namespace) -> int:
    return new_context_commands.new_source_command(args, deps=new_context_deps())


def new_reference_command(args: argparse.Namespace) -> int:
    return new_context_commands.new_reference_command(args, deps=new_context_deps())


def new_rule_command(args: argparse.Namespace) -> int:
    return new_context_commands.new_rule_command(args, deps=new_context_deps())


def new_feedback_command(args: argparse.Namespace) -> int:
    return new_context_commands.new_feedback_command(args, deps=new_context_deps())


def new_human_note_command(args: argparse.Namespace) -> int:
    return new_context_commands.new_human_note_command(args, deps=new_context_deps())


def human_deps() -> human_commands.HumanDependencies:
    return human_commands.HumanDependencies(
        maybe_check_after=maybe_check_after,
        sync_human_index=sync_human_index,
        human_index_row_to_payload=human_index_row_to_payload,
        human_index_path=human_index_path,
        read_human_index_rows=read_human_index_rows,
        count_by_key=count_by_key,
        find_human_index_row=find_human_index_row,
        write_human_index=write_human_index,
    )


def feedback_deps() -> feedback_commands.FeedbackDependencies:
    return feedback_commands.FeedbackDependencies(
        maybe_check_after=maybe_check_after,
        feedback_inbox_path=feedback_inbox_path,
        read_feedback_rows=read_feedback_rows,
        feedback_row_to_payload=feedback_row_to_payload,
        count_by_key=count_by_key,
        update_feedback_row=update_feedback_row,
        feedback_archive_path=feedback_archive_path,
        read_text=read_text,
        find_feedback_row=find_feedback_row,
        remove_feedback_row=remove_feedback_row,
        append_feedback_archive_row=append_feedback_archive_row,
    )


def human_index_sync_command(args: argparse.Namespace) -> int:
    return human_commands.human_index_sync_command(args, deps=human_deps())


def human_list_command(args: argparse.Namespace) -> int:
    return human_commands.human_list_command(args, deps=human_deps())


def human_mark_command(args: argparse.Namespace) -> int:
    return human_commands.human_mark_command(args, deps=human_deps())


def feedback_list_command(args: argparse.Namespace) -> int:
    return feedback_commands.feedback_list_command(args, deps=feedback_deps())


def feedback_archive_candidates_command(args: argparse.Namespace) -> int:
    return feedback_commands.feedback_archive_candidates_command(args, deps=feedback_deps())


def feedback_triage_command(args: argparse.Namespace) -> int:
    return feedback_commands.feedback_triage_command(args, deps=feedback_deps())


def feedback_done_command(args: argparse.Namespace) -> int:
    return feedback_commands.feedback_done_command(args, deps=feedback_deps())


def feedback_reject_command(args: argparse.Namespace) -> int:
    return feedback_commands.feedback_reject_command(args, deps=feedback_deps())


def feedback_archive_command(args: argparse.Namespace) -> int:
    return feedback_commands.feedback_archive_command(args, deps=feedback_deps())


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
    return new_context_commands.writeback_draft_command(args, deps=new_context_deps())


def linkify_command(args: argparse.Namespace) -> int:
    return edit_link_commands.linkify_command(args, maybe_check_after=maybe_check_after)


def link_add_command(args: argparse.Namespace) -> int:
    return edit_link_commands.link_add_command(args, maybe_check_after=maybe_check_after)


def edit_section_get_command(args: argparse.Namespace) -> int:
    return edit_link_commands.edit_section_get_command(args)


def edit_section_replace_command(args: argparse.Namespace) -> int:
    return edit_link_commands.edit_section_replace_command(args, maybe_check_after=maybe_check_after)


def edit_section_append_command(args: argparse.Namespace) -> int:
    return edit_link_commands.edit_section_append_command(args, maybe_check_after=maybe_check_after)


def edit_table_upsert_command(args: argparse.Namespace) -> int:
    return edit_link_commands.edit_table_upsert_command(args, maybe_check_after=maybe_check_after)


def slugify_file_stem(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = re.sub(r"[^\w.-]+", "-", normalized, flags=re.UNICODE).strip(".-_")
    return normalized or hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]


def version_files() -> list[Path]:
    return versioning_commands.version_files(require_source_project_root())


def discover_source_project_root(start: Path | None = None) -> Path | None:
    return versioning_commands.discover_source_project_root(start, source_root=ROOT)


def require_source_project_root() -> Path:
    return versioning_commands.require_source_project_root(source_root=ROOT)


def read_project_versions() -> dict[str, str | None]:
    return versioning_commands.read_project_versions(source_root=ROOT)


def version_show_command(args: argparse.Namespace) -> int:
    return versioning_commands.version_show_command(args, source_root=ROOT)


def version_set_command(args: argparse.Namespace) -> int:
    return versioning_commands.version_set_command(args, source_root=ROOT)


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


def render_human_index() -> str:
    return f"""# Human Index

本文件是 human 层的可发现索引。`human/` 保存人类给 AI 上下文系统留下的主观、半结构化材料，包括理解、规划、疑问、解释、整理、随笔、复盘和汇报。

`human/` 默认不进入 AI 必读路径；只有用户明确要求整理/修改 human 内容、当前任务显式引用 human 材料，或需要追溯人工判断来源时才读取。

---

## Materials

{HUMAN_INDEX_TABLE_HEADER}
|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |

---

## 使用规则

1. `human/` 是输入信号层，不是 active 当前事实源。
2. `Human_Index.md` 只负责发现、状态和追溯，不代表索引条目已经被确认。
3. 已确认事实应整理到 `active/`、ADR、Knowledge、reference 或 worklog 的权威位置。
4. 工具可以机械同步索引；是否已整理为事实必须由人或 AI 语义判断。
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

{ARCHIVE_INDEX_MARKER_START}
{ARCHIVE_TABLE_HEADER}
|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |
{ARCHIVE_INDEX_MARKER_END}
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

{KNOWLEDGE_INDEX_MARKER_START}
{KNOWLEDGE_TABLE_HEADER}
|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |
{KNOWLEDGE_INDEX_MARKER_END}

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
        elif path.name == "Human_Index.md":
            template_human_index = TEMPLATE_DIR / "human" / "Human_Index.md"
            path.write_text(read_text(template_human_index) if template_human_index.exists() else render_human_index(), encoding="utf-8")
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
    return init_upgrade_commands.upgrade_command(
        args,
        maybe_check_after=maybe_check_after,
        ensure_upgrade_structure=ensure_upgrade_structure,
        upgrade_contract_payload=upgrade_contract_payload,
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


def plan_task_deps() -> plan_task_commands.PlanTaskDependencies:
    return plan_task_commands.PlanTaskDependencies(
        maybe_check_after=maybe_check_after,
        task_plan_path=task_plan_path,
        current_task_path=current_task_path,
        plan_reference_payload=plan_reference_payload,
        normalize_plan_reference_path=normalize_plan_reference_path,
        normalize_plan_reference_purpose=normalize_plan_reference_purpose,
        ensure_plan_reference_target=ensure_plan_reference_target,
        read_plan_references=read_plan_references,
        replace_or_add_plan_reference=replace_or_add_plan_reference,
        remove_plan_reference=remove_plan_reference,
        read_text=read_text,
        write_plan_references_text=write_plan_references_text,
        sync_current_task_reference_text=sync_current_task_reference_text,
        render_plan_reference=render_plan_reference,
        read_task_rows=read_task_rows,
        read_task_stage_rows=read_task_stage_rows,
        task_stage_payload=task_stage_payload,
        validate_task_stage_parent=validate_task_stage_parent,
        validate_task_stage_workstream=validate_task_stage_workstream,
        find_task_stage_row=find_task_stage_row,
        write_task_stage_rows=write_task_stage_rows,
        find_task_row=find_task_row,
        next_task_id=next_task_id,
        write_task_rows=write_task_rows,
        set_plan_focus=set_plan_focus,
        set_plan_status=set_plan_status,
        recommended_next_task=recommended_next_task,
        extract_heading_value=extract_heading_value,
        normalize_items=normalize_items,
        render_task_plan=render_task_plan,
        extract_current_task_status=extract_current_task_status,
        blocked_dependency_ids=blocked_dependency_ids,
        build_task_start_fields=build_task_start_fields,
        render_empty_current_task=render_empty_current_task,
    )


def plan_reference_list_command(args: argparse.Namespace) -> int:
    return plan_task_commands.plan_reference_list_command(args, deps=plan_task_deps())


def plan_reference_add_command(args: argparse.Namespace) -> int:
    return plan_task_commands.plan_reference_add_command(args, deps=plan_task_deps())


def plan_reference_remove_command(args: argparse.Namespace) -> int:
    return plan_task_commands.plan_reference_remove_command(args, deps=plan_task_deps())


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
    return plan_task_commands.plan_init_command(args, deps=plan_task_deps())


def plan_add_task_command(args: argparse.Namespace) -> int:
    return plan_task_commands.plan_add_task_command(args, deps=plan_task_deps())


def plan_set_task_command(args: argparse.Namespace) -> int:
    return plan_task_commands.plan_set_task_command(args, deps=plan_task_deps())


def plan_focus_command(args: argparse.Namespace) -> int:
    return plan_task_commands.plan_focus_command(args, deps=plan_task_deps())


def plan_complete_command(args: argparse.Namespace) -> int:
    return plan_task_commands.plan_complete_command(args, deps=plan_task_deps())


def plan_status_command(args: argparse.Namespace) -> int:
    return plan_task_commands.plan_status_command(args, deps=plan_task_deps())


def plan_stage_list_command(args: argparse.Namespace) -> int:
    return plan_task_commands.plan_stage_list_command(args, deps=plan_task_deps())


def plan_stage_add_command(args: argparse.Namespace) -> int:
    return plan_task_commands.plan_stage_add_command(args, deps=plan_task_deps())


def plan_stage_set_command(args: argparse.Namespace) -> int:
    return plan_task_commands.plan_stage_set_command(args, deps=plan_task_deps())


def plan_stage_done_command(args: argparse.Namespace) -> int:
    return plan_task_commands.plan_stage_done_command(args, deps=plan_task_deps())


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
    return plan_task_commands.task_start_command(args, deps=plan_task_deps())


def task_done_command(args: argparse.Namespace) -> int:
    return plan_task_commands.task_done_command(args, deps=plan_task_deps())


def task_block_command(args: argparse.Namespace) -> int:
    return plan_task_commands.task_block_command(args, deps=plan_task_deps())


def task_clear_command(args: argparse.Namespace) -> int:
    return plan_task_commands.task_clear_command(args, deps=plan_task_deps())


TERMINAL_SUBTASK_STATUSES = {"Done", "Skipped", "Superseded"}
TERMINAL_WORKSTREAM_STATUSES = {"Done", "Cancelled"}
DOCTOR_TERMINAL_WORKSTREAM_EXCESS_THRESHOLD = 5
DOCTOR_CONTEXT_LINE_THRESHOLD = 200
DOCTOR_CONTEXT_PROCESS_SIGNAL_LINE_THRESHOLD = 5
DOCTOR_ROOT_OUTPUT_THRESHOLD = 5
DOCTOR_DATA_REF_EXTENSIONS = ("csv", "json", "parquet", "xlsx", "yaml", "yml")
DOCTOR_BACKTICK_PATH_RE = re.compile(r"`([^`]+\.(?:csv|json|parquet|xlsx|yaml|yml))`", re.IGNORECASE)
DOCTOR_MARKDOWN_LINK_TARGET_RE = re.compile(r"\]\(([^)]+\.(?:csv|json|parquet|xlsx|yaml|yml))\)", re.IGNORECASE)
DOCTOR_PLAIN_DATA_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_./\\:-])"
    r"((?:(?:\.{1,2})[\\/])*(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+\.(?:csv|json|parquet|xlsx|yaml|yml))"
    r"(?![A-Za-z0-9_.-])",
    re.IGNORECASE,
)
DOCTOR_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
DOCTOR_ROOT_OUTPUT_RE = re.compile(r"(?:probe|phase|ref|verify|result|baseline|debug|inspect)", re.IGNORECASE)
DOCTOR_CONTEXT_PROCESS_SIGNALS = ("运行记录", "stdout", "stderr", "probe", "探针", "日志", "尝试", "result")
DOCTOR_CONTEXT_PROCESS_SECTION_RE = re.compile(
    r"^#{2,6}\s*(?:运行记录|过程记录|执行记录|调试记录|日志|探针|run log|process log|execution log|debug log|probe log)(?:\s|$|[:：])",
    re.IGNORECASE,
)
DOCTOR_COMPLETION_TARGET_LINE_RE = re.compile(
    r"(?:(?:写回|同步|更新|标记|设为|设置|mark|update).*(?:任务板|任务计划|Task_Plan|Current_Task|当前任务|当前焦点|焦点)"
    r"|(?:任务板|任务计划|Task_Plan|Current_Task|当前任务|当前焦点|焦点).*(?:写回|同步|更新|标记|设为|设置|mark|update))",
    re.IGNORECASE,
)
WORKSTREAM_PROTOCOL_WITHOUT_MERGING = "Active、Blocked 或 ReadyToMerge"
WORKSTREAM_PROTOCOL_WITH_MERGING = "Active、Blocked、ReadyToMerge 或 Merging"


def doctor_finding(
    code: str,
    severity: str,
    domain: str,
    message: str,
    authority: str,
    locations: Sequence[str],
    evidence: Sequence[dict[str, str]],
    repair_mode: str,
    safe_to_apply: bool,
    suggested_actions: Sequence[str],
) -> dict[str, object]:
    return {
        "code": code,
        "severity": severity,
        "domain": domain,
        "message": message,
        "authority": authority,
        "locations": list(locations),
        "evidence": list(evidence),
        "repair_mode": repair_mode,
        "safe_to_apply": safe_to_apply,
        "suggested_actions": list(suggested_actions),
    }


def doctor_summary(findings: Sequence[dict[str, object]]) -> dict[str, object]:
    return {
        "findings_total": len(findings),
        "by_severity": count_by_key(findings, "severity"),
        "by_domain": count_by_key(findings, "domain"),
        "by_repair_mode": count_by_key(findings, "repair_mode"),
    }


def task_rows_by_id(rows: Sequence[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row.get("ID", ""): row for row in rows if row.get("ID")}


def task_plan_focus_repair_mode(rows: Sequence[dict[str, str]], focus: str) -> tuple[str, bool, list[str]]:
    next_task = recommended_next_task(rows)
    if next_task is None:
        return "safe_fix", True, ["Clear current focus because no unfinished task is available."]
    return "draft_only", False, [
        f"Review whether current focus should move from terminal task {focus} to {next_task.get('ID')}."
    ]


def current_task_completion_target_plan(completion_body: str, current_task_id: str) -> dict[str, object]:
    target_ids: list[str] = []
    non_target_ids: list[str] = []
    for line in completion_body.splitlines():
        line_ids = dependency_task_ids(line)
        if not line_ids:
            continue
        if DOCTOR_COMPLETION_TARGET_LINE_RE.search(line):
            target_ids.extend(line_ids)
        else:
            non_target_ids.extend(line_ids)

    wrong_target_ids = sorted({task_id for task_id in target_ids if task_id != current_task_id})
    wrong_non_target_ids = sorted({task_id for task_id in non_target_ids if task_id != current_task_id})
    safe_to_apply = (
        len(wrong_target_ids) == 1
        and not wrong_non_target_ids
        and set(target_ids) == set(wrong_target_ids)
    )

    updated_lines: list[str] = []
    for line in completion_body.splitlines():
        if safe_to_apply and DOCTOR_COMPLETION_TARGET_LINE_RE.search(line):
            updated_lines.append(TASK_ID_TOKEN_RE.sub(current_task_id, line))
        else:
            updated_lines.append(line)
    updated_body = "\n".join(updated_lines)
    if completion_body.endswith("\n"):
        updated_body += "\n"

    return {
        "wrong_target_ids": wrong_target_ids,
        "wrong_non_target_ids": wrong_non_target_ids,
        "safe_to_apply": safe_to_apply,
        "updated_body": updated_body,
    }


def collect_task_lifecycle_doctor_findings(root: Path) -> list[dict[str, object]]:
    plan_path = task_plan_path(root)
    current_path = current_task_path(root)
    findings: list[dict[str, object]] = []
    if not plan_path.exists():
        return findings
    rows = read_task_rows(plan_path)
    by_id = task_rows_by_id(rows)
    plan_status = extract_heading_value(plan_path, "## 大任务状态") or ""
    current_status = extract_current_task_status(current_path) if current_path.exists() else None

    if current_path.exists() and (
        (plan_status == "Active" and current_status in {"Paused", "Done", "Empty"})
        or (plan_status in {"Done", "Empty"} and current_status == "Active")
    ):
        findings.append(
            doctor_finding(
                "plan_current_task_status_mismatch",
                "warning",
                "task_lifecycle",
                f"Task_Plan status is {plan_status or 'Unknown'} but Current_Task status is {current_status or 'Unknown'}.",
                "active/Task_Plan.md",
                ["active/Task_Plan.md", "active/Current_Task.md"],
                [
                    {"path": "active/Task_Plan.md", "detail": f"大任务状态 is {plan_status or 'Unknown'}"},
                    {"path": "active/Current_Task.md", "detail": f"当前任务状态 is {current_status or 'Unknown'}"},
                ],
                "draft_only",
                False,
                ["Review whether the plan or current task should be cleared, paused, or restarted."],
            )
        )

    focus = extract_heading_value(plan_path, "## 当前焦点")
    if focus in by_id and by_id[focus].get("状态") in TERMINAL_SUBTASK_STATUSES:
        repair_mode, safe_to_apply, suggested_actions = task_plan_focus_repair_mode(rows, focus)
        findings.append(
            doctor_finding(
                "plan_focus_points_to_done_task",
                "warning",
                "task_lifecycle",
                f"Task_Plan current focus points to terminal task {focus}.",
                "active/Task_Plan.md",
                ["active/Task_Plan.md"],
                [
                    {
                        "path": "active/Task_Plan.md",
                        "detail": f"{focus} status is {by_id[focus].get('状态')}",
                    }
                ],
                repair_mode,
                safe_to_apply,
                suggested_actions,
            )
        )

    if current_path.exists() and current_status == "Active":
        current_task_id = extract_heading_value(current_path, "## 子任务 ID")
        if current_task_id in by_id and by_id[current_task_id].get("状态") in TERMINAL_SUBTASK_STATUSES:
            findings.append(
                doctor_finding(
                    "current_task_points_to_done_task",
                    "error",
                    "task_lifecycle",
                    f"Current_Task is Active but points to terminal task {current_task_id}.",
                    "active/Task_Plan.md",
                    ["active/Current_Task.md", "active/Task_Plan.md"],
                    [
                        {
                            "path": "active/Current_Task.md",
                            "detail": f"current task status is Active and 子任务 ID is {current_task_id}",
                        },
                        {
                            "path": "active/Task_Plan.md",
                            "detail": f"{current_task_id} status is {by_id[current_task_id].get('状态')}",
                        },
                    ],
                    "draft_only",
                    False,
                    ["Clear Current_Task or explicitly start the next task."],
                )
            )
        completion_body = safe_section_body(current_path, "## 完成后的回写要求") or ""
        completion_plan = current_task_completion_target_plan(completion_body, current_task_id)
        wrong_completion_ids = completion_plan["wrong_target_ids"]
        extra_ids = completion_plan["wrong_non_target_ids"]
        if meaningful_ref_value(current_task_id) and wrong_completion_ids:
            safe_to_apply = bool(completion_plan["safe_to_apply"])
            repair_mode = "safe_fix" if safe_to_apply else "draft_only"
            suggested_actions = (
                ["Rewrite completion writeback task IDs to the current 子任务 ID."]
                if safe_to_apply
                else ["Review completion writeback targets and preserve non-target task references."]
            )
            detail = f"completion writeback IDs {', '.join(wrong_completion_ids)} differ from {current_task_id}"
            if extra_ids:
                detail += f"; non-target task refs require review: {', '.join(extra_ids)}"
            findings.append(
                doctor_finding(
                    "current_task_wrong_completion_target",
                    "warning",
                    "task_lifecycle",
                    f"Current_Task completion writeback mentions {', '.join(wrong_completion_ids)} but current 子任务 ID is {current_task_id}.",
                    "active/Current_Task.md",
                    ["active/Current_Task.md"],
                    [
                        {
                            "path": "active/Current_Task.md",
                            "detail": detail,
                        }
                    ],
                    repair_mode,
                    safe_to_apply,
                    suggested_actions,
                )
            )
    return findings


def collect_workstream_lifecycle_doctor_findings(root: Path, today: date) -> list[dict[str, object]]:
    if not workstream_initialized(root):
        return []
    findings: list[dict[str, object]] = []
    try:
        entries = parse_workstream_index(root)
    except SystemExit:
        return findings
    terminal_active_details: list[str] = []
    for entry in entries:
        try:
            detail = read_workstream_detail(root, entry.workstream_id)
        except SystemExit:
            continue
        status = detail.metadata.get("status")
        if status in TERMINAL_WORKSTREAM_STATUSES:
            terminal_active_details.append(detail.path.relative_to(root).as_posix())
            keep_until = detail.metadata.get("keep_active_until")
            if isinstance(keep_until, str) and DATE_RE.match(keep_until) and date.fromisoformat(keep_until) < today:
                rel_detail = detail.path.relative_to(root).as_posix()
                findings.append(
                    doctor_finding(
                        "terminal_workstream_keep_active_expired",
                        "warning",
                        "workstream_lifecycle",
                        f"Terminal Workstream {detail.workstream_id} keep_active_until is expired: {keep_until}.",
                        rel_detail,
                        [rel_detail],
                        [{"path": rel_detail, "detail": f"keep_active_until {keep_until} is before today"}],
                        "draft_only",
                        False,
                        ["Review whether this terminal Workstream should be archived or keep-active metadata should be renewed."],
                    )
                )
        if status not in TERMINAL_WORKSTREAM_STATUSES:
            continue
        write_scope = normalize_typed_scope_values(detail.metadata.get("write_scope"))
        assigned_authority = []
        for item in write_scope:
            scope_type, scope_path = split_typed_scope(item)
            if scope_type == "assigned" and scope_path and is_authority_path(scope_path):
                assigned_authority.append(item)
        if assigned_authority:
            rel_detail = detail.path.relative_to(root).as_posix()
            findings.append(
                doctor_finding(
                    "terminal_workstream_assigned_authority",
                    "error",
                    "workstream_lifecycle",
                    f"Terminal Workstream {detail.workstream_id} still assigns authority write scope.",
                    rel_detail,
                    [rel_detail],
                    [
                        {
                            "path": rel_detail,
                            "detail": f"remove terminal assigned authority scope: {item}",
                        }
                        for item in assigned_authority
                    ],
                    "safe_fix",
                    True,
                    ["Remove assigned authority scope from terminal Workstream write_scope."],
                )
            )
    if len(terminal_active_details) >= DOCTOR_TERMINAL_WORKSTREAM_EXCESS_THRESHOLD:
        findings.append(
            doctor_finding(
                "active_terminal_workstreams_excessive",
                "warning",
                "attention_hygiene",
                f"Active workstream directory contains {len(terminal_active_details)} terminal Workstream details.",
                "active/workstreams",
                terminal_active_details,
                [{"path": path, "detail": "terminal Workstream remains in active/workstreams"} for path in terminal_active_details],
                "draft_only",
                False,
                ["Review archive candidates and move no-longer-needed terminal Workstreams to archive."],
            )
        )
    return findings


def normalize_doctor_data_ref(value: str) -> str | None:
    ref = unquote(strip_code_ticks(value.strip())).replace("\\", "/")
    if not ref or ref.startswith(("http://", "https://", "file://", "#")):
        return None
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", ref) or ref.startswith(("/", "//")):
        return None
    if ref.startswith("./"):
        ref = ref[2:]
    ref = ref.strip()
    suffix = Path(ref).suffix.lower().lstrip(".")
    if suffix not in DOCTOR_DATA_REF_EXTENSIONS:
        return None
    return normalize_scope_path(ref)


def doctor_data_ref_candidates(text: str) -> list[str]:
    refs: list[str] = []
    for pattern in (DOCTOR_BACKTICK_PATH_RE, DOCTOR_MARKDOWN_LINK_TARGET_RE, DOCTOR_PLAIN_DATA_PATH_RE):
        for match in pattern.finditer(text):
            normalized = normalize_doctor_data_ref(match.group(1))
            if normalized:
                refs.append(normalized)
    return sorted(dict.fromkeys(refs))


def doctor_data_ref_groups(text: str) -> list[list[str]]:
    groups: list[list[str]] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        refs = doctor_data_ref_candidates("\n".join(paragraph_lines))
        if len(refs) >= 2:
            groups.append(refs)
        paragraph_lines.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            flush_paragraph()
            continue
        if DOCTOR_LIST_ITEM_RE.match(line):
            flush_paragraph()
            refs = doctor_data_ref_candidates(line)
            if len(refs) >= 2:
                groups.append(refs)
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            refs = doctor_data_ref_candidates(line)
            if len(refs) >= 2:
                groups.append(refs)
            continue
        paragraph_lines.append(line)
    flush_paragraph()
    return groups


def resolve_doctor_data_ref(root: Path, ref: str, source_path: Path | None = None) -> Path | None:
    project_root = infer_project_root(root).resolve()
    candidates = []
    if source_path is not None:
        candidates.append((source_path.parent / ref).resolve())
    candidates.extend([
        (project_root / ref).resolve(),
        (root / ref).resolve(),
    ])
    candidates = [candidate for candidate in candidates if is_relative_to(candidate, project_root)]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def collect_data_source_doctor_findings(root: Path) -> list[dict[str, object]]:
    scan_paths = [
        root / "active" / "Context.md",
        root / "reference" / "Sources_Index.md",
        root / "reference" / "Decisions_Index.md",
    ]
    groups: list[tuple[list[str], str, Path]] = []
    for scan_path in scan_paths:
        if not scan_path.exists():
            continue
        source = scan_path.relative_to(root).as_posix()
        for refs in doctor_data_ref_groups(read_text(scan_path)):
            groups.append((refs, source, scan_path))

    findings: list[dict[str, object]] = []
    seen_codes: set[tuple[str, str, str, str]] = set()
    for refs, source, source_path in groups:
        items_by_name: dict[str, list[tuple[str, Path, str]]] = {}
        for ref in refs:
            resolved = resolve_doctor_data_ref(root, ref, source_path)
            if resolved is None:
                continue
            items_by_name.setdefault(Path(ref).name, []).append((ref, resolved, source))
        for items in items_by_name.values():
            unique_items = []
            seen_refs: set[str] = set()
            for item in items:
                if item[0] in seen_refs:
                    continue
                seen_refs.add(item[0])
                unique_items.append(item)
            if len(unique_items) < 2:
                continue
            for left_index, left in enumerate(unique_items):
                for right in unique_items[left_index + 1 :]:
                    left_ref, left_path, left_source = left
                    right_ref, right_path, right_source = right
                    if left_ref == right_ref:
                        continue
                    missing = [ref for ref, path, _source in (left, right) if not path.exists()]
                    if missing:
                        key = ("declared_duplicate_missing", source, left_ref, right_ref)
                        if key in seen_codes:
                            continue
                        seen_codes.add(key)
                        findings.append(
                            doctor_finding(
                                "declared_duplicate_missing",
                                "warning",
                                "data_source",
                                f"Declared duplicate data refs include missing file(s): {', '.join(missing)}.",
                                left_source,
                                sorted({left_source, right_source}),
                                [
                                    {
                                        "path": left_source,
                                        "detail": f"{left_ref}: {'exists' if left_path.exists() else 'missing'}",
                                    },
                                    {
                                        "path": right_source,
                                        "detail": f"{right_ref}: {'exists' if right_path.exists() else 'missing'}",
                                    },
                                ],
                                "evidence_fix",
                                False,
                                ["Review the data source statement and update the authority file or create a writeback draft."],
                            )
                        )
                        continue
                    left_hash = file_sha256(left_path)
                    right_hash = file_sha256(right_path)
                    if left_hash == right_hash:
                        key = ("duplicate_data_hash_confirmed", source, left_ref, right_ref)
                        if key in seen_codes:
                            continue
                        seen_codes.add(key)
                        findings.append(
                            doctor_finding(
                                "duplicate_data_hash_confirmed",
                                "info",
                                "data_source",
                                f"Declared duplicate data refs have matching SHA256: {left_ref} and {right_ref}.",
                                left_source,
                                sorted({left_source, right_source}),
                                [
                                    {"path": left_source, "detail": f"{left_ref}: sha256 {left_hash}"},
                                    {"path": right_source, "detail": f"{right_ref}: sha256 {right_hash}"},
                                ],
                                "evidence_fix",
                                False,
                                ["Record the verified hash evidence in the appropriate source or writeback draft."],
                            )
                        )
    return findings


def planned_workstream_index_sync(root: Path) -> tuple[Path, str, str] | None:
    if not workstream_initialized(root):
        return None
    index_path = workstream_index_path(root)
    try:
        current_text = read_text(index_path)
        entries = parse_workstream_index(root)
        planned_entries = synced_workstream_entries(root, entries)
        planned_text = render_workstream_index_text(root, planned_entries)
    except SystemExit:
        return None
    return index_path, current_text, planned_text


def planned_archive_index_sync(root: Path) -> tuple[Path, str, str, list[dict[str, str]]] | None:
    index_path = archive_index_path(root)
    if not index_path.exists():
        return None
    original = read_text(index_path)
    if ARCHIVE_INDEX_MARKER_START not in original or ARCHIVE_INDEX_MARKER_END not in original:
        return None
    try:
        rows, skipped, _warnings = collect_archive_sync_rows(root)
        skipped.extend(skipped_missing_generated_archive_details(root, original))
        generated_table = render_archive_index_table(rows)
        updated, _changed = replace_generated_marker_block(
            original,
            ARCHIVE_INDEX_MARKER_START,
            ARCHIVE_INDEX_MARKER_END,
            generated_table,
        )
    except SystemExit:
        return None
    return index_path, original, updated, rows


def collect_generated_index_doctor_findings(root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    workstream_plan = planned_workstream_index_sync(root)
    if workstream_plan is not None:
        index_path, current_text, planned_text = workstream_plan
        if planned_text != current_text:
            rel_index = index_path.relative_to(root).as_posix()
            findings.append(
                doctor_finding(
                    "workstream_index_detail_status_mismatch",
                    "warning",
                    "generated_index",
                    "active/Workstreams.md is out of sync with Workstream detail front matter.",
                    rel_index,
                    [rel_index],
                    [{"path": rel_index, "detail": "generated Workstream index text differs from detail-derived text"}],
                    "safe_fix",
                    True,
                    ["Run `acf doctor --fix safe` or `acf workstream sync` to refresh the Workstream index."],
                )
            )

    archive_plan = planned_archive_index_sync(root)
    if archive_plan is not None:
        index_path, original, updated, rows = archive_plan
        if updated != original:
            rel_index = index_path.relative_to(root).as_posix()
            workstream_rows = [row for row in rows if row.get("type") == "workstream" and row.get("id")]
            non_workstream_rows = [row for row in rows if row.get("type") != "workstream"]
            if workstream_rows:
                findings.append(
                    doctor_finding(
                        "archive_index_missing_workstream",
                        "warning",
                        "generated_index",
                        "archive/Archive_Index.md generated block is out of sync with archived Workstream files.",
                        rel_index,
                        [rel_index],
                        [
                            {
                                "path": row.get("archive_path", rel_index),
                                "detail": f"archive index should include {row.get('id')}",
                            }
                            for row in workstream_rows
                        ],
                        "safe_fix",
                        True,
                        ["Run `acf doctor --fix safe` or `acf archive sync` to refresh the Archive index generated block."],
                    )
                )
            if non_workstream_rows or not workstream_rows:
                findings.append(
                    doctor_finding(
                        "archive_index_generated_block_out_of_sync",
                        "warning",
                        "generated_index",
                        "archive/Archive_Index.md generated block is out of sync with archived Task/Plan files.",
                        rel_index,
                        [rel_index],
                        [
                            {
                                "path": row.get("archive_path", rel_index),
                                "detail": f"archive index should include {row.get('type')} {row.get('id')}",
                            }
                            for row in non_workstream_rows
                        ]
                        or [{"path": rel_index, "detail": "archive generated block differs from archive files"}],
                        "safe_fix",
                        True,
                        ["Run `acf doctor --fix safe` or `acf archive sync` to refresh the Archive index generated block."],
                    )
                )
    return findings


def collect_decision_index_doctor_findings(root: Path) -> list[dict[str, object]]:
    decisions_path = root / "reference" / "Decisions_Index.md"
    if not decisions_path.exists():
        return []
    findings: list[dict[str, object]] = []
    rel_path = decisions_path.relative_to(root).as_posix()
    for cells in parse_markdown_table_rows(read_text(decisions_path)):
        if len(cells) < 5 or cells[0] in {"ID", "暂无"}:
            continue
        decision_id, title, status, summary, detail = cells[:5]
        if is_placeholder(decision_id) or is_placeholder(summary):
            continue
        normalized_summary = summary.strip()
        if normalized_summary.endswith((":", "：")) or len(normalized_summary) < 8:
            findings.append(
                doctor_finding(
                    "decisions_index_summary_truncated",
                    "warning",
                    "generated_index",
                    f"Decisions_Index summary for {decision_id} appears truncated.",
                    rel_path,
                    [rel_path],
                    [
                        {
                            "path": rel_path,
                            "detail": f"{decision_id} {title} ({status}) summary is `{normalized_summary}`; detail {detail}",
                        }
                    ],
                    "draft_only",
                    False,
                    ["Open the ADR detail and rewrite the summary after review."],
                )
            )
    return findings


def collect_rule_drift_doctor_findings(root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    candidates = [root / "AGENTS.md", workstream_index_path(root)]
    for path in candidates:
        if not path.exists():
            continue
        text = read_text(path)
        if WORKSTREAM_PROTOCOL_WITHOUT_MERGING in text and WORKSTREAM_PROTOCOL_WITH_MERGING not in text:
            rel_path = path.relative_to(root).as_posix()
            findings.append(
                doctor_finding(
                    "workstream_index_protocol_missing_merging",
                    "warning",
                    "rule_drift",
                    f"{rel_path} Workstream protocol text omits the Merging status from Active-class workstreams.",
                    rel_path,
                    [rel_path],
                    [{"path": rel_path, "detail": "replace protocol literal to include Merging"}],
                    "safe_fix",
                    True,
                    ["Run `acf doctor --fix safe` to update the Workstream protocol literal."],
                )
            )
    return findings


def collect_source_index_doctor_findings(root: Path) -> list[dict[str, object]]:
    sources_path = root / "reference" / "Sources_Index.md"
    if not sources_path.exists():
        return []
    findings: list[dict[str, object]] = []
    rel_source = sources_path.relative_to(root).as_posix()
    rows = parse_markdown_table_rows(read_text(sources_path))
    for cells in rows:
        if len(cells) < 7 or cells[0] in {"资料", "暂无"}:
            continue
        title, _source_type, location, status, _credibility, _relation, _next_action = cells[:7]
        location_ref = strip_code_ticks(location)
        if is_placeholder(title) or is_placeholder(location_ref) or not meaningful_ref_value(location_ref):
            continue
        if is_uri_ref(location_ref):
            continue
        if should_check_ref(location_ref) and resolve_ref(root, sources_path, location_ref) is None:
            findings.append(
                doctor_finding(
                    "source_index_missing_file",
                    "warning",
                    "data_source",
                    f"Sources_Index local source file does not exist: {location_ref}.",
                    rel_source,
                    [rel_source],
                    [
                        {
                            "path": rel_source,
                            "detail": f"{title} status {status or 'Unknown'} points to missing local path {location_ref}",
                        }
                    ],
                    "evidence_fix",
                    False,
                    ["Review the source row and update the path, create the file, or write a semantic draft."],
                )
            )
    return findings


def collect_data_lineage_doctor_findings(root: Path, data_findings: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    lineage_trigger_codes = {"duplicate_data_hash_confirmed", "declared_duplicate_missing"}
    if not any(item.get("code") in lineage_trigger_codes for item in data_findings):
        return []
    lineage_candidates = [
        root / "reference" / "Project_Relationships.md",
        root / "reference" / "Data_Lineage.md",
    ]
    if any(path.exists() for path in lineage_candidates):
        return []
    return [
        doctor_finding(
            "data_lineage_missing",
            "warning",
            "data_source",
            "Data source findings exist but no reference/Project_Relationships.md or reference/Data_Lineage.md file was found.",
            "reference",
            ["reference"],
            [
                {
                    "path": "reference",
                    "detail": "add a lightweight project relationship or data lineage note if these data files depend on upstream projects",
                }
            ],
            "draft_only",
            False,
            ["Create a semantic draft describing whether data is frozen locally or depends on an upstream project."],
        )
    ]


def doctor_context_process_evidence(lines: Sequence[str]) -> list[str]:
    signal_lines: list[str] = []
    process_heading: str | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if process_heading is None and DOCTOR_CONTEXT_PROCESS_SECTION_RE.search(stripped):
            process_heading = stripped
        lower = stripped.lower()
        if any(signal.lower() in lower for signal in DOCTOR_CONTEXT_PROCESS_SIGNALS):
            signal_lines.append(stripped)

    if process_heading is not None:
        return [process_heading, *signal_lines[:4]]
    if len(signal_lines) >= DOCTOR_CONTEXT_PROCESS_SIGNAL_LINE_THRESHOLD:
        return signal_lines[:5]
    return []


def collect_attention_hygiene_doctor_findings(root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    context_path = root / "active" / "Context.md"
    if context_path.exists():
        text = read_text(context_path)
        lines = text.splitlines()
        process_evidence = doctor_context_process_evidence(lines)
        if len(lines) > DOCTOR_CONTEXT_LINE_THRESHOLD and process_evidence:
            findings.append(
                doctor_finding(
                    "context_too_thick",
                    "warning",
                    "attention_hygiene",
                    f"active/Context.md has {len(lines)} lines and contains process-log signals.",
                    "active/Context.md",
                    ["active/Context.md"],
                    [
                        {
                            "path": "active/Context.md",
                            "detail": f"{len(lines)} lines; process signals: {' | '.join(process_evidence)}",
                        }
                    ],
                    "draft_only",
                    False,
                    ["Move process history to worklog/archive and keep active/Context.md focused on current facts."],
                )
            )

    project_root = infer_project_root(root)
    if project_root.exists():
        probe_outputs = [
            path
            for path in sorted(project_root.glob("*.json"))
            if DOCTOR_ROOT_OUTPUT_RE.search(path.name)
        ]
        if len(probe_outputs) >= DOCTOR_ROOT_OUTPUT_THRESHOLD:
            rel_outputs = [path.relative_to(project_root).as_posix() for path in probe_outputs]
            findings.append(
                doctor_finding(
                    "root_probe_outputs_detected",
                    "warning",
                    "attention_hygiene",
                    f"Project root contains {len(probe_outputs)} probe/result JSON outputs.",
                    ".",
                    rel_outputs,
                    [{"path": rel, "detail": "root-level generated output candidate"} for rel in rel_outputs],
                    "draft_only",
                    False,
                    ["Move generated probe/result outputs under output/ or document only an index in reference."],
                )
            )
    return findings


def collect_doctor_findings(root: Path, today: date | None = None) -> list[dict[str, object]]:
    _today = today or date.today()
    findings: list[dict[str, object]] = []
    findings.extend(collect_task_lifecycle_doctor_findings(root))
    findings.extend(collect_workstream_lifecycle_doctor_findings(root, _today))
    findings.extend(collect_generated_index_doctor_findings(root))
    findings.extend(collect_decision_index_doctor_findings(root))
    findings.extend(collect_rule_drift_doctor_findings(root))
    data_findings = collect_data_source_doctor_findings(root)
    source_findings = collect_source_index_doctor_findings(root)
    findings.extend(data_findings)
    findings.extend(source_findings)
    findings.extend(collect_data_lineage_doctor_findings(root, data_findings))
    findings.extend(collect_attention_hygiene_doctor_findings(root))
    return findings


def apply_doctor_plan_focus_safe_fix(root: Path, findings: Sequence[dict[str, object]], dry_run: bool) -> list[Path]:
    if not any(item.get("code") == "plan_focus_points_to_done_task" and item.get("safe_to_apply") for item in findings):
        return []
    plan_path = task_plan_path(root)
    rows = read_task_rows(plan_path)
    focus = extract_heading_value(plan_path, "## 当前焦点")
    if not focus:
        return []
    next_task = recommended_next_task(rows)
    if next_task is not None:
        return []
    updated = replace_section_text(read_text(plan_path), "## 当前焦点", "无。")
    if updated == read_text(plan_path):
        return []
    if not dry_run:
        plan_path.write_text(updated, encoding="utf-8")
    return [plan_path]


def apply_doctor_current_task_completion_target_safe_fix(root: Path, findings: Sequence[dict[str, object]], dry_run: bool) -> list[Path]:
    if not any(item.get("code") == "current_task_wrong_completion_target" and item.get("safe_to_apply") for item in findings):
        return []
    current_path = current_task_path(root)
    if not current_path.exists():
        return []
    current_id = extract_heading_value(current_path, "## 子任务 ID")
    if not meaningful_ref_value(current_id):
        return []
    original = read_text(current_path)
    completion_body = safe_section_body(current_path, "## 完成后的回写要求") or ""
    if not completion_body:
        return []
    completion_plan = current_task_completion_target_plan(completion_body, current_id)
    if not completion_plan["safe_to_apply"]:
        return []
    updated_body = str(completion_plan["updated_body"])
    if updated_body == completion_body:
        return []
    updated = replace_section_text(original, "## 完成后的回写要求", updated_body)
    if updated == original:
        return []
    if not dry_run:
        current_path.write_text(updated, encoding="utf-8")
    return [current_path]


def remove_terminal_workstream_assigned_authority(root: Path, dry_run: bool) -> list[Path]:
    if not workstream_initialized(root):
        return []
    changed: list[Path] = []
    try:
        entries = parse_workstream_index(root)
    except SystemExit:
        return changed
    for entry in entries:
        try:
            detail = read_workstream_detail(root, entry.workstream_id)
        except SystemExit:
            continue
        if detail.metadata.get("status") not in {"Done", "Cancelled"}:
            continue
        write_scope = detail.metadata.get("write_scope")
        if not isinstance(write_scope, list):
            continue
        filtered: list[str] = []
        removed = False
        for item in normalize_typed_scope_values(write_scope):
            scope_type, scope_path = split_typed_scope(item)
            if scope_type == "assigned" and scope_path and is_authority_path(scope_path):
                removed = True
                continue
            filtered.append(item)
        if not removed:
            continue
        metadata = dict(detail.metadata)
        metadata["write_scope"] = filtered
        if not dry_run:
            detail.path.write_text(format_front_matter(metadata, detail.body, WORKSTREAM_METADATA_FIELDS), encoding="utf-8")
        changed.append(detail.path)
    return changed


def apply_doctor_workstream_index_safe_fix(root: Path, findings: Sequence[dict[str, object]], dry_run: bool) -> list[Path]:
    if not any(item.get("code") == "workstream_index_detail_status_mismatch" and item.get("safe_to_apply") for item in findings):
        return []
    plan = planned_workstream_index_sync(root)
    if plan is None:
        return []
    index_path, current_text, planned_text = plan
    if planned_text == current_text:
        return []
    if not dry_run:
        index_path.write_text(planned_text, encoding="utf-8")
    return [index_path]


def apply_doctor_archive_index_safe_fix(root: Path, findings: Sequence[dict[str, object]], dry_run: bool) -> list[Path]:
    archive_repair_codes = {"archive_index_missing_workstream", "archive_index_generated_block_out_of_sync"}
    if not any(item.get("code") in archive_repair_codes and item.get("safe_to_apply") for item in findings):
        return []
    plan = planned_archive_index_sync(root)
    if plan is None:
        return []
    index_path, original, updated, _rows = plan
    if updated == original:
        return []
    if not dry_run:
        index_path.write_text(updated, encoding="utf-8")
    return [index_path]


def apply_doctor_workstream_protocol_safe_fix(root: Path, findings: Sequence[dict[str, object]], dry_run: bool) -> list[Path]:
    if not any(item.get("code") == "workstream_index_protocol_missing_merging" and item.get("safe_to_apply") for item in findings):
        return []
    changed: list[Path] = []
    for path in (root / "AGENTS.md", workstream_index_path(root)):
        if not path.exists():
            continue
        original = read_text(path)
        updated = original.replace(WORKSTREAM_PROTOCOL_WITHOUT_MERGING, WORKSTREAM_PROTOCOL_WITH_MERGING)
        if updated == original:
            continue
        if not dry_run:
            path.write_text(updated, encoding="utf-8")
        changed.append(path)
    return changed


def apply_doctor_safe_fixes(root: Path, findings: Sequence[dict[str, object]], dry_run: bool) -> tuple[list[Path], int]:
    if not findings:
        return [], 0
    changed: list[Path] = []
    repair_count = 0

    def append_repair(paths: Sequence[Path]) -> None:
        nonlocal repair_count
        if not paths:
            return
        changed.extend(paths)
        repair_count += len(paths)

    append_repair(apply_doctor_plan_focus_safe_fix(root, findings, dry_run))
    append_repair(apply_doctor_current_task_completion_target_safe_fix(root, findings, dry_run))
    append_repair(apply_doctor_workstream_index_safe_fix(root, findings, dry_run))
    append_repair(apply_doctor_archive_index_safe_fix(root, findings, dry_run))
    append_repair(apply_doctor_workstream_protocol_safe_fix(root, findings, dry_run))
    if any(item.get("code") == "terminal_workstream_assigned_authority" for item in findings):
        append_repair(remove_terminal_workstream_assigned_authority(root, dry_run))
    return sorted(dict.fromkeys(changed)), repair_count


def doctor_evidence_repair_count(findings: Sequence[dict[str, object]], fix: str) -> int:
    if fix != "evidence":
        return 0
    return sum(1 for finding in findings if finding.get("repair_mode") == "evidence_fix")


def doctor_next_actions(
    findings: Sequence[dict[str, object]],
    fix: str,
    check_result: CheckResult | None = None,
) -> list[str]:
    if check_result is not None and not check_result.ok:
        actions = [
            "Fix the reported doctor check errors before relying on the doctor result.",
            "Rerun `acf check --json` after correcting the context structure.",
        ]
        if findings:
            actions.append("Review doctor findings after the structural check is clean.")
        return actions
    if not findings:
        return ["No doctor findings found."]
    actions = ["Review doctor findings and apply safe fixes or create writeback drafts for semantic items."]
    if fix == "none" and any(item.get("safe_to_apply") for item in findings):
        actions.append("Rerun with `acf doctor --fix safe --json` to apply safe mechanical fixes.")
    if fix == "none" and any(item.get("repair_mode") == "evidence_fix" for item in findings):
        actions.append("Rerun with `acf doctor --fix evidence --dry-run --json` to plan evidence repairs without rewriting semantic authority files.")
    return actions


def doctor_report_path(root: Path, report_date: date) -> Path:
    return root / "worklog" / "doctor-reports" / f"{report_date.isoformat()}.md"


def doctor_semantic_draft_path(root: Path, draft_date: date) -> Path:
    return root / "worklog" / "writeback-drafts" / f"{draft_date.isoformat()}-doctor.md"


def semantic_doctor_findings(findings: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    return [
        finding
        for finding in findings
        if finding.get("repair_mode") in {"draft_only", "evidence_fix"}
    ]


def preflight_doctor_output_files(args: argparse.Namespace, root: Path, today: date) -> None:
    if dry_run_enabled(args):
        return
    if getattr(args, "force", False):
        return
    if getattr(args, "report", False):
        report_path = doctor_report_path(root, today)
        if report_path.exists():
            raise SystemExit(f"doctor_report_exists: {relative_display_path(report_path, root)}")
    if getattr(args, "draft_semantic", False):
        draft_path = doctor_semantic_draft_path(root, today)
        if draft_path.exists():
            raise SystemExit(f"doctor_draft_exists: {relative_display_path(draft_path, root)}")


def render_doctor_finding_markdown(finding: dict[str, object], index: int) -> list[str]:
    lines = [
        f"### {index}. {markdown_value(finding.get('code'))}",
        "",
        f"- severity: {markdown_value(finding.get('severity'))}",
        f"- domain: {markdown_value(finding.get('domain'))}",
        f"- repair_mode: {markdown_value(finding.get('repair_mode'))}",
        f"- safe_to_apply: {markdown_value(finding.get('safe_to_apply'))}",
        f"- authority: {markdown_value(finding.get('authority'))}",
        f"- message: {markdown_value(finding.get('message'))}",
        "",
    ]
    evidence = finding.get("evidence")
    if isinstance(evidence, list) and evidence:
        lines.extend(["Evidence:", ""])
        for item in evidence:
            if isinstance(item, dict):
                lines.append(f"- {markdown_value(item.get('path'))}: {markdown_value(item.get('detail'))}")
        lines.append("")
    actions = finding.get("suggested_actions")
    if isinstance(actions, list) and actions:
        lines.extend(["Suggested actions:", ""])
        for action in actions:
            lines.append(f"- {markdown_value(action)}")
        lines.append("")
    return lines


def render_doctor_report(root: Path, report_date: date, findings: Sequence[dict[str, object]], summary: dict[str, object]) -> str:
    lines = [
        f"# ACF Doctor Report: {report_date.isoformat()}",
        "",
        "本报告由 `acf doctor` 生成，不是默认读取入口，也不是事实裁决结果。",
        "",
        "## Summary",
        "",
        f"- context: {root}",
        f"- findings_total: {summary.get('findings_total', len(findings))}",
        f"- by_severity: {json.dumps(summary.get('by_severity', {}), ensure_ascii=False, sort_keys=True)}",
        f"- by_domain: {json.dumps(summary.get('by_domain', {}), ensure_ascii=False, sort_keys=True)}",
        f"- by_repair_mode: {json.dumps(summary.get('by_repair_mode', {}), ensure_ascii=False, sort_keys=True)}",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.extend(["No doctor findings found.", ""])
    for index, finding in enumerate(findings, start=1):
        lines.extend(render_doctor_finding_markdown(finding, index))
    return "\n".join(lines).rstrip() + "\n"


def render_doctor_semantic_draft(root: Path, draft_date: date, findings: Sequence[dict[str, object]]) -> str:
    lines = [
        "本文件是 doctor 语义回写草案，不是当前事实源。",
        "",
        "请人工审阅后，再决定是否使用 CLI 或手工方式写入权威上下文。",
        "",
        "---",
        "",
        "## 草案名称",
        "",
        f"{draft_date.isoformat()}-doctor",
        "",
        "---",
        "",
        "## 来源",
        "",
        f"- command: acf doctor --draft-semantic",
        f"- context: {root}",
        "",
        "---",
        "",
        "## Doctor Findings",
        "",
    ]
    if not findings:
        lines.extend(["无需要语义回写的 finding。", ""])
    for index, finding in enumerate(findings, start=1):
        lines.extend(render_doctor_finding_markdown(finding, index))
        lines.extend(
            [
                "人工处理：",
                "",
                "- 目标权威位置：",
                "- 拟写入内容：",
                "- 保留 / 修改 / 忽略：",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_doctor_output_files(
    args: argparse.Namespace,
    root: Path,
    today: date,
    findings: Sequence[dict[str, object]],
    summary: dict[str, object],
) -> tuple[list[Path], dict[str, object]]:
    dry_run = dry_run_enabled(args)
    changed: list[Path] = []
    extra: dict[str, object] = {
        "report_path": None,
        "draft_path": None,
        "created_report": False,
        "created_draft": False,
    }
    if getattr(args, "report", False):
        report_path = doctor_report_path(root, today)
        report_text = render_doctor_report(root, today, findings, summary)
        extra["report_path"] = relative_display_path(report_path, root)
        if dry_run:
            extra["planned_report"] = report_text
            changed.append(report_path)
        else:
            if report_path.exists() and not getattr(args, "force", False):
                raise SystemExit(f"doctor_report_exists: {relative_display_path(report_path, root)}")
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(report_text, encoding="utf-8")
            changed.append(report_path)
            extra["created_report"] = True

    semantic_findings = semantic_doctor_findings(findings)
    if getattr(args, "draft_semantic", False):
        draft_path = doctor_semantic_draft_path(root, today)
        draft_text = render_doctor_semantic_draft(root, today, semantic_findings)
        extra["draft_path"] = relative_display_path(draft_path, root)
        if dry_run:
            extra["planned_draft"] = draft_text
            changed.append(draft_path)
        else:
            if draft_path.exists() and not getattr(args, "force", False):
                raise SystemExit(f"doctor_draft_exists: {relative_display_path(draft_path, root)}")
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text(draft_text, encoding="utf-8")
            changed.append(draft_path)
            extra["created_draft"] = True
    return changed, extra


def doctor_single_context_payload(args: argparse.Namespace, root: Path) -> dict[str, object]:
    strict = bool(getattr(args, "strict", False))
    today = date.fromisoformat(args.today) if getattr(args, "today", None) else date.today()
    findings = collect_doctor_findings(root, today)
    fix = getattr(args, "fix", "none")
    preflight_doctor_output_files(args, root, today)
    if fix in {"safe", "evidence"}:
        repair_changed_files, repair_count = apply_doctor_safe_fixes(root, findings, dry_run_enabled(args))
    else:
        repair_changed_files, repair_count = [], 0
    summary = doctor_summary(findings)
    output_changed_files, output_payload = write_doctor_output_files(args, root, today, findings, summary)
    changed_files = sorted(dict.fromkeys([*repair_changed_files, *output_changed_files]))
    check_result = maybe_check_after(args, root) if changed_files else None
    if check_result is None:
        check_result = check_context(root, infer_context_profile(root), strict)
    evidence_repair_count = doctor_evidence_repair_count(findings, fix)
    summary["applied_repairs"] = repair_count if not dry_run_enabled(args) else 0
    summary["planned_repairs"] = repair_count + evidence_repair_count
    summary["planned_evidence_repairs"] = evidence_repair_count
    summary["changed_repair_files"] = len(repair_changed_files)
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "doctor",
        "ok": check_result.ok,
        "context": str(root),
        "profile": infer_context_profile(root),
        "strict": strict,
        "fix": fix,
        "dry_run": dry_run_enabled(args),
        "changed_files": path_values(changed_files),
        "summary": summary,
        "findings": findings,
        "check": check_payload(check_result),
        "error_code": check_error_code(check_result),
        "next_actions": doctor_next_actions(findings, fix, check_result),
    }
    if not check_result.ok:
        payload["message"] = "doctor check failed; inspect check.errors before applying doctor findings"
    payload.update(output_payload)
    return payload


def doctor_failed_project_payload(args: argparse.Namespace, project: Path, message: str) -> dict[str, object]:
    error_code, _exit_code = classify_cli_error(message)
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "doctor",
        "ok": False,
        "context": str(project),
        "profile": None,
        "strict": bool(getattr(args, "strict", False)),
        "fix": getattr(args, "fix", "none"),
        "dry_run": dry_run_enabled(args),
        "changed_files": [],
        "summary": doctor_summary([]),
        "findings": [],
        "check": None,
        "error_code": error_code,
        "message": message,
        "next_actions": error_next_actions(error_code),
    }


def doctor_project_payload(args: argparse.Namespace, project: Path) -> dict[str, object]:
    try:
        root = require_context_root(project)
    except SystemExit as exc:
        message = str(exc.code)
        return doctor_failed_project_payload(args, project, message)
    return doctor_single_context_payload(args, root)


def doctor_projects_next_actions(
    project_payloads: Sequence[dict[str, object]],
    findings: Sequence[dict[str, object]],
    fix: str,
    ok: bool,
) -> list[str]:
    if ok:
        return doctor_next_actions(findings, fix)
    actions = ["Inspect per-project error_code/message and fix invalid context paths or failed checks."]
    if findings:
        actions.extend(doctor_next_actions(findings, fix))
    return sorted(dict.fromkeys(actions))


def doctor_deps() -> doctor_commands.DoctorDependencies:
    return doctor_commands.DoctorDependencies(
        doctor_project_payload=doctor_project_payload,
        doctor_single_context_payload=doctor_single_context_payload,
        doctor_summary=doctor_summary,
        doctor_projects_next_actions=doctor_projects_next_actions,
    )


def doctor_command(args: argparse.Namespace) -> int:
    return doctor_commands.doctor_command(args, deps=doctor_deps())


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


ARCHIVE_FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")


def archive_date_from_file_name(path: Path) -> str | None:
    match = ARCHIVE_FILENAME_DATE_RE.match(path.stem)
    if not match:
        return None
    value = match.group(1)
    return value if DATE_RE.match(value) else None


def archive_title_fallback(path: Path) -> str:
    match = ARCHIVE_FILENAME_DATE_RE.match(path.stem)
    return match.group(2) if match else path.stem


def render_archive_index_table(rows: Sequence[dict[str, str]]) -> str:
    lines = [ARCHIVE_TABLE_HEADER, "|---|---|---|---|---|---|---|"]
    if rows:
        for row in sorted(rows, key=lambda item: (item["date"], item["type"], item["id"])):
            lines.append(
                render_table_row(
                    [
                        row["date"],
                        row["type"],
                        row["id"],
                        row["source_path"],
                        f"`{row['archive_path']}`",
                        row["status"],
                        row["reason"],
                    ]
                )
            )
    else:
        lines.append("| 暂无 |  |  |  |  |  |  |")
    return "\n".join(lines)


def collect_task_plan_archive_rows(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], int]:
    rows: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    fallback_reason_count = 0
    sources = (
        ("Task", root / "archive" / "tasks", "## 任务名称", "active/Current_Task.md"),
        ("Plan", root / "archive" / "plans", "## 大任务名称", "active/Task_Plan.md"),
    )
    for item_type, directory, title_heading, source_path in sources:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            rel = path.relative_to(root).as_posix()
            text = read_text(path)
            marker = marker_fields(text, ARCHIVE_RECORD_MARKER_START, ARCHIVE_RECORD_MARKER_END)
            archive_date = marker.get("archived_at", "") if marker else archive_date_from_file_name(path)
            if not archive_date or not DATE_RE.match(archive_date):
                skipped.append({"path": rel, "reason": "archive date not recoverable"})
                continue
            item_id = marker.get("item_id", "") if marker else ""
            status = marker.get("status", "") if marker else ""
            reason = marker.get("archive_reason", "") if marker else ""
            rows.append(
                {
                    "date": archive_date,
                    "type": marker.get("item_type", item_type) if marker else item_type,
                    "id": item_id or extract_heading_value(path, title_heading) or archive_title_fallback(path),
                    "source_path": marker.get("source_path", source_path) if marker else source_path,
                    "archive_path": marker.get("archive_path", rel) if marker else rel,
                    "status": status or "Archived",
                    "reason": reason or "未记录。",
                }
            )
            if marker is None or not reason:
                fallback_reason_count += 1
    return rows, skipped, fallback_reason_count


def collect_workstream_archive_rows(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    directory = root / WORKSTREAM_ARCHIVE_DIR_REL
    if not directory.exists():
        return rows, skipped
    for path in sorted(directory.glob("*.md")):
        rel = path.relative_to(root).as_posix()
        match = re.match(r"^(WS\d{3})\.md$", path.name)
        if match is None:
            skipped.append({"path": rel, "reason": "workstream archive file name does not use WSNNN.md"})
            continue
        text = read_text(path)
        marker = workstream_archive_marker_fields(text)
        archive_date = marker.get("archived_at", "") if marker else ""
        if not DATE_RE.match(archive_date):
            skipped.append({"id": match.group(1), "path": rel, "reason": "archive date not recoverable"})
            continue
        metadata, _body, _diagnostics = parse_front_matter(text)
        status = metadata.get("status") if isinstance(metadata, dict) else None
        rows.append(
            {
                "date": archive_date,
                "type": "workstream",
                "id": match.group(1),
                "source_path": marker.get("source_path", f"{WORKSTREAM_DIR_REL}/{match.group(1)}.md") if marker else f"{WORKSTREAM_DIR_REL}/{match.group(1)}.md",
                "archive_path": marker.get("archive_path", rel) if marker else rel,
                "status": status if isinstance(status, str) and status.strip() else "Archived",
                "reason": marker.get("archive_reason", "未记录。") if marker else "未记录。",
            }
        )
    return rows, skipped


def collect_archive_sync_rows(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    task_plan_rows, skipped, fallback_reason_count = collect_task_plan_archive_rows(root)
    workstream_rows, workstream_skipped = collect_workstream_archive_rows(root)
    warnings: list[str] = []
    if fallback_reason_count:
        warnings.append(
            "Task/Plan archive reason is not recoverable from archived files; "
            f"{fallback_reason_count} rows used fallback reason."
        )
    return task_plan_rows + workstream_rows, skipped + workstream_skipped, warnings


def skipped_missing_generated_archive_details(root: Path, index_text: str) -> list[dict[str, str]]:
    if ARCHIVE_INDEX_MARKER_START not in index_text or ARCHIVE_INDEX_MARKER_END not in index_text:
        return []
    start = index_text.index(ARCHIVE_INDEX_MARKER_START) + len(ARCHIVE_INDEX_MARKER_START)
    end = index_text.index(ARCHIVE_INDEX_MARKER_END, start)
    marker_body = index_text[start:end]
    skipped: list[dict[str, str]] = []
    index_path = archive_index_path(root)
    for cells in parse_markdown_table_rows(marker_body):
        if len(cells) < 7 or cells[0] in {"日期", "暂无"}:
            continue
        ref = strip_code_ticks(cells[4])
        if should_check_ref(ref) and resolve_ref(root, index_path, ref) is None:
            skipped.append({"id": cells[2], "path": ref, "reason": "detail source is missing"})
    return skipped


def archive_deps() -> archive_commands.ArchiveDependencies:
    return archive_commands.ArchiveDependencies(
        maybe_check_after=maybe_check_after,
        archive_index_path=archive_index_path,
        read_text=read_text,
        render_archive_index=render_archive_index,
        collect_archive_sync_rows=collect_archive_sync_rows,
        skipped_missing_generated_archive_details=skipped_missing_generated_archive_details,
        render_archive_index_table=render_archive_index_table,
        archive_file=archive_file,
        current_task_path=current_task_path,
        task_plan_path=task_plan_path,
        find_archive_table=find_archive_table,
        archive_table_header=ARCHIVE_TABLE_HEADER,
    )


def archive_sync_command(args: argparse.Namespace) -> int:
    return archive_commands.archive_sync_command(args, deps=archive_deps())


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
    archived_text, _rewritten_links = rewrite_local_markdown_links_for_move(root, source, destination, read_text(source))
    archive_rel = destination.relative_to(root).as_posix()
    source_rel = source.relative_to(root).as_posix()
    archived_text = (
        archived_text.rstrip()
        + "\n\n---\n\n"
        + archive_record_marker(
            archive_date,
            kind,
            title,
            source_rel,
            archive_rel,
            "Archived",
            reason.strip() or "归档旧内容。",
        )
    )
    destination.write_text(archived_text, encoding="utf-8")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if not index_path.exists():
        index_path.write_text(render_archive_index(), encoding="utf-8")
    update_archive_index(
        index_path,
        archive_date,
        kind,
        title,
        reason.strip() or "归档旧内容。",
        archive_rel,
    )
    if kind == "Task":
        source.write_text(render_empty_current_task(), encoding="utf-8")
    else:
        source.write_text(render_empty_task_plan(), encoding="utf-8")
    return changed


def archive_current_task_command(args: argparse.Namespace) -> int:
    return archive_commands.archive_current_task_command(args, deps=archive_deps())


def archive_task_plan_command(args: argparse.Namespace) -> int:
    return archive_commands.archive_task_plan_command(args, deps=archive_deps())


def archive_list_command(args: argparse.Namespace) -> int:
    return archive_commands.archive_list_command(args, deps=archive_deps())


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
            "type",
            "status",
            "owner",
            "title",
            "current_stage",
            "merge_owner",
            "coordination",
            "merge_resolution",
            "keep_active_reason",
            "keep_active_until",
        ),
        list_fields=("depends_on", "read_scope", "write_scope", "merge_targets"),
        enum_fields={
            "type": VALID_WORKSTREAM_TYPES,
            "status": VALID_WORKSTREAM_STATUSES,
            "coordination": {"parallel", "serial"},
            "merge_resolution": VALID_MERGE_RESOLUTIONS,
        },
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

Workstream 是可选并行目标线协议。启用后采用强隔离协作约束：详情文件 front matter 是唯一事实源，索引由工具同步，AI 执行前先读取专属 context packet，完成前用 guard 检查实际改动。

默认读取规则：只有存在 Active、Blocked、ReadyToMerge 或 Merging workstream，或当前任务需要整理并行协作时，才读取本文件。没有这些状态时，本文件不进入默认上下文。

---

## Workstream 状态

Inactive

说明：当前没有 Active、Blocked、ReadyToMerge 或 Merging workstream。

---

## Workstreams

{WORKSTREAM_TABLE_HEADER}
|---|---|---|---|---|---|---|---|
| 暂无 | Empty | 无。 | 无。 | 无。 | 无。 | 无。 | 无。 |

---

## 使用规则

1. 本索引只保留低噪音摘要，由 `acf workstream sync` 从详情 front matter 同步。
2. 单个 Workstream 详情文件是该 Workstream 的唯一事实源。
3. Task / Merge / Maintenance 三类 Workstream 权限不同；Task 不直接写 authority 文件。
4. Active 类 Workstream 默认禁止重叠 `owned:` 写入；共享文件必须显式 `shared:` 并设置 merge_owner 或 serial coordination。
5. AI 执行前运行 `acf workstream context WSxxx`，完成前运行 `acf workstream guard WSxxx`。
6. ReadyToMerge 表示任务产物完成；Done 表示合并或处置完成。
7. Done / Cancelled workstream 只在当前计划仍需解释时保留在 active 区域。
8. 当前计划结束后，Done / Cancelled workstream 应归档到 archive/workstreams。
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


def workstream_type(detail: WorkstreamDetail) -> str:
    value = detail.metadata.get("type")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "Task"


def workstream_id_exists(root: Path, workstream_id: str, entries: Sequence[WorkstreamEntry]) -> bool:
    if any(entry.workstream_id == workstream_id for entry in entries):
        return True
    candidates = [
        workstream_details_dir(root) / f"{workstream_id}.md",
        workstream_archive_dir(root) / f"{workstream_id}.md",
    ]
    return any(candidate.exists() for candidate in candidates)


def format_bullets(values: Sequence[str]) -> str:
    items = [str(value).strip() for value in values if str(value).strip()]
    if not items:
        return "- 无。"
    return "\n".join(f"- {item}" for item in items)


def render_workstream_detail(
    workstream_id: str,
    title: str,
    owner: str,
    depends_on: Sequence[str],
    read_scope: Sequence[str],
    write_scope: Sequence[str],
    output: str,
    goal: str = "待补充。",
    workstream_kind: str = "Task",
) -> str:
    metadata: dict[str, str | list[str]] = {
        "id": workstream_id,
        "type": workstream_kind,
        "status": "Open",
        "owner": owner,
        "title": title,
        "depends_on": list(depends_on),
        "read_scope": list(read_scope),
        "write_scope": list(write_scope),
    }
    body = f"""# {workstream_id} - {title}

## 边界说明

本 Workstream 使用强隔离协作协议。AI 执行前应先运行 `acf workstream context {workstream_id}` 获取专属上下文入口；完成或切换状态前应运行 `acf workstream guard {workstream_id}` 检查实际改动是否越界。

- `read_scope` 是允许读取的默认上下文入口。
- `write_scope` 是允许直接修改的范围。
- Task Workstream 不直接修改 authority 文件；需要主线合并时先写 merge request。
- active workstream 默认禁止重叠写入；共享文件必须显式使用 `shared:` 并指定 merge_owner 或 serial coordination。

---

## Context Packet

### Mission

{goal or "待补充。"}

### Allowed Read Scope

{format_bullets(read_scope)}

### Allowed Write Scope

{format_bullets(write_scope)}

### Forbidden Scope

- 未在 write_scope 中声明的文件。
- 其他 active workstream 的 owned 文件。
- Task Workstream 的 authority 文件直接写入。

### Evidence Required

- 状态迁移到 ReadyToMerge 前必须有合并请求或明确无主线合并说明。
- 状态迁移到 Done 前必须有 evidence 和 merge_resolution。

### Merge Contract

- ReadyToMerge 表示任务产物完成。
- Done 表示合并或处置完成。

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


def update_workstream_index_state_text(text: str, entries: Sequence[WorkstreamEntry]) -> str:
    state = "Active" if any(entry.status in ACTIVE_WORKSTREAM_STATUSES for entry in entries) else "Inactive"
    explanation = (
        "说明：存在 Active、Blocked、ReadyToMerge 或 Merging workstream。"
        if state == "Active"
        else "说明：当前没有 Active、Blocked、ReadyToMerge 或 Merging workstream。"
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



def workstream_deps() -> workstream_commands.WorkstreamDependencies:
    return workstream_commands.WorkstreamDependencies(symbols=globals())


_WORKSTREAM_COMPAT_EXPORTS = {
    name
    for name, value in vars(workstream_commands).items()
    if inspect.isfunction(value)
    and value.__module__ == workstream_commands.__name__
    and not name.startswith("_")
    and not name.endswith("_command")
}


def workstream_init_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_init_command(args, deps=workstream_deps())


def workstream_status_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_status_command(args, deps=workstream_deps())


def workstream_list_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_list_command(args, deps=workstream_deps())


def workstream_archive_candidates_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_archive_candidates_command(args, deps=workstream_deps())


def workstream_archive_draft_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_archive_draft_command(args, deps=workstream_deps())


def workstream_archive_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_archive_command(args, deps=workstream_deps())


def workstream_sync_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_sync_command(args, deps=workstream_deps())


def workstream_show_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_show_command(args, deps=workstream_deps())


def workstream_add_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_add_command(args, deps=workstream_deps())


def workstream_set_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_set_command(args, deps=workstream_deps())


def workstream_block_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_block_command(args, deps=workstream_deps())


def workstream_cancel_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_cancel_command(args, deps=workstream_deps())


def workstream_merge_request_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_merge_request_command(args, deps=workstream_deps())


def workstream_ready_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_ready_command(args, deps=workstream_deps())


def workstream_done_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_done_command(args, deps=workstream_deps())


def workstream_note_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_note_command(args, deps=workstream_deps())


def workstream_scope_add_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_scope_add_command(args, deps=workstream_deps())


def workstream_context_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_context_command(args, deps=workstream_deps())


def workstream_guard_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_guard_command(args, deps=workstream_deps())


def workstream_merge_start_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_merge_start_command(args, deps=workstream_deps())


def workstream_dashboard_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_dashboard_command(args, deps=workstream_deps())


def workstream_claim_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_claim_command(args, deps=workstream_deps())


def workstream_stage_add_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_stage_add_command(args, deps=workstream_deps())


def workstream_stage_list_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_stage_list_command(args, deps=workstream_deps())


def workstream_focus_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_focus_command(args, deps=workstream_deps())


def workstream_stage_done_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_stage_done_command(args, deps=workstream_deps())


def bind_workstream_compat_dependencies() -> None:
    workstream_commands._bind(workstream_deps())


def count_by_key(items: Sequence[dict[str, object]], key: str) -> dict[str, int]:
    bind_workstream_compat_dependencies()
    return workstream_commands.count_by_key(items, key)


def merge_request_has_required_fields(body: str) -> bool:
    bind_workstream_compat_dependencies()
    return workstream_commands.merge_request_has_required_fields(body)


def scope_paths_conflict(left: str, right: str) -> bool:
    bind_workstream_compat_dependencies()
    return workstream_commands.scope_paths_conflict(left, right)


def __getattr__(name: str) -> object:
    if name in _WORKSTREAM_COMPAT_EXPORTS:
        bind_workstream_compat_dependencies()
        return getattr(workstream_commands, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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


def knowledge_deps() -> knowledge_commands.KnowledgeDependencies:
    return knowledge_commands.KnowledgeDependencies(
        maybe_check_after=maybe_check_after,
        resolve_context_existing_path=resolve_context_existing_path,
        slugify_file_stem=slugify_file_stem,
        render_knowledge_draft=render_knowledge_draft,
        knowledge_index_path=knowledge_index_path,
        read_text=read_text,
        render_knowledge_index=render_knowledge_index,
        collect_knowledge_sync_rows=collect_knowledge_sync_rows,
        skipped_missing_generated_knowledge_details=skipped_missing_generated_knowledge_details,
        render_knowledge_index_table=render_knowledge_index_table,
        resolve_knowledge_draft=resolve_knowledge_draft,
        knowledge_title_from_text=knowledge_title_from_text,
        extract_heading_value=extract_heading_value,
        safe_section_body_from_text=safe_section_body_from_text,
        similar_knowledge_entries=similar_knowledge_entries,
        collect_knowledge_entries=collect_knowledge_entries,
        next_knowledge_id=next_knowledge_id,
        update_knowledge_index=update_knowledge_index,
        knowledge_detail_path=knowledge_detail_path,
        knowledge_table_header=KNOWLEDGE_TABLE_HEADER,
        valid_knowledge_statuses=VALID_KNOWLEDGE_STATUSES,
    )


def knowledge_draft_command(args: argparse.Namespace) -> int:
    return knowledge_commands.knowledge_draft_command(args, deps=knowledge_deps())


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


def render_knowledge_index_table(rows: Sequence[dict[str, str]]) -> str:
    lines = [
        KNOWLEDGE_TABLE_HEADER,
        "|---|---|---|---|---|---|",
    ]
    if rows:
        for row in rows:
            lines.append(
                render_table_row(
                    [
                        row["id"],
                        row["title"],
                        row["status"],
                        row["tags"],
                        row["summary"],
                        f"`{row['detail']}`",
                    ]
                )
            )
    else:
        lines.append("| 暂无 |  |  |  |  |  |")
    return "\n".join(lines)


def collect_knowledge_sync_rows(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    warnings: list[str] = []
    knowledge_dir = root / "reference" / "knowledge"
    if not knowledge_dir.exists():
        return rows, skipped, warnings

    for path in sorted(knowledge_dir.glob("K*.md")):
        match = re.match(r"^(K\d{3})-", path.name)
        rel = path.relative_to(root).as_posix()
        if match is None:
            skipped.append({"path": rel, "reason": "knowledge file name does not start with KNNN-"})
            continue
        status = extract_heading_value(path, "## 状态") or "Draft"
        if status not in VALID_KNOWLEDGE_STATUSES:
            skipped.append({"id": match.group(1), "path": rel, "reason": f"invalid knowledge status `{status}`"})
            warnings.append(f"{rel}: skipped invalid knowledge status `{status}`")
            continue
        text = read_text(path)
        summary = extract_heading_value(path, "## 摘要") or ""
        if not summary:
            summary = next((line.strip() for line in safe_section_body_from_text(text, "## 摘要").splitlines() if line.strip()), "")
        rows.append(
            {
                "id": match.group(1),
                "title": knowledge_title_from_text(text, path.stem),
                "status": status,
                "tags": extract_heading_value(path, "## 标签") or "未分类",
                "summary": summary.strip() or "无。",
                "detail": rel,
            }
        )
    return rows, skipped, warnings


def skipped_missing_generated_knowledge_details(root: Path, index_text: str) -> list[dict[str, str]]:
    if KNOWLEDGE_INDEX_MARKER_START not in index_text or KNOWLEDGE_INDEX_MARKER_END not in index_text:
        return []
    start = index_text.index(KNOWLEDGE_INDEX_MARKER_START) + len(KNOWLEDGE_INDEX_MARKER_START)
    end = index_text.index(KNOWLEDGE_INDEX_MARKER_END, start)
    marker_body = index_text[start:end]
    skipped: list[dict[str, str]] = []
    index_path = knowledge_index_path(root)
    for cells in parse_markdown_table_rows(marker_body):
        if len(cells) < 6 or cells[0] in {"ID", "暂无"}:
            continue
        ref = strip_code_ticks(cells[5])
        if should_check_ref(ref) and resolve_ref(root, index_path, ref) is None:
            skipped.append({"id": cells[0], "path": ref, "reason": "detail source is missing"})
    return skipped


def knowledge_sync_command(args: argparse.Namespace) -> int:
    return knowledge_commands.knowledge_sync_command(args, deps=knowledge_deps())


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
    return knowledge_commands.knowledge_apply_command(args, deps=knowledge_deps())


def knowledge_list_command(args: argparse.Namespace) -> int:
    return knowledge_commands.knowledge_list_command(args, deps=knowledge_deps())


def knowledge_detail_path(root: Path, knowledge_id: str) -> Path:
    index_path = knowledge_index_path(root)
    if index_path.exists():
        for cells in parse_markdown_table_rows(read_text(index_path)):
            if len(cells) >= 6 and cells[0] == knowledge_id:
                return resolve_context_existing_path(root, cells[5])
    raise SystemExit(f"knowledge id was not found: {knowledge_id}")


def knowledge_show_command(args: argparse.Namespace) -> int:
    return knowledge_commands.knowledge_show_command(args, deps=knowledge_deps())


def knowledge_mark_command(args: argparse.Namespace) -> int:
    return knowledge_commands.knowledge_mark_command(args, deps=knowledge_deps())


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


def review_audit_curate_deps() -> review_audit_curate_commands.ReviewAuditCurateDependencies:
    return review_audit_curate_commands.ReviewAuditCurateDependencies(
        maybe_check_after=maybe_check_after,
        parse_iso_date_value=parse_iso_date_value,
        collect_review_stale_items=collect_review_stale_items,
        review_stale_summary=review_stale_summary,
        review_stale_next_actions=review_stale_next_actions,
        collect_audit_context_candidates=collect_audit_context_candidates,
        audit_context_summary=audit_context_summary,
        audit_context_next_actions=audit_context_next_actions,
        curation_draft_path=curation_draft_path,
        render_curation_draft=render_curation_draft,
    )


def review_stale_command(args: argparse.Namespace) -> int:
    return review_audit_curate_commands.review_stale_command(args, deps=review_audit_curate_deps())


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
    return review_audit_curate_commands.audit_context_command(args, deps=review_audit_curate_deps())


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
    return review_audit_curate_commands.curate_draft_command(args, deps=review_audit_curate_deps())


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


def check_human_index(root: Path, errors: list[str]) -> None:
    index_path = human_index_path(root)
    if not index_path.exists():
        return
    try:
        rows = read_human_index_rows(index_path)
    except SystemExit as exc:
        errors.append(f"human/Human_Index.md: {exc}")
        return
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    human_root = (root / "human").resolve()
    for row in rows:
        item_id = row.get("ID", "").strip()
        status = row.get("状态", "").strip()
        rel_path = clean_human_index_path_cell(row.get("路径", ""))
        label = item_id or rel_path or "unknown"
        if status and status not in VALID_HUMAN_INDEX_STATUSES:
            errors.append(f"human/Human_Index.md: invalid status `{status}` for `{label}`")
        if item_id and item_id != "暂无":
            if item_id in seen_ids:
                errors.append(f"human/Human_Index.md: duplicate ID `{item_id}`")
            seen_ids.add(item_id)
        if not rel_path or rel_path == "暂无":
            continue
        target_ref, _fragment = split_ref_fragment(rel_path)
        target = (human_root / target_ref).resolve()
        if not is_relative_to(target, human_root) or not target.exists():
            errors.append(f"human/Human_Index.md: missing indexed path `{rel_path}`")
        if not item_id:
            if rel_path in seen_paths:
                errors.append(f"human/Human_Index.md: duplicate path `{rel_path}`")
            seen_paths.add(rel_path)


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
    kind = workstream_type(detail)
    merge_targets = detail.metadata.get("merge_targets")
    has_merge_targets = isinstance(merge_targets, list) and any(str(target).strip() for target in merge_targets)
    rows = read_workstream_stage_rows(detail.body)
    unfinished_stages = [
        row.get("ID", "")
        for row in rows
        if row.get("状态") not in {"Done", "Skipped", "Cancelled"}
    ]
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
        if unfinished_stages:
            errors.append(f"{rel}: ReadyToMerge workstream has unfinished stage `{unfinished_stages[0]}`")
    elif status == "Merging":
        if kind not in {"Merge", "Maintenance"}:
            errors.append(f"{rel}: Merging status requires type Merge or Maintenance")
        if not merge_request_has_required_fields(detail.body):
            errors.append(f"{rel}: Merging workstream missing merge target or candidate summary")
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
        kind = workstream_type(detail)
        merge_owner = detail.metadata.get("merge_owner")
        coordination = detail.metadata.get("coordination")
        write_scope = detail.metadata.get("write_scope")
        if not isinstance(write_scope, list):
            continue
        rel = detail.path.relative_to(root).as_posix()
        for item in write_scope:
            scope_type, scope_path = split_typed_scope(item)
            if not scope_type or not scope_path or scope_type not in {"authority", "draft", "owned", "assigned", "shared", "evidence"}:
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
            if scope_type == "authority" and kind == "Task":
                check_warn_or_error(
                    f"{rel}: Task workstream declares authority write_scope `{normalized_path}`; use merge_targets and merge-request instead",
                    errors,
                    warnings,
                    strict,
                )
            if scope_type == "shared" and required_field_missing(merge_owner) and coordination != "serial":
                check_warn_or_error(
                    f"{rel}: shared write_scope `{normalized_path}` requires merge_owner or coordination: serial",
                    errors,
                    warnings,
                    strict,
                )
            if scope_type == "draft" and detail.workstream_id not in Path(normalized_path).name:
                check_warn_or_error(
                    f"{rel}: draft write_scope should include {detail.workstream_id} in the file name: {normalized_path}",
                    errors,
                    warnings,
                    strict,
                )
            if isinstance(status, str) and status in ACTIVE_WORKSTREAM_STATUSES and scope_type in {"authority", "assigned", "owned"}:
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
    check_human_index(path, errors)
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
    return status_check_commands.check_command(args, check_context=check_context)


def status_command(args: argparse.Namespace) -> int:
    return status_check_commands.status_command(
        args,
        check_context=check_context,
        extract_current_task_status=extract_current_task_status,
    )


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

    knowledge_sync_parser = knowledge_subparsers.add_parser("sync", help="sync the generated Knowledge index block")
    knowledge_sync_parser.add_argument("path", nargs="?", type=Path)
    knowledge_sync_parser.add_argument("--init-marker", action="store_true", help="insert generated markers when missing")
    add_write_arguments(knowledge_sync_parser)
    knowledge_sync_parser.set_defaults(func=knowledge_sync_command)

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
