# 实施计划（路线 C：消费侧契约声明）

> 状态：待批准。**不改发布闸门、不改共存断言、不改 `release.yml`。**
> 改动全在 `rulego-indexed-media` 一个仓；本仓（文档仓）不动代码。
> 依据：`research/dependency-surface-and-routes.md` §3。

## 设计要点：声明与证据各一处，零重复 bump 点

对比 FF 现状（`rulego-ffmpeg-over-ip/.github/workflows/ci.yml:34` 用字面量
`v0.5.0` 断言 `plugin/go.mod`）——那是"字面量 + 等式"的重复 bump 点模式。
C 路线取更严格形状：

| 事实 | 唯一声明处 | 唯一证明处 |
| --- | --- | --- |
| 所需协议号 | `compatibility.json` 新增 `ffmpegOverIp.protocol` | Go 测试比对 `client.ProtocolVersion` 与该字段 |
| 编译进的客户端身份 | `go.mod` existing require | CI 比对 `.so` 内 `dep` 记录与 `go.mod` 声明 |

协议号是 `go.mod` 表达不出**意图**的那一格：它能钉住某个客户端版本，却不能说明
"IM 只依赖 protocol 6 这一事实"。FF 若为无关原因改版并把协议推到 7，go.mod 会变，
但 IM 的期望从未被写下，也就无从对照。所以只有协议号新增 JSON 字段；模块版本
不重复声明，避免第二处 bump。

## 步骤 1 — IM 声明所需协议（新增 1 字段 + 1 测试）

- [ ] **1.1** `compatibility.json` 增加：

```json
{
  "pluginVersion": "0.3.1",
  "pluginAbiRelease": "plugin-abi-release.json",
  "rulegoRelease": "v1.0.0",
  "ffmpegOverIp": { "protocol": 6 }
}
```

  加法式改动已核：IM `ci.yml:31-32` 与 `:138` 只按字段名取值，仓内**无**
  key 集合等式断言，`release-metadata` job（`:308`）整文件复制。
- [ ] **1.2** 新增 Go 测试（root package `main`，与 `node_test.go` 同包同目录）：
  读 `compatibility.json`，断言 `int(client.ProtocolVersion) == ffmpegOverIp.protocol`。
  这把"声明"钉在**编译进的常量**上，而不是手打数字：协议常量若变，声明即红。
  可行性依据：FF `client/protocol.go:15` 的 `ProtocolVersion` 是导出常量；
  IM 测试已运行于仓根目录。
- [ ] **1.3** 反向漂移保护（可选，建议同 PR）：同测试文件加一条
  断言客户端错误字母覆盖 IM 映射所需的 10 个 kind——今天 IM 只 switch
  `output_limit`/`canceled`/`transport|server|timeout`
  （`rulego-indexed-media/producer.go:289-298`），其余 kind 落 default。
  注意：FF 未导出 kind 常量表，跨仓枚举需 FF 侧先导出。**因此本条默认不做**，
  只在 `README.md` 记一句"未知 kind 一律按不可重试 production_failed 处理"。

## 步骤 2 — 证明编译进的依赖身份（CI，1 步）

- [ ] **2.1** 在 IM `build` job 的 `Verify embedded Go module identity`
  （现 `ci.yml:116-129`，已在产 `plugin/tmp/module-info.txt`）追加等式：

```bash
declared=$(awk '$1 == "github.com/killbus/rulego-ffmpeg-over-ip" { print $2 }' plugin/go.mod)
compiled=$(awk '$1 == "dep" && $2 == "github.com/killbus/rulego-ffmpeg-over-ip" { print $3 }' \
  plugin/tmp/module-info.txt)
test -n "$declared"
test "$compiled" = "$declared"
```

  路径注意：`build` job 的 checkout 带 `path: plugin`（IM `ci.yml:71`），
  所以该 job 内 go.mod 在 **`plugin/go.mod`**，与既有
  `plugin/plugin-abi-release.json`（`:81`）、`plugin/tmp/module-info.txt`
  （`:124`）同前缀；`test` job 无 `path:`（`:20-22`），那里才是仓根。

  两点形状照抄 FF 现成写法，避免自造：`go.mod` 的 require 在 **require 块**内
  （`go.mod:6` 是制表符缩进的 `<path> v0.5.0`，行首没有 `require` 关键字），
  所以按 `$1 == path { print $2 }` 取版本——FF `ci.yml:34` 正是这个 awk。
  `dep` 行取 `$3` 为版本（tab 分隔：`dep`、path、version、`h1:`），与 FF
  `ci.yml:229-231` 的 `client_identity()` 同形。
  断言"go.mod 声明 == 实际编进 `.so` 的版本"。同 job、同架构矩阵（amd64/arm64），
  **不需要任何兄弟下载**，因此顺序无关。build job 无宿主 Go，故用 awk 解析
  `go.mod` 而非 `go list`。
- [ ] **2.2** 不动 `e2e-hls-seek` job 的 peer 下载与 `ci.yml:228-231` 版本字面量
  （属 10-20 的共存归属议题，另批批准）。

## 步骤 3 — 文档（同 PR）

- [ ] **3.1** `README.md` 安装段补一句：所需对端协议号见 `compatibility.json`，
  并在同段说明未知错误 kind 的处置（见 1.3）。
- [ ] **3.2** 不新建 `COMPATIBILITY.md`：IM 现有 `README.md` + `compatibility.json`
  + `plugin-abi-release.json` 已覆盖，FF 那份 `COMPATIBILITY.md` 里含易变事实
  （旧 peer 版本），不作为模仿对象。

## 验证与门禁

- 本地快检：`go test ./...`、`jq . compatibility.json`、`bash -n`（无涉）。
- 权威验证走 CI：`test` + `build`（双架构）+ `e2e-hls-seek` + `release-metadata`。
- **新增失败模式（有意）**：FF 推进协议而 IM 未跟进 ⇒ IM CI 红。这是本改动的
  目的，但它是今天不存在的红，需在 PR 描述里显式声明。
- 审批门禁：本 PR 不新增 secret、不触 `release.yml`；但它**加强**了 IM 的
  `CI:success` 内容（多两条断言），任何通过 `CI:success` 间接读取的语义变化
  都须用户明示批准后方可合并。
- 回滚：单 commit revert；JSON 字段为加法式，revert 后无残留依赖。

## 与 10-20 任务的顺序约束

- IM PR #5 目前因共存 job 红而挂起（见
  `../10-20-rulego-v1-upgrade/implement.md` 3.6）。本改动**不合进 PR #5**：
  两事混提会让"闸门改动"与"声明补齐"互相遮蔽。
- 本 PR 不依赖死锁解除，可独立先行（只触 `test`/`build` job）。
- 若 10-20 先把 peer 下载移出成员闸门，本计划步骤 2 不受影响（它不下载兄弟产物）。

## 显式不做

- A1 自实现协议分帧（笔记已否决）。
- A2 纯改名重构（不等价于解耦，需要时另开可读性 PR）。
- B 独立契约模块：等笔记 §3 两条可观测触发之一成立再评估。
- 任何共存/发布闸门改动、任何 `compatibility.json` 破坏性重构。
