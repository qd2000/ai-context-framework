"""Markdown table helpers."""

from __future__ import annotations

import re
from typing import Sequence

from ai_context_framework.models import TableRange


def clean_table_cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "/")


def table_cell(value: str, default: str = "无。") -> str:
    value = value.strip()
    return clean_table_cell(value or default)


def split_table_line(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def is_table_separator(line: str) -> bool:
    if not is_table_line(line):
        return False
    cells = split_table_line(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def table_header_matches(line: str, header: str | None) -> bool:
    if header is None:
        return True
    if not is_table_line(line):
        return False
    return split_table_line(line) == split_table_line(header)


def find_table(lines: Sequence[str], header: str | None) -> TableRange:
    for index, line in enumerate(lines[:-1]):
        if not table_header_matches(line, header):
            continue
        if not is_table_line(line) or not is_table_separator(lines[index + 1]):
            continue

        body_start = index + 2
        body_end = body_start
        while body_end < len(lines) and is_table_line(lines[body_end]):
            body_end += 1
        return TableRange(index, index + 1, body_start, body_end, split_table_line(line))

    if header is None:
        raise SystemExit("Markdown table was not found")
    raise SystemExit(f"Markdown table header was not found: {header}")


def render_table_row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(clean_table_cell(cell) for cell in cells) + " |"


def parse_markdown_table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(set(cell) <= {"-", " "} for cell in cells):
            continue
        rows.append(cells)
    return rows


def parse_cell_updates(values: Sequence[str]) -> dict[str, str]:
    updates: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"table cell update must use COLUMN=VALUE: {value}")
        column, cell_value = value.split("=", 1)
        column = column.strip()
        if not column:
            raise SystemExit(f"table cell update has empty column name: {value}")
        updates[column] = cell_value.strip()
    return updates


def upsert_table_row(
    original: str,
    header: str | None,
    key_column: str,
    key: str,
    cell_updates: dict[str, str],
) -> str:
    lines = original.splitlines()
    table = find_table(lines, header)
    headers = table.headers
    if key_column not in headers:
        raise SystemExit(f"table key column was not found: {key_column}")

    unknown_columns = sorted(set(cell_updates) - set(headers))
    if unknown_columns:
        raise SystemExit(f"table cell column was not found: {', '.join(unknown_columns)}")

    key_index = headers.index(key_column)
    updated_rows = list(lines[table.body_start : table.body_end])
    target_row_index: int | None = None
    for index, row in enumerate(updated_rows):
        row_cells = split_table_line(row)
        if len(row_cells) != len(headers):
            raise SystemExit(f"table row has {len(row_cells)} cells but header has {len(headers)} cells: {row}")
        if row_cells[key_index] == key:
            target_row_index = index
            break

    if target_row_index is None:
        row_cells = [""] * len(headers)
    else:
        row_cells = split_table_line(updated_rows[target_row_index])

    row_cells[key_index] = key
    for column, value in cell_updates.items():
        row_cells[headers.index(column)] = value

    rendered = render_table_row(row_cells)
    if target_row_index is None:
        updated_rows.append(rendered)
    else:
        updated_rows[target_row_index] = rendered

    updated_lines = list(lines[: table.body_start]) + updated_rows + list(lines[table.body_end :])
    return "\n".join(updated_lines).rstrip() + "\n"
