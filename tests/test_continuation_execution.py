from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import acf
from ai_context_framework import continuation_execution
from ai_context_framework.commands import continuation
from ai_context_framework.commands import continuation_execution as continuation_execution_commands
from ai_context_framework.commands import continuation_workspace as continuation_workspace_commands


class ContinuationExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._home = tempfile.TemporaryDirectory()
        self._repo = tempfile.TemporaryDirectory()
        self.previous_home = os.environ.get("ACF_HOME")
        os.environ["ACF_HOME"] = self._home.name
        self.root = Path(self._repo.name).resolve()
        self._git("init", "-b", "main")
        self._git("config", "user.name", "ACF Execution Test")
        self._git("config", "user.email", "acf-execution@example.invalid")
        (self.root / "README.md").write_text("continuation execution\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-m", "test: init")

    def tearDown(self) -> None:
        if self.previous_home is None:
            os.environ.pop("ACF_HOME", None)
        else:
            os.environ["ACF_HOME"] = self.previous_home
        self._repo.cleanup()
        self._home.cleanup()

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            self.fail(result.stderr or result.stdout)
        return result

    def run_json(self, args: list[str], *, already_json: bool = False) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = acf.main(args if already_json else [*args, "--json"])
        raw = stdout.getvalue().strip()
        self.assertTrue(raw, stderr.getvalue())
        return code, json.loads(raw), stderr.getvalue()

    def init_and_claim(self) -> tuple[dict[str, object], dict[str, object]]:
        code, initialized, stderr = self.run_json(
            [
                "continuation",
                "init",
                str(self.root),
                "--task-id",
                "WS900",
                "--title",
                "Physical execution test",
                "--objective",
                "Protect a long local process from false stale-owner recovery.",
                "--next-action",
                "Run the supervised process.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{initialized}")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS900",
                "--runner-id",
                "runner-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        return initialized, claim

    def owner_flags(self, claim: dict[str, object]) -> list[str]:
        lease = claim["lease"]
        self.assertIsInstance(lease, dict)
        return [
            "--generation",
            str(lease["generation"]),
            "--fence-token",
            str(claim["fence_token"]),
        ]

    def test_process_identity_rejects_pid_reuse(self) -> None:
        with patch.object(
            continuation_execution,
            "process_start_marker",
            return_value=("live", "marker-a", "process_identity_verified"),
        ):
            identity = continuation_execution.capture_process_identity(321)
        with patch.object(
            continuation_execution,
            "process_start_marker",
            return_value=("live", "marker-b", "process_identity_verified"),
        ):
            probe = continuation_execution.probe_process_identity(identity)
        self.assertFalse(probe["live"])
        self.assertEqual("terminal", probe["status"])
        self.assertEqual("pid_reused_or_process_replaced", probe["reason"])

    @unittest.skipUnless(os.name == "nt", "Windows taskkill /T integration")
    def test_tree_cleanup_terminates_supervised_descendants(self) -> None:
        pid_path = self.root / "grandchild.pid"
        parent = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import pathlib, subprocess, sys, time; "
                    "p=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
                    f"pathlib.Path({str(pid_path)!r}).write_text(str(p.pid), encoding='utf-8'); "
                    "time.sleep(60)"
                ),
            ],
            cwd=self.root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        grandchild_pid: int | None = None
        try:
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and not pid_path.exists():
                time.sleep(0.02)
            self.assertTrue(pid_path.exists(), "parent did not report descendant PID")
            grandchild_pid = int(pid_path.read_text(encoding="utf-8"))
            self.assertEqual("live", continuation_execution.process_start_marker(grandchild_pid)[0])

            continuation_execution.terminate_process_tree(parent)
            self.assertIsNotNone(parent.poll())
            deadline = time.monotonic() + 5.0
            status = "live"
            while time.monotonic() < deadline:
                status = continuation_execution.process_start_marker(grandchild_pid)[0]
                if status == "terminal":
                    break
                time.sleep(0.02)
            self.assertEqual("terminal", status)
        finally:
            if parent.poll() is None:
                continuation_execution.terminate_process_tree(parent)
            if grandchild_pid is not None:
                status = continuation_execution.process_start_marker(grandchild_pid)[0]
                if status == "live":
                    subprocess.run(
                        ["taskkill.exe", "/PID", str(grandchild_pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                        timeout=5,
                    )

    def test_proc_zombie_identity_is_terminal(self) -> None:
        with patch.object(Path, "read_text", return_value="321 (python) Z"):
            probe = continuation_execution._proc_process_marker(321)
        self.assertEqual(("terminal", None, "process_exited"), probe)

    def test_ps_zombie_identity_is_terminal(self) -> None:
        result = subprocess.CompletedProcess(
            args=["ps"],
            returncode=0,
            stdout="Z+   Sun Sep  6 00:00:00 2026\n",
            stderr="",
        )
        with patch.object(subprocess, "run", return_value=result):
            probe = continuation_execution._ps_process_marker(321)
        self.assertEqual(("terminal", None, "process_exited"), probe)

    def test_supervised_execution_keeps_machine_output_json_and_terminalizes_effect(self) -> None:
        _, claim = self.init_and_claim()
        lease = claim["lease"]
        self.assertIsInstance(lease, dict)
        args = [
            "continuation",
            "execution",
            "run",
            str(self.root),
            "--task-id",
            "WS900",
            "--lease-id",
            str(lease["lease_id"]),
            *self.owner_flags(claim),
            "--key",
            "validation-gate-001",
            "--json",
            "--",
            sys.executable,
            "-c",
            "print('supervised-output')",
        ]
        code, result, stderr = self.run_json(args, already_json=True)
        self.assertEqual(0, code, f"{stderr}\n{result}")
        self.assertTrue(result["ok"])
        self.assertEqual("physical_execution_completed", result["status"])
        self.assertEqual(0, result["returncode"])
        self.assertEqual("supervised-output\n", result["child_stdout"])
        effect = result["effect"]
        self.assertIsInstance(effect, dict)
        self.assertEqual("completed", effect["status"])
        self.assertEqual(
            continuation_execution.PHYSICAL_EXECUTION_EFFECT_KIND,
            effect["kind"],
        )

        code, replay, _ = self.run_json(args, already_json=True)
        self.assertEqual(3, code)
        self.assertFalse(replay["ok"])
        self.assertEqual("physical_execution_identity_exists", replay["error_code"])

    def test_supervised_child_failure_is_terminal_and_not_replayable(self) -> None:
        _, claim = self.init_and_claim()
        lease = claim["lease"]
        self.assertIsInstance(lease, dict)
        args = [
            "continuation",
            "execution",
            "run",
            str(self.root),
            "--task-id",
            "WS900",
            "--lease-id",
            str(lease["lease_id"]),
            *self.owner_flags(claim),
            "--key",
            "failing-gate-001",
            "--json",
            "--",
            sys.executable,
            "-c",
            "import sys; print('expected-failure', file=sys.stderr); raise SystemExit(7)",
        ]
        code, result, stderr = self.run_json(args, already_json=True)
        self.assertEqual(2, code, f"{stderr}\n{result}")
        self.assertFalse(result["ok"])
        self.assertEqual("physical_execution_child_failed", result["error_code"])
        self.assertEqual("physical_execution_failed", result["status"])
        self.assertEqual(7, result["returncode"])
        self.assertEqual("failed", result["effect"]["status"])
        self.assertIn("expected-failure", result["child_stderr"])

        code, replay, _ = self.run_json(args, already_json=True)
        self.assertEqual(3, code)
        self.assertFalse(replay["ok"])
        self.assertEqual("physical_execution_identity_exists", replay["error_code"])

    def test_supervisor_refreshes_owner_while_child_is_running(self) -> None:
        _, claim = self.init_and_claim()
        lease = claim["lease"]
        self.assertIsInstance(lease, dict)
        args = [
            "continuation",
            "execution",
            "run",
            str(self.root),
            "--task-id",
            "WS900",
            "--lease-id",
            str(lease["lease_id"]),
            *self.owner_flags(claim),
            "--key",
            "keepalive-proof-001",
            "--json",
            "--",
            sys.executable,
            "-c",
            "import time; time.sleep(0.25)",
        ]
        with (
            patch.object(continuation_execution_commands, "_keepalive_seconds", return_value=0.03),
            patch.object(continuation_execution_commands, "_poll_seconds", return_value=0.01),
            patch.object(
                continuation_execution_commands,
                "_record_keepalive",
                wraps=continuation_execution_commands._record_keepalive,
            ) as keepalive,
        ):
            code, result, stderr = self.run_json(args, already_json=True)
        self.assertEqual(0, code, f"{stderr}\n{result}")
        self.assertEqual("physical_execution_completed", result["status"])
        # The supervisor records one keepalive immediately after durable
        # process identity plus the terminal keepalive.  Longer children may
        # add periodic keepalives between them.
        self.assertGreaterEqual(keepalive.call_count, 2)

    def test_supervisor_scrubs_parent_fence_token_file_from_child_environment(self) -> None:
        token_file = Path(self._home.name) / "parent-owner-fence.token"
        with patch.dict(
            os.environ,
            {continuation_workspace_commands.FENCE_TOKEN_FILE_ENV: str(token_file)},
            clear=False,
        ):
            _, claim = self.init_and_claim()
            lease = claim["lease"]
            self.assertIsInstance(lease, dict)
            self.assertIsNone(claim["fence_token"])
            self.assertTrue(token_file.is_file())
            token_before = token_file.read_bytes()
            args = [
                "continuation",
                "execution",
                "run",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                str(lease["lease_id"]),
                "--generation",
                str(lease["generation"]),
                "--key",
                "credential-env-scrub-001",
                "--json",
                "--",
                sys.executable,
                "-c",
                (
                    "import os; "
                    f"print(os.environ.get({continuation_workspace_commands.FENCE_TOKEN_FILE_ENV!r}, 'ABSENT'))"
                ),
            ]
            code, result, stderr = self.run_json(args, already_json=True)

            self.assertEqual(0, code, f"{stderr}\n{result}")
            self.assertEqual("physical_execution_completed", result["status"])
            self.assertEqual("ABSENT\n", result["child_stdout"])
            self.assertEqual(token_before, token_file.read_bytes())

    def test_pause_during_supervised_execution_waits_for_terminal_and_requests_release(self) -> None:
        initialized, claim = self.init_and_claim()
        state_dir = Path(str(initialized["state_dir"]))
        lease = claim["lease"]
        self.assertIsInstance(lease, dict)
        args = [
            "continuation",
            "execution",
            "run",
            str(self.root),
            "--task-id",
            "WS900",
            "--lease-id",
            str(lease["lease_id"]),
            *self.owner_flags(claim),
            "--key",
            "pause-after-spawn-001",
            "--json",
            "--",
            sys.executable,
            "-c",
            "import time; time.sleep(0.25); print('terminal-after-pause')",
        ]

        spawned = threading.Event()
        real_capture_process_identity = continuation_execution.capture_process_identity

        def capture_and_signal(pid: int) -> str:
            identity = real_capture_process_identity(pid)
            spawned.set()
            return identity

        def request_pause() -> None:
            self.assertTrue(spawned.wait(timeout=1))
            continuation._write_json(
                state_dir / "pause.json",
                {
                    "schema_version": continuation.PAUSE_SCHEMA,
                    "task_id": "WS900",
                    "reason": "test pause while child is live",
                    "requested_by": "test",
                    "created_at": continuation._iso(),
                },
            )

        pause_thread = threading.Thread(target=request_pause, daemon=True)
        pause_thread.start()
        with (
            patch.object(
                continuation_execution,
                "capture_process_identity",
                side_effect=capture_and_signal,
            ),
            patch.object(continuation_execution_commands, "_keepalive_seconds", return_value=0.03),
            patch.object(continuation_execution_commands, "_poll_seconds", return_value=0.01),
        ):
            code, result, stderr = self.run_json(args, already_json=True)
        pause_thread.join(timeout=1)

        self.assertEqual(0, code, f"{stderr}\n{result}")
        self.assertEqual("physical_execution_completed", result["status"])
        self.assertEqual("completed", result["effect"]["status"])
        self.assertEqual("terminal-after-pause\n", result["child_stdout"])
        self.assertTrue(result["pause_pending"])
        self.assertTrue((state_dir / "pause.json").exists())
        self.assertTrue(any("Release the current round" in action for action in result["next_actions"]))

    def test_fast_terminal_child_does_not_become_unknown_effect(self) -> None:
        _, claim = self.init_and_claim()
        lease = claim["lease"]
        self.assertIsInstance(lease, dict)
        args = [
            "continuation",
            "execution",
            "run",
            str(self.root),
            "--task-id",
            "WS900",
            "--lease-id",
            str(lease["lease_id"]),
            *self.owner_flags(claim),
            "--key",
            "fast-terminal-001",
            "--json",
            "--",
            sys.executable,
            "-c",
            "print('fast')",
        ]

        def fail_after_child_exit(_pid: int) -> str:
            time.sleep(0.2)
            raise continuation_execution.ProcessIdentityError("already terminal")

        with patch.object(
            continuation_execution,
            "capture_process_identity",
            side_effect=fail_after_child_exit,
        ):
            code, result, stderr = self.run_json(args, already_json=True)
        self.assertEqual(0, code, f"{stderr}\n{result}")
        self.assertEqual("physical_execution_completed", result["status"])
        self.assertEqual("completed", result["effect"]["status"])
        self.assertIsNone(result["process_identity"])

    def test_verified_live_process_prevents_stale_challenge_but_terminal_process_does_not(self) -> None:
        initialized, claim = self.init_and_claim()
        state_dir = Path(str(initialized["state_dir"]))
        lease = claim["lease"]
        self.assertIsInstance(lease, dict)
        sleeper = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=self.root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            process_identity = continuation_execution.capture_process_identity(sleeper.pid)
            owner = ["--lease-id", str(lease["lease_id"]), *self.owner_flags(claim)]
            code, prepared, stderr = self.run_json(
                [
                    "continuation",
                    "effect",
                    "prepare",
                    str(self.root),
                    "--task-id",
                    "WS900",
                    *owner,
                    "--key",
                    "physical-process-live",
                    "--kind",
                    continuation_execution.PHYSICAL_EXECUTION_EFFECT_KIND,
                    "--external-id",
                    process_identity,
                ]
            )
            self.assertEqual(0, code, f"{stderr}\n{prepared}")
            code, active, stderr = self.run_json(
                [
                    "continuation",
                    "effect",
                    "update",
                    str(self.root),
                    "--task-id",
                    "WS900",
                    *owner,
                    "--key",
                    "physical-process-live",
                    "--status",
                    "active",
                    "--milestone",
                    "process-running",
                ]
            )
            self.assertEqual(0, code, f"{stderr}\n{active}")

            lease_path = state_dir / "lease.json"
            lease_payload = json.loads(lease_path.read_text(encoding="utf-8"))
            now = continuation._now()
            lease_payload["issued_at"] = continuation._iso(now - timedelta(minutes=60))
            lease_payload["last_renew_at"] = continuation._iso(now - timedelta(minutes=60))
            lease_payload["last_heartbeat_at"] = continuation._iso(now - timedelta(minutes=31))
            lease_payload["expires_at"] = continuation._iso(now + timedelta(minutes=60))
            continuation._write_json(lease_path, lease_payload)

            code, doctor, stderr = self.run_json(
                ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
            )
            self.assertEqual(0, code, f"{stderr}\n{doctor}")
            self.assertEqual("fresh", doctor["lease"]["liveness"])
            self.assertEqual("physical_execution", doctor["lease"]["liveness_source"])
            self.assertFalse(doctor["orphan_candidate"])
            self.assertTrue(doctor["lease"]["physical_execution"]["live"])

            code, contender, stderr = self.run_json(
                [
                    "continuation",
                    "coordination",
                    "attempt",
                    str(self.root),
                    "--task-id",
                    "WS900",
                    "--runner-id",
                    "runner-b",
                    "--objective-summary",
                    "Verify that a live physical process prevents false recovery.",
                ]
            )
            self.assertEqual(0, code, f"{stderr}\n{contender}")
            self.assertEqual("live_owner_observed", contender["status"])
            self.assertFalse(contender["challenge_required"])

            sleeper.terminate()
            sleeper.wait(timeout=5)
            code, terminal_doctor, stderr = self.run_json(
                ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
            )
            self.assertEqual(0, code, f"{stderr}\n{terminal_doctor}")
            self.assertEqual("stale", terminal_doctor["lease"]["liveness"])
            self.assertEqual("heartbeat", terminal_doctor["lease"]["liveness_source"])
            self.assertTrue(terminal_doctor["orphan_candidate"])
            probes = terminal_doctor["lease"]["physical_execution"]["probes"]
            self.assertEqual("terminal", probes[0]["status"])
        finally:
            if sleeper.poll() is None:
                sleeper.terminate()
                sleeper.wait(timeout=5)

    def test_unverifiable_or_expired_physical_execution_never_resurrects_owner(self) -> None:
        initialized, claim = self.init_and_claim()
        state_dir = Path(str(initialized["state_dir"]))
        lease = claim["lease"]
        self.assertIsInstance(lease, dict)
        owner = ["--lease-id", str(lease["lease_id"]), *self.owner_flags(claim)]
        code, prepared, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS900",
                *owner,
                "--key",
                "physical-process-unverifiable",
                "--kind",
                continuation_execution.PHYSICAL_EXECUTION_EFFECT_KIND,
                "--external-id",
                "local-process-v1:321:" + ("a" * 43),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prepared}")
        code, active, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "update",
                str(self.root),
                "--task-id",
                "WS900",
                *owner,
                "--key",
                "physical-process-unverifiable",
                "--status",
                "active",
                "--milestone",
                "process-running",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{active}")

        lease_path = state_dir / "lease.json"
        lease_payload = json.loads(lease_path.read_text(encoding="utf-8"))
        now = continuation._now()
        lease_payload["issued_at"] = continuation._iso(now - timedelta(minutes=60))
        lease_payload["last_renew_at"] = continuation._iso(now - timedelta(minutes=60))
        lease_payload["last_heartbeat_at"] = continuation._iso(now - timedelta(minutes=31))
        lease_payload["expires_at"] = continuation._iso(now + timedelta(minutes=60))
        continuation._write_json(lease_path, lease_payload)
        with patch.object(
            continuation_execution,
            "process_start_marker",
            return_value=("unverifiable", None, "process_access_denied"),
        ):
            code, doctor, stderr = self.run_json(
                ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
            )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertEqual("stale", doctor["lease"]["liveness"])
        self.assertEqual("heartbeat", doctor["lease"]["liveness_source"])
        self.assertTrue(doctor["orphan_candidate"])
        self.assertFalse(doctor["lease"]["physical_execution"]["live"])
        self.assertEqual(
            "unverifiable",
            doctor["lease"]["physical_execution"]["probes"][0]["status"],
        )

        lease_payload = json.loads(lease_path.read_text(encoding="utf-8"))
        lease_payload["expires_at"] = continuation._iso(now - timedelta(seconds=1))
        continuation._write_json(lease_path, lease_payload)
        with patch.object(
            continuation_execution,
            "process_start_marker",
            return_value=("live", "marker-a", "process_identity_verified"),
        ):
            code, expired_doctor, stderr = self.run_json(
                ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
            )
        self.assertEqual(0, code, f"{stderr}\n{expired_doctor}")
        self.assertEqual("expired", expired_doctor["lease"]["liveness"])
        self.assertEqual("lease_expiry", expired_doctor["lease"]["liveness_source"])
        self.assertFalse(expired_doctor["orphan_candidate"])


if __name__ == "__main__":
    unittest.main()
