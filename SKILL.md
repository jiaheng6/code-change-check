---
name: code-change-check
description: 用于检查 AI 或人工完成的代码变更质量，选择迭代提交范围，关联需求与提交，选择业务契约来源，从指定契约文件或迭代前旧代码提取候选契约，并结合可选 CodeQL 深度分析发现需求实现偏差、旧逻辑兼容问题、内部寻址错误、权限遗漏、状态流转错误、第三方对接风险、数据库写入风险和高风险调用，支持 Git、SVN、目录快照、OpenSpec、spec-kit、superpowers、Markdown 需求和任务列表。
---

# 代码变更检查

当用户要求检查代码变更、审计 AI 写出的代码、核对一次迭代质量、分析 Git/SVN/快照变化、检查需求是否落地、发现业务逻辑误解、内部寻址错误、权限遗漏、状态流转错误、第三方对接风险或旧逻辑兼容问题时，使用本技能。

## Claude Code 和无终端交互硬规则

在 Claude Code 中通过 `/code-change-check` 触发，或任何 shell 不支持 TTY 交互时，禁止直接执行审计命令。必须先预检项目上下文，并先在聊天里向用户确认检查范围、业务契约来源和是否启用 CodeQL，确认后再用显式参数和 `--no-interactive` 执行脚本。

预检命令：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --print-context
```

根据预检结果处理：

1. 如果检测到当前目录是 SVN 工作副本子目录，必须告诉用户当前目录和 SVN 工作副本根目录，询问审计当前子目录还是 SVN 工作副本根目录。默认建议使用 SVN 工作副本根目录，避免漏掉同次迭代里的前端、后端或兄弟目录改动。
2. 如果检测到当前目录是 Git 工作树子目录，也必须询问审计当前子目录还是 Git 工作树根目录。
3. 如果没有显式范围，必须询问本次迭代范围：选择哪些 Git 提交、哪些 SVN revision、工作副本未提交改动，或全量扫描。
4. 必须询问业务契约来源：指定契约文件、从迭代前旧代码提取、两者都用或不使用。
5. 必须区分期望契约和实际响应快照：契约 JSON 表示期望结构，`--response-snapshot` 只能使用接口真实运行后得到的实际响应。不得把同一文件或内容完全相同的复制文件同时作为期望契约和实际响应快照，否则会产生虚假通过。
6. 如果用户指定 JSON 响应契约，必须询问是否有同文件名的实际响应快照。没有快照时，必须把 JSON 契约报告为未检查，不能把“0 违反”解释为通过。
7. 如果选中的 OpenSpec、设计、任务或契约文档引用了 JSON 契约材料，必须检查审计计划中的 `missing_referenced_contract_artifacts`，询问用户是否纳入，不能静默忽略。
8. 必须询问是否启用 CodeQL；如果用户启用但本机未安装 CodeQL CLI，必须询问是否需要安装说明，不能把 CodeQL 缺失解释为检查通过。Maven/Gradle Java 项目不得显式选择 `--codeql-build-mode none`，应不传构建模式让工具自动判断，或显式使用 `autobuild`。

Claude Code、Cline 或其他无 TTY 环境确认完毕后，禁止直接执行最终审计。必须把用户选择编译成审计计划，展示计划内容，得到用户确认后再执行：

```bash
# 1. 生成计划，不执行审计
path/to/code-change-check/run-code-change-check.cmd --project selected-code-root --spec selected-spec-dir --strict-spec --contract selected-contract-dir --strict-contract --contract-source file --scan-all --codeql --no-interactive --output code-change-check-output --save-audit-plan code-change-check-audit-plan.json

# 2. 用户确认计划内容后，标记计划已确认
path/to/code-change-check/run-code-change-check.cmd --confirm-audit-plan code-change-check-audit-plan.json

