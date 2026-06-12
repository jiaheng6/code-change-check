from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from build_release import build_standard_package
from build_runtime_manifest import validate_runtime_manifest


class ReleasePackageTest(unittest.TestCase):
    def test_standard_skill_zip_contains_analyzer_and_manifest(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = build_standard_package(root, Path(temp_dir))
            with zipfile.ZipFile(archive) as handle:
                names = set(handle.namelist())

        self.assertIn("SKILL.md", names)
        self.assertIn("assets/runtime-manifest.json", names)
        self.assertIn("tools/java-analyzer/dist/java-analyzer.jar", names)
        self.assertFalse(any(name.endswith("node.exe") for name in names))

    def test_every_runtime_artifact_has_digest(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "assets" / "runtime-manifest.json").read_text(encoding="utf-8"))

        errors = validate_runtime_manifest(manifest)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
