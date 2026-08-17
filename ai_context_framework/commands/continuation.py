"""Model-agnostic bounded continuation control for long-running AI work.

The continuation controller is deliberately not an agent runtime or scheduler.
It stores a compact, user-local recovery state for one Git worktree and exposes
deterministic claim/renew/checkpoint/release primitives that external agents or
schedulers can call.  Authoritative plans and evidence remain in the project.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

try:  # Windows production path.
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows fallback.
    msvcrt = None  # type: ignore[assignment]

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows path.
    fcntl = None  # type: ignore[assignment]

from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.observability import (
    append_usage_event,
    atomic_write_text,
    usage_log_enabled,
    usage_log_path,
    usage_project_dir,
    utc_now_iso,
)
from ai_context_framework.worktree_service import target_from_registry, verify_target
from ai_context_framework.git_support import discover_git_project


CONTROL_SCHEMA = "acf.continuation.control.v1"
STATE_SCHEMA = "acf.continuation.state.v1"
LEASE_SCHEMA = "acf.continuation.lease.v1"
PAUSE_SCHEMA = "acf.continuation.pause.v1"
RECEIPT_SCHEMA = "acf.continuation.receipt.v1"

DEFAULT_INTERVAL_MINUTES = 60
DEFAULT_LEASE_TTL_MINUTES = 120
DEFAULT_RENEW_INTERVAL_MINUTES = 30
MAX_LEASE_TTL_MINUTES = 24 * 60
MAX_STATE_BYTES = 64 * 1024
MAX_LIST_ITEMS = 64
MAX_TEXT_BYTES = 4096

RUNNABLE_STATUSES = frozenset({"ready", "waiting_external"})
STATE_STATUSES = frozenset(
    {
        "ready",
        "running",
        "waiting_external",
        "reconciling",
        "blocked_human",
        "paused",
        "done",
    }
)
FORBIDDEN_STATE_KEYS = frozenset(
    {
        "events",
        "full_history",
        "full_transcript",
        "history",
        "raw_output",
        "rollout",
        "snapshots",
        "stderr",
        "stdout",
        "tool_output",
        "tool_outputs",
        "transcript",
        "transcripts",
    }
)
LIST_FIELDS = (
    "completed",
    "constraints",
    "evidence_refs",
    "open_questions",
    "plan_refs",
    "verification",
)


class ContinuationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "continuation_error",
        exit_code: int = 2,
        details: Mapping[str, Any] | None = None,
        next_actions: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.details = dict(details or {})
        self.next_actions = list(next_actions)


class ContinuationBusy(ContinuationError):
    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="continuation_busy",
            exit_code=3,
            details=details,
            next_actions=["Do not start another round; retry after the active lease is released."],
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _parse_iso(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ContinuationError(f"{field} must be a non-empty timestamp", code="state_invalid")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ContinuationError(f"{field} is not a valid timestamp", code="state_invalid") from exc
    if parsed.tzinfo is None:
        raise ContinuationError(f"{field} must include a timezone", code="state_invalid")
    return parsed.astimezone(timezone.utc)


def _safe_key(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    if not normalized:
        raise ContinuationError("task_id cannot render to an empty state key", code="task_id_invalid")
    return normalized[:120]


def _run_git(location: Path, *args: str, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(location), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise ContinuationError("git is unavailable", code="git_unavailable") from exc
    if completed.returncode != 0 and not allow_failure:
        raise ContinuationError(
            f"git command failed: {' '.join(args)}",
            code="git_command_failed",
            details={"stderr": completed.stderr[-2000:]},
        )
    return completed


def _workspace_root(path: str | Path | None) -> Path:
    location = Path(path or Path.cwd()).expanduser().resolve()
    if not location.exists():
        raise ContinuationError(f"path does not exist: {location}", code="workspace_missing")
    completed = _run_git(location, "rev-parse", "--show-toplevel")
    root = Path(completed.stdout.strip()).resolve()
    if not root.is_dir():
        raise ContinuationError("Git top-level is not a directory", code="workspace_invalid")
    return root


def _git_identity(root: Path) -> dict[str, Any]:
    branch = _run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD", allow_failure=True)
    head = _run_git(root, "rev-parse", "HEAD")
    status = _run_git(root, "status", "--porcelain=v1", "--untracked-files=all")
    dirty = [line for line in status.stdout.splitlines() if line.strip()]
    return {
        "workspace_root": str(root),
        "branch": branch.stdout.strip() if branch.returncode == 0 else None,
        "detached": branch.returncode != 0,
        "head": head.stdout.strip(),
        "clean": not dirty,
        "dirty_entries": dirty[:128],
    }


def _task_parent(root: Path) -> Path:
    return usage_project_dir(root) / "continuation"


def _task_dir(root: Path, task_id: str | None) -> Path:
    parent = _task_parent(root)
    if task_id:
        return parent / _safe_key(task_id)
    candidates = sorted(
        path for path in parent.iterdir() if path.is_dir() and (path / "control.json").is_file()
    ) if parent.is_dir() else []
    if not candidates:
        raise ContinuationError(
            "no continuation task is configured for this worktree",
            code="continuation_not_initialized",
            next_actions=["Run `acf continuation init ...` first."],
        )
    if len(candidates) > 1:
        raise ContinuationError(
            "multiple continuation tasks exist; pass --task-id",
            code="continuation_task_ambiguous",
            details={"tasks": [path.name for path in candidates]},
        )
    return candidates[0]


def _paths(root: Path, task_id: str | None) -> dict[str, Path]:
    directory = _task_dir(root, task_id)
    return {
        "directory": directory,
        "lock": directory / "state.lock",
        "control": directory / "control.json",
        "state": directory / "state.json",
        "lease": directory / "lease.json",
        "pause": directory / "pause.json",
        "receipt": directory / "last_run.json",
    }


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContinuationError(f"{label} is missing", code=f"{label}_missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ContinuationError(f"{label} is unreadable", code=f"{label}_invalid") from exc
    if not isinstance(value, dict):
        raise ContinuationError(f"{label} must be a JSON object", code=f"{label}_invalid")
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )


@contextmanager
def _state_lock(lock_path: Path, *, timeout_seconds: float = 10.0) -> Iterator[None]:
    deadline = time.monotonic() + timeout_seconds
    try:
        stream = lock_path.open("r+b")
    except FileNotFoundError as exc:
        raise ContinuationError("continuation state lock is missing", code="control_missing") from exc
    with stream:
        while True:
            try:
                stream.seek(0)
                if msvcrt is not None:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                elif fcntl is not None:  # pragma: no cover - POSIX fallback.
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:  # pragma: no cover - unsupported platform.
                    raise ContinuationError("OS file locking is unavailable", code="lock_unavailable")
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise ContinuationBusy("continuation state transition is already in progress") from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            if msvcrt is not None:
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            elif fcntl is not None:  # pragma: no cover - POSIX fallback.
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _validate_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContinuationError(f"{field} must be a non-empty string", code="state_invalid")
    if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ContinuationError(f"{field} exceeds {MAX_TEXT_BYTES} bytes", code="state_invalid")
    return value.strip()


def _reject_forbidden_state_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_STATE_KEYS:
                raise ContinuationError(
                    f"forbidden raw-history field: {path}.{key}",
                    code="state_invalid",
                )
            _reject_forbidden_state_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_state_keys(child, path=f"{path}[{index}]")


def _validate_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    state = dict(payload)
    required = {"schema_version", "task_id", "objective", "status", "stage", "next_action", "updated_at"}
    missing = sorted(required - set(state))
    if missing or state.get("schema_version") != STATE_SCHEMA:
        raise ContinuationError(f"state schema is invalid; missing={missing}", code="state_invalid")
    _reject_forbidden_state_keys(state)
    for field in ("task_id", "objective", "stage", "next_action", "updated_at"):
        _validate_text(state.get(field), field=field)
    if state.get("status") not in STATE_STATUSES:
        raise ContinuationError(f"unsupported state status: {state.get('status')}", code="state_invalid")
    _parse_iso(state["updated_at"], field="updated_at")
    allowed = required | set(LIST_FIELDS)
    unknown = sorted(set(state) - allowed)
    if unknown:
        raise ContinuationError(f"unsupported state fields: {', '.join(unknown)}", code="state_invalid")
    for field in LIST_FIELDS:
        values = state.get(field, [])
        if not isinstance(values, list) or len(values) > MAX_LIST_ITEMS:
            raise ContinuationError(f"{field} must be a bounded list", code="state_invalid")
        for item in values:
            encoded = json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")
            if len(encoded) > MAX_TEXT_BYTES:
                raise ContinuationError(f"{field} item is too large", code="state_invalid")
    encoded = json.dumps(state, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_STATE_BYTES:
        raise ContinuationError("state exceeds bounded continuation limit", code="state_invalid")
    return state


def _write_state(path: Path, payload: Mapping[str, Any]) -> None:
    _write_json(path, _validate_state(payload))


def _load_control(paths: Mapping[str, Path], root: Path) -> dict[str, Any]:
    control = _read_json(paths["control"], label="control")
    if control.get("schema_version") != CONTROL_SCHEMA:
        raise ContinuationError("control schema mismatch", code="control_invalid")
    if Path(str(control.get("workspace_root") or "")).resolve() != root:
        raise ContinuationError("configured worktree does not match current Git root", code="workspace_mismatch")
    for field in (
        "task_id",
        "title",
        "objective",
        "workspace_root",
        "expected_branch",
        "created_at",
        "updated_at",
    ):
        _validate_text(control.get(field), field=field)
    for field in ("interval_minutes", "lease_ttl_minutes", "renew_interval_minutes"):
        value = control.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ContinuationError(f"invalid control field: {field}", code="control_invalid")
    if control["lease_ttl_minutes"] > MAX_LEASE_TTL_MINUTES:
        raise ContinuationError("lease TTL exceeds safety maximum", code="control_invalid")
    if control["renew_interval_minutes"] >= control["lease_ttl_minutes"]:
        raise ContinuationError("renew interval must be shorter than lease TTL", code="control_invalid")
    if control.get("history_policy") != "local_first":
        raise ContinuationError("continuation history_policy must be local_first", code="control_invalid")
    return control


def _load_state(paths: Mapping[str, Path]) -> dict[str, Any]:
    return _validate_state(_read_json(paths["state"], label="state"))


def _lease_snapshot(paths: Mapping[str, Path], control: Mapping[str, Any]) -> dict[str, Any]:
    path = paths["lease"]
    if not path.exists():
        return {"state": "absent", "path": str(path)}
    try:
        lease = _read_json(path, label="lease")
        required = {
            "schema_version",
            "lease_id",
            "runner_id",
            "task_id",
            "workspace_root",
            "branch",
            "head",
            "issued_at",
            "expires_at",
        }
        if lease.get("schema_version") != LEASE_SCHEMA or required - set(lease):
            raise ContinuationError("lease schema is invalid", code="lease_invalid")
        if lease.get("task_id") != control.get("task_id"):
            raise ContinuationError("lease task identity mismatch", code="lease_invalid")
        if Path(str(lease.get("workspace_root"))).resolve() != Path(str(control["workspace_root"])).resolve():
            raise ContinuationError("lease workspace identity mismatch", code="lease_invalid")
        if lease.get("branch") != control.get("expected_branch"):
            raise ContinuationError("lease branch identity mismatch", code="lease_invalid")
        issued = _parse_iso(lease.get("issued_at"), field="issued_at")
        expires = _parse_iso(lease.get("expires_at"), field="expires_at")
        if expires <= issued:
            raise ContinuationError("lease expiry must be after issue time", code="lease_invalid")
    except ContinuationError as exc:
        return {"state": "invalid", "path": str(path), "error": str(exc)}
    return {
        "state": "active" if expires > _now() else "expired",
        "path": str(path),
        "lease": lease,
    }


def _workstream_verification(root: Path, workstream_id: str | None) -> dict[str, Any]:
    if not workstream_id:
        return {"required": False, "ok": True, "status": "not_required"}
    try:
        project = discover_git_project(root)
        target = target_from_registry(project, workstream_id=workstream_id, target_path=None)
        result = verify_target(project, target)
    except SystemExit as exc:
        return {"required": True, "ok": False, "status": "invalid", "message": str(exc)}
    result = dict(result)
    result.update({"required": True, "status": "verified" if result.get("ok") else "invalid"})
    return result


def _status(root: Path, task_id: str | None) -> dict[str, Any]:
    paths = _paths(root, task_id)
    control = _load_control(paths, root)
    state = _load_state(paths)
    git = _git_identity(root)
    identity_errors: list[str] = []
    if git["detached"]:
        identity_errors.append("Git HEAD is detached")
    if git["branch"] != control["expected_branch"]:
        identity_errors.append(
            f"branch mismatch: expected {control['expected_branch']}, got {git['branch']}"
        )
    if state["task_id"] != control["task_id"]:
        identity_errors.append("state task_id does not match control task_id")
    workstream = _workstream_verification(root, control.get("workstream_id"))
    if not workstream.get("ok"):
        identity_errors.append("ACF worktree verification failed")
    lease = _lease_snapshot(paths, control)
    if lease["state"] == "invalid":
        identity_errors.append("lease is malformed or identity-mismatched")
    pause = _read_json(paths["pause"], label="pause") if paths["pause"].exists() else None
    expired_running_round = state["status"] == "running" and lease["state"] == "expired"
    expired_round_head_changed = bool(
        expired_running_round
        and isinstance(lease.get("lease"), Mapping)
        and lease["lease"].get("head") != git["head"]
    )
    recoverable_expired = expired_running_round and not expired_round_head_changed
    can_claim = (
        not identity_errors
        and git["clean"]
        and pause is None
        and lease["state"] in {"absent", "expired"}
        and (state["status"] in RUNNABLE_STATUSES or recoverable_expired)
    )
    blocked: list[str] = list(identity_errors)
    if not git["clean"]:
        blocked.append("worktree_dirty")
    if pause is not None:
        blocked.append("paused")
    if lease["state"] == "active":
        blocked.append("active_lease")
    if expired_round_head_changed:
        blocked.append("expired_round_head_changed")
    if state["status"] not in RUNNABLE_STATUSES and not recoverable_expired:
        blocked.append(f"state_status:{state['status']}")
    return {
        "ok": not identity_errors,
        "can_claim": can_claim,
        "blocked_reasons": blocked,
        "control": control,
        "state": state,
        "git": git,
        "lease": lease,
        "pause": pause,
        "workstream": workstream,
        "state_dir": str(paths["directory"]),
        "recoverable_expired_round": recoverable_expired,
        "expired_round_head_changed": expired_round_head_changed,
    }


def _append_unique(existing: Iterable[Any], additions: Iterable[Any]) -> list[Any]:
    result = list(existing)
    for value in additions:
        if value not in result:
            result.append(value)
    return result


def _emit(args: argparse.Namespace, command: str, payload: Mapping[str, Any], exit_code: int = 0) -> int:
    result = {
        "schema_version": 1,
        "command": command,
        "ok": exit_code == 0 and bool(payload.get("ok", True)),
        "error_code": None,
        "next_actions": [],
        **dict(payload),
    }
    set_result_payload(args, result)
    if json_enabled(args):
        print_json(result)
    else:
        print(result.get("status") or ("ok" if result["ok"] else "error"))
        if result.get("message"):
            print(result["message"])
        if result.get("next_action"):
            print(f"next_action: {result['next_action']}")
    return exit_code


def _emit_error(args: argparse.Namespace, command: str, exc: ContinuationError) -> int:
    return _emit(
        args,
        command,
        {
            "ok": False,
            "error_code": exc.code,
            "message": str(exc),
            "details": exc.details,
            "next_actions": exc.next_actions or ["Inspect continuation status before retrying."],
        },
        exc.exit_code,
    )


def _guarded(args: argparse.Namespace, command: str, operation) -> int:
    try:
        result = operation()
        return _emit(
            args,
            command,
            result,
            exit_code=0 if bool(result.get("ok", True)) else 2,
        )
    except ContinuationError as exc:
        return _emit_error(args, command, exc)


def continuation_init_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        task_id = str(args.task_id or args.workstream or "").strip()
        if not task_id:
            raise ContinuationError("--task-id or --workstream is required", code="task_id_required")
        git = _git_identity(root)
        if git["detached"] or not git["branch"]:
            raise ContinuationError("continuation init refuses detached HEAD", code="detached_head")
        if not git["clean"]:
            raise ContinuationError(
                "continuation init requires a clean worktree checkpoint",
                code="worktree_dirty",
                details={"dirty_entries": git["dirty_entries"]},
                next_actions=["Commit or otherwise reconcile the current worktree before enabling automation."],
            )
        expected_branch = str(args.expected_branch or git["branch"])
        if expected_branch != git["branch"]:
            raise ContinuationError("current branch does not match --expected-branch", code="branch_mismatch")
        workstream = _workstream_verification(root, args.workstream)
        if args.workstream and not workstream.get("ok"):
            raise ContinuationError(
                "ACF worktree verification failed",
                code="workstream_verification_failed",
                details={"workstream": workstream},
            )
        interval = int(args.interval_minutes)
        ttl = int(args.lease_ttl_minutes)
        renew = int(args.renew_interval_minutes)
        if interval < 1 or ttl < 1 or ttl > MAX_LEASE_TTL_MINUTES or renew < 1 or renew >= ttl:
            raise ContinuationError("invalid interval/lease timing values", code="timing_invalid")
        directory = _task_parent(root) / _safe_key(task_id)
        paths = {
            "directory": directory,
            "lock": directory / "state.lock",
            "control": directory / "control.json",
            "state": directory / "state.json",
            "lease": directory / "lease.json",
            "pause": directory / "pause.json",
            "receipt": directory / "last_run.json",
        }
        if paths["control"].exists() and not args.force:
            raise ContinuationError(
                "continuation task is already initialized",
                code="continuation_exists",
                next_actions=["Use `acf continuation doctor` or rerun init with --force after review."],
            )
        now = _iso()
        control = {
            "schema_version": CONTROL_SCHEMA,
            "task_id": task_id,
            "title": str(args.title).strip(),
            "objective": str(args.objective).strip(),
            "workspace_root": str(root),
            "expected_branch": expected_branch,
            "bootstrap_head": git["head"],
            "workstream_id": args.workstream,
            "interval_minutes": interval,
            "lease_ttl_minutes": ttl,
            "renew_interval_minutes": renew,
            "history_policy": "local_first",
            "created_at": now,
            "updated_at": now,
        }
        plan_refs = list(args.plan_ref or [])
        state = {
            "schema_version": STATE_SCHEMA,
            "task_id": task_id,
            "objective": str(args.objective).strip(),
            "status": "ready",
            "stage": str(args.stage or "bootstrap").strip(),
            "next_action": str(args.next_action or "Run continuation doctor and the next bounded gate.").strip(),
            "updated_at": now,
            "completed": ["Initialized ACF bounded continuation control."],
            "constraints": [
                "Use the configured fixed Git worktree and branch.",
                "Treat local project state as authoritative; do not reconstruct state from chat history by default.",
                "Do not repeat an uncertain non-idempotent operation.",
                "Finish a write round with a clean worktree checkpoint before release.",
            ],
            "evidence_refs": [],
            "open_questions": [],
            "plan_refs": plan_refs,
            "verification": ["Continuation control initialized from a clean Git checkpoint."],
        }
        directory.mkdir(parents=True, exist_ok=True)
        if not paths["lock"].exists():
            paths["lock"].write_bytes(b"0")
        _write_json(paths["control"], control)
        _write_state(paths["state"], state)
        if args.force:
            for stale in (paths["lease"], paths["pause"], paths["receipt"]):
                stale.unlink(missing_ok=True)
        return {
            "status": "initialized",
            "task_id": task_id,
            "workspace_root": str(root),
            "branch": expected_branch,
            "state_dir": str(directory),
            "workstream": workstream,
            "next_action": state["next_action"],
        }

    return _guarded(args, "continuation init", operation)


def continuation_doctor_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        result = _status(root, args.task_id)
        result["status"] = "healthy" if result["ok"] else "invalid"
        result["next_action"] = result["state"]["next_action"]
        return result

    return _guarded(args, "continuation doctor", operation)


def continuation_claim_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            status = _status(root, args.task_id)
            if not status["ok"]:
                raise ContinuationError(
                    "continuation identity checks failed",
                    code="continuation_invalid",
                    details={"blocked_reasons": status["blocked_reasons"]},
                )
            if status["pause"] is not None:
                raise ContinuationError("continuation is paused", code="continuation_paused", exit_code=3)
            if status["lease"]["state"] == "active":
                raise ContinuationBusy(
                    "another round already owns the worktree",
                    details={"lease": status["lease"].get("lease")},
                )
            if not status["git"]["clean"]:
                raise ContinuationError("worktree is dirty", code="worktree_dirty")
            state = _load_state(paths)
            if status.get("expired_round_head_changed"):
                lease_head = status["lease"].get("lease", {}).get("head")
                raise ContinuationError(
                    "expired round changed Git HEAD; reconcile the uncertain prior outcome before another claim",
                    code="continuation_reconciliation_required",
                    exit_code=3,
                    details={
                        "lease_head": lease_head,
                        "current_head": status["git"]["head"],
                    },
                    next_actions=[
                        "Inspect commits since the expired lease head and reconcile the prior round before retrying."
                    ],
                )
            recoverable = state["status"] == "running" and status["lease"]["state"] == "expired"
            if state["status"] not in RUNNABLE_STATUSES and not recoverable:
                raise ContinuationError(
                    f"state is not runnable: {state['status']}", code="continuation_not_runnable", exit_code=3
                )
            control = _load_control(paths, root)
            ttl = int(args.ttl_minutes or control["lease_ttl_minutes"])
            if ttl < 1 or ttl > MAX_LEASE_TTL_MINUTES:
                raise ContinuationError("invalid lease TTL", code="timing_invalid")
            now = _now()
            lease = {
                "schema_version": LEASE_SCHEMA,
                "lease_id": str(uuid.uuid4()),
                "runner_id": str(args.runner_id).strip(),
                "task_id": control["task_id"],
                "workspace_root": str(root),
                "branch": status["git"]["branch"],
                "head": status["git"]["head"],
                "issued_at": _iso(now),
                "expires_at": _iso(now + timedelta(minutes=ttl)),
            }
            _write_json(paths["lease"], lease)
            state["status"] = "running"
            state["updated_at"] = _iso()
            if recoverable:
                state["verification"] = _append_unique(
                    state["verification"], ["Recovered an expired lease after clean identity checks."]
                )
            _write_state(paths["state"], state)
            return {
                "status": "claimed",
                "task_id": control["task_id"],
                "lease": lease,
                "stage": state["stage"],
                "next_action": state["next_action"],
                "renew_interval_minutes": control["renew_interval_minutes"],
            }

    return _guarded(args, "continuation claim", operation)


def continuation_renew_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            if paths["pause"].exists():
                raise ContinuationError(
                    "pause was requested; do not extend the active round",
                    code="continuation_paused",
                    exit_code=3,
                )
            snapshot = _lease_snapshot(paths, control)
            if snapshot["state"] != "active":
                raise ContinuationError(
                    f"active lease required; current={snapshot['state']}", code="lease_not_active", exit_code=3
                )
            lease = dict(snapshot["lease"])
            if lease["lease_id"] != args.lease_id:
                raise ContinuationError("lease id does not match active lease", code="lease_mismatch")
            git = _git_identity(root)
            if git["branch"] != control["expected_branch"] or git["detached"]:
                raise ContinuationError("Git identity changed during active round", code="workspace_mismatch")
            ttl = int(args.ttl_minutes or control["lease_ttl_minutes"])
            if ttl < 1 or ttl > MAX_LEASE_TTL_MINUTES:
                raise ContinuationError("invalid lease TTL", code="timing_invalid")
            lease["expires_at"] = _iso(_now() + timedelta(minutes=ttl))
            _write_json(paths["lease"], lease)
            return {"status": "renewed", "lease": lease}

    return _guarded(args, "continuation renew", operation)


def continuation_checkpoint_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            snapshot = _lease_snapshot(paths, control)
            if snapshot["state"] != "active" or snapshot["lease"]["lease_id"] != args.lease_id:
                raise ContinuationError("matching active lease required", code="lease_mismatch")
            state = _load_state(paths)
            if args.status:
                if args.status not in STATE_STATUSES:
                    raise ContinuationError("unsupported continuation status", code="state_invalid")
                state["status"] = args.status
            if args.stage:
                state["stage"] = _validate_text(args.stage, field="stage")
            if args.next_action:
                state["next_action"] = _validate_text(args.next_action, field="next_action")
            updates = {
                "completed": args.completed or [],
                "constraints": args.constraint or [],
                "evidence_refs": args.evidence_ref or [],
                "open_questions": args.open_question or [],
                "plan_refs": args.plan_ref or [],
                "verification": args.verification or [],
            }
            for field, values in updates.items():
                state[field] = _append_unique(state.get(field, []), values)
            state["updated_at"] = _iso()
            _write_state(paths["state"], state)
            return {"status": "checkpointed", "state": state, "next_action": state["next_action"]}

    return _guarded(args, "continuation checkpoint", operation)


def continuation_release_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            snapshot = _lease_snapshot(paths, control)
            if snapshot["state"] != "active" or snapshot["lease"]["lease_id"] != args.lease_id:
                raise ContinuationError("matching active lease required", code="lease_mismatch")
            lease = snapshot["lease"]
            state = _load_state(paths)
            git = _git_identity(root)
            pause = _read_json(paths["pause"], label="pause") if paths["pause"].exists() else None
            outcome = "released"
            if pause is not None:
                state["status"] = "paused"
                state["next_action"] = "Wait for an explicit continuation resume action."
                outcome = "released_to_paused"
            elif not git["clean"]:
                state["status"] = "reconciling"
                state["next_action"] = (
                    "Reconcile the reported worktree changes and create a clean checkpoint before another round."
                )
                state["verification"] = _append_unique(
                    state["verification"], ["Release detected a dirty worktree and failed closed."]
                )
                outcome = "released_to_reconciling"
            else:
                final_status = args.final_status or "ready"
                if final_status not in STATE_STATUSES - {"running"}:
                    raise ContinuationError("invalid final status", code="state_invalid")
                state["status"] = final_status
                if args.stage:
                    state["stage"] = args.stage.strip()
                if args.next_action:
                    state["next_action"] = args.next_action.strip()
                state["verification"] = _append_unique(state["verification"], args.verification or [])
            state["updated_at"] = _iso()
            _write_state(paths["state"], state)
            receipt = {
                "schema_version": RECEIPT_SCHEMA,
                "task_id": control["task_id"],
                "lease_id": lease["lease_id"],
                "runner_id": lease["runner_id"],
                "workspace_root": str(root),
                "branch": git["branch"],
                "head_before": lease["head"],
                "head_after": git["head"],
                "started_at": lease["issued_at"],
                "released_at": _iso(),
                "outcome": outcome,
                "state_status": state["status"],
                "state_stage": state["stage"],
                "dirty_entries": git["dirty_entries"],
            }
            _write_json(paths["receipt"], receipt)
            paths["lease"].unlink(missing_ok=False)
            return {
                "ok": outcome == "released",
                "status": outcome,
                "state": state,
                "receipt": receipt,
                "next_action": state["next_action"],
            }

    return _guarded(args, "continuation release", operation)


def continuation_pause_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            marker = {
                "schema_version": PAUSE_SCHEMA,
                "task_id": control["task_id"],
                "reason": _validate_text(args.reason, field="reason"),
                "requested_by": str(args.requested_by or "user").strip() or "user",
                "created_at": _iso(),
            }
            _write_json(paths["pause"], marker)
            snapshot = _lease_snapshot(paths, control)
            state = _load_state(paths)
            if snapshot["state"] != "active":
                state["status"] = "paused"
                state["next_action"] = "Wait for an explicit continuation resume action."
                state["updated_at"] = _iso()
                _write_state(paths["state"], state)
            return {
                "status": "pause_requested" if snapshot["state"] == "active" else "paused",
                "pause": marker,
                "active_lease": snapshot["state"] == "active",
            }

    return _guarded(args, "continuation pause", operation)


def continuation_resume_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            snapshot = _lease_snapshot(paths, control)
            if snapshot["state"] == "active":
                raise ContinuationBusy("cannot resume while an active round still owns the lease")
            if not paths["pause"].exists():
                raise ContinuationError("pause marker is not present", code="continuation_not_paused")
            state = _load_state(paths)
            state["status"] = "ready"
            state["next_action"] = _validate_text(args.next_action, field="next_action")
            state["updated_at"] = _iso()
            _write_state(paths["state"], state)
            paths["pause"].unlink(missing_ok=False)
            return {"status": "ready", "state": state, "next_action": state["next_action"]}

    return _guarded(args, "continuation resume", operation)


def continuation_prompt_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        control = _load_control(paths, root)
        state = _load_state(paths)
        task_flag = f" --task-id {json.dumps(control['task_id'])}"
        prompt = f"""Use the fixed local Git worktree below as the authoritative execution target.

