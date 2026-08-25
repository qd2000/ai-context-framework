from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = ROOT / "scripts" / "update_acf.ps1"
INSTALL_SCRIPT = ROOT / "scripts" / "install_acf.ps1"


@unittest.skipUnless(os.name == "nt", "PowerShell uv-tool process-lock tests are Windows-specific")
class InstallScriptTests(unittest.TestCase):
    def _fake_uv_environment(self, root: Path) -> tuple[dict[str, str], Path, Path]:
        fake_bin = root / "fake-bin"
        fake_bin.mkdir(parents=True)
        tool_dir = root / "tools"
        tool_bin = root / "tool-bin"
        tool_dir.mkdir()
        tool_bin.mkdir()
        log_path = root / "uv.log"

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
        env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
        env["FAKE_UV_TOOL_DIR"] = str(tool_dir)
        env["FAKE_UV_TOOL_BIN"] = str(tool_bin)
        env["FAKE_UV_LOG"] = str(log_path)
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
        with tempfile.TemporaryDirectory() as raw:
            env, log_path, _tool_dir = self._fake_uv_environment(Path(raw))
            result = self._run_script(UPDATE_SCRIPT, env)
            self.assertEqual(result.returncode, 0, result.stdout)
            log = log_path.read_text(encoding="utf-8")
            self.assertIn("tool install --force --upgrade ai-context-framework", log)
            self.assertNotIn("tool upgrade ai-context-framework", log)
            self.assertIn("tool update-shell", log)

    def test_update_reinstall_preserves_latest_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            env, log_path, _tool_dir = self._fake_uv_environment(Path(raw))
            result = self._run_script(UPDATE_SCRIPT, env, "-Reinstall")
            self.assertEqual(result.returncode, 0, result.stdout)
            log = log_path.read_text(encoding="utf-8")
            self.assertIn("tool install --force --upgrade --reinstall ai-context-framework", log)

    def test_install_and_update_fail_before_uv_mutation_when_tool_process_is_live(self) -> None:
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        source_exe = system_root / "System32" / "ping.exe"
        self.assertTrue(source_exe.exists(), source_exe)

        for script in (INSTALL_SCRIPT, UPDATE_SCRIPT):
            with self.subTest(script=script.name), tempfile.TemporaryDirectory() as raw:
                env, log_path, tool_dir = self._fake_uv_environment(Path(raw))
                scripts_dir = tool_dir / "ai-context-framework" / "Scripts"
                scripts_dir.mkdir(parents=True)
                fake_tool_process = scripts_dir / "python.exe"
                shutil.copy2(source_exe, fake_tool_process)
                process = subprocess.Popen(
                    [str(fake_tool_process), "127.0.0.1", "-n", "20"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                try:
                    result = self._run_script(script, env)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("Refusing to mutate the global uv tool", result.stdout)
                    if log_path.exists():
                        mutation_log = log_path.read_text(encoding="utf-8")
                        self.assertNotIn("tool install", mutation_log)
                        self.assertNotIn("tool upgrade", mutation_log)
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
