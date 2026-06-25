#!/usr/bin/env python3
"""HTML 格式报告生成器。

基于 JSON 证据包生成自包含 HTML 文件。
支持可交付评分矩阵、颜色标注严重级别、Mermaid 图渲染、可折叠区域和表格化摘要。
"""
from __future__ import annotations

import html
from typing import Any

from delivery_assessment import build_delivery_assessment


_SEVERITY_COLORS = {
    "critical": "#dc2626",
    "high": "#ea580c",
    "medium": "#ca8a04",
    "low": "#2563eb",
}

_CSS = """\
:root {
  --bg: #ffffff;
  --fg: #1f2937;
  --border: #e5e7eb;
  --header-bg: #f9fafb;
  --code-bg: #f3f4f6;
  --critical: #dc2626;
  --high: #ea580c;
  --medium: #ca8a04;
  --low: #2563eb;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: var(--fg);
  background: var(--bg);
  margin: 0;
  padding: 2rem;
  line-height: 1.6;
}
h1 { border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; }
h2 { margin-top: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; }
h3 { margin-top: 1.5rem; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid var(--border); padding: 0.5rem 0.75rem; text-align: left; }
th { background: var(--header-bg); font-weight: 600; }
code { background: var(--code-bg); padding: 0.15rem 0.4rem; border-radius: 3px; font-size: 0.9em; }
.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 3px;
  color: #fff;
  font-size: 0.8em;
  font-weight: 600;
}
.badge-critical { background: var(--critical); }
.badge-high { background: var(--high); }
.badge-medium { background: var(--medium); }
.badge-low { background: var(--low); }
details { margin: 0.5rem 0; }
details summary { cursor: pointer; font-weight: 500; padding: 0.3rem 0; }
details summary:hover { color: #2563eb; }
.meta-list { list-style: none; padding: 0; }
.meta-list li { padding: 0.2rem 0; }
.meta-list li::before { content: "•"; color: #9ca3af; margin-right: 0.5rem; }
.finding-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1rem;
  margin: 0.75rem 0;
  border-left: 4px solid var(--border);
}
.finding-card.critical { border-left-color: var(--critical); }
.finding-card.high { border-left-color: var(--high); }
.finding-card.medium { border-left-color: var(--medium); }
.finding-card.low { border-left-color: var(--low); }
.mermaid { margin: 1rem 0; }
.score-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
  margin: 1rem 0 1.5rem;
  background: #f8fafc;
}
.score-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.75rem 0;
}
.score-chip {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  padding: 0.2rem 0.65rem;
  font-size: 0.9rem;
}
.score-matrix th:first-child { min-width: 18rem; }
.score-row-title { font-weight: 700; }
.score-row-meta {
  color: #6b7280;
  font-size: 0.85rem;
  margin-top: 0.15rem;
}
.score-cell {
  display: block;
  min-width: 4.5rem;
  border-radius: 5px;
  padding: 0.4rem 0.35rem;
  text-align: center;
  text-decoration: none;
  color: #111827;
  font-weight: 700;
}
.score-cell:hover { outline: 2px solid #111827; outline-offset: 1px; }
.score-cell small {
  display: block;
  font-size: 0.72rem;
  font-weight: 500;
  opacity: 0.82;
}
.score-pass { background: #86efac; }
.score-warning { background: #fde68a; }
.score-failed { background: #fca5a5; }
.score-blocked { background: #ef4444; color: #fff; }
.score-unknown { background: #e5e7eb; color: #374151; }
.score-detail-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.85rem;
  margin: 0.75rem 0;
  background: #fff;
}
.score-detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 0.65rem;
}
.score-detail-item {
  border-left: 4px solid var(--border);
  padding: 0.35rem 0.5rem;
  background: #f9fafb;
}
.score-detail-item.pass { border-left-color: #22c55e; }
.score-detail-item.warning { border-left-color: #f59e0b; }
.score-detail-item.failed { border-left-color: #f97316; }
.score-detail-item.blocked { border-left-color: #dc2626; }
.score-detail-item.unknown { border-left-color: #9ca3af; }
"""

_MERMAID_SCRIPT = '<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js" integrity="sha384-EnYhRnB3MO+yzNoHB7mRdKXTBn9lREOHjk3OP1k39vMz2BrgLPI2SH/fMKynHayq" crossorigin="anonymous"></script>'
_MERMAID_INIT = "<script>mermaid.initialize({startOnLoad:true});</script>"


