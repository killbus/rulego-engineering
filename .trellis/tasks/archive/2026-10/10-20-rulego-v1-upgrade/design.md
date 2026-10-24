# Design — RuleGo v1.0.0 多仓升级

## 1. 架构与边界

本次升级不改任何节点语义，只改**依赖契约链**上的版本坐标。契约链
（`rulego-plugin-delivery.md`）：

```
host source (rulego v1.0.0 server)
   → ABI lock (server-docker plugin-abi.lock, 重签)
   → immutable SDK/runtime 镜像 (rulego-plugin-sdk / rulego-server -plugin, 新 digest)
   → plugin artifact (.so, 用新 SDK 重建)
   → matching-runtime registration (smoke-load / 共存)
   → deployment installation (部署回读)
```

- **生产方** `rulego-server-docker`：独占 ABI lock 与 SDK/runtime 生产。
- **消费方** 三插件仓：消费契约，证明各自 artifact（sha256 + ABI sidecar + 注册回读）。
- **部署**：装新 artifact 到匹配 runtime，回读注册与行为。
- 每个仓保留自己的契约/测试/发布/提交历史；跨仓只通过**已发布坐标**（tag + digest +
  abi_id/lock_digest）耦合，不互相 import 私有实现。

## 2. 关键设计决策

### D1. 升级是"契约坐标平移"，不是源码迁移
三插件对 v1.0.0 零 breaking（核验证据见 research/rulego-core-v1.0.0-facts.md §5）。
因此每插件仓的改动面收敛为：
- `go.mod`：`require github.com/rulego/rulego v1.0.0`（正式 tag，消除现有伪版本错位）+ `go mod tidy` 更新 go.sum。
- `plugin-abi-release.json`：四元组（abi_id/lock_digest/packaging_revision/sdk/runtime）换为 server-docker 新契约值。
- 版本三/五处联动 + `compatibility.json.rulegoRelease = v1.0.0`。
- 源码 `.go`：**预期零改动**。若 `go build -buildmode=plugin` 编译出意外报错（不应发生），
  记录为 prd 缺陷回 Phase 1。

### D2. host 必须源码重编译（CGO 约束）
上游 v1.0.0 GitHub 发布二进制是 `CGO_ENABLED=0` 静态编译；而 ABI lock 要求
`cgo_enabled: true`、`host_mode: exe`、`plugin_mode: plugin`，且 Go plugin ABI 要求 host 与
plugin 由**同一 Go 工具链 + 同一依赖图**编译。故 server-docker 的 ABI 流必须：
- 拉 v1.0.0 server 源码（revision 锁到 v1.0.0 tag 的 server module）。
- 在 `golang:1.25.0-bookworm`（gcc/g++ 12.2.0, GNU ld 2.40, glibc≥2.34）内
  `CGO_ENABLED=1 go build -buildmode=exe -trimpath`。
- 产出 host 二进制 + 计算 go.mod/go.sum sha256 + module_graph hash + editor_payload。
- 由 `prepare-plugin-abi.sh` → `plugin-abi.sh validate --candidate` 重算 `abi_id`/`lock_digest`。

> 标准/all 镜像流（`publish.yml`）**不走这条路**——它直接用上游静态发布二进制
> （`fetch-release.sh`），两者独立，可并行。

### D3. 版本号方案（已批准）
插件仓**不跳 v1.0.0**，而是递增各自版本，理由：插件自身无语义变更，跟随 host 大版本
会污染插件的版本语义；RuleGo 侧已有独立的"兼容 v1.0.0 运行时"表达（compatibility.json）。
- `rulego-resource-origin`：0.1.3 → **0.2.0**（升 minor：换 ABI 基线是可部署面变更）
- `rulego-indexed-media`：0.3.0 → **0.3.1**（patch：仅换 host 基线，无自身变更）
- `rulego-ffmpeg-over-ip`：0.5.1 → **0.5.2**（patch；client 包若不改源码可沿用 v0.5.0 依赖）

该口径已由用户批准。VERSION/compatibility.json/node.go/tag 按上述版本联动；
RuleGo 依赖统一使用正式 tag `v1.0.0`。

