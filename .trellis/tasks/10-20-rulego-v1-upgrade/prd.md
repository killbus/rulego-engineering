# RuleGo v1.0.0 多仓升级

## Goal

把 RuleGo 生态从 v0.37.0 主机基线整体升级到上游 **RuleGo v1.0.0**（首个 1.0 大版本，
2026-10-19 发布），覆盖四个 killbus 仓的联动改动：

- `rulego-server-docker`（ABI 生产方）：以 v1.0.0 server 源码重签 `plugin-abi.lock`，
  产出并发布的新的 SDK/runtime 镜像（digest 化），标准/all 镜像流跟上 v1.0.0。
- 三个插件仓（`rulego-resource-origin`、`rulego-indexed-media`、`rulego-ffmpeg-over-ip`）：
  `go.mod` rulego pin 升到 v1.0.0、`plugin-abi-release.json` 换到新的 ABI 契约、
  版本号联动，CI 重建双架构 `.so` 并在匹配运行时做注册回读与共存验证。

升级后，部署在 v1.0.0 主机（`-plugin` runtime）上的三个插件仍能正常加载、注册、
被规则调用，且三插件在同进程共存；既有已部署规则链在 v1.0.0 引擎语义下行为被回读验证。

这是一个**跨仓、多交付物、强 ABI 契约**的复杂任务，必须 `prd.md` + `design.md` +
`implement.md` 齐备后才可 `task.py start`。

## Background / Current State（事实，见 research/）

- 上游 v1.0.0 已 tag（`45d1a6c`）并 publish 到 GitHub releases（2026-10-19）。
- 三插件当前编译基线 = rulego 伪版本 `v0.36.1-0.20260802040353-2ec085f29027`，
  `compatibility.json.rulegoRelease = v0.37.0`，共享同一 ABI 契约
  （`abi_id abi-d4fc741b…`，`packaging_revision = server-docker@a498c9e`）。
- 经逐 API 核验：三插件源码对 v1.0.0 **零 breaking**（未使用任何被删 API；
  `OnMsg`/`SharedNode.InitWithClose`/`GetSafely`/`endpoint.Exchange`/`processor.OutBuiltins`
  均不变）。插件 `.go` 文件预期无需改动，改的是依赖 pin 与 ABI sidecar。
- server-docker 的 plugin-ABI 流 host 必须从 v1.0.0 server **源码**用匹配工具链
  （CGO_ENABLED=1, buildmode=exe）重编译，不能复用上游 `CGO_ENABLED=0` 静态发布二进制。

## In Scope

1. `rulego-server-docker`：
   - 以 v1.0.0 server 源码重签 `plugin-abi.lock`（server revision + go.mod/go.sum sha256、
     core 版本/revision、module_graph、editor_payload v1.0.0 asset sha256、`abi_id`/
     `lock_digest`/`packaging_revision`、SDK/runtime 镜像 digest）。
   - 发布新 `rulego-plugin-sdk` + `rulego-server`（`-plugin`）镜像（digest 化，不可变 tag）。
   - 标准/all 镜像流（`publish.yml`）跟上 v1.0.0（验证 asset 命名/成员结构未变即可）。
   - 同步 tests 中 v0.37.0 版本断言（`plugin-abi-lock.sh` 等 6+ 文件）与 README 示例。
2. 三个插件仓：
   - `go.mod` rulego pin → v1.0.0（正式 tag）；`plugin-abi-release.json` 换新 ABI 四元组。
   - 版本号联动（`VERSION`/`compatibility.json`/`node.go`；ffmpeg-over-ip 多 client 依赖 +
     CI 硬编码 hash）。
   - `compatibility.json.rulegoRelease` → v1.0.0。
   - CI 重建双架构 `.so` + 匹配运行时 smoke-load + 共存验证。
   - ffmpeg-over-ip 的 co-existence peer 从旧 `indexed-vod v0.2.0`/`origin v0.1.1`
     改指升级后的 `indexed-media`/`resource-origin`。
