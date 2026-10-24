# Co-existence ownership, from first principles

Written 2026-10-23 while deciding the options in
`coexistence-gate-verdict.md`. It does not change the chosen implementation;
it corrects one premise that the deadlock write-up quietly relied on.

## The premise being corrected

`coexistence-release-deadlock.md:58` records that `ffmpeg-over-ip` "needs"
`indexed-vod v0.2.0` and `resource-origin v0.1.1`, and `:57` that
`indexed-media` "needs" a released `ffmpeg-over-ip` on the new ABI. Read as
repository dependencies, that is a symmetric cross-repo cycle, and a cycle
explains the deadlock.

Verified against source, the dependency is not symmetric:

| edge | where it lives | real? |
| --- | --- | --- |
| indexed-media -> ffmpeg-over-ip | `rulego-indexed-media/go.mod` requires `github.com/killbus/rulego-ffmpeg-over-ip v0.5.0`; `node.go:36-37`, `producer.go:18`, `source.go:16` import `.../client` | compile-time, one-way |
| ffmpeg-over-ip -> indexed-media | nowhere in Go source. Only `COMPATIBILITY.md:11`, `README.md:101`, and `.github/workflows/ci.yml` | no |
| ffmpeg-over-ip -> resource-origin | nowhere in Go source | no |
| indexed-media -> resource-origin | nowhere in Go source | no |
| resource-origin -> any sibling | nowhere, and `ci.yml` has no peer step at all | no |

So exactly one real edge exists, and it points **into** ffmpeg-over-ip. Every
"needs a released sibling" in the deadlock table is a property of the CI file,
not of the repository.

## Why the fabricated edge exists

The co-existence proposition is: *these N published .so files load together in
one process on this runtime.* That is an assertion about a **set**. It is not
an attribute of any member, so it has to be owned by someone, and that owner
must be able to address all members.

This fleet has no such owner, so the set assertion was replicated into member
gates. `rulego-ffmpeg-over-ip/.github/workflows/ci.yml:173-213` downloads two
sibling releases and verifies their sidecars, `:215-236` compares the compiled
client module identity between candidate and peer, and `:247-306` smoke-loads
all three in both filename orders.
`rulego-indexed-media/.github/workflows/ci.yml:209-244` does the same with a
different pair. Two members each prove the same three-element set, each
treating itself as the candidate and the other two as downloads.

The structural consequence, independent of versions: an N-member set assertion
embedded in every member's release gate requires N-1 already published
members, so no member can be first. Any synchronized migration of that fleet
deadlocks by construction. The cycle is an artifact of the placement, not of
the plugins.

## The control that is missing

`resource-origin` published first in this batch (`c6731ac`, main run
`39811100101`) because its `ci.yml` has three jobs - `test`, `build`,
`release-metadata` - and no co-existence step. Its gate never asks what else is
installed; its sidecar pins `abi_id`, `lock_digest`, `platform`,
`plugin_sha256` for its own bytes.

That is the self-attribute shape, and it is already load-bearing in
`release.yml` (`workflowName:conclusion` + `headSha`, both from `gh run view`).
It is not a workaround or a temporary exemption; it is the only member gate
shape that is order-independent.

The counter-lesson: origin's freedom to release came from *not carrying the set
assertion*, and the set has no other owner. So this batch's first three-plugin
co-existence evidence does not exist anywhere - a gap, not a property of the
winning design. Whatever the fleet believes about "we verify co-existence
before release" is true only for the two members whose gates happen to download
the other two.

## One assertion in the set is on the pre-rename name

`indexedVod` is not a second capability. It is the old name of the same
component: v0.3.0 renamed module, component type, artifact and cache names in
one deliberate breaking change, with "no `indexedVod` alias, forwarding module,
old-artifact selector, or cache fallback" (`rulego-indexed-media/README.md:168-173`).
So every remaining `indexedVod` string is residue of that rename, and the correct
question for each one is whether it is intentional residue or an un-migrated
leftover. Sorted by that test:

