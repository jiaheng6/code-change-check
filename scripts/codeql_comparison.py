#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack, contextmanager
from pathlib import Path
import tempfile
from typing import Callable, Iterator

from codeql_support import run_codeql_analysis, run_command


CommandRunner = Callable[[list[str], Path], tuple[int, str]]
Analyzer = Callable[..., dict]


def finding_identity(item: dict) -> tuple:
    return (
        item.get("id", ""),
        item.get("file", ""),
        item.get("title", ""),
        item.get("message", ""),
        item.get("snippet", ""),
    )


def compare_codeql_findings(baseline: list[dict], target: list[dict]) -> dict:
    baseline_groups: dict[tuple, list[dict]] = defaultdict(list)
    target_groups: dict[tuple, list[dict]] = defaultdict(list)
    for item in baseline:
        baseline_groups[finding_identity(item)].append(item)
    for item in target:
        target_groups[finding_identity(item)].append(item)

    new_findings = []
    existing_findings = []
    resolved_findings = []
    for key in sorted(set(baseline_groups) | set(target_groups)):
        baseline_items = baseline_groups.get(key, [])
        target_items = target_groups.get(key, [])
        shared_count = min(len(baseline_items), len(target_items))
        existing_findings.extend(target_items[:shared_count])
        new_findings.extend(target_items[shared_count:])
        resolved_findings.extend(baseline_items[shared_count:])
    return {
        "new_findings": new_findings,
        "existing_findings": existing_findings,
        "resolved_findings": resolved_findings,
    }


def unsupported_plan(message: str, target: dict | None = None) -> dict:
    return {
        "status": "unsupported",
        "message": message,
        "baseline": None,
        "target": target or {"kind": "current", "value": "current-working-tree"},
    }


def resolve_codeql_comparison_plan(
    project: Path,
    changes: dict,
    baseline_path: Path | None = None,
    command_runner: CommandRunner = run_command,
) -> dict:
    source = changes.get("source")
    selected = changes.get("selected_commits") or []
    range_ref = changes.get("range", "")

    if source == "git":
        if selected:
            oldest = selected[-1]["id"]
            newest = selected[0]["id"]
            parent_code, parent_output = command_runner(["git", "rev-parse", f"{oldest}^"], project)
            if parent_code != 0 or not parent_output:
                return unsupported_plan(
                    "无法解析最早选中提交的父提交，不能构造 CodeQL baseline。",
                    {"kind": "git-ref", "value": newest},
                )
            parent = parent_output.splitlines()[-1].strip()
            list_code, list_output = command_runner(
                ["git", "rev-list", "--reverse", f"{parent}..{newest}"],
                project,
            )
            actual = [line.strip() for line in list_output.splitlines() if line.strip()] if list_code == 0 else []
            expected = [item["id"] for item in reversed(selected)]
            if actual != expected:
                return unsupported_plan(
                    "选中的 Git 提交属于非连续或非线性范围，暂不构造 CodeQL baseline/target 对比。",
                    {"kind": "git-ref", "value": newest},
                )
            return {
                "status": "ready",
                "message": "将比较连续选中提交的父版本和最新选中提交。",
                "baseline": {"kind": "git-ref", "value": parent},
                "target": {"kind": "git-ref", "value": newest},
            }
        if ".." in range_ref:
            baseline_ref, target_ref = range_ref.split("..", 1)
            if baseline_ref and target_ref:
                return {
                    "status": "ready",
                    "message": "将比较显式 Git baseline 和 target。",
                    "baseline": {"kind": "git-ref", "value": baseline_ref},
                    "target": {"kind": "git-ref", "value": target_ref},
                }
        if range_ref == "working-tree":
            return {
                "status": "ready",
                "message": "将比较 HEAD 和当前工作区。",
                "baseline": {"kind": "git-ref", "value": "HEAD"},
                "target": {"kind": "current", "value": "current-working-tree"},
            }
        return unsupported_plan("当前 Git 变更范围不足以构造 CodeQL baseline/target 对比。")

    if source == "snapshot":
        baseline = baseline_path
        if baseline is None and ".." in range_ref:
            raw_baseline = range_ref.split("..", 1)[0]
            baseline = Path(raw_baseline) if raw_baseline else None
        if baseline is not None and baseline.exists() and baseline.is_dir():
            return {
                "status": "ready",
                "message": "将比较目录快照 baseline 和当前目录。",
                "baseline": {"kind": "snapshot", "value": str(baseline.resolve())},
                "target": {"kind": "current", "value": "current-working-tree"},
            }
        return unsupported_plan("未提供有效目录快照 baseline，不能执行 CodeQL 对比。")

    if source == "svn":
        return unsupported_plan("当前阶段尚未实现 SVN revision 的 CodeQL 源代码物化。")
    return unsupported_plan("当前变更来源不支持 CodeQL baseline/target 对比。")


def source_scope(descriptor: dict, role: str) -> str:
    kind = descriptor["kind"]
    if kind == "current":
        return "current-working-tree"
    if kind == "snapshot":
        return f"snapshot:{role}"
    return f"git:{descriptor['value']}"