### D4. client 包身份（ffmpeg-over-ip ↔ indexed-media）
`indexed-media/go.mod` 依赖 `killbus/rulego-ffmpeg-over-ip v0.5.0`（client 包）。ffmpeg-over-ip
CI 的"共享 client 模块身份"硬校验要求 co-existence peer 编译出的依赖记录逐字节相同。
- 若 ffmpeg-over-ip client 源码**不改**：沿用 `v0.5.0` client tag，indexed-media 的
  `rulego-ffmpeg-over-ip` 依赖保持 `v0.5.0`，两仓 CI 的共享 hash 断言不变。
- 若 client 源码**需改**：先发新 client tag（如 v0.5.2 根模块），indexed-media 升级该依赖，
  两仓 CI 硬编码 `h1:` hash 同步更新。
推荐**前者**（client 不改源码），降低跨仓耦合面。

### D5. co-existence peer 迁移（必改）
ffmpeg-over-ip `ci.yml:178-181` 现引用 `killbus/rulego-indexed-vod v0.2.0` +
`killbus/rulego-resource-origin v0.1.1`。新 ABI 下这两个旧 release 的
`abi_id`/`lock_digest` 与新契约不同，smoke 校验必失败。改为：
- `killbus/rulego-indexed-media <新版 tag>`（artifact 名 `indexed-media-rulego-v<ver>-...`）
- `killbus/rulego-resource-origin <新版 tag>`
同理由：indexed-media `ci.yml` 的 e2e peer（ffmpeg-over-ip + resource-origin）也需指向
升级后版本。**三仓 co-existence 必须同批升级、同 ABI**（这也是"三仓原子联升"的根因）。

### D6. 升级顺序（关键路径，见 prd/ABI research §4）
```
[0] 上游 v1.0.0 已就绪（无动作）
[1] server-docker ABI 重签 + 发布新 SDK/runtime 镜像   ← 门槛
[2] 三插件仓联升（可并行；indexed-media 依赖 ffmpeg-over-ip client 为唯一例外）
[3] 部署到匹配 runtime + 注册/行为回读
[4] 发布产物/校验和/GHCR digest 回读
```
[1] 未完成前，[2] 的 CI build 必失败（smoke-load 校验 release label）。

### D7. 不改 WIP、不碰废弃仓
- server-docker 的未跟踪 WIP（`build.yaml`/`Dockerfile.all|slim`/`detect-base.sh`/
  `verify-image.sh`/各 `.agents|.claude|...` 目录）**一律不碰**，不纳入本任务提交。
  它是否成为正式构建方案是 server-docker 的独立决策（延期项）。
- `rulego-indexed-vod` 只作为"要迁走的旧 peer 引用"被消除，**不作为事实源读取**。

## 3. 契约与数据流

### 3.1 ABI 契约字段映射（v0.37.0 → v1.0.0）
| 字段 | 旧值 | 新值来源 |
| --- | --- | --- |
| `rulego_server.release_version` | v0.37.0 | v1.0.0 |
| `rulego_server.revision` | a7be24c… | v1.0.0 tag 下 server module 的 commit |
| `rulego_server.go_mod_sha256` / `go_sum_sha256` | 66ed8ce…/420ec69… | `sha256sum` v1.0.0 server go.mod/go.sum |
| `rulego_core.version` / `.revision` | v0.36.1-0…2ec085f | v1.0.0 tag（`45d1a6c…`）|
| `module_graph.list_sha256`/`graph_sha256` | 0b3633b…/e339e96… | `go mod` 在 v1.0.0 依赖图重算 |
| `editor_payload.version`/`.asset.sha256` | v0.37.0 / c541c800… | v1.0.0 release `rulego-server-linux-amd64.tar.gz` |
| `abi_id` / `lock_digest` | abi-d4fc74… / sha256:5f9501… | `plugin-abi.sh` 重算 |
| `release.sdk_image` / `runtime_image` digest | be81ad63… / 8594e773… | 新发布镜像 digest |
| `packaging_revision`（插件侧 sidecar） | a498c9e…（server-docker HEAD） | 重签后的 server-docker HEAD |
| Go / 工具链 / glibc | 1.25.0 / gcc 12.2 / glibc≥2.34 | **预期不变**（除非 v1.0.0 server 提 go directive） |

