# AGENTS.md

## 语言要求

- 除必要术语、名词、变量、命令和路径外，所有成果物使用中文简体。
- 代码注释、文档、提示词、报告和日志默认使用中文简体。

## 项目说明

- 本仓库是 `code-change-check` Skill，根目录必须保留 `SKILL.md`。
- `scripts/` 放 Python 编排、版本状态、运行时和报告逻辑。
- `tools/java-analyzer/` 放内置 Spoon Java 分析器及分发 JAR。
- `references/` 放当前架构说明。
- `assets/` 放运行时清单、证据结构和规则。

## 验证命令

```bash
python -m unittest discover -s tests -p "test_*.py"
cd tools/java-analyzer && mvn test package
python scripts/code_change_check.py --project . --output code-change-check-output --scan-all --no-interactive
```
