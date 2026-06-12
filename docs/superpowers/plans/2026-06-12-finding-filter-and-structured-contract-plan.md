# 风险命中过滤与结构化契约实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 降低文本规则误报，并让业务契约检查提供可验证的结构化差异和未检查状态。

**Architecture:** 新建独立的命中过滤模块，保持文本扫描和报告生成解耦；在契约规则模块中增加 JSON shape 与结构化 difference，主脚本只负责组装输入输出。

**Tech Stack:** Python 3.10+、`unittest`、JSON、现有轻量语义清单。

---

### Task 1: 文本规则命中过滤

**Files:**
- Create: `scripts/finding_filter.py`
- Create: `tests/test_finding_filter.py`
- Modify: `scripts/code_change_check.py`
- Modify: `scripts/audit_plan.py`

- [x] 写测试，覆盖测试、文档、debug、fixture、XML namespace 和生产代码分类。
- [x] 运行 `python tests/test_finding_filter.py`，确认因模块不存在而失败。
- [x] 实现 `classify_finding` 和 `partition_findings`。
- [x] 在主流程中写入 `suppressed_findings`、`suppression_summary`，增加 `--include-support-findings`。
- [x] 运行聚焦测试并确认通过。

### Task 2: JSON shape 契约提取

**Files:**
- Modify: `scripts/code_change_check.py`
- Modify: `tests/test_contracts.py`

- [x] 写测试，覆盖嵌套对象、数组和稳定字段路径。
- [x] 运行 `python tests/test_contracts.py`，确认 JSON 契约尚未提取而失败。
- [x] 实现 JSON shape 路径提取和 `json-shape` 契约生成。
- [x] 增加 `--response-snapshot` 参数并锁定到审计计划。
- [x] 运行聚焦测试并确认通过。

### Task 3: 结构化契约差异与未检查状态

**Files:**
- Modify: `scripts/contract_rules.py`
- Modify: `tests/test_contract_rules.py`
- Modify: `scripts/code_change_check.py`

- [x] 写测试，覆盖调用参数 difference、JSON 缺失字段和无快照未检查状态。
- [x] 运行 `python tests/test_contract_rules.py`，确认测试失败。
- [x] 为违反项增加 `difference`，为执行结果增加总数、已检查和未检查契约。
- [x] 在主流程中加载实际响应快照并传给契约执行器。
- [x] 运行聚焦测试并确认通过。

### Task 4: 报告与文档

**Files:**
- Modify: `scripts/code_change_check.py`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `SKILL.md`
- Modify: `references/business-contracts.md`
- Modify: `references/report-schema.md`

- [x] 在 Markdown 报告展示抑制数量、原因、未检查契约和结构化差异。
- [x] 更新中英文使用说明和 skill 工作流。
- [x] 运行 `python -m unittest discover -s tests -p "test_*.py"`。
- [x] 运行 Python 编译、`git diff --check` 和 skill 校验。
- [ ] 提交并推送，确保 `debug/` 未进入提交。
