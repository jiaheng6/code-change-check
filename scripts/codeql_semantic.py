#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable

from codeql_support import run_command


CommandRunner = Callable[[list[str], Path], tuple[int, str]]
DEFAULT_QUERY_ROOT = Path(__file__).resolve().parents[1] / "codeql" / "semantic"


def parse_call_rows(rows: list[list[str]]) -> list[dict]:
    items = []
    for row in rows:
        if len(row) < 4:
            continue
        try:
            line = int(row[1])
            argument_count = int(row[3])
        except ValueError:
            continue
        items.append(
            {
                "kind": "call",
                "file": row[0].replace("\\", "/"),
                "line": line,
                "symbol": row[2],
                "argument_count": argument_count,
                "arguments": [],
                "text": "",
                "engine": "codeql",
            }
        )
    return items


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        return list(csv.reader(handle))


def run_query_to_csv(
    database: Path,
    query: Path,
    output_root: Path,
    executable: str,
    command_runner: CommandRunner,
) -> tuple[list[list[str]], str]:
    output_root.mkdir(parents=True, exist_ok=True)
    bqrs = output_root / f"{query.stem}.bqrs"
    csv_path = output_root / f"{query.stem}.csv"
    query_code, query_output = command_runner(
        [
            executable,
            "query",
            "run",
            f"--database={database}",
            f"--output={bqrs}",
            "--",
            str(query),
        ],
        query.parent,
    )
    if query_code != 0:
        return [], f"CodeQL 语义查询执行失败：{query_output}"
    decode_code, decode_output = command_runner(
        [
            executable,
            "bqrs",
            "decode",
            "--format=csv",
            "--no-titles",
            f"--output={csv_path}",
            "--",
            str(bqrs),
        ],
        query.parent,
    )
    if decode_code != 0:
        return [], f"CodeQL 语义查询结果解码失败：{decode_output}"
    if not csv_path.exists():
        return [], "CodeQL 语义查询未生成 CSV 结果。"
    try:
        return read_csv_rows(csv_path), ""
    except OSError as error:
        return [], f"无法读取 CodeQL 语义查询结果：{error}"


def run_codeql_semantic_queries(
    database: Path,
    language: str,
    output_root: Path,
    *,
    query_root: Path = DEFAULT_QUERY_ROOT,
    executable: str = "codeql",
    command_runner: CommandRunner = run_command,
) -> dict:
    language_root = query_root / language
    query = language_root / "calls.ql"
    if not query.exists():
        return {
            "status": "unsupported",
            "engine": "codeql",
            "language": language,
            "message": f"当前没有 {language} 的 CodeQL 语义查询。",
            "errors": [],
            "items": [],
        }
    rows, error = run_query_to_csv(
        database,
        query,
        output_root / language,
        executable,
        command_runner,
    )
    if error:
        return {
            "status": "failed",
            "engine": "codeql",
            "language": language,
            "message": error,
            "errors": [error],
            "items": [],
        }
    return {
        "status": "success",
        "engine": "codeql",
        "language": language,
        "message": "CodeQL 语义查询完成。",
        "errors": [],
        "items": parse_call_rows(rows),
    }
