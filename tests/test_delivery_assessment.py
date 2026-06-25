from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from delivery_assessment import build_delivery_assessment
from html_report import make_html_report


class DeliveryAssessmentTest(unittest.TestCase):
    def test_contract_violation_lowers_contract_and_delivery_scores(self):
        data = {
            "requirement_items": [
                {
                    "id": "R1",
                    "kind_label": "任务",
                    "file": "docs/spec.md",
                    "line": 3,
                    "text": "保持 fireEvent.count.value 字段来源不变",
                }
            ],
            "requirement_commit_mappings": [
                {"commit": {"id": "abc"}, "requirements": [{"id": "R1"}]}
            ],
            "business_contracts": [
                {
                    "id": "C1",
                    "kind": "field-mapping",
                    "file": "docs/contracts.md",
                    "line": 8,
                    "text": "fireEvent.count.value 必须来自 statistics.getTotalFireAlarms()",
                }
            ],
            "business_contract_check": {
                "status": "success",
                "total_contracts": 1,
                "checked_contracts": 1,
                "unchecked_contracts": [],
                "violations": [
                    {
                        "severity": "critical",
                        "type": "contract-field-mapping",
                        "message": "字段映射 fireEvent.count.value 的值来源不符合业务契约。",
                        "contract": {"id": "C1"},
                    }
                ],
            },
            "audit_coverage": {"status": "success", "reasons": []},
            "java_analysis": {
                "status": "success",
                "coverage": {
                    "core_complete": True,
                    "graph_complete": True,
                    "comparison_complete": True,
                },
                "target": {"code_graph": {"status": "success", "affected_tests": ["SafetyServiceTest"]}},
                "comparison": {
                    "status": "success",
                    "changes": [{"severity": "critical", "message": "字段值来源变化"}],
                },
            },
            "findings": [{"severity": "critical"}],
            "summary": {"by_severity": {"critical": 1}},
        }

        assessment = build_delivery_assessment(data)
        contract_row = next(row for row in assessment["rows"] if row["kind"] == "contract")

        self.assertLess(contract_row["scores"]["contract_correctness"]["score"], 60)
        self.assertLess(contract_row["scores"]["deliverability"]["score"], 60)
        self.assertEqual(contract_row["scores"]["contract_correctness"]["status"], "blocked")

    def test_html_report_renders_score_matrix_with_clickable_cells(self):
        data = {
            "generated_at": "2026-06-25T10:00:00",
            "project": "demo",
            "audit_plan": {},
            "changes": {"source": "snapshot", "range": "current", "changed_files": []},
            "specs": [],
            "contract_candidates": [],
            "business_contracts": [],
            "business_contract_check": {"status": "disabled", "unchecked_contracts": [], "violations": []},
            "manual_review_obligations": [],
            "audit_coverage": {"status": "success", "reasons": []},
            "java_analysis": {"status": "disabled", "coverage": {}, "target": {"code_graph": {}}, "comparison": {}},
            "findings": [],
            "suppressed_findings": [],
            "suppression_summary": {},
            "summary": {"by_severity": {}, "by_category": {}},
            "mermaid": "",
        }
        data["delivery_assessment"] = build_delivery_assessment(data)

        html = make_html_report(data)

        self.assertIn('id="delivery-assessment"', html)
        self.assertIn("可交付评分矩阵", html)
        self.assertIn('class="score-cell', html)
        self.assertIn('href="#delivery-detail-', html)


if __name__ == "__main__":
    unittest.main()
