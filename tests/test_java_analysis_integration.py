from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


def load_tool_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "code_change_check.py"
    spec = importlib.util.spec_from_file_location("code_change_check_java", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["code_change_check_java"] = module
    spec.loader.exec_module(module)
    return module


class JavaAnalysisMainIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool_module()

    def test_java_project_runs_analysis_automatically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            output = root / "output"
            project.mkdir()
            (project / "App.java").write_text(
                'import java.util.Map; class App { void run(Map<String,Object> out){ out.put("x", 1); } }',
                encoding="utf-8",
            )

            exit_code = self.tool.main([
                "--project", str(project), "--scan-all", "--no-contract", "--no-interactive", "--output", str(output)
            ])
            evidence = json.loads((output / "evidence.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(evidence["java_analysis"]["target"]["core"]["status"], "success")
        self.assertGreater(evidence["java_analysis"]["coverage"]["java_files_parsed"], 0)

    def test_non_java_project_skips_java_analysis(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            output = root / "output"
            project.mkdir()
            (project / "app.py").write_text("print('ok')", encoding="utf-8")

            exit_code = self.tool.main([
                "--project", str(project), "--scan-all", "--no-contract", "--no-interactive", "--output", str(output)
            ])
            evidence = json.loads((output / "evidence.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(evidence["java_analysis"]["status"], "disabled")


if __name__ == "__main__":
    unittest.main()
