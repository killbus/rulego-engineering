# G3 发布实测：Plugin ABI 镜像进入 GHCR

> run：https://github.com/killbus/rulego-server-docker/actions/runs/39754464997
> 触发：`workflow_dispatch`，`ref=main`，`publish=true`，head `006436e`（dispatch 前用
> `git ls-remote origin refs/heads/main` 确认 main 未被移动）。
> 结论：**success**（4 job 全绿）→ 契约校验 4s / amd64 staging 6m35s / arm64 staging 5m28s
> / publish immutable indexes 2m36s。

## 1. 发布记录（三仓 sidecar 的唯一合法来源）

`plugin-abi-publish.yml` 的 `plugin-abi-release-006436e….zip` artifact 内容：

```json
{
  "abi_id": "abi-3e0c9d46dddaf6235cfe609d543222f07f8e1abf3374f0669bf703df85063885",
  "lock_digest": "sha256:e19c9657ede2e9da86aae38c2ab972d32ff22aa2f2c8f1aa327714967baf8f80",
  "packaging_revision": "006436e34d1fa2cd811f840547724fb0ace3605b",
  "runtime": "ghcr.io/killbus/rulego-server@sha256:53719b71a4890a39086a921c557ab2c0386de57a5450cceaad5d7fc7564f0419",
  "sdk": "ghcr.io/killbus/rulego-plugin-sdk@sha256:c5fadb574a1171854eead3a9f94484e1470aba5496d51c2751a6313d7f2b8d01"
}
```

这两个 digest 与前三轮验证矩阵 evidence 里的 `localhost:5000` digest **不同**，
印证 `ci-matrix-pr1.md` §6：矩阵跑出来的是 job 内本地 registry 的 digest，
GHCR digest 只在这里产生。

## 2. canonical tag 首写（不可逆）

```text
ghcr.io/killbus/rulego-plugin-sdk:abi-3e0c9d46…  → sha256:c5fadb57…
ghcr.io/killbus/rulego-server:v1.0.0-plugin      → sha256:53719b71…
```

标签由 `scripts/plugin-abi.sh render tags` 决定：
`sdk = release.sdk_image + ":" + abi_id`，`runtime = release.runtime_image + ":" +
release_version + runtime_tag_suffix`。发布日志逐条可见两次
`docker buildx imagetools create` 都把 staging index 推成了上述 canonical tag。

## 3. 1.8 回读：不依赖本机 Docker 的 registry 侧核验

本机没有 docker CLI，`docker manifest inspect` / `docker run` 这条路走不通。
改用 GHCR 的**匿名 pull token**（`GET /token?scope=repository:killbus/<pkg>:pull`）
+ registry API 直接回读，比"本地 docker 能看见"更强：它验证的是 registry 的真实状态。

| 检查 | 结果 |
| --- | --- |
| `Docker-Content-Digest`（runtime tag） | `sha256:53719b71…` ＝ release record |
| `Docker-Content-Digest`（sdk tag） | `sha256:c5fadb57…` ＝ release record |
| runtime index 子镜像 | `linux/amd64` + `linux/arm64` + 2 个 attestation |
| runtime child config labels | `io.rulego.server.release=v1.0.0`、`io.rulego.abi.lock.digest=sha256:e19c9657…`、`io.rulego.abi.platform=linux/amd64`、`io.rulego.server.revision=45d1a6c4…`、`io.rulego.core.version=v1.0.0`、`io.rulego.go.version=1.25.0`、`io.rulego.libc.minimum=2.34` |
| sdk index annotations | 同组值 + `io.rulego.abi.platforms=linux/amd64,linux/arm64` |

- 两处 `org.opencontainers.image.revision` 都是 `006436e…`（main commit）→
  `PLUGIN_ABI_PACKAGING_REVISION` 注入生效。
- SDK 的 ABI 元数据在 **index annotations**（含复数 `platforms`），runtime 的在
  **child config labels**（含单数 `platform`）。这不是不一致，而是
  `verify-plugin-oci.sh:53` 的正向断言：index 上不允许出现单数 `platform`。
- 本机 token 无 `read:packages` scope（`gh api users/killbus/packages/...` 403），
  所以匿名 pull token 是这台机器上唯一可用的 registry 回读通道。

## 4. 发布态 size 报告（`published-sizes.tsv`）

| variant | arch | compressed | uncompressed |
| --- | --- | --- | --- |
| plugin-sdk | amd64 | 1,325,312,437 | 3,381,673,854 |
| plugin-sdk | arm64 | 1,316,264,176 | 3,388,073,100 |
| plugin-runtime | amd64 | 29,976,185 | 69,691,934 |
| plugin-runtime | arm64 | 28,751,227 | 80,424,467 |

全部在 ready 态 ceilings 内；这些值是 `verify-plugin-oci.sh … release` 对
**已发布 canonical ref** 复检后写出的，不是 staging 阶段的数字。

## 5. 下一步

1. 三仓 `go.mod` pin `github.com/rulego/rulego v1.0.0`（现为
   `v0.36.1-0.20260802040353-2ec085f29027`）。
2. 三仓 `plugin-abi-release.json` 换成上面五字段（三仓逐字节一致）。
3. 版本联动 + CI co-existence peer 迁移，按 implement.md 步骤 2/3。
