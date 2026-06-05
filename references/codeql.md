# CodeQL 深度分析

## 当前能力

- CodeQL 是可选分析引擎，不影响原有文本规则扫描。
- 交互模式会询问是否启用；非交互模式默认不启用。
- `--codeql` 启用分析，但 CodeQL 不可用时仍生成其余报告。
- `--require-codeql` 启用分析，并要求 CodeQL 完整成功，否则工具返回状态码 `3`。
- 自动检测项目语言和 CodeQL CLI 已安装的 extractor。
- 为每种语言创建独立 database，执行标准 code-scanning query suite。
- 将 SARIF 结果转换为统一风险项，并合并到 JSON 证据包和 Markdown 报告。
- Java-only、JavaScript/TypeScript、Python 等默认使用 `none`；检测到 Kotlin、Go 或 Swift 时默认使用 `autobuild`。

## 初始化时机

用户确认 Git、SVN 或目录快照范围后，工具立即确定是否启用 CodeQL。启用时先检测 CodeQL CLI，然后对项目当前工作目录创建或复用 target database。

当前阶段尚未为 Git/SVN 历史版本创建临时工作目录，因此 target database 的分析范围固定为：

```text
current-working-tree
```

选择历史提交只决定普通变更证据和旧代码契约 baseline，不会改变当前 CodeQL database 的源代码范围。报告必须明确展示该范围。

## 缓存

默认缓存目录：

```text
.code-change-check/cache/codeql/
```

缓存键包含：

- 支持语言源文件和依赖描述文件的内容摘要。
- CodeQL CLI 版本。
- 分析语言。
- 构建模式。
- 构建命令。

源代码、依赖文件、CodeQL 版本或构建配置变化时，会创建新的 database 缓存。

## 参数

```text
--codeql
--no-codeql
--require-codeql
--codeql-executable
--codeql-language
--codeql-build-mode
--codeql-build-command
--codeql-cache
```

`--codeql-language` 可重复传入，接受 `javascript`、`typescript`、`java`、`kotlin`、`cpp` 等常见别名。

示例：

```bash
run-code-change-check.cmd --project . --codeql --codeql-language javascript --output code-change-check-output
```

编译型项目可指定构建命令：

```bash
run-code-change-check.cmd --project . --codeql --codeql-language java --codeql-build-command "mvn -DskipTests package" --output code-change-check-output
```

## 状态

- `disabled`：本次未启用 CodeQL。
- `unavailable`：未检测到 CodeQL CLI。
- `no-supported-language`：没有可分析的语言或 extractor。
- `success`：所有选中语言分析成功。
- `partial-failure`：部分语言成功，部分语言失败。
- `failed`：没有语言成功完成分析。

CodeQL 命中为零只代表已执行查询没有产生结果，不代表业务逻辑正确。

## 后续阶段

1. 为 Git/SVN baseline 和 target 构造独立源代码目录及 database。
2. 执行 baseline/target 调用、参数、字段和数据流语义差异比较。
3. 将用户确认的 `business_contracts` 转换为有限类型的 CodeQL 或 AST 可执行规则。
4. 增加项目级自定义 query pack 和 CI 集成。

使用 CodeQL 分析私有仓库前，用户需要自行确认适用的 GitHub CodeQL 和 GitHub Code Security 许可条件。
