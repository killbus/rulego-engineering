# Frozen dependency surface and the four routes

Analysis only. No IM or FF file was modified. Every line reference is from the
working trees on 2026-10-23.

## 1. Dependency surface (AC1)

Exhaustive: every occurrence of the import alias in the IM tree is accounted
for. `grep ffmpegclient` over `rulego-indexed-media/*.go` yields 30 lines in 6
files: 7 lines in 2 production files (`producer.go:18,110,114,281` and
`source.go:16,53,65`, of which 2 are the import), and 23 lines of test
scaffolding in 4 test files.

| Symbol | Production use | Test use |
| --- | --- | --- |
| `client.Run` | `source.go:65` (default for `runFn`) | none - tests inject their own `runFn` |
| `client.Config` | `producer.go:110-113`, `source.go:53` | stub signature, fields never read |
| `client.Invocation` | `producer.go:114`, `source.go:53` | stub signature; `Args` asserted |
| `client.OutputFunc` | `source.go:53` only - the call site passes `nil` (`producer.go:117`) and no code ever invokes the callback | stub signature |
| `client.Error` | `producer.go:281` (`errors.As`) then `switch remote.Kind` | constructed: `producer_modes_test.go:267,359`, `producer_test.go:199,214,260` |

Fields actually consumed: `Config.Address`, `AuthSecret`, `DialTimeout`
(`producer.go:111-112`); `Invocation.Program`, `Args`, `MaxOutputBytes`
(`producer.go:114`); `Error.Kind`. IM never reads `Invocation.Stdin`,
`Invocation.OnFileReady`, or `Error.ExitCode` - verified by grep, zero hits
outside the FF module. `OutputFunc` is in the signature but never called.

So the production surface is 6 symbols, 7 fields, and the `error` method set.
Half of `Invocation` and part of `Error` are imported shape, not consumed
behaviour.

### Error alphabet that IM must classify

FF emits 10 kinds from the non-test sources: `canceled`, `configuration`
(`client.go:63`), `internal`, `invalid_input`, `output_limit`, `protocol`,
`server`, `timeout`, `transport`, plus `exit` constructed at
`client/client.go:221`. Counted by enumerating every `safeError("…")` and
`&Error{Kind: "…"}` literal outside `_test` files.

IM maps them at `producer.go:289-298`: `output_limit` to `output_limit`,
`canceled` to `canceled`, `transport|server|timeout` to retryable, everything
else (including `internal`, `invalid_input`, `protocol`, `exit`) to
`production_failed`. The alphabet is the real contract: an adapter may choose
its own type freely as long as these ten strings keep their meaning.

## 2. Correction to an earlier claim in this task's PRD

This session earlier implied that dropping the FF dependency would remove the
Go-plugin shared-identity invariant. It does not:

- `rulego-indexed-media/go.mod`, `rulego-resource-origin/go.mod` and
  `rulego-ffmpeg-over-ip/plugin/go.mod` all require
  `github.com/rulego/rulego v1.0.0`.
- Every plugin therefore shares the RuleGo package set regardless of the FF
  client, and the loader's identity check stays load-bearing for that set. That
  is precisely what the ABI lock pins.

What route A removes is only the FF-specific instance of a shared package
(`rulego-ffmpeg-over-ip/client`), not the family of assertions. Any claim that
decoupling deletes `ci.yml:236`-style checks entirely is wrong, and this note
supersedes it.

## 3. Four routes, same six questions

| Question | A1 own client | A2 own interface + FF-client adapter | B separately versioned contract module | C declarations only |
| --- | --- | --- | --- | --- |
| Shape | IM implements protocol framing itself | IM types everywhere; one adapter file imports the FF client | Contract module holds types + protocol constant; FF client implements it; IM links contract module and client | unchanged code |
| Does IM still link `.../client`? | no | yes (adapter) | yes (execution needs an implementation) | yes |
| Shared package identity with the FF plugin | broken | kept | kept | kept |
| Who proves it | the ABI lock covers RuleGo packages only; the FF client package is then unshared, so nothing to prove for it | still needs the equality check | still needs it, comparing the contract module version | FF `ci.yml:236` |
| Protocol change, who moves | IM re-implements framing and HMAC - the private-implementation reach that `.trellis/spec/guides/rulego-ownership.md` forbids | FF releases the client; IM bumps the adapter | FF bumps contract and client; IM bumps the contract only if a type it uses changed | IM bumps the client whenever FF's plugin cadence moves, even when the protocol is unchanged |
| IM unit tests import FF | no | signature types no, adapter yes | no | yes |
| New release ordering | none | none | the contract module needs its own tag cadence | none |

