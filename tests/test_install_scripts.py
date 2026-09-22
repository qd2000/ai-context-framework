from __future__ import annotations

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.windows_teardown import cleanup_temporary_directory, temporary_root


ROOT = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = ROOT / "scripts" / "update_acf.ps1"
INSTALL_SCRIPT = ROOT / "scripts" / "install_acf.ps1"


@unittest.skipUnless(os.name == "nt", "PowerShell uv-tool process-lock tests are Windows-specific")
class InstallScriptTests(unittest.TestCase):
    def _fake_uv_environment(self, root: Path) -> tuple[dict[str, str], Path, Path]:
        # Hosted Windows runners expose TEMP as `C:\Users\RUNNER~1\...` while the install
        # scripts resolve the canonical `C:\Users\runneradmin\...` form. Use the canonical
        # root so the generated acf.cmd path is compared against the same representation.
        root = Path(root).resolve()
        fake_bin = root / "fake-bin"
        fake_bin.mkdir(parents=True)
        tool_dir = root / "tools"
        tool_bin = root / "tool-bin"
        tool_dir.mkdir()
        tool_bin.mkdir()
        log_path = root / "uv.log"

        scripts_dir = tool_dir / "ai-context-framework" / "Scripts"
        scripts_dir.mkdir(parents=True)
        fake_python = scripts_dir / "python.cmd"
        fake_python.write_text(
            "@echo off\r\n"
            "echo %*>>\"%FAKE_PYTHON_LOG%\"\r\n"
            "if \"%1\"==\"-I\" if \"%2\"==\"-m\" if \"%3\"==\"acf\" if \"%4\"==\"--version\" (echo acf vFAKE& exit /b 0)\r\n"
            "exit /b 0\r\n",
            encoding="utf-8",
        )
        (tool_bin / "acf.exe").write_bytes(b"fake uv console launcher")

        uv_cmd = fake_bin / "uv.cmd"
        uv_cmd.write_text(
            "@echo off\r\n"
            "if \"%1\"==\"tool\" if \"%2\"==\"dir\" if \"%3\"==\"--bin\" (echo %FAKE_UV_TOOL_BIN%& exit /b 0)\r\n"
            "if \"%1\"==\"tool\" if \"%2\"==\"dir\" (echo %FAKE_UV_TOOL_DIR%& exit /b 0)\r\n"
            "echo %*>>\"%FAKE_UV_LOG%\"\r\n"
            "exit /b 0\r\n",
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}{os.pathsep}{tool_bin}{os.pathsep}{env.get('PATH', '')}"
        env["FAKE_UV_TOOL_DIR"] = str(tool_dir)
        env["FAKE_UV_TOOL_BIN"] = str(tool_bin)
        env["FAKE_UV_LOG"] = str(log_path)
        env["FAKE_PYTHON_LOG"] = str(root / "python.log")
        return env, log_path, tool_dir

    def _run_script(self, script: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["pwsh", "-NoLogo", "-NoProfile", "-File", str(script), *args],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )

    def test_update_uses_unpinned_force_upgrade_install(self) -> None:
        with temporary_root(prefix="acf-update-") as raw:
            env, log_path, _tool_dir = self._fake_uv_environment(Path(raw))
            result = self._run_script(UPDATE_SCRIPT, env)
            self.assertEqual(result.returncode, 0, result.stdout)
            log = log_path.read_text(encoding="utf-8")
            self.assertIn("tool install --force --upgrade ai-context-framework", log)
            self.assertNotIn("tool upgrade ai-context-framework", log)
            self.assertIn("tool update-shell", log)

    def test_update_reinstall_preserves_latest_discovery(self) -> None:
        with temporary_root(prefix="acf-update-reinstall-") as raw:
            env, log_path, _tool_dir = self._fake_uv_environment(Path(raw))
            result = self._run_script(UPDATE_SCRIPT, env, "-Reinstall")
            self.assertEqual(result.returncode, 0, result.stdout)
            log = log_path.read_text(encoding="utf-8")
            self.assertIn("tool install --force --upgrade --reinstall ai-context-framework", log)

    def test_install_and_update_replace_uv_exe_with_canonical_cmd(self) -> None:
        for script in (INSTALL_SCRIPT, UPDATE_SCRIPT):
            with self.subTest(script=script.name), temporary_root(prefix="acf-canonical-cmd-") as raw:
                root = Path(raw)
                env, _log_path, tool_dir = self._fake_uv_environment(root)
                tool_bin = Path(env["FAKE_UV_TOOL_BIN"])
                result = self._run_script(script, env)
                self.assertEqual(result.returncode, 0, result.stdout)

                acf_cmd = tool_bin / "acf.cmd"
                self.assertTrue(acf_cmd.exists(), result.stdout)
                self.assertFalse((tool_bin / "acf.exe").exists(), result.stdout)
                cmd_text = acf_cmd.read_text(encoding="utf-8")
                self.assertIn("-I -m acf %*", cmd_text)
                expected_python = tool_dir / "ai-context-framework" / "Scripts" / "python.cmd"
                called = re.search(r'call\s+"([^"]+)"', cmd_text)
                self.assertIsNotNone(called, cmd_text)
                self.assertTrue(
                    Path(called.group(1)).samefile(expected_python),
                    f"acf.cmd must call {expected_python}, got {called.group(1)!r}",
                )
                self.assertIn("Canonical Windows ACF command", result.stdout)

                python_log = (root / "python.log").read_text(encoding="utf-8")
                self.assertIn("-I -m acf --version", python_log)

                resolved = subprocess.run(
                    [
                        "pwsh",
                        "-NoLogo",
                        "-NoProfile",
                        "-Command",
                        "(Get-Command acf -CommandType Application -All | Select-Object -First 1).Source",
                    ],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(resolved.returncode, 0, resolved.stdout)
                self.assertTrue(
                    Path(resolved.stdout.strip()).samefile(acf_cmd),
                    f"resolved command {resolved.stdout.strip()!r} is not {acf_cmd}",
                )

    def test_install_and_update_fail_before_uv_mutation_when_tool_process_is_live(self) -> None:
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        source_exe = system_root / "System32" / "ping.exe"
        self.assertTrue(source_exe.exists(), source_exe)

        for script in (INSTALL_SCRIPT, UPDATE_SCRIPT):
            with self.subTest(script=script.name):
                temporary = temporary_root(prefix="acf-live-process-")
                process = None
                try:
                    env, log_path, tool_dir = self._fake_uv_environment(Path(temporary.name))
                    scripts_dir = tool_dir / "ai-context-framework" / "Scripts"
                    scripts_dir.mkdir(parents=True, exist_ok=True)
                    fake_tool_process = scripts_dir / "python.exe"
                    shutil.copy2(source_exe, fake_tool_process)
                    process = subprocess.Popen(
                        [str(fake_tool_process), "127.0.0.1", "-n", "20"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    result = self._run_script(script, env)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("Refusing to mutate the global uv tool", result.stdout)
                    if log_path.exists():
                        mutation_log = log_path.read_text(encoding="utf-8")
                        self.assertNotIn("tool install", mutation_log)
                        self.assertNotIn("tool upgrade", mutation_log)
                finally:
                    # The launched image lives inside the temporary root, so the process
                    # must be confirmed gone before the tree is removed.
                    cleanup_temporary_directory(
                        temporary,
                        processes=() if process is None else (process,),
                    )


if __name__ == "__main__":
    unittest.main()
