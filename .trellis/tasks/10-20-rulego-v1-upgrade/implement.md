# Implement — RuleGo v1.0.0 多仓升级执行计划

> 执行仅在 `task.py start` 之后（status=in_progress）进行。
> 所有 git 写操作、push、release、镜像 push 均为**对外动作**，逐项列出审批门禁。
> 仓库路径简写：`[ENG]`=rulego-engineering，`[SD]`=rulego-server-docker，
> `[RO]`=rulego-resource-origin，`[IM]`=rulego-indexed-media，`[FF]`=rulego-ffmpeg-over-ip。

## 0. 前置检查（start 后、动手前）

- [x] 复核六仓状态与 design.md §5 保护表一致（只读 `git status -sb` / `rev-parse HEAD`）：
  - `[ENG]` main@138eee7 ahead 2；`[RO]` main@fc0d15a；`[IM]` main@4f30239；
    `[FF]` master@76e8c0e；`[SD]` main@a498c9e + 11 项未跟踪 WIP。
- [x] 复核上游 v1.0.0 release 资产可用（`gh api repos/rulego/rulego/releases/tags/v1.0.0`，
  1.x 步实测资产 digest 并落档）。
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
- [x] **1.7b 已完成（`measurement` → `ready` 的第二轮 CI）**：
  第一轮 lock 处于 `release.state=measurement` 且 ceilings 为 `null`
  （`plugin-abi-build.sh:200` 只在 `release_state==ready` 时断言 ceiling）。
  `654b044` 回填 ceilings（**沿用旧已评审值**——全部实测值都在其中，最紧 89.4%，
  不重新"从被约束的那次运行反推闸门"）+ `state=ready`，仅动 `plugin-abi.lock` 一个文件。
  - run `39739872974`（`event=pull_request`，head `654b044`）三 job 全绿。
  - ready 态 `lock_digest` → `sha256:e19c9657ede2e9da86aae38c2ab972d32ff22aa2f2c8f1aa327714967baf8f80`，
    `abi_id` 不变（release 块不进 ABI 身份，但进 lock 哈希）→
    **插件侧 sidecar 记这个 ready 态 digest**。详见 `research/ci-matrix-pr1.md` §4。
  - `packaging_revision` 在 ready 轮仍是 merge ref SHA（`d2e12eaa…`），G3 必须在 main 上跑这一点复现。
- [x] **PR #1 已合并（用户批准 rebase）**：main `a498c9e` → `006436e`，
  三个逻辑 commit 线性落地（`7dae0a8`/`b1c20fe`/`006436e`），无 merge commit
  （与该仓历史 0 merge commit 一致）。碎片化判定：3 个 commit 各是一个连贯关切、
  闸门在中间 revision 也跑过，无需 fixup/squash（`rulego-delivery-workflow.md:66-70`）。
  合并后 main 自证轮 run `39752226819`（head `006436e`）**success**，
  `packaging_revision` 首次等于可引用的 main commit `006436e…`。
  - **新发现并登记的边界**：三轮验证矩阵的 `sdk`/`runtime` digest 都是 job 内
    `localhost:5000` 本地 registry 的（`staging_reference: null`），**不是 GHCR digest**。
    插件 sidecar 的 `runtime`/`sdk` 两字段只能取自 `plugin-abi-publish.yml` 的
    `plugin-abi-release-<sha>` artifact。详见 `research/ci-matrix-pr1.md` §6。
