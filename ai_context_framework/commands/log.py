"""Usage log command handlers and event recording."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_context_framework.constants import JSON_SCHEMA_VERSION
from ai_context_framework.json_contract import (
    check_after_enabled,
    dry_run_enabled,
    get_result_payload,
    json_enabled,
    print_json,
)
from ai_context_framework.models import ContextLocation
from ai_context_framework.observability import (
    acf_home,
    append_usage_event,
    filter_usage_events,
    parse_usage_since,
    parse_usage_timestamp,
    read_usage_events,
    summarize_usage_events,
    usage_config_path,
    usage_log_enabled,
    usage_log_path,
    usage_log_status_payload,
    utc_now_iso,
    write_usage_config,
    write_usage_events,
)
from ai_context_framework.paths import (
    discover_context,
    make_context_location,
    relative_display_path,
    require_context_root,
    resolve_context_root,
    resolve_status_location,
)
from ai_context_framework.sensitive_data import contains_credential_like_text, sanitize_public_payload


def command_label(args: argparse.Namespace) -> str:
    command = getattr(args, "command", "") or ""
    if command == "new":
        return f"new {getattr(args, 'entry_type', '')}".strip()
    if command == "writeback":
        return f"writeback {getattr(args, 'writeback_command', '')}".strip()
    if command == "edit":
        edit_target = getattr(args, "edit_target", "")
        if edit_target == "section":
            return f"edit section {getattr(args, 'section_command', '')}".strip()
        if edit_target == "table":
            return f"edit table {getattr(args, 'table_command', '')}".strip()
    if command == "log":
        return f"log {getattr(args, 'log_command', '')}".strip()
    if command == "version":
        return f"version {getattr(args, 'version_command', '')}".strip()
    if command == "plan":
        plan_command = getattr(args, "plan_command", "")
        if plan_command == "stage":
            return f"plan stage {getattr(args, 'plan_stage_command', '')}".strip()
        return f"plan {plan_command}".strip()
    if command == "task":
        return f"task {getattr(args, 'task_command', '')}".strip()
    if command == "archive":
        return f"archive {getattr(args, 'archive_command', '')}".strip()
    if command == "decisions":
        return f"decisions {getattr(args, 'decisions_command', '')}".strip()
    if command == "knowledge":
        return f"knowledge {getattr(args, 'knowledge_command', '')}".strip()
    if command == "review":
        return f"review {getattr(args, 'review_command', '')}".strip()
    if command == "audit":
        return f"audit {getattr(args, 'audit_command', '')}".strip()
    if command == "curate":
        return f"curate {getattr(args, 'curate_command', '')}".strip()
    if command == "doctor":
        return "doctor"
    if command == "workstream":
        return f"workstream {getattr(args, 'workstream_command', '')}".strip()
    if command == "worktree":
        return f"worktree {getattr(args, 'worktree_command', '')}".strip()
    if command == "continuation":
        continuation_command = getattr(args, "continuation_command", "")
        if continuation_command == "owner":
            return f"continuation owner {getattr(args, 'continuation_owner_command', '')}".strip()
        return f"continuation {continuation_command}".strip()
    if command == "link":
        return f"link {getattr(args, 'link_command', '')}".strip()
    return command


def usage_loggable(args: argparse.Namespace) -> bool:
    if getattr(args, "command", None) == "upgrade" and bool(getattr(args, "plan", False)):
        return False
    return getattr(args, "command", None) != "log"


def context_location_for_args(args: argparse.Namespace) -> ContextLocation:
    command = getattr(args, "command", None)
    if command == "status":
        return resolve_status_location(getattr(args, "path", None))
    if command == "check":
        return make_context_location(resolve_context_root(getattr(args, "path", None)))
    if command == "init":
        return make_context_location(getattr(args, "target").resolve())
    if command == "simplify":
        return make_context_location(getattr(args, "target").resolve())
    if command == "upgrade":
        return make_context_location(require_context_root(getattr(args, "path", None)))
    if command == "linkify":
        return make_context_location(require_context_root(getattr(args, "path", None)))
    if command == "link":
        return make_context_location(require_context_root(getattr(args, "path", None)))
    if command == "new":
        return make_context_location(require_context_root(getattr(args, "path", None)))
    if command == "writeback":
        return make_context_location(require_context_root(getattr(args, "path", None)))
    if command == "edit":
        return make_context_location(require_context_root(getattr(args, "context", None)))
    if command in {"plan", "task", "archive", "decisions", "knowledge", "review", "audit", "doctor", "workstream"}:
        return make_context_location(require_context_root(getattr(args, "path", None)))
    if command in {"worktree", "continuation"}:
        start = Path(getattr(args, "path", None) or Path.cwd()).resolve()
        try:
            return discover_context(start)
        except SystemExit:
            completed = subprocess.run(
                ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if completed.returncode != 0 or not completed.stdout.strip():
                raise
            project_root = Path(completed.stdout.strip()).resolve()
            return ContextLocation(
                project_root=project_root,
                context_root=project_root,
                profile="git",
            )
    raise SystemExit("usage log is not available for this command")


def relative_usage_paths(values: object, project_root: Path) -> list[str]:
    if not isinstance(values, list):
        return []
    paths: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        paths.append(relative_display_path(Path(value).resolve(), project_root))
    return paths


def check_counts(payload: dict[str, object]) -> tuple[int, int]:
    check = payload.get("check")
    if not isinstance(check, dict):
        return 0, 0
    errors = check.get("errors")
    warnings = check.get("warnings")
    return (
        len(errors) if isinstance(errors, list) else 0,
        len(warnings) if isinstance(warnings, list) else 0,
    )


def build_usage_event(
    args: argparse.Namespace,
    location: ContextLocation,
    exit_code: int,
    duration_ms: int,
) -> dict[str, object]:
    payload = get_result_payload(args)
    error_count, warning_count = check_counts(payload)
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "timestamp": utc_now_iso(),
        "command": command_label(args),
        "project_root": str(location.project_root),
        "context_root": str(location.context_root),
        "cwd_rel": relative_display_path(Path.cwd().resolve(), location.project_root),
        "context_rel": relative_display_path(location.context_root, location.project_root),
        "profile": location.profile,
        "ok": bool(payload.get("ok", exit_code == 0)),
        "exit_code": exit_code,
        "error_code": payload.get("error_code"),
        "duration_ms": duration_ms,
        "dry_run": dry_run_enabled(args),
        "check_after": check_after_enabled(args),
        "strict": bool(getattr(args, "strict", False)),
        "json": json_enabled(args),
        "changed_files": relative_usage_paths(payload.get("changed_files"), location.project_root),
        "check_errors_count": error_count,
        "check_warnings_count": warning_count,
    }


def record_usage_event(args: argparse.Namespace, exit_code: int, duration_ms: int) -> None:
    if not usage_loggable(args):
        return
    try:
        location = context_location_for_args(args)
        if not usage_log_enabled(location.project_root):
            return
        append_usage_event(location.project_root, build_usage_event(args, location, exit_code, duration_ms))
    except BaseException:
        return


def log_enable_command(args: argparse.Namespace) -> int:
    location = resolve_status_location(args.path)
    write_usage_config(location.project_root, True)
    payload: dict[str, object] = {
        "command": "log enable",
        "ok": True,
        "enabled": True,
        "project_root": str(location.project_root),
        "config_path": str(usage_config_path(location.project_root)),
        "log_path": str(usage_log_path(location.project_root)),
    }
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"usage log enabled: {usage_log_path(location.project_root)}")
    return 0


def log_disable_command(args: argparse.Namespace) -> int:
    location = resolve_status_location(args.path)
    write_usage_config(location.project_root, False)
    payload: dict[str, object] = {
        "command": "log disable",
        "ok": True,
        "enabled": False,
        "project_root": str(location.project_root),
        "config_path": str(usage_config_path(location.project_root)),
        "log_path": str(usage_log_path(location.project_root)),
    }
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"usage log disabled: {usage_log_path(location.project_root)}")
    return 0


def log_status_command(args: argparse.Namespace) -> int:
    location = resolve_status_location(args.path)
    payload = usage_log_status_payload(location.project_root)
    if json_enabled(args):
        print_json(payload)
    else:
        state = "enabled" if payload["enabled"] else "disabled"
        print(f"usage log: {state}")
        print(f"project root: {payload['project_root']}")
        print(f"log path: {payload['log_path']}")
        print(f"events: {payload['event_count']}")
        if payload["latest_event_at"]:
            print(f"latest event: {payload['latest_event_at']}")
    return 0


def log_tail_command(args: argparse.Namespace) -> int:
    if args.limit < 0:
        raise SystemExit("log tail limit cannot be negative")
    location = resolve_status_location(args.path)
    events = read_usage_events(location.project_root)
    tail_events = events[-args.limit :] if args.limit else []
    public_tail_events = sanitize_public_payload(tail_events)
    assert isinstance(public_tail_events, list)
    payload: dict[str, object] = {
        "command": "log tail",
        "ok": True,
        "project_root": str(location.project_root),
        "log_path": str(usage_log_path(location.project_root)),
        "limit": args.limit,
        "event_count": len(tail_events),
        "events": public_tail_events,
    }
    if json_enabled(args):
        print_json(payload)
    else:
        for event in public_tail_events:
            print(json.dumps(event, ensure_ascii=False, sort_keys=True))
    return 0


def log_summarize_command(args: argparse.Namespace) -> int:
    if args.days is not None and args.days < 0:
        raise SystemExit("log summarize days cannot be negative")
    location = resolve_status_location(args.path)
    events = read_usage_events(location.project_root)
    since = parse_usage_since(args.since) if args.since else None
    if args.days is not None:
        days_since = datetime.now(timezone.utc) - timedelta(days=args.days)
        since = max(since, days_since) if since is not None else days_since
    filtered_events = filter_usage_events(events, since=since, commands=args.command_filter or (), errors_only=args.errors_only)
    payload: dict[str, object] = {
        "command": "log summarize",
        "ok": True,
        "project_root": str(location.project_root),
        "log_path": str(usage_log_path(location.project_root)),
        "filters": {
            "days": args.days,
            "since": args.since,
            "command": args.command_filter or [],
            "errors_only": args.errors_only,
        },
        "total_event_count": len(events),
        **summarize_usage_events(filtered_events),
    }
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"events: {payload['event_count']}")
        print(f"ok: {payload['ok_count']}")
        print(f"failed: {payload['failed_count']}")
        print(f"dry-run: {payload['dry_run_count']}")
        print(f"changed files: {payload['changed_files_count']}")
        print("commands:")
        for command, count in sorted(payload["command_counts"].items()):
            print(f"- {command}: {count}")
        if payload["error_counts"]:
            print("errors:")
            for error_code, count in sorted(payload["error_counts"].items()):
                print(f"- {error_code}: {count}")
    return 0


_ISSUE_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _continuation_issue_groups(events: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    for event in sorted(events, key=lambda item: str(item.get("timestamp") or "")):
        event_kind = event.get("event_kind")
        if event_kind == "continuation_issue_resolution":
            fingerprint = str(event.get("fingerprint") or "")
            current = groups.get(fingerprint)
            if current is not None:
                current["status"] = "resolved"
                current["resolved_at"] = event.get("timestamp")
                current["resolution_text"] = event.get("text")
                current["resolution_evidence_refs"] = list(event.get("evidence_refs") or [])
            continue
        if event_kind != "continuation_issue":
            continue
        fingerprint = str(event.get("fingerprint") or "")
        if not fingerprint:
            seed = "|".join(
                str(event.get(key) or "")
                for key in ("category", "related_command", "text")
            )
            fingerprint = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
        current = groups.get(fingerprint)
        severity = str(event.get("severity") or "medium")
        if current is None:
            current = {
                "fingerprint": fingerprint,
                "category": event.get("category"),
                "severity": severity,
                "text": event.get("text"),
                "count": 0,
                "first_seen": event.get("timestamp"),
                "last_seen": event.get("timestamp"),
                "tasks": [],
                "projects": [],
                "evidence_refs": [],
                "related_commands": [],
                "status": "open",
                "resolved_at": None,
                "resolution_text": None,
                "resolution_evidence_refs": [],
                "reopened_at": None,
            }
            groups[fingerprint] = current
        elif current.get("status") == "resolved":
            current["status"] = "open"
            current["reopened_at"] = event.get("timestamp")
            current["resolved_at"] = None
            current["resolution_text"] = None
            current["resolution_evidence_refs"] = []
        current["count"] = int(current["count"]) + 1
        current["last_seen"] = event.get("timestamp")
        if _ISSUE_SEVERITY_RANK.get(severity, 2) > _ISSUE_SEVERITY_RANK.get(
            str(current.get("severity") or "medium"), 2
        ):
            current["severity"] = severity
        for field, event_key in (
            ("tasks", "task_id"),
            ("projects", "project_root"),
            ("related_commands", "related_command"),
        ):
            value = event.get(event_key)
            if value and value not in current[field]:
                current[field].append(value)
        for value in event.get("evidence_refs") or []:
            if value not in current["evidence_refs"]:
                current["evidence_refs"].append(value)
    return sorted(
        groups.values(),
        key=lambda item: (
            _ISSUE_SEVERITY_RANK.get(str(item.get("severity") or "medium"), 2),
            str(item.get("last_seen") or ""),
        ),
        reverse=True,
    )


def log_issues_command(args: argparse.Namespace) -> int:
    events: list[dict[str, object]] = []
    paths: list[str] = []
    if bool(getattr(args, "all_projects", False)):
        projects_root = acf_home() / "projects"
        if projects_root.is_dir():
            for log_path in sorted(projects_root.glob("*/logs/usage.jsonl")):
                paths.append(str(log_path))
                try:
                    raw_events: list[dict[str, object]] = []
                    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
                        if not line.strip():
                            continue
                        try:
                            value = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(value, dict):
                            raw_events.append(value)
                except OSError:
                    continue
                events.extend(raw_events)
        project_root: str | None = None
    else:
        location = resolve_status_location(getattr(args, "path", None))
        project_root = str(location.project_root)
        paths.append(str(usage_log_path(location.project_root)))
        events = read_usage_events(location.project_root)
    groups = _continuation_issue_groups(events)
    if bool(getattr(args, "open_only", False)):
        groups = [group for group in groups if group.get("status") == "open"]
    limit = max(0, int(getattr(args, "limit", 100) or 0))
    if limit:
        groups = groups[:limit]
    public_groups = sanitize_public_payload(groups)
    assert isinstance(public_groups, list)
    payload: dict[str, object] = {
        "command": "log issues",
        "ok": True,
        "project_root": project_root,
        "all_projects": bool(getattr(args, "all_projects", False)),
        "log_paths": paths,
        "issue_count": len(groups),
        "occurrence_count": sum(int(group.get("count") or 0) for group in groups),
        "issues": public_groups,
    }
    if json_enabled(args):
        print_json(payload)
    else:
        for group in public_groups:
            print(
                f"[{group['severity']}] {group['fingerprint']} x{group['count']} "
                f"{group['category']}: {group['text']}"
            )
    return 0


def read_log_feedback_input(args: argparse.Namespace) -> str:
    if args.text and args.input:
        raise SystemExit("use either --text or --input, not both")
    if args.text:
        return args.text
    if args.input:
        input_path = args.input.resolve()
        if not input_path.is_file():
            raise SystemExit(f"log feedback input file does not exist: {input_path}")
        return input_path.read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("log feedback requires --text, --input, or stdin")


def log_feedback_command(args: argparse.Namespace) -> int:
    location = resolve_status_location(args.path)
    if not usage_log_enabled(location.project_root):
        raise SystemExit("usage log is disabled for this project")
    text = read_log_feedback_input(args).strip()
    if not text:
        raise SystemExit("log feedback text cannot be empty")
    feedback_type = (args.type or "Feedback").strip() or "Feedback"
    source = (args.source or "manual").strip() or "manual"
    related_command = (args.related_command or "").strip()
    for field, value in (
        ("text", text),
        ("type", feedback_type),
        ("source", source),
        ("related command", related_command),
    ):
        if value and contains_credential_like_text(value):
            raise SystemExit(f"log feedback {field} cannot contain credential-like material")
    event: dict[str, object] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "timestamp": utc_now_iso(),
        "event_kind": "feedback",
        "command": "log feedback",
        "cwd_rel": relative_display_path(Path.cwd().resolve(), location.project_root),
        "context_rel": relative_display_path(location.context_root, location.project_root),
        "profile": location.profile,
        "ok": True,
        "exit_code": 0,
        "error_code": None,
        "feedback_type": feedback_type,
        "source": source,
        "text": text,
    }
    if related_command:
        event["related_command"] = related_command
    append_usage_event(location.project_root, event)
    payload: dict[str, object] = {
        "command": "log feedback",
        "ok": True,
        "project_root": str(location.project_root),
        "log_path": str(usage_log_path(location.project_root)),
        "feedback_type": feedback_type,
        "source": source,
        "message": "recorded feedback event",
        "event": event,
    }
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"recorded feedback: {feedback_type}")
        print(f"log path: {payload['log_path']}")
    return 0


def log_prune_command(args: argparse.Namespace) -> int:
    if args.days < 0:
        raise SystemExit("log prune days cannot be negative")
    location = resolve_status_location(args.path)
    log_path = usage_log_path(location.project_root)
    events = read_usage_events(location.project_root)
    if args.days <= 0:
        kept_events: list[dict[str, object]] = []
    else:
        threshold = datetime.now(timezone.utc) - timedelta(days=args.days)
        kept_events = [
            event
            for event in events
            if (parse_usage_timestamp(event.get("timestamp")) or threshold) >= threshold
        ]
    removed_count = len(events) - len(kept_events)
    if events or log_path.exists():
        write_usage_events(location.project_root, kept_events)
    payload: dict[str, object] = {
        "command": "log prune",
        "ok": True,
        "project_root": str(location.project_root),
        "log_path": str(log_path),
        "days": args.days,
        "removed_count": removed_count,
        "kept_count": len(kept_events),
    }
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"removed events: {removed_count}")
        print(f"kept events: {len(kept_events)}")
    return 0
