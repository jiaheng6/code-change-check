from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SkillInstructionsTest(unittest.TestCase):
    def test_skill_describes_current_java_analysis_workflow(self):
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("Spoon", content)
        self.assertIn("CodeGraph", content)
        self.assertIn("Java 语义分析", content)
        self.assertIn("--java-analysis", content)
        self.assertIn("--offline", content)
        self.assertNotIn("是否启用深度分析", content)

    def test_repository_has_no_retired_engine_trace(self):
        legacy = "code" + "ql"
        excluded = {".git", ".codegraph", "__pycache__", "debug", "dist", "code-change-check-output"}
        hits = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in excluded or part.startswith("code-change-check-output") for part in path.relative_to(ROOT).parts):
                continue
            if legacy in path.name.lower():
                hits.append(str(path.relative_to(ROOT)))
                continue
            if path.suffix.lower() in {".jar", ".zip", ".png", ".jpg", ".jpeg", ".webp"}:
                continue
            if legacy in path.read_text(encoding="utf-8", errors="ignore").lower():
                hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
