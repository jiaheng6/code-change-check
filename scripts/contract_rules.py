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
    difference: dict,
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
        "difference": difference,
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
                {
                    "kind": "addressing",
                    "expected": expected,
                    "actual": [],
                    "missing": [expected],
                    "added": [],
                },
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
            {
                "kind": "addressing",
                "expected": expected,
                "actual": sorted(values),
                "missing": [] if expected in values else [expected],
                "added": sorted(value for value in values if value != expected),
            },
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
                {
                    "kind": "call-shape",
                    "expected": shape,
                    "actual": [],
                    "missing": list(shape.get("arguments", [])),
                    "added": [],
                },
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
    expected_tokens = {
        token
        for argument in shape.get("arguments", [])
        for token in re.findall(r"\b[A-Za-z_$][\w$]*\b", argument)
    }
    actual_tokens = {
        token
        for item in calls
        for argument in item.get("arguments", [])
        for token in re.findall(r"\b[A-Za-z_$][\w$]*\b", argument)
    }
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
            {
                "kind": "call-shape",
                "expected": shape,
                "actual": [
                    {
                        "argument_count": item.get("argument_count", 0),
                        "arguments": item.get("arguments", []),
                    }
                    for item in calls
                ],
                "missing": removed_required,
                "added": sorted(actual_tokens - expected_tokens),
            },
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
            {
                "kind": "field",
                "expected": required,
                "actual": sorted(available),
                "missing": missing,
                "added": sorted(available - set(required)),
            },
        )
    ]


def evaluate_json_shape_contract(contract: dict, response_snapshots: dict[str, dict]) -> list[dict]:
    snapshot = response_snapshots.get(str(contract.get("match_key", "")).lower())
    if not snapshot:
        return []
    expected_paths = sorted(set(contract.get("shape", {}).get("paths", [])))
    actual_paths = sorted(set(snapshot.get("paths", [])))
    missing = sorted(set(expected_paths) - set(actual_paths))
    expected_constants = contract.get("shape", {}).get("constants", {})
    actual_constants = snapshot.get("constants", {})
    changed = [
        {
            "path": path,
            "expected": expected,
            "actual": actual_constants[path],
        }
        for path, expected in sorted(expected_constants.items())
        if path in actual_constants and actual_constants[path] != expected
    ]
    if not missing and not changed:
        return []
    added = sorted(set(actual_paths) - set(expected_paths))
    details = []
    if missing:
        details.append(f"缺少字段路径：{', '.join(missing)}")
    if changed:
        details.append(
            "稳定标签值变化："
            + ", ".join(
                f"{item['path']}={item['actual']}（期望 {item['expected']}）"
                for item in changed
            )
        )
    return [
        make_violation(
            contract,
            "contract-json-shape",
            "high",
            snapshot.get("file", contract.get("file", "")),
            1,
            f"实际响应与 JSON 契约不一致：{'；'.join(details)}。",
            ", ".join(expected_paths),
            ", ".join(actual_paths),
            {
                "kind": "json-shape",
                "expected": expected_paths,
                "actual": actual_paths,
                "missing": missing,
                "added": added,
                "changed": changed,
            },
        )
    ]


def contract_unchecked_reason(contract: dict, response_snapshots: dict[str, dict]) -> str | None:
    kind = contract.get("kind", "")
    if kind == "json-shape":
        if str(contract.get("match_key", "")).lower() not in response_snapshots:
            return "没有找到同文件名的实际响应快照，无法执行 JSON 字段形状对比。"
        return None
    if kind == "addressing":
        return None if expected_addressing(contract) else "寻址契约无法解析出明确期望值。"
    if kind == "call-shape":
        return None if parse_call_shape(contract) else "调用契约无法解析出参数形状。"
    if kind == "tenant":
        return None if required_field_tokens(contract, TENANT_RE) else "租户契约无法解析出字段名。"
    if kind == "state":
        return None if required_field_tokens(contract, STATE_RE) else "状态契约无法解析出字段名。"
    if kind == "text-rule":
        executable = any(
            (
                expected_addressing(contract),
                parse_call_shape(contract),
                required_field_tokens(contract, TENANT_RE),
                required_field_tokens(contract, STATE_RE),
            )
        )
        return None if executable else "文本契约无法解析为当前规则支持的可执行结构。"
    return f"暂不支持自动执行契约类型：{kind or 'unknown'}。"