- [x] **审批门禁 G3 已完成（用户批准"发"）**：在 main `006436e` 上 dispatch
  `plugin-abi-publish.yml`（`publish=true`），run `39754464997` **success**（4 job 全绿）。
  - dispatch 前先 `git ls-remote origin refs/heads/main` 确认 main 仍是 `006436e`，
    避免 dispatch 到被移动的 ref。
  - `plugin-abi-release` environment 实测 `protection_rules: []`——**没有人工审批闸门**，
    因此"批准 dispatch"就是唯一的发布闸门，Agent 不得自行触发。
  - canonical tag 首写（不可逆）：`rulego-plugin-sdk:abi-3e0c9d46…` → `sha256:c5fadb57…`；
    `rulego-server:v1.0.0-plugin` → `sha256:53719b71…`。
  - GHCR digest **只**存在于本步的 `plugin-abi-release-<sha>` artifact；
    验证矩阵的 digest 是 job 内 `localhost:5000` 的（见 `ci-matrix-pr1.md` §6）。
  - 为什么必须在合并后的 main 上：`plugin-abi-build.sh:58` 用
    `packaging_revision=${GITHUB_SHA}`，而插件仓 sidecar 的 `packaging_revision`
    必须指向 server-docker 的 **main commit**；PR merge-ref 的 SHA 不能进
    `plugin-abi-release.json`。本轮实测 `packaging_revision=006436e…` 正确。
- [x] **1.8 已完成（换回读通道）**：本机**没有 docker CLI**，
  `docker manifest inspect` / `docker run` 不可用。改用 GHCR 匿名 pull token
  （`GET /token?scope=repository:killbus/<pkg>:pull`）+ registry API 回读，
  这比"本地 docker 看得见"更接近事实源：
  - 两个 canonical tag 的 `Docker-Content-Digest` 与 release record 逐字节相同；
  - runtime index 含 `linux/amd64` + `linux/arm64`（另 2 个 attestation）；
  - runtime child config labels：`io.rulego.server.release=v1.0.0`、
    `io.rulego.abi.lock.digest=sha256:e19c9657…`、`io.rulego.server.revision=45d1a6c4…`；
  - sdk index annotations：同组值 + `io.rulego.abi.platforms=linux/amd64,linux/arm64`；
  - 两处 `org.opencontainers.image.revision` 均为 `006436e…`。
  - 元数据位置不对称是设计而非缺陷：SDK 在 index annotations（复数 `platforms`）、
    runtime 在 child config labels（单数 `platform`）；`verify-plugin-oci.sh:53`
    正向断言 index 上不得出现单数 `platform`。
  - 本机 token 无 `read:packages` scope（`gh api users/killbus/packages/...` 403），
    匿名 pull token 是这台机器唯一的 registry 回读通道。
  - 详见 `research/g3-abi-publish.md`。**matching-runtime 插件加载仍在三仓 CI 里做**
    （步骤 2/3 的 `test` job），本机不补。
- [x] **1.9 已完成（实为合并前 2 天就已产出，本轮只做回读定位）**：
  GHCR 上 `rulego-server:v1.0.0` = `sha256:ea0bf619…`、`v1.0.0-all` = `sha256:92a8a388…`，
  且 `latest`/`latest-all` 的 digest 与之相同（移动别名已跟上）。
  - 真正执行发布的是 cron run `39400807187`（`2026-10-20T09:27Z`，head `a498c9e`）：
    `Publish standard image` + `Publish all image` 两个 job 都 success，
    即 `fetch-release.sh`（v1.0.0 包成员校验）与 `verify-published.sh`
    （版本 tag + 移动别名）当时就绿了。
  - 之后每天的 cron 都把 publish job **skipped**（幂等：tag 已存在），
    包括合并后 09:26 那次——所以"等 cron 产出"这条根本不需要等。
  - **重要区分**：标准/all 流**不受 ABI lock 约束**。`v1.0.0` 标准镜像的
    config labels 只有 `io.rulego.image.variant=standard`，**没有** `io.rulego.abi.*`，
    `org.opencontainers.image.revision` 是打包仓的 `a498c9e`（不是 `006436e`）——
    这是正确的：只有 `-plugin` 变体携带 ABI 身份。别把标准镜像的 revision 当作 ABI 证据。

