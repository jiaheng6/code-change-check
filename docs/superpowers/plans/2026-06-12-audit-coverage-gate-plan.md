# 审计覆盖质量闸门实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 防止审计在契约覆盖为零、输入角色错误或关键契约材料缺失时给出低质量结论，并为未检查契约生成具体代码核验位置。

**Architecture:** 新增独立的 `audit_coverage.py` 负责输入角色校验、引用材料发现、人工核验任务和覆盖质量评估；审计计划和主执行流程消费其结果；报告与 Skill 将质量闸门置于普通风险之前。

**Tech Stack:** Python 3.10+、unittest、Markdown、Skill 指令。

---

### Task 1: 覆盖分析核心

**Files:**
- Create: `scripts/audit_coverage.py`
- Create: `tests/test_audit_coverage.py`

- [ ] 编写失败测试，覆盖引用 JSON 发现、同路径/同内容角色冲突、未检查契约代码反查和覆盖状态计算。
- [ ] 运行 `python -m unittest tests.test_audit_coverage`，确认因模块或行为缺失而失败。
- [ ] 实现最小覆盖分析核心。
- [ ] 重跑测试并确认通过。

### Task 2: 审计计划预警

**Files:**
- Modify: `scripts/audit_plan.py`
- Modify: `tests/test_audit_plan.py`

- [ ] 编写失败测试，要求计划记录全量扫描、缺失引用 JSON、快照角色冲突和 Java `none` 构建模式预警。
- [ ] 运行 `python -m unittest tests.test_audit_plan`，确认失败。
- [ ] 在计划生成时写入预警和引用材料信息。
- [ ] 重跑测试并确认通过。

### Task 3: 主流程与报告

**Files:**
- Modify: `scripts/code_change_check.py`
- Modify: `tests/test_contract_rules.py`
- Modify: `references/report-schema.md`

- [ ] 编写集成失败测试，要求证据包与报告包含覆盖质量闸门、缺失引用材料、输入角色冲突和人工核验任务。
- [ ] 运行目标测试并确认失败。
- [ ] 集成覆盖分析，排除冲突响应快照，并在报告顶部展示质量闸门。
- [ ] 重跑目标测试并确认通过。

### Task 4: Skill 与使用文档

**Files:**
- Modify: `SKILL.md`
- Modify: `references/workflow.md`
- Modify: `references/business-contracts.md`
- Modify: `references/audit-plan.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `tests/test_skill_instructions.py`

- [ ] 编写失败测试，锁定契约/快照角色、覆盖闸门、人工核验和 Maven/Gradle CodeQL 规则。
- [ ] 更新 Skill 和文档。
- [ ] 运行文档测试并确认通过。

### Task 5: 完整验证

- [ ] 运行 `python -m unittest discover -s tests -p "test_*.py"`。
- [ ] 运行 Python 编译检查。
- [ ] 运行 Skill 校验。
- [ ] 运行项目自检。
- [ ] 检查 `git diff --check` 和提交范围，确保 `debug/` 不进入提交。
