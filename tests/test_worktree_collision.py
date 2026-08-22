from __future__ import annotations

import unittest

from ai_context_framework.worktree_collision import (
    analyze_primary_collisions,
    build_candidate_preview,
    parse_raw_diff_z,
)
from ai_context_framework.worktree_status import capture_git_worktree_snapshot
from tests.worktree_scenarios import TemporaryWorktreeScenario, run_git


class WorktreeCollisionTests(unittest.TestCase):
    def test_raw_diff_parser_preserves_rename_source_and_destination(self):
        raw = ":100644 100644 " + "1" * 40 + " " + "2" * 40 + " R100\0old.txt\0new.txt\0"
        rows = parse_raw_diff_z(raw)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "R100")
        self.assertEqual(rows[0].original_path, "old.txt")
        self.assertEqual(rows[0].path, "new.txt")

    def test_candidate_preview_reports_merge_tree_changes(self):
        with TemporaryWorktreeScenario() as scenario:
            source_head = scenario.commit_source_files([("feature.txt", "feature\n")])
            primary_head = scenario.head(scenario.primary)
            candidate = build_candidate_preview(
                scenario.primary,
                primary_head=primary_head,
                source_head=source_head,
            )
            self.assertTrue(candidate["ok"])
            self.assertIn("feature.txt", candidate["changed_paths"])
            self.assertEqual(candidate["changes"][0]["status_code"], "A")

    def test_non_overlapping_primary_change_is_allowed(self):
        with TemporaryWorktreeScenario() as scenario:
            source_head = scenario.commit_source_files([("feature.txt", "feature\n")])
            scenario.write(scenario.primary, "notes.txt", "local\n")
            snapshot = capture_git_worktree_snapshot(scenario.primary, include_ignored=True)
            candidate = build_candidate_preview(
                scenario.primary,
                primary_head=scenario.head(scenario.primary),
                source_head=source_head,
            )
            report = analyze_primary_collisions(
                scenario.primary,
                snapshot=snapshot,
                candidate=candidate,
            )
            self.assertTrue(report["allowed"])
            self.assertEqual(report["collisions"], [])

    def test_identical_untracked_overlap_is_allowed(self):
        with TemporaryWorktreeScenario() as scenario:
            source_head = scenario.commit_source_files([("same.txt", "same\n")])
            scenario.write(scenario.primary, "same.txt", "same\n")
            snapshot = capture_git_worktree_snapshot(scenario.primary, include_ignored=True)
            candidate = build_candidate_preview(
                scenario.primary,
                primary_head=scenario.head(scenario.primary),
                source_head=source_head,
            )
            report = analyze_primary_collisions(
                scenario.primary,
                snapshot=snapshot,
                candidate=candidate,
            )
            self.assertTrue(report["allowed"])
            self.assertEqual(report["identical_overlap_paths"], ["same.txt"])

    def test_divergent_untracked_overlap_is_blocked(self):
        with TemporaryWorktreeScenario() as scenario:
            source_head = scenario.commit_source_files([("same.txt", "candidate\n")])
            scenario.write(scenario.primary, "same.txt", "local\n")
            snapshot = capture_git_worktree_snapshot(scenario.primary, include_ignored=True)
            candidate = build_candidate_preview(
                scenario.primary,
                primary_head=scenario.head(scenario.primary),
                source_head=source_head,
            )
            report = analyze_primary_collisions(
                scenario.primary,
                snapshot=snapshot,
                candidate=candidate,
            )
            self.assertFalse(report["allowed"])
            self.assertEqual(report["divergent_overlap_paths"], ["same.txt"])

    def test_stat_only_primary_overlap_does_not_block_candidate_change(self):
        with TemporaryWorktreeScenario() as scenario:
            scenario.write(scenario.primary, ".gitattributes", "normalized.txt text eol=crlf\n")
            scenario.write(scenario.primary, "normalized.txt", b"base\n")
            run_git(scenario.primary, "add", ".gitattributes", "normalized.txt")
            run_git(scenario.primary, "commit", "-m", "add normalized fixture")
            source_head = scenario.commit_source_files([("normalized.txt", b"candidate\n")])

            (scenario.primary / "normalized.txt").unlink()
            run_git(scenario.primary, "checkout", "--", "normalized.txt")
            self.assertIn(b"\r\n", (scenario.primary / "normalized.txt").read_bytes())
            (scenario.primary / "normalized.txt").write_bytes(b"base\n")

            snapshot = capture_git_worktree_snapshot(scenario.primary, include_ignored=True)
            self.assertEqual(["normalized.txt"], snapshot["stat_only_paths"])
            candidate = build_candidate_preview(
                scenario.primary,
                primary_head=scenario.head(scenario.primary),
                source_head=source_head,
            )
            report = analyze_primary_collisions(
                scenario.primary,
                snapshot=snapshot,
                candidate=candidate,
            )
            self.assertTrue(report["allowed"])
            self.assertEqual([], report["divergent_overlap_paths"])
            self.assertEqual([], report["collisions"])

    def test_primary_ignored_collision_is_detected_without_full_ignored_snapshot(self):
        with TemporaryWorktreeScenario() as scenario:
            source = scenario.add_source_worktree()
            scenario.write(source, "output/result.ksc", b"candidate")
            run_git(source, "add", "-f", "output/result.ksc")
            run_git(source, "commit", "-m", "source ignored-path candidate")
            source_head = scenario.head(source)
            scenario.write(scenario.primary, "output/result.ksc", b"local")
            snapshot = capture_git_worktree_snapshot(scenario.primary, include_ignored=False)
            candidate = build_candidate_preview(
                scenario.primary,
                primary_head=scenario.head(scenario.primary),
                source_head=source_head,
            )
            report = analyze_primary_collisions(
                scenario.primary,
                snapshot=snapshot,
                candidate=candidate,
            )
            self.assertFalse(report["allowed"])
            self.assertEqual(report["divergent_overlap_paths"], ["output/result.ksc"])

    def test_identical_staged_and_worktree_layers_are_required(self):
        with TemporaryWorktreeScenario() as scenario:
            source_head = scenario.commit_source_files([("same.txt", "candidate\n")])
            scenario.write(scenario.primary, "same.txt", "candidate\n")
            run_git(scenario.primary, "add", "same.txt")
            scenario.write(scenario.primary, "same.txt", "later-local\n")
            snapshot = capture_git_worktree_snapshot(scenario.primary, include_ignored=True)
            candidate = build_candidate_preview(
                scenario.primary,
                primary_head=scenario.head(scenario.primary),
                source_head=source_head,
            )
            report = analyze_primary_collisions(
                scenario.primary,
                snapshot=snapshot,
                candidate=candidate,
            )
            self.assertFalse(report["allowed"])
            self.assertEqual(report["divergent_overlap_paths"], ["same.txt"])

    def test_parent_child_collision_is_blocked(self):
        with TemporaryWorktreeScenario() as scenario:
            source_head = scenario.commit_source_files([("folder/child.txt", "candidate\n")])
            scenario.write(scenario.primary, "folder", "local-file\n")
            snapshot = capture_git_worktree_snapshot(scenario.primary, include_ignored=True)
            candidate = build_candidate_preview(
                scenario.primary,
                primary_head=scenario.head(scenario.primary),
                source_head=source_head,
            )
            report = analyze_primary_collisions(
                scenario.primary,
                snapshot=snapshot,
                candidate=candidate,
            )
            self.assertFalse(report["allowed"])
            self.assertIn("folder", report["divergent_overlap_paths"])

    def test_branch_conflict_is_reported_without_modifying_primary(self):
        with TemporaryWorktreeScenario() as scenario:
            scenario.write(scenario.primary, "shared.txt", "base\n")
            run_git(scenario.primary, "add", "shared.txt")
            run_git(scenario.primary, "commit", "-m", "shared base")
            source_head = scenario.commit_source_files([("shared.txt", "source\n")])
            scenario.write(scenario.primary, "shared.txt", "primary\n")
            run_git(scenario.primary, "add", "shared.txt")
            run_git(scenario.primary, "commit", "-m", "primary shared")
            primary_head = scenario.head(scenario.primary)
            candidate = build_candidate_preview(
                scenario.primary,
                primary_head=primary_head,
                source_head=source_head,
            )
            self.assertFalse(candidate["ok"])
            report = analyze_primary_collisions(
                scenario.primary,
                snapshot=capture_git_worktree_snapshot(scenario.primary),
                candidate=candidate,
            )
            self.assertTrue(report["branch_conflict"])
            self.assertEqual(scenario.head(scenario.primary), primary_head)


if __name__ == "__main__":
    unittest.main()
