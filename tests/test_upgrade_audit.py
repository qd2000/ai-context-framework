import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import acf
from ai_context_framework.domains.upgrade_audit import build_upgrade_plan_payload
from ai_context_framework.models import CheckResult
from ai_context_framework.observability import usage_log_path
from ai_context_framework.markers import PLACEHOLDER_RE


class UpgradeAuditTests(unittest.TestCase):
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

    def read_usage_lines(self, context_root):
        path = usage_log_path(context_root.parent if context_root.parent.name != "docs" else context_root.parent.parent)
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8").splitlines()

    def replace_template_placeholders(self, context_root):
        for path in context_root.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            path.write_text(PLACEHOLDER_RE.sub("project fact", text), encoding="utf-8")
        sources = context_root / "reference" / "Sources_Index.md"
        if sources.exists():
            sources.write_text(
                "# Sources Index\n\n"
                "| 资料 | 类型 | 位置 | 状态 | 可信度 | 关联 | 下一步 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| 暂无 |  |  |  |  |  |  |\n",
                encoding="utf-8",
            )
        context = context_root / "active" / "Context.md"
        if context.exists():
            context.write_text("## 当前有效事实\n\n- Unique current fact for upgrade audit tests.\n", encoding="utf-8")
        current_task = context_root / "active" / "Current_Task.md"
        if current_task.exists():
            current_task.write_text("## 当前任务状态\n\nEmpty\n", encoding="utf-8")
        task_plan = context_root / "active" / "Task_Plan.md"
        if task_plan.exists():
            task_plan.write_text(acf.render_empty_task_plan(), encoding="utf-8")

    def test_upgrade_plan_reports_missing_structure_without_writing_or_logging(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "project" / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.replace_template_placeholders(context)
            task_plan = context / "active" / "Task_Plan.md"
            curation_prompt = context / "reference" / "Context_Curation_Prompt.md"
            task_plan.unlink()
            curation_prompt.unlink()
            before_usage = self.read_usage_lines(context)

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(context), "--plan", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "upgrade plan")
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["readiness"], "safe_to_apply_structure")
            self.assertEqual(payload["changed_files"], [])
            self.assertIn("risk_summary", payload)
            self.assertNotIn("summary", payload)
            self.assertIn("missing_structure", {item["code"] for item in payload["findings"]})
            self.assertIn("active/Task_Plan.md", {item["path"] for item in payload["structural_changes"]})
            self.assertIn("reference/Context_Curation_Prompt.md", {item["path"] for item in payload["structural_changes"]})
            self.assertFalse(task_plan.exists())
            self.assertFalse(curation_prompt.exists())
            self.assertFalse((context / ".omx").exists())
            self.assertEqual(before_usage, self.read_usage_lines(context))

    def test_upgrade_plan_reports_placeholder_debt_as_manual_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "project" / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            target = context / "active" / "Context.md"
            target.write_text("## 当前阶段\n\n【项目阶段】\n", encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(context), "--plan", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["readiness"], "needs_cleanup")
            self.assertIn("template_placeholder", {item["code"] for item in payload["findings"]})
            self.assertEqual(payload["structural_changes"], [])
            self.assertTrue(payload["manual_actions"])
            action = payload["manual_actions"][0]
            self.assertIsInstance(action, dict)
            self.assertIn("path", action)
            self.assertIn("next_actions", action)

    def test_upgrade_plan_rejects_write_mode_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "project" / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)

            exit_code, stdout, _stderr = self.run_cli_output(["upgrade", str(context), "--plan", "--dry-run", "--json"])

            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], "input_error")

    def test_upgrade_plan_reports_non_context_without_logging(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            before_logs = list(Path(os.environ["ACF_HOME"]).rglob("usage.jsonl"))

            exit_code, stdout, _stderr = self.run_cli_output(["upgrade", str(project), "--plan", "--json"])

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["command"], "upgrade plan")
            self.assertEqual(payload["error_code"], "context_not_found")
            self.assertEqual(payload["readiness"], "blocked")
            self.assertIn("acf init", " ".join(payload["next_actions"]))
            self.assertEqual(before_logs, list(Path(os.environ["ACF_HOME"]).rglob("usage.jsonl")))

    def test_upgrade_plan_keeps_minimal_context_minimal(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "project" / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.replace_template_placeholders(context)

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(context), "--plan", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["schema_version"], 1)
            self.assertIsNone(payload["error_code"])
            self.assertEqual(payload["profile"], "minimal")
            self.assertEqual(payload["readiness"], "current")
            self.assertNotIn("human/Human_Index.md", {item["path"] for item in payload["structural_changes"]})

    def test_upgrade_plan_discovers_context_from_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            context = project / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.replace_template_placeholders(context)

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(project), "--plan", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["context"], str(context.resolve()))
            self.assertEqual(payload["readiness"], "current")

    def test_upgrade_plan_reports_inventory_debt_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            context = project / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.replace_template_placeholders(context)
            root_agent = project / "AGENTS.md"
            root_agent.unlink()
            draft = context / "worklog" / "curation-drafts" / "2026-06-09.md"
            draft.parent.mkdir(parents=True, exist_ok=True)
            draft.write_text("# draft\n", encoding="utf-8")
            before_text = draft.read_text(encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(context), "--plan", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            codes = {item["code"] for item in payload["findings"]}
            self.assertIn("root_agent_missing", codes)
            self.assertIn("draft_exists", codes)
            self.assertEqual(payload["readiness"], "needs_cleanup")
            self.assertFalse(root_agent.exists())
            self.assertEqual(draft.read_text(encoding="utf-8"), before_text)

    def test_upgrade_plan_reports_nonstandard_context_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "project" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.replace_template_placeholders(context)

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(context), "--plan", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            findings = {item["code"]: item for item in payload["findings"]}
            self.assertEqual(payload["readiness"], "needs_cleanup")
            self.assertEqual(findings["nonstandard_context_path"]["path"], "ai")

    def test_upgrade_plan_classifies_workstream_scope_conflict_as_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "project" / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.replace_template_placeholders(context)
            self.assertEqual(self.run_cli_output(["workstream", "init", str(context), "--json"])[0], 0)
            for ws_id in ("WS001", "WS002"):
                self.assertEqual(
                    self.run_cli_output(
                        [
                            "workstream",
                            "add",
                            str(context),
                            "--id",
                            ws_id,
                            "--title",
                            f"{ws_id} scope test",
                            "--owner",
                            "codex",
                            "--output",
                            "out",
                            "--json",
                        ]
                    )[0],
                    0,
                )
                self.assertEqual(
                    self.run_cli_output(["workstream", "set", ws_id, str(context), "--status", "Active", "--json"])[0],
                    0,
                )
                detail = context / "active" / "workstreams" / f"{ws_id}.md"
                text = detail.read_text(encoding="utf-8")
                text = text.replace(f"  - owned: active/workstreams/{ws_id}.md", "  - assigned: src/shared.py")
                detail.write_text(text, encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(context), "--plan", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["readiness"], "blocked")
            findings = {item["code"]: item for item in payload["findings"]}
            self.assertEqual(findings["workstream_scope_conflict"]["severity"], "blocking")

    def test_upgrade_plan_maps_workstream_lifecycle_errors_to_stable_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "project" / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.replace_template_placeholders(context)
            result = CheckResult(
                [
                    "active/workstreams/WS001.md: Done workstream missing merge_resolution",
                    "active/workstreams/WS002.md: ReadyToMerge workstream missing merge target or candidate summary",
                    "active/workstreams/WS003.md: invalid keep_active_until `tomorrow`",
                    "active/workstreams/WS004.md: Merging status requires type Merge or Maintenance",
                ],
                [
                    "active/workstreams/WS005.md: terminal workstream remains active without keep_active_reason",
                ],
            )

            payload = build_upgrade_plan_payload(context, [], [], result)

            findings = {item["code"]: item for item in payload["findings"]}
            self.assertEqual(payload["readiness"], "blocked")
            self.assertEqual(findings["workstream_missing_merge_resolution"]["severity"], "blocking")
            self.assertEqual(findings["workstream_missing_merge_request"]["severity"], "blocking")
            self.assertEqual(findings["workstream_invalid_keep_active_until"]["severity"], "blocking")
            self.assertEqual(findings["workstream_invalid_merge_state"]["severity"], "blocking")
            self.assertEqual(findings["workstream_terminal_retained"]["severity"], "warning")

    def test_upgrade_plan_classifies_upgrade_warning_as_manual_when_insert_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "project" / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.replace_template_placeholders(context)
            current = context / "active" / "Current_Task.md"
            current.write_text("## 当前任务状态\n\nActive\n\n## 任务名称\n\nLegacy task\n", encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(context), "--plan", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            findings = {item["code"]: item for item in payload["findings"]}
            self.assertEqual(findings["managed_doc_upgrade_skipped"]["auto_fix"], "manual")

    def test_upgrade_refreshes_legacy_system_manual_with_workstream_guard_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "project" / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.replace_template_placeholders(context)
            manual = context / "reference" / "System_Manual.md"
            manual.write_text(
                "# System Manual\n\n"
                "## 14. CLI 辅助工具\n\n"
                "Workstream 完成前运行 `acf workstream guard WS001` 检查真实 git diff。\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(context), "--dry-run", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(any(str(path).endswith("reference\\System_Manual.md") or str(path).endswith("reference/System_Manual.md") for path in payload["changed_files"]))
            self.assertNotIn("Workstream guard 模式", manual.read_text(encoding="utf-8"))

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(context), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(any(str(path).endswith("reference\\System_Manual.md") or str(path).endswith("reference/System_Manual.md") for path in payload["changed_files"]))
            updated = manual.read_text(encoding="utf-8")
            self.assertIn("### Workstream guard 模式", updated)
            self.assertIn("acf workstream guard WS001 --files", updated)
            self.assertIn("acf workstream guard WS001 --workspace --strict-workspace", updated)
            self.assertIn("只有显式文件集模式可作为完成或切换状态的强验收证据", updated)

    def test_upgrade_replaces_incomplete_workstream_guard_modes_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "project" / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.replace_template_placeholders(context)
            manual = context / "reference" / "System_Manual.md"
            manual.write_text(
                "# System Manual\n\n"
                "## 14. CLI 辅助工具\n\n"
                "### Workstream guard 模式\n\n"
                "旧说明：完成前运行裸 guard。\n\n"
                "### 旧版本上下文升级\n\n"
                "旧升级说明。\n",
                encoding="utf-8",
            )

            exit_code, _stdout, stderr = self.run_cli_output(["upgrade", str(context), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            updated = manual.read_text(encoding="utf-8")
            self.assertEqual(updated.count("### Workstream guard 模式"), 1)
            self.assertNotIn("旧说明：完成前运行裸 guard。", updated)
            self.assertIn("acf workstream guard WS001 --files", updated)
            self.assertIn("acf workstream guard WS001 --workspace --strict-workspace", updated)

    def test_upgrade_plan_maps_runtime_environment_signals_to_stable_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "项目" / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.replace_template_placeholders(context)
            result = CheckResult(
                [
                    "runtime: git unavailable for this project",
                    "runtime: git dirty working tree",
                    "active/Context.md: CRLF line ending must be preserved",
                    "runtime: unicode path supported",
                ],
                [],
            )

            payload = build_upgrade_plan_payload(context, [], [], result)

            codes = {item["code"] for item in payload["findings"]}
            self.assertIn("git_unavailable", codes)
            self.assertIn("git_dirty", codes)
            self.assertIn("line_ending_preserved", codes)
            self.assertIn("unicode_path_supported", codes)

    def test_upgrade_plan_classifies_invalid_workstream_stage_as_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp) / "project" / "docs" / "ai"
            exit_code, _stdout, stderr = self.run_cli_output(["init", str(context), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.replace_template_placeholders(context)
            self.assertEqual(self.run_cli_output(["workstream", "init", str(context), "--json"])[0], 0)
            self.assertEqual(
                self.run_cli_output(
                    [
                        "workstream",
                        "add",
                        str(context),
                        "--id",
                        "WS001",
                        "--title",
                        "Stage test",
                        "--owner",
                        "codex",
                        "--output",
                        "out",
                        "--json",
                    ]
                )[0],
                0,
            )
            detail = context / "active" / "workstreams" / "WS001.md"
            detail.write_text(
                detail.read_text(encoding="utf-8")
                + "\n---\n\n## 阶段\n\n"
                + acf.WORKSTREAM_STAGE_TABLE_HEADER
                + "\n|---|---|---|---|---|---|---|\n"
                + "| WS001.1a | Active | Invalid suffix | 无。 | out | evidence | next |\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(context), "--plan", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["readiness"], "blocked")
            findings = {item["code"]: item for item in payload["findings"]}
            self.assertEqual(findings["workstream_invalid_stage_id"]["severity"], "blocking")


if __name__ == "__main__":
    unittest.main()
