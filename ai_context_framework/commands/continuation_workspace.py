"""CLI adapter for bounded continuation workspace ownership.

The durable workspace model lives in :mod:`ai_context_framework.continuation_workspace`.
This module keeps the command wiring and Workstream-scope integration out of the
main continuation controller so both surfaces remain small enough to review.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping

from ai_context_framework import (
    continuation_coordination,
    continuation_directives,
    continuation_inventory,
    continuation_recovery,
    continuation_rounds,
    continuation_workspace,
)
from ai_context_framework.automation_contracts import (
    automation_prompt_execution_contract,
    writer_scheduler_wrapper_contract,
)
from ai_context_framework.commands import continuation_directives as continuation_directive_commands
from ai_context_framework.front_matter import parse_front_matter, split_typed_scope, validate_front_matter
from ai_context_framework.git_support import discover_git_project
from ai_context_framework.observability import acf_home, atomic_write_text
from ai_context_framework.runtime_parts.archive_workstream import (
    normalize_scope_path,
    read_workstream_detail,
    workstream_archive_dir,
    workstream_front_matter_schema,
)


DEFAULT_INTERVAL_MINUTES = 60
DEFAULT_LEASE_TTL_MINUTES = 120
DEFAULT_RENEW_INTERVAL_MINUTES = 30
DEFAULT_HEARTBEAT_INTERVAL_MINUTES = 10
DEFAULT_STALE_AFTER_MINUTES = 30
LONG_RUNNING_LEASE_TTL_MINUTES = 180
LONG_RUNNING_RENEW_INTERVAL_MINUTES = 45
LONG_RUNNING_HEARTBEAT_INTERVAL_MINUTES = 10
LONG_RUNNING_STALE_AFTER_MINUTES = 25
MAX_LEASE_TTL_MINUTES = 24 * 60
FENCE_TOKEN_FILE_ENV = "ACF_CONTINUATION_FENCE_TOKEN_FILE"
MAX_FENCE_TOKEN_FILE_BYTES = 4096

TIMING_PROFILES: dict[str, dict[str, int]] = {
    "standard": {
        "interval_minutes": DEFAULT_INTERVAL_MINUTES,
        "lease_ttl_minutes": DEFAULT_LEASE_TTL_MINUTES,
        "renew_interval_minutes": DEFAULT_RENEW_INTERVAL_MINUTES,
        "heartbeat_interval_minutes": DEFAULT_HEARTBEAT_INTERVAL_MINUTES,
        "stale_after_minutes": DEFAULT_STALE_AFTER_MINUTES,
    },
    "long-running": {
        "interval_minutes": DEFAULT_INTERVAL_MINUTES,
        "lease_ttl_minutes": LONG_RUNNING_LEASE_TTL_MINUTES,
        "renew_interval_minutes": LONG_RUNNING_RENEW_INTERVAL_MINUTES,
        "heartbeat_interval_minutes": LONG_RUNNING_HEARTBEAT_INTERVAL_MINUTES,
        "stale_after_minutes": LONG_RUNNING_STALE_AFTER_MINUTES,
    },
}


def continuation_schema_contract() -> dict[str, dict[str, Any]]:
    """Return the single machine-readable continuation state compatibility contract."""

    core = _continuation()
    return {
        "control.json": {"current": [core.CONTROL_SCHEMA], "required": True},
        "state.json": {"current": [core.STATE_SCHEMA], "required": True},
        "lease.json": {"current": [core.LEASE_SCHEMA], "required": False},
        "pause.json": {"current": [core.PAUSE_SCHEMA], "required": False},
        "last_run.json": {"current": [core.RECEIPT_SCHEMA], "required": False},
        "rounds.json": {
            "current": [continuation_rounds.ROUND_JOURNAL_SCHEMA],
            "required": False,
        },
        "effects.json": {
            "current": [continuation_rounds.EFFECT_JOURNAL_SCHEMA],
            "required": False,
        },
        "coordination.json": {
            "current": [continuation_coordination.COORDINATION_SCHEMA],
            "required": False,
        },
        "workspace.json": {
            "current": [continuation_workspace.WORKSPACE_SCHEMA],
            "legacy_migratable": [
                continuation_workspace.LEGACY_WORKSPACE_SCHEMA,
                continuation_workspace.LEGACY_WORKSPACE_SCHEMA_V2,
            ],
            "required": False,
        },
        "reconcile.json": {
            "current": [continuation_recovery.RECONCILE_SCHEMA],
            "required": False,
        },
        "last_recovery.json": {
            "current": [continuation_recovery.RECOVERY_SCHEMA],
            "required": False,
        },
        "last_migration.json": {
            "current": [continuation_inventory.MIGRATION_RECEIPT_SCHEMA],
            "required": False,
        },
        "directives.json": {
            "current": [continuation_directives.DIRECTIVE_JOURNAL_SCHEMA],
            "required": False,
        },
    }


def validate_timing_values(values: Mapping[str, Any]) -> dict[str, int]:
    core = _continuation()
    timing: dict[str, int] = {}
    for field in (
        "interval_minutes",
        "lease_ttl_minutes",
        "renew_interval_minutes",
        "heartbeat_interval_minutes",
        "stale_after_minutes",
    ):
        value = values.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise core.ContinuationError(f"invalid control field: {field}", code="timing_invalid")
        timing[field] = value
    if timing["lease_ttl_minutes"] > MAX_LEASE_TTL_MINUTES:
        raise core.ContinuationError("lease TTL exceeds safety maximum", code="timing_invalid")
    if timing["renew_interval_minutes"] >= timing["lease_ttl_minutes"]:
        raise core.ContinuationError("renew interval must be shorter than lease TTL", code="timing_invalid")
    if timing["heartbeat_interval_minutes"] > timing["stale_after_minutes"]:
        raise core.ContinuationError(
            "heartbeat recommendation must not exceed stale threshold",
            code="timing_invalid",
        )
    if timing["stale_after_minutes"] >= timing["lease_ttl_minutes"]:
        raise core.ContinuationError("stale threshold must be shorter than lease TTL", code="timing_invalid")
    return timing


def timing_values(
    *,
    profile: str | None,
    interval_minutes: int | None,
    lease_ttl_minutes: int | None,
    renew_interval_minutes: int | None,
    heartbeat_interval_minutes: int | None,
    stale_after_minutes: int | None,
    base: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, int]]:
    requested_profile = str(profile or "").strip()
    if requested_profile:
        if requested_profile not in TIMING_PROFILES:
            raise _continuation().ContinuationError(
                f"unsupported timing profile: {requested_profile}", code="timing_invalid"
            )
        values: dict[str, Any] = dict(TIMING_PROFILES[requested_profile])
    elif base is not None:
        values = {
            field: base[field]
            for field in (
                "interval_minutes",
                "lease_ttl_minutes",
                "renew_interval_minutes",
                "heartbeat_interval_minutes",
                "stale_after_minutes",
            )
        }
    else:
        values = dict(TIMING_PROFILES["standard"])
    for field, value in {
        "interval_minutes": interval_minutes,
        "lease_ttl_minutes": lease_ttl_minutes,
        "renew_interval_minutes": renew_interval_minutes,
        "heartbeat_interval_minutes": heartbeat_interval_minutes,
        "stale_after_minutes": stale_after_minutes,
    }.items():
        if value is not None:
            values[field] = int(value)
    timing = validate_timing_values(values)
    matched_profile = next(
        (name for name, profile_values in TIMING_PROFILES.items() if timing == profile_values),
        "custom",
    )
    return matched_profile, timing


def _continuation():
    # Imported lazily to avoid a module-import cycle.  The main continuation
    # controller imports this adapter for backwards-compatible command aliases.
    from ai_context_framework.commands import continuation

    return continuation


def _fence_token_file_from_env() -> Path | None:
    raw = os.environ.get(FENCE_TOKEN_FILE_ENV)
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        core = _continuation()
        raise core.ContinuationError(
            f"{FENCE_TOKEN_FILE_ENV} cannot be empty",
            code="fence_token_transport_invalid",
        )
    return Path(value).expanduser()


def resolve_fence_token(args: argparse.Namespace) -> str | None:
    """Resolve a fenced-owner credential without requiring it in argv."""

    literal = getattr(args, "fence_token", None)
    if literal:
        return str(literal)
    path = _fence_token_file_from_env()
    if path is None:
        return None
    core = _continuation()
    try:
        if not path.is_file():
            raise core.ContinuationError(
                "configured fence token file is not a regular file",
                code="fence_token_transport_unavailable",
                details={"environment": FENCE_TOKEN_FILE_ENV, "path": str(path)},
                exit_code=3,
            )
        size = path.stat().st_size
        if size < 1 or size > MAX_FENCE_TOKEN_FILE_BYTES:
            raise core.ContinuationError(
                "configured fence token file has an invalid size",
                code="fence_token_transport_invalid",
                details={"environment": FENCE_TOKEN_FILE_ENV, "path": str(path)},
                exit_code=3,
            )
        value = path.read_text(encoding="utf-8").strip()
    except core.ContinuationError:
        raise
    except OSError as exc:
        raise core.ContinuationError(
            "configured fence token file could not be read",
            code="fence_token_transport_unavailable",
            details={"environment": FENCE_TOKEN_FILE_ENV, "path": str(path)},
            exit_code=3,
        ) from exc
    if not value:
        raise core.ContinuationError(
            "configured fence token file is empty",
            code="fence_token_transport_invalid",
            details={"environment": FENCE_TOKEN_FILE_ENV, "path": str(path)},
            exit_code=3,
        )
    return value


def deliver_fence_token(fence_token: str) -> dict[str, Any]:
    """Return the legacy token or externalize it to an opt-in local file.

    Delivery happens before lease/control generation state is committed, so a
    bad credential transport cannot create a fresh owner that the caller cannot
    authenticate.  The plaintext file is caller-controlled and stays outside
    canonical continuation state; only the token hash is durable there.
    """

    path = _fence_token_file_from_env()
    if path is None:
        return {"fence_token": fence_token}
    core = _continuation()
    try:
        parent = path.parent
        if not parent.exists() or not parent.is_dir():
            raise core.ContinuationError(
                "configured fence token file parent does not exist",
                code="fence_token_transport_unavailable",
                details={"environment": FENCE_TOKEN_FILE_ENV, "path": str(path)},
            )
        atomic_write_text(path, fence_token + "\n")
        try:
            os.chmod(path, 0o600)
        except OSError:
            # Windows ACLs are inherited from the caller-controlled parent;
            # chmod is only a best-effort narrowing on platforms that honor it.
            pass
    except core.ContinuationError:
        raise
    except OSError as exc:
        raise core.ContinuationError(
            "configured fence token file could not be written",
            code="fence_token_transport_unavailable",
            details={"environment": FENCE_TOKEN_FILE_ENV, "path": str(path)},
        ) from exc
    return {
        "fence_token": None,
        "fence_token_transport": "file",
        "fence_token_file": str(path),
        "fence_token_environment": FENCE_TOKEN_FILE_ENV,
    }


def workspace_error(exc: continuation_workspace.ContinuationWorkspaceError):
    core = _continuation()
    return core.ContinuationError(str(exc), code=exc.code)


def load_workspace_manifest(
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
    *,
    require_existing: bool = False,
) -> dict[str, Any] | None:
    core = _continuation()
    path = paths["workspace"]
    if not path.exists():
        if require_existing:
            raise core.ContinuationError(
                "workspace ownership manifest is missing",
                code="workspace_manifest_missing",
                exit_code=3,
            )
        return None
    try:
        payload = core._read_json(path, label="workspace_manifest")
        return continuation_workspace.validate_manifest(
            payload,
            task_id=str(control["task_id"]),
        )
    except continuation_workspace.ContinuationWorkspaceError as exc:
        raise workspace_error(exc) from exc


def workspace_current_snapshot(root: Path) -> dict[str, Any]:
    try:
        return continuation_workspace.git_snapshot(root)
    except continuation_workspace.ContinuationWorkspaceError as exc:
        raise workspace_error(exc) from exc


def workspace_snapshot(
    root: Path,
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
    *,
    rebaseline: bool = False,
) -> dict[str, Any]:
    core = _continuation()
    current = workspace_current_snapshot(root)
    manifest = load_workspace_manifest(paths, control)
    if manifest is None:
        return {
            "state": "absent",
            "path": str(paths["workspace"]),
            "handoff_validation_on_claim": False,
            "unclassified_paths": [entry["path"] for entry in current["entries"]],
        }
    try:
        if rebaseline:
            observed = continuation_workspace.observe_handoff(
                manifest,
                task_id=str(control["task_id"]),
                snapshot=current,
                now=core._iso(),
            )
        else:
            observed = continuation_workspace.classify(
                manifest,
                task_id=str(control["task_id"]),
                snapshot=current,
                now=core._iso(),
            )
        summary = continuation_workspace.summary(
            observed,
            task_id=str(control["task_id"]),
        )
        return {
            "state": "valid",
            "path": str(paths["workspace"]),
            "handoff_validation_on_claim": rebaseline,
            "unclassified_paths": [],
            **summary,
        }
    except continuation_workspace.ContinuationWorkspaceError as exc:
        return {
            "state": "invalid",
            "path": str(paths["workspace"]),
            "error": str(exc),
            "handoff_validation_on_claim": False,
            "unclassified_paths": [entry["path"] for entry in current["entries"]],
        }


def workstream_direct_write_scopes(
    root: Path,
    workstream_id: str | None,
) -> tuple[list[str], Path | None]:
    if not workstream_id:
        return [], None
    project = discover_git_project(root)
    archived = False
    try:
        detail = read_workstream_detail(project.context_root, workstream_id)
        metadata = detail.metadata
    except SystemExit as exc:
        if not str(exc).startswith(f"workstream_not_found: {workstream_id}"):
            raise
        archive_path = workstream_archive_dir(project.context_root) / f"{workstream_id}.md"
        if not archive_path.is_file():
            raise
        metadata, _, diagnostics = parse_front_matter(archive_path.read_text(encoding="utf-8"))
        diagnostics.extend(validate_front_matter(metadata, workstream_front_matter_schema()))
        if metadata.get("id") != workstream_id:
            raise SystemExit(
                f"workstream_schema_failed: archived workstream id mismatch: expected {workstream_id}"
            ) from exc
        if diagnostics:
            raise SystemExit(
                "workstream_schema_failed: "
                + "; ".join(
                    f"{diagnostic.field + ': ' if diagnostic.field else ''}{diagnostic.message}"
                    for diagnostic in diagnostics
                )
            ) from exc
        archived = True
    kind = str(metadata.get("type") or "Task")
    merge_owner = metadata.get("merge_owner")
    coordination = metadata.get("coordination")
    raw_scopes = metadata.get("write_scope")
    scopes: list[str] = []
    if isinstance(raw_scopes, list):
        for item in raw_scopes:
            scope_type, scope_path = split_typed_scope(item)
            if not scope_type or not scope_path:
                continue
            allowed = scope_type in {"owned", "assigned", "draft", "evidence"}
            allowed = allowed or (scope_type == "authority" and kind in {"Merge", "Maintenance"})
            allowed = allowed or (
                scope_type == "shared"
                and (
                    merge_owner == workstream_id
                    or (coordination == "serial" and kind in {"Merge", "Maintenance"})
                )
            )
            if allowed:
                scopes.append(normalize_scope_path(scope_path))
    if archived:
        # A Workstream archive is an ACF-managed lifecycle transition that
        # intentionally removes the active detail before its surrounding Git
        # checkpoint may be committed.  If that owner dies in this narrow
        # window, recovery still needs to classify the exact archive authority
        # files from durable provenance without restoring the active Workstream.
        scopes.extend(
            [
                "active/Workstreams.md",
                f"active/workstreams/{workstream_id}.md",
                "archive/Archive_Index.md",
                f"archive/workstreams/{workstream_id}.md",
            ]
        )
    return sorted(dict.fromkeys(scopes)), project.context_root


def workspace_intent_candidates(
    root: Path,
    context_root: Path | None,
    path_value: str,
) -> list[str]:
    normalized = continuation_workspace.normalize_path(path_value)
    candidates = [normalized]
    if context_root is not None:
        absolute = (root / Path(normalized)).resolve()
        try:
            context_relative = absolute.relative_to(context_root.resolve()).as_posix()
        except ValueError:
            context_relative = None
        if context_relative:
            candidates.append(context_relative)
    return sorted(dict.fromkeys(candidates))


def continuation_init_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        task_id = str(args.task_id or args.workstream or "").strip()
        if not task_id:
            raise core.ContinuationError("--task-id or --workstream is required", code="task_id_required")
        git = core._git_identity(root)
        if git["detached"] or not git["branch"]:
            raise core.ContinuationError("continuation init refuses detached HEAD", code="detached_head")
        expected_branch = str(args.expected_branch or git["branch"])
        if expected_branch != git["branch"]:
            raise core.ContinuationError("current branch does not match --expected-branch", code="branch_mismatch")
        workstream = core._workstream_verification(root, args.workstream)
        if args.workstream and not workstream.get("ok"):
            raise core.ContinuationError(
                "ACF worktree verification failed",
                code="workstream_verification_failed",
                details={"workstream": workstream},
            )
        timing_profile, timing = timing_values(
            profile=args.profile,
            interval_minutes=args.interval_minutes,
            lease_ttl_minutes=args.lease_ttl_minutes,
            renew_interval_minutes=args.renew_interval_minutes,
            heartbeat_interval_minutes=args.heartbeat_interval_minutes,
            stale_after_minutes=args.stale_after_minutes,
        )
        directory = core._task_parent(root) / core._safe_key(task_id)
        paths = {
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
        }
        if paths["control"].exists() and not args.force:
            raise core.ContinuationError(
                "continuation task is already initialized",
                code="continuation_exists",
                next_actions=["Use `acf continuation doctor` or rerun init with --force after review."],
            )
        now = core._iso()
        snapshot = workspace_current_snapshot(root)
        try:
            manifest = continuation_workspace.new_manifest(
                task_id=task_id,
                snapshot=snapshot,
                now=now,
            )
        except continuation_workspace.ContinuationWorkspaceError as exc:
            raise workspace_error(exc) from exc
        control = {
            "schema_version": core.CONTROL_SCHEMA,
            "task_id": task_id,
            "title": str(args.title).strip(),
            "objective": str(args.objective).strip(),
            "workspace_root": str(root),
            "expected_branch": expected_branch,
            "bootstrap_head": git["head"],
            "workstream_id": args.workstream,
            "timing_profile": timing_profile,
            **timing,
            "history_policy": "local_first",
            "created_at": now,
            "updated_at": now,
        }
        plan_refs = list(args.plan_ref or [])
        state = {
            "schema_version": core.STATE_SCHEMA,
            "task_id": task_id,
            "objective": str(args.objective).strip(),
            "status": "ready",
            "stage": str(args.stage or "bootstrap").strip(),
            "next_action": str(
                args.next_action or "Refresh local authority and execute the current default plan."
            ).strip(),
            "updated_at": now,
            "completed": ["Initialized ACF bounded continuation control."],
            "constraints": [
                "Use the configured fixed Git worktree and branch.",
                "Treat local project state as authoritative; do not reconstruct state from chat history by default.",
                "Do not repeat an uncertain non-idempotent operation.",
                "Finish runner-owned writes with the project-required checkpoint; preserve unrelated external dirty state.",
            ],
            "evidence_refs": [],
            "open_questions": [],
            "plan_refs": plan_refs,
            "verification": ["Continuation control initialized with a bounded Git workspace baseline."],
        }
        directory.mkdir(parents=True, exist_ok=True)
        if not paths["lock"].exists():
            paths["lock"].write_bytes(b"0")
        core._write_json(paths["control"], control)
        core._write_state(paths["state"], state)
        core._write_json(paths["workspace"], manifest)
        if args.force:
            for stale in (
                paths["lease"],
                paths["pause"],
                paths["receipt"],
                paths["rounds"],
                paths["effects"],
                paths["coordination"],
                paths["workspace"],
                paths["reconcile"],
                paths["recovery"],
            ):
                stale.unlink(missing_ok=True)
            core._write_json(paths["workspace"], manifest)
        return {
            "status": "initialized",
            "task_id": task_id,
            "workspace_root": str(root),
            "branch": expected_branch,
            "state_dir": str(directory),
            "workstream": workstream,
            "workspace": continuation_workspace.summary(manifest, task_id=task_id),
            "next_action": state["next_action"],
        }

    return core._guarded(args, "continuation init", operation)


def continuation_configure_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            lease = core._lease_snapshot(paths, control)
            if lease["state"] == "active":
                raise core.ContinuationBusy(
                    "cannot reconfigure continuation timing while an active round owns the lease"
                )
            if not any(
                value is not None
                for value in (
                    args.profile,
                    args.interval_minutes,
                    args.lease_ttl_minutes,
                    args.renew_interval_minutes,
                    args.heartbeat_interval_minutes,
                    args.stale_after_minutes,
                )
            ):
                raise core.ContinuationError(
                    "configure requires --profile or at least one timing override",
                    code="timing_config_empty",
                )
            previous = {
                field: control[field]
                for field in (
                    "timing_profile",
                    "interval_minutes",
                    "lease_ttl_minutes",
                    "renew_interval_minutes",
                    "heartbeat_interval_minutes",
                    "stale_after_minutes",
                )
            }
            profile, timing = timing_values(
                profile=args.profile,
                interval_minutes=args.interval_minutes,
                lease_ttl_minutes=args.lease_ttl_minutes,
                renew_interval_minutes=args.renew_interval_minutes,
                heartbeat_interval_minutes=args.heartbeat_interval_minutes,
                stale_after_minutes=args.stale_after_minutes,
                base=control,
            )
            control.update({"timing_profile": profile, **timing, "updated_at": core._iso()})
            core._write_json(paths["control"], control)
            return {
                "status": "configured",
                "task_id": control["task_id"],
                "previous": previous,
                "control": {"timing_profile": profile, **timing},
            }

    return core._guarded(args, "continuation configure", operation)


def continuation_prompt_command(args: argparse.Namespace) -> int:
    core = _continuation()
    result_holder: dict[str, Any] = {}

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        control = core._load_control(paths, root)
        state = core._load_state(paths)
        round_snapshot, effect_snapshot = core._journal_snapshot(paths, control)
        status_snapshot = core._status(root, control["task_id"])
        task_flag = f" --task-id {json.dumps(control['task_id'])}"
        runner_id = str(getattr(args, "runner_id", None) or "").strip() or None
        plan_refs = list(state.get("plan_refs") or [])
        constraints = list(state.get("constraints") or [])
        directive_context = continuation_directive_commands.directive_context(paths, control)

        effect_summary = effect_snapshot.get("summary")
        if not isinstance(effect_summary, dict):
            effect_summary = {}
        effect_by_status = effect_summary.get("by_status")
        if not isinstance(effect_by_status, dict):
            effect_by_status = {}
        unresolved_effects = effect_summary.get("unresolved")
        if not isinstance(unresolved_effects, list):
            unresolved_effects = []
        resume_context = {
            "source": "persisted_state",
            "authority": "recovery_hint_only",
            "requires_local_authority_refresh": True,
            "may_lag_newer_project_effect_or_external_authority": True,
            "state_updated_at": state.get("updated_at"),
            "round_journal": {
                "state": round_snapshot.get("state"),
                "count": round_snapshot.get("count", 0),
            },
            "effect_journal": {
                "state": effect_snapshot.get("state"),
                "total": effect_summary.get("total", 0),
                "by_status": dict(effect_by_status),
                "unresolved_count": len(unresolved_effects),
            },
        }

        def render_items(values: list[Any], *, empty: str) -> str:
            if not values:
                return f"- {empty}"
            rendered: list[str] = []
            for value in values:
                if isinstance(value, str):
                    text = value
                else:
                    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
                rendered.append(f"- {text}")
            return "\n".join(rendered)

        hard_stop_conditions = [
            {
                "id": "objective_completed",
                "description": "The overall objective is genuinely complete with required evidence.",
            },
            {
                "id": "user_paused",
                "description": "The user explicitly paused the task.",
            },
            {
                "id": "human_input_required",
                "description": (
                    "New human authorization, credentials, or a non-delegable decision are required."
                ),
            },
            {
                "id": "project_access_unavailable",
                "description": (
                    "The configured project-access tool or connection, such as DevSpace, remains "
                    "unavailable after reasonable reconnect attempts."
                ),
            },
        ]
        execution_policy = {
            "schema_version": "acf.continuation.execution_policy.v1",
            "mode": "goal_directed_continuous",
            "bounded_scope": "ownership_write_and_effect_risk_only",
            "scheduler_wake_is_resume_only": True,
            "protocol_is_sequential_checklist": False,
            "agent_selects_work_scope": True,
            "continue_while_safe_useful": True,
            "mission_open_requires_active_alternative_search": True,
            "blocked_lane_should_switch_to_safe_alternative": True,
            "anti_busywork_scope": "unchanged_failed_action_only",
            "no_useful_work_end_requires_alternative_audit": True,
            "prefer_mission_stage_over_microtask_fragmentation": True,
            "checkpoint_requires_authority_refresh_and_continue": True,
            "next_action_is_default_execution_plan": True,
            "next_action_is_work_quota": False,
            "next_action_requires_authority_refresh": True,
            "next_action_may_be_superseded_by_newer_authority": True,
            "pending_user_directive_supersedes_persisted_next_action": True,
            "consumed_user_directive_requires_disposition": True,
            "directive_dispositions": ["resolve", "adopt", "supersede", "withdraw", "keep_pending_with_reason"],
            "checkpoint_is_stop": False,
            "commit_is_stop": False,
            "gate_completion_is_stop": False,
            "final_response_is_terminal": True,
            "final_response_requires_session_end_reason": True,
            "session_end_requires_no_safe_useful_work": True,
            "claim_requires_present_safe_useful_work": True,
            "control_plane_activity_satisfies_wait_condition": False,
            "no_useful_work_may_end_wake_without_claim": True,
            "progress_report_is_session_end_reason": False,
            "elapsed_time_is_session_end_reason": False,
            "startup_probe_is_session_end_reason": False,
            "active_owner_is_session_end_reason": False,
            "active_lease_requires_liveness_verification": True,
            "active_lease_is_session_end_reason": False,
            "verified_duplicate_owner_may_end_duplicate_wake": True,
            "duplicate_wake_exit_is_task_stop": False,
            "stale_owner_requires_recovery": True,
            "contender_continues_safe_read_only_when_available": True,
            "contender_must_create_busywork": False,
            "resume_hint_is_live_authority": False,
            "resume_hint_requires_authority_refresh": True,
            "timing_is_execution_duration_target": False,
            "platform_boundary_requires_explicit_signal": True,
            "release_is_default_end_step": False,
            "action_refusal_scope": "specific_action_only",
            "unchanged_failed_action_may_repeat": False,
            "hard_stop_conditions": hard_stop_conditions,
        }
        project_context = {
            "plan_refs": plan_refs,
            "constraints": constraints,
            "wrapper_constraint_slot": {
                "required": True,
                "classes": [
                    "tooling",
                    "runtime",
                    "resource",
                    "permission",
                    "security",
                    "scientific",
                    "validation",
                    "issue_reporting",
                ],
                "rule": (
                    "The scheduler wrapper must be a sufficient high-salience bootstrap contract: "
                    "it supplies exact project/workspace/tooling entry, stable ACF upgrade/adaptation, "
                    "authority refresh and generated-plan execution rules, owner disclosure, and "
                    "project-specific constraints without copying the generic continuation state machine."
                ),
            },
        }
        pending_directives = list(directive_context.get("pending") or [])

        def render_directives(values: list[Any]) -> str:
            if not values:
                return "- No pending user directives."
            rendered: list[str] = []
            for value in values:
                if not isinstance(value, Mapping):
                    continue
                rendered.append(
                    "- "
                    f"{value.get('id')} | kind={value.get('kind')} | priority={value.get('priority')} | "
                    f"{value.get('text')}"
                )
            return "\n".join(rendered) or "- No pending user directives."
        lease_snapshot = status_snapshot["lease"]
        raw_lease = lease_snapshot.get("lease") if isinstance(lease_snapshot, Mapping) else None
        owner_runner_id = str(raw_lease.get("runner_id") or "") if isinstance(raw_lease, Mapping) else None
        owner_generation = raw_lease.get("generation") if isinstance(raw_lease, Mapping) else None
        owner_liveness = str(lease_snapshot.get("liveness") or "absent")
        caller_identity_known = runner_id is not None
        same_runner_owner = bool(
            lease_snapshot.get("state") == "active"
            and runner_id
            and owner_runner_id
            and runner_id == owner_runner_id
        )
        fresh_owner_caller_unknown = bool(
            lease_snapshot.get("state") == "active"
            and owner_liveness == "fresh"
            and not caller_identity_known
        )
        verified_live_other_owner = bool(
            lease_snapshot.get("state") == "active"
            and owner_liveness == "fresh"
            and caller_identity_known
            and not same_runner_owner
        )
        stale_or_unverified_owner = bool(
            lease_snapshot.get("state") == "active"
            and owner_liveness in {"stale", "legacy_unknown"}
            and not same_runner_owner
        )
        expired_owner = lease_snapshot.get("state") == "expired"
        owner_disposition = (
            "current_owner"
            if same_runner_owner
            else "fresh_owner_caller_unknown"
            if fresh_owner_caller_unknown
            else "verified_live_other_owner"
            if verified_live_other_owner
            else "stale_or_unverified_owner"
            if stale_or_unverified_owner
            else "expired_owner"
            if expired_owner
            else "no_active_owner"
        )
        owner_context = {
            "disposition": owner_disposition,
            "caller_runner_id": runner_id,
            "caller_identity_known": caller_identity_known,
            "owner_runner_id": owner_runner_id,
            "generation": owner_generation,
            "liveness": owner_liveness,
            "heartbeat_age_seconds": lease_snapshot.get("heartbeat_age_seconds"),
            "orphan_candidate": bool(lease_snapshot.get("orphan_candidate")),
            "verified_live": bool(owner_liveness == "fresh" and lease_snapshot.get("state") == "active"),
            "duplicate_wake_candidate": verified_live_other_owner,
            "can_claim": bool(status_snapshot.get("can_claim")),
            "blocked_reasons": list(status_snapshot.get("blocked_reasons") or []),
        }

        goal_summary_placeholder = "<current-goal-summary>"
        attempt_command = (
            f"acf continuation coordination attempt {json.dumps(str(root))}{task_flag} "
            f"--runner-id <runner> --objective-summary {goal_summary_placeholder} --json"
        )
        control_actions: list[str] = []
        conditional_sections: list[str] = []
        if same_runner_owner:
            control_actions.append(
                "Continue under the current owner credential; assert ownership before protected non-idempotent work "
                "and heartbeat/renew according to lease liveness."
            )
            conditional_sections.append(
                "Current writer safety:\n"
                "- Before project writes, declare concrete workspace intent and preserve unrelated external dirty state.\n"
                "- If the project-access/scheduler transport rejects high-entropy owner credentials, set `ACF_CONTINUATION_FENCE_TOKEN_FILE` to a caller-controlled local temp file before claim/recover. ACF will write the new fence token there and omit the raw token from JSON; keep the same environment variable on fenced owner commands and delete the file after release.\n"
                "- Before each non-idempotent or long-lived writer side effect, use deterministic effect identity; never replay an uncertain outcome.\n"
                "- Narrow ACF control-plane lifecycle exception: after the authenticated runner itself executes deterministic `acf workstream scope-add|merge-request|ready|merge-start|done` for the bound Workstream, the exact generated `docs/ai/active/Workstreams.md` plus that Workstream detail may be reviewed and committed as a dedicated control-plane checkpoint; this does not extend ordinary Task write scope or permit any third baseline/external path.\n"
                "- Checkpoints and Git commits are persistence points, not stop signals. Release only when this execution session is actually handing off or ending."
            )
        elif fresh_owner_caller_unknown:
            control_actions.append(
                "A fresh active owner exists, but the caller runner identity was not supplied. Re-render this prompt with `--runner-id <runner>` before deciding whether this is the current owner or a duplicate wake."
            )
            conditional_sections.append(
                "Fresh owner with unknown caller identity:\n"
                "- Fresh liveness proves an owner session is live, but without the caller runner id this prompt cannot safely classify the caller as that owner or as a duplicate wake.\n"
                "- Do not infer duplicate ownership, auto-challenge a healthy owner, or write protected project files until caller identity is explicit."
            )
        elif verified_live_other_owner:
            control_actions.extend(
                [
                    attempt_command,
                    "Do not challenge while the observed owner remains fresh. Do not write protected project files.",
                    "If this activation is only a duplicate scheduler wake and no independent safe non-conflicting work is useful, it may end without changing task state; the mission remains running under the existing owner.",
                ]
            )
            conditional_sections.append(
                "Verified live other owner:\n"
                "- Fresh owner liveness is authenticated control-plane evidence that the owner session is still live; it does not prove which file is being edited at this instant.\n"
                "- A healthy overlap is not a recovery event. Do not auto-challenge it. Safe independent read-only work is optional, not mandatory busywork.\n"
                "- Ending only this duplicate wake is not a task stop, pause, blocker, or completion."
            )
        elif stale_or_unverified_owner:
            control_actions.extend(
                [
                    attempt_command,
                    f"Inspect `acf continuation coordination status {json.dumps(str(root))}{task_flag} --json`; a stale/unverified owner requires challenge-backed verification before recovery.",
                    "After ownership forfeiture evidence or other valid owner-ended evidence, use formal reconcile/recover with current workspace/HEAD/effect/identity evidence; never steal ownership from a mere lease record.",
                ]
            )
            conditional_sections.append(
                "Stale or unverified owner recovery:\n"
                "- An active lease is not proof that another agent is still working. Verify liveness first.\n"
                "- Challenge timeout only forfeits the old ownership claim; it does not grant write access or prove external effects are terminal.\n"
                "- Recovery remains receipt-bound and generation-fenced. A blocked recovery action does not prevent other safe diagnosis or evidence work."
            )
        elif expired_owner:
            control_actions.append(
                "The previous lease is expired. Use doctor/reconcile evidence to decide whether formal recover is required; do not re-claim through unresolved effects, HEAD drift, or workspace provenance ambiguity."
            )
            conditional_sections.append(
                "Expired-owner recovery:\n"
                "- Reconcile current workspace, HEAD, effect journal, identity, and prior generation before recovery when required.\n"
                "- Reuse credentials returned by recover; do not claim a second time after successful recovery. If raw credentials cannot safely cross the command transport, set `ACF_CONTINUATION_FENCE_TOKEN_FILE` before recover and reuse that file handle for fenced commands."
            )
        elif status_snapshot.get("can_claim"):
            control_actions.extend(
                [
                    attempt_command,
                    "Use refreshed project authority to decide whether safe useful work is executable now. If the persisted/default plan explicitly waits for a real external or project-state change and that condition is not met, do not claim merely to manufacture a continuation lifecycle change; scheduler wake, coordination attempt, and claim are control-plane activity, not evidence satisfying that wait condition.",
                    f"If useful work is executable now, claim with `acf continuation claim {json.dumps(str(root))}{task_flag} --runner-id <runner> --json`, then re-render `acf continuation prompt {json.dumps(str(root))}{task_flag} --runner-id <runner> --json` with the same runner id before project writes so current-writer safety guidance is loaded.",
                    "If no safe useful work is presently executable, this scheduler wake may end without claiming and without changing task state; otherwise execute the refreshed default plan under the returned fenced owner credential after the post-claim prompt refresh.",
                ]
            )
            conditional_sections.append(
                "Claimable writer path:\n"
                "- The coordination attempt is a compact intent record, not a bounded work quota. `--objective-summary` names the current goal; it does not limit how much useful work the session may complete.\n"
                "- A scheduler wake, coordination attempt, or claim is control-plane bookkeeping. It must not be counted as the real/external state change required by a conditional wait plan, and it must not be used to create synthetic progress solely so the task can observe itself.\n"
                "- Claim only when refreshed authority identifies safe useful work that is executable now. If a wait condition is still unsatisfied and no other useful work exists, ending this wake without claim leaves the mission running and is not a pause, blocker, or completion.\n"
                "- For credential-redacting command transports, set `ACF_CONTINUATION_FENCE_TOKEN_FILE` to a caller-controlled local temp file before claim so ACF returns a non-secret file handle instead of the raw token.\n"
                "- After claim, declare concrete workspace intent before writes and use deterministic effect identity before non-idempotent side effects."
            )
        else:
            control_actions.append(
                "The task is not currently claimable. Inspect the reported blocked reasons and perform only the safe action that resolves the specific blocker."
            )

        workspace_snapshot = status_snapshot.get("workspace")
        if isinstance(workspace_snapshot, Mapping) and (
            workspace_snapshot.get("state") == "invalid"
            or workspace_snapshot.get("has_conflicts")
            or workspace_snapshot.get("unclassified_paths")
        ):
            conditional_sections.append(
                "Workspace provenance is currently relevant:\n"
                "- Inspect `acf continuation workspace status ... --json`. Preserve baseline/external dirty state; do not stash, reset, clean, or absorb uncertain files.\n"
                "- Reclassify unexpected output only after provenance is proven with durable evidence; uncertainty remains fail-closed."
            )

        if resume_context["effect_journal"]["unresolved_count"]:
            conditional_sections.append(
                "Unresolved effect authority is currently relevant:\n"
                "- Inspect the existing effect identity before any submit/replay. Prepared/active/unknown effects remain unresolved until authoritative terminal observation.\n"
                "- If an owner lifecycle ended, reconcile the existing durable identity rather than creating a replacement effect from memory.\n"
                "- A local deterministic effect with no external id may use `reconcile --effect-local-terminal` when it is still prepared or active and durable local authority evidence proves its terminal result; unknown effects and external jobs remain fail-closed."
            )

        conditional_text = "\n\n".join(conditional_sections) if conditional_sections else "No additional conditional safety branch is active."
        prompt = f"""Use the fixed local Git worktree below as the authoritative execution target.

