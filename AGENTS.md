# AGENTS.md

## 语言要求

- 除必要术语、名词、变量、命令和路径外，所有成果物使用中文简体。
- 代码注释、文档、提示词、报告和日志默认使用中文简体。

## 项目说明

- 本仓库是 `code-change-check` 技能包。
- 根目录本身就是可安装的 skill 目录，必须保留 `SKILL.md`。
- `scripts/` 放确定性脚本。
- `references/` 放按需读取的详细说明。
- `assets/` 放示例规则和模板。
- `adapters/` 放 Claude Code、Codex、Cline 之外的轻量适配入口。
- 修改需求、提交、风险或报告结构时，同步更新 `references/report-schema.md`。

## 验证命令

- 自检：`python scripts/code_change_check.py --project . --output code-change-check-output --scan-all`
- 单元测试：`python tests/test_interactive_selection.py`
- 契约测试：`python tests/test_contracts.py`
- 启动器测试：`python tests/test_launchers.py`
- CodeQL 支撑测试：`python tests/test_codeql_support.py`
- CodeQL 集成测试：`python tests/test_codeql_integration.py`
