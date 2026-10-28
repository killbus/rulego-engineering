# Design: Budva audit index (verified against rulego v1.0.0 module source + the fork/join spike)

## Topology (deployed)
```
POST /budva-to-es  (toHex + headersToMetadata, wait:true, responseToBody)
  v
node_parse (jsTransform, unchanged skeleton)
  | msg = messages contract JSON; metadata gains rawHex = hex(raw body)
  v
node_fork (type: fork, no config)
  +-- Success --> node_write (elasticsearchWrite, budva-messages-v1, op index, unchanged)
  +-- Success --> node_events (jsTransform, events.js)
                    | msg = audit contract JSON (index budva-events-v1, op create,
                    | _id = sha256(raw bytes))
                    v
                  node_write_events (elasticsearchWrite, same ref:// owner)
  node_write + node_write_events --Success--> node_join (type: join, timeout 45)
```
Single terminal = the join, so the endpoint's response OnEnd fires exactly
once (deterministic). Without the join both writes would be terminals and
the response body would be whichever branch's OnEnd ran last.

## Spike-verified runtime facts (research/forkjoin-spike/, real engine + real HTTP)
Anchors are the v1.0.0 source plus OBSERVED behavior (the spike fails if the
response contract changes; it pins rulego v1.0.0, so it is task research
evidence, not a standing regression):
1. fork (components/common/fork_node.go) broadcasts the SAME msg to all
   Success edges. Both branches therefore receive the parser's full
   messages contract; the audit branch needs no extra passthrough fields
   beyond metadata.rawHex (fork copies nothing, it re-delivers the msg).
2. jsTransform result processing (js_transform_node.go
   processJsResult): the returned `metadata` map is written back onto the
   RuleMsg via ReplaceAll. The endpoint's headersToMetadata-stamped headers
   plus our rawHex survive into both branches.
3. join (components/common/join_node.go) collects the branches it is
   connected from (Success edges) and emits ONE merged msg. Default
   (mergeToMap:false) => JSON array of both branch results with nodeId,
   usable as the response body. mergeToMap:true FLATTENS each branch's top
   level and colliding keys overwrite - with two structurally identical
   write summaries it collapses to one, so the chain uses the default.
4. Wait semantics (engine.go processMessage: OnMsgAndWait blocks on
   onAllNodeCompleted): the HTTP response is written only after BOTH writes
   complete (observed: lat >= slowest branch). join timeout 45 > write
   timeout 30 keeps a hung write from outliving the request.
5. One-branch failure (observed): the failed branch is terminal (its
   Success edge into the join is not traversed on TellFailure) so it fires
   its own OnEnd(Failure) -> responseToBody 400 immediately (observed ~50ms,
   not the join timeout); the engine releases the join's skipped branch when
   the common ancestor (fork) completes, so the join still fires and the
   request ends. The 400 reason carries the failed node id and reason.
   Cost: two OnEnds -> the failure-path body is a concatenation of the
   reason text and the surviving branch's summary. Status is clean.
6. The 400/200 status contract is unchanged from Phase-1: 200 only when the
   chain ends without error, 400 otherwise (responseToBody hardcodes 400 on
   error). Budva never retries; the reason text is the signal.

## Audit doc
- `_id = sha256Hex(raw body bytes)` (the SAME bytes the HMAC gate verified,
  carried as metadata.rawHex). Redelivery of an identical body => identical
  _id, op `create` => ES 409 duplicate => classified `duplicate` by the
  plugin (idempotent success).
- doc: `{event, occurred_at, chat_id, message_id, received_at}`. Projection
  of the parser's validated contract (operations[0].doc) plus the server
  receipt time. No content: the audit index is a delivery log, not a
  second copy of message text (keeps it cheap and out of the sensitive-
  content surface; full state remains in budva-messages-v1).
- `dynamic: false`, ids long, times date, discriminators keyword.

## Parser change (one line, drift-guarded)
`metadata.rawHex = msg;` before the return. Everything else in parser.js is
untouched, so the existing Phase-1 harness cases keep validating the same
gate.

## Response contract (README states the spike-verified shape)
- 200 body: JSON array, one entry per branch, each with nodeId and the
  plugin write summary (accepted/duplicates/total/results).
- 400 body: reason text of the failed node (+ possibly the surviving
  branch's summary). Alert on non-2xx as in Phase-1.

## Commit boundaries (planned)
C1 task docs (this dir) + the fork/join spike under research/ (one-time
design-time verification, not a CI job).
C2 events.js + parser.js rawHex line + harness extension (goja, RFC-anchored).
C3 chain.json rewire + mappings/budva-events-v1.json + README deploy update.
