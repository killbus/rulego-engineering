# Implement notes: Budva example profile

## Source-verified decisions (rulego v1.0.0 module, the ABI-compiled version)
- Processor order `["toHex","headersToMetadata"]` is the native raw-body +
  signature-header capture: toHex (processor.go:240) sets msg = uppercase-hex(raw)
  and REPLACES the msg (fresh metadata), so headersToMetadata MUST run after it to
  re-stamp headers (incl. X-Budva-Signature) onto the hex msg. No custom processor.
- jsTransform wraps the jsScript as `function Transform(msg, metadata, msgType,
  dataType){...}` (JsTransformFuncTemplate) and injects config.Properties as
  `global` (js_engine.go:138). UDFs via config.RegisterUdf(name,
  types.Script{Js, src}) are precompiled + RunProgram'd into the VM (js_engine.go
  PreCompileJs/NewVm) — exactly how the server's DataDir/js loader registers UDFs.
- Harness (parser_test.go) reproduces that wiring with the real
  GojaJsEngine + JsTransformFuncTemplate + goja pinned to the same version
  rulego v1.0.0 uses (v0.0.0-20231024180952), so a green test = the committed JS
  is the JS that runs in the chain. It imports rulego, never the plugin package.
- responseToBody hardcodes 400 on error (processor.go:266): HMAC/schema failures
  are 400 with a reason, not 401. Recorded as a constraint, not a bug.
- wait:true => OnMsgAndWait (engine.go:1135); the HTTP response reflects the write.

## Bugs found by the harness (evidence it is not self-attesting)
1. SHA-256 64-bit big-endian length block was mis-indexed (low byte dropped, upper
   shifted). `sha256_empty` passed (bitLen=0 masks it) but `sha256_abc` failed.
   Fixed to hi[32] then lo[32] per RFC 6234.
2. My "RFC 4231" Jefe digest constant was a memorized (wrong) value. Replaced with
   a Go-stdlib-computed reference at test time (independent implementation) — no
   memorized HMAC constants. SHA-256 empty/abc still use the well-known RFC 6234
   digests.

## Mutation check
Flipping one SHA-256 S1 round op in crypto.js => TestCryptoVectors red; restore =>
green. Confirms the test anchors to the crypto output, not to the test's own text.

## Gates
go test ./... (incl. -race), gofmt -l (empty), go vet — all green.

## Boundary commits
- docs: prd.md + design.md (this task dir).
- tested core: examples/budva-to-es/{go.mod,go.sum,crypto.js,parser.js,parser_test.go,fixtures/}.
- deploy surface: examples/budva-to-es/{chain.json,mappings/,README.md}.
