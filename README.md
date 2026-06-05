# code-change-check

[English](README.en.md) | 简体中文

`code-change-check` 是一个面向 AI 编程迭代的代码变更质量检查 Skill/CLI。

它不是普通的 `git diff` 阅读器，而是把一次迭代里的提交范围、需求文档、任务列表、业务契约、语义差异和可选 CodeQL 分析放到同一个审计流程里，帮助你更快发现“代码能跑、语法也对，但业务理解错了一小块”的问题。

典型问题包括：

- AI 把内部服务调用改成了外部地址。
- 第三方接口少传、错传或改了参数顺序。
- 新代码绕过了旧的 `Client`、`Service`、`Helper`、`Adapter` 约定。
- 租户字段、状态字段、权限线索在改动中丢失。
- 需求、设计、任务和实际提交对不上。
- CodeQL 命中无法区分新增问题、历史已有问题和已消失问题。

## 核心能力

- 支持 Git、SVN、目录快照和当前工作区扫描。
- 支持交互式选择一次迭代包含的提交记录，空格多选，回车提交。
- 支持 OpenSpec、spec-kit、superpowers、Markdown 需求、设计和 todo 文档。
- 支持需求和提交映射，暴露无需求来源的提交、无提交落地的需求。
- 支持从契约文件或迭代前旧代码提取候选业务契约。
- 支持业务契约执行检查，首批覆盖寻址、调用参数、租户字段和状态字段。
- 支持轻量语义清单对比，CodeQL 不可用时也能发现一部分业务语义变化。
- 支持可选 CodeQL baseline/target 对比，区分新增、已有和已消失的 CodeQL 命中。
- 输出 JSON 证据包和 Markdown 审计报告。
- 可作为 Claude Code、Codex、Cline 的 Skill/规则包使用。

## 适用场景

- 你使用 AI 写了大量代码，但不想逐行读完所有改动。
- 一次迭代包含多次提交，需要选择本次真正要审计的提交范围。
- 项目既有 Git，也可能有 SVN。
- 需求来自 OpenSpec、spec-kit、superpowers 或普通 Markdown。
- 业务里存在隐式规则，例如内部寻址、租户隔离、状态流转、第三方参数契约。
- 你希望把“旧代码里已有的调用形态”先提取成候选契约，再人工确认是否作为本次审计标准。

## 环境要求

- Python 3.10 或更高版本。
- Windows、macOS、Linux 均可运行。
- Git 或 SVN 可选；没有版本管理时可使用目录快照。
- CodeQL 可选；没有安装 CodeQL CLI 时，工具会提示并降级到非 CodeQL 检查。

启动器会检测 Python：

- Windows：检测 `python` 和 `py -3`。
- macOS/Linux：检测 `python3` 和 `python`。

如果本机没有可用的 Python 3.10+，启动器会给出中文提示。

## 安装方式

### 方式一：作为普通 CLI 使用

克隆仓库：

```bash
git clone https://github.com/jiaheng6/code-change-check.git
```

如果仓库仍是私有仓库，需要当前 GitHub 账号拥有访问权限。

进入仓库：

```bash
cd code-change-check
```

在要审计的目标项目中调用启动器。

Windows：

```cmd
path\to\code-change-check\run-code-change-check.cmd --project . --output code-change-check-output
```

PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File path\to\code-change-check\run-code-change-check.ps1 --project . --output code-change-check-output
```

macOS/Linux：

```bash
sh /path/to/code-change-check/run-code-change-check.sh --project . --output code-change-check-output
```

### 方式二：安装为 Codex Skill

将本仓库目录放到 Codex skills 目录，例如：

```text
~/.codex/skills/code-change-check/
```

目录根部必须保留 `SKILL.md`。

### 方式三：安装为 Claude Code Skill

将本仓库目录放到 Claude skills 目录，例如：

```text
~/.claude/skills/code-change-check/
```

### 方式四：接入 Cline

将规则文件复制到目标项目：

```text
<project>/.clinerules/code-change-check.md
```

来源文件：

```text
adapters/cline/code-change-check.md
```

## 快速开始

在目标项目根目录运行：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --output code-change-check-output
```

通过根目录启动器运行，或在真实终端直接运行 Python 脚本时，如果没有显式传入 `--base-ref`、`--svn-revision`、`--baseline` 或 `--scan-all` 等变动范围参数，默认会进入交互向导，依次选择变动范围、业务契约来源和是否启用 CodeQL。需要用于 CI、管道或脚本自动化时，追加 `--no-interactive`。

输出目录会生成：

```text
code-change-check-output/code-change-check-evidence.json
code-change-check-output/code-change-check-report.md
```

优先阅读 Markdown 报告；需要做二次分析或接入自动化时读取 JSON 证据包。

## 常用命令