def _esc(text: Any) -> str:
    return html.escape(str(text))


def _badge(severity: str) -> str:
    css_class = f"badge badge-{severity}" if severity in _SEVERITY_COLORS else "badge"
    return f'<span class="{css_class}">{_esc(severity)}</span>'


def _status_label(status: str) -> str:
    return {
        "pass": "达标",
        "warning": "需确认",
        "failed": "未达标",
        "blocked": "严重未达标",
        "unknown": "证据不足",
    }.get(status, status or "未知")


def _meta_table(rows: list[tuple[str, str]]) -> str:
    lines = ['<table><tbody>']
    for label, value in rows:
        lines.append(f'<tr><th>{_esc(label)}</th><td>{value}</td></tr>')
    lines.append('</tbody></table>')
    return "\n".join(lines)


def _severity_summary_table(by_severity: dict[str, int]) -> str:
    if not by_severity:
        return "<p>未发现内置风险命中。</p>"
    lines = ['<table><thead><tr><th>严重程度</th><th>数量</th></tr></thead><tbody>']
    for severity, count in by_severity.items():
        lines.append(f'<tr><td>{_badge(severity)}</td><td>{count}</td></tr>')
    lines.append('</tbody></table>')
    return "\n".join(lines)


def _category_summary_table(by_category: dict[str, int]) -> str:
    if not by_category:
        return "<p>未发现内置风险命中。</p>"
    lines = ['<table><thead><tr><th>风险类型</th><th>数量</th></tr></thead><tbody>']
    for category, count in by_category.items():
        lines.append(f'<tr><td>{_esc(category)}</td><td>{count}</td></tr>')
    lines.append('</tbody></table>')
    return "\n".join(lines)


def _findings_section(findings: list[dict], limit: int = 200) -> str:
    if not findings:
        return "<p>未发现详细风险命中。</p>"
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_findings = sorted(
        findings,
        key=lambda f: (severity_rank.get(f.get("severity", ""), 4), f.get("file", ""), f.get("line", 1)),
    )
    lines = []
    for finding in sorted_findings[:limit]:
        severity = finding.get("severity", "unknown")
        lines.append(f'<div class="finding-card {_esc(severity)}">')
        lines.append(f'  <strong>{_badge(severity)} {_esc(finding.get("title", ""))}</strong>')
        lines.append(f'  <ul class="meta-list">')
        lines.append(f'    <li>位置：<code>{_esc(finding.get("file", ""))}:{finding.get("line", 1)}</code></li>')
        lines.append(f'    <li>类型：{_esc(finding.get("category", ""))}</li>')
        lines.append(f'    <li>原因：{_esc(finding.get("message", ""))}</li>')
        lines.append(f'    <li>代码：<code>{_esc(finding.get("snippet", ""))}</code></li>')
        lines.append(f'  </ul>')
        lines.append(f'</div>')
    if len(sorted_findings) > limit:
        lines.append(f'<p>其余 {len(sorted_findings) - limit} 条命中请查看 JSON 证据包。</p>')
    return "\n".join(lines)


def _changed_files_section(changed_files: list[str]) -> str:
    if not changed_files:
        return "<p>未从版本系统发现变更文件。</p>"
    lines = ["<details><summary>变更文件列表（共 %d 个）</summary><ul>" % len(changed_files)]
    for path in changed_files[:120]:
        lines.append(f'<li><code>{_esc(path)}</code></li>')
    if len(changed_files) > 120:
        lines.append(f'<li>其余 {len(changed_files) - 120} 个文件略。</li>')
    lines.append("</ul></details>")
    return "\n".join(lines)


def _mermaid_section(mermaid_code: str) -> str:
    if not mermaid_code.strip():
        return ""
    return f'<div class="mermaid">\n{mermaid_code.strip()}\n</div>'


def _contracts_section(contracts: list[dict]) -> str:
    if not contracts:
        return "<p>未启用或未提取到业务契约。</p>"
    lines = ['<details><summary>业务契约列表（共 %d 条）</summary><ul>' % len(contracts)]
    for contract in contracts[:120]:
        lines.append(
            f'<li><code>{_esc(contract.get("id", ""))}</code> '
            f'<code>{_esc(contract.get("source", ""))}</code> '
            f'{_esc(contract.get("kind", ""))} '
            f'<code>{_esc(contract.get("file", ""))}:L{contract.get("line", 1)}</code> '
            f'{_esc(contract.get("text", "")[:120])}</li>'
        )
    if len(contracts) > 120:
        lines.append(f'<li>其余 {len(contracts) - 120} 条略。</li>')
    lines.append("</ul></details>")
    return "\n".join(lines)