| site | string | verdict |
| --- | --- | --- |
| `rulego-indexed-media/ci.yml:129,163,165,176,177`, `tests/e2e-hls-seek.sh:193,196,215,216`, `node_test.go:45-65` | negative assertions | intentional - they prove the old name is gone |
| `rulego-indexed-media/node_test.go:630-663` | seeded `indexed-vod:` cache keys | intentional - proves stale entries are ignored rather than deleted, matching `README.md:165-166` |
| `rulego-ffmpeg-over-ip/ci.yml:194,196` | downloads `indexed-vod` artifact `v0.2.0` | leftover |
| `rulego-ffmpeg-over-ip/ci.yml:294` | `.nodes | any(.type == "indexedVod")` | leftover |
| `rulego-ffmpeg-over-ip/COMPATIBILITY.md:11,13,22`, `README.md:101` | names the retired peer to install alongside | leftover - user-facing, so it can send someone to install a retired artifact |

`rulego-indexed-media/node.go:23` is `componentType = "indexedMedia"`, and
`node_test.go:45-65` asserts `indexedVod` fails to load as an unregistered
component. The rename is documented in
`plugin-abi-contract-and-repo-impact.md:54` (v0.3.0, no alias, no forwarding).

`rulego-ffmpeg-over-ip/.github/workflows/ci.yml:294` still asserts
`.nodes | any(.type == "indexedVod")`, and it can pass only because
`:194-196` downloads the retired `killbus/rulego-indexed-vod v0.2.0` artifact.
The green light describes a set that no longer ships.

Two things follow, and they are separate findings:

- This is the concrete instance of the "green nobody re-reads" objection in
  `coexistence-gate-verdict.md:78-81`. It is not hypothetical; the assertion is
  live and wrong today.
- The migration target was already recorded as a repo swap
  (`plugin-abi-contract-and-repo-impact.md:109`, `implement.md:194-197`,
  `implement.md:365`). Because this is a rename rather than a removal, pointing
  the peer at `indexed-media` and changing the `:294` string to `indexedMedia`
  preserves the coverage the assertion was written for - "the third plugin
  registers in this process" - while updating only the identity it names. What is
  missing is not an approval to weaken a gate, it is the unrecorded half of a
  migration that was already approved: the plan lists the peer lines and never
  lists the node-type string or the two FF doc files.
  Doing one half alone is what breaks coverage: switch the peer artifact without
  the string and the smoke step demands a node type nothing registers; switch the
  string without the peer and it demands the type of an artifact no longer
  downloaded.

## What changes, what does not
Changes:

- The deadlock is not caused by a genuine symmetric cross-repo dependency. No
  source-level decoupling is required to break it.
- Options that keep the set assertion inside a member gate are paying a
  permanent structural cost to avoid a one-time ownership decision.
- `prd.md:152` (AC17) and this plan do not collide after all, and an earlier
  reading of this note said they did. AC17 updates an ownership-pointer in this
  documentation repository; the `ci.yml:294` string is a residue of the same
  rename in a different repository. Both are migrations of one decided change,
  not a gate argument. The real defect is narrower: `prd.md:131-133` (AC12)
  already requires the FF peer to point at the new artifact and the step to go
  green, and it does not list the node-type string that has to change for that
  step to be able to go green.
- Steady state: a component-level assertion lives in the member gate; a
  fleet-level assertion lives where the expected member set can be named.
  `coexistence-gate-verdict.md:44-50` records exactly that shape - the contract
  repo as release unit with the expected peer set declared in
  `compatibility.json` - as Conway's and Perrow's steady state, deferred only
  because adopting it changes release gate semantics mid-batch. That declaration
  is the precondition for a fleet gate that does not need a candidate to stand in
  for itself.

Does not change:

