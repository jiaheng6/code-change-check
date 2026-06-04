# 三个目标工具的适配方式

## Claude Code

将仓库复制或克隆到：

```text
~/.claude/skills/code-change-check/
```

目录内必须包含 `SKILL.md`，脚本和参考文件保持相对路径不变。

## Codex

将仓库复制或克隆到：

```text
~/.codex/skills/code-change-check/
```

Codex 会根据 `SKILL.md` 的 `name` 和 `description` 触发技能。

## Cline

Cline 使用 `.clinerules/` 规则。将 `adapters/cline/code-change-check.md` 复制到目标项目：

```text
<project>/.clinerules/code-change-check.md
```

该规则只负责触发和指向本技能目录，实际检查仍由 `scripts/code_change_check.py` 完成。
