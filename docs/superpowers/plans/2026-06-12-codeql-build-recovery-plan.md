# CodeQL 构建诊断与恢复实施计划

**目标：** 让 Maven/Gradle Java 项目的 CodeQL database 创建具备环境诊断、错误构建模式修正、一次自动恢复和可追溯报告。

## Task 1：失败测试

- [x] 增加 Maven 多模块构建策略测试。
- [x] 增加 JDK/Maven 环境诊断测试。
- [x] 增加构建失败分类测试。
- [x] 增加 `autobuild` 失败后自动重试测试。
- [x] 增加 Markdown 报告诊断展示测试。

## Task 2：构建策略与恢复

- [x] 检测 Maven/Gradle 和 wrapper。
- [x] Maven/Gradle Java 的 `none` 自动调整为 `autobuild`。
- [x] 生成 Maven 单模块、多模块和 Gradle 重试命令。
- [x] 首次失败后清理不完整 database 并重试一次。
- [x] 最终失败后清理残留 database。

## Task 3：证据与报告

- [x] 记录构建环境、策略调整、每次尝试、恢复状态和失败分类。
- [x] 缓存元数据保留实际构建方式和诊断信息。
- [x] Markdown 报告增加“CodeQL 构建诊断与重试”。

## Task 4：文档与验证

- [x] 更新 Skill、CodeQL 参考、报告结构和中英文 README。
- [x] 运行完整单元测试、编译检查、Skill 校验和项目自检。
