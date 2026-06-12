#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import zipfile

from build_runtime_manifest import validate_runtime_manifest
from tool_runtime import load_runtime_manifest, platform_key, resolve_code_graph_runtime, resolve_portable_java_runtime


SKIP_PARTS = {
    ".code-change-check",
    ".codegraph",
    ".git",
    ".idea",
    ".svn",
    "__pycache__",
    "code-change-check-output",
    "debug",
    "dist",
    "target",
}


def include_file(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    if relative.as_posix() == "tools/java-analyzer/dist/java-analyzer.jar":
        return path.is_file()
    return path.is_file() and not any(part in SKIP_PARTS or part.startswith("code-change-check-output") for part in relative.parts)


def build_standard_package(root: Path, output_dir: Path) -> Path:
    manifest = load_runtime_manifest(root)
    errors = validate_runtime_manifest(manifest)
    if errors:
        raise ValueError("；".join(errors))
    analyzer = root / manifest["java_analyzer"]["bundled_path"]
    if not analyzer.is_file():
        raise FileNotFoundError(f"内置 Java 分析器不存在：{analyzer}")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / "code-change-check.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
            if include_file(root, path):
                handle.write(path, path.relative_to(root).as_posix())
    return archive


def build_offline_package(root: Path, output_dir: Path, cache_root: Path) -> Path:
    manifest = load_runtime_manifest(root)
    java = resolve_portable_java_runtime(manifest, cache_root, False)
    graph = resolve_code_graph_runtime(manifest, cache_root, False)
    if java["status"] != "success" or graph["status"] != "success":
        raise RuntimeError(f"无法准备离线运行时：Java={java['message']}；CodeGraph={graph['message']}")
    standard = build_standard_package(root, output_dir)
    archive = output_dir / f"code-change-check-{platform_key()}-offline.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as target:
        with zipfile.ZipFile(standard) as source:
            for name in source.namelist():
                target.writestr(name, source.read(name))
        for label, executable in (("portable-java", Path(java["executable"])), ("code-graph", Path(graph["executable"]))):
            runtime_root = executable.parent.parent
            for path in runtime_root.rglob("*"):
                if path.is_file():
                    target.write(path, f"offline-runtimes/{label}/{path.relative_to(runtime_root).as_posix()}")
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构建 code-change-check 发布包")
    parser.add_argument("--output", default="dist")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--tool-cache", default=str(Path.home() / ".code-change-check" / "tools"))
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output).resolve()
    archive = (
        build_offline_package(root, output, Path(args.tool_cache).expanduser())
        if args.offline
        else build_standard_package(root, output)
    )
    print(f"已生成发布包：{archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