**回滚点 R1**：`plugin-abi.lock` 与 tests 的改动是独立 commit，可整体 revert；
旧 `-plugin` 镜像 tag/digest 不可变，永久可回指。

## 2. [FF] ffmpeg-over-ip：client 身份与 co-existence（插件侧先行者）

> 为什么 FF 先：IM 依赖 FF 的 client 包；FF 的 CI co-existence 又引用 RO/IM。
> FF 先行可先定 client 版本坐标，减少返工。

- [x] **2.1 已完成**：根 `go.mod` 与 `plugin/go.mod` 均 `require github.com/rulego/rulego
  v1.0.0`（`go.sum`/`plugin/go.sum` 同步为 `h1:2dMEtgsPPOfu34n8doTzu51tqp4kptGYp5DI07XRGTI=`），
  `go mod verify` 通过。client 源码零改动（D4），client 模块身份仍 `v0.5.0`，
  CI 硬编码 `h1:4jeQQTATep8oP1BumDO/DftVAxlDz1SYzU6eA0xxfwU=` 不需改。
- [x] **2.2 已完成**：`plugin-abi-release.json`（本仓只有根目录一份，CI 里的
  `plugin/` 前缀来自 checkout `path: plugin`）换成发布态五字段
  `abi-3e0c9d46…` / `sha256:e19c9657…` / `packaging_revision=006436e3…` /
  runtime `sha256:53719b71…` / sdk `sha256:c5fadb57…`。
- [x] **2.3 已完成**：`VERSION`、`compatibility.json`（`pluginVersion=0.5.2` +
  `rulegoRelease=v1.0.0`）、`plugin/node.go`、`plugin/producer.go` 全部 0.5.1 → 0.5.2。
- [x] **2.4 已完成（形态变更，用户 2026-10-24 批准"直接落地"）**：四组
  "同批改名残留"方案**作废**，被成员闸门瘦身取代（FF commit `ce9b2bf`，本地，
  G4 未 push）：`ci.yml` 删除 peer 下载步与跨成员 shared-identity 步，smoke 改
  为单插件自证（`ffmpegOverIp`+`ffmpegOverIpProducer`+`ffmpegOverIpResponse`）；
  新增 `Verify own module identity` 步保留成员级 client 身份钉定。集合断言
  （三件共存 + 跨成员 shared-package）整体迁入 `killbus/rulego-fleet`（已
  push，`7524ffe`），由 4.2 承载。`ci.yml:294` 的 `indexedVod` 字符串随整步
  删除而消失（非改名迁移）；`COMPATIBILITY.md`/`README.md` 不再指向退役
  `indexed-vod` peer，改指 rulego-fleet，并收口 v0.37.0→v1.0.0。原四组方案的
  论证过程仍见 `research/coexistence-ownership-first-principles.md`（残留清单）
  与 `research/coexistence-gate-verdict.md`（R1 定案 + R2 圆桌 + fleet 命名裁定）。
  FF 闸门从此顺序无关：不再下载任何兄弟发布物。
- [x] **2.5 已完成**：`gofmt -l`（tracked `.go`，空）、根模块 `go vet ./...` +
  `go test -count=1 ./...`（`client` ok）、`GOWORK=off go -C plugin vet .` +
  `go -C plugin test -count=1 .`（ok）全绿。`go -C plugin list -m` 回读
  `ffmpeg-over-ip v0.5.0` + `rulego v1.0.0`。**`-race` 本机跑不了**（`requires cgo`，
  PATH 无 gcc/clang），由 CI 覆盖。
- [x] **2.6 已完成（G4 已批准并执行）**：分支 `feat/rulego-v1-abi-on-hardened`
  （自 `origin/master 90ce79c`）push 两个 commit（`cd3f446` 升级 +
  `ce9b2bf` 闸门瘦身），PR #2（CI 5/5 绿，run `40055027123`）→ 用户确认 →
  **rebase 合并**，`origin/master` = `956ed85`，master 自证轮 run
  `40055386317` **5/5 绿**（G6 的 `ci_run_id` 候选）。

