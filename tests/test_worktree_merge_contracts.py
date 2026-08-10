from __future__ import annotations

import json
import unittest

from ai_context_framework.worktree_merge_contracts import (
    ARTIFACT_HANDOFF_SCHEMA_VERSION,
    DEFAULT_MERGE_RETRY_POLICY,
    MERGE_OPERATION_SCHEMA_VERSION,
    MERGE_STRATEGY,
    PROMOTION_STRATEGY,
    artifact_handoff_ready_for_promotion,
    build_artifact_handoff_v1,
    build_merge_operation_v2,
    validate_artifact_handoff_v1,
    validate_merge_operation_v2,
)
from tests.worktree_scenarios import TemporaryWorktreeScenario, run_git


class WorktreeMergeContractTests(unittest.TestCase):
    def test_operation_v2_freezes_single_integration_strategy_and_retry_defaults(self):
        payload = build_merge_operation_v2(
            operation_id="merge-001",
            target_key="WS001",
            source_branch="codex/ws001-feature",
            source_path="C:/worktrees/ws001-feature",
            source_head="1" * 40,
            primary_branch="main",
            primary_checkout="C:/repo",
            primary_head="2" * 40,
            integration_branch="acf/integration/WS001/merge-001",
            integration_path="C:/worktrees/.acf-integration/merge-001",
            timestamp="2026-08-06T00:00:00+00:00",
        )

        self.assertEqual(payload["schema_version"], MERGE_OPERATION_SCHEMA_VERSION)
        self.assertEqual(payload["merge_strategy"], MERGE_STRATEGY)
        self.assertEqual(payload["promotion_strategy"], PROMOTION_STRATEGY)
        self.assertEqual(payload["integration"]["base_head"], "2" * 40)
        self.assertEqual(
            payload["retry_policy"],
            DEFAULT_MERGE_RETRY_POLICY.to_payload(),
        )
        self.assertEqual(payload["retry_policy"]["max_replans"], 8)
        self.assertEqual(payload["retry_policy"]["conflict_replans"], 3)
        json.dumps(payload)
        validate_merge_operation_v2(payload)

    def test_operation_v2_rejects_primary_direct_merge_strategy(self):
        payload = build_merge_operation_v2(
            operation_id="merge-002",
            target_key="WS001",
            source_branch="codex/ws001-feature",
            source_path="C:/worktrees/ws001-feature",
            source_head="1" * 40,
            primary_branch="main",
            primary_checkout="C:/repo",
            primary_head="2" * 40,
            integration_branch="acf/integration/WS001/merge-002",
            integration_path="C:/worktrees/.acf-integration/merge-002",
        )
        payload["merge_strategy"] = "direct_primary_checkout"
        with self.assertRaisesRegex(ValueError, "temporary integration worktree"):
            validate_merge_operation_v2(payload)

    def test_artifact_handoff_blocks_unknown_and_requires_verified_preserved_entries(self):
        unknown = build_artifact_handoff_v1(
            target_key="WS001",
            source_head="3" * 40,
            entries=[
                {
                    "relative_path": "output/result.ksc",
                    "classification": "unknown",
                    "transfer": "none",
                    "destination": None,
                    "size": 12,
                    "sha256": None,
                    "status": "unclassified",
                    "rationale": None,
                }
            ],
        )
        self.assertEqual(unknown["schema_version"], ARTIFACT_HANDOFF_SCHEMA_VERSION)
        self.assertFalse(artifact_handoff_ready_for_promotion(unknown))

        digest = "a" * 64
        ready = build_artifact_handoff_v1(
            target_key="WS001",
            source_head="3" * 40,
            entries=[
                {
                    "relative_path": "output/result.ksc",
                    "classification": "required",
                    "transfer": "copy",
                    "destination": "C:/artifacts/WS001/result.ksc",
                    "size": 12,
                    "sha256": digest,
                    "status": "verified",
                    "rationale": None,
                },
                {
                    "relative_path": "output/cache.bin",
                    "classification": "reproducible_cache",
                    "transfer": "none",
                    "destination": None,
                    "size": 4,
                    "sha256": None,
                    "status": "acknowledged",
                    "rationale": "Rebuilt by the documented test command.",
                },
            ],
        )
        validate_artifact_handoff_v1(ready)
        self.assertTrue(artifact_handoff_ready_for_promotion(ready))

    def test_artifact_handoff_rejects_absolute_or_unsafe_paths(self):
        with self.assertRaisesRegex(ValueError, "must be relative"):
            build_artifact_handoff_v1(
                target_key="WS001",
                source_head="3" * 40,
                entries=[
                    {
                        "relative_path": "../outside.bin",
                        "classification": "unknown",
                        "transfer": "none",
                        "destination": None,
                        "size": 1,
                        "sha256": None,
                        "status": "unclassified",
                        "rationale": None,
                    }
                ],
            )

    def test_temporary_integration_merge_leaves_primary_unchanged(self):
        with TemporaryWorktreeScenario() as scenario:
            primary_before = scenario.head(scenario.primary)
            source_tip = scenario.commit_source_files(
                [("feature.txt", "feature\n")],
                message="feature",
            )
            candidate_tip = scenario.merge_source_in_integration()

            self.assertEqual(scenario.head(scenario.primary), primary_before)
            parents = run_git(
                scenario.integration,
                "show",
                "-s",
                "--format=%P",
                candidate_tip,
            ).stdout.split()
            self.assertEqual(parents, [primary_before, source_tip])
            self.assertTrue((scenario.integration / "feature.txt").is_file())
            self.assertFalse((scenario.primary / "feature.txt").exists())

    def test_ignored_artifact_exists_while_source_git_status_is_clean(self):
        with TemporaryWorktreeScenario() as scenario:
            scenario.commit_source_files([("feature.txt", "feature\n")])
            scenario.write(scenario.source, "output/result.ksc", b"ksc-result")

            self.assertEqual(scenario.status(scenario.source), [])
            self.assertIn(
                "output/result.ksc",
                scenario.ignored_paths(scenario.source),
            )


if __name__ == "__main__":
    unittest.main()
