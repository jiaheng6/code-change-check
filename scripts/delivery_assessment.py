from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any


MAX_SCORE_ROWS = 80

DIMENSIONS = [
    {
        "id": "requirement_coverage",
        "label": "需求覆盖",
        "description": "需求、任务或契约是否已经进入本次审查范围，并能关联到迭代证据。",
    },
    {
        "id": "contract_correctness",
        "label": "契约正确",
        "description": "业务契约是否已自动检查，且没有发现字段、参数、寻址或结构违反。",
    },
    {
        "id": "semantic_consistency",
        "label": "语义一致",
        "description": "baseline/target 的 Java 业务语义差异是否可解释，是否存在高风险值来源变化。",
    },
    {
        "id": "impact_scope",
        "label": "影响范围",
        "description": "调用链、影响范围和受影响测试是否足够支撑变更影响判断。",
    },
    {
        "id": "risk_closure",
        "label": "风险收敛",
        "description": "高风险命中、覆盖缺口和人工核验义务是否已经收敛到可处理范围。",
    },
    {
        "id": "deliverability",
        "label": "可交付性",
        "description": "综合前几项证据后，本功能点或契约项是否达到可交付状态。",
    },
]

BASE_DIMENSION_IDS = [item["id"] for item in DIMENSIONS if item["id"] != "deliverability"]
WEIGHTS = {
    "requirement_coverage": 0.18,
    "contract_correctness": 0.27,
    "semantic_consistency": 0.2,
    "impact_scope": 0.15,
    "risk_closure": 0.2,
}


