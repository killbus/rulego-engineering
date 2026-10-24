# RuleGo 核心 v1.0.0 事实证据

事实源：`D:\Repositories\rulego`（本地克隆，非 shallow）。全部结论附 `文件:行` 或精确命令输出。
核验时间：2026-10-20。本次仅只读核验，未改动 rulego 仓任何文件。

## 1. 版本与标签

- 本地 `HEAD` = `45d1a6c4e1af594d7319dd11df9fa58bd48fd0e0`，`git describe --tags` = `v1.0.0`（与 origin/main 一致）。
- 标签集合（`git tag | tail`）：`v0.12.0 … v0.37.2 v0.37.3 v0.38.0 v1.0.0`。**v1.0.0 是首个 1.0 大版本**。
- `v0.38.0..v1.0.0` 共 **92 个提交**（`git log --oneline v0.38.0..v1.0.0 | wc -l`）。
- 标签日期：`v0.38.0` @ 2026-09-09（commit `1378763`），`v1.0.0` @ 2026-10-19（commit `45d1a6c`）。
- `git merge-base --is-ancestor v0.38.0 v1.0.0` = yes（线性累积）。
- **注意**：本地克隆**不含** `v0.37.0` tag（`git rev-parse v0.37.0^{commit}` = unknown revision），也不含 v0.37.0 线的 core/server commit（`2ec085f2`、`a7be24c` 均 `cat-file` 失败）。v0.37.0 事实经插件仓 gomodcache 与 server-docker `plugin-abi.lock` 交叉取证，见 `plugin-abi-contract-and-repo-impact.md`。
- 上游 GitHub release `v1.0.0` 已发布：`published_at 2026-10-19T10:09:34Z`，`releases[0]` = v1.0.0（`gh api repos/rulego/rulego/releases`）。上一条为 `v0.37.0` @ 2026-08-03。**v0.38.0 从未单独 publish 到 GitHub releases**（只作为源码 tag 存在）。

## 2. 版本常量与哨兵错误（v1.0.0 新增）

- 根包 `github.com/rulego/rulego` 的版本常量：`rulego.go:119-120`
  ```go
  // Version is the semantic version of the RuleGo core library.
  const Version = "1.0.0"
  ```
  注意：`api/types` 下**无** `types.Version` 常量（`grep "Version ="` 无命中）。changelog 中 "新增 types.Version" 系措辞偏差，真实位置是根包 `rulego.Version`。
- `api/types/component.go:248-250` 的 `Version string` 是 **ComponentForm 的组件版本号字段**（插件 `Def()` 填自己的版本），不是核心版本。
- 新增哨兵错误 `api/types/errors.go:22-27`（v0.38.0..v1.0.0 新增，`errors.go +28` 行）：
  - `ErrRuleChainNotFound = errors.New("rule chain not found")`
  - `ErrNodeNotFound = errors.New("node not found")`
  - `ErrMsgHopBudgetExceeded = errors.New("message hop budget exceeded")`

## 3. Go 版本与模块布局

- 根模块 `go.mod:1-3`：`module github.com/rulego/rulego`，`go 1.20`（核心库仍声明 go 1.20）。
- server 模块 `server/go.mod:1-3`：`module github.com/rulego/rulego/server`，**`go 1.25.0`**；直接依赖（`server/go.mod:6-18`）：
  - `github.com/rulego/rulego v1.0.0`
  - `github.com/rulego/rulego-components v1.0.0`
  - `github.com/rulego/rulego-components-ai / -ci / -discovery / -etl / -iot` 各 `v1.0.0`
- 两个 Go 模块（根 `go.mod` + `server/go.mod`）。`components/` 目录属于**根模块**（`find go.mod` 仅两根），v0.38.0 起已入核心（`git log --diff-filter=A -- components/base/base.go` → `2e66930`）。
- CI Go 版本：`build.yml:19 go-version: '1.25.x'`、`test-server.yml:22 go-version: ["1.25"]`、`test.yml:33 go-version: ['1.18.10','1.20','1.22']`（核心库兼容老 Go，server 用 1.25）。

## 4. 动态插件加载契约（.so）

