# 报告结构

## JSON 证据包

`code-change-check-evidence.json` 包含：

- `generated_at`：生成时间。
- `project`：项目路径。
- `changes`：变更来源、状态、diff 和变更文件。
- `changes.selected_commits`：交互模式下用户选择的 Git 提交或 SVN 版本。
- `specs`：需求、设计、任务文档摘要。
- `requirement_items`：从需求、设计、任务文档中抽出的可映射条目。
- `requirement_commit_mappings`：用户建立的需求-提交映射。
- `contract_source`：业务契约来源。
- `contract_candidates`：从契约文件或旧代码提取出的候选契约。
- `business_contracts`：用户确认后本次审计启用的业务契约。
- `response_snapshots`：用于 JSON 契约结构化对比的实际响应字段路径。
- `input_role_issues`：期望契约与实际响应快照使用同一路径或相同内容等输入角色冲突。
- `referenced_contract_artifacts`：选中文档引用的 JSON 契约材料。
- `missing_referenced_contract_artifacts`：文档引用但未纳入契约输入的 JSON 材料。
- `business_contract_check`：业务契约执行状态、总契约数、实际检查数、未检查契约、违反项和结构化差异。
- `manual_review_obligations`：由未检查契约生成的人工核验任务及候选代码位置。
- `audit_coverage`：自动契约覆盖率、覆盖质量状态和阻断/限制原因。
- `codeql`：target CodeQL 启用状态、CLI 状态、分析范围、语言、数据库、SARIF 文件和原始 CodeQL 命中。
- `codeql.comparison`：baseline/target 来源、两端状态、新增命中、已有命中、已消失命中和 baseline 分析证据。
- `codeql.comparison.semantic`：baseline/target 语义清单、语义对比状态，以及调用参数、寻址、租户字段和状态字段变化。
- `findings`：风险命中列表。
- `suppressed_findings`：测试、文档、调试日志、fixture 和 XML namespace 等默认不进入正式风险的文本线索。
- `suppression_summary`：按抑制原因汇总的线索数量。
- `summary`：按严重程度、类型、文件聚合的统计。
- `mermaid`：风险类型图。

## Markdown 报告

`code-change-check-report.md` 包含：

- 总览。
- 变更文件。
- 本次迭代提交记录。
- 需求-提交映射。
- 业务契约来源、候选契约数、启用契约和业务契约执行结果。
- 审计覆盖质量闸门、输入角色冲突、缺失引用契约材料和必须人工核验的未检查契约。
- CodeQL 状态、分析范围、语言、数据库缓存状态、两端对比状态、差异命中数和业务语义差异。
- 需求和任务线索。
- Mermaid 风险图。
- 人工优先阅读清单。
- 详细风险命中。
- 建议验证。