def _safe_anchor(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return text or "item"


def _status_from_score(score: int, *, blocked: bool = False, unknown: bool = False) -> str:
    if unknown:
        return "unknown"
    if blocked or score < 40:
        return "blocked"
    if score < 60:
        return "failed"
    if score < 80:
        return "warning"
    return "pass"


def _cell(score: int, reason: str, *, blocked: bool = False, unknown: bool = False, evidence: list[str] | None = None) -> dict:
    score = max(0, min(100, int(round(score))))
    return {
        "score": score,
        "status": _status_from_score(score, blocked=blocked, unknown=unknown),
        "reason": reason,
        "evidence": evidence or [],
    }


def _severity_counts(data: dict) -> Counter:
    summary_counts = data.get("summary", {}).get("by_severity", {})
    if summary_counts:
        return Counter({str(key): int(value) for key, value in summary_counts.items()})
    return Counter(str(item.get("severity", "unknown")) for item in data.get("findings", []))


def _mapped_requirement_ids(mappings: list[dict]) -> set[str]:
    result = set()
    for mapping in mappings:
        for requirement in mapping.get("requirements", []):
            requirement_id = requirement.get("id")
            if requirement_id:
                result.add(requirement_id)
    return result


def _contract_indexes(contract_check: dict) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    violations_by_contract: dict[str, list[dict]] = defaultdict(list)
    unchecked_by_contract: dict[str, list[dict]] = defaultdict(list)
    for violation in contract_check.get("violations", []):
        contract_id = violation.get("contract", {}).get("id") or violation.get("contract_id", "")
        if contract_id:
            violations_by_contract[contract_id].append(violation)
    for unchecked in contract_check.get("unchecked_contracts", []):
        contract_id = unchecked.get("contract_id", "")
        if contract_id:
            unchecked_by_contract[contract_id].append(unchecked)
    return violations_by_contract, unchecked_by_contract


def _global_requirement_score(data: dict) -> dict:
    requirements = data.get("requirement_items", [])
    if not requirements:
        return _cell(65, "未发现需求或任务材料，本项只能按整体变更证据估算。", unknown=True)
    mappings = data.get("requirement_commit_mappings", [])
    if not mappings:
        return _cell(72, f"已识别 {len(requirements)} 条需求/任务，但未执行需求-提交映射。")
    mapped = _mapped_requirement_ids(mappings)
    ratio = len(mapped) / len(requirements)
    score = 50 + ratio * 45
    reason = f"需求-提交映射覆盖 {len(mapped)}/{len(requirements)} 条需求/任务。"
    return _cell(score, reason, blocked=not mapped)


def _global_contract_score(data: dict) -> dict:
    contracts = data.get("business_contracts", [])
    contract_check = data.get("business_contract_check", {})
    if not contracts:
        return _cell(62, "本次未启用业务契约，无法证明隐式业务规则已被覆盖。", unknown=True)
    total = int(contract_check.get("total_contracts", len(contracts)) or len(contracts))
    checked = int(contract_check.get("checked_contracts", 0))
    unchecked = len(contract_check.get("unchecked_contracts", []))
    violations = contract_check.get("violations", [])
    if total and checked == 0:
        return _cell(25, f"已启用 {total} 条业务契约，但自动检查数为 0。", blocked=True)
    if violations:
        critical = sum(1 for item in violations if item.get("severity") == "critical")
        high = sum(1 for item in violations if item.get("severity") == "high")
        score = 30 if critical else 45 if high else 58
        return _cell(score, f"发现 {len(violations)} 条业务契约违反，其中 critical={critical}，high={high}。", blocked=bool(critical))
    if unchecked:
        coverage = checked / total if total else 1
        return _cell(58 + coverage * 18, f"仍有 {unchecked} 条业务契约未自动检查。")
    return _cell(90, f"{checked}/{total} 条业务契约已检查，未发现当前规则支持的违反。")


def _global_semantic_score(data: dict) -> dict:
    java_analysis = data.get("java_analysis", {})
    java_status = java_analysis.get("status", "disabled")
    if java_status == "disabled":
        return _cell(65, "Java 语义分析未启用，本项只能依据文本风险估算。", unknown=True)
    if java_status == "blocked":
        return _cell(30, "Java 语义分析阻塞，无法支撑语义一致性结论。", blocked=True)
    comparison = java_analysis.get("comparison", {})
    changes = comparison.get("changes", [])
    severe = [item for item in changes if item.get("severity") in {"critical", "high"}]
    if severe:
        critical = sum(1 for item in severe if item.get("severity") == "critical")
        score = 35 if critical else 50
        return _cell(score, f"baseline/target 发现 {len(severe)} 条高风险语义变化。", blocked=bool(critical))
    coverage = java_analysis.get("coverage", {})
    if comparison.get("status") != "success" or not coverage.get("comparison_complete", True):
        return _cell(62, "baseline/target 语义比较未完整完成。")
    return _cell(88, "Java 语义比较完整，未发现高风险业务语义变化。")


def _global_impact_score(data: dict) -> dict:
    java_analysis = data.get("java_analysis", {})
    if java_analysis.get("status") == "disabled":
        return _cell(64, "Java 语义分析未启用，调用链和影响范围未自动确认。", unknown=True)
    coverage = java_analysis.get("coverage", {})
    graph = java_analysis.get("target", {}).get("code_graph", {})
    if not coverage.get("graph_complete", True) or graph.get("status") not in {"success", "disabled"}:
        return _cell(58, "调用链或影响范围分析未完整完成。")
    affected_tests = graph.get("affected_tests", [])
    if affected_tests:
        return _cell(90, f"调用图完整，识别到 {len(affected_tests)} 个受影响测试。")
    return _cell(82, "调用图完整，但未识别到受影响测试，需要结合人工回归策略。")


def _global_risk_score(data: dict) -> dict:
    counts = _severity_counts(data)
    audit_coverage = data.get("audit_coverage", {})
    if audit_coverage.get("status") == "blocked":
        return _cell(28, "审计覆盖质量闸门为 blocked，禁止据此判断可交付。", blocked=True)
    if counts.get("critical", 0):
        return _cell(30, f"仍有 {counts['critical']} 个 critical 风险命中。", blocked=True)
    if counts.get("high", 0):
        return _cell(52, f"仍有 {counts['high']} 个 high 风险命中。")
    if audit_coverage.get("status") == "partial":
        return _cell(64, "审计覆盖质量闸门为 partial，结论必须附带限制条件。")
    if sum(counts.values()):
        return _cell(76, "仅存在 medium/low 风险，仍需按建议验证。")
    return _cell(90, "未发现当前规则支持的正式风险命中，覆盖质量闸门通过。")


def _overall_cell(cells: dict[str, dict]) -> dict:
    weighted = sum(cells[key]["score"] * WEIGHTS[key] for key in BASE_DIMENSION_IDS)
    score = int(round(weighted))
    blocked = any(cells[key]["status"] == "blocked" for key in BASE_DIMENSION_IDS)
    failed = any(cells[key]["status"] == "failed" for key in BASE_DIMENSION_IDS)
    if blocked:
        reason = "存在 blocked 维度，暂不能判断为可交付。"
    elif failed:
        reason = "存在 failed 维度，需要修复后再交付。"
    elif score >= 80:
        reason = "关键证据基本达标，可进入交付前人工确认。"
    else:
        reason = "仍有覆盖或风险缺口，需要补充验证。"
    return _cell(score, reason, blocked=blocked)


def _base_cells(data: dict) -> dict[str, dict]:
    return {
        "requirement_coverage": _global_requirement_score(data),
        "contract_correctness": _global_contract_score(data),
        "semantic_consistency": _global_semantic_score(data),
        "impact_scope": _global_impact_score(data),
        "risk_closure": _global_risk_score(data),
    }


def _requirement_row(requirement: dict, data: dict, base_cells: dict[str, dict], mapped_ids: set[str], mappings_enabled: bool) -> dict:
    requirement_id = requirement.get("id", "")
    cells = dict(base_cells)
    if mappings_enabled:
        if requirement_id in mapped_ids:
            cells["requirement_coverage"] = _cell(92, "该需求/任务已关联到本次选中的提交。")
        else:
            cells["requirement_coverage"] = _cell(48, "该需求/任务未关联到本次选中的提交，需要确认是否遗漏。", blocked=True)
    else:
        cells["requirement_coverage"] = _cell(74, "该需求/任务已进入审查材料，但未启用需求-提交映射。")
    cells["deliverability"] = _overall_cell(cells)
    row_id = f"requirement-{_safe_anchor(requirement_id)}"
    return {
        "id": row_id,
        "kind": "requirement",
        "label": f"{requirement_id} {requirement.get('kind_label', '需求')}".strip(),
        "source": f"{requirement.get('file', '')}:L{requirement.get('line', 1)}",
        "text": requirement.get("text", ""),
        "detail_anchor": f"delivery-detail-{row_id}",
        "scores": cells,
    }


def _contract_score(contract: dict, contract_check: dict, violations: list[dict], unchecked: list[dict]) -> dict:
    if unchecked:
        reason = "；".join(item.get("reason", "") for item in unchecked if item.get("reason"))
        return _cell(42, f"该契约未能自动检查。{reason}", blocked=True)
    if violations:
        severities = Counter(item.get("severity", "unknown") for item in violations)
        if severities.get("critical", 0):
            score = 28
            blocked = True
        elif severities.get("high", 0):
            score = 42
            blocked = False
        else:
            score = 58
            blocked = False
        return _cell(score, f"该契约发现 {len(violations)} 条违反：{dict(severities)}。", blocked=blocked)
    if contract_check.get("status") in {"disabled", "failed"}:
        return _cell(45, "业务契约执行检查未成功完成。", blocked=contract_check.get("status") == "failed")
    return _cell(92, "该契约已自动检查，未发现当前规则支持的违反。")


def _contract_row(
    contract: dict,
    data: dict,
    base_cells: dict[str, dict],
    violations_by_contract: dict[str, list[dict]],
    unchecked_by_contract: dict[str, list[dict]],
) -> dict:
    contract_id = contract.get("id", "")
    contract_check = data.get("business_contract_check", {})
    violations = violations_by_contract.get(contract_id, [])
    unchecked = unchecked_by_contract.get(contract_id, [])
    cells = dict(base_cells)
    cells["requirement_coverage"] = _cell(86, "该业务契约已纳入本次启用契约列表。")
    cells["contract_correctness"] = _contract_score(contract, contract_check, violations, unchecked)
    if violations:
        cells["risk_closure"] = _cell(
            min(48, cells["risk_closure"]["score"]),
            "该契约仍存在违反，必须修复或解释后才能交付。",
            blocked=any(item.get("severity") == "critical" for item in violations),
        )
    elif unchecked:
        cells["risk_closure"] = _cell(50, "该契约存在人工核验义务，不能直接视为通过。")
    cells["deliverability"] = _overall_cell(cells)
    row_id = f"contract-{_safe_anchor(contract_id)}"
    return {
        "id": row_id,
        "kind": "contract",
        "label": f"{contract_id} {contract.get('kind', '契约')}".strip(),
        "source": f"{contract.get('file', '')}:L{contract.get('line', 1)}",
        "text": contract.get("text", ""),
        "detail_anchor": f"delivery-detail-{row_id}",
        "scores": cells,
    }


def _overall_row(data: dict, base_cells: dict[str, dict]) -> dict:
    cells = dict(base_cells)
    cells["deliverability"] = _overall_cell(cells)
    return {
        "id": "overall-change",
        "kind": "overall",
        "label": "整体变更",
        "source": data.get("changes", {}).get("range", ""),
        "text": "未识别到可单独列出的需求、任务或业务契约，按整体证据评分。",
        "detail_anchor": "delivery-detail-overall-change",
        "scores": cells,
    }


def build_delivery_assessment(data: dict[str, Any]) -> dict[str, Any]:
    base_cells = _base_cells(data)
    rows = []
    mappings = data.get("requirement_commit_mappings", [])
    mapped_ids = _mapped_requirement_ids(mappings)
    mappings_enabled = bool(mappings)
    for requirement in data.get("requirement_items", []):
        if len(rows) >= MAX_SCORE_ROWS:
            break
        rows.append(_requirement_row(requirement, data, base_cells, mapped_ids, mappings_enabled))
    violations_by_contract, unchecked_by_contract = _contract_indexes(data.get("business_contract_check", {}))
    for contract in data.get("business_contracts", []):
        if len(rows) >= MAX_SCORE_ROWS:
            break
        rows.append(_contract_row(contract, data, base_cells, violations_by_contract, unchecked_by_contract))
    if not rows:
        rows.append(_overall_row(data, base_cells))
    score_counts = Counter(row["scores"]["deliverability"]["status"] for row in rows)
    average = round(sum(row["scores"]["deliverability"]["score"] for row in rows) / len(rows), 1)
    total_items = len(data.get("requirement_items", [])) + len(data.get("business_contracts", []))
    truncated_count = max(0, total_items - len(rows))
    return {
        "dimensions": DIMENSIONS,
        "rows": rows,
        "summary": {
            "average_score": average,
            "by_status": dict(score_counts),
            "row_count": len(rows),
            "truncated_count": truncated_count,
            "message": "评分用于定位人工审查优先级，不替代最终业务验收。",
        },
    }
