# IM→FF 契约解耦评估（mediaRunner 抽取 + 消费侧契约声明）

## Goal

判定 `rulego-indexed-media`（下称 IM）是否应当、以及如何把对
`rulego-ffmpeg-over-ip`（下称 FF）的**类型级 Go 依赖**换成**最小调用契约依赖**；
同时补齐舰队缺失的另一半——消费侧的机器可读对端契约声明与断言。
本任务的交付物是**决策与依据**，不是重构本身。

## Background / Current State（事实，逐条可核）

依赖面实测（IM 侧全部 4 个类型 + 1 个函数 + 1 个错误类型）：

| 符号 | IM 使用点 |
| --- | --- |
| `client.Run` | `source.go:65`（`runFn` 默认实现） |
| `client.Config` | `source.go:53`、`producer.go:110` |
| `client.Invocation` | `source.go:53`、`producer.go:114` |
| `client.OutputFunc` | `source.go:53`（IM 调用处传 `nil`，见 `producer.go:117`） |
| `client.Error` | `producer.go:281`（`errors.As`）后 switch `remote.Kind` |

关键事实：

1. **执行缝隙早已存在**：`source.go:53` 的 `runFn` 是函数类型字段，
   `source.go:65` 才填入 `ffmpegclient.Run`。IM 全部单测注入自己的 stub
   （`producer_test.go`、`producer_modes_test.go`、`track_modes_test.go`、
   `node_test.go`），因此单测从不触达分帧/HMAC。缺的不是可测性，是那四个
   参数类型仍来自 FF 模块。
2. **真实需要是协议版本，不是 Go 类型**：FF `client/protocol.go:15`
   `ProtocolVersion = uint8(0x06)`；FF `compatibility.json:5-9` 声明
   `ffmpegOverIp{version: "v5.2.1", revision: "ab7adfeed…", protocol: 6}`；
   FF `COMPATIBILITY.md` 末段以散文重申同一 wire contract。
3. **同包身份等式是文档化的刻意设计**：FF `COMPATIBILITY.md` 明写其入口模块对
   `…rulego-ffmpeg-over-ip v0.5.0` 的依赖"与对端刻意保持一致……这保留了共享
   客户端的单一包身份"，并称 CI 在 co-load 前比较编译期依赖记录。它防的是
   Go plugin loader 对"同包不同版本"的拒绝（FF `ci.yml:300` grep 的正是该错误
   原文）。这条不变式**真实**，本任务不否认它。
4. **叶子客户端没有独立版本节奏**：FF 内 `git diff --stat v0.5.0 HEAD -- client`
   为空（client 自 v0.5.0 起一行未改），而仓已发布至 0.5.2。契约变更条件
   （协议变）与发布变更条件（插件变）绑在同一个 `VERSION`。
   根模块只含 `client/`，插件入口是 `plugin/` 子模块并 require 根模块
   （`plugin/go.mod:6` 钉 `v0.5.0`，FF `ci.yml:34` 另以断言钉死）。
5. **消费侧声明缺失**：IM `compatibility.json` 只有 3 个字段，无任何
   peer/protocol 块；IM 无 `COMPATIBILITY.md`；IM `ci.yml` 无"编译进的客户端
   身份 == 我所声明"的断言。IM `README.md` 安装段只给
   `ffmpegAddress: ffmpeg-over-ip:15050`，无版本；但 IM 自己的 hermetic E2E
   按 digest 钉死 FF server 镜像（`tests/e2e-hls-seek.sh:7`，`:106` 启动）。
   即：**真正的跨仓契约（protocol 6 ↔ 该 server 镜像）在任何机器可读文件里不存在**。
6. **FF 不依赖 IM**：FF `go.mod` 仅 `github.com/rulego/rulego`；全仓 Go 代码
   零处提及 indexed。反向边只存在于 `.github/workflows/ci.yml`，见
   `../10-20-rulego-v1-upgrade/research/coexistence-ownership-first-principles.md`。

## In Scope

1. 冻结依赖面：枚举 IM 从 FF 消费的每个符号与语义（含 `Error.Kind` 的取值集合：
   `output_limit` / `canceled` / `transport` / `server` / `timeout`，
   见 `producer.go:289-298`），给出"若改为自有契约需搬运什么"的清单。
2. 比较四条路线（A1/A2/B/C，见下"候选路线"与
   `research/dependency-surface-and-routes.md`），产出带条件的推荐。
3. 定义消费侧契约声明的最小机器可读形状（IM `compatibility.json` 增加对端
   protocol/服务版本块）与对应 CI 断言，使声明可被证伪。
4. 判定 `ci.yml:236` 型跨二进制等式在三条路线下各自"是否仍存在 / 由谁证"。
5. 若推荐抽取，给出可分单的最小 PR 序列（不动发布闸门、不动共存断言）。

## Out of Scope

- 任何发布闸门/共存断言改动：FF/IM `ci.yml` 的 peer 下载与
  `rulego-ffmpeg-over-ip/.github/workflows/ci.yml:294` 的 `indexedVod` 断言
  归属，属 `10-20-rulego-v1-upgrade` 的 4.2 与另批批准，本任务不改。