Task: {control['task_id']} — {control['title']}
Worktree: {root}
Branch: {control['expected_branch']}
Current stage: {state['stage']}
Current status: {state['status']}
Next action: {state['next_action']}

Continuation protocol:
1. Do not reconstruct task state from chat history by default. Read local project plans/evidence and `acf continuation doctor` first.
2. Run `acf continuation doctor {json.dumps(str(root))}{task_flag} --json`.
3. If `can_claim` is false, do not modify the worktree. Report the blocking reason.
4. Claim one bounded round with `acf continuation claim {json.dumps(str(root))}{task_flag} --runner-id <runner> --json` and keep the returned lease_id.
5. Execute only the current bounded gate. Never repeat an uncertain non-idempotent operation.
6. For a long interactive round, renew the same lease before expiry with `acf continuation renew ... --lease-id <lease_id> --json`.
7. Validate the gate and create the project-required clean Git checkpoint before release.
8. Update bounded state with `acf continuation checkpoint ... --lease-id <lease_id> ... --json`.
9. Release the same lease with `acf continuation release ... --lease-id <lease_id> --json`.
10. Stop on paused, blocked_human, reconciling, identity mismatch, or unknown write outcome.
11. If this round exposes a concrete reusable ACF/continuation/workflow defect or operational gap, record it immediately with `acf continuation issue {json.dumps(str(root))}{task_flag} --category <category> --severity <low|medium|high|critical> --text <concise issue> --evidence-ref <path-or-commit> --json`. Do not record normal active-lease no-ops, expected waits, or task-specific scientific failures as product issues.
"""
        return {"status": "rendered", "task_id": control["task_id"], "prompt": prompt}

    result_holder: dict[str, Any] = {}

    def capture() -> dict[str, Any]:
        value = operation()
        result_holder.update(value)
        return value

    exit_code = _guarded(args, "continuation prompt", capture)
    if exit_code == 0 and not json_enabled(args):
        print(result_holder["prompt"])
    return exit_code


def continuation_issue_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        control = _load_control(paths, root)
        state = _load_state(paths)
        if not usage_log_enabled(root):
            raise ContinuationError(
                "usage logging is disabled for this worktree",
                code="usage_log_disabled",
                next_actions=["Run `acf log enable` from the project context before recording dogfood issues."],
            )
        category = str(args.category or "other").strip().lower() or "other"
        severity = str(args.severity or "medium").strip().lower()
        if severity not in {"low", "medium", "high", "critical"}:
            raise ContinuationError("unsupported issue severity", code="issue_invalid")
        text = _validate_text(args.text, field="text")
        related_command = str(args.related_command or "").strip()
        normalized_text = " ".join(text.lower().split())
        fingerprint_seed = "|".join((category, related_command.lower(), normalized_text))
        fingerprint = hashlib.sha256(fingerprint_seed.encode("utf-8")).hexdigest()[:20]
        event: dict[str, object] = {
            "schema_version": 1,
            "timestamp": utc_now_iso(),
            "event_kind": "continuation_issue",
            "command": "continuation issue",
            "project_root": str(root),
            "workspace_root": str(root),
            "task_id": control["task_id"],
            "workstream_id": control.get("workstream_id"),
            "stage": state["stage"],
            "state_status": state["status"],
            "category": category,
            "severity": severity,
            "text": text,
            "fingerprint": fingerprint,
            "evidence_refs": list(dict.fromkeys(args.evidence_ref or []))[:MAX_LIST_ITEMS],
            "related_command": related_command or None,
            "runner_id": str(args.runner_id or "agent").strip() or "agent",
            "ok": True,
            "exit_code": 0,
            "error_code": None,
        }
        append_usage_event(root, event)
        return {
            "status": "issue_recorded",
            "task_id": control["task_id"],
            "fingerprint": fingerprint,
            "log_path": str(usage_log_path(root)),
            "issue": event,
        }

    return _guarded(args, "continuation issue", operation)


__all__ = [
    "continuation_checkpoint_command",
    "continuation_claim_command",
    "continuation_doctor_command",
    "continuation_init_command",
    "continuation_issue_command",
    "continuation_pause_command",
    "continuation_prompt_command",
    "continuation_release_command",
    "continuation_renew_command",
    "continuation_resume_command",
]