def _obligations_section(obligations: list[dict]) -> str:
    if not obligations:
        return "<p>无。</p>"
    lines = []
    for obligation in obligations[:100]:
        lines.append('<div class="finding-card high">')
        lines.append(
            f'  <strong><code>{_esc(obligation.get("priority", ""))}</code> '
            f'<code>{_esc(obligation.get("contract_id", ""))}</code> '
            f'<code>{_esc(obligation.get("file", ""))}:L{obligation.get("line", 1)}</code></strong>'
        )
        lines.append(f'  <ul class="meta-list">')
        lines.append(f'    <li>契约：{_esc(obligation.get("contract_text", ""))}</li>')
        lines.append(f'    <li>未检查原因：{_esc(obligation.get("reason", ""))}</li>')
        tokens = obligation.get("tokens", [])
        lines.append(f'    <li>反查标识符：{_esc(", ".join(tokens)) if tokens else "无"}</li>')
        candidates = obligation.get("candidates", [])
        if candidates:
            lines.append("    <li>候选实现位置：<ul>")
            for candidate in candidates[:8]:
                lines.append(
                    f'      <li><code>{_esc(candidate.get("file", ""))}:L{candidate.get("line", 1)}</code> '
                    f'命中 <code>{_esc(", ".join(candidate.get("tokens", [])))}</code>：'
                    f'{_esc(candidate.get("snippet", ""))}</li>'
                )
            lines.append("    </ul></li>")
        else:
            lines.append("    <li>候选实现位置：未自动定位，必须人工搜索契约涉及的接口或字段。</li>")
        lines.append(f'  </ul>')
        lines.append('</div>')
    return "\n".join(lines)


def _audit_coverage_section(audit_coverage: dict) -> str:
    lines = [
        f'<p>状态：<code>{_esc(audit_coverage.get("status", "unknown"))}</code></p>',
        f'<p>说明：{_esc(audit_coverage.get("message", ""))}</p>',
        f'<p>自动契约覆盖率：{audit_coverage.get("contract_coverage_percent", 100)}%</p>',
        f'<p>必须人工核验任务数：{audit_coverage.get("manual_review_obligation_count", 0)}</p>',
    ]
    reasons = audit_coverage.get("reasons", [])
    if reasons:
        lines.append("<ul>")
        for reason in reasons:
            lines.append(
                f'<li>{_badge(reason.get("severity", ""))} '
                f'<code>{_esc(reason.get("code", ""))}</code> '
                f'{_esc(reason.get("message", ""))}</li>'
            )
        lines.append("</ul>")
    else:
        lines.append("<p>未发现当前规则支持的审计覆盖缺口。</p>")
    return "\n".join(lines)


def _delivery_score_cell(cell: dict, anchor: str) -> str:
    status = cell.get("status", "unknown")
    return (
        f'<a class="score-cell score-{_esc(status)}" href="#{_esc(anchor)}" '
        f'title="{_esc(cell.get("reason", ""))}">'
        f'<span>{cell.get("score", 0)}</span><small>{_esc(_status_label(status))}</small></a>'
    )


