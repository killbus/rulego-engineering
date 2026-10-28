# Budva webhook → elasticsearchWrite example profile

Deploys the generic `elasticsearchWrite` node (from `killbus/rulego-elasticsearch`)
against the real Budva push contract (schema v2) using **only RuleGo-native
content**: three `jsTransform` nodes (embedded scripts below), two write
nodes, two indices — the current-state index and the append-only audit index —
joined before the HTTP response. `node_wire` is the single owner of crypto and
raw-byte handling; the other transforms are pure business logic. No Budva
semantics are compiled into the plugin, and nothing under this directory is
imported by the plugin package.

## What it does

```
POST /budva-to-es  (application/json, optional X-Budva-Signature)
  → toHex + headersToMetadata   (raw body → hex carrier; headers → metadata)
  → jsTransform budvaWire       (the only crypto owner: HMAC gate over the
                                 exact wire bytes, publishes
                                 metadata.audit_id = sha256(raw), and hands
                                 downstream the body decoded as a string)
  → jsTransform budvaParse      (strict schema v2 validation, _id derivation,
                                 tombstone for deleted — pure business)
  → fork
      ├→ elasticsearchWrite     (budva-messages-v1, op index, LWW)
      └→ jsTransform budvaEvents (audit projection: consumes
                                 metadata.audit_id — pure business)
           → elasticsearchWrite  (budva-events-v1, op create, append-only)
  → join (timeout 45s)
  → 200 + joined ack  |  400 + reason  (Budva never retries; the code is the signal)
```

- `budva-messages-v1` = current state per message, `_id = <chat_id>:<message_id>`,
  unconditional overwrite (`op: index`), ordering fact is `occurred_at`.
- `deleted` events write a `tombstone: true` doc (the write node cannot issue
  deletes). Reconstruct live messages with `{"query":{"bool":{"must_not":{"term":{"tombstone":true}}}}}`.
- `budva-events-v1` = append-only delivery log, one doc per delivery,
  `_id = sha256(exact raw body)`, `op: create` — a redelivered body is the same
  `_id` and becomes an ES 409 duplicate, which the plugin classifies as success
  (idempotent, no second doc). The audit doc is `{event, occurred_at, chat_id,
  message_id, received_at}`: a delivery log, not a second copy of message text.
- Why a wire node at all: jsTransform nodes are isolated VMs — a node
  cannot call another node's functions, and a chain file cannot inject UDFs.
  So the crypto capability atomic is a NODE that computes and publishes
  values (`metadata.audit_id`) that other nodes consume, instead of inlining
  the same crypto source into every consumer (which would duplicate it in
  the running chain). The harness asserts the single-owner property
  (`TestCryptoSingleOwner`): `parser.js` and `events.js` contain no crypto
  symbol, and `chain.json` embeds crypto in exactly one node.
- Response contract (verified by the task's fork/join spike, see "Audit
  index behavior" below): the join is the chain's single terminal, so the
  response is deterministic. 200 body = the joined
  array of BOTH write summaries (messages + events); one-branch failure = a
  **fast 400** with the failed node's reason (the failed branch is terminal and
  fires its own OnEnd; it does not wait the join timeout). A 400 does not roll
  back the other branch: fork/join is not a transaction.

## Loss model (read this before deploying)

Budva delivery is **at-most-once, single attempt, in-memory buffer**. Under this
contract:

- The failure mode is **missing** updates (process restart before flush, HTTP
  failure), **not** reversed updates. Reversal can only come from a producer
  restart whose buffer held an older edit.
- The chain cannot make Budva retry: 4xx/5xx are terminal for the sender.
  What is dropped is gone from the current-state index. Reconciliation: the
  `occurred_at` ordering plus the producer's own observation log, now backed by
  a query — the audit index holds every delivery that reached the chain, so a
  missing update is detectable by diffing the audit log against the producer's
  observation record. A delivery that failed the audit write but succeeded the
  messages write (or vice versa) is visible as the 400 alert.
- **Do not** put durability guarantees on this pipeline. It is a mirror, not a
  system of record.

## Files

| File | Role |
| --- | --- |
| `crypto.js` | vendored pure-JS SHA-256/HMAC-SHA256 + hex/UTF-8 codec (RFC 6234/2104), no goja builtins — the shared capability, embedded in exactly one node |
| `wire.js` | `node_wire` body: the single crypto owner — HMAC gate over exact wire bytes, publishes `metadata.audit_id = sha256(raw)`, decodes the body for downstream (pure business downstream sees a string, never bytes) |
| `parser.js` | `node_parse` body: strict schema v2 validation, messages contract emit, tombstone for deleted — **no crypto** |
| `events.js` | `node_events` body: pure audit projection, consumes `metadata.audit_id`, `received_at` = server receipt time — **no crypto** |
| `parser_test.go` | goja harness: runs the **deployed** scripts through rulego v1.0.0's `GojaJsEngine` with the node's exact wrapper; anchors = RFC 6234 digests, Go-stdlib HMAC/SHA-256 references, the plugin message contract, redelivery idempotency; `TestCryptoSingleOwner` asserts crypto lives in exactly one node; chain-embedding + topology drift guard |
| `chain.json` | rule chain: endpoint + wire + parse + fork + two write nodes + events + join; each `jsScript` is byte-identical to its tested source (guard-tested) |
| `mappings/budva-messages-v1.json` | current-state index body, `dynamic: false` |
| `mappings/budva-events-v1.json` | audit index body, `dynamic: false` |
| `fixtures/` | `new.json` / `edited.json` / `deleted.json`, real-shape samples |

