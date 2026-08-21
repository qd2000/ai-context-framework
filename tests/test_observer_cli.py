import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import acf
from ai_context_framework.observer import (
    OBSERVER_CURRENT_SCHEMA,
    OBSERVER_LOCK_SCHEMA,
    OBSERVER_MACHINE_STATE_SCHEMA,
    capture_project_workstreams,
    capture_project_worktrees,
    observer_paths,
    resolve_observer_project,
)
from ai_context_framework.observability import usage_project_dir
from ai_context_framework.git_support import discover_git_project, write_registry


class ObserverCliTests(unittest.TestCase):
    def setUp(self):
        self._previous_acf_home = os.environ.get("ACF_HOME")
        self._acf_home_dir = tempfile.TemporaryDirectory()
        os.environ["ACF_HOME"] = self._acf_home_dir.name

    def tearDown(self):
        if self._previous_acf_home is None:
            os.environ.pop("ACF_HOME", None)
        else:
            os.environ["ACF_HOME"] = self._previous_acf_home
        self._acf_home_dir.cleanup()

    def run_cli(self, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = acf.main(args)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def make_project(self, root: Path) -> tuple[Path, Path]:
        project = root / "project"
        context = project / "docs" / "ai"
        exit_code, _stdout, stderr = self.run_cli(["init", str(context), "--profile", "minimal", "--json"])
        self.assertEqual(exit_code, 0, stderr)
        return project, context

    def init_git_project(self, project: Path) -> None:
        subprocess.run(["git", "init", "-b", "main"], cwd=project, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "observer-tests@example.invalid"], cwd=project, check=True)
        subprocess.run(["git", "config", "user.name", "Observer Tests"], cwd=project, check=True)
        subprocess.run(["git", "add", "AGENTS.md", "docs"], cwd=project, check=True)
        subprocess.run(["git", "commit", "-m", "test: initialize observer project"], cwd=project, check=True, capture_output=True, text=True)

    def test_status_before_snapshot_is_read_only_and_reports_user_state_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            before = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))

            exit_code, stdout, stderr = self.run_cli(["observer", "status", str(project), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], "observer status")
            self.assertFalse(payload["initialized"])
            self.assertEqual(payload["changed_files"], [])
            self.assertTrue(Path(payload["observer_dir"]).is_relative_to(Path(os.environ["ACF_HOME"])))
            after = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))
            self.assertEqual(after, before)

    def test_snapshot_dry_run_does_not_create_observer_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            self.assertFalse(observer_project.observer_dir.exists())

    def test_linked_worktree_invocation_uses_canonical_primary_project_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, context = self.make_project(root)
            self.init_git_project(project)
            linked = root / "linked"
            subprocess.run(
                ["git", "worktree", "add", "-b", "observer-linked", str(linked)],
                cwd=project,
                check=True,
                capture_output=True,
                text=True,
            )

            primary_observer = resolve_observer_project(project)
            linked_observer = resolve_observer_project(linked)

            self.assertEqual(linked_observer.canonical_root, project.resolve())
            self.assertEqual(linked_observer.context_root, context.resolve())
            self.assertEqual(linked_observer.project_id, primary_observer.project_id)
            self.assertEqual(linked_observer.observer_dir, primary_observer.observer_dir)
            self.assertEqual(linked_observer.invocation_root, linked.resolve())

    def test_registry_scopes_semantic_sources_but_retains_unregistered_worktree_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, context = self.make_project(root)
            detail_dir = context / "active" / "workstreams"
            detail_dir.mkdir(parents=True, exist_ok=True)
            (detail_dir / "WS123.md").write_text(
                "---\n"
                "id: WS123\n"
                "type: Task\n"
                "status: Active\n"
                "attention: Now\n"
                "owner: agent\n"
                "title: Registry-scoped observer task\n"
                "---\n"
                "# WS123\n\n"
                "## 目标\n\n"
                "验证临时 Git worktree 不会污染项目语义来源。\n",
                encoding="utf-8",
            )
            self.init_git_project(project)

            owner_worktree = root / "owner-worktree"
            unrelated_worktree = root / "unrelated-worktree"
            transient_worktree = root / "transient-worktree"
            for branch, target in (
                ("ws123-owner", owner_worktree),
                ("unrelated", unrelated_worktree),
                ("transient", transient_worktree),
            ):
                subprocess.run(
                    ["git", "worktree", "add", "-b", branch, str(target)],
                    cwd=project,
                    check=True,
                    capture_output=True,
                    text=True,
                )

            git_project = discover_git_project(project)
            write_registry(
                git_project.common_dir,
                "WS123",
                {
                    "workstream": "WS123",
                    "branch": "ws123-owner",
                    "path": str(owner_worktree),
                    "state": "active",
                    "slug": "registry-scoped-observer-task",
                },
            )
            write_registry(
                git_project.common_dir,
                "bugfix:unrelated",
                {
                    "workstream": None,
                    "branch": "unrelated",
                    "path": str(unrelated_worktree),
                    "state": "active",
                    "slug": "unrelated",
                },
            )

            observer_project = resolve_observer_project(project)
            worktrees = capture_project_worktrees(observer_project)
            by_path = {Path(str(row["path"])).resolve(): row for row in worktrees}
            self.assertTrue(by_path[project.resolve()]["observer_scope"])
            self.assertTrue(by_path[owner_worktree.resolve()]["observer_scope"])
            self.assertTrue(by_path[unrelated_worktree.resolve()]["observer_scope"])
            self.assertFalse(by_path[transient_worktree.resolve()]["observer_scope"])
            self.assertFalse(by_path[transient_worktree.resolve()]["registered"])

            workstreams = capture_project_workstreams(observer_project, worktrees)
            workstream = next(row for row in workstreams if row["id"] == "WS123")
            semantic_source_paths = {
                Path(str(row["source_worktree"])).resolve()
                for row in workstream["sources"]
            }
            self.assertEqual(
                semantic_source_paths,
                {project.resolve(), owner_worktree.resolve()},
            )

            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--dry-run", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["snapshot"]["schema_version"], OBSERVER_CURRENT_SCHEMA)
            self.assertEqual(payload["snapshot"]["project_id"], observer_project.project_id)
            self.assertFalse(observer_project.observer_dir.exists())

    def test_snapshot_writes_only_user_level_observer_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            before = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))

            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["dry_run"])
            self.assertEqual(payload["changed_files"], [])
            paths = observer_paths(resolve_observer_project(project))
            self.assertTrue(paths["current"].is_file())
            self.assertTrue(paths["timeline"].is_file())
            self.assertTrue(paths["observations"].is_file())
            self.assertTrue(paths["runs"].is_file())
            self.assertTrue(paths["status"].is_file())
            current = json.loads(paths["current"].read_text(encoding="utf-8"))
            self.assertEqual(current["schema_version"], OBSERVER_CURRENT_SCHEMA)
            self.assertEqual(current["snapshot_consistency"]["state"], "stable")
            after = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))
            self.assertEqual(after, before)

    def test_repeated_snapshot_appends_liveness_without_copying_current_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            self.assertEqual(self.run_cli(["observer", "snapshot", str(project), "--json"])[0], 0)
            self.assertEqual(self.run_cli(["observer", "snapshot", str(project), "--json"])[0], 0)
            paths = observer_paths(resolve_observer_project(project))

            run_lines = [line for line in paths["runs"].read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(run_lines), 2)
            observation_lines = [
                line
                for line in paths["observations"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(observation_lines), 1)
            self.assertTrue(paths["current"].is_file())
            self.assertFalse((paths["root"] / "history" / "snapshot-1.json").exists())

            first_run = json.loads(run_lines[0])
            second_run = json.loads(run_lines[1])
            self.assertTrue(first_run["observation_recorded"])
            self.assertFalse(second_run["observation_recorded"])

    def test_existing_observer_lock_fails_closed_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            paths = observer_paths(observer_project)
            paths["lock"].parent.mkdir(parents=True, exist_ok=True)
            lock_payload = {
                "schema_version": OBSERVER_LOCK_SCHEMA,
                "project_id": observer_project.project_id,
                "run_id": "other-run",
                "pid": 123,
                "started_at": "2026-08-21T00:00:00Z",
            }
            paths["lock"].write_text(json.dumps(lock_payload), encoding="utf-8")

            exit_code, stdout, _stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])

            self.assertEqual(exit_code, 3)
            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], "observer_locked")
            self.assertEqual(payload["lock_owner"]["run_id"], "other-run")
            self.assertEqual(json.loads(paths["lock"].read_text(encoding="utf-8"))["run_id"], "other-run")
            self.assertFalse(paths["current"].exists())

    def test_status_after_snapshot_reports_self_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            self.assertEqual(self.run_cli(["observer", "snapshot", str(project), "--json"])[0], 0)

            exit_code, stdout, stderr = self.run_cli(["observer", "status", str(project), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["initialized"])
            self.assertEqual(payload["self_health"]["errors"], [])
            self.assertIsNotNone(payload["self_health"]["last_success"])

    def test_snapshot_reads_workstream_detail_without_modifying_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, context = self.make_project(Path(tmp))
            detail_dir = context / "active" / "workstreams"
            detail_dir.mkdir(parents=True, exist_ok=True)
            detail = detail_dir / "WS123.md"
            detail.write_text(
                "---\n"
                "id: WS123\n"
                "type: Task\n"
                "status: Active\n"
                "attention: Now\n"
                "owner: agent\n"
                "title: Observer test task\n"
                "---\n"
                "# WS123\n\n"
                "## 目标\n\n"
                "验证 Observer 能读取 Workstream 语义入口。\n\n"
                "---\n\n"
                "## 当前发现\n\n"
                "无。\n",
                encoding="utf-8",
            )
            before = detail.read_bytes()

            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["snapshot"]["workstream_count"], 1)
            workstream = payload["snapshot"]["workstreams"][0]
            self.assertEqual(workstream["id"], "WS123")
            self.assertEqual(workstream["status"], "Active")
            self.assertIn("读取 Workstream", workstream["goal"])
            self.assertNotIn("---", workstream["goal"])
            self.assertEqual(workstream["machine_state"]["schema_version"], OBSERVER_MACHINE_STATE_SCHEMA)
            self.assertEqual(workstream["machine_state"]["execution"], "idle")
            self.assertEqual(workstream["machine_state"]["progress"], "unknown")
            self.assertEqual(workstream["machine_state"]["health"], "healthy")
            self.assertEqual(detail.read_bytes(), before)

    def test_snapshot_reads_continuation_directly_and_redacts_owner_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            task_dir = usage_project_dir(project) / "continuation" / "WS123"
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "control.json").write_text(
                json.dumps(
                    {
                        "schema_version": "acf.continuation.control.v1",
                        "task_id": "WS123",
                        "workstream_id": "WS123",
                        "title": "Test continuation",
                        "objective": "Observe safely",
                    }
                ),
                encoding="utf-8",
            )
            (task_dir / "state.json").write_text(
                json.dumps(
                    {
                        "schema_version": "acf.continuation.state.v1",
                        "task_id": "WS123",
                        "objective": "Observe safely",
                        "stage": "C04",
                        "status": "running",
                        "next_action": "Continue",
                        "updated_at": "2026-08-21T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            (task_dir / "lease.json").write_text(
                json.dumps(
                    {
                        "schema_version": "acf.continuation.lease.v1",
                        "lease_id": "do-not-copy-lease-id",
                        "fence_token": "super-secret-fence-token",
                        "runner_id": "runner-a",
                        "generation": 4,
                        "issued_at": "2026-08-21T00:00:00Z",
                        "expires_at": "2026-08-21T03:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            (task_dir / "rounds.json").write_text(
                json.dumps(
                    {
                        "schema_version": "acf.continuation.round-journal.v1",
                        "task_id": "WS123",
                        "rounds": [
                            {
                                "schema_version": "acf.continuation.round.v1",
                                "generation": 4,
                                "lease_id": "do-not-copy-round-lease-id",
                                "runner_id": "runner-a",
                                "phase": "waiting_external",
                                "milestone": "waiting-runtime",
                                "evidence_refs": ["runtime/job-123"],
                                "started_at": "2026-08-21T00:00:00Z",
                                "updated_at": "2026-08-21T00:10:00Z",
                                "ended_at": None,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            before_control_bytes = {
                path.name: path.read_bytes()
                for path in task_dir.iterdir()
                if path.is_file()
            }

            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["snapshot"]["continuation_count"], 1)
            continuation = payload["snapshot"]["continuations"][0]
            self.assertEqual(continuation["workstream_id"], "WS123")
            self.assertEqual(continuation["lease"]["runner_id"], "runner-a")
            self.assertEqual(continuation["latest_round"]["phase"], "waiting_external")
            self.assertEqual(continuation["latest_round"]["milestone"], "waiting-runtime")
            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("super-secret-fence-token", serialized)
            self.assertNotIn("do-not-copy-lease-id", serialized)
            self.assertNotIn("do-not-copy-round-lease-id", serialized)
            after_control_bytes = {
                path.name: path.read_bytes()
                for path in task_dir.iterdir()
                if path.is_file()
            }
            self.assertEqual(after_control_bytes, before_control_bytes)

    def test_workstream_machine_state_distinguishes_external_wait_from_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, context = self.make_project(Path(tmp))
            detail_dir = context / "active" / "workstreams"
            detail_dir.mkdir(parents=True, exist_ok=True)
            (detail_dir / "WS123.md").write_text(
                "---\n"
                "id: WS123\n"
                "type: Task\n"
                "status: Active\n"
                "attention: Now\n"
                "owner: agent\n"
                "title: Waiting task\n"
                "---\n"
                "# WS123\n\n"
                "## 目标\n\n"
                "等待外部任务并继续。\n",
                encoding="utf-8",
            )
            task_dir = usage_project_dir(project) / "continuation" / "WS123"
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "control.json").write_text(
                json.dumps({"task_id": "WS123", "workstream_id": "WS123", "title": "Waiting task"}),
                encoding="utf-8",
            )
            (task_dir / "state.json").write_text(
                json.dumps({"task_id": "WS123", "status": "running", "stage": "C04"}),
                encoding="utf-8",
            )
            (task_dir / "rounds.json").write_text(
                json.dumps(
                    {
                        "rounds": [
                            {
                                "generation": 1,
                                "runner_id": "runner-a",
                                "phase": "waiting_external",
                                "milestone": "waiting-job",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            workstream = payload["snapshot"]["workstreams"][0]
            machine = workstream["machine_state"]
            self.assertEqual(machine["execution"], "waiting_external")
            self.assertEqual(machine["progress"], "unknown")
            self.assertEqual(machine["health"], "healthy")
            self.assertEqual(machine["progress_basis"], "history_not_evaluated")

    def test_meaningful_history_records_status_change_without_full_snapshot_duplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, context = self.make_project(Path(tmp))
            detail_dir = context / "active" / "workstreams"
            detail_dir.mkdir(parents=True, exist_ok=True)
            detail = detail_dir / "WS123.md"
            detail.write_text(
                "---\n"
                "id: WS123\n"
                "type: Task\n"
                "status: Active\n"
                "attention: Now\n"
                "owner: agent\n"
                "title: History task\n"
                "---\n"
                "# WS123\n\n"
                "## 目标\n\n"
                "验证 meaningful history。\n",
                encoding="utf-8",
            )
            self.assertEqual(self.run_cli(["observer", "snapshot", str(project), "--json"])[0], 0)
            detail.write_text(detail.read_text(encoding="utf-8").replace("status: Active", "status: Blocked"), encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertGreaterEqual(payload["run"]["meaningful_event_count"], 2)
            paths = observer_paths(resolve_observer_project(project))
            events = [json.loads(line) for line in paths["timeline"].read_text(encoding="utf-8").splitlines() if line.strip()]
            status_events = [event for event in events if event["kind"] == "workstream_status_changed"]
            self.assertEqual(len(status_events), 1)
            self.assertEqual(status_events[0]["before"], "Active")
            self.assertEqual(status_events[0]["after"], "Blocked")
            execution_events = [event for event in events if event["kind"] == "workstream_execution_changed"]
            self.assertEqual(len(execution_events), 1)
            self.assertEqual(execution_events[0]["before"], "idle")
            self.assertEqual(execution_events[0]["after"], "blocked")
            observations = [
                json.loads(line)
                for line in paths["observations"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(observations), 2)

    def test_lease_heartbeat_timestamp_change_does_not_create_project_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, context = self.make_project(Path(tmp))
            detail_dir = context / "active" / "workstreams"
            detail_dir.mkdir(parents=True, exist_ok=True)
            (detail_dir / "WS123.md").write_text(
                "---\n"
                "id: WS123\n"
                "type: Task\n"
                "status: Active\n"
                "attention: Now\n"
                "owner: agent\n"
                "title: Heartbeat task\n"
                "---\n"
                "# WS123\n\n"
                "## 目标\n\n"
                "验证 heartbeat 不污染进展历史。\n",
                encoding="utf-8",
            )
            task_dir = usage_project_dir(project) / "continuation" / "WS123"
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "control.json").write_text(
                json.dumps({"task_id": "WS123", "workstream_id": "WS123", "title": "Heartbeat task"}),
                encoding="utf-8",
            )
            (task_dir / "state.json").write_text(
                json.dumps({"task_id": "WS123", "status": "running", "stage": "C04", "next_action": "Continue"}),
                encoding="utf-8",
            )
            lease_path = task_dir / "lease.json"
            lease = {
                "runner_id": "runner-a",
                "generation": 1,
                "issued_at": "2026-08-21T00:00:00Z",
                "last_heartbeat_at": "2026-08-21T00:00:00Z",
                "expires_at": "2026-08-21T03:00:00Z",
            }
            lease_path.write_text(json.dumps(lease), encoding="utf-8")
            self.assertEqual(self.run_cli(["observer", "snapshot", str(project), "--json"])[0], 0)

            lease["last_heartbeat_at"] = "2026-08-21T00:10:00Z"
            lease_path.write_text(json.dumps(lease), encoding="utf-8")
            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertFalse(payload["run"]["observation_recorded"])
            self.assertEqual(payload["run"]["meaningful_event_count"], 0)
            paths = observer_paths(resolve_observer_project(project))
            observations = [
                line
                for line in paths["observations"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(observations), 1)

    def test_repeated_identical_transition_keeps_each_meaningful_occurrence(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, context = self.make_project(Path(tmp))
            detail_dir = context / "active" / "workstreams"
            detail_dir.mkdir(parents=True, exist_ok=True)
            detail = detail_dir / "WS123.md"
            detail.write_text(
                "---\n"
                "id: WS123\n"
                "type: Task\n"
                "status: Active\n"
                "attention: Now\n"
                "owner: agent\n"
                "title: Repeated transition task\n"
                "---\n"
                "# WS123\n\n"
                "## 目标\n\n"
                "验证重复状态迁移不会丢失历史。\n",
                encoding="utf-8",
            )

            self.assertEqual(self.run_cli(["observer", "snapshot", str(project), "--json"])[0], 0)
            detail.write_text(detail.read_text(encoding="utf-8").replace("status: Active", "status: Blocked"), encoding="utf-8")
            self.assertEqual(self.run_cli(["observer", "snapshot", str(project), "--json"])[0], 0)
            detail.write_text(detail.read_text(encoding="utf-8").replace("status: Blocked", "status: Active"), encoding="utf-8")
            self.assertEqual(self.run_cli(["observer", "snapshot", str(project), "--json"])[0], 0)
            detail.write_text(detail.read_text(encoding="utf-8").replace("status: Active", "status: Blocked"), encoding="utf-8")
            self.assertEqual(self.run_cli(["observer", "snapshot", str(project), "--json"])[0], 0)

            paths = observer_paths(resolve_observer_project(project))
            events = [
                json.loads(line)
                for line in paths["timeline"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            active_to_blocked = [
                event
                for event in events
                if event["kind"] == "workstream_status_changed"
                and event["before"] == "Active"
                and event["after"] == "Blocked"
            ]
            self.assertEqual(len(active_to_blocked), 2)
            self.assertNotEqual(active_to_blocked[0]["event_id"], active_to_blocked[1]["event_id"])
            self.assertNotEqual(
                active_to_blocked[0]["occurrence_anchor"],
                active_to_blocked[1]["occurrence_anchor"],
            )


if __name__ == "__main__":
    unittest.main()
