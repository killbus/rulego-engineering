# Implement — RuleGo v1.0.0 多仓升级执行计划

> 执行仅在 `task.py start` 之后（status=in_progress）进行。
> 所有 git 写操作、push、release、镜像 push 均为**对外动作**，逐项列出审批门禁。
> 仓库路径简写：`[ENG]`=rulego-engineering，`[SD]`=rulego-server-docker，
> `[RO]`=rulego-resource-origin，`[IM]`=rulego-indexed-media，`[FF]`=rulego-ffmpeg-over-ip。

## 0. 前置检查（start 后、动手前）

- [ ] 复核六仓状态与 design.md §5 保护表一致（只读 `git status -sb` / `rev-parse HEAD`）：
  - `[ENG]` main@138eee7 ahead 2；`[RO]` main@fc0d15a；`[IM]` main@4f30239；
    `[FF]` master@76e8c0e；`[SD]` main@a498c9e + 11 项未跟踪 WIP。
- [ ] 复核上游 v1.0.0 release 资产可用（`gh api repos/rulego/rulego/releases/tags/v1.0.0`）。
- [x] **审批门禁 G1 已通过**：采用 design.md §D3 版本号方案；ffmpeg-over-ip client
  源码不变并继续沿用 `v0.5.0`；RuleGo 依赖统一使用正式 tag `v1.0.0`；
  co-existence peer 迁移到新版 indexed-media/resource-origin；server-docker 未跟踪 WIP 排除。

## 1. [SD] server-docker：ABI 重签（门槛步骤）

顺序执行，每步验证通过再进下一步：

- [x] **1.1** 拉取 v1.0.0 server 源码坐标：确认 v1.0.0 tag 下 `server/go.mod` 的
  go directive 仍为 1.25.0、无 `replace`（`git -C D:/Repositories/rulego show v1.0.0:server/go.mod`）。
  记录 `sha256sum server/go.mod server/go.sum`。
  实测：`go 1.25.0`；全部 `replace` 行均为注释状态（生效 replace 数 0）；
  `go_mod_sha256=e525b511…`/`go_sum_sha256=db5464f6…` 与 lock 一致（见
  `research/abi-byte-canonicalization.md`）。
- [x] **1.2** 取 v1.0.0 release `rulego-server-linux-amd64.tar.gz` 的 sha256
  （当前记录 `c1a73595…`，以实拉为准）→ 填入新 `editor_payload`。
  实测：GitHub release API 返回 `sha256:c1a735950e6572ac6dbc95f578458f8d6f5d5ad8ab3c433a531e8c55c7372650`
  （10613125 B），与 lock 的 `editor_payload.asset.sha256` 逐字符相同。
- [x] **1.3** 运行仓库自有 ABI 重签流程（**不手改 lock JSON 的 hash 字段**，全部由脚本重算）：
  `scripts/prepare-plugin-abi.sh`（输入 v1.0.0 server 坐标）→ 在
  `golang:1.25.0-bookworm` 内 `CGO_ENABLED=1 go build -buildmode=exe -trimpath` 重编 host
  → `plugin-abi.sh validate --candidate` 重算 `abi_id`/`lock_digest`/module_graph。
  - **派生值口径（实测教训）**：`abi_id`/`lock_digest` 是 `sha256(jq -S -c …)`，
    而 Windows 的 `jq -c` 会在每个输出行尾追加 `CR`；HEAD 提交态的 lock 是 LF-only，
    旧记录值（`abi-d4fc741b…` / `sha256:5f9501666…`）与**去 CR 后**的重算逐字节相同
    → 记录口径 = CI/Linux 字节口径。在 Windows 上按未规范化字节算出的
    `abi-1b36cb64…` 是错的，CI 会在 `plugin-abi.sh:128-130` 直接判红。
    本地重算必须 `| tr -d '\r'`；真正的修复是让 lock 与其派生 manifest 以 LF 落盘。
  - `prepare-plugin-abi.sh` 是**校验器不是生成器**：`plugin-abi-build.sh:10` 要求
    `GITHUB_ACTIONS=true`，`prepare-plugin-abi.sh:101` 断言 `GOVERSION==go1.25.0`
    （本机 go1.25.1/windows 必红）。所以本地只能把 candidate 备料算对，
    `abi_id`/`lock_digest`/module graph 的**权威值只能由 CI 产出**，本地值仅用于自证一致。
