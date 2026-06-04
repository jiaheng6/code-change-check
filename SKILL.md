---
name: code-change-check
description: 用于检查 AI 或人工完成的代码变更质量，发现需求实现偏差、旧逻辑兼容问题、内部寻址错误、权限遗漏、状态流转错误、第三方对接风险、数据库写入风险和高风险调用，支持 Git、SVN、目录快照、OpenSpec、spec-kit、superpowers、Markdown 需求和任务列表。
---

# 代码变更检查

当用户要求检查代码变更、审计 AI 写出的代码、核对一次迭代质量、分析 Git/SVN/快照变化、检查需求是否落地、发现业务逻辑误解、内部寻址错误、权限遗漏、状态流转错误、第三方对接风险或旧逻辑兼容问题时，使用本技能。

## 工作流

1. 明确检查范围：确认项目根目录、需求/设计/任务文档位置、版本来源和用户特别关注的风险。
2. 收集变更证据：优先识别 Git，其次 SVN；没有版本管理时使用目录快照或全量扫描。
3. 收集需求证据：读取 OpenSpec、spec-kit、superpowers、Markdown 需求、任务列表和用户补充说明。
4. 运行 `scripts/code_change_check.py` 生成审计证据包和 Markdown 报告。
5. 基于报告继续人工推理，重点解释高风险位置，不要只复述扫描结果。
6. 输出结论时必须包含文件、行号、风险原因和建议验证方式。

## 推荐命令

在目标项目根目录运行：

```bash
python path/to/code-change-check/scripts/code_change_check.py --project . --output code-change-check-output
```

交互选择本次迭代包含的提交记录：

```bash
python path/to/code-change-check/scripts/code_change_check.py --project . --interactive --output code-change-check-output
```

交互模式支持方向键移动、空格多选、回车提交、`q` 取消。Git 会展示最近提交记录，SVN 会展示最近版本记录。可用 `--commit-limit 50` 调整展示数量。

如果项目中能发现需求、设计或任务文档，交互模式会继续让用户把每个提交关联到对应需求/任务。需要跳过时使用：

```bash
python path/to/code-change-check/scripts/code_change_check.py --project . --interactive --no-map-requirements --output code-change-check-output
```

指定需求文档：

```bash
python path/to/code-change-check/scripts/code_change_check.py --project . --spec docs/spec.md --spec tasks.md --output code-change-check-output
```

检查 Git 某个迭代范围：

```bash
python path/to/code-change-check/scripts/code_change_check.py --project . --base-ref main --target-ref HEAD --output code-change-check-output
```

检查 SVN 版本范围：

```bash
python path/to/code-change-check/scripts/code_change_check.py --project . --svn-revision 100:120 --output code-change-check-output
```

比较两个目录快照：

```bash
python path/to/code-change-check/scripts/code_change_check.py --project after --baseline before --output code-change-check-output
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

如果报告证据不足，明确说明缺少什么证据，而不是凭感觉判断安全。
