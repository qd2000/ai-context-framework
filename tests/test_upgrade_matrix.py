import sys
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

    def test_full_upgrade_matrix_fixture_metadata_is_present(self):
        fixture_root = Path(__file__).resolve().parent / "fixtures" / "upgrade_matrix"
        metadata_files = sorted(fixture_root.glob("*/metadata.json"))
        self.assertGreaterEqual(len(metadata_files), 8)
        for metadata in metadata_files:
            text = metadata.read_text(encoding="utf-8")
            self.assertIn("source_version", text)
            self.assertIn("risk_tags", text)
            self.assertIn("expected_upgrade_behavior", text)


if __name__ == "__main__":
    unittest.main()