def evaluate_one_contract(
    contract: dict,
    inventory: dict,
    response_snapshots: dict[str, dict],
) -> list[dict]:
    kind = contract.get("kind", "")
    violations = []
    if kind == "json-shape":
        return evaluate_json_shape_contract(contract, response_snapshots)
    if kind in {"addressing", "text-rule"}:
        violations.extend(evaluate_addressing_contract(contract, inventory))
    if kind in {"call-shape", "text-rule"}:
        violations.extend(evaluate_call_contract(contract, inventory))
    if kind in {"tenant", "text-rule"}:
        violations.extend(evaluate_field_contract(contract, inventory, "tenant", TENANT_RE))
    if kind in {"state", "text-rule"}:
        violations.extend(evaluate_field_contract(contract, inventory, "state", STATE_RE))
    return violations


def evaluate_contracts(
    contracts: list[dict],
    inventory: dict | None,
    response_snapshots: dict[str, dict] | None = None,
) -> dict:
    response_snapshots = response_snapshots or {}
    if not contracts:
        return {
            "status": "disabled",
            "message": "本次未启用业务契约执行检查。",
            "total_contracts": 0,
            "checked_contracts": 0,
            "unchecked_contracts": [],
            "violations": [],
            "differences": [],
        }
    violations = []
    unchecked_contracts = []
    checked_contracts = 0
    checked_semantic_contracts = 0
    inventory_available = bool(inventory and inventory.get("status") != "failed")
    for contract in contracts:
        kind = contract.get("kind", "")
        reason = None
        if kind != "json-shape" and not inventory_available:
            reason = "目标语义清单不可用。"
        if reason is None:
            reason = contract_unchecked_reason(contract, response_snapshots)
        if reason:
            unchecked_contracts.append(
                {
                    "contract_id": contract.get("id", ""),
                    "kind": contract.get("kind", ""),
                    "file": contract.get("file", ""),
                    "line": int(contract.get("line", 1)),
                    "reason": reason,
                }
            )
            continue
        checked_contracts += 1
        if kind != "json-shape":
            checked_semantic_contracts += 1
        violations.extend(evaluate_one_contract(contract, inventory or {"items": []}, response_snapshots))
    grouped = defaultdict(list)
    for violation in violations:
        grouped[(violation["type"], violation["file"], violation["line"], violation["message"])].append(violation)
    inventory_status = (inventory or {}).get("status", "failed")
    status = "partial-failure" if checked_semantic_contracts and inventory_status == "partial-failure" else "success"
    if unchecked_contracts and status == "success":
        status = "partial"
    has_semantic_contracts = any(contract.get("kind") != "json-shape" for contract in contracts)
    if not inventory_available and has_semantic_contracts and checked_contracts == 0 and unchecked_contracts:
        status = "failed"
    deduplicated = [items[0] for _, items in sorted(grouped.items())]
    if status == "failed":
        message = f"业务契约执行检查未完成：{(inventory or {}).get('message', '缺少目标语义清单')}。"
    elif unchecked_contracts:
        message = "业务契约执行检查完成，存在无法自动执行的契约。"
    else:
        message = "业务契约执行检查完成。"
    return {
        "status": status,
        "message": message,
        "total_contracts": len(contracts),
        "checked_contracts": checked_contracts,
        "unchecked_contracts": unchecked_contracts,
        "violations": deduplicated,
        "differences": [
            {
                "contract_id": violation.get("contract", {}).get("id", ""),
                "type": violation.get("type", ""),
                "file": violation.get("file", ""),
                "line": violation.get("line", 1),
                **violation.get("difference", {}),
            }
            for violation in deduplicated
        ],
    }
