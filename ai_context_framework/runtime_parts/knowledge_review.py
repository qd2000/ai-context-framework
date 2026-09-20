"""Legacy runtime functions split out for agent-friendly navigation.

Names in this module are rebound by ai_context_framework.runtime so the
migration can stay mechanical while behavior remains unchanged.
"""

from __future__ import annotations
import re

from ai_context_framework.constants import DEFAULT_STALE_DAYS

def resolve_context_existing_path(root: Path, value: str) -> Path:
    candidate = Path(strip_code_ticks(value))
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not is_relative_to(resolved, root):
        raise SystemExit(f"path is outside context root: {value}")
    if not resolved.exists():
        raise SystemExit(f"path does not exist: {value}")
    return resolved


def render_knowledge_draft(
    title: str,
    sources: Sequence[str],
    tags: str,
    summary: str,
    evidence: Sequence[str] | None = None,
    applies_to: Sequence[str] | None = None,
    not_applies_to: Sequence[str] | None = None,
    read_when: Sequence[str] | None = None,
    from_workstream: str | None = None,
) -> str:
    source_lines = "\n".join(f"- `{source}`" for source in sources)
    evidence_values = list(evidence or [])
    applies_to_values = list(applies_to or [])
    not_applies_to_values = list(not_applies_to or [])
    read_when_values = list(read_when or [])
    metadata_lines = [
        "---",
        "id: K-DRAFT",
        "status: Draft",
        "tags:",
        *(f"  - {tag.strip()}" for tag in [tags or "未分类"] if tag.strip()),
        "source:",
        *(f"  - {source}" for source in sources),
        "evidence:",
        *(f"  - {item}" for item in evidence_values),
        "validated_by:",
        *(f"  - workstream:{from_workstream}" for _ in [from_workstream] if from_workstream),
        "applies_to:",
        *(f"  - {item}" for item in applies_to_values),
        "not_applies_to:",
        *(f"  - {item}" for item in not_applies_to_values),
        "read_when:",
        *(f"  - {item}" for item in read_when_values),
        f"last_reviewed: {date.today().isoformat()}",
        "stale_after_days: 60",
        "promoted_to: []",
        "supersedes: []",
        "depends_on: []",
        "derived_from: []",
        "related: []",
        "---",
    ]
    evidence_lines = "\n".join(f"- `{item}`" for item in evidence_values) or "- 待补充。"
    applies_lines = "\n".join(f"- {item}" for item in applies_to_values) or "- 待补充。"
    not_applies_lines = "\n".join(f"- {item}" for item in not_applies_to_values) or "- 待补充。"
    metadata_text = "\n".join(metadata_lines)
    return f"""{metadata_text}
# K-草案：{title}

## 状态

Draft

## 标签

{tags or "未分类"}

## 摘要

{summary or "待补充。"}

## 结论

待提炼为一句可复用经验，不写当前事实。

## 适用场景

{applies_lines}

## 不适用场景

{not_applies_lines}

## 证据

{evidence_lines}

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
    _metadata, body, diagnostics = parse_front_matter(text)
    if not diagnostics and body != text:
        text = body
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
    if status == "Done":
        return [
            stale_item(
                root,
                path,
                "current_task",
                "current_task_terminal_retained",
                "Current_Task is Done but remains retained as non-empty active authority.",
                "Archive or clear the terminal Current_Task after reviewing its completion evidence.",
                status=status,
            )
        ]
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
    if status == "Done":
        items.append(
            stale_item(
                root,
                path,
                "task_plan",
                "task_plan_terminal_retained",
                "Task_Plan is Done but remains retained as non-empty active authority.",
                "Archive or clear the terminal Task_Plan after reviewing its completion evidence.",
                status=status,
            )
        )
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


