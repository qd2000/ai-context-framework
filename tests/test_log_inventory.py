import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import acf
from ai_context_framework.observability import usage_log_path, usage_project_dir


class LogInventoryTests(unittest.TestCase):
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

    def run_cli_output(self, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = acf.main(args)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def append_event(self, project_root, event):
        path = usage_log_path(project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def test_log_projects_summarizes_legacy_and_resolved_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            context = project / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.append_event(
                project,
                {
                    "schema_version": 1,
                    "timestamp": "2026-06-09T00:00:00Z",
                    "command": "check",
                    "ok": True,
                    "exit_code": 0,
                    "context_rel": "docs/ai",
                    "cwd_rel": ".",
                },
            )
            log_root = Path(os.environ["ACF_HOME"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["log", "projects", "--log-root", str(log_root), "--scan-root", str(tmp), "--include-unresolved", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "log projects")
            self.assertTrue(payload["ok"])
            self.assertGreaterEqual(payload["raw_project_count"], 1)
            self.assertGreaterEqual(payload["resolved_context_count"], 1)
            resolved = [item for item in payload["projects"] if item["classification"] == "resolved_context"]
            self.assertTrue(resolved)
            self.assertEqual(resolved[0]["context_root"], str(context.resolve()))
            self.assertEqual(resolved[0]["project_id"], usage_project_dir(project).name)

    def test_log_projects_resolves_new_event_paths_without_scan_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            context = project / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.append_event(
                project,
                {
                    "schema_version": 1,
                    "timestamp": "2026-06-09T00:00:00Z",
                    "command": "status",
                    "ok": True,
                    "project_root": str(project.resolve()),
                    "context_root": str(context.resolve()),
                },
            )
            log_root = Path(os.environ["ACF_HOME"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["log", "projects", "--log-root", str(log_root), "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["schema_version"], 1)
            self.assertIsNone(payload["error_code"])
            self.assertGreaterEqual(payload["resolved_context_count"], 1)
            resolved = [item for item in payload["projects"] if item["classification"] == "resolved_context"]
            self.assertEqual(resolved[0]["context_root"], str(context.resolve()))

    def test_log_projects_prefers_real_docs_context_over_template_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            context = project / "docs" / "ai"
            template_context = project / "template"
            self.assertEqual(self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])[0], 0)
            self.assertEqual(self.run_cli_output(["init", str(template_context), "--profile", "minimal", "--json"])[0], 0)
            self.append_event(
                project,
                {
                    "schema_version": 1,
                    "timestamp": "2026-06-09T00:00:00Z",
                    "command": "status",
                    "ok": True,
                },
            )
            log_root = Path(os.environ["ACF_HOME"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["log", "projects", "--log-root", str(log_root), "--scan-root", str(project), "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["resolved_context_count"], 1)
            self.assertEqual(payload["projects"][0]["classification"], "resolved_context")
            self.assertEqual(payload["projects"][0]["context_root"], str(context.resolve()))

    def test_log_projects_min_events_filters_list_not_raw_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            one_event = Path(tmp) / "one"
            two_events = Path(tmp) / "two"
            self.append_event(one_event, {"schema_version": 1, "timestamp": "2026-06-09T00:00:00Z", "command": "status", "ok": True})
            self.append_event(two_events, {"schema_version": 1, "timestamp": "2026-06-09T00:00:00Z", "command": "status", "ok": True})
            self.append_event(two_events, {"schema_version": 1, "timestamp": "2026-06-09T00:00:01Z", "command": "check", "ok": False, "error_code": "check_failed"})
            log_root = Path(os.environ["ACF_HOME"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["log", "projects", "--log-root", str(log_root), "--min-events", "2", "--include-unresolved", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["raw_project_count"], 2)
            self.assertEqual(payload["classification_counts"]["unresolved_log"], 2)
            self.assertEqual(len(payload["projects"]), 1)
            self.assertEqual(payload["projects"][0]["event_count"], 2)

    def test_log_projects_hides_unresolved_synthetic_and_missing_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            unresolved = Path(tmp) / "realish"
            missing = Path(tmp) / "deleted"
            synthetic = Path(tmp) / "acf-upgrade-matrix-demo"
            self.append_event(unresolved, {"schema_version": 1, "timestamp": "2026-06-09T00:00:00Z", "command": "status", "ok": True})
            self.append_event(
                missing,
                {
                    "schema_version": 1,
                    "timestamp": "2026-06-09T00:00:01Z",
                    "command": "status",
                    "ok": True,
                    "project_root": str((Path(tmp) / "missing-project").resolve()),
                    "context_root": str((Path(tmp) / "missing-project" / "docs" / "ai").resolve()),
                },
            )
            self.append_event(synthetic, {"schema_version": 1, "timestamp": "2026-06-09T00:00:02Z", "command": "status", "ok": True})
            log_root = Path(os.environ["ACF_HOME"])

            exit_code, stdout, stderr = self.run_cli_output(["log", "projects", "--log-root", str(log_root), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["raw_project_count"], 3)
            self.assertEqual(payload["classification_counts"]["unresolved_log"], 1)
            self.assertEqual(payload["classification_counts"]["missing_path"], 1)
            self.assertEqual(payload["classification_counts"]["synthetic_or_test_like"], 1)
            self.assertEqual(payload["projects"], [])

            exit_code, stdout, stderr = self.run_cli_output(
                ["log", "projects", "--log-root", str(log_root), "--include-unresolved", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            classifications = {item["classification"] for item in payload["projects"]}
            self.assertIn("missing_path", classifications)
            self.assertIn("synthetic_or_test_like", classifications)
            self.assertIn("unresolved_log", classifications)

    def test_log_projects_classifies_archive_temp_context_and_scan_only_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_context = Path(tmp) / "90-archive" / "TEMP" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(archive_context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            log_root = Path(os.environ["ACF_HOME"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["log", "projects", "--log-root", str(log_root), "--scan-root", str(tmp), "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["projects"][0]["classification"], "archive_or_temp_context")
            self.assertEqual(payload["resolved_context_count"], 0)

            clean_project = Path(tmp) / "clean"
            clean_context = clean_project / "docs" / "ai"
            self.assertEqual(self.run_cli_output(["init", str(clean_context), "--profile", "minimal", "--json"])[0], 0)
            exit_code, stdout, stderr = self.run_cli_output(
                ["log", "projects", "--log-root", str(log_root), "--scan-root", str(clean_project), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertGreaterEqual(payload["resolved_context_count"], 1)


if __name__ == "__main__":
    unittest.main()
