from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from tool_runtime import (
    download_verified_artifact,
    platform_key,
    resolve_code_graph_runtime,
    resolve_java_analyzer,
    resolve_portable_java_runtime,
    resolve_java_runtime,
)


class ToolRuntimeTest(unittest.TestCase):
    def test_prefers_system_java_17_or_newer(self):
        def fake(command, cwd):
            return 0, 'openjdk version "17.0.14"'

        result = resolve_java_runtime({}, Path("."), False, command_runner=fake)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["source"], "system")

    def test_rejects_system_java_older_than_17_in_offline_mode(self):
        def fake(command, cwd):
            return 0, 'java version "1.8.0_401"'

        result = resolve_java_runtime(
            {"portable_java": {"platforms": {}}},
            Path("."),
            True,
            command_runner=fake,
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertIn("17", result["message"])

    def test_resolves_bundled_java_analyzer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            jar = root / "tools" / "java-analyzer" / "dist" / "java-analyzer.jar"
            jar.parent.mkdir(parents=True)
            jar.write_bytes(b"jar")
            manifest = {"java_analyzer": {"version": "1.0.0", "bundled_path": str(jar.relative_to(root))}}

            result = resolve_java_analyzer(root, manifest)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["source"], "bundled")

    def test_offline_mode_never_downloads_code_graph(self):
        result = resolve_code_graph_runtime(
            {"code_graph": {"version": "0.9.9", "platforms": {}}},
            Path("."),
            True,
        )

        self.assertEqual(result["status"], "unavailable")

    def test_offline_package_prefers_bundled_portable_java(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "offline-runtimes" / "portable-java" / "bin" / "java.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"java")
            manifest = {
                "portable_java": {
                    "version": "17",
                    "_skill_root": str(root),
                    "platforms": {
                        platform_key(): {
                            "bundled_path": "offline-runtimes/portable-java/bin/java.exe"
                        }
                    },
                }
            }

            result = resolve_portable_java_runtime(manifest, root / "cache", True)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["source"], "bundled")

    def test_download_verifies_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.bin"
            destination = root / "destination.bin"
            source.write_bytes(b"content")
            digest = hashlib.sha256(b"content").hexdigest()

            download_verified_artifact(source.as_uri(), destination, "sha256", digest)

            self.assertEqual(destination.read_bytes(), b"content")

    def test_hash_mismatch_removes_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.bin"
            destination = root / "destination.bin"
            source.write_bytes(b"content")

            with self.assertRaises(ValueError):
                download_verified_artifact(source.as_uri(), destination, "sha256", "0" * 64)

            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
