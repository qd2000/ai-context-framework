"""ACF marker and placeholder helpers."""

from __future__ import annotations

import re
from datetime import date
from typing import Sequence

from ai_context_framework.markdown import find_section, normalized_section_body_lines, strip_code_ticks
from ai_context_framework.tables import find_table, split_table_line


PLACEHOLDER_RE = re.compile(r"【[^】]+】")
ACF_PLACEHOLDER_RE = re.compile(r"^【ACF:[A-Z0-9_:-]+(?:\|[^】]+)?】$")
ACF_MARKER_RE = re.compile(r"<!--\s*ACF:([A-Z0-9_-]+):([A-Z0-9_-]+):(START|END)\s*-->")

KNOWLEDGE_INDEX_MARKER_START = "<!-- ACF:KNOWLEDGE:INDEX-GENERATED:START -->"
KNOWLEDGE_INDEX_MARKER_END = "<!-- ACF:KNOWLEDGE:INDEX-GENERATED:END -->"
DECISIONS_INDEX_MARKER_START = "<!-- ACF:DECISIONS:INDEX-GENERATED:START -->"
DECISIONS_INDEX_MARKER_END = "<!-- ACF:DECISIONS:INDEX-GENERATED:END -->"
ARCHIVE_INDEX_MARKER_START = "<!-- ACF:ARCHIVE:INDEX-GENERATED:START -->"
ARCHIVE_INDEX_MARKER_END = "<!-- ACF:ARCHIVE:INDEX-GENERATED:END -->"
ARCHIVE_RECORD_MARKER_START = "<!-- ACF:ARCHIVE:RECORD:START -->"
ARCHIVE_RECORD_MARKER_END = "<!-- ACF:ARCHIVE:RECORD:END -->"
WORKSTREAM_ARCHIVE_MARKER_START = "<!-- ACF:WORKSTREAM:ARCHIVE-RECORD:START -->"
WORKSTREAM_ARCHIVE_MARKER_END = "<!-- ACF:WORKSTREAM:ARCHIVE-RECORD:END -->"
LEGACY_WORKSTREAM_ARCHIVE_MARKER_START = "<!-- ACF:WORKSTREAM-ARCHIVE:START -->"
LEGACY_WORKSTREAM_ARCHIVE_MARKER_END = "<!-- ACF:WORKSTREAM-ARCHIVE:END -->"
UPGRADE_NOTES_START = "<!-- ACF:UPGRADE:NOTES:START -->"
UPGRADE_NOTES_END = "<!-- ACF:UPGRADE:NOTES:END -->"
LEGACY_UPGRADE_NOTES_START = "<!-- ACF:UPGRADE-NOTES:START -->"
LEGACY_UPGRADE_NOTES_END = "<!-- ACF:UPGRADE-NOTES:END -->"

LEGACY_ACF_MARKER_REPLACEMENTS = {
    LEGACY_UPGRADE_NOTES_START: UPGRADE_NOTES_START,
    LEGACY_UPGRADE_NOTES_END: UPGRADE_NOTES_END,
    LEGACY_WORKSTREAM_ARCHIVE_MARKER_START: WORKSTREAM_ARCHIVE_MARKER_START,
    LEGACY_WORKSTREAM_ARCHIVE_MARKER_END: WORKSTREAM_ARCHIVE_MARKER_END,
}


def is_acf_placeholder(value: str) -> bool:
    return ACF_PLACEHOLDER_RE.match(value) is not None


def legacy_placeholder_count(placeholders: Sequence[str]) -> int:
    return sum(1 for placeholder in placeholders if not is_acf_placeholder(placeholder))


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


