# Implement notes: Budva audit index

## Source-verified decisions (rulego v1.0.0 module)
- fork (components/common/fork_node.go) re-delivers the SAME msg to every
  Success edge; the audit branch therefore receives the parser's full
  messages contract as a parsed object (JSON data type, base.go
  GetDataByType) and needs no extra passthrough fields beyond
  metadata.rawHex.
- jsTransform result metadata is written back via
  processJsResult ReplaceAll (js_transform_node.go): the parser's
  `metadata.rawHex = msg` stamp survives into both fork branches. Probe-
  verified under goja that the returned map carries the stamp and that
  ReplaceAll (str.ToStringMapString) accepts it.
- join (components/common/join_node.go) emits one merged Success from the
  branches it is connected from; default (mergeToMap:false) is a JSON array
  of both branch results (usable response body). mergeToMap:true flattens
  and colliding top-level keys overwrite, so two structurally identical
  write summaries would collapse to one — the chain uses the default.
- One-branch failure is NOT masked and is fast: the failed branch is
  terminal (no Success edge traversed on TellFailure) so it fires its own
  OnEnd(Failure) -> responseToBody 400 immediately; the engine releases the
  join's skipped branch when the fork completes. Spike-verified (~50ms).

## Change set (one coherent boundary)
- parser.js: +1 line `metadata.rawHex = msg;` (the toHex carrier of the
  exact wire bytes) before the return. Gate unchanged.
- events.js (new): pure projection. Reads operations[0].doc for the
  validated fields, `metadata.rawHex` for the id (sha256 over the exact raw
  bytes via the vendored crypto), `new Date().toISOString()` for
  received_at. Emits the single-index contract for budva-events-v1, op
  create. Throws (-> 400) on a missing id source or contract.
- chain.json: node_parse -> node_fork -> [node_write (unchanged config),
  node_events -> node_write_events (same ref:// owner)] -> node_join
  (timeout 45). Each jsScript byte-identical to its tested source.
- mappings/budva-events-v1.json: append-only, dynamic:false, delivery-log
  fields only (no message text).
- parser_test.go: TestParserEmit now asserts the rawHex stamp; new
  TestEventsEmit (chained on the parser's actual output; _id anchored to a
  Go-stdlib SHA-256 of the same bytes), TestEventsRedeliveryIsIdempotent,
  TestEventsRejection; the drift guard is now
  TestChainEmbedsTestedScripts (both scripts byte-identical + the six-node
  topology + Success-only edges + join timeout).
- README.md: what-it-does, loss model, files, deployment (two indices),
  verification, and the "Audit index behavior" section replacing the old
  Phase-2 note.

## Gates (all green)
go test ./... + -race (8 top-level cases incl. the drift guard),
gofmt -l empty (example + spike), go vet, spike go test (real HTTP),
validate.py, JSON lint on chain + both mappings + fixtures.
