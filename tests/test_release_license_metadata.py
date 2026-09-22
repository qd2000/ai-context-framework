"""Deterministic PEP 639 license metadata regression for release artifacts.

The published v0.0.3.97 wheel and sdist carried no LICENSE file at all, so the
license story must now be asserted where it can still fail: in pyproject
metadata, in the committed egg-info snapshot, and in freshly built artifacts.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import tarfile
import unittest
import zipfile

from tests.windows_teardown import cleanup_temporary_directory, temporary_root


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT_PATH = ROOT / "pyproject.toml"
PKG_INFO_PATH = ROOT / "ai_context_framework.egg-info" / "PKG-INFO"
SOURCES_PATH = ROOT / "ai_context_framework.egg-info" / "SOURCES.txt"


class ReleaseLicenseMetadataTests(unittest.TestCase):
    def test_pyproject_declares_pep_639_license(self):
        pyproject = PYPROJECT_PATH.read_text(encoding="utf-8")
        self.assertRegex(pyproject, r'(?m)^license = "MIT"$')
        self.assertRegex(pyproject, r'(?m)^license-files = \["LICENSE"\]$')

    def test_build_backend_requires_pep_639_capable_setuptools(self):
        pyproject = PYPROJECT_PATH.read_text(encoding="utf-8")
        match = re.search(r"(?ms)\[build-system\].*?^requires = \[([^\]]*)\]", pyproject)
        self.assertIsNotNone(match, "pyproject.toml is missing [build-system] requires")
        requirements = [item.strip().strip('"') for item in match.group(1).split(",") if item.strip()]
        setuptools_bounds = [item for item in requirements if item.startswith("setuptools")]
        self.assertEqual(len(setuptools_bounds), 1, "build-system must pin setuptools once")
        bound = re.search(r"setuptools>=([0-9][0-9.]*)", setuptools_bounds[0])
        self.assertIsNotNone(bound, "setuptools requirement must carry an explicit lower bound")
        version = tuple(int(part) for part in bound.group(1).split("."))
        self.assertGreaterEqual(version, (77, 0, 3))

    def test_egg_info_records_deterministic_license_metadata(self):
        pkg_info = PKG_INFO_PATH.read_text(encoding="utf-8")
        self.assertRegex(pkg_info, r"(?m)^License-Expression: MIT$")
        self.assertRegex(pkg_info, r"(?m)^License-File: LICENSE$")
        self.assertIn("LICENSE", SOURCES_PATH.read_text(encoding="utf-8").splitlines())

    def test_built_artifacts_carry_mit_license(self):
        if shutil.which("uv") is None:
            self.skipTest("uv is required to build release artifacts")
        if os.environ.get("ACF_SKIP_ARTIFACT_BUILD"):
            self.skipTest("ACF_SKIP_ARTIFACT_BUILD is set; artifact build skipped")

        temporary = temporary_root(prefix="acf-license-build-")
        try:
            output_dir = pathlib.Path(temporary.name)
            subprocess.run(
                ["uv", "build", "--no-sources", "--out-dir", str(output_dir)],
                cwd=str(ROOT),
                check=True,
                capture_output=True,
                text=True,
                timeout=900,
            )
            wheels = sorted(output_dir.glob("ai_context_framework-*.whl"))
            sdists = sorted(output_dir.glob("ai_context_framework-*.tar.gz"))
            self.assertEqual(len(wheels), 1, "expected exactly one built wheel")
            self.assertEqual(len(sdists), 1, "expected exactly one built sdist")
            self._assert_wheel_license(wheels[0])
            self._assert_sdist_license(sdists[0])
        finally:
            cleanup_temporary_directory(temporary)

    def _assert_wheel_license(self, wheel_path: pathlib.Path) -> None:
        with zipfile.ZipFile(wheel_path) as wheel:
            names = wheel.namelist()
            metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
            self.assertEqual(len(metadata_names), 1, "wheel must contain exactly one METADATA")
            metadata = wheel.read(metadata_names[0]).decode("utf-8")
            # Wheel METADATA is CRLF-encoded, so compare on splitlines instead of anchors.
            self.assertIn("License-Expression: MIT", metadata.splitlines())

            license_names = [name for name in names if name.endswith(".dist-info/licenses/LICENSE")]
            self.assertEqual(len(license_names), 1, "wheel must ship dist-info/licenses/LICENSE")
            self.assertTrue(wheel.read(license_names[0]).strip(), "shipped LICENSE must not be empty")

    def _assert_sdist_license(self, sdist_path: pathlib.Path) -> None:
        with tarfile.open(sdist_path) as sdist:
            names = sdist.getnames()
        root_license = [name for name in names if name.count("/") == 1 and name.endswith("/LICENSE")]
        self.assertEqual(len(root_license), 1, "sdist must ship a top-level LICENSE")


if __name__ == "__main__":
    unittest.main()
