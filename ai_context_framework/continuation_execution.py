"""Durable local-process identity for continuation physical execution.

The continuation control plane normally learns liveness from authenticated
heartbeats.  Long deterministic local commands are different: the owning
agent can be blocked waiting for one physical process while that process is
still making progress.  This module provides a small, database-free process
identity that can be persisted in the existing effect journal and probed by a
later scheduler wake.

Only an exact process identity counts as live.  A bare PID is insufficient
because operating systems reuse PIDs.  Windows uses the kernel process
creation FILETIME; Linux/other POSIX hosts prefer /proc start time and fall
back to ``ps`` start time when available.  Unverifiable evidence never becomes
positive liveness evidence.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import os
import signal
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping


PHYSICAL_EXECUTION_EFFECT_KIND = "continuation-physical-execution"
PROCESS_IDENTITY_PREFIX = "local-process-v1"


class ProcessIdentityError(RuntimeError):
    """Raised when a live process cannot be given a verifiable identity."""


def _encode_marker(marker: str) -> str:
    digest = hashlib.sha256(marker.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _windows_process_marker(pid: int) -> tuple[str, str | None, str]:
    # PROCESS_QUERY_LIMITED_INFORMATION works for an ordinary same-user child
    # without requesting mutation rights.
    process_query_limited_information = 0x1000
    synchronize = 0x00100000
    error_access_denied = 5
    error_invalid_parameter = 87

    class FileTime(ctypes.Structure):
        _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetProcessTimes.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
    ]
    kernel32.GetProcessTimes.restype = ctypes.c_int
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    handle = kernel32.OpenProcess(process_query_limited_information | synchronize, 0, int(pid))
    if not handle:
        error = ctypes.get_last_error()
        if error == error_invalid_parameter:
            return "terminal", None, "process_not_found"
        if error == error_access_denied:
            return "unverifiable", None, "process_access_denied"
        return "unverifiable", None, f"open_process_error:{error}"

    creation = FileTime()
    exit_time = FileTime()
    kernel = FileTime()
    user = FileTime()
    try:
        # A process object can remain openable after the process has exited.
        # Creation time therefore proves identity but not liveness.  Probe the
        # process object's signaled state first so a terminated process cannot
        # keep a stale continuation owner artificially fresh.
        wait_object_0 = 0x00000000
        wait_timeout = 0x00000102
        wait_failed = 0xFFFFFFFF
        wait_result = int(kernel32.WaitForSingleObject(handle, 0))
        if wait_result == wait_object_0:
            return "terminal", None, "process_exited"
        if wait_result == wait_failed:
            return "unverifiable", None, f"wait_process_error:{ctypes.get_last_error()}"
        if wait_result != wait_timeout:
            return "unverifiable", None, f"wait_process_unexpected:{wait_result}"

        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return "unverifiable", None, f"get_process_times_error:{ctypes.get_last_error()}"
        ticks = (int(creation.high) << 32) | int(creation.low)
        return "live", f"windows-filetime:{ticks}", "process_identity_verified"
    finally:
        kernel32.CloseHandle(handle)


def _proc_process_marker(pid: int) -> tuple[str, str | None, str] | None:
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        raw = stat_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "terminal", None, "process_not_found"
    except OSError:
        return None
    close = raw.rfind(")")
    if close < 0:
        return None
    fields = raw[close + 2 :].split()
    if not fields:
        return None
    # /proc retains zombie/dead process records until their parent reaps
    # them. Stable PID/start identity therefore does not by itself prove
    # useful physical execution is still live.
    if fields[0] in {"Z", "X", "x"}:
        return "terminal", None, "process_exited"
    # fields[0] is field 3 (state), so field 22 (starttime) is index 19.
    if len(fields) <= 19:
        return None
    return "live", f"proc-starttime:{fields[19]}", "process_identity_verified"


def _ps_process_marker(pid: int) -> tuple[str, str | None, str]:
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat=", "-o", "lstart="],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unverifiable", None, "process_probe_unavailable"
    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        return "terminal", None, "process_not_found"
    parts = output.split(maxsplit=1)
    if len(parts) != 2:
        return "unverifiable", None, "process_probe_unparseable"
    state, marker = parts
    if state[:1] in {"Z", "X", "x"}:
        return "terminal", None, "process_exited"
    return "live", f"ps-lstart:{marker}", "process_identity_verified"


def process_start_marker(pid: int) -> tuple[str, str | None, str]:
    """Return ``(status, marker, reason)`` for one operating-system process."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
        return "invalid", None, "invalid_pid"
    if os.name == "nt":  # pragma: no branch - production Windows path.
        return _windows_process_marker(pid)
    proc = _proc_process_marker(pid)
    if proc is not None:
        return proc
    return _ps_process_marker(pid)


