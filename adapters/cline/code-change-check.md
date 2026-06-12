# Cline：code-change-check

当用户要求审查 Java 代码变更时：

1. 先运行 `run-code-change-check.cmd --project . --print-context`。
2. 在聊天中确认实际项目根目录、Git/SVN/快照范围、需求材料和业务契约来源。
3. 检测到 Java 文件后自动运行 Java 语义分析，不询问是否启用。
4. 使用显式参数和 `--no-interactive` 生成审计计划，展示计划并获得用户确认后执行。
5. 优先解读字段映射、调用参数、寻址、guard、状态条件、调用链、受影响测试和覆盖质量闸门。

```bash
run-code-change-check.cmd --project selected-root --base-ref main --target-ref HEAD --contract-source existing-code --java-analysis auto --no-interactive --save-audit-plan code-change-check-audit-plan.json
run-code-change-check.cmd --confirm-audit-plan code-change-check-audit-plan.json
run-code-change-check.cmd --audit-plan code-change-check-audit-plan.json
```
