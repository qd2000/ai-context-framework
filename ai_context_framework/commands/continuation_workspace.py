"""CLI adapter for bounded continuation workspace ownership.

The durable workspace model lives in :mod:`ai_context_framework.continuation_workspace`.
This module keeps the command wiring and Workstream-scope integration out of the
main continuation controller so both surfaces remain small enough to review.
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any, Mapping

from ai_context_framework import (
    continuation_coordination,
    continuation_inventory,
    continuation_recovery,
    continuation_rounds,
    continuation_workspace,
)
from ai_context_framework.front_matter import split_typed_scope
from ai_context_framework.git_support import discover_git_project
from ai_context_framework.observability import acf_home
from ai_context_framework.runtime_parts.archive_workstream import (
    normalize_scope_path,
    read_workstream_detail,
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
    detail = read_workstream_detail(project.context_root, workstream_id)
    kind = str(detail.metadata.get("type") or "Task")
    merge_owner = detail.metadata.get("merge_owner")
    coordination = detail.metadata.get("coordination")
    raw_scopes = detail.metadata.get("write_scope")
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
            "next_action": str(args.next_action or "Run continuation doctor and the next bounded gate.").strip(),
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
        task_flag = f" --task-id {json.dumps(control['task_id'])}"
        plan_refs = list(state.get("plan_refs") or [])
        constraints = list(state.get("constraints") or [])

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
            "next_action_is_work_quota": False,
            "checkpoint_is_stop": False,
            "commit_is_stop": False,
            "gate_completion_is_stop": False,
            "final_response_is_terminal": True,
            "final_response_requires_session_end_reason": True,
            "session_end_requires_no_safe_useful_work": True,
            "progress_report_is_session_end_reason": False,
            "elapsed_time_is_session_end_reason": False,
            "startup_probe_is_session_end_reason": False,
            "active_owner_is_session_end_reason": False,
            "contender_continues_safe_read_only_when_available": True,
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
                    "The thin scheduler wrapper must add project-specific constraints that are not "
                    "already represented by local plan refs or continuation state, without copying "
                    "the generic continuation state machine."
                ),
            },
        }
        prompt = f"""Use the fixed local Git worktree below as the authoritative execution target.

Task: {control['task_id']} — {control['title']}
Worktree: {root}
Branch: {control['expected_branch']}

Resume context:
- Current stage: {state['stage']}
- Current status: {state['status']}
- Resume hint: {state['next_action']}

The stage/status/resume hint above are compact persisted recovery metadata, not live authority. They may lag newer Git/project evidence, continuation effects, Runtime state, or other external authority. Before acting on the resume hint, refresh local authority with `acf continuation doctor`, inspect the effect journal when relevant, and perform the project-specific evidence/Runtime checks required by the wrapper. Newer authoritative evidence supersedes the hint; never replay an already-observed side effect merely because the hint is old.
The resume hint is only an entry point recovered from persisted state. It is not a work quota, the only task allowed now, or a stopping boundary.
Render-time continuation journal summary: rounds={resume_context['round_journal']['count']}; effects={resume_context['effect_journal']['total']}; unresolved_effects={resume_context['effect_journal']['unresolved_count']}; effect_statuses={json.dumps(resume_context['effect_journal']['by_status'], ensure_ascii=False, sort_keys=True)}.

Project plan references:
{render_items(plan_refs, empty="No plan reference is currently recorded.")}

Project-specific constraints recorded in continuation state:
{render_items(constraints, empty="No compact project constraint is currently recorded in continuation state.")}

The thin scheduler wrapper must additionally provide any project-specific tooling, Runtime, resource/VM/node, permission, security, scientific, validation, and issue-reporting constraints that are not already represented above. These additions are project authority; they must not copy or redefine the generic continuation state machine.

Generic Scheduled Task protocol authority: this generated prompt is the only generic continuation state-machine contract. External wrappers should keep only fixed project/worktree/branch/task identity plus project-specific constraints, invoke `acf continuation prompt` again on every scheduler wake, and not freeze a second copy of the contention/recovery/workspace/effect protocol.

