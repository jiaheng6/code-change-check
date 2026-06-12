#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse


CommandRunner = Callable[[list[str], Path], tuple[int, str]]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

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


def run_codeql_semantic_queries(*args, **kwargs):
    from codeql_semantic import run_codeql_semantic_queries as implementation

    return implementation(*args, **kwargs)


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
        build_files = {"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}
        if any(path.is_file() and path.name in build_files for path in project.rglob("*")):
            return "autobuild"
        for path in project.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".kt", ".kts"} and not should_skip(path.relative_to(project)):
                return "autobuild"
    return "none"


def quote_command_path(value: str) -> str:
    return f'"{value}"' if any(character.isspace() for character in value) else value


def parse_maven_modules(pom: Path) -> list[str]:
    try:
        root = ET.fromstring(pom.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ET.ParseError):
        return []
    return [
        (element.text or "").strip().replace("\\", "/")
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "module" and (element.text or "").strip()
    ]


def find_maven_build(project: Path) -> dict | None:
    project = project.resolve()
    if not (project / "pom.xml").is_file():
        candidates = [
            path
            for path in project.rglob("pom.xml")
            if not should_skip(path.relative_to(project))
        ]
        if not candidates:
            return None
        pom = min(
            candidates,
            key=lambda path: (
                len(path.relative_to(project).parts),
                0 if parse_maven_modules(path) else 1,
                path.as_posix(),
            ),
        )
        return {
            "build_system": "maven",
            "root": pom.parent,
            "module": "",
            "source_root": project,
        }
    current = project.parent
    while current != current.parent:
        pom = current / "pom.xml"
        if pom.is_file():
            for module in parse_maven_modules(pom):
                if (current / module).resolve() == project:
                    return {
                        "build_system": "maven",
                        "root": current,
                        "module": module,
                        "source_root": project,
                    }
        current = current.parent
    return {
        "build_system": "maven",
        "root": project,
        "module": "",
        "source_root": project,
    }


def find_gradle_build(project: Path) -> dict | None:
    project = project.resolve()
    build_names = {"build.gradle", "build.gradle.kts"}
    settings_names = {"settings.gradle", "settings.gradle.kts"}
    if not any((project / name).is_file() for name in build_names | settings_names):
        settings = [
            path
            for name in settings_names
            for path in project.rglob(name)
            if not should_skip(path.relative_to(project))
        ]
        builds = [
            path
            for name in build_names
            for path in project.rglob(name)
            if not should_skip(path.relative_to(project))
        ]
        candidates = settings or builds
        if not candidates:
            return None
        build_file = min(
            candidates,
            key=lambda path: (len(path.relative_to(project).parts), path.as_posix()),
        )
        return {
            "build_system": "gradle",
            "root": build_file.parent,
            "module": "",
            "source_root": project,
        }
    root = project
    current = project.parent
    while current != current.parent:
        if any((current / name).is_file() for name in settings_names):
            root = current
            break
        current = current.parent
    return {
        "build_system": "gradle",
        "root": root,
        "module": project.relative_to(root).as_posix() if root != project else "",
        "source_root": project,
    }


def detect_build_system(project: Path) -> dict | None:
    return find_maven_build(project) or find_gradle_build(project)


def build_tool_executable(build: dict) -> str:
    root = Path(build["root"])
    if build["build_system"] == "maven":
        wrapper_names = ["mvnw.cmd", "mvnw"] if os.name == "nt" else ["mvnw", "mvnw.cmd"]
        fallback = "mvn"
    else:
        wrapper_names = ["gradlew.bat", "gradlew"] if os.name == "nt" else ["gradlew", "gradlew.bat"]
        fallback = "gradle"
    wrapper = next((root / name for name in wrapper_names if (root / name).is_file()), None)
    return str(wrapper.resolve()) if wrapper else fallback


def build_retry_command(build: dict | None) -> str:
    if not build:
        return ""
    executable = quote_command_path(build_tool_executable(build))
    root = Path(build["root"])
    source_root = Path(build.get("source_root", root))
    module = build.get("module", "")
    if build["build_system"] == "maven":
        if module:
            return (
                f"{executable} -f {quote_command_path(str((root / 'pom.xml').resolve()))} "
                f"-pl {quote_command_path(module)} -am -DskipTests compile"
            )
        if root.resolve() != source_root.resolve():
            return (
                f"{executable} -f {quote_command_path(str((root / 'pom.xml').resolve()))} "
                "-DskipTests compile"
            )
        return f"{executable} -DskipTests compile"
    project_option = f" -p {quote_command_path(str(root.resolve()))}" if root else ""
    task = f":{module.replace('/', ':')}:classes" if module else "classes"
    return f"{executable}{project_option} {task} -x test"


