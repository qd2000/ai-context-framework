"""Markdown section helpers."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import unquote

from ai_context_framework.models import SectionRange
from ai_context_framework.paths import infer_project_root, is_relative_to


MARKDOWN_REF_RE = re.compile(r"`([^`\n]+\.md)`")
MARKDOWN_LINK_RE = re.compile(r"(!?)\[([^\]\n]*)\]\(([^)\n]+)\)")
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+\S.*$")
PATH_LIKE_RE = re.compile(
    r"(?<![\w./\\:-])"
    r"((?:\.{1,2}/)?(?:[A-Za-z0-9_.\-\u4e00-\u9fff]+/)+"
    r"[A-Za-z0-9_.\-\u4e00-\u9fff]+(?:\.[A-Za-z0-9]+)"
    r"(?:#[A-Za-z0-9_.%\-_\u4e00-\u9fff]+)?)"
)
PLACEHOLDER_RE = re.compile(r"【[^】]+】")


def heading_level(line: str) -> int | None:
    match = MARKDOWN_HEADING_RE.match(line.strip())
    if match is None:
        return None
    return len(match.group(1))


def find_section(lines: Sequence[str], heading: str) -> SectionRange:
    expected = heading.strip()
    if heading_level(expected) is None:
        raise SystemExit(f"section heading must be a Markdown heading: {heading}")

    heading_index = next((index for index, line in enumerate(lines) if line.strip() == expected), None)
    if heading_index is None:
        raise SystemExit(f"section heading was not found: {heading}")

    level = heading_level(lines[heading_index])
    if level is None:
        raise SystemExit(f"section heading must be a Markdown heading: {heading}")

    body_start = heading_index + 1
    body_end = len(lines)
    for index in range(body_start, len(lines)):
        candidate_level = heading_level(lines[index])
        if candidate_level is not None and candidate_level <= level:
            body_end = index
            break

    return SectionRange(heading_index, body_start, body_end, level)


def section_content_and_suffix(lines: Sequence[str], section: SectionRange) -> tuple[list[str], list[str]]:
    content = list(lines[section.body_start : section.body_end])
    while content and not content[-1].strip():
        content.pop()

    suffix: list[str] = []
    if content and content[-1].strip() == "---":
        content.pop()
        while content and not content[-1].strip():
            content.pop()
        suffix = ["---", ""]

    while content and not content[0].strip():
        content.pop(0)

    return content, suffix


def section_body(lines: Sequence[str], section: SectionRange) -> str:
    content, _suffix = section_content_and_suffix(lines, section)
    return "\n".join(content).strip("\n")


def normalized_section_body_lines(text: str) -> list[str]:
    stripped = text.strip("\n")
    return stripped.splitlines() if stripped else []


def apply_section_body(
    lines: Sequence[str],
    section: SectionRange,
    body_lines: Sequence[str],
    suffix_lines: Sequence[str] | None = None,
) -> str:
    replacement = list(body_lines)
    new_section = [lines[section.heading_index], ""]
    new_section.extend(replacement)
    suffix = list(suffix_lines or [])
    if suffix:
        if replacement:
            new_section.append("")
        new_section.extend(suffix)
    elif replacement:
        new_section.append("")

    updated_lines = (
        list(lines[: section.heading_index])
        + new_section
        + list(lines[section.body_end :])
    )
    return "\n".join(updated_lines).rstrip() + "\n"


def replace_section_text(original: str, heading: str, replacement: str) -> str:
    lines = original.splitlines()
    section = find_section(lines, heading)
    _content, suffix = section_content_and_suffix(lines, section)
    return apply_section_body(lines, section, normalized_section_body_lines(replacement), suffix)


def append_section_text(original: str, heading: str, addition: str) -> str:
    lines = original.splitlines()
    section = find_section(lines, heading)
    body_lines, suffix = section_content_and_suffix(lines, section)
    addition_lines = normalized_section_body_lines(addition)
    if body_lines and addition_lines:
        body_lines.append("")
    body_lines.extend(addition_lines)
    return apply_section_body(lines, section, body_lines, suffix)


def insert_section_after(text: str, anchor_heading: str, heading: str, body: str) -> str:
    lines = text.splitlines()
    anchor = find_section(lines, anchor_heading)
    insert_at = anchor.body_end
    while insert_at > anchor.body_start and not lines[insert_at - 1].strip():
        insert_at -= 1
    if insert_at > anchor.body_start and lines[insert_at - 1].strip() == "---":
        insert_at -= 1
        while insert_at > anchor.body_start and not lines[insert_at - 1].strip():
            insert_at -= 1
    section_lines = ["", "---", "", heading, "", *normalized_section_body_lines(body), ""]
    updated = lines[:insert_at] + section_lines + lines[insert_at:]
    return "\n".join(updated).rstrip() + "\n"


def insert_section_before(text: str, anchor_heading: str, heading: str, body: str) -> str:
    lines = text.splitlines()
    anchor = find_section(lines, anchor_heading)
    insert_at = anchor.heading_index
    while insert_at > 0 and not lines[insert_at - 1].strip():
        insert_at -= 1
    section_lines = [heading, "", *normalized_section_body_lines(body), "", "---", ""]
    updated = lines[:insert_at] + section_lines + lines[insert_at:]
    return "\n".join(updated).rstrip() + "\n"


def remove_markdown_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        return text
    end = next(
        (
            index
            for index, line in enumerate(lines[start + 1 :], start=start + 1)
            if line.strip().startswith("## ")
        ),
        len(lines),
    )
    updated = lines[:start] + lines[end:]
    return "\n".join(updated).rstrip() + "\n"


def section_insert_after_line(text: str, heading: str) -> int:
    lines = text.splitlines()
    section = find_section(lines, heading)
    insert_index = section.body_end
    while insert_index > section.body_start and not lines[insert_index - 1].strip():
        insert_index -= 1
    if insert_index > section.body_start and lines[insert_index - 1].strip() == "---":
        insert_index -= 1
        while insert_index > section.body_start and not lines[insert_index - 1].strip():
            insert_index -= 1
    return insert_index if insert_index > section.body_start else section.heading_index + 1


def replace_or_append_section(text: str, heading: str, replacement: str) -> str:
    try:
        return replace_section_text(text, heading, replacement)
    except SystemExit:
        return text.rstrip() + f"\n\n---\n\n{heading}\n\n{replacement.strip()}\n"


def append_or_create_section(text: str, heading: str, addition: str) -> str:
    try:
        return append_section_text(text, heading, addition)
    except SystemExit:
        return text.rstrip() + f"\n\n---\n\n{heading}\n\n{addition.strip()}\n"


def subsection_body(text: str, heading: str) -> str:
    lines = text.splitlines()
    heading_index = next((index for index, line in enumerate(lines) if line.strip() == heading), None)
    if heading_index is None:
        return ""
    body_start = heading_index + 1
    body_end = len(lines)
    for index in range(body_start, len(lines)):
        if heading_level(lines[index]) is not None and heading_level(lines[index]) <= 3:
            body_end = index
            break
    return "\n".join(lines[body_start:body_end]).strip()


def safe_section_body_from_text(text: str, heading: str) -> str:
    try:
        lines = text.splitlines()
        return section_body(lines, find_section(lines, heading))
    except SystemExit:
        return ""


def markdown_sections(text: str) -> list[tuple[int, str, list[str]]]:
    lines = text.splitlines()
    sections: list[tuple[int, str, list[str]]] = []
    for index, line in enumerate(lines):
        level = heading_level(line)
        if level is None:
            continue
        body_end = len(lines)
        for candidate_index in range(index + 1, len(lines)):
            candidate_level = heading_level(lines[candidate_index])
            if candidate_level is not None and candidate_level <= level:
                body_end = candidate_index
                break
        title = line.strip().lstrip("#").strip()
        sections.append((level, title, lines[index + 1 : body_end]))
    return sections


def section_contains_child_heading(body_lines: list[str]) -> bool:
    return any(heading_level(line) is not None for line in body_lines)


def safe_section_body(path: Path, heading: str) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return section_body(lines, find_section(lines, heading))
    except SystemExit:
        return None


def markdown_link_target_for(md_file: Path, target_file: Path, fragment: str = "") -> str:
    relative = os.path.relpath(target_file, start=md_file.parent).replace("\\", "/")
    if fragment:
        relative = f"{relative}#{fragment}"
    return relative


def render_markdown_link_target(target: str) -> str:
    if any(char in target for char in " ()"):
        return f"<{target}>"
    return target


def render_markdown_link(text: str, target: str) -> str:
    return f"[{text}]({render_markdown_link_target(target)})"


def render_existing_markdown_link(prefix: str, text: str, target: str) -> str:
    return f"{prefix}[{text}]({render_markdown_link_target(target)})"


def clean_markdown_link_target(value: str) -> str:
    target = value.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    return target


def split_ref_fragment(ref: str) -> tuple[str, str]:
    if "#" not in ref:
        return ref, ""
    target, fragment = ref.split("#", 1)
    return target, fragment


def should_check_ref(ref: str) -> bool:
    if "*" in ref:
        return False
    if PLACEHOLDER_RE.search(ref):
        return False
    if ref.startswith(("http://", "https://", "file://")):
        return False
    if ref.startswith("<") or ref.startswith("$"):
        return False
    return True


def is_uri_ref(ref: str) -> bool:
    return re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", ref) is not None


def is_local_link_ref(ref: str) -> bool:
    cleaned = clean_markdown_link_target(ref)
    if not cleaned or PLACEHOLDER_RE.search(cleaned) or "*" in cleaned:
        return False
    if cleaned in {"path", "url"}:
        return False
    if cleaned.startswith("$"):
        return False
    if is_uri_ref(cleaned):
        return False
    return True


def normalize_ref_path(ref: str) -> str:
    return unquote(ref.replace("\\", "/"))


def resolve_ref_path(root: Path, md_file: Path, ref: str) -> Path | None:
    normalized = normalize_ref_path(ref)
    root = root.resolve()
    project_root = infer_project_root(root).resolve()
    candidates = [
        (root / normalized).resolve(),
        (md_file.parent / normalized).resolve(),
        (project_root / normalized).resolve(),
    ]
    for candidate in candidates:
        if candidate.exists() and is_relative_to(candidate, project_root):
            return candidate
    return None


def resolve_ref(root: Path, md_file: Path, ref: str) -> Path | None:
    ref_path, _fragment = split_ref_fragment(clean_markdown_link_target(ref))
    return resolve_ref_path(root, md_file, ref_path)


def markdown_heading_slug(value: str) -> str:
    text = unicodedata.normalize("NFKC", value.strip()).lower()
    text = re.sub(r"\s+", "-", text)
    chars: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if char.isalnum() or category.startswith(("L", "N")):
            chars.append(char)
        elif char in {"-", "_"}:
            chars.append(char)
    slug = re.sub(r"-+", "-", "".join(chars)).strip("-")
    return slug


def markdown_heading_text(line: str) -> str | None:
    match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
    if not match:
        return None
    return re.sub(r"\s+#+\s*$", "", match.group(2)).strip()


def markdown_heading_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for line in text.splitlines():
        heading = markdown_heading_text(line)
        if heading is None:
            continue
        base = markdown_heading_slug(heading)
        index = seen.get(base, 0)
        seen[base] = index + 1
        anchors.add(base if index == 0 else f"{base}-{index}")
    return anchors


def markdown_heading_anchor_for(text: str, heading: str) -> str | None:
    wanted = heading.strip()
    if wanted.startswith("#"):
        wanted = wanted.lstrip("#").strip()
    seen: dict[str, int] = {}
    for line in text.splitlines():
        current = markdown_heading_text(line)
        if current is None:
            continue
        base = markdown_heading_slug(current)
        index = seen.get(base, 0)
        seen[base] = index + 1
        anchor = base if index == 0 else f"{base}-{index}"
        if current.strip() == wanted:
            return anchor
    return None


def iter_non_fenced_lines(text: str) -> Iterable[tuple[int, str]]:
    in_fence = False
    fence_marker = ""
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        fence = re.match(r"^(```+|~~~+)", stripped)
        if fence:
            marker = fence.group(1)[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if not in_fence:
            yield index, line


def validate_local_markdown_link(
    root: Path,
    md_file: Path,
    rel_file: str,
    raw_target: str,
    errors: list[str],
) -> None:
    target = clean_markdown_link_target(raw_target)
    if not is_local_link_ref(target):
        return
    target_ref, fragment = split_ref_fragment(target)
    if target_ref == "":
        target_path = md_file
    else:
        target_path = resolve_ref_path(root, md_file, target_ref)
        if target_path is None:
            errors.append(f"{rel_file}: broken markdown link `{target}`")
            return
    if fragment and target_path.suffix.lower() == ".md":
        anchors = markdown_heading_anchors(target_path.read_text(encoding="utf-8"))
        normalized_fragment = markdown_heading_slug(unquote(fragment))
        if fragment not in anchors and normalized_fragment not in anchors:
            errors.append(f"{rel_file}: broken markdown link anchor `{target}`")


def is_placeholder(value: str) -> bool:
    return "【" in value and "】" in value


def strip_code_ticks(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    link_match = MARKDOWN_LINK_RE.fullmatch(value)
    if link_match:
        return link_match.group(2).strip() or clean_markdown_link_target(link_match.group(3))
    return value


def rewrite_local_markdown_links_for_move(
    root: Path,
    source_md_file: Path,
    destination_md_file: Path,
    text: str,
) -> tuple[str, int]:
    updated_lines: list[str] = []
    replacements = 0
    in_fence = False
    fence_marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        fence = re.match(r"^(```+|~~~+)", stripped)
        if fence:
            marker = fence.group(1)[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            updated_lines.append(line)
            continue
        if in_fence:
            updated_lines.append(line)
            continue

        chunks: list[str] = []
        last = 0
        line_replacements = 0
        for match in MARKDOWN_LINK_RE.finditer(line):
            raw_target = match.group(3)
            target = clean_markdown_link_target(raw_target)
            if not is_local_link_ref(target):
                continue
            target_ref, fragment = split_ref_fragment(target)
            if target_ref == "":
                continue
            resolved = resolve_ref_path(root, source_md_file, target_ref)
            if resolved is None:
                continue
            rewritten_target = markdown_link_target_for(destination_md_file, resolved, fragment)
            if rewritten_target == target:
                continue
            chunks.append(line[last : match.start()])
            chunks.append(render_existing_markdown_link(match.group(1), match.group(2), rewritten_target))
            last = match.end()
            line_replacements += 1
        if line_replacements:
            chunks.append(line[last:])
            updated_lines.append("".join(chunks))
            replacements += line_replacements
        else:
            updated_lines.append(line)

    trailing_newline = "\n" if text.endswith("\n") else ""
    return "\n".join(updated_lines) + trailing_newline, replacements


def path_candidate_from_ref(root: Path, md_file: Path, ref_path: str, *, allow_missing: bool) -> Path | None:
    if not ref_path:
        return md_file
    resolved = resolve_ref_path(root, md_file, ref_path)
    if resolved is not None:
        return resolved
    if not allow_missing:
        return None
    normalized = normalize_ref_path(ref_path)
    if normalized.startswith(("../", "./")):
        candidate = (md_file.parent / normalized).resolve()
    else:
        candidate = (root / normalized).resolve()
    if not is_relative_to(candidate, root.resolve()):
        return None
    return candidate


def is_linkify_path_candidate(value: str) -> bool:
    candidate = clean_markdown_link_target(value.strip().strip("`"))
    if not is_local_link_ref(candidate):
        return False
    ref_path, _fragment = split_ref_fragment(candidate)
    if not ref_path or ref_path.endswith(("/", ".")):
        return False
    if " " in ref_path or "\t" in ref_path:
        return False
    if "/" not in ref_path and "\\" not in ref_path:
        return False
    return bool(Path(ref_path).suffix)


def linkify_candidate(
    root: Path,
    md_file: Path,
    candidate: str,
    *,
    allow_missing: bool,
) -> tuple[str | None, dict[str, str] | None]:
    display = candidate.strip().strip("`")
    if not is_linkify_path_candidate(display):
        return None, None
    ref_path, fragment = split_ref_fragment(clean_markdown_link_target(display))
    target_file = path_candidate_from_ref(root, md_file, ref_path, allow_missing=allow_missing)
    if target_file is None:
        return None, {"target": display, "reason": "missing target"}
    href = markdown_link_target_for(md_file, target_file, fragment)
    return render_markdown_link(display, href), None


def match_overlaps_spans(start: int, end: int, spans: Sequence[tuple[int, int]]) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in spans)


def replace_linkify_matches(
    line: str,
    pattern: re.Pattern[str],
    root: Path,
    md_file: Path,
    *,
    allow_missing: bool,
    protected_spans: Sequence[tuple[int, int]] = (),
) -> tuple[str, int, list[dict[str, str]]]:
    chunks: list[str] = []
    skipped: list[dict[str, str]] = []
    last = 0
    replacements = 0
    for match in pattern.finditer(line):
        if match_overlaps_spans(match.start(), match.end(), protected_spans):
            continue
        candidate = match.group(1)
        replacement, skip = linkify_candidate(root, md_file, candidate, allow_missing=allow_missing)
        if skip is not None:
            skipped.append(skip)
        if replacement is None:
            continue
        chunks.append(line[last : match.start()])
        chunks.append(replacement)
        last = match.end()
        replacements += 1
    if replacements == 0:
        return line, 0, skipped
    chunks.append(line[last:])
    return "".join(chunks), replacements, skipped


def linkify_markdown_text(
    root: Path,
    md_file: Path,
    text: str,
    *,
    allow_missing: bool,
) -> tuple[str, int, list[dict[str, str]]]:
    updated_lines: list[str] = []
    total = 0
    skipped: list[dict[str, str]] = []
    in_fence = False
    fence_marker = ""
    in_front_matter = False
    front_matter_done = False
    code_ref_re = re.compile(r"`([^`\n]+)`")
    for index, line in enumerate(text.splitlines()):
        if index == 0 and line.strip() == "---":
            in_front_matter = True
            updated_lines.append(line)
            continue
        if in_front_matter:
            updated_lines.append(line)
            if line.strip() == "---":
                in_front_matter = False
                front_matter_done = True
            continue
        if not front_matter_done and line.strip():
            front_matter_done = True

        stripped = line.lstrip()
        fence = re.match(r"^(```+|~~~+)", stripped)
        if fence:
            marker = fence.group(1)[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            updated_lines.append(line)
            continue
        if in_fence:
            updated_lines.append(line)
            continue

        link_spans = [(match.start(), match.end()) for match in MARKDOWN_LINK_RE.finditer(line)]
        line, count, line_skipped = replace_linkify_matches(
            line,
            code_ref_re,
            root,
            md_file,
            allow_missing=allow_missing,
            protected_spans=link_spans,
        )
        total += count
        skipped.extend(line_skipped)

        link_spans = [(match.start(), match.end()) for match in MARKDOWN_LINK_RE.finditer(line)]
        code_spans = [(match.start(), match.end()) for match in code_ref_re.finditer(line)]
        line, count, line_skipped = replace_linkify_matches(
            line,
            PATH_LIKE_RE,
            root,
            md_file,
            allow_missing=allow_missing,
            protected_spans=[*link_spans, *code_spans],
        )
        total += count
        skipped.extend(line_skipped)
        updated_lines.append(line)

    trailing_newline = "\n" if text.endswith("\n") else ""
    return "\n".join(updated_lines) + trailing_newline, total, skipped
