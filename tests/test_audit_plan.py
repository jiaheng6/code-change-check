from __future__ import annotations

import importlib.util
import json
from pathlib import Path
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


class AuditPlanTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool_module()

    def test_audit_plan_round_trip_locks_confirmed_scope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "backend"
            spec_dir = root / "openspec" / "changes" / "selected"
            contract_dir = root / "docs" / "contracts"
            response = root / "responses" / "actual.json"
            project.mkdir()
            spec_dir.mkdir(parents=True)
            contract_dir.mkdir(parents=True)
            response.parent.mkdir(parents=True)
            response.write_text('{"ok": true}\n', encoding="utf-8")
            args = self.tool.parse_args(
                [
                    "--project",
                    str(project),
                    "--spec",
                    str(spec_dir),
                    "--strict-spec",
                    "--contract",
                    str(contract_dir),
                    "--strict-contract",
                    "--response-snapshot",
                    str(response),
                    "--include-support-findings",
                    "--contract-source",
                    "file",
                    "--scan-all",
                    "--codeql",
                    "--codeql-build-mode",
                    "autobuild",
                    "--no-interactive",
                ]
            )

            plan = self.tool.build_audit_plan(args)
            plan_path = root / "audit-plan.json"
            self.tool.save_audit_plan(plan_path, plan)
            self.tool.confirm_audit_plan(plan_path)
            loaded_args = self.tool.parse_args(["--audit-plan", str(plan_path)])
            self.tool.apply_audit_plan(loaded_args, self.tool.load_audit_plan(plan_path))

        self.assertEqual(loaded_args.project, str(project.resolve()))
        self.assertEqual(loaded_args.spec, [str(spec_dir.resolve())])
        self.assertTrue(loaded_args.strict_spec)
        self.assertEqual(loaded_args.contract, [str(contract_dir.resolve())])
        self.assertTrue(loaded_args.strict_contract)
        self.assertEqual(loaded_args.response_snapshot, [str(response.resolve())])
        self.assertTrue(loaded_args.include_support_findings)
        self.assertEqual(loaded_args.contract_source, "file")
        self.assertTrue(loaded_args.scan_all)
        self.assertTrue(loaded_args.codeql)
        self.assertEqual(loaded_args.codeql_build_mode, "autobuild")
        self.assertTrue(loaded_args.no_interactive)

    def test_main_save_audit_plan_exits_without_generating_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "backend"
            output = root / "output"
            plan_path = root / "audit-plan.json"
            project.mkdir()

            exit_code = self.tool.main(
                [
                    "--project",
                    str(project),
                    "--scan-all",
                    "--no-contract",
                    "--no-codeql",
                    "--no-interactive",
                    "--output",
                    str(output),
                    "--save-audit-plan",
                    str(plan_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(plan_path.exists())
            self.assertFalse(output.exists())

    def test_unconfirmed_audit_plan_cannot_be_applied(self):
        args = self.tool.parse_args([])
        plan = self.tool.build_audit_plan(args)

        with self.assertRaisesRegex(ValueError, "尚未确认"):
            self.tool.apply_audit_plan(args, plan)

    def test_confirm_audit_plan_marks_plan_confirmed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "audit-plan.json"
            self.tool.save_audit_plan(plan_path, self.tool.build_audit_plan(self.tool.parse_args([])))

            self.tool.confirm_audit_plan(plan_path)
            plan = self.tool.load_audit_plan(plan_path)

        self.assertTrue(plan["confirmed"])
        self.assertTrue(plan["confirmation_hash"])

    def test_confirmed_audit_plan_rejects_changes_after_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "audit-plan.json"
            self.tool.save_audit_plan(plan_path, self.tool.build_audit_plan(self.tool.parse_args([])))
            self.tool.confirm_audit_plan(plan_path)
            plan = self.tool.load_audit_plan(plan_path)
            plan["project"] = str((Path(temp_dir) / "other").resolve())
            self.tool.save_audit_plan(plan_path, plan)

            with self.assertRaisesRegex(ValueError, "确认后已被修改"):
                self.tool.apply_audit_plan(
                    self.tool.parse_args(["--audit-plan", str(plan_path)]),
                    self.tool.load_audit_plan(plan_path),
                )

    def test_confirmed_audit_plan_execution_records_effective_scope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "backend"
            spec_dir = root / "openspec" / "changes" / "selected"
            output = root / "output"
            plan_path = root / "audit-plan.json"
            project.mkdir()
            spec_dir.mkdir(parents=True)
            (project / "App.java").write_text("class App {}\n", encoding="utf-8")
            (spec_dir / "proposal.md").write_text("# 选中需求\n", encoding="utf-8")
            args = self.tool.parse_args(
                [
                    "--project",
                    str(project),
                    "--spec",
                    str(spec_dir),
                    "--strict-spec",
                    "--scan-all",
                    "--no-contract",
                    "--no-codeql",
                    "--no-interactive",
                    "--output",
                    str(output),
                ]
            )
            self.tool.save_audit_plan(plan_path, self.tool.build_audit_plan(args))
            self.tool.confirm_audit_plan(plan_path)

            exit_code = self.tool.main(["--audit-plan", str(plan_path)])
            evidence = json.loads(
                (output / "code-change-check-evidence.json").read_text(encoding="utf-8")
            )
            report = (output / "code-change-check-report.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(evidence["project"], str(project.resolve()))
        self.assertEqual([item["file"] for item in evidence["specs"]], [str((spec_dir / "proposal.md").resolve()).replace("\\", "/")])
        self.assertTrue(evidence["audit_plan"]["confirmed"])
        self.assertEqual(evidence["audit_plan"]["path"], str(plan_path.resolve()))
        self.assertTrue(evidence["audit_plan"]["effective"]["confirmed"])
        self.assertTrue(evidence["audit_plan"]["effective"]["confirmation_hash"])
        self.assertIn("已确认审计计划", report)

    def test_audit_plan_warns_about_missing_referenced_contracts_and_unsafe_modes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "backend"
            spec = root / "openspec" / "changes" / "selected"
            contract = root / "docs" / "api-mock-backup" / "safetyInspection.json"
            project.mkdir()
            spec.mkdir(parents=True)
            contract.parent.mkdir(parents=True)
            (project / "pom.xml").write_text("<project />\n", encoding="utf-8")
            (spec / "proposal.md").write_text(
                "响应必须与 `docs/api-mock-backup/*.json` 完全一致。\n",
                encoding="utf-8",
            )
            contract.write_text('{"data": {}}\n', encoding="utf-8")
            args = self.tool.parse_args(
                [
                    "--project",
                    str(project),
                    "--spec",
                    str(spec),
                    "--strict-spec",
                    "--contract",
                    str(spec),
                    "--strict-contract",
                    "--contract-source",
                    "file",
                    "--scan-all",
                    "--codeql",
                    "--codeql-build-mode",
                    "none",
                    "--no-interactive",
                ]
            )

            plan = self.tool.build_audit_plan(args)

        warning_codes = {item["code"] for item in plan["review_warnings"]}
        self.assertIn("full-scan-no-baseline", warning_codes)
        self.assertIn("missing-referenced-contract-artifacts", warning_codes)
        self.assertIn("java-build-mode-none", warning_codes)
        self.assertEqual(
            plan["missing_referenced_contract_artifacts"][0]["path"],
            str(contract.resolve()),
        )


if __name__ == "__main__":
    unittest.main()
