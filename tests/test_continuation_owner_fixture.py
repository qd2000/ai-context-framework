"""Isolated owner-context verification fixture regression."""

import importlib.util
import os
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE_SCRIPT = ROOT / "scripts" / "continuation_owner_fixture.py"


def load_fixture_module():
    spec = importlib.util.spec_from_file_location("acf_owner_context_fixture", FIXTURE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def real_projects_root() -> pathlib.Path:
    home = os.environ.get("ACF_HOME")
    base = pathlib.Path(home) if home else pathlib.Path.home() / ".acf"
    return base / "projects"


def project_namespace_names(root: pathlib.Path) -> tuple[str, ...]:
    """Return the set of real ACF_HOME project namespaces as a sorted tuple.

    Only the namespace set is compared: concurrent external continuation activity
    in other projects may legitimately update mtimes or log contents, while this
    regression is about the fixture creating or removing real namespaces.
    """
    if not root.is_dir():
        return ()
    return tuple(sorted(entry.name for entry in root.iterdir()))


class ContinuationOwnerFixtureTests(unittest.TestCase):
    def test_classify_layer_distinguishes_pre_acf_from_acf_errors(self):
        module = load_fixture_module()
        self.assertEqual(module.classify_layer({"ok": True, "payload": {}}), "ok")
        self.assertEqual(module.classify_layer({"ok": False, "payload": None}), "pre_acf")
        self.assertEqual(
            module.classify_layer({"ok": False, "payload": {"error_code": "owner_context_binding_mismatch"}}),
            "acf_owner_binding",
        )
        self.assertEqual(
            module.classify_layer({"ok": False, "payload": {"error_code": "invalid_argument"}}),
            "acf_parser",
        )
        self.assertEqual(
            module.classify_layer({"ok": False, "payload": {"error_code": "workspace_digest_failed"}}),
            "acf_runtime",
        )

    def test_isolated_fixture_verifies_acf_side_owner_context(self):
        module = load_fixture_module()
        projects_root = real_projects_root()
        before = project_namespace_names(projects_root)

        result = module.OwnerContextFixture([sys.executable, str(ROOT / "acf.py")], False).run()

        after = project_namespace_names(projects_root)
        failures = [step for step in result["steps"] if not step["ok"]]
        self.assertTrue(result["ok"], failures)
        self.assertEqual(result["acf_side_verdict"], "acf_side_ok")
        self.assertEqual(result["real_chain_status"], "not_verified_here")
        by_name = {step["name"]: step for step in result["steps"]}
        for name in ("assert-owner", "progress", "release"):
            self.assertIn(name, by_name)
            self.assertTrue(by_name[name]["ok"], by_name[name])
            self.assertEqual(by_name[name]["layer"], "ok")
        handle_step = by_name["owner-context handle issued"]
        self.assertTrue(handle_step["ok"])
        created = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        self.assertEqual(
            (created, removed),
            ([], []),
            "owner-context fixture must not create or remove real ACF_HOME project namespaces",
        )


if __name__ == "__main__":
    unittest.main()
