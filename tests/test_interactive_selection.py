from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import sys
import unittest


def load_tool_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "code_change_check.py"
    spec = importlib.util.spec_from_file_location("code_change_check", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["code_change_check"] = module
    spec.loader.exec_module(module)
    return module


class InteractiveSelectionTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool_module()

    def test_space_toggles_selection_and_enter_submits(self):
        state = self.tool.MultiSelectState(cursor=0, selected=set())

        action = self.tool.apply_multiselect_key(state, "space", 3)
        self.assertEqual(action, "continue")
        self.assertEqual(state.cursor, 0)
        self.assertEqual(state.selected, {0})

        action = self.tool.apply_multiselect_key(state, "down", 3)
        self.assertEqual(action, "continue")
        self.assertEqual(state.cursor, 1)

        action = self.tool.apply_multiselect_key(state, "space", 3)
        self.assertEqual(action, "continue")
        self.assertEqual(state.selected, {0, 1})

        action = self.tool.apply_multiselect_key(state, "up", 3)
        self.assertEqual(action, "continue")
        self.assertEqual(state.cursor, 0)

        action = self.tool.apply_multiselect_key(state, "space", 3)
        self.assertEqual(action, "continue")
        self.assertEqual(state.selected, {1})

        action = self.tool.apply_multiselect_key(state, "enter", 3)
        self.assertEqual(action, "submit")

    def test_run_multiselect_returns_items_in_original_order(self):
        keys = iter(["space", "down", "down", "space", "enter"])

        selected = self.tool.run_multiselect(
            "选择提交",
            ["提交 A", "提交 B", "提交 C"],
            read_key=lambda: next(keys),
            output=io.StringIO(),
            clear_screen=False,
        )

        self.assertEqual(selected, ["提交 A", "提交 C"])

    def test_navigation_wraps_around(self):
        state = self.tool.MultiSelectState(cursor=0, selected=set())

        self.tool.apply_multiselect_key(state, "up", 3)
        self.assertEqual(state.cursor, 2)

        self.tool.apply_multiselect_key(state, "down", 3)
        self.assertEqual(state.cursor, 0)

    def test_parse_number_selection_ignores_invalid_encoded_input(self):
        selected = self.tool.parse_number_selection("锘?1,无效,3", 3)

        self.assertEqual(selected, {0, 2})

    def test_parse_git_log_records(self):
        raw = "abcdef123456\x1fabcdef1\x1f2026-06-04\x1f修复内部寻址\n"

        records = self.tool.parse_git_log_records(raw)

        self.assertEqual(
            records,
            [
                {
                    "id": "abcdef123456",
                    "short_id": "abcdef1",
                    "date": "2026-06-04",
                    "message": "修复内部寻址",
                }
            ],
        )

    def test_build_requirement_items_keeps_source_location(self):
        specs = [
            {
                "file": "docs/spec.md",
                "headings": [{"line": 1, "text": "订单改造"}],
                "tasks": [{"line": 5, "text": "修复内部寻址"}],
                "key_lines": [{"line": 9, "text": "内部调用必须走 internalBaseUrl"}],
            }
        ]

        items = self.tool.build_requirement_items(specs)

        self.assertEqual(items[0]["id"], "R1")
        self.assertEqual(items[0]["kind"], "heading")
        self.assertEqual(items[0]["file"], "docs/spec.md")
        self.assertEqual(items[0]["line"], 1)
        self.assertIn("订单改造", items[0]["label"])
        self.assertEqual(items[1]["id"], "R2")
        self.assertEqual(items[1]["kind"], "task")
        self.assertIn("修复内部寻址", items[1]["label"])

    def test_create_requirement_commit_mappings_uses_selected_requirements(self):
        commits = [
            {
                "id": "abcdef123456",
                "short_id": "abcdef1",
                "date": "2026-06-04",
                "message": "修复内部寻址",
            }
        ]
        requirements = [
            {
                "id": "R1",
                "label": "R1 task docs/spec.md:L5 修复内部寻址",
                "file": "docs/spec.md",
                "line": 5,
                "kind": "task",
                "text": "修复内部寻址",
            },
            {
                "id": "R2",
                "label": "R2 constraint docs/spec.md:L9 内部调用必须走 internalBaseUrl",
                "file": "docs/spec.md",
                "line": 9,
                "kind": "constraint",
                "text": "内部调用必须走 internalBaseUrl",
            },
        ]

        mappings = self.tool.create_requirement_commit_mappings(
            commits,
            requirements,
            choose_for_commit=lambda commit, labels: [labels[1]],
        )

        self.assertEqual(len(mappings), 1)
        self.assertEqual(mappings[0]["commit"]["short_id"], "abcdef1")
        self.assertEqual(mappings[0]["requirements"][0]["id"], "R2")
        self.assertEqual(mappings[0]["requirements"][0]["line"], 9)


if __name__ == "__main__":
    unittest.main()
