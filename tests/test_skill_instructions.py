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


if __name__ == "__main__":
    unittest.main()
