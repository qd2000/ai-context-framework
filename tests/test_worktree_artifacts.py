from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_context_framework.git_support import git_common_dir
from ai_context_framework.worktree_artifacts import (
    build_artifact_plan,
    load_artifact_plan,
    migrate_artifacts,
    parse_artifact_overrides,
    scan_source_artifacts,
    write_artifact_plan,
)
from tests.worktree_scenarios import TemporaryWorktreeScenario


class WorktreeArtifactTests(unittest.TestCase):
    def test_scan_keeps_all_unconfigured_paths_unknown(self):
        with TemporaryWorktreeScenario() as scenario:
            source = scenario.add_source_worktree()
            scenario.write(source, "output/result.ksc", b"result")
            scenario.write(source, "pkg/__pycache__/module.pyc", b"cache")
            rows = scan_source_artifacts(source)
            by_path = {row["relative_path"]: row for row in rows}
            self.assertEqual(by_path["output/result.ksc"]["classification"], "unknown")
            self.assertEqual(by_path["output/result.ksc"]["status"], "unclassified")
            self.assertEqual(
                by_path["pkg/__pycache__/module.pyc"]["classification"],
                "unknown",
            )
            self.assertEqual(by_path["pkg/__pycache__/module.pyc"]["status"], "unclassified")

    def test_configured_patterns_classify_cache_and_discardable(self):
        with TemporaryWorktreeScenario() as scenario:
            source = scenario.add_source_worktree()
            scenario.write(source, "pkg/__pycache__/module.pyc", b"cache")
            scenario.write(source, "output/debug/session.tmp", b"debug")
            payload = build_artifact_plan(
                target_key="WS001",
                source_head=scenario.head(source),
                source_path=source,
                cache_patterns=["**/__pycache__/*.pyc"],
                discardable_patterns=["output/debug/*.tmp"],
            )
            by_path = {row["relative_path"]: row for row in payload["entries"]}
            self.assertEqual(
                by_path["pkg/__pycache__/module.pyc"]["classification"],
                "reproducible_cache",
            )
            self.assertEqual(
                by_path["output/debug/session.tmp"]["classification"],
                "discardable",
            )

    def test_explicit_override_for_missing_path_is_rejected(self):
        with TemporaryWorktreeScenario() as scenario, tempfile.TemporaryDirectory() as destination_root:
            source = scenario.add_source_worktree()
            destination = Path(destination_root) / "missing.ksc"
            with self.assertRaisesRegex(SystemExit, "artifact_override_path_not_found"):
                build_artifact_plan(
                    target_key="WS001",
                    source_head=scenario.head(source),
                    source_path=source,
                    overrides=parse_artifact_overrides(
                        required=[f"output/missing.ksc={destination}"]
                    ),
                )

    def test_required_artifact_is_copied_and_verified_idempotently(self):
        with TemporaryWorktreeScenario() as scenario, tempfile.TemporaryDirectory() as destination_root:
            source = scenario.add_source_worktree()
            result = scenario.write(source, "output/result.ksc", b"important-result")
            destination = Path(destination_root) / "retained" / "result.ksc"
            overrides = parse_artifact_overrides(
                required=[f"output/result.ksc={destination}"]
            )
            payload = build_artifact_plan(
                target_key="WS001",
                source_head=scenario.head(source),
                source_path=source,
                overrides=overrides,
            )
            common = git_common_dir(scenario.primary)
            path = write_artifact_plan(common, payload)
            self.assertTrue(path.is_file())
            first = migrate_artifacts(common, payload, source_path=source)
            self.assertTrue(first["promotion_ready"])
            self.assertEqual(destination.read_bytes(), result.read_bytes())
            loaded = load_artifact_plan(common, "WS001")
            self.assertIsNotNone(loaded)
            second = migrate_artifacts(common, loaded, source_path=source)
            self.assertTrue(second["promotion_ready"])
            self.assertEqual(second["results"][0]["status"], "already_verified")

    def test_unknown_artifact_blocks_promotion(self):
        with TemporaryWorktreeScenario() as scenario:
            source = scenario.add_source_worktree()
            scenario.write(source, "output/result.ksc", b"result")
            payload = build_artifact_plan(
                target_key="WS001",
                source_head=scenario.head(source),
                source_path=source,
            )
            common = git_common_dir(scenario.primary)
            result = migrate_artifacts(common, payload, source_path=source)
            self.assertFalse(result["promotion_ready"])
            self.assertEqual(result["results"][0]["status"], "unclassified")

    def test_retained_reference_must_match_source_digest(self):
        with TemporaryWorktreeScenario() as scenario, tempfile.TemporaryDirectory() as destination_root:
            source = scenario.add_source_worktree()
            scenario.write(source, "output/result.json", json.dumps({"ok": True}))
            destination = Path(destination_root) / "result.json"
            destination.write_text("different", encoding="utf-8")
            overrides = parse_artifact_overrides(
                references=[f"output/result.json={destination}"]
            )
            payload = build_artifact_plan(
                target_key="WS001",
                source_head=scenario.head(source),
                source_path=source,
                overrides=overrides,
            )
            result = migrate_artifacts(
                git_common_dir(scenario.primary), payload, source_path=source
            )
            self.assertFalse(result["promotion_ready"])
            self.assertEqual(result["results"][0]["status"], "reference_mismatch")

    def test_explicit_cache_and_discardable_are_acknowledged(self):
        with TemporaryWorktreeScenario() as scenario:
            source = scenario.add_source_worktree()
            scenario.write(source, "output/cache.bin", b"cache")
            scenario.write(source, "output/debug.tmp", b"debug")
            payload = build_artifact_plan(
                target_key="WS001",
                source_head=scenario.head(source),
                source_path=source,
                overrides=parse_artifact_overrides(
                    caches=["output/cache.bin"],
                    discardable=["output/debug.tmp"],
                ),
            )
            result = migrate_artifacts(
                git_common_dir(scenario.primary), payload, source_path=source
            )
            self.assertTrue(result["promotion_ready"])
            self.assertEqual(
                {row["status"] for row in result["results"]}, {"acknowledged"}
            )


if __name__ == "__main__":
    unittest.main()
