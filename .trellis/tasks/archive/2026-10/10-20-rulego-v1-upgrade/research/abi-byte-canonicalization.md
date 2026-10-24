# ABI 派生值的字节口径（实测取证）

> 结论：`abi_id`/`lock_digest` 的记录口径是 **LF（CI/Linux）字节口径**。
> 本任务一度按 Windows 口径写入 `abi-1b36cb64…`，属实现缺陷，已修。
> 全部数字来自真实命令输出，非推断。

## 1. 现象

`scripts/plugin-abi.sh` 的派生方式：

```bash
canonical_abi()      { jq -S -c '.abi' "${lock}" | ... ; }   # → sha256 → abi_id
canonical_manifest() { jq -S -c . "${lock}"      | ... ; }   # → sha256 → lock_digest
```

本机 `jq 1.7.1`（Scoop shim，Windows 构建）**在每条输出行尾追加 `CR`**：

```text
$ echo '{"a":"ld"}' | jq -c . | od -An -c
 { " a " : " l d " } \r \n
```

而提交的 `plugin-abi.lock` 本身是 LF-only（`tr -cd '\r' | wc -c` = 0）。
所以 CR 只可能来自 jq 的 **stdout**，不进文件，只污染哈希输入。

## 2. 口径判定（对提交态 HEAD lock 双向复算）

```text
HEAD lock 记录的 abi_id     = abi-d4fc741b72b9dba1573b61029d6deba9d17c8c22f2805546a5a92764b5c404bf
HEAD lock 未去 CR 重算      = 0261a6c24112a6c80615885dbac829d4768cfc91db8a196dfbdfcefb4059f3d4
HEAD lock 去 CR(LF) 重算    = d4fc741b72b9dba1573b61029d6deba9d17c8c22f2805546a5a92764b5c404bf   ← 与记录一致

HEAD lock 去 CR 的 lock_digest = sha256:5f9501666c46871d6acd84ab259f5ce72bf11ae2d566a51f649d2c6acd289c98
三插件 plugin-abi-release.json 记录的 lock_digest 与之逐字节相同
```

→ 旧契约的 `abi_id` 与 `lock_digest` 都是在 **LF 字节口径**下算出的。
按未规范化字节算出的 `abi-1b36cb64…` 是本地口径错误，CI 会在
`plugin-abi.sh` 的 `stale abi_id` 检查上判红。

## 3. 修复面（三处，均在 `rulego-server-docker`）

1. `plugin-abi.lock`：`abi_id` → `abi-3e0c9d46dddaf6235cfe609d543222f07f8e1abf3374f0669bf703df85063885`
   （由当前 v1.0.0 lock 内容按 LF 口径重算；文件保持 LF、CR 计数 0）。
   `render lock-digest` 随之为
   `sha256:111ea6bbbce3d075752ff3639c77f9ca1cf129020ebf7da4f78482b095d775ef`
   （`lock_digest` 不在 lock 内存储，纯派生；最终值仍以 CI 输出为准）。
2. `scripts/plugin-abi.sh`：`canonical_abi` / `canonical_manifest` 的哈希输入
   `| tr -d '\r'`；`render_sdk_env` 的 jq 输出同样归一化——否则 CR 会被 `read`
   折进变量值，再被 `printf %q` 转义成字面量 `\r` 写进 `build.env`
   （`tests/plugin-abi-lock.sh` 的 `grep -Fxq 'LINKER_COMMAND=ld'` 正是被这个假象挡住）。
   在 CI 的 LF emitter 上 `tr -d '\r'` 是 **no-op**，不改契约语义。
3. `tests/prepare-plugin-abi.sh`：测试自带 fixture 用 `jq -S -c .abi | sha256sum`
   复算期望 `abi_id`，同样需要 `tr -d '\r'` 才能与验证器口径一致
   （真跨平台缺陷：该测试此前只在 Linux 上跑过）。

> 遗留风险（登记，不在本任务改）：`canonical_manifest` 全局 `tr -d '\r'` 意味着
> `lock_digest` 描述的是"去掉 CR 后的提交字节"。本例 lock 无 CR 故等价；
> 更稳的做法是加 `.gitattributes`/CI 断言强制 lock LF-only，而不是在哈希输入处吞 CR。

## 4. 本地 `tests/run.sh`（14 项）实测

```text
RUN_SH_EXIT=0
fetch-release-failure / fetch-release-success / fetch-plugin-editor /
lib-plugin-helpers / repository-contract / plugin-abi-lock / plugin-abi-drivers /
plugin-build-helper / plugin-image-contract / plugin-publication-policy /
prepare-plugin-abi / resolve-release / retry-and-manifest /
verify-published-failures  → 全 pass
```

环境：Windows + Git Bash 5.2.37 + `go1.25.1 windows/amd64` + `jq 1.7.1`。

**这只是契约单测层的本地绿。ABI 权威证据仍需 CI**：`plugin-abi-build.sh:10` 要求
`GITHUB_ACTIONS=true`、`prepare-plugin-abi.sh:101` 断言 `GOVERSION==go1.25.0`，
本机不可能替代。另注意 `tests/run.sh` **未被任何 workflow 引用**，CI 只跑
`plugin-abi.sh render/validate` + `plugin-abi-build.sh`。

## 5. 未改的 v0.37.0 引用（曾误列必改项）

`tests/resolve-release.sh`、`tests/fetch-release-{success,failure}.sh`、
`tests/verify-published-failures.sh` 里的 `v0.37.0` 是测试**自注入**的 mock
fixture（喂给被测脚本再断言自己注入的值），与 ABI lock 无关，不改。
标准/all 流的版本坐标由 `publish.yml` 经 `resolve-release.sh` 动态解析。

## 6. 触发与凭据事实

- `.github/workflows/plugin-abi.yml` 触发只有 `pull_request` 与
  `push: branches:[main]`，**无** `workflow_dispatch` → 不动 main 的验证路径是 PR。
- 写凭据可用：`gh auth status` → `killbus (keyring)`，scopes 含 `repo`、`workflow`；
  `C:\Users\ying\.gitconfig` 的 `credential.https://github.com.helper`
  即 `gh auth git-credential`，故 `git push` 与 `gh` 共用同一 token。
  早先"token 失效"的判断是沙箱屏蔽凭据造成的假象。
- 公开仓库可匿名读运行结论，但 `/actions/runs/<id>/logs` 未认证返回 403。

## 7. 可复现材料位置

- 模块图解析产物（v1.0.0 server `go list -m all` / `go mod graph`，CR 计数 0）：
  `D:/tmp/rulego-abi/resolve2/{module-list,module-graph}.txt`
  → `list_sha256=47be6910…`、`graph_sha256=1ed5c015…` 与 lock 一致。
- `.trellis/tasks/10-20-rulego-v1-upgrade/research/local-evidence/module-graph-report.txt`
  是一次**失败**日志（C 盘写满 + sumdb 权限），不可作为证据使用。
- 临时文件一律落 `D:/tmp`，不放 C 盘（C 盘剩余约 0.5 GB，是上述失败的直接原因）。
