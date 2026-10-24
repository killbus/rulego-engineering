# 插件 ABI 契约与五仓影响面

事实源：各插件仓当前源码 + `D:\Repositories\rulego-server-docker`（ABI 生产方）。
核验时间：2026-10-20，只读。

## 1. 现行 ABI 契约（v0.37.0 主机基线）

server-docker `plugin-abi.lock`（已跟踪）当前锁定：
- `abi_id`: `abi-d4fc741b72b9dba1573b61029d6deba9d17c8c22f2805546a5a92764b5c404bf`
- Go `1.25.0`，`cgo_enabled: true`，targets `linux/amd64`（GOAMD64=v1）+ `linux/arm64`（GOARM64=v8.0），gcc/g++ 12.2.0，GNU ld 2.40，`glibc >= 2.34`
- `rulego_server`: `release_version v0.37.0` @ revision `a7be24c4c1f649d422b41eb623d1d6e314b20c58`，module `github.com/rulego/rulego/server`，带 `go_mod_sha256`/`go_sum_sha256`
- `rulego_core`: `v0.36.1-0.20260802040353-2ec085f29027` @ `2ec085f2902777f10d0f867fa4295b11629257ad`
- `module_graph`: `list_sha256` + `graph_sha256`，`replacements: []`
- `build.host_mode: "exe"` / `plugin_mode: "plugin"`，`plugin_symbol: "Plugins"`，`host_workspace: "off"` / `plugin_workspace: "generated-server-and-plugin"`
- `release.sdk_image: rulego-plugin-sdk`，`runtime_image: rulego-server`，`runtime_tag_suffix: "-plugin"`，`manifest_path: /usr/share/rulego/plugin-abi.json`
- `editor_payload`: v0.37.0 的 `rulego-server-linux-amd64.tar.gz` sha256 `c541c800...`
- SDK base `golang:1.25.0-bookworm@sha256:81dc45d0...`，runtime base `distroless/base-debian12:nonroot@sha256:7f0c72cd...`

三个插件仓的 `plugin-abi-release.json` **逐字节相同**（`md5sum` 三者一致）：
```json
{
  "abi_id": "abi-d4fc741b...404bf",
  "lock_digest": "sha256:5f9501666c46871d6acd84ab259f5ce72bf11ae2d566a51f649d2c6acd289c98",
  "packaging_revision": "a498c9e29b0121e5495557ecc88c4a5df9150637",
  "runtime": "ghcr.io/killbus/rulego-server@sha256:8594e773...36cc1fcb559a",
  "sdk": "ghcr.io/killbus/rulego-plugin-sdk@sha256:be81ad63...0fdd73a48"
}
```
- `packaging_revision a498c9e...` = server-docker 当前 main HEAD（`a498c9e Document Plugin ABI consumption`）→ ABI 由 server-docker 生产并下发。
- 契约链（符合 `rulego-plugin-delivery.md`）：host source → ABI lock → immutable SDK/runtime → plugin artifact → matching-runtime registration。

## 2. 每仓 go.mod pin 与版本错位（现状）

三插件共用同一 rulego pin：`github.com/rulego/rulego v0.36.1-0.20260802040353-2ec085f29027`（伪版本，v0.37.0 开发线 @ `2ec085f2`）。
- `rulego-resource-origin/go.mod:5`（go 1.25.0）
- `rulego-indexed-media/go.mod:7`（go 1.25.0）；另直接依赖 `rulego-ffmpeg-over-ip v0.5.0`
- `rulego-ffmpeg-over-ip/go.mod:5`（go 1.25.0）+ `plugin/go.mod`（子模块，依赖根模块已发布 `v0.5.0` + 同一 rulego pin）

三插件 `compatibility.json.rulegoRelease` 均 = `"v0.37.0"`。
> **现状错位（事实）**：go.mod 编译 pin（`2ec085f2` 伪版本）≠ compatibility.json 声明 runtime（`v0.37.0`）。即"编译用的核心代码"与"声明兼容的发布版本"不在同一版本线。v1.0.0 升级时这一错位必须显式收口（见 §5）。

## 3. 每仓影响面

