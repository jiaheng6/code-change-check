from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


def load_module():
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    path = scripts / "codeql_semantic.py"
    spec = importlib.util.spec_from_file_location("codeql_semantic", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CodeQLSemanticTest(unittest.TestCase):
    def setUp(self):
        self.semantic = load_module()

    def test_parse_call_rows_converts_csv_to_inventory_items(self):
        rows = [
            ["src/order.ts", "12", "OrderClient.create", "3"],
            ["src/client.ts", "5", "http.get", "1"],
        ]

        items = self.semantic.parse_call_rows(rows)

        self.assertEqual(items[0]["kind"], "call")
        self.assertEqual(items[0]["symbol"], "OrderClient.create")
        self.assertEqual(items[0]["argument_count"], 3)
        self.assertEqual(items[0]["engine"], "codeql")

    def test_run_codeql_semantic_queries_decodes_supported_language(self):
        commands = []

        def fake_runner(args, cwd):
            commands.append(args)
            if args[1:3] == ["query", "run"]:
                bqrs_arg = next(item for item in args if item.startswith("--output="))
                Path(bqrs_arg.split("=", 1)[1]).write_text("bqrs", encoding="utf-8")
                return 0, "查询完成"
            if args[1:3] == ["bqrs", "decode"]:
                csv_arg = next(item for item in args if item.startswith("--output="))
                Path(csv_arg.split("=", 1)[1]).write_text(
                    "src/order.ts,12,OrderClient.create,3\n",
                    encoding="utf-8",
                )
                return 0, "解码完成"
            return 1, "未知命令"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            query = root / "queries" / "javascript-typescript" / "calls.ql"
            query.parent.mkdir(parents=True)
            query.write_text("select 1\n", encoding="utf-8")
            database = root / "database"
            database.mkdir()

            result = self.semantic.run_codeql_semantic_queries(
                database,
                "javascript-typescript",
                root / "output",
                query_root=root / "queries",
                command_runner=fake_runner,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["items"][0]["symbol"], "OrderClient.create")
        self.assertTrue(any(args[1:3] == ["query", "run"] for args in commands))
        self.assertTrue(any(args[1:3] == ["bqrs", "decode"] for args in commands))

    def test_run_codeql_semantic_queries_reports_query_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            query = root / "queries" / "java-kotlin" / "calls.ql"
            query.parent.mkdir(parents=True)
            query.write_text("select 1\n", encoding="utf-8")

            result = self.semantic.run_codeql_semantic_queries(
                root / "database",
                "java-kotlin",
                root / "output",
                query_root=root / "queries",
                command_runner=lambda args, cwd: (1, "查询编译失败"),
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["items"], [])
        self.assertIn("查询编译失败", result["message"])

    def test_repository_contains_supported_language_query_packs(self):
        root = Path(__file__).resolve().parents[1] / "codeql" / "semantic"
        expected = {
            "javascript-typescript": "codeql/javascript-all",
            "java-kotlin": "codeql/java-all",
        }

        for language, dependency in expected.items():
            with self.subTest(language=language):
                pack = (root / language / "qlpack.yml").read_text(encoding="utf-8")
                query = (root / language / "calls.ql").read_text(encoding="utf-8")

                self.assertIn(dependency, pack)
                self.assertIn("select", query)
                self.assertIn("getNumArgument()", query)


if __name__ == "__main__":
    unittest.main()
