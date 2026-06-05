# 三个目标工具的适配方式

## Claude Code

将仓库复制或克隆到：

```text
~/.claude/skills/code-change-check/
```

目录内必须包含 `SKILL.md`，脚本和参考文件保持相对路径不变。

Windows 用户优先运行根目录的 `run-code-change-check.cmd` 或 `run-code-change-check.ps1`。macOS/Linux 用户优先运行 `run-code-change-check.sh`。启动器会检测 Python 3.10+，没有时会给出中文安装提示。没有显式变动范围时，启动器默认进入交互向导；自动化场景追加 `--no-interactive`。

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
Windows 用户优先通过 `run-code-change-check.cmd` 或 `run-code-change-check.ps1` 间接调用脚本；macOS/Linux 用户优先通过 `run-code-change-check.sh` 间接调用脚本。没有显式变动范围时，启动器默认进入交互向导；自动化场景追加 `--no-interactive`。