3. 部署与运行时回读（在匹配 `-plugin` runtime 上）：三插件注册、最小规则调用、
   三插件同进程共存、既有规则链行为回读。
4. 发布产物/校验和/版本元数据回读（GitHub release assets + GHCR 镜像 digest）。
5. 更新 `rulego-engineering` 规范中过时的 ownership 指针（`rulego-indexed-vod` →
   `rulego-indexed-media`）——此项属 Phase 3.3 spec 更新，本 PRD 仅登记。

## Out of Scope

- **不得**改动或"顺手修复" `rulego-server-docker` 的未跟踪 WIP
  （`.agents/ .claude/ .codex/ .cursor/ .opencode/ .trellis/ AGENTS.md`
  `Dockerfile.all` `Dockerfile.slim` `scripts/detect-base.sh` `scripts/verify-image.sh`
  `.github/workflows/build.yaml`）。是否采纳 `build.yaml` 那套构建方案属 server-docker
  独立决策，列为延期项。
- **不得**读取/引用已迁移废弃的 `rulego-indexed-vod` 仓作为事实源。
- **不得**修改旧任务 `.trellis/tasks/09-11-indexed-audio`。
- 不改插件节点的业务逻辑/节点契约（本次是兼容升级，非功能开发）。
- 不改上游 `rulego` 仓（它是事实源，非本任务改动对象）。
- 不涉及部署到具体生产主机的凭据/路由/密钥（部署回读用既有部署机制）。
- 不在本任务内执行 `git push`/`release`/镜像 `push`——这些是实施期需用户逐项批准的
  对外动作（见 implement.md 的审批门禁）。

## Constraints

- 规划阶段（本阶段）**不实施产品代码**、不 `task.py start`、不安装/升级依赖、
  不做任何 git 写操作、不覆盖任何既有修改。
- 六仓既有未提交/未跟踪状态必须保护（详见 design.md §State Protection）。
- 插件 `.so` 的合法性由 ABI 契约四元组背书；host 与 plugin 必须同一工具链+依赖图编译。
- server-docker main 无 upstream tracking；插件 ffmpeg-over-ip 主分支是 master，
  且有分叉的 azure remote。

## Acceptance Criteria（可机械证伪）

> 每条给出可执行的核验命令/回读，"绿"必须来自真实执行，不得声称未运行的验证。

**A. server-docker ABI 重签**
1. [x] 新 `plugin-abi.lock` 中 `rulego_server.release_version == "v1.0.0"`，
   `rulego_core.version` 为 v1.0.0 对应的正式 tag，`go_mod_sha256`/`go_sum_sha256`
   与 v1.0.0 server 源码实际 `sha256sum` 一致（命令可复算）。
   由 `prepare-plugin-abi.sh:113-116` 在 `golang:1.25.0-bookworm` 内重算并断言通过。
2. [x] `plugin-abi.sh validate --candidate`（或等价 CI job `plugin-abi.yml`）全绿。
   实跑三轮 `pull_request`/`push` + 一轮 `validate --release`（run `39754464997`）。
3. [x] 新 `rulego-plugin-sdk` 与 `rulego-server`（`-plugin`）镜像在 GHCR 存在，
   `ghcr.io/killbus/...` 可 `docker pull`，`runtime` 镜像带
   `io.rulego.server.release == v1.0.0` label（`docker inspect` 回读）。
   回读通道替代：本机无 docker CLI，改用 GHCR 匿名 pull token + registry API
   直接读 tag 的 `Docker-Content-Digest`、index 子镜像与 config labels/annotations
   （比"本地 docker 看得见"更接近事实源）。见 `research/g3-abi-publish.md` §3。
4. [x] 标准/all 镜像流产出 `rulego-server:v1.0.0[-all]`，
   `fetch-release.sh` 成员校验（`config.conf`/`node_pool.json`/`editor/index.html`）通过。
   实测：cron run `39400807187` 两个 publish job 全绿；registry 回读
   `v1.0.0`=`sha256:ea0bf619…`、`v1.0.0-all`=`sha256:92a8a388…`＝`latest`/`latest-all`。
   注：标准/all 流不带 `io.rulego.abi.*`，ABI 身份只在 `-plugin` 变体上。

