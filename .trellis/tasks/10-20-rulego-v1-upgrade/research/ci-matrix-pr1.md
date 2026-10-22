# PR #1 ABI 矩阵实测（G2 已完成）

> 运行：https://github.com/killbus/rulego-server-docker/actions/runs/39733165394
> PR：<https://github.com/killbus/rulego-server-docker/pull/1>
> 触发：`event=pull_request`，head `568f6c9`，结论 **success**（三 job 全绿）。

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

## 4. 剩余步骤（按 implement.md）

1. 回填 ceilings + `state=ready` 为一个 commit → PR 再跑绿（1.7b）。
2. 合并 PR → 在 main 上 dispatch `plugin-abi-publish.yml`（G3）。
3. 取新 SDK/runtime digest → 三插件仓 `plugin-abi-release.json`（步骤 2/3）。
