from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def load_comparison_module():
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    path = scripts / "codeql_comparison.py"
    spec = importlib.util.spec_from_file_location("codeql_comparison", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def finding(rule_id: str, file: str, line: int, message: str) -> dict:
    return {
        "id": rule_id,
        "title": rule_id,
        "severity": "high",
        "category": "CodeQL",
        "file": file,
        "line": line,
        "snippet": "",
        "message": message,
    }


class CodeQLComparisonTest(unittest.TestCase):
    def setUp(self):
        self.comparison = load_comparison_module()

    def test_compare_findings_classifies_new_existing_and_resolved(self):
        baseline = [
            finding("codeql:old", "src/old.py", 4, "旧问题"),
            finding("codeql:keep", "src/app.py", 10, "保留问题"),
        ]
        target = [
            finding("codeql:keep", "src/app.py", 20, "保留问题"),
            finding("codeql:new", "src/new.py", 8, "新增问题"),
        ]

        result = self.comparison.compare_codeql_findings(baseline, target)

        self.assertEqual([item["id"] for item in result["new_findings"]], ["codeql:new"])
        self.assertEqual([item["id"] for item in result["existing_findings"]], ["codeql:keep"])
        self.assertEqual([item["id"] for item in result["resolved_findings"]], ["codeql:old"])

    def test_resolve_git_range_plan_uses_explicit_refs(self):
        plan = self.comparison.resolve_codeql_comparison_plan(
            Path("."),
            {"source": "git", "range": "main..feature"},
        )

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["baseline"], {"kind": "git-ref", "value": "main"})
        self.assertEqual(plan["target"], {"kind": "git-ref", "value": "feature"})

    def test_resolve_selected_non_contiguous_commits_is_unsupported(self):
        def fake_runner(args, cwd):
            if args[:3] == ["git", "rev-parse", "oldest^"]:
                return 0, "parent"
            if args[:3] == ["git", "rev-list", "--reverse"]:
                return 0, "oldest\nmiddle\nnewest"
            return 1, "未知命令"

        plan = self.comparison.resolve_codeql_comparison_plan(
            Path("."),
            {
                "source": "git",
                "range": "interactive-selected-commits",
                "selected_commits": [{"id": "newest"}, {"id": "oldest"}],
            },
            command_runner=fake_runner,
        )

        self.assertEqual(plan["status"], "unsupported")
        self.assertIn("非连续", plan["message"])
        self.assertEqual(plan["target"], {"kind": "git-ref", "value": "newest"})

    def test_materialize_git_ref_exports_requested_revision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            subprocess.run(["git", "init"], cwd=project, check=True, stdout=subprocess.PIPE)
            source = project / "app.py"
            source.write_text("print('baseline')\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=project, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "baseline"],
                cwd=project,
                check=True,
                stdout=subprocess.PIPE,
            )
            baseline = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()
            source.write_text("print('target')\n", encoding="utf-8")

            with self.comparison.materialize_codeql_source(
                project,
                {"kind": "git-ref", "value": baseline},
            ) as materialized:
                content = (materialized / "app.py").read_text(encoding="utf-8")

        self.assertEqual(content, "print('baseline')\n")

    def test_run_codeql_review_compares_snapshot_baseline_and_target(self):
        calls = []

        def fake_analyzer(project, output, **kwargs):
            calls.append((project, kwargs["source_scope"]))
            if kwargs["source_scope"] == "snapshot:baseline":
                findings = [finding("codeql:old", "app.py", 1, "旧问题")]
            else:
                findings = [finding("codeql:new", "app.py", 1, "新增问题")]
            return {
                "enabled": True,
                "available": True,
                "status": "success",
                "message": "完成",
                "detail": "",
                "version": "2.20.0",
                "source_scope": kwargs["source_scope"],
                "detected_languages": ["python"],
                "languages": ["python"],
                "databases": [],
                "sarif_files": [],
                "findings": findings,
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            baseline = root / "baseline"
            target = root / "target"
            output = root / "output"
            baseline.mkdir()
            target.mkdir()

            result = self.comparison.run_codeql_review(
                target,
                output,
                {"source": "snapshot", "range": f"{baseline}..{target}"},
                baseline_path=baseline,
                analyzer=fake_analyzer,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["comparison"]["status"], "success")
        self.assertEqual(result["comparison"]["new_findings"][0]["id"], "codeql:new")
        self.assertEqual(result["comparison"]["resolved_findings"][0]["id"], "codeql:old")
        self.assertEqual(len(calls), 2)

    def test_run_codeql_review_compares_semantics_even_when_codeql_is_unavailable(self):
        def unavailable_analyzer(project, output, **kwargs):
            return {
                "enabled": True,
                "available": False,
                "status": "unavailable",
                "message": "未安装 CodeQL",
                "detail": "",
                "version": "",
                "source_scope": kwargs["source_scope"],
                "detected_languages": [],
                "languages": [],
                "databases": [],
                "sarif_files": [],
                "findings": [],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            baseline = root / "baseline"
            target = root / "target"
            baseline.mkdir()
            target.mkdir()
            (baseline / "client.ts").write_text(
                "OrderClient.create(tenantId, orderId, amount);\nconst url = config.internalBaseUrl;\n",
                encoding="utf-8",
            )
            (target / "client.ts").write_text(
                "OrderClient.create(orderId, amount);\nconst url = config.publicBaseUrl;\n",
                encoding="utf-8",
            )

            result = self.comparison.run_codeql_review(
                target,
                root / "output",
                {"source": "snapshot", "range": f"{baseline}..{target}"},
                baseline_path=baseline,
                analyzer=unavailable_analyzer,
            )

        semantic = result["comparison"]["semantic"]
        self.assertEqual(semantic["status"], "success")
        self.assertEqual(
            [item["type"] for item in semantic["changes"]],
            ["addressing-changed", "call-arguments-changed", "tenant-field-removed"],
        )

    def test_run_codeql_review_does_not_mark_all_target_findings_new_when_baseline_fails(self):
        def fake_analyzer(project, output, **kwargs):
            is_baseline = kwargs["source_scope"] == "snapshot:baseline"
            return {
                "enabled": True,
                "available": True,
                "status": "failed" if is_baseline else "success",
                "message": "baseline 创建失败" if is_baseline else "target 完成",
                "detail": "",
                "version": "2.20.0",
                "source_scope": kwargs["source_scope"],
                "detected_languages": ["python"],
                "languages": ["python"],
                "databases": [],
                "sarif_files": [],
                "findings": [] if is_baseline else [finding("codeql:new", "app.py", 1, "问题")],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            baseline = root / "baseline"
            target = root / "target"
            baseline.mkdir()
            target.mkdir()

            result = self.comparison.run_codeql_review(
                target,
                root / "output",
                {"source": "snapshot", "range": f"{baseline}..{target}"},
                baseline_path=baseline,
                analyzer=fake_analyzer,
            )

        comparison = result["comparison"]
        self.assertEqual(comparison["status"], "failed")
        self.assertEqual(comparison["baseline_status"], "failed")
        self.assertEqual(comparison["target_status"], "success")
        self.assertEqual(comparison["new_findings"], [])
        self.assertIn("baseline 创建失败", comparison["message"])

    def test_run_codeql_review_target_only_records_target_status_without_differences(self):
        def fake_analyzer(project, output, **kwargs):
            return {
                "enabled": True,
                "available": True,
                "status": "success",
                "message": "target 完成",
                "detail": "",
                "version": "2.20.0",
                "source_scope": kwargs["source_scope"],
                "detected_languages": ["python"],
                "languages": ["python"],
                "databases": [],
                "sarif_files": [],
                "findings": [finding("codeql:target", "app.py", 1, "目标问题")],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()

            result = self.comparison.run_codeql_review(
                project,
                root / "output",
                {"source": "svn", "range": "1:2"},
                analyzer=fake_analyzer,
            )

        comparison = result["comparison"]
        self.assertEqual(comparison["status"], "unsupported")
        self.assertEqual(comparison["target_status"], "success")
        self.assertEqual(comparison["new_findings"], [])

    def test_run_codeql_review_without_comparison_still_analyzes_explicit_target_ref(self):
        scopes = []

        def fake_analyzer(project, output, **kwargs):
            scopes.append(kwargs["source_scope"])
            return {
                "enabled": True,
                "available": True,
                "status": "success",
                "message": "target 完成",
                "detail": "",
                "version": "2.20.0",
                "source_scope": kwargs["source_scope"],
                "detected_languages": ["python"],
                "languages": ["python"],
                "databases": [],
                "sarif_files": [],
                "findings": [],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            project.mkdir()
            subprocess.run(["git", "init"], cwd=project, check=True, stdout=subprocess.PIPE)
            source = project / "app.py"
            source.write_text("print('baseline')\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=project, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "baseline"],
                cwd=project,
                check=True,
                stdout=subprocess.PIPE,
            )
            baseline = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()
            source.write_text("print('target')\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=project, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "target"],
                cwd=project,
                check=True,
                stdout=subprocess.PIPE,
            )
            target = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()

            result = self.comparison.run_codeql_review(
                project,
                Path(temp_dir) / "output",
                {"source": "git", "range": f"{baseline}..{target}"},
                compare=False,
                analyzer=fake_analyzer,
            )

        self.assertEqual(scopes, [f"git:{target}"])
        self.assertEqual(result["comparison"]["status"], "disabled")
        self.assertEqual(result["comparison"]["target"], {"kind": "git-ref", "value": target})


if __name__ == "__main__":
    unittest.main()
