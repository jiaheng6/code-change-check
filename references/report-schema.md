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
- `findings`：风险命中列表。
- `summary`：按严重程度、类型、文件聚合的统计。
- `mermaid`：风险类型图。

## Markdown 报告

`code-change-check-report.md` 包含：

- 总览。
- 变更文件。
- 本次迭代提交记录。
- 需求-提交映射。
- 需求和任务线索。
- Mermaid 风险图。
- 人工优先阅读清单。
- 详细风险命中。
- 建议验证。
