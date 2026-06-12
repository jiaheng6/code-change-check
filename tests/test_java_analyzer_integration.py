from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
JAR = ROOT / "tools" / "java-analyzer" / "dist" / "java-analyzer.jar"


class JavaAnalyzerIntegrationTest(unittest.TestCase):
    def run_source(self, source: str) -> dict:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            (project / "App.java").write_text(source, encoding="utf-8")
            completed = subprocess.run(
                ["java", "-jar", str(JAR), "--project", str(project)],
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_analyzer_parses_project_without_project_dependencies(self):
        result = self.run_source(
            """
            import org.springframework.stereotype.Service;
            import com.company.privatepkg.SecretClient;
            @Service class App { SecretClient client; void run() { client.call("x"); } }
            """
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["coverage"]["java_files_parsed"], 1)
        self.assertTrue(any(item["kind"] == "call" for item in result["evidence"]))

    def test_analyzer_extracts_field_mapping(self):
        result = self.run_source(
            """
            import java.util.Map;
            class App { void run(Map<String,Object> out, Stats s) {
              out.put("fireEvent.count.value", s.getFireSafetyIncidents());
            }}
            class Stats { int getFireSafetyIncidents(){ return 1; } }
            """
        )

        mapping = next(item for item in result["evidence"] if item["kind"] == "field-mapping")
        self.assertEqual(mapping["slot"], "fireEvent.count.value")
        self.assertEqual(mapping["source_expression"], "s.getFireSafetyIncidents()")


if __name__ == "__main__":
    unittest.main()
