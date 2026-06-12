# 审计计划

审计计划用于锁定用户在聊天或交互向导中确认的范围，避免最终执行命令重新使用错误目录、额外需求文档或额外契约。

## 无 TTY 环境流程

1. 使用 `--print-context` 识别 Git、SVN、SVN 不兼容状态和推荐根目录。
2. 在聊天里确认代码审计目录、版本范围、需求文档、契约来源和 CodeQL。
3. 使用全部显式参数和 `--save-audit-plan` 生成计划。该步骤不生成报告。
4. 读取计划 JSON，向用户展示其中的 `project`、`spec`、`contract`、版本范围、CodeQL 和输出目录。
5. 用户确认后，使用 `--confirm-audit-plan` 标记计划。
6. 使用 `--audit-plan` 执行。未确认计划会被拒绝。

确认动作会为计划内容写入 SHA-256 摘要。计划确认后，只要代码范围、需求、契约、CodeQL 或其他执行参数被修改，执行阶段就会拒绝该计划，必须重新展示并确认。

## 范围规则

- `project` 是实际代码扫描和 CodeQL 分析根目录。用户选择子项目时，必须使用子项目路径，不能继续使用父目录。
- 用户只选择部分 OpenSpec、需求或任务目录时，使用 `--strict-spec`。
- 用户只选择部分契约文件或目录时，使用 `--strict-contract`。
- `--spec` 和 `--contract` 支持文件或目录；目录会递归读取支持的文件。
- JSON 契约需要实际响应验证时，把同文件名响应通过 `--response-snapshot` 写入计划。
- `--include-support-findings` 会把测试、文档、调试、fixture 和 XML namespace 文本线索重新纳入正式风险，必须由用户明确选择。
- 需求或契约位于代码目录之外时，可以传绝对路径，或传相对于 `project` 的路径。
- `svn-incompatible` 不能自动降级。只有用户明确选择目录快照时才使用 `--scan-all`，或提供 `--baseline`。

## 示例

用户选择只审计后端子项目和两个 OpenSpec change：

```bash
path/to/code-change-check/run-code-change-check.cmd \
  --project ctm01sboard-business \
  --spec ../openspec/changes/overview-controller-realdata \
  --spec ../openspec/changes/safety-energy-controller-realdata \
  --strict-spec \
  --contract ../docs/api-mock-backup \
  --strict-contract \
  --contract-source file \
  --scan-all \
  --codeql \
  --codeql-build-mode autobuild \
  --no-interactive \
  --output code-change-check-output \
  --save-audit-plan code-change-check-audit-plan.json
```

确认并执行：

```bash
path/to/code-change-check/run-code-change-check.cmd --confirm-audit-plan code-change-check-audit-plan.json
path/to/code-change-check/run-code-change-check.cmd --audit-plan code-change-check-audit-plan.json
```

JSON 证据包和 Markdown 报告会记录是否通过已确认计划执行。直接执行仍被支持，但报告会标记“未使用已确认审计计划”。
