from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from java_analysis import run_java_analysis


class JavaBusinessRiskIntegrationTest(unittest.TestCase):
    def test_known_field_mapping_getter_mismatch_is_critical(self):
        root = Path(__file__).resolve().parent / "fixtures" / "java-analysis" / "field-mapping"
        target = root / "after"
        baseline = root / "baseline"
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_java_analysis(
                target,
                {"source": "snapshot", "range": f"{baseline}..current", "changed_files": ["SafetyService.java"]},
                Path(temp_dir),
                baseline_path=baseline,
                graph_analyzer=lambda *args, **kwargs: {
                    "status": "success",
                    "callers": [],
                    "callees": [],
                    "impacts": [],
                    "affected_tests": [],
                    "errors": [],
                },
            )

        finding = next(item for item in result["findings"] if item["type"] == "field-mapping-source-changed")
        self.assertEqual(finding["severity"], "critical")
        self.assertEqual(finding["slot"], "fireEvent.count.value")


if __name__ == "__main__":
    unittest.main()
