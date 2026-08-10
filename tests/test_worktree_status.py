from __future__ import annotations

import unittest
from pathlib import Path

from ai_context_framework.worktree_status import (
    SNAPSHOT_SCHEMA_VERSION,
    capture_git_worktree_snapshot,
    comparison_key,
    parse_porcelain_v2_z,
)
from tests.worktree_scenarios import TemporaryWorktreeScenario, run_git


class WorktreeStatusTests(unittest.TestCase):
    def test_snapshot_separates_staged_unstaged_untracked_and_ignored(self):
        with TemporaryWorktreeScenario() as scenario:
            scenario.write(scenario.primary, "staged.txt", "staged\n")
            run_git(scenario.primary, "add", "staged.txt")

            scenario.write(scenario.primary, "mixed.txt", "index\n")
            run_git(scenario.primary, "add", "mixed.txt")
            scenario.write(scenario.primary, "mixed.txt", "worktree\n")

            scenario.write(scenario.primary, "base.txt", "base changed\n")
            scenario.write(scenario.primary, "untracked.txt", "untracked\n")
            scenario.write(scenario.primary, "output/result.ksc", b"ignored-result")

            snapshot = capture_git_worktree_snapshot(
                scenario.primary,
                include_ignored=True,
                timestamp="2026-08-06T00:00:00+00:00",
            )

            self.assertEqual(snapshot["schema_version"], SNAPSHOT_SCHEMA_VERSION)
            self.assertEqual(snapshot["branch"], "main")
            self.assertIn("staged.txt", snapshot["staged_paths"])
            self.assertIn("mixed.txt", snapshot["staged_paths"])
            self.assertIn("mixed.txt", snapshot["unstaged_paths"])
            self.assertIn("base.txt", snapshot["unstaged_paths"])
            self.assertEqual(snapshot["untracked_paths"], ["untracked.txt"])
            self.assertIn("output/result.ksc", snapshot["ignored_paths"])
            self.assertFalse(snapshot["sequencer"]["active"])

            mixed = next(row for row in snapshot["entries"] if row["path"] == "mixed.txt")
            self.assertTrue(mixed["staged"])
            self.assertTrue(mixed["unstaged"])
            mixed_state = next(
                row for row in snapshot["path_states"] if row["path"] == "mixed.txt"
            )
            self.assertEqual(mixed_state["kind"], "file")
            self.assertEqual(len(mixed_state["sha256"]), 64)

    def test_snapshot_fingerprint_is_stable_and_tracks_worktree_content(self):
        with TemporaryWorktreeScenario() as scenario:
            scenario.write(scenario.primary, "untracked.txt", "one\n")
            first = capture_git_worktree_snapshot(
                scenario.primary,
                timestamp="2026-08-06T00:00:00+00:00",
            )
            second = capture_git_worktree_snapshot(
                scenario.primary,
                timestamp="2026-08-06T00:01:00+00:00",
            )
            self.assertEqual(first["fingerprint"], second["fingerprint"])

            scenario.write(scenario.primary, "untracked.txt", "two\n")
            changed = capture_git_worktree_snapshot(scenario.primary)
            self.assertNotEqual(first["fingerprint"], changed["fingerprint"])

    def test_snapshot_preserves_rename_source_and_destination(self):
        with TemporaryWorktreeScenario() as scenario:
            scenario.write(scenario.primary, "old-name.txt", "rename me\n")
            run_git(scenario.primary, "add", "old-name.txt")
            run_git(scenario.primary, "commit", "-m", "add rename source")
            run_git(scenario.primary, "mv", "old-name.txt", "new-name.txt")

            snapshot = capture_git_worktree_snapshot(scenario.primary)
            rename = next(row for row in snapshot["entries"] if row["record_type"] == "rename")
            self.assertEqual(rename["path"], "new-name.txt")
            self.assertEqual(rename["original_path"], "old-name.txt")
            self.assertIn("new-name.txt", snapshot["staged_paths"])
            state_paths = {row["path"] for row in snapshot["path_states"]}
            self.assertIn("new-name.txt", state_paths)
            self.assertIn("old-name.txt", state_paths)

    def test_snapshot_reports_index_lock_without_modifying_it(self):
        with TemporaryWorktreeScenario() as scenario:
            git_dir = run_git(
                scenario.primary,
                "rev-parse",
                "--path-format=absolute",
                "--git-dir",
            ).stdout.strip()
            actual_lock = Path(git_dir) / "index.lock"
            actual_lock.write_text("lock", encoding="utf-8")
            try:
                snapshot = capture_git_worktree_snapshot(scenario.primary)
                self.assertTrue(snapshot["index_lock"])
                self.assertTrue(actual_lock.is_file())
            finally:
                actual_lock.unlink(missing_ok=True)

    def test_unmerged_parser_preserves_all_stage_modes_and_oids(self):
        h1 = "1" * 40
        h2 = "2" * 40
        h3 = "3" * 40
        _headers, entries = parse_porcelain_v2_z(
            f"u UU N... 100644 100755 120000 100644 {h1} {h2} {h3} conflict.txt\0"
        )
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.record_type, "unmerged")
        self.assertEqual(entry.stage1_mode, "100644")
        self.assertEqual(entry.stage2_mode, "100755")
        self.assertEqual(entry.stage3_mode, "120000")
        self.assertEqual(entry.stage1_oid, h1)
        self.assertEqual(entry.stage2_oid, h2)
        self.assertEqual(entry.stage3_oid, h3)

    def test_comparison_key_is_normalized(self):
        self.assertEqual(comparison_key("folder\\file.txt"), comparison_key("folder/file.txt"))


if __name__ == "__main__":
    unittest.main()
