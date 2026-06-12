from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SkillInstructionsTest(unittest.TestCase):
    def test_skill_forbids_direct_execution_before_claude_code_preflight_confirmation(self):
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("Claude Code", content)
        self.assertIn("禁止直接执行", content)
        self.assertIn("先在聊天里向用户确认", content)
        self.assertIn("SVN 工作副本根目录", content)
        self.assertIn("--save-audit-plan", content)
        self.assertIn("--confirm-audit-plan", content)
        self.assertIn("--audit-plan", content)
        self.assertIn("--strict-spec", content)
        self.assertIn("--response-snapshot", content)
        self.assertIn("--include-support-findings", content)

    def test_readme_explains_installation_workflow_and_terms(self):
        content = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("CC Switch", content)
        self.assertIn("ZIP", content)
        self.assertIn("独立审查会话", content)
        self.assertIn("```mermaid", content)
        self.assertIn("## 近期亮点", content)
        self.assertIn("## 名词解释", content)
        self.assertIn("迭代范围", content)
        self.assertIn("业务契约", content)
        self.assertIn("CodeQL", content)
        self.assertIn("证据", content)


if __name__ == "__main__":
    unittest.main()