- [x] **1.4** 更新 `plugin-abi.lock`：`rulego_server.release_version=v1.0.0`、
  revision/go_mod_sha256/go_sum_sha256、`rulego_core` 坐标、`module_graph`、`editor_payload`
  **已写入并由 CI 复核通过**（PR #1 三 job 全绿）。
  口径说明：这些值不是本地"脚本产物"——`prepare-plugin-abi.sh` 是校验器
  （CI-only + 断言 `GOVERSION==go1.25.0`），本地只能按其同一套算法把 candidate 备料算对；
  权威值由 CI 回读确认，两者已逐字节相同（`research/ci-matrix-pr1.md` §1）。
  - 已实测复核（与 `git show v1.0.0:server/go.{mod,sum}` 及 resolver 产物一致）：
    `go_mod_sha256=e525b51161aed32d97e51e257efdea4c1f6ebba4b949ba58e0398588722ddff0`、
    `go_sum_sha256=db5464f62d5b2ae75a79544033912f7776c15267080171957ced4faa47595b32`、
    `list_sha256=47be6910…`、`graph_sha256=1ed5c015…`（两份产物 CR 计数为 0）、
    `editor_payload=c1a73595…`（v1.0.0 amd64 asset）。
  - 派生值已由 CI 确认（不再是"待复核"）：
    `abi_id=abi-3e0c9d46dddaf6235cfe609d543222f07f8e1abf3374f0669bf703df85063885`、
    `lock_digest=sha256:111ea6bbbce3d075752ff3639c77f9ca1cf129020ebf7da4f78482b095d775ef`
    （amd64/arm64 两份 native evidence 一致回读）。
- [x] **1.5** 同步 tests 版本断言。**仅改与 lock 绑定的文件**：
  `tests/plugin-abi-lock.sh`（v0.37.0→v1.0.0、`v0.37.0-plugin`→`v1.0.0-plugin`、
  revision/core 版本）、`tests/fetch-plugin-editor.sh`、`tests/plugin-image-contract.sh`
  （三者都 render/读取 lock 或断言 README 文本）。README 中 v0.37.0 示例文本同步。
  - **不改** `tests/resolve-release.sh`、`tests/fetch-release-{success,failure}.sh`、
    `tests/verify-published-failures.sh`：其中的 `v0.37.0` 是测试**自注入**的 mock fixture
    （喂给 `resolve-release.sh`/`fetch-release.sh` 再断言自己注入的值），与 ABI lock 无关。
    本任务曾把它列为必改项，属误判；改它只是无证据的文本 churn。
  - 标准/all 流的实际版本坐标来自 `plugin-abi.lock` 的 `editor_payload`，
    由 `publish.yml` 的 `resolve-release.sh` 动态解析，不需在测试里平移版本。
  - 顺带补一条缺失的负向断言：`rulego_core.version` 放宽为"正式 tag 或 revision 前缀
    伪版本"后没有对应负向用例，现加 `mutate_and_fail 'core version is neither a tag nor
    revision-prefixed'` 覆盖 `v1.0.0-rc1` 这类既不等同 tag、也不带 revision 前缀的值。
- [x] **1.6** 本地跑 `tests/run.sh` 全绿（ABI contract 测试）。
  实测 `RUN_SH_EXIT=0`（14 项全 pass，Windows + Git Bash + go1.25.1 + jq 1.7.1），
  证据见 `research/abi-byte-canonicalization.md` §4。
  - 注意：`tests/run.sh` **没有被任何 workflow 引用**（`.github/workflows/` 下 grep 不到），
    CI 只跑 `plugin-abi.sh render/validate` + `plugin-abi-build.sh`。本地这一跑是唯一一层
    契约单测证据，绿是提交前置条件，但不能据此声称"CI 已验证"。
