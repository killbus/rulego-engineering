# PR #1 ABI 矩阵实测（G2 已完成）

> 第一轮 `measurement`（head `568f6c9`）：<https://github.com/killbus/rulego-server-docker/actions/runs/39733165394>
> 第二轮 `ready`（head `654b044`）：<https://github.com/killbus/rulego-server-docker/actions/runs/39739872974>
> PR：<https://github.com/killbus/rulego-server-docker/pull/1>
> 触发：均为 `event=pull_request`，两轮结论都是 **success**（三 job 全绿）。

## 1. CI 复核了本地算出的派生身份

两个架构的 native evidence 一致回读：

```text
abi_id      = abi-3e0c9d46dddaf6235cfe609d543222f07f8e1abf3374f0669bf703df85063885
lock_digest = sha256:111ea6bbbce3d075752ff3639c77f9ca1cf129020ebf7da4f78482b095d775ef
```

与本地按 LF 口径重算并写入 lock 的值逐字节相同 → 实现说明：
`abi_id`/`lock_digest` 的 CI 口径判定（见 `abi-byte-canonicalization.md`）成立；
`go_mod_sha256`/`go_sum_sha256` 与 `module_graph` 两个 digest 由
`prepare-plugin-abi.sh:113-116` 在 `golang:1.25.0-bookworm` 内重算并断言通过
（含 `GOVERSION==go1.25.0`、`replacements == []`、core 选中 `v1.0.0`）。

Job 结果：Validate Plugin ABI contract / Native amd64（5m33s）/ Native arm64（6m3s）
均 success。工具链假设未失效：Go 1.25.0 + gcc 12.2.0 + GNU ld 2.40 + glibc≥2.34 照旧。

## 2. 实测镜像大小（1.7b 的输入）

| arch | 对象 | compressed | uncompressed |
| --- | --- | --- | --- |
| amd64 | sdk | 1,325,288,158 | 3,381,656,026 |
| amd64 | runtime | 29,976,175 | 69,691,900 |
| arm64 | sdk | 1,316,192,360 | 3,388,009,640 |
| arm64 | runtime | 28,751,198 | 80,424,433 |

对照旧契约（v0.37.0）已评审 ceiling：sdk 1,500,000,000 / 3,800,000,000；
runtime amd64 35,000,000 / 80,000,000；runtime arm64 35,000,000 / 90,000,000。
**全部实测值都在旧 ceiling 之内**（最紧的是 amd64 runtime uncompressed
69.7M/80M＝87%，arm64 为 80.4M/90M＝89%）。

> 待用户决策：ceilings 沿用旧已评审值（最小变更、保持既有闸门），还是按实测收紧。
> README 的 release-ready 流程把"记录正值 ceilings"明确留给维护者判断，代理不代签。

## 3. 实测确认：发布必须在合并后的 main 上

两次 evidence 的 `packaging_revision` 都是
`327599ca821953278bef8e687be0ca8515c36b58`，**不等于** PR head `568f6c9`
——`pull_request` 事件下 `GITHUB_SHA` 是 merge ref 的 SHA。这直接证实 design 的约束：
`plugin-abi-release.json` 的 `packaging_revision` 不能引用 PR 运行产物，
G3 必须在合并后的 main 上 dispatch。

本 PR 未发布任何镜像：`plugin-abi.yml` 从不设 `PLUGIN_ABI_PUBLISH`，
registry 是 job 本地（`localhost:5000/...`，`staging_reference: null`），
`release.state=measurement` 下不会走 `validate --release`。

## 4. 第二轮 CI：`release.state=ready` 实测（1.7b）

`654b044` 只改 `plugin-abi.lock` 的 release 块（`state=ready` + 沿用旧已评审 ceilings）。
run `39739872974`（head `654b044`）三 job 全绿：Validate（3s）/ Native amd64（5m20s）/
Native arm64（4m24s）。两架构 evidence 一致回读：

```text
abi_id      = abi-3e0c9d46dddaf6235cfe609d543222f07f8e1abf3374f0669bf703df85063885
lock_digest = sha256:e19c9657ede2e9da86aae38c2ab972d32ff22aa2f2c8f1aa327714967baf8f80
```

- `abi_id` 与第一轮相同：它只覆盖构建契约，不含 release 块。
- `lock_digest` 从 `sha256:111ea6bb…` 变为 `sha256:e19c9657…`：release 块进 manifest 哈希。
  **插件侧 `plugin-abi-release.json` 必须记 ready 态这个值**，不能记第一轮的。

ready 态下 `plugin-abi-build.sh:201-207` 会真正用 ceilings 断言，实测占用率：

| arch | 对象 | 实测 / ceiling | occupancy |
| --- | --- | --- | --- |
| amd64 | sdk compressed | 1,325,272,144 / 1,500,000,000 | 88.4% |
| amd64 | sdk uncompressed | 3,381,663,230 / 3,800,000,000 | 89.0% |
| amd64 | runtime compressed | 29,976,185 / 35,000,000 | 85.6% |
| amd64 | runtime uncompressed | 69,691,934 / 80,000,000 | 87.1% |
| arm64 | sdk compressed | 1,316,183,819 / 1,500,000,000 | 87.7% |
| arm64 | sdk uncompressed | 3,388,018,572 / 3,800,000,000 | 89.2% |
| arm64 | runtime compressed | 28,751,226 / 35,000,000 | 82.1% |
| arm64 | runtime uncompressed | 80,424,467 / 90,000,000 | 89.4% |

与 measurement 轮的值差在压缩器噪声量级（<0.01%），没有"贴边"通过。
`packaging_revision` 仍是 merge ref SHA（本轮 `d2e12eaa…`，不等于 head `654b044`），
第 3 节的结论在 ready 轮复现。

## 5. 剩余步骤（按 implement.md）

1. 合并 PR #1（需用户批准）→ 在合并后的 main 上 dispatch `plugin-abi-publish.yml`（G3）。
2. 取新 SDK/runtime GHCR digest，并以合并后的 main commit 作 `packaging_revision`
   → 三插件仓 `plugin-abi-release.json`（步骤 2/3）。