Task: {control['task_id']} — {control['title']}
Worktree: {root}
Branch: {control['expected_branch']}

Overall objective:
{state.get('objective') or control['objective']}

Current execution state:
- Stage: {state['stage']}
- Status: {state['status']}
- Default execution plan (persisted): {state['next_action']}

Authority rule:
- Refresh local authority with `acf continuation doctor {json.dumps(str(root))}{task_flag} --json` plus the project-specific Git/plan/Runtime/evidence checks required by the scheduler wrapper.
- The persisted default execution plan may lag newer authority. Newer authoritative evidence supersedes it; otherwise execute it as the next plan instead of merely reading, explaining, or reporting it.
- If newer authority explicitly invalidates a persisted compact constraint or closes an old open question, an authenticated owner must retire the exact stale entry at checkpoint with `--supersede-constraint` / `--resolve-open-question` plus durable `--evidence-ref`; do not leave contradictory high-salience state beside the newer plan.
- Completing the default plan is not a work quota or stopping boundary. Reassess the overall objective and continue with the next safe, non-repetitive, valuable action while useful work remains.
- Never replay an already-observed side effect merely because persisted recovery metadata is old.

User directive authority:
- Directive revision: {directive_context['revision']}; pending: {directive_context['pending_count']}; adopted: {directive_context.get('adopted_count', 0)}; active: {directive_context.get('active_count', 0)}; digest: {directive_context['digest']}.
- Pending directives are new user-authority signals and supersede the persisted default execution plan until authority refresh decides how each applies.
- The directive inbox is not a second Task Plan. Persistent requirements/constraints/plan changes must be synchronized into the correct project Markdown authority before being marked adopted; temporary runtime steering may be adopted with durable evidence.
- Every directive actually consumed in this session must reach an explicit safe-control-point disposition: resolve when completed, adopt only after the required durable authority/execution evidence exists, supersede when replaced by a newer version, withdraw only with explicit cancellation authority, or deliberately remain pending with a recorded reason. Merely reading directive text is never adoption evidence.
- `resolve`, `withdraw`, and `supersede` are distinct terminal meanings. Do not reopen resolved history; use a new add/supersede event for new user authority.
- Directive pressure is mechanical observability only: {json.dumps(directive_context.get('pressure') or {}, ensure_ascii=False, sort_keys=True)}. Never infer semantic completion from age or capacity pressure.
{render_directives(pending_directives)}

