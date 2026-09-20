"""Edit, linkify, and link command handlers."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_context_framework.json_contract import (
    dry_run_enabled,
    emit_write_result,
    json_enabled,
    print_json,
    set_result_payload,
)
from ai_context_framework.markdown import (
    append_section_text,
    find_section,
    linkify_markdown_text,
    markdown_heading_anchor_for,
    markdown_link_target_for,
    render_markdown_link,
    replace_section_text,
    section_body,
)
from ai_context_framework.models import CheckResult
from ai_context_framework.observability import atomic_write_text
from ai_context_framework.paths import is_relative_to, require_context_root
from ai_context_framework.tables import parse_cell_updates, upsert_table_row


LINKIFY_DEFAULT_DIRS = ("active", "reference", "rules", "decisions")
LINKIFY_DEFAULT_FILES = ("worklog/Worklog_Index.md", "archive/Archive_Index.md")
CheckAfter = Callable[[argparse.Namespace, Path], CheckResult | None]


def resolve_context_markdown_file(root: Path, target: Path) -> Path:
    root = root.resolve()
    if target.is_absolute():
        resolved = target.resolve()
    else:
        root_candidate = (root / target).resolve()
        if not is_relative_to(root_candidate, root):
            raise SystemExit(f"target file is outside context root: {target}")

        cwd_candidate = (Path.cwd() / target).resolve()
        if cwd_candidate.exists() and is_relative_to(cwd_candidate, root):
            resolved = cwd_candidate
        else:
            resolved = root_candidate

    if not is_relative_to(resolved, root):
        raise SystemExit(f"target file is outside context root: {target}")
    if resolved.suffix.lower() != ".md":
        raise SystemExit(f"target file must be Markdown (.md): {resolved}")
    if not resolved.exists():
        raise SystemExit(f"target file does not exist: {resolved}")
    if not resolved.is_file():
        raise SystemExit(f"target path is not a file: {resolved}")
    return resolved


def resolve_context_file(root: Path, target: Path, *, must_exist: bool = True) -> Path:
    root = root.resolve()
    if target.is_absolute():
        resolved = target.resolve()
    else:
        root_candidate = (root / target).resolve()
        if not is_relative_to(root_candidate, root):
            raise SystemExit(f"target file is outside context root: {target}")

        cwd_candidate = (Path.cwd() / target).resolve()
        if cwd_candidate.exists() and is_relative_to(cwd_candidate, root):
            resolved = cwd_candidate
        else:
            resolved = root_candidate

    if not is_relative_to(resolved, root):
        raise SystemExit(f"target file is outside context root: {target}")
    if must_exist and not resolved.exists():
        raise SystemExit(f"target file does not exist: {resolved}")
    if must_exist and not resolved.is_file():
        raise SystemExit(f"target path is not a file: {resolved}")
    return resolved


def read_edit_input(args: argparse.Namespace) -> str:
    text = getattr(args, "text", None)
    input_path = getattr(args, "input", None)
    if text is not None and input_path is not None:
        raise SystemExit("use either --text or --input, not both")
    if text is not None:
        return text
    if input_path is not None:
        resolved = input_path.resolve()
        if not resolved.is_file():
            raise SystemExit(f"edit input file does not exist: {resolved}")
        return resolved.read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("edit command requires --text, --input, or stdin")


def linkify_candidate_files(root: Path, args: argparse.Namespace) -> list[Path]:
    files: set[Path] = set()
    for dirname in LINKIFY_DEFAULT_DIRS:
        directory = root / dirname
        if directory.exists():
            files.update(path for path in directory.rglob("*.md") if path.is_file())
    for rel in LINKIFY_DEFAULT_FILES:
        file_path = root / rel
        if file_path.is_file():
            files.add(file_path)
    if getattr(args, "include_worklog_daily", False):
        daily = root / "worklog" / "daily"
        if daily.exists():
            files.update(path for path in daily.rglob("*.md") if path.is_file())
    if getattr(args, "include_archive", False):
        archive = root / "archive"
        if archive.exists():
            files.update(path for path in archive.rglob("*.md") if path.is_file())
    return sorted(files)


def linkify_command(args: argparse.Namespace, *, maybe_check_after: CheckAfter) -> int:
    if getattr(args, "format", "markdown") != "markdown":
        raise SystemExit("linkify currently supports only --format markdown")
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    changed_files: list[Path] = []
    updated_entries: list[dict[str, object]] = []
    skipped_entries: list[dict[str, str]] = []
    for md_file in linkify_candidate_files(root, args):
        original = md_file.read_text(encoding="utf-8")
        updated, replacements, skipped = linkify_markdown_text(
            root,
            md_file,
            original,
            allow_missing=bool(getattr(args, "allow_missing", False)),
        )
        rel_file = md_file.relative_to(root).as_posix()
        skipped_entries.extend({"file": rel_file, **entry} for entry in skipped)
        if updated == original:
            continue
        changed_files.append(md_file)
        updated_entries.append({"path": rel_file, "replacements": replacements})
        if not dry_run:
            atomic_write_text(md_file, updated)

    check_result = maybe_check_after(args, root)
    action = "would linkify" if dry_run else "linkified"
    return emit_write_result(
        args,
        "linkify",
        f"{action} {len(changed_files)} file(s)",
        changed_files,
        check_result,
        extra_payload={
            "format": args.format,
            "updated": updated_entries,
            "skipped": skipped_entries,
        },
    )


def link_add_command(args: argparse.Namespace, *, maybe_check_after: CheckAfter) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    target_file = resolve_context_markdown_file(root, args.file)
    link_target_file = resolve_context_file(root, args.target)
    target_fragment = ""
    if args.target_heading:
        if link_target_file.suffix.lower() != ".md":
            raise SystemExit("--target-heading requires a Markdown target file")
        anchor = markdown_heading_anchor_for(link_target_file.read_text(encoding="utf-8"), args.target_heading)
        if anchor is None:
            raise SystemExit(f"target heading was not found: {args.target_heading}")
        target_fragment = anchor
    link_href = markdown_link_target_for(target_file, link_target_file, target_fragment)
    context_target_display = link_target_file.relative_to(root).as_posix()
    default_text = f"{context_target_display}#{target_fragment}" if target_fragment else context_target_display
    link_text = args.text or default_text
    bullet = f"- {render_markdown_link(link_text, link_href)}"

    original = target_file.read_text(encoding="utf-8")
    original_lines = original.splitlines()
    body = section_body(original_lines, find_section(original_lines, args.heading))
    duplicate_markers = {f"]({link_href})", f"](<{link_href}>)"}
    if not args.force and any(marker in body for marker in duplicate_markers):
        raise SystemExit(f"link already exists in section: {link_href}")
    updated = append_section_text(original, args.heading, bullet)
    changed_files = [target_file] if updated != original else []
    if changed_files and not dry_run:
        atomic_write_text(target_file, updated)

    check_result = maybe_check_after(args, root)
    action = "would add" if dry_run else "added"
    return emit_write_result(
        args,
        "link add",
        f"{action} link to {target_file}",
        changed_files,
        check_result,
        extra_payload={
            "file": target_file.relative_to(root).as_posix(),
            "heading": args.heading,
            "link": bullet,
            "target": context_target_display,
            "target_heading": args.target_heading,
        },
    )


def edit_section_get_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.context)
    target = resolve_context_markdown_file(root, args.file)
    lines = target.read_text(encoding="utf-8").splitlines()
    section = find_section(lines, args.heading)
    body = section_body(lines, section)
    payload: dict[str, object] = {
        "command": "edit section get",
        "ok": True,
        "context": str(root),
        "file": str(target),
        "heading": args.heading,
        "body": body,
        "heading_line": section.heading_index + 1,
        "body_start_line": section.body_start + 1,
        "body_end_line": section.body_end,
    }
    set_result_payload(args, payload)

    if json_enabled(args):
        print_json(payload)
    else:
        print(body)
    return 0


def edit_section_replace_command(args: argparse.Namespace, *, maybe_check_after: CheckAfter) -> int:
    root = require_context_root(args.context)
    dry_run = dry_run_enabled(args)
    target = resolve_context_markdown_file(root, args.file)
    updated = replace_section_text(target.read_text(encoding="utf-8"), args.heading, read_edit_input(args))
    if not dry_run:
        target.write_text(updated, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would replace" if dry_run else "replaced"
    return emit_write_result(
        args,
        "edit section replace",
        f"{action} section {args.heading} in {target}",
        [target],
        check_result,
    )


def edit_section_append_command(args: argparse.Namespace, *, maybe_check_after: CheckAfter) -> int:
    root = require_context_root(args.context)
    dry_run = dry_run_enabled(args)
    target = resolve_context_markdown_file(root, args.file)
    updated = append_section_text(target.read_text(encoding="utf-8"), args.heading, read_edit_input(args))
    if not dry_run:
        target.write_text(updated, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would append" if dry_run else "appended"
    return emit_write_result(
        args,
        "edit section append",
        f"{action} to section {args.heading} in {target}",
        [target],
        check_result,
    )


def edit_table_upsert_command(args: argparse.Namespace, *, maybe_check_after: CheckAfter) -> int:
    root = require_context_root(args.context)
    dry_run = dry_run_enabled(args)
    target = resolve_context_markdown_file(root, args.file)
    updated = upsert_table_row(
        target.read_text(encoding="utf-8"),
        args.header,
        args.key_column,
        args.key,
        parse_cell_updates(args.cell),
    )
    if not dry_run:
        target.write_text(updated, encoding="utf-8")
    check_result = maybe_check_after(args, root)
    action = "would upsert" if dry_run else "upserted"
    return emit_write_result(
        args,
        "edit table upsert",
        f"{action} table row {args.key} in {target}",
        [target],
        check_result,
    )


def register_linkify_parser(
    subparsers: Any, add_write_arguments: Callable[..., None], handler: Callable[..., int]
) -> None:
    """Register the `linkify` parser (moved out of ``runtime.build_parser``)."""

    linkify_parser = subparsers.add_parser(
        "linkify",
        help="convert path references in context Markdown files to clickable Markdown links",
    )
    linkify_parser.add_argument("path", nargs="?", type=Path)
    linkify_parser.add_argument("--format", choices=("markdown",), default="markdown")
    linkify_parser.add_argument("--include-archive", action="store_true", help="also linkify archive detail files")
    linkify_parser.add_argument(
        "--include-worklog-daily",
        action="store_true",
        help="also linkify daily worklog files",
    )
    linkify_parser.add_argument("--allow-missing", action="store_true", help="linkify paths even when targets do not exist")
    add_write_arguments(linkify_parser)
    linkify_parser.set_defaults(func=handler)


def register_link_parser(
    subparsers: Any, add_write_arguments: Callable[..., None], handler: Callable[..., int]
) -> None:
    """Register the `link` group (moved out of ``runtime.build_parser``)."""

    link_parser = subparsers.add_parser("link", help="manage explicit Markdown links")
    link_subparsers = link_parser.add_subparsers(dest="link_command", required=True)

    link_add_parser = link_subparsers.add_parser("add", help="append a Markdown link bullet to a section")
    link_add_parser.add_argument("path", nargs="?", type=Path)
    link_add_parser.add_argument("file", type=Path, help="Markdown file inside the context root")
    link_add_parser.add_argument("--heading", required=True, help="exact section heading to append to")
    link_add_parser.add_argument("--target", type=Path, required=True, help="local target file inside the context root")
    link_add_parser.add_argument("--target-heading", default=None, help="target Markdown heading to link to")
    link_add_parser.add_argument("--text", default=None, help="link text; defaults to target path plus anchor")
    link_add_parser.add_argument("--force", action="store_true", help="allow duplicate links")
    add_write_arguments(link_add_parser)
    link_add_parser.set_defaults(func=handler)


def register_edit_parsers(
    subparsers: Any,
    add_json_argument: Callable[..., None],
    add_write_arguments: Callable[..., None],
    *,
    section_get_handler: Callable[..., int],
    section_replace_handler: Callable[..., int],
    section_append_handler: Callable[..., int],
    table_upsert_handler: Callable[..., int],
) -> None:
    """Register the `edit` group (moved out of ``runtime.build_parser``).

    Handlers are injected because the CLI binds the ``runtime_parts`` adapters that
    supply each handler's dependencies.
    """

    edit_parser = subparsers.add_parser("edit", help="safely edit context Markdown files")
    edit_subparsers = edit_parser.add_subparsers(dest="edit_target", required=True)

    section_parser = edit_subparsers.add_parser("section", help="get or update a Markdown section")
    section_subparsers = section_parser.add_subparsers(dest="section_command", required=True)

    section_get_parser = section_subparsers.add_parser("get", help="print a section body")
    section_get_parser.add_argument("file", type=Path, help="Markdown file inside the context root")
    section_get_parser.add_argument("--heading", required=True, help="exact Markdown heading, for example '## 当前阶段'")
    section_get_parser.add_argument("--context", type=Path, default=None, help="context root; omitted to auto-discover")
    add_json_argument(section_get_parser)
    section_get_parser.set_defaults(func=section_get_handler)

    section_replace_parser = section_subparsers.add_parser("replace", help="replace a section body")
    section_replace_parser.add_argument("file", type=Path, help="Markdown file inside the context root")
    section_replace_parser.add_argument("--heading", required=True, help="exact Markdown heading to replace")
    section_replace_parser.add_argument("--text", default=None, help="replacement text")
    section_replace_parser.add_argument("--input", type=Path, default=None, help="file containing replacement text")
    section_replace_parser.add_argument("--context", type=Path, default=None, help="context root; omitted to auto-discover")
    add_write_arguments(section_replace_parser)
    section_replace_parser.set_defaults(func=section_replace_handler)

    section_append_parser = section_subparsers.add_parser("append", help="append text to a section body")
    section_append_parser.add_argument("file", type=Path, help="Markdown file inside the context root")
    section_append_parser.add_argument("--heading", required=True, help="exact Markdown heading to append to")
    section_append_parser.add_argument("--text", default=None, help="text to append")
    section_append_parser.add_argument("--input", type=Path, default=None, help="file containing text to append")
    section_append_parser.add_argument("--context", type=Path, default=None, help="context root; omitted to auto-discover")
    add_write_arguments(section_append_parser)
    section_append_parser.set_defaults(func=section_append_handler)

    table_parser = edit_subparsers.add_parser("table", help="update Markdown tables")
    table_subparsers = table_parser.add_subparsers(dest="table_command", required=True)

    table_upsert_parser = table_subparsers.add_parser("upsert", help="insert or update a Markdown table row")
    table_upsert_parser.add_argument("file", type=Path, help="Markdown file inside the context root")
    table_upsert_parser.add_argument("--header", default=None, help="exact table header line; omitted to use first table")
    table_upsert_parser.add_argument("--key-column", required=True, help="column used as the row key")
    table_upsert_parser.add_argument("--key", required=True, help="key value to update or append")
    table_upsert_parser.add_argument("--cell", action="append", required=True, help="cell update as COLUMN=VALUE; can be repeated")
    table_upsert_parser.add_argument("--context", type=Path, default=None, help="context root; omitted to auto-discover")
    add_write_arguments(table_upsert_parser)
    table_upsert_parser.set_defaults(func=table_upsert_handler)
