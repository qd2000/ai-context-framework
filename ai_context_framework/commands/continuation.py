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
from ai_context_framework import (
    continuation_coordination,
    continuation_effect_archive,
    continuation_inventory,
    continuation_recovery,
    continuation_rounds,
    continuation_workspace,
)
from ai_context_framework.commands import continuation_parsers
from ai_context_framework.commands import continuation_coordination as continuation_coordination_commands
from ai_context_framework.commands import continuation_directives as continuation_directive_commands
from ai_context_framework.commands import continuation_issue as continuation_issue_commands
from ai_context_framework.commands import continuation_recovery as continuation_recovery_commands
from ai_context_framework.commands import continuation_workspace as continuation_workspace_commands
from ai_context_framework.observability import (
    atomic_write_text,
    usage_project_dir,
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

DEFAULT_INTERVAL_MINUTES = continuation_workspace_commands.DEFAULT_INTERVAL_MINUTES
DEFAULT_LEASE_TTL_MINUTES = continuation_workspace_commands.DEFAULT_LEASE_TTL_MINUTES
DEFAULT_RENEW_INTERVAL_MINUTES = continuation_workspace_commands.DEFAULT_RENEW_INTERVAL_MINUTES
DEFAULT_HEARTBEAT_INTERVAL_MINUTES = continuation_workspace_commands.DEFAULT_HEARTBEAT_INTERVAL_MINUTES
DEFAULT_STALE_AFTER_MINUTES = continuation_workspace_commands.DEFAULT_STALE_AFTER_MINUTES
MAX_LEASE_TTL_MINUTES = continuation_workspace_commands.MAX_LEASE_TTL_MINUTES
TIMING_PROFILES = continuation_workspace_commands.TIMING_PROFILES
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
ROLLING_LIST_FIELDS = frozenset({"completed", "evidence_refs", "verification"})


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
        "coordination": directory / "coordination.json",
        "workspace": directory / "workspace.json",
        "reconcile": directory / "reconcile.json",
        "recovery": directory / "last_recovery.json",
        "directives": directory / "directives.json",
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
        journal = continuation_rounds.empty_effect_journal(str(control["task_id"]))
        try:
            continuation_effect_archive.validate_history(path, journal, task_id=str(control["task_id"]))
        except continuation_rounds.ContinuationRoundError as exc:
            raise _round_error(exc) from exc
        return journal
    try:
        payload = _read_json(path, label="effect_journal")
        journal = continuation_rounds.validate_effect_journal(payload, task_id=str(control["task_id"]))
        continuation_effect_archive.validate_history(path, journal, task_id=str(control["task_id"]))
        return journal
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

    effect_archives = continuation_effect_archive.archive_paths(effect_path)
    if effect_path.exists() or effect_archives:
        try:
            effects = _load_effect_journal(paths, control)
            _, effect_summary, archive_paths = continuation_effect_archive.list_history(effect_path, effects, task_id=str(control["task_id"]))
            effect_snapshot = {
                "state": "valid",
                "path": str(effect_path),
                "summary": effect_summary,
                "archive_paths": archive_paths,
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


def _compact_state_lists(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep compact state fields inside their rolling bounded window.

    Older ACF releases could append beyond ``MAX_LIST_ITEMS`` and then make
    the same state unreadable on the next command.  History-like state lists
    are compact recovery summaries rather than the authoritative history
    journal, so retain their most recent bounded window.  Semantic lists such
    as constraints, open questions and plan refs must never be silently
    dropped; they remain strict and fail closed if an old state exceeds the
    bound.
    """

    state = dict(payload)
    # Capacity repair must not become a way to hide an invalid old entry by
    # trimming it before normal state validation sees it.  Scan the complete
    # pre-compaction payload for the safety properties that apply to every
    # individual item, then relax only the aggregate list-count bound.
    _reject_forbidden_state_keys(state)
    for field in LIST_FIELDS:
        values = state.get(field, [])
        if not isinstance(values, list):
            continue
        for item in values:
            encoded = json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")
            if len(encoded) > MAX_TEXT_BYTES:
                raise ContinuationError(f"{field} item is too large", code="state_invalid")
        if field in ROLLING_LIST_FIELDS and len(values) > MAX_LIST_ITEMS:
            state[field] = values[-MAX_LIST_ITEMS:]
    return state


def _write_state(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    state = _validate_state(_compact_state_lists(payload))
    _write_json(path, state)
    return state


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
    renew = control.get("renew_interval_minutes")
    if isinstance(renew, bool) or not isinstance(renew, int) or renew < 1:
        raise ContinuationError("invalid control field: renew_interval_minutes", code="control_invalid")
    control.setdefault(
        "heartbeat_interval_minutes",
        min(DEFAULT_HEARTBEAT_INTERVAL_MINUTES, max(1, renew // 2)),
    )
    control.setdefault("stale_after_minutes", renew)
    timing_source = {
        field: control.get(field)
        for field in (
            "interval_minutes",
            "lease_ttl_minutes",
            "renew_interval_minutes",
            "heartbeat_interval_minutes",
            "stale_after_minutes",
        )
    }
    try:
        timing = continuation_workspace_commands.validate_timing_values(timing_source)
    except ContinuationError as exc:
        raise ContinuationError(str(exc), code="control_invalid") from exc
    control.update(timing)
    timing_profile = str(control.get("timing_profile") or "").strip()
    if not timing_profile:
        timing_profile = next(
            (name for name, profile_values in TIMING_PROFILES.items() if timing == profile_values),
            "legacy",
        )
        control["timing_profile"] = timing_profile
    elif timing_profile not in {*TIMING_PROFILES, "custom", "legacy"}:
        raise ContinuationError("invalid control field: timing_profile", code="control_invalid")
    if control.get("history_policy") != "local_first":
        raise ContinuationError("continuation history_policy must be local_first", code="control_invalid")
    generation = control.get("generation", 0)
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise ContinuationError("invalid control field: generation", code="control_invalid")
    return control


def _load_state(paths: Mapping[str, Path]) -> dict[str, Any]:
    return _validate_state(_compact_state_lists(_read_json(paths["state"], label="state")))


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
    stale_after_seconds = int(control["stale_after_minutes"]) * 60
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


def _assert_lease_owner_with_activity(
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    lease_id: str,
    fence_token: str | None,
    generation: int | None,
) -> dict[str, Any]:
    lease = _assert_lease_owner(
        snapshot,
        lease_id=lease_id,
        fence_token=fence_token,
        generation=generation,
    )
    continuation_coordination_commands.record_authenticated_owner_activity(
        paths,
        control,
        lease,
        now=_iso(),
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
    workspace_unclassified_paths = list(workspace.get("unclassified_paths") or [])
    workspace_claimable = (
        (workspace["state"] == "valid" and not workspace_has_conflicts)
        or (workspace["state"] == "absent" and not workspace_unclassified_paths)
    )
    can_claim = (
        not identity_errors
        and workspace_claimable
        and pause is None
        and lease["state"] in {"absent", "expired"}
        and (state["status"] in RUNNABLE_STATUSES or recoverable_expired)
    )
    blocked: list[str] = list(identity_errors)
    if workspace["state"] == "absent" and workspace_unclassified_paths:
        blocked.append("workspace_provenance_missing")
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


def _retire_exact_state_items(
    existing: Iterable[Any],
    retirements: Iterable[str],
    *,
    field: str,
) -> tuple[list[Any], list[str]]:
    """Retire exact current semantic-state entries without guessing identity.

    ``constraints`` and ``open_questions`` are current compact authority hints,
    not append-only history.  When newer authority invalidates one of them, an
    authenticated checkpoint may retire the exact old text.  Exact matching is
    deliberate: fuzzy or substring removal could silently discard a different
    still-authoritative constraint/question.
    """

    result = list(existing)
    removed: list[str] = []
    for raw_value in _append_unique([], retirements):
        value = _validate_text(raw_value, field=field)
        if value not in result:
            raise ContinuationError(
                f"{field} item is not current: {value}",
                code="state_item_not_found",
            )
        result.remove(value)
        removed.append(value)
    return result, removed


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
        paths = _paths(root, args.task_id)
        compatibility = continuation_inventory.inspect_task_dir(
            paths["directory"],
            contracts=continuation_workspace_commands.continuation_schema_contract(),
        )
        result["status"] = "healthy" if result["ok"] else "invalid"
        result["next_action"] = result["state"]["next_action"]
        result["state_compatibility"] = {
            "compatibility": compatibility["compatibility"],
            "migration_required": compatibility["migration_required"],
            "migration_files": compatibility["migration_files"],
            "blocked_files": compatibility["blocked_files"],
            "schemas": compatibility["schemas"],
        }
        next_actions: list[str] = []
        if bool(compatibility["migration_required"]):
            next_actions.append(
                "Run `acf continuation migrate ... --dry-run --json` with no active lease, review the history-preserving plan, then apply it explicitly if appropriate."
            )
        if "workspace_provenance_missing" in result["blocked_reasons"]:
            next_actions.extend(
                [
                    "Review every path in workspace.unclassified_paths, then run `acf continuation workspace adopt` with an explicit `--task-owned` or `--baseline-external` classification for each path plus durable evidence refs.",
                    "If any changed path cannot be attributed confidently, do not adopt it; preserve the worktree and keep recovery fail-closed until provenance is resolved.",
                ]
            )
        result["next_actions"] = next_actions
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
            directive_context = continuation_directive_commands.directive_context(paths, control)
            continuation_directive_commands.observe_directive_context(lease, directive_context)
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
            workspace_snapshot = continuation_workspace_commands.workspace_current_snapshot(root)
            if workspace_manifest is None:
                if workspace_snapshot["entries"]:
                    raise ContinuationError(
                        "legacy continuation has changed paths without ownership provenance",
                        code="workspace_provenance_missing",
                        exit_code=3,
                        details={"paths": [entry["path"] for entry in workspace_snapshot["entries"]]},
                    )
                try:
                    workspace_manifest = continuation_workspace.new_manifest(
                        task_id=str(control["task_id"]),
                        snapshot=workspace_snapshot,
                        now=_iso(now),
                    )
                except continuation_workspace.ContinuationWorkspaceError as exc:
                    raise continuation_workspace_commands.workspace_error(exc) from exc
            try:
                workspace_manifest = continuation_workspace.begin_generation(
                    workspace_manifest,
                    task_id=str(control["task_id"]),
                    generation=generation,
                    snapshot=workspace_snapshot,
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
                    state["verification"], ["Recovered an expired lease after identity/workspace ownership checks."]
                )
            state = _write_state(paths["state"], state)
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
                "timing_profile": control["timing_profile"],
                "heartbeat_interval_minutes": control["heartbeat_interval_minutes"],
                "stale_after_minutes": control["stale_after_minutes"],
                "renew_interval_minutes": control["renew_interval_minutes"],
                "directive_context": directive_context,
            }

    return _guarded(args, "continuation claim", operation)


def continuation_assert_owner_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            snapshot = _lease_snapshot(paths, control)
            lease = _assert_lease_owner_with_activity(
                paths,
                control,
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
            lease = _assert_lease_owner_with_activity(
                paths,
                control,
                snapshot,
                lease_id=args.lease_id,
                fence_token=args.fence_token,
                generation=args.generation,
            )
            git = _git_identity(root)
            if git["branch"] != control["expected_branch"] or git["detached"]:
                raise ContinuationError("Git identity changed during active round", code="workspace_mismatch")
            directive_context = continuation_directive_commands.directive_context(paths, control)
            directive_signal = continuation_directive_commands.observe_directive_context(
                lease,
                directive_context,
            )
            lease["last_heartbeat_at"] = _iso()
            _write_json(paths["lease"], lease)
            return {
                "status": "heartbeat_recorded",
                "lease": _public_lease(lease),
                "generation": lease.get("generation"),
                "directive_signal": directive_signal,
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
            lease = _assert_lease_owner_with_activity(
                paths,
                control,
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
            lease = _assert_lease_owner_with_activity(
                paths,
                control,
                snapshot,
                lease_id=args.lease_id,
                fence_token=args.fence_token,
                generation=args.generation,
            )
            generation = _require_fenced_generation(lease)
            journal = _load_effect_journal(paths, control)
            try:
                journal, effect, created, summary, rollover = continuation_effect_archive.prepare_with_rollover(
                    paths["effects"], journal,
                    task_id=str(control["task_id"]), generation=generation,
                    logical_key=args.key, kind=args.kind, external_id=args.external_id,
                    milestone=args.milestone, evidence_refs=args.evidence_ref or [], now=_iso(),
                )
            except continuation_rounds.ContinuationRoundError as exc:
                raise _round_error(exc) from exc
            return {
                "status": "effect_prepared" if created else "effect_exists",
                "created": created,
                "effect": effect,
                "summary": summary,
                "rollover": rollover,
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
            lease = _assert_lease_owner_with_activity(
                paths,
                control,
                snapshot,
                lease_id=args.lease_id,
                fence_token=args.fence_token,
                generation=args.generation,
            )
            generation = _require_fenced_generation(lease)
            journal = _load_effect_journal(paths, control, require_existing=True)
            try:
                journal, effect, summary = continuation_effect_archive.update_across_history(
                    paths["effects"],
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
            return {
                "status": "effect_updated",
                "effect": effect,
                "summary": summary,
            }

    return _guarded(args, "continuation effect update", operation)
def continuation_effect_list_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            journal = _load_effect_journal(paths, control)
            try:
                effects, summary, archive_paths = continuation_effect_archive.list_history(paths["effects"], journal, task_id=str(control["task_id"]))
            except continuation_rounds.ContinuationRoundError as exc:
                raise _round_error(exc) from exc
            return {
                "status": "listed",
                "effects": effects,
                "summary": summary,
                "path": str(paths["effects"]),
                "archive_paths": archive_paths,
            }

    return _guarded(args, "continuation effect list", operation)
def continuation_recover_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            (
                receipt,
                status,
                observation,
                effect_journal,
                effect_reconciliations,
            ) = continuation_recovery_commands.validate_recovery_inputs(
                root,
                paths,
                control,
                task_id=args.task_id,
                reconcile_id=str(args.reconcile_id),
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
                effect_reconciliations=effect_reconciliations,
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

            reconciled_effect_journal, reconciled_effects = (
                continuation_recovery_commands.apply_recovery_effect_reconciliations(
                    effect_journal,
                    task_id=str(control["task_id"]),
                    generation=generation,
                    reconciliations=effect_reconciliations,
                    reconcile_id=str(receipt["receipt_id"]),
                    now=_iso(now),
                )
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

            coordination_state = continuation_coordination_commands.load_coordination_state(
                paths,
                control,
                now=_iso(now),
            )
            challenge_resolution = None
            if isinstance(old_generation, int) and not isinstance(old_generation, bool):
                try:
                    coordination_state, challenge_resolution = continuation_coordination.resolve_recovery(
                        coordination_state,
                        task_id=str(control["task_id"]),
                        owner_generation=old_generation,
                        recovery_generation=generation,
                        reconcile_receipt_id=str(receipt["receipt_id"]),
                        now=_iso(now),
                    )
                except continuation_coordination.ContinuationCoordinationError as exc:
                    raise continuation_coordination_commands.coordination_error(exc) from exc

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
            # Validate/compact the final continuation state before any of the
            # generation-transfer files are persisted.  Older releases wrote
            # control/lease/round/workspace first and could therefore leave a
            # half-committed fresh lease when the final state write rejected
            # an over-capacity verification list.
            state = _validate_state(_compact_state_lists(state))
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
                "reconciled_effect_digest": continuation_recovery.json_digest(reconciled_effect_journal),
                "effect_reconciliations": [str(effect["logical_key"]) for effect in reconciled_effects],
                "workspace_digest": workspace_summary["manifest_digest"],
                "coordination_digest": observation["coordination_digest"],
                "challenge_resolution": challenge_resolution,
            }
            _write_json(paths["control"], control)
            _write_json(paths["lease"], lease)
            _write_json(paths["rounds"], round_journal)
            if effect_reconciliations:
                _write_json(paths["effects"], reconciled_effect_journal)
            _write_json(paths["workspace"], workspace_manifest)
            state = _write_state(paths["state"], state)
            if challenge_resolution is not None:
                _write_json(paths["coordination"], coordination_state)
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
                "timing_profile": control["timing_profile"],
                "heartbeat_interval_minutes": control["heartbeat_interval_minutes"],
                "stale_after_minutes": control["stale_after_minutes"],
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
            lease = _assert_lease_owner_with_activity(
                paths,
                control,
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
            directive_context = continuation_directive_commands.directive_context(paths, control)
            directive_signal = continuation_directive_commands.observe_directive_context(
                lease,
                directive_context,
            )
            lease["last_heartbeat_at"] = _iso(now)
            lease["last_renew_at"] = _iso(now)
            lease["expires_at"] = _iso(now + timedelta(minutes=ttl))
            _write_json(paths["lease"], lease)
            return {
                "status": "renewed",
                "lease": _public_lease(lease),
                "directive_signal": directive_signal,
            }

    return _guarded(args, "continuation renew", operation)


def continuation_checkpoint_command(args: argparse.Namespace) -> int:
    def operation() -> dict[str, Any]:
        root = _workspace_root(args.path)
        paths = _paths(root, args.task_id)
        with _state_lock(paths["lock"]):
            control = _load_control(paths, root)
            snapshot = _lease_snapshot(paths, control)
            _assert_lease_owner_with_activity(
                paths,
                control,
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
            superseded_constraints = args.supersede_constraint or []
            resolved_open_questions = args.resolve_open_question or []
            if (superseded_constraints or resolved_open_questions) and not args.evidence_ref:
                raise ContinuationError(
                    "retiring a current constraint/open question requires --evidence-ref",
                    code="state_authority_evidence_required",
                )
            state["constraints"], retired_constraints = _retire_exact_state_items(
                state.get("constraints", []),
                superseded_constraints,
                field="constraint",
            )
            state["open_questions"], retired_open_questions = _retire_exact_state_items(
                state.get("open_questions", []),
                resolved_open_questions,
                field="open_question",
            )
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
            state = _write_state(paths["state"], state)
            return {
                "status": "checkpointed",
                "state": state,
                "next_action": state["next_action"],
                "retired_state_items": {
                    "constraints": retired_constraints,
                    "open_questions": retired_open_questions,
                },
            }

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
            workspace_snapshot = continuation_workspace_commands.workspace_current_snapshot(root)
            workspace_summary: dict[str, Any] | None = None
            workspace_release_blocked = False
            workspace_block_reason: str | None = None
            if workspace_manifest is not None:
                try:
                    workspace_manifest = continuation_workspace.handoff_generation(
                        workspace_manifest,
                        task_id=str(control["task_id"]),
                        snapshot=workspace_snapshot,
                        now=_iso(),
                    )
                except continuation_workspace.ContinuationWorkspaceError as exc:
                    raise continuation_workspace_commands.workspace_error(exc) from exc
                workspace_summary = continuation_workspace.summary(
                    workspace_manifest,
                    task_id=str(control["task_id"]),
                )
                workspace_release_blocked = bool(workspace_summary["has_conflicts"])
                if workspace_release_blocked:
                    workspace_block_reason = "workspace_conflict"
            elif workspace_snapshot["entries"]:
                workspace_release_blocked = True
                workspace_block_reason = "workspace_provenance_missing"
            pause = _read_json(paths["pause"], label="pause") if paths["pause"].exists() else None
            outcome = "released"
            if pause is not None:
                state["status"] = "paused"
                state["next_action"] = "Wait for an explicit continuation resume action."
                outcome = "released_to_paused"
            elif workspace_release_blocked:
                state["status"] = "reconciling"
                state["next_action"] = "Reconcile ambiguous workspace ownership before another round."
                state["verification"] = _append_unique(
                    state["verification"],
                    [f"Release failed closed because {workspace_block_reason or 'workspace ownership is ambiguous'}."],
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
            state = _write_state(paths["state"], state)
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
            coordination_resolution = continuation_coordination_commands.record_owner_release(
                paths,
                control,
                lease,
                now=release_now,
            )
            paths["lease"].unlink(missing_ok=False)
            return {
                "ok": outcome == "released",
                "status": outcome,
                "state": state,
                "receipt": receipt,
                "round": finished_round,
                "workspace": workspace_summary,
                "coordination_resolution": coordination_resolution,
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
                state = _write_state(paths["state"], state)
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
            state = _write_state(paths["state"], state)
            paths["pause"].unlink(missing_ok=False)
            return {"status": "ready", "state": state, "next_action": state["next_action"]}

    return _guarded(args, "continuation resume", operation)


def register_round_effect_parsers(subparsers, add_json_argument) -> None:
    continuation_directive_commands.register_directive_parser(subparsers, add_json_argument)
    continuation_parsers.register_round_effect_parsers(
        subparsers,
        add_json_argument,
        round_phases=ROUND_PHASES,
        effect_statuses=EFFECT_STATUSES,
        progress_command=continuation_progress_command,
        effect_prepare_command=continuation_effect_prepare_command,
        effect_update_command=continuation_effect_update_command,
        effect_list_command=continuation_effect_list_command,
        register_recovery_parsers=continuation_recovery_commands.register_recovery_parsers,
    )


continuation_init_command = continuation_workspace_commands.continuation_init_command
continuation_configure_command = continuation_workspace_commands.continuation_configure_command
continuation_prompt_command = continuation_workspace_commands.continuation_prompt_command
continuation_workspace_adopt_command = continuation_workspace_commands.continuation_workspace_adopt_command
continuation_workspace_status_command = continuation_workspace_commands.continuation_workspace_status_command
continuation_workspace_intent_command = continuation_workspace_commands.continuation_workspace_intent_command
continuation_workspace_refresh_command = continuation_workspace_commands.continuation_workspace_refresh_command
continuation_coordination_status_command = continuation_coordination_commands.continuation_coordination_status_command
continuation_coordination_attempt_command = continuation_coordination_commands.continuation_coordination_attempt_command
continuation_coordination_challenge_command = continuation_coordination_commands.continuation_coordination_challenge_command
continuation_reconcile_command = continuation_recovery_commands.continuation_reconcile_command
continuation_issue_command = continuation_issue_commands.continuation_issue_command
register_workspace_parsers = continuation_workspace_commands.register_workspace_parsers
register_configure_parser = continuation_workspace_commands.register_configure_parser
register_coordination_parsers = continuation_coordination_commands.register_coordination_parsers
register_issue_parser = continuation_issue_commands.register_issue_parser


__all__ = [
    "continuation_assert_owner_command",
    "continuation_checkpoint_command",
    "continuation_claim_command",
    "continuation_configure_command",
    "continuation_coordination_attempt_command",
    "continuation_coordination_challenge_command",
    "continuation_coordination_status_command",
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
    "continuation_workspace_adopt_command",
    "continuation_workspace_intent_command",
    "continuation_workspace_refresh_command",
    "continuation_workspace_status_command",
    "register_round_effect_parsers",
    "register_coordination_parsers",
    "register_configure_parser",
    "register_workspace_parsers",
    "register_issue_parser",
]
