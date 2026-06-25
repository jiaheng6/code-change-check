from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


def load_module(name: str):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    path = scripts / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FindingFilterTest(unittest.TestCase):
    def test_partition_suppresses_support_files_and_xml_namespace(self):
        finding_filter = load_module("finding_filter")
        findings = [
            {"source": "text-rule", "file": "src/app.ts", "snippet": "client.publicBaseUrl"},
            {"source": "text-rule", "file": "contracts/payment.ts", "snippet": "client.publicBaseUrl"},
            {"source": "text-rule", "file": "responses/ApiResponse.java", "snippet": "status = paid"},
            {"source": "text-rule", "file": "tests/test_app.py", "snippet": "status = 'paid'"},
            {"source": "text-rule", "file": "docs/api.md", "snippet": "https://api.example.com"},
            {"source": "text-rule", "file": "debug/debug.txt", "snippet": "publicBaseUrl"},
            {"source": "text-rule", "file": "fixtures/response.json", "snippet": '"status": "paid"'},
            {"source": "text-rule", "file": "contracts/expected.json", "snippet": '"status": "paid"'},
            {"source": "text-rule", "file": "responses/actual.json", "snippet": '"status": "paid"'},
            {
                "source": "text-rule",
                "file": "pom.xml",
                "snippet": '<project xmlns="http://maven.apache.org/POM/4.0.0">',
            },
            {"source": "business-contract", "file": "tests/client.ts", "snippet": "contract difference"},
        ]

        active, suppressed = finding_filter.partition_findings(findings)

        self.assertEqual(
            [item["file"] for item in active],
            ["src/app.ts", "contracts/payment.ts", "responses/ApiResponse.java", "tests/client.ts"],
        )
        self.assertEqual(len(suppressed), 7)
        self.assertEqual(
            {item["file_role"] for item in suppressed},
            {"test", "documentation", "debug", "fixture", "markup-namespace"},
        )
        self.assertTrue(all(item["suppression_reason"] for item in suppressed))

    def test_partition_can_include_support_findings(self):
        finding_filter = load_module("finding_filter")
        findings = [
            {"source": "text-rule", "file": "tests/test_app.py", "snippet": "status = 'paid'"},
        ]

        active, suppressed = finding_filter.partition_findings(findings, include_support=True)

        self.assertEqual(len(active), 1)
        self.assertEqual(suppressed, [])


class FindingFilterIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_module("code_change_check")

    def test_main_keeps_suppressed_findings_out_of_primary_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            output = root / "output"
            (project / "src").mkdir(parents=True)
            (project / "tests").mkdir()
            (project / "docs").mkdir()
            (project / "src" / "app.ts").write_text("const url = config.publicBaseUrl;\n", encoding="utf-8")
            (project / "tests" / "test_app.py").write_text("status = 'paid'\n", encoding="utf-8")
            (project / "docs" / "api.md").write_text("https://api.example.com\n", encoding="utf-8")
            (project / "pom.xml").write_text(
                '<project xmlns="http://maven.apache.org/POM/4.0.0"></project>\n',
                encoding="utf-8",
            )

            exit_code = self.tool.main(
                [
                    "--project",
                    str(project),
                    "--scan-all",
                    "--no-contract",
                    "--java-analysis", "off",
                    "--no-interactive",
                    "--output",
                    str(output),
                ]
            )
            evidence = json.loads(
                (output / "evidence.json").read_text(encoding="utf-8")
            )
            report = (output / "report.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual({item["file"] for item in evidence["findings"]}, {"src/app.ts"})
        self.assertEqual(
            {item["file"] for item in evidence["suppressed_findings"]},
            {"tests/test_app.py", "docs/api.md", "pom.xml"},
        )
        self.assertEqual(evidence["summary"]["by_severity"]["critical"], 1)
        self.assertEqual(evidence["suppression_summary"]["total"], 3)
        self.assertIn("已抑制文本线索", report)


if __name__ == "__main__":
    unittest.main()
