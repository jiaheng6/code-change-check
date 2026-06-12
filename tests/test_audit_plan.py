from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from audit_plan import apply_audit_plan, build_audit_plan, confirm_audit_plan, load_audit_plan, save_audit_plan
from code_change_check import parse_args


class AuditPlanTest(unittest.TestCase):
    def test_confirmed_plan_locks_java_analysis_and_offline_options(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            path = root / "plan.json"
            args = parse_args([
                "--project", str(project),
                "--scan-all",
                "--no-contract",
                "--java-analysis", "required",
                "--offline",
                "--no-interactive",
            ])
            save_audit_plan(path, build_audit_plan(args))
            confirm_audit_plan(path)
            loaded_args = parse_args([])
            apply_audit_plan(loaded_args, load_audit_plan(path))

        self.assertEqual(loaded_args.java_analysis, "required")
        self.assertTrue(loaded_args.offline)
        self.assertTrue(loaded_args.no_interactive)

    def test_unconfirmed_plan_is_rejected(self):
        args = parse_args([])
        with self.assertRaises(ValueError):
            apply_audit_plan(args, build_audit_plan(args))


if __name__ == "__main__":
    unittest.main()
