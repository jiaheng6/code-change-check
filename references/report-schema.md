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
- `codeql`：CodeQL 启用状态、CLI 状态、分析范围、语言、数据库、SARIF 文件和原始 CodeQL 命中。
- `findings`：风险命中列表。
- `summary`：按严重程度、类型、文件聚合的统计。
- `mermaid`：风险类型图。

## Markdown 报告

`code-change-check-report.md` 包含：

- 总览。
- 变更文件。
- 本次迭代提交记录。
- 需求-提交映射。
- 业务契约来源、候选契约数和启用契约。
- CodeQL 状态、分析范围、语言、数据库缓存状态和命中数。
- 需求和任务线索。
- Mermaid 风险图。
- 人工优先阅读清单。
- 详细风险命中。
- 建议验证。
