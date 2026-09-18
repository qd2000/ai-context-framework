"""Regression coverage for `acf worktree retire`.

Retirement is the narrow, evidence-bound path for a registered worktree whose branch must
stay intentionally non-mergeable after its required commits are preserved elsewhere. It
never deletes a branch or Git ref; `acf worktree close` keeps its own merged-only contract.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path

import acf

from ai_context_framework.git_support import git_common_dir, operations_dir, read_registry


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


class WorktreeRetireTests(unittest.TestCase):
    def setUp(self):
        self._acf_home = tempfile.TemporaryDirectory()
        self._old_acf_home = os.environ.get("ACF_HOME")
        os.environ["ACF_HOME"] = self._acf_home.name
        self._roots: list[tempfile.TemporaryDirectory[str]] = []

    def tearDown(self):
        if self._old_acf_home is None:
            os.environ.pop("ACF_HOME", None)
        else:
            os.environ["ACF_HOME"] = self._old_acf_home
        self._acf_home.cleanup()
        for root in reversed(self._roots):
            root.cleanup()

    def run_cli(self, args: list[str], *, cwd: Path | None = None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        context = nullcontext() if cwd is None else pushd(cwd)
        with context, redirect_stdout(stdout), redirect_stderr(stderr):
            code = acf.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def json_cli(self, args: list[str], *, cwd: Path | None = None):
        if "--json" not in args:
            args = [*args, "--json"]
        code, stdout, stderr = self.run_cli(args, cwd=cwd)
        payload = json.loads(stdout) if stdout.strip() else {}
        return code, payload, stderr

    def make_repo(self, name: str = "repo"):
        root = tempfile.TemporaryDirectory()
        self._roots.append(root)
        root_path = Path(root.name)
        repo = root_path / name
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "ACF Test")
        git(repo, "config", "user.email", "acf-test@example.invalid")
        context = repo / "docs" / "ai"
        self.assertEqual(self.run_cli(["init", str(context), "--profile", "standard"])[0], 0)
        self.assertEqual(self.run_cli(["workstream", "init", str(context)])[0], 0)
        git(repo, "add", "--all")
        git(repo, "commit", "-m", "initial context")
        self.assert_authorization_policy(context, decision="auto")
        return root_path, repo, context

    def assert_authorization_policy(self, context: Path, *, decision: str):
        args = [
            "workstream",
            "authorization",
            "policy-set",
            str(context),
            "--decision",
            decision,
            "--action",
            "ready",
            "--action",
            "merge",
            "--action",
            "done",
            "--action",
            "archive",
            "--actor",
            "human-owner",
            "--authority-source",
            "user-authority:test-fixture",
            "--evidence-ref",
            f"test-evidence:worktree-{decision}",
        ]
        self.assertEqual(self.run_cli(args)[0], 0)

    def reserve(self, context: Path, *, slug: str = "retire-task"):
        code, payload, stderr = self.json_cli(
            [
                "workstream",
                "reserve",
                str(context),
                "--title",
                "Retire feature",
                "--slug",
                slug,
                "--owner",
                "codex",
                "--goal",
                "Implement feature.",
                "--output",
                "Feature output.",
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["status"], "reserved")
        return payload

    def create_ws_worktree(self, context: Path, workstream_id: str):
        code, payload, stderr = self.json_cli(
            ["worktree", "create", str(context), "--workstream", workstream_id, "--apply"]
        )
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["ok"])
        return payload

    def unmerged_registered_worktree(self, *, slug: str = "retire-task"):
        """Registered worktree whose branch holds a commit that never reaches main."""

        _root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug=slug)
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        (target / "feature.txt").write_text("feature", encoding="utf-8")
        git(target, "add", "feature.txt")
        git(target, "commit", "-m", "feature not merged")
        return repo, context, reserved["id"], target

    def retire_args(
        self,
        context: Path,
        workstream_id: str,
        *,
        apply: bool = False,
        disposition: str | None = "curated_handoff",
        evidence_ref: str | None = "worklog:daily/2026-09-18 curated handoff",
    ):
        args = ["worktree", "retire", str(context), "--workstream", workstream_id]
        if disposition is not None:
            args += ["--disposition", disposition]
        if evidence_ref is not None:
            args += ["--evidence-ref", evidence_ref]
        args += ["--preserve-branch"]
        if apply:
            args += ["--apply"]
        return args

    def test_retire_removes_worktree_and_registry_but_preserves_branch(self):
        repo, context, workstream_id, target = self.unmerged_registered_worktree()

        code, plan, stderr = self.json_cli(self.retire_args(context, workstream_id))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(plan["status"], "ready_to_retire")
        self.assertFalse(plan["applied"])
        self.assertTrue(plan["preserved_branch"])
        self.assertEqual(plan["disposition"], "curated_handoff")
        self.assertEqual(plan["evidence_ref"], "worklog:daily/2026-09-18 curated handoff")
        self.assertTrue(target.exists())

        code, result, stderr = self.json_cli(self.retire_args(context, workstream_id, apply=True))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(result["status"], "retired")
        self.assertTrue(result["applied"])
        self.assertFalse(target.exists())
        self.assertTrue(result["branch_cleanup"]["preserved"])
        self.assertIsNone(read_registry(git_common_dir(repo), workstream_id))

        branch_probe = git(
            repo,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{result['target']['branch']}",
            check=False,
        )
        self.assertEqual(branch_probe.returncode, 0)

        code, listing, _stderr = self.json_cli(["worktree", "list", str(context)])
        self.assertEqual(code, 0)
        self.assertNotIn(
            str(target),
            [row["path"] for row in listing["worktrees"]],
        )

    def test_retire_apply_is_idempotent_after_completion(self):
        _repo, context, workstream_id, target = self.unmerged_registered_worktree()
        code, _result, stderr = self.json_cli(
            self.retire_args(context, workstream_id, apply=True)
        )
        self.assertEqual(code, 0, stderr)
        self.assertFalse(target.exists())

        code, again, stderr = self.json_cli(
            self.retire_args(context, workstream_id, apply=True)
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(again["status"], "already_retired")
        self.assertFalse(again["worktree_registered"])

    def test_retire_requires_evidence_ref(self):
        _repo, context, workstream_id, _target = self.unmerged_registered_worktree()
        code, payload, _stderr = self.json_cli(
            self.retire_args(context, workstream_id, evidence_ref=None)
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "worktree_retire_evidence_required")
        self.assertTrue(payload["next_actions"])

    def test_retire_rejects_blank_evidence_ref(self):
        _repo, context, workstream_id, _target = self.unmerged_registered_worktree()
        code, payload, _stderr = self.json_cli(
            self.retire_args(context, workstream_id, evidence_ref="   ")
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "worktree_retire_evidence_required")

    def test_retire_rejects_unsupported_disposition(self):
        _repo, context, workstream_id, _target = self.unmerged_registered_worktree()
        code, payload, _stderr = self.json_cli(
            self.retire_args(context, workstream_id, disposition="abandon")
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "worktree_retire_disposition_unsupported")

    def test_retire_rejects_merged_branch_and_points_to_close(self):
        repo, context, workstream_id, target = self.unmerged_registered_worktree()
        branch = self.json_cli(self.retire_args(context, workstream_id))[1]["target"]["branch"]
        git(repo, "merge", "--ff-only", branch)

        code, payload, _stderr = self.json_cli(self.retire_args(context, workstream_id))
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "worktree_retire_branch_already_merged")
        self.assertIn("worktree close", payload["next_actions"][0])
        self.assertTrue(target.exists())

    def test_retire_rejects_dirty_worktree(self):
        _repo, context, workstream_id, target = self.unmerged_registered_worktree()
        (target / "dirty.txt").write_text("dirty", encoding="utf-8")
        code, payload, _stderr = self.json_cli(self.retire_args(context, workstream_id))
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "worktree_dirty")

    def test_retire_rejects_unregistered_worktree(self):
        root_path, repo, context = self.make_repo()
        unregistered = root_path / "unregistered"
        git(repo, "worktree", "add", "-b", "codex/unregistered-retire", str(unregistered), "main")
        code, payload, _stderr = self.json_cli(
            [
                "worktree",
                "retire",
                str(context),
                "--target",
                str(unregistered),
                "--disposition",
                "curated_handoff",
                "--evidence-ref",
                "worklog:daily/2026-09-18 curated handoff",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "worktree_not_registered")
        self.assertTrue(unregistered.exists())

    def test_retire_is_blocked_by_deny_authorization_policy(self):
        _repo, context, workstream_id, target = self.unmerged_registered_worktree()
        self.assert_authorization_policy(context, decision="deny")
        code, payload, _stderr = self.json_cli(
            self.retire_args(context, workstream_id, apply=True)
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "workstream_closeout_denied")
        self.assertTrue(target.exists())

    def test_retire_apply_records_journal_evidence(self):
        repo, context, workstream_id, _target = self.unmerged_registered_worktree()
        code, result, stderr = self.json_cli(
            self.retire_args(context, workstream_id, apply=True)
        )
        self.assertEqual(code, 0, stderr)
        operation_id = result["operation_id"]
        self.assertTrue(operation_id.startswith("worktree.retire-"))
        journal = json.loads(
            (operations_dir(git_common_dir(repo)) / f"{operation_id}.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(journal["command"], "worktree.retire")
        self.assertEqual(journal["status"], "completed")
        self.assertEqual(journal["disposition"], "curated_handoff")
        self.assertTrue(journal["preserved_branch"])
        self.assertEqual(
            journal["retire_snapshot"]["branch"], result["target"]["branch"]
        )
        self.assertIsNotNone(journal["retire_snapshot"]["branch_head"])
        self.assertEqual(journal["steps"]["worktree_removed"]["state"], "completed")
        self.assertEqual(journal["steps"]["branch_preserved"]["state"], "completed")

    def test_close_keeps_its_merged_only_contract(self):
        _repo, context, workstream_id, target = self.unmerged_registered_worktree(
            slug="close-still-gated"
        )
        code, payload, _stderr = self.json_cli(
            ["worktree", "close", str(context), "--workstream", workstream_id]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "branch_not_merged")
        self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
