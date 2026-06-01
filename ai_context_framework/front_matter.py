"""Small, strict front matter parser and validator used by ACF metadata files."""

from __future__ import annotations

import re
from typing import Sequence

from ai_context_framework.models import FrontMatterDiagnostic, FrontMatterSchema


FRONT_MATTER_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
FRONT_MATTER_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
MARKDOWN_LIKE_SCOPE_PREFIXES = ("active/", "reference/", "decisions/", "rules/")


def diagnostic_codes(diagnostics: Sequence[FrontMatterDiagnostic]) -> list[str]:
    return [diagnostic.code for diagnostic in diagnostics]


def unsupported_front_matter_value(value: str) -> bool:
    stripped = value.strip()
    if stripped in {"|", ">"}:
        return True
    if stripped in {"true", "false", "True", "False"}:
        return True
    if FRONT_MATTER_NUMBER_RE.match(stripped):
        return True
    if stripped.startswith(("{", "[")) and stripped != "[]":
        return True
    if stripped.startswith(("'", '"')) or stripped.endswith(("'", '"')):
        return True
    return False


def parse_front_matter(
    text: str,
) -> tuple[dict[str, str | list[str]], str, list[FrontMatterDiagnostic]]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text, []

    end_index: int | None = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break

    if end_index is None:
        return (
            {},
            text,
            [
                FrontMatterDiagnostic(
                    "front_matter_unclosed",
                    "front matter opening marker has no closing marker",
                    line=1,
                )
            ],
        )

    metadata: dict[str, str | list[str]] = {}
    diagnostics: list[FrontMatterDiagnostic] = []
    current_list_key: str | None = None

    for line_number, raw_line in enumerate(lines[1:end_index], start=2):
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            continue

        if line.startswith("  - "):
            item = line[4:].strip()
            if current_list_key is None or not isinstance(metadata.get(current_list_key), list):
                diagnostics.append(
                    FrontMatterDiagnostic(
                        "front_matter_invalid_list_item",
                        "list item has no list field",
                        line=line_number,
                    )
                )
                continue
            if unsupported_front_matter_value(item):
                diagnostics.append(
                    FrontMatterDiagnostic(
                        "front_matter_unsupported_syntax",
                        "list item uses unsupported front matter syntax",
                        field=current_list_key,
                        line=line_number,
                    )
                )
                continue
            metadata[current_list_key].append(item)  # type: ignore[union-attr]
            continue

        current_list_key = None
        if line.startswith((" ", "\t")):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_unsupported_syntax",
                    "front matter only supports top-level fields and two-space list items",
                    line=line_number,
                )
            )
            continue

        if ":" not in line:
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_unsupported_syntax",
                    "front matter field must use KEY: VALUE syntax",
                    line=line_number,
                )
            )
            continue

        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not FRONT_MATTER_KEY_RE.match(key):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_invalid_key",
                    f"invalid front matter key: {key}",
                    field=key or None,
                    line=line_number,
                )
            )
            continue
        if key in metadata:
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_duplicate_key",
                    f"duplicate front matter key: {key}",
                    field=key,
                    line=line_number,
                )
            )
            continue

        if value == "[]":
            metadata[key] = []
        elif value == "":
            metadata[key] = []
            current_list_key = key
        elif unsupported_front_matter_value(value):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_unsupported_syntax",
                    "front matter value uses unsupported syntax",
                    field=key,
                    line=line_number,
                )
            )
        else:
            metadata[key] = value

    body = "".join(lines[end_index + 1 :])
    return metadata, body, diagnostics


def ordered_front_matter_keys(
    metadata: dict[str, str | list[str]], field_order: Sequence[str] | None
) -> list[str]:
    ordered: list[str] = []
    if field_order:
        ordered.extend(key for key in field_order if key in metadata)
    ordered.extend(sorted(key for key in metadata if key not in ordered))
    return ordered


def format_front_matter(
    metadata: dict[str, str | list[str]],
    body: str,
    field_order: Sequence[str] | None = None,
) -> str:
    lines = ["---"]
    for key in ordered_front_matter_keys(metadata, field_order):
        value = metadata[key]
        if isinstance(value, list):
            if value:
                lines.append(f"{key}:")
                lines.extend(f"  - {item}" for item in value)
            else:
                lines.append(f"{key}: []")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def required_field_missing(value: str | list[str] | None) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return not value
    return not value.strip()


