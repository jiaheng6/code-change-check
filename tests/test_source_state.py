from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from source_state import materialize_source_state, resolve_source_states


class SourceStateTest(unittest.TestCase):
    def test_git_range_builds_baseline_and_target_descriptors(self):
        result = resolve_source_states(
            Path("."),
            {"source": "git", "range": "main..HEAD", "selected_commits": []},
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["baseline"], {"kind": "git-ref", "value": "main"})
        self.assertEqual(result["target"], {"kind": "git-ref", "value": "HEAD"})

    def test_snapshot_uses_directory_as_baseline_and_current_as_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline = Path(temp_dir)
            result = resolve_source_states(
                Path("."),
                {"source": "snapshot", "range": f"{baseline}..current"},
                baseline_path=baseline,
            )

        self.assertEqual(result["baseline"]["kind"], "snapshot")
        self.assertEqual(result["target"]["kind"], "current")

    def test_svn_range_uses_exportable_revisions_when_repository_url_is_available(self):
        commands = []

        def fake(command, cwd):
            commands.append(command)
            if command == ["svn", "info", "--show-item", "url"]:
                return 0, "https://svn.example.com/project/backend"
            return 0, ""

        result = resolve_source_states(
            Path("."),
            {"source": "svn", "range": "100:120"},
            command_runner=fake,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["baseline"]["kind"], "svn-revision")
        self.assertEqual(result["baseline"]["value"], "99")
        self.assertEqual(result["target"]["value"], "120")
        self.assertEqual(result["target"]["url"], "https://svn.example.com/project/backend")

    def test_svn_materialization_exports_to_temporary_directory(self):
        calls = []

        def fake(command, cwd):
            calls.append(command)
            Path(command[-1]).mkdir(parents=True, exist_ok=True)
            return 0, ""

        descriptor = {
            "kind": "svn-revision",
            "value": "120",
            "url": "https://svn.example.com/project/backend",
        }
        with materialize_source_state(Path("."), descriptor, command_runner=fake) as source:
            self.assertTrue(source.exists())

        self.assertEqual(calls[0][:4], ["svn", "export", "--force", "-r"])
        self.assertFalse(source.exists())


if __name__ == "__main__":
    unittest.main()
