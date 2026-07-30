"""Legacy runtime functions split out for agent-friendly navigation.

Names in this module are rebound by ai_context_framework.runtime so the
migration can stay mechanical while behavior remains unchanged.
"""

from __future__ import annotations
import re

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
    workstreams: Sequence[str] = (),
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
        "workstreams": list(workstreams),
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


