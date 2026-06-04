#!/usr/bin/env python3
from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".env",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".lua",
    ".md",
    ".mjs",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".scss",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}

SKIP_DIRS = {
    ".git",
    ".idea",
    ".svn",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "coverage",
    "code-change-check-output",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

SPEC_GLOBS = [
    "openspec/**/*.md",
    "specs/**/*.md",
    ".specify/**/*.md",
    "docs/**/*.md",
    "requirements/**/*.md",
    "tasks/**/*.md",
    "*spec*.md",
    "*requirement*.md",
    "*design*.md",
    "*task*.md",
    "todo*.md",
]


@dataclasses.dataclass(frozen=True)
class RiskPattern:
    id: str
    title: str
    severity: str
    regex: str
    message: str
    category: str


@dataclasses.dataclass
class Finding:
    id: str
    title: str
    severity: str
    category: str
    file: str
    line: int
    snippet: str
    message: str


@dataclasses.dataclass
class MultiSelectState:
    cursor: int
    selected: set[int]


DEFAULT_RISK_PATTERNS = [
    RiskPattern(
        id="external-address",
        title="可能误用外部地址",
        severity="critical",
        category="寻址",
        regex=r"\b(publicBaseUrl|PUBLIC_BASE_URL|externalBaseUrl|EXTERNAL_BASE_URL|https?://)",
        message="发现外部地址或公网域名线索，需确认内部服务调用是否应使用 internalBaseUrl 或内部服务发现。",
    ),
    RiskPattern(
        id="http-rpc-call",
        title="新增或修改 HTTP/RPC 调用",
        severity="high",
        category="服务调用",
        regex=r"\b(fetch|axios|request|requests|HttpClient|RestTemplate|WebClient|OkHttp|grpc|FeignClient)\b",
        message="发现网络调用线索，需核对地址来源、超时、重试、鉴权、幂等和错误处理。",
    ),
    RiskPattern(
        id="db-write",
        title="数据库写入或删除",
        severity="high",
        category="数据写入",
        regex=r"\b(insert|update|delete|save|remove|create|bulkWrite|executeUpdate)\b",
        message="发现数据库写入/删除线索，需核对事务、条件、幂等、回滚和旧数据兼容。",
    ),
    RiskPattern(
        id="auth-permission",
        title="权限或鉴权逻辑",
        severity="high",
        category="权限",
        regex=r"\b(auth|permission|role|tenant|token|jwt|session|login|logout|acl|scope)\b",
        message="发现权限相关线索，需核对是否绕过既有鉴权、租户隔离或角色判断。",
    ),
    RiskPattern(
        id="state-transition",
        title="状态流转逻辑",
        severity="high",
        category="状态",
        regex=r"\b(status|state|phase|transition|workflow|approve|reject|cancel|refund|paid|closed)\b",
        message="发现状态流转线索，需核对非法状态跳转、旧状态兼容和并发更新。",
    ),
    RiskPattern(
        id="money-inventory",
        title="金额、库存或数量计算",
        severity="high",
        category="计算",
        regex=r"\b(amount|price|fee|balance|quota|stock|inventory|quantity|discount|tax|total)\b",
        message="发现金额/库存/数量线索，需核对精度、舍入、边界、负数和重复扣减。",
    ),
    RiskPattern(
        id="third-party",
        title="第三方对接风险",
        severity="medium",
        category="第三方",
        regex=r"\b(webhook|callback|signature|sign|secret|apiKey|retry|timeout|provider|vendor)\b",
        message="发现第三方对接线索，需核对签名、回调来源、重试、超时和兼容字段。",
    ),
    RiskPattern(
        id="config-env",
        title="配置或环境变量变化",
        severity="medium",
        category="配置",
        regex=r"\b(process\.env|getenv|ENV|config|application\.yml|application\.properties|dotenv)\b",
        message="发现配置读取线索，需核对不同环境、默认值、灰度和安全边界。",
    ),
    RiskPattern(
        id="route-middleware",
        title="路由或中间件变化",
        severity="medium",
        category="入口",
        regex=r"\b(router|route|controller|middleware|interceptor|filter|endpoint|@RequestMapping|@GetMapping|@PostMapping)\b",
        message="发现入口层线索，需核对鉴权、中间件顺序、兼容路径和暴露范围。",
    ),
]


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


def apply_multiselect_key(state: MultiSelectState, key: str, item_count: int) -> str:
    if item_count <= 0:
        return "submit" if key == "enter" else "continue"
    if key in {"up", "k"}:
        state.cursor = (state.cursor - 1) % item_count
        return "continue"
    if key in {"down", "j"}:
        state.cursor = (state.cursor + 1) % item_count
        return "continue"
    if key == "space":
        if state.cursor in state.selected:
            state.selected.remove(state.cursor)
        else:
            state.selected.add(state.cursor)
        return "continue"
    if key == "enter":
        return "submit"
    if key in {"q", "esc", "ctrl_c"}:
        return "cancel"
    return "continue"


def render_multiselect(
    title: str,
    items: list[str],
    state: MultiSelectState,
    output,
    clear_screen: bool,
) -> None:
    if clear_screen:
        output.write("\x1b[2J\x1b[H")
    output.write(f"{title}\n\n")
    output.write("使用 ↑/↓ 移动，空格选择/取消，回车提交，q 取消。\n\n")
    if not items:
        output.write("没有可选择的记录。\n")
        output.flush()
        return
    for index, item in enumerate(items):
        cursor = ">" if index == state.cursor else " "
        checked = "[x]" if index in state.selected else "[ ]"
        output.write(f"{cursor} {checked} {item}\n")
    output.flush()


def run_multiselect(
    title: str,
    items: list[str],
    read_key,
    output,
    clear_screen: bool = True,
) -> list[str]:
    state = MultiSelectState(cursor=0, selected=set())
    while True:
        render_multiselect(title, items, state, output, clear_screen)
        action = apply_multiselect_key(state, read_key(), len(items))
        if action == "submit":
            if clear_screen:
                output.write("\x1b[2J\x1b[H")
            return [item for index, item in enumerate(items) if index in state.selected]
        if action == "cancel":
            if clear_screen:
                output.write("\x1b[2J\x1b[H")
            return []


def read_terminal_key() -> str:
    if os.name == "nt":
        import msvcrt

        char = msvcrt.getwch()
        if char in {"\x00", "\xe0"}:
            second = msvcrt.getwch()
            return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(second, second)
        if char in {"\r", "\n"}:
            return "enter"
        if char == " ":
            return "space"
        if char == "\x03":
            return "ctrl_c"
        if char == "\x1b":
            return "esc"
        return char.lower()

    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        char = sys.stdin.read(1)
        if char == "\x1b":
            ready, _, _ = select.select([sys.stdin], [], [], 0.05)
            rest = sys.stdin.read(2) if ready else ""
            if rest == "[A":
                return "up"
            if rest == "[B":
                return "down"
            return "esc"
        if char in {"\r", "\n"}:
            return "enter"
        if char == " ":
            return "space"
        if char == "\x03":
            return "ctrl_c"
        return char.lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def parse_number_selection(raw: str, item_count: int) -> set[int]:
    selected: set[int] = set()
    for part in raw.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            for value in range(min(start, end), max(start, end) + 1):
                if 1 <= value <= item_count:
                    selected.add(value - 1)
        else:
            value = int(part)
            if 1 <= value <= item_count:
                selected.add(value - 1)
    return selected


def choose_items(title: str, items: list[str]) -> list[str]:
    if not items:
        print("没有可选择的记录。")
        return []
    if sys.stdin.isatty() and sys.stdout.isatty():
        return run_multiselect(title, items, read_terminal_key, sys.stdout)

    print(title)
    for index, item in enumerate(items, start=1):
        print(f"[{index}] {item}")
    raw = input("请输入序号，支持 1,2,3 或 1-5：").strip()
    selected_indexes = parse_number_selection(raw, len(items))
    return [item for index, item in enumerate(items) if index in selected_indexes]


def is_git_repo(project: Path) -> bool:
    code, _ = run_command(["git", "rev-parse", "--is-inside-work-tree"], project)
    return code == 0


def is_svn_repo(project: Path) -> bool:
    if (project / ".svn").exists():
        return True
    code, _ = run_command(["svn", "info"], project)
    return code == 0


def normalize_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def is_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    if path.name in {"Dockerfile", "Makefile", "AGENTS.md", "SKILL.md"}:
        return True
    return False


def iter_project_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and not should_skip(path.relative_to(root)) and is_text_file(path):
            yield path


def parse_git_log_records(raw: str) -> list[dict]:
    records = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f", 3)
        if len(parts) != 4:
            continue
        records.append(
            {
                "id": parts[0],
                "short_id": parts[1],
                "date": parts[2],
                "message": parts[3],
            }
        )
    return records


def parse_svn_log_records(raw: str) -> list[dict]:
    records = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return records
    for entry in root.findall("logentry"):
        revision = entry.attrib.get("revision", "")
        date = (entry.findtext("date") or "")[:10]
        message = (entry.findtext("msg") or "").replace("\n", " ").strip()
        records.append(
            {
                "id": revision,
                "short_id": f"r{revision}",
                "date": date,
                "message": message,
            }
        )
    return records


def format_change_record(record: dict) -> str:
    message = record.get("message") or "无提交说明"
    return f"{record.get('short_id', '')} {record.get('date', '')} {message}".strip()


def choose_records(title: str, records: list[dict]) -> list[dict]:
    labels = [format_change_record(record) for record in records]
    selected_labels = set(choose_items(title, labels))
    return [record for label, record in zip(labels, records) if label in selected_labels]


def list_recent_git_commits(project: Path, limit: int) -> list[dict]:
    code, output = run_command(
        [
            "git",
            "log",
            "--date=short",
            f"--max-count={limit}",
            "--pretty=format:%H%x1f%h%x1f%ad%x1f%s",
        ],
        project,
    )
    if code != 0:
        return []
    return parse_git_log_records(output)


def list_recent_svn_revisions(project: Path, limit: int) -> list[dict]:
    code, output = run_command(["svn", "log", "--xml", "-l", str(limit)], project)
    if code != 0:
        return []
    return parse_svn_log_records(output)


def collect_git_selected_commits(project: Path, commits: list[dict]) -> dict:
    status_code, status = run_command(["git", "status", "--short", "--untracked-files=all"], project)
    changed = set()
    diff_parts = []
    stat_parts = []
    for commit in commits:
        commit_id = commit["id"]
        name_code, names = run_command(["git", "show", "--name-only", "--format=", commit_id], project)
        if name_code == 0:
            changed.update(line.strip() for line in names.splitlines() if line.strip())
        stat_code, stat = run_command(["git", "show", "--stat", "--format=medium", commit_id], project)
        if stat_code == 0 and stat:
            stat_parts.append(stat)
        diff_code, diff = run_command(["git", "show", "--patch", "--unified=3", "--format=medium", commit_id], project)
        if diff_code == 0 and diff:
            diff_parts.append(diff)

    return {
        "source": "git",
        "range": "interactive-selected-commits",
        "selected_commits": commits,
        "status": status if status_code == 0 else "",
        "stat": "\n\n".join(stat_parts),
        "diff": "\n\n".join(diff_parts),
        "changed_files": sorted(changed),
    }


def collect_svn_selected_revisions(project: Path, revisions: list[dict]) -> dict:
    status_code, status = run_command(["svn", "status"], project)
    changed = set()
    diff_parts = []
    for revision in revisions:
        revision_id = revision["id"]
        diff_code, diff = run_command(["svn", "diff", "-c", revision_id], project)
        if diff_code == 0 and diff:
            diff_parts.append(diff)
        summarize_code, summarize = run_command(["svn", "diff", "--summarize", "-c", revision_id], project)
        if summarize_code == 0:
            for line in summarize.splitlines():
                parts = line.split()
                if parts:
                    changed.add(parts[-1])

    return {
        "source": "svn",
        "range": "interactive-selected-revisions",
        "selected_commits": revisions,
        "status": status if status_code == 0 else "",
        "stat": "",
        "diff": "\n\n".join(diff_parts),
        "changed_files": sorted(changed),
    }


def empty_interactive_changes(source: str) -> dict:
    return {
        "source": source,
        "range": "interactive-empty",
        "selected_commits": [],
        "status": "未选择提交记录。",
        "stat": "",
        "diff": "",
        "changed_files": [],
    }


def collect_interactive_changes(project: Path, limit: int) -> dict:
    if is_git_repo(project):
        records = list_recent_git_commits(project, limit)
        selected = choose_records("请选择本次迭代包含的 Git 提交记录", records)
        if not selected:
            return empty_interactive_changes("git")
        return collect_git_selected_commits(project, selected)
    if is_svn_repo(project):
        records = list_recent_svn_revisions(project, limit)
        selected = choose_records("请选择本次迭代包含的 SVN 版本记录", records)
        if not selected:
            return empty_interactive_changes("svn")
        return collect_svn_selected_revisions(project, selected)
    print("当前项目不是 Git 或 SVN 仓库，交互选择提交记录不可用，改用目录快照扫描。")
    return collect_snapshot_changes(project, None)


def collect_git_changes(project: Path, base_ref: str | None, target_ref: str | None) -> dict:
    status_code, status = run_command(["git", "status", "--short", "--untracked-files=all"], project)
    if base_ref:
        range_ref = f"{base_ref}..{target_ref or 'HEAD'}"
        name_code, names = run_command(["git", "diff", "--name-only", range_ref], project)
        cached_code, cached_names = 0, ""
        stat_code, stat = run_command(["git", "diff", "--stat", range_ref], project)
        diff_code, diff = run_command(["git", "diff", "--unified=3", range_ref], project)
    else:
        range_ref = "working-tree"
        name_code, names = run_command(["git", "diff", "--name-only"], project)
        cached_code, cached_names = run_command(["git", "diff", "--cached", "--name-only"], project)
        stat_code, stat = run_command(["git", "diff", "--stat"], project)
        diff_code, diff = run_command(["git", "diff", "--unified=3"], project)

    changed = set()
    if name_code == 0:
        changed.update(line.strip() for line in names.splitlines() if line.strip())
    if cached_code == 0:
        changed.update(line.strip() for line in cached_names.splitlines() if line.strip())
    if status_code == 0:
        for line in status.splitlines():
            if len(line) > 3:
                changed.add(line[3:].strip().strip('"'))

    return {
        "source": "git",
        "range": range_ref,
        "status": status,
        "stat": stat if stat_code == 0 else "",
        "diff": diff if diff_code == 0 else "",
        "changed_files": sorted(changed),
    }


def collect_svn_changes(project: Path, svn_revision: str | None) -> dict:
    status_code, status = run_command(["svn", "status"], project)
    if svn_revision:
        diff_code, diff = run_command(["svn", "diff", "-r", svn_revision], project)
        summarize_code, summarize = run_command(["svn", "diff", "--summarize", "-r", svn_revision], project)
    else:
        diff_code, diff = run_command(["svn", "diff"], project)
        summarize_code, summarize = 1, ""
    changed = []
    if status_code == 0:
        for line in status.splitlines():
            if len(line) > 8:
                changed.append(line[8:].strip())
    if summarize_code == 0:
        for line in summarize.splitlines():
            parts = line.split()
            if parts:
                changed.append(parts[-1])
    return {
        "source": "svn",
        "range": svn_revision or "working-copy",
        "status": status if status_code == 0 else "",
        "stat": "",
        "diff": diff if diff_code == 0 else "",
        "changed_files": sorted(set(changed)),
    }


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_index(root: Path) -> dict[str, str]:
    result = {}
    for path in iter_project_files(root):
        result[normalize_relative(path, root)] = file_hash(path)
    return result


def collect_snapshot_changes(project: Path, baseline: Path | None) -> dict:
    current = snapshot_index(project)
    if baseline is None:
        return {
            "source": "snapshot",
            "range": "current",
            "status": "未提供 baseline，执行当前目录全量扫描。",
            "stat": "",
            "diff": "",
            "changed_files": sorted(current),
        }

    before = snapshot_index(baseline)
    changed = []
    for rel_path, digest in current.items():
        if before.get(rel_path) != digest:
            changed.append(rel_path)
    for rel_path in before:
        if rel_path not in current:
            changed.append(rel_path)

    return {
        "source": "snapshot",
        "range": f"{baseline}..{project}",
        "status": f"baseline={baseline}",
        "stat": "",
        "diff": "",
        "changed_files": sorted(set(changed)),
    }


def collect_changes(
    project: Path,
    baseline: Path | None,
    base_ref: str | None,
    target_ref: str | None,
    svn_revision: str | None,
) -> dict:
    if is_git_repo(project):
        return collect_git_changes(project, base_ref, target_ref)
    if is_svn_repo(project):
        return collect_svn_changes(project, svn_revision)
    return collect_snapshot_changes(project, baseline)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def discover_spec_files(project: Path, explicit_specs: list[str]) -> list[Path]:
    result: list[Path] = []
    for spec in explicit_specs:
        path = Path(spec)
        if not path.is_absolute():
            path = project / path
        if path.exists() and path.is_file():
            result.append(path)

    seen = {p.resolve() for p in result}
    for pattern in SPEC_GLOBS:
        for path in project.glob(pattern):
            if path.is_file() and path.resolve() not in seen and not should_skip(path.relative_to(project)):
                seen.add(path.resolve())
                result.append(path)
    return result


def extract_spec_summary(project: Path, spec_files: list[Path]) -> list[dict]:
    summaries = []
    heading_re = re.compile(r"^(#{1,6})\s+(.+)$")
    task_re = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+(.+)$")
    keyword_re = re.compile(r"(必须|不能|不得|需要|验收|兼容|风险|规则|约束|内部|外部|权限|状态|第三方)")

    for path in spec_files:
        text = read_text(path)
        headings = []
        tasks = []
        key_lines = []
        for index, line in enumerate(text.splitlines(), start=1):
            heading = heading_re.match(line)
            if heading:
                headings.append({"line": index, "text": heading.group(2).strip()})
            task = task_re.match(line)
            if task:
                tasks.append({"line": index, "text": task.group(1).strip()})
            if keyword_re.search(line):
                key_lines.append({"line": index, "text": line.strip()[:300]})

        summaries.append(
            {
                "file": normalize_relative(path, project),
                "headings": headings[:30],
                "tasks": tasks[:80],
                "key_lines": key_lines[:120],
            }
        )
    return summaries


def load_custom_patterns(rules_path: Path | None) -> list[RiskPattern]:
    if rules_path is None:
        return []
    data = json.loads(read_text(rules_path))
    patterns = []
    for item in data.get("riskPatterns", []):
        patterns.append(
            RiskPattern(
                id=item["id"],
                title=item["title"],
                severity=item.get("severity", "medium"),
                category=item.get("category", "自定义"),
                regex=item["regex"],
                message=item.get("message", "命中自定义风险规则。"),
            )
        )
    return patterns


def scan_files(project: Path, changed_files: list[str], scan_all: bool, patterns: list[RiskPattern]) -> list[Finding]:
    files: list[Path] = []
    if changed_files and not scan_all:
        for rel_path in changed_files:
            path = project / rel_path
            if path.exists() and path.is_file() and is_text_file(path) and not should_skip(path.relative_to(project)):
                files.append(path)
    else:
        files = list(iter_project_files(project))

    findings: list[Finding] = []
    compiled = [(pattern, re.compile(pattern.regex, re.IGNORECASE)) for pattern in patterns]
    for path in files:
        try:
            lines = read_text(path).splitlines()
        except OSError:
            continue
        rel_file = normalize_relative(path, project)
        for line_number, line in enumerate(lines, start=1):
            for pattern, regex in compiled:
                if regex.search(line):
                    findings.append(
                        Finding(
                            id=pattern.id,
                            title=pattern.title,
                            severity=pattern.severity,
                            category=pattern.category,
                            file=rel_file,
                            line=line_number,
                            snippet=line.strip()[:240],
                            message=pattern.message,
                        )
                    )
    return findings


def severity_rank(severity: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(severity, 4)


def summarize_findings(findings: list[Finding]) -> dict:
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_file: dict[str, int] = {}
    for finding in findings:
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
        by_category[finding.category] = by_category.get(finding.category, 0) + 1
        by_file[finding.file] = by_file.get(finding.file, 0) + 1
    return {
        "by_severity": dict(sorted(by_severity.items(), key=lambda item: severity_rank(item[0]))),
        "by_category": dict(sorted(by_category.items(), key=lambda item: item[0])),
        "top_files": dict(sorted(by_file.items(), key=lambda item: item[1], reverse=True)[:20]),
    }


def build_mermaid(findings: list[Finding]) -> str:
    categories = sorted({finding.category for finding in findings})
    if not categories:
        return "flowchart LR\n  A[代码变更] --> B[未发现内置风险命中]\n"
    lines = ["flowchart LR", "  A[代码变更] --> B[风险类型]"]
    for index, category in enumerate(categories, start=1):
        safe_id = f"C{index}"
        count = sum(1 for finding in findings if finding.category == category)
        lines.append(f"  B --> {safe_id}[{category}: {count}]")
    return "\n".join(lines) + "\n"


def make_report(data: dict) -> str:
    findings = [Finding(**item) for item in data["findings"]]
    sorted_findings = sorted(findings, key=lambda item: (severity_rank(item.severity), item.file, item.line))
    summary = data["summary"]
    changes = data["changes"]

    lines = [
        "# 代码变更检查报告",
        "",
        f"- 生成时间：{data['generated_at']}",
        f"- 项目路径：`{data['project']}`",
        f"- 变更来源：`{changes['source']}`",
        f"- 变更范围：`{changes.get('range', '')}`",
        f"- 变更文件数：{len(changes['changed_files'])}",
        f"- 需求/任务文档数：{len(data['specs'])}",
        f"- 风险命中数：{len(findings)}",
        "",
        "## 总览",
        "",
        "### 按严重程度",
        "",
    ]

    if summary["by_severity"]:
        for severity, count in summary["by_severity"].items():
            lines.append(f"- `{severity}`：{count}")
    else:
        lines.append("- 未发现内置风险命中。")

    lines.extend(["", "### 按风险类型", ""])
    if summary["by_category"]:
        for category, count in summary["by_category"].items():
            lines.append(f"- {category}：{count}")
    else:
        lines.append("- 未发现内置风险命中。")

    lines.extend(["", "## 变更文件", ""])
    if changes["changed_files"]:
        for path in changes["changed_files"][:120]:
            lines.append(f"- `{path}`")
        if len(changes["changed_files"]) > 120:
            lines.append(f"- 其余 {len(changes['changed_files']) - 120} 个文件略。")
    else:
        lines.append("- 未从版本系统发现变更文件。")

    if changes.get("selected_commits") is not None:
        lines.extend(["", "## 本次迭代提交记录", ""])
        if changes["selected_commits"]:
            for commit in changes["selected_commits"]:
                lines.append(
                    f"- `{commit.get('short_id', commit.get('id', ''))}` {commit.get('date', '')} {commit.get('message', '')}"
                )
        else:
            lines.append("- 未选择提交记录。")

    lines.extend(["", "## 需求和任务线索", ""])
    if data["specs"]:
        for spec in data["specs"]:
            lines.append(f"### `{spec['file']}`")
            if spec["headings"]:
                lines.append("")
                lines.append("标题：")
                for heading in spec["headings"][:12]:
                    lines.append(f"- L{heading['line']} {heading['text']}")
            if spec["tasks"]:
                lines.append("")
                lines.append("任务：")
                for task in spec["tasks"][:20]:
                    lines.append(f"- L{task['line']} {task['text']}")
            if spec["key_lines"]:
                lines.append("")
                lines.append("关键约束线索：")
                for key_line in spec["key_lines"][:20]:
                    lines.append(f"- L{key_line['line']} {key_line['text']}")
            lines.append("")
    else:
        lines.append("- 未自动发现需求、设计或任务文档。建议通过 `--spec` 显式指定。")

    lines.extend(["", "## Mermaid 风险图", "", "```mermaid", data["mermaid"].rstrip(), "```", ""])

    lines.extend(["## 人工优先阅读清单", ""])
    if sorted_findings:
        for finding in sorted_findings[:50]:
            lines.append(
                f"- `{finding.severity}` `{finding.file}:{finding.line}` {finding.title}：{finding.message}"
            )
    else:
        lines.append("- 暂无命中。仍建议结合测试和业务规则做人工抽查。")

    lines.extend(["", "## 详细风险命中", ""])
    if sorted_findings:
        for finding in sorted_findings[:200]:
            lines.extend(
                [
                    f"### `{finding.severity}` {finding.title}",
                    "",
                    f"- 位置：`{finding.file}:{finding.line}`",
                    f"- 类型：{finding.category}",
                    f"- 原因：{finding.message}",
                    f"- 代码：`{finding.snippet}`",
                    "",
                ]
            )
        if len(sorted_findings) > 200:
            lines.append(f"其余 {len(sorted_findings) - 200} 条命中请查看 JSON 证据包。")
    else:
        lines.append("- 未发现详细风险命中。")

    lines.extend(["", "## 建议验证", ""])
    lines.extend(
        [
            "- 对 `critical` 和 `high` 位置做人工阅读。",
            "- 对网络调用核对内外部寻址、超时、重试和鉴权。",
            "- 对数据库写入核对事务、条件、并发和幂等。",
            "- 对权限、状态、金额、库存相关路径补充回归测试。",
            "- 将项目隐式规则沉淀为 `--rules` 可执行规则，降低下次误漏。",
        ]
    )

    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="代码变更检查工具")
    parser.add_argument("--project", default=".", help="目标项目目录")
    parser.add_argument("--baseline", help="目录快照模式下的旧版本目录")
    parser.add_argument("--base-ref", help="Git 基准引用，例如 main、HEAD~3 或某个 tag")
    parser.add_argument("--target-ref", help="Git 目标引用，默认 HEAD")
    parser.add_argument("--svn-revision", help="SVN 版本范围，例如 100:120")
    parser.add_argument("--interactive", action="store_true", help="交互式选择本次迭代包含的 Git 提交或 SVN 版本")
    parser.add_argument("--commit-limit", type=int, default=30, help="交互模式展示的最近提交/版本数量")
    parser.add_argument("--spec", action="append", default=[], help="需求、设计或任务文档，可重复传入")
    parser.add_argument("--rules", help="自定义 JSON 风险规则文件")
    parser.add_argument("--output", default="code-change-check-output", help="报告输出目录")
    parser.add_argument("--scan-all", action="store_true", help="忽略变更文件限制，扫描项目内所有文本代码")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    project = Path(args.project).resolve()
    baseline = Path(args.baseline).resolve() if args.baseline else None
    output = Path(args.output).resolve()

    if not project.exists() or not project.is_dir():
        print(f"项目目录不存在：{project}", file=sys.stderr)
        return 2
    if baseline is not None and (not baseline.exists() or not baseline.is_dir()):
        print(f"baseline 目录不存在：{baseline}", file=sys.stderr)
        return 2

    rules_path = Path(args.rules).resolve() if args.rules else None
    patterns = DEFAULT_RISK_PATTERNS + load_custom_patterns(rules_path)
    if args.interactive:
        changes = collect_interactive_changes(project, args.commit_limit)
    else:
        changes = collect_changes(project, baseline, args.base_ref, args.target_ref, args.svn_revision)
    spec_files = discover_spec_files(project, args.spec)
    specs = extract_spec_summary(project, spec_files)
    findings = scan_files(project, changes["changed_files"], args.scan_all, patterns)

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project": str(project),
        "changes": changes,
        "specs": specs,
        "findings": [dataclasses.asdict(finding) for finding in findings],
        "summary": summarize_findings(findings),
        "mermaid": build_mermaid(findings),
    }

    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "code-change-check-evidence.json"
    report_path = output / "code-change-check-report.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(make_report(data), encoding="utf-8")

    print(f"已生成证据包：{json_path}")
    print(f"已生成报告：{report_path}")
    if findings:
        print(f"风险命中数：{len(findings)}")
    else:
        print("未发现内置风险命中。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
