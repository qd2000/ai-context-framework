import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import acf
from ai_context_framework.observability import usage_project_dir


def iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class LogGcTests(unittest.TestCase):
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

    def write_namespace(self, project_root: Path, *, days_ago: int = 365) -> Path:
        directory = usage_project_dir(project_root)
        log_path = directory / "logs" / "usage.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "schema_version": 1,
            "timestamp": iso(days_ago),
            "command": "status",
            "ok": True,
            "project_root": str(project_root.resolve()),
            "context_root": str((project_root / "docs" / "ai").resolve()),
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        return directory

    def gc(self, *extra):
        exit_code, stdout, stderr = self.run_cli(["log", "gc", "--log-root", os.environ["ACF_HOME"], *extra, "--json"])
        self.assertEqual(exit_code, 0, stderr)
        return json.loads(stdout)

    def test_gc_keeps_resolvable_real_project_and_defaults_to_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "real-project"
            context = project / "docs" / "ai"
            self.assertEqual(self.run_cli(["init", str(context), "--profile", "minimal", "--json"])[0], 0)
            directory = self.write_namespace(project, days_ago=3650)

            payload = self.gc()

            self.assertEqual(payload["command"], "log gc")
            self.assertEqual(payload["mode"], "dry_run")
            self.assertEqual(payload["candidate_count"], 0)
            self.assertTrue(directory.exists())
            kept = [row for row in payload["kept"] if row["project_id"] == directory.name]
            self.assertEqual(len(kept), 1)
            self.assertIn("resolvable_real_project_root", kept[0]["blockers"])

    def test_gc_flags_orphan_test_namespace_and_apply_removes_it_with_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "init-status-check"
            project.mkdir(parents=True, exist_ok=True)
            directory = self.write_namespace(project, days_ago=3650)
            self.assertTrue(directory.exists())
            project.rmdir()

            dry_run = self.gc()
            self.assertEqual(dry_run["candidate_count"], 1)
            self.assertEqual(dry_run["removed_count"], 0)
            self.assertEqual(dry_run["candidates"][0]["project_id"], directory.name)
            self.assertIn("missing_project_root", dry_run["candidates"][0]["reasons"])
            self.assertIn("test_like_namespace", dry_run["candidates"][0]["reasons"])
            self.assertTrue(directory.exists(), "dry run must not delete anything")

            applied = self.gc("--apply")
            self.assertEqual(applied["mode"], "apply")
            self.assertEqual(applied["removed_count"], 1)
            self.assertEqual(applied["removed_project_ids"], [directory.name])
            self.assertFalse(directory.exists())
            self.assertIsNotNone(applied["receipt_path"])
            receipt = Path(str(applied["receipt_path"]))
            self.assertTrue(receipt.is_file())
            body = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(body["removed_project_ids"], [directory.name])

    def test_gc_keeps_namespace_with_continuation_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "worklog"
            project.mkdir(parents=True, exist_ok=True)
            directory = self.write_namespace(project, days_ago=3650)
            project.rmdir()
            (directory / "continuation" / "WS001").mkdir(parents=True)

            payload = self.gc()
            self.assertEqual(payload["candidate_count"], 0)
            kept = [row for row in payload["kept"] if row["project_id"] == directory.name]
            self.assertIn("has_continuation_state", kept[0]["blockers"])

    def test_gc_keeps_namespace_with_non_log_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "workstream"
            project.mkdir(parents=True, exist_ok=True)
            directory = self.write_namespace(project, days_ago=3650)
            project.rmdir()
            (directory / "closeout").mkdir(parents=True)

            payload = self.gc()
            self.assertEqual(payload["candidate_count"], 0)
            kept = [row for row in payload["kept"] if row["project_id"] == directory.name]
            self.assertIn("has_non_log_state", kept[0]["blockers"])
            self.assertIn("closeout", kept[0]["non_log_state_entries"])

    def test_gc_respects_retention_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "plan-reference"
            project.mkdir(parents=True, exist_ok=True)
            directory = self.write_namespace(project, days_ago=1)
            project.rmdir()

            payload = self.gc("--retention-days", "30")
            self.assertEqual(payload["candidate_count"], 0)
            kept = [row for row in payload["kept"] if row["project_id"] == directory.name]
            self.assertIn("within_retention_window", kept[0]["blockers"])

            payload = self.gc("--retention-days", "0")
            self.assertEqual(payload["candidate_count"], 1)
            self.assertEqual(payload["candidates"][0]["project_id"], directory.name)
            self.assertTrue(directory.exists())


if __name__ == "__main__":
    unittest.main()
