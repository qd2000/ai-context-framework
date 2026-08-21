"""CLI adapter for bounded continuation attempt/challenge coordination.

The durable state model is intentionally separate from ownership transfer.
This adapter can register contenders and open/join one challenge for the
currently observed owner generation, but it never grants write ownership or
declares an owner dead.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

from ai_context_framework import continuation_coordination


def _continuation():
    # Imported lazily because the main continuation controller imports this
    # adapter for command aliases and parser registration.
    from ai_context_framework.commands import continuation

    return continuation


def coordination_error(exc: continuation_coordination.ContinuationCoordinationError):
    core = _continuation()
    return core.ContinuationError(str(exc), code=exc.code, exit_code=3)


def load_coordination_state(
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
    *,
    now: str,
) -> dict[str, Any]:
    core = _continuation()
    path = paths["coordination"]
    if not path.exists():
        return continuation_coordination.new_state(task_id=str(control["task_id"]), now=now)
    try:
        payload = core._read_json(path, label="coordination")
        return continuation_coordination.validate_state(payload, task_id=str(control["task_id"]))
    except continuation_coordination.ContinuationCoordinationError as exc:
        raise coordination_error(exc) from exc


def refresh_coordination_timeouts(
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
    *,
    now: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    core = _continuation()
    state = load_coordination_state(paths, control, now=now)
    try:
        state, timed_out = continuation_coordination.advance_timeouts(
            state,
            task_id=str(control["task_id"]),
            now=now,
        )
    except continuation_coordination.ContinuationCoordinationError as exc:
        raise coordination_error(exc) from exc
    if timed_out:
        core._write_json(paths["coordination"], state)
    return state, timed_out


def challenge_deadline(
    control: Mapping[str, Any],
    *,
    deadline_minutes: int | None,
    now_dt,
) -> tuple[int, str]:
    core = _continuation()
    minutes = int(deadline_minutes or control["heartbeat_interval_minutes"])
    if minutes < 1 or minutes >= int(control["lease_ttl_minutes"]):
        raise core.ContinuationError(
            "challenge deadline must be positive and shorter than lease TTL",
            code="coordination_deadline_invalid",
        )
    return minutes, core._iso(now_dt + timedelta(minutes=minutes))


def record_authenticated_owner_activity(
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
    lease: Mapping[str, Any],
    *,
    now: str,
) -> dict[str, Any] | None:
    core = _continuation()
    owner_generation = lease.get("generation")
    if (
        isinstance(owner_generation, bool)
        or not isinstance(owner_generation, int)
        or owner_generation < 1
    ):
        # Legacy active leases remain readable/renewable through their
        # compatibility path.  They predate generation fencing, so they cannot
        # safely authenticate a generation-bound challenge response.
        return None
    state, timed_out = refresh_coordination_timeouts(paths, control, now=now)
    try:
        state, acknowledged = continuation_coordination.acknowledge_owner_activity(
            state,
            task_id=str(control["task_id"]),
            owner_generation=owner_generation,
            lease_id=str(lease["lease_id"]),
            runner_id=str(lease["runner_id"]),
            now=now,
        )
    except continuation_coordination.ContinuationCoordinationError as exc:
        raise coordination_error(exc) from exc
    if acknowledged is not None:
        core._write_json(paths["coordination"], state)
    elif timed_out:
        # refresh_coordination_timeouts already persisted the timeout transition.
        pass
    return acknowledged


def record_owner_release(
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
    lease: Mapping[str, Any],
    *,
    now: str,
) -> dict[str, Any] | None:
    core = _continuation()
    owner_generation = lease.get("generation")
    if (
        isinstance(owner_generation, bool)
        or not isinstance(owner_generation, int)
        or owner_generation < 1
    ):
        return None
    state, timed_out = refresh_coordination_timeouts(paths, control, now=now)
    try:
        state, resolved = continuation_coordination.resolve_owner_release(
            state,
            task_id=str(control["task_id"]),
            owner_generation=owner_generation,
            lease_id=str(lease["lease_id"]),
            runner_id=str(lease["runner_id"]),
            now=now,
        )
    except continuation_coordination.ContinuationCoordinationError as exc:
        raise coordination_error(exc) from exc
    if resolved is not None:
        core._write_json(paths["coordination"], state)
    elif timed_out:
        pass
    return resolved


def owner_summary(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    raw_lease = snapshot.get("lease")
    lease = raw_lease if isinstance(raw_lease, Mapping) else {}
    return {
        "state": snapshot.get("state"),
        "generation": lease.get("generation"),
        "runner_id": lease.get("runner_id"),
        "lease_id": lease.get("lease_id"),
        "liveness": snapshot.get("liveness"),
        "orphan_candidate": bool(snapshot.get("orphan_candidate")),
    }


def pending_challenge_probe(root: Path) -> list[dict[str, Any]]:
    """Return bounded pending challenge hints without changing ownership state.

    The top-level CLI calls this after ordinary project commands.  It is
    deliberately fail-open and read-only: unauthenticated ACF activity may
    surface a challenge, but it must never become an owner ACK or grant write
    authority.
    """
    core = _continuation()
    try:
        workspace_root = core._workspace_root(root)
        parent = core._task_parent(workspace_root)
    except Exception:
        return []
    if not parent.is_dir():
        return []

    now = core._iso()
    findings: list[dict[str, Any]] = []
    candidates = sorted(
        path
        for path in parent.iterdir()
        if path.is_dir()
        and (path / "control.json").is_file()
        and (path / "coordination.json").is_file()
    )
    for directory in candidates:
        try:
            raw_control = core._read_json(directory / "control.json", label="control")
            task_id = str(raw_control.get("task_id") or "").strip()
            if not task_id:
                continue
            paths = core._paths(workspace_root, task_id)
            control = core._load_control(paths, workspace_root)
            lease_snapshot = core._lease_snapshot(paths, control)
            if lease_snapshot.get("state") != "active":
                continue
            raw_lease = lease_snapshot.get("lease")
            if not isinstance(raw_lease, Mapping):
                continue
            owner_generation = raw_lease.get("generation")
            if (
                isinstance(owner_generation, bool)
                or not isinstance(owner_generation, int)
                or owner_generation < 1
            ):
                continue
            state = load_coordination_state(paths, control, now=now)
            coordination = continuation_coordination.summary(
                state,
                task_id=str(control["task_id"]),
                now=now,
            )
        except Exception:
            continue
        for challenge in coordination["nonterminal_challenges"]:
            if challenge["owner_generation"] != owner_generation:
                continue
            findings.append(
                {
                    "task_id": str(control["task_id"]),
                    "challenge_id": challenge["challenge_id"],
                    "owner_generation": challenge["owner_generation"],
                    "status": challenge["status"],
                    "deadline_at": challenge["deadline_at"],
                    "deadline_passed": bool(challenge["deadline_passed"]),
                    "ownership_forfeiture_candidate": bool(
                        challenge["ownership_forfeiture_candidate"]
                    ),
                    "contender_count": len(challenge["contender_attempt_ids"]),
                }
            )
            if len(findings) >= 8:
                return findings
    return findings


def _probe_workspace_root(args: argparse.Namespace) -> Path | None:
    core = _continuation()
    candidates: list[Path] = []
    for field in ("path", "context", "target"):
        value = getattr(args, field, None)
        if isinstance(value, (str, Path)):
            candidates.append(Path(value))
    candidates.append(Path.cwd())
    for candidate in candidates:
        try:
            location = candidate.expanduser().resolve()
            if location.is_file():
                location = location.parent
            return core._workspace_root(location)
        except (Exception, SystemExit):
            continue
    return None


def emit_pending_challenge_probe(args: argparse.Namespace) -> None:
    """Surface pending challenges without changing command success or ownership."""
    root = _probe_workspace_root(args)
    if root is None:
        return
    try:
        findings = pending_challenge_probe(root)
    except (Exception, SystemExit):
        return
    if not findings:
        return

    shown = findings[:3]
    for finding in shown:
        status = str(finding["status"])
        if finding["ownership_forfeiture_candidate"]:
            status += "/ownership_forfeiture_candidate"
        print(
            "ACF continuation challenge pending: "
            f"task={finding['task_id']} generation={finding['owner_generation']} "
            f"status={status} contenders={finding['contender_count']}. "
            "This ordinary ACF command is only a probe; it does not ACK the challenge or grant ownership. "
            f"Inspect with `acf continuation coordination status {json.dumps(str(root))} "
            f"--task-id {json.dumps(str(finding['task_id']))} --json`.",
            file=sys.stderr,
        )
    if len(findings) > len(shown):
        print(
            f"ACF continuation challenge pending: {len(findings) - len(shown)} additional challenge(s) omitted.",
            file=sys.stderr,
        )


def continuation_coordination_status_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            now = core._iso()
            state, timed_out = refresh_coordination_timeouts(paths, control, now=now)
            lease = core._lease_snapshot(paths, control)
            try:
                coordination = continuation_coordination.summary(
                    state,
                    task_id=str(control["task_id"]),
                    now=now,
                )
            except continuation_coordination.ContinuationCoordinationError as exc:
                raise coordination_error(exc) from exc
            return {
                "status": "coordination_status",
                "task_id": control["task_id"],
                "path": str(paths["coordination"]),
                "state": "valid" if paths["coordination"].exists() else "absent",
                "owner": owner_summary(lease),
                "coordination": coordination,
                "timed_out_challenge_ids": [item["challenge_id"] for item in timed_out],
            }

    return core._guarded(args, "continuation coordination status", operation)


def continuation_coordination_attempt_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            lease = core._lease_snapshot(paths, control)
            if lease["state"] == "invalid":
                raise core.ContinuationError(
                    "cannot register a contender against an invalid lease",
                    code="lease_invalid",
                    exit_code=3,
                )
            observed_owner_generation: int | None = None
            owner_liveness: str | None = None
            if lease["state"] == "active":
                raw_lease = lease.get("lease")
                if not isinstance(raw_lease, Mapping):
                    raise core.ContinuationError("active lease payload is missing", code="lease_invalid")
                observed_owner_generation = core._require_fenced_generation(raw_lease)
                owner_liveness = str(lease.get("liveness") or "legacy_unknown")
            now = core._iso()
            state, _ = refresh_coordination_timeouts(paths, control, now=now)
            try:
                state, attempt = continuation_coordination.register_attempt(
                    state,
                    task_id=str(control["task_id"]),
                    runner_id=str(args.runner_id),
                    objective_summary=str(args.objective_summary),
                    observed_owner_generation=observed_owner_generation,
                    now=now,
                )
                challenge = None
                challenge_created = False
                verified_live_owner = observed_owner_generation is not None and owner_liveness == "fresh"
                if observed_owner_generation is not None and not verified_live_owner:
                    now_dt = core._now()
                    _, deadline_at = challenge_deadline(
                        control,
                        deadline_minutes=args.deadline_minutes,
                        now_dt=now_dt,
                    )
                    state, challenge, challenge_created = continuation_coordination.open_or_join_challenge(
                        state,
                        task_id=str(control["task_id"]),
                        attempt_id=str(attempt["attempt_id"]),
                        owner_generation=observed_owner_generation,
                        deadline_at=deadline_at,
                        now=now,
                    )
                coordination = continuation_coordination.summary(
                    state,
                    task_id=str(control["task_id"]),
                    now=now,
                )
            except continuation_coordination.ContinuationCoordinationError as exc:
                raise coordination_error(exc) from exc
            core._write_json(paths["coordination"], state)
            contender = observed_owner_generation is not None
            verified_live_owner = contender and owner_liveness == "fresh"
            owner_disposition = (
                "verified_live"
                if verified_live_owner
                else "stale_or_unverified"
                if contender
                else "absent"
            )
            return {
                "status": (
                    "live_owner_observed"
                    if verified_live_owner
                    else "contender_registered"
                    if contender
                    else "claim_candidate_registered"
                ),
                "task_id": control["task_id"],
                "attempt": attempt,
                "challenge": challenge,
                "challenge_created": challenge_created,
                "challenge_required": bool(contender and not verified_live_owner),
                "owner_disposition": owner_disposition,
                "duplicate_wake_safe_to_yield": bool(verified_live_owner),
                "owner": owner_summary(lease),
                "coordination": coordination,
                "next_action": (
                    "A fresh authenticated owner was observed. Do not challenge or write protected project files; "
                    "if this is only a duplicate scheduler wake, it may yield without changing task state."
                    if verified_live_owner
                    else "Remain a contender; the challenge does not grant write ownership or prove owner death."
                    if contender
                    else "No active owner was observed; re-run doctor/claim rather than treating this attempt as ownership."
                ),
            }

    return core._guarded(args, "continuation coordination attempt", operation)


def continuation_coordination_challenge_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            lease = core._lease_snapshot(paths, control)
            if lease["state"] != "active":
                raise core.ContinuationError(
                    "an active owner is required to open or join a challenge",
                    code="coordination_owner_absent",
                    exit_code=3,
                    next_actions=["Re-run continuation doctor; if claimable, claim normally instead of challenging."],
                )
            raw_lease = lease.get("lease")
            if not isinstance(raw_lease, Mapping):
                raise core.ContinuationError("active lease payload is missing", code="lease_invalid")
            owner_generation = core._require_fenced_generation(raw_lease)
            now_dt = core._now()
            now = core._iso(now_dt)
            _, deadline_at = challenge_deadline(
                control,
                deadline_minutes=args.deadline_minutes,
                now_dt=now_dt,
            )
            state, _ = refresh_coordination_timeouts(paths, control, now=now)
            try:
                state, challenge, created = continuation_coordination.open_or_join_challenge(
                    state,
                    task_id=str(control["task_id"]),
                    attempt_id=str(args.attempt_id),
                    owner_generation=owner_generation,
                    deadline_at=deadline_at,
                    now=now,
                )
                coordination = continuation_coordination.summary(
                    state,
                    task_id=str(control["task_id"]),
                    now=now,
                )
            except continuation_coordination.ContinuationCoordinationError as exc:
                raise coordination_error(exc) from exc
            core._write_json(paths["coordination"], state)
            return {
                "status": "challenge_opened" if created else "challenge_joined",
                "task_id": control["task_id"],
                "created": created,
                "challenge": challenge,
                "owner": owner_summary(lease),
                "coordination": coordination,
                "next_action": "Remain a contender; this command does not grant write ownership or prove owner death.",
            }

    return core._guarded(args, "continuation coordination challenge", operation)


def register_coordination_parsers(subparsers, add_json_argument) -> None:
    coordination = subparsers.add_parser(
        "coordination",
        help="register compact runner intent and coordinate owner liveness without granting write ownership",
    )
    coordination_subparsers = coordination.add_subparsers(
        dest="continuation_coordination_command",
        required=True,
    )

    status = coordination_subparsers.add_parser(
        "status",
        help="inspect runner attempts, challenges, and the currently observed owner",
    )
    status.add_argument("path", nargs="?", type=Path)
    status.add_argument("--task-id", default=None)
    add_json_argument(status)
    status.set_defaults(func=continuation_coordination_status_command)

    attempt = coordination_subparsers.add_parser(
        "attempt",
        help="register a contender or claim candidate before trying to acquire ownership",
    )
    attempt.add_argument("path", nargs="?", type=Path)
    attempt.add_argument("--task-id", default=None)
    attempt.add_argument("--runner-id", required=True)
    attempt.add_argument("--objective-summary", required=True)
    attempt.add_argument(
        "--deadline-minutes",
        type=int,
        default=None,
        help="challenge response window used only when the observed owner is stale or otherwise unverified; defaults to heartbeat recommendation",
    )
    add_json_argument(attempt)
    attempt.set_defaults(func=continuation_coordination_attempt_command)

    challenge = coordination_subparsers.add_parser(
        "challenge",
        help="open or join the single bounded challenge for the currently observed owner generation",
    )
    challenge.add_argument("path", nargs="?", type=Path)
    challenge.add_argument("--task-id", default=None)
    challenge.add_argument("--attempt-id", required=True)
    challenge.add_argument(
        "--deadline-minutes",
        type=int,
        default=None,
        help="challenge response window; defaults to the configured heartbeat recommendation",
    )
    add_json_argument(challenge)
    challenge.set_defaults(func=continuation_coordination_challenge_command)


__all__ = [
    "challenge_deadline",
    "continuation_coordination_attempt_command",
    "continuation_coordination_challenge_command",
    "continuation_coordination_status_command",
    "emit_pending_challenge_probe",
    "load_coordination_state",
    "pending_challenge_probe",
    "record_authenticated_owner_activity",
    "record_owner_release",
    "refresh_coordination_timeouts",
    "register_coordination_parsers",
]
