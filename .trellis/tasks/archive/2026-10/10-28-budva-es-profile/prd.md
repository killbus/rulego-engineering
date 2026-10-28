# PRD: Budva webhook -> elasticsearchWrite example profile

## Outcome
A deployable, self-contained example under `examples/budva-to-es/` that proves the
generic `elasticsearchWrite` node against the real Budva push contract, using
only RuleGo-native content (jsTransform, a small JS-registered In-processor,
chain JSON, index mappings, fixtures). No Budva semantics compiled into the
Go plugin; the example is never imported by the plugin package.

Consumer-side half of the plugin's acceptance: it composes with the node as
deployed (HTTP endpoint -> chain), not against an invented API.

## Budva contract (facts from ~/Src/budva, schema v2, serializer.go)
- `schema_version: 2`; events `new | edited | deleted` (discriminators pinned).
- `occurred_at` = RFC3339 UTC, Budva observation time (NOT send/edit time).
- No event id; delivery is at-most-once (single attempt, in-memory buffer).
  Consumers must be idempotent and tolerate missing predecessors.
- `deleted` carries only identities + delete facts.
- Optional HMAC: `X-Budva-Signature: sha256=<hex>` = hex(HMAC-SHA256(secret, exact raw body)).
  Sent only when secret is configured (delivery.go:161).
- `message`: `chat_id`(long), `message_id`(long), `sent_at`, `edited_at`,
  `sender{type,user_id,chat_id}`, `content{type, source_type?,
  formatted_text{text, entities[{offset,length,type}]}, show_caption_above_media,
  has_spoiler}`, `reply_to`, forward, ids, `has_sensitive_content`,
  `restriction_reason`, `delete{is_permanent,from_cache}`.

## Deliverables
1. `examples/budva-to-es/README.md` — deployment walk-through: endpoint route, chain,
   node_pool shared ES owner + secret refs, index creation (mappings), HMAC key
   setup, loss model (at-most-once: what is lost, why tolerated), LWW honesty.
2. `examples/budva-to-es/crypto.js` — pure-JS SHA-256 + HMAC-SHA256 + base64/hex UDF,
   vendored with attribution, constant-time compare. Test vectors in-repo.
3. `examples/budva-to-es/parser.js` — jsTransform `budvaParse`: strict-validate schema,
   verify HMAC against raw (when key set), emit single-index `elasticsearchWrite`
   message for `budva-messages-v1` (`_id=<chat>:<msg>`, op `index`, LWW,
   `tombstone:true` for deleted).
4. `examples/budva-to-es/chain.json` — endpoint(`/budva-to-es`, `toHex`+
   `headersToMetadata`, wait:true) -> jsTransform -> elasticsearchWrite(ref) ->
   Success 200 ack; 400 with the reason otherwise (responseToBody).
5. `examples/budva-to-es/mappings/budva-messages-v1.json` — `dynamic:false` current-state
   mapping (ids long, times date, discriminators keyword, entities nested,
   tombstone bool).
6. `examples/budva-to-es/fixtures/new|edited|deleted.json` — real-shape samples.
7. `examples/budva-to-es/parser_test.go` + `go.mod` — goja harness runs the exact
   `crypto.js` + `parser.js` (same template the server wraps) and asserts the
   emitted `_id`/ops/tombstone + HMAC accept/drop. No network.

## Acceptance
- All JSON lints; `crypto.js` vectors pass under goja (empty, "abc", 64/65-byte,
  known HMAC-SHA256 RFC 4231 vectors); `parser.js` emits the right two-index
  (Phase-1: messages) operations and tombstone.
- HMAC: one valid + one tampered + one wrong-key assert accept/drop.
- README copy-pasteable against the deployed rulego-server-docker runtime; no
  secrets in any committed file.
- `examples/budva-to-es/` is not imported by the Go plugin package.

## Phase-2 (out of scope, documented)
`budva-events-v1` append-only audit index (`op=create`, `_id=sha256(raw)`),
via a `fork -> [events, messages] -> join` topology. Not shipped until its
fork/join+REST-response interaction is verified end-to-end.