- [x] **1.7** 提交拆成**两个各自可证的 commit**（分支 `plugin-abi-v1.0.0`，
  仅 7 个已跟踪文件；12 项未跟踪 WIP 全程保持未跟踪、未被 add）：
  - `54f01e4` *Keep derived ABI identities platform-stable* —
    `scripts/plugin-abi.sh` 的三处 `tr -d '\r'` + `tests/prepare-plugin-abi.sh` fixture 同步。
    **不含** core-version 放宽。在**旧 v0.37.0 lock** 下 `tests/run.sh` 全绿
    （`COMMIT_A_SUITE_EXIT=0`）→ 该 commit 独立自洽。
  - `568f6c9` *Re-sign the Plugin ABI contract for RuleGo v1.0.0* —
    lock + README + 三个契约测试 + core-version 放宽与负向断言。
  - 合并树与被改写的 `967cc33` **逐字节一致**（`git diff 967cc33 568f6c9` 为空），
    跟踪树干净、WIP 计数仍为 12。
  - **拆分方向的实测判决**（解释为何不是"测试+README 先"）：版本坐标与断言互相依赖，
    任何"lock 与测试分家"的方向都会红——旧 lock 渲染 `server=v0.37.0`，
    新测试断言 `== "v1.0.0"`；新 lock 渲染 `v1.0.0`，旧测试断言 `== "v0.37.0"`。
    真正可独立成立的切线是**关切**而非文件类型：字节口径修复（与版本无关）先行，
    版本重签（依赖前者）随后。`tests/plugin-image-contract.sh:96` 对 README 的断言
    只是这条线的一个约束，不是拆分不可能性的根因。
  - 更正一处早先误判：`tests/fetch-plugin-editor.sh` 的改动**不是**独立 bug 修复，
    它只是 mock 版本串随 lock 的 `editor_payload.version` 平移，属同一关切。
- [x] **审批门禁 G2 已完成（PR #1 全矩阵绿）**：
  push `[SD]` 功能分支 `plugin-abi-v1.0.0` → 开 PR → `plugin-abi.yml` 由
  `pull_request` 触发全矩阵（contract + amd64/arm64 native）。
  - `plugin-abi.yml` 的触发只有 `pull_request` 与 `push: branches:[main]`，**无**
    `workflow_dispatch`；不动 main 的唯一现成路径是 PR。
  - **红是可接受的产出**：PR 上红不发布任何东西（`plugin-abi-build.sh:24-27` 只在
    `PLUGIN_ABI_PUBLISH=true` 时才走 `validate --release`；registry 是 job 内本地
    registry），也不可能污染下游（canonical tag 首写不可变，`validate --release`
    过不去就产不出 release record）。红跑日志里
    `plugin-abi.sh:128-130` 的 `expected abi-<CI 口径>` 就是权威口径证据。
  - 迭代 commit 留在分支上；合并前按
    `.trellis/spec/guides/rulego-delivery-workflow.md` 的合并点纪律 fixup/squash
    成少数连贯 commit，再 merge main。
- [ ] **1.7b（`measurement` → `ready` 需要第二轮 CI，一轮做不到）**：
  第一轮的 lock 处于 `release.state=measurement` 且 size ceilings 为 `null`
  （`plugin-abi-build.sh:200` 只在 `release_state==ready` 时断言 ceiling，
  因此 measurement 轮会**收集** image size 而不因 null 失败）。
  取 PR 证据里的实测 size → 回填正值 ceilings + `state=ready` 为一个 coherent commit
  → PR 再跑绿 → 才允许 merge（`README.md` 的 release-ready 流程即此口径）。
- [ ] **审批门禁 G3**：**合并进 main 之后**在 main 上 dispatch
  `plugin-abi-publish.yml`（`publish=true` + `plugin-abi-release` environment 审批）
  发布新 `rulego-plugin-sdk` + `rulego-server`（`-plugin`）镜像，记录新 GHCR digest。
  - 为什么必须在合并后的 main 上：`plugin-abi-build.sh:58` 用
    `packaging_revision=${GITHUB_SHA}`，而插件仓 sidecar 的 `packaging_revision`
    必须指向 server-docker 的 **main commit**；PR merge-ref 的 SHA 不能进
    `plugin-abi-release.json`。
