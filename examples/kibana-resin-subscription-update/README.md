# 通过 Kibana Webhook 更新 Resin 订阅地址

这个例子将 `4wuqBxeSn9uV` 命名为 `kibana-webhook-ingress`，通过
`POST /webhooks/kibana` 接收告警，校验公共输入后按 `workflow` 分流。当前实现
`resin.subscription-url.update` 分支：从告警正文提取第一个 HTTP/HTTPS URL，更新
指定 UUID 的**现有远程订阅**。正文没有 URL 时返回忽略结果，不向 Resin 发请求。

```text
POST /webhooks/kibana
  → Validate webhook envelope (jsTransform)
  → Route by workflow (switch)
      resin.subscription-url.update
        → Extract Resin subscription URL (jsTransform)
        → Has HTTP(S) URL (jsFilter)
            True  → resinSubscriptionUpdate → 返回 Resin 的订阅对象
            False → Ignore without update → { status: "ignored", reason: "no_http_url" }
      Default
        → Reject unsupported workflow → Failure
```

`resinSubscriptionUpdate` 通过 RuleGo 原生动态组件机制注册，节点类型名就是
`resinSubscriptionUpdate`。组件内部由校验转换和 `restApiCall` 两个节点组成，
无须编译 Go 插件。它的边界是“按 ID 更新一个 Resin 订阅”；告警格式、频道名、
URL 提取及无 URL 丢弃策略属于主链的订阅更新分支。

## 文件

| 文件 | 用途 |
| --- | --- |
| `resin-subscription-update.json` | 注册到动态组件管理的组件 DSL |
| `chain.json` | 公共入口与分流图；保留原规则链 ID，更新名称、HTTP 路径和入口节点 |
| `validate-webhook.js` | 公共输入校验与 JSON 标准化，不包含具体 workflow 选择规则 |
| `alert-to-update.js` | 订阅更新分支 JS：提取 URL 并生成 `{ id, body }` |
| `prepare-update.js` | 通用组件的输入校验与 HTTP 请求准备 |
| `build.mjs` | 将脚本和图配置生成到上述两个 JSON 文件 |
| `fixtures/alert.json` | 已渲染的告警输入样例，地址及令牌均为虚构值 |
| `kibana-body.json` | 可粘贴到 Kibana Webhook Action 的 Body 模板，需填写真实订阅 UUID |
| `chain_test.go` | 真实 RuleGo 引擎、动态组件、HTTP 入口与本地模拟 Resin 的集成测试 |

## Webhook 输入协议

命名从入口来源、目标系统和具体操作区分职责：

| 位置 | 名称或值 |
| --- | --- |
| Kibana connector | `rulego-webhook-prod`，同一环境内共用 |
| Kibana 当前告警规则 | 建议 `resin-subscription-url-update-fq521` |
| Kibana Action Body 的 `workflow` | `resin.subscription-url.update` |
| RuleGo 公共入口规则链 | `kibana-webhook-ingress` |
| RuleGo HTTP 路由 | `POST /webhooks/kibana` |
| RuleGo switch 条件及分支连线 | `resin.subscription-url.update` |
| RuleGo 提取节点 | `Extract Resin subscription URL` |

`resin` 限定目标系统，`subscription-url` 限定更新对象，`update` 表示操作。
频道标识 `fq521` 用于具体 Kibana 规则的显示名称；不同频道可使用相同 workflow，
通过 `payload.subscription_id` 选择目标订阅。未来抽成子链时可命名为
`resin-subscription-url-update`。Kibana connector 和 RuleGo 入口继续承担公共接入职责。

部署这次命名调整时，需同时更新 Kibana Body 和 RuleGo 分流配置；旧值
`subscription-url.update` 不再匹配，会进入默认拒绝分支。

公共字段使用 `workflow`，表示这条消息要执行的业务流程；当前值为
`resin.subscription-url.update`。它不是内部规则链 ID，目标订阅 UUID 由每条消息的
`payload.subscription_id` 提供。示例接受以下格式：

```json
{
  "schema_version": 1,
  "workflow": "resin.subscription-url.update",
  "rule_id": "example-rule-1",
  "rule_name": "resin-subscription-url-update-fq521",
  "alert_id": "example-alert-1",
  "timestamp": "2026-11-10T02:10:49+08:00",
  "payload": {
    "subscription_id": "12345678-1234-4234-8234-123456789abc",
    "sender_user_id": "7131987336",
    "message_content": "订阅 https://subscriptions.example.com/fq521",
    "sent_at": "2026-11-10T02:10:00+08:00"
  }
}
```

