# 风险规则

## 默认高风险类型

- 寻址：`publicBaseUrl`、`externalBaseUrl`、公网 URL、硬编码域名。
- 服务调用：`fetch`、`axios`、`requests`、`HttpClient`、`RestTemplate`、`FeignClient`、`grpc`。
- 数据写入：`insert`、`update`、`delete`、`save`、`remove`、`bulkWrite`。
- 权限：`auth`、`permission`、`role`、`tenant`、`token`、`session`。
- 状态：`status`、`state`、`workflow`、`approve`、`cancel`、`refund`、`paid`。
- 计算：`amount`、`price`、`fee`、`balance`、`stock`、`quantity`。
- 第三方：`webhook`、`callback`、`signature`、`apiKey`、`retry`、`timeout`。
- 配置：`process.env`、`getenv`、`config`、`application.yml`、`dotenv`。
- 入口：`router`、`controller`、`middleware`、`endpoint`、`@RequestMapping`。

## 项目规则示例

内部寻址规则：

```text
后台任务、内部服务和同一集群内调用禁止使用 publicBaseUrl。
只有用户入口、公开 API、第三方 webhook 和外部回调可以使用 publicBaseUrl。
```

权限规则：

```text
新增接口必须经过既有鉴权中间件。
租户数据查询必须包含 tenantId 或等价隔离条件。
```

状态规则：

```text
订单、支付、退款、审批状态只能通过既有状态机或领域 service 修改。
不能在 controller 或脚本中直接改状态字段。
```

## 自定义 JSON 规则

可以通过 `--rules` 传入 JSON 文件：

```json
{
  "riskPatterns": [
    {
      "id": "internal-address-rule",
      "title": "内部调用疑似使用公网地址",
      "severity": "critical",
      "category": "寻址",
      "regex": "publicBaseUrl|PUBLIC_BASE_URL|https://api\\.example\\.com",
      "message": "内部调用必须核对是否应改用 internalBaseUrl。"
    }
  ]
}
```
