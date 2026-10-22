# Co-existence peer pinning blocks the new-ABI releases

## Symptom

`rulego-indexed-media` PR #5 (`f3e64b7`, new v1.0.0 ABI sidecar) went red in
run `39813678234`. The four publishing-relevant jobs were green
(`test`, `build` amd64, `build` arm64, `release-metadata`). The failing job is
`Hermetic selected-track TS and HLS seek`, step
`Download and verify peer plugins`.

Job logs are admin-only, so the cause was reproduced from public inputs. The
step downloads released peers and asserts their sidecar equals this repo's:

```bash
abi_id=$(jq -er .abi_id plugin-abi-release.json)
lock_digest=$(jq -er .lock_digest plugin-abi-release.json)
jq -e --arg abi "$abi_id" --arg lock "$lock_digest" --arg sha "$artifact_sha256" '
  .abi_id == $abi and .lock_digest == $lock and
  .platform == "linux/amd64" and .plugin_sha256 == $sha
' "tmp/peers/$artifact.abi.json"
```

Fetched peer sidecars (public release assets):

| peer release | `abi_id` | `lock_digest` |
| --- | --- | --- |
| `killbus/rulego-resource-origin v0.1.1` | `abi-d4fc741b…` | `sha256:5f9501666…` |
| `killbus/rulego-ffmpeg-over-ip v0.5.1` | `abi-d4fc741b…` | `sha256:5f9501666…` |

This repo now pins `abi-3e0c9d46…` / `sha256:e19c9657…`. `jq -e` returns false
and `set -euo pipefail` exits 1. Expected, not a regression.

## Why this is a deadlock, not a bug

Each repo's only release path is `release.yml` (`workflow_dispatch`), which
refuses unless a whole CI run of this workflow succeeded on exactly the commit
being tagged:

```bash
test "$(gh run view "$RUN_ID" … --jq '.workflowName + ":" + .conclusion')" = "CI:success"
test "$(gh run view "$RUN_ID" … --json headSha --jq .headSha)" = "$(git rev-parse HEAD)"
```

The co-existence job is inside `ci.yml`, so peer ABI equality is part of that
`CI:success` verdict. Peer downloads per repo:

| repo | peers downloaded | can CI go green now? |
| --- | --- | --- |
| `resource-origin` | none | yes — run `39810333396` + main run `39811100101` both green |
| `indexed-media` | `ffmpeg-over-ip v0.5.1`, `resource-origin v0.1.1` | only after both peers ship new-ABI releases |
| `ffmpeg-over-ip` | `indexed-vod v0.2.0`, `resource-origin v0.1.1` | only after both peers ship new-ABI releases |

`indexed-media` needs a released `ffmpeg-over-ip` on the new ABI and
`ffmpeg-over-ip` needs a released `indexed-media` on the new ABI. A plugin built
on the old ABI also cannot be smoke-loaded next to one on the new ABI, so
pointing the peer download at any old release fails at load even if the ABI
assert were removed. Neither repo can produce the `CI:success` run that the
other one needs.

Old ABI (`abi-d4fc741b…`, `sha256:5f9501666…`) versus new ABI
(`abi-3e0c9d46…`, `sha256:e19c9657…`) is the same split that drove this whole
task, so no re-signing can bridge it.

## Unblocked right now

taking `resource-origin` as the reference point: no peer downloads, PR #4 CI
green (`39810333396`), rebased main is `c6731ac`, main push CI green
(`39811100101`). A `release.yml` dispatch with that run id satisfies both gate
assertions today.

## Options to break the cycle

1. **Shorten co-existence to two plugins for one migration run**
   (recommended). In `ffmpeg-over-ip`, temporarily drop the `indexed-media`
   peer so the job smokes `ffmpeg + origin` (both new ABI).
   `ffmpeg-over-ip` releases `v0.5.2`, then `indexed-media` CI (peers
   `ffmpeg-over-ip v0.5.2` + `resource-origin v0.2.0`) goes green and releases
   `v0.3.1`, then a follow-up commit restores the three-plugin matrix and CI
   re-verifies it. The three-plugin proof still exists twice over: the restore
   commit and the deploy-side check in step 4.2.
2. **Move the co-existence job out of `ci.yml` into its own workflow.** Keeps
   every assertion but redefines what `CI:success` covers, which is the
   guarantee `release.yml` relies on. More permanent gate surgery than option 1
   needs.
3. **Peer from sibling CI artifacts instead of releases**
   (`download-artifact` with `repository:` + `run-id:`). Cross-repo artifact
   download needs a `repo`-scoped token, which `github.token` does not have, so
   this is not viable as-is.

Any of 1–2 is a deliberate change to a release gate and needs explicit
approval.

## Lock digest note (checked while investigating)

`plugin-abi.sh:lock_digest()` is `sha256(jq -S -c <whole lock> | tr -d '\r')`,
and `006436e` changed only `release.state` plus the four `size_limits` numbers
in `plugin-abi.lock` relative to `b1c20fe` (where `abi_id` was signed). So
`111ea6bb…` is the digest of the lock at signing time and `e19c9657…` is the
digest of the published `ready` lock that CI compares against; the SDK/runtime
image labels carry `e19c9657…`. The plugin sidecars use `e19c9657…`, which is
what the plugin repos assert against.
