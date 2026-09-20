"""Regression: the minimal smoke suite must never touch the real user-level runtime state."""

import ast
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = ROOT / "scripts" / "minimal_smoke.py"
WORKTREE_SMOKE_SCRIPT = ROOT / "scripts" / "worktree_release_smoke.py"


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


def load_worktree_smoke_module():
    spec = importlib.util.spec_from_file_location(
        "acf_worktree_release_smoke", WORKTREE_SMOKE_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def subprocess_runs_without_env(source: str) -> list[int]:
    """Return line numbers of ``subprocess.run(...)`` calls that omit ``env``."""

    tree = ast.parse(source)
    missing: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "run":
            continue
        if not isinstance(func.value, ast.Name) or func.value.id != "subprocess":
            continue
        if not any(keyword.arg == "env" for keyword in node.keywords):
            missing.append(node.lineno)
    return missing


class WorktreeReleaseSmokeIsolationTests(unittest.TestCase):
    def test_isolated_env_points_at_the_run_root(self):
        smoke = load_worktree_smoke_module()
        real_home = str(real_projects_root().parent)
        with tempfile.TemporaryDirectory(prefix="acf-smoke-isolation-") as tmp:
            root = pathlib.Path(tmp)
            env = smoke.isolated_acf_home_env(root)
            self.assertEqual(env["ACF_HOME"], str(root / "acf-home"))
            self.assertTrue(env["ACF_HOME"].startswith(str(root)))
            self.assertNotEqual(env["ACF_HOME"], real_home)

    def test_every_subprocess_call_forwards_the_isolated_env(self):
        missing = subprocess_runs_without_env(
            WORKTREE_SMOKE_SCRIPT.read_text(encoding="utf-8")
        )
        self.assertEqual(
            missing,
            [],
            "every subprocess.run in the release smoke must forward the isolated env",
        )

    def test_subprocess_calls_receive_isolated_acf_home(self):
        smoke = load_worktree_smoke_module()
        captured: dict[str, object] = {}
        original_run = smoke.subprocess.run
        expected_home = ""

        class _FakeCompleted:
            returncode = 0
            stdout = "{}"
            stderr = ""

        def fake_run(argv, **kwargs):
            captured.update(kwargs)
            return _FakeCompleted()

        smoke.subprocess.run = fake_run
        try:
            with tempfile.TemporaryDirectory(prefix="acf-smoke-isolation-") as tmp:
                root = pathlib.Path(tmp)
                with smoke.isolated_runtime_state(root) as active_env:
                    expected_home = active_env["ACF_HOME"]
                    smoke.run(["acf", "status", "--json"], cwd=root)
        finally:
            smoke.subprocess.run = original_run
        self.assertIn("env", captured)
        self.assertEqual(captured["env"]["ACF_HOME"], expected_home)


if __name__ == "__main__":
    unittest.main()
