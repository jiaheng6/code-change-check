from __future__ import annotations

import importlib.util
import json
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


class ContractRulesTest(unittest.TestCase):
    def setUp(self):
        self.rules = load_module("contract_rules")

    def test_addressing_contract_flags_internal_to_public_target(self):
        contracts = [
            {
                "id": "C1",
                "source": "existing-code-baseline:abc",
                "file": "src/client.ts",
                "line": 2,
                "kind": "addressing",
                "text": "已有代码使用 internalBaseUrl 作为内部寻址线索：const url = config.internalBaseUrl;",
            }
        ]
        inventory = {
            "status": "success",
            "items": [
                {
                    "kind": "addressing",
                    "file": "src/client.ts",
                    "line": 4,
                    "symbol": "base-url",
                    "value": "public",
                    "token": "publicBaseUrl",
                }
            ],
        }

        result = self.rules.evaluate_contracts(contracts, inventory)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["violations"][0]["type"], "contract-addressing")
        self.assertEqual(result["violations"][0]["severity"], "critical")
        self.assertIn("internalBaseUrl", result["violations"][0]["message"])

    def test_call_shape_contract_flags_removed_tenant_argument(self):
        contracts = [
            {
                "id": "C2",
                "source": "existing-code-baseline:abc",
                "file": "src/order.ts",
                "line": 8,
                "kind": "call-shape",
                "text": "已有调用约定 OrderClient.create 参数数量 3，参数：orderId, tenantId, payload",
            }
        ]
        inventory = {
            "status": "success",
            "items": [
                {
                    "kind": "call",
                    "file": "src/order.ts",
                    "line": 12,
                    "symbol": "OrderClient.create",
                    "argument_count": 2,
                    "arguments": ["orderId", "payload"],
                }
            ],
        }

        result = self.rules.evaluate_contracts(contracts, inventory)

        self.assertEqual(result["violations"][0]["type"], "contract-call-shape")
        self.assertEqual(result["violations"][0]["severity"], "critical")
        self.assertIn("tenantId", result["violations"][0]["message"])
        self.assertEqual(result["violations"][0]["difference"]["kind"], "call-shape")
        self.assertEqual(result["violations"][0]["difference"]["missing"], ["tenantId"])
        self.assertEqual(result["checked_contracts"], 1)
        self.assertEqual(result["unchecked_contracts"], [])

    def test_json_shape_contract_compares_matching_response_snapshot(self):
        contracts = [
            {
                "id": "C5",
                "source": "contract-file",
                "file": "docs/contracts/safetyInspection.json",
                "line": 1,
                "kind": "json-shape",
                "match_key": "safetyinspection",
                "text": "JSON 响应形状契约",
                "shape": {
                    "paths": [
                        "data",
                        "data.event",
                        "data.event.handleRate",
                        "data.event.handleRate.label",
                        "data.list",
                        "data.list[]",
                    ]
                },
            }
        ]
        responses = {
            "safetyinspection": {
                "file": "responses/safetyInspection.json",
                "paths": ["data", "data.event", "data.event.handleRate"],
            }
        }

        result = self.rules.evaluate_contracts(
            contracts,
            {"status": "success", "items": []},
            responses,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["checked_contracts"], 1)
        self.assertEqual(result["violations"][0]["type"], "contract-json-shape")
        self.assertEqual(
            result["violations"][0]["difference"]["missing"],
            ["data.event.handleRate.label", "data.list", "data.list[]"],
        )

    def test_json_shape_contract_without_snapshot_is_reported_unchecked(self):
        contracts = [
            {
                "id": "C6",
                "source": "contract-file",
                "file": "docs/contracts/safetyInspection.json",
                "line": 1,
                "kind": "json-shape",
                "match_key": "safetyinspection",
                "text": "JSON 响应形状契约",
                "shape": {"paths": ["data.event.handleRate.label"]},
            }
        ]

        result = self.rules.evaluate_contracts(contracts, None)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["total_contracts"], 1)
        self.assertEqual(result["checked_contracts"], 0)
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["unchecked_contracts"][0]["contract_id"], "C6")
        self.assertIn("响应快照", result["unchecked_contracts"][0]["reason"])

    def test_json_shape_contract_still_runs_when_semantic_inventory_failed(self):
        contracts = [
            {
                "id": "C8",
                "source": "contract-file",
                "file": "docs/contracts/safetyInspection.json",
                "line": 1,
                "kind": "json-shape",
                "match_key": "safetyinspection",
                "text": "JSON 响应形状契约",
                "shape": {"paths": ["data", "data.list", "data.list[]"]},
            }
        ]
        responses = {
            "safetyinspection": {
                "file": "responses/safetyInspection.json",
                "paths": ["data"],
            }
        }

        result = self.rules.evaluate_contracts(
            contracts,
            {"status": "failed", "message": "代码语义提取失败", "items": []},
            responses,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["checked_contracts"], 1)
        self.assertIn("data.list[]", result["differences"][0]["missing"])

    def test_json_shape_contract_detects_stable_label_value_change(self):
        contracts = [
            {
                "id": "C9",
                "source": "contract-file",
                "file": "docs/contracts/safetyInspection.json",
                "line": 1,
                "kind": "json-shape",
                "match_key": "safetyinspection",
                "text": "JSON 响应形状契约",
                "shape": {
                    "paths": ["data", "data.event", "data.event.handleRate", "data.event.handleRate.label"],
                    "constants": {"data.event.handleRate.label": "事件处置率"},
                },
            }
        ]
        responses = {
            "safetyinspection": {
                "file": "responses/safetyInspection.json",
                "paths": ["data", "data.event", "data.event.handleRate", "data.event.handleRate.label"],
                "constants": {"data.event.handleRate.label": "消防隐患整改处置率"},
            }
        }

        result = self.rules.evaluate_contracts(
            contracts,
            {"status": "success", "items": []},
            responses,
        )

        self.assertEqual(result["checked_contracts"], 1)
        self.assertEqual(result["violations"][0]["type"], "contract-json-shape")
        self.assertEqual(
            result["violations"][0]["difference"]["changed"][0],
            {
                "path": "data.event.handleRate.label",
                "expected": "事件处置率",
                "actual": "消防隐患整改处置率",
            },
        )

    def test_unparseable_text_contract_is_not_counted_as_checked(self):
        contracts = [
            {
                "id": "C7",
                "source": "contract-file",
                "file": "docs/contracts.md",
                "line": 1,
                "kind": "text-rule",
                "text": "接口必须兼容旧前端展示。",
            }
        ]

        result = self.rules.evaluate_contracts(contracts, {"status": "success", "items": []})

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["checked_contracts"], 0)
        self.assertEqual(len(result["unchecked_contracts"]), 1)

    def test_text_rule_contract_applies_project_wide_for_internal_addressing(self):
        contracts = [
            {
                "id": "C3",
                "source": "contract-file",
                "file": "docs/contracts.md",
                "line": 2,
                "kind": "text-rule",
                "text": "内部服务调用必须使用 internalBaseUrl，禁止使用 publicBaseUrl。",
            }
        ]
        inventory = {
            "status": "success",
            "items": [
                {
                    "kind": "addressing",
                    "file": "src/payment.ts",
                    "line": 3,
                    "symbol": "base-url",
                    "value": "public",
                    "token": "publicBaseUrl",
                }
            ],
        }

        result = self.rules.evaluate_contracts(contracts, inventory)

        self.assertEqual(len(result["violations"]), 1)
        self.assertEqual(result["violations"][0]["file"], "src/payment.ts")

    def test_text_rule_contract_uses_addressing_token_even_without_chinese_keyword(self):
        contracts = [
            {
                "id": "C4",
                "source": "contract-file",
                "file": "docs/contracts.md",
                "line": 3,
                "kind": "text-rule",
                "text": "internalBaseUrl / publicBaseUrl",
            }
        ]
        inventory = {
            "status": "success",
            "items": [
                {
                    "kind": "addressing",
                    "file": "src/client.ts",
                    "line": 5,
                    "symbol": "base-url",
                    "value": "public",
                    "token": "publicBaseUrl",
                }
            ],
        }

        result = self.rules.evaluate_contracts(contracts, inventory)

        self.assertEqual(result["violations"][0]["type"], "contract-addressing")

    def test_evaluate_contracts_reports_failed_inventory_without_false_pass(self):
        result = self.rules.evaluate_contracts(
            [
                {
                    "id": "C1",
                    "source": "contract-file",
                    "file": "docs/contracts.md",
                    "line": 1,
                    "kind": "text-rule",
                    "text": "内部服务调用必须使用 internalBaseUrl。",
                }
            ],
            {"status": "failed", "message": "无法读取项目", "items": []},
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["violations"], [])


class ContractRulesIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_module("code_change_check")

    def test_main_merges_contract_violations_into_evidence_and_report_without_codeql(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            output = root / "output"
            project.mkdir()
            (project / "client.ts").write_text("const url = config.publicBaseUrl;\n", encoding="utf-8")
            contract = project / "contracts.md"
            contract.write_text("内部服务调用必须使用 internalBaseUrl，禁止使用 publicBaseUrl。\n", encoding="utf-8")

            exit_code = self.tool.main(
                [
                    "--project",
                    str(project),
                    "--contract",
                    str(contract),
                    "--contract-source",
                    "file",
                    "--output",
                    str(output),
                ]
            )

            evidence = (output / "code-change-check-evidence.json").read_text(encoding="utf-8")
            report = (output / "code-change-check-report.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("contract:contract-addressing", evidence)
        self.assertIn("## 业务契约执行结果", report)

    def test_main_does_not_extract_contract_inventory_when_contracts_disabled(self):
        self.tool.extract_semantic_inventory = lambda project: (_ for _ in ()).throw(
            AssertionError("不应提取语义清单")
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            output = Path(temp_dir) / "output"
            project.mkdir()
            (project / "client.ts").write_text("const value = 1;\n", encoding="utf-8")

            exit_code = self.tool.main(
                ["--project", str(project), "--no-contract", "--output", str(output)]
            )

        self.assertEqual(exit_code, 0)

    def test_main_compares_json_contract_with_response_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            output = root / "output"
            project.mkdir()
            contract = project / "contracts" / "safetyInspection.json"
            response = project / "responses" / "safetyInspection.json"
            contract.parent.mkdir()
            response.parent.mkdir()
            contract.write_text(
                '{"data":{"event":{"handleRate":{"label":"事件处置率"}},"list":[{"id":1}]}}',
                encoding="utf-8",
            )
            response.write_text('{"data":{"event":{"handleRate":{}}}}\n', encoding="utf-8")

            exit_code = self.tool.main(
                [
                    "--project",
                    str(project),
                    "--contract",
                    str(contract),
                    "--strict-contract",
                    "--contract-source",
                    "file",
                    "--response-snapshot",
                    str(response),
                    "--no-codeql",
                    "--no-interactive",
                    "--output",
                    str(output),
                ]
            )
            evidence = json.loads(
                (output / "code-change-check-evidence.json").read_text(encoding="utf-8")
            )
            report = (output / "code-change-check-report.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(evidence["business_contract_check"]["checked_contracts"], 1)
        difference = evidence["business_contract_check"]["differences"][0]
        self.assertEqual(difference["kind"], "json-shape")
        self.assertIn("data.list[]", difference["missing"])
        self.assertIn("结构化差异", report)


if __name__ == "__main__":
    unittest.main()
