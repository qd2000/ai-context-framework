"""Task-plan domain helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from ai_context_framework.markdown import (
    apply_section_body,
    find_section,
    normalized_section_body_lines,
    replace_section_text,
    section_body,
    section_content_and_suffix,
    strip_code_ticks,
)
from ai_context_framework.markers import PLACEHOLDER_RE
from ai_context_framework.models import PlanReference


PLAN_REFERENCE_BULLET_RE = re.compile(
    r"^-\s+(?:`(?P<path>reference/[^`\n]+\.md)`|"
    r"\[(?P<link_path>reference/[^\]\n]+\.md)\]\([^)]+\))"
    r"[：:]\s*(?P<purpose>.+?)\s*$"
)
PLAN_REFERENCE_HEADING = "## 规划依据"
PLAN_REFERENCE_EMPTY = "- 无。"
PLAN_REFERENCE_SECTION_INTRO = (
    "列出当前大任务必须对齐的 reference 设计、路线或差距文档；"
    "只放路径和一句话用途，不复制详细规划。"
)
PLAN_REFERENCE_UPGRADE_PROMPT = "- 使用 `acf plan reference add` 添加当前大任务必须对齐的 reference 规划依据。"
CURRENT_TASK_REFERENCE_PROMPT = "- 相关 reference 规划依据请查看 `active/Task_Plan.md` 的 `## 规划依据`。"


def normalize_plan_reference_path(value: str) -> str:
    normalized = strip_code_ticks(value).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or "\\" in normalized
        or any(part in {"", ".", ".."} for part in parts)
        or parts[0] != "reference"
        or not normalized.lower().endswith(".md")
    ):
        raise SystemExit("plan reference path must be a relative reference/*.md path")
    return "/".join(parts)


def normalize_plan_reference_purpose(value: str) -> str:
    purpose = value.strip()
    if not purpose:
        raise SystemExit("plan reference purpose cannot be empty")
    if purpose[-1] not in "。.！!?？":
        purpose += "。"
    return purpose


def render_plan_reference(reference: PlanReference) -> str:
    return f"- [{reference.path}](../{reference.path})：{reference.purpose}"


def render_plan_reference_input(reference: PlanReference) -> str:
    return f"[{reference.path}](../{reference.path})：{reference.purpose}"


def render_plan_reference_section(
    references: Sequence[PlanReference],
    *,
    placeholder: bool = False,
    upgrade_prompt: bool = False,
) -> str:
    if placeholder:
        bullets = [
            "- `reference/【规划依据文档 1】.md`：【该规划依据的用途】。",
            "- `reference/【规划依据文档 2】.md`：【该规划依据的用途】。",
        ]
    elif upgrade_prompt:
        bullets = [PLAN_REFERENCE_EMPTY, PLAN_REFERENCE_UPGRADE_PROMPT]
    else:
        bullets = [render_plan_reference(reference) for reference in references] or [PLAN_REFERENCE_EMPTY]
    return "\n".join([PLAN_REFERENCE_SECTION_INTRO, "", *bullets])


def parse_plan_references_from_body(body: str) -> tuple[list[PlanReference], list[str]]:
    references: list[PlanReference] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for raw_line in normalized_section_body_lines(body):
        line = raw_line.strip()
        if not line.startswith("-"):
            continue
        if line in {PLAN_REFERENCE_EMPTY, "- 暂无。", PLAN_REFERENCE_UPGRADE_PROMPT}:
            continue
        match = PLAN_REFERENCE_BULLET_RE.match(line)
        if not match:
            warnings.append(f"ignored non-standard plan reference line: {line}")
            continue
        if PLACEHOLDER_RE.search(line):
            continue
        path = normalize_plan_reference_path(match.group("path") or match.group("link_path") or "")
        purpose = normalize_plan_reference_purpose(match.group("purpose"))
        if path in seen:
            warnings.append(f"ignored duplicate plan reference path: {path}")
            continue
        seen.add(path)
        references.append(PlanReference(path, purpose))
    return references, warnings


def read_plan_references(plan_path: Path) -> tuple[list[PlanReference], list[str]]:
    text = plan_path.read_text(encoding="utf-8")
    section = find_section(text.splitlines(), PLAN_REFERENCE_HEADING)
    return parse_plan_references_from_body(section_body(text.splitlines(), section))


def write_plan_references_text(text: str, references: Sequence[PlanReference]) -> str:
    return replace_section_text(text, PLAN_REFERENCE_HEADING, render_plan_reference_section(references))


def valid_plan_reference_input_lines(plan_path: Path) -> list[str]:
    try:
        references, _warnings = read_plan_references(plan_path)
    except SystemExit:
        return [CURRENT_TASK_REFERENCE_PROMPT.removeprefix("- ")]
    return [render_plan_reference_input(reference) for reference in references] or [
        CURRENT_TASK_REFERENCE_PROMPT.removeprefix("- ")
    ]


def current_task_has_active_status(text: str) -> bool:
    try:
        section = find_section(text.splitlines(), "## 当前任务状态")
    except SystemExit:
        return False
    body = section_body(text.splitlines(), section)
    return body.splitlines()[0].strip() == "Active" if body.strip() else False


def standard_reference_line_path(line: str) -> str | None:
    match = PLAN_REFERENCE_BULLET_RE.match(line.strip())
    if not match or PLACEHOLDER_RE.search(line):
        return None
    return normalize_plan_reference_path(match.group("path") or match.group("link_path") or "")


def sync_current_task_reference_text(
    text: str,
    reference: PlanReference,
    *,
    operation: str,
    force: bool = False,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not current_task_has_active_status(text):
        warnings.append("active/Current_Task.md is not Active; skipped reference sync")
        return text, warnings
    lines = text.splitlines()
    try:
        section = find_section(lines, "## 输入材料")
    except SystemExit:
        warnings.append("active/Current_Task.md has no ## 输入材料 section; skipped reference sync")
        return text, warnings

    body_lines, suffix = section_content_and_suffix(lines, section)
    target_line = render_plan_reference(reference)
    existing_index: int | None = None
    nonstandard_same_path = False
    for index, line in enumerate(body_lines):
        line_path = standard_reference_line_path(line)
        if line_path == reference.path:
            existing_index = index
            break
        if f"`{reference.path}`" in line:
            nonstandard_same_path = True

    if operation == "add":
        if existing_index is not None:
            if body_lines[existing_index].strip() == target_line:
                return text, warnings
            if force:
                body_lines[existing_index] = target_line
            else:
                warnings.append(f"active/Current_Task.md already references `{reference.path}` with a different purpose")
                return text, warnings
        elif nonstandard_same_path:
            warnings.append(f"active/Current_Task.md contains a non-standard reference line for `{reference.path}`; skipped reference sync")
            return text, warnings
        else:
            stripped = [line.strip() for line in body_lines if line.strip()]
            if stripped == [PLAN_REFERENCE_EMPTY]:
                body_lines = [target_line]
            else:
                insert_at = len(body_lines)
                while insert_at > 0 and not body_lines[insert_at - 1].strip():
                    insert_at -= 1
                body_lines.insert(insert_at, target_line)
    elif operation == "remove":
        if existing_index is None:
            if nonstandard_same_path:
                warnings.append(f"active/Current_Task.md keeps a non-standard reference line for `{reference.path}`")
            return text, warnings
        if body_lines[existing_index].strip() == target_line:
            body_lines.pop(existing_index)
        else:
            warnings.append(f"active/Current_Task.md reference for `{reference.path}` differs from the plan entry; skipped reference sync")
            return text, warnings
    else:
        raise SystemExit(f"unknown reference sync operation: {operation}")

    return apply_section_body(lines, section, body_lines, suffix), warnings
