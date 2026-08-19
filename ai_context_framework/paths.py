"""Context discovery and path presentation helpers."""

from __future__ import annotations

import re
from pathlib import Path

from ai_context_framework.models import ContextLocation
from ai_context_framework.templates import MINIMAL_FILES, STANDARD_FILES


def infer_context_profile(root: Path) -> str:
    standard_only_files = set(STANDARD_FILES) - set(MINIMAL_FILES)
    # `acf new rule` may add Rules_Index.md to an otherwise minimal context.
    # That single optional index should not opt the whole context into the
    # standard profile's required file set.
    standard_only_files.discard("rules/Rules_Index.md")
    if any((root / rel_path).exists() for rel_path in standard_only_files):
        return "standard"
    return "minimal"


def is_context_root(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "AGENTS.md").is_file()
        and (path / "active" / "Context.md").is_file()
        and (path / "rules" / "Always_Active.md").is_file()
    )


def infer_project_root(context_root: Path) -> Path:
    if context_root.name == "ai" and context_root.parent.name in {"docs", "docs-acf"}:
        return context_root.parent.parent
    if context_root.parent.name.lower() == "docs":
        return context_root.parent.parent
    return context_root.parent


def make_context_location(context_root: Path) -> ContextLocation:
    root = context_root.resolve()
    return ContextLocation(
        project_root=infer_project_root(root),
        context_root=root,
        profile=infer_context_profile(root),
    )


def discover_context(start: Path | None = None) -> ContextLocation:
    start_path = (start or Path.cwd()).resolve()
    current = start_path.parent if start_path.is_file() else start_path

    for directory in (current, *current.parents):
        if is_context_root(directory):
            return make_context_location(directory)

        docs_ai = directory / "docs" / "ai"
        if is_context_root(docs_ai):
            return make_context_location(docs_ai)
        docs_acf_ai = directory / "docs-acf" / "ai"
        if is_context_root(docs_acf_ai):
            return make_context_location(docs_acf_ai)

    raise SystemExit("could not find AI context directory; pass a context path or run `acf init docs/ai`")


def resolve_context_root(path: Path | None) -> Path:
    if path is not None:
        return path.resolve()
    return discover_context().context_root


def require_context_root(path: Path | None) -> Path:
    root = resolve_context_root(path)
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"context directory does not exist: {root}")
    return root


def resolve_status_location(path: Path | None) -> ContextLocation:
    if path is None:
        return discover_context()

    resolved = path.resolve()
    if is_context_root(resolved):
        return make_context_location(resolved)
    return discover_context(resolved)


def display_path(path: Path) -> str:
    return path.as_posix()


def relative_display_path(path: Path, base: Path) -> str:
    try:
        return display_path(path.relative_to(base))
    except ValueError:
        pass
    try:
        return display_path(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return display_path(path)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def context_json_path(root: Path, path: Path) -> str:
    return relative_display_path(path.resolve(), infer_project_root(root).resolve())


def slugify_project_name(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return slug or "project"
