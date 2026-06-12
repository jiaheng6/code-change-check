from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from code_graph import run_code_graph_analysis


class CodeGraphTest(unittest.TestCase):
    def test_collects_callers_callees_impact_and_affected_tests(self):
        commands = []

        def fake(command, cwd):
            commands.append(command)
            operation = command[1]
            if operation in {"init", "sync"}:
                return 0, "{}"
            if operation == "status":
                return 0, '{"files": 3, "nodes": 8, "edges": 7}'
            if operation == "callers":
                return 0, '[{"name":"Controller.run"}]'
            if operation == "callees":
                return 0, '[{"name":"Mapper.save"}]'
            if operation == "impact":
                return 0, '[{"name":"Service.run"}]'
            if operation == "affected":
                return 0, '["ServiceTest.java"]'
            return 1, "unexpected"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = run_code_graph_analysis(
                root,
                ["src/Service.java"],
                ["Service.run"],
                root / "cache",
                {"status": "success", "executable": "codegraph", "version": "0.9.9"},
                command_runner=fake,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["index"]["nodes"], 8)
        self.assertEqual(result["affected_tests"], ["ServiceTest.java"])
        self.assertFalse(any("npm" in part or "install" in part for command in commands for part in command))

    def test_unavailable_runtime_returns_partial(self):
        result = run_code_graph_analysis(
            Path("."),
            [],
            [],
            Path("."),
            {"status": "unavailable", "message": "不存在"},
        )

        self.assertEqual(result["status"], "partial")


if __name__ == "__main__":
    unittest.main()