### rulego-resource-origin（v0.1.3，main @ fc0d15a，与 origin 一致）
- 版本三处须一致（CI 硬校验 `ci.yml:21-33`）：`VERSION`、`compatibility.json:2 pluginVersion`、`node.go:49 Version`。
- 直接 import rulego：`api/types`、`api/types/endpoint`、`builtin/processor`、`components/base`、`utils/maps`（+ 根包，测试用）。
- 插件入口 `plugin.go:13-14 var Plugins`；`init()` 注册 out 处理器 `resourceOriginResponse`（`plugin.go:24-27`）。
- 节点 `resourceOrigin` 内嵌 `base.SharedNode[*originManager]`，实际调用 `InitWithClose`（`node.go:74`）+ `GetSafely`（`node.go:94`）→ 两方法 v1.0.0 不变。
- 构建/发布全在 CI：pinned SDK 容器出 `.so`，双架构，smoke-load 断言 `io.rulego.server.release == compatibility.json.rulegoRelease`（`ci.yml` build job），e2e `tests/e2e-origin.py`。
- **升级改动**：`go.mod` rulego pin → v1.0.0；`plugin-abi-release.json` 四元组换新 ABI；`VERSION`/`compatibility.json`/`node.go` 版本号联动；（无源码 API 改动预期）。
- 版本跳：`0.1.3 → ?`（见 §6 版本号决策）。

### rulego-indexed-media（v0.3.0，main @ 4f30239，与 origin 一致）
- 单一子系统（原 indexed-vod，v0.3.0 已完成 vod→media 改名，**无别名/转发**）。
- 版本三处：`VERSION`、`compatibility.json:2`、`node.go:24 componentVersion`（CI 校验）。
- 直接 import：`api/types`、`components/base`、`utils/maps`；实际调用 `InitWithClose`（`node.go:183`）+ `GetSafely`（`node.go:193`）。
- **额外跨仓依赖**：`go.mod:6 rulego-ffmpeg-over-ip v0.5.0`（client 包）。e2e `tests/e2e-hls-seek.sh` 下载 peer 插件 `ffmpeg-over-ip` + `resource-origin` 做交叉 ABI 校验。
- **升级改动**：rulego pin → v1.0.0；`rulego-ffmpeg-over-ip` 依赖 → 升级后版本；`plugin-abi-release.json` 换 ABI；版本三处联动。
- 迁移模式现成（README：无别名、不双加载、配对回滚），可直接复用到 v1.0.0。

### rulego-ffmpeg-over-ip（v0.5.1，master @ 76e8c0e，与 origin/master 一致）
- **主分支是 master 不是 main**；存在第二 remote `azure`，`azure/master`（f3b3cd2）**领先** origin/master，含 task 归档提交 → 发布前需明确以 origin(GitHub) 为准并同步 azure（风险）。
- 双 go.mod：根模块（client，纯标准库）+ `plugin/go.mod`（依赖根模块已发布 `v0.5.0` + rulego pin）。
- 版本五处须一致（CI 校验）：`VERSION`、`compatibility.json:2`、`plugin/node.go:69`、`plugin/producer.go:75`、`plugin/go.mod` 的 client 依赖版本；另有 CI 两处硬编码断言（client 版本 + 共享模块 h1 hash）。
- 插件两节点 `ffmpegOverIp` / `ffmpegOverIpProducer`，`init()` 注册 out 处理器 `ffmpegOverIpResponse`。
- **共享 client 身份约束**（CI 硬校验）：plugin 编译出的 `killbus/rulego-ffmpeg-over-ip` 依赖记录必须与 co-existence peer 逐字节相同（`go version -m` 比对 + 硬编码 `h1:` hash）。
- **co-existence 三角（关键耦合，`ci.yml:178-181`）**：当前硬引用
  - `killbus/rulego-indexed-vod v0.2.0`（**旧仓名，已迁移为 indexed-media**）
  - `killbus/rulego-resource-origin v0.1.1`
  即 ffmpeg-over-ip 的冒烟测试仍拉**旧 indexed-vod** 与**旧 origin v0.1.1** 做双/三加载。v1.0.0 ABI 重签后这两个旧 release 与新 ABI 不匹配（`abi_id`/`lock_digest` 不同），**该 CI 步必然失败** → 必须把 co-existence peer 换成升级后的 `indexed-media` + 新 `resource-origin`。
