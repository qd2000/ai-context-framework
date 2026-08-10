from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import acf


class ContextRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_acf_home = os.environ.get("ACF_HOME")
        self._acf_home = tempfile.TemporaryDirectory()
        os.environ["ACF_HOME"] = self._acf_home.name

    def tearDown(self) -> None:
        if self._previous_acf_home is None:
            os.environ.pop("ACF_HOME", None)
        else:
            os.environ["ACF_HOME"] = self._previous_acf_home
        self._acf_home.cleanup()

    def run_json(self, args: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = acf.main([*args, "--json"] if "--json" not in args else args)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
        payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
        return code, payload, stderr.getvalue()

    def assert_ok(self, args: list[str]) -> dict[str, object]:
        code, payload, stderr = self.run_json(args)
        self.assertEqual(code, 0, stderr or payload)
        self.assertTrue(payload.get("ok"), payload)
        return payload

    def make_context(self, root: Path) -> Path:
        context = root / "docs" / "ai"
        self.assert_ok(["init", str(context), "--profile", "standard"])
        for path in context.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            cleaned = acf.PLACEHOLDER_RE.sub("placeholder", text)
            if cleaned != text:
                path.write_text(cleaned, encoding="utf-8")
        (context / "active" / "Current_Task.md").write_text(
            "## 当前任务状态\n\nEmpty\n\n## 子任务 ID\n\n无。\n",
            encoding="utf-8",
        )
        (context / "active" / "Task_Plan.md").write_text(
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
        (context / "reference" / "Sources_Index.md").write_text(
            "## 核心资料\n\n"
            "| 资料 | 类型 | 链接或位置 | 状态 | 可信度 | 和本项目的关系 | 后续动作 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 暂无 |  |  |  |  |  |  |\n",
            encoding="utf-8",
        )
        adr_template = context / "decisions" / "ADR-0001-template.md"
        if adr_template.exists():
            adr_text = adr_template.read_text(encoding="utf-8")
            adr_template.write_text(
                adr_text.replace("## 状态\n\nplaceholder", "## 状态\n\nProposed"),
                encoding="utf-8",
            )
        self.assert_ok(["workstream", "init", str(context)])
        return context

    def add_active(self, context: Path, workstream_id: str) -> Path:
        self.assert_ok(
            [
                "workstream",
                "add",
                str(context),
                "--id",
                workstream_id,
                "--title",
                f"Routing {workstream_id}",
                "--owner",
                "codex",
                "--goal",
                f"Route {workstream_id} explicitly.",
                "--output",
                f"Output {workstream_id}",
            ]
        )
        self.assert_ok(
            ["workstream", "set", workstream_id, str(context), "--status", "Active"]
        )
        return context / "active" / "workstreams" / f"{workstream_id}.md"

    def test_default_is_global_only_even_with_one_active_workstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self.make_context(Path(tmp))
            detail = self.add_active(context, "WS101")
            secret = "PRIVATE_WS101_BODY_SENTINEL"
            detail.write_text(detail.read_text(encoding="utf-8") + f"\n{secret}\n", encoding="utf-8")

            payload = self.assert_ok(["status", str(context)])
            self.assertEqual(payload["workstream_state"], "GlobalOnly")
            self.assertEqual(payload["context_mode"], "global")
            self.assertEqual(payload["disclosure_level"], "global")
            self.assertIsNone(payload["selected_workstream"])
            self.assertEqual(payload["selected_context_files"], [])
            self.assertEqual(payload["recommended_entry"]["kind"], "global_context")
            self.assertIn("active/Task_Plan.md", payload["global_context_files"])
            self.assertFalse(
                any(path.startswith("active/workstreams/") for path in payload["global_context_files"])
            )
            self.assertNotIn(secret, json.dumps(payload, ensure_ascii=False))

    def test_multiple_active_and_attention_remain_global_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self.make_context(Path(tmp))
            self.add_active(context, "WS101")
            self.add_active(context, "WS102")
            self.assert_ok(
                ["workstream", "set", "WS101", str(context), "--attention", "Now"]
            )
            self.assert_ok(
                ["workstream", "set", "WS102", str(context), "--attention", "Next"]
            )

            payload = self.assert_ok(["next", str(context)])
            self.assertEqual(payload["workstream_state"], "GlobalOnly")
            self.assertIsNone(payload["selected_workstream"])
            self.assertEqual(payload["candidate_entries"], [])
            self.assertEqual(payload["attention_summary"]["Now"], 1)
            self.assertEqual(payload["attention_summary"]["Next"], 1)
            self.assertEqual(payload["management_entry"]["kind"], "workstream_dashboard")

    def test_explicit_selection_returns_pointer_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self.make_context(Path(tmp))
            detail = self.add_active(context, "WS101")
            secret = "PRIVATE_EXPLICIT_SENTINEL"
            detail.write_text(detail.read_text(encoding="utf-8") + f"\n{secret}\n", encoding="utf-8")

            payload = self.assert_ok(
                ["status", str(context), "--workstream", "WS101"]
            )
            self.assertEqual(payload["workstream_state"], "Selected")
            self.assertEqual(payload["context_mode"], "workstream")
            self.assertEqual(payload["disclosure_level"], "workstream_pointer")
            self.assertEqual(payload["selected_workstream"], "WS101")
            self.assertEqual(payload["selection_source"], "explicit_cli")
            self.assertEqual(payload["selected_context_files"], ["active/workstreams/WS101.md"])
            self.assertEqual(payload["recommended_entry"]["disclosure"], "pointer_only")
            self.assertNotIn(secret, json.dumps(payload, ensure_ascii=False))

    def test_current_task_unique_binding_selects_workstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self.make_context(Path(tmp))
            self.add_active(context, "WS101")
            (context / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n"
                "## 所属 Workstream\n\n- `WS101`\n",
                encoding="utf-8",
            )

            payload = self.assert_ok(["next", str(context)])
            self.assertEqual(payload["workstream_state"], "CurrentTaskSelected")
            self.assertEqual(payload["selected_workstream"], "WS101")
            self.assertEqual(payload["selection_source"], "current_task")

    def test_multiple_current_task_bindings_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self.make_context(Path(tmp))
            self.add_active(context, "WS101")
            self.add_active(context, "WS102")
            (context / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n"
                "## 所属 Workstream\n\n- `WS101`\n- `WS102`\n",
                encoding="utf-8",
            )

            code, payload, _stderr = self.run_json(["status", str(context)])
            self.assertEqual(code, 2)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["workstream_state"], "SelectionConflict")
            self.assertEqual(payload["context_mode"], "global")
            self.assertIsNone(payload["selected_workstream"])
            self.assertEqual(payload["recommended_entry"]["kind"], "global_context")

    def test_explicit_selection_conflicting_with_current_task_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self.make_context(Path(tmp))
            self.add_active(context, "WS101")
            self.add_active(context, "WS102")
            (context / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n"
                "## 所属 Workstream\n\n- `WS101`\n",
                encoding="utf-8",
            )

            code, payload, _stderr = self.run_json(
                ["next", str(context), "--workstream", "WS102"]
            )
            self.assertEqual(code, 2)
            self.assertEqual(payload["workstream_state"], "SelectionConflict")
            self.assertEqual(set(payload["selection_candidates"]), {"WS101", "WS102"})
            self.assertEqual(payload["context_mode"], "global")

    def test_same_explicit_and_current_task_selection_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self.make_context(Path(tmp))
            self.add_active(context, "WS101")
            (context / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n"
                "## 所属 Workstream\n\n- `WS101`\n",
                encoding="utf-8",
            )

            payload = self.assert_ok(
                ["status", str(context), "--workstream", "WS101"]
            )
            self.assertEqual(payload["workstream_state"], "CurrentTaskSelected")
            self.assertEqual(payload["selected_workstream"], "WS101")
            self.assertEqual(
                payload["selection_sources"], ["current_task", "explicit_cli"]
            )

    def test_missing_explicit_selection_is_invalid_and_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self.make_context(Path(tmp))
            self.add_active(context, "WS101")

            code, payload, _stderr = self.run_json(
                ["status", str(context), "--workstream", "WS999"]
            )
            self.assertEqual(code, 2)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["workstream_state"], "SelectionInvalid")
            self.assertEqual(payload["context_mode"], "global")
            self.assertIsNone(payload["selected_workstream"])
            self.assertIn("workstream_not_found", payload["selection_errors"][0])


if __name__ == "__main__":
    unittest.main()
