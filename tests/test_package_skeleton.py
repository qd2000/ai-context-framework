import ast
import importlib
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class PackageSkeletonTests(unittest.TestCase):
    def test_package_cli_module_is_importable(self):
        package = importlib.import_module("ai_context_framework")
        archive = importlib.import_module("ai_context_framework.commands.archive")
        cli = importlib.import_module("ai_context_framework.cli")
        constants = importlib.import_module("ai_context_framework.constants")
        doctor = importlib.import_module("ai_context_framework.commands.doctor")
        runtime = importlib.import_module("ai_context_framework.runtime")
        runtime_parts = [
            importlib.import_module(f"ai_context_framework.runtime_parts.{name}")
            for name in (
                "archive_workstream",
                "check",
                "core",
                "doctor",
                "knowledge_review",
                "objects",
                "plan_task",
                "upgrade",
            )
        ]
        task_domain = importlib.import_module("ai_context_framework.domains.tasks")
        upgrade_audit = importlib.import_module("ai_context_framework.domains.upgrade_audit")
        decisions = importlib.import_module("ai_context_framework.commands.decisions")
        front_matter = importlib.import_module("ai_context_framework.front_matter")
        json_contract = importlib.import_module("ai_context_framework.json_contract")
        locks = importlib.import_module("ai_context_framework.locks")
        markers = importlib.import_module("ai_context_framework.markers")
        markdown = importlib.import_module("ai_context_framework.markdown")
        models = importlib.import_module("ai_context_framework.models")
        observability = importlib.import_module("ai_context_framework.observability")
        paths = importlib.import_module("ai_context_framework.paths")
        tables = importlib.import_module("ai_context_framework.tables")
        templates = importlib.import_module("ai_context_framework.templates")
        version = importlib.import_module("ai_context_framework.version")
        edit_link = importlib.import_module("ai_context_framework.commands.edit_link")
        init_upgrade = importlib.import_module("ai_context_framework.commands.init_upgrade")
        feedback = importlib.import_module("ai_context_framework.commands.feedback")
        human = importlib.import_module("ai_context_framework.commands.human")
        knowledge_commands = importlib.import_module("ai_context_framework.commands.knowledge")
        log_commands = importlib.import_module("ai_context_framework.commands.log")
        log_inventory = importlib.import_module("ai_context_framework.commands.log_inventory")
        new_context = importlib.import_module("ai_context_framework.commands.new_context")
        plan_task = importlib.import_module("ai_context_framework.commands.plan_task")
        review_audit_curate = importlib.import_module("ai_context_framework.commands.review_audit_curate")
        status_check = importlib.import_module("ai_context_framework.commands.status_check")
        versioning = importlib.import_module("ai_context_framework.commands.versioning")
        workstream = importlib.import_module("ai_context_framework.commands.workstream")
        worklog = importlib.import_module("ai_context_framework.commands.worklog")
        checks = importlib.import_module("ai_context_framework.validators.checks")
        template_checks = importlib.import_module("ai_context_framework.validators.template_checks")

        self.assertEqual(package.__all__, ())
        self.assertTrue(callable(cli.main))
        self.assertTrue(callable(runtime.main))
        self.assertTrue(all(module.__name__.startswith("ai_context_framework.runtime_parts.") for module in runtime_parts))
        self.assertTrue(callable(front_matter.parse_front_matter))
        self.assertTrue(callable(json_contract.print_json))
        self.assertTrue(callable(locks.acquire_context_lock))
        self.assertTrue(markers.is_acf_placeholder("【ACF:DATE】"))
        self.assertTrue(callable(markers.replace_generated_marker_block))
        self.assertEqual(markdown.heading_level("## Heading"), 2)
        self.assertTrue(models.CheckResult([], []).ok)
        self.assertTrue(callable(observability.usage_log_status_payload))
        self.assertEqual(paths.slugify_project_name("AI Context Framework"), "AI-Context-Framework")
        self.assertEqual(tables.render_table_row(["a", "b|c"]), "| a | b/c |")
        self.assertEqual(tables.parse_markdown_table_rows("| A | B |\n|---|---|\n| x | y |\n"), [["A", "B"], ["x", "y"]])
        self.assertEqual(tables.parse_cell_updates(["A=x"]), {"A": "x"})
        self.assertEqual(templates.TEMPLATE_DIR.name, "template")
        self.assertTrue((templates.TEMPLATE_DIR / "AGENTS.md").is_file())
        self.assertTrue(callable(archive.archive_sync_command))
        self.assertTrue(callable(doctor.doctor_command))
        self.assertTrue(callable(decisions.decisions_sync_command))
        self.assertTrue(callable(edit_link.resolve_context_markdown_file))
        self.assertTrue(callable(feedback.feedback_list_command))
        self.assertTrue(callable(human.human_list_command))
        self.assertTrue(callable(init_upgrade.init_command))
        self.assertTrue(callable(knowledge_commands.knowledge_draft_command))
        self.assertTrue(callable(new_context.new_adr_command))
        self.assertTrue(callable(plan_task.plan_status_command))
        self.assertTrue(callable(review_audit_curate.review_stale_command))
        self.assertRegex(version.VERSION, r"^v[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$")
        self.assertEqual(log_commands.command_label(type("Args", (), {"command": "doctor"})()), "doctor")
        self.assertTrue(callable(log_inventory.log_projects_command))
        self.assertTrue(callable(upgrade_audit.build_upgrade_plan_payload))
        self.assertTrue(callable(status_check.check_command))
        self.assertEqual(versioning.normalize_release_version(version.VERSION), (version.VERSION, version.VERSION.removeprefix("v")))
        self.assertTrue(callable(workstream.workstream_status_command))
        self.assertIn("## 今日完成", worklog.render_worklog_daily("2026-06-01", "summary", "conclusion"))
        self.assertEqual(checks.validate_task_id("T001"), "T001")
        self.assertTrue(callable(template_checks.check_template_packaging))
        self.assertEqual(constants.JSON_SCHEMA_VERSION, 1)
        self.assertEqual(constants.EXIT_CHECK_FAILED, 1)
        self.assertEqual(constants.EXIT_INPUT_ERROR, 2)
        self.assertEqual(constants.EXIT_SAFETY_REFUSED, 3)
        self.assertEqual(constants.EXIT_RUNTIME_ERROR, 70)
        self.assertEqual(constants.TARGET_EXISTS_APPEND_REQUIRED, "TARGET_EXISTS_APPEND_REQUIRED")
        self.assertEqual(constants.APPEND_FORCE_CONFLICT, "APPEND_FORCE_CONFLICT")
        self.assertEqual(constants.ANCHOR_NOT_FOUND, "ANCHOR_NOT_FOUND")
        self.assertEqual(task_domain.normalize_plan_reference_path("reference/Plan.md"), "reference/Plan.md")

    def test_package_modules_stay_agent_friendly_in_size(self):
        oversized = []
        for path in (ROOT / "ai_context_framework").rglob("*.py"):
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            if line_count > 2000:
                oversized.append((path.relative_to(ROOT).as_posix(), line_count))

        self.assertEqual(oversized, [])

    def test_package_modules_do_not_import_top_level_acf(self):
        package_dir = ROOT / "ai_context_framework"
        violations = []

        for path in package_dir.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "acf" or alias.name.startswith("acf."):
                            violations.append(path.relative_to(ROOT).as_posix())
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module == "acf" or node.module.startswith("acf."):
                        violations.append(path.relative_to(ROOT).as_posix())

        self.assertEqual(violations, [])

    def test_package_discovery_metadata_covers_package_modules(self):
        pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('acf = "ai_context_framework.cli:main"', pyproject_text)
        self.assertIn('py-modules = ["acf"]', pyproject_text)
        self.assertIn("[tool.setuptools.packages.find]", pyproject_text)
        self.assertIn('include = ["ai_context_framework*"]', pyproject_text)

        top_level = (ROOT / "ai_context_framework.egg-info" / "top_level.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("acf", top_level.splitlines())
        self.assertIn("ai_context_framework", top_level.splitlines())

        entry_points = (ROOT / "ai_context_framework.egg-info" / "entry_points.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("acf = ai_context_framework.cli:main", entry_points)

        sources = (ROOT / "ai_context_framework.egg-info" / "SOURCES.txt").read_text(
            encoding="utf-8"
        )
        for path in (ROOT / "ai_context_framework").rglob("*.py"):
            self.assertIn(path.relative_to(ROOT).as_posix(), sources)

    def test_version_fact_lives_in_package_after_version_migration(self):
        self.assertTrue((ROOT / "ai_context_framework" / "version.py").exists())
        source = (ROOT / "acf.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r'(?m)^VERSION = "v[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"$')
        self.assertIn("from ai_context_framework.version import VERSION", source)
        self.assertIn("from ai_context_framework import runtime as _runtime", source)
        self.assertLessEqual(len(source.splitlines()), 100)

    def test_workstream_dependency_binding_refreshes_external_symbols(self):
        workstream = importlib.import_module("ai_context_framework.commands.workstream")
        sentinel = object()
        previous = getattr(workstream, "dependency_probe", sentinel)
        try:
            original_handler = workstream.workstream_status_command
            workstream._bind(
                workstream.WorkstreamDependencies(
                    {"dependency_probe": "first", "workstream_status_command": "replaced"}
                )
            )
            self.assertEqual(workstream.dependency_probe, "first")
            self.assertIs(workstream.workstream_status_command, original_handler)

            workstream._bind(workstream.WorkstreamDependencies({"dependency_probe": "second"}))
            self.assertEqual(workstream.dependency_probe, "second")
        finally:
            if previous is sentinel:
                if hasattr(workstream, "dependency_probe"):
                    delattr(workstream, "dependency_probe")
            else:
                workstream.dependency_probe = previous

    def test_moved_workstream_helpers_remain_import_compatible(self):
        acf_module = importlib.import_module("acf")
        workstream = importlib.import_module("ai_context_framework.commands.workstream")

        self.assertIs(acf_module.parse_workstream_archive_date, workstream.parse_workstream_archive_date)
        with self.assertRaises(AttributeError):
            getattr(acf_module, "definitely_missing_workstream_helper")

    def test_top_level_shim_syncs_root_through_the_public_entry_point(self):
        acf_module = importlib.import_module("acf")
        runtime = importlib.import_module("ai_context_framework.runtime")
        previous_acf_root = acf_module.ROOT
        previous_runtime_root = runtime.ROOT
        try:
            acf_module.ROOT = ROOT / "missing-source-checkout"
            _ = acf_module.read_project_versions
            self.assertEqual(runtime.ROOT, acf_module.ROOT)
            self.assertEqual(runtime.set_root(previous_runtime_root), previous_runtime_root)
        finally:
            acf_module.ROOT = previous_acf_root
            runtime.set_root(previous_runtime_root)

    def test_top_level_shim_does_not_write_runtime_internals(self):
        acf_module = importlib.import_module("acf")
        runtime = importlib.import_module("ai_context_framework.runtime")
        shim_source = pathlib.Path(acf_module.__file__).read_text(encoding="utf-8")

        self.assertTrue(callable(runtime.set_root))
        self.assertIn("set_root", shim_source)
        self.assertNotIn("_sync_runtime_part_globals", shim_source)
        self.assertNotIn("_runtime.ROOT =", shim_source)


if __name__ == "__main__":
    unittest.main()
