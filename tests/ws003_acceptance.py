import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import acf


ROOT = Path(__file__).resolve().parents[1]


class Ws003AcceptanceTests(unittest.TestCase):
    """Acceptance gates for docs/ai/active/workstreams/WS003.md.

    This module is intentionally named ws003_acceptance.py so it is not picked
    up by the default `python -m unittest` discovery. Run it explicitly with:

        uv run python -m unittest tests.ws003_acceptance

    These tests describe the completed WS003 Slice A-E behavior. Failures now
    indicate a regression or an incomplete slice implementation.
    """

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
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = acf.main(args)
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def run_cli_json(self, args):
        exit_code, stdout, stderr = self.run_cli_output(args)
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None
        return exit_code, payload, stdout, stderr

    def assert_cli_json_ok(self, args):
        exit_code, payload, stdout, stderr = self.run_cli_json(args)
        self.assertEqual(exit_code, 0, stderr or stdout)
        self.assertIsInstance(payload, dict, stdout or stderr)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(payload.get("schema_version"), 1, payload)
        return payload

    def init_standard_context(self, tmp):
        target = Path(tmp) / "docs" / "ai"
        payload = self.assert_cli_json_ok(["init", str(target), "--profile", "standard", "--json"])
        self.assertIn(str(target.resolve()), payload["changed_files"][0])
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
        adr_template = target / "decisions" / "ADR-0001-template.md"
        if adr_template.exists():
            text = adr_template.read_text(encoding="utf-8")
            text = text.replace("## 状态\n\nplaceholder", "## 状态\n\nProposed")
            adr_template.write_text(text, encoding="utf-8")
        evidence = Path(tmp) / "tests" / "ws003_acceptance.py"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("# WS003 acceptance evidence fixture\n", encoding="utf-8")
        self.assert_cli_json_ok(["workstream", "init", str(target), "--json"])
        return target

    def add_active_workstream(self, target, workstream_id="WS101"):
        self.assert_cli_json_ok(
            [
                "workstream",
                "add",
                str(target),
                "--id",
                workstream_id,
                "--title",
                "Acceptance Workstream",
                "--owner",
                "主 agent",
                "--output",
                "acceptance evidence",
                "--goal",
                "Exercise WS003 acceptance behavior.",
                "--json",
            ]
        )
        self.assert_cli_json_ok(["workstream", "set", workstream_id, str(target), "--status", "Active", "--json"])
        return workstream_id

    def test_slice_a_information_architecture_docs_are_workstream_first(self):
        expected_terms_by_file = {
            "README.md": [
                "Workstream-first when active",
                "Task_Plan",
                "Knowledge",
            ],
            "docs/ai/AGENTS.md": [
                "Workstream-first",
                "Task_Plan.md 为 Empty",
                "reference/ 是中间材料层",
                "Knowledge 是高可信",
            ],
            "template/AGENTS.md": [
                "Workstream-first",
                "Task_Plan.md 为 Empty",
                "reference/ 是中间材料层",
                "Knowledge 是高可信",
            ],
            "docs/ai/reference/System_Manual.md": [
                "Workstream-first when active",
                "reference/ 是中间材料层",
                "Knowledge 高可信",
                "ReadyToMerge 不表示权威事实已经合并",
            ],
            "template/reference/System_Manual.md": [
                "Workstream-first when active",
                "reference/ 是中间材料层",
                "Knowledge 高可信",
            ],
            "template/reference/Knowledge_Index.md": [
                "高可信",
                "来源",
                "证据",
                "适用边界",
            ],
        }
        for rel_path, terms in expected_terms_by_file.items():
            text = (ROOT / rel_path).read_text(encoding="utf-8")
            with self.subTest(file=rel_path):
                missing = [term for term in terms if term not in text]
                self.assertEqual(missing, [], f"{rel_path} missing WS003 information architecture terms")

    def test_slice_b_knowledge_v2_metadata_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_standard_context(tmp)
            self.add_active_workstream(target)

            draft = self.assert_cli_json_ok(
                [
                    "knowledge",
                    "draft",
                    str(target),
                    "--title",
                    "Workstream-first acceptance",
                    "--source",
                    "active/workstreams/WS101.md",
                    "--from-workstream",
                    "WS101",
                    "--evidence",
                    "tests/ws003_acceptance.py",
                    "--applies-to",
                    "多 agent 并行 Workstream 开发",
                    "--not-applies-to",
                    "单文件短修复",
                    "--read-when",
                    "当前任务由 Workstream 承载",
                    "--tag",
                    "workstream",
                    "--summary",
                    "Acceptance fixture for Knowledge v2.",
                    "--json",
                ]
            )
            draft_path = Path(draft["changed_files"][0])
            draft_text = draft_path.read_text(encoding="utf-8")
            for expected in [
                "---",
                "status: Draft",
                "source:",
                "evidence:",
                "applies_to:",
                "not_applies_to:",
                "read_when:",
                "last_reviewed:",
                "stale_after_days:",
            ]:
                self.assertIn(expected, draft_text)

            apply_payload = self.assert_cli_json_ok(["knowledge", "apply", str(target), "--draft", str(draft_path), "--json"])
            knowledge_files = [Path(path) for path in apply_payload["changed_files"] if "reference" in path and "knowledge" in path]
            self.assertTrue(knowledge_files, apply_payload)
            active_payload = self.assert_cli_json_ok(
                ["knowledge", "mark", str(target), "--id", "K001", "--status", "Active", "--json", "--check-after", "--strict"]
            )
            self.assertEqual(active_payload["status"], "Active")

    def test_slice_c_links_graph_and_backlinks_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_standard_context(tmp)
            knowledge_dir = target / "reference" / "knowledge"
            knowledge_dir.mkdir(parents=True, exist_ok=True)
            (knowledge_dir / "K001-workstream-first.md").write_text(
                "---\n"
                "id: K001\n"
                "status: Active\n"
                "source:\n"
                "  - active/Context.md\n"
                "evidence:\n"
                "  - tests/ws003_acceptance.py\n"
                "promoted_to:\n"
                "  - rules/Project_Rules.md\n"
                "supersedes: []\n"
                "depends_on: []\n"
                "derived_from: []\n"
                "related: []\n"
                "---\n"
                "# K001 - Workstream-first\n\n"
                "## 结论\n\nUse Workstreams as the current execution entry.\n\n"
                "## 证据\n\n- tests/ws003_acceptance.py\n\n"
                "## 来源\n\n- active/Context.md\n",
                encoding="utf-8",
            )

            graph = self.assert_cli_json_ok(["links", "graph", str(target), "--json"])
            promoted_edges = [
                edge for edge in graph["edges"] if edge["relation"] == "promoted_to" and edge["target"] == "rules/Project_Rules.md"
            ]
            self.assertTrue(promoted_edges, graph)

            check_payload = self.assert_cli_json_ok(["links", "check", str(target), "--json", "--strict"])
            self.assertEqual(check_payload["broken_refs"], [])

            backlinks = self.assert_cli_json_ok(["links", "backlinks", "rules/Project_Rules.md", str(target), "--json"])
            self.assertEqual(backlinks["target"], "rules/Project_Rules.md")
            self.assertTrue(backlinks["backlinks"])

            sync_dry_run = self.assert_cli_json_ok(["links", "sync-backlinks", str(target), "--dry-run", "--json"])
            self.assertEqual(sync_dry_run["changed_files"], [])
            self.assertIn("removed_edges_count", sync_dry_run)

    def test_slice_d_workstream_guard_file_modes_and_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_standard_context(tmp)
            workstream_id = self.add_active_workstream(target)

            guard = self.assert_cli_json_ok(
                [
                    "workstream",
                    "guard",
                    workstream_id,
                    str(target),
                    "--file",
                    f"active/workstreams/{workstream_id}.md",
                    "--json",
                ]
            )
            self.assertEqual(guard["mode"], "files")
            self.assertTrue(guard["authoritative_for_completion"])
            self.assertEqual(guard["changed_files"], [])
            self.assertEqual(guard["out_of_scope_files"], [])

            preflight = self.assert_cli_json_ok(["workstream", "preflight", workstream_id, str(target), "--json"])
            self.assertEqual(preflight["mode"], "preflight")
            self.assertEqual(preflight["changed_files"], [])
            self.assertIn("unattributed_dirty_files", preflight)

            help_exit, _stdout, help_stderr = self.run_cli_output(["workstream", "guard", "--help"])
            self.assertEqual(help_exit, 0, help_stderr)
            for option in ["--files", "--from-git", "--workspace", "--strict-workspace", "--owned-only", "--changed-file"]:
                self.assertIn(option, _stdout)

    def test_slice_e_workstream_first_next_actions_and_draft_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_standard_context(tmp)
            workstream_id = self.add_active_workstream(target)

            status = self.assert_cli_json_ok(["status", str(target), "--json"])
            self.assertIn("changed_files", status)
            self.assertEqual(status["changed_files"], [])
            self.assertIn("workstream_state", status)
            self.assertEqual(status["workstream_state"], "ActiveClassPresent")
            self.assertIn("recommended_entry", status)
            self.assertEqual(status["recommended_entry"]["kind"], "workstream_context")
            self.assertEqual(status["recommended_entry"]["workstream_id"], workstream_id)
            self.assertIn("candidate_entries", status)
            self.assertTrue(status["candidate_entries"])

            next_actions = self.assert_cli_json_ok(["workstream", "next-actions", workstream_id, str(target), "--json"])
            self.assertEqual(next_actions["changed_files"], [])
            self.assertTrue(next_actions["next_actions"])
            guard_command = next_actions["next_actions"][0]["command"]
            self.assertIn(f"--file docs/ai/active/workstreams/{workstream_id}.md", guard_command)
            self.assert_cli_json_ok(
                [
                    "workstream",
                    "guard",
                    workstream_id,
                    str(target),
                    "--file",
                    f"docs/ai/active/workstreams/{workstream_id}.md",
                    "--json",
                ]
            )
            for action in next_actions["next_actions"]:
                self.assertIsInstance(action["command"], str)
                self.assertIsInstance(action["reason"], str)
                self.assertIn(action["writes"], [True, False])
                self.assertIn(action["requires_human"], [True, False])

            global_next = self.assert_cli_json_ok(["next", str(target), "--json"])
            self.assertEqual(global_next["changed_files"], [])
            self.assertEqual(global_next["recommended_entry"]["workstream_id"], workstream_id)

            draft_status = self.assert_cli_json_ok(["draft", "status", str(target), "--json"])
            self.assertEqual(draft_status["changed_files"], [])
            self.assertIn("drafts", draft_status)

    def test_current_task_workstream_link_focuses_next_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_standard_context(tmp)
            self.add_active_workstream(target, "WS101")
            self.add_active_workstream(target, "WS102")
            task_path = target / "active" / "Current_Task.md"
            task_text = task_path.read_text(encoding="utf-8").rstrip()
            task_text = "## \u5f53\u524d\u4efb\u52a1\u72b6\u6001\n\nActive"
            task_path.write_text(
                task_text + "\n\n## Now\n\n- Workstream / \u5b50\u4efb\u52a1\uff1a" + chr(96) + "WS101" + chr(96) + " / T009\n",
                encoding="utf-8",
            )

            payload = self.assert_cli_json_ok(["next", str(target), "--json"])
            self.assertEqual(payload["workstream_state"], "Focused")
            self.assertEqual(payload["current_task_workstreams"], ["WS101"])
            self.assertEqual(payload["recommended_entry"]["workstream_id"], "WS101")
            self.assertEqual(len(payload["candidate_entries"]), 1)

    def test_attention_state_routes_next_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_standard_context(tmp)
            self.add_active_workstream(target, "WS101")
            self.add_active_workstream(target, "WS102")
            self.assert_cli_json_ok(
                ["workstream", "set", "WS101", str(target), "--attention", "Waiting", "--json"]
            )
            self.assert_cli_json_ok(
                ["workstream", "set", "WS102", str(target), "--attention", "Next", "--json"]
            )
            payload = self.assert_cli_json_ok(["next", str(target), "--json"])
            self.assertEqual(payload["workstream_state"], "AttentionNext")
            self.assertEqual(payload["recommended_entry"]["workstream_id"], "WS102")
            self.assertEqual(payload["recommended_entry"]["attention"], "Next")
            self.assertEqual(payload["attention_summary"]["Waiting"], 1)
            self.assertEqual(payload["attention_summary"]["Next"], 1)

    def test_new_task_writes_standard_workstream_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_standard_context(tmp)
            self.add_active_workstream(target, "WS101")
            task = self.assert_cli_json_ok(
                [
                    "new",
                    "task",
                    str(target),
                    "--force",
                    "--title",
                    "Linked task",
                    "--goal",
                    "Route through WS101",
                    "--workstream",
                    "WS101",
                    "--json",
                ]
            )
            self.assertEqual(task["changed_files"], [str(target / "active" / "Current_Task.md")])
            text = (target / "active" / "Current_Task.md").read_text(encoding="utf-8")
            self.assertIn("## 所属 Workstream", text)
            self.assertIn("`WS101`", text)
            payload = self.assert_cli_json_ok(["next", str(target), "--json"])
            self.assertEqual(payload["workstream_state"], "Focused")
            self.assertEqual(payload["recommended_entry"]["workstream_id"], "WS101")

    def test_context_budget_warnings_are_non_blocking_and_route_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_standard_context(tmp)
            self.add_active_workstream(target, "WS101")
            self.add_active_workstream(target, "WS102")
            self.assert_cli_json_ok(
                ["workstream", "set", "WS101", str(target), "--attention", "Now", "--json"]
            )
            context_path = target / "active" / "Context.md"
            context_path.write_text("\n".join(["context line"] * 241) + "\n", encoding="utf-8")
            task_path = target / "active" / "Current_Task.md"
            task_path.write_text(
                "## 当前任务状态\n\nActive\n\n"
                + "\n".join(["task line"] * 158)
                + "\n",
                encoding="utf-8",
            )
            selected = target / "active" / "workstreams" / "WS101.md"
            selected.write_text(
                selected.read_text(encoding="utf-8")
                + "\n## Activity Log\n"
                + "\n".join(["- activity"] * 121)
                + "\n"
                + "\n".join(["- detail"] * 261)
                + "\n",
                encoding="utf-8",
            )
            unselected = target / "active" / "workstreams" / "WS102.md"
            unselected.write_text(
                unselected.read_text(encoding="utf-8")
                + "\n"
                + "\n".join(["- unselected"] * 500)
                + "\n",
                encoding="utf-8",
            )

            next_payload = self.assert_cli_json_ok(["next", str(target), "--json"])
            warning_kinds = {item["kind"] for item in next_payload["context_warnings"]}
            self.assertEqual(next_payload["workstream_state"], "AttentionNow")
            self.assertIn("context", warning_kinds)
            self.assertIn("current_task", warning_kinds)
            self.assertIn("selected_workstream", warning_kinds)
            self.assertIn("selected_activity_log", warning_kinds)
            self.assertFalse(any(item["path"].endswith("WS102.md") for item in next_payload["context_warnings"]))

            status_payload = self.assert_cli_json_ok(["status", str(target), "--strict", "--json"])
            self.assertTrue(status_payload["ok"])
            self.assertEqual(len(status_payload["context_warnings"]), len(next_payload["context_warnings"]))

            check_payload = self.assert_cli_json_ok(["check", str(target), "--strict", "--json"])
            self.assertTrue(check_payload["ok"])
            self.assertEqual(len(check_payload["context_warnings"]), len(next_payload["context_warnings"]))

    def test_inactive_current_task_link_does_not_focus_next_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self.init_standard_context(tmp)
            self.add_active_workstream(target, "WS101")
            self.add_active_workstream(target, "WS102")
            (target / "active" / "Current_Task.md").write_text(
                "## \u5f53\u524d\u4efb\u52a1\u72b6\u6001\n\nEmpty\n\n## Now\n\n- Workstream / \u5b50\u4efb\u52a1\uff1a"
                + chr(96)
                + "WS101"
                + chr(96)
                + " / T009\n",
                encoding="utf-8",
            )

            payload = self.assert_cli_json_ok(["next", str(target), "--json"])
            self.assertEqual(payload["workstream_state"], "Ambiguous")
            self.assertEqual(payload["current_task_workstreams"], [])
            self.assertEqual(len(payload["candidate_entries"]), 2)