- 规范文件落地（`rulego-capability-design.md` 的适配器判据、
  `rulego-plugin-delivery.md` 的消费侧证据项）：等本任务结论，先不写。
- FF 上游 ffmpeg 版本策略、协议本身的分帧/HMAC 设计变更。
- 读取/引用已废弃的 `rulego-indexed-vod` 仓作为事实源。

## Constraints

- 不新增 secret、不新增跨仓权限；现状跨仓读公开 release 已够用。
- IM 现有不变式不得削弱：有界 Range 读、单成员原子产出、3 次重试、
  `output_limit`/`canceled` 区分、产出失败即清理
  （`producer.go:110-138`、`:270-298`）。
- Go plugin 的"同包同版本"约束若仍成立，必须显式命名其载体，不得默认继承。
- 本任务为分析型：默认不向 IM/FF 仓提交代码；spike 若需要，在分支上跑且不发版。

## 候选路线

| 路线 | 形状 | 预期效果 |
| --- | --- | --- |
| A1 | IM 自带协议分帧实现 | 真正断开链接；但复制 FF 私有协议实现，被 ownership 规范禁止 |
| A2 | IM 自定义最小 `mediaRunner` 接口 + 自有错误分类，一个薄适配器文件仍包 FF 客户端 | 仅命名层解耦：链接、共享包身份、版本连带全部保留 |
| B | FF 发布独立契约模块（仅类型 + 协议版本常量，版本只在协议变更时推进），IM 依赖该模块 + 客户端 | 保留单一包身份，且契约有独立版本节奏 |
| C | 维持类型依赖，仅补消费侧声明与断言（IM `compatibility.json` + CI） | 成本最低；补上今天完全缺失的那一半 |

判定与逐路线六问已落 `research/dependency-surface-and-routes.md`：
**A1 否决、A2 近似空操作、推荐 C 并把 B 的触发条件写成可观测事件**。
该笔记同时更正了本会话早期的一处说法——解耦**不会**消除 `ci.yml:236`
那一族断言：三仓插件都 require `github.com/rulego/rulego v1.0.0`，
RuleGo 包集合始终共享，被消除的只是 FF 客户端这一个共享包实例。

## Acceptance Criteria（可机械证伪）

1. [x] 存在一份依赖面清单，逐符号给出 IM 使用点 file:line，且声明清单外无遗漏
    （核验法：IM 侧 grep `ffmpegclient` 的全部 30 行命中都被覆盖，
    见 `research/dependency-surface-and-routes.md` §1）。
2. [x] 四条路线各有一份取舍，且每条都回答同一组问题：同包身份等式是否仍存在、
    由谁证；协议变更时谁需要动；IM 单测是否仍需 import FF；跨仓发布顺序是否新增。
3. [x] 推荐结论带**失效条件**：笔记 §3 把翻案条件写成两个可观测事件（协议不变但
    FF 改动了 IM 消费的类型/错误字母；出现第二个客户端消费者）。
4. [x] 消费侧声明形状有样例 JSON 与对应断言草案（笔记 §3），并指出今天 IM
    `compatibility.json` 只有 3 字段、无对端块。
5. [x] 明确回答"`ci.yml:236` 在推荐路线下是否消失"（笔记 §4）：
    **不消失**——三仓插件共享 `github.com/rulego/rulego v1.0.0` 包集合，
    该族断言对整个 RuleGo 包集合继续成立；被消除的只是 FF 客户端这一个共享包实例。
    这与"该边为 CI 构造"结论不矛盾：那条讲的是 FF↔IM 的**源码依赖**不存在，
    本条讲的是 Go plugin 的**包身份**约束另有真实来源。
6. [x] 不适用（推荐 C，不需 PR 序列）；若日后转 B，再按本条补最小 PR 序列，
    且不含发布闸门改动。

## 事实 / 推断 / 待确认

- 事实：上表符号面、`source.go:53` 缝隙存在、client 自 v0.5.0 未变、
  IM 无消费侧声明、FF 无 IM 依赖。
- 推断：IM 只把 ffmpeg 用作容器重封装（`producer.go:98-114` 全为 `-c copy`
  / `-f mpegts`，无转码），故所需契约面可远小于当前依赖面。
- 待确认：上述"共享包集合"结论来自 `go.mod` pin 的静态推断，未在匹配运行时的
  两个 `.so` 上跑 `go version -m` 求交集确认（需 digest 钉定的 SDK，本机工具链
  不属匹配工具链）。它只影响"解耦收益有多大"，不影响否决 A1 与推荐 C 的结论。
- 另需确认：IM 生产代码从不触发 `OutputFunc`（`producer.go:117` 传 `nil`），
  这意味着 IM 声明的契约里可以不含输出回调面；若将来需要流式回传，契约面会扩大。

## Notes

- 上游讨论与判定链见 `../10-20-rulego-v1-upgrade/research/` 三份共存文档；
  本任务只解决"真边为什么合法、能否更小"，不重开共存归属。
- 状态：`planning`。`task.py start` 前需先由用户选定路线倾向，或确认要
  先补 `design.md` + `implement.md`。