def replace_generated_marker_block(text: str, start_marker: str, end_marker: str, body: str) -> tuple[str, bool]:
    start_count = text.count(start_marker)
    end_count = text.count(end_marker)
    if start_count == 0 and end_count == 0:
        raise SystemExit(f"generated_marker_missing: missing generated marker {start_marker}")
    if start_count != end_count:
        raise SystemExit(f"generated_marker_unclosed: marker pair is not balanced for {start_marker}")
    if start_count > 1:
        raise SystemExit(f"generated_marker_duplicate: duplicate generated marker {start_marker}")

    lines = text.splitlines()
    start_index = next(index for index, line in enumerate(lines) if line.strip() == start_marker)
    end_index = next((index for index in range(start_index + 1, len(lines)) if lines[index].strip() == end_marker), None)
    if end_index is None:
        raise SystemExit(f"generated_marker_unclosed: marker pair is not balanced for {start_marker}")

    replacement = [start_marker, *normalized_section_body_lines(body), end_marker]
    updated = lines[:start_index] + replacement + lines[end_index + 1 :]
    updated_text = "\n".join(updated).rstrip() + "\n"
    return updated_text, updated_text != text


def insert_generated_marker_block_after_heading(
    text: str,
    heading: str,
    start_marker: str,
    end_marker: str,
    body: str,
    *,
    replace_empty_table_header: str | None = None,
) -> tuple[str, bool]:
    if start_marker in text or end_marker in text:
        return replace_generated_marker_block(text, start_marker, end_marker, body)

    lines = text.splitlines()
    section = find_section(lines, heading)
    block = [start_marker, *normalized_section_body_lines(body), end_marker]
    if replace_empty_table_header is not None:
        section_lines = lines[section.body_start : section.body_end]
        try:
            table = find_table(section_lines, replace_empty_table_header)
        except SystemExit:
            table = None
        if table is not None:
            body_rows = section_lines[table.body_start : table.body_end]
            if all((split_table_line(row) or [""])[0] == "暂无" for row in body_rows):
                start = section.body_start + table.header_index
                end = section.body_start + table.body_end
                updated = lines[:start] + block + lines[end:]
                updated_text = "\n".join(updated).rstrip() + "\n"
                return updated_text, updated_text != text

    insert_at = section.body_start
    while insert_at < section.body_end and not lines[insert_at].strip():
        insert_at += 1
    updated = lines[:insert_at] + block + [""] + lines[insert_at:]
    updated_text = "\n".join(updated).rstrip() + "\n"
    return updated_text, updated_text != text


def archive_record_marker(
    archive_date: str,
    item_type: str,
    item_id: str,
    source_rel: str,
    archive_rel: str,
    status: str,
    reason: str,
) -> str:
    return f"""{ARCHIVE_RECORD_MARKER_START}
- archived_at: {archive_date}
- item_type: {item_type}
- item_id: {item_id}
- source_path: {source_rel}
- archive_path: `{archive_rel}`
- status: {status}
- archive_reason: {reason}
{ARCHIVE_RECORD_MARKER_END}
"""


def marker_fields(text: str, start_marker: str, end_marker: str) -> dict[str, str] | None:
    if start_marker not in text or end_marker not in text:
        return None
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        return None
    body = text[start + len(start_marker) : end]
    fields: dict[str, str] = {}
    for line in body.splitlines():
        match = re.match(r"^-\s+([A-Za-z_]+):\s*(.+?)\s*$", line.strip())
        if match:
            fields[match.group(1)] = strip_code_ticks(match.group(2))
    return fields


def workstream_archive_marker_fields(text: str) -> dict[str, str] | None:
    return marker_fields(text, WORKSTREAM_ARCHIVE_MARKER_START, WORKSTREAM_ARCHIVE_MARKER_END)


def workstream_archive_marker(archive_date: date, source_rel: str, archive_rel: str, reason: str) -> str:
    return f"""{WORKSTREAM_ARCHIVE_MARKER_START}
## 归档记录

- archived_at: {archive_date.isoformat()}
- source_path: {source_rel}
- archive_path: `{archive_rel}`
- archive_reason: {reason}
{WORKSTREAM_ARCHIVE_MARKER_END}
"""
