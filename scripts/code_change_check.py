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


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from contract_rules import evaluate_contracts
from delivery_assessment import build_delivery_assessment
from html_report import make_html_report
from java_analysis import disabled_java_analysis_result, run_java_analysis
from semantic_inventory import extract_text_inventory
from audit_plan import apply_audit_plan, build_audit_plan, confirm_audit_plan, load_audit_plan, save_audit_plan
from audit_coverage import (
    assess_audit_coverage,
    build_manual_review_obligations,
    discover_referenced_json_artifacts,
    validate_contract_snapshot_roles,
)
from finding_filter import partition_findings, summarize_suppressed


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
    ".code-change-check",
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

CONTRACT_GLOBS = [
    "contracts/**/*.md",
    "contracts/**/*.json",
    "contracts/**/*.yaml",
    "contracts/**/*.yml",
    "docs/**/*contract*.md",
    "docs/**/*契约*.md",
    "*contract*.md",
    "*契约*.md",
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
    source: str = "text-rule"
    file_role: str = "production"
    suppression_reason: str = ""


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
    normalized = raw.replace("\ufeff", "").replace("，", ",")
    for part in re.findall(r"\d+(?:-\d+)?", normalized):
        try:
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
        except ValueError:
            continue
    return selected


def stream_is_tty(stream) -> bool:
    is_tty = getattr(stream, "isatty", None)
    if not callable(is_tty):
        return False
    try:
        return bool(is_tty())
    except OSError:
        return False


def can_use_terminal_interaction(stdin=None, stdout=None) -> bool:
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    return stream_is_tty(stdin) and stream_is_tty(stdout)


def choose_items(title: str, items: list[str]) -> list[str]:
    if not items:
        print("没有可选择的记录。")
        return []
    if can_use_terminal_interaction():
        return run_multiselect(title, items, read_terminal_key, sys.stdout)

    print(title)
    for index, item in enumerate(items, start=1):
        print(f"[{index}] {item}")
    try:
        raw = input("请输入序号，支持 1,2,3 或 1-5：").strip()
    except EOFError:
        print("未收到输入，已跳过本次选择。")
        return []
    selected_indexes = parse_number_selection(raw, len(items))
    return [item for index, item in enumerate(items) if index in selected_indexes]


def is_git_repo(project: Path) -> bool:
    code, _ = run_command(["git", "rev-parse", "--is-inside-work-tree"], project)
    return code == 0


def git_working_tree_root(project: Path) -> Path | None:
    code, output = run_command(["git", "rev-parse", "--show-toplevel"], project)
    if code != 0 or not output.strip():
        return None
    return Path(output.strip()).resolve()


def parse_svn_info(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def svn_working_copy_root(project: Path) -> Path | None:
    code, output = run_command(["svn", "info", "--show-item", "wc-root"], project)
    if code == 0 and output.strip():
        return Path(output.strip()).resolve()

    code, output = run_command(["svn", "info"], project)
    if code != 0:
        return None
    parsed = parse_svn_info(output)
    root = parsed.get("Working Copy Root Path")
    if not root:
        return None
    return Path(root).resolve()


def is_svn_repo(project: Path) -> bool:
    return svn_working_copy_root(project) is not None


def find_svn_metadata_root(project: Path) -> Path | None:
    current = project.resolve()
    candidate = None
    while True:
        if (current / ".svn").exists():
            candidate = current
        elif candidate is not None:
            break
        if current.parent == current:
            break
        current = current.parent
    return candidate


def probe_svn_working_copy(project: Path) -> dict:
    code, output = run_command(["svn", "info", "--show-item", "wc-root"], project)
    if code == 0 and output.strip():
        return {"status": "svn", "root": Path(output.strip()).resolve(), "detail": ""}

    fallback_code, fallback_output = run_command(["svn", "info"], project)
    if fallback_code == 0:
        parsed = parse_svn_info(fallback_output)
        root = parsed.get("Working Copy Root Path")
        if root:
            return {"status": "svn", "root": Path(root).resolve(), "detail": ""}

    metadata_root = find_svn_metadata_root(project)
    if metadata_root is not None:
        detail = fallback_output or output
        return {"status": "svn-incompatible", "root": metadata_root, "detail": detail}
    return {"status": "none", "root": None, "detail": fallback_output or output}


def is_relative_to_path(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def detect_repository_context(project: Path) -> dict:
    project_path = project.resolve()
    git_root = git_working_tree_root(project_path)
    if git_root is not None:
        is_root = project_path == git_root
        return {
            "vcs": "git",
            "project": str(project_path),
            "root": str(git_root),
            "project_is_vcs_root": is_root,
            "recommended_project": str(git_root if is_relative_to_path(project_path, git_root) else project_path),
            "message": "当前目录是 Git 工作树根目录。"
            if is_root
            else "当前目录是 Git 工作树子目录，请先确认审计当前目录还是 Git 工作树根目录。",
        }

    svn_probe = probe_svn_working_copy(project_path)
    svn_root = svn_probe["root"]
    if svn_probe["status"] == "svn" and svn_root is not None:
        is_root = project_path == svn_root
        return {
            "vcs": "svn",
            "project": str(project_path),
            "root": str(svn_root),
            "project_is_vcs_root": is_root,
            "recommended_project": str(svn_root if is_relative_to_path(project_path, svn_root) else project_path),
            "message": "当前目录是 SVN 工作副本根目录。"
            if is_root
            else "当前目录是 SVN 工作副本子目录，请先确认审计当前目录还是 SVN 工作副本根目录。",
        }
    if svn_probe["status"] == "svn-incompatible" and svn_root is not None:
        is_root = project_path == svn_root
        return {
            "vcs": "svn-incompatible",
            "project": str(project_path),
            "root": str(svn_root),
            "project_is_vcs_root": is_root,
            "recommended_project": str(svn_root),
            "message": "检测到 SVN 元数据，但当前 SVN 客户端无法读取该工作副本。请先确认是否升级工作副本或降级为目录快照审计。",
            "detail": svn_probe["detail"],
        }

    return {
        "vcs": "none",
        "project": str(project_path),
        "root": "",
        "project_is_vcs_root": False,
        "recommended_project": str(project_path),
        "message": "当前目录未检测到 Git 或 SVN 工作副本，建议使用目录快照或显式指定项目根目录。",
    }


def validate_repository_context_for_run(context: dict, args: argparse.Namespace) -> str | None:
    if context.get("vcs") != "svn-incompatible":
        return None
    if args.scan_all or args.baseline:
        return None
    return (
        "检测到 SVN 元数据，但当前 SVN 客户端无法读取工作副本。"
        "请先使用 --print-context 查看详情，并显式选择 --scan-all 目录快照审计、提供 --baseline，"
        "或在用户确认后处理 SVN 客户端兼容问题。"
    )


def normalize_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def filter_changed_files(paths: Iterable[str]) -> list[str]:
    return sorted(
        {
            path
            for path in paths
            if path and not should_skip(Path(path.replace("\\", "/")))
        }
    )


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


def project_has_java(root: Path) -> bool:
    return any(path.suffix.lower() == ".java" for path in iter_project_files(root))


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
        "changed_files": filter_changed_files(changed),
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
        "changed_files": filter_changed_files(changed),
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
    if status_code == 0 and not base_ref:
        for line in status.splitlines():
            if len(line) > 3:
                changed.add(line[3:].strip().strip('"'))

    return {
        "source": "git",
        "range": range_ref,
        "status": status,
        "stat": stat if stat_code == 0 else "",
        "diff": diff if diff_code == 0 else "",
        "changed_files": filter_changed_files(changed),
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
    if status_code == 0 and not svn_revision:
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
        "changed_files": filter_changed_files(changed),
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
        "changed_files": filter_changed_files(changed),
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


def expand_explicit_files(project: Path, entries: list[str], suffixes: set[str]) -> list[Path]:
    result: list[Path] = []
    for entry in entries:
        path = Path(entry)
        if not path.is_absolute():
            path = project / path
        candidates = [path] if path.exists() else list(project.glob(entry))
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() in suffixes:
                result.append(candidate)
            elif candidate.is_dir():
                result.extend(
                    item
                    for item in candidate.rglob("*")
                    if item.is_file() and item.suffix.lower() in suffixes
                )
    return sorted({path.resolve() for path in result}, key=lambda path: path.as_posix())


def discover_spec_files(project: Path, explicit_specs: list[str], strict: bool = False) -> list[Path]:
    result = expand_explicit_files(project, explicit_specs, {".md"})
    if strict:
        return result

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


def build_requirement_items(specs: list[dict]) -> list[dict]:
    items = []
    kinds = [
        ("headings", "heading", "标题"),
        ("tasks", "task", "任务"),
        ("key_lines", "constraint", "约束"),
    ]
    for spec in specs:
        file = spec["file"]
        for source_key, kind, kind_label in kinds:
            for source_item in spec.get(source_key, []):
                item_id = f"R{len(items) + 1}"
                text = source_item["text"].strip()
                line = source_item["line"]
                label = f"{item_id} {kind_label} {file}:L{line} {text[:120]}"
                items.append(
                    {
                        "id": item_id,
                        "kind": kind,
                        "kind_label": kind_label,
                        "file": file,
                        "line": line,
                        "text": text,
                        "label": label,
                    }
                )
    return items


def create_requirement_commit_mappings(
    commits: list[dict],
    requirements: list[dict],
    choose_for_commit=None,
) -> list[dict]:
    if not commits or not requirements:
        return []
    labels = [requirement["label"] for requirement in requirements]
    label_to_requirement = {requirement["label"]: requirement for requirement in requirements}
    mappings = []
    for commit in commits:
        if choose_for_commit is None:
            title = f"请选择提交 {commit.get('short_id', commit.get('id', ''))} 对应的需求/任务"
            selected_labels = choose_items(title, labels)
        else:
            selected_labels = choose_for_commit(commit, labels)
        selected_requirements = [
            label_to_requirement[label]
            for label in selected_labels
            if label in label_to_requirement
        ]
        mappings.append(
            {
                "commit": commit,
                "requirements": selected_requirements,
            }
        )
    return mappings


def resolve_contract_source_selection(selected_labels: list[str]) -> str:
    has_file = any("指定契约文件" in label for label in selected_labels)
    has_existing = any("旧代码" in label or "已有代码" in label for label in selected_labels)
    has_none = any("不使用" in label for label in selected_labels)
    if has_none:
        return "none"
    if has_file and has_existing:
        return "both"
    if has_file:
        return "file"
    if has_existing:
        return "existing-code"
    return "none"


def choose_contract_source() -> str:
    labels = [
        "使用指定契约文件",
        "从旧代码自动提取",
        "本次先不使用业务契约",
    ]
    selected = choose_items("请选择业务契约来源", labels)
    return resolve_contract_source_selection(selected)


def discover_contract_files(project: Path, explicit_contracts: list[str], strict: bool = False) -> list[Path]:
    result = expand_explicit_files(project, explicit_contracts, {".md", ".json", ".yaml", ".yml"})
    if strict:
        return result

    seen = {p.resolve() for p in result}
    for pattern in CONTRACT_GLOBS:
        for path in project.glob(pattern):
            if path.is_file() and path.resolve() not in seen and not should_skip(path.relative_to(project)):
                seen.add(path.resolve())
                result.append(path)
    return result


def renumber_contracts(contracts: list[dict]) -> list[dict]:
    result = []
    for index, contract in enumerate(contracts, start=1):
        item = dict(contract)
        item["id"] = f"C{index}"
        result.append(item)
    return result


def extract_contracts_from_text(file: str, text: str, source: str = "contract-file") -> list[dict]:
    contract_re = re.compile(
        r"(必须|不能|不得|禁止|只允许|应当|需要|参数|字段|格式|顺序|兼容|internalBaseUrl|publicBaseUrl|tenantId|签名|幂等|状态|枚举)"
    )
    contracts = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if contract_re.search(stripped):
            contracts.append(
                {
                    "id": f"C{len(contracts) + 1}",
                    "source": source,
                    "file": file,
                    "line": line_number,
                    "kind": "text-rule",
                    "text": stripped[:300],
                }
            )
    return contracts


def json_shape_paths(value: object, prefix: str = "") -> list[str]:
    paths = []
    if isinstance(value, dict):
        for key in sorted(value):
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.append(path)
            paths.extend(json_shape_paths(value[key], path))
    elif isinstance(value, list):
        array_path = f"{prefix}[]" if prefix else "[]"
        paths.append(array_path)
        for item in value:
            paths.extend(json_shape_paths(item, array_path))
    return sorted(set(paths))


def json_shape_constants(
    value: object,
    prefix: str = "",
    collected: dict[str, set[str]] | None = None,
) -> dict[str, str]:
    collected = collected if collected is not None else {}
    if isinstance(value, dict):
        for key in sorted(value):
            path = f"{prefix}.{key}" if prefix else str(key)
            json_shape_constants(value[key], path, collected)
    elif isinstance(value, list):
        array_path = f"{prefix}[]" if prefix else "[]"
        for item in value:
            json_shape_constants(item, array_path, collected)
    elif isinstance(value, str) and prefix.rsplit(".", 1)[-1].lower() == "label":
        collected.setdefault(prefix, set()).add(value)
    return {
        path: next(iter(values))
        for path, values in sorted(collected.items())
        if len(values) == 1
    }


def extract_json_shape_contract(file: str, text: str) -> dict | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    paths = json_shape_paths(value)
    return {
        "id": "C1",
        "source": "contract-file",
        "file": file,
        "line": 1,
        "kind": "json-shape",
        "match_key": Path(file).stem.lower(),
        "text": f"JSON 响应形状契约，共 {len(paths)} 个字段路径。",
        "shape": {
            "paths": paths,
            "constants": json_shape_constants(value),
        },
    }


def extract_contracts_from_files(project: Path, contract_files: list[Path]) -> list[dict]:
    contracts = []
    for path in contract_files:
        file = normalize_relative(path, project)
        text = read_text(path)
        if path.suffix.lower() == ".json":
            contract = extract_json_shape_contract(file, text)
            if contract:
                contracts.append(contract)
                continue
        contracts.extend(
            extract_contracts_from_text(
                file,
                text,
                source="contract-file",
            )
        )
    return renumber_contracts(contracts)


def load_response_snapshots(project: Path, entries: list[str]) -> dict[str, dict]:
    snapshots = {}
    for path in expand_explicit_files(project, entries, {".json"}):
        try:
            value = json.loads(read_text(path))
        except (OSError, json.JSONDecodeError):
            continue
        snapshots[path.stem.lower()] = {
            "file": normalize_relative(path, project),
            "paths": json_shape_paths(value),
            "constants": json_shape_constants(value),
        }
    return snapshots


def extract_contracts_from_code_text(file: str, text: str, source: str) -> list[dict]:
    contracts = []
    seen = set()

    def add_contract(line_number: int, kind: str, contract_text: str) -> None:
        key = (kind, contract_text)
        if key in seen:
            return
        seen.add(key)
        contracts.append(
            {
                "id": f"C{len(contracts) + 1}",
                "source": source,
                "file": file,
                "line": line_number,
                "kind": kind,
                "text": contract_text,
            }
        )

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if "internalBaseUrl" in stripped:
            add_contract(line_number, "addressing", f"已有代码使用 internalBaseUrl 作为内部寻址线索：{stripped[:180]}")
        if "publicBaseUrl" in stripped:
            add_contract(line_number, "addressing", f"已有代码使用 publicBaseUrl 作为外部寻址线索：{stripped[:180]}")
        if "tenantId" in stripped or "tenant_id" in stripped:
            add_contract(line_number, "tenant", f"已有代码包含租户隔离字段线索：{stripped[:180]}")
        if re.search(r"\b(status|state)\b", stripped, re.IGNORECASE):
            add_contract(line_number, "state", f"已有代码包含状态字段线索：{stripped[:180]}")
    for item in extract_text_inventory(file, text):
        if item.get("kind") != "call":
            continue
        call_name = item.get("symbol", "")
        if re.search(r"[A-Z][A-Za-z0-9_]*(?:Client|Service|Helper|Adapter)\.[A-Za-z_][A-Za-z0-9_]*$", call_name):
            add_contract(
                int(item.get("line", 1)),
                "call-shape",
                f"已有调用约定 {call_name} 参数数量 {item.get('argument_count', 0)}，参数：{', '.join(item.get('arguments', []))[:160]}",
            )
    return contracts


def extract_contracts_from_existing_code(project: Path, candidate_files: list[str] | None = None) -> list[dict]:
    if candidate_files:
        files = []
        for rel_path in candidate_files:
            path = project / rel_path
            if path.exists() and path.is_file() and is_text_file(path) and not should_skip(path.relative_to(project)):
                files.append(path)
    else:
        files = list(iter_project_files(project))

    contracts = []
    for path in files:
        try:
            text = read_text(path)
        except OSError:
            continue
        contracts.extend(
            extract_contracts_from_code_text(
                normalize_relative(path, project),
                text,
                source="existing-code-current",
            )
        )
    return renumber_contracts(contracts)


def resolve_previous_revision(project: Path, changes: dict) -> tuple[str, str] | None:
    source = changes.get("source")
    selected = changes.get("selected_commits") or []
    if source == "git":
        if selected:
            oldest_commit = selected[-1]["id"]
            code, output = run_command(["git", "rev-parse", f"{oldest_commit}^"], project)
            if code == 0 and output:
                return "git", output.splitlines()[-1].strip()
        range_ref = changes.get("range", "")
        if ".." in range_ref:
            return "git", range_ref.split("..", 1)[0]
        return "git", "HEAD"
    if source == "svn":
        if selected:
            revisions = [int(item["id"]) for item in selected if str(item.get("id", "")).isdigit()]
            if revisions:
                return "svn", str(max(min(revisions) - 1, 0))
        range_ref = changes.get("range", "")
        if ":" in range_ref:
            start = range_ref.split(":", 1)[0]
            if start.isdigit():
                return "svn", str(max(int(start) - 1, 0))
    if source == "snapshot":
        range_ref = changes.get("range", "")
        if ".." in range_ref:
            baseline = range_ref.split("..", 1)[0]
            if baseline:
                return "snapshot", baseline
    return None


def extract_contracts_from_previous_code(project: Path, changes: dict) -> list[dict]:
    previous = resolve_previous_revision(project, changes)
    if previous is None:
        return []
    source, revision = previous
    contracts = []
    for rel_path in changes.get("changed_files", []):
        if not is_text_file(Path(rel_path)):
            continue
        if source == "git":
            code, text = run_command(["git", "show", f"{revision}:{rel_path}"], project)
        elif source == "svn":
            code, text = run_command(["svn", "cat", "-r", revision, rel_path], project)
        else:
            baseline_path = Path(revision) / rel_path
            if not baseline_path.exists() or not baseline_path.is_file():
                continue
            code, text = 0, read_text(baseline_path)
        if code != 0 or not text:
            continue
        contracts.extend(
            extract_contracts_from_code_text(
                rel_path,
                text,
                source=f"existing-code-baseline:{revision}",
            )
        )
    return renumber_contracts(contracts)


def collect_business_contracts(
    project: Path,
    source: str,
    explicit_contracts: list[str],
    changes: dict,
    strict_contract: bool = False,
) -> tuple[str, list[dict]]:
    if source == "interactive":
        source = choose_contract_source()
    if source == "none":
        return source, []

    contracts = []
    if source in {"file", "both"}:
        contract_files = discover_contract_files(project, explicit_contracts, strict=strict_contract)
        contracts.extend(extract_contracts_from_files(project, contract_files))
    if source in {"existing-code", "both"}:
        if resolve_previous_revision(project, changes) is not None:
            contracts.extend(extract_contracts_from_previous_code(project, changes))
        else:
            contracts.extend(extract_contracts_from_existing_code(project, changes.get("changed_files") or None))
    return source, renumber_contracts(contracts)


def confirm_business_contracts(contracts: list[dict], choose_contracts=None) -> list[dict]:
    if not contracts:
        return []
    labels = [
        f"{contract['id']} {contract['source']} {contract['kind']} {contract['file']}:L{contract['line']} {contract['text'][:120]}"
        for contract in contracts
    ]
    if choose_contracts is None:
        selected_labels = choose_items("请选择本次审计启用的业务契约", labels)
    else:
        selected_labels = choose_contracts(labels)
    selected_set = set(selected_labels)
    return [contract for label, contract in zip(labels, contracts) if label in selected_set]


def semantic_changes_to_findings(changes: list[dict]) -> list[Finding]:
    return [
        Finding(
            id=f"semantic:{change.get('type', 'unknown')}",
            title=f"业务语义变化：{change.get('symbol', change.get('type', ''))}",
            severity=change.get("severity", "high"),
            category="业务语义",
            file=change.get("file", ""),
            line=int(change.get("line", 1)),
            snippet=change.get("symbol", "")[:240],
            message=change.get("message", "发现业务语义变化。"),
            source="semantic-diff",
        )
        for change in changes
    ]


def contract_violations_to_findings(violations: list[dict]) -> list[Finding]:
    return [
        Finding(
            id=violation.get("id", "contract:unknown"),
            title=f"业务契约违反：{violation.get('type', 'unknown')}",
            severity=violation.get("severity", "high"),
            category="业务契约",
            file=violation.get("file", ""),
            line=int(violation.get("line", 1)),
            snippet=violation.get("actual", "")[:240],
            message=violation.get("message", "发现业务契约违反。"),
            source="business-contract",
        )
        for violation in violations
    ]


def java_analysis_target_inventory(java_analysis: dict) -> dict | None:
    core = java_analysis.get("target", {}).get("core", {})
    if not core:
        return None
    return {
        "status": core.get("status", "failed"),
        "engine": "spoon",
        "message": core.get("message", ""),
        "errors": core.get("errors", []),
        "items": core.get("evidence", []),
    }


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



def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="代码变更检查工具")
    parser.add_argument("--project", default=".", help="目标项目目录")
    parser.add_argument("--baseline", help="目录快照模式下的旧版本目录")
    parser.add_argument("--base-ref", help="Git 基准引用，例如 main、HEAD~3 或某个 tag")
    parser.add_argument("--target-ref", help="Git 目标引用，默认 HEAD")
    parser.add_argument("--svn-revision", help="SVN 版本范围，例如 100:120")
    interactive_group = parser.add_mutually_exclusive_group()
    interactive_group.add_argument("--interactive", action="store_true", help="交互式选择本次迭代包含的 Git 提交或 SVN 版本")
    interactive_group.add_argument("--no-interactive", action="store_true", help="关闭启动器默认交互，适合 CI 或脚本自动化")
    parser.add_argument("--commit-limit", type=int, default=30, help="交互模式展示的最近提交/版本数量")
    parser.add_argument("--map-requirements", action="store_true", help="为选中的提交交互式关联需求/任务")
    parser.add_argument("--no-map-requirements", action="store_true", help="交互模式下跳过需求-提交映射")
    parser.add_argument("--spec", action="append", default=[], help="需求、设计或任务文档，可重复传入")
    parser.add_argument("--strict-spec", action="store_true", help="只使用显式指定的需求、设计或任务文档")
    parser.add_argument("--contract", action="append", default=[], help="业务契约文件，可重复传入")
    parser.add_argument("--strict-contract", action="store_true", help="只使用显式指定的业务契约文件")
    parser.add_argument(
        "--contract-source",
        choices=["interactive", "file", "existing-code", "both", "none"],
        default=None,
        help="业务契约来源：交互选择、指定文件、已有代码、两者都用或不使用",
    )
    parser.add_argument("--no-contract", action="store_true", help="跳过业务契约提取")
    parser.add_argument("--confirm-contracts", action="store_true", help="交互确认本次审计启用的候选契约")
    parser.add_argument("--no-confirm-contracts", action="store_true", help="跳过候选契约确认并启用全部候选契约")
    parser.add_argument("--rules", help="自定义 JSON 风险规则文件")
    parser.add_argument(
        "--java-analysis",
        choices=["auto", "required", "off"],
        default="auto",
        help="Java 语义分析模式：自动执行、必须成功或关闭",
    )
    parser.add_argument("--tool-cache", help="指定 Java 分析运行时和辅助工具缓存目录")
    parser.add_argument("--offline", action="store_true", help="离线模式，不自动下载任何运行时")
    parser.add_argument("--output", default="code-change-check-output", help="报告输出目录")
    parser.add_argument(
        "--format",
        choices=["html"],
        default="html",
        help="报告输出格式：当前仅生成 HTML 报告",
    )
    parser.add_argument("--scan-all", action="store_true", help="忽略变更文件限制，扫描项目内所有文本代码")
    parser.add_argument("--include-support-findings", action="store_true", help="把测试、文档、调试和 fixture 文本命中纳入正式风险")
    parser.add_argument("--response-snapshot", action="append", default=[], help="用于 JSON 契约结构化对比的实际响应快照，可重复传入")
    parser.add_argument("--print-context", action="store_true", help="输出项目版本控制上下文后退出，供 AI 适配器预检")
    parser.add_argument("--audit-plan", help="从已确认的审计计划 JSON 执行")
    parser.add_argument("--save-audit-plan", help="把当前显式参数保存为审计计划 JSON 后退出")
    parser.add_argument("--confirm-audit-plan", help="确认审计计划 JSON，确认后才能通过计划执行")
    return parser.parse_args(argv)


def has_explicit_change_scope(args: argparse.Namespace) -> bool:
    return bool(
        args.baseline
        or args.base_ref
        or args.target_ref
        or args.svn_revision
        or args.scan_all
        or args.print_context
    )


def apply_default_interactive(args: argparse.Namespace, stdin=None, stdout=None) -> bool:
    if args.interactive or args.no_interactive:
        return False
    if has_explicit_change_scope(args):
        return False
    if not can_use_terminal_interaction(stdin, stdout):
        return False
    args.interactive = True
    return True


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    loaded_audit_plan = None
    audit_plan_path = ""
    if args.confirm_audit_plan:
        try:
            plan_path = Path(args.confirm_audit_plan).resolve()
            confirm_audit_plan(plan_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"无法确认审计计划：{error}", file=sys.stderr)
            return 2
        print(f"已确认审计计划：{plan_path}")
        return 0
    if args.audit_plan:
        try:
            audit_plan_path = str(Path(args.audit_plan).resolve())
            loaded_audit_plan = load_audit_plan(Path(audit_plan_path))
            apply_audit_plan(args, loaded_audit_plan)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"无法加载审计计划：{error}", file=sys.stderr)
            return 2
    apply_default_interactive(args)
    project = Path(args.project).resolve()
    baseline = Path(args.baseline).resolve() if args.baseline else None
    output = Path(args.output).resolve()

    if not project.exists() or not project.is_dir():
        print(f"项目目录不存在：{project}", file=sys.stderr)
        return 2
    if args.save_audit_plan:
        plan_path = Path(args.save_audit_plan).resolve()
        save_audit_plan(plan_path, build_audit_plan(args))
        print(f"已生成审计计划：{plan_path}")
        return 0
    if args.print_context:
        print(json.dumps(detect_repository_context(project), ensure_ascii=False, indent=2))
        return 0
    if baseline is not None and (not baseline.exists() or not baseline.is_dir()):
        print(f"baseline 目录不存在：{baseline}", file=sys.stderr)
        return 2
    repository_context_error = validate_repository_context_for_run(detect_repository_context(project), args)
    if repository_context_error:
        print(repository_context_error, file=sys.stderr)
        return 2

    rules_path = Path(args.rules).resolve() if args.rules else None
    patterns = DEFAULT_RISK_PATTERNS + load_custom_patterns(rules_path)
    if args.interactive:
        changes = collect_interactive_changes(project, args.commit_limit)
    else:
        changes = collect_changes(project, baseline, args.base_ref, args.target_ref, args.svn_revision)
    has_java = project_has_java(project)
    java_analysis = disabled_java_analysis_result()
    if has_java and args.java_analysis != "off":
        cache_root = Path(args.tool_cache).expanduser().resolve() if args.tool_cache else None
        java_analysis = run_java_analysis(
            project,
            changes,
            output / "java-analysis",
            baseline_path=baseline,
            tool_cache=cache_root,
            offline=args.offline,
        )
    spec_files = discover_spec_files(project, args.spec, strict=args.strict_spec)
    specs = extract_spec_summary(project, spec_files)
    requirement_items = build_requirement_items(specs)
    should_map_requirements = (
        bool(changes.get("selected_commits"))
        and requirement_items
        and not args.no_map_requirements
        and (args.interactive or args.map_requirements)
    )
    requirement_commit_mappings = (
        create_requirement_commit_mappings(changes.get("selected_commits", []), requirement_items)
        if should_map_requirements
        else []
    )
    contract_source = "none"
    if not args.no_contract:
        contract_source = args.contract_source or ("interactive" if args.interactive else ("file" if args.contract else "none"))
    contract_source, contract_candidates = collect_business_contracts(
        project,
        contract_source,
        args.contract,
        changes,
        strict_contract=args.strict_contract,
    )
    should_confirm_contracts = (
        bool(contract_candidates)
        and not args.no_confirm_contracts
        and (args.interactive or args.confirm_contracts)
    )
    business_contracts = (
        confirm_business_contracts(contract_candidates)
        if should_confirm_contracts
        else contract_candidates
    )
    contract_files = (
        discover_contract_files(project, args.contract, strict=args.strict_contract)
        if contract_source in {"file", "both"}
        else []
    )
    response_snapshot_files = expand_explicit_files(project, args.response_snapshot, {".json"})
    role_validation = validate_contract_snapshot_roles(
        [path for path in contract_files if path.suffix.lower() == ".json"],
        response_snapshot_files,
    )
    target_inventory = None
    if business_contracts:
        target_inventory = java_analysis_target_inventory(java_analysis)
    response_snapshots = load_response_snapshots(
        project,
        [str(path) for path in role_validation["valid_snapshot_files"]],
    )
    business_contract_check = evaluate_contracts(
        business_contracts,
        target_inventory,
        response_snapshots,
    )
    referenced_artifacts = discover_referenced_json_artifacts(
        project,
        spec_files + [path for path in contract_files if path.suffix.lower() == ".md"],
        contract_files,
    )
    manual_review_obligations = build_manual_review_obligations(
        project,
        business_contract_check.get("unchecked_contracts", []),
        business_contracts,
    )
    audit_coverage = assess_audit_coverage(
        changes=changes,
        contract_check=business_contract_check,
        java_analysis=java_analysis,
        role_issues=role_validation["issues"],
        missing_referenced_artifacts=referenced_artifacts["missing"],
        manual_review_obligations=manual_review_obligations,
    )
    findings = scan_files(project, changes["changed_files"], args.scan_all, patterns)
    findings.extend(contract_violations_to_findings(business_contract_check.get("violations", [])))
    findings.extend(semantic_changes_to_findings(java_analysis.get("findings", [])))

    raw_finding_data = [dataclasses.asdict(finding) for finding in findings]
    active_finding_data, suppressed_findings = partition_findings(
        raw_finding_data,
        include_support=args.include_support_findings,
    )
    findings = [Finding(**item) for item in active_finding_data]
    effective_audit_plan = dict(loaded_audit_plan) if loaded_audit_plan else build_audit_plan(args)
    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project": str(project),
        "audit_plan": {
            "path": audit_plan_path,
            "confirmed": bool(loaded_audit_plan and loaded_audit_plan.get("confirmed")),
            "effective": effective_audit_plan,
        },
        "changes": changes,
        "specs": specs,
        "requirement_items": requirement_items,
        "requirement_commit_mappings": requirement_commit_mappings,
        "contract_source": contract_source,
        "contract_candidates": contract_candidates,
        "business_contracts": business_contracts,
        "response_snapshots": response_snapshots,
        "input_role_issues": role_validation["issues"],
        "referenced_contract_artifacts": referenced_artifacts["referenced"],
        "missing_referenced_contract_artifacts": referenced_artifacts["missing"],
        "unresolved_contract_references": referenced_artifacts["unresolved"],
        "business_contract_check": business_contract_check,
        "manual_review_obligations": manual_review_obligations,
        "audit_coverage": audit_coverage,
        "java_analysis": java_analysis,
        "findings": active_finding_data,
        "suppressed_findings": suppressed_findings,
        "suppression_summary": summarize_suppressed(suppressed_findings),
        "summary": summarize_findings(findings),
        "mermaid": build_mermaid(findings),
    }
    data["delivery_assessment"] = build_delivery_assessment(data)

    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "evidence.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成证据包：{json_path}")

    for legacy_markdown_path in (output / "report.md", output / "code-change-check-report.md"):
        if legacy_markdown_path.is_file():
            legacy_markdown_path.unlink()
            print(f"已移除旧版 Markdown 报告：{legacy_markdown_path}")

    html_path = output / "report.html"
    html_path.write_text(make_html_report(data), encoding="utf-8")
    print(f"已生成 HTML 报告：{html_path}")
    if findings:
        print(f"风险命中数：{len(findings)}")
    else:
        print("未发现内置风险命中。")
    if suppressed_findings:
        print(f"已抑制文本线索数：{len(suppressed_findings)}，完整证据已写入 JSON。")
    if business_contract_check.get("unchecked_contracts"):
        print(f"未检查业务契约数：{len(business_contract_check['unchecked_contracts'])}。")
    if audit_coverage.get("status") != "success":
        print(f"审计覆盖质量闸门：{audit_coverage.get('status')}，{audit_coverage.get('message')}")
    print(f"Java 语义分析状态：{java_analysis['status']}，{java_analysis['message']}")
    if args.java_analysis == "required" and java_analysis["status"] != "success":
        print("Java 语义分析是本次检查的必需项，但未成功完成。", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
