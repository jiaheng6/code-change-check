# 审计计划

审计计划锁定项目目录、迭代范围、需求材料、契约来源、Java 分析模式、运行时缓存和离线模式。确认后任何字段变化都会使确认摘要失效。

```bash
run-code-change-check.cmd --project . --base-ref main --target-ref HEAD --contract-source existing-code --java-analysis auto --no-interactive --save-audit-plan code-change-check-audit-plan.json
run-code-change-check.cmd --confirm-audit-plan code-change-check-audit-plan.json
run-code-change-check.cmd --audit-plan code-change-check-audit-plan.json
```

确认前必须展示 `review_warnings`、缺失契约材料和输入角色冲突。
