# 报告结构

JSON 证据包的关键字段：

```text
changes
specs
business_contracts
business_contract_check
java_analysis.status
java_analysis.coverage
java_analysis.target.core.evidence
java_analysis.target.code_graph
java_analysis.comparison.changes
audit_coverage
delivery_assessment
findings
manual_review_obligations
```

HTML 报告包含顶部可交付评分矩阵、Java 语义分析、Java 分析覆盖率、调用链与影响范围、baseline/target 业务语义差异、业务契约执行结果和人工核验清单。

`delivery_assessment` 是从同一证据包推导出的评分矩阵：

- `dimensions` 定义评分维度。
- `rows` 按需求、任务和业务契约列出评分项。
- `scores` 给出每个维度的分数、状态和原因。
- `summary` 汇总平均分、状态分布和被截断的评分项数量。
