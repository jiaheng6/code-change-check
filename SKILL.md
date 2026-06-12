---
name: code-change-check
description: Use when reviewing Java code changes produced by AI or humans, especially when syntax is valid but business value sources, parameters, addressing, guards, state conditions, or legacy behavior may be subtly wrong.
---

# code-change-check

## 目标

通过迭代范围、需求、业务契约、Spoon Java 语义证据和 CodeGraph 调用链证据，发现需要逐行阅读大量代码才能识别的细微业务偏差。

## 硬规则

1. 在 Claude Code、Codex、Cline 或无 TTY 环境中，先运行 `--print-context`，再在聊天中确认项目根目录、迭代范围、需求材料和业务契约来源。
2. 当前目录是 Git/SVN 子目录时，必须向用户说明根目录与当前目录的差异，确认实际审查目录。
3. 检测到 Java 文件后直接运行 Spoon 和 CodeGraph，不增加额外启用确认步骤。
4. 不调用目标项目的 Maven、Gradle、构建脚本或私有依赖仓库。
5. 契约文件优先于 baseline 旧代码推导出的候选契约。旧代码候选契约必须让用户确认。
6. `blocked` 状态禁止给出“可以合并”或“未发现风险”结论；`partial` 状态必须明确覆盖限制。
7. 最终风险项必须包含契约或需求证据、代码位置、偏差说明、业务影响和验证方式。

## 执行流程

1. 预检：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --print-context
```

2. 确认范围与契约来源后，生成审计计划：

```bash
path/to/code-change-check/run-code-change-check.cmd --project selected-root --base-ref main --target-ref HEAD --contract-source existing-code --java-analysis auto --no-interactive --save-audit-plan code-change-check-audit-plan.json
```

3. 展示计划中的项目目录、范围、需求、契约来源、`review_warnings` 和缺失材料，获得用户确认后执行：

```bash
path/to/code-change-check/run-code-change-check.cmd --confirm-audit-plan code-change-check-audit-plan.json
path/to/code-change-check/run-code-change-check.cmd --audit-plan code-change-check-audit-plan.json
```

4. 优先解读：

- `audit_coverage.status`
- `java_analysis.coverage`
- `java_analysis.comparison.changes`
- `java_analysis.target.code_graph`
- `business_contract_check.violations`
- `manual_review_obligations`

## Java 语义分析

- Spoon 使用 `NOCLASSPATH` 模式，不要求目标项目可编译。
- CodeGraph 由 Skill 管理，不要求用户安装 Node.js 或全局工具。
- 系统缺少 Java 17 时，运行时管理器会使用固定版本和摘要校验自动准备便携运行时。
- `--offline` 禁止联网；缺少缓存时必须明确报告不可用。
- `--java-analysis required` 要求完整成功，否则命令返回非零状态。

详细说明见：

- `references/workflow.md`
- `references/java-analysis.md`
- `references/tool-runtime.md`
- `references/report-schema.md`
- `references/business-contracts.md`
