from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def load_tool_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "code_change_check.py"
    spec = importlib.util.spec_from_file_location("code_change_check", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["code_change_check"] = module
    spec.loader.exec_module(module)
    return module


class ContractTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool_module()

    def test_extract_contracts_from_text_keeps_file_and_line(self):
        text = "\n".join(
            [
                "# 契约",
                "内部服务调用必须使用 internalBaseUrl。",
                "普通说明。",
                "PaymentClient.createOrder 参数顺序为 amount, currency, userId。",
            ]
        )

        contracts = self.tool.extract_contracts_from_text("docs/contracts.md", text)

        self.assertEqual(contracts[0]["id"], "C1")
        self.assertEqual(contracts[0]["source"], "contract-file")
        self.assertEqual(contracts[0]["file"], "docs/contracts.md")
        self.assertEqual(contracts[0]["line"], 2)
        self.assertIn("internalBaseUrl", contracts[0]["text"])
        self.assertEqual(contracts[1]["line"], 4)

    def test_extract_contracts_from_existing_code_detects_common_patterns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            source = project / "src" / "payment.ts"
            source.parent.mkdir()
            source.write_text(
                "\n".join(
                    [
                        "const baseUrl = config.internalBaseUrl;",
                        "await PaymentClient.createOrder(amount, currency, userId);",
                        "await db.order.update({ tenantId, status });",
                    ]
                ),
                encoding="utf-8",
            )

            contracts = self.tool.extract_contracts_from_existing_code(project, ["src/payment.ts"])

        contract_text = "\n".join(item["text"] for item in contracts)
        self.assertIn("internalBaseUrl", contract_text)
        self.assertIn("PaymentClient.createOrder", contract_text)
        self.assertIn("tenantId", contract_text)

    def test_extract_contracts_from_existing_code_detects_multiline_call_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            source = project / "src" / "order.ts"
            source.parent.mkdir()
            source.write_text(
                "\n".join(
                    [
                        "await OrderClient.create(",
                        "  orderId,",
                        "  tenantId,",
                        "  payload,",
                        ");",
                    ]
                ),
                encoding="utf-8",
            )

            contracts = self.tool.extract_contracts_from_existing_code(project, ["src/order.ts"])

        call_contract = next(item for item in contracts if item["kind"] == "call-shape")
        self.assertIn("OrderClient.create", call_contract["text"])
        self.assertIn("参数数量 3", call_contract["text"])
        self.assertIn("tenantId", call_contract["text"])

    def test_choose_contract_source_maps_labels_to_source(self):
        selected = self.tool.resolve_contract_source_selection(
            ["从旧代码自动提取", "使用指定契约文件"]
        )

        self.assertEqual(selected, "both")

    def test_extract_contracts_from_previous_git_code_uses_parent_commit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=project, check=True, stdout=subprocess.PIPE)
            source = project / "client.ts"
            source.write_text("const baseUrl = config.internalBaseUrl;\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=project, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "旧版本"],
                cwd=project,
                check=True,
                stdout=subprocess.PIPE,
            )
            source.write_text("const baseUrl = config.publicBaseUrl;\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=project, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "新版本"],
                cwd=project,
                check=True,
                stdout=subprocess.PIPE,
            )
            new_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()
            changes = {
                "source": "git",
                "range": "interactive-selected-commits",
                "selected_commits": [{"id": new_commit}],
                "changed_files": ["client.ts"],
            }

            contracts = self.tool.extract_contracts_from_previous_code(project, changes)

        contract_text = "\n".join(item["text"] for item in contracts)
        self.assertIn("internalBaseUrl", contract_text)
        self.assertNotIn("publicBaseUrl", contract_text)

    def test_collect_business_contracts_does_not_treat_new_code_as_old_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=project, check=True, stdout=subprocess.PIPE)
            source = project / "client.ts"
            source.write_text("const value = 1;\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=project, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "旧版本"],
                cwd=project,
                check=True,
                stdout=subprocess.PIPE,
            )
            source.write_text("const baseUrl = config.publicBaseUrl;\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=project, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "新版本"],
                cwd=project,
                check=True,
                stdout=subprocess.PIPE,
            )
            new_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()
            changes = {
                "source": "git",
                "range": "interactive-selected-commits",
                "selected_commits": [{"id": new_commit}],
                "changed_files": ["client.ts"],
            }

            _, contracts = self.tool.collect_business_contracts(project, "existing-code", [], changes)

        self.assertEqual(contracts, [])

    def test_extract_contracts_from_snapshot_baseline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before"
            after = root / "after"
            before.mkdir()
            after.mkdir()
            (before / "client.ts").write_text("const baseUrl = config.internalBaseUrl;\n", encoding="utf-8")
            (after / "client.ts").write_text("const baseUrl = config.publicBaseUrl;\n", encoding="utf-8")
            changes = {
                "source": "snapshot",
                "range": f"{before}..{after}",
                "changed_files": ["client.ts"],
            }

            contracts = self.tool.extract_contracts_from_previous_code(after, changes)

        contract_text = "\n".join(item["text"] for item in contracts)
        self.assertIn("internalBaseUrl", contract_text)
        self.assertNotIn("publicBaseUrl", contract_text)

    def test_git_range_does_not_include_untracked_working_tree_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=project, check=True, stdout=subprocess.PIPE)
            source = project / "client.ts"
            source.write_text("const value = 1;\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=project, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "旧版本"],
                cwd=project,
                check=True,
                stdout=subprocess.PIPE,
            )
            source.write_text("const value = 2;\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=project, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "新版本"],
                cwd=project,
                check=True,
                stdout=subprocess.PIPE,
            )
            (project / "untracked.ts").write_text("const value = 3;\n", encoding="utf-8")

            changes = self.tool.collect_git_changes(project, "HEAD~1", "HEAD")

        self.assertEqual(changes["changed_files"], ["client.ts"])

    def test_confirm_business_contracts_keeps_selected_candidates(self):
        contracts = [
            {
                "id": "C1",
                "source": "contract-file",
                "file": "docs/contracts.md",
                "line": 2,
                "kind": "text-rule",
                "text": "内部调用必须走 internalBaseUrl",
            },
            {
                "id": "C2",
                "source": "existing-code-baseline:abc",
                "file": "client.ts",
                "line": 8,
                "kind": "call-shape",
                "text": "PaymentClient.createOrder 参数数量 3",
            },
        ]

        selected = self.tool.confirm_business_contracts(
            contracts,
            choose_contracts=lambda labels: [labels[1]],
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["id"], "C2")

    def test_strict_contract_discovery_only_uses_explicit_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            selected = project / "docs" / "selected"
            selected.mkdir(parents=True)
            (selected / "api.json").write_text('{"ok": true}\n', encoding="utf-8")
            ignored = project / "contracts"
            ignored.mkdir()
            (ignored / "ignored.md").write_text("必须忽略\n", encoding="utf-8")

            files = self.tool.discover_contract_files(
                project,
                [str(selected)],
                strict=True,
            )

        self.assertEqual([path.name for path in files], ["api.json"])


if __name__ == "__main__":
    unittest.main()
