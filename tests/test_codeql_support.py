from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


def load_codeql_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "codeql_support.py"
    spec = importlib.util.spec_from_file_location("codeql_support", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CodeQLSupportTest(unittest.TestCase):
    def setUp(self):
        self.codeql = load_codeql_module()

    def test_detect_project_languages_uses_supported_source_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            (project / "src").mkdir()
            (project / "src" / "app.ts").write_text("export const app = 1;\n", encoding="utf-8")
            (project / "service.py").write_text("print('ok')\n", encoding="utf-8")
            (project / "README.md").write_text("# 说明\n", encoding="utf-8")

            languages = self.codeql.detect_project_languages(project)

        self.assertEqual(languages, ["javascript-typescript", "python"])

    def test_detect_codeql_reports_unavailable(self):
        def missing_runner(args, cwd):
            return 127, "命令不存在：codeql"

        status = self.codeql.detect_codeql(Path("."), command_runner=missing_runner)

        self.assertFalse(status["available"])
        self.assertEqual(status["status"], "unavailable")
        self.assertIn("未检测到 CodeQL CLI", status["message"])

    def test_run_codeql_analysis_keeps_explicit_source_scope_when_unavailable(self):
        result = self.codeql.run_codeql_analysis(
            Path("."),
            Path("output"),
            source_scope="git:main",
            command_runner=lambda args, cwd: (127, "命令不存在：codeql"),
        )

        self.assertEqual(result["source_scope"], "git:main")

    def test_normalize_languages_accepts_codeql_extractor_aliases(self):
        languages = self.codeql.normalize_languages(["javascript", "java", "cpp", "python"])

        self.assertEqual(
            languages,
            ["c-cpp", "java-kotlin", "javascript-typescript", "python"],
        )

    def test_detect_default_build_mode_distinguishes_java_and_kotlin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            (project / "App.java").write_text("class App {}\n", encoding="utf-8")

            java_mode = self.codeql.detect_default_build_mode(project, "java-kotlin")
            (project / "App.kt").write_text("class AppKt\n", encoding="utf-8")
            kotlin_mode = self.codeql.detect_default_build_mode(project, "java-kotlin")

        self.assertEqual(java_mode, "none")
        self.assertEqual(kotlin_mode, "autobuild")

    def test_run_codeql_analysis_reuses_successful_database_cache(self):
        commands = []

        def fake_runner(args, cwd):
            commands.append(args)
            if args[1] == "version":
                return 0, "CodeQL command-line toolchain release 2.20.0"
            if args[1:3] == ["resolve", "languages"]:
                return 0, "javascript-typescript"
            if args[1:3] == ["database", "create"]:
                database = Path(args[3])
                database.mkdir(parents=True)
                return 0, "数据库创建完成"
            if args[1:3] == ["database", "analyze"]:
                output_arg = next(item for item in args if item.startswith("--output="))
                output = Path(output_arg.split("=", 1)[1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps({"version": "2.1.0", "runs": [{"tool": {"driver": {}}, "results": []}]}),
                    encoding="utf-8",
                )
                return 0, "分析完成"
            return 1, "未知命令"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            output = root / "output"
            cache = root / "cache"
            project.mkdir()
            (project / "app.ts").write_text("export const app = 1;\n", encoding="utf-8")

            first = self.codeql.run_codeql_analysis(
                project,
                output,
                cache_root=cache,
                command_runner=fake_runner,
            )
            second = self.codeql.run_codeql_analysis(
                project,
                output,
                cache_root=cache,
                command_runner=fake_runner,
            )

        create_commands = [args for args in commands if args[1:3] == ["database", "create"]]
        self.assertEqual(first["status"], "success")
        self.assertEqual(second["status"], "success")
        self.assertEqual(len(create_commands), 1)
        self.assertEqual(second["databases"][0]["cache_status"], "reused")

    def test_run_codeql_analysis_collects_custom_semantic_inventory(self):
        def fake_runner(args, cwd):
            if args[1] == "version":
                return 0, "CodeQL command-line toolchain release 2.20.0"
            if args[1:3] == ["resolve", "languages"]:
                return 0, "python"
            if args[1:3] == ["database", "create"]:
                Path(args[3]).mkdir(parents=True)
                return 0, "数据库创建完成"
            if args[1:3] == ["database", "analyze"]:
                output_arg = next(item for item in args if item.startswith("--output="))
                output = Path(output_arg.split("=", 1)[1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps({"version": "2.1.0", "runs": [{"tool": {"driver": {}}, "results": []}]}),
                    encoding="utf-8",
                )
                return 0, "分析完成"
            return 1, "未知命令"

        self.codeql.run_codeql_semantic_queries = lambda *args, **kwargs: {
            "status": "success",
            "engine": "codeql",
            "language": "python",
            "message": "完成",
            "errors": [],
            "items": [
                {
                    "kind": "call",
                    "file": "app.py",
                    "line": 1,
                    "symbol": "client.call",
                    "argument_count": 1,
                    "arguments": [],
                    "engine": "codeql",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            (project / "app.py").write_text("client.call(value)\n", encoding="utf-8")

            result = self.codeql.run_codeql_analysis(
                project,
                root / "output",
                cache_root=root / "cache",
                command_runner=fake_runner,
            )

        self.assertEqual(result["semantic_inventory"]["status"], "success")
        self.assertEqual(result["semantic_inventory"]["items"][0]["symbol"], "client.call")

    def test_run_codeql_analysis_keeps_standard_result_when_custom_query_raises(self):
        def fake_runner(args, cwd):
            if args[1] == "version":
                return 0, "CodeQL command-line toolchain release 2.20.0"
            if args[1:3] == ["resolve", "languages"]:
                return 0, "python"
            if args[1:3] == ["database", "create"]:
                Path(args[3]).mkdir(parents=True)
                return 0, "数据库创建完成"
            if args[1:3] == ["database", "analyze"]:
                output_arg = next(item for item in args if item.startswith("--output="))
                output = Path(output_arg.split("=", 1)[1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps({"version": "2.1.0", "runs": [{"tool": {"driver": {}}, "results": []}]}),
                    encoding="utf-8",
                )
                return 0, "分析完成"
            return 1, "未知命令"

        self.codeql.run_codeql_semantic_queries = lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("自定义查询执行异常")
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            (project / "app.py").write_text("client.call(value)\n", encoding="utf-8")

            result = self.codeql.run_codeql_analysis(
                project,
                root / "output",
                cache_root=root / "cache",
                command_runner=fake_runner,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["semantic_inventory"]["status"], "failed")
        self.assertIn("自定义查询执行异常", result["semantic_inventory"]["message"])

    def test_parse_sarif_converts_result_to_finding(self):
        sarif = {
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "rules": [
                                {
                                    "id": "js/sql-injection",
                                    "shortDescription": {"text": "SQL 注入"},
                                    "properties": {"security-severity": "9.1"},
                                }
                            ]
                        }
                    },
                    "results": [
                        {
                            "ruleId": "js/sql-injection",
                            "level": "error",
                            "message": {"text": "发现不可信 SQL 输入"},
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": "src/query.ts"},
                                        "region": {"startLine": 12, "snippet": {"text": "db.query(input)"}},
                                    }
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        findings = self.codeql.parse_sarif_data(sarif)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["id"], "codeql:js/sql-injection")
        self.assertEqual(findings[0]["severity"], "critical")
        self.assertEqual(findings[0]["category"], "CodeQL")
        self.assertEqual(findings[0]["file"], "src/query.ts")
        self.assertEqual(findings[0]["line"], 12)

    def test_run_codeql_analysis_fails_when_analyze_does_not_write_sarif(self):
        def fake_runner(args, cwd):
            if args[1] == "version":
                return 0, "CodeQL command-line toolchain release 2.20.0"
            if args[1:3] == ["resolve", "languages"]:
                return 0, '{"javascript": ["bundle/javascript"]}'
            if args[1:3] == ["database", "create"]:
                Path(args[3]).mkdir(parents=True)
                return 0, "数据库创建完成"
            if args[1:3] == ["database", "analyze"]:
                return 0, "命令返回成功但未写入结果"
            return 1, "未知命令"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            (project / "app.ts").write_text("export const app = 1;\n", encoding="utf-8")

            result = self.codeql.run_codeql_analysis(
                project,
                root / "output",
                cache_root=root / "cache",
                command_runner=fake_runner,
            )

        self.assertEqual(result["status"], "failed")
        self.assertIn("未生成 SARIF", result["databases"][0]["message"])

    def test_run_codeql_analysis_fails_when_sarif_is_invalid(self):
        def fake_runner(args, cwd):
            if args[1] == "version":
                return 0, "CodeQL command-line toolchain release 2.20.0"
            if args[1:3] == ["resolve", "languages"]:
                return 0, '{"python": ["bundle/python"]}'
            if args[1:3] == ["database", "create"]:
                Path(args[3]).mkdir(parents=True)
                return 0, "数据库创建完成"
            if args[1:3] == ["database", "analyze"]:
                output_arg = next(item for item in args if item.startswith("--output="))
                output = Path(output_arg.split("=", 1)[1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("不是合法 JSON", encoding="utf-8")
                return 0, "分析完成"
            return 1, "未知命令"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            (project / "app.py").write_text("print('ok')\n", encoding="utf-8")

            result = self.codeql.run_codeql_analysis(
                project,
                root / "output",
                cache_root=root / "cache",
                command_runner=fake_runner,
            )

        self.assertEqual(result["status"], "failed")
        self.assertIn("无法解析 SARIF", result["databases"][0]["message"])

    def test_run_codeql_analysis_retries_after_partial_database_creation(self):
        create_count = 0

        def fake_runner(args, cwd):
            nonlocal create_count
            if args[1] == "version":
                return 0, "CodeQL command-line toolchain release 2.20.0"
            if args[1:3] == ["resolve", "languages"]:
                return 0, '{"python": ["bundle/python"]}'
            if args[1:3] == ["database", "create"]:
                create_count += 1
                database = Path(args[3])
                if database.exists():
                    return 1, "database 已存在"
                database.mkdir(parents=True)
                if create_count == 1:
                    return 1, "模拟创建中断"
                return 0, "数据库创建完成"
            if args[1:3] == ["database", "analyze"]:
                output_arg = next(item for item in args if item.startswith("--output="))
                output = Path(output_arg.split("=", 1)[1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps({"version": "2.1.0", "runs": [{"tool": {"driver": {}}, "results": []}]}),
                    encoding="utf-8",
                )
                return 0, "分析完成"
            return 1, "未知命令"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            (project / "app.py").write_text("print('ok')\n", encoding="utf-8")

            first = self.codeql.run_codeql_analysis(
                project,
                root / "output",
                cache_root=root / "cache",
                command_runner=fake_runner,
            )
            second = self.codeql.run_codeql_analysis(
                project,
                root / "output",
                cache_root=root / "cache",
                command_runner=fake_runner,
            )

        self.assertEqual(first["status"], "failed")
        self.assertEqual(second["status"], "success")
        self.assertEqual(create_count, 2)

    def test_run_codeql_analysis_reports_invalid_cache_path_without_crashing(self):
        def fake_runner(args, cwd):
            if args[1] == "version":
                return 0, "CodeQL command-line toolchain release 2.20.0"
            if args[1:3] == ["resolve", "languages"]:
                return 0, '{"python": ["bundle/python"]}'
            return 1, "不应执行"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            (project / "app.py").write_text("print('ok')\n", encoding="utf-8")
            cache_file = root / "cache"
            cache_file.write_text("这是文件，不是目录", encoding="utf-8")

            result = self.codeql.run_codeql_analysis(
                project,
                root / "output",
                cache_root=cache_file,
                command_runner=fake_runner,
            )

        self.assertEqual(result["status"], "failed")
        self.assertIn("缓存目录", result["message"])


if __name__ == "__main__":
    unittest.main()
