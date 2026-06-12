#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate_runtime_manifest(manifest: dict) -> list[str]:
    errors = []
    for section_name in ("portable_java", "code_graph"):
        section = manifest.get(section_name, {})
        for platform_name, artifact in section.get("platforms", {}).items():
            for field in ("url", "algorithm", "digest", "archive_format", "entrypoint"):
                if not artifact.get(field):
                    errors.append(f"{section_name}.{platform_name} 缺少 {field}")
            if artifact.get("algorithm") not in {"sha256", "sha512"}:
                errors.append(f"{section_name}.{platform_name} 使用了不支持的摘要算法")
    analyzer = manifest.get("java_analyzer", {})
    if not analyzer.get("bundled_path"):
        errors.append("java_analyzer 缺少 bundled_path")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验运行时清单")
    parser.add_argument("--manifest", default="assets/runtime-manifest.json")
    args = parser.parse_args(argv)
    path = Path(args.manifest)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_runtime_manifest(manifest)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("运行时清单校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