Ownership now:
- Disposition: {owner_disposition}
- Caller runner: {runner_id or 'not supplied'}
- Active owner runner: {owner_runner_id or 'none'}
- Generation: {owner_generation if owner_generation is not None else 'none'}
- Liveness: {owner_liveness}
- Heartbeat age seconds: {lease_snapshot.get('heartbeat_age_seconds') if lease_snapshot.get('heartbeat_age_seconds') is not None else 'unknown'}
- Can claim now: {str(bool(status_snapshot.get('can_claim'))).lower()}
- Blocked reasons: {json.dumps(list(status_snapshot.get('blocked_reasons') or []), ensure_ascii=False)}

Journal authority summary: rounds={resume_context['round_journal']['count']}; effects={resume_context['effect_journal']['total']}; unresolved_effects={resume_context['effect_journal']['unresolved_count']}.

Control actions relevant now:
{render_items(control_actions, empty="No control-plane action is required.")}

Continuous execution contract:
- A scheduler wake only resumes one continuous task; it is not a work round, reporting interval, quota, or expected stopping point.
- Scheduler/coordination/claim activity is not project progress and does not satisfy a plan that explicitly waits for a real external or project-state change.
- Bounded continuation limits ownership, write scope, external side effects, and recovery risk. It does not bound the amount of useful project work.
- The Agent chooses work scope, order, implementation strategy, and validation depth from current project authority.
- Mission open => search safe alternatives before no-work: diagnosis, adjacent gap, validation, contract, dogfood, release prep, diagnostics. Anti-busywork blocks only unchanged failure; prefer mission/PLAN stage; checkpoint => refresh and continue.
- Tests, fixes, commits, checkpoints, and Gates are progress evidence, not session-end signals.
- A final assistant response ends the current execution session. Do not final merely to report progress, because time passed, because context feels long, or because a local milestone succeeded.
- A safety refusal blocks only the unsafe action. Continue other safe diagnosis, evidence review, testing, planning, or non-conflicting work when available.
- Do not repeat an unchanged failed action without new evidence, input, environment, or strategy.

