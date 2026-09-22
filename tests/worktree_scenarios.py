"""Reusable temporary Git repositories for worktree merge tests."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

from tests.windows_teardown import cleanup_temporary_directory


def run_git(
    cwd: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


class TemporaryWorktreeScenario:
    """Create an isolated primary repository plus source/integration worktrees."""

    def __init__(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.primary = self.root / "repo"
        self.worktree_root = self.root / "repo_worktrees"
        self.source = self.worktree_root / "source"
        self.integration = self.worktree_root / "integration"
        self.source_branch = "codex/ws001-scenario"
        self.integration_branch = "acf/integration/WS001/scenario"
        self._closed = False

        self.primary.mkdir()
        self.worktree_root.mkdir()
        run_git(self.primary, "init", "-b", "main")
        run_git(self.primary, "config", "user.name", "ACF Scenario")
        run_git(self.primary, "config", "user.email", "acf-scenario@example.invalid")
        run_git(self.primary, "config", "core.autocrlf", "false")
        self.write(self.primary, ".gitignore", "output/\n")
        self.write(self.primary, "base.txt", "base\n")
        run_git(self.primary, "add", "--all")
        run_git(self.primary, "commit", "-m", "initial")

    def __enter__(self) -> "TemporaryWorktreeScenario":
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Windows releases the handles of the `git` processes used to build the
        # scenario asynchronously, so removal needs a bounded retry budget.
        cleanup_temporary_directory(self._temporary)

    @staticmethod
    def write(root: Path, relative_path: str, content: str | bytes) -> Path:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def head(root: Path, ref: str = "HEAD") -> str:
        return run_git(root, "rev-parse", ref).stdout.strip()

    @staticmethod
    def status(root: Path) -> list[str]:
        output = run_git(
            root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ).stdout
        return [line for line in output.splitlines() if line]

    @staticmethod
    def ignored_paths(root: Path) -> list[str]:
        output = run_git(
            root,
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
        ).stdout
        return [line.replace("\\", "/") for line in output.splitlines() if line]

    def add_source_worktree(self) -> Path:
        run_git(
            self.primary,
            "worktree",
            "add",
            "-b",
            self.source_branch,
            str(self.source),
            "main",
        )
        return self.source

    def commit_source_files(
        self,
        files: Iterable[tuple[str, str | bytes]],
        *,
        message: str = "source change",
    ) -> str:
        if not self.source.exists():
            self.add_source_worktree()
        for relative_path, content in files:
            self.write(self.source, relative_path, content)
        run_git(self.source, "add", "--all")
        run_git(self.source, "commit", "-m", message)
        return self.head(self.source)

    def add_integration_worktree(self, *, base_ref: str = "main") -> Path:
        run_git(
            self.primary,
            "worktree",
            "add",
            "-b",
            self.integration_branch,
            str(self.integration),
            base_ref,
        )
        return self.integration

    def merge_source_in_integration(self, *, message: str = "merge source") -> str:
        if not self.integration.exists():
            self.add_integration_worktree()
        run_git(
            self.integration,
            "merge",
            "--no-ff",
            self.source_branch,
            "-m",
            message,
        )
        return self.head(self.integration)
