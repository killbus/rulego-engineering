# Budva webhook → elasticsearchWrite example profile

Deploys the generic `elasticsearchWrite` node (from `killbus/rulego-elasticsearch`)
against the real Budva push contract (schema v2) using **only RuleGo-native
content**: one `jsTransform` node (embedded script below), one write node, one
index. No Budva semantics are compiled into the plugin, and nothing under this
directory is imported by the plugin package.

## What it does

```
POST /budva-to-es  (application/json, optional X-Budva-Signature)
  → toHex + headersToMetadata   (raw body → hex carrier; headers → metadata)
  → jsTransform budvaParse      (HMAC gate, strict schema v2 validation,
                                 _id derivation, tombstone for deleted)
  → elasticsearchWrite          (budva-messages-v1, op index, LWW)
  → 200 ack  |  400 + reason    (Budva never retries; the code is the signal)
```

- `budva-messages-v1` = current state per message, `_id = <chat_id>:<message_id>`,
  unconditional overwrite (`op: index`), ordering fact is `occurred_at`.
- `deleted` events write a `tombstone: true` doc (the write node cannot issue
  deletes). Reconstruct live messages with `{"query":{"bool":{"must_not":{"term":{"tombstone":true}}}}}`.
- Audit index (`budva-events-v1`, append-only, `_id = sha256(raw)`): **Phase-2**,
  see "Phase-2" below.

## Loss model (read this before deploying)

Budva delivery is **at-most-once, single attempt, in-memory buffer**. Under this
contract:

- The failure mode is **missing** updates (process restart before flush, HTTP
  failure), **not** reversed updates. Reversal can only come from a producer
  restart whose buffer held an older edit.
- The chain cannot make Budva retry: 4xx/5xx are terminal for the sender.
  What is dropped is gone from the current-state index. The `occurred_at`
  ordering plus the producer's own observation log is the reconciliation path;
  the Phase-2 audit index makes that reconciliation a query.
- **Do not** put durability guarantees on this pipeline. It is a mirror, not a
  system of record.

## Files

| File | Role |
| --- | --- |
| `crypto.js` | vendored pure-JS SHA-256/HMAC-SHA256 + hex/UTF-8 codec (RFC 6234/2104), no goja builtins |
| `parser.js` | the transform body: HMAC gate over exact wire bytes, strict schema validation, contract emit |
| `parser_test.go` | goja harness: runs the **deployed** script through rulego v1.0.0's `GojaJsEngine` with the node's exact wrapper; anchors = RFC 6234 digests, Go-stdlib HMAC reference, plugin message contract; includes the chain-embedding drift guard |
| `chain.json` | rule chain: endpoint + jsTransform + elasticsearchWrite; `jsScript` is byte-identical to `crypto.js + parser.js` (guard-tested) |
| `mappings/budva-messages-v1.json` | `dynamic: false` index body |
| `fixtures/` | `new.json` / `edited.json` / `deleted.json`, real-shape samples |

## Deployment

### 1. Index

```bash
curl -X PUT "$ES/budva-messages-v1" \
  -H 'Content-Type: application/json' \
  --data @mappings/budva-messages-v1.json
```

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
plugin contract, and that `chain.json` embeds exactly the tested script with
the load-bearing route facts (processor order, `wait:true`, `responseToBody`,
`ref://` server). A mutation check confirmed both the crypto harness and the
drift guard fail when the code or the embedded script changes.

## Phase-2 (not shipped)

`budva-events-v1` audit index: append-only, `op: create`, `_id = sha256(raw)`,
so a redelivered body is an idempotent duplicate (409 → success). Requires a
`fork → [parseEvents→writeEvents, parseMessages→writeMessages] → join` topology
(v1.0.0 ships `fork`/`join` natively); the fork/join + `wait` + response
interaction is to be verified end-to-end before this lands. The mappings for
the audit index will follow the same `dynamic: false` discipline.
