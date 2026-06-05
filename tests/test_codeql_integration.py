from __future__ import annotations

import importlib.util
import io
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


def codeql_result(
    status: str,
    findings: list[dict] | None = None,
    comparison_status: str = "unsupported",
    semantic_changes: list[dict] | None = None,
) -> dict:
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
        "comparison": {
            "status": comparison_status,
            "message": "测试对比状态",
            "baseline": None,
            "target": {"kind": "current", "value": "current-working-tree"},
            "new_findings": findings or [],
            "existing_findings": [],
            "resolved_findings": [],
            "semantic": {
                "status": "success",
                "message": "测试语义对比状态",
                "baseline_inventory": {"status": "success", "engine": "lightweight", "items": []},
                "target_inventory": {"status": "success", "engine": "lightweight", "items": []},
                "changes": semantic_changes or [],
            },
        },
    }


class CodeQLIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool_module()

    def test_default_interactive_turns_on_in_tty(self):
        class Tty:
            def isatty(self):
                return True

        args = self.tool.parse_args([])

        changed = self.tool.apply_default_interactive(args, stdin=Tty(), stdout=Tty())

        self.assertTrue(changed)
        self.assertTrue(args.interactive)

    def test_default_interactive_respects_no_interactive(self):
        class Tty:
            def isatty(self):
                return True

        args = self.tool.parse_args(["--no-interactive"])

        changed = self.tool.apply_default_interactive(args, stdin=Tty(), stdout=Tty())

        self.assertFalse(changed)
        self.assertFalse(args.interactive)

    def test_default_interactive_stays_off_outside_tty(self):
        class NotTty:
            def isatty(self):
                return False

        args = self.tool.parse_args([])

        changed = self.tool.apply_default_interactive(args, stdin=NotTty(), stdout=NotTty())

        self.assertFalse(changed)
        self.assertFalse(args.interactive)

    def test_default_interactive_respects_explicit_change_scope(self):
        class Tty:
            def isatty(self):
                return True

        args = self.tool.parse_args(["--base-ref", "main"])

        changed = self.tool.apply_default_interactive(args, stdin=Tty(), stdout=Tty())

        self.assertFalse(changed)
        self.assertFalse(args.interactive)

    def test_resolve_codeql_enabled_defaults_to_disabled_outside_interactive_mode(self):
        args = self.tool.parse_args([])

        enabled = self.tool.resolve_codeql_enabled(args)

        self.assertFalse(enabled)

    def test_parse_args_accepts_no_interactive_for_launchers(self):
        args = self.tool.parse_args(["--no-interactive"])

        self.assertTrue(args.no_interactive)
        self.assertFalse(args.interactive)

    def test_resolve_codeql_enabled_asks_in_interactive_mode(self):
        args = self.tool.parse_args(["--interactive"])

        enabled = self.tool.resolve_codeql_enabled(args, choose_enabled=lambda: True)

        self.assertTrue(enabled)

    def test_prompt_missing_codeql_prints_install_guide_in_interactive_mode(self):
        args = self.tool.parse_args(["--interactive"])
        output = io.StringIO()

        prompted = self.tool.maybe_prompt_codeql_installation(
            args,
            codeql_result("unavailable"),
            read_input=lambda prompt: "y",
            output=output,
        )

        self.assertTrue(prompted)
        text = output.getvalue()
        self.assertIn("未检测到 CodeQL CLI", text)
        self.assertIn("官方安装文档", text)
        self.assertIn("https://docs.github.com/en/code-security/codeql-cli/getting-started-with-the-codeql-cli/setting-up-the-codeql-cli", text)

    def test_prompt_missing_codeql_skips_install_guide_when_input_is_unavailable(self):
        args = self.tool.parse_args(["--interactive"])
        output = io.StringIO()

        def raise_eof(prompt):
            raise EOFError()

        prompted = self.tool.maybe_prompt_codeql_installation(
            args,
            codeql_result("unavailable"),
            read_input=raise_eof,
            output=output,
        )

        self.assertTrue(prompted)
        self.assertIn("未收到输入", output.getvalue())

    def test_main_prompts_when_interactive_codeql_is_unavailable(self):
        prompted = []
        self.tool.choose_codeql_enabled = lambda: True
        self.tool.collect_interactive_changes = lambda project, limit: {
            "source": "snapshot",
            "range": "interactive-test",
            "status": "",
            "stat": "",
            "diff": "",
            "changed_files": ["app.py"],
            "selected_commits": [],
        }
        self.tool.run_codeql_review = lambda *args, **kwargs: codeql_result("unavailable")
        self.tool.maybe_prompt_codeql_installation = lambda args, codeql: prompted.append(codeql) or True

        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            output = Path(temp_dir) / "output"
            project.mkdir()
            (project / "app.py").write_text("print('ok')\n", encoding="utf-8")

            exit_code = self.tool.main(
                ["--project", str(project), "--interactive", "--no-contract", "--output", str(output)]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(prompted[0]["status"], "unavailable")

    def test_require_codeql_compare_enables_codeql(self):
        args = self.tool.parse_args(["--require-codeql-compare"])

        self.assertTrue(self.tool.resolve_codeql_enabled(args))

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
        self.tool.run_codeql_review = lambda *args, **kwargs: codeql_result("success", [finding], "success")

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
        self.assertEqual(evidence["codeql"]["comparison"]["status"], "success")

    def test_require_codeql_returns_failure_after_writing_report(self):
        self.tool.run_codeql_review = lambda *args, **kwargs: codeql_result("unavailable")

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

    def test_require_codeql_compare_returns_failure_when_comparison_is_unsupported(self):
        self.tool.run_codeql_review = lambda *args, **kwargs: codeql_result("success", comparison_status="unsupported")

        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            output = Path(temp_dir) / "output"
            project.mkdir()
            (project / "app.py").write_text("print('ok')\n", encoding="utf-8")

            exit_code = self.tool.main(
                [
                    "--project",
                    str(project),
                    "--require-codeql-compare",
                    "--no-contract",
                    "--output",
                    str(output),
                ]
            )
            report = (output / "code-change-check-report.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 4)
        self.assertIn("## CodeQL baseline/target 对比", report)

    def test_main_merges_semantic_changes_into_findings_and_report(self):
        semantic_change = {
            "type": "addressing-changed",
            "severity": "critical",
            "file": "src/client.ts",
            "line": 2,
            "symbol": "base-url",
            "message": "寻址方式从 internal 变化为 public。",
            "removed": ["internal"],
            "added": ["public"],
        }
        self.tool.run_codeql_review = lambda *args, **kwargs: codeql_result(
            "success",
            comparison_status="success",
            semantic_changes=[semantic_change],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            output = Path(temp_dir) / "output"
            project.mkdir()
            (project / "app.py").write_text("print('ok')\n", encoding="utf-8")

            exit_code = self.tool.main(
                ["--project", str(project), "--codeql", "--no-contract", "--output", str(output)]
            )
            evidence = json.loads(
                (output / "code-change-check-evidence.json").read_text(encoding="utf-8")
            )
            report = (output / "code-change-check-report.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertTrue(any(item["id"] == "semantic:addressing-changed" for item in evidence["findings"]))
        self.assertIn("## 业务语义差异", report)
        self.assertIn("寻址方式从 internal 变化为 public", report)


if __name__ == "__main__":
    unittest.main()