> Go 1.25.0 / gcc / glibc 组合：v1.0.0 server 已 `go 1.25.0`，与现有 SDK base
> `golang:1.25.0-bookworm` 一致 → **工具链大概率不变**，主要变的是 rulego 源码坐标 +
> 依赖图 hash。以 `plugin-abi.sh validate` 实算为准。

### 3.2 插件 artifact 身份
每插件每架构产出：`.so` + `.so.sha256` + `.so.abi.json`（sidecar 含 abi_id/lock_digest/
platform/plugin_sha256）。三插件的 `plugin-abi-release.json` 保持**逐字节相同**
（同一 ABI 契约），由 server-docker 重签后统一下发。

## 4. 兼容性 / 回滚

- **配对回滚**：`.so` 与其 ABI 契约必须同版本。回滚 = 整组（新/旧 .so + 对应 -plugin
  runtime 镜像）回退，禁止新 .so + 旧 runtime（ABI 不匹配会加载失败）。
- **不可变镜像**：`-plugin` runtime/sdk 用 first-writer canonical tag + digest，旧镜像
  永久可回指。
- **规则链语义**：v1.0.0 重做 join/flow 语义 + ssh 认证字段合并（`certKeyFile`）。升级
  host 后，**含 join/group/flow/ssh 的已部署链**需按新语义回读验证，可能需调整链配置
  （这是规则侧改动，属部署回读步骤，非插件改动）。
- **editor**：v1.0.0 editor 为私有仓构建，server-docker ABI 流的 editor_payload 需重取
  v1.0.0 asset sha256；标准/all 流的 editor 由上游发布包带入。

## 5. 状态保护（不得破坏的既有状态）

| 仓 | 必须保护 |
| --- | --- |
| rulego-engineering | HEAD 138eee7（领先 origin 2）；`M .trellis/spec/guides/rulego-capability-design.md`；`?? .trellis/tasks/09-11-indexed-audio/research/indexed-vod-contract-review.md`；旧任务 `09-11-indexed-audio` 目录不动 |
| rulego-resource-origin | main@fc0d15a，与 origin 一致，工作树干净 |
| rulego-indexed-media | main@4f30239，与 origin 一致，工作树干净 |
| rulego-ffmpeg-over-ip | master@76e8c0e，与 origin/master 一致；azure remote 分叉不动 |
| rulego-server-docker | main@a498c9e（无 upstream）；**全部 11 项未跟踪 WIP 不动** |

本规划阶段（Phase 1）**零写**：不 commit/push/reset/rebase/clean/fetch，不安装依赖，
不构建，不改产品代码。上述仓在规划期保持原样。

## 6. 风险

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| 插件 `go build -buildmode=plugin` 意外编译失败（核验说零 breaking，但需实编译证实） | 中 | 以 CI 实际编译为准；失败即记 prd 缺陷回 Phase 1 |
| 三仓 co-existence 未同批升级 → 冒烟失败 | 高 | D5 强制同批；ci.yml peer 引用原子改 |
| ffmpeg-over-ip azure 分叉导致 release `--verify-tag` SHA 不一致 | 中 | 发布前确认以 origin 为准，必要时同步 azure（待确认项） |
| server-docker host 误用静态发布二进制（CGO_ENABLED=0）→ 与 plugin ABI 不匹配 | 高 | D2 明确源码重编译；verify-build.sh 断言 |
| v1.0.0 join/flow 语义变化破坏既有已部署链 | 中 | 部署回读步单独验证含 join/group/flow 的链 |
| 工具链/glibc 假设失效（v1.0.0 提高 go directive） | 低 | v1.0.0 server 仍 go 1.25.0，与 SDK base 一致；validate 实算 |
| 插件版本联动遗漏导致 tag、组件元数据或兼容声明不一致 | 中 | 按 D3 的已批准版本统一更新并由 CI/发布回读核对 |
| 规划期误碰 WIP/旧任务/废弃仓 | 中 | §5 状态保护 + 明确的 out-of-scope 清单 |

## 7. 延期项（本次不做，登记）

- server-docker `build.yaml`/`Dockerfile.all|slim` WIP 的采纳与否。
- 三插件仓补 CHANGELOG。
- ffmpeg-over-ip azure remote 策略。
- rulego-engineering ownership 指南 `indexed-vod → indexed-media` 指针更新（Phase 3.3）。
- 部署到具体生产主机的凭据/路由/密钥配置（部署回读用既有机制）。
