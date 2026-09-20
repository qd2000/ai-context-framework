"""Legacy runtime functions split out for agent-friendly navigation.

Names in this module are rebound by ai_context_framework.runtime so the
migration can stay mechanical while behavior remains unchanged.
"""

from __future__ import annotations
import re

from ai_context_framework.constants import VALID_HUMAN_INDEX_STATUSES

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
            rel_adr = relative_display_path(resolved, root)
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
    path = path.resolve()

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


