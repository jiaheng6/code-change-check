# 代码变更检查

当用户要求检查 AI 或人工完成的代码变更、分析 Git/SVN/目录快照、核对需求实现、发现业务逻辑误解、内部寻址错误、权限遗漏、状态流转错误或第三方对接风险时，使用 `code-change-check` 流程。

优先读取技能目录中的文件：

- `SKILL.md`
- `references/workflow.md`
- `references/risk-rules.md`
- `references/business-contracts.md`
- `references/codeql.md`
- `references/adapters.md`

需要提取证据时，运行：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --output code-change-check-output
```

PowerShell 可使用：

```powershell
powershell -ExecutionPolicy Bypass -File path/to/code-change-check/run-code-change-check.ps1 --project . --output code-change-check-output
```

macOS/Linux 可使用：

```bash
sh path/to/code-change-check/run-code-change-check.sh --project . --output code-change-check-output
```

如果用户没有明确给出版本范围，优先使用交互式提交选择：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --interactive --output code-change-check-output
```

交互模式支持方向键移动、空格多选、回车提交、`q` 取消。

如果发现需求、设计或任务文档，交互模式会继续让用户把每个提交关联到对应需求/任务。用户明确不需要时追加 `--no-map-requirements`。

交互模式还会让用户选择业务契约来源：

- 使用指定契约文件。
- 从迭代前旧代码自动提取。
- 两者都用。
- 本次不使用业务契约。

旧代码候选契约必须让用户确认后再用于审计。用户明确不需要确认时追加 `--no-confirm-contracts`。

交互模式会询问是否启用 CodeQL。非交互模式需要显式使用：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --codeql --output code-change-check-output
```

当用户要求 CodeQL 必须完成时使用 `--require-codeql`。CodeQL 不可用或执行失败时，该模式必须返回失败状态。

如果用户提供需求、设计或任务文档，使用：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --spec docs/spec.md --output code-change-check-output
```

如果用户指定 Git 或 SVN 迭代范围，使用：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --base-ref main --target-ref HEAD --output code-change-check-output
path/to/code-change-check/run-code-change-check.cmd --project . --svn-revision 100:120 --output code-change-check-output
```

输出必须包含：

- 总体结论。
- 高风险清单。
- 人工优先阅读位置。
- 文件、行号和风险原因。
- 需要补充的测试或运行验证。
- 需求、设计、任务和代码之间的缺口。
- 需求-提交映射缺口。
- 业务契约来源、候选契约和启用契约。
- CodeQL 状态、分析语言、数据库缓存状态和命中。
