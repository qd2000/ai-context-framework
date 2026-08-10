"""Retry, lock lease, and stale-lock handling for resilient Git operations."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from ai_context_framework.git_support import (
    atomic_write_json,
    load_operation,
    lock_path,
    read_json_object,
    safe_file_key,
)
from ai_context_framework.worktree_merge_contracts import MergeRetryPolicy, utc_now


LOCK_SCHEMA_VERSION = "acf.git_lock.v2"


@dataclass(frozen=True)
class LockLease:
    path: Path
    operation_id: str
    key: str


def retry_delay(policy: MergeRetryPolicy, attempt: int, *, seed: str = "") -> float:
    base = min(
        policy.max_delay_seconds,
        policy.initial_delay_seconds * (2 ** max(0, attempt)),
    )
    if policy.jitter_ratio == 0:
        return base
    digest = hashlib.sha256(f"{seed}:{attempt}".encode("utf-8")).digest()
    unit = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
    jitter = (unit * 2.0 - 1.0) * policy.jitter_ratio
    return max(0.0, base * (1.0 + jitter))


def acquire_lock_with_wait(
    common_dir: Path,
    *,
    key: str,
    operation_id: str,
    command: str,
    target_key: str,
    policy: MergeRetryPolicy,
    expected_primary_head: str | None = None,
    expected_source_head: str | None = None,
    timeout_seconds: float | None = None,
    stale_ttl_seconds: float = 120.0,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> tuple[LockLease, int]:
    timeout = (
        float(policy.lock_wait_timeout_seconds)
        if timeout_seconds is None
        else max(0.0, float(timeout_seconds))
    )
    path = lock_path(common_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    started = monotonic()
    attempt = 0
    while True:
        payload = _lock_payload(
            operation_id=operation_id,
            command=command,
            target_key=target_key,
            expected_primary_head=expected_primary_head,
            expected_source_head=expected_source_head,
            lease_seconds=max(stale_ttl_seconds, timeout + 30.0),
        )
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            descriptor = os.open(path, flags)
        except FileExistsError:
            if _quarantine_stale_lock(
                common_dir,
                path,
                stale_ttl_seconds=stale_ttl_seconds,
            ):
                continue
            elapsed = monotonic() - started
            if elapsed >= timeout:
                existing = read_json_object(path, error_code="worktree_lock_invalid")
                holder = existing.get("operation_id", "unknown")
                raise SystemExit(
                    f"worktree_operation_lock_timeout: {key} held by {holder}"
                )
            delay = min(retry_delay(policy, attempt, seed=operation_id), timeout - elapsed)
            attempt += 1
            sleep(delay)
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return LockLease(path=path, operation_id=operation_id, key=key), attempt


def refresh_lock(
    lease: LockLease,
    *,
    state: str | None = None,
    expected_primary_head: str | None = None,
    expected_source_head: str | None = None,
) -> None:
    if not lease.path.is_file():
        raise SystemExit(f"worktree_lock_lost: {lease.key}")
    payload = read_json_object(lease.path, error_code="worktree_lock_invalid")
    if payload.get("operation_id") != lease.operation_id:
        raise SystemExit(f"worktree_lock_replaced: {lease.key}")
    payload["heartbeat_at"] = utc_now()
    if state is not None:
        payload["state"] = state
    if expected_primary_head is not None:
        payload["expected_primary_head"] = expected_primary_head
    if expected_source_head is not None:
        payload["expected_source_head"] = expected_source_head
    atomic_write_json(lease.path, payload)


def release_owned_lock(lease: LockLease) -> bool:
    if not lease.path.is_file():
        return False
    payload = read_json_object(lease.path, error_code="worktree_lock_invalid")
    if payload.get("operation_id") != lease.operation_id:
        return False
    lease.path.unlink()
    return True


def _lock_payload(
    *,
    operation_id: str,
    command: str,
    target_key: str,
    expected_primary_head: str | None,
    expected_source_head: str | None,
    lease_seconds: float,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "schema_version": LOCK_SCHEMA_VERSION,
        "operation_id": operation_id,
        "pid": os.getpid(),
        "process_start_identity": _process_start_identity(os.getpid()),
        "hostname": socket.gethostname(),
        "command": command,
        "target_key": target_key,
        "created_at": now.isoformat(),
        "heartbeat_at": now.isoformat(),
        "lease_deadline_epoch": now.timestamp() + lease_seconds,
        "expected_primary_head": expected_primary_head,
        "expected_source_head": expected_source_head,
        "state": "held",
    }


def _quarantine_stale_lock(
    common_dir: Path,
    path: Path,
    *,
    stale_ttl_seconds: float,
) -> bool:
    try:
        payload = read_json_object(path, error_code="worktree_lock_invalid")
    except SystemExit:
        return False
    if payload.get("hostname") != socket.gethostname():
        return False
    pid = payload.get("pid")
    if not isinstance(pid, int) or _pid_alive(pid):
        return False
    heartbeat = _parse_timestamp(payload.get("heartbeat_at") or payload.get("created_at"))
    if heartbeat is None:
        return False
    age = datetime.now(timezone.utc).timestamp() - heartbeat
    if age < stale_ttl_seconds:
        return False
    operation_id = payload.get("operation_id")
    if isinstance(operation_id, str) and operation_id:
        try:
            operation = load_operation(common_dir, operation_id)
        except SystemExit:
            operation = None
        if isinstance(operation, Mapping):
            state = str(operation.get("state") or operation.get("status") or "")
            if state in {"PROMOTING", "promoting"}:
                return False
    stale_dir = common_dir / "acf" / "stale-locks"
    stale_dir.mkdir(parents=True, exist_ok=True)
    destination = stale_dir / (
        f"{safe_file_key(path.stem)}-{int(time.time())}-{safe_file_key(str(operation_id or 'unknown'))}.lock"
    )
    try:
        os.replace(path, destination)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _parse_timestamp(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        pid,
    )
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def _process_start_identity(pid: int) -> str | None:
    if pid != os.getpid():
        return None
    return f"{pid}:{int(time.time() - time.monotonic())}"
