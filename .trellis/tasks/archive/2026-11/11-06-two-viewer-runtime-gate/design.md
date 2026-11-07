# Two-viewer runtime gate design

## 1. Decision summary

Add one diagnostic collector mode that runs two same-program HLS consumers at
different start positions under a single shared telemetry poller. The mode emits
per-viewer evidence plus one cross-viewer summary and never edits production
configuration.

The run uses video `3UJp1qfvL90`, starts 0 and 600 seconds, a 360-second media
target, unchanged 1080p/read-ahead, child TTL `120000 ms`, and the existing
512 MiB budget. (`R1`-`R5`)

The alternative of launching two separate single-viewer collectors is rejected
for this gate because it duplicates the 22-node, one-second debug polling load
and makes launch synchronization and cross-viewer attribution harder. The
alternative of jumping directly to the three-viewer matrix is rejected because
the earlier separated-position run produced four capacity failures and there is
no two-viewer contention evidence. (`R1`, `R4`, `R9`)

## 2. Module boundaries and responsibilities

| Module | Responsibility | Change |
| --- | --- | --- |
| Diagnostic collector | Own bounded player processes, shared telemetry polling, sanitized evidence, and per-run summary | Add a two-viewer mode while preserving the existing single-viewer behavior |
| Offline tests | Prove parsing, launch, cleanup, and summary invariants with mocks and fixtures | Add two-viewer cases |
| Deployed RuleGo runtime | Serve the unchanged HLS graph and debug API | No change |
| `mpv` | Consume the actual HLS rendition and report player-observable behavior | No change |
| Parent coordination task | Approve scope, run the live gate, and review the result | No change |

The collector is task-local evidence tooling under `research/`. It does not
become a production dependency, a graph component, or a second capacity owner.
(`R3`, `R7`)

## 3. Dependency direction

```text
two-viewer collector -> mpv
two-viewer collector -> deployed debug API
two-viewer collector -> shared sanitization and parsing helpers
deployed runtime -/-> task-local collector
player -/-> task-local collector
```

The collector may depend on the existing public HTTP contracts. It must not
import runtime internals, read deployment files, mutate chains, or infer
inventory from debug tails. (`R3`, `R6`)

## 4. Inputs and preconditions

The two-viewer invocation accepts only the following bounded inputs:

```text
base URL, chain ID, two viewer labels, video ID, start seconds,
360-second media target, output directory, optional mpv path
```

For this gate the values are:

```text
viewer A: video 3UJp1qfvL90, start 0
viewer B: video 3UJp1qfvL90, start 600
media target: 360 seconds
```

Before playback:

1. Require a new output directory and create its evidence files exclusively.
2. Fetch and parse the component and chain read-back through authenticated,
   no-redirect, no-proxy requests.
3. Require `resourceOrigin` 0.2.1, child lease `120000`, parent lease
   `21600000`, and `maxRetainedBytes` 536870912.
4. Require one successful initial tail fetch for every configured node.
5. Record sanitized hashes/identities for the preflight rather than volatile
   credentials or raw configuration.

Any failed precondition stops before spawning a player. (`R3`, `R7`, `AC6`)

## 5. Launch and lifecycle

The collector owns exactly two player processes and one polling-helper process:

1. Resolve `mpv` to an executable that the collector can own; a wrapper without
   its sibling executable is rejected.
2. Prepare separate temporary logs and final evidence paths for both viewers.
3. Record spawn-request and spawn-return UTC for each viewer.
4. Launch both with `--start=<position> --end=<position+360> --no-ytdl
   --vo=null --ao=null --force-window=no --read-ahead` unchanged.
5. Fail the run if the two observed launch timestamps are more than two seconds
   apart, or if either process is not alive at the post-launch barrier.
6. Stop either viewer only at its natural exit, the wall deadline minus cleanup
   reserve, an owned-process failure, or collector interruption.
7. Terminate only owned PIDs, with process-tree containment and direct-child
   fallback. Never target processes by image name.
8. In `finally`, stop the poller, attempt final tails, close evidence files, and
   summarize partial results even after interruption.

The wall deadline remains 540 seconds. The existing 12-second cleanup reserve is
preserved. (`R4`, `R5`, `R7`)

## 6. Shared telemetry

One polling helper fetches the same 22 node tails as the single-viewer collector,
at a target one-second interval, rather than multiplying request load by the
number of viewers. Each row retains:

- node, message and request identity, IN/OUT direction, relation, server time;
- sanitized resource, generation, parent, video/revision, index/segment, size,
  state, TTL/expiry, failure kind;
- whether the row arrived before, during, or after each player lifecycle.