> **步骤 2 阻塞已于 2026-10-24 结构性解除**：原死锁（FF/IM 成员闸门互指对方
> 已发布产物 + `release.yml` 要求整条 CI 全绿）的成因是集合断言放在成员闸门
> 里。成员闸门瘦身后（FF `ce9b2bf`，G4 未 push）FF 不再下载任何兄弟发布物，
> 顺序无关；剩余顺序依赖是单向的（IM 的 e2e 指 FF release → FF 先发）。
> 历史论证：`research/coexistence-release-deadlock.md`（死锁结构与解法）、
> `research/coexistence-gate-verdict.md`（R1 定案 + R2 圆桌 + fleet 命名与
> 职能裁定）、`research/coexistence-ownership-first-principles.md`（依赖边
> 第一性核验 + 成员/组成证据之分）。
> **G6 部分完成（RO）**：`v0.2.0` 已发布并回读核验（2026-10-24），见
> `research/coexistence-release-deadlock.md` "Executed" 节。

**回滚点 R2**：FF 改动为独立 commit，revert 即回到 v0.37.0 契约。

## 3. [RO] resource-origin / [IM] indexed-media（可并行）

每仓独立执行（两仓步骤对称，IM 多 client 依赖一项）：

- [x] **3.1 已完成（RO + IM）**：两仓 `go.mod` 均 `require github.com/rulego/rulego
  v1.0.0`（同一 `h1:2dMEtgsP…`）。IM 的 `rulego-ffmpeg-over-ip` 依赖按 D4 保持 `v0.5.0`。
- [x] **3.2 已完成（RO + IM）**：两份 `plugin-abi-release.json` 五字段与 FF 逐字节一致。
- [x] **3.3 已完成（RO + IM）**：RO `0.1.3 → 0.2.0`（`VERSION`/`compatibility.json`
  /`node.go`），IM `0.3.0 → 0.3.1`（同三处）；两仓 `rulegoRelease=v1.0.0`。
- [x] **3.4 已完成（IM）**：`ci.yml` e2e peer 下载改指升级后 release（FF
  `v0.5.1 → v0.5.2`、RO `v0.1.1 → v0.2.0`），commit `ec2a24b` 上 PR #5；
  死锁解除后该步侧车断言验到的正是新 ABI 值。
- [x] **3.5 已完成（RO + IM）**：两仓 `gofmt -l`（tracked `.go`，空）、`go vet .` 0、
  `go test -count=1 .` ok（IM 6.6s / RO 17.8s）。**RO 本机测试结果不可信为信号**：
  `testing.go:1369 TempDir RemoveAll cleanup: … catalog: The directory is not empty`
  在**未升级的 base 全量跑**里同样随机出现（base 两轮命中 3 个/1 个不同用例，
  升级分支两轮 0 个/1 个，失败集合每次不同、零业务断言失败）→ 判为 Windows 本机
  既有 flake，交给 Linux CI 权威判定；本任务不在升级 PR 里顺手改无关测试。
  另注意：cached 结果会掩盖该现象，一律 `-count=1`。
- [x] **3.6 已完成（RO）**：走 PR 而非直接 push main（合并点纪律）。
  `rulego-resource-origin` PR #4（head `c7ae356`）CI run `39810333396` 四 job 全绿
  （test / build amd64 / build arm64 / release-metadata）→ 用户批准 → **rebase 合并**，
  main `01c2b23` → `c6731ac`，head 自证轮 run `39811100101` **success**。
- [x] **3.6 已完成（IM）**：走 PR 而非直接 push main（合并点纪律）。PR #5
  （head `f3e64b7`）首轮仅 `Hermetic selected-track TS and HLS seek` 的 peer
  下载红（peer 仍是旧 ABI，属 3.4 未做 + Step 2 死锁）；3.4 修复后 head
  `ec2a24b` CI **5/5 全绿**（run `40057506621`）→ 用户批准 → **rebase 合并**，
  main = `d6786a5`，main 自证轮 run `40058007544` **5/5 绿**。
