#!/usr/bin/env python3
"""HTML 格式报告生成器。

基于 make_report() 使用的同一数据结构，生成自包含 HTML 文件。
支持颜色标注严重级别、Mermaid 图渲染、可折叠区域和表格化摘要。
"""
from __future__ import annotations

import html
import json
from typing import Any


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
"""

_MERMAID_SCRIPT = '<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>'
_MERMAID_INIT = "<script>mermaid.initialize({startOnLoad:true});</script>"


def _esc(text: Any) -> str:
    return html.escape(str(text))


def _badge(severity: str) -> str:
    css_class = f"badge badge-{severity}" if severity in _SEVERITY_COLORS else "badge"
    return f'<span class="{css_class}">{_esc(severity)}</span>'


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
        key=lambda f: (severity_rank.get(f.get("severity", ""), 4), f.get("file", ""), f.get("line", 0)),
    )
    lines = []
    for finding in sorted_findings[:limit]:
        severity = finding.get("severity", "unknown")
        lines.append(f'<div class="finding-card {_esc(severity)}">')
        lines.append(f'  <strong>{_badge(severity)} {_esc(finding.get("title", ""))}</strong>')
        lines.append(f'  <ul class="meta-list">')
        lines.append(f'    <li>位置：<code>{_esc(finding.get("file", ""))}:{finding.get("line", 0)}</code></li>')
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
    return f'<div class="mermaid">\n{_esc(mermaid_code.strip())}\n</div>'


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


def make_html_report(data: dict) -> str:
    """基于检查数据生成自包含 HTML 报告。"""
    changes = data.get("changes", {})
    summary = data.get("summary", {})
    findings = data.get("findings", [])
    audit_coverage = data.get("audit_coverage", {})
    business_contracts = data.get("business_contracts", [])
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
        _meta_table(meta_rows),
        "<h2>总览</h2>",
        "<h3>按严重程度</h3>",
        _severity_summary_table(summary.get("by_severity", {})),
        "<h3>按风险类型</h3>",
        _category_summary_table(summary.get("by_category", {})),
        "<h2>审计覆盖质量闸门</h2>",
        _audit_coverage_section(audit_coverage),
        "<h2>必须人工核验的未检查契约</h2>",
        _obligations_section(obligations),
        "<h2>变更文件</h2>",
        _changed_files_section(changes.get("changed_files", [])),
        "<h2>业务契约</h2>",
        _contracts_section(business_contracts),
        "<h2>Mermaid 风险图</h2>",
        _mermaid_section(mermaid_code),
        "<h2>Java 语义分析</h2>",
        f'<p>状态：<code>{_esc(java_analysis.get("status", "disabled"))}</code></p>',
        f'<p>说明：{_esc(java_analysis.get("message", ""))}</p>',
        "<h2>详细风险命中</h2>",
        _findings_section(findings),
        "<h2>建议验证</h2>",
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
