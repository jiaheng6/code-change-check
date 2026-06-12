from __future__ import annotations

import importlib.util
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


class SvnContextTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool_module()

    def test_parse_svn_info_extracts_working_copy_root(self):
        info = "\n".join(
            [
                "Path: backend",
                "Working Copy Root Path: E:\\work\\project",
                "URL: https://svn.example.com/project/backend",
            ]
        )

        parsed = self.tool.parse_svn_info(info)

        self.assertEqual(parsed["Working Copy Root Path"], "E:\\work\\project")

    def test_svn_working_copy_root_uses_show_item_from_subdirectory(self):
        project = Path("E:/work/project/backend")
        root = Path("E:/work/project")

        def fake_run_command(command, cwd):
            if command == ["svn", "info", "--show-item", "wc-root"]:
                return 0, f"{root}\n"
            return 1, ""

        self.tool.run_command = fake_run_command

        detected = self.tool.svn_working_copy_root(project)

        self.assertEqual(detected, root.resolve())

    def test_repository_context_recommends_svn_root_when_project_is_subdirectory(self):
        project = Path("E:/work/project/backend")
        root = Path("E:/work/project")

        def fake_run_command(command, cwd):
            if command[:3] == ["git", "rev-parse", "--show-toplevel"]:
                return 1, ""
            if command == ["svn", "info", "--show-item", "wc-root"]:
                return 0, f"{root}\n"
            return 1, ""

        self.tool.run_command = fake_run_command

        context = self.tool.detect_repository_context(project)

        self.assertEqual(context["vcs"], "svn")
        self.assertEqual(context["root"], str(root.resolve()))
        self.assertFalse(context["project_is_vcs_root"])
        self.assertEqual(context["recommended_project"], str(root.resolve()))
        self.assertIn("SVN 工作副本子目录", context["message"])

    def test_repository_context_reports_incompatible_svn_instead_of_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "backend"
            project.mkdir()
            (root / ".svn").mkdir()

            def fake_run_command(command, cwd):
                if command[:3] == ["git", "rev-parse", "--show-toplevel"]:
                    return 1, ""
                if command[0:2] == ["svn", "info"]:
                    return 1, "E155036: Please see the 'svn upgrade' command"
                return 1, ""

            self.tool.run_command = fake_run_command

            context = self.tool.detect_repository_context(project)

        self.assertEqual(context["vcs"], "svn-incompatible")
        self.assertEqual(context["root"], str(root.resolve()))
        self.assertIn("svn upgrade", context["detail"])

    def test_incompatible_svn_requires_explicit_snapshot_fallback(self):
        context = {
            "vcs": "svn-incompatible",
            "message": "检测到旧 SVN 工作副本",
            "detail": "E155036: Please see the 'svn upgrade' command",
        }

        blocked = self.tool.validate_repository_context_for_run(
            context,
            self.tool.parse_args(["--no-interactive"]),
        )
        allowed = self.tool.validate_repository_context_for_run(
            context,
            self.tool.parse_args(["--scan-all", "--no-interactive"]),
        )

        self.assertIn("显式选择", blocked)
        self.assertIsNone(allowed)


if __name__ == "__main__":
    unittest.main()