Continuous execution contract:
- A scheduler wake is only a resume signal for one continuous task. It does not define a work round, reporting interval, work quota, expected stopping point, or Gate deadline.
- Bounded continuation limits ownership, write scope, external side effects, and recovery risk. It does not limit how much useful work the Agent may complete during the current execution session.
- The Agent chooses the most effective work scope, order, implementation strategy, and validation depth from the overall local objective, plans, constraints, and evidence.
- After a subtask, test, fix, commit, checkpoint, or Gate, reassess the local facts and continue with the next safe, non-repetitive, valuable action while the overall objective remains open.
- Checkpoints persist progress, commits record natural semantic checkpoints, and Gates open the next decision. They are not session-end signals.
- A final assistant response ends the current execution session. Do not produce one merely to report progress, summarize completed work, or create a neat stopping point. If the overall objective remains open and safe, non-repetitive, valuable work can continue now, keep using tools and continue the task.
- Elapsed time, tool-call count, perceived context length, the number of completed steps, successful tests, commits, checkpoints, Gates, or a desire to update the user are not session-end reasons.
- Startup probes such as `prompt`, `doctor`, `coordination attempt`, or `coordination status` are evidence-gathering steps, not session-end reasons by themselves.
- A safety refusal blocks only the specific unsafe claim, write, recovery, or side effect. Continue safe diagnosis, evidence review, issue recording, planning, testing, or other non-conflicting work when available.
- Do not repeat an unchanged failed action when no input, evidence, environment, or strategy has changed. Diagnose, narrow the reproduction, change conditions, choose another approach, or wait for an explicit external state change.

Task-level hard-stop conditions are limited to exactly these four cases:
1. The overall objective is genuinely complete with required evidence.
2. The user explicitly pauses the task.
3. New human authorization, credentials, or a non-delegable decision are required.
4. The configured project-access tool or connection, such as DevSpace, remains unavailable after reasonable reconnect attempts.

The safety rules below apply when their condition is relevant. They are not a sequential checklist, and reaching the last section is not a reason to end the execution session.

Startup and ownership:
- Reconstruct current task state from local project plans/evidence and persisted continuation state, not chat history by default. Inspect with `acf continuation doctor {json.dumps(str(root))}{task_flag} --json`.
- Register the runner with `acf continuation coordination attempt {json.dumps(str(root))}{task_flag} --runner-id <runner> --objective-summary <bounded-objective> --json` before trying to obtain writer ownership. An attempt is not ownership.
- If doctor reports `can_claim=true` and no active owner was observed, claim one execution lease with `acf continuation claim {json.dumps(str(root))}{task_flag} --runner-id <runner> --json`. A lease bounds ownership and safety, not work quantity. Keep the returned lease_id, generation, and fence_token private to the current owner session.

Contention and recovery:
- If another owner exists, the attempt becomes a contender and opens or joins the challenge for that owner generation. Do not impersonate the owner or modify protected project files. Safe non-conflicting read-only work may continue.
- Another fresh authenticated owner is not, by itself, a session-end reason. After becoming a contender, continue safe useful read-only authority/evidence refresh when available; do not jump directly from owner detection to a final response.
- `ACF continuation challenge pending` from ordinary project-locatable ACF commands is only an informational probe. Inspect with `acf continuation coordination status {json.dumps(str(root))}{task_flag} --json`; ordinary commands do not ACK a challenge or grant ownership.
- A valid owner-protected continuation command authenticated by lease_id + generation + fence_token resolves a pending challenge as `owner_active`; normal release resolves it as `owner_released`.
- Challenge timeout / `ownership_forfeiture_candidate` forfeits only the old ownership claim; it does not grant write access or prove the old process ended. Use formal `acf continuation reconcile ... --json` and `acf continuation recover ... --reconcile-id <receipt_id> --runner-id <runner> --json` with workspace/HEAD/effect/identity evidence. Reuse credentials returned by recover rather than claiming again.
- If recovery of a specific action remains fail-closed, do not perform that blocked action. Continue other safe diagnosis, evidence collection, issue recording, planning, testing, or non-conflicting work when available.

Workspace writes:
- Inspect ownership with `acf continuation workspace status ... --json`. Before modifying project files, declare concrete paths with `acf continuation workspace intent ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --path <path> ... --json`; a bound Workstream intent must remain inside its direct write scope.
- Protect baseline/external dirty state; do not stash, reset, clean, stage, or commit unrelated external changes.
- If a reviewed durable writer output was not declared before launch and appears as `unexpected_nonoverlap`, use fenced `workspace reclassify --task-owned <path> --evidence-ref <durable-ref> --reason <review>` only after proving provenance. Uncertain output remains external/fail-closed.
- Refresh workspace ownership after writes and before an actual handoff with `acf continuation workspace refresh ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json` so task-owned, external, and conflict paths remain explicit.

