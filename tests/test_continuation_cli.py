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
from ai_context_framework import continuation_inventory, continuation_workspace
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

    def test_list_reports_acf_home_identity_schema_and_timing_contract(self) -> None:
        init = self.init_task()
        code, payload, stderr = self.run_json(
            ["continuation", "list", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{payload}")
        self.assertEqual("current_project", payload["scope"])
        self.assertEqual(str(Path(self._home.name).resolve()), payload["acf_home"])
        self.assertEqual(1, payload["task_count"])
        task = payload["tasks"][0]
        self.assertEqual("WS900", task["task_id"])
        self.assertIsNone(task["workstream_id"])
        self.assertEqual(str(self.root), task["workspace_root"])
        self.assertEqual("standard", task["timing_profile"])
        self.assertEqual("current", task["compatibility"])
        self.assertFalse(task["migration_required"])
        self.assertEqual(
            continuation_workspace.WORKSPACE_SCHEMA,
            task["schemas"]["workspace.json"]["schema_version"],
        )
        self.assertEqual(
            [continuation_workspace.WORKSPACE_SCHEMA],
            payload["schema_contract"]["workspace.json"]["current"],
        )

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertEqual("current", doctor["state_compatibility"]["compatibility"])
        self.assertFalse(doctor["state_compatibility"]["migration_required"])
        self.assertEqual(str(init["state_dir"]), str(task["state_dir"]))

    def test_list_all_projects_discovers_namespaced_tasks(self) -> None:
        self.init_task("WS900")
        with tempfile.TemporaryDirectory() as tmp:
            second = Path(tmp).resolve()
            for args in (
                ("init", "-b", "main"),
                ("config", "user.name", "ACF Continuation Test"),
                ("config", "user.email", "acf-continuation@example.invalid"),
            ):
                completed = subprocess.run(
                    ["git", *args],
                    cwd=second,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
            (second / "README.md").write_text("second\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=second, check=True)
            subprocess.run(["git", "commit", "-m", "test: init"], cwd=second, check=True)
            code, init, stderr = self.run_json(
                [
                    "continuation",
                    "init",
                    str(second),
                    "--task-id",
                    "TASK-B",
                    "--title",
                    "Second continuation",
                    "--objective",
                    "Inventory namespace coverage.",
                ]
            )
            self.assertEqual(0, code, f"{stderr}\n{init}")

            code, payload, stderr = self.run_json(["continuation", "list", "--all-projects"])
            self.assertEqual(0, code, f"{stderr}\n{payload}")
            identities = {
                (item["task_id"], item["workspace_root"])
                for item in payload["tasks"]
            }
            self.assertIn(("WS900", str(self.root)), identities)
            self.assertIn(("TASK-B", str(second)), identities)
            self.assertGreaterEqual(payload["project_count"], 2)

    def test_migrate_upgrades_legacy_workspace_with_receipt_and_preserves_history(self) -> None:
        init = self.init_task()
        code, claim, stderr = self.run_json(
            ["continuation", "claim", str(self.root), "--task-id", "WS900", "--runner-id", "runner-a"]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, released, stderr = self.run_json(
            [
                "continuation",
                "release",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{released}")
        state_dir = Path(str(init["state_dir"]))
        workspace_path = state_dir / "workspace.json"
        workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
        workspace["schema_version"] = continuation_workspace.LEGACY_WORKSPACE_SCHEMA_V2
        workspace.pop("adoption_receipt", None)
        workspace_path.write_text(
            json.dumps(workspace, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        preserved_names = ["control.json", "state.json", "rounds.json", "last_run.json"]
        preserved_before = {
            name: (state_dir / name).read_bytes()
            for name in preserved_names
            if (state_dir / name).exists()
        }

        code, listed, stderr = self.run_json(
            ["continuation", "list", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{listed}")
        task = listed["tasks"][0]
        self.assertEqual("migration_available", task["compatibility"])
        self.assertEqual(["workspace.json"], task["migration_files"])

        workspace_before = workspace_path.read_bytes()
        code, planned, stderr = self.run_json(
            ["continuation", "migrate", str(self.root), "--task-id", "WS900", "--dry-run"]
        )
        self.assertEqual(0, code, f"{stderr}\n{planned}")
        self.assertEqual("migration_planned", planned["status"])
        self.assertFalse(planned["applied"])
        self.assertEqual(workspace_before, workspace_path.read_bytes())

        code, migrated, stderr = self.run_json(
            [
                "continuation",
                "migrate",
                str(self.root),
                "--task-id",
                "WS900",
                "--apply",
                "--reason",
                "test supported legacy migration",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{migrated}")
        self.assertTrue(migrated["applied"])
        current = json.loads(workspace_path.read_text(encoding="utf-8"))
        self.assertEqual(continuation_workspace.WORKSPACE_SCHEMA, current["schema_version"])
        receipt_path = Path(str(migrated["receipt_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(continuation_inventory.MIGRATION_RECEIPT_SCHEMA, receipt["schema_version"])
        self.assertEqual(continuation_workspace.LEGACY_WORKSPACE_SCHEMA_V2, receipt["changes"][0]["from_schema"])
        self.assertEqual(continuation_workspace.WORKSPACE_SCHEMA, receipt["changes"][0]["to_schema"])
        for name, before in preserved_before.items():
            self.assertEqual(before, (state_dir / name).read_bytes(), name)

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertEqual("current", doctor["state_compatibility"]["compatibility"])

    def test_migrate_refuses_active_owner_and_list_blocks_unknown_schema(self) -> None:
        init = self.init_task()
        state_dir = Path(str(init["state_dir"]))
        workspace_path = state_dir / "workspace.json"
        workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
        workspace["schema_version"] = continuation_workspace.LEGACY_WORKSPACE_SCHEMA_V2
        workspace.pop("adoption_receipt", None)
        workspace_path.write_text(
            json.dumps(workspace, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        code, claim, stderr = self.run_json(
            ["continuation", "claim", str(self.root), "--task-id", "WS900", "--runner-id", "runner-a"]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, blocked, _ = self.run_json(
            [
                "continuation",
                "migrate",
                str(self.root),
                "--task-id",
                "WS900",
                "--apply",
                "--reason",
                "must be rejected while owned",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("continuation_migration_active_owner", blocked["error_code"])

        code, released, stderr = self.run_json(
            [
                "continuation",
                "release",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{released}")
        workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
        workspace["schema_version"] = "acf.continuation.workspace.v999"
        workspace_path.write_text(
            json.dumps(workspace, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        code, listed, stderr = self.run_json(
            ["continuation", "list", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{listed}")
        self.assertEqual("blocked", listed["tasks"][0]["compatibility"])
        self.assertIn("workspace.json", listed["tasks"][0]["blocked_files"])
        code, blocked, _ = self.run_json(
            ["continuation", "migrate", str(self.root), "--task-id", "WS900", "--dry-run"]
        )
        self.assertEqual(3, code)
        self.assertEqual("continuation_migration_blocked", blocked["error_code"])

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

    def test_task_owned_wip_release_succeeds_without_git_commit(self) -> None:
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
        code, intent, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "intent",
                str(self.root),
                "--task-id",
                "WS900",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
                "--path",
                "dirty.txt",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{intent}")
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
        self.assertEqual(0, code, release)
        self.assertEqual("released", release["status"])
        self.assertEqual("ready", release["state"]["status"])
        self.assertEqual(["dirty.txt"], release["workspace"]["task_owned_paths"])
        self.assertEqual(["dirty.txt"], release["workspace"]["write_intent_paths"])
        self.assertTrue((self.root / "dirty.txt").exists())

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS900"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertTrue(doctor["can_claim"], doctor)
        self.assertNotIn("worktree_dirty", doctor["blocked_reasons"])
        self.assertEqual(["dirty.txt"], doctor["workspace"]["task_owned_paths"])

        code, inherited, stderr = self.run_json(
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
        self.assertEqual(0, code, f"{stderr}\n{inherited}")
        self.assertGreater(int(inherited["generation"]), int(claim["generation"]))
        self.assertEqual(["dirty.txt"], inherited["workspace"]["task_owned_paths"])
        self.assertEqual(["dirty.txt"], inherited["workspace"]["write_intent_paths"])

    def test_task_owned_wip_can_cross_multiple_generations_without_commit(self) -> None:
        self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "runner-1",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, intent, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "intent",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
                "--path",
                "feature.txt",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{intent}")
        (self.root / "feature.txt").write_text("generation 1\n", encoding="utf-8")

        current = claim
        for generation_number in (2, 3):
            code, released, stderr = self.run_json(
                [
                    "continuation",
                    "release",
                    str(self.root),
                    "--task-id",
                    "WS908",
                    "--lease-id",
                    str(current["lease"]["lease_id"]),
                    *self.owner_flags(current),
                ]
            )
            self.assertEqual(0, code, f"{stderr}\n{released}")
            self.assertEqual(["feature.txt"], released["workspace"]["task_owned_paths"])
            code, current, stderr = self.run_json(
                [
                    "continuation",
                    "claim",
                    str(self.root),
                    "--task-id",
                    "WS908",
                    "--runner-id",
                    f"runner-{generation_number}",
                ]
            )
            self.assertEqual(0, code, f"{stderr}\n{current}")
            self.assertEqual(["feature.txt"], current["workspace"]["task_owned_paths"])
            (self.root / "feature.txt").write_text(
                f"generation {generation_number}\n", encoding="utf-8"
            )

    def test_ownerless_task_owned_drift_blocks_next_claim_by_provenance(self) -> None:
        self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "runner-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, intent, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "intent",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
                "--path",
                "handoff.txt",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{intent}")
        (self.root / "handoff.txt").write_text("owned v1\n", encoding="utf-8")
        code, released, stderr = self.run_json(
            [
                "continuation",
                "release",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{released}")

        (self.root / "handoff.txt").write_text("unknown owner edit\n", encoding="utf-8")
        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertFalse(doctor["can_claim"])
        self.assertIn("workspace_conflict", doctor["blocked_reasons"])
        self.assertNotIn("worktree_dirty", doctor["blocked_reasons"])
        self.assertEqual(
            "task_owned_handoff_drift",
            doctor["workspace"]["conflicts"][0]["reason"],
        )

    def test_legacy_changed_paths_report_provenance_missing_not_worktree_dirty(self) -> None:
        init = self.init_task("WS908")
        state_dir = Path(str(init["state_dir"]))
        (state_dir / "workspace.json").unlink()
        (self.root / "unknown.txt").write_text("unknown provenance\n", encoding="utf-8")

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertFalse(doctor["can_claim"])
        self.assertIn("workspace_provenance_missing", doctor["blocked_reasons"])
        self.assertNotIn("worktree_dirty", doctor["blocked_reasons"])
        self.assertEqual(["unknown.txt"], doctor["workspace"]["unclassified_paths"])

    def test_ws009_legacy_no_manifest_reviewed_wip_stays_blocked_without_adoption_receipt(
        self,
    ) -> None:
        """Freeze the .63 legacy handoff gap before adding an explicit adoption path."""
        init = self.init_task("WS909")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS909",
                "--runner-id",
                "legacy-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        lease_id = str(claim["lease"]["lease_id"])
        code, intent, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "intent",
                str(self.root),
                "--task-id",
                "WS909",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
                "--path",
                "reviewed-wip.txt",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{intent}")
        (self.root / "reviewed-wip.txt").write_text("reviewed task WIP\n", encoding="utf-8")

        # Simulate an upgrade from a pre-workspace-manifest continuation while
        # preserving the old lease and round history.
        (state_dir / "workspace.json").unlink()
        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        lease["issued_at"] = continuation._iso(continuation._now() - timedelta(minutes=60))
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
                "WS909",
                "--owner-ended",
                "--evidence-ref",
                "review:reviewed-wip.txt",
                "--reason",
                "The old owner ended and the task WIP was reviewed, but no adoption receipt exists.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertEqual("blocked", reconciled["decision"])
        self.assertFalse(reconciled["eligible_for_recover"])
        self.assertIn("workspace_provenance_missing", reconciled["reasons"])
        self.assertEqual("absent", reconciled["observation"]["workspace_state"])
        self.assertEqual(
            ["reviewed-wip.txt"],
            reconciled["observation"]["workspace_unclassified_paths"],
        )
        self.assertEqual(
            claim["lease"]["generation"],
            reconciled["observation"]["latest_round"]["generation"],
        )

        code, denied, _ = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS909",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "new-owner",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("recovery_not_authorized", denied["error_code"])

    def test_ws009_legacy_no_manifest_reviewed_wip_can_be_adopted_without_resetting_history(
        self,
    ) -> None:
        init = self.init_task("WS909")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS909",
                "--runner-id",
                "legacy-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, intent, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "intent",
                str(self.root),
                "--task-id",
                "WS909",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
                "--path",
                "reviewed-wip.txt",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{intent}")
        (self.root / "reviewed-wip.txt").write_text("reviewed task WIP\n", encoding="utf-8")
        (self.root / "external-note.txt").write_text("reviewed external WIP\n", encoding="utf-8")

        (state_dir / "workspace.json").unlink()
        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        lease["issued_at"] = continuation._iso(continuation._now() - timedelta(minutes=60))
        lease["last_heartbeat_at"] = continuation._iso(
            continuation._now() - timedelta(minutes=31)
        )
        lease["expires_at"] = continuation._iso(continuation._now() - timedelta(minutes=1))
        continuation._write_json(lease_path, lease)
        preserved = {
            name: (state_dir / name).read_bytes()
            for name in ("control.json", "state.json", "rounds.json", "lease.json")
        }

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS909"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertIn("workspace_provenance_missing", doctor["blocked_reasons"])
        self.assertTrue(any("workspace adopt" in action for action in doctor["next_actions"]))

        code, incomplete, _ = self.run_json(
            [
                "continuation",
                "workspace",
                "adopt",
                str(self.root),
                "--task-id",
                "WS909",
                "--task-owned",
                "reviewed-wip.txt",
                "--evidence-ref",
                "review:reviewed-wip.txt",
                "--reason",
                "Reviewed legacy handoff WIP.",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("workspace_adoption_incomplete", incomplete["error_code"])

        code, adopted, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "adopt",
                str(self.root),
                "--task-id",
                "WS909",
                "--task-owned",
                "reviewed-wip.txt",
                "--baseline-external",
                "external-note.txt",
                "--evidence-ref",
                "review:reviewed-wip.txt",
                "--evidence-ref",
                "review:external-note.txt",
                "--reason",
                "Reviewed legacy handoff WIP and external baseline.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{adopted}")
        self.assertEqual("workspace_adopted", adopted["status"])
        self.assertEqual(int(claim["generation"]), adopted["adoption"]["prior_generation"])
        self.assertEqual(["reviewed-wip.txt"], adopted["workspace"]["task_owned_paths"])
        self.assertEqual(["external-note.txt"], adopted["workspace"]["baseline_external_paths"])
        self.assertEqual(
            {"baseline_external", "task_owned"},
            {entry["classification"] for entry in adopted["adoption"]["entries"]},
        )
        for entry in adopted["adoption"]["entries"]:
            self.assertTrue(entry["evidence_refs"])
            self.assertEqual(64, len(entry["digest"]))
        for name, before in preserved.items():
            self.assertEqual(before, (state_dir / name).read_bytes(), name)

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS909",
                "--owner-ended",
                "--evidence-ref",
                "review:legacy-owner-ended",
                "--reason",
                "The old owner ended and adopted WIP remained unchanged.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertEqual("eligible", reconciled["decision"])
        self.assertNotIn("workspace_provenance_missing", reconciled["reasons"])
        code, recovered, stderr = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS909",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "new-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{recovered}")
        self.assertEqual(["reviewed-wip.txt"], recovered["workspace"]["task_owned_paths"])
        self.assertEqual(["external-note.txt"], recovered["workspace"]["baseline_external_paths"])

    def test_ws009_legacy_workspace_adoption_fails_closed_on_active_owner_or_head_drift(
        self,
    ) -> None:
        init = self.init_task("WS909")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS909",
                "--runner-id",
                "legacy-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        (self.root / "reviewed-wip.txt").write_text("reviewed task WIP\n", encoding="utf-8")
        (state_dir / "workspace.json").unlink()

        adopt_args = [
            "continuation",
            "workspace",
            "adopt",
            str(self.root),
            "--task-id",
            "WS909",
            "--task-owned",
            "reviewed-wip.txt",
            "--evidence-ref",
            "review:reviewed-wip.txt",
            "--reason",
            "Reviewed legacy task WIP.",
        ]
        code, active, _ = self.run_json(adopt_args)
        self.assertEqual(3, code)
        self.assertEqual("workspace_adoption_owner_active", active["error_code"])

        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        lease["issued_at"] = continuation._iso(continuation._now() - timedelta(minutes=60))
        lease["last_heartbeat_at"] = continuation._iso(
            continuation._now() - timedelta(minutes=31)
        )
        lease["expires_at"] = continuation._iso(continuation._now() - timedelta(minutes=1))
        continuation._write_json(lease_path, lease)
        self._git("add", "reviewed-wip.txt")
        self._git("commit", "-m", "advance head after legacy owner")
        (self.root / "reviewed-wip.txt").write_text("reviewed task WIP after head drift\n", encoding="utf-8")

        code, drifted, _ = self.run_json(adopt_args)
        self.assertEqual(3, code)
        self.assertEqual("workspace_adoption_head_mismatch", drifted["error_code"])

    def test_ws009_legacy_workspace_adoption_enforces_task_owned_scope(self) -> None:
        snapshot = {
            "head": "a" * 40,
            "entries": [
                {
                    "schema_version": continuation_workspace.ENTRY_SCHEMA,
                    "path": "docs/outside.md",
                    "status": "??",
                    "digest": "b" * 64,
                }
            ],
        }
        with self.assertRaises(continuation_workspace.ContinuationWorkspaceError) as raised:
            continuation_workspace.adopt_legacy_manifest(
                task_id="WS909",
                prior_generation=3,
                snapshot=snapshot,
                task_owned_paths=["docs/outside.md"],
                baseline_external_paths=[],
                allowed_scopes=["src/**"],
                candidate_paths={"docs/outside.md": ["docs/outside.md"]},
                evidence_refs=["review:outside"],
                reason="Reviewed path outside the bound Workstream scope.",
                receipt_id="receipt-1",
                now=continuation._iso(),
            )
        self.assertEqual("workspace_adoption_out_of_scope", raised.exception.code)

    def test_ws008_preexisting_unrelated_dirty_is_baseline_not_global_blocker(self) -> None:
        """WS008 target: pre-claim external dirty is preserved as baseline metadata."""
        (self.root / "manual-note.txt").write_text("manual external change\n", encoding="utf-8")
        code, payload, stderr = self.run_json(
            [
                "continuation",
                "init",
                str(self.root),
                "--task-id",
                "WS908",
                "--title",
                "Dirty baseline test",
                "--objective",
                "Preserve non-overlapping external dirty state.",
                "--next-action",
                "Modify only task-owned paths.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{payload}")
        self.assertEqual("initialized", payload["status"])
        self.assertEqual(["manual-note.txt"], payload["workspace"]["baseline_external_paths"])

    def test_ws008_unrelated_post_claim_dirty_does_not_create_false_parallel_block(self) -> None:
        """WS008 target: disjoint external dirty is observable but not a worktree-wide stop."""
        self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "ws008-test-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        (self.root / "unrelated-user-note.txt").write_text("external\n", encoding="utf-8")
        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertNotIn("worktree_dirty", doctor["blocked_reasons"])
        self.assertEqual(
            ["unrelated-user-note.txt"],
            doctor["workspace"]["unexpected_nonoverlap_paths"],
        )

    def test_ws008_stale_owner_reconcile_can_preserve_attributable_dirty_wip(self) -> None:
        """WS008 target: dirty orphan WIP is not rejected solely because Git is dirty."""
        init = self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "ws008-old-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, intent, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "intent",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
                "--path",
                "runner-owned.txt",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{intent}")
        (self.root / "runner-owned.txt").write_text("recover me\n", encoding="utf-8")
        (self.root / "external-note.txt").write_text("preserve me\n", encoding="utf-8")

        state_dir = Path(str(init["state_dir"]))
        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        lease["issued_at"] = continuation._iso(continuation._now() - timedelta(minutes=60))
        stale = continuation._now() - timedelta(minutes=31)
        lease["last_heartbeat_at"] = continuation._iso(stale)
        lease_path.write_text(json.dumps(lease, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS908",
                "--owner-ended",
                "--evidence-ref",
                "test:owner-ended",
                "--reason",
                "Old owner ended; dirty WIP is attributable to that round.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertTrue(reconciled["eligible_for_recover"], reconciled)
        self.assertNotIn("worktree_dirty", reconciled["reasons"])
        self.assertEqual(["runner-owned.txt"], reconciled["observation"]["workspace_runner_owned_paths"])
        self.assertEqual(
            ["external-note.txt"],
            reconciled["observation"]["workspace_unexpected_nonoverlap_paths"],
        )

        code, recovered, stderr = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS908",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "ws008-new-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{recovered}")
        self.assertGreater(int(recovered["generation"]), int(claim["generation"]))
        self.assertEqual(["runner-owned.txt"], recovered["workspace"]["runner_owned_paths"])
        self.assertEqual(["runner-owned.txt"], recovered["workspace"]["write_intent_paths"])
        self.assertEqual(["external-note.txt"], recovered["workspace"]["unexpected_nonoverlap_paths"])
        self.assertTrue((self.root / "runner-owned.txt").exists())
        self.assertTrue((self.root / "external-note.txt").exists())

        code, stale_owner, _ = self.run_json(
            [
                "continuation",
                "heartbeat",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(3, code)
        self.assertIn(stale_owner["error_code"], {"lease_mismatch", "fence_generation_mismatch"})

        code, refreshed, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "refresh",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(recovered["lease"]["lease_id"]),
                *self.owner_flags(recovered),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{refreshed}")
        self.assertEqual(["runner-owned.txt"], refreshed["workspace"]["runner_owned_paths"])
        self.assertEqual(["external-note.txt"], refreshed["workspace"]["unexpected_nonoverlap_paths"])

    def test_ws008_dirty_recovery_receipt_stales_when_workspace_digest_changes(self) -> None:
        init = self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "ws008-old-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, _, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "intent",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
                "--path",
                "runner-owned.txt",
            ]
        )
        self.assertEqual(0, code, stderr)
        (self.root / "runner-owned.txt").write_text("version one\n", encoding="utf-8")

        state_dir = Path(str(init["state_dir"]))
        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        lease["issued_at"] = continuation._iso(continuation._now() - timedelta(minutes=60))
        lease["last_heartbeat_at"] = continuation._iso(continuation._now() - timedelta(minutes=31))
        lease_path.write_text(json.dumps(lease, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS908",
                "--owner-ended",
                "--evidence-ref",
                "test:owner-ended",
                "--reason",
                "Old owner ended.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        recorded_digest = reconciled["observation"]["workspace_manifest_digest"]

        (self.root / "runner-owned.txt").write_text("version two\n", encoding="utf-8")
        code, stale, _ = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS908",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "ws008-new-owner",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("reconciliation_stale", stale["error_code"], stale)
        self.assertNotEqual(recorded_digest, stale["details"]["current"]["workspace_manifest_digest"])

    def test_ws008_stale_threshold_is_independent_from_renew_interval(self) -> None:
        """WS008 target: liveness cadence is independently configured from lease renewal."""
        init = self.init_task("WS908")
        state_dir = Path(str(init["state_dir"]))
        code, configured, stderr = self.run_json(
            [
                "continuation",
                "configure",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-ttl-minutes",
                "180",
                "--renew-interval-minutes",
                "45",
                "--heartbeat-interval-minutes",
                "10",
                "--stale-after-minutes",
                "25",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{configured}")
        self.assertEqual("long-running", configured["control"]["timing_profile"])
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "ws008-long-run-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        lease["issued_at"] = continuation._iso(continuation._now() - timedelta(minutes=60))
        lease["last_heartbeat_at"] = continuation._iso(continuation._now() - timedelta(minutes=30))
        lease_path.write_text(json.dumps(lease, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertEqual("stale", doctor["lease"]["liveness"])
        self.assertEqual(1500, doctor["lease"]["stale_after_seconds"])

    def test_ws008_long_running_round_survives_two_hour_simulated_heartbeat_renew_cycles(self) -> None:
        """WS008.5 failure injection: a 2h+ Gate remains one fenced generation."""
        init = self.init_task("WS918")
        state_dir = Path(str(init["state_dir"]))
        code, configured, stderr = self.run_json(
            [
                "continuation",
                "configure",
                str(self.root),
                "--task-id",
                "WS918",
                "--profile",
                "long-running",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{configured}")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS918",
                "--runner-id",
                "ws008-two-hour-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        lease_id = str(claim["lease"]["lease_id"])
        generation = int(claim["generation"])
        lease_path = state_dir / "lease.json"

        for elapsed_minutes in (55, 110, 125):
            with self.subTest(elapsed_minutes=elapsed_minutes):
                lease = json.loads(lease_path.read_text(encoding="utf-8"))
                now = continuation._now()
                lease["issued_at"] = continuation._iso(now - timedelta(minutes=elapsed_minutes))
                lease["last_heartbeat_at"] = continuation._iso(now - timedelta(minutes=9))
                lease["last_renew_at"] = continuation._iso(now - timedelta(minutes=44))
                lease["expires_at"] = continuation._iso(now + timedelta(minutes=136))
                continuation._write_json(lease_path, lease)
                expires_before_heartbeat = lease["expires_at"]

                code, heartbeat, stderr = self.run_json(
                    [
                        "continuation",
                        "heartbeat",
                        str(self.root),
                        "--task-id",
                        "WS918",
                        "--lease-id",
                        lease_id,
                        *self.owner_flags(claim),
                    ]
                )
                self.assertEqual(0, code, f"{stderr}\n{heartbeat}")
                after_heartbeat = json.loads(lease_path.read_text(encoding="utf-8"))
                self.assertEqual(expires_before_heartbeat, after_heartbeat["expires_at"])

                code, renewed, stderr = self.run_json(
                    [
                        "continuation",
                        "renew",
                        str(self.root),
                        "--task-id",
                        "WS918",
                        "--lease-id",
                        lease_id,
                        *self.owner_flags(claim),
                    ]
                )
                self.assertEqual(0, code, f"{stderr}\n{renewed}")
                self.assertEqual("renewed", renewed["status"])
                persisted = json.loads(lease_path.read_text(encoding="utf-8"))
                self.assertEqual(generation, int(persisted["generation"]))
                self.assertGreater(
                    continuation._parse_iso(str(persisted["expires_at"]), field="expires_at"),
                    continuation._now() + timedelta(minutes=170),
                )

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS918"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertEqual("fresh", doctor["lease"]["liveness"])
        self.assertEqual(generation, int(doctor["lease"]["lease"]["generation"]))
        self.assertFalse(doctor["can_claim"])
        self.assertEqual("running", doctor["state"]["status"])

    def test_ws008_long_running_profile_configures_existing_task_and_generated_prompt(self) -> None:
        init = self.init_task("WS908")
        state_dir = Path(str(init["state_dir"]))
        state_before = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))

        code, configured, stderr = self.run_json(
            [
                "continuation",
                "configure",
                str(self.root),
                "--task-id",
                "WS908",
                "--profile",
                "long-running",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{configured}")
        self.assertEqual(
            {
                "timing_profile": "long-running",
                "interval_minutes": 60,
                "lease_ttl_minutes": 180,
                "renew_interval_minutes": 45,
                "heartbeat_interval_minutes": 10,
                "stale_after_minutes": 25,
            },
            configured["control"],
        )
        state_after = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state_before, state_after)

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertEqual("long-running", doctor["control"]["timing_profile"])
        self.assertEqual(10, doctor["control"]["heartbeat_interval_minutes"])
        self.assertEqual(25, doctor["control"]["stale_after_minutes"])

        code, prompt, stderr = self.run_json(
            ["continuation", "prompt", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{prompt}")
        prompt_text = str(prompt["prompt"])
        self.assertIn("Timing profile: long-running", prompt_text)
        self.assertIn("Heartbeat recommendation: every 10 minutes", prompt_text)
        self.assertIn("Stale threshold: 25 minutes", prompt_text)
        self.assertIn("Renew recommendation: every 45 minutes", prompt_text)
        self.assertIn("scheduler interval is only a wake cadence", prompt_text)

    def test_ws008_configure_refuses_active_owner(self) -> None:
        self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "ws008-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, configured, _ = self.run_json(
            [
                "continuation",
                "configure",
                str(self.root),
                "--task-id",
                "WS908",
                "--profile",
                "long-running",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("continuation_busy", configured["error_code"])

    def test_ws008_write_intent_rejects_protected_external_dirty_overlap(self) -> None:
        (self.root / "manual-note.txt").write_text("manual external change\n", encoding="utf-8")
        self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "ws008-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, intent, _ = self.run_json(
            [
                "continuation",
                "workspace",
                "intent",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
                "--path",
                "manual-note.txt",
            ]
        )
        self.assertEqual(2, code)
        self.assertEqual("workspace_intent_conflict", intent["error_code"])

    def test_ws008_release_preserves_unrelated_external_dirty_without_reconciling(self) -> None:
        self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "ws008-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        (self.root / "external-note.txt").write_text("manual\n", encoding="utf-8")
        code, release, stderr = self.run_json(
            [
                "continuation",
                "release",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{release}")
        self.assertEqual("released", release["status"])
        self.assertEqual("ready", release["state"]["status"])
        self.assertEqual(["external-note.txt"], release["workspace"]["baseline_external_paths"])
        self.assertEqual([], release["workspace"]["unexpected_nonoverlap_paths"])
        self.assertTrue((self.root / "external-note.txt").exists())

    def test_ws008_preexisting_external_dirty_may_change_without_false_conflict(self) -> None:
        (self.root / "manual-note.txt").write_text("manual v1\n", encoding="utf-8")
        self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "ws008-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        (self.root / "manual-note.txt").write_text("manual v2\n", encoding="utf-8")
        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertNotIn("workspace_conflict", doctor["blocked_reasons"])
        self.assertNotIn("worktree_dirty", doctor["blocked_reasons"])
        self.assertEqual(["manual-note.txt"], doctor["workspace"]["baseline_external_paths"])

    def test_ws008_workspace_intent_scope_filter_is_path_specific(self) -> None:
        manifest = continuation_workspace.new_manifest(
            task_id="WS908",
            snapshot={"head": "a" * 40, "entries": []},
            now=continuation._iso(),
        )
        manifest = continuation_workspace.add_intents(
            manifest,
            task_id="WS908",
            paths=["src/allowed.py"],
            allowed_scopes=["src/**"],
            candidate_paths={"src/allowed.py": ["src/allowed.py"]},
            snapshot={"head": "a" * 40, "entries": []},
            now=continuation._iso(),
        )
        self.assertEqual(["src/allowed.py"], manifest["write_intents"])
        with self.assertRaises(continuation_workspace.ContinuationWorkspaceError) as raised:
            continuation_workspace.add_intents(
                manifest,
                task_id="WS908",
                paths=["docs/outside.md"],
                allowed_scopes=["src/**"],
                candidate_paths={"docs/outside.md": ["docs/outside.md"]},
                snapshot={"head": "a" * 40, "entries": []},
                now=continuation._iso(),
            )
        self.assertEqual("workspace_intent_out_of_scope", raised.exception.code)

    def test_ws008_coordination_attempt_without_owner_is_only_claim_candidate(self) -> None:
        init = self.init_task("WS908")
        state_dir = Path(str(init["state_dir"]))
        code, before, stderr = self.run_json(
            ["continuation", "coordination", "status", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{before}")
        self.assertEqual("absent", before["state"])

        code, attempt, stderr = self.run_json(
            [
                "continuation",
                "coordination",
                "attempt",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
                "--objective-summary",
                "Continue the next bounded gate.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{attempt}")
        self.assertEqual("claim_candidate_registered", attempt["status"])
        self.assertEqual("claim_candidate", attempt["attempt"]["status"])
        self.assertIsNone(attempt["attempt"]["observed_owner_generation"])
        self.assertTrue((state_dir / "coordination.json").is_file())
        self.assertEqual("", self._git("status", "--porcelain").stdout)

    def test_ws008_coordination_contenders_join_one_challenge_per_owner_generation(self) -> None:
        self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "owner-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        generation = int(claim["generation"])

        attempt_ids: list[str] = []
        challenge_ids: list[str] = []
        for runner_id in ("contender-a", "contender-b"):
            code, attempt, stderr = self.run_json(
                [
                    "continuation",
                    "coordination",
                    "attempt",
                    str(self.root),
                    "--task-id",
                    "WS908",
                    "--runner-id",
                    runner_id,
                    "--objective-summary",
                    "Continue the same WS008 gate.",
                ]
            )
            self.assertEqual(0, code, f"{stderr}\n{attempt}")
            self.assertEqual("contender_registered", attempt["status"])
            self.assertEqual(generation, attempt["attempt"]["observed_owner_generation"])
            attempt_id = str(attempt["attempt"]["attempt_id"])
            attempt_ids.append(attempt_id)

            code, challenge, stderr = self.run_json(
                [
                    "continuation",
                    "coordination",
                    "challenge",
                    str(self.root),
                    "--task-id",
                    "WS908",
                    "--attempt-id",
                    attempt_id,
                ]
            )
            self.assertEqual(0, code, f"{stderr}\n{challenge}")
            challenge_ids.append(str(challenge["challenge"]["challenge_id"]))

        self.assertEqual(challenge_ids[0], challenge_ids[1])
        code, status, stderr = self.run_json(
            ["continuation", "coordination", "status", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{status}")
        self.assertEqual(2, status["coordination"]["contender_count"])
        self.assertEqual(1, status["coordination"]["challenge_count"])
        active = status["coordination"]["nonterminal_challenges"]
        self.assertEqual(1, len(active))
        self.assertEqual(generation, active[0]["owner_generation"])
        self.assertEqual(attempt_ids, active[0]["contender_attempt_ids"])
        self.assertFalse(active[0]["deadline_passed"])

    def test_ws008_coordination_old_attempt_cannot_challenge_new_owner_generation(self) -> None:
        self.init_task("WS908")
        code, first_claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "owner-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{first_claim}")
        code, attempt, stderr = self.run_json(
            [
                "continuation",
                "coordination",
                "attempt",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
                "--objective-summary",
                "Continue after the current owner.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{attempt}")
        attempt_id = str(attempt["attempt"]["attempt_id"])

        code, released, stderr = self.run_json(
            [
                "continuation",
                "release",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(first_claim["lease"]["lease_id"]),
                *self.owner_flags(first_claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{released}")
        code, second_claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "owner-b",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{second_claim}")
        self.assertGreater(int(second_claim["generation"]), int(first_claim["generation"]))

        code, challenged, _ = self.run_json(
            [
                "continuation",
                "coordination",
                "challenge",
                str(self.root),
                "--task-id",
                "WS908",
                "--attempt-id",
                attempt_id,
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("coordination_owner_changed", challenged["error_code"])

    def test_ws008_coordination_rejects_unbounded_objective_text(self) -> None:
        self.init_task("WS908")
        code, attempt, _ = self.run_json(
            [
                "continuation",
                "coordination",
                "attempt",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
                "--objective-summary",
                "x" * 1025,
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("coordination_text_too_large", attempt["error_code"])

    def test_ws008_coordination_attempt_auto_opens_challenge_for_active_owner(self) -> None:
        self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "owner-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")

        code, attempt, stderr = self.run_json(
            [
                "continuation",
                "coordination",
                "attempt",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
                "--objective-summary",
                "Continue the same bounded gate.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{attempt}")
        self.assertEqual("contender_registered", attempt["status"])
        self.assertTrue(attempt["challenge_created"])
        self.assertEqual("open", attempt["challenge"]["status"])
        self.assertEqual(int(claim["generation"]), attempt["challenge"]["owner_generation"])
        self.assertEqual(1, len(attempt["coordination"]["nonterminal_challenges"]))

    def test_ws008_generic_project_command_probes_pending_challenge_without_ack(self) -> None:
        code, initialized, stderr = self.run_json(["init", str(self.root / "docs" / "ai")])
        self.assertEqual(0, code, f"{stderr}\n{initialized}")
        self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "owner-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, attempt, stderr = self.run_json(
            [
                "continuation",
                "coordination",
                "attempt",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
                "--objective-summary",
                "Surface the challenge through ordinary project commands.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{attempt}")
        challenge_id = str(attempt["challenge"]["challenge_id"])

        code, project_status, stderr = self.run_json(["status", str(self.root)])
        self.assertEqual(0, code, f"{stderr}\n{project_status}")
        self.assertIn("ACF continuation challenge pending", stderr)
        self.assertIn("task=WS908", stderr)
        self.assertIn("does not ACK the challenge or grant ownership", stderr)

        code, coordination_status, stderr = self.run_json(
            ["continuation", "coordination", "status", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{coordination_status}")
        current = next(
            item
            for item in coordination_status["coordination"]["challenges"]
            if item["challenge_id"] == challenge_id
        )
        self.assertEqual("open", current["status"])
        self.assertIsNone(current["acknowledged_at"])

    def test_ws008_generic_probe_ignores_challenge_for_noncurrent_generation(self) -> None:
        code, initialized, stderr = self.run_json(["init", str(self.root / "docs" / "ai")])
        self.assertEqual(0, code, f"{stderr}\n{initialized}")
        init = self.init_task("WS908")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "owner-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, attempt, stderr = self.run_json(
            [
                "continuation",
                "coordination",
                "attempt",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
                "--objective-summary",
                "Create a challenge that will be made historically stale.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{attempt}")
        coordination_path = state_dir / "coordination.json"
        coordination = continuation._read_json(coordination_path, label="coordination")
        coordination["challenges"][0]["owner_generation"] = int(claim["generation"]) + 100
        continuation._write_json(coordination_path, coordination)

        code, project_status, stderr = self.run_json(["status", str(self.root)])
        self.assertEqual(0, code, f"{stderr}\n{project_status}")
        self.assertNotIn("ACF continuation challenge pending", stderr)

    def test_ws008_owner_authenticated_activity_acknowledges_pending_challenge(self) -> None:
        self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "owner-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, attempt, stderr = self.run_json(
            [
                "continuation",
                "coordination",
                "attempt",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
                "--objective-summary",
                "Continue after the current owner.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{attempt}")
        challenge_id = str(attempt["challenge"]["challenge_id"])

        code, denied, _ = self.run_json(
            [
                "continuation",
                "assert-owner",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                "--generation",
                str(claim["generation"]),
                "--fence-token",
                "not-the-owner-token",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("fence_token_mismatch", denied["error_code"])
        code, before, stderr = self.run_json(
            ["continuation", "coordination", "status", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{before}")
        current = next(item for item in before["coordination"]["challenges"] if item["challenge_id"] == challenge_id)
        self.assertEqual("open", current["status"])

        code, confirmed, stderr = self.run_json(
            [
                "continuation",
                "assert-owner",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{confirmed}")
        code, after, stderr = self.run_json(
            ["continuation", "coordination", "status", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{after}")
        current = next(item for item in after["coordination"]["challenges"] if item["challenge_id"] == challenge_id)
        self.assertEqual("acknowledged", current["status"])
        self.assertEqual("owner_active", current["resolution"])
        self.assertEqual(str(claim["lease"]["lease_id"]), current["acknowledged_lease_id"])
        self.assertEqual("owner-a", current["acknowledged_runner_id"])
        self.assertEqual([], after["coordination"]["nonterminal_challenges"])

    def test_ws008_coordination_timeout_is_only_ownership_forfeiture_candidate(self) -> None:
        init = self.init_task("WS908")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "owner-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, attempt, stderr = self.run_json(
            [
                "continuation",
                "coordination",
                "attempt",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
                "--objective-summary",
                "Continue after timeout if formal recovery proves safety.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{attempt}")
        challenge_id = str(attempt["challenge"]["challenge_id"])
        coordination_path = state_dir / "coordination.json"
        coordination = continuation._read_json(coordination_path, label="coordination")
        challenge = coordination["challenges"][0]
        challenge["opened_at"] = continuation._iso(continuation._now() - timedelta(minutes=2))
        challenge["deadline_at"] = continuation._iso(continuation._now() - timedelta(minutes=1))
        continuation._write_json(coordination_path, coordination)

        code, status, stderr = self.run_json(
            ["continuation", "coordination", "status", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{status}")
        self.assertEqual([challenge_id], status["timed_out_challenge_ids"])
        current = next(item for item in status["coordination"]["challenges"] if item["challenge_id"] == challenge_id)
        self.assertEqual("timed_out", current["status"])
        self.assertTrue(current["ownership_forfeiture_candidate"])
        self.assertEqual(1, status["coordination"]["ownership_forfeiture_candidate_count"])

        code, busy, _ = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("continuation_busy", busy["error_code"])

        code, heartbeat, stderr = self.run_json(
            [
                "continuation",
                "heartbeat",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{heartbeat}")
        code, acknowledged, stderr = self.run_json(
            ["continuation", "coordination", "status", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{acknowledged}")
        current = next(
            item
            for item in acknowledged["coordination"]["challenges"]
            if item["challenge_id"] == challenge_id
        )
        self.assertEqual("acknowledged", current["status"])
        self.assertEqual("owner_active", current["resolution"])
        self.assertIsNotNone(current["timed_out_at"])
        self.assertFalse(current["ownership_forfeiture_candidate"])
        self.assertEqual(0, acknowledged["coordination"]["ownership_forfeiture_candidate_count"])

    def test_ws008_owner_release_resolves_pending_challenge_without_preemption(self) -> None:
        self.init_task("WS908")
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "owner-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, attempt, stderr = self.run_json(
            [
                "continuation",
                "coordination",
                "attempt",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
                "--objective-summary",
                "Continue after owner release.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{attempt}")
        challenge_id = str(attempt["challenge"]["challenge_id"])

        code, released, stderr = self.run_json(
            [
                "continuation",
                "release",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{released}")
        self.assertEqual("owner_released", released["coordination_resolution"]["resolution"])
        code, status, stderr = self.run_json(
            ["continuation", "coordination", "status", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{status}")
        current = next(item for item in status["coordination"]["challenges"] if item["challenge_id"] == challenge_id)
        self.assertEqual("resolved", current["status"])
        self.assertEqual("owner_released", current["resolution"])
        self.assertEqual([], status["coordination"]["nonterminal_challenges"])

        code, next_claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{next_claim}")
        self.assertGreater(int(next_claim["generation"]), int(claim["generation"]))

    def test_ws008_timed_out_challenge_can_authorize_fenced_recovery_without_death_claim(self) -> None:
        init = self.init_task("WS908")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "owner-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, attempt, stderr = self.run_json(
            [
                "continuation",
                "coordination",
                "attempt",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
                "--objective-summary",
                "Take ownership only after challenge-backed formal recovery.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{attempt}")
        challenge_id = str(attempt["challenge"]["challenge_id"])
        coordination_path = state_dir / "coordination.json"
        coordination = continuation._read_json(coordination_path, label="coordination")
        challenge = coordination["challenges"][0]
        challenge["opened_at"] = continuation._iso(continuation._now() - timedelta(minutes=2))
        challenge["deadline_at"] = continuation._iso(continuation._now() - timedelta(minutes=1))
        continuation._write_json(coordination_path, coordination)

        code, status, stderr = self.run_json(
            ["continuation", "coordination", "status", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{status}")
        self.assertEqual([challenge_id], status["timed_out_challenge_ids"])
        self.assertEqual("fresh", status["owner"]["liveness"])

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS908",
                "--record",
                "--reason",
                "The owner did not answer the bounded challenge; formal state evidence is otherwise safe.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertTrue(reconciled["eligible_for_recover"], reconciled)
        self.assertFalse(reconciled["assertions"]["owner_ended"])
        self.assertEqual([], reconciled["evidence_refs"])
        candidates = reconciled["observation"]["ownership_forfeiture_candidates"]
        self.assertEqual([challenge_id], [item["challenge_id"] for item in candidates])
        self.assertTrue(reconciled["observation"]["coordination_digest"])

        code, recovered, stderr = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS908",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "contender-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{recovered}")
        self.assertEqual(int(claim["generation"]) + 1, recovered["generation"])
        resolution = recovered["recovery"]["challenge_resolution"]
        self.assertEqual(challenge_id, resolution["challenge_id"])
        self.assertEqual("ownership_recovered", resolution["resolution"])
        self.assertEqual(recovered["generation"], resolution["recovery_generation"])

        code, coordination_after, stderr = self.run_json(
            ["continuation", "coordination", "status", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{coordination_after}")
        current = next(
            item
            for item in coordination_after["coordination"]["challenges"]
            if item["challenge_id"] == challenge_id
        )
        self.assertEqual("resolved", current["status"])
        self.assertEqual("ownership_recovered", current["resolution"])
        self.assertEqual(0, coordination_after["coordination"]["ownership_forfeiture_candidate_count"])

        code, fenced, _ = self.run_json(
            [
                "continuation",
                "heartbeat",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("lease_mismatch", fenced["error_code"])

    def test_ws008_owner_ack_after_reconcile_stales_challenge_backed_recovery(self) -> None:
        init = self.init_task("WS908")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "owner-a",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        code, attempt, stderr = self.run_json(
            [
                "continuation",
                "coordination",
                "attempt",
                str(self.root),
                "--task-id",
                "WS908",
                "--runner-id",
                "contender-a",
                "--objective-summary",
                "Race owner acknowledgement against recovery safely.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{attempt}")
        coordination_path = state_dir / "coordination.json"
        coordination = continuation._read_json(coordination_path, label="coordination")
        challenge = coordination["challenges"][0]
        challenge["opened_at"] = continuation._iso(continuation._now() - timedelta(minutes=2))
        challenge["deadline_at"] = continuation._iso(continuation._now() - timedelta(minutes=1))
        continuation._write_json(coordination_path, coordination)

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS908",
                "--record",
                "--reason",
                "Challenge timed out before the old owner responded.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertTrue(reconciled["eligible_for_recover"], reconciled)

        code, heartbeat, stderr = self.run_json(
            [
                "continuation",
                "heartbeat",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                str(claim["lease"]["lease_id"]),
                *self.owner_flags(claim),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{heartbeat}")

        code, denied, _ = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS908",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "contender-a",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("reconciliation_stale", denied["error_code"])
        self.assertNotEqual(
            reconciled["observation"]["coordination_digest"],
            denied["details"]["current"]["coordination_digest"],
        )

        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", "WS908"]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertEqual(str(claim["lease"]["lease_id"]), doctor["lease"]["lease"]["lease_id"])
        self.assertEqual(int(claim["generation"]), doctor["lease"]["lease"]["generation"])

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

    def test_crash_point_failure_matrix_classifies_wait_reconcile_and_recover(self) -> None:
        """Frozen WS007 crash matrix: every durable boundary has an explicit recovery class."""

        def init_claim(task_id: str) -> tuple[Path, dict[str, object], str]:
            init = self.init_task(task_id)
            code, claim, stderr = self.run_json(
                [
                    "continuation",
                    "claim",
                    str(self.root),
                    "--task-id",
                    task_id,
                    "--runner-id",
                    f"runner-{task_id.lower()}",
                ]
            )
            self.assertEqual(0, code, f"{stderr}\n{claim}")
            return Path(str(init["state_dir"])), claim, str(claim["lease"]["lease_id"])

        def make_stale(state_dir: Path) -> None:
            lease_path = state_dir / "lease.json"
            lease = json.loads(lease_path.read_text(encoding="utf-8"))
            lease["issued_at"] = continuation._iso(
                continuation._now() - timedelta(minutes=60)
            )
            lease["last_heartbeat_at"] = continuation._iso(
                continuation._now() - timedelta(minutes=31)
            )
            continuation._write_json(lease_path, lease)

        def owner_ended_reconcile(task_id: str, *extra: str) -> dict[str, object]:
            code, payload, stderr = self.run_json(
                [
                    "continuation",
                    "reconcile",
                    str(self.root),
                    "--task-id",
                    task_id,
                    "--owner-ended",
                    "--evidence-ref",
                    f"scheduler:{task_id}-owner-ended",
                    *extra,
                ]
            )
            self.assertEqual(0, code, f"{stderr}\n{payload}")
            return payload

        # Crash after claim while heartbeat is fresh -> wait for the live owner.
        _, fresh_claim, fresh_lease_id = init_claim("WS901")
        code, fresh, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS901",
                "--owner-ended",
                "--evidence-ref",
                "scheduler:untrusted-early-end-signal",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{fresh}")
        self.assertEqual("blocked", fresh["decision"])
        self.assertIn("active_owner_live", fresh["reasons"])
        self.assertEqual(fresh_lease_id, fresh["observation"]["lease_id"])
        self.assertEqual("fresh", fresh["observation"]["liveness"])

        # Crash after effect prepare -> identity exists but outcome is unresolved: reconcile only.
        state_dir, prepared_claim, prepared_lease_id = init_claim("WS902")
        code, prepared, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS902",
                "--lease-id",
                prepared_lease_id,
                *self.owner_flags(prepared_claim),
                "--key",
                "effect-prepare",
                "--kind",
                "external-job",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prepared}")
        make_stale(state_dir)
        reconciled = owner_ended_reconcile("WS902")
        self.assertEqual("blocked", reconciled["decision"])
        self.assertIn("unresolved_effects", reconciled["reasons"])
        self.assertEqual(["effect-prepare"], reconciled["observation"]["effect_summary"]["unresolved"])

        # Crash after external submit acknowledgement -> active external identity remains unresolved.
        state_dir, ack_claim, ack_lease_id = init_claim("WS903")
        code, _, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS903",
                "--lease-id",
                ack_lease_id,
                *self.owner_flags(ack_claim),
                "--key",
                "external-ack",
                "--kind",
                "campaign",
            ]
        )
        self.assertEqual(0, code, stderr)
        code, ack, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "update",
                str(self.root),
                "--task-id",
                "WS903",
                "--lease-id",
                ack_lease_id,
                *self.owner_flags(ack_claim),
                "--key",
                "external-ack",
                "--status",
                "active",
                "--external-id",
                "campaign-ack-001",
                "--milestone",
                "submitted",
                "--evidence-ref",
                "authority:campaign-ack-001",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{ack}")
        make_stale(state_dir)
        reconciled = owner_ended_reconcile("WS903")
        self.assertEqual("blocked", reconciled["decision"])
        self.assertIn("unresolved_effects", reconciled["reasons"])

        # Crash after terminal/collect/aggregate evidence -> completed identities are reusable.
        for task_id, key, milestone in (
            ("WS904", "terminal-effect", "terminal"),
            ("WS905", "collected-effect", "collected"),
            ("WS906", "aggregate-effect", "aggregated"),
        ):
            with self.subTest(crash_point=milestone):
                state_dir, claim, lease_id = init_claim(task_id)
                code, _, stderr = self.run_json(
                    [
                        "continuation",
                        "effect",
                        "prepare",
                        str(self.root),
                        "--task-id",
                        task_id,
                        "--lease-id",
                        lease_id,
                        *self.owner_flags(claim),
                        "--key",
                        key,
                        "--kind",
                        "external-job",
                    ]
                )
                self.assertEqual(0, code, stderr)
                code, updated, stderr = self.run_json(
                    [
                        "continuation",
                        "effect",
                        "update",
                        str(self.root),
                        "--task-id",
                        task_id,
                        "--lease-id",
                        lease_id,
                        *self.owner_flags(claim),
                        "--key",
                        key,
                        "--status",
                        "completed",
                        "--milestone",
                        milestone,
                        "--evidence-ref",
                        f"artifact:{milestone}.json",
                    ]
                )
                self.assertEqual(0, code, f"{stderr}\n{updated}")
                make_stale(state_dir)
                reconciled = owner_ended_reconcile(task_id)
                self.assertEqual("eligible", reconciled["decision"])
                self.assertEqual([], reconciled["reasons"])
                self.assertEqual([key], reconciled["observation"]["effect_summary"]["terminal"])

        # Crash after Git commit -> advanced HEAD must be explicitly reconciled, never inferred.
        state_dir, _, _ = init_claim("WS907")
        (self.root / "crash-after-commit.txt").write_text("durable commit\n", encoding="utf-8")
        self._git("add", "crash-after-commit.txt")
        self._git("commit", "-m", "test: crash after commit")
        current_head = self._git("rev-parse", "HEAD").stdout.strip()
        make_stale(state_dir)
        reconciled = owner_ended_reconcile("WS907")
        self.assertEqual("blocked", reconciled["decision"])
        self.assertIn("head_change_unaccepted", reconciled["reasons"])
        reconciled = owner_ended_reconcile("WS907", "--accept-head", current_head)
        self.assertEqual("eligible", reconciled["decision"])

        # Crash after continuation checkpoint -> explicit waiting state survives and is recoverable.
        state_dir, checkpoint_claim, checkpoint_lease_id = init_claim("WS908")
        code, checkpointed, stderr = self.run_json(
            [
                "continuation",
                "checkpoint",
                str(self.root),
                "--task-id",
                "WS908",
                "--lease-id",
                checkpoint_lease_id,
                *self.owner_flags(checkpoint_claim),
                "--status",
                "waiting_external",
                "--next-action",
                "Reuse the existing completed external identity.",
                "--evidence-ref",
                "artifact:checkpoint.json",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{checkpointed}")
        make_stale(state_dir)
        reconciled = owner_ended_reconcile("WS908")
        self.assertEqual("eligible", reconciled["decision"])
        self.assertEqual("waiting_external", reconciled["observation"]["state_status"])

        # Crash immediately before release -> finalizing round is recoverable from the durable milestone.
        state_dir, final_claim, final_lease_id = init_claim("WS909")
        code, progress, stderr = self.run_json(
            [
                "continuation",
                "progress",
                str(self.root),
                "--task-id",
                "WS909",
                "--lease-id",
                final_lease_id,
                *self.owner_flags(final_claim),
                "--phase",
                "finalizing",
                "--milestone",
                "pre-release",
                "--evidence-ref",
                "git:clean-checkpoint",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{progress}")
        make_stale(state_dir)
        reconciled = owner_ended_reconcile("WS909")
        self.assertEqual("eligible", reconciled["decision"])
        self.assertEqual("finalizing", reconciled["observation"]["latest_round"]["phase"])
        self.assertEqual("pre-release", reconciled["observation"]["latest_round"]["milestone"])

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

    def test_ws009_ownerless_terminal_evidence_cannot_close_prepared_effect_without_old_fence(
        self,
    ) -> None:
        """Freeze the WS086-class externally proven effect reconciliation deadlock."""
        init = self.init_task("WS910")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS910",
                "--runner-id",
                "expired-effect-owner",
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
                "WS910",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
                "--key",
                "campaign-q03",
                "--kind",
                "runtime-campaign",
                "--external-id",
                "runtime-job-q03-v11",
                "--evidence-ref",
                "runtime:submission-q03-v11",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prepared}")
        self.assertEqual("prepared", prepared["effect"]["status"])

        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        now = continuation._now()
        lease["issued_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_renew_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_heartbeat_at"] = continuation._iso(now - timedelta(minutes=60))
        lease["expires_at"] = continuation._iso(now - timedelta(minutes=1))
        continuation._write_json(lease_path, lease)

        code, rejected_update, _ = self.run_json(
            [
                "continuation",
                "effect",
                "update",
                str(self.root),
                "--task-id",
                "WS910",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
                "--key",
                "campaign-q03",
                "--status",
                "completed",
                "--milestone",
                "collected",
                "--evidence-ref",
                "runtime:60-of-60-collected",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("lease_not_active", rejected_update["error_code"])

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS910",
                "--owner-ended",
                "--evidence-ref",
                "runtime:60-of-60-collected",
                "--reason",
                "Runtime authority proves the deterministic job completed and was collected.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertEqual("blocked", reconciled["decision"])
        self.assertFalse(reconciled["eligible_for_recover"])
        self.assertIn("unresolved_effects", reconciled["reasons"])
        self.assertEqual("expired", reconciled["observation"]["lease_state"])
        self.assertEqual(
            ["campaign-q03"],
            reconciled["observation"]["effect_summary"]["unresolved"],
        )
        self.assertEqual(
            ["runtime:60-of-60-collected"],
            reconciled["evidence_refs"],
        )

        code, denied, _ = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS910",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "new-effect-owner",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("recovery_not_authorized", denied["error_code"])

    def test_ws009_ownerless_terminal_effect_reconciliation_allows_recovery_without_replay(
        self,
    ) -> None:
        """An expired owner may reconcile one existing effect from authoritative terminal evidence."""
        init = self.init_task("WS914")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS914",
                "--runner-id",
                "expired-effect-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        lease_id = str(claim["lease"]["lease_id"])
        owner = ["--lease-id", lease_id, *self.owner_flags(claim)]
        code, prepared, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS914",
                *owner,
                "--key",
                "campaign-q03",
                "--kind",
                "runtime-campaign",
                "--external-id",
                "runtime-job-q03-v11",
                "--evidence-ref",
                "runtime:submission-q03-v11",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prepared}")

        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        now = continuation._now()
        lease["issued_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_renew_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_heartbeat_at"] = continuation._iso(now - timedelta(minutes=60))
        lease["expires_at"] = continuation._iso(now - timedelta(minutes=1))
        continuation._write_json(lease_path, lease)

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS914",
                "--owner-ended",
                "--evidence-ref",
                "scheduler:expired-effect-owner-ended",
                "--effect-key",
                "campaign-q03",
                "--effect-terminal-status",
                "completed",
                "--effect-external-id",
                "runtime-job-q03-v11",
                "--effect-milestone",
                "collected",
                "--effect-evidence-ref",
                "runtime:60-of-60-collected",
                "--reason",
                "Runtime authority proves the existing deterministic job completed and was collected.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertEqual("eligible", reconciled["decision"])
        self.assertTrue(reconciled["eligible_for_recover"])
        self.assertEqual(
            ["campaign-q03"],
            reconciled["observation"]["effect_summary"]["unresolved"],
        )
        self.assertEqual(1, len(reconciled["effect_reconciliations"]))
        effect_assertion = reconciled["effect_reconciliations"][0]
        self.assertEqual("prepared", effect_assertion["observed_status"])
        self.assertEqual("completed", effect_assertion["terminal_status"])
        self.assertEqual("runtime-job-q03-v11", effect_assertion["external_id"])

        code, before_recover, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "list",
                str(self.root),
                "--task-id",
                "WS914",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{before_recover}")
        self.assertEqual("prepared", before_recover["effects"][0]["status"])

        code, recovered, stderr = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS914",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "new-effect-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{recovered}")
        self.assertEqual(["campaign-q03"], recovered["recovery"]["effect_reconciliations"])

        code, after_recover, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "list",
                str(self.root),
                "--task-id",
                "WS914",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{after_recover}")
        effect = after_recover["effects"][0]
        self.assertEqual("completed", effect["status"])
        self.assertEqual("collected", effect["milestone"])
        self.assertIn("runtime:60-of-60-collected", effect["evidence_refs"])
        self.assertIn(
            f"reconcile:{reconciled['receipt']['receipt_id']}",
            effect["evidence_refs"],
        )
        self.assertEqual([], after_recover["summary"]["unresolved"])

    def test_ws009_ownerless_effect_reconciliation_accepts_matching_forfeiture_challenge(
        self,
    ) -> None:
        """A timed-out generation-bound challenge can replace an explicit owner-ended assertion."""
        init = self.init_task("WS917")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS917",
                "--runner-id",
                "effect-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        owner = ["--lease-id", str(claim["lease"]["lease_id"]), *self.owner_flags(claim)]
        code, prepared, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS917",
                *owner,
                "--key",
                "campaign-q03",
                "--kind",
                "runtime-campaign",
                "--external-id",
                "runtime-job-q03-v11",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prepared}")
        code, attempt, stderr = self.run_json(
            [
                "continuation",
                "coordination",
                "attempt",
                str(self.root),
                "--task-id",
                "WS917",
                "--runner-id",
                "effect-contender",
                "--objective-summary",
                "Recover the existing terminal external effect without replay.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{attempt}")
        challenge_id = str(attempt["challenge"]["challenge_id"])
        coordination_path = state_dir / "coordination.json"
        coordination = continuation._read_json(coordination_path, label="coordination")
        coordination["challenges"][0]["opened_at"] = continuation._iso(
            continuation._now() - timedelta(minutes=2)
        )
        coordination["challenges"][0]["deadline_at"] = continuation._iso(
            continuation._now() - timedelta(minutes=1)
        )
        continuation._write_json(coordination_path, coordination)
        code, status, stderr = self.run_json(
            ["continuation", "coordination", "status", str(self.root), "--task-id", "WS917"]
        )
        self.assertEqual(0, code, f"{stderr}\n{status}")
        self.assertEqual([challenge_id], status["timed_out_challenge_ids"])

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS917",
                "--effect-key",
                "campaign-q03",
                "--effect-terminal-status",
                "completed",
                "--effect-external-id",
                "runtime-job-q03-v11",
                "--effect-evidence-ref",
                "runtime:60-of-60-collected",
                "--reason",
                "The matching timed-out challenge forfeits old ownership; external authority proves terminal state.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertTrue(reconciled["eligible_for_recover"])
        self.assertFalse(reconciled["assertions"]["owner_ended"])
        candidates = reconciled["observation"]["ownership_forfeiture_candidates"]
        self.assertEqual([challenge_id], [item["challenge_id"] for item in candidates])
        self.assertEqual("campaign-q03", reconciled["effect_reconciliations"][0]["logical_key"])

    def test_ws009_ownerless_effect_reconciliation_rejects_external_identity_mismatch(
        self,
    ) -> None:
        init = self.init_task("WS915")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS915",
                "--runner-id",
                "expired-effect-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        owner = ["--lease-id", str(claim["lease"]["lease_id"]), *self.owner_flags(claim)]
        code, prepared, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS915",
                *owner,
                "--key",
                "campaign-q03",
                "--kind",
                "runtime-campaign",
                "--external-id",
                "runtime-job-q03-v11",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prepared}")
        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        now = continuation._now()
        lease["issued_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_renew_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_heartbeat_at"] = continuation._iso(now - timedelta(minutes=60))
        lease["expires_at"] = continuation._iso(now - timedelta(minutes=1))
        continuation._write_json(lease_path, lease)

        code, rejected, _ = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS915",
                "--owner-ended",
                "--evidence-ref",
                "scheduler:expired-effect-owner-ended",
                "--effect-key",
                "campaign-q03",
                "--effect-terminal-status",
                "completed",
                "--effect-external-id",
                "runtime-job-q03-v12",
                "--effect-evidence-ref",
                "runtime:60-of-60-collected",
                "--reason",
                "Mismatched runtime identity must not be accepted.",
                "--record",
            ]
        )
        self.assertEqual(2, code)
        self.assertEqual("effect_identity_conflict", rejected["error_code"])

    def test_ws009_ownerless_effect_reconciliation_receipt_fails_closed_on_effect_drift(
        self,
    ) -> None:
        init = self.init_task("WS916")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS916",
                "--runner-id",
                "expired-effect-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        owner = ["--lease-id", str(claim["lease"]["lease_id"]), *self.owner_flags(claim)]
        code, prepared, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS916",
                *owner,
                "--key",
                "campaign-q03",
                "--kind",
                "runtime-campaign",
                "--external-id",
                "runtime-job-q03-v11",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prepared}")
        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        now = continuation._now()
        lease["issued_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_renew_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_heartbeat_at"] = continuation._iso(now - timedelta(minutes=60))
        lease["expires_at"] = continuation._iso(now - timedelta(minutes=1))
        continuation._write_json(lease_path, lease)

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS916",
                "--owner-ended",
                "--evidence-ref",
                "scheduler:expired-effect-owner-ended",
                "--effect-key",
                "campaign-q03",
                "--effect-terminal-status",
                "completed",
                "--effect-external-id",
                "runtime-job-q03-v11",
                "--effect-evidence-ref",
                "runtime:60-of-60-collected",
                "--reason",
                "Record a terminal observation that must stay bound to the observed effect digest.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        effects_path = state_dir / "effects.json"
        effects = json.loads(effects_path.read_text(encoding="utf-8"))
        effects["effects"][0]["milestone"] = "observation-drifted"
        continuation._write_json(effects_path, effects)

        code, denied, _ = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS916",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "new-effect-owner",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("reconciliation_stale", denied["error_code"])

    def test_ws009_unresolved_durable_physical_writer_identity_blocks_recovery(self) -> None:
        """A known long-lived writer identity must stay unresolved until authority proves terminal."""
        init = self.init_task("WS911")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS911",
                "--runner-id",
                "physical-writer-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        lease_id = str(claim["lease"]["lease_id"])
        owner = ["--lease-id", lease_id, *self.owner_flags(claim)]

        code, intent, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "intent",
                str(self.root),
                "--task-id",
                "WS911",
                *owner,
                "--path",
                "writer-output.txt",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{intent}")
        code, prepared, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS911",
                *owner,
                "--key",
                "physical-writer:job-001",
                "--kind",
                "long-lived-local-writer",
                "--external-id",
                "job-001",
                "--evidence-ref",
                "writer:job-001-started",
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
                "WS911",
                *owner,
                "--key",
                "physical-writer:job-001",
                "--status",
                "active",
                "--milestone",
                "writing",
                "--evidence-ref",
                "writer:job-001-running",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{active}")
        (self.root / "writer-output.txt").write_text("writer still active\n", encoding="utf-8")

        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        now = continuation._now()
        lease["issued_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_renew_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_heartbeat_at"] = continuation._iso(now - timedelta(minutes=60))
        lease["expires_at"] = continuation._iso(now - timedelta(minutes=1))
        continuation._write_json(lease_path, lease)

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS911",
                "--owner-ended",
                "--evidence-ref",
                "scheduler:old-owner-ended",
                "--reason",
                "The logical owner ended, but the durable physical-writer identity is not terminal.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertEqual("blocked", reconciled["decision"])
        self.assertFalse(reconciled["eligible_for_recover"])
        self.assertIn("unresolved_effects", reconciled["reasons"])
        self.assertEqual(
            ["physical-writer:job-001"],
            reconciled["observation"]["effect_summary"]["unresolved"],
        )

        code, denied, _ = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS911",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "physical-writer-new-owner",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("recovery_not_authorized", denied["error_code"])

    def test_ws009_terminal_durable_physical_writer_identity_permits_recovery(self) -> None:
        """A terminal durable writer identity may hand attributable output to the next generation."""
        init = self.init_task("WS912")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS912",
                "--runner-id",
                "physical-writer-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        lease_id = str(claim["lease"]["lease_id"])
        owner = ["--lease-id", lease_id, *self.owner_flags(claim)]

        code, intent, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "intent",
                str(self.root),
                "--task-id",
                "WS912",
                *owner,
                "--path",
                "writer-output.txt",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{intent}")
        code, prepared, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "prepare",
                str(self.root),
                "--task-id",
                "WS912",
                *owner,
                "--key",
                "physical-writer:job-002",
                "--kind",
                "long-lived-local-writer",
                "--external-id",
                "job-002",
                "--evidence-ref",
                "writer:job-002-started",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prepared}")
        (self.root / "writer-output.txt").write_text("final writer output\n", encoding="utf-8")
        code, completed, stderr = self.run_json(
            [
                "continuation",
                "effect",
                "update",
                str(self.root),
                "--task-id",
                "WS912",
                *owner,
                "--key",
                "physical-writer:job-002",
                "--status",
                "completed",
                "--milestone",
                "writer-terminal",
                "--evidence-ref",
                "writer:job-002-terminal",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{completed}")

        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        now = continuation._now()
        lease["issued_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_renew_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_heartbeat_at"] = continuation._iso(now - timedelta(minutes=60))
        lease["expires_at"] = continuation._iso(now - timedelta(minutes=1))
        continuation._write_json(lease_path, lease)

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS912",
                "--owner-ended",
                "--evidence-ref",
                "writer:job-002-terminal",
                "--reason",
                "The old owner ended and the durable physical writer is authoritatively terminal.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertEqual("eligible", reconciled["decision"])
        self.assertTrue(reconciled["eligible_for_recover"])
        self.assertEqual(
            ["physical-writer:job-002"],
            reconciled["observation"]["effect_summary"]["terminal"],
        )

        code, recovered, stderr = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS912",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "physical-writer-new-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{recovered}")
        self.assertGreater(int(recovered["generation"]), int(claim["generation"]))
        self.assertEqual(["writer-output.txt"], recovered["workspace"]["task_owned_paths"])
        self.assertFalse(recovered["workspace"]["has_conflicts"])

    def test_ws009_characterizes_unidentified_old_writer_as_indistinguishable_after_recovery(
        self,
    ) -> None:
        """Freeze P0-A: a writer bypassing durable identity can still mutate inherited intent after recovery."""
        init = self.init_task("WS913")
        state_dir = Path(str(init["state_dir"]))
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                "WS913",
                "--runner-id",
                "old-logical-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        lease_id = str(claim["lease"]["lease_id"])
        code, intent, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "intent",
                str(self.root),
                "--task-id",
                "WS913",
                "--lease-id",
                lease_id,
                *self.owner_flags(claim),
                "--path",
                "writer-output.txt",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{intent}")
        (self.root / "writer-output.txt").write_text("old generation initial output\n", encoding="utf-8")

        lease_path = state_dir / "lease.json"
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
        now = continuation._now()
        lease["issued_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_renew_at"] = continuation._iso(now - timedelta(minutes=240))
        lease["last_heartbeat_at"] = continuation._iso(now - timedelta(minutes=60))
        lease["expires_at"] = continuation._iso(now - timedelta(minutes=1))
        continuation._write_json(lease_path, lease)

        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "reconcile",
                str(self.root),
                "--task-id",
                "WS913",
                "--owner-ended",
                "--evidence-ref",
                "scheduler:old-logical-owner-ended",
                "--reason",
                "The logical owner ended; no durable physical-writer identity was registered.",
                "--record",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertTrue(reconciled["eligible_for_recover"], reconciled)
        self.assertEqual([], reconciled["observation"]["effect_summary"]["unresolved"])

        code, recovered, stderr = self.run_json(
            [
                "continuation",
                "recover",
                str(self.root),
                "--task-id",
                "WS913",
                "--reconcile-id",
                str(reconciled["receipt"]["receipt_id"]),
                "--runner-id",
                "new-logical-owner",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{recovered}")

        # Failure injection: an old detached physical writer bypasses ACF after
        # generation N+1 owns the same logical path.  The current workspace
        # classifier only sees the inherited write intent and therefore cannot
        # attribute these bytes to generation N versus N+1.
        (self.root / "writer-output.txt").write_text(
            "late write from old detached physical writer\n",
            encoding="utf-8",
        )
        code, refreshed, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "refresh",
                str(self.root),
                "--task-id",
                "WS913",
                "--lease-id",
                str(recovered["lease"]["lease_id"]),
                *self.owner_flags(recovered),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{refreshed}")
        self.assertFalse(refreshed["workspace"]["has_conflicts"])
        self.assertEqual(["writer-output.txt"], refreshed["workspace"]["task_owned_paths"])
        self.assertEqual(["writer-output.txt"], refreshed["workspace"]["write_intent_paths"])

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
        identity = payload["identity"]
        self.assertIsInstance(identity, dict)
        assert isinstance(identity, dict)
        self.assertEqual("WS900", identity["task_id"])
        self.assertEqual(str(self.root), identity["workspace_root"])
        self.assertEqual("main", identity["branch"])
        self.assertIsNone(identity["workstream_id"])
        wrapper = payload["scheduler_wrapper_contract"]
        self.assertIsInstance(wrapper, dict)
        assert isinstance(wrapper, dict)
        self.assertEqual("acf.continuation.scheduler_wrapper.v1", wrapper["schema_version"])
        self.assertEqual("acf continuation prompt", wrapper["generic_protocol_source"])
        self.assertTrue(wrapper["refresh_prompt_each_run"])
        self.assertFalse(wrapper["copy_generic_state_machine"])
        self.assertEqual(
            ["runtime", "scientific", "permission", "validation"],
            wrapper["project_constraint_classes"],
        )
        self.assertEqual(identity, wrapper["identity"])
        self.assertIn("Do not reconstruct task state from chat history", prompt)
        self.assertIn("acf continuation doctor", prompt)
        self.assertIn("only generic continuation state-machine contract", prompt)
        self.assertIn("Thin-wrapper recipe", prompt)
        self.assertIn("invoke `acf continuation prompt` again on every scheduler wake", prompt)
        self.assertIn("acf continuation coordination attempt", prompt)
        self.assertIn("acf continuation coordination status", prompt)
        self.assertIn("ACF continuation challenge pending", prompt)
        self.assertIn("ownership_forfeiture_candidate", prompt)
        self.assertIn("does not prove the Agent is dead", prompt)
        self.assertIn("acf continuation claim", prompt)
        self.assertIn("acf continuation assert-owner", prompt)
        self.assertIn("heartbeat", prompt)
        self.assertIn("acf continuation progress", prompt)
        self.assertIn("acf continuation workspace status", prompt)
        self.assertIn("acf continuation workspace intent", prompt)
        self.assertIn("acf continuation workspace refresh", prompt)
        self.assertIn("acf continuation effect prepare", prompt)
        self.assertIn("acf continuation effect update", prompt)
        self.assertIn("acf continuation effect list", prompt)
        self.assertIn("long-lived local subprocess", prompt)
        self.assertIn("DevSpace session", prompt)
        self.assertIn("Runtime job", prompt)
        self.assertIn("must not cross an owner lifecycle", prompt)
        self.assertIn("purely read-only/blocking tool call does not need a writer effect identity", prompt)
        self.assertIn("before the next project write or non-idempotent action, re-run `assert-owner`", prompt)
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
