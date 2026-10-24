# 插件仓 CI 硬化（升级为前置条件）

## 为什么先做这个

三插件仓的 `release.yml` 已经是**唯一发布闸门**：必须传 `ci_run_id`，并断言

```text
workflowName + ":" + conclusion == "CI:success"
run.headSha == 被 tag 的 commit
```

再 `download-artifact` 取 CI 产物 + `sha256sum --check`，step 名就叫
"Publish without rebuilding"。所以 CI 的**可复现性属于发布保证的一部分**，
而三仓 workflow 里 actions 全是浮动标签（`@v4`/`@v5`）——同一条 main 在不同
日期重跑可能执行不同的 action 代码。

与 ABI 版本无关 → 按 `rulego-delivery-workflow.md:56-63` 的关切切线，
**与版本无关的改动先落**，并在旧契约上跑绿，再用硬化后的闸门去认证升级。

## 实测的仓库现状（硬化前）

| 项 | resource-origin | indexed-media | ffmpeg-over-ip | server-docker（基线） |
| --- | --- | --- | --- | --- |
| 固定 SHA 的 actions 引用 | 0 | 0 | 0 | 4–11 / workflow |
| 浮动标签引用 | 7+3 | 11+3 | 9+2 | 0 |
| `persist-credentials: false` | 0/3 · 0/1 | 0/4 · 0/1 | 0/5 · 0/1 | 全覆盖 |
| `concurrency` | 无 | 无 | 无 | 有 |
| 默认分支保护 | **404 未保护** | **404 未保护** | **404 未保护** | — |

分支保护未开启意味着"CI 绿了才能进 main"目前只是习惯，不是闸门；
`release.yml` 的 run↔commit 绑定是唯一的实际约束。

## 钉固值（= 写入当日浮动标签的解析结果，故行为中性）

| action | 版本 | commit |
| --- | --- | --- |
| `actions/checkout` | v4.4.0 | `11d5960a326750d5838078e36cf38b85af677262` |
| `actions/setup-go` | v5.6.0 | `40f1582b2485089dde7abd97c1529aa768e1baff` |
| `actions/upload-artifact` | v4.6.2 | `ea165f8d65b6e75b540449e92b4886f43607fa02` |
| `actions/download-artifact` | v4.3.0 | `d3f86a106a0bac45b974a628896c90dbdf5c8093` |

四个值都用 `GET /repos/<act>/git/commits/<sha>` 验证过是 **commit 对象**——
若浮动标签是附注标签（`object` 为 tag 对象），`uses: …@<sha>` 会在 CI 直接失败，
这一步必须在推送前做。upload-artifact 的值与 server-docker 已钉的**完全相同**，
两仓收敛到同一供应链基线。

## 如何证明"行为中性"而不是嘴上说

脚本 `D:/tmp/.../harden.py` 改写后重新 `yaml.safe_load`，把三处预期改动**逆操作**
（SHA 换回浮动标签、删 `persist-credentials`、删 `concurrency`），再断言与原文件
解析结果**结构相同**。这个断言在开发中抓到三次真错：

1. `- uses:` 的列表符号被吃掉（YAML 非法）；
2. 符号列计算把整个步骤右移 2 列（YAML 非法）；
3. 合成 `with:` 块缩进多两列（YAML 非法）。

校验器自身也错过一次（先删空 `with` 再递归，导致假阳性漂移），改为后序遍历。
本地无 PyYAML/actionlint，用 `pip install --target D:/tmp/.../pylibs pyyaml` 补齐，
不写 C 盘也不动仓库环境。

## 落地状态

三仓各一新分支 `ci/harden-workflows`（从各自主干 HEAD 出发，只动 2 个 workflow）：

| 仓 | commit | diff |
| --- | --- | --- |
| `rulego-resource-origin` | `f2f71d7` | 2 files, +34/−10 |
| `rulego-indexed-media` | `81fe7fa` | 2 files, +44/−14 |
| `rulego-ffmpeg-over-ip` | `f3fa520` | 2 files, +39/−11 |

校验（`verify-workflows.py`，YAML 解析而非正则）：三仓 6 个 workflow
`floating_refs=0`、`missing_persist_credentials=0`、`concurrency=True`。

## 首轮 CI 实测：钉固引用被真实执行（三仓 PR 全绿）

PR：origin [#3](https://github.com/killbus/rulego-resource-origin/pull/3) ·
indexed-media [#4](https://github.com/killbus/rulego-indexed-media/pull/4) ·
ffmpeg-over-ip [#1](https://github.com/killbus/rulego-ffmpeg-over-ip/pull/1)

| 仓 | run | 结论 | job 明细 |
| --- | --- | --- | --- |
| `rulego-resource-origin` | `39797558518` | success | `actionDate`：test / build amd64 / build arm64 / release-metadata 全 success |
| `rulego-indexed-media` | `39797584463` | success | test（含 `go test -race`）/ build ×2 / e2e HLS seek / release-metadata 全 success |
| `rulego-ffmpeg-over-ip` | `39797591889` | success | pinned-upstream / test / build ×2 / release-metadata 全 success |

日志里步骤名直接是可解析的钉固引用，即钉固值确实被 Actions 解析并执行：

```text
✓ Run actions/checkout@11d5960a326750d5838078e36cf38b85af677262
✓ Run actions/setup-go@40f1582b2485089dde7abd97c1529aa768e1baff
✓ Run actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
```

读取教训：`gh run view --json jobs` 首次返回时 job 列表**会滞后于 run 状态**
（run 已 `completed/success`，jobs 里还有 `in_progress`/`queued`）；
而 `--jq` 里写 `select(...)` 的计数在 PowerShell 里被引号吃掉过，报出
`jobs=1` 这种自相矛盾的值。终态判定改用 `--json` 原样返回 + 本地反序列化逐 job 看。

## 未做（需单独批准，属远端仓库设置写入）

- 分支保护 + required status checks。开启后"必须先 PR 才能进 main"，
  与 `implement.md` 里 G4/G5 现在写的"直接 push 主干后看 CI"模型冲突，需一并改口径。
- 三仓升级到 v1.0.0 的改动另出一个 PR：resource-origin 的已存
  `D:/tmp/rulego-abi/session-20261022/origin-v1-upgrade.patch`（8 文件 +19/−15）。
