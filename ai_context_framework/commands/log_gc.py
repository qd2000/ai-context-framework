"""Cross-project garbage collection for orphaned user-level usage-log namespaces.

The command only removes runtime namespaces under ``ACF_HOME/projects`` that are
provably unreachable and carry no durable state:

- the recorded project root no longer exists;
- the namespace looks like a synthetic / smoke / temp namespace;
- there is no ``continuation/`` state and no other non-log state;
- the newest recorded event (or the directory mtime) is older than the
  retention window.

Anything that still resolves to a real project, or that carries continuation
state, is always kept. The command defaults to a dry run; deletion requires an
explicit ``--apply`` and writes a reviewable receipt.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_context_framework.commands.log_inventory import (
    event_context_match,
    is_synthetic_project_id,
    projects_root_from_log_root,
    read_jsonl_events,
)
from ai_context_framework.constants import (
    JSON_SCHEMA_VERSION,
    USAGE_LOCK_FILE_NAME,
    USAGE_LOG_CONFIG_NAME,
)
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.observability import atomic_write_text, parse_usage_timestamp


DEFAULT_RETENTION_DAYS = 30
LOG_ENTRY_NAME = "logs"
CONTINUATION_ENTRY_NAME = "continuation"
ALLOWED_LOG_ONLY_ENTRIES = {LOG_ENTRY_NAME, USAGE_LOG_CONFIG_NAME, USAGE_LOCK_FILE_NAME}
REAL_CONTEXT_CLASSIFICATIONS = {
    "resolved_context",
    "template_context",
    "archive_or_temp_context",
}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _latest_event_at(events: list[dict[str, object]]) -> str | None:
    for event in reversed(events):
        value = event.get("timestamp")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _directory_entries(directory: Path) -> list[str]:
    try:
        return sorted(entry.name for entry in directory.iterdir())
    except OSError:
        return []


def _continuation_entries(directory: Path) -> list[str]:
    continuation = directory / CONTINUATION_ENTRY_NAME
    if not continuation.is_dir():
        return []
    return _directory_entries(continuation)


def _non_log_state_entries(directory: Path) -> list[str]:
    return [
        name
        for name in _directory_entries(directory)
        if name not in ALLOWED_LOG_ONLY_ENTRIES and name != CONTINUATION_ENTRY_NAME
    ]


def evaluate_namespace(
    directory: Path,
    *,
    retention_days: int,
    now: datetime,
) -> dict[str, object]:
    """Return the GC verdict for one ACF_HOME project namespace."""
    project_id = directory.name
    log_path = directory / LOG_ENTRY_NAME / "usage.jsonl"
    events, _bad_lines = read_jsonl_events(log_path)
    context_match = event_context_match(events)
    classification = str(context_match.get("classification")) if context_match else None
    resolved_root = context_match.get("resolved_project_root") if context_match else None
    resolved_value = str(resolved_root) if resolved_root else None
    resolved_exists = bool(resolved_value) and Path(resolved_value).exists()
    synthetic = is_synthetic_project_id(project_id)
    recorded_root = bool(resolved_value)

    continuation_entries = _continuation_entries(directory)
    non_log_entries = _non_log_state_entries(directory)

    blockers: list[str] = []
    if resolved_exists:
        blockers.append("resolvable_real_project_root")
    if recorded_root and not synthetic:
        blockers.append("not_test_like_namespace")
    if not recorded_root and not synthetic:
        blockers.append("unknown_namespace_origin")
    if classification in REAL_CONTEXT_CLASSIFICATIONS:
        blockers.append("recorded_context_still_classified")
    if continuation_entries:
        blockers.append("has_continuation_state")
    if non_log_entries:
        blockers.append("has_non_log_state")

    last_event_at = _latest_event_at(events)
    parsed_event_at = _aware(parse_usage_timestamp(last_event_at)) if last_event_at else None
    try:
        fallback_at = datetime.fromtimestamp(directory.stat().st_mtime, tz=timezone.utc)
    except OSError:
        fallback_at = now
    reference_at = parsed_event_at or fallback_at
    expired = reference_at < now - timedelta(days=retention_days)
    if not expired:
        blockers.append("within_retention_window")

    reasons: list[str] = []
    if not resolved_exists:
        reasons.append("missing_project_root")
    if synthetic:
        reasons.append("test_like_namespace")
    if not continuation_entries:
        reasons.append("no_continuation_state")
    if not non_log_entries:
        reasons.append("log_only_state")
    if expired:
        reasons.append("expired_retention")

    return {
        "project_id": project_id,
        "path": str(directory),
        "log_path": str(log_path) if log_path.exists() else None,
        "event_count": len(events),
        "last_event_at": last_event_at,
        "retention_reference_at": reference_at.isoformat(),
        "classification": classification,
        "resolved_project_root": resolved_value,
        "synthetic_or_test_like": synthetic,
        "continuation_entries": continuation_entries,
        "non_log_state_entries": non_log_entries,
        "reasons": reasons,
        "blockers": blockers,
        "eligible": not blockers,
    }


def collect_gc_plan(
    *,
    log_root: Path | None,
    retention_days: int,
    now: datetime,
) -> dict[str, object]:
    projects_root = projects_root_from_log_root(log_root)
    candidates: list[dict[str, object]] = []
    kept: list[dict[str, object]] = []
    if projects_root.is_dir():
        for directory in sorted(path for path in projects_root.iterdir() if path.is_dir()):
            row = evaluate_namespace(directory, retention_days=retention_days, now=now)
            if row["eligible"]:
                candidates.append(row)
            else:
                kept.append(row)
    return {
        "projects_root": projects_root,
        "candidates": candidates,
        "kept": kept,
    }


def write_gc_receipt(projects_root: Path, payload: dict[str, object]) -> Path:
    receipt_dir = projects_root.parent / "gc-receipts"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt_path = receipt_dir / f"log-gc-{stamp}.json"
    body = {**payload, "receipt_path": None}
    atomic_write_text(
        receipt_path,
        json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return receipt_path


def log_gc_command(args: argparse.Namespace) -> int:
    retention_days = max(0, int(getattr(args, "retention_days", DEFAULT_RETENTION_DAYS) or 0))
    apply_changes = bool(getattr(args, "apply", False))
    now = datetime.now(timezone.utc)
    plan = collect_gc_plan(
        log_root=getattr(args, "log_root", None),
        retention_days=retention_days,
        now=now,
    )
    candidates = plan["candidates"]
    assert isinstance(candidates, list)
    kept = plan["kept"]
    assert isinstance(kept, list)

    removed_ids: list[str] = []
    if apply_changes:
        for row in candidates:
            shutil.rmtree(str(row["path"]))
            removed_ids.append(str(row["project_id"]))

    projects_root = plan["projects_root"]
    assert isinstance(projects_root, Path)
    payload: dict[str, object] = {
        "command": "log gc",
        "ok": True,
        "schema_version": JSON_SCHEMA_VERSION,
        "mode": "apply" if apply_changes else "dry_run",
        "acf_home": str(projects_root.parent),
        "projects_root": str(projects_root),
        "retention_days": retention_days,
        "generated_at": now.isoformat(),
        "candidate_count": len(candidates),
        "kept_count": len(kept),
        "removed_count": len(removed_ids),
        "removed_project_ids": removed_ids,
        "candidates": candidates,
        "kept": kept,
        "receipt_path": None,
        "next_actions": [
            "Review `candidates` and rerun with `--apply` to remove them."
            if not apply_changes
            else "Review the receipt and rerun `acf log projects --include-unresolved --json` to confirm the orphan namespaces are gone."
        ],
    }
    if apply_changes:
        payload["receipt_path"] = str(write_gc_receipt(projects_root, payload))

    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"mode: {payload['mode']}")
        print(f"candidates: {payload['candidate_count']}")
        print(f"kept: {payload['kept_count']}")
        print(f"removed: {payload['removed_count']}")
        if payload["receipt_path"]:
            print(f"receipt: {payload['receipt_path']}")
    return 0


def register_gc_parser(subparsers, add_json_argument) -> None:
    parser = subparsers.add_parser(
        "gc",
        help="report or remove orphaned user-level usage-log namespaces",
    )
    parser.add_argument("--log-root", type=Path, default=None, help="ACF home or projects directory to inspect")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help="only remove namespaces whose newest event is older than this many days",
    )
    parser.add_argument("--apply", action="store_true", help="actually remove eligible namespaces and write a receipt")
    parser.add_argument("--dry-run", action="store_true", help="explicitly request the default dry-run mode")
    add_json_argument(parser)
    parser.set_defaults(func=log_gc_command)
