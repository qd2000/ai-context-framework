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
            self.assertFalse((target / "decisions" / "ADR-0001-template.md").exists())
            self.assertFalse((target / "worklog" / "daily" / "YYYY-MM-DD.md").exists())
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_init_creates_root_thin_agent_for_docs_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            exit_code = self.run_cli(["init", str(target), "--profile", "minimal"])
            self.assertEqual(exit_code, 0)

            root_agents = project_root / "AGENTS.md"
            self.assertTrue(root_agents.exists())
            root_text = root_agents.read_text(encoding="utf-8")
            self.assertIn("docs/ai/AGENTS.md", root_text)
            self.assertIn("AI 上下文目录", root_text)
            self.assertTrue((target / "AGENTS.md").exists())

    def test_init_keeps_existing_root_agent_without_force_root_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            project_root.mkdir()
            root_agents = project_root / "AGENTS.md"
            root_agents.write_text("custom root agent\n", encoding="utf-8")

            target = project_root / "docs" / "ai"
            exit_code = self.run_cli(["init", str(target), "--profile", "minimal"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(root_agents.read_text(encoding="utf-8"), "custom root agent\n")

    def test_init_force_root_agent_replaces_existing_root_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            project_root.mkdir()
            root_agents = project_root / "AGENTS.md"
            root_agents.write_text("custom root agent\n", encoding="utf-8")

            target = project_root / "docs" / "ai"
            exit_code = self.run_cli(
                ["init", str(target), "--profile", "minimal", "--force-root-agent"]
            )
            self.assertEqual(exit_code, 0)
            root_text = root_agents.read_text(encoding="utf-8")
            self.assertNotEqual(root_text, "custom root agent\n")
            self.assertIn("docs/ai/AGENTS.md", root_text)

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

    def test_simplify_copies_real_history_without_placeholder_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            target = Path(tmp) / "target"
            self.run_cli(["init", str(source), "--profile", "minimal"])
            self.run_cli(
                [
                    "new",
                    "adr",
                    str(source),
                    "--date",
                    "2026-04-27",
                    "--title",
                    "Keep real decisions",
                    "--summary",
                    "Real ADR files survive simplify.",
                    "--decision",
                    "Copy real ADR files into simplified contexts.",
                ]
            )
            self.run_cli(
                [
                    "new",
                    "worklog",
                    str(source),
                    "--date",
                    "2026-04-27",
                    "--summary",
                    "Keep real worklogs.",
                ]
            )

            exit_code = self.run_cli(["simplify", str(source), str(target)])
            self.assertEqual(exit_code, 0)
            self.assertTrue((target / "decisions" / "ADR-0001.md").exists())
            self.assertTrue((target / "worklog" / "daily" / "2026-04-27.md").exists())
            self.assertFalse((target / "decisions" / "ADR-0001-template.md").exists())
            self.assertFalse((target / "worklog" / "daily" / "YYYY-MM-DD.md").exists())
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_strict_flags_placeholder_files_when_present(self):
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

            placeholder_file = target / "decisions" / "ADR-0001-template.md"
            placeholder_file.write_text("【占位内容】\n", encoding="utf-8")
            result = acf.check_context(target, "minimal", strict=True)
            self.assertTrue(
                any(
                    "decisions/ADR-0001-template.md: contains 1 placeholder(s)" in error
                    for error in result.errors
                )
            )

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

    def test_new_task_creates_current_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            exit_code = self.run_cli(
                [
                    "new",
                    "task",
                    str(target),
                    "--title",
                    "Implement task command",
                    "--goal",
                    "Generate active/Current_Task.md.",
                    "--goal",
                    "Keep task status valid.",
                    "--success",
                    "Context check passes.",
                    "--constraint",
                    "Use existing CLI patterns.",
                ]
            )
            self.assertEqual(exit_code, 0)

            task_text = (target / "active" / "Current_Task.md").read_text(encoding="utf-8")
            self.assertIn("## 当前任务状态\n\nActive", task_text)
            self.assertIn("Implement task command", task_text)
            self.assertIn("1. Generate active/Current_Task.md.", task_text)
            self.assertNotIn("【", task_text)
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_new_task_refuses_to_replace_active_task_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            args = [
                "new",
                "task",
                str(target),
                "--title",
                "First task",
                "--goal",
                "Create the first task.",
            ]
            self.run_cli(args)
            with self.assertRaises(SystemExit):
                self.run_cli(
                    [
                        "new",
                        "task",
                        str(target),
                        "--title",
                        "Second task",
                        "--goal",
                        "Do not replace active tasks implicitly.",
                    ]
                )

            exit_code = self.run_cli(args + ["--force"])
            self.assertEqual(exit_code, 0)

    def test_new_adr_creates_file_and_active_index_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            exit_code = self.run_cli(
                [
                    "new",
                    "adr",
                    str(target),
                    "--date",
                    "2026-04-27",
                    "--status",
                    "Active",
                    "--title",
                    "Use uv for Python execution",
                    "--summary",
                    "Python commands run through uv.",
                    "--decision",
                    "Use uv run python for repository Python commands.",
                ]
            )
            self.assertEqual(exit_code, 0)

            adr_file = target / "decisions" / "ADR-0001.md"
            self.assertTrue(adr_file.exists())
            adr_text = adr_file.read_text(encoding="utf-8")
            self.assertIn("Use uv for Python execution", adr_text)
            self.assertIn("Active", adr_text)

            index_text = (target / "reference" / "Decisions_Index.md").read_text(encoding="utf-8")
            self.assertIn("| ADR-0001 | Use uv for Python execution | Active | Python commands run through uv. | `decisions/ADR-0001.md` |", index_text)
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_new_adr_uses_next_available_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "decisions" / "ADR-0001.md").write_text(
                "ADR：Existing\n\n## 状态\n\nActive\n",
                encoding="utf-8",
            )
            self.run_cli(
                [
                    "new",
                    "adr",
                    str(target),
                    "--title",
                    "Second decision",
                    "--summary",
                    "Second summary.",
                    "--decision",
                    "Record a second decision.",
                ]
            )
            self.assertTrue((target / "decisions" / "ADR-0002.md").exists())

    def test_new_adr_refuses_existing_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "decisions" / "ADR-0001.md").write_text("existing", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.run_cli(
                    [
                        "new",
                        "adr",
                        str(target),
                        "--id",
                        "ADR-0001",
                        "--title",
                        "Duplicate decision",
                        "--summary",
                        "Duplicate summary.",
                        "--decision",
                        "Do not overwrite existing ADRs.",
                    ]
                )

    def test_new_adr_creates_proposed_index_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(
                [
                    "new",
                    "adr",
                    str(target),
                    "--status",
                    "Proposed",
                    "--title",
                    "Proposed decision",
                    "--summary",
                    "Needs confirmation.",
                    "--decision",
                    "Draft the decision before confirmation.",
                ]
            )
            index_text = (target / "reference" / "Decisions_Index.md").read_text(encoding="utf-8")
            self.assertIn("| ADR-0001 | Proposed decision | Proposed | Needs confirmation. | 详情：`decisions/ADR-0001.md` |", index_text)


if __name__ == "__main__":
    unittest.main()
