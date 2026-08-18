"""CLI adapter for bounded continuation attempt/challenge coordination.

The durable state model is intentionally separate from ownership transfer.
This adapter can register contenders and open/join one challenge for the
currently observed owner generation, but it never grants write ownership or
declares an owner dead.
"""

from __future__ import annotations

import argparse
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
    state, timed_out = refresh_coordination_timeouts(paths, control, now=now)
    try:
        state, acknowledged = continuation_coordination.acknowledge_owner_activity(
            state,
            task_id=str(control["task_id"]),
            owner_generation=core._require_fenced_generation(lease),
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
    state, timed_out = refresh_coordination_timeouts(paths, control, now=now)
    try:
        state, resolved = continuation_coordination.resolve_owner_release(
            state,
            task_id=str(control["task_id"]),
            owner_generation=core._require_fenced_generation(lease),
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
            if lease["state"] == "active":
                raw_lease = lease.get("lease")
                if not isinstance(raw_lease, Mapping):
                    raise core.ContinuationError("active lease payload is missing", code="lease_invalid")
                observed_owner_generation = core._require_fenced_generation(raw_lease)
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
                if observed_owner_generation is not None:
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
            return {
                "status": "contender_registered" if contender else "claim_candidate_registered",
                "task_id": control["task_id"],
                "attempt": attempt,
                "challenge": challenge,
                "challenge_created": challenge_created,
                "owner": owner_summary(lease),
                "coordination": coordination,
                "next_action": (
                    "Remain a contender; the challenge does not grant write ownership or prove owner death."
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
        help="register bounded contender attempts and challenges without granting write ownership",
    )
    coordination_subparsers = coordination.add_subparsers(
        dest="continuation_coordination_command",
        required=True,
    )

    status = coordination_subparsers.add_parser(
        "status",
        help="inspect bounded attempt/challenge state and the currently observed owner",
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
        help="automatic challenge response window when an owner is active; defaults to heartbeat recommendation",
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
    "load_coordination_state",
    "record_authenticated_owner_activity",
    "record_owner_release",
    "refresh_coordination_timeouts",
    "register_coordination_parsers",
]
