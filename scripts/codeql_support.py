#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse


CommandRunner = Callable[[list[str], Path], tuple[int, str]]

LANGUAGE_EXTENSIONS = {
    "c-cpp": {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"},
    "csharp": {".cs"},
    "go": {".go"},
    "java-kotlin": {".java", ".kt", ".kts"},
    "javascript-typescript": {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue"},
    "python": {".py"},
    "ruby": {".rb"},
    "rust": {".rs"},
    "swift": {".swift"},
}

LANGUAGE_ALIASES = {
    "c": "c-cpp",
    "c++": "c-cpp",
    "cpp": "c-cpp",
    "c-cpp": "c-cpp",
    "csharp": "csharp",
    "c#": "csharp",
    "go": "go",
    "java": "java-kotlin",
    "kotlin": "java-kotlin",
    "java-kotlin": "java-kotlin",
    "javascript": "javascript-typescript",
    "typescript": "javascript-typescript",
    "javascript-typescript": "javascript-typescript",
    "python": "python",
    "ruby": "ruby",
    "rust": "rust",
    "swift": "swift",
}

QUERY_SUITES = {
    "c-cpp": "cpp-code-scanning.qls",
    "csharp": "csharp-code-scanning.qls",
    "go": "go-code-scanning.qls",
    "java-kotlin": "java-code-scanning.qls",
    "javascript-typescript": "javascript-code-scanning.qls",
    "python": "python-code-scanning.qls",
    "ruby": "ruby-code-scanning.qls",
    "rust": "rust-code-scanning.qls",
    "swift": "swift-code-scanning.qls",
}

SKIP_DIRS = {
    ".code-change-check",
    ".git",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

FINGERPRINT_FILES = {
    "Cargo.lock",
    "Cargo.toml",
    "Gemfile.lock",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "go.sum",
    "gradle.lockfile",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "yarn.lock",
}


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


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS or part.startswith("code-change-check-output") for part in path.parts)


def detect_project_languages(project: Path) -> list[str]:
    detected = set()
    extension_to_language = {
        extension: language
        for language, extensions in LANGUAGE_EXTENSIONS.items()
        for extension in extensions
    }
    for path in project.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(project)
        if should_skip(relative):
            continue
        language = extension_to_language.get(path.suffix.lower())
        if language:
            detected.add(language)
    return sorted(detected)


def normalize_languages(languages: list[str]) -> list[str]:
    return sorted(
        {
            LANGUAGE_ALIASES[language.strip().lower()]
            for language in languages
            if language.strip().lower() in LANGUAGE_ALIASES
        }
    )


def parse_available_languages(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        return normalize_languages(list(data))
    if isinstance(data, list):
        return normalize_languages([str(language) for language in data])
    return normalize_languages(raw.replace(",", " ").split())


def detect_codeql(
    project: Path,
    executable: str = "codeql",
    command_runner: CommandRunner = run_command,
) -> dict:
    version_code, version_output = command_runner([executable, "version"], project)
    if version_code != 0:
        return {
            "available": False,
            "status": "unavailable",
            "executable": executable,
            "version": "",
            "languages": [],
            "message": "未检测到 CodeQL CLI，已跳过 CodeQL 深度分析。",
            "detail": version_output,
        }

    language_code, language_output = command_runner(
        [executable, "resolve", "languages", "--format=json"],
        project,
    )
    languages = parse_available_languages(language_output) if language_code == 0 else []
    version = version_output.strip().splitlines()[0] if version_output.strip() else "未知版本"
    return {
        "available": True,
        "status": "available",
        "executable": executable,
        "version": version,
        "languages": languages,
        "message": "CodeQL CLI 可用。",
        "detail": "" if language_code == 0 else language_output,
    }


def iter_fingerprint_files(project: Path):
    supported_extensions = set().union(*LANGUAGE_EXTENSIONS.values())
    for path in project.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(project)
        if should_skip(relative):
            continue
        if path.suffix.lower() in supported_extensions or path.name in FINGERPRINT_FILES:
            yield path


def project_fingerprint(project: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(iter_fingerprint_files(project), key=lambda item: item.as_posix()):
        digest.update(path.relative_to(project).as_posix().encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            continue
        digest.update(b"\0")
    return digest.hexdigest()


def build_cache_key(
    project: Path,
    version: str,
    languages: list[str],
    build_mode: str | None,
    build_command: str | None,
) -> str:
    payload = {
        "project_fingerprint": project_fingerprint(project),
        "version": version,
        "languages": sorted(languages),
        "build_mode": build_mode or "auto",
        "build_command": build_command or "",
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def detect_default_build_mode(project: Path, language: str) -> str:
    if language in {"go", "swift"}:
        return "autobuild"
    if language == "java-kotlin":
        for path in project.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".kt", ".kts"} and not should_skip(path.relative_to(project)):
                return "autobuild"
    return "none"


def normalize_sarif_uri(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return path.replace("\\", "/")
    return unquote(uri).replace("\\", "/")


def sarif_severity(result: dict, rule: dict) -> str:
    security_severity = rule.get("properties", {}).get("security-severity")
    try:
        score = float(security_severity)
    except (TypeError, ValueError):
        score = None
    if score is not None:
        if score >= 9:
            return "critical"
        if score >= 7:
            return "high"
        if score >= 4:
            return "medium"
        return "low"
    return {
        "error": "high",
        "warning": "medium",
        "note": "low",
        "none": "low",
    }.get(result.get("level", "warning"), "medium")


def parse_sarif_data(data: dict) -> list[dict]:
    findings = []
    for run in data.get("runs", []):
        rules = {
            rule.get("id", ""): rule
            for rule in run.get("tool", {}).get("driver", {}).get("rules", [])
        }
        for result in run.get("results", []):
            rule_id = result.get("ruleId", "unknown")
            rule = rules.get(rule_id, {})
            locations = result.get("locations") or [{}]
            physical = locations[0].get("physicalLocation", {})
            region = physical.get("region", {})
            uri = physical.get("artifactLocation", {}).get("uri", "")
            title = rule.get("shortDescription", {}).get("text") or rule_id
            message = result.get("message", {}).get("text", "CodeQL 命中。")
            findings.append(
                {
                    "id": f"codeql:{rule_id}",
                    "title": title,
                    "severity": sarif_severity(result, rule),
                    "category": "CodeQL",
                    "file": normalize_sarif_uri(uri),
                    "line": int(region.get("startLine", 1)),
                    "snippet": region.get("snippet", {}).get("text", "")[:240],
                    "message": message,
                }
            )
    return findings


def load_sarif_findings(path: Path) -> tuple[list[dict], str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [], f"无法解析 SARIF 结果文件：{error}"
    if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
        return [], "无法解析 SARIF 结果文件：缺少 runs 数组。"
    return parse_sarif_data(data), ""


def create_database(
    project: Path,
    database: Path,
    language: str,
    executable: str,
    build_mode: str | None,
    build_command: str | None,
    command_runner: CommandRunner,
) -> tuple[int, str]:
    args = [
        executable,
        "database",
        "create",
        str(database),
        f"--language={language}",
        f"--source-root={project}",
    ]
    if build_command:
        args.append(f"--command={build_command}")
    else:
        args.append(f"--build-mode={build_mode or detect_default_build_mode(project, language)}")
    return command_runner(args, project)


def analyze_database(
    project: Path,
    database: Path,
    output: Path,
    language: str,
    executable: str,
    command_runner: CommandRunner,
) -> tuple[int, str]:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    args = [
        executable,
        "database",
        "analyze",
        str(database),
        QUERY_SUITES[language],
        "--format=sarifv2.1.0",
        f"--output={output}",
        f"--sarif-category={language}",
    ]
    return command_runner(args, project)


def clear_incomplete_database(database: Path, language_root: Path) -> None:
    if not database.exists() and not database.is_symlink():
        return
    if database.parent.resolve() != language_root.resolve():
        raise ValueError("拒绝清理 CodeQL 缓存目录之外的路径。")
    if database.is_symlink() or database.is_file():
        database.unlink()
    else:
        shutil.rmtree(database)


def run_codeql_analysis(
    project: Path,
    output: Path,
    *,
    languages: list[str] | None = None,
    executable: str = "codeql",
    build_mode: str | None = None,
    build_command: str | None = None,
    cache_root: Path | None = None,
    source_scope: str = "current-working-tree",
    command_runner: CommandRunner = run_command,
) -> dict:
    environment = detect_codeql(project, executable, command_runner)
    result = {
        "enabled": True,
        "available": environment["available"],
        "status": environment["status"],
        "message": environment["message"],
        "detail": environment.get("detail", ""),
        "version": environment.get("version", ""),
        "source_scope": source_scope,
        "detected_languages": [],
        "languages": [],
        "databases": [],
        "sarif_files": [],
        "findings": [],
    }
    if not environment["available"]:
        return result

    detected_languages = detect_project_languages(project)
    result["detected_languages"] = detected_languages
    requested_languages = normalize_languages(languages) if languages else detected_languages
    available_languages = set(environment.get("languages", []))
    selected_languages = [
        language
        for language in requested_languages
        if language in LANGUAGE_EXTENSIONS and language in available_languages
    ]
    result["languages"] = selected_languages
    if not selected_languages:
        result["status"] = "no-supported-language"
        result["message"] = "未检测到 CodeQL 可分析的项目语言，已跳过 CodeQL 深度分析。"
        return result

    cache_root = cache_root or project / ".code-change-check" / "cache" / "codeql"
    try:
        cache_root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        result["status"] = "failed"
        result["message"] = f"无法使用 CodeQL 缓存目录：{error}"
        return result
    cache_key = build_cache_key(project, result["version"], selected_languages, build_mode, build_command)
    analysis_failed = False
    for language in selected_languages:
        effective_build_mode = build_mode or detect_default_build_mode(project, language)
        language_root = cache_root / cache_key / language
        database = language_root / "database"
        metadata = language_root / "metadata.json"
        cache_status = "reused" if database.exists() and metadata.exists() else "created"
        if cache_status == "created":
            try:
                language_root.mkdir(parents=True, exist_ok=True)
                clear_incomplete_database(database, language_root)
                create_code, create_output = create_database(
                    project,
                    database,
                    language,
                    executable,
                    build_mode,
                    build_command,
                    command_runner,
                )
            except (OSError, ValueError) as error:
                create_code, create_output = 1, f"无法创建 CodeQL database：{error}"
            if create_code != 0:
                analysis_failed = True
                result["databases"].append(
                    {
                        "language": language,
                        "path": str(database),
                        "cache_status": "create-failed",
                        "message": create_output,
                    }
                )
                continue
            try:
                metadata.write_text(
                    json.dumps(
                        {
                            "cache_key": cache_key,
                            "language": language,
                            "version": result["version"],
                            "build_mode": effective_build_mode,
                            "build_command": build_command or "",
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except OSError as error:
                analysis_failed = True
                result["databases"].append(
                    {
                        "language": language,
                        "path": str(database),
                        "cache_status": "metadata-failed",
                        "message": f"无法写入 CodeQL 缓存元数据：{error}",
                    }
                )
                continue

        database_info = {
            "language": language,
            "path": str(database),
            "cache_status": cache_status,
            "build_mode": effective_build_mode,
            "message": "",
        }
        result["databases"].append(database_info)
        sarif_path = output / "codeql" / f"{language}.sarif"
        try:
            analyze_code, analyze_output = analyze_database(
                project,
                database,
                sarif_path,
                language,
                executable,
                command_runner,
            )
        except OSError as error:
            analyze_code, analyze_output = 1, f"无法执行 CodeQL 分析：{error}"
        if analyze_code != 0:
            analysis_failed = True
            database_info["message"] = analyze_output
            continue
        if not sarif_path.exists():
            analysis_failed = True
            database_info["message"] = "CodeQL 分析命令未生成 SARIF 结果文件。"
            continue
        sarif_findings, sarif_error = load_sarif_findings(sarif_path)
        if sarif_error:
            analysis_failed = True
            database_info["message"] = sarif_error
            continue
        result["sarif_files"].append(str(sarif_path))
        result["findings"].extend(sarif_findings)

    if analysis_failed:
        result["status"] = "partial-failure" if result["sarif_files"] else "failed"
        result["message"] = "CodeQL 分析未全部成功，请查看数据库状态和错误详情。"
    else:
        result["status"] = "success"
        result["message"] = "CodeQL 深度分析完成。"
    return result
