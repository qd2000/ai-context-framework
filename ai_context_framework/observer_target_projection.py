"""Fresh target-scoped Observer fact projection for presentation workflows.

Target-local semantic/presentation commands must validate against current
project authority without rebuilding the full Project Observer snapshot.  A
full snapshot intentionally samples every in-scope Git worktree multiple
times for project-wide consistency; that cost is unnecessary when a caller
needs only the facts that can invalidate one explicitly registered target.
"""

from __future__ import annotations

import _thread
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Iterable, Mapping

from ai_context_framework.git_support import GitCommandError, list_worktrees, path_key
from ai_context_framework.observer import (
    OBSERVER_WORKTREE_SCHEMA,
    ObserverProject,
    _safe_registry_rows,
    _worktree_payload,
    capture_project_continuations,
    capture_project_workstreams,
    enrich_workstream_machine_states,
    resolve_observer_project,
)
from ai_context_framework.observer_storage import sanitize_observer_payload
from ai_context_framework.observer_targets import build_target_views, read_target_registry


OBSERVER_TARGET_READ_TIMEOUT_SECONDS = 30.0
OBSERVER_TARGET_READ_WORKER_SCHEMA = "acf.observer.target-read-worker.v1"


class ObserverTargetReadError(RuntimeError):
    """Fail-visible bounded target/project read failure."""

    def __init__(self, error_code: str, message: str, *, stderr: str | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.stderr = stderr


def hard_failstop_target_read_timeout_if_needed(
    exc: ObserverTargetReadError,
    exit_code: int,
) -> None:
    """Force a real Windows CLI process terminal after a target-read timeout.

    A Windows ``CreateProcess`` stall can outlive the Python helper thread that
    enforces the logical deadline.  In real ``acf`` console-script execution,
    returning the structured timeout payload and then entering normal Python
    interpreter shutdown has been observed to leave the outer CLI process
    non-terminal.  Once the command adapter has emitted the fail-visible payload
    *outside any Observer lock*, flush OS-backed streams and fail-stop the CLI
    process so DevSpace/schedulers cannot inherit an unknown session.

    Programmatic/test ``acf.main(...)`` calls are deliberately excluded: their
    ``sys.argv[0]`` is not the ACF console entrypoint (and unit-test StringIO
    streams have no usable file descriptor), so library callers still receive a
    normal exception/result instead of process termination.
    """

    if os.name != "nt" or exc.error_code != "observer_target_read_timeout":
        return
    entrypoint = Path(str(sys.argv[0] or "")).name.lower()
    if entrypoint not in {"acf.exe", "acf.py", "acf"}:
        return
    try:
        sys.stdout.fileno()
        sys.stderr.fileno()
    except (AttributeError, OSError, ValueError):
        return
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(int(exit_code))


def _target_read_worker_command() -> list[str]:
    """Return a worker command whose Windows top PID is killable immediately.

    The expensive/sometimes policy-inspected executable here is Python.  A
    direct ``Popen(sys.executable, ...)`` can block inside Windows process
    creation before ``Popen`` returns, which means the parent has no PID to
    terminate at the deadline.  On Windows, launch a system ``cmd.exe`` first
    and let that process create the Python worker.  Once ``cmd.exe`` exists the
    parent owns an exact top PID; if Python bootstrap stalls, ``taskkill /T`` on
    that PID terminates the whole scoped worker tree.  POSIX keeps the direct
    Python process-group launch.
    """

    worker = [sys.executable, "-m", "ai_context_framework.observer_target_projection", "--worker"]
    if os.name != "nt":
        return worker
    comspec = os.environ.get("COMSPEC")
    if not comspec:
        system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
        comspec = str(Path(system_root) / "System32" / "cmd.exe") if system_root else "cmd.exe"
    return [comspec, "/d", "/s", "/c", subprocess.list2cmdline(worker)]


def _project_from_payload(payload: Mapping[str, object]) -> ObserverProject:
    required = ("project_id", "canonical_root", "invocation_root", "context_root", "observer_dir")
    missing = [key for key in required if not isinstance(payload.get(key), str) or not payload.get(key)]
    if missing:
        raise ObserverTargetReadError(
            "observer_target_read_invalid",
            f"Observer target-read worker returned an invalid project payload; missing={','.join(missing)}",
        )
    git_managed = payload.get("git_managed")
    if not isinstance(git_managed, bool):
        raise ObserverTargetReadError(
            "observer_target_read_invalid",
            "Observer target-read worker returned an invalid project payload; git_managed must be boolean",
        )
    return ObserverProject(
        project_id=str(payload["project_id"]),
        canonical_root=Path(str(payload["canonical_root"])),
        invocation_root=Path(str(payload["invocation_root"])),
        context_root=Path(str(payload["context_root"])),
        observer_dir=Path(str(payload["observer_dir"])),
        git_managed=git_managed,
    )


def _terminate_worker_tree(process: subprocess.Popen[str]) -> None:
    """Terminate only the timed-out Observer worker and its descendants."""

    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


def _spawn_target_read_worker(
    command: list[str],
    popen_kwargs: Mapping[str, object],
    *,
    deadline: float,
    timeout_seconds: float,
) -> subprocess.Popen[str]:
    """Start the read worker without letting ``CreateProcess`` defeat the deadline.

    ``subprocess`` timeouts begin only after ``Popen`` returns.  On Windows a
    process creation call can itself block (for example while endpoint policy
    inspects an executable), which would otherwise leave the outer Observer CLI
    non-terminal before a worker PID even exists.  Launch in a low-level helper
    thread so the caller can still fail visible at the overall deadline.  Do not
    use ``threading.Thread.start`` here: that high-level API waits for child
    bootstrap before returning, which would put its own startup handshake outside
    the explicit ``ready.wait`` deadline.  If a delayed launch eventually returns
    after cancellation, that exact worker tree is immediately terminated instead
    of being allowed to become an orphan.
    """

    ready = threading.Event()
    cancelled = threading.Event()
    state: dict[str, object] = {}

    def launch() -> None:
        try:
            process = subprocess.Popen(command, **dict(popen_kwargs))
            state["process"] = process
            if cancelled.is_set():
                _terminate_worker_tree(process)
                try:
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        except Exception as exc:  # marshalled back to the caller thread below
            state["error"] = exc
        finally:
            ready.set()

    try:
        _thread.start_new_thread(launch, ())
    except Exception as exc:
        raise ObserverTargetReadError(
            "observer_target_read_spawn_failed",
            f"Observer target-read helper thread could not start: {exc}",
        ) from exc
    remaining = max(0.0, deadline - time.monotonic())
    if not ready.wait(remaining):
        cancelled.set()
        process = state.get("process")
        if process is not None:
            _terminate_worker_tree(process)  # close the timeout race after Popen returns
        raise ObserverTargetReadError(
            "observer_target_read_timeout",
            f"Observer target-read worker launch exceeded the {float(timeout_seconds):g}s bounded deadline.",
        )
    error = state.get("error")
    if error is not None:
        if isinstance(error, OSError):
            raise ObserverTargetReadError(
                "observer_target_read_spawn_failed",
                f"Observer target-read worker could not start: {error}",
            ) from error
        raise ObserverTargetReadError(
            "observer_target_read_spawn_failed",
            f"Observer target-read worker could not start: {error}",
        ) from error
    process = state.get("process")
    if process is None:
        raise ObserverTargetReadError(
            "observer_target_read_spawn_failed",
            "Observer target-read worker launch ended without a process handle.",
        )
    return process


def _run_target_read_worker(
    request: Mapping[str, object],
    *,
    timeout_seconds: float = OBSERVER_TARGET_READ_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Run one Observer-only read in a bounded child process.

    The worker boundary intentionally contains existing Path.resolve/Git discovery
    semantics instead of changing shared ``git_support.run_git`` behavior for
    continuation/worktree/release control planes.  On Windows a timed-out worker
    is terminated by exact PID with descendants so a stuck Git child cannot be
    orphaned.
    """

    command = _target_read_worker_command()
    popen_kwargs: dict[str, object] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "shell": False,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    bounded_timeout = max(0.01, float(timeout_seconds))
    deadline = time.monotonic() + bounded_timeout
    process = _spawn_target_read_worker(
        command,
        popen_kwargs,
        deadline=deadline,
        timeout_seconds=bounded_timeout,
    )
    request_text = json.dumps(dict(request), ensure_ascii=False)
    try:
        remaining = max(0.01, deadline - time.monotonic())
        stdout, stderr = process.communicate(request_text, timeout=remaining)
    except subprocess.TimeoutExpired as exc:
        _terminate_worker_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        raise ObserverTargetReadError(
            "observer_target_read_timeout",
            f"Observer target/project read exceeded the {bounded_timeout:g}s bounded deadline and was terminated.",
            stderr=stderr or None,
        ) from exc
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ObserverTargetReadError(
            "observer_target_read_invalid",
            "Observer target-read worker returned invalid JSON on stdout.",
            stderr=stderr or None,
        ) from exc
    if not isinstance(payload, dict):
        raise ObserverTargetReadError(
            "observer_target_read_invalid",
            "Observer target-read worker returned a non-object JSON payload.",
            stderr=stderr or None,
        )
    if process.returncode != 0 or payload.get("ok") is not True:
        message = payload.get("message") if isinstance(payload.get("message"), str) else None
        raise ObserverTargetReadError(
            "observer_target_read_failed",
            message or f"Observer target-read worker exited with code {process.returncode}.",
            stderr=stderr or None,
        )
    return payload


def resolve_observer_project_bounded(
    path: Path | str | None = None,
    *,
    timeout_seconds: float = OBSERVER_TARGET_READ_TIMEOUT_SECONDS,
) -> ObserverProject:
    """Resolve Observer project identity with a bounded fail-visible deadline."""

    payload = _run_target_read_worker(
        {
            "operation": "resolve_project",
            "path": str(path) if path is not None else None,
        },
        timeout_seconds=timeout_seconds,
    )
    project_payload = payload.get("project")
    if not isinstance(project_payload, dict):
        raise ObserverTargetReadError(
            "observer_target_read_invalid",
            "Observer target-read worker omitted the resolved project payload.",
        )
    return _project_from_payload(project_payload)


def build_observer_target_views_bounded(
    project: ObserverProject,
    *,
    target_ids: Iterable[str] | None = None,
    timeout_seconds: float = OBSERVER_TARGET_READ_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Build fresh target views inside the same Observer-only bounded boundary."""

    requested = [str(value) for value in target_ids] if target_ids is not None else None
    payload = _run_target_read_worker(
        {
            "operation": "target_views",
            "project": project.to_payload(),
            "target_ids": requested,
        },
        timeout_seconds=timeout_seconds,
    )
    target_views = payload.get("target_views")
    if not isinstance(target_views, dict):
        raise ObserverTargetReadError(
            "observer_target_read_invalid",
            "Observer target-read worker omitted the target projection payload.",
        )
    return target_views


def _target_scope_worktree_rows(
    project: ObserverProject,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Return cheap path-only Observer-scope rows plus Git records by path."""

    if not project.git_managed:
        return ([{"path": str(project.invocation_root), "observer_scope": True}], {})
    records = list_worktrees(project.canonical_root)
    registry_rows = _safe_registry_rows(project)
    registry_by_path = {
        path_key(str(row["path"])): row
        for row in registry_rows
        if isinstance(row.get("path"), str)
    }
    registry_managed_domain = bool(registry_rows)
    primary_key = path_key(project.canonical_root)
    by_path: dict[str, object] = {}
    rows: list[dict[str, object]] = []
    for record in records:
        if record.bare or not record.path.is_dir():
            continue
        record_key = path_key(record.path)
        by_path[record_key] = record
        registered = record_key in registry_by_path
        primary = record_key == primary_key
        if not (primary or registered or not registry_managed_domain):
            continue
        rows.append(
            {
                "path": str(record.path),
                "head": record.head,
                "branch": record.branch_short,
                "primary": primary,
                "registered": registered,
                "registry": registry_by_path.get(record_key),
                "observer_scope": True,
            }
        )
    return rows, by_path


def build_observer_target_views(
    project: ObserverProject,
    *,
    target_ids: Iterable[str] | None = None,
) -> dict[str, object]:
    """Build fresh facts only for explicitly registered Observer targets.

    The projection first reads cheap target/continuation topology, derives the
    Workstreams actually relevant to the requested targets, then captures full
    Git facts only for the primary/bound worktrees needed to preserve existing
    Workstream source-authority and source-divergence semantics.
    """

    wanted = {str(value) for value in target_ids} if target_ids is not None else None
    registry = read_target_registry(project)
    selected_targets = [
        row
        for row in registry.get("targets") or []
        if isinstance(row, dict)
        and (wanted is None or str(row.get("target_id") or "") in wanted)
    ]
    scope_rows, records_by_path = _target_scope_worktree_rows(project)
    continuations = capture_project_continuations(project, scope_rows)

    workstream_ids: set[str] = {
        str(row.get("workstream_id"))
        for row in selected_targets
        if row.get("mode") == "fixed_workstream"
        and isinstance(row.get("workstream_id"), str)
        and row.get("workstream_id")
    }
    selected_task_ids = {
        str(row.get("continuation_task_id"))
        for row in selected_targets
        if isinstance(row.get("continuation_task_id"), str) and row.get("continuation_task_id")
    }
    for row in continuations if selected_task_ids else []:
        if not isinstance(row, dict) or row.get("task_id") not in selected_task_ids:
            continue
        workstream_id = row.get("workstream_id")
        if isinstance(workstream_id, str) and workstream_id:
            workstream_ids.add(workstream_id)

    relevant_rows: list[dict[str, object]] = []
    if project.git_managed:
        registry_rows = _safe_registry_rows(project)
        relevant_keys = {path_key(project.canonical_root)}
        for row in registry_rows:
            if not isinstance(row.get("path"), str):
                continue
            if row.get("workstream") in workstream_ids or row.get("key") in workstream_ids:
                relevant_keys.add(path_key(str(row["path"])))
        registry_by_path = {
            path_key(str(row["path"])): row
            for row in registry_rows
            if isinstance(row.get("path"), str)
        }
        for key in sorted(relevant_keys):
            record = records_by_path.get(key)
            if record is None:
                continue
            try:
                payload = _worktree_payload(
                    record.path,
                    listed_head=record.head,
                    listed_branch=record.branch_short,
                )
            except (GitCommandError, SystemExit, OSError) as exc:
                payload = {
                    "schema_version": OBSERVER_WORKTREE_SCHEMA,
                    "path": str(record.path),
                    "branch": record.branch_short,
                    "head": record.head,
                    "clean": None,
                    "read_error": str(exc),
                    "git_fingerprint": None,
                }
            payload["primary"] = key == path_key(project.canonical_root)
            payload["registered"] = key in registry_by_path
            payload["registry"] = registry_by_path.get(key)
            payload["observer_scope"] = True
            relevant_rows.append(payload)
    else:
        relevant_rows = scope_rows

    workstreams = capture_project_workstreams(
        project,
        relevant_rows,
        workstream_ids=workstream_ids,
    )
    workstreams = enrich_workstream_machine_states(workstreams, continuations)
    target_views = build_target_views(
        project,
        {"workstreams": workstreams, "continuations": continuations},
        target_ids=wanted,
    )
    sanitized = sanitize_observer_payload(target_views)
    if not isinstance(sanitized, dict):
        raise TypeError("Observer target projection sanitization must preserve object shape")
    return sanitized


def _worker_dispatch(request: Mapping[str, object]) -> dict[str, object]:
    operation = request.get("operation")
    if operation == "resolve_project":
        raw_path = request.get("path")
        if raw_path is not None and not isinstance(raw_path, str):
            raise ValueError("resolve_project path must be a string or null")
        project = resolve_observer_project(Path(raw_path) if raw_path else None)
        return {"project": project.to_payload()}
    if operation == "target_views":
        raw_project = request.get("project")
        if not isinstance(raw_project, dict):
            raise ValueError("target_views requires a project object")
        project = _project_from_payload(raw_project)
        raw_target_ids = request.get("target_ids")
        if raw_target_ids is not None and not (
            isinstance(raw_target_ids, list) and all(isinstance(value, str) for value in raw_target_ids)
        ):
            raise ValueError("target_views target_ids must be a string list or null")
        return {
            "target_views": build_observer_target_views(
                project,
                target_ids=raw_target_ids,
            )
        }
    raise ValueError(f"unsupported Observer target-read worker operation: {operation!r}")


def _worker_main() -> int:
    try:
        request = json.loads(sys.stdin.read())
        if not isinstance(request, dict):
            raise ValueError("Observer target-read worker request must be a JSON object")
        payload = {
            "schema_version": OBSERVER_TARGET_READ_WORKER_SCHEMA,
            "ok": True,
            **_worker_dispatch(request),
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except (Exception, SystemExit) as exc:
        payload = {
            "schema_version": OBSERVER_TARGET_READ_WORKER_SCHEMA,
            "ok": False,
            "message": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 2


__all__ = [
    "OBSERVER_TARGET_READ_TIMEOUT_SECONDS",
    "ObserverTargetReadError",
    "build_observer_target_views",
    "build_observer_target_views_bounded",
    "resolve_observer_project_bounded",
]


if __name__ == "__main__":
    raise SystemExit(_worker_main())
