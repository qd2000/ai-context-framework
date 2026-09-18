"""User-level issue lifecycle ledger for cross-project ACF dogfood issues.

Product issue lifecycle must not depend on an active continuation task. The
canonical occurrence stream stays in each project's usage log
(``continuation_issue`` events); durable dispositions live in one append-only
user-level ledger at ``ACF_HOME/issues/ledger.jsonl``.

Aggregation overlays the ledger on top of the usage-log occurrences, so the
existing fingerprint aggregation, the legacy ``continuation_issue_resolution``
events and every previously recorded status stay readable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

from ai_context_framework.constants import EXIT_INPUT_ERROR, JSON_SCHEMA_VERSION
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.observability import acf_home, utc_now_iso
from ai_context_framework.sensitive_data import sanitize_public_payload


LEDGER_REL = ("issues", "ledger.jsonl")
LEDGER_LOCK_REL = ("issues", "ledger.lock")
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{20}$")
STATUSES = ("open", "resolved", "superseded", "rejected")
ACTIONS = ("resolve", "supersede", "reject", "reopen")
ACTION_EVENT_KIND = {
    "resolve": "issue_resolution",
    "supersede": "issue_supersede",
    "reject": "issue_reject",
    "reopen": "issue_reopen",
}
ACTION_STATUS = {
    "resolve": "resolved",
    "supersede": "superseded",
    "reject": "rejected",
    "reopen": "open",
}


def _log_commands():
    # Lazy import avoids a module cycle: log.py imports the ledger helpers.
    from ai_context_framework.commands import log as log_commands

    return log_commands


def ledger_path() -> Path:
    return acf_home().joinpath(*LEDGER_REL)


def ledger_lock_path() -> Path:
    return acf_home().joinpath(*LEDGER_LOCK_REL)


def read_issue_ledger() -> list[dict[str, object]]:
    path = ledger_path()
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _acquire_ledger_lock(timeout_seconds: float = 5.0) -> Path:
    lock_path = ledger_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "schema_version": JSON_SCHEMA_VERSION,
                            "created_at": utc_now_iso(),
                            "pid": os.getpid(),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
            return lock_path
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise SystemExit(f"issue ledger is locked: {lock_path}") from exc
            time.sleep(0.05)


def _release_ledger_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return


def append_issue_ledger_event(event: dict[str, object]) -> Path:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _acquire_ledger_lock()
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    finally:
        _release_ledger_lock(lock_path)
    return path


def _ledger_only_group(fingerprint: str) -> dict[str, object]:
    return {
        "fingerprint": fingerprint,
        "category": None,
        "severity": "medium",
        "text": None,
        "count": 0,
        "first_seen": None,
        "last_seen": None,
        "tasks": [],
        "projects": [],
        "evidence_refs": [],
        "related_commands": [],
        "status": "open",
        "resolved_at": None,
        "resolution_text": None,
        "resolution_evidence_refs": [],
        "reopened_at": None,
        "ledger_only": True,
    }


def apply_issue_ledger(
    groups: list[dict[str, object]],
    ledger_events: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Overlay user-level ledger dispositions on aggregated issue groups."""
    by_fingerprint = {str(group.get("fingerprint") or ""): group for group in groups}
    ordered = sorted(ledger_events, key=lambda item: str(item.get("timestamp") or ""))
    for event in ordered:
        action = str(event.get("action") or "")
        if action not in ACTION_EVENT_KIND:
            continue
        fingerprint = str(event.get("fingerprint") or "").strip().lower()
        if not FINGERPRINT_RE.match(fingerprint):
            continue
        group = by_fingerprint.get(fingerprint)
        if group is None:
            group = _ledger_only_group(fingerprint)
            groups.append(group)
            by_fingerprint[fingerprint] = group
        timestamp = event.get("timestamp")
        evidence = [str(value) for value in (event.get("evidence_refs") or [])]
        group["status"] = ACTION_STATUS[action]
        group["resolution_source"] = "user_ledger"
        group["resolution_text"] = event.get("reason")
        group["resolution_evidence_refs"] = evidence
        group["superseded_by"] = event.get("superseded_by") if action == "supersede" else None
        if action == "reopen":
            group["reopened_at"] = timestamp
            group["resolved_at"] = None
            group["resolution_text"] = event.get("reason")
        else:
            group["resolved_at"] = timestamp
            group["reopened_at"] = None
        if isinstance(event.get("actor"), str) and event.get("actor"):
            group["resolution_actor"] = event.get("actor")
    return groups