- The implementation chosen for this batch in `coexistence-gate-verdict.md`
  stands as written. Do not reopen it on the strength of this note.
- The `resource-origin` reproducibility step is a genuine experiment, not a
  wayfinding aid: its output is compared against a **published** value
  (`abi-3e0c9d46…`, `sha256:e19c9657…`), so a mismatch is evidence about the
  published artifact.
- The indexed-media residual is still unsatisfiable by "take the release", for
  the reason already recorded: the new-ABI bytes do not exist as a release yet.

## Open, not resolved here

1. Where the fleet-level assertion should live, given `release.yml` only accepts
   a run of its own repository. Five candidates were ranked in
   `coexistence-gate-verdict.md`; this note does not settle who owns the set
   once it leaves the member gates.
2. Whether "first releaser carries no fleet evidence" is acceptable as a
   permanent property of member-level gates, or must be closed by a fleet job
   that takes only published releases and runs after every batch member exists.
3. No required status checks exist on the three plugin repositories today, so
   no written ordering is a control - the same gap recorded in
   `coexistence-gate-verdict.md:35-39` and `coexistence-gate-verdict.md:96-98`.
   Verified by API 2026-10-24: `GET /branches/{main,master}/protection` returns
   404 "Branch not protected" for all three (RO/IM default `main`, FF
   `master`); this item stays open as a *future* control, not as unknown.
4. The split runs through the middle of one existing step. In
   `rulego-ffmpeg-over-ip/.github/workflows/ci.yml` the shared-identity step ends
   with two adjacent assertions: `:236` requires the candidate's client record to
   equal the peer's (set assertion), and `:237` requires it to equal `v0.5.0`
   plus the pinned `h1:` hash (member assertion - `plugin/go.mod` declares
   exactly that version). The member check already exists, so dropping the set
   check costs no coverage the repository cannot prove alone.
5. Module-identity coverage is uneven as member evidence: `indexed-media` checks
   its own module path at `ci.yml:116-129`, `ffmpeg-over-ip` checks its
   dependency version at `:237`, and `resource-origin` has neither - its
   `ci.yml` only greps the version string in `node.go` (`:33`). Closing that is a
   per-repository gap on its own schedule, not a blocker for this batch.

## Verified by API, 2026-10-24

Facts this note carried as local-only or unverified, now closed against the
GitHub API (read-only `gh api`):

- Branch protection: none. `GET /branches/{main,master}/protection` -> 404
  "Branch not protected" on all three plugin repos (RO/IM default `main`, FF
  `master`). Open item 3 is settled as a known gap, not an unknown.
- The three recorded run ids all exist and map as documented:
  `39810333396` = RO CI on PR #4 head `c7ae356` (success); `39811100101` =
  RO CI main push `c6731ac` (success); `39813678234` = IM CI on PR #5 head
  `f3e64b7` (failure).
- IM PR #5's red run: `test` / both `build` / `release-metadata` all
  success; the single failing job is the e2e `Hermetic selected-track TS
  and HLS seek` - the peer-download step, matching the local read.
- RO release v0.2.0: annotated tag -> commit `c6731ac` = the dispatch's CI
  run head; both `.so` sha256 values recomputed from the downloaded assets
  match the published `.sha256` files and the `plugin_sha256` fields in the
  published sidecars (amd64 `f6532aed…`, arm64 `19ab29f1…`); both sidecars
  carry `abi-3e0c9d46…` / `sha256:e19c9657…`, the batch's new ABI values.
  The "take the release" path therefore exists for RO from this day; the
  reproducibility experiment in FF's CI remains the one open byte-level
  question.
- FF's `ci.yml:294` green-light finding stands, with the peer side now
  visible in the release list: the retired `indexed-vod v0.2.0` artifact the
  download step fetches is a real, current release of
  `killbus/rulego-indexed-media` (tag `v0.2.0`), which is exactly why the
  old-name string still passes.
