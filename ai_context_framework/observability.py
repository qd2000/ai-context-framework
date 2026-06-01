"""Usage-log storage and filtering helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from ai_context_framework.constants import (
    ACF_HOME_ENV,
    JSON_SCHEMA_VERSION,
    USAGE_LOCK_FILE_NAME,
    USAGE_LOG_CONFIG_NAME,
    USAGE_LOG_FILE_REL,
)
from ai_context_framework.paths import slugify_project_name


def os_environ_value(name: str) -> str:
    return os.environ.get(name, "").strip()


def acf_home() -> Path:
    override = os_environ_value(ACF_HOME_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".acf").resolve()


def usage_project_dir(project_root: Path) -> Path:
    resolved = project_root.resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
    return acf_home() / "projects" / f"{slugify_project_name(resolved.name)}-{digest}"


def usage_config_path(project_root: Path) -> Path:
    return usage_project_dir(project_root) / USAGE_LOG_CONFIG_NAME


def usage_log_path(project_root: Path) -> Path:
    return usage_project_dir(project_root) / USAGE_LOG_FILE_REL


def usage_lock_path(project_root: Path) -> Path:
    return usage_project_dir(project_root) / USAGE_LOCK_FILE_NAME


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def acquire_usage_lock(project_root: Path, timeout_seconds: float = 5.0) -> Path:
    lock_path = usage_lock_path(project_root)
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
                raise SystemExit(f"usage log is locked: {lock_path}") from exc
            time.sleep(0.05)


def release_usage_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_usage_config(project_root: Path) -> dict[str, object]:
    config_path = usage_config_path(project_root)
    if not config_path.exists():
        return {"usage_log_enabled": True}
    try:
        data = json.loads(read_text(config_path))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False}
    return data if isinstance(data, dict) else {"enabled": False}


def write_usage_config(project_root: Path, enabled: bool) -> None:
    config_path = usage_config_path(project_root)
    lock_path = acquire_usage_lock(project_root)
    try:
        atomic_write_text(
            config_path,
            json.dumps(
                {
                    "schema_version": JSON_SCHEMA_VERSION,
                    "usage_log_enabled": enabled,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    finally:
        release_usage_lock(lock_path)


def usage_log_enabled(project_root: Path) -> bool:
    return bool(read_usage_config(project_root).get("usage_log_enabled", False))


def parse_usage_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_usage_events(project_root: Path) -> list[dict[str, object]]:
    log_path = usage_log_path(project_root)
    if not log_path.exists():
        return []
    events: list[dict[str, object]] = []
    for line in read_text(log_path).splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def write_usage_events(project_root: Path, events: Sequence[dict[str, object]]) -> None:
    log_path = usage_log_path(project_root)
    text = "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in events)
    lock_path = acquire_usage_lock(project_root)
    try:
        atomic_write_text(log_path, text)
    finally:
        release_usage_lock(lock_path)


def append_usage_event(project_root: Path, event: dict[str, object]) -> None:
    log_path = usage_log_path(project_root)
    lock_path = acquire_usage_lock(project_root)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    finally:
        release_usage_lock(lock_path)


def usage_log_status_payload(project_root: Path) -> dict[str, object]:
    events = read_usage_events(project_root)
    latest = events[-1].get("timestamp") if events else None
    return {
        "command": "log status",
        "ok": True,
        "enabled": usage_log_enabled(project_root),
        "project_root": str(project_root),
        "config_path": str(usage_config_path(project_root)),
        "log_path": str(usage_log_path(project_root)),
        "event_count": len(events),
        "latest_event_at": latest,
    }


def summarize_usage_events(events: Sequence[dict[str, object]]) -> dict[str, object]:
    command_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    event_kind_counts: dict[str, int] = {}
    dry_run_count = 0
    changed_files_count = 0
    ok_count = 0
    for event in events:
        command = str(event.get("command") or "unknown")
        command_counts[command] = command_counts.get(command, 0) + 1
        event_kind = str(event.get("event_kind") or "usage")
        event_kind_counts[event_kind] = event_kind_counts.get(event_kind, 0) + 1
        if event.get("ok") is True:
            ok_count += 1
        error_code = event.get("error_code")
        if error_code:
            key = str(error_code)
            error_counts[key] = error_counts.get(key, 0) + 1
        if event.get("dry_run") is True:
            dry_run_count += 1
        changed_files = event.get("changed_files")
        if isinstance(changed_files, list):
            changed_files_count += len(changed_files)
    return {
        "event_count": len(events),
        "ok_count": ok_count,
        "failed_count": len(events) - ok_count,
        "command_counts": command_counts,
        "error_counts": error_counts,
        "event_kind_counts": event_kind_counts,
        "feedback_count": event_kind_counts.get("feedback", 0),
        "dry_run_count": dry_run_count,
        "changed_files_count": changed_files_count,
    }


def parse_usage_since(value: str) -> datetime:
    normalized = value.strip()
    if not normalized:
        raise SystemExit("--since cannot be empty")
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", normalized):
            return datetime.fromisoformat(normalized).replace(tzinfo=timezone.utc)
        return parse_usage_timestamp(normalized) or datetime.fromisoformat(normalized).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise SystemExit(f"invalid --since value `{value}`, expected YYYY-MM-DD or ISO timestamp") from exc


def filter_usage_events(
    events: Sequence[dict[str, object]],
    since: datetime | None = None,
    commands: Sequence[str] = (),
    errors_only: bool = False,
) -> list[dict[str, object]]:
    command_set = {command.strip() for command in commands if command.strip()}
    filtered: list[dict[str, object]] = []
    for event in events:
        if since is not None:
            timestamp = parse_usage_timestamp(event.get("timestamp"))
            if timestamp is None or timestamp < since:
                continue
        if command_set and str(event.get("command") or "") not in command_set:
            continue
        if errors_only and event.get("ok") is True:
            continue
        filtered.append(event)
    return filtered
