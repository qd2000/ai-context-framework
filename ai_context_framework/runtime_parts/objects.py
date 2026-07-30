"""Legacy runtime functions split out for agent-friendly navigation.

Names in this module are rebound by ai_context_framework.runtime so the
migration can stay mechanical while behavior remains unchanged.
"""

from __future__ import annotations
import re

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
    workstreams: Sequence[str] = (),
) -> str:
    workstream_text = bullet_list([f"`{item}`" for item in workstreams]) if workstreams else "无。"

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

## 所属 Workstream

{workstream_text}

---

## 当前执行线

{workstream_text}

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