- **升级改动**：两个 go.mod 的 rulego pin → v1.0.0；`plugin-abi-release.json` 换 ABI；版本五处 + CI 硬编码 hash 联动；**co-existence peer 引用改指向升级后的 indexed-media/resource-origin**；若发新 client 版本则牵动 indexed-media 的 `go.mod`。

### rulego-server-docker（main @ a498c9e，**无 tracking upstream**，含 11 项未跟踪 WIP）
- **已跟踪**（45 项）：`Dockerfile`/`Dockerfile.plugin-sdk`/`Dockerfile.plugin-runtime`、`plugin-abi.lock`、`.github/workflows/{publish.yml,plugin-abi.yml,plugin-abi-publish.yml}`、`scripts/*`（14 个，含 `fetch-release.sh`/`verify-build.sh`/`verify-published.sh`/`plugin-abi.sh`/`prepare-plugin-abi.sh`/`plugin-abi-build.sh`）、`tests/*`（14 个）。
- **标准/all 镜像流**（`publish.yml`）：版本由 `resolve-release.sh` 动态发现上游 latest stable → **v1.0.0 发布后此流几乎零改动**（除非 asset 命名/结构变）。风险点：`fetch-release.sh` 强制要求包内含 `config.conf`/`node_pool.json`/`editor/index.html`（v1.0.0 仍满足）。
- **Plugin ABI 流（升级主战场）**：`plugin-abi.lock` 全部与 v0.37.0 绑定，需完整重签：
  - 用 v1.0.0 server 源码重算 `rulego_server`（revision + go.mod/go.sum sha256）
  - 重算 `rulego_core` 版本/revision、`module_graph`（list/graph sha256）、`editor_payload`（v1.0.0 asset sha256）
  - 重算 `abi_id`、`lock_digest`、`packaging_revision`，换 `sdk`/`runtime` 镜像 digest
  - 流程：`scripts/prepare-plugin-abi.sh` → `plugin-abi.sh validate --candidate` → size 审查 → release
  - **6+ 个 tests 的版本断言需同步**：`tests/plugin-abi-lock.sh:29-42,79`（断言 v0.37.0/v0.37.0-plugin/revision/core 版本）、`tests/resolve-release.sh`、`tests/fetch-release-{success,failure}.sh`、`tests/fetch-plugin-editor.sh`、`tests/plugin-image-contract.sh:96`。
  - **cgo 约束**：ABI lock `cgo_enabled: true`、host_mode `exe`。而上游 v1.0.0 GitHub 发布二进制是 `CGO_ENABLED=0` 静态编译。**plugin-ABI 流的 host 必须从 v1.0.0 server 源码用匹配工具链（golang:1.25.0-bookworm, gcc 12.2, CGO_ENABLED=1, buildmode=exe）重新编译**，不能复用静态发布二进制。
- **未跟踪 WIP（他人工作，须保护、不可动）**：`.agents/ .claude/ .codex/ .cursor/ .opencode/ .trellis/ AGENTS.md Dockerfile.all Dockerfile.slim scripts/detect-base.sh scripts/verify-image.sh .github/workflows/build.yaml`。
  - `build.yaml`（WIP）与已跟踪 `publish.yml` 是**平行两套构建方案**，且 WIP 有明显缺陷（只拉 amd64 asset 却建双平台、`$EXPECTED`/`$VERSION` 变量错误、base 未 pin digest）。
  - `Dockerfile.all/slim`（WIP，逐字节相同）端口 9000、`/usr/local/bin`、无 VOLUME，**与已跟踪契约（9090/`/app`/`/app/data`）冲突**。
  - 这些 WIP 与未跟踪 `.trellis/tasks/08-24-rulego-server-docker/` 同源。**本次升级不得触碰或"顺手修"这些 WIP**；是否采纳哪套 build.yaml 属 server-docker 自己的决策，列为待确认/延期项。
- **保护要求**：main 无 upstream tracking，升级涉及 server-docker 的提交方式须遵守其既有流程；不得 reset/clean/动 WIP。

## 4. 升级顺序与依赖（关键路径）

