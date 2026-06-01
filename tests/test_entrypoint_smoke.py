import pathlib
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from ai_context_framework import cli


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

    def test_package_cli_main_executes_help(self):
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.main(["--help"])

        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertIn("usage:", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
