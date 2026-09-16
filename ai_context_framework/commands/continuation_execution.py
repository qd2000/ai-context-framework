"""Supervise one long local process while preserving continuation liveness."""

from __future__ import annotations

import argparse
import os
import subprocess
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

from ai_context_framework import continuation_execution, continuation_rounds
from ai_context_framework.commands import continuation_workspace as continuation_workspace_commands
from ai_context_framework.sensitive_data import (
    contains_credential_like_text,
    is_explicit_credential_key,
    redact_credential_like_text,
)


MAX_CAPTURE_BYTES = 64 * 1024
TRUNCATED_OUTPUT_REDACTED = "[truncated child output omitted because sanitization context is incomplete]\n"
OUTPUT_DRAIN_JOIN_SECONDS = 5.0
RETIRED_OWNER_TOKEN_FILE_ENV = "ACF_CONTINUATION_FENCE_TOKEN_FILE"
MIN_POLL_SECONDS = 0.05
MAX_POLL_SECONDS = 1.0
MAX_KEEPALIVE_SECONDS = 300.0


class _BoundedOutputCapture:
    """Bounded in-memory child output capture with fail-closed overflow."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._truncated = False

    def feed(self, raw: bytes) -> None:
        if not raw:
            return
        with self._lock:
            if self._truncated:
                return
            if len(self._buffer) + len(raw) > MAX_CAPTURE_BYTES:
                # Once context is incomplete, keeping an arbitrary suffix can
                # expose a credential whose identifying key/header was in the
                # discarded prefix.  Drop the whole diagnostic body instead.
                self._buffer.clear()
                self._truncated = True
                return
            self._buffer.extend(raw)

    def mark_incomplete(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._truncated = True

    @property
    def truncated(self) -> bool:
        with self._lock:
            return self._truncated

    def render_public(self) -> str:
        with self._lock:
            if self._truncated:
                return TRUNCATED_OUTPUT_REDACTED
            raw = bytes(self._buffer)
        text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        return redact_credential_like_text(text)[0]


def _drain_pipe(stream: Any, capture: _BoundedOutputCapture) -> None:
    try:
        while True:
            raw = stream.read(8192)
            if not raw:
                break
            capture.feed(raw)
    except (OSError, ValueError):
        capture.mark_incomplete()
    finally:
        try:
            stream.close()
        except (OSError, ValueError):
            pass


def _start_output_capture(stream: Any) -> tuple[_BoundedOutputCapture, threading.Thread]:
    capture = _BoundedOutputCapture()
    thread = threading.Thread(target=_drain_pipe, args=(stream, capture), daemon=True)
    thread.start()
    return capture, thread


def _finish_output_capture(
    capture: _BoundedOutputCapture,
    thread: threading.Thread,
) -> tuple[str, bool]:
    thread.join(timeout=OUTPUT_DRAIN_JOIN_SECONDS)
    if thread.is_alive():
        capture.mark_incomplete()
    return capture.render_public(), capture.truncated


def split_cli_child_argv(argv: list[str]) -> tuple[list[str], list[str] | None]:
    """Detach the literal ``--`` child tail before argparse interprets child flags.

    ``argparse`` otherwise treats child options such as ``python -c`` as ACF
    options on some Python/platform combinations.  Keeping the delimiter split
    outside the parser preserves the existing ``run PATH --options -- CHILD``
    ordering while still passing the child argv byte-for-byte as strings.
    """
    if len(argv) < 3 or argv[:3] != ["continuation", "execution", "run"]:
        return argv, None
    try:
        delimiter = argv.index("--", 3)
    except ValueError:
        return argv, None
    return argv[:delimiter], argv[delimiter + 1 :]


def _continuation():
    # Lazy import avoids a cycle because the core continuation module exposes
    # this adapter back to the runtime parser.
    from ai_context_framework.commands import continuation

    return continuation


def _command_argv(args: argparse.Namespace) -> list[str]:
    core = _continuation()
    values = [str(value) for value in list(args.child_argv or [])]
    if values and values[0] == "--":
        values = values[1:]
    if not values:
        raise core.ContinuationError(
            "physical execution requires a command after `--`",
            code="physical_execution_command_missing",
            next_actions=[
                "Pass the exact local command after `--`; shell interpolation is intentionally not implicit."
            ],
        )
    for value in values:
        option: str | None = None
        if value.startswith("--") and len(value) > 2:
            option = value[2:].split("=", 1)[0]
        elif value.startswith("-") and len(value) > 1:
            option = value[1:].split("=", 1)[0]
        elif os.name == "nt" and value.startswith("/") and len(value) > 1:
            # Windows tools commonly use /NAME.  On POSIX, /password can be a
            # legitimate absolute path and must not be reclassified by name.
            option = value[1:].split("=", 1)[0].split(":", 1)[0]
        if (option and is_explicit_credential_key(option)) or contains_credential_like_text(value):
            raise core.ContinuationError(
                "physical execution refuses credential-bearing child argv",
                code="physical_execution_sensitive_argv_refused",
                exit_code=3,
                next_actions=[
                    "Pass only non-secret command arguments. Use a child-local credential file, OS credential mechanism, or another transport that keeps reusable credentials out of the ACF command boundary."
                ],
            )
    return values


def _command_summary(argv: list[str]) -> dict[str, object]:
    executable = Path(argv[0]).name or argv[0]
    return {
        "executable": executable,
        "argument_count": max(0, len(argv) - 1),
        "argv_persisted": False,
    }


def _child_environment() -> dict[str, str]:
    """Inherit ordinary process environment without parent owner credentials.

    Owner capability paths are CLI-only.  Ordinary non-credential environment
    metadata is inherited for compatibility, while explicit credential keys or
    credential-shaped values are not delegated to the supervised child.
    The supervisor keeps its own environment unchanged.
    """

    child_env = os.environ.copy()
    child_env.pop(RETIRED_OWNER_TOKEN_FILE_ENV, None)
    child_env.pop("ACF_CONTINUATION_OWNER_FILE", None)
    for key, value in list(child_env.items()):
        if is_explicit_credential_key(key) or contains_credential_like_text(value):
            child_env.pop(key, None)
    return child_env


def _keepalive_seconds(control: Mapping[str, Any]) -> float:
    heartbeat_seconds = max(1.0, float(control["heartbeat_interval_minutes"]) * 60.0)
    stale_seconds = max(2.0, float(control["stale_after_minutes"]) * 60.0)
    return max(1.0, min(MAX_KEEPALIVE_SECONDS, heartbeat_seconds / 2.0, stale_seconds / 3.0))


def _poll_seconds(control: Mapping[str, Any]) -> float:
    return max(MIN_POLL_SECONDS, min(MAX_POLL_SECONDS, _keepalive_seconds(control) / 20.0))


def _terminal_next_actions(*, return_code: int, pause_pending: bool) -> list[str]:
    actions: list[str] = []
    if return_code != 0:
        actions.append(
            "Treat the child command failure as terminal evidence for this deterministic execution key; do not replay it unchanged without new evidence, input, environment, or strategy."
        )
    if pause_pending:
        actions.append(
            "The pause request arrived while this physical execution was active. Release the current round now that the supervised command is terminal; release will transition continuation state to paused."
        )
    return actions


def _load_owner(
    root: Path,
    paths: Mapping[str, Path],
    args: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any]]:
    core = _continuation()
    control = core._load_control(paths, root)
    snapshot = core._lease_snapshot(paths, control)
    lease, _owner_context = continuation_workspace_commands.assert_owner_context(
        args,
        paths,
        root=root,
        control=control,
        snapshot=snapshot,
    )
    core._require_fenced_generation(lease)
    git = core._git_identity(root)
    if git["branch"] != control["expected_branch"] or git["detached"]:
        raise core.ContinuationError(
            "Git identity changed during physical execution",
            code="workspace_mismatch",
            exit_code=3,
        )
    return control, lease


def _update_effect(
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
    *,
    generation: int,
    key: str,
    status: str,
    external_id: str | None = None,
    milestone: str,
    evidence_ref: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    core = _continuation()
    journal = core._load_effect_journal(paths, control, require_existing=True)
    try:
        journal, effect, summary = core.continuation_effect_archive.update_across_history(
            paths["effects"],
            journal,
            task_id=str(control["task_id"]),
            generation=generation,
            logical_key=key,
            status=status,
            external_id=external_id,
            milestone=milestone,
            evidence_refs=[evidence_ref],
            now=core._iso(),
        )
    except continuation_rounds.ContinuationRoundError as exc:
        raise core._round_error(exc) from exc
    return effect, summary


def _record_keepalive(
    root: Path,
    paths: Mapping[str, Path],
    args: argparse.Namespace,
    *,
    renew_if_due: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    core = _continuation()
    control, lease = _load_owner(root, paths, args)
    # A pause request prevents starting new work, but it must not turn a live
    # deterministic child into an orphan or force-kill it.  Keep the current
    # owner alive until the already-started child is terminal; the caller can
    # then release, and the normal release path will transition state to
    # ``paused`` because the durable pause marker is still present.
    now = core._now()
    directive_context = core.continuation_directive_commands.directive_context(paths, control)
    directive_signal = core.continuation_directive_commands.observe_directive_context(
        lease,
        directive_context,
    )
    last_renew = core._parse_iso(lease.get("last_renew_at"), field="last_renew_at")
    renew_seconds = max(60.0, float(control["renew_interval_minutes"]) * 60.0)
    should_renew = renew_if_due and (now - last_renew).total_seconds() >= renew_seconds
    lease["last_heartbeat_at"] = core._iso(now)
    if should_renew:
        ttl = int(control["lease_ttl_minutes"])
        lease["last_renew_at"] = core._iso(now)
        lease["expires_at"] = core._iso(now + timedelta(minutes=ttl))
    core._write_json(paths["lease"], lease)
    return lease, directive_signal


def continuation_execution_run_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        argv = _command_argv(args)
        execution_key = core._validate_public_input_text(args.key, field="execution_key")
        with core._state_lock(paths["lock"]):
            control, lease = _load_owner(root, paths, args)
            if paths["pause"].exists():
                raise core.ContinuationError(
                    "pause was requested; do not start a new physical execution",
                    code="continuation_paused",
                    exit_code=3,
                )
            generation = core._require_fenced_generation(lease)
            journal = core._load_effect_journal(paths, control)
            try:
                journal, effect, created, summary, rollover = (
                    core.continuation_effect_archive.prepare_with_rollover(
                        paths["effects"],
                        journal,
                        task_id=str(control["task_id"]),
                        generation=generation,
                        logical_key=execution_key,
                        kind=continuation_execution.PHYSICAL_EXECUTION_EFFECT_KIND,
                        external_id=None,
                        milestone="spawn_pending",
                        evidence_refs=[f"physical-execution:{execution_key}:prepared"],
                        now=core._iso(),
                    )
                )
            except continuation_rounds.ContinuationRoundError as exc:
                raise core._round_error(exc) from exc
            if not created:
                raise core.ContinuationError(
                    "physical execution key already exists; deterministic identity cannot be replayed",
                    code="physical_execution_identity_exists",
                    exit_code=3,
                    details={"effect": effect, "summary": summary},
                    next_actions=[
                        "Inspect the existing effect. Reconcile an uncertain prior execution instead of spawning a replacement, or use a new key only for a genuinely new logical execution."
                    ],
                )

        process: subprocess.Popen[bytes] | None = None
        stdout_capture: _BoundedOutputCapture | None = None
        stderr_capture: _BoundedOutputCapture | None = None
        stdout_thread: threading.Thread | None = None
        stderr_thread: threading.Thread | None = None
        process_identity: str | None = None
        directive_signal: dict[str, Any] | None = None

        def public_child_output() -> tuple[str, str, bool, bool]:
            if (
                stdout_capture is None
                or stderr_capture is None
                or stdout_thread is None
                or stderr_thread is None
            ):
                return "", "", False, False
            child_stdout, stdout_truncated = _finish_output_capture(stdout_capture, stdout_thread)
            child_stderr, stderr_truncated = _finish_output_capture(stderr_capture, stderr_thread)
            return child_stdout, child_stderr, stdout_truncated, stderr_truncated

        try:
            try:
                popen_kwargs: dict[str, Any] = {}
                if os.name == "nt":
                    popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                else:
                    popen_kwargs["start_new_session"] = True
                process = subprocess.Popen(
                    argv,
                    cwd=root,
                    env=_child_environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    **popen_kwargs,
                )
                assert process.stdout is not None and process.stderr is not None
                stdout_capture, stdout_thread = _start_output_capture(process.stdout)
                stderr_capture, stderr_thread = _start_output_capture(process.stderr)
            except OSError as exc:
                with core._state_lock(paths["lock"]):
                    control, lease = _load_owner(root, paths, args)
                    generation = core._require_fenced_generation(lease)
                    effect, summary = _update_effect(
                        paths,
                        control,
                        generation=generation,
                        key=execution_key,
                        status="failed",
                        milestone="spawn_failed",
                        evidence_ref=f"physical-execution:{execution_key}:spawn-failed",
                    )
                raise core.ContinuationError(
                    f"physical execution spawn failed: {exc}",
                    code="physical_execution_spawn_failed",
                    details={"effect": effect, "summary": summary},
                ) from exc

            try:
                process_identity = continuation_execution.capture_process_identity(process.pid)
            except continuation_execution.ProcessIdentityError as exc:
                return_code = process.poll()
                if return_code is None:
                    # Identity capture can race a very short child on slower or
                    # heavily loaded runners.  Give only that already-spawned
                    # child a small bounded terminal observation window before
                    # classifying the effect as unverifiable/unknown.
                    try:
                        return_code = process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        return_code = None
                if return_code is not None:
                    # A very short local command can finish before its start
                    # marker is captured. The parent directly observed that
                    # terminal result, so this deterministic execution is not
                    # an uncertain external effect.
                    with core._state_lock(paths["lock"]):
                        control, lease = _load_owner(root, paths, args)
                        generation = core._require_fenced_generation(lease)
                        lease, directive_signal = _record_keepalive(
                            root,
                            paths,
                            args,
                            renew_if_due=True,
                        )
                        terminal_status = "completed" if return_code == 0 else "failed"
                        effect, summary = _update_effect(
                            paths,
                            control,
                            generation=generation,
                            key=execution_key,
                            status=terminal_status,
                            milestone=f"process_exit_{return_code}",
                            evidence_ref=f"physical-execution:{execution_key}:exit:{return_code}",
                        )
                        pause_pending = paths["pause"].exists()
                    child_stdout, child_stderr, stdout_truncated, stderr_truncated = public_child_output()
                    return {
                        "ok": return_code == 0,
                        "error_code": None if return_code == 0 else "physical_execution_child_failed",
                        "status": (
                            "physical_execution_completed"
                            if return_code == 0
                            else "physical_execution_failed"
                        ),
                        "task_id": control["task_id"],
                        "generation": generation,
                        "key": execution_key,
                        "command": _command_summary(argv),
                        "returncode": return_code,
                        "process_identity": None,
                        "effect": effect,
                        "summary": summary,
                        "rollover": rollover,
                        "directive_signal": directive_signal,
                        "pause_pending": pause_pending,
                        "child_stdout": child_stdout,
                        "child_stderr": child_stderr,
                        "output_truncated": {
                            "stdout": stdout_truncated,
                            "stderr": stderr_truncated,
                        },
                        "next_actions": _terminal_next_actions(
                            return_code=return_code,
                            pause_pending=pause_pending,
                        ),
                    }
                if return_code is None:
                    continuation_execution.terminate_process_tree(process)
                    with core._state_lock(paths["lock"]):
                        control, lease = _load_owner(root, paths, args)
                        generation = core._require_fenced_generation(lease)
                        effect, summary = _update_effect(
                            paths,
                            control,
                            generation=generation,
                            key=execution_key,
                            status="unknown",
                            milestone="identity_unverifiable",
                            evidence_ref=f"physical-execution:{execution_key}:identity-unverifiable",
                        )
                    raise core.ContinuationError(
                        f"physical execution identity is unverifiable: {exc}",
                        code="physical_execution_identity_unverifiable",
                        exit_code=3,
                        details={"effect": effect, "summary": summary},
                        next_actions=[
                            "Do not replay the command. Reconcile the unknown physical effect with authoritative terminal evidence first."
                        ],
                    ) from exc

            with core._state_lock(paths["lock"]):
                control, lease = _load_owner(root, paths, args)
                generation = core._require_fenced_generation(lease)
                effect, summary = _update_effect(
                    paths,
                    control,
                    generation=generation,
                    key=execution_key,
                    status="active",
                    external_id=process_identity,
                    milestone="process_running",
                    evidence_ref=f"physical-execution:{execution_key}:process-started",
                )
                # Refresh owner liveness as soon as the supervised process has
                # a durable identity.  Without this initial keepalive, a busy
                # runner can spend most of a short child's lifetime capturing
                # process identity and reach terminal handling before the first
                # periodic keepalive is due.
                lease, directive_signal = _record_keepalive(
                    root,
                    paths,
                    args,
                    renew_if_due=True,
                )
                keepalive_seconds = _keepalive_seconds(control)
                poll_seconds = _poll_seconds(control)
            next_keepalive = time.monotonic() + keepalive_seconds

            while True:
                return_code = process.poll()
                if return_code is not None:
                    break
                now_monotonic = time.monotonic()
                if now_monotonic >= next_keepalive:
                    with core._state_lock(paths["lock"]):
                        lease, directive_signal = _record_keepalive(
                            root,
                            paths,
                            args,
                            renew_if_due=True,
                        )
                        control = core._load_control(paths, root)
                        keepalive_seconds = _keepalive_seconds(control)
                    next_keepalive = time.monotonic() + keepalive_seconds
                time.sleep(poll_seconds)

            with core._state_lock(paths["lock"]):
                control, lease = _load_owner(root, paths, args)
                generation = core._require_fenced_generation(lease)
                lease, directive_signal = _record_keepalive(
                    root,
                    paths,
                    args,
                    renew_if_due=True,
                )
                terminal_status = "completed" if return_code == 0 else "failed"
                effect, summary = _update_effect(
                    paths,
                    control,
                    generation=generation,
                    key=execution_key,
                    status=terminal_status,
                    milestone=f"process_exit_{return_code}",
                    evidence_ref=f"physical-execution:{execution_key}:exit:{return_code}",
                )
                pause_pending = paths["pause"].exists()
            child_stdout, child_stderr, stdout_truncated, stderr_truncated = public_child_output()
            return {
                "ok": return_code == 0,
                "error_code": None if return_code == 0 else "physical_execution_child_failed",
                "status": "physical_execution_completed" if return_code == 0 else "physical_execution_failed",
                "task_id": control["task_id"],
                "generation": generation,
                "key": execution_key,
                "command": _command_summary(argv),
                "returncode": return_code,
                "process_identity": process_identity,
                "effect": effect,
                "summary": summary,
                "rollover": rollover,
                "directive_signal": directive_signal,
                "pause_pending": pause_pending,
                "child_stdout": child_stdout,
                "child_stderr": child_stderr,
                "output_truncated": {
                    "stdout": stdout_truncated,
                    "stderr": stderr_truncated,
                },
                "next_actions": _terminal_next_actions(
                    return_code=return_code,
                    pause_pending=pause_pending,
                ),
            }
        finally:
            if process is not None and process.poll() is None:
                # A controller exception must not silently orphan the process.
                continuation_execution.terminate_process_tree(process)
            if stdout_capture is not None and stdout_thread is not None:
                _finish_output_capture(stdout_capture, stdout_thread)
            if stderr_capture is not None and stderr_thread is not None:
                _finish_output_capture(stderr_capture, stderr_thread)

    return core._guarded(args, "continuation execution run", operation)


def register_execution_parser(subparsers, add_json_argument) -> None:
    execution = subparsers.add_parser(
        "execution",
        help="supervise one deterministic local process while maintaining owner liveness",
    )
    execution_subparsers = execution.add_subparsers(
        dest="continuation_execution_command",
        required=True,
    )
    run = execution_subparsers.add_parser(
        "run",
        help="run one local process under a durable physical-execution identity and automatic heartbeat/renew",
    )
    run.add_argument("path", nargs="?", type=Path)
    run.add_argument("--task-id", default=None)
    run.add_argument("--owner-file", default=None)
    run.add_argument(
        "--key",
        required=True,
        help="deterministic logical execution key; an existing key is never replayed",
    )
    add_json_argument(run)
    run.add_argument(
        "child_argv",
        nargs="*",
        help="exact command argv after `--`; no implicit shell is used",
    )
    run.set_defaults(func=continuation_execution_run_command)


__all__ = [
    "continuation_execution_run_command",
    "register_execution_parser",
    "split_cli_child_argv",
]
