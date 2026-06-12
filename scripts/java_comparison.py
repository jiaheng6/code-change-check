#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict


def _key(item: dict) -> tuple:
    return (
        item.get("file", ""),
        item.get("symbol", ""),
        item.get("kind", ""),
        item.get("slot", ""),
    )


def _groups(items: list[dict]) -> dict[tuple, list[dict]]:
    result: dict[tuple, list[dict]] = defaultdict(list)
    for item in items:
        result[_key(item)].append(item)
    return result


def _change(change_type: str, severity: str, before: dict | None, after: dict | None, message: str) -> dict:
    item = after or before or {}
    return {
        "type": change_type,
        "severity": severity,
        "file": item.get("file", ""),
        "line": int(item.get("line", 1)),
        "symbol": item.get("symbol", ""),
        "slot": item.get("slot", ""),
        "before": (before or {}).get("source_expression", ""),
        "after": (after or {}).get("source_expression", ""),
        "message": message,
    }


def compare_java_evidence(baseline: list[dict], target: list[dict]) -> dict:
    before_groups = _groups(baseline)
    after_groups = _groups(target)
    changes = []
    for key in sorted(set(before_groups) | set(after_groups)):
        before_items = before_groups.get(key, [])
        after_items = after_groups.get(key, [])
        kind = key[2]
        before = before_items[0] if before_items else None
        after = after_items[0] if after_items else None
        if kind == "field-mapping" and before and after:
            if before.get("source_expression") != after.get("source_expression"):
                changes.append(_change("field-mapping-source-changed", "critical", before, after, "响应字段值来源发生变化。"))
        elif kind == "http-argument" and before and after:
            before_value = before.get("value") or before.get("source_expression")
            after_value = after.get("value") or after.get("source_expression")
            if before_value != after_value:
                severity = "critical" if before_value == "internal" and after_value in {"external", "public"} else "high"
                changes.append(_change("http-address-source-changed", severity, before, after, "HTTP 地址来源发生变化。"))
        elif kind == "call" and before and after:
            before_signatures = {(tuple(item.get("arguments", []))) for item in before_items}
            after_signatures = {(tuple(item.get("arguments", []))) for item in after_items}
            if before_signatures != after_signatures:
                changes.append(_change("call-arguments-changed", "high", before, after, "调用参数数量、顺序或来源发生变化。"))
        elif kind == "guard" and before and not after:
            changes.append(_change("guard-removed", "critical", before, None, "权限、租户或保护条件被删除。"))
        elif kind == "guard" and after and not before:
            changes.append(_change("guard-added", "medium", None, after, "新增权限、租户或保护条件。"))
        elif kind == "state-condition" and before and after:
            if before.get("source_expression") != after.get("source_expression"):
                changes.append(_change("state-condition-changed", "high", before, after, "状态条件发生变化。"))
        elif kind == "database-write" and before and after:
            if before.get("source_expression") != after.get("source_expression"):
                changes.append(_change("database-write-source-changed", "high", before, after, "数据库写入参数来源发生变化。"))
        elif kind == "config-read" and before and after:
            if before.get("source_expression") != after.get("source_expression"):
                changes.append(_change("config-source-changed", "high", before, after, "配置值来源发生变化。"))
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    changes.sort(key=lambda item: (rank.get(item["severity"], 9), item["file"], item["type"]))
    return {
        "status": "success",
        "message": "Java baseline/target 业务语义比较完成。",
        "changes": changes,
    }