def split_typed_scope(value: str) -> tuple[str | None, str | None]:
    if ":" not in value:
        return None, None
    scope_type, path = value.split(":", 1)
    return scope_type.strip(), path.strip()


def validate_scope_path(path_value: str, field_name: str) -> list[FrontMatterDiagnostic]:
    diagnostics: list[FrontMatterDiagnostic] = []
    normalized = path_value.replace("\\", "/")
    if normalized != path_value:
        diagnostics.append(
            FrontMatterDiagnostic(
                "front_matter_path_not_normalized",
                "scope path must use forward slashes",
                field=field_name,
            )
        )
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        diagnostics.append(
            FrontMatterDiagnostic(
                "front_matter_path_not_normalized",
                "scope path must be relative",
                field=field_name,
            )
        )
    if "//" in normalized:
        diagnostics.append(
            FrontMatterDiagnostic(
                "front_matter_path_not_normalized",
                "scope path contains duplicate separators",
                field=field_name,
            )
        )
    if (
        "*" not in normalized
        and normalized.startswith(MARKDOWN_LIKE_SCOPE_PREFIXES)
        and not normalized.endswith(".md")
    ):
        diagnostics.append(
            FrontMatterDiagnostic(
                "front_matter_path_missing_extension",
                "Markdown-like scope path must include .md extension",
                field=field_name,
            )
        )
    return diagnostics


def validate_front_matter(
    metadata: dict[str, str | list[str]],
    schema: FrontMatterSchema,
) -> list[FrontMatterDiagnostic]:
    diagnostics: list[FrontMatterDiagnostic] = []

    if schema.allowed_fields is not None:
        allowed = set(schema.allowed_fields)
        for key in metadata:
            if key not in allowed:
                diagnostics.append(
                    FrontMatterDiagnostic(
                        "front_matter_schema_failed",
                        f"field is not allowed: {key}",
                        field=key,
                    )
                )

    for field_name in schema.required_fields:
        if required_field_missing(metadata.get(field_name)):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"required field is missing or empty: {field_name}",
                    field=field_name,
                )
            )

    for field_name in schema.scalar_fields:
        if field_name in metadata and not isinstance(metadata[field_name], str):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"field must be a string: {field_name}",
                    field=field_name,
                )
            )

    for field_name in schema.list_fields:
        if field_name in metadata and not isinstance(metadata[field_name], list):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"field must be a list: {field_name}",
                    field=field_name,
                )
            )

    for field_name in schema.scope_fields:
        value = metadata.get(field_name)
        if value is None:
            continue
        if not isinstance(value, list):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"scope field must be a list: {field_name}",
                    field=field_name,
                )
            )
            continue
        for item in value:
            diagnostics.extend(validate_scope_path(item, field_name))

    for field_name, allowed_values in schema.enum_fields.items():
        value = metadata.get(field_name)
        if isinstance(value, str) and value not in allowed_values:
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"field has invalid value: {field_name}",
                    field=field_name,
                )
            )
        elif value is not None and not isinstance(value, str):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"enum field must be a string: {field_name}",
                    field=field_name,
                )
            )

    for field_name in schema.typed_scope_fields:
        value = metadata.get(field_name)
        if value is None:
            continue
        if not isinstance(value, list):
            diagnostics.append(
                FrontMatterDiagnostic(
                    "front_matter_schema_failed",
                    f"typed scope field must be a list: {field_name}",
                    field=field_name,
                )
            )
            continue
        for item in value:
            scope_type, scope_path = split_typed_scope(item)
            if not scope_type or not scope_path or scope_type not in schema.scope_types:
                diagnostics.append(
                    FrontMatterDiagnostic(
                        "front_matter_scope_invalid",
                        f"scope item must use TYPE: PATH with an allowed type: {item}",
                        field=field_name,
                    )
                )
                continue
            diagnostics.extend(validate_scope_path(scope_path, field_name))

    return diagnostics
