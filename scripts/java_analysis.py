#!/usr/bin/env python3
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
from typing import Callable

from code_graph import run_code_graph_analysis
from java_comparison import compare_java_evidence
from source_state import materialize_source_state, resolve_source_states, run_command
from tool_runtime import (
    load_runtime_manifest,
    resolve_code_graph_runtime,
    resolve_java_analyzer,
    resolve_java_runtime,
)


CoreAnalyzer = Callable[[Path, dict], dict]
GraphAnalyzer = Callable[..., dict]
SKILL_ROOT = Path(__file__).resolve().parents[1]


def disabled_java_analysis_result(message: str = "当前项目未检测到 Java 源文件，已跳过 Java 语义分析。") -> dict:
    return {
        "status": "disabled",
        "message": message,
        "coverage": {
            "java_files_total": 0,
            "java_files_parsed": 0,
            "java_files_failed": 0,
            "core_complete": True,
            "graph_complete": True,
            "comparison_complete": True,
        },
        "target": {
            "source": {"kind": "current", "value": "current-working-tree"},
            "core": {"status": "disabled", "evidence": [], "errors": []},
            "code_graph": {"status": "disabled", "errors": []},
        },
        "comparison": {"status": "disabled", "changes": []},
        "findings": [],
        "errors": [],
    }


def _run_core(source: Path, runtime: dict) -> dict:
    command = [runtime["java"]["executable"], "-jar", runtime["analyzer"]["executable"], "--project", str(source)]
    completed = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "status": "blocked",
            "message": "内置 Java 分析器没有返回有效 JSON。",
            "coverage": {"java_files_total": 0, "java_files_parsed": 0, "java_files_failed": 0},
            "evidence": [],
            "errors": [completed.stderr or completed.stdout],
        }


def _changed_symbols(evidence: list[dict], changed_files: list[str]) -> list[str]:
    normalized = {value.replace("\\", "/") for value in changed_files}
    symbols = set()
    for item in evidence:
        if normalized and item.get("file", "").replace("\\", "/") not in normalized:
            continue
        symbol = item.get("symbol", "")
        if symbol:
            symbols.add(symbol)
            if "#" in symbol:
                symbols.add(symbol.split("#", 1)[1].split("(", 1)[0])
        if item.get("kind") == "call" and item.get("slot"):
            symbols.add(item["slot"])
    return sorted(symbols)


def run_java_analysis(
    project: Path,
    changes: dict,
    output: Path,
    baseline_path: Path | None = None,
    tool_cache: Path | None = None,
    offline: bool = False,
    command_runner=run_command,
    core_analyzer: CoreAnalyzer | None = None,
    graph_analyzer: GraphAnalyzer = run_code_graph_analysis,
) -> dict:
    manifest = load_runtime_manifest(SKILL_ROOT)
    cache_root = tool_cache or Path.home() / ".code-change-check" / "tools"
    java_runtime = resolve_java_runtime(manifest, cache_root, offline, command_runner=command_runner)
    analyzer_runtime = resolve_java_analyzer(SKILL_ROOT, manifest)
    graph_runtime = resolve_code_graph_runtime(manifest, cache_root, offline)
    runtime = {"java": java_runtime, "analyzer": analyzer_runtime}
    if java_runtime["status"] != "success" or analyzer_runtime["status"] != "success":
        errors = [item["message"] for item in (java_runtime, analyzer_runtime) if item["status"] != "success"]
        return {
            "status": "blocked",
            "message": "Java 核心分析运行时不可用。",
            "coverage": {"java_files_total": 0, "java_files_parsed": 0, "java_files_failed": 0, "core_complete": False, "graph_complete": False, "comparison_complete": False},
            "target": {"source": {"kind": "current", "value": "current-working-tree"}, "core": {"status": "blocked", "evidence": [], "errors": errors}, "code_graph": {"status": "partial", "errors": []}},
            "comparison": {"status": "partial", "changes": []},
            "findings": [],
            "errors": errors,
        }

    states = resolve_source_states(project, changes, baseline_path, command_runner)
    target_descriptor = states.get("target") or {"kind": "current", "value": "current-working-tree"}
    analyze_core = core_analyzer or _run_core
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with ExitStack() as stack:
        target_source = stack.enter_context(materialize_source_state(project, target_descriptor, command_runner))
        target_core = analyze_core(target_source, runtime)
        if target_core.get("status") == "blocked":
            return {
                "status": "blocked",
                "message": target_core.get("message", "Java 核心分析失败。"),
                "coverage": {**target_core.get("coverage", {}), "core_complete": False, "graph_complete": False, "comparison_complete": False},
                "target": {"source": target_descriptor, "core": target_core, "code_graph": {"status": "partial", "errors": []}},
                "comparison": {"status": "partial", "changes": []},
                "findings": [],
                "errors": target_core.get("errors", []),
            }
        changed_files = changes.get("changed_files", [])
        symbols = _changed_symbols(target_core.get("evidence", []), changed_files)
        target_graph = graph_analyzer(
            target_source,
            changed_files,
            symbols,
            project / ".code-change-check" / "cache" / "code-graph",
            graph_runtime,
            command_runner=command_runner,
        )
        baseline_descriptor = states.get("baseline")
        if baseline_descriptor:
            baseline_source = stack.enter_context(materialize_source_state(project, baseline_descriptor, command_runner))
            baseline_core = analyze_core(baseline_source, runtime)
            if baseline_core.get("status") == "blocked":
                comparison = {"status": "partial", "message": "baseline Java 核心分析失败。", "baseline": baseline_descriptor, "target": target_descriptor, "changes": []}
            else:
                comparison = {
                    **compare_java_evidence(baseline_core.get("evidence", []), target_core.get("evidence", [])),
                    "baseline": baseline_descriptor,
                    "target": target_descriptor,
                    "baseline_core": baseline_core,
                }
        else:
            comparison = {
                "status": "partial",
                "message": states.get("message", "缺少 baseline，无法执行语义比较。"),
                "baseline": None,
                "target": target_descriptor,
                "changes": [],
            }
    coverage = dict(target_core.get("coverage", {}))
    coverage["core_complete"] = target_core.get("status") == "success"
    coverage["graph_complete"] = target_graph.get("status") == "success"
    coverage["comparison_complete"] = comparison.get("status") == "success"
    status = "success" if all((coverage["core_complete"], coverage["graph_complete"], coverage["comparison_complete"])) else "partial"
    errors.extend(target_core.get("errors", []))
    errors.extend(target_graph.get("errors", []))
    return {
        "status": status,
        "message": "Java 语义分析完成。" if status == "success" else "Java 语义分析完成，但存在覆盖缺口。",
        "coverage": coverage,
        "target": {"source": target_descriptor, "core": target_core, "code_graph": target_graph},
        "comparison": comparison,
        "findings": comparison.get("changes", []),
        "errors": errors,
    }