**B. 插件仓升级**
5. [x] 三仓 `go.mod` 的 `github.com/rulego/rulego` pin == `v1.0.0`（正式 tag），
   `go mod verify` 通过；`compatibility.json.rulegoRelease == "v1.0.0"`。
   实测三仓（RO `c7ae356`、IM `f3e64b7`、FF `cd3f446`）：根 + `plugin/` 全部
   `h1:2dMEtgsPPOfu34n8doTzu51tqp4kptGYp5DI07XRGTI=`，`go mod verify` = all modules verified。
6. [x] 三仓 `plugin-abi-release.json` 的 `abi_id`/`lock_digest` == server-docker 新
   `plugin-abi.lock` 的值（逐字节比对），`sdk`/`runtime` digest == 新发布的镜像。
   三仓五字段一致：`abi-3e0c9d46…` / `sha256:e19c9657…`（ready 态 lock 哈希，
   非签署态 `111ea6bb…`）/ `006436e3…` / runtime `sha256:53719b71…` / sdk `sha256:c5fadb57…`。
7. [~] 三仓版本号三/五处一致（CI 元数据校验 job 绿）：`VERSION`/`compatibility.json`/
   `node.go`( /producer.go)。RO `0.2.0`、IM `0.3.1` 的 `test` job 已在 CI 绿；
   FF `0.5.2` 仅本地核过，未 push（见 12 的死锁）。
8. [~] 三仓 `go test ./...` 与 `go test -race ./...` 绿（go 1.25 工具链）。
   三仓本地 `-count=1` 全绿；CI `test` job RO/IM 绿。`-race` 本机 `requires cgo`
   跑不了（PATH 无 gcc/clang），由 Linux CI 的 `-race` 覆盖。
   RO 本机存在与本任务无关的 Windows `TempDir RemoveAll cleanup` flake
   （base 全量跑同样随机红，失败集合每次变，零业务断言失败）。
9. [~] 三仓 CI build job 产出 `linux-{amd64,arm64}.so` + `.sha256` + `.abi.json`，
   `sha256sum --check` 通过，`.abi.json` 的 `abi_id`/`lock_digest`/`platform`/
   `plugin_sha256` 与 lock 一致。RO（run `39810333396`、main `39811100101`）与
   IM（PR #5 run `39813678234`）双架构 build job 已绿；FF 未跑。
10. [~] 每仓 smoke-load：在匹配 `-plugin` runtime 容器内，`/api/v1/components`
     回读到本仓节点（`resourceOrigin` / `indexedMedia` / `ffmpegOverIp`+`ffmpegOverIpProducer`）
     与 out 处理器（`resourceOriginResponse` / `ffmpegOverIpResponse`），日志无 ABI 错误。
     RO/IM 的 build job（含 `io.rulego.server.release == v1.0.0` 断言 + 容器回读）已绿；
     FF 未跑。
11. [ ] **共存验证**：同一 `-plugin` runtime 内同时加载三插件，`/api/v1/components`
     回读到全部 5 个节点类型 + 2 个处理器，无 package-identity 冲突（`go version -m`
     共享模块身份一致）。
12. [~] ffmpeg-over-ip CI 不再引用任何退役名 `indexed-vod` 的 peer 发布物，
      且其 build job 绿（成员证据：自身 sidecar + 自身注册 + 自身模块身份）。
      实现形态已变更（2026-10-24 批准，FF 本地 `ce9b2bf`，G4 未 push）：原
      "改 peer 坐标 + 改名 `ci.yml:294` + 文档"方案作废，改为成员闸门瘦身——
      peer 下载步与跨成员 shared-identity 步删除，smoke 改单插件自证；
      `COMPATIBILITY.md`/`README.md` 不再指向退役产物，改指 `rulego-fleet`。
      共存断言整体迁入 `killbus/rulego-fleet`（AC11 / `implement.md` 4.2）。
      原 FF⇄IM 互指死锁已结构性解除：FF 闸门不再下载任何兄弟发布物；剩余
      顺序依赖是单向的（IM 的 e2e（3.4）要指 FF 的 release → FF 先发）。
      见 `research/coexistence-release-deadlock.md`、
      `research/coexistence-gate-verdict.md`。

