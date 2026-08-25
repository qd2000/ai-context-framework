import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import acf
from ai_context_framework.observer import (
    OBSERVER_CURRENT_SCHEMA,
    OBSERVER_LOCK_SCHEMA,
    OBSERVER_MACHINE_STATE_SCHEMA,
    _observation_fingerprint,
    _stable_fingerprint,
    append_jsonl_unique,
    build_observer_snapshot,
    build_alert_lifecycle_events,
    build_unchanged_milestone_observation,
    capture_project_workstreams,
    capture_project_worktrees,
    derive_snapshot_alerts,
    enrich_workstream_machine_states,
    observer_data_age,
    observer_lock_health,
    observer_paths,
    observer_status,
    read_observer_history_stream,
    refresh_history_index,
    resolve_observer_project,
    rotate_jsonl_monthly,
)
from ai_context_framework.observability import usage_project_dir
from ai_context_framework.git_support import discover_git_project, write_registry
from ai_context_framework.observer_storage import render_dashboard_html, semantic_source_fingerprint


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

    def test_registry_managed_workstream_does_not_fallback_to_unrelated_stale_source_after_primary_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, context = self.make_project(root)
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
                "title: Archived observer task\n"
                "---\n"
                "# WS123\n\n"
                "## 目标\n\n"
                "验证 unrelated stale worktree 不会复活已归档 Workstream。\n",
                encoding="utf-8",
            )
            self.init_git_project(project)

            unrelated_worktree = root / "unrelated-worktree"
            subprocess.run(
                ["git", "worktree", "add", "-b", "unrelated", str(unrelated_worktree)],
                cwd=project,
                check=True,
                capture_output=True,
                text=True,
            )
            owner_worktree = root / "owner-worktree"
            subprocess.run(
                ["git", "worktree", "add", "-b", "ws123-owner", str(owner_worktree)],
                cwd=project,
                check=True,
                capture_output=True,
                text=True,
            )

            archive_dir = context / "archive" / "workstreams"
            archive_dir.mkdir(parents=True, exist_ok=True)
            archived_detail = archive_dir / "WS123.md"
            archived_detail.write_text(
                detail.read_text(encoding="utf-8").replace("status: Active", "status: Done"),
                encoding="utf-8",
            )
            detail.unlink()
            subprocess.run(["git", "add", "docs"], cwd=project, check=True)
            subprocess.run(
                ["git", "commit", "-m", "test: archive WS123"],
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
                    "slug": "archived-observer-task",
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
            workstreams = capture_project_workstreams(observer_project, worktrees)

            self.assertNotIn("WS123", {row["id"] for row in workstreams})
            by_path = {Path(str(row["path"])).resolve(): row for row in worktrees}
            self.assertTrue(by_path[unrelated_worktree.resolve()]["observer_scope"])
            self.assertTrue(by_path[unrelated_worktree.resolve()]["registered"])

    def test_non_active_bound_registry_uses_primary_terminal_source_instead_of_stale_bound_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, context = self.make_project(root)
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
                "title: Lifecycle observer task\n"
                "---\n"
                "# WS123\n\n"
                "## 目标\n\n"
                "验证 terminal primary authority。\n",
                encoding="utf-8",
            )
            self.init_git_project(project)

            owner_worktree = root / "owner-worktree"
            subprocess.run(
                ["git", "worktree", "add", "-b", "ws123-owner", str(owner_worktree)],
                cwd=project,
                check=True,
                capture_output=True,
                text=True,
            )
            detail.write_text(
                detail.read_text(encoding="utf-8").replace("status: Active", "status: Done"),
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "docs"], cwd=project, check=True)
            subprocess.run(
                ["git", "commit", "-m", "test: mark WS123 done"],
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
                    "state": "merged",
                    "slug": "lifecycle-observer-task",
                },
            )

            observer_project = resolve_observer_project(project)
            workstreams = capture_project_workstreams(
                observer_project,
                capture_project_worktrees(observer_project),
            )
            workstream = next(row for row in workstreams if row["id"] == "WS123")

            self.assertEqual(workstream["status"], "Done")
            self.assertEqual(Path(str(workstream["selected_source"])).resolve(), project.resolve())
            self.assertEqual(
                {Path(str(row["source_worktree"])).resolve() for row in workstream["sources"]},
                {project.resolve()},
            )

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
            self.assertTrue(paths["alerts"].is_file())
            self.assertTrue(paths["runs"].is_file())
            self.assertTrue(paths["status"].is_file())
            self.assertTrue(paths["history_index"].is_file())
            self.assertTrue(paths["dashboard"].is_file())
            current = json.loads(paths["current"].read_text(encoding="utf-8"))
            self.assertEqual(current["schema_version"], OBSERVER_CURRENT_SCHEMA)
            self.assertEqual(current["snapshot_consistency"]["state"], "stable")
            history_index = json.loads(paths["history_index"].read_text(encoding="utf-8"))
            live_counts = {row["stream"]: row["record_count"] for row in history_index["live_streams"]}
            self.assertEqual(live_counts["runs"], 1)
            self.assertGreaterEqual(live_counts["observations"], 1)
            self.assertEqual(
                history_index["total_record_count"],
                history_index["record_count"] + history_index["live_record_count"],
            )
            after = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))
            self.assertEqual(after, before)

    def test_dashboard_is_self_contained_file_safe_and_secret_safe(self):
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
                "title: Observer dashboard task\n"
                "---\n"
                "# WS123\n\n"
                "## 目标\n\n"
                "验证 dashboard；password=super-secret-value；token=another-secret-value。\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            serialized = json.dumps(payload["snapshot"], ensure_ascii=False)
            self.assertNotIn("super-secret-value", serialized)
            self.assertNotIn("another-secret-value", serialized)
            self.assertIn("[redacted]", serialized)
            paths = observer_paths(resolve_observer_project(project))
            current_text = paths["current"].read_text(encoding="utf-8")
            html = paths["dashboard"].read_text(encoding="utf-8")
            self.assertNotIn("super-secret-value", current_text)
            self.assertNotIn("another-secret-value", current_text)
            self.assertNotIn("super-secret-value", html)
            self.assertNotIn("another-secret-value", html)
            self.assertTrue(html.lower().startswith("<!doctype html>"))
            self.assertIn('type="application/json"', html)
            self.assertIn("observer-data", html)
            self.assertIn("tone-critical", html)
            self.assertIn("Overall Health", html)
            self.assertIn("h1{font-size:24px", html)
            self.assertIn("h3{font-size:17px", html)
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)
            self.assertNotIn("fetch(", html)
            status = json.loads(paths["status"].read_text(encoding="utf-8"))
            self.assertEqual(status["dashboard"]["status"], "success")

    def test_dashboard_renders_human_times_in_beijing_while_embedded_state_stays_utc(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            current = {
                "observed_at": "2026-08-24T01:51:10Z",
                "workstreams": [],
                "alerts": [],
                "semantic": {"status": "current"},
            }
            status = {"data_age": {"state": "fresh"}}
            machine_events = [
                {
                    "observed_at": "2026-08-24T02:00:00Z",
                    "kind": "worktree_head_changed",
                    "canonical_identity": {"id": "WS001"},
                    "before": "abc",
                    "after": "def",
                }
            ]
            interpretations = [
                {
                    "interpreted_at": "2026-08-24T03:00:00Z",
                    "interpretation_version": 1,
                    "workstream_id": "WS001",
                    "human_title": "示例语义更新",
                    "recent_proof": [],
                }
            ]

            html = render_dashboard_html(
                observer_project,
                current=current,
                status=status,
                machine_events=machine_events,
                interpretations=interpretations,
                glossary={"terms": {}},
            )

            visible_html = html.split('<script id="observer-data"', 1)[0]
            self.assertIn("2026-08-24 09:51:10 北京时间 (UTC+08:00)", visible_html)
            self.assertIn("2026-08-24 10:00:00 北京时间 (UTC+08:00)", visible_html)
            self.assertIn("2026-08-24 11:00:00 北京时间 (UTC+08:00)", visible_html)
            self.assertNotIn("2026-08-24T01:51:10Z", visible_html)
            self.assertNotIn("2026-08-24T02:00:00Z", visible_html)
            self.assertNotIn("2026-08-24T03:00:00Z", visible_html)
            self.assertIn('"observed_at": "2026-08-24T01:51:10Z"', html)

    def test_dashboard_render_failure_preserves_last_good_file_and_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            paths = observer_paths(observer_project)
            paths["dashboard"].parent.mkdir(parents=True, exist_ok=True)
            paths["dashboard"].write_text("LAST GOOD DASHBOARD", encoding="utf-8")

            with patch("ai_context_framework.observer.write_dashboard", side_effect=RuntimeError("render boom")):
                exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["run"]["dashboard_render_status"], "failed")
            self.assertEqual(paths["dashboard"].read_text(encoding="utf-8"), "LAST GOOD DASHBOARD")
            status_payload = observer_status(observer_project)
            self.assertEqual(status_payload["self_health"]["dashboard"]["status"], "failed")
            alert_keys = {row["alert_key"] for row in status_payload["self_health_alerts"]}
            self.assertIn("observer:dashboard-render-failed", alert_keys)

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
                "pid": os.getpid(),
                "started_at": "2026-08-21T00:00:00Z",
            }
            paths["lock"].write_text(json.dumps(lock_payload), encoding="utf-8")

            exit_code, stdout, _stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])

            self.assertEqual(exit_code, 3)
            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], "observer_locked")
            self.assertEqual(payload["lock_owner"]["run_id"], "other-run")
            self.assertTrue(payload["overlap_detected"])
            self.assertEqual(payload["lock_health"]["state"], "active")
            self.assertEqual(json.loads(paths["lock"].read_text(encoding="utf-8"))["run_id"], "other-run")
            self.assertFalse(paths["current"].exists())

    def test_confidently_abandoned_observer_lock_is_recovered_and_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            paths = observer_paths(observer_project)
            paths["lock"].parent.mkdir(parents=True, exist_ok=True)
            paths["lock"].write_text(
                json.dumps(
                    {
                        "schema_version": OBSERVER_LOCK_SCHEMA,
                        "project_id": observer_project.project_id,
                        "run_id": "abandoned-run",
                        "pid": 2147483647,
                        "started_at": "2020-01-01T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            with patch("ai_context_framework.observer_storage._process_is_alive", return_value=False):
                exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["run"]["stale_lock_recovered"])
            self.assertEqual(payload["run"]["recovered_lock_owner"]["run_id"], "abandoned-run")
            self.assertFalse(paths["lock"].exists())
            self.assertTrue(paths["current"].is_file())

    def test_monthly_rotation_is_lossless_idempotent_and_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            paths = observer_paths(observer_project)
            paths["timeline"].parent.mkdir(parents=True, exist_ok=True)
            old_event = {
                "event_id": "event-old",
                "observed_at": "2020-01-15T00:00:00Z",
                "kind": "workstream_discovered",
            }
            current_event = {
                "event_id": "event-current",
                "observed_at": "2020-02-15T00:00:00Z",
                "kind": "workstream_status_changed",
            }
            paths["timeline"].write_text(
                json.dumps(old_event) + "\n" + json.dumps(current_event) + "\n",
                encoding="utf-8",
            )

            first = rotate_jsonl_monthly(
                paths["timeline"],
                paths["history"],
                stream_name="timeline",
                timestamp_field="observed_at",
                id_field="event_id",
                current_month="2020-02",
            )
            second = rotate_jsonl_monthly(
                paths["timeline"],
                paths["history"],
                stream_name="timeline",
                timestamp_field="observed_at",
                id_field="event_id",
                current_month="2020-02",
            )
            index = refresh_history_index(observer_project)

            self.assertEqual(first[0]["records_moved"], 1)
            self.assertEqual(second, [])
            live_rows = [json.loads(line) for line in paths["timeline"].read_text(encoding="utf-8").splitlines() if line]
            shard = paths["history"] / "timeline" / "2020-01.jsonl"
            shard_rows = [json.loads(line) for line in shard.read_text(encoding="utf-8").splitlines() if line]
            self.assertEqual([row["event_id"] for row in live_rows], ["event-current"])
            self.assertEqual([row["event_id"] for row in shard_rows], ["event-old"])
            self.assertEqual(index["shard_count"], 1)
            self.assertEqual(index["record_count"], 1)
            self.assertEqual(index["live_record_count"], 1)
            self.assertEqual(index["total_record_count"], 2)
            self.assertTrue(paths["history_index"].is_file())
            rebuilt = read_observer_history_stream(observer_project, "timeline")
            self.assertEqual([row["event_id"] for row in rebuilt], ["event-old", "event-current"])

    def test_atomic_jsonl_append_isolates_interrupted_tail_without_losing_new_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            paths = observer_paths(resolve_observer_project(project))
            paths["timeline"].parent.mkdir(parents=True, exist_ok=True)
            paths["timeline"].write_text('{"event_id":"interrupted"', encoding="utf-8")

            appended = append_jsonl_unique(
                paths["timeline"],
                {
                    "event_id": "event-valid",
                    "observed_at": "2026-08-21T00:00:00Z",
                    "kind": "workstream_discovered",
                },
                id_field="event_id",
            )

            self.assertTrue(appended)
            text = paths["timeline"].read_text(encoding="utf-8")
            self.assertTrue(text.startswith('{"event_id":"interrupted"\n'))
            self.assertIn('"event_id": "event-valid"', text)
            rebuilt = read_observer_history_stream(resolve_observer_project(project), "timeline")
            self.assertEqual([row["event_id"] for row in rebuilt], ["event-valid"])

    def test_data_age_uses_observed_run_cadence_instead_of_assuming_scheduler_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            paths = observer_paths(resolve_observer_project(project))
            paths["runs"].parent.mkdir(parents=True, exist_ok=True)
            runs = [
                {"run_id": "r1", "status": "success", "started_at": "2020-01-01T00:00:00Z"},
                {"run_id": "r2", "status": "success", "started_at": "2020-01-01T01:00:00Z"},
                {"run_id": "r3", "status": "success", "started_at": "2020-01-01T02:00:00Z"},
            ]
            paths["runs"].write_text("".join(json.dumps(row) + "\n" for row in runs), encoding="utf-8")
            current = {"observed_at": "2020-01-01T02:00:00Z"}

            age = observer_data_age(current, paths["runs"])

            self.assertEqual(age["expected_interval_seconds"], 3600.0)
            self.assertEqual(age["cadence_sample_count"], 2)
            self.assertEqual(age["stale_after_seconds"], 7200.0)
            self.assertEqual(age["critical_after_seconds"], 21600.0)
            self.assertEqual(age["state"], "critical")

    def test_data_age_keeps_learned_cadence_after_runs_rotate(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            paths = observer_paths(resolve_observer_project(project))
            shard = paths["history"] / "runs" / "2020-01.jsonl"
            shard.parent.mkdir(parents=True, exist_ok=True)
            runs = [
                {"run_id": "r1", "status": "success", "started_at": "2020-01-01T00:00:00Z"},
                {"run_id": "r2", "status": "success", "started_at": "2020-01-01T01:00:00Z"},
                {"run_id": "r3", "status": "success", "started_at": "2020-01-01T02:00:00Z"},
            ]
            shard.write_text("".join(json.dumps(row) + "\n" for row in runs), encoding="utf-8")
            paths["runs"].parent.mkdir(parents=True, exist_ok=True)
            paths["runs"].write_text("", encoding="utf-8")
            current = {"observed_at": "2020-01-01T02:00:00Z"}

            age = observer_data_age(current, paths["runs"], paths["history"])

            self.assertEqual(age["expected_interval_seconds"], 3600.0)
            self.assertEqual(age["cadence_sample_count"], 2)

    def test_snapshot_consistency_ignores_derived_heartbeat_age(self):
        first = {
            "continuations": [
                {
                    "task_id": "WS123",
                    "lease": {
                        "present": True,
                        "liveness": {
                            "state": "fresh",
                            "heartbeat_age_seconds": 10.0,
                            "expires_at": "2026-08-21T03:00:00Z",
                        },
                    },
                }
            ]
        }
        second = json.loads(json.dumps(first))
        second["continuations"][0]["lease"]["liveness"]["heartbeat_age_seconds"] = 11.5

        self.assertEqual(_stable_fingerprint(first), _stable_fingerprint(second))

    def test_snapshot_retries_once_and_reports_critical_when_source_never_stabilizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            captures = [
                {"worktrees": [], "workstreams": [], "continuations": [], "marker": 1},
                {"worktrees": [], "workstreams": [], "continuations": [], "marker": 2},
                {"worktrees": [], "workstreams": [], "continuations": [], "marker": 3},
            ]

            with patch("ai_context_framework.observer._capture_project_facts", side_effect=captures):
                snapshot = build_observer_snapshot(observer_project)

            consistency = snapshot["snapshot_consistency"]
            self.assertEqual(consistency["state"], "unstable")
            self.assertEqual(consistency["attempts"], 3)
            self.assertNotEqual(consistency["first_fingerprint"], consistency["second_fingerprint"])
            self.assertNotEqual(consistency["second_fingerprint"], consistency["final_fingerprint"])
            self.assertEqual(snapshot["alerts"][0]["alert_key"], "project:snapshot-consistency-unstable")
            self.assertEqual(snapshot["alerts"][0]["severity"], "critical")

    def test_divergent_workstream_sources_warn_machine_health_and_raise_critical_alert(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            workstream = {
                "id": "WS123",
                "status": "Active",
                "source_consistency": "divergent",
                "sources": [
                    {"detail_path": "primary/docs/ai/active/workstreams/WS123.md"},
                    {"detail_path": "worktree/docs/ai/active/workstreams/WS123.md"},
                ],
            }
            enriched = enrich_workstream_machine_states([workstream], [])[0]
            self.assertEqual(enriched["machine_state"]["health"], "warning")
            self.assertIn("workstream_sources_divergent", enriched["machine_state"]["health_reasons"])
            alerts = derive_snapshot_alerts(
                observer_project,
                {
                    "observed_at": "2026-08-21T00:00:00Z",
                    "snapshot_consistency": {"state": "stable"},
                    "workstreams": [enriched],
                    "continuations": [],
                    "worktrees": [],
                },
            )
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["alert_key"], "workstream:WS123:source-divergent")
            self.assertEqual(alerts[0]["severity"], "critical")

    def test_active_workstream_with_nonactive_registry_warns_and_surfaces_lifecycle_alert(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            workstream = {
                "id": "WS123",
                "status": "Active",
                "source_consistency": "consistent",
                "registry": {
                    "state": "merged",
                    "path": str(project / "linked-worktree"),
                    "branch": "codex/ws123",
                },
            }

            enriched = enrich_workstream_machine_states([workstream], [])[0]

            self.assertEqual(enriched["machine_state"]["health"], "warning")
            self.assertIn("workstream_registry_not_active", enriched["machine_state"]["health_reasons"])
            alerts = derive_snapshot_alerts(
                observer_project,
                {
                    "observed_at": "2026-08-21T00:00:00Z",
                    "snapshot_consistency": {"state": "stable"},
                    "workstreams": [enriched],
                    "continuations": [],
                    "worktrees": [],
                },
            )
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["alert_key"], "workstream:WS123:registry-lifecycle-mismatch")
            self.assertEqual(alerts[0]["severity"], "warning")
            self.assertEqual(alerts[0]["provenance"][0]["registry_state"], "merged")

            terminal = {**workstream, "status": "Done"}
            terminal_enriched = enrich_workstream_machine_states([terminal], [])[0]
            self.assertEqual(terminal_enriched["machine_state"]["health"], "healthy")
            terminal_alerts = derive_snapshot_alerts(
                observer_project,
                {
                    "observed_at": "2026-08-21T00:00:00Z",
                    "snapshot_consistency": {"state": "stable"},
                    "workstreams": [terminal_enriched],
                    "continuations": [],
                    "worktrees": [],
                },
            )
            self.assertEqual(terminal_alerts, [])

    def test_unchanged_progress_records_sparse_milestone_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            paths = observer_paths(observer_project)
            paths["observations"].parent.mkdir(parents=True, exist_ok=True)
            current_at = datetime.now(timezone.utc)
            anchor_at = current_at - timedelta(hours=7)
            current = {
                "observed_at": current_at.isoformat().replace("+00:00", "Z"),
                "snapshot_consistency": {"final_fingerprint": "snapshot-fp"},
                "workstreams": [],
                "continuations": [],
                "worktrees": [],
            }
            fingerprint = _observation_fingerprint(current)
            anchor = {
                "schema_version": "acf.observer.observation.v1",
                "project_id": observer_project.project_id,
                "observation_id": "observation-anchor",
                "observed_at": anchor_at.isoformat().replace("+00:00", "Z"),
                "current_fingerprint": fingerprint,
            }
            paths["observations"].write_text(json.dumps(anchor) + "\n", encoding="utf-8")

            milestone = build_unchanged_milestone_observation(observer_project, current)
            self.assertIsNotNone(milestone)
            assert milestone is not None
            self.assertEqual(milestone["observation_kind"], "unchanged_milestone")
            self.assertEqual(milestone["milestone_seconds"], 6 * 60 * 60)
            self.assertTrue(append_jsonl_unique(paths["observations"], milestone, id_field="observation_id"))
            self.assertIsNone(build_unchanged_milestone_observation(observer_project, current))

    def test_snapshot_alert_lifecycle_opens_and_resolves_machine_alerts(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            base = {
                "revision": 1,
                "observed_at": "2026-08-21T00:00:00Z",
                "snapshot_consistency": {"state": "unstable"},
                "workstreams": [],
                "continuations": [],
                "worktrees": [],
            }
            current = dict(base)
            current["alerts"] = derive_snapshot_alerts(observer_project, current)
            opened = build_alert_lifecycle_events(observer_project, None, current)

            self.assertEqual(len(current["alerts"]), 1)
            self.assertEqual(current["alerts"][0]["severity"], "critical")
            self.assertEqual(opened[0]["kind"], "opened")

            resolved_snapshot = {
                **base,
                "revision": 2,
                "observed_at": "2026-08-21T01:00:00Z",
                "snapshot_consistency": {"state": "stable"},
                "alerts": [],
            }
            resolved = build_alert_lifecycle_events(observer_project, current, resolved_snapshot)
            self.assertEqual(len(resolved), 1)
            self.assertEqual(resolved[0]["kind"], "resolved")

    def test_inflight_effect_under_fresh_owner_is_not_health_alert_but_stale_active_effect_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            fresh_continuation = {
                "task_id": "WS123",
                "workstream_id": "WS123",
                "status": "running",
                "lease": {"present": True, "liveness": {"state": "fresh"}},
                "effects": {"status_counts": {"active": 1}, "unresolved_count": 1},
            }
            workstream = {
                "id": "WS123",
                "status": "Active",
                "source_consistency": "consistent",
            }
            enriched = enrich_workstream_machine_states([workstream], [fresh_continuation])[0]
            self.assertEqual(enriched["machine_state"]["health"], "healthy")
            self.assertIn("effects_in_flight:1", enriched["machine_state"]["signals"])
            fresh_snapshot = {
                "observed_at": "2026-08-21T00:00:00Z",
                "snapshot_consistency": {"state": "stable"},
                "workstreams": [enriched],
                "continuations": [fresh_continuation],
                "worktrees": [],
            }
            self.assertEqual(derive_snapshot_alerts(observer_project, fresh_snapshot), [])

            stale_continuation = {
                **fresh_continuation,
                "lease": {"present": True, "liveness": {"state": "stale"}},
            }
            stale_enriched = enrich_workstream_machine_states([workstream], [stale_continuation])[0]
            self.assertEqual(stale_enriched["machine_state"]["health"], "critical")
            stale_snapshot = {
                **fresh_snapshot,
                "workstreams": [stale_enriched],
                "continuations": [stale_continuation],
            }
            alerts = derive_snapshot_alerts(observer_project, stale_snapshot)
            self.assertEqual(len(alerts), 2)
            effect_alert = next(row for row in alerts if row["alert_key"].endswith(":unresolved-effects"))
            self.assertEqual(effect_alert["severity"], "critical")
            self.assertEqual(effect_alert["provenance"][0]["risk_reason"], "active_effect_without_fresh_owner")

    def test_running_continuation_liveness_changes_health_without_changing_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            workstream = {"id": "WS123", "status": "Active", "source_consistency": "consistent"}
            base = {
                "task_id": "WS123",
                "workstream_id": "WS123",
                "status": "running",
                "effects": {"status_counts": {"completed": 1}, "unresolved_count": 0},
            }

            fresh = {**base, "lease": {"present": True, "liveness": {"state": "fresh"}}}
            fresh_ws = enrich_workstream_machine_states([workstream], [fresh])[0]
            self.assertEqual(fresh_ws["machine_state"]["execution"], "running")
            self.assertEqual(fresh_ws["machine_state"]["health"], "healthy")

            stale = {
                **base,
                "lease": {
                    "present": True,
                    "liveness": {
                        "state": "stale",
                        "heartbeat_age_seconds": 1800,
                        "stale_after_seconds": 1500,
                    },
                },
            }
            stale_ws = enrich_workstream_machine_states([workstream], [stale])[0]
            self.assertEqual(stale_ws["machine_state"]["execution"], "running")
            self.assertEqual(stale_ws["machine_state"]["health"], "warning")
            self.assertIn("continuation_owner_stale", stale_ws["machine_state"]["health_reasons"])
            alerts = derive_snapshot_alerts(
                observer_project,
                {
                    "observed_at": "2026-08-21T00:00:00Z",
                    "snapshot_consistency": {"state": "stable"},
                    "workstreams": [stale_ws],
                    "continuations": [stale],
                    "worktrees": [],
                },
            )
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["severity"], "warning")
            self.assertEqual(alerts[0]["alert_key"], "continuation:WS123:owner-liveness")
            self.assertEqual(alerts[0]["provenance"][0]["reason"], "continuation_owner_stale")

            expired = {
                **base,
                "lease": {"present": True, "liveness": {"state": "expired", "expires_at": "2026-08-21T00:00:00Z"}},
            }
            expired_ws = enrich_workstream_machine_states([workstream], [expired])[0]
            self.assertEqual(expired_ws["machine_state"]["execution"], "running")
            self.assertEqual(expired_ws["machine_state"]["health"], "critical")
            expired_alerts = derive_snapshot_alerts(
                observer_project,
                {
                    "observed_at": "2026-08-21T00:00:00Z",
                    "snapshot_consistency": {"state": "stable"},
                    "workstreams": [expired_ws],
                    "continuations": [expired],
                    "worktrees": [],
                },
            )
            self.assertEqual(expired_alerts[0]["severity"], "critical")
            self.assertEqual(expired_alerts[0]["provenance"][0]["reason"], "continuation_lease_expired")

    def test_semantic_interpretation_is_versioned_bound_to_facts_and_stale_after_fact_change(self):
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
                "title: Semantic task\n"
                "---\n"
                "# WS123\n\n"
                "## 目标\n\n"
                "把机器事实解释成人类进展。\n",
                encoding="utf-8",
            )
            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--dry-run", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            source = json.loads(stdout)["snapshot"]["workstreams"][0]["semantic"]["source_fingerprint"]
            args = [
                "observer", "interpret", str(project),
                "--workstream", "WS123",
                "--source-fingerprint", source,
                "--human-title", "语义观察任务",
                "--current-focus", "建立可审计的人类进展解释。",
                "--why-now", "机器状态已经稳定，下一步必须验证语义层不会覆盖事实。",
                "--recent-proof", "Observer snapshot 已能稳定读取 Workstream。",
                "--implication", "可以在不修改项目事实源的前提下增加解释缓存。",
                "--next-step", "验证解释版本、来源绑定和陈旧检测。",
                "--confidence", "low",
                "--provenance", "docs/ai/active/workstreams/WS123.md",
            ]
            exit_code, stdout, stderr = self.run_cli(args + ["--json"])
            self.assertEqual(exit_code, 0, stderr)
            applied = json.loads(stdout)
            self.assertTrue(applied["changed"])
            self.assertEqual(applied["interpretation"]["interpretation_version"], 1)
            self.assertNotIn("progress_percent", applied["interpretation"])

            exit_code, stdout, stderr = self.run_cli(args + ["--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertFalse(json.loads(stdout)["changed"])
            project_model = resolve_observer_project(project)
            history = Path(observer_paths(project_model)["interpretations"]).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(history), 1)
            exit_code, stdout, stderr = self.run_cli(
                ["observer", "history", str(project), "--stream", "interpretations", "--limit", "10", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            history_payload = json.loads(stdout)
            self.assertEqual(history_payload["total_count"], 1)
            self.assertEqual(history_payload["records"][0]["event_kind"], "semantic_interpretation_updated")

            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--dry-run", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            semantic = json.loads(stdout)["snapshot"]["workstreams"][0]["semantic"]
            self.assertEqual(semantic["status"], "current")
            self.assertEqual(semantic["interpretation"]["human_title"], "语义观察任务")
            self.assertEqual(semantic["interpretation"]["confidence"], "low")
            self.assertEqual(semantic["interpretation"]["confidence_notice"], "暂译/当前理解")

            detail.write_text(detail.read_text(encoding="utf-8").replace("status: Active", "status: Blocked"), encoding="utf-8")
            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--dry-run", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            changed_semantic = json.loads(stdout)["snapshot"]["workstreams"][0]["semantic"]
            self.assertEqual(changed_semantic["status"], "stale")
            self.assertNotEqual(changed_semantic["source_fingerprint"], source)
            exit_code, stdout, _stderr = self.run_cli(args + ["--json"])
            self.assertNotEqual(exit_code, 0)
            mismatch = json.loads(stdout)
            self.assertEqual(mismatch["error_code"], "observer_semantic_source_changed")

    def test_semantic_source_fingerprint_changes_when_unresolved_effect_risk_changes(self):
        workstream = {
            "id": "WS123",
            "title": "Semantic task",
            "status": "Active",
            "attention": "Now",
            "goal": "Explain progress",
            "source_consistency": "consistent",
            "machine_state": {"execution": "running", "health": "healthy", "health_reasons": ["no_machine_warning_detected"]},
        }
        base = {
            "task_id": "WS123",
            "workstream_id": "WS123",
            "stage": "C04",
            "status": "running",
            "next_action": "Continue",
            "objective": "Explain progress",
            "latest_round": {"phase": "claimed", "milestone": "claimed", "evidence_refs": []},
        }
        before = {**base, "effects": {"status_counts": {"completed": 2}, "unresolved_count": 0}}
        during = {**base, "effects": {"status_counts": {"completed": 2, "prepared": 1}, "unresolved_count": 1}}

        self.assertNotEqual(
            semantic_source_fingerprint(workstream, [before]),
            semantic_source_fingerprint(workstream, [during]),
        )

    def test_semantic_source_fingerprint_ignores_terminal_effect_count_growth(self):
        workstream = {
            "id": "WS123",
            "title": "Semantic task",
            "status": "Active",
            "attention": "Now",
            "goal": "Explain progress",
            "source_consistency": "consistent",
            "machine_state": {"execution": "running", "health": "healthy", "health_reasons": ["no_machine_warning_detected"]},
        }
        base = {
            "task_id": "WS123",
            "workstream_id": "WS123",
            "stage": "C04",
            "status": "running",
            "next_action": "Continue",
            "objective": "Explain progress",
            "latest_round": {"generation": 7, "phase": "claimed", "milestone": "claimed", "evidence_refs": []},
        }
        before = {**base, "effects": {"status_counts": {"completed": 2}, "unresolved_count": 0}}
        after = {**base, "effects": {"status_counts": {"completed": 3}, "unresolved_count": 0}}

        self.assertEqual(
            semantic_source_fingerprint(workstream, [before]),
            semantic_source_fingerprint(workstream, [after]),
        )

    def test_semantic_source_fingerprint_changes_when_continuation_generation_changes(self):
        workstream = {
            "id": "WS123",
            "title": "Semantic task",
            "status": "Active",
            "attention": "Now",
            "goal": "Explain progress",
            "source_consistency": "consistent",
            "machine_state": {"execution": "running", "health": "healthy", "health_reasons": ["no_machine_warning_detected"]},
        }
        base = {
            "task_id": "WS123",
            "workstream_id": "WS123",
            "stage": "C04",
            "status": "running",
            "next_action": "Continue",
            "objective": "Explain progress",
            "effects": {"status_counts": {"completed": 2}, "unresolved_count": 0},
        }
        generation_7 = {
            **base,
            "latest_round": {"generation": 7, "phase": "claimed", "milestone": "claimed", "evidence_refs": []},
        }
        generation_8 = {
            **base,
            "latest_round": {"generation": 8, "phase": "claimed", "milestone": "claimed", "evidence_refs": []},
        }

        self.assertNotEqual(
            semantic_source_fingerprint(workstream, [generation_7]),
            semantic_source_fingerprint(workstream, [generation_8]),
        )

    def test_glossary_set_is_user_level_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            args = [
                "observer", "glossary-set", str(project),
                "--term", "LM/TR",
                "--human-term", "LM/信赖域优化",
                "--explanation", "利用局部模型和信赖域约束优化步长的方法。",
                "--confidence", "high",
                "--provenance", "docs/ai/reference/optimization.md",
                "--json",
            ]
            exit_code, stdout, stderr = self.run_cli(args)
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["changed"])
            self.assertEqual(payload["glossary"]["terms"]["LM/TR"]["human_term"], "LM/信赖域优化")
            exit_code, stdout, stderr = self.run_cli(args)
            self.assertEqual(exit_code, 0, stderr)
            self.assertFalse(json.loads(stdout)["changed"])
            exit_code, stdout, stderr = self.run_cli(["observer", "glossary", str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            glossary_payload = json.loads(stdout)
            self.assertEqual(glossary_payload["term_count"], 1)
            self.assertEqual(glossary_payload["glossary"]["terms"]["LM/TR"]["canonical_term"], "LM/TR")
            project_model = resolve_observer_project(project)
            self.assertTrue(observer_paths(project_model)["glossary"].is_file())
            self.assertTrue(observer_paths(project_model)["glossary"].is_relative_to(Path(os.environ["ACF_HOME"])))

    def test_semantic_write_refuses_credential_like_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            exit_code, stdout, _stderr = self.run_cli(
                [
                    "observer", "glossary-set", str(project),
                    "--term", "unsafe",
                    "--human-term", "unsafe",
                    "--explanation", "password=super-secret-value",
                    "--confidence", "low",
                    "--provenance", "test",
                    "--json",
                ]
            )
            self.assertNotEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["error_code"], "observer_sensitive_value_refused")
            project_model = resolve_observer_project(project)
            self.assertFalse(observer_paths(project_model)["glossary"].exists())

    def test_project_narrative_is_versioned_source_bound_and_rendered_as_project_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, _context = self.make_project(root)
            source_path = "AGENTS.md"
            exit_code, stdout, stderr = self.run_cli(
                ["observer", "narrative-source", str(project), "--source-path", source_path, "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            source_payload = json.loads(stdout)
            source_fingerprint = source_payload["source_fingerprint"]
            self.assertEqual(source_payload["source_projection"]["sources"][0]["path"], source_path)

            narrative_input = root / "project-narrative.json"
            narrative_input.write_text(
                json.dumps(
                    {
                        "confidence": "authoritative",
                        "overall_goal": {
                            "summary": "让项目级 Observer 同时解释长期目标、架构、逻辑里程碑和当前位置。",
                            "provenance": ["AGENTS.md"],
                        },
                        "architecture": {
                            "nodes": [
                                {
                                    "id": "authority",
                                    "title": "项目 Authority",
                                    "category": "authority",
                                    "status": "completed",
                                    "summary": "Markdown 与运行事实提供 canonical authority。",
                                    "provenance": ["AGENTS.md"],
                                },
                                {
                                    "id": "observer",
                                    "title": "Project Observer",
                                    "category": "observability",
                                    "status": "current",
                                    "summary": "Observer 将 authority 转换为可追溯的人类语义。",
                                    "provenance": ["AGENTS.md"],
                                },
                            ],
                            "edges": [
                                {
                                    "from": "authority",
                                    "to": "observer",
                                    "relation": "interpreted_by",
                                    "summary": "Observer 只解释 authority，不替代它。",
                                    "provenance": ["AGENTS.md"],
                                }
                            ],
                        },
                        "milestones": [
                            {
                                "id": "foundation",
                                "title": "Observer 基础能力",
                                "status": "completed",
                                "depends_on": [],
                                "next": ["project-map"],
                                "summary": "完成 snapshot、semantic、history 和 static Dashboard。",
                                "implication": "可以继续构建长期项目地图。",
                                "evidence": ["AGENTS.md"],
                                "provenance": ["AGENTS.md"],
                            },
                            {
                                "id": "project-map",
                                "title": "Project Narrative / Map",
                                "status": "current",
                                "depends_on": ["foundation"],
                                "next": [],
                                "summary": "把长期项目逻辑链加入 Dashboard。",
                                "implication": "用户无需只靠最近 Timeline 理解项目。",
                                "evidence": ["AGENTS.md"],
                                "provenance": ["AGENTS.md"],
                            },
                        ],
                        "current_position": {
                            "milestone_id": "project-map",
                            "summary": "当前正在实现长期项目地图。",
                            "next_logic": "验证 source fingerprint、历史和静态 HTML 安全。",
                            "provenance": ["AGENTS.md"],
                        },
                        "provenance": ["AGENTS.md"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            apply_args = [
                "observer",
                "narrative-apply",
                str(project),
                "--source-fingerprint",
                source_fingerprint,
                "--source-path",
                source_path,
                "--input",
                str(narrative_input),
                "--json",
            ]
            exit_code, stdout, stderr = self.run_cli(apply_args)
            self.assertEqual(exit_code, 0, stderr)
            applied = json.loads(stdout)
            self.assertTrue(applied["changed"])
            self.assertEqual(applied["narrative"]["narrative_version"], 1)

            exit_code, stdout, stderr = self.run_cli(apply_args)
            self.assertEqual(exit_code, 0, stderr)
            self.assertFalse(json.loads(stdout)["changed"])
            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            snapshot = json.loads(stdout)["snapshot"]
            self.assertEqual(snapshot["project_narrative"]["status"], "current")
            observer_project = resolve_observer_project(project)
            html = observer_paths(observer_project)["dashboard"].read_text(encoding="utf-8")
            self.assertIn("Project Narrative / 项目地图", html)
            self.assertIn("Architecture Map / 架构地图", html)
            self.assertIn("Logical Milestone Flow / Project Evolution", html)
            self.assertIn("Current Position / 当前所在位置", html)
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)
            self.assertNotIn("fetch(", html)

            exit_code, stdout, stderr = self.run_cli(
                ["observer", "history", str(project), "--stream", "narratives", "--limit", "10", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            history = json.loads(stdout)
            self.assertEqual(history["total_count"], 1)
            self.assertEqual(history["records"][0]["event_kind"], "project_narrative_updated")

            agents = project / source_path
            agents.write_text(agents.read_text(encoding="utf-8") + "\n# authority changed\n", encoding="utf-8")
            exit_code, stdout, stderr = self.run_cli(["observer", "narrative", str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            narrative_status = json.loads(stdout)["project_narrative"]
            self.assertEqual(narrative_status["status"], "stale")
            self.assertNotEqual(narrative_status["source_fingerprint"], source_fingerprint)
            exit_code, stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--dry-run", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            alerts = json.loads(stdout)["snapshot"]["alerts"]
            self.assertIn("project:narrative-stale", [row["alert_key"] for row in alerts])

    def test_project_narrative_refuses_sensitive_or_invalid_graph_input_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, _context = self.make_project(root)
            exit_code, stdout, stderr = self.run_cli(
                ["observer", "narrative-source", str(project), "--source-path", "AGENTS.md", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            fingerprint = json.loads(stdout)["source_fingerprint"]
            input_path = root / "unsafe-narrative.json"
            input_path.write_text(
                json.dumps(
                    {
                        "confidence": "high",
                        "overall_goal": {"summary": "password=do-not-store", "provenance": ["AGENTS.md"]},
                        "architecture": {
                            "nodes": [
                                {
                                    "id": "one",
                                    "title": "One",
                                    "category": "test",
                                    "status": "current",
                                    "summary": "safe",
                                    "provenance": ["AGENTS.md"],
                                }
                            ],
                            "edges": [{"from": "one", "to": "missing", "relation": "bad", "summary": "bad", "provenance": ["AGENTS.md"]}],
                        },
                        "milestones": [
                            {
                                "id": "m1",
                                "title": "M1",
                                "status": "current",
                                "depends_on": [],
                                "next": [],
                                "summary": "safe",
                                "implication": "safe",
                                "evidence": ["AGENTS.md"],
                                "provenance": ["AGENTS.md"],
                            }
                        ],
                        "current_position": {"milestone_id": "m1", "summary": "safe", "next_logic": "safe", "provenance": ["AGENTS.md"]},
                        "provenance": ["AGENTS.md"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            exit_code, stdout, _stderr = self.run_cli(
                [
                    "observer", "narrative-apply", str(project),
                    "--source-fingerprint", fingerprint,
                    "--source-path", "AGENTS.md",
                    "--input", str(input_path),
                    "--json",
                ]
            )
            self.assertNotEqual(exit_code, 0)
            self.assertIn(json.loads(stdout)["error_code"], {"observer_sensitive_value_refused", "observer_project_narrative_invalid"})
            observer_project = resolve_observer_project(project)
            self.assertFalse(observer_paths(observer_project)["project_narrative"].exists())
            self.assertFalse(observer_paths(observer_project)["project_narratives"].exists())

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
            self.assertEqual(payload["self_health"]["last_run_status"], "success")
            self.assertIsInstance(payload["self_health"]["data_age"], dict)

    def test_status_reports_latest_failure_and_abandoned_lock_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _context = self.make_project(Path(tmp))
            observer_project = resolve_observer_project(project)
            paths = observer_paths(observer_project)
            paths["current"].parent.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc)
            paths["current"].write_text(
                json.dumps({"observed_at": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")}),
                encoding="utf-8",
            )
            paths["status"].write_text(
                json.dumps(
                    {
                        "last_success": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
                        "last_failure": (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                        "last_run_status": "failed",
                        "errors": ["synthetic failure"],
                    }
                ),
                encoding="utf-8",
            )
            lock_payload = {
                "schema_version": OBSERVER_LOCK_SCHEMA,
                "project_id": observer_project.project_id,
                "run_id": "dead-run",
                "pid": 2147483647,
                "started_at": "2020-01-01T00:00:00Z",
            }
            paths["lock"].write_text(json.dumps(lock_payload), encoding="utf-8")
            before = paths["lock"].read_bytes()

            with patch("ai_context_framework.observer_storage._process_is_alive", return_value=False):
                payload = observer_status(observer_project)

            self.assertEqual(payload["lock_health"]["state"], "abandoned")
            keys = {row["alert_key"] for row in payload["self_health_alerts"]}
            self.assertIn("observer:last-run-failed", keys)
            self.assertIn("observer:abandoned-lock", keys)
            self.assertEqual(paths["lock"].read_bytes(), before)

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
