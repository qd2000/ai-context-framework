"""Legacy runtime functions split out for agent-friendly navigation.

Names in this module are rebound by ai_context_framework.runtime so the
migration can stay mechanical while behavior remains unchanged.
"""

from __future__ import annotations
import re
import inspect

from ai_context_framework.commands import workstream as workstream_commands
from ai_context_framework.commands import workstream_reserve as workstream_reserve_commands

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
            "attention": VALID_WORKSTREAM_ATTENTION,
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

Workstream 是可选并行目标线协议。启用后采用强隔离协作约束：详情文件 front matter 是唯一事实源，索引由工具同步，AI 执行前先读取专属 context packet，完成、ready、done 或切换状态前优先用 guard 的显式文件集模式检查本次改动。

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
5. AI 执行前运行 `acf workstream context WSxxx`，完成、ready、done 或切换状态前优先运行 `acf workstream guard WSxxx --files <本次修改文件...> --json`；裸 guard / `--from-git` 只用于快速查看当前 git diff，旧式整工作区排他检查需显式使用 `--workspace --strict-workspace`。
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
    attention: str | None = None,
    merge_owner: str | None = None,
    coordination: str | None = None,
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
    if attention is not None:
        metadata["attention"] = attention
    if merge_owner is not None:
        metadata["merge_owner"] = merge_owner
    if coordination is not None:
        metadata["coordination"] = coordination
    body = f"""# {workstream_id} - {title}

## 边界说明

本 Workstream 使用强隔离协作协议。AI 执行前应先运行 `acf workstream context {workstream_id}` 获取专属上下文入口；完成、ready、done 或切换状态前，应优先运行 `acf workstream guard {workstream_id} --files <本次修改文件...> --json` 对本次文件集做强验收。裸 guard / `--from-git` 只用于快速查看当前 git diff；旧式整工作区排他检查需显式使用 `--workspace --strict-workspace`。

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
    if status == current_status and not section_updates and not metadata_updates:
        return []
    if status != current_status and status not in allowed:
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


def workstream_reserve_command(args: argparse.Namespace) -> int:
    deps = workstream_deps()
    workstream_commands._bind(deps)
    symbols = dict(globals())
    symbols.update(vars(workstream_commands))
    return workstream_reserve_commands.workstream_reserve_command(
        args,
        deps=workstream_reserve_commands.WorkstreamReserveDependencies(symbols=symbols),
    )


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


def workstream_next_actions_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_next_actions_command(args, deps=workstream_deps())


def workstream_preflight_command(args: argparse.Namespace) -> int:
    return workstream_commands.workstream_preflight_command(args, deps=workstream_deps())


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


