from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from java_analysis import run_java_analysis


class JavaAnalysisTest(unittest.TestCase):
    def test_graph_failure_marks_result_partial_but_keeps_core_findings(self):
        core = {
            "status": "success",
            "coverage": {"java_files_total": 1, "java_files_parsed": 1, "java_files_failed": 0},
            "evidence": [],
            "errors": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            (project / "App.java").write_text("class App {}", encoding="utf-8")
            result = run_java_analysis(
                project,
                {"source": "snapshot", "range": "current", "changed_files": ["App.java"]},
                project / "out",
                core_analyzer=lambda source, runtime: core,
                graph_analyzer=lambda *args, **kwargs: {"status": "partial", "errors": ["不可用"]},
            )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["target"]["core"]["status"], "success")

    def test_core_failure_blocks_analysis(self):
        core = {
            "status": "blocked",
            "coverage": {"java_files_total": 1, "java_files_parsed": 0, "java_files_failed": 1},
            "evidence": [],
            "errors": ["失败"],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            (project / "App.java").write_text("class App {}", encoding="utf-8")
            result = run_java_analysis(
                project,
                {"source": "snapshot", "range": "current", "changed_files": ["App.java"]},
                project / "out",
                core_analyzer=lambda source, runtime: core,
            )

        self.assertEqual(result["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
