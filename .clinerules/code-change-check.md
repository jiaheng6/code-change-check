# 代码变更检查

本仓库是 `code-change-check` 技能包。处理本仓库任务时：

- 所有成果物使用中文简体，必要技术名、变量名和命令除外。
- 修改技能行为时，优先更新 `SKILL.md`。
- 修改确定性检查逻辑时，优先更新 `scripts/code_change_check.py`。
- 修改审计规则说明时，优先更新 `references/risk-rules.md`。
- 完成后运行 `python scripts/code_change_check.py --project . --output code-change-check-output --scan-all` 做自检。
