# 业务契约

## 来源优先级

1. 用户显式指定的契约文件。
2. 从迭代前旧代码提取出的候选契约。
3. 完全没有历史版本能力时，才允许从当前已有代码提取候选契约。

契约文件和旧代码可以同时使用。用户确认候选契约时，应优先采用显式指定的契约文件；冲突自动识别属于后续能力。

## 旧代码 baseline

- Git 交互选择提交：使用最早选中提交的父提交。
- Git 版本范围：使用 `--base-ref`。
- Git 工作区改动：使用 `HEAD`。
- SVN 交互选择版本：使用最早选中 revision 的前一个版本。
- SVN 版本范围：使用范围起始 revision 的前一个版本。
- 目录快照：使用 `--baseline` 指定的旧目录。

只要 baseline 可用，就不能把本次新增代码当作旧契约。

## 当前提取类型

- 寻址：`internalBaseUrl`、`publicBaseUrl`。
- 调用形态：Client、Service、Helper、Adapter 调用的参数数量和参数表达式。
- 租户隔离：`tenantId`、`tenant_id`。
- 状态字段：`status`、`state`。
- 显式文本规则：必须、禁止、字段、格式、参数、顺序、兼容、签名、幂等等。

## 执行检查

已启用的 `business_contracts` 会和 target 语义清单对比，结果写入 `business_contract_check`，并将违反项转成 `业务契约` 风险命中。

首批可执行类型：

- `addressing`：旧代码或显式规则要求 `internalBaseUrl` 时，target 不能改成 `publicBaseUrl`。
- `call-shape`：旧代码的 `Client`、`Service`、`Helper`、`Adapter` 调用需要保留参数数量和已知参数线索，支持跨行调用。
- `tenant`：旧代码或显式规则中的租户字段线索需要在 target 中保留。
- `state`：旧代码或显式规则中的状态字段线索需要在 target 中保留。
- `text-rule`：目前只执行能解析为寻址、调用形态、租户字段或状态字段的文本规则，其余文本规则仍作为人工复核线索。
- `json-shape`：从 JSON 契约递归提取字段路径和稳定且唯一的 `label` 文案；只有提供同文件名的 `--response-snapshot` 时才执行实际响应形状与标签值对比。动态数值不做常量比较，避免误报。

契约执行结果必须区分：

- `total_contracts`：启用契约总数。
- `checked_contracts`：实际执行过自动检查的契约数。
- `unchecked_contracts`：缺少响应快照或无法解析为可执行结构的契约。
- `differences`：机器可读的期望、实际、缺失和新增项。

`unchecked_contracts` 不得解释为检查通过。JSON 契约没有匹配响应快照时，即使 `violations` 为 0，也只能说明尚未执行字段形状对比。

## 使用原则

- 自动提取结果只是候选契约，不是最终标准。
- 交互模式下必须让用户确认本次启用的候选契约。
- 没有选择的候选契约保留在 JSON 证据包中，但不作为本次审计标准。
- 规则引擎只消费 `business_contracts`，不直接消费全部候选契约。
- 契约执行结果是风险线索，不替代人工确认和回归测试。
