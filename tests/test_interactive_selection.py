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


if __name__ == "__main__":
    unittest.main()