**C. 部署与运行时回读**
13. [ ] 在匹配 runtime 部署：新 `.so` 落位插件目录、进程按主机机制重启/重载、
    组件注册回读、最小规则调用（每插件一条最小输入→期望输出）通过。
14. [ ] 既有已部署规则链在 v1.0.0 语义下回读：节点类型/引用/endpoint/enabled 语义不变；
    含 join/group/flow 的链按 v1.0.0 新语义行为符合预期（或按新语义调整并记录）。

**D. 发布产物与元数据**
15. [~] 各插件 GitHub release 的 asset 带 `.sha256`，`sha256sum --check` 通过，
    release tag 与 `VERSION` 一致（`--verify-tag`）。RO v0.2.0 已回读核验
    （2026-10-24：tag→run head `c6731ac`、双架构 sha256 重算与 `.sha256` 文件
    及 sidecar `plugin_sha256` 一致、sidecar 五字段为新 ABI）；IM/FF 待各自
    G6 dispatch。
16. [ ] GHCR 上 `-plugin` runtime/sdk 镜像 digest 与 `plugin-abi-release.json` 记录一致
    （`docker manifest inspect` 回读）。

**E. 规范一致性**
17. [ ] `rulego-engineering` 的 ownership 指南中 `rulego-indexed-vod` 指针更新为
    `rulego-indexed-media`（Phase 3.3）。

## 事实 / 推断 / 待确认（区分）

**事实**（有 file:line 或命令输出证据，见 research/）：
- v1.0.0 已 tag+publish；`rulego.Version = "1.0.0"`；server `go 1.25.0`。
- 三插件对 v1.0.0 零 breaking API；共享同一 ABI 契约。
- 三插件 go.mod pin 为伪版本、与 compatibility.json v0.37.0 错位。
- server-docker ABI lock 全绑定 v0.37.0；host 需 CGO_ENABLED=1 源码重编译。
- ffmpeg-over-ip CI co-existence 仍引用旧 `indexed-vod v0.2.0`。

**推断**（合理但未直接证实，实施时验证）：
- 插件 `.go` 源码零改动即可完成升级（基于零 breaking 核验；以 `go build -buildmode=plugin`
  实际编译为准）。
- server-docker 标准/all 流对 v1.0.0 零改动（基于 `resolve-release.sh` 动态发现 + asset
  结构未变；以 `fetch-release.sh` 实跑为准）。
- 升级后既有规则链大多不需改（基于 v1.0.0 变化集中在新增能力；以回读为准，join/flow 语义
  重做的链是例外）。

**已批准的发布口径**：
- resource-origin 发布 `v0.2.0`，indexed-media 发布 `v0.3.1`，
  ffmpeg-over-ip 发布 `v0.5.2`。
- 三仓 RuleGo 依赖统一使用正式 tag `v1.0.0`。
- ffmpeg-over-ip client 源码不变，继续沿用 client `v0.5.0`。
- ffmpeg-over-ip 的共存测试从 indexed-vod 迁移到新版 indexed-media。
- server-docker 未跟踪 WIP 不纳入本次升级。
- go.mod pin 落正式 tag v1.0.0（建议）还是 pseudo-version。
- client 包是否发新版本。
- server-docker WIP 是否纳入（建议排除）。
- ffmpeg-over-ip azure remote 是否同步。
- 是否补 CHANGELOG。

## 与主会话的交接（规划完成时返回）

- 新任务路径：`.trellis/tasks/10-20-rulego-v1-upgrade`
- 创建/修改文件清单
- 关键事实证据（research/ 两文件）
- 推荐升级顺序（design.md §Upgrade Order）
- 风险与待确认事项
- 是否满足进入用户审批门禁（满足：prd/design/implement 齐备，planning 状态，未 start）
