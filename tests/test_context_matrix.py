import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import acf


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "context_matrix"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name / "metadata.json").read_text(encoding="utf-8"))


class ContextMatrixTests(unittest.TestCase):
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

    def run_cli(self, args):
        exit_code, _stdout, _stderr = self.run_cli_output(args)
        return exit_code

    def run_cli_json(self, args):
        exit_code, stdout, stderr = self.run_cli_output(args)
        payload = json.loads(stdout)
        return exit_code, payload, stderr

    def init_context(self, tmp: str, fixture_name: str) -> Path:
        fixture = load_fixture(fixture_name)
        target = Path(tmp) / fixture_name / "docs" / "ai"
        exit_code, _payload, stderr = self.run_cli_json(
            ["init", str(target), "--profile", fixture.get("profile", "minimal"), "--json"]
        )
        self.assertEqual(exit_code, 0, stderr)
        for path in target.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            cleaned = acf.PLACEHOLDER_RE.sub("placeholder", text)
            if cleaned != text:
                path.write_text(cleaned, encoding="utf-8")
        (target / "active" / "Current_Task.md").write_text(
            "## 当前任务状态\n\nEmpty\n\n## 子任务 ID\n\n无。\n",
            encoding="utf-8",
        )
        (target / "active" / "Task_Plan.md").write_text(
            "## 大任务状态\n\nDone\n\n"
            "## 当前焦点\n\n无。\n\n"
            "## 子任务\n\n"
            "| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 暂无 |  |  |  |  |  |  |\n\n"
            "## 任务阶段\n\n"
            + acf.TASK_STAGE_TABLE_HEADER
            + "\n|---|---|---|---|---|---|---|---|---|\n"
            "| 暂无 |  |  |  |  |  |  |  |  |\n",
            encoding="utf-8",
        )
        (target / "reference" / "Sources_Index.md").write_text(
            "## 核心资料\n\n"
            "| 资料 | 类型 | 链接或位置 | 状态 | 可信度 | 和本项目的关系 | 后续动作 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 暂无 |  |  |  |  |  |  |\n",
            encoding="utf-8",
        )
        return target

    def test_context_matrix_fixture_inventory(self):
        expected = {
            "minimal_clean",
            "legacy_old_context",
            "audit_long_section",
            "workstream_complex",
            "authority_gate",
            "workstream_stage_flow",
            "task_stage_registry",
            "workstream_lifecycle_archive",
        }
        actual = {path.name for path in FIXTURE_ROOT.iterdir() if path.is_dir()}
        self.assertTrue(expected.issubset(actual))
        for name in expected:
            fixture = load_fixture(name)
            self.assertEqual(fixture["kind"], name)
            self.assertIn("intent", fixture)
            self.assertIn("expected_behavior", fixture)
            self.assertIn("risk_tags", fixture)
        legacy = load_fixture("legacy_old_context")
        referenced = ROOT / legacy["covered_by"]
        self.assertTrue((referenced / "metadata.json").exists(), referenced)

    def test_minimal_clean_fixture_has_no_audit_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_context(tmp, "minimal_clean")

            exit_code, payload, stderr = self.run_cli_json(["audit", "context", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["candidates"], [])
            self.assertEqual(payload["summary"]["total"], 0)

    def test_audit_long_section_fixture_reports_real_section_not_h1_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_context(tmp, "audit_long_section")
            wrapper_sections = "\n\n".join(
                f"## Short Section {section}\n\n" + "\n".join(f"- Short fact {section}-{index}" for index in range(30))
                for section in range(3)
            )
            long_lines = "\n".join(f"- Long detail {index}" for index in range(90))
            (target / "active" / "Context.md").write_text(
                "# Active Context Wrapper\n\n"
                f"{wrapper_sections}\n\n"
                "## Deep Detail\n\n"
                f"{long_lines}\n",
                encoding="utf-8",
            )

            exit_code, payload, stderr = self.run_cli_json(["audit", "context", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            long_candidates = [item for item in payload["candidates"] if item["kind"] == "active_section_too_long"]
            self.assertEqual(len(long_candidates), 1, payload)
            self.assertEqual(long_candidates[0]["section"], "Deep Detail")
            self.assertNotIn("Active Context Wrapper", {item.get("section") for item in long_candidates})

    def test_workstream_complex_fixture_passes_strict_and_sync_noops(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_context(tmp, "workstream_complex")
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS004",
                        "--title",
                        "Generic complex workstream",
                        "--owner",
                        "codex",
                        "--output",
                        "reviewed output",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "set", "WS004", str(target), "--status", "Active"]), 0)
            detail = target / "active" / "workstreams" / "WS004.md"
            text = detail.read_text(encoding="utf-8")
            text = text.replace("title: Generic complex workstream\n", "title: Generic complex workstream\ncurrent_stage: WS004.2\n")
            text = text.replace("## 目标\n\n待补充。", "## 目标\n\nGeneric goal.")
            text += (
                "\n## 阶段\n\n"
                + acf.WORKSTREAM_STAGE_TABLE_HEADER
                + "\n|---|---|---|---|---|---|---|\n"
                + "| WS004.1 | Done | first generic stage | 无。 | stage evidence | worklog/generic.md | activate WS004.2 |\n"
                + "| WS004.2 | Active | second generic stage | WS004.1 | reviewed output | worklog/generic.md | finish stage |\n"
            )
            detail.write_text(text, encoding="utf-8")

            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS005",
                        "--title",
                        "Generic terminal workstream",
                        "--owner",
                        "codex",
                        "--output",
                        "terminal output",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "set", "WS005", str(target), "--status", "Active"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS005",
                        str(target),
                        "--target",
                        "active/Context.md",
                        "--summary",
                        "No context change required for fixture.",
                        "--verification",
                        "Fixture evidence reviewed.",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "ready", "WS005", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "done",
                        "WS005",
                        str(target),
                        "--evidence",
                        "worklog/terminal.md",
                        "--merge-resolution",
                        "no_merge_required",
                    ]
                ),
                0,
            )
            terminal = target / "active" / "workstreams" / "WS005.md"
            terminal.write_text(
                terminal.read_text(encoding="utf-8").replace(
                    "title: Generic terminal workstream\n",
                    "title: Generic terminal workstream\n"
                    "keep_active_reason: retained for complex fixture coverage\n"
                    "keep_active_until: 2099-01-01\n",
                ),
                encoding="utf-8",
            )

            exit_code, check_payload, stderr = self.run_cli_json(["check", str(target), "--strict", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(check_payload["ok"])
            exit_code, sync_payload, stderr = self.run_cli_json(["workstream", "sync", str(target), "--dry-run", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(sync_payload["changed_files"], [])

    def test_workstream_stage_flow_fixture_exercises_stage_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_context(tmp, "workstream_stage_flow")
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS010",
                        "--title",
                        "Stage flow fixture",
                        "--owner",
                        "codex",
                        "--goal",
                        "Verify generic Workstream stage flow.",
                        "--output",
                        "stage flow evidence",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "set", "WS010", str(target), "--status", "Active"]), 0)
            for stage_id, title, depends in (
                ("WS010.1", "First generic stage", "无。"),
                ("WS010.2", "Second generic stage", "WS010.1"),
                ("WS010.3", "Conflict candidate stage", "无。"),
            ):
                args = [
                    "workstream",
                    "stage",
                    "add",
                    "WS010",
                    str(target),
                    "--id",
                    stage_id,
                    "--title",
                    title,
                    "--depends",
                    depends,
                    "--output",
                    "stage output",
                    "--json",
                ]
                exit_code, payload, stderr = self.run_cli_json(args)
                self.assertEqual(exit_code, 0, stderr)
                self.assertEqual(payload["stage"]["id"], stage_id)
                self.assertEqual(payload["stage"]["status"], "Pending")

            exit_code, payload, stderr = self.run_cli_json(
                ["workstream", "stage", "list", "WS010", str(target), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual([stage["id"] for stage in payload["stages"]], ["WS010.1", "WS010.2", "WS010.3"])

            exit_code, payload, _stderr = self.run_cli_json(
                ["workstream", "focus", "WS010", "WS010.2", str(target), "--json"]
            )
            self.assertNotEqual(exit_code, 0)
            self.assertEqual(payload["error_code"], "workstream_stage_dependency_blocked")

            exit_code, payload, stderr = self.run_cli_json(
                ["workstream", "focus", "WS010", "WS010.1", str(target), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["current_stage"], "WS010.1")

            exit_code, payload, _stderr = self.run_cli_json(
                ["workstream", "stage", "done", "WS010", "WS010.1", str(target), "--json"]
            )
            self.assertNotEqual(exit_code, 0)
            self.assertEqual(payload["error_code"], "workstream_missing_evidence")

            exit_code, payload, _stderr = self.run_cli_json(
                [
                    "workstream",
                    "stage",
                    "done",
                    "WS010",
                    "WS010.1",
                    str(target),
                    "--evidence",
                    "worklog/stage-1.md",
                    "--json",
                ]
            )
            self.assertNotEqual(exit_code, 0)
            self.assertEqual(payload["error_code"], "workstream_stage_clear_current_required")

            exit_code, payload, stderr = self.run_cli_json(
                [
                    "workstream",
                    "stage",
                    "done",
                    "WS010",
                    "WS010.1",
                    str(target),
                    "--evidence",
                    "worklog/stage-1.md",
                    "--clear-current",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["status"], "Done")

            exit_code, payload, stderr = self.run_cli_json(
                ["workstream", "focus", "WS010", "WS010.2", str(target), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["current_stage"], "WS010.2")

            exit_code, payload, _stderr = self.run_cli_json(
                ["workstream", "focus", "WS010", "WS010.3", str(target), "--json"]
            )
            self.assertNotEqual(exit_code, 0)
            self.assertEqual(payload["error_code"], "workstream_stage_active_conflict")

            exit_code, payload, stderr = self.run_cli_json(
                [
                    "workstream",
                    "stage",
                    "done",
                    "WS010",
                    "WS010.2",
                    str(target),
                    "--evidence",
                    "worklog/stage-2.md",
                    "--clear-current",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["status"], "Done")

            detail_text = (target / "active" / "workstreams" / "WS010.md").read_text(encoding="utf-8")
            self.assertNotIn("current_stage:", detail_text)
            self.assertIn("| WS010.1 | Done | First generic stage", detail_text)
            self.assertIn("| WS010.2 | Done | Second generic stage", detail_text)
            self.assertIn("| WS010.3 | Pending | Conflict candidate stage", detail_text)

            exit_code, check_payload, stderr = self.run_cli_json(["check", str(target), "--strict", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(check_payload["ok"])
            exit_code, sync_payload, stderr = self.run_cli_json(["workstream", "sync", str(target), "--dry-run", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(sync_payload["changed_files"], [])
            exit_code, audit_payload, stderr = self.run_cli_json(["audit", "context", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(audit_payload["candidates"], [])

    def test_task_stage_registry_fixture_exercises_plan_stage_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_context(tmp, "task_stage_registry")
            self.assertEqual(
                self.run_cli(["plan", "init", str(target), "--title", "Task stage fixture", "--goal", "Goal.", "--force"]),
                0,
            )
            self.assertEqual(self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Parent task"]), 0)

            exit_code, payload, _stderr = self.run_cli_json(
                [
                    "plan",
                    "stage",
                    "add",
                    str(target),
                    "--id",
                    "T001.1",
                    "--parent",
                    "T002",
                    "--title",
                    "Invalid parent",
                    "--json",
                ]
            )
            self.assertNotEqual(exit_code, 0)
            self.assertEqual(payload["error_code"], "task_stage_scope_invalid")

            exit_code, payload, stderr = self.run_cli_json(
                [
                    "plan",
                    "stage",
                    "add",
                    str(target),
                    "--id",
                    "T001.1",
                    "--parent",
                    "T001",
                    "--title",
                    "Registered fixture stage",
                    "--output",
                    "fixture output",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["stage"]["id"], "T001.1")
            self.assertEqual(payload["stage"]["status"], "Pending")

            exit_code, payload, stderr = self.run_cli_json(["plan", "stage", "list", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual([stage["id"] for stage in payload["stages"]], ["T001.1"])

            exit_code, payload, stderr = self.run_cli_json(
                [
                    "plan",
                    "stage",
                    "done",
                    str(target),
                    "--id",
                    "T001.1",
                    "--evidence",
                    "worklog/task-stage.md",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(payload["status"], "Done")

            plan_text = (target / "active" / "Task_Plan.md").read_text(encoding="utf-8")
            self.assertIn("| T001.1 | Done | T001 | Registered fixture stage", plan_text)
            self.assertIn("worklog/task-stage.md", plan_text)

            exit_code, check_payload, stderr = self.run_cli_json(["check", str(target), "--strict", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(check_payload["ok"])

    def test_workstream_lifecycle_archive_fixture_retains_needed_terminal_workstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_context(tmp, "workstream_lifecycle_archive")
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS020",
                        "--title",
                        "Lifecycle fixture workstream",
                        "--owner",
                        "codex",
                        "--output",
                        "lifecycle evidence",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "set", "WS020", str(target), "--status", "Active"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS020",
                        str(target),
                        "--target",
                        "active/Context.md",
                        "--summary",
                        "No authority write required for lifecycle fixture.",
                        "--verification",
                        "Fixture evidence reviewed.",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "ready", "WS020", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "done",
                        "WS020",
                        str(target),
                        "--evidence",
                        "worklog/lifecycle.md",
                        "--merge-resolution",
                        "no_merge_required",
                    ]
                ),
                0,
            )
            detail = target / "active" / "workstreams" / "WS020.md"
            detail.write_text(
                detail.read_text(encoding="utf-8").replace(
                    "title: Lifecycle fixture workstream\n",
                    "title: Lifecycle fixture workstream\n"
                    "keep_active_reason: retained to explain current synthetic plan\n"
                    "keep_active_until: 2099-01-01\n",
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                self.run_cli(["plan", "init", str(target), "--title", "Lifecycle plan", "--goal", "Goal.", "--force"]),
                0,
            )
            self.assertEqual(self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Parent task"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "plan",
                        "stage",
                        "add",
                        str(target),
                        "--id",
                        "T001.1",
                        "--parent",
                        "T001",
                        "--title",
                        "Stage referencing retained terminal Workstream",
                        "--workstream",
                        "WS020",
                        "--output",
                        "stage output",
                    ]
                ),
                0,
            )

            exit_code, check_payload, stderr = self.run_cli_json(["check", str(target), "--strict", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(check_payload["ok"])

            exit_code, archive_payload, stderr = self.run_cli_json(
                ["workstream", "archive-candidates", str(target), "--today", "2026-05-08", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(archive_payload["candidates"], [])
            self.assertEqual(archive_payload["blocked"][0]["id"], "WS020")
            self.assertIn("referenced_by_current_task_stage", archive_payload["blocked"][0]["blocked_by"])

            (target / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n## 子任务 ID\n\nT001\n\n## 当前执行线\n\nWS020\n",
                encoding="utf-8",
            )
            result = acf.check_context(target, "minimal", strict=True)
            self.assertTrue(
                any("current execution line references terminal workstream `WS020`" in error for error in result.errors),
                result.errors,
            )

            (target / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nEmpty\n\n## 子任务 ID\n\n无。\n\n## 当前执行线\n\n无。\n",
                encoding="utf-8",
            )
            detail.write_text(
                detail.read_text(encoding="utf-8").replace("keep_active_until: 2099-01-01", "keep_active_until: 2000-01-01"),
                encoding="utf-8",
            )
            result = acf.check_context(target, "minimal", strict=True)
            self.assertTrue(any("keep_active_until `2000-01-01` is expired" in error for error in result.errors), result.errors)

    def test_workstream_lifecycle_archive_fixture_draft_to_archive_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_context(tmp, "workstream_lifecycle_archive")
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS021",
                        "--title",
                        "Archive candidate fixture",
                        "--owner",
                        "codex",
                        "--output",
                        "archive evidence",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "set", "WS021", str(target), "--status", "Active"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS021",
                        str(target),
                        "--target",
                        "active/Context.md",
                        "--summary",
                        "No authority write required for archive fixture.",
                        "--verification",
                        "Fixture evidence reviewed.",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "ready", "WS021", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "done",
                        "WS021",
                        str(target),
                        "--evidence",
                        "worklog/lifecycle.md",
                        "--merge-resolution",
                        "no_merge_required",
                    ]
                ),
                0,
            )

            exit_code, draft_payload, stderr = self.run_cli_json(
                ["workstream", "archive-draft", str(target), "--date", "2026-05-08", "--dry-run", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(draft_payload["candidate_count"], 1)
            self.assertIn("WS021", draft_payload["planned_draft"])

            exit_code, archive_payload, stderr = self.run_cli_json(
                [
                    "workstream",
                    "archive",
                    "WS021",
                    str(target),
                    "--reason",
                    "reviewed in worklog/archive-drafts/2026-05-08.md",
                    "--date",
                    "2026-05-08",
                    "--check-after",
                    "--strict",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(archive_payload["archived_id"], "WS021")
            self.assertFalse((target / "active" / "workstreams" / "WS021.md").exists())
            self.assertTrue((target / "archive" / "workstreams" / "WS021.md").exists())
            exit_code, check_payload, stderr = self.run_cli_json(["check", str(target), "--strict", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(check_payload["ok"])

    def test_authority_gate_fixture_rejects_direct_authority_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_context(tmp, "authority_gate")
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS004",
                        "--title",
                        "Authority gate fixture",
                        "--owner",
                        "codex",
                        "--output",
                        "candidate change",
                    ]
                ),
                0,
            )
            detail = target / "active" / "workstreams" / "WS004.md"
            detail.write_text(
                detail.read_text(encoding="utf-8").replace(
                    "write_scope:\n  - owned: active/workstreams/WS004.md\n",
                    "write_scope:\n  - owned: active/workstreams/WS004.md\n  - assigned: active/Context.md\n",
                ),
                encoding="utf-8",
            )

            exit_code, payload, stderr = self.run_cli_json(["check", str(target), "--strict", "--json"])

            self.assertEqual(exit_code, 1, stderr)
            self.assertFalse(payload["ok"])
            errors = payload["check"]["errors"]
            self.assertTrue(any("targets an authority path" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