def detect_build_strategy(
    project: Path,
    language: str,
    requested_build_mode: str | None,
    requested_build_command: str | None,
) -> dict:
    build = detect_build_system(project) if language == "java-kotlin" else None
    if requested_build_command:
        return {
            "build_system": build.get("build_system", "") if build else "",
            "build_root": str(build.get("root", "")) if build else "",
            "effective_build_mode": "manual",
            "build_command": requested_build_command,
            "initial_build_command": requested_build_command,
            "retry_command": "",
            "adjustment": "",
        }
    effective_build_mode = requested_build_mode or detect_default_build_mode(project, language)
    adjustment = ""
    if language == "java-kotlin" and build and effective_build_mode == "none":
        effective_build_mode = "autobuild"
        adjustment = "java-build-mode-none-overridden"
    return {
        "build_system": build.get("build_system", "") if build else "",
        "build_root": str(build.get("root", "")) if build else "",
        "effective_build_mode": effective_build_mode,
        "build_command": "",
        "initial_build_command": "",
        "retry_command": build_retry_command(build) if language == "java-kotlin" else "",
        "adjustment": adjustment,
    }


def command_status(
    command: list[str],
    project: Path,
    command_runner: CommandRunner,
) -> dict:
    code, output = command_runner(command, project)
    return {
        "available": code == 0,
        "command": command,
        "detail": output[:1000],
    }


def detect_build_environment(
    project: Path,
    language: str,
    build_system: str,
    command_runner: CommandRunner = run_command,
) -> dict:
    if language != "java-kotlin":
        return {
            "jdk": {"name": "JDK", "available": True, "command": [], "detail": "当前语言不需要 Java 构建环境。"},
            "build_tool": {"name": "", "available": True, "command": [], "detail": "当前语言不需要 Java 构建工具。"},
        }
    jdk = command_status(["java", "-version"], project, command_runner)
    jdk["name"] = "JDK"
    build = detect_build_system(project)
    if build_system and build:
        tool = build_tool_executable(build)
        build_tool = command_status([tool, "-version"], Path(build["root"]), command_runner)
        build_tool["name"] = build_system
    else:
        build_tool = {
            "name": build_system,
            "available": not build_system,
            "command": [],
            "detail": "未检测到 Maven/Gradle 构建文件。" if not build_system else "未检测到构建工具。",
        }
    return {
        "jdk": jdk,
        "build_tool": build_tool,
    }


def classify_build_failure(output: str) -> dict:
    lowered = output.lower()
    categories = [
        (
            "missing-jdk",
            ("java_home", "java: command not found", "java is not recognized", "no java installation"),
            "未检测到可用 JDK，或 JAVA_HOME 配置不正确。",
        ),
        (
            "missing-build-tool",
            ("mvn: command not found", "mvn is not recognized", "gradle: command not found", "gradle is not recognized"),
            "未检测到可用 Maven/Gradle 构建工具。",
        ),
        (
            "dependency-resolution",
            ("could not resolve dependencies", "dependency resolution", "could not transfer artifact", "non-resolvable parent"),
            "项目依赖解析失败，请检查私服、网络、凭据和本地 Maven/Gradle 配置。",
        ),
        (
            "compilation-failed",
            ("compilation failure", "compilation error", "failed to execute goal", "compiler:compile", "compilejava"),
            "项目编译失败，CodeQL 无法完成 Java 提取。",
        ),
        (
            "no-source-code",
            ("no source code was seen", "no code found", "no sources"),
            "CodeQL 构建过程中没有观察到目标源代码。",
        ),
    ]
    for category, patterns, message in categories:
        if any(pattern in lowered for pattern in patterns):
            return {"category": category, "message": message}
    return {
        "category": "build-failed",
        "message": "CodeQL database 创建失败，未能从日志中识别更具体的构建原因。",
    }


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


