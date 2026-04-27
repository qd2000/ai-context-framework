import io
import json
import os
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

import acf


@contextmanager
def pushd(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class CliTests(unittest.TestCase):
    def run_cli(self, args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return acf.main(args)

    def run_cli_output(self, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = acf.main(args)
        return exit_code, stdout.getvalue(), stderr.getvalue()

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

    def test_status_discovers_context_from_project_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            nested = project_root / "src" / "package"
            nested.mkdir(parents=True)
            self.run_cli(["init", str(target), "--profile", "minimal"])

            with pushd(nested):
                exit_code, stdout, stderr = self.run_cli_output(["status"])

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn(f"project root: {project_root.resolve()}", stdout)
            self.assertIn(f"context: {target.resolve()}", stdout)
            self.assertIn("profile: minimal", stdout)
            self.assertIn("current task: Empty", stdout)
            self.assertIn("check: passed", stdout)

    def test_status_json_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            nested = project_root / "src"
            nested.mkdir(parents=True)
            self.run_cli(["init", str(target), "--profile", "minimal"])

            with pushd(nested):
                exit_code, stdout, stderr = self.run_cli_output(["status", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["command"], "status")
            self.assertEqual(payload["context"], str(target.resolve()))
            self.assertEqual(payload["profile"], "minimal")
            self.assertIsNone(payload["error_code"])
            self.assertTrue(payload["next_actions"])
            self.assertTrue(payload["check"]["ok"])

    def test_check_uses_discovered_context_when_path_is_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            nested = project_root / "src"
            nested.mkdir(parents=True)
            self.run_cli(["init", str(target), "--profile", "minimal"])

            with pushd(nested):
                exit_code, stdout, stderr = self.run_cli_output(["check"])

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn(f"check passed: {target.resolve()}", stdout)

    def test_check_json_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(["check", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["command"], "check")
            self.assertEqual(payload["context"], str(target.resolve()))
            self.assertIsNone(payload["error_code"])
            self.assertTrue(payload["next_actions"])
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["check"]["ok"])

    def test_check_json_reports_error_code_and_next_actions_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "AGENTS.md").unlink()

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--json"])

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout)
            self.assertEqual(payload["schema_version"], 1)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], "check_failed")
            self.assertTrue(payload["next_actions"])
            self.assertTrue(payload["check"]["errors"])

    def test_check_explicit_path_takes_priority_over_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            discovered = project_root / "docs" / "ai"
            explicit = Path(tmp) / "explicit"
            nested = project_root / "src"
            nested.mkdir(parents=True)
            self.run_cli(["init", str(discovered), "--profile", "minimal"])
            self.run_cli(["init", str(explicit), "--profile", "minimal"])
            (explicit / "AGENTS.md").unlink()

            with pushd(nested):
                exit_code, _stdout, stderr = self.run_cli_output(["check", str(explicit)])

            self.assertEqual(exit_code, 1)
            self.assertIn("missing file: AGENTS.md", stderr)

    def test_new_task_uses_discovered_context_when_path_is_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            nested = project_root / "src"
            nested.mkdir(parents=True)
            self.run_cli(["init", str(target), "--profile", "minimal"])

            with pushd(nested):
                exit_code = self.run_cli(
                    [
                        "new",
                        "task",
                        "--title",
                        "Discovered task",
                        "--goal",
                        "Use discovered context.",
                    ]
                )

            self.assertEqual(exit_code, 0)
            task_text = (target / "active" / "Current_Task.md").read_text(encoding="utf-8")
            self.assertIn("Discovered task", task_text)

    def test_new_task_dry_run_reports_changed_file_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            before = (target / "active" / "Current_Task.md").read_text(encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "new",
                    "task",
                    str(target),
                    "--title",
                    "Dry run task",
                    "--goal",
                    "Do not write.",
                    "--dry-run",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["schema_version"], 1)
            self.assertTrue(payload["dry_run"])
            self.assertIsNone(payload["error_code"])
            self.assertTrue(payload["next_actions"])
            self.assertEqual(payload["changed_files"], [str((target / "active" / "Current_Task.md").resolve())])
            after = (target / "active" / "Current_Task.md").read_text(encoding="utf-8")
            self.assertEqual(after, before)
            self.assertNotIn("Dry run task", after)

    def test_status_fails_when_context_cannot_be_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pushd(Path(tmp)):
                with self.assertRaises(SystemExit):
                    self.run_cli(["status"])

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

    def test_check_detects_invalid_source_status_in_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            index_file = target / "reference" / "Sources_Index.md"
            index_file.write_text(
                "| 资料 | 类型 | 链接或位置 | 状态 | 可信度 | 和本项目的关系 | 后续动作 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| Source | 文档 | https://example.com | Maybe | 未评估 | Test | Read it. |\n",
                encoding="utf-8",
            )
            result = acf.check_context(target, "minimal", strict=False)
            self.assertTrue(any("invalid source status" in error for error in result.errors))

    def test_template_packaging_entries_cover_all_template_files(self):
        actual_files = {
            path.relative_to(acf.TEMPLATE_DIR).as_posix()
            for path in acf.TEMPLATE_DIR.rglob("*")
            if path.is_file()
        }
        packaged_files = acf.template_packaging_files_from_pyproject(acf.ROOT / "pyproject.toml")
        self.assertFalse(actual_files - packaged_files)
        self.assertFalse(packaged_files - actual_files)

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

            result = acf.check_context(target, "minimal", strict=False)
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

    def test_new_source_creates_index_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            exit_code = self.run_cli(
                [
                    "new",
                    "source",
                    str(target),
                    "--title",
                    "Python docs",
                    "--type",
                    "文档",
                    "--location",
                    "https://docs.python.org/3/",
                    "--status",
                    "Useful",
                    "--credibility",
                    "高",
                    "--relation",
                    "Python standard library reference.",
                    "--next-action",
                    "Use for CLI behavior checks.",
                ]
            )
            self.assertEqual(exit_code, 0)

            index_text = (target / "reference" / "Sources_Index.md").read_text(encoding="utf-8")
            self.assertIn(
                "| Python docs | 文档 | https://docs.python.org/3/ | Useful | 高 | "
                "Python standard library reference. | Use for CLI behavior checks. |",
                index_text,
            )
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_new_source_refuses_duplicate_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            args = [
                "new",
                "source",
                str(target),
                "--title",
                "Python docs",
                "--type",
                "文档",
                "--location",
                "https://docs.python.org/3/",
                "--relation",
                "Python reference.",
            ]
            self.run_cli(args)
            with self.assertRaises(SystemExit):
                self.run_cli(args)

    def test_new_source_force_updates_existing_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            base_args = [
                "new",
                "source",
                str(target),
                "--title",
                "Python docs",
                "--type",
                "文档",
                "--location",
                "https://docs.python.org/3/",
                "--relation",
                "Initial relation.",
            ]
            self.run_cli(base_args)
            self.run_cli(
                base_args
                + [
                    "--status",
                    "Read",
                    "--relation",
                    "Updated relation.",
                    "--force",
                ]
            )
            index_text = (target / "reference" / "Sources_Index.md").read_text(encoding="utf-8")
            self.assertIn("Updated relation.", index_text)
            self.assertNotIn("Initial relation.", index_text)

    def test_writeback_draft_creates_review_file_from_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            exit_code = self.run_cli(
                [
                    "writeback",
                    "draft",
                    str(target),
                    "--name",
                    "session-1",
                    "--text",
                    "Context update: new source command shipped.",
                ]
            )
            self.assertEqual(exit_code, 0)

            draft_file = target / "worklog" / "writeback-drafts" / "session-1.md"
            self.assertTrue(draft_file.exists())
            draft_text = draft_file.read_text(encoding="utf-8")
            self.assertIn("Context update: new source command shipped.", draft_text)
            self.assertIn("active/Context.md 候选", draft_text)
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_writeback_draft_reads_input_file_and_sanitizes_check_sensitive_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            input_file = Path(tmp) / "writeback.txt"
            input_file.write_text("Update `missing.md` and remove 【placeholder】.", encoding="utf-8")
            self.run_cli(["init", str(target), "--profile", "minimal"])
            exit_code = self.run_cli(
                [
                    "writeback",
                    "draft",
                    str(target),
                    "--name",
                    "session-2",
                    "--input",
                    str(input_file),
                ]
            )
            self.assertEqual(exit_code, 0)

            draft_text = (target / "worklog" / "writeback-drafts" / "session-2.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("'missing.md'", draft_text)
            self.assertIn("[placeholder]", draft_text)
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_writeback_draft_refuses_existing_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            args = [
                "writeback",
                "draft",
                str(target),
                "--name",
                "session-1",
                "--text",
                "Initial draft.",
            ]
            self.run_cli(args)
            with self.assertRaises(SystemExit):
                self.run_cli(args)

    def test_writeback_draft_force_updates_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(
                [
                    "writeback",
                    "draft",
                    str(target),
                    "--name",
                    "session-1",
                    "--text",
                    "Initial draft.",
                ]
            )
            self.run_cli(
                [
                    "writeback",
                    "draft",
                    str(target),
                    "--name",
                    "session-1",
                    "--text",
                    "Updated draft.",
                    "--force",
                ]
            )
            draft_text = (target / "worklog" / "writeback-drafts" / "session-1.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("Updated draft.", draft_text)
            self.assertNotIn("Initial draft.", draft_text)

    def test_writeback_draft_rejects_path_like_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            with self.assertRaises(SystemExit):
                self.run_cli(
                    [
                        "writeback",
                        "draft",
                        str(target),
                        "--name",
                        "../session",
                        "--text",
                        "Do not escape draft directory.",
                    ]
                )
            self.assertFalse((target / "worklog" / "writeback-drafts").exists())

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
