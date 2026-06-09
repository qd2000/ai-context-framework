import sys
import json
import unittest
from pathlib import Path

from scripts.upgrade_matrix import ROOT, run_matrix


class UpgradeMatrixTests(unittest.TestCase):
    def test_quick_upgrade_matrix(self):
        payload = run_matrix(
            mode="quick",
            acf_cmd=[sys.executable, str(ROOT / "acf.py")],
        )

        self.assertTrue(payload["ok"], payload)
        self.assertGreaterEqual(payload["fixture_count"], 3)
        fixtures = {result["fixture"] for result in payload["results"]}
        self.assertIn("v00317_standard_legacy", fixtures)
        self.assertIn("customized_docs_marker_notes", fixtures)
        self.assertIn("curation_draft_collision", fixtures)
        self.assertIn("missing_context_curation_prompt", fixtures)
        self.assertIn("old_without_workstreams_optional", fixtures)
        self.assertIn("old_active_reference_traceability", fixtures)

    def test_full_upgrade_matrix_fixture_metadata_is_present(self):
        fixture_root = Path(__file__).resolve().parent / "fixtures" / "upgrade_matrix"
        metadata_files = sorted(fixture_root.glob("*/metadata.json"))
        self.assertGreaterEqual(len(metadata_files), 13)
        fixture_names = {metadata.parent.name for metadata in metadata_files}
        self.assertIn("old_active_reference_traceability", fixture_names)
        self.assertIn("old_workstreams_without_current_stage", fixture_names)
        self.assertIn("old_adr_without_front_matter", fixture_names)
        self.assertIn("custom_agents_missing_reference_combo", fixture_names)
        for required in {
            "placeholder_polluted_standard",
            "workstream_expired_invalid_stage",
            "broken_links_multiple_active_plan",
            "legacy_nonstandard_ai_path",
            "global_log_legacy_unresolved",
            "old_minimal_context",
            "old_standard_missing_layers",
            "root_agent_variants",
            "root_agent_stale",
            "marker_collision_variants",
            "upgrade_archive_draft_collision",
            "missing_core_indexes",
            "workstream_parallel_valid",
            "workstream_merge_terminal_retained",
        }:
            self.assertIn(required, fixture_names)
        for metadata in metadata_files:
            text = metadata.read_text(encoding="utf-8")
            self.assertIn("source_version", text)
            self.assertIn("risk_tags", text)
            self.assertIn("expected_upgrade_behavior", text)
            payload = json.loads(text)
            if payload.get("scenario") == "main":
                self.assertIn("expected_plan_readiness", payload)
                self.assertIn("expected_finding_codes", payload)
                self.assertIsInstance(payload["expected_finding_codes"], list)
                self.assertIn("expected_structural_change_suffixes", payload)
                self.assertIsInstance(payload["expected_structural_change_suffixes"], list)
                self.assertIs(payload.get("expect_plan_no_write"), True)


if __name__ == "__main__":
    unittest.main()