@contextmanager
def materialize_codeql_source(
    project: Path,
    descriptor: dict,
    command_runner: CommandRunner = run_command,
) -> Iterator[Path]:
    kind = descriptor["kind"]
    if kind == "current":
        yield project
        return
    if kind == "snapshot":
        yield Path(descriptor["value"]).resolve()
        return
    if kind != "git-ref":
        raise ValueError(f"不支持的 CodeQL 源代码类型：{kind}")

    with tempfile.TemporaryDirectory(prefix="code-change-check-codeql-") as temp_dir:
        source = Path(temp_dir) / "source"
        add_code, add_output = command_runner(
            ["git", "worktree", "add", "--detach", str(source), descriptor["value"]],
            project,
        )
        if add_code != 0:
            raise RuntimeError(f"无法物化 Git revision {descriptor['value']}：{add_output}")
        try:
            yield source
        finally:
            command_runner(["git", "worktree", "remove", "--force", str(source)], project)
            command_runner(["git", "worktree", "prune"], project)


def skipped_comparison(plan: dict) -> dict:
    return {
        "status": plan["status"],
        "message": plan["message"],
        "baseline": plan.get("baseline"),
        "target": plan.get("target"),
        "baseline_status": "",
        "target_status": "",
        "new_findings": [],
        "existing_findings": [],
        "resolved_findings": [],
    }


def run_codeql_review(
    project: Path,
    output: Path,
    changes: dict,
    *,
    baseline_path: Path | None = None,
    compare: bool = True,
    languages: list[str] | None = None,
    executable: str = "codeql",
    build_mode: str | None = None,
    build_command: str | None = None,
    cache_root: Path | None = None,
    command_runner: CommandRunner = run_command,
    analyzer: Analyzer = run_codeql_analysis,
) -> dict:
    resolved_plan = resolve_codeql_comparison_plan(project, changes, baseline_path, command_runner)
    plan = resolved_plan
    if not compare:
        plan = {
            "status": "disabled",
            "message": "本次已禁用 CodeQL baseline/target 对比。",
            "baseline": None,
            "target": resolved_plan["target"],
        }

    effective_cache = cache_root or project / ".code-change-check" / "cache" / "codeql"
    if plan["status"] != "ready":
        try:
            with materialize_codeql_source(project, plan["target"], command_runner) as target_source:
                target = analyzer(
                    target_source,
                    output / "target",
                    languages=languages,
                    executable=executable,
                    build_mode=build_mode,
                    build_command=build_command,
                    cache_root=effective_cache,
                    command_runner=command_runner,
                    source_scope=source_scope(plan["target"], "target"),
                )
        except (OSError, RuntimeError, ValueError) as error:
            target = analyzer(
                project,
                output / "target",
                languages=languages,
                executable=executable,
                build_mode=build_mode,
                build_command=build_command,
                cache_root=effective_cache,
                command_runner=command_runner,
                source_scope="current-working-tree",
            )
            plan = {
                **plan,
                "target": {"kind": "current", "value": "current-working-tree"},
                "message": f"{plan['message']} target revision 物化失败，已降级为当前工作区：{error}",
            }
        comparison = skipped_comparison(plan)
        comparison["target_status"] = target.get("status", "")
        target["comparison"] = comparison
        return target

    try:
        with ExitStack() as stack:
            baseline_source = stack.enter_context(
                materialize_codeql_source(project, plan["baseline"], command_runner)
            )
            target_source = stack.enter_context(
                materialize_codeql_source(project, plan["target"], command_runner)
            )
            baseline_result = analyzer(
                baseline_source,
                output / "baseline",
                languages=languages,
                executable=executable,
                build_mode=build_mode,
                build_command=build_command,
                cache_root=effective_cache,
                command_runner=command_runner,
                source_scope=source_scope(plan["baseline"], "baseline"),
            )
            target_result = analyzer(
                target_source,
                output / "target",
                languages=languages,
                executable=executable,
                build_mode=build_mode,
                build_command=build_command,
                cache_root=effective_cache,
                command_runner=command_runner,
                source_scope=source_scope(plan["target"], "target"),
            )
    except (OSError, RuntimeError, ValueError) as error:
        target_result = analyzer(
            project,
            output / "target",
            languages=languages,
            executable=executable,
            build_mode=build_mode,
            build_command=build_command,
            cache_root=effective_cache,
            command_runner=command_runner,
            source_scope="current-working-tree",
        )
        target_result["comparison"] = {
            **skipped_comparison(plan),
            "status": "failed",
            "message": f"无法构造 CodeQL baseline/target 源代码：{error}",
        }
        return target_result

    baseline_success = baseline_result.get("status") == "success"
    target_success = target_result.get("status") == "success"
    comparison_success = baseline_success and target_success
    differences = (
        compare_codeql_findings(
            baseline_result.get("findings", []),
            target_result.get("findings", []),
        )
        if comparison_success
        else {
            "new_findings": [],
            "existing_findings": [],
            "resolved_findings": [],
        }
    )
    message = plan["message"]
    if not comparison_success:
        message = (
            f"CodeQL 对比未完成。baseline={baseline_result.get('status', '')}："
            f"{baseline_result.get('message', '')}；target={target_result.get('status', '')}："
            f"{target_result.get('message', '')}"
        )
    comparison = {
        "status": "success" if comparison_success else "failed",
        "message": message,
        "baseline": plan["baseline"],
        "target": plan["target"],
        "baseline_status": baseline_result.get("status", ""),
        "target_status": target_result.get("status", ""),
        **differences,
        "baseline_analysis": baseline_result,
    }
    target_result["comparison"] = comparison
    if comparison["status"] != "success" and target_result.get("status") == "success":
        target_result["status"] = "partial-failure"
        target_result["message"] = "target CodeQL 分析成功，但 baseline/target 对比未完整成功。"
    return target_result
