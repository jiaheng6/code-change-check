# CodeQL 深度分析

## 当前能力

- CodeQL 是可选分析引擎，不影响原有文本规则扫描。
- 交互模式会询问是否启用；非交互模式默认不启用。
- `--codeql` 启用分析，但 CodeQL 不可用时仍生成其余报告。
- `--require-codeql` 启用分析，并要求 CodeQL 完整成功，否则工具返回状态码 `3`。
- 自动检测项目语言和 CodeQL CLI 已安装的 extractor。
- 可靠构造 baseline/target 源代码，为每种语言创建独立 database，执行标准 code-scanning query suite。
- 将 SARIF 结果转换为统一风险项，并合并到 JSON 证据包和 Markdown 报告。
- Maven/Gradle Java、Kotlin、Go 或 Swift 默认使用 `autobuild`；没有构建文件的纯 Java、JavaScript/TypeScript、Python 等默认使用 `none`。
- Maven/Gradle Java 项目即使被错误指定为 `none`，也会调整为 `autobuild`，避免在没有观察编译过程的情况下创建无效 database。
- Java 建库前会检测 JDK 和 Maven/Gradle；`autobuild` 失败后会清理不完整 database，并使用检测出的 Maven/Gradle 编译命令自动重试一次。
- 审计目录是 SVN/Git 根目录、而 Java 工程位于 `backend/` 等子目录时，会继续向下发现嵌套 Maven/Gradle 构建根目录。
- 构建诊断、每次建库尝试、最终构建命令、恢复状态和失败分类都会写入证据包及 Markdown 报告。
- 将 CodeQL 命中分为新增、已有和已消失。只有两端分析都成功时才生成差异分类。
- 对 baseline/target 提取并比较业务语义清单，当前覆盖调用参数、内部/外部寻址、租户字段和状态字段。
- 轻量语义提取器作为降级基础；CodeQL 可用时，运行仓库内置自定义查询补充 Java/Kotlin 和 JavaScript/TypeScript 调用清单。

## 初始化时机

用户确认 Git、SVN 或目录快照范围后，工具立即确定是否启用 CodeQL。启用时解析 baseline/target 来源，通过临时 Git worktree 或目录快照得到两个代码状态，先提取轻量语义清单，再创建或复用 database。

支持的对比来源：

- Git 显式范围：比较 `--base-ref` 和 `--target-ref`。
- Git 连续选中提交：比较最早提交的父提交和最新选中提交。
- Git 工作区：比较 `HEAD` 和当前工作目录。
- 目录快照：比较 `--baseline` 和当前目录。

暂不可靠支持：

- 非连续或非线性的 Git 提交组合。
- SVN revision 源代码物化。

不支持可靠对比时，普通 `--codeql` 会降级为 target-only，并在报告中标记原因。能够确定目标 revision 时，target-only 仍分析该 revision，而不是无条件使用当前工作区。`--require-codeql-compare` 会返回失败状态。

退出状态：

- `3`：使用 `--require-codeql`，但 CodeQL 分析未成功。
- `4`：使用 `--require-codeql-compare`，但 baseline/target 对比未成功。

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
--no-codeql-compare
--require-codeql-compare
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

显式指定的 `--codeql-build-command` 优先级最高，工具不会替换该命令，也不会在失败后擅自改用其他命令。未指定命令时，Maven 项目自动重试命令为 `mvn -DskipTests compile`；多模块项目会增加 `-f`、`-pl` 和 `-am`。Gradle 项目会使用 `classes -x test` 或对应模块任务。

自动重试只执行一次。JDK 缺失、构建工具缺失、依赖解析失败、项目编译失败或构建过程未观察到源代码时，报告会保留对应失败分类，CodeQL 状态仍为失败，而不是把零命中解释为通过。

## 状态

- `disabled`：本次未启用 CodeQL。
- `unavailable`：未检测到 CodeQL CLI。
- `no-supported-language`：没有可分析的语言或 extractor。
- `success`：所有选中语言分析成功。
- `partial-failure`：部分语言成功，部分语言失败。
- `failed`：没有语言成功完成分析。

CodeQL 命中为零只代表已执行查询没有产生结果，不代表业务逻辑正确。

## 业务语义清单

业务语义清单位于 `codeql.comparison.semantic`，用于把需要逐行阅读才能发现的细微变化集中展示：

- `call-arguments-changed`：同一文件中的同名调用参数数量或参数线索变化。
- `addressing-changed`：已有内部寻址线索变为外部寻址，或反向变化。
- `tenant-field-removed`：目标代码不再包含 baseline 中已有的租户字段线索。
- `state-field-removed`：目标代码不再包含 baseline 中已有的状态字段线索。

轻量提取器支持多种常见源码后缀，但调用识别目前以单行点号调用为主。CodeQL 自定义查询当前位于：

```text
codeql/semantic/javascript-typescript/
codeql/semantic/java-kotlin/
```

CodeQL 自定义查询失败不会让标准 CodeQL SARIF 分析失败；报告会记录查询失败，并保留轻量语义清单作为降级结果。

## 对比状态

- `disabled`：用户关闭了 baseline/target 对比。
- `unsupported`：当前版本范围无法可靠构造对比。
- `success`：baseline 和 target 均分析成功，差异分类有效。
- `failed`：源代码物化或任一端 CodeQL 分析失败，差异分类为空。

## 后续阶段

1. 将用户确认的 `business_contracts` 转换为有限类型的 CodeQL 或 AST 可执行规则。
2. 扩展跨行调用、字段格式、数据流和上下游契约差异比较。
3. 实现 SVN revision 源代码物化。
4. 增加项目级自定义 query pack 和 CI 集成。

使用 CodeQL 分析私有仓库前，用户需要自行确认适用的 GitHub CodeQL 和 GitHub Code Security 许可条件。