def capture_process_identity(pid: int) -> str:
    """Capture a PID plus a non-reusable start marker for durable evidence."""
    status, marker, reason = process_start_marker(pid)
    if status != "live" or not marker:
        raise ProcessIdentityError(f"cannot capture live process identity: {reason}")
    return f"{PROCESS_IDENTITY_PREFIX}:{pid}:{_encode_marker(marker)}"


def parse_process_identity(value: str | None) -> tuple[int, str] | None:
    if not isinstance(value, str):
        return None
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != PROCESS_IDENTITY_PREFIX:
        return None
    try:
        pid = int(parts[1])
    except ValueError:
        return None
    marker_digest = parts[2]
    if pid < 1 or len(marker_digest) != 43:
        return None
    return pid, marker_digest


def probe_process_identity(value: str | None) -> dict[str, Any]:
    """Probe persisted process evidence without granting any authority."""
    parsed = parse_process_identity(value)
    if parsed is None:
        return {
            "status": "invalid",
            "live": False,
            "pid": None,
            "reason": "process_identity_invalid",
        }
    pid, expected_digest = parsed
    status, marker, reason = process_start_marker(pid)
    if status == "live" and marker:
        if _encode_marker(marker) == expected_digest:
            return {"status": "live", "live": True, "pid": pid, "reason": reason}
        return {
            "status": "terminal",
            "live": False,
            "pid": pid,
            "reason": "pid_reused_or_process_replaced",
        }
    return {"status": status, "live": False, "pid": pid, "reason": reason}


def physical_execution_probes(
    effects: Iterable[Mapping[str, Any]],
    *,
    generation: int | None,
) -> list[dict[str, Any]]:
    """Probe active physical-execution effects owned by one generation."""
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        return []
    probes: list[dict[str, Any]] = []
    for effect in effects:
        if effect.get("kind") != PHYSICAL_EXECUTION_EFFECT_KIND:
            continue
        if effect.get("status") != "active" or effect.get("last_generation") != generation:
            continue
        probe = probe_process_identity(effect.get("external_id"))
        probes.append(
            {
                "logical_key": effect.get("logical_key"),
                "effect_id": effect.get("effect_id"),
                "external_id": effect.get("external_id"),
                **probe,
            }
        )
    return probes


def terminate_process_tree(process: subprocess.Popen[Any], *, timeout_seconds: float = 5.0) -> None:
    """Terminate one supervised process and only its descendant tree.

    The physical-execution supervisor must never turn a controller failure into
    a new orphan.  Killing only the direct wrapper PID is insufficient for
    commands such as ``uv run ...`` because the useful Python process can be a
    descendant.  Windows therefore uses the OS ``taskkill /T`` primitive on the
    exact root PID; POSIX children are launched in their own session and the
    matching process group is killed.  A direct-process kill remains the final
    fallback when the platform tree primitive is unavailable.
    """

    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=timeout_seconds,
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
    try:
        process.wait(timeout=timeout_seconds)
    except (OSError, subprocess.TimeoutExpired):
        pass


__all__ = [
    "PHYSICAL_EXECUTION_EFFECT_KIND",
    "PROCESS_IDENTITY_PREFIX",
    "ProcessIdentityError",
    "capture_process_identity",
    "parse_process_identity",
    "physical_execution_probes",
    "probe_process_identity",
    "process_start_marker",
    "terminate_process_tree",
]