公共校验要求版本为数字 `1`、`payload` 为对象。`Route by workflow` 节点随后
选择分支；未知或缺失 `workflow` 进入默认拒绝分支，返回 Failure，不执行 URL
提取，也不调用 Resin。正文没有 URL 时忽略；有 URL 时将目标 ID 交给通用组件
做 UUID 校验。

公共格式校验通过后，入口将以下可选来源字段保存到 RuleGo metadata，供后续
节点关联 Kibana 规则与告警。业务转换将 `msg` 替换为 `{ id, body }` 后，这些
字段仍随 metadata 保留，直至更新成功、无 URL 忽略或 Resin 调用失败。

| Webhook 顶层字段 | RuleGo metadata 键 |
| --- | --- |
| `rule_id` | `kibana_rule_id` |
| `rule_name` | `kibana_rule_name` |
| `alert_id` | `kibana_alert_id` |
| `timestamp` | `kibana_timestamp` |

仅复制非空白字符串，并保留原始字符串值；缺失、空白或类型不符的可选字段跳过，
不影响业务处理。入口只写入以上已提供的追踪字段，其他已有 metadata 保持原样。
这些字段保存在链内 metadata 中，不添加到 Resin PATCH 请求体、请求头或 webhook
响应体，也不用于去重、排序或判断订阅是否已经刷新。入口不将整个 envelope 或
正文复制到 metadata；通用 Resin 组件继续只消费 `{ id, body }`。

`kibana-body.json` 使用重命名后的 ES|QL 列，配套查询为：

```esql
FROM budva-messages-* METADATA _id
| WHERE sender.user_id == 7131987336
    AND content.formatted_text.text RLIKE ".*https?://.*"
| SORT sent_at DESC
| LIMIT 1
| RENAME sender.user_id AS sender_user_id,
         content.formatted_text.text AS message_content
| KEEP _id, sent_at, sender_user_id, message_content
```

模板通过 `context.hits.0._source.message_content` 等字段取值，保持双大括号，
由 Kibana Webhook connector 完成 JSON 字符串转义。查询和模板需要一起调整。

## 在 Kibana 端抑制同一消息的重复通知

对于此 ES|QL 查询，配置为：

1. 告警生成方式选择 **Create an alert for each row**。
2. Action 选择 **For each alert**，频率选择 **On status changes**。
3. 只在 **Query matched** 时调用 webhook，不为恢复状态配置订阅更新 action。

当前 Kibana 实现对没有 `STATS ... BY` 分组的逐行查询，优先使用显式声明且保留
在输出中的元数据 `_id` 作为告警身份。因此查询同时需要 `METADATA _id` 和
`KEEP _id`；不要在最终输出中删除或重命名该字段。同一个文档连续命中时，属于
同一个持续 Active 的告警，不再触发状态变化 action；新文档有新的 `_id`，会
创建自己的告警并发送 webhook。单个“查询有结果”告警无法区分这两种情况。

`kibana-body.json` 无须因增加 `_id` 而改动。如果需要将文档标识加入请求用于
追踪，应取 `context.hits.0._source._id`。部署版本需支持上述逐行选项；可通过
查询预览中的告警 ID 验证身份是否对应文档 `_id`，再用真实 action 执行记录确认
同一消息连续两次检查只发送一次、新消息出现后再次发送。

这里保留 `LIMIT 1`，语义是处理每次检查时最新的一条匹配消息；两次检查之间出现
多条消息时，不保证每条都处理。相同 `_id` 的消息编辑在告警持续 Active 时不会
再次通知。此配置依靠告警生命周期抑制重复；已恢复的文档重新命中时可能再次发送，
不提供永久去重或严格的一次投递保证。当前 RuleGo 示例也没有持久化去重状态。