def collect_issue_groups(
    path: Path | None,
    all_projects: bool,
) -> tuple[list[dict[str, object]], list[str], str | None]:
    log_commands = _log_commands()
    events, paths, project_root = log_commands._collect_issue_events(path, all_projects)
    groups = log_commands._continuation_issue_groups(events)
    apply_issue_ledger(groups, read_issue_ledger())
    return groups, paths, project_root


def _emit(args: argparse.Namespace, payload: dict[str, object], exit_code: int = 0) -> int:
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        if payload.get("ok"):
            print(str(payload.get("message") or payload.get("command") or "ok"))
        else:
            print(str(payload.get("message") or payload.get("error_code") or "issue command failed"))
    return exit_code


def _error(
    args: argparse.Namespace,
    command: str,
    error_code: str,
    message: str,
    next_actions: list[str],
) -> int:
    return _emit(
        args,
        {
            "schema_version": JSON_SCHEMA_VERSION,
            "command": command,
            "ok": False,
            "error_code": error_code,
            "message": message,
            "changed_files": [],
            "next_actions": next_actions,
        },
        EXIT_INPUT_ERROR,
    )


def normalize_fingerprint(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if FINGERPRINT_RE.match(normalized) else None


def log_issue_list_command(args: argparse.Namespace) -> int:
    status = str(getattr(args, "status", "") or "").strip().lower() or None
    if status is not None and status not in STATUSES:
        return _error(
            args,
            "log issue list",
            "issue_invalid_status",
            f"unsupported issue status: {status}",
            [f"Use one of: {', '.join(STATUSES)}."],
        )
    groups, paths, project_root = collect_issue_groups(
        getattr(args, "path", None),
        bool(getattr(args, "all_projects", False)),
    )
    if status is not None:
        groups = [group for group in groups if str(group.get("status")) == status]
    limit = max(0, int(getattr(args, "limit", 100) or 0))
    paged = groups[:limit] if limit else groups
    log_commands = _log_commands()
    public = sanitize_public_payload(paged)
    assert isinstance(public, list)
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "log issue list",
        "ok": True,
        "error_code": None,
        "project_root": project_root,
        "all_projects": bool(getattr(args, "all_projects", False)),
        "log_path_count": len(paths),
        "status_filter": status,
        "issue_count": len(groups),
        "returned_count": len(paged),
        "ledger_path": str(ledger_path()),
        "summary": log_commands._issue_summary(groups),
        "issues": public,
        "changed_files": [],
        "next_actions": [
            "Use `acf log issue show <fingerprint>` for a single issue.",
            "Use `acf log issue resolve|supersede|reject|reopen <fingerprint> --reason ...` to record a durable disposition.",
        ],
    }
    return _emit(args, payload)


def log_issue_show_command(args: argparse.Namespace) -> int:
    fingerprint = normalize_fingerprint(getattr(args, "fingerprint", ""))
    if fingerprint is None:
        return _error(
            args,
            "log issue show",
            "issue_invalid_fingerprint",
            "issue fingerprint must be 20 lowercase hex characters",
            ["Copy the exact `fingerprint` value from `acf log issues --json`."],
        )
    groups, _paths, _project_root = collect_issue_groups(
        getattr(args, "path", None),
        bool(getattr(args, "all_projects", False)),
    )
    match = next((group for group in groups if str(group.get("fingerprint")) == fingerprint), None)
    if match is None:
        return _error(
            args,
            "log issue show",
            "issue_not_found",
            f"no aggregated issue matches fingerprint {fingerprint}",
            ["Run `acf log issues --all-projects --json` to list known fingerprints."],
        )
    public = sanitize_public_payload(match)
    assert isinstance(public, dict)
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "log issue show",
        "ok": True,
        "error_code": None,
        "fingerprint": fingerprint,
        "ledger_path": str(ledger_path()),
        "issue": public,
        "changed_files": [],
        "next_actions": [],
    }
    return _emit(args, payload)