# 3. 只通过已确认计划执行
path/to/code-change-check/run-code-change-check.cmd --audit-plan code-change-check-audit-plan.json
```

`--project` 必须使用用户实际选择的代码审计目录，不能因为当前 shell 位于父目录就继续传 `--project .`。用户只选择部分需求或契约时，必须使用 `--strict-spec` 或 `--strict-contract`，禁止重新自动发现未选择的文档。详细流程见 `references/audit-plan.md`。

生成审计计划后，必须读取并展示 `review_warnings`、`missing_referenced_contract_artifacts` 和 `input_role_issues`。存在 `critical` 或 `high` 预警时，先解释并修正输入，不能直接请求用户确认计划。

如果 `--print-context` 返回 `svn-incompatible`，禁止静默当作无版本控制目录继续。必须告知用户 SVN 客户端无法读取工作副本；只有用户明确选择目录快照时才追加 `--scan-all`，或提供 `--baseline`。

## 工作流

1. 明确检查范围：确认项目根目录、需求/设计/任务文档位置、版本来源和用户特别关注的风险。
2. 收集变更证据：优先识别 Git，其次 SVN；没有版本管理时使用目录快照或全量扫描。
3. 确认是否启用 CodeQL。启用后检测 CLI、语言和缓存，构造可靠的 baseline/target 源代码，分别创建或复用 database，并对比调用参数、寻址、租户字段和状态字段等业务语义线索。
4. 收集需求证据：读取 OpenSpec、spec-kit、superpowers、Markdown 需求、任务列表和用户补充说明。
5. 确认业务契约来源：使用指定契约文件、从迭代前旧代码提取、两者都用或不使用。
6. 让用户确认从旧代码和契约文件中提取出的候选契约，避免把历史坏代码直接当标准。
7. 执行业务契约检查：将已启用契约和 target 语义清单对比，覆盖寻址、调用参数、租户字段、状态字段；JSON 契约只有在提供同文件名的 `--response-snapshot` 时才执行字段路径对比。
8. 运行 `scripts/code_change_check.py` 生成审计证据包和 Markdown 报告。
9. 先检查审计覆盖质量闸门。状态为 `blocked` 时，禁止给出“可以合并”“未发现风险”或类似安全结论；状态为 `partial` 时，结论必须明确覆盖限制。
10. 对报告中的“必须人工核验的未检查契约”逐项核验：读取契约证据和候选实现位置，交叉检查字段、参数、寻址、状态和响应结构。不能因为自动规则无法执行就跳过。
11. 优先阅读与所选需求和契约相关的正式风险；测试、文档、调试日志、fixture、契约/响应 JSON 和 XML namespace 的文本正则命中默认只作为已抑制线索，除非用户明确要求 `--include-support-findings`。
12. 基于报告继续人工推理，重点解释高风险位置，不要只复述扫描结果。`--scan-all` 只表示全量扫描，不代表这些代码都属于本次迭代。
13. 输出结论时必须包含文件、行号、风险原因和建议验证方式。

## 推荐命令

在目标项目根目录运行：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --output code-change-check-output
```

根目录启动器在没有显式变动范围时默认进入交互向导；在真实终端直接运行 Python 脚本时，主脚本也会按同样规则自动进入交互。交互向导会询问变动范围、业务契约来源和是否启用 CodeQL。CI、管道或脚本自动化使用 `--no-interactive` 关闭交互。

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

非交互模式：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --no-interactive --output code-change-check-output
```

生成、确认和执行审计计划：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --scan-all --no-contract --no-codeql --no-interactive --save-audit-plan code-change-check-audit-plan.json
path/to/code-change-check/run-code-change-check.cmd --confirm-audit-plan code-change-check-audit-plan.json
path/to/code-change-check/run-code-change-check.cmd --audit-plan code-change-check-audit-plan.json
```

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

交互模式启用 CodeQL 但未检测到 CodeQL CLI 时，工具会询问是否查看安装方式，并给出 GitHub 官方 CodeQL CLI 安装文档链接。

指定业务契约文件：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --contract docs/contracts.md --contract-source file --output code-change-check-output
```

使用同名实际响应快照执行 JSON 字段路径对比：

```bash
path/to/code-change-check/run-code-change-check.cmd --project . --contract docs/contracts/safetyInspection.json --strict-contract --contract-source file --response-snapshot responses/safetyInspection.json --output code-change-check-output
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
7. 业务契约来源、候选契约、启用契约、契约执行结果和缺少契约的高风险位置。
8. CodeQL 是否启用、分析状态、语言、数据库缓存状态、SARIF 命中和业务语义差异。

## 最终解读质量闸门

最终高风险清单中的每一项必须同时具备：

1. 契约或需求证据：来自哪个需求、设计、任务、期望 JSON 或旧代码约定。
2. 代码证据：具体文件、行号和实际实现。
3. 偏差说明：期望与实际哪里不一致。
4. 业务影响：可能破坏哪个调用方、页面、数据或状态流程。
5. 验证方式：建议的测试、接口调用或数据对比。

只包含“可能无事务”“可能需要重试”等通用正则描述的项目，不能替代与所选需求直接相关的业务高风险清单。审计覆盖质量闸门为 `blocked` 时，必须人工核验报告列出的高优先级任务后再形成最终结论。

如果报告证据不足，明确说明缺少什么证据，而不是凭感觉判断安全。
