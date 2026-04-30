import io
import json
import os
import re
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


@contextmanager
def isolated_acf_home(path):
    previous = os.environ.get("ACF_HOME")
    os.environ["ACF_HOME"] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("ACF_HOME", None)
        else:
            os.environ["ACF_HOME"] = previous


class CliTests(unittest.TestCase):
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
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return acf.main(args)

    def run_cli_output(self, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = acf.main(args)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def init_minimal_workstream_context(self, target):
        self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
        self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)

    def add_workstream(self, target, workstream_id, title=None):
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "add",
                    str(target),
                    "--id",
                    workstream_id,
                    "--title",
                    title or workstream_id,
                    "--owner",
                    "主 agent",
                    "--output",
                    "输出物",
                ]
            ),
            0,
        )

    def test_standard_template_check_passes_with_placeholder_warnings(self):
        result = acf.check_context(acf.TEMPLATE_DIR, "standard", strict=False)
        self.assertFalse(result.errors)
        self.assertTrue(result.warnings)

    def test_version_flag_prints_current_version(self):
        exit_code, stdout, stderr = self.run_cli_output(["--version"])
        self.assertEqual(exit_code, 0, stderr)
        self.assertIn(acf.VERSION, stdout)

    def test_version_show_and_set_dry_run(self):
        exit_code, stdout, stderr = self.run_cli_output(["version", "show", "--json"])
        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["version"], acf.VERSION)
        self.assertEqual(payload["versions"]["pyproject"], acf.VERSION.removeprefix("v"))

        exit_code, stdout, stderr = self.run_cli_output(["version", "set", "v0.0.3.3", "--dry-run", "--json"])
        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["version"], "v0.0.3.3")
        self.assertEqual(payload["package_version"], "0.0.3.3")

    def test_front_matter_parse_valid_subset_and_preserves_body(self):
        text = (
            "---\n"
            "id: WS001\n"
            "status: Open\n"
            "depends_on: []\n"
            "read_scope:\n"
            "  - active/Context.md\n"
            "  - active/Task_Plan.md\n"
            "---\n"
            "\n"
            "# Body\n"
            "\n"
            "正文。\n"
        )

        metadata, body, diagnostics = acf.parse_front_matter(text)

        self.assertFalse(diagnostics)
        self.assertEqual(metadata["id"], "WS001")
        self.assertEqual(metadata["status"], "Open")
        self.assertEqual(metadata["depends_on"], [])
        self.assertEqual(metadata["read_scope"], ["active/Context.md", "active/Task_Plan.md"])
        self.assertEqual(body, "\n# Body\n\n正文。\n")

    def test_front_matter_parse_reports_invalid_subset(self):
        cases = {
            "front_matter_unclosed": "---\nid: WS001\n# Body\n",
            "front_matter_duplicate_key": "---\nid: WS001\nid: WS002\n---\n",
            "front_matter_unsupported_syntax": "---\nflag: true\ncount: 1\nnested: {a: b}\ntext: |\n---\n",
            "front_matter_invalid_list_item": "---\n  - orphan\n---\n",
        }

        for expected_code, text in cases.items():
            with self.subTest(expected_code=expected_code):
                _metadata, _body, diagnostics = acf.parse_front_matter(text)
                self.assertIn(expected_code, acf.diagnostic_codes(diagnostics))

    def test_front_matter_format_uses_stable_order_without_rewriting_body(self):
        metadata = {
            "write_scope": ["owned: active/workstreams/WS001.md"],
            "id": "WS001",
            "status": "Open",
        }
        body = "# WS001\n\nBody.\n"

        rendered = acf.format_front_matter(metadata, body, field_order=("id", "status"))

        self.assertEqual(
            rendered,
            "---\n"
            "id: WS001\n"
            "status: Open\n"
            "write_scope:\n"
            "  - owned: active/workstreams/WS001.md\n"
            "---\n"
            "# WS001\n"
            "\n"
            "Body.\n",
        )

    def test_front_matter_schema_validates_required_enum_lists_and_scope_paths(self):
        schema = acf.FrontMatterSchema(
            required_fields=("id", "status", "owner", "title", "read_scope", "write_scope"),
            allowed_fields=(
                "id",
                "status",
                "owner",
                "title",
                "depends_on",
                "read_scope",
                "write_scope",
            ),
            scalar_fields=("id", "status", "owner", "title"),
            list_fields=("depends_on", "read_scope", "write_scope"),
            enum_fields={"status": {"Open", "Active", "Blocked", "ReadyToMerge", "Done", "Cancelled"}},
            typed_scope_fields=("write_scope",),
        )
        metadata = {
            "id": "WS001",
            "status": "Open",
            "owner": "主 agent",
            "title": "Workstream",
            "depends_on": [],
            "read_scope": ["active/Context.md"],
            "write_scope": [
                "owned: active/workstreams/WS001.md",
                "draft: worklog/writeback-drafts/WS001-*",
            ],
        }

        diagnostics = acf.validate_front_matter(metadata, schema)

        self.assertFalse(diagnostics)

    def test_front_matter_schema_reports_missing_enum_typed_scope_and_path_diagnostics(self):
        schema = acf.FrontMatterSchema(
            required_fields=("id", "status", "owner", "title", "read_scope", "write_scope"),
            allowed_fields=("id", "status", "owner", "title", "read_scope", "write_scope"),
            scalar_fields=("id", "status", "owner", "title"),
            list_fields=("read_scope", "write_scope"),
            enum_fields={"status": {"Open", "Active"}},
            typed_scope_fields=("write_scope",),
        )
        metadata = {
            "id": "WS001",
            "status": "Invalid",
            "owner": "主 agent",
            "title": "Workstream",
            "read_scope": [],
            "write_scope": [
                "active/workstreams/WS001.md",
                "owned: active\\workstreams\\WS001.md",
                "owned: active/workstreams/WS001",
            ],
        }

        diagnostics = acf.validate_front_matter(metadata, schema)
        codes = acf.diagnostic_codes(diagnostics)

        self.assertIn("front_matter_schema_failed", codes)
        self.assertIn("front_matter_scope_invalid", codes)
        self.assertIn("front_matter_path_not_normalized", codes)
        self.assertIn("front_matter_path_missing_extension", codes)

    def test_workstream_status_and_init_are_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertFalse((target / "active" / "Workstreams.md").exists())

            exit_code, stdout, stderr = self.run_cli_output(["check", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(json.loads(stdout)["ok"])

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "status", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertFalse(payload["initialized"])
            self.assertEqual(payload["state"], "NotInitialized")
            self.assertTrue(payload["next_actions"])

            exit_code, stdout, _stderr = self.run_cli_output(["workstream", "list", str(target), "--json"])
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_not_initialized")

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "init", str(target), "--json", "--check-after"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["initialized"])
            self.assertTrue((target / "active" / "Workstreams.md").exists())
            self.assertTrue((target / "active" / "workstreams").is_dir())
            self.assertTrue((target / "archive" / "workstreams").is_dir())
            self.assertTrue(payload["changed_files"])

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "init", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["changed_files"], [])

    def test_workstream_list_and_show_parse_front_matter(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(
                acf.render_workstream_index().replace(
                    "| 暂无 | Empty | 无。 | 无。 | 无。 | 无。 | 无。 | 无。 |",
                    "| WS001 | Open | 并行线 | 主 agent | owned: active/workstreams/WS001.md | 无。 | 输出摘要 | active/workstreams/WS001.md |",
                ),
                encoding="utf-8",
            )
            detail_path = target / "active" / "workstreams" / "WS001.md"
            detail_path.write_text(
                "---\n"
                "id: WS001\n"
                "status: Open\n"
                "owner: 主 agent\n"
                "title: 并行线\n"
                "depends_on: []\n"
                "read_scope:\n"
                "  - active/Context.md\n"
                "write_scope:\n"
                "  - owned: active/workstreams/WS001.md\n"
                "---\n"
                "\n"
                "# WS001 - 并行线\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "list", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["workstreams"][0]["id"], "WS001")
            self.assertEqual(payload["counts"]["Open"], 1)

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "show", "WS001", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["metadata"]["id"], "WS001")
            self.assertEqual(payload["normalized_read_scope"], ["active/Context.md"])
            self.assertEqual(payload["normalized_write_scope"], ["owned: active/workstreams/WS001.md"])

    def test_workstream_show_reports_schema_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            (target / "active" / "Workstreams.md").write_text(
                acf.render_workstream_index().replace(
                    "| 暂无 | Empty | 无。 | 无。 | 无。 | 无。 | 无。 | 无。 |",
                    "| WS001 | Open | 并行线 | 主 agent | owned: active/workstreams/WS001.md | 无。 | 输出摘要 | active/workstreams/WS001.md |",
                ),
                encoding="utf-8",
            )
            (target / "active" / "workstreams" / "WS001.md").write_text(
                "---\n"
                "id: WS001\n"
                "status: Invalid\n"
                "owner: 主 agent\n"
                "title: 并行线\n"
                "read_scope: []\n"
                "---\n",
                encoding="utf-8",
            )

            exit_code, stdout, _stderr = self.run_cli_output(["workstream", "show", "WS001", str(target), "--json"])
            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertEqual(payload["error_code"], "workstream_schema_failed")

    def test_workstream_add_creates_detail_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "add",
                    str(target),
                    "--id",
                    "WS002",
                    "--title",
                    "创建状态机",
                    "--owner",
                    "主 agent",
                    "--depends-on",
                    "T004",
                    "--output",
                    "状态机实现",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["id"], "WS002")
            self.assertTrue((target / "active" / "workstreams" / "WS002.md").exists())
            index_text = (target / "active" / "Workstreams.md").read_text(encoding="utf-8")
            self.assertIn("| WS002 | Open | 创建状态机 | 主 agent |", index_text)

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "show", "WS002", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["metadata"]["status"], "Open")
            self.assertEqual(payload["metadata"]["depends_on"], ["T004"])
            self.assertEqual(payload["normalized_write_scope"], ["owned: active/workstreams/WS002.md"])

    def test_workstream_add_rejects_duplicate_and_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)

            dry_args = [
                "workstream",
                "add",
                str(target),
                "--id",
                "WS002",
                "--title",
                "预览",
                "--owner",
                "主 agent",
                "--dry-run",
                "--json",
            ]
            exit_code, stdout, stderr = self.run_cli_output(dry_args)
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn(str(target / "active" / "workstreams" / "WS002.md"), payload["changed_files"])
            self.assertFalse((target / "active" / "workstreams" / "WS002.md").exists())

            add_args = [
                "workstream",
                "add",
                str(target),
                "--id",
                "WS002",
                "--title",
                "创建",
                "--owner",
                "主 agent",
            ]
            self.assertEqual(self.run_cli(add_args), 0)
            exit_code, stdout, _stderr = self.run_cli_output(add_args + ["--json"])
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_duplicate_id")

    def test_workstream_set_and_block_state_transitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS002",
                        "--title",
                        "状态机",
                        "--owner",
                        "主 agent",
                    ]
                ),
                0,
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "set", "WS002", str(target), "--status", "Active", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["status"], "Active")

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "block", "WS002", str(target), "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_reason_required")

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "block", "WS002", str(target), "--reason", "等待 T005 输出", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["status"], "Blocked")
            detail_text = (target / "active" / "workstreams" / "WS002.md").read_text(encoding="utf-8")
            self.assertIn("status: Blocked", detail_text)
            self.assertIn("等待 T005 输出", detail_text)

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "set", "WS002", str(target), "--status", "Active", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["status"], "Active")

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "set", "WS002", str(target), "--status", "Done", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_invalid_transition")

    def test_workstream_cancel_requires_reason_and_is_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS002",
                        "--title",
                        "取消线",
                        "--owner",
                        "主 agent",
                    ]
                ),
                0,
            )

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "cancel", "WS002", str(target), "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_reason_required")

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "cancel", "WS002", str(target), "--reason", "方向取消", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["status"], "Cancelled")
            detail_text = (target / "active" / "workstreams" / "WS002.md").read_text(encoding="utf-8")
            self.assertIn("status: Cancelled", detail_text)
            self.assertIn("方向取消", detail_text)

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "set", "WS002", str(target), "--status", "Active", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_invalid_transition")

    def test_workstream_done_status_is_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS002",
                        "--title",
                        "终态",
                        "--owner",
                        "主 agent",
                    ]
                ),
                0,
            )
            detail_path = target / "active" / "workstreams" / "WS002.md"
            detail_path.write_text(detail_path.read_text(encoding="utf-8").replace("status: Open", "status: Done"), encoding="utf-8")
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS002 | Open |", "| WS002 | Done |"), encoding="utf-8")

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "set", "WS002", str(target), "--status", "Active", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_invalid_transition")

    def test_workstream_merge_request_writes_section_and_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS002",
                        "--title",
                        "合并请求",
                        "--owner",
                        "主 agent",
                    ]
                ),
                0,
            )
            detail_path = target / "active" / "workstreams" / "WS002.md"

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "merge-request",
                    "WS002",
                    str(target),
                    "--target",
                    "Context",
                    "--summary",
                    "候选摘要",
                    "--verification",
                    "单元测试通过",
                    "--dry-run",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn(str(detail_path), payload["changed_files"])
            self.assertNotIn("候选摘要", detail_path.read_text(encoding="utf-8"))

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "merge-request",
                    "WS002",
                    str(target),
                    "--target",
                    "Context",
                    "--target",
                    "Task_Plan",
                    "--summary",
                    "候选摘要",
                    "--verification",
                    "单元测试通过",
                    "--question",
                    "是否同步 ADR",
                    "--conflict",
                    "无代码冲突",
                    "--strategy",
                    "人工审阅后合并",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            detail_text = detail_path.read_text(encoding="utf-8")
            self.assertIn("### 需要合并到哪里", detail_text)
            self.assertIn("- Context", detail_text)
            self.assertIn("- Task_Plan", detail_text)
            self.assertIn("候选摘要", detail_text)

    def test_workstream_ready_requires_merge_request_and_active_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS002",
                        "--title",
                        "Ready",
                        "--owner",
                        "主 agent",
                    ]
                ),
                0,
            )

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "ready", "WS002", str(target), "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_invalid_transition")

            self.assertEqual(self.run_cli(["workstream", "set", "WS002", str(target), "--status", "Active"]), 0)
            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "ready", "WS002", str(target), "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_missing_merge_request")

            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS002",
                        str(target),
                        "--target",
                        "Context",
                        "--summary",
                        "候选摘要",
                        "--verification",
                        "测试通过",
                    ]
                ),
                0,
            )
            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "ready", "WS002", str(target), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["status"], "ReadyToMerge")
            detail_text = (target / "active" / "workstreams" / "WS002.md").read_text(encoding="utf-8")
            self.assertIn("status: ReadyToMerge", detail_text)
            index_text = (target / "active" / "Workstreams.md").read_text(encoding="utf-8")
            self.assertIn("| WS002 | ReadyToMerge |", index_text)

    def test_workstream_done_requires_ready_and_evidence_then_is_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS002",
                        "--title",
                        "Done",
                        "--owner",
                        "主 agent",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "set", "WS002", str(target), "--status", "Active"]), 0)

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "done", "WS002", str(target), "--evidence", "tests", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_invalid_transition")

            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS002",
                        str(target),
                        "--target",
                        "Context",
                        "--summary",
                        "候选摘要",
                        "--verification",
                        "测试通过",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "ready", "WS002", str(target)]), 0)

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "done", "WS002", str(target), "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_missing_evidence")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "done",
                    "WS002",
                    str(target),
                    "--evidence",
                    "tests/test_cli.py",
                    "--summary",
                    "已合并并验证",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["status"], "Done")
            detail_text = (target / "active" / "workstreams" / "WS002.md").read_text(encoding="utf-8")
            self.assertIn("status: Done", detail_text)
            self.assertIn("tests/test_cli.py", detail_text)
            self.assertIn("已合并并验证", detail_text)

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "list", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["workstreams"][0]["status"], "Done")

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "show", "WS002", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["metadata"]["status"], "Done")
            self.assertIn("tests/test_cli.py", payload["evidence"])

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "ready", "WS002", str(target), "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_invalid_transition")
            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "set", "WS002", str(target), "--status", "Active", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_invalid_transition")

    def test_workstream_note_appends_to_allowed_sections_and_creates_missing_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            note_input = Path(tmp) / "note.md"
            note_input.write_text("输入文件结论", encoding="utf-8")
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS002",
                        "--title",
                        "Note",
                        "--owner",
                        "主 agent",
                    ]
                ),
                0,
            )
            detail_path = target / "active" / "workstreams" / "WS002.md"

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "note",
                    "WS002",
                    str(target),
                    "--section",
                    "当前发现",
                    "--text",
                    "新的发现",
                    "--dry-run",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertIn(str(detail_path), json.loads(stdout)["changed_files"])
            self.assertNotIn("新的发现", detail_path.read_text(encoding="utf-8"))

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "note",
                    "WS002",
                    str(target),
                    "--section",
                    "当前发现",
                    "--text",
                    "新的发现",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("新的发现", detail_path.read_text(encoding="utf-8"))

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "note",
                    "WS002",
                    str(target),
                    "--section",
                    "待合并结论",
                    "--input",
                    str(note_input),
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            detail_text = detail_path.read_text(encoding="utf-8")
            self.assertIn("## 待合并结论", detail_text)
            self.assertIn("输入文件结论", detail_text)

            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "workstream",
                    "note",
                    "WS002",
                    str(target),
                    "--section",
                    "Context",
                    "--text",
                    "不允许",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_section_not_allowed")

    def test_workstream_claim_appends_scopes_and_reports_draft_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "add",
                        str(target),
                        "--id",
                        "WS002",
                        "--title",
                        "Claim",
                        "--owner",
                        "主 agent",
                    ]
                ),
                0,
            )
            detail_path = target / "active" / "workstreams" / "WS002.md"

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "claim",
                    "WS002",
                    str(target),
                    "--read",
                    "reference/Architecture.md",
                    "--write",
                    "assigned: src/foo.py",
                    "--write",
                    "draft: worklog/writeback-drafts/draft.md",
                    "--dry-run",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn(str(detail_path), payload["changed_files"])
            self.assertTrue(payload["warnings"])
            self.assertNotIn("reference/Architecture.md", detail_path.read_text(encoding="utf-8"))

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "claim",
                    "WS002",
                    str(target),
                    "--read",
                    "reference/Architecture.md",
                    "--write",
                    "assigned: src/foo.py",
                    "--write",
                    "draft: worklog/writeback-drafts/draft.md",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn("reference/Architecture.md", payload["read_scope"])
            self.assertIn("assigned: src/foo.py", payload["write_scope"])
            self.assertIn("draft: worklog/writeback-drafts/draft.md", payload["write_scope"])
            index_text = (target / "active" / "Workstreams.md").read_text(encoding="utf-8")
            self.assertIn("assigned: src/foo.py", index_text)

    def test_workstream_claim_rejects_invalid_owned_and_conflicting_write_scopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            for workstream_id in ("WS002", "WS003"):
                self.assertEqual(
                    self.run_cli(
                        [
                            "workstream",
                            "add",
                            str(target),
                            "--id",
                            workstream_id,
                            "--title",
                            workstream_id,
                            "--owner",
                            "主 agent",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    self.run_cli(["workstream", "set", workstream_id, str(target), "--status", "Active"]),
                    0,
                )

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "claim", "WS002", str(target), "--write", "src/foo.py", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_scope_invalid")

            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "workstream",
                    "claim",
                    "WS002",
                    str(target),
                    "--write",
                    "owned: active/workstreams/WS003.md",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_owned_scope_invalid")

            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "claim",
                        "WS002",
                        str(target),
                        "--write",
                        "authority: active/Context.md",
                    ]
                ),
                0,
            )
            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "workstream",
                    "claim",
                    "WS003",
                    str(target),
                    "--write",
                    "authority: active/Context.md",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_claim_conflict")

            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "claim",
                        "WS002",
                        str(target),
                        "--write",
                        "assigned: src/bar.py",
                    ]
                ),
                0,
            )
            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "workstream",
                    "claim",
                    "WS003",
                    str(target),
                    "--write",
                    "assigned: src/bar.py",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_claim_conflict")

    def test_workstream_check_is_optional_when_index_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)

            exit_code, stdout, stderr = self.run_cli_output(["check", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertFalse(any("Workstream" in warning or "workstreams" in warning for warning in payload["check"]["warnings"]))

    def test_workstream_check_requires_detail_directory_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            (target / "active" / "workstreams").rmdir()

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--json"])
            self.assertEqual(exit_code, 1)
            errors = json.loads(stdout)["check"]["errors"]
            self.assertTrue(any("active/workstreams" in error for error in errors))

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(
                acf.render_workstream_index().replace(
                    "| 暂无 | Empty | 无。 | 无。 | 无。 | 无。 | 无。 | 无。 |",
                    "| WS002 | Open | Broken | 主 agent | owned: active/workstreams/WS002.md | 无。 | 输出物 | active/workstreams/WS002.md |",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--json"])
            self.assertEqual(exit_code, 1)
            errors = json.loads(stdout)["check"]["errors"]
            self.assertTrue(any("broken Workstream detail" in error for error in errors))

    def test_workstream_check_unindexed_detail_and_status_mismatch_severity(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            detail_path = target / "active" / "workstreams" / "WS999.md"
            detail_path.write_text(
                acf.render_workstream_detail(
                    "WS999",
                    "未索引",
                    "主 agent",
                    [],
                    ["active/Context.md"],
                    ["owned: active/workstreams/WS999.md"],
                    "输出物",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["check", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            warnings = json.loads(stdout)["check"]["warnings"]
            self.assertTrue(any("missing from active/Workstreams.md" in warning for warning in warnings))

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--strict", "--json"])
            self.assertEqual(exit_code, 1)
            errors = json.loads(stdout)["check"]["errors"]
            self.assertTrue(any("missing from active/Workstreams.md" in error for error in errors))

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            detail_path = target / "active" / "workstreams" / "WS002.md"
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS002 | Open |", "| WS002 | Cancelled |"), encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["check", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            warnings = json.loads(stdout)["check"]["warnings"]
            self.assertTrue(any("status mismatch" in warning for warning in warnings))

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--strict", "--json"])
            self.assertEqual(exit_code, 1)
            errors = json.loads(stdout)["check"]["errors"]
            self.assertTrue(any("status mismatch" in error for error in errors))

    def test_workstream_check_state_required_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            detail_path = target / "active" / "workstreams" / "WS002.md"
            text = detail_path.read_text(encoding="utf-8")
            text = text.replace("status: Open", "status: Active")
            text = re.sub(r"read_scope:\n  - active/Context\.md\n  - active/Task_Plan\.md\n", "", text)
            text = re.sub(r"write_scope:\n  - owned: active/workstreams/WS002\.md\n", "", text)
            detail_path.write_text(text, encoding="utf-8")
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS002 | Open |", "| WS002 | Active |"), encoding="utf-8")

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--json"])
            self.assertEqual(exit_code, 1)
            errors = json.loads(stdout)["check"]["errors"]
            self.assertTrue(any("read_scope" in error for error in errors))
            self.assertTrue(any("write_scope" in error for error in errors))

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            self.assertEqual(self.run_cli(["workstream", "set", "WS002", str(target), "--status", "Active"]), 0)
            detail_path = target / "active" / "workstreams" / "WS002.md"
            detail_path.write_text(detail_path.read_text(encoding="utf-8").replace("status: Active", "status: ReadyToMerge"), encoding="utf-8")
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS002 | Active |", "| WS002 | ReadyToMerge |"), encoding="utf-8")

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--json"])
            self.assertEqual(exit_code, 1)
            errors = json.loads(stdout)["check"]["errors"]
            self.assertTrue(any("ReadyToMerge" in error and "merge" in error for error in errors))

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            detail_path = target / "active" / "workstreams" / "WS002.md"
            detail_path.write_text(detail_path.read_text(encoding="utf-8").replace("status: Open", "status: Done"), encoding="utf-8")
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS002 | Open |", "| WS002 | Done |"), encoding="utf-8")

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--json"])
            self.assertEqual(exit_code, 1)
            errors = json.loads(stdout)["check"]["errors"]
            self.assertTrue(any("Done" in error and "evidence" in error for error in errors))

    def test_workstream_check_scope_conflict_and_draft_severity(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            for workstream_id in ("WS002", "WS003"):
                self.add_workstream(target, workstream_id)
                self.assertEqual(self.run_cli(["workstream", "set", workstream_id, str(target), "--status", "Active"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "claim",
                        "WS002",
                        str(target),
                        "--write",
                        "authority: active/Context.md",
                    ]
                ),
                0,
            )
            detail_path = target / "active" / "workstreams" / "WS003.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace(
                    "  - owned: active/workstreams/WS003.md\n",
                    "  - owned: active/workstreams/WS003.md\n  - authority: active/Context.md\n  - draft: worklog/writeback-drafts/draft.md\n",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--json"])
            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout)
            self.assertTrue(any("write scope conflict" in error for error in payload["check"]["errors"]))
            self.assertTrue(any("draft write_scope" in warning for warning in payload["check"]["warnings"]))

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--strict", "--json"])
            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout)
            self.assertTrue(any("draft write_scope" in error for error in payload["check"]["errors"]))

    def test_strict_template_check_fails_on_placeholders(self):
        result = acf.check_context(acf.TEMPLATE_DIR, "standard", strict=True)
        self.assertTrue(any("placeholder" in error for error in result.errors))

    def test_template_project_rules_require_upgrade_compatibility(self):
        text = (acf.TEMPLATE_DIR / "rules" / "Project_Rules.md").read_text(encoding="utf-8")
        self.assertIn("acf upgrade", text)
        self.assertIn("旧版本上下文", text)
        self.assertIn("init/upgrade 测试", text)

    def test_init_minimal_creates_checkable_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            exit_code = self.run_cli(["init", str(target), "--profile", "minimal"])
            self.assertEqual(exit_code, 0)
            self.assertTrue((target / "active" / "Task_Plan.md").exists())
            self.assertTrue((target / "active" / "Feedback_Inbox.md").exists())
            self.assertTrue((target / "archive" / "Archive_Index.md").exists())
            self.assertTrue((target / "archive" / "feedback" / ".gitkeep").exists())
            self.assertTrue((target / "reference" / "Knowledge_Index.md").exists())
            self.assertFalse((target / "decisions" / "ADR-0001-template.md").exists())
            self.assertFalse((target / "worklog" / "daily" / "YYYY-MM-DD.md").exists())
            agents_text = (target / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("## CLI 辅助维护", agents_text)
            self.assertIn("active/Task_Plan.md", agents_text)
            self.assertIn("active/Feedback_Inbox.md", agents_text)
            self.assertIn("acf status --json", agents_text)
            self.assertIn("acf --help", agents_text)
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_init_standard_agents_exposes_cli_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            exit_code = self.run_cli(["init", str(target)])
            self.assertEqual(exit_code, 0)
            self.assertTrue((target / "active" / "Task_Plan.md").exists())
            self.assertTrue((target / "active" / "Feedback_Inbox.md").exists())
            self.assertTrue((target / "archive" / "Archive_Index.md").exists())
            self.assertTrue((target / "archive" / "feedback" / ".gitkeep").exists())
            self.assertTrue((target / "reference" / "Knowledge_Index.md").exists())

            agents_text = (target / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("## CLI 辅助维护", agents_text)
            self.assertIn("acf status --json", agents_text)
            self.assertIn("reference/System_Manual.md", agents_text)

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

    def test_upgrade_dry_run_reports_missing_new_structure_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            for rel in (
                "active/Task_Plan.md",
                "archive/Archive_Index.md",
                "archive/feedback/.gitkeep",
                "reference/Knowledge_Index.md",
            ):
                (target / rel).unlink()

            exit_code, stdout, stderr = self.run_cli_output(
                ["upgrade", str(target), "--dry-run", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["dry_run"])
            self.assertIn(str((target / "active" / "Task_Plan.md").resolve()), payload["changed_files"])
            self.assertFalse((target / "active" / "Task_Plan.md").exists())

    def test_upgrade_does_not_replace_active_current_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            task_path = target / "active" / "Current_Task.md"
            task_path.write_text("## 当前任务状态\n\nActive\n\n## 任务名称\n\nKeep me\n", encoding="utf-8")
            (target / "active" / "Task_Plan.md").unlink()

            exit_code = self.run_cli(["upgrade", str(target)])

            self.assertEqual(exit_code, 0)
            self.assertIn("Keep me", task_path.read_text(encoding="utf-8"))
            self.assertTrue((target / "active" / "Task_Plan.md").exists())

    def test_upgrade_updates_old_standard_agents_and_system_manual(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target)])
            agents = target / "AGENTS.md"
            agents.write_text(
                "## 默认读取顺序\n\n"
                "1. `active/Context.md`\n"
                "2. `rules/Always_Active.md`\n"
                "3. `active/Current_Task.md`（仅当该文件存在且任务状态为 Active 时）\n\n"
                "- 新增或更新当前任务、资料索引、worklog、ADR、section 或 table 时，优先考虑 `acf new`。\n",
                encoding="utf-8",
            )
            manual = target / "reference" / "System_Manual.md"
            manual.write_text(
                "## 14. CLI 辅助工具\n\n### 14.2 常用命令\n\n- `acf status`：查看状态。\n",
                encoding="utf-8",
            )
            for rel in (
                "active/Task_Plan.md",
                "archive/Archive_Index.md",
                "archive/feedback/.gitkeep",
                "reference/Knowledge_Index.md",
            ):
                (target / rel).unlink()

            exit_code, stdout, stderr = self.run_cli_output(
                ["upgrade", str(target), "--dry-run", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn(str(agents.resolve()), payload["changed_files"])
            self.assertIn(str(manual.resolve()), payload["changed_files"])
            self.assertIn(str((target / "archive" / "feedback" / ".gitkeep").resolve()), payload["changed_files"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["upgrade", str(target), "--check-after", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            apply_payload = json.loads(stdout)
            self.assertTrue(apply_payload["check"]["ok"])
            agents_text = agents.read_text(encoding="utf-8")
            self.assertIn("3. `active/Feedback_Inbox.md`", agents_text)
            self.assertIn("4. `active/Task_Plan.md`", agents_text)
            self.assertIn("5. `active/Current_Task.md`", agents_text)
            self.assertIn("Knowledge 草案", agents_text)
            manual_text = manual.read_text(encoding="utf-8")
            self.assertIn("旧版本上下文升级", manual_text)
            self.assertIn("acf plan init|add-task|set-task|focus|complete|status", manual_text)
            self.assertTrue((target / "archive" / "feedback" / ".gitkeep").exists())

    def test_upgrade_refreshes_existing_stale_template_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            agents = target / "AGENTS.md"
            feedback = target / "active" / "Feedback_Inbox.md"
            rules = target / "rules" / "Project_Rules.md"
            manual = target / "reference" / "System_Manual.md"

            agents.write_text(
                "## 默认读取顺序\n\n"
                "1. `active/Context.md`\n"
                "2. `rules/Always_Active.md`\n"
                "3. `active/Feedback_Inbox.md`（仅当存在 Open 条目或需要整理人工反馈时）\n"
                "4. `active/Task_Plan.md`\n"
                "5. `active/Current_Task.md`（仅当任务状态为 Active 时）\n\n"
                "---\n\n"
                "## 会话结束回写要求\n\n"
                "每次重要协作结束时，AI 必须输出标准化的回写建议：\n\n"
                "最终是否写入，由用户决定。\n",
                encoding="utf-8",
            )
            feedback.write_text(
                "## 状态说明\n\n"
                "- Open：尚未整理。\n"
                "- Done：已处理完成。\n\n"
                "---\n\n"
                "## 反馈条目\n\n"
                "| ID | 状态 | 类型 | 内容 | 来源 | 后续处理 |\n"
                "|---|---|---|---|---|---|\n"
                "| F001 | Open | 需求 | Keep row | user | later |\n\n"
                "---\n\n"
                "## 使用规则\n\n"
                "1. AI 不应把本文件中的随想直接当作已确认事实。\n",
                encoding="utf-8",
            )
            rules.write_text("这些规则适用于本项目的大多数任务。\n", encoding="utf-8")
            manual.write_text(
                "本文件是上下文管理系统的详细使用手册。\n\n"
                "## 1. active/ 使用规则\n\n"
                "1. 默认优先读取 `active/Context.md`。\n\n"
                "---\n\n"
                "## 2. rules/ 读取策略\n\n"
                "默认读取 rules。\n\n"
                "---\n\n"
                "## 13. 更新项目上下文的规则\n\n"
                "每次重要协作结束后，AI 应输出标准化的回写建议（格式见 AGENTS.md）。\n\n"
                "最终是否写入，由用户决定。\n\n"
                "---\n\n"
                "## 15. CLI 辅助工具\n\n"
                "### 15.2 常用命令\n\n"
                "- `acf upgrade [target]`：非破坏式补齐当前版本需要的 Feedback_Inbox、Task_Plan、archive 和 Knowledge 结构。\n\n"
                "### 15.3 旧版本上下文升级\n\n"
                "`upgrade` 是非破坏式命令，只补齐当前 schema 缺失的 `active/Task_Plan.md`、archive 和 Knowledge 文件/目录。\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["upgrade", str(target), "--dry-run", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn(str(agents.resolve()), payload["changed_files"])
            self.assertIn(str(feedback.resolve()), payload["changed_files"])
            self.assertIn(str(rules.resolve()), payload["changed_files"])
            self.assertIn(str(manual.resolve()), payload["changed_files"])

            self.assertEqual(self.run_cli(["upgrade", str(target)]), 0)
            self.assertIn("不应默认重复打印完整回写建议清单", agents.read_text(encoding="utf-8"))
            self.assertIn("## 会话结束回写建议", agents.read_text(encoding="utf-8"))
            self.assertIn("Keep row", feedback.read_text(encoding="utf-8"))
            self.assertIn("archive/feedback/", feedback.read_text(encoding="utf-8"))
            self.assertIn("旧版本上下文", rules.read_text(encoding="utf-8"))
            self.assertIn("Feedback_Inbox 生命周期", manual.read_text(encoding="utf-8"))
            self.assertIn("archive、archive/feedback 和 Knowledge", manual.read_text(encoding="utf-8"))

    def test_upgrade_dry_run_reports_no_changes_when_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["upgrade", str(target), "--dry-run", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["changed_files"], [])
            self.assertEqual(payload["next_actions"], ["No changes needed."])

    def test_strict_check_ignores_template_examples_in_real_standard_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target)])

            result = acf.check_context(target, "standard", strict=True)

            joined = "\n".join(result.errors)
            self.assertNotIn("decisions/ADR-0001-template.md: contains", joined)
            self.assertNotIn("worklog/daily/YYYY-MM-DD.md: contains", joined)

    def test_upgrade_appends_marker_notes_for_custom_old_docs_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            agents = target / "AGENTS.md"
            manual = target / "reference" / "System_Manual.md"
            agents.write_text("Custom agent instructions without known ACF sections.\n", encoding="utf-8")
            manual.write_text("Custom system manual without known ACF sections.\n", encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                ["upgrade", str(target), "--dry-run", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn(str(agents.resolve()), payload["changed_files"])
            self.assertIn(str(manual.resolve()), payload["changed_files"])
            self.assertTrue(any("append upgrade notes" in warning for warning in payload["warnings"]))
            self.assertNotIn("ACF Current Schema Upgrade Notes", agents.read_text(encoding="utf-8"))

            self.assertEqual(self.run_cli(["upgrade", str(target)]), 0)
            self.assertEqual(self.run_cli(["upgrade", str(target)]), 0)

            agents_text = agents.read_text(encoding="utf-8")
            manual_text = manual.read_text(encoding="utf-8")
            self.assertEqual(agents_text.count("<!-- ACF:UPGRADE-NOTES:START -->"), 1)
            self.assertEqual(manual_text.count("<!-- ACF:UPGRADE-NOTES:START -->"), 1)
            self.assertIn("ACF Current Schema Upgrade Notes", agents_text)
            self.assertIn("ACF Current Schema Upgrade Notes", manual_text)

    def test_plan_and_task_commands_manage_subtask_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.assertEqual(
                self.run_cli(
                    [
                        "plan",
                        "init",
                        str(target),
                        "--title",
                        "Large task",
                        "--goal",
                        "Finish the plan.",
                    ]
                ),
                0,
            )
            self.assertEqual(
                self.run_cli(
                    [
                        "plan",
                        "add-task",
                        str(target),
                        "--title",
                        "First slice",
                        "--output",
                        "Slice output",
                        "--next-action",
                        "Do first slice",
                    ]
                ),
                0,
            )
            plan_text = (target / "active" / "Task_Plan.md").read_text(encoding="utf-8")
            self.assertIn("| T001 | Pending | First slice |", plan_text)

            self.assertEqual(self.run_cli(["task", "start", str(target), "--id", "T001"]), 0)
            task_text = (target / "active" / "Current_Task.md").read_text(encoding="utf-8")
            self.assertIn("T001", task_text)
            self.assertIn("产出并验证输出物：Slice output", task_text)
            self.assertIn("`active/Context.md`", task_text)
            self.assertIn("保持 `active/Task_Plan.md` 与 `active/Current_Task.md` 状态同步", task_text)
            self.assertIn("## 当前焦点\n\nT001", (target / "active" / "Task_Plan.md").read_text(encoding="utf-8"))

            self.assertEqual(
                self.run_cli(["task", "done", str(target), "--id", "T001", "--evidence", "unit test"]),
                0,
            )
            plan_text = (target / "active" / "Task_Plan.md").read_text(encoding="utf-8")
            self.assertIn("| T001 | Done | First slice |", plan_text)
            self.assertIn("## 当前任务状态\n\nDone", (target / "active" / "Current_Task.md").read_text(encoding="utf-8"))

    def test_task_start_blocks_unfinished_dependencies_and_reports_dry_run_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "First"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T002", "--title", "Second", "--depends", "T001"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["task", "start", str(target), "--id", "T002", "--dry-run", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["task_id"], "T002")
            self.assertEqual(payload["blocked_dependencies"], ["T001"])
            self.assertIn("blocked dependencies", payload["warnings"][0])

            exit_code, stdout, _stderr = self.run_cli_output(
                ["task", "start", str(target), "--id", "T002", "--json"]
            )
            self.assertEqual(exit_code, acf.EXIT_SAFETY_REFUSED)
            self.assertIn("unfinished dependencies", stdout)

            self.assertEqual(self.run_cli(["task", "start", str(target), "--id", "T002", "--force"]), 0)
            task_text = (target / "active" / "Current_Task.md").read_text(encoding="utf-8")
            self.assertIn("`--force` 启动时仍存在未完成依赖：T001", task_text)

    def test_plan_set_task_updates_evidence_and_next_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--title", "First slice"])

            exit_code = self.run_cli(
                [
                    "plan",
                    "set-task",
                    str(target),
                    "--id",
                    "T001",
                    "--status",
                    "Blocked",
                    "--evidence",
                    "blocked evidence",
                    "--next-action",
                    "wait",
                ]
            )

            self.assertEqual(exit_code, 0)
            plan_text = (target / "active" / "Task_Plan.md").read_text(encoding="utf-8")
            self.assertIn("| T001 | Blocked | First slice |", plan_text)
            self.assertIn("blocked evidence", plan_text)
            self.assertIn("wait", plan_text)

    def test_plan_status_recommends_active_or_dependency_ready_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "First"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T002", "--title", "Second", "--depends", "T001"])

            exit_code, stdout, stderr = self.run_cli_output(["plan", "status", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["next_task"]["ID"], "T001")

            self.run_cli(["task", "start", str(target), "--id", "T002", "--force"])
            exit_code, stdout, stderr = self.run_cli_output(["plan", "status", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["next_task"]["ID"], "T002")

    def test_plan_complete_marks_done_after_subtasks_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--title", "First"])
            self.run_cli(["task", "start", str(target), "--id", "T001"])
            self.run_cli(["task", "done", str(target), "--id", "T001", "--evidence", "done"])

            exit_code = self.run_cli(["plan", "complete", str(target)])

            self.assertEqual(exit_code, 0)
            plan_text = (target / "active" / "Task_Plan.md").read_text(encoding="utf-8")
            self.assertIn("## 大任务状态\n\nDone", plan_text)
            self.assertIn("## 当前焦点\n\n无。", plan_text)

    def test_archive_current_task_and_task_plan_reset_active_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--title", "First slice"])
            self.run_cli(["task", "start", str(target), "--id", "T001"])
            self.run_cli(["task", "done", str(target), "--id", "T001", "--evidence", "done"])

            self.assertEqual(
                self.run_cli(["archive", "current-task", str(target), "--reason", "completed"]),
                0,
            )
            self.assertIn("## 当前任务状态\n\nEmpty", (target / "active" / "Current_Task.md").read_text(encoding="utf-8"))
            self.assertTrue(list((target / "archive" / "tasks").glob("*.md")))

            exit_code = self.run_cli(
                ["archive", "task-plan", str(target), "--reason", "completed", "--force"]
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("## 大任务状态\n\nEmpty", (target / "active" / "Task_Plan.md").read_text(encoding="utf-8"))
            self.assertTrue(list((target / "archive" / "plans").glob("*.md")))

    def test_knowledge_draft_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(
                [
                    "knowledge",
                    "draft",
                    str(target),
                    "--title",
                    "Markdown editing lesson",
                    "--source",
                    "active/Context.md",
                    "--summary",
                    "Reusable editing lesson.",
                ]
            )
            self.assertFalse(list((target / "reference" / "knowledge").glob("*.md")))
            draft = next((target / "worklog" / "knowledge-drafts").glob("*.md"))

            exit_code = self.run_cli(["knowledge", "apply", str(draft), str(target)])

            self.assertEqual(exit_code, 0)
            self.assertTrue((target / "reference" / "knowledge" / "K001-markdown-editing-lesson.md").exists())
            index_text = (target / "reference" / "Knowledge_Index.md").read_text(encoding="utf-8")
            self.assertIn("| K001 | Markdown editing lesson | Draft |", index_text)

    def test_knowledge_draft_uses_unicode_slug_and_strict_rejects_draft_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(
                [
                    "knowledge",
                    "draft",
                    str(target),
                    "--title",
                    "上下文维护写命令需要串行化",
                    "--source",
                    "active/Context.md",
                ]
            )
            draft = next((target / "worklog" / "knowledge-drafts").glob("*-上下文维护写命令需要串行化.md"))
            self.run_cli(["knowledge", "apply", str(draft), str(target)])

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("placeholder-like draft content" in error for error in result.errors))

    def test_knowledge_similarity_warns_and_strict_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            knowledge_dir = target / "reference" / "knowledge"
            one = knowledge_dir / "K001-cli-write-lock.md"
            two = knowledge_dir / "K002-cli-write-lock-copy.md"
            body_template = """# {kid}：CLI write lock pattern

## 状态

Active

## 摘要

CLI write commands should serialize context updates.

## 结论

Use a context lock when CLI commands write shared context files.

## 适用场景

- Multiple write commands may update active context files.

## 不适用场景

- Read-only commands.

## 来源

- `active/Context.md`

## 与现有事实源的关系

- Current facts remain in `active/Context.md`.

## 去重判断

This records a reusable write-safety pattern instead of a current task fact.
"""
            one.write_text(body_template.format(kid="K001"), encoding="utf-8")
            two.write_text(body_template.format(kid="K002"), encoding="utf-8")
            (target / "reference" / "Knowledge_Index.md").write_text(
                "## Knowledge 条目\n\n"
                "| ID | 标题 | 状态 | 标签 | 摘要 | 详情 |\n"
                "|---|---|---|---|---|---|\n"
                "| K001 | CLI write lock pattern | Active | cli | serialize writes | `reference/knowledge/K001-cli-write-lock.md` |\n"
                "| K002 | CLI write lock pattern | Active | cli | serialize writes | `reference/knowledge/K002-cli-write-lock-copy.md` |\n",
                encoding="utf-8",
            )

            non_strict = acf.check_context(target, "minimal", strict=False)
            strict = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("similar Knowledge entries" in warning for warning in non_strict.warnings))
            self.assertTrue(any("similar Knowledge entries" in error for error in strict.errors))

    def test_knowledge_apply_blocks_similar_unless_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(
                [
                    "knowledge",
                    "draft",
                    str(target),
                    "--title",
                    "CLI write lock pattern",
                    "--source",
                    "active/Context.md",
                    "--summary",
                    "CLI write commands should serialize context updates.",
                ]
            )
            first_draft = next((target / "worklog" / "knowledge-drafts").glob("*.md"))
            self.assertEqual(self.run_cli(["knowledge", "apply", str(first_draft), str(target)]), 0)
            first_draft.unlink()
            self.run_cli(
                [
                    "knowledge",
                    "draft",
                    str(target),
                    "--title",
                    "CLI write lock pattern",
                    "--source",
                    "active/Context.md",
                    "--summary",
                    "CLI write commands should serialize context updates.",
                ]
            )
            second_draft = next((target / "worklog" / "knowledge-drafts").glob("*.md"))

            exit_code, stdout, _stderr = self.run_cli_output(
                ["knowledge", "apply", str(second_draft), str(target), "--json"]
            )
            self.assertEqual(exit_code, acf.EXIT_SAFETY_REFUSED)
            self.assertIn("similar knowledge already exists", stdout)

            exit_code, stdout, stderr = self.run_cli_output(
                ["knowledge", "apply", str(second_draft), str(target), "--allow-similar", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["similar_knowledge"][0]["id"], "K001")
            self.assertIn("similar knowledge detected", payload["warnings"][0])

    def test_write_command_refuses_existing_context_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / ".acf.lock").write_text("locked\n", encoding="utf-8")

            exit_code, stdout, _stderr = self.run_cli_output(
                ["plan", "init", str(target), "--title", "Large task", "--goal", "Goal", "--json"]
            )

            self.assertEqual(exit_code, acf.EXIT_SAFETY_REFUSED)
            payload = json.loads(stdout)
            self.assertEqual(payload["error_code"], "safety_refused")

    def test_check_detects_invalid_plan_and_knowledge(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            plan = target / "active" / "Task_Plan.md"
            plan.write_text(
                "## 大任务状态\n\nActive\n\n## 当前焦点\n\nT999\n\n## 子任务\n\n"
                "| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| T001 | Active | A | 无。 | 无。 | 无。 | 无。 |\n"
                "| T001 | Active | B | 无。 | 无。 | 无。 | 无。 |\n",
                encoding="utf-8",
            )
            knowledge_dir = target / "reference" / "knowledge"
            knowledge_dir.mkdir(parents=True, exist_ok=True)
            knowledge_file = knowledge_dir / "K001-bad.md"
            knowledge_file.write_text("# K001：Bad\n\n## 状态\n\nActive\n\n## 结论\n\n当前已支持 bad。\n", encoding="utf-8")
            (target / "reference" / "Knowledge_Index.md").write_text(
                "## Knowledge 条目\n\n"
                "| ID | 标题 | 状态 | 标签 | 摘要 | 详情 |\n"
                "|---|---|---|---|---|---|\n"
                "| K001 | Bad | Active | test | bad | `reference/knowledge/K001-bad.md` |\n",
                encoding="utf-8",
            )

            result = acf.check_context(target, "minimal", strict=True)

            joined = "\n".join(result.errors)
            self.assertIn("duplicate subtask id", joined)
            self.assertIn("more than one subtask is Active", joined)
            self.assertIn("current focus `T999`", joined)
            self.assertIn("missing or empty required section", joined)
            self.assertIn("may contain current-fact wording", joined)

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
                exit_code = self.run_cli(["status"])
            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)

    def test_status_json_reports_input_error_when_context_cannot_be_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pushd(Path(tmp)):
                exit_code, stdout, _stderr = self.run_cli_output(["status", "--json"])

            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], "input_error")
            self.assertTrue(payload["next_actions"])

    def test_usage_log_is_enabled_by_default_without_project_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            acf_home = Path(tmp) / "acf-home"
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            with isolated_acf_home(acf_home):
                exit_code, stdout, stderr = self.run_cli_output(["log", "status", str(project_root), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["enabled"])
            self.assertEqual(payload["event_count"], 0)
            self.assertIn(str(acf_home.resolve()), payload["log_path"])
            self.assertFalse((project_root / ".acf").exists())
            self.assertFalse(acf_home.exists())

    def test_usage_log_disable_stops_later_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            acf_home = Path(tmp) / "acf-home"
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            with isolated_acf_home(acf_home):
                self.assertEqual(self.run_cli(["log", "disable", str(project_root)]), 0)
                self.run_cli(["status", str(project_root)])
                exit_code, stdout, stderr = self.run_cli_output(["log", "status", str(project_root), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertFalse(payload["enabled"])
            self.assertEqual(payload["event_count"], 0)

    def test_usage_log_enable_records_later_command_without_input_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            acf_home = Path(tmp) / "acf-home"
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            nested = project_root / "src"
            nested.mkdir(parents=True)
            self.run_cli(["init", str(target), "--profile", "minimal"])

            with isolated_acf_home(acf_home):
                self.assertEqual(self.run_cli(["log", "enable", str(project_root)]), 0)
                with pushd(nested):
                    exit_code = self.run_cli(
                        [
                            "new",
                            "task",
                            "--title",
                            "Logged task",
                            "--goal",
                            "Sensitive secret should not be logged.",
                            "--dry-run",
                            "--json",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            with isolated_acf_home(acf_home):
                log_path = acf.usage_log_path(project_root)
            self.assertTrue(log_path.exists())
            self.assertIn(str(acf_home.resolve()), str(log_path))
            self.assertFalse((project_root / ".acf").exists())
            raw_log = log_path.read_text(encoding="utf-8")
            self.assertNotIn("Sensitive secret should not be logged.", raw_log)
            event = json.loads(raw_log.splitlines()[-1])
            self.assertEqual(event["command"], "new task")
            self.assertTrue(event["dry_run"])
            self.assertTrue(event["json"])
            self.assertTrue(event["ok"])
            self.assertEqual(event["exit_code"], 0)
            self.assertEqual(event["context_rel"], "docs/ai")
            self.assertEqual(event["profile"], "minimal")
            self.assertEqual(event["changed_files"], ["docs/ai/active/Current_Task.md"])
            with isolated_acf_home(acf_home):
                self.assertFalse(acf.usage_lock_path(project_root).exists())

    def test_usage_log_records_failed_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            acf_home = Path(tmp) / "acf-home"
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            with isolated_acf_home(acf_home):
                self.run_cli(["log", "enable", str(project_root)])
                self.run_cli(["new", "worklog", str(target), "--date", "2026-04-27", "--summary", "Initial."])

                exit_code, stdout, _stderr = self.run_cli_output(
                    [
                        "new",
                        "worklog",
                        str(target),
                        "--date",
                        "2026-04-27",
                        "--summary",
                        "Duplicate.",
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, acf.EXIT_SAFETY_REFUSED)
            self.assertEqual(json.loads(stdout)["error_code"], "safety_refused")
            with isolated_acf_home(acf_home):
                log_path = acf.usage_log_path(project_root)
            events = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            failed = events[-1]
            self.assertEqual(failed["command"], "new worklog")
            self.assertFalse(failed["ok"])
            self.assertEqual(failed["exit_code"], acf.EXIT_SAFETY_REFUSED)
            self.assertEqual(failed["error_code"], "safety_refused")

    def test_usage_log_tail_and_summarize_do_not_record_themselves(self):
        with tempfile.TemporaryDirectory() as tmp:
            acf_home = Path(tmp) / "acf-home"
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            with isolated_acf_home(acf_home):
                self.run_cli(["log", "enable", str(project_root)])
                self.run_cli(["status", str(project_root)])
                self.run_cli(["check", str(target)])

                exit_code, stdout, stderr = self.run_cli_output(["log", "tail", str(project_root), "--limit", "1", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            tail_payload = json.loads(stdout)
            self.assertEqual(len(tail_payload["events"]), 1)
            self.assertEqual(tail_payload["events"][0]["command"], "check")

            with isolated_acf_home(acf_home):
                exit_code, stdout, stderr = self.run_cli_output(["log", "summarize", str(project_root), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            summary_payload = json.loads(stdout)
            self.assertEqual(summary_payload["event_count"], 2)
            self.assertEqual(summary_payload["total_event_count"], 2)
            self.assertEqual(summary_payload["command_counts"], {"check": 1, "status": 1})
            self.assertEqual(summary_payload["ok_count"], 2)

            with isolated_acf_home(acf_home):
                exit_code, stdout, stderr = self.run_cli_output(
                    ["log", "summarize", str(project_root), "--command", "status", "--json"]
                )
            self.assertEqual(exit_code, 0, stderr)
            filtered_payload = json.loads(stdout)
            self.assertEqual(filtered_payload["event_count"], 1)
            self.assertEqual(filtered_payload["command_counts"], {"status": 1})

            with isolated_acf_home(acf_home):
                exit_code, stdout, stderr = self.run_cli_output(
                    ["log", "summarize", str(project_root), "--days", "1", "--json"]
                )
            self.assertEqual(exit_code, 0, stderr)
            days_payload = json.loads(stdout)
            self.assertEqual(days_payload["event_count"], 2)
            self.assertEqual(days_payload["filters"]["days"], 1)

            with isolated_acf_home(acf_home):
                exit_code, stdout, stderr = self.run_cli_output(
                    ["log", "summarize", str(project_root), "--errors-only", "--json"]
                )
            self.assertEqual(exit_code, 0, stderr)
            errors_payload = json.loads(stdout)
            self.assertEqual(errors_payload["event_count"], 0)

            with isolated_acf_home(acf_home):
                log_lines = acf.usage_log_path(project_root).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(log_lines), 2)
            self.assertFalse((project_root / ".acf").exists())

    def test_usage_log_prune_removes_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            acf_home = Path(tmp) / "acf-home"
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            with isolated_acf_home(acf_home):
                self.run_cli(["log", "enable", str(project_root)])
                self.run_cli(["status", str(project_root)])

            with isolated_acf_home(acf_home):
                log_path = acf.usage_log_path(project_root)
            self.assertTrue(log_path.read_text(encoding="utf-8").splitlines())

            with isolated_acf_home(acf_home):
                exit_code, stdout, stderr = self.run_cli_output(["log", "prune", str(project_root), "--days", "0", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["removed_count"], 1)
            self.assertEqual(log_path.read_text(encoding="utf-8"), "")

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

    def test_pyproject_declares_acf_console_script(self):
        pyproject_text = (acf.ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("[project.scripts]", pyproject_text)
        self.assertIn('acf = "acf:main"', pyproject_text)
        self.assertIn('py-modules = ["acf"]', pyproject_text)
        self.assertIn("[tool.setuptools.data-files]", pyproject_text)

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

            placeholder_file = target / "decisions" / "ADR-9999.md"
            placeholder_file.write_text("【占位内容】\n", encoding="utf-8")
            result = acf.check_context(target, "minimal", strict=True)
            self.assertTrue(
                any(
                    "decisions/ADR-9999.md: contains 1 placeholder(s)" in error
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
            self.assertEqual(self.run_cli(args), acf.EXIT_SAFETY_REFUSED)

    def test_duplicate_write_json_reports_safety_refused(self):
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
            exit_code, stdout, _stderr = self.run_cli_output(args + ["--json"])

            self.assertEqual(exit_code, acf.EXIT_SAFETY_REFUSED)
            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], "safety_refused")
            self.assertTrue(payload["next_actions"])

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
            exit_code = self.run_cli(
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
            self.assertEqual(exit_code, acf.EXIT_SAFETY_REFUSED)

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
            self.assertEqual(self.run_cli(args), acf.EXIT_SAFETY_REFUSED)

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
            self.assertIn("acf new task", draft_text)
            self.assertNotIn("uv run", draft_text)
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
            self.assertEqual(self.run_cli(args), acf.EXIT_SAFETY_REFUSED)

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
            exit_code = self.run_cli(
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
            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
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
            exit_code = self.run_cli(
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
            self.assertEqual(exit_code, acf.EXIT_SAFETY_REFUSED)

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

    def test_edit_section_get_json_returns_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            context_file = target / "active" / "Context.md"
            context_file.write_text(
                "# Context\n\n## Alpha\n\nOld body.\n\n## Beta\n\nNext body.\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "edit",
                    "section",
                    "get",
                    str(context_file),
                    "--heading",
                    "## Alpha",
                    "--json",
                    "--context",
                    str(target),
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["command"], "edit section get")
            self.assertEqual(payload["body"], "Old body.")
            self.assertEqual(payload["heading_line"], 3)

    def test_edit_section_replace_dry_run_reports_changed_file_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            context_file = target / "active" / "Context.md"
            before = "# Context\n\n## Alpha\n\nOld body.\n"
            context_file.write_text(before, encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "edit",
                    "section",
                    "replace",
                    "active/Context.md",
                    "--heading",
                    "## Alpha",
                    "--text",
                    "New body.",
                    "--dry-run",
                    "--json",
                    "--context",
                    str(target),
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["changed_files"], [str(context_file.resolve())])
            self.assertEqual(context_file.read_text(encoding="utf-8"), before)

    def test_edit_section_replace_preserves_section_separator(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            context_file = target / "active" / "Context.md"
            context_file.write_text(
                "# Context\n\n## Alpha\n\nOld body.\n\n---\n\n## Beta\n\nNext body.\n",
                encoding="utf-8",
            )

            exit_code = self.run_cli(
                [
                    "edit",
                    "section",
                    "replace",
                    "active/Context.md",
                    "--heading",
                    "## Alpha",
                    "--text",
                    "New body.",
                    "--context",
                    str(target),
                ]
            )

            self.assertEqual(exit_code, 0)
            context_text = context_file.read_text(encoding="utf-8")
            self.assertIn("New body.\n\n---\n\n## Beta", context_text)

    def test_edit_section_append_writes_and_check_after_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, _stdout, stderr = self.run_cli_output(
                [
                    "edit",
                    "section",
                    "append",
                    "active/Context.md",
                    "--heading",
                    "## 当前开放问题",
                    "--text",
                    "2. 新增的开放问题。",
                    "--check-after",
                    "--context",
                    str(target),
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            context_text = (target / "active" / "Context.md").read_text(encoding="utf-8")
            self.assertIn("2. 新增的开放问题。", context_text)

    def test_edit_section_append_inserts_before_section_separator(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            context_file = target / "active" / "Context.md"
            context_file.write_text(
                "# Context\n\n## Alpha\n\nOld body.\n\n---\n\n## Beta\n\nNext body.\n",
                encoding="utf-8",
            )

            exit_code = self.run_cli(
                [
                    "edit",
                    "section",
                    "append",
                    "active/Context.md",
                    "--heading",
                    "## Alpha",
                    "--text",
                    "Added body.",
                    "--context",
                    str(target),
                ]
            )

            self.assertEqual(exit_code, 0)
            context_text = context_file.read_text(encoding="utf-8")
            self.assertIn("Old body.\n\nAdded body.\n\n---\n\n## Beta", context_text)

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "edit",
                    "section",
                    "get",
                    "active/Context.md",
                    "--heading",
                    "## Alpha",
                    "--json",
                    "--context",
                    str(target),
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertNotIn("---", payload["body"])

    def test_edit_section_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "edit",
                    "section",
                    "replace",
                    "../README.md",
                    "--heading",
                    "## Alpha",
                    "--text",
                    "No escape.",
                    "--json",
                    "--context",
                    str(target),
                ]
            )

            self.assertEqual(exit_code, acf.EXIT_SAFETY_REFUSED)
            payload = json.loads(stdout)
            self.assertEqual(payload["error_code"], "safety_refused")

    def test_edit_section_rejects_non_markdown_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            note = target / "active" / "note.txt"
            note.write_text("text", encoding="utf-8")

            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "edit",
                    "section",
                    "get",
                    "active/note.txt",
                    "--heading",
                    "## Alpha",
                    "--json",
                    "--context",
                    str(target),
                ]
            )

            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            payload = json.loads(stdout)
            self.assertEqual(payload["error_code"], "input_error")

    def test_edit_table_upsert_updates_existing_key_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            table_file = target / "active" / "Table.md"
            table_file.write_text(
                "| Key | Value | Note |\n|---|---|---|\n| A | old | keep |\n",
                encoding="utf-8",
            )

            exit_code = self.run_cli(
                [
                    "edit",
                    "table",
                    "upsert",
                    "active/Table.md",
                    "--key-column",
                    "Key",
                    "--key",
                    "A",
                    "--cell",
                    "Value=new",
                    "--context",
                    str(target),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("| A | new | keep |", table_file.read_text(encoding="utf-8"))

    def test_edit_table_upsert_appends_missing_key_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            table_file = target / "active" / "Table.md"
            table_file.write_text(
                "| Key | Value | Note |\n|---|---|---|\n| A | old | keep |\n",
                encoding="utf-8",
            )

            exit_code = self.run_cli(
                [
                    "edit",
                    "table",
                    "upsert",
                    "active/Table.md",
                    "--key-column",
                    "Key",
                    "--key",
                    "B",
                    "--cell",
                    "Value=added",
                    "--cell",
                    "Note=created",
                    "--context",
                    str(target),
                ]
            )

            self.assertEqual(exit_code, 0)
            table_text = table_file.read_text(encoding="utf-8")
            self.assertIn("| B | added | created |", table_text)

    def test_edit_table_upsert_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            table_file = target / "active" / "Table.md"
            before = "| Key | Value |\n|---|---|\n| A | old |\n"
            table_file.write_text(before, encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "edit",
                    "table",
                    "upsert",
                    "active/Table.md",
                    "--key-column",
                    "Key",
                    "--key",
                    "A",
                    "--cell",
                    "Value=new",
                    "--dry-run",
                    "--json",
                    "--context",
                    str(target),
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(table_file.read_text(encoding="utf-8"), before)

    def test_edit_section_uses_discovered_context_from_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            nested = project_root / "src" / "package"
            nested.mkdir(parents=True)
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "active" / "Context.md").write_text(
                "# Context\n\n## Alpha\n\nDiscovered body.\n",
                encoding="utf-8",
            )

            with pushd(nested):
                exit_code, stdout, stderr = self.run_cli_output(
                    ["edit", "section", "get", "active/Context.md", "--heading", "## Alpha", "--json"]
                )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["context"], str(target.resolve()))
            self.assertEqual(payload["body"], "Discovered body.")


if __name__ == "__main__":
    unittest.main()
