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
from ai_context_framework.observability import usage_log_path


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

    def owner_flags(self, claim: dict[str, object]) -> list[str]:
        lease = claim["lease"]
        self.assertIsInstance(lease, dict)
        return [
            "--generation",
            str(lease["generation"]),
            "--fence-token",
            str(claim["fence_token"]),
        ]

    def test_init_and_doctor_use_user_global_state_without_dirtying_repo(self) -> None:
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
        self.assertTrue((state_dir / "control.json").is_file())
        self.assertTrue((state_dir / "state.json").is_file())
        self.assertFalse((state_dir / "rounds.json").exists())
        self.assertFalse((state_dir / "effects.json").exists())
        self.assertEqual("", self._git("status", "--porcelain").stdout)

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertTrue(doctor["ok"])
        self.assertTrue(doctor["can_claim"])
        self.assertEqual("ready", doctor["state"]["status"])
        self.assertEqual("local_first", doctor["control"]["history_policy"])

        events = [
            json.loads(line)
            for line in usage_log_path(self.root).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertTrue(any(event.get("command") == "continuation init" for event in events))
        self.assertTrue(any(event.get("command") == "continuation doctor" for event in events))

    def test_wrong_task_id_reports_available_continuation_tasks(self) -> None:
        self.init_task()
        code, payload, _ = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS999"]
        )
        self.assertEqual(2, code)
        self.assertEqual("continuation_task_not_found", payload["error_code"])
        self.assertEqual("WS999", payload["details"]["requested_task_id"])
        self.assertEqual(["WS900"], payload["details"]["available_tasks"])
        self.assertTrue(payload["next_actions"])

    def test_issue_events_are_structured_and_aggregated_across_projects(self) -> None:
        self.init_task()
        for evidence in ("git:abc", "git:def"):
            code, payload, stderr = self.run_json(
                [
                    "continuation",
                    "issue",
                    str(self.root),
                    "--task-id",
                    "WS900",
                    "--category",
                    "recovery",
                    "--severity",
                    "high",
                    "--text",
                    "Expired round recovery needs explicit operator evidence.",
                    "--evidence-ref",
                    evidence,
                    "--related-command",
                    "continuation claim",
                    "--runner-id",
                    "scheduled-test",
                ]
            )
            self.assertEqual(0, code, f"{stderr}\n{payload}")
            self.assertEqual("issue_recorded", payload["status"])

        code, issues, stderr = self.run_json(
            ["log", "issues", "--all-projects", "--limit", "20"]
        )
        self.assertEqual(0, code, f"{stderr}\n{issues}")
        self.assertEqual(1, issues["issue_count"])
        self.assertEqual(2, issues["occurrence_count"])
        row = issues["issues"][0]
        self.assertEqual(2, row["count"])
        self.assertEqual("open", row["status"])
        self.assertEqual("high", row["severity"])
        self.assertEqual("recovery", row["category"])
        self.assertEqual(["WS900"], row["tasks"])
        self.assertEqual(["git:abc", "git:def"], row["evidence_refs"])

        code, resolved, stderr = self.run_json(
            [
                "continuation",
                "issue",
                str(self.root),
                "--task-id",
                "WS900",
                "--text",
                "Fixed by the validated recovery protocol.",
                "--resolve-fingerprint",
                str(row["fingerprint"]),
                "--evidence-ref",
                "git:fix",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{resolved}")
        self.assertEqual("issue_resolved", resolved["status"])

        code, issues, stderr = self.run_json(["log", "issues", "--all-projects", "--limit", "20"])
        self.assertEqual(0, code, f"{stderr}\n{issues}")
        row = issues["issues"][0]
        self.assertEqual("resolved", row["status"])
        self.assertEqual("Fixed by the validated recovery protocol.", row["resolution_text"])
        self.assertEqual(["git:fix"], row["resolution_evidence_refs"])
        code, open_only, stderr = self.run_json(
            ["log", "issues", "--all-projects", "--open-only", "--limit", "20"]
        )
        self.assertEqual(0, code, f"{stderr}\n{open_only}")
        self.assertEqual(0, open_only["issue_count"])

        code, reopened, stderr = self.run_json(
            [
                "continuation",
                "issue",
                str(self.root),
                "--task-id",
                "WS900",
                "--category",
                "recovery",
                "--severity",
                "high",
                "--text",
                "Expired round recovery needs explicit operator evidence.",
                "--evidence-ref",
                "git:ghi",
                "--related-command",
                "continuation claim",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reopened}")
        code, issues, stderr = self.run_json(["log", "issues", "--all-projects", "--limit", "20"])
        self.assertEqual(0, code, f"{stderr}\n{issues}")
        row = issues["issues"][0]
        self.assertEqual("open", row["status"])
        self.assertEqual(3, row["count"])
        self.assertTrue(row["reopened_at"])

        code, prompt, stderr = self.run_json(
            ["continuation", "prompt", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{prompt}")
        self.assertIn("acf continuation issue", prompt["prompt"])
        self.assertIn("Do not record normal active-lease no-ops", prompt["prompt"])

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
                *self.owner_flags(first),
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
                *self.owner_flags(first),
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
                *self.owner_flags(first),
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

    def test_claim_creates_fenced_owner_and_heartbeat_refreshes_liveness(self) -> None:
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
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
        self.assertEqual(1, claim["generation"])
        self.assertTrue(str(claim["fence_token"]))
        self.assertRegex(str(claim["fence_token"]), r"^[0-9a-f]{64}$")
        lease_id = str(claim["lease"]["lease_id"])

        persisted = json.loads((state_dir / "lease.json").read_text(encoding="utf-8"))
        self.assertEqual(1, persisted["generation"])
        self.assertIn("fence_token_hash", persisted)
        self.assertNotIn("fence_token", persisted)
        self.assertNotIn("fence_token_hash", claim["lease"])
        expires_before_heartbeat = persisted["expires_at"]

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertEqual("fresh", doctor["lease"]["liveness"])
        self.assertFalse(doctor["orphan_candidate"])

        code, rejected, _ = self.run_json(
            [
                "continuation",
                "assert-owner",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                "--generation",
                "1",
                "--fence-token",
                "wrong-token",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("fence_token_mismatch", rejected["error_code"])

        code, missing_generation, _ = self.run_json(
            [
                "continuation",
                "assert-owner",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                "--fence-token",
                str(claim["fence_token"]),
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("fence_generation_required", missing_generation["error_code"])

        code, missing_token, _ = self.run_json(
            [
                "continuation",
                "assert-owner",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                "--generation",
                "1",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("fence_token_required", missing_token["error_code"])

        code, owner, stderr = self.run_json(
            [
                "continuation",
                "assert-owner",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{owner}")
        self.assertEqual("owner_confirmed", owner["status"])

        code, heartbeat, stderr = self.run_json(
            [
                "continuation",
                "heartbeat",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{heartbeat}")
        self.assertEqual("heartbeat_recorded", heartbeat["status"])
        persisted_after_heartbeat = json.loads(
            (state_dir / "lease.json").read_text(encoding="utf-8")
        )
        self.assertEqual(expires_before_heartbeat, persisted_after_heartbeat["expires_at"])

        code, wrong_generation, _ = self.run_json(
            [
                "continuation",
                "assert-owner",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                "--generation",
                "2",
                "--fence-token",
                str(claim["fence_token"]),
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("fence_generation_mismatch", wrong_generation["error_code"])

    def test_clean_release_preserves_checkpointed_waiting_external_status(self) -> None:
        """WS079 regression: release must not silently convert an external wait to ready."""
        self.init_task()
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
        lease_id = str(claim["lease"]["lease_id"])

        code, checkpoint, stderr = self.run_json(
            [
                "continuation",
                "checkpoint",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
                "--status",
                "waiting_external",
                "--next-action",
                "Wait for the existing external job identity.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{checkpoint}")
        self.assertEqual("waiting_external", checkpoint["state"]["status"])

        code, released, stderr = self.run_json(
            [
                "continuation",
                "release",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{released}")
        self.assertEqual("waiting_external", released["state"]["status"])
        self.assertEqual(
            "Wait for the existing external job identity.",
            released["state"]["next_action"],
        )

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
                *self.owner_flags(claim),
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
                *self.owner_flags(claim),
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
                *self.owner_flags(claim),
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
        self.assertEqual(int(claim["generation"]) + 1, recovered["generation"])

        for command in ("assert-owner", "heartbeat", "renew", "checkpoint", "release"):
            with self.subTest(command=command):
                code, fenced, _ = self.run_json(
                    [
                        "continuation",
                        command,
                        str(self.root),
                        "--task-id",
                        "WS900",
                        "--lease-id",
                        str(claim["lease"]["lease_id"]),
                        *self.owner_flags(claim),
                    ]
                )
                self.assertEqual(3, code)
                self.assertEqual("lease_mismatch", fenced["error_code"])

        code, doctor_after_fenced_calls, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor_after_fenced_calls}")
        self.assertEqual("active", doctor_after_fenced_calls["lease"]["state"])
        self.assertEqual(
            recovered["lease"]["lease_id"],
            doctor_after_fenced_calls["lease"]["lease"]["lease_id"],
        )

        code, fenced_progress, _ = self.run_json(
            [
                "continuation",
                "progress",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
                "--phase",
                "executing",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("lease_mismatch", fenced_progress["error_code"])

        code, fenced_effect, _ = self.run_json(
            [
                "continuation",
                "effect",
                "update",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
                "--key",
                "job-a",
                "--status",
                "active",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("lease_mismatch", fenced_effect["error_code"])

    def test_round_progress_and_effect_journal_are_bounded_write_ahead_records(self) -> None:
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
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
        self.assertEqual("claimed", claim["round"]["phase"])
        self.assertTrue((state_dir / "rounds.json").is_file())
        self.assertFalse((state_dir / "effects.json").exists())

        owner = [
            "--lease-id",
            str(claim["lease"]["lease_id"]),
            *self.owner_flags(claim),
        ]
        code, progress, stderr = self.run_json(
            [
                "continuation",
                "progress",
                str(self.root),
                "--task-id",
                "WS900",
                *owner,
                "--phase",
                "executing",
                "--milestone",
                "wave-1",
                "--evidence-ref",
                "artifact:wave-plan.json",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{progress}")
        self.assertEqual("executing", progress["round"]["phase"])
        self.assertEqual("wave-1", progress["round"]["milestone"])

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
                "campaign:wave-1",
                "--kind",
                "external-job",
                "--evidence-ref",
                "plan:campaign-wave-1",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prepared}")
        self.assertTrue(prepared["created"])
        self.assertEqual("prepared", prepared["effect"]["status"])
        first_effect_id = prepared["effect"]["effect_id"]
        self.assertEqual(64, len(str(first_effect_id)))

        code, duplicate, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS900",
                *owner,
                "--key",
                "campaign:wave-1",
                "--kind",
                "external-job",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{duplicate}")
        self.assertFalse(duplicate["created"])
        self.assertEqual(first_effect_id, duplicate["effect"]["effect_id"])

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
                "campaign:wave-1",
                "--status",
                "active",
                "--external-id",
                "runtime-job-123",
                "--milestone",
                "submitted",
                "--evidence-ref",
                "authority:runtime-job-123",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{active}")
        self.assertEqual("runtime-job-123", active["effect"]["external_id"])
        self.assertEqual("active", active["effect"]["status"])

        code, completed, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "update",
                str(self.root),
                "--task-id",
                "WS900",
                *owner,
                "--key",
                "campaign:wave-1",
                "--status",
                "completed",
                "--milestone",
                "collected",
                "--evidence-ref",
                "artifact:wave-1-result.json",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{completed}")
        self.assertEqual("completed", completed["effect"]["status"])

        code, listed, stderr = self.run_json(
            ["continuation", "effect", "list", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{listed}")
        self.assertEqual(1, listed["summary"]["total"])
        self.assertEqual(["campaign:wave-1"], listed["summary"]["terminal"])
        self.assertEqual([], listed["summary"]["unresolved"])

        persisted = (state_dir / "effects.json").read_text(encoding="utf-8")
        self.assertNotIn(str(claim["fence_token"]), persisted)
        self.assertNotIn("raw_output", persisted)
        self.assertNotIn("transcript", persisted)

        code, released, stderr = self.run_json(
            [
                "continuation",
                "release",
                str(self.root),
                "--task-id",
                "WS900",
                *owner,
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{released}")
        self.assertEqual("released", released["round"]["phase"])
        rounds = json.loads((state_dir / "rounds.json").read_text(encoding="utf-8"))
        self.assertEqual("released", rounds["rounds"][-1]["phase"])

    def test_expired_running_round_with_effects_requires_reconciliation_before_reclaim(self) -> None:
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
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
        code, prepared, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
                "--key",
                "deployment:prod",
                "--kind",
                "external-write",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prepared}")

        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        lease["issued_at"] = continuation._iso(continuation._now() - timedelta(minutes=20))
        lease["expires_at"] = continuation._iso(continuation._now() - timedelta(minutes=1))
        continuation._write_json(lease_path, lease)

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertFalse(doctor["can_claim"])
        self.assertFalse(doctor["recoverable_expired_round"])
        self.assertTrue(doctor["effect_reconciliation_required"])
        self.assertIn("effect_reconciliation_required", doctor["blocked_reasons"])
        self.assertEqual(1, doctor["effect_journal"]["summary"]["total"])

        code, blocked, _ = self.run_json(
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
        self.assertEqual("continuation_reconciliation_required", blocked["error_code"])
        self.assertEqual(1, blocked["details"]["effect_summary"]["total"])

    def test_malformed_effect_journal_fails_doctor_closed(self) -> None:
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
        (state_dir / "effects.json").write_text(
            json.dumps(
                {
                    "schema_version": "acf.continuation.effect-journal.v1",
                    "task_id": "WS900",
                    "effects": [],
                    "raw_output": "forbidden",
                }
            ),
            encoding="utf-8",
        )
        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(2, code, f"{stderr}\n{doctor}")
        self.assertFalse(doctor["ok"])
        self.assertFalse(doctor["can_claim"])
        self.assertEqual("invalid", doctor["effect_journal"]["state"])
        self.assertIn("effect journal is malformed or identity-mismatched", doctor["blocked_reasons"])

    def test_reconcile_never_steals_a_fresh_active_owner(self) -> None:
        self.init_task()
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

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS900",
                "--owner-ended",
                "--evidence-ref",
                "scheduler:runner-a-ended",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertFalse(reconciled["eligible_for_recover"])
        self.assertEqual("blocked", reconciled["decision"])
        self.assertIn("active_owner_live", reconciled["reasons"])

    def test_stale_fenced_owner_reconcile_recover_fences_resurrection(self) -> None:
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
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
        lease_id = str(claim["lease"]["lease_id"])

        code, prepared, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
                "--key",
                "campaign-wave-a",
                "--kind",
                "campaign",
                "--external-id",
                "campaign-001",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prepared}")
        code, completed, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "update",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
                "--key",
                "campaign-wave-a",
                "--status",
                "completed",
                "--milestone",
                "aggregated",
                "--evidence-ref",
                "artifact:aggregate.json",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{completed}")

        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        lease["issued_at"] = continuation._iso(
            continuation._now() - timedelta(minutes=60)
        )
        lease["last_heartbeat_at"] = continuation._iso(
            continuation._now() - timedelta(minutes=31)
        )
        continuation._write_json(lease_path, lease)

        code, blocked, stderr = self.run_json(
            ["continuation", "reconcile", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{blocked}")
        self.assertIn("owner_end_not_proven", blocked["reasons"])

        reconcile_args = [
            "continuation",
            "reconcile",
            str(self.root),
            "--task-id",
            "WS900",
            "--owner-ended",
            "--evidence-ref",
            "scheduler:runner-a-ended",
            "--reason",
            "Scheduler reports the stale runner has ended and the recorded effect is terminal.",
            "--record",
        ]
        code, reconciled, stderr = self.run_json(reconcile_args)
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertTrue(reconciled["eligible_for_recover"])
        reconcile_id = str(reconciled["receipt"]["receipt_id"])

        # A resurrected old owner invalidates the previously recorded observation.
        code, heartbeat, stderr = self.run_json(
            [
                "continuation",
                "heartbeat",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{heartbeat}")
        code, stale_receipt, _ = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS900",
                "--reconcile-id",
                reconcile_id,
                "--runner-id",
                "runner-b",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("reconciliation_stale", stale_receipt["error_code"])

        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        lease["last_heartbeat_at"] = continuation._iso(
            continuation._now() - timedelta(minutes=31)
        )
        continuation._write_json(lease_path, lease)
        code, reconciled, stderr = self.run_json(reconcile_args)
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        reconcile_id = str(reconciled["receipt"]["receipt_id"])

        code, recovered, stderr = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS900",
                "--reconcile-id",
                reconcile_id,
                "--runner-id",
                "runner-b",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{recovered}")
        self.assertEqual(2, recovered["generation"])
        self.assertNotEqual(lease_id, recovered["lease"]["lease_id"])

        for command in ("assert-owner", "heartbeat", "renew", "checkpoint", "release"):
            with self.subTest(command=command):
                code, fenced, _ = self.run_json(
                    [
                        "continuation",
                        command,
                        str(self.root),
                        "--task-id",
                        "WS900",
                        "--lease-id",
                        lease_id,
                        *self.owner_flags(claim),
                    ]
                )
                self.assertEqual(3, code)
                self.assertEqual("lease_mismatch", fenced["error_code"])

        code, effects, stderr = self.run_json(
            ["continuation", "effect", "list", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{effects}")
        self.assertEqual("completed", effects["effects"][0]["status"])
        self.assertEqual(["campaign-wave-a"], effects["summary"]["terminal"])

    def test_reconcile_blocks_unresolved_effects_and_blocked_receipt_cannot_recover(self) -> None:
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
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
        lease_id = str(claim["lease"]["lease_id"])
        code, prepared, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
                "--key",
                "external-write",
                "--kind",
                "deployment",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prepared}")
        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        lease["issued_at"] = continuation._iso(
            continuation._now() - timedelta(minutes=60)
        )
        lease["last_heartbeat_at"] = continuation._iso(
            continuation._now() - timedelta(minutes=31)
        )
        continuation._write_json(lease_path, lease)

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS900",
                "--owner-ended",
                "--evidence-ref",
                "scheduler:runner-a-ended",
                "--reason",
                "Runner ended but external effect outcome is unresolved.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertFalse(reconciled["eligible_for_recover"])
        self.assertIn("unresolved_effects", reconciled["reasons"])

        code, denied, _ = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS900",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "runner-b",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("recovery_not_authorized", denied["error_code"])

    def test_legacy_unknown_owner_with_advanced_head_requires_explicit_head_acceptance(self) -> None:
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS900",
                "--runner-id",
                "legacy-runner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")

        control_path = state_dir / "control.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control.pop("generation", None)
        continuation._write_json(control_path, control)
        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        for field in ("generation", "fence_token_hash", "last_heartbeat_at", "last_renew_at"):
            lease.pop(field, None)
        continuation._write_json(lease_path, lease)
        (state_dir / "rounds.json").unlink(missing_ok=True)
        (state_dir / "effects.json").unlink(missing_ok=True)

        (self.root / "recovered-work.txt").write_text("durable work before crash\n", encoding="utf-8")
        self._git("add", "recovered-work.txt")
        self._git("commit", "-m", "test: durable work before crash")
        current_head = self._git("rev-parse", "HEAD").stdout.strip()

        base_reconcile = [
            "continuation",
            "reconcile",
            str(self.root),
            "--task-id",
            "WS900",
            "--owner-ended",
            "--evidence-ref",
            "scheduler:legacy-runner-ended",
        ]
        code, blocked, stderr = self.run_json(base_reconcile)
        self.assertEqual(0, code, f"{stderr}\n{blocked}")
        self.assertIn("head_change_unaccepted", blocked["reasons"])

        code, reconciled, stderr = self.run_json(
            [
                *base_reconcile,
                "--accept-head",
                current_head,
                "--reason",
                "Operator verified the old runner ended and the advanced HEAD is the recovered durable checkpoint.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertTrue(reconciled["eligible_for_recover"])
        self.assertEqual("legacy_unknown", reconciled["observation"]["liveness"])

        code, recovered, stderr = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS900",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "runner-b",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{recovered}")
        self.assertEqual(1, recovered["generation"])
        self.assertEqual(current_head, recovered["lease"]["head"])
        self.assertEqual(lease["lease_id"], recovered["recovery"]["previous_lease_id"])
        self.assertIsNone(recovered["recovery"]["previous_generation"])

    def test_legacy_active_lease_without_fencing_metadata_remains_readable(self) -> None:
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS900",
                "--runner-id",
                "legacy-runner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")

        control_path = state_dir / "control.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control.pop("generation", None)
        continuation._write_json(control_path, control)

        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        for field in ("generation", "fence_token_hash", "last_heartbeat_at", "last_renew_at"):
            lease.pop(field, None)
        continuation._write_json(lease_path, lease)
        (state_dir / "rounds.json").unlink(missing_ok=True)
        (state_dir / "effects.json").unlink(missing_ok=True)

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertEqual("legacy_unknown", doctor["lease"]["liveness"])
        self.assertEqual("absent", doctor["round_journal"]["state"])
        self.assertEqual("absent", doctor["effect_journal"]["state"])
        self.assertFalse(doctor["orphan_candidate"])
        self.assertFalse(doctor["can_claim"])

        code, renewed, stderr = self.run_json(
            [
                "continuation",
                "renew",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                str(lease["lease_id"]),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{renewed}")
        self.assertEqual("renewed", renewed["status"])

        code, doctor_after_renew, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor_after_renew}")
        self.assertEqual("fresh", doctor_after_renew["lease"]["liveness"])

    def test_active_lease_with_stale_heartbeat_is_exposed_as_orphan_candidate(self) -> None:
        """WS086 regression: TTL-active must not be treated as proof of runner liveness."""
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
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
        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        lease["generation"] = 1
        lease["last_heartbeat_at"] = continuation._iso(
            continuation._now() - timedelta(minutes=31)
        )
        lease["issued_at"] = continuation._iso(
            continuation._now() - timedelta(minutes=60)
        )
        lease["expires_at"] = continuation._iso(
            continuation._now() + timedelta(minutes=60)
        )
        continuation._write_json(lease_path, lease)

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertFalse(doctor["can_claim"])
        self.assertTrue(doctor["orphan_candidate"])
        self.assertEqual("stale", doctor["lease"]["liveness"])
        self.assertIn("orphan_candidate", doctor["blocked_reasons"])

    def test_expired_running_lease_with_advanced_head_requires_reconciliation(self) -> None:
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
        self.assertEqual(0, code, claim)
        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))

        (self.root / "completed.txt").write_text("completed before crash\n", encoding="utf-8")
        self._git("add", "completed.txt")
        self._git("commit", "-m", "test: completed before crash")

        lease["issued_at"] = continuation._iso(continuation._now() - timedelta(minutes=20))
        lease["expires_at"] = continuation._iso(continuation._now() - timedelta(minutes=1))
        continuation._write_json(lease_path, lease)

        code, doctor, _ = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code)
        self.assertFalse(doctor["recoverable_expired_round"])
        self.assertTrue(doctor["expired_round_head_changed"])
        self.assertFalse(doctor["can_claim"])
        self.assertIn("expired_round_head_changed", doctor["blocked_reasons"])

        code, blocked, _ = self.run_json(
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
        self.assertEqual("continuation_reconciliation_required", blocked["error_code"])
        self.assertEqual(lease["head"], blocked["details"]["lease_head"])
        self.assertEqual(self._git("rev-parse", "HEAD").stdout.strip(), blocked["details"]["current_head"])

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
        self.assertIn("acf continuation assert-owner", prompt)
        self.assertIn("heartbeat", prompt)
        self.assertIn("acf continuation progress", prompt)
        self.assertIn("acf continuation effect prepare", prompt)
        self.assertIn("acf continuation effect update", prompt)
        self.assertIn("acf continuation effect list", prompt)
        self.assertIn("acf continuation reconcile", prompt)
        self.assertIn("acf continuation recover", prompt)
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
