# 当前工作流程

1. 预检 Git/SVN 上下文并确定实际审查根目录。
2. 用户选择迭代范围：提交、revision、未提交改动或目录快照。
3. 收集需求、设计和任务材料。
4. 用户选择业务契约来源。
5. 物化 baseline 与 target。
6. Spoon 提取 Java 语义证据。
7. CodeGraph 提取调用链、影响范围和受影响测试。
8. 比较 baseline/target 证据并生成高置信风险。
9. 执行业务契约检查和覆盖质量闸门。
10. 生成 JSON 证据包和 HTML 报告。

核心 Java 分析失败时状态为 `blocked`。调用图、baseline 或部分文件解析不完整时状态至少为 `partial`。
