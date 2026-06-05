#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
import re


CALL_SHAPE_RE = re.compile(r"([\w$.]+)\s+参数数量\s+(\d+)(?:，参数：(.+))?")
TENANT_RE = re.compile(r"\b(tenantId|tenant_id|tenantKey|tenant_key)\b", re.IGNORECASE)
STATE_RE = re.compile(r"\b(status|state|phase|workflowState|workflow_state)\b", re.IGNORECASE)


def is_file_scoped(contract: dict) -> bool:
    return str(contract.get("source", "")).startswith("existing-code")


def contract_scope_file(contract: dict) -> str | None:
    return contract.get("file", "") if is_file_scoped(contract) else None


def inventory_items(inventory: dict, kind: str, file: str | None = None) -> list[dict]:
    return [
        item
        for item in inventory.get("items", [])
        if item.get("kind") == kind and (file is None or item.get("file") == file)
    ]


def make_violation(
    contract: dict,
    violation_type: str,
    severity: str,
    file: str,
    line: int,
    message: str,
    expected: str,
    actual: str,
) -> dict:
    return {
        "id": f"contract:{violation_type}:{contract.get('id', '')}",
        "type": violation_type,
        "severity": severity,
        "file": file or contract.get("file", ""),
        "line": line or int(contract.get("line", 1)),
        "message": message,
        "expected": expected,
        "actual": actual,
        "contract": contract,
    }


def expected_addressing(contract: dict) -> str | None:
    text = contract.get("text", "")
    if "internalBaseUrl" in text:
        return "internal"
    if "publicBaseUrl" in text and re.search(r"(必须|应当|需要|只允许)", text):
        return "public"
    return None


def evaluate_addressing_contract(contract: dict, inventory: dict) -> list[dict]:
    expected = expected_addressing(contract)
    if expected is None:
        return []
    file = contract_scope_file(contract)
    items = inventory_items(inventory, "addressing", file)
    if not items:
        return [
            make_violation(
                contract,
                "contract-addressing",
                "high",
                file or contract.get("file", ""),
                int(contract.get("line", 1)),
                f"契约要求使用 {'internalBaseUrl' if expected == 'internal' else 'publicBaseUrl'}，但目标代码没有找到对应寻址线索。",
                expected,
                "missing",
            )
        ]
    values = {item.get("value", "") for item in items}
    if expected in values and not (expected == "internal" and "public" in values):
        return []
    offending = next((item for item in items if item.get("value") != expected), items[0])
    actual = ", ".join(sorted(values))
    severity = "critical" if expected == "internal" and "public" in values else "high"
    return [
        make_violation(
            contract,
            "contract-addressing",
            severity,
            offending.get("file", file or contract.get("file", "")),
            int(offending.get("line", contract.get("line", 1))),
            f"契约要求使用 {'internalBaseUrl' if expected == 'internal' else 'publicBaseUrl'}，但目标代码寻址为 {actual}。",
            expected,
            actual,
        )
    ]


def parse_call_shape(contract: dict) -> dict | None:
    match = CALL_SHAPE_RE.search(contract.get("text", ""))
    if not match:
        return None
    raw_arguments = match.group(3) or ""
    arguments = [part.strip() for part in raw_arguments.split(",") if part.strip()]
    return {
        "symbol": match.group(1),
        "argument_count": int(match.group(2)),
        "arguments": arguments,
    }


def call_matches_shape(item: dict, shape: dict) -> bool:
    if item.get("argument_count") != shape["argument_count"]:
        return False
    expected_arguments = shape.get("arguments", [])
    if not expected_arguments:
        return True
    actual_arguments = item.get("arguments", [])
    if not actual_arguments:
        return True
    actual_tokens = {
        token
        for argument in actual_arguments
        for token in re.findall(r"\b[A-Za-z_$][\w$]*\b", argument)
    }
    expected_tokens = {
        token
        for argument in expected_arguments
        for token in re.findall(r"\b[A-Za-z_$][\w$]*\b", argument)
    }
    return expected_tokens <= actual_tokens