- [ ] **1.8** 回读：`docker manifest inspect` 两镜像存在且 digest 与 lock 一致；
  `docker run --rm <runtime> -c "echo ok"` 或 label 回读
  `io.rulego.server.release == v1.0.0`。
- [ ] **1.9**（并行可）标准/all 流：`publish.yml` dispatch（或等每日 cron）产出
  `rulego-server:v1.0.0[-all]`；`verify-published.sh` 绿。
  验证 `fetch-release.sh` 对 v1.0.0 包成员（`config.conf`/`node_pool.json`/`editor/index.html`）校验通过。

**回滚点 R1**：`plugin-abi.lock` 与 tests 的改动是独立 commit，可整体 revert；
旧 `-plugin` 镜像 tag/digest 不可变，永久可回指。

## 2. [FF] ffmpeg-over-ip：client 身份与 co-existence（插件侧先行者）

> 为什么 FF 先：IM 依赖 FF 的 client 包；FF 的 CI co-existence 又引用 RO/IM。
> FF 先行可先定 client 版本坐标，减少返工。

- [ ] **2.1** `go.mod` + `plugin/go.mod`：`require github.com/rulego/rulego v1.0.0`，
  `go mod tidy`（更新 go.sum）。client 源码**预期不改**（D4）。
- [ ] **2.2** 更新 `plugin-abi-release.json` 为 [SD] 新契约四元组
  （abi_id/lock_digest/packaging_revision=新 [SD] HEAD/sdk/runtime 新 digest）。
- [ ] **2.3** 版本联动（用户确认方案后）：`VERSION`、`compatibility.json`
  （`pluginVersion` + `rulegoRelease=v1.0.0`）、`plugin/node.go`、`plugin/producer.go`
  的 `Version:`；若发新 client 版本，同步 `plugin/go.mod` 依赖 + CI 硬编码 `h1:` hash。
- [ ] **2.4** 改 CI co-existence peer（`ci.yml:178-181` 一带）：
  `killbus/rulego-indexed-vod v0.2.0` → `killbus/rulego-indexed-media <新tag>`
  （artifact 名 `indexed-media-rulego-v<ver>-linux-{arch}.so`）；
  `resource-origin v0.1.1` → `resource-origin <新tag>`。
  **注意**：此步依赖 RO/IM 已按新 ABI 发布 release → 实际执行时序为
  FF 先改 go.mod/ABI sidecar 提交（2.1-2.3），co-existence 步（2.4）在 RO/IM 发版后补跑 CI。
- [ ] **2.5** 本地轻验证：`gofmt -l .`（空）、`go vet ./...`、`go test ./...`、
  `go test -race ./...`；`GOWORK=off go -C plugin vet/test/-race`。
- [ ] **2.6** 提交；**审批门禁 G4**：push `[FF]` master → CI `test` job 绿。
  （build job 因新 ABI 的 runtime 镜像与 peer release 就绪情况，可能在 3.x 后全绿。）

**回滚点 R2**：FF 改动为独立 commit，revert 即回到 v0.37.0 契约。

## 3. [RO] resource-origin / [IM] indexed-media（可并行）

每仓独立执行（两仓步骤对称，IM 多 client 依赖一项）：

- [ ] **3.1** `go.mod`：`require github.com/rulego/rulego v1.0.0` + `go mod tidy`。
  （IM 额外：确认 `rulego-ffmpeg-over-ip` 依赖版本按 D4 决策。）
- [ ] **3.2** `plugin-abi-release.json` 换新契约四元组（与 FF 同一份值，逐字节一致）。
- [ ] **3.3** 版本联动：`VERSION`、`compatibility.json`（+`rulegoRelease=v1.0.0`）、
  `node.go` 的 `Version:`。
- [ ] **3.4** IM 的 e2e peer 引用（`ci.yml` 下载 ffmpeg-over-ip/resource-origin 的步）
  指向升级后版本。
- [ ] **3.5** 本地轻验证：`gofmt -l .`、`go vet ./...`、`go test ./...`、
  `go test -race ./...`（IM 另 `python3 -m unittest discover -s tests/e2e -p 'test_*.py'`）。
