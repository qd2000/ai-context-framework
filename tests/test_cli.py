import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import acf


class CliTests(unittest.TestCase):
    def run_cli(self, args):
        with redirect_stdout(io.StringIO()):
            return acf.main(args)

    def test_standard_template_check_passes_with_placeholder_warnings(self):
        result = acf.check_context(acf.TEMPLATE_DIR, "standard", strict=False)
        self.assertFalse(result.errors)
        self.assertTrue(result.warnings)

    def test_strict_template_check_fails_on_placeholders(self):
        result = acf.check_context(acf.TEMPLATE_DIR, "standard", strict=True)
        self.assertTrue(any("placeholder" in error for error in result.errors))

    def test_init_minimal_creates_checkable_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            exit_code = self.run_cli(["init", str(target), "--profile", "minimal"])
            self.assertEqual(exit_code, 0)
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_check_detects_missing_required_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "AGENTS.md").unlink()
            result = acf.check_context(target, "minimal", strict=False)
            self.assertIn("missing file: AGENTS.md", result.errors)

    def test_check_detects_invalid_task_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            task_file = target / "active" / "Current_Task.md"
            text = task_file.read_text(encoding="utf-8").replace("Empty", "Started", 1)
            task_file.write_text(text, encoding="utf-8")
            result = acf.check_context(target, "minimal", strict=False)
            self.assertTrue(any("valid current task status" in error for error in result.errors))

    def test_check_detects_decision_status_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            decision_file = target / "decisions" / "ADR-0001.md"
            decision_file.write_text(
                "ADR\n## 状态\n\nRejected\n\n## 日期\n\n2026-04-26\n",
                encoding="utf-8",
            )
            index_file = target / "reference" / "Decisions_Index.md"
            index_file.write_text(
                "| ID | 标题 | 状态 | 摘要 | 详情 |\n"
                "|---|---|---|---|---|\n"
                "| ADR-0001 | Test | Active | Summary | `decisions/ADR-0001.md` |\n",
                encoding="utf-8",
            )
            result = acf.check_context(target, "minimal", strict=False)
            self.assertTrue(any("status mismatch" in error for error in result.errors))

    def test_check_detects_worklog_date_path_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            index_file = target / "worklog" / "Worklog_Index.md"
            index_file.write_text(
                "| 日期 | 摘要 | 关键结论 | 详情 |\n"
                "|---|---|---|---|\n"
                "| 2026-04-26 | Test | None | `worklog/daily/2026-04-25.md` |\n",
                encoding="utf-8",
            )
            (target / "worklog" / "daily" / "2026-04-25.md").write_text("test", encoding="utf-8")
            result = acf.check_context(target, "minimal", strict=False)
            self.assertTrue(any("does not match date" in error for error in result.errors))

    def test_strict_ignores_explicit_template_placeholder_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            replacements = {
                "AGENTS.md": "入口\n",
                "active/Context.md": "当前事实\n",
                "active/Current_Task.md": "## 当前任务状态\n\nEmpty\n",
                "rules/Always_Active.md": "规则\n",
                "rules/Project_Rules.md": "规则\n",
                "reference/Project_Brief.md": "项目背景\n",
                "reference/Decisions_Index.md": "| ID | 标题 | 状态 | 摘要 | 详情 |\n|---|---|---|---|---|\n| 暂无 | | | | |\n",
                "reference/Sources_Index.md": "| 资料 | 状态 | 摘要 |\n|---|---|---|\n| 暂无 | | |\n",
                "worklog/Worklog_Index.md": "| 日期 | 摘要 | 关键结论 | 详情 |\n|---|---|---|---|\n| 暂无 | | | |\n",
            }
            for rel_path, content in replacements.items():
                (target / rel_path).write_text(content, encoding="utf-8")

            result = acf.check_context(target, "minimal", strict=True)
            self.assertFalse(result.errors)

    def test_new_worklog_creates_daily_file_and_index_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            exit_code = self.run_cli(
                [
                    "new",
                    "worklog",
                    str(target),
                    "--date",
                    "2026-04-27",
                    "--summary",
                    "Implemented | worklog command.",
                    "--conclusion",
                    "Worklog maintenance is now automated.",
                ]
            )
            self.assertEqual(exit_code, 0)

            daily_file = target / "worklog" / "daily" / "2026-04-27.md"
            self.assertTrue(daily_file.exists())
            self.assertIn("Implemented | worklog command.", daily_file.read_text(encoding="utf-8"))

            index_text = (target / "worklog" / "Worklog_Index.md").read_text(encoding="utf-8")
            self.assertIn("| 2026-04-27 | Implemented / worklog command.", index_text)
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_new_worklog_refuses_existing_daily_file_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            args = [
                "new",
                "worklog",
                str(target),
                "--date",
                "2026-04-27",
                "--summary",
                "Initial worklog.",
            ]
            self.run_cli(args)
            with self.assertRaises(SystemExit):
                self.run_cli(args)

    def test_new_worklog_force_updates_existing_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(
                [
                    "new",
                    "worklog",
                    str(target),
                    "--date",
                    "2026-04-27",
                    "--summary",
                    "Initial worklog.",
                ]
            )
            self.run_cli(
                [
                    "new",
                    "worklog",
                    str(target),
                    "--date",
                    "2026-04-27",
                    "--summary",
                    "Updated worklog.",
                    "--force",
                ]
            )
            index_text = (target / "worklog" / "Worklog_Index.md").read_text(encoding="utf-8")
            self.assertIn("Updated worklog.", index_text)
            self.assertNotIn("Initial worklog.", index_text)


if __name__ == "__main__":
    unittest.main()
