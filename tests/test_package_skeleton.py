import ast
import importlib
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class PackageSkeletonTests(unittest.TestCase):
    def test_package_cli_module_is_importable(self):
        package = importlib.import_module("ai_context_framework")
        cli = importlib.import_module("ai_context_framework.cli")
        constants = importlib.import_module("ai_context_framework.constants")
        json_contract = importlib.import_module("ai_context_framework.json_contract")

        self.assertEqual(package.__all__, ())
        self.assertTrue(callable(cli.main))
        self.assertTrue(callable(json_contract.print_json))
        self.assertEqual(constants.JSON_SCHEMA_VERSION, 1)
        self.assertEqual(constants.EXIT_CHECK_FAILED, 1)
        self.assertEqual(constants.EXIT_INPUT_ERROR, 2)
        self.assertEqual(constants.EXIT_SAFETY_REFUSED, 3)
        self.assertEqual(constants.EXIT_RUNTIME_ERROR, 70)
        self.assertEqual(constants.TARGET_EXISTS_APPEND_REQUIRED, "TARGET_EXISTS_APPEND_REQUIRED")
        self.assertEqual(constants.APPEND_FORCE_CONFLICT, "APPEND_FORCE_CONFLICT")
        self.assertEqual(constants.ANCHOR_NOT_FOUND, "ANCHOR_NOT_FOUND")

    def test_package_cli_does_not_import_top_level_acf(self):
        source = (ROOT / "ai_context_framework" / "cli.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)

        imported_modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)

        self.assertNotIn("acf", imported_modules)

    def test_version_fact_remains_in_top_level_acf_until_version_migration(self):
        self.assertFalse((ROOT / "ai_context_framework" / "version.py").exists())

        source = (ROOT / "acf.py").read_text(encoding="utf-8")
        self.assertRegex(source, r'(?m)^VERSION = "v[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"$')


if __name__ == "__main__":
    unittest.main()
