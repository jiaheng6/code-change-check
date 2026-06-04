# 代码变更检查

当用户要求检查 AI 或人工完成的代码变更、分析 Git/SVN/目录快照、核对需求实现、发现业务逻辑误解、内部寻址错误、权限遗漏、状态流转错误或第三方对接风险时，使用 `code-change-check` 流程。

优先读取技能目录中的文件：

- `SKILL.md`
- `references/workflow.md`
- `references/risk-rules.md`
- `references/adapters.md`

需要提取证据时，运行：

```bash
python path/to/code-change-check/scripts/code_change_check.py --project . --output code-change-check-output
```

如果用户没有明确给出版本范围，优先使用交互式提交选择：

```bash
python path/to/code-change-check/scripts/code_change_check.py --project . --interactive --output code-change-check-output
```

交互模式支持方向键移动、空格多选、回车提交、`q` 取消。

如果用户提供需求、设计或任务文档，使用：

```bash
python path/to/code-change-check/scripts/code_change_check.py --project . --spec docs/spec.md --output code-change-check-output
```

如果用户指定 Git 或 SVN 迭代范围，使用：

```bash
python path/to/code-change-check/scripts/code_change_check.py --project . --base-ref main --target-ref HEAD --output code-change-check-output
python path/to/code-change-check/scripts/code_change_check.py --project . --svn-revision 100:120 --output code-change-check-output
```

输出必须包含：

- 总体结论。
- 高风险清单。
- 人工优先阅读位置。
- 文件、行号和风险原因。
- 需要补充的测试或运行验证。
- 需求、设计、任务和代码之间的缺口。
