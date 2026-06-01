"""Command handlers for context creation, simplification, and upgrade."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Callable, Sequence

from ai_context_framework.json_contract import dry_run_enabled, emit_write_result
from ai_context_framework.models import CheckResult
from ai_context_framework.paths import require_context_root
from ai_context_framework.templates import MINIMAL_DIRS, MINIMAL_FILES, TEMPLATE_DIR


MaybeCheckAfter = Callable[[argparse.Namespace, Path, str | None], CheckResult | None]


def init_command(
    args: argparse.Namespace,
    *,
    maybe_check_after: MaybeCheckAfter,
    ensure_clean_target: Callable[[Path, bool, bool], None],
    planned_init_files: Callable[[Path, str, bool], list[Path]],
    copy_selected_files: Callable[[Path, Path, Sequence[str], Sequence[str]], None],
    write_minimal_overrides: Callable[[Path], None],
    write_root_agents: Callable[[Path, bool], Path | None],
) -> int:
    target = args.target.resolve()
    dry_run = dry_run_enabled(args)
    ensure_clean_target(target, args.force, dry_run)
    changed_files = planned_init_files(target, args.profile, args.force_root_agent)
    if not dry_run:
        if args.profile == "standard":
            shutil.copytree(TEMPLATE_DIR, target, dirs_exist_ok=True)
        else:
            copy_selected_files(TEMPLATE_DIR, target, MINIMAL_FILES, MINIMAL_DIRS)
            write_minimal_overrides(target)
        write_root_agents(target, args.force_root_agent)
    check_result = maybe_check_after(args, target, args.profile)
    action = "would create" if dry_run else "created"
    return emit_write_result(
        args,
        "init",
        f"{action} {args.profile} context template at {target}",
        changed_files,
        check_result,
    )


def simplify_command(
    args: argparse.Namespace,
    *,
    maybe_check_after: MaybeCheckAfter,
    ensure_clean_target: Callable[[Path, bool, bool], None],
    planned_simplify_files: Callable[[Path, Path], list[Path]],
    copy_selected_files: Callable[[Path, Path, Sequence[str], Sequence[str]], None],
    copy_dynamic_minimal_files: Callable[[Path, Path], None],
    write_minimal_overrides: Callable[[Path], None],
) -> int:
    source = args.source.resolve()
    target = args.target.resolve()
    if not source.exists():
        raise SystemExit(f"source context does not exist: {source}")
    dry_run = dry_run_enabled(args)
    ensure_clean_target(target, args.force, dry_run)
    changed_files = planned_simplify_files(source, target)
    if not dry_run:
        copy_selected_files(source, target, MINIMAL_FILES, MINIMAL_DIRS)
        copy_dynamic_minimal_files(source, target)
        write_minimal_overrides(target)
    check_result = maybe_check_after(args, target, "minimal")
    action = "would create" if dry_run else "created"
    return emit_write_result(args, "simplify", f"{action} minimal context at {target}", changed_files, check_result)


def upgrade_command(
    args: argparse.Namespace,
    *,
    maybe_check_after: MaybeCheckAfter,
    ensure_upgrade_structure: Callable[[Path, bool], tuple[list[Path], list[str]]],
    upgrade_contract_payload: Callable[[Path, Sequence[Path]], dict[str, object]],
) -> int:
    root = require_context_root(args.path)
    dry_run = dry_run_enabled(args)
    changed_files, warnings = ensure_upgrade_structure(root, dry_run)
    check_result = maybe_check_after(args, root, None)
    action = "would upgrade" if dry_run else "upgraded"
    return emit_write_result(
        args,
        "upgrade",
        f"{action} context structure at {root}",
        changed_files,
        check_result,
        extra_payload=upgrade_contract_payload(root, changed_files),
        warnings=warnings,
    )
