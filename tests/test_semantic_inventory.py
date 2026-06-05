from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


def load_semantic_module():
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    path = scripts / "semantic_inventory.py"
    spec = importlib.util.spec_from_file_location("semantic_inventory", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SemanticInventoryTest(unittest.TestCase):
    def setUp(self):
        self.semantic = load_semantic_module()

    def test_split_arguments_handles_nested_calls_and_objects(self):
        arguments = self.semantic.split_arguments(
            "tenantId, buildOrder(user.id, amount), { retry: 3, tags: ['a', 'b'] }"
        )

        self.assertEqual(
            arguments,
            [
                "tenantId",
                "buildOrder(user.id, amount)",
                "{ retry: 3, tags: ['a', 'b'] }",
            ],
        )

    def test_extract_semantic_inventory_finds_calls_addressing_tenant_and_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            source = project / "src" / "order.ts"
            source.parent.mkdir()
            source.write_text(
                "\n".join(
                    [
                        "const baseUrl = config.internalBaseUrl;",
                        "await OrderClient.create(tenantId, buildOrder(user.id, amount));",
                        "await db.order.update({ tenantId, status });",
                    ]
                ),
                encoding="utf-8",
            )

            inventory = self.semantic.extract_semantic_inventory(project)

        calls = [item for item in inventory["items"] if item["kind"] == "call"]
        addressing = [item for item in inventory["items"] if item["kind"] == "addressing"]
        fields = [item for item in inventory["items"] if item["kind"] == "field"]
        self.assertTrue(any(item["symbol"] == "OrderClient.create" and item["argument_count"] == 2 for item in calls))
        self.assertTrue(any(item["value"] == "internal" for item in addressing))
        self.assertTrue(any(item["symbol"] == "tenantId" for item in fields))
        self.assertTrue(any(item["symbol"] == "status" for item in fields))

    def test_extract_semantic_inventory_reports_unreadable_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            source = project / "app.py"
            source.write_text("client.call(value)\n", encoding="utf-8")

            with patch.object(self.semantic.Path, "read_text", side_effect=OSError("无法读取")):
                inventory = self.semantic.extract_semantic_inventory(project)

        self.assertEqual(inventory["status"], "partial-failure")
        self.assertIn("无法读取", inventory["errors"][0])

    def test_compare_inventory_detects_call_argument_change(self):
        baseline = {
            "status": "success",
            "items": [
                {
                    "kind": "call",
                    "file": "src/order.ts",
                    "line": 4,
                    "symbol": "OrderClient.create",
                    "argument_count": 3,
                    "arguments": ["tenantId", "orderId", "amount"],
                }
            ],
        }
        target = {
            "status": "success",
            "items": [
                {
                    "kind": "call",
                    "file": "src/order.ts",
                    "line": 8,
                    "symbol": "OrderClient.create",
                    "argument_count": 2,
                    "arguments": ["orderId", "amount"],
                }
            ],
        }

        result = self.semantic.compare_semantic_inventories(baseline, target)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["changes"][0]["type"], "call-arguments-changed")
        self.assertEqual(result["changes"][0]["severity"], "critical")
        self.assertIn("tenantId", result["changes"][0]["removed"])

    def test_compare_inventory_detects_internal_to_public_address_change(self):
        baseline = {
            "status": "success",
            "items": [
                {
                    "kind": "addressing",
                    "file": "src/client.ts",
                    "line": 2,
                    "symbol": "base-url",
                    "value": "internal",
                }
            ],
        }
        target = {
            "status": "success",
            "items": [
                {
                    "kind": "addressing",
                    "file": "src/client.ts",
                    "line": 2,
                    "symbol": "base-url",
                    "value": "public",
                }
            ],
        }

        result = self.semantic.compare_semantic_inventories(baseline, target)

        self.assertEqual(result["changes"][0]["type"], "addressing-changed")
        self.assertEqual(result["changes"][0]["severity"], "critical")

    def test_compare_inventory_detects_removed_tenant_field(self):
        baseline = {
            "status": "success",
            "items": [
                {
                    "kind": "field",
                    "file": "src/order.ts",
                    "line": 3,
                    "symbol": "tenantId",
                    "value": "tenant",
                }
            ],
        }
        target = {"status": "success", "items": []}

        result = self.semantic.compare_semantic_inventories(baseline, target)

        self.assertEqual(result["changes"][0]["type"], "tenant-field-removed")
        self.assertEqual(result["changes"][0]["severity"], "critical")

    def test_compare_inventory_refuses_diff_when_one_side_failed(self):
        result = self.semantic.compare_semantic_inventories(
            {"status": "failed", "items": [], "message": "baseline 失败"},
            {"status": "success", "items": [], "message": "target 完成"},
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["changes"], [])

    def test_merge_inventories_prefers_lightweight_call_arguments(self):
        lightweight = {
            "status": "success",
            "engine": "lightweight",
            "items": [
                {
                    "kind": "call",
                    "file": "src/order.ts",
                    "line": 2,
                    "symbol": "OrderClient.create",
                    "argument_count": 2,
                    "arguments": ["tenantId", "orderId"],
                }
            ],
        }
        codeql = {
            "status": "success",
            "engine": "codeql",
            "items": [
                {
                    "kind": "call",
                    "file": "src/order.ts",
                    "line": 2,
                    "symbol": "OrderClient.create",
                    "argument_count": 2,
                    "arguments": [],
                    "engine": "codeql",
                },
                {
                    "kind": "call",
                    "file": "src/hidden.ts",
                    "line": 5,
                    "symbol": "HiddenClient.call",
                    "argument_count": 1,
                    "arguments": [],
                    "engine": "codeql",
                },
            ],
        }

        merged = self.semantic.merge_semantic_inventories(lightweight, codeql)

        self.assertEqual(len(merged["items"]), 2)
        order = next(item for item in merged["items"] if item["symbol"] == "OrderClient.create")
        self.assertEqual(order["arguments"], ["tenantId", "orderId"])

    def test_merge_inventories_keeps_partial_lightweight_status(self):
        lightweight = {
            "status": "partial-failure",
            "engine": "lightweight",
            "message": "部分文件无法提取",
            "errors": ["src/hidden.ts: 无法读取"],
            "items": [],
        }
        codeql = {
            "status": "success",
            "engine": "codeql",
            "message": "CodeQL 查询完成",
            "errors": [],
            "items": [],
        }

        merged = self.semantic.merge_semantic_inventories(lightweight, codeql)

        self.assertEqual(merged["status"], "partial-failure")


if __name__ == "__main__":
    unittest.main()