### 交互式选择本次迭代提交

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --interactive --output code-change-check-output
```

交互模式支持：

- 方向键移动。
- 空格选择或取消。
- 回车提交。
- `q` 取消。

根目录的 `.cmd`、`.ps1`、`.sh` 启动器在没有显式变动范围时会自动追加 `--interactive`。如果你在真实终端直接运行 `python scripts/code_change_check.py`，主脚本也会按同样规则自动进入交互；非 TTY 环境不会自动交互。

### 非交互模式

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --no-interactive --output code-change-check-output
```

非交互模式适合 CI、脚本自动化或已有明确参数的检查。该模式不会询问变动范围、契约来源或是否启用 CodeQL。

### 指定 Git 迭代范围

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --base-ref main --target-ref HEAD --output code-change-check-output
```

### 指定 SVN 版本范围

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --svn-revision 100:120 --output code-change-check-output
```

### 比较两个目录快照

```bash
path/to/code-change-check/run-code-change-check.cmd --project after --baseline before --output code-change-check-output
```

### 指定需求或任务文档

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --spec docs/spec.md --spec tasks.md --output code-change-check-output
```

### 从契约文件执行业务契约检查

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --contract docs/contracts.md --contract-source file --output code-change-check-output
```

### 从迭代前旧代码提取候选契约

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --base-ref main --target-ref HEAD --contract-source existing-code --output code-change-check-output
```

### 同时使用契约文件和旧代码

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --contract docs/contracts.md --contract-source both --confirm-contracts --output code-change-check-output
```

### 启用 CodeQL

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --codeql --output code-change-check-output
```

要求 CodeQL 必须成功，否则返回非零状态：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --require-codeql --output code-change-check-output
```

要求 CodeQL baseline/target 对比必须成功：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --require-codeql-compare --output code-change-check-output
```

## 业务契约检查

业务契约有两个来源：

- 显式契约文件，例如 `docs/contracts.md`。
- 从迭代前旧代码中提取出的候选契约。

当前可执行的契约类型：

- `addressing`：检查 `internalBaseUrl`、`publicBaseUrl` 等寻址约定。
- `call-shape`：检查 `Client`、`Service`、`Helper`、`Adapter` 调用的参数数量和已知参数线索。
- `tenant`：检查 `tenantId`、`tenant_id` 等租户字段线索。
- `state`：检查 `status`、`state` 等状态字段线索。
- `text-rule`：对能解析为上述类型的文本规则执行检查，其余保留为人工复核线索。

旧代码提取出的契约只是候选标准。交互模式下建议人工确认后再启用，避免把历史坏代码固化为规则。

## CodeQL 分析

CodeQL 是可选能力。

启用后会尝试：

- 检测 CodeQL CLI 和可用语言。
- 构造 baseline/target 源代码。
- 创建或复用 CodeQL database。
- 执行标准 code-scanning query suite。
- 运行内置自定义语义查询。
- 将命中分为新增、已有和已消失。

如果没有安装 CodeQL CLI，工具不会把它解释为“通过”，而是在报告中明确标记 `unavailable`，并继续执行其他检查。

交互模式下，如果用户选择启用 CodeQL 但本地没有安装 CodeQL CLI，工具会提示是否查看安装方式，并给出官方安装文档链接。安装后请确认 `codeql version` 可执行，再重新运行检查。

## 报告重点

Markdown 报告包含：

- 总览和风险统计。
- 变更文件。
- 本次迭代提交记录。
- 需求-提交映射。
- 业务契约来源、启用契约和执行结果。
- CodeQL 状态和 baseline/target 对比。
- 业务语义差异。
- 人工优先阅读清单。
- 详细风险命中。
- 建议验证。

JSON 证据包包含完整结构化数据，适合继续交给 AI 或脚本做二次分析。

## 和普通 diff 工具的区别

`code-change-check` 的目标不是替代人工 review，而是降低人工 review 的入口成本。

它会把一次迭代中的高风险线索先集中出来，尤其是这些不容易从语法错误或运行报错中暴露的问题：

- 参数少传、漏传、顺序变化。
- 内部寻址和外部寻址混用。
- 旧调用约定被绕过。
- 租户隔离、状态字段、权限线索丢失。
- 需求、任务和提交无法对应。

最终结论仍需要结合业务知识、测试和人工判断。

## 开发验证

运行全量测试：

```bash
python -m unittest discover -s tests -p "test_*.py"
```

编译检查：

```bash
python -m py_compile scripts/code_change_check.py scripts/codeql_support.py scripts/codeql_comparison.py scripts/semantic_inventory.py scripts/codeql_semantic.py scripts/contract_rules.py
```

Skill 校验：

```bash
py -3 path\to\skill-creator\scripts\quick_validate.py path\to\code-change-check
```

## 关键词

AI code review、AI coding、code audit、static analysis、semantic diff、business contracts、CodeQL、OpenSpec、spec-kit、superpowers、Claude Code、Codex、Cline、Git、SVN。
