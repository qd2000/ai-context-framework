import hashlib
import io
import json
import os
import re
import subprocess
import sys
import shutil
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

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

    def json_payload(self, stdout):
        return json.loads(stdout)

    def test_minimal_smoke_console_json_is_ascii_safe(self):
        from scripts.minimal_smoke import render_json_for_console

        rendered = render_json_for_console({"message": "中文路径"})
        rendered.encode("cp1252")
        self.assertEqual("中文路径", json.loads(rendered)["message"])
        self.assertIn(r"\u4e2d", rendered)

    def test_shared_json_contract_falls_back_to_escapes_on_narrow_console_encoding(self):
        from ai_context_framework.json_contract import print_json

        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="cp936", newline="\n")
        with redirect_stdout(stream):
            print_json({"message": "状态 A↔B"})
            stream.flush()
        rendered = buffer.getvalue().decode("cp936")
        self.assertEqual("状态 A↔B", json.loads(rendered)["message"])
        self.assertIn(r"\u2194", rendered)

    def test_runtime_and_argparse_error_boundaries_redact_explicit_credentials(self):
        secret = "runtime-error-secret-sentinel"
        with patch(
            "ai_context_framework.runtime.run_with_context_lock",
            side_effect=RuntimeError(f"password={secret}"),
        ):
            exit_code, stdout, stderr = self.run_cli_output(["status", "--json"])
        self.assertEqual(acf.EXIT_RUNTIME_ERROR, exit_code)
        self.assertEqual("", stderr)
        payload = self.json_payload(stdout)
        self.assertNotIn(secret, json.dumps(payload, ensure_ascii=False))
        self.assertIn("redacted credential-like value", payload["message"])

        argv_secret = "argparse-secret-sentinel"
        exit_code, stdout, stderr = self.run_cli_output(
            ["status", f"--api-key={argv_secret}"]
        )
        self.assertEqual(acf.EXIT_INPUT_ERROR, exit_code)
        self.assertEqual("", stdout)
        self.assertNotIn(argv_secret, stderr)
        self.assertIn("redacted credential-like value", stderr)

    def assert_success_json_contract(self, payload, command=None):
        self.assertEqual(payload.get("schema_version"), 1)
        self.assertIs(payload.get("ok"), True)
        self.assertIn("next_actions", payload)
        self.assertIsInstance(payload["next_actions"], list)
        if command is not None:
            self.assertEqual(payload.get("command"), command)
        if "error_code" in payload:
            self.assertIsNone(payload["error_code"])

    def assert_failure_json_contract(self, payload, error_code=None, command=None):
        self.assertEqual(payload.get("schema_version"), 1)
        self.assertIs(payload.get("ok"), False)
        self.assertIn("error_code", payload)
        self.assertIsInstance(payload.get("message"), str)
        self.assertIn("next_actions", payload)
        self.assertIsInstance(payload["next_actions"], list)
        self.assertTrue(payload["next_actions"])
        if error_code is not None:
            self.assertEqual(payload["error_code"], error_code)
        if command is not None:
            self.assertEqual(payload.get("command"), command)

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

    def complete_workstream(self, target, workstream_id):
        self.assertEqual(self.run_cli(["workstream", "set", workstream_id, str(target), "--status", "Active"]), 0)
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "merge-request",
                    workstream_id,
                    str(target),
                    "--target",
                    "active/Context.md",
                    "--summary",
                    "No authority change required.",
                    "--verification",
                    "Unit test fixture.",
                ]
            ),
            0,
        )
        self.authorize_closeout(target, workstream_id, "ready")
        self.assertEqual(self.run_cli(["workstream", "ready", workstream_id, str(target), "--human-approved"]), 0)
        self.authorize_closeout(target, workstream_id, "done")
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "done",
                    workstream_id,
                    str(target),
                    "--evidence",
                    "tests/test_cli.py",
                    "--merge-resolution",
                    "no_merge_required",
                ]
            ),
            0,
        )

    def authorize_closeout(self, target, workstream_id, action):
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "authorization",
                    "approve",
                    workstream_id,
                    str(target),
                    "--action",
                    action,
                    "--actor",
                    "human-owner",
                    "--authority-source",
                    "user-authority:test-fixture",
                    "--evidence-ref",
                    f"test-evidence:{workstream_id}:{action}",
                ]
            ),
            0,
        )

    def set_auto_closeout_policy(self, target, *actions, workstream_class="ordinary"):
        argv = [
            "workstream",
            "authorization",
            "policy-set",
            str(target),
            "--decision",
            "auto",
            "--workstream-class",
            workstream_class,
            "--actor",
            "human-owner",
            "--authority-source",
            "user-authority:test-fixture",
            "--evidence-ref",
            "test-evidence:auto-close-policy",
        ]
        for action in actions:
            argv.extend(["--action", action])
        self.assertEqual(self.run_cli(argv), 0)

    def write_workstream_stage_table(self, target, workstream_id, rows):
        detail_path = target / "active" / "workstreams" / f"{workstream_id}.md"
        table_rows = "\n".join(f"| {' | '.join(row)} |" for row in rows)
        detail_path.write_text(
            detail_path.read_text(encoding="utf-8").rstrip()
            + "\n\n---\n\n## 阶段\n\n"
            + acf.WORKSTREAM_STAGE_TABLE_HEADER
            + "\n|---|---|---|---|---|---|---|\n"
            + table_rows
            + "\n",
            encoding="utf-8",
        )

    def test_standard_template_check_passes_with_placeholder_warnings(self):
        result = acf.check_context(acf.TEMPLATE_DIR, "standard", strict=False)
        self.assertFalse(result.errors)
        self.assertTrue(result.warnings)
        self.assertFalse(any("legacy placeholder" in warning for warning in result.warnings))

    def test_placeholder_format_distinguishes_canonical_from_legacy(self):
        self.assertTrue(acf.is_acf_placeholder("【ACF:PROJECT_NAME|项目名称】"))
        self.assertTrue(acf.is_acf_placeholder("【ACF:DATE】"))
        self.assertEqual(acf.legacy_placeholder_count(["【ACF:DATE】", "【项目名称】"]), 1)

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

    def test_version_show_works_without_source_checkout(self):
        previous_root = acf.ROOT
        with tempfile.TemporaryDirectory() as install_dir, tempfile.TemporaryDirectory() as cwd:
            acf.ROOT = Path(install_dir)
            try:
                with pushd(Path(cwd)):
                    exit_code, stdout, stderr = self.run_cli_output(["version", "show", "--json"])
            finally:
                acf.ROOT = previous_root

        self.assertEqual(exit_code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["version"], acf.VERSION)
        self.assertEqual(payload["versions"]["cli"], acf.VERSION)
        self.assertIsNone(payload["versions"]["pyproject"])
        self.assertIsNone(payload["versions"]["uv_lock"])

    def test_version_set_requires_source_checkout(self):
        previous_root = acf.ROOT
        with tempfile.TemporaryDirectory() as install_dir, tempfile.TemporaryDirectory() as cwd:
            acf.ROOT = Path(install_dir)
            try:
                with pushd(Path(cwd)):
                    exit_code, stdout, stderr = self.run_cli_output(["version", "set", "v0.0.3.3", "--dry-run", "--json"])
            finally:
                acf.ROOT = previous_root

        self.assertEqual(exit_code, 2, stderr)
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_code"], "input_error")
        self.assertIn("source checkout", payload["message"])

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
                    "--write-scope",
                    "assigned: active/Current_Task.md",
                    "--output",
                    "状态机实现",
                    "--goal",
                    "实现 Workstream 状态机。",
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
            self.assertEqual(payload["normalized_write_scope"], ["assigned: active/Current_Task.md"])
            detail_text = (target / "active" / "workstreams" / "WS002.md").read_text(encoding="utf-8")
            self.assertIn("实现 Workstream 状态机。", detail_text)

    def test_workstream_add_rejects_invalid_write_scope_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)

            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "workstream",
                    "add",
                    str(target),
                    "--id",
                    "WS002",
                    "--title",
                    "无效范围",
                    "--owner",
                    "主 agent",
                    "--write-scope",
                    "active/Current_Task.md",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertEqual(payload["error_code"], "workstream_scope_invalid")
            self.assertFalse((target / "active" / "workstreams" / "WS002.md").exists())

    def test_workstream_add_goal_supports_active_check(self):
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
                        "可激活目标线",
                        "--owner",
                        "主 agent",
                        "--goal",
                        "验证 Active 状态所需目标可由 add 写入。",
                        "--output",
                        "验证记录",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "set", "WS002", str(target), "--status", "Active"]), 0)

            exit_code, stdout, stderr = self.run_cli_output(["check", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(json.loads(stdout)["ok"])

    def test_workstream_set_goal_replaces_goal_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.assertEqual(self.run_cli(["init", str(target), "--profile", "minimal"]), 0)
            self.assertEqual(self.run_cli(["workstream", "init", str(target)]), 0)
            self.add_workstream(target, "WS002")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "set",
                    "WS002",
                    str(target),
                    "--goal",
                    "补齐已有 Workstream 目标。",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "Open")
            detail_text = (target / "active" / "workstreams" / "WS002.md").read_text(encoding="utf-8")
            self.assertIn("补齐已有 Workstream 目标。", detail_text)
            self.assertNotIn("待补充。\n\n---\n\n## 当前发现", detail_text)

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
            self.assertIn(str((target / "active" / "workstreams" / "WS002.md").resolve()), payload["changed_files"])
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
            self.assertIn(str(detail_path.resolve()), payload["changed_files"])
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
            self.assertIn("merge_targets:", detail_text)
            self.assertIn("  - Context", detail_text)
            self.assertIn("  - Task_Plan", detail_text)
            self.assertIn("### 需要合并到哪里", detail_text)
            self.assertIn("- Context", detail_text)
            self.assertIn("- Task_Plan", detail_text)
            self.assertIn("候选摘要", detail_text)

    def test_workstream_ready_requires_human_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            self.assertEqual(self.run_cli(["workstream", "set", "WS002", str(target), "--status", "Active"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS002",
                        str(target),
                        "--target",
                        "active/Context.md",
                        "--summary",
                        "No authority change required.",
                        "--verification",
                        "Unit test fixture.",
                    ]
                ),
                0,
            )

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "ready", "WS002", str(target), "--json"]
            )

            self.assertNotEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assert_failure_json_contract(payload, "workstream_human_approval_required", "workstream")
            self.assertIn("--human-approved", payload["message"])
            self.assertIn("explicit approval evidence", " ".join(payload["next_actions"]))
            self.assertIn("naked --human-approved", " ".join(payload["next_actions"]))

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "ready", "WS002", str(target), "--human-approved", "--json"]
            )
            self.assertNotEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assert_failure_json_contract(payload, "workstream_human_approval_required", "workstream")

            detail_text = (target / "active" / "workstreams" / "WS002.md").read_text(encoding="utf-8")
            self.assertIn("status: Active", detail_text)

    def test_workstream_ready_reports_closeout_ledger_migration_error(self):
        from ai_context_framework import closeout_authorization as auth

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            self.assertEqual(self.run_cli(["workstream", "set", "WS002", str(target), "--status", "Active"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS002",
                        str(target),
                        "--target",
                        "active/Context.md",
                        "--summary",
                        "No authority change required.",
                        "--verification",
                        "Unit test fixture.",
                    ]
                ),
                0,
            )
            self.authorize_closeout(target, "WS002", "ready")
            project_root, _context_root = auth.project_identity(target)
            ledger_path = auth.ledger_path(project_root)
            payload = json.loads(ledger_path.read_text(encoding="utf-8"))
            payload["schema_version"] = "legacy"
            ledger_path.write_text(json.dumps(payload), encoding="utf-8")

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "ready", "WS002", str(target), "--json"]
            )
            self.assertNotEqual(exit_code, 0)
            result = json.loads(stdout)
            self.assert_failure_json_contract(
                result,
                "closeout_authorization_migration_required",
                "workstream",
            )
            self.assertIn("authorization ledger", " ".join(result["next_actions"]))

    def test_workstream_authorization_list_preserves_global_json_contract(self):
        from ai_context_framework import closeout_authorization as auth

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.set_auto_closeout_policy(target, "ready")

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "authorization", "list", str(target), "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assert_success_json_contract(payload, "workstream authorization list")
            ledger = payload["authorization_ledger"]
            self.assertEqual(ledger["schema_version"], auth.LEDGER_SCHEMA)
            self.assertGreaterEqual(ledger["revision"], 1)
            self.assertEqual(len(ledger["policies"]), 1)

    def test_workstream_ready_with_human_approval_still_rejects_unfinished_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            self.assertEqual(self.run_cli(["workstream", "set", "WS002", str(target), "--status", "Active"]), 0)
            self.write_workstream_stage_table(
                target,
                "WS002",
                [["WS002.1", "Pending", "stage", "无。", "output", "无。", "next"]],
            )
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS002",
                        str(target),
                        "--target",
                        "active/Context.md",
                        "--summary",
                        "No authority change required.",
                        "--verification",
                        "Unit test fixture.",
                    ]
                ),
                0,
            )

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "ready", "WS002", str(target), "--human-approved", "--json"]
            )

            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assert_failure_json_contract(payload, "workstream_stage_dependency_blocked", "workstream")
            self.assertIn("WS002.1", payload["message"])

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
                ["workstream", "ready", "WS002", str(target), "--human-approved", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_invalid_transition")

            self.assertEqual(self.run_cli(["workstream", "set", "WS002", str(target), "--status", "Active"]), 0)
            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "ready", "WS002", str(target), "--human-approved", "--json"]
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
            self.authorize_closeout(target, "WS002", "ready")
            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "ready", "WS002", str(target), "--human-approved", "--json"]
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
            self.authorize_closeout(target, "WS002", "ready")
            self.assertEqual(self.run_cli(["workstream", "ready", "WS002", str(target), "--human-approved"]), 0)

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "done", "WS002", str(target), "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_missing_evidence")

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "done", "WS002", str(target), "--evidence", "tests/test_cli.py", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_missing_merge_resolution")

            self.authorize_closeout(target, "WS002", "done")
            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "done",
                    "WS002",
                    str(target),
                    "--evidence",
                    "tests/test_cli.py",
                    "--merge-resolution",
                    "merged",
                    "--summary",
                    "已合并并验证",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["status"], "Done")
            detail_text = (target / "active" / "workstreams" / "WS002.md").read_text(encoding="utf-8")
            self.assertIn("status: Done", detail_text)
            self.assertIn("merge_resolution: merged", detail_text)
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
                ["workstream", "ready", "WS002", str(target), "--human-approved", "--json"]
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
            self.assertIn(str(detail_path.resolve()), json.loads(stdout)["changed_files"])
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
            self.assertIn(str(detail_path.resolve()), payload["changed_files"])
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

    def test_workstream_claim_rejects_untyped_and_conflicting_write_scopes(self):
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
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_claim_conflict")

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

    def test_workstream_context_scope_add_guard_and_dashboard(self):
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
                        "Isolation",
                        "--owner",
                        "主 agent",
                        "--output",
                        "输出物",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "set", "WS002", str(target), "--status", "Active"]), 0)

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "context", "WS002", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["workstream"]["type"], "Task")
            self.assertIn("owned: active/workstreams/WS002.md", payload["workstream"]["write_scope"])

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "scope-add",
                    "WS002",
                    str(target),
                    "--write",
                    "owned: src/foo.py",
                    "--reason",
                    "需要修改实现文件。",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn("owned: src/foo.py", payload["write_scope"])
            detail_text = (target / "active" / "workstreams" / "WS002.md").read_text(encoding="utf-8")
            self.assertIn("## Activity Log", detail_text)
            self.assertIn("需要修改实现文件。", detail_text)

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "guard", "WS002", str(target), "--changed-file", "src/foo.py", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(json.loads(stdout)["ok"])

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "guard", "WS002", str(target), "--changed-file", "active/Context.md", "--json"]
            )
            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout)
            self.assertEqual(payload["error_code"], "workstream_guard_failed")
            self.assertTrue(any("authority" in item["reason"] for item in payload["violations"]))

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "dashboard", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["counts"]["Active"], 1)
            self.assertFalse(payload["conflicts"])

    def test_workstream_merge_start_requires_merge_workstream_type(self):
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
                        "WS010",
                        "--type",
                        "Merge",
                        "--title",
                        "Merge lane",
                        "--owner",
                        "主 agent",
                        "--output",
                        "合并记录",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "set", "WS010", str(target), "--status", "Active"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS010",
                        str(target),
                        "--target",
                        "active/Task_Plan.md",
                        "--summary",
                        "Merge reviewed outputs.",
                        "--verification",
                        "Unit fixture.",
                    ]
                ),
                0,
            )
            self.authorize_closeout(target, "WS010", "ready")
            self.assertEqual(self.run_cli(["workstream", "ready", "WS010", str(target), "--human-approved"]), 0)

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "set", "WS010", str(target), "--status", "Merging", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_invalid_transition")

            self.authorize_closeout(target, "WS010", "merge")

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "merge-start", "WS010", str(target), "--summary", "Start merge.", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "Merging")
            self.assertEqual(payload["type"], "Merge")

            detail_text = (target / "active" / "workstreams" / "WS010.md").read_text(encoding="utf-8")
            self.assertIn("status: Merging", detail_text)

    def test_maintenance_workstream_can_reactivate_from_merging(self):
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
                        "WS010",
                        "--type",
                        "Maintenance",
                        "--title",
                        "Long-lived maintenance",
                        "--owner",
                        "主 agent",
                        "--output",
                        "维护记录",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "set", "WS010", str(target), "--status", "Active"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS010",
                        str(target),
                        "--target",
                        "active/Task_Plan.md",
                        "--summary",
                        "Merge reviewed maintenance patch.",
                        "--verification",
                        "Unit fixture.",
                    ]
                ),
                0,
            )
            self.authorize_closeout(target, "WS010", "ready")
            self.assertEqual(self.run_cli(["workstream", "ready", "WS010", str(target), "--human-approved"]), 0)
            self.authorize_closeout(target, "WS010", "merge")
            self.assertEqual(
                self.run_cli(
                    ["workstream", "merge-start", "WS010", str(target), "--summary", "Start maintenance merge."]
                ),
                0,
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "set", "WS010", str(target), "--status", "Active", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "Active")
            detail_text = (target / "active" / "workstreams" / "WS010.md").read_text(encoding="utf-8")
            self.assertIn("status: Active", detail_text)

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

    def test_workstream_check_accepts_padded_table_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(
                index_path.read_text(encoding="utf-8").replace(
                    "| ID | 状态 | 标题 | Owner | 写入范围 | 依赖 | 输出物 | 详情 |",
                    "| ID    | 状态   | 标题 | Owner   | 写入范围 | 依赖 | 输出物 | 详情 |",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["check", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])

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

    def test_workstream_check_title_mismatch_severity(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS002 | Open | WS002 |", "| WS002 | Open | Stale title |"), encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["check", str(target), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            warnings = json.loads(stdout)["check"]["warnings"]
            self.assertTrue(any("title mismatch" in warning for warning in warnings))

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--strict", "--json"])
            self.assertEqual(exit_code, 1)
            errors = json.loads(stdout)["check"]["errors"]
            self.assertTrue(any("title mismatch" in error for error in errors))

    def test_terminal_workstreams_keep_index_inactive(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            self.add_workstream(target, "WS003")
            self.run_cli(["workstream", "set", "WS002", str(target), "--status", "Active"])
            self.run_cli(
                [
                    "workstream",
                    "merge-request",
                    "WS002",
                    str(target),
                    "--target",
                    "active/Context.md",
                    "--summary",
                    "候选摘要",
                    "--verification",
                    "验证通过",
                ]
            )
            self.authorize_closeout(target, "WS002", "ready")
            self.run_cli(["workstream", "ready", "WS002", str(target), "--human-approved"])
            self.authorize_closeout(target, "WS002", "done")
            self.run_cli(
                [
                    "workstream",
                    "done",
                    "WS002",
                    str(target),
                    "--evidence",
                    "done evidence",
                    "--merge-resolution",
                    "merged",
                ]
            )
            self.run_cli(["workstream", "cancel", "WS003", str(target), "--reason", "取消"])
            for workstream_id in ("WS002", "WS003"):
                detail_path = target / "active" / "workstreams" / f"{workstream_id}.md"
                detail_path.write_text(
                    detail_path.read_text(encoding="utf-8").replace(
                        f"title: {workstream_id}\n",
                        f"title: {workstream_id}\nkeep_active_reason: terminal state retained for index verification\nkeep_active_until: 2099-01-01\n",
                    ),
                    encoding="utf-8",
                )

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "status", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["state"], "Inactive")

            exit_code, stdout, stderr = self.run_cli_output(["check", str(target), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["check"]["errors"], [])
            self.assertFalse(any("workstream" in warning.lower() for warning in payload["check"]["warnings"]))

    def test_workstream_sync_dry_run_previews_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            index_path = target / "active" / "Workstreams.md"
            original = index_path.read_text(encoding="utf-8")
            index_path.write_text(original.replace("| WS002 | Open | WS002 |", "| WS002 | Done | Stale title |"), encoding="utf-8")
            drifted = index_path.read_text(encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "sync", str(target), "--dry-run", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["changed_files"], [str(index_path.resolve())])
            self.assertIn("| WS002 | Open | WS002 |", payload["preview"]["content"])
            self.assertEqual(index_path.read_text(encoding="utf-8"), drifted)

    def test_workstream_sync_fixes_index_metadata_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            detail_path = target / "active" / "workstreams" / "WS002.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace("owner: 主 agent", "owner: detail owner"),
                encoding="utf-8",
            )
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS002 | Open | WS002 |", "| WS002 | Done | Stale title |"), encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "sync", str(target), "--json", "--check-after"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["changed_files"], [str(index_path.resolve())])
            synced = index_path.read_text(encoding="utf-8")
            self.assertIn("| WS002 | Open | WS002 | detail owner |", synced)
            self.assertTrue(payload["check"]["ok"])

    def test_workstream_index_compacts_long_write_scope_but_context_keeps_full_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sample-project" / "docs" / "ai"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            detail_path = target / "active" / "workstreams" / "WS002.md"
            custom_detail_note = "\n## Project-specific note\n\nKeep this customized detail unchanged.\n"
            detail_path.write_text(detail_path.read_text(encoding="utf-8") + custom_detail_note, encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "scope-add",
                    "WS002",
                    str(target),
                    "--write",
                    "assigned: src/one.py",
                    "--write",
                    "assigned: src/two.py",
                    "--write",
                    "assigned: src/three.py",
                    "--write",
                    "assigned: src/four.py",
                    "--reason",
                    "exercise compact index scope",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(len(json.loads(stdout)["write_scope"]), 5)

            index_path = target / "active" / "Workstreams.md"
            index_text = index_path.read_text(encoding="utf-8")
            self.assertIn("详情(5 项)", index_text)
            self.assertNotIn("assigned: src/one.py", index_text)

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "context", "WS002", str(target), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            context_payload = json.loads(stdout)
            self.assertIn("assigned: src/one.py", context_payload["workstream"]["write_scope"])
            self.assertIn("assigned: src/four.py", context_payload["workstream"]["write_scope"])

            full_write_scope = ", ".join(context_payload["workstream"]["write_scope"])
            index_path.write_text(
                index_path.read_text(encoding="utf-8").replace("详情(5 项)", full_write_scope),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "context", "WS002", str(target), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            legacy_context_payload = json.loads(stdout)
            self.assertEqual(legacy_context_payload["workstream"]["write_scope"], context_payload["workstream"]["write_scope"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "sync", str(target), "--json", "--check-after"]
            )
            self.assertEqual(exit_code, 0, stderr)
            legacy_sync_payload = json.loads(stdout)
            self.assertEqual(legacy_sync_payload["changed_files"], [str(index_path.resolve())])
            self.assertTrue(legacy_sync_payload["check"]["ok"])
            self.assertIn("详情(5 项)", index_path.read_text(encoding="utf-8"))

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "sync", str(target), "--json", "--check-after"]
            )
            self.assertEqual(exit_code, 0, stderr)
            sync_payload = json.loads(stdout)
            self.assertEqual(sync_payload["changed_files"], [])
            self.assertTrue(sync_payload["check"]["ok"])
            self.assertIn(custom_detail_note.strip(), detail_path.read_text(encoding="utf-8"))

    def test_workstream_sync_adds_missing_detail_row(self):
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
            index_path = target / "active" / "Workstreams.md"

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "sync", str(target), "--json", "--check-after"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["changed_files"], [str(index_path.resolve())])
            self.assertIn("| WS999 | Open | 未索引 | 主 agent | owned: active/workstreams/WS999.md | 无。 | 待补充。 | active/workstreams/WS999.md |", index_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["check"]["ok"])

    def test_workstream_sync_preserves_stale_index_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(
                index_path.read_text(encoding="utf-8")
                .replace("| WS002 | Open | WS002 |", "| WS002 | Done | Stale title |")
                .replace(
                    "| WS002 | Done | Stale title | 主 agent | owned: active/workstreams/WS002.md | 无。 | 输出物 | active/workstreams/WS002.md |",
                    "| WS404 | Open | Missing detail | 主 agent | owned: active/workstreams/WS404.md | 无。 | 输出物 | active/workstreams/WS404.md |\n| WS002 | Done | Stale title | 主 agent | owned: active/workstreams/WS002.md | 无。 | 输出物 | active/workstreams/WS002.md |",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "sync", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("| WS404 | Open | Missing detail |", index_path.read_text(encoding="utf-8"))
            self.assertIn("| WS002 | Open | WS002 |", index_path.read_text(encoding="utf-8"))

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, 1)
            self.assertTrue(any("broken Workstream detail" in error for error in json.loads(stdout)["check"]["errors"]))

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

    def test_done_workstream_requires_merge_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8")
                .replace("status: Open", "status: Done")
                .replace("## 证据\n\n无。", "## 证据\n\ndone"),
                encoding="utf-8",
            )
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS004 | Open |", "| WS004 | Done |"), encoding="utf-8")

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("Done workstream missing merge_resolution" in error for error in result.errors))

    def test_done_workstream_rejects_invalid_merge_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8")
                .replace("status: Open", "status: Done")
                .replace("title: WS004\n", "title: WS004\nmerge_resolution: maybe\n")
                .replace("## 证据\n\n无。", "## 证据\n\ndone"),
                encoding="utf-8",
            )
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS004 | Open |", "| WS004 | Done |"), encoding="utf-8")

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("merge_resolution" in error and "invalid value" in error for error in result.errors))

    def test_terminal_active_workstream_missing_retention_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8")
                .replace("status: Open", "status: Done")
                .replace("title: WS004\n", "title: WS004\nmerge_resolution: no_merge_required\n")
                .replace("## 证据\n\n无。", "## 证据\n\ndone"),
                encoding="utf-8",
            )
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS004 | Open |", "| WS004 | Done |"), encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["check", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            warnings = json.loads(stdout)["check"]["warnings"]
            self.assertTrue(any("terminal workstream remains active without keep_active_reason" in warning for warning in warnings))
            self.assertTrue(any("terminal workstream remains active without keep_active_until" in warning for warning in warnings))

    def test_strict_rejects_expired_keep_active_until(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8")
                .replace("status: Open", "status: Done")
                .replace(
                    "title: WS004\n",
                    "title: WS004\nmerge_resolution: no_merge_required\nkeep_active_reason: needed by current plan\nkeep_active_until: 2000-01-01\n",
                )
                .replace("## 证据\n\n无。", "## 证据\n\ndone"),
                encoding="utf-8",
            )
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS004 | Open |", "| WS004 | Done |"), encoding="utf-8")

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("keep_active_until `2000-01-01` is expired" in error for error in result.errors))

    def test_keep_active_until_requires_iso_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8")
                .replace("status: Open", "status: Cancelled")
                .replace("title: WS004\n", "title: WS004\nkeep_active_reason: needed\nkeep_active_until: tomorrow\n")
                .replace("## 取消原因\n\n无。", "## 取消原因\n\ncancelled"),
                encoding="utf-8",
            )
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS004 | Open |", "| WS004 | Cancelled |"), encoding="utf-8")

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("invalid keep_active_until `tomorrow`" in error for error in result.errors))

    def test_workstream_current_stage_requires_stage_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace(
                    "title: WS004\n",
                    "title: WS004\ncurrent_stage: WS004.2\n",
                ).replace("## 目标\n\n待补充。", "## 目标\n\nGoal"),
                encoding="utf-8",
            )

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("current_stage `WS004.2` is not registered" in error for error in result.errors))

    def test_workstream_stage_add_and_list_registers_only_detail_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            current_task_before = (target / "active" / "Current_Task.md").read_text(encoding="utf-8")
            context_before = (target / "active" / "Context.md").read_text(encoding="utf-8")
            index_before = (target / "active" / "Workstreams.md").read_text(encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "stage",
                    "add",
                    "WS004",
                    str(target),
                    "--id",
                    "WS004.2",
                    "--title",
                    "pct10 formal Morris",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["changed_files"], [str(detail_path.resolve())])
            self.assertIn("| WS004.2 | Pending | pct10 formal Morris |", detail_path.read_text(encoding="utf-8"))
            self.assertEqual((target / "active" / "Current_Task.md").read_text(encoding="utf-8"), current_task_before)
            self.assertEqual((target / "active" / "Context.md").read_text(encoding="utf-8"), context_before)
            self.assertEqual((target / "active" / "Workstreams.md").read_text(encoding="utf-8"), index_before)

            exit_code, stdout, stderr = self.run_cli_output(["workstream", "stage", "list", "WS004", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            stages = json.loads(stdout)["stages"]
            self.assertEqual(stages[0]["id"], "WS004.2")
            self.assertEqual(stages[0]["status"], "Pending")
            self.assertFalse(acf.check_context(target, "minimal", strict=False).errors)

            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "workstream",
                    "stage",
                    "add",
                    "WS004",
                    str(target),
                    "--id",
                    "WS004.2",
                    "--title",
                    "duplicate",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_stage_duplicate_id")

            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "workstream",
                    "stage",
                    "add",
                    "WS004",
                    str(target),
                    "--id",
                    "WS005.1",
                    "--title",
                    "foreign",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_stage_scope_invalid")

    def test_workstream_focus_sets_current_stage_and_rejects_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            self.assertEqual(self.run_cli(["workstream", "set", "WS004", str(target), "--status", "Active"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "stage",
                        "add",
                        "WS004",
                        str(target),
                        "--id",
                        "WS004.1",
                        "--title",
                        "first",
                    ]
                ),
                0,
            )
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "stage",
                        "add",
                        "WS004",
                        str(target),
                        "--id",
                        "WS004.2",
                        "--title",
                        "second",
                        "--depends",
                        "WS004.1",
                    ]
                ),
                0,
            )

            exit_code, stdout, _stderr = self.run_cli_output(["workstream", "focus", "WS004", "WS004.2", str(target), "--json"])
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_stage_dependency_blocked")

            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "stage",
                        "done",
                        "WS004",
                        "WS004.1",
                        str(target),
                        "--evidence",
                        "worklog/daily/stage-1.md",
                    ]
                ),
                0,
            )
            exit_code, stdout, stderr = self.run_cli_output(["workstream", "focus", "WS004", "WS004.2", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["current_stage"], "WS004.2")
            detail_text = (target / "active" / "workstreams" / "WS004.md").read_text(encoding="utf-8")
            self.assertIn("current_stage: WS004.2", detail_text)
            self.assertIn("| WS004.2 | Active | second | WS004.1 |", detail_text)

            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "stage",
                        "add",
                        "WS004",
                        str(target),
                        "--id",
                        "WS004.3",
                        "--title",
                        "third",
                    ]
                ),
                0,
            )
            exit_code, stdout, _stderr = self.run_cli_output(["workstream", "focus", "WS004", "WS004.3", str(target), "--json"])
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_stage_active_conflict")

    def test_workstream_stage_done_requires_evidence_and_clears_current_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            self.assertEqual(self.run_cli(["workstream", "set", "WS004", str(target), "--status", "Active"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "stage",
                        "add",
                        "WS004",
                        str(target),
                        "--id",
                        "WS004.1",
                        "--title",
                        "stage one",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "focus", "WS004", "WS004.1", str(target)]), 0)

            exit_code, stdout, _stderr = self.run_cli_output(["workstream", "stage", "done", "WS004", "WS004.1", str(target), "--json"])
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_missing_evidence")

            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "workstream",
                    "stage",
                    "done",
                    "WS004",
                    "WS004.1",
                    str(target),
                    "--evidence",
                    "output/stage-one",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(stdout)["error_code"], "workstream_stage_clear_current_required")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "stage",
                    "done",
                    "WS004",
                    "WS004.1",
                    str(target),
                    "--evidence",
                    "output/stage-one",
                    "--clear-current",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "Done")
            detail_text = (target / "active" / "workstreams" / "WS004.md").read_text(encoding="utf-8")
            self.assertNotIn("current_stage:", detail_text)
            self.assertIn("| WS004.1 | Done | stage one | 无。 | 待补充。 | output/stage-one |", detail_text)

    def test_workstream_strict_rejects_done_stage_without_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            self.write_workstream_stage_table(
                target,
                "WS004",
                [["WS004.1", "Done", "stage", "无。", "output", "无。", "next"]],
            )

            self.assertFalse(acf.check_context(target, "minimal", strict=False).errors)
            result = acf.check_context(target, "minimal", strict=True)
            self.assertTrue(any("Done workstream stage `WS004.1` missing evidence" in error for error in result.errors))

    def test_workstream_current_stage_must_belong_to_workstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace(
                    "title: WS004\n",
                    "title: WS004\ncurrent_stage: WS005.1\n",
                ),
                encoding="utf-8",
            )
            self.write_workstream_stage_table(
                target,
                "WS004",
                [["WS005.1", "Active", "foreign stage", "无。", "output", "evidence", "next"]],
            )

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("does not belong to WS004" in error for error in result.errors))

    def test_workstream_current_stage_must_be_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace(
                    "title: WS004\n",
                    "title: WS004\ncurrent_stage: WS004.2\n",
                ).replace("## 目标\n\n待补充。", "## 目标\n\nGoal"),
                encoding="utf-8",
            )
            self.write_workstream_stage_table(
                target,
                "WS004",
                [["WS004.1", "Done", "first stage", "无。", "output", "evidence", "next"]],
            )

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("current_stage `WS004.2` is not registered" in error for error in result.errors))

    def test_workstream_current_stage_accepts_registered_active_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            self.run_cli(["workstream", "set", "WS004", str(target), "--status", "Active"])
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace(
                    "title: WS004\n",
                    "title: WS004\ncurrent_stage: WS004.2\n",
                ).replace("## 目标\n\n待补充。", "## 目标\n\nGoal"),
                encoding="utf-8",
            )
            self.write_workstream_stage_table(
                target,
                "WS004",
                [
                    ["WS004.1", "Done", "first stage", "无。", "output", "evidence", "next"],
                    ["WS004.2", "Active", "second stage", "WS004.1", "output", "evidence", "next"],
                ],
            )

            result = acf.check_context(target, "minimal", strict=False)

            self.assertFalse(result.errors)

    def test_workstream_rejects_multiple_active_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            self.run_cli(["workstream", "set", "WS004", str(target), "--status", "Active"])
            self.write_workstream_stage_table(
                target,
                "WS004",
                [
                    ["WS004.1", "Active", "first stage", "无。", "output", "evidence", "next"],
                    ["WS004.2", "Active", "second stage", "无。", "output", "evidence", "next"],
                ],
            )

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("more than one Active stage" in error for error in result.errors))

    def test_terminal_workstream_rejects_active_current_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8")
                .replace("status: Open", "status: Done")
                .replace("title: WS004\n", "title: WS004\ncurrent_stage: WS004.1\n")
                .replace("## 证据\n\n无。", "## 证据\n\ndone"),
                encoding="utf-8",
            )
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS004 | Open |", "| WS004 | Done |"), encoding="utf-8")
            self.write_workstream_stage_table(
                target,
                "WS004",
                [["WS004.1", "Active", "stage", "无。", "output", "evidence", "next"]],
            )

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("terminal workstream has Active stage" in error for error in result.errors))

    def test_workstream_stage_table_optional_without_current_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")

            result = acf.check_context(target, "minimal", strict=False)

            self.assertFalse(result.errors)

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

    def test_workstream_strict_rejects_assigned_authority_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace(
                    "  - owned: active/workstreams/WS004.md\n",
                    "  - owned: active/workstreams/WS004.md\n  - assigned: active/Context.md\n",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--strict", "--json"])

            self.assertEqual(exit_code, 1)
            errors = json.loads(stdout)["check"]["errors"]
            self.assertTrue(any("authority path" in error and "assigned: active/Context.md" in error for error in errors))

    def test_workstream_strict_rejects_docs_ai_prefixed_assigned_authority_path(self):
        cases = [
            "docs/ai/active/Context.md",
            "docs\\ai\\active\\Context.md",
        ]
        for claimed_path in cases:
            with self.subTest(claimed_path=claimed_path):
                with tempfile.TemporaryDirectory() as tmp:
                    target = Path(tmp) / "ctx"
                    self.init_minimal_workstream_context(target)
                    self.add_workstream(target, "WS004")
                    detail_path = target / "active" / "workstreams" / "WS004.md"
                    detail_path.write_text(
                        detail_path.read_text(encoding="utf-8").replace(
                            "  - owned: active/workstreams/WS004.md\n",
                            f"  - owned: active/workstreams/WS004.md\n  - assigned: {claimed_path}\n",
                        ),
                        encoding="utf-8",
                    )

                    exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--strict", "--json"])

                    self.assertEqual(exit_code, 1)
                    errors = json.loads(stdout)["check"]["errors"]
                    self.assertTrue(any("authority path" in error and "assigned: docs/ai/active/Context.md" in error for error in errors))

    def test_workstream_strict_allows_docs_ai_prefixed_non_authority_project_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace(
                    "  - owned: active/workstreams/WS004.md\n",
                    "  - owned: active/workstreams/WS004.md\n  - assigned: docs/ai/worklog/writeback-drafts/WS004-draft.md\n",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--strict", "--json"])

            errors = json.loads(stdout)["check"]["errors"]
            self.assertFalse(any("authority path" in error for error in errors))

    def test_workstream_strict_rejects_owned_authority_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace(
                    "  - owned: active/workstreams/WS004.md\n",
                    "  - owned: active/workstreams/WS004.md\n  - owned: active/Current_Task.md\n",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--strict", "--json"])

            self.assertEqual(exit_code, 1)
            errors = json.loads(stdout)["check"]["errors"]
            self.assertTrue(any("authority path" in error and "owned: active/Current_Task.md" in error for error in errors))

    def test_workstream_merge_targets_authority_path_allowed_with_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace(
                    "write_scope:\n  - owned: active/workstreams/WS004.md\n",
                    "write_scope:\n  - owned: active/workstreams/WS004.md\nmerge_targets:\n  - active/Context.md\n",
                ),
                encoding="utf-8",
            )
            self.run_cli(
                [
                    "workstream",
                    "merge-request",
                    "WS004",
                    str(target),
                    "--target",
                    "active/Context.md",
                    "--summary",
                    "候选摘要",
                    "--verification",
                    "测试通过",
                ]
            )
            self.run_cli(["workstream", "set", "WS004", str(target), "--status", "Active"])
            self.authorize_closeout(target, "WS004", "ready")
            self.run_cli(["workstream", "ready", "WS004", str(target), "--human-approved"])

            result = acf.check_context(target, "minimal", strict=True)

            self.assertFalse([error for error in result.errors if "WS004" in error or "Workstreams" in error])

    def test_workstream_ready_to_merge_with_merge_targets_requires_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8")
                .replace("status: Open", "status: ReadyToMerge")
                .replace(
                    "write_scope:\n  - owned: active/workstreams/WS004.md\n",
                    "write_scope:\n  - owned: active/workstreams/WS004.md\nmerge_targets:\n  - active/Context.md\n",
                ),
                encoding="utf-8",
            )
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS004 | Open |", "| WS004 | ReadyToMerge |"), encoding="utf-8")

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("declares merge_targets but is missing merge request" in error for error in result.errors))

    def test_done_workstream_with_merge_targets_requires_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8")
                .replace("status: Open", "status: Done")
                .replace("## 证据\n\n无。", "## 证据\n\ndone")
                .replace(
                    "write_scope:\n  - owned: active/workstreams/WS004.md\n",
                    "write_scope:\n  - owned: active/workstreams/WS004.md\nmerge_targets:\n  - active/Context.md\n",
                ),
                encoding="utf-8",
            )
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(index_path.read_text(encoding="utf-8").replace("| WS004 | Open |", "| WS004 | Done |"), encoding="utf-8")

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("Done workstream declares merge_targets but is missing merge request" in error for error in result.errors))

    def test_workstream_archive_candidates_is_read_only_and_reports_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS010")
            self.assertEqual(self.run_cli(["workstream", "set", "WS010", str(target), "--status", "Active"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS010",
                        str(target),
                        "--target",
                        "active/Context.md",
                        "--summary",
                        "Archive candidate test has no authority change.",
                        "--verification",
                        "Unit test fixture.",
                    ]
                ),
                0,
            )
            self.authorize_closeout(target, "WS010", "ready")
            self.assertEqual(self.run_cli(["workstream", "ready", "WS010", str(target), "--human-approved"]), 0)
            self.authorize_closeout(target, "WS010", "done")
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "done",
                        "WS010",
                        str(target),
                        "--evidence",
                        "tests/test_cli.py",
                        "--merge-resolution",
                        "no_merge_required",
                    ]
                ),
                0,
            )
            detail = target / "active" / "workstreams" / "WS010.md"
            detail.write_text(
                detail.read_text(encoding="utf-8").replace(
                    "title: WS010\n",
                    "title: WS010\nkeep_active_reason: still explains the current plan\nkeep_active_until: 2099-01-01\n",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "archive-candidates", str(target), "--today", "2026-05-08", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "workstream archive-candidates")
            self.assertEqual(payload["candidates"], [])
            self.assertEqual(payload["blocked"][0]["id"], "WS010")
            self.assertIn("keep_active_until_not_expired", payload["blocked"][0]["blocked_by"])

            detail.write_text(detail.read_text(encoding="utf-8").replace("keep_active_until: 2099-01-01", "keep_active_until: 2026-05-01"), encoding="utf-8")
            before_detail = detail.read_text(encoding="utf-8")
            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "archive-candidates", str(target), "--today", "2026-05-08", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertEqual(payload["changed_files"], [])
            self.assertEqual(payload["candidates"][0]["id"], "WS010")
            self.assertEqual(payload["candidates"][0]["blocked_by"], [])
            self.assertEqual(detail.read_text(encoding="utf-8"), before_detail)

            (target / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n## 子任务 ID\n\nT001\n\n## 当前执行线\n\nWS010\n",
                encoding="utf-8",
            )
            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "archive-candidates", str(target), "--today", "2026-05-08", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertEqual(payload["candidates"], [])
            self.assertIn("referenced_by_current_task_execution_line", payload["blocked"][0]["blocked_by"])

    def test_workstream_archive_draft_creates_reviewable_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS011")
            self.complete_workstream(target, "WS011")
            self.add_workstream(target, "WS012")
            self.assertEqual(
                self.run_cli(["workstream", "cancel", "WS012", str(target), "--reason", "方向取消"]),
                0,
            )
            detail = target / "active" / "workstreams" / "WS012.md"
            detail.write_text(
                detail.read_text(encoding="utf-8").replace(
                    "title: WS012\n",
                    "title: WS012\nkeep_active_reason: still useful\nkeep_active_until: 2099-01-01\n",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "archive-draft", str(target), "--date", "2026-05-08", "--dry-run", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "workstream archive-draft")
            self.assertEqual(payload["candidate_count"], 1)
            self.assertEqual(payload["blocked_count"], 1)
            self.assertIn("uv run acf workstream archive WS011", payload["planned_draft"])
            self.assertIn("keep_active_until_not_expired", payload["planned_draft"])
            self.assertFalse((target / "worklog" / "archive-drafts" / "2026-05-08.md").exists())

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "archive-draft", str(target), "--date", "2026-05-08", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            draft_path = target / payload["draft_path"]
            self.assertTrue(draft_path.exists())
            draft_text = draft_path.read_text(encoding="utf-8")
            self.assertIn("## 可归档候选", draft_text)
            self.assertIn("## 暂不归档", draft_text)

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "archive-draft", str(target), "--date", "2026-05-08", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(self.json_payload(stdout)["error_code"], "workstream_archive_draft_exists")

    def test_workstream_archive_moves_detail_updates_indexes_and_checks_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS013")
            self.complete_workstream(target, "WS013")
            self.authorize_closeout(target, "WS013", "archive")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "archive",
                    "WS013",
                    str(target),
                    "--reason",
                    "reviewed in worklog/archive-drafts/2026-05-08.md",
                    "--date",
                    "2026-05-08",
                    "--dry-run",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "workstream archive")
            self.assertIn(str((target / "archive" / "workstreams" / "WS013.md").resolve()), payload["changed_files"])
            self.assertTrue((target / "active" / "workstreams" / "WS013.md").exists())

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "workstream",
                    "archive",
                    "WS013",
                    str(target),
                    "--reason",
                    "reviewed in worklog/archive-drafts/2026-05-08.md",
                    "--date",
                    "2026-05-08",
                    "--check-after",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertEqual(payload["archived_id"], "WS013")
            self.assertFalse((target / "active" / "workstreams" / "WS013.md").exists())
            self.assertTrue((target / "active" / "workstreams" / ".gitkeep").exists())
            archive_detail = target / "archive" / "workstreams" / "WS013.md"
            archive_text = archive_detail.read_text(encoding="utf-8")
            self.assertIn("ACF:WORKSTREAM:ARCHIVE-RECORD:START", archive_text)
            self.assertIn("source_path: active/workstreams/WS013.md", archive_text)
            index_text = (target / "active" / "Workstreams.md").read_text(encoding="utf-8")
            self.assertNotIn("WS013", index_text)
            self.assertIn("Inactive", index_text)
            archive_index = (target / "archive" / "Archive_Index.md").read_text(encoding="utf-8")
            self.assertIn("| 日期 | 类型 | ID | 原路径 | 归档路径 | 状态 | 原因 |", archive_index)
            self.assertIn("| 2026-05-08 | workstream | WS013 | active/workstreams/WS013.md | `archive/workstreams/WS013.md` | Done | reviewed in worklog/archive-drafts/2026-05-08.md |", archive_index)
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors, result.errors)

    def test_workstream_archive_respects_blockers_and_index_edge_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS014")
            self.complete_workstream(target, "WS014")
            (target / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n## 子任务 ID\n\nT001\n\n## 当前执行线\n\nWS014\n",
                encoding="utf-8",
            )
            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "archive", "WS014", str(target), "--reason", "reviewed", "--date", "2026-05-08", "--json"]
            )
            self.assertEqual(exit_code, 2)
            payload = self.json_payload(stdout)
            self.assertEqual(payload["error_code"], "workstream_archive_blocked")
            self.assertIn("referenced_by_current_task_execution_line", payload["message"])

            (target / "active" / "Current_Task.md").write_text("## 当前任务状态\n\nEmpty\n", encoding="utf-8")
            index_path = target / "active" / "Workstreams.md"
            index_text = index_path.read_text(encoding="utf-8")
            ws_row = next(line for line in index_text.splitlines() if "| WS014 |" in line)
            index_path.write_text(index_text.replace(ws_row, ws_row + "\n" + ws_row), encoding="utf-8")
            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "archive", "WS014", str(target), "--reason", "reviewed", "--date", "2026-05-08", "--json"]
            )
            self.assertEqual(exit_code, 2)
            self.assertEqual(self.json_payload(stdout)["error_code"], "workstream_archive_duplicate_index")

    def test_workstream_archive_warns_when_index_row_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS015")
            self.complete_workstream(target, "WS015")
            self.authorize_closeout(target, "WS015", "archive")
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(
                "\n".join(line for line in index_path.read_text(encoding="utf-8").splitlines() if "| WS015 |" not in line)
                + "\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["workstream", "archive", "WS015", str(target), "--reason", "reviewed", "--date", "2026-05-08", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertTrue(any("has no row for WS015" in warning for warning in payload["warnings"]))
            self.assertTrue((target / "archive" / "workstreams" / "WS015.md").exists())

    def test_strict_template_check_fails_on_placeholders(self):
        result = acf.check_context(acf.TEMPLATE_DIR, "standard", strict=True)
        self.assertTrue(any("placeholder" in error for error in result.errors))

    def test_template_project_rules_require_upgrade_compatibility(self):
        text = (acf.TEMPLATE_DIR / "rules" / "Project_Rules.md").read_text(encoding="utf-8")
        self.assertIn("acf upgrade", text)
        self.assertIn("旧版本上下文", text)
        self.assertIn("init/upgrade 测试", text)
        self.assertIn("upgrade compatibility runner", text)

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
            self.assertTrue((target / "reference" / "Context_Curation_Prompt.md").exists())
            self.assertFalse((target / "human" / "Human_Notes.md").exists())
            self.assertFalse((target / "decisions" / "ADR-0001-template.md").exists())
            self.assertFalse((target / "worklog" / "daily" / "YYYY-MM-DD.md").exists())
            agents_text = (target / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("## CLI 辅助维护", agents_text)
            self.assertIn("active/Task_Plan.md", agents_text)
            self.assertIn("active/Feedback_Inbox.md", agents_text)
            self.assertIn("reference/Context_Curation_Prompt.md", agents_text)
            plan_text = (target / "active" / "Task_Plan.md").read_text(encoding="utf-8")
            self.assertIn("## 规划依据", plan_text)
            self.assertIn("reference/【ACF:TODO|规划依据文档 1】.md", plan_text)
            self.assertIn("acf status --json", agents_text)
            self.assertIn("acf --help", agents_text)
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_init_force_refuses_targets_overlapping_acf_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = {
                "exact": (root / "exact-home", root / "exact-home"),
                "inside": (root / "inside-home", root / "inside-home" / "context"),
                "ancestor": (root / "ancestor" / "acf-home", root / "ancestor"),
            }
            for name, (runtime_home, target) in cases.items():
                with self.subTest(name=name):
                    runtime_home.mkdir(parents=True, exist_ok=True)
                    target.mkdir(parents=True, exist_ok=True)
                    sentinel = runtime_home / "continuation-state.json"
                    sentinel.write_text("preserve me\n", encoding="utf-8")
                    with isolated_acf_home(runtime_home):
                        exit_code, stdout, _stderr = self.run_cli_output(
                            ["init", str(target), "--force", "--json"]
                        )
                    self.assertEqual(exit_code, acf.EXIT_SAFETY_REFUSED)
                    payload = self.json_payload(stdout)
                    self.assert_failure_json_contract(
                        payload,
                        error_code="acf_home_target_protected",
                        command="init",
                    )
                    self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me\n")

    def test_simplify_force_refuses_acf_home_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self.assertEqual(self.run_cli(["init", str(source)]), 0)
            runtime_home = root / "acf-home"
            runtime_home.mkdir()
            sentinel = runtime_home / "runtime-state.json"
            sentinel.write_text("preserve me\n", encoding="utf-8")
            with isolated_acf_home(runtime_home):
                exit_code, stdout, _stderr = self.run_cli_output(
                    ["simplify", str(source), str(runtime_home), "--force", "--json"]
                )
            self.assertEqual(exit_code, acf.EXIT_SAFETY_REFUSED)
            payload = self.json_payload(stdout)
            self.assert_failure_json_contract(
                payload,
                error_code="acf_home_target_protected",
                command="simplify",
            )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me\n")

    def test_init_nonforce_target_inside_isolated_acf_home_remains_nondestructive(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_home = Path(tmp) / "acf-home"
            runtime_home.mkdir()
            target = runtime_home / "context"
            with isolated_acf_home(runtime_home):
                exit_code, stdout, _stderr = self.run_cli_output(
                    ["init", str(target), "--json"]
                )
            self.assertEqual(exit_code, 0)
            payload = self.json_payload(stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(target.exists())

    def test_observer_is_a_side_effect_free_retired_tombstone(self):
        def snapshot(root):
            state = {}
            for path in sorted(root.rglob("*")):
                relative = path.relative_to(root).as_posix()
                if path.is_dir():
                    state[relative] = "<dir>"
                else:
                    state[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            return state

        with tempfile.TemporaryDirectory() as tmp:
            runtime_home = Path(tmp) / "acf-home"
            runtime_home.mkdir()
            with isolated_acf_home(runtime_home):
                before = snapshot(runtime_home)
                exit_code, stdout, _stderr = self.run_cli_output(["observer", "--json"])
                after = snapshot(runtime_home)
            self.assertEqual(acf.EXIT_RUNTIME_ERROR, exit_code)
            payload = self.json_payload(stdout)
            self.assert_failure_json_contract(
                payload,
                error_code="observer_retired",
                command="observer",
            )
            self.assertEqual([], payload["changed_files"])
            self.assertIn("acf status --json", " ".join(payload["next_actions"]))
            self.assertEqual(before, after)

    def test_observer_tombstone_tolerates_legacy_subcommands(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_home = Path(tmp) / "acf-home"
            runtime_home.mkdir()
            with isolated_acf_home(runtime_home):
                exit_code, stdout, _stderr = self.run_cli_output(
                    ["observer", "snapshot", str(runtime_home), "--dry-run", "--json"]
                )
            self.assertEqual(acf.EXIT_RUNTIME_ERROR, exit_code)
            payload = self.json_payload(stdout)
            self.assert_failure_json_contract(
                payload,
                error_code="observer_retired",
                command="observer",
            )
            self.assertEqual([], payload["changed_files"])

    def test_init_force_allows_cleanup_outside_isolated_acf_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_home = root / "acf-home"
            runtime_home.mkdir()
            target = root / "scratch-context"
            target.mkdir()
            stale = target / "stale.txt"
            stale.write_text("replace me\n", encoding="utf-8")
            with isolated_acf_home(runtime_home):
                exit_code, stdout, _stderr = self.run_cli_output(
                    ["init", str(target), "--force", "--json"]
                )
            self.assertEqual(exit_code, 0)
            payload = self.json_payload(stdout)
            self.assertTrue(payload["ok"])
            self.assertFalse(stale.exists())

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
            self.assertTrue((target / "reference" / "Context_Curation_Prompt.md").exists())
            self.assertTrue((target / "human" / "Human_Index.md").exists())
            self.assertTrue((target / "human" / "Human_Notes.md").exists())
            self.assertTrue((target / "human" / "weekly" / ".gitkeep").exists())
            self.assertTrue((target / "human" / "reports" / ".gitkeep").exists())

            agents_text = (target / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("## CLI 辅助维护", agents_text)
            self.assertIn("acf status --json", agents_text)
            self.assertIn("reference/System_Manual.md", agents_text)
            self.assertEqual(agents_text.count("reference/Context_Curation_Prompt.md"), 1)
            human_text = (target / "human" / "Human_Notes.md").read_text(encoding="utf-8")
            self.assertIn("[[双链]]", human_text)
            human_index_text = (target / "human" / "Human_Index.md").read_text(encoding="utf-8")
            self.assertIn("默认不进入 AI 必读路径", human_index_text)
            result = acf.check_context(target, "standard", strict=False)
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

    def test_upgrade_dry_run_reports_missing_new_structure_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            for rel in (
                "active/Task_Plan.md",
                "archive/Archive_Index.md",
                "archive/feedback/.gitkeep",
                "reference/Knowledge_Index.md",
                "reference/Context_Curation_Prompt.md",
            ):
                (target / rel).unlink()

            exit_code, stdout, stderr = self.run_cli_output(
                ["upgrade", str(target), "--dry-run", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["dry_run"])
            self.assertIn("detected_features", payload)
            self.assertIn("planned_changes", payload)
            self.assertIn("skipped_changes", payload)
            self.assertIn(str((target / "active" / "Task_Plan.md").resolve()), payload["changed_files"])
            self.assertIn(str((target / "reference" / "Context_Curation_Prompt.md").resolve()), payload["changed_files"])
            self.assertIn(
                str((target / "active" / "Task_Plan.md").resolve()),
                [item["path"] for item in payload["planned_changes"]],
            )
            self.assertFalse((target / "active" / "Task_Plan.md").exists())
            self.assertFalse((target / "reference" / "Context_Curation_Prompt.md").exists())

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

    def test_upgrade_adds_missing_plan_reference_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            plan_path = target / "active" / "Task_Plan.md"
            plan_path.write_text(
                "## 大任务状态\n\nActive\n\n"
                "## 大任务名称\n\nLegacy plan\n\n"
                "## 成功标准\n\n1. Pass.\n\n"
                "## 当前焦点\n\nT001\n\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(target), "--dry-run", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn(str(plan_path.resolve()), payload["changed_files"])
            self.assertNotIn("## 规划依据", plan_path.read_text(encoding="utf-8"))

            self.assertEqual(self.run_cli(["upgrade", str(target)]), 0)
            updated = plan_path.read_text(encoding="utf-8")
            self.assertIn("## 规划依据", updated)
            self.assertIn("acf plan reference add", updated)
            self.assertLess(updated.index("## 成功标准"), updated.index("## 规划依据"))
            self.assertLess(updated.index("## 规划依据"), updated.index("## 当前焦点"))

    def test_upgrade_appends_current_task_reference_prompt_non_destructively(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            task_path = target / "active" / "Current_Task.md"
            task_path.write_text(
                "## 当前任务状态\n\nActive\n\n"
                "## 任务名称\n\nKeep me\n\n"
                "## 输入材料\n\n- 无。\n\n"
                "## 输出要求\n\n- Keep output\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(target), "--dry-run", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn(str(task_path.resolve()), payload["changed_files"])
            self.assertIn("- 无。", task_path.read_text(encoding="utf-8"))

            self.assertEqual(self.run_cli(["upgrade", str(target)]), 0)
            updated = task_path.read_text(encoding="utf-8")
            self.assertIn("Keep me", updated)
            self.assertIn("相关 reference 规划依据请查看", updated)
            self.assertNotIn("- 无。\n\n## 输出要求", updated)

    def test_upgrade_adds_missing_context_curation_prompt_without_overwriting_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            self.run_cli(["init", str(missing), "--profile", "minimal"])
            prompt = missing / "reference" / "Context_Curation_Prompt.md"
            prompt.unlink()

            exit_code = self.run_cli(["upgrade", str(missing)])

            self.assertEqual(exit_code, 0)
            self.assertTrue(prompt.exists())
            self.assertIn("默认产物是整理建议", prompt.read_text(encoding="utf-8"))

            custom = Path(tmp) / "custom"
            self.run_cli(["init", str(custom), "--profile", "minimal"])
            custom_prompt = custom / "reference" / "Context_Curation_Prompt.md"
            custom_prompt.write_text("custom curation prompt\n", encoding="utf-8")

            exit_code = self.run_cli(["upgrade", str(custom)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(custom_prompt.read_text(encoding="utf-8"), "custom curation prompt\n")

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
                "reference/Context_Curation_Prompt.md",
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
            self.assertIn(str((target / "reference" / "Context_Curation_Prompt.md").resolve()), payload["changed_files"])

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
            self.assertEqual(agents_text.count("reference/Context_Curation_Prompt.md"), 1)
            manual_text = manual.read_text(encoding="utf-8")
            self.assertIn("旧版本上下文升级", manual_text)
            self.assertIn("acf plan init|add-task|set-task|focus|complete|status", manual_text)
            self.assertTrue((target / "reference" / "Context_Curation_Prompt.md").exists())
            self.assertTrue((target / "archive" / "feedback" / ".gitkeep").exists())

    def test_upgrade_compacts_legacy_worktree_guidance_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target)])
            agents = target / "AGENTS.md"
            always_active = target / "rules" / "Always_Active.md"
            manual = target / "reference" / "System_Manual.md"

            legacy_resilient_rule = (
                "- `acf worktree merge` 必须在 ACF 管理的临时 integration worktree 中完成真实 merge 和 post-check，"
                "primary checkout 只执行碰撞保护后的 fast-forward promotion。来源 worktree 必须 clean；primary 可保留无关 "
                "staged/unstaged/untracked 修改。发生冲突、检查失败或短时并发竞争时，优先使用 operation ID 等待、重规划或 "
                "resume，不得在 primary 中直接制造冲突，也不得自动 stash、reset、clean、rebase 或 force。关闭前必须完成 "
                "ignored/untracked artifact handoff。"
            )
            task_triggered_rule = (
                "- 只有任务实际涉及 worktree 的 merge / close / recovery / artifact handoff 时，才按需查看 `acf worktree --help` "
                "和 `reference/System_Manual.md` 的对应细节；默认入口不复制完整 worktree 状态机。安全边界保持不变：不得自动 "
                "stash、reset、clean、rebase、force，也不得静默解决冲突。"
            )
            legacy_always_active_rule = (
                "12. Workstream 与 Git worktree 相互独立：创建 Workstream 不隐式创建 branch/worktree；AI 只有在任务需要隔离环境时才调用 "
                "`acf worktree create`，未使用 worktree 的原任务逻辑不得受影响。"
            )
            agents_text = agents.read_text(encoding="utf-8")
            self.assertIn(task_triggered_rule, agents_text)
            self.assertNotIn(legacy_resilient_rule, agents_text)
            self.assertNotIn(legacy_always_active_rule, always_active.read_text(encoding="utf-8"))
            agents.write_text(
                agents_text.replace(task_triggered_rule, legacy_resilient_rule)
                + "\nProject-specific AGENTS note must remain.\n",
                encoding="utf-8",
            )
            always_active.write_text(
                always_active.read_text(encoding="utf-8")
                + legacy_always_active_rule
                + "\nProject-specific always-active constraint.\n",
                encoding="utf-8",
            )

            new_manual_line = (
                "非 WS 任务使用 `--kind bugfix|docs|experiment|investigation|maintenance|refactor|release --slug ...`。"
                "`worktree list|audit|verify|attach|sync|merge-plan|merge|artifact-plan|artifact-migrate|close|retire|resume` 提供发现、恢复、同步、临时候选合并、结果迁移、安全关闭和 curated handoff 退役。"
            )
            old_manual_line = (
                "非 WS 任务使用 `--kind bugfix|docs|experiment|investigation|maintenance|refactor|release --slug ...`。"
                "`worktree list|audit|verify|attach|sync|merge-plan|merge|close|resume` 提供发现、恢复、同步、无冲突 no-ff 合并和安全关闭；"
            )
            manual_text = manual.read_text(encoding="utf-8")
            self.assertIn(new_manual_line, manual_text)
            start = manual_text.index(new_manual_line)
            end = manual_text.index("\n", start)
            manual.write_text(
                manual_text[:start]
                + old_manual_line
                + "写操作默认 plan-only，`--apply` 后执行。项目可在 `.acf/project.toml` 配置 primary checkout/branch、worktree root 和命名模板；不配置或不调用 worktree 时，原上下文与 Workstream 命令不受影响。ACF 不自动 stash、reset、clean、rebase、force、push、覆盖目录或解决冲突。"
                + manual_text[end:],
                encoding="utf-8",
            )

            self.assertEqual(self.run_cli(["upgrade", str(target)]), 0)
            upgraded_agents = agents.read_text(encoding="utf-8")
            self.assertIn(task_triggered_rule, upgraded_agents)
            self.assertNotIn(legacy_resilient_rule, upgraded_agents)
            self.assertIn("Project-specific AGENTS note must remain.", upgraded_agents)
            upgraded_always_active = always_active.read_text(encoding="utf-8")
            self.assertNotIn(legacy_always_active_rule, upgraded_always_active)
            self.assertIn("Project-specific always-active constraint.", upgraded_always_active)
            self.assertIn(new_manual_line, manual.read_text(encoding="utf-8"))

            exit_code, stdout, stderr = self.run_cli_output(
                ["upgrade", str(target), "--dry-run", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["changed_files"], [])

    def test_context_global_first_route_is_generated_and_legacy_upgrade_is_nondestructive(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sample-project" / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            context = target / "active" / "Context.md"
            current_route = (
                "- 当前执行入口按 `AGENTS.md` 的 Global-first 规则选择：未显式选择 Workstream 时保持全局上下文；"
                "选择 Workstream 后先运行 `acf workstream context WSxxx`，再按其 scope 渐进读取。"
                "`active/Current_Task.md` 只在它本身为当前全局任务时作为任务事实源。"
            )
            legacy_route = "- 当前具体任务请查看：`active/Current_Task.md`"
            context_text = context.read_text(encoding="utf-8")
            self.assertIn(current_route, context_text)
            self.assertNotIn(legacy_route, context_text)

            context.write_text(
                context_text.replace(current_route, legacy_route)
                + "\nProject-specific Context fact must remain.\n",
                encoding="utf-8",
            )
            exit_code, stdout, stderr = self.run_cli_output(
                ["upgrade", str(target), "--dry-run", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertIn(str(context.resolve()), json.loads(stdout)["changed_files"])

            self.assertEqual(self.run_cli(["upgrade", str(target)]), 0)
            upgraded_context = context.read_text(encoding="utf-8")
            self.assertIn(current_route, upgraded_context)
            self.assertNotIn(legacy_route, upgraded_context)
            self.assertIn("Project-specific Context fact must remain.", upgraded_context)

            exit_code, stdout, stderr = self.run_cli_output(
                ["upgrade", str(target), "--dry-run", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertNotIn(str(context.resolve()), json.loads(stdout)["changed_files"])

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
            self.assertEqual(payload["planned_changes"], [])
            self.assertIn("task_plan", payload["detected_features"])
            self.assertTrue(payload["skipped_changes"])
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
            self.assertEqual(agents_text.count("<!-- ACF:UPGRADE:NOTES:START -->"), 1)
            self.assertEqual(manual_text.count("<!-- ACF:UPGRADE:NOTES:START -->"), 1)
            self.assertNotIn("ACF:UPGRADE-NOTES", agents_text)
            self.assertNotIn("ACF:UPGRADE-NOTES", manual_text)
            self.assertIn("ACF Current Schema Upgrade Notes", agents_text)
            self.assertIn("ACF Current Schema Upgrade Notes", manual_text)

    def test_upgrade_migrates_legacy_marker_notes_to_canonical_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            agents = target / "AGENTS.md"
            agents.write_text(
                "Custom agent instructions.\n\n"
                "<!-- ACF:UPGRADE-NOTES:START -->\n"
                "legacy body\n"
                "<!-- ACF:UPGRADE-NOTES:END -->\n",
                encoding="utf-8",
            )

            result = acf.check_context(target, "minimal", strict=False)
            self.assertTrue(any("legacy ACF marker `ACF:UPGRADE-NOTES`" in warning for warning in result.warnings))

            exit_code, stdout, stderr = self.run_cli_output(["upgrade", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertIn(str(agents.resolve()), payload["changed_files"])
            agents_text = agents.read_text(encoding="utf-8")
            self.assertIn("<!-- ACF:UPGRADE:NOTES:START -->", agents_text)
            self.assertNotIn("ACF:UPGRADE-NOTES", agents_text)

    def test_upgrade_adds_human_layer_only_for_standard_contexts(self):
        with tempfile.TemporaryDirectory() as tmp:
            standard = Path(tmp) / "standard"
            minimal = Path(tmp) / "minimal"
            self.run_cli(["init", str(standard)])
            self.run_cli(["init", str(minimal), "--profile", "minimal"])
            shutil.rmtree(standard / "human")

            standard_exit, standard_stdout, standard_stderr = self.run_cli_output(["upgrade", str(standard), "--json"])
            self.assertEqual(standard_exit, 0, standard_stderr)
            standard_payload = self.json_payload(standard_stdout)
            self.assertIn(str((standard / "human" / "Human_Index.md").resolve()), standard_payload["changed_files"])
            self.assertIn(str((standard / "human" / "Human_Notes.md").resolve()), standard_payload["changed_files"])
            self.assertTrue((standard / "human" / "Human_Index.md").exists())
            self.assertTrue((standard / "human" / "Human_Notes.md").exists())
            self.assertIn("human/Human_Notes.md", (standard / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertIn("human", standard_payload["detected_features"])

            minimal_exit, minimal_stdout, minimal_stderr = self.run_cli_output(["upgrade", str(minimal), "--dry-run", "--json"])
            self.assertEqual(minimal_exit, 0, minimal_stderr)
            minimal_payload = self.json_payload(minimal_stdout)
            self.assertNotIn(str((minimal / "human" / "Human_Notes.md").resolve()), minimal_payload["changed_files"])
            self.assertFalse((minimal / "human" / "Human_Notes.md").exists())

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
            reference_path = target / "reference" / "Roadmap.md"
            reference_path.write_text("# Roadmap\n", encoding="utf-8")
            self.assertEqual(
                self.run_cli(
                    [
                        "plan",
                        "reference",
                        "add",
                        str(target),
                        "--path",
                        "reference/Roadmap.md",
                        "--purpose",
                        "Roadmap priority",
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
            self.assertIn("- [reference/Roadmap.md](../reference/Roadmap.md)：Roadmap priority。", task_text)
            self.assertNotIn("- - `reference/Roadmap.md`", task_text)
            self.assertIn("保持 `active/Task_Plan.md` 与 `active/Current_Task.md` 状态同步", task_text)
            self.assertIn("## 当前焦点\n\nT001", (target / "active" / "Task_Plan.md").read_text(encoding="utf-8"))

            self.assertEqual(
                self.run_cli(["task", "done", str(target), "--id", "T001", "--evidence", "unit test"]),
                0,
            )
            plan_text = (target / "active" / "Task_Plan.md").read_text(encoding="utf-8")
            self.assertIn("| T001 | Done | First slice |", plan_text)
            self.assertIn("## 当前任务状态\n\nDone", (target / "active" / "Current_Task.md").read_text(encoding="utf-8"))

    def test_doctor_reports_plan_focus_points_to_done_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Finished"])
            self.run_cli(["plan", "set-task", str(target), "--id", "T001", "--status", "Done", "--evidence", "done"])
            self.run_cli(["plan", "focus", str(target), "--id", "T001"])

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertIn(
                "plan_focus_points_to_done_task",
                {finding["code"] for finding in payload["findings"]},
            )
            finding = next(item for item in payload["findings"] if item["code"] == "plan_focus_points_to_done_task")
            self.assertEqual(finding["repair_mode"], "safe_fix")
            self.assertTrue(finding["safe_to_apply"])
            self.assertEqual(payload["summary"]["by_repair_mode"]["safe_fix"], 1)

    def test_doctor_reports_current_task_points_to_done_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Finished"])
            self.run_cli(["task", "start", str(target), "--id", "T001"])
            self.run_cli(["plan", "set-task", str(target), "--id", "T001", "--status", "Done", "--evidence", "done"])

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertIn(
                "current_task_points_to_done_task",
                {finding["code"] for finding in payload["findings"]},
            )
            finding = next(item for item in payload["findings"] if item["code"] == "current_task_points_to_done_task")
            self.assertEqual(finding["repair_mode"], "draft_only")
            self.assertFalse(finding["safe_to_apply"])

    def test_doctor_projects_reports_each_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean"
            drifted = Path(tmp) / "drifted"
            self.run_cli(["init", str(clean), "--profile", "minimal"])
            self.run_cli(["init", str(drifted), "--profile", "minimal"])
            for target in (clean, drifted):
                context_path = target / "active" / "Context.md"
                context_path.write_text(
                    context_path.read_text(encoding="utf-8")
                    + "\n\n## 审阅标记\n\n- Last reviewed: 2026-05-31\n",
                    encoding="utf-8",
                )
            self.run_cli(["plan", "init", str(drifted), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(drifted), "--id", "T001", "--title", "Finished"])
            self.run_cli(["plan", "set-task", str(drifted), "--id", "T001", "--status", "Done", "--evidence", "done"])
            self.run_cli(["plan", "focus", str(drifted), "--id", "T001"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", "--projects", str(clean), str(drifted), "--today", "2026-05-31", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertEqual(len(payload["projects"]), 2)
            by_context = {Path(item["context"]).name: item for item in payload["projects"]}
            self.assertEqual(by_context["clean"]["summary"]["findings_total"], 0)
            self.assertGreaterEqual(by_context["drifted"]["summary"]["findings_total"], 1)
            self.assertIn(
                "plan_focus_points_to_done_task",
                {finding["code"] for finding in by_context["drifted"]["findings"]},
            )

    def test_doctor_projects_reports_invalid_project_without_suppressing_valid_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean"
            invalid = Path(tmp) / "missing"
            self.run_cli(["init", str(clean), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", "--projects", str(clean), str(invalid), "--json"]
            )

            self.assertNotEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_failure_json_contract(payload, "doctor_failed", "doctor")
            self.assertEqual(len(payload["projects"]), 2)
            self.assertTrue(payload["projects"][0]["ok"])
            self.assertFalse(payload["projects"][1]["ok"])
            self.assertEqual(payload["projects"][1]["error_code"], "input_error")
            self.assertIn(str(invalid), payload["projects"][1]["context"])

    def test_doctor_projects_all_invalid_next_actions_do_not_claim_clean_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            invalid = Path(tmp) / "missing"

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", "--projects", str(invalid), "--json"]
            )

            self.assertNotEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_failure_json_contract(payload, "doctor_failed", "doctor")
            self.assertNotIn("No doctor findings found.", payload["next_actions"])
            self.assertTrue(any("per-project" in action for action in payload["next_actions"]))

    def test_doctor_check_failed_next_actions_prioritize_check_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "active" / "Context.md").unlink()

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertNotEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_failure_json_contract(payload, "check_failed", "doctor")
            self.assertNotIn("No doctor findings found.", payload["next_actions"])
            self.assertTrue(any("check" in action.lower() for action in payload["next_actions"]))

    def test_doctor_projects_fix_safe_is_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            drifted = Path(tmp) / "drifted"
            self.run_cli(["init", str(drifted), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(drifted), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(drifted), "--id", "T001", "--title", "Finished"])
            self.run_cli(["plan", "set-task", str(drifted), "--id", "T001", "--status", "Done", "--evidence", "done"])
            self.run_cli(["plan", "focus", str(drifted), "--id", "T001"])
            plan_path = drifted / "active" / "Task_Plan.md"
            before = plan_path.read_text(encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", "--projects", str(drifted), "--fix", "safe", "--json"]
            )

            self.assertNotEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_failure_json_contract(payload, "doctor_projects_fix_unsupported", "doctor")
            self.assertEqual(plan_path.read_text(encoding="utf-8"), before)

    def test_doctor_projects_report_is_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            drifted = Path(tmp) / "drifted"
            self.run_cli(["init", str(drifted), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", "--projects", str(drifted), "--report", "--today", "2026-05-31", "--json"]
            )

            self.assertNotEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_failure_json_contract(payload, "doctor_projects_write_unsupported", "doctor")
            self.assertFalse((drifted / "worklog" / "doctor-reports" / "2026-05-31.md").exists())

    def test_doctor_fix_safe_clears_done_plan_focus_without_next_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Finished"])
            self.run_cli(["plan", "set-task", str(target), "--id", "T001", "--status", "Done", "--evidence", "done"])
            self.run_cli(["plan", "focus", str(target), "--id", "T001"])

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--fix", "safe", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertIn(str((target / "active" / "Task_Plan.md").resolve()), payload["changed_files"])
            self.assertEqual(payload["summary"]["applied_repairs"], 1)
            plan_text = (target / "active" / "Task_Plan.md").read_text(encoding="utf-8")
            self.assertIn("## 当前焦点\n\n无。", plan_text)

    def test_doctor_fix_safe_keeps_done_plan_focus_when_next_task_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Finished"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T002", "--title", "Next"])
            self.run_cli(["plan", "set-task", str(target), "--id", "T001", "--status", "Done", "--evidence", "done"])
            self.run_cli(["plan", "focus", str(target), "--id", "T001"])
            plan_path = target / "active" / "Task_Plan.md"
            before = plan_path.read_text(encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--fix", "safe", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "plan_focus_points_to_done_task")
            self.assertEqual(finding["repair_mode"], "draft_only")
            self.assertFalse(finding["safe_to_apply"])
            self.assertEqual(payload["changed_files"], [])
            self.assertEqual(plan_path.read_text(encoding="utf-8"), before)

    def test_doctor_fix_safe_dry_run_reports_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Finished"])
            self.run_cli(["plan", "set-task", str(target), "--id", "T001", "--status", "Done", "--evidence", "done"])
            self.run_cli(["plan", "focus", str(target), "--id", "T001"])
            plan_path = target / "active" / "Task_Plan.md"
            before = plan_path.read_text(encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--fix", "safe", "--dry-run", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertIs(payload["dry_run"], True)
            self.assertIn(str(plan_path.resolve()), payload["changed_files"])
            self.assertEqual(plan_path.read_text(encoding="utf-8"), before)

    def test_doctor_fix_safe_removes_terminal_workstream_assigned_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            self.complete_workstream(target, "WS004")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace(
                    "  - owned: active/workstreams/WS004.md\n",
                    "  - owned: active/workstreams/WS004.md\n  - assigned: active/Context.md\n",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--fix", "safe", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertIn(
                "terminal_workstream_assigned_authority",
                {finding["code"] for finding in payload["findings"]},
            )
            self.assertIn(str(detail_path.resolve()), payload["changed_files"])
            detail_text = detail_path.read_text(encoding="utf-8")
            self.assertIn("  - owned: active/workstreams/WS004.md", detail_text)
            self.assertNotIn("assigned: active/Context.md", detail_text)

    def test_doctor_report_dry_run_includes_planned_report_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Finished"])
            self.run_cli(["plan", "set-task", str(target), "--id", "T001", "--status", "Done", "--evidence", "done"])
            self.run_cli(["plan", "focus", str(target), "--id", "T001"])
            report_path = target / "worklog" / "doctor-reports" / "2026-05-31.md"

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--report", "--today", "2026-05-31", "--dry-run", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertEqual(payload["report_path"], "worklog/doctor-reports/2026-05-31.md")
            self.assertIn(str(report_path.resolve()), payload["changed_files"])
            self.assertIn("plan_focus_points_to_done_task", payload["planned_report"])
            self.assertFalse(report_path.exists())

    def test_doctor_report_creates_reviewable_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Finished"])
            self.run_cli(["plan", "set-task", str(target), "--id", "T001", "--status", "Done", "--evidence", "done"])
            self.run_cli(["plan", "focus", str(target), "--id", "T001"])
            report_path = target / "worklog" / "doctor-reports" / "2026-05-31.md"

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--report", "--today", "2026-05-31", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertEqual(payload["report_path"], "worklog/doctor-reports/2026-05-31.md")
            self.assertTrue(report_path.exists())
            report_text = report_path.read_text(encoding="utf-8")
            self.assertIn("# ACF Doctor Report: 2026-05-31", report_text)
            self.assertIn("plan_focus_points_to_done_task", report_text)

    def test_doctor_report_exists_does_not_apply_safe_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Finished"])
            self.run_cli(["plan", "set-task", str(target), "--id", "T001", "--status", "Done", "--evidence", "done"])
            self.run_cli(["plan", "focus", str(target), "--id", "T001"])
            plan_path = target / "active" / "Task_Plan.md"
            before = plan_path.read_text(encoding="utf-8")
            report_path = target / "worklog" / "doctor-reports" / "2026-05-31.md"
            report_path.parent.mkdir(parents=True)
            report_path.write_text("existing\n", encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--fix", "safe", "--report", "--today", "2026-05-31", "--json"]
            )

            self.assertNotEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_failure_json_contract(payload, "doctor_report_exists", "doctor")
            self.assertEqual(plan_path.read_text(encoding="utf-8"), before)

    def test_doctor_report_creates_clean_report_when_no_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8")
                + "\n\n## 审阅标记\n\n- Last reviewed: 2026-05-31\n",
                encoding="utf-8",
            )
            report_path = target / "worklog" / "doctor-reports" / "2026-05-31.md"

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--report", "--today", "2026-05-31", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertEqual(payload["summary"]["findings_total"], 0)
            self.assertEqual(payload["report_path"], "worklog/doctor-reports/2026-05-31.md")
            self.assertTrue(payload["created_report"])
            self.assertIn(str(report_path.resolve()), payload["changed_files"])
            self.assertIn("No doctor findings found.", report_path.read_text(encoding="utf-8"))

    def test_doctor_draft_semantic_creates_writeback_draft_for_non_safe_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Finished"])
            self.run_cli(["task", "start", str(target), "--id", "T001"])
            self.run_cli(["plan", "set-task", str(target), "--id", "T001", "--status", "Done", "--evidence", "done"])
            draft_path = target / "worklog" / "writeback-drafts" / "2026-05-31-doctor.md"

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--draft-semantic", "--today", "2026-05-31", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertEqual(payload["draft_path"], "worklog/writeback-drafts/2026-05-31-doctor.md")
            self.assertIn(str(draft_path.resolve()), payload["changed_files"])
            self.assertTrue(draft_path.exists())
            draft_text = draft_path.read_text(encoding="utf-8")
            self.assertIn("current_task_points_to_done_task", draft_text)
            self.assertNotIn("plan_focus_points_to_done_task", draft_text)

    def test_doctor_draft_exists_does_not_apply_safe_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Finished"])
            self.run_cli(["plan", "set-task", str(target), "--id", "T001", "--status", "Done", "--evidence", "done"])
            self.run_cli(["plan", "focus", str(target), "--id", "T001"])
            plan_path = target / "active" / "Task_Plan.md"
            before = plan_path.read_text(encoding="utf-8")
            draft_path = target / "worklog" / "writeback-drafts" / "2026-05-31-doctor.md"
            draft_path.parent.mkdir(parents=True)
            draft_path.write_text("existing\n", encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--fix", "safe", "--draft-semantic", "--today", "2026-05-31", "--json"]
            )

            self.assertNotEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_failure_json_contract(payload, "doctor_draft_exists", "doctor")
            self.assertEqual(plan_path.read_text(encoding="utf-8"), before)

    def test_doctor_draft_semantic_creates_empty_draft_when_no_semantic_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8")
                + "\n\n## 审阅标记\n\n- Last reviewed: 2026-05-31\n",
                encoding="utf-8",
            )
            draft_path = target / "worklog" / "writeback-drafts" / "2026-05-31-doctor.md"

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--draft-semantic", "--today", "2026-05-31", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertEqual(payload["draft_path"], "worklog/writeback-drafts/2026-05-31-doctor.md")
            self.assertTrue(payload["created_draft"])
            self.assertIn(str(draft_path.resolve()), payload["changed_files"])
            self.assertIn("无需要语义回写的 finding。", draft_path.read_text(encoding="utf-8"))

    def test_doctor_reports_plan_current_task_status_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "plan_current_task_status_mismatch")
            self.assertEqual(finding["repair_mode"], "draft_only")

    def test_doctor_reports_current_task_wrong_completion_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T002", "--title", "Second"])
            self.run_cli(["task", "start", str(target), "--id", "T002"])
            current_path = target / "active" / "Current_Task.md"
            current_path.write_text(
                current_path.read_text(encoding="utf-8").replace(
                    "5. 应归档到 archive 的历史内容。",
                    "5. 应归档到 archive 的历史内容。\n6. 完成后将 T001 写回任务板。",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "current_task_wrong_completion_target")
            self.assertEqual(finding["repair_mode"], "safe_fix")
            self.assertTrue(finding["safe_to_apply"])

    def test_doctor_fix_safe_rewrites_current_task_wrong_completion_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T002", "--title", "Second"])
            self.run_cli(["task", "start", str(target), "--id", "T002"])
            current_path = target / "active" / "Current_Task.md"
            current_path.write_text(
                current_path.read_text(encoding="utf-8").replace(
                    "5. 应归档到 archive 的历史内容。",
                    "5. 应归档到 archive 的历史内容。\n6. 完成后将 T001 写回任务板。",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--fix", "safe", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertIn(str(current_path.resolve()), payload["changed_files"])
            current_text = current_path.read_text(encoding="utf-8")
            self.assertIn("完成后将 T002 写回任务板", current_text)
            self.assertNotIn("完成后将 T001 写回任务板", current_text)

    def test_doctor_ignores_dependency_task_ids_in_completion_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T002", "--title", "Second"])
            self.run_cli(["task", "start", str(target), "--id", "T002"])
            current_path = target / "active" / "Current_Task.md"
            current_path.write_text(
                current_path.read_text(encoding="utf-8").replace(
                    "5. 应归档到 archive 的历史内容。",
                    "5. 应归档到 archive 的历史内容。\n6. 保留依赖 T001 的证据链接。",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertNotIn(
                "current_task_wrong_completion_target",
                {finding["code"] for finding in payload["findings"]},
            )

    def test_doctor_ignores_completion_section_dependency_line_with_update_word(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T002", "--title", "Second"])
            self.run_cli(["task", "start", str(target), "--id", "T002"])
            current_path = target / "active" / "Current_Task.md"
            current_path.write_text(
                current_path.read_text(encoding="utf-8").replace(
                    "5. 应归档到 archive 的历史内容。",
                    "5. 应归档到 archive 的历史内容。\n6. 完成后保留依赖 T001 的更新证据链接。",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--fix", "safe", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertNotIn(
                "current_task_wrong_completion_target",
                {finding["code"] for finding in payload["findings"]},
            )
            self.assertNotIn(str(current_path.resolve()), payload["changed_files"])
            self.assertIn("完成后保留依赖 T001", current_path.read_text(encoding="utf-8"))

    def test_doctor_ignores_completion_section_dependency_status_update_evidence_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T002", "--title", "Second"])
            self.run_cli(["task", "start", str(target), "--id", "T002"])
            current_path = target / "active" / "Current_Task.md"
            current_path.write_text(
                current_path.read_text(encoding="utf-8").replace(
                    "5. 应归档到 archive 的历史内容。",
                    "5. 应归档到 archive 的历史内容。\n6. 完成后保留依赖 T001 的状态更新证据链接。",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--fix", "safe", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertNotIn(
                "current_task_wrong_completion_target",
                {finding["code"] for finding in payload["findings"]},
            )
            self.assertNotIn(str(current_path.resolve()), payload["changed_files"])
            self.assertIn("完成后保留依赖 T001 的状态更新证据链接", current_path.read_text(encoding="utf-8"))

    def test_doctor_downgrades_completion_target_with_extra_task_refs_to_draft_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T002", "--title", "Second"])
            self.run_cli(["task", "start", str(target), "--id", "T002"])
            current_path = target / "active" / "Current_Task.md"
            current_path.write_text(
                current_path.read_text(encoding="utf-8").replace(
                    "5. 应归档到 archive 的历史内容。",
                    "5. 应归档到 archive 的历史内容。\n6. 保留依赖 T001 的证据链接。\n7. 完成后将 T003 写回任务板。",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--fix", "safe", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "current_task_wrong_completion_target")
            self.assertEqual(finding["repair_mode"], "draft_only")
            self.assertFalse(finding["safe_to_apply"])
            self.assertNotIn(str(current_path.resolve()), payload["changed_files"])
            current_text = current_path.read_text(encoding="utf-8")
            self.assertIn("保留依赖 T001", current_text)
            self.assertIn("完成后将 T003 写回任务板", current_text)

    def test_doctor_reports_terminal_workstream_keep_active_expired(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS006")
            self.complete_workstream(target, "WS006")
            detail_path = target / "active" / "workstreams" / "WS006.md"
            detail_path.write_text(
                detail_path.read_text(encoding="utf-8").replace(
                    "merge_resolution: no_merge_required\n",
                    "merge_resolution: no_merge_required\nkeep_active_reason: test retention\nkeep_active_until: 2026-05-01\n",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--today", "2026-05-31", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "terminal_workstream_keep_active_expired")
            self.assertEqual(finding["repair_mode"], "draft_only")

    def test_doctor_reports_source_index_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            target = project / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            sources_path = target / "reference" / "Sources_Index.md"
            sources_path.write_text(
                sources_path.read_text(encoding="utf-8").replace(
                    "| 【ACF:TODO】 | 【ACF:TODO】 | 【ACF:TODO】 | 【ACF:TODO】 | 【ACF:TODO】 | 【ACF:TODO】 | 【ACF:TODO】 |",
                    "| Local doc | Document | docs/missing.md | Useful | local | test fixture | verify path |",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "source_index_missing_file")
            self.assertEqual(finding["repair_mode"], "evidence_fix")
            self.assertNotIn("data_lineage_missing", {finding["code"] for finding in payload["findings"]})

    def test_doctor_reports_context_too_thick(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8").rstrip()
                + "\n\n## 运行记录\n\n"
                + "\n".join(f"- 运行记录 {index}: stdout probe result" for index in range(230))
                + "\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "context_too_thick")
            self.assertEqual(finding["repair_mode"], "draft_only")

    def test_doctor_context_too_thick_ignores_single_generic_log_word(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8").rstrip()
                + "\n\n"
                + "\n".join(f"- 当前事实 {index}: 保持默认上下文轻量。" for index in range(230))
                + "\n- usage event log 是用户级运行态观测数据，日志写入失败不应影响原命令退出码。\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertNotIn("context_too_thick", {finding["code"] for finding in payload["findings"]})

    def test_doctor_reports_root_probe_outputs_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            target = project / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            for index in range(6):
                (project / f"probe_result_{index}.json").write_text("{}", encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "root_probe_outputs_detected")
            self.assertEqual(finding["repair_mode"], "draft_only")

    def test_doctor_reports_active_terminal_workstreams_excessive(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            for number in range(1, 7):
                workstream_id = f"WS{number:03d}"
                self.add_workstream(target, workstream_id)
                self.complete_workstream(target, workstream_id)

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "active_terminal_workstreams_excessive")
            self.assertEqual(finding["repair_mode"], "draft_only")

    def test_doctor_fix_safe_syncs_workstream_index_detail_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS007")
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(
                index_path.read_text(encoding="utf-8").replace("| WS007 | Open |", "| WS007 | Active |"),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--fix", "safe", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "workstream_index_detail_status_mismatch")
            self.assertTrue(finding["safe_to_apply"])
            self.assertIn(str(index_path.resolve()), payload["changed_files"])
            self.assertIn("| WS007 | Open |", index_path.read_text(encoding="utf-8"))

    def test_doctor_fix_safe_syncs_archive_index_missing_workstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            archive_dir = target / "archive" / "workstreams"
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_path = archive_dir / "WS099.md"
            archive_path.write_text(
                "---\n"
                "id: WS099\n"
                "type: Task\n"
                "status: Done\n"
                "owner: tester\n"
                "title: Archived WS\n"
                "depends_on: []\n"
                "read_scope: []\n"
                "write_scope: []\n"
                "merge_resolution: merged\n"
                "---\n\n"
                "# WS099\n\n"
                "<!-- ACF:WORKSTREAM:ARCHIVE-RECORD:START -->\n"
                "## 归档记录\n\n"
                "- archived_at: 2026-05-01\n"
                "- source_path: active/workstreams/WS099.md\n"
                "- archive_path: `archive/workstreams/WS099.md`\n"
                "- archive_reason: test archive\n"
                "<!-- ACF:WORKSTREAM:ARCHIVE-RECORD:END -->\n",
                encoding="utf-8",
            )
            index_path = target / "archive" / "Archive_Index.md"

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--fix", "safe", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "archive_index_missing_workstream")
            self.assertTrue(finding["safe_to_apply"])
            self.assertIn(str(index_path.resolve()), payload["changed_files"])
            self.assertIn("WS099", index_path.read_text(encoding="utf-8"))

    def test_doctor_reports_non_workstream_archive_index_drift_with_generic_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            archive_dir = target / "archive" / "tasks"
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_path = archive_dir / "2026-05-01-old-task.md"
            archive_path.write_text(
                "## 任务名称\n\nOld Task\n\n"
                f"{acf.ARCHIVE_RECORD_MARKER_START}\n"
                "- archived_at: 2026-05-01\n"
                "- item_type: Task\n"
                "- item_id: Old Task\n"
                "- source_path: active/Current_Task.md\n"
                "- archive_path: `archive/tasks/2026-05-01-old-task.md`\n"
                "- status: Archived\n"
                "- archive_reason: test archive\n"
                f"{acf.ARCHIVE_RECORD_MARKER_END}\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            codes = {finding["code"] for finding in payload["findings"]}
            self.assertIn("archive_index_generated_block_out_of_sync", codes)
            self.assertNotIn("archive_index_missing_workstream", codes)

    def test_doctor_fix_safe_repairs_workstream_protocol_missing_merging(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(
                index_path.read_text(encoding="utf-8").replace(
                    "Active、Blocked、ReadyToMerge 或 Merging",
                    "Active、Blocked 或 ReadyToMerge",
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--fix", "safe", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "workstream_index_protocol_missing_merging")
            self.assertTrue(finding["safe_to_apply"])
            self.assertIn(str(index_path.resolve()), payload["changed_files"])
            self.assertIn("Active、Blocked、ReadyToMerge 或 Merging", index_path.read_text(encoding="utf-8"))

    def test_doctor_fix_safe_repairs_agents_protocol_missing_merging(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            agents_path = target / "AGENTS.md"
            agents_path.write_text(
                agents_path.read_text(encoding="utf-8").rstrip()
                + "\n\n6. `active/Workstreams.md`（仅当存在 Active、Blocked 或 ReadyToMerge workstream 时读取）\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--fix", "safe", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "workstream_index_protocol_missing_merging")
            self.assertIn("AGENTS.md", finding["locations"])
            self.assertIn(str(agents_path.resolve()), payload["changed_files"])
            self.assertIn("Active、Blocked、ReadyToMerge 或 Merging", agents_path.read_text(encoding="utf-8"))

    def test_doctor_fix_safe_counts_repairs_separately_from_changed_files_on_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS008")
            index_path = target / "active" / "Workstreams.md"
            index_path.write_text(
                index_path.read_text(encoding="utf-8")
                .replace("| WS008 | Open |", "| WS008 | Active |")
                .replace("Active、Blocked、ReadyToMerge 或 Merging", "Active、Blocked 或 ReadyToMerge"),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--fix", "safe", "--dry-run", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertEqual(payload["summary"]["planned_repairs"], 2)
            self.assertEqual(payload["summary"]["applied_repairs"], 0)
            self.assertEqual(payload["summary"]["changed_repair_files"], 1)
            self.assertEqual(payload["changed_files"], [str(index_path.resolve())])

    def test_doctor_reports_decisions_index_summary_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "decisions" / "ADR-0001.md").write_text(
                "# Decision\n\n## 状态\n\nActive\n",
                encoding="utf-8",
            )
            decisions_path = target / "reference" / "Decisions_Index.md"
            decisions_path.write_text(
                decisions_path.read_text(encoding="utf-8").replace(
                    "| 暂无 |  |  |  |  |",
                    "| ADR-0001 | Decision | Active | 采用方案： | `decisions/ADR-0001.md` |",
                    1,
                ),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(item for item in payload["findings"] if item["code"] == "decisions_index_summary_truncated")
            self.assertEqual(finding["repair_mode"], "draft_only")

    def test_doctor_reports_duplicate_data_hash_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            target = project / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            left = project / "data" / "source.csv"
            right = project / "thesis_ch4" / "data" / "source.csv"
            left.parent.mkdir(parents=True)
            right.parent.mkdir(parents=True)
            left.write_text("x,y\n1,2\n", encoding="utf-8")
            right.write_text("x,y\n1,2\n", encoding="utf-8")
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8").rstrip()
                + "\n\n数据副本待确认：`data/source.csv` 与 `thesis_ch4/data/source.csv`。\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(
                item for item in payload["findings"] if item["code"] == "duplicate_data_hash_confirmed"
            )
            self.assertEqual(finding["repair_mode"], "evidence_fix")
            self.assertFalse(finding["safe_to_apply"])
            self.assertIn("data/source.csv", finding["message"])
            self.assertIn("data_lineage_missing", {finding["code"] for finding in payload["findings"]})

    def test_doctor_fix_evidence_plans_evidence_repairs_without_writing_authority_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            target = project / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            left = project / "data" / "source.csv"
            right = project / "copy" / "source.csv"
            left.parent.mkdir(parents=True)
            right.parent.mkdir(parents=True)
            left.write_text("x,y\n1,2\n", encoding="utf-8")
            right.write_text("x,y\n1,2\n", encoding="utf-8")
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8").rstrip()
                + "\n\n数据副本待确认：`data/source.csv` 与 `copy/source.csv`。\n",
                encoding="utf-8",
            )
            before = context_path.read_text(encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--fix", "evidence", "--dry-run", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertIn("duplicate_data_hash_confirmed", {finding["code"] for finding in payload["findings"]})
            self.assertEqual(payload["summary"]["planned_repairs"], 1)
            self.assertEqual(payload["summary"]["planned_evidence_repairs"], 1)
            self.assertEqual(payload["summary"]["applied_repairs"], 0)
            self.assertEqual(payload["changed_files"], [])
            self.assertEqual(context_path.read_text(encoding="utf-8"), before)

    def test_doctor_reports_duplicate_data_hash_from_plain_paths_in_same_paragraph(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            target = project / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            left = project / "data" / "source.csv"
            right = project / "copy" / "source.csv"
            left.parent.mkdir(parents=True)
            right.parent.mkdir(parents=True)
            left.write_text("x,y\n1,2\n", encoding="utf-8")
            right.write_text("x,y\n1,2\n", encoding="utf-8")
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8").rstrip()
                + "\n\n数据副本待确认：data/source.csv 与 copy/source.csv。\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(
                item for item in payload["findings"] if item["code"] == "duplicate_data_hash_confirmed"
            )
            self.assertIn("data/source.csv", finding["message"])
            self.assertIn("copy/source.csv", finding["message"])

    def test_doctor_reports_duplicate_data_hash_from_plain_paths_in_table_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            target = project / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            left = project / "data" / "source.csv"
            right = project / "copy" / "source.csv"
            left.parent.mkdir(parents=True)
            right.parent.mkdir(parents=True)
            left.write_text("x,y\n1,2\n", encoding="utf-8")
            right.write_text("x,y\n1,2\n", encoding="utf-8")
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8").rstrip()
                + "\n\n| 说明 | 文件 A | 文件 B |\n|---|---|---|\n| 副本 | data/source.csv | copy/source.csv |\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertIn("duplicate_data_hash_confirmed", {finding["code"] for finding in payload["findings"]})

    def test_doctor_data_refs_ignore_absolute_paths_outside_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            target = project / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            inside = project / "data" / "source.csv"
            outside = Path(tmp) / "outside" / "source.csv"
            inside.parent.mkdir(parents=True)
            outside.parent.mkdir(parents=True)
            inside.write_text("x,y\n1,2\n", encoding="utf-8")
            outside.write_text("x,y\n1,2\n", encoding="utf-8")
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8").rstrip()
                + f"\n\n数据副本待确认：`data/source.csv` 与 `{outside.as_posix()}`。\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertNotIn(
                "duplicate_data_hash_confirmed",
                {finding["code"] for finding in payload["findings"]},
            )

    def test_doctor_data_refs_resolve_markdown_links_relative_to_source_file_inside_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            target = project / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            left = project / "data" / "source.csv"
            right = project / "thesis_ch4" / "data" / "source.csv"
            left.parent.mkdir(parents=True)
            right.parent.mkdir(parents=True)
            left.write_text("x,y\n1,2\n", encoding="utf-8")
            right.write_text("x,y\n1,2\n", encoding="utf-8")
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8").rstrip()
                + "\n\n数据副本待确认：[data/source.csv](../../../data/source.csv) 与 "
                + "[thesis_ch4/data/source.csv](../../../thesis_ch4/data/source.csv)。\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(
                item for item in payload["findings"] if item["code"] == "duplicate_data_hash_confirmed"
            )
            self.assertIn("../../../data/source.csv", finding["message"])

    def test_doctor_reports_declared_duplicate_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            target = project / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            existing = project / "thesis_ch4" / "data" / "missing.csv"
            existing.parent.mkdir(parents=True)
            existing.write_text("x,y\n1,2\n", encoding="utf-8")
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8").rstrip()
                + "\n\n数据副本待确认：`data/missing.csv` 与 `thesis_ch4/data/missing.csv`。\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            finding = next(
                item for item in payload["findings"] if item["code"] == "declared_duplicate_missing"
            )
            self.assertEqual(finding["repair_mode"], "evidence_fix")
            self.assertFalse(finding["safe_to_apply"])
            self.assertIn("data/missing.csv", finding["message"])

    def test_doctor_ignores_unrelated_same_basename_data_refs_in_different_paragraphs(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            target = project / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            existing = project / "data" / "source.csv"
            existing.parent.mkdir(parents=True)
            existing.write_text("x,y\n1,2\n", encoding="utf-8")
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8").rstrip()
                + "\n\n输入文件：`data/source.csv`。\n\n历史说明提到另一路径：`archive/source.csv`。\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertNotIn(
                "declared_duplicate_missing",
                {finding["code"] for finding in payload["findings"]},
            )

    def test_doctor_ignores_unrelated_same_basename_data_refs_in_adjacent_list_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            target = project / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            existing = project / "data" / "source.csv"
            existing.parent.mkdir(parents=True)
            existing.write_text("x,y\n1,2\n", encoding="utf-8")
            context_path = target / "active" / "Context.md"
            context_path.write_text(
                context_path.read_text(encoding="utf-8").rstrip()
                + "\n\n- 输入文件：`data/source.csv`。\n- 历史说明提到另一路径：`archive/source.csv`。\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["doctor", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "doctor")
            self.assertNotIn(
                "declared_duplicate_missing",
                {finding["code"] for finding in payload["findings"]},
            )

    def test_plan_reference_commands_manage_basis_entries_and_sync_current_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "First"])
            self.run_cli(["task", "start", str(target), "--id", "T001"])
            (target / "reference" / "roadmap").mkdir()
            (target / "reference" / "roadmap" / "Plan.md").write_text("# Plan\n", encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "plan",
                    "reference",
                    "add",
                    str(target),
                    "--path",
                    "reference\\roadmap\\Plan.md",
                    "--purpose",
                    "Roadmap priority",
                    "--sync-current-task",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["references"], [{"path": "reference/roadmap/Plan.md", "purpose": "Roadmap priority。"}])
            self.assertIn(str((target / "active" / "Task_Plan.md").resolve()), payload["changed_files"])
            self.assertIn(str((target / "active" / "Current_Task.md").resolve()), payload["changed_files"])
            task_text = (target / "active" / "Current_Task.md").read_text(encoding="utf-8")
            self.assertIn("- [reference/roadmap/Plan.md](../reference/roadmap/Plan.md)：Roadmap priority。", task_text)

            duplicate_exit = self.run_cli(
                [
                    "plan",
                    "reference",
                    "add",
                    str(target),
                    "--path",
                    "reference/roadmap/Plan.md",
                    "--purpose",
                    "New purpose",
                ]
            )
            self.assertNotEqual(duplicate_exit, 0)

            self.assertEqual(
                self.run_cli(
                    [
                        "plan",
                        "reference",
                        "add",
                        str(target),
                        "--path",
                        "reference/roadmap/Plan.md",
                        "--purpose",
                        "Updated priority",
                        "--force",
                        "--sync-current-task",
                    ]
                ),
                0,
            )
            self.assertIn(
                "- [reference/roadmap/Plan.md](../reference/roadmap/Plan.md)：Updated priority。",
                (target / "active" / "Current_Task.md").read_text(encoding="utf-8"),
            )

            exit_code, stdout, stderr = self.run_cli_output(["plan", "reference", "list", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["count"], 1)

            self.assertEqual(
                self.run_cli(
                    [
                        "plan",
                        "reference",
                        "remove",
                        str(target),
                        "--path",
                        "reference/roadmap/Plan.md",
                        "--sync-current-task",
                    ]
                ),
                0,
            )
            self.assertNotIn(
                "reference/roadmap/Plan.md",
                (target / "active" / "Current_Task.md").read_text(encoding="utf-8"),
            )

    def test_plan_reference_allows_missing_explicitly_and_skips_non_active_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])

            missing_exit = self.run_cli(
                [
                    "plan",
                    "reference",
                    "add",
                    str(target),
                    "--path",
                    "reference/Missing.md",
                    "--purpose",
                    "Missing reference",
                ]
            )
            self.assertNotEqual(missing_exit, 0)

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "plan",
                    "reference",
                    "add",
                    str(target),
                    "--path",
                    "reference/Missing.md",
                    "--purpose",
                    "Missing reference",
                    "--allow-missing",
                    "--sync-current-task",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(any("does not exist" in warning for warning in payload["warnings"]))
            self.assertTrue(any("not Active" in warning for warning in payload["warnings"]))
            self.assertEqual(payload["changed_files"], [str((target / "active" / "Task_Plan.md").resolve())])

    def test_plan_reference_dry_run_and_nonstandard_sync_are_conservative(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "First"])
            self.run_cli(["task", "start", str(target), "--id", "T001"])
            reference_path = target / "reference" / "Plan.md"
            reference_path.write_text("# Plan\n", encoding="utf-8")

            task_path = target / "active" / "Current_Task.md"
            before_task = task_path.read_text(encoding="utf-8")
            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "plan",
                    "reference",
                    "add",
                    str(target),
                    "--path",
                    "reference/Plan.md",
                    "--purpose",
                    "Dry-run basis",
                    "--sync-current-task",
                    "--dry-run",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertIn(str((target / "active" / "Task_Plan.md").resolve()), payload["changed_files"])
            self.assertIn(str(task_path.resolve()), payload["changed_files"])
            self.assertEqual(task_path.read_text(encoding="utf-8"), before_task)

            task_path.write_text(before_task.replace("- `active/Context.md`。", "- see `reference/Plan.md` for details"), encoding="utf-8")
            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "plan",
                    "reference",
                    "add",
                    str(target),
                    "--path",
                    "reference/Plan.md",
                    "--purpose",
                    "Real basis",
                    "--sync-current-task",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(any("non-standard reference line" in warning for warning in payload["warnings"]))
            self.assertEqual(payload["changed_files"], [str((target / "active" / "Task_Plan.md").resolve())])
            self.assertNotIn("Real basis", task_path.read_text(encoding="utf-8"))

    def test_task_start_ignores_placeholder_plan_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "First"])
            plan_path = target / "active" / "Task_Plan.md"
            plan_text = plan_path.read_text(encoding="utf-8")
            plan_path.write_text(
                plan_text.replace(
                    "- 无。",
                    "- `reference/【规划依据文档】.md`：【该规划依据的用途】。",
                    1,
                ),
                encoding="utf-8",
            )

            self.assertEqual(self.run_cli(["task", "start", str(target), "--id", "T001"]), 0)

            task_text = (target / "active" / "Current_Task.md").read_text(encoding="utf-8")
            self.assertIn("相关 reference 规划依据请查看", task_text)
            self.assertNotIn("- - 相关 reference 规划依据", task_text)
            self.assertNotIn("【规划依据文档】", task_text)

    def test_plan_reference_remove_missing_ok_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "plan",
                    "reference",
                    "remove",
                    str(target),
                    "--path",
                    "reference/Missing.md",
                    "--missing-ok",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["changed_files"], [])
            self.assertEqual(payload["count"], 0)

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

    def test_plan_stage_commands_manage_task_stage_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "First"])

            exit_code, stdout, stderr = self.run_cli_output(
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
                    "First stage",
                    "--output",
                    "Stage output",
                    "--next-action",
                    "Run stage",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "plan stage add")
            self.assertEqual(payload["stage"]["id"], "T001.1")
            plan_text = (target / "active" / "Task_Plan.md").read_text(encoding="utf-8")
            self.assertIn("| T001.1 | Pending | T001 | First stage |", plan_text)

            exit_code, stdout, stderr = self.run_cli_output(["plan", "stage", "list", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "plan stage list")
            self.assertEqual(payload["stages"][0]["id"], "T001.1")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "plan",
                    "stage",
                    "set",
                    str(target),
                    "--id",
                    "T001.1",
                    "--status",
                    "Active",
                    "--evidence",
                    "stage evidence",
                    "--next-action",
                    "Finish stage",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "plan stage set")
            self.assertEqual(payload["stage"]["status"], "Active")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "plan",
                    "stage",
                    "done",
                    str(target),
                    "--id",
                    "T001.1",
                    "--evidence",
                    "worklog/stage.md",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "plan stage done")
            self.assertEqual(payload["status"], "Done")
            plan_text = (target / "active" / "Task_Plan.md").read_text(encoding="utf-8")
            self.assertIn("| T001.1 | Done | T001 | First stage |", plan_text)
            self.assertIn("worklog/stage.md", plan_text)

    def test_plan_stage_add_rejects_invalid_parent_scope_and_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "First"])

            exit_code, stdout, _stderr = self.run_cli_output(
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
                    "Wrong parent",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            self.assert_failure_json_contract(self.json_payload(stdout), "task_stage_scope_invalid", "plan")

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
                        "First stage",
                    ]
                ),
                0,
            )
            exit_code, stdout, _stderr = self.run_cli_output(
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
                    "Duplicate",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            self.assert_failure_json_contract(self.json_payload(stdout), "task_stage_duplicate_id", "plan")

    def test_plan_stage_workstream_owner_must_exist_when_declared(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "First"])

            exit_code, stdout, _stderr = self.run_cli_output(
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
                    "Stage",
                    "--workstream",
                    "WS004",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            self.assert_failure_json_contract(self.json_payload(stdout), "task_stage_workstream_not_found", "plan")

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

    def test_task_stage_registry_is_optional_without_stage_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "First"])
            self.run_cli(["task", "start", str(target), "--id", "T001"])

            plan_path = target / "active" / "Task_Plan.md"
            plan_path.write_text(
                "## 大任务状态\n\nActive\n\n## 当前焦点\n\nT001\n\n## 子任务\n\n"
                "| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| T001 | Active | First | 无。 | 无。 | 无。 | next |\n",
                encoding="utf-8",
            )

            result = acf.check_context(target, "minimal", strict=False)

            self.assertFalse(result.errors)

    def test_check_rejects_unregistered_current_task_stage_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "First"])
            (target / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n## 子任务 ID\n\nT001.4\n",
                encoding="utf-8",
            )

            result = acf.check_context(target, "minimal", strict=False)

            self.assertTrue(any("stage id `T001.4` does not exist" in error for error in result.errors))

    def test_check_rejects_stage_with_missing_parent_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            plan_path = target / "active" / "Task_Plan.md"
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8").replace(
                    "| 暂无 |  |  |  |  |  |  |  |  |",
                    "| T001.4 | Active | T001 | Stage | 无。 | 无。 | out | evidence | next |",
                ),
                encoding="utf-8",
            )
            (target / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n## 子任务 ID\n\nT001.4\n",
                encoding="utf-8",
            )

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("parent task `T001` does not exist" in error for error in result.errors))

    def test_check_rejects_stage_with_missing_workstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "First"])
            plan_path = target / "active" / "Task_Plan.md"
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8").replace(
                    "| 暂无 |  |  |  |  |  |  |  |  |",
                    "| T001.4 | Active | T001 | Stage | WS004 | 无。 | out | evidence | next |",
                ),
                encoding="utf-8",
            )

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("workstream `WS004` does not exist" in error for error in result.errors))

    def test_check_rejects_terminal_workstream_as_current_execution_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            self.run_cli(["workstream", "set", "WS004", str(target), "--status", "Active"])
            self.run_cli(
                [
                    "workstream",
                    "merge-request",
                    "WS004",
                    str(target),
                    "--target",
                    "active/Context.md",
                    "--summary",
                    "summary",
                    "--verification",
                    "verified",
                ]
            )
            self.authorize_closeout(target, "WS004", "ready")
            self.run_cli(["workstream", "ready", "WS004", str(target), "--human-approved"])
            self.authorize_closeout(target, "WS004", "done")
            self.run_cli(["workstream", "done", "WS004", str(target), "--evidence", "done", "--merge-resolution", "no_merge_required"])
            (target / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n## 子任务 ID\n\nT001\n\n## 当前执行线\n\nWS004\n",
                encoding="utf-8",
            )

            result = acf.check_context(target, "minimal", strict=True)

            self.assertTrue(any("current execution line references terminal workstream `WS004`" in error for error in result.errors))

    def test_done_workstream_allowed_as_stage_history_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004")
            self.run_cli(["workstream", "set", "WS004", str(target), "--status", "Active"])
            self.run_cli(
                [
                    "workstream",
                    "merge-request",
                    "WS004",
                    str(target),
                    "--target",
                    "active/Context.md",
                    "--summary",
                    "summary",
                    "--verification",
                    "verified",
                ]
            )
            self.authorize_closeout(target, "WS004", "ready")
            self.run_cli(["workstream", "ready", "WS004", str(target), "--human-approved"])
            self.authorize_closeout(target, "WS004", "done")
            self.run_cli(["workstream", "done", "WS004", str(target), "--evidence", "done", "--merge-resolution", "no_merge_required"])
            self.run_cli(["plan", "init", str(target), "--title", "Large task", "--goal", "Goal", "--force"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "First"])
            plan_path = target / "active" / "Task_Plan.md"
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8").replace(
                    "| 暂无 |  |  |  |  |  |  |  |  |",
                    "| T001.4 | Active | T001 | Stage | 无。 | WS004 | out | active/workstreams/WS004.md | next |",
                ),
                encoding="utf-8",
            )
            (target / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n## 子任务 ID\n\nT001.4\n\n## 当前执行线\n\n无。\n",
                encoding="utf-8",
            )

            result = acf.check_context(target, "minimal", strict=False)

            self.assertFalse(result.errors)

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
            archived_task = next((target / "archive" / "tasks").glob("*.md"))
            archived_task_text = archived_task.read_text(encoding="utf-8")
            self.assertIn(acf.ARCHIVE_RECORD_MARKER_START, archived_task_text)
            self.assertIn("- source_path: active/Current_Task.md", archived_task_text)
            self.assertIn("- archive_reason: completed", archived_task_text)

            exit_code = self.run_cli(
                ["archive", "task-plan", str(target), "--reason", "completed", "--force"]
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("## 大任务状态\n\nEmpty", (target / "active" / "Task_Plan.md").read_text(encoding="utf-8"))
            self.assertTrue(list((target / "archive" / "plans").glob("*.md")))
            archived_plan = next((target / "archive" / "plans").glob("*.md"))
            archived_plan_text = archived_plan.read_text(encoding="utf-8")
            self.assertIn(acf.ARCHIVE_RECORD_MARKER_START, archived_plan_text)
            self.assertIn("- source_path: active/Task_Plan.md", archived_plan_text)
            self.assertIn("- archive_reason: completed", archived_plan_text)

    def test_archive_rewrites_local_markdown_links_for_new_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            target = project / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "standard"])
            for path in target.rglob("*.md"):
                text = path.read_text(encoding="utf-8")
                path.write_text(acf.PLACEHOLDER_RE.sub("placeholder", text), encoding="utf-8")
            (target / "reference" / "Sources_Index.md").write_text(
                "## 核心资料\n\n"
                "| 资料 | 类型 | 链接或位置 | 状态 | 可信度 | 和本项目的关系 | 后续动作 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| 暂无 |  |  |  |  |  |  |\n",
                encoding="utf-8",
            )
            (target / "decisions" / "ADR-0001-template.md").write_text(
                "## 状态\n\nProposed\n\n## 日期\n\n2099-01-01\n",
                encoding="utf-8",
            )
            (target / "active" / "Task_Plan.md").write_text(acf.render_empty_task_plan(), encoding="utf-8")
            (project / "template").mkdir(parents=True)
            (project / "template" / "AGENTS.md").write_text("# Template Agent\n", encoding="utf-8")
            (target / "reference" / "System_Manual.md").write_text("# Manual\n\n## manual\n\n内容。\n", encoding="utf-8")
            (target / "reference" / "asset.png").write_text("png", encoding="utf-8")
            current = target / "active" / "Current_Task.md"
            current.write_text(
                "## 当前任务状态\n\nDone\n\n"
                "## 任务名称\n\nArchive Link Rewrite\n\n"
                "## 输入材料\n\n"
                "- [manual](../reference/System_Manual.md#manual)\n"
                "- ![asset](../reference/asset.png)\n"
                "- [template](../../../template/AGENTS.md)\n"
                "- [self](#输入材料)\n"
                "- [external](https://example.com/file.md)\n"
                "```\n"
                "[code](../reference/System_Manual.md)\n"
                "```\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["archive", "current-task", str(target), "--reason", "done", "--check-after", "--strict", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            self.assert_success_json_contract(self.json_payload(stdout), "archive current-task")
            archived_task = next((target / "archive" / "tasks").glob("*archive-link-rewrite.md"))
            archived_text = archived_task.read_text(encoding="utf-8")
            self.assertIn("[manual](../../reference/System_Manual.md#manual)", archived_text)
            self.assertIn("![asset](../../reference/asset.png)", archived_text)
            self.assertIn("[template](../../../../template/AGENTS.md)", archived_text)
            self.assertIn("[self](#输入材料)", archived_text)
            self.assertIn("[code](../reference/System_Manual.md)", archived_text)

            plan = target / "active" / "Task_Plan.md"
            plan.write_text(
                "## 大任务状态\n\nDone\n\n"
                "## 大任务名称\n\nArchive Plan Links\n\n"
                "## 规划依据\n\n"
                "- [manual](../reference/System_Manual.md#manual)\n"
                "- [template](../../../template/AGENTS.md)\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["archive", "task-plan", str(target), "--reason", "done", "--check-after", "--strict", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            self.assert_success_json_contract(self.json_payload(stdout), "archive task-plan")
            archived_plan = next((target / "archive" / "plans").glob("*archive-plan-links.md"))
            archived_plan_text = archived_plan.read_text(encoding="utf-8")
            self.assertIn("[manual](../../reference/System_Manual.md#manual)", archived_plan_text)
            self.assertIn("[template](../../../../template/AGENTS.md)", archived_plan_text)

    def write_archive_sync_details(self, target):
        task = target / "archive" / "tasks" / "2026-05-01-old-task.md"
        task.parent.mkdir(parents=True, exist_ok=True)
        task.write_text(
            "## 任务名称\n\nOld Task\n\n## 当前任务状态\n\nDone\n\n"
            f"{acf.ARCHIVE_RECORD_MARKER_START}\n"
            "- archived_at: 2026-05-01\n"
            "- item_type: Task\n"
            "- item_id: Old Task\n"
            "- source_path: active/Current_Task.md\n"
            "- archive_path: `archive/tasks/2026-05-01-old-task.md`\n"
            "- status: Archived\n"
            "- archive_reason: task marker reason\n"
            f"{acf.ARCHIVE_RECORD_MARKER_END}\n",
            encoding="utf-8",
        )
        plan = target / "archive" / "plans" / "2026-05-02-old-plan.md"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text("## 大任务名称\n\nOld Plan\n\n## 大任务状态\n\nDone\n", encoding="utf-8")
        workstream = target / "archive" / "workstreams" / "WS001.md"
        workstream.parent.mkdir(parents=True, exist_ok=True)
        workstream.write_text(
            "---\n"
            "id: WS001\n"
            "status: Done\n"
            "---\n\n"
            "# WS001\n\n"
            f"{acf.WORKSTREAM_ARCHIVE_MARKER_START}\n"
            "## 归档记录\n\n"
            "- archived_at: 2026-05-03\n"
            "- source_path: active/workstreams/WS001.md\n"
            "- archive_path: `archive/workstreams/WS001.md`\n"
            "- archive_reason: merged after review\n"
            f"{acf.WORKSTREAM_ARCHIVE_MARKER_END}\n",
            encoding="utf-8",
        )
        undated = target / "archive" / "tasks" / "old-undated-task.md"
        undated.write_text("## 任务名称\n\nUndated Task\n", encoding="utf-8")

    def test_archive_sync_requires_marker_unless_initialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            index_path = target / "archive" / "Archive_Index.md"
            index_text = index_path.read_text(encoding="utf-8")
            index_path.write_text(
                index_text.replace(acf.ARCHIVE_INDEX_MARKER_START + "\n", "").replace(acf.ARCHIVE_INDEX_MARKER_END + "\n", ""),
                encoding="utf-8",
            )

            exit_code, stdout, _stderr = self.run_cli_output(["archive", "sync", str(target), "--json"])

            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            self.assert_failure_json_contract(self.json_payload(stdout), "generated_marker_missing", "archive")

    def test_archive_sync_init_marker_dry_run_and_write_preserves_old_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.write_archive_sync_details(target)
            index_path = target / "archive" / "Archive_Index.md"
            index_path.write_text(
                "## 归档条目\n\n"
                "| 日期 | 类型 | ID | 原路径 | 归档路径 | 状态 | 原因 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| 2026-04-30 | Task | Legacy Task | 无。 | `archive/tasks/2026-05-01-old-task.md` | Archived | legacy reason |\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["archive", "sync", str(target), "--init-marker", "--dry-run", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "archive sync")
            self.assertEqual(payload["generated_count"], 3)
            self.assertIn("Task/Plan archive reason is not recoverable", payload["warnings"][0])
            self.assertTrue(any(item["reason"] == "archive date not recoverable" for item in payload["skipped_items"]))
            self.assertIn("| 2026-05-01 | Task | Old Task | active/Current_Task.md | `archive/tasks/2026-05-01-old-task.md` | Archived | task marker reason |", payload["planned_block"])
            self.assertNotIn(acf.ARCHIVE_INDEX_MARKER_START, index_path.read_text(encoding="utf-8"))

            exit_code, stdout, stderr = self.run_cli_output(
                ["archive", "sync", str(target), "--init-marker", "--check-after", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "archive sync")
            index_text = index_path.read_text(encoding="utf-8")
            self.assertIn(acf.ARCHIVE_INDEX_MARKER_START, index_text)
            self.assertIn("| 2026-05-01 | Task | Old Task | active/Current_Task.md | `archive/tasks/2026-05-01-old-task.md` | Archived | task marker reason |", index_text)
            self.assertIn("| 2026-05-03 | workstream | WS001 | active/workstreams/WS001.md | `archive/workstreams/WS001.md` | Done | merged after review |", index_text)
            self.assertIn("| 2026-04-30 | Task | Legacy Task | 无。 | `archive/tasks/2026-05-01-old-task.md` | Archived | legacy reason |", index_text)

            exit_code, stdout, stderr = self.run_cli_output(["archive", "sync", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertEqual(payload["changed_files"], [])

    def test_archive_sync_replaces_existing_generated_block_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.write_archive_sync_details(target)
            index_path = target / "archive" / "Archive_Index.md"
            index_path.write_text(
                "## 归档条目\n\n"
                f"{acf.ARCHIVE_INDEX_MARKER_START}\n"
                "| 日期 | 类型 | ID | 原路径 | 归档路径 | 状态 | 原因 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| 2026-01-01 | Task | Stale | active/Current_Task.md | `archive/tasks/missing.md` | Archived | stale |\n"
                f"{acf.ARCHIVE_INDEX_MARKER_END}\n\n"
                "Manual archive note outside generated block.\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["archive", "sync", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertTrue(any(item.get("id") == "Stale" for item in payload["skipped_items"]))
            index_text = index_path.read_text(encoding="utf-8")
            self.assertIn("| 2026-05-02 | Plan | Old Plan | active/Task_Plan.md | `archive/plans/2026-05-02-old-plan.md` | Archived | 未记录。 |", index_text)
            self.assertNotIn("| 2026-01-01 | Task | Stale |", index_text)
            self.assertIn("Manual archive note outside generated block.", index_text)

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

    def test_generated_marker_block_replaces_only_marker_content(self):
        original = "before\n<!-- ACF:TEST:BLOCK:START -->\nstale\n<!-- ACF:TEST:BLOCK:END -->\nafter\n"

        updated, changed = acf.replace_generated_marker_block(
            original,
            "<!-- ACF:TEST:BLOCK:START -->",
            "<!-- ACF:TEST:BLOCK:END -->",
            "fresh",
        )

        self.assertTrue(changed)
        self.assertEqual(updated, "before\n<!-- ACF:TEST:BLOCK:START -->\nfresh\n<!-- ACF:TEST:BLOCK:END -->\nafter\n")
        with self.assertRaises(SystemExit) as missing:
            acf.replace_generated_marker_block("before\nafter\n", "<!-- ACF:X:Y:START -->", "<!-- ACF:X:Y:END -->", "body")
        self.assertIn("generated_marker_missing", str(missing.exception))
        with self.assertRaises(SystemExit) as duplicate:
            acf.replace_generated_marker_block(
                "<!-- ACF:X:Y:START -->\n1\n<!-- ACF:X:Y:END -->\n<!-- ACF:X:Y:START -->\n2\n<!-- ACF:X:Y:END -->\n",
                "<!-- ACF:X:Y:START -->",
                "<!-- ACF:X:Y:END -->",
                "body",
            )
        self.assertIn("generated_marker_duplicate", str(duplicate.exception))

    def write_valid_knowledge_detail(self, target, name="K001-markdown-editing-lesson.md", status="Active"):
        path = target / "reference" / "knowledge" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# K001：Markdown editing lesson\n\n"
            "## 状态\n\n"
            f"{status}\n\n"
            "## 标签\n\n"
            "cli, docs\n\n"
            "## 摘要\n\n"
            "Keep generated blocks bounded.\n\n"
            "## 结论\n\n"
            "Only replace content inside generated markers.\n\n"
            "## 适用场景\n\n"
            "- Syncing maintained Markdown index tables.\n\n"
            "## 不适用场景\n\n"
            "- Manually curated prose outside generated markers.\n\n"
            "## 来源\n\n"
            "- `active/Context.md`\n\n"
            "## 与现有事实源的关系\n\n"
            "- Current facts remain in `active/Context.md`.\n\n"
            "## 去重判断\n\n"
            "This records a reusable index maintenance pattern.\n",
            encoding="utf-8",
        )
        return path

    def test_knowledge_sync_requires_marker_unless_initialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            index_path = target / "reference" / "Knowledge_Index.md"
            index_text = index_path.read_text(encoding="utf-8")
            index_path.write_text(
                index_text.replace(acf.KNOWLEDGE_INDEX_MARKER_START + "\n", "").replace(acf.KNOWLEDGE_INDEX_MARKER_END + "\n", ""),
                encoding="utf-8",
            )

            exit_code, stdout, _stderr = self.run_cli_output(["knowledge", "sync", str(target), "--json"])

            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            payload = self.json_payload(stdout)
            self.assert_failure_json_contract(payload, "generated_marker_missing", "knowledge")

    def test_knowledge_sync_init_marker_dry_run_and_write_preserves_outside_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.write_valid_knowledge_detail(target)
            index_path = target / "reference" / "Knowledge_Index.md"
            original = index_path.read_text(encoding="utf-8")
            original = original.replace(acf.KNOWLEDGE_INDEX_MARKER_START + "\n", "").replace(acf.KNOWLEDGE_INDEX_MARKER_END + "\n", "")
            index_path.write_text(original + "\nManual note outside generated block.\n", encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                ["knowledge", "sync", str(target), "--init-marker", "--dry-run", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "knowledge sync")
            self.assertEqual(payload["generated_count"], 1)
            self.assertIn("K001", payload["planned_block"])
            self.assertNotIn(acf.KNOWLEDGE_INDEX_MARKER_START, index_path.read_text(encoding="utf-8"))

            exit_code, stdout, stderr = self.run_cli_output(
                ["knowledge", "sync", str(target), "--init-marker", "--check-after", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "knowledge sync")
            index_text = index_path.read_text(encoding="utf-8")
            self.assertIn(acf.KNOWLEDGE_INDEX_MARKER_START, index_text)
            self.assertIn("| K001 | Markdown editing lesson | Active | cli, docs | Keep generated blocks bounded. |", index_text)
            self.assertIn("Manual note outside generated block.", index_text)

            exit_code, stdout, stderr = self.run_cli_output(["knowledge", "sync", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertEqual(payload["changed_files"], [])

    def test_knowledge_sync_replaces_existing_generated_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.write_valid_knowledge_detail(target)
            index_path = target / "reference" / "Knowledge_Index.md"
            index_path.write_text(
                "## Knowledge 条目\n\n"
                f"{acf.KNOWLEDGE_INDEX_MARKER_START}\n"
                "| ID | 标题 | 状态 | 标签 | 摘要 | 详情 |\n"
                "|---|---|---|---|---|---|\n"
                "| K999 | Stale | Active | old | stale | `reference/knowledge/missing.md` |\n"
                f"{acf.KNOWLEDGE_INDEX_MARKER_END}\n\n"
                "Manual note outside generated block.\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["knowledge", "sync", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertEqual(payload["skipped_items"][0]["id"], "K999")
            index_text = index_path.read_text(encoding="utf-8")
            self.assertIn("| K001 | Markdown editing lesson | Active | cli, docs | Keep generated blocks bounded. |", index_text)
            self.assertNotIn("K999", index_text)
            self.assertIn("Manual note outside generated block.", index_text)

    def write_valid_decision_detail(self, target, name="ADR-0001.md", status="Active"):
        path = target / "decisions" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# ADR-0001 - Use generated decision index sync\n\n"
            "## 状态\n\n"
            f"{status}\n\n"
            "## 日期\n\n"
            "2026-05-08\n\n"
            "## 决策\n\n"
            "Generate the decision index from ADR detail files.\n\n"
            "## 理由\n\n"
            "1. ADR details are the durable source.\n",
            encoding="utf-8",
        )
        return path

    def test_decisions_sync_requires_marker_unless_initialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            index_path = target / "reference" / "Decisions_Index.md"
            index_text = index_path.read_text(encoding="utf-8")
            index_path.write_text(
                index_text.replace(acf.DECISIONS_INDEX_MARKER_START + "\n", "").replace(acf.DECISIONS_INDEX_MARKER_END + "\n", ""),
                encoding="utf-8",
            )

            exit_code, stdout, _stderr = self.run_cli_output(["decisions", "sync", str(target), "--json"])

            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            payload = self.json_payload(stdout)
            self.assert_failure_json_contract(payload, "generated_marker_missing", "decisions")

    def test_decisions_sync_init_marker_dry_run_and_write_preserves_outside_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.write_valid_decision_detail(target)
            index_path = target / "reference" / "Decisions_Index.md"
            original = index_path.read_text(encoding="utf-8")
            original = original.replace(acf.DECISIONS_INDEX_MARKER_START + "\n", "").replace(acf.DECISIONS_INDEX_MARKER_END + "\n", "")
            index_path.write_text(original + "\nManual decision note outside generated block.\n", encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(
                ["decisions", "sync", str(target), "--init-marker", "--dry-run", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "decisions sync")
            self.assertEqual(payload["generated_count"], 1)
            self.assertIn("ADR-0001", payload["planned_block"])
            self.assertNotIn(acf.DECISIONS_INDEX_MARKER_START, index_path.read_text(encoding="utf-8"))

            exit_code, stdout, stderr = self.run_cli_output(
                ["decisions", "sync", str(target), "--init-marker", "--check-after", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "decisions sync")
            index_text = index_path.read_text(encoding="utf-8")
            self.assertIn(acf.DECISIONS_INDEX_MARKER_START, index_text)
            self.assertIn(
                "| ADR-0001 | Use generated decision index sync | Active | Generate the decision index from ADR detail files. | `decisions/ADR-0001.md` |",
                index_text,
            )
            self.assertIn("Manual decision note outside generated block.", index_text)

            exit_code, stdout, stderr = self.run_cli_output(["decisions", "sync", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertEqual(payload["changed_files"], [])

    def test_decisions_sync_replaces_existing_generated_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.write_valid_decision_detail(target)
            index_path = target / "reference" / "Decisions_Index.md"
            index_path.write_text(
                "## 当前有效决策\n\n"
                f"{acf.DECISIONS_INDEX_MARKER_START}\n"
                "| ID | 标题 | 状态 | 摘要 | 详情 |\n"
                "|---|---|---|---|---|\n"
                "| ADR-9999 | Stale | Active | stale | `decisions/ADR-9999.md` |\n"
                f"{acf.DECISIONS_INDEX_MARKER_END}\n\n"
                "Manual decision note outside generated block.\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["decisions", "sync", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertEqual(payload["skipped_items"][0]["id"], "ADR-9999")
            index_text = index_path.read_text(encoding="utf-8")
            self.assertIn(
                "| ADR-0001 | Use generated decision index sync | Active | Generate the decision index from ADR detail files. | `decisions/ADR-0001.md` |",
                index_text,
            )
            self.assertNotIn("ADR-9999", index_text)
            self.assertIn("Manual decision note outside generated block.", index_text)

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

    def test_status_discovers_docs_acf_context_from_project_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            target = project_root / "docs-acf" / "ai"
            nested = project_root / "src"
            nested.mkdir(parents=True)
            self.run_cli(["init", str(target), "--profile", "minimal"])

            with pushd(nested):
                exit_code, stdout, stderr = self.run_cli_output(["status", "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertEqual(payload["context"], str(target.resolve()))
            self.assertEqual(payload["project_root"], str(project_root.resolve()))

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

    def test_check_validates_markdown_links_images_and_heading_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "reference" / "System_Manual.md").write_text(
                "# System Manual\n\n## 人工笔记与 Obsidian\n\n内容。\n",
                encoding="utf-8",
            )
            (target / "reference" / "asset.png").write_text("png", encoding="utf-8")
            current = target / "active" / "Current_Task.md"
            current.write_text(
                "# Current Task\n\n"
                "## 当前任务状态\n\nActive\n\n"
                "## 输入材料\n\n"
                "- [manual](../reference/System_Manual.md#人工笔记与-obsidian)\n"
                "- ![asset](../reference/asset.png)\n"
                "- [external](https://example.com/file.md)\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["check", str(target), "--profile", "minimal", "--json"])
            payload = self.json_payload(stdout)
            self.assertEqual(exit_code, 0, stderr)
            self.assert_success_json_contract(payload, "check")

            current.write_text(
                current.read_text(encoding="utf-8")
                + "- [missing](../reference/Missing.md)\n"
                + "- ![missing asset](../reference/missing.png)\n"
                + "- [bad anchor](../reference/System_Manual.md#不存在)\n",
                encoding="utf-8",
            )
            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--profile", "minimal", "--json"])
            payload = self.json_payload(stdout)
            self.assertEqual(exit_code, 1)
            errors = "\n".join(payload["check"]["errors"])
            self.assertIn("broken markdown link `../reference/Missing.md`", errors)
            self.assertIn("broken markdown link `../reference/missing.png`", errors)
            self.assertIn("broken markdown link anchor `../reference/System_Manual.md#不存在`", errors)

    def test_linkify_converts_default_scope_and_skips_daily_worklog_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "reference" / "System_Manual.md").write_text("# Manual\n", encoding="utf-8")
            (target / "archive" / "tasks" / "done.md").write_text("# Done\n", encoding="utf-8")
            (target / "active" / "Current_Task.md").write_text(
                "# Current Task\n\n"
                "## 当前任务状态\n\nActive\n\n"
                "## 输入材料\n\n"
                "- `reference/System_Manual.md`\n"
                "- reference/System_Manual.md\n"
                "- reference/Missing.md\n"
                "- `uv run acf link add active/Current_Task.md --target reference/System_Manual.md`\n"
                "```\nreference/System_Manual.md\n```\n",
                encoding="utf-8",
            )
            (target / "archive" / "Archive_Index.md").write_text(
                "# Archive\n\n- archive/tasks/done.md\n",
                encoding="utf-8",
            )
            frontmatter_file = target / "active" / "FrontMatter.md"
            frontmatter_file.write_text(
                "---\n"
                "read_scope:\n"
                "  - reference/System_Manual.md\n"
                "---\n\n"
                "- reference/System_Manual.md\n",
                encoding="utf-8",
            )
            daily = target / "worklog" / "daily" / "2099-01-01.md"
            daily.write_text("- reference/System_Manual.md\n", encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["linkify", str(target), "--dry-run", "--json"])
            payload = self.json_payload(stdout)
            self.assertEqual(exit_code, 0, stderr)
            self.assert_success_json_contract(payload, "linkify")
            self.assertIn("active/Current_Task.md", {entry["path"] for entry in payload["updated"]})
            self.assertFalse((target / ".acf.lock").exists())

            self.assertEqual(self.run_cli(["linkify", str(target)]), 0)
            text = (target / "active" / "Current_Task.md").read_text(encoding="utf-8")
            self.assertIn("[reference/System_Manual.md](../reference/System_Manual.md)", text)
            self.assertIn("reference/Missing.md", text)
            self.assertIn("`uv run acf link add active/Current_Task.md --target reference/System_Manual.md`", text)
            self.assertIn("```\nreference/System_Manual.md\n```", text)
            archive_index = (target / "archive" / "Archive_Index.md").read_text(encoding="utf-8")
            self.assertIn("[archive/tasks/done.md](tasks/done.md)", archive_index)
            frontmatter_text = frontmatter_file.read_text(encoding="utf-8")
            self.assertIn("  - reference/System_Manual.md\n---", frontmatter_text)
            self.assertIn("[reference/System_Manual.md](../reference/System_Manual.md)", frontmatter_text)
            self.assertEqual("- reference/System_Manual.md\n", daily.read_text(encoding="utf-8"))

    def test_linkify_links_project_root_paths_from_docs_ai_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            target = project / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (project / "template").mkdir(parents=True)
            (project / "template" / "AGENTS.md").write_text("# Template Agent\n", encoding="utf-8")
            current = target / "active" / "Current_Task.md"
            current.write_text(
                "# Current Task\n\n"
                "## 当前任务状态\n\nActive\n\n"
                "## 输入材料\n\n"
                "- template/AGENTS.md\n"
                "- docs/ai/AGENTS.md\n",
                encoding="utf-8",
            )

            self.assertEqual(self.run_cli(["linkify", str(target)]), 0)
            text = current.read_text(encoding="utf-8")
            self.assertIn("[template/AGENTS.md](../../../template/AGENTS.md)", text)
            self.assertIn("[docs/ai/AGENTS.md](../AGENTS.md)", text)

    def test_index_path_markup_can_be_checked_after_linkify(self):
        self.assertEqual(
            acf.strip_code_ticks("[worklog/daily/2026-05-08.md](daily/2026-05-08.md)"),
            "worklog/daily/2026-05-08.md",
        )
        self.assertEqual(
            acf.strip_code_ticks("[active/workstreams/WS001.md](workstreams/WS001.md)"),
            "active/workstreams/WS001.md",
        )

    def test_linkify_allow_missing_links_missing_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            current = target / "active" / "Current_Task.md"
            current.write_text(
                "# Current Task\n\n## 当前任务状态\n\nActive\n\n## 输入材料\n\n- reference/Missing.md\n",
                encoding="utf-8",
            )

            self.assertEqual(self.run_cli(["linkify", str(target), "--allow-missing"]), 0)
            self.assertIn(
                "[reference/Missing.md](../reference/Missing.md)",
                current.read_text(encoding="utf-8"),
            )

    def test_link_add_appends_heading_link_and_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "reference" / "System_Manual.md").write_text(
                "# System Manual\n\n## 人工笔记与 Obsidian\n\n内容。\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "link",
                    "add",
                    str(target),
                    "active/Current_Task.md",
                    "--heading",
                    "## 输入材料",
                    "--target",
                    "reference/System_Manual.md",
                    "--target-heading",
                    "人工笔记与 Obsidian",
                    "--json",
                ]
            )
            payload = self.json_payload(stdout)
            self.assertEqual(exit_code, 0, stderr)
            self.assert_success_json_contract(payload, "link add")
            text = (target / "active" / "Current_Task.md").read_text(encoding="utf-8")
            self.assertIn(
                "- [reference/System_Manual.md#人工笔记与-obsidian](../reference/System_Manual.md#人工笔记与-obsidian)",
                text,
            )

            exit_code, _stdout, stderr = self.run_cli_output(
                [
                    "link",
                    "add",
                    str(target),
                    "active/Current_Task.md",
                    "--heading",
                    "## 输入材料",
                    "--target",
                    "reference/System_Manual.md",
                    "--target-heading",
                    "人工笔记与 Obsidian",
                ]
            )
            self.assertEqual(exit_code, 3)
            self.assertIn("link already exists", stderr)

    def test_ai_facing_success_json_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "active" / "Context.md").write_text(
                "## 审阅标记\n\n"
                "- Last reviewed: 2026-05-05\n"
                "- Review scope: 文件级。\n\n"
                "## 当前有效事实\n\n- Fact.\n\n"
                "## Alpha\n\nBody.\n",
                encoding="utf-8",
            )
            self.run_cli(["workstream", "init", str(target)])
            self.run_cli(["plan", "init", str(target), "--title", "Contract plan", "--goal", "Contract goal", "--force"])
            self.run_cli(["plan", "add-task", str(target), "--id", "T001", "--title", "Contract task"])
            self.run_cli(
                [
                    "workstream",
                    "add",
                    str(target),
                    "--id",
                    "WS001",
                    "--title",
                    "Contract workstream",
                    "--owner",
                    "主 agent",
                    "--output",
                    "验证记录",
                ]
            )
            self.run_cli(
                [
                    "workstream",
                    "stage",
                    "add",
                    "WS001",
                    str(target),
                    "--id",
                    "WS001.1",
                    "--title",
                    "Contract stage",
                ]
            )
            self.run_cli(
                [
                    "new",
                    "feedback",
                    str(target),
                    "--id",
                    "F001",
                    "--type",
                    "需求",
                    "--content",
                    "Contract feedback.",
                    "--source",
                    "2026-05-05 contract",
                ]
            )

            cases = [
                ("status", ["status", str(target), "--json"]),
                ("check", ["check", str(target), "--json"]),
                ("upgrade", ["upgrade", str(target), "--dry-run", "--json"]),
                ("linkify", ["linkify", str(target), "--dry-run", "--json"]),
                (
                    "link add",
                    [
                        "link",
                        "add",
                        str(target),
                        "active/Current_Task.md",
                        "--heading",
                        "## 输入材料",
                        "--target",
                        "reference/Project_Brief.md",
                        "--dry-run",
                        "--json",
                    ],
                ),
                ("audit context", ["audit", "context", str(target), "--json"]),
                ("review stale", ["review", "stale", str(target), "--today", "2026-05-05", "--json"]),
                ("curate draft", ["curate", "draft", str(target), "--today", "2026-05-05", "--dry-run", "--json"]),
                ("doctor", ["doctor", str(target), "--json"]),
                ("archive sync", ["archive", "sync", str(target), "--dry-run", "--json"]),
                ("decisions sync", ["decisions", "sync", str(target), "--dry-run", "--json"]),
                ("knowledge sync", ["knowledge", "sync", str(target), "--dry-run", "--json"]),
                ("feedback list", ["feedback", "list", str(target), "--json"]),
                ("feedback archive-candidates", ["feedback", "archive-candidates", str(target), "--json"]),
                (
                    "feedback triage",
                    [
                        "feedback",
                        "triage",
                        str(target),
                        "F001",
                        "--next-action",
                        "Contract next action.",
                        "--dry-run",
                        "--json",
                    ],
                ),
                (
                    "new reference",
                    [
                        "new",
                        "reference",
                        str(target),
                        "--title",
                        "Smoke Reference",
                        "--summary",
                        "Smoke reference summary.",
                        "--dry-run",
                        "--json",
                    ],
                ),
                (
                    "new rule",
                    [
                        "new",
                        "rule",
                        str(target),
                        "--title",
                        "Smoke Rule",
                        "--condition",
                        "Smoke condition.",
                        "--purpose",
                        "Smoke purpose.",
                        "--rule",
                        "Smoke rule.",
                        "--dry-run",
                        "--json",
                    ],
                ),
                (
                    "new feedback",
                    [
                        "new",
                        "feedback",
                        str(target),
                        "--type",
                        "需求",
                        "--content",
                        "Smoke feedback.",
                        "--source",
                        "2026-05-05 smoke",
                        "--dry-run",
                        "--json",
                    ],
                ),
                ("workstream status", ["workstream", "status", str(target), "--json"]),
                ("workstream list", ["workstream", "list", str(target), "--json"]),
                ("workstream archive-candidates", ["workstream", "archive-candidates", str(target), "--json"]),
                ("workstream archive-draft", ["workstream", "archive-draft", str(target), "--dry-run", "--json"]),
                ("workstream show", ["workstream", "show", "WS001", str(target), "--json"]),
                ("workstream stage list", ["workstream", "stage", "list", "WS001", str(target), "--json"]),
                (
                    "workstream stage add",
                    [
                        "workstream",
                        "stage",
                        "add",
                        "WS001",
                        str(target),
                        "--id",
                        "WS001.2",
                        "--title",
                        "Dry run stage",
                        "--dry-run",
                        "--json",
                    ],
                ),
                (
                    "plan stage add",
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
                        "Dry run task stage",
                        "--dry-run",
                        "--json",
                    ],
                ),
                (
                    "edit section get",
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
                    ],
                ),
                (
                    "clock now",
                    ["clock", "now", "--json"],
                ),
            ]

            for command, args in cases:
                with self.subTest(command=command):
                    exit_code, stdout, stderr = self.run_cli_output(args)
                    self.assertEqual(exit_code, 0, stderr)
                    payload = self.json_payload(stdout)
                    self.assert_success_json_contract(payload, command)

    def test_ai_facing_failure_json_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            broken = target / "active" / "Task_Plan.md"
            broken.write_text(
                "## 大任务状态\n\nActive\n\n## 当前焦点\n\nT999\n\n## 子任务\n\n"
                "| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| T001 | Active | A | 无。 | 无。 | 无。 | 无。 |\n"
                "| T001 | Active | B | 无。 | 无。 | 无。 | 无。 |\n",
                encoding="utf-8",
            )
            exit_code, stdout, _stderr = self.run_cli_output(["check", str(target), "--profile", "minimal", "--json"])
            self.assertEqual(exit_code, acf.EXIT_CHECK_FAILED)
            self.assert_failure_json_contract(self.json_payload(stdout), "check_failed", "check")

            broken.write_text(
                acf.render_task_plan("Done", "Plan", ["Goal"], ["Success"], "无。", []),
                encoding="utf-8",
            )
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
            self.assertNotEqual(exit_code, 0)
            self.assert_failure_json_contract(self.json_payload(stdout), "safety_refused", "edit")

            workstream_target = Path(tmp) / "workstream-ctx"
            self.init_minimal_workstream_context(workstream_target)
            self.add_workstream(workstream_target, "WS001")
            self.write_workstream_stage_table(
                workstream_target,
                "WS001",
                [
                    ["WS001.1", "Active", "First", "无。", "Output", "无。", "Next"],
                    ["WS001.2", "Pending", "Second", "无。", "Output", "无。", "Next"],
                ],
            )
            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "focus", "WS001", "WS001.2", str(workstream_target), "--json"]
            )
            self.assertNotEqual(exit_code, 0)
            self.assert_failure_json_contract(
                self.json_payload(stdout),
                "workstream_stage_active_conflict",
                "workstream",
            )

            exit_code, stdout, _stderr = self.run_cli_output(
                ["curate", "draft", str(workstream_target), "--today", "2026-05-05", "--json"]
            )
            self.assertEqual(exit_code, 0)
            self.assert_success_json_contract(self.json_payload(stdout), "curate draft")
            exit_code, stdout, _stderr = self.run_cli_output(
                ["curate", "draft", str(workstream_target), "--today", "2026-05-05", "--json"]
            )
            self.assertEqual(exit_code, acf.EXIT_SAFETY_REFUSED)
            self.assert_failure_json_contract(self.json_payload(stdout), "curation_draft_exists", "curate draft")

            with tempfile.TemporaryDirectory() as empty:
                with pushd(Path(empty)):
                    exit_code, stdout, _stderr = self.run_cli_output(["status", "--json"])
            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            self.assert_failure_json_contract(self.json_payload(stdout), "input_error", "status")

    def test_review_stale_json_reports_context_review_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["review", "stale", str(target), "--today", "2026-05-05", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], "review stale")
            self.assertIn("warnings", payload)
            self.assertIn("stale_items", payload)
            self.assertIn("summary", payload)
            self.assertGreater(payload["summary"]["total"], 0)
            self.assertTrue(
                any(item["signal"] == "context_missing_review_marker" for item in payload["stale_items"])
            )
            item = next(item for item in payload["stale_items"] if item["signal"] == "context_missing_review_marker")
            self.assertEqual(item["kind"], "context_review")
            self.assertEqual(item["path"], "active/Context.md")
            self.assertIn("Last reviewed", item["reason"])
            self.assertIsNone(item["age_days"])
            self.assertIsNone(item["status"])
            self.assertEqual(item["message"], item["reason"])
            self.assertTrue(payload["next_actions"])
            self.assertIn(
                "Review active/Context.md current facts and refresh the review marker if still accurate.",
                payload["next_actions"],
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--today", "2026-05-05", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            doctor_payload = self.json_payload(stdout)
            finding = next(
                item
                for item in doctor_payload["findings"]
                if item["code"] == "context_missing_review_marker"
            )
            self.assertEqual(finding["domain"], "attention_hygiene")
            self.assertEqual(finding["repair_mode"], "draft_only")
            self.assertFalse(finding["safe_to_apply"])

    def test_review_stale_reports_terminal_active_authority_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nDone\n\n"
                "## 任务名称\n\nCompleted task retained in active authority.\n",
                encoding="utf-8",
            )
            (target / "active" / "Task_Plan.md").write_text(
                "## 大任务状态\n\nDone\n\n"
                "## 当前焦点\n\n无。\n\n"
                "## 子任务\n\n"
                "| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| T001 | Done | Completed | 无。 | 无。 | done | 已完成 |\n",
                encoding="utf-8",
            )
            (target / "active" / "Context.md").write_text(
                "## 审阅标记\n\n- Last reviewed: 2026-05-05\n\n"
                "## 当前有效事实\n\n- Fact.\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["review", "stale", str(target), "--today", "2026-05-05", "--days", "14", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            signals = {item["signal"] for item in payload["stale_items"]}
            self.assertEqual(
                signals,
                {"current_task_terminal_retained", "task_plan_terminal_retained"},
            )
            by_signal = {item["signal"]: item for item in payload["stale_items"]}
            self.assertEqual(by_signal["current_task_terminal_retained"]["path"], "active/Current_Task.md")
            self.assertEqual(by_signal["current_task_terminal_retained"]["status"], "Done")
            self.assertEqual(by_signal["task_plan_terminal_retained"]["path"], "active/Task_Plan.md")
            self.assertEqual(by_signal["task_plan_terminal_retained"]["status"], "Done")

    def test_doctor_reuses_terminal_authority_and_context_review_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nDone\n\n"
                "## 任务名称\n\nCompleted task retained in active authority.\n",
                encoding="utf-8",
            )
            (target / "active" / "Task_Plan.md").write_text(
                "## 大任务状态\n\nDone\n\n"
                "## 当前焦点\n\n无。\n\n"
                "## 子任务\n\n"
                "| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| T001 | Done | Completed | 无。 | 无。 | done | 已完成 |\n",
                encoding="utf-8",
            )
            (target / "active" / "Context.md").write_text(
                "## 审阅标记\n\n- Last reviewed: 2026-04-01\n\n"
                "## 当前有效事实\n\n- Fact.\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["review", "stale", str(target), "--today", "2026-05-05", "--days", "14", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            review_payload = json.loads(stdout)
            self.assertIn(
                "context_review_stale",
                {item["signal"] for item in review_payload["stale_items"]},
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["doctor", str(target), "--today", "2026-05-05", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            doctor_payload = self.json_payload(stdout)
            self.assert_success_json_contract(doctor_payload, "doctor")
            finding_codes = {finding["code"] for finding in doctor_payload["findings"]}
            self.assertEqual(
                finding_codes,
                {
                    "current_task_terminal_retained",
                    "task_plan_terminal_retained",
                    "context_review_stale",
                },
            )
            self.assertEqual(doctor_payload["summary"]["findings_total"], 3)
            for finding in doctor_payload["findings"]:
                self.assertEqual(finding["severity"], "warning")
                self.assertEqual(finding["domain"], "attention_hygiene")
                self.assertEqual(finding["repair_mode"], "draft_only")
                self.assertFalse(finding["safe_to_apply"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["check", str(target), "--strict", "--json"]
            )
            self.assertIn(exit_code, {0, 1}, stderr)
            check_payload = json.loads(stdout)
            strict_output = json.dumps(check_payload, ensure_ascii=False)
            self.assertNotIn("current_task_terminal_retained", strict_output)
            self.assertNotIn("task_plan_terminal_retained", strict_output)
            self.assertNotIn("context_review_stale", strict_output)

    def test_review_stale_reports_mechanical_attention_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n## 任务名称\n\nLong task\n",
                encoding="utf-8",
            )
            (target / "active" / "Task_Plan.md").write_text(
                "## 大任务状态\n\nActive\n\n## 当前焦点\n\nT001\n\n## 子任务\n\n"
                "| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |\n"
                "|---|---|---|---|---|---|---|\n"
                "| T001 | Blocked | A | 无。 | 无。 | 无。 | 等待外部输入。 |\n",
                encoding="utf-8",
            )
            (target / "active" / "Feedback_Inbox.md").write_text(
                "## 反馈条目\n\n"
                "| ID    | 状态   | 类型 | 内容 | 来源 | 后续处理 |\n"
                "|---|---|---|---|---|---|\n"
                "| F001 | Open | Problem | 2026-04-01 旧反馈 | user | 待整理 |\n",
                encoding="utf-8",
            )
            (target / "active" / "Context.md").write_text(
                "## 当前有效事实\n\nLast reviewed: 2026-04-01\n\n- Fact.\n",
                encoding="utf-8",
            )
            draft_dir = target / "worklog" / "knowledge-drafts"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "2026-04-01-old.md").write_text(
                "# K-草案：Old\n\n## 状态\n\nDraft\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["review", "stale", str(target), "--today", "2026-05-05", "--days", "14", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            signals = {item["signal"] for item in payload["stale_items"]}
            kinds = {item["kind"] for item in payload["stale_items"]}
            self.assertIn("current_task_active_missing_update_date", signals)
            self.assertIn("task_plan_blocked_subtask", signals)
            self.assertIn("feedback_pending_stale", signals)
            self.assertIn("context_review_stale", signals)
            self.assertIn("knowledge_draft_stale", signals)
            self.assertEqual(
                {"current_task", "task_plan", "feedback", "context_review", "knowledge_draft"},
                kinds,
            )
            self.assertEqual(payload["summary"]["total"], len(payload["stale_items"]))
            self.assertEqual(payload["summary"]["by_kind"]["task_plan"], 1)
            self.assertIn("active/Task_Plan.md", payload["summary"]["by_path"])
            self.assertIn(
                "Review active Current_Task status, update its dated note, or finish/block/clear it.",
                payload["next_actions"],
            )
            self.assertIn(
                "Triage Feedback_Inbox items into a plan, current fact, draft, close, or archive them.",
                payload["next_actions"],
            )
            self.assertIn(
                "Review knowledge drafts and apply, mark, close, rewrite, or archive them.",
                payload["next_actions"],
            )

    def test_review_stale_accepts_context_review_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "active" / "Context.md").write_text(
                "## 审阅标记\n\n"
                "- Last reviewed: 2026-05-05\n"
                "- Review scope: 文件级。\n\n"
                "## 当前有效事实\n\n- Fact.\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["review", "stale", str(target), "--today", "2026-05-05", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            context_signals = [
                item["signal"]
                for item in payload["stale_items"]
                if item["path"] == "active/Context.md"
            ]
            self.assertNotIn("context_missing_review_marker", context_signals)
            self.assertNotIn("context_review_stale", context_signals)
            self.assertEqual(payload["summary"]["total"], 0)
            self.assertEqual(payload["next_actions"], ["No stale attention candidates found."])

    def test_review_stale_human_output_reports_clean_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "active" / "Context.md").write_text(
                "## 审阅标记\n\n"
                "- Last reviewed: 2026-05-05\n"
                "- Review scope: 文件级。\n\n"
                "## 当前有效事实\n\n- Fact.\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["review", "stale", str(target), "--today", "2026-05-05"]
            )

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("review stale: clean (0 candidate(s))", stdout)
            self.assertIn("next: No stale attention candidates found.", stdout)

    def test_review_stale_human_output_groups_by_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["review", "stale", str(target), "--today", "2026-05-05"]
            )

            self.assertEqual(exit_code, 0, stderr)
            self.assertIn("review stale:", stdout)
            self.assertIn("context_review:", stdout)
            self.assertIn("context_missing_review_marker", stdout)

    def test_audit_context_clean_json_reports_no_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(["audit", "context", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["command"], "audit context")
            self.assertEqual(payload["context"], str(target.resolve()))
            self.assertEqual(payload["candidates"], [])
            self.assertEqual(
                payload["summary"],
                {"total": 0, "by_kind": {}, "by_path": {}, "by_severity": {}},
            )
            self.assertEqual(payload["next_actions"], ["No context audit candidates found."])

    def test_audit_context_reports_long_active_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            long_lines = "\n".join(f"- Fact {index}" for index in range(90))
            (target / "active" / "Context.md").write_text(
                f"## 当前有效事实\n\n{long_lines}\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["audit", "context", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            candidates = payload["candidates"]
            self.assertEqual(payload["summary"]["total"], len(candidates))
            item = next(candidate for candidate in candidates if candidate["kind"] == "active_section_too_long")
            self.assertEqual(item["severity"], "P1-candidate")
            self.assertEqual(item["path"], "active/Context.md")
            self.assertEqual(item["section"], "当前有效事实")
            self.assertIn("90", item["reason"])
            self.assertIn("summary", payload)

    def test_audit_context_ignores_h1_wrapper_with_child_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004", "Formal Morris")
            short_sections = "\n\n".join(
                f"## Section {section}\n\n" + "\n".join(f"- Fact {section}-{index}" for index in range(30))
                for section in range(3)
            )
            (target / "active" / "workstreams" / "WS004.md").write_text(
                "---\n"
                "id: WS004\n"
                "status: Active\n"
                "owner: codex\n"
                "title: Formal Morris\n"
                "---\n"
                "# WS004 - Formal Morris\n\n"
                f"{short_sections}\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["audit", "context", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertFalse(
                [
                    candidate
                    for candidate in payload["candidates"]
                    if candidate["kind"] == "active_section_too_long"
                    and candidate.get("section") == "WS004 - Formal Morris"
                ]
            )

    def test_audit_context_reports_stale_current_task_and_workstream_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004", "Formal Morris")
            detail_path = target / "active" / "workstreams" / "WS004.md"
            detail_text = detail_path.read_text(encoding="utf-8")
            detail_text = detail_text.replace("status: Open", "status: Active\ncurrent_stage: WS004.1")
            detail_text = detail_text.replace(
                "## 目标\n\n待补充。",
                "## 目标\n\nFormal Morris.\n\n"
                "## 阶段\n\n"
                + acf.WORKSTREAM_STAGE_TABLE_HEADER
                + "\n|---|---|---|---|---|---|---|\n"
                + "| WS004.1 | Active | pct25 | 无。 | metrics | 2000-01-01 output | 等待 metrics |\n",
            )
            detail_path.write_text(detail_text, encoding="utf-8")
            (target / "active" / "Current_Task.md").write_text(
                "## 当前任务状态\n\nActive\n\n## 任务名称\n\nOld task\n\n## 最近更新\n\n2000-01-01\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(["audit", "context", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            stale_items = [
                candidate
                for candidate in payload["candidates"]
                if candidate["kind"] == "stale_current_task_or_workstream_stage"
            ]
            self.assertEqual({item["path"] for item in stale_items}, {"active/Current_Task.md", "active/workstreams/WS004.md"})
            self.assertTrue(all(item["severity"] == "P1-candidate" for item in stale_items))
            self.assertEqual(payload["summary"]["by_kind"]["stale_current_task_or_workstream_stage"], 2)

    def test_audit_context_reports_terminal_conclusion_not_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS004", "Formal Morris")
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS004",
                        str(target),
                        "--target",
                        "active/Context.md",
                        "--summary",
                        "Merge formal Morris conclusion.",
                        "--verification",
                        "Validated by output metrics.",
                    ]
                ),
                0,
            )
            self.assertEqual(self.run_cli(["workstream", "set", "WS004", str(target), "--status", "Active"]), 0)
            self.authorize_closeout(target, "WS004", "ready")
            self.assertEqual(self.run_cli(["workstream", "ready", "WS004", str(target), "--human-approved"]), 0)

            exit_code, stdout, stderr = self.run_cli_output(["audit", "context", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            item = next(candidate for candidate in payload["candidates"] if candidate["kind"] == "terminal_conclusion_not_merged")
            self.assertEqual(item["severity"], "P0-candidate")
            self.assertEqual(item["path"], "active/workstreams/WS004.md")
            self.assertEqual(item["section"], "合并请求")
            self.assertIn("ReadyToMerge", item["reason"])

    def test_audit_context_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            before = {
                path.relative_to(target).as_posix(): path.read_text(encoding="utf-8")
                for path in sorted(target.rglob("*.md"))
            }

            exit_code, stdout, stderr = self.run_cli_output(["audit", "context", str(target), "--json"])

            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(json.loads(stdout)["ok"])
            after = {
                path.relative_to(target).as_posix(): path.read_text(encoding="utf-8")
                for path in sorted(target.rglob("*.md"))
            }
            self.assertEqual(before, after)

    def test_curate_draft_creates_reviewable_curation_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(
                ["curate", "draft", str(target), "--today", "2026-05-05", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], "curate draft")
            self.assertTrue(payload["created"])
            self.assertEqual(payload["draft_path"], "worklog/curation-drafts/2026-05-05.md")
            self.assertEqual(payload["changed_files"], ["worklog/curation-drafts/2026-05-05.md"])
            self.assertGreater(payload["stale_summary"]["total"], 0)
            self.assertTrue(payload["stale_items"])
            draft = target / "worklog" / "curation-drafts" / "2026-05-05.md"
            self.assertTrue(draft.exists())
            text = draft.read_text(encoding="utf-8")
            self.assertIn("# 注意力治理草案：2026-05-05", text)
            self.assertIn("## context_review", text)
            self.assertIn("- path: active/Context.md", text)
            self.assertIn("- 人工复核：", text)

    def test_curate_draft_dry_run_previews_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "curate",
                    "draft",
                    str(target),
                    "--today",
                    "2026-05-05",
                    "--name",
                    "session-curation",
                    "--dry-run",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertFalse(payload["created"])
            self.assertEqual(payload["draft_path"], "worklog/curation-drafts/session-curation.md")
            self.assertEqual(payload["changed_files"], ["worklog/curation-drafts/session-curation.md"])
            self.assertIn("planned_draft", payload)
            self.assertFalse((target / "worklog" / "curation-drafts" / "session-curation.md").exists())

    def test_curate_draft_clean_does_not_create_empty_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            (target / "active" / "Context.md").write_text(
                "## 审阅标记\n\n"
                "- Last reviewed: 2026-05-05\n"
                "- Review scope: 文件级。\n\n"
                "## 当前有效事实\n\n- Fact.\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["curate", "draft", str(target), "--today", "2026-05-05", "--json"]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["stale_summary"]["total"], 0)
            self.assertIsNone(payload["draft_path"])
            self.assertFalse(payload["created"])
            self.assertEqual(payload["changed_files"], [])
            self.assertEqual(payload["next_actions"], ["No stale attention candidates found."])
            self.assertFalse((target / "worklog" / "curation-drafts" / "2026-05-05.md").exists())

    def test_curate_draft_refuses_existing_same_day_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(["curate", "draft", str(target), "--today", "2026-05-05", "--json"])

            exit_code, stdout, _stderr = self.run_cli_output(
                ["curate", "draft", str(target), "--today", "2026-05-05", "--json"]
            )

            self.assertEqual(exit_code, 3)
            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["command"], "curate draft")
            self.assertEqual(payload["error_code"], "curation_draft_exists")
            self.assertTrue(payload["next_actions"])

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
            self.assertEqual(json.loads(stdout)["error_code"], acf.TARGET_EXISTS_APPEND_REQUIRED)
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
            self.assertEqual(failed["error_code"], acf.TARGET_EXISTS_APPEND_REQUIRED)

    def test_usage_log_feedback_records_explicit_feedback_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            acf_home = Path(tmp) / "acf-home"
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            with isolated_acf_home(acf_home):
                exit_code, stdout, stderr = self.run_cli_output(
                    [
                        "log",
                        "feedback",
                        str(project_root),
                        "--type",
                        "Problem",
                        "--source",
                        "manual-test",
                        "--related-command",
                        "workstream add",
                        "--text",
                        "Workstream add needs a goal option.",
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "log feedback")
            self.assertEqual(payload["event"]["event_kind"], "feedback")
            self.assertEqual(payload["event"]["feedback_type"], "Problem")
            self.assertEqual(payload["event"]["related_command"], "workstream add")
            self.assertEqual(payload["event"]["text"], "Workstream add needs a goal option.")

            with isolated_acf_home(acf_home):
                exit_code, stdout, stderr = self.run_cli_output(["log", "tail", str(project_root), "--limit", "1", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            tail_payload = json.loads(stdout)
            self.assertEqual(tail_payload["events"][0]["event_kind"], "feedback")
            self.assertEqual(tail_payload["events"][0]["text"], "Workstream add needs a goal option.")

            with isolated_acf_home(acf_home):
                exit_code, stdout, stderr = self.run_cli_output(["log", "summarize", str(project_root), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            summary_payload = json.loads(stdout)
            self.assertEqual(summary_payload["feedback_count"], 1)
            self.assertEqual(summary_payload["event_kind_counts"], {"feedback": 1})

    def test_usage_log_feedback_refuses_credential_like_text_without_persisting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            acf_home = Path(tmp) / "acf-home"
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            sentinel = "feedback-secret-sentinel"

            with isolated_acf_home(acf_home):
                exit_code, stdout, stderr = self.run_cli_output(
                    [
                        "log",
                        "feedback",
                        str(project_root),
                        "--text",
                        f"api_key={sentinel}",
                        "--json",
                    ]
                )
                log_path = acf.usage_log_path(project_root)

            self.assertEqual(acf.EXIT_INPUT_ERROR, exit_code)
            self.assertEqual("", stderr)
            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertNotIn(sentinel, json.dumps(payload, ensure_ascii=False))
            if log_path.exists():
                self.assertNotIn(sentinel, log_path.read_text(encoding="utf-8"))

    def test_usage_log_public_readers_redact_legacy_credential_like_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            acf_home = Path(tmp) / "acf-home"
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            sentinel = "legacy-log-secret-sentinel"
            legacy_event = {
                "schema_version": 1,
                "timestamp": "2026-09-14T00:00:00Z",
                "event_kind": "continuation_issue",
                "command": "continuation issue",
                "ok": True,
                "category": "transport",
                "severity": "high",
                "fingerprint": "legacy-log-fixture",
                "text": f"api_key={sentinel}",
                "evidence_refs": [],
            }
            with isolated_acf_home(acf_home):
                log_path = acf.usage_log_path(project_root)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(json.dumps(legacy_event) + "\n", encoding="utf-8")
                tail_code, tail_stdout, tail_stderr = self.run_cli_output(
                    ["log", "tail", str(project_root), "--limit", "1", "--json"]
                )
                issues_code, issues_stdout, issues_stderr = self.run_cli_output(
                    ["log", "issues", str(project_root), "--json"]
                )

            self.assertEqual(0, tail_code, tail_stderr)
            self.assertEqual(0, issues_code, issues_stderr)
            self.assertNotIn(sentinel, tail_stdout)
            self.assertNotIn(sentinel, issues_stdout)
            self.assertIn("redacted credential-like value", tail_stdout)
            self.assertIn("redacted credential-like value", issues_stdout)
            self.assertIn(sentinel, log_path.read_text(encoding="utf-8"))

    def test_usage_log_feedback_respects_disabled_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            acf_home = Path(tmp) / "acf-home"
            project_root = Path(tmp) / "project"
            target = project_root / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            with isolated_acf_home(acf_home):
                self.assertEqual(self.run_cli(["log", "disable", str(project_root)]), 0)
                exit_code, stdout, _stderr = self.run_cli_output(
                    ["log", "feedback", str(project_root), "--text", "Should not be recorded.", "--json"]
                )

            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], "input_error")
            with isolated_acf_home(acf_home):
                log_path = acf.usage_log_path(project_root)
            self.assertFalse(log_path.exists())

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
        self.assertIn('acf = "ai_context_framework.cli:main"', pyproject_text)
        self.assertIn('py-modules = ["acf"]', pyproject_text)
        self.assertIn("[tool.setuptools.data-files]", pyproject_text)

    def test_installed_console_script_can_init_context_outside_source_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package_source = tmp_path / "package-source"
            venv_dir = tmp_path / "venv"
            workspace = tmp_path / "workspace"
            shutil.copytree(
                acf.ROOT,
                package_source,
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".mypy_cache",
                    ".omx",
                    ".pytest_cache",
                    ".ruff_cache",
                    ".venv",
                    ".venv-*",
                    "__pycache__",
                    "*.egg-info",
                    "build",
                    "dist",
                ),
            )
            workspace.mkdir()
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if os.name == "nt":
                python_exe = venv_dir / "Scripts" / "python.exe"
                acf_exe = venv_dir / "Scripts" / "acf.exe"
            else:
                python_exe = venv_dir / "bin" / "python"
                acf_exe = venv_dir / "bin" / "acf"
            install = subprocess.run(
                [str(python_exe), "-m", "pip", "install", "--disable-pip-version-check", str(package_source)],
                check=False,
                cwd=str(tmp_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(install.returncode, 0, install.stdout)
            self.assertTrue(acf_exe.exists(), install.stdout)

            version = subprocess.run(
                [str(acf_exe), "--version"],
                check=False,
                cwd=str(workspace),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(version.returncode, 0, version.stdout)
            self.assertIn(acf.VERSION, version.stdout)

            init = subprocess.run(
                [str(acf_exe), "init", "docs/ai"],
                check=False,
                cwd=str(workspace),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(init.returncode, 0, init.stdout)
            target = workspace / "docs" / "ai"
            self.assertTrue((workspace / "AGENTS.md").exists(), init.stdout)
            self.assertTrue((target / "AGENTS.md").exists(), init.stdout)
            self.assertTrue((target / "reference" / "System_Manual.md").exists(), init.stdout)

            status = subprocess.run(
                [str(acf_exe), "status", "--json"],
                check=False,
                cwd=str(workspace),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(status.returncode, 0, status.stdout)
            payload = json.loads(status.stdout)
            self.assertTrue(payload["ok"], payload)
            self.assertEqual(Path(payload["context"]).resolve(), target.resolve())
            self.assertEqual(Path(payload["project_root"]).resolve(), workspace.resolve())

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

    def test_worklog_append_anchors_are_preserved_in_renderer_and_template(self):
        required_anchors = ("## 今日完成", "## 有价值的结论")
        rendered = acf.render_worklog_daily("2026-05-03", "Summary.", "Conclusion.")
        template = (acf.TEMPLATE_DIR / "worklog" / "daily" / "YYYY-MM-DD.md").read_text(encoding="utf-8")

        for anchor in required_anchors:
            self.assertIn(anchor, rendered)
            self.assertIn(anchor, template)

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
            self.assertEqual(payload["error_code"], acf.TARGET_EXISTS_APPEND_REQUIRED)
            self.assertEqual(payload["target"], "ctx/worklog/daily/2026-04-27.md")
            self.assertTrue(payload["next_actions"])

    def test_new_worklog_append_adds_to_existing_daily_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            target = project / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(
                [
                    "new",
                    "worklog",
                    str(target),
                    "--date",
                    "2026-05-03",
                    "--summary",
                    "Initial worklog.",
                    "--conclusion",
                    "Initial conclusion.",
                ]
            )

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "new",
                    "worklog",
                    str(target),
                    "--date",
                    "2026-05-03",
                    "--summary",
                    "Appended worklog.",
                    "--conclusion",
                    "Appended conclusion.",
                    "--append",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["action"], "append")
            self.assertEqual(payload["target"], "docs/ai/worklog/daily/2026-05-03.md")
            self.assertEqual(payload["anchor"], "## 今日完成")
            self.assertFalse(payload["created"])
            self.assertTrue(payload["appended"])
            self.assertTrue(payload["index_updated"])
            self.assertEqual(
                payload["changed_files"],
                [
                    "docs/ai/worklog/daily/2026-05-03.md",
                    "docs/ai/worklog/Worklog_Index.md",
                ],
            )
            self.assertEqual(payload["warnings"], [])

            daily_text = (target / "worklog" / "daily" / "2026-05-03.md").read_text(encoding="utf-8")
            self.assertIn("- Initial worklog.", daily_text)
            self.assertIn("- Appended worklog.", daily_text)
            self.assertIn("- Appended conclusion.", daily_text)
            index_text = (target / "worklog" / "Worklog_Index.md").read_text(encoding="utf-8")
            self.assertIn("Initial worklog.; 追加：Appended worklog.", index_text)

    def test_new_worklog_append_create_reports_create_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            target = project / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "new",
                    "worklog",
                    str(target),
                    "--date",
                    "2026-05-03",
                    "--summary",
                    "Created through append.",
                    "--append",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["action"], "create")
            self.assertEqual(payload["target"], "docs/ai/worklog/daily/2026-05-03.md")
            self.assertIsNone(payload["anchor"])
            self.assertTrue(payload["created"])
            self.assertFalse(payload["appended"])
            self.assertTrue(payload["index_updated"])
            self.assertEqual(payload["warnings"], [])

    def test_new_worklog_append_dry_run_reports_insert_point_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            target = project / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(
                [
                    "new",
                    "worklog",
                    str(target),
                    "--date",
                    "2026-05-03",
                    "--summary",
                    "Initial worklog.",
                ]
            )
            daily_file = target / "worklog" / "daily" / "2026-05-03.md"
            index_file = target / "worklog" / "Worklog_Index.md"
            before_daily = daily_file.read_text(encoding="utf-8")
            before_index = index_file.read_text(encoding="utf-8")
            before_daily_mtime = daily_file.stat().st_mtime_ns
            before_index_mtime = index_file.stat().st_mtime_ns

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "new",
                    "worklog",
                    str(target),
                    "--date",
                    "2026-05-03",
                    "--summary",
                    "Dry-run append.",
                    "--append",
                    "--dry-run",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["dry_run"])
            self.assertTrue(payload["would_change"])
            self.assertEqual(payload["operation"], "append")
            self.assertEqual(payload["target"], "docs/ai/worklog/daily/2026-05-03.md")
            self.assertEqual(payload["anchor"], "## 今日完成")
            self.assertIsInstance(payload["insert_after_line"], int)
            self.assertGreater(payload["insert_after_line"], 0)
            self.assertEqual(
                payload["changed_files"],
                [
                    "docs/ai/worklog/daily/2026-05-03.md",
                    "docs/ai/worklog/Worklog_Index.md",
                ],
            )
            self.assertEqual(daily_file.read_text(encoding="utf-8"), before_daily)
            self.assertEqual(index_file.read_text(encoding="utf-8"), before_index)
            self.assertEqual(daily_file.stat().st_mtime_ns, before_daily_mtime)
            self.assertEqual(index_file.stat().st_mtime_ns, before_index_mtime)

    def test_new_worklog_append_force_conflict_returns_stable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            target = project / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "new",
                    "worklog",
                    str(target),
                    "--date",
                    "2026-05-03",
                    "--summary",
                    "Conflict.",
                    "--append",
                    "--force",
                    "--dry-run",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], acf.APPEND_FORCE_CONFLICT)
            self.assertEqual(payload["target"], "docs/ai/worklog/daily/2026-05-03.md")

    def test_new_worklog_append_missing_anchor_returns_stable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            target = project / "docs" / "ai"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(
                [
                    "new",
                    "worklog",
                    str(target),
                    "--date",
                    "2026-05-03",
                    "--summary",
                    "Initial worklog.",
                ]
            )
            daily_file = target / "worklog" / "daily" / "2026-05-03.md"
            daily_file.write_text(
                daily_file.read_text(encoding="utf-8").replace("## 今日完成", "## 今日记录"),
                encoding="utf-8",
            )

            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "new",
                    "worklog",
                    str(target),
                    "--date",
                    "2026-05-03",
                    "--summary",
                    "Append without anchor.",
                    "--append",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            payload = json.loads(stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], acf.ANCHOR_NOT_FOUND)
            self.assertEqual(payload["target"], "docs/ai/worklog/daily/2026-05-03.md")

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

    def test_new_reference_creates_safe_markdown_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "new",
                    "reference",
                    str(target),
                    "--file",
                    "reference/Feature_Guide.md",
                    "--title",
                    "Feature Guide",
                    "--status",
                    "Active",
                    "--summary",
                    "Reusable guidance for a core feature.",
                    "--body",
                    "Keep guidance stable and reviewable.",
                    "--next-action",
                    "Read before changing related commands.",
                    "--dry-run",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "new reference")
            self.assertEqual(payload["target"], "reference/Feature_Guide.md")
            self.assertFalse((target / "reference" / "Feature_Guide.md").exists())

            exit_code = self.run_cli(
                [
                    "new",
                    "reference",
                    str(target),
                    "--file",
                    "reference/Feature_Guide.md",
                    "--title",
                    "Feature Guide",
                    "--status",
                    "Active",
                    "--summary",
                    "Reusable guidance for a core feature.",
                    "--body",
                    "Keep guidance stable and reviewable.",
                    "--next-action",
                    "Read before changing related commands.",
                    "--check-after",
                ]
            )
            self.assertEqual(exit_code, 0)
            text = (target / "reference" / "Feature_Guide.md").read_text(encoding="utf-8")
            self.assertIn("# Feature Guide", text)
            self.assertIn("## 状态\n\nActive", text)
            self.assertIn("1. Keep guidance stable and reviewable.", text)
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_new_reference_refuses_unsafe_or_managed_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            self.assertEqual(
                self.run_cli(
                    [
                        "new",
                        "reference",
                        str(target),
                        "--file",
                        "../Outside.md",
                        "--title",
                        "Outside",
                        "--summary",
                        "Unsafe.",
                    ]
                ),
                acf.EXIT_SAFETY_REFUSED,
            )
            self.assertEqual(
                self.run_cli(
                    [
                        "new",
                        "reference",
                        str(target),
                        "--file",
                        "reference/knowledge/K999-bad.md",
                        "--title",
                        "Bad Knowledge",
                        "--summary",
                        "Managed by knowledge commands.",
                    ]
                ),
                acf.EXIT_SAFETY_REFUSED,
            )

    def test_new_rule_creates_file_and_rules_index_for_minimal_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.assertFalse((target / "rules" / "Rules_Index.md").exists())

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "new",
                    "rule",
                    str(target),
                    "--file",
                    "rules/Testing_Rules.md",
                    "--title",
                    "Testing Rules",
                    "--condition",
                    "涉及测试、验证或回归检查。",
                    "--purpose",
                    "测试和验证规则。",
                    "--rule",
                    "修改 CLI 后运行相关测试。",
                    "--rule",
                    "文档变更后运行 context check。",
                    "--check-after",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "new rule")
            self.assertTrue(payload["index_updated"])
            rule_text = (target / "rules" / "Testing_Rules.md").read_text(encoding="utf-8")
            self.assertIn("# Testing Rules", rule_text)
            self.assertIn("1. 修改 CLI 后运行相关测试。", rule_text)
            self.assertIn("2. 文档变更后运行 context check。", rule_text)
            index_text = (target / "rules" / "Rules_Index.md").read_text(encoding="utf-8")
            self.assertIn("| `Testing_Rules.md` | 涉及测试、验证或回归检查。 | 测试和验证规则。 |", index_text)
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_new_rule_refuses_duplicate_without_force_and_force_updates_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            args = [
                "new",
                "rule",
                str(target),
                "--file",
                "rules/Testing_Rules.md",
                "--title",
                "Testing Rules",
                "--condition",
                "涉及测试。",
                "--purpose",
                "测试规则。",
                "--rule",
                "运行测试。",
            ]
            self.assertEqual(self.run_cli(args), 0)
            self.assertEqual(self.run_cli(args), acf.EXIT_SAFETY_REFUSED)

            self.assertEqual(
                self.run_cli(
                    args
                    + [
                        "--condition",
                        "涉及回归测试。",
                        "--purpose",
                        "更新后的测试规则。",
                        "--rule",
                        "运行完整测试。",
                        "--force",
                    ]
                ),
                0,
            )
            index_text = (target / "rules" / "Rules_Index.md").read_text(encoding="utf-8")
            self.assertIn("更新后的测试规则。", index_text)
            self.assertNotIn("| `Testing_Rules.md` | 涉及测试。 | 测试规则。 |", index_text)

    def test_new_feedback_adds_next_feedback_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "new",
                    "feedback",
                    str(target),
                    "--type",
                    "需求",
                    "--content",
                    "需要一个安全反馈写入命令。",
                    "--source",
                    "2026-05-08 user",
                    "--next-action",
                    "进入任务计划评估。",
                    "--dry-run",
                    "--json",
                ]
            )

            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "new feedback")
            self.assertEqual(payload["id"], "F001")
            inbox_path = target / "active" / "Feedback_Inbox.md"
            self.assertNotIn("需要一个安全反馈写入命令。", inbox_path.read_text(encoding="utf-8"))

            exit_code = self.run_cli(
                [
                    "new",
                    "feedback",
                    str(target),
                    "--type",
                    "需求",
                    "--content",
                    "需要一个安全反馈写入命令。",
                    "--source",
                    "2026-05-08 user",
                    "--next-action",
                    "进入任务计划评估。",
                    "--check-after",
                ]
            )
            self.assertEqual(exit_code, 0)
            inbox_text = inbox_path.read_text(encoding="utf-8")
            self.assertIn(
                "| F001 | Open | 需求 | 需要一个安全反馈写入命令。 | 2026-05-08 user | 进入任务计划评估。 |",
                inbox_text,
            )
            result = acf.check_context(target, "minimal", strict=False)
            self.assertFalse(result.errors)

    def test_new_feedback_refuses_duplicate_id_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            args = [
                "new",
                "feedback",
                str(target),
                "--id",
                "F007",
                "--type",
                "问题",
                "--content",
                "First feedback.",
                "--source",
                "2026-05-08 user",
            ]
            self.assertEqual(self.run_cli(args), 0)
            self.assertEqual(self.run_cli(args), acf.EXIT_SAFETY_REFUSED)
            self.assertEqual(
                self.run_cli(
                    args
                    + [
                        "--content",
                        "Updated feedback.",
                        "--next-action",
                        "已更新。",
                        "--force",
                    ]
                ),
                0,
            )
            inbox_text = (target / "active" / "Feedback_Inbox.md").read_text(encoding="utf-8")
            self.assertIn("Updated feedback.", inbox_text)
            self.assertNotIn("First feedback.", inbox_text)

    def test_feedback_lifecycle_commands_update_and_archive_one_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(
                [
                    "new",
                    "feedback",
                    str(target),
                    "--id",
                    "F019",
                    "--type",
                    "改进",
                    "--content",
                    "需要反馈生命周期命令。",
                    "--source",
                    "2026-05-08 user",
                ]
            )

            exit_code, stdout, stderr = self.run_cli_output(
                ["feedback", "list", str(target), "--status", "Open", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "feedback list")
            self.assertEqual(payload["items"][0]["id"], "F019")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "feedback",
                    "triage",
                    str(target),
                    "F019",
                    "--next-action",
                    "进入 RC 计划。",
                    "--evidence",
                    "active/Task_Plan.md T003",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assert_success_json_contract(self.json_payload(stdout), "feedback triage")
            inbox_text = (target / "active" / "Feedback_Inbox.md").read_text(encoding="utf-8")
            self.assertIn("| F019 | Triaged | 改进 | 需要反馈生命周期命令。 | 2026-05-08 user | 进入 RC 计划。 证据：active/Task_Plan.md T003 |", inbox_text)

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "feedback",
                    "done",
                    str(target),
                    "F019",
                    "--result",
                    "已实现反馈生命周期命令。",
                    "--evidence",
                    "tests/test_cli.py",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assert_success_json_contract(self.json_payload(stdout), "feedback done")

            exit_code, stdout, stderr = self.run_cli_output(
                ["feedback", "archive-candidates", str(target), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "feedback archive-candidates")
            self.assertEqual(payload["candidates"][0]["id"], "F019")

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "feedback",
                    "archive",
                    str(target),
                    "F019",
                    "--reason",
                    "RC 已关闭。",
                    "--date",
                    "2026-05-08",
                    "--check-after",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "feedback archive")
            self.assertEqual(payload["archive_path"], "archive/feedback/2026-05.md")
            self.assertNotIn("F019", (target / "active" / "Feedback_Inbox.md").read_text(encoding="utf-8"))
            archive_text = (target / "archive" / "feedback" / "2026-05.md").read_text(encoding="utf-8")
            self.assertIn("| 2026-05-08 | F019 | Done | 改进 | 需要反馈生命周期命令。 | 2026-05-08 user | 已实现反馈生命周期命令。 证据：tests/test_cli.py | RC 已关闭。 |", archive_text)

    def test_feedback_archive_refuses_open_or_missing_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.run_cli(["init", str(target), "--profile", "minimal"])
            self.run_cli(
                [
                    "new",
                    "feedback",
                    str(target),
                    "--id",
                    "F020",
                    "--type",
                    "问题",
                    "--content",
                    "Open item.",
                    "--source",
                    "2026-05-08 user",
                ]
            )

            exit_code, stdout, _stderr = self.run_cli_output(
                ["feedback", "archive", str(target), "F020", "--reason", "too early", "--json"]
            )
            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            self.assert_failure_json_contract(self.json_payload(stdout), "feedback_archive_blocked", "feedback")

            exit_code, stdout, _stderr = self.run_cli_output(
                ["feedback", "done", str(target), "F999", "--result", "none", "--evidence", "none", "--json"]
            )
            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            self.assert_failure_json_contract(self.json_payload(stdout), "feedback_not_found", "feedback")

            self.run_cli(
                [
                    "new",
                    "feedback",
                    str(target),
                    "--id",
                    "F021",
                    "--type",
                    "需求",
                    "--content",
                    "Reject item.",
                    "--source",
                    "2026-05-08 user",
                ]
            )
            exit_code, stdout, stderr = self.run_cli_output(
                ["feedback", "reject", str(target), "F021", "--reason", "不采纳。", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "feedback reject")
            self.assertEqual(payload["item"]["status"], "Rejected")
            self.assertIn("Rejected：不采纳。", (target / "active" / "Feedback_Inbox.md").read_text(encoding="utf-8"))

    def test_new_human_note_writes_standard_human_inbox_and_refuses_minimal(self):
        with tempfile.TemporaryDirectory() as tmp:
            standard = Path(tmp) / "standard"
            minimal = Path(tmp) / "minimal"
            self.run_cli(["init", str(standard), "--profile", "standard"])
            self.run_cli(["init", str(minimal), "--profile", "minimal"])

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "new",
                    "human-note",
                    str(standard),
                    "--type",
                    "想法",
                    "--content",
                    "人工临时想法。",
                    "--related",
                    "reference/Product_Roadmap.md",
                    "--suggestion",
                    "后续判断是否进入 Task_Plan。",
                    "--dry-run",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "new human-note")
            self.assertEqual(payload["id"], "H001")
            note_path = standard / "human" / "Human_Notes.md"
            self.assertNotIn("人工临时想法。", note_path.read_text(encoding="utf-8"))

            exit_code = self.run_cli(
                [
                    "new",
                    "human-note",
                    str(standard),
                    "--type",
                    "想法",
                    "--content",
                    "人工临时想法。",
                    "--related",
                    "reference/Product_Roadmap.md",
                    "--suggestion",
                    "后续判断是否进入 Task_Plan。",
                    "--check-after",
                ]
            )
            self.assertEqual(exit_code, 0)
            note_text = note_path.read_text(encoding="utf-8")
            self.assertIn("| H001 | Open | 想法 | 人工临时想法。 | reference/Product_Roadmap.md | 后续判断是否进入 Task_Plan。 | 未整理。 |", note_text)
            index_text = (standard / "human" / "Human_Index.md").read_text(encoding="utf-8")
            self.assertIn("| H001 | Open | 想法 | 人工临时想法。 | Human_Notes.md |", index_text)

            exit_code, stdout, _stderr = self.run_cli_output(
                [
                    "new",
                    "human-note",
                    str(minimal),
                    "--type",
                    "想法",
                    "--content",
                    "Minimal should refuse.",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, acf.EXIT_INPUT_ERROR)
            self.assert_failure_json_contract(self.json_payload(stdout), "human_notes_missing", "new")

    def test_human_index_sync_list_mark_and_check_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "standard"
            self.run_cli(["init", str(target), "--profile", "standard"])
            report = target / "human" / "reports" / "PetroSim_Runtime_Recovery_Notes_2026-05-07.md"
            report.write_text("# PetroSim Runtime Recovery Notes\n\n人工复盘。\n", encoding="utf-8")

            exit_code, stdout, stderr = self.run_cli_output(["human", "index", "sync", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "human index sync")
            self.assertEqual(payload["indexed_total"], 1)
            self.assertEqual(payload["items"][0]["path"], "reports/PetroSim_Runtime_Recovery_Notes_2026-05-07.md")
            self.assertEqual(payload["items"][0]["date"], "2026-05-07")
            index_path = target / "human" / "Human_Index.md"
            index_path.write_text(
                index_path.read_text(encoding="utf-8").replace("| 2026-05-07 | 未整理。 |", "| 未标注 | 未整理。 |"),
                encoding="utf-8",
            )
            exit_code, stdout, stderr = self.run_cli_output(["human", "index", "sync", str(target), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assertEqual(payload["items"][0]["date"], "2026-05-07")

            exit_code, stdout, stderr = self.run_cli_output(["human", "list", str(target), "--status", "Open", "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "human list")
            self.assertEqual(payload["summary"]["total"], 1)

            exit_code, stdout, stderr = self.run_cli_output(
                [
                    "human",
                    "mark",
                    str(target),
                    "reports/PetroSim_Runtime_Recovery_Notes_2026-05-07.md",
                    "--status",
                    "Extracted",
                    "--extracted-to",
                    "reference/PetroSim_Runtime_Runbook.md",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = self.json_payload(stdout)
            self.assert_success_json_contract(payload, "human mark")
            self.assertEqual(payload["item"]["status"], "Extracted")
            self.assertIn("reference/PetroSim_Runtime_Runbook.md", (target / "human" / "Human_Index.md").read_text(encoding="utf-8"))

            index_text = (target / "human" / "Human_Index.md").read_text(encoding="utf-8")
            (target / "human" / "Human_Index.md").write_text(
                index_text.replace("reports/PetroSim_Runtime_Recovery_Notes_2026-05-07.md", "reports/Missing.md"),
                encoding="utf-8",
            )
            result = acf.check_context(target, "standard", strict=True)
            self.assertTrue(any("missing indexed path `reports/Missing.md`" in error for error in result.errors))

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
            self.assertIn("当前事实变更候选", draft_text)
            self.assertIn("唯一权威位置判断", draft_text)
            self.assertIn("acf edit section get|replace", draft_text)
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