- 加载点 `engine/registry.go:277-295` `loadPlugin(file)`：`plugin.Open(file)` → `p.Lookup(PluginsSymbol)` → 类型断言 `types.PluginRegistry`。
- `engine/registry.go:35-36`：`const PluginsSymbol = "Plugins"`。
- `api/types/types.go:251-286` `PluginRegistry` 接口：导出符号名 `Plugins`，方法 `Init() error` + `Components() []Node`。
- **结论**：插件契约自 v0.38.0 未变（符号名/接口方法名一致）。真正的 ABI 绑定不在源码接口，而在 Go 运行时 ABI（见 ABI 研究文件）。

## 5. 插件面向 API 面：v0.38.0..v1.0.0 diff

对比对象：插件当前编译基线 `core@2ec085f2`（伪版本 `v0.36.1-0.20260802040353-2ec085f29027`，取自插件仓 gomodcache）vs v1.0.0 工作树。

| 插件使用的 API | v0.37 线（gomodcache） | v1.0.0 | 结论 |
| --- | --- | --- | --- |
| `types.Node` 接口（`OnMsg(ctx,msg)`/`Init`/`Destroy`/`Def() ComponentForm`/`Type()`） | `types.go:528,596,646,693,738` | 同 | **签名不变** |
| `base.SharedNode[T]` 导出方法 | `base.go` Init/InitWithClose/GetSafely/Close/… | `base.go:248+` 同名方法集**超集**（新增 `InitWithCloseSoftFail`/`RefTarget`/`IsBorrower`/`SetStatus`/`ConnectionStatus`/`Instance`） | **纯增量，无删除** |
| `base.SharedNode.InitWithClose` / `GetSafely`（resource-origin、indexed-media 实际调用） | 存在 | 存在 | **不变** |
| `endpoint.Exchange` 结构（`In/Out Message` + `sync.RWMutex`） | `endpoint.go:597-621` | `endpoint.go:623-647` 字段一致 | **不变** |
| `endpoint.Flusher`（ffmpeg-over-ip 类型断言） | `endpoint.go:1730` | `endpoint.go:1756` | **不变** |
| `processor.OutBuiltins` / `.Register(name, func(endpoint.Router,*endpoint.Exchange) bool)`（resource-origin、ffmpeg-over-ip 注册 out 处理器） | `processor.go:202,267` | `processor.go:202,267` | **不变** |
| `utils/maps.Map2Struct`（三插件 import） | 存在 | `maps.go` 仅删一空行 | **不变** |
| 根包 `rulego.NewConfig()`（测试用） | 存在 | 存在 | **不变** |

v0.38.0..v1.0.0 在插件可能触及的包中**被删除**的 API（`git diff v0.38.0..v1.0.0`）：
- `api/types/types.go`（`-16`）：删 `RuleContext.SubmitTack(task func())`（deprecated）、删 `WithEndFunc(...)`（deprecated，改用 `WithOnEnd`）。
- `utils/str`：`template.go -94`（删 `NewTemplate`/`ExecuteTemplate`/`Template`，迁到 `utils/el`）。
- iterator 节点组件删除（changelog）。

**三插件源码对这些被删 API 的引用**（全仓 `grep`，排除 `tmp/gomodcache` 依赖缓存）：
- `SubmitTack` / `WithEndFunc` / `OnMsgWithEndFunc` / `OnMsgWithOptions`：**无命中**（resource-origin 的命中全部在 `tmp/gomodcache` 旧依赖里，非本仓源码）。
- `utils/str` / `NewTemplate` / `ExecuteTemplate`：resource-origin、indexed-media、ffmpeg-over-ip 源码均**无命中**。
- `ffmpeg-over-ip` 的 `client/` 子包（`client.go/files.go/protocol.go`）**纯标准库，零 rulego import**（`grep rulego` 无命中）。

> **结论：三个插件仓对 v1.0.0 的编译依赖是零 breaking。** 核心升级对插件源码是"纯兼容升级"——插件 `.go` 文件预期无需改动，唯一必须改的是 `go.mod` 的 rulego pin（见 ABI 文件）。风险不在 API 面，而在 Go 运行时 ABI（`go build -buildmode=plugin` 要求 host 与 plugin 由同一工具链/依赖图编译）。

## 6. v1.0.0 功能性变化（影响部署/行为，非插件编译）

