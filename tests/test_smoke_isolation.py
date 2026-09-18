"""Regression: the minimal smoke suite must never touch the real user-level runtime state."""

import importlib.util
import json
import os
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = ROOT / "scripts" / "minimal_smoke.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("acf_minimal_smoke", SMOKE_SCRIPT)
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
    regression is about a smoke run creating or removing namespaces.
    """
    if not root.is_dir():
        return ()
    return tuple(sorted(entry.name for entry in root.iterdir()))


class SmokeIsolationTests(unittest.TestCase):
    def test_runner_forces_isolated_acf_home_per_scenario(self):
        smoke = load_smoke_module()
        real_home = str(real_projects_root().parent)
        runner = smoke.SmokeRunner(
            [
                sys.executable,
                "-c",
                "import json, os; print(json.dumps({'ok': True, 'acf_home': os.environ.get('ACF_HOME')}))",
            ],
            keep_tmp=True,
        )

        def probe(tmp_path, steps):
            steps.append(runner.run_acf([]))

        runner.scenario("isolation probe", probe)
        record = runner.scenarios[0]
        self.assertTrue(record["ok"], record)
        observed = record["steps"][0]["payload"]["acf_home"]
        self.assertIsNotNone(observed)
        self.assertTrue(observed.startswith(str(pathlib.Path(record["tmp"]))), observed)
        self.assertNotEqual(observed, real_home)

    def test_minimal_smoke_run_leaves_real_acf_home_untouched(self):
        smoke = load_smoke_module()
        projects_root = real_projects_root()
        before = project_namespace_names(projects_root)

        runner = smoke.SmokeRunner([sys.executable, str(ROOT / "acf.py")], keep_tmp=False)
        result = runner.run()

        after = project_namespace_names(projects_root)
        failed = [scenario["name"] for scenario in result["scenarios"] if not scenario["ok"]]
        self.assertTrue(result["ok"], f"smoke scenarios failed: {failed}")
        created = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        self.assertEqual(
            (created, removed),
            ([], []),
            "minimal smoke must not create or remove real ACF_HOME project namespaces",
        )


if __name__ == "__main__":
    unittest.main()
