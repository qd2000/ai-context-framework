import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class EntrypointSmokeTests(unittest.TestCase):
    def run_acf_py(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "acf.py"), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def assert_help_success(self, *args):
        completed = self.run_acf_py(*args)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("usage:", completed.stdout)
        self.assertEqual(completed.stderr, "")

    def test_top_level_help_succeeds_from_acf_py(self):
        self.assert_help_success("--help")

    def test_check_help_succeeds_from_acf_py(self):
        self.assert_help_success("check", "--help")

    def test_workstream_help_succeeds_from_acf_py(self):
        self.assert_help_success("workstream", "--help")


if __name__ == "__main__":
    unittest.main()
