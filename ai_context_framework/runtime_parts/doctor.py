"""Legacy runtime functions split out for agent-friendly navigation.

Names in this module are rebound by ai_context_framework.runtime so the
migration can stay mechanical while behavior remains unchanged.
"""

from __future__ import annotations
import re

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


def collect_attention_hygiene_doctor_findings(
    root: Path,
    today_value: date,
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    surfaced_stale_signals = {
        "current_task_terminal_retained",
        "task_plan_terminal_retained",
        "context_missing_review_marker",
        "context_review_stale",
    }
    for item in collect_review_stale_items(root, DEFAULT_STALE_DAYS, today_value):
        signal = str(item.get("signal") or "")
        if signal not in surfaced_stale_signals:
            continue
        path = str(item.get("path") or "")
        reason = str(item.get("reason") or signal)
        action = str(item.get("suggested_action") or "Review this attention-hygiene signal.")
        findings.append(
            doctor_finding(
                signal,
                "warning",
                "attention_hygiene",
                reason,
                path,
                [path],
                [{"path": path, "detail": reason}],
                "draft_only",
                False,
                [action],
            )
        )
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
    findings.extend(collect_attention_hygiene_doctor_findings(root, _today))
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