- [x] **3.7 已完成（RO）**：PR 轮与 main 自证轮均产出双架构 `.so`/`.sha256`/`.abi.json`，
  `sha256sum --check` 与 sidecar 比对通过，`io.rulego.server.release == v1.0.0`
  断言（`ci.yml:118`）随 build job 一起绿。IM 的 build job 同样已绿。

**回滚点 R3**：RO/IM 各自独立 commit revert。

## 4. 跨仓集成验证（匹配运行时）

- [x] **4.1 已完成**：三仓 CI `build` job 全绿并各自发布（RO v0.2.0 / IM
  v0.3.1 / FF v0.5.2），双架构 artifact 经 5.1 回读（sha256 重算 = `.sha256`
  = sidecar `plugin_sha256`）。形态说明：fleet 载体取**已发布 release** 而非
  CI artifact（全 release 版 = 出货字节本身，覆盖更强；CI artifact 与 release
  asset 字节同源——release 只发 CI 已验证 artifact，不重建）。
- [x] **4.2 已完成（载体 = rulego-fleet）**：`killbus/rulego-fleet` run
  `40083866855`（2026-10-24，main `e3c498d`）**双架构 success**。在钉死 runtime
  （`ghcr.io/killbus/rulego-server@sha256:53719b71…`，
  `io.rulego.server.release=v1.0.0`）内装入三件已发布 `.so`，
  `GET /api/v1/components` 回读 4 个节点类型
  （`resourceOrigin`/`indexedMedia`/`ffmpegOverIp`/`ffmpegOverIpProducer`，
  以 FF/IM 仓现有断言为准，非 5 个）+ 2 个 out 处理器
  （`resourceOriginResponse`/`ffmpegOverIpResponse`），启动日志无
  `plugin`/ABI 错误；`go version -m` 对共享包
  `github.com/killbus/rulego-ffmpeg-over-ip` 的 `dep` 行跨三件逐字节相等。
  定位：集合断言不属成员闸门（见
  `research/coexistence-ownership-first-principles.md`）；fleet 是常驻载体，
  本批证据 = 首个全 release 版 manifest 的绿 run。运行侧证据性质：证
  "已发布字节在同进程注册"，属安装/组成证据，不产出 ABI 身份断言（后者仍
  只在钉定 CI 环境成立）。
- [ ] **4.3** **最小规则调用**：每插件一条最小输入→期望输出
  （如 resource-origin 发布一个资源并 GET 回读；indexed-media 对 fixture 源请求一段 range；
  ffmpeg-over-ip 起 pinned upstream 跑一次 invocation）。

## 5. 发布

- [x] **审批门禁 G6 已完成（三仓）**：`release.yml` dispatch（各仓：`ci_run_id` + `tag`，RO=run `39811100101`/`v0.2.0`、FF=run `40055386317`/`v0.5.2`、IM=run `40058007544`/`v0.3.1`，2026-10-24 均用户逐项批准）。
  tag 与 `VERSION` 一致）。release 只发 CI 已验证 artifact（不重建），`--verify-tag`。
  `ci_run_id` **有保质期**：run 元数据（`workflowName`/`conclusion`/`headSha` 两道
  断言所读）不过期，但 artifact 自创建起 90 天后过期，届时 `release.yml` 会在
  `download-artifact` 步响亮地红。过期处置 = `gh run rerun` 同一 run（同 headSha、
  同钉死 SDK、artifact 重生、run 记录不变）后仍用**同一 run id** dispatch；
  不得改用新 revision 重触发来"造新 artifact"（会移动发布修订、破合并点碎片化纪律）。
  见 `.trellis/spec/guides/rulego-delivery-workflow.md`。
