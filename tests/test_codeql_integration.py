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


def codeql_result(status: str, findings: list[dict] | None = None) -> dict:
    return {
        "enabled": True,
        "available": status != "unavailable",
        "status": status,
        "message": "测试 CodeQL 状态",
        "detail": "",
        "version": "2.20.0",
        "detected_languages": ["javascript-typescript"],
        "languages": ["javascript-typescript"],
        "databases": [],
        "sarif_files": [],
        "findings": findings or [],
    }


class CodeQLIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool_module()

    def test_resolve_codeql_enabled_defaults_to_disabled_outside_interactive_mode(self):
        args = self.tool.parse_args([])

        enabled = self.tool.resolve_codeql_enabled(args)

        self.assertFalse(enabled)

    def test_resolve_codeql_enabled_asks_in_interactive_mode(self):
        args = self.tool.parse_args(["--interactive"])

        enabled = self.tool.resolve_codeql_enabled(args, choose_enabled=lambda: True)

        self.assertTrue(enabled)

    def test_main_scanner_skips_codeql_cache_directory(self):
        self.assertTrue(self.tool.should_skip(Path(".code-change-check/cache/codeql/database/file.py")))

    def test_changed_file_filter_removes_codeql_cache_directory(self):
        changed = self.tool.filter_changed_files(
            [".code-change-check/cache/codeql/database/file.py", "src/app.py"]
        )

        self.assertEqual(changed, ["src/app.py"])

    def test_main_merges_codeql_findings_into_evidence(self):
        finding = {
            "id": "codeql:js/sql-injection",
            "title": "SQL 注入",
            "severity": "critical",
            "category": "CodeQL",
            "file": "app.ts",
            "line": 1,
            "snippet": "db.query(input)",
            "message": "发现不可信 SQL 输入",
        }
        self.tool.run_codeql_analysis = lambda *args, **kwargs: codeql_result("success", [finding])

        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            output = Path(temp_dir) / "output"
            project.mkdir()
            (project / "app.ts").write_text("export const app = 1;\n", encoding="utf-8")

            exit_code = self.tool.main(
                ["--project", str(project), "--codeql", "--no-contract", "--output", str(output)]
            )
            evidence = json.loads(
                (output / "code-change-check-evidence.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(evidence["codeql"]["status"], "success")
        self.assertTrue(any(item["id"] == "codeql:js/sql-injection" for item in evidence["findings"]))

    def test_require_codeql_returns_failure_after_writing_report(self):
        self.tool.run_codeql_analysis = lambda *args, **kwargs: codeql_result("unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            output = Path(temp_dir) / "output"
            project.mkdir()
            (project / "app.py").write_text("print('ok')\n", encoding="utf-8")

            exit_code = self.tool.main(
                ["--project", str(project), "--require-codeql", "--no-contract", "--output", str(output)]
            )
            report = (output / "code-change-check-report.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 3)
        self.assertIn("## CodeQL 深度分析", report)
        self.assertIn("unavailable", report)


if __name__ == "__main__":
    unittest.main()