依据：[Elasticsearch query rule 文档](https://www.elastic.co/docs/explore-analyze/alerting/alerts/rule-type-es-query)
及 [Kibana ES|QL 告警身份实现](https://github.com/elastic/kibana/blob/main/x-pack/platform/plugins/shared/stack_alerts/common/es_query/esql_query_utils.ts)。
文档中的 **Exclude matches from previous run** 适用于 DSL/KQL/Lucene，不能作为
这里 ES|QL 查询的配置步骤。

## 可见的 workflow 分流

编辑器中选择 **Route by workflow**，在 `cases` 中维护入口允许的业务流程：

```json
{
  "cases": [
    {
      "case": "msg.workflow == \"resin.subscription-url.update\"",
      "then": "resin.subscription-url.update"
    }
  ]
}
```

`then` 对应画布上的连线类型。当前 `resin.subscription-url.update` 连到
**Extract Resin subscription URL**，`Default` 连到 **Reject unsupported workflow**。
使用原生 `switch` 的首个匹配语义，一次只选择一条分支。分流规则不再隐藏在
URL 提取脚本中，也不需要增加第二个 `preset` 请求字段。

当前分支直接画在入口链内。增加业务流程时，添加一项 case 和同名连线，连接
对应业务分支；若分支需要独立维护，可以将它抽成子链，用 `flow` 节点替代分支
入口。HTTP 路由和外部 `workflow` 标识不必改变。不要把外部传入的 workflow
直接当作任意子链 ID 调用；明确的分发表是入口支持流程的契约。

## 通用节点契约

节点配置只包含稳定的服务依赖：

```json
{
  "baseUrl": "${global.resin_base_url}",
  "adminToken": "${global.resin_admin_token}"
}
```

上游输出 `msg`：

```json
{
  "id": "12345678-1234-4234-8234-123456789abc",
  "body": {
    "url": "https://subscriptions.example.com/fq521?token=example-token"
  }
}
```

示例 UUID 必须换成真实值。节点校验标准 UUID 格式及非空对象 `body`，然后发送：

```http
PATCH <baseUrl>/api/v1/subscriptions/<id>
Authorization: Bearer <adminToken>
Content-Type: application/json

{"url":"https://subscriptions.example.com/fq521?token=example-token"}
```

只有 `body` 成为 HTTP 请求体；`id` 用于路径。节点不查询名称、不创建订阅、
不自动重试，也不额外调用 refresh。JSON 由 RuleGo 序列化，避免引号、换行、
反斜杠或 URL 参数被手工拼接破坏。

`body` 可以是 Resin 接受的其他 PATCH 字段组合，例如 `{"enabled":false}`，
或针对本地订阅的 `{"content":"..."}`。具体字段合法性及来源类型限制由 Resin
校验。此主链使用 `body.url`，所以目标必须是 `source_type=remote`；Resin 不允许
通过 PATCH 修改 `source_type`。

成功输出是 Resin 返回的订阅对象，`msgType` 和原有 metadata 保留。组件写入
`metadata.resin_subscription_id`、`metadata.resin_request_url`；HTTP 节点写入
`status`、`statusCode`，失败时还会写入 `errorBody`。令牌不放进消息或 metadata。

## 前置提取与丢弃

- 从 `payload.message_content` 按文本顺序提取第一个 `http://` 或 `https://` URL，
  协议名不区分大小写。多个链接时只更新一次；这项选择策略仅存在于前置节点。
- 保留 URL 的查询参数、百分号编码和 fragment。支持 Markdown 链接、尖括号、
  中文括号及常见句末标点；移除多余的闭括号，同时保留路径中的成对括号。
- 空、缺失、非字符串或没有 HTTP(S) URL 的 `payload.message_content` 都走过滤分支，
  HTTP 返回 `200` 和 `{"status":"ignored","reason":"no_http_url"}`，Resin 调用次数为零。
- 不请求提取出的链接，也不验证其内容是否为订阅；提取规则无法根据文本判断多个
  链接中哪个才是订阅地址。正文内若有宣传链接，应在这个节点调整选择规则。
- 原始文本 URL 若本身以英文 `. , ; !` 结尾，会按句末标点去除；有此需求时上游
  应提供百分号编码或调整提取规则。对 HTML 实体不做解码。

## 安装与配置

1. 在 RuleGo 的全局属性中设置：

   | 属性 | 值 |
   | --- | --- |
   | `resin_base_url` | RuleGo 所在环境可访问的 Resin HTTP(S) 服务地址，可包含反代路径前缀 |
   | `resin_admin_token` | Resin 管理令牌，通过部署配置提供 |

   订阅 UUID 填在 Kibana Body 的 `payload.subscription_id` 中，不再使用全局
   `resin_subscription_id`。旧的顶层 `message_content` 输入需要迁移到 `payload`。

2. 先注册 `resin-subscription-update.json` 为动态组件。管理 API 为
   `POST /api/v1/dynamic-components/resinSubscriptionUpdate`，请求体是整个文件。
   支持此入口的编辑器也可使用“组件管理 → 已安装 → 从 DSL 安装”粘贴完整 DSL。
   例如在 PowerShell 中，假定两个环境变量已配置为 RuleGo 管理地址及其令牌：

   ```powershell
   curl.exe --fail-with-body -X POST "$env:RULEGO_URL/api/v1/dynamic-components/resinSubscriptionUpdate" `
     -H "Authorization: Bearer $env:RULEGO_TOKEN" `
     -H 'Content-Type: application/json' `
     --data-binary '@resin-subscription-update.json'
   ```

   这里的 `RULEGO_TOKEN` 用于 RuleGo 管理 API，与 Resin 的管理令牌是两个配置。
   组件 ID 必须保持为 `resinSubscriptionUpdate`。

3. 再导入 `chain.json`，更新原来的 `4wuqBxeSn9uV` 规则链，并部署。链名改为
   `kibana-webhook-ingress`，入口先执行公共校验与分流；订阅分支的
   `resinSubscriptionUpdate` 配置引用上述全局属性。
   保留原来的共享 HTTP 服务 `ref://:9090`，该资源须已存在。

4. Kibana connector（建议名称 `rulego-webhook-prod`）的 URL 改为
   `https://<RuleGo 域名>/webhooks/kibana`，方法 `POST`，使用 `Content-Type: application/json`。
   上游告警模板必须先渲染为合法 JSON；正文中的引号和换行需要由发送方正确
   JSON 转义。`fixtures/alert.json` 展示渲染后的消息形状。

HTTP 路径由原 `/es-to-resin` 迁移到 `/webhooks/kibana`；导入新版规则链时需要
同步更新 connector。规则链 ID 不变，路由的目标起点改为 `node_validate`，
原 `node_5` 保留为分流后的 URL 提取节点。

原例的 `wait:false` 改为 `wait:true` 并增加 `responseToBody`，入口会等待 PATCH
返回。请求超时为 10 秒，入口写超时为 30 秒。示例默认关闭 debug/detail 日志。

Resin 正常 PATCH 返回 HTTP 200；接口拒绝、鉴权失败、目标不存在或网络错误走
节点的 `Failure`。当前 RuleGo `responseToBody` 将这些错误映射为入口 HTTP 400，
返回错误文本，而不是透传 Resin 的状态码。

**PATCH 成功只证明订阅配置更新被接受。** Resin 对 URL/content 变更异步执行
订阅更新；后续下载或解析可能失败。若要确认节点加载结果，应另行读取该订阅的
`last_checked`、`last_updated`、`last_error` 和节点信息。这个组件不把 PATCH 成功
解释为订阅已经可用。

## 验证与维护

在本目录执行：

```powershell
node build.mjs
go test ./... -count=1
```

测试固定使用 RuleGo v1.0.0，加载生成后的组件与主链，运行真实的 JS、动态组件、
过滤节点、HTTP 调用及入口响应处理器。Resin 端用本地 HTTP 测试服务模拟，覆盖
URL 提取、无 URL 不写入、UUID 校验、请求体及鉴权、通用字段透传、响应与失败传播。
同时验证工作流协议拒绝错误输入，以及同一规则链按消息中的不同 UUID 更新目标。
追踪回归测试验证成功、忽略和 Resin 调用失败时的来源 metadata 保留，以及可选
追踪字段缺失或类型不符时仍能处理消息；模拟 Resin 端确认 PATCH body 仍只包含
业务更新字段。
通过引擎执行轨迹确认先校验、再分流；未知 workflow 不进入提取分支。
HTTP 入口测试实际请求 `/webhooks/kibana`，覆盖成功、上游失败、无 URL 忽略和
未知 workflow 拒绝。
测试替换了部署专有的共享监听器，未连接线上 RuleGo 或 Resin，也未验证线上订阅
下载成功。

Resin 契约核对自相邻仓库提交 `c0aa422` 的
`internal/api/handler_subscription.go`、`internal/api/middleware.go` 及
`internal/service/control_plane_subscription.go`。动态组件注册机制及管理 API 核对
自 RuleGo 的 `engine/dynamic_node.go` 与 `server/docs/api-reference.md`。这些是
本例的验证依据，不代表任意部署的运行版本。