def _delivery_assessment_section(data: dict) -> str:
    assessment = data.get("delivery_assessment") or build_delivery_assessment(data)
    dimensions = assessment.get("dimensions", [])
    rows = assessment.get("rows", [])
    if not rows:
        return ""
    summary = assessment.get("summary", {})
    lines = [
        '<section id="delivery-assessment" class="score-panel">',
        "<h2>可交付评分矩阵</h2>",
        "<p>按需求、任务和业务契约聚合当前证据，快速判断每个功能点是否达到可交付程度。评分用于定位人工审查优先级，不替代最终业务验收。</p>",
        '<div class="score-summary">',
        f'<span class="score-chip">平均分：{summary.get("average_score", 0)}</span>',
        f'<span class="score-chip">评分项：{summary.get("row_count", len(rows))}</span>',
    ]
    by_status = summary.get("by_status", {})
    for status in ["pass", "warning", "failed", "blocked", "unknown"]:
        count = by_status.get(status, 0)
        if count:
            lines.append(f'<span class="score-chip">{_esc(_status_label(status))}：{count}</span>')
    if summary.get("truncated_count", 0):
        lines.append(f'<span class="score-chip">已折叠：{summary["truncated_count"]}</span>')
    lines.extend(["</div>", '<table class="score-matrix"><thead><tr><th>功能点/契约项</th>'])
    for dimension in dimensions:
        lines.append(f'<th title="{_esc(dimension.get("description", ""))}">{_esc(dimension.get("label", ""))}</th>')
    lines.append("</tr></thead><tbody>")
    for row in rows:
        anchor = row.get("detail_anchor", row.get("id", ""))
        lines.append("<tr>")
        lines.append(
            f'<th><a href="#{_esc(anchor)}" class="score-row-title">{_esc(row.get("label", ""))}</a>'
            f'<div class="score-row-meta"><code>{_esc(row.get("source", ""))}</code></div>'
            f'<div class="score-row-meta">{_esc(row.get("text", "")[:120])}</div></th>'
        )
        scores = row.get("scores", {})
        for dimension in dimensions:
            cell = scores.get(dimension.get("id", ""), {"score": 0, "status": "unknown", "reason": "无评分。"})
            lines.append(f"<td>{_delivery_score_cell(cell, anchor)}</td>")
        lines.append("</tr>")
    lines.append("</tbody></table>")
    lines.append("<h3>评分详情</h3>")
    for row in rows:
        anchor = row.get("detail_anchor", row.get("id", ""))
        lines.append(f'<div id="{_esc(anchor)}" class="score-detail-card">')
        lines.append(f'<h4>{_esc(row.get("label", ""))}</h4>')
        lines.append(f'<p><code>{_esc(row.get("source", ""))}</code> {_esc(row.get("text", ""))}</p>')
        lines.append('<div class="score-detail-grid">')
        scores = row.get("scores", {})
        for dimension in dimensions:
            cell = scores.get(dimension.get("id", ""), {})
            status = cell.get("status", "unknown")
            lines.append(f'<div class="score-detail-item {_esc(status)}">')
            lines.append(
                f'<strong>{_esc(dimension.get("label", ""))}：{cell.get("score", 0)} '
                f'{_esc(_status_label(status))}</strong>'
            )
            lines.append(f'<p>{_esc(cell.get("reason", ""))}</p>')
            evidence = cell.get("evidence", [])
            if evidence:
                lines.append("<ul>")
                for item in evidence[:6]:
                    lines.append(f"<li>{_esc(item)}</li>")
                lines.append("</ul>")
            lines.append("</div>")
        lines.append("</div>")
        lines.append('<p><a href="#delivery-assessment">返回评分矩阵</a></p>')
        lines.append("</div>")
    lines.append("</section>")
    return "\n".join(lines)


def _contract_check_section(contract_check: dict) -> str:
    violations = contract_check.get("violations", [])
    unchecked = contract_check.get("unchecked_contracts", [])
    lines = [
        f'<p>状态：<code>{_esc(contract_check.get("status", "disabled"))}</code></p>',
        f'<p>说明：{_esc(contract_check.get("message", ""))}</p>',
        f'<p>启用契约总数：{contract_check.get("total_contracts", 0)}；'
        f'检查契约数：{contract_check.get("checked_contracts", 0)}；'
        f'未检查契约数：{len(unchecked)}；违反契约数：{len(violations)}</p>',
    ]
    if unchecked:
        lines.append("<h3>未检查契约</h3><ul>")
        for item in unchecked[:100]:
            lines.append(
                f'<li><code>{_esc(item.get("contract_id", ""))}</code> '
                f'<code>{_esc(item.get("kind", ""))}</code> '
                f'<code>{_esc(item.get("file", ""))}:L{item.get("line", 1)}</code> '
                f'{_esc(item.get("reason", ""))}</li>'
            )
        lines.append("</ul>")
    if violations:
        lines.append("<h3>违反契约</h3>")
        for violation in violations[:100]:
            contract = violation.get("contract", {})
            severity = violation.get("severity", "high")
            lines.append(f'<div class="finding-card {_esc(severity)}">')
            lines.append(
                f'<strong>{_badge(severity)} {_esc(violation.get("type", ""))} '
                f'来源契约 <code>{_esc(contract.get("id", ""))}</code></strong>'
            )
            lines.append("<ul class=\"meta-list\">")
            lines.append(f'<li>位置：<code>{_esc(violation.get("file", ""))}:L{violation.get("line", 1)}</code></li>')
            lines.append(f'<li>原因：{_esc(violation.get("message", ""))}</li>')
            lines.append(f'<li>期望：<code>{_esc(violation.get("expected", ""))}</code></li>')
            lines.append(f'<li>实际：<code>{_esc(violation.get("actual", ""))}</code></li>')
            lines.append("</ul></div>")
    else:
        lines.append("<p>未发现当前规则支持的契约违反。</p>")
    differences = contract_check.get("differences", [])
    lines.append("<h3>结构化差异</h3>")
    if differences:
        lines.append("<ul>")
        for difference in differences[:100]:
            changed = difference.get("changed", [])
            changed_text = "；变化：" + ", ".join(
                f'{item.get("path", "")}={item.get("actual", "")}（期望 {item.get("expected", "")}）'
                for item in changed
            ) if changed else ""
            lines.append(
                f'<li><code>{_esc(difference.get("kind", difference.get("type", "")))}</code> '
                f'<code>{_esc(difference.get("file", ""))}:L{difference.get("line", 1)}</code> '
                f'缺失：<code>{_esc(", ".join(str(item) for item in difference.get("missing", [])) or "无")}</code>；'
                f'新增：<code>{_esc(", ".join(str(item) for item in difference.get("added", [])) or "无")}</code>'
                f'{_esc(changed_text)}</li>'
            )
        lines.append("</ul>")
    else:
        lines.append("<p>未生成结构化差异。</p>")
    return "\n".join(lines)


