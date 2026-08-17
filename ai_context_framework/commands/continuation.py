"""Model-agnostic bounded continuation control for long-running AI work.

The continuation controller is deliberately not an agent runtime or scheduler.
It stores a compact, user-local recovery state for one Git worktree and exposes
deterministic claim/renew/checkpoint/release primitives that external agents or
schedulers can call.  Authoritative plans and evidence remain in the project.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
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
from ai_context_framework import continuation_recovery, continuation_rounds, continuation_workspace
from ai_context_framework.commands import continuation_workspace as continuation_workspace_commands
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

ROUND_PHASES = continuation_rounds.ROUND_PHASES
EFFECT_STATUSES = continuation_rounds.EFFECT_STATUSES

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


def _fence_token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _public_lease(lease: Mapping[str, Any]) -> dict[str, Any]:
    public = dict(lease)
    public.pop("fence_token_hash", None)
    return public


def _new_fenced_lease(
    *,
    control: Mapping[str, Any],
    root: Path,
    branch: str,
    head: str,
    runner_id: str,
    generation: int,
    ttl_minutes: int,
    now: datetime,
) -> tuple[dict[str, Any], str]:
    fence_token = secrets.token_hex(32)
    lease = {
        "schema_version": LEASE_SCHEMA,
        "lease_id": str(uuid.uuid4()),
        "runner_id": runner_id.strip(),
        "generation": generation,
        "fence_token_hash": _fence_token_hash(fence_token),
        "task_id": control["task_id"],
        "workspace_root": str(root),
        "branch": branch,
        "head": head,
        "issued_at": _iso(now),
        "last_heartbeat_at": _iso(now),
        "last_renew_at": _iso(now),
        "expires_at": _iso(now + timedelta(minutes=ttl_minutes)),
    }
    return lease, fence_token


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
    candidates = sorted(
        path for path in parent.iterdir() if path.is_dir() and (path / "control.json").is_file()
    ) if parent.is_dir() else []
    if task_id:
        directory = parent / _safe_key(task_id)
        if (directory / "control.json").is_file():
            return directory
        if candidates:
            raise ContinuationError(
                f"continuation task is not configured: {task_id}",
                code="continuation_task_not_found",
                details={
                    "requested_task_id": task_id,
                    "available_tasks": [path.name for path in candidates],
                },
                next_actions=["Use one of the available task ids or omit --task-id when only one task exists."],
            )
        raise ContinuationError(
            "no continuation task is configured for this worktree",
            code="continuation_not_initialized",
            details={"requested_task_id": task_id},
            next_actions=["Run `acf continuation init ...` first."],
        )
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
        "rounds": directory / "rounds.json",
        "effects": directory / "effects.json",
        "workspace": directory / "workspace.json",
        "reconcile": directory / "reconcile.json",
        "recovery": directory / "last_recovery.json",
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


def _round_error(exc: continuation_rounds.ContinuationRoundError) -> ContinuationError:
    return ContinuationError(str(exc), code=exc.code)


def _load_round_journal(
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
    *,
    require_existing: bool = False,
) -> dict[str, Any]:
    path = paths["rounds"]
    if not path.exists():
        if require_existing:
            raise ContinuationError(
                "active fenced round is missing its round journal",
                code="round_record_missing",
                exit_code=3,
            )
        return continuation_rounds.empty_round_journal(str(control["task_id"]))
    try:
        payload = _read_json(path, label="round_journal")
        return continuation_rounds.validate_round_journal(payload, task_id=str(control["task_id"]))
    except continuation_rounds.ContinuationRoundError as exc:
        raise _round_error(exc) from exc


def _load_effect_journal(
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
    *,
    require_existing: bool = False,
) -> dict[str, Any]:
    path = paths["effects"]
    if not path.exists():
        if require_existing:
            raise ContinuationError("effect journal is missing", code="effect_journal_missing")
        return continuation_rounds.empty_effect_journal(str(control["task_id"]))
    try:
        payload = _read_json(path, label="effect_journal")
        return continuation_rounds.validate_effect_journal(payload, task_id=str(control["task_id"]))
    except continuation_rounds.ContinuationRoundError as exc:
        raise _round_error(exc) from exc


def _journal_snapshot(paths: Mapping[str, Path], control: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    round_path = paths["rounds"]
    effect_path = paths["effects"]
    if round_path.exists():
        try:
            rounds = _load_round_journal(paths, control)
            round_snapshot = {
                "state": "valid",
                "path": str(round_path),
                "count": len(rounds["rounds"]),
                "latest": continuation_rounds.latest_round(rounds, task_id=str(control["task_id"])),
            }
        except ContinuationError as exc:
            round_snapshot = {"state": "invalid", "path": str(round_path), "error": str(exc)}
    else:
        round_snapshot = {"state": "absent", "path": str(round_path), "count": 0, "latest": None}

    if effect_path.exists():
        try:
            effects = _load_effect_journal(paths, control)
            effect_snapshot = {
                "state": "valid",
                "path": str(effect_path),
                "summary": continuation_rounds.effect_summary(effects, task_id=str(control["task_id"])),
            }
        except ContinuationError as exc:
            effect_snapshot = {"state": "invalid", "path": str(effect_path), "error": str(exc)}
    else:
        effect_snapshot = {
            "state": "absent",
            "path": str(effect_path),
            "summary": continuation_rounds.effect_summary(
                continuation_rounds.empty_effect_journal(str(control["task_id"])),
                task_id=str(control["task_id"]),
            ),
        }
    return round_snapshot, effect_snapshot


def _reconcile_observation(
    root: Path,
    task_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    status = _status(root, task_id)
    paths = _paths(root, task_id)
    control = status["control"]
    rounds = _load_round_journal(paths, control)
    effects = _load_effect_journal(paths, control)
    observation = continuation_recovery.build_observation(
        status,
        rounds=rounds,
        effects=effects,
        task_id=str(control["task_id"]),
    )
    return status, observation


def _require_fenced_generation(lease: Mapping[str, Any]) -> int:
    generation = lease.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise ContinuationError(
            "this command requires a fenced continuation round",
            code="fenced_round_required",
            exit_code=3,
            next_actions=[
                "Finish the legacy round through its compatible path, then claim a new fenced round before using progress/effect commands."
            ],
        )
    return generation


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
    generation = control.get("generation", 0)
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise ContinuationError("invalid control field: generation", code="control_invalid")
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
        generation = lease.get("generation")
        if generation is not None and (
            isinstance(generation, bool) or not isinstance(generation, int) or generation < 1
        ):
            raise ContinuationError("lease generation is invalid", code="lease_invalid")
        fence_hash = lease.get("fence_token_hash")
        if fence_hash is not None:
            if not isinstance(fence_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", fence_hash):
                raise ContinuationError("lease fence token hash is invalid", code="lease_invalid")
            if generation is None:
                raise ContinuationError("fenced lease requires generation", code="lease_invalid")
        heartbeat_at: datetime | None = None
        if lease.get("last_heartbeat_at") is not None:
            heartbeat_at = _parse_iso(lease.get("last_heartbeat_at"), field="last_heartbeat_at")
            if heartbeat_at < issued:
                raise ContinuationError("lease heartbeat predates issue time", code="lease_invalid")
        if lease.get("last_renew_at") is not None:
            last_renew_at = _parse_iso(lease.get("last_renew_at"), field="last_renew_at")
            if last_renew_at < issued:
                raise ContinuationError("lease renew timestamp predates issue time", code="lease_invalid")
    except ContinuationError as exc:
        return {"state": "invalid", "path": str(path), "error": str(exc)}
    active = expires > _now()
    stale_after_seconds = int(control["renew_interval_minutes"]) * 60
    heartbeat_age_seconds: int | None = None
    if not active:
        liveness = "expired"
    elif heartbeat_at is None:
        liveness = "legacy_unknown"
    else:
        heartbeat_age_seconds = max(0, int((_now() - heartbeat_at).total_seconds()))
        liveness = "stale" if heartbeat_age_seconds > stale_after_seconds else "fresh"
    orphan_candidate = active and liveness == "stale"
    return {
        "state": "active" if active else "expired",
        "path": str(path),
        "lease": lease,
        "liveness": liveness,
        "orphan_candidate": orphan_candidate,
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "stale_after_seconds": stale_after_seconds,
    }


def _assert_lease_owner(
    snapshot: Mapping[str, Any],
    *,
    lease_id: str,
    fence_token: str | None,
    generation: int | None,
) -> dict[str, Any]:
    if snapshot.get("state") != "active":
        raise ContinuationError(
            f"active lease required; current={snapshot.get('state')}",
            code="lease_not_active",
            exit_code=3,
        )
    raw_lease = snapshot.get("lease")
    if not isinstance(raw_lease, Mapping):
        raise ContinuationError("active lease payload is missing", code="lease_invalid")
    lease = dict(raw_lease)
    if lease.get("lease_id") != lease_id:
        raise ContinuationError(
            "lease id does not match active lease",
            code="lease_mismatch",
            exit_code=3,
        )
    lease_generation = lease.get("generation")
    if lease_generation is not None and generation is None:
        raise ContinuationError(
            "lease generation is required for this lease",
            code="fence_generation_required",
            exit_code=3,
            details={"active_generation": lease_generation},
        )
    if generation is not None and lease_generation != generation:
        raise ContinuationError(
            "lease generation does not match active owner",
            code="fence_generation_mismatch",
            exit_code=3,
            details={"active_generation": lease_generation, "provided_generation": generation},
        )
    expected_hash = lease.get("fence_token_hash")
    if expected_hash is not None:
        if not fence_token:
            raise ContinuationError(
                "fence token is required for this lease",
                code="fence_token_required",
                exit_code=3,
            )
        actual_hash = _fence_token_hash(fence_token)
        if not hmac.compare_digest(str(expected_hash), actual_hash):
            raise ContinuationError(
                "fence token does not match active owner",
                code="fence_token_mismatch",
                exit_code=3,
            )
    return lease


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
    round_journal, effect_journal = _journal_snapshot(paths, control)
    if round_journal["state"] == "invalid":
        identity_errors.append("round journal is malformed or identity-mismatched")
    if effect_journal["state"] == "invalid":
        identity_errors.append("effect journal is malformed or identity-mismatched")
    pause = _read_json(paths["pause"], label="pause") if paths["pause"].exists() else None
    rebaseline_workspace = lease["state"] == "absent" and state["status"] in RUNNABLE_STATUSES
    workspace = continuation_workspace_commands.workspace_snapshot(
        root,
        paths,
        control,
        rebaseline=rebaseline_workspace,
    )
    if workspace["state"] == "invalid":
        identity_errors.append("workspace ownership manifest is malformed or identity-mismatched")
    expired_running_round = state["status"] == "running" and lease["state"] == "expired"
    expired_round_head_changed = bool(
        expired_running_round
        and isinstance(lease.get("lease"), Mapping)
        and lease["lease"].get("head") != git["head"]
    )
    effect_summary = effect_journal.get("summary", {})
    effect_reconciliation_required = bool(
        expired_running_round
        and effect_journal["state"] == "valid"
        and isinstance(effect_summary, Mapping)
        and int(effect_summary.get("total", 0)) > 0
    )
    recoverable_expired = (
        expired_running_round
        and not expired_round_head_changed
        and not effect_reconciliation_required
    )
    workspace_has_conflicts = bool(workspace.get("has_conflicts"))
    if git["clean"]:
        workspace_allows_dirty = True
    elif workspace["state"] != "valid":
        workspace_allows_dirty = False
    elif lease["state"] == "active":
        workspace_allows_dirty = not workspace_has_conflicts
    elif lease["state"] == "absent" and state["status"] in RUNNABLE_STATUSES:
        workspace_allows_dirty = not workspace_has_conflicts
    else:
        workspace_allows_dirty = False
    can_claim = (
        not identity_errors
        and workspace_allows_dirty
        and pause is None
        and lease["state"] in {"absent", "expired"}
        and (state["status"] in RUNNABLE_STATUSES or recoverable_expired)
    )
    blocked: list[str] = list(identity_errors)
    if not git["clean"] and not workspace_allows_dirty:
        blocked.append("worktree_dirty")
    if workspace_has_conflicts:
        blocked.append("workspace_conflict")
    if pause is not None:
        blocked.append("paused")
    if lease["state"] == "active":
        blocked.append("active_lease")
    orphan_candidate = bool(lease.get("orphan_candidate"))
    if orphan_candidate:
        blocked.append("orphan_candidate")
    if expired_round_head_changed:
        blocked.append("expired_round_head_changed")
    if effect_reconciliation_required:
        blocked.append("effect_reconciliation_required")
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
        "round_journal": round_journal,
        "effect_journal": effect_journal,
        "workspace": workspace,
        "pause": pause,
        "workstream": workstream,
        "state_dir": str(paths["directory"]),
        "recoverable_expired_round": recoverable_expired,
        "expired_round_head_changed": expired_round_head_changed,
        "effect_reconciliation_required": effect_reconciliation_required,
        "orphan_candidate": orphan_candidate,
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
            if status.get("effect_reconciliation_required"):
                raise ContinuationError(
                    "expired round has durable effect records; reconcile them before another claim",
                    code="continuation_reconciliation_required",
                    exit_code=3,
                    details={"effect_summary": status["effect_journal"].get("summary", {})},
                    next_actions=[
                        "Inspect `acf continuation effect list` and use the formal reconcile/recover path once available; do not resubmit recorded effects."
                    ],
                )
            recoverable = state["status"] == "running" and status["lease"]["state"] == "expired"
            if state["status"] not in RUNNABLE_STATUSES and not recoverable:
                raise ContinuationError(
                    f"state is not runnable: {state['status']}", code="continuation_not_runnable", exit_code=3
                )
            if not status["can_claim"]:
                raise ContinuationError(
                    "continuation round cannot be claimed from the current workspace state",
                    code="continuation_not_claimable",
                    exit_code=3,
                    details={"blocked_reasons": status["blocked_reasons"]},
                )
            control = _load_control(paths, root)
            ttl = int(args.ttl_minutes or control["lease_ttl_minutes"])
            if ttl < 1 or ttl > MAX_LEASE_TTL_MINUTES:
                raise ContinuationError("invalid lease TTL", code="timing_invalid")
            now = _now()
            generation = int(control.get("generation", 0)) + 1
            lease, fence_token = _new_fenced_lease(
                control=control,
                root=root,
                branch=str(status["git"]["branch"]),
                head=str(status["git"]["head"]),
                runner_id=str(args.runner_id),
                generation=generation,
                ttl_minutes=ttl,
                now=now,
            )
            round_journal = _load_round_journal(paths, control)
            try:
                round_journal, round_record = continuation_rounds.begin_round(
                    round_journal,
                    task_id=str(control["task_id"]),
                    generation=generation,
                    lease_id=str(lease["lease_id"]),
                    runner_id=str(lease["runner_id"]),
                    now=_iso(now),
                )
            except continuation_rounds.ContinuationRoundError as exc:
                raise _round_error(exc) from exc
            workspace_manifest = continuation_workspace_commands.load_workspace_manifest(paths, control)
            if workspace_manifest is None:
                if not status["git"]["clean"]:
                    raise ContinuationError(
                        "legacy continuation without a workspace manifest cannot adopt dirty state implicitly",
                        code="workspace_manifest_missing",
                        exit_code=3,
                    )
                try:
                    workspace_manifest = continuation_workspace.new_manifest(
                        task_id=str(control["task_id"]),
                        snapshot=continuation_workspace_commands.workspace_current_snapshot(root),
                        now=_iso(now),
                    )
                except continuation_workspace.ContinuationWorkspaceError as exc:
                    raise continuation_workspace_commands.workspace_error(exc) from exc
            try:
                workspace_manifest = continuation_workspace.begin_generation(
                    workspace_manifest,
                    task_id=str(control["task_id"]),
                    generation=generation,
                    snapshot=continuation_workspace_commands.workspace_current_snapshot(root),
                    now=_iso(now),
                )
            except continuation_workspace.ContinuationWorkspaceError as exc:
                raise continuation_workspace_commands.workspace_error(exc) from exc
            control["generation"] = generation
            control["updated_at"] = _iso(now)
            _write_json(paths["control"], control)
            _write_json(paths["lease"], lease)
            _write_json(paths["rounds"], round_journal)
            _write_json(paths["workspace"], workspace_manifest)
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
                "lease": _public_lease(lease),
                "fence_token": fence_token,
                "generation": generation,
                "round": round_record,
                "workspace": continuation_workspace.summary(
                    workspace_manifest,
                    task_id=str(control["task_id"]),
                ),
                "stage": state["stage"],
                "next_action": state["next_action"],
                "renew_interval_minutes": control["renew_interval_minutes"],
            }

    return _guarded(args, "continuation claim", operation)


def continuation_assert_owner_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            snapshot = _lease_snapshot(paths, control)
            lease = _assert_lease_owner(
                snapshot,
                lease_id=args.lease_id,
                fence_token=args.fence_token,
                generation=args.generation,
            )
            git = _git_identity(root)
            if git["branch"] != control["expected_branch"] or git["detached"]:
                raise ContinuationError("Git identity changed during active round", code="workspace_mismatch")
            return {
                "status": "owner_confirmed",
                "lease": _public_lease(lease),
                "generation": lease.get("generation"),
                "liveness": snapshot.get("liveness"),
            }

    return _guarded(args, "continuation assert-owner", operation)


def continuation_heartbeat_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            snapshot = _lease_snapshot(paths, control)
            lease = _assert_lease_owner(
                snapshot,
                lease_id=args.lease_id,
                fence_token=args.fence_token,
                generation=args.generation,
            )
            git = _git_identity(root)
            if git["branch"] != control["expected_branch"] or git["detached"]:
                raise ContinuationError("Git identity changed during active round", code="workspace_mismatch")
            lease["last_heartbeat_at"] = _iso()
            _write_json(paths["lease"], lease)
            return {
                "status": "heartbeat_recorded",
                "lease": _public_lease(lease),
                "generation": lease.get("generation"),
            }

    return _guarded(args, "continuation heartbeat", operation)


def continuation_progress_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        if args.phase is None and args.milestone is None and not (args.evidence_ref or []):
            raise ContinuationError(
                "progress requires --phase, --milestone, or --evidence-ref",
                code="progress_empty",
            )
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            snapshot = _lease_snapshot(paths, control)
            lease = _assert_lease_owner(
                snapshot,
                lease_id=args.lease_id,
                fence_token=args.fence_token,
                generation=args.generation,
            )
            generation = _require_fenced_generation(lease)
            journal = _load_round_journal(paths, control, require_existing=True)
            try:
                journal, record = continuation_rounds.update_round(
                    journal,
                    task_id=str(control["task_id"]),
                    generation=generation,
                    lease_id=str(lease["lease_id"]),
                    phase=args.phase,
                    milestone=args.milestone,
                    evidence_refs=args.evidence_ref or [],
                    now=_iso(),
                )
            except continuation_rounds.ContinuationRoundError as exc:
                raise _round_error(exc) from exc
            _write_json(paths["rounds"], journal)
            return {
                "status": "progress_recorded",
                "round": record,
                "generation": generation,
            }

    return _guarded(args, "continuation progress", operation)


def continuation_effect_prepare_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            snapshot = _lease_snapshot(paths, control)
            lease = _assert_lease_owner(
                snapshot,
                lease_id=args.lease_id,
                fence_token=args.fence_token,
                generation=args.generation,
            )
            generation = _require_fenced_generation(lease)
            journal = _load_effect_journal(paths, control)
            try:
                journal, effect, created = continuation_rounds.prepare_effect(
                    journal,
                    task_id=str(control["task_id"]),
                    generation=generation,
                    logical_key=args.key,
                    kind=args.kind,
                    external_id=args.external_id,
                    milestone=args.milestone,
                    evidence_refs=args.evidence_ref or [],
                    now=_iso(),
                )
            except continuation_rounds.ContinuationRoundError as exc:
                raise _round_error(exc) from exc
            if created:
                _write_json(paths["effects"], journal)
            return {
                "status": "effect_prepared" if created else "effect_exists",
                "created": created,
                "effect": effect,
                "summary": continuation_rounds.effect_summary(
                    journal, task_id=str(control["task_id"])
                ),
            }

    return _guarded(args, "continuation effect prepare", operation)


def continuation_effect_update_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        if (
            args.status is None
            and args.external_id is None
            and args.milestone is None
            and not (args.evidence_ref or [])
        ):
            raise ContinuationError(
                "effect update requires a status, external id, milestone, or evidence reference",
                code="effect_update_empty",
            )
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            snapshot = _lease_snapshot(paths, control)
            lease = _assert_lease_owner(
                snapshot,
                lease_id=args.lease_id,
                fence_token=args.fence_token,
                generation=args.generation,
            )
            generation = _require_fenced_generation(lease)
            journal = _load_effect_journal(paths, control, require_existing=True)
            try:
                journal, effect = continuation_rounds.update_effect(
                    journal,
                    task_id=str(control["task_id"]),
                    generation=generation,
                    logical_key=args.key,
                    status=args.status,
                    external_id=args.external_id,
                    milestone=args.milestone,
                    evidence_refs=args.evidence_ref or [],
                    now=_iso(),
                )
            except continuation_rounds.ContinuationRoundError as exc:
                raise _round_error(exc) from exc
            _write_json(paths["effects"], journal)
            return {
                "status": "effect_updated",
                "effect": effect,
                "summary": continuation_rounds.effect_summary(
                    journal, task_id=str(control["task_id"])
                ),
            }

    return _guarded(args, "continuation effect update", operation)


def continuation_effect_list_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            journal = _load_effect_journal(paths, control)
            return {
                "status": "listed",
                "effects": journal["effects"],
                "summary": continuation_rounds.effect_summary(
                    journal, task_id=str(control["task_id"])
                ),
                "path": str(paths["effects"]),
            }

    return _guarded(args, "continuation effect list", operation)


def continuation_reconcile_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            status, observation = _reconcile_observation(root, args.task_id)
            evidence_refs = list(dict.fromkeys(args.evidence_ref or []))[:MAX_LIST_ITEMS]
            for evidence_ref in evidence_refs:
                _validate_text(evidence_ref, field="evidence_ref")
            accepted_head = str(args.accept_head).strip() if args.accept_head else None
            decision, reasons = continuation_recovery.reconcile_decision(
                status,
                observation,
                owner_ended=bool(args.owner_ended),
                accepted_head=accepted_head,
                evidence_refs=evidence_refs,
            )
            result: dict[str, Any] = {
                "status": "reconciled",
                "decision": decision,
                "eligible_for_recover": decision == "eligible",
                "reasons": reasons,
                "observation": observation,
                "assertions": {
                    "owner_ended": bool(args.owner_ended),
                    "accepted_head": accepted_head,
                },
                "evidence_refs": evidence_refs,
                "recorded": False,
            }
            if args.record:
                reason = _validate_text(args.reason, field="reason")
                receipt = {
                    "schema_version": continuation_recovery.RECONCILE_SCHEMA,
                    "receipt_id": str(uuid.uuid4()),
                    "task_id": status["control"]["task_id"],
                    "created_at": _iso(),
                    "decision": decision,
                    "reasons": reasons,
                    "reason": reason,
                    "evidence_refs": evidence_refs,
                    "assertions": result["assertions"],
                    "observation": observation,
                }
                _write_json(paths["reconcile"], receipt)
                result["recorded"] = True
                result["receipt"] = receipt
            return result

    return _guarded(args, "continuation reconcile", operation)


def continuation_recover_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            try:
                receipt = continuation_recovery.validate_reconcile_receipt(
                    _read_json(paths["reconcile"], label="reconcile")
                )
            except continuation_recovery.ContinuationRecoveryError as exc:
                raise ContinuationError(str(exc), code=exc.code) from exc
            if receipt["task_id"] != control["task_id"]:
                raise ContinuationError("reconcile receipt task mismatch", code="reconcile_invalid")
            if receipt["receipt_id"] != args.reconcile_id:
                raise ContinuationError(
                    "reconcile receipt id does not match",
                    code="reconcile_mismatch",
                    exit_code=3,
                )
            if receipt["decision"] != "eligible":
                raise ContinuationError(
                    "reconcile receipt does not authorize recovery",
                    code="recovery_not_authorized",
                    exit_code=3,
                    details={"reasons": receipt["reasons"]},
                )

            status, observation = _reconcile_observation(root, args.task_id)
            if dict(receipt["observation"]) != observation:
                raise ContinuationError(
                    "continuation state changed after reconciliation",
                    code="reconciliation_stale",
                    exit_code=3,
                    details={"recorded": receipt["observation"], "current": observation},
                    next_actions=["Run `acf continuation reconcile` again against the current state."],
                )
            assertions = receipt["assertions"]
            owner_ended = assertions.get("owner_ended") is True
            accepted_head = assertions.get("accepted_head")
            decision, reasons = continuation_recovery.reconcile_decision(
                status,
                observation,
                owner_ended=owner_ended,
                accepted_head=str(accepted_head) if accepted_head is not None else None,
                evidence_refs=[str(value) for value in receipt["evidence_refs"]],
            )
            if decision != "eligible":
                raise ContinuationError(
                    "current state no longer satisfies the recorded reconciliation",
                    code="recovery_not_authorized",
                    exit_code=3,
                    details={"reasons": reasons},
                )

            ttl = int(args.ttl_minutes or control["lease_ttl_minutes"])
            if ttl < 1 or ttl > MAX_LEASE_TTL_MINUTES:
                raise ContinuationError("invalid lease TTL", code="timing_invalid")
            old_lease_payload = status["lease"].get("lease")
            if not isinstance(old_lease_payload, Mapping):
                raise ContinuationError("recoverable lease is missing", code="lease_invalid")
            old_lease = dict(old_lease_payload)
            old_generation = old_lease.get("generation")
            generation = max(
                int(control.get("generation", 0)),
                int(old_generation) if isinstance(old_generation, int) and not isinstance(old_generation, bool) else 0,
            ) + 1
            now = _now()
            lease, fence_token = _new_fenced_lease(
                control=control,
                root=root,
                branch=str(status["git"]["branch"]),
                head=str(status["git"]["head"]),
                runner_id=str(args.runner_id),
                generation=generation,
                ttl_minutes=ttl,
                now=now,
            )

            workspace_snapshot = continuation_workspace_commands.workspace_current_snapshot(root)
            workspace_manifest = continuation_workspace_commands.load_workspace_manifest(paths, control)
            try:
                if workspace_manifest is None:
                    if not status["git"]["clean"]:
                        raise ContinuationError(
                            "dirty recovery requires an existing workspace ownership manifest",
                            code="workspace_manifest_missing",
                            exit_code=3,
                        )
                    workspace_manifest = continuation_workspace.new_manifest(
                        task_id=str(control["task_id"]),
                        snapshot=workspace_snapshot,
                        now=_iso(now),
                    )
                    workspace_manifest = continuation_workspace.begin_generation(
                        workspace_manifest,
                        task_id=str(control["task_id"]),
                        generation=generation,
                        snapshot=workspace_snapshot,
                        now=_iso(now),
                    )
                elif isinstance(old_generation, int) and not isinstance(old_generation, bool):
                    workspace_manifest = continuation_workspace.recover_generation(
                        workspace_manifest,
                        task_id=str(control["task_id"]),
                        previous_generation=old_generation,
                        generation=generation,
                        snapshot=workspace_snapshot,
                        now=_iso(now),
                    )
                else:
                    if not status["git"]["clean"]:
                        raise ContinuationError(
                            "legacy dirty recovery cannot prove workspace ownership",
                            code="workspace_generation_mismatch",
                            exit_code=3,
                        )
                    workspace_manifest = continuation_workspace.begin_generation(
                        workspace_manifest,
                        task_id=str(control["task_id"]),
                        generation=generation,
                        snapshot=workspace_snapshot,
                        now=_iso(now),
                    )
            except continuation_workspace.ContinuationWorkspaceError as exc:
                raise continuation_workspace_commands.workspace_error(exc) from exc
            workspace_summary = continuation_workspace.summary(
                workspace_manifest,
                task_id=str(control["task_id"]),
            )

            round_journal = _load_round_journal(paths, control)
            if isinstance(old_generation, int) and not isinstance(old_generation, bool):
                try:
                    round_journal, _ = continuation_rounds.finish_round(
                        round_journal,
                        task_id=str(control["task_id"]),
                        generation=old_generation,
                        lease_id=str(old_lease["lease_id"]),
                        reconciling=True,
                        milestone="superseded_by_recovery",
                        evidence_refs=[f"reconcile:{receipt['receipt_id']}"],
                        now=_iso(now),
                    )
                except continuation_rounds.ContinuationRoundError as exc:
                    raise _round_error(exc) from exc
            try:
                round_journal, round_record = continuation_rounds.begin_round(
                    round_journal,
                    task_id=str(control["task_id"]),
                    generation=generation,
                    lease_id=str(lease["lease_id"]),
                    runner_id=str(lease["runner_id"]),
                    now=_iso(now),
                )
            except continuation_rounds.ContinuationRoundError as exc:
                raise _round_error(exc) from exc

            control["generation"] = generation
            control["updated_at"] = _iso(now)
            state = _load_state(paths)
            state["status"] = "running"
            state["updated_at"] = _iso(now)
            state["verification"] = _append_unique(
                state["verification"],
                [f"Recovered continuation ownership via reconcile receipt {receipt['receipt_id']}."],
            )
            recovery = {
                "schema_version": continuation_recovery.RECOVERY_SCHEMA,
                "recovery_id": str(uuid.uuid4()),
                "reconcile_receipt_id": receipt["receipt_id"],
                "task_id": control["task_id"],
                "recovered_at": _iso(now),
                "previous_lease_id": old_lease["lease_id"],
                "previous_generation": old_generation,
                "new_lease_id": lease["lease_id"],
                "new_generation": generation,
                "runner_id": lease["runner_id"],
                "head": status["git"]["head"],
                "effect_digest": observation["effect_digest"],
                "workspace_digest": workspace_summary["manifest_digest"],
            }
            _write_json(paths["control"], control)
            _write_json(paths["lease"], lease)
            _write_json(paths["rounds"], round_journal)
            _write_json(paths["workspace"], workspace_manifest)
            _write_state(paths["state"], state)
            _write_json(paths["recovery"], recovery)
            return {
                "status": "recovered",
                "task_id": control["task_id"],
                "lease": _public_lease(lease),
                "fence_token": fence_token,
                "generation": generation,
                "round": round_record,
                "recovery": recovery,
                "workspace": workspace_summary,
                "next_action": state["next_action"],
                "renew_interval_minutes": control["renew_interval_minutes"],
            }

    return _guarded(args, "continuation recover", operation)


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
            lease = _assert_lease_owner(
                snapshot,
                lease_id=args.lease_id,
                fence_token=args.fence_token,
                generation=args.generation,
            )
            git = _git_identity(root)
            if git["branch"] != control["expected_branch"] or git["detached"]:
                raise ContinuationError("Git identity changed during active round", code="workspace_mismatch")
            ttl = int(args.ttl_minutes or control["lease_ttl_minutes"])
            if ttl < 1 or ttl > MAX_LEASE_TTL_MINUTES:
                raise ContinuationError("invalid lease TTL", code="timing_invalid")
            now = _now()
            lease["last_heartbeat_at"] = _iso(now)
            lease["last_renew_at"] = _iso(now)
            lease["expires_at"] = _iso(now + timedelta(minutes=ttl))
            _write_json(paths["lease"], lease)
            return {"status": "renewed", "lease": _public_lease(lease)}

    return _guarded(args, "continuation renew", operation)


def continuation_checkpoint_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            snapshot = _lease_snapshot(paths, control)
            _assert_lease_owner(
                snapshot,
                lease_id=args.lease_id,
                fence_token=args.fence_token,
                generation=args.generation,
            )
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
            lease = _assert_lease_owner(
                snapshot,
                lease_id=args.lease_id,
                fence_token=args.fence_token,
                generation=args.generation,
            )
            generation = lease.get("generation")
            round_journal: dict[str, Any] | None = None
            if generation is not None:
                round_journal = _load_round_journal(paths, control, require_existing=True)
            state = _load_state(paths)
            git = _git_identity(root)
            workspace_manifest = continuation_workspace_commands.load_workspace_manifest(paths, control)
            workspace_summary: dict[str, Any] | None = None
            workspace_release_blocked = False
            if workspace_manifest is not None:
                try:
                    workspace_manifest = continuation_workspace.classify(
                        workspace_manifest,
                        task_id=str(control["task_id"]),
                    snapshot=continuation_workspace_commands.workspace_current_snapshot(root),
                        now=_iso(),
                    )
                except continuation_workspace.ContinuationWorkspaceError as exc:
                    raise continuation_workspace_commands.workspace_error(exc) from exc
                workspace_summary = continuation_workspace.summary(
                    workspace_manifest,
                    task_id=str(control["task_id"]),
                )
                workspace_release_blocked = bool(
                    workspace_summary["has_conflicts"] or workspace_summary["runner_owned_paths"]
                )
            elif not git["clean"]:
                workspace_release_blocked = True
            pause = _read_json(paths["pause"], label="pause") if paths["pause"].exists() else None
            outcome = "released"
            if pause is not None:
                state["status"] = "paused"
                state["next_action"] = "Wait for an explicit continuation resume action."
                outcome = "released_to_paused"
            elif workspace_release_blocked:
                state["status"] = "reconciling"
                state["next_action"] = (
                    "Reconcile runner-owned or conflicting workspace changes before another round."
                )
                state["verification"] = _append_unique(
                    state["verification"], ["Release detected runner-owned/conflicting workspace state and failed closed."]
                )
                outcome = "released_to_reconciling"
            else:
                final_status = args.final_status
                if final_status is None:
                    final_status = "ready" if state["status"] == "running" else state["status"]
                if final_status not in STATE_STATUSES - {"running"}:
                    raise ContinuationError("invalid final status", code="state_invalid")
                state["status"] = final_status
                if args.stage:
                    state["stage"] = args.stage.strip()
                if args.next_action:
                    state["next_action"] = args.next_action.strip()
                state["verification"] = _append_unique(state["verification"], args.verification or [])
            release_now = _iso()
            finished_round: dict[str, Any] | None = None
            if round_journal is not None:
                try:
                    round_journal, finished_round = continuation_rounds.finish_round(
                        round_journal,
                        task_id=str(control["task_id"]),
                        generation=_require_fenced_generation(lease),
                        lease_id=str(lease["lease_id"]),
                        reconciling=state["status"] == "reconciling",
                        milestone=outcome,
                        evidence_refs=[],
                        now=release_now,
                    )
                except continuation_rounds.ContinuationRoundError as exc:
                    raise _round_error(exc) from exc
            state["updated_at"] = release_now
            _write_state(paths["state"], state)
            if round_journal is not None:
                _write_json(paths["rounds"], round_journal)
            if workspace_manifest is not None:
                _write_json(paths["workspace"], workspace_manifest)
            receipt = {
                "schema_version": RECEIPT_SCHEMA,
                "task_id": control["task_id"],
                "lease_id": lease["lease_id"],
                "runner_id": lease["runner_id"],
                "generation": lease.get("generation"),
                "workspace_root": str(root),
                "branch": git["branch"],
                "head_before": lease["head"],
                "head_after": git["head"],
                "started_at": lease["issued_at"],
                "released_at": release_now,
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
                "round": finished_round,
                "workspace": workspace_summary,
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
3. If `can_claim` is false, never copy an old lease id to impersonate its owner. A fresh active owner means no-op. For stale/orphan_candidate, legacy_unknown, changed HEAD, or effect reconciliation signals, use `acf continuation reconcile ... --json` to inspect the exact recovery blockers. Only after external/local evidence proves the prior owner ended, all effects are resolved/reusable, and any advanced HEAD is explicitly accepted may you record an eligible receipt with `acf continuation reconcile ... --owner-ended --accept-head <current-head-if-needed> --evidence-ref <durable-ref> --reason <concise-reason> --record --json`, then fence the old owner with `acf continuation recover ... --reconcile-id <receipt_id> --runner-id <runner> --json`. If reconcile remains blocked, stop without modifying the worktree.
4. If `can_claim` is true, claim one bounded round with `acf continuation claim {json.dumps(str(root))}{task_flag} --runner-id <runner> --json`. If step 3 recovered an orphan instead, use the credentials returned by `recover` and do not claim again. Keep the returned lease_id, generation, and fence_token; treat fence_token as an owner credential and do not copy it into project files or logs.
5. Execute only the current bounded gate. Record compact runtime-neutral progress with `acf continuation progress ... --phase <phase> --milestone <compact-name> --evidence-ref <durable-ref> --json`; do not copy raw tool output or transcript history into continuation state.
6. Inspect workspace ownership with `acf continuation workspace status ... --json`. Before modifying project files, declare the concrete paths with `acf continuation workspace intent ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --path <path> ... --json`. A bound Workstream intent must remain inside its direct write scope. Existing baseline/external dirty is protected; do not stash, reset, clean, stage, or commit it. After writes and before finalization, refresh ownership with `acf continuation workspace refresh ...` so runner-owned, unrelated external, and true path conflicts are explicit.
7. Before protected non-idempotent work, verify ownership with `acf continuation assert-owner ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json`. For long work, record liveness with `acf continuation heartbeat ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json` and extend TTL with `acf continuation renew ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json` before their configured thresholds; heartbeat proves liveness but does not extend TTL.
8. Before executing each external/non-idempotent side effect, write its deterministic identity first with `acf continuation effect prepare ... --key <logical-key> --kind <generic-kind> --json`. Execute the side effect only when prepare returns `created=true`; `created=false` means the logical effect already exists and must be inspected/reused/reconciled rather than resubmitted. After authoritative observations, update only compact status/milestone/external-id/evidence references with `acf continuation effect update ...`. If an outcome is uncertain, stop and preserve the effect for reconciliation; never resubmit it from memory. Use `acf continuation effect list ... --json` to inspect durable effect identities.
9. Validate the gate and create the project-required checkpoint for runner-owned writes. The entire worktree does not need to become clean when preserved baseline/external dirty is unrelated; never include those external paths in the checkpoint. Any runner-owned path left dirty or any workspace conflict must remain fail-closed.
10. Update bounded state with `acf continuation checkpoint ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> ... --json`.
11. Release the same lease with `acf continuation release ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json`. Release may preserve unrelated external dirty, but it must not silently release unresolved runner-owned/conflicting workspace state.
12. Stop on paused, blocked_human, reconciling, identity mismatch, workspace conflict, effect reconciliation required, or unknown write outcome.
13. If this round exposes a concrete reusable ACF/continuation/workflow defect or operational gap, record it immediately with `acf continuation issue {json.dumps(str(root))}{task_flag} --category <category> --severity <low|medium|high|critical> --text <concise issue> --evidence-ref <path-or-commit> --json`. Do not record normal active-lease no-ops, expected waits, or task-specific scientific failures as product issues.
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
        resolve_fingerprint = str(args.resolve_fingerprint or "").strip().lower()
        if resolve_fingerprint:
            if not re.fullmatch(r"[0-9a-f]{20}", resolve_fingerprint):
                raise ContinuationError("issue fingerprint must be 20 lowercase hex characters", code="issue_invalid")
            fingerprint = resolve_fingerprint
            event_kind = "continuation_issue_resolution"
            command_status = "issue_resolved"
        else:
            normalized_text = " ".join(text.lower().split())
            fingerprint_seed = "|".join((category, related_command.lower(), normalized_text))
            fingerprint = hashlib.sha256(fingerprint_seed.encode("utf-8")).hexdigest()[:20]
            event_kind = "continuation_issue"
            command_status = "issue_recorded"
        event: dict[str, object] = {
            "schema_version": 1,
            "timestamp": utc_now_iso(),
            "event_kind": event_kind,
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
            "status": command_status,
            "task_id": control["task_id"],
            "fingerprint": fingerprint,
            "log_path": str(usage_log_path(root)),
            "issue": event,
        }

    return _guarded(args, "continuation issue", operation)


def register_round_effect_parsers(subparsers, add_json_argument) -> None:
    progress = subparsers.add_parser(
        "progress",
        help="record bounded runtime-neutral round phase/milestone progress",
    )
    progress.add_argument("path", nargs="?", type=Path)
    progress.add_argument("--task-id", default=None)
    progress.add_argument("--lease-id", required=True)
    progress.add_argument("--generation", type=int, default=None)
    progress.add_argument("--fence-token", default=None)
    progress.add_argument(
        "--phase",
        choices=tuple(sorted(ROUND_PHASES - {"released"})),
        default=None,
    )
    progress.add_argument("--milestone", default=None)
    progress.add_argument("--evidence-ref", action="append", default=None)
    add_json_argument(progress)
    progress.set_defaults(func=continuation_progress_command)

    effect = subparsers.add_parser(
        "effect",
        help="record bounded write-ahead identities and durable external-effect observations",
    )
    effect_subparsers = effect.add_subparsers(dest="continuation_effect_command", required=True)

    prepare = effect_subparsers.add_parser(
        "prepare",
        help="prepare one deterministic external-effect identity before executing it",
    )
    prepare.add_argument("path", nargs="?", type=Path)
    prepare.add_argument("--task-id", default=None)
    prepare.add_argument("--lease-id", required=True)
    prepare.add_argument("--generation", type=int, default=None)
    prepare.add_argument("--fence-token", default=None)
    prepare.add_argument("--key", required=True)
    prepare.add_argument("--kind", required=True)
    prepare.add_argument("--external-id", default=None)
    prepare.add_argument("--milestone", default=None)
    prepare.add_argument("--evidence-ref", action="append", default=None)
    add_json_argument(prepare)
    prepare.set_defaults(func=continuation_effect_prepare_command)

    update = effect_subparsers.add_parser(
        "update",
        help="record an observed durable effect status/milestone/evidence update",
    )
    update.add_argument("path", nargs="?", type=Path)
    update.add_argument("--task-id", default=None)
    update.add_argument("--lease-id", required=True)
    update.add_argument("--generation", type=int, default=None)
    update.add_argument("--fence-token", default=None)
    update.add_argument("--key", required=True)
    update.add_argument(
        "--status",
        choices=tuple(sorted(EFFECT_STATUSES)),
        default=None,
    )
    update.add_argument("--external-id", default=None)
    update.add_argument("--milestone", default=None)
    update.add_argument("--evidence-ref", action="append", default=None)
    add_json_argument(update)
    update.set_defaults(func=continuation_effect_update_command)

    list_parser = effect_subparsers.add_parser(
        "list",
        help="list compact durable effect records for reconciliation/reuse decisions",
    )
    list_parser.add_argument("path", nargs="?", type=Path)
    list_parser.add_argument("--task-id", default=None)
    add_json_argument(list_parser)
    list_parser.set_defaults(func=continuation_effect_list_command)

    reconcile = subparsers.add_parser(
        "reconcile",
        help="classify an interrupted round, including bounded dirty ownership, and optionally record an auditable recovery decision",
        description="Classify an interrupted round using lease/effect/workspace ownership evidence and optionally record an auditable recovery decision.",
    )
    reconcile.add_argument("path", nargs="?", type=Path)
    reconcile.add_argument("--task-id", default=None)
    reconcile.add_argument("--owner-ended", action="store_true")
    reconcile.add_argument("--accept-head", default=None)
    reconcile.add_argument("--evidence-ref", action="append", default=None)
    reconcile.add_argument("--reason", default=None)
    reconcile.add_argument("--record", action="store_true")
    add_json_argument(reconcile)
    reconcile.set_defaults(func=continuation_reconcile_command)

    recover = subparsers.add_parser(
        "recover",
        help="fence an interrupted owner and transfer evidence-backed WIP using one eligible reconcile receipt",
        description="Fence an interrupted owner and transfer evidence-backed write intent/WIP ownership using one eligible reconcile receipt.",
    )
    recover.add_argument("path", nargs="?", type=Path)
    recover.add_argument("--task-id", default=None)
    recover.add_argument("--reconcile-id", required=True)
    recover.add_argument("--runner-id", required=True)
    recover.add_argument("--ttl-minutes", type=int, default=None)
    add_json_argument(recover)
    recover.set_defaults(func=continuation_recover_command)


continuation_init_command = continuation_workspace_commands.continuation_init_command
continuation_workspace_status_command = continuation_workspace_commands.continuation_workspace_status_command
continuation_workspace_intent_command = continuation_workspace_commands.continuation_workspace_intent_command
continuation_workspace_refresh_command = continuation_workspace_commands.continuation_workspace_refresh_command
register_workspace_parsers = continuation_workspace_commands.register_workspace_parsers


__all__ = [
    "continuation_assert_owner_command",
    "continuation_checkpoint_command",
    "continuation_claim_command",
    "continuation_doctor_command",
    "continuation_effect_list_command",
    "continuation_effect_prepare_command",
    "continuation_effect_update_command",
    "continuation_heartbeat_command",
    "continuation_init_command",
    "continuation_issue_command",
    "continuation_pause_command",
    "continuation_progress_command",
    "continuation_prompt_command",
    "continuation_reconcile_command",
    "continuation_recover_command",
    "continuation_release_command",
    "continuation_renew_command",
    "continuation_resume_command",
    "continuation_workspace_intent_command",
    "continuation_workspace_refresh_command",
    "continuation_workspace_status_command",
    "register_round_effect_parsers",
    "register_workspace_parsers",
]