Ownership liveness:
- Timing profile: {control['timing_profile']}; scheduler wake {control['interval_minutes']} min; lease TTL {control['lease_ttl_minutes']} min; heartbeat recommendation {control['heartbeat_interval_minutes']} min; stale threshold {control['stale_after_minutes']} min; renew recommendation {control['renew_interval_minutes']} min.
- These values govern lease liveness only. They are not execution-duration targets, work quotas, reporting intervals, or reasons to stop.
- Before protected non-idempotent work, verify ownership with `acf continuation assert-owner ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json`. For long work, use `acf continuation heartbeat ...` at roughly the configured cadence and `acf continuation renew ...` before the renew threshold; heartbeat proves liveness but does not extend TTL.
- A long-running purely read-only/blocking call does not need a writer effect identity, but after it returns and before the next project write or non-idempotent action, re-run `assert-owner`.

External and non-idempotent side effects:
- Before each such side effect, establish its deterministic identity with `acf continuation effect prepare ... --key <logical-key> --kind <generic-kind> --json`. This includes long-lived local subprocesses, DevSpace sessions, Runtime jobs, or external jobs that may outlive the current owner/tool call and later write project files or create a non-idempotent effect.
- Execute the side effect only when prepare returns `created=true`. `created=false` means inspect/reuse/reconcile the existing logical effect rather than resubmitting it.
- Persist a reusable external/job identity after launch and keep the effect `prepared|active|unknown` until authoritative terminal observation. Update compact status with `acf continuation effect update ...`; use `acf continuation effect list ... --json` to inspect durable identities.
- If outcome is uncertain, preserve the effect for reconciliation and never resubmit from memory. If no durable identity can be persisted, the writer must not cross an owner lifecycle while termination remains unproven.

Progress and checkpoints:
- Continuously advance the overall local objective while ownership is valid. Record compact runtime-neutral progress when useful with `acf continuation progress ... --phase <phase> --milestone <compact-name> --evidence-ref <durable-ref> --json`; do not copy raw tool output or transcript history into continuation state.
- Validate completed work enough to choose the next safe action. A dirty task-owned worktree does not by itself require a Git commit or handoff; create commits only at natural project semantic checkpoints and never include unrelated external dirty.
- Update compact persisted state when useful with `acf continuation checkpoint ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> ... --json`. Checkpointing does not require release.

Actual handoff or session end:
- Continue is the default while the objective is open and safe, useful work can be done now. Another authenticated owner, a durable external wait, or a fail-closed action justifies handoff only when it actually leaves no safe, useful, non-conflicting work available now.
- A contender may end the current session only after safe useful non-conflicting work has actually been exhausted, or when an explicit task-level hard stop or platform termination signal applies. State that concrete session-end reason in the final response.
- Do not guess a platform boundary. Treat it as real only when the platform, system, or tool provides an explicit signal that the current execution is about to terminate; elapsed time, perceived context usage, completed work, or a subjective sense that it is time to wrap up are not such signals.
- If the current execution session really must end, preserve accurate resumable state and a concrete next action. Do not mark the mission paused, blocked_human, or done unless one of the four task-level hard-stop conditions actually applies.
- If this runner owns a live lease and the session is actually ending, refresh/checkpoint as useful and release with `acf continuation release ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json` before final response. Release is not a default final step and is not triggered by progress reporting, commits, checkpoints, tests, or Gates.

Reusable product issues:
- When this work exposes a concrete reusable ACF/continuation/workflow defect or operational gap, record it with `acf continuation issue {json.dumps(str(root))}{task_flag} --category <category> --severity <low|medium|high|critical> --text <concise issue> --evidence-ref <path-or-commit> --json`. Do not record normal active-lease no-ops, expected waits, or task-specific scientific failures as product issues.
"""
        identity = {
            "workspace_root": str(root),
            "branch": control["expected_branch"],
            "task_id": control["task_id"],
            "workstream_id": control.get("workstream_id"),
        }
        scheduler_wrapper_contract = {
            "schema_version": "acf.continuation.scheduler_wrapper.v1",
            "generic_protocol_source": "acf continuation prompt",
            "refresh_prompt_each_run": True,
            "identity": identity,
            "project_constraint_classes": project_context["wrapper_constraint_slot"]["classes"],
            "project_specific_constraints_slot": project_context["wrapper_constraint_slot"],
            "copy_generic_state_machine": False,
        }
        value = {
            "status": "rendered",
            "task_id": control["task_id"],
            "identity": identity,
            "current": {
                "stage": state["stage"],
                "status": state["status"],
                "next_action": state["next_action"],
            },
            "resume_context": resume_context,
            "execution_policy": execution_policy,
            "project_context": project_context,
            "scheduler_wrapper_contract": scheduler_wrapper_contract,
            "prompt": prompt,
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
                fence_token=args.fence_token,
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
                fence_token=args.fence_token,
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
                    next_actions=["Let the active owner finish or use the generated challenge/recovery protocol."],
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
                fence_token=args.fence_token,
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
        help="reviewed unexpected path attributable to this task; repeat per path",
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
