# Two-viewer runtime verification

- date: 2026-11-06 (UTC) / 2026-11-07 (CST)
- scope: `two_viewer_same_program_different_positions_not_AC5`
- run directory:
  `.trellis/tasks/11-06-two-viewer-runtime-gate/research/runtime/two-viewer-20261106T162620Z`
- command:
  `python -B .trellis/tasks/11-06-two-viewer-runtime-gate/research/run-two-viewer.py --out <run directory>`
- exit code `0`, wall `402 s` (limit `540 s`), no abort, collection
  `completed` with `stopReason: player_exited`
- frozen harness: `run-two-viewer.py`
  `4982CB29C71D81F16768FC9F7857A7E9803F9C937D9AF00DD902A6C863BDE369`,
  `test_two_viewer.py`
  `7D66B42DD37486A560E870EE1C9DC00A86556A6B8A98E29168DDD2099DAD0E01`

This run is diagnostic evidence for the two-viewer scenario only. It is not an
AC5 result and cannot be converted into one.

## Review chain

| Gate | Verdict | Artifact | Agent |
| --- | --- | --- | --- |
| Design review | PASS (D1-D8) | `review/design-findings.json` | `6df32838-e8aa-4613-addd-87407ed29c86` |
| Code review round 1 | PASS | `review/findings.json` | `a73e1c17-048e-4b97-b3dd-94a9d3d2ea77` |
| Implementer (preflight fix) | delivered | `review/responses.json` | `a3aee033-53ae-49fd-afd8-2c7ad9e4df5b` |
| Code review round 2 | PASS | `review/findings-round2.json` | `0762ce27-1c30-485b-8c95-177344de446b` |
| Evidence review | PASS | `review/evidence-findings-run1.json` | `2805410b-c376-4447-9f3f-39179fcfb48b` |

`design.md` stayed byte-identical at
`28742D5547C83FEE6C3007891B6910B46454451E626C5837909F345E0BBB03B2`, so the
planning approval remains valid. The round-2 review exists because the preflight
endpoint mapping had to be corrected before the run.

## Preflight read-back

`status: accepted`, 8 of 8 checks true:

```text
resourceOriginVersion   0.2.1          from /api/v1/components nodes[]
sharedNodeInstance      resourceOrigin from /api/v1/shared-nodes items[]
sharedNodeId            resource-origin
maxRetainedBytes        536870912
maxResourceBytes        33554432
maxTtlMs                86400000
maxProductionMs         300000
childTtlMs              120000         chain child-acquire-request
parentTtlMs             21600000       chain parent-acquire-request
chain shape             52 nodes / 69 connections
resourceOrigin roots    7 nodes, all ref://resource-origin
```

Endpoint mapping verified by live read-only probing from the main session: the
component version comes from the `/api/v1/components` form catalog, while the
instance configuration (including `maxRetainedBytes`) comes from the
`/api/v1/shared-nodes?page=1&size=100` `items[]` entry whose id is
`resource-origin`. Raw bodies, URLs, and secrets are never persisted; the
evidence keeps only hashes and extracted numbers.

## Player results

| Viewer | Start | PID | Exit | Max position | Relative progress | Resolution | Captured error signals | Completed buffering |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| viewer-a | 0 s | 1296 | 0 | 359.976278 s | 359.976278 s | 1920x1080 | 0 | none |
| viewer-b | 600 s | 45880 | 0 | 959.975678 s | 359.975678 s | 1920x1080 | 0 | 5.393761 s, one interval |

- spawn-return spread `1.81768798828125 s` against a `2.0 s` window; the
  post-launch barrier passed
- request spread was `1.54988 s`; the two separate spreads are both recorded
- observed open indices: viewer-a `0..108`, viewer-b `114..224` plus `0, 1`; the
  two viewers consumed disjoint regions apart from the first two indices
- no `storage_limit`, `wait_timeout`, HTTP 507/504, and no
  `Failed to open segment` in either viewer this run
- the single completed buffering interval is attributable to viewer-b. The
  flattened `consumer-events.jsonl` carries no viewer label, so the reviewer
  could not isolate viewer-a buffering markers from the raw stream; viewer-a's
  "none" is the per-player summary value, not a raw-stream proof.

## Server telemetry (bounded observation, not a ledger)

```text
captured events                     3136
failure signals in client window    0
fetch failures                      0
invalid or missing jsonl rows       0
ready/commit events                 221
ledgerComplete                      false
retainedBytes                       null
inventory                           unknown_not_collected
server/client clock offset          unknown
```

## What this run does and does not prove

It supports: two simultaneous discrete consumers of `3UJp1qfvL90` at positions
`0` and `600` can both complete a 360 s 1080p span with exit 0, unchanged
quality, TTLs, and 512 MiB budget, and with no captured server failure signal or
segment-open failure, while one shared 22-node poller observed the chain.

It does not prove: AC5 or three-viewer capacity, same-position reuse behaviour,
aggregate `retainedBytes` or inventory state, disk headroom, other-host traffic,
server/client clock alignment, absence of stalls without buffering markers,
per-segment fetch completion, or the cause of viewer-b's single 5.4 s buffering
interval. No raw per-viewer mpv log was retained, so parser-level buffering
conclusions cannot be re-audited from a raw source.

## Cross-validation

Consistent with the sequential single-viewer baselines in the parent task:
`3UJp1qfvL90` reached `359.976 s` and `J1z_eXpVD1w` reached `359.920 s`, both
1080p with no captured player errors. It neither contradicts nor revalidates the
earlier three-concurrent-viewer `storage_limit` / HTTP 507 finding, which
remains the open capacity question.