def _java_analysis_section(java_analysis: dict) -> str:
    coverage = java_analysis.get("coverage", {})
    graph = java_analysis.get("target", {}).get("code_graph", {})
    comparison = java_analysis.get("comparison", {})
    changes = comparison.get("changes", [])
    lines = [
        f'<p>状态：<code>{_esc(java_analysis.get("status", "disabled"))}</code></p>',
        f'<p>说明：{_esc(java_analysis.get("message", ""))}</p>',
        "<h3>Java 分析覆盖率</h3>",
        "<ul>",
        f'<li>Java 文件总数：{coverage.get("java_files_total", 0)}</li>',
        f'<li>成功解析：{coverage.get("java_files_parsed", 0)}</li>',
        f'<li>解析失败：{coverage.get("java_files_failed", 0)}</li>',
        f'<li>核心证据完整：{"是" if coverage.get("core_complete") else "否"}</li>',
        f'<li>调用图完整：{"是" if coverage.get("graph_complete") else "否"}</li>',
        f'<li>baseline/target 比较完整：{"是" if coverage.get("comparison_complete") else "否"}</li>',
        "</ul>",
        "<h3>调用链与影响范围</h3>",
        f'<p>状态：<code>{_esc(graph.get("status", "disabled"))}</code>；'
        f'调用者证据：{len(graph.get("callers", []))}；'
        f'被调方法证据：{len(graph.get("callees", []))}；'
        f'影响范围证据：{len(graph.get("impacts", []))}；'
        f'受影响测试：{len(graph.get("affected_tests", []))}</p>',
    ]
    if graph.get("affected_tests"):
        lines.append("<ul>")
        for test in graph.get("affected_tests", [])[:50]:
            lines.append(f'<li><code>{_esc(test)}</code></li>')
        lines.append("</ul>")
    lines.extend([
        "<h3>baseline/target 业务语义差异</h3>",
        f'<p>状态：<code>{_esc(comparison.get("status", "disabled"))}</code></p>',
        f'<p>说明：{_esc(comparison.get("message", ""))}</p>',
        f'<p>语义变化数：{len(changes)}</p>',
    ])
    if changes:
        for change in changes[:100]:
            severity = change.get("severity", "medium")
            lines.append(f'<div class="finding-card {_esc(severity)}">')
            lines.append(f'<strong>{_badge(severity)} {_esc(change.get("type", ""))}</strong>')
            lines.append("<ul class=\"meta-list\">")
            lines.append(f'<li>位置：<code>{_esc(change.get("file", ""))}:L{change.get("line", 1)}</code></li>')
            lines.append(f'<li>说明：{_esc(change.get("message", ""))}</li>')
            lines.append("</ul></div>")
    return "\n".join(lines)


