"""CLI adapter for bounded continuation workspace ownership.

The durable workspace model lives in :mod:`ai_context_framework.continuation_workspace`.
This module keeps the command wiring and Workstream-scope integration out of the
main continuation controller so both surfaces remain small enough to review.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from ai_context_framework import continuation_workspace
from ai_context_framework.front_matter import split_typed_scope
from ai_context_framework.git_support import discover_git_project
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
        task_flag = f" --task-id {json.dumps(control['task_id'])}"
        prompt = f"""Use the fixed local Git worktree below as the authoritative execution target.

Task: {control['task_id']} — {control['title']}
Worktree: {root}
Branch: {control['expected_branch']}
Current stage: {state['stage']}
Current status: {state['status']}
Next action: {state['next_action']}

Timing profile: {control['timing_profile']}
Scheduler interval: every {control['interval_minutes']} minutes
Lease TTL: {control['lease_ttl_minutes']} minutes
Heartbeat recommendation: every {control['heartbeat_interval_minutes']} minutes
Stale threshold: {control['stale_after_minutes']} minutes
Renew recommendation: every {control['renew_interval_minutes']} minutes
The scheduler interval is only a wake cadence; it is not a round/Gate deadline.

Continuation protocol:
1. Do not reconstruct task state from chat history by default. Read local project plans/evidence and `acf continuation doctor` first.
2. Run `acf continuation doctor {json.dumps(str(root))}{task_flag} --json`.
3. If `can_claim` is false, never copy an old lease id to impersonate its owner. A fresh active owner means no-op. For stale/orphan_candidate, legacy_unknown, changed HEAD, or effect reconciliation signals, use `acf continuation reconcile ... --json` to inspect the exact recovery blockers. Only after external/local evidence proves the prior owner ended, all effects are resolved/reusable, and any advanced HEAD is explicitly accepted may you record an eligible receipt with `acf continuation reconcile ... --owner-ended --accept-head <current-head-if-needed> --evidence-ref <durable-ref> --reason <concise-reason> --record --json`, then fence the old owner with `acf continuation recover ... --reconcile-id <receipt_id> --runner-id <runner> --json`. If reconcile remains blocked by a true identity/effect/workspace conflict, stop without modifying the worktree.
4. If `can_claim` is true, claim one bounded round with `acf continuation claim {json.dumps(str(root))}{task_flag} --runner-id <runner> --json`. If step 3 recovered an orphan instead, use the credentials returned by `recover` and do not claim again. Keep the returned lease_id, generation, and fence_token; treat fence_token as an owner credential and do not copy it into project files or logs.
5. Execute only the current bounded gate. Record compact runtime-neutral progress with `acf continuation progress ... --phase <phase> --milestone <compact-name> --evidence-ref <durable-ref> --json`; do not copy raw tool output or transcript history into continuation state.
6. Inspect workspace ownership with `acf continuation workspace status ... --json`. Before modifying project files, declare the concrete paths with `acf continuation workspace intent ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --path <path> ... --json`. A bound Workstream intent must remain inside its direct write scope. Existing baseline/external dirty is protected; do not stash, reset, clean, stage, or commit it. After writes and before handoff/finalization, refresh ownership with `acf continuation workspace refresh ...` so task-owned, unrelated external, and true path conflicts are explicit.
7. Before protected non-idempotent work, verify ownership with `acf continuation assert-owner ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json`. For long work, record liveness with `acf continuation heartbeat ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json` at roughly the configured heartbeat cadence and extend TTL with `acf continuation renew ...` before the renew threshold; heartbeat proves liveness but does not extend TTL.
8. Before executing each external/non-idempotent side effect, write its deterministic identity first with `acf continuation effect prepare ... --key <logical-key> --kind <generic-kind> --json`. Execute the side effect only when prepare returns `created=true`; `created=false` means the logical effect already exists and must be inspected/reused/reconciled rather than resubmitted. After authoritative observations, update only compact status/milestone/external-id/evidence references with `acf continuation effect update ...`. If an outcome is uncertain, stop and preserve the effect for reconciliation; never resubmit it from memory. Use `acf continuation effect list ... --json` to inspect durable effect identities.
9. Validate the bounded gate enough for safe handoff. A continuation handoff does not require a Git commit merely because the worktree is dirty; create a Git checkpoint only when the project has reached a natural semantic checkpoint. Never include unrelated external dirty in a commit.
10. Update bounded state with `acf continuation checkpoint ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> ... --json`.
11. Release the same lease with `acf continuation release ... --lease-id <lease_id> --generation <generation> --fence-token <fence_token> --json`. Preserved task WIP may remain uncommitted across rounds; only true workspace conflict/ambiguous provenance, identity mismatch, unresolved effect, paused/blocked state, or unknown write outcome should fail closed.
12. If this round exposes a concrete reusable ACF/continuation/workflow defect or operational gap, record it immediately with `acf continuation issue {json.dumps(str(root))}{task_flag} --category <category> --severity <low|medium|high|critical> --text <concise issue> --evidence-ref <path-or-commit> --json`. Do not record normal active-lease no-ops, expected waits, or task-specific scientific failures as product issues.
"""
        value = {"status": "rendered", "task_id": control["task_id"], "prompt": prompt}
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
            lease = core._assert_lease_owner(
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


def continuation_workspace_refresh_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            lease_snapshot = core._lease_snapshot(paths, control)
            lease = core._assert_lease_owner(
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


def register_workspace_parsers(subparsers, add_json_argument) -> None:
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
    "continuation_init_command",
    "continuation_workspace_intent_command",
    "continuation_workspace_refresh_command",
    "continuation_workspace_status_command",
    "load_workspace_manifest",
    "register_workspace_parsers",
    "workspace_current_snapshot",
    "workspace_error",
    "workspace_snapshot",
]