## Deployment

### 1. Indices

```bash
curl -X PUT "$ES/budva-messages-v1" \
  -H 'Content-Type: application/json' \
  --data @mappings/budva-messages-v1.json

curl -X PUT "$ES/budva-events-v1" \
  -H 'Content-Type: application/json' \
  --data @mappings/budva-events-v1.json
```

The audit index grows with delivery volume (one doc per delivery, small doc).
Size it (and, later, ILM) like a log, not like the current-state index.

### 2. Shared Elasticsearch node (node pool)

Create it once (management UI or API) so the chain can borrow it via `ref://`,
instead of inlining credentials per chain. Credentials come from **global
properties** — never from this repository:

```
global properties:
  elasticsearch_username  <user>
  elasticsearch_password  <password>
  budva_hmac_key          <key or empty>
```

The node configuration in `chain.json` already references
`ref://shared_elasticsearchWrite` with `auth.type=basic` and the two `${global.*}`
placeholders; adjust the ref id if your shared node has another id.

### 3. Chain

Import `chain.json` (management UI → rule chain import, or the chains API).
Then verify the route is registered on the shared HTTP server:

```bash
curl -i -X POST "$RULEGO:9090/budva-to-es" \
  -H 'Content-Type: application/json' \
  --data @fixtures/new.json
# expect: 200 + ack JSON
```

### 4. HMAC (optional, default OFF)

- `budva_hmac_key` empty (default): signature is not required. Acceptable only
  while the network boundary is clean (see checklist).
- Key set: Budva must be configured with the same `HMACSecret` (it then sends
  `X-Budva-Signature: sha256=<hex>` = HMAC-SHA256(secret, exact raw body)); the
  chain verifies over the captured raw bytes and drops mismatches with `400`
  and an `hmac: ...` reason.
- Trade-off (decided 2026-10-28): verification happens **in-chain**, so a
  request aborted before the parse node (e.g. endpoint read timeout) is not
  signature-checked before being dropped. With the key unset there is no attack
  surface from this window; with the key set it only affects *when* a bad
  signature is rejected, not whether the data is trusted. A fronting proxy is
  the atomic alternative if that matters.
- Note: `responseToBody` maps every chain error to HTTP 400 (v1.0.0
  `processor.go`); HMAC failures are distinguishable by the `hmac:` reason
  prefix, not by status code.

## Production checklist

- Network boundary: `POST /budva-to-es` reachable only from Budva's egress
  (ingress allowlist). No path-level allow/deny exists in the endpoint.
- Management plane on the same port: set `require_auth=true` with a strong
  admin token (default is anonymous admin), or put the management API behind
  its own network segment.
- Body limits: align the proxy `max_body_size`, the endpoint `readTimeout`/
  `writeTimeout` (seconds), and the node `maxRequestBytes` (default 30 MiB)
  with the expected Budva payload size.
- Alerting: non-2xx on `/budva-to-es` = lost delivery (Budva won't retry).
- `runLogMode: detail` logs doc contents — keep it off in production (as in
  `chain.json`).

## Verification (local, no network)

```bash
cd examples/budva-to-es
go test ./...          # + go test -race ./...
```

Covers: RFC 6234 digests under goja, Go-stdlib-referenced HMAC (incl. 64/65-
byte key paths), schema strictness, the six HMAC gate cases, the emitted
plugin contracts (messages LWW + audit create), the audit `_id` against a
Go-stdlib SHA-256 reference, redelivery idempotency (same raw => same id),
that `chain.json` embeds ALL THREE tested scripts byte-identically with the
load-bearing route/topology facts (processor order, `wait:true`,
`responseToBody`, wire-first entry, fork/join wiring, `ref://` servers, join
timeout), and the single-owner property (`TestCryptoSingleOwner`: crypto
embedded in exactly one node, none in parser.js/events.js). A mutation check
confirmed the crypto harness and the drift guard fail when the code or the
embedded script changes. The response contract stated in "Audit
index behavior" below was established by the task's fork/join spike (task
research: `.trellis/tasks/10-28-budva-events/research/forkjoin-spike/`, real
engine + real HTTP endpoint) — a one-time design-time verification against
pinned rulego v1.0.0, not a standing regression of this example.

## Audit index behavior (Phase-2, shipped)

The fork/join + `wait` + response interaction was verified before this shipped
by the task's fork/join spike (task research, `.trellis/tasks/10-28-budva-events/research/forkjoin-spike/`):

- Both writes are reflected in one deterministic 200 (the join is the single
  terminal; the response waits for both — observed latency ≥ the slower write).
- A failed write is NOT masked: the failed branch is terminal, so the response
  is 400 with the failed node's reason immediately (~50ms observed, not the
  join timeout). The surviving branch may still be written; there is no
  rollback, and a redelivery of the same body is idempotent on the audit side
  (409 → duplicate → success).
- Alert on non-2xx from `/budva-to-es` as the loss signal; a 400 naming
  `node_write_events` means the audit side missed while messages may have
  landed, and vice versa. Reconcile via the audit log + producer observation
  record.
