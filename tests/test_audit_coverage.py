from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


def load_module(name: str):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    path = scripts / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class AuditCoverageTest(unittest.TestCase):
    def setUp(self):
        self.coverage = load_module("audit_coverage")

    def test_discovers_json_artifacts_referenced_by_selected_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "backend"
            spec = root / "openspec" / "changes" / "selected" / "proposal.md"
            contract = root / "docs" / "api-mock-backup" / "safetyInspection.json"
            project.mkdir()
            spec.parent.mkdir(parents=True)
            contract.parent.mkdir(parents=True)
            spec.write_text(
                "响应必须与 `docs/api-mock-backup/*.json` 完全一致。\n",
                encoding="utf-8",
            )
            contract.write_text('{"data": {}}\n', encoding="utf-8")

            result = self.coverage.discover_referenced_json_artifacts(
                project,
                [spec],
                [],
            )

        self.assertEqual(result["referenced"][0]["path"], str(contract.resolve()))
        self.assertEqual(result["missing"][0]["path"], str(contract.resolve()))
        self.assertEqual(result["missing"][0]["reference"], "docs/api-mock-backup/*.json")

    def test_rejects_response_snapshot_with_same_content_as_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contract = root / "contracts" / "safetyInspection.json"
            response = root / "responses" / "safetyInspection.json"
            contract.parent.mkdir()
            response.parent.mkdir()
            contract.write_text('{"data":{"ok":true}}\n', encoding="utf-8")
            response.write_text('{"data":{"ok":true}}\n', encoding="utf-8")

            result = self.coverage.validate_contract_snapshot_roles([contract], [response])

        self.assertEqual(result["valid_snapshot_files"], [])
        self.assertEqual(result["issues"][0]["type"], "same-content")
        self.assertIn("虚假通过", result["issues"][0]["message"])

    def test_builds_manual_review_obligation_with_related_code_locations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            source = project / "src" / "OverviewServiceImpl.java"
            source.parent.mkdir()
            source.write_text(
                "\n".join(
                    [
                        "class OverviewServiceImpl {",
                        "  Map safetyInspection() {",
                        '    result.put("handleRate", buildValue("错误标签"));',
                        "  }",
                        "}",
                    ]
                ),
                encoding="utf-8",
            )
            contracts = [
                {
                    "id": "C1",
                    "kind": "text-rule",
                    "file": "proposal.md",
                    "line": 12,
                    "text": "/safetyInspection 的 handleRate 字段必须保持兼容。",
                }
            ]
            unchecked = [
                {
                    "contract_id": "C1",
                    "kind": "text-rule",
                    "file": "proposal.md",
                    "line": 12,
                    "reason": "文本契约无法自动执行。",
                }
            ]

            obligations = self.coverage.build_manual_review_obligations(
                project,
                unchecked,
                contracts,
            )

        self.assertEqual(len(obligations), 1)
        self.assertIn("safetyInspection", obligations[0]["tokens"])
        self.assertEqual(obligations[0]["candidates"][0]["file"], "src/OverviewServiceImpl.java")
        self.assertIn(obligations[0]["candidates"][0]["line"], {2, 3})

    def test_zero_checked_contracts_blocks_audit_coverage(self):
        result = self.coverage.assess_audit_coverage(
            changes={"source": "snapshot", "range": "current"},
            contract_check={
                "total_contracts": 59,
                "checked_contracts": 0,
                "unchecked_contracts": [{"contract_id": "C1"}],
            },
            codeql={"enabled": True, "status": "failed"},
            role_issues=[],
            missing_referenced_artifacts=[],
            manual_review_obligations=[{"contract_id": "C1"}],
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["contract_coverage_percent"], 0)
        self.assertTrue(any(item["code"] == "zero-contract-coverage" for item in result["reasons"]))
        self.assertTrue(any(item["code"] == "full-scan-no-baseline" for item in result["reasons"]))
        self.assertTrue(any(item["code"] == "codeql-incomplete" for item in result["reasons"]))


if __name__ == "__main__":
    unittest.main()
