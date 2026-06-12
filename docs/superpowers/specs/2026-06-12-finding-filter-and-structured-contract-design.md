# 风险命中过滤与结构化契约设计

## 目标

降低全量扫描时由测试、文档、调试日志和 XML namespace 造成的噪声，同时保证所有原始证据仍可追溯；让业务契约报告明确区分已执行检查和无法执行检查，并支持 JSON 响应形状的精确差异。

## 风险命中过滤

文本正则扫描产生的命中先进入统一分类器。分类器根据文件路径和命中行判断其角色：

- `production`：生产代码和配置，保留为正式风险。
- `test`：测试目录、测试文件。
- `documentation`：Markdown、文本说明和文档目录。
- `debug`：调试日志和 debug 目录。
- `fixture`：fixture、mock、example、sample 等测试数据。
- `markup-namespace`：XML namespace、schemaLocation 等标准声明。

除 `production` 外，文本规则命中默认进入 `suppressed_findings`，并记录 `suppression_reason`。它们仍写入 JSON 证据包，并在 Markdown 报告中汇总。`--include-support-findings` 可把这些线索重新纳入正式风险。

业务契约、CodeQL 和 baseline/target 语义差异属于高置信证据，不参与文本噪声过滤。

## 结构化契约

契约执行结果增加以下字段：

- `total_contracts`：启用契约总数。
- `checked_contracts`：实际执行过的契约数。
- `unchecked_contracts`：无法自动执行的契约及原因。
- `violations`：确认存在差异的契约。

每个违反项包含结构化 `difference`，描述差异类型、期望值、实际值、缺失项和新增项。调用参数差异还要保留参数数量、参数列表和缺失必需参数。

JSON 契约文件提取为一个 `json-shape` 契约，字段路径使用点号和 `[]` 表示数组，例如 `data.list[].tenantId`。稳定且唯一的 `label` 文案也作为常量契约；动态数值不做常量比较。只有提供同文件名的 `--response-snapshot` 实际响应快照时，才执行字段形状比较：

- 缺失期望字段路径：`high`。
- 稳定 `label` 文案变化：`high`。
- 新增字段路径：仅记录在同一差异中，不单独判定风险。
- 没有匹配响应快照：进入 `unchecked_contracts`，不得算作检查通过。

## 数据流

1. 文本扫描生成原始 `Finding`，标记来源为 `text-rule`。
2. 分类器拆分为正式风险和已抑制线索。
3. 契约提取器从 Markdown/旧代码/JSON 中生成候选契约。
4. 契约执行器对可执行契约生成结构化差异，对不可执行契约生成未检查原因。
5. 正式风险与高置信契约、CodeQL、语义差异合并；抑制线索单独写入证据包和报告。

## 兼容性

- 保留现有 `findings` 和 `summary` 字段含义，它们只表示正式风险。
- 新增 `suppressed_findings` 和 `suppression_summary`。
- 未使用 `--response-snapshot` 时不影响现有命令执行，但 JSON 契约会明确显示为未检查。
- 审计计划必须锁定 `--include-support-findings` 和 `--response-snapshot`。

## 验证

- 测试目录、文档、debug 日志和 XML namespace 命中默认被抑制。
- 生产源代码同样的关键字仍作为正式风险。
- `--include-support-findings` 恢复全部文本规则命中。
- JSON 契约可提取稳定字段路径。
- 同名响应快照缺字段时生成结构化差异。
- 没有响应快照和无法解析的文本契约进入 `unchecked_contracts`。
