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
    continuation_owner_context,
    continuation_recovery,
    continuation_rounds,
    continuation_workspace,
)
from ai_context_framework.automation_contracts import (
    automation_prompt_execution_contract,
    writer_continuous_execution_contract,
    writer_scheduler_wrapper_contract,
)
from ai_context_framework.commands import continuation_directives as continuation_directive_commands
from ai_context_framework.commands import continuation_workspace_parsers
from ai_context_framework.front_matter import parse_front_matter, split_typed_scope, validate_front_matter
from ai_context_framework.git_support import discover_git_project
from ai_context_framework.observability import acf_home
from ai_context_framework.sensitive_data import sanitize_public_payload
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
LEGACY_FENCE_TOKEN_FILE_ENV = "ACF_CONTINUATION_FENCE_TOKEN_FILE"

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
        "last_workspace_reconcile.json": {
            "current": [continuation_workspace.HANDOFF_RECONCILE_SCHEMA],
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


def _owner_context_error(exc: continuation_owner_context.OwnerContextError):
    core = _continuation()
    return core.ContinuationError(
        str(exc),
        code=exc.code,
        exit_code=3,
        next_actions=[
            "Use only the local owner_context.handle returned by the current claim/recover generation. "
            "Do not reconstruct or pass reusable authentication material in command text."
        ],
    )


def reject_legacy_owner_transport(args: argparse.Namespace | None = None) -> None:
    """Fail closed instead of silently accepting either legacy secret path."""

    legacy_argument = args is not None and getattr(args, "fence_token", None) is not None
    legacy_environment = LEGACY_FENCE_TOKEN_FILE_ENV in os.environ
    if not legacy_argument and not legacy_environment:
        return
    core = _continuation()
    raise core.ContinuationError(
        "legacy raw owner-credential transport is no longer accepted",
        code="legacy_owner_transport_refused",
        exit_code=3,
        details={"legacy_environment_present": legacy_environment},
        next_actions=[
            f"Remove {LEGACY_FENCE_TOKEN_FILE_ENV} and use the owner_context.handle returned by a fresh claim/recover."
        ],
    )


def deliver_owner_context(
    args: argparse.Namespace,
    paths: Mapping[str, Path],
    *,
    root: Path,
    control: Mapping[str, Any],
    lease: Mapping[str, Any],
    credential: str,
) -> continuation_owner_context.OwnerContext:
    """Create a local capability before committing a fresh owner generation."""

    reject_legacy_owner_transport(args)
    try:
        return continuation_owner_context.create_owner_context(
            paths["directory"],
            workspace_root=root,
            task_id=str(control["task_id"]),
            lease_id=str(lease["lease_id"]),
            generation=int(lease["generation"]),
            runner_id=str(lease["runner_id"]),
            credential=credential,
            created_at=str(lease["issued_at"]),
        )
    except continuation_owner_context.OwnerContextError as exc:
        raise _owner_context_error(exc) from exc


def resolve_owner_context(
    args: argparse.Namespace,
    paths: Mapping[str, Path],
    *,
    root: Path,
    control: Mapping[str, Any],
) -> continuation_owner_context.OwnerContext:
    reject_legacy_owner_transport(args)
    raw_handle = getattr(args, "owner_file", None)
    if raw_handle is None:
        raise _continuation().ContinuationError(
            "--owner-file is required for owner-protected commands",
            code="owner_context_required",
            exit_code=3,
        )
    try:
        context = continuation_owner_context.load_owner_context(
            raw_handle,
            paths["directory"],
            workspace_root=root,
            task_id=str(control["task_id"]),
        )
    except continuation_owner_context.OwnerContextError as exc:
        raise _owner_context_error(exc) from exc

    lease_assertion = getattr(args, "lease_id", None)
    if lease_assertion is not None and str(lease_assertion) != context.lease_id:
        raise _continuation().ContinuationError(
            "optional lease assertion does not match the owner context",
            code="owner_context_binding_mismatch",
            exit_code=3,
        )
    generation_assertion = getattr(args, "generation", None)
    if generation_assertion is not None and generation_assertion != context.generation:
        raise _continuation().ContinuationError(
            "optional generation assertion does not match the owner context",
            code="owner_context_binding_mismatch",
            exit_code=3,
        )
    return context


def assert_owner_context(
    args: argparse.Namespace,
    paths: Mapping[str, Path],
    *,
    root: Path,
    control: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    record_activity: bool = True,
) -> tuple[dict[str, Any], continuation_owner_context.OwnerContext]:
    """Resolve one handle and preserve the existing fenced-owner verifier."""

    core = _continuation()
    context = resolve_owner_context(args, paths, root=root, control=control)
    raw_lease = snapshot.get("lease")
    if isinstance(raw_lease, Mapping) and raw_lease.get("runner_id") != context.runner_id:
        raise core.ContinuationError(
            "owner context runner binding does not match the active lease",
            code="owner_context_binding_mismatch",
            exit_code=3,
        )
    verifier = core._assert_lease_owner_with_activity if record_activity else core._assert_lease_owner
    if record_activity:
        lease = verifier(
            paths,
            control,
            snapshot,
            lease_id=context.lease_id,
            fence_token=context.credential,
            generation=context.generation,
        )
    else:
        lease = verifier(
            snapshot,
            lease_id=context.lease_id,
            fence_token=context.credential,
            generation=context.generation,
        )
    return lease, context


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
        title = core._validate_public_input_text(args.title, field="title")
        objective = core._validate_public_input_text(args.objective, field="objective")
        stage = core._validate_public_input_text(args.stage or "bootstrap", field="stage")
        next_action = core._validate_public_input_text(
            args.next_action or "Refresh local authority and execute the current default plan.",
            field="next_action",
        )
        plan_refs = [
            core._validate_public_input_text(value, field="plan_ref")
            for value in (args.plan_ref or [])
        ]
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
            "workspace_reconcile": directory / "last_workspace_reconcile.json",
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
            "title": title,
            "objective": objective,
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
        state = {
            "schema_version": core.STATE_SCHEMA,
            "task_id": task_id,
            "objective": objective,
            "status": "ready",
            "stage": stage,
            "next_action": next_action,
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
                paths["workspace_reconcile"],
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
        continuous_execution_contract = writer_continuous_execution_contract()
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
            "stale_owner_wait_is_tool_backed": True,
            "stale_owner_wait_bound_source": "persisted_challenge_deadline",
            "challenge_pending_is_session_end_reason": False,
            "pure_idle_wait_required": False,
            "coordination_wait_grants_ownership": False,
            "same_activation_recovery_after_timeout": True,
            "same_activation_recovery_continues_project_work": True,
            "contender_continues_safe_read_only_when_available": True,
            "contender_must_create_busywork": False,
            "resume_hint_is_live_authority": False,
            "resume_hint_requires_authority_refresh": True,
            "timing_is_execution_duration_target": False,
            "platform_boundary_requires_explicit_signal": True,
            "release_is_default_end_step": False,
            "control_plane_checks_proportional_to_evidence_backed_risk": True,
            "prefer_cheapest_deterministic_safe_continuation": True,
            "genuine_ambiguity_behavior": "fail_closed",
            "safe_session_end_requires_graceful_handoff": True,
            "ghost_running_owner_allowed_at_safe_end": False,
            "verified_live_physical_execution_must_not_duplicate": True,
            "non_stop_signals": list(continuous_execution_contract["non_stop_signals"]),
            "timing_policy": dict(continuous_execution_contract["timing_policy"]),
            "execution_observability_contract": dict(
                continuous_execution_contract["execution_observability"]
            ),
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
        owner_context_migration_required = bool(
            (status_snapshot.get("owner_context_transport") or {}).get("migration_required")
        )
        caller_identity_known = runner_id is not None
        same_runner_owner = bool(
            lease_snapshot.get("state") == "active"
            and not owner_context_migration_required
            and runner_id
            and owner_runner_id
            and runner_id == owner_runner_id
        )
        fresh_owner_caller_unknown = bool(
            lease_snapshot.get("state") == "active"
            and not owner_context_migration_required
            and owner_liveness == "fresh"
            and not caller_identity_known
        )
        verified_live_other_owner = bool(
            lease_snapshot.get("state") == "active"
            and not owner_context_migration_required
            and owner_liveness == "fresh"
            and caller_identity_known
            and not same_runner_owner
        )
        stale_or_unverified_owner = bool(
            lease_snapshot.get("state") == "active"
            and not owner_context_migration_required
            and owner_liveness in {"stale", "legacy_unknown"}
            and not same_runner_owner
        )
        expired_owner = lease_snapshot.get("state") == "expired"
        owner_disposition = (
            "legacy_owner_context_migration_required"
            if owner_context_migration_required
            else "current_owner"
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
            "liveness_source": lease_snapshot.get("liveness_source"),
            "heartbeat_age_seconds": lease_snapshot.get("heartbeat_age_seconds"),
            "orphan_candidate": bool(lease_snapshot.get("orphan_candidate")),
            "physical_execution": lease_snapshot.get("physical_execution"),
            "verified_live": bool(owner_liveness == "fresh" and lease_snapshot.get("state") == "active"),
            "duplicate_wake_candidate": verified_live_other_owner,
            "can_claim": bool(status_snapshot.get("can_claim")),
            "blocked_reasons": list(status_snapshot.get("blocked_reasons") or []),
            "owner_context_transport": status_snapshot.get("owner_context_transport"),
        }
        latest_round = round_snapshot.get("latest")
        if not isinstance(latest_round, Mapping):
            latest_round = {}
        execution_observability = {
            "schema_version": "acf.continuation.execution-observability.v1",
            "timing_values_are_diagnostic_only": True,
            "fixed_timing_budget_allowed": False,
            "bootstrap_control_plane": {
                "owner_disposition": owner_disposition,
                "generation": owner_generation,
                "directive_revision": directive_context.get("revision"),
                "blocked_reasons": list(status_snapshot.get("blocked_reasons") or []),
            },
            "project_work": {
                "stage": state.get("stage"),
                "status": state.get("status"),
                "next_action": state.get("next_action"),
                "git_head": (status_snapshot.get("git") or {}).get("head"),
                "git_clean": (status_snapshot.get("git") or {}).get("clean"),
            },
            "physical_execution": {
                "tracked_effects_only": True,
                "journal_state": effect_snapshot.get("state"),
                "total": effect_summary.get("total", 0),
                "unresolved_count": len(unresolved_effects),
                "owner_probe": lease_snapshot.get("physical_execution"),
            },
            "graceful_handoff": {
                "owner_state": lease_snapshot.get("state"),
                "owner_liveness": owner_liveness,
                "latest_round_phase": latest_round.get("phase"),
                "latest_round_milestone": latest_round.get("milestone"),
                "explicit_safe_control_point_required": True,
            },
            "abnormal_incomplete_termination": {
                "orphan_candidate": bool(status_snapshot.get("orphan_candidate")),
                "expired_round_head_changed": bool(status_snapshot.get("expired_round_head_changed")),
                "recoverable_expired_round": bool(status_snapshot.get("recoverable_expired_round")),
                "effect_reconciliation_required": bool(status_snapshot.get("effect_reconciliation_required")),
            },
            "recovery_overhead": {
                "generation": owner_generation,
                "round_count": round_snapshot.get("count", 0),
                "diagnostic_counters_only": True,
            },
        }

        goal_summary_placeholder = "<current-goal-summary>"
        attempt_command = (
            f"acf continuation coordination attempt {json.dumps(str(root))}{task_flag} "
            f"--runner-id <runner> --objective-summary {goal_summary_placeholder} --json"
        )
        wait_command = (
            f"acf continuation coordination wait {json.dumps(str(root))}{task_flag} "
            "--challenge-id <challenge-id-from-attempt> --attempt-id <attempt-id-from-attempt> --json"
        )
        control_actions: list[str] = []
        conditional_sections: list[str] = []
        if owner_context_migration_required:
            control_actions.append(
                "The active lease predates the current owner-context transport or its current-generation capability is unavailable. Do not perform .90 owner-protected writes and do not restore raw-secret transport. Preserve any already-running pre-upgrade process; if it cannot release through its already-loaded old runtime, wait for stale/expired ownership and use formal reconcile/recover to mint a new owner context."
            )
            conditional_sections.append(
                "Owner-context migration hold:\n"
                "- This is a fail-closed compatibility state, not permission to take over the lease.\n"
                "- Do not reconstruct credentials from verifier state and do not use the retired raw-secret/token-file transport.\n"
                "- A still-live pre-upgrade physical process should be left undisturbed. If its original already-loaded runtime can release normally, let it finish; otherwise wait for stale/expired ownership, refresh evidence, and use the normal reconcile/recover path.\n"
                "- New recover creates a fresh generation-bound owner_context.handle."
            )
        elif same_runner_owner:
            control_actions.append(
                "Continue under the current local owner-context capability; assert ownership before protected non-idempotent work "
                "and heartbeat/renew according to lease liveness."
            )
            conditional_sections.append(
                "Current writer safety:\n"
                "- Before project writes, declare concrete workspace intent and preserve unrelated external dirty state.\n"
                "- Reuse only the local `owner_context.handle` returned by claim/recover on owner-protected commands; do not read, copy, or place its reusable credential material into command text, JSON, prompts, logs, or project files.\n"
                "- Before each non-idempotent or long-lived writer side effect, use deterministic effect identity; never replay an uncertain outcome.\n"
                "- For a deterministic local command that may cross the stale window, use `acf continuation execution run ... --key <key> -- <argv>`. It records exact process identity, keeps owner liveness, terminalizes on exit, and still requires polling the same DevSpace session to terminal.\n"
                "- Narrow ACF control-plane lifecycle exception: after the authenticated runner itself executes deterministic `acf workstream scope-add|merge-request|ready|merge-start|done` for the bound Workstream, the exact generated `docs/ai/active/Workstreams.md` plus that Workstream detail may be reviewed and committed as a dedicated control-plane checkpoint; this does not extend ordinary Task write scope or permit any third baseline/external path.\n"
                "- Checkpoints and Git commits are persistence points, not stop signals. At a genuine safe session end, persist current progress/next action/evidence and use the authenticated graceful handoff release mode so the long-lived mission remains running without leaving an active owner; do not hand off while safe useful work remains."
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
                    "Use the challenge id and contender attempt id returned by that attempt to block on the persisted deadline with `"
                    + wait_command
                    + "`. A pending challenge is not a session-end signal and does not require pure model idle waiting.",
                    "If wait returns `owner_active`, yield protected writes. If it returns `owner_released`, refresh doctor and claim normally when eligible. If it returns `timeout`, immediately refresh physical execution, HEAD, workspace, effect, and provenance evidence, then use formal reconcile/recover when eligible.",
                    "After successful timeout-backed recovery, continue safe useful project work in this same activation while the platform session still exists; timeout and wait never grant ownership by themselves.",
                ]
            )
            conditional_sections.append(
                "Stale or unverified owner recovery:\n"
                "- An active lease is not proof that another agent is still working. Verify liveness first.\n"
                "- A generation-bound active physical-execution record only counts as live when its persisted PID+start identity still probes as the exact same local process. Bare PIDs, unknown probes, and stale effect labels are not liveness evidence.\n"
                "- A stale-owner challenge provides challenge-backed verification and must be observed through the tool-backed `coordination wait`/`await` command when the current activation can continue. The tool reads the persisted challenge deadline; do not depend on pure model idle waiting and do not end merely because the challenge is pending.\n"
                "- `owner_active` means yield; `owner_released` means refresh and use the normal claim path; `timeout` only forfeits the old ownership claim and still requires fresh physical-execution/HEAD/workspace/effect/provenance evidence plus formal reconcile/recover. The wait command never grants ownership.\n"
                "- After successful recovery, continue safe useful project work in the same activation when the platform session remains available. Recovery remains receipt-bound and generation-fenced; a blocked recovery action does not prevent other safe diagnosis or evidence work."
            )
        elif expired_owner:
            control_actions.append(
                "The previous lease is expired. Use doctor/reconcile evidence to decide whether formal recover is required; do not re-claim through unresolved effects, HEAD drift, or workspace provenance ambiguity."
            )
            conditional_sections.append(
                "Expired-owner recovery:\n"
                "- Reconcile current workspace, HEAD, effect journal, identity, and prior generation before recovery when required.\n"
                "- Reuse the local `owner_context.handle` returned by recover; do not claim a second time after successful recovery and do not reconstruct raw owner authentication material in public command arguments."
            )
        elif status_snapshot.get("can_claim"):
            control_actions.extend(
                [
                    attempt_command,
                    "Use refreshed project authority to decide whether safe useful work is executable now. If the persisted/default plan explicitly waits for a real external or project-state change and that condition is not met, do not claim merely to manufacture a continuation lifecycle change; scheduler wake, coordination attempt, and claim are control-plane activity, not evidence satisfying that wait condition.",
                    f"If useful work is executable now, claim with `acf continuation claim {json.dumps(str(root))}{task_flag} --runner-id <runner> --json`, then re-render `acf continuation prompt {json.dumps(str(root))}{task_flag} --runner-id <runner> --json` with the same runner id before project writes so current-writer safety guidance is loaded.",
                    "If no safe useful work is presently executable, this scheduler wake may end without claiming and without changing task state; otherwise execute the refreshed default plan under the returned local owner-context capability after the post-claim prompt refresh.",
                ]
            )
            conditional_sections.append(
                "Claimable writer path:\n"
                "- The coordination attempt is a compact intent record, not a bounded work quota. `--objective-summary` names the current goal; it does not limit how much useful work the session may complete.\n"
                "- A scheduler wake, coordination attempt, or claim is control-plane bookkeeping. It must not be counted as the real/external state change required by a conditional wait plan, and it must not be used to create synthetic progress solely so the task can observe itself.\n"
                "- Claim only when refreshed authority identifies safe useful work that is executable now. If a wait condition is still unsatisfied and no other useful work exists, ending this wake without claim leaves the mission running and is not a pause, blocker, or completion.\n"
                "- Claim returns only a local `owner_context.handle` for owner-protected commands; reusable owner authentication material stays inside that local capability and is not a public CLI/JSON value.\n"
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
- The inbox is not a Task Plan: durable semantics require Markdown authority + evidence before adopt; consumed directives need explicit resolve/adopt/supersede/withdraw/keep-pending disposition. Reading alone is not adoption evidence.
- `resolve`, `withdraw`, and `supersede` remain distinct; pressure is mechanical observability only: {json.dumps(directive_context.get('pressure') or {}, ensure_ascii=False, sort_keys=True)}.
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
- Control-plane checks are risk-proportional: prefer the cheapest deterministic safe path; unchanged bookkeeping is not progress; genuine ambiguity stays fail-closed.
- The Agent chooses work scope, order, implementation strategy, and validation depth from current project authority.
- Mission open => search safe alternatives before no-work: diagnosis, adjacent gap, validation, contract, dogfood, release prep, diagnostics. Anti-busywork blocks only unchanged failure; prefer mission/PLAN stage; checkpoint => refresh and continue.
- Tests, fixes, commits, checkpoints, and Gates are progress evidence, not session-end signals.
- Active lease, abnormal generation, task-owned dirty, wake/checkpoint/test/commit/Gate, or one blocked lane are not stop signals; verified-live physical execution must never be duplicated.
- At genuine safe end, persist progress/next/evidence and use authenticated graceful handoff so the mission stays running without a stale owner. Timing/overhead telemetry is diagnostic only, never an execution budget.
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
            "execution_observability": execution_observability,
            "project_context": project_context,
            "scheduler_wrapper_contract": scheduler_wrapper_contract,
            "automation_prompt_execution_contract": automation_prompt_execution_contract(),
            "prompt": prompt,
            "next_actions": control_actions,
        }
        public_value = sanitize_public_payload(value)
        assert isinstance(public_value, dict)
        result_holder.update(public_value)
        return public_value

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
            lease, _owner_context = assert_owner_context(
                args,
                paths,
                root=root,
                control=control,
                snapshot=lease_snapshot,
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
            lease, _owner_context = assert_owner_context(
                args,
                paths,
                root=root,
                control=control,
                snapshot=lease_snapshot,
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
            evidence_refs = [
                core._validate_public_input_text(value, field="evidence_ref")
                for value in (args.evidence_ref or [])
            ]
            reason = core._validate_public_input_text(args.reason, field="reason")
            try:
                manifest, review = continuation_workspace.reclassify_unexpected(
                    manifest,
                    task_id=str(control["task_id"]),
                    snapshot=workspace_current_snapshot(root),
                    task_owned_paths=task_paths,
                    baseline_external_paths=external_paths,
                    allowed_scopes=allowed_scopes,
                    candidate_paths=candidate_paths,
                    evidence_refs=evidence_refs,
                    reason=reason,
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


def continuation_workspace_reconcile_handoff_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            lease_snapshot = core._lease_snapshot(paths, control)
            if lease_snapshot["state"] != "absent":
                raise core.ContinuationError(
                    "ownerless handoff reconciliation requires no lease record",
                    code="workspace_handoff_reconcile_owner_present",
                    exit_code=3,
                    details={"lease_state": lease_snapshot["state"]},
                    next_actions=[
                        "Use the active-owner workspace flow, or formally resolve/recover the interrupted owner first."
                    ],
                )

            state = core._load_state(paths)
            if state["status"] not in {*core.RUNNABLE_STATUSES, "running"}:
                raise core.ContinuationError(
                    "ownerless handoff reconciliation requires a runnable long-lived continuation",
                    code="workspace_handoff_reconcile_state_invalid",
                    exit_code=3,
                    details={"state_status": state["status"]},
                )

            rounds = core._load_round_journal(paths, control, require_existing=True)
            latest_round = continuation_rounds.latest_round(
                rounds,
                task_id=str(control["task_id"]),
            )
            if not isinstance(latest_round, Mapping) or (
                latest_round.get("phase") != "released"
                or latest_round.get("milestone") != "released_to_running_handoff"
            ):
                raise core.ContinuationError(
                    "ownerless workspace reconciliation is only valid after an explicit graceful running handoff",
                    code="workspace_handoff_reconcile_not_handoff",
                    exit_code=3,
                    details={"latest_round": latest_round},
                )

            effects = core._load_effect_journal(paths, control)
            effect_summary = continuation_rounds.effect_summary(
                effects,
                task_id=str(control["task_id"]),
            )
            unresolved_effects = list(effect_summary.get("unresolved") or [])
            if unresolved_effects:
                raise core.ContinuationError(
                    "ownerless handoff reconciliation refuses unresolved effects",
                    code="workspace_handoff_reconcile_effects_unresolved",
                    exit_code=3,
                    details={"unresolved_effects": unresolved_effects},
                    next_actions=[
                        "Reconcile durable effect identity/outcome before accepting ownerless workspace cleanup."
                    ],
                )

            manifest = load_workspace_manifest(paths, control, require_existing=True)
            assert manifest is not None
            if int(manifest["generation"]) != int(latest_round["generation"]):
                raise core.ContinuationError(
                    "workspace manifest generation does not match the released handoff generation",
                    code="workspace_generation_mismatch",
                    exit_code=3,
                    details={
                        "workspace_generation": manifest["generation"],
                        "handoff_generation": latest_round["generation"],
                    },
                )

            raw_cleanup_paths = list(dict.fromkeys(args.cleanup_path or []))
            if not raw_cleanup_paths:
                raise core.ContinuationError(
                    "ownerless handoff reconciliation requires --cleanup",
                    code="workspace_handoff_reconcile_incomplete",
                )
            evidence_refs = list(dict.fromkeys(args.evidence_ref or []))
            evidence_refs = [
                core._validate_public_input_text(value, field="evidence_ref")
                for value in evidence_refs
            ]
            reason = core._validate_public_input_text(args.reason, field="reason")
            accepted_head = (
                core._validate_public_input_text(args.accept_head, field="accepted_head")
                if args.accept_head
                else None
            )
            try:
                manifest, receipt = continuation_workspace.reconcile_handoff_cleanup(
                    manifest,
                    task_id=str(control["task_id"]),
                    snapshot=workspace_current_snapshot(root),
                    cleanup_paths=raw_cleanup_paths,
                    accepted_head=accepted_head,
                    evidence_refs=evidence_refs,
                    reason=reason,
                    receipt_id=str(uuid.uuid4()),
                    now=core._iso(),
                )
            except continuation_workspace.ContinuationWorkspaceError as exc:
                error = workspace_error(exc)
                error.exit_code = 3
                raise error from exc

            core._write_json(paths["workspace"], manifest)
            core._write_json(paths["workspace_reconcile"], receipt)
            refreshed = core._status(root, str(control["task_id"]))
            return {
                "status": "workspace_handoff_reconciled",
                "task_id": control["task_id"],
                "generation": manifest["generation"],
                "receipt": receipt,
                "workspace": continuation_workspace.summary(
                    manifest,
                    task_id=str(control["task_id"]),
                ),
                "can_claim": bool(refreshed.get("can_claim")),
                "blocked_reasons": list(refreshed.get("blocked_reasons") or []),
                "next_action": (
                    "Re-run `acf continuation doctor`; if no other blocker remains, register coordination intent and claim normally."
                ),
            }

    return core._guarded(args, "continuation workspace reconcile-handoff", operation)


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
            evidence_refs = [
                core._validate_public_input_text(value, field="evidence_ref")
                for value in (args.evidence_ref or [])
            ]
            reason = core._validate_public_input_text(args.reason, field="reason")
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
                    evidence_refs=evidence_refs,
                    reason=reason,
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
            lease, _owner_context = assert_owner_context(
                args,
                paths,
                root=root,
                control=control,
                snapshot=lease_snapshot,
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
            if not str(args.reason or "").strip():
                raise core.ContinuationError(
                    "--reason is required with --apply",
                    code="continuation_migration_invalid",
                )
            reason = core._validate_public_input_text(args.reason, field="reason")
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


register_workspace_parsers = continuation_workspace_parsers.register_workspace_parsers
register_configure_parser = continuation_workspace_parsers.register_configure_parser


__all__ = [
    "continuation_list_command",
    "continuation_migrate_command",
    "continuation_schema_contract",
    "continuation_init_command",
    "continuation_workspace_adopt_command",
    "continuation_workspace_intent_command",
    "continuation_workspace_reconcile_handoff_command",
    "continuation_workspace_reclassify_command",
    "continuation_workspace_refresh_command",
    "continuation_workspace_status_command",
    "load_workspace_manifest",
    "register_workspace_parsers",
    "workspace_current_snapshot",
    "workspace_error",
    "workspace_snapshot",
]