- [ ] **3.6** 提交；**审批门禁 G5**：push `[RO]` main / `[IM]` main → CI `test` job 绿。
- [ ] **3.7** CI `build` job 全绿：双架构 `.so` + `.sha256` + `.abi.json` 产出；
  smoke-load 回读 `/api/v1/components` 含本仓节点/处理器、
  `io.rulego.server.release == v1.0.0` 校验通过。
  （依赖 [SD] 1.3/1.7 的新 runtime 镜像就绪。）

**回滚点 R3**：RO/IM 各自独立 commit revert。

## 4. 跨仓集成验证（匹配运行时）

- [ ] **4.1** 三仓 CI `build` job 全绿后，取得三组双架构 artifact（含 sidecar）。
- [ ] **4.2** **共存验证**（关键）：在 `rulego-server:v1.0.0-plugin` runtime 容器内
  同时安装三插件（`.so` 落 `/app/data/plugins` 或约定插件目录），重启，
  `GET /api/v1/components` 回读 5 个节点类型
  （`resourceOrigin`/`indexedMedia`/`ffmpegOverIp`/`ffmpegOverIpProducer`/…）
  + 2 个 out 处理器（`resourceOriginResponse`/`ffmpegOverIpResponse`），
  日志无 `plugin`/ABI 错误；`go version -m` 共享模块身份一致。
  （FF 的 CI 内置双/三加载冒烟已覆盖大半；本步是部署侧独立确认。）
- [ ] **4.3** **最小规则调用**：每插件一条最小输入→期望输出
  （如 resource-origin 发布一个资源并 GET 回读；indexed-media 对 fixture 源请求一段 range；
  ffmpeg-over-ip 起 pinned upstream 跑一次 invocation）。

## 5. 发布

- [ ] **审批门禁 G6**：三仓 `release.yml` dispatch（各仓：`ci_run_id` + `tag`，
  tag 与 `VERSION` 一致）。release 只发 CI 已验证 artifact（不重建），`--verify-tag`。
- [ ] **5.1** 发布后回读（`gh api`）：release 存在、asset 带 `.sha256`、
  `sha256sum --check` 通过、artifact 名含正确平台/版本。
- [ ] **5.2** GHCR 回读：`-plugin` runtime/sdk 镜像 digest 与 `plugin-abi-release.json`
  记录一致。

## 6. 部署与运行时回读

- [ ] **6.1** 目标部署装新 `.so`（校验和匹配 release 记录）、runtime 切
  `rulego-server:v1.0.0-plugin`（或按部署机制重启/重载）。
- [ ] **6.2** 注册回读：组件注册表含全部预期节点/处理器。
- [ ] **6.3** **既有规则链回读**（v1.0.0 语义）：经 API 读回全部已部署链，
  比对节点类型/引用/endpoint/enabled 语义；**重点**验证含 join/group/flow/ssh 的链
  （v1.0.0 join 语义重做、flow 跨链、ssh `certKeyFile` 字段合并）。
  行为异常 → 记录，按 v1.0.0 语义调整链配置（规则侧，非插件侧）。
- [ ] **6.4** 端到端最小验证：对既有对外路由发最小已知输入，检查状态/头/体/流。

## 7. 收尾

- [ ] **[ENG]** Phase 3.3 spec 更新：`rulego-ownership.md` 中
  `rulego-indexed-vod` 权威指针 → `rulego-indexed-media`；
  若发现新的稳定实践（如"插件 go.mod 必须 pin 正式 tag 以对齐 compatibility.json"）
  写入 `rulego-plugin-delivery.md`。
- [ ] **[ENG]** 本任务 research/ 补充实施期实测证据（ABI 重签日志、共存回读、发布 digest）。
- [ ] 按 Phase 3.4 提交（work commits 先行；排除非本任务脏文件：
  `[ENG]` 的 `rulego-capability-design.md` 改动与 `09-11-indexed-audio` 未跟踪文件
  **不属于本任务**，单独确认）。
- [ ] 提醒用户 `/trellis:finish-work`。

## 验证命令速查