Task-level hard-stop conditions are exactly:
1. The overall objective is genuinely complete with required evidence.
2. The user explicitly paused the task.
3. New human authorization, credentials, or a non-delegable decision are required.
4. The configured project-access tool or connection, such as DevSpace, remains unavailable after reasonable reconnect attempts.

Current conditional safety guidance:
{conditional_text}

Lease timing (liveness only): profile={control['timing_profile']}; wake={control['interval_minutes']}m; TTL={control['lease_ttl_minutes']}m; heartbeat={control['heartbeat_interval_minutes']}m; stale={control['stale_after_minutes']}m; renew={control['renew_interval_minutes']}m. These numbers are not execution-duration targets or stop signals.

Project plan references:
{render_items(plan_refs, empty="No plan reference is currently recorded.")}

Project-specific constraints recorded in continuation state:
{render_items(constraints, empty="No compact project constraint is currently recorded in continuation state.")}

Scheduler wrapper contract:
- The wrapper must be sufficient, not artificially thin: it must carry exact project/workspace/tool entry, exact existing-worktree opening semantics, stable ACF upgrade/adaptation, authority refresh, generated-plan execution, owner disclosure, and project-specific Runtime/resource/permission/security/scientific/validation/issue-reporting rules.
- This generated prompt plus `execution_policy` remain the dynamic generic continuation authority. The wrapper must not freeze a second copy of claim/challenge/reconcile/workspace/effect state-machine details.
- Invoke `acf continuation prompt` again on every scheduler wake so the current owner state and only the relevant control branch are rendered.

