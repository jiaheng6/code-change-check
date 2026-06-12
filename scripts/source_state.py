#!/usr/bin/env python3
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable, Iterator


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


def _unsupported(message: str, target: dict | None = None) -> dict:
    return {
        "status": "partial",
        "message": message,
        "baseline": None,
        "target": target or {"kind": "current", "value": "current-working-tree"},
    }


def _svn_url(project: Path, command_runner: CommandRunner) -> str:
    code, output = command_runner(["svn", "info", "--show-item", "url"], project)
    if code == 0 and output.strip():
        return output.strip().splitlines()[-1]
    code, output = command_runner(["svn", "info"], project)
    if code != 0:
        return ""
    for line in output.splitlines():
        if line.startswith("URL:"):
            return line.split(":", 1)[1].strip()
    return ""


def resolve_source_states(
    project: Path,
    changes: dict,
    baseline_path: Path | None = None,
    command_runner: CommandRunner = run_command,
) -> dict:
    source = changes.get("source", "")
    range_value = str(changes.get("range", ""))
    selected = changes.get("selected_commits") or []

    if source == "git":
        if selected:
            oldest = selected[-1]["id"]
            newest = selected[0]["id"]
            code, output = command_runner(["git", "rev-parse", f"{oldest}^"], project)
            if code != 0 or not output.strip():
                return _unsupported(
                    "无法解析最早选中提交的父提交，不能构造 baseline。",
                    {"kind": "git-ref", "value": newest},
                )
            return {
                "status": "success",
                "message": "已解析选中 Git 提交的 baseline 和 target。",
                "baseline": {"kind": "git-ref", "value": output.splitlines()[-1].strip()},
                "target": {"kind": "git-ref", "value": newest},
            }
        if ".." in range_value:
            baseline, target = range_value.split("..", 1)
            if baseline and target:
                return {
                    "status": "success",
                    "message": "已解析 Git baseline 和 target。",
                    "baseline": {"kind": "git-ref", "value": baseline},
                    "target": {"kind": "git-ref", "value": target},
                }
        if range_value == "working-tree":
            return {
                "status": "success",
                "message": "将比较 HEAD 和当前工作区。",
                "baseline": {"kind": "git-ref", "value": "HEAD"},
                "target": {"kind": "current", "value": "current-working-tree"},
            }
        return _unsupported("当前 Git 范围不足以构造 baseline/target。")

    if source == "snapshot":
        baseline = baseline_path
        if baseline is None and ".." in range_value:
            raw = range_value.split("..", 1)[0]
            baseline = Path(raw) if raw else None
        if baseline is not None and baseline.exists() and baseline.is_dir():
            return {
                "status": "success",
                "message": "将比较目录快照和当前工作区。",
                "baseline": {"kind": "snapshot", "value": str(baseline.resolve())},
                "target": {"kind": "current", "value": "current-working-tree"},
            }
        return _unsupported("未提供有效目录快照 baseline。")

    if source == "svn":
        if ":" not in range_value:
            return _unsupported("SVN 范围缺少起止 revision。")
        start_text, end_text = range_value.split(":", 1)
        try:
            start = int(start_text)
            end = int(end_text)
        except ValueError:
            return _unsupported("SVN revision 范围格式无效。")
        url = _svn_url(project, command_runner)
        if not url:
            return _unsupported("无法解析 SVN 仓库 URL，不能可靠物化 baseline/target。")
        return {
            "status": "success",
            "message": "已解析 SVN baseline 和 target。",
            "baseline": {"kind": "svn-revision", "value": str(max(0, start - 1)), "url": url},
            "target": {"kind": "svn-revision", "value": str(end), "url": url},
        }

    if baseline_path is not None and baseline_path.is_dir():
        return {
            "status": "success",
            "message": "将比较目录快照和当前工作区。",
            "baseline": {"kind": "snapshot", "value": str(baseline_path.resolve())},
            "target": {"kind": "current", "value": "current-working-tree"},
        }
    return _unsupported("当前变更来源无法构造 baseline/target。")


@contextmanager
def materialize_source_state(
    project: Path,
    descriptor: dict,
    command_runner: CommandRunner = run_command,
) -> Iterator[Path]:
    kind = descriptor.get("kind")
    if kind == "current":
        yield project.resolve()
        return
    if kind == "snapshot":
        source = Path(descriptor["value"]).resolve()
        if not source.is_dir():
            raise ValueError(f"目录快照不存在：{source}")
        yield source
        return

    prefix = "code-change-check-source-"
    with tempfile.TemporaryDirectory(prefix=prefix) as temp_dir:
        source = Path(temp_dir) / "source"
        if kind == "git-ref":
            code, output = command_runner(
                ["git", "worktree", "add", "--detach", str(source), descriptor["value"]],
                project,
            )
            if code != 0:
                raise RuntimeError(f"无法物化 Git revision {descriptor['value']}：{output}")
            try:
                yield source
            finally:
                command_runner(["git", "worktree", "remove", "--force", str(source)], project)
                command_runner(["git", "worktree", "prune"], project)
            return
        if kind == "svn-revision":
            command = [
                "svn",
                "export",
                "--force",
                "-r",
                str(descriptor["value"]),
                str(descriptor["url"]),
                str(source),
            ]
            code, output = command_runner(command, project)
            if code != 0:
                raise RuntimeError(f"无法物化 SVN revision {descriptor['value']}：{output}")
            yield source
            return
        raise ValueError(f"不支持的源代码状态类型：{kind}")
