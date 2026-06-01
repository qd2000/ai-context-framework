"""Template packaging validators."""

from __future__ import annotations

import re
from pathlib import Path

from ai_context_framework.templates import SOURCE_ROOT, TEMPLATE_DIR


def template_packaging_files_from_pyproject(pyproject_path: Path) -> set[str]:
    if not pyproject_path.exists():
        return set()
    text = pyproject_path.read_text(encoding="utf-8")
    return {
        match.replace("\\", "/").removeprefix("template/")
        for match in re.findall(r'"(template/[^"]+)"', text)
    }


def check_template_packaging(root: Path, errors: list[str]) -> None:
    pyproject_path = SOURCE_ROOT / "pyproject.toml"
    if root.resolve() != TEMPLATE_DIR.resolve() or not pyproject_path.exists():
        return

    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    packaged_files = template_packaging_files_from_pyproject(pyproject_path)
    missing = sorted(actual_files - packaged_files)
    extra = sorted(packaged_files - actual_files)

    for rel_path in missing:
        errors.append(f"pyproject.toml: missing template data-file entry for `{rel_path}`")
    for rel_path in extra:
        errors.append(f"pyproject.toml: stale template data-file entry for `{rel_path}`")
