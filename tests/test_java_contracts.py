from __future__ import annotations

from pathlib import Path
import sys
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from audit_coverage import assess_audit_coverage
from contract_rules import evaluate_contracts


class JavaContractTest(unittest.TestCase):
    def test_field_mapping_contract_checks_expected_value_source(self):
        contract = {
            "id": "mapping-1",
            "kind": "field-mapping",
            "file": "contract.md",
            "line": 1,
            "slot": "fireEvent.count.value",
            "expected_source": "statistics.getTotalFireAlarms()",
            "text": "字段映射必须保持不变",
        }
        inventory = {
            "status": "success",
            "items": [
                {
                    "kind": "field-mapping",
                    "file": "SafetyService.java",
                    "line": 10,
                    "slot": "fireEvent.count.value",
                    "source_expression": "statistics.getFireSafetyIncidents()",
                }
            ],
        }

        result = evaluate_contracts([contract], inventory)

        self.assertEqual(result["violations"][0]["type"], "contract-field-mapping")
        self.assertEqual(result["violations"][0]["severity"], "critical")

    def test_zero_parsed_java_files_blocks_coverage(self):
        result = assess_audit_coverage(
            changes={"source": "git", "range": "main..HEAD"},
            contract_check={"total_contracts": 0, "checked_contracts": 0, "unchecked_contracts": []},
            java_analysis={"status": "blocked", "coverage": {"java_files_total": 1, "java_files_parsed": 0}},
            role_issues=[],
            missing_referenced_artifacts=[],
            manual_review_obligations=[],
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("java-analysis-blocked", {item["code"] for item in result["reasons"]})

    def test_graph_failure_marks_coverage_partial(self):
        result = assess_audit_coverage(
            changes={"source": "git", "range": "main..HEAD"},
            contract_check={"total_contracts": 0, "checked_contracts": 0, "unchecked_contracts": []},
            java_analysis={
                "status": "partial",
                "coverage": {
                    "java_files_total": 1,
                    "java_files_parsed": 1,
                    "core_complete": True,
                    "graph_complete": False,
                    "comparison_complete": True,
                },
            },
            role_issues=[],
            missing_referenced_artifacts=[],
            manual_review_obligations=[],
        )

        self.assertEqual(result["status"], "partial")
        self.assertIn("code-graph-incomplete", {item["code"] for item in result["reasons"]})


if __name__ == "__main__":
    unittest.main()
