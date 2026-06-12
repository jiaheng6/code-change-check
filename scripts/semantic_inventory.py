#!/usr/bin/env python3
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from pathlib import Path
import re


SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".mjs",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
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

CALL_START_RE = re.compile(r"\b([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)\s*\(")
TENANT_RE = re.compile(r"\b(tenantId|tenant_id|tenantKey|tenant_key)\b", re.IGNORECASE)
STATE_RE = re.compile(r"\b(status|state|phase|workflowState|workflow_state)\b", re.IGNORECASE)


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS or part.startswith("code-change-check-output") for part in path.parts)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def split_arguments(raw: str) -> list[str]:
    if not raw.strip():
        return []
    arguments = []
    start = 0
    stack = []
    quote = ""
    escaped = False
    pairs = {")": "(", "]": "[", "}": "{"}
    for index, char in enumerate(raw):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char in "([{":
            stack.append(char)
            continue
        if char in ")]}":
            if stack and stack[-1] == pairs[char]:
                stack.pop()
            continue
        if char == "," and not stack:
            arguments.append(normalize_space(raw[start:index]))
            start = index + 1
    arguments.append(normalize_space(raw[start:]))
    return [argument for argument in arguments if argument]


def find_closing_parenthesis(line: str, open_index: int) -> int | None:
    depth = 0
    quote = ""
    escaped = False
    for index in range(open_index, len(line)):
        char = line[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def extract_line_calls(file: str, line_number: int, line: str) -> list[dict]:
    items = []
    for match in CALL_START_RE.finditer(line):
        open_index = line.find("(", match.start())
        close_index = find_closing_parenthesis(line, open_index)
        if close_index is None:
            continue
        arguments = split_arguments(line[open_index + 1 : close_index])
        items.append(
            {
                "kind": "call",
                "file": file,
                "line": line_number,
                "symbol": match.group(1),
                "argument_count": len(arguments),
                "arguments": arguments,
                "text": normalize_space(line)[:300],
            }
        )
    return items


def line_starts(text: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def line_number_for_offset(starts: list[int], offset: int) -> int:
    return bisect_right(starts, offset)


def extract_text_calls(file: str, text: str) -> list[dict]:
    items = []
    starts = line_starts(text)
    for match in CALL_START_RE.finditer(text):
        open_index = text.find("(", match.end() - 1)
        if open_index < 0:
            continue
        close_index = find_closing_parenthesis(text, open_index)
        if close_index is None:
            continue
        arguments = split_arguments(text[open_index + 1 : close_index])
        line_number = line_number_for_offset(starts, match.start())
        snippet_start = starts[line_number - 1]
        snippet_end = text.find("\n", close_index)
        if snippet_end < 0:
            snippet_end = len(text)
        items.append(
            {
                "kind": "call",
                "file": file,
                "line": line_number,
                "symbol": match.group(1),
                "argument_count": len(arguments),
                "arguments": arguments,
                "text": normalize_space(text[snippet_start:snippet_end])[:300],
            }
        )
    return items


def extract_text_inventory(file: str, text: str) -> list[dict]:
    lines = text.splitlines()
    items = []
    seen_fields = set()
    items.extend(extract_text_calls(file, text))
    for line_number, line in enumerate(lines, start=1):
        for token, value in (
            ("internalBaseUrl", "internal"),
            ("INTERNAL_BASE_URL", "internal"),
            ("publicBaseUrl", "public"),
            ("PUBLIC_BASE_URL", "public"),
            ("externalBaseUrl", "public"),
            ("EXTERNAL_BASE_URL", "public"),
        ):
            if token in line:
                items.append(
                    {
                        "kind": "addressing",
                        "file": file,
                        "line": line_number,
                        "symbol": "base-url",
                        "value": value,
                        "token": token,
                        "text": normalize_space(line)[:300],
                    }
                )
        for match, value in ((TENANT_RE, "tenant"), (STATE_RE, "state")):
            for field_match in match.finditer(line):
                symbol = field_match.group(1)
                key = (value, symbol.lower())
                if key in seen_fields:
                    continue
                seen_fields.add(key)
                items.append(
                    {
                        "kind": "field",
                        "file": file,
                        "line": line_number,
                        "symbol": symbol,
                        "value": value,
                        "text": normalize_space(line)[:300],
                    }
                )
    return items


def extract_file_inventory(path: Path, project: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    file = path.relative_to(project).as_posix()
    return extract_text_inventory(file, text)


def extract_semantic_inventory(project: Path, engine: str = "lightweight") -> dict:
    items = []
    errors = []
    try:
        paths = sorted(project.rglob("*"), key=lambda path: path.as_posix())
    except OSError as error:
        return {"status": "failed", "engine": engine, "message": str(error), "items": []}
    for path in paths:
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        if should_skip(path.relative_to(project)):
            continue
        try:
            items.extend(extract_file_inventory(path, project))
        except OSError as error:
            errors.append(f"{path}: {error}")
    return {
        "status": "success" if not errors else "partial-failure",
        "engine": engine,
        "message": "轻量语义清单提取完成。" if not errors else "部分文件无法提取语义清单。",
        "errors": errors,
        "items": items,
    }


def merge_semantic_inventories(primary: dict, secondary: dict | None) -> dict:
    if not secondary:
        return primary
    items = []
    seen = set()
    for inventory in (primary, secondary):
        for item in inventory.get("items", []):
            key = (
                item.get("kind", ""),
                item.get("file", ""),
                item.get("line", 1),
                item.get("symbol", ""),
                item.get("value", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
    return {
        "status": primary.get("status", "failed"),
        "engine": "lightweight+spoon",
        "message": "已合并轻量语义清单和 Spoon 语义查询结果。",
        "errors": [*primary.get("errors", []), *secondary.get("errors", [])],
        "items": items,
    }


def group_items(inventory: dict, kind: str) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for item in inventory.get("items", []):
        if item.get("kind") != kind:
            continue
        key = (item.get("file", ""), item.get("symbol", ""))
        groups[key].append(item)
    return groups


def argument_tokens(arguments: list[str]) -> set[str]:
    tokens = set()
    for argument in arguments:
        tokens.update(re.findall(r"\b[A-Za-z_$][\w$]*\b", argument))
    return tokens


def compare_calls(baseline: dict, target: dict) -> list[dict]:
    changes = []
    baseline_groups = group_items(baseline, "call")
    target_groups = group_items(target, "call")
    for key in sorted(set(baseline_groups) & set(target_groups)):
        before_items = baseline_groups[key]
        after_items = target_groups[key]
        before_signatures = {(item["argument_count"], tuple(item["arguments"])) for item in before_items}
        after_signatures = {(item["argument_count"], tuple(item["arguments"])) for item in after_items}
        if before_signatures == after_signatures:
            continue
        before_tokens = set().union(*(argument_tokens(item["arguments"]) for item in before_items))
        after_tokens = set().union(*(argument_tokens(item["arguments"]) for item in after_items))
        removed = sorted(before_tokens - after_tokens)
        added = sorted(after_tokens - before_tokens)
        tenant_removed = any(TENANT_RE.fullmatch(token) for token in removed)
        changes.append(
            {
                "type": "call-arguments-changed",
                "severity": "critical" if tenant_removed else "high",
                "file": key[0],
                "symbol": key[1],
                "line": after_items[0].get("line", 1),
                "message": f"调用 {key[1]} 的参数结构发生变化。",
                "removed": removed,
                "added": added,
                "before": [list(signature) for signature in sorted(before_signatures)],
                "after": [list(signature) for signature in sorted(after_signatures)],
            }
        )
    return changes


def values_by_file(inventory: dict, kind: str, value: str | None = None) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for item in inventory.get("items", []):
        if item.get("kind") != kind:
            continue
        if value is not None and item.get("value") != value:
            continue
        result[item.get("file", "")].add(item.get("value") if kind == "addressing" else item.get("symbol", ""))
    return result


def compare_addressing(baseline: dict, target: dict) -> list[dict]:
    changes = []
    before = values_by_file(baseline, "addressing")
    after = values_by_file(target, "addressing")
    for file in sorted(set(before) & set(after)):
        if before[file] == after[file]:
            continue
        critical = "internal" in before[file] and "public" in after[file]
        changes.append(
            {
                "type": "addressing-changed",
                "severity": "critical" if critical else "high",
                "file": file,
                "symbol": "base-url",
                "line": 1,
                "message": f"寻址方式从 {sorted(before[file])} 变化为 {sorted(after[file])}。",
                "removed": sorted(before[file] - after[file]),
                "added": sorted(after[file] - before[file]),
            }
        )
    return changes


def compare_fields(baseline: dict, target: dict, value: str) -> list[dict]:
    changes = []
    before = values_by_file(baseline, "field", value)
    after = values_by_file(target, "field", value)
    for file in sorted(before):
        removed = sorted(before[file] - after.get(file, set()))
        if not removed:
            continue
        changes.append(
            {
                "type": "tenant-field-removed" if value == "tenant" else "state-field-removed",
                "severity": "critical" if value == "tenant" else "high",
                "file": file,
                "symbol": ", ".join(removed),
                "line": 1,
                "message": f"目标代码不再包含已有的{'租户' if value == 'tenant' else '状态'}字段线索：{', '.join(removed)}。",
                "removed": removed,
                "added": [],
            }
        )
    return changes


def compare_semantic_inventories(baseline: dict, target: dict) -> dict:
    if baseline.get("status") != "success" or target.get("status") != "success":
        return {
            "status": "failed",
            "message": (
                f"语义清单对比未完成。baseline={baseline.get('status', '')}：{baseline.get('message', '')}；"
                f"target={target.get('status', '')}：{target.get('message', '')}"
            ),
            "changes": [],
        }
    changes = [
        *compare_calls(baseline, target),
        *compare_addressing(baseline, target),
        *compare_fields(baseline, target, "tenant"),
        *compare_fields(baseline, target, "state"),
    ]
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    changes.sort(key=lambda item: (severity_rank.get(item["severity"], 9), item["file"], item["type"]))
    return {
        "status": "success",
        "message": "语义清单对比完成。",
        "changes": changes,
    }
