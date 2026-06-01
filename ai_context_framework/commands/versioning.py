"""Version command handlers."""

from __future__ import annotations

import argparse
import importlib.metadata
import re
from pathlib import Path

from ai_context_framework.json_contract import (
    dry_run_enabled,
    emit_write_result,
    json_enabled,
    print_json,
)
from ai_context_framework.templates import SOURCE_ROOT
from ai_context_framework.version import VERSION


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalize_release_version(value: str) -> tuple[str, str]:
    raw = value.strip()
    if raw.startswith("v"):
        raw = raw[1:]
    if not re.fullmatch(r"\d+(?:\.\d+)+", raw):
        raise SystemExit(f"invalid version `{value}`, expected for example v0.0.3.6")
    return f"v{raw}", raw


def replace_regex_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"could not update {label}")
    return updated


def is_source_project_root(path: Path) -> bool:
    pyproject_path = path / "pyproject.toml"
    version_path = path / "ai_context_framework" / "version.py"
    if not pyproject_path.exists() or not version_path.exists():
        return False
    return 'name = "ai-context-framework"' in read_text(pyproject_path)


def discover_source_project_root(start: Path | None = None, *, source_root: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if start is not None:
        candidates.extend([start.resolve(), *start.resolve().parents])
    candidates.append(source_root or SOURCE_ROOT)
    for candidate in candidates:
        if is_source_project_root(candidate):
            return candidate
    return None


def require_source_project_root(*, source_root: Path | None = None) -> Path:
    root = discover_source_project_root(Path.cwd(), source_root=source_root)
    if root is None:
        raise SystemExit("version set requires an ai-context-framework source checkout")
    return root


def version_files(root: Path) -> list[Path]:
    files = [root / "ai_context_framework" / "version.py", root / "pyproject.toml"]
    pkg_info = root / "ai_context_framework.egg-info" / "PKG-INFO"
    uv_lock = root / "uv.lock"
    if pkg_info.exists():
        files.append(pkg_info)
    if uv_lock.exists():
        files.append(uv_lock)
    return files


def installed_package_version() -> str | None:
    try:
        return importlib.metadata.version("ai-context-framework")
    except importlib.metadata.PackageNotFoundError:
        return None


def read_project_versions(*, source_root: Path | None = None) -> dict[str, str | None]:
    versions: dict[str, str | None] = {
        "cli": VERSION,
        "pyproject": None,
        "pkg_info": None,
        "uv_lock": None,
    }
    checkout_root = discover_source_project_root(Path.cwd(), source_root=source_root)
    if checkout_root is None:
        versions["pkg_info"] = installed_package_version()
        return versions

    version_path = checkout_root / "ai_context_framework" / "version.py"
    pyproject_path = checkout_root / "pyproject.toml"
    pkg_info_path = checkout_root / "ai_context_framework.egg-info" / "PKG-INFO"
    uv_lock_path = checkout_root / "uv.lock"
    if version_path.exists():
        match = re.search(r'^VERSION = "([^"]+)"', read_text(version_path), flags=re.MULTILINE)
        if match:
            versions["cli"] = match.group(1)
    if pyproject_path.exists():
        match = re.search(r'^version = "([^"]+)"', read_text(pyproject_path), flags=re.MULTILINE)
        if match:
            versions["pyproject"] = match.group(1)
    if pkg_info_path.exists():
        match = re.search(r"^Version: (.+)$", read_text(pkg_info_path), flags=re.MULTILINE)
        if match:
            versions["pkg_info"] = match.group(1).strip()
    else:
        versions["pkg_info"] = installed_package_version()
    if uv_lock_path.exists():
        match = re.search(r'(?ms)name = "ai-context-framework".*?^version = "([^"]+)"', read_text(uv_lock_path))
        if match:
            versions["uv_lock"] = match.group(1)
    return versions


def version_show_command(args: argparse.Namespace, *, source_root: Path | None = None) -> int:
    versions = read_project_versions(source_root=source_root)
    payload: dict[str, object] = {
        "command": "version show",
        "ok": True,
        "version": versions.get("cli"),
        "versions": versions,
        "error_code": None,
        "next_actions": [],
    }
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"version: {versions.get('cli')}")
        for key, value in versions.items():
            print(f"{key}: {value}")
    return 0


def version_set_command(args: argparse.Namespace, *, source_root: Path | None = None) -> int:
    dry_run = dry_run_enabled(args)
    cli_version, package_version = normalize_release_version(args.value)
    root = require_source_project_root(source_root=source_root)
    changed = version_files(root)
    if not dry_run:
        version_path = root / "ai_context_framework" / "version.py"
        pyproject_path = root / "pyproject.toml"
        version_path.write_text(
            replace_regex_once(
                read_text(version_path),
                r'^VERSION = "[^"]+"',
                f'VERSION = "{cli_version}"',
                "version.py VERSION",
            ),
            encoding="utf-8",
        )
        pyproject_path.write_text(
            replace_regex_once(
                read_text(pyproject_path),
                r'^version = "[^"]+"',
                f'version = "{package_version}"',
                "pyproject.toml version",
            ),
            encoding="utf-8",
        )
        pkg_info_path = root / "ai_context_framework.egg-info" / "PKG-INFO"
        if pkg_info_path.exists():
            pkg_info_path.write_text(
                replace_regex_once(read_text(pkg_info_path), r"^Version: .+$", f"Version: {package_version}", "PKG-INFO version"),
                encoding="utf-8",
            )
        uv_lock_path = root / "uv.lock"
        if uv_lock_path.exists():
            uv_lock_path.write_text(
                replace_regex_once(
                    read_text(uv_lock_path),
                    r'(?ms)(name = "ai-context-framework".*?^version = ")[^"]+(")',
                    rf"\g<1>{package_version}\2",
                    "uv.lock version",
                ),
                encoding="utf-8",
            )
    action = "would set" if dry_run else "set"
    return emit_write_result(
        args,
        "version set",
        f"{action} version to {cli_version}",
        changed,
        extra_payload={"version": cli_version, "package_version": package_version},
    )
