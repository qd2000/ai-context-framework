from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import acf

from ai_context_framework.observer_target_projection import (
    ObserverTargetReadError,
    _run_target_read_worker,
    _target_read_worker_command,
    _terminate_worker_tree,
    resolve_observer_project_bounded,
)


class _TimeoutProcess:
    pid = 4242
    returncode = None

    def __init__(self):
        self.communicate_calls = 0

    def communicate(self, _input=None, timeout=None):
        self.communicate_calls += 1
        if self.communicate_calls == 1:
            raise subprocess.TimeoutExpired(cmd="observer-target-read-worker", timeout=timeout)
        self.returncode = -9
        return "", "worker diagnostic"

    def poll(self):
        return self.returncode


class _ResultProcess:
    pid = 4343

    def __init__(self, *, returncode: int, stdout: str, stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def communicate(self, _input=None, timeout=None):
        return self.stdout, self.stderr

    def poll(self):
        return self.returncode


class ObserverTargetProjectionBoundedReadTests(unittest.TestCase):
    def test_windows_worker_bootstrap_uses_killable_system_launcher_before_python(self):
        with mock.patch("ai_context_framework.observer_target_projection.os.name", "nt"), mock.patch.dict(
            os.environ,
            {"COMSPEC": r"C:\Windows\System32\cmd.exe"},
            clear=False,
        ):
            command = _target_read_worker_command()
        self.assertEqual(command[:4], [r"C:\Windows\System32\cmd.exe", "/d", "/s", "/c"])
        self.assertIn("observer_target_projection", command[4])
        self.assertIn("--worker", command[4])
        self.assertIn(Path(os.sys.executable).name, command[4])

    def test_windows_timeout_cleanup_targets_exact_worker_pid_tree(self):
        process = mock.Mock()
        process.pid = 4242
        process.poll.side_effect = [None, None]
        with mock.patch("ai_context_framework.observer_target_projection.os.name", "nt"), mock.patch(
            "ai_context_framework.observer_target_projection.subprocess.run"
        ) as run:
            _terminate_worker_tree(process)
        run.assert_called_once_with(
            ["taskkill.exe", "/PID", "4242", "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        process.kill.assert_called_once_with()

    def test_worker_timeout_terminates_exact_worker_tree_and_fails_visible(self):
        process = _TimeoutProcess()
        with mock.patch("subprocess.Popen", return_value=process), mock.patch(
            "ai_context_framework.observer_target_projection._terminate_worker_tree"
        ) as terminate:
            with self.assertRaises(ObserverTargetReadError) as raised:
                _run_target_read_worker({"operation": "resolve_project", "path": "C:/slow"}, timeout_seconds=0.01)
        self.assertEqual(raised.exception.error_code, "observer_target_read_timeout")
        self.assertIn("bounded deadline", str(raised.exception))
        self.assertEqual(raised.exception.stderr, "worker diagnostic")
        terminate.assert_called_once_with(process)

    def test_worker_spawn_itself_is_bounded_and_late_process_is_cleaned(self):
        process = _ResultProcess(returncode=None, stdout="", stderr="")
        release_spawn = threading.Event()
        late_cleanup = threading.Event()

        def blocking_popen(*_args, **_kwargs):
            release_spawn.wait(timeout=2)
            return process

        def record_cleanup(_process):
            late_cleanup.set()

        started = time.monotonic()
        with mock.patch("subprocess.Popen", side_effect=blocking_popen), mock.patch(
            "ai_context_framework.observer_target_projection._terminate_worker_tree",
            side_effect=record_cleanup,
        ):
            with self.assertRaises(ObserverTargetReadError) as raised:
                _run_target_read_worker(
                    {"operation": "resolve_project", "path": "C:/spawn-stall"},
                    timeout_seconds=0.03,
                )
            elapsed = time.monotonic() - started
            self.assertEqual(raised.exception.error_code, "observer_target_read_timeout")
            self.assertIn("worker launch", str(raised.exception))
            self.assertLess(elapsed, 0.5)
            release_spawn.set()
            self.assertTrue(late_cleanup.wait(timeout=1))

    def test_real_worker_round_trip_is_terminal_for_repository_project(self):
        project_root = Path(__file__).resolve().parents[1]
        started = time.monotonic()
        project = resolve_observer_project_bounded(project_root, timeout_seconds=5)
        self.assertTrue(project.project_id)
        self.assertLess(time.monotonic() - started, 5)

    def test_worker_failure_parses_json_only_from_stdout(self):
        process = _ResultProcess(
            returncode=2,
            stdout=json.dumps({"ok": False, "message": "Git discovery failed"}),
            stderr="warning: this is diagnostics, not JSON",
        )
        with mock.patch("subprocess.Popen", return_value=process):
            with self.assertRaises(ObserverTargetReadError) as raised:
                _run_target_read_worker({"operation": "resolve_project", "path": "C:/bad"})
        self.assertEqual(raised.exception.error_code, "observer_target_read_failed")
        self.assertEqual(str(raised.exception), "Git discovery failed")
        self.assertEqual(raised.exception.stderr, "warning: this is diagnostics, not JSON")

    def test_bounded_project_resolution_reconstructs_worker_payload_without_reresolve(self):
        worker_payload = {
            "ok": True,
            "project": {
                "project_id": "project-test",
                "canonical_root": "C:/canonical",
                "invocation_root": "C:/linked",
                "context_root": "C:/canonical/docs/ai",
                "observer_dir": "C:/acf-home/projects/project-test/observer",
                "git_managed": True,
            },
        }
        with mock.patch(
            "ai_context_framework.observer_target_projection._run_target_read_worker",
            return_value=worker_payload,
        ) as worker:
            project = resolve_observer_project_bounded(Path("C:/linked"), timeout_seconds=7)
        self.assertEqual(project.project_id, "project-test")
        self.assertEqual(str(project.canonical_root).replace("\\", "/"), "C:/canonical")
        self.assertEqual(str(project.invocation_root).replace("\\", "/"), "C:/linked")
        self.assertTrue(project.git_managed)
        request = worker.call_args.args[0]
        self.assertEqual(request["operation"], "resolve_project")
        self.assertEqual(worker.call_args.kwargs["timeout_seconds"], 7)


class ObserverTargetProjectionCliFailureTests(unittest.TestCase):
    def setUp(self):
        self._previous_acf_home = os.environ.get("ACF_HOME")
        self._acf_home = tempfile.TemporaryDirectory()
        os.environ["ACF_HOME"] = self._acf_home.name

    def tearDown(self):
        if self._previous_acf_home is None:
            os.environ.pop("ACF_HOME", None)
        else:
            os.environ["ACF_HOME"] = self._previous_acf_home
        self._acf_home.cleanup()

    def run_cli(self, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = acf.main(args)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_target_set_timeout_fails_before_creating_observer_runtime(self):
        before = list(Path(self._acf_home.name).rglob("*"))
        self.assertEqual(before, [])
        error = ObserverTargetReadError(
            "observer_target_read_timeout",
            "Observer target/project read exceeded the 30s bounded deadline and was terminated.",
        )
        with mock.patch(
            "ai_context_framework.commands.observer.resolve_observer_project_bounded",
            side_effect=error,
        ):
            exit_code, stdout, _stderr = self.run_cli(
                [
                    "observer",
                    "target-set",
                    "C:/slow-project",
                    "--target-id",
                    "ws012-writer",
                    "--mode",
                    "fixed_workstream",
                    "--title",
                    "WS012 Writer",
                    "--automation-ref",
                    "automation:ws012",
                    "--workstream",
                    "WS012",
                    "--continuation-task-id",
                    "WS012",
                    "--json",
                ]
            )
        self.assertNotEqual(exit_code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["error_code"], "observer_target_read_timeout")
        self.assertEqual(list(Path(self._acf_home.name).rglob("*")), [])

    def test_presentation_status_timeout_is_fail_visible(self):
        error = ObserverTargetReadError(
            "observer_target_read_timeout",
            "Observer target/project read exceeded the 30s bounded deadline and was terminated.",
        )
        with mock.patch(
            "ai_context_framework.commands.observer_presentation.resolve_observer_project_bounded",
            side_effect=error,
        ):
            exit_code, stdout, _stderr = self.run_cli(
                ["observer", "presentation-status", "C:/slow-project", "--json"]
            )
        self.assertNotEqual(exit_code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["error_code"], "observer_target_read_timeout")

    def test_semantic_review_timeout_is_fail_visible_before_input_or_state_write(self):
        error = ObserverTargetReadError(
            "observer_target_read_timeout",
            "Observer target/project read exceeded the 30s bounded deadline and was terminated.",
        )
        with mock.patch(
            "ai_context_framework.commands.observer_presentation.resolve_observer_project_bounded",
            side_effect=error,
        ):
            exit_code, stdout, _stderr = self.run_cli(
                [
                    "observer",
                    "semantic-review-apply",
                    "C:/slow-project",
                    "--target-id",
                    "ws012-writer",
                    "--review-id",
                    "review-timeout",
                    "--expected-target-revision",
                    "0",
                    "--source-fingerprint",
                    "source-timeout",
                    "--authority-fingerprint",
                    "authority-timeout",
                    "--authority-reread",
                    "--decision",
                    "rebuild",
                    "--reason",
                    "Bounded read failure must stop before semantic input is consumed.",
                    "--evidence-ref",
                    "test:timeout",
                    "--presentation-type",
                    "roadmap",
                    "--input",
                    "C:/definitely-not-read.json",
                    "--json",
                ]
            )
        self.assertNotEqual(exit_code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["error_code"], "observer_target_read_timeout")
        self.assertEqual(list(Path(self._acf_home.name).rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
