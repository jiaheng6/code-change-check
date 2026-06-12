# Java 语义分析

Java 分析由两个层次组成：

- Spoon：使用 `NOCLASSPATH` 构建 AST，提取字段映射、值来源、方法调用、配置读取、HTTP 地址、数据库写入、guard、状态条件和路由。
- CodeGraph：构建调用图，补充调用者、被调方法、影响范围和受影响测试。

Spoon 是核心层。无法解析任何 Java 文件时审计状态为 `blocked`。CodeGraph 是辅助层，不可用时保留 Spoon 证据并将状态标记为 `partial`。

稳定证据标识由相对文件路径、所属方法、证据类型和语义槽位组成，不依赖行号。