def _suppressed_section(suppressed_findings: list[dict], suppression_summary: dict) -> str:
    if not suppressed_findings:
        return "<p>无。</p>"
    lines = ["<ul>"]
    for reason, count in suppression_summary.get("by_reason", {}).items():
        lines.append(f"<li><code>{_esc(reason)}</code>：{count}</li>")
    lines.append(f"<li>完整线索保留在 JSON 证据包的 <code>suppressed_findings</code> 中，共 {len(suppressed_findings)} 条。</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def make_html_report(data: dict) -> str:
    """基于检查数据生成自包含 HTML 报告。"""
    changes = data.get("changes", {})
    summary = data.get("summary", {})
    findings = data.get("findings", [])
    audit_coverage = data.get("audit_coverage", {})
    business_contracts = data.get("business_contracts", [])
    contract_check = data.get("business_contract_check", {})
    obligations = data.get("manual_review_obligations", [])
    mermaid_code = data.get("mermaid", "")
    java_analysis = data.get("java_analysis", {})
    audit_plan = data.get("audit_plan", {})
    audit_plan_summary = (
        f'已确认审计计划 <code>{_esc(audit_plan.get("path", ""))}</code>'
        if audit_plan.get("confirmed")
        else "未使用已确认审计计划"
    )

    meta_rows = [
        ("生成时间", f'<code>{_esc(data.get("generated_at", ""))}</code>'),
        ("项目路径", f'<code>{_esc(data.get("project", ""))}</code>'),
        ("执行计划", audit_plan_summary),
        ("变更来源", f'<code>{_esc(changes.get("source", ""))}</code>'),
        ("变更范围", f'<code>{_esc(changes.get("range", ""))}</code>'),
        ("变更文件数", str(len(changes.get("changed_files", [])))),
        ("需求/任务文档数", str(len(data.get("specs", [])))),
        ("候选业务契约数", str(len(data.get("contract_candidates", [])))),
        ("启用业务契约数", str(len(business_contracts))),
        ("风险命中数", str(len(findings))),
        ("已抑制文本线索数", str(len(data.get("suppressed_findings", [])))),
    ]

    body_parts = [
        "<h1>代码变更检查报告</h1>",
        _delivery_assessment_section(data),
        _meta_table(meta_rows),
        '<h2 id="overview">总览</h2>',
        "<h3>按严重程度</h3>",
        _severity_summary_table(summary.get("by_severity", {})),
        "<h3>按风险类型</h3>",
        _category_summary_table(summary.get("by_category", {})),
        '<h2 id="audit-coverage">审计覆盖质量闸门</h2>',
        _audit_coverage_section(audit_coverage),
        '<h2 id="manual-review-obligations">必须人工核验的未检查契约</h2>',
        _obligations_section(obligations),
        '<h2 id="suppressed-findings">已抑制文本线索</h2>',
        _suppressed_section(data.get("suppressed_findings", []), data.get("suppression_summary", {})),
        '<h2 id="changed-files">变更文件</h2>',
        _changed_files_section(changes.get("changed_files", [])),
        '<h2 id="business-contracts">业务契约</h2>',
        _contracts_section(business_contracts),
        '<h2 id="business-contract-check">业务契约执行结果</h2>',
        _contract_check_section(contract_check),
        '<h2 id="mermaid-risk-graph">Mermaid 风险图</h2>',
        _mermaid_section(mermaid_code),
        '<h2 id="java-analysis">Java 语义分析</h2>',
        _java_analysis_section(java_analysis),
        '<h2 id="detailed-findings">详细风险命中</h2>',
        _findings_section(findings),
        '<h2 id="suggested-verification">建议验证</h2>',
        "<ul>",
        "<li>对 <code>critical</code> 和 <code>high</code> 位置做人工阅读。</li>",
        "<li>对网络调用核对内外部寻址、超时、重试和鉴权。</li>",
        "<li>对数据库写入核对事务、条件、并发和幂等。</li>",
        "<li>对权限、状态、金额、库存相关路径补充回归测试。</li>",
        "<li>将项目隐式规则沉淀为 <code>--rules</code> 可执行规则，降低下次误漏。</li>",
        "</ul>",
    ]

    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>代码变更检查报告</title>",
        f"<style>{_CSS}</style>",
        _MERMAID_SCRIPT,
        "</head>",
        "<body>",
        *body_parts,
        _MERMAID_INIT,
        "</body>",
        "</html>",
    ]) + "\n"
