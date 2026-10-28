# PRD: Budva audit index (budva-events-v1)

## Outcome
The deployed budva chain writes BOTH indices in one request: the existing
current-state index (budva-messages-v1) and the new append-only audit index
(budva-events-v1, one doc per delivery, `_id = sha256(raw body)`, op `create`
so a redelivered body is an idempotent 409 duplicate). This makes the
at-most-once loss model reconcilable: a dropped message becomes a query
against the audit log and the producer's observation record.

Single chain, in-chain `fork -> [messages, events] -> join` (option A, decided
2026-10-28). Budva configuration is untouched (one push target).

## Deliverables
1. `examples/budva-to-es/parser.js` — the existing parse (HMAC gate over the
   exact wire bytes, strict schema v2 validation, messages emit) gains one
   line: `metadata.rawHex = msg` (the toHex hex carrier of the exact raw
   body). The audit `_id` is derived from these bytes downstream. The
   parser stays the single owner of validation.
2. `examples/budva-to-es/events.js` — transform body for the audit branch:
   a pure projection. Both fork branches receive the same msg (the messages
   contract), so events.js reads the validated fields from
   `operations[0].doc` and `metadata.rawHex` for the id (`sha256Hex` of the
   exact wire bytes), emitting `{index, operations:[{op:"create", id,
   doc:{event, occurred_at, chat_id, message_id, received_at}}]}` for
   `budva-events-v1`. `received_at` = goja `new Date().toISOString()` at
   receipt time (server clock, first doc wins on redelivery). No second
   parse, no duplicated validation.
3. `examples/budva-to-es/chain.json` — rewires the chain:
   `node_parse -> node_fork -> [node_write (unchanged), node_events ->
   node_write_events] -> node_join`; join is default-merge (array of both
   branch results), `timeout: 45` (>= max write timeout 30s).
4. `examples/budva-to-es/mappings/budva-events-v1.json` — append-only
   mapping, `dynamic: false`.
5. `examples/budva-to-es/parser_test.go` — the harness extends: the audit
   branch is tested through the same goja engine (RFC-anchored SHA-256 id
   against a Go-stdlib reference), and the drift guard now pins the fork/join
   topology, the two write nodes, and both embedded scripts.
6. `examples/budva-to-es/README.md` — deploy section: create the second
   index; the Phase-2 section is replaced by the live behavior + the
   response contract from the spike (200 = joined array of both writes;
   one-branch failure = fast 400 with the failed node's reason; the failed
   branch may still be written on the other side, no rollback exists).
7. `.trellis/tasks/10-28-budva-events/` — task docs + the fork/join spike
   (spike/ module, run in CI as the runtime-semantics anchor for the
   chain's response contract).

## Acceptance
- Harness green under goja: parser emits messages contract + rawHex;
  events emits the audit contract; `_id` matches a Go-stdlib SHA-256 of the
  same bytes; redelivery idempotency is pinned (same raw => same id, op
  create).
- Drift guard: chain.json embeds both scripts byte-identically; topology
  (fork, join, both writes, Success edges) asserted.
- Spike module runs in CI (real engine + real HTTP endpoint): the response
  contract the README states (200 joined array / fast 400 on one-branch
  failure) is a test, not a claim.
- No secrets committed; Budva side unchanged; the chain imports via the same
  `ref://shared_elasticsearchWrite` owner node.

## Out of scope
- No rollback/compensation: fork/join is not a transaction. If one write
  fails the chain responds 400; the other index may have been written.
  The README states this as the loss model (reconciliation path = audit
  index + producer log), not a defect to hide.
- No ILM/aliases on the audit index in v1.
