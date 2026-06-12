#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from typing import Callable


CommandRunner = Callable[[list[str], Path], tuple[int, str]]


def run_command(args: list[str], cwd: Path) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        return completed.returncode, completed.stdout.strip()
    except FileNotFoundError:
        return 127, f"命令不存在：{args[0]}"


def load_runtime_manifest(skill_root: Path) -> dict:
    path = skill_root / "assets" / "runtime-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for section_name in ("portable_java", "code_graph"):
        manifest.setdefault(section_name, {})["_skill_root"] = str(skill_root.resolve())
    return manifest


def platform_key() -> str:
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), platform.system().lower())
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64" if machine in {"amd64", "x86_64"} else machine
    return f"{system}-{arch}"


def _java_major(raw: str) -> int:
    match = re.search(r'version\s+"([^"]+)"', raw, re.IGNORECASE)
    if not match:
        match = re.search(r"\b(\d+)(?:\.\d+)+", raw)
    if not match:
        return 0
    version = match.group(1)
    parts = version.split(".")
    return int(parts[1] if parts[0] == "1" and len(parts) > 1 else parts[0])


def _result(status: str, source: str, executable: str, version: str, message: str, errors: list[str] | None = None) -> dict:
    return {
        "status": status,
        "source": source,
        "executable": executable,
        "version": version,
        "message": message,
        "errors": errors or [],
    }


def file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified_artifact(url: str, destination: Path, algorithm: str, digest: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    destination.unlink(missing_ok=True)
    try:
        urllib.request.urlretrieve(url, temporary)
        actual = file_digest(temporary, algorithm)
        if actual.lower() != digest.lower():
            raise ValueError(f"下载文件校验失败：期望 {digest}，实际 {actual}")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise


def _extract(archive: Path, destination: Path, archive_format: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if archive_format == "zip":
        with zipfile.ZipFile(archive) as handle:
            handle.extractall(destination)
        return
    if archive_format in {"tar.gz", "tgz"}:
        with tarfile.open(archive, "r:gz") as handle:
            handle.extractall(destination)
        return
    raise ValueError(f"不支持的归档格式：{archive_format}")


def _resolve_managed_runtime(
    name: str,
    section: dict,
    cache_root: Path,
    offline: bool,
) -> dict:
    key = platform_key()
    artifact = section.get("platforms", {}).get(key)
    if not artifact:
        return _result("unavailable", "", "", section.get("version", ""), f"运行时清单未提供 {key} 的 {name}。")
    bundled_path = artifact.get("bundled_path")
    skill_root = section.get("_skill_root")
    if bundled_path and skill_root:
        bundled = Path(skill_root) / bundled_path
        if bundled.is_file():
            return _result("success", "bundled", str(bundled.resolve()), section.get("version", ""), f"已使用发布包内的 {name}。")
    runtime_root = cache_root / name / section.get("version", "unknown") / key
    executable = runtime_root / artifact["entrypoint"]
    marker = runtime_root / ".verified"
    if executable.is_file() and marker.is_file():
        return _result("success", "cache", str(executable), section.get("version", ""), f"已使用缓存中的 {name}。")
    if offline:
        return _result("unavailable", "", "", section.get("version", ""), f"离线模式下没有可用的 {name} 缓存。")
    archive = cache_root / "downloads" / Path(artifact["url"]).name
    try:
        download_verified_artifact(artifact["url"], archive, artifact.get("algorithm", "sha256"), artifact["digest"])
        if runtime_root.exists():
            shutil.rmtree(runtime_root)
        _extract(archive, runtime_root, artifact.get("archive_format", "zip"))
        if not executable.is_file():
            raise ValueError(f"{name} 归档缺少入口文件：{artifact['entrypoint']}")
        marker.write_text(artifact["digest"], encoding="utf-8")
    except (OSError, ValueError) as error:
        return _result("unavailable", "", "", section.get("version", ""), f"无法准备 {name}：{error}", [str(error)])
    return _result("success", "downloaded", str(executable), section.get("version", ""), f"已下载并校验 {name}。")


def resolve_java_runtime(
    manifest: dict,
    cache_root: Path,
    offline: bool,
    command_runner: CommandRunner = run_command,
) -> dict:
    code, output = command_runner(["java", "-version"], Path.cwd())
    major = _java_major(output) if code == 0 else 0
    if major >= 17:
        return _result("success", "system", "java", str(major), "已使用系统 Java 17 或更高版本。")
    managed = _resolve_managed_runtime("portable-java", manifest.get("portable_java", {}), cache_root, offline)
    if managed["status"] != "success":
        managed["message"] = f"需要 Java 17 或更高版本；{managed['message']}"
    return managed


def resolve_portable_java_runtime(manifest: dict, cache_root: Path, offline: bool) -> dict:
    return _resolve_managed_runtime("portable-java", manifest.get("portable_java", {}), cache_root, offline)


def resolve_java_analyzer(skill_root: Path, manifest: dict) -> dict:
    section = manifest.get("java_analyzer", {})
    path = skill_root / section.get("bundled_path", "")
    if path.is_file():
        return _result("success", "bundled", str(path.resolve()), section.get("version", ""), "已找到内置 Java 分析器。")
    return _result("unavailable", "", "", section.get("version", ""), f"内置 Java 分析器不存在：{path}")


def resolve_code_graph_runtime(manifest: dict, cache_root: Path, offline: bool) -> dict:
    return _resolve_managed_runtime("code-graph", manifest.get("code_graph", {}), cache_root, offline)