def _record_issue_action(args: argparse.Namespace, action: str) -> int:
    command = f"log issue {action}"
    fingerprint = normalize_fingerprint(getattr(args, "fingerprint", ""))
    if fingerprint is None:
        return _error(
            args,
            command,
            "issue_invalid_fingerprint",
            "issue fingerprint must be 20 lowercase hex characters",
            ["Copy the exact `fingerprint` value from `acf log issues --json`."],
        )
    reason = str(getattr(args, "reason", "") or "").strip()
    if not reason:
        return _error(args, command, "issue_reason_required", "--reason is required", ["Provide --reason."])
    superseded_by: str | None = None
    if action == "supersede":
        raw_by = str(getattr(args, "by", "") or "").strip()
        superseded_by = normalize_fingerprint(raw_by)
        if superseded_by is None:
            return _error(
                args,
                command,
                "issue_invalid_supersede_target",
                "--by must be the 20 hex fingerprint that replaces this issue",
                ["Use `acf log issue list --json` to pick the canonical fingerprint."],
            )
    evidence_refs = [
        str(value).strip()
        for value in (getattr(args, "evidence_ref", None) or [])
        if str(value).strip()
    ]
    dry_run = bool(getattr(args, "dry_run", False))
    event: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "timestamp": utc_now_iso(),
        "event_kind": ACTION_EVENT_KIND[action],
        "command": command,
        "action": action,
        "fingerprint": fingerprint,
        "superseded_by": superseded_by,
        "reason": reason,
        "evidence_refs": evidence_refs,
        "actor": str(getattr(args, "actor", "") or "user").strip() or "user",
    }
    path = ledger_path()
    if not dry_run:
        path = append_issue_ledger_event(event)
    payload: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": command,
        "ok": True,
        "error_code": None,
        "message": f"{action} recorded for {fingerprint}" if not dry_run else f"would record {action} for {fingerprint}",
        "action": action,
        "fingerprint": fingerprint,
        "status": ACTION_STATUS[action],
        "superseded_by": superseded_by,
        "dry_run": dry_run,
        "ledger_path": str(path),
        "event": event,
        "changed_files": [],
        "next_actions": [
            "Run `acf log issues --all-projects --open-only --json` to confirm the disposition."
        ],
    }
    return _emit(args, payload)


def _issue_action_command(action: str):
    def handler(args: argparse.Namespace) -> int:
        return _record_issue_action(args, action)

    return handler


def register_log_issue_parser(subparsers, add_json_argument) -> None:
    parser = subparsers.add_parser(
        "issue",
        help="maintain the user-level cross-project issue ledger",
    )
    issue_subparsers = parser.add_subparsers(dest="issue_command", required=True)

    list_parser = issue_subparsers.add_parser("list", help="list aggregated issues and their dispositions")
    list_parser.add_argument("path", nargs="?", type=Path)
    list_parser.add_argument("--all-projects", action="store_true")
    list_parser.add_argument("--status", choices=STATUSES, default=None)
    list_parser.add_argument("--limit", type=int, default=100)
    add_json_argument(list_parser)
    list_parser.set_defaults(func=log_issue_list_command)

    show_parser = issue_subparsers.add_parser("show", help="show one aggregated issue by fingerprint")
    show_parser.add_argument("fingerprint")
    show_parser.add_argument("path", nargs="?", type=Path)
    show_parser.add_argument("--all-projects", action="store_true")
    add_json_argument(show_parser)
    show_parser.set_defaults(func=log_issue_show_command)

    for action, help_text in (
        ("resolve", "record that an aggregated issue is fixed"),
        ("supersede", "record that an aggregated issue is replaced by another fingerprint"),
        ("reject", "record that an aggregated issue is not going to be fixed"),
        ("reopen", "reopen a previously closed aggregated issue"),
    ):
        action_parser = issue_subparsers.add_parser(action, help=help_text)
        action_parser.add_argument("fingerprint")
        action_parser.add_argument("--reason", required=True, help="durable reason recorded in the ledger")
        action_parser.add_argument("--evidence-ref", action="append", default=None, help="durable evidence reference; can be repeated")
        action_parser.add_argument("--actor", default="user", help="actor that authorizes this disposition")
        if action == "supersede":
            action_parser.add_argument("--by", required=False, default=None, help="replacement 20 hex fingerprint")
        action_parser.add_argument("--dry-run", action="store_true")
        add_json_argument(action_parser)
        action_parser.set_defaults(func=_issue_action_command(action))