The summary records per-node fetch failures, retained-row caps, long gaps,
overlap loss, and final-tail gaps. Captured events are a bounded observation,
not a complete ledger. Absence of a failure row is not proof that the runtime
emitted none. (`R5`, `R6`)

## 7. Consumer evidence

Each player has independent:

- command and owned PID;
- spawn-request/return, exit and stop reason;
- direct numeric `time-pos` progress and source of the maximum;
- resolution, end-file status and exit code;
- HTTP/status, segment-open and retry signals;
- completed and unfinished buffering intervals;
- audio-null underruns, retained as a separate observation.

Startup is separated from midplay by the first observed advance beyond 0.25
seconds. Missing progress is `unknown`, not zero. The 360-second target permits
the existing one-second endpoint tolerance. (`R2`, `R5`, `AC2`, `AC3`)

## 8. Cross-viewer correlation

The summary joins only on stable identifiers:

- `msgId`/message ID from request through acquire, produce, commit and serving;
- resource/generation identity;
- video ID plus requested segment/index;
- node IN/OUT timestamps for stage latency.

It reports two requested regions: around index 0 and around the index derived
from start 600. It counts captured ready commits, observed TTLs, failure signals
and derived lower-bound peaks independently. Server/client clock offset remains
unknown; temporal containment is not treated as proof of ownership. (`R6`,
`AC4`)

## 9. Result model

`summary.json` has these separate sections:

```text
scope = two_viewer_same_program_different_positions_not_AC5
preflight
launch
viewers[A,B]
server
crossViewer
limits
collectionStatus
```

There is no field that converts this run into three-viewer acceptance. The
reviewer may issue a gate verdict only for AC1-AC7 and must repeat the limits.
`collectionStatus` distinguishes completed, partial, and aborted evidence.
(`R8`, `R9`, `AC5`-`AC7`)

## 10. Failure handling and stopping rules

- Precondition mismatch: write `aborted.json`, do not play.
- Initial telemetry failure: write `aborted.json`, do not play.
- Second-player launch failure: stop the first owned player, preserve partial
  evidence, and mark the run aborted.
- Any captured `storage_limit` or `wait_timeout`: preserve evidence and stop the
  capacity branch; do not add a third viewer.
- Either player fails to reach the media target, reports non-1080p, exits
  abnormally, or has a segment-open/HTTP failure: preserve evidence and treat the
  narrow gate as failed pending review.
- Polling gaps or final-tail loss: do not manufacture a verdict; classify the
  affected dimensions as incomplete.

No failure permits quality reduction, TTL/budget changes, cache clearing, or a
silent rerun. (`R1`-`R3`, `R7`, `R9`)

## 11. Verification

Offline tests must cover:

- exactly two viewers, distinct positions, and an enforced synchronization
  barrier;
- rejection of duplicate labels, duplicate positions, unsupported viewer count,
  and existing output directories;
- shared single poller with the same node set as the single-viewer mode;
- per-viewer progress/resolution/log parsing and no cross-assignment;
- owned-PID-only cleanup on normal exit, one-player failure, deadline, and
  interruption;
- preflight mismatch/initial-tail failure before player launch;
- summary separation, all limits, and no AC5 field;
- source and destination preservation of the single-viewer mode.

The live gate then requires preflight read-back, a two-player run, and an
independent evidence review. (`AC1`-`AC7`)

## 12. Non-goals

- No same-position reuse test.
- No third viewer and no AC5 closure.
- No production code, graph, plugin, TTL, budget, disk, cache, or service edits.
- No physical quality, inventory, retained-byte, other-host, or universal
  capacity claim.
- No automatic retry after a failed run.

## 13. Assumptions and risks

- [ASSUMPTION] Running two 1080p positions for 360 seconds is materially safer
  than repeating the failed three-position workload and is sufficient to decide
  whether a third viewer remains plausible.
- [ASSUMPTION] The two `/youtube/3UJp1qfvL90` requests remain within the same
  production chain and public origin.
- One-second shared polling is measurable instrumentation overhead; it can
  perturb latency and must be reported.
- A successful two-viewer run does not prove three viewers fit the 512 MiB
  budget.

## 14. Acceptance mapping

| Criterion | Design landing |
| --- | --- |
| AC1 | §4-§5 launch and preconditions |
| AC2 | §7 consumer evidence |
| AC3 | §7 failure and buffering classification |
| AC4 | §6 and §8 shared telemetry/correlation |
| AC5 | §9-§10 result separation and stopping rules |
| AC6 | §4 preflight |
| AC7 | §2, §9 and §12 boundaries |