```
[0] rulego 核心 v1.0.0 已 tag/已发布（事实，无需动作）
  │
  ▼
[1] rulego-server-docker：以 v1.0.0 server 源码重签 plugin-abi.lock
  │    → 产出新 abi_id / lock_digest / packaging_revision
  │    → 发布新 rulego-plugin-sdk + rulego-server(-plugin) 镜像（digest 化）
  │    （标准/all 镜像流 publish.yml 可并行，零改动即可出 v1.0.0 镜像）
  ▼
[2] 三个插件仓（可并行，彼此无编译依赖，除 indexed-media→ffmpeg-over-ip client）：
  │    各自 go.mod rulego pin → v1.0.0 + 换 plugin-abi-release.json 新 ABI
  │    + 版本号联动 → CI 重建双架构 .so + 匹配运行时 smoke-load
  │
  │    子顺序（client 身份约束）：
  │      ffmpeg-over-ip 若发新 client 版本 → 先打 client tag
  │      → indexed-media go.mod 依赖该 client 版本
  │      → 两仓 co-existence peer 互指升级后版本
  │    ffmpeg-over-ip CI co-existence peer：
  │      killbus/rulego-indexed-vod v0.2.0 → killbus/rulego-indexed-media <新>
  │      killbus/rulego-resource-origin v0.1.1 → killbus/rulego-resource-origin <新>
  ▼
[3] 部署：安装新 .so 到匹配 -plugin runtime，重启，组件注册回读，
  │    最小规则调用验证；多插件共存验证
  ▼
[4] 发布产物/校验和/版本元数据回读（GitHub release + GHCR digest）
```

**硬依赖**：插件仓的 CI build job 在 `plugin-abi-release.json` 的 abi_id/lock_digest/sdk/runtime 未更新为 v1.0.0 对应值之前**必然失败**（smoke-load 校验 `io.rulego.server.release == rulegoRelease`）。所以 **[1] server-docker ABI 重签是 [2] 的前置门槛**。

**软依赖/可并行**：三插件彼此无直接编译依赖（indexed-media 依赖 ffmpeg-over-ip 的 *client 包* 是唯一例外）。server-docker 标准/all 流与 ABI 流相互独立。

## 5. 已批准决策与剩余外部门禁

1. **版本号方案（已批准）**：resource-origin 0.1.3→0.2.0、indexed-media 0.3.0→0.3.1、ffmpeg-over-ip 0.5.1→0.5.2。
2. **go.mod pin（已批准）**：统一使用正式 tag `v1.0.0`。
3. **client 包（已批准）**：ffmpeg-over-ip client 源码不变，沿用 `v0.5.0`。
4. **co-existence peer（已批准）**：将 ffmpeg-over-ip CI 的 `indexed-vod v0.2.0` 换成新版 `indexed-media`，并同步新版 resource-origin。
5. **server-docker WIP（已批准排除）**：未跟踪的 `build.yaml`/`Dockerfile.all`/`Dockerfile.slim` 等不纳入本次升级。
6. **ffmpeg-over-ip azure remote 同步**：升级/发布前是否需把 azure/master 与 origin/master 对齐。
7. **CHANGELOG 缺失**：三插件仓均无 CHANGELOG（release notes 靠 `--generate-notes`）。是否借 v1.0.0 迁移补 CHANGELOG？

## 6. 回滚点

- 各插件仓：升级以**独立 commit/branch** 进行，`.so`/go.mod/ABI sidecar 原子更新；回滚 = revert 到升级前 commit（旧 .so 与其旧 ABI 配对，不可混搭）。
- server-docker：`plugin-abi.lock` 重签是独立提交；`-plugin` runtime/sdk 镜像 tag 不可变（first-writer canonical），回滚 = 指回旧 digest（旧镜像仍在 GHCR）。
- 部署层：保留旧版 .so + 旧 -plugin runtime 镜像，故障时整组回退（配对回滚，禁止新 .so + 旧 runtime）。
- 规则链：v1.0.0 有 join/flow 语义重做，升级 host 后**既有已部署链需回读验证**（尤其含 join/group/flow 跨链的链），必要时按 v1.0.0 语义调整。