### Why A1 is rejected

`rulego-ffmpeg-over-ip/client/protocol.go` owns a framed, HMAC-authenticated
wire format (`ProtocolVersion = uint8(0x06)` at `:15`, used at `:113` and
`:131`). A second implementation inside IM would be the exact "reach through
another component's private implementation" case the ownership guide prohibits,
and nothing would catch silent drift between the two implementations.

### Why A2 is close to a no-op

The only thing A2 buys is that `producer.go` stops naming FF types. The link
stays, the shared identity stays, the equality assertion stays, and the version
cadence stays. It is a naming refactor, not a decoupling. It is fine as a
readability change; it must not be sold as contract separation.

### Why C is the recommendation, with B's trigger written down

Observed cost of the cadence coupling so far is one instance: FF `client/` is
byte-identical from `v0.5.0` to HEAD (`git diff --stat v0.5.0 HEAD -- client` is
empty) while the repository released `0.5.1` and `0.5.2`. IM therefore pins a
client version chosen by plugin-release timing rather than by protocol change.
That is noise, not yet a broken contract.

C closes the gap that causes incidents today - the consumer side declares
nothing:

```json
{
  "pluginVersion": "0.3.1",
  "pluginAbiRelease": "plugin-abi-release.json",
  "rulegoRelease": "v1.0.0",
  "ffmpegOverIp": { "protocol": 6, "clientModule": "v0.5.0" }
}
```

paired with one assertion that the compiled record equals the declaration:

```bash
test "$(awk '$1=="dep" && $2=="github.com/killbus/rulego-ffmpeg-over-ip"' \
        plugin/tmp/module-info.txt)" = \
     "dep github.com/killbus/rulego-ffmpeg-over-ip $(jq -er .ffmpegOverIp.clientModule compatibility.json)"
```

IM already produces `plugin/tmp/module-info.txt` at `ci.yml:116-129`, so the
assertion costs one line and needs no peer download. FF keeps its own
`ffmpegOverIp{version,revision,protocol}` block in `compatibility.json:5-9`;
this makes the two sides symmetrical.

B becomes worth its tag-cadence overhead on either of these observations, and
not before:

- a FF release changes a type IM consumes (`Config`, `Invocation`, `Error`, or
  the kind alphabet) while the protocol stays 6 - then every FF plugin release
  forces an IM release for a non-protocol reason; or
- a second consumer of the client appears, making the pinned-version triangle
  impossible to satisfy by coincidence.

Both are observable in release diffs, so the trigger is not a judgement call.

## 4. Effect on `rulego-ffmpeg-over-ip/.github/workflows/ci.yml:236`

Under C the step stays as it is, and `:237` (candidate equals the pinned
`v0.5.0` plus `h1:` hash) remains the order-independent half. Under B the
comparison target becomes the contract module version. Under A1 it disappears,
at the cost named above. Under A2 it stays. Under every route the set-level half
of that step belongs to the composition carrier decided in
`../10-20-rulego-v1-upgrade/research/coexistence-ownership-first-principles.md`;
this task changes none of it.

## 5. What remains unproven

The claim "the IM and FF plugins share only the RuleGo package set plus the FF
client" was established from `go.mod` pins, not from `go version -m` on two
matching-runtime `.so` files. Two facts make the static reading safe to use
here: the ABI lock pins the RuleGo module for all plugins, and the FF client is
the only non-RuleGo outside module IM requires besides its own. Confirming it
properly needs the digest-pinned SDK image, and the local toolchain is not the
matching toolchain (`.trellis/spec/guides/rulego-plugin-delivery.md`), so that
check belongs in CI rather than on this workstation.
