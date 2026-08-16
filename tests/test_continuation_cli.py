from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from pathlib import Path

import acf
from ai_context_framework.commands import continuation


class ContinuationCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._home = tempfile.TemporaryDirectory()
        self._repo = tempfile.TemporaryDirectory()
        self.previous_home = os.environ.get("ACF_HOME")
        os.environ["ACF_HOME"] = self._home.name
        self.root = Path(self._repo.name).resolve()
        self._git("init", "-b", "main")
        self._git("config", "user.name", "ACF Continuation Test")
        self._git("config", "user.email", "acf-continuation@example.invalid")
        (self.root / "README.md").write_text("continuation\n", encoding="utf-8")
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

    def run_json(self, args: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = acf.main([*args, "--json"])
        raw = stdout.getvalue().strip()
        self.assertTrue(raw, stderr.getvalue())
        return code, json.loads(raw), stderr.getvalue()

    def init_task(self, task_id: str = "WS900") -> dict[str, object]:
        code, payload, stderr = self.run_json(
            [
                "continuation",
                "init",
                str(self.root),
                "--task-id",
                task_id,
                "--title",
                "Continuation test",
                "--objective",
                "Validate model-agnostic bounded continuation.",
                "--next-action",
                "Run gate one.",
                "--plan-ref",
                "docs/ai/active/Task_Plan.md",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{payload}")
        self.assertTrue(payload["ok"])
        return payload

    def test_init_and_doctor_use_user_global_state_without_dirtying_repo(self) -> None:
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
        self.assertTrue((state_dir / "control.json").is_file())
        self.assertTrue((state_dir / "state.json").is_file())
        self.assertEqual("", self._git("status", "--porcelain").stdout)

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertTrue(doctor["ok"])
        self.assertTrue(doctor["can_claim"])
        self.assertEqual("ready", doctor["state"]["status"])
        self.assertEqual("local_first", doctor["control"]["history_policy"])

    def test_claim_renew_checkpoint_release_and_collision(self) -> None:
        self.init_task()
        code, first, stderr = self.run_json(
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
        self.assertEqual(0, code, f"{stderr}\n{first}")
        lease_id = str(first["lease"]["lease_id"])

        code, busy, _ = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS900",
                "--runner-id",
                "runner-b",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("continuation_busy", busy["error_code"])

        code, renewed, stderr = self.run_json(
            [
                "continuation",
                "renew",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
            ]
        )
        self.assertEqual(0, code, stderr)
        self.assertEqual("renewed", renewed["status"])

        code, checkpoint, stderr = self.run_json(
            [
                "continuation",
                "checkpoint",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                "--stage",
                "gate-1",
                "--next-action",
                "Run gate two.",
                "--completed",
                "Gate one completed.",
                "--verification",
                "Unit test passed.",
            ]
        )
        self.assertEqual(0, code, stderr)
        self.assertEqual("gate-1", checkpoint["state"]["stage"])

        code, released, stderr = self.run_json(
            [
                "continuation",
                "release",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                "--next-action",
                "Run gate two.",
            ]
        )
        self.assertEqual(0, code, stderr)
        self.assertEqual("released", released["status"])

        code, doctor, _ = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, doctor)
        self.assertTrue(doctor["can_claim"])
        self.assertEqual("absent", doctor["lease"]["state"])

    def test_dirty_release_fails_closed_into_reconciling(self) -> None:
        self.init_task()
        code, claim, _ = self.run_json(
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
        self.assertEqual(0, code, claim)
        lease_id = str(claim["lease"]["lease_id"])
        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        code, release, _ = self.run_json(
            [
                "continuation",
                "release",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
            ]
        )
        self.assertEqual(2, code)
        self.assertEqual("released_to_reconciling", release["status"])
        self.assertEqual("reconciling", release["state"]["status"])

    def test_pause_during_active_round_blocks_renew_and_release_finishes_paused(self) -> None:
        self.init_task()
        code, claim, _ = self.run_json(
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
        self.assertEqual(0, code, claim)
        lease_id = str(claim["lease"]["lease_id"])
        code, pause, _ = self.run_json(
            [
                "continuation",
                "pause",
                str(self.root),
                "--task-id",
                "WS900",
                "--reason",
                "Human review",
            ]
        )
        self.assertEqual(0, code)
        self.assertEqual("pause_requested", pause["status"])

        code, renew, _ = self.run_json(
            [
                "continuation",
                "renew",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("continuation_paused", renew["error_code"])

        code, release, _ = self.run_json(
            [
                "continuation",
                "release",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
            ]
        )
        self.assertEqual(2, code)
        self.assertEqual("released_to_paused", release["status"])

        code, resume, stderr = self.run_json(
            [
                "continuation",
                "resume",
                str(self.root),
                "--task-id",
                "WS900",
                "--next-action",
                "Continue approved gate.",
            ]
        )
        self.assertEqual(0, code, stderr)
        self.assertEqual("ready", resume["status"])

    def test_expired_running_lease_can_be_recovered_from_clean_checkpoint(self) -> None:
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
        code, claim, _ = self.run_json(
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
        self.assertEqual(0, code)
        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        lease["issued_at"] = continuation._iso(continuation._now() - timedelta(minutes=20))
        lease["expires_at"] = continuation._iso(continuation._now() - timedelta(minutes=1))
        continuation._write_json(lease_path, lease)

        code, doctor, _ = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code)
        self.assertTrue(doctor["recoverable_expired_round"])
        self.assertTrue(doctor["can_claim"])

        code, recovered, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS900",
                "--runner-id",
                "runner-b",
            ]
        )
        self.assertEqual(0, code, stderr)
        self.assertNotEqual(claim["lease"]["lease_id"], recovered["lease"]["lease_id"])

    def test_prompt_is_local_first_and_contains_full_round_protocol(self) -> None:
        self.init_task()
        code, payload, stderr = self.run_json(
            ["continuation", "prompt", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, stderr)
        prompt = str(payload["prompt"])
        self.assertIn("Do not reconstruct task state from chat history", prompt)
        self.assertIn("acf continuation doctor", prompt)
        self.assertIn("acf continuation claim", prompt)
        self.assertIn("acf continuation renew", prompt)
        self.assertIn("acf continuation release", prompt)

    def test_state_rejects_raw_history_fields(self) -> None:
        payload = {
            "schema_version": continuation.STATE_SCHEMA,
            "task_id": "WS900",
            "objective": "test",
            "status": "ready",
            "stage": "gate",
            "next_action": "next",
            "updated_at": continuation._iso(),
            "completed": [],
            "constraints": [],
            "evidence_refs": [],
            "open_questions": [],
            "plan_refs": [],
            "verification": [],
            "transcript": "must not persist",
        }
        with self.assertRaises(continuation.ContinuationError):
            continuation._validate_state(payload)

        nested = dict(payload)
        nested.pop("transcript")
        nested["evidence_refs"] = [{"path": "result.json", "tool_output": "raw"}]
        with self.assertRaises(continuation.ContinuationError):
            continuation._validate_state(nested)


if __name__ == "__main__":
    unittest.main()
