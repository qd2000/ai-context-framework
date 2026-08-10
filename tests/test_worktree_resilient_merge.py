from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from unittest.mock import patch
from pathlib import Path

import acf
from ai_context_framework.git_support import GitCommandResult, discover_git_project
from ai_context_framework.worktree_merge_contracts import MergeRetryPolicy
from ai_context_framework.worktree_service import (
    _close_remove_worktree_with_retry,
    target_from_registry,
)


@contextmanager
def pushd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


class ResilientMergeCliTests(unittest.TestCase):
    def setUp(self):
        self._acf_home = tempfile.TemporaryDirectory()
        self._old_acf_home = os.environ.get("ACF_HOME")
        os.environ["ACF_HOME"] = self._acf_home.name
        self._root = tempfile.TemporaryDirectory()
        root = Path(self._root.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "ACF Test")
        git(self.repo, "config", "user.email", "acf-test@example.invalid")
        git(self.repo, "config", "core.autocrlf", "false")
        self.context = self.repo / "docs" / "ai"
        self.assertEqual(self.run_cli(["init", str(self.context)])[0], 0)
        self.assertEqual(self.run_cli(["workstream", "init", str(self.context)])[0], 0)
        (self.repo / ".gitignore").write_text("output/\n", encoding="utf-8")
        git(self.repo, "add", "--all")
        git(self.repo, "commit", "-m", "initial")
        self.reserved = self.reserve()
        self.created = self.create_worktree()
        self.target = Path(self.created["target"]["path"])

    def tearDown(self):
        if self._old_acf_home is None:
            os.environ.pop("ACF_HOME", None)
        else:
            os.environ["ACF_HOME"] = self._old_acf_home
        self._acf_home.cleanup()
        self._root.cleanup()

    def run_cli(self, args: list[str], *, cwd: Path | None = None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        context = pushd(cwd) if cwd is not None else pushd(self.repo)
        with context, redirect_stdout(stdout), redirect_stderr(stderr):
            code = acf.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def json_cli(self, args: list[str], *, cwd: Path | None = None):
        if "--json" not in args:
            args = [*args, "--json"]
        code, stdout, stderr = self.run_cli(args, cwd=cwd)
        return code, json.loads(stdout) if stdout.strip() else {}, stderr

    def reserve(self):
        code, payload, stderr = self.json_cli(
            [
                "workstream",
                "reserve",
                str(self.context),
                "--title",
                "Resilient merge",
                "--slug",
                "resilient-merge",
                "--owner",
                "codex",
                "--goal",
                "Test resilient merge.",
                "--output",
                "Merged output.",
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        return payload

    def create_worktree(self):
        code, payload, stderr = self.json_cli(
            [
                "worktree",
                "create",
                str(self.context),
                "--workstream",
                self.reserved["id"],
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        return payload

    def commit_source(self, path: str, content: str):
        target = self.target / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        git(self.target, "add", "--all")
        git(self.target, "commit", "-m", f"source {path}")

    def mark_ready(self):
        target_context = self.target / "docs" / "ai"
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "set",
                    self.reserved["id"],
                    str(target_context),
                    "--status",
                    "Active",
                ]
            )[0],
            0,
        )
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "merge-request",
                    self.reserved["id"],
                    str(target_context),
                    "--target",
                    "main",
                    "--summary",
                    "Merge resilient branch.",
                    "--verification",
                    "Tests passed.",
                ]
            )[0],
            0,
        )
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "ready",
                    self.reserved["id"],
                    str(target_context),
                    "--human-approved",
                ]
            )[0],
            0,
        )
        git(self.target, "add", "--all")
        git(self.target, "commit", "-m", "ready")

    def merge(self, extra: list[str] | None = None):
        return self.json_cli(
            [
                "worktree",
                "merge",
                str(self.context),
                "--workstream",
                self.reserved["id"],
                *(extra or []),
                "--apply",
            ]
        )

    def test_require_clean_policy_uses_same_engine_but_rejects_dirty_primary(self):
        self.commit_source("feature.txt", "feature\n")
        self.mark_ready()
        config = self.repo / ".acf" / "project.toml"
        config.parent.mkdir(exist_ok=True)
        config.write_text(
            "[git]\n"
            f'primary_checkout = "{self.repo.as_posix()}"\n'
            'primary_branch = "main"\n'
            'primary_dirty_policy = "require_clean"\n',
            encoding="utf-8",
        )
        git(self.repo, "add", ".acf/project.toml")
        git(self.repo, "commit", "-m", "strict primary policy")
        (self.repo / "local.txt").write_text("local\n", encoding="utf-8")
        code, payload, _stderr = self.json_cli(
            [
                "worktree",
                "merge-plan",
                str(self.context),
                "--workstream",
                self.reserved["id"],
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "primary_checkout_dirty")

    def test_non_overlapping_staged_and_unstaged_primary_are_preserved(self):
        self.commit_source("feature.txt", "feature\n")
        self.mark_ready()
        (self.repo / "staged.txt").write_text("staged\n", encoding="utf-8")
        git(self.repo, "add", "staged.txt")
        (self.repo / "unstaged.txt").write_text("unstaged\n", encoding="utf-8")
        code, payload, stderr = self.merge()
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["status"], "merged")
        self.assertTrue((self.repo / "feature.txt").is_file())
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only").stdout.strip(), "staged.txt")
        self.assertTrue((self.repo / "unstaged.txt").is_file())
        self.assertEqual((self.repo / "unstaged.txt").read_text(encoding="utf-8"), "unstaged\n")

    def test_identical_untracked_overlap_becomes_clean_after_promotion(self):
        self.commit_source("same.txt", "same\n")
        self.mark_ready()
        (self.repo / "same.txt").write_text("same\n", encoding="utf-8")
        code, payload, stderr = self.merge()
        self.assertEqual(code, 0, (stderr, payload))
        self.assertEqual(payload["collisions"]["identical_overlap_paths"], ["same.txt"])
        self.assertNotIn("same.txt", git(self.repo, "status", "--porcelain").stdout)

    def test_divergent_overlap_pauses_without_changing_main(self):
        self.commit_source("same.txt", "candidate\n")
        self.mark_ready()
        before = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        (self.repo / "same.txt").write_text("local\n", encoding="utf-8")
        code, payload, _stderr = self.merge(["--wait-timeout", "0"])
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["status"], "paused_retryable")
        self.assertEqual(payload["pause_reason"], "primary_path_collision")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").stdout.strip(), before)
        self.assertTrue(Path(payload["target"]["path"]).is_dir())

    def test_conflict_is_resolved_in_integration_then_resumed(self):
        (self.repo / "shared.txt").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", "shared.txt")
        git(self.repo, "commit", "-m", "shared base")
        git(self.target, "merge", "main")
        self.commit_source("shared.txt", "source\n")
        self.mark_ready()
        (self.repo / "shared.txt").write_text("primary\n", encoding="utf-8")
        git(self.repo, "add", "shared.txt")
        git(self.repo, "commit", "-m", "primary shared")
        before = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        code, payload, _stderr = self.merge()
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["status"], "conflict_resolution_required")
        integration = Path(payload["integration_path"])
        self.assertTrue(integration.is_dir())
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").stdout.strip(), before)
        (integration / "shared.txt").write_text("resolved\n", encoding="utf-8")
        git(integration, "add", "shared.txt")
        git(integration, "commit", "-m", "resolve conflict")
        code, resumed, stderr = self.json_cli(
            [
                "worktree",
                "resume",
                payload["operation_id"],
                str(self.context),
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(resumed["status"], "merged")
        self.assertEqual((self.repo / "shared.txt").read_text(encoding="utf-8"), "resolved\n")

    def test_unknown_ignored_artifact_can_be_classified_migrated_and_resumed(self):
        self.commit_source("feature.txt", "feature\n")
        output = self.target / "output" / "result.ksc"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"important")
        self.mark_ready()
        before = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        code, payload, _stderr = self.merge()
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["status"], "artifact_handoff_required")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").stdout.strip(), before)
        destination = Path(self._root.name) / "artifacts" / "result.ksc"
        code, plan, stderr = self.json_cli(
            [
                "worktree",
                "artifact-plan",
                str(self.context),
                "--workstream",
                self.reserved["id"],
                "--required",
                f"output/result.ksc={destination}",
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(plan["manifest"]["entries"][0]["classification"], "required")
        code, migrated, stderr = self.json_cli(
            [
                "worktree",
                "artifact-migrate",
                str(self.context),
                "--workstream",
                self.reserved["id"],
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertTrue(migrated["promotion_ready"])
        code, resumed, stderr = self.json_cli(
            [
                "worktree",
                "resume",
                payload["operation_id"],
                str(self.context),
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(resumed["status"], "merged")
        self.assertEqual(destination.read_bytes(), b"important")

    def test_transient_primary_collision_is_retried_until_path_clears(self):
        self.commit_source("same.txt", "candidate\n")
        self.mark_ready()
        local = self.repo / "same.txt"
        local.write_text("temporary-local\n", encoding="utf-8")

        def clear_path():
            time.sleep(0.15)
            local.unlink()

        thread = threading.Thread(target=clear_path)
        thread.start()
        try:
            code, payload, stderr = self.merge(
                [
                    "--wait-timeout",
                    "3",
                    "--initial-delay",
                    "0.02",
                    "--max-delay",
                    "0.05",
                    "--jitter-ratio",
                    "0",
                ]
            )
        finally:
            thread.join()
        self.assertEqual(code, 0, (stderr, payload))
        self.assertEqual(payload["status"], "merged")
        self.assertEqual((self.repo / "same.txt").read_text(encoding="utf-8"), "candidate\n")

    def test_primary_advance_during_post_check_automatically_replans(self):
        self.commit_source("feature.txt", "feature\n")
        self.mark_ready()
        marker = Path(self._root.name) / "advance-once.marker"
        script = (
            "from pathlib import Path; import subprocess; "
            f"m=Path({str(marker)!r}); "
            f"repo={str(self.repo)!r}; "
            "(m.exists() or (m.write_text('1'), subprocess.run(['git','-C',repo,'commit','--allow-empty','-m','concurrent primary'],check=True)))"
        )
        check = json.dumps(["python", "-c", script])
        code, payload, stderr = self.merge(["--post-check-json", check])
        self.assertEqual(code, 0, (stderr, payload))
        self.assertEqual(payload["status"], "merged")
        journal = json.loads(
            (self.repo / ".git" / "acf" / "operations" / f"{payload['operation_id']}.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertGreaterEqual(journal["attempts"]["replans"], 1)
        self.assertTrue((self.repo / "feature.txt").is_file())

    def test_source_advance_during_pre_check_is_revalidated_and_merged(self):
        self.commit_source("feature.txt", "feature\n")
        self.mark_ready()
        marker = Path(self._root.name) / "source-advance-once.marker"
        script = (
            "from pathlib import Path; import subprocess; "
            f"m=Path({str(marker)!r}); "
            "cwd=Path.cwd(); "
            "(m.exists() or (m.write_text('1'), (cwd/'late.txt').write_text('late\\n'), "
            "subprocess.run(['git','add','late.txt'],check=True), "
            "subprocess.run(['git','commit','-m','late source'],check=True)))"
        )
        check = json.dumps(["python", "-c", script])
        code, payload, stderr = self.merge(["--pre-check-json", check])
        self.assertEqual(code, 0, (stderr, payload))
        self.assertEqual(payload["status"], "merged")
        self.assertTrue((self.repo / "late.txt").is_file())

    def test_primary_promotion_lock_is_waited_and_then_acquired(self):
        self.commit_source("feature.txt", "feature\n")
        self.mark_ready()
        lock = self.repo / ".git" / "acf" / "locks" / "primary-promotion.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(
            json.dumps(
                {
                    "schema_version": "acf.git_lock.v2",
                    "operation_id": "other-operation",
                    "pid": os.getpid(),
                    "hostname": __import__("socket").gethostname(),
                    "created_at": "2026-08-06T00:00:00+00:00",
                    "heartbeat_at": "2026-08-06T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )

        def release_lock():
            time.sleep(0.15)
            lock.unlink()

        thread = threading.Thread(target=release_lock)
        thread.start()
        try:
            code, payload, stderr = self.merge(
                [
                    "--lock-wait-timeout",
                    "3",
                    "--initial-delay",
                    "0.02",
                    "--max-delay",
                    "0.05",
                    "--jitter-ratio",
                    "0",
                ]
            )
        finally:
            thread.join()
        self.assertEqual(code, 0, (stderr, payload))
        self.assertEqual(payload["status"], "merged")

    def test_close_retries_transient_worktree_remove_failure(self):
        self.commit_source("feature.txt", "feature\n")
        self.mark_ready()
        code, payload, stderr = self.merge()
        self.assertEqual(code, 0, (stderr, payload))
        project = discover_git_project(self.context)
        target = target_from_registry(project, workstream_id=self.reserved["id"])
        import ai_context_framework.worktree_service as service

        original = service.run_git
        attempts = {"remove": 0}

        def flaky(cwd, args, *, check=True, env=None):
            if tuple(args[:2]) == ("worktree", "remove") and attempts["remove"] == 0:
                attempts["remove"] += 1
                return GitCommandResult(
                    argv=("git", *tuple(args)),
                    cwd=str(cwd),
                    returncode=1,
                    stdout="",
                    stderr="simulated file handle",
                )
            return original(cwd, args, check=check, env=env)

        with patch("ai_context_framework.worktree_service.run_git", side_effect=flaky):
            result = _close_remove_worktree_with_retry(
                project,
                target,
                timeout_seconds=2,
                policy=MergeRetryPolicy(
                    initial_delay_seconds=0.01,
                    max_delay_seconds=0.01,
                    jitter_ratio=0,
                ),
            )
        self.assertTrue(result["removed"])
        self.assertEqual(result["attempts"], 2)

    def test_close_partial_success_resumes_same_operation(self):
        self.commit_source("feature.txt", "feature\n")
        self.mark_ready()
        code, payload, stderr = self.merge()
        self.assertEqual(code, 0, (stderr, payload))
        import ai_context_framework.worktree_service as service

        original = service.run_git

        def fail_branch_delete(cwd, args, *, check=True, env=None):
            if tuple(args[:2]) == ("branch", "-d"):
                return GitCommandResult(
                    argv=("git", *tuple(args)),
                    cwd=str(cwd),
                    returncode=1,
                    stdout="",
                    stderr="simulated branch lock",
                )
            return original(cwd, args, check=check, env=env)

        with patch("ai_context_framework.worktree_service.run_git", side_effect=fail_branch_delete):
            code, failed, _stderr = self.json_cli(
                [
                    "worktree",
                    "close",
                    str(self.context),
                    "--workstream",
                    self.reserved["id"],
                    "--wait-timeout",
                    "0",
                    "--operation-id",
                    "close-partial",
                    "--apply",
                ]
            )
        self.assertNotEqual(code, 0)
        self.assertFalse(self.target.exists())
        self.assertTrue(git(self.repo, "branch", "--list", "codex/ws001-resilient-merge").stdout.strip())
        code, resumed, stderr = self.json_cli(
            [
                "worktree",
                "resume",
                "close-partial",
                str(self.context),
                "--apply",
            ]
        )
        self.assertEqual(code, 0, (stderr, resumed))
        self.assertEqual(resumed["status"], "closed")
        journal = json.loads(
            (self.repo / ".git" / "acf" / "operations" / "close-partial.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(journal["status"], "completed")
        self.assertIn("worktree_removed", journal["steps"])
        self.assertIn("branch_deleted", journal["steps"])
        self.assertFalse(git(self.repo, "branch", "--list", "codex/ws001-resilient-merge").stdout.strip())

    def test_post_check_fix_commit_is_used_on_resume(self):
        self.commit_source("health.txt", "bad\n")
        self.mark_ready()
        check = json.dumps(
            [
                "python",
                "-c",
                "from pathlib import Path; import sys; sys.exit(0 if Path('health.txt').read_text().strip() == 'good' else 4)",
            ]
        )
        before = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        code, payload, _stderr = self.merge(["--post-check-json", check])
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["status"], "candidate_checks_failed")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").stdout.strip(), before)
        integration = Path(payload["integration_path"])
        (integration / "health.txt").write_text("good\n", encoding="utf-8")
        git(integration, "add", "health.txt")
        git(integration, "commit", "-m", "fix candidate")
        code, resumed, stderr = self.json_cli(
            [
                "worktree",
                "resume",
                payload["operation_id"],
                str(self.context),
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(resumed["status"], "merged")
        self.assertEqual((self.repo / "health.txt").read_text(encoding="utf-8"), "good\n")


if __name__ == "__main__":
    unittest.main()
