from __future__ import annotations

from pathlib import Path
import sys
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from audit_coverage import assess_audit_coverage


class AuditCoverageTest(unittest.TestCase):
    def test_complete_java_analysis_allows_success(self):
        result = assess_audit_coverage(
            changes={"source": "git", "range": "main..HEAD"},
            contract_check={"total_contracts": 0, "checked_contracts": 0, "unchecked_contracts": []},
            java_analysis={
                "status": "success",
                "coverage": {
                    "java_files_total": 2,
                    "java_files_parsed": 2,
                    "core_complete": True,
                    "graph_complete": True,
                    "comparison_complete": True,
                },
            },
            role_issues=[],
            missing_referenced_artifacts=[],
            manual_review_obligations=[],
        )

        self.assertEqual(result["status"], "success")

    def test_missing_baseline_marks_partial(self):
        result = assess_audit_coverage(
            changes={"source": "snapshot", "range": "current"},
            contract_check={"total_contracts": 0, "checked_contracts": 0, "unchecked_contracts": []},
            java_analysis={"status": "disabled", "coverage": {}},
            role_issues=[],
            missing_referenced_artifacts=[],
            manual_review_obligations=[],
        )

        self.assertEqual(result["status"], "partial")


if __name__ == "__main__":
    unittest.main()
