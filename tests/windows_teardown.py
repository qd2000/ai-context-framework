"""Bounded-retry teardown helpers for tests that mix child processes and temp roots.

Why this module exists
----------------------

On Windows the OS releases the last handles of a terminated process
asynchronously. A test that starts a process *inside* a temporary directory and
then lets ``TemporaryDirectory`` delete that tree can therefore fail with
``PermissionError`` / ``WinError 32`` even though the test itself passed.

The helpers below absorb that transient lag with an explicit, bounded budget:

1. first confirm the process tree is really gone (poll the PID, not just
   ``wait()``, because ``wait()`` returns before every handle is released);
2. then retry the removal with exponential backoff until a deadline;
3. never swallow a real leak - once the budget is exhausted the original error
   is re-raised so CI still reports the genuine failure.

Every side effect (time source, sleeping, PID probing, the removal itself) is
injectable so unit tests stay deterministic and millisecond-fast.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

DEFAULT_EXIT_TIMEOUT_SECONDS = 5.0
DEFAULT_CLEANUP_TIMEOUT_SECONDS = 15.0
DEFAULT_INITIAL_DELAY_SECONDS = 0.25
DEFAULT_MAX_DELAY_SECONDS = 2.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.05

RETRY_ERRORS: tuple[type[BaseException], ...] = (PermissionError, OSError)

PidProbe = Callable[[int], bool]


def is_windows() -> bool:
    """Return True on Windows, where handle release is asynchronous."""

    return os.name == "nt"


def default_pid_probe(pid: int) -> bool:
    """Report whether ``pid`` still exists, without extra dependencies."""

    if pid <= 0:
        return False
    if not is_windows():
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def _process_pid(process: Any) -> int:
    try:
        pid = process.pid
    except Exception:  # pragma: no cover - defensive for stubbed processes
        return 0
    return int(pid) if isinstance(pid, int) else 0


def _process_exited(process: Any) -> bool:
    try:
        return process.poll() is not None
    except Exception:  # pragma: no cover - defensive for stubbed processes
        return True


def _wait_until_dead(
    process: Any,
    *,
    deadline: float,
    pid_probe: PidProbe,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
    poll_interval: float,
) -> bool:
    while True:
        pid = _process_pid(process)
        pid_gone = pid <= 0 or not pid_probe(pid)
        if _process_exited(process) and pid_gone:
            return True
        remaining = deadline - monotonic()
        if remaining <= 0:
            return False
        sleep(min(poll_interval, remaining))


def terminate_and_wait(
    process: Any,
    *,
    exit_timeout_seconds: float = DEFAULT_EXIT_TIMEOUT_SECONDS,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    pid_probe: PidProbe | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    """Terminate ``process`` (then kill it) and wait until the PID is gone.

    Returns True when the process and its PID are confirmed gone, False when the
    timeout budget elapsed first. A False result does not raise: the caller keeps
    control, and the cleanup retry still decides whether to fail the test.
    """

    probe = pid_probe or default_pid_probe
    started = monotonic()
    deadline = started + max(0.0, exit_timeout_seconds)

    if not _process_exited(process):
        try:
            process.terminate()
        except (ProcessLookupError, OSError):
            pass
    if _wait_until_dead(
        process,
        deadline=deadline,
        pid_probe=probe,
        sleep=sleep,
        monotonic=monotonic,
        poll_interval=poll_interval,
    ):
        return True

    try:
        process.kill()
    except (ProcessLookupError, OSError):
        pass
    return _wait_until_dead(
        process,
        deadline=deadline,
        pid_probe=probe,
        sleep=sleep,
        monotonic=monotonic,
        poll_interval=poll_interval,
    )


def _retry_with_backoff(
    operation: Callable[[], None],
    *,
    timeout_seconds: float,
    initial_delay: float,
    max_delay: float,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> int:
    started = monotonic()
    deadline = started + max(0.0, timeout_seconds)
    attempt = 0
    while True:
        try:
            operation()
        except RETRY_ERRORS:
            if monotonic() >= deadline:
                raise
            delay = min(max_delay, initial_delay * (2 ** attempt))
            remaining = deadline - monotonic()
            sleep(max(0.0, min(delay, remaining)))
            attempt += 1
            continue
        return attempt


def cleanup_temporary_directory(
    directory: Any | None,
    *,
    processes: Sequence[Any] = (),
    exit_timeout_seconds: float = DEFAULT_EXIT_TIMEOUT_SECONDS,
    timeout_seconds: float = DEFAULT_CLEANUP_TIMEOUT_SECONDS,
    initial_delay: float = DEFAULT_INITIAL_DELAY_SECONDS,
    max_delay: float = DEFAULT_MAX_DELAY_SECONDS,
    pid_probe: PidProbe | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> int:
    """Retire tracked processes then remove ``directory`` with bounded retries.

    Returns the number of removal retries that were needed (0 when the first
    attempt succeeded). A genuine leak still raises once the budget is gone.
    """

    for process in processes:
        terminate_and_wait(
            process,
            exit_timeout_seconds=exit_timeout_seconds,
            pid_probe=pid_probe,
            sleep=sleep,
            monotonic=monotonic,
        )
    if directory is None:
        return 0
    return _retry_with_backoff(
        directory.cleanup,
        timeout_seconds=timeout_seconds,
        initial_delay=initial_delay,
        max_delay=max_delay,
        sleep=sleep,
        monotonic=monotonic,
    )


def resilient_rmtree(
    path: str | Path | None,
    *,
    timeout_seconds: float = DEFAULT_CLEANUP_TIMEOUT_SECONDS,
    initial_delay: float = DEFAULT_INITIAL_DELAY_SECONDS,
    max_delay: float = DEFAULT_MAX_DELAY_SECONDS,
    rmtree: Callable[[Any], None] = shutil.rmtree,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> int:
    """Remove a tree with bounded retries; idempotent when it is already gone.

    Returns the number of retries that were needed; re-raises the original error
    once ``timeout_seconds`` elapsed so a real leak is never hidden.
    """

    if path is None:
        return 0
    target = Path(path)
    started = monotonic()
    deadline = started + max(0.0, timeout_seconds)
    attempt = 0
    while True:
        if not target.exists():
            return attempt
        try:
            rmtree(target)
        except RETRY_ERRORS:
            if monotonic() >= deadline:
                raise
            delay = min(max_delay, initial_delay * (2 ** attempt))
            remaining = deadline - monotonic()
            sleep(max(0.0, min(delay, remaining)))
            attempt += 1
            continue
        return attempt


def temporary_root(prefix: str = "acf-test-") -> tempfile.TemporaryDirectory[str]:
    """Return a canonical temporary directory rooted at a resolved temp path.

    Hosted Windows runners expose ``TEMP`` through 8.3 short names
    (``C:\\Users\\RUNNER~1\\...``) while other observers see the canonical form.
    Resolving the parent keeps every comparison and every spawned process inside
    one representation.
    """

    root = Path(tempfile.gettempdir()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix, dir=str(root))


def cleanup_iterable(items: Iterable[Any], **kwargs: Any) -> None:
    """Convenience wrapper cleaning every temporary directory in ``items``."""

    for item in items:
        cleanup_temporary_directory(item, **kwargs)
