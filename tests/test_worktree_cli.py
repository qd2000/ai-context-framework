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
from ai_context_framework.cli import main as package_cli_main

from ai_context_framework.git_support import (
    acquire_operation_lock,
    discover_git_project,
    git_common_dir,
    list_worktrees,
    load_toml_subset,
    read_registry,
    release_operation_lock,
)
from ai_context_framework.worktree_service import apply_create, resolve_workstream_target


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


class WorktreeCliTests(unittest.TestCase):
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

    def package_json_cli(self, args: list[str], *, cwd: Path | None = None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        context = nullcontext() if cwd is None else pushd(cwd)
        with context, redirect_stdout(stdout), redirect_stderr(stderr):
            code = package_cli_main([*args, "--json"] if "--json" not in args else args)
        payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
        return code, payload, stderr.getvalue()

    def json_cli(self, args: list[str], *, cwd: Path | None = None):
        if "--json" not in args:
            args = [*args, "--json"]
        code, stdout, stderr = self.run_cli(args, cwd=cwd)
        payload = json.loads(stdout) if stdout.strip() else {}
        return code, payload, stderr

    def make_repo(self, name: str = "repo", *, minimal: bool = False):
        root = tempfile.TemporaryDirectory()
        self._roots.append(root)
        root_path = Path(root.name)
        repo = root_path / name
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "ACF Test")
        git(repo, "config", "user.email", "acf-test@example.invalid")
        context = repo / "docs" / "ai"
        profile = "minimal" if minimal else "standard"
        self.assertEqual(self.run_cli(["init", str(context), "--profile", profile])[0], 0)
        self.assertEqual(self.run_cli(["workstream", "init", str(context)])[0], 0)
        git(repo, "add", "--all")
        git(repo, "commit", "-m", "initial context")
        return root_path, repo, context

    def reserve(self, context: Path, *, title: str = "Feature", slug: str = "feature-task"):
        code, payload, stderr = self.json_cli(
            [
                "workstream",
                "reserve",
                str(context),
                "--title",
                title,
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
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "reserved")
        return payload

    def create_ws_worktree(self, context: Path, workstream_id: str):
        code, payload, stderr = self.json_cli(
            [
                "worktree",
                "create",
                str(context),
                "--workstream",
                workstream_id,
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["ok"])
        return payload

    def mark_ready_in_worktree(self, worktree: Path, workstream_id: str):
        context = worktree / "docs" / "ai"
        self.assertEqual(
            self.run_cli(
                ["workstream", "set", workstream_id, str(context), "--status", "Active"]
            )[0],
            0,
        )
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "merge-request",
                    workstream_id,
                    str(context),
                    "--target",
                    "main",
                    "--summary",
                    "Merge feature branch.",
                    "--verification",
                    "Temporary repository checks passed.",
                ]
            )[0],
            0,
        )
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "ready",
                    workstream_id,
                    str(context),
                    "--human-approved",
                ]
            )[0],
            0,
        )
        git(worktree, "add", "--all")
        git(worktree, "commit", "-m", "mark workstream ready")

    def test_installed_package_entrypoint_can_reserve_and_create(self):
        _root, _repo, context = self.make_repo()
        code, reserved, stderr = self.package_json_cli(
            [
                "workstream",
                "reserve",
                str(context),
                "--title",
                "Package entry",
                "--slug",
                "package-entry",
                "--owner",
                "codex",
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(reserved["status"], "reserved")
        code, created, stderr = self.package_json_cli(
            [
                "worktree",
                "create",
                str(context),
                "--workstream",
                reserved["id"],
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(created["status"], "created")

    def test_existing_workstream_add_needs_no_git_or_worktree_config(self):
        root = tempfile.TemporaryDirectory()
        self._roots.append(root)
        context = Path(root.name) / "docs" / "ai"
        self.assertEqual(self.run_cli(["init", str(context), "--profile", "minimal"])[0], 0)
        self.assertEqual(self.run_cli(["workstream", "init", str(context)])[0], 0)
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "add",
                    str(context),
                    "--id",
                    "WS001",
                    "--title",
                    "No Git",
                    "--owner",
                    "codex",
                ]
            )[0],
            0,
        )
        self.assertTrue((context / "active" / "workstreams" / "WS001.md").is_file())
        self.assertFalse((Path(root.name) / ".git").exists())

    def test_reserve_plan_has_no_side_effects_and_no_worktree(self):
        _root, repo, context = self.make_repo()
        before = git(repo, "rev-parse", "HEAD").stdout.strip()
        code, payload, stderr = self.json_cli(
            [
                "workstream",
                "reserve",
                str(context),
                "--title",
                "Plan only",
                "--slug",
                "plan-only",
                "--owner",
                "codex",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["status"], "reservation_planned")
        self.assertFalse(payload["applied"])
        self.assertEqual(git(repo, "rev-parse", "HEAD").stdout.strip(), before)
        self.assertFalse((context / "active" / "workstreams" / "WS001.md").exists())
        self.assertEqual(len(list_worktrees(repo)), 1)

    def test_reserve_apply_commits_only_detail_and_index_and_not_worktree(self):
        _root, repo, context = self.make_repo()
        payload = self.reserve(context, slug="reserved-task")
        workstream_id = payload["id"]
        self.assertEqual(workstream_id, "WS001")
        detail = context / "active" / "workstreams" / "WS001.md"
        text = detail.read_text(encoding="utf-8")
        self.assertIn("## Workspace", text)
        self.assertIn("- slug: reserved-task", text)
        self.assertIn("- mode: none", text)
        changed = git(repo, "show", "--format=", "--name-only", "HEAD").stdout.splitlines()
        self.assertEqual(
            sorted(line for line in changed if line),
            [
                "docs/ai/active/Workstreams.md",
                "docs/ai/active/workstreams/WS001.md",
            ],
        )
        self.assertEqual(len(list_worktrees(repo)), 1)
        self.assertFalse(git(repo, "branch", "--list", "codex/ws001-reserved-task").stdout.strip())

    def test_reserve_shared_scope_supplies_serial_merge_contract(self):
        _root, _repo, context = self.make_repo()
        code, payload, stderr = self.json_cli(
            [
                "workstream",
                "reserve",
                str(context),
                "--title",
                "Shared",
                "--slug",
                "shared-task",
                "--owner",
                "codex",
                "--write-scope",
                "shared: README.md",
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        detail = context / "active" / "workstreams" / f"{payload['id']}.md"
        text = detail.read_text(encoding="utf-8")
        self.assertIn(f"merge_owner: {payload['id']}", text)
        self.assertIn("coordination: serial", text)

    def test_reserve_dirty_primary_is_refused_without_staging(self):
        _root, repo, context = self.make_repo()
        (repo / "dirty.txt").write_text("dirty", encoding="utf-8")
        code, payload, _stderr = self.json_cli(
            [
                "workstream",
                "reserve",
                str(context),
                "--title",
                "Dirty",
                "--slug",
                "dirty-task",
                "--owner",
                "codex",
                "--apply",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "primary_checkout_dirty")
        self.assertFalse(git(repo, "diff", "--cached", "--name-only").stdout.strip())

    def test_reserve_uses_next_id_across_archive_and_branch_refs(self):
        _root, repo, context = self.make_repo()
        archive = context / "archive" / "workstreams"
        archive.mkdir(parents=True, exist_ok=True)
        (archive / "WS007.md").write_text("# archived WS007\n", encoding="utf-8")
        git(repo, "add", "--all")
        git(repo, "commit", "-m", "archive id")
        git(repo, "branch", "codex/ws009-existing")
        code, payload, stderr = self.json_cli(
            [
                "workstream",
                "reserve",
                str(context),
                "--title",
                "Next",
                "--slug",
                "next-task",
                "--owner",
                "codex",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["id"], "WS010")

    def test_worktree_create_plan_and_apply_are_idempotent(self):
        _root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug="long-task")
        workstream_id = reserved["id"]
        code, plan, stderr = self.json_cli(
            ["worktree", "create", str(context), "--workstream", workstream_id]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(plan["status"], "ready_to_create")
        self.assertFalse(plan["applied"])
        self.assertFalse(Path(plan["target"]["path"]).exists())
        created = self.create_ws_worktree(context, workstream_id)
        target = Path(created["target"]["path"])
        self.assertTrue(target.is_dir())
        self.assertEqual(git(target, "branch", "--show-current").stdout.strip(), "codex/ws001-long-task")
        self.assertEqual(git_common_dir(target), git_common_dir(repo))
        repeated = self.create_ws_worktree(context, workstream_id)
        self.assertEqual(repeated["status"], "already_created")
        self.assertEqual(len([r for r in list_worktrees(repo) if r.branch_short == "codex/ws001-long-task"]), 1)

    def test_worktree_create_recovers_existing_branch_without_path(self):
        _root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug="resume-task")
        branch = "codex/ws001-resume-task"
        git(repo, "branch", branch, "main")
        created = self.create_ws_worktree(context, reserved["id"])
        self.assertEqual(created["status"], "created")
        self.assertTrue(Path(created["target"]["path"]).is_dir())

    def test_non_workstream_create_does_not_create_workstream(self):
        _root, repo, context = self.make_repo()
        code, payload, stderr = self.json_cli(
            [
                "worktree",
                "create",
                str(context),
                "--kind",
                "investigation",
                "--slug",
                "runtime-timeout",
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["target"]["branch"], "codex/investigation-runtime-timeout")
        self.assertTrue(Path(payload["target"]["path"]).is_dir())
        self.assertFalse(list((context / "active" / "workstreams").glob("WS*.md")))
        self.assertTrue(read_registry(git_common_dir(repo), "investigation:runtime-timeout"))

    def test_low_information_non_workstream_slug_is_refused(self):
        _root, _repo, context = self.make_repo()
        code, payload, _stderr = self.json_cli(
            [
                "worktree",
                "create",
                str(context),
                "--kind",
                "experiment",
                "--slug",
                "test",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "invalid_low_information_slug")

    def test_existing_non_worktree_target_path_is_preserved_and_refused(self):
        root, _repo, context = self.make_repo()
        reserved = self.reserve(context, slug="occupied-task")
        target = root / "repo_worktrees" / "ws001-occupied-task"
        target.mkdir(parents=True)
        (target / "user.txt").write_text("preserve", encoding="utf-8")
        code, payload, _stderr = self.json_cli(
            [
                "worktree",
                "create",
                str(context),
                "--workstream",
                reserved["id"],
                "--apply",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "target_path_exists_not_worktree")
        self.assertEqual((target / "user.txt").read_text(encoding="utf-8"), "preserve")

    def test_worktree_verify_list_and_audit(self):
        _root, _repo, context = self.make_repo()
        reserved = self.reserve(context, slug="verified-task")
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        code, verified, stderr = self.json_cli(
            ["worktree", "verify", str(context), "--workstream", reserved["id"]]
        )
        self.assertEqual(code, 0, stderr)
        self.assertTrue(verified["ok"])
        code, listed, stderr = self.json_cli(["worktree", "list", str(context)])
        self.assertEqual(code, 0, stderr)
        self.assertIn(str(target), [row["path"] for row in listed["worktrees"]])
        code, audited, stderr = self.json_cli(["worktree", "audit", str(context)])
        self.assertEqual(code, 0, stderr)
        self.assertTrue(audited["ok"])

    def test_attach_requires_standard_name_and_correct_common_dir(self):
        _root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug="attach-task")
        branch = "codex/ws001-attach-task"
        path = repo.parent / "repo_worktrees" / "ws001-attach-task"
        git(repo, "worktree", "add", str(path), "-b", branch, "main")
        code, plan, stderr = self.json_cli(
            [
                "worktree",
                "attach",
                str(context),
                "--workstream",
                reserved["id"],
                "--target",
                str(path),
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(plan["status"], "ready_to_attach")
        code, applied, stderr = self.json_cli(
            [
                "worktree",
                "attach",
                str(context),
                "--workstream",
                reserved["id"],
                "--target",
                str(path),
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(applied["status"], "attached")

    def test_sync_merges_primary_into_clean_worktree(self):
        _root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug="sync-task")
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        (repo / "primary.txt").write_text("primary", encoding="utf-8")
        git(repo, "add", "primary.txt")
        git(repo, "commit", "-m", "primary advance")
        code, plan, stderr = self.json_cli(
            ["worktree", "sync", str(context), "--workstream", reserved["id"]]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(plan["status"], "ready_to_sync")
        code, result, stderr = self.json_cli(
            [
                "worktree",
                "sync",
                str(context),
                "--workstream",
                reserved["id"],
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(result["status"], "synced")
        self.assertTrue((target / "primary.txt").is_file())

    def test_sync_dirty_worktree_is_refused(self):
        _root, _repo, context = self.make_repo()
        reserved = self.reserve(context, slug="dirty-sync")
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        (target / "dirty.txt").write_text("dirty", encoding="utf-8")
        code, payload, _stderr = self.json_cli(
            ["worktree", "sync", str(context), "--workstream", reserved["id"]]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "worktree_dirty")

    def test_merge_requires_ready_workstream_and_clean_primary(self):
        _root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug="merge-gate")
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        (target / "feature.txt").write_text("feature", encoding="utf-8")
        git(target, "add", "feature.txt")
        git(target, "commit", "-m", "feature")
        code, payload, _stderr = self.json_cli(
            ["worktree", "merge-plan", str(context), "--workstream", reserved["id"]]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "workstream_not_ready_to_merge")
        self.mark_ready_in_worktree(target, reserved["id"])
        (repo / "dirty.txt").write_text("dirty", encoding="utf-8")
        code, payload, _stderr = self.json_cli(
            ["worktree", "merge-plan", str(context), "--workstream", reserved["id"]]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "primary_checkout_dirty")

    def test_merge_no_ff_checks_and_close_lifecycle(self):
        _root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug="full-lifecycle")
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        (target / "feature.txt").write_text("feature", encoding="utf-8")
        git(target, "add", "feature.txt")
        git(target, "commit", "-m", "feature")
        self.mark_ready_in_worktree(target, reserved["id"])
        pre = json.dumps(["git", "status", "--porcelain"], ensure_ascii=False)
        post = json.dumps(["git", "merge-base", "--is-ancestor", "HEAD^2", "HEAD"])
        code, plan, stderr = self.json_cli(
            ["worktree", "merge-plan", str(context), "--workstream", reserved["id"]]
        )
        self.assertEqual(code, 0, stderr)
        self.assertTrue(plan["merge_allowed"])
        code, merged, stderr = self.json_cli(
            [
                "worktree",
                "merge",
                str(context),
                "--workstream",
                reserved["id"],
                "--pre-check-json",
                pre,
                "--post-check-json",
                post,
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(merged["status"], "merged")
        parents = git(repo, "show", "-s", "--format=%P", "HEAD").stdout.split()
        self.assertEqual(len(parents), 2)
        self.assertTrue((repo / "feature.txt").is_file())
        code, close_plan, stderr = self.json_cli(
            ["worktree", "close", str(context), "--workstream", reserved["id"]]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(close_plan["status"], "ready_to_close")
        code, closed, stderr = self.json_cli(
            [
                "worktree",
                "close",
                str(context),
                "--workstream",
                reserved["id"],
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(closed["status"], "closed")
        self.assertFalse(target.exists())
        self.assertFalse(git(repo, "branch", "--list", "codex/ws001-full-lifecycle").stdout.strip())

    def test_close_refuses_unmerged_or_dirty_worktree(self):
        _root, _repo, context = self.make_repo()
        reserved = self.reserve(context, slug="close-gate")
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        (target / "feature.txt").write_text("feature", encoding="utf-8")
        git(target, "add", "feature.txt")
        git(target, "commit", "-m", "feature")
        code, payload, _stderr = self.json_cli(
            ["worktree", "close", str(context), "--workstream", reserved["id"]]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "branch_not_merged")
        (target / "dirty.txt").write_text("dirty", encoding="utf-8")
        code, payload, _stderr = self.json_cli(
            ["worktree", "close", str(context), "--workstream", reserved["id"]]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "worktree_dirty")

    def test_operation_lock_and_resume_plan_are_auditable(self):
        _root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug="journal-task")
        common = git_common_dir(repo)
        lock = acquire_operation_lock(common, "WS001-worktree", "test-lock")
        try:
            code, payload, _stderr = self.json_cli(
                [
                    "worktree",
                    "create",
                    str(context),
                    "--workstream",
                    reserved["id"],
                    "--apply",
                ]
            )
            self.assertNotEqual(code, 0)
            self.assertEqual(payload["error_code"], "worktree_operation_locked")
        finally:
            release_operation_lock(lock)
        created = self.create_ws_worktree(context, reserved["id"])
        operation_id = created["operation_id"]
        code, inspected, stderr = self.json_cli(
            ["worktree", "resume", operation_id, str(context)]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(inspected["status"], "resume_planned")
        self.assertEqual(inspected["operation"]["status"], "completed")

    def test_interrupted_reservation_resumes_same_id_from_journal(self):
        _root, repo, context = self.make_repo()
        hook = repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        code, payload, _stderr = self.json_cli(
            [
                "workstream",
                "reserve",
                str(context),
                "--title",
                "Interrupted",
                "--slug",
                "interrupted-task",
                "--owner",
                "codex",
                "--apply",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "git_command_failed")
        self.assertFalse(git(repo, "log", "-1", "--format=%s").stdout.startswith("文档：登记WS001"))
        operations = sorted((repo / ".git" / "acf" / "operations").glob("*.json"))
        self.assertEqual(len(operations), 1)
        journal = json.loads(operations[0].read_text(encoding="utf-8"))
        self.assertEqual(journal["status"], "failed")
        self.assertEqual(journal["reservation"]["workstream_id"], "WS001")
        operation_id = journal["operation_id"]
        hook.unlink()
        code, plan, stderr = self.json_cli(
            [
                "workstream",
                "reserve",
                str(context),
                "--resume-operation",
                operation_id,
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(plan["status"], "reservation_resume_planned")
        code, resumed, stderr = self.json_cli(
            [
                "workstream",
                "reserve",
                str(context),
                "--resume-operation",
                operation_id,
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(resumed["id"], "WS001")
        self.assertEqual(resumed["status"], "reserved")
        self.assertTrue((context / "active" / "workstreams" / "WS001.md").is_file())
        self.assertIn("WS001", git(repo, "show", "-s", "--format=%s", "HEAD").stdout)

    def test_reserve_explicit_duplicate_and_reservation_lock_are_refused(self):
        _root, repo, context = self.make_repo()
        self.reserve(context, slug="first-task")
        code, payload, _stderr = self.json_cli(
            [
                "workstream",
                "reserve",
                str(context),
                "--id",
                "WS001",
                "--title",
                "Duplicate",
                "--slug",
                "duplicate-task",
                "--owner",
                "codex",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "workstream_duplicate_id")

        common = git_common_dir(repo)
        lock = acquire_operation_lock(common, "workstream-reservation", "reserve-lock")
        try:
            code, payload, _stderr = self.json_cli(
                [
                    "workstream",
                    "reserve",
                    str(context),
                    "--title",
                    "Locked",
                    "--slug",
                    "locked-task",
                    "--owner",
                    "codex",
                    "--apply",
                ]
            )
            self.assertNotEqual(code, 0)
            self.assertEqual(payload["error_code"], "worktree_operation_locked")
        finally:
            release_operation_lock(lock)

    def test_branch_checked_out_at_other_path_is_refused(self):
        root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug="branch-conflict")
        other_path = root / "other-worktree"
        git(
            repo,
            "worktree",
            "add",
            str(other_path),
            "-b",
            "codex/ws001-branch-conflict",
            "main",
        )
        code, payload, _stderr = self.json_cli(
            [
                "worktree",
                "create",
                str(context),
                "--workstream",
                reserved["id"],
                "--apply",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "branch_already_checked_out")
        self.assertTrue(other_path.is_dir())

    def test_target_worktree_from_wrong_repository_is_refused(self):
        root, _repo, context = self.make_repo()
        reserved = self.reserve(context, slug="wrong-repo")
        expected = root / "repo_worktrees" / "ws001-wrong-repo"
        other = root / "other-repo"
        other.mkdir()
        git(other, "init", "-b", "main")
        git(other, "config", "user.name", "Other")
        git(other, "config", "user.email", "other@example.invalid")
        (other / "README.md").write_text("other", encoding="utf-8")
        git(other, "add", "README.md")
        git(other, "commit", "-m", "other")
        git(
            other,
            "worktree",
            "add",
            str(expected),
            "-b",
            "codex/ws001-wrong-repo",
            "main",
        )
        code, payload, _stderr = self.json_cli(
            [
                "worktree",
                "create",
                str(context),
                "--workstream",
                reserved["id"],
                "--apply",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "git_common_dir_mismatch")
        self.assertTrue((expected / "README.md").is_file())

    def test_detached_worktree_is_reported_by_audit(self):
        root, repo, context = self.make_repo()
        detached = root / "detached"
        git(repo, "worktree", "add", "--detach", str(detached), "main")
        code, payload, _stderr = self.json_cli(["worktree", "audit", str(context)])
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["status"], "findings")
        self.assertIn("detached_worktree", [row["code"] for row in payload["findings"]])

    def test_primary_advance_after_target_resolution_is_refused(self):
        _root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug="advance-gate")
        project = discover_git_project(context)
        target, _info = resolve_workstream_target(project, reserved["id"])
        (repo / "advance.txt").write_text("advance", encoding="utf-8")
        git(repo, "add", "advance.txt")
        git(repo, "commit", "-m", "advance primary")
        with self.assertRaisesRegex(SystemExit, "primary_branch_advanced"):
            apply_create(project, target)
        self.assertFalse(target.path.exists())
        self.assertFalse(git(repo, "branch", "--list", target.branch).stdout.strip())

    def test_sync_conflict_preflight_does_not_modify_branch(self):
        _root, repo, context = self.make_repo()
        (repo / "shared.txt").write_text("base\n", encoding="utf-8")
        git(repo, "add", "shared.txt")
        git(repo, "commit", "-m", "shared base")
        reserved = self.reserve(context, slug="sync-conflict")
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        (target / "shared.txt").write_text("feature\n", encoding="utf-8")
        git(target, "add", "shared.txt")
        git(target, "commit", "-m", "feature shared")
        branch_before = git(target, "rev-parse", "HEAD").stdout.strip()
        (repo / "shared.txt").write_text("primary\n", encoding="utf-8")
        git(repo, "add", "shared.txt")
        git(repo, "commit", "-m", "primary shared")
        code, payload, _stderr = self.json_cli(
            ["worktree", "sync", str(context), "--workstream", reserved["id"]]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "merge_conflicts_detected")
        self.assertEqual(git(target, "rev-parse", "HEAD").stdout.strip(), branch_before)
        self.assertFalse((target / ".git" / "MERGE_HEAD").exists())

    def test_merge_conflict_preflight_does_not_modify_primary(self):
        _root, repo, context = self.make_repo()
        (repo / "shared.txt").write_text("base\n", encoding="utf-8")
        git(repo, "add", "shared.txt")
        git(repo, "commit", "-m", "shared base")
        reserved = self.reserve(context, slug="merge-conflict")
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        (target / "shared.txt").write_text("feature\n", encoding="utf-8")
        git(target, "add", "shared.txt")
        git(target, "commit", "-m", "feature shared")
        self.mark_ready_in_worktree(target, reserved["id"])
        (repo / "shared.txt").write_text("primary\n", encoding="utf-8")
        git(repo, "add", "shared.txt")
        git(repo, "commit", "-m", "primary shared")
        main_before = git(repo, "rev-parse", "HEAD").stdout.strip()
        code, payload, _stderr = self.json_cli(
            ["worktree", "merge-plan", str(context), "--workstream", reserved["id"]]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "merge_conflicts_detected")
        self.assertEqual(git(repo, "rev-parse", "HEAD").stdout.strip(), main_before)
        self.assertFalse((repo / ".git" / "MERGE_HEAD").exists())

    def test_pre_merge_check_failure_prevents_merge(self):
        _root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug="precheck-gate")
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        (target / "feature.txt").write_text("feature", encoding="utf-8")
        git(target, "add", "feature.txt")
        git(target, "commit", "-m", "feature")
        self.mark_ready_in_worktree(target, reserved["id"])
        before = git(repo, "rev-parse", "HEAD").stdout.strip()
        failing = json.dumps(["python", "-c", "import sys; sys.exit(3)"])
        code, payload, _stderr = self.json_cli(
            [
                "worktree",
                "merge",
                str(context),
                "--workstream",
                reserved["id"],
                "--pre-check-json",
                failing,
                "--apply",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "worktree_pre_merge_check_failed")
        self.assertEqual(git(repo, "rev-parse", "HEAD").stdout.strip(), before)

    def test_post_merge_check_failure_retains_merge_commit(self):
        _root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug="postcheck-gate")
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        (target / "feature.txt").write_text("feature", encoding="utf-8")
        git(target, "add", "feature.txt")
        git(target, "commit", "-m", "feature")
        self.mark_ready_in_worktree(target, reserved["id"])
        before = git(repo, "rev-parse", "HEAD").stdout.strip()
        failing = json.dumps(["python", "-c", "import sys; sys.exit(4)"])
        code, payload, _stderr = self.json_cli(
            [
                "worktree",
                "merge",
                str(context),
                "--workstream",
                reserved["id"],
                "--post-check-json",
                failing,
                "--apply",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "worktree_post_merge_check_failed")
        self.assertEqual(payload["status"], "merged_checks_failed")
        self.assertNotEqual(git(repo, "rev-parse", "HEAD").stdout.strip(), before)
        self.assertEqual(len(git(repo, "show", "-s", "--format=%P", "HEAD").stdout.split()), 2)

    def test_close_recovers_when_worktree_was_manually_removed_and_is_idempotent(self):
        _root, repo, context = self.make_repo()
        reserved = self.reserve(context, slug="partial-close")
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        (target / "feature.txt").write_text("feature", encoding="utf-8")
        git(target, "add", "feature.txt")
        git(target, "commit", "-m", "feature")
        self.mark_ready_in_worktree(target, reserved["id"])
        code, _merged, stderr = self.json_cli(
            [
                "worktree",
                "merge",
                str(context),
                "--workstream",
                reserved["id"],
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        git(repo, "worktree", "remove", str(target))
        self.assertTrue(git(repo, "branch", "--list", "codex/ws001-partial-close").stdout.strip())
        code, closed, stderr = self.json_cli(
            [
                "worktree",
                "close",
                str(context),
                "--workstream",
                reserved["id"],
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(closed["status"], "closed")
        self.assertFalse(git(repo, "branch", "--list", "codex/ws001-partial-close").stdout.strip())
        code, repeated, stderr = self.json_cli(
            [
                "worktree",
                "close",
                str(context),
                "--workstream",
                reserved["id"],
                "--apply",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(repeated["status"], "already_closed")

    def test_verified_worktree_selects_only_its_bound_workstream(self):
        _root, _repo, context = self.make_repo()
        reserved = self.reserve(context, slug="routing-selection")
        created = self.create_ws_worktree(context, reserved["id"])
        target = Path(created["target"]["path"])
        target_context = target / "docs" / "ai"
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "set",
                    reserved["id"],
                    str(target_context),
                    "--status",
                    "Active",
                ],
                cwd=target,
            )[0],
            0,
        )

        code, payload, stderr = self.json_cli(
            ["status", str(target_context)], cwd=target
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["workstream_state"], "WorktreeSelected")
        self.assertEqual(payload["selected_workstream"], reserved["id"])
        self.assertEqual(payload["selection_source"], "verified_worktree")
        self.assertEqual(payload["disclosure_level"], "workstream_pointer")

        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "add",
                    str(target_context),
                    "--id",
                    "WS002",
                    "--title",
                    "Conflicting selection",
                    "--owner",
                    "codex",
                    "--goal",
                    "Exercise selection conflict.",
                    "--output",
                    "Conflict evidence.",
                ],
                cwd=target,
            )[0],
            0,
        )
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "set",
                    "WS002",
                    str(target_context),
                    "--status",
                    "Active",
                ],
                cwd=target,
            )[0],
            0,
        )
        code, conflict, _stderr = self.json_cli(
            ["status", str(target_context), "--workstream", "WS002"], cwd=target
        )
        self.assertEqual(code, 2)
        self.assertEqual(conflict["workstream_state"], "SelectionConflict")
        self.assertEqual(conflict["context_mode"], "global")
        self.assertIsNone(conflict["selected_workstream"])
        self.assertEqual(
            set(conflict["selection_candidates"]), {reserved["id"], "WS002"}
        )

    def test_invalid_project_config_is_isolated_to_worktree_commands(self):
        _root, repo, context = self.make_repo()
        config_dir = repo / ".acf"
        config_dir.mkdir()
        (config_dir / "project.toml").write_text(
            "[git]\nprimary_branch = 'does-not-exist'\n",
            encoding="utf-8",
        )
        git(repo, "add", ".acf/project.toml")
        git(repo, "commit", "-m", "invalid worktree config")
        self.assertEqual(
            self.run_cli(
                [
                    "workstream",
                    "add",
                    str(context),
                    "--id",
                    "WS001",
                    "--title",
                    "Still works",
                    "--owner",
                    "codex",
                ]
            )[0],
            0,
        )
        code, payload, _stderr = self.json_cli(["worktree", "list", str(context)])
        self.assertNotEqual(code, 0)
        self.assertEqual(payload["error_code"], "primary_branch_missing")

    def test_project_toml_overrides_worktree_root_and_prefix(self):
        root, repo, context = self.make_repo()
        config_dir = repo / ".acf"
        config_dir.mkdir()
        custom_root = root / "custom-worktrees"
        (config_dir / "project.toml").write_text(
            "[git]\n"
            f'primary_checkout = "{repo.as_posix()}"\n'
            'primary_branch = "main"\n'
            f'worktree_root = "{custom_root.as_posix()}"\n'
            'branch_prefix = "agent"\n',
            encoding="utf-8",
        )
        git(repo, "add", ".acf/project.toml")
        git(repo, "commit", "-m", "configure worktrees")
        reserved = self.reserve(context, slug="configured-task")
        created = self.create_ws_worktree(context, reserved["id"])
        self.assertEqual(created["target"]["branch"], "agent/ws001-configured-task")
        self.assertTrue(Path(created["target"]["path"]).is_relative_to(custom_root))

    def test_toml_subset_fallback_shape(self):
        root = tempfile.TemporaryDirectory()
        self._roots.append(root)
        path = Path(root.name) / "project.toml"
        path.write_text(
            "[git]\nprimary_branch = 'main'\nbranch_prefix = 'codex'\n",
            encoding="utf-8",
        )
        payload = load_toml_subset(path)
        self.assertEqual(payload["git"]["primary_branch"], "main")


if __name__ == "__main__":
    unittest.main()