| 目的 | 命令 |
| --- | --- |
| 仓状态 | `git -C <repo> status -sb && git -C <repo> rev-parse HEAD` |
| v1.0.0 release 资产 | `gh api repos/rulego/rulego/releases/tags/v1.0.0 --jq '.assets[]|{name,digest,size}'` |
| 插件元数据一致性 | 各仓 CI `test` job 首步（jq/grep 校验 VERSION/compatibility.json/node.go） |
| Go 验证 | `gofmt -l . && go vet ./... && go test ./... && go test -race ./...`（go 1.25） |
| ABI 校验 | `[SD]` `tests/run.sh`、`plugin-abi.sh validate`；插件仓 CI build job 的 sidecar 比对 |
| 运行时回读 | `docker run ... <rulego-server:v1.0.0-plugin>` + `curl -s localhost:9090/api/v1/components` |
| 镜像 digest | `docker manifest inspect ghcr.io/killbus/rulego-server:<tag>` |
| release 回读 | `gh api repos/killbus/<repo>/releases/tags/<tag> --jq '.assets[]|{name, size}'` + `sha256sum --check` |

## 审批门禁汇总（需用户逐项批准）

| 门禁 | 动作 | 时机 |
| --- | --- | --- |
| G1 | 版本号方案 + client 方案确认 | **已批准** |
| G2 | push `[SD]` 功能分支 + 开 PR（`pull_request` 触发 plugin-abi.yml；**不为触发 CI 直接 push main**） | 步骤 1.7 |
| G3 | 合并后的 main 上 dispatch `plugin-abi-publish.yml` 发布 SDK/runtime 镜像 | 步骤 1.8 前 |
| G4 | push `[FF]` master | 步骤 2.6 |
| G5 | push `[RO]` main / `[IM]` main | 步骤 3.6 |
| G6 | 三仓 `release.yml` dispatch 发布 | 步骤 5 |
| G7 | 部署变更（装 .so / 切 runtime / 重启） | 步骤 6 |

## 计划修改文件清单（按仓）

**[SD] rulego-server-docker（已跟踪；WIP 一律不动）**
- `plugin-abi.lock`（脚本重签）
- `tests/plugin-abi-lock.sh`、`tests/resolve-release.sh`、
  `tests/fetch-release-success.sh`、`tests/fetch-release-failure.sh`、
  `tests/fetch-plugin-editor.sh`、`tests/plugin-image-contract.sh`
- `README.md`（v0.37.0 示例 → v1.0.0）

**[RO] rulego-resource-origin**
- `go.mod`、`go.sum`、`VERSION`、`compatibility.json`、`plugin-abi-release.json`、`node.go`

**[IM] rulego-indexed-media**
- `go.mod`、`go.sum`、`VERSION`、`compatibility.json`、`plugin-abi-release.json`、`node.go`
- `.github/workflows/ci.yml`（e2e peer 引用升级后版本）

**[FF] rulego-ffmpeg-over-ip**
- `go.mod`、`go.sum`、`plugin/go.mod`、`plugin/go.sum`、`VERSION`、`compatibility.json`、
  `plugin-abi-release.json`、`plugin/node.go`、`plugin/producer.go`
- `.github/workflows/ci.yml`（co-existence peer：indexed-vod v0.2.0 → indexed-media <新>；
  resource-origin v0.1.1 → <新>；client 版本/h1 hash 若发新 client）

**[ENG] rulego-engineering**
- `.trellis/spec/guides/rulego-ownership.md`（indexed-vod → indexed-media 指针，Phase 3.3）
- `.trellis/spec/guides/rulego-plugin-delivery.md`（视实施期新实践，Phase 3.3）
- 本任务目录 `research/`、`prd.md`、`design.md`、`implement.md`、`*.jsonl`

## 显式不做

- 不读取/引用 `D:\Repositories\rulego-indexed-vod`（仅作为 ci.yml 中待消除的旧引用）。
- 不动 `[ENG]` 旧任务 `09-11-indexed-audio`、`M rulego-capability-design.md`、
  `?? 09-11-indexed-audio/research/indexed-vod-contract-review.md`。
- 不动 `[SD]` 全部未跟踪 WIP。
- 不改上游 `[rulego]` 仓。
- 规划阶段（现在）：零产品代码改动、零 git 写、零构建、零依赖安装。