摘自 `doc/CHANGELOG.md` v1.0.0 段 + 92 提交列表（选择性，标注与多仓升级相关项）：
- **engine**：join 语义重做（等直接入边分支完成，不再等整个 fork 子树）；`msg_max_hops` hop 预算防失控循环；worker 池打满同步降级。→ 行为变化，影响已部署链的运行语义（尤其含 join/group 的链）。
- **node_pool**：新增分布式原语 `Locker`/`OnceGuard`/`ActiveGuard`；`SetConfig` 锁内热更换。→ schedule 多副本去重、主备选主。
- **endpoint**：链内 `ref://` 解析到同链节点/端点（两阶段部署）；mqtt 消息数据类型可配置；EventConnect 支持关 websocket。
- **flow/ref**：flow 节点支持 `chainId:nodeId` 跨链起点 + `${}` 动态 targetId。
- **server**：多租户用户管理、管理面审计、规则链版本快照与回滚、全局配置热更新、可嵌入 bridge 模式、chat completions 按用户限流；**依赖工具链要求 Go 1.25+**。
- **security 一轮加固**：拒绝已删除用户认证、config 资源仅管理员、JWT 算法白名单等。
- **rulego-components**：fasthttp 流式重构、kafka/redis/rabbitmq 共享连接与单活选主、streamsql v1.3.0 流-流 JOIN、**SSH 认证字段合并 `certKeyFile`**（breaking，影响用 ssh 节点的已部署链配置）。
- **聚合覆盖率提升到 88.4%**（core）。

> 这些是**行为/配置面**变化，属于"部署与运行时回读"验收范围，不是插件编译面。plugin .so 本身不变。

## 7. v1.0.0 发布产物（server 二进制，供 server-docker 消费）

上游 `build.yml`（push tag `v*` 触发）产物 = **静态 server 二进制**（`CGO_ENABLED=0 go build`，`-trimpath`，`with_all`/标准两种），**不含任何 .so 插件、不含 docker 镜像**。归档成员：`rulego-server[-all]-<os>-<arch>` + `config.conf` + `node_pool.json` + `editor/`。
- **发布包内 editor 来自私有仓** `whki/rulego-editor`（`build.yml` "Checkout editor (private)"，`base=/editor/`，`user-manual.pdf` 已剥离）。
- GitHub release v1.0.0 资产 digests（`gh api .../releases/tags/v1.0.0`）：
  - `rulego-server-linux-amd64.tar.gz` = `sha256:c1a735950e6572ac6dbc95f578458f8d6f5d5ad8ab3c433a531e8c55c7372650`（10,613,125 B）
  - `rulego-server-linux-arm64.tar.gz` = `sha256:39d9ccd666e827bc557c1bf9813461810113c85fe2e429eca127f90a736f7f5f`（9,769,562 B）
  - `rulego-server-all-linux-amd64.tar.gz` = `sha256:eacacc57089aa1f1098bdf99b374a6d417ad1945077c1f9d545b4212b5e1d178`（35,066,239 B）
  - （完整 14 资产清单见 `gh api`；含 386/macos/windows）
- **关键**：server-docker 的 plugin-ABI 流需要 **server 从源码以 `buildmode=exe` 用匹配工具链重编译**（非直接用上面静态 CGO_ENABLED=0 发布二进制），因为 Go plugin ABI 要求 host(exe) 与 plugin(.so) 共享同一工具链+依赖图。发布二进制是 `CGO_ENABLED=0`，而 ABI lock 记录 `cgo_enabled: true`。**这是 v1.0.0 升级的核心约束之一。**

## 8. 待确认（core 侧）

- [ ] v1.0.0 线 server 模块的 `go.mod`/`go.sum` 是否有 `replace`？（根 `go.mod` 无 replace；server 需确认——影响 ABI lock 的 `module_graph.replacements`。）
- [ ] v1.0.0 的 editor 私有仓 ref（`EDITOR_REF`）与 editor asset 的确切 sha256（server-docker 重新 fetch 时由 CI 算，规划期不抄）。
- [ ] `types.Logger.Printf` 标注"计划 2.0 移除"（`api/types/logger.go:81-84`）——v1.0.0 仍保留，插件若实现自定义 Logger 需保留 `Printf`。
