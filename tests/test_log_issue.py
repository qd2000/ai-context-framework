import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import acf
from ai_context_framework.observability import usage_log_path


class LogIssueLifecycleTests(unittest.TestCase):
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

    def run_json(self, args):
        exit_code, stdout, stderr = self.run_cli(args)
        payload = json.loads(stdout) if stdout.strip() else {}
        return exit_code, payload, stderr

    def append_event(self, project_root, event):
        path = usage_log_path(project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def append_issue(self, project_root, fingerprint, *, text="smoke issue", severity="high"):
        self.append_event(
            project_root,
            {
                "schema_version": 1,
                "timestamp": "2026-06-01T00:00:00Z",
                "event_kind": "continuation_issue",
                "command": "continuation issue",
                "project_root": str(project_root.resolve()),
                "fingerprint": fingerprint,
                "category": "other",
                "severity": severity,
                "text": text,
            },
        )

    def init_project(self, tmp):
        project = Path(tmp) / "project"
        context = project / "docs" / "ai"
        self.assertEqual(self.run_cli(["init", str(context), "--profile", "minimal", "--json"])[0], 0)
        return project

    def test_resolve_then_reopen_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.init_project(tmp)
            fingerprint = "0" * 19 + "1"
            self.append_issue(project, fingerprint)

            exit_code, payload, stderr = self.run_json(
                ["log", "issue", "resolve", fingerprint, "--reason", "fixed in ws014", "--evidence-ref", "commit:abc123", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["status"], "resolved")
            ledger = Path(payload["ledger_path"])
            self.assertTrue(ledger.is_file())
            event = json.loads(ledger.read_text(encoding="utf-8").strip())
            self.assertEqual(event["action"], "resolve")
            self.assertEqual(event["event_kind"], "issue_resolution")
            self.assertEqual(event["evidence_refs"], ["commit:abc123"])

            exit_code, payload, stderr = self.run_json(["log", "issue", "list", str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["issue_count"], 1)
            self.assertEqual(payload["issues"][0]["status"], "resolved")
            self.assertEqual(payload["issues"][0]["resolution_source"], "user_ledger")

            exit_code, payload, stderr = self.run_json(["log", "issues", str(project), "--open-only", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["issue_count"], 0)

            exit_code, _payload, stderr = self.run_json(
                ["log", "issue", "reopen", fingerprint, "--reason", "regressed on main", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            exit_code, payload, stderr = self.run_json(["log", "issues", str(project), "--open-only", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["issue_count"], 1)
            self.assertEqual(payload["issues"][0]["status"], "open")

    def test_supersede_requires_target_and_records_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.init_project(tmp)
            duplicate = "0" * 19 + "2"
            canonical = "0" * 19 + "3"
            self.append_issue(project, duplicate, text="owner-context blocked")
            self.append_issue(project, canonical, text="owner-context blocked")

            exit_code, payload, stderr = self.run_json(
                ["log", "issue", "supersede", duplicate, "--reason", "same root cause", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(payload["error_code"], "issue_invalid_supersede_target")

            exit_code, payload, stderr = self.run_json(
                ["log", "issue", "supersede", duplicate, "--by", canonical, "--reason", "same root cause", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["status"], "superseded")
            self.assertEqual(payload["superseded_by"], canonical)

            exit_code, payload, stderr = self.run_json(["log", "issue", "list", str(project), "--status", "superseded", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["issue_count"], 1)
            self.assertEqual(payload["issues"][0]["superseded_by"], canonical)

    def test_reject_and_dry_run_does_not_write_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.init_project(tmp)
            fingerprint = "0" * 19 + "4"
            self.append_issue(project, fingerprint)

            exit_code, payload, stderr = self.run_json(
                ["log", "issue", "reject", fingerprint, "--reason", "project-specific", "--dry-run", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(payload["dry_run"])
            ledger = Path(payload["ledger_path"])
            self.assertFalse(ledger.exists())

            exit_code, _payload, stderr = self.run_json(
                ["log", "issue", "reject", fingerprint, "--reason", "project-specific, moved to FCC", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            exit_code, payload, stderr = self.run_json(["log", "issue", "show", fingerprint, str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["issue"]["status"], "rejected")

    def test_legacy_resolution_event_remains_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.init_project(tmp)
            fingerprint = "0" * 19 + "5"
            self.append_issue(project, fingerprint)
            self.append_event(
                project,
                {
                    "schema_version": 1,
                    "timestamp": "2026-06-02T00:00:00Z",
                    "event_kind": "continuation_issue_resolution",
                    "command": "continuation issue",
                    "project_root": str(project.resolve()),
                    "fingerprint": fingerprint,
                    "text": "resolved through continuation",
                },
            )

            exit_code, payload, stderr = self.run_json(["log", "issue", "list", str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["issues"][0]["status"], "resolved")
            self.assertNotEqual(payload["issues"][0].get("resolution_source"), "user_ledger")

            exit_code, payload, stderr = self.run_json(["log", "issues", str(project), "--open-only", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["issue_count"], 0)

    def test_invalid_fingerprint_and_missing_issue_report_input_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.init_project(tmp)

            exit_code, payload, stderr = self.run_json(
                ["log", "issue", "resolve", "not-a-fingerprint", "--reason", "x", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(payload["error_code"], "issue_invalid_fingerprint")

            exit_code, payload, stderr = self.run_json(
                ["log", "issue", "show", "f" * 20, str(project), "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(payload["error_code"], "issue_not_found")

    def test_ledger_entry_without_occurrence_is_reported_as_ledger_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.init_project(tmp)
            fingerprint = "0" * 19 + "6"

            exit_code, _payload, stderr = self.run_json(
                ["log", "issue", "reject", fingerprint, "--reason", "recorded before occurrences existed", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)

            exit_code, payload, stderr = self.run_json(["log", "issue", "list", str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["issue_count"], 1)
            self.assertTrue(payload["issues"][0]["ledger_only"])
            self.assertEqual(payload["issues"][0]["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
