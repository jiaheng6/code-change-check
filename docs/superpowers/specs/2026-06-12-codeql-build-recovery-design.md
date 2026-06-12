# CodeQL 构建诊断与恢复设计

## 背景

真实 Maven Java 项目中，CodeQL database 创建曾因错误使用 `build-mode=none` 或 `autobuild` 无法完成项目编译而失败。旧流程只记录建库命令失败，没有说明 JDK、构建工具、依赖解析或编译状态，也不会在同一次审计中恢复。

## 目标

- Maven/Gradle Java 项目不得使用无法观察编译过程的 `none` 模式。
- 建库前记录 JDK 和构建工具状态。
- `autobuild` 失败后安全清理不完整 database，并使用确定性构建命令重试一次。
- 把每次尝试和最终失败原因写入证据包与 Markdown 报告。
- 尊重用户显式提供的构建命令，不擅自替换。

## 构建策略

- 用户传入 `--codeql-build-command`：使用该命令，失败后不自动替换。
- Maven/Gradle Java 且构建模式为 `none`：调整为 `autobuild`。
- Maven 单模块重试：`mvn -DskipTests compile`。
- Maven 多模块重试：从父 `pom.xml` 定位模块，使用 `-f`、`-pl`、`-am` 和 `-DskipTests compile`。
- Gradle 重试：使用 wrapper 或 `gradle` 执行 `classes -x test`，子模块使用对应模块任务。

## 恢复流程

1. 检测 CodeQL CLI、extractor、JDK 和 Maven/Gradle。
2. 根据语言、构建文件和用户参数生成构建策略。
3. 执行首次 database 创建。
4. 首次 `autobuild` 失败且存在 Java 构建系统时，清理不完整 database。
5. 使用检测出的构建命令重试一次。
6. 最终失败时再次清理不完整 database，并保留失败日志和分类。

## 失败分类

- `missing-jdk`
- `missing-build-tool`
- `dependency-resolution`
- `compilation-failed`
- `no-source-code`
- `build-failed`

## 非目标

- 不自动修复项目编译错误或依赖仓库配置。
- 不无限重试。
- 不替换用户显式指定的构建命令。