def evaluate_call_contract(contract: dict, inventory: dict) -> list[dict]:
    shape = parse_call_shape(contract)
    if not shape:
        return []
    file = contract_scope_file(contract)
    calls = [
        item
        for item in inventory_items(inventory, "call", file)
        if item.get("symbol") == shape["symbol"]
    ]
    expected = f"{shape['symbol']} 参数数量 {shape['argument_count']}，参数：{', '.join(shape['arguments'])}"
    if not calls:
        return [
            make_violation(
                contract,
                "contract-call-shape",
                "high",
                file or contract.get("file", ""),
                int(contract.get("line", 1)),
                f"契约要求保留调用 {shape['symbol']}，但目标代码没有找到该调用。",
                expected,
                "missing",
            )
        ]
    if any(call_matches_shape(item, shape) for item in calls):
        return []
    actual_parts = [
        f"{item.get('argument_count', 0)}({', '.join(item.get('arguments', []))})"
        for item in calls
    ]
    removed_required = [
        argument
        for argument in shape.get("arguments", [])
        if not any(argument in item.get("arguments", []) for item in calls)
    ]
    severity = "critical" if any(TENANT_RE.fullmatch(argument) for argument in removed_required) else "high"
    first = calls[0]
    detail = f"，缺少参数线索：{', '.join(removed_required)}" if removed_required else ""
    return [
        make_violation(
            contract,
            "contract-call-shape",
            severity,
            first.get("file", file or contract.get("file", "")),
            int(first.get("line", contract.get("line", 1))),
            f"契约要求调用 {shape['symbol']} 保持参数形态，但目标代码不匹配{detail}。",
            expected,
            "; ".join(actual_parts),
        )
    ]


def required_field_tokens(contract: dict, pattern: re.Pattern) -> list[str]:
    text = contract.get("text", "")
    tokens = []
    for match in pattern.finditer(text):
        token = match.group(1)
        if token not in tokens:
            tokens.append(token)
    return tokens


def evaluate_field_contract(contract: dict, inventory: dict, value: str, pattern: re.Pattern) -> list[dict]:
    required = required_field_tokens(contract, pattern)
    if not required:
        return []
    file = contract_scope_file(contract)
    items = inventory_items(inventory, "field", file)
    available = {
        item.get("symbol", "")
        for item in items
        if item.get("value") == value
    }
    missing = [token for token in required if token not in available]
    if not missing:
        return []
    return [
        make_violation(
            contract,
            "contract-tenant-field" if value == "tenant" else "contract-state-field",
            "critical" if value == "tenant" else "high",
            file or contract.get("file", ""),
            int(contract.get("line", 1)),
            f"契约要求保留字段线索 {', '.join(required)}，但目标代码缺少：{', '.join(missing)}。",
            ", ".join(required),
            ", ".join(sorted(available)) or "missing",
        )
    ]


def evaluate_one_contract(contract: dict, inventory: dict) -> list[dict]:
    kind = contract.get("kind", "")
    violations = []
    if kind in {"addressing", "text-rule"}:
        violations.extend(evaluate_addressing_contract(contract, inventory))
    if kind in {"call-shape", "text-rule"}:
        violations.extend(evaluate_call_contract(contract, inventory))
    if kind in {"tenant", "text-rule"}:
        violations.extend(evaluate_field_contract(contract, inventory, "tenant", TENANT_RE))
    if kind in {"state", "text-rule"}:
        violations.extend(evaluate_field_contract(contract, inventory, "state", STATE_RE))
    return violations


def evaluate_contracts(contracts: list[dict], inventory: dict | None) -> dict:
    if not contracts:
        return {
            "status": "disabled",
            "message": "本次未启用业务契约执行检查。",
            "checked_contracts": 0,
            "violations": [],
        }
    if not inventory or inventory.get("status") == "failed":
        return {
            "status": "failed",
            "message": f"业务契约执行检查未完成：{(inventory or {}).get('message', '缺少语义清单')}",
            "checked_contracts": 0,
            "violations": [],
        }
    violations = []
    for contract in contracts:
        violations.extend(evaluate_one_contract(contract, inventory))
    grouped = defaultdict(list)
    for violation in violations:
        grouped[(violation["type"], violation["file"], violation["line"], violation["message"])].append(violation)
    deduplicated = [items[0] for _, items in sorted(grouped.items())]
    return {
        "status": "partial-failure" if inventory.get("status") == "partial-failure" else "success",
        "message": "业务契约执行检查完成。",
        "checked_contracts": len(contracts),
        "violations": deduplicated,
    }