def build_attempt(
    project: Path,
    database: Path,
    language: str,
    executable: str,
    *,
    name: str,
    build_mode: str | None,
    build_command: str | None,
    command_runner: CommandRunner,
) -> tuple[int, str, dict]:
    code, output = create_database(
        project,
        database,
        language,
        executable,
        build_mode,
        build_command,
        command_runner,
    )
    attempt = {
        "name": name,
        "status": "success" if code == 0 else "failed",
        "build_mode": "manual" if build_command else build_mode,
        "command": build_command or "",
        "detail": output[:2000],
    }
    if code != 0:
        attempt["failure"] = classify_build_failure(output)
    return code, output, attempt


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
        "semantic_inventory": {
            "status": "unavailable" if not environment["available"] else "pending",
            "engine": "codeql",
            "message": environment["message"],
            "errors": [],
            "items": [],
            "languages": [],
        },
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
    strategies = {
        language: detect_build_strategy(project, language, build_mode, build_command)
        for language in selected_languages
    }
    strategy_fingerprint = json.dumps(
        {
            language: {
                "build_mode": strategy["effective_build_mode"],
                "build_command": strategy["initial_build_command"],
                "retry_command": strategy["retry_command"],
            }
            for language, strategy in strategies.items()
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    cache_key = build_cache_key(
        project,
        result["version"],
        selected_languages,
        strategy_fingerprint,
        build_command,
    )
    analysis_failed = False
    for language in selected_languages:
        strategy = strategies[language]
        effective_build_mode = strategy["effective_build_mode"]
        actual_build_mode = effective_build_mode
        actual_build_command = strategy["initial_build_command"]
        recovery_status = "not-attempted"
        attempts = []
        build_environment = detect_build_environment(
            project,
            language,
            strategy["build_system"],
            command_runner,
        )
        language_root = cache_root / cache_key / language
        database = language_root / "database"
        metadata = language_root / "metadata.json"
        cache_status = "reused" if database.exists() and metadata.exists() else "created"
        database_info = {
            "language": language,
            "path": str(database),
            "cache_status": cache_status,
            "build_mode": actual_build_mode,
            "build_command": actual_build_command,
            "build_system": strategy["build_system"],
            "build_root": strategy["build_root"],
            "strategy_adjustment": strategy["adjustment"],
            "recovery_status": recovery_status,
            "environment": build_environment,
            "attempts": attempts,
            "message": "",
        }
        if cache_status == "created":
            try:
                language_root.mkdir(parents=True, exist_ok=True)
                clear_incomplete_database(database, language_root)
                create_code, create_output, attempt = build_attempt(
                    project,
                    database,
                    language,
                    executable,
                    name="build-command" if actual_build_command else effective_build_mode,
                    build_mode=effective_build_mode,
                    build_command=actual_build_command or None,
                    command_runner=command_runner,
                )
                attempts.append(attempt)
            except (OSError, ValueError) as error:
                create_code, create_output = 1, f"无法创建 CodeQL database：{error}"
                attempts.append(
                    {
                        "name": "build-command" if actual_build_command else effective_build_mode,
                        "status": "failed",
                        "build_mode": actual_build_mode,
                        "command": actual_build_command,
                        "detail": create_output,
                        "failure": classify_build_failure(create_output),
                    }
                )

            should_retry = (
                create_code != 0
                and language == "java-kotlin"
                and not build_command
                and effective_build_mode == "autobuild"
                and bool(strategy["retry_command"])
            )
            if should_retry:
                recovery_status = "attempted"
                try:
                    clear_incomplete_database(database, language_root)
                    create_code, create_output, attempt = build_attempt(
                        project,
                        database,
                        language,
                        executable,
                        name="build-command-retry",
                        build_mode=None,
                        build_command=strategy["retry_command"],
                        command_runner=command_runner,
                    )
                    attempts.append(attempt)
                except (OSError, ValueError) as error:
                    create_code, create_output = 1, f"CodeQL 构建命令重试失败：{error}"
                    attempts.append(
                        {
                            "name": "build-command-retry",
                            "status": "failed",
                            "build_mode": "manual",
                            "command": strategy["retry_command"],
                            "detail": create_output,
                            "failure": classify_build_failure(create_output),
                        }
                    )
                actual_build_mode = "manual"
                actual_build_command = strategy["retry_command"]
                recovery_status = "success" if create_code == 0 else "failed"
            elif create_code == 0:
                recovery_status = "not-needed"

            database_info.update(
                {
                    "build_mode": actual_build_mode,
                    "build_command": actual_build_command,
                    "recovery_status": recovery_status,
                    "attempts": attempts,
                }
            )
            if create_code != 0:
                analysis_failed = True
                try:
                    clear_incomplete_database(database, language_root)
                except (OSError, ValueError) as error:
                    create_output = f"{create_output}\n无法清理失败的 CodeQL database：{error}"
                database_info["cache_status"] = "create-failed"
                database_info["message"] = create_output
                result["databases"].append(database_info)
                continue
            try:
                metadata.write_text(
                    json.dumps(
                        {
                            "cache_key": cache_key,
                            "language": language,
                            "version": result["version"],
                            "build_mode": actual_build_mode,
                            "build_command": actual_build_command,
                            "build_system": strategy["build_system"],
                            "build_root": strategy["build_root"],
                            "strategy_adjustment": strategy["adjustment"],
                            "recovery_status": recovery_status,
                            "environment": build_environment,
                            "attempts": attempts,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except OSError as error:
                analysis_failed = True
                database_info["cache_status"] = "metadata-failed"
                database_info["message"] = f"无法写入 CodeQL 缓存元数据：{error}"
                result["databases"].append(database_info)
                continue
        else:
            try:
                cached_metadata = json.loads(metadata.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cached_metadata = {}
            database_info.update(
                {
                    "build_mode": cached_metadata.get("build_mode", actual_build_mode),
                    "build_command": cached_metadata.get("build_command", actual_build_command),
                    "build_system": cached_metadata.get("build_system", strategy["build_system"]),
                    "build_root": cached_metadata.get("build_root", strategy["build_root"]),
                    "strategy_adjustment": cached_metadata.get(
                        "strategy_adjustment",
                        strategy["adjustment"],
                    ),
                    "recovery_status": cached_metadata.get("recovery_status", "cache-reused"),
                    "environment": cached_metadata.get("environment", build_environment),
                    "attempts": cached_metadata.get("attempts", []),
                }
            )
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
        try:
            semantic_result = run_codeql_semantic_queries(
                database,
                language,
                output / "codeql-semantic",
                executable=executable,
                command_runner=command_runner,
            )
        except Exception as error:
            semantic_result = {
                "status": "failed",
                "message": f"CodeQL 自定义语义查询执行异常：{error}",
                "errors": [str(error)],
                "items": [],
            }
        result["semantic_inventory"]["languages"].append(
            {
                "language": language,
                "status": semantic_result.get("status", ""),
                "message": semantic_result.get("message", ""),
            }
        )
        result["semantic_inventory"]["items"].extend(semantic_result.get("items", []))
        result["semantic_inventory"]["errors"].extend(semantic_result.get("errors", []))

    if analysis_failed:
        result["status"] = "partial-failure" if result["sarif_files"] else "failed"
        result["message"] = "CodeQL 分析未全部成功，请查看数据库状态和错误详情。"
    else:
        result["status"] = "success"
        result["message"] = "CodeQL 深度分析完成。"
    semantic_languages = result["semantic_inventory"]["languages"]
    if any(item["status"] == "success" for item in semantic_languages):
        result["semantic_inventory"]["status"] = (
            "partial-failure"
            if any(item["status"] == "failed" for item in semantic_languages)
            else "success"
        )
        result["semantic_inventory"]["message"] = "CodeQL 自定义语义查询已执行。"
    elif any(item["status"] == "failed" for item in semantic_languages):
        result["semantic_inventory"]["status"] = "failed"
        failed_messages = [
            item["message"]
            for item in semantic_languages
            if item["status"] == "failed" and item.get("message")
        ]
        detail = f" 原因：{'；'.join(failed_messages)}" if failed_messages else ""
        result["semantic_inventory"]["message"] = (
            f"CodeQL 自定义语义查询执行失败，已保留轻量语义清单作为降级结果。{detail}"
        )
    else:
        result["semantic_inventory"]["status"] = "unsupported"
        result["semantic_inventory"]["message"] = "当前分析语言没有可用的 CodeQL 自定义语义查询。"
    return result
