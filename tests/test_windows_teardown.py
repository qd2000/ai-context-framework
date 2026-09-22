"""Deterministic unit tests for the shared Windows teardown helper.

Every time source, sleep call, PID probe and removal operation is injected, so
the whole module runs in milliseconds and cannot depend on real handle timing.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from tests import windows_teardown
from tests.windows_teardown import (
    cleanup_temporary_directory,
    default_pid_probe,
    resilient_rmtree,
    temporary_root,
    terminate_and_wait,
)


def _missing_path() -> Path:
    return Path(tempfile.gettempdir()) / f"acf-teardown-missing-{uuid.uuid4().hex}"


class _Clock:
    """Fake monotonic clock that advances whenever the code sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class _FakeProcess:
    def __init__(self, *, pid: int = 4242, exit_after_polls: int = 0) -> None:
        self.pid = pid
        self.exit_after_polls = exit_after_polls
        self.poll_calls = 0
        self.terminated = 0
        self.killed = 0

    def poll(self) -> int | None:
        self.poll_calls += 1
        return None if self.poll_calls <= self.exit_after_polls else 0

    def terminate(self) -> None:
        self.terminated += 1

    def kill(self) -> None:
        self.killed += 1


class _FakeDirectory:
    def __init__(self, failures: int = 0, error: BaseException | None = None) -> None:
        self.failures = failures
        self.error = error or PermissionError("WinError 32")
        self.calls = 0

    def cleanup(self) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error


class TerminateAndWaitTests(unittest.TestCase):
    def test_exited_process_needs_no_termination(self) -> None:
        clock = _Clock()
        process = _FakeProcess(exit_after_polls=0)

        self.assertTrue(
            terminate_and_wait(
                process,
                pid_probe=lambda _pid: False,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            )
        )
        self.assertEqual(0, process.terminated)
        self.assertEqual(0, process.killed)
        self.assertEqual([], clock.sleeps)

    def test_terminate_then_wait_until_pid_is_gone(self) -> None:
        clock = _Clock()
        process = _FakeProcess(exit_after_polls=1)
        probes: list[int] = []

        def probe(pid: int) -> bool:
            probes.append(pid)
            return len(probes) < 2

        self.assertTrue(
            terminate_and_wait(
                process,
                pid_probe=probe,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            )
        )
        self.assertEqual(1, process.terminated)
        self.assertEqual(0, process.killed)
        self.assertEqual(process.pid, probes[0])

    def test_kill_is_used_when_terminate_cannot_retire_the_process(self) -> None:
        clock = _Clock()
        process = _FakeProcess(exit_after_polls=100)

        self.assertFalse(
            terminate_and_wait(
                process,
                exit_timeout_seconds=1.0,
                pid_probe=lambda _pid: True,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            )
        )
        self.assertEqual(1, process.terminated)
        self.assertEqual(1, process.killed)
        self.assertTrue(clock.sleeps)

    def test_process_that_is_already_gone_is_not_terminated(self) -> None:
        clock = _Clock()
        process = _FakeProcess(exit_after_polls=0)
        process.pid = 0

        self.assertTrue(
            terminate_and_wait(
                process,
                pid_probe=lambda _pid: True,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            )
        )
        self.assertEqual(0, process.terminated)


class CleanupTemporaryDirectoryTests(unittest.TestCase):
    def test_first_attempt_reports_zero_retries(self) -> None:
        clock = _Clock()
        directory = _FakeDirectory()

        self.assertEqual(
            0,
            cleanup_temporary_directory(
                directory,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            ),
        )
        self.assertEqual(1, directory.calls)
        self.assertEqual([], clock.sleeps)

    def test_transient_handle_lag_is_absorbed_with_bounded_backoff(self) -> None:
        clock = _Clock()
        directory = _FakeDirectory(failures=2)

        retries = cleanup_temporary_directory(
            directory,
            timeout_seconds=15.0,
            initial_delay=0.25,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )

        self.assertEqual(2, retries)
        self.assertEqual(3, directory.calls)
        self.assertEqual([0.25, 0.5], clock.sleeps)

    def test_real_leak_still_raises_after_the_budget_is_exhausted(self) -> None:
        clock = _Clock()
        directory = _FakeDirectory(failures=99)
        sleeps = []

        with self.assertRaises(PermissionError):
            cleanup_temporary_directory(
                directory,
                timeout_seconds=1.0,
                initial_delay=0.25,
                max_delay=0.25,
                sleep=lambda value: (sleeps.append(value), clock.sleep(value))[1],
                monotonic=clock.monotonic,
            )
        self.assertLessEqual(sum(sleeps), 1.0 + 0.25)

    def test_unrelated_errors_propagate_immediately(self) -> None:
        clock = _Clock()
        directory = _FakeDirectory(failures=1, error=RuntimeError("not a handle problem"))

        with self.assertRaises(RuntimeError):
            cleanup_temporary_directory(
                directory,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            )
        self.assertEqual(1, directory.calls)
        self.assertEqual([], clock.sleeps)

    def test_tracked_processes_retire_before_cleanup_starts(self) -> None:
        clock = _Clock()
        process = _FakeProcess(exit_after_polls=1)
        order: list[str] = []

        class _RecordingDirectory:
            def cleanup(self) -> None:
                order.append("cleanup")

        original_terminate = process.terminate

        def recording_terminate() -> None:
            order.append("terminate")
            original_terminate()

        process.terminate = recording_terminate  # type: ignore[method-assign]

        cleanup_temporary_directory(
            _RecordingDirectory(),
            processes=(process,),
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        self.assertEqual(["terminate", "cleanup"], order)

    def test_missing_directory_is_a_no_op(self) -> None:
        self.assertEqual(0, cleanup_temporary_directory(None))


class ResilientRmtreeTests(unittest.TestCase):
    def test_missing_path_is_idempotent(self) -> None:
        calls: list[Path] = []

        self.assertEqual(
            0,
            resilient_rmtree(
                _missing_path(),
                rmtree=lambda path: calls.append(path),
            ),
        )
        self.assertEqual([], calls)

    def test_retries_then_succeeds(self) -> None:
        attempts: list[int] = []

        def rmtree(path: Path) -> None:
            attempts.append(1)
            if len(attempts) < 3:
                raise PermissionError("WinError 32")

        self.assertEqual(
            2,
            resilient_rmtree(
                Path(tempfile.gettempdir()),
                initial_delay=0.25,
                rmtree=rmtree,
            ),
        )
        self.assertEqual(3, len(attempts))

    def test_deadline_exhaustion_reraises(self) -> None:
        def rmtree(path: Path) -> None:
            raise PermissionError("WinError 32")

        with self.assertRaises(PermissionError):
            resilient_rmtree(
                Path(tempfile.gettempdir()),
                timeout_seconds=0.5,
                initial_delay=0.25,
                max_delay=0.25,
                rmtree=rmtree,
            )


class HelperSurfaceTests(unittest.TestCase):
    def test_default_pid_probe_sees_the_current_process(self) -> None:
        self.assertTrue(default_pid_probe(os.getpid()))
        self.assertFalse(default_pid_probe(0))

    def test_is_windows_matches_the_running_platform(self) -> None:
        self.assertEqual(os.name == "nt", windows_teardown.is_windows())

    def test_temporary_root_uses_a_resolved_canonical_parent(self) -> None:
        with temporary_root(prefix="acf-teardown-test-") as name:
            path = Path(name)
            self.assertTrue(path.exists())
            self.assertEqual(Path(tempfile.gettempdir()).resolve(), path.parent.resolve())


if __name__ == "__main__":
    unittest.main()
