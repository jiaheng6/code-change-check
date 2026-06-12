# AI 编程工具适配

## Claude Code 与 Codex

无 TTY 环境中，先通过聊天确认根目录、迭代范围、需求材料和契约来源，再使用显式参数加 `--no-interactive`。建议使用独立审查对话，避免开发上下文影响结论。

## Cline

使用 `adapters/cline/code-change-check.md` 或 `.clinerules/code-change-check.md`。

所有适配入口必须遵守：

- Java 分析自动执行，不询问是否启用。
- 不调用目标项目构建工具。
- 审计计划确认后才能执行。
- `blocked` 禁止给出安全结论。
