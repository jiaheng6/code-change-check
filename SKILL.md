---
name: code-change-check
description: 用于检查 AI 或人工完成的代码变更质量，选择迭代提交范围，关联需求与提交，选择业务契约来源，从指定契约文件或迭代前旧代码提取候选契约，并结合可选 CodeQL 深度分析发现需求实现偏差、旧逻辑兼容问题、内部寻址错误、权限遗漏、状态流转错误、第三方对接风险、数据库写入风险和高风险调用，支持 Git、SVN、目录快照、OpenSpec、spec-kit、superpowers、Markdown 需求和任务列表。
---

# 代码变更检查

当用户要求检查代码变更、审计 AI 写出的代码、核对一次迭代质量、分析 Git/SVN/快照变化、检查需求是否落地、发现业务逻辑误解、内部寻址错误、权限遗漏、状态流转错误、第三方对接风险或旧逻辑兼容问题时，使用本技能。

## 工作流

1. 明确检查范围：确认项目根目录、需求/设计/任务文档位置、版本来源和用户特别关注的风险。
2. 收集变更证据：优先识别 Git，其次 SVN；没有版本管理时使用目录快照或全量扫描。
3. 确认是否启用 CodeQL。启用后检测 CLI、语言和缓存，构造可靠的 baseline/target 源代码，分别创建或复用 database，并对比调用参数、寻址、租户字段和状态字段等业务语义线索。
4. 收集需求证据：读取 OpenSpec、spec-kit、superpowers、Markdown 需求、任务列表和用户补充说明。
5. 确认业务契约来源：使用指定契约文件、从迭代前旧代码提取、两者都用或不使用。
6. 让用户确认从旧代码和契约文件中提取出的候选契约，避免把历史坏代码直接当标准。
7. 运行 `scripts/code_change_check.py` 生成审计证据包和 Markdown 报告。
8. 基于报告继续人工推理，重点解释高风险位置，不要只复述扫描结果。
9. 输出结论时必须包含文件、行号、风险原因和建议验证方式。

## 推荐命令

在目标项目根目录运行：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --output code-change-check-output
```

PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File path/to/code-change-check/run-code-change-check.ps1 --project . --output code-change-check-output
```

macOS/Linux：

```bash
sh path/to/code-change-check/run-code-change-check.sh --project . --output code-change-check-output
```

启动器会先检测可用的 Python 3.10+。Windows 会检测 `python` 和 `py -3`，macOS/Linux 会检测 `python3` 和 `python`；如果没有，会提示用户先安装 Python。

交互选择本次迭代包含的提交记录：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --interactive --output code-change-check-output
```

交互模式支持方向键移动、空格多选、回车提交、`q` 取消。Git 会展示最近提交记录，SVN 会展示最近版本记录。可用 `--commit-limit 50` 调整展示数量。

如果项目中能发现需求、设计或任务文档，交互模式会继续让用户把每个提交关联到对应需求/任务。需要跳过时使用：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --interactive --no-map-requirements --output code-change-check-output
```

交互模式还会让用户选择业务契约来源，并确认本次启用的候选契约。旧代码来源会优先扫描迭代前的 Git/SVN baseline，不会把本次新增代码当作旧标准。

交互模式会询问是否启用 CodeQL。非交互模式默认不启用，需要显式追加 `--codeql`：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --codeql --output code-change-check-output
```

要求 CodeQL 必须成功，否则返回非零状态：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --require-codeql --output code-change-check-output
```

CodeQL database 默认缓存到目标项目的 `.code-change-check/cache/codeql/`。默认尝试 baseline/target 对比；需要关闭时使用 `--no-codeql-compare`，要求对比必须成功时使用 `--require-codeql-compare`。启用 CodeQL 后，即使本地没有 CodeQL CLI，仍会运行轻量语义清单对比；CodeQL 可用时会用自定义查询补充调用清单。详细规则见 `references/codeql.md`。

指定业务契约文件：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --contract docs/contracts.md --contract-source file --output code-change-check-output
```

从迭代前旧代码提取候选契约：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --base-ref main --target-ref HEAD --contract-source existing-code --output code-change-check-output
```

同时使用契约文件和旧代码，并交互确认候选契约：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --contract docs/contracts.md --contract-source both --confirm-contracts --output code-change-check-output
```

指定需求文档：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --spec docs/spec.md --spec tasks.md --output code-change-check-output
```

检查 Git 某个迭代范围：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --base-ref main --target-ref HEAD --output code-change-check-output
```

检查 SVN 版本范围：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --svn-revision 100:120 --output code-change-check-output
```

比较两个目录快照：

```bash
path/to/code-change-check/run-code-change-check.cmd --project after --baseline before --output code-change-check-output
```

## 审查重点

- 需求有实现但没有测试。
- 代码有改动但找不到需求来源。
- 新增或修改 HTTP/RPC 调用。
- 内部服务调用误用外部地址。
- 新增数据库写入、删除或复杂查询。
- 权限、鉴权、角色、租户隔离逻辑变化。
- 金额、库存、订单、支付、退款、状态机变化。
- 绕过既有 service、client、helper、adapter。
- 第三方对接参数、回调、签名、重试、幂等逻辑变化。
- 共享工具函数、配置、环境变量、路由、中间件变化。

## 输出要求

最终回答使用中文简体，并优先给出：

1. 总体结论：是否建议合并/发布。
2. 高风险清单：按严重程度排序。
3. 人工优先阅读位置：文件和行号。
4. 需要补测或运行验证的路径。
5. 需求、设计、任务和代码之间的缺口。
6. 需求-提交映射，以及没有关联需求的提交、没有关联提交的需求。
7. 业务契约来源、候选契约、启用契约和缺少契约的高风险位置。
8. CodeQL 是否启用、分析状态、语言、数据库缓存状态、SARIF 命中和业务语义差异。

如果报告证据不足，明确说明缺少什么证据，而不是凭感觉判断安全。
