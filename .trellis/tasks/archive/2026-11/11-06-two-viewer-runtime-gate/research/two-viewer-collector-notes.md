# Two-viewer diagnostic collector

## Scope and boundary

This task-local collector implements only the approved same-program,
different-position diagnostic run. Its scope string is
`two_viewer_same_program_different_positions_not_AC5`; it emits no conformance
verdict and has no field that converts the run into AC5.

The collector launches exactly two owned `mpv.exe` processes for video
`3UJp1qfvL90`: `viewer-a` at position 0 and `viewer-b` at position 600. Each
player has a 360-second media target (`--end=360` and `--end=960`). It does not
change a graph, plugin, rendition, TTL, budget, cache, service, read-ahead,
quality setting, prior evidence, planning artifact, or spec.

The frozen single-viewer source and tests were read as a safety/parsing pattern
only. Their hashes remain:

```text
run-single-baseline.py   BA6C23FBE69FB012211F0C31F615837738C3AD3F66E8B6B9F6B19A9E13A45A26
test_single_baseline.py  E8943DC330C2F2B8B2DF6363B2D82A3550C56FB76A90ADBBE5BAD4E83339206A
```

## Preflight and launch

The output path must be new. Authenticated component, shared-node, and chain
read-backs use no-redirect, no-proxy requests with an 8 MiB response cap.
Preflight resolves the resource-origin values from two verified endpoint
envelopes and requires:

```text
resourceOrigin version       0.2.1
child ttlMs                  120000
parent ttlMs                 21600000
maxRetainedBytes             536870912
resourceOrigin roots         ref://resource-origin
```

The catalog is `/api/v1/components`. Its top-level `nodes[]` contains component
form definitions; preflight selects that unique `type: resourceOrigin` definition
and requires `version: 0.2.1`. The live instance is `/api/v1/shared-nodes?page=1&size=100`;
its top-level `items[]` contains shared node instances. Preflight requires
exactly one `type: resourceOrigin` item and its `id` must be `resource-origin`.
Instance policy values are read from that item's `configuration`; the catalog
form definition has neither `configuration` nor `maxRetainedBytes`. Raw bodies
are never persisted. The evidence records separate `componentsSha256` and
`sharedNodesSha256`, the sanitized instance id, selected policy numbers, and the
chain hash.

The collector writes a sanitized `preflight.json`, requiring successful initial
tail receipts for all 22 nodes before either player is spawned. Policy mismatch,
read-back failure, and initial telemetry failure write `aborted.json` and leave
all players unstarted except that the separate polling helper may have started
for the initial-tail attempt. `existingTraffic.knownLocalMpvProcesses` is `null`
with state `not_measured`; it is not a measured zero.

Spawn-request and spawn-return UTC, owned PID, sanitized command, and player exit
are recorded separately. Both spawn returns must fall within two seconds and
both owned processes must be live at the post-launch barrier. A launch failure
stops only still-live owned PIDs and preserves partial evidence.

## Telemetry and evidence

One helper process owns the shared poller. It contains 22 node workers at a
one-second target, or 22 debug-tail requests per second, rather than 44 because
the viewer count does not multiply polling. This is measurable instrumentation
overhead and may perturb latency.

Each viewer has a distinct stdout marker (`VIEWER-A` or `VIEWER-B`), a separate
temporary verbose log, and an independent evidence stream. Log files are read
incrementally by byte offset; an event line is parsed once and an incomplete
final line is held until completed. This avoids duplicate event counts during
polling. Raw URLs, credentials, configuration bodies, and temporary log paths
are not persisted in summary evidence.

`summary.json` has only these top-level sections:

```text
scope
preflight
launch
viewers
server
crossViewer
limits
collectionStatus
```

`collectionStatus.status` is `completed`, `partial`, or `aborted`.
`completed` describes collection state only, never conformance. Server events
are joined only on sanitized stable identifiers and are not assigned to a
viewer by time. Inventory, server/client clock offset, and ledger completeness
remain unknown.

## Limits

```text
media target per viewer              360 s
progress endpoint tolerance          1 s
minimum progress floor               359 s
minimum overlap bound                359 s
nominal overlap                      360 s
playback-rate assumption             approximately 1x
launch synchronization window        2 s
wall limit                           540 s
cleanup reserve                      12 s
shared poll interval                 1 s
debug nodes                          22
target debug request rate            22 requests/s
HTTP socket timeout                  3 s
maximum response body                8 MiB
```

The 359-second overlap and progress floor deliberately share one bound and are
coherent only under approximately 1x media progress. Slower playback can fail
overlap before it fails the progress floor.

## Offline verification

The deterministic suite uses mocked HTTP/process objects and fabricated logs;
it performs no live API call, playback, deployment, commit, push, merge, or
release.

```powershell
python -B -W error::ResourceWarning -m unittest discover -s .trellis/tasks/11-06-two-viewer-runtime-gate/research -p test_two_viewer.py -v
python -B -c "from pathlib import Path; p=Path('.trellis/tasks/11-06-two-viewer-runtime-gate/research/run-two-viewer.py'); compile(p.read_text(), str(p), 'exec'); q=Path('.trellis/tasks/11-06-two-viewer-runtime-gate/research/test_two_viewer.py'); compile(q.read_text(), str(q), 'exec'); print('compile ok both')"
```

The suite covers two-viewer bounds, duplicate/unsupported inputs, existing
output refusal, the frozen 22-node set, launch synchronization, single-poller
spawning, real catalog/shared-node envelopes, old-summary fail-closed behavior,
unique instance selection, preflight and initial-tail aborts, incremental-log
deduplication, per-viewer isolation, owned-PID cleanup, wall deadline,
interruption, summary separation, all limits, and the no-AC5 boundary. Last
result: 39 tests, OK, with `ResourceWarning` treated as an error. Both sources
compile without writing bytecode.

## Exact code hashes

```text
design.md                 28742D5547C83FEE6C3007891B6910B46454451E626C5837909F345E0BBB03B2
run-two-viewer.py         4982CB29C71D81F16768FC9F7857A7E9803F9C937D9AF00DD902A6C863BDE369
test_two_viewer.py        7D66B42DD37486A560E870EE1C9DC00A86556A6B8A98E29168DDD2099DAD0E01
```

The notes and `review/responses.json` are mutable implementation records; their
final hashes are reported after the last write and are intentionally not
embedded here to avoid a self-referential hash.

## Residual unknowns

- The shared-nodes request must return the verified `{items, page, size, total}`
  envelope and exactly one `resourceOrigin` item with id `resource-origin`;
  otherwise preflight aborts. The component catalog must return a `nodes[]`
  array with one `resourceOrigin` form definition carrying `version`; otherwise
  preflight aborts.
- Real mpv progress cadence, stderr/log ordering, and final-line flushing remain
  runtime behavior not proven offline.
- Windows `taskkill /T` containment and direct-child fallback are mocked; real
  process-tree containment was not exercised.
- Final-tail capture can still miss rows that race helper shutdown. This remains
  an incomplete dimension, not evidence of absence.
- Server clock offset, cross-client traffic, inventory, and actual instrumentation
  perturbation remain unknown until an independently reviewed live run.