Reusable product issues:
- Record concrete reusable ACF/continuation/workflow defects with `acf continuation issue ... --json`. Do not record normal active-lease no-ops, healthy duplicate-owner overlap, expected waits, or task-specific scientific failures as product issues.
"""
        identity = {
            "workspace_root": str(root),
            "branch": control["expected_branch"],
            "task_id": control["task_id"],
            "workstream_id": control.get("workstream_id"),
        }
        scheduler_wrapper_contract = writer_scheduler_wrapper_contract(
            identity,
            project_context["wrapper_constraint_slot"],
        )
        value = {
            "status": "rendered",
            "task_id": control["task_id"],
            "identity": identity,
            "current": {
                "stage": state["stage"],
                "status": state["status"],
                "next_action": state["next_action"],
            },
            "owner_context": owner_context,
            "directive_context": directive_context,
            "resume_context": resume_context,
            "execution_policy": execution_policy,
            "project_context": project_context,
            "scheduler_wrapper_contract": scheduler_wrapper_contract,
            "automation_prompt_execution_contract": automation_prompt_execution_contract(),
            "prompt": prompt,
            "next_actions": control_actions,
        }
        result_holder.update(value)
        return value

    exit_code = core._guarded(args, "continuation prompt", operation)
    if exit_code == 0 and not core.json_enabled(args):
        print(result_holder["prompt"])
    return exit_code


def continuation_workspace_status_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        status = core._status(root, args.task_id)
        return {
            "status": "workspace_status",
            "workspace": status["workspace"],
            "git": status["git"],
            "lease": status["lease"],
        }

    return core._guarded(args, "continuation workspace status", operation)


def continuation_workspace_intent_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            lease_snapshot = core._lease_snapshot(paths, control)
            lease = core._assert_lease_owner_with_activity(
                paths,
                control,
                lease_snapshot,
                lease_id=args.lease_id,
                fence_token=resolve_fence_token(args),
                generation=args.generation,
            )
            generation = core._require_fenced_generation(lease)
            manifest = load_workspace_manifest(paths, control, require_existing=True)
            assert manifest is not None
            if int(manifest["generation"]) != generation:
                raise core.ContinuationError(
                    "workspace manifest generation does not match active owner",
                    code="workspace_generation_mismatch",
                    exit_code=3,
                )
            raw_paths = list(dict.fromkeys(args.intent_path or []))
            if not raw_paths:
                raise core.ContinuationError("workspace intent requires --path", code="workspace_intent_empty")
            normalized_paths: list[str] = []
            try:
                for path_value in raw_paths:
                    normalized_paths.append(continuation_workspace.normalize_path(path_value))
            except continuation_workspace.ContinuationWorkspaceError as exc:
                raise workspace_error(exc) from exc
            allowed_scopes, context_root = workstream_direct_write_scopes(
                root,
                str(control.get("workstream_id")) if control.get("workstream_id") else None,
            )
            if control.get("workstream_id") and not allowed_scopes:
                raise core.ContinuationError(
                    "bound Workstream has no direct write scope for continuation workspace intent",
                    code="workspace_intent_out_of_scope",
                    exit_code=3,
                )
            candidate_paths = {
                path_value: workspace_intent_candidates(root, context_root, path_value)
                for path_value in normalized_paths
            }
            try:
                manifest = continuation_workspace.add_intents(
                    manifest,
                    task_id=str(control["task_id"]),
                    paths=normalized_paths,
                    allowed_scopes=allowed_scopes,
                    candidate_paths=candidate_paths,
                    snapshot=workspace_current_snapshot(root),
                    now=core._iso(),
                )
            except continuation_workspace.ContinuationWorkspaceError as exc:
                raise workspace_error(exc) from exc
            core._write_json(paths["workspace"], manifest)
            return {
                "status": "workspace_intent_recorded",
                "generation": generation,
                "workspace": continuation_workspace.summary(
                    manifest,
                    task_id=str(control["task_id"]),
                ),
            }

    return core._guarded(args, "continuation workspace intent", operation)


def continuation_workspace_reclassify_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            lease_snapshot = core._lease_snapshot(paths, control)
            lease = core._assert_lease_owner_with_activity(
                paths,
                control,
                lease_snapshot,
                lease_id=args.lease_id,
                fence_token=resolve_fence_token(args),
                generation=args.generation,
            )
            generation = core._require_fenced_generation(lease)
            manifest = load_workspace_manifest(paths, control, require_existing=True)
            assert manifest is not None
            if int(manifest["generation"]) != generation:
                raise core.ContinuationError(
                    "workspace manifest generation does not match active owner",
                    code="workspace_generation_mismatch",
                    exit_code=3,
                )
            raw_task_paths = list(dict.fromkeys(args.task_owned_path or []))
            raw_external_paths = list(dict.fromkeys(args.baseline_external_path or []))
            if not raw_task_paths and not raw_external_paths:
                raise core.ContinuationError(
                    "workspace reclassification requires at least one explicit path",
                    code="workspace_reclassification_incomplete",
                )
            try:
                task_paths = [
                    continuation_workspace.normalize_path(path_value)
                    for path_value in raw_task_paths
                ]
                external_paths = [
                    continuation_workspace.normalize_path(path_value)
                    for path_value in raw_external_paths
                ]
            except continuation_workspace.ContinuationWorkspaceError as exc:
                raise workspace_error(exc) from exc
            allowed_scopes, context_root = workstream_direct_write_scopes(
                root,
                str(control.get("workstream_id")) if control.get("workstream_id") else None,
            )
            if control.get("workstream_id") and task_paths and not allowed_scopes:
                raise core.ContinuationError(
                    "bound Workstream has no direct write scope for task-owned workspace reclassification",
                    code="workspace_reclassification_out_of_scope",
                    exit_code=3,
                )
            candidate_paths = {
                path_value: workspace_intent_candidates(root, context_root, path_value)
                for path_value in task_paths
            }
            try:
                manifest, review = continuation_workspace.reclassify_unexpected(
                    manifest,
                    task_id=str(control["task_id"]),
                    snapshot=workspace_current_snapshot(root),
                    task_owned_paths=task_paths,
                    baseline_external_paths=external_paths,
                    allowed_scopes=allowed_scopes,
                    candidate_paths=candidate_paths,
                    evidence_refs=list(args.evidence_ref or []),
                    reason=str(args.reason),
                    now=core._iso(),
                )
            except continuation_workspace.ContinuationWorkspaceError as exc:
                error = workspace_error(exc)
                error.exit_code = 3
                raise error from exc
            core._write_json(paths["workspace"], manifest)
            return {
                "status": "workspace_reclassified",
                "generation": generation,
                "review": review,
                "workspace": continuation_workspace.summary(
                    manifest,
                    task_id=str(control["task_id"]),
                ),
            }

    return core._guarded(args, "continuation workspace reclassify", operation)


def continuation_workspace_adopt_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            if paths["workspace"].exists():
                raise core.ContinuationError(
                    "workspace ownership manifest already exists; legacy adoption is one-time only",
                    code="workspace_adoption_not_required",
                    exit_code=3,
                    next_actions=["Use `acf continuation workspace status` and the normal intent/refresh flow."],
                )
            lease_snapshot = core._lease_snapshot(paths, control)
            if lease_snapshot["state"] == "invalid":
                raise core.ContinuationError(
                    "legacy workspace adoption requires a valid ownerless lease state",
                    code="workspace_adoption_lease_invalid",
                    exit_code=3,
                )
            if lease_snapshot["state"] == "active":
                raise core.ContinuationError(
                    "legacy workspace adoption cannot run while an active owner holds the task",
                    code="workspace_adoption_owner_active",
                    exit_code=3,
                    next_actions=[
                        "Inspect owner liveness first. A fresh verified owner should not be challenged merely because another scheduler wake arrived; stale or unverified ownership uses the generated recovery path."
                    ],
                )
            state = core._load_state(paths)
            snapshot = workspace_current_snapshot(root)
            prior_generation: int
            if lease_snapshot["state"] == "expired":
                raw_lease = lease_snapshot.get("lease")
                if not isinstance(raw_lease, Mapping):
                    raise core.ContinuationError(
                        "expired lease payload is missing",
                        code="workspace_adoption_lease_invalid",
                        exit_code=3,
                    )
                lease_head = str(raw_lease.get("head") or "")
                if lease_head != str(snapshot["head"]):
                    raise core.ContinuationError(
                        "legacy workspace adoption refuses Git HEAD drift from the interrupted owner",
                        code="workspace_adoption_head_mismatch",
                        exit_code=3,
                        details={"lease_head": lease_head, "current_head": snapshot["head"]},
                        next_actions=["Reconcile the HEAD change before classifying legacy dirty paths."],
                    )
                generation_value = raw_lease.get("generation")
                if isinstance(generation_value, bool) or not isinstance(generation_value, int):
                    raise core.ContinuationError(
                        "legacy workspace adoption requires a durable prior generation",
                        code="workspace_adoption_generation_invalid",
                        exit_code=3,
                    )
                prior_generation = generation_value
            else:
                if state["status"] == "running":
                    raise core.ContinuationError(
                        "running continuation without a lease cannot be safely adopted",
                        code="workspace_adoption_owner_unknown",
                        exit_code=3,
                        next_actions=["Reconcile the missing owner identity before adopting workspace provenance."],
                    )
                prior_generation = int(control.get("generation", 0))

            task_owned_paths = list(dict.fromkeys(args.task_owned_path or []))
            baseline_external_paths = list(dict.fromkeys(args.baseline_external_path or []))
            if not task_owned_paths and not baseline_external_paths:
                raise core.ContinuationError(
                    "legacy workspace adoption requires at least one explicit path classification",
                    code="workspace_adoption_incomplete",
                    exit_code=3,
                )
            allowed_scopes, context_root = workstream_direct_write_scopes(
                root,
                str(control.get("workstream_id")) if control.get("workstream_id") else None,
            )
            if control.get("workstream_id") and task_owned_paths and not allowed_scopes:
                raise core.ContinuationError(
                    "bound Workstream has no direct write scope for task-owned legacy adoption",
                    code="workspace_adoption_out_of_scope",
                    exit_code=3,
                )
            candidate_paths: dict[str, list[str]] = {}
            try:
                normalized_task_paths = [
                    continuation_workspace.normalize_path(path_value)
                    for path_value in task_owned_paths
                ]
                normalized_external_paths = [
                    continuation_workspace.normalize_path(path_value)
                    for path_value in baseline_external_paths
                ]
                candidate_paths = {
                    path_value: workspace_intent_candidates(root, context_root, path_value)
                    for path_value in normalized_task_paths
                }
                manifest = continuation_workspace.adopt_legacy_manifest(
                    task_id=str(control["task_id"]),
                    prior_generation=prior_generation,
                    snapshot=snapshot,
                    task_owned_paths=normalized_task_paths,
                    baseline_external_paths=normalized_external_paths,
                    allowed_scopes=allowed_scopes,
                    candidate_paths=candidate_paths,
                    evidence_refs=list(args.evidence_ref or []),
                    reason=str(args.reason),
                    receipt_id=str(uuid.uuid4()),
                    now=core._iso(),
                )
            except continuation_workspace.ContinuationWorkspaceError as exc:
                error = workspace_error(exc)
                error.exit_code = 3
                raise error from exc
            core._write_json(paths["workspace"], manifest)
            adoption = manifest.get("adoption_receipt")
            next_action = (
                "Run `acf continuation doctor`, then use formal reconcile/recover for the expired owner."
                if lease_snapshot["state"] == "expired"
                else "Run `acf continuation doctor` and claim the next bounded round when eligible."
            )
            return {
                "status": "workspace_adopted",
                "task_id": control["task_id"],
                "prior_generation": prior_generation,
                "adoption": adoption,
                "workspace": continuation_workspace.summary(
                    manifest,
                    task_id=str(control["task_id"]),
                ),
                "next_action": next_action,
            }

    return core._guarded(args, "continuation workspace adopt", operation)


def continuation_workspace_refresh_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            lease_snapshot = core._lease_snapshot(paths, control)
            lease = core._assert_lease_owner_with_activity(
                paths,
                control,
                lease_snapshot,
                lease_id=args.lease_id,
                fence_token=resolve_fence_token(args),
                generation=args.generation,
            )
            generation = core._require_fenced_generation(lease)
            manifest = load_workspace_manifest(paths, control, require_existing=True)
            assert manifest is not None
            if int(manifest["generation"]) != generation:
                raise core.ContinuationError(
                    "workspace manifest generation does not match active owner",
                    code="workspace_generation_mismatch",
                    exit_code=3,
                )
            try:
                manifest = continuation_workspace.classify(
                    manifest,
                    task_id=str(control["task_id"]),
                    snapshot=workspace_current_snapshot(root),
                    now=core._iso(),
                )
            except continuation_workspace.ContinuationWorkspaceError as exc:
                raise workspace_error(exc) from exc
            core._write_json(paths["workspace"], manifest)
            return {
                "status": "workspace_refreshed",
                "generation": generation,
                "workspace": continuation_workspace.summary(
                    manifest,
                    task_id=str(control["task_id"]),
                ),
            }

    return core._guarded(args, "continuation workspace refresh", operation)


def continuation_list_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root: Path | None
        if bool(args.all_projects):
            root = None
        else:
            root = core._workspace_root(args.path)
        contract = continuation_schema_contract()
        tasks = continuation_inventory.discover_tasks(
            acf_home(),
            contracts=contract,
            workspace_root=root,
            task_id=args.task_id,
        )
        project_keys = sorted(
            {str(item.get("project_key") or "") for item in tasks if item.get("project_key")}
        )
        return {
            "status": "listed",
            "scope": "all_projects" if bool(args.all_projects) else "current_project",
            "acf_home": str(acf_home()),
            "project_count": len(project_keys),
            "task_count": len(tasks),
            "schema_contract": contract,
            "tasks": tasks,
        }

    return core._guarded(args, "continuation list", operation)


def continuation_migrate_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        if bool(args.apply) and bool(args.dry_run):
            raise core.ContinuationError(
                "--apply and --dry-run are mutually exclusive",
                code="continuation_migration_invalid",
            )
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            lease = core._lease_snapshot(paths, control)
            if lease["state"] != "absent":
                raise core.ContinuationError(
                    "continuation state migration requires no lease record",
                    code="continuation_migration_active_owner",
                    exit_code=3,
                    details={"lease_state": lease["state"]},
                    next_actions=[
                        "Finish/recover and release the continuation round before migrating state schemas."
                    ],
                )
            try:
                plan = continuation_inventory.workspace_migration_plan(
                    paths["directory"],
                    task_id=str(control["task_id"]),
                )
            except continuation_inventory.ContinuationInventoryError as exc:
                raise core.ContinuationError(str(exc), code=exc.code, exit_code=3) from exc
            public_plan = {key: value for key, value in plan.items() if key != "payload"}
            if not bool(plan.get("migration_required")):
                return {
                    "status": "migration_not_needed",
                    "applied": False,
                    "task_id": control["task_id"],
                    "workstream_id": control.get("workstream_id"),
                    "state_dir": str(paths["directory"]),
                    "plan": public_plan,
                }
            if not bool(args.apply):
                return {
                    "status": "migration_planned",
                    "applied": False,
                    "dry_run": True,
                    "task_id": control["task_id"],
                    "workstream_id": control.get("workstream_id"),
                    "state_dir": str(paths["directory"]),
                    "plan": public_plan,
                    "next_action": "Review the plan, then rerun with --apply --reason <reason>.",
                }
            reason = str(args.reason or "").strip()
            if not reason:
                raise core.ContinuationError(
                    "--reason is required with --apply",
                    code="continuation_migration_invalid",
                )
            preserved_before = continuation_inventory.preserved_history_digests(paths["directory"])
            payload = plan.get("payload")
            if not isinstance(payload, Mapping):
                raise core.ContinuationError(
                    "migration plan did not produce a workspace payload",
                    code="continuation_migration_invalid",
                )
            core._write_json(paths["workspace"], payload)
            preserved_after = continuation_inventory.preserved_history_digests(paths["directory"])
            if preserved_after != preserved_before:
                raise core.ContinuationError(
                    "continuation history changed during state migration",
                    code="continuation_migration_history_drift",
                    exit_code=3,
                )
            receipt = continuation_inventory.migration_receipt(
                paths["directory"],
                task_id=str(control["task_id"]),
                workspace_root=str(root),
                reason=reason,
                migrated_at=core._iso(),
                plan=plan,
                history_digests=preserved_before,
            )
            receipt_path = paths["directory"] / "last_migration.json"
            core._write_json(receipt_path, receipt)
            return {
                "status": "migrated",
                "applied": True,
                "task_id": control["task_id"],
                "workstream_id": control.get("workstream_id"),
                "state_dir": str(paths["directory"]),
                "plan": public_plan,
                "receipt_path": str(receipt_path),
                "receipt": receipt,
            }

    return core._guarded(args, "continuation migrate", operation)


def register_workspace_parsers(subparsers, add_json_argument) -> None:
    list_parser = subparsers.add_parser(
        "list",
        help="read ACF_HOME continuation task/schema/timing compatibility without mutating state",
    )
    list_parser.add_argument("path", nargs="?", type=Path)
    list_parser.add_argument("--task-id", default=None)
    list_parser.add_argument(
        "--all-projects",
        action="store_true",
        help="scan every continuation namespace under the current ACF_HOME",
    )
    add_json_argument(list_parser)
    list_parser.set_defaults(func=continuation_list_command)

    migrate = subparsers.add_parser(
        "migrate",
        help="plan or apply an explicit history-preserving migration for supported legacy state",
    )
    migrate.add_argument("path", nargs="?", type=Path)
    migrate.add_argument("--task-id", default=None)
    migrate.add_argument("--apply", action="store_true")
    migrate.add_argument("--dry-run", action="store_true")
    migrate.add_argument("--reason", default=None)
    add_json_argument(migrate)
    migrate.set_defaults(func=continuation_migrate_command)

    workspace = subparsers.add_parser(
        "workspace",
        help="inspect and declare bounded Git workspace ownership without editing project files",
    )
    workspace_subparsers = workspace.add_subparsers(
        dest="continuation_workspace_command",
        required=True,
    )

    status = workspace_subparsers.add_parser(
        "status",
        help="classify baseline, runner-owned, unrelated and conflicting dirty paths",
    )
    status.add_argument("path", nargs="?", type=Path)
    status.add_argument("--task-id", default=None)
    add_json_argument(status)
    status.set_defaults(func=continuation_workspace_status_command)

    intent = workspace_subparsers.add_parser(
        "intent",
        help="declare concrete paths the active fenced owner intends to modify",
    )
    intent.add_argument("path", nargs="?", type=Path)
    intent.add_argument("--task-id", default=None)
    intent.add_argument("--lease-id", required=True)
    intent.add_argument("--generation", type=int, default=None)
    intent.add_argument("--fence-token", default=None)
    intent.add_argument("--path", dest="intent_path", action="append", required=True)
    add_json_argument(intent)
    intent.set_defaults(func=continuation_workspace_intent_command)

    reclassify = workspace_subparsers.add_parser(
        "reclassify",
        help="evidence-review unexpected dirty paths into task-owned or protected external ownership",
    )
    reclassify.add_argument("path", nargs="?", type=Path)
    reclassify.add_argument("--task-id", default=None)
    reclassify.add_argument("--lease-id", required=True)
    reclassify.add_argument("--generation", type=int, default=None)
    reclassify.add_argument("--fence-token", default=None)
    reclassify.add_argument(
        "--task-owned",
        dest="task_owned_path",
        action="append",
        default=[],
        help=(
            "reviewed unexpected path, or exact baseline-external recovery path, "
            "attributable to this task; repeat per path"
        ),
    )
    reclassify.add_argument(
        "--baseline-external",
        dest="baseline_external_path",
        action="append",
        default=[],
        help="reviewed unexpected path confirmed external to this task; repeat per path",
    )
    reclassify.add_argument("--evidence-ref", action="append", required=True)
    reclassify.add_argument("--reason", required=True)
    add_json_argument(reclassify)
    reclassify.set_defaults(func=continuation_workspace_reclassify_command)

    adopt = workspace_subparsers.add_parser(
        "adopt",
        help="explicitly classify every reviewed dirty path for a legacy task missing a workspace manifest",
    )
    adopt.add_argument("path", nargs="?", type=Path)
    adopt.add_argument("--task-id", default=None)
    adopt.add_argument(
        "--task-owned",
        dest="task_owned_path",
        action="append",
        default=[],
        help="reviewed changed path attributable to this continuation task; repeat per path",
    )
    adopt.add_argument(
        "--baseline-external",
        dest="baseline_external_path",
        action="append",
        default=[],
        help="reviewed changed path owned outside this continuation task; repeat per path",
    )
    adopt.add_argument("--evidence-ref", action="append", required=True)
    adopt.add_argument("--reason", required=True)
    add_json_argument(adopt)
    adopt.set_defaults(func=continuation_workspace_adopt_command)

    refresh = workspace_subparsers.add_parser(
        "refresh",
        help="refresh compact workspace ownership digests for the active fenced owner",
    )
    refresh.add_argument("path", nargs="?", type=Path)
    refresh.add_argument("--task-id", default=None)
    refresh.add_argument("--lease-id", required=True)
    refresh.add_argument("--generation", type=int, default=None)
    refresh.add_argument("--fence-token", default=None)
    add_json_argument(refresh)
    refresh.set_defaults(func=continuation_workspace_refresh_command)


def register_configure_parser(subparsers, add_json_argument) -> None:
    configure = subparsers.add_parser(
        "configure",
        help="update timing for an existing continuation task without re-initializing its state",
    )
    configure.add_argument("path", nargs="?", type=Path)
    configure.add_argument("--task-id", default=None)
    configure.add_argument("--profile", choices=tuple(sorted(TIMING_PROFILES)), default=None)
    configure.add_argument("--interval-minutes", type=int, default=None)
    configure.add_argument("--lease-ttl-minutes", type=int, default=None)
    configure.add_argument("--renew-interval-minutes", type=int, default=None)
    configure.add_argument("--heartbeat-interval-minutes", type=int, default=None)
    configure.add_argument("--stale-after-minutes", type=int, default=None)
    add_json_argument(configure)
    configure.set_defaults(func=continuation_configure_command)


__all__ = [
    "continuation_list_command",
    "continuation_migrate_command",
    "continuation_schema_contract",
    "continuation_init_command",
    "continuation_workspace_adopt_command",
    "continuation_workspace_intent_command",
    "continuation_workspace_reclassify_command",
    "continuation_workspace_refresh_command",
    "continuation_workspace_status_command",
    "load_workspace_manifest",
    "register_workspace_parsers",
    "workspace_current_snapshot",
    "workspace_error",
    "workspace_snapshot",
]