- [x] **5.1 已完成（RO + FF + IM）**：三 release 回读通过（RO v0.2.0 tag→`c6731ac`、FF v0.5.2 tag→`956ed85`、IM v0.3.1 tag→`d6786a5`；双架构 sha256 与：RO v0.2.0 回读通过（tag→`c6731ac`、双架构 sha256 与
  sidecar `plugin_sha256` 一致、sidecar 五字段为新 ABI，2026-10-24 `gh api` +
  资产重算）。IM/FF 待各自 dispatch。完整回读项（`gh api`）：release 存在、asset 带 `.sha256`、
  `sha256sum --check` 通过、artifact 名含正确平台/版本。
- [x] **5.2 已完成（G3 时点）**：GHCR 回读（`ghcr.io/killbus/rulego-server:v1.0.0-plugin` = `sha256:53719b71…`、`ghcr.io/killbus/rulego-plugin-sdk:abi-3e0c9d46…` = `sha256:c5fadb57…`，`Docker-Content-Digest` 逐条比对，见 `research/g3-abi-publish.md`）与三仓 `plugin-abi-release.json` 记录一致
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
| G3 | 合并后的 main 上 dispatch `plugin-abi-publish.yml` 发布 SDK/runtime 镜像 | **已批准并完成**（environment 无人工审批闸门，故批准 dispatch 即发布闸门） |
| G4 | push `[FF]` master | 步骤 2.6（**已批准并完成**：PR #2 rebase 合并，master `956ed85` 自证绿 `40055386317`） |
| G5 | push `[RO]` main / `[IM]` main | 步骤 3.6（**已完成**：RO `c6731ac` / IM `d6786a5`，均经 PR rebase 合并 + main 自证轮绿） |
| G6 | 三仓 `release.yml` dispatch 发布 | 步骤 5（**三仓全部完成**：RO v0.2.0 / FF v0.5.2 / IM v0.3.1，均回读核验，2026-10-24） |
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
  注：IM 的 peer 下载只被 `Hermetic selected-track TS and HLS seek` 消耗，而该
  job 已同时装入三件（`tests/e2e-hls-seek.sh:156-158`）并断言全部节点类型注册
  （`:189-199`）——它本身已是组成级载体，只是媒体路径经
  `indexedMedia`/`resourceOrigin` 与独立 ffmpeg-over-ip server 容器走，链里
  没有 `ffmpegOverIp` 节点。移出与否属另批批准，不单方改。

**[FF] rulego-ffmpeg-over-ip**
- `go.mod`、`go.sum`、`plugin/go.mod`、`plugin/go.sum`、`VERSION`、`compatibility.json`、
  `plugin-abi-release.json`、`plugin/node.go`、`plugin/producer.go`
- `.github/workflows/ci.yml`（co-existence peer：indexed-vod v0.2.0 → indexed-media <新>；
  resource-origin v0.1.1 → <新>；client 版本/h1 hash 若发新 client）
  注 1（改名残留，属 2.4 未列出的另一半）：`ci.yml:294` 的 `.nodes | any(.type ==
  "indexedVod")` 与 `COMPATIBILITY.md:11,13,22`、`README.md:101` 是同一次
  vod→media 改名（`rulego-indexed-media/README.md:168-173`：无别名/无转发）留在
  FF 仓的残留字符串。peer 改指新产物时该字符串必须同批改为 `indexedMedia`，
  否则 smoke 步要求一个无人注册的节点类型；只改字符串不改 peer 同样红。
  这是 AC12（`prd.md:131-133`）已批准迁移的缺失部分，不是新的闸门论证。
  注 2（归属）：这些 peer 行是否移出成员闸门，现由 4.2 与成员/组成证据之分决定；
  移入组成载体属发布闸门改动，需显式批准（见
  `research/coexistence-ownership-first-principles.md`）。

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
