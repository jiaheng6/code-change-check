#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Callable


CommandRunner = Callable[[list[str], Path], tuple[int, str]]


def run_command(args: list[str], cwd: Path, *, code_graph_dir: Path | None = None) -> tuple[int, str]:
    env = os.environ.copy()
    env["CODEGRAPH_NO_DAEMON"] = "1"
    if code_graph_dir is not None:
        env["CODEGRAPH_DIR"] = str(code_graph_dir)
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd),
            env=env,
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


def _parse_json(raw: str, default):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _query(
    executable: str,
    operation: str,
    value: str,
    command_runner,
) -> tuple[object, str]:
    command = [executable, operation, value, "--json"]
    code, output = command_runner(command)
    if code != 0:
        return [], output
    return _parse_json(output, []), ""


def run_code_graph_analysis(
    source: Path,
    changed_files: list[str],
    changed_symbols: list[str],
    cache_dir: Path,
    runtime: dict,
    command_runner: CommandRunner = run_command,
) -> dict:
    base = {
        "status": "partial",
        "version": runtime.get("version", ""),
        "index": {"files": 0, "nodes": 0, "edges": 0},
        "symbols": changed_symbols,
        "callers": [],
        "callees": [],
        "impacts": [],
        "affected_tests": [],
        "errors": [],
    }
    if runtime.get("status") != "success" or not runtime.get("executable"):
        base["errors"].append(runtime.get("message", "CodeGraph 运行时不可用。"))
        return base

    cache_dir.mkdir(parents=True, exist_ok=True)
    executable = runtime["executable"]

    def execute(command: list[str]) -> tuple[int, str]:
        if command_runner is run_command:
            return run_command(command, source, code_graph_dir=cache_dir)
        return command_runner(command, source)

    init_code, init_output = execute([executable, "init", str(source), "--index"])
    if init_code != 0:
        base["errors"].append(f"CodeGraph 索引失败：{init_output}")
        return base
    status_code, status_output = execute([executable, "status", str(source), "--json"])
    if status_code == 0:
        status = _parse_json(status_output, {})
        if isinstance(status, dict):
            base["index"] = {
                "files": int(status.get("files", status.get("fileCount", 0)) or 0),
                "nodes": int(status.get("nodes", status.get("nodeCount", 0)) or 0),
                "edges": int(status.get("edges", status.get("edgeCount", 0)) or 0),
            }

    errors = []
    for symbol in changed_symbols[:50]:
        for operation, target in (("callers", "callers"), ("callees", "callees"), ("impact", "impacts")):
            data, error = _query(executable, operation, symbol, execute)
            if error:
                errors.append(f"{operation} {symbol}：{error}")
            elif isinstance(data, list):
                base[target].extend(data)
            elif isinstance(data, dict):
                values = data.get(target) or data.get(operation) or []
                if isinstance(values, list):
                    base[target].extend(values)
                else:
                    base[target].append(data)
    if changed_files:
        command = [executable, "affected", *changed_files, "--json"]
        code, output = execute(command)
        if code == 0:
            affected = _parse_json(output, [])
            if isinstance(affected, list):
                base["affected_tests"] = affected
            elif isinstance(affected, dict):
                base["affected_tests"] = affected.get("affected_tests") or affected.get("tests") or []
        else:
            errors.append(f"affected：{output}")
    base["errors"] = errors
    base["status"] = "success" if not errors else "partial"
    return base
