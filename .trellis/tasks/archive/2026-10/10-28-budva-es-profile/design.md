# Design: Budva example profile (verified against rulego v1.0.0 module source)

## Source-of-truth (compiled into the plugin ABI)
All behavior below is pinned from `~/go/pkg/mod/github.com/rulego/rulego@v1.0.0`
(the module the plugin links), NOT the worktree.

## Design facts
1. Plugin contract is single-index: `{"index","operations":[{op,id,doc}]}`
   (rulego-elasticsearch client.go:41). One message = one index. Phase-1 ships
   the `budva-messages-v1` index only (the consumer's current-state store); the
   `budva-events-v1` audit index is Phase-2 (fork/join topology, unverified).
2. HMAC must verify over the exact raw body bytes. The jsTransform `msg` arg is
   the PARSED object (base.go:108 GetDataByType unmarshals JSON into a map);
   re-serializing in JS cannot byte-match the wire (Go vs JS JSON escaping).
   => capture the raw bytes at the endpoint. v1.0.0 `toHex` (processor.go:240)
   captures raw but REPLACES the msg (drops prior metadata), so the processor
   ORDER is load-bearing: `["toHex","headersToMetadata"]`. toHex sets msg =
   uppercase-hex(rawBody) (TEXT) + metadata{topic}; the following
   headersToMetadata re-stamps ALL request headers (incl. X-Budva-Signature)
   onto that hex msg (GetMsg() is cached: rest.go:356 + processor.go:216).
   Result: parser gets msg=hex(raw) and the signature header, with NO custom
   processor. Parser hex-decodes -> UTF-8-decodes -> JSON.parse -> extracts, and
   signs the SAME raw bytes it parsed (byte-consistent).
3. Error status is fixed at 400: responseToBody hardcodes http.StatusBadRequest
   on error (processor.go:266); a chain cannot set a custom status natively.
   => HMAC failure is 400 with an "hmac" reason text, NOT 401. Functionally
   equivalent for Budva (no retry either way; the reason text is the signal).

## Data flow (deployed, Phase-1)
```
Budva (at-most-once, 1 attempt)
  | POST /budva-to-es  application/json  X-Budva-Signature: sha256=<hex>
  v
endpoint/http route, from.processors = ["toHex","headersToMetadata"], to.wait=true
  | toHex:             msg = uppercase-hex(rawBody) as TEXT, metadata{topic}
  | headersToMetadata: all request headers -> that msg metadata (incl. signature)
  v
jsTransform "budvaParse" (parser.js; node wraps it as
  function Transform(msg, metadata, msgType, dataType) {...})
  | 1. msg = uppercase-hex(rawBody); rawBytes = hexToBytes(msg)  (exact wire bytes)
  | 2. obj = JSON.parse(utf8Decode(rawBytes))  (parsed from the exact raw bytes)
  | 3. HMAC policy: global.budva_hmac_key == "" => accept, signature not required
  |    key set => header must be "sha256=<64hex>", recompute HMAC-SHA256 over
  |    rawBytes, constant-time compare; mismatch/absent => drop with Error
  | 4. require obj.schema_version==2, event in {new,edited,deleted},
  |    chat_id/message_id finite numbers
  | 5. emit single-index message:
  |      {index:"budva-messages-v1",
  |       operations:[{op:"index", id:"<chat_id>:<message_id>",
  |                    doc:{event, occurred_at, tombstone?, <state fields>}}]}
  |    deleted => doc {event, occurred_at, tombstone:true, chat_id, message_id}
  |    (node op whitelist is create|index; no physical delete)
  v
elasticsearchWrite (configuration.server = ref://<shared ES node id>)
  |-- Success (incl. 409-duplicate) -> respond 200 ack
  +-- Error (retryable/terminal/auth) -> respond 400 + node reason
```
wait semantics pinned: rest.go:1197 reads to.IsWait(); rest.go:1312 handler keeps
the request context when isWait; the chain executor (impl/endpoint.go) uses
ruleEngine.OnMsgAndWait (engine.go:1135). The HTTP response therefore reflects
the write outcome (matches the live T1-T3 observations).

Processor order is load-bearing: toHex REPLACES the msg, so headersToMetadata
MUST run after it (it reads the cached hex msg and adds headers). Reversed order
= original parsed msg kept but the signature header lost.

## UDF delivery (no server DataDir coupling)
Single `crypto.js` UDF (pure JS: hex/utf8/sha256/hmac/ct-compare). Delivery:
inline it into the chain via the RuleGo UDF mechanism so the example is one
deployable artifact; fallback if the v1.0.0 inline-UDF key does not reach the
jsTransform VM: ship `crypto.js` under `examples/budva-to-es/js/` and document copying
it into the server `DataDir/js/` (server loads `*.js` there as UDFs by filename,
server internal/engine/manager.go loadJs). Decision recorded at implement time
against the v1.0.0 jsTransform + config.Udf contract.

Parser reads the HMAC key from `global.budva_hmac_key` (server global property;
the js engine injects config.Properties as `global`, js_engine.go:138). Empty
string = HMAC off. Key is never committed; README shows how to set it.

## crypto.js (pure JS, no goja builtins)
- hexToBytes (upper/lower hex -> byte array) — the raw-body carrier.
- utf8Decode (byte array -> JS string, pure ES; NO TextDecoder — goja lacks it)
  — required because Telegram text is multi-byte UTF-8.
- SHA-256 (RFC 6234): 64-byte block padding, big-endian, over byte array.
- HMAC-SHA256 (RFC 2104): ipad/opad 64-byte block; key > 64B => key = H(key).
- Constant-time compare: xor-accumulate; length mismatch rejects immediately.
- Vectors (harness test, run under goja): SHA-256("")/SHA-256("abc") RFC 6234;
  HMAC-SHA256 RFC 4231 case 2 (key "Jefe"); 64- and 65-byte keys (hash-key
  path); hexToBytes+utf8Decode round-trip on a multi-byte UTF-8 fixture.

## id / LWW / tombstone
- `_id = String(chat_id) + ":" + String(message_id)` — stable per message.
- op `index` (unconditional overwrite); ordering fact = `occurred_at`.
- Failure mode under at-most-once is MISSING updates, not reversal; reversal only
  across a producer restart whose buffer held an older edit. The audit index
  (Phase-2) makes ordering reconcilable; Phase-1 README states the accepted model.
- deleted => tombstone doc (no physical delete: node op whitelist is
  create|index only). Reconciliation query: filter tombstone:false.

## Mapping discipline (budva-messages-v1)
- Root `dynamic:false`; only documented fields mapped.
- chat_id/message_id/reply+forward ids/user ids: `long`.
- sent_at/edited_at/occurred_at: `date` `strict_date_optional_time||epoch_millis`.
- event/content.type/sender.type/entity.type/source_type: `keyword`.
- has_sensitive_content/show_caption_above_media/has_spoiler/tombstone: `boolean`.
- entities: `nested` {offset integer, length integer, type keyword}.
- formatted_text.text: `text` (standard analyzer), plus `keyword` subfield for
  exact-match debugging. No ILM/aliases in v1.

## Response semantics
- 200 + ack on Success (incl. duplicate).
- 400 on jsTransform failure (schema error, HMAC mismatch -> reason starts
  "hmac:"), or on elasticsearchWrite failure with the node's reason text
  (responseToBody: error -> 400 + err.Error()).
- Budva never retries: the status + reason are the only honest signal; README
  instructs operators to alert on non-2xx from this route.

## Atomic commit boundaries (planned)
C1 task docs + go.mod/go.sum (module skeleton, no behavior).
C2 crypto.js + goja harness (external facts: RFC 4231/6234 vectors).
C3 parser.js + fixtures (parser contract anchored to the plugin message contract).
C4 chain.json + mapping + README (deployment surface).
One coherent change per boundary; no WIP commits; fragment convergence on the
previous boundary commit only.
