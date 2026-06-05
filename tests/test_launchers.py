from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LauncherTest(unittest.TestCase):
    def test_cmd_launcher_checks_python_and_py(self):
        launcher = ROOT / "run-code-change-check.cmd"

        self.assertTrue(launcher.exists())
        content = launcher.read_text(encoding="utf-8")
        self.assertIn("python --version", content)
        self.assertIn("py -3 --version", content)
        self.assertIn("未检测到 Python 3.10+", content)
        self.assertIn("scripts\\code_change_check.py", content)
        self.assertIn("--interactive", content)
        self.assertIn("--no-interactive", content)
        self.assertIn("--base-ref", content)
        self.assertIn("--svn-revision", content)
        self.assertIn("--baseline", content)

    def test_powershell_launcher_checks_python_and_py(self):
        launcher = ROOT / "run-code-change-check.ps1"

        self.assertTrue(launcher.exists())
        content = launcher.read_text(encoding="utf-8-sig")
        self.assertIn("Get-Command python", content)
        self.assertIn("Get-Command py", content)
        self.assertIn("未检测到 Python 3.10+", content)
        self.assertIn("scripts/code_change_check.py", content)
        self.assertIn("--interactive", content)
        self.assertIn("--no-interactive", content)
        self.assertIn("--base-ref", content)
        self.assertIn("--svn-revision", content)
        self.assertIn("--baseline", content)

    def test_shell_launcher_checks_python3_and_python(self):
        launcher = ROOT / "run-code-change-check.sh"

        self.assertTrue(launcher.exists())
        content = launcher.read_text(encoding="utf-8")
        self.assertIn("command -v python3", content)
        self.assertIn("command -v python", content)
        self.assertIn("未检测到 Python 3.10+", content)
        self.assertIn("scripts/code_change_check.py", content)
        self.assertIn("--interactive", content)
        self.assertIn("--no-interactive", content)
        self.assertIn("--base-ref", content)
        self.assertIn("--svn-revision", content)
        self.assertIn("--baseline", content)


if __name__ == "__main__":
    unittest.main()
